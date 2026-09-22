"""Sistema de Crafteo de Skins — La Isla Nublar (Fase 1).

Server-authoritative. Todo el estado vive en Mongo; los timers se calculan con
started_at/finish_at persistidos (nunca setTimeout del backend). WebSocket empuja
eventos en vivo (sin polling). Los materiales se descuentan de forma atómica con
guardas $gte + compensación; CRAFT y CLAIM usan idempotency keys.

Colecciones:
  crafting_materials   {id,name,description,icon,rarity,stack_limit,enabled,order}
  player_materials     {player_id,material_id,quantity}   (único player_id+material_id)
  crafting_recipes     {id,name,dino,dino_slug,diet,rarity,image_url,crafting_time,
                        uses_granted,enabled,materials:[{material_id,qty}],order}
  crafting_jobs        {id,player_id,recipe_id,recipe_snapshot,started_at,finish_at,
                        status,claimed_at,idempotency_key,created_at}
  crafting_settings    {_id:"crafting", ...flags...}
  crafting_logs        {id,player_id,kind,action,detail,created_at}

Estados de job: CRAFTING · COMPLETED · CLAIMED · CANCELLED
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("laislanublar.crafting")

# ── DI (rellenado por configure() en server.py) ──────────────────────────────
_db = None
_admin_ids = set()
_jwt_secret = ""
_jwt_algo = "HS256"
_grant_skin = None      # async fn(user_id, recipe_snapshot, uses) -> None
_add_log = None         # async fn(actor, action, target, meta)
_discord_notify = None  # async fn(recipe_snapshot, user_info) or None

MIN_USES = 20
RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]
RARE_PLUS = {"epic", "legendary"}
STATUS_CRAFTING = "CRAFTING"
STATUS_COMPLETED = "COMPLETED"
STATUS_CLAIMED = "CLAIMED"
STATUS_CANCELLED = "CANCELLED"

DEFAULT_SETTINGS = {
    "crafting_enabled": True,
    "gathering_enabled": True,
    "crafting_speed_mult": 1.0,
    "material_drop_mult": 1.0,
    "max_active_crafts": 1,
    "node_respawn_mult": 1.0,
    "notifications_enabled": True,
    "discord_enabled": False,
    "discord_webhook": "",
    "role_limits": {"vip": 2, "apex": 3},   # por staff_rank/tier; default = max_active_crafts
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


# ─────────────────────────── Hub WebSocket ───────────────────────────
class CraftHub:
    def __init__(self):
        self.conns: set = set()
        self.by_uid: dict = {}
        self.uid_of: dict = {}

    def add(self, ws, uid=None):
        self.conns.add(ws)
        if uid:
            self.by_uid.setdefault(uid, set()).add(ws)
            self.uid_of[ws] = uid

    def remove(self, ws):
        self.conns.discard(ws)
        uid = self.uid_of.pop(ws, None)
        if uid and uid in self.by_uid:
            self.by_uid[uid].discard(ws)
            if not self.by_uid[uid]:
                self.by_uid.pop(uid, None)

    async def send_to(self, uid: str, event: str, data: dict):
        payload = {"event": event, "data": data}
        for ws in list(self.by_uid.get(uid, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.remove(ws)

    async def broadcast(self, event: str, data: dict):
        payload = {"event": event, "data": data}
        for ws in list(self.conns):
            try:
                await ws.send_json(payload)
            except Exception:
                self.remove(ws)


hub = CraftHub()


# ─────────────────────────── Config / settings ───────────────────────────
def configure(db, *, admin_ids, grant_skin, add_log=None, discord_notify=None,
              jwt_secret="", jwt_algo="HS256"):
    global _db, _admin_ids, _grant_skin, _add_log, _discord_notify, _jwt_secret, _jwt_algo
    _db = db
    _admin_ids = set(admin_ids or [])
    _grant_skin = grant_skin
    _add_log = add_log
    _discord_notify = discord_notify
    _jwt_secret = jwt_secret
    _jwt_algo = jwt_algo


async def get_settings() -> dict:
    doc = await _db.crafting_settings.find_one({"_id": "crafting"}) or {}
    out = dict(DEFAULT_SETTINGS)
    for k in DEFAULT_SETTINGS:
        if doc.get(k) is not None:
            out[k] = doc[k]
    return out


async def _log(player_id, kind, action, detail=None):
    try:
        await _db.crafting_logs.insert_one({
            "id": _new_id(), "player_id": player_id, "kind": kind, "action": action,
            "detail": detail or {}, "created_at": _iso(_now())})
    except Exception:
        logger.warning("[crafting] log skipped", exc_info=True)


async def ensure_indexes():
    try:
        await _db.crafting_materials.create_index("id", unique=True)
        await _db.crafting_materials.create_index("enabled")
        await _db.player_materials.create_index([("player_id", 1), ("material_id", 1)], unique=True)
        await _db.player_materials.create_index("player_id")
        await _db.crafting_recipes.create_index("id", unique=True)
        await _db.crafting_recipes.create_index("enabled")
        await _db.crafting_jobs.create_index("id", unique=True)
        await _db.crafting_jobs.create_index([("player_id", 1), ("status", 1)])
        await _db.crafting_jobs.create_index([("status", 1), ("finish_at", 1)])
        await _db.crafting_jobs.create_index([("player_id", 1), ("idempotency_key", 1)],
                                             unique=True, sparse=True)
        await _db.crafting_logs.create_index([("created_at", -1)])
        await _db.crafting_logs.create_index([("player_id", 1), ("kind", 1)])
    except Exception:
        logger.warning("[crafting] index init skipped", exc_info=True)


# ─────────────────────────── Seed inicial ───────────────────────────
_SEED_MATERIALS = [
    {"id": "bones", "name": "Huesos", "description": "Restos óseos recolectados en cementerios, cadáveres y zonas de fósiles.",
     "icon": "https://customer-assets-agu9un31.emergentagent.net/job_synced-animations/artifacts/6t8p6wl0_huesos-removebg-preview.png",
     "rarity": "common", "stack_limit": 999, "enabled": True, "order": 1},
    {"id": "metal", "name": "Metal", "description": "Mineral de hierro extraído de cuevas, minas y zonas rocosas.",
     "icon": "https://customer-assets-agu9un31.emergentagent.net/job_synced-animations/artifacts/mq1svrtm_metal-removebg-preview.png",
     "rarity": "uncommon", "stack_limit": 999, "enabled": True, "order": 2},
    {"id": "leather", "name": "Cuero", "description": "Cuero curtido obtenido de restos de animales en zonas especiales.",
     "icon": "https://customer-assets-agu9un31.emergentagent.net/job_synced-animations/artifacts/29uus1sw_cuero-removebg-preview.png",
     "rarity": "rare", "stack_limit": 999, "enabled": True, "order": 3},
    {"id": "polymer", "name": "Polímero Orgánico", "description": "Polímero de alta pureza hallado en laboratorios y zonas contaminadas.",
     "icon": "https://customer-assets-agu9un31.emergentagent.net/job_synced-animations/artifacts/lux99d19_polimero-removebg-preview.png",
     "rarity": "epic", "stack_limit": 999, "enabled": True, "order": 4},
]

_SEED_RECIPES = [
    {"id": "rex_volcanic", "name": "T-Rex Volcánico", "dino": "Tyrannosaurus", "dino_slug": "trex",
     "diet": "carnivore", "rarity": "legendary", "image_url": "/dinos/trex.png",
     "crafting_time": 7200, "uses_granted": 20, "enabled": True, "order": 1,
     "materials": [{"material_id": "bones", "qty": 120}, {"material_id": "metal", "qty": 80},
                   {"material_id": "leather", "qty": 45}, {"material_id": "polymer", "qty": 30}]},
    {"id": "spino_abyss", "name": "Spino Abismal", "dino": "Spinosaurus", "dino_slug": "spino",
     "diet": "carnivore", "rarity": "epic", "image_url": "/dinos/allo.png",
     "crafting_time": 5400, "uses_granted": 20, "enabled": True, "order": 2,
     "materials": [{"material_id": "bones", "qty": 80}, {"material_id": "metal", "qty": 60},
                   {"material_id": "polymer", "qty": 20}]},
    {"id": "trike_gilded", "name": "Trike Dorado", "dino": "Triceratops", "dino_slug": "trike",
     "diet": "herbivore", "rarity": "rare", "image_url": "/dinos/trike.png",
     "crafting_time": 3600, "uses_granted": 20, "enabled": True, "order": 3,
     "materials": [{"material_id": "bones", "qty": 60}, {"material_id": "leather", "qty": 40}]},
    {"id": "stego_frost", "name": "Stego Invernal", "dino": "Stegosaurus", "dino_slug": "stego",
     "diet": "herbivore", "rarity": "uncommon", "image_url": "/dinos/stego.png",
     "crafting_time": 1800, "uses_granted": 20, "enabled": True, "order": 4,
     "materials": [{"material_id": "bones", "qty": 40}, {"material_id": "metal", "qty": 20}]},
]


async def seed_defaults():
    try:
        if await _db.crafting_materials.count_documents({}) == 0:
            await _db.crafting_materials.insert_many([dict(m) for m in _SEED_MATERIALS])
            logger.info("[crafting] seeded %d materials", len(_SEED_MATERIALS))
        if await _db.crafting_recipes.count_documents({}) == 0:
            await _db.crafting_recipes.insert_many([dict(r) for r in _SEED_RECIPES])
            logger.info("[crafting] seeded %d recipes", len(_SEED_RECIPES))
        if await _db.crafting_settings.find_one({"_id": "crafting"}) is None:
            await _db.crafting_settings.insert_one({"_id": "crafting", **DEFAULT_SETTINGS})
    except Exception:
        logger.warning("[crafting] seed skipped", exc_info=True)


# ─────────────────────────── Helpers de estado ───────────────────────────
def _pub_material(m: dict) -> dict:
    return {k: m.get(k) for k in ("id", "name", "description", "icon", "rarity", "stack_limit", "order")}


def _pub_job(j: dict) -> dict:
    return {"id": j["id"], "recipe_id": j["recipe_id"], "recipe": j.get("recipe_snapshot", {}),
            "started_at": j.get("started_at"), "finish_at": j.get("finish_at"),
            "status": j.get("status"), "claimed_at": j.get("claimed_at")}


def _tier_of(user: dict) -> str:
    if user.get("role") == "admin" or user.get("steam_id") in _admin_ids:
        return "apex"
    sr = user.get("staff_rank")
    if sr in ("owner", "admin"):
        return "apex"
    if sr == "vip" or user.get("is_vip") or user.get("patreon_tier"):
        return "vip"
    return "default"


def _craft_limit(user: dict, settings: dict) -> int:
    base = int(settings.get("max_active_crafts", 1) or 1)
    tier = _tier_of(user)
    rl = settings.get("role_limits") or {}
    return int(rl.get(tier, base)) if tier != "default" else base


async def _player_qty_map(player_id: str) -> dict:
    rows = await _db.player_materials.find({"player_id": player_id}, {"_id": 0}).to_list(500)
    return {r["material_id"]: int(r.get("quantity", 0)) for r in rows}


async def build_state(user: dict) -> dict:
    pid = user["id"]
    settings = await get_settings()
    mats = await _db.crafting_materials.find({"enabled": True}, {"_id": 0}).sort("order", 1).to_list(200)
    recipes = await _db.crafting_recipes.find({"enabled": True}, {"_id": 0}).sort("order", 1).to_list(300)
    qty = await _player_qty_map(pid)
    jobs = await _db.crafting_jobs.find(
        {"player_id": pid, "status": {"$in": [STATUS_CRAFTING, STATUS_COMPLETED]}}, {"_id": 0}
    ).sort("started_at", 1).to_list(100)
    jobs_by_recipe = {}
    for j in jobs:
        jobs_by_recipe.setdefault(j["recipe_id"], []).append(j)
    owned_ids = set(d["item_id"] for d in await _db.inventory.find(
        {"user_id": pid, "item_id": {"$regex": "^craft:"}}, {"item_id": 1, "_id": 0}).to_list(500))

    recipe_views = []
    for r in recipes:
        req = []
        craftable = True
        for m in r.get("materials", []):
            have = qty.get(m["material_id"], 0)
            need = int(m["qty"])
            if have < need:
                craftable = False
            req.append({"material_id": m["material_id"], "required": need, "have": have,
                        "ok": have >= need})
        job = None
        rjobs = jobs_by_recipe.get(r["id"], [])
        ready = next((jj for jj in rjobs if jj["status"] == STATUS_COMPLETED), None)
        active = next((jj for jj in rjobs if jj["status"] == STATUS_CRAFTING), None)
        if ready:
            status, job = "READY", _pub_job(ready)
        elif active:
            status, job = "CRAFTING", _pub_job(active)
        elif ("craft:" + r["id"]) in owned_ids:
            status = "OWNED"
        elif craftable:
            status = "CRAFTABLE"
        else:
            status = "MISSING"
        recipe_views.append({
            "id": r["id"], "name": r["name"], "dino": r.get("dino"), "dino_slug": r.get("dino_slug"),
            "diet": r.get("diet"), "rarity": r.get("rarity"), "image_url": r.get("image_url"),
            "crafting_time": int(r.get("crafting_time", 0)), "uses_granted": max(MIN_USES, int(r.get("uses_granted", MIN_USES))),
            "materials": req, "status": status, "job": job})

    active_jobs = [_pub_job(j) for j in jobs if j["status"] in (STATUS_CRAFTING, STATUS_COMPLETED)]
    return {
        "settings": {k: settings[k] for k in ("crafting_enabled", "gathering_enabled",
                     "crafting_speed_mult", "notifications_enabled")},
        "craft_limit": _craft_limit(user, settings),
        "materials": [_pub_material(m) for m in mats],
        "inventory": [{"material_id": mid, "quantity": q} for mid, q in qty.items()],
        "recipes": recipe_views,
        "active_jobs": active_jobs,
    }


# ─────────────────────────── Sweeper (recuperación + fin) ───────────────────────────
async def sweep_due(push=True) -> int:
    """CRAFTING con finish_at<=NOW -> COMPLETED. Idempotente, seguro tras reinicios."""
    now_iso = _iso(_now())
    due = await _db.crafting_jobs.find(
        {"status": STATUS_CRAFTING, "finish_at": {"$lte": now_iso}}, {"_id": 0}).to_list(500)
    n = 0
    for j in due:
        res = await _db.crafting_jobs.update_one(
            {"id": j["id"], "status": STATUS_CRAFTING},
            {"$set": {"status": STATUS_COMPLETED}})
        if res.modified_count:
            n += 1
            await _log(j["player_id"], "craft", "completed", {"job_id": j["id"], "recipe_id": j["recipe_id"]})
            if push:
                await hub.send_to(j["player_id"], "crafting:completed",
                                  {"job": _pub_job({**j, "status": STATUS_COMPLETED})})
    return n


async def _sweeper_loop():
    while True:
        try:
            await sweep_due(push=True)
        except Exception:
            logger.warning("[crafting] sweeper tick failed", exc_info=True)
        await asyncio.sleep(15)


def start_loops():
    asyncio.create_task(_boot())


async def _boot():
    await ensure_indexes()
    await seed_defaults()
    try:
        flipped = await sweep_due(push=False)  # recupera vencidos tras reinicio (sin spamear WS)
        if flipped:
            logger.info("[crafting] recovered %d due jobs on boot", flipped)
    except Exception:
        logger.warning("[crafting] boot sweep failed", exc_info=True)
    asyncio.create_task(_sweeper_loop())


# ─────────────────────────── Modelos de entrada ───────────────────────────
class CraftIn(BaseModel):
    recipe_id: str
    idempotency_key: str | None = None


class ClaimIn(BaseModel):
    job_id: str
    idempotency_key: str | None = None


class CancelIn(BaseModel):
    job_id: str


class GrantIn(BaseModel):
    player_id: str | None = None
    steam_id: str | None = None
    material_id: str
    amount: int


class MaterialIn(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    icon: str = ""
    rarity: str = "common"
    stack_limit: int = 999
    enabled: bool = True
    order: int = 999


class RecipeMat(BaseModel):
    material_id: str
    qty: int


class RecipeIn(BaseModel):
    id: str | None = None
    name: str
    dino: str = ""
    dino_slug: str = ""
    diet: str = "carnivore"
    rarity: str = "common"
    image_url: str = ""
    crafting_time: int = 3600
    uses_granted: int = MIN_USES
    enabled: bool = True
    order: int = 999
    materials: list[RecipeMat] = []


# ─────────────────────────── Núcleo: craft / claim ───────────────────────────
_lock = asyncio.Lock()


async def _grant_materials(player_id: str, material_id: str, amount: int):
    await _db.player_materials.update_one(
        {"player_id": player_id, "material_id": material_id},
        {"$inc": {"quantity": int(amount)}}, upsert=True)


async def do_craft(user: dict, recipe_id: str, idem: str | None) -> dict:
    pid = user["id"]
    settings = await get_settings()
    if not settings.get("crafting_enabled", True):
        raise HTTPException(423, "El crafteo está deshabilitado temporalmente.")
    recipe = await _db.crafting_recipes.find_one({"id": recipe_id, "enabled": True}, {"_id": 0})
    if not recipe:
        raise HTTPException(404, "Receta no encontrada.")

    idem = (idem or "").strip() or None

    async with _lock:
        # Idempotencia: mismo idempotency_key -> devolver el job existente.
        if idem:
            prev = await _db.crafting_jobs.find_one({"player_id": pid, "idempotency_key": idem}, {"_id": 0})
            if prev:
                return {"success": True, "job": _pub_job(prev), "idempotent": True}

        # Límite de crafteos activos por rol.
        limit = _craft_limit(user, settings)
        active = await _db.crafting_jobs.count_documents(
            {"player_id": pid, "status": {"$in": [STATUS_CRAFTING, STATUS_COMPLETED]}})
        if active >= limit:
            raise HTTPException(409, f"Ya tienes {active} crafteo(s) activo(s). Límite: {limit}.")

        mats = recipe.get("materials", [])
        # Pre-chequeo con lectura única.
        qty = await _player_qty_map(pid)
        missing = [m for m in mats if qty.get(m["material_id"], 0) < int(m["qty"])]
        if missing:
            raise HTTPException(400, "Materiales insuficientes para fabricar esta skin.")

        # Descuento atómico compensado (guardas $gte). Si algo falla -> ROLLBACK.
        deducted = []
        try:
            for m in mats:
                res = await _db.player_materials.update_one(
                    {"player_id": pid, "material_id": m["material_id"], "quantity": {"$gte": int(m["qty"])}},
                    {"$inc": {"quantity": -int(m["qty"])}})
                if res.modified_count == 0:
                    raise HTTPException(400, "Materiales insuficientes (condición de carrera evitada).")
                deducted.append(m)
        except Exception:
            for m in deducted:  # refund
                await _db.player_materials.update_one(
                    {"player_id": pid, "material_id": m["material_id"]},
                    {"$inc": {"quantity": int(m["qty"])}})
            raise

        # Crear el job con timers server-side.
        speed = max(0.05, float(settings.get("crafting_speed_mult", 1.0) or 1.0))
        secs = max(1, int(round(int(recipe.get("crafting_time", 0)) / speed)))
        started = _now()
        finish = started.fromtimestamp(started.timestamp() + secs, tz=timezone.utc)
        snap = {"id": recipe["id"], "name": recipe["name"], "dino": recipe.get("dino"),
                "dino_slug": recipe.get("dino_slug"), "rarity": recipe.get("rarity"),
                "image_url": recipe.get("image_url"), "diet": recipe.get("diet"),
                "uses_granted": max(MIN_USES, int(recipe.get("uses_granted", MIN_USES)))}
        job = {"id": _new_id(), "player_id": pid, "recipe_id": recipe["id"], "recipe_snapshot": snap,
               "started_at": _iso(started), "finish_at": _iso(finish), "status": STATUS_CRAFTING,
               "claimed_at": None, "idempotency_key": idem, "created_at": _iso(started)}
        try:
            await _db.crafting_jobs.insert_one(dict(job))
        except Exception:
            # colisión de idempotency_key (doble request simultáneo): refund + devolver el existente
            for m in mats:
                await _db.player_materials.update_one(
                    {"player_id": pid, "material_id": m["material_id"]},
                    {"$inc": {"quantity": int(m["qty"])}})
            prev = await _db.crafting_jobs.find_one({"player_id": pid, "idempotency_key": idem}, {"_id": 0})
            if prev:
                return {"success": True, "job": _pub_job(prev), "idempotent": True}
            raise HTTPException(409, "No se pudo iniciar el crafteo, inténtalo de nuevo.")

    await _log(pid, "craft", "started", {"job_id": job["id"], "recipe_id": recipe["id"],
                                         "materials": mats})
    inv = [{"material_id": mid, "quantity": q} for mid, q in (await _player_qty_map(pid)).items()]
    await hub.send_to(pid, "materials:updated", {"inventory": inv})
    await hub.send_to(pid, "crafting:started", {"job": _pub_job(job)})
    return {"success": True, "job": _pub_job(job)}


async def do_claim(user: dict, job_id: str, idem: str | None) -> dict:
    pid = user["id"]
    async with _lock:
        job = await _db.crafting_jobs.find_one({"id": job_id, "player_id": pid}, {"_id": 0})
        if not job:
            raise HTTPException(404, "Crafteo no encontrado.")
        if job["status"] == STATUS_CLAIMED:
            raise HTTPException(409, "Este crafteo ya fue reclamado.")
        # Server-authoritative: si venció pero sigue CRAFTING, promover ahora.
        if job["status"] == STATUS_CRAFTING:
            if job.get("finish_at") and job["finish_at"] <= _iso(_now()):
                await _db.crafting_jobs.update_one({"id": job_id, "status": STATUS_CRAFTING},
                                                   {"$set": {"status": STATUS_COMPLETED}})
                job["status"] = STATUS_COMPLETED
            else:
                raise HTTPException(400, "El crafteo aún no ha terminado.")
        if job["status"] != STATUS_COMPLETED:
            raise HTTPException(400, "Este crafteo no está listo para reclamar.")

        # Marcar CLAIMED atómicamente: solo un ganador (evita doble claim).
        res = await _db.crafting_jobs.update_one(
            {"id": job_id, "player_id": pid, "status": STATUS_COMPLETED},
            {"$set": {"status": STATUS_CLAIMED, "claimed_at": _iso(_now())}})
        if res.modified_count == 0:
            raise HTTPException(409, "Este crafteo ya fue reclamado.")

    snap = job.get("recipe_snapshot", {})
    uses = max(MIN_USES, int(snap.get("uses_granted", MIN_USES)))
    try:
        await _grant_skin(pid, snap, uses)
    except Exception:
        logger.exception("[crafting] grant_skin failed; reabriendo claim")
        await _db.crafting_jobs.update_one({"id": job_id}, {"$set": {"status": STATUS_COMPLETED, "claimed_at": None}})
        raise HTTPException(500, "No se pudo entregar la skin. Intenta reclamar de nuevo.")

    await _log(pid, "claim", "claimed", {"job_id": job_id, "recipe_id": job["recipe_id"], "uses": uses})
    await hub.send_to(pid, "crafting:claimed", {"job_id": job_id, "recipe": snap, "uses": uses})
    # Discord opcional para skins raras.
    if _discord_notify and snap.get("rarity") in RARE_PLUS:
        try:
            await _discord_notify(snap, {"name": user.get("persona_name"), "steam_id": user.get("steam_id")})
        except Exception:
            pass
    return {"success": True, "recipe": snap, "uses": uses}


async def do_cancel(user: dict, job_id: str) -> dict:
    pid = user["id"]
    async with _lock:
        job = await _db.crafting_jobs.find_one({"id": job_id, "player_id": pid}, {"_id": 0})
        if not job:
            raise HTTPException(404, "Crafteo no encontrado.")
        if job["status"] not in (STATUS_CRAFTING, STATUS_COMPLETED):
            raise HTTPException(400, "Este crafteo no se puede cancelar.")
        res = await _db.crafting_jobs.update_one(
            {"id": job_id, "player_id": pid, "status": {"$in": [STATUS_CRAFTING, STATUS_COMPLETED]}},
            {"$set": {"status": STATUS_CANCELLED, "cancelled_at": _iso(_now())}})
        if res.modified_count == 0:
            raise HTTPException(409, "El crafteo cambió de estado.")
        recipe = await _db.crafting_recipes.find_one({"id": job["recipe_id"]}, {"_id": 0})
        refunded = []
        if recipe:  # reembolsar materiales
            for m in recipe.get("materials", []):
                await _grant_materials(pid, m["material_id"], int(m["qty"]))
                refunded.append(m)
    await _log(pid, "craft", "cancelled", {"job_id": job_id, "refunded": refunded})
    inv = [{"material_id": mid, "quantity": q} for mid, q in (await _player_qty_map(pid)).items()]
    await hub.send_to(pid, "materials:updated", {"inventory": inv})
    await hub.send_to(pid, "crafting:cancelled", {"job_id": job_id})
    return {"success": True, "refunded": refunded}


# ─────────────────────────── Router ───────────────────────────
def build_router(get_current_user, get_admin_user):
    router = APIRouter(prefix="/crafting", tags=["crafting"])

    @router.get("/state")
    async def state(user=Depends(get_current_user)):
        return await build_state(user)

    @router.post("/craft")
    async def craft(data: CraftIn, user=Depends(get_current_user)):
        return await do_craft(user, data.recipe_id, data.idempotency_key)

    @router.post("/claim")
    async def claim(data: ClaimIn, user=Depends(get_current_user)):
        return await do_claim(user, data.job_id, data.idempotency_key)

    @router.post("/cancel")
    async def cancel(data: CancelIn, user=Depends(get_current_user)):
        return await do_cancel(user, data.job_id)

    # ─── WebSocket ───
    @router.websocket("/ws")
    async def craft_ws(ws: WebSocket):
        await ws.accept()
        uid = None
        token = ws.query_params.get("token")
        if token:
            try:
                uid = jwt.decode(token, _jwt_secret, algorithms=[_jwt_algo]).get("sub")
            except Exception:
                uid = None
        if uid and not await _db.users.find_one({"id": uid}, {"_id": 1}):
            uid = None
        try:
            hub.add(ws, uid)
            await ws.send_json({"event": "crafting:hello", "data": {"ok": True}})
            while True:
                msg = await ws.receive_text()
                if msg == "ping":
                    await ws.send_text("pong")
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("[crafting] ws: %r", e)
        finally:
            hub.remove(ws)

    # ─────────────── ADMIN ───────────────
    @router.get("/admin/overview")
    async def admin_overview(user=Depends(get_admin_user)):
        mats = await _db.crafting_materials.find({}, {"_id": 0}).sort("order", 1).to_list(300)
        recipes = await _db.crafting_recipes.find({}, {"_id": 0}).sort("order", 1).to_list(500)
        settings = await get_settings()
        active = await _db.crafting_jobs.count_documents({"status": {"$in": [STATUS_CRAFTING, STATUS_COMPLETED]}})
        return {"materials": mats, "recipes": recipes, "settings": settings, "active_jobs": active}

    @router.post("/admin/materials")
    async def admin_save_material(data: MaterialIn, user=Depends(get_admin_user)):
        doc = data.model_dump()
        mid = (doc.pop("id", None) or "").strip()
        if mid:
            await _db.crafting_materials.update_one({"id": mid}, {"$set": doc}, upsert=True)
        else:
            mid = data.name.strip().lower().replace(" ", "_")[:40] or _new_id()
            if await _db.crafting_materials.find_one({"id": mid}):
                mid = f"{mid}_{_new_id()[:6]}"
            await _db.crafting_materials.insert_one({"id": mid, **doc})
        await _admin_log(user, "material_save", mid, doc)
        await hub.broadcast("material:updated", {"material_id": mid})
        return {"success": True, "id": mid}

    @router.delete("/admin/materials/{mid}")
    async def admin_del_material(mid: str, user=Depends(get_admin_user)):
        await _db.crafting_materials.update_one({"id": mid}, {"$set": {"enabled": False}})
        await _admin_log(user, "material_disable", mid, {})
        await hub.broadcast("material:updated", {"material_id": mid})
        return {"success": True}

    @router.post("/admin/recipes")
    async def admin_save_recipe(data: RecipeIn, user=Depends(get_admin_user)):
        doc = data.model_dump()
        doc["materials"] = [{"material_id": m["material_id"], "qty": int(m["qty"])} for m in doc.get("materials", [])]
        doc["uses_granted"] = max(MIN_USES, int(doc.get("uses_granted", MIN_USES)))
        rid = (doc.pop("id", None) or "").strip()
        if rid:
            await _db.crafting_recipes.update_one({"id": rid}, {"$set": doc}, upsert=True)
        else:
            rid = data.name.strip().lower().replace(" ", "_")[:40] or _new_id()
            if await _db.crafting_recipes.find_one({"id": rid}):
                rid = f"{rid}_{_new_id()[:6]}"
            await _db.crafting_recipes.insert_one({"id": rid, **doc})
        await _admin_log(user, "recipe_save", rid, {"name": doc.get("name")})
        await hub.broadcast("recipe:updated", {"recipe_id": rid})
        return {"success": True, "id": rid}

    @router.delete("/admin/recipes/{rid}")
    async def admin_del_recipe(rid: str, user=Depends(get_admin_user)):
        await _db.crafting_recipes.update_one({"id": rid}, {"$set": {"enabled": False}})
        await _admin_log(user, "recipe_disable", rid, {})
        await hub.broadcast("recipe:updated", {"recipe_id": rid})
        return {"success": True}

    @router.get("/admin/settings")
    async def admin_get_settings(user=Depends(get_admin_user)):
        return await get_settings()

    @router.put("/admin/settings")
    async def admin_put_settings(data: dict, user=Depends(get_admin_user)):
        allowed = {k: data[k] for k in DEFAULT_SETTINGS if k in data}
        await _db.crafting_settings.update_one({"_id": "crafting"}, {"$set": allowed}, upsert=True)
        await _admin_log(user, "settings_save", "crafting", allowed)
        await hub.broadcast("settings:updated", {})
        return {"success": True, "settings": await get_settings()}

    @router.post("/admin/grant")
    async def admin_grant(data: GrantIn, user=Depends(get_admin_user)):
        target = None
        if data.player_id:
            target = await _db.users.find_one({"id": data.player_id}, {"_id": 0, "id": 1, "persona_name": 1})
        elif data.steam_id:
            target = await _db.users.find_one({"steam_id": data.steam_id}, {"_id": 0, "id": 1, "persona_name": 1})
        if not target:
            raise HTTPException(404, "Jugador no encontrado.")
        if not await _db.crafting_materials.find_one({"id": data.material_id}):
            raise HTTPException(404, "Material no encontrado.")
        amt = int(data.amount)
        await _grant_materials(target["id"], data.material_id, amt)
        await _admin_log(user, "grant_materials", target["id"],
                         {"material_id": data.material_id, "amount": amt})
        await _log(target["id"], "gather", "admin_grant", {"material_id": data.material_id, "amount": amt})
        inv = [{"material_id": mid, "quantity": q} for mid, q in (await _player_qty_map(target["id"])).items()]
        await hub.send_to(target["id"], "materials:updated", {"inventory": inv})
        await hub.send_to(target["id"], "material:collected", {"material_id": data.material_id, "amount": amt})
        return {"success": True, "player_id": target["id"]}

    @router.get("/admin/logs")
    async def admin_logs(kind: str | None = None, limit: int = 100, user=Depends(get_admin_user)):
        q = {}
        if kind:
            q["kind"] = kind
        rows = await _db.crafting_logs.find(q, {"_id": 0}).sort("created_at", -1).to_list(min(500, max(1, limit)))
        return {"logs": rows}

    return router


async def _admin_log(user, action, target, meta):
    if _add_log:
        try:
            await _add_log(user.get("steam_id") or user.get("id"), f"crafting_{action}", target, meta)
        except Exception:
            pass
    await _log(None, "admin", action, {"target": target, **(meta or {})})
