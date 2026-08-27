# ═══════════════════════════════════════════════════════════════════════════
# CEMENTERIO & RESURRECCIÓN (FÓSIL)  — Backend (extraído de backend/server.py)
# The Isle Evrima — La Isla Nublar LATAM
# ---------------------------------------------------------------------------
# Este archivo es una EXTRACCIÓN de todo el módulo de Cementerio que vive dentro
# de /app/backend/server.py. Depende de objetos globales ya definidos en
# server.py, por lo que NO se ejecuta solo — es para referencia / descarga.
#
# Dependencias que provee server.py:
#   - db (Motor/MongoDB), api_router (APIRouter), app (FastAPI), logger
#   - get_current_user, get_admin_user (auth deps), add_log
#   - new_id(), now_iso(), _nonnegative_int(), _user_park_cap(), vault
#   - JWT_SECRET, JWT_ALGO, jwt   (para el WebSocket)
#   - imports: asyncio, re, random as _random, datetime, timezone, timedelta,
#              Optional, BaseModel, HTTPException, Depends, WebSocket,
#              WebSocketDisconnect
#
# WIRING EN EL STARTUP (en server.py, dentro de @app.on_event("startup")):
#     try:
#         await _cem_ensure_indexes()
#         await _cem_seed_demo()
#     except Exception:
#         logger.warning("[cemetery] startup init skipped", exc_info=True)
#
# ENDPOINTS EXPUESTOS (prefijo /api vía api_router):
#   GET    /api/cemetery/config
#   GET    /api/cemetery/feed                (privado: solo tus dinos)
#   GET    /api/cemetery/record/{id}
#   GET    /api/cemetery/hall-of-fame
#   GET    /api/cemetery/fossils
#   POST   /api/cemetery/fossils/buy
#   POST   /api/cemetery/fossils/claim-free
#   GET    /api/cemetery/transactions
#   GET    /api/cemetery/my-resurrections
#   POST   /api/cemetery/resurrect
#   POST   /api/cemetery/admin/record
#   PUT    /api/cemetery/admin/record/{id}
#   DELETE /api/cemetery/admin/record/{id}
#   POST   /api/cemetery/admin/fossils
#   PUT    /api/cemetery/admin/config
#   GET    /api/cemetery/admin/transactions
#   GET    /api/cemetery/admin/records
#   WS     /api/cemetery/ws
#
# COLECCIONES MONGO: cemetery_records, fossil_transactions, resurrected_dinos,
#   settings ({_id:"cemetery"}), users (campos: fossils, vip_coins,
#   last_free_fossil_month, last_resurrection_at)
# ═══════════════════════════════════════════════════════════════════════════

CEM_DEFAULT_FOSSIL_PRICE = 8000          # Amberiums (vip_coins) por 1 fósil
CEM_RESURRECT_COOLDOWN_H = 24            # horas de cooldown POST-resurrección
CEM_REDEEM_COOLDOWN_H = 2               # horas que el dino resucitado NO se puede redimir (anti revenge-kill)
CEM_DEINO_SLUG = "deino"                 # Deinosuchus: excepción al ahogamiento
CEM_LOCATIONS = [
    "Acceso Oeste", "Tierras Altas", "Pantano Sur", "Lago Panjura",
    "El Estuario", "Llanuras del Norte", "Delta del Río", "El Volcán",
    "El Titán", "Acceso Este", "Bosque Central", "Costa Rocosa",
]


class CemBuyFossilInput(BaseModel):
    quantity: int = 1


class CemResurrectInput(BaseModel):
    record_id: str


class CemDeathInput(BaseModel):
    # Alta de muerte (usada por el hook del mod y por el panel admin).
    species_slug: str
    species_name: Optional[str] = None
    image: Optional[str] = None
    rarity: Optional[str] = None
    type: Optional[str] = None
    diet: Optional[str] = None
    growth: float = 100.0
    age_label: Optional[str] = None
    mutations: Optional[list] = None
    prime: bool = False
    elder: bool = False
    skin_data: Optional[str] = None
    skin_name: Optional[str] = None
    stats: Optional[dict] = None
    owner_steam_id: Optional[str] = None
    owner_name: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_avatar: Optional[str] = None
    cause: str = "Combate"
    in_combat: bool = False
    killer_name: Optional[str] = None
    killer_species: Optional[str] = None
    killer_steam_id: Optional[str] = None
    location: Optional[str] = None
    playtime_minutes: int = 0
    kills: int = 0
    group: Optional[str] = None
    died_at: Optional[str] = None


