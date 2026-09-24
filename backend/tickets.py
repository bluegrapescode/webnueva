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
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Response
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
TICKETS_CLOSED_CATEGORY_ID = os.environ.get("TICKETS_CLOSED_CHANNEL_ID", "").strip()
TICKETS_HELP_CHANNEL_ID = os.environ.get("TICKETS_HELP_CHANNEL_ID", "").strip()
PUBLIC_URL = (os.environ.get("PUBLIC_APP_URL") or os.environ.get("PUBLIC_BASE_URL") or os.environ.get("FRONTEND_URL") or "").strip()

# ─────────────── Object Storage (subida real de evidencias) ───────────────
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()
STORAGE_APP = "laislanublar"
_storage_key = None
UPLOAD_EXT = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "webm", "mov", "m4v"}
UPLOAD_MIME = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
    "webp": "image/webp", "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime", "m4v": "video/x-m4v",
}
MAX_UPLOAD = 25 * 1024 * 1024


async def _storage_init():
    global _storage_key
    if _storage_key:
        return _storage_key
    if not EMERGENT_KEY:
        return None
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY})
        r.raise_for_status()
        _storage_key = r.json()["storage_key"]
    return _storage_key


async def _storage_put(path, data, content_type):
    key = await _storage_init()
    if not key:
        raise HTTPException(503, "Almacenamiento no disponible.")
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type}, content=data)
        r.raise_for_status()
        return r.json()


async def _storage_get(path):
    key = await _storage_init()
    if not key:
        raise HTTPException(404, "Archivo no encontrado.")
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key})
        r.raise_for_status()
        return r.content, r.headers.get("Content-Type", "application/octet-stream")

STATUSES = ["open", "in_process", "waiting_user", "resolved", "closed"]
PRIORITIES = ["normal", "media", "alta", "urgente"]
# Prioridad por defecto según la gravedad de la categoría (reportes=rojo, apelación=amarillo, preguntas=verde)
CAT_PRIORITY = {
    "report_staff": "urgente", "report_player": "urgente",
    "appeal": "media",
    "general": "normal", "membership": "normal", "patreon": "normal", "battlepass": "normal",
}


def _default_priority(cat_id):
    return CAT_PRIORITY.get(cat_id, "normal")


def _is_img_url(u):
    return bool(re.search(r"\.(png|jpe?g|gif|webp)(\?|$)", str(u or ""), re.I))
_create_cooldown = {}  # user_id -> ts
_link_cache = {}       # url -> (ts, data)  cache en memoria para previews de enlaces

DEFAULT_SERVERS = [
    {"id": "isla-nublar-x3", "name": "LA ISLA NUBLAR - X3 - SEMI-REALISMO - VC - ESP/LATAM"},
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
def _clean(s): return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(s or "")).strip()


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
    await _db.tickets.create_index("discord_thread_id")
    await _db.ticket_messages.create_index("ticket_id")
    await _db.ticket_messages.create_index("discord_message_id")
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


async def _estimate_response():
    """Estimación dinámica del tiempo de respuesta según cuántos tickets activos hay en cola."""
    n = await _db.tickets.count_documents({"status": {"$in": ["open", "in_process", "waiting_user"]}})
    if n <= 5:
        eta = "2–6 horas"
    elif n <= 12:
        eta = "6–12 horas"
    elif n <= 25:
        eta = "12–24 horas"
    elif n <= 45:
        eta = "24–48 horas"
    else:
        eta = "48–72 horas"
    return eta, n


