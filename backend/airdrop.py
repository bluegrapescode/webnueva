"""Sistema de Airdrop Global — La Isla Nublar.
Evento global por hora controlado por el servidor. Estado autoritativo en backend,
contador global sincronizado, claim ATÓMICO (un único ganador), loot table configurable
y entrega real de recompensas reutilizando los sistemas existentes:
  PrimeMeat = users.coins · Amberium = users.vip_coins (via add_transaction)
  Materiales = player_materials (crafting._grant_materials)
  Growth/Diet/Resurrection Tokens = db.inventory categoría "Tokens"
  Chat global = db.chat_messages · WebSockets = hub propio.
"""
import logging, os, uuid, random, asyncio
from datetime import datetime, timezone, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("airdrop")

_db = None
_add_transaction = None
_grant_materials = None
_admin_ids = set()
_jwt_secret = None
_jwt_algo = "HS256"
_is_staff_fn = lambda u: (u.get("role") == "admin") or (u.get("staff_rank") in {"owner", "admin", "mod", "helper"})

MATERIAL_TYPES = ["bones", "metal", "leather", "polymer"]
MATERIAL_NAMES = {"bones": "Hueso", "metal": "Metal", "leather": "Cuero", "polymer": "Polímero Orgánico"}
RARITIES = ["common", "rare", "epic", "legendary"]
RARITY_LABEL = {"common": "COMMON", "rare": "RARE", "epic": "EPIC", "legendary": "LEGENDARY"}

DEFAULT_SETTINGS = {
    "enabled": True,
    "interval_minutes": 60,
    "warning_seconds": 60,
    "falling_seconds": 10,
    "available_seconds": 180,   # ventana para reclamar tras aterrizar
    "cooldown_minutes": 5,      # espera tras cada airdrop antes del siguiente conteo
    "claim_enabled": True,
    "rarity_weights": {"common": 60, "rare": 25, "epic": 12, "legendary": 3},
    "loot": {
        "common":    {"materials": {"chance": 100, "picks": 2, "min": 4,  "max": 12},
                      "primemeat": {"chance": 60, "min": 10000, "max": 15000},
                      "amberium":  {"chance": 10, "min": 50,  "max": 80},
                      "growth_token": {"chance": 3}, "diet_token": {"chance": 3}, "resurrection_token": {"chance": 0}},
        "rare":      {"materials": {"chance": 100, "picks": 3, "min": 8,  "max": 20},
                      "primemeat": {"chance": 75, "min": 12000, "max": 25000},
                      "amberium":  {"chance": 25, "min": 50,  "max": 120},
                      "growth_token": {"chance": 8}, "diet_token": {"chance": 8}, "resurrection_token": {"chance": 1}},
        "epic":      {"materials": {"chance": 100, "picks": 4, "min": 15, "max": 40},
                      "primemeat": {"chance": 90, "min": 20000, "max": 45000},
                      "amberium":  {"chance": 45, "min": 75,  "max": 200},
                      "growth_token": {"chance": 18}, "diet_token": {"chance": 18}, "resurrection_token": {"chance": 4}},
        "legendary": {"materials": {"chance": 100, "picks": 4, "min": 30, "max": 80},
                      "primemeat": {"chance": 100, "min": 40000, "max": 90000},
                      "amberium":  {"chance": 70, "min": 100, "max": 400},
                      "growth_token": {"chance": 35}, "diet_token": {"chance": 35}, "resurrection_token": {"chance": 12}},
    },
}


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).isoformat()


def _nid():
    return uuid.uuid4().hex


# ─────────────── WebSocket hub ───────────────
class AirdropHub:
    def __init__(self):
        self.sockets = set()
        self.uid_of = {}

    def add(self, ws, uid):
        self.sockets.add(ws)
        self.uid_of[ws] = uid

    def remove(self, ws):
        self.sockets.discard(ws)
        self.uid_of.pop(ws, None)

    async def broadcast(self, event, data):
        for ws in list(self.sockets):
            try:
                await ws.send_json({"event": event, "data": data})
            except Exception:
                pass

    async def send_uid(self, uid, event, data):
        for ws in list(self.sockets):
            if self.uid_of.get(ws) == uid:
                try:
                    await ws.send_json({"event": event, "data": data})
                except Exception:
                    pass