class CemAdminFossilInput(BaseModel):
    user_id: Optional[str] = None
    steam_id: Optional[str] = None
    delta: Optional[int] = None
    set_to: Optional[int] = None


class CemConfigInput(BaseModel):
    fossil_price: int


class CemRecordUpdateInput(BaseModel):
    status: Optional[str] = None
    cause: Optional[str] = None
    in_combat: Optional[bool] = None
    location: Optional[str] = None
    kills: Optional[int] = None
    playtime_minutes: Optional[int] = None
    group: Optional[str] = None


def _cem_eligibility(cause: Optional[str], in_combat: bool, species_slug: str):
    """Regla del dueño: muerte por Ahogamiento DURANTE combate = NO REVIVIBLE,
    salvo el Deinosuchus, que sigue ELEGIBLE. El slug se normaliza para tolerar
    variantes que envíe el mod (deino / deinosuchus / Deinosuchus)."""
    c = (cause or "").strip().lower()
    slug = (species_slug or "").strip().lower()
    is_deino = slug.startswith("deino")
    is_drown = c in ("ahogamiento", "ahogado", "drown", "drowning")
    if is_drown and in_combat and not is_deino:
        return "NO_REVIVIBLE", "Murió ahogado durante combate — no revivible."
    return "ELEGIBLE", None


async def _cem_fossil_price() -> int:
    doc = await db.settings.find_one({"_id": "cemetery"}, {"_id": 0, "fossil_price": 1})
    if doc and isinstance(doc.get("fossil_price"), int) and doc["fossil_price"] > 0:
        return doc["fossil_price"]
    return CEM_DEFAULT_FOSSIL_PRICE


def _cem_current_month() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _cem_cooldown_until(user: dict):
    ts = user.get("last_resurrection_at")
    if not ts:
        return None
    try:
        base = datetime.fromisoformat(ts)
    except Exception:
        return None
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    until = base + timedelta(hours=CEM_RESURRECT_COOLDOWN_H)
    return until if until > datetime.now(timezone.utc) else None


def _cem_public(rec: dict) -> dict:
    rec = dict(rec)
    rec.pop("_id", None)
    return rec


async def _cem_resolve_owner_uid(rec: dict):
    """El user_id del dueño del registro (para pushes privados por WebSocket).
    Cae al steam_id cuando el registro vino del mod sin user_id."""
    o = rec.get("owner") or {}
    if o.get("user_id"):
        return o["user_id"]
    sid = o.get("steam_id")
    if sid:
        u = await db.users.find_one({"steam_id": sid}, {"_id": 0, "id": 1})
        if u:
            return u["id"]
    return None


def _cem_owner_clause(user: dict) -> dict:
    """El registro pertenece a este usuario (por user_id o por steam_id)."""
    ors = [{"owner.user_id": user["id"]}]
    if user.get("steam_id"):
        ors.append({"owner.steam_id": user["steam_id"]})
    return {"$or": ors}


async def _cem_fossil_tx(user_id: str, kind: str, amount: int, meta: dict = None):
    """kind: buy | claim_free | resurrect | admin_grant | admin_set"""
    await db.fossil_transactions.insert_one({
        "id": new_id(), "user_id": user_id, "kind": kind, "amount": amount,
        "meta": meta or {}, "created_at": now_iso(),
    })


class CemeteryHub:
    """WebSocket hub del cementerio: difunde muertes/resurrecciones a todos y
    empuja el saldo de fósiles al dueño."""
    def __init__(self):
        self.clients: dict = {}   # ws -> user_id | None

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


cemetery_hub = CemeteryHub()


async def _cem_ensure_indexes():
    try:
        await db.cemetery_records.create_index("id", unique=True)
        await db.cemetery_records.create_index("died_at")
        await db.cemetery_records.create_index("status")
        await db.cemetery_records.create_index("owner.user_id")
        await db.fossil_transactions.create_index("user_id")
        await db.fossil_transactions.create_index("created_at")
        await db.resurrected_dinos.create_index("owner_user_id")
    except Exception:
        logger.warning("[cemetery] index init skipped", exc_info=True)


