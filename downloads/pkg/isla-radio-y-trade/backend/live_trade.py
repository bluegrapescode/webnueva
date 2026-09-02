"""Trade en Vivo (P2P, cara a cara) — sesiones interactivas en tiempo real.

Self-contained (like skin_shop.py / crash_game.py): server.py hands in the Mongo
handle, JWT secret and the auth dependency via build_router(...).

Model in one line each:
  - Hub: WebSocket presence (who is online on the trades tab) + per-user push.
  - Session: two mirrored offers, a lock+confirm handshake, atomic swap on both
    confirmed. Any offer edit resets BOTH locks (BG3 barter behaviour).
  - Rules: the ONLY tradeable currency is Amberium (vip_coins), capped at 1000
    SENT per user per calendar day. Every inventory item EXCEPT dinosaurs is
    tradeable. A trade that moves any non-amberium item puts both users on a
    3h cooldown; amberium-only trades have no cooldown (just the daily cap).

Collections: trade_sessions, trade_log. User fields: trade_amber_day,
trade_amber_sent, last_item_trade_at.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger("live_trade")

AMBER_DAILY_CAP = 1000
ITEM_COOLDOWN_SECS = 3 * 3600
UNTRADEABLE_CATEGORIES = {"Dinosaurs"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _now().isoformat()


def _nid() -> str:
    return uuid.uuid4().hex


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def _parse(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ─────────────────────────── Hub (presence + push) ───────────────────────────
class TradeHub:
    def __init__(self):
        # user_id -> {"wss": set(ws), "name": str, "avatar": str}
        self.users: dict = {}
        self.ws_user: dict = {}  # ws -> user_id

    async def add(self, ws, user_id, name, avatar):
        self.ws_user[ws] = user_id
        u = self.users.get(user_id)
        if u:
            u["wss"].add(ws)
        else:
            self.users[user_id] = {"wss": {ws}, "name": name, "avatar": avatar}
        await self.broadcast_presence()

    async def remove(self, ws):
        uid = self.ws_user.pop(ws, None)
        if uid and uid in self.users:
            self.users[uid]["wss"].discard(ws)
            if not self.users[uid]["wss"]:
                self.users.pop(uid, None)
        await self.broadcast_presence()

    def online_list(self, exclude: str = ""):
        return [
            {"user_id": uid, "name": u["name"], "avatar": u["avatar"]}
            for uid, u in self.users.items() if uid != exclude
        ]

    def is_online(self, user_id: str) -> bool:
        return user_id in self.users

    async def push(self, user_id: str, payload: dict):
        u = self.users.get(user_id)
        if not u:
            return
        dead = []
        for ws in list(u["wss"]):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            u["wss"].discard(ws)

    async def broadcast_presence(self):
        for uid, u in list(self.users.items()):
            payload = {"type": "presence", "online": self.online_list(exclude=uid)}
            for ws in list(u["wss"]):
                try:
                    await ws.send_json(payload)
                except Exception:
                    pass


hub = TradeHub()
_locks: dict = {}


def _slock(session_id: str) -> asyncio.Lock:
    lk = _locks.get(session_id)
    if lk is None:
        lk = asyncio.Lock()
        _locks[session_id] = lk
    return lk


# ─────────────────────────── I/O ───────────────────────────
class OfferItem(BaseModel):
    inv_id: str
    qty: int = Field(ge=1)


class InviteIn(BaseModel):
    to_user_id: str


class RespondIn(BaseModel):
    session_id: str
    accept: bool


class OfferIn(BaseModel):
    session_id: str
    items: List[OfferItem] = []
    amber: int = Field(default=0, ge=0)


class SessionRef(BaseModel):
    session_id: str


class LockIn(BaseModel):
    session_id: str
    locked: bool


# ─────────────────────────── Router factory ───────────────────────────
def build_router(db, jwt_secret: str, get_current_user, add_log, jwt_algo: str = "HS256"):
    router = APIRouter()

    async def ensure_indexes():
        try:
            await db.trade_sessions.create_index("id", unique=True)
            await db.trade_sessions.create_index([("a_id", 1), ("status", 1)])
            await db.trade_sessions.create_index([("b_id", 1), ("status", 1)])
            await db.trade_log.create_index("created_at")
        except Exception:
            logger.warning("[trade] index init skipped", exc_info=True)

    # -------- helpers --------
    def _item_view(doc: dict) -> dict:
        return {
            "inv_id": doc["id"], "item_id": doc.get("item_id"), "name": doc.get("name"),
            "category": doc.get("category"), "rarity": doc.get("rarity"),
            "image": doc.get("image"), "tier": doc.get("tier"),
            "quantity": int(doc.get("quantity", 1)),
        }

    async def _tradeable_inventory(user_id: str) -> list:
        cur = db.inventory.find(
            {"user_id": user_id, "category": {"$nin": list(UNTRADEABLE_CATEGORIES)}}, {"_id": 0})
        return [_item_view(d) for d in await cur.to_list(1000)]

    async def _amber_state(user: dict) -> dict:
        day = user.get("trade_amber_day")
        sent = int(user.get("trade_amber_sent", 0)) if day == _today() else 0
        return {"balance": int(user.get("vip_coins", 0)), "sent_today": sent,
                "daily_cap": AMBER_DAILY_CAP, "remaining_today": max(0, AMBER_DAILY_CAP - sent)}

    def _cooldown_left(user: dict) -> int:
        last = _parse(user.get("last_item_trade_at"))
        if not last:
            return 0
        left = ITEM_COOLDOWN_SECS - (_now() - last).total_seconds()
        return int(left) if left > 0 else 0

    def _public(sess: dict, viewer_id: str) -> dict:
        me_is_a = sess["a_id"] == viewer_id
        mine = sess["a_offer"] if me_is_a else sess["b_offer"]
        theirs = sess["b_offer"] if me_is_a else sess["a_offer"]
        return {
            "session_id": sess["id"], "status": sess["status"],
            "me": {
                "offer": mine, "locked": sess["a_locked"] if me_is_a else sess["b_locked"],
                "confirmed": sess["a_confirmed"] if me_is_a else sess["b_confirmed"],
                "user_id": viewer_id,
            },
            "them": {
                "offer": theirs, "locked": sess["b_locked"] if me_is_a else sess["a_locked"],
                "confirmed": sess["b_confirmed"] if me_is_a else sess["a_confirmed"],
                "user_id": sess["b_id"] if me_is_a else sess["a_id"],
                "name": sess["b_name"] if me_is_a else sess["a_name"],
                "avatar": sess["b_avatar"] if me_is_a else sess["a_avatar"],
            },
        }

    async def _push_state(sess: dict):
        await hub.push(sess["a_id"], {"type": "trade_state", "state": _public(sess, sess["a_id"])})
        await hub.push(sess["b_id"], {"type": "trade_state", "state": _public(sess, sess["b_id"])})

    async def _active_for(user_id: str):
        return await db.trade_sessions.find_one(
            {"status": {"$in": ["invited", "active"]},
             "$or": [{"a_id": user_id}, {"b_id": user_id}]}, {"_id": 0})

    def _side_key(sess, user_id):
        return "a" if sess["a_id"] == user_id else "b"

    async def _validate_offer_items(user_id: str, items: List[OfferItem]) -> list:
        """Returns normalised item snapshots; raises if the user can't back them."""
        out = []
        for it in items:
            doc = await db.inventory.find_one({"id": it.inv_id, "user_id": user_id}, {"_id": 0})
            if not doc:
                raise HTTPException(status_code=400, detail="No tienes uno de los objetos ofrecidos")
            if doc.get("category") in UNTRADEABLE_CATEGORIES:
                raise HTTPException(status_code=400, detail="Los dinosaurios no se intercambian aquí")
            if int(doc.get("quantity", 1)) < it.qty:
                raise HTTPException(status_code=400, detail=f"No tienes suficientes de {doc.get('name')}")
            snap = _item_view(doc)
            snap["qty"] = it.qty
            out.append(snap)
        return out

    # -------- inventory transfer (conditional, rollback-safe) --------
    async def _dec_item(user_id: str, inv_id: str, qty: int) -> Optional[dict]:
        doc = await db.inventory.find_one({"id": inv_id, "user_id": user_id}, {"_id": 0})
        if not doc or int(doc.get("quantity", 1)) < qty:
            return None
        res = await db.inventory.update_one(
            {"id": inv_id, "user_id": user_id, "quantity": {"$gte": qty}},
            {"$inc": {"quantity": -qty}})
        if res.modified_count != 1:
            return None
        await db.inventory.delete_one({"id": inv_id, "user_id": user_id, "quantity": {"$lte": 0}})
        return doc

    async def _add_item(user_id: str, snap: dict, qty: int):
        match = {"user_id": user_id, "category": snap.get("category"), "item_id": snap.get("item_id")}
        if snap.get("tier") is not None:
            match["tier"] = snap.get("tier")
        existing = await db.inventory.find_one(match)
        if existing:
            await db.inventory.update_one({"id": existing["id"]},
                                          {"$inc": {"quantity": qty}, "$set": {"acquired_at": _iso()}})
        else:
            await db.inventory.insert_one({
                "id": _nid(), "user_id": user_id, "item_id": snap.get("item_id"),
                "name": snap.get("name"), "category": snap.get("category"),
                "rarity": snap.get("rarity"), "image": snap.get("image"),
                "tier": snap.get("tier"), "quantity": qty, "acquired_at": _iso(),
            })

    async def _execute(sess: dict) -> dict:
        a_id, b_id = sess["a_id"], sess["b_id"]
        ua = await db.users.find_one({"id": a_id}, {"_id": 0})
        ub = await db.users.find_one({"id": b_id}, {"_id": 0})
        if not ua or not ub:
            raise HTTPException(status_code=400, detail="Usuario no encontrado")
        a_off, b_off = sess["a_offer"], sess["b_offer"]
        has_item = bool(a_off["items"] or b_off["items"])

        # cooldown (only when a non-amber item moves)
        if has_item:
            for u, who in ((ua, ua.get("persona_name")), (ub, ub.get("persona_name"))):
                if _cooldown_left(u) > 0:
                    raise HTTPException(status_code=429, detail=f"{who} está en cooldown de intercambio (3h)")

        # amber caps + balance (per SENDER)
        for u, off in ((ua, a_off), (ub, b_off)):
            amt = int(off.get("amber", 0))
            if amt <= 0:
                continue
            if int(u.get("vip_coins", 0)) < amt:
                raise HTTPException(status_code=400, detail=f"{u.get('persona_name')} no tiene suficientes Amberiums")
            day = u.get("trade_amber_day")
            sent = int(u.get("trade_amber_sent", 0)) if day == _today() else 0
            if sent + amt > AMBER_DAILY_CAP:
                raise HTTPException(status_code=400, detail=f"{u.get('persona_name')} supera el límite diario de 1000 Amberiums")

        # ---- move items with rollback ----
        moved = []  # (owner_id, snap, qty) already decremented
        try:
            for off, owner in ((a_off, a_id), (b_off, b_id)):
                for it in off["items"]:
                    doc = await _dec_item(owner, it["inv_id"], it["qty"])
                    if not doc:
                        raise HTTPException(status_code=409, detail="El inventario cambió, intento cancelado")
                    moved.append((owner, _item_view(doc), it["qty"]))
        except HTTPException:
            for owner, snap, qty in moved:  # restore
                await _add_item(owner, snap, qty)
            raise
        # deliver items to the other side
        for off, owner, other in ((a_off, a_id, b_id), (b_off, b_id, a_id)):
            for it in off["items"]:
                await _add_item(other, it, it["qty"])

        # ---- amber ----
        for u, off, other in ((ua, a_off, b_id), (ub, b_off, a_id)):
            amt = int(off.get("amber", 0))
            if amt <= 0:
                continue
            day = u.get("trade_amber_day")
            sent = int(u.get("trade_amber_sent", 0)) if day == _today() else 0
            await db.users.update_one({"id": u["id"]}, {
                "$inc": {"vip_coins": -amt},
                "$set": {"trade_amber_day": _today(), "trade_amber_sent": sent + amt}})
            await db.users.update_one({"id": other}, {"$inc": {"vip_coins": amt}})

        # ---- cooldown stamp ----
        if has_item:
            await db.users.update_many({"id": {"$in": [a_id, b_id]}},
                                       {"$set": {"last_item_trade_at": _iso()}})

        await db.trade_log.insert_one({
            "id": _nid(), "a_id": a_id, "b_id": b_id,
            "a_name": sess.get("a_name"), "b_name": sess.get("b_name"),
            "a_avatar": sess.get("a_avatar"), "b_avatar": sess.get("b_avatar"),
            "a_offer": a_off, "b_offer": b_off, "created_at": _iso()})
        return {"a_offer": a_off, "b_offer": b_off}

    # ============ endpoints ============
    @router.get("/trade/online")
    async def online(user=Depends(get_current_user)):
        return {"online": hub.online_list(exclude=user["id"])}

    @router.get("/trade/inventory")
    async def inventory(user=Depends(get_current_user)):
        fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        return {
            "items": await _tradeable_inventory(user["id"]),
            "amber": await _amber_state(fresh),
            "cooldown_left": _cooldown_left(fresh),
        }

    @router.get("/trade/active")
    async def active(user=Depends(get_current_user)):
        sess = await _active_for(user["id"])
        return {"session": _public(sess, user["id"]) if sess else None}

    @router.get("/trade/peer/{session_id}")
    async def peer_inventory(session_id: str, user=Depends(get_current_user)):
        sess = await db.trade_sessions.find_one({"id": session_id}, {"_id": 0})
        if not sess or user["id"] not in (sess["a_id"], sess["b_id"]):
            raise HTTPException(status_code=404, detail="Sesión no válida")
        other = sess["b_id"] if sess["a_id"] == user["id"] else sess["a_id"]
        ou = await db.users.find_one({"id": other}, {"_id": 0, "vip_coins": 1})
        return {"items": await _tradeable_inventory(other), "amber_balance": int((ou or {}).get("vip_coins", 0))}

    @router.get("/trade/history")
    async def history(user=Depends(get_current_user)):
        uid = user["id"]
        cur = db.trade_log.find({"$or": [{"a_id": uid}, {"b_id": uid}]}, {"_id": 0}).sort("created_at", -1).limit(100)
        rows = await cur.to_list(100)
        out = []
        for r in rows:
            me_is_a = r["a_id"] == uid
            gave = r["a_offer"] if me_is_a else r["b_offer"]
            got = r["b_offer"] if me_is_a else r["a_offer"]
            out.append({
                "id": r["id"], "created_at": r["created_at"],
                "partner_name": (r.get("b_name") if me_is_a else r.get("a_name")) or "Jugador",
                "partner_avatar": (r.get("b_avatar") if me_is_a else r.get("a_avatar")),
                "gave": {"items": gave.get("items", []), "amber": gave.get("amber", 0)},
                "received": {"items": got.get("items", []), "amber": got.get("amber", 0)},
            })
        return {"trades": out}

    @router.post("/trade/invite")
    async def invite(data: InviteIn, user=Depends(get_current_user)):
        target_id = data.to_user_id
        if target_id == user["id"]:
            raise HTTPException(status_code=400, detail="No puedes intercambiar contigo mismo")
        if not hub.is_online(target_id):
            raise HTTPException(status_code=400, detail="Ese jugador no está en línea")
        if await _active_for(user["id"]):
            raise HTTPException(status_code=400, detail="Ya tienes una sesión de intercambio abierta")
        if await _active_for(target_id):
            raise HTTPException(status_code=400, detail="Ese jugador ya está en un intercambio")
        target = await db.users.find_one({"id": target_id}, {"_id": 0, "persona_name": 1, "avatar": 1})
        if not target:
            raise HTTPException(status_code=404, detail="Jugador no encontrado")
        sess = {
            "id": _nid(), "a_id": user["id"], "a_name": user.get("persona_name"), "a_avatar": user.get("avatar"),
            "b_id": target_id, "b_name": target.get("persona_name"), "b_avatar": target.get("avatar"),
            "a_offer": {"items": [], "amber": 0}, "b_offer": {"items": [], "amber": 0},
            "a_locked": False, "b_locked": False, "a_confirmed": False, "b_confirmed": False,
            "status": "invited", "created_at": _iso(), "updated_at": _iso(),
        }
        await db.trade_sessions.insert_one(dict(sess))
        await hub.push(target_id, {"type": "trade_invite", "session_id": sess["id"],
                                   "from": {"user_id": user["id"], "name": user.get("persona_name"), "avatar": user.get("avatar")}})
        return {"session_id": sess["id"], "status": "invited"}

    @router.post("/trade/respond")
    async def respond(data: RespondIn, user=Depends(get_current_user)):
        async with _slock(data.session_id):
            sess = await db.trade_sessions.find_one({"id": data.session_id}, {"_id": 0})
            if not sess or sess["b_id"] != user["id"] or sess["status"] != "invited":
                raise HTTPException(status_code=404, detail="Invitación no válida")
            if not data.accept:
                await db.trade_sessions.update_one({"id": sess["id"]}, {"$set": {"status": "cancelled", "updated_at": _iso()}})
                await hub.push(sess["a_id"], {"type": "trade_declined", "session_id": sess["id"], "by": user.get("persona_name")})
                return {"status": "cancelled"}
            await db.trade_sessions.update_one({"id": sess["id"]}, {"$set": {"status": "active", "updated_at": _iso()}})
            sess["status"] = "active"
            await hub.push(sess["a_id"], {"type": "trade_start", "state": _public(sess, sess["a_id"])})
            await hub.push(sess["b_id"], {"type": "trade_start", "state": _public(sess, sess["b_id"])})
            return {"status": "active"}

    @router.post("/trade/offer")
    async def set_offer(data: OfferIn, user=Depends(get_current_user)):
        async with _slock(data.session_id):
            sess = await db.trade_sessions.find_one({"id": data.session_id}, {"_id": 0})
            if not sess or sess["status"] != "active" or user["id"] not in (sess["a_id"], sess["b_id"]):
                raise HTTPException(status_code=404, detail="Sesión no válida")
            snaps = await _validate_offer_items(user["id"], data.items)
            if data.amber > 0:
                st = await _amber_state(await db.users.find_one({"id": user["id"]}, {"_id": 0}))
                if data.amber > st["balance"]:
                    raise HTTPException(status_code=400, detail="No tienes suficientes Amberiums")
                if data.amber > st["remaining_today"]:
                    raise HTTPException(status_code=400, detail=f"Te quedan {st['remaining_today']} Amberiums por hoy (límite 1000)")
            side = _side_key(sess, user["id"])
            other_side = "b" if side == "a" else "a"
            other_was_locked = sess[f"{other_side}_locked"]
            # editing an offer resets BOTH locks & confirms
            await db.trade_sessions.update_one({"id": sess["id"]}, {"$set": {
                f"{side}_offer": {"items": [{"inv_id": s["inv_id"], "qty": s["qty"], "item_id": s.get("item_id"),
                                             "name": s["name"], "image": s["image"], "category": s["category"],
                                             "rarity": s["rarity"], "tier": s["tier"]} for s in snaps], "amber": int(data.amber)},
                "a_locked": False, "b_locked": False, "a_confirmed": False, "b_confirmed": False,
                "updated_at": _iso()}})
            fresh = await db.trade_sessions.find_one({"id": sess["id"]}, {"_id": 0})
            await _push_state(fresh)
            # anti-scam: if the OTHER player had already locked, alert them loudly
            if other_was_locked:
                other_id = sess["b_id"] if side == "a" else sess["a_id"]
                await hub.push(other_id, {"type": "trade_offer_changed", "by": user.get("persona_name")})
            return {"ok": True}

    @router.post("/trade/lock")
    async def lock(data: LockIn, user=Depends(get_current_user)):
        async with _slock(data.session_id):
            sess = await db.trade_sessions.find_one({"id": data.session_id}, {"_id": 0})
            if not sess or sess["status"] != "active" or user["id"] not in (sess["a_id"], sess["b_id"]):
                raise HTTPException(status_code=404, detail="Sesión no válida")
            side = _side_key(sess, user["id"])
            upd = {f"{side}_locked": bool(data.locked), "updated_at": _iso()}
            if not data.locked:
                upd["a_confirmed"] = False
                upd["b_confirmed"] = False
            await db.trade_sessions.update_one({"id": sess["id"]}, {"$set": upd})
            fresh = await db.trade_sessions.find_one({"id": sess["id"]}, {"_id": 0})
            await _push_state(fresh)
            return {"ok": True}

    @router.post("/trade/confirm")
    async def confirm(data: SessionRef, user=Depends(get_current_user)):
        async with _slock(data.session_id):
            sess = await db.trade_sessions.find_one({"id": data.session_id}, {"_id": 0})
            if not sess or sess["status"] != "active" or user["id"] not in (sess["a_id"], sess["b_id"]):
                raise HTTPException(status_code=404, detail="Sesión no válida")
            if not (sess["a_locked"] and sess["b_locked"]):
                raise HTTPException(status_code=400, detail="Ambos deben bloquear la oferta antes de confirmar")
            side = _side_key(sess, user["id"])
            await db.trade_sessions.update_one({"id": sess["id"]}, {"$set": {f"{side}_confirmed": True, "updated_at": _iso()}})
            sess = await db.trade_sessions.find_one({"id": sess["id"]}, {"_id": 0})
            if sess["a_confirmed"] and sess["b_confirmed"]:
                try:
                    result = await _execute(sess)
                except HTTPException as e:
                    # abort the session cleanly and tell both
                    await db.trade_sessions.update_one({"id": sess["id"]}, {"$set": {"status": "cancelled", "updated_at": _iso(), "error": e.detail}})
                    for uid in (sess["a_id"], sess["b_id"]):
                        await hub.push(uid, {"type": "trade_error", "session_id": sess["id"], "detail": e.detail})
                    raise
                await db.trade_sessions.update_one({"id": sess["id"]}, {"$set": {"status": "completed", "updated_at": _iso()}})
                await add_log(user.get("persona_name"), "live_trade_complete", sess["id"],
                              {"a": sess["a_id"], "b": sess["b_id"]})
                for uid in (sess["a_id"], sess["b_id"]):
                    await hub.push(uid, {"type": "trade_completed", "session_id": sess["id"]})
                return {"status": "completed"}
            await _push_state(sess)
            return {"status": "waiting"}

    @router.post("/trade/cancel")
    async def cancel(data: SessionRef, user=Depends(get_current_user)):
        async with _slock(data.session_id):
            sess = await db.trade_sessions.find_one({"id": data.session_id}, {"_id": 0})
            if not sess or user["id"] not in (sess["a_id"], sess["b_id"]):
                raise HTTPException(status_code=404, detail="Sesión no válida")
            if sess["status"] in ("completed", "cancelled"):
                return {"status": sess["status"]}
            await db.trade_sessions.update_one({"id": sess["id"]}, {"$set": {"status": "cancelled", "updated_at": _iso()}})
            other = sess["b_id"] if sess["a_id"] == user["id"] else sess["a_id"]
            await hub.push(other, {"type": "trade_cancelled", "session_id": sess["id"], "by": user.get("persona_name")})
            return {"status": "cancelled"}

    # ============ websocket (presence) ============
    @router.websocket("/trade/ws")
    async def trade_ws(ws: WebSocket):
        await ws.accept()
        token = ws.query_params.get("token")
        user_id = None
        if token:
            try:
                user_id = jwt.decode(token, jwt_secret, algorithms=[jwt_algo]).get("sub")
            except Exception:
                user_id = None
        if not user_id:
            await ws.close()
            return
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "persona_name": 1, "avatar": 1})
        name = (u or {}).get("persona_name") or "Jugador"
        avatar = (u or {}).get("avatar")
        try:
            await hub.add(ws, user_id, name, avatar)
            # resume an in-flight session on reconnect
            sess = await _active_for(user_id)
            if sess and sess["status"] == "active":
                await ws.send_json({"type": "trade_start", "state": _public(sess, user_id)})
            elif sess and sess["status"] == "invited" and sess["b_id"] == user_id:
                await ws.send_json({"type": "trade_invite", "session_id": sess["id"],
                                    "from": {"user_id": sess["a_id"], "name": sess["a_name"], "avatar": sess["a_avatar"]}})
            while True:
                msg = await ws.receive_text()
                if msg == "ping":
                    await ws.send_text("pong")
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning(f"[trade] ws: {e}")
        finally:
            await hub.remove(ws)

    global _ensure_indexes_fn
    _ensure_indexes_fn = ensure_indexes
    return router


_ensure_indexes_fn = None


async def ensure_indexes():
    if _ensure_indexes_fn:
        await _ensure_indexes_fn()