hub = AirdropHub()
_engine_task = None
_lock = asyncio.Lock()


def configure(db, add_transaction=None, grant_materials=None, admin_ids=None,
              jwt_secret=None, jwt_algo="HS256", is_staff_fn=None):
    global _db, _add_transaction, _grant_materials, _admin_ids, _jwt_secret, _jwt_algo, _is_staff_fn
    _db = db
    _add_transaction = add_transaction
    _grant_materials = grant_materials
    _admin_ids = set(admin_ids or [])
    _jwt_secret = jwt_secret
    _jwt_algo = jwt_algo or "HS256"
    if is_staff_fn:
        _is_staff_fn = is_staff_fn


async def ensure_indexes():
    await _db.airdrops.create_index("id", unique=True)
    await _db.airdrops.create_index("state")
    await _db.airdrop_history.create_index("claimed_at")


async def get_settings():
    doc = await _db.airdrop_settings.find_one({"_id": "settings"}) or {}
    s = dict(DEFAULT_SETTINGS)
    s.update({k: v for k, v in doc.items() if k != "_id"})
    # loot y rarity_weights: merge superficial por rareza
    s["loot"] = {**DEFAULT_SETTINGS["loot"], **(doc.get("loot") or {})}
    s["rarity_weights"] = {**DEFAULT_SETTINGS["rarity_weights"], **(doc.get("rarity_weights") or {})}
    return s


# ─────────────── Loot ───────────────
def _roll_rarity(weights):
    keys = [r for r in RARITIES if weights.get(r, 0) > 0]
    if not keys:
        return "common"
    return random.choices(keys, weights=[weights[r] for r in keys], k=1)[0]


def _gen_rewards(rarity, settings):
    lt = (settings.get("loot") or {}).get(rarity) or DEFAULT_SETTINGS["loot"][rarity]
    rewards = []
    mat = lt.get("materials") or {}
    if random.randint(1, 100) <= int(mat.get("chance", 0)):
        picks = max(1, int(mat.get("picks", 2)))
        types = random.sample(MATERIAL_TYPES, min(picks, len(MATERIAL_TYPES)))
        for mid in types:
            qty = random.randint(int(mat.get("min", 1)), max(int(mat.get("min", 1)), int(mat.get("max", 1))))
            rewards.append({"type": "material", "key": mid, "name": MATERIAL_NAMES[mid], "qty": qty, "icon": "🦴"})
    pm = lt.get("primemeat") or {}
    if random.randint(1, 100) <= int(pm.get("chance", 0)):
        qty = random.randint(int(pm.get("min", 10000)), max(int(pm.get("min", 10000)), int(pm.get("max", 10000))))
        rewards.append({"type": "primemeat", "key": "primemeat", "name": "PrimeMeat", "qty": max(10000, qty), "icon": "🥩"})
    am = lt.get("amberium") or {}
    if random.randint(1, 100) <= int(am.get("chance", 0)):
        qty = random.randint(int(am.get("min", 50)), max(int(am.get("min", 50)), int(am.get("max", 50))))
        rewards.append({"type": "amberium", "key": "amberium", "name": "Amberium", "qty": max(50, qty), "icon": "💎"})
    for tk, nm, ic in [("growth_token", "Growth Token", "🧬"), ("diet_token", "Diet Token", "🍖"),
                       ("resurrection_token", "Resurrection Token", "🦖")]:
        c = int((lt.get(tk) or {}).get("chance", 0))
        if c > 0 and random.randint(1, 100) <= c:
            rewards.append({"type": "token", "key": tk, "name": nm, "qty": 1, "icon": ic,
                            "special": tk == "resurrection_token"})
    if not rewards:  # nunca vacío
        rewards.append({"type": "material", "key": "bones", "name": "Hueso", "qty": 5, "icon": "🦴"})
    return rewards