def _welcome_message(cat_id, eta, queue, help_url=""):
    greet = {
        "general": "👋 ¡Hola! Cuéntanos tu duda con el mayor detalle posible y te ayudaremos enseguida.",
        "report_player": "👋 Gracias por reportar. Ten **toda la evidencia a la mano** e insértala aquí para que el staff pueda actuar.",
        "report_staff": "👋 Gracias por tu reporte. Este canal es **confidencial**: describe lo ocurrido con el mayor detalle y aporta pruebas si las tienes.",
        "appeal": "👋 Vamos a revisar tu caso. Explica con calma por qué crees que tu sanción debería revisarse.",
        "membership": "👋 ¡Hola! Cuéntanos qué necesitas con tu membresía y lo revisamos lo antes posible.",
        "patreon": "👋 ¡Gracias por tu apoyo! Cuéntanos tu consulta de Patreon y te ayudamos con tus beneficios.",
        "battlepass": "👋 ¡Hola! Cuéntanos qué ocurre con tu Battle Pass y lo revisamos.",
    }.get(cat_id, "👋 ¡Gracias por contactarnos! Cuéntanos tu consulta y el staff te ayudará.")

    lines = [
        greet,
        f"⏱️ **Tiempo estimado actual:** {eta} · hay {queue} ticket(s) en cola.",
        "",
        "## Tiempo de Respuesta",
        "Respondemos la mayoría de tickets en **24–48 horas**.",
        "Para agilizar la atención:",
        "• Abre **un solo ticket** por problema.",
        "!• El spam o abuso del sistema puede resultar en advertencias o restricciones temporales de soporte.",
        "",
    ]

    sections = {
        "general": [
            "## Sobre tu Consulta",
            "Este ticket es para **dudas y preguntas generales** — no necesitas adjuntar pruebas.",
            "• Describe tu duda o problema con el mayor detalle posible y el staff te responderá.",
        ],
        "report_player": [
            "## Requisitos para Reportes de Jugadores",
            "Los reportes deben incluir **toda la evidencia necesaria**:",
            "• Replay desde el menú F2",
            "• Clip POV del jugador",
            "• Descripción clara de lo ocurrido",
            "!• No aceptamos clips sueltos ni archivos directamente en el ticket.",
            "Las pruebas deben enviarse mediante un **enlace** (ej. Medal u otra plataforma similar).",
            "!Los reportes sin evidencia suficiente podrán ser rechazados.",
        ],
        "report_staff": [
            "## Requisitos para Reportes de Staff",
            "Este reporte se trata con **total confidencialidad y discreción**.",
            "• Indica **qué miembro del staff**, la **fecha/hora** y el **servidor**.",
            "• Describe con claridad lo ocurrido.",
            "• Si tienes pruebas (clips o capturas), compártelas por **enlace** (ej. Medal).",
            "!Los reportes falsos o malintencionados pueden conllevar sanciones.",
        ],
        "appeal": [
            "## Sobre tu Apelación",
            "Explica con claridad **por qué crees que la sanción debe revisarse**.",
            "• Indica tu **SteamID** y, si lo conoces, el **motivo** mostrado.",
            "• Si tienes pruebas a tu favor, compártelas por **enlace** — no son obligatorias, pero ayudan.",
            "!Mantén un tono respetuoso: insultar o presionar al staff no acelerará tu apelación.",
        ],
        "membership": [
            "## Sobre tu Membresía",
            "Este ticket es para **preguntas y problemas de membresía** — no necesitas adjuntar pruebas.",
            "• Indícanos tu **SteamID** y describe qué ocurre (acceso, beneficios, renovación…).",
            "• Si tu caso es un **pago**, comparte el **comprobante** por enlace (si aplica).",
        ],
        "patreon": [
            "## Sobre tu Patreon",
            "Este ticket es para **tus beneficios de Patreon** — no necesitas adjuntar pruebas.",
            "• Indícanos tu **usuario de Discord** y tu **nivel/tier** de Patreon.",
            "• Cuéntanos qué necesitas: **roles, vinculación, recompensas o beneficios**.",
            "• Si es un pago, comparte el **comprobante** por enlace (si aplica).",
        ],
        "battlepass": [
            "## Sobre tu Battle Pass",
            "Este ticket es para **preguntas del Battle Pass** — no necesitas adjuntar pruebas.",
            "• Incluye tu **SteamID** y cuéntanos qué ocurre con tu **progreso, recompensas, tokens o compra**.",
        ],
    }
    lines += sections.get(cat_id, sections["general"])

    lines += [
        "",
        "!🆘 ¿Necesitas ayuda más rápida? Visita el **canal de ayuda** en nuestro Discord mientras un miembro del staff atiende tu ticket.",
    ]
    return "\n".join(lines)


DISCORD_API = "https://discord.com/api/v10"


