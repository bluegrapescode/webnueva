"""Sistema de Tickets/Soporte en tiempo real — La Isla Nublar.
Reutiliza auth (get_current_user/get_admin_user), roles (staff_rank), WebSockets (patrón hub)
y Discord (bot REST) del proyecto. Web -> Discord (aviso). Discord -> Web queda para Fase 2.
"""
from __future__ import annotations
import logging, os, time, uuid, random, re, asyncio
from datetime import datetime, timezone
from typing import Optional
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("tickets")

_db = None
_admin_ids = set()
_add_log = None
_jwt_secret = None
_jwt_algo = "HS256"
_is_staff_fn = lambda u: (u.get("role") == "admin") or (u.get("staff_rank") in {"owner", "admin", "mod", "helper"})

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
TICKETS_CHANNEL_ID = os.environ.get("TICKETS_DISCORD_CHANNEL_ID", "").strip()
PUBLIC_URL = os.environ.get("PUBLIC_APP_URL", "").strip()

STATUSES = ["open", "in_process", "waiting_user", "resolved", "closed"]
PRIORITIES = ["normal", "media", "alta", "urgente"]
_create_cooldown = {}  # user_id -> ts

DEFAULT_SERVERS = [
    {"id": "srv1", "name": "La Isla Nublar #1 — PvP"},
    {"id": "srv2", "name": "La Isla Nublar #2 — PvE"},
    {"id": "srv3", "name": "La Isla Nublar #3 — Small Tribes"},
]

# Campos por categoría (schema para formularios dinámicos, editable desde Admin)
DEFAULT_CATEGORIES = [
    {"id": "general", "emoji": "💬", "name": "Pregunta General",
     "desc": "Dudas sobre servidor, sistemas, reglas o funcionamiento.",
     "fields": [
         {"key": "subject", "label": "Asunto", "type": "text", "required": True},
         {"key": "description", "label": "Descripción detallada", "type": "textarea", "required": True},
     ]},
    {"id": "report_staff", "emoji": "🛡️", "name": "Reportar a un Staff",
     "desc": "Reportar el comportamiento o acciones de un miembro del staff.",
     "fields": [
         {"key": "steam_id", "label": "SteamID", "type": "text", "required": True},
         {"key": "server", "label": "Servidor", "type": "server", "required": True},
         {"key": "incident_date", "label": "Fecha del incidente", "type": "date", "required": True},
         {"key": "incident_time", "label": "Hora aproximada", "type": "time", "required": True},
         {"key": "reported_staff", "label": "Staff reportado", "type": "text", "required": True},
         {"key": "subject", "label": "Asunto", "type": "text", "required": True},
         {"key": "description", "label": "Descripción detallada", "type": "textarea", "required": True},
         {"key": "evidence", "label": "Evidencias (enlaces)", "type": "evidence", "required": False},
     ]},
    {"id": "report_player", "emoji": "🚨", "name": "Reportar a un Jugador",
     "desc": "Reglas, exploits, toxicidad, acoso, combat logging, abuso de sistemas.",
     "fields": [
         {"key": "steam_id", "label": "Tu SteamID", "type": "text", "required": True},
         {"key": "server", "label": "Servidor", "type": "server", "required": True},
         {"key": "incident_date", "label": "Fecha del incidente", "type": "date", "required": True},
         {"key": "incident_time", "label": "Hora aproximada", "type": "time", "required": True},
         {"key": "reported_player", "label": "Jugador reportado", "type": "text", "required": True},
         {"key": "reason", "label": "Motivo", "type": "select", "required": True,
          "options": ["Incumplimiento de reglas", "Exploits", "Toxicidad", "Acoso", "Combat logging", "Abuso de sistemas", "Otro"]},
         {"key": "subject", "label": "Asunto", "type": "text", "required": True},
         {"key": "description", "label": "Descripción detallada", "type": "textarea", "required": True},
         {"key": "evidence", "label": "Evidencias (clips/vídeos/screenshots/links)", "type": "evidence", "required": True},
     ]},
    {"id": "appeal", "emoji": "⚖️", "name": "Apelar un Ban / Strike",
     "desc": "Revisión de ban temporal, permanente, strike u otra sanción.",
     "fields": [
         {"key": "steam_id", "label": "SteamID", "type": "text", "required": True},
         {"key": "sanction_type", "label": "Tipo de sanción", "type": "select", "required": True,
          "options": ["Ban temporal", "Ban permanente", "Strike", "Otra"]},
         {"key": "incident_date", "label": "Fecha de la sanción", "type": "date", "required": True},
         {"key": "reason_shown", "label": "Motivo mostrado", "type": "text", "required": True},
         {"key": "staff_involved", "label": "Staff que aplicó la sanción (si lo conoce)", "type": "text", "required": False},
         {"key": "description", "label": "Explica por qué solicitas la apelación", "type": "textarea", "required": True},
         {"key": "evidence", "label": "Evidencias (enlaces)", "type": "evidence", "required": False},
     ]},
    {"id": "membership", "emoji": "💎", "name": "Membresías",
     "desc": "Preguntas o problemas relacionados con membresías.",
     "fields": [
         {"key": "steam_id", "label": "SteamID", "type": "text", "required": True},
         {"key": "subject", "label": "Asunto", "type": "text", "required": True},
         {"key": "description", "label": "Descripción detallada", "type": "textarea", "required": True},
     ]},
    {"id": "patreon", "emoji": "❤️", "name": "Patreon",
     "desc": "Beneficios, vinculación, roles, renovaciones.",
     "fields": [
         {"key": "steam_id", "label": "SteamID", "type": "text", "required": True},
         {"key": "discord_user", "label": "Usuario de Discord", "type": "text", "required": True},
         {"key": "issue", "label": "Problema", "type": "select", "required": True,
          "options": ["Beneficios faltantes", "Problema de vinculación", "Renovación", "Roles", "Otro"]},
         {"key": "description", "label": "Descripción detallada", "type": "textarea", "required": True},
         {"key": "evidence", "label": "Evidencia / recibo (enlace)", "type": "evidence", "required": False},
     ]},
    {"id": "battlepass", "emoji": "🎫", "name": "Battle Pass",
     "desc": "Recompensas, progreso, desbloqueos, compras, tokens.",
     "fields": [
         {"key": "steam_id", "label": "SteamID", "type": "text", "required": True},
         {"key": "issue", "label": "Problema", "type": "select", "required": True,
          "options": ["Recompensas faltantes", "Progreso", "Desbloqueos", "Compras", "Tokens/recompensas", "Pregunta general"]},
         {"key": "description", "label": "Descripción detallada", "type": "textarea", "required": True},
         {"key": "evidence", "label": "Evidencia (enlace)", "type": "evidence", "required": False},
     ]},
]


