"""Sistema Global de Bounties (☠️) — server-side, seguro, automático y en vivo.

Self-contained como skin_shop.py / live_trade.py: server.py inyecta el handle de
Mongo, las dependencias de auth, el proveedor de jugadores online (RCON + log del
juego) y los callbacks de recompensa vía configure(...).

Modelo en una línea:
  - El backend elige ALEATORIAMENTE a un jugador ONLINE, VIVO, con SteamID válido,
    con >= minimum_online_time conectado, que no sea el bounty anterior ni de los
    últimos N, y que no sea administrador. Ese jugador queda WANTED.
  - El primer jugador que lo ELIMINE (kill PVP validado por el servidor, killer !=
    target, bounty ACTIVO y no procesado) recibe la recompensa. La entrega es
    ATÓMICA e IDEMPOTENTE (nunca doble cobro).
  - Suicidio, muerte ambiental, admin-kill, desconexión o eventos duplicados NO
    pagan. Si el objetivo se desconecta, el bounty se SUSPENDE 5 min; si vuelve,
    continúa; si no, se cancela sin recompensa y se elige uno nuevo.
  - Tras completarse, cooldown de next_bounty_delay y nuevo bounty automático.
  - Todo el estado se empuja por WebSocket (sin polling). Discord recibe embeds.

Colecciones: bounties, bounty_state (singleton), bounty_dodge_log.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from datetime import datetime, timezone, timedelta

import httpx
import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("bounty")

DARK_RED = 0x8B0000

# ── Config por defecto (tuneable en runtime desde el panel admin, guardado en
# settings/bounty). Estructura pensada para cambiar cantidades sin tocar código.
DEFAULT_CONFIG = {
    "prime_meat": 60000,
    "experience": 2500,
    "amberium": 500,
    "next_bounty_delay": 20 * 60,     # cooldown tras completar (segundos)
    "minimum_online_time": 15 * 60,   # tiempo mínimo conectado para ser elegible
    "recent_target_protection": 3,    # no repetir en los últimos N bounties
    "disconnect_grace": 5 * 60,       # suspensión por desconexión (segundos)
    "empty_retry": 30,                # reintento de selección si no hay elegibles
}

# Inyectado por server.py
_db = None
_admin_ids: set = set()
_online_provider = None            # async () -> list[{sid,name,species,slug}] | None
_award_reward = None               # async (user_id, prime, amber, xp, bounty_id) -> None
_resolve_user_id = None            # async (sid) -> user_id | None
_ingame_grant = None               # (sid, prime, amber, xp) -> None   (best effort)
_jwt_secret = ""
_jwt_algo = "HS256"

# Tiempo de primera vista por SteamID (para exigir minimum_online_time). El módulo
# lleva su propio reloj de conexión — funciona igual con el juego real o en sim.
_seen_since: dict = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _now().isoformat()


def _ts_ms() -> int:
    return int(time.time() * 1000)


def _bid() -> str:
    return "BNT-" + str(random.randint(10000, 99999))


def _fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


# ─────────────────────────── Hub WebSocket (público) ───────────────────────────
class BountyHub:
    def __init__(self):
        self.conns: set = set()

    async def add(self, ws):
        self.conns.add(ws)

    def remove(self, ws):
        self.conns.discard(ws)

    async def broadcast(self, event: str, data: dict):
        payload = {"event": event, "data": data}
        dead = []
        for ws in list(self.conns):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.conns.discard(ws)


hub = BountyHub()
_loop_lock = asyncio.Lock()


# ─────────────────────────── Config / estado ───────────────────────────
async def get_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        doc = await _db.settings.find_one({"_id": "bounty"}, {"_id": 0})
        if doc:
            for k in DEFAULT_CONFIG:
                if doc.get(k) is not None:
                    cfg[k] = int(doc[k])
    except Exception:
        pass
    return cfg


async def _get_state() -> dict:
    st = await _db.bounty_state.find_one({"_id": "state"})
    if not st:
        st = {"_id": "state", "phase": "waiting", "current_bounty_id": None,
              "next_at": _iso(), "paused": False, "recent_targets": [],
              "updated_at": _iso()}
        await _db.bounty_state.insert_one(dict(st))
    return st


async def _set_state(**fields):
    fields["updated_at"] = _iso()
    await _db.bounty_state.update_one({"_id": "state"}, {"$set": fields}, upsert=True)


def _public_bounty(b: dict, cfg: dict, next_at: str | None = None) -> dict:
    return {
        "bountyId": b.get("id"),
        "status": b.get("status"),
        "targetId": b.get("target_sid"),
        "targetName": b.get("target_name"),
        "dinosaur": b.get("target_species"),
        "slug": b.get("target_slug"),
        "killerId": b.get("killer_sid"),
        "killerName": b.get("killer_name"),
        "rewards": {
            "primeMeat": b.get("rewards", {}).get("prime_meat", cfg["prime_meat"]),
            "experience": b.get("rewards", {}).get("experience", cfg["experience"]),
            "amberium": b.get("rewards", {}).get("amberium", cfg["amberium"]),
        },
        "startedAt": b.get("started_at_ms"),
        "completedAt": b.get("completed_at_ms"),
        "suspendUntil": b.get("suspend_until_ms"),
        "nextAt": next_at,
        "rewardProcessed": b.get("reward_processed", False),
        "rewardDelivered": b.get("reward_delivered", False),
    }


async def snapshot() -> dict:
    """Estado completo para un cliente que acaba de conectar (o el REST /current)."""
    cfg = await get_config()
    st = await _get_state()
    b = None
    if st.get("current_bounty_id"):
        b = await _db.bounties.find_one({"id": st["current_bounty_id"]}, {"_id": 0})
    if b:
        return {"phase": st["phase"], "paused": st.get("paused", False),
                "bounty": _public_bounty(b, cfg, st.get("next_at")), "config": cfg}
    return {"phase": st["phase"], "paused": st.get("paused", False),
            "bounty": None, "nextAt": st.get("next_at"), "config": cfg}


# ─────────────────────────── Roster / elegibilidad ───────────────────────────
async def _observe_roster() -> list:
    """Lista de jugadores online (real o simulada). Actualiza el reloj de conexión."""
    roster = None
    if _online_provider:
        try:
            roster = await _online_provider()
        except Exception as e:
            logger.warning("[bounty] online provider failed: %r", e)
            roster = None
    if roster is None:
        roster = _sim_roster()
        sim = True
    else:
        sim = False
    now = time.time()
    seen_now = set()
    for p in roster:
        sid = str(p.get("sid") or "").strip()
        if not sid:
            continue
        seen_now.add(sid)
        if sid not in _seen_since:
            # Los jugadores simulados nacen con antigüedad para poder probar el flujo
            # sin esperar 15 min reales; los reales empiezan su reloj ahora.
            _seen_since[sid] = now - (25 * 60 if sim else 0)
    # Limpia relojes de quienes ya no están (para que reconectar reinicie el reloj).
    for sid in list(_seen_since.keys()):
        if sid not in seen_now:
            _seen_since.pop(sid, None)
    return roster


def _eligible(roster: list, cfg: dict, recent: list) -> list:
    now = time.time()
    out = []
    for p in roster:
        sid = str(p.get("sid") or "").strip()
        if not sid or not sid.isdigit() or len(sid) < 17:
            continue                                   # SteamID válido
        if not p.get("alive", True):
            continue                                   # vivo
        if sid in _admin_ids:
            continue                                   # no admins
        if sid in recent:
            continue                                   # ni el anterior ni últimos N
        since = _seen_since.get(sid)
        if since is None or (now - since) < cfg["minimum_online_time"]:
            continue                                   # tiempo mínimo conectado
        out.append(p)
    return out


# ─────────────────────────── Discord ───────────────────────────
_http = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0),
                          limits=httpx.Limits(max_connections=10, max_keepalive_connections=5))


async def _discord(embed: dict, max_retries: int = 2) -> None:
    url = os.environ.get("DISCORD_BOUNTY_WEBHOOK_URL", "").strip()
    if not url:
        return
    payload = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    for attempt in range(max_retries + 1):
        try:
            r = await _http.post(url, json=payload)
            if 200 <= r.status_code < 300:
                return
            if r.status_code == 429 and attempt < max_retries:
                try:
                    ra = float(r.json().get("retry_after", 1.0))
                except Exception:
                    ra = 1.0
                await asyncio.sleep(min(ra + random.uniform(0, 0.25), 30.0))
                continue
            if r.status_code in {500, 502, 503, 504} and attempt < max_retries:
                await asyncio.sleep(min((2 ** attempt) + random.random(), 10.0))
                continue
            logger.error("[bounty] discord HTTP %s", r.status_code)
            return
        except Exception:
            logger.warning("[bounty] discord send failed", exc_info=False)
            return


def _discord_new_embed(b: dict) -> dict:
    r = b["rewards"]
    return {
        "title": "☠️ NUEVO BOUNTY DETECTADO",
        "color": DARK_RED,
        "description": ("La cacería ha comenzado.\n\n"
                        "☠️ El jugador que elimine al objetivo recibirá "
                        "automáticamente la recompensa."),
        "fields": [
            {"name": "🎯 OBJETIVO", "value": b.get("target_name") or "—", "inline": True},
            {"name": "🦖 DINOSAURIO", "value": b.get("target_species") or "—", "inline": True},
            {"name": "💰 RECOMPENSA",
             "value": (f"🥩 {_fmt(r['prime_meat'])} Prime Meat\n"
                       f"✨ {_fmt(r['experience'])} EXP\n"
                       f"🟠 {_fmt(r['amberium'])} Amberiums"),
             "inline": False},
        ],
        "footer": {"text": f"BOUNTY ID • {b['id']}"},
        "timestamp": _iso(),
    }


def _discord_done_embed(b: dict) -> dict:
    r = b["rewards"]
    return {
        "title": "💀 BOUNTY COMPLETADO",
        "color": DARK_RED,
        "description": "☠️ La cacería ha terminado.\n\nNuevo objetivo en 20 minutos.",
        "fields": [
            {"name": "🎯 OBJETIVO ELIMINADO", "value": b.get("target_name") or "—", "inline": True},
            {"name": "⚔️ CAZADOR", "value": b.get("killer_name") or "—", "inline": True},
            {"name": "💰 RECOMPENSA ENTREGADA",
             "value": (f"🥩 {_fmt(r['prime_meat'])} Prime Meat\n"
                       f"✨ {_fmt(r['experience'])} EXP\n"
                       f"🟠 {_fmt(r['amberium'])} Amberiums"),
             "inline": False},
        ],
        "footer": {"text": f"BOUNTY ID • {b['id']}"},
        "timestamp": _iso(),
    }


# ─────────────────────────── Motor ───────────────────────────
async def _select_target(cfg: dict, st: dict) -> dict | None:
    roster = await _observe_roster()
    recent = st.get("recent_targets", [])
    elig = _eligible(roster, cfg, recent)
    if not elig:
        next_at = (_now() + timedelta(seconds=cfg["empty_retry"])).isoformat()
        await _set_state(phase="waiting", current_bounty_id=None, next_at=next_at)
        await hub.broadcast("bounty:waiting", {"reason": "no_eligible_players",
                                               "nextAt": next_at})
        return None
    pick = random.choice(elig)
    now_ms = _ts_ms()
    b = {
        "id": _bid(),
        "status": "active",
        "target_sid": str(pick["sid"]),
        "target_name": pick.get("name") or "Jugador",
        "target_species": pick.get("species") or "Dinosaurio",
        "target_slug": pick.get("slug"),
        "target_user_id": await _resolve_user_id(str(pick["sid"])) if _resolve_user_id else None,
        "killer_sid": None, "killer_name": None, "killer_user_id": None,
        "rewards": {"prime_meat": cfg["prime_meat"], "experience": cfg["experience"],
                    "amberium": cfg["amberium"]},
        "started_at": _iso(), "started_at_ms": now_ms,
        "completed_at": None, "completed_at_ms": None,
        "suspended_at": None, "suspend_until_ms": None,
        "reward_processed": False, "reward_delivered": False,
        "created_at": _iso(),
    }
    await _db.bounties.insert_one(dict(b))
    new_recent = ([b["target_sid"]] + recent)[: max(1, cfg["recent_target_protection"])]
    await _set_state(phase="active", current_bounty_id=b["id"], next_at=None,
                     recent_targets=new_recent)
    global _sim_next_kill
    _sim_next_kill = time.time() + random.uniform(90, 150)  # ventana visible en sim
    pub = _public_bounty(b, cfg)
    await hub.broadcast("bounty:new", pub)
    await hub.broadcast("bounty:active", pub)
    asyncio.create_task(_discord(_discord_new_embed(b)))
    logger.info("[bounty] NEW %s target=%s (%s)", b["id"], b["target_name"], b["target_sid"])
    return b


async def _cancel(b: dict, reason: str, cfg: dict, dodge: bool = False):
    await _db.bounties.update_one(
        {"id": b["id"], "status": {"$in": ["active", "suspended"]}},
        {"$set": {"status": "cancelled", "cancelled_at": _iso(),
                  "cancel_reason": reason}})
    if dodge:
        try:
            await _db.bounty_dodge_log.insert_one({
                "id": _bid(), "bounty_id": b["id"], "target_sid": b["target_sid"],
                "target_name": b["target_name"], "at": _iso()})
        except Exception:
            pass
    await _set_state(phase="waiting", current_bounty_id=None, next_at=_iso())
    await hub.broadcast("bounty:cancelled", {"bountyId": b["id"], "reason": reason,
                                             "targetName": b["target_name"]})


async def _tick():
    """Un paso del ciclo. Serializado con _loop_lock."""
    async with _loop_lock:
        cfg = await get_config()
        st = await _get_state()
        if st.get("paused"):
            return
        await _observe_roster()
        bid = st.get("current_bounty_id")
        b = await _db.bounties.find_one({"id": bid}, {"_id": 0}) if bid else None

        if b and b["status"] == "active":
            online = b["target_sid"] in _seen_since
            if not online:
                until_ms = _ts_ms() + cfg["disconnect_grace"] * 1000
                await _db.bounties.update_one(
                    {"id": b["id"], "status": "active"},
                    {"$set": {"status": "suspended", "suspended_at": _iso(),
                              "suspend_until_ms": until_ms}})
                await hub.broadcast("bounty:target_disconnected", {
                    "bountyId": b["id"], "targetName": b["target_name"],
                    "suspendUntil": until_ms})
                logger.info("[bounty] %s target disconnected -> suspended", b["id"])
            return

        if b and b["status"] == "suspended":
            online = b["target_sid"] in _seen_since
            if online:
                await _db.bounties.update_one(
                    {"id": b["id"], "status": "suspended"},
                    {"$set": {"status": "active", "suspend_until_ms": None}})
                await hub.broadcast("bounty:target_returned", {
                    "bountyId": b["id"], "targetName": b["target_name"]})
                logger.info("[bounty] %s target returned -> active", b["id"])
            elif _ts_ms() >= (b.get("suspend_until_ms") or 0):
                await _cancel(b, "target_disconnect_timeout", cfg, dodge=True)
                logger.info("[bounty] %s cancelled (dodge)", b["id"])
            return

        # Sin bounty vivo: esperar cooldown y seleccionar.
        if st["phase"] == "waiting":
            next_at = st.get("next_at")
            if next_at:
                try:
                    due = datetime.fromisoformat(next_at)
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                    if _now() < due:
                        return
                except Exception:
                    pass
            await _select_target(cfg, st)
        else:
            await _set_state(phase="waiting", current_bounty_id=None, next_at=_iso())


async def on_kill(killer_sid: str, victim_sid: str, killer_name: str | None = None):
    """Hook desde el drenaje de kills PVP del servidor. Solo llega aquí una muerte
    PVP validada por el log del juego (nunca suicidio/natural/admin). La compleción
    y la entrega de recompensa son ATÓMICAS e IDEMPOTENTES."""
    killer_sid = str(killer_sid or "").strip()
    victim_sid = str(victim_sid or "").strip()
    if not killer_sid or not victim_sid or killer_sid == victim_sid:
        return
    await _complete(victim_sid, killer_sid, killer_name)


async def _complete(victim_sid: str, killer_sid: str, killer_name: str | None) -> bool:
    cfg = await get_config()
    st = await _get_state()
    bid = st.get("current_bounty_id")
    if not bid:
        return False
    # Match atómico: solo si ESTE bounty está activo, es el objetivo, y NO fue
    # procesado. reward_processed pasa a True en el MISMO update -> nadie más puede
    # entrar (idempotencia contra eventos duplicados / concurrencia).
    res = await _db.bounties.update_one(
        {"id": bid, "status": "active", "target_sid": victim_sid,
         "reward_processed": False},
        {"$set": {"status": "completed", "reward_processed": True,
                  "killer_sid": killer_sid, "killer_name": killer_name,
                  "completed_at": _iso(), "completed_at_ms": _ts_ms()}})
    if res.modified_count != 1:
        return False
    b = await _db.bounties.find_one({"id": bid}, {"_id": 0})
    if killer_name is None:
        killer_name = b.get("killer_name")
    # Resolver killer -> usuario web y entregar recompensa (idempotente por el match).
    killer_uid = await _resolve_user_id(killer_sid) if _resolve_user_id else None
    r = b["rewards"]
    delivered = False
    if killer_uid and _award_reward:
        try:
            await _award_reward(killer_uid, r["prime_meat"], r["amberium"],
                                r["experience"], b["id"])
            delivered = True
        except Exception as e:
            logger.warning("[bounty] award failed: %r", e)
    # Intento in-game (best effort; se ignora si el mod está offline).
    if _ingame_grant:
        try:
            _ingame_grant(killer_sid, r["prime_meat"], r["amberium"], r["experience"])
        except Exception:
            pass
    await _db.bounties.update_one({"id": b["id"]},
                                  {"$set": {"killer_user_id": killer_uid,
                                            "reward_delivered": delivered}})
    next_at = (_now() + timedelta(seconds=cfg["next_bounty_delay"])).isoformat()
    await _set_state(phase="waiting", current_bounty_id=None, next_at=next_at)
    b["killer_user_id"] = killer_uid
    b["reward_delivered"] = delivered
    pub = _public_bounty(b, cfg, next_at)
    await hub.broadcast("bounty:completed", pub)
    asyncio.create_task(_discord(_discord_done_embed(b)))
    logger.info("[bounty] COMPLETED %s killer=%s delivered=%s", b["id"], killer_sid, delivered)
    return True


# ─────────────────────────── Simulación (preview) ───────────────────────────
_SIM_DINOS = [
    ("Tyrannosaurus", "trex"), ("Spinosaurus", "spino"), ("Allosaurus", "allo"),
    ("Carnotaurus", "carno"), ("Austroraptor", "austro"), ("Ceratosaurus", "cerato"),
    ("Deinosuchus", "deino"), ("Triceratops", "trike"), ("Dilophosaurus", "dilo"),
    ("Herrerasaurus", "herrera"),
]
_SIM_NAMES = ["YonduSkywalker", "Bluecito", "RaptorKing", "DonDino", "ElCarnicero",
              "LaBestia", "NubladoMX", "TorvoLATAM", "AlfaMacho", "ReinaRex",
              "CazadorNocturno", "GarraVeloz"]
_sim_players: list = []
_sim_next_kill = 0.0


def _sim_roster() -> list:
    global _sim_players, _sim_next_kill
    if not _sim_players:
        rng = random.Random(4207)
        picks = rng.sample(range(len(_SIM_NAMES)), 9)
        for i, idx in enumerate(picks):
            dino, slug = _SIM_DINOS[i % len(_SIM_DINOS)]
            _sim_players.append({
                "sid": str(76561190000000000 + idx * 1337 + 11),
                "name": _SIM_NAMES[idx], "species": dino, "slug": slug, "alive": True})
        _sim_next_kill = time.time() + random.uniform(35, 70)
    return [dict(p) for p in _sim_players]


async def _sim_autokill_loop():
    """Solo en modo simulación: completa el bounty activo tras un rato para que el
    flujo completo (nuevo -> activo -> completado -> espera) se vea en el preview."""
    global _sim_next_kill
    while True:
        await asyncio.sleep(6)
        try:
            if _online_provider:
                real = await _online_provider()
                if real is not None:
                    continue  # juego real conectado -> no auto-kill
            st = await _get_state()
            if st.get("paused") or not st.get("current_bounty_id"):
                continue
            b = await _db.bounties.find_one({"id": st["current_bounty_id"]}, {"_id": 0})
            if not b or b["status"] != "active":
                continue
            if time.time() < _sim_next_kill:
                continue
            roster = _sim_roster()
            killers = [p for p in roster if str(p["sid"]) != b["target_sid"]]
            if not killers:
                continue
            k = random.choice(killers)
            _sim_next_kill = time.time() + random.uniform(40, 75)
            await _complete(b["target_sid"], str(k["sid"]), k["name"])
        except Exception as e:
            logger.warning("[bounty] sim autokill: %r", e)


async def _main_loop():
    while True:
        try:
            await _tick()
        except Exception as e:
            logger.warning("[bounty] tick: %r", e)
        await asyncio.sleep(6)


# ─────────────────────────── Wiring ───────────────────────────
def configure(db, *, admin_ids, online_provider, award_reward, resolve_user_id,
              ingame_grant=None, jwt_secret="", jwt_algo="HS256"):
    global _db, _admin_ids, _online_provider, _award_reward, _resolve_user_id
    global _ingame_grant, _jwt_secret, _jwt_algo
    _db = db
    _admin_ids = set(admin_ids or [])
    _online_provider = online_provider
    _award_reward = award_reward
    _resolve_user_id = resolve_user_id
    _ingame_grant = ingame_grant
    _jwt_secret = jwt_secret
    _jwt_algo = jwt_algo


async def ensure_indexes():
    try:
        await _db.bounties.create_index("id", unique=True)
        await _db.bounties.create_index([("status", 1)])
        await _db.bounties.create_index([("created_at", -1)])
        await _db.bounty_dodge_log.create_index([("at", -1)])
        await _get_state()
    except Exception:
        logger.warning("[bounty] index init skipped", exc_info=True)


def start_loops():
    asyncio.create_task(_main_loop())
    asyncio.create_task(_sim_autokill_loop())


class ConfigIn(BaseModel):
    prime_meat: int | None = None
    experience: int | None = None
    amberium: int | None = None
    next_bounty_delay: int | None = None
    minimum_online_time: int | None = None
    recent_target_protection: int | None = None
    disconnect_grace: int | None = None


class SimKillIn(BaseModel):
    killer_sid: str | None = None


def build_router(get_current_user, get_admin_user):
    router = APIRouter()

    @router.get("/bounty/current")
    async def current():
        return await snapshot()

    @router.get("/bounty/config")
    async def config():
        return await get_config()

    @router.get("/bounty/history")
    async def history(limit: int = 15):
        limit = max(1, min(50, int(limit)))
        rows = await _db.bounties.find(
            {"status": {"$in": ["completed", "cancelled"]}}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        cfg = await get_config()
        return {"items": [_public_bounty(r, cfg) for r in rows]}

    # ── Admin ──
    @router.post("/bounty/admin/force-new")
    async def force_new(admin=Depends(get_admin_user)):
        async with _loop_lock:
            cfg = await get_config()
            st = await _get_state()
            bid = st.get("current_bounty_id")
            if bid:
                b = await _db.bounties.find_one({"id": bid}, {"_id": 0})
                if b and b["status"] in ("active", "suspended"):
                    await _cancel(b, "admin_force_new", cfg)
                    st = await _get_state()
            b = await _select_target(cfg, st)
        return {"ok": True, "bounty": _public_bounty(b, cfg) if b else None}

    @router.post("/bounty/admin/pause")
    async def pause(admin=Depends(get_admin_user)):
        await _set_state(paused=True)
        await hub.broadcast("bounty:paused", {"paused": True})
        return {"ok": True, "paused": True}

    @router.post("/bounty/admin/resume")
    async def resume(admin=Depends(get_admin_user)):
        await _set_state(paused=False, phase="waiting", next_at=_iso())
        await hub.broadcast("bounty:paused", {"paused": False})
        return {"ok": True, "paused": False}

    @router.post("/bounty/admin/cancel")
    async def cancel(admin=Depends(get_admin_user)):
        cfg = await get_config()
        st = await _get_state()
        bid = st.get("current_bounty_id")
        if not bid:
            return {"ok": True, "cancelled": False}
        b = await _db.bounties.find_one({"id": bid}, {"_id": 0})
        if b and b["status"] in ("active", "suspended"):
            await _cancel(b, "admin_cancel", cfg)
            return {"ok": True, "cancelled": True}
        return {"ok": True, "cancelled": False}

    @router.post("/bounty/admin/config")
    async def set_config(data: ConfigIn, admin=Depends(get_admin_user)):
        upd = {k: int(v) for k, v in data.dict().items() if v is not None and int(v) >= 0}
        if upd:
            await _db.settings.update_one({"_id": "bounty"}, {"$set": upd}, upsert=True)
        cfg = await get_config()
        await hub.broadcast("bounty:config", cfg)
        return {"ok": True, "config": cfg}

    @router.post("/bounty/admin/simulate-kill")
    async def simulate_kill(data: SimKillIn, admin=Depends(get_admin_user)):
        """Completa el bounty activo simulando una muerte válida (para probar el
        flujo end-to-end sin el servidor de juego real)."""
        st = await _get_state()
        bid = st.get("current_bounty_id")
        if not bid:
            return {"ok": False, "detail": "No hay bounty activo"}
        b = await _db.bounties.find_one({"id": bid}, {"_id": 0})
        if not b or b["status"] != "active":
            return {"ok": False, "detail": "El bounty no está activo"}
        killer_sid = (data.killer_sid or "").strip()
        killer_name = None
        if not killer_sid:
            roster = await _observe_roster()
            cand = [p for p in roster if str(p["sid"]) != b["target_sid"]]
            if cand:
                pick = random.choice(cand)
                killer_sid, killer_name = str(pick["sid"]), pick.get("name")
            else:
                killer_sid = str(int(b["target_sid"]) + 1)
                killer_name = "Cazador"
        ok = await _complete(b["target_sid"], killer_sid, killer_name)
        return {"ok": ok}

    # ── WebSocket público (sin polling) ──
    @router.websocket("/bounty/ws")
    async def bounty_ws(ws: WebSocket):
        await ws.accept()
        try:
            await hub.add(ws)
            snap = await snapshot()
            await ws.send_json({"event": "bounty:state", "data": snap})
            while True:
                msg = await ws.receive_text()
                if msg == "ping":
                    await ws.send_text("pong")
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("[bounty] ws: %r", e)
        finally:
            hub.remove(ws)

    return router