def _bot_headers():
    return {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://laislanublar.net, 1.0)"}


async def _discord_create_thread(name):
    """Compat: crea un canal de texto por ticket bajo la categoría de tickets."""
    return await _discord_create_channel(name)


_DISCORD_GUILD_ID = None


async def _resolve_guild_id():
    global _DISCORD_GUILD_ID
    if _DISCORD_GUILD_ID:
        return _DISCORD_GUILD_ID
    env_gid = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if env_gid:
        _DISCORD_GUILD_ID = env_gid
        return _DISCORD_GUILD_ID
    if not (DISCORD_BOT_TOKEN and TICKETS_CHANNEL_ID):
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{DISCORD_API}/channels/{TICKETS_CHANNEL_ID}", headers=_bot_headers())
            if r.status_code < 300:
                _DISCORD_GUILD_ID = str(r.json().get("guild_id") or "")
                return _DISCORD_GUILD_ID or None
    except Exception as e:
        logger.warning("[tickets] resolve guild err: %r", e)
    return None


def _slug_channel(name):
    s = re.sub(r"[^a-z0-9\- ]", "", (name or "ticket").lower())
    s = re.sub(r"\s+", "-", s.strip()) or "ticket"
    return s[:90]


async def _discord_create_channel(name):
    """Crea un canal de texto por ticket bajo la categoría TICKETS_CHANNEL_ID.
    Devuelve el channel_id o None si falla (p. ej. sin permiso Manage Channels)."""
    if not (DISCORD_BOT_TOKEN and TICKETS_CHANNEL_ID):
        return None
    gid = await _resolve_guild_id()
    if not gid:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{DISCORD_API}/guilds/{gid}/channels", headers=_bot_headers(),
                             json={"name": _slug_channel(name), "type": 0,
                                   "parent_id": TICKETS_CHANNEL_ID,
                                   "topic": "Ticket de soporte — responde aquí y le llegará al usuario en la web."})
            if r.status_code >= 300:
                logger.warning("[tickets] crear canal %s: %s", r.status_code, r.text[:200])
                return None
            return str(r.json().get("id"))
    except Exception as e:
        logger.warning("[tickets] crear canal err: %r", e)
        return None


async def _discord_post(channel_id, content=None, embeds=None):
    if not (DISCORD_BOT_TOKEN and channel_id):
        return None
    payload = {"allowed_mentions": {"parse": []}}
    if content:
        payload["content"] = content[:1900]
    if embeds:
        payload["embeds"] = embeds
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{DISCORD_API}/channels/{channel_id}/messages",
                             headers=_bot_headers(), json=payload)
            if r.status_code >= 300:
                logger.warning("[tickets] post msg %s: %s", r.status_code, r.text[:200])
                return None
            return r.json()
    except Exception as e:
        logger.warning("[tickets] post msg err: %r", e)
        return None


def _welcome_to_embed_fields(text):
    """Convierte el aviso automático (marcadores internos) en campos de embed de Discord.
    '## Título' → nombre de campo; el resto de líneas → valor. '!'/'!•' → ⚠️. La línea 🆘 va aparte."""
    intro = []
    sections = []  # [ [name, [lines]] ]
    help_line = None
    for raw in str(text or "").split("\n"):
        line = raw
        if line.startswith("!• "):
            line = "⚠️ " + line[3:]
        elif line.startswith("!"):
            line = "⚠️ " + line[1:]
        if "🆘" in line:
            help_line = line.replace("⚠️ ", "").strip()
            continue
        if line.startswith("## "):
            sections.append([line[3:].strip(), []])
        elif not sections:
            if line.strip():
                intro.append(line)
        else:
            sections[-1][1].append(line)
    fields = []
    if intro:
        fields.append({"name": "\u200b", "value": "\n".join(intro).strip()[:1024], "inline": False})
    for name, lines in sections:
        val = "\n".join(lines).strip()
        if val:
            fields.append({"name": name[:256], "value": val[:1024], "inline": False})
    if help_line:
        fields.append({"name": "🆘 Ayuda rápida", "value": help_line[:1024], "inline": False})
    return fields