async def _cem_build_record(data: CemDeathInput) -> dict:
    slug = (data.species_slug or "").strip().lower()
    cat = await db.dinosaurs.find_one({"slug": slug}, {"_id": 0}) or {}
    species_name = data.species_name or cat.get("name") or slug.title()
    image = data.image or cat.get("image")
    rarity = data.rarity or cat.get("rarity") or "Common"
    dtype = data.type or cat.get("type") or "Carnivore"
    diet = data.diet or cat.get("diet")
    status, reason = _cem_eligibility(data.cause, data.in_combat, slug)
    muts = data.mutations or []
    rec = {
        "id": new_id(),
        "dino": {
            "species_slug": slug, "species_name": species_name, "image": image,
            "rarity": rarity, "type": dtype, "diet": diet,
            "growth": round(float(data.growth or 0), 1),
            "age_label": data.age_label,
            "mutations": muts, "mutations_count": len(muts),
            "prime": bool(data.prime), "elder": bool(data.elder),
            "skin_data": data.skin_data, "skin_name": data.skin_name,
            "stats": data.stats or cat.get("stats", {}),
        },
        "owner": {
            "steam_id": data.owner_steam_id, "persona_name": data.owner_name,
            "user_id": data.owner_user_id, "avatar": data.owner_avatar,
        },
        "cause": data.cause or "Combate",
        "in_combat": bool(data.in_combat),
        "killer": ({"name": data.killer_name, "species": data.killer_species,
                    "steam_id": data.killer_steam_id} if data.killer_name else None),
        "location": data.location or _random.choice(CEM_LOCATIONS),
        "playtime_minutes": _nonnegative_int(data.playtime_minutes),
        "kills": _nonnegative_int(data.kills),
        "group": data.group,
        "died_at": data.died_at or now_iso(),
        "status": status,
        "not_revivable_reason": reason,
        "resurrected_at": None, "resurrected_by": None, "vault_row_id": None,
        "created_at": now_iso(),
    }
    return rec


# ── Config pública ──────────────────────────────────────────────────────────
@api_router.get("/cemetery/config")
async def cemetery_config():
    price = await _cem_fossil_price()
    return {"fossil_price": price, "amber_per_fossil": price,
            "resurrection_cooldown_hours": CEM_RESURRECT_COOLDOWN_H,
            "redeem_cooldown_hours": CEM_REDEEM_COOLDOWN_H,
            "deino_exception": True}


# ── Feed / búsqueda / filtros  (PRIVADO: cada usuario ve SOLO sus propios dinos) ──
@api_router.get("/cemetery/feed")
async def cemetery_feed(
    search: Optional[str] = None, species: Optional[str] = None,
    status: Optional[str] = None, rarity: Optional[str] = None,
    cause: Optional[str] = None, sort: str = "recent",
    limit: int = 60, skip: int = 0,
    user=Depends(get_current_user),
):
    owner = _cem_owner_clause(user)
    and_list = [owner]
    if species:
        and_list.append({"dino.species_slug": species.strip().lower()})
    if status:
        and_list.append({"status": status.strip().upper()})
    if rarity:
        and_list.append({"dino.rarity": rarity})
    if cause:
        and_list.append({"cause": cause})
    if search:
        rx = {"$regex": re.escape(search.strip()), "$options": "i"}
        and_list.append({"$or": [{"dino.species_name": rx}, {"killer.name": rx}, {"group": rx}]})
    q = and_list[0] if len(and_list) == 1 else {"$and": and_list}
    sort_map = {
        "recent": [("died_at", -1)], "oldest": [("died_at", 1)],
        "kills": [("kills", -1)], "playtime": [("playtime_minutes", -1)],
        "growth": [("dino.growth", -1)],
    }
    order = sort_map.get(sort, sort_map["recent"])
    total = await db.cemetery_records.count_documents(q)
    cur = db.cemetery_records.find(q, {"_id": 0}).sort(order).skip(max(0, skip)).limit(min(200, max(1, limit)))
    items = await cur.to_list(200)
    stats = {
        "total": await db.cemetery_records.count_documents(owner),
        "eligible": await db.cemetery_records.count_documents({"$and": [owner, {"status": "ELEGIBLE"}]}),
        "resurrected": await db.cemetery_records.count_documents({"$and": [owner, {"status": "RESUCITADO"}]}),
        "not_revivable": await db.cemetery_records.count_documents({"$and": [owner, {"status": "NO_REVIVIBLE"}]}),
    }
    return {"items": items, "total": total, "stats": stats}