async def _deliver(uid, rewards):
    """Entrega real de recompensas a los sistemas existentes."""
    u = await _db.users.find_one({"id": uid}, {"_id": 0, "id": 1})
    if not u:
        return
    for r in rewards:
        try:
            if r["type"] == "primemeat":
                await _db.users.update_one({"id": uid}, {"$inc": {"coins": int(r["qty"])}})
                if _add_transaction:
                    await _add_transaction(uid, "normal", int(r["qty"]), "reward", "Airdrop — PrimeMeat")
            elif r["type"] == "amberium":
                await _db.users.update_one({"id": uid}, {"$inc": {"vip_coins": int(r["qty"])}})
                if _add_transaction:
                    await _add_transaction(uid, "vip", int(r["qty"]), "reward", "Airdrop — Amberium")
            elif r["type"] == "material" and _grant_materials:
                await _grant_materials(uid, r["key"], int(r["qty"]))
            elif r["type"] == "token":
                await _db.inventory.insert_one({
                    "id": _nid(), "user_id": uid, "item_id": f"airdrop_{r['key']}",
                    "name": r["name"], "category": "Tokens",
                    "rarity": "Legendary" if r.get("special") else "Epic",
                    "image": f"/tokens/{r['key']}.png", "token": r["key"],
                    "source": "Airdrop", "quantity": 1, "acquired_at": _iso(),
                })
        except Exception as e:
            logger.warning("[airdrop] deliver %s err: %r", r.get("key"), e)


# ─────────────── Chat global ───────────────
async def _chat(text):
    try:
        await _db.chat_messages.insert_one({
            "id": _nid(), "channel": "global", "user_id": "system",
            "persona_name": "AIRDROP", "avatar": "", "role": "system",
            "system": True, "kind": "airdrop", "text": text, "created_at": _iso(),
        })
    except Exception as e:
        logger.warning("[airdrop] chat err: %r", e)


# ─────────────── Estado / máquina ───────────────
def _public(doc, uid=None):
    if not doc:
        return {"state": "disabled", "server_time": _iso()}
    winner = doc.get("winner")
    out = {
        "id": doc["id"], "state": doc["state"], "rarity": doc.get("rarity"),
        "rarity_label": RARITY_LABEL.get(doc.get("rarity"), ""),
        "server_time": _iso(),
        "drop_at": doc.get("drop_at"), "land_at": doc.get("land_at"),
        "available_at": doc.get("available_at"), "expire_at": doc.get("expire_at"),
        "cooldown_until": doc.get("cooldown_until"), "next_at": doc.get("next_at"),
        "warning_seconds": doc.get("warning_seconds"), "falling_seconds": doc.get("falling_seconds"),
        "winner": {"name": winner.get("name"), "avatar": winner.get("avatar")} if winner else None,
        "claimed_at": doc.get("claimed_at"),
        "contents": "classified",   # el loot NO se revela antes de reclamar
    }
    # El ganador puede ver sus propias recompensas
    if uid and doc.get("winner_uid") == uid:
        out["my_rewards"] = doc.get("rewards")
    return out


async def _current():
    return await _db.airdrops.find_one({"_id": "current"}, {"_id": 0})


async def _schedule_new(settings, rarity=None, manual=False, from_time=None):
    now = from_time or _now()
    warn = int(settings["warning_seconds"])
    fall = int(settings["falling_seconds"])
    avail = int(settings["available_seconds"])
    drop_at = now + timedelta(minutes=int(settings["interval_minutes"])) if not manual else now + timedelta(seconds=8)
    land_at = drop_at + timedelta(seconds=fall)
    doc = {
        "id": _nid(), "state": "waiting",
        "rarity": rarity or _roll_rarity(settings["rarity_weights"]),
        "manual": bool(manual),
        "created_at": _iso(now),
        "drop_at": _iso(drop_at), "land_at": _iso(land_at),
        "available_at": _iso(land_at), "expire_at": _iso(land_at + timedelta(seconds=avail)),
        "next_at": _iso(drop_at),
        "warning_seconds": warn, "falling_seconds": fall,
        "winner": None, "winner_uid": None, "rewards": None, "claimed_at": None, "cooldown_until": None,
    }
    await _db.airdrops.update_one({"_id": "current"}, {"$set": {**doc, "_id": "current"}}, upsert=True)
    await _db.airdrops.update_one({"_id": "current"}, {"$set": {"_id": "current"}})  # noop keep
    await hub.broadcast("airdrop:next", _public(doc))
    return doc


async def _set(fields):
    await _db.airdrops.update_one({"_id": "current"}, {"$set": fields})


def _parse(ts):
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


