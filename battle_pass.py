# -*- coding: utf-8 -*-
"""Pase de Batalla — La Isla Nublar. 100 levels, one season per UTC calendar month.

Owner ask (Moonveil via Ishaq, 2026-08-05/06) + his own Emergent prototype. His XP
curve, his season names and his tier-resolve are kept verbatim; the reward tables
are the ones the design pins EXACTLY, because the totals are a promise:

    PASE (premium track)   2.000.000 PrimeMeat + 6.000 Amberium   -- every cell EVEN
    PASE REGULAR ($5)      exactly half of both, by integer halving at claim time
    GRATIS (free track)      160.000 PrimeMeat +   500 Amberium + 20 empty cells

Those four numbers are asserted at IMPORT (_assert_track_totals). A cell edit that
breaks them refuses to load rather than quietly paying the wrong economy.

WHY THIS MODULE NEVER IMPORTS server.py
    Same reason crash_game.py does not: server.py imports this one. The Mongo
    handle, the two auth dependencies and the four helper callables arrive once
    through configure(), exactly the dependency-injection pattern crash_game and
    vault already use. Everything else (vault, game_ipc, mutation_catalog,
    glitch_catalog, seed_data, game_telemetry) is a leaf import with no cycle.

WHAT TOUCHES WHAT
    XP            db.bp_passes.xp -- NEVER db.users.xp, which is the chat level.
    Currency      db.users.coins (PrimeMeat) / db.users.vip_coins (Amberium),
                  through the injected add_transaction so the ledger stays whole.
    Dinos         vault.save_parked(), the exact payload shape /store/purchase-dino
                  writes (0-sentinel vitals, no elder_stacks key).
    Skins         db.reward_skins, byte-identical to the crate grant lane, with
                  the Battle Pass exclusives that live in glitch_catalog.BP_SKINS.
    Tokens        db.inventory category "Tokens".
    Parked redeem a NARROW UPDATE against the bot's sqlite, written here because
                  vault.py exposes no public writer for growth/prime/diet. It
                  mirrors vault.cas_update_mutations discipline exactly: WAL +
                  busy_timeout, BEGIN IMMEDIATE, ownership in the WHERE clause,
                  the redeem_pending guard, and an optimistic CAS on the old
                  value so a concurrent redeem can never be overwritten.

STRIPE IS OPTIONAL AT RUNTIME
    The library is imported guarded and the key is read from env. With neither,
    the two checkout-shaped endpoints answer 503 "Pagos no disponibles por ahora"
    and EVERYTHING ELSE still works -- XP, claims, tokens, settle, admin, gifts.
    No credential is ever written to a file by this module.
"""
from __future__ import annotations

import asyncio
import collections
import functools
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import game_ipc
import game_telemetry
import glitch_catalog
import mutation_catalog
import quest_data
import seed_data
import vault

logger = logging.getLogger("laislanublar.battlepass")

router = APIRouter(prefix="/battle-pass")
_security = HTTPBearer(auto_error=False)


# ===========================================================================
# Injected host wiring (server.py hands these in once; see configure()).
# ===========================================================================
db = None
_current_user_dep = None
_admin_user_dep = None
_add_transaction = None
_add_log = None
_park_cap = None


def configure(mongo_db, *, current_user_dep, admin_user_dep,
              add_transaction, add_log, park_cap) -> None:
    """One-shot dependency injection from server.py. Called beside the router
    include so the module can be imported (and unit-tested) with no host."""
    global db, _current_user_dep, _admin_user_dep, _add_transaction, _add_log, _park_cap
    db = mongo_db
    _current_user_dep = current_user_dep
    _admin_user_dep = admin_user_dep
    _add_transaction = add_transaction
    _add_log = add_log
    _park_cap = park_cap
    # A new handle means the old season-name cache belongs to a database this
    # module no longer talks to.
    _season_name_cache["at"] = None
    _season_name_cache["map"] = {}
    logger.info("[bp] configured")


# ===========================================================================
# Constants
# ===========================================================================
MAX_LEVEL = 100

# ★ v2 ROW MODEL (owner correction 2026-08-07: "there should be no free. there
# should be regular and premium. im able to use regular without even buying and
# i dont see premium benefits either").
#   * There is NO free row. The two rows are REGULAR and PREMIUM.
#   * A player who has bought nothing (tier "free") can claim NOTHING on either
#     row. XP still accrues and both rows are still SERVED, so the page shows
#     exactly what the money buys.
#   * A $5 Pase Regular claims the REGULAR row. A $10 Pase Premium+ claims BOTH
#     rows -- they stack, which is where the owner's 2.000.000 / 6.000 / 8
#     mutations comes from.
TRACK_REGULAR = "regular"
TRACK_PREMIUM = "premium"
TRACKS = (TRACK_REGULAR, TRACK_PREMIUM)
# The v1 wire names. Kept ONLY so a browser holding the previous bundle keeps
# rendering while the new one rolls out -- deprecated, remove once that window
# has passed.
LEGACY_TRACK_ALIAS = {"free": TRACK_REGULAR, "pass": TRACK_PREMIUM}
LEGACY_TRACK_NAME = {TRACK_REGULAR: "free", TRACK_PREMIUM: "pass"}

TIER_FREE = "free"
TIER_REGULAR = "regular"
TIER_PREMIUM = "premium_plus"
TIER_RANK = {TIER_FREE: 0, TIER_REGULAR: 1, TIER_PREMIUM: 2}
TIER_LABEL = {TIER_FREE: "Sin pase", TIER_REGULAR: "Pase Regular", TIER_PREMIUM: "Pase Premium+"}

# Which rows a tier may claim. This is the whole access model.
TIER_TRACKS = {
    TIER_FREE: (),
    TIER_REGULAR: (TRACK_REGULAR,),
    TIER_PREMIUM: (TRACK_REGULAR, TRACK_PREMIUM),
}


def can_claim_track(tier: str, track: str) -> bool:
    return track in TIER_TRACKS.get(tier, ())


def normalize_track(track) -> Optional[str]:
    t = str(track or "").strip()
    t = LEGACY_TRACK_ALIAS.get(t, t)
    return t if t in TRACKS else None

# XP economy (owner's constants).
BP_XP_PER_PLAYTIME_CYCLE = 60          # per existing 4-minute passive cycle
BP_XP_QUEST_BY_RARITY = {              # LIN has no Apex quest rarity
    "Common": 120, "Uncommon": 250, "Rare": 500, "Epic": 1000, "Legendary": 2000,
}
BP_XP_KILL_BY_BAND = {"low": 80, "mid": 150, "high": 250, "apex": 500}
KILL_MIN_VICTIM_GROWTH = 0.25          # anti-farm: hatchling kills pay nothing
KILL_PAIR_COOLDOWN_S = 30 * 60         # per killer->victim pair

# Token effects.
GROWTH_TOKEN_TARGET = 0.70             # owner corrected 75% -> 70%; every string says 70
DIET_PREMIUM_EACH = 1.0                # 3 nutrients x 100% = 300%
DIET_BASIC_EACH = 0.5                  # 3 nutrients x  50% = 150%
# Prime route caps. Real named constants live in dino_recovery; imported lazily
# there so a missing sibling can never take the whole pass down.
PRIME_ROUTE_MIG_MAX = 2
PRIME_ROUTE_PAT_MAX = 4
try:  # pragma: no cover - trivial
    import dino_recovery as _dr
    PRIME_ROUTE_MIG_MAX = int(getattr(_dr, "PRIME_ROUTE_MIG_MAX", PRIME_ROUTE_MIG_MAX))
    PRIME_ROUTE_PAT_MAX = int(getattr(_dr, "PRIME_ROUTE_PAT_MAX", PRIME_ROUTE_PAT_MAX))
except Exception:  # pragma: no cover
    pass

DINO_GROWTH = 0.75                     # every dino cell arrives 75% grown
# ★ Owner order 2026-08-08: every dino reward carries 3 random mutations when
# it is NOT prime and 4 when it IS. The ROW decides prime (ROW_DINO_RULES), so
# regular-row dinos get 3 and premium-row dinos get 4. These two constants are
# the only place the numbers live; totals derive from them.
MUTATIONS_NON_PRIME = 3
MUTATIONS_PRIME = 4

# Everything a dino cell grants is decided by its ROW, never by the buyer's
# tier: a Premium+ buyer claiming the regular row's pick gets that row's
# non-prime, 150%-diet version, and the premium row's prime one on top.
ROW_DINO_RULES = {
    "regular": {"prime": False, "diet": 0.5},
    "premium": {"prime": True, "diet": 1.0},
}
ROW_TOKEN_FLAVOR = {"regular": "basic", "premium": "premium"}


def mutations_per_dino(track: str) -> int:
    """3 for a non-prime row's dinos, 4 for a prime row's — the row decides
    prime, so it decides the count too."""
    rules = ROW_DINO_RULES.get(track) or ROW_DINO_RULES["regular"]
    return MUTATIONS_PRIME if rules["prime"] else MUTATIONS_NON_PRIME

GLITCH_USES_PER_WIN = max(1, int(os.environ.get("LIN_GLITCH_USES_PER_WIN") or 25))
PUBLIC_SITE_URL = (os.environ.get("PUBLIC_SITE_URL") or "https://laislanublar.net").rstrip("/")

# Live-token capability key the lua wave must advertise (see BACKEND_NOTES.md).
BP_CAPABILITY_KEY = "bp_tokens"
LIVE_ACK_TIMEOUT_S = 20.0
LIVE_ACK_POLL_S = 0.25
# The growth token's full-food rider gets a shorter, separate wait: the primary
# effect already landed, so this only bounds how long the answer can lag.
LIVE_FOOD_RIDER_TIMEOUT_S = 10.0

PAY_UNAVAILABLE = "Pagos no disponibles por ahora"

# ★ THERE IS NO PATREON UNLOCK. v1 mapped active Patreon tiers onto pass tiers;
# the owner tested it live and rejected it outright -- "im able to use regular
# without even buying" was a Patreon-mapped account. The pass is bought with
# money (Stripe) or given by staff (gift). Nothing else grants it. Do not put
# the mapping back without him asking for it in those words.


# ===========================================================================
# XP curve + season helpers (owner's, kept verbatim)
# ===========================================================================
def xp_for_level(level: int) -> int:
    """Total XP needed to REACH `level`. level 1 = 0, level 100 = 59.251."""
    if level <= 1:
        return 0
    base = 450
    return int(base * (level - 1) * (1 + (level - 1) / 300))


def level_from_xp(xp: int) -> int:
    if xp <= 0:
        return 1
    lo, hi = 1, MAX_LEVEL
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if xp_for_level(mid) <= xp:
            lo = mid
        else:
            hi = mid - 1
    return lo


def level_progress(xp: int) -> dict:
    lv = level_from_xp(xp)
    cur = xp_for_level(lv)
    nxt = xp_for_level(min(lv + 1, MAX_LEVEL))
    span = max(1, nxt - cur)
    inside = max(0, int(xp) - cur)
    # At the cap there is no next level, so the bar reads 100% instead of the
    # 0% the owner's raw formula produces the instant a player hits 100.
    pct = 100.0 if lv >= MAX_LEVEL else round(min(1.0, inside / span) * 100.0, 1)
    return {
        "level": lv, "xp": int(xp), "xp_at_level": int(cur), "xp_next": int(nxt),
        "xp_in_level": int(inside), "xp_span": int(span),
        "percent": pct, "max_level": MAX_LEVEL, "capped": lv >= MAX_LEVEL,
    }