@api_router.get("/cemetery/record/{record_id}")
async def cemetery_record(record_id: str, user=Depends(get_current_user)):
    rec = await db.cemetery_records.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    o = rec.get("owner") or {}
    is_owner = (o.get("user_id") and o.get("user_id") == user["id"]) or \
               (o.get("steam_id") and o.get("steam_id") == user.get("steam_id"))
    if not is_owner and user.get("role") != "admin":
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return rec


# ── Salón de la Fama (PRIVADO: solo tus propios dinos caídos) ─────────────────
@api_router.get("/cemetery/hall-of-fame")
async def cemetery_hall_of_fame(user=Depends(get_current_user)):
    owner = _cem_owner_clause(user)
    async def top(field, extra=None):
        q = {"$and": [owner, extra]} if extra else owner
        cur = db.cemetery_records.find(q, {"_id": 0}).sort(field, -1).limit(5)
        return await cur.to_list(5)
    return {
        "longest_survival": await top("playtime_minutes"),
        "most_kills": await top("kills"),
        "biggest": await top("dino.growth", {"dino.prime": True}),
        "resurrected": await top("resurrected_at", {"status": "RESUCITADO"}),
    }


# ── Saldo de fósiles / estado del jugador ────────────────────────────────────
@api_router.get("/cemetery/fossils")
async def cemetery_fossils(user=Depends(get_current_user)):
    price = await _cem_fossil_price()
    can_claim = user.get("last_free_fossil_month") != _cem_current_month()
    until = _cem_cooldown_until(user)
    return {
        "fossils": _nonnegative_int(user.get("fossils")),
        "amber_balance": _nonnegative_int(user.get("vip_coins")),
        "fossil_price": price,
        "can_claim_free": can_claim,
        "cooldown_active": bool(until),
        "cooldown_until": until.isoformat() if until else None,
    }


@api_router.post("/cemetery/fossils/buy")
async def cemetery_buy_fossils(data: CemBuyFossilInput, user=Depends(get_current_user)):
    qty = int(data.quantity or 0)
    if qty < 1:
        raise HTTPException(status_code=400, detail="Cantidad inválida")
    price = await _cem_fossil_price()
    cost = qty * price
    if _nonnegative_int(user.get("vip_coins")) < cost:
        raise HTTPException(status_code=400, detail=f"Amberiums insuficientes. Necesitas {cost:,}")
    res = await db.users.update_one(
        {"id": user["id"], "vip_coins": {"$gte": cost}},
        {"$inc": {"vip_coins": -cost, "fossils": qty}})
    if res.modified_count != 1:
        raise HTTPException(status_code=400, detail="Amberiums insuficientes")
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "fossils": 1, "vip_coins": 1})
    await _cem_fossil_tx(user["id"], "buy", qty, {"cost_amber": cost, "unit_price": price})
    await add_log(user.get("persona_name"), "cem_buy_fossil", user["id"], {"qty": qty, "cost": cost})
    payload = {"type": "fossil_balance", "fossils": fresh["fossils"], "amber_balance": fresh["vip_coins"]}
    await cemetery_hub.push_to_user(user["id"], payload)
    return {"success": True, **payload, "purchased": qty}


@api_router.post("/cemetery/fossils/claim-free")
async def cemetery_claim_free(user=Depends(get_current_user)):
    month = _cem_current_month()
    # Idempotente por mes calendario: sólo cuenta si el $set del mes gana.
    res = await db.users.update_one(
        {"id": user["id"], "last_free_fossil_month": {"$ne": month}},
        {"$set": {"last_free_fossil_month": month}, "$inc": {"fossils": 1}})
    if res.modified_count != 1:
        raise HTTPException(status_code=400, detail="Ya reclamaste tu fósil gratis de este mes")
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "fossils": 1, "vip_coins": 1})
    await _cem_fossil_tx(user["id"], "claim_free", 1, {"month": month})
    await add_log(user.get("persona_name"), "cem_claim_free", user["id"], {"month": month})
    payload = {"type": "fossil_balance", "fossils": fresh["fossils"], "amber_balance": fresh["vip_coins"]}
    await cemetery_hub.push_to_user(user["id"], payload)
    return {"success": True, **payload}