async def _discord_notify_new(t, welcome_text=""):
    if not (DISCORD_BOT_TOKEN and TICKETS_CHANNEL_ID):
        return
    cats = {c["id"]: c for c in (await get_config())["categories"]}
    cat = cats.get(t["category"], {})
    fields = t.get("fields") or {}
    ev = fields.get("evidence") or ""
    link = f"{PUBLIC_URL}/soporte?t={t['id']}" if PUBLIC_URL else "Abrir en la web"
    thread_id = await _discord_create_channel(f"ticket-{t['code']}")

    CAT_COLORS = {"report_player": 0xEF4444, "report_staff": 0xF59E0B, "appeal": 0x8B5CF6,
                  "membership": 0x22D3EE, "patreon": 0xF96854, "battlepass": 0xEAB308, "general": 0x22C55E}
    PRIO_EMOJI = {"normal": "🟢", "media": "🟡", "alta": "🟠", "urgente": "🔴"}
    color = CAT_COLORS.get(t["category"], 0x22C55E)
    emoji = cat.get("emoji", "🎫")
    cat_name = cat.get("name", t["category"])
    avatar = t.get("user_avatar") or ""
    avatar = avatar if isinstance(avatar, str) and avatar.startswith("http") else None
    prio = t.get("priority", "normal")

    is_report = t["category"] in ("report_player", "report_staff")
    inline_fields = [
        {"name": "🏷️ Prioridad", "value": f"{PRIO_EMOJI.get(prio,'🟢')} {prio.capitalize()}", "inline": True},
        {"name": "🎮 SteamID", "value": f"`{t.get('steam_id')}`" if t.get("steam_id") else "—", "inline": True},
    ]
    if is_report or t.get("server_name"):
        inline_fields.append({"name": "🗺️ Servidor", "value": t.get("server_name") or "—", "inline": True})
    if is_report:
        inline_fields.append({"name": "📅 Fecha / Hora", "value": f"{t.get('incident_date') or '—'} {t.get('incident_time') or ''}".strip(), "inline": True})
    if t.get("discord_id"):
        inline_fields.append({"name": "💬 Discord", "value": f"<@{t['discord_id']}>", "inline": True})

    welcome_fields = _welcome_to_embed_fields(welcome_text)
    fields_list = list(inline_fields)
    if ev:
        fields_list.append({"name": "🔗 Evidencias", "value": ev[:1000], "inline": False})
    fields_list += welcome_fields
    fields_list.append({"name": "\u200b", "value": f"📩 **[Abrir el ticket en la web]({link})**" if PUBLIC_URL else "📩 Abrir en la web", "inline": False})
    fields_list.append({"name": "💬 ¿Cómo responder?", "value": "Escribe **en este canal** y tu mensaje le llegará al usuario en la web en tiempo real.", "inline": False})

    embed = {
        "author": {"name": f"{t.get('user_name','Superviviente')} abrió un ticket", **({"icon_url": avatar} if avatar else {})},
        "title": f"{emoji}  {cat_name}",
        "url": link if PUBLIC_URL else None,
        "description": f"**`{t['code']}`**\n>>> {(t.get('description') or '—')[:900]}",
        "color": color,
        "fields": fields_list[:25],
        "footer": {"text": "La Isla Nublar · Sistema de Soporte"},
        "timestamp": _iso(),
    }
    if avatar:
        embed["thumbnail"] = {"url": avatar}
    embed = {k: v for k, v in embed.items() if v is not None}

    target = thread_id or TICKETS_CHANNEL_ID
    content = f"{PRIO_EMOJI.get(prio,'🟢')} Nuevo ticket **{t['code']}** — {emoji} {cat_name}"
    msg = await _discord_post(target, content=content, embeds=[embed])
    upd = {}
    if thread_id:
        upd["discord_thread_id"] = thread_id
    if msg and msg.get("id"):
        upd["discord_opening_message_id"] = str(msg["id"])
    if upd:
        await _db.tickets.update_one({"id": t["id"]}, {"$set": upd})
        t.update(upd)