def current_season_id(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def season_bounds(season_id: str):
    y, m = [int(x) for x in season_id.split("-")]
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = datetime(y + 1, 1, 1, tzinfo=timezone.utc) if m == 12 else datetime(y, m + 1, 1, tzinfo=timezone.utc)
    return start, end


_SEASON_NAMES = {
    1: "Alba Primal", 2: "Marca del Colmillo", 3: "Sombra Ancestral", 4: "Rugido de Marzo",
    5: "Corazón de Ámbar", 6: "Marea Mesozoica", 7: "Fuego del Solsticio", 8: "Cacería Bajo el Sol",
    9: "Furia de Otoño", 10: "Colmillos de Hierro", 11: "Última Estación", 12: "Aliento del Invierno",
}


def _season_parts(season_id: str):
    """(year, month) or None -- every season helper below stays honest on a
    malformed id instead of raising inside a page render."""
    try:
        y, m = [int(x) for x in str(season_id).split("-")]
    except Exception:
        return None
    if not (1 <= m <= 12) or y < 1970:
        return None
    return y, m


def season_code(season_id: str) -> str:
    """The short code the money labels carry ("S08"), derived STRUCTURALLY from
    the id. It used to be taken by splitting the display name on " · " -- which
    breaks the instant a custom name has no separator in it, dropping the whole
    title into a transaction label."""
    parts = _season_parts(season_id)
    if not parts:
        return "S--"
    y, m = parts
    return f"S{((y - 2026) * 12 + m):02d}"


def season_display_name(season_id: str) -> str:
    """The BUILT-IN name for a season. This is the fallback; what the page shows
    is season_name(), which lets an admin override this per season."""
    parts = _season_parts(season_id)
    if not parts:
        return "Pase de Batalla"
    y, m = parts
    return f"{season_code(season_id)} · {_SEASON_NAMES.get(m, 'Temporada')} {y}"


# ---------------------------------------------------------------------------
# Owner-editable season name (his ask 2026-08-07: rename the pass season without
# a deploy). One doc per season in db.bp_seasons; an ABSENT or EMPTY name is not
# an error, it simply means "use the built-in name", so the default can always
# be restored by clearing the box.
# ---------------------------------------------------------------------------
SEASON_NAME_MAX = 48
_SEASON_NAME_TTL = 30.0                       # seconds; the page reads this on every load
_CTRL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_season_name_cache = {"at": None, "map": {}}


def sanitize_season_name(raw) -> str:
    """Control chars out, whitespace runs collapsed, hard length cap. The header
    is ONE line -- an unbounded string would blow the layout, and a newline or a
    tab would render as a gap nobody typed."""
    s = _CTRL_CHARS.sub(" ", str(raw if raw is not None else ""))
    s = " ".join(s.split())
    return s[:SEASON_NAME_MAX].strip()


def render_season_name(season_id: str, override) -> str:
    """Built-in name unless an override carries text. `verbatim` means the owner
    wants EXACTLY what he typed (no code, no year); otherwise his text takes the
    place of the built-in title and keeps "S08 · ... 2026" around it."""
    name = sanitize_season_name((override or {}).get("name"))
    if not name:
        return season_display_name(season_id)
    if (override or {}).get("verbatim"):
        return name
    parts = _season_parts(season_id)
    if not parts:
        return name
    return f"{season_code(season_id)} · {name} {parts[0]}"


async def _season_overrides(force: bool = False) -> dict:
    """TTL-cached read of every override. Bounded: one small collection, one
    query at most every 30s, and a read failure keeps serving the last good map
    (first-ever failure = the built-in names) rather than breaking the page."""
    now = time.monotonic()
    if not force and _season_name_cache["at"] is not None \
            and (now - _season_name_cache["at"]) < _SEASON_NAME_TTL:
        return _season_name_cache["map"]
    try:
        docs = await db.bp_seasons.find({}, {"_id": 0}).to_list(600)
        _season_name_cache["map"] = {d["season"]: d for d in docs if d.get("season")}
        _season_name_cache["at"] = now
    except Exception:
        logger.warning("[bp] season-name overrides unreadable -- serving the built-in names",
                       exc_info=True)
        _season_name_cache["at"] = now      # never hammer a broken read
    return _season_name_cache["map"]


async def season_override(season_id: str) -> dict:
    return (await _season_overrides()).get(season_id) or {}


async def season_name(season_id: str) -> str:
    """What every surface shows. Contained: if anything at all goes wrong the
    season still has its built-in name."""
    try:
        return render_season_name(season_id, await season_override(season_id))
    except Exception:
        logger.warning("[bp] season name render failed for %r", season_id, exc_info=True)
        return season_display_name(season_id)


async def set_season_name(season_id: str, raw_name, verbatim: bool = False,
                          by: str = "") -> dict:
    """Store (or CLEAR, when the text is empty) one season's name. Returns what
    the page will now show, so the caller never has to guess."""
    clean = sanitize_season_name(raw_name)
    if clean:
        await db.bp_seasons.update_one(
            {"season": season_id},
            {"$set": {"season": season_id, "name": clean, "verbatim": bool(verbatim),
                      "updated_at": _now_iso(), "updated_by": by or ""}},
            upsert=True)
    else:
        await db.bp_seasons.delete_one({"season": season_id})
    await _season_overrides(force=True)
    return {"season": season_id, "name": await season_name(season_id),
            "custom": bool(clean), "text": clean, "verbatim": bool(clean and verbatim),
            "default_name": season_display_name(season_id)}


def season_has_ended(season_id: str, now: Optional[datetime] = None) -> bool:
    try:
        _, end = season_bounds(season_id)
    except Exception:
        return False
    return (now or datetime.now(timezone.utc)) >= end


# ===========================================================================
# Species bands (LIN roster, 22 in-game species -- seed_data slugs)
# ===========================================================================
BAND_LOW = ("beipiao", "dryo", "hypsi", "ptera", "galli", "herrera", "troodon")
BAND_MID = ("austro", "dilo", "raptor", "pachy", "carno", "cerato", "kentro", "tenonto")
BAND_HIGH = ("allo", "diablo", "maia")
BANDS = {"low": BAND_LOW, "mid": BAND_MID, "high": BAND_HIGH}
# Owner order 2026-08-07: deino/trike/stego (and rex) are APEXES -- regular-row
# picks must not offer them; only the premium row's "all" picks may.
APEX_SLUGS = ("deino", "stego", "trike", "trex")

# ONE band per dino cell. The pass page is the consumer and its model is exactly
# that: a cell carries a single `band` key and DinoPicker renders
# status.dino_bands[cell.band], with BAND_LABEL naming it ("Bajo"/"Medio"/
# "Alto"/"Ápex"). A cumulative band could not be expressed through that field at
# all, and this also matches DESIGN.md's own bracket list literally
# (LOW at 25, MID at 50, HIGH at 75).
# Both rows pick at the same three levels, from the same three bands.
PICK_BAND_BY_LEVEL = {25: "low", 50: "mid", 75: "high"}

# Fixed level-100 cell, per ROW (not per tier any more).
APEX_BY_TRACK = {TRACK_REGULAR: "trike", TRACK_PREMIUM: "trex"}

_SPECIES_BY_SLUG = {slug: species for species, slug in game_telemetry.EVRIMA_SPECIES.items()}
_DINO_BY_SLUG = {d["slug"]: d for d in seed_data.DINOSAURS}
_CLASS_BY_SLUG = {slug: f"BP_{species}_C" for species, slug in game_telemetry.EVRIMA_SPECIES.items()}
_SLUG_BY_CLASS = {c: s for s, c in _CLASS_BY_SLUG.items()}
_SLUG_BY_SPECIES = dict(game_telemetry.EVRIMA_SPECIES)
_BAND_BY_SLUG = {}
for _b, _slugs in BANDS.items():
    for _s in _slugs:
        _BAND_BY_SLUG[_s] = _b
for _s in APEX_SLUGS:
    _BAND_BY_SLUG[_s] = "apex"

# Kill XP keeps the pre-2026-08-07 brackets: the owner's apex order moved
# deino/stego out of the REGULAR pick pool only -- a deino/stego kill still
# pays HIGH-band XP, not apex XP (test-pinned).
_XP_BAND_BY_SLUG = dict(_BAND_BY_SLUG)
_XP_BAND_BY_SLUG.update({"deino": "high", "stego": "high"})


ALL_PICK_SLUGS = tuple(BAND_LOW) + tuple(BAND_MID) + tuple(BAND_HIGH) + tuple(APEX_SLUGS)


def pick_band(track: str, level: int) -> Optional[str]:
    """The one band key a dino cell picks from, or None when the cell is FIXED.
    ★ The PREMIUM row's picks are UNRESTRICTED (owner order 2026-08-07: "for
    elder dino it should let me pick any specie") -- its three pick cells offer
    the whole roster, apexes included. The regular row keeps the low/mid/high
    brackets."""
    if int(level) not in PICK_BAND_BY_LEVEL:
        return None
    if normalize_track(track) == TRACK_PREMIUM:
        return "all"
    return PICK_BAND_BY_LEVEL.get(int(level))


def band_choices(track: str, level: int, tier: str = TIER_FREE) -> list:
    """Slugs a dino cell offers. Empty list = a FIXED cell (level 100)."""
    b = pick_band(track, level)
    if b == "all":
        return list(ALL_PICK_SLUGS)
    return list(BANDS[b]) if b else []


def fixed_dino(track: str, level: int, tier: str = TIER_FREE) -> Optional[str]:
    """The level-100 species. It is the ROW's, not the tier's -- a Premium+
    buyer claims the regular row's Triceratops AND the premium row's rex."""
    if int(level) != MAX_LEVEL:
        return None
    return APEX_BY_TRACK.get(track)


def _species_view(slug: str) -> dict:
    """{slug, name, rarity} — the shape DinoPicker renders (image is
    /dinos/<slug>.png, label is name, badge is rarity) and the shape
    BattlePassSection folds into its nameBySlug map."""
    d = _DINO_BY_SLUG.get(slug) or {}
    return {"slug": slug, "name": d.get("name") or slug, "rarity": d.get("rarity") or "Common"}


def dino_bands_view() -> dict:
    """Every band the page needs, INCLUDING apex — the section builds its whole
    slug -> display-name map out of this, and the level-100 cells are apex.
    "all" (the premium picks) lists the whole roster, low→apex order."""
    out = {b: [_species_view(s) for s in slugs] for b, slugs in BANDS.items()}
    out["apex"] = [_species_view(s) for s in APEX_SLUGS]
    out["all"] = [_species_view(s) for s in ALL_PICK_SLUGS]
    return out


# ===========================================================================
# Reward tracks -- EXACT per design. Totals asserted at import.
# ===========================================================================
DINO_LEVELS = (25, 50, 75, 100)          # both rows: 3 picks + the fixed apex

# ---- REGULAR row ($5) ------------------------------------------------------
REG_TOKEN_LEVELS = {20: "diet", 60: "diet", 40: "growth", 80: "growth"}
REG_SKIN_BY_LEVEL = {}
# Owner-retired regular cells (2026-08-08): 35 (bp_s_alba), 65 (bp_s_jungla)
# and 95 (bp_s_ambar) — all three regular-row skins removed from the catalog.
# Retired EMPTY, exactly like the premium level-20 sol removal: every other
# cell keeps its exact hand-approved amount (the PM ramp is a solver —
# un-occupying a cell would move every coin cell).
REG_RETIRED_LEVELS = frozenset({35, 65, 95})
# Hand-set by the owner's brief; they total EXACTLY 3.000 (asserted below).
REG_AMBER = {5: 150, 10: 180, 15: 210, 30: 270, 45: 330,
             55: 390, 70: 450, 85: 480, 90: 540}
REG_PM_BASE, REG_PM_STEP, REG_PM_TOPUP, REG_PM_TOPUP_N = 2000, 290, 500, 20

# ---- PREMIUM row ($10) -----------------------------------------------------
PRE_TOKEN_LEVELS = {10: "diet", 30: "diet", 65: "diet",
                    15: "growth", 45: "growth", 85: "growth"}
# bp_s_sol ("Sol de Medianoche") REMOVED on the owner's order 2026-08-08 -- its
# rebuilt look duplicated another skin. Its level-20 cell sat retired EMPTY
# until 2026-08-13, when the owner's "add these two skins to battle pass,
# crates, etc" re-opened it for "supernova". The occupied SET is unchanged
# either way (retired and skin cells both occupy), so every coin cell keeps
# its exact hand-approved amount — the PM ramp never re-solves.
# ★ supernova / constelacion live in glitch_catalog.GLITCH_SKINS (crate-
# droppable) AND are granted here — dual-surface by owner order; only the
# bp_exclusive flag keeps a skin out of crates, not its presence on the pass.
# ★ 2026-08-16 (owner order: "add the glitch skin ... to the 1rst place
#   leaderboard ... but add the pink glitter in BP"): supernova became the
#   season leaderboard's 1º-place prize, so the pink-glitter design
#   ("constelacion" — pink/white starfield sparkle) takes its premium level-20
#   cell and supernova moves to the level-100 apex rider. A STRAIGHT SWAP on
#   purpose: the occupied-set is unchanged, so the PrimeMeat ramp never
#   re-solves and every other cell keeps its exact hand-approved amount; and
#   every cell still grants a DISTINCT skin (the import gate below enforces it).
PRE_SKIN_BY_LEVEL = {20: "constelacion", 55: "bp_s_vacio", 90: "bp_s_eclipse"}
PRE_RETIRED_LEVELS = frozenset()
PRE_PM_BASE, PRE_PM_STEP = 7065, 125

# Rides along with the premium row's level-100 Tyrannosaurus claim. bp_s_corona
# ("Corona del Rey") was REMOVED by owner order 2026-08-08; the rider returned
# 2026-08-13 carrying "constelacion" (owner order: the two new skins enter the
# Battle Pass), and swapped to "supernova" 2026-08-16 when constelacion took
# the level-20 cell (see PRE_SKIN_BY_LEVEL). The dino claim itself is untouched.
APEX_BONUS_SKIN = "supernova"


def _cell(kind: str, **kw) -> dict:
    d = {"type": kind}
    d.update(kw)
    return d


def _bp_skin_rarity(gid: str) -> str:
    """Cell rarity for ANY pass-granted skin: a BP exclusive carries its own
    bp_rarity; a dual-surface catalog skin (2026-08-13: supernova /
    constelacion) rides the crate rarity. KeyError-free by the import gate
    below (every cell id must resolve in GLITCH_BY_ID)."""
    g = glitch_catalog.GLITCH_BY_ID.get(gid) or {}
    return g.get("bp_rarity") or glitch_catalog.GLITCH_RARITY


def _skin_cell(gid: str) -> dict:
    return _cell("skin", skin=gid, rarity=_bp_skin_rarity(gid))


def _ramp_pm(levels, base: int, step: int, topup: int = 0, topup_n: int = 0) -> dict:
    """Deterministic PrimeMeat solver: a linear ramp base + step*level over the
    row's remaining levels, then a flat top-up on the highest `topup_n` of them
    to land the total on the nose. Integers only, no rounding anywhere -- the
    total is a promise, not an approximation."""
    levels = sorted(levels)
    out = {lv: base + step * lv for lv in levels}
    if topup and topup_n:
        for lv in levels[-topup_n:]:
            out[lv] += topup
    return out


def _build_regular_track() -> list:
    empty = {lv for lv in range(1, MAX_LEVEL + 1) if lv % 10 in (3, 7)}
    occupied = (empty | set(REG_TOKEN_LEVELS) | set(DINO_LEVELS) | set(REG_SKIN_BY_LEVEL)
                | set(REG_AMBER) | REG_RETIRED_LEVELS)
    pm = _ramp_pm([lv for lv in range(1, MAX_LEVEL + 1) if lv not in occupied],
                  REG_PM_BASE, REG_PM_STEP, REG_PM_TOPUP, REG_PM_TOPUP_N)
    out = []
    for lv in range(1, MAX_LEVEL + 1):
        if lv in empty or lv in REG_RETIRED_LEVELS:
            row = _cell("empty")
        elif lv in REG_TOKEN_LEVELS:
            row = _cell("token", token=REG_TOKEN_LEVELS[lv])
        elif lv in DINO_LEVELS:
            row = _cell("dino")
        elif lv in REG_SKIN_BY_LEVEL:
            row = _skin_cell(REG_SKIN_BY_LEVEL[lv])
        elif lv in REG_AMBER:
            row = _cell("amber", amount=REG_AMBER[lv])
        else:
            row = _cell("coins", amount=pm[lv])
        row["level"] = lv
        out.append(row)
    return out


def _build_premium_track() -> list:
    amber = {lv: 42 + 4 * lv for lv in range(1, MAX_LEVEL + 1) if lv % 8 == 0}
    occupied = (set(PRE_TOKEN_LEVELS) | set(DINO_LEVELS) | set(PRE_SKIN_BY_LEVEL)
                | set(amber) | PRE_RETIRED_LEVELS)
    pm = _ramp_pm([lv for lv in range(1, MAX_LEVEL + 1) if lv not in occupied],
                  PRE_PM_BASE, PRE_PM_STEP)
    out = []
    for lv in range(1, MAX_LEVEL + 1):
        if lv in PRE_RETIRED_LEVELS:
            row = _cell("empty")
        elif lv in PRE_TOKEN_LEVELS:
            row = _cell("token", token=PRE_TOKEN_LEVELS[lv])
        elif lv in DINO_LEVELS:
            row = _cell("dino")
        elif lv in PRE_SKIN_BY_LEVEL:
            row = _skin_cell(PRE_SKIN_BY_LEVEL[lv])
        elif lv in amber:
            row = _cell("amber", amount=amber[lv])
        else:
            row = _cell("coins", amount=pm[lv])
        row["level"] = lv
        out.append(row)
    return out


REGULAR_TRACK = _build_regular_track()
PREMIUM_TRACK = _build_premium_track()
_TRACK_CELLS = {TRACK_REGULAR: REGULAR_TRACK, TRACK_PREMIUM: PREMIUM_TRACK}


def get_track(track: str) -> list:
    return _TRACK_CELLS.get(normalize_track(track) or TRACK_REGULAR, REGULAR_TRACK)


def cell_at(track: str, level: int) -> Optional[dict]:
    if not isinstance(level, int) or level < 1 or level > MAX_LEVEL:
        return None
    return get_track(track)[level - 1]


def _require(cond, msg: str) -> None:
    """Deliberately NOT `assert`: `python -O` strips asserts, and a promise that
    disappears under an optimisation flag is not a promise."""
    if not cond:
        raise RuntimeError(msg)


def _assert_track_totals() -> None:
    """The owner's exact numbers, checked at IMPORT. A cell edit that breaks any
    of them refuses to load rather than quietly paying a wrong economy.

        REGULAR row  1.000.000 PM + 3.000 AMB, 12 mutations (4 dinos x 3
                     non-prime), 20 empty cells
        PREMIUM row  1.000.000 PM + 3.000 AMB, 16 mutations (4 dinos x 4
                     PRIME), no retired cells (level 20 re-opened 2026-08-13,
                     carrying constelacion since the 2026-08-16 swap; the
                     level-100 claim carries the supernova rider)
        a Premium+ buyer claims BOTH  ->  2.000.000 PM + 6.000 AMB, 28 mutations
    """
    totals = {}
    for track, cells in _TRACK_CELLS.items():
        _require(len(cells) == MAX_LEVEL, f"[bp] {track} row is not 100 levels long")
        pm = [c["amount"] for c in cells if c["type"] == "coins"]
        amb = [c["amount"] for c in cells if c["type"] == "amber"]
        _require(all(isinstance(v, int) for v in pm + amb),
                 f"[bp] {track} row has a non-integer currency cell")
        _require(sum(pm) == 1_000_000, f"[bp] {track} PrimeMeat total {sum(pm)} != 1.000.000")
        _require(sum(amb) == 3_000, f"[bp] {track} Amberium total {sum(amb)} != 3.000")
        dinos = [c["level"] for c in cells if c["type"] == "dino"]
        _require(tuple(dinos) == DINO_LEVELS, f"[bp] {track} dino cells at {dinos}")
        totals[track] = (sum(pm), sum(amb), len(dinos) * mutations_per_dino(track))
    _require(sum(t[0] for t in totals.values()) == 2_000_000,
             "[bp] both rows together must total 2.000.000 PrimeMeat")
    _require(sum(t[1] for t in totals.values()) == 6_000,
             "[bp] both rows together must total 6.000 Amberium")
    _require(totals[TRACK_REGULAR][2] == 12 and totals[TRACK_PREMIUM][2] == 16,
             "[bp] rows must carry 12 (4 x 3 non-prime) and 16 (4 x 4 PRIME) "
             "mutations -- 28 for a Premium+ buyer")
    empties = [c["level"] for c in REGULAR_TRACK if c["type"] == "empty"]
    reg_owner_empties = [lv for lv in empties if lv not in REG_RETIRED_LEVELS]
    _require(len(reg_owner_empties) == 20 and all(lv % 10 in (3, 7) for lv in reg_owner_empties),
             "[bp] the regular row must have 20 empty cells at levels ending in 3 or 7")
    _require(sorted(lv for lv in empties if lv in REG_RETIRED_LEVELS) == sorted(REG_RETIRED_LEVELS),
             "[bp] regular retired cells must be exactly the owner-retired levels")
    pre_empties = [c["level"] for c in PREMIUM_TRACK if c["type"] == "empty"]
    _require(sorted(pre_empties) == sorted(PRE_RETIRED_LEVELS),
             "[bp] premium empties must be exactly the owner-retired cells")
    # Bands may only name species that really exist in game.
    slugs = {d["slug"] for d in seed_data.DINOSAURS}
    for band in list(BANDS.values()) + [APEX_SLUGS, tuple(APEX_BY_TRACK.values())]:
        for s in band:
            _require(s in slugs, f"[bp] band species {s!r} is not in seed_data")
            _require(s in _CLASS_BY_SLUG, f"[bp] band species {s!r} has no game class")
    skins = list(REG_SKIN_BY_LEVEL.values()) + list(PRE_SKIN_BY_LEVEL.values()) + [APEX_BONUS_SKIN]
    _require(len(set(skins)) == len(skins), "[bp] a skin is granted by two different cells")
    for gid in skins:
        # 2026-08-13: a pass cell may grant any catalog design, not only a BP
        # exclusive — exclusivity is the SKIN's bp_exclusive flag (keeps it out
        # of crates), never a property of the granting cell.
        _require(gid in glitch_catalog.GLITCH_BY_ID, f"[bp] skin {gid!r} is not in the glitch catalog")
    _require(all(_bp_skin_rarity(g) != "Legendary"
                 for g in REG_SKIN_BY_LEVEL.values()),
             "[bp] the regular row must not carry a Legendary skin")
    _require(all(_bp_skin_rarity(g) == "Legendary"
                 for g in list(PRE_SKIN_BY_LEVEL.values()) + [APEX_BONUS_SKIN]),
             "[bp] every premium-row skin must be Legendary")


_assert_track_totals()


# ===========================================================================
# Tier resolve (owner's precedence, with the manual-wins rule made explicit)
# ===========================================================================
def resolve_tier(user: dict, pass_doc: Optional[dict]) -> tuple:
    """(tier, source) -- the ONLY thing that grants a pass is a paid Stripe
    session or a staff gift, both of which are written onto the pass document.
    A Patreon membership, however high, resolves to `free` (owner ruling
    2026-08-07). `user` is accepted and deliberately unused so every caller
    keeps the same signature."""
    p = pass_doc or {}
    stored = p.get("tier")
    if stored in (TIER_REGULAR, TIER_PREMIUM):
        return stored, p.get("tier_source") or "manual"
    return TIER_FREE, "free"


# ===========================================================================
# Small utilities
# ===========================================================================
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _steam_id(user: dict) -> str:
    sid = str((user or {}).get("steam_id") or "").strip()
    if not sid:
        raise HTTPException(status_code=400,
                            detail="Vincula tu cuenta de Steam para usar el Pase de Batalla.")
    return sid


def _fail(status: int, detail: str):
    raise HTTPException(status_code=status, detail=detail)


def _seeded_rng(*parts) -> random.Random:
    """Deterministic per (user, season, track, level, ...) so a retried claim can
    never reroll into a better dino."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


# ===========================================================================
# Mongo: indexes + pass document
# ===========================================================================
async def ensure_indexes() -> None:
    """Contained on purpose -- the host awaits this at startup, and one index
    failure must never crash-loop the whole site. The claim/webhook lanes each
    also read-before-write, so an absent index degrades to a narrow race, not to
    an open door."""
    try:
        await db.bp_passes.create_index([("user_id", 1), ("season", 1)], unique=True,
                                        name="bp_pass_user_season")
        await db.bp_passes.create_index([("season", 1), ("settled", 1)], name="bp_pass_settle")
        await db.bp_passes.create_index([("season", 1), ("skin_layout_sig", 1)],
                                        name="bp_pass_skin_layout")
        await db.bp_claims.create_index(
            [("user_id", 1), ("season", 1), ("track", 1), ("level", 1)],
            unique=True, name="bp_claim_once")
        await db.bp_payments.create_index("session_id", unique=True, name="bp_payment_session")
        await db.bp_payments.create_index([("user_id", 1), ("created_at", -1)])
        await db.bp_stripe_events.create_index("event_id", unique=True, name="bp_event_once")
        await db.bp_seasons.create_index("season", unique=True, name="bp_season_once")
        logger.info("[bp] indexes ready")
    except Exception:
        logger.error("[bp] index build FAILED -- claims still refuse duplicates via the "
                     "read-before-write check, but the race guard is off until this is fixed",
                     exc_info=True)


async def _get_pass(user_id: str, season: str, create: bool = True) -> dict:
    doc = await db.bp_passes.find_one({"user_id": user_id, "season": season}, {"_id": 0})
    if doc or not create:
        return doc or {}
    try:
        await db.bp_passes.update_one(
            {"user_id": user_id, "season": season},
            {"$setOnInsert": {"id": _new_id(), "user_id": user_id, "season": season,
                              "xp": 0, "tier": TIER_FREE, "tier_source": "free",
                              "settled": False, "created_at": _now_iso()}},
            upsert=True)
    except DuplicateKeyError:
        # Two tabs opening the pass page at once both upsert against the unique
        # (user_id, season) index; the loser just reads what the winner wrote.
        pass
    return await db.bp_passes.find_one({"user_id": user_id, "season": season}, {"_id": 0}) or {}


async def _add_xp(user_id: str, amount: int, reason: str) -> None:
    if not user_id or amount <= 0:
        return
    season = current_season_id()
    await db.bp_passes.update_one(
        {"user_id": user_id, "season": season},
        {"$inc": {"xp": int(amount)},
         "$setOnInsert": {"id": _new_id(), "user_id": user_id, "season": season,
                          "tier": TIER_FREE, "tier_source": "free", "settled": False,
                          "created_at": _now_iso()}},
        upsert=True)
    logger.debug("[bp] +%d xp user=%s (%s)", amount, user_id, reason)


# ===========================================================================
# XP hooks -- called from server.py. Each is independently contained: the host
# wraps them too, but a hook that can take the host path down is a bug even if
# the host is wrapped.
# ===========================================================================
async def hook_passive_xp(user_id: str, cycles: int) -> None:
    """+60 BP XP per 4-minute passive cycle actually PAID (normal and catch-up)."""
    try:
        n = int(cycles or 0)
        if n <= 0:
            return
        await _add_xp(user_id, BP_XP_PER_PLAYTIME_CYCLE * n, f"passive x{n}")
    except Exception as e:
        logger.warning("[bp] hook_passive_xp failed: %r", e)


async def hook_quest_xp(user_id: str, rarity) -> None:
    try:
        amt = BP_XP_QUEST_BY_RARITY.get(str(rarity or ""))
        if not amt:
            return
        await _add_xp(user_id, amt, f"quest {rarity}")
    except Exception as e:
        logger.warning("[bp] hook_quest_xp failed: %r", e)


_kill_pair_seen: dict = {}


def _kill_pair_allowed(killer_sid: str, victim_sid: str, now: Optional[float] = None) -> bool:
    """30-minute XP cooldown per killer->victim pair. In-process on purpose: a
    restart re-opening one pair pays 500 XP at most, while a Mongo round-trip in
    the telemetry drain loop would cost one per kill on every poll."""
    now = time.time() if now is None else now
    key = (str(killer_sid), str(victim_sid))
    last = _kill_pair_seen.get(key)
    if last is not None and (now - last) < KILL_PAIR_COOLDOWN_S:
        return False
    _kill_pair_seen[key] = now
    if len(_kill_pair_seen) > 20000:  # unbounded growth guard
        cutoff = now - KILL_PAIR_COOLDOWN_S
        for k, v in list(_kill_pair_seen.items()):
            if v < cutoff:
                _kill_pair_seen.pop(k, None)
    return True


def kill_xp_for(victim_species, victim_growth) -> int:
    """FAIL CLOSED. The kill feed's victim fields are optional -- an unknown
    species or an unknown growth pays NOTHING rather than guessing a band."""
    if victim_species is None or victim_growth is None:
        return 0
    slug = _SLUG_BY_SPECIES.get(str(victim_species).strip())
    if not slug:
        return 0
    try:
        g = float(victim_growth)
    except (TypeError, ValueError):
        return 0
    if g != g or g < KILL_MIN_VICTIM_GROWTH:  # NaN guard + growth floor
        return 0
    band = _XP_BAND_BY_SLUG.get(slug)
    return BP_XP_KILL_BY_BAND.get(band, 0)


async def hook_kill_xp(killer_user_id: str, victim_species, victim_growth,
                       killer_sid, victim_sid) -> None:
    try:
        if not killer_user_id:
            return
        ks, vs = str(killer_sid or "").strip(), str(victim_sid or "").strip()
        if not ks or not vs or ks == vs:      # self-kills never count
            return
        amt = kill_xp_for(victim_species, victim_growth)
        if amt <= 0:
            return
        if not _kill_pair_allowed(ks, vs):
            return
        await _add_xp(killer_user_id, amt, f"kill {victim_species}")
    except Exception as e:
        logger.warning("[bp] hook_kill_xp failed: %r", e)


_last_periodic = 0.0
PERIODIC_INTERVAL_S = 3600.0


async def periodic() -> None:
    """Cheap heartbeat called from the kill-drain hook site. No-ops in under a
    microsecond except once an hour, when it settles any ended season so absent
    players are banked without anybody pressing the admin button."""
    global _last_periodic
    try:
        now = time.time()
        if now - _last_periodic < PERIODIC_INTERVAL_S:
            return
        _last_periodic = now
        # ★ EACH LANE IS CONTAINED ON ITS OWN. The hourly clock is advanced
        # ABOVE, before either call, so a raise that escaped one lane would cost
        # the OTHER lane a full hour every hour -- silently, and forever if the
        # cause is persistent. settle_ended_seasons() reads Mongo outside any
        # try of its own, so this is a live failure mode, not a theoretical one.
        try:
            await settle_ended_seasons()
        except Exception as e:
            logger.warning("[bp] settle sweep failed: %r", e)
        # Catches players who never open the pass page after a cell swap.
        try:
            await sweep_skin_layout()
        except Exception as e:
            logger.warning("[bp] skin sweep failed: %r", e)
    except Exception as e:
        logger.warning("[bp] periodic failed: %r", e)


# ===========================================================================
# Reward payout lanes
# ===========================================================================
# ★ NOTHING IS HALVED. v1 listed one row at full price and paid a Regular buyer
# half of it; v2 gives each row its own literal numbers instead, so what a cell
# shows is what it pays. There is no _halve helper and no amount_granted field.


async def _pay_currency(user, kind: str, amount: int, label: str) -> dict:
    field = "coins" if kind == "coins" else "vip_coins"
    currency = "normal" if kind == "coins" else "vip"
    await db.users.update_one({"id": user["id"]}, {"$inc": {field: int(amount)}})
    try:
        await _add_transaction(user["id"], currency, int(amount), "reward", label)
    except Exception as e:
        logger.warning("[bp] ledger row failed (payment stands): %r", e)
    unit = "PrimeMeat" if kind == "coins" else "Amberium"
    return {"kind": kind, "amount": int(amount), "text": f"{int(amount):,} {unit}".replace(",", ".")}


def _token_flavor(track: str, tier: str = TIER_FREE) -> str:
    """The flavour is the ROW's. `tier` is accepted and unused so every call
    site keeps one signature."""
    return ROW_TOKEN_FLAVOR.get(track, "basic")


async def _grant_token(user, token: str, flavor: str, season: str) -> dict:
    name = ("Ficha de Dieta" if token == "diet" else "Ficha de Crecimiento")
    name += " Premium" if flavor == "premium" else " Básica"
    doc = {
        "id": _new_id(), "user_id": user["id"],
        "item_id": f"bp_token_{token}_{flavor}", "name": name, "category": "Tokens",
        "rarity": "Epic" if flavor == "premium" else "Rare",
        "image": f"/tokens/{token}.png",
        "token": token, "token_tier": flavor, "season": season,
        "quantity": 1, "acquired_at": _now_iso(),
    }
    await db.inventory.insert_one(doc)
    return {"kind": "token", "token": token, "tier": flavor, "inv_id": doc["id"], "text": name}


async def _grant_skin(user, glitch_id: str, season: str) -> dict:
    """Byte-identical to the crate grant lane (server.py _grant_case_reward), so
    a Battle Pass skin behaves exactly like a won one everywhere downstream."""
    g = glitch_catalog.GLITCH_BY_ID.get(glitch_id)
    if not g:
        raise RuntimeError(f"unknown bp skin {glitch_id}")
    source = f"Pase de Batalla {season_code(season)}"
    await db.reward_skins.update_one(
        {"user_id": user["id"], "glitch_id": glitch_id},
        {"$inc": {"quantity": 1, "uses": GLITCH_USES_PER_WIN},
         "$set": {"last_won_at": _now_iso(), "source": source},
         "$setOnInsert": {
             "id": _new_id(), "name": g["name"], "subtitle": g["subtitle"],
             "image": g["preview"], "accent_hex": g["accent_hex"],
             "rarity": g.get("bp_rarity") or glitch_catalog.GLITCH_RARITY,
             "acquired_at": _now_iso(),
         }},
        upsert=True)
    return {"kind": "skin", "skin": glitch_id, "text": g["name"]}


# ===========================================================================
# Claimed-cell skin reconciliation
# ===========================================================================
# A cell's skin gets SWAPPED mid-season by owner order -- bp_s_sol out
# 2026-08-08, supernova into level 20 on 08-13, supernova -> constelacion on
# 08-16 with the apex rider swapping the other way. bp_claims is uniquely
# indexed on (user_id, season, track, level), so a player who had ALREADY
# claimed that cell can never claim it again: the new skin is unreachable for
# them forever while every later claimer gets it, and a pre-swap claimer ends
# the season with a DUPLICATE where the row promises four distinct skins.
# Measured 2026-08-20 before this landed: 23 paying premium players were short
# 24 skins between them, every one of them premium_plus.
#
# The cure: a claim on a skin-bearing cell is reconciled against what that cell
# grants TODAY, and anything short is granted through the normal lane. Nothing
# is ever revoked -- a skin granted under the old layout was legitimately won.
#
# ★ THE GATE IS A STAMP ON THE CLAIM, never "does the player hold the skin".
#   A reward_skins row is DELETED when its last use is spent (server.py), so a
#   holds-it test would re-grant the skin every time the player used it up:
#   free legendaries forever. The stamp is the only key that survives.
def _skins_owed_at(track: str, level: int) -> tuple:
    """Every skin this cell grants TODAY, catalog-checked so a retired id (the
    removed bp_s_sol / bp_s_corona) can never reach the grant lane."""
    out = []
    c = cell_at(track, level)
    if c and c.get("type") == "skin" and c.get("skin"):
        out.append(c["skin"])
    if track == TRACK_PREMIUM and level == MAX_LEVEL and APEX_BONUS_SKIN:
        out.append(APEX_BONUS_SKIN)
    return tuple(g for g in out if g in glitch_catalog.GLITCH_BY_ID)


def _build_skin_layout() -> tuple:
    out = []
    for tr in TRACKS:
        for lv in range(1, MAX_LEVEL + 1):
            owed = _skins_owed_at(tr, lv)
            if owed:
                out.append((tr, lv, owed))
    return tuple(out)


SKIN_LAYOUT = _build_skin_layout()
# Changes the moment the owner swaps, adds or retires any skin cell. It is what
# tells a pass document it has drifted; a matching signature costs one dict read.
SKIN_LAYOUT_SIG = hashlib.sha256(repr(SKIN_LAYOUT).encode("utf-8")).hexdigest()[:16]
SKIN_SWEEP_LIMIT = 200


def _claim_skins(claim: dict) -> list:
    """Every skin this claim is on record as having delivered -- what it granted
    at the time, PLUS anything a previous backfill already stamped on it. The
    stamp counts as delivered even when the reward_skins row is long gone."""
    out = [(e or {}).get("skin") for e in (claim.get("effects") or [])
           if (e or {}).get("kind") == "skin"]
    return [g for g in out if g] + list(claim.get("skin_backfill") or ())


def plan_skin_shortfall(claims: list) -> list:
    """[(claim, skin_id), ...] -- what this player's claimed cells still owe.

    ★ THE UNIT IS THE ROW, NOT THE CELL. LIN's 2026-08-16 edit was a STRAIGHT
      SWAP: constelacion took level 20 and supernova took the level-100 rider,
      trading places. A player who claimed BOTH cells in the window before it
      already holds exactly today's pair -- just assigned to the opposite cells
      -- and owes nothing. Reconciling cell-by-cell would hand that player both
      skins a SECOND time. Measured 2026-08-20: one real player, two phantom
      grants. So the shortfall is a MULTISET difference over the cells the
      player has actually claimed: what those cells grant today, minus what
      those same claims already delivered.

    A multiset (not a set) because a future layout may legitimately place the
    same skin on two cells, and then the row really does owe it twice.

    Only cells the player HAS claimed are counted -- an unclaimed cell owes
    nothing yet, and will grant the current skin when they claim it normally.
    """
    owed = collections.Counter()
    have = collections.Counter()
    for cl in claims:
        owed.update(_skins_owed_at(cl.get("track"), cl.get("level")))
        have.update(_claim_skins(cl))
    short = owed - have
    if not short:
        return []
    plan = []
    for cl in claims:
        stamped = set(cl.get("skin_backfill") or ())
        for gid in _skins_owed_at(cl.get("track"), cl.get("level")):
            # Never stamp the same skin onto one claim twice, and stop as soon
            # as the row's debt for that skin is covered.
            if short[gid] > 0 and gid not in stamped:
                plan.append((cl, gid))
                short[gid] -= 1
    return plan


async def _backfill_one_skin(user, season: str, claim: dict, gid: str) -> int:
    """One grant, exactly once. The claim row is stamped FIRST and that stamp is
    the mutex -- a second tab, or the hourly sweep landing at the same moment,
    matches 0 documents and does nothing. A failed grant rolls the stamp back so
    the next pass retries instead of swallowing the debt."""
    res = await db.bp_claims.update_one(
        {"_id": claim["_id"], "skin_backfill": {"$ne": gid},
         "effects": {"$not": {"$elemMatch": {"kind": "skin", "skin": gid}}}},
        {"$addToSet": {"skin_backfill": gid}, "$set": {"skin_backfill_at": _now_iso()}})
    if res.matched_count != 1:
        return 0
    try:
        eff = await _grant_skin(user, gid, season)
        await db.bp_claims.update_one(
            {"_id": claim["_id"]}, {"$push": {"effects": {**eff, "backfill": True}}})
        logger.info("[bp] skin_backfill user=%s %s L%s +%s",
                    user.get("id"), claim.get("track"), claim.get("level"), gid)
        return 1
    except Exception as e:
        await db.bp_claims.update_one({"_id": claim["_id"]},
                                      {"$pull": {"skin_backfill": gid}})
        logger.warning("[bp] skin_backfill FAILED user=%s %s L%s %s: %r "
                       "(stamp rolled back, retries next pass)",
                       user.get("id"), claim.get("track"), claim.get("level"), gid, e)
        return 0


async def _reconcile_claimed_skins(user, season: str, pass_doc=None) -> int:
    """Grant whatever a player's already-claimed cells are short after a swap.

    Contained on purpose: this rides the pass page's own load, and a reconcile
    failure must never turn that page into a 500. Costs nothing when the layout
    has not moved -- the pass document carries the signature it was last
    reconciled against, so the common case is a single dict lookup and return.
    """
    uid = (user or {}).get("id")
    if not uid or not SKIN_LAYOUT:
        return 0
    try:
        doc = pass_doc if pass_doc is not None else await _get_pass(uid, season, create=False)
        if (doc or {}).get("skin_layout_sig") == SKIN_LAYOUT_SIG:
            return 0
        cells = [{"track": tr, "level": lv} for tr, lv, _ in SKIN_LAYOUT]
        claims = await db.bp_claims.find(
            {"user_id": uid, "season": season, "$or": cells}).to_list(len(cells))
        granted = 0
        for cl, gid in plan_skin_shortfall(claims):
            granted += await _backfill_one_skin(user, season, cl, gid)
        # Stamped LAST and unconditionally: a player with nothing owed is
        # reconciled too, so the sweep below never looks at them again.
        await db.bp_passes.update_one(
            {"user_id": uid, "season": season},
            {"$set": {"skin_layout_sig": SKIN_LAYOUT_SIG, "skin_layout_at": _now_iso()}})
        if isinstance(doc, dict):
            doc["skin_layout_sig"] = SKIN_LAYOUT_SIG
        return granted
    except Exception as e:
        logger.warning("[bp] skin reconcile failed user=%s: %r", uid, e)
        return 0


async def sweep_skin_layout(limit: int = SKIN_SWEEP_LIMIT) -> dict:
    """Reconcile players who have NOT opened the pass page since a swap, so a
    player who simply stopped visiting the site is still made whole. Bounded per
    run and driven off the signature index, so a settled fleet costs one query
    that matches nothing."""
    season = current_season_id()
    scanned = granted = 0
    try:
        docs = await db.bp_passes.find(
            {"season": season, "skin_layout_sig": {"$ne": SKIN_LAYOUT_SIG}},
            {"_id": 0, "user_id": 1}).to_list(max(1, int(limit)))
        for d in docs:
            uid = d.get("user_id")
            u = await db.users.find_one({"id": uid}, {"_id": 0}) if uid else None
            if not u:
                # A pass with no user row must not pin the sweep forever.
                await db.bp_passes.update_one(
                    {"user_id": uid, "season": season},
                    {"$set": {"skin_layout_sig": SKIN_LAYOUT_SIG,
                              "skin_layout_at": _now_iso()}})
                continue
            scanned += 1
            granted += await _reconcile_claimed_skins(u, season, d)
    except Exception as e:
        logger.warning("[bp] skin sweep failed: %r", e)
    if granted or scanned:
        logger.info("[bp] skin sweep scanned=%d granted=%d", scanned, granted)
    return {"scanned": scanned, "granted": granted}


def _pick_mutations(dino_class: str, count: int, *seed_parts) -> str:
    """`count` diet-legal mutations for this species, chosen deterministically so
    a retried claim can never reroll. Returns the 4-segment "|" own column."""
    segs = ["None"] * 4
    if count > 0:
        pool = sorted(set(mutation_catalog.PICKABLE) & mutation_catalog.allowed_names_for_class(dino_class))
        if pool:
            rng = _seeded_rng(*seed_parts)
            picks = rng.sample(pool, k=min(int(count), len(pool)))
            for i, name in enumerate(picks[:4]):
                segs[i] = name
    return mutation_catalog.join_segments(segs)


async def _grant_dino(user, slug: str, track: str, tier: str, season: str, level: int) -> dict:
    """The store purchase precedent (server.py purchase_dino), same payload
    shape: 0-sentinel vitals, no elder_stacks key, prime == elder."""
    dino_class = _CLASS_BY_SLUG.get(slug)
    if not dino_class:
        _fail(400, "Esa especie no está disponible en el servidor de juego.")
    sid = _steam_id(user)
    # ★ The ROW decides, not the buyer's tier: a Premium+ buyer claiming the
    # regular row's pick gets that row's non-prime 150% version, and the premium
    # row's PRIME 300% one on top. Owner order 2026-08-08: non-prime rewards
    # carry 3 mutations, prime rewards carry 4.
    rules = ROW_DINO_RULES.get(track) or ROW_DINO_RULES["regular"]
    is_prime = bool(rules["prime"])
    diet = float(rules["diet"])
    mut_count = MUTATIONS_PRIME if is_prime else MUTATIONS_NON_PRIME
    pd = {
        "dino": dino_class,
        "growth": DINO_GROWTH,
        "is_prime": is_prime,
        "is_elder": is_prime,
        "mutations": _pick_mutations(dino_class, mut_count,
                                     user["id"], season, track, level, dino_class),
        "parent_mutations": mutation_catalog.join_segments(["None"] * 4),
        "elder_mutations": "",
        # NO elder_stacks key and NO vitals keys, on purpose: 0 is the mod's
        # admin-add sentinel and the store lane relies on it (server.py:1650).
        "diet_a": diet, "diet_b": diet, "diet_c": diet,
    }
    # The PREMIUM row's dino is sold as PRIME, so it is minted prime-complete:
    # is_prime alone left prime_conditions/prime_route_mig/prime_route_pat NULL
    # and the mod planned no prime restore leg, delivering a plain animal. The
    # REGULAR row is not prime and is not touched by this call.
    # (2026-08-08 primemint fix, deployed box-direct that day; mirrored into
    # the repo 2026-08-13 when the deploy lane's drift guard caught it.)
    pd = vault.mint_prime_state(pd)
    cap = int(_park_cap(user) or 0)
    discord_id = await asyncio.to_thread(vault.resolve_discord_id, sid)
    try:
        row_id = await asyncio.to_thread(vault.save_parked, sid, discord_id, pd, cap)
    except Exception:
        logger.exception("[bp] save_parked crashed sid=%s slug=%s", sid, slug)
        row_id = None
    if row_id is None:
        # Vault full (or the write was lost). REFUSE HONESTLY -- the caller
        # deletes the claim row so the cell stays claimable.
        raise _VaultFull()
    logger.info("[bp] dino delivered sid=%s slug=%s track=%s tier=%s row=%s", sid, slug, track, tier, row_id)
    name = seed_data.DINOSAURS and next((d["name"] for d in seed_data.DINOSAURS if d["slug"] == slug), slug)
    return {"kind": "dino", "slug": slug, "vault_row": row_id,
            "text": f"{name} 75% {'PRIME ' if is_prime else ''}en tu Bóveda"}


class _VaultFull(Exception):
    pass


# ===========================================================================
# Claims
# ===========================================================================
def _skin_view(gid: str, rarity: Optional[str] = None) -> dict:
    """RewardCard reads cell.skin.name and cell.skin.rarity -- the skin is an
    OBJECT on the cell, not an id."""
    g = glitch_catalog.GLITCH_BY_ID.get(gid) or {}
    prox = glitch_catalog.design_proximity(g) if g else {"accent": "#7CA842", "strip": []}
    return {"id": gid, "name": g.get("name") or gid,
            "rarity": rarity or g.get("bp_rarity") or glitch_catalog.GLITCH_RARITY,
            # A glitch card is a NAME + COLOUR PROXIMITY, never a picture
            # (fleet order 2026-08-11) — image stays "" for schema stability.
            "image": "", "proximity": prox["strip"], "accent_hex": g.get("accent_hex")}


def _cell_public(c: dict, track: str, tier: str = TIER_FREE) -> dict:
    """One track cell, in the shape the pass page consumes.

    ★ `amount` is LITERAL. Each row now carries its own numbers, so there is no
    halving anywhere and no `amount_granted`. `premium_only` is gone too -- the
    ROW is the entitlement now.
    """
    out = {"level": c["level"], "type": c["type"]}
    if c["type"] in ("coins", "amber"):
        out["amount"] = c["amount"]
    elif c["type"] == "token":
        out["token"] = c["token"]
        # `tier` on a cell is the token FLAVOUR (RewardCard.tokenDetail), not the
        # pass tier; token_tier is kept as an alias for any older reader.
        out["tier"] = _token_flavor(track)
        out["token_tier"] = out["tier"]
    elif c["type"] == "skin":
        out["skin"] = _skin_view(c["skin"], c.get("rarity"))
    elif c["type"] == "dino":
        fixed = fixed_dino(track, c["level"])
        # ★ `slug` present == FIXED cell; ABSENT == a pick. The page keys its
        # "open the picker" branch and its pending-picks banner on exactly that.
        if fixed:
            out["slug"] = fixed
        out["band"] = pick_band(track, c["level"]) or "apex"
        out["growth"] = DINO_GROWTH
        rules = ROW_DINO_RULES.get(track) or ROW_DINO_RULES["regular"]
        out["prime"] = bool(rules["prime"])
        out["mutations"] = mutations_per_dino(track)
        if track == TRACK_PREMIUM and c["level"] == MAX_LEVEL:
            out["bonus_skin"] = _skin_view(APEX_BONUS_SKIN)
    return out


def _reward_view(c: dict, track: str, tier: str = TIER_FREE, slug: Optional[str] = None,
                 **_ignored) -> dict:
    """The reward object the claim celebration renders. One shape for both claim
    endpoints now -- with no halving there is nothing for the two consumers to
    disagree about."""
    out = {"level": c["level"], "type": c["type"]}
    if c["type"] in ("coins", "amber"):
        out["amount"] = c["amount"]
    elif c["type"] == "token":
        out["token"] = c["token"]
        out["tier"] = _token_flavor(track)
    elif c["type"] == "skin":
        out["skin"] = _skin_view(c["skin"], c.get("rarity"))
    elif c["type"] == "dino":
        out["slug"] = slug or fixed_dino(track, c["level"])
        out["band"] = pick_band(track, c["level"]) or "apex"
    return out


def _is_choice_cell(c: dict, track: str, tier: str = TIER_FREE) -> bool:
    return c["type"] == "dino" and not fixed_dino(track, c["level"])


def _validate_claimable(c: dict, track: str, level: int, tier: str, user_level: int) -> None:
    if c is None:
        _fail(400, "Ese nivel no existe en el Pase de Batalla.")
    # ★ ENTITLEMENT FIRST. Without a pass NOTHING is claimable on either row --
    # this is the exact hole the owner hit in testing.
    if not can_claim_track(tier, track):
        if tier == TIER_FREE:
            _fail(403, "Necesitas comprar un Pase para reclamar recompensas.")
        _fail(403, "Esta fila es solo del Pase Premium+.")
    if level > user_level:
        _fail(400, f"Todavía no llegas al nivel {level}.")
    if c["type"] == "empty":
        _fail(400, "Esa casilla no tiene recompensa.")


async def _pay_cell(user, c: dict, track: str, tier: str, season: str, choice) -> list:
    """Pay ONE cell. Raises _VaultFull when the vault refused a dino."""
    lv = c["level"]
    label = f"Pase de Batalla {season_code(season)} · Nivel {lv}"
    effects = []
    if c["type"] in ("coins", "amber"):
        effects.append(await _pay_currency(user, c["type"], c["amount"], label))
    elif c["type"] == "token":
        effects.append(await _grant_token(user, c["token"], _token_flavor(track), season))
    elif c["type"] == "skin":
        effects.append(await _grant_skin(user, c["skin"], season))
    elif c["type"] == "dino":
        slug = fixed_dino(track, lv) or str(choice or "").strip()
        effects.append(await _grant_dino(user, slug, track, tier, season, lv))
        if track == TRACK_PREMIUM and lv == MAX_LEVEL:
            effects.append(await _grant_skin(user, APEX_BONUS_SKIN, season))
    return effects


async def _claim_one(user, season: str, track: str, level: int, tier: str,
                     choice=None, *, source: str = "claim") -> list:
    """Reserve the cell atomically FIRST, pay after. A payout that refuses (a
    full vault) deletes the reservation so the cell stays claimable -- the
    player is never charged a claim for a reward they did not get."""
    c = cell_at(track, level)
    claim_doc = {
        "id": _new_id(), "user_id": user["id"], "season": season, "track": track,
        "level": int(level), "type": c["type"], "tier": tier, "choice": choice,
        "source": source, "created_at": _now_iso(),
    }
    try:
        await db.bp_claims.insert_one(dict(claim_doc))
    except DuplicateKeyError:
        _fail(400, "Ya reclamaste esta recompensa.")
    except Exception as e:
        logger.warning("[bp] claim reserve failed: %r", e)
        _fail(500, "No pudimos registrar el reclamo. Inténtalo de nuevo.")
    try:
        effects = await _pay_cell(user, c, track, tier, season, choice)
    except _VaultFull:
        await db.bp_claims.delete_one({"id": claim_doc["id"]})
        _fail(400, "Tu Bóveda está llena. Libera un espacio y vuelve a reclamar "
                   "— la recompensa sigue disponible.")
    except HTTPException:
        await db.bp_claims.delete_one({"id": claim_doc["id"]})
        raise
    except Exception:
        await db.bp_claims.delete_one({"id": claim_doc["id"]})
        logger.exception("[bp] payout crashed track=%s level=%s user=%s", track, level, user["id"])
        _fail(500, "No pudimos entregar la recompensa. No se consumió el reclamo; inténtalo de nuevo.")
    await db.bp_claims.update_one({"id": claim_doc["id"]}, {"$set": {"effects": effects}})
    try:
        await _add_log(user["id"], "bp_claim", f"{track}:{level}",
                       {"season": season, "tier": tier, "effects": effects, "source": source})
    except Exception as e:
        logger.warning("[bp] claim log failed (claim stands): %r", e)
    return effects


async def _claimed_levels(user_id: str, season: str) -> dict:
    """{track: set(levels)} — the internal shape the settle and claim-all loops
    use. Legacy "free"/"pass" rows written by v1 are folded onto the new keys so
    a mid-season rename can never hand a level out twice."""
    rows = await db.bp_claims.find({"user_id": user_id, "season": season},
                                   {"_id": 0, "track": 1, "level": 1}).to_list(400)
    out = {TRACK_REGULAR: set(), TRACK_PREMIUM: set()}
    for r in rows:
        t = normalize_track(r.get("track"))
        if t:
            out[t].add(int(r.get("level") or 0))
    return out


def _claimed_public(levels: dict) -> dict:
    """★ A FLAT map keyed "<track>:<level>" — RewardTrack tests
    `claimed["regular:12"]` per card. The v1 "free:"/"pass:" keys are emitted
    ALONGSIDE so a browser still holding the previous bundle keeps showing its
    ticks; deprecated, drop once that window has passed."""
    out = {}
    for track, lvs in (levels or {}).items():
        legacy = LEGACY_TRACK_NAME.get(track)
        for lv in lvs:
            out[f"{track}:{lv}"] = True
            if legacy:
                out[f"{legacy}:{lv}"] = True
    return out


def _claimable_levels(track: str, tier: str, level: int, done: set, *, choices: bool):
    """Every cell on `track` this tier may claim right now. `choices=False`
    excludes the dino picks, which is exactly what RECLAMAR TODAS grants."""
    if not can_claim_track(tier, track):
        return
    for c in get_track(track):
        lv = c["level"]
        if lv > level or lv in done or c["type"] == "empty":
            continue
        if not choices and _is_choice_cell(c, track):
            continue
        yield c


def _token_public(doc: dict) -> dict:
    """★ TokenPanel reads `t.tier` (and `t.inv_id || t.id`). The stored document
    keeps `token_tier` as its canonical column; both names travel on the wire so
    the panel and any older reader are each served without a second source of
    truth in the database."""
    d = {k: v for k, v in (doc or {}).items() if k != "_id"}
    d["inv_id"] = d.get("id")
    d["tier"] = d.get("token_tier") or "basic"
    return d


async def _resolve_user(needle: str) -> dict:
    """The admin forms take free text ("Steam ID, Discord o nombre"), not an
    internal id. Exact identifiers first; a name is only accepted when it
    matches ONE player, so a gift can never land on the wrong account."""
    q = str(needle or "").strip()
    if not q:
        _fail(400, "Escribe el Steam ID, el Discord o el nombre del jugador.")
    for field in ("id", "steam_id", "discord_id"):
        hit = await db.users.find_one({field: q}, {"_id": 0})
        if hit:
            return hit
    rx = {"$regex": f"^{re.escape(q)}$", "$options": "i"}
    exact = await db.users.find({"persona_name": rx}, {"_id": 0}).to_list(5)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        _fail(400, f"Hay varios jugadores llamados «{q}». Usa su Steam ID.")
    loose = await db.users.find({"persona_name": {"$regex": re.escape(q), "$options": "i"}},
                                {"_id": 0}).to_list(5)
    if len(loose) == 1:
        return loose[0]
    if len(loose) > 1:
        _fail(400, f"«{q}» coincide con varios jugadores. Usa su Steam ID.")
    _fail(404, f"No encontramos a «{q}».")


# ===========================================================================
# Season settle
# ===========================================================================
async def settle_user_season(user, pass_doc: dict) -> dict:
    """Idempotent. Auto-grants every unclaimed NON-CHOICE cell the player was
    entitled to, expires the unpicked dino cells (a choice nobody made cannot be
    made for them), drops the Discord roles and marks the pass settled."""
    season = pass_doc.get("season")
    if not season or pass_doc.get("settled"):
        return {"settled": True, "granted": 0, "expired": 0, "already": True}
    tier, _src = resolve_tier(user, pass_doc)
    level = level_from_xp(int(pass_doc.get("xp") or 0))
    claimed = await _claimed_levels(user["id"], season)
    granted, expired, failed = 0, 0, 0
    for track in TRACKS:
        done = claimed.get(track) or set()
        for c in _claimable_levels(track, tier, level, done, choices=True):
            lv = c["level"]
            if _is_choice_cell(c, track):
                expired += 1
                continue
            try:
                await _claim_one(user, season, track, lv, tier, None, source="settle")
                granted += 1
            except HTTPException as e:
                failed += 1
                logger.info("[bp] settle skip user=%s %s:%s -> %s", user["id"], track, lv, e.detail)
            except Exception as e:
                failed += 1
                logger.warning("[bp] settle cell crashed user=%s %s:%s: %r", user["id"], track, lv, e)
    await _remove_bp_roles(user)
    await db.bp_passes.update_one(
        {"user_id": user["id"], "season": season},
        {"$set": {"settled": True, "settled_at": _now_iso(),
                  "settle_granted": granted, "settle_expired": expired,
                  "settle_failed": failed}})
    logger.info("[bp] settled user=%s season=%s granted=%d expired=%d failed=%d",
                user["id"], season, granted, expired, failed)
    return {"settled": True, "granted": granted, "expired": expired, "failed": failed}


async def _maybe_settle_user(user) -> None:
    """Lazy settle on the player's own traffic: every pass of theirs whose season
    has ENDED and is not settled yet."""
    try:
        cur = current_season_id()
        rows = await db.bp_passes.find(
            {"user_id": user["id"], "settled": {"$ne": True}}, {"_id": 0}).to_list(24)
        for p in rows:
            if p.get("season") != cur and season_has_ended(p.get("season") or ""):
                await settle_user_season(user, p)
    except Exception as e:
        logger.warning("[bp] lazy settle failed for %s: %r", (user or {}).get("id"), e)


async def settle_ended_seasons(limit: int = 500) -> dict:
    """Server-side sweep so ABSENT players still get banked (lazy-settle law).
    Runs from periodic() at most once an hour and from the admin button."""
    cur = current_season_id()
    # ★ The current season is excluded IN THE QUERY, not after the read. Every
    # active player holds an unsettled current-season pass, so a plain
    # {"settled": {"$ne": True}} scan would fill the whole `limit` with rows that
    # are then skipped -- and the ended seasons that actually need settling would
    # never be reached once the server has more than `limit` active players.
    rows = await db.bp_passes.find({"settled": {"$ne": True}, "season": {"$ne": cur}},
                                   {"_id": 0}).to_list(limit)
    done, skipped = 0, 0
    for p in rows:
        season = p.get("season") or ""
        if season == cur or not season_has_ended(season):
            skipped += 1
            continue
        user = await db.users.find_one({"id": p.get("user_id")}, {"_id": 0})
        if not user:
            await db.bp_passes.update_one({"user_id": p.get("user_id"), "season": season},
                                          {"$set": {"settled": True, "settled_at": _now_iso(),
                                                    "settle_note": "user_missing"}})
            skipped += 1
            continue
        try:
            await settle_user_season(user, p)
            done += 1
        except Exception as e:
            logger.warning("[bp] settle sweep failed user=%s: %r", p.get("user_id"), e)
    if done:
        logger.info("[bp] settle sweep: settled=%d skipped=%d", done, skipped)
    return {"settled": done, "skipped": skipped, "scanned": len(rows)}


# ===========================================================================
# Discord roles -- mirrors server.py's Patreon role lane (direct REST via the
# bot token). Every failure is logged and swallowed: a Discord outage must never
# be the thing that refuses a paid pass.
# ===========================================================================
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
BP_ROLE_REGULAR = os.environ.get("BP_ROLE_REGULAR", "").strip()
BP_ROLE_PREMIUM = os.environ.get("BP_ROLE_PREMIUM", "").strip()
BP_ROLE_REGULAR_NAME = os.environ.get("BP_ROLE_REGULAR_NAME", "Battle Pass").strip()
BP_ROLE_PREMIUM_NAME = os.environ.get("BP_ROLE_PREMIUM_NAME", "Battle Pass Premium+").strip()
_BP_ROLE_ID_CACHE: dict = {}


async def _bp_role_id(tier: str) -> str:
    """Explicit id wins. Otherwise resolve the configured NAME against the guild
    once and cache it -- the owner's role list arrived cut off, so names are the
    only thing that can be configured up front (BACKEND_NOTES OWED item)."""
    explicit = BP_ROLE_PREMIUM if tier == TIER_PREMIUM else BP_ROLE_REGULAR
    if explicit:
        return explicit
    want = (BP_ROLE_PREMIUM_NAME if tier == TIER_PREMIUM else BP_ROLE_REGULAR_NAME).lower()
    if not (want and DISCORD_BOT_TOKEN and DISCORD_GUILD_ID):
        return ""
    if want in _BP_ROLE_ID_CACHE:
        return _BP_ROLE_ID_CACHE[want]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.get(f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/roles",
                             headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"})
        if r.status_code != 200:
            logger.warning("[bp] role lookup HTTP %s -- Battle Pass roles not applied", r.status_code)
            return ""
        for role in (r.json() or []):
            if str(role.get("name") or "").lower() == want:
                _BP_ROLE_ID_CACHE[want] = str(role.get("id"))
                return _BP_ROLE_ID_CACHE[want]
        logger.warning("[bp] no Discord role named %r in the guild -- set BP_ROLE_%s",
                       want, "PREMIUM" if tier == TIER_PREMIUM else "REGULAR")
    except Exception as e:
        logger.warning("[bp] role lookup failed: %r", e)
    return ""


async def _bp_role_call(method: str, discord_id: str, role_id: str) -> bool:
    if not (DISCORD_BOT_TOKEN and DISCORD_GUILD_ID and discord_id and role_id):
        return False
    try:
        import httpx
        url = (f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}"
               f"/members/{discord_id}/roles/{role_id}")
        headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                   "X-Audit-Log-Reason": "Pase de Batalla (laislanublar.net)"}
        for attempt in (1, 2):
            async with httpx.AsyncClient(timeout=10) as hc:
                r = await hc.request(method, url, headers=headers)
            if r.status_code in (200, 204):
                return True
            if r.status_code == 429 and attempt == 1:
                try:
                    wait = float((r.json() or {}).get("retry_after", 1.5))
                except Exception:
                    wait = 1.5
                await asyncio.sleep(min(max(wait, 0.5), 6.0))
                continue
            if r.status_code == 403:
                logger.warning("[bp] role %s %s: 403 -- the bot's role must sit ABOVE the "
                               "Battle Pass roles and hold Manage Roles", method, role_id)
            else:
                logger.warning("[bp] role %s %s: HTTP %s", method, role_id, r.status_code)
            break
    except Exception as e:
        logger.warning("[bp] role %s %s failed: %r", method, role_id, e)
    return False


async def _grant_bp_role(user, tier: str) -> None:
    try:
        did = str((user or {}).get("discord_id") or "")
        if not did or tier == TIER_FREE:
            return
        rid = await _bp_role_id(tier)
        if not rid:
            return
        if await _bp_role_call("PUT", did, rid):
            await db.users.update_one({"id": user["id"]}, {"$addToSet": {"bp_site_roles": rid}})
            logger.info("[bp] +role %s -> %s", rid, user.get("persona_name"))
    except Exception as e:
        logger.warning("[bp] grant role failed: %r", e)


async def _remove_bp_roles(user) -> None:
    try:
        fresh = await db.users.find_one({"id": (user or {}).get("id")}, {"_id": 0}) or user or {}
        did = str(fresh.get("discord_id") or "")
        held = [str(r) for r in (fresh.get("bp_site_roles") or []) if str(r)]
        if not (did and held):
            return
        for rid in held:
            await _bp_role_call("DELETE", did, rid)
        await db.users.update_one({"id": fresh["id"]}, {"$set": {"bp_site_roles": []}})
        logger.info("[bp] -roles %s -> %s", held, fresh.get("persona_name"))
    except Exception as e:
        logger.warning("[bp] remove roles failed: %r", e)


# ===========================================================================
# Tier grant / revoke
# ===========================================================================
async def grant_tier(user, season: str, tier: str, source: str, note: str = "") -> dict:
    """Idempotent upgrade-only grant. A grant for a season that already ENDED is
    refused and flagged for review instead of silently paying nothing."""
    if tier not in (TIER_REGULAR, TIER_PREMIUM):
        _fail(400, "Nivel de pase inválido.")
    if season != current_season_id():
        logger.warning("[bp] grant for a non-current season user=%s season=%s tier=%s",
                       user["id"], season, tier)
        return {"granted": False, "needs_review": True,
                "detail": "La temporada de esa compra ya terminó; un administrador la revisará."}
    await _get_pass(user["id"], season)
    doc = await db.bp_passes.find_one({"user_id": user["id"], "season": season}, {"_id": 0}) or {}
    cur = doc.get("tier") if doc.get("tier") in (TIER_REGULAR, TIER_PREMIUM) else TIER_FREE
    if TIER_RANK.get(cur, 0) >= TIER_RANK[tier]:
        return {"granted": False, "already": True, "tier": cur}
    await db.bp_passes.update_one(
        {"user_id": user["id"], "season": season},
        {"$set": {"tier": tier, "tier_source": source, "tier_granted_at": _now_iso(),
                  "tier_note": note or ""}})
    await _grant_bp_role(user, tier)
    try:
        await _add_log(user["id"], "bp_tier_grant", tier, {"season": season, "source": source, "note": note})
    except Exception:
        pass
    logger.info("[bp] tier granted user=%s season=%s tier=%s source=%s", user["id"], season, tier, source)
    return {"granted": True, "tier": tier, "source": source}


async def revoke_tier(user_id: str, season: str, reason: str) -> dict:
    """Refund / chargeback. The pass drops to free; ALREADY-CLAIMED rewards stay
    (taking a dino back out of a vault is not a thing we do), the event is
    logged, and the admin feed carries the line."""
    doc = await db.bp_passes.find_one({"user_id": user_id, "season": season}, {"_id": 0})
    if not doc:
        return {"revoked": False, "detail": "no_pass"}
    await db.bp_passes.update_one(
        {"user_id": user_id, "season": season},
        {"$set": {"tier": TIER_FREE, "tier_source": "revoked", "revoked_at": _now_iso(),
                  "revoked_reason": reason}})
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user:
        await _remove_bp_roles(user)
    try:
        await _add_log("stripe", "bp_tier_revoke", user_id, {"season": season, "reason": reason})
    except Exception:
        pass
    logger.warning("[bp] tier REVOKED user=%s season=%s reason=%s", user_id, season, reason)
    return {"revoked": True, "was": doc.get("tier")}


# ===========================================================================
# Stripe (optional at runtime -- never at import)
# ===========================================================================
STRIPE_PRODUCTS = [
    {"key": "bp_regular", "name": "Pase de Batalla · Regular",
     "description": "Desbloquea la fila del Pase por la temporada actual.",
     "lookup_key": "bp_regular_monthly", "amount": 500},
    {"key": "bp_premium_plus", "name": "Pase de Batalla · Premium+",
     "description": "Fila del Pase completa: dinos PRIME, fichas premium y skins legendarias.",
     "lookup_key": "bp_premium_plus_monthly", "amount": 1000},
    {"key": "bp_upgrade", "name": "Pase de Batalla · Mejora a Premium+",
     "description": "Sube tu Pase Regular a Premium+ durante la temporada actual.",
     "lookup_key": "bp_upgrade_monthly", "amount": 500},
]
STRIPE_CURRENCY = "usd"
# The owner's Stripe account runs Managed Payments, which REFUSES any checkout
# whose product has no tax_code. This is the owner's own prototype's code
# (general electronically supplied services); ensure_catalog also back-fills it
# onto products created before this constant existed.
STRIPE_TAX_CODE = "txcd_10000000"
_catalog_ready = False


class _StripeUnavailable(Exception):
    """Library missing or key unset -- the caller answers 503, never 500."""


def _stripe_lib():
    """Guarded import. Absent library or absent key = the pass still works, only
    the two checkout-shaped endpoints answer 503."""
    key = os.environ.get("STRIPE_SECRET_KEY") or ""
    if not key:
        return None
    try:
        import stripe  # noqa: PLC0415 - deliberately lazy
    except Exception:
        return None
    stripe.api_key = key
    return stripe


def stripe_available() -> bool:
    return _stripe_lib() is not None


def _plain(obj):
    """Stripe v15 objects are NOT dicts: no .get(), no keys(), dict(obj) fails.
    to_dict() (proven recursive on 15.4.0) flattens them; plain dicts pass
    through untouched so the fakes in the tests keep working."""
    if isinstance(obj, dict) or obj is None:
        return obj or {}
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    return {}


def ensure_catalog() -> dict:
    """Idempotent product/price setup (owner's stripe_catalog pattern), called
    LAZILY on the first checkout -- never at import, never at startup."""
    global _catalog_ready
    lib = _stripe_lib()
    if lib is None:
        raise _StripeUnavailable()
    if _catalog_ready:
        return {"ready": True, "cached": True}
    made = 0
    for entry in STRIPE_PRODUCTS:
        product = None
        for p in lib.Product.list(active=True, limit=100).auto_paging_iter():
            # stripe v15 objects have no .get(); _plain() flattens to real dicts.
            if (_plain(p).get("metadata") or {}).get("bp_product_key") == entry["key"]:
                product = p
                break
        if product is None:
            product = lib.Product.create(
                name=entry["name"], description=entry["description"],
                tax_code=STRIPE_TAX_CODE,
                metadata={"managed_by": "lin_bp", "bp_product_key": entry["key"]})
            made += 1
        elif (_plain(product).get("tax_code") or "") != STRIPE_TAX_CODE:
            # Heal products minted before the tax code was carried.
            lib.Product.modify(product.id, tax_code=STRIPE_TAX_CODE)
            made += 1
        existing = lib.Price.list(lookup_keys=[entry["lookup_key"]], active=True, limit=1).data
        if existing and (existing[0].unit_amount != entry["amount"]
                         or existing[0].currency != STRIPE_CURRENCY):
            lib.Price.modify(existing[0].id, active=False)
            existing = []
        if not existing:
            lib.Price.create(product=product.id, unit_amount=entry["amount"],
                             currency=STRIPE_CURRENCY, lookup_key=entry["lookup_key"],
                             transfer_lookup_key=True,
                             metadata={"managed_by": "lin_bp", "bp_product_key": entry["key"]})
            made += 1
    _catalog_ready = True
    logger.info("[bp] stripe catalog ready (%d objects created)", made)
    return {"ready": True, "created": made}


def _stripe_price_id(lookup_key: str) -> str:
    lib = _stripe_lib()
    if lib is None:
        raise _StripeUnavailable()
    data = lib.Price.list(lookup_keys=[lookup_key], active=True, limit=1).data
    if not data:
        raise RuntimeError(f"stripe price {lookup_key} missing")
    return data[0].id


def _stripe_create_session(price_id: str, metadata: dict, success_url: str, cancel_url: str) -> dict:
    lib = _stripe_lib()
    if lib is None:
        raise _StripeUnavailable()
    s = lib.checkout.Session.create(
        mode="payment", line_items=[{"price": price_id, "quantity": 1}],
        metadata=metadata, success_url=success_url, cancel_url=cancel_url)
    return {"id": s.id, "url": s.url}


def _stripe_retrieve_session(session_id: str) -> dict:
    """Server-side RE-FETCH. Defence in depth: even a perfectly signed event is
    not allowed to be the only word on whether money moved."""
    lib = _stripe_lib()
    if lib is None:
        raise _StripeUnavailable()
    s = lib.checkout.Session.retrieve(session_id)
    return _plain(s)


def _stripe_construct_event(raw: bytes, sig_header: str) -> dict:
    lib = _stripe_lib()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET") or ""
    if lib is None or not secret:
        raise _StripeUnavailable()
    ev = lib.Webhook.construct_event(raw, sig_header, secret)
    return _plain(ev)


def _checkout_plan(current_tier: str, want: str) -> dict:
    if want not in (TIER_REGULAR, TIER_PREMIUM):
        _fail(400, "Nivel de pase inválido.")
    if TIER_RANK.get(current_tier, 0) >= TIER_RANK[want]:
        _fail(400, "Ya tienes este Pase (o uno mejor) esta temporada.")
    if current_tier == TIER_REGULAR and want == TIER_PREMIUM:
        return {"lookup_key": "bp_upgrade_monthly", "amount": 500, "upgrade": True}
    if want == TIER_PREMIUM:
        return {"lookup_key": "bp_premium_plus_monthly", "amount": 1000, "upgrade": False}
    return {"lookup_key": "bp_regular_monthly", "amount": 500, "upgrade": False}


# ===========================================================================
# Tokens -- inventory, parked redeem, live redeem
# ===========================================================================
async def _claim_token(user, inv_id: str) -> tuple:
    """Atomic one-shot claim of an inventory token (deploy_dino's pattern).
    Returns (item, decremented) -- the caller MUST refund on any failure."""
    claimed = await db.inventory.find_one_and_update(
        {"id": inv_id, "user_id": user["id"], "category": "Tokens", "quantity": {"$gt": 1}},
        {"$inc": {"quantity": -1}})
    if claimed is not None:
        return claimed, True
    claimed = await db.inventory.find_one_and_delete(
        {"id": inv_id, "user_id": user["id"], "category": "Tokens"})
    if claimed is None:
        _fail(404, "Ficha no encontrada en tu inventario.")
    return claimed, False


async def _refund_token(inv_id: str, item: dict, decremented: bool) -> None:
    try:
        if decremented:
            await db.inventory.update_one({"id": inv_id}, {"$inc": {"quantity": 1}})
        else:
            await db.inventory.insert_one({k: v for k, v in (item or {}).items() if k != "_id"})
    except Exception:
        logger.exception("[bp] TOKEN REFUND FAILED inv=%s -- restore by hand", inv_id)


# ---- narrow, guarded write against the bot's sqlite --------------------------
# vault.py exposes NO public writer for growth / prime / diet (its own UPDATEs
# only ever touch redeem_pending_*, custom_name, recovery_id and the three
# mutation columns), and vault.py is drift-protected, so the write lives here.
# It copies vault.cas_update_mutations discipline exactly, line for line:
# _connect_rw's pragmas, BEGIN IMMEDIATE, ownership in the WHERE clause, the
# redeem_pending guard, and an optimistic CAS on the OLD values so a concurrent
# edit or an in-flight redeem can never be silently overwritten.
def _bp_connect():
    if not os.path.isfile(game_ipc.BOT_DB_PATH):
        raise HTTPException(503, "La bóveda no está disponible en este momento.")
    conn = sqlite3.connect(game_ipc.BOT_DB_PATH, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def bp_cas_update_row(dino_id: int, steam_id: str, expected: dict, new_values: dict) -> tuple:
    """Write growth / is_prime / is_elder / diet_a / diet_b / diet_c on ONE parked
    row. Returns (written, reason). reason "state_changed" means the row moved
    under us (or a redeem started) -- the caller refunds the token."""
    if not new_values:
        return False, "nothing_to_write"
    cols = [c for c in ("growth", "is_prime", "is_elder", "diet_a", "diet_b", "diet_c")
            if c in new_values]
    if not cols:
        return False, "nothing_to_write"
    guard_cols = [c for c in ("growth", "diet_a", "diet_b", "diet_c") if c in new_values]
    sql = ("UPDATE parked_dinos SET " + ", ".join(f"{c} = ?" for c in cols) +
           " WHERE id = ? AND steam_id = ? "
           "AND (redeem_pending_cmd_id IS NULL OR redeem_pending_cmd_id = '')")
    params = [float(new_values[c]) if c.startswith(("growth", "diet")) else int(new_values[c])
              for c in cols]
    params += [int(dino_id), str(steam_id)]
    for c in guard_cols:
        sql += f" AND IFNULL({c}, 0) = ?"
        params.append(float(expected.get(c) or 0))
    conn = _bp_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(sql, tuple(params))
        n = int(cur.rowcount or 0)
        conn.execute("COMMIT")
        return (True, "") if n == 1 else (False, "state_changed")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _routes_at_cap(row: dict) -> bool:
    """A BASIC growth token may only mint prime when the dino's own prime routes
    are ALREADY at cap -- i.e. the player really did the missions. NULL means
    "parked before the columns existed, never recorded": fail closed."""
    mig, pat = row.get("prime_route_mig"), row.get("prime_route_pat")
    if mig is None or pat is None:
        return False
    try:
        return int(mig) >= PRIME_ROUTE_MIG_MAX and int(pat) >= PRIME_ROUTE_PAT_MAX
    except (TypeError, ValueError):
        return False


def _plan_parked_effect(row: dict, token: str, flavor: str) -> tuple:
    """(new_values, effects) -- effects EMPTY means nothing would change, and the
    caller must refuse WITHOUT consuming the token."""
    new, effects = {}, []
    if token == "growth":
        cur = float(row.get("growth") or 0.0)
        if cur >= GROWTH_TOKEN_TARGET:
            return {}, []                      # never lowers growth
        new["growth"] = GROWTH_TOKEN_TARGET
        effects.append(f"Crecimiento subido a {int(GROWTH_TOKEN_TARGET * 100)}%")
        already_prime = bool(int(row.get("is_prime") or 0))
        if not already_prime:
            if flavor == "premium":
                new["is_prime"] = 1
                new["is_elder"] = 1
                effects.append("Marcado como PRIME")
            elif _routes_at_cap(row):
                new["is_prime"] = 1
                new["is_elder"] = 1
                effects.append("Marcado como PRIME (misiones completas)")
    elif token == "diet":
        # ★ Basic ADDS 150% (0.5 per nutrient) and STACKS across uses up to the
        # 300% cap -- two basic tokens take any dino to full diet (owner order
        # 2026-08-07: "the 150% diet token can be used twice to get to 300%").
        # Premium still fills to 300% in one press. Neither ever lowers: the
        # max(cur, ...) keeps even an out-of-range stored value untouched.
        raised = False
        total = 0.0
        for col in ("diet_a", "diet_b", "diet_c"):
            cur = float(row.get(col) or 0.0)
            if flavor == "premium":
                nxt = max(cur, DIET_PREMIUM_EACH)
            else:
                nxt = max(cur, min(DIET_PREMIUM_EACH, cur + DIET_BASIC_EACH))
            new[col] = nxt
            total += nxt
            if nxt > cur:
                raised = True
        if not raised:
            return {}, []
        if flavor == "premium":
            effects.append("Dieta restaurada al 300%")
        else:
            effects.append(f"Dieta subida al {int(round(total * 100))}%")
    return new, effects


async def _redeem_parked(user, item: dict, dino_id: int) -> dict:
    sid = _steam_id(user)
    token = str(item.get("token") or "")
    flavor = str(item.get("token_tier") or "basic")
    # Belt to the endpoint gate: EVERY pass token is live-only (owner orders
    # 2026-08-07). HTTPException here refunds the already-claimed token in the
    # caller. `token`/`flavor` stay read above for the log line on any future
    # caller that reaches this.
    _fail(400, "Las fichas del Pase se usan en tu dinosaurio EN VIVO, dentro del juego.")
    row = await asyncio.to_thread(vault.get_parked_by_id, int(dino_id))
    if not row or str(row.get("steam_id")) != sid:
        _fail(404, "Ese dinosaurio no está en tu Bóveda.")
    row = await asyncio.to_thread(vault.resolve_stale_redeem_pending, row)
    if not row:
        _fail(404, "Ese dinosaurio ya no está en tu Bóveda (su recuperación terminó).")
    if str(row.get("redeem_pending_cmd_id") or "").strip():
        _fail(409, "Ese dinosaurio tiene una recuperación en progreso; inténtalo en un minuto.")
    new_values, effects = _plan_parked_effect(row, token, flavor)
    if not effects:
        if token == "growth":
            _fail(400, f"Ese dinosaurio ya tiene {int(GROWTH_TOKEN_TARGET * 100)}% o más de "
                       "crecimiento. No usamos tu ficha.")
        _fail(400, "Ese dinosaurio ya tiene la dieta al máximo (300%). No usamos tu ficha.")
    written, reason = await asyncio.to_thread(bp_cas_update_row, int(dino_id), sid, row, new_values)
    if not written:
        raise _CasLost(reason)
    logger.info("[bp] token applied parked sid=%s row=%s token=%s tier=%s -> %s",
                sid, dino_id, token, flavor, effects)
    return {"target": "parked", "dino_id": int(dino_id), "effects": effects}


class _CasLost(Exception):
    def __init__(self, reason=""):
        super().__init__(reason)
        self.reason = reason


# ---- live lane (the lua half ships separately; this is the sender + gate) ----
def live_tokens_enabled() -> bool:
    """The mod must ADVERTISE bp_tokens before the live lane is offered. Mirrors
    the bot's despawn_available() precedent (a capability FILE, checked for the
    flag rather than for mere existence) against the lua's restore-caps file.
    False until the mod restarts with the Battle Pass wave; the parked lane is
    unaffected either way."""
    try:
        if not game_ipc.mod_alive():
            return False
        for name in ("laislanublar_restore_caps.json", "bp_capabilities.json"):
            path = os.path.join(game_ipc.SAVED_DIR, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if isinstance(data, dict) and bool(data.get(BP_CAPABILITY_KEY)):
                return True
        return False
    except Exception as e:
        logger.warning("[bp] capability probe failed (live lane stays off): %r", e)
        return False


async def _send_live_cmd(sid: str, ctype: str, flavor: str, timeout_s: float):
    """Write ONE game command and wait for its ack. Returns (status, reason):
    "ok" / "refused" / "timeout" / "unsent". One shot, its own cmd_id."""
    cmd_id = uuid.uuid4().hex
    cmd = {"type": ctype, "steamid": sid, "cmd_id": cmd_id, "tier": flavor,
           "issued_at_ms": int(time.time() * 1000)}
    sent = await asyncio.to_thread(game_ipc.write_game_command, cmd)
    if not sent:
        return "unsent", "", cmd_id
    ok_event, fail_event = f"{ctype}_ok", f"{ctype}_failed"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for ev in (ok_event, fail_event):
            hit = await asyncio.to_thread(game_ipc.read_restore_status, sid, None, ev, None, cmd_id)
            if hit:
                if ev == ok_event:
                    return "ok", "", cmd_id
                return "refused", str(hit.get("reason") or ""), cmd_id
        await asyncio.sleep(LIVE_ACK_POLL_S)
    return "timeout", "", cmd_id


async def _redeem_live(user, item: dict) -> dict:
    sid = _steam_id(user)
    token = str(item.get("token") or "")
    flavor = str(item.get("token_tier") or "basic")
    if not live_tokens_enabled():
        _fail(503, "El juego no está aceptando fichas en este momento. "
                   "Inténtalo de nuevo en unos minutos — tu ficha no se gastó.")
    ctype = "bp_diet" if token == "diet" else "bp_grow"
    status, reason, cmd_id = await _send_live_cmd(sid, ctype, flavor, LIVE_ACK_TIMEOUT_S)
    if status == "unsent":
        _fail(503, "El servidor de juego no está respondiendo ahora mismo. Inténtalo en un momento.")
    if status == "refused":
        logger.info("[bp] live token refused sid=%s cmd=%s reason=%s", sid, cmd_id, reason)
        raise _LiveFailed("El juego no pudo aplicar la ficha en tu dinosaurio vivo.")
    if status == "timeout":
        raise _LiveFailed("El juego no confirmó a tiempo. Te devolvimos la ficha; vuelve a intentarlo.")
    logger.info("[bp] live token ok sid=%s cmd=%s type=%s", sid, cmd_id, ctype)
    effects = [_live_effect_text(token, flavor)]
    if token == "growth":
        # ★ Owner order 2026-08-07: a growth token must ALSO leave the dino at
        # 100% food. Rider = one full-fill diet command through the SAME armed
        # lane; the token is already spent on the growth, so a rider hiccup
        # never refunds — it reports honestly instead.
        fstatus, freason, fid = await _send_live_cmd(sid, "bp_diet", "premium",
                                                     LIVE_FOOD_RIDER_TIMEOUT_S)
        if fstatus == "ok" or (fstatus == "refused" and freason == "already_full"):
            effects.append("Comida al 100%")
        else:
            logger.warning("[bp] growth food rider did not land sid=%s cmd=%s status=%s reason=%s",
                           sid, fid, fstatus, freason)
            effects.append("La comida no se pudo rellenar esta vez")
    return {"target": "live", "cmd_id": cmd_id, "effects": effects}


def _live_effect_text(token: str, flavor: str) -> str:
    if token == "growth":
        base = f"Crecimiento subido a {int(GROWTH_TOKEN_TARGET * 100)}%"
        return base + (" + PRIME" if flavor == "premium" else "")
    if flavor == "premium":
        return "Dieta restaurada al 300%"
    return "Dieta +150% (se acumula hasta el 300%)"


class _LiveFailed(Exception):
    pass


# ===========================================================================
# Auth shims -- the REAL host dependencies, called through the injection seam.
# ===========================================================================
async def _require_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_security)):
    if _current_user_dep is None:
        raise HTTPException(503, "El Pase de Batalla no está disponible ahora mismo.")
    return await _current_user_dep(creds)


async def _require_admin(user=Depends(_require_user)):
    if _admin_user_dep is None:
        raise HTTPException(503, "El Pase de Batalla no está disponible ahora mismo.")
    return await _admin_user_dep(user)


# ===========================================================================
# Request models
# ===========================================================================
class ClaimIn(BaseModel):
    track: str = Field(min_length=1, max_length=8)
    level: int
    choice: Optional[str] = None


class CheckoutIn(BaseModel):
    tier: str = Field(min_length=1, max_length=24)


class TokenRedeemIn(BaseModel):
    inv_id: str = Field(min_length=1, max_length=64)
    target: str = Field(default="parked", max_length=16)
    # The redeem modal sends `vault_id`; `dino_id` stays accepted as an alias.
    vault_id: Optional[int] = None
    dino_id: Optional[int] = None

    @property
    def row_id(self) -> Optional[int]:
        return self.vault_id if self.vault_id is not None else self.dino_id


class AdminGiftIn(BaseModel):
    # The admin form sends free text under `user` ("Steam ID, Discord o
    # nombre"); `user_id` stays accepted for a direct internal id.
    user: Optional[str] = Field(default=None, max_length=120)
    user_id: Optional[str] = Field(default=None, max_length=120)
    tier: str = Field(min_length=1, max_length=24)
    note: Optional[str] = Field(default="", max_length=200)

    @property
    def needle(self) -> str:
        return (self.user or self.user_id or "").strip()


class AdminGrantXpIn(BaseModel):
    user: Optional[str] = Field(default=None, max_length=120)
    user_id: Optional[str] = Field(default=None, max_length=120)
    amount: int

    @property
    def needle(self) -> str:
        return (self.user or self.user_id or "").strip()


class AdminSettleIn(BaseModel):
    season: Optional[str] = None


class AdminSeasonNameIn(BaseModel):
    # An EMPTY name is the documented way to go back to the built-in name, so it
    # is accepted, never refused. max_length is generous on the wire; the value
    # is sanitized and capped server-side either way.
    season: Optional[str] = Field(default=None, max_length=16)
    name: Optional[str] = Field(default="", max_length=400)
    verbatim: bool = False


# ===========================================================================
# Routes. EVERY one is fully contained: an unexpected failure becomes an honest
# Spanish detail plus a "[bp]" log line, never a bare 500 and never a silence.
# ===========================================================================
def _contained(name: str):
    """Decorator: HTTPExceptions pass through (they are our own honest answers);
    anything else is logged with its repr and answered in Spanish."""
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*a, **kw):
            try:
                return await fn(*a, **kw)
            except HTTPException:
                raise
            except Exception as e:
                logger.exception("[bp] %s crashed: %r", name, e)
                raise HTTPException(status_code=500,
                                    detail="El Pase de Batalla tuvo un problema. Inténtalo de nuevo.")
        return wrapper
    return deco


async def _status_payload(user) -> dict:
    """The one payload the pass page consumes. Field names here are the page's,
    not this module's: free_track / pass_track (flat, not nested), level as an
    int beside xp as the PROGRESS object, claimed as a flat "track:level" map,
    dino_bands, claimable_count."""
    season = current_season_id()
    await _maybe_settle_user(user)
    doc = await _get_pass(user["id"], season)
    # Self-heal a mid-season skin swap before the page renders, so a player who
    # claimed the cell under the old layout sees the new skin the first time
    # they look. No-op (one dict read) once their signature matches.
    await _reconcile_claimed_skins(user, season, doc)
    tier, source = resolve_tier(user, doc)
    xp = int(doc.get("xp") or 0)
    prog = level_progress(xp)
    level = prog["level"]
    claimed = await _claimed_levels(user["id"], season)
    start, end = season_bounds(season)
    tokens = await db.inventory.find(
        {"user_id": user["id"], "category": "Tokens"}, {"_id": 0}).to_list(200)
    # What RECLAMAR TODAS would actually grant: the non-choice cells. Counting
    # the dino picks here would light up a button that then claims nothing.
    claimable = sum(len(list(_claimable_levels(t, tier, level, claimed.get(t) or set(),
                                               choices=False))) for t in TRACKS)
    regular_cells = [_cell_public(c, TRACK_REGULAR) for c in REGULAR_TRACK]
    premium_cells = [_cell_public(c, TRACK_PREMIUM) for c in PREMIUM_TRACK]
    return {
        "season": {"id": season, "name": await season_name(season),
                   "starts_at": start.isoformat(), "ends_at": end.isoformat(),
                   "seconds_left": max(0, int((end - datetime.now(timezone.utc)).total_seconds()))},
        "tier": tier, "tier_source": source, "tier_label": TIER_LABEL[tier],
        "settled": bool(doc.get("settled")),
        "level": level,
        "xp": prog,
        "progress": prog,          # extra: the same object under this module's own name
        "regular_track": regular_cells,
        "premium_track": premium_cells,
        # DEPRECATED v1 names, same arrays. They exist ONLY so a browser holding
        # the previous bundle keeps rendering during the rollout; remove them
        # once that window has passed.
        "free_track": regular_cells,
        "pass_track": premium_cells,
        "claimed": _claimed_public(claimed),
        "claimable_count": claimable,
        "claimable_tracks": list(TIER_TRACKS.get(tier, ())),
        "dino_bands": dino_bands_view(),
        "tokens": [_token_public(t) for t in tokens],
        "live_tokens_enabled": live_tokens_enabled(),
        "payments_enabled": stripe_available(),
        "prices": {TIER_REGULAR: 5.0, TIER_PREMIUM: 10.0, "upgrade": 5.0},
        "rules": {
            "growth_token_pct": int(GROWTH_TOKEN_TARGET * 100),
            "diet_premium_pct": int(DIET_PREMIUM_EACH * 300),
            "diet_basic_pct": int(DIET_BASIC_EACH * 300),
            "dino_growth_pct": int(DINO_GROWTH * 100),
            # mutations_premium is the BUYER total across both rows (the owner's
            # number); the per-row totals derive from the 3-non-prime /
            # 4-prime per-dino rule (owner order 2026-08-08).
            "mutations_premium": len(DINO_LEVELS) * (MUTATIONS_NON_PRIME + MUTATIONS_PRIME),
            "mutations_regular": len(DINO_LEVELS) * MUTATIONS_NON_PRIME,
            "mutations_per_dino": {t: mutations_per_dino(t) for t in TRACKS},
            "rows": list(TRACKS),
        },
    }


@router.get("/status")
@_contained("status")
async def bp_status(user=Depends(_require_user)):
    return await _status_payload(user)


@router.post("/claim")
@_contained("claim")
async def bp_claim(data: ClaimIn, user=Depends(_require_user)):
    track = normalize_track(data.track)   # accepts the v1 "free"/"pass" names too
    if track is None:
        _fail(400, "Fila inválida.")
    season = current_season_id()
    await _maybe_settle_user(user)
    doc = await _get_pass(user["id"], season)
    if doc.get("settled"):
        _fail(400, "Esa temporada ya cerró.")
    tier, _src = resolve_tier(user, doc)
    level = int(data.level or 0)
    c = cell_at(track, level)
    _validate_claimable(c, track, level, tier, level_from_xp(int(doc.get("xp") or 0)))
    choice = None
    if c["type"] == "dino":
        fixed = fixed_dino(track, level)
        if fixed is None:
            choice = str(data.choice or "").strip()
            allowed = band_choices(track, level, tier)
            if choice not in allowed:
                _fail(400, "Elige una especie disponible en este nivel.")
    effects = await _claim_one(user, season, track, level, tier, choice)
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or {}
    return {"ok": True, "success": True, "track": track, "level": level,
            # `reward` carries the GRANTED amount: the celebration prints it raw.
            "reward": _reward_view(c, track, tier, choice),
            "coins": int(fresh.get("coins") or 0), "vip_coins": int(fresh.get("vip_coins") or 0),
            "effects": effects}


@router.post("/claim-all")
@_contained("claim-all")
async def bp_claim_all(user=Depends(_require_user)):
    """Every claimable NON-CHOICE cell in one press. Dino cells stay behind for a
    manual pick, and one refusal never stops the rest."""
    season = current_season_id()
    await _maybe_settle_user(user)
    doc = await _get_pass(user["id"], season)
    if doc.get("settled"):
        _fail(400, "Esa temporada ya cerró.")
    tier, _src = resolve_tier(user, doc)
    level = level_from_xp(int(doc.get("xp") or 0))
    claimed = await _claimed_levels(user["id"], season)
    all_effects, rows, skipped = [], [], []
    for track in TRACKS:
        done = claimed.get(track) or set()
        for c in list(_claimable_levels(track, tier, level, done, choices=False)):
            lv = c["level"]
            try:
                all_effects.extend(await _claim_one(user, season, track, lv, tier, None, source="claim_all"))
                rows.append({"track": track, "level": lv,
                             "reward": _reward_view(c, track, tier)})
            except HTTPException as e:
                skipped.append({"track": track, "level": lv, "detail": e.detail})
            except Exception as e:
                logger.warning("[bp] claim-all cell failed %s:%s: %r", track, lv, e)
                skipped.append({"track": track, "level": lv, "detail": "No se pudo entregar."})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or {}
    return {"ok": True, "success": True,
            "claimed": rows, "claimed_count": len(rows),
            "coins": int(fresh.get("coins") or 0), "vip_coins": int(fresh.get("vip_coins") or 0),
            "effects": all_effects, "skipped": skipped}


@router.post("/checkout")
@_contained("checkout")
async def bp_checkout(data: CheckoutIn, user=Depends(_require_user)):
    season = current_season_id()
    doc = await _get_pass(user["id"], season)
    cur_tier, _src = resolve_tier(user, doc)
    plan = _checkout_plan(cur_tier, str(data.tier or "").strip())
    try:
        ensure_catalog()
        price_id = await asyncio.to_thread(_stripe_price_id, plan["lookup_key"])
        session = await asyncio.to_thread(
            _stripe_create_session, price_id,
            {"user_id": user["id"], "season": season, "tier": str(data.tier).strip(),
             "upgrade": "1" if plan["upgrade"] else "0"},
            # ★ The pass lives on its own page since 2026-08-07 (owner order);
            # /profile?tab=battlepass still forwards for sessions minted before.
            f"{PUBLIC_SITE_URL}/battle-pass?bp_session={{CHECKOUT_SESSION_ID}}",
            f"{PUBLIC_SITE_URL}/battle-pass")
    except _StripeUnavailable:
        _fail(503, PAY_UNAVAILABLE)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[bp] checkout failed: %r", e)
        _fail(502, "No pudimos abrir el pago. Inténtalo de nuevo en un momento.")
    await db.bp_payments.update_one(
        {"session_id": session["id"]},
        {"$setOnInsert": {"id": _new_id(), "session_id": session["id"], "user_id": user["id"],
                          "season": season, "tier": str(data.tier).strip(),
                          "upgrade": plan["upgrade"], "amount": plan["amount"],
                          "status": "pending", "bp_applied": False, "created_at": _now_iso()}},
        upsert=True)
    logger.info("[bp] checkout session=%s user=%s tier=%s upgrade=%s",
                session["id"], user["id"], data.tier, plan["upgrade"])
    # `checkout_url` is the name the purchase modal redirects on; `url` stays as
    # an alias.
    return {"ok": True, "session_id": session["id"], "checkout_url": session["url"],
            "url": session["url"], "upgrade": plan["upgrade"], "amount": plan["amount"]}


@router.get("/payment/{session_id}")
@_contained("payment-status")
async def bp_payment_status(session_id: str, user=Depends(_require_user)):
    row = await db.bp_payments.find_one({"session_id": session_id}, {"_id": 0})
    if not row or row.get("user_id") != user["id"]:
        _fail(404, "Pago no encontrado.")
    status = row.get("status")
    # `payment_status` is the field the return-page poll reads; it stops on
    # "paid" and on "expired" and keeps polling on anything else.
    return {"ok": True, "session_id": session_id, "payment_status": status, "status": status,
            "bp_tier": row.get("tier"), "tier": row.get("tier"),
            "bp_applied": bool(row.get("bp_applied")), "applied": bool(row.get("bp_applied")),
            "season": row.get("season"), "needs_review": bool(row.get("needs_review"))}


@router.post("/stripe-webhook")
@_contained("stripe-webhook")
async def bp_stripe_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("stripe-signature") or ""
    if not sig:
        # An unsigned POST is forgery, full stop -- checked BEFORE anything else
        # so it is refused even on a box with no Stripe key at all.
        logger.warning("[bp] webhook without a signature refused")
        _fail(400, "Firma de Stripe ausente.")
    try:
        event = _stripe_construct_event(raw, sig)
    except _StripeUnavailable:
        _fail(503, PAY_UNAVAILABLE)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("[bp] webhook signature rejected: %r", e)
        _fail(400, "Firma de Stripe inválida.")
    event_id = str(event.get("id") or "")
    etype = str(event.get("type") or "")
    if not event_id:
        _fail(400, "Evento de Stripe inválido.")
    try:
        await db.bp_stripe_events.insert_one(
            {"id": _new_id(), "event_id": event_id, "type": etype, "received_at": _now_iso()})
    except DuplicateKeyError:
        logger.info("[bp] webhook replay ignored event=%s", event_id)
        return {"received": True, "duplicate": True}
    obj = ((event.get("data") or {}).get("object")) or {}
    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        # Async methods (OXXO/SPEI style): completed fires unpaid, the money
        # lands later as async_payment_succeeded -- same grant path, and the
        # paid re-fetch inside stays the authority either way.
        return await _webhook_completed(obj, event_id)
    if etype == "checkout.session.async_payment_failed":
        sid = str(obj.get("id") or "")
        if sid:
            await db.bp_payments.update_one(
                {"session_id": sid, "bp_applied": {"$ne": True}},
                {"$set": {"status": "async_failed", "failed_at": _now_iso()}})
        return {"received": True, "async_failed": sid}
    if etype == "checkout.session.expired":
        # Sessions expire ~24h after creation (long after the return page's own
        # short poll gave up) -- this keeps the payment ROW and the admin feed
        # honest about abandoned checkouts; it does not shorten any poll.
        sid = str(obj.get("id") or "")
        if sid:
            await db.bp_payments.update_one(
                {"session_id": sid, "bp_applied": {"$ne": True}},
                {"$set": {"status": "expired", "expired_at": _now_iso()}})
        return {"received": True, "expired": sid}
    if etype in ("charge.refunded", "charge.dispute.created"):
        return await _webhook_revoke(obj, etype)
    return {"received": True, "ignored": etype}


async def _webhook_completed(obj: dict, event_id: str) -> dict:
    session_id = str(obj.get("id") or "")
    if not session_id:
        return {"received": True, "ignored": "no_session"}
    # DEFENCE IN DEPTH: the event said "completed"; Stripe itself is asked
    # whether the money actually landed.
    try:
        fresh = await asyncio.to_thread(_stripe_retrieve_session, session_id)
    except _StripeUnavailable:
        _fail(503, PAY_UNAVAILABLE)
    except Exception as e:
        logger.warning("[bp] session re-fetch failed %s: %r", session_id, e)
        _fail(502, "No pudimos verificar el pago con Stripe.")
    if str(fresh.get("payment_status") or "") != "paid":
        # Async methods (OXXO/SPEI style) legitimately complete "unpaid" and pay
        # later via checkout.session.async_payment_succeeded -- that event lands
        # in this same handler with a new event id and grants then.
        logger.warning("[bp] session %s not paid (%s) -- grant refused",
                       session_id, fresh.get("payment_status"))
        await db.bp_payments.update_one({"session_id": session_id},
                                        {"$set": {"status": "unpaid"}})
        return {"received": True, "granted": False, "reason": "not_paid"}
    meta = dict(fresh.get("metadata") or obj.get("metadata") or {})
    user_id = str(meta.get("user_id") or "")
    season = str(meta.get("season") or "")
    tier = str(meta.get("tier") or "")
    # The refund/dispute webhook carries a CHARGE that names only the
    # payment_intent -- persist it here or a revoke can never find this row.
    payment_intent = str(fresh.get("payment_intent") or obj.get("payment_intent") or "")
    claimed = await db.bp_payments.find_one_and_update(
        {"session_id": session_id, "bp_applied": {"$ne": True}},
        {"$set": {"bp_applied": True, "status": "paid", "applied_at": _now_iso(),
                  "event_id": event_id, "payment_intent": payment_intent}},
        return_document=ReturnDocument.AFTER, upsert=False)
    if claimed is None:
        existing = await db.bp_payments.find_one({"session_id": session_id}, {"_id": 0})
        if existing is None:
            # A session this box never created (or a lost row): record it, then grant.
            await db.bp_payments.insert_one(
                {"id": _new_id(), "session_id": session_id, "user_id": user_id, "season": season,
                 "tier": tier, "status": "paid", "bp_applied": True, "event_id": event_id,
                 "payment_intent": payment_intent,
                 "created_at": _now_iso(), "recovered": True})
        else:
            logger.info("[bp] session %s already applied", session_id)
            return {"received": True, "duplicate_session": True}
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        logger.warning("[bp] paid session %s has no user %s", session_id, user_id)
        await db.bp_payments.update_one({"session_id": session_id},
                                        {"$set": {"needs_review": True, "review": "user_missing"}})
        return {"received": True, "granted": False, "reason": "user_missing"}
    res = await grant_tier(user, season, tier, "stripe", note=session_id)
    if not res.get("granted"):
        # MONEY MOVED but no tier landed (already at that tier from a stale
        # second tab, or the season rolled over mid-checkout). Flag it so the
        # admin feed shows a refund candidate instead of swallowing it.
        await db.bp_payments.update_one(
            {"session_id": session_id},
            {"$set": {"needs_review": True,
                      "review": "season_ended" if res.get("needs_review") else "paid_but_not_granted"}})
    return {"received": True, "granted": bool(res.get("granted")), **res}


async def _webhook_revoke(obj: dict, etype: str) -> dict:
    """Refund / chargeback. Stripe sends a CHARGE here, not a session, so the
    payment row is found by its payment_intent (recorded on the paid session)."""
    pi = str(obj.get("payment_intent") or obj.get("id") or "")
    row = None
    if pi:
        row = await db.bp_payments.find_one({"$or": [{"payment_intent": pi}, {"session_id": pi}]},
                                            {"_id": 0})
    if row is None:
        logger.warning("[bp] %s could not be matched to a Battle Pass payment (pi=%s)", etype, pi)
        return {"received": True, "revoked": False, "reason": "no_match"}
    await db.bp_payments.update_one({"session_id": row["session_id"]},
                                    {"$set": {"status": "refunded", "refunded_at": _now_iso(),
                                              "refund_event": etype}})
    res = await revoke_tier(row.get("user_id"), row.get("season"), etype)
    return {"received": True, **res}


@router.get("/tokens")
@_contained("tokens")
async def bp_tokens(user=Depends(_require_user)):
    items = await db.inventory.find({"user_id": user["id"], "category": "Tokens"},
                                    {"_id": 0}).sort("acquired_at", 1).to_list(200)
    return {"ok": True, "tokens": [_token_public(t) for t in items],
            "live_enabled": live_tokens_enabled(),
            "growth_pct": int(GROWTH_TOKEN_TARGET * 100)}


@router.get("/vault-targets")
@_contained("vault-targets")
async def bp_vault_targets(user=Depends(_require_user)):
    """The parked rows a token may be spent on, with what the token would change."""
    sid = _steam_id(user)
    rows = await asyncio.to_thread(vault.get_parked, sid)
    out = []
    for r in rows or []:
        cls = str(r.get("dino_class") or "")
        slug = _SLUG_BY_CLASS.get(cls)
        # ★ `species` is the SLUG: the redeem list renders /dinos/<species>.png.
        # The readable name travels as `name`; `prime`/`deployed` are the flags
        # the row's caption and its disabled state are keyed on.
        pending = bool(str(r.get("redeem_pending_cmd_id") or "").strip())
        out.append({
            "id": int(r.get("id")),
            "dino_id": int(r.get("id")),
            "species": slug or cls,
            "slug": slug,
            "class": cls,
            "name": (_DINO_BY_SLUG.get(slug or "") or {}).get("name")
                    or _SPECIES_BY_SLUG.get(slug or "") or cls,
            "growth": float(r.get("growth") or 0.0),
            "growth_pct": round(float(r.get("growth") or 0.0) * 100.0, 1),
            "prime": bool(int(r.get("is_prime") or 0)),
            "is_prime": bool(int(r.get("is_prime") or 0)),
            "diet": {"a": float(r.get("diet_a") or 0.0), "b": float(r.get("diet_b") or 0.0),
                     "c": float(r.get("diet_c") or 0.0)},
            "routes_at_cap": _routes_at_cap(r),
            # A row mid-redeem is on its way into the server, and it is exactly
            # the row a token redeem refuses -- so the list greys it out with
            # "Está en el servidor — guárdalo primero" instead of letting the
            # player pick it and collect a 409.
            "deployed": pending,
            "redeem_pending": pending,
        })
    return {"ok": True, "targets": out}


@router.post("/token/redeem")
@_contained("token-redeem")
async def bp_token_redeem(data: TokenRedeemIn, user=Depends(_require_user)):
    target = str(data.target or "parked").strip()
    if target not in ("parked", "live"):
        _fail(400, "Destino inválido.")
    if target == "live" and not live_tokens_enabled():
        # Neutral copy: growth may fall back to the vault, diet may NOT (live-only),
        # so this message cannot recommend the Bóveda.
        _fail(503, "El juego no está aceptando fichas en este momento. "
                   "Inténtalo de nuevo en unos minutos — tu ficha no se gastó.")
    row_id = data.row_id
    # ★ ALL pass tokens are LIVE-ONLY (owner orders 2026-08-07: diet first,
    # then "same with this" for growth). A stored dino refills food on redeem
    # and its growth belongs to the redeem/park machinery, so the vault target
    # is refused outright — BEFORE anything is consumed.
    if target == "parked":
        _fail(400, "Las fichas del Pase se usan en tu dinosaurio EN VIVO, dentro del juego. "
                   "Entra al juego y úsala ahí — no se gastó tu ficha.")
    # Read the item WITHOUT consuming, so a doomed redeem never eats a token.
    peek = await db.inventory.find_one({"id": data.inv_id, "user_id": user["id"],
                                        "category": "Tokens"}, {"_id": 0})
    if not peek:
        _fail(404, "Ficha no encontrada en tu inventario.")
    if str(peek.get("token") or "") not in ("diet", "growth"):
        _fail(400, "Esa ficha no es del Pase de Batalla.")
    item, decremented = await _claim_token(user, data.inv_id)
    try:
        res = await _redeem_live(user, item)
    except _CasLost:
        await _refund_token(data.inv_id, item, decremented)
        _fail(409, "El dinosaurio cambió mientras aplicábamos la ficha. Te la devolvimos; "
                   "vuelve a intentarlo.")
    except _LiveFailed as e:
        await _refund_token(data.inv_id, item, decremented)
        _fail(409, str(e))
    except HTTPException:
        await _refund_token(data.inv_id, item, decremented)
        raise
    except Exception as e:
        await _refund_token(data.inv_id, item, decremented)
        logger.exception("[bp] token redeem crashed inv=%s: %r", data.inv_id, e)
        _fail(500, "No pudimos aplicar la ficha. Te la devolvimos; inténtalo de nuevo.")
    try:
        await _add_log(user["id"], "bp_token_redeem", data.inv_id,
                       {"token": item.get("token"), "tier": item.get("token_tier"), **res})
    except Exception:
        pass
    return {"ok": True, "success": True, **res}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@router.get("/admin/overview")
@_contained("admin-overview")
async def bp_admin_overview(season: Optional[str] = None, admin=Depends(_require_admin)):
    season = season or current_season_id()
    passes = await db.bp_passes.find({"season": season}, {"_id": 0}).to_list(2000)
    payments = await db.bp_payments.find({"season": season}, {"_id": 0}).sort("created_at", -1).to_list(500)
    claims_count = await db.bp_claims.count_documents({"season": season})
    start, end = season_bounds(season)

    by_tier = {TIER_FREE: 0, TIER_REGULAR: 0, TIER_PREMIUM: 0}
    for p in passes:
        by_tier[p.get("tier") if p.get("tier") in by_tier else TIER_FREE] += 1
    buyers = {TIER_REGULAR: by_tier[TIER_REGULAR], TIER_PREMIUM: by_tier[TIER_PREMIUM],
              "gift": sum(1 for p in passes if p.get("tier_source") == "gift")}

    # One purchases feed, in the order the table renders: paid/pending Stripe
    # sessions AND staff gifts, which never create a payment row.
    names = {}
    ids = {p.get("user_id") for p in payments} | {p.get("user_id") for p in passes
                                                  if p.get("tier_source") == "gift"}
    ids.discard(None)
    if ids:
        for u in await db.users.find({"id": {"$in": list(ids)}},
                                     {"_id": 0, "id": 1, "persona_name": 1, "steam_id": 1}).to_list(len(ids)):
            names[u["id"]] = u.get("persona_name") or u.get("steam_id") or u["id"]
    rows = [{"at": p.get("created_at"), "user_id": p.get("user_id"),
             "user_name": names.get(p.get("user_id")) or p.get("user_id"),
             "tier": p.get("tier"), "source": "upgrade" if p.get("upgrade") else "stripe",
             "status": p.get("status"), "session_id": p.get("session_id"),
             "amount_cents": int(p.get("amount") or 0),
             "needs_review": bool(p.get("needs_review"))} for p in payments]
    rows += [{"at": p.get("tier_granted_at") or p.get("created_at"), "user_id": p.get("user_id"),
              "user_name": names.get(p.get("user_id")) or p.get("user_id"),
              "tier": p.get("tier"), "source": "gift", "status": "paid",
              "amount_cents": 0, "needs_review": False}
             for p in passes if p.get("tier_source") == "gift"]
    rows.sort(key=lambda r: str(r.get("at") or ""), reverse=True)

    paid = [p for p in payments if p.get("status") == "paid"]
    revenue_cents = sum(int(p.get("amount") or 0) for p in paid)
    shown = await season_name(season)
    ov = await season_override(season)
    return {
        "ok": True,
        # `season` is the OBJECT the header renders (name + id + ends_at), not a
        # bare id string.
        "season": {"id": season, "name": shown,
                   "starts_at": start.isoformat(), "ends_at": end.isoformat(),
                   "ended": season_has_ended(season)},
        "season_id": season, "season_name": shown,
        # What the rename box needs: the text as typed (empty = using the
        # built-in name), the mode, and the built-in name for the reset button.
        "season_name_text": sanitize_season_name(ov.get("name")),
        "season_name_verbatim": bool(ov.get("verbatim")),
        "season_name_custom": bool(sanitize_season_name(ov.get("name"))),
        "season_name_default": season_display_name(season),
        "season_name_max": SEASON_NAME_MAX,
        "ended": season_has_ended(season),
        "buyers": buyers,
        "claims_count": int(claims_count),
        "revenue_cents": revenue_cents,
        "revenue_usd": round(revenue_cents / 100.0, 2),
        "purchases": rows[:200],
        "passes": len(passes), "by_tier": by_tier,
        "settled": sum(1 for p in passes if p.get("settled")),
        "payments": payments[:200],
        "needs_review": [p for p in payments if p.get("needs_review")],
        "payments_enabled": stripe_available(),
        "live_tokens_enabled": live_tokens_enabled(),
    }


@router.post("/admin/gift")
@_contained("admin-gift")
async def bp_admin_gift(data: AdminGiftIn, admin=Depends(_require_admin)):
    target = await _resolve_user(data.needle)
    season = current_season_id()
    res = await grant_tier(target, season, str(data.tier or "").strip(), "gift",
                           note=f"gift by {admin.get('persona_name') or admin.get('id')}: {data.note or ''}")
    try:
        await _add_log(admin["id"], "bp_gift", target["id"],
                       {"tier": data.tier, "season": season, "note": data.note, **res})
    except Exception:
        pass
    return {"ok": True, "success": True, "user_id": target["id"],
            "user_name": target.get("persona_name"), **res}


@router.post("/admin/grant-xp")
@_contained("admin-grant-xp")
async def bp_admin_grant_xp(data: AdminGrantXpIn, admin=Depends(_require_admin)):
    target = await _resolve_user(data.needle)
    uid = target["id"]
    amount = int(data.amount or 0)
    if amount == 0:
        _fail(400, "Indica una cantidad de XP distinta de cero.")
    season = current_season_id()
    await _get_pass(uid, season)
    await db.bp_passes.update_one({"user_id": uid, "season": season}, {"$inc": {"xp": amount}})
    doc = await db.bp_passes.find_one({"user_id": uid, "season": season}, {"_id": 0})
    if int(doc.get("xp") or 0) < 0:  # never leave a negative pass
        await db.bp_passes.update_one({"user_id": uid, "season": season}, {"$set": {"xp": 0}})
        doc["xp"] = 0
    try:
        await _add_log(admin["id"], "bp_grant_xp", uid, {"amount": amount, "season": season})
    except Exception:
        pass
    return {"ok": True, "success": True, "user_id": uid, "user_name": target.get("persona_name"),
            "xp": int(doc.get("xp") or 0), "level": level_from_xp(int(doc.get("xp") or 0))}


@router.post("/admin/season-name")
@_contained("admin-season-name")
async def bp_admin_season_name(data: AdminSeasonNameIn, admin=Depends(_require_admin)):
    """Rename the pass season from the admin tab -- no deploy, no restart. An
    empty name restores the built-in one."""
    season = (data.season or "").strip() or current_season_id()
    if not _season_parts(season):
        _fail(400, "Esa temporada no existe. Usa el formato 2026-08.")
    raw = data.name or ""
    if raw.strip() and not sanitize_season_name(raw):
        # Everything he typed was control characters or spacing.
        _fail(400, "Ese nombre queda vacío. Escribe al menos una letra.")
    res = await set_season_name(season, raw, bool(data.verbatim),
                                by=str(admin.get("persona_name") or admin.get("id") or ""))
    try:
        await _add_log(admin["id"], "bp_season_name", season,
                       {"text": res["text"], "verbatim": res["verbatim"], "shown": res["name"]})
    except Exception:
        pass
    return {"ok": True, "success": True, **res}


@router.post("/admin/settle")
@_contained("admin-settle")
async def bp_admin_settle(data: AdminSettleIn, admin=Depends(_require_admin)):
    res = await settle_ended_seasons()
    try:
        await _add_log(admin["id"], "bp_settle", data.season or "ended", res)
    except Exception:
        pass
    return {"ok": True, "success": True, "count": res.get("settled", 0), **res}