async def _tick():
    settings = await get_settings()
    if not settings.get("enabled", True):
        cur = await _current()
        if cur and cur.get("state") != "disabled":
            await _set({"state": "disabled"})
            await hub.broadcast("airdrop:disabled", {})
        return
    cur = await _current()
    now = _now()
    if not cur or cur.get("state") == "disabled":
        await _schedule_new(settings)
        return
    st = cur["state"]
    drop_at = _parse(cur["drop_at"]); land_at = _parse(cur["land_at"])
    warn = int(cur.get("warning_seconds", 60))

    if st in ("waiting", "incoming", "falling"):
        if now < drop_at - timedelta(seconds=warn):
            phase = "waiting"
        elif now < drop_at:
            phase = "incoming"
        elif now < land_at:
            phase = "falling"
        else:
            phase = "available"
        if phase != st:
            if phase == "incoming":
                await _set({"state": "incoming"})
                await hub.broadcast("airdrop:incoming", _public({**cur, "state": "incoming"}))
            elif phase == "falling":
                rewards = _gen_rewards(cur["rarity"], settings)   # generado en servidor, oculto
                await _set({"state": "falling", "rewards": rewards})
                await hub.broadcast("airdrop:falling", _public({**cur, "state": "falling"}))
                await _chat("🪂 [AIRDROP] Un suministro está cayendo sobre La Isla Nublar. ¡Prepárate! Solo un jugador podrá reclamarlo.")
            elif phase == "available":
                await _set({"state": "available"})
                await hub.broadcast("airdrop:available", _public({**cur, "state": "available"}))
                await _chat("📦 [AIRDROP] ¡EL SUMINISTRO HA ATERRIZADO! El primero en reclamarlo se queda con todo.")
        return

    if st == "available":
        expire_at = _parse(cur.get("expire_at"))
        if expire_at and now >= expire_at:
            cd = now + timedelta(minutes=int(settings["cooldown_minutes"]))
            await _set({"state": "expired", "cooldown_until": _iso(cd), "next_at": _iso(cd + timedelta(minutes=int(settings["interval_minutes"])))})
            await hub.broadcast("airdrop:expired", {"cooldown_until": _iso(cd)})
            await _history(cur, winner=None, expired=True)
        return

    if st in ("claimed", "expired"):
        cd = _parse(cur.get("cooldown_until"))
        if cd and now >= cd:
            await _schedule_new(settings, from_time=now)
        return


async def _history(cur, winner=None, expired=False):
    try:
        await _db.airdrop_history.insert_one({
            "id": cur["id"], "date": _iso(), "rarity": cur.get("rarity"),
            "winner": (winner or {}).get("name") if winner else None,
            "winner_uid": (winner or {}).get("uid") if winner else None,
            "steam_id": (winner or {}).get("steam_id") if winner else None,
            "rewards": cur.get("rewards") if winner else None,
            "expired": expired,
            "available_at": cur.get("available_at"),
            "claimed_at": cur.get("claimed_at"),
        })
    except Exception as e:
        logger.warning("[airdrop] history err: %r", e)


async def _engine_loop():
    logger.info("[airdrop] motor iniciado")
    while True:
        try:
            async with _lock:
                await _tick()
        except Exception as e:
            logger.warning("[airdrop] tick err: %r", e)
        await asyncio.sleep(1)


def start_engine():
    global _engine_task
    if _engine_task and not _engine_task.done():
        return
    try:
        _engine_task = asyncio.create_task(_engine_loop())
    except Exception as e:
        logger.warning("[airdrop] no se pudo iniciar el motor: %r", e)


