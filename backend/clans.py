"""Sistema de Clanes — La Isla Nublar (Fase 1: Hub de Clan).

Server-authoritative. WebSocket para chat + estado en vivo (sin polling).
Fundar un clan cobra una moneda configurable (Amberium/PrimeMeat) de forma atómica.
Un jugador solo puede pertenecer a UN clan. Permisos por rango; el líder tiene todo.

Colecciones:
  clans          {id,name,tag,color,leader_id,description,notoriety,member_count,
                  ranks:[{id,name,order,perms:{...}}],created_at}
  clan_members   {clan_id,user_id,rank_id,name,avatar,joined_at}  (único user_id)
  clan_invites   {id,clan_id,user_id,invited_by,created_at}
  clan_messages  {id,clan_id,user_id,name,text,created_at}
  clan_settings  {_id:"clans", founding_currency, founding_cost, min_members, creation_enabled}
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("laislanublar.clans")

_db = None
_admin_ids = set()
_jwt_secret = ""
_jwt_algo = "HS256"
_add_log = None

DEFAULT_SETTINGS = {
    "founding_currency": "amberium",   # amberium (vip_coins) | primemeat (coins)
    "founding_cost": 20000,
    "min_members": 20,
    "creation_enabled": True,
}
CURRENCY_FIELD = {"amberium": "vip_coins", "primemeat": "coins"}
CURRENCY_LABEL = {"amberium": "Amberium", "primemeat": "PrimeMeat"}

PERM_KEYS = ["edit_clan", "manage_ranks", "assign_ranks", "invite", "kick", "manage_members"]


def _now(): return datetime.now(timezone.utc)
def _iso(dt): return dt.astimezone(timezone.utc).isoformat()
def _nid(): return uuid.uuid4().hex


def _default_ranks():
    return [
        {"id": "leader", "name": "Líder", "order": 0, "perms": {k: True for k in PERM_KEYS}},
        {"id": "officer", "name": "Oficial", "order": 1, "perms": {"edit_clan": False, "manage_ranks": False, "assign_ranks": True, "invite": True, "kick": True, "manage_members": True}},
        {"id": "member", "name": "Miembro", "order": 2, "perms": {k: False for k in PERM_KEYS}},
    ]


# ─────────────── Hub WebSocket (por usuario) ───────────────
class ClanHub:
    def __init__(self):
        self.conns = set(); self.by_uid = {}; self.uid_of = {}

    def add(self, ws, uid=None):
        self.conns.add(ws)
        if uid:
            self.by_uid.setdefault(uid, set()).add(ws); self.uid_of[ws] = uid

    def remove(self, ws):
        self.conns.discard(ws)
        uid = self.uid_of.pop(ws, None)
        if uid and uid in self.by_uid:
            self.by_uid[uid].discard(ws)
            if not self.by_uid[uid]: self.by_uid.pop(uid, None)

    async def send_to(self, uid, event, data):
        for ws in list(self.by_uid.get(uid, [])):
            try: await ws.send_json({"event": event, "data": data})
            except Exception: self.remove(ws)

    async def send_clan(self, uids, event, data):
        for uid in uids:
            await self.send_to(uid, event, data)

    async def broadcast_all(self, event, data):
        for ws in list(self.conns):
            try: await ws.send_json({"event": event, "data": data})
            except Exception: self.remove(ws)


GLOBAL_ROOM = "__global__"


hub = ClanHub()


def configure(db, *, admin_ids, add_log=None, jwt_secret="", jwt_algo="HS256"):
    global _db, _admin_ids, _add_log, _jwt_secret, _jwt_algo
    _db = db; _admin_ids = set(admin_ids or []); _add_log = add_log
    _jwt_secret = jwt_secret; _jwt_algo = jwt_algo


async def get_settings():
    doc = await _db.clan_settings.find_one({"_id": "clans"}) or {}
    out = dict(DEFAULT_SETTINGS)
    for k in DEFAULT_SETTINGS:
        if doc.get(k) is not None: out[k] = doc[k]
    return out


async def ensure_indexes():
    try:
        await _db.clans.create_index("id", unique=True)
        await _db.clans.create_index("name", unique=True)
        await _db.clans.create_index("tag", unique=True)
        await _db.clan_members.create_index("user_id", unique=True)
        await _db.clan_members.create_index("clan_id")
        await _db.clan_invites.create_index([("clan_id", 1), ("user_id", 1)], unique=True)
        await _db.clan_invites.create_index("user_id")
        await _db.clan_requests.create_index([("clan_id", 1), ("user_id", 1)], unique=True)
        await _db.clan_requests.create_index("user_id")
        await _db.clan_messages.create_index([("clan_id", 1), ("created_at", -1)])
        if await _db.clan_settings.find_one({"_id": "clans"}) is None:
            await _db.clan_settings.insert_one({"_id": "clans", **DEFAULT_SETTINGS})
    except Exception:
        logger.warning("[clans] index init skipped", exc_info=True)


async def _log(actor, action, target=None, meta=None):
    if _add_log:
        try: await _add_log(actor, f"clan_{action}", target, meta or {})
        except Exception: pass


async def _clan_member_ids(clan_id):
    rows = await _db.clan_members.find({"clan_id": clan_id}, {"user_id": 1, "_id": 0}).to_list(1000)
    return [r["user_id"] for r in rows]


def _rank_of(clan, rank_id):
    return next((r for r in clan.get("ranks", []) if r["id"] == rank_id), None)


def _perms_for(clan, uid, rank_id):
    if clan.get("leader_id") == uid:
        return {k: True for k in PERM_KEYS}, True
    r = _rank_of(clan, rank_id) or {}
    return {k: bool((r.get("perms") or {}).get(k)) for k in PERM_KEYS}, False


def _level_info(xp):
    xp = max(0, int(xp or 0)); level = 1; rem = xp
    while True:
        need = level * 1000
        if rem < need: break
        rem -= need; level += 1
    return {"level": level, "xp_into": rem, "xp_needed": level * 1000, "xp_total": xp}


def _acct_level(u):
    return min(99, 1 + int(u.get("coins", 0) or 0) // 50000)


def _player_status(u):
    if u.get("active_dino"): return "En partida"
    last = u.get("last_login")
    try:
        from datetime import datetime as _dt
        dt = _dt.fromisoformat(str(last).replace("Z", "+00:00"))
        if (_now() - dt).total_seconds() < 300: return "En línea"
    except Exception: pass
    return "Ausente"


def _clan_code(clan):
    try: return f"#{int(clan['id'][:8], 16) % 10000:04d}"
    except Exception: return "#0000"


async def _pub_clan(clan, settings=None):
    settings = settings or await get_settings()
    lvl = _level_info(clan.get("notoriety", 0))
    territories = 0
    try: territories = await _db.turf_zones.count_documents({"owner_clan_id": clan["id"]})
    except Exception: pass
    return {
        "id": clan["id"], "name": clan["name"], "tag": clan["tag"], "color": clan.get("color", "#7CA842"),
        "leader_id": clan.get("leader_id"), "description": clan.get("description", ""),
        "notoriety": clan.get("notoriety", 0), "member_count": clan.get("member_count", 0),
        "ranks": sorted(clan.get("ranks", []), key=lambda r: r.get("order", 99)),
        "min_members": settings["min_members"], "active": clan.get("member_count", 0) >= settings["min_members"],
        "created_at": clan.get("created_at"), "code": _clan_code(clan),
        "language": clan.get("language", "Español"), "clan_type": clan.get("clan_type", "PvP / Territorios"),
        "level": lvl["level"], "xp_into": lvl["xp_into"], "xp_needed": lvl["xp_needed"],
        "territories": territories,
    }


async def _members_view(clan):
    clan_id = clan["id"]
    order_map = {r["id"]: r.get("order", 50) for r in clan.get("ranks", [])}
    mems = await _db.clan_members.find({"clan_id": clan_id}, {"_id": 0}).to_list(1000)
    ids = [m["user_id"] for m in mems]
    fresh = {u["id"]: u async for u in _db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1})}
    for m in mems:
        u = fresh.get(m["user_id"], {})
        m["name"] = u.get("persona_name") or m.get("name") or "Superviviente"
        m["avatar"] = u.get("avatar") or m.get("avatar")
        m["online"] = m["user_id"] in hub.by_uid
    return sorted(mems, key=lambda m: (order_map.get(m.get("rank_id"), 50), m["name"].lower()))


async def build_me(user):
    uid = user["id"]; settings = await get_settings()
    mem = await _db.clan_members.find_one({"user_id": uid}, {"_id": 0})
    invites = []
    inv_rows = await _db.clan_invites.find({"user_id": uid}, {"_id": 0}).to_list(50)
    for iv in inv_rows:
        c = await _db.clans.find_one({"id": iv["clan_id"]}, {"_id": 0, "name": 1, "tag": 1, "color": 1, "id": 1})
        if c: invites.append({"clan_id": c["id"], "name": c["name"], "tag": c["tag"], "color": c.get("color")})
    if not mem:
        return {"clan": None, "invites": invites, "config": _pub_config(settings)}
    clan = await _db.clans.find_one({"id": mem["clan_id"]}, {"_id": 0})
    if not clan:
        await _db.clan_members.delete_one({"user_id": uid})
        return {"clan": None, "invites": invites, "config": _pub_config(settings)}
    perms, is_leader = _perms_for(clan, uid, mem.get("rank_id"))
    members = await _members_view(clan)
    online_count = sum(1 for m in members if m.get("online"))
    out = {
        "clan": await _pub_clan(clan, settings), "members": members,
        "my_rank_id": mem.get("rank_id"), "my_perms": perms, "is_leader": is_leader,
        "invites": invites, "config": _pub_config(settings), "online_count": online_count,
    }
    if is_leader or perms.get("invite") or perms.get("manage_members"):
        out["sent_invites"] = await _sent_invites(clan["id"])
        out["join_requests"] = await _join_requests(clan["id"])
    return out


async def _sent_invites(clan_id):
    rows = await _db.clan_invites.find({"clan_id": clan_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    ids = [r["user_id"] for r in rows]
    users = {u["id"]: u async for u in _db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1, "coins": 1})}
    out = []
    for r in rows:
        u = users.get(r["user_id"], {})
        out.append({"user_id": r["user_id"], "name": u.get("persona_name") or "Superviviente", "avatar": u.get("avatar"),
                    "level": _acct_level(u), "created_at": r.get("created_at")})
    return out


async def _join_requests(clan_id):
    rows = await _db.clan_requests.find({"clan_id": clan_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    ids = [r["user_id"] for r in rows]
    users = {u["id"]: u async for u in _db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1, "coins": 1})}
    out = []
    for r in rows:
        u = users.get(r["user_id"], {})
        out.append({"user_id": r["user_id"], "name": u.get("persona_name") or "Superviviente", "avatar": u.get("avatar"),
                    "level": _acct_level(u), "created_at": r.get("created_at")})
    return out


def _pub_config(settings):
    return {"founding_currency": settings["founding_currency"], "founding_currency_label": CURRENCY_LABEL.get(settings["founding_currency"], "Amberium"),
            "founding_cost": settings["founding_cost"], "min_members": settings["min_members"], "creation_enabled": settings["creation_enabled"]}


# ─────────────── Modelos ───────────────
class FoundIn(BaseModel):
    name: str; tag: str; color: str = "#7CA842"; description: str = ""

class EditIn(BaseModel):
    name: str | None = None; tag: str | None = None; color: str | None = None; description: str | None = None
    language: str | None = None; clan_type: str | None = None

class RankIn(BaseModel):
    id: str | None = None; name: str; order: int = 5; perms: dict = {}

class AssignIn(BaseModel):
    user_id: str; rank_id: str

class TargetIn(BaseModel):
    user_id: str

class InviteIn(BaseModel):
    user_id: str | None = None; steam_id: str | None = None; name: str | None = None

class ClanIdIn(BaseModel):
    clan_id: str

class ChatIn(BaseModel):
    text: str
    channel: str = "clan"


# ─────────────── Lógica ───────────────
async def do_found(user, data: FoundIn):
    uid = user["id"]; s = await get_settings()
    if not s["creation_enabled"]:
        raise HTTPException(423, "La creación de clanes está deshabilitada.")
    if await _db.clan_members.find_one({"user_id": uid}):
        raise HTTPException(409, "Ya perteneces a un clan.")
    name = data.name.strip(); tag = data.tag.strip().upper()
    if not (3 <= len(name) <= 28): raise HTTPException(400, "El nombre debe tener entre 3 y 28 caracteres.")
    if not re.fullmatch(r"[A-Z0-9]{4}", tag): raise HTTPException(400, "El tag debe tener exactamente 4 caracteres (A-Z, 0-9).")
    if await _db.clans.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}):
        raise HTTPException(409, "Ese nombre de clan ya existe.")
    if await _db.clans.find_one({"tag": tag}):
        raise HTTPException(409, "Ese tag ya está en uso.")

    field = CURRENCY_FIELD.get(s["founding_currency"], "vip_coins"); cost = int(s["founding_cost"])
    charge = await _db.users.update_one({"id": uid, field: {"$gte": cost}}, {"$inc": {field: -cost}})
    if charge.modified_count == 0:
        raise HTTPException(402, f"Saldo insuficiente. Necesitas {cost:,} {CURRENCY_LABEL.get(s['founding_currency'])}.")

    clan = {"id": _nid(), "name": name, "tag": tag, "color": data.color or "#7CA842",
            "leader_id": uid, "description": data.description.strip()[:280], "notoriety": 0,
            "member_count": 1, "ranks": _default_ranks(), "language": "Español",
            "clan_type": "PvP / Territorios", "created_at": _iso(_now())}
    try:
        await _db.clans.insert_one(dict(clan))
    except Exception:
        await _db.users.update_one({"id": uid}, {"$inc": {field: cost}})  # refund
        raise HTTPException(409, "No se pudo crear el clan (nombre/tag duplicado).")
    await _db.clan_members.insert_one({"clan_id": clan["id"], "user_id": uid, "rank_id": "leader",
                                       "name": user.get("persona_name"), "avatar": user.get("avatar"), "joined_at": _iso(_now())})
    await _db.clan_invites.delete_many({"user_id": uid})
    await _log(user.get("steam_id") or uid, "found", clan["id"], {"name": name, "tag": tag, "cost": cost, "currency": s["founding_currency"]})
    return {"success": True}


async def _require_clan(uid):
    mem = await _db.clan_members.find_one({"user_id": uid}, {"_id": 0})
    if not mem: raise HTTPException(404, "No perteneces a ningún clan.")
    clan = await _db.clans.find_one({"id": mem["clan_id"]}, {"_id": 0})
    if not clan: raise HTTPException(404, "Clan no encontrado.")
    return mem, clan


async def _require_perm(user, perm):
    mem, clan = await _require_clan(user["id"])
    perms, is_leader = _perms_for(clan, user["id"], mem.get("rank_id"))
    if not (is_leader or perms.get(perm)):
        raise HTTPException(403, "No tienes permiso para esta acción.")
    return mem, clan


async def _push_clan_update(clan_id):
    ids = await _clan_member_ids(clan_id)
    await hub.send_clan(ids, "clan:updated", {"clan_id": clan_id})


async def do_edit(user, data: EditIn):
    mem, clan = await _require_perm(user, "edit_clan")
    upd = {}
    if data.color: upd["color"] = data.color
    if data.description is not None: upd["description"] = data.description.strip()[:280]
    if data.language is not None: upd["language"] = data.language.strip()[:24] or "Español"
    if data.clan_type is not None: upd["clan_type"] = data.clan_type.strip()[:32] or "PvP / Territorios"
    if data.name:
        name = data.name.strip()
        if not (3 <= len(name) <= 28): raise HTTPException(400, "Nombre inválido (3-28).")
        if await _db.clans.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "id": {"$ne": clan["id"]}}):
            raise HTTPException(409, "Ese nombre ya existe.")
        upd["name"] = name
    if data.tag:
        tag = data.tag.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{4}", tag): raise HTTPException(400, "El tag debe tener exactamente 4 caracteres (A-Z, 0-9).")
        if await _db.clans.find_one({"tag": tag, "id": {"$ne": clan["id"]}}):
            raise HTTPException(409, "Ese tag ya está en uso.")
        upd["tag"] = tag
    if upd:
        await _db.clans.update_one({"id": clan["id"]}, {"$set": upd})
        await _log(user.get("steam_id") or user["id"], "edit", clan["id"], upd)
        await _push_clan_update(clan["id"])
    return {"success": True}


async def do_save_rank(user, data: RankIn):
    mem, clan = await _require_perm(user, "manage_ranks")
    perms = {k: bool((data.perms or {}).get(k)) for k in PERM_KEYS}
    ranks = clan.get("ranks", [])
    if data.id:
        if data.id == "leader": raise HTTPException(400, "El rango Líder no se puede editar.")
        found = False
        for r in ranks:
            if r["id"] == data.id:
                r["name"] = data.name.strip()[:24]; r["order"] = int(data.order); r["perms"] = perms; found = True
        if not found: raise HTTPException(404, "Rango no encontrado.")
    else:
        rid = re.sub(r"[^a-z0-9]+", "_", data.name.strip().lower())[:20] or _nid()[:8]
        if any(r["id"] == rid for r in ranks): rid = f"{rid}_{_nid()[:4]}"
        ranks.append({"id": rid, "name": data.name.strip()[:24], "order": int(data.order), "perms": perms})
    await _db.clans.update_one({"id": clan["id"]}, {"$set": {"ranks": ranks}})
    await _push_clan_update(clan["id"])
    return {"success": True}


async def do_delete_rank(user, rank_id):
    mem, clan = await _require_perm(user, "manage_ranks")
    if rank_id in ("leader", "member"): raise HTTPException(400, "Ese rango no se puede eliminar.")
    ranks = [r for r in clan.get("ranks", []) if r["id"] != rank_id]
    await _db.clans.update_one({"id": clan["id"]}, {"$set": {"ranks": ranks}})
    await _db.clan_members.update_many({"clan_id": clan["id"], "rank_id": rank_id}, {"$set": {"rank_id": "member"}})
    await _push_clan_update(clan["id"])
    return {"success": True}


async def do_assign(user, data: AssignIn):
    mem, clan = await _require_perm(user, "assign_ranks")
    if data.rank_id == "leader": raise HTTPException(400, "Usa transferir liderazgo para asignar Líder.")
    if not _rank_of(clan, data.rank_id): raise HTTPException(404, "Rango no encontrado.")
    if data.user_id == clan["leader_id"]: raise HTTPException(400, "No puedes cambiar el rango del líder.")
    res = await _db.clan_members.update_one({"clan_id": clan["id"], "user_id": data.user_id}, {"$set": {"rank_id": data.rank_id}})
    if res.matched_count == 0: raise HTTPException(404, "Miembro no encontrado.")
    await _push_clan_update(clan["id"])
    return {"success": True}


async def do_invite(user, data: InviteIn):
    mem, clan = await _require_perm(user, "invite")
    q = None
    if data.user_id: q = {"id": data.user_id}
    elif data.steam_id: q = {"steam_id": data.steam_id}
    elif data.name: q = {"persona_name": {"$regex": f"^{re.escape(data.name.strip())}$", "$options": "i"}}
    if not q: raise HTTPException(400, "Indica jugador.")
    target = await _db.users.find_one(q, {"_id": 0, "id": 1, "persona_name": 1})
    if not target: raise HTTPException(404, "Jugador no encontrado.")
    if await _db.clan_members.find_one({"user_id": target["id"]}): raise HTTPException(409, "Ese jugador ya está en un clan.")
    try:
        await _db.clan_invites.update_one({"clan_id": clan["id"], "user_id": target["id"]},
                                          {"$setOnInsert": {"id": _nid(), "invited_by": user["id"], "created_at": _iso(_now())}}, upsert=True)
    except Exception: pass
    await hub.send_to(target["id"], "clan:invited", {"clan_id": clan["id"], "name": clan["name"], "tag": clan["tag"]})
    await _push_clan_update(clan["id"])
    return {"success": True}


async def do_invite_accept(user, clan_id):
    uid = user["id"]
    if await _db.clan_members.find_one({"user_id": uid}): raise HTTPException(409, "Ya perteneces a un clan.")
    inv = await _db.clan_invites.find_one({"clan_id": clan_id, "user_id": uid})
    if not inv: raise HTTPException(404, "Invitación no encontrada.")
    clan = await _db.clans.find_one({"id": clan_id}, {"_id": 0})
    if not clan: raise HTTPException(404, "Clan no encontrado.")
    await _db.clan_members.insert_one({"clan_id": clan_id, "user_id": uid, "rank_id": "member",
                                       "name": user.get("persona_name"), "avatar": user.get("avatar"), "joined_at": _iso(_now())})
    await _db.clans.update_one({"id": clan_id}, {"$inc": {"member_count": 1}})
    await _db.clan_invites.delete_many({"user_id": uid})
    await _log(user.get("steam_id") or uid, "join", clan_id, {})
    await _push_clan_update(clan_id)
    await _sys_msg(clan_id, f"{user.get('persona_name') or 'Un superviviente'} se unió al clan.")
    return {"success": True}


async def do_invite_decline(user, clan_id):
    await _db.clan_invites.delete_one({"clan_id": clan_id, "user_id": user["id"]})
    return {"success": True}


async def _remove_member(clan, uid):
    await _db.clan_members.delete_one({"clan_id": clan["id"], "user_id": uid})
    await _db.clans.update_one({"id": clan["id"]}, {"$inc": {"member_count": -1}})
    await hub.send_to(uid, "clan:removed", {"clan_id": clan["id"]})
    await _push_clan_update(clan["id"])


async def do_kick(user, data: TargetIn):
    mem, clan = await _require_perm(user, "kick")
    if data.user_id == clan["leader_id"]: raise HTTPException(400, "No puedes expulsar al líder.")
    if data.user_id == user["id"]: raise HTTPException(400, "Usa salir del clan.")
    if not await _db.clan_members.find_one({"clan_id": clan["id"], "user_id": data.user_id}): raise HTTPException(404, "Miembro no encontrado.")
    await _remove_member(clan, data.user_id)
    await _log(user.get("steam_id") or user["id"], "kick", clan["id"], {"target": data.user_id})
    return {"success": True}


async def do_leave(user):
    mem, clan = await _require_clan(user["id"])
    if clan["leader_id"] == user["id"]:
        others = await _db.clan_members.count_documents({"clan_id": clan["id"], "user_id": {"$ne": user["id"]}})
        if others > 0: raise HTTPException(400, "Transfiere el liderazgo antes de salir, o disuelve el clan.")
        return await do_disband(user)
    await _remove_member(clan, user["id"])
    await _sys_msg(clan["id"], f"{user.get('persona_name') or 'Un miembro'} abandonó el clan.")
    return {"success": True}


async def do_transfer(user, data: TargetIn):
    mem, clan = await _require_clan(user["id"])
    if clan["leader_id"] != user["id"]: raise HTTPException(403, "Solo el líder puede transferir el liderazgo.")
    if not await _db.clan_members.find_one({"clan_id": clan["id"], "user_id": data.user_id}): raise HTTPException(404, "Miembro no encontrado.")
    await _db.clans.update_one({"id": clan["id"]}, {"$set": {"leader_id": data.user_id}})
    await _db.clan_members.update_one({"clan_id": clan["id"], "user_id": data.user_id}, {"$set": {"rank_id": "leader"}})
    await _db.clan_members.update_one({"clan_id": clan["id"], "user_id": user["id"]}, {"$set": {"rank_id": "officer"}})
    await _log(user.get("steam_id") or user["id"], "transfer", clan["id"], {"to": data.user_id})
    await _push_clan_update(clan["id"])
    return {"success": True}


async def do_disband(user):
    mem, clan = await _require_clan(user["id"])
    if clan["leader_id"] != user["id"]: raise HTTPException(403, "Solo el líder puede disolver el clan.")
    ids = await _clan_member_ids(clan["id"])
    await _db.clan_members.delete_many({"clan_id": clan["id"]})
    await _db.clan_invites.delete_many({"clan_id": clan["id"]})
    await _db.clans.delete_one({"id": clan["id"]})
    await hub.send_clan(ids, "clan:removed", {"clan_id": clan["id"]})
    await _log(user.get("steam_id") or user["id"], "disband", clan["id"], {})
    return {"success": True}


async def _sys_msg(clan_id, text):
    await _post_message(clan_id, None, "Sistema", text, system=True)


async def _post_message(clan_id, uid, name, text, system=False):
    msg = {"id": _nid(), "clan_id": clan_id, "user_id": uid, "name": name, "text": text,
           "system": system, "created_at": _iso(_now())}
    await _db.clan_messages.insert_one(dict(msg))
    ids = await _clan_member_ids(clan_id)
    await hub.send_clan(ids, "clan:message", {k: msg[k] for k in ("id", "user_id", "name", "text", "system", "created_at")})
    return msg


async def _post_global_message(user, clan, text):
    msg = {"id": _nid(), "clan_id": GLOBAL_ROOM, "user_id": user["id"],
           "name": user.get("persona_name") or "Superviviente", "text": text, "system": False,
           "clan_tag": clan.get("tag"), "clan_color": clan.get("color"), "sender_clan_id": clan.get("id"),
           "created_at": _iso(_now())}
    await _db.clan_messages.insert_one(dict(msg))
    await hub.broadcast_all("clan:global", {k: msg[k] for k in ("id", "user_id", "name", "text", "system", "clan_tag", "clan_color", "sender_clan_id", "created_at")})
    return msg


async def do_chat(user, text, channel="clan"):
    mem, clan = await _require_clan(user["id"])
    text = (text or "").strip()[:500]
    if not text: raise HTTPException(400, "Mensaje vacío.")
    if channel == "global":
        await _post_global_message(user, clan, text)
    else:
        await _post_message(clan["id"], user["id"], user.get("persona_name") or "Superviviente", text)
    return {"success": True}


async def get_chat_history(user, limit=50, channel="clan"):
    mem, clan = await _require_clan(user["id"])
    room = GLOBAL_ROOM if channel == "global" else clan["id"]
    rows = await _db.clan_messages.find({"clan_id": room}, {"_id": 0}).sort("created_at", -1).to_list(min(100, limit))
    return {"messages": list(reversed(rows))}


async def get_directory():
    clans = await _db.clans.find({}, {"_id": 0}).sort("notoriety", -1).to_list(200)
    s = await get_settings()
    return {"clans": [{"id": c["id"], "name": c["name"], "tag": c["tag"], "color": c.get("color"),
                       "member_count": c.get("member_count", 0), "notoriety": c.get("notoriety", 0),
                       "level": _level_info(c.get("notoriety", 0))["level"],
                       "active": c.get("member_count", 0) >= s["min_members"]} for c in clans]}


async def search_players(user, q):
    q = (q or "").strip()
    mem = await _db.clan_members.find_one({"user_id": user["id"]}, {"_id": 0, "clan_id": 1})
    clan_id = mem["clan_id"] if mem else None
    query = {"persona_name": {"$regex": re.escape(q), "$options": "i"}} if q else {}
    rows = await _db.users.find(query, {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1, "coins": 1, "active_dino": 1, "last_login": 1}).limit(40).to_list(40)
    in_clan = {r["user_id"] async for r in _db.clan_members.find({}, {"_id": 0, "user_id": 1})}
    invited = set()
    if clan_id:
        invited = {r["user_id"] async for r in _db.clan_invites.find({"clan_id": clan_id}, {"_id": 0, "user_id": 1})}
    out = []
    for u in rows:
        if u["id"] == user["id"]: continue
        out.append({"id": u["id"], "name": u.get("persona_name") or "Superviviente", "avatar": u.get("avatar"),
                    "level": _acct_level(u), "status": _player_status(u),
                    "in_clan": u["id"] in in_clan, "invited": u["id"] in invited})
    out.sort(key=lambda p: (p["in_clan"], p["invited"], p["name"].lower()))
    return {"players": out[:24]}


async def do_cancel_invite(user, target_id):
    mem, clan = await _require_perm(user, "invite")
    await _db.clan_invites.delete_one({"clan_id": clan["id"], "user_id": target_id})
    await hub.send_to(target_id, "clan:invite_cancelled", {"clan_id": clan["id"]})
    await _push_clan_update(clan["id"])
    return {"success": True}


async def do_request_join(user, clan_id):
    uid = user["id"]
    if await _db.clan_members.find_one({"user_id": uid}): raise HTTPException(409, "Ya perteneces a un clan.")
    clan = await _db.clans.find_one({"id": clan_id}, {"_id": 0, "id": 1})
    if not clan: raise HTTPException(404, "Clan no encontrado.")
    try:
        await _db.clan_requests.update_one({"clan_id": clan_id, "user_id": uid},
            {"$setOnInsert": {"id": _nid(), "name": user.get("persona_name"), "avatar": user.get("avatar"), "created_at": _iso(_now())}}, upsert=True)
    except Exception: pass
    await _push_clan_update(clan_id)
    return {"success": True}


async def do_cancel_request(user, clan_id):
    await _db.clan_requests.delete_one({"clan_id": clan_id, "user_id": user["id"]})
    return {"success": True}


async def do_request_accept(user, target_id):
    mem, clan = await _require_perm(user, "invite")
    req = await _db.clan_requests.find_one({"clan_id": clan["id"], "user_id": target_id})
    if not req: raise HTTPException(404, "Solicitud no encontrada.")
    if await _db.clan_members.find_one({"user_id": target_id}):
        await _db.clan_requests.delete_many({"user_id": target_id})
        raise HTTPException(409, "Ese jugador ya está en un clan.")
    target = await _db.users.find_one({"id": target_id}, {"_id": 0, "persona_name": 1, "avatar": 1})
    await _db.clan_members.insert_one({"clan_id": clan["id"], "user_id": target_id, "rank_id": "member",
        "name": (target or {}).get("persona_name"), "avatar": (target or {}).get("avatar"), "joined_at": _iso(_now())})
    await _db.clans.update_one({"id": clan["id"]}, {"$inc": {"member_count": 1}})
    await _db.clan_requests.delete_many({"user_id": target_id})
    await _db.clan_invites.delete_many({"user_id": target_id})
    await hub.send_to(target_id, "clan:updated", {"clan_id": clan["id"]})
    await _push_clan_update(clan["id"])
    await _sys_msg(clan["id"], f"{(target or {}).get('persona_name') or 'Un superviviente'} se unió al clan.")
    return {"success": True}


async def do_request_decline(user, target_id):
    mem, clan = await _require_perm(user, "invite")
    await _db.clan_requests.delete_one({"clan_id": clan["id"], "user_id": target_id})
    await _push_clan_update(clan["id"])
    return {"success": True}


# ─────────────── Router ───────────────
def build_router(get_current_user, get_admin_user):
    router = APIRouter(prefix="/clans", tags=["clans"])

    @router.get("/me")
    async def me(user=Depends(get_current_user)): return await build_me(user)

    @router.get("/config")
    async def config(user=Depends(get_current_user)): return _pub_config(await get_settings())

    @router.get("/directory")
    async def directory(user=Depends(get_current_user)): return await get_directory()

    @router.post("/found")
    async def found(data: FoundIn, user=Depends(get_current_user)): return await do_found(user, data)

    @router.post("/edit")
    async def edit(data: EditIn, user=Depends(get_current_user)): return await do_edit(user, data)

    @router.post("/ranks")
    async def save_rank(data: RankIn, user=Depends(get_current_user)): return await do_save_rank(user, data)

    @router.delete("/ranks/{rank_id}")
    async def del_rank(rank_id: str, user=Depends(get_current_user)): return await do_delete_rank(user, rank_id)

    @router.post("/assign")
    async def assign(data: AssignIn, user=Depends(get_current_user)): return await do_assign(user, data)

    @router.post("/invite")
    async def invite(data: InviteIn, user=Depends(get_current_user)): return await do_invite(user, data)

    @router.get("/players/search")
    async def players_search(q: str = "", user=Depends(get_current_user)): return await search_players(user, q)

    @router.post("/invite/cancel")
    async def invite_cancel(data: TargetIn, user=Depends(get_current_user)): return await do_cancel_invite(user, data.user_id)

    @router.post("/request")
    async def request_join(data: ClanIdIn, user=Depends(get_current_user)): return await do_request_join(user, data.clan_id)

    @router.post("/request/cancel")
    async def request_cancel(data: ClanIdIn, user=Depends(get_current_user)): return await do_cancel_request(user, data.clan_id)

    @router.post("/request/accept")
    async def request_accept(data: TargetIn, user=Depends(get_current_user)): return await do_request_accept(user, data.user_id)

    @router.post("/request/decline")
    async def request_decline(data: TargetIn, user=Depends(get_current_user)): return await do_request_decline(user, data.user_id)

    @router.post("/invite/accept")
    async def inv_accept(data: ClanIdIn, user=Depends(get_current_user)): return await do_invite_accept(user, data.clan_id)

    @router.post("/invite/decline")
    async def inv_decline(data: ClanIdIn, user=Depends(get_current_user)): return await do_invite_decline(user, data.clan_id)

    @router.post("/kick")
    async def kick(data: TargetIn, user=Depends(get_current_user)): return await do_kick(user, data)

    @router.post("/transfer")
    async def transfer(data: TargetIn, user=Depends(get_current_user)): return await do_transfer(user, data)

    @router.post("/leave")
    async def leave(user=Depends(get_current_user)): return await do_leave(user)

    @router.post("/disband")
    async def disband(user=Depends(get_current_user)): return await do_disband(user)

    @router.get("/chat")
    async def chat_history(limit: int = 50, channel: str = "clan", user=Depends(get_current_user)): return await get_chat_history(user, limit, channel)

    @router.post("/chat")
    async def chat_send(data: ChatIn, user=Depends(get_current_user)): return await do_chat(user, data.text, data.channel or "clan")

    @router.websocket("/ws")
    async def clan_ws(ws: WebSocket):
        await ws.accept()
        uid = None; token = ws.query_params.get("token")
        if token:
            try: uid = jwt.decode(token, _jwt_secret, algorithms=[_jwt_algo]).get("sub")
            except Exception: uid = None
        if uid and not await _db.users.find_one({"id": uid}, {"_id": 1}): uid = None
        try:
            hub.add(ws, uid)
            await ws.send_json({"event": "clan:hello", "data": {"ok": True}})
            while True:
                m = await ws.receive_text()
                if m == "ping": await ws.send_text("pong")
        except WebSocketDisconnect: pass
        except Exception as e: logger.warning("[clans] ws: %r", e)
        finally: hub.remove(ws)

    # ─── Admin ───
    @router.get("/admin/settings")
    async def admin_settings(user=Depends(get_admin_user)): return await get_settings()

    @router.put("/admin/settings")
    async def admin_save_settings(data: dict, user=Depends(get_admin_user)):
        upd = {}
        if data.get("founding_currency") in CURRENCY_FIELD: upd["founding_currency"] = data["founding_currency"]
        if data.get("founding_cost") is not None: upd["founding_cost"] = max(0, int(data["founding_cost"]))
        if data.get("min_members") is not None: upd["min_members"] = max(1, int(data["min_members"]))
        if data.get("creation_enabled") is not None: upd["creation_enabled"] = bool(data["creation_enabled"])
        await _db.clan_settings.update_one({"_id": "clans"}, {"$set": upd}, upsert=True)
        await _log(user.get("steam_id") or user["id"], "admin_settings", "clans", upd)
        await hub.send_clan(list(hub.by_uid.keys()), "clan:config", _pub_config(await get_settings()))
        return {"success": True, "settings": await get_settings()}

    @router.get("/admin/list")
    async def admin_list(user=Depends(get_admin_user)):
        return await get_directory()

    @router.post("/admin/delete")
    async def admin_delete(data: ClanIdIn, user=Depends(get_admin_user)):
        clan = await _db.clans.find_one({"id": data.clan_id}, {"_id": 0})
        if not clan: raise HTTPException(404, "Clan no encontrado.")
        ids = await _clan_member_ids(data.clan_id)
        await _db.clan_members.delete_many({"clan_id": data.clan_id})
        await _db.clan_invites.delete_many({"clan_id": data.clan_id})
        await _db.clans.delete_one({"id": data.clan_id})
        await hub.send_clan(ids, "clan:removed", {"clan_id": data.clan_id})
        await _log(user.get("steam_id") or user["id"], "admin_delete", data.clan_id, {"name": clan.get("name")})
        return {"success": True}

    return router