async def _discord_relay_message(t, author, text, attachments=None, role="user"):
    """Reenvía a Discord un mensaje escrito desde la web (al canal del ticket), con estilo (embed)."""
    if not DISCORD_BOT_TOKEN:
        return
    target = t.get("discord_thread_id")
    if not target:
        return
    a = author or {}
    name = a.get("name") or "Usuario"
    avatar = a.get("avatar") or ""
    avatar = avatar if isinstance(avatar, str) and avatar.startswith("http") else None
    is_staff = role == "staff"
    atts = attachments or []
    imgs = [u for u in atts if _is_img_url(u)]
    others = [u for u in atts if not _is_img_url(u)]
    desc = text or ""
    if others:
        desc += ("\n\n" if desc else "") + "\n".join(f"🔗 {u}" for u in others)
    if len(imgs) > 1:
        desc += ("\n\n" if desc else "") + "\n".join(imgs[1:])
    embed = {
        "author": {"name": f"{name}{'  ·  Staff' if is_staff else ''}", **({"icon_url": avatar} if avatar else {})},
        "description": (desc or "*(sin texto)*")[:4000],
        "color": 0x5865F2 if is_staff else 0x22C55E,
        "footer": {"text": "💬 Respuesta del staff" if is_staff else "📨 Mensaje del usuario (web)"},
        "timestamp": _iso(),
    }
    if imgs:
        embed["image"] = {"url": imgs[0]}
    await _discord_post(target, embeds=[embed])


# ─────────────── Discord Gateway (Discord -> Web) ───────────────
_discord_client = None
_discord_task = None


def _build_discord_client():
    import discord
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info("[tickets] Discord gateway conectado como %s", client.user)

    @client.event
    async def on_message(message):
        try:
            if client.user and message.author.id == client.user.id:
                return
            if getattr(message.author, "bot", False):
                return
            ch_id = str(getattr(message.channel, "id", "") or "")
            if not ch_id:
                return
            t = await _db.tickets.find_one({"discord_thread_id": ch_id}, {"_id": 0})
            if not t:
                return
            content = message.content or ""
            atts = [a.url for a in message.attachments] if message.attachments else []
            if not content and not atts:
                return
            did = str(message.id)
            if await _db.ticket_messages.find_one({"discord_message_id": did}, {"_id": 1}):
                return
            avatar = ""
            try:
                avatar = str(message.author.display_avatar.url)
            except Exception:
                pass
            author = {"id": None,
                      "name": (getattr(message.author, "display_name", None) or getattr(message.author, "name", None) or "Staff"),
                      "avatar": avatar}
            await _add_message(t, author, content, role="staff", attachments=atts,
                               origin="discord", discord_message_id=did)
            await _log_event(t["id"], author["name"], "Respuesta desde Discord")
        except Exception as e:
            logger.warning("[tickets] on_message err: %r", e)

    return client


async def _discord_ticket_state(t, closed, who):
    """Avisa en el canal de Discord del ticket que se cerró/reabrió y renombra el canal."""
    if not DISCORD_BOT_TOKEN:
        return
    ch = t.get("discord_thread_id")
    if not ch:
        return
    await _discord_post(ch, content=(f"🔒 **Ticket cerrado** por {who}. Enviado al historial." if closed
                                     else f"🔓 **Ticket reabierto** por {who}."))
    try:
        code = (t.get("code") or "").replace("#", "").lower()
        newname = _slug_channel(f"cerrado-{code}" if closed else f"ticket-{code}")
        payload = {"name": newname}
        # Mover el canal: a la categoría de cerrados al cerrar, de vuelta a la de tickets al reabrir.
        if closed and TICKETS_CLOSED_CATEGORY_ID:
            payload["parent_id"] = TICKETS_CLOSED_CATEGORY_ID
        elif (not closed) and TICKETS_CHANNEL_ID:
            payload["parent_id"] = TICKETS_CHANNEL_ID
        async with httpx.AsyncClient(timeout=10) as c:
            await c.patch(f"{DISCORD_API}/channels/{ch}", headers=_bot_headers(), json=payload)
    except Exception:
        pass


async def _discord_runner():
    global _discord_client
    if not DISCORD_BOT_TOKEN:
        logger.info("[tickets] DISCORD_BOT_TOKEN ausente; gateway desactivado")
        return
    try:
        _discord_client = _build_discord_client()
        await _discord_client.start(DISCORD_BOT_TOKEN, reconnect=True)
    except Exception as e:
        logger.warning("[tickets] gateway detenido: %r", e)