@api_router.get("/cemetery/transactions")
async def cemetery_transactions(user=Depends(get_current_user)):
    cur = db.fossil_transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(100)
    return {"items": await cur.to_list(100)}


@api_router.get("/cemetery/my-resurrections")
async def cemetery_my_resurrections(user=Depends(get_current_user)):
    cur = db.resurrected_dinos.find({"owner_user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(100)
    return {"items": await cur.to_list(100)}


# ── Resurrección ─────────────────────────────────────────────────────────────
@api_router.post("/cemetery/resurrect")
async def cemetery_resurrect(data: CemResurrectInput, user=Depends(get_current_user)):
    rec = await db.cemetery_records.find_one({"id": data.record_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if rec.get("status") == "RESUCITADO":
        raise HTTPException(status_code=400, detail="Este dino ya fue resucitado")
    if rec.get("status") == "NO_REVIVIBLE":
        raise HTTPException(status_code=400, detail=rec.get("not_revivable_reason") or "Este dino no es revivible")
    # Solo el dueño (por user_id o steam_id).
    owner = rec.get("owner") or {}
    is_owner = (owner.get("user_id") and owner.get("user_id") == user["id"]) or \
               (owner.get("steam_id") and owner.get("steam_id") == user.get("steam_id"))
    if not is_owner:
        raise HTTPException(status_code=403, detail="Solo el dueño del dino puede resucitarlo")
    # Cooldown.
    until = _cem_cooldown_until(user)
    if until:
        raise HTTPException(status_code=400, detail="Estás en cooldown de resurrección (24h)")
    # Saldo de fósiles.
    if _nonnegative_int(user.get("fossils")) < 1:
        raise HTTPException(status_code=400, detail="No tienes Fósiles. Compra o reclama tu fósil gratis mensual")
    # Cobra 1 fósil + marca cooldown, atómico.
    now = now_iso()
    upd = await db.users.update_one(
        {"id": user["id"], "fossils": {"$gte": 1}},
        {"$inc": {"fossils": -1}, "$set": {"last_resurrection_at": now}})
    if upd.modified_count != 1:
        raise HTTPException(status_code=400, detail="No tienes Fósiles")
    # Marca el registro RESUCITADO (idempotencia: sólo si seguía revivible).
    # redeem_cooldown_until: el dino NO se puede redimir/spawnear en 2h (anti revenge-kill).
    redeem_until = (datetime.now(timezone.utc) + timedelta(hours=CEM_REDEEM_COOLDOWN_H)).isoformat()
    claimed = await db.cemetery_records.update_one(
        {"id": rec["id"], "status": "ELEGIBLE"},
        {"$set": {"status": "RESUCITADO", "resurrected_at": now, "resurrected_by": user["id"],
                  "redeem_cooldown_until": redeem_until}})
    if claimed.modified_count != 1:
        # Reembolsa el fósil si alguien ganó la carrera.
        await db.users.update_one({"id": user["id"]}, {"$inc": {"fossils": 1}})
        raise HTTPException(status_code=400, detail="Este dino ya fue resucitado")
    dino = rec.get("dino") or {}
    # Intenta escribir a la bóveda REAL del juego (solo funciona con el servidor
    # Windows online); en preview cae con gracia al inventario web.
    vault_row_id = None
    sid = user.get("steam_id")
    if sid:
        pd = {
            "dino": dino.get("species_name"), "growth": (dino.get("growth", 0) or 0) / 100.0,
            "is_prime": dino.get("prime"), "is_elder": dino.get("elder"),
            "mutations": dino.get("mutations") or [], "skin_data": dino.get("skin_data") or "",
            "steam_id": sid,
        }
        try:
            row = await asyncio.to_thread(vault.save_parked, sid, "", pd, _user_park_cap(user))
            vault_row_id = int(row) if row is not None else None
        except Exception:
            vault_row_id = None
    # Guarda el dino restaurado del lado web (inventario del jugador).
    restored = {
        "id": new_id(), "owner_user_id": user["id"], "owner_steam_id": sid,
        "record_id": rec["id"], "dino": dino, "vault_row_id": vault_row_id,
        "redeemable_at": redeem_until, "created_at": now,
    }
    await db.resurrected_dinos.insert_one(dict(restored))
    if vault_row_id is not None:
        await db.cemetery_records.update_one({"id": rec["id"]}, {"$set": {"vault_row_id": vault_row_id}})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "fossils": 1, "vip_coins": 1})
    await _cem_fossil_tx(user["id"], "resurrect", -1,
                         {"record_id": rec["id"], "species": dino.get("species_name"),
                          "vault_row_id": vault_row_id})
    await add_log(user.get("persona_name"), "cem_resurrect", user["id"],
                  {"record_id": rec["id"], "species": dino.get("species_name")})
    fresh_rec = await db.cemetery_records.find_one({"id": rec["id"]}, {"_id": 0})
    cooldown_until = _cem_cooldown_until({"last_resurrection_at": now})
    # Privado: solo el dueño (que aquí es quien resucita) recibe el update en vivo.
    await cemetery_hub.push_to_user(user["id"], {"type": "cemetery_resurrection", "record": fresh_rec})
    await cemetery_hub.push_to_user(user["id"], {
        "type": "fossil_balance", "fossils": fresh["fossils"], "amber_balance": fresh["vip_coins"]})
    return {
        "success": True, "record": fresh_rec, "fossils": fresh["fossils"],
        "restored": _cem_public(restored), "vault_row_id": vault_row_id,
        "vault_written": vault_row_id is not None,
        "cooldown_until": cooldown_until.isoformat() if cooldown_until else None,
        "redeemable_at": redeem_until,
    }


# ── Alta de muerte (hook del mod / admin) ────────────────────────────────────
@api_router.post("/cemetery/admin/record")
async def cemetery_admin_add(data: CemDeathInput, admin=Depends(get_admin_user)):
    rec = await _cem_build_record(data)
    await db.cemetery_records.insert_one(dict(rec))
    await add_log(admin.get("persona_name"), "cem_add_record", rec["id"],
                  {"species": rec["dino"]["species_name"], "status": rec["status"]})
    owner_uid = await _cem_resolve_owner_uid(rec)
    if owner_uid:
        await cemetery_hub.push_to_user(owner_uid, {"type": "cemetery_death", "record": _cem_public(rec)})
    return {"success": True, "record": _cem_public(rec)}


@api_router.put("/cemetery/admin/record/{record_id}")
async def cemetery_admin_update(record_id: str, data: CemRecordUpdateInput, admin=Depends(get_admin_user)):
    rec = await db.cemetery_records.find_one({"id": record_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    changes = {}
    for f in ("cause", "location", "group"):
        v = getattr(data, f)
        if v is not None:
            changes[f] = v
    if data.in_combat is not None:
        changes["in_combat"] = bool(data.in_combat)
    if data.kills is not None:
        changes["kills"] = _nonnegative_int(data.kills)
    if data.playtime_minutes is not None:
        changes["playtime_minutes"] = _nonnegative_int(data.playtime_minutes)
    # Recalcula elegibilidad si cambió causa/combate (nunca pisa un RESUCITADO).
    if rec.get("status") != "RESUCITADO" and ("cause" in changes or "in_combat" in changes):
        st, reason = _cem_eligibility(changes.get("cause", rec.get("cause")),
                                      changes.get("in_combat", rec.get("in_combat")),
                                      rec["dino"]["species_slug"])
        changes["status"] = st
        changes["not_revivable_reason"] = reason
    if data.status is not None:
        st = data.status.strip().upper()
        if st in ("ELEGIBLE", "NO_REVIVIBLE", "RESUCITADO"):
            changes["status"] = st
    if changes:
        await db.cemetery_records.update_one({"id": record_id}, {"$set": changes})
    fresh = await db.cemetery_records.find_one({"id": record_id}, {"_id": 0})
    await add_log(admin.get("persona_name"), "cem_update_record", record_id, changes)
    owner_uid = await _cem_resolve_owner_uid(fresh)
    if owner_uid:
        await cemetery_hub.push_to_user(owner_uid, {"type": "cemetery_update", "record": fresh})
    return {"success": True, "record": fresh}


@api_router.delete("/cemetery/admin/record/{record_id}")
async def cemetery_admin_delete(record_id: str, admin=Depends(get_admin_user)):
    rec = await db.cemetery_records.find_one({"id": record_id}, {"_id": 0})
    res = await db.cemetery_records.delete_one({"id": record_id})
    if res.deleted_count != 1:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    await add_log(admin.get("persona_name"), "cem_delete_record", record_id, {})
    owner_uid = await _cem_resolve_owner_uid(rec) if rec else None
    if owner_uid:
        await cemetery_hub.push_to_user(owner_uid, {"type": "cemetery_delete", "record_id": record_id})
    return {"success": True}


@api_router.post("/cemetery/admin/fossils")
async def cemetery_admin_fossils(data: CemAdminFossilInput, admin=Depends(get_admin_user)):
    q = {}
    if data.user_id:
        q = {"id": data.user_id}
    elif data.steam_id:
        q = {"steam_id": data.steam_id}
    else:
        raise HTTPException(status_code=400, detail="Indica user_id o steam_id")
    target = await db.users.find_one(q, {"_id": 0, "id": 1, "persona_name": 1, "fossils": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if data.set_to is not None:
        new_val = max(0, int(data.set_to))
        await db.users.update_one({"id": target["id"]}, {"$set": {"fossils": new_val}})
        await _cem_fossil_tx(target["id"], "admin_set", new_val, {"by": admin.get("persona_name")})
    elif data.delta is not None:
        await db.users.update_one({"id": target["id"]}, {"$inc": {"fossils": int(data.delta)}})
        # Evita negativos.
        cur = await db.users.find_one({"id": target["id"]}, {"_id": 0, "fossils": 1})
        if _nonnegative_int(cur.get("fossils")) != cur.get("fossils"):
            await db.users.update_one({"id": target["id"]}, {"$set": {"fossils": 0}})
        await _cem_fossil_tx(target["id"], "admin_grant", int(data.delta), {"by": admin.get("persona_name")})
    else:
        raise HTTPException(status_code=400, detail="Indica delta o set_to")
    fresh = await db.users.find_one({"id": target["id"]}, {"_id": 0, "fossils": 1, "persona_name": 1})
    await add_log(admin.get("persona_name"), "cem_admin_fossils", target["id"],
                  {"delta": data.delta, "set_to": data.set_to})
    await cemetery_hub.push_to_user(target["id"], {
        "type": "fossil_balance", "fossils": _nonnegative_int(fresh.get("fossils"))})
    return {"success": True, "user_id": target["id"],
            "persona_name": fresh.get("persona_name"), "fossils": _nonnegative_int(fresh.get("fossils"))}


@api_router.put("/cemetery/admin/config")
async def cemetery_admin_config(data: CemConfigInput, admin=Depends(get_admin_user)):
    if data.fossil_price < 1:
        raise HTTPException(status_code=400, detail="El precio debe ser mayor a 0")
    await db.settings.update_one({"_id": "cemetery"},
                                 {"$set": {"fossil_price": int(data.fossil_price)}}, upsert=True)
    await add_log(admin.get("persona_name"), "cem_set_price", None, {"price": data.fossil_price})
    await cemetery_hub.broadcast({"type": "cemetery_config", "fossil_price": int(data.fossil_price)})
    return {"success": True, "fossil_price": int(data.fossil_price)}


@api_router.get("/cemetery/admin/transactions")
async def cemetery_admin_transactions(admin=Depends(get_admin_user)):
    cur = db.fossil_transactions.find({}, {"_id": 0}).sort("created_at", -1).limit(200)
    return {"items": await cur.to_list(200)}


@api_router.get("/cemetery/admin/records")
async def cemetery_admin_records(search: Optional[str] = None, admin=Depends(get_admin_user)):
    q: dict = {}
    if search:
        rx = {"$regex": re.escape(search.strip()), "$options": "i"}
        q["$or"] = [{"dino.species_name": rx}, {"owner.persona_name": rx},
                    {"owner.steam_id": rx}, {"killer.name": rx}]
    cur = db.cemetery_records.find(q, {"_id": 0}).sort("died_at", -1).limit(200)
    return {"items": await cur.to_list(200)}


# ── WebSocket del cementerio ─────────────────────────────────────────────────
@app.websocket("/api/cemetery/ws")
async def cemetery_ws(ws: WebSocket):
    await ws.accept()
    user_id = None
    try:
        token = ws.query_params.get("token")
        if token:
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
                user_id = payload.get("sub")
            except Exception:
                user_id = None
    except Exception:
        pass
    try:
        await cemetery_hub.add(ws, user_id)
        await ws.send_json({"type": "cemetery_hello", "ts": now_iso()})
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[cemetery] ws: {e}")
    finally:
        await cemetery_hub.remove(ws)


# ── Semilla demo del cementerio (preview) ────────────────────────────────────
async def _cem_seed_demo():
    if await db.cemetery_records.count_documents({}) > 0:
        return
    demo = await db.users.find_one({"steam_id": "demo_0000000001"}, {"_id": 0, "id": 1, "steam_id": 1, "persona_name": 1, "avatar": 1})
    owner_uid = demo.get("id") if demo else None
    owner_sid = demo.get("steam_id") if demo else "demo_0000000001"
    owner_name = demo.get("persona_name") if demo else "Demo Survivor"
    owner_av = demo.get("avatar") if demo else None
    seeds = [
        ("trex", "Combate", False, 100.0, True, 4820, 31, "Clan Ápice", "Tyrannosaurus rival", "Tyrannosaurus Rex", "Tierras Altas"),
        ("deino", "Ahogamiento", True, 88.0, False, 2100, 12, None, "Sarcosuchus", "Deinosuchus", "Lago Panjura"),
        ("carno", "Ahogamiento", True, 74.0, False, 1500, 6, "Manada Roja", "Allosaurus", "Allosaurus", "Delta del Río"),
        ("raptor", "Emboscada", False, 62.0, False, 900, 9, "Manada Roja", "Omniraptor", "Omniraptor", "Bosque Central"),
        ("trike", "Combate", True, 100.0, True, 6100, 18, "Rebaño", "Tyrannosaurus Rex", "Tyrannosaurus Rex", "Llanuras del Norte"),
        ("allo", "Inanición", False, 55.0, False, 700, 3, None, None, None, "Acceso Oeste"),
        ("cerato", "Caída", False, 48.0, False, 620, 2, None, None, None, "El Volcán"),
        ("stego", "Combate", True, 91.0, True, 3300, 7, "Rebaño", "Ceratosaurus", "Ceratosaurus", "Pantano Sur"),
        ("dilo", "Ahogamiento", False, 40.0, False, 300, 1, None, None, None, "El Estuario"),
        ("ptera", "Combate", True, 70.0, False, 1100, 4, None, "Omniraptor", "Omniraptor", "Costa Rocosa"),
        ("troodon", "Enfermedad", False, 66.0, False, 980, 5, "Pack Nocturno", None, None, "Acceso Este"),
        ("diablo", "Combate", True, 100.0, True, 5400, 14, "Rebaño", "Tyrannosaurus Rex", "Tyrannosaurus Rex", "El Titán"),
    ]
    now = datetime.now(timezone.utc)
    for i, (slug, cause, in_combat, growth, prime, pt, kills, group, kname, kspec, loc) in enumerate(seeds):
        data = CemDeathInput(
            species_slug=slug, growth=growth, prime=prime,
            mutations=(["Metabolismo Eficiente", "Piel Gruesa"] if prime else []),
            owner_steam_id=owner_sid, owner_name=owner_name, owner_user_id=owner_uid, owner_avatar=owner_av,
            cause=cause, in_combat=in_combat, killer_name=kname, killer_species=kspec,
            location=loc, playtime_minutes=pt, kills=kills, group=group,
            died_at=(now - timedelta(hours=i * 7 + 2)).isoformat(),
            skin_name=("Skin Legendaria" if prime else None),
        )
        rec = await _cem_build_record(data)
        await db.cemetery_records.insert_one(dict(rec))
    logger.info("[cemetery] demo seed inserted %d records", len(seeds))

# ── end Cementerio ────────────────────────────────────────────────────────────