def _now(): return datetime.now(timezone.utc)
def _iso(dt=None): return (dt or _now()).astimezone(timezone.utc).isoformat()
def _nid(): return uuid.uuid4().hex
def _clean(s): return re.sub(r"[\x00-\x1f\x7f]", "", str(s or "")).strip()


# ─────────────── Hub WebSocket ───────────────
class TicketHub:
    def __init__(self):
        self.by_uid = {}       # uid -> set(ws)
        self.uid_of = {}       # ws -> uid
        self.staff = set()     # uids que son staff
        self.viewing = {}      # ticket_id -> {uid: name}

    def add(self, ws, uid, staff=False):
        self.uid_of[ws] = uid
        if uid:
            self.by_uid.setdefault(uid, set()).add(ws)
            if staff: self.staff.add(uid)

    def remove(self, ws):
        uid = self.uid_of.pop(ws, None)
        if uid and uid in self.by_uid:
            self.by_uid[uid].discard(ws)
            if not self.by_uid[uid]:
                self.by_uid.pop(uid, None)
                self.staff.discard(uid)

    async def send(self, uid, event, data):
        for ws in list(self.by_uid.get(uid, [])):
            try: await ws.send_json({"event": event, "data": data})
            except Exception: pass

    async def send_many(self, uids, event, data):
        for uid in set(uids or []):
            await self.send(uid, event, data)

    async def send_staff(self, event, data):
        await self.send_many(list(self.staff), event, data)


hub = TicketHub()


def configure(db, admin_ids=None, add_log=None, jwt_secret=None, jwt_algo="HS256", is_staff_fn=None):
    global _db, _admin_ids, _add_log, _jwt_secret, _jwt_algo, _is_staff_fn
    _db = db
    _admin_ids = set(admin_ids or [])
    _add_log = add_log
    _jwt_secret = jwt_secret
    _jwt_algo = jwt_algo or "HS256"
    if is_staff_fn: _is_staff_fn = is_staff_fn


