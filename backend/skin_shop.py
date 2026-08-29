"""Tienda de Skins Únicas — estilo Fortnite (rotativa, por temporadas).

Self-contained like crash_game.py / battle_pass.py: it NEVER imports from
server.py. The Mongo handle, JWT secret and the auth dependencies are handed in
once via build_router(...), which returns an APIRouter mounted under /api.

Pieces (one job each):
  - ShopHub: WebSocket fan-out. Broadcasts `shop_update` to everyone and pushes
    `purchase_success` / `inventory` to a single owner.
  - Stripe: real-money checkout (Flow A claimable sandbox). Each skin owns a
    Stripe Product+Price created at admin-create time; checkout uses that price
    so the amount is ALWAYS server-side (never trusted from the client).
  - Grant: idempotent — a paid session grants the skin exactly once (unique
    index on owned_shop_skins (user_id, skin_id) + a `granted` flag on the tx).

Collections: shop_skins, owned_shop_skins, shop_payments.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List

import jwt
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger("skin_shop")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or "sk_test_emergent"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
# US + digital goods -> Stripe manages tax (SMP). Falls back to Stripe Tax if the
# account turns out ineligible (handled inline at checkout).
SHOP_TAX_MODE = "full"
DIGITAL_TAX_CODE = "txcd_10302000"  # digital content

RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
SECTIONS = ["destacados", "diario", "temporada"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _now().isoformat()


def _nid() -> str:
    return uuid.uuid4().hex


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _is_live(skin: dict) -> bool:
    """A skin is buyable when active and inside its [start_at, end_at] window."""
    if not skin.get("active", True):
        return False
    now = _now()
    s = _parse(skin.get("start_at"))
    e = _parse(skin.get("end_at"))
    if s and now < s:
        return False
    if e and now > e:
        return False
    return True


def _public(skin: dict) -> dict:
    return {
        "id": skin["id"],
        "name": skin.get("name"),
        "description": skin.get("description"),
        "image_url": skin.get("image_url"),
        "rarity": skin.get("rarity", "common"),
        "section": skin.get("section", "diario"),
        "dino_species": skin.get("dino_species"),
        "price_cents": skin.get("price_cents", 0),
        "price_usd": round((skin.get("price_cents", 0) or 0) / 100, 2),
        "currency": skin.get("currency", "usd"),
        "start_at": skin.get("start_at"),
        "end_at": skin.get("end_at"),
        "active": skin.get("active", True),
        "live": _is_live(skin),
        "created_at": skin.get("created_at"),
    }


class ShopHub:
    def __init__(self):
        self.clients: dict = {}  # ws -> user_id | None

    async def add(self, ws, user_id):
        self.clients[ws] = user_id

    async def remove(self, ws):
        self.clients.pop(ws, None)

    async def broadcast(self, payload: dict):
        dead = []
        for ws in list(self.clients.keys()):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.pop(ws, None)

    async def push_to_user(self, user_id: str, payload: dict):
        if not user_id:
            return
        dead = []
        for ws, uid in list(self.clients.items()):
            if uid == user_id:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)
        for ws in dead:
            self.clients.pop(ws, None)


hub = ShopHub()


# ─────────────────────────── Pydantic I/O ───────────────────────────
class SkinCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=600)
    image_url: str = Field(min_length=1, max_length=1000)
    rarity: str = "common"
    section: str = "diario"
    dino_species: Optional[str] = Field(default=None, max_length=80)
    price_usd: float = Field(gt=0, le=100000)
    skin_data: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    active: bool = True


class SkinUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    rarity: Optional[str] = None
    section: Optional[str] = None
    dino_species: Optional[str] = None
    price_usd: Optional[float] = Field(default=None, gt=0, le=100000)
    skin_data: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    active: Optional[bool] = None


class CheckoutIn(BaseModel):
    skin_id: str
    origin_url: str


class EquipIn(BaseModel):
    skin_id: str


# ─────────────────────────── Stripe helpers (sync, run in thread) ───────────
def _stripe_create_product_price(name: str, price_cents: int, currency: str, skin_id: str):
    product = stripe.Product.create(
        name=name, tax_code=DIGITAL_TAX_CODE,
        metadata={"managed_by": "emergent", "kind": "shop_skin", "skin_id": skin_id})
    price = stripe.Price.create(
        product=product.id, unit_amount=price_cents, currency=currency,
        lookup_key=f"shop_skin_{skin_id}", transfer_lookup_key=True)
    return product.id, price.id


def _stripe_new_price(product_id: str, price_cents: int, currency: str, skin_id: str, old_price_id: Optional[str]):
    if old_price_id:
        try:
            stripe.Price.modify(old_price_id, active=False, lookup_key="")
        except Exception:
            pass
    price = stripe.Price.create(
        product=product_id, unit_amount=price_cents, currency=currency,
        lookup_key=f"shop_skin_{skin_id}", transfer_lookup_key=True)
    return price.id


def _stripe_deactivate(product_id: Optional[str], price_id: Optional[str]):
    try:
        if price_id:
            stripe.Price.modify(price_id, active=False)
    except Exception:
        pass
    try:
        if product_id:
            stripe.Product.modify(product_id, active=False)
    except Exception:
        pass


def _stripe_checkout(price_id: str, success_url: str, cancel_url: str, metadata: dict):
    kwargs = dict(
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
    )
    if SHOP_TAX_MODE == "full":
        try:
            return stripe.checkout.Session.create(**kwargs, managed_payments={"enabled": True})
        except stripe.error.InvalidRequestError as e:
            msg = (getattr(e, "user_message", "") or "").lower()
            if "managed payments" in msg or "ineligible" in msg:
                return stripe.checkout.Session.create(
                    **kwargs, automatic_tax={"enabled": True}, billing_address_collection="required")
            raise
    else:
        return stripe.checkout.Session.create(
            **kwargs, automatic_tax={"enabled": True}, billing_address_collection="required")


def _stripe_retrieve(session_id: str):
    return stripe.checkout.Session.retrieve(session_id)


# ─────────────────────────── Router factory ───────────────────────────
def build_router(db, jwt_secret: str, get_current_user, get_admin_user, add_log, jwt_algo: str = "HS256"):
    router = APIRouter()

    async def ensure_indexes():
        try:
            await db.shop_skins.create_index("id", unique=True)
            await db.shop_skins.create_index("section")
            await db.owned_shop_skins.create_index([("user_id", 1), ("skin_id", 1)], unique=True)
            await db.owned_shop_skins.create_index("user_id")
            await db.shop_payments.create_index("session_id", unique=True)
            await db.shop_payments.create_index("user_id")
        except Exception:
            logger.warning("[shop] index init skipped", exc_info=True)

    async def _grant_skin(user_id: str, skin_id: str, session_id: str) -> bool:
        """Idempotent grant. Returns True if this call created the ownership."""
        skin = await db.shop_skins.find_one({"id": skin_id}, {"_id": 0})
        if not skin:
            return False
        try:
            await db.owned_shop_skins.insert_one({
                "id": _nid(), "user_id": user_id, "skin_id": skin_id,
                "name": skin.get("name"), "image_url": skin.get("image_url"),
                "rarity": skin.get("rarity"), "dino_species": skin.get("dino_species"),
                "skin_data": skin.get("skin_data"),
                "session_id": session_id, "acquired_at": _iso(),
            })
            created = True
        except Exception:
            created = False  # duplicate key -> already owned
        await db.shop_payments.update_one(
            {"session_id": session_id}, {"$set": {"granted": True, "granted_at": _iso()}})
        # tell the owner in real time
        await hub.push_to_user(user_id, {
            "type": "purchase_success", "skin_id": skin_id, "name": skin.get("name"),
            "image_url": skin.get("image_url"), "rarity": skin.get("rarity")})
        owned = await db.owned_shop_skins.find({"user_id": user_id}, {"_id": 0}).to_list(500)
        await hub.push_to_user(user_id, {"type": "inventory", "skins": owned})
        return created

    async def _maybe_settle(session_id: str):
        """Poll Stripe; if paid, flip the tx and grant the skin (idempotent)."""
        tx = await db.shop_payments.find_one({"session_id": session_id}, {"_id": 0})
        if not tx:
            return None
        if tx.get("payment_status") != "paid":
            try:
                s = await asyncio.to_thread(_stripe_retrieve, session_id)
                if s.payment_status == "paid" or s.status == "complete":
                    await db.shop_payments.update_one(
                        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                        {"$set": {"status": "completed", "payment_status": "paid", "updated_at": _iso()}})
                    tx = await db.shop_payments.find_one({"session_id": session_id}, {"_id": 0})
            except stripe.error.StripeError:
                pass
        if tx and tx.get("payment_status") == "paid" and not tx.get("granted"):
            await _grant_skin(tx["user_id"], tx["skin_id"], session_id)
            tx = await db.shop_payments.find_one({"session_id": session_id}, {"_id": 0})
        return tx

    # ---------- public (auth) ----------
    @router.get("/shop/skins")
    async def list_skins(user=Depends(get_current_user)):
        owned_ids = set(d["skin_id"] for d in await db.owned_shop_skins.find(
            {"user_id": user["id"]}, {"_id": 0, "skin_id": 1}).to_list(500))
        equipped = user.get("equipped_shop_skin")
        cur = db.shop_skins.find({"active": True}, {"_id": 0}).sort("created_at", -1)
        skins = await cur.to_list(500)
        out = {"destacados": [], "diario": [], "temporada": []}
        for s in skins:
            if not _is_live(s):
                continue
            p = _public(s)
            p["owned"] = s["id"] in owned_ids
            p["equipped"] = equipped == s["id"]
            out.get(p["section"], out["diario"]).append(p)
        return {"sections": out, "server_time": _iso()}

    @router.get("/shop/skins/mine")
    async def my_skins(user=Depends(get_current_user)):
        owned = await db.owned_shop_skins.find({"user_id": user["id"]}, {"_id": 0}).sort("acquired_at", -1).to_list(500)
        return {"skins": owned, "equipped": user.get("equipped_shop_skin")}

    @router.post("/shop/checkout")
    async def checkout(data: CheckoutIn, user=Depends(get_current_user)):
        skin = await db.shop_skins.find_one({"id": data.skin_id}, {"_id": 0})
        if not skin:
            raise HTTPException(status_code=404, detail="Skin no encontrada")
        if not _is_live(skin):
            raise HTTPException(status_code=400, detail="Esta skin no está disponible ahora mismo")
        already = await db.owned_shop_skins.find_one({"user_id": user["id"], "skin_id": skin["id"]})
        if already:
            raise HTTPException(status_code=400, detail="Ya tienes esta skin")
        if not skin.get("stripe_price_id"):
            raise HTTPException(status_code=500, detail="Skin sin precio de Stripe configurado")
        origin = data.origin_url.rstrip("/")
        success_url = f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/tienda-skins?canceled=1"
        try:
            session = await asyncio.to_thread(
                _stripe_checkout, skin["stripe_price_id"], success_url, cancel_url,
                {"user_id": user["id"], "skin_id": skin["id"], "kind": "shop_skin"})
        except Exception as e:
            logger.exception("[shop] checkout create failed")
            raise HTTPException(status_code=502, detail=f"No se pudo iniciar el pago: {e}")
        await db.shop_payments.insert_one({
            "id": _nid(), "session_id": session.id, "user_id": user["id"],
            "skin_id": skin["id"], "skin_name": skin.get("name"),
            "amount": skin.get("price_cents", 0), "currency": skin.get("currency", "usd"),
            "status": "initiated", "payment_status": "pending", "granted": False,
            "created_at": _iso(), "updated_at": _iso(),
        })
        return {"checkout_url": session.url, "session_id": session.id}

    @router.get("/payments/status/{session_id}")
    async def payment_status(session_id: str):
        tx = await _maybe_settle(session_id)
        if not tx:
            raise HTTPException(status_code=404, detail="Transacción no encontrada")
        return {"session_id": tx["session_id"], "status": tx.get("status"),
                "payment_status": tx.get("payment_status"), "granted": bool(tx.get("granted")),
                "skin_id": tx.get("skin_id"), "skin_name": tx.get("skin_name")}

    @router.post("/stripe/webhook")
    async def stripe_webhook(request: Request):
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        try:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid signature")
        obj = event["data"]["object"]
        t = event["type"]
        if t == "checkout.session.completed":
            sid = obj["id"]
            await db.shop_payments.update_one(
                {"session_id": sid, "payment_status": {"$ne": "paid"}},
                {"$set": {"status": "completed", "payment_status": obj.get("payment_status", "paid"),
                          "updated_at": _iso()}})
            tx = await db.shop_payments.find_one({"session_id": sid}, {"_id": 0})
            if tx and tx.get("payment_status") == "paid" and not tx.get("granted"):
                await _grant_skin(tx["user_id"], tx["skin_id"], sid)
        elif t in ("checkout.session.async_payment_failed", "checkout.session.expired"):
            await db.shop_payments.update_one(
                {"session_id": obj["id"]},
                {"$set": {"status": "failed", "payment_status": "failed", "updated_at": _iso()}})
        return {"status": "ok"}

    @router.post("/shop/equip")
    async def equip(data: EquipIn, user=Depends(get_current_user)):
        owned = await db.owned_shop_skins.find_one({"user_id": user["id"], "skin_id": data.skin_id})
        if not owned:
            raise HTTPException(status_code=403, detail="No tienes esta skin")
        await db.users.update_one({"id": user["id"]}, {"$set": {"equipped_shop_skin": data.skin_id}})
        await hub.push_to_user(user["id"], {"type": "equipped", "skin_id": data.skin_id})
        return {"success": True, "equipped": data.skin_id}

    @router.post("/shop/unequip")
    async def unequip(user=Depends(get_current_user)):
        await db.users.update_one({"id": user["id"]}, {"$unset": {"equipped_shop_skin": ""}})
        await hub.push_to_user(user["id"], {"type": "equipped", "skin_id": None})
        return {"success": True}

    # ---------- admin ----------
    @router.get("/admin/shop/skins")
    async def admin_list(admin=Depends(get_admin_user)):
        skins = await db.shop_skins.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
        # sold counts
        agg = await db.owned_shop_skins.aggregate([
            {"$group": {"_id": "$skin_id", "n": {"$sum": 1}}}]).to_list(2000)
        sold = {a["_id"]: a["n"] for a in agg}
        items = []
        for s in skins:
            p = _public(s)
            p["sold"] = sold.get(s["id"], 0)
            p["skin_data"] = s.get("skin_data")
            items.append(p)
        paid = await db.shop_payments.count_documents({"payment_status": "paid"})
        revenue = await db.shop_payments.aggregate([
            {"$match": {"payment_status": "paid"}},
            {"$group": {"_id": None, "sum": {"$sum": "$amount"}}}]).to_list(1)
        stats = {
            "total_skins": len(skins),
            "live_skins": sum(1 for s in skins if _is_live(s)),
            "total_sold": sum(sold.values()),
            "paid_orders": paid,
            "revenue_usd": round((revenue[0]["sum"] if revenue else 0) / 100, 2),
        }
        return {"items": items, "stats": stats}

    @router.post("/admin/shop/skins")
    async def admin_create(data: SkinCreate, admin=Depends(get_admin_user)):
        if data.rarity not in RARITIES:
            raise HTTPException(status_code=400, detail="Rareza inválida")
        if data.section not in SECTIONS:
            raise HTTPException(status_code=400, detail="Sección inválida")
        skin_id = _nid()
        price_cents = int(round(data.price_usd * 100))
        try:
            product_id, price_id = await asyncio.to_thread(
                _stripe_create_product_price, data.name, price_cents, "usd", skin_id)
        except Exception as e:
            logger.exception("[shop] stripe product create failed")
            raise HTTPException(status_code=502, detail=f"Stripe: {e}")
        doc = {
            "id": skin_id, "name": data.name, "description": data.description,
            "image_url": data.image_url, "rarity": data.rarity, "section": data.section,
            "dino_species": data.dino_species, "price_cents": price_cents, "currency": "usd",
            "skin_data": data.skin_data, "start_at": data.start_at, "end_at": data.end_at,
            "active": data.active, "stripe_product_id": product_id, "stripe_price_id": price_id,
            "created_at": _iso(), "created_by": admin.get("persona_name"),
        }
        await db.shop_skins.insert_one(dict(doc))
        await add_log(admin.get("persona_name"), "shop_create_skin", skin_id, {"name": data.name})
        await hub.broadcast({"type": "shop_update", "action": "create", "skin_id": skin_id})
        doc.pop("_id", None)
        return {"success": True, "skin": _public(doc)}

    @router.patch("/admin/shop/skins/{skin_id}")
    async def admin_update(skin_id: str, data: SkinUpdate, admin=Depends(get_admin_user)):
        skin = await db.shop_skins.find_one({"id": skin_id}, {"_id": 0})
        if not skin:
            raise HTTPException(status_code=404, detail="Skin no encontrada")
        upd = {k: v for k, v in data.model_dump().items() if v is not None}
        if "rarity" in upd and upd["rarity"] not in RARITIES:
            raise HTTPException(status_code=400, detail="Rareza inválida")
        if "section" in upd and upd["section"] not in SECTIONS:
            raise HTTPException(status_code=400, detail="Sección inválida")
        if "price_usd" in upd:
            new_cents = int(round(upd.pop("price_usd") * 100))
            if new_cents != skin.get("price_cents"):
                try:
                    new_price = await asyncio.to_thread(
                        _stripe_new_price, skin.get("stripe_product_id"), new_cents, "usd",
                        skin_id, skin.get("stripe_price_id"))
                    upd["stripe_price_id"] = new_price
                except Exception as e:
                    logger.exception("[shop] stripe price update failed")
                    raise HTTPException(status_code=502, detail=f"Stripe: {e}")
                upd["price_cents"] = new_cents
        if "name" in upd and skin.get("stripe_product_id"):
            try:
                await asyncio.to_thread(lambda: stripe.Product.modify(skin["stripe_product_id"], name=upd["name"]))
            except Exception:
                pass
        upd["updated_at"] = _iso()
        await db.shop_skins.update_one({"id": skin_id}, {"$set": upd})
        await add_log(admin.get("persona_name"), "shop_update_skin", skin_id, upd)
        await hub.broadcast({"type": "shop_update", "action": "update", "skin_id": skin_id})
        fresh = await db.shop_skins.find_one({"id": skin_id}, {"_id": 0})
        return {"success": True, "skin": _public(fresh)}

    @router.delete("/admin/shop/skins/{skin_id}")
    async def admin_delete(skin_id: str, admin=Depends(get_admin_user)):
        skin = await db.shop_skins.find_one({"id": skin_id}, {"_id": 0})
        if not skin:
            raise HTTPException(status_code=404, detail="Skin no encontrada")
        await asyncio.to_thread(_stripe_deactivate, skin.get("stripe_product_id"), skin.get("stripe_price_id"))
        await db.shop_skins.delete_one({"id": skin_id})
        await add_log(admin.get("persona_name"), "shop_delete_skin", skin_id, {})
        await hub.broadcast({"type": "shop_update", "action": "delete", "skin_id": skin_id})
        return {"success": True}

    # ---------- websocket ----------
    @router.websocket("/shop/ws")
    async def shop_ws(ws: WebSocket):
        await ws.accept()
        user_id = None
        token = ws.query_params.get("token")
        if token:
            try:
                payload = jwt.decode(token, jwt_secret, algorithms=[jwt_algo])
                user_id = payload.get("sub")
            except Exception:
                user_id = None
        try:
            await hub.add(ws, user_id)
            await ws.send_json({"type": "shop_hello", "ts": _iso()})
            while True:
                msg = await ws.receive_text()
                if msg == "ping":
                    await ws.send_text("pong")
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning(f"[shop] ws: {e}")
        finally:
            await hub.remove(ws)

    global _ensure_indexes_fn
    _ensure_indexes_fn = ensure_indexes
    return router


_ensure_indexes_fn = None


async def ensure_indexes():
    if _ensure_indexes_fn:
        await _ensure_indexes_fn()