# ─────────────── Claim atómico ───────────────
async def claim(user):
    if not user.get("steam_id"):
        raise HTTPException(403, "Debes iniciar sesión con Steam para reclamar el Airdrop.")
    settings = await get_settings()
    if not settings.get("claim_enabled", True):
        raise HTTPException(423, "Los reclamos están deshabilitados temporalmente.")
    uid = user["id"]
    winner = {"uid": uid, "name": user.get("persona_name") or "Superviviente",
              "avatar": user.get("avatar") or "", "steam_id": user.get("steam_id")}
    async with _lock:
        cur = await _current()
        if not cur:
            raise HTTPException(409, "No hay ningún Airdrop activo.")
        # Idempotente: si ya es el ganador, devuelve sus recompensas
        if cur.get("winner_uid") == uid:
            return {"success": True, "winner": True, "rewards": cur.get("rewards"), "rarity": cur.get("rarity")}
        # Operación ATÓMICA: solo gana quien pase el filtro state=available & winner_uid=None
        res = await _db.airdrops.find_one_and_update(
            {"_id": "current", "id": cur["id"], "state": "available", "winner_uid": None},
            {"$set": {"state": "claimed", "winner_uid": uid, "winner": winner, "claimed_at": _iso()}},
            return_document=False)
        if not res:
            cur2 = await _current()
            wname = (cur2.get("winner") or {}).get("name") if cur2 else None
            raise HTTPException(409, f"❌ Demasiado tarde. El Airdrop ya fue reclamado por {wname or 'otro jugador'}.")
        rewards = cur.get("rewards") or _gen_rewards(cur["rarity"], settings)
        if not cur.get("rewards"):
            await _set({"rewards": rewards})
    # Entregar (fuera del lock)
    await _deliver(uid, rewards)
    cd = _now() + timedelta(minutes=int(settings["cooldown_minutes"]))
    await _set({"cooldown_until": _iso(cd), "next_at": _iso(cd + timedelta(minutes=int(settings["interval_minutes"])))})
    claimed = await _current()
    await hub.broadcast("airdrop:claimed", {"winner": winner, "rarity": cur.get("rarity"),
                                            "cooldown_until": _iso(cd)})
    await hub.send_uid(uid, "airdrop:rewards", {"rewards": rewards, "rarity": cur.get("rarity")})
    await _chat(f"🏆 [AIRDROP] {winner['name']} aseguró el suministro. Próximo Airdrop en ~{int(settings['interval_minutes'])} minutos.")
    await _history({**cur, "claimed_at": claimed.get("claimed_at")}, winner=winner)
    return {"success": True, "winner": True, "rewards": rewards, "rarity": cur.get("rarity")}


# ─────────────── Router ───────────────
class SettingsIn(BaseModel):
    settings: dict


class LaunchIn(BaseModel):
    rarity: str = "common"


def build_router(get_current_user, get_admin_user):
    router = APIRouter(prefix="/airdrop", tags=["airdrop"])

    @router.get("/state")
    async def state(user=Depends(get_current_user)):
        cur = await _current()
        return _public(cur, uid=user["id"])

    @router.get("/state/public")
    async def state_public():
        return _public(await _current())

    @router.post("/claim")
    async def claim_route(user=Depends(get_current_user)):
        return await claim(user)

    @router.get("/history")
    async def history(user=Depends(get_current_user), limit: int = 25):
        items = await _db.airdrop_history.find({}, {"_id": 0}).sort("claimed_at", -1).to_list(min(limit, 100))
        return {"history": items}

    @router.get("/settings")
    async def get_admin_settings(admin=Depends(get_admin_user)):
        return await get_settings()

    @router.put("/settings")
    async def put_settings(data: SettingsIn, admin=Depends(get_admin_user)):
        s = data.settings or {}
        await _db.airdrop_settings.update_one({"_id": "settings"}, {"$set": {**s, "_id": "settings"}}, upsert=True)
        return await get_settings()

    @router.post("/launch")
    async def launch(data: LaunchIn, admin=Depends(get_admin_user)):
        rarity = data.rarity if data.rarity in RARITIES else "common"
        settings = await get_settings()
        async with _lock:
            doc = await _schedule_new(settings, rarity=rarity, manual=True)
        return {"success": True, "airdrop": _public(doc)}

    @router.websocket("/ws")
    async def airdrop_ws(ws: WebSocket):
        await ws.accept()
        uid = None
        token = ws.query_params.get("token")
        if token:
            try:
                uid = jwt.decode(token, _jwt_secret, algorithms=[_jwt_algo]).get("sub")
            except Exception:
                uid = None
        try:
            hub.add(ws, uid)
            cur = await _current()
            await ws.send_json({"event": "airdrop:sync", "data": _public(cur, uid=uid)})
            while True:
                m = await ws.receive_json()
                if m.get("event") == "ping":
                    await ws.send_json({"event": "pong", "data": {}})
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("[airdrop] ws: %r", e)
        finally:
            hub.remove(ws)

    return router