async def ensure_indexes():
    await _db.tickets.create_index("id", unique=True)
    await _db.tickets.create_index("code", unique=True)
    await _db.tickets.create_index("user_id")
    await _db.tickets.create_index("steam_id")
    await _db.tickets.create_index("status")
    await _db.tickets.create_index("assigned_to")
    await _db.ticket_messages.create_index("ticket_id")
    await _db.ticket_events.create_index("ticket_id")


async def _log_event(ticket_id, actor, text):
    await _db.ticket_events.insert_one({"ticket_id": ticket_id, "at": _iso(), "actor": actor, "text": text})


async def get_config():
    doc = await _db.ticket_config.find_one({"_id": "config"}) or {}
    return {
        "servers": doc.get("servers") or DEFAULT_SERVERS,
        "categories": doc.get("categories") or DEFAULT_CATEGORIES,
    }


async def _gen_code():
    for _ in range(6):
        code = f"#NBL-{random.randint(10000, 99999)}"
        if not await _db.tickets.find_one({"code": code}, {"_id": 1}):
            return code
    return f"#NBL-{int(time.time()) % 100000}"


def _pub_ticket(t, is_staff=False):
    d = {k: t.get(k) for k in ("id", "code", "user_id", "user_name", "user_avatar", "steam_id",
                               "discord_id", "category", "subject", "description", "server", "server_name",
                               "incident_date", "incident_time", "priority", "status", "assigned_to",
                               "assigned_name", "fields", "created_at", "updated_at", "last_activity", "unread")}
    d["fields"] = t.get("fields") or {}
    return d


async def _discord_notify_new(t):
    if not (DISCORD_BOT_TOKEN and TICKETS_CHANNEL_ID):
        return
    cats = {c["id"]: c for c in (await get_config())["categories"]}
    cat = cats.get(t["category"], {})
    fields = t.get("fields") or {}
    ev = fields.get("evidence") or ""
    link = f"{PUBLIC_URL}/soporte?t={t['id']}" if PUBLIC_URL else "Abrir en la web"
    embed = {
        "title": f"NUEVO TICKET — {t['code']}",
        "color": 0x22C55E,
        "fields": [
            {"name": "Categoría", "value": f"{cat.get('emoji','')} {cat.get('name', t['category'])}", "inline": True},
            {"name": "Usuario", "value": t.get("user_name", "?"), "inline": True},
            {"name": "Prioridad", "value": t.get("priority", "normal").capitalize(), "inline": True},
            {"name": "SteamID", "value": t.get("steam_id") or "—", "inline": True},
            {"name": "Servidor", "value": t.get("server_name") or "—", "inline": True},
            {"name": "Fecha/Hora", "value": f"{t.get('incident_date') or '—'} {t.get('incident_time') or ''}", "inline": True},
            {"name": "Descripción", "value": (t.get("description") or "—")[:1000], "inline": False},
        ],
        "footer": {"text": "La Isla Nublar · Soporte"},
    }
    if ev:
        embed["fields"].append({"name": "Evidencias", "value": ev[:1000], "inline": False})
    content = f"🎫 **{t['code']}** · [Abrir Ticket en la Web]({link})"
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            await c.post(f"https://discord.com/api/v10/channels/{TICKETS_CHANNEL_ID}/messages",
                         headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
                         json={"content": content, "embeds": [embed]})
    except Exception as e:
        logger.warning("[tickets] discord notify: %r", e)


async def _discord_relay_message(t, author, text):
    if not (DISCORD_BOT_TOKEN and TICKETS_CHANNEL_ID):
        return
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            await c.post(f"https://discord.com/api/v10/channels/{TICKETS_CHANNEL_ID}/messages",
                         headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
                         json={"content": f"**{t['code']}** · {author}: {text[:1500]}"})
    except Exception:
        pass


def _can_view(t, user):
    if _is_staff_fn(user):
        # El staff reportado no puede ver su propio reporte
        if t.get("category") == "report_staff" and t.get("reported_staff_id") == user["id"]:
            return False
        return True
    return t.get("user_id") == user["id"]


def _can_manage(t, user):
    if not _is_staff_fn(user):
        return False
    if t.get("category") == "report_staff" and t.get("reported_staff_id") == user["id"]:
        return False
    return True