def start_discord_gateway():
    global _discord_task
    if _discord_task and not _discord_task.done():
        return
    try:
        _discord_task = asyncio.create_task(_discord_runner())
    except Exception as e:
        logger.warning("[tickets] no se pudo iniciar el gateway: %r", e)


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
        "priority": _default_priority(data.category), "status": "open",
        "assigned_to": None, "assigned_name": None,
        "reported_staff_id": None,
        "fields": fields,
        "created_at": _iso(), "updated_at": _iso(), "last_activity": _iso(),
    }
    await _db.tickets.insert_one(dict(t))
    # Aviso del sistema (requisitos + tiempo estimado dinámico) como PRIMER mensaje
    eta, queue = await _estimate_response()
    welcome = _welcome_message(t["category"], eta, queue)
    await _add_message(t, {"id": None, "name": "Soporte La Isla Nublar", "avatar": ""},
                       welcome, role="notice", notify=False)
    # primer mensaje del sistema con el resumen
    await _add_message(t, {"id": user["id"], "name": t["user_name"], "avatar": t["user_avatar"]},
                       t["description"] or t["subject"], role="user", notify=False)
    await _log_event(tid, t["user_name"], "Ticket creado")
    await _discord_notify_new(t, welcome)
    pub = _pub_ticket(t, True)
    await hub.send_staff("ticket:created", pub)
    await hub.send(user["id"], "ticket:created", pub)
    return pub


