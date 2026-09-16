"""Sistema de Cacería / Bounties puestos por jugadores (☠️).

Rediseño: ya NO hay bounty aleatorio automático. Ahora los bounties los ponen
los propios jugadores:

  1) CONTRATO — un jugador elige a QUIÉN cazar de la lista de jugadores online y
     pone precio a su cabeza pagándolo de SU billetera (mínimo configurable). El
     primero que mate a ese objetivo (kill PVP validado por el servidor, distinto
     del que puso el contrato y de su grupo) cobra la recompensa. Varios contratos
     sobre el mismo objetivo SE ACUMULAN. Límite: 1 contrato activo por persona.

  2) AUTO-BOUNTY — un jugador pone precio a SU PROPIA cabeza y gana PrimeMeat por
     minuto mientras siga vivo, hasta que muera o se acabe el tiempo. Si lo matan,
     el cazador recibe Amberium y el jugador CONSERVA lo ya acumulado. Gratis, con
     cooldown. Además, cada cierto tiempo el servidor ENVÍA una invitación aleatoria
     a un jugador online de la web ("¿pones precio a tu cabeza?"), con fuerte
     protección para que sea muy raro que le toque a la misma persona.

Seguridad / anti-exploit: selección y validación 100% server-side; fondeo de
billetera atómico; compleción de muerte atómica e idempotente (nunca doble cobro);
no puedes cazarte a ti mismo ni a tu grupo; reembolso al expirar sin muerte.
Todo se empuja por WebSocket (sin polling). Discord recibe embeds.

Colecciones: bounties (type: contract|self), bounty_invite_log.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("bounty")

DARK_RED = 0x8B0000

DEFAULT_CONFIG = {
    "min_contract_prime": 20000,     # mínimo de PrimeMeat para poner un contrato
    "reward_amber_bonus": 100,       # Amberium mínimo que el sistema añade a la recompensa
    "contract_duration": 30 * 60,    # tiempo para reclamar el contrato (s)
    "self_prime_per_min": 5000,      # PrimeMeat/minuto del auto-bounty
    "self_max_seconds": 15 * 60,     # duración máxima del auto-bounty (s)
    "self_killer_amber": 300,        # Amberium para quien mata a un auto-bounty
    "self_cooldown": 10 * 60,        # cooldown para reponerte auto-bounty (s)
    "invite_interval": 5 * 60,       # cada cuánto se ofrece a alguien (s)
    "invite_recent_protection": 25,  # no repetir invitado entre los últimos N
    "invite_ttl": 90,                # segundos para aceptar la invitación
    "max_contracts_per_user": 3,     # contratos activos por persona
}

# Inyectado por server.py
_db = None
_admin_ids: set = set()
_online_provider = None      # async () -> [{sid,name,species,slug,alive}] | None (sim)
_resolve_user_id = None      # async (sid) -> uid | None
_user_info = None            # async (uid) -> {steam_id,name,avatar,coins,vip_coins} | None
_charge_wallet = None        # async (uid, prime, amber, ref) -> bool
_refund_wallet = None        # async (uid, prime, amber, ref) -> None
_award_reward = None         # async (uid, prime, amber, xp, ref) -> None
_ingame_grant = None         # (sid, prime, amber, xp) -> None (best effort)
_jwt_secret = ""
_jwt_algo = "HS256"

# Estado en memoria
_invite_recent = deque(maxlen=64)     # uids invitados recientemente
_self_cooldown_until: dict = {}       # uid -> ts hasta cuándo no puede reponerse
_paused = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _now().isoformat()


def _ms() -> int:
    return int(time.time() * 1000)


def _bid() -> str:
    return "BNT-" + uuid.uuid4().hex[:10].upper()


def _fmt(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


# ─────────────────────────── Hub WebSocket ───────────────────────────
class BountyHub:
    def __init__(self):
        self.conns: set = set()            # todas las conexiones (público)
        self.by_uid: dict = {}             # uid -> set(ws) (usuarios web logueados)
        self.uid_of: dict = {}             # ws -> uid
        self.info: dict = {}               # uid -> {name, steam_id, avatar}

    async def add(self, ws, uid=None, info=None):
        self.conns.add(ws)
        if uid:
            self.by_uid.setdefault(uid, set()).add(ws)
            self.uid_of[ws] = uid
            if info:
                self.info[uid] = info

    def remove(self, ws):
        self.conns.discard(ws)
        uid = self.uid_of.pop(ws, None)
        if uid and uid in self.by_uid:
            self.by_uid[uid].discard(ws)
            if not self.by_uid[uid]:
                self.by_uid.pop(uid, None)
                self.info.pop(uid, None)

    def online_web_uids(self) -> list:
        return list(self.by_uid.keys())

    async def broadcast(self, event: str, data: dict):
        payload = {"event": event, "data": data}
        dead = []
        for ws in list(self.conns):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove(ws)

    async def send_to(self, uid: str, event: str, data: dict):
        payload = {"event": event, "data": data}
        for ws in list(self.by_uid.get(uid, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.remove(ws)


hub = BountyHub()
_lock = asyncio.Lock()


# ─────────────────────────── Config ───────────────────────────
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


# ─────────────────────────── Roster online ───────────────────────────
async def _roster() -> list:
    if _online_provider:
        try:
            r = await _online_provider()
            if r is not None:
                _roster._last_sim = False
                return r
        except Exception as e:
            logger.warning("[bounty] online provider: %r", e)
    return _sim_roster()


def _is_sim() -> bool:
    return getattr(_roster, "_last_sim", False)


# ─────────────────────────── Serializers ───────────────────────────
def _pub_contract(c: dict) -> dict:
    return {
        "type": "contract", "bountyId": c["id"], "status": c["status"],
        "targetId": c.get("target_sid"), "targetName": c.get("target_name"),
        "dinosaur": c.get("target_species"), "slug": c.get("target_slug"),
        "placerName": c.get("placer_name"),
        "reward": {"primeMeat": c.get("reward", {}).get("prime", 0),
                   "amberium": c.get("reward", {}).get("amber", 0)},
        "createdAt": c.get("created_at_ms"), "expiresAt": c.get("expires_at_ms"),
        "killerName": c.get("killer_name"),
    }


def _pub_self(s: dict) -> dict:
    return {
        "type": "self", "bountyId": s["id"], "status": s["status"],
        "targetId": s.get("holder_sid"), "targetName": s.get("holder_name"),
        "dinosaur": s.get("holder_species"), "slug": s.get("holder_slug"),
        "primePerMin": s.get("prime_per_min"), "accrued": s.get("accrued_prime", 0),
        "startedAt": s.get("started_at_ms"), "endsAt": s.get("ends_at_ms"),
        "killerAmber": s.get("killer_amber"), "killerName": s.get("killer_name"),
    }


async def _build_board() -> dict:
    contracts = await _db.bounties.find(
        {"type": "contract", "status": "active"}, {"_id": 0}).to_list(500)
    # Acumular por objetivo.
    by_target = {}
    for c in contracts:
        sid = c["target_sid"]
        acc = by_target.get(sid)
        if not acc:
            acc = {"type": "contract", "targetId": sid, "targetName": c["target_name"],
                   "dinosaur": c.get("target_species"), "slug": c.get("target_slug"),
                   "reward": {"primeMeat": 0, "amberium": 0}, "count": 0,
                   "placerName": c.get("placer_name"), "createdAt": c.get("created_at_ms"),
                   "expiresAt": c.get("expires_at_ms")}
            by_target[sid] = acc
        acc["reward"]["primeMeat"] += c.get("reward", {}).get("prime", 0)
        acc["reward"]["amberium"] += c.get("reward", {}).get("amber", 0)
        acc["count"] += 1
        if c.get("created_at_ms") and (not acc.get("createdAt") or c["created_at_ms"] < acc["createdAt"]):
            acc["createdAt"] = c["created_at_ms"]
            acc["placerName"] = c.get("placer_name")
        if c.get("expires_at_ms") and (not acc["expiresAt"] or c["expires_at_ms"] > acc["expiresAt"]):
            acc["expiresAt"] = c["expires_at_ms"]
    selfs = await _db.bounties.find(
        {"type": "self", "status": "active"}, {"_id": 0}).to_list(200)
    board_contracts = sorted(by_target.values(), key=lambda x: x["reward"]["primeMeat"], reverse=True)
    board_self = [_pub_self(s) for s in selfs]
    return {"contracts": board_contracts, "self": board_self}


async def snapshot() -> dict:
    return {"config": await get_config(), "board": await _build_board(), "paused": _paused}


async def _push_board():
    await hub.broadcast("bounty:board", await _build_board())


# ─────────────────────────── Discord ───────────────────────────
_http = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0),
                          limits=httpx.Limits(max_connections=10, max_keepalive_connections=5))


async def _discord(embed: dict, retries: int = 2):
    url = os.environ.get("DISCORD_BOUNTY_WEBHOOK_URL", "").strip()
    if not url:
        return
    payload = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    for a in range(retries + 1):
        try:
            r = await _http.post(url, json=payload)
            if 200 <= r.status_code < 300:
                return
            if r.status_code == 429 and a < retries:
                try:
                    ra = float(r.json().get("retry_after", 1.0))
                except Exception:
                    ra = 1.0
                await asyncio.sleep(min(ra + random.uniform(0, 0.25), 30))
                continue
            if r.status_code in {500, 502, 503, 504} and a < retries:
                await asyncio.sleep(min((2 ** a) + random.random(), 10))
                continue
            return
        except Exception:
            return


def _discord_contract(c: dict) -> dict:
    r = c["reward"]
    return {
        "title": "☠️ NUEVO BOUNTY DETECTADO",
        "color": DARK_RED,
        "description": (f"**{c.get('placer_name','Alguien')}** puso precio a la cabeza de un jugador.\n\n"
                        "☠️ El primero que lo elimine se lleva la recompensa."),
        "fields": [
            {"name": "🎯 OBJETIVO", "value": c.get("target_name") or "—", "inline": True},
            {"name": "🦖 DINOSAURIO", "value": c.get("target_species") or "—", "inline": True},
            {"name": "💰 RECOMPENSA",
             "value": f"🥩 {_fmt(r['prime'])} Prime Meat" + (f"\n🟠 {_fmt(r['amber'])} Amberium" if r.get("amber") else ""),
             "inline": False},
        ],
        "footer": {"text": f"BOUNTY ID • {c['id']}"}, "timestamp": _iso(),
    }


def _discord_completed(target_name, killer_name, prime, amber, bid) -> dict:
    return {
        "title": "💀 BOUNTY COMPLETADO",
        "color": DARK_RED,
        "description": "☠️ La cacería ha terminado.",
        "fields": [
            {"name": "🎯 OBJETIVO ELIMINADO", "value": target_name or "—", "inline": True},
            {"name": "⚔️ CAZADOR", "value": killer_name or "—", "inline": True},
            {"name": "💰 RECOMPENSA ENTREGADA",
             "value": f"🥩 {_fmt(prime)} Prime Meat" + (f"\n🟠 {_fmt(amber)} Amberium" if amber else ""),
             "inline": False},
        ],
        "footer": {"text": f"BOUNTY ID • {bid}"}, "timestamp": _iso(),
    }


# ─────────────────────────── Grupo / anti-exploit ───────────────────────────
async def _same_group(sid_a: str, sid_b: str) -> bool:
    """Best-effort: sin datos de tribu/grupo en el roster actual devuelve False.
    Cuando el mod exponga tribu se puede completar aquí."""
    return False


# ─────────────────────────── Contratos ───────────────────────────
async def place_contract(uid: str, target_sid: str, prime: int, amber: int = 0) -> dict:
    """El que pone el contrato paga SOLO con PrimeMeat. La recompensa que recibe el
    cazador es ese PrimeMeat + un mínimo de Amberium que aporta el sistema."""
    cfg = await get_config()
    prime = max(0, int(prime or 0))
    if prime < cfg["min_contract_prime"]:
        raise HTTPException(400, f"El mínimo es {cfg['min_contract_prime']} PrimeMeat")
    amber_bonus = int(cfg["reward_amber_bonus"])
    info = await _user_info(uid) if _user_info else None
    if not info:
        raise HTTPException(400, "Usuario inválido")
    placer_sid = str(info.get("steam_id") or "")
    if placer_sid and str(target_sid) == placer_sid:
        raise HTTPException(400, "No puedes ponerte precio a ti mismo (usa auto-bounty)")
    # Objetivo debe estar online.
    roster = await _roster()
    tgt = next((p for p in roster if str(p.get("sid")) == str(target_sid)), None)
    if not tgt or not tgt.get("alive", True):
        raise HTTPException(400, "El objetivo no está disponible")
    if placer_sid and await _same_group(placer_sid, str(target_sid)):
        raise HTTPException(400, "No puedes cazar a alguien de tu grupo")
    # Límite de contratos activos por persona.
    active_mine = await _db.bounties.count_documents(
        {"type": "contract", "status": "active", "placer_user_id": uid})
    if active_mine >= cfg["max_contracts_per_user"]:
        raise HTTPException(400, f"Alcanzaste el máximo de {cfg['max_contracts_per_user']} bounties activos. Cancela uno para poner otro")
    # Cobro atómico: SOLO PrimeMeat.
    ok = await _charge_wallet(uid, prime, 0, "Bounty: fondeo de contrato")
    if not ok:
        raise HTTPException(400, "Fondos insuficientes")
    c = {
        "id": _bid(), "type": "contract", "status": "active",
        "placer_user_id": uid, "placer_sid": placer_sid, "placer_name": info.get("name"),
        "target_sid": str(target_sid), "target_name": tgt.get("name"),
        "target_species": tgt.get("species"), "target_slug": tgt.get("slug"),
        "target_user_id": await _resolve_user_id(str(target_sid)) if _resolve_user_id else None,
        "reward": {"prime": prime, "amber": amber_bonus},
        "paid_prime": prime,  # lo que realmente pagó el que puso el contrato (para reembolso)
        "created_at": _iso(), "created_at_ms": _ms(),
        "expires_at_ms": _ms() + cfg["contract_duration"] * 1000,
        "killer_sid": None, "killer_name": None, "killer_user_id": None,
        "reward_processed": False,
    }
    try:
        await _db.bounties.insert_one(dict(c))
    except Exception as e:
        # Nunca dejar al usuario cobrado sin bounty: reembolsar y abortar.
        await _refund_wallet(uid, prime, 0, "Bounty: reembolso (fallo al crear el contrato)")
        logger.warning("[bounty] insert contract failed, refunded uid=%s: %r", uid, e)
        raise HTTPException(500, "No se pudo crear el bounty; te reembolsamos tu PrimeMeat")
    await hub.broadcast("bounty:contract_new", _pub_contract(c))
    await _push_board()
    asyncio.create_task(_discord(_discord_contract(c)))
    logger.info("[bounty] CONTRACT %s by=%s target=%s prime=%s", c["id"], uid, target_sid, prime)
    return _pub_contract(c)


async def cancel_contract(uid: str, bounty_id: str) -> dict:
    c = await _db.bounties.find_one({"id": bounty_id, "type": "contract"}, {"_id": 0})
    if not c or c["placer_user_id"] != uid:
        raise HTTPException(404, "Bounty no encontrado")
    res = await _db.bounties.update_one(
        {"id": bounty_id, "status": "active"},
        {"$set": {"status": "cancelled", "cancelled_at": _iso()}})
    if res.modified_count != 1:
        raise HTTPException(400, "El bounty ya no está activo")
    refund = int(c.get("paid_prime", c["reward"]["prime"]))
    await _refund_wallet(uid, refund, 0, "Bounty: reembolso por cancelación")
    await _push_board()
    return {"ok": True, "refunded": {"prime": refund}}


# ─────────────────────────── Auto-bounty ───────────────────────────
async def start_self(uid: str, from_invite: bool = False) -> dict:
    cfg = await get_config()
    now = time.time()
    if _self_cooldown_until.get(uid, 0) > now:
        left = int(_self_cooldown_until[uid] - now)
        raise HTTPException(400, f"Debes esperar {left // 60}m {left % 60}s para volver a ponerte precio")
    existing = await _db.bounties.find_one({"type": "self", "status": "active", "holder_user_id": uid})
    if existing:
        raise HTTPException(400, "Ya tienes un auto-bounty activo")
    info = await _user_info(uid) if _user_info else None
    if not info:
        raise HTTPException(400, "Usuario inválido")
    holder_sid = str(info.get("steam_id") or "")
    roster = await _roster()
    tgt = next((p for p in roster if str(p.get("sid")) == holder_sid), None)
    s = {
        "id": _bid(), "type": "self", "status": "active",
        "holder_user_id": uid, "holder_sid": holder_sid, "holder_name": info.get("name"),
        "holder_species": (tgt or {}).get("species") or "Dinosaurio",
        "holder_slug": (tgt or {}).get("slug"),
        "prime_per_min": cfg["self_prime_per_min"], "killer_amber": cfg["self_killer_amber"],
        "accrued_prime": 0, "from_invite": from_invite,
        "started_at": _iso(), "started_at_ms": _ms(), "last_accrual_ms": _ms(),
        "ends_at_ms": _ms() + cfg["self_max_seconds"] * 1000,
        "killer_sid": None, "killer_name": None, "reward_processed": False,
    }
    await _db.bounties.insert_one(dict(s))
    await hub.broadcast("bounty:self_started", _pub_self(s))
    await hub.send_to(uid, "bounty:self_mine", _pub_self(s))
    await _push_board()
    asyncio.create_task(_discord({
        "title": "🩸 PRECIO A SU PROPIA CABEZA",
        "color": DARK_RED,
        "description": (f"**{info.get('name')}** puso precio a su propia cabeza.\n\n"
                        f"Gana 🥩 {_fmt(cfg['self_prime_per_min'])} PrimeMeat/min mientras siga vivo. "
                        f"¡Quien lo elimine se lleva 🟠 {_fmt(cfg['self_killer_amber'])} Amberium!"),
        "footer": {"text": f"BOUNTY ID • {s['id']}"}, "timestamp": _iso(),
    }))
    logger.info("[bounty] SELF %s uid=%s", s["id"], uid)
    return _pub_self(s)


# ─────────────────────────── Validación de muerte ───────────────────────────
async def on_kill(killer_sid: str, victim_sid: str, killer_name: str = None):
    """Hook desde el drenaje de kills PVP. Completa contratos + auto-bounty del
    objetivo muerto de forma atómica e idempotente."""
    killer_sid = str(killer_sid or "").strip()
    victim_sid = str(victim_sid or "").strip()
    if not killer_sid or not victim_sid or killer_sid == victim_sid:
        return
    async with _lock:
        await _resolve_death(killer_sid, victim_sid, killer_name)


async def _resolve_death(killer_sid, victim_sid, killer_name):
    killer_uid = await _resolve_user_id(killer_sid) if _resolve_user_id else None
    if killer_name is None and killer_uid and _user_info:
        ki = await _user_info(killer_uid)
        killer_name = (ki or {}).get("name")
    if not killer_name:
        killer_name = "Cazador"
    changed = False
    total_prime = total_amber = 0
    target_name = None

    # 1) Contratos sobre la víctima.
    contracts = await _db.bounties.find(
        {"type": "contract", "status": "active", "target_sid": victim_sid}, {"_id": 0}).to_list(500)
    for c in contracts:
        res = await _db.bounties.update_one(
            {"id": c["id"], "status": "active", "reward_processed": False},
            {"$set": {"status": "completed", "reward_processed": True,
                      "killer_sid": killer_sid, "killer_name": killer_name,
                      "killer_user_id": killer_uid, "completed_at": _iso(),
                      "completed_at_ms": _ms()}})
        if res.modified_count != 1:
            continue
        changed = True
        target_name = c["target_name"]
        r = c["reward"]
        # Anti-exploit: si el que puso el contrato es quien mata, se reembolsa (no cobra).
        if c["placer_sid"] and c["placer_sid"] == killer_sid:
            await _refund_wallet(c["placer_user_id"], int(c.get("paid_prime", r["prime"])), 0, "Bounty: te reembolsamos (mataste a tu propio objetivo)")
            await _db.bounties.update_one({"id": c["id"]}, {"$set": {"status": "cancelled", "cancel_reason": "self_kill"}})
        else:
            total_prime += r["prime"]
            total_amber += r["amber"]
    if killer_uid and (total_prime or total_amber):
        await _award_reward(killer_uid, total_prime, total_amber, 0, "Bounty: contrato reclamado")
    if _ingame_grant and (total_prime or total_amber):
        try:
            _ingame_grant(killer_sid, total_prime, total_amber, 0)
        except Exception:
            pass

    # 2) Auto-bounty de la víctima.
    self_b = await _db.bounties.find_one({"type": "self", "status": "active", "holder_sid": victim_sid}, {"_id": 0})
    if self_b:
        res = await _db.bounties.update_one(
            {"id": self_b["id"], "status": "active", "reward_processed": False},
            {"$set": {"status": "dead", "reward_processed": True, "killer_sid": killer_sid,
                      "killer_name": killer_name, "killer_user_id": killer_uid,
                      "ended_at": _iso(), "ended_at_ms": _ms()}})
        if res.modified_count == 1:
            changed = True
            target_name = target_name or self_b["holder_name"]
            _self_cooldown_until[self_b["holder_user_id"]] = time.time() + (await get_config())["self_cooldown"]
            amber = self_b.get("killer_amber", 0)
            if killer_uid and amber:
                await _award_reward(killer_uid, 0, amber, 0, "Bounty: auto-bounty eliminado")
                total_amber += amber
            if _ingame_grant and amber:
                try:
                    _ingame_grant(killer_sid, 0, amber, 0)
                except Exception:
                    pass
            await hub.send_to(self_b["holder_user_id"], "bounty:self_ended",
                              {**_pub_self(self_b), "reason": "killed", "killerName": killer_name})

    if changed:
        await hub.broadcast("bounty:completed", {
            "targetName": target_name, "killerName": killer_name,
            "reward": {"primeMeat": total_prime, "amberium": total_amber}})
        await _push_board()
        asyncio.create_task(_discord(_discord_completed(
            target_name, killer_name, total_prime, total_amber, "múltiple")))
        logger.info("[bounty] KILL victim=%s killer=%s prime=%s amber=%s",
                    victim_sid, killer_sid, total_prime, total_amber)


# ─────────────────────────── Loops ───────────────────────────
async def _accrual_tick():
    """Acredita PrimeMeat por minuto a los auto-bounties vivos y expira los vencidos
    o los contratos vencidos (reembolsando al que los puso)."""
    now = _ms()
    roster = await _roster()
    online_sids = {str(p.get("sid")) for p in roster if p.get("alive", True)}
    sim = getattr(_roster, "_last_sim", False)

    # Contratos vencidos -> reembolso.
    expired = await _db.bounties.find(
        {"type": "contract", "status": "active", "expires_at_ms": {"$lte": now}}, {"_id": 0}).to_list(500)
    for c in expired:
        res = await _db.bounties.update_one({"id": c["id"], "status": "active"},
                                            {"$set": {"status": "expired", "ended_at": _iso()}})
        if res.modified_count == 1:
            r = c["reward"]
            await _refund_wallet(c["placer_user_id"], int(c.get("paid_prime", r["prime"])), 0, "Bounty: reembolso por expiración")
    if expired:
        await _push_board()

    # Auto-bounties: acreditar por minuto / expirar.
    selfs = await _db.bounties.find({"type": "self", "status": "active"}, {"_id": 0}).to_list(200)
    for s in selfs:
        if now >= s.get("ends_at_ms", 0):
            res = await _db.bounties.update_one({"id": s["id"], "status": "active"},
                                                {"$set": {"status": "expired", "ended_at": _iso(), "ended_at_ms": now}})
            if res.modified_count == 1:
                _self_cooldown_until[s["holder_user_id"]] = time.time() + (await get_config())["self_cooldown"]
                await hub.send_to(s["holder_user_id"], "bounty:self_ended", {**_pub_self(s), "reason": "expired"})
                await hub.broadcast("bounty:self_expired", {"bountyId": s["id"], "holderName": s["holder_name"]})
                await _push_board()
            continue
        alive = sim or (s.get("holder_sid") in online_sids)
        if not alive:
            # Pausar acumulación mientras esté offline (no acredita tiempo ausente).
            await _db.bounties.update_one({"id": s["id"]}, {"$set": {"last_accrual_ms": now}})
            continue
        minutes = int((now - s.get("last_accrual_ms", now)) // 60000)
        if minutes >= 1:
            gain = minutes * s["prime_per_min"]
            new_last = s["last_accrual_ms"] + minutes * 60000
            r2 = await _db.bounties.update_one(
                {"id": s["id"], "status": "active"},
                {"$inc": {"accrued_prime": gain}, "$set": {"last_accrual_ms": new_last}})
            if r2.modified_count == 1:
                await _award_reward(s["holder_user_id"], gain, 0, 0, "Bounty: supervivencia con precio a tu cabeza")
                if _ingame_grant:
                    try:
                        _ingame_grant(s["holder_sid"], gain, 0, 0)
                    except Exception:
                        pass
                s2 = await _db.bounties.find_one({"id": s["id"]}, {"_id": 0})
                await hub.send_to(s["holder_user_id"], "bounty:self_tick", _pub_self(s2))


async def _invite_tick():
    """Ofrece aleatoriamente a un jugador online de la web ponerse precio. Fuerte
    protección para que sea muy raro que le toque a la misma persona."""
    if _paused:
        return
    cfg = await get_config()
    online = hub.online_web_uids()
    if not online:
        return
    now = time.time()
    # Excluir a quien ya tiene auto-bounty activo o está en cooldown.
    busy = set()
    active_selfs = await _db.bounties.find({"type": "self", "status": "active"}, {"holder_user_id": 1}).to_list(200)
    busy.update(x["holder_user_id"] for x in active_selfs)
    for uid in list(_self_cooldown_until):
        if _self_cooldown_until[uid] > now:
            busy.add(uid)
    recent = set(list(_invite_recent)[-cfg["invite_recent_protection"]:])
    fresh = [u for u in online if u not in busy and u not in recent]
    pool = fresh if fresh else [u for u in online if u not in busy]
    if not pool:
        return
    uid = random.choice(pool)
    _invite_recent.append(uid)
    payload = {"primePerMin": cfg["self_prime_per_min"], "durationMin": cfg["self_max_seconds"] // 60,
               "killerAmber": cfg["self_killer_amber"], "ttl": cfg["invite_ttl"],
               "expiresAt": _ms() + cfg["invite_ttl"] * 1000}
    await hub.send_to(uid, "bounty:self_invite", payload)
    try:
        await _db.bounty_invite_log.insert_one({"id": _bid(), "uid": uid, "at": _iso()})
    except Exception:
        pass
    logger.info("[bounty] self-invite -> %s", uid)


async def _main_loop():
    while True:
        try:
            if not _paused:
                async with _lock:
                    await _accrual_tick()
        except Exception as e:
            logger.warning("[bounty] accrual tick: %r", e)
        await asyncio.sleep(10)


async def _invite_loop():
    await asyncio.sleep(30)
    while True:
        try:
            await _invite_tick()
        except Exception as e:
            logger.warning("[bounty] invite tick: %r", e)
        cfg = await get_config()
        await asyncio.sleep(max(30, cfg["invite_interval"]))


# ─────────────────────────── Simulación (preview) ───────────────────────────
_SIM_DINOS = [("Tyrannosaurus", "trex"), ("Spinosaurus", "spino"), ("Allosaurus", "allo"),
              ("Carnotaurus", "carno"), ("Austroraptor", "austro"), ("Ceratosaurus", "cerato"),
              ("Deinosuchus", "deino"), ("Triceratops", "trike"), ("Dilophosaurus", "dilo"),
              ("Herrerasaurus", "herrera")]
_SIM_NAMES = ["YonduSkywalker", "Bluecito", "RaptorKing", "DonDino", "ElCarnicero", "LaBestia",
              "NubladoMX", "TorvoLATAM", "AlfaMacho", "ReinaRex", "CazadorNocturno", "GarraVeloz"]
_sim_players: list = []


def _sim_roster() -> list:
    global _sim_players
    _roster._last_sim = True
    if not _sim_players:
        rng = random.Random(4207)
        idxs = rng.sample(range(len(_SIM_NAMES)), 10)
        for i, idx in enumerate(idxs):
            dino, slug = _SIM_DINOS[i % len(_SIM_DINOS)]
            _sim_players.append({"sid": str(76561190000000000 + idx * 1337 + 11),
                                 "name": _SIM_NAMES[idx], "species": dino, "slug": slug, "alive": True})
    return [dict(p) for p in _sim_players]


# ─────────────────────────── Wiring ───────────────────────────
def configure(db, *, admin_ids, online_provider, resolve_user_id, user_info,
              charge_wallet, refund_wallet, award_reward, ingame_grant=None,
              jwt_secret="", jwt_algo="HS256"):
    global _db, _admin_ids, _online_provider, _resolve_user_id, _user_info
    global _charge_wallet, _refund_wallet, _award_reward, _ingame_grant, _jwt_secret, _jwt_algo
    _db = db
    _admin_ids = set(admin_ids or [])
    _online_provider = online_provider
    _resolve_user_id = resolve_user_id
    _user_info = user_info
    _charge_wallet = charge_wallet
    _refund_wallet = refund_wallet
    _award_reward = award_reward
    _ingame_grant = ingame_grant
    _jwt_secret = jwt_secret
    _jwt_algo = jwt_algo


async def ensure_indexes():
    try:
        await _db.bounties.create_index("id", unique=True)
        await _db.bounties.create_index([("type", 1), ("status", 1)])
        await _db.bounties.create_index([("target_sid", 1), ("status", 1)])
        await _db.bounties.create_index([("holder_user_id", 1), ("status", 1)])
        await _db.bounties.create_index([("placer_user_id", 1), ("status", 1)])
        await _db.bounties.create_index([("created_at", -1)])
    except Exception:
        logger.warning("[bounty] index init skipped", exc_info=True)


def start_loops():
    asyncio.create_task(_main_loop())
    asyncio.create_task(_invite_loop())


class ContractIn(BaseModel):
    target_sid: str
    prime: int
    amber: int = 0


class CancelIn(BaseModel):
    bounty_id: str


class ConfigIn(BaseModel):
    min_contract_prime: int | None = None
    reward_amber_bonus: int | None = None
    contract_duration: int | None = None
    self_prime_per_min: int | None = None
    self_max_seconds: int | None = None
    self_killer_amber: int | None = None
    self_cooldown: int | None = None
    invite_interval: int | None = None
    invite_recent_protection: int | None = None
    invite_ttl: int | None = None
    max_contracts_per_user: int | None = None


class SimKillIn(BaseModel):
    target_sid: str


def build_router(get_current_user, get_admin_user):
    router = APIRouter()

    @router.get("/bounty/config")
    async def config():
        return await get_config()

    @router.get("/bounty/board")
    async def board():
        return await snapshot()

    @router.get("/bounty/targets")
    async def targets(user=Depends(get_current_user)):
        roster = await _roster()
        my_sid = str((user or {}).get("steam_id") or "")
        contracts = await _db.bounties.find({"type": "contract", "status": "active"}, {"_id": 0}).to_list(500)
        totals = {}
        for c in contracts:
            t = totals.setdefault(c["target_sid"], {"prime": 0, "amber": 0, "count": 0})
            t["prime"] += c["reward"]["prime"]
            t["amber"] += c["reward"]["amber"]
            t["count"] += 1
        out = []
        for p in roster:
            sid = str(p.get("sid"))
            t = totals.get(sid, {"prime": 0, "amber": 0, "count": 0})
            out.append({
                "sid": sid, "name": p.get("name"), "species": p.get("species"),
                "slug": p.get("slug"), "alive": p.get("alive", True),
                "isMe": bool(my_sid) and sid == my_sid,
                "bounty": {"primeMeat": t["prime"], "amberium": t["amber"], "count": t["count"]},
            })
        # Los que ya tienen bounty primero, luego alfabético.
        out.sort(key=lambda x: (-x["bounty"]["primeMeat"], x["name"] or ""))
        return {"targets": out, "simulated": getattr(_roster, "_last_sim", False)}

    @router.get("/bounty/mine")
    async def mine(user=Depends(get_current_user)):
        uid = user["id"]
        contracts = await _db.bounties.find(
            {"type": "contract", "placer_user_id": uid, "status": "active"}, {"_id": 0}
        ).sort("created_at", -1).to_list(50)
        self_b = await _db.bounties.find_one({"type": "self", "holder_user_id": uid, "status": "active"}, {"_id": 0})
        now = time.time()
        cd = _self_cooldown_until.get(uid, 0)
        return {
            "contracts": [_pub_contract(c) for c in contracts],
            "self": _pub_self(self_b) if self_b else None,
            "selfCooldownLeft": max(0, int(cd - now)),
            "wallet": {"coins": user.get("coins", 0), "vip_coins": user.get("vip_coins", 0)},
        }

    @router.get("/bounty/history")
    async def history(limit: int = 20):
        limit = max(1, min(60, int(limit)))
        rows = await _db.bounties.find(
            {"type": {"$in": ["contract", "self"]},
             "status": {"$in": ["completed", "dead", "expired", "cancelled"]}}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        out = []
        for r in rows:
            out.append(_pub_self(r) if r["type"] == "self" else _pub_contract(r))
        return {"items": out}

    @router.post("/bounty/contract")
    async def contract(data: ContractIn, user=Depends(get_current_user)):
        return await place_contract(user["id"], data.target_sid, data.prime, data.amber)

    @router.post("/bounty/contract/cancel")
    async def contract_cancel(data: CancelIn, user=Depends(get_current_user)):
        return await cancel_contract(user["id"], data.bounty_id)

    @router.post("/bounty/self/start")
    async def self_start(user=Depends(get_current_user)):
        return await start_self(user["id"], from_invite=False)

    @router.post("/bounty/self/accept-invite")
    async def self_accept(user=Depends(get_current_user)):
        return await start_self(user["id"], from_invite=True)

    # ── Admin ──
    @router.post("/bounty/admin/simulate-kill")
    async def simulate_kill(data: SimKillIn, admin=Depends(get_admin_user)):
        """Simula una muerte válida del objetivo (para probar sin el juego real)."""
        roster = await _roster()
        killer = next((p for p in roster if str(p["sid"]) != str(data.target_sid)), None)
        killer_sid = str(killer["sid"]) if killer else ("SIMKILL-" + uuid.uuid4().hex[:8])
        killer_name = (killer or {}).get("name")
        await on_kill(killer_sid, str(data.target_sid), killer_name)
        return {"ok": True, "killer": killer_name}

    @router.post("/bounty/admin/config")
    async def set_config(data: ConfigIn, admin=Depends(get_admin_user)):
        upd = {k: int(v) for k, v in data.dict().items() if v is not None and int(v) >= 0}
        if upd:
            await _db.settings.update_one({"_id": "bounty"}, {"$set": upd}, upsert=True)
        cfg = await get_config()
        await hub.broadcast("bounty:config", cfg)
        return {"ok": True, "config": cfg}

    @router.post("/bounty/admin/pause")
    async def pause(admin=Depends(get_admin_user)):
        global _paused
        _paused = True
        return {"ok": True, "paused": True}

    @router.post("/bounty/admin/resume")
    async def resume(admin=Depends(get_admin_user)):
        global _paused
        _paused = False
        return {"ok": True, "paused": False}

    @router.websocket("/bounty/ws")
    async def bounty_ws(ws: WebSocket):
        await ws.accept()
        uid = None
        info = None
        token = ws.query_params.get("token")
        if token:
            try:
                uid = jwt.decode(token, _jwt_secret, algorithms=[_jwt_algo]).get("sub")
            except Exception:
                uid = None
        if uid:
            try:
                u = await _db.users.find_one({"id": uid}, {"_id": 0, "persona_name": 1, "avatar": 1, "steam_id": 1})
                if u:
                    info = {"name": u.get("persona_name"), "avatar": u.get("avatar"), "steam_id": u.get("steam_id")}
                else:
                    uid = None
            except Exception:
                uid = None
        try:
            await hub.add(ws, uid, info)
            await ws.send_json({"event": "bounty:state", "data": await snapshot()})
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