async def create_ticket(user, data):
    now = time.time()
    last = _create_cooldown.get(user["id"], 0)
    if now - last < 12:
        raise HTTPException(429, "Espera unos segundos antes de crear otro ticket.")
    cfg = await get_config()
    cats = {c["id"]: c for c in cfg["categories"]}
    cat = cats.get(data.category)
    if not cat:
        raise HTTPException(400, "Categoría inválida.")
    fields = {}
    for f in cat["fields"]:
        v = _clean((data.fields or {}).get(f["key"], ""))
        if f.get("required") and not v:
            raise HTTPException(400, f"Falta el campo obligatorio: {f['label']}")
        if v:
            fields[f["key"]] = v[:2000]
    # servidor legible
    server_name = ""
    sid = fields.get("server")
    if sid:
        server_name = next((s["name"] for s in cfg["servers"] if s["id"] == sid), sid)
    open_count = await _db.tickets.count_documents({"user_id": user["id"], "status": {"$in": ["open", "in_process", "waiting_user"]}})
    if open_count >= 8:
        raise HTTPException(400, "Tienes demasiados tickets abiertos. Cierra alguno antes de crear otro.")
    _create_cooldown[user["id"]] = now
    tid = _nid()
    code = await _gen_code()
    t = {
        "id": tid, "code": code,
        "user_id": user["id"], "user_name": user.get("persona_name") or "Superviviente",
        "user_avatar": user.get("avatar") or "",
        "steam_id": fields.get("steam_id") or user.get("steam_id") or "",
        "discord_id": user.get("discord_id") or "",
        "category": data.category,
        "subject": fields.get("subject") or cat["name"],
        "description": fields.get("description") or fields.get("explanation") or "",
        "server": sid or "", "server_name": server_name,
        "incident_date": fields.get("incident_date") or "",
        "incident_time": fields.get("incident_time") or "",
        "priority": "normal", "status": "open",
        "assigned_to": None, "assigned_name": None,
        "reported_staff_id": None,
        "fields": fields,
        "created_at": _iso(), "updated_at": _iso(), "last_activity": _iso(),
    }
    await _db.tickets.insert_one(dict(t))
    # primer mensaje del sistema con el resumen
    await _add_message(t, {"id": user["id"], "name": t["user_name"], "avatar": t["user_avatar"]},
                       t["description"] or t["subject"], role="user", notify=False)
    await _log_event(tid, t["user_name"], "Ticket creado")
    await _discord_notify_new(t)
    pub = _pub_ticket(t, True)
    await hub.send_staff("ticket:created", pub)
    await hub.send(user["id"], "ticket:created", pub)
    return pub


async def _add_message(t, author, text, role="user", internal=False, attachments=None, origin="web", notify=True):
    msg = {
        "id": _nid(), "ticket_id": t["id"],
        "author_id": author.get("id"), "author_name": author.get("name") or "?",
        "author_avatar": author.get("avatar") or "",
        "role": role, "text": _clean(text)[:4000], "internal": bool(internal),
        "attachments": attachments or [], "origin": origin,
        "created_at": _iso(), "read_by": [author.get("id")],
    }
    await _db.ticket_messages.insert_one(dict(msg))
    await _db.tickets.update_one({"id": t["id"]}, {"$set": {"last_activity": _iso(), "updated_at": _iso()}})
    if notify:
        # a dueño + staff (notas internas solo a staff)
        targets = set([t["user_id"]]) if not internal else set()
        targets |= set(hub.staff)
        if internal:
            targets.discard(t["user_id"])
        await hub.send_many(list(targets), "message:new", {"ticket_id": t["id"], "message": msg})
        if role == "user" and not internal:
            await _discord_relay_message(t, author.get("name"), text)
    return msg


async def get_my_tickets(user, status=None):
    q = {"user_id": user["id"]}
    if status and status in STATUSES:
        q["status"] = status
    rows = await _db.tickets.find(q, {"_id": 0}).sort("last_activity", -1).to_list(100)
    return {"tickets": [_pub_ticket(r) for r in rows]}


async def get_ticket(user, tid):
    t = await _db.tickets.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Ticket no encontrado.")
    if not _can_view(t, user):
        raise HTTPException(403, "No tienes acceso a este ticket.")
    staff = _is_staff_fn(user)
    q = {"ticket_id": tid}
    if not staff:
        q["internal"] = False
    msgs = await _db.ticket_messages.find(q, {"_id": 0}).sort("created_at", 1).to_list(1000)
    events = await _db.ticket_events.find({"ticket_id": tid}, {"_id": 0}).sort("at", 1).to_list(200) if staff else []
    return {"ticket": _pub_ticket(t, staff), "messages": msgs, "events": events, "can_manage": _can_manage(t, user), "is_staff": staff}