async def _add_message(t, author, text, role="user", internal=False, attachments=None, origin="web", notify=True, discord_message_id=None):
    msg = {
        "id": _nid(), "ticket_id": t["id"],
        "author_id": author.get("id"), "author_name": author.get("name") or "?",
        "author_avatar": author.get("avatar") or "",
        "role": role, "text": _clean(text)[:4000], "internal": bool(internal),
        "attachments": attachments or [], "origin": origin,
        "discord_message_id": discord_message_id,
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
        # Reenvía a Discord SOLO lo escrito desde la web (evita bucle con mensajes de Discord)
        if origin == "web" and not internal:
            await _discord_relay_message(t, author, text, attachments, role)
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


async def set_open_state(user, tid, closed):
    """Cerrar / reabrir un ticket. Permitido al DUEÑO del ticket o al staff."""
    t = await _db.tickets.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Ticket no encontrado.")
    is_owner = t.get("user_id") == user["id"]
    if closed:
        # Cerrar: lo puede hacer el dueño del ticket o el staff.
        if not (is_owner or _can_manage(t, user)):
            raise HTTPException(403, "No tienes acceso a este ticket.")
    else:
        # Reabrir: SOLO staff (un usuario no puede alternar el ticket a voluntad).
        if not _can_manage(t, user):
            raise HTTPException(403, "Solo el staff puede reabrir un ticket. Si necesitas ayuda, abre un ticket nuevo.")
    new_status = "closed" if closed else "open"
    if t.get("status") == new_status:
        return {"success": True, "ticket": _pub_ticket(t, True)}
    who = user.get("persona_name") or ("Staff" if _is_staff_fn(user) else "Usuario")
    await _db.tickets.update_one({"id": tid}, {"$set": {"status": new_status, "updated_at": _iso(), "last_activity": _iso()}})
    await _log_event(tid, who, "Ticket cerrado" if closed else "Ticket reabierto")
    t2 = await _db.tickets.find_one({"id": tid}, {"_id": 0})
    # Mensaje de sistema visible en el chat para ambas partes
    sysmsg = {
        "id": _nid(), "ticket_id": tid, "author_id": None,
        "author_name": who, "author_avatar": "", "role": "system",
        "text": f"🔒 {who} cerró el ticket." if closed else f"🔓 {who} reabrió el ticket.",
        "internal": False, "attachments": [], "origin": "web",
        "created_at": _iso(), "read_by": [],
    }
    await _db.ticket_messages.insert_one(dict(sysmsg))
    targets = set([t["user_id"]]) | set(hub.staff)
    await hub.send_many(list(targets), "message:new", {"ticket_id": tid, "message": sysmsg})
    await hub.send_staff("ticket:updated", _pub_ticket(t2, True))
    await hub.send(t["user_id"], "ticket:updated", _pub_ticket(t2))
    await _discord_ticket_state(t2, closed, who)
    return {"success": True, "ticket": _pub_ticket(t2, True)}


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

    @router.get("/link-preview")
    async def link_preview(url: str, user=Depends(get_current_user)):
        u = (url or "").strip()
        if not re.match(r"^https?://", u, re.I):
            raise HTTPException(400, "URL inválida.")
        now = time.time()
        hit = _link_cache.get(u)
        if hit and now - hit[0] < 3600:
            return hit[1]
        data = {"url": u, "title": None, "image": None, "video": None, "site": None, "description": None}

        def _meta(html, prop):
            m = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if not m:
                m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\']', html, re.I)
            return m.group(1).strip() if m else None

        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True, max_redirects=4,
                                         headers={"User-Agent": "Mozilla/5.0 (compatible; LaIslaNublarBot/1.0; +https://laislanublar.net)"}) as c:
                r = await c.get(u)
                if "text/html" in (r.headers.get("content-type") or ""):
                    html = r.text[:2500000]
                    title = _meta(html, "og:title") or _meta(html, "twitter:title")
                    if not title:
                        tm = re.search(r"<title[^>]*>([^<]{1,300})</title>", html, re.I)
                        title = tm.group(1).strip() if tm else None
                    data["title"] = title
                    data["image"] = _meta(html, "og:image") or _meta(html, "og:image:url") or _meta(html, "twitter:image") or _meta(html, "twitter:image:src")
                    data["video"] = _meta(html, "og:video") or _meta(html, "og:video:url") or _meta(html, "og:video:secure_url")
                    data["site"] = _meta(html, "og:site_name")
                    data["description"] = _meta(html, "og:description")
        except Exception as e:
            logger.info("[tickets] link-preview %r: %r", u, e)
        _link_cache[u] = (now, data)
        return data

    @router.get("/{tid}")
    async def one(tid: str, user=Depends(get_current_user)):
        return await get_ticket(user, tid)

    @router.post("/{tid}/message")
    async def message(tid: str, data: MessageIn, user=Depends(get_current_user)):
        return await post_message(user, tid, data.text, data.attachments, data.internal)

    @router.post("/{tid}/upload")
    async def upload_evidence(tid: str, file: UploadFile = File(...), user=Depends(get_current_user)):
        t = await _db.tickets.find_one({"id": tid}, {"_id": 0})
        if not t:
            raise HTTPException(404, "Ticket no encontrado.")
        if not _can_view(t, user):
            raise HTTPException(403, "Sin acceso.")
        fname = file.filename or ""
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in UPLOAD_EXT:
            raise HTTPException(400, "Tipo de archivo no permitido (imágenes o vídeos).")
        data = await file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(400, "Archivo demasiado grande (máx 25 MB).")
        if not data:
            raise HTTPException(400, "Archivo vacío.")
        fid = _nid()
        ct = file.content_type or UPLOAD_MIME.get(ext, "application/octet-stream")
        path = f"{STORAGE_APP}/tickets/{tid}/{fid}.{ext}"
        res = await _storage_put(path, data, ct)
        await _db.ticket_files.insert_one({
            "id": fid, "ticket_id": tid, "user_id": user["id"],
            "storage_path": res.get("path", path), "ext": ext, "content_type": ct,
            "name": fname or f"{fid}.{ext}", "size": len(data),
            "is_deleted": False, "created_at": _iso(),
        })
        base = PUBLIC_URL.rstrip("/") if PUBLIC_URL else ""
        return {"url": f"{base}/api/tickets/files/{fid}.{ext}", "content_type": ct, "name": fname}

    @router.get("/files/{fname}")
    async def serve_file(fname: str):
        fid = fname.rsplit(".", 1)[0]
        rec = await _db.ticket_files.find_one({"id": fid, "is_deleted": False}, {"_id": 0})
        if not rec:
            raise HTTPException(404, "Archivo no encontrado.")
        data, ct = await _storage_get(rec["storage_path"])
        return Response(content=data, media_type=rec.get("content_type") or ct,
                        headers={"Cache-Control": "public, max-age=86400"})

    @router.post("/{tid}/take")
    async def take(tid: str, user=Depends(get_current_user)):
        if not _is_staff_fn(user): raise HTTPException(403, "Solo staff.")
        return await _update_ticket(user, tid, {"assigned_to": user["id"], "assigned_name": user.get("persona_name"), "status": "in_process"}, f"{user.get('persona_name')} tomó el ticket")

    @router.post("/{tid}/close")
    async def close_ticket(tid: str, user=Depends(get_current_user)):
        return await set_open_state(user, tid, True)

    @router.post("/{tid}/reopen")
    async def reopen_ticket(tid: str, user=Depends(get_current_user)):
        return await set_open_state(user, tid, False)

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
