"""Turf Wars — Fase 2 del Sistema de Clanes (guerra de territorios).

Server-authoritative. Los clanes luchan por ZONAS del mapa. Capturar una zona
requiere tener MÁS miembros presentes que el resto y SOSTENERLA durante
`capture_seconds`. Al capturar: la zona cambia de dueño (se colorea con el color
del clan), el clan gana notoriedad y se anuncia EN EL CHAT DEL CLAN (tanto al
que captura como al que pierde).

En preview NO hay servidor de juego (RCON/mod), así que la PRESENCIA de miembros
por zona se SIMULA de forma estable por ventanas de tiempo, creando batallas
vivas entre clanes. Cuando el mod exponga presencia real, `presence_provider`
la devuelve y la simulación se apaga automáticamente. Los jugadores pueden
ordenar a su clan HACER UN "RALLY" a una zona para reforzar su presencia allí.

Colecciones:
  turf_zones     {id,name,x,y,owner_clan_id,owner_since,contest_clan_id,contest_progress,updated_at}
  turf_settings  {_id:"turf", capture_seconds, min_presence, tick_seconds, deploy_window,
                  rally_seconds, rally_push, notoriety_capture, notoriety_hold, sim_enabled}
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("laislanublar.turfwars")

_db = None
_admin_ids = set()
_jwt_secret = ""
_jwt_algo = "HS256"
_announce = None          # async (clan_id, text)
_notify_clan = None       # async (clan_id)  -> refresca el hub del clan
_presence_provider = None  # async () -> {zone_id:{clan_id:count}} | None

# Rally en memoria: clan_id -> {zone_id, until(ts)}
_rally = {}

DEFAULT_SETTINGS = {
    "capture_seconds": 30,     # segundos sosteniendo para capturar
    "min_presence": 1,         # miembros presentes mínimos para disputar
    "tick_seconds": 5,         # cadencia del loop
    "deploy_window": 60,       # ventana estable de despliegue simulado
    "rally_seconds": 120,      # duración de un rally
    "rally_push": 10,          # presencia que aporta un rally (domina)
    "notoriety_capture": 50,   # notoriedad al capturar
    "notoriety_hold": 2,       # notoriedad por zona sostenida (cada ~60s)
    "sim_enabled": True,
}

# Territorios en disputa (coordenadas en % alineadas con InteractiveMap).
ZONES = [
    {"id": "north_plains", "name": "North Plains", "x": 55, "y": 33},
    {"id": "highland", "name": "Highland", "x": 49, "y": 46},
    {"id": "forks_plains", "name": "Forks Plains", "x": 63, "y": 49},
    {"id": "the_pit", "name": "The Pit", "x": 45, "y": 58},
    {"id": "jungle_i", "name": "Jungle I Sector", "x": 59, "y": 62},
    {"id": "delta", "name": "Delta", "x": 82, "y": 62},
    {"id": "east_coast", "name": "East Coast", "x": 90, "y": 55},
    {"id": "swamps", "name": "Swamps", "x": 62, "y": 76},
    {"id": "south_plains", "name": "South Plains", "x": 42, "y": 74},
    {"id": "west_coast", "name": "West Coast", "x": 15, "y": 52},
]

# Clanes rivales de IA para dar vida al mapa en preview (idempotentes por tag).
RIVAL_CLANS = [
    {"tag": "ALBA", "name": "Raptores del Alba", "color": "#38bdf8", "member_count": 22},
    {"tag": "OBSD", "name": "Colosos de Obsidiana", "color": "#a855f7", "member_count": 19},
    {"tag": "CNBR", "name": "Manada Cinabrio", "color": "#e11d48", "member_count": 24},
]


def _now(): return datetime.now(timezone.utc)
def _iso(dt): return dt.astimezone(timezone.utc).isoformat()


def configure(db, *, admin_ids, announce=None, notify_clan=None, presence_provider=None,
              jwt_secret="", jwt_algo="HS256"):
    global _db, _admin_ids, _announce, _notify_clan, _presence_provider, _jwt_secret, _jwt_algo
    _db = db
    _admin_ids = set(admin_ids or [])
    _announce = announce
    _notify_clan = notify_clan
    _presence_provider = presence_provider
    _jwt_secret = jwt_secret
    _jwt_algo = jwt_algo


async def get_settings():
    doc = await _db.turf_settings.find_one({"_id": "turf"}) or {}
    out = dict(DEFAULT_SETTINGS)
    for k in DEFAULT_SETTINGS:
        if doc.get(k) is not None:
            out[k] = doc[k]
    return out


# ─────────────── WebSocket hub (broadcast a todos) ───────────────
class TurfHub:
    def __init__(self):
        self.conns = set()

    def add(self, ws): self.conns.add(ws)
    def remove(self, ws): self.conns.discard(ws)

    async def broadcast(self, event, data):
        for ws in list(self.conns):
            try:
                await ws.send_json({"event": event, "data": data})
            except Exception:
                self.remove(ws)


hub = TurfHub()


# ─────────────── Seed / índices ───────────────
async def ensure_seed():
    try:
        await _db.turf_zones.create_index("id", unique=True)
        if await _db.turf_settings.find_one({"_id": "turf"}) is None:
            await _db.turf_settings.insert_one({"_id": "turf", **DEFAULT_SETTINGS})
        for z in ZONES:
            existing = await _db.turf_zones.find_one({"id": z["id"]}, {"_id": 0, "id": 1})
            if not existing:
                await _db.turf_zones.insert_one({
                    **z, "owner_clan_id": None, "owner_since": None,
                    "contest_clan_id": None, "contest_progress": 0, "updated_at": _iso(_now())})
        await _ensure_rivals()
    except Exception:
        logger.warning("[turf] seed skipped", exc_info=True)


async def _ensure_rivals():
    """Clanes de IA para el preview (no tienen miembros reales; solo luchan)."""
    import uuid
    default_ranks = [
        {"id": "leader", "name": "Líder", "order": 0, "perms": {}},
        {"id": "member", "name": "Miembro", "order": 2, "perms": {}},
    ]
    for r in RIVAL_CLANS:
        if await _db.clans.find_one({"tag": r["tag"]}, {"_id": 1}):
            continue
        try:
            await _db.clans.insert_one({
                "id": uuid.uuid4().hex, "name": r["name"], "tag": r["tag"], "color": r["color"],
                "leader_id": None, "description": "Clan rival (IA) de las Turf Wars.",
                "notoriety": 0, "member_count": r["member_count"], "ranks": default_ranks,
                "simulated": True, "created_at": _iso(_now())})
        except Exception:
            pass  # tag/nombre duplicado: ya existe


# ─────────────── Presencia (real o simulada) ───────────────
async def _compute_presence(zone_ids, s):
    if _presence_provider:
        try:
            real = await _presence_provider()
            if real is not None:
                return real
        except Exception:
            logger.warning("[turf] presence provider failed; usando simulación", exc_info=True)
    # Simulación estable por ventanas.
    clans = await _db.clans.find({}, {"_id": 0, "id": 1, "member_count": 1, "leader_id": 1}).to_list(300)
    now = time.time()
    window = int(now // max(15, s["deploy_window"]))
    out = {}
    for c in clans:
        cid = c["id"]
        # Los clanes de jugadores (con líder) NO participan de la simulación pasiva:
        # solo entran a disputar zonas cuando hacen rally. Así su chat no se inunda de
        # capturas automáticas. Los clanes IA (sin líder) siguen peleando entre sí.
        if c.get("leader_id"):
            continue
        mc = max(1, int(c.get("member_count", 1)))
        rng = random.Random(f"{cid}:{window}")
        k = rng.randint(1, min(3, len(zone_ids)))
        for zid in rng.sample(zone_ids, k):
            push = rng.randint(1, max(1, min(mc, 8)))
            out.setdefault(zid, {})[cid] = out.get(zid, {}).get(cid, 0) + push
    # Rally activo: cualquier clan (incluidos los de jugadores) puede disputar.
    for cid, rr in _rally.items():
        if rr and rr["until"] > now:
            zid = rr["zone_id"]
            cur = out.setdefault(zid, {}).get(cid, 0)
            out[zid][cid] = max(cur, int(s["rally_push"]))
    return out


# ─────────────── Loop del motor ───────────────
_tick_count = 0


async def _tick():
    global _tick_count
    s = await get_settings()
    if not s.get("sim_enabled") and not _presence_provider:
        return
    zones = await _db.turf_zones.find({}, {"_id": 0}).to_list(100)
    if not zones:
        return
    zone_ids = [z["id"] for z in zones]
    presence = await _compute_presence(zone_ids, s)
    now = _now()
    changed = False
    captures = []  # (zone, new_owner_id, prev_owner_id)
    _tick_count += 1
    income = _tick_count % max(1, int(60 // max(1, s["tick_seconds"]))) == 0

    for z in zones:
        pres = presence.get(z["id"], {})
        owner = z.get("owner_clan_id")
        ranked = sorted(pres.items(), key=lambda kv: kv[1], reverse=True)
        owner_ct = pres.get(owner, 0) if owner else 0
        challenger = next(((cid, ct) for cid, ct in ranked
                           if cid != owner and ct >= s["min_presence"]), None)

        if challenger and not (owner and owner_ct >= challenger[1]):
            cid, _ct = challenger
            prog = (z.get("contest_progress", 0) + s["tick_seconds"]
                    if z.get("contest_clan_id") == cid else s["tick_seconds"])
            if prog >= s["capture_seconds"]:
                captures.append((z, cid, owner))
                z["owner_clan_id"] = cid
                z["owner_since"] = _iso(now)
                z["contest_clan_id"] = None
                z["contest_progress"] = 0
            else:
                z["contest_clan_id"] = cid
                z["contest_progress"] = prog
            changed = True
        elif z.get("contest_progress"):
            z["contest_progress"] = max(0, z["contest_progress"] - s["tick_seconds"])
            if z["contest_progress"] == 0:
                z["contest_clan_id"] = None
            changed = True

        await _db.turf_zones.update_one({"id": z["id"]}, {"$set": {
            "owner_clan_id": z.get("owner_clan_id"), "owner_since": z.get("owner_since"),
            "contest_clan_id": z.get("contest_clan_id"),
            "contest_progress": z.get("contest_progress", 0), "updated_at": _iso(now)}})

    for z, new_owner, prev_owner in captures:
        await _apply_capture(z, new_owner, prev_owner, s)

    # Renta de territorio: notoriedad por zona sostenida (~cada 60s).
    if income and s.get("notoriety_hold"):
        held = {}
        for z in zones:
            oc = z.get("owner_clan_id")
            if oc:
                held[oc] = held.get(oc, 0) + 1
        for cid, n in held.items():
            await _db.clans.update_one({"id": cid}, {"$inc": {"notoriety": int(s["notoriety_hold"]) * n}})
            if _notify_clan:
                try: await _notify_clan(cid)
                except Exception: pass
        if held:
            changed = True

    if changed:
        await _broadcast_state(s)


async def _apply_capture(zone, new_owner, prev_owner, s):
    noto = int(s.get("notoriety_capture", 50))
    await _db.clans.update_one({"id": new_owner}, {"$inc": {"notoriety": noto}})
    new_clan = await _db.clans.find_one({"id": new_owner}, {"_id": 0, "name": 1, "tag": 1})
    prev_clan = await _db.clans.find_one({"id": prev_owner}, {"_id": 0, "name": 1, "tag": 1}) if prev_owner else None
    zn = zone["name"]
    if _announce:
        try:
            await _announce(new_owner, f"⚔️ ¡Capturamos {zn}! El territorio ahora es nuestro (+{noto} notoriedad).")
            if prev_owner and prev_clan:
                await _announce(prev_owner, f"🏴 Perdimos {zn} ante [{(new_clan or {}).get('tag','?')}] {(new_clan or {}).get('name','otro clan')}.")
        except Exception:
            logger.warning("[turf] announce failed", exc_info=True)
    if _notify_clan:
        for cid in (new_owner, prev_owner):
            if cid:
                try: await _notify_clan(cid)
                except Exception: pass
    await hub.broadcast("turf:captured", {
        "zone_id": zone["id"], "zone_name": zn,
        "owner": {"id": new_owner, "name": (new_clan or {}).get("name"), "tag": (new_clan or {}).get("tag")},
        "prev": ({"id": prev_owner, "tag": (prev_clan or {}).get("tag")} if prev_clan else None)})
    logger.info("[turf] %s capturada por %s (antes %s)", zn, new_owner, prev_owner)


async def _loop():
    while True:
        try:
            s = await get_settings()
            await _tick()
            await asyncio.sleep(max(2, int(s["tick_seconds"])))
        except Exception:
            logger.warning("[turf] tick failed", exc_info=True)
            await asyncio.sleep(5)


def start_loops():
    asyncio.create_task(_boot())


async def _boot():
    await ensure_seed()
    asyncio.create_task(_loop())


# ─────────────── Estado público ───────────────
async def _clans_map():
    rows = await _db.clans.find({}, {"_id": 0, "id": 1, "name": 1, "tag": 1, "color": 1, "notoriety": 1}).to_list(300)
    return {c["id"]: c for c in rows}


def _pub_zone(z, cmap, s):
    owner = cmap.get(z.get("owner_clan_id"))
    ch = cmap.get(z.get("contest_clan_id"))
    cap = max(1, int(s["capture_seconds"]))
    return {
        "id": z["id"], "name": z["name"], "x": z["x"], "y": z["y"],
        "owner": ({"id": owner["id"], "name": owner["name"], "tag": owner["tag"], "color": owner.get("color")} if owner else None),
        "owner_since": z.get("owner_since"),
        "contest": ({"id": ch["id"], "tag": ch["tag"], "color": ch.get("color"),
                     "progress": min(100, round(z.get("contest_progress", 0) / cap * 100))} if ch else None),
    }


async def build_state(user=None):
    s = await get_settings()
    cmap = await _clans_map()
    zones = await _db.turf_zones.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    pub = [_pub_zone(z, cmap, s) for z in zones]
    # Leaderboard: zonas controladas + notoriedad.
    held = {}
    for z in zones:
        oc = z.get("owner_clan_id")
        if oc:
            held[oc] = held.get(oc, 0) + 1
    board = []
    for cid, c in cmap.items():
        if held.get(cid) or c.get("notoriety"):
            board.append({"id": cid, "name": c["name"], "tag": c["tag"], "color": c.get("color"),
                          "zones": held.get(cid, 0), "notoriety": c.get("notoriety", 0)})
    board.sort(key=lambda b: (b["zones"], b["notoriety"]), reverse=True)

    my_clan_id = None
    my_rally = None
    if user:
        mem = await _db.clan_members.find_one({"user_id": user["id"]}, {"_id": 0, "clan_id": 1})
        if mem:
            my_clan_id = mem["clan_id"]
            rr = _rally.get(my_clan_id)
            if rr and rr["until"] > time.time():
                my_rally = {"zone_id": rr["zone_id"], "seconds_left": int(rr["until"] - time.time())}
    return {"zones": pub, "leaderboard": board[:12], "config": {
        "capture_seconds": s["capture_seconds"], "rally_seconds": s["rally_seconds"],
        "min_presence": s["min_presence"]},
        "my_clan_id": my_clan_id, "my_rally": my_rally}


async def _broadcast_state(s=None):
    await hub.broadcast("turf:state", await build_state())


# ─────────────── Acciones ───────────────
async def do_rally(user, zone_id):
    mem = await _db.clan_members.find_one({"user_id": user["id"]}, {"_id": 0, "clan_id": 1})
    if not mem:
        raise HTTPException(404, "No perteneces a ningún clan.")
    z = await _db.turf_zones.find_one({"id": zone_id}, {"_id": 0, "name": 1})
    if not z:
        raise HTTPException(404, "Zona no encontrada.")
    cid = mem["clan_id"]
    s = await get_settings()
    now = time.time()
    cur = _rally.get(cid)
    if cur and cur["until"] > now:
        raise HTTPException(429, f"Tu clan ya tiene un rally activo ({int(cur['until'] - now)}s restantes).")
    _rally[cid] = {"zone_id": zone_id, "until": now + int(s["rally_seconds"])}
    if _announce:
        try:
            await _announce(cid, f"📣 ¡Rally a {z['name']}! Todos a reforzar la zona durante {int(s['rally_seconds'])}s.")
        except Exception:
            pass
    return {"success": True, "seconds": int(s["rally_seconds"])}


# ─────────────── Router ───────────────
def build_router(get_current_user, get_admin_user):
    router = APIRouter(prefix="/turf", tags=["turf"])

    @router.get("/state")
    async def state(user=Depends(get_current_user)):
        return await build_state(user)

    @router.get("/config")
    async def config(user=Depends(get_current_user)):
        s = await get_settings()
        return {k: s[k] for k in ("capture_seconds", "rally_seconds", "min_presence", "sim_enabled")}

    @router.post("/rally")
    async def rally(data: dict, user=Depends(get_current_user)):
        return await do_rally(user, str(data.get("zone_id") or ""))

    @router.websocket("/ws")
    async def turf_ws(ws: WebSocket):
        await ws.accept()
        try:
            hub.add(ws)
            await ws.send_json({"event": "turf:state", "data": await build_state()})
            while True:
                m = await ws.receive_text()
                if m == "ping":
                    await ws.send_text("pong")
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("[turf] ws: %r", e)
        finally:
            hub.remove(ws)

    # ─── Admin ───
    @router.get("/admin/settings")
    async def admin_settings(user=Depends(get_admin_user)):
        return await get_settings()

    @router.put("/admin/settings")
    async def admin_save(data: dict, user=Depends(get_admin_user)):
        upd = {}
        for k in ("capture_seconds", "min_presence", "tick_seconds", "deploy_window",
                  "rally_seconds", "rally_push", "notoriety_capture", "notoriety_hold"):
            if data.get(k) is not None:
                upd[k] = max(0, int(data[k]))
        if data.get("sim_enabled") is not None:
            upd["sim_enabled"] = bool(data["sim_enabled"])
        await _db.turf_settings.update_one({"_id": "turf"}, {"$set": upd}, upsert=True)
        await _broadcast_state()
        return {"success": True, "settings": await get_settings()}

    @router.post("/admin/capture")
    async def admin_capture(data: dict, user=Depends(get_admin_user)):
        zid = str(data.get("zone_id") or "")
        cid = str(data.get("clan_id") or "")
        z = await _db.turf_zones.find_one({"id": zid}, {"_id": 0})
        if not z:
            raise HTTPException(404, "Zona no encontrada.")
        if not await _db.clans.find_one({"id": cid}, {"_id": 1}):
            raise HTTPException(404, "Clan no encontrado.")
        s = await get_settings()
        prev = z.get("owner_clan_id")
        z["name"] = z.get("name")
        await _db.turf_zones.update_one({"id": zid}, {"$set": {
            "owner_clan_id": cid, "owner_since": _iso(_now()),
            "contest_clan_id": None, "contest_progress": 0, "updated_at": _iso(_now())}})
        await _apply_capture(z, cid, prev, s)
        await _broadcast_state()
        return {"success": True}

    @router.post("/admin/reset")
    async def admin_reset(user=Depends(get_admin_user)):
        await _db.turf_zones.update_many({}, {"$set": {
            "owner_clan_id": None, "owner_since": None,
            "contest_clan_id": None, "contest_progress": 0, "updated_at": _iso(_now())}})
        _rally.clear()
        await _broadcast_state()
        return {"success": True}

    return router