async def post_message(user, tid, text, attachments=None, internal=False):
    t = await _db.tickets.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Ticket no encontrado.")
    staff = _is_staff_fn(user)
    if internal and not _can_manage(t, user):
        raise HTTPException(403, "Solo el staff puede añadir notas internas.")
    if not internal and not _can_view(t, user):
        raise HTTPException(403, "Sin acceso.")
    text = _clean(text)
    if not text and not attachments:
        raise HTTPException(400, "Mensaje vacío.")
    author = {"id": user["id"], "name": user.get("persona_name") or "?", "avatar": user.get("avatar") or ""}
    role = "staff" if staff else "user"
    msg = await _add_message(t, author, text, role=role, internal=internal, attachments=attachments)
    if internal:
        await _log_event(tid, author["name"], "Staff añadió una nota interna")
    return {"success": True, "message": msg}


async def _update_ticket(user, tid, changes, event_text):
    t = await _db.tickets.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Ticket no encontrado.")
    if not _can_manage(t, user):
        raise HTTPException(403, "Solo el staff puede gestionar el ticket.")
    changes["updated_at"] = _iso()
    await _db.tickets.update_one({"id": tid}, {"$set": changes})
    await _log_event(tid, user.get("persona_name") or "Staff", event_text)
    t2 = await _db.tickets.find_one({"id": tid}, {"_id": 0})
    pub = _pub_ticket(t2, True)
    await hub.send_staff("ticket:updated", pub)
    await hub.send(t["user_id"], "ticket:updated", _pub_ticket(t2))
    return {"success": True, "ticket": pub}


async def staff_list(user, box="new", search="", limit=100):
    if not _is_staff_fn(user):
        raise HTTPException(403, "Solo staff.")
    q = {}
    if box == "new":
        q = {"status": "open", "assigned_to": None}
    elif box == "unassigned":
        q = {"assigned_to": None, "status": {"$ne": "closed"}}
    elif box == "mine":
        q = {"assigned_to": user["id"]}
    elif box in ("in_process", "waiting_user", "resolved", "closed"):
        q = {"status": box}
    if search:
        s = _clean(search)
        q = {"$and": [q, {"$or": [
            {"code": {"$regex": re.escape(s), "$options": "i"}},
            {"steam_id": {"$regex": re.escape(s), "$options": "i"}},
            {"user_name": {"$regex": re.escape(s), "$options": "i"}},
            {"discord_id": {"$regex": re.escape(s), "$options": "i"}},
            {"subject": {"$regex": re.escape(s), "$options": "i"}},
        ]}]} if q else {"$or": []}
    rows = await _db.tickets.find(q, {"_id": 0}).sort("last_activity", -1).to_list(limit)
    # respeta privacidad de report_staff
    rows = [r for r in rows if not (r.get("category") == "report_staff" and r.get("reported_staff_id") == user["id"])]
    counts = {
        "new": await _db.tickets.count_documents({"status": "open", "assigned_to": None}),
        "unassigned": await _db.tickets.count_documents({"assigned_to": None, "status": {"$ne": "closed"}}),
        "mine": await _db.tickets.count_documents({"assigned_to": user["id"]}),
        "in_process": await _db.tickets.count_documents({"status": "in_process"}),
        "waiting_user": await _db.tickets.count_documents({"status": "waiting_user"}),
        "resolved": await _db.tickets.count_documents({"status": "resolved"}),
        "closed": await _db.tickets.count_documents({"status": "closed"}),
    }
    return {"tickets": [_pub_ticket(r, True) for r in rows], "counts": counts, "staff_online": len(hub.staff)}


# ─────────────── Models ───────────────
class CreateIn(BaseModel):
    category: str
    fields: dict = {}

class MessageIn(BaseModel):
    text: str = ""
    attachments: list = []
    internal: bool = False

class UpdateIn(BaseModel):
    priority: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    assigned_to: Optional[str] = None


