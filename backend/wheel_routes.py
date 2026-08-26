# -*- coding: utf-8 -*-
"""Nublar Spin — the daily free wheel (Mini Juegos tab). La Isla Nublar.

Owner ask (2026-08-23, via Ishaq): a daily free spin wheel like Forza Horizon;
rewards = skins, dinos, growth/diet tokens, zombie dinos, prime dinos, PrimeMeat
and Amberium; lives in the casino tab; Patreon = more spins a day, each tier +1.
The reward table is ours to choose. His "Nublar Spin" bundle (an extract from an
older fork of this codebase) supplied the carousel frontend; this backend is
built on THIS site's proven lanes instead of the bundle's, because the bundle
read-then-wrote the cooldown (concurrent double-spin), granted dinos into a
Mongo shape the vault never reads, wrote token rows the Battle Pass refuses,
and had no replay wall.

WHY THIS MODULE NEVER IMPORTS server.py
    Same reason battle_pass.py and crash_game.py do not: server.py imports this
    one. The Mongo handle, the auth dependencies and the helper callables
    arrive once through configure(). glitch_catalog / seed_data /
    mutation_catalog / game_telemetry / vault / battle_pass are leaf imports.

WHAT TOUCHES WHAT
    Spins-per-day  users.wheel_day / wheel_spins_today / wheel_bonus_spins.
                   Every claim is ONE conditional update_one (the casino
                   settle-race law: a read-then-write here mints spins). The
                   day key moves FORWARD only — a clock that jumps back cannot
                   re-pay a day already paid. The Patreon fields the allowance
                   was computed from are pinned in the filter, so a downgrade
                   racing a spin can never win an extra one.
    Draw           the casino's own provably-fair seeds (HMAC roll, nonce++),
                   injected from server.py; the answer carries the same proof
                   shape crates return.
    Replay         one op document per spin, _id = "lin:wheel:<user>:<cmd>"
                   (store_orders precedent): the request that loses the insert
                   hands its claim back and answers with the recorded spin.
                   States: drawn -> granting -> granted | grant_failed. A spin
                   whose grant failed is RESTORED to the player, never eaten.
    PrimeMeat      users.coins  $inc + add_transaction("normal") — crate lane.
    Amberium       users.vip_coins $inc + add_transaction("vip") — crate lane.
    Tokens         battle_pass._grant_token rows (bp_token_<growth|diet>_<basic|premium>,
                   category "Tokens"), redeemed through the Battle Pass live lane.
    Glitch skin    db.reward_skins upsert, byte-identical to the crate grant;
                   pool = glitch_catalog.crate_eligible. Cards render NAME +
                   colour proximity, never a picture (fleet order 2026-08-11).
    Dinos          vault.save_parked() with the store/Battle-Pass payload shape
                   (0-sentinel vitals, no elder_stacks key, prime == elder,
                   mint_prime_state for prime) and cap=0: a full Bóveda never
                   eats a won dino (the PI wheel ruling). Mutations are
                   diet-legal for the species and seeded by the op key, so a
                   replayed grant can never reroll.
    Vial GEN-Ø     an inventory consumable (category "Consumables"). USAR sets
                   gen0_state.percent = 100 for the PLAYER — exactly what four
                   facility visits do — and the LIVE zombify sweep + mod
                   transformation take over (zero new mod surface, no SID-only
                   action fired after a redeem). The vial is consumed only
                   after the state write landed; a refused write hands it back.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import battle_pass
import game_telemetry
import glitch_catalog
import mutation_catalog
import seed_data
import vault

logger = logging.getLogger("laislanublar.wheel")

router = APIRouter()

# ---------------------------------------------------------------------------
# configure() — dependency injection (battle_pass / crash_game pattern)
# ---------------------------------------------------------------------------
_db = None
_current_user_dep = None
_owner_user_dep = None
_add_transaction = None
_add_log = None
_new_id = None
_now_iso = None
_patreon_tier_key = None
_pf = None            # dict: get_active(user_id) / float / float_i / pick
_GLITCH_USES_PER_WIN = 3
_indexes_ready = False

# The five tiers, lowest first. An EXPLICIT ladder: no rank is derived from a
# dict's insertion order or from an Amberium amount (Codex finding, 08-23).
PATREON_RANK = {"juvie": 1, "sub": 2, "adult": 3, "elder": 4, "apex": 5}
PATREON_ACTIVE = "active_patron"


def configure(mongo_db, *, current_user_dep, owner_user_dep, add_transaction,
              add_log, new_id, now_iso, patreon_tier_key, pf,
              glitch_uses_per_win=3) -> None:
    global _db, _current_user_dep, _owner_user_dep, _add_transaction, _add_log
    global _new_id, _now_iso, _patreon_tier_key, _pf, _GLITCH_USES_PER_WIN
    global _indexes_ready
    _db = mongo_db
    _current_user_dep = current_user_dep
    _owner_user_dep = owner_user_dep
    _add_transaction = add_transaction
    _add_log = add_log
    _new_id = new_id
    _now_iso = now_iso
    _patreon_tier_key = patreon_tier_key
    _pf = pf
    _GLITCH_USES_PER_WIN = int(glitch_uses_per_win)
    _indexes_ready = False
    logger.info("[wheel] configured")


# Late-bound auth (battle_pass._require_user precedent): FastAPI resolved the
# Depends objects at decoration time, before configure() ran, so the wrappers
# close over the module globals instead.
_security = HTTPBearer(auto_error=False)


async def _require_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_security)):
    if _current_user_dep is None:
        raise HTTPException(503, "La ruleta no está disponible ahora mismo.")
    return await _current_user_dep(creds)


async def _require_owner(user=Depends(_require_user)):
    if _owner_user_dep is None:
        raise HTTPException(503, "La ruleta no está disponible ahora mismo.")
    return await _owner_user_dep(user)


async def ensure_indexes() -> None:
    """Additive, idempotent. steam_id UNIQUE on gen0_state matches the
    tracker's own one-doc-per-sid invariant and is what makes the vial's
    write race-safe (a loser's upsert dies on the index, never as a twin)."""
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await _db.wheel_spins.create_index([("user_id", 1), ("at", -1)])
        await _db.wheel_spins.create_index([("at", -1)])
        await _db.gen0_state.create_index("steam_id", unique=True)
        _indexes_ready = True
    except Exception as e:  # a legacy twin doc would surface here, by name
        logger.warning("[wheel] index build: %r", e)


# ---------------------------------------------------------------------------
# Reward table — the owner said "u make all the rewards. choose wisely."
# Calibration: crates pay 1.5k–25k PM (crate price 10k/25k), dino slots cost
# 400–3.000 Amberium, Patreon amber stipends 18k–80k / 2 weeks. A daily FREE
# spin mostly lands 1k–2.5k PM or a token; the showpieces stay ~1–1.5%.
# ---------------------------------------------------------------------------
KINDS = ("primemeat", "amberium", "growth_token", "diet_token",
         "glitch_skin", "dino_basic", "dino_prime", "gen0_vial")
ICONS = ("coin", "coin_big", "amberium", "amberium_big", "diet", "growth",
         "growth_big", "skin", "dino", "crown", "vial", "gift")
VIAL_ITEM_ID = "wheel_gen0_vial"
CONFIG_ID = "wheel_config"

DEFAULT_SEGMENTS = [
    {"key": "s0",  "kind": "primemeat",    "label": "1.000 PrimeMeat",      "amount": 1000,  "weight": 20,  "color": "#22C55E", "icon": "coin"},
    {"key": "s1",  "kind": "primemeat",    "label": "2.500 PrimeMeat",      "amount": 2500,  "weight": 16,  "color": "#10B981", "icon": "coin"},
    {"key": "s2",  "kind": "primemeat",    "label": "7.500 PrimeMeat",      "amount": 7500,  "weight": 10,  "color": "#059669", "icon": "coin_big"},
    {"key": "s3",  "kind": "primemeat",    "label": "20.000 PrimeMeat",     "amount": 20000, "weight": 5,   "color": "#0D9488", "icon": "coin_big"},
    {"key": "s4",  "kind": "amberium",     "label": "100 Amberium",         "amount": 100,   "weight": 12,  "color": "#F59E0B", "icon": "amberium"},
    {"key": "s5",  "kind": "amberium",     "label": "250 Amberium",         "amount": 250,   "weight": 7,   "color": "#F97316", "icon": "amberium"},
    {"key": "s6",  "kind": "amberium",     "label": "1.000 Amberium",       "amount": 1000,  "weight": 2.5, "color": "#EA580C", "icon": "amberium_big"},
    {"key": "s7",  "kind": "diet_token",   "label": "Ficha de Dieta",       "amount": 1,     "weight": 8,   "color": "#EC4899", "icon": "diet"},
    {"key": "s8",  "kind": "growth_token", "label": "Ficha de Crecimiento", "amount": 1,     "weight": 8,   "color": "#A78BFA", "icon": "growth",     "flavor": "basic"},
    {"key": "s9",  "kind": "growth_token", "label": "Crecimiento Premium",  "amount": 1,     "weight": 2,   "color": "#8B5CF6", "icon": "growth_big", "flavor": "premium"},
    {"key": "s10", "kind": "glitch_skin",  "label": "Skin Glitch",          "amount": 1,     "weight": 3,   "color": "#38BDF8", "icon": "skin"},
    {"key": "s11", "kind": "dino_basic",   "label": "Dino Salvaje",         "amount": 1,     "weight": 4,   "color": "#0EA5E9", "icon": "dino"},
    {"key": "s12", "kind": "dino_prime",   "label": "Dino Prime",           "amount": 1,     "weight": 1,   "color": "#D4AF37", "icon": "crown"},
    {"key": "s13", "kind": "gen0_vial",    "label": "Vial GEN-Ø",           "amount": 1,     "weight": 1.5, "color": "#84CC16", "icon": "vial"},
]

# Species pools resolved against seed_data at spin time; unknown slugs are
# dropped with a warning, an EMPTY resolved pool refuses the spin BEFORE any
# allowance is spent (the PI wheel law: prove every plate payable first).
DEFAULT_DINO_POOLS = {
    "basic": ["hypsi", "dryo", "galli", "beipiao", "pachy", "tenonto", "maia",
              "kentro", "stego", "ptera", "herrera", "austro", "dilo", "allo", "raptor"],
    "prime": ["carno", "deino", "cerato", "troodon", "diablo", "trex", "trike"],
}

DEFAULT_BASE_SPINS = 1          # everyone's free daily spin
DEFAULT_PATREON_BONUS = True    # +1 per tier rank (juvie..apex → +1..+5)
MAX_BASE_SPINS = 24
MAX_SEGMENTS = 24
MAX_AMOUNT = {"primemeat": 5_000_000, "amberium": 100_000}
HISTORY_LIMIT = 30
RECENT_LIMIT = 8
WS_MAX_CLIENTS = 300
GRANTING_STALE_S = 30
MUTS_PRIME = 4                  # the Battle Pass / shop prime payload
MUTS_BASIC = 3
DINO_GROWTH = 0.75
DIET_BASIC = 0.5                # ROW_DINO_RULES "regular" diet (150%)
DIET_PRIME = 1.0                # ROW_DINO_RULES "premium" diet (300%)
CMD_RE = re.compile(r"^[A-Za-z0-9_.:-]{6,64}$")

_CLASS_BY_SLUG = {slug: f"BP_{species}_C"
                  for species, slug in game_telemetry.EVRIMA_SPECIES.items()}


def default_config() -> dict:
    return {
        "enabled": True,
        "base_spins": DEFAULT_BASE_SPINS,
        "patreon_bonus": DEFAULT_PATREON_BONUS,
        "segments": [dict(s) for s in DEFAULT_SEGMENTS],
        "dino_pools": {k: list(v) for k, v in DEFAULT_DINO_POOLS.items()},
        "revision": 0,
        "updated_at": None,
    }


def _coerce_config(doc: Optional[dict]) -> dict:
    """A stale row of the wrong TYPE must not 500 the wheel (PI finding #6):
    type-check every field against the shipped defaults, fall back per field."""
    out = default_config()
    for k, v in (doc or {}).items():
        if k == "_id":
            continue
        if k == "segments" and not isinstance(v, list):
            continue
        if k == "dino_pools" and not isinstance(v, dict):
            continue
        if k in ("enabled", "patreon_bonus"):
            v = bool(v)
        if k in ("base_spins", "revision"):
            try:
                v = max(0, min(MAX_BASE_SPINS if k == "base_spins" else 10**9, int(v)))
            except (TypeError, ValueError):
                continue
        out[k] = v
    return out


async def _get_config() -> dict:
    doc = await _db.wheel_config.find_one({"_id": CONFIG_ID})
    if doc is None:
        fresh = default_config()
        fresh["updated_at"] = _now_iso()
        try:
            await _db.wheel_config.insert_one({"_id": CONFIG_ID, **fresh})
        except DuplicateKeyError:
            pass  # a racer seeded it — _id is the wall, read it back
        doc = await _db.wheel_config.find_one({"_id": CONFIG_ID})
    return _coerce_config(doc)


# ---------------------------------------------------------------------------
# Rarity — canonical rules first (cannot be broken from admin), then weight.
# ---------------------------------------------------------------------------
def rarity_for(seg: dict) -> str:
    kind = str(seg.get("kind") or "")
    if kind in ("dino_prime", "gen0_vial"):
        return "legendary"
    if kind in ("glitch_skin", "dino_basic", "growth_token", "diet_token"):
        return "epic"
    if kind == "amberium":
        return "epic" if float(seg.get("amount") or 0) >= 1000 else "rare"
    try:
        w = float(seg.get("weight") or 0)
    except (TypeError, ValueError):
        w = 0.0
    if w >= 15:
        return "common"
    if w >= 3:
        return "rare"
    if w >= 1:
        return "epic"
    return "legendary"


def _weight(seg: dict) -> float:
    try:
        w = float(seg.get("weight") or 0)
    except (TypeError, ValueError):
        return 0.0
    return w if (w == w and w > 0 and w != float("inf")) else 0.0


def public_segments(segments: list) -> list:
    """Strip weights; odds are computed over the WHOLE table so a single
    segment never reports itself as 100% (bundle defect #15)."""
    total = sum(_weight(s) for s in segments) or 1.0
    out = []
    for s in segments:
        pub = {
            "key": s.get("key"), "kind": s.get("kind"), "label": s.get("label"),
            "amount": s.get("amount"), "color": s.get("color") or "#8B5CF6",
            "icon": s.get("icon") or "gift", "rarity": rarity_for(s),
            "probability": round((_weight(s) / total) * 100.0, 2),
        }
        if s.get("kind") == "growth_token":
            pub["flavor"] = s.get("flavor") or "basic"
        out.append(pub)
    return out


def _public_one(seg: dict, segments: list) -> dict:
    """One segment's public view with its odds taken from the full table."""
    for pub in public_segments(segments):
        if pub["key"] == seg.get("key"):
            return pub
    pub = public_segments([seg])[0]
    pub["probability"] = None
    return pub


# ---------------------------------------------------------------------------
# Spins-per-day
# ---------------------------------------------------------------------------
def today_key(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def next_reset_iso(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


def tier_rank(user: dict) -> tuple:
    """(rank, tier_key) — rank 0 unless the membership is EXACTLY active_patron
    (gifted_no_charge and lapsed patrons keep the free spin only)."""
    u = user or {}
    if u.get("patreon_patron_status") != PATREON_ACTIVE or not _patreon_tier_key:
        return 0, None
    key = _patreon_tier_key(u.get("patreon_tier_name"))
    rank = PATREON_RANK.get(key or "", 0)
    return (rank, key) if rank else (0, None)


def allowance_for(user: dict, cfg: dict) -> dict:
    rank, tier = tier_rank(user)
    base = max(0, min(MAX_BASE_SPINS, int(cfg.get("base_spins", DEFAULT_BASE_SPINS))))
    bonus = rank if cfg.get("patreon_bonus", True) else 0
    return {"allowance": base + bonus, "base": base, "patreon": bonus, "tier_key": tier}


def spins_used_today(user: dict, today: str) -> int:
    if (user or {}).get("wheel_day") != today:
        return 0
    try:
        return max(0, int(user.get("wheel_spins_today") or 0))
    except (TypeError, ValueError):
        return 0


def _patreon_pin(user: dict) -> dict:
    """The exact field values the allowance was computed from. Pinned into the
    claim filter so a concurrent tier change can never win a spin the new
    tier does not grant; the loser simply re-reads and retries."""
    return {"patreon_patron_status": (user or {}).get("patreon_patron_status"),
            "patreon_tier_name": (user or {}).get("patreon_tier_name")}


async def claim_spin(user: dict, today: str, allowance: int) -> Optional[str]:
    """One spin, claimed atomically. Returns "daily" / "bonus" / None.
    Three single-document conditional writes; no read decides anything."""
    uid = user["id"]
    pin = _patreon_pin(user)
    if allowance > 0:
        r = await _db.users.update_one(
            {"id": uid, **pin, "wheel_day": today,
             "wheel_spins_today": {"$lt": allowance}},
            {"$inc": {"wheel_spins_today": 1, "wheel_spin_count": 1}})
        if r.modified_count == 1:
            return "daily"
        # Day rollover — FORWARD only ($lt refuses a stored FUTURE day, so a
        # clock that visited tomorrow and came back cannot pay today twice).
        r = await _db.users.update_one(
            {"id": uid, **pin,
             "$or": [{"wheel_day": {"$exists": False}},
                     {"wheel_day": None},
                     {"wheel_day": {"$lt": today}}]},
            {"$set": {"wheel_day": today, "wheel_spins_today": 1},
             "$inc": {"wheel_spin_count": 1}})
        if r.modified_count == 1:
            return "daily"
        # Another request may have won the rollover write between our first
        # same-day attempt and this one. Retry the SAME atomic allowance claim
        # once so a first-use burst can fill (but never exceed) the allowance
        # instead of incorrectly falling through to bonus/no-spins.
        r = await _db.users.update_one(
            {"id": uid, **pin, "wheel_day": today,
             "wheel_spins_today": {"$lt": allowance}},
            {"$inc": {"wheel_spins_today": 1, "wheel_spin_count": 1}})
        if r.modified_count == 1:
            return "daily"
    r = await _db.users.update_one(
        {"id": uid, "wheel_bonus_spins": {"$gt": 0}},
        {"$inc": {"wheel_bonus_spins": -1, "wheel_spin_count": 1}})
    if r.modified_count == 1:
        return "bonus"
    return None


async def unclaim_spin(user_id: str, lane: str, today: str) -> None:
    """Hand a claimed spin back (lost the op insert, or the grant failed)."""
    try:
        if lane == "bonus":
            await _db.users.update_one(
                {"id": user_id},
                {"$inc": {"wheel_bonus_spins": 1, "wheel_spin_count": -1}})
        else:
            # Only today's counter can be handed back; a midnight in between
            # means the claim belonged to a day that is already closed.
            await _db.users.update_one(
                {"id": user_id, "wheel_day": today, "wheel_spins_today": {"$gt": 0}},
                {"$inc": {"wheel_spins_today": -1, "wheel_spin_count": -1}})
    except Exception:
        logger.exception("[wheel] unclaim lost user=%s lane=%s", user_id, lane)


# ---------------------------------------------------------------------------
# Payability — proven BEFORE any allowance is spent (PI wheel law).
# ---------------------------------------------------------------------------
def _species_by_slug() -> dict:
    return {d["slug"]: d for d in (seed_data.DINOSAURS or [])}


def resolve_pool(cfg: dict, tier: str) -> list:
    known = _species_by_slug()
    slugs = (cfg.get("dino_pools") or {}).get(tier) or []
    if not isinstance(slugs, list):
        return []
    out, dropped = [], []
    for s in slugs:
        if s in known and s in _CLASS_BY_SLUG and s not in out:
            out.append(s)
        else:
            dropped.append(s)
    if dropped:
        logger.warning("[wheel] dino pool %s: unresolvable slugs dropped %s", tier, dropped)
    return out


def glitch_pool() -> list:
    return [gid for gid in glitch_catalog.GLITCH_BY_ID
            if glitch_catalog.crate_eligible(gid)]


def payability_errors(cfg: dict) -> list:
    errs = []
    segs = [s for s in (cfg.get("segments") or []) if isinstance(s, dict) and _weight(s) > 0]
    if not segs:
        errs.append("sin premios con peso > 0")
    kinds = {s.get("kind") for s in segs}
    unknown = sorted(str(k) for k in kinds if k not in KINDS)
    if unknown:
        errs.append(f"kinds desconocidos: {unknown}")
    if "dino_basic" in kinds and not resolve_pool(cfg, "basic"):
        errs.append("pool de dinos 'basic' vacío o irresoluble")
    if "dino_prime" in kinds and not resolve_pool(cfg, "prime"):
        errs.append("pool de dinos 'prime' vacío o irresoluble")
    if "glitch_skin" in kinds and not glitch_pool():
        errs.append("no hay glitch skins elegibles de caja")
    return errs


def _live_segments(cfg: dict) -> list:
    """The drawable table: weight > 0 only, in config order."""
    return [s for s in (cfg.get("segments") or []) if isinstance(s, dict) and _weight(s) > 0]


# ---------------------------------------------------------------------------
# Grants — every lane is this site's own proven lane.
# ---------------------------------------------------------------------------
def _seeded_rng(*parts) -> random.Random:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def pick_mutations(dino_class: str, count: int, *seed_parts) -> str:
    """`count` diet-legal mutations for this species, seeded by the op key so a
    replayed grant never rerolls. Returns the 4-segment "|" own column
    (battle_pass._pick_mutations shape)."""
    segs = ["None"] * 4
    if count > 0:
        pool = sorted(set(mutation_catalog.PICKABLE)
                      & set(mutation_catalog.allowed_names_for_class(dino_class)))
        if pool:
            rng = _seeded_rng(*seed_parts)
            picks = rng.sample(pool, k=min(int(count), len(pool)))
            if len(picks) < count:
                logger.warning("[wheel] short mutation pool class=%s wanted=%d got=%d",
                               dino_class, count, len(picks))
            for i, name in enumerate(picks[:4]):
                segs[i] = name
    return mutation_catalog.join_segments(segs)


def steam_id_of(user: dict) -> str:
    return str((user or {}).get("steam_id") or "").strip()


async def _grant_currency(user: dict, seg: dict, op_key: str) -> dict:
    amount = max(1, int(seg.get("amount") or 1))
    vip = seg.get("kind") == "amberium"
    field = "vip_coins" if vip else "coins"
    cur = "vip" if vip else "normal"
    r = await _db.users.update_one({"id": user["id"]}, {"$inc": {field: amount}})
    if r.matched_count != 1:
        raise RuntimeError("user row vanished")
    await _add_transaction(user["id"], cur, amount, "reward",
                           f"Ruleta diaria · {seg.get('label')} · {op_key}")
    return {"kind": seg["kind"], "amount": amount, "text": seg.get("label")}


async def _grant_token(user: dict, seg: dict) -> dict:
    token = "diet" if seg.get("kind") == "diet_token" else "growth"
    flavor = "premium" if (seg.get("flavor") == "premium") else "basic"
    season = battle_pass.current_season_id()
    got = await battle_pass._grant_token(user, token, flavor, season)
    return {"kind": seg["kind"], "token": token, "flavor": flavor,
            "inv_id": got.get("inv_id"), "text": got.get("text")}


async def _grant_glitch(user: dict, seg: dict, roll: float) -> dict:
    pool = glitch_pool()
    gid = pool[min(len(pool) - 1, int(roll * len(pool)))]
    g = glitch_catalog.GLITCH_BY_ID[gid]
    await _db.reward_skins.update_one(
        {"user_id": user["id"], "glitch_id": gid},
        {"$inc": {"quantity": 1, "uses": _GLITCH_USES_PER_WIN},
         "$set": {"last_won_at": _now_iso(), "source": "Ruleta diaria"},
         "$setOnInsert": {
             "id": _new_id(), "name": g["name"], "subtitle": g["subtitle"],
             "image": g["preview"], "accent_hex": g["accent_hex"],
             "rarity": g.get("bp_rarity") or glitch_catalog.GLITCH_RARITY,
             "acquired_at": _now_iso(),
         }},
        upsert=True)
    try:
        prox = glitch_catalog.design_proximity(g)
    except Exception:
        prox = {"accent": g.get("accent_hex"), "strip": []}
    return {"kind": "glitch_skin", "glitch_id": gid, "name": g["name"],
            "accent_hex": g.get("accent_hex"), "proximity": prox.get("strip") or [],
            "text": g["name"]}


async def _grant_dino(user: dict, seg: dict, cfg: dict, roll: float, op_key: str) -> dict:
    prime = seg.get("kind") == "dino_prime"
    tier = "prime" if prime else "basic"
    pool = resolve_pool(cfg, tier)
    slug = pool[min(len(pool) - 1, int(roll * len(pool)))]
    d = _species_by_slug()[slug]
    dino_class = _CLASS_BY_SLUG[slug]
    sid = steam_id_of(user)
    if not sid:
        raise RuntimeError("no steam_id")
    diet = DIET_PRIME if prime else DIET_BASIC
    pd = {
        "dino": dino_class,
        "growth": DINO_GROWTH,
        "is_prime": prime,
        "is_elder": prime,
        "mutations": pick_mutations(dino_class, MUTS_PRIME if prime else MUTS_BASIC,
                                    op_key, dino_class),
        "parent_mutations": mutation_catalog.join_segments(["None"] * 4),
        "elder_mutations": "",
        # NO elder_stacks key and NO vitals keys, on purpose: 0 is the mod's
        # admin-add sentinel and the store lane relies on it.
        "diet_a": diet, "diet_b": diet, "diet_c": diet,
    }
    pd = vault.mint_prime_state(pd)
    discord_id = await asyncio.to_thread(vault.resolve_discord_id, sid)
    # cap=0 == unlimited in save_parked: a won dino ignores the Bóveda cap (a
    # full vault must never eat a prize the wheel already paid).
    row_id = await asyncio.to_thread(vault.save_parked, sid, discord_id, pd, 0)
    if row_id is None:
        raise RuntimeError("save_parked returned None")
    muts = [m for m in pd["mutations"].split("|") if m and m != "None"]
    return {"kind": seg["kind"], "slug": slug, "name": d["name"], "tier": tier,
            "vault_row": row_id, "mutations": muts,
            "text": f"{d['name']} {'PRIME ' if prime else ''}75% en tu Bóveda"}


async def _grant_vial(user: dict, seg: dict) -> dict:
    # find_one_and_update with upsert on the (user, item) pair: two wins that
    # land together both count, as one row with quantity 2.
    doc = await _db.inventory.find_one_and_update(
        {"user_id": user["id"], "item_id": VIAL_ITEM_ID},
        {"$inc": {"quantity": 1},
         "$set": {"acquired_at": _now_iso()},
         "$setOnInsert": {
             "id": _new_id(), "name": "Vial GEN-Ø", "category": "Consumables",
             "rarity": "Legendary", "image": "/tokens/vial-gen0.png",
             "source": "wheel_spin", "order": 9999,
         }},
        upsert=True, return_document=ReturnDocument.AFTER)
    return {"kind": "gen0_vial", "inv_id": doc["id"], "quantity": int(doc.get("quantity") or 1),
            "text": "Vial GEN-Ø — úsalo desde tu inventario"}


async def grant(user: dict, seg: dict, cfg: dict, op_key: str, sub_roll: float) -> dict:
    kind = seg.get("kind")
    if kind in ("primemeat", "amberium"):
        return await _grant_currency(user, seg, op_key)
    if kind in ("growth_token", "diet_token"):
        return await _grant_token(user, seg)
    if kind == "glitch_skin":
        return await _grant_glitch(user, seg, sub_roll)
    if kind in ("dino_basic", "dino_prime"):
        return await _grant_dino(user, seg, cfg, sub_roll, op_key)
    if kind == "gen0_vial":
        return await _grant_vial(user, seg)
    raise RuntimeError(f"unknown wheel kind {kind!r}")


# ---------------------------------------------------------------------------
# Live wins hub (creator_ws precedent: bounded, ping/pong; no user ids leave)
# ---------------------------------------------------------------------------
class _Hub:
    def __init__(self, cap: int = WS_MAX_CLIENTS):
        self.conns: set = set()
        self.cap = cap

    async def add(self, ws) -> None:
        self.conns.add(ws)

    async def remove(self, ws) -> None:
        self.conns.discard(ws)

    async def broadcast(self, msg: dict) -> None:
        dead = []
        for ws in list(self.conns):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for d in dead:
            await self.remove(d)


wheel_hub = _Hub()


async def _stats() -> dict:
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        spins_24h = await _db.wheel_spins.count_documents({"at": {"$gte": since}})
    except Exception:
        spins_24h = 0
    return {"online": len(wheel_hub.conns), "spins_24h": spins_24h}


def _feed_view(row: dict) -> dict:
    """What other players may see about a win: persona + the plate. Never the
    user id, never the op key."""
    return {"at": row.get("at"), "name": row.get("user_name") or "Superviviente",
            "avatar": row.get("user_avatar"), "segment": row.get("segment")}


def _broadcast_later(msg: dict) -> None:
    async def _go():
        try:
            await wheel_hub.broadcast(msg)
        except Exception:
            pass
    try:
        asyncio.get_running_loop().create_task(_go())
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------
def _status_view(user: dict, cfg: dict, today: Optional[str] = None) -> dict:
    today = today or today_key()
    al = allowance_for(user, cfg)
    used = spins_used_today(user, today)
    try:
        bonus = max(0, int(user.get("wheel_bonus_spins") or 0))
    except (TypeError, ValueError):
        bonus = 0
    enabled = bool(cfg.get("enabled", True))
    left = max(0, al["allowance"] - used)
    return {
        "enabled": enabled,
        "can_spin": enabled and (left > 0 or bonus > 0),
        "allowance": al["allowance"], "base": al["base"], "patreon_bonus": al["patreon"],
        "tier_key": al["tier_key"],
        "used_today": used, "left_today": left, "bonus_spins": bonus,
        "day": today, "next_reset": next_reset_iso(),
        "spin_count": int(user.get("wheel_spin_count") or 0),
    }


def _spin_answer(row: dict, status: dict, segments: list) -> dict:
    return {
        "op_key": row["_id"], "status": row.get("status"),
        "segment_index": row.get("segment_index"), "segment": row.get("segment"),
        "segments": public_segments(segments),
        "reward": row.get("reward"), "fairness": row.get("fairness"),
        "lane": row.get("lane"), "at": row.get("at"),
        "wheel": status,
    }


# ---------------------------------------------------------------------------
# Player endpoints
# ---------------------------------------------------------------------------
class SpinIn(BaseModel):
    cmd_id: str = Field(min_length=6, max_length=64)


class VialIn(BaseModel):
    inv_id: str = Field(min_length=4, max_length=64)


@router.get("/wheel/config")
async def wheel_public_config(user=Depends(_require_user)):
    cfg = await _get_config()
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "segments": public_segments(_live_segments(cfg)),
        "base_spins": cfg.get("base_spins", DEFAULT_BASE_SPINS),
        "patreon_bonus": bool(cfg.get("patreon_bonus", True)),
        "patreon_rank": dict(PATREON_RANK),
        "wheel": _status_view(user, cfg),
    }


@router.get("/wheel/status")
async def wheel_status(user=Depends(_require_user)):
    cfg = await _get_config()
    return _status_view(user, cfg)


@router.post("/wheel/spin")
async def wheel_spin(data: SpinIn, user=Depends(_require_user)):
    """Order (the canonical wheel's): replay -> switch -> prizes payable ->
    CLAIM the spin -> draw -> record -> grant -> receipt. Nothing is spent
    before the table is proven payable; nothing is drawn before the claim."""
    if not CMD_RE.match(data.cmd_id or ""):
        raise HTTPException(400, "cmd_id inválido")
    op_key = f"lin:wheel:{user['id']}:{data.cmd_id}"
    cfg = await _get_config()
    segments = _live_segments(cfg)
    today = today_key()
    stamp = _now_iso()

    # The op key is claimed FIRST, before anything is read or spent (the
    # store_orders wall): of N identical requests exactly one owns the op and
    # the rest answer from it — a duplicate can never reach the spin claim.
    try:
        await _db.wheel_spins.insert_one({
            "_id": op_key, "user_id": user["id"], "status": "new", "at": stamp,
            "user_name": user.get("persona_name") or user.get("username"),
            "user_avatar": user.get("avatar") or user.get("avatar_url"),
        })
    except DuplicateKeyError:
        prior = await _db.wheel_spins.find_one({"_id": op_key})
        return await _resume(prior, user, cfg, segments, today)
    return await _run_new(op_key, user, cfg, segments, today)


async def _refuse(op_key: str, code: int, detail) -> None:
    await _db.wheel_spins.update_one(
        {"_id": op_key, "status": "new"},
        {"$set": {"status": "refused", "refusal": {"code": code, "detail": detail},
                  "refused_at": _now_iso()}})
    raise HTTPException(code, detail)


async def _run_new(op_key: str, user: dict, cfg: dict, segments: list, today: str) -> dict:
    """Owner of a fresh op: switch -> payable -> CLAIM -> draw -> settle."""
    if not cfg.get("enabled", True):
        await _refuse(op_key, 400, "WHEEL_DISABLED")
    errs = payability_errors(cfg)
    if errs:
        logger.error("[wheel] refusing spin, table not payable: %s", errs)
        await _refuse(op_key, 503, "La ruleta está mal configurada; avisa al staff.")

    al = allowance_for(user, cfg)
    lane = await claim_spin(user, today, al["allowance"])
    if lane is None:
        fresh = await _db.users.find_one({"id": user["id"]}, {"_id": 0}) or user
        st = _status_view(fresh, cfg, today)
        await _refuse(op_key, 429, {"code": "NO_SPINS", "next_reset": st["next_reset"],
                                    "allowance": st["allowance"], "used_today": st["used_today"]})

    seed = await _pf["get_active"](user["id"])
    nonce = int(seed["nonce"])
    roll = _pf["float"](seed["server_seed"], seed["client_seed"], nonce)
    sub_roll = _pf["float_i"](seed["server_seed"], seed["client_seed"], nonce, 1)
    weights = [_weight(s) for s in segments]
    seg = _pf["pick"](segments, weights, roll)
    idx = segments.index(seg)
    await _db.pf_seeds.update_one({"id": seed["id"]}, {"$inc": {"nonce": 1}})
    drawn = {
        "lane": lane, "day": today,
        "segment_index": idx, "segment_key": seg.get("key"), "kind": seg.get("kind"),
        "amount": seg.get("amount"), "label": seg.get("label"),
        # the plate as it was when drawn — a later config edit cannot rewrite
        # what this win looked like (bundle defect #16)
        "segment": _public_one(seg, segments),
        "segment_snapshot": dict(seg),
        "fairness": {"server_seed_hash": seed["server_seed_hash"],
                     "client_seed": seed["client_seed"], "nonce": nonce,
                     "roll": round(roll, 8), "sub_roll": round(sub_roll, 8)},
        "status": "drawn", "reward": None, "drawn_at": _now_iso(),
    }
    row = await _db.wheel_spins.find_one_and_update(
        {"_id": op_key, "status": "new"}, {"$set": drawn},
        return_document=ReturnDocument.AFTER)
    if row is None:  # cannot happen (we own the op); never pay on a ghost
        await unclaim_spin(user["id"], lane, today)
        raise HTTPException(500, "Giro perdido; inténtalo de nuevo.")
    return await _settle(row, user, cfg, segments, today, sub_roll)


async def _settle(row: dict, user: dict, cfg: dict, segments: list, today: str,
                  sub_roll: float) -> dict:
    op_key = row["_id"]
    seg = row.get("segment_snapshot") or {}
    claimed = await _db.wheel_spins.find_one_and_update(
        {"_id": op_key, "status": "drawn"},
        {"$set": {"status": "granting", "granting_at": _now_iso()}},
        return_document=ReturnDocument.AFTER)
    if claimed is None:
        prior = await _db.wheel_spins.find_one({"_id": op_key})
        return await _resume(prior, user, cfg, segments, today)
    try:
        reward = await grant(user, seg, cfg, op_key, sub_roll)
    except Exception as e:
        logger.exception("[wheel] grant FAILED op=%s kind=%s", op_key, seg.get("kind"))
        await _db.wheel_spins.update_one(
            {"_id": op_key}, {"$set": {"status": "grant_failed", "error": repr(e)[:300],
                                       "failed_at": _now_iso()}})
        await unclaim_spin(user["id"], row.get("lane") or "daily", today)
        raise HTTPException(500, "No pudimos entregar el premio; tu giro fue devuelto. Inténtalo de nuevo.")
    done = await _db.wheel_spins.find_one_and_update(
        {"_id": op_key},
        {"$set": {"status": "granted", "reward": reward, "granted_at": _now_iso()}},
        return_document=ReturnDocument.AFTER)
    logger.info("[wheel] granted op=%s user=%s lane=%s plate=%s reward=%s",
                op_key, user["id"], row.get("lane"), seg.get("key"), reward.get("text"))
    fresh = await _db.users.find_one({"id": user["id"]}, {"_id": 0}) or user
    status = _status_view(fresh, cfg, today)
    stats = await _stats()
    _broadcast_later({"type": "wheel_win", **_feed_view(done), "stats": stats})
    out = _spin_answer(done, status, segments)
    out["balance"] = {"coins": fresh.get("coins", 0), "vip_coins": fresh.get("vip_coins", 0)}
    return out


async def _resume(prior: dict, user: dict, cfg: dict, segments: list, today: str) -> dict:
    """A replayed cmd_id. granted -> the recorded answer. drawn -> finish the
    grant (the first attempt died before claiming it). granting, stale ->
    left alone and reported: re-granting blindly could pay twice, so a human
    reads the receipt. grant_failed -> the spin was already restored; tell
    the player to spin again (a NEW cmd_id)."""
    if prior is None:
        raise HTTPException(500, "Giro no encontrado")
    status_ = prior.get("status")
    if status_ == "new":
        # In flight (a duplicate fired before the owner finished) — or the
        # owner died before claiming. Stale = retake it; fresh = tell the
        # client to ask again in a moment (it re-sends the SAME cmd_id).
        if _is_stale(prior.get("at")):
            taken = await _db.wheel_spins.find_one_and_update(
                {"_id": prior["_id"], "status": "new", "at": prior.get("at")},
                {"$set": {"at": _now_iso(), "retaken": True}},
                return_document=ReturnDocument.AFTER)
            if taken is not None:
                return await _run_new(prior["_id"], user, cfg, segments, today)
        raise HTTPException(409, {"code": "PENDING"})
    if status_ == "refused":
        ref = prior.get("refusal") or {}
        raise HTTPException(int(ref.get("code") or 400), ref.get("detail") or "NO_SPINS")
    if status_ == "drawn":
        return await _settle(prior, user, cfg, segments, today,
                             float((prior.get("fairness") or {}).get("sub_roll") or 0.0))
    fresh = await _db.users.find_one({"id": user["id"]}, {"_id": 0}) or user
    status = _status_view(fresh, cfg, today)
    if status_ == "granted":
        out = _spin_answer(prior, status, segments)
        out["replayed"] = True
        out["balance"] = {"coins": fresh.get("coins", 0), "vip_coins": fresh.get("vip_coins", 0)}
        return out
    if status_ == "grant_failed":
        raise HTTPException(409, {"code": "GRANT_FAILED", "message":
                                  "Ese giro falló y fue devuelto. Gira de nuevo."})
    # granting: in flight, or stale (the grant may or may not have landed —
    # re-granting blindly could pay twice, so a human reads the receipt)
    if _is_stale(prior.get("granting_at")):
        logger.warning("[wheel] replay hit a STALE granting op=%s since=%s",
                       prior["_id"], prior.get("granting_at"))
    raise HTTPException(409, {"code": "PENDING"})


def _is_stale(iso: Optional[str]) -> bool:
    try:
        t = datetime.fromisoformat(str(iso))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() > GRANTING_STALE_S
    except Exception:
        return True


@router.get("/wheel/history")
async def wheel_history(user=Depends(_require_user)):
    cur = _db.wheel_spins.find({"user_id": user["id"], "status": "granted"},
                               {"_id": 0, "segment": 1, "reward": 1, "at": 1, "lane": 1,
                                "fairness": 1}).sort("at", -1).limit(HISTORY_LIMIT)
    rows = await cur.to_list(length=HISTORY_LIMIT)
    return {"history": rows}


@router.post("/wheel/vial/use")
async def wheel_use_vial(data: VialIn, user=Depends(_require_user)):
    """Drink the vial: the PLAYER's GEN-Ø infection goes to 100 % — exactly
    what four facility visits do — and the live lane transforms the animal
    they are walking the next time it is seen alive. Order: own the vial ->
    eligible (cheap refusal, vial kept) -> CONSUME the vial -> state write;
    a refused state write hands the vial back (deploy-lane restore)."""
    item = await _db.inventory.find_one(
        {"id": data.inv_id, "user_id": user["id"], "item_id": VIAL_ITEM_ID}, {"_id": 0})
    if not item:
        raise HTTPException(404, "No tienes ese vial en tu inventario.")
    sid = steam_id_of(user)
    if not sid:
        raise HTTPException(400, "Vincula tu cuenta de Steam para usar el vial.")
    doc = await _db.gen0_state.find_one({"steam_id": sid}, {"_id": 0, "percent": 1, "zombie_active": 1})
    if doc and (doc.get("zombie_active") or int(doc.get("percent") or 0) >= 100):
        raise HTTPException(400, "Ya estás al 100 % de infección GEN-Ø. Guarda el vial para tu próxima vida.")

    # CONSUME = one conditional decrement (never delete-then-insert): a stack
    # raced by several uses hands out exactly one unit per winner, and a
    # refused use below puts its unit back by the same counter. The row is
    # only removed once it is truly empty, by a delete that re-checks zero.
    claimed = await _db.inventory.find_one_and_update(
        {"id": data.inv_id, "user_id": user["id"], "item_id": VIAL_ITEM_ID,
         "quantity": {"$gte": 1}},
        {"$inc": {"quantity": -1}}, return_document=ReturnDocument.AFTER)
    if claimed is None:
        raise HTTPException(404, "No tienes ese vial en tu inventario.")

    async def _restore():
        r = await _db.inventory.update_one({"id": data.inv_id, "user_id": user["id"]},
                                           {"$inc": {"quantity": 1}})
        if r.matched_count == 0:
            # The empty row was swept meanwhile: give the unit back as a fresh
            # row (a NEW id — never two rows sharing one id).
            back = {k: v for k, v in claimed.items() if k != "_id"}
            back.update({"id": _new_id(), "quantity": 1, "acquired_at": _now_iso()})
            await _db.inventory.insert_one(back)

    async def _sweep_empty():
        await _db.inventory.delete_one({"id": data.inv_id, "user_id": user["id"],
                                        "item_id": VIAL_ITEM_ID, "quantity": {"$lte": 0}})

    try:
        res = await _db.gen0_state.update_one(
            {"steam_id": sid, "zombie_active": {"$ne": True},
             "$or": [{"percent": {"$exists": False}}, {"percent": None},
                     {"percent": {"$lt": 100}}]},
            {"$set": {"percent": 100, "updated_at": _now_iso(), "vial_at": _now_iso()},
             "$setOnInsert": {"steam_id": sid, "claims": {}}},
            upsert=True)
    except DuplicateKeyError:
        # The doc exists and failed the filter (raced to 100 % / zombie since
        # the read above): the unique steam_id index refused the twin insert.
        await _restore()
        raise HTTPException(400, "Ya estás al 100 % de infección GEN-Ø. Guarda el vial para tu próxima vida.")
    except Exception:
        logger.exception("[wheel] vial state write crashed sid=%s", sid)
        await _restore()
        raise HTTPException(500, "No pudimos aplicar el vial; lo devolvimos a tu inventario.")
    if res.matched_count != 1 and not res.upserted_id:
        await _restore()
        raise HTTPException(400, "Ya estás al 100 % de infección GEN-Ø. Guarda el vial para tu próxima vida.")
    await _sweep_empty()
    logger.info("[wheel] vial used user=%s sid=...%s left=%s", user["id"], sid[-4:],
                int(claimed.get("quantity") or 0))
    return {"success": True, "percent": 100,
            "message": "El virus GEN-Ø recorre tus venas. Tu próximo dinosaurio vivo se transformará."}


# ---------------------------------------------------------------------------
# Admin (owner only)
# ---------------------------------------------------------------------------
class SegmentIn(BaseModel):
    key: Optional[str] = Field(None, max_length=24)
    kind: str = Field(min_length=3, max_length=24)
    label: str = Field(min_length=1, max_length=40)
    amount: int = Field(1, ge=1)
    weight: float = Field(1.0, ge=0)
    color: Optional[str] = Field("#8B5CF6", max_length=9)
    icon: Optional[str] = Field("gift", max_length=16)
    flavor: Optional[str] = Field(None, max_length=8)


class ConfigIn(BaseModel):
    enabled: Optional[bool] = None
    base_spins: Optional[int] = Field(None, ge=0, le=MAX_BASE_SPINS)
    patreon_bonus: Optional[bool] = None
    segments: Optional[list[SegmentIn]] = None
    dino_pools: Optional[dict[str, list[str]]] = None


class GrantSpinsIn(BaseModel):
    user_id: str = Field(min_length=4, max_length=64)
    amount: int = Field(ge=-100, le=100)
    reason: Optional[str] = Field(None, max_length=120)


_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def clean_segments(raw: list) -> list:
    """Validate the WHOLE table (never a partial). Raises ValueError naming
    the first offence so the admin sees what to fix."""
    if not isinstance(raw, list):
        raise ValueError("segments debe ser una lista")
    if len(raw) > MAX_SEGMENTS:
        raise ValueError(f"máximo {MAX_SEGMENTS} premios")
    out, keys = [], set()
    for i, s in enumerate(raw):
        s = s.model_dump() if hasattr(s, "model_dump") else dict(s)
        kind = str(s.get("kind") or "").strip()
        if kind not in KINDS:
            raise ValueError(f"premio {i + 1}: kind desconocido {kind!r}")
        key = str(s.get("key") or f"s{i}").strip()[:24] or f"s{i}"
        if key in keys:
            raise ValueError(f"premio {i + 1}: key repetida {key!r}")
        keys.add(key)
        label = str(s.get("label") or "").strip()[:40]
        if not label:
            raise ValueError(f"premio {i + 1}: falta label")
        try:
            amount = int(s.get("amount") if s.get("amount") is not None else 1)
            weight = float(s.get("weight") if s.get("weight") is not None else 0)
        except (TypeError, ValueError):
            raise ValueError(f"premio {i + 1}: amount/weight inválidos")
        if kind in MAX_AMOUNT:
            if amount < 1 or amount > MAX_AMOUNT[kind]:
                raise ValueError(f"premio {i + 1}: amount fuera de rango 1..{MAX_AMOUNT[kind]}")
        else:
            amount = 1
        if not (weight == weight) or weight < 0 or weight == float("inf") or weight > 10_000:
            raise ValueError(f"premio {i + 1}: weight fuera de rango 0..10000")
        color = str(s.get("color") or "#8B5CF6")
        if not _HEX_RE.match(color):
            raise ValueError(f"premio {i + 1}: color debe ser #RRGGBB")
        icon = str(s.get("icon") or "gift")
        if icon not in ICONS:
            icon = "gift"
        seg = {"key": key, "kind": kind, "label": label, "amount": amount,
               "weight": weight, "color": color, "icon": icon}
        if kind == "growth_token":
            seg["flavor"] = "premium" if s.get("flavor") == "premium" else "basic"
        out.append(seg)
    if not any(_weight(s) > 0 for s in out):
        raise ValueError("al menos un premio necesita weight > 0")
    return out


def clean_pools(raw: dict, current: dict) -> dict:
    known = _species_by_slug()
    out = {k: list(v) for k, v in (current or {}).items()}
    for tier, slugs in (raw or {}).items():
        if tier not in ("basic", "prime"):
            raise ValueError(f"pool desconocido {tier!r}")
        if not isinstance(slugs, list):
            raise ValueError(f"pool {tier}: debe ser una lista")
        clean = []
        for s in slugs:
            s = str(s).strip()
            if s not in known or s not in _CLASS_BY_SLUG:
                raise ValueError(f"pool {tier}: especie desconocida {s!r}")
            if s not in clean:
                clean.append(s)
        out[tier] = clean
    return out


@router.get("/wheel/admin/config")
async def wheel_admin_config(owner=Depends(_require_owner)):
    cfg = await _get_config()
    cfg["problems"] = payability_errors(cfg)
    cfg["species"] = [{"slug": d["slug"], "name": d["name"], "rarity": d.get("rarity")}
                      for d in (seed_data.DINOSAURS or []) if d["slug"] in _CLASS_BY_SLUG]
    cfg["glitch_pool"] = glitch_pool()
    cfg["kinds"] = list(KINDS)
    cfg["icons"] = list(ICONS)
    cfg["patreon_rank"] = dict(PATREON_RANK)
    return cfg


@router.post("/wheel/admin/config")
async def wheel_admin_save(body: ConfigIn, owner=Depends(_require_owner)):
    cur = await _get_config()
    merged = dict(cur)
    if body.enabled is not None:
        merged["enabled"] = bool(body.enabled)
    if body.base_spins is not None:
        merged["base_spins"] = int(body.base_spins)
    if body.patreon_bonus is not None:
        merged["patreon_bonus"] = bool(body.patreon_bonus)
    try:
        if body.segments is not None:
            merged["segments"] = clean_segments(body.segments)
        if body.dino_pools is not None:
            merged["dino_pools"] = clean_pools(body.dino_pools, cur.get("dino_pools") or {})
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Judged on the MERGED table (a save naming only one field must not read
    # as emptying the others — PI finding #4).
    if merged.get("enabled"):
        errs = payability_errors(merged)
        if errs:
            raise HTTPException(400, "La ruleta quedaría sin premios pagables: " + "; ".join(errs))
    update = {k: merged[k] for k in ("enabled", "base_spins", "patreon_bonus", "segments", "dino_pools")}
    update["updated_at"] = _now_iso()
    await _db.wheel_config.update_one(
        {"_id": CONFIG_ID}, {"$set": update, "$inc": {"revision": 1}}, upsert=True)
    try:
        await _add_log(owner.get("persona_name"), "wheel_config", None,
                       {"enabled": update["enabled"], "base_spins": update["base_spins"],
                        "patreon_bonus": update["patreon_bonus"],
                        "segments": len(update["segments"])})
    except Exception:
        pass
    _broadcast_later({"type": "wheel_config_updated"})
    return await wheel_admin_config(owner)


@router.post("/wheel/admin/reset-defaults")
async def wheel_admin_reset(owner=Depends(_require_owner)):
    fresh = default_config()
    fresh["updated_at"] = _now_iso()
    fresh.pop("revision", None)
    await _db.wheel_config.update_one(
        {"_id": CONFIG_ID}, {"$set": fresh, "$inc": {"revision": 1}}, upsert=True)
    try:
        await _add_log(owner.get("persona_name"), "wheel_reset", None, {})
    except Exception:
        pass
    _broadcast_later({"type": "wheel_config_updated"})
    return await wheel_admin_config(owner)


@router.post("/wheel/admin/grant-spins")
async def wheel_admin_grant_spins(body: GrantSpinsIn, owner=Depends(_require_owner)):
    """Gift (or take back) bonus spins. The counter never goes below zero:
    a negative amount is clamped by the $max-guarded pipeline below."""
    if body.amount == 0:
        raise HTTPException(400, "amount no puede ser 0")
    target = await _db.users.find_one({"id": body.user_id}, {"_id": 0, "id": 1, "persona_name": 1,
                                                              "wheel_bonus_spins": 1})
    if not target:
        raise HTTPException(404, "Usuario no encontrado")
    if body.amount > 0:
        r = await _db.users.update_one({"id": body.user_id}, {"$inc": {"wheel_bonus_spins": body.amount}})
    else:
        take = -body.amount
        r = await _db.users.update_one(
            {"id": body.user_id, "wheel_bonus_spins": {"$gte": take}},
            {"$inc": {"wheel_bonus_spins": -take}})
        if r.modified_count != 1:
            raise HTTPException(400, "Ese usuario no tiene tantos giros bonus")
    fresh = await _db.users.find_one({"id": body.user_id}, {"_id": 0, "wheel_bonus_spins": 1})
    try:
        await _add_log(owner.get("persona_name"), "wheel_grant_spins", body.user_id,
                       {"amount": body.amount, "reason": body.reason or "",
                        "target": target.get("persona_name")})
    except Exception:
        pass
    return {"success": True, "user_id": body.user_id,
            "bonus_spins": int((fresh or {}).get("wheel_bonus_spins") or 0)}


@router.get("/wheel/admin/recent")
async def wheel_admin_recent(owner=Depends(_require_owner)):
    cur = _db.wheel_spins.find({}, {"segment_snapshot": 0}).sort("at", -1).limit(100)
    rows = await cur.to_list(length=100)
    for r in rows:
        r["op_key"] = r.pop("_id")
    stuck = await _db.wheel_spins.count_documents({"status": {"$in": ["granting", "grant_failed"]}})
    return {"recent": rows, "attention": stuck}


# ---------------------------------------------------------------------------
# Live feed
# ---------------------------------------------------------------------------
@router.websocket("/wheel/ws")
async def wheel_ws(ws: WebSocket):
    await ws.accept()
    if _db is None or len(wheel_hub.conns) >= wheel_hub.cap:
        await ws.close()
        return
    await wheel_hub.add(ws)
    try:
        try:
            cur = _db.wheel_spins.find({"status": "granted"},
                                       {"_id": 0, "at": 1, "user_name": 1, "user_avatar": 1,
                                        "segment": 1}).sort("at", -1).limit(RECENT_LIMIT)
            recent = await cur.to_list(length=RECENT_LIMIT)
            await ws.send_json({"type": "wheel_recent",
                                "items": [_feed_view(r) for r in recent],
                                "stats": await _stats()})
        except Exception:
            pass
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("[wheel] ws: %r", e)
    finally:
        await wheel_hub.remove(ws)