def build_router(get_current_user, get_admin_user):
    router = APIRouter(prefix="/tickets", tags=["tickets"])

    @router.get("/config")
    async def config(user=Depends(get_current_user)):
        cfg = await get_config()
        return {**cfg, "is_staff": _is_staff_fn(user)}

    @router.post("")
    async def create(data: CreateIn, user=Depends(get_current_user)):
        return await create_ticket(user, data)

    @router.get("/mine")
    async def mine(status: str = None, user=Depends(get_current_user)):
        return await get_my_tickets(user, status)

    @router.get("/staff")
    async def staff(box: str = "new", search: str = "", user=Depends(get_current_user)):
        return await staff_list(user, box, search)

    @router.get("/{tid}")
    async def one(tid: str, user=Depends(get_current_user)):
        return await get_ticket(user, tid)

    @router.post("/{tid}/message")
    async def message(tid: str, data: MessageIn, user=Depends(get_current_user)):
        return await post_message(user, tid, data.text, data.attachments, data.internal)

    @router.post("/{tid}/take")
    async def take(tid: str, user=Depends(get_current_user)):
        if not _is_staff_fn(user): raise HTTPException(403, "Solo staff.")
        return await _update_ticket(user, tid, {"assigned_to": user["id"], "assigned_name": user.get("persona_name"), "status": "in_process"}, f"{user.get('persona_name')} tomó el ticket")

    @router.post("/{tid}/update")
    async def update(tid: str, data: UpdateIn, user=Depends(get_current_user)):
        changes, ev = {}, []
        if data.priority in PRIORITIES: changes["priority"] = data.priority; ev.append(f"Prioridad → {data.priority}")
        if data.status in STATUSES: changes["status"] = data.status; ev.append(f"Estado → {data.status}")
        if data.category: changes["category"] = data.category; ev.append(f"Categoría → {data.category}")
        if data.assigned_to is not None:
            if data.assigned_to:
                su = await _db.users.find_one({"id": data.assigned_to}, {"_id": 0, "persona_name": 1})
                changes["assigned_to"] = data.assigned_to; changes["assigned_name"] = (su or {}).get("persona_name")
                ev.append("Ticket asignado")
            else:
                changes["assigned_to"] = None; changes["assigned_name"] = None; ev.append("Asignación quitada")
        if not changes: raise HTTPException(400, "Nada que actualizar.")
        return await _update_ticket(user, tid, changes, " · ".join(ev))

    # ─── Admin: configuración de servidores y categorías ───
    @router.get("/admin/config")
    async def admin_config(user=Depends(get_admin_user)):
        return await get_config()

    @router.put("/admin/config")
    async def admin_save(data: dict, user=Depends(get_admin_user)):
        upd = {}
        if isinstance(data.get("servers"), list): upd["servers"] = data["servers"]
        if isinstance(data.get("categories"), list): upd["categories"] = data["categories"]
        if upd:
            await _db.ticket_config.update_one({"_id": "config"}, {"$set": upd}, upsert=True)
        return await get_config()

    @router.get("/admin/by-steam/{steam_id}")
    async def by_steam(steam_id: str, user=Depends(get_admin_user)):
        rows = await _db.tickets.find({"steam_id": _clean(steam_id)}, {"_id": 0}).sort("last_activity", -1).to_list(100)
        return {"tickets": [_pub_ticket(r, True) for r in rows]}

    @router.websocket("/ws")
    async def ticket_ws(ws: WebSocket):
        await ws.accept()
        uid = None; token = ws.query_params.get("token")
        if token:
            try: uid = jwt.decode(token, _jwt_secret, algorithms=[_jwt_algo]).get("sub")
            except Exception: uid = None
        u = await _db.users.find_one({"id": uid}, {"_id": 0}) if uid else None
        if not u: uid = None
        staff = bool(u and _is_staff_fn(u))
        try:
            hub.add(ws, uid, staff)
            await ws.send_json({"event": "ticket:hello", "data": {"ok": True, "staff": staff, "staff_online": len(hub.staff)}})
            while True:
                m = await ws.receive_json()
                ev = m.get("event"); d = m.get("data") or {}
                tid = d.get("ticket_id")
                if ev == "ping":
                    await ws.send_json({"event": "pong", "data": {}})
                elif ev in ("typing:start", "typing:stop") and tid and uid:
                    t = await _db.tickets.find_one({"id": tid}, {"_id": 0, "user_id": 1})
                    if t:
                        name = (u or {}).get("persona_name") or "Alguien"
                        targets = set([t["user_id"]]) | set(hub.staff)
                        targets.discard(uid)
                        await hub.send_many(list(targets), ev, {"ticket_id": tid, "name": name, "uid": uid})
                elif ev == "staff:viewing" and tid and staff:
                    name = (u or {}).get("persona_name") or "Staff"
                    await hub.send_staff("staff:viewing", {"ticket_id": tid, "name": name, "uid": uid})
                elif ev == "message:read" and tid and uid:
                    await _db.ticket_messages.update_many({"ticket_id": tid}, {"$addToSet": {"read_by": uid}})
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("[tickets] ws: %r", e)
        finally:
            hub.remove(ws)

    return router
