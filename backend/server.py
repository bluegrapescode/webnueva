from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query, Header
from fastapi.responses import RedirectResponse, FileResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError
import os
import re
import logging
import uuid
import jwt
import base64
import hmac
import hashlib
import secrets
import asyncio
import math
import time
import unicodedata
import httpx
from urllib.parse import urlencode
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError
from typing import Any, List, Optional
from datetime import datetime, timezone, timedelta, date

import glitch_catalog
import skin_exact
import seed_data
import cosmetics_data
import quest_data
import quest_pois
import quest_events
import gen0_infection
import leaderboards
import event_feed

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

import rcon_client
import game_telemetry
from game_telemetry import telemetry as game_tele

# La Isla Nublar game-mod web surface (LOCAL). Importing game_ipc also registers
# the .webp/.glb/.gltf/.wasm mimetypes the 3D dino assets need on Windows.
import threading
import game_ipc

# ---------- skin contract v2 (ten colour slots) ----------------------------
# THIS OWNER IS A THIN ADAPTER OVER THE FRAMEWORK, NOT A FORK. The five
# `lin_skin*` / `lin_skinv2_*` modules below are RENDERED from the canonical
# webcore contract by `webcore.bespoke_skin_contract.flatten --ns lin`; the
# sixth carries the 767 KB capability sidecar. Never edit them by hand - fix
# the framework and re-render, or `flatten`/`manifest_module --check` reports
# them as DRIFTED.
#
# THEY ARE FLAT MODULES BECAUSE THIS OWNER'S DEPLOY LANE IS TOP-LEVEL-ONLY.
# `C:\LaIslaNublarDeploy\deploy_agent.ps1:88` picks changed files with
# `^web/backend/[^/]+\.py$`. A `webcore/` PACKAGE under web/backend is filed
# as a non-py manual step and never copied to prod - while the rewritten
# server.py, being top-level, deploys ALONE and boots into
# `ModuleNotFoundError: webcore`, failing the agent's health probe and
# tripping this owner's AUTO-ROLLBACK. The gate that proves a ship survives
# its own lane is `webcore.bespoke_skin_contract.deploy_lane`.
#
# The sidecar is a .py for the same reason: a 767 KB JSON is not a .py, so the
# lane would ALERT and drop it and this site would answer `no_manifest`
# forever with every upstream gate green. `install()` writes it back out to a
# real path (outside the served root and outside the website backup mirror)
# because the canonical contract reads it off disk; it never raises, and
# `None` here is the contract's own named `no_manifest` state, not a crash.
import lin_skinv2_manifest
_SKIN_V2_MANIFEST_PATH = lin_skinv2_manifest.install(
    os.environ.get("LIN_SKINV2_MANIFEST_DIR"),
    Path(__file__).resolve().parents[2] / "data" / "skincontract",
    Path(__file__).resolve().parent / "_skinv2_data")
if _SKIN_V2_MANIFEST_PATH is not None:
    os.environ.setdefault("SKIN_CAPABILITIES_V2_PATH", str(_SKIN_V2_MANIFEST_PATH))
import lin_skinv2_engine as _skin_v2_engine
import lin_skinv2_fastapi as _skin_v2_mount

import native_bans
import mutation_catalog
import vault
import voice_token
import pop_control
import dino_recovery
import save_rescue
# Pase de Batalla. Self-contained like crash_game.py: it never imports server.py
# (the Mongo handle, the auth dependencies and four helpers arrive through
# battle_pass.configure(), called beside the router include at the bottom).
import battle_pass
# Nublar Spin (daily wheel, Mini Juegos tab). Same self-contained shape:
# wheel_routes.configure() beside the router include at the bottom.
import wheel_routes
try:
    import skinkeeper_web
except ImportError:  # deploy-ordering guard, see docs/AUTODEPLOY.md
    class _SkinKeeperUnavailable:
        @staticmethod
        def record_apply(cmd, kind):
            return False

        @staticmethod
        def ensure_web():
            logger.warning(
                "[SkinKeeper] skinkeeper_web.py is NOT deployed - skin capture is "
                "DISABLED; rejoin restores will find no recipe. Place the file in "
                "web/backend/ and restart.")

        @staticmethod
        def maybe_start_birth_sweep():
            return None

    skinkeeper_web = _SkinKeeperUnavailable()
import teleport_presets
import strike_feed
import staff_feed
import crash_game
# Baneos de la página web (2026-08-17): the store, the gate and the owner-only
# console in one self-contained module (never imports server.py; the Mongo
# handle + auth deps arrive through webban.configure() beside the router
# include, exactly like battle_pass). Its check() is called INSIDE
# get_current_user and BEFORE the Steam callback mints a token.
import webban


STEAM_API_KEY = os.environ.get('STEAM_API_KEY', '')
ADMIN_STEAM_IDS = set(s.strip() for s in os.environ.get('ADMIN_STEAM_IDS', '').split(',') if s.strip())
JWT_SECRET = os.environ.get('JWT_SECRET', 'devsecret')
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')
FRONTEND_URL = os.environ.get('FRONTEND_URL', '').rstrip('/')
PATREON_CLIENT_ID = os.environ.get('PATREON_CLIENT_ID', '')
PATREON_CLIENT_SECRET = os.environ.get('PATREON_CLIENT_SECRET', '')
PATREON_CREATOR_ACCESS_TOKEN = os.environ.get('PATREON_CREATOR_ACCESS_TOKEN', '')
PATREON_CAMPAIGN_ID = os.environ.get('PATREON_CAMPAIGN_ID', '').strip()
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET', '')
DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')
DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID', '')
DISCORD_VIP_ROLE_ID = os.environ.get('DISCORD_VIP_ROLE_ID', '')
VIP_GRANT_ON_LINK = int(os.environ.get('VIP_GRANT_ON_LINK', '50') or '50')

# ── Streamer Pack (free, application-only perk driven by a dedicated Discord role) ──
# The role is granted on admin approval (via _discord_role_call, same lane as tier roles)
# and its benefits are computed LIVE from role membership, so removing the role (ban /
# caught cheating) auto-revokes everything on the next access check.
DISCORD_STREAMER_ROLE_ID = os.environ.get('DISCORD_STREAMER_ROLE_ID', '').strip()
# Channel the web posts each application into (with Approve/Reject buttons the bot handles).
DISCORD_STREAMER_APPS_CHANNEL_ID = os.environ.get('DISCORD_STREAMER_APPS_CHANNEL_ID', '').strip()
# Streamer-only channel used ONLY as a fallback when a payout DM cannot be delivered
# (closed DMs). Optional: unset just means a failed DM is logged instead of re-routed.
DISCORD_STREAMER_LOUNGE_CHANNEL_ID = os.environ.get('DISCORD_STREAMER_LOUNGE_CHANNEL_ID', '').strip()
# Same idea for the Patreon payout notice: optional fallback channel used ONLY when a
# patron's DM cannot be delivered. Unset (the default) just logs the undelivered notice —
# the money is never affected either way.
DISCORD_PATREON_NOTICE_CHANNEL_ID = os.environ.get('DISCORD_PATREON_NOTICE_CHANNEL_ID', '').strip()
try:
    STREAMER_AMBER = int(os.environ.get('LIN_STREAMER_AMBER', '') or 20000)
except ValueError:
    STREAMER_AMBER = 20000
try:
    STREAMER_MULT = float(os.environ.get('LIN_STREAMER_MULT', '') or 2.0)
except ValueError:
    STREAMER_MULT = 2.0
# Shared secret for the loopback bot->web decision callback (Approve/Reject buttons).
LIN_INTERNAL_KEY = os.environ.get('LIN_INTERNAL_KEY', '').strip()
# Public Discord invite surfaced on the Streamer Pack section for users not yet in the guild.
DISCORD_INVITE_URL = os.environ.get('DISCORD_INVITE_URL', '').strip()


def _parse_patreon_roles(raw):
    """'id:Label,id:Label' (or bare ids) -> ordered {role_id: label}."""
    out = {}
    for part in (raw or '').split(','):
        part = part.strip()
        if not part:
            continue
        rid, _, label = part.partition(':')
        rid = rid.strip()
        if rid.isdigit():
            out[rid] = label.strip() or rid
    return out


DISCORD_PATREON_ROLES = _parse_patreon_roles(os.environ.get('DISCORD_PATREON_ROLE_IDS', ''))
DISCORD_TIER_ROLE_SYNC = os.environ.get('LIN_DISCORD_ROLE_SYNC', '1').strip().lower() not in {'0', 'false', 'off'}
try:
    PATREON_RESYNC_HOURS = float(os.environ.get('LIN_PATREON_RESYNC_HOURS', '') or 12)
except ValueError:
    PATREON_RESYNC_HOURS = 12.0
# Creator-side truth cadence: the reconcile loop reads the CAMPAIGN member list with the
# creator token (no per-user OAuth involved), so cancels, tier changes and brand-new
# patrons land within minutes even for people who never linked or whose token died.
try:
    PATREON_RECONCILE_MINUTES = float(os.environ.get('LIN_PATREON_RECONCILE_MINUTES', '') or 15)
except ValueError:
    PATREON_RECONCILE_MINUTES = 15.0
# Joining-Amberium ledger audit: how often the money owed vs the money paid is
# re-derived for active patrons, and how many accounts one pass may touch.
try:
    PATREON_AMBER_AUDIT_MINUTES = float(os.environ.get('LIN_PATREON_AMBER_AUDIT_MINUTES', '') or 15)
except ValueError:
    PATREON_AMBER_AUDIT_MINUTES = 15.0
try:
    PATREON_AMBER_AUDIT_BATCH = int(os.environ.get('LIN_PATREON_AMBER_AUDIT_BATCH', '') or 50)
except ValueError:
    PATREON_AMBER_AUDIT_BATCH = 50
PATREON_CREATOR_REFRESH_TOKEN = os.environ.get('PATREON_CREATOR_REFRESH_TOKEN', '')

try:
    PATREON_DEAD_LINK_FAILS = int(os.environ.get('LIN_PATREON_DEAD_LINK_FAILS', '') or 3)
except ValueError:
    PATREON_DEAD_LINK_FAILS = 3

try:
    PATREON_DEAD_LINK_HOURS = float(os.environ.get('LIN_PATREON_DEAD_LINK_HOURS', '') or 24)
except ValueError:
    PATREON_DEAD_LINK_HOURS = 24.0

ALLOW_DEMO_LOGIN = os.environ.get('ALLOW_DEMO_LOGIN', '0').strip().lower() in {'1', 'true', 'yes', 'on'}
SEED_DEMO_MARKET = os.environ.get('SEED_DEMO_MARKET', '0').strip().lower() in {'1', 'true', 'yes', 'on'}
DATA_URL_MAX_CHARS = 2_000_000
DATA_IMAGE_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,", re.IGNORECASE)

PATREON_TIER_AMBER = {"juvie": 18000, "sub": 28000, "adult": 40000, "elder": 60000, "apex": 80000}
PATREON_TIER_BOOST = {"juvie": "1.5x", "sub": "2x", "adult": "2.5x", "elder": "3x", "apex": "3.5x"}
PATREON_TIER_MULT = {"juvie": 1.5, "sub": 2.0, "adult": 2.5, "elder": 3.0, "apex": 3.5}

SKIN_CREATOR_TIER_KEYS = {t.strip() for t in os.environ.get(
    'LIN_SKIN_CREATOR_TIERS', 'sub,adult,elder,apex').split(',') if t.strip()}
#: Glitch Lab: website owners, the dedicated Discord Streamer role, and these
#: Patreon tiers. Deliberately narrower than the skin creator (no juvie/sub
#: without Streamer, and no staff-admin shortcut).
GLITCH_CREATOR_TIER_KEYS = {t.strip() for t in os.environ.get(
    'LIN_GLITCH_CREATOR_TIERS', 'adult,elder,apex').split(',') if t.strip()}
PATREON_PAYOUT_DAYS = 14
CURRENCY_SYMBOL = {"USD": "$", "GBP": "£", "EUR": "€", "MXN": "MX$", "CAD": "C$", "AUD": "A$"}


#: OURS, not Patreon's: what we store for a membership the OWNER GAVE AWAY.
#: Patreon has no word for one - see _demote_comped_status.
PATREON_GIFTED_STATUS = "gifted_no_charge"


def _patreon_charge_backed(last_charge, next_charge):
    """Has money ever moved for this membership, or is it ever going to?
    Either date is enough: the first says they have paid, the second says they
    are scheduled to."""
    return bool(str(last_charge or "").strip() or str(next_charge or "").strip())


def _demote_comped_status(status, last_charge, next_charge):
    """The status to STORE, with a membership the owner comped called what it is
    instead of being filed beside the people who pay.

    ★★★★★ THE HOLE THIS CLOSES. A creator can add a FREE member to any tier on
    their own campaign. Patreon then reports that member as `active_patron`, on
    the tier's real title, carrying the tier's full
    `currently_entitled_amount_cents` — identical field for field to somebody
    paying that price every month. The only difference is that no charge is
    attached: no last charge, no next charge, ever. Every perk gate on this site
    is spelled `status == "active_patron"`, so a gift walked through all of them
    and collected the paid rank, the Amberium multiplier, the joining Amberium
    and the recurring payout. Measured here 2026-08-12: 221 comped memberships
    against 27 real payers, 174 of them wearing the rank the site had granted.

    ★ IT IS A STORAGE-TIME FIX ON PURPOSE. Demoting once, where the row is
    written, means a gift never reaches a gate wearing the paying status — so a
    gate nobody remembered to update fails CLOSED instead of open.

    ★ A BRAND-NEW PLEDGE IS NOT A GIFT. Somebody who pledged an hour ago has not
    been charged yet either; what saves them is their NEXT charge date. Getting
    that wrong takes the rank off a customer who just paid.

    ★ ONLY THE PAYING STATUS IS EVER TOUCHED. former_patron / declined_patron
    come back untouched — Patreon's own word for what happened to them is worth
    more than ours.

    ★ IT SELF-HEALS BOTH WAYS. Re-derived from the campaign's own fields on
    every sync rather than latched onto the row, so a comped member who later
    starts paying is restored by the next pass with nothing to undo.

    Fleet-canonical twin: botcore/modules/patreon.py demote_comped_status.
    """
    if str(status or "").strip().lower() != "active_patron":
        return status
    if _patreon_charge_backed(last_charge, next_charge):
        return status
    return PATREON_GIFTED_STATUS


def _patreon_tier_key(tier_name):
    if not tier_name:
        return None
    t = str(tier_name).lower()
    for key in PATREON_TIER_AMBER:
        if key in t:
            return key
    return None


def _best_entitled_tier(titles):
    """The tier to store when a membership is entitled to several at once.

    Patreon keeps the free tier entitled ALONGSIDE the paid one for a member who
    joined free first and then upgraded, and the paid tier holds no fixed position
    in `currently_entitled_tiers` -- storing whichever title came first recorded
    "Free" for a paying patron, and every paid gate (joining Amberium, bi-weekly
    payout, boost, skin creator, Discord role) then refused him. Prefer the
    highest-priced recognized tier; fall back to the first title only when nothing
    is recognized, so the profile still shows what Patreon sent and the paid gates
    still refuse it."""
    titles = [t for t in titles if t]
    recognized = [t for t in titles if _patreon_tier_key(t)]
    if recognized:
        return max(recognized, key=lambda t: PATREON_TIER_AMBER[_patreon_tier_key(t)])
    return titles[0] if titles else None


def _patreon_welcome_amber_paid(user):
    """How much joining Amberium this account has ALREADY been paid, or None when that
    cannot be established from the row.

    `patreon_welcome_amber_total` is the exact figure and is written by every payment
    from 2026-07-29 on. Rows paid before that field existed carry only the tier key
    they were priced at -- and that key IS the amount, so the fallback is exact too,
    not a guess.

    ★None is NOT zero. A row that carries the joining stamp but neither field has been
    paid an unknown amount, and pricing that as "nothing paid yet" would make the
    upgrade top-up hand it a SECOND full joining payment. The caller refuses instead."""
    u = user or {}
    raw = u.get("patreon_welcome_amber_total")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw >= 0:
        return int(raw)
    return PATREON_TIER_AMBER.get(u.get("patreon_welcome_amber_tier"))


def _payout_multiplier(user):
    """PrimeMeat playtime multiplier. Active Patreon tier gives its multiplier; the
    Streamer Pack gives STREAMER_MULT (2.0x). A user who is both gets the higher of the
    two (no stacking). 1.0 for everyone else. Reads the STORED streamer flag (kept fresh
    by _patreon_access / the amber pass / the resync loop), so it revokes with the role."""
    u = user or {}
    mult = 1.0
    if u.get("patreon_patron_status") == "active_patron":
        mult = PATREON_TIER_MULT.get(_patreon_tier_key(u.get("patreon_tier_name")), 1.0)
    if u.get("discord_streamer_role"):
        mult = max(mult, STREAMER_MULT)
    return mult


def _skin_creator_allowed(access: dict) -> bool:
    """Skin-creator entitlement for an allowed patreon-access decision, and THE single
    truth for it — `access["skin_creator"]` is only this function's cached value.

    The Streamer Pack includes the skin creator with no paid tier, so it is honoured
    here. It used to be honoured ONLY where the field was built, while POST /apply
    called this tier-only helper directly: every pure streamer saw "Acceso activo" in
    the editor and then got 403 tier_insufficient on Aplicar (owner report 2026-07-24,
    holder `lyngta`). One entitlement, one function — the two can no longer disagree."""
    a = access or {}
    if a.get("via") == "admin":
        return True
    if a.get("streamer") or a.get("via") == "streamer":
        return True
    key = _patreon_tier_key(a.get("tier"))
    return bool(key and key in SKIN_CREATOR_TIER_KEYS)


def _glitch_creator_verdict(user, access) -> dict:
    """Glitch Lab entitlement: WEBSITE OWNERS, the server-verified Discord
    Streamer role, and Adult / Elder / Apex Patreon tiers. Staff 'admin' alone
    does not open it. Returns the structured verdict the UI renders:
    {allowed, via, tier, tier_key}."""
    u = user or {}
    a = access or {}
    if _is_owner(u):
        return {"allowed": True, "via": "owner", "tier": a.get("tier"),
                "tier_key": _patreon_tier_key(a.get("tier"))}
    if a.get("allowed") and (a.get("streamer") or a.get("via") == "streamer"):
        return {"allowed": True, "via": "streamer", "tier": a.get("tier"),
                "tier_key": _patreon_tier_key(a.get("tier"))}
    key = _patreon_tier_key(a.get("tier")) if a.get("allowed") else None
    if key and key in GLITCH_CREATOR_TIER_KEYS:
        return {"allowed": True, "via": "tier", "tier": a.get("tier"), "tier_key": key}
    return {"allowed": False, "via": None, "tier": a.get("tier"),
            "tier_key": _patreon_tier_key(a.get("tier"))}


def _glitch_tier_403(access, verdict):
    """Structured refusal for the Glitch Lab lanes — same rendering contract as
    tier_insufficient (the editor shows the message + refreshed access)."""
    _pretty = {"juvie": "Juvie", "sub": "Sub Adult", "adult": "Adult", "elder": "Elder", "apex": "Apex"}
    raw = str((access or {}).get("tier") or "Patreon")
    tier_label = _pretty.get(_patreon_tier_key(raw) or "", raw)
    return HTTPException(status_code=403, detail={
        "code": "glitch_tier_insufficient", "access": access, "glitch": verdict,
        "message": ("El Glitch Lab está incluido para Streamers, cuentas Owner y los "
                    f"niveles Adult, Elder y Apex — tu nivel actual ({tier_label}) no lo incluye.")})

JWT_ALGO = "HS256"
STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"

# Dino Crash (crash_game.py) is a self-contained module that never imports from
# server.py -- to avoid a circular import, the shared Mongo handle and JWT
# secret are handed in once here (same dependency-injection pattern as
# vault.set_loop()).
crash_game.configure(db, JWT_SECRET, ban_check=webban.check)

# ------------------------------------------------------------------------------
# INICIALIZACIÓN DE FASTAPI
# ------------------------------------------------------------------------------
app = FastAPI()

# ------------------------------------------------------------------------------
# RUTAS DE TU SERVIDOR
# ------------------------------------------------------------------------------
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ------------------------------------------------------------------------------
# Access-log noise gate.
#
# Every signed-in browser polls /api/chat/poll, /api/friends and /api/me/state
# continuously, and uvicorn writes one access line per request. Measured on prod
# 2026-08-04: logs/backend.log had reached 3.4 GB and was growing ~87 MB every
# four minutes (~30 GB/day), which fills the box's remaining disk in under two
# weeks. Those lines carry no diagnostic value -- they are all "200 OK" on the
# same three endpoints -- while everything that DOES matter (errors, warnings,
# the vault/body-drop application logs, and any 4xx/5xx on these same endpoints)
# is untouched.
#
# Deliberately a filter, not `--no-access-log`: the launcher is a `:loop` .bat
# that must never be edited while it is running, and blanket-disabling access
# logging would also hide genuine failures.
_QUIET_ACCESS_PREFIXES = ("/api/chat/poll", "/api/friends", "/api/me/state")


class _QuietPollAccessFilter(logging.Filter):
    """Drop uvicorn access lines for successful high-frequency poll requests."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            args = record.args
            if not isinstance(args, tuple) or len(args) < 5:
                return True
            path = str(args[2] or "")
            status = int(args[4])
            if status >= 400:
                return True
            return not path.startswith(_QUIET_ACCESS_PREFIXES)
        except Exception:
            # Never let the log filter be the thing that breaks logging.
            return True


logging.getLogger("uvicorn.access").addFilter(_QuietPollAccessFilter())


# ---------- helpers ----------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return uuid.uuid4().hex


def _validate_data_image(value: Optional[str], field_name: str) -> Optional[str]:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field_name} debe ser una imagen data URL PNG, JPEG o WebP")
    if len(value) > DATA_URL_MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"{field_name} supera el limite de 2 MB")
    if not DATA_IMAGE_RE.match(value):
        raise HTTPException(status_code=400, detail=f"{field_name} debe ser una imagen data URL PNG, JPEG o WebP")
    try:
        payload = value.split(",", 1)[1]
        base64.b64decode(payload, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field_name} es una imagen data URL invalida")
    return value


def _validated_skin3d_config(config: dict) -> dict:
    cfg = dict(config or {})
    if "preview" in cfg:
        cfg["preview"] = _validate_data_image(cfg.get("preview"), "preview")
    return cfg


def gen_recovery_id():
    """Human-readable dino recovery code, e.g. 1686-18379-6399."""
    import random as _r
    return f"{_r.randint(1000, 9999)}-{_r.randint(10000, 99999)}-{_r.randint(1000, 9999)}"


def make_token(user_id: str):
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not creds:
        raise HTTPException(status_code=401, detail="Inicia sesion para continuar")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Sesion invalida o expirada")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    # THE WEBSITE-BAN GATE (2026-08-17). This is the ONE place a bearer token
    # becomes a user, so a banned account is refused here for every route that
    # depends on it - no route has to remember to. Plain words in the detail,
    # and X-Web-Ban so the page can tell a ban from an expired token and say
    # why. webban.check never raises: a store fault answers "not banned" for a
    # few seconds and is counted (the Baneos tab shows the count).
    banned, ban_row = await webban.check(user.get("steam_id"))
    if banned:
        raise HTTPException(status_code=401, detail=webban.message(ban_row),
                            headers={"X-Web-Ban": "1"})
    return user


async def get_admin_user(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acceso de administrador requerido")
    return user


# Staff ranks (separate from playtime rank). Colours + permissions per rank.
STAFF_RANKS = {
    "owner":  {"label": "Owner",     "color": "#ff3b3b", "perms": ["all"]},
    "admin":  {"label": "Admin",     "color": "#D4AF37", "perms": ["economy", "users", "codes", "chat_mod", "ranks"]},
    "mod":    {"label": "Moderator", "color": "#38bdf8", "perms": ["chat_mod"]},
    "helper": {"label": "Helper",    "color": "#22c55e", "perms": ["chat_mod"]},
    "vip":    {"label": "VIP",       "color": "#a855f7", "perms": []},
}


def staff_meta(rank):
    return STAFF_RANKS.get(rank) if rank in STAFF_RANKS else None


def _has_chat_mod(user):
    r = user.get("staff_rank")
    return user.get("role") == "admin" or r in ("owner", "admin", "mod", "helper")


def _is_owner(user):
    return user.get("staff_rank") == "owner" or user.get("steam_id") in ADMIN_STEAM_IDS


async def get_owner_user(user=Depends(get_current_user)):
    if not _is_owner(user):
        raise HTTPException(status_code=403, detail="Solo el Dueño (Owner) puede hacer esto")
    return user


async def add_log(actor, action, target=None, meta=None):
    await db.logs.insert_one({
        "id": new_id(), "actor": actor, "action": action, "target": target,
        "meta": meta or {}, "created_at": now_iso(),
    })


# ---- app settings (admin-configurable) ----
_chat_cooldown = None


async def chat_cooldown_value():
    global _chat_cooldown
    if _chat_cooldown is None:
        doc = await db.settings.find_one({"_id": "app"})
        _chat_cooldown = int(doc.get("chat_cooldown_seconds", 1)) if doc else 1
    return _chat_cooldown


RANKS = ["Hatchling", "Juvenile", "Sub-Adult", "Adult", "Elder", "Apex"]


def rank_for_playtime(minutes: int) -> str:
    hours = minutes / 60
    if hours < 5:
        return RANKS[0]
    if hours < 25:
        return RANKS[1]
    if hours < 75:
        return RANKS[2]
    if hours < 200:
        return RANKS[3]
    if hours < 500:
        return RANKS[4]
    return RANKS[5]


def _nonnegative_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def public_user(u: dict) -> dict:
    return {
        "id": u["id"], "steam_id": u.get("steam_id"), "persona_name": u.get("persona_name"),
        "avatar": u.get("avatar"), "profile_url": u.get("profile_url"), "role": u.get("role", "user"),
        "coins": u.get("coins", 0), "vip_coins": u.get("vip_coins", 0),
        "fossils": _nonnegative_int(u.get("fossils")),
        # Nublar Spin bonus balance. Admin/owner user rows consume this same
        # public shape, so the number shown beside a grant is the stored value.
        "wheel_bonus_spins": _nonnegative_int(u.get("wheel_bonus_spins")),
        "xp": u.get("xp", 0), "gift_streak": u.get("gift_streak", 0),
        "cosmetics": resolve_cosmetics(u), "emotes": owned_emotes(u),
        "playtime_minutes": u.get("playtime_minutes", 0), "rank": rank_for_playtime(u.get("playtime_minutes", 0)),
        "staff_rank": u.get("staff_rank"), "staff_meta": staff_meta(u.get("staff_rank")),
        "is_owner": _is_owner(u),
        "created_at": u.get("created_at"), "last_login": u.get("last_login"),
        "last_daily_claim": u.get("last_daily_claim"),
        "patreon": {
            "linked": bool(u.get("patreon_id")),
            "patron_status": u.get("patreon_patron_status"),
            "tier_name": u.get("patreon_tier_name"),
        },
        "discord": {
            "linked": bool(u.get("discord_id")),
            "username": u.get("discord_username"),
            "in_guild": u.get("discord_in_guild", False),
            "vip_role": u.get("discord_vip_role_granted", False),
            "tier_role": u.get("discord_tier_role") or None,
            "streamer": bool(u.get("discord_streamer_role")),
        },
    }


COSMETIC_EQUIP_SLOTS = ["color", "border", "effect", "font", "chat_bg"]


def resolve_cosmetics(u):
    """Resolve the user's equipped decorations into full render objects for chat/profile."""
    eq = u.get("cosmetics_equipped") or {}
    return {slot: cosmetics_data.DECO_BY_ID.get(eq.get(slot)) for slot in COSMETIC_EQUIP_SLOTS}


def owned_emotes(u):
    owned = set(u.get("cosmetics_owned") or [])
    return [d for d in cosmetics_data.items_by_category("emote") if d["id"] in owned]


async def add_transaction(user_id, currency, amount, ttype, description):
    await db.transactions.insert_one({
        "id": new_id(), "user_id": user_id, "currency": currency, "amount": amount,
        "type": ttype, "description": description, "created_at": now_iso(),
    })


# ---------- models ----------
class PurchaseInput(BaseModel):
    item_id: str


class CheckoutItem(BaseModel):
    item_id: str
    quantity: int = 1


class CheckoutInput(BaseModel):
    items: List[CheckoutItem]


class PurchaseDinoInput(BaseModel):
    item_id: str
    tier: str = "basic"  # "basic" | "prime"
    mutations: List[str] = []
    parents: List[str] = []  # "Linaje Parental" picker: the frontend has always
                             # sent this; until 2026-07-15 the model dropped it.


class ReorderInput(BaseModel):
    ids: List[str]


class EquipSkinInput(BaseModel):
    inv_id: str


class CustomSkinInput(BaseModel):
    name: Optional[str] = None
    color: str
    config: Optional[dict] = None       # full 3D zone config (base/underbelly/pattern/eyes/...)
    image: Optional[str] = None         # captured preview (data URL) of the configured dino


class MarketListInput(BaseModel):
    inv_id: Optional[str] = None  # the specific inventory dino being listed (source=="vault": omitted)
    type: str = "sale"          # "sale" | "auction"
    # THE SELLER'S OWN NUMBER, inside a per-animal rail (2026-08-11 owner spec).
    # Deliberately typed Any, not Optional[int]: pydantic would coerce "5000" to
    # 5000 and reject 5.5 with a 422 in English, and this lane owes the player
    # one exact Spanish sentence per wrong shape. The route validates the RAW
    # value -- present, int, not bool, inside abs bounds, inside the rails.
    price: Any = None
    duration_hours: Any = 24    # MEMBERSHIP-tested against the live tier menu, never snapped
    title: Optional[str] = None # custom display name, e.g. "Rex 16 mutations"
    source: Optional[str] = None   # None (inventory, default) | "vault"
    dino_id: Optional[int] = None  # parked_dinos row id -- required when source=="vault"
    # ONE ID PER ATTEMPT. A replay of the same id returns the stored receipt
    # instead of listing the animal twice; a new id is a new attempt. Typed Any
    # for the same reason `price` is: this lane owes the player one exact
    # sentence per wrong shape, not a 422 in English.
    client_request_id: Any = None


class MarketActionInput(BaseModel):
    """The body buy / withdraw post. Both fields are OPTIONAL so the pre-wave
    frontend -- which posts no body at all -- keeps working unchanged."""
    expected_price: Any = None
    client_request_id: Any = None


class MutationEditInput(BaseModel):
    mutations: List[str] = []


class DinoRenameInput(BaseModel):
    name: str = ""


class MutationGroupsInput(BaseModel):
    groups: dict = {}


class BidInput(BaseModel):
    # `amount` OMITTED is the AUTO lane: bid exactly the next legal amount, and
    # prove the page was current by sending the number it showed. Typed Any (not
    # Optional[int]) so a float, a string or a bool earns its own exact Spanish
    # refusal instead of pydantic's English 422 -- and so that `True`, which is
    # an int in Python, can be refused as a TYPE rather than read as one coin.
    amount: Any = None
    expected_price: Any = None
    client_request_id: Any = None


class RewardModel(BaseModel):
    coins: int = 0
    vip_coins: int = 0
    # Promo codes grant BONUS spins, never today's daily allowance. Capping the
    # per-redemption value keeps a typo on an unlimited code bounded.
    spins: int = Field(0, strict=True, ge=0, le=100)
    items: List[str] = []          # store_item ids
    dinos: List[str] = []          # dinosaur slugs
    roles: List[str] = []          # role names


class CodeInput(BaseModel):
    code: str
    name: str
    description: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    max_uses: int = 0              # 0 = unlimited
    per_user: int = 1
    reward: RewardModel = Field(default_factory=RewardModel)
    active: bool = True


class CodeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    max_uses: Optional[int] = None
    per_user: Optional[int] = None
    active: Optional[bool] = None


class RedeemInput(BaseModel):
    code: str


class GrantInput(BaseModel):
    user_id: str
    currency: str                  # "normal" | "vip"
    amount: int
    reason: str = "Admin grant"


class RoleInput(BaseModel):
    user_id: str
    role: str                      # "user" | "admin"


class StreamerApplyInput(BaseModel):
    platform: str = ""
    channel_url: str = ""
    followers: str = ""
    avg_viewers: str = ""
    about: str = ""


class StreamerDecideInput(BaseModel):
    message_id: str = ""
    channel_id: str = ""
    action: str = ""               # "approve" | "reject"
    moderator_id: str = ""
    moderator_name: str = ""
    reason: str = ""


class NewsInput(BaseModel):
    title: str
    body: str
    category: str = "Update"
    image: Optional[str] = None


class EventInput(BaseModel):
    title: str
    description: str
    date_label: str
    type: str = "Community"
    image: Optional[str] = None


class StoreItemInput(BaseModel):
    name: str
    description: str
    category: str
    price: int
    currency: str = "normal"
    rarity: str = "Common"
    image: Optional[str] = None
    featured: bool = False


class StoreItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    currency: Optional[str] = None
    rarity: Optional[str] = None
    featured: Optional[bool] = None


class RecoverDinoInput(BaseModel):
    """Three ways to hand a dino back, all of which end in the same vault row.

    * ``death_key``  — the normal path: the admin clicked one of the player's
      lost dinos, so we restore exactly that one.
    * ``recovery_id`` — the legacy pre-2026-07-15 dino_records path, kept alive
      so the handful of old records stay usable.
    * ``steam_id`` + ``species`` — the manual fallback for a loss the mod's
      death log cannot describe.
    """
    recovery_id: Optional[str] = None
    death_key: Optional[str] = None
    steam_id: Optional[str] = None
    species: Optional[str] = None
    growth: Optional[float] = None
    is_prime: Optional[bool] = None
    is_elder: Optional[bool] = None
    mutations: Optional[str] = None
    # The rest of what makes a dino itself. build_recovery_payload has always
    # accepted these, but no caller ever passed them, so an admin had no way to
    # repair a recovery that came back wrong — the only lever was the species
    # and the growth. Every one of them overrides the captured value.
    parent_mutations: Optional[str] = None
    elder_mutations: Optional[str] = None
    elder_stacks: Optional[int] = None
    prime_conditions: Optional[int] = None
    prime_route_mig: Optional[int] = None
    prime_route_pat: Optional[int] = None
    # A grant that would hand back an EMPTY dino — right species, right size,
    # none of its mutations, prime or elder state — is refused unless the admin
    # says so explicitly. That silent degradation is the entire bug this lane
    # was reported for; making it a decision is the fix that matters most.
    allow_partial: Optional[bool] = False


class FriendUserInput(BaseModel):
    user_id: str


class SteamAddInput(BaseModel):
    query: str = ""


class FriendRespondInput(BaseModel):
    user_id: str
    accept: bool = True


class TeleportRespondInput(BaseModel):
    request_id: str
    accept: bool = True


class DinoInput(BaseModel):
    slug: str
    name: str
    type: str
    diet: str
    rarity: str = "Common"
    description: str
    image: Optional[str] = None
    speed: int = 50
    health: int = 50
    weight: int = 1000
    damage: int = 50
    growth_time: str = "1h 00m"
    abilities: List[str] = []
    status: str = "Available"
    featured: bool = False


# ---------- auth / steam ----------
@api_router.get("/auth/steam/login")
async def steam_login():
    return_to = f"{PUBLIC_BASE_URL}/api/auth/steam/callback"
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": PUBLIC_BASE_URL,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return RedirectResponse(url=f"{STEAM_OPENID_URL}?{urlencode(params)}")


@api_router.get("/auth/steam/callback")
async def steam_callback(request: Request):
    params = dict(request.query_params)
    # validate with steam
    validation = dict(params)
    validation["openid.mode"] = "check_authentication"
    async with httpx.AsyncClient(timeout=15) as hc:
        resp = await hc.post(STEAM_OPENID_URL, data=validation)
    if "is_valid:true" not in resp.text:
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?error=invalid")

    claimed = params.get("openid.claimed_id", "")
    match = re.search(r"/openid/id/(\d+)", claimed)
    if not match:
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?error=nosteamid")
    steam_id = match.group(1)

    # A banned account cannot start a FRESH session either: checked here, on
    # the store directly (no cache), BEFORE any token is minted or the user row
    # is touched. Back to the site with the same plain-words sentence.
    banned, ban_row = await webban.check(steam_id, fresh=True)
    if banned:
        logger.info("steam sign-in refused: website ban on ...%s", steam_id[-4:])
        return RedirectResponse(url=webban.banned_redirect_url(FRONTEND_URL, ban_row))

    persona, avatar, profile_url = None, None, None
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            r = await hc.get(
                "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
                params={"key": STEAM_API_KEY, "steamids": steam_id},
            )
        players = r.json().get("response", {}).get("players", [])
        if players:
            p = players[0]
            persona = p.get("personaname")
            avatar = p.get("avatarfull") or p.get("avatar")
            profile_url = p.get("profileurl")
    except Exception as e:
        logger.warning(f"steam summary failed: {e}")

    token = await upsert_steam_user(steam_id, persona, avatar, profile_url)
    return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback#token={token}")


async def upsert_steam_user(steam_id, persona, avatar, profile_url):
    is_admin = steam_id in ADMIN_STEAM_IDS
    existing = await db.users.find_one({"steam_id": steam_id})
    if existing:
        update = {
            "persona_name": persona or existing.get("persona_name"),
            "avatar": avatar or existing.get("avatar"),
            "profile_url": profile_url or existing.get("profile_url"),
            "last_login": now_iso(),
        }
        if is_admin:
            update["role"] = "admin"  # auto-promote configured owners
        await db.users.update_one({"id": existing["id"]}, {"$set": update})
        return make_token(existing["id"])
    uid = new_id()
    doc = {
        "id": uid, "steam_id": steam_id, "persona_name": persona or f"Survivor_{steam_id[-4:]}",
        "avatar": avatar, "profile_url": profile_url, "role": "admin" if is_admin else "user",
        "coins": 1500, "vip_coins": 25, "playtime_minutes": 0,
        "created_at": now_iso(), "last_login": now_iso(), "last_daily_claim": None,
    }
    await db.users.insert_one(doc)
    await add_transaction(uid, "normal", 1500, "reward", "Welcome bonus")
    await add_transaction(uid, "vip", 25, "reward", "Founder VIP bonus")
    return make_token(uid)


@api_router.post("/auth/demo")
async def demo_login():
    """Creates / reuses a demo account so the platform is fully usable without Steam."""
    if not ALLOW_DEMO_LOGIN:
        raise HTTPException(status_code=404, detail="Cuenta demo desactivada")
    demo_steam = "demo_0000000001"
    existing = await db.users.find_one({"steam_id": demo_steam})
    if existing:
        await db.users.update_one({"id": existing["id"]}, {"$set": {"last_login": now_iso(), "role": "admin", "staff_rank": "owner"}})
        uid = existing["id"]
        if not existing.get("active_dino"):
            await _seed_demo_live_dino(uid)
    else:
        uid = new_id()
        await db.users.insert_one({
            "id": uid, "steam_id": demo_steam, "persona_name": "Demo Survivor",
            "avatar": seed_data.LOGO, "profile_url": "https://steamcommunity.com",
            "role": "admin", "staff_rank": "owner", "coins": 8400, "vip_coins": 120, "playtime_minutes": 5200,
            "created_at": now_iso(), "last_login": now_iso(), "last_daily_claim": None,
        })
        await add_transaction(uid, "normal", 8400, "reward", "Demo account funding")
        await add_transaction(uid, "vip", 120, "reward", "Demo VIP funding")
        await _seed_demo_live_dino(uid)
    return {"token": make_token(uid)}


async def _seed_demo_live_dino(uid):
    """Put the demo account in the simulation AS THE OWNER PLAYING: without RCON,
    `_is_user_in_game` reads `active_dino`, so seeding a live dino makes the demo
    appear connected in-game. That unlocks the payout counters, the live-dino card,
    apply-skin-to-live and population respawn in the preview simulation. Seeds a
    fully grown, prime Apex Tyrannosaurus. Non-destructive: only ever called when
    the account has no active dino."""
    d = await db.dinosaurs.find_one({"slug": "trex"}, {"_id": 0}) or await db.dinosaurs.find_one({}, {"_id": 0})
    if not d:
        return
    ad = {
        "slug": d.get("slug"), "name": d.get("name"), "image": d.get("image"),
        "type": d.get("type"), "diet": d.get("diet"), "rarity": d.get("rarity"),
        "set_at": now_iso(), "fed_at": now_iso(),
        "base_growth": 100, "base_stats": d.get("stats", {}),
        "recovery_id": new_id(), "mutations": [], "prime": True,
    }
    await db.users.update_one({"id": uid}, {"$set": {"active_dino": ad}})


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    # web_build rides along so open tabs can detect a newer deployed frontend
    # and self-reload once (AuthContext) instead of silently running stale.
    return {**public_user(user), "web_build": current_web_build()}


@api_router.post("/auth/daily")
async def claim_daily(user=Depends(get_current_user)):
    last = user.get("last_daily_claim")
    if last:
        last_dt = datetime.fromisoformat(last)
        if datetime.now(timezone.utc) - last_dt < timedelta(hours=20):
            raise HTTPException(status_code=400, detail="Ya reclamaste la recompensa diaria. Vuelve mas tarde.")
    reward = 250
    # The stamp IS the claim: pin it to the value we just read so simultaneous
    # claims cannot all pass the 20-hour check above and all pay.
    took = await db.users.update_one(
        {"id": user["id"], "last_daily_claim": last},
        {"$inc": {"coins": reward}, "$set": {"last_daily_claim": now_iso()}})
    if took.modified_count == 0:
        raise HTTPException(status_code=400, detail="Ya reclamaste la recompensa diaria. Vuelve mas tarde.")
    await add_transaction(user["id"], "normal", reward, "reward", "Daily login reward")
    return {"reward": reward, "currency": "normal"}


PASSIVE_INTERVAL_SECONDS = 240
PASSIVE_REWARD = 350
# Longest unobserved gap the passive tick will still pay for. The HUD posts every
# ~20s while the site is open (hidden tabs get throttled, hence > 1 interval of
# grace), so a gap beyond this means the site was closed or the player was
# offline — presence during that window is unverifiable and it is NOT paid:
# the pay window reseeds at `now` instead. Before 2026-07-16 the whole gap was
# paid out at 5 cycles per 20s tick (60x real time) — overnight gaps completed
# every play_time quest and drained PrimeMeat (owner report "way more time than
# needed").
PASSIVE_CATCHUP_MAX_SECONDS = PASSIVE_INTERVAL_SECONDS * 5


def _passive_pay_plan(last, now):
    """Pure decision for one passive tick, unit-testable without Mongo.
    Returns (action, cycles, new_last_iso):
      action 'seed'   — no valid prior stamp: start the window at `now`, pay 0
      action 'reseed' — gap exceeds PASSIVE_CATCHUP_MAX_SECONDS (or the stored
                        stamp is malformed): restart the window at `now`, pay 0
      action 'wait'   — inside the current interval: pay 0, keep the stamp
      action 'pay'    — pay `cycles` (1..5) and advance the stamp by exactly the
                        cycles consumed (remainder carries into the next window)
    """
    if not last:
        return "seed", 0, now.isoformat()
    try:
        last_dt = datetime.fromisoformat(last)
        elapsed = (now - last_dt).total_seconds()
    except (TypeError, ValueError):
        return "reseed", 0, now.isoformat()
    if elapsed > PASSIVE_CATCHUP_MAX_SECONDS:
        return "reseed", 0, now.isoformat()
    if elapsed < PASSIVE_INTERVAL_SECONDS:
        return "wait", 0, last
    cycles = min(int(elapsed // PASSIVE_INTERVAL_SECONDS), 5)
    new_last = last_dt + timedelta(seconds=cycles * PASSIVE_INTERVAL_SECONDS)
    return "pay", cycles, new_last.isoformat()

_rcon_players_cache = {"ts": 0, "ids": set(), "names": set()}


async def _rcon_online_players():
    """Cached (10s) set of connected Steam64 ids + lowercased in-game names from RCON."""
    import time as _t
    if rcon_client.is_configured() and (_t.time() - _rcon_players_cache["ts"] < 10):
        return _rcon_players_cache["ids"], _rcon_players_cache["names"]
    ids, names = set(), set()
    if rcon_client.is_configured():
        try:
            for p in await rcon_client.player_list():
                if p.get("steam_id"):
                    ids.add(str(p["steam_id"]).strip())
                if p.get("name"):
                    names.add(str(p["name"]).strip().lower())
            _rcon_players_cache.update({"ts": _t.time(), "ids": ids, "names": names})
        except Exception as e:
            logger.warning(f"RCON player list failed: {e}")
            return _rcon_players_cache["ids"], _rcon_players_cache["names"]
    return ids, names


async def _is_user_in_game(user) -> bool:
    """Real presence via RCON: is this user's Steam account connected to the game server?
    Falls back to the web active_dino proxy only when RCON is unavailable."""
    if not rcon_client.is_configured():
        return bool(user.get("active_dino"))
    ids, names = await _rcon_online_players()
    sid = str(user.get("steam_id") or "").strip()
    if sid and sid in ids:
        return True
    pname = (user.get("persona_name") or "").strip().lower()
    return bool(pname and pname in names)


async def _credit_playtime(user, now):
    """Grant PrimeMeat for elapsed in-game time (gated by passive_last_at). Applies Patreon boost. Returns (awarded, effective_reward)."""
    mult = _payout_multiplier(user)
    eff = int(round(PASSIVE_REWARD * mult))
    last = user.get("passive_last_at")
    action, cycles, new_last_iso = _passive_pay_plan(last, now)
    if action == "seed":
        # Filter on the unseeded state so two first ticks racing seed only once
        # ($in None matches missing and null; "" covers any legacy empty value).
        await db.users.update_one({"id": user["id"], "passive_last_at": {"$in": [None, ""]}}, {"$set": {
            "passive_last_at": new_last_iso,
            "pm_session_start": user.get("pm_session_start") or now.isoformat(),
        }})
        return 0, eff
    if action == "reseed":
        logger.info(f"[passive] reseed for {user.get('persona_name')}: unverifiable gap since {last!r} - backlog NOT paid")
        await db.users.update_one({"id": user["id"], "passive_last_at": last},
                                  {"$set": {"passive_last_at": new_last_iso, "pm_session_start": now.isoformat()},
                                   "$unset": {"pm_session_earned": ""}})
        return 0, eff
    if action == "wait":
        return 0, eff
    # Multiplier event boost: while an event is active for the player's CURRENT
    # species, the whole payout scales by the event value. Applied inside the
    # same CAS-guarded write so concurrent tabs can never double-boost; any
    # failure in the boost lookup degrades to the normal payout, never blocks it.
    boost_mult, boost_ev = 1, None
    try:
        boost_mult, boost_ev = await _playtime_boost(user)
    except Exception as e:
        logger.warning(f"[multx] boost lookup failed (base pay continues): {e}")
    awarded = cycles * eff * max(1, int(boost_mult))
    set_fields = {"passive_last_at": new_last_iso}
    if not user.get("pm_session_start"):
        set_fields["pm_session_start"] = last
    # CAS on the exact prior stamp: concurrent tabs both ticking could pay the
    # same window twice (observed in prod tx, 0.0s gap) — only one writer wins.
    res = await db.users.update_one(
        {"id": user["id"], "passive_last_at": last},
        {"$inc": {"coins": awarded, "pm_payout_total": awarded, "pm_session_earned": awarded},
         "$set": set_fields})
    if res.modified_count == 0:
        logger.info(f"[passive] duplicate tick lost CAS for {user.get('persona_name')} - window already paid")
        return 0, eff
    label = f"PrimeMeat por tiempo de juego ({cycles}x)"
    if boost_ev:
        label += f" · {boost_ev.get('title') or 'Evento'} x{boost_mult}"
        logger.info(f"[multx] boost x{boost_mult} applied to {user.get('persona_name')} "
                    f"({boost_ev.get('species')}): {awarded} PrimeMeat")
    await add_transaction(user["id"], "normal", awarded, "reward", label)
    await _track_quest_progress(user["id"], "play_time", cycles * (PASSIVE_INTERVAL_SECONDS // 60))
    try:
        await battle_pass.hook_passive_xp(user["id"], cycles)
    except Exception as e:
        logger.warning("[bp] hook failed: %r", e)
    # Leaderboard: the SAME verified cycles the payout just paid (the CAS write
    # above already de-duplicated concurrent tabs, so this can never double-count).
    await _lb_bump(user["id"], playtime_seconds=cycles * PASSIVE_INTERVAL_SECONDS)
    return awarded, eff


@api_router.post("/economy/passive-tick")
async def passive_tick(user=Depends(get_current_user)):
    # Players earn PrimeMeat every 4 minutes while connected in-game (real RCON presence). Patreon tiers multiply the reward.
    in_game = await _is_user_in_game(user)
    now = datetime.now(timezone.utc)
    mult = _payout_multiplier(user)
    eff = int(round(PASSIVE_REWARD * mult))
    base = {"in_game": in_game, "interval_seconds": PASSIVE_INTERVAL_SECONDS, "reward": eff,
            "base_reward": PASSIVE_REWARD, "multiplier": mult}
    if not in_game:
        # End the current play session (keep lifetime total). passive_last_at is
        # cleared too: an offline player must never keep an open pay window, or
        # the gap until their next join would be credited as play time.
        if user.get("pm_session_start") or user.get("passive_last_at"):
            await db.users.update_one({"id": user["id"]}, {"$unset": {
                "pm_session_start": "", "pm_session_earned": "", "passive_last_at": ""}})
        return {**base, "seconds_remaining": PASSIVE_INTERVAL_SECONDS, "awarded": 0,
                "total_earned": user.get("pm_payout_total", 0), "session_earned": 0}
    awarded, eff = await _credit_playtime(user, now)
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "coins": 1, "pm_payout_total": 1, "pm_session_earned": 1, "passive_last_at": 1})
    last = (fresh or {}).get("passive_last_at")
    remaining = PASSIVE_INTERVAL_SECONDS
    if last:
        remaining = max(0, int(PASSIVE_INTERVAL_SECONDS - (now - datetime.fromisoformat(last)).total_seconds()))
    return {**base, "seconds_remaining": remaining, "awarded": awarded,
            "coins": (fresh or {}).get("coins", user.get("coins")),
            "total_earned": (fresh or {}).get("pm_payout_total", 0),
            "session_earned": (fresh or {}).get("pm_session_earned", 0)}


@api_router.get("/payout/status")
async def payout_status(user=Depends(get_current_user)):
    in_game = await _is_user_in_game(user)
    now = datetime.now(timezone.utc)
    mult = _payout_multiplier(user)
    eff = int(round(PASSIVE_REWARD * mult))
    last = user.get("passive_last_at")
    remaining = PASSIVE_INTERVAL_SECONDS
    if in_game and last:
        try:
            remaining = max(0, int(PASSIVE_INTERVAL_SECONDS - (now - datetime.fromisoformat(last)).total_seconds()))
        except (TypeError, ValueError):
            remaining = PASSIVE_INTERVAL_SECONDS
    session_seconds = None
    if in_game and user.get("pm_session_start"):
        try:
            session_seconds = int((now - datetime.fromisoformat(user["pm_session_start"])).total_seconds())
        except Exception:
            session_seconds = None
    return {
        "in_game": in_game,
        "interval_seconds": PASSIVE_INTERVAL_SECONDS,
        "base_reward": PASSIVE_REWARD,
        "multiplier": mult,
        "reward_per_tick": eff,
        "per_hour": int(round(eff * (3600 / PASSIVE_INTERVAL_SECONDS))),
        "seconds_remaining": remaining,
        "session_earned": user.get("pm_session_earned", 0) if in_game else 0,
        "session_seconds": session_seconds,
        "total_earned": user.get("pm_payout_total", 0),
        "coins": user.get("coins", 0),
        "tier_key": _patreon_tier_key(user.get("patreon_tier_name")) if user.get("patreon_patron_status") == "active_patron" else None,
    }


# ---------- daily login gift (7-day streak) ----------
# Days 1-4 pay PrimeMeat + XP, days 5-7 pay Amberium + XP. Days 3/5/7 also grant a
# Dino Egg (special = egg tier) — one of the two ways to win eggs (the other is crates).
GIFT_SCHEDULE = [
    {"day": 1, "coins": 300,  "vip": 0,  "xp": 50,  "special": None},
    {"day": 2, "coins": 500,  "vip": 0,  "xp": 75,  "special": None},
    {"day": 3, "coins": 800,  "vip": 0,  "xp": 100, "special": "common"},
    {"day": 4, "coins": 1200, "vip": 0,  "xp": 150, "special": None},
    {"day": 5, "coins": 0,    "vip": 15, "xp": 200, "special": "uncommon"},
    {"day": 6, "coins": 0,    "vip": 25, "xp": 275, "special": None},
    {"day": 7, "coins": 0,    "vip": 50, "xp": 400, "special": "rare"},
]


_gift_schedule = None


async def gift_schedule_value():
    global _gift_schedule
    if _gift_schedule is None:
        doc = await db.settings.find_one({"_id": "gift_schedule"})
        _gift_schedule = doc["schedule"] if (doc and doc.get("schedule")) else [dict(g) for g in GIFT_SCHEDULE]
    return _gift_schedule


def _gift_reward_for(sched, day: int) -> dict:
    return next((g for g in sched if g["day"] == day), sched[0])


def _gift_compute(user):
    """Return (display_streak, next_day, claimed_today) from the user's stored gift state.
    display_streak is the number of days already secured in the *current* active streak
    (resets to 0 when the streak is broken or a new 7-day cycle is starting)."""
    today = datetime.now(timezone.utc).date()
    streak = int(user.get("gift_streak", 0) or 0)
    last_str = user.get("last_gift_date")
    last = None
    if last_str:
        try:
            last = date.fromisoformat(last_str)
        except ValueError:
            last = None
    claimed_today = last == today
    if claimed_today:
        next_day = streak
        display = streak
    elif last == today - timedelta(days=1) and streak < 7:
        next_day = streak + 1          # continue the streak
        display = streak
    else:
        next_day = 1                   # first claim, missed a day, or new cycle after 7
        display = 0
    return display, next_day, claimed_today


@api_router.get("/gift/status")
async def gift_status(user=Depends(get_current_user)):
    streak, next_day, claimed_today = _gift_compute(user)
    schedule = []
    for g in await gift_schedule_value():
        sp = cosmetics_data.EGGS.get(g["special"]) if g.get("special") else None
        schedule.append({
            "day": g["day"], "coins": g["coins"], "vip": g["vip"], "xp": g["xp"],
            "special": sp["name"] if sp else None,
        })
    return {
        "streak": streak, "next_day": next_day,
        "can_claim": not claimed_today, "claimed_today": claimed_today,
        "schedule": schedule,
    }


@api_router.post("/gift/claim")
async def gift_claim(user=Depends(get_current_user)):
    streak, next_day, claimed_today = _gift_compute(user)
    if claimed_today:
        raise HTTPException(status_code=400, detail="Ya reclamaste tu regalo de hoy. Vuelve mañana.")
    reward = _gift_reward_for(await gift_schedule_value(), next_day)
    today = datetime.now(timezone.utc).date()
    inc = {"xp": reward["xp"]}
    if reward["coins"]:
        inc["coins"] = reward["coins"]
    if reward["vip"]:
        inc["vip_coins"] = reward["vip"]
    # Same claim as the daily reward: the date stamp is what makes today's gift
    # unrepeatable, so it has to move in the SAME write that pays it. ($ne also
    # matches a row that has never claimed, so a first-time claim still passes.)
    took = await db.users.update_one(
        {"id": user["id"], "last_gift_date": {"$ne": today.isoformat()}},
        {"$inc": inc, "$set": {"gift_streak": next_day, "last_gift_date": today.isoformat()}})
    if took.modified_count == 0:
        raise HTTPException(status_code=400, detail="Ya reclamaste tu regalo de hoy. Vuelve mañana.")
    if reward["coins"]:
        await add_transaction(user["id"], "normal", reward["coins"], "reward", f"Login gift — Día {next_day}")
    if reward["vip"]:
        await add_transaction(user["id"], "vip", reward["vip"], "reward", f"Login gift — Día {next_day}")

    special = None
    sp = cosmetics_data.EGGS.get(reward["special"]) if reward["special"] else None
    if sp:
        await _grant_egg(user["id"], sp["tier"])
        special = {"label": sp["name"], "image": sp["image"]}

    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {
        "success": True, "day": next_day, "streak": next_day,
        "reward": {"coins": reward["coins"], "vip": reward["vip"], "xp": reward["xp"], "special": special},
        "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"], "xp": fresh.get("xp", 0)},
    }


# ---------- chat cosmetics (Decorations) ----------
class EquipCosmeticInput(BaseModel):
    category: str
    id: Optional[str] = None


async def _owned_eggs(user_id):
    docs = await db.inventory.find({"user_id": user_id, "category": "Eggs"}, {"_id": 0}).to_list(200)
    counts = {}
    for d in docs:
        counts[d.get("tier")] = counts.get(d.get("tier"), 0) + d.get("quantity", 1)
    return counts


async def _grant_egg(user_id, tier):
    """Add one Dino Egg of the given tier to a user's inventory (won, never bought)."""
    egg = cosmetics_data.EGGS.get(tier)
    if not egg:
        return
    existing = await db.inventory.find_one({"user_id": user_id, "category": "Eggs", "tier": tier})
    if existing:
        await db.inventory.update_one({"id": existing["id"]}, {"$inc": {"quantity": 1}, "$set": {"acquired_at": now_iso()}})
    else:
        await db.inventory.insert_one({
            "id": new_id(), "user_id": user_id, "item_id": egg["id"], "name": egg["name"],
            "category": "Eggs", "rarity": egg["rarity"], "image": egg["image"], "tier": tier,
            "quantity": 1, "order": 9999, "acquired_at": now_iso(),
        })


def _egg_tiers_view(counts):
    out = []
    for t in cosmetics_data.EGG_TIERS:
        e = cosmetics_data.EGGS[t]
        out.append({"tier": t, "id": e["id"], "name": e["name"], "rarity": e["rarity"],
                    "color": e["color"], "image": e["image"], "odds": cosmetics_data.egg_odds(t),
                    "owned": counts.get(t, 0)})
    return out


@api_router.get("/cosmetics/catalog")
async def cosmetics_catalog(user=Depends(get_current_user)):
    owned = set(user.get("cosmetics_owned") or [])
    eq = user.get("cosmetics_equipped") or {}
    items = [{**d, "owned": d["id"] in owned, "equipped": eq.get(d["category"]) == d["id"]}
             for d in cosmetics_data.DECORATIONS]
    counts = await _owned_eggs(user["id"])
    return {
        "rarities": cosmetics_data.DECO_RARITY,
        "categories": cosmetics_data.CATEGORIES,
        "items": items,
        "equipped": {k: eq.get(k) for k in COSMETIC_EQUIP_SLOTS},
        "eggs": _egg_tiers_view(counts),
    }


@api_router.post("/cosmetics/equip")
async def cosmetics_equip(data: EquipCosmeticInput, user=Depends(get_current_user)):
    if data.category not in COSMETIC_EQUIP_SLOTS:
        raise HTTPException(status_code=400, detail="Esta categoría no se puede equipar")
    if data.id:
        d = cosmetics_data.DECO_BY_ID.get(data.id)
        if not d or d["category"] != data.category:
            raise HTTPException(status_code=404, detail="Decoración no encontrada")
        if data.id not in set(user.get("cosmetics_owned") or []):
            raise HTTPException(status_code=403, detail="No posees esta decoración")
    eq = dict(user.get("cosmetics_equipped") or {})
    eq[data.category] = data.id  # None clears the slot
    await db.users.update_one({"id": user["id"]}, {"$set": {"cosmetics_equipped": eq}})
    return {"success": True, "equipped": {k: eq.get(k) for k in COSMETIC_EQUIP_SLOTS}}


@api_router.get("/cosmetics/eggs")
async def cosmetics_eggs(user=Depends(get_current_user)):
    counts = await _owned_eggs(user["id"])
    return {"eggs": _egg_tiers_view(counts)}


@api_router.get("/cosmetics/emotes")
async def cosmetics_emotes(user=Depends(get_current_user)):
    owned = set(user.get("cosmetics_owned") or [])
    emotes = [{"id": d["id"], "name": d["name"], "rarity": d["rarity"],
               "emote": d["emote"], "code": d["code"], "pack": d.get("pack", "react"),
               "owned": d["id"] in owned}
              for d in cosmetics_data.items_by_category("emote")]
    return {"packs": cosmetics_data.EMOTE_PACKS, "emotes": emotes}


@api_router.get("/cosmetics/egg/{tier}/pool")
async def cosmetics_egg_pool(tier: str, user=Depends(get_current_user)):
    if tier not in cosmetics_data.EGGS:
        raise HTTPException(status_code=404, detail="Huevo inválido")
    egg = cosmetics_data.EGGS[tier]
    owned = set(user.get("cosmetics_owned") or [])
    total = sum(w for _, w in egg["buckets"])
    buckets = []
    for b, w in egg["buckets"]:
        if b == "coins":
            continue  # coins are a drop but not shown as a cosmetic "pool" entry
        chance = round(w / total * 100, 2)
        items = cosmetics_data.ITEMS_BY_RARITY.get(b, [])
        buckets.append({
            "kind": "rarity", "rarity": b, "chance": chance,
            "color": cosmetics_data.DECO_RARITY[b]["color"], "count": len(items),
            "per_item": round(chance / max(1, len(items)), 4),
            "items": [{**it, "category": it["category"], "owned": it["id"] in owned} for it in items],
        })
    return {"tier": tier, "name": egg["name"], "color": egg["color"], "buckets": buckets}


def _egg_reward_view(entry):
    if entry["type"] == "coins":
        return {"type": "coins", "label": f"{entry['amount']:,} PrimeMeat", "amount": entry["amount"],
                "rarity": entry["rarity"], "image": seed_data.COIN_NORMAL}
    d = cosmetics_data.DECO_BY_ID[entry["id"]]
    return {"type": "decoration", **d, "label": d["name"]}


class EggOpenInput(BaseModel):
    tier: str


@api_router.post("/cosmetics/egg/open")
async def cosmetics_egg_open(data: EggOpenInput, user=Depends(get_current_user)):
    tier = data.tier
    if tier not in cosmetics_data.EGGS:
        raise HTTPException(status_code=400, detail="Huevo inválido")
    egg = cosmetics_data.EGGS[tier]
    # Consume one egg as an ATOMIC CLAIM. Reading the row and deleting it afterwards
    # lets several opens share one egg -- every racer draws a reward from a single
    # item. The $gte guard also means the quantity can never go negative.
    inv = await db.inventory.find_one_and_update(
        {"user_id": user["id"], "category": "Eggs", "tier": tier, "quantity": {"$gte": 1}},
        {"$inc": {"quantity": -1}}, return_document=ReturnDocument.AFTER)
    if not inv:
        raise HTTPException(status_code=400, detail="No tienes este huevo. Consíguelos en cajas o el login diario.")
    if int(inv.get("quantity") or 0) <= 0:
        await db.inventory.delete_one({"id": inv["id"], "quantity": {"$lte": 0}})

    seed = await _pf_get_active(user["id"])
    nonce = seed["nonce"]
    roll_b = _pf_float(seed["server_seed"], seed["client_seed"], nonce)
    roll_i = _pf_float_i(seed["server_seed"], seed["client_seed"], nonce, 1)
    winner = cosmetics_data.egg_draw(tier, roll_b, roll_i)
    await db.pf_seeds.update_one({"id": seed["id"]}, {"$inc": {"nonce": 1}})
    proof = {"server_seed_hash": seed["server_seed_hash"], "client_seed": seed["client_seed"],
             "nonce": nonce, "roll": round(roll_b, 8)}

    rv = _egg_reward_view(winner)
    duplicate, refund = False, 0
    if winner["type"] == "coins":
        await db.users.update_one({"id": user["id"]}, {"$inc": {"coins": winner["amount"]}})
        await add_transaction(user["id"], "normal", winner["amount"], "reward", f"{egg['name']} — PrimeMeat")
    else:
        owned = set(user.get("cosmetics_owned") or [])
        if winner["id"] in owned:
            duplicate = True
            refund = max(1, cosmetics_data.DECO_RARITY[winner["rarity"]]["value"] // 4)
            await db.users.update_one({"id": user["id"]}, {"$inc": {"coins": refund}})
            await add_transaction(user["id"], "normal", refund, "reward", f"Duplicado: {rv['label']}")
        else:
            await db.users.update_one({"id": user["id"]}, {"$addToSet": {"cosmetics_owned": winner["id"]}})
    rv["duplicate"], rv["refund"] = duplicate, refund

    await db.unboxings.insert_one({
        "id": new_id(), "user_id": user["id"], "user_name": user.get("persona_name"),
        "case_id": egg["id"], "case_name": egg["name"], "reward": rv,
        "fairness": proof, "created_at": now_iso(),
    })
    if rv["type"] == "decoration" and rv["rarity"] in ("Epic", "Legendary", "Apex") and not duplicate:
        await db.chat_messages.insert_one({
            "id": new_id(), "user_id": "system", "name": user.get("persona_name") or "Survivor",
            "avatar": user.get("avatar"), "role": "system", "channel": "feed",
            "text": f"consiguió {rv['name']} ({rv['rarity']}) de un {egg['name']}",
            "win": {"game": "egg", "rarity": rv["rarity"], "kind": "crate"},
            "created_at": now_iso(),
        })

    reel_len, win_index = 60, 54
    reel = [_egg_reward_view(cosmetics_data.egg_random_entry(tier)) for _ in range(reel_len)]
    reel[win_index] = rv
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    counts = await _owned_eggs(user["id"])
    return {"reward": rv, "reel": reel, "win_index": win_index, "fairness": proof,
            "coins": fresh["coins"], "owned_count": len(fresh.get("cosmetics_owned") or []),
            "eggs": _egg_tiers_view(counts)}




# ---------- dinosaurs ----------
@api_router.get("/dinosaurs")
async def list_dinosaurs(diet: Optional[str] = None, search: Optional[str] = None):
    q = {}
    if diet and diet != "all":
        q["type"] = diet
    items = await db.dinosaurs.find(q, {"_id": 0}).to_list(200)
    if search:
        s = search.lower()
        items = [d for d in items if s in d["name"].lower() or s in d["description"].lower()]
    return items


@api_router.get("/dinosaurs/{slug}")
async def get_dinosaur(slug: str):
    d = await db.dinosaurs.find_one({"slug": slug}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Dinosaurio no encontrado")
    return d


# ---------- store ----------
@api_router.get("/store/categories")
async def store_categories():
    cats = await db.store_items.distinct("category")
    return ["All"] + sorted(cats)


@api_router.get("/store/items")
async def store_items(category: Optional[str] = None, search: Optional[str] = None,
                      currency: Optional[str] = None):
    q = {}
    if category and category not in ("All", "all"):
        q["category"] = category
    if currency and currency in ("normal", "vip"):
        q["currency"] = currency
    items = await db.store_items.find(q, {"_id": 0}).to_list(200)
    if search:
        s = search.lower()
        items = [i for i in items if s in i["name"].lower() or s in i["description"].lower()]
    # enrich dino items with type/diet from the roster (for category filtering & labels)
    slugs = [i["dino_slug"] for i in items if i.get("dino_slug")]
    if slugs:
        dinos = await db.dinosaurs.find({"slug": {"$in": slugs}}, {"_id": 0, "slug": 1, "type": 1, "diet": 1}).to_list(200)
        dmap = {d["slug"]: d for d in dinos}
        for i in items:
            d = dmap.get(i.get("dino_slug"))
            if d:
                i["type"] = d.get("type")
                i["diet"] = d.get("diet")
    return items


@api_router.post("/store/purchase")
async def purchase(data: PurchaseInput, user=Depends(get_current_user)):
    item = await db.store_items.find_one({"id": data.item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    cur = item["currency"]
    bal_field = "coins" if cur == "normal" else "vip_coins"
    if user.get(bal_field, 0) < item["price"]:
        raise HTTPException(status_code=400, detail="Fondos insuficientes (Insufficient balance)")
    # CONDITIONAL DEBIT. The check above reads `user`, which is a REQUEST-TIME
    # SNAPSHOT -- two purchases fired at the same instant both saw the same
    # balance, and the plain `$inc` that used to sit here applied both, driving
    # the balance negative and handing out two items for the price of one. The
    # balance guard has to live in the same atomic write as the decrement.
    price = int(item["price"])
    if price > 0:
        paid = await db.users.update_one({"id": user["id"], bal_field: {"$gte": price}},
                                         {"$inc": {bal_field: -price}})
        if paid.modified_count == 0:
            raise HTTPException(status_code=400, detail="Fondos insuficientes (Insufficient balance)")
    await add_transaction(user["id"], cur, -item["price"], "purchase", f"Purchased {item['name']}")
    inv = {
        "id": new_id(), "user_id": user["id"], "item_id": item["id"], "name": item["name"],
        "category": item["category"], "rarity": item["rarity"], "image": item["image"],
        "quantity": 1, "acquired_at": now_iso(),
    }
    if item["category"] == "Skins":
        inv["uses"] = SKIN_USES_PER_GRANT
    if item.get("dino_slug"):
        inv["dino_slug"] = item["dino_slug"]
    await db.inventory.insert_one(inv)
    await db.purchases.insert_one({
        "id": new_id(), "user_id": user["id"], "item_id": item["id"], "name": item["name"],
        "price": item["price"], "currency": cur, "created_at": now_iso(),
    })
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {"success": True, "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]}}


# How long two IDENTICAL cart submissions from the same player are treated as
# one order. Long enough to swallow a double click, a client retry or a proxy
# replay; short enough that deliberately buying the same cart again still works.
STORE_ORDER_DEDUPE_SECS = float(os.environ.get("LIN_STORE_ORDER_DEDUPE_SECS", "30"))


def _store_order_key(user_id, lines) -> str:
    """Stable identity for one cart submission: this player, these items, these
    quantities. Sorted, so the order the client happens to list the items in
    cannot produce two different keys for the same cart."""
    parts = sorted("%s:%d" % (str(i.get("id")), int(q)) for i, q in lines)
    raw = "%s|%s" % (str(user_id), "|".join(parts))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@api_router.post("/store/checkout")
async def checkout(data: CheckoutInput, user=Depends(get_current_user)):
    if not data.items:
        raise HTTPException(status_code=400, detail="El carrito esta vacio")
    # fetch items and compute totals per currency
    lines = []
    totals = {"normal": 0, "vip": 0}
    for ci in data.items:
        qty = max(1, ci.quantity)
        item = await db.store_items.find_one({"id": ci.item_id}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail=f"Item no encontrado: {ci.item_id}")
        lines.append((item, qty))
        totals[item["currency"]] += item["price"] * qty
    # Fast refusal off the request-time snapshot: cheap, and it keeps the two
    # distinct currency messages. It is NOT the guard -- see the debit below.
    if user.get("coins", 0) < totals["normal"]:
        raise HTTPException(status_code=400, detail="PrimeMeat insuficiente (Insufficient Survival Coins)")
    if user.get("vip_coins", 0) < totals["vip"]:
        raise HTTPException(status_code=400, detail="Amberium insuficiente (Insufficient VIP currency)")

    # ---- idempotency wall ----
    # Nothing made this route replay-safe: a double click, a client retry or a
    # proxy replay ran the whole body twice, debiting twice and granting the
    # cart twice. The order key is claimed BEFORE any money moves, the way
    # botcore economy.apply_delta_locked writes its UNIQUE ledger row first --
    # the claim, not a read, is what makes the second attempt harmless.
    order_key = _store_order_key(user["id"], lines)
    now_ts = time.time()
    claimed = True
    try:
        await db.store_orders.insert_one({
            "_id": order_key, "user_id": user["id"], "created_at": now_ts, "seq": 0,
            "status": "claimed", "total": dict(totals), "created_iso": now_iso(),
        })
    except DuplicateKeyError:
        # This exact cart has been submitted before. Re-claim ONLY if that claim
        # is older than the dedupe window; the conditional update IS the race
        # wall, so of two simultaneous replays exactly one can win it.
        prior = await db.store_orders.find_one_and_update(
            {"_id": order_key, "created_at": {"$lt": now_ts - STORE_ORDER_DEDUPE_SECS}},
            {"$set": {"created_at": now_ts, "status": "claimed"}, "$inc": {"seq": 1}},
            return_document=ReturnDocument.AFTER)
        claimed = prior is not None
    if not claimed:
        # REPLAY. Answer in the route's own shape with the recorded result and
        # the live balance. Not one coin moves a second time.
        rec = await db.store_orders.find_one({"_id": order_key}) or {}
        fresh_r = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or {}
        logger.info("[STOREORDER] replay suppressed user=%s key=%s normal=%s vip=%s",
                    user["id"], order_key[:16], totals["normal"], totals["vip"])
        return {"success": True, "purchased": list(rec.get("purchased") or []),
                "total": rec.get("total") or totals,
                "balance": {"coins": fresh_r.get("coins", 0),
                            "vip_coins": fresh_r.get("vip_coins", 0)}}

    # ---- conditional debit ----
    # ONE atomic operation carrying the balance guard for BOTH currencies. The
    # old code checked the snapshot above and then applied an unconditional
    # `$inc`: N carts submitted at the same instant all passed the check and all
    # debited, driving the balance negative and handing out N carts for the
    # price of one. Both currencies move in the same write, so a partial debit
    # (coins taken, Amberium short) is impossible. A currency with a zero total
    # contributes no filter key -- `{"$gte": 0}` would not match a user document
    # that has never had that field.
    inc, guard = {}, {"id": user["id"]}
    if totals["normal"]:
        inc["coins"] = -totals["normal"]
        guard["coins"] = {"$gte": totals["normal"]}
    if totals["vip"]:
        inc["vip_coins"] = -totals["vip"]
        guard["vip_coins"] = {"$gte": totals["vip"]}
    if inc:
        charged = await db.users.find_one_and_update(guard, {"$inc": inc})
        if charged is None:
            # Short AT THE MOMENT OF THE WRITE. Release the claim so a genuine
            # retry after topping up is not mistaken for a replay, then refuse
            # without having moved anything.
            await db.store_orders.update_one(
                {"_id": order_key}, {"$set": {"created_at": 0.0, "status": "insufficient"}})
            cur_u = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or {}
            if cur_u.get("vip_coins", 0) < totals["vip"]:
                raise HTTPException(status_code=400, detail="Amberium insuficiente (Insufficient VIP currency)")
            raise HTTPException(status_code=400, detail="PrimeMeat insuficiente (Insufficient Survival Coins)")
    purchased = []
    for item, qty in lines:
        cur = item["currency"]
        await add_transaction(user["id"], cur, -item["price"] * qty, "purchase",
                              f"Purchased {item['name']}" + (f" x{qty}" if qty > 1 else ""))
        await db.purchases.insert_one({
            "id": new_id(), "user_id": user["id"], "item_id": item["id"], "name": item["name"],
            "price": item["price"] * qty, "currency": cur, "quantity": qty, "created_at": now_iso(),
        })
        existing = await db.inventory.find_one({"user_id": user["id"], "item_id": item["id"]})
        is_skin = item["category"] == "Skins"
        if existing:
            inc = {"uses": SKIN_USES_PER_GRANT * qty} if is_skin else {"quantity": qty}
            await db.inventory.update_one({"id": existing["id"]}, {"$inc": inc, "$set": {"acquired_at": now_iso()}})
        else:
            doc = {
                "id": new_id(), "user_id": user["id"], "item_id": item["id"], "name": item["name"],
                "category": item["category"], "rarity": item["rarity"], "image": item["image"],
                "quantity": qty, "order": 9999, "acquired_at": now_iso(),
            }
            if is_skin:
                doc["uses"] = SKIN_USES_PER_GRANT * qty
            if item.get("dino_slug"):
                doc["dino_slug"] = item["dino_slug"]
            await db.inventory.insert_one(doc)
        purchased.append(item["name"])
    # Settle the order record: a replay inside the window now echoes THIS result
    # instead of re-running the body.
    await db.store_orders.update_one(
        {"_id": order_key},
        {"$set": {"status": "done", "purchased": purchased, "total": dict(totals),
                  "completed_at": now_iso()}})
    logger.info("[STOREORDER] checkout ok user=%s key=%s items=%s normal=%s vip=%s",
                user["id"], order_key[:16], len(lines), totals["normal"], totals["vip"])
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {"success": True, "purchased": purchased, "total": totals,
            "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]}}


# Dino purchase tiers: BOTH deliver at 75% growth, Prime included (owner ruling
# 2026-07-16: a store-bought dino redeems at 75%, never full-grown; Prime keeps
# its stat multipliers, surcharge and 6 mutation slots). Env override
# LIN_STORE_DINO_GROWTH (percent, clamped 1-100; blank/garbage falls back to 75
# with a warning so a bad value can never brick boot or zero a spawn).
# Prime costs a flat surcharge above the (admin-editable) normal price.
PRIME_SURCHARGE = 1000

def _store_dino_growth_pct() -> int:
    raw = (os.environ.get("LIN_STORE_DINO_GROWTH") or "").strip()
    if not raw:
        return 75
    try:
        return max(1, min(100, int(float(raw))))
    except (TypeError, ValueError):
        logging.warning("[store] LIN_STORE_DINO_GROWTH=%r invalid; using 75", raw)
        return 75

STORE_DINO_GROWTH = _store_dino_growth_pct()
DINO_TIERS = {
    "basic": {"label": "Basic", "max_mutations": 3, "growth": STORE_DINO_GROWTH},
    "prime": {"label": "Prime", "max_mutations": 6, "growth": STORE_DINO_GROWTH},
}

# Official Prime bonuses. PRIME_STAT_MULT applies both when BUYING a Prime-tier
# dino and via Set Prime; PRIME_GROWTH applies ONLY to the live Set Prime
# promotion — store purchases deliver at DINO_TIERS growth.
PRIME_GROWTH = 100  # live Set Prime promotes to full-grown
PRIME_STAT_MULT = {"health": 1.20, "stamina": 1.15, "speed": 1.10, "weight": 1.25, "damage": 1.20}

def _apply_prime_stats(base_stats):
    bs = base_stats or {}
    return {
        "health": round(bs.get("health", 100) * PRIME_STAT_MULT["health"]),
        "stamina": round(bs.get("stamina", 100) * PRIME_STAT_MULT["stamina"]),
        "speed": round(bs.get("speed", 60) * PRIME_STAT_MULT["speed"]),
        "weight": round(bs.get("weight", 1000) * PRIME_STAT_MULT["weight"]),
        "damage": round(bs.get("damage", 50) * PRIME_STAT_MULT["damage"]),
    }


# A purchased dino goes into the REAL vault (La Boveda). Until 2026-07-15 it was
# inserted into db.inventory and "redeemed" by /active-dino/deploy, which wrote
# Mongo and nothing else -- it never sent the mod a command, so a bought dino
# never existed in-game (reported 2026-07-15: "i bought a dino from store and
# redeem it is not working"). Purchases now go through the same
# vault.save_parked() that /adddino and the marketplace already use, and the
# player redeems from La Boveda through the vault lane, which is what spawns.
_EVRIMA_CLASS_BY_SLUG = {slug: f"BP_{species}_C"
                         for species, slug in game_telemetry.EVRIMA_SPECIES.items()}

_OWN_MUT_SEGMENTS = 4     # parked_dinos.mutations        -> slots n1..n4
_PARENT_MUT_SEGMENTS = 4  # parked_dinos.parent_mutations -> slots p1..p4


def _store_mutation_segments(own_keys: list, parent_keys: list, dino_class: str):
    """Store mutation KEYS -> (mutations, parent_mutations) "|" strings.

    Own picks fill n1..n4 and parent picks p1..p4 -- the same 16-slot model
    mutation_catalog and the mutation editor use, so a purchased row is
    indistinguishable from a parked one downstream. Rejects a mutation the
    species cannot carry: the old lane only checked that the key existed, so a
    Triceratops could be sold Hematophagy.
    """
    allowed = mutation_catalog.allowed_names_for_class(dino_class)

    def canon(keys, limit):
        out = []
        for key in keys:
            name = MUTATIONS_BY_KEY[key]["name"]
            c = mutation_catalog.canonical_mutation_name(name)
            if not c:
                raise HTTPException(status_code=400, detail=f"Mutacion desconocida: {name}")
            if c not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"{name} no esta disponible para un {_bare_species(dino_class)}.")
            out.append(c)
        if len(out) > limit:
            raise HTTPException(status_code=400, detail="Demasiadas mutaciones para esta especie.")
        return out

    own = canon(own_keys, _OWN_MUT_SEGMENTS)
    parent = canon(parent_keys, _PARENT_MUT_SEGMENTS)

    def pad(xs, n):
        return mutation_catalog.join_segments(xs + ["None"] * (n - len(xs)))

    return pad(own, _OWN_MUT_SEGMENTS), pad(parent, _PARENT_MUT_SEGMENTS)


@api_router.post("/store/purchase-dino")
async def purchase_dino(data: PurchaseDinoInput, user=Depends(get_current_user)):
    tier = DINO_TIERS.get(data.tier)
    if not tier:
        raise HTTPException(status_code=400, detail="Nivel invalido")
    item = await db.store_items.find_one({"id": data.item_id}, {"_id": 0})
    if not item or item.get("category") != "Dinosaurs":
        raise HTTPException(status_code=404, detail="Dinosaurio no encontrado en la tienda")
    slug = item.get("dino_slug")
    if not slug:
        raise HTTPException(status_code=400, detail="Este item de tienda no es un dinosaurio desplegable")
    sid = _steam_id_or_400(user)
    dino_class = _EVRIMA_CLASS_BY_SLUG.get(slug)
    if not dino_class:
        raise HTTPException(status_code=400,
                            detail="Esa especie no esta disponible en el servidor de juego.")

    # De-dupe within AND across both pickers, then charge the tier's cap against
    # the TOTAL -- the UI offers 3 own + 3 parent, which is exactly Prime's 6.
    own_keys = list(dict.fromkeys(data.mutations))
    parent_keys = [k for k in dict.fromkeys(data.parents) if k not in own_keys]
    total = len(own_keys) + len(parent_keys)
    if total > tier["max_mutations"]:
        raise HTTPException(
            status_code=400,
            detail=f"Los dinos {tier['label']} permiten hasta {tier['max_mutations']} mutaciones (elegiste {total}).")
    invalid = [m for m in own_keys + parent_keys if m not in MUTATIONS_BY_KEY]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Mutacion(es) desconocida(s) (unknown): {', '.join(invalid)}")
    mut_own, mut_parent = _store_mutation_segments(own_keys, parent_keys, dino_class)

    is_prime = data.tier == "prime"
    growth_pct = tier["growth"]

    # Capacity is checked BEFORE the debit so a full vault never eats the price;
    # save_parked re-checks under BEGIN EXCLUSIVE and we refund on that race.
    cap = _user_park_cap(user)
    if cap > 0 and await asyncio.to_thread(vault.count_parked, sid) >= cap:
        raise HTTPException(
            status_code=400,
            detail=f"Tu Boveda esta llena ({cap}). Recupera o libera un dino antes de comprar otro.")

    cur = item["currency"]
    bal_field = "coins" if cur == "normal" else "vip_coins"
    price = item["price"] + (PRIME_SURCHARGE if is_prime else 0)
    res = await db.users.update_one({"id": user["id"], bal_field: {"$gte": price}},
                                    {"$inc": {bal_field: -price}})
    if res.modified_count == 0:
        raise HTTPException(status_code=400, detail="Fondos insuficientes (Insufficient balance)")

    # Vitals are deliberately absent (stored 0). Zero is the mod's admin-add
    # sentinel: ApplyAllStats (main.full.lua) fills health/stamina/thirst from
    # the LIVE post-growth GetMax* and computes max_hunger = GetMaxHealth x
    # species ratio, writing SetMaxHunger before SetHunger so current can never
    # exceed max (no regurgitate). Storing maxes here would strand the dino at
    # stale/low vitals -- the working owner sends 0 for exactly this reason
    # (donor dino.py), and it is the same path /adddino has always used.
    pd = {
        "dino": dino_class,
        "growth": max(0, min(100, int(growth_pct))) / 100.0,
        "is_prime": is_prime,
        "is_elder": is_prime,
        "mutations": mut_own,
        "parent_mutations": mut_parent,
        "elder_mutations": "",
        # NO elder_stacks KEY, ON PURPOSE. A store dino has never been entombed,
        # so save_parked's int(_num(None)) = 0 is the truth about it. This dict
        # briefly carried a derived count so the editor would open the "Linaje
        # Parental" slots the player had just paid for -- but elder_stacks is not
        # an editor field: vault._run_redeem sends this column to the mod, which
        # writes ElderReplicationStacks (main.full.lua :9910, :9918), so storing
        # 1 here would hand every store purchase an in-game elder replication
        # stack nobody asked for and nothing can take back. The editor problem is
        # solved where it belongs, at READ time, in mutation_catalog._entomb_state
        # (the parent column proves the lineage step); the game keeps seeing 0.
    }
    # A PRIME SOLD HERE IS PRIME WHEN IT ARRIVES. Without this the row landed
    # is_prime=1 with prime_conditions/prime_route_mig/prime_route_pat NULL, and
    # the mod plans its prime restore leg off the MASK -- so the dino the player
    # paid a surcharge for redeemed as an ordinary animal. No-op for a basic buy.
    pd = vault.mint_prime_state(pd)
    discord_id = await asyncio.to_thread(vault.resolve_discord_id, sid)
    try:
        row_id = await asyncio.to_thread(vault.save_parked, sid, discord_id, pd, cap)
    except Exception:
        logging.getLogger("laislanublar.vault").exception(
            "[vault] store purchase save_parked crashed sid=%s slug=%s", sid, slug)
        row_id = None
    if row_id is None:
        await db.users.update_one({"id": user["id"]}, {"$inc": {bal_field: price}})
        raise HTTPException(
            status_code=400,
            detail="No se pudo guardar el dino en tu Boveda. No se te ha cobrado; intentalo de nuevo.")

    label = f"{item['name'].replace(' Slot', '')} ({tier['label']})"
    await add_transaction(user["id"], cur, -price, "purchase", f"Purchased {label}")
    await db.purchases.insert_one({
        "id": new_id(), "user_id": user["id"], "item_id": item["id"], "name": label,
        "price": price, "currency": cur, "created_at": now_iso(),
    })
    logging.getLogger("laislanublar.vault").info(
        "[store] dino delivered to vault sid=%s slug=%s tier=%s growth=%d%% row=%s",
        sid, slug, data.tier, growth_pct, row_id)
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {"success": True, "tier": data.tier, "price": price,
            "growth_pct": growth_pct,
            "mutations": own_keys, "parents": parent_keys,
            "delivered_to": "vault", "vault_dino_id": row_id,
            "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]}}


# ---------- economy ----------
@api_router.get("/economy/summary")
async def economy_summary(user=Depends(get_current_user)):
    txs = await db.transactions.find({"user_id": user["id"]}, {"_id": 0}).to_list(2000)
    earned_normal = sum(t["amount"] for t in txs if t["currency"] == "normal" and t["amount"] > 0)
    spent_normal = sum(-t["amount"] for t in txs if t["currency"] == "normal" and t["amount"] < 0)
    earned_vip = sum(t["amount"] for t in txs if t["currency"] == "vip" and t["amount"] > 0)
    spent_vip = sum(-t["amount"] for t in txs if t["currency"] == "vip" and t["amount"] < 0)
    return {
        "coins": user.get("coins", 0), "vip_coins": user.get("vip_coins", 0),
        "earned_normal": earned_normal, "spent_normal": spent_normal,
        "earned_vip": earned_vip, "spent_vip": spent_vip,
        "transaction_count": len(txs),
    }


@api_router.get("/economy/transactions")
async def transactions(currency: Optional[str] = None, ttype: Optional[str] = None,
                       user=Depends(get_current_user)):
    q = {"user_id": user["id"]}
    if currency in ("normal", "vip"):
        q["currency"] = currency
    if ttype and ttype != "all":
        q["type"] = ttype
    txs = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return txs


@api_router.get("/economy/chart")
async def economy_chart(user=Depends(get_current_user)):
    txs = await db.transactions.find({"user_id": user["id"]}, {"_id": 0}).to_list(2000)
    days = {}
    for i in range(6, -1, -1):
        d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        days[d] = {"date": d, "normal": 0, "vip": 0}
    for t in txs:
        d = t["created_at"][:10]
        if d in days:
            key = "normal" if t["currency"] == "normal" else "vip"
            days[d][key] += t["amount"]
    return list(days.values())


# ---------- inventory ----------
@api_router.get("/inventory")
async def inventory(user=Depends(get_current_user)):
    items = await db.inventory.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
    items.sort(key=lambda x: (x.get("order", 9999), x.get("acquired_at", "")))
    return items


@api_router.post("/inventory/reorder")
async def inventory_reorder(data: ReorderInput, user=Depends(get_current_user)):
    for idx, inv_id in enumerate(data.ids):
        await db.inventory.update_one({"id": inv_id, "user_id": user["id"]}, {"$set": {"order": idx}})
    return {"success": True}


@api_router.delete("/inventory/{inv_id}")
async def release_inventory_item(inv_id: str, user=Depends(get_current_user)):
    """Release (permanently delete) an inventory item — used to free up dinos."""
    res = await db.inventory.delete_one({"id": inv_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item no encontrado en tu inventario")
    return {"success": True}


@api_router.post("/inventory/dino/{inv_id}/mutations")
async def edit_dino_mutations(inv_id: str, data: MutationEditInput, user=Depends(get_current_user)):
    """Edit the mutations of a parked dino (only inventory dinos; the live dino cannot be edited)."""
    item = await db.inventory.find_one({"id": inv_id, "user_id": user["id"], "category": "Dinosaurs"}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Dinosaurio no encontrado en tu inventario")
    muts = list(dict.fromkeys(data.mutations))
    cap = _tier_mut_cap(item.get("tier"))
    if len(muts) > cap:
        raise HTTPException(status_code=400, detail=f"Este dino permite up to {cap} mutations")
    invalid = [m for m in muts if m not in MUTATIONS_BY_KEY]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Mutacion(es) desconocida(s) (unknown): {', '.join(invalid)}")
    await db.inventory.update_one({"id": inv_id}, {"$set": {"mutations": muts}})
    return {"success": True, "mutations": muts, "max": cap}


@api_router.post("/inventory/dino/{inv_id}/rename")
async def rename_dino(inv_id: str, data: DinoRenameInput, user=Depends(get_current_user)):
    """Give a parked inventory dino a custom name (used as the default listing title when sold/auctioned)."""
    item = await db.inventory.find_one({"id": inv_id, "user_id": user["id"], "category": "Dinosaurs"}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Dinosaurio no encontrado en tu inventario")
    name = (data.name or "").strip()[:40]
    await db.inventory.update_one({"id": inv_id}, {"$set": {"custom_name": name or None}})
    return {"success": True, "custom_name": name or None}


# The Isle Evrima mutation groups. Child (lifecycle) unlock by growth; Elder sets unlock via Entomb.
MUTATION_GROUP_KEYS = ["child", "parent", "elder_a", "elder_b"]
CHILD_GROWTH_REQ_PRIME = [20, 50, 100, 100]   # official Evrima lifecycle stages (Juvenile/Sub-adult/Adult); Prime gets a 4th at Adult
CHILD_GROWTH_REQ_BASE = [20, 50, 100]         # 3 lifecycle slots: Juvenile 20%, Sub-adult 50%, Adult 100%
PARENT_SLOTS = 4
ELDER_SLOTS = 4
MAX_ENTOMB_GEN = 2                          # Gen 1 unlocks Elder Set A, Gen 2 unlocks Set B


def _dino_growth(item: dict) -> float:
    return float(item.get("saved_growth", item.get("growth", 0)) or 0)


def _mut_slot_unlocked(gk: str, i: int, is_prime: bool, growth: float, entomb: int) -> bool:
    if gk == "child":
        reqs = CHILD_GROWTH_REQ_PRIME if is_prime else CHILD_GROWTH_REQ_BASE
        return i < len(reqs) and growth >= reqs[i]
    if gk == "parent":
        return i < PARENT_SLOTS
    if gk == "elder_a":
        return is_prime and entomb >= 1 and i < ELDER_SLOTS
    if gk == "elder_b":
        return is_prime and entomb >= 2 and i < ELDER_SLOTS
    return False


def _mut_group_counts(is_prime: bool) -> dict:
    child = len(CHILD_GROWTH_REQ_PRIME if is_prime else CHILD_GROWTH_REQ_BASE)
    return {"child": child, "parent": PARENT_SLOTS, "elder_a": ELDER_SLOTS, "elder_b": ELDER_SLOTS}


@api_router.post("/inventory/dino/{inv_id}/mutation-groups")
async def edit_dino_mutation_groups(inv_id: str, data: MutationGroupsInput, user=Depends(get_current_user)):
    """Edit a parked dino's grouped mutations. Child slots gate on growth; Elder sets gate on Entomb generation."""
    item = await db.inventory.find_one({"id": inv_id, "user_id": user["id"], "category": "Dinosaurs"}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Dinosaurio no encontrado en tu inventario")
    is_prime = bool(item.get("prime")) or item.get("tier") == "prime"
    growth = _dino_growth(item)
    entomb = int(item.get("entomb_count", 0) or 0)
    counts = _mut_group_counts(is_prime)
    clean, flat = {}, []
    for gk in MUTATION_GROUP_KEYS:
        n = counts[gk]
        incoming = list(data.groups.get(gk) or [])
        out = [None] * n
        for i in range(n):
            k = incoming[i] if i < len(incoming) else None
            if k and k in MUTATIONS_BY_KEY and _mut_slot_unlocked(gk, i, is_prime, growth, entomb) and k not in flat:
                out[i] = k
                flat.append(k)
        clean[gk] = out
    await db.inventory.update_one({"id": inv_id}, {"$set": {"mutation_groups": clean, "mutations": flat}})
    return {"success": True, "mutation_groups": clean, "mutations": flat, "entomb_count": entomb, "growth": growth}


@api_router.post("/inventory/dino/{inv_id}/entomb")
async def entomb_dino(inv_id: str, user=Depends(get_current_user)):
    """Entomb a fully-grown Prime Elder: advances the Entomb generation, unlocking an Elder mutation set."""
    item = await db.inventory.find_one({"id": inv_id, "user_id": user["id"], "category": "Dinosaurs"}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Dinosaur not found in your inventory")
    is_prime = bool(item.get("prime")) or item.get("tier") == "prime"
    if not is_prime:
        raise HTTPException(status_code=400, detail="Solo un Prime Elder puede hacer Entomb")
    if _dino_growth(item) < 100:
        raise HTTPException(status_code=400, detail="Debes alcanzar el 100% de crecimiento para hacer Entomb")
    cur = int(item.get("entomb_count", 0) or 0)
    if cur >= MAX_ENTOMB_GEN:
        raise HTTPException(status_code=400, detail=f"Ya alcanzaste la generación máxima de Entomb ({MAX_ENTOMB_GEN})")
    nxt = cur + 1
    # Rebirth: physical growth (and temporary states) reset to a hatchling; evolutionary lineage persists.
    await db.inventory.update_one({"id": inv_id}, {"$set": {"entomb_count": nxt, "saved_growth": 5}})
    return {"success": True, "entomb_count": nxt, "growth": 5, "unlocked": "elder_a" if nxt == 1 else "elder_b"}


# ---------- cases (CS:GO style crates) ----------
import random as _random

SKIN_USES_PER_GRANT = 40  # each skin win/purchase grants this many "uses"; equipping costs 1.
# Won GLITCH skins are consumables too: each win grants this many applies, every
# successful apply spends one, and the skin disappears from the inventory at
# zero (mirrors the universal-skin uses model above). Guarded so a blank or
# zero env value can never brick the apply lane.
GLITCH_USES_PER_WIN = max(1, int(os.environ.get("LIN_GLITCH_USES_PER_WIN") or 25))


def _fmt_es(n):
    """1234567 -> '1.234.567' (Spanish thousands separator)."""
    return f"{int(n):,}".replace(",", ".")


def _reward_view(entry, amount=None):
    """Public view of a pool entry. Range entries (min/max) show the range in
    the pool/odds list; pass `amount` (the rolled or cosmetic reel value) to
    show a concrete figure instead."""
    t = entry["type"]
    if t == "coins":
        out = {"type": "coins", "image": seed_data.COIN_NORMAL,
               "rarity": entry["rarity"], "currency": "normal"}
        if "min" in entry:
            out["min"], out["max"] = entry["min"], entry["max"]
            if amount is not None:
                out["amount"] = int(amount)
                out["label"] = f"{_fmt_es(amount)} PrimeMeat"
            else:
                out["label"] = f"{_fmt_es(entry['min'])} – {_fmt_es(entry['max'])} PrimeMeat"
        else:
            out["amount"] = entry["amount"]
            out["label"] = f"{_fmt_es(entry['amount'])} PrimeMeat"
        return out
    if t == "vip":
        out = {"type": "vip", "image": seed_data.COIN_VIP,
               "rarity": entry["rarity"], "currency": "vip"}
        if "min" in entry:
            out["min"], out["max"] = entry["min"], entry["max"]
            if amount is not None:
                out["amount"] = int(amount)
                out["label"] = f"{_fmt_es(amount)} Amberium"
            else:
                out["label"] = f"{_fmt_es(entry['min'])} – {_fmt_es(entry['max'])} Amberium"
        else:
            out["amount"] = entry["amount"]
            out["label"] = f"{_fmt_es(entry['amount'])} Amberium"
        return out
    if t == "glitch":
        g = glitch_catalog.GLITCH_BY_ID[entry["glitch"]]
        prox = glitch_catalog.design_proximity(g)
        # image "" on purpose: a glitch card is a NAME + COLOUR PROXIMITY,
        # never a picture (fleet order 2026-08-11).
        return {"type": "glitch", "label": g["name"], "image": "",
                "rarity": entry.get("rarity", glitch_catalog.GLITCH_RARITY),
                "glitch": g["id"], "subtitle": g["subtitle"], "accent_hex": g["accent_hex"],
                "proximity": prox["strip"]}
    if t == "egg":
        egg = cosmetics_data.EGGS[entry["tier"]]
        return {"type": "egg", "label": egg["name"], "image": egg["image"],
                "rarity": egg["rarity"], "tier": entry["tier"]}
    skin = seed_data.SKINS[entry["skin"]]
    return {"type": "skin", "label": skin["name"], "image": skin.get("image"),
            "rarity": skin["rarity"], "skin": entry["skin"], "color": skin.get("color")}


def _case_public(case):
    # On-site odds show each drop's RAW typed percent verbatim (seed_data stores it
    # as `percent`); a crate's chances can total != 100 by owner design. Fall back to
    # the normalised weight for any legacy pool entry without a `percent`.
    total = sum(p["weight"] for p in case["pool"]) or 1
    pool = sorted(
        [{**_reward_view(p), "chance": round(p.get("percent", p["weight"] / total * 100), 2)} for p in case["pool"]],
        key=lambda x: x["chance"],
    )
    return {"id": case["id"], "name": case["name"], "description": case["description"],
            "image": case["image"], "price": case["price"], "currency": case["currency"],
            "drops": len(case["pool"]), "pool": pool}


# The /admin Store tab edits the two crate rows in db.store_items ("Common
# Crate" / "Uncommon Crate") — that row is the live source of truth for what
# a crate COSTS. seed_data.CASES keeps the reward pools and the fallback price.
_CASE_STORE_NAME = {"common": "Common Crate", "uncommon": "Uncommon Crate"}


async def _case_live_pricing(case):
    """(price, currency) for a crate — admin-edited store row wins, seed is
    the fallback. Price floors at 1 so a typo can never mint free crates."""
    price, currency = case["price"], case["currency"]
    name = _CASE_STORE_NAME.get(case["id"])
    if name:
        row = await db.store_items.find_one(
            {"name": name, "category": "Crates"}, {"_id": 0, "price": 1, "currency": 1})
        if row:
            try:
                price = max(1, int(row.get("price", price)))
            except (TypeError, ValueError):
                pass
            if row.get("currency") in ("normal", "vip"):
                currency = row["currency"]
    return price, currency


@api_router.get("/cases")
async def list_cases():
    out = []
    for c in seed_data.CASES:
        pub = _case_public(c)
        pub["price"], pub["currency"] = await _case_live_pricing(c)
        pub["opened"] = await db.unboxings.count_documents({"case_id": c["id"]})
        out.append(pub)
    return out


# ---------- Provably Fair (CS:GO style) ----------
def _pf_hash(server_seed: str) -> str:
    return hashlib.sha256(server_seed.encode()).hexdigest()


def _pf_float(server_seed: str, client_seed: str, nonce: int) -> float:
    """Deterministic roll in [0,1) from HMAC-SHA256(server_seed, client_seed:nonce)."""
    msg = f"{client_seed}:{nonce}".encode()
    digest = hmac.new(server_seed.encode(), msg, hashlib.sha256).hexdigest()
    return int(digest[:13], 16) / float(1 << 52)


def _pf_float_i(server_seed: str, client_seed: str, nonce: int, i: int) -> float:
    msg = f"{client_seed}:{nonce}:{i}".encode()
    digest = hmac.new(server_seed.encode(), msg, hashlib.sha256).hexdigest()
    return int(digest[:13], 16) / float(1 << 52)


def _pf_shuffle(items, floats):
    a = list(items)
    n = len(a)
    for i in range(n - 1, 0, -1):
        j = int(floats[n - 1 - i] * (i + 1))
        if j > i:
            j = i
        a[i], a[j] = a[j], a[i]
    return a


def _pf_pick(pool, weights, roll: float):
    """Pick a pool entry using the [0,1) roll against cumulative weights."""
    total = sum(weights)
    target = roll * total
    acc = 0.0
    for entry, w in zip(pool, weights):
        acc += w
        if target < acc:
            return entry
    return pool[-1]


async def _pf_get_active(user_id: str):
    seed = await db.pf_seeds.find_one({"user_id": user_id, "active": True}, {"_id": 0})
    if not seed:
        seed = await _pf_create(user_id)
    return seed


async def _pf_create(user_id: str, client_seed: str = None):
    server_seed = secrets.token_hex(32)
    doc = {
        "id": new_id(), "user_id": user_id,
        "server_seed": server_seed, "server_seed_hash": _pf_hash(server_seed),
        "client_seed": client_seed or secrets.token_hex(8),
        "nonce": 0, "active": True, "revealed": False, "created_at": now_iso(),
    }
    await db.pf_seeds.insert_one(doc)
    return doc


def _pf_public(seed, reveal=False):
    out = {
        "server_seed_hash": seed["server_seed_hash"],
        "client_seed": seed["client_seed"],
        "nonce": seed["nonce"],
    }
    if reveal:
        out["server_seed"] = seed["server_seed"]
    return out


@api_router.get("/fairness/current")
async def fairness_current(user=Depends(get_current_user)):
    seed = await _pf_get_active(user["id"])
    return _pf_public(seed)


class ClientSeedInput(BaseModel):
    client_seed: str = Field(..., min_length=1, max_length=64)


@api_router.post("/fairness/client-seed")
async def fairness_set_client_seed(data: ClientSeedInput, user=Depends(get_current_user)):
    seed = await _pf_get_active(user["id"])
    cs = re.sub(r"[^A-Za-z0-9_\-]", "", data.client_seed)[:64] or secrets.token_hex(8)
    await db.pf_seeds.update_one({"id": seed["id"]}, {"$set": {"client_seed": cs}})
    seed["client_seed"] = cs
    return _pf_public(seed)


class RotateInput(BaseModel):
    client_seed: Optional[str] = None


@api_router.post("/fairness/rotate")
async def fairness_rotate(data: RotateInput = RotateInput(), user=Depends(get_current_user)):
    """Reveal the current server seed (for verification) and start a fresh pair."""
    old = await _pf_get_active(user["id"])
    await db.pf_seeds.update_one({"id": old["id"]}, {"$set": {"active": False, "revealed": True, "revealed_at": now_iso()}})
    new_client = data.client_seed if data and data.client_seed else None
    fresh = await _pf_create(user["id"], client_seed=new_client)
    return {
        "revealed": _pf_public(old, reveal=True) | {"rolls_used": old["nonce"]},
        "current": _pf_public(fresh),
    }


class VerifyInput(BaseModel):
    server_seed: str
    client_seed: str
    nonce: int


@api_router.post("/fairness/verify")
async def fairness_verify(data: VerifyInput):
    roll = _pf_float(data.server_seed, data.client_seed, data.nonce)
    return {
        "server_seed_hash": _pf_hash(data.server_seed),
        "roll": round(roll, 8),
        "client_seed": data.client_seed,
        "nonce": data.nonce,
    }


CRATE_NAME_TO_CASE = {"common crate": "common", "uncommon crate": "uncommon"}


async def _grant_case_reward(user, case):
    """Pick a winner using the player's provably-fair seed, grant it, log the unboxing
    and return the reel payload + fairness proof. Any price is charged by the caller."""
    pool = case["pool"]
    if not pool:  # defence-in-depth: callers guard before charging, this stops an IndexError
        raise HTTPException(status_code=503, detail="Esta caja no está disponible ahora mismo")
    weights = [p["weight"] for p in pool]

    # provably-fair draw
    seed = await _pf_get_active(user["id"])
    nonce = seed["nonce"]
    roll = _pf_float(seed["server_seed"], seed["client_seed"], nonce)
    winner = _pf_pick(pool, weights, roll)
    await db.pf_seeds.update_one({"id": seed["id"]}, {"$inc": {"nonce": 1}})
    proof = {
        "server_seed_hash": seed["server_seed_hash"],
        "client_seed": seed["client_seed"],
        "nonce": nonce,
        "roll": round(roll, 8),
    }

    # Range rewards roll the exact amount with a second provably-fair float
    # (same seed pair + nonce, sub-index 1) so both the pick AND the amount
    # are verifiable from the revealed seed.
    won_amount = None
    if winner["type"] in ("coins", "vip") and "min" in winner:
        amt_roll = _pf_float_i(seed["server_seed"], seed["client_seed"], nonce, 1)
        span = int(winner["max"]) - int(winner["min"]) + 1
        won_amount = int(winner["min"]) + min(span - 1, int(amt_roll * span))
        proof["amount_roll"] = round(amt_roll, 8)

    rv = _reward_view(winner, amount=won_amount)
    if winner["type"] == "coins":
        amt = won_amount if won_amount is not None else winner["amount"]
        await db.users.update_one({"id": user["id"]}, {"$inc": {"coins": amt}})
        await add_transaction(user["id"], "normal", amt, "reward", f"{case['name']} reward")
    elif winner["type"] == "vip":
        amt = won_amount if won_amount is not None else winner["amount"]
        await db.users.update_one({"id": user["id"]}, {"$inc": {"vip_coins": amt}})
        await add_transaction(user["id"], "vip", amt, "reward", f"{case['name']} reward")
    elif winner["type"] == "glitch":
        gid = winner["glitch"]
        g = glitch_catalog.GLITCH_BY_ID[gid]
        # Atomic upsert keyed on the unique (user_id, glitch_id) index —
        # concurrent wins of the same skin both land as quantity increments.
        await db.reward_skins.update_one(
            {"user_id": user["id"], "glitch_id": gid},
            {"$inc": {"quantity": 1, "uses": GLITCH_USES_PER_WIN},
             "$set": {"last_won_at": now_iso(), "source": case["name"]},
             "$setOnInsert": {
                 "id": new_id(), "name": g["name"], "subtitle": g["subtitle"],
                 "image": g["preview"], "accent_hex": g["accent_hex"],
                 "rarity": rv["rarity"], "acquired_at": now_iso(),
             }},
            upsert=True)
    elif winner["type"] == "egg":
        await _grant_egg(user["id"], winner["tier"])
    else:
        skin_key = winner["skin"]
        item_id = f"skin_{skin_key}"
        existing = await db.inventory.find_one({"user_id": user["id"], "item_id": item_id})
        if existing:
            await db.inventory.update_one({"id": existing["id"]}, {"$inc": {"uses": SKIN_USES_PER_GRANT}, "$set": {"acquired_at": now_iso()}})
        else:
            await db.inventory.insert_one({
                "id": new_id(), "user_id": user["id"], "item_id": item_id, "name": rv["label"],
                "category": "Skins", "rarity": rv["rarity"], "image": rv["image"],
                "color": rv.get("color"), "skin_key": skin_key,
                "universal": True, "quantity": 1, "uses": SKIN_USES_PER_GRANT, "order": 9999, "acquired_at": now_iso(),
            })
    # record the unboxing for history (with fairness proof)
    await db.unboxings.insert_one({
        "id": new_id(), "user_id": user["id"], "user_name": user.get("persona_name"),
        "case_id": case["id"], "case_name": case["name"], "reward": rv,
        "fairness": proof, "created_at": now_iso(),
    })
    # feed: broadcast only hard-to-get pulls (Epic+ rarity) to keep chat controlled
    if rv.get("rarity") in ("Epic", "Legendary", "Mythic", "Apex"):
        await db.chat_messages.insert_one({
            "id": new_id(), "user_id": "system", "name": user.get("persona_name") or "Survivor",
            "avatar": user.get("avatar"), "role": "system", "channel": "feed",
            "text": f"unboxed {rv.get('label')} from {case['name']}",
            "win": {"game": "crate", "rarity": rv.get("rarity"), "kind": "crate"},
            "created_at": now_iso(),
        })
    # build a CS:GO-style reel with the winner near the end. Reel entries are
    # cosmetic only — range rewards get a display-only random amount so the
    # strip varies; the authoritative amount is the provably-fair one above.
    reel_len = 60
    win_index = 54

    def _reel_view(entry):
        if entry["type"] in ("coins", "vip") and "min" in entry:
            return _reward_view(entry, amount=_random.randint(entry["min"], entry["max"]))
        return _reward_view(entry)

    reel = [_reel_view(_random.choices(pool, weights=weights, k=1)[0]) for _ in range(reel_len)]
    reel[win_index] = rv
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {
        "reward": rv, "reel": reel, "win_index": win_index, "fairness": proof,
        "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]},
    }


@api_router.post("/cases/{case_id}/open")
async def open_case(case_id: str, user=Depends(get_current_user)):
    case = next((c for c in seed_data.CASES if c["id"] == case_id), None)
    if not case:
        raise HTTPException(status_code=404, detail="Caja no encontrada")
    # Guard an empty pool BEFORE charging (a crate whose CRATE_DROPS lines were all
    # invalid builds to pool=[]): never debit a player for a crate that can't pay out.
    if not case["pool"]:
        raise HTTPException(status_code=503, detail="Esta caja no está disponible ahora mismo")
    price, cur = await _case_live_pricing(case)
    field = "coins" if cur == "normal" else "vip_coins"
    # Atomic conditional charge: the $gte guard makes parallel opens race-safe
    # (a plain check-then-$inc could drive the balance negative).
    charged = await db.users.update_one(
        {"id": user["id"], field: {"$gte": price}}, {"$inc": {field: -price}})
    if charged.modified_count != 1:
        raise HTTPException(status_code=400, detail="Fondos insuficientes para abrir esta caja (Insufficient balance)")
    await add_transaction(user["id"], cur, -price, "purchase", f"Opened {case['name']}")
    return await _grant_case_reward(user, case)


class BulkOpenInput(BaseModel):
    count: int = Field(1, ge=1, le=5)


@api_router.post("/cases/{case_id}/open-bulk")
async def open_case_bulk(case_id: str, data: BulkOpenInput, user=Depends(get_current_user)):
    """Open up to 5 crates in a single action. Each draw uses the provably-fair seed
    with an incrementing nonce, so every result stays independently verifiable."""
    case = next((c for c in seed_data.CASES if c["id"] == case_id), None)
    if not case:
        raise HTTPException(status_code=404, detail="Caja no encontrada")
    if not case["pool"]:
        raise HTTPException(status_code=503, detail="Esta caja no está disponible ahora mismo")
    count = max(1, min(5, data.count))
    price, cur = await _case_live_pricing(case)
    field = "coins" if cur == "normal" else "vip_coins"
    total = price * count
    # Atomic conditional charge (see open_case).
    charged = await db.users.update_one(
        {"id": user["id"], field: {"$gte": total}}, {"$inc": {field: -total}})
    if charged.modified_count != 1:
        raise HTTPException(status_code=400, detail=f"Fondos insuficientes para abrir {count} cajas (Insufficient balance)")
    await add_transaction(user["id"], cur, -total, "purchase", f"Opened {count}× {case['name']}")
    results = []
    for _ in range(count):
        results.append(await _grant_case_reward(user, case))
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {
        "count": count,
        "rewards": [r["reward"] for r in results],
        "reels": [{"reel": r["reel"], "win_index": r["win_index"], "reward": r["reward"]} for r in results],
        "reel": results[-1]["reel"], "win_index": results[-1]["win_index"],
        "fairness": [r["fairness"] for r in results],
        "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]},
    }


@api_router.post("/inventory/open-crate")
async def open_crate_from_inventory(data: EquipSkinInput, user=Depends(get_current_user)):
    """Open a crate the player already owns in their inventory (no extra charge)."""
    item = await db.inventory.find_one(
        {"id": data.inv_id, "user_id": user["id"], "category": "Crates"}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Caja no encontrada en tu inventario")
    case_id = CRATE_NAME_TO_CASE.get(item.get("name", "").strip().lower())
    case = next((c for c in seed_data.CASES if c["id"] == case_id), None)
    if not case:
        raise HTTPException(status_code=400, detail="Esta caja ya no se puede abrir")
    if not case["pool"]:
        raise HTTPException(status_code=503, detail="Esta caja no está disponible ahora mismo")
    # Consume one crate as an ATOMIC CLAIM -- the paid crate routes charge with a
    # conditional $inc for exactly this reason, and a free crate is worth the same
    # rewards. Every refusal above happens before anything is spent.
    taken = await db.inventory.find_one_and_update(
        {"id": item["id"], "user_id": user["id"], "category": "Crates", "quantity": {"$gte": 1}},
        {"$inc": {"quantity": -1}}, return_document=ReturnDocument.AFTER)
    if not taken:
        raise HTTPException(status_code=404, detail="Caja no encontrada en tu inventario")
    if int(taken.get("quantity") or 0) <= 0:
        await db.inventory.delete_one({"id": item["id"], "quantity": {"$lte": 0}})
    return await _grant_case_reward(user, case)


@api_router.get("/profile/unboxings")
async def my_unboxings(user=Depends(get_current_user)):
    items = await db.unboxings.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


# ---------- reward skins (glitch skins won from crates) ----------
# Won glitch skins are stored per-user in db.reward_skins and applied to the
# LIVE in-game dino through the mod's skin_commands.json IPC. This lane is
# entitlement-gated by OWNERSHIP (the player won the skin), deliberately NOT
# by Patreon — the Patreon gate covers the free-form skin editor only.
_REWARD_APPLY_COOLDOWN_SECONDS = 30.0
_reward_apply_last: dict = {}
_reward_apply_lock = threading.Lock()


async def _grant_prize_skin(user_id: str, glitch_id: str, source: str) -> bool:
    """Grant one catalog glitch design to a player as a PRIZE (season
    leaderboard rank; 2026-08-16). Same atomic upsert shape as the crate win at
    `_grant_case_reward` — keyed on the unique (user_id, glitch_id) index, so a
    player who already owns the design gets another quantity + use allowance
    instead of a duplicate-key crash.

    Returns False on an unknown id rather than raising: a caller that already
    claimed its payment marker must not be turned into an exception by a
    retired design, and the id is import-gated at `leaderboards` anyway.
    `image` is deliberately taken from the catalog's retired-to-"" preview, so
    a grant doc can never carry a render URL back onto a card."""
    g = glitch_catalog.GLITCH_BY_ID.get(glitch_id)
    if not g:
        logger.error("[rewards] prize skin %r is not in the catalog", glitch_id)
        return False
    await db.reward_skins.update_one(
        {"user_id": user_id, "glitch_id": glitch_id},
        {"$inc": {"quantity": 1, "uses": GLITCH_USES_PER_WIN},
         "$set": {"last_won_at": now_iso(), "source": source},
         "$setOnInsert": {
             "id": new_id(), "name": g["name"], "subtitle": g["subtitle"],
             "image": g["preview"], "accent_hex": g["accent_hex"],
             "rarity": glitch_catalog.GLITCH_RARITY, "acquired_at": now_iso(),
         }},
        upsert=True)
    return True


def _reward_skin_public(r: dict) -> dict:
    view = {k: r.get(k) for k in (
        "glitch_id", "name", "subtitle", "accent_hex", "rarity",
        "quantity", "acquired_at", "last_won_at", "source")}
    # A glitch card is a NAME + COLOUR PROXIMITY, never a picture (fleet order
    # 2026-08-11). `image` is forced "" AT THE BOUNDARY so a stored render URL
    # from an old grant doc can never resurface; `proximity` joins live from
    # the catalog (an unknown/retired id degrades to an accent-only strip).
    g = glitch_catalog.GLITCH_BY_ID.get(r.get("glitch_id"))
    prox = glitch_catalog.design_proximity(g) if g else {
        "accent": r.get("accent_hex") or "#7CA842", "strip": []}
    view["image"] = ""
    view["proximity"] = prox["strip"]
    # Rows won before the use-limit existed carry no counter yet; render the
    # same allowance the lazy heal in the apply lane will write (25 per win).
    view["uses"] = r.get("uses", GLITCH_USES_PER_WIN * max(1, int(r.get("quantity") or 1)))
    return view


@api_router.get("/me/rewards/skins")
async def my_reward_skins(user=Depends(get_current_user)):
    items = await db.reward_skins.find({"user_id": user["id"]}, {"_id": 0}).sort("acquired_at", 1).to_list(200)
    return {"skins": [_reward_skin_public(r) for r in items],
            "catalog_count": len(glitch_catalog.GLITCH_SKINS)}


class RewardSkinApplyIn(BaseModel):
    glitch_id: str = Field(min_length=1, max_length=64)
    # Picked body layout (the engine's region-layout index): 0..2 or absent.
    # Absent = the skin's authored layout, byte-identical to before this field
    # existed. Out-of-domain never folds — pydantic refuses it before any use
    # is spent (a player must not receive a layout nobody chose).
    pattern: int | None = Field(default=None, ge=0, le=2)


def _live_female_or_none(actor_name: str):
    """Live in-game sex from the mod's skin snapshot. The mod WRITES the
    command's female field into CustomizerData, so an apply MUST carry the
    dino's current sex — fail closed (None) when it can't be determined."""
    snap = game_ipc.read_skin_snapshot(actor_name)
    if isinstance(snap, dict):
        fv = snap.get("female")
        if isinstance(fv, bool):
            return fv
        if isinstance(fv, int) and fv in (0, 1):
            return bool(fv)
    return None


async def _refund_reward_skin_use(user_id: str, glitch_id: str, owned: dict):
    """Give back a reserved use after a failed IPC write. If a concurrent apply
    emptied and deleted the row in the meantime, re-insert it from the pre-apply
    snapshot with the single refunded use (duplicate-key safe: a racing grant
    upsert wins and the refund lands as an increment instead)."""
    try:
        res = await db.reward_skins.update_one(
            {"user_id": user_id, "glitch_id": glitch_id}, {"$inc": {"uses": 1}})
        if res.matched_count == 0:
            doc = {k: v for k, v in owned.items() if k != "_id"}
            doc["uses"] = 1
            try:
                await db.reward_skins.insert_one(doc)
            except Exception:
                await db.reward_skins.update_one(
                    {"user_id": user_id, "glitch_id": glitch_id}, {"$inc": {"uses": 1}})
    except Exception:
        logger.exception("[rewards] use refund failed user=%s glitch=%s", user_id, glitch_id)


# Ghost-paint gate (2026-08-08): the sid->actor registry can serve a PREVIOUS
# life's actor (or a previous boot's) for minutes after a death/respawn; the mod
# paints whatever name it is handed, so the player pays a use and sees nothing.
# When the ENGINE snapshot is fresh and provably lacks the resolved actor, the
# apply refuses BEFORE anything is spent. None/True fail OPEN (a dead snapshot
# writer must never block applies). Receipt line: "[skins] ghost_gate refused".
_GHOST_GATE_MSG = ("Tu dino acaba de cambiar o morir y el mundo aún no refleja el nuevo — "
                   "espera unos segundos y vuelve a intentarlo (no se gastó ningún uso).")


def _ghost_gate_check(sid: str, dino: dict, lane: str) -> None:
    """Raises 409 when the resolved actor is provably absent from the world."""
    if not dino:
        return
    if game_ipc.actor_live_in_engine(dino.get("actor_name")) is False:
        logger.info("[skins] ghost_gate refused sid=%s actor=%s lane=%s",
                    sid, dino.get("actor_name"), lane)
        raise HTTPException(status_code=409, detail=_GHOST_GATE_MSG)


@api_router.post("/me/rewards/skins/apply")
async def apply_reward_skin(data: RewardSkinApplyIn, user=Depends(get_current_user)):
    owned = await db.reward_skins.find_one(
        {"user_id": user["id"], "glitch_id": data.glitch_id}, {"_id": 0})
    if not owned:
        raise HTTPException(status_code=404, detail="No tienes esa skin glitch. Gánala abriendo cajas.")
    # Rows won before the use-limit existed self-heal to the standard allowance
    # (25 per win) on first touch — exactly-once thanks to the $exists filter.
    if "uses" not in owned:
        allowance = GLITCH_USES_PER_WIN * max(1, int(owned.get("quantity") or 1))
        await db.reward_skins.update_one(
            {"user_id": user["id"], "glitch_id": data.glitch_id, "uses": {"$exists": False}},
            {"$set": {"uses": allowance}})
    sid = _steam_id_or_400(user)
    import time as _time
    now_mono = _time.monotonic()
    with _reward_apply_lock:
        last = _reward_apply_last.get(sid, 0.0)
        wait = _REWARD_APPLY_COOLDOWN_SECONDS - (now_mono - last)
        if wait > 0:
            raise HTTPException(status_code=429, detail=f"Espera {max(1, math.ceil(wait))} segundos antes de aplicar otra skin.")
    dino = await asyncio.to_thread(game_ipc.find_active_dino, sid)
    if not dino:
        raise HTTPException(status_code=409, detail="No tienes un dino activo — entra al juego primero.")
    await asyncio.to_thread(_ghost_gate_check, sid, dino, "reward")
    # Sex is resolved by the CONSUMER now: the mod's ProcessCommands honors
    # "preserve_female" and overrides the command value with the live pawn's
    # bIsFemale (fail-closed in the mod when unreadable). skin_snapshots.json
    # is a best-effort subset — a respawned actor is absent until the next
    # snapshot pass (and indefinitely if the snapshot writer dies), so a
    # missing entry must never hard-block the apply. Snapshot value = hint.
    female = await asyncio.to_thread(_live_female_or_none, dino["actor_name"])
    if female is None:
        logger.info("[rewards] glitch apply snapshot_sex=unknown steam_id=%s actor=%s (consumer resolves via preserve_female)",
                    sid, dino["actor_name"])
    cmd = glitch_catalog.build_glitch_command(
        data.glitch_id, dino["actor_name"], dino["class"], sid, bool(female),
        pattern_override=data.pattern)
    if not cmd:
        raise HTTPException(status_code=404, detail="Skin glitch desconocida.")
    cmd["preserve_female"] = True
    # Reserve ONE use atomically BEFORE the IPC write. The $gte guard means two
    # racing applies on the last use can never drive the counter negative, and
    # every earlier exit (429/409/404) happens before anything is spent.
    after = await db.reward_skins.find_one_and_update(
        {"user_id": user["id"], "glitch_id": data.glitch_id, "uses": {"$gte": 1}},
        {"$inc": {"uses": -1}}, return_document=ReturnDocument.AFTER)
    if not after:
        raise HTTPException(status_code=400, detail="Esta skin glitch ya no tiene usos disponibles.")
    uses_left = int(after.get("uses", 0))
    if not await asyncio.to_thread(game_ipc.write_skin_command, cmd):
        # A failed apply never burns a use.
        await _refund_reward_skin_use(user["id"], data.glitch_id, owned)
        raise HTTPException(status_code=500, detail="No se pudo aplicar la skin. Intenta de nuevo.")
    # SkinKeeper capture (GLITCH reward lane) -- SUCCESS path only, never the
    # refund branch above. Keyed on the target sid (cmd['steamid']). preserve_female
    # is carried verbatim in the recipe so a rejoin never sex-flips the dino.
    await asyncio.to_thread(skinkeeper_web.record_apply, cmd, "glitch")
    if uses_left <= 0:
        # Out of uses — the skin disappears from the inventory. Conditional on
        # the counter so a concurrent refund can never be swept away with it.
        await db.reward_skins.delete_one(
            {"user_id": user["id"], "glitch_id": data.glitch_id, "uses": {"$lte": 0}})
    # Cooldown starts only on a SUCCESSFUL apply — the no-dino 409 must stay
    # retryable immediately.
    with _reward_apply_lock:
        _reward_apply_last[sid] = _time.monotonic()
    logger.info("[rewards] glitch apply steam_id=%s glitch=%s actor=%s class=%s uses_left=%d removed=%s",
                sid, data.glitch_id, dino["actor_name"], dino["class"], uses_left, uses_left <= 0)
    return {"ok": True, "actor_name": dino["actor_name"], "class": dino["class"],
            "glitch_id": data.glitch_id, "uses_left": uses_left}


@api_router.get("/profile/purchases")
async def purchase_history(user=Depends(get_current_user)):
    items = await db.purchases.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


# ---------- server status / news / events ----------
_server_status_cache = {"ts": 0, "data": None}


@api_router.get("/server/status")
async def server_status():
    import random, time as _time
    now = datetime.now(timezone.utc)
    next_restart = (now + timedelta(hours=(6 - now.hour % 6), minutes=(60 - now.minute) % 60))
    # Try live RCON data (cached 30s to avoid hammering the game server)
    if rcon_client.is_configured():
        if _server_status_cache["data"] and (_time.time() - _server_status_cache["ts"] < 30):
            live = _server_status_cache["data"]
        else:
            live = None
            try:
                d = await rcon_client.server_details()
                live = {
                    "online": True, "name": d["name"], "map": d["map"],
                    "players": d["players"], "max_players": d["max_players"],
                    "queue": max(0, d["players"] - (d["max_players"] - 10)),
                    "mutations": d["mutations"], "humans": d["humans"],
                    "version": "Evrima 0.16", "next_restart": next_restart.isoformat(),
                    "tickrate": 30, "source": "rcon",
                }
                _server_status_cache.update({"ts": _time.time(), "data": live})
            except Exception as e:
                logger.warning(f"RCON server_status failed: {e}")
                return {
                    "online": False, "name": "Isla Nublar LATAM — Evrima Oficial #1", "map": "Gateway",
                    "players": 0, "max_players": 120, "queue": 0,
                    "uptime_hours": 0, "version": "Evrima 0.16",
                    "next_restart": next_restart.isoformat(), "tickrate": 0, "source": "rcon-error",
                    "mutations": False, "humans": False, "staff_online": [],
                }
        if live:
            return live
    # Fallback: simulated status for local/dev when RCON is not configured.
    seed = int(now.timestamp() // 60)
    random.seed(seed)
    players = random.randint(78, 120)
    return {
        "online": True, "name": "Isla Nublar LATAM — Evrima Oficial #1", "map": "Gateway",
        "players": players, "max_players": 120, "queue": max(0, players - 110),
        "uptime_hours": 312 + (seed % 24), "version": "Evrima 0.16",
        "next_restart": next_restart.isoformat(), "tickrate": 30, "source": "sim",
        "staff_online": [
            {"name": "RexAdmin", "role": "Owner", "status": "online"},
            {"name": "ApexMod", "role": "Moderator", "status": "online"},
            {"name": "RangerK", "role": "Game Master", "status": "idle"},
        ],
    }


class RconAnnounceInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=240)


@api_router.get("/admin/rcon/status")
async def admin_rcon_status(owner=Depends(get_owner_user)):
    if not rcon_client.is_configured():
        return {"configured": False, "online": False}
    try:
        info = await rcon_client.ping()
        return {"configured": True, **info}
    except Exception as e:
        return {"configured": True, "online": False, "error": str(e)}


@api_router.get("/admin/rcon/players")
async def admin_rcon_players(owner=Depends(get_owner_user)):
    if not rcon_client.is_configured():
        raise HTTPException(status_code=400, detail="RCON no configurado")
    try:
        return {"players": await rcon_client.player_list()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RCON error: {e}")


@api_router.post("/admin/rcon/announce")
async def admin_rcon_announce(data: RconAnnounceInput, owner=Depends(get_owner_user)):
    if not rcon_client.is_configured():
        raise HTTPException(status_code=400, detail="RCON no configurado")
    try:
        await rcon_client.announce(data.message.strip())
        await add_log(owner["persona_name"], "rcon_announce", None, {"message": data.message.strip()})
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RCON error: {e}")


@api_router.post("/admin/rcon/save")
async def admin_rcon_save(owner=Depends(get_owner_user)):
    if not rcon_client.is_configured():
        raise HTTPException(status_code=400, detail="RCON no configurado")
    try:
        await rcon_client.save()
        await add_log(owner["persona_name"], "rcon_save", None, {})
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RCON error: {e}")


@api_router.get("/news")
async def news():
    return await db.news.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)


@api_router.get("/events")
async def events():
    return await db.events.find({}, {"_id": 0}).to_list(50)


# ---------- codes (redeem) ----------
DEFAULT_ITEM_IMG = seed_data.COIN_NORMAL


async def apply_reward(user_id: str, reward: dict, source: str):
    """Apply a reward dict to a user. Returns a summary of what was granted."""
    granted = {"coins": 0, "vip_coins": 0, "spins": 0,
               "items": [], "dinos": [], "roles": []}
    coins = int(reward.get("coins", 0) or 0)
    vip = int(reward.get("vip_coins", 0) or 0)
    spins = int(reward.get("spins", 0) or 0)
    if spins < 0 or spins > 100:
        # CodeInput prevents this for every normal write. Keep the payout lane
        # fail-closed as well in case a legacy/manual Mongo row is malformed.
        raise ValueError("code reward spins fuera de rango 0..100")
    inc = {}
    if coins:
        inc["coins"] = coins
        granted["coins"] = coins
    if vip:
        inc["vip_coins"] = vip
        granted["vip_coins"] = vip
    if spins:
        inc["wheel_bonus_spins"] = spins
        granted["spins"] = spins
    if inc:
        await db.users.update_one({"id": user_id}, {"$inc": inc})
    if coins:
        await add_transaction(user_id, "normal", coins, "redeem", f"{source}")
    if vip:
        await add_transaction(user_id, "vip", vip, "redeem", f"{source}")

    for item_id in reward.get("items", []) or []:
        item = await db.store_items.find_one({"id": item_id}, {"_id": 0})
        if item:
            doc = {
                "id": new_id(), "user_id": user_id, "item_id": item["id"], "name": item["name"],
                "category": item["category"], "rarity": item["rarity"], "image": item["image"],
                "quantity": 1, "acquired_at": now_iso(),
            }
            if item["category"] == "Skins":
                doc["uses"] = SKIN_USES_PER_GRANT
            if item.get("dino_slug"):
                doc["dino_slug"] = item["dino_slug"]
            await db.inventory.insert_one(doc)
            granted["items"].append(item["name"])

    for slug in reward.get("dinos", []) or []:
        d = await db.dinosaurs.find_one({"slug": slug}, {"_id": 0})
        if d:
            await db.inventory.insert_one({
                "id": new_id(), "user_id": user_id, "item_id": f"dino_{slug}", "name": f"{d['name']} Slot",
                "category": "Dinosaurs", "rarity": d.get("rarity", "Common"), "image": d["image"],
                "dino_slug": slug, "quantity": 1, "acquired_at": now_iso(),
            })
            granted["dinos"].append(d["name"])

    roles = reward.get("roles", []) or []
    if roles:
        await db.users.update_one({"id": user_id}, {"$addToSet": {"extra_roles": {"$each": roles}}})
        granted["roles"] = roles
    return granted


@api_router.post("/codes/redeem")
async def redeem_code(data: RedeemInput, user=Depends(get_current_user)):
    code_str = data.code.strip().upper()
    code = await db.codes.find_one({"code": code_str})
    if not code:
        raise HTTPException(status_code=404, detail="Codigo invalido")
    if not code.get("active", True):
        raise HTTPException(status_code=400, detail="Este codigo ya no esta activo")
    now = datetime.now(timezone.utc)
    if code.get("start_date"):
        try:
            if now < datetime.fromisoformat(code["start_date"]):
                raise HTTPException(status_code=400, detail="Este codigo todavia no esta activo")
        except ValueError:
            pass
    if code.get("end_date"):
        try:
            if now > datetime.fromisoformat(code["end_date"]):
                raise HTTPException(status_code=400, detail="Este codigo expiro")
        except ValueError:
            pass
    # Validate the stored payload BEFORE claiming either the global or per-user
    # use. A hand-edited/legacy malformed spin reward must not burn a code use
    # and then fail during payout.
    try:
        reward = RewardModel.model_validate(code.get("reward") or {}).model_dump()
    except ValidationError as exc:
        logger.error("code reward invalid code=%s errors=%s", code_str, exc.errors())
        raise HTTPException(status_code=500,
                            detail="Este código tiene una recompensa inválida; no consumió un uso")
    max_uses = code.get("max_uses", 0) or 0
    per_user = code.get("per_user", 1) or 1
    # BOTH limits are claimed, never merely read. Counting redemptions and THEN
    # granting lets several requests fired at the same instant all count zero and
    # all pay out -- on a code worth 1.500.000 PrimeMeat + 5.000 Amberium that is
    # a mint. The per-user counter is a separate document so it stays correct even
    # though code_redemptions has no unique index; `base` is stamped once, on
    # insert, from the redemptions that existed before this lane was hardened, so
    # historical claims still count.
    uses_filter = {"id": code["id"]}
    if max_uses:
        uses_filter["$or"] = [{"uses": {"$exists": False}}, {"uses": {"$lt": max_uses}}]
    took_use = await db.codes.find_one_and_update(uses_filter, {"$inc": {"uses": 1}},
                                                 return_document=ReturnDocument.AFTER)
    if not took_use:
        raise HTTPException(status_code=400, detail="Este codigo alcanzo su limite de usos")
    prior = await db.code_redemptions.count_documents({"code_id": code["id"], "user_id": user["id"]})
    claim_key = "%s:%s" % (code["id"], user["id"])
    try:
        claim = await db.code_claims.find_one_and_update(
            {"_id": claim_key},
            {"$inc": {"n": 1},
             "$setOnInsert": {"base": prior, "code_id": code["id"], "user_id": user["id"]}},
            upsert=True, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        claim = await db.code_claims.find_one_and_update(
            {"_id": claim_key}, {"$inc": {"n": 1}}, return_document=ReturnDocument.AFTER)
    if int(claim.get("base", 0)) + int(claim.get("n", 0)) > per_user:
        # Hand the code use back; the per-user counter is deliberately NOT decremented
        # (it is only ever compared against the limit, so leaving it high keeps this
        # account refused rather than re-opening the race).
        await db.codes.update_one({"id": code["id"]}, {"$inc": {"uses": -1}})
        raise HTTPException(status_code=400, detail="Ya canjeaste este codigo (already redeemed)")

    granted = await apply_reward(user["id"], reward, f"Code: {code['name']}")
    await db.code_redemptions.insert_one({
        "id": new_id(), "code_id": code["id"], "code": code_str, "user_id": user["id"],
        "granted": granted, "created_at": now_iso(),
    })
    await add_log(user["persona_name"], "redeem_code", code_str, {"granted": granted})
    return {"success": True, "granted": granted}


# ---------- admin ----------
@api_router.get("/admin/stats")
async def admin_stats(admin=Depends(get_admin_user)):
    users = await db.users.find({}, {"_id": 0, "coins": 1, "vip_coins": 1}).to_list(100000)
    total_coins = sum(u.get("coins", 0) for u in users)
    total_vip = sum(u.get("vip_coins", 0) for u in users)
    return {
        "users": len(users),
        "coins_in_circulation": total_coins,
        "vip_in_circulation": total_vip,
        "transactions": await db.transactions.count_documents({}),
        "purchases": await db.purchases.count_documents({}),
        "codes": await db.codes.count_documents({}),
        "code_redemptions": await db.code_redemptions.count_documents({}),
        "dinosaurs": await db.dinosaurs.count_documents({}),
        "store_items": await db.store_items.count_documents({}),
    }


# ---------- admin user directory ----------
# 2026-08-09: the Usuarios tab AND the moderation search both read this one
# route, and it used to pull the newest 1000 accounts and filter them in
# Python. On a 1192-account site that made the 192 OLDEST accounts -- the
# founding players, the ones most likely to need a grant, a rank or a sanction
# -- unreachable by any search, while the dashboard's own "Total Users" tile
# read 1192 and contradicted the list. The match now runs in the database over
# the WHOLE collection, and a truncated answer says so on the wire instead of
# looking exactly like "no such player".
ADMIN_USER_LIMIT_DEFAULT = 2000
ADMIN_USER_LIMIT_MAX = 10000


def admin_user_search_query(search: Optional[str]) -> dict:
    """Mongo filter for the admin user directory.

    An absent or all-whitespace needle is the WHOLE directory, never a query
    that matches nothing. The needle is regex-ESCAPED: an admin typing "." or
    "+" or "a|b" is searching for those characters, not writing a pattern that
    would quietly match everyone (or blow up). Discord names are searchable too
    -- staff know a lot of players only by the name in the server.
    """
    s = (search or "").strip()
    if not s:
        return {}
    rx = re.escape(s)
    return {"$or": [
        {"persona_name": {"$regex": rx, "$options": "i"}},
        {"steam_id": {"$regex": rx, "$options": "i"}},
        {"discord_username": {"$regex": rx, "$options": "i"}},
    ]}


def clamp_admin_user_limit(limit) -> int:
    """Row cap: default covers the whole site today with headroom, and a
    garbage or hostile ?limit= falls back to the default instead of erroring or
    handing out the entire collection.

    This is why the route takes ?limit= as a STRING: typed as int, FastAPI
    answers 422 for ?limit=abc before this function is ever reached, and a
    422 in the admin tab reads to staff exactly like the search being broken
    again. Parsing here keeps the promise the battery makes."""
    try:
        n = ADMIN_USER_LIMIT_DEFAULT if limit is None else int(limit)
    except (TypeError, ValueError):
        n = ADMIN_USER_LIMIT_DEFAULT
    return max(1, min(n, ADMIN_USER_LIMIT_MAX))


@api_router.get("/admin/users")
async def admin_users(response: Response, search: Optional[str] = None,
                      limit: Optional[str] = None, admin=Depends(get_admin_user)):
    q = admin_user_search_query(search)
    n = clamp_admin_user_limit(limit)
    total = await db.users.count_documents(q)
    users = await db.users.find(q, {"_id": 0}).sort("created_at", -1).to_list(n)
    # NO SILENT CAP: the body is still a bare array (the tab renders it
    # directly), so the honesty rides on headers + a log line.
    response.headers["X-Total-Matches"] = str(total)
    response.headers["X-Returned"] = str(len(users))
    if total > len(users):
        response.headers["X-Truncated"] = "1"
        logger.warning("[admin/users] TRUNCATED: returned %s of %s matches (limit=%s, search=%r)",
                       len(users), total, n, (search or "")[:64])
    return [public_user(u) for u in users]


@api_router.post("/admin/grant")
async def admin_grant(data: GrantInput, admin=Depends(get_admin_user)):
    target = await db.users.find_one({"id": data.user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if data.currency not in ("normal", "vip"):
        raise HTTPException(status_code=400, detail="Invalid currency")
    field = "coins" if data.currency == "normal" else "vip_coins"
    await db.users.update_one({"id": data.user_id}, {"$inc": {field: data.amount}})
    await add_transaction(data.user_id, data.currency, data.amount, "reward", data.reason)
    await add_log(admin["persona_name"], "grant", target.get("persona_name"),
                  {"currency": data.currency, "amount": data.amount, "reason": data.reason})
    staff_feed.fire_grant(admin.get("persona_name"), target.get("persona_name"),
                          data.currency, data.amount, data.reason,
                          self_grant=(str(data.user_id) == str(admin.get("id"))))
    return {"success": True}


@api_router.post("/admin/users/{user_id}/inventory-wipe")
async def admin_wipe_inventory(user_id: str, admin=Depends(get_admin_user)):
    """Cheat/bot enforcement: purge web inventory + glitch skins. Coins, La
    Boveda (vault) and market listings are deliberately untouched. Idempotent —
    a retry after a partial failure just deletes what remains (counts then 0)."""
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    inv_res = await db.inventory.delete_many({"user_id": user_id})
    skins_res = await db.reward_skins.delete_many({"user_id": user_id})
    deleted = {"inventory": inv_res.deleted_count, "reward_skins": skins_res.deleted_count}
    try:
        await add_log(admin["persona_name"], "inventory_wipe", target.get("persona_name"),
                      {"user_id": user_id, **deleted})
    except Exception:
        logger.exception("[admin] inventory_wipe audit log failed user=%s", user_id)
    staff_feed.fire_inventory_wipe(admin.get("persona_name"), target.get("persona_name"),
                                   deleted["inventory"], deleted["reward_skins"],
                                   self_wipe=(str(user_id) == str(admin.get("id"))))
    return {"success": True, "deleted": deleted, "target": target.get("persona_name")}


@api_router.post("/admin/role")
async def admin_set_role(data: RoleInput, admin=Depends(get_admin_user)):
    if data.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if data.role == "user":
        if data.user_id == admin["id"]:
            raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
        admin_count = await db.users.count_documents({"role": "admin"})
        target = await db.users.find_one({"id": data.user_id}, {"role": 1})
        if target and target.get("role") == "admin" and admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last administrator")
    await db.users.update_one({"id": data.user_id}, {"$set": {"role": data.role}})
    await add_log(admin["persona_name"], "set_role", data.user_id, {"role": data.role})
    return {"success": True}


@api_router.get("/staff-ranks")
async def get_staff_ranks():
    return STAFF_RANKS


class StaffRankInput(BaseModel):
    user_id: str
    rank: Optional[str] = None  # one of STAFF_RANKS keys, or null to clear


@api_router.post("/admin/staff-rank")
async def admin_set_staff_rank(data: StaffRankInput, admin=Depends(get_admin_user)):
    # only owner/admin (or seeded role admin) may assign ranks
    if not (admin.get("role") == "admin" or admin.get("staff_rank") in ("owner", "admin")):
        raise HTTPException(status_code=403, detail="Not allowed to assign ranks")
    if data.rank is not None and data.rank not in STAFF_RANKS:
        raise HTTPException(status_code=400, detail="Invalid rank")
    target = await db.users.find_one({"id": data.user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # Owner rank is the self-leniency boundary (a struck admin who self-promotes to
    # "owner" could self-unban). Only a REAL owner may grant it, revoke it, or change an
    # existing owner's rank — nobody self-promotes into the escape hatch.
    if (data.rank == "owner" or target.get("staff_rank") == "owner") and not _is_owner(admin):
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar el rango de propietario")
    update = {"staff_rank": data.rank}
    # owner/admin ranks unlock the admin panel; lower ranks don't touch role
    if data.rank in ("owner", "admin"):
        update["role"] = "admin"
    elif target.get("role") == "admin" and target.get("staff_rank") in ("owner", "admin"):
        admin_count = await db.users.count_documents({"role": "admin"})
        if admin_count > 1 and data.user_id != admin["id"]:
            update["role"] = "user"
    await db.users.update_one({"id": data.user_id}, {"$set": update})
    await add_log(admin["persona_name"], "set_staff_rank", target.get("persona_name"), {"rank": data.rank})
    return {"success": True}


@api_router.get("/admin/codes")
async def admin_list_codes(admin=Depends(get_admin_user)):
    return await db.codes.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api_router.post("/admin/codes")
async def admin_create_code(data: CodeInput, admin=Depends(get_admin_user)):
    code_str = data.code.strip().upper()
    if await db.codes.find_one({"code": code_str}):
        raise HTTPException(status_code=400, detail="A code with this name already exists")
    doc = {
        "id": new_id(), "code": code_str, "name": data.name, "description": data.description,
        "start_date": data.start_date, "end_date": data.end_date,
        "max_uses": data.max_uses, "per_user": data.per_user,
        "reward": data.reward.model_dump(), "active": data.active,
        "uses": 0, "created_at": now_iso(),
    }
    await db.codes.insert_one(doc)
    await add_log(admin["persona_name"], "create_code", code_str)
    staff_feed.fire_code_created(admin.get("persona_name"), code_str, doc.get("reward"),
                                 doc.get("max_uses"), doc.get("per_user"), doc.get("active"))
    doc.pop("_id", None)
    return doc


@api_router.patch("/admin/codes/{code_id}")
async def admin_update_code(code_id: str, data: CodeUpdate, admin=Depends(get_admin_user)):
    update = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    res = await db.codes.update_one({"id": code_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Code not found")
    await add_log(admin["persona_name"], "update_code", code_id, update)
    row = await db.codes.find_one({"id": code_id}, {"_id": 0, "code": 1})
    staff_feed.fire_code_updated(admin.get("persona_name"), (row or {}).get("code") or code_id, update)
    return {"success": True}


@api_router.delete("/admin/codes/{code_id}")
async def admin_delete_code(code_id: str, admin=Depends(get_admin_user)):
    row = await db.codes.find_one({"id": code_id}, {"_id": 0, "code": 1})
    await db.codes.delete_one({"id": code_id})
    await add_log(admin["persona_name"], "delete_code", code_id)
    staff_feed.fire_code_deleted(admin.get("persona_name"), (row or {}).get("code") or code_id)
    return {"success": True}


@api_router.get("/admin/logs")
async def admin_logs(admin=Depends(get_admin_user)):
    return await db.logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


# --- admin content CRUD: news ---
@api_router.post("/admin/news")
async def admin_create_news(data: NewsInput, admin=Depends(get_admin_user)):
    doc = {**data.model_dump(), "id": new_id(), "created_at": now_iso()}
    if not doc.get("image"):
        doc["image"] = seed_data.HERO_BG
    await db.news.insert_one(doc)
    await add_log(admin["persona_name"], "create_news", data.title)
    doc.pop("_id", None)
    return doc


@api_router.delete("/admin/news/{news_id}")
async def admin_delete_news(news_id: str, admin=Depends(get_admin_user)):
    await db.news.delete_one({"id": news_id})
    await add_log(admin["persona_name"], "delete_news", news_id)
    return {"success": True}


# --- admin content CRUD: events ---
@api_router.post("/admin/events")
async def admin_create_event(data: EventInput, admin=Depends(get_admin_user)):
    doc = {**data.model_dump(), "id": new_id(), "created_at": now_iso()}
    await db.events.insert_one(doc)
    await add_log(admin["persona_name"], "create_event", data.title)
    doc.pop("_id", None)
    return doc


@api_router.delete("/admin/events/{event_id}")
async def admin_delete_event(event_id: str, admin=Depends(get_admin_user)):
    await db.events.delete_one({"id": event_id})
    await add_log(admin["persona_name"], "delete_event", event_id)
    return {"success": True}


# --- admin content CRUD: store ---
@api_router.post("/admin/store")
async def admin_create_store(data: StoreItemInput, admin=Depends(get_admin_user)):
    doc = {**data.model_dump(), "id": new_id(), "created_at": now_iso()}
    if not doc.get("image"):
        doc["image"] = seed_data.COIN_NORMAL
    await db.store_items.insert_one(doc)
    await add_log(admin["persona_name"], "create_store_item", data.name)
    doc.pop("_id", None)
    return doc


@api_router.delete("/admin/store/{item_id}")
async def admin_delete_store(item_id: str, admin=Depends(get_admin_user)):
    await db.store_items.delete_one({"id": item_id})
    await add_log(admin["persona_name"], "delete_store_item", item_id)
    return {"success": True}


@api_router.patch("/admin/store/{item_id}")
async def admin_update_store(item_id: str, data: StoreItemUpdate, admin=Depends(get_admin_user)):
    update = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if "price" in update and update["price"] < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative")
    res = await db.store_items.update_one({"id": item_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    await add_log(admin["persona_name"], "update_store_item", item_id, update)
    item = await db.store_items.find_one({"id": item_id}, {"_id": 0})
    return item


@api_router.get("/admin/dino-records")
async def admin_dino_records(search: Optional[str] = None, admin=Depends(get_admin_user)):
    """Legacy pre-2026-07-15 dino_records. Kept for the handful of old rows.

    The live surface is /admin/recoverable — this collection stopped being
    written when dinosaurs moved to the vault, and no admin page reads this
    route any more. Left exactly as it was so the old records stay inspectable.
    """
    q = {}
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q = {"$or": [{"recovery_id": rx}, {"user_name": rx}, {"name": rx}]}
    items = await db.dino_records.find(q, {"_id": 0}).sort("updated_at", -1).to_list(300)
    return items


def _sid_from_query(raw: str) -> str:
    """A SteamID64 out of whatever the admin pasted (id, profile URL, spaces).

    A SteamID64 is exactly 17 digits. Anything else is not one — accepting a
    longer run of digits would key a vault row to an account that cannot exist,
    and the player would never see the dino.
    """
    term = str(raw or "").strip()
    if not term:
        return ""
    m = re.search(r"(?<!\d)(\d{17})(?!\d)", term)
    return m.group(1) if m else ""


async def _resolve_player(term: str) -> dict:
    """Identify a player from a Steam ID, persona or in-game name.

    Works for players with NO website account: the vault, the death log and the
    mod are all keyed by Steam ID, so a recovery never needs a web user row.
    """
    sid = _sid_from_query(term)
    user = None
    if sid:
        user = await db.users.find_one({"steam_id": sid}, {"_id": 0, "id": 1, "persona_name": 1, "steam_id": 1})
    if not user and term.strip():
        rx = {"$regex": re.escape(term.strip()), "$options": "i"}
        user = await db.users.find_one({"persona_name": rx},
                                       {"_id": 0, "id": 1, "persona_name": 1, "steam_id": 1})
        if user:
            sid = str(user.get("steam_id") or "")
    name = (user or {}).get("persona_name") or ""
    if sid and not name:
        # No web account: fall back to the name the mod knows them by.
        try:
            live = await asyncio.to_thread(game_ipc.read_player, sid)
        except Exception:
            live = None
        if isinstance(live, dict):
            name = str(live.get("name") or "")
    return {"steam_id": sid, "persona_name": name, "user_id": (user or {}).get("id"),
            "has_account": bool(user)}


# The playable roster keyed for case-insensitive lookup, so an admin's typing
# does not have to match the catalog's capitalisation.
_SPECIES_BY_CLASS_CASEFOLD = {s.casefold(): s for s in pop_control.SUPPORTED_SPECIES}

# When the park ledger started. Deaths older than this cannot be told apart from
# a park that was redeemed before we were recording, so they are flagged rather
# than trusted. Fixed once the first mark exists, so it is cached.
_park_ledger_start_ts = None


async def _park_ledger_start():
    global _park_ledger_start_ts
    if _park_ledger_start_ts is None:
        first = await db[dino_recovery.PARK_MARK_COLLECTION].find_one(
            {}, {"_id": 0, "created_at": 1}, sort=[("created_at", 1)])
        _park_ledger_start_ts = dino_recovery.parse_iso_ts((first or {}).get("created_at"))
    return _park_ledger_start_ts


async def _recent_deaths(sid: str) -> list[dict]:
    """The death window BOTH the lister and the granter must agree on.

    If these two ever scanned different depths, the panel would offer a dino
    whose grant then 404s.
    """
    return await asyncio.to_thread(
        dino_recovery.read_recent_deaths, game_ipc.SAVED_DIR, sid,
        dino_recovery.DEATH_SCAN_SIZE)


async def _recovery_captures(sid: str) -> list[dict]:
    """Every capture we still hold for this player, newest first.

    The lister and the granter MUST read the same set, or the panel promises
    mutations the grant then fails to deliver. Bounded by
    SNAPSHOT_HISTORY_SCAN so the cost does not grow with how long the player
    has been on the server.
    """
    return await db[dino_recovery.SNAPSHOT_HISTORY_COLLECTION].find(
        {"steam_id": sid}, {"_id": 0}
    ).sort("seen_at", -1).to_list(dino_recovery.SNAPSHOT_HISTORY_SCAN)


@api_router.get("/admin/recoverable")
async def admin_recoverable(q: str = "", admin=Depends(get_admin_user)):
    """A player's last 15 LOST dinos, newest first, plus what is in their vault.

    Type a Steam ID (or a name) and every dino that player lost comes back with
    its species, growth, how it died and when — click one to hand it back. Works
    for any player on the server, website account or not.
    """
    player = await _resolve_player(q)
    sid = player["steam_id"]
    if not sid:
        return {"player": player, "lost": [], "vault_count": 0,
                "message": "Introduce el SteamID64 del jugador (17 dígitos) o su nombre."}

    deaths, vault_rows = await asyncio.gather(
        _recent_deaths(sid),
        asyncio.to_thread(dino_recovery.read_parked_rows, game_ipc.BOT_DB_PATH, sid),
    )
    keys = [d["death_key"] for d in deaths]
    park_marks, granted, snap, history = await asyncio.gather(
        db[dino_recovery.PARK_MARK_COLLECTION].find(
            {"steam_id": sid}, {"_id": 0, "dino_class": 1, "parked_at_ts": 1}
        ).sort("parked_at_ts", -1).to_list(200),
        db[dino_recovery.RECOVERY_COLLECTION].find(
            {"death_key": {"$in": keys}}, {"_id": 0, "death_key": 1}
        ).to_list(len(keys) or 1),
        db[dino_recovery.SNAPSHOT_COLLECTION].find_one({"steam_id": sid}, {"_id": 0}),
        _recovery_captures(sid),
    )

    lost = dino_recovery.build_lost_list(
        deaths, vault_rows=vault_rows, park_marks=park_marks,
        recovered_keys={g["death_key"] for g in granted}, snapshot=snap,
        size=dino_recovery.LOST_LIST_SIZE,
        ledger_start_ts=await _park_ledger_start(), history=history)
    for item in lost:
        item["image"] = seed_data.DINO_IMG.get(
            game_telemetry._slug(item.get("species", "")), "")
    return {"player": player, "lost": lost, "vault_count": len(vault_rows)}


# A claim is written before the vault row and flipped to "done" after it. If the
# process dies in between, the claim is left "pending" and would block that dino
# from EVER being recovered. Anything still pending this long lost its request.
RECOVERY_CLAIM_STALE_S = 120


def _recovery_claim_is_stale(claim) -> bool:
    """Only a non-done claim older than the window may be taken over.

    A 'done' claim is permanent: that dino really was handed back.
    """
    if not isinstance(claim, dict) or claim.get("status") == "done":
        return False
    made = dino_recovery.parse_iso_ts(claim.get("created_at"))
    if not made:
        return True  # unreadable stamp on a non-done claim: never wedge the lane
    return (time.time() - made) > RECOVERY_CLAIM_STALE_S


# The claim above dedupes one DEATH EVENT; one dinosaur produces many death
# events, and granting a later one while an earlier grant still sits banked
# mints a second copy (rows 14013+14029 and 15251, 2026-08-20 — the
# vault_world_check "counted twice" alerts). So every grant asks the vault
# first, whatever door it came through (panel, legacy id, auto-rescue).
# Kill switch mirrors LIN_SAVE_RESCUE_OFF.
RECOVERY_TWIN_GATE_OFF = str(os.environ.get("LIN_RECOVERY_TWIN_GATE_OFF") or "").strip() == "1"
try:
    RECOVERY_TWIN_GATE_GROWTH_TOL = float(
        os.environ.get("LIN_RECOVERY_TWIN_GATE_GROWTH_TOL") or 0.02)
except (TypeError, ValueError):
    RECOVERY_TWIN_GATE_GROWTH_TOL = 0.02


async def _grant_recovered_dino(sid: str, payload: dict, *, death_key: str, admin,
                                label: str, source: str):
    """Claim the death, write the vault row, keep the claim only if it worked.

    Two independent guards, because either one alone has a hole:

    * a read-before-write check, which still refuses a duplicate if the unique
      index failed to build (see ensure_indexes) — that covers the realistic
      case of an admin clicking twice;
    * the unique index itself, which is the only thing that can settle two
      admins clicking in the same instant.

    If the vault write then fails or the player is at capacity, the claim is
    released — a failed recovery must never leave a dino marked as handed back.
    A claim that is still 'pending' long after it was made belongs to a request
    that died mid-flight; it is taken over rather than blocking that dino from
    ever being recovered again.
    """
    existing = await db[dino_recovery.RECOVERY_COLLECTION].find_one(
        {"death_key": death_key}, {"_id": 0, "status": 1, "created_at": 1})
    claim = {
        "death_key": death_key, "steam_id": sid, "status": "pending",
        "granted_by": admin.get("persona_name"), "created_at": now_iso(),
        "dino_class": payload.get("dino"), "growth": payload.get("growth"),
        "source": source,
    }
    if existing:
        if not _recovery_claim_is_stale(existing):
            raise HTTPException(status_code=400, detail="Ese dino ya fue recuperado.")
        logger.warning("[recovery] taking over a stale pending claim death_key=%s created_at=%s",
                       death_key, existing.get("created_at"))
        # ★TAKE IT OVER WITH A COMPARE-AND-SWAP, never delete-then-insert.
        # The old shape read the stale claim, deleted it unscoped, then
        # inserted a fresh one — so two admins who both saw the SAME stale
        # claim would both delete (the second deleting the first's brand new
        # claim) and both insert, and the unique index could not help because
        # by then there was nothing to collide with. Two vault rows, one dino.
        # Matching on the created_at we just observed means exactly one of them
        # can win the takeover; the loser is told it is already claimed.
        taken = await db[dino_recovery.RECOVERY_COLLECTION].update_one(
            {"death_key": death_key, "status": {"$ne": "done"},
             "created_at": existing.get("created_at")},
            {"$set": claim})
        if taken.matched_count != 1:
            raise HTTPException(status_code=400, detail="Ese dino ya fue recuperado.")
    else:
        try:
            await db[dino_recovery.RECOVERY_COLLECTION].insert_one(dict(claim))
        except DuplicateKeyError:
            raise HTTPException(status_code=400, detail="Ese dino ya fue recuperado.")

    # THE TWIN GATE — before anything is written. A banked dinosaur is not a
    # lost one; the claim is handed back on refusal so a future HONEST loss of
    # this same dinosaur (row redeemed, then really lost) can still be granted.
    # Every failure inside the gate falls OPEN with a receipt: a broken gate
    # must not block real recoveries.
    if not RECOVERY_TWIN_GATE_OFF:
        twin = None
        reader = getattr(dino_recovery, "read_twin_rows", None)
        finder = getattr(dino_recovery, "find_grant_twin", None)
        if reader is not None and finder is not None:
            try:
                twin_rows = await asyncio.to_thread(reader, game_ipc.BOT_DB_PATH, sid)
                twin = finder(sid, payload, twin_rows,
                              growth_tolerance=RECOVERY_TWIN_GATE_GROWTH_TOL)
            except Exception:
                logger.warning("[recovery] twin gate failed OPEN sid=%s", sid,
                               exc_info=True)
                twin = None
        if twin is not None:
            await db[dino_recovery.RECOVERY_COLLECTION].delete_one({"death_key": death_key})
            logger.warning("[recovery] refused banked_twin sid=%s source=%s by=%s %s",
                           sid, source, admin.get("persona_name"),
                           dino_recovery.grant_twin_receipt(twin))
            raise HTTPException(
                status_code=400,
                detail="Ese dino ya está guardado en la bóveda (fila %s). "
                       "No se creó otra copia: el jugador puede canjear esa fila."
                       % (twin.row_id,))

    # The cap the TARGET player parks under, not the admin's — staff park
    # without a limit, so a recovery to a staff account must not stop at 10.
    target = await db.users.find_one({"steam_id": sid},
                                     {"_id": 0, "role": 1, "staff_rank": 1, "steam_id": 1})
    cap = _user_park_cap(target) if target else _park_cap_default()
    try:
        row_id = await asyncio.to_thread(vault.save_parked, sid, "", payload, cap)
    except Exception:
        await db[dino_recovery.RECOVERY_COLLECTION].delete_one({"death_key": death_key})
        logger.warning("recover-dino: vault write failed sid=%s", sid, exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo escribir en la bóveda. No se recuperó nada.")
    if row_id is None:
        await db[dino_recovery.RECOVERY_COLLECTION].delete_one({"death_key": death_key})
        raise HTTPException(status_code=400,
                            detail=f"El jugador está al límite de dinos guardados ({cap}). Libera un espacio y reintenta.")

    await db[dino_recovery.RECOVERY_COLLECTION].update_one(
        {"death_key": death_key},
        {"$set": {"status": "done", "vault_row_id": int(row_id), "granted_at": now_iso()}})
    await add_log(admin["persona_name"], "recover_dino", sid,
                  {"death_key": death_key, "dino": payload.get("dino"),
                   "growth": payload.get("growth"), "vault_row_id": int(row_id),
                   "source": source})
    # ★The summary is not decoration. Without it a grant that handed back an
    # empty dino and one that carried every mutation, both prime flags and the
    # entomb stacks printed the SAME line, so no grep over the log could ever
    # have found this bug — only a player complaining could.
    logger.info("[recovery] granted sid=%s class=%s growth=%.4f vault_row=%s by=%s source=%s %s",
                sid, payload.get("dino"), float(payload.get("growth") or 0), row_id,
                admin.get("persona_name"), source, dino_recovery.payload_summary(payload))
    return {
        "success": True, "steam_id": sid, "owner": label,
        "dino": dino_recovery.clean_species(payload.get("dino")),
        "growth": round(float(payload.get("growth") or 0) * 100, 1),
        "mutations_count": dino_recovery.count_mutations(payload.get("mutations")),
        "parent_mutations_count": dino_recovery.count_mutations(payload.get("parent_mutations")),
        "elder_mutations_count": dino_recovery.count_mutations(payload.get("elder_mutations")),
        "is_prime": bool(payload.get("is_prime")),
        "is_elder": bool(payload.get("is_elder")),
        "elder_stacks": int(payload.get("elder_stacks") or 0),
        "prime_conditions": payload.get("prime_conditions"),
        "partial": dino_recovery.payload_is_bare(payload),
        "source": source,
        "vault_row_id": int(row_id),
        "skin_restored": bool(str(payload.get("skin_data") or "").strip()),
    }


@api_router.post("/admin/recover-dino")
async def admin_recover_dino(data: RecoverDinoInput, admin=Depends(get_admin_user)):
    """Hand a lost dino back. It lands in the player's vault, where they redeem
    it in game as that species — the same place a parked dino lives.

    The three ways in differ only in how the dino is IDENTIFIED; once a species,
    a growth fraction and a death key are settled, the tail is the same for all
    of them. Growth is a FRACTION everywhere below — never a percent.
    """
    legacy_rec = None
    extras = {}

    # ---- legacy dino_records path (pre-2026-07-15 rows) -------------------
    if data.recovery_id and not data.death_key:
        rid = data.recovery_id.strip()
        legacy_rec = await db.dino_records.find_one({"recovery_id": rid}, {"_id": 0})
        if not legacy_rec:
            raise HTTPException(status_code=404, detail="No hay ningún dino con ese ID de recuperación.")
        if legacy_rec.get("recovered"):
            raise HTTPException(status_code=400, detail="Ese dino ya fue recuperado.")
        owner = await db.users.find_one({"id": legacy_rec.get("user_id")},
                                        {"_id": 0, "steam_id": 1, "persona_name": 1})
        sid = str((owner or {}).get("steam_id") or "")
        if not sid:
            raise HTTPException(status_code=400,
                                detail="Ese registro no tiene una cuenta de Steam vinculada.")
        # Straight from the slug the record stores, via the same map every other
        # slug->class caller uses. Never fall back to the display NAME: "T-Rex"
        # would be stored as BP_T-Rex_C, a row the mod can never spawn.
        cls = _EVRIMA_CLASS_BY_SLUG.get(legacy_rec.get("slug") or "", "")
        if not cls:
            raise HTTPException(status_code=400, detail="No se pudo identificar la especie de ese registro.")
        growth = float(legacy_rec.get("growth") or 5) / 100.0
        snapshot, death_key, source = None, "legacy:%s" % rid, "legacy_record"
        label = (owner or {}).get("persona_name") or sid

    else:
        sid = _sid_from_query(data.steam_id or "")
        if not sid:
            raise HTTPException(status_code=400, detail="Falta el SteamID64 del jugador.")
        label = (await _resolve_player(sid)).get("persona_name") or sid

        # ---- normal path: one of the player's listed lost dinos -----------
        if data.death_key:
            death_key = str(data.death_key).strip()
            deaths = await _recent_deaths(sid)
            death = next((d for d in deaths if d["death_key"] == death_key), None)
            if not death:
                raise HTTPException(status_code=404,
                                    detail="Ese dino ya no aparece en las muertes recientes del jugador.")
            rolling, history = await asyncio.gather(
                db[dino_recovery.SNAPSHOT_COLLECTION].find_one({"steam_id": sid}, {"_id": 0}),
                _recovery_captures(sid),
            )
            candidates = [s for s in history if isinstance(s, dict)]
            if isinstance(rolling, dict) and rolling:
                candidates.append(rolling)
            snapshot = dino_recovery.pick_history_snapshot(candidates, death)
            detail = "full" if snapshot else ""
            if snapshot is None:
                # Say WHY, every time. This branch used to be a bare
                # `snapshot = None` with no log line anywhere, so a recovery
                # that quietly handed back an empty dino looked identical in
                # the log to one that carried everything.
                logger.warning(
                    "[recovery] capture did not bind sid=%s death_key=%s reason=%s "
                    "death_ts=%s captures=%d",
                    sid, death_key,
                    dino_recovery.snapshot_reject_reason(rolling, death) or "no_history",
                    death.get("ts"), len(candidates))
                snapshot = dino_recovery.pick_lkg_snapshot(candidates, death)
                if snapshot is not None:
                    detail = "lkg"
                    logger.info(
                        "[recovery] using last-known-good capture sid=%s death_key=%s "
                        "captured_at=%s age_s=%d",
                        sid, death_key, snapshot.get("seen_at"),
                        dino_recovery.snapshot_age_s(snapshot, death))
            cls, growth, source = death["dino_class"], death["growth"], "death_log"
            if detail == "lkg":
                source = "death_log_lkg"

        # ---- manual fallback: species + growth typed by the admin ---------
        else:
            # Matched case-insensitively against the roster the bot enforces, so
            # an admin typing "carnotaurus" gets BP_Carnotaurus_C and "Nope!!"
            # gets nothing. That roster is the right catalog: a species that is
            # not playable could never be redeemed even if it were granted, and
            # a bogus class would be a vault row the mod can never spawn.
            # (pop_control.canonical_species is not used here — its bare-name
            # branch strips BP_/_C then matches a map keyed on the full class,
            # so it only ever resolves an already-class-shaped input.)
            cls = _SPECIES_BY_CLASS_CASEFOLD.get(
                dino_recovery.to_class_name(data.species or "").casefold(), "")
            if not cls:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{data.species or ''}' no es una especie del servidor.")
            growth = (data.growth if data.growth is not None else 100.0) / 100.0
            snapshot, source = None, "manual"
            death_key = "manual:%s:%s:%d" % (
                sid, dino_recovery.clean_species(cls), int(time.time()))

    # Admin overrides apply on EVERY branch, not just the manual one. Without
    # this there was no way to repair a recovery that came back wrong: the only
    # fields an admin could state were species and growth, and the ones that
    # actually make a dino itself had no route in at all. A None means "not
    # supplied" and leaves the captured value alone.
    extras = {
        "is_prime": data.is_prime,
        "is_elder": data.is_elder,
        "mutations": data.mutations,
        "parent_mutations": data.parent_mutations,
        "elder_mutations": data.elder_mutations,
        "elder_stacks": data.elder_stacks,
        "prime_conditions": data.prime_conditions,
        "prime_route_mig": data.prime_route_mig,
        "prime_route_pat": data.prime_route_pat,
    }

    skin_data = await asyncio.to_thread(
        dino_recovery.read_last_skin, game_ipc.BOT_DB_PATH, sid, cls)
    payload = dino_recovery.build_recovery_payload(
        cls, growth, snapshot=snapshot, skin_data=skin_data, **extras)

    # A grant that would hand back an EMPTY dino is a decision, not a default.
    # The admin sees what is missing and re-posts with allow_partial to go
    # ahead. Refusing BEFORE the claim is inserted matters: a refusal must not
    # burn the death_key, or the dino becomes unrecoverable once the data to
    # recover it properly exists again.
    # Scoped to the automatic path on purpose. On the manual branch the admin is
    # stating everything they know by hand, so an empty dino is what they asked
    # for and a prompt would just be noise; on the death-log branch it means we
    # failed to bind a capture, which is the thing that must never be silent.
    if (source == "death_log" and dino_recovery.payload_is_bare(payload)
            and not data.allow_partial):
        logger.warning("[recovery] refused a bare grant sid=%s death_key=%s by=%s (%s)",
                       sid, death_key, admin.get("persona_name"),
                       dino_recovery.payload_summary(payload))
        raise HTTPException(status_code=409, detail={
            "code": "partial_requires_confirm",
            "message": ("No conservamos el estado de este dino: volvería sin mutaciones, "
                        "sin Prime y sin entombs. Confirma para devolverlo igualmente, "
                        "o rellena los datos a mano."),
            "dino": dino_recovery.clean_species(cls),
            "growth_pct": int(round(float(growth or 0) * 100)),
        })
    if dino_recovery.elder_slots_look_corrupt(payload.get("elder_mutations"),
                                              payload.get("elder_stacks")):
        logger.warning("[recovery] elder slots present with elder_stacks=0 sid=%s death_key=%s "
                       "elders=%r — storing as given, but the capture looks wrong",
                       sid, death_key, payload.get("elder_mutations"))

    result = await _grant_recovered_dino(sid, payload, death_key=death_key, admin=admin,
                                         label=label, source=source)
    if legacy_rec is not None:
        await db.dino_records.update_one(
            {"recovery_id": legacy_rec["recovery_id"]},
            {"$set": {"recovered": True, "status": "recovered", "recovered_at": now_iso(),
                      "recovered_by": admin["persona_name"]}})
    return result


# ---------------------------------------------------------------------------
# AUTOMATIC SAVE-CORRUPT RESCUE — the game's key check eats a save at join
# ("Save file is corrupt for <sid>"), the player is forced to a fresh spawn,
# and this lane hands the lost dino straight back into their vault from our
# last-seen-alive capture, through the SAME grant tail the /admin Recuperación
# panel uses. Eligibility is decided by save_rescue.decide() (pure, tested);
# everything io-shaped lives here. Kill switch: LIN_SAVE_RESCUE_OFF=1.
# ---------------------------------------------------------------------------
SAVE_RESCUE_STATE_COLLECTION = "save_rescue_state"
SAVE_RESCUE_STATE_ID = "game_log_pos"
SAVE_RESCUE_POLL_S = 20
# Catch-up ceiling per tick. A rotation reset re-reads a fresh boot log from
# the top; 4 MB covers ~40 minutes of this box's log at its measured rate, and
# anything longer just takes a few more ticks.
SAVE_RESCUE_READ_CAP = 4 * 1024 * 1024
SAVE_RESCUE_VICTIM_KEEP = 2000


def _save_rescue_log_path() -> str:
    return os.path.join(game_ipc.SAVED_DIR, "Logs", "TheIsle.log")


async def _try_auto_rescue(event: dict, victim_kills: list[dict]) -> None:
    """One corrupt-join event through the gates and (maybe) the grant tail."""
    sid = str(event.get("sid") or "")
    ts = int(event.get("ts") or 0)
    shape = save_rescue.key_shape(event)
    dkey = save_rescue.rescue_key(sid, ts)

    # Cheap idempotency read; the claim CAS inside _grant_recovered_dino is
    # the real guard. This just keeps replayed log windows quiet.
    if await db[dino_recovery.RECOVERY_COLLECTION].find_one(
            {"death_key": dkey}, {"_id": 1}):
        return

    day_lo = ts - save_rescue.RESCUE_DAILY_WINDOW_S
    recent = await db[dino_recovery.RECOVERY_COLLECTION].find(
        {"steam_id": sid, "source": save_rescue.RESCUE_SOURCE, "status": "done"},
        {"_id": 0, "granted_at": 1}).sort("granted_at", -1).to_list(5)
    grants_24h = sum(1 for r in recent
                     if dino_recovery.parse_iso_ts(r.get("granted_at")) >= day_lo)

    rolling, history, park_marks = await asyncio.gather(
        db[dino_recovery.SNAPSHOT_COLLECTION].find_one({"steam_id": sid}, {"_id": 0}),
        _recovery_captures(sid),
        db[dino_recovery.PARK_MARK_COLLECTION].find(
            {"steam_id": sid}, {"_id": 0, "dino_class": 1, "parked_at_ts": 1}
        ).sort("parked_at_ts", -1).to_list(20),
    )
    candidates = [s for s in history if isinstance(s, dict)]
    if isinstance(rolling, dict) and rolling:
        candidates.append(rolling)
    snap = save_rescue.pick_rescue_snapshot(candidates, ts)
    deaths = await _recent_deaths(sid)

    ok, reason = save_rescue.decide(event, snap, deaths, park_marks,
                                    victim_kills, grants_24h)
    if not ok:
        logger.info("[rescue] save-corrupt SKIP sid=%s shape=%s reason=%s ts=%d",
                    sid, shape, reason, ts)
        return

    cls = dino_recovery.to_class_name(snap.get("dino_class"))
    skin = await asyncio.to_thread(
        dino_recovery.read_last_skin, game_ipc.BOT_DB_PATH, sid, cls)
    payload = dino_recovery.build_recovery_payload(
        cls, snap.get("growth"), snapshot=snap, skin_data=skin)
    if dino_recovery.payload_is_bare(payload):
        # An automatic lane never hands back an empty animal — that decision
        # stays with a human on the admin panel.
        logger.warning("[rescue] save-corrupt SKIP bare payload sid=%s (%s)",
                       sid, dino_recovery.payload_summary(payload))
        return

    label = (await _resolve_player(sid)).get("persona_name") or sid
    try:
        result = await _grant_recovered_dino(
            sid, payload, death_key=dkey,
            admin={"persona_name": save_rescue.RESCUE_ACTOR}, label=label,
            source=save_rescue.RESCUE_SOURCE)
    except HTTPException as e:
        # duplicate claim (two ticks raced) or the player's vault is full —
        # both are terminal for THIS event and the reason is worth a line.
        logger.info("[rescue] save-corrupt grant refused sid=%s detail=%s",
                    sid, e.detail)
        return
    logger.info("[rescue] save-corrupt RESCUED sid=%s shape=%s class=%s "
                "growth=%.3f vault_row=%s",
                sid, shape, cls, float(snap.get("growth") or 0),
                result.get("vault_row_id"))


async def save_corrupt_rescue_loop():
    """Tail the game log for corrupt-join lines and rescue what they destroy.

    First install seeds the position at the CURRENT end of the log — the lane
    only ever acts on corrupt joins it watched happen, never on a backlog it
    cannot cross-check live. Every tick is exception-contained; a failed tick
    is a logged tick, never a dead loop.
    """
    await asyncio.sleep(25)
    if os.environ.get("LIN_SAVE_RESCUE_OFF", "").strip() == "1":
        logger.info("[rescue] save-corrupt auto rescue DISABLED by LIN_SAVE_RESCUE_OFF")
        return
    victim_kills: list[dict] = []
    while True:
        try:
            path = _save_rescue_log_path()
            state = await db[SAVE_RESCUE_STATE_COLLECTION].find_one(
                {"_id": SAVE_RESCUE_STATE_ID})
            if not state:
                try:
                    pos = os.path.getsize(path)
                except OSError:
                    pos = 0
                await db[SAVE_RESCUE_STATE_COLLECTION].update_one(
                    {"_id": SAVE_RESCUE_STATE_ID},
                    {"$set": {"pos": int(pos), "seeded_at": now_iso()}},
                    upsert=True)
                logger.info("[rescue] save-corrupt watcher armed, seeded at end pos=%d", pos)
                await asyncio.sleep(SAVE_RESCUE_POLL_S)
                continue
            pos = int(state.get("pos") or 0)
            lines, new_pos, rotated = await asyncio.to_thread(
                save_rescue.read_new_lines, path, pos, SAVE_RESCUE_READ_CAP)
            if rotated:
                logger.info("[rescue] game log rotated - reading the new boot from the top")
            events = []
            for ln in lines:
                v = save_rescue.parse_victim_line(ln)
                if v:
                    victim_kills.append(v)
                    continue
                e = save_rescue.parse_corrupt_line(ln)
                if e:
                    events.append(e)
            if len(victim_kills) > SAVE_RESCUE_VICTIM_KEEP:
                victim_kills = victim_kills[-SAVE_RESCUE_VICTIM_KEEP:]
            for event in events:
                try:
                    await _try_auto_rescue(event, victim_kills)
                except Exception:
                    logger.warning("[rescue] auto rescue errored sid=%s",
                                   event.get("sid"), exc_info=True)
            if new_pos != pos:
                await db[SAVE_RESCUE_STATE_COLLECTION].update_one(
                    {"_id": SAVE_RESCUE_STATE_ID},
                    {"$set": {"pos": int(new_pos)}}, upsert=True)
        except Exception as e:
            logger.warning("[rescue] save-corrupt watcher tick failed: %s", e,
                           exc_info=True)
        await asyncio.sleep(SAVE_RESCUE_POLL_S)


# --- admin content CRUD: dinosaurs ---
@api_router.post("/admin/dinosaurs")
async def admin_create_dino(data: DinoInput, admin=Depends(get_admin_user)):
    if await db.dinosaurs.find_one({"slug": data.slug}):
        raise HTTPException(status_code=400, detail="A dinosaur with this slug already exists")
    doc = {
        "id": new_id(), "slug": data.slug, "name": data.name, "type": data.type,
        "diet": data.diet, "rarity": data.rarity, "description": data.description,
        "image": data.image or seed_data.DINO_IMG["trex"],
        "stats": {"speed": data.speed, "health": data.health, "weight": data.weight,
                  "damage": data.damage, "growth_time": data.growth_time},
        "abilities": data.abilities, "status": data.status, "featured": data.featured,
        "created_at": now_iso(),
    }
    await db.dinosaurs.insert_one(doc)
    await add_log(admin["persona_name"], "create_dinosaur", data.name)
    doc.pop("_id", None)
    return doc


@api_router.delete("/admin/dinosaurs/{slug}")
async def admin_delete_dino(slug: str, admin=Depends(get_admin_user)):
    await db.dinosaurs.delete_one({"slug": slug})
    await add_log(admin["persona_name"], "delete_dinosaur", slug)
    return {"success": True}


# ---------- integrations: patreon & discord ----------
def make_state(user_id: str, purpose: str) -> str:
    return jwt.encode(
        {"sub": user_id, "p": purpose, "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
        JWT_SECRET, algorithm=JWT_ALGO,
    )


def read_state(state: str, purpose: str):
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGO])
        if payload.get("p") != purpose:
            return None
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


@api_router.get("/integrations/status")
async def integrations_status():
    return {
        "patreon_configured": bool(PATREON_CLIENT_ID and PATREON_CLIENT_SECRET),
        "discord_configured": bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET),
        "discord_role_sync": bool(DISCORD_BOT_TOKEN and DISCORD_GUILD_ID and DISCORD_VIP_ROLE_ID),
        "discord_tier_role_sync": bool(DISCORD_TIER_ROLE_SYNC and DISCORD_BOT_TOKEN
                                       and DISCORD_GUILD_ID and DISCORD_PATREON_ROLES),
    }


@api_router.post("/integrations/start")
async def integrations_start(user=Depends(get_current_user)):
    """Issue a short-lived one-time link token so the long-lived session JWT is never exposed in OAuth redirect URLs."""
    return {"link_token": make_state(user["id"], "linkstart")}


def _front_redirect(provider, status, detail=""):
    url = f"{FRONTEND_URL}/profile?{provider}={status}"
    if detail:
        url += f"&detail={detail}"
    return RedirectResponse(url=url)


# --- Patreon ---
@api_router.get("/patreon/login")
async def patreon_login(token: str):
    if not (PATREON_CLIENT_ID and PATREON_CLIENT_SECRET):
        raise HTTPException(status_code=503, detail="Patreon no esta configurado todavia (not configured)")
    user_id = read_state(token, "linkstart")
    if not user_id:
        raise HTTPException(status_code=401, detail="Sesion de enlace invalida o expirada")
    params = {
        "response_type": "code",
        "client_id": PATREON_CLIENT_ID,
        "redirect_uri": f"{PUBLIC_BASE_URL}/api/patreon/callback",
        "scope": "identity identity.memberships",
        "state": make_state(user_id, "patreon"),
    }
    return RedirectResponse(url=f"https://www.patreon.com/oauth2/authorize?{urlencode(params)}")


class PatreonUnauthorized(Exception):
    """Patreon rejected the user's access token (expired or revoked)."""


def _campaign_members(included):
    """Member rows that belong to THIS campaign (all of them when no id is configured).
    Identity returns memberships to every campaign the user supports; a foreign
    pledge — or a foreign free membership — must never read as a LIN patron."""
    members = [i for i in (included or []) if i.get("type") == "member"]
    if not PATREON_CAMPAIGN_ID:
        return members
    return [m for m in members
            if str((((m.get("relationships") or {}).get("campaign") or {}).get("data") or {}).get("id"))
            == PATREON_CAMPAIGN_ID]


async def sync_patreon_for_user(user_id: str, access_token: str):
    url = ("https://www.patreon.com/api/oauth2/v2/identity"
           "?include=memberships.currently_entitled_tiers,memberships.campaign"
           # 'currency' is no longer a valid member field upstream — requesting it 400s
           # the whole identity call (root cause of links storing empty data).
           "&fields[member]=patron_status,currently_entitled_amount_cents,last_charge_date,next_charge_date,pledge_relationship_start"
           "&fields[user]=full_name"
           "&fields[tier]=title")
    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.get(url, headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code == 401:
        raise PatreonUnauthorized()
    if r.status_code != 200:
        # A Patreon outage must never overwrite the stored status/tier with blanks.
        raise RuntimeError(f"patreon identity HTTP {r.status_code}")
    data = r.json()
    patreon_id = data.get("data", {}).get("id")
    full_name = data.get("data", {}).get("attributes", {}).get("full_name")
    included = data.get("included", [])
    members = _campaign_members(included)
    tiers = {i["id"]: i.get("attributes", {}).get("title") for i in included if i.get("type") == "tier"}
    status = None
    entitled_titles = []
    extra = {}
    for m in members:
        a = m.get("attributes", {})
        status = a.get("patron_status") or status
        if a.get("currently_entitled_amount_cents") is not None:
            extra["patreon_pledge_cents"] = a.get("currently_entitled_amount_cents")
        extra["patreon_last_charge"] = a.get("last_charge_date") or extra.get("patreon_last_charge")
        extra["patreon_next_charge"] = a.get("next_charge_date") or extra.get("patreon_next_charge")
        extra["patreon_since"] = a.get("pledge_relationship_start") or extra.get("patreon_since")
        tdata = m.get("relationships", {}).get("currently_entitled_tiers", {}).get("data", [])
        entitled_titles.extend(tiers.get((td or {}).get("id")) for td in tdata)
    tier_name = _best_entitled_tier(entitled_titles)
    # A membership the owner gave away is not a membership somebody bought, and
    # this is one of only two places a paying status is ever written.
    status = _demote_comped_status(status, extra.get("patreon_last_charge"),
                                   extra.get("patreon_next_charge"))
    await db.users.update_one({"id": user_id}, {"$set": {
        "patreon_id": patreon_id, "patreon_patron_status": status,
        "patreon_tier_name": tier_name, "patreon_synced_at": now_iso(),
        "patreon_name": full_name, **extra,
    }})
    await _after_patreon_status_update(user_id, status)
    return status, patreon_id


async def _amber_freeze_cycle(user_id):
    """Stop the bi-weekly Amberium clock when an account stops being an entitled
    patron, WITHOUT losing the days it has already served.

    Owner ruling 2026-08-16 ("if someone disconnects the reconnects timer shouldnt
    reset"): until this, `/patreon/unlink` deleted the anchor and the count outright,
    so the next link started a fresh 14 days and every day already served was gone.
    Measured on prod the same day: 7 accounts had been re-anchored this way, one
    active Adult patron 7.16 days into a 14-day cycle.

    Freezing is a STAMP, not a rewrite. The anchor and the count are left exactly as
    they stand and `_amber_resume_cycle` slides the anchor forward by however long
    the freeze lasted. That is what preserves the progress AND refuses to pay for the
    gap: an account that unlinks for two months must not come back to four periods of
    back-pay, which is the hole a naive "just stop clearing the anchor" would open.

    Only the FIRST stamp counts (`$exists: False` in the filter). Re-stamping on a
    second unlink would shorten the measured gap and hand out time nobody was
    entitled to. No anchor means there is no clock to freeze, so nothing is written.
    Contained: this must never break the status update that called it."""
    try:
        res = await db.users.update_one(
            {"id": user_id,
             "amber_payout_anchor": {"$exists": True},
             "amber_payout_paused_at": {"$exists": False}},
            {"$set": {"amber_payout_paused_at": now_iso()}})
        if getattr(res, "modified_count", 0) == 1:
            logger.info("[patreon] amber cycle frozen for %s", user_id)
            return True
    except Exception as e:
        logger.warning(f"[patreon] amber freeze for {user_id}: {e}")
    return False


async def _amber_resume_cycle(user_id):
    """Restart a frozen clock exactly where it stopped, by sliding the anchor forward
    by the length of the freeze. Progress is kept to the second; the frozen gap is
    never priced as elapsed cycle time.

    CAS'd on the pause stamp AND the anchor it was read against, because this account's
    own record proves the double fire is real: the OAuth callback and the creator-side
    reconcile both landed a `link_patreon` for the same relink 1.0 s apart. Two
    un-CAS'd resumes would slide the anchor by the gap TWICE and push the payout
    further away than the bug being fixed did.

    A junk or unparseable anchor is REPAIRED rather than preserved: the stamp and the
    dead anchor are dropped so the caller re-anchors from now, instead of the row
    sitting frozen forever with a value nothing can price. A pause stamp dated in the
    future (clock step) yields a zero-length gap — the anchor is never slid backwards,
    which would make a payout instantly due."""
    try:
        u = await db.users.find_one({"id": user_id}) or {}
        paused = u.get("amber_payout_paused_at")
        if not paused:
            return False
        anchor = u.get("amber_payout_anchor")
        cas = {"id": user_id, "amber_payout_paused_at": paused, "amber_payout_anchor": anchor}
        try:
            base = datetime.fromisoformat(anchor)
            since = datetime.fromisoformat(paused)
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
        except Exception:
            await db.users.update_one(cas, {"$unset": {"amber_payout_paused_at": "",
                                                       "amber_payout_anchor": "",
                                                       "amber_payout_count": ""}})
            logger.warning("[patreon] amber cycle had an unusable anchor/pause stamp for %s "
                           "(anchor=%r paused=%r) — cleared so it re-anchors", user_id, anchor, paused)
            return False
        gap = max(0.0, (datetime.now(timezone.utc) - since).total_seconds())
        res = await db.users.update_one(cas, {
            "$set": {"amber_payout_anchor": (base + timedelta(seconds=gap)).isoformat()},
            "$unset": {"amber_payout_paused_at": ""}})
        if getattr(res, "modified_count", 0) != 1:
            return False
        logger.info("[patreon] amber cycle resumed for %s — %.1f h frozen, progress kept",
                    user_id, gap / 3600.0)
        return True
    except Exception as e:
        logger.warning(f"[patreon] amber resume for {user_id}: {e}")
        return False


async def _after_patreon_status_update(user_id, status):
    """Shared tail for EVERY path that just wrote a fresh patron status (the OAuth
    sync, the members webhook, the creator-side reconcile): anchor the bi-weekly
    Amberium cycle the first time they become an active patron, then pay the joining
    Amberium (the claim inside is atomic and once-per-account, so calling it from
    every path is safe). Contained: a payout failure must never break the update
    that just refreshed their tier."""
    if status != "active_patron":
        # Entitlement is gone (cancelled, declined, unlinked, link_dead). Stop the
        # clock where it stands so returning keeps the days already served, and so
        # the time spent away is never paid out as elapsed cycles.
        await _amber_freeze_cycle(user_id)
        return
    # Entitled again: pick the clock up where it was frozen. A first-time patron has
    # nothing frozen, so this is a no-op and the fresh anchor below is what runs.
    await _amber_resume_cycle(user_id)
    u2 = await db.users.find_one({"id": user_id})
    if not (u2 or {}).get("amber_payout_anchor"):
        await db.users.update_one({"id": user_id}, {"$set": {
            "amber_payout_anchor": now_iso(), "amber_payout_count": 0,
        }})
        u2 = await db.users.find_one({"id": user_id})
    try:
        paid = await _patreon_pay_welcome_amber(u2)
    except Exception as e:
        paid = False
        logger.warning(f"[patreon] welcome amber for {user_id}: {e}")
    if not paid:
        # Already had a joining payment: if this sync is the one that saw them move UP
        # a tier, pay the difference. Contained separately so a top-up failure can
        # never undo or hide the joining payment above.
        try:
            await _patreon_topup_welcome_amber(u2)
        except Exception as e:
            logger.warning(f"[patreon] upgrade amber for {user_id}: {e}")


@api_router.get("/patreon/callback")
async def patreon_callback(request: Request):
    params = dict(request.query_params)
    state = params.get("state", "")
    code = params.get("code")
    user_id = read_state(state, "patreon")
    if not user_id or not code:
        return _front_redirect("patreon", "error", "invalid")
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            tr = await hc.post("https://www.patreon.com/api/oauth2/token", data={
                "code": code, "grant_type": "authorization_code",
                "client_id": PATREON_CLIENT_ID, "client_secret": PATREON_CLIENT_SECRET,
                "redirect_uri": f"{PUBLIC_BASE_URL}/api/patreon/callback",
            })
        td = tr.json()
        access = td.get("access_token")
        if not access:
            # Never log the raw body — a partial token response could carry a live token.
            logger.warning(f"[patreon] token exchange failed HTTP {tr.status_code}: "
                           f"error={td.get('error')} desc={td.get('error_description')}")
            return _front_redirect("patreon", "error", "token")
        upd = {"patreon_access_token": access, "patreon_refresh_token": td.get("refresh_token")}
        try:
            if td.get("expires_in"):
                upd["patreon_token_expires_at"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=int(td["expires_in"]))).isoformat()
        except Exception:
            pass
        await db.users.update_one({"id": user_id}, {"$set": upd})
        status, _ = await sync_patreon_for_user(user_id, access)
        user = await db.users.find_one({"id": user_id})
        if status == "active_patron" and not user.get("patreon_link_granted"):
            await db.users.update_one({"id": user_id}, {"$inc": {"vip_coins": VIP_GRANT_ON_LINK}, "$set": {"patreon_link_granted": True}})
            await add_transaction(user_id, "vip", VIP_GRANT_ON_LINK, "reward", "Patreon link bonus")
        await maybe_grant_discord_vip(user_id)
        await sync_discord_tier_roles(user_id)
        await add_log(user.get("persona_name"), "link_patreon", status)
    except Exception as e:
        logger.warning(f"patreon callback error: {e}")
        return _front_redirect("patreon", "error", "exception")
    return _front_redirect("patreon", "ok")


@api_router.get("/patreon/status")
async def patreon_status(user=Depends(get_current_user)):
    active = user.get("patreon_patron_status") == "active_patron"
    tier_key = _patreon_tier_key(user.get("patreon_tier_name"))
    amber = PATREON_TIER_AMBER.get(tier_key, 0)
    anchor = user.get("amber_payout_anchor")
    paused_at = user.get("amber_payout_paused_at")
    next_payout_iso = None
    seconds_remaining = None
    if active and anchor:
        try:
            base = datetime.fromisoformat(anchor)
        except Exception:
            base = datetime.now(timezone.utc)
        # A frozen clock is read AS OF the moment it froze. Counting down from the
        # wall clock instead would show a number that is quietly not running, which is
        # the same class of lie as the reset this panel is here to make visible.
        nowt = datetime.now(timezone.utc)
        if paused_at:
            try:
                frozen = datetime.fromisoformat(paused_at)
                nowt = frozen if frozen.tzinfo else frozen.replace(tzinfo=timezone.utc)
            except Exception:
                pass
        period = timedelta(days=PATREON_PAYOUT_DAYS)
        n = int((nowt - base) / period) + 1
        nxt = base + period * n
        next_payout_iso = nxt.isoformat()
        seconds_remaining = max(0, int((nxt - nowt).total_seconds()))
    pledge_cents = user.get("patreon_pledge_cents")
    pledge_str = None
    if pledge_cents:
        sym = CURRENCY_SYMBOL.get((user.get("patreon_currency") or "USD").upper(), "$")
        pledge_str = f"{sym}{pledge_cents / 100:.2f}/month"
    return {
        "active": bool(active and tier_key),
        "linked": bool(user.get("patreon_id")),
        "patron_status": user.get("patreon_patron_status"),
        "tier_key": tier_key,
        "tier_name": user.get("patreon_tier_name"),
        "amber_per_payout": amber,
        "boost": PATREON_TIER_BOOST.get(tier_key),
        "payout_days": PATREON_PAYOUT_DAYS,
        "next_payout": next_payout_iso,
        "seconds_remaining": seconds_remaining,
        # True while the account is unlinked/not entitled: the countdown above is held,
        # not running, and picks up from here when they link again.
        "cycle_paused": bool(paused_at),
        "last_payout_at": user.get("last_amber_payout_at"),
        # Set once, when the joining payment landed — lets the panel say the first payout
        # is already in the balance instead of implying a 14-day wait.
        "welcome_paid_at": user.get("patreon_welcome_amber_at"),
        # The joining Amberium this account has received in total, and when a tier
        # upgrade last topped it up. Makes "did my upgrade pay?" answerable from the
        # profile instead of from the database.
        "welcome_total": _patreon_welcome_amber_paid(user) if user.get("patreon_welcome_amber_at") else None,
        "welcome_upgraded_at": user.get("patreon_welcome_amber_upgraded_at"),
        "supporting_since": user.get("patreon_since"),
        "next_renewal": user.get("patreon_next_charge"),
        "last_payment": user.get("patreon_last_charge"),
        "pledge": pledge_str,
        "patreon_name": user.get("patreon_name"),
        "synced_at": user.get("patreon_synced_at"),
        "configured": bool(PATREON_CLIENT_ID and PATREON_CLIENT_SECRET),
    }



@api_router.post("/patreon/sync")
async def patreon_sync(user=Depends(get_current_user)):
    if not user.get("patreon_access_token"):
        raise HTTPException(status_code=400, detail="Patreon no esta vinculado")
    synced, status = await _sync_patreon_with_refresh(user)
    if not synced:
        raise HTTPException(status_code=502, detail="No se pudo sincronizar con Patreon — reintenta o vuelve a vincular la cuenta")
    await maybe_grant_discord_vip(user["id"])
    await sync_discord_tier_roles(user["id"])
    return {"patron_status": status}


@api_router.post("/patreon/unlink")
async def patreon_unlink(user=Depends(get_current_user)):
    # FREEZE FIRST, then drop the link. The anchor and the count are deliberately NOT
    # in the $unset below any more: deleting them is what threw away a patron's served
    # days on every unlink→relink, and the freeze stamp needs the anchor to still be
    # there to have anything to hold. Doing it in this order also means an unlink that
    # dies between the two writes leaves a frozen clock, not a deleted one.
    await _amber_freeze_cycle(user["id"])
    await db.users.update_one({"id": user["id"]}, {"$unset": {
        "patreon_id": "", "patreon_patron_status": "", "patreon_tier_name": "",
        "patreon_access_token": "", "patreon_refresh_token": "", "patreon_token_expires_at": "",
        "patreon_name": "", "patreon_since": "", "patreon_next_charge": "",
        "patreon_last_charge": "", "patreon_pledge_cents": "", "patreon_currency": "",
        "patreon_synced_at": "",
    }})
    # NOTE: `patreon_welcome_amber_at` is deliberately NOT cleared here. Unlinking and
    # relinking must never mint a second joining payment — the stamp is the
    # once-per-account claim that prevents it. Keeping `amber_payout_count` matters for
    # the same reason: that claim also refuses anyone who has already collected a
    # recurring cycle, and clearing the count used to disarm exactly that guard.
    # Entitlement is gone: take back the site-granted Discord tier roles.
    await sync_discord_tier_roles(user["id"])
    return {"success": True}


# --- Discord ---
@api_router.get("/discord/login")
async def discord_login(token: str):
    if not (DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET):
        raise HTTPException(status_code=503, detail="Discord no esta configurado todavia (not configured)")
    user_id = read_state(token, "linkstart")
    if not user_id:
        raise HTTPException(status_code=401, detail="Sesion de enlace invalida o expirada")
    params = {
        "response_type": "code",
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": f"{PUBLIC_BASE_URL}/api/discord/callback",
        "scope": "identify guilds guilds.members.read",
        "state": make_state(user_id, "discord"),
    }
    return RedirectResponse(url=f"https://discord.com/oauth2/authorize?{urlencode(params)}")


# ---------- Patreon access via Discord tier roles ----------
# Live role reads so a freshly-granted role works near-instantly: tiny TTL cache per
# discord_id (30 s hit / 15 s miss-or-error), explicit refresh bypasses it.
_DISCORD_MEMBER_CACHE = {}
_DISCORD_MEMBER_TTL_OK = 30.0
_DISCORD_MEMBER_TTL_ERR = 15.0
_DISCORD_UA = "DiscordBot (https://laislanublar.net, 1.0)"


async def _discord_member_info(discord_id: str, force: bool = False):
    """Fetch the member's roles in the LIN guild via the bot token.
    Returns (in_guild, roles): (True, [...]) member, (False, []) not in guild,
    (None, None) Discord API unreachable/unauthorized (unknown)."""
    if not (DISCORD_BOT_TOKEN and DISCORD_GUILD_ID and discord_id):
        return (None, None)
    now = asyncio.get_running_loop().time()
    if not force:
        hit = _DISCORD_MEMBER_CACHE.get(discord_id)
        if hit and hit[0] > now:
            return (hit[1], hit[2])
    in_guild, roles, ttl = None, None, _DISCORD_MEMBER_TTL_ERR
    try:
        async with httpx.AsyncClient(timeout=6) as hc:
            r = await hc.get(
                f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/members/{discord_id}",
                headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "User-Agent": _DISCORD_UA},
            )
        if r.status_code == 200:
            roles = [str(x) for x in (r.json().get("roles") or [])]
            in_guild, ttl = True, _DISCORD_MEMBER_TTL_OK
        elif r.status_code == 404:
            in_guild, roles, ttl = False, [], _DISCORD_MEMBER_TTL_OK
        else:
            logger.warning(f"discord member fetch {discord_id}: HTTP {r.status_code}")
    except Exception as e:
        logger.warning(f"discord member fetch error: {e}")
    _DISCORD_MEMBER_CACHE[discord_id] = (now + ttl, in_guild, roles)
    return (in_guild, roles)


def _tier_from_roles(roles):
    """First configured tier role the member holds (config order = precedence)."""
    if not roles:
        return None
    held = set(roles)
    for rid, label in DISCORD_PATREON_ROLES.items():
        if rid in held:
            return label
    return None


def _has_streamer_role(roles):
    """True if the member currently holds the dedicated free Streamer Pack role."""
    if not roles or not DISCORD_STREAMER_ROLE_ID:
        return False
    return DISCORD_STREAMER_ROLE_ID in {str(r) for r in roles}


async def _patreon_access(user, force: bool = False):
    """Full Patreon-access decision for the skin editor apply lane. Live-checks the
    Discord tier roles (near-instant for fresh grants) and persists the found tier on
    the user doc so the rest of the site (_is_subscriber) recognizes role holders too."""
    u = user or {}
    pat_active = u.get("patreon_patron_status") == "active_patron"
    out = {
        "allowed": False, "via": None, "tier": None,
        "discord": {
            "linked": bool(u.get("discord_id")),
            "username": u.get("discord_username") or None,
            "in_guild": None,
            "tier_role": None,
            "checked": False,
        },
        "patreon": {
            "linked": bool(u.get("patreon_id")),
            "active": pat_active,
            "tier_name": u.get("patreon_tier_name") if pat_active else None,
        },
        "tier_roles": list(DISCORD_PATREON_ROLES.values()),
        "streamer": False,
    }
    # Owner ruling 2026-07-18: staff ranks NEVER imply Patreon perks — only the
    # server owner keeps the bypass. Staff who are real patrons still qualify
    # through the normal role/patron lanes below.
    if _is_owner(u):
        # Route the owner's field through the SAME helper the /apply gate calls, instead of
        # hardcoding it here. This early return was the one place the reported field was
        # still written independently of the enforced gate — the exact split that broke the
        # streamer lane — so it is closed rather than left as the next one to bite.
        out.update(allowed=True, via="admin")
        out["skin_creator"] = _skin_creator_allowed(out)
        return out
    tier = None
    streamer = False
    # One live guild read covers BOTH the tier roles and the Streamer Pack role.
    if u.get("discord_id") and (DISCORD_PATREON_ROLES or DISCORD_STREAMER_ROLE_ID):
        in_guild, roles = await _discord_member_info(str(u["discord_id"]), force=force)
        out["discord"]["in_guild"] = in_guild
        out["discord"]["checked"] = in_guild is not None
        if in_guild is None:
            # Discord unreachable: previously-verified holders keep working (stale grant);
            # unknowns stay locked rather than failing open.
            tier = u.get("discord_tier_role") or None
            streamer = bool(u.get("discord_streamer_role"))
            out["discord"]["in_guild"] = u.get("discord_in_guild") if (tier or streamer) else None
        else:
            tier = _tier_from_roles(roles)
            streamer = _has_streamer_role(roles)
            stored_streamer = bool(u.get("discord_streamer_role"))
            if u.get("id") and ((u.get("discord_tier_role") or None) != tier or stored_streamer != streamer):
                # Persist BOTH so sync gates and _is_subscriber (which read stored fields,
                # no live call) recognize/revoke role holders. Removing the role clears it.
                set_fields = {
                    "discord_tier_role": tier or "",
                    "discord_streamer_role": DISCORD_STREAMER_ROLE_ID if streamer else "",
                    "discord_tier_checked_at": now_iso(),
                }
                if streamer and not stored_streamer:
                    # Fresh grant / re-grant after a revoke: start a fresh amber clock so a
                    # gap in eligibility is never back-paid.
                    set_fields["streamer_amber_anchor"] = now_iso()
                    set_fields["streamer_amber_count"] = 0
                await db.users.update_one({"id": u["id"]}, {"$set": set_fields})
                u["discord_tier_role"] = tier or ""
                u["discord_streamer_role"] = DISCORD_STREAMER_ROLE_ID if streamer else ""
                if streamer and not stored_streamer:
                    # Role handed out in Discord directly, with no application to approve:
                    # the joining payment must land here too, or a manual grant would sit
                    # 14 days with nothing. One Mongo write; the notice is fired, not awaited.
                    await _streamer_pay_welcome_amber(
                        u["id"], str(u.get("discord_id") or ""), u.get("persona_name") or "")
    out["discord"]["tier_role"] = tier
    out["streamer"] = streamer
    if tier:
        out.update(allowed=True, via="discord_role", tier=tier)
    elif pat_active and _patreon_tier_key(u.get("patreon_tier_name")):
        # A recognized PAID tier is required — an active free membership is not access.
        out.update(allowed=True, via="patreon", tier=_patreon_tier_key(u.get("patreon_tier_name")))
    elif streamer:
        # Streamer Pack: no paid tier, but the role grants skin creator + dino unlock.
        out.update(allowed=True, via="streamer")
    # Streamer Pack always includes the skin creator (juvie-only patrons still don't).
    # Cached from the helper the /apply gate also calls, so the reported field and the
    # enforced gate are the same decision by construction.
    out["skin_creator"] = _skin_creator_allowed(out)
    return out


@api_router.get("/patreon-access")
async def patreon_access(refresh: int = 0, user=Depends(get_current_user)):
    return await _patreon_access(user, force=bool(refresh))


# ── Streamer Pack: free, application-only perk (benefits driven by the Discord role) ──
async def _discord_post_application(app: dict):
    """Post one Streamer Pack application to the review channel with Approve/Reject
    buttons the bot handles. Returns the Discord message id, or None on any failure
    (never raises). Buttons carry STATIC custom_ids; the bot disambiguates by message id."""
    chan = DISCORD_STREAMER_APPS_CHANNEL_ID
    if not (DISCORD_BOT_TOKEN and chan):
        return None
    try:
        did = str(app.get("discord_id") or "")
        fields = [
            {"name": "Jugador", "value": f"{app.get('persona_name') or '—'}\n`{app.get('steam_id') or '—'}`", "inline": True},
            {"name": "Discord", "value": (f"<@{did}>" if did else "—"), "inline": True},
            {"name": "Plataforma", "value": (app.get("platform") or "—")[:120], "inline": True},
            {"name": "Canal", "value": (app.get("channel_url") or "—")[:300], "inline": False},
            {"name": "Seguidores / subs", "value": (app.get("followers") or "—")[:120], "inline": True},
            {"name": "Espectadores prom.", "value": (app.get("avg_viewers") or "—")[:120], "inline": True},
            {"name": "Sobre su contenido", "value": (app.get("about") or "—")[:1024], "inline": False},
        ]
        embed = {"title": "🎥 Nueva solicitud de Streamer Pack", "color": 0x9146FF,
                 "fields": fields, "footer": {"text": f"ID {app.get('id')}"}, "timestamp": app.get("created_at")}
        components = [{"type": 1, "components": [
            {"type": 2, "style": 3, "label": "Aprobar", "custom_id": "streamer:approve", "emoji": {"name": "✅"}},
            {"type": 2, "style": 4, "label": "Rechazar", "custom_id": "streamer:reject", "emoji": {"name": "❌"}},
        ]}]
        url = f"https://discord.com/api/v10/channels/{chan}/messages"
        headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "User-Agent": _DISCORD_UA, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.post(url, headers=headers, json={
                "embeds": [embed], "components": components, "allowed_mentions": {"parse": []}})
        if r.status_code in (200, 201):
            return str((r.json() or {}).get("id") or "") or None
        logger.warning(f"[streamer] post application HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[streamer] post application: {e}")
    return None


_BG_TASKS = set()


def _fire(coro):
    """Run a best-effort coroutine without making the caller wait for it. Keeps a hard
    reference until it finishes, because a task with no live reference can be garbage
    collected mid-flight and silently never run. Returns the task (tests await it)."""
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:            # no running loop (sync context) — nothing to schedule
        coro.close()
        return None
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


async def _discord_dm(discord_id: str, content: str) -> bool:
    """Best-effort DM to one member. True only if Discord accepted the message.
    Never raises: a closed DM inbox or a Discord outage must never cost a payout."""
    if not (DISCORD_BOT_TOKEN and discord_id):
        return False
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "User-Agent": _DISCORD_UA,
               "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.post("https://discord.com/api/v10/users/@me/channels",
                              headers=headers, json={"recipient_id": str(discord_id)})
            if r.status_code not in (200, 201):
                logger.warning(f"[streamer] open DM HTTP {r.status_code}: {r.text[:160]}")
                return False
            chan = str(((r.json() or {}) if r.content else {}).get("id") or "")
            if not chan:
                return False
            r2 = await hc.post(f"https://discord.com/api/v10/channels/{chan}/messages",
                               headers=headers,
                               json={"content": content[:1900], "allowed_mentions": {"parse": []}})
        if r2.status_code in (200, 201):
            return True
        logger.warning(f"[streamer] DM HTTP {r2.status_code}: {r2.text[:160]}")
    except Exception as e:
        logger.warning(f"[streamer] DM: {e}")
    return False


def _amber_es(amount: int) -> str:
    """20000 -> '20.000' (es-ES thousands separator). Formatted on its own so the
    separator swap can never touch punctuation in the surrounding sentence."""
    return f"{int(amount):,}".replace(",", ".")


async def _streamer_notify_payout(discord_id: str, amount: int, first: bool = False) -> bool:
    """Tell a streamer their Amberium landed. DM first; if the DM cannot be delivered
    (closed inbox) fall back to the streamers channel with a mention, so the notice is
    never silently lost. NEVER raises and never blocks the money: it is always called
    after the payout is already committed."""
    try:
        did = str(discord_id or "")
        if not did:
            return False
        amt = _amber_es(amount)
        if first:
            msg = (f"🎥 ¡Bienvenido al Streamer Pack! Acabamos de añadir **{amt} Amberium** "
                   f"a tu cuenta. El siguiente pago llega en {PATREON_PAYOUT_DAYS} días y se "
                   f"repite cada {PATREON_PAYOUT_DAYS} días mientras conserves el rol de Streamer.")
        else:
            msg = (f"🎥 Pago del Streamer Pack: **{amt} Amberium** añadidos a tu cuenta. "
                   f"El siguiente llega en {PATREON_PAYOUT_DAYS} días.")
        if await _discord_dm(did, msg):
            return True
        chan = DISCORD_STREAMER_LOUNGE_CHANNEL_ID
        if not (chan and DISCORD_BOT_TOKEN):
            logger.warning("[streamer] payout notice undelivered (DM closed, no fallback channel) did=%s", did)
            return False
        url = f"https://discord.com/api/v10/channels/{chan}/messages"
        headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "User-Agent": _DISCORD_UA,
                   "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.post(url, headers=headers, json={
                "content": f"<@{did}> {msg}", "allowed_mentions": {"users": [did]}})
        if r.status_code in (200, 201):
            return True
        logger.warning(f"[streamer] payout notice fallback HTTP {r.status_code}: {r.text[:160]}")
    except Exception as e:
        logger.warning(f"[streamer] payout notice: {e}")
    return False


async def _streamer_pay_welcome_amber(user_id: str, discord_id: str = "", persona: str = "") -> bool:
    """Pay the JOINING Amberium the instant someone becomes a streamer — the 14-day clock
    then runs from that moment (owner ruling 2026-07-24: "they should get it instantly then
    timer begins").

    Claimed ATOMICALLY on `streamer_welcome_amber_at` not existing, so the approve button,
    the live role read and the payout loop may all call it and exactly one wins. That same
    claim makes it once-per-account for good: a role removed and re-added restarts the timer
    but can never mint a second joining payment. Active patrons are skipped for the same
    no-stacking reason the recurring pass excludes them. Returns True only if IT paid."""
    if not user_id or STREAMER_AMBER <= 0:
        return False
    did = str(discord_id or "")
    if did:
        # Nothing enforces one site account per discord_id (users is unique on steam_id
        # only), so the same Discord person can hold several site accounts and a per-user
        # claim alone would mint the joining payment once per ALT. Scope the claim to the
        # Discord identity as well. A true race still needs a unique index on discord_id.
        twin = await db.users.find_one(
            {"discord_id": did, "id": {"$ne": user_id},
             "streamer_welcome_amber_at": {"$exists": True}}, {"_id": 0, "id": 1})
        if twin:
            logger.warning("[streamer] joining amber refused: discord %s already claimed it on user %s",
                           did, twin.get("id"))
            return False
    try:
        res = await db.users.update_one(
            {"id": user_id,
             "streamer_welcome_amber_at": {"$exists": False},
             "patreon_patron_status": {"$ne": "active_patron"}},
            {"$inc": {"vip_coins": STREAMER_AMBER},
             "$set": {"streamer_welcome_amber_at": now_iso(), "last_amber_payout_at": now_iso()}})
    except Exception as e:
        logger.warning(f"[streamer] welcome amber write: {e}")
        return False
    if getattr(res, "modified_count", 0) != 1:
        return False
    logger.info("[streamer] welcome amber %s paid user=%s", STREAMER_AMBER, user_id)
    try:
        # Same paper trail the recurring payout leaves, so the coins are explainable in
        # the player's history and in the staff log rather than appearing from nowhere.
        await add_transaction(user_id, "vip", STREAMER_AMBER, "reward",
                              "Streamer Pack Amberium de bienvenida")
        await add_log(persona or "—", "streamer_amber_welcome", None,
                      {"amount": STREAMER_AMBER, "user_id": user_id})
    except Exception as e:
        logger.warning(f"[streamer] welcome amber log: {e}")
    _fire(_streamer_notify_payout(did, STREAMER_AMBER, first=True))
    return True


async def _patreon_notify_payout(discord_id: str, amount: int, tier_name: str = "",
                                 first: bool = False, upgrade: bool = False) -> bool:
    """Tell a patron their Amberium landed. DM first; fall back to the optional patron
    notice channel with a mention so the notice is never silently lost. NEVER raises and
    never blocks the money — always called after the payout is already committed."""
    try:
        did = str(discord_id or "")
        if not did:
            return False
        amt = _amber_es(amount)
        tier = f" ({tier_name})" if tier_name else ""
        if upgrade:
            # The upgrade pays a DIFFERENCE, so the message says so -- a patron who
            # reads "10.000" after subscribing to a 28.000 tier would otherwise think
            # he was short-changed a second time.
            msg = (f"🧡 ¡Gracias por mejorar tu nivel de Patreon{tier}! Hemos añadido "
                   f"**{amt} Amberium**, la diferencia hasta el total de tu nuevo "
                   f"nivel. Tu pago cada {PATREON_PAYOUT_DAYS} días pasa a ser el de "
                   f"este nivel y mantiene la fecha que ya tenías.")
        elif first:
            msg = (f"🧡 ¡Gracias por suscribirte a Patreon{tier}! Acabamos de añadir "
                   f"**{amt} Amberium** a tu cuenta. El siguiente pago llega en "
                   f"{PATREON_PAYOUT_DAYS} días y se repite cada {PATREON_PAYOUT_DAYS} días "
                   f"mientras conserves tu suscripción.")
        else:
            msg = (f"🧡 Pago de Patreon{tier}: **{amt} Amberium** añadidos a tu cuenta. "
                   f"El siguiente llega en {PATREON_PAYOUT_DAYS} días.")
        if await _discord_dm(did, msg):
            return True
        chan = DISCORD_PATREON_NOTICE_CHANNEL_ID
        if not (chan and DISCORD_BOT_TOKEN):
            logger.warning("[patreon] payout notice undelivered (DM closed, no fallback channel) did=%s", did)
            return False
        url = f"https://discord.com/api/v10/channels/{chan}/messages"
        headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "User-Agent": _DISCORD_UA,
                   "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.post(url, headers=headers, json={
                "content": f"<@{did}> {msg}", "allowed_mentions": {"users": [did]}})
        if r.status_code in (200, 201):
            return True
        logger.warning(f"[patreon] payout notice fallback HTTP {r.status_code}: {r.text[:160]}")
    except Exception as e:
        logger.warning(f"[patreon] payout notice: {e}")
    return False


async def _patreon_pay_welcome_amber(user) -> bool:
    """Pay the tier Amberium the INSTANT someone becomes an active patron — the 14-day
    clock then runs from that moment (owner ruling 2026-07-24: "make all patreon roles get
    a payout right as the person gets it then the timer begins ... ensure they also get a
    discord message"). Applies to every tier in PATREON_TIER_AMBER, at its own amount.

    Claimed ATOMICALLY on `patreon_welcome_amber_at` not existing, so the OAuth callback,
    the manual Sincronizar button, the 12-hourly resync loop and the payout loop may all
    call it and exactly one wins. Deliberately once-per-account for good: `patreon_unlink`
    clears the anchor and the count but NOT this stamp, so unlink→relink restarts the
    countdown and can never mint a second joining payment.

    Refuses when the tier is unpriced ("Free", or a membership with no tier) and when the
    account has ALREADY been paid a recurring cycle (`amber_payout_count` > 0) — that
    guard is what keeps a long-standing patron from collecting a retroactive windfall the
    first time this code runs. Returns True only if IT paid."""
    u = user or {}
    uid = u.get("id")
    if not uid or u.get("patreon_patron_status") != "active_patron":
        return False
    if u.get("patreon_welcome_amber_at"):
        return False
    tier_name = u.get("patreon_tier_name")
    tier_key = _patreon_tier_key(tier_name)
    amber = PATREON_TIER_AMBER.get(tier_key) or 0
    if amber <= 0:
        return False
    pid = str(u.get("patreon_id") or "")
    if pid:
        # Nothing enforces one site account per Patreon identity (users is unique on
        # steam_id only), so the same Patreon membership can be linked from several site
        # accounts and a per-user claim alone would mint the joining payment once per ALT.
        # ★The claim is matched on `patreon_welcome_amber_patreon_id`, a field NOTHING
        # clears, because `patreon_id` itself is $unset by /patreon/unlink — matching on
        # that alone would let unlink-here-relink-there pay the same membership twice.
        # The legacy shape (paid before this field existed) is still honoured.
        twin = await db.users.find_one(
            {"id": {"$ne": uid},
             "$or": [{"patreon_welcome_amber_patreon_id": pid},
                     {"patreon_id": pid, "patreon_welcome_amber_at": {"$exists": True}}]},
            {"_id": 0, "id": 1})
        if twin:
            logger.warning("[patreon] joining amber refused: patreon %s already claimed it on user %s",
                           pid, twin.get("id"))
            return False
    stamp = now_iso()
    try:
        res = await db.users.update_one(
            {"id": uid,
             "patreon_welcome_amber_at": {"$exists": False},
             "patreon_patron_status": "active_patron",
             # Price and pay the SAME tier: a live upgrade between the read above and this
             # write must not pay the old amount against the new tier.
             "patreon_tier_name": tier_name,
             # Missing counts as zero — legacy docs predate the field.
             "$or": [{"amber_payout_count": {"$exists": False}},
                     {"amber_payout_count": {"$lte": 0}}]},
            {"$inc": {"vip_coins": amber},
             # The countdown restarts HERE, so the next cycle is a full period away.
             "$set": {"patreon_welcome_amber_at": stamp,
                      # Survives an unlink (see the twin check above) — this is the durable
                      # record of WHICH Patreon membership was already paid its joining amber.
                      "patreon_welcome_amber_patreon_id": pid,
                      "patreon_welcome_amber_tier": tier_key,
                      # The exact figure paid, so a later tier upgrade can price the
                      # difference without having to re-derive it from the tier key.
                      "patreon_welcome_amber_total": amber,
                      "amber_payout_anchor": stamp,
                      "amber_payout_count": 0, "last_amber_payout_at": stamp}})
    except Exception as e:
        logger.warning(f"[patreon] welcome amber write: {e}")
        return False
    if getattr(res, "modified_count", 0) != 1:
        return False
    logger.info("[patreon] welcome amber %s (%s) paid user=%s", amber, tier_key, uid)
    try:
        # Same paper trail the recurring payout leaves, so the coins are explainable in the
        # player's history and in the staff log rather than appearing from nowhere.
        await add_transaction(uid, "vip", amber, "reward",
                              f"Patreon {tier_key} Amberium de bienvenida")
        await add_log(u.get("persona_name") or "—", "amber_payout", tier_key,
                      {"amount": amber, "periods": 0, "welcome": True, "user_id": uid})
    except Exception as e:
        logger.warning(f"[patreon] welcome amber log: {e}")
    _fire(_patreon_notify_payout(u.get("discord_id"), amber, tier_name or "", first=True))
    return True


async def _patreon_topup_welcome_amber(user) -> int:
    """Pay the DIFFERENCE when a patron moves UP a tier after their joining payment.

    The joining Amberium is once per account and is priced at the tier held at the
    moment it was claimed. Someone who joined 🟢Juvie and upgraded to 🩷 Sub Adult a
    few hours later therefore kept the 18.000 and never saw the 28.000 the Sub Adult
    tier is sold with -- a real paying patron sat 10.000 short on 2026-07-29. This
    tops him up to what the NEW tier is worth: `new tier amount - already paid`.

    Properties that make it safe to call from every sync path:
      * It is a DIFFERENCE, never a second full payment: the account's lifetime
        joining Amberium can only ever equal the highest tier it has held. Cancel and
        resubscribe higher pays the gap and nothing more; a DOWNGRADE pays nothing
        (the difference is negative) and never claws anything back.
      * Claimed with a CAS on the tier AND the running total exactly as stored, so two
        concurrent syncs (OAuth callback racing the webhook racing the reconciler)
        pay it exactly once.
      * Same alt guard as the joining payment -- another account already holding this
        Patreon membership's joining stamp refuses the top-up.
      * The 14-day countdown is deliberately NOT re-anchored. The upgrade is extra
        money on top of a cycle that is already running; restarting the clock here
        would push the patron's next payout further away as a punishment for paying
        more. The recurring pass already prices from the CURRENT tier, so their next
        bi-weekly payment is the new tier's amount on the original schedule.

    Returns the Amberium it paid, 0 for nothing owed. Never raises."""
    u = user or {}
    uid = u.get("id")
    if not uid or u.get("patreon_patron_status") != "active_patron":
        return 0
    if not u.get("patreon_welcome_amber_at"):
        # Never had a joining payment at all -- that is _patreon_pay_welcome_amber's
        # job, and paying here too would double it.
        return 0
    tier_name = u.get("patreon_tier_name")
    tier_key = _patreon_tier_key(tier_name)
    owed = PATREON_TIER_AMBER.get(tier_key) or 0
    if owed <= 0:
        return 0
    already = _patreon_welcome_amber_paid(u)
    if already is None:
        # Stamped as paid but with no record of HOW MUCH. Paying a difference against an
        # assumed zero would mint a second full joining payment, so this refuses and says
        # so once per pass rather than guessing with someone's money.
        logger.warning("[patreon] upgrade amber refused: user %s has a joining stamp but "
                       "no recorded amount or tier", uid)
        return 0
    delta = owed - already
    if delta <= 0:
        return 0
    pid = str(u.get("patreon_id") or "")
    if pid:
        twin = await db.users.find_one(
            {"id": {"$ne": uid}, "patreon_welcome_amber_patreon_id": pid},
            {"_id": 0, "id": 1})
        if twin:
            logger.warning("[patreon] upgrade amber refused: patreon %s already claimed "
                           "the joining payment on user %s", pid, twin.get("id"))
            return 0
    stored_total = u.get("patreon_welcome_amber_total")
    stamp = now_iso()
    try:
        res = await db.users.update_one(
            {"id": uid,
             "patreon_patron_status": "active_patron",
             # Price and pay the SAME tier: an upgrade landing between the read above
             # and this write must not pay the older, smaller difference.
             "patreon_tier_name": tier_name,
             "patreon_welcome_amber_at": {"$exists": True},
             "patreon_welcome_amber_tier": u.get("patreon_welcome_amber_tier"),
             # Missing and null both mean "derive from the tier key" -- $in matches
             # an absent field, a plain equality on None would not.
             "patreon_welcome_amber_total": (stored_total if stored_total is not None
                                             else {"$in": [None]})},
            {"$inc": {"vip_coins": delta},
             "$set": {"patreon_welcome_amber_tier": tier_key,
                      "patreon_welcome_amber_total": owed,
                      "patreon_welcome_amber_upgraded_at": stamp}})
    except Exception as e:
        logger.warning(f"[patreon] upgrade amber write: {e}")
        return 0
    if getattr(res, "modified_count", 0) != 1:
        return 0
    logger.info("[patreon] upgrade amber %s paid user=%s (%s -> %s, already %s of %s)",
                delta, uid, u.get("patreon_welcome_amber_tier"), tier_key, already, owed)
    try:
        await add_transaction(uid, "vip", delta, "reward",
                              f"Patreon {tier_key} Amberium por mejora de nivel")
        await add_log(u.get("persona_name") or "—", "amber_payout", tier_key,
                      {"amount": delta, "periods": 0, "upgrade": True,
                       "from_tier": u.get("patreon_welcome_amber_tier"),
                       "already_paid": already, "user_id": uid})
    except Exception as e:
        logger.warning(f"[patreon] upgrade amber log: {e}")
    _fire(_patreon_notify_payout(u.get("discord_id"), delta, tier_name or "", upgrade=True))
    return delta


async def _patreon_payout_one(u, nowt, period) -> int:
    """One patron's turn in the bi-weekly pass. Split out of `amber_payout_loop` so the
    loop can contain a bad row per user (an escape used to skip every patron behind it
    AND the streamer pass that runs afterwards) and so the money path can be driven
    directly by tests. Returns the Amberium it paid, 0 for nothing owed."""
    if u.get("amber_payout_paused_at"):
        # Belt and braces. This row is an active patron whose clock is still frozen,
        # so SOMETHING flipped the status back without going through
        # `_after_patreon_status_update` (the link_dead path is the known one). Resume
        # here rather than let the anchor read below price the frozen gap as elapsed
        # cycles and pay for time the account was not entitled to.
        await _amber_resume_cycle(u["id"])
        u = await db.users.find_one({"id": u["id"]}) or u
    tier_key = _patreon_tier_key(u.get("patreon_tier_name"))
    amber = PATREON_TIER_AMBER.get(tier_key)
    if not amber:
        return 0
    # Backstop for the joining payment: a patron whose sync happened before this feature
    # existed (or whose sync raised mid-flight) is paid here instead of waiting a full
    # period. The claim is atomic and once-per-account, and it re-anchors the cycle, so
    # this pass is done with the user once it fires.
    if not u.get("patreon_welcome_amber_at"):
        if await _patreon_pay_welcome_amber(u):
            return amber
    else:
        # Backstop for the upgrade top-up, for the same reason: a patron whose tier
        # moved up while every sync path was failing is squared up here rather than
        # staying short until someone notices.
        top = await _patreon_topup_welcome_amber(u)
        if top:
            u = await db.users.find_one({"id": u["id"]}) or u
    try:
        base = datetime.fromisoformat(u["amber_payout_anchor"])
        if base.tzinfo is None:
            # Every anchor this code writes carries a UTC offset, but a hand-edited or
            # pre-timezone row would otherwise raise on the subtraction below and sit
            # unpaid forever. Naive stamps have always meant UTC here.
            base = base.replace(tzinfo=timezone.utc)
    except Exception:
        return 0
    # Every writer of this field stores a number or nothing today, but a payout pass must
    # not be the thing that dies on a legacy or hand-edited row: a junk value is priced as
    # zero periods paid and REPAIRED by the write below. (An `$inc` would have errored on
    # it, and a count-shaped CAS could never match it, so the row would sit unpaid forever
    # with nothing in the log to say why.)
    raw = u.get("amber_payout_count", None)
    done = int(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw >= 0 else 0
    due = int((nowt - base) / period)  # completed 14-day periods
    if due <= done:
        return 0
    times = due - done
    total = amber * times
    # CAS on the counter EXACTLY as it is stored: a concurrent pass (or a manual sync
    # racing it) can no longer pay the same period twice. A `done` of zero must also match
    # a doc where the field is absent — {$in: [0, None]} matches missing AND null. The new
    # count is $set (not $inc) so it is written from the value this pass priced, which the
    # CAS has just pinned.
    cas = {"id": u["id"],
           "amber_payout_count": {"$in": [0, None]} if raw is None or raw == 0 else raw}
    res = await db.users.update_one(cas, {
        "$inc": {"vip_coins": total},
        "$set": {"amber_payout_count": done + times, "last_amber_payout_at": now_iso()},
    })
    if getattr(res, "modified_count", 0) != 1:
        return 0
    await add_transaction(u["id"], "vip", total, "reward", f"Patreon {tier_key} Amberium quincenal")
    await add_log(u.get("persona_name"), "amber_payout", tier_key, {"amount": total, "periods": times})
    # Announced to the patron the same way the joining payment is. Fired, not awaited: a
    # slow or closed DM must never stall the pass or hold up the next patron's money.
    _fire(_patreon_notify_payout(u.get("discord_id"), total, u.get("patreon_tier_name") or ""))
    return total


async def _streamer_status_for(user):
    """Status payload for the profile Streamer Pack section (display + eligibility)."""
    u = user or {}
    configured = bool(DISCORD_STREAMER_ROLE_ID)
    access = await _patreon_access(u)  # cached live read; keeps discord_streamer_role fresh
    is_streamer = bool(access.get("streamer"))
    discord_linked = bool(u.get("discord_id"))
    ig = access.get("discord", {}).get("in_guild")
    eff_in_guild = ig if ig is not None else bool(u.get("discord_in_guild"))
    app = None
    if u.get("id"):
        app = await db.streamer_applications.find_one({"user_id": u["id"]}, sort=[("created_at", -1)])
    app_public = None
    if app:
        app_public = {"status": app.get("status"), "created_at": app.get("created_at"),
                      "decided_at": app.get("decided_at"), "reason": app.get("reason") or None}
    pending = bool(app and app.get("status") == "pending")
    can_apply = bool(configured and discord_linked and eff_in_guild is True and not is_streamer and not pending)
    next_payout_seconds = None
    if is_streamer and u.get("streamer_amber_anchor"):
        try:
            base = datetime.fromisoformat(u["streamer_amber_anchor"])
            done = int(u.get("streamer_amber_count", 0))
            nxt = base + timedelta(days=PATREON_PAYOUT_DAYS) * (done + 1)
            next_payout_seconds = max(0, int((nxt - datetime.now(timezone.utc)).total_seconds()))
        except Exception:
            next_payout_seconds = None
    return {
        "configured": configured,
        "discord_linked": discord_linked,
        "in_guild": bool(eff_in_guild),
        "is_streamer": is_streamer,
        "can_apply": can_apply,
        "application": app_public,
        "amber_per_payout": STREAMER_AMBER if is_streamer else 0,
        "next_payout_seconds": next_payout_seconds,
        "discord_invite": DISCORD_INVITE_URL or None,
        "multiplier": STREAMER_MULT,
    }


@api_router.get("/streamer/status")
async def streamer_status(user=Depends(get_current_user)):
    return await _streamer_status_for(user)


@api_router.post("/streamer/apply")
async def streamer_apply(body: StreamerApplyInput, user=Depends(get_current_user)):
    if not DISCORD_STREAMER_ROLE_ID:
        raise HTTPException(status_code=400, detail="streamer_disabled")
    did = str(user.get("discord_id") or "")
    if not did:
        raise HTTPException(status_code=400, detail="discord_link_required")
    # Direct live guild/role read — do NOT go through _patreon_access here: it
    # short-circuits owners before setting discord.in_guild, which wrongly reported
    # "discord_required" for the server owner. This works for everyone.
    in_guild, roles = await _discord_member_info(did, force=True)
    if in_guild is None:
        raise HTTPException(status_code=503, detail="discord_unreachable")
    if in_guild is not True:
        raise HTTPException(status_code=400, detail="guild_join_required")
    if _has_streamer_role(roles):
        raise HTTPException(status_code=409, detail="already_streamer")
    existing = await db.streamer_applications.find_one({"user_id": user["id"], "status": "pending"})
    if existing:
        raise HTTPException(status_code=409, detail="already_pending")
    def _clean(s, n):
        return str(s or "").strip()[:n]
    platform = _clean(body.platform, 40)
    channel_url = _clean(body.channel_url, 300)
    about = _clean(body.about, 1000)
    if not platform or not channel_url or len(about) < 10:
        raise HTTPException(status_code=400, detail="incomplete")
    app = {
        "id": new_id(), "user_id": user["id"], "steam_id": user.get("steam_id"),
        "discord_id": str(user.get("discord_id") or ""), "discord_username": user.get("discord_username"),
        "persona_name": user.get("persona_name"),
        "platform": platform, "channel_url": channel_url,
        "followers": _clean(body.followers, 40), "avg_viewers": _clean(body.avg_viewers, 40),
        "about": about, "status": "pending", "created_at": now_iso(),
        "message_id": None, "channel_id": DISCORD_STREAMER_APPS_CHANNEL_ID or None, "posted": False,
    }
    await db.streamer_applications.insert_one(app)
    mid = await _discord_post_application(app)
    if mid:
        await db.streamer_applications.update_one({"id": app["id"]}, {"$set": {"message_id": mid, "posted": True}})
    await add_log(user.get("persona_name"), "streamer_apply", user.get("steam_id"),
                  {"platform": platform, "app_id": app["id"]})
    return {"ok": True, "status": "pending"}


@api_router.post("/internal/streamer/decide")
async def streamer_decide(body: StreamerDecideInput, x_internal_key: str = Header(default="")):
    """Loopback-only decision callback fired by the bot's Approve/Reject buttons.
    Protected by a shared secret. Approve grants the role (idempotent, seeds a fresh
    amber cycle); reject records the outcome. The web owns all role writes + Mongo."""
    # Fail CLOSED on an empty/unset key; constant-time compare (this endpoint is reachable
    # publicly through the Caddy /api/* proxy, so guard the secret against timing probes).
    if not LIN_INTERNAL_KEY or not hmac.compare_digest(
            (x_internal_key or "").encode("utf-8", "ignore"), LIN_INTERNAL_KEY.encode("utf-8", "ignore")):
        raise HTTPException(status_code=403, detail="forbidden")
    action = (body.action or "").strip().lower()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="bad_action")
    app = None
    if body.message_id:
        app = await db.streamer_applications.find_one({"message_id": str(body.message_id)})
    if not app:
        raise HTTPException(status_code=404, detail="not_found")
    persona = app.get("persona_name") or "—"
    did = str(app.get("discord_id") or "")
    if app.get("status") != "pending":
        # Idempotent: already decided (double click / restart) — report current state.
        return {"ok": True, "already": True, "decision": app.get("status"),
                "persona_name": persona, "discord_id": did}
    moderator = body.moderator_name or body.moderator_id or "admin"
    if action == "approve":
        granted = False
        if did and DISCORD_STREAMER_ROLE_ID:
            granted = await _discord_role_call("PUT", did, DISCORD_STREAMER_ROLE_ID)  # idempotent PUT
        if not granted:
            raise HTTPException(status_code=502, detail="role_grant_failed")
        # Atomic claim: only the first of two concurrent approvers flips pending->approved,
        # so the amber seed / log / DM happen exactly once (the PUT above is harmless twice).
        res = await db.streamer_applications.update_one(
            {"id": app["id"], "status": "pending"},
            {"$set": {"status": "approved", "decided_at": now_iso(), "decided_by": moderator}})
        if getattr(res, "modified_count", 0) == 0:
            fresh = await db.streamer_applications.find_one({"id": app["id"]})
            return {"ok": True, "already": True, "decision": (fresh or {}).get("status"),
                    "persona_name": persona, "discord_id": did}
        # Seed a FRESH amber cycle so a re-approval never lump-sum back-pays an idle gap.
        await db.users.update_one({"id": app["user_id"]}, {"$set": {
            "discord_streamer_role": DISCORD_STREAMER_ROLE_ID,
            "streamer_amber_anchor": now_iso(), "streamer_amber_count": 0}})
        _DISCORD_MEMBER_CACHE.pop(did, None)  # gates see the new role on the next check
        # Joining Amberium lands the moment they are approved, and the 14-day clock seeded
        # just above runs from here. Once-per-account, so a re-approval never pays twice.
        paid_welcome = await _streamer_pay_welcome_amber(app["user_id"], did, persona)
        await add_log(persona, "streamer_approved", app.get("steam_id"),
                      {"by": moderator, "app_id": app["id"], "welcome_amber": paid_welcome})
        return {"ok": True, "decision": "approved", "persona_name": persona, "discord_id": did,
                "welcome_amber": STREAMER_AMBER if paid_welcome else 0}
    res = await db.streamer_applications.update_one(
        {"id": app["id"], "status": "pending"},
        {"$set": {"status": "rejected", "decided_at": now_iso(), "decided_by": moderator,
                  "reason": (body.reason or "").strip()[:300] or None}})
    if getattr(res, "modified_count", 0) == 0:
        fresh = await db.streamer_applications.find_one({"id": app["id"]})
        return {"ok": True, "already": True, "decision": (fresh or {}).get("status"),
                "persona_name": persona, "discord_id": did}
    await add_log(persona, "streamer_rejected", app.get("steam_id"),
                  {"by": moderator, "app_id": app["id"]})
    return {"ok": True, "decision": "rejected", "persona_name": persona, "discord_id": did}


async def streamer_repost_loop():
    """Self-heal: re-post any pending application whose Discord message failed to send
    at submit time, so admins always have working Approve/Reject buttons."""
    await asyncio.sleep(45)
    while True:
        try:
            if DISCORD_STREAMER_ROLE_ID and DISCORD_STREAMER_APPS_CHANNEL_ID and DISCORD_BOT_TOKEN:
                async for app in db.streamer_applications.find({"status": "pending", "posted": {"$ne": True}}):
                    mid = await _discord_post_application(app)
                    if mid:
                        await db.streamer_applications.update_one(
                            {"id": app["id"]}, {"$set": {"message_id": mid, "posted": True}})
                    await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning(f"streamer repost loop: {e}")
        await asyncio.sleep(120)


async def maybe_grant_discord_vip(user_id: str):
    """If the user is an active patron, is linked to Discord and in the guild, assign the VIP role via the bot."""
    if not (DISCORD_BOT_TOKEN and DISCORD_GUILD_ID and DISCORD_VIP_ROLE_ID):
        return
    user = await db.users.find_one({"id": user_id})
    if not user or not user.get("discord_id"):
        return
    if user.get("patreon_patron_status") != "active_patron":
        return
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            resp = await hc.put(
                f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/members/{user['discord_id']}/roles/{DISCORD_VIP_ROLE_ID}",
                headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
            )
        if resp.status_code in (200, 204):
            await db.users.update_one({"id": user_id}, {"$set": {"discord_vip_role_granted": True}})
    except Exception as e:
        logger.warning(f"discord role grant error: {e}")


# ---------- Patreon tier -> Discord role auto-sync ----------
# When a member has BOTH accounts linked, the site keeps their Discord roles in step
# with the purchased Patreon tier: the matching tier role (Apex/Elder/Adult/Sub Adult/
# Juvie) plus every non-tier role in the config (Supporter) while the pledge is active.
# Only roles this site granted (tracked in users.discord_site_roles) are ever removed,
# so roles staff hand out manually always survive.

def _tier_role_map():
    """DISCORD_PATREON_ROLES ({role_id: label}) -> ({tier_key: role_id}, [always-on ids]).
    Labels that match no tier key (e.g. Supporter) are granted with every active tier."""
    by_key, extras = {}, []
    for rid, label in DISCORD_PATREON_ROLES.items():
        k = _patreon_tier_key(label)
        if k and k not in by_key:
            by_key[k] = rid
        elif not k:
            extras.append(rid)
    return by_key, extras


async def _discord_role_call(method: str, discord_id: str, role_id: str) -> bool:
    """One role PUT/DELETE via the bot. True on success; failures are logged, never
    raised. A burst 429 is honored once (bounded sleep) so link-time grants land."""
    try:
        url = (f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}"
               f"/members/{discord_id}/roles/{role_id}")
        headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "User-Agent": _DISCORD_UA,
                   "X-Audit-Log-Reason": "Patreon tier sync (laislanublar.net)"}
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
                logger.warning(f"[discord-roles] {method} {role_id} for {discord_id}: 403 — the bot's "
                               "role must sit ABOVE the tier roles and have Manage Roles")
            else:
                logger.warning(f"[discord-roles] {method} {role_id} for {discord_id}: HTTP {r.status_code}")
            break
    except Exception as e:
        logger.warning(f"[discord-roles] {method} {role_id} for {discord_id}: {e}")
    return False


async def sync_discord_tier_roles(user_id: str):
    """Reconcile the configured Discord roles with the user's live Patreon tier.
    Adds what the tier entitles; removes only site-granted roles that are no longer
    entitled. Contained: safe to call from any lane, returns None when not applicable."""
    try:
        if not (DISCORD_TIER_ROLE_SYNC and DISCORD_BOT_TOKEN and DISCORD_GUILD_ID and DISCORD_PATREON_ROLES):
            return None
        user = await db.users.find_one({"id": user_id})
        if not user:
            return None
        discord_id = str(user.get("discord_id") or "")
        granted = {str(r) for r in (user.get("discord_site_roles") or [])}
        if not discord_id:
            if granted:  # Discord was unlinked while roles were still recorded
                await db.users.update_one({"id": user_id}, {"$set": {"discord_site_roles": []}})
            return None
        by_key, extras = _tier_role_map()
        desired = set()
        hold_removals = False
        if user.get("patreon_patron_status") == "active_patron":
            k = _patreon_tier_key(user.get("patreon_tier_name"))
            rid = by_key.get(k)
            if rid:
                desired = {rid, *extras}
            elif user.get("patreon_tier_name"):
                # A PAYING patron whose tier title matches nothing (renamed/new tier):
                # never strip their roles on a config gap — hold and log until mapped.
                hold_removals = True
                logger.warning(f"[discord-roles] active patron tier '{user.get('patreon_tier_name')}' "
                               "matches no configured tier role — holding existing roles")
        in_guild, roles = await _discord_member_info(discord_id, force=True)
        if in_guild is None:
            return None  # Discord unreachable — the resync loop retries later
        if in_guild is False:
            if granted:
                await db.users.update_one({"id": user_id}, {"$set": {"discord_site_roles": []}})
            return None
        current = set(roles or [])
        to_add = sorted(desired - current)
        to_remove = [] if hold_removals else sorted((granted & current) - desired)
        added_ok, removed_ok = set(), set()
        for rid in to_add:
            if await _discord_role_call("PUT", discord_id, rid):
                added_ok.add(rid)
                logger.info(f"[discord-roles] +{DISCORD_PATREON_ROLES.get(rid, rid)} -> "
                            f"{user.get('persona_name')} ({discord_id})")
        for rid in to_remove:
            if await _discord_role_call("DELETE", discord_id, rid):
                removed_ok.add(rid)
                logger.info(f"[discord-roles] -{DISCORD_PATREON_ROLES.get(rid, rid)} -> "
                            f"{user.get('persona_name')} ({discord_id})")
        if added_ok or removed_ok:
            _DISCORD_MEMBER_CACHE.pop(discord_id, None)  # gates see the new roles immediately
        record = sorted(((granted & current) - removed_ok) | added_ok)
        if record != sorted(granted):
            await db.users.update_one({"id": user_id}, {"$set": {
                "discord_site_roles": record, "discord_roles_synced_at": now_iso()}})
        return {"added": sorted(added_ok), "removed": sorted(removed_ok), "held": record}
    except Exception as e:
        logger.warning(f"[discord-roles] sync error for {user_id}: {e}")
        return None


async def _discord_relink_cleanup(user, new_discord_id: str):
    """Linking a DIFFERENT Discord account than the stored one: take the site-granted
    roles off the OLD member and reset the record so the new account starts clean
    (otherwise the stale record could later strip a hand-granted role)."""
    try:
        old_id = str((user or {}).get("discord_id") or "")
        if not old_id or old_id == str(new_discord_id or ""):
            return
        granted = [str(r) for r in ((user or {}).get("discord_site_roles") or [])]
        if granted and DISCORD_BOT_TOKEN and DISCORD_GUILD_ID:
            for rid in granted:
                await _discord_role_call("DELETE", old_id, rid)
            _DISCORD_MEMBER_CACHE.pop(old_id, None)
        if granted:
            await db.users.update_one({"id": user["id"]}, {"$set": {"discord_site_roles": []}})
    except Exception as e:
        logger.warning(f"[discord-roles] relink cleanup error: {e}")


async def _clear_patreon_auth_failures(user):
    """A successful sync resets the dead-link failure bookkeeping."""
    try:
        if (user or {}).get("patreon_sync_fail_count"):
            await db.users.update_one({"id": user["id"]}, {"$unset": {
                "patreon_sync_fail_count": "", "patreon_sync_fail_first": ""}})
    except Exception:
        pass


async def _note_patreon_auth_failure(user):
    """Auth-dead sync (401 and the refresh also failed). After
    PATREON_DEAD_LINK_FAILS consecutive failures spanning PATREON_DEAD_LINK_HOURS,
    the link is declared dead: status flips to link_dead (every benefit gate fails
    closed and the next reconcile revokes the roles) and the dead tokens drop."""
    try:
        uid = (user or {}).get("id")
        if not uid:
            return
        now = datetime.now(timezone.utc)
        u = await db.users.find_one({"id": uid}) or {}
        count = int(u.get("patreon_sync_fail_count") or 0) + 1
        first = u.get("patreon_sync_fail_first") or now.isoformat()
        await db.users.update_one({"id": uid}, {"$set": {
            "patreon_sync_fail_count": count, "patreon_sync_fail_first": first}})
        try:
            first_dt = datetime.fromisoformat(first)
        except Exception:
            first_dt = now
        if count >= PATREON_DEAD_LINK_FAILS and (now - first_dt) >= timedelta(hours=PATREON_DEAD_LINK_HOURS):
            await db.users.update_one({"id": uid}, {
                "$set": {"patreon_patron_status": "link_dead", "patreon_link_dead_at": now.isoformat()},
                "$unset": {"patreon_access_token": "", "patreon_refresh_token": "", "patreon_token_expires_at": ""},
            })
            # This writes a non-active status without going through
            # `_after_patreon_status_update`, so freeze the cycle here too — otherwise a
            # dead link keeps the clock running and the eventual relink back-pays it.
            await _amber_freeze_cycle(uid)
            logger.warning(f"[patreon] link DEAD for {uid} after {count} failed auth syncs — "
                           "benefits revoke on this reconcile pass")
    except Exception as e:
        logger.warning(f"[patreon] failure bookkeeping error: {e}")


async def _patreon_refresh_token(user):
    """Rotate the user's Patreon token pair. Returns the fresh access token or None."""
    rt = (user or {}).get("patreon_refresh_token")
    if not (rt and PATREON_CLIENT_ID and PATREON_CLIENT_SECRET):
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            r = await hc.post("https://www.patreon.com/api/oauth2/token", data={
                "grant_type": "refresh_token", "refresh_token": rt,
                "client_id": PATREON_CLIENT_ID, "client_secret": PATREON_CLIENT_SECRET,
            })
        if r.status_code != 200:
            logger.warning(f"[patreon] token refresh for {(user or {}).get('id')}: HTTP {r.status_code}")
            return None
        td = r.json()
        access = td.get("access_token")
        if not access:
            return None
        upd = {"patreon_access_token": access}
        if td.get("refresh_token"):
            upd["patreon_refresh_token"] = td["refresh_token"]
        try:
            if td.get("expires_in"):
                upd["patreon_token_expires_at"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=int(td["expires_in"]))).isoformat()
        except Exception:
            pass
        await db.users.update_one({"id": user["id"]}, {"$set": upd})
        return access
    except Exception as e:
        logger.warning(f"[patreon] token refresh error for {(user or {}).get('id')}: {e}")
        return None


async def _sync_patreon_with_refresh(user):
    """sync_patreon_for_user with one refresh-and-retry on an expired token.
    Returns (synced, status): synced=False means Patreon was unreachable/unauthorized
    and the stored fields were left untouched; when synced=True, status may still be
    None — a valid link that simply holds no membership to this campaign."""
    access = (user or {}).get("patreon_access_token")
    if not access:
        return (False, None)
    try:
        status = (await sync_patreon_for_user(user["id"], access))[0]
        await _clear_patreon_auth_failures(user)
        return (True, status)
    except PatreonUnauthorized:
        access = await _patreon_refresh_token(user)
        if not access:
            await _note_patreon_auth_failure(user)
            return (False, None)
        try:
            status = (await sync_patreon_for_user(user["id"], access))[0]
            await _clear_patreon_auth_failures(user)
            return (True, status)
        except PatreonUnauthorized:
            await _note_patreon_auth_failure(user)
            return (False, None)
        except Exception as e:
            logger.warning(f"[patreon] resync after refresh failed for {user.get('id')}: {e}")
            return (False, None)
    except Exception as e:
        logger.warning(f"[patreon] sync failed for {(user or {}).get('id')}: {e}")
        return (False, None)


async def patreon_resync_loop():
    """Every LIN_PATREON_RESYNC_HOURS (default 12): re-read each linked patron's live
    tier from Patreon (rotating expired tokens) and reconcile their Discord tier roles,
    so upgrades, downgrades and cancelations apply without anyone clicking Sincronizar."""
    await asyncio.sleep(120)
    while True:
        try:
            n = synced = changed = 0
            cursor = db.users.find({"$or": [
                {"patreon_access_token": {"$exists": True, "$nin": ["", None]}},
                {"discord_site_roles.0": {"$exists": True}},
                {"discord_streamer_role": {"$nin": ["", None]}},
            ]}, {"_id": 0})
            async for u in cursor:
                n += 1
                try:
                    if u.get("patreon_access_token"):
                        ok, _st = await _sync_patreon_with_refresh(u)
                        if ok:
                            synced += 1
                    r = await sync_discord_tier_roles(u["id"])
                    if r and (r.get("added") or r.get("removed")):
                        changed += 1
                    # Streamer Pack parity: a live read reconciles the stored streamer flag,
                    # so a role removed directly in Discord revokes benefits for idle holders too.
                    if u.get("discord_streamer_role"):
                        await _patreon_access(u, force=True)
                except Exception as e:
                    logger.warning(f"[patreon] resync user {u.get('id')}: {e}")
                await asyncio.sleep(0.35)
            if n:
                logger.info(f"[patreon] resync pass: users={n} synced={synced} role_changes={changed}")
        except Exception as e:
            logger.warning(f"[patreon] resync loop error: {e}")
        await asyncio.sleep(max(0.25, PATREON_RESYNC_HOURS) * 3600)


# ---------------------------------------------------------------------------
# Patreon creator-side truth: the campaign member list read with the CREATOR token
# (webhook-pushed and reconciled every few minutes), so the site no longer depends
# on each patron's own OAuth token staying alive, on them clicking Sincronizar, or
# on the 12-hour resync. Mirrors every member into `patreon_members` — including
# people who paid but never linked, who were invisible before.
# ---------------------------------------------------------------------------

def _member_state_from_resource(member, included):
    """Normalize one JSON:API member resource (webhook payload or the campaign
    members endpoint) into the flat shape the appliers eat. The join key is the
    member's Patreon USER id — the same id the OAuth identity call stores in
    `users.patreon_id`."""
    tiers = {i["id"]: (i.get("attributes") or {}).get("title")
             for i in (included or []) if i.get("type") == "tier"}
    a = member.get("attributes") or {}
    rel = member.get("relationships") or {}
    tdata = ((rel.get("currently_entitled_tiers") or {}).get("data")) or []
    titles = [tiers.get((td or {}).get("id")) for td in tdata]
    puser = (((rel.get("user") or {}).get("data")) or {}).get("id")
    raw_status = a.get("patron_status")
    # ★ THE DEMOTION HAPPENS HERE, not in the applier, so `status` means the
    # same thing to the applier, to the mirror and to the reconcile's
    # change-detection. Demoting later would leave `st["status"]` saying
    # active_patron while the stored row said otherwise, and the reconcile would
    # then re-apply every comped member — and re-hit Discord for each of them —
    # on every single pass, forever. Patreon's own word is kept beside it.
    status = _demote_comped_status(raw_status, a.get("last_charge_date"),
                                   a.get("next_charge_date"))
    return {
        "patreon_id": str(puser) if puser else None,
        "member_id": member.get("id"),
        "status": status,
        "status_raw": raw_status,
        "comped": status != raw_status,
        "tier_name": _best_entitled_tier(titles),
        "pledge_cents": a.get("currently_entitled_amount_cents"),
        "last_charge": a.get("last_charge_date"),
        "charge_status": a.get("last_charge_status"),
        "next_charge": a.get("next_charge_date"),
        "since": a.get("pledge_relationship_start"),
        "full_name": a.get("full_name"),
    }


async def _patreon_mirror_upsert(st):
    """Keep the campaign-truth mirror row for one member. Deliberately does NOT
    store email — the join key is the Patreon user id, nothing more is needed."""
    if not st.get("patreon_id"):
        return
    doc = {k: st.get(k) for k in ("member_id", "status", "status_raw", "comped",
                                  "tier_name", "pledge_cents",
                                  "last_charge", "charge_status", "next_charge",
                                  "since", "full_name")}
    doc["updated_at"] = now_iso()
    await db.patreon_members.update_one(
        {"patreon_id": st["patreon_id"]},
        {"$set": doc, "$unset": {"missing_since": ""}}, upsert=True)


async def _apply_patreon_member_state(user_id, st):
    """Write one member's campaign-side truth onto the linked account and run the
    same consequences as an OAuth sync (payout anchor + joining Amberium). Field
    names are identical to `sync_patreon_for_user` so the two sources can never
    fork; link/token fields are never touched here."""
    upd = {"patreon_patron_status": st.get("status"),
           "patreon_tier_name": st.get("tier_name"),
           "patreon_synced_at": now_iso()}
    if st.get("full_name"):
        upd["patreon_name"] = st["full_name"]
    if st.get("pledge_cents") is not None:
        upd["patreon_pledge_cents"] = st["pledge_cents"]
    for k_src, k_dst in (("last_charge", "patreon_last_charge"),
                         ("next_charge", "patreon_next_charge"),
                         ("since", "patreon_since")):
        if st.get(k_src):
            upd[k_dst] = st[k_src]
    await db.users.update_one({"id": user_id}, {"$set": upd})
    await _after_patreon_status_update(user_id, st.get("status"))


async def _patreon_creator_access(force_rotate=False):
    """The creator token used for campaign-wide reads, with rotation persisted in
    settings so a refreshed pair survives restarts (.env only seeds the first one).
    Returns the access token or None; never logs token material."""
    doc = await db.settings.find_one({"_id": "patreon_creator"}) or {}
    access = doc.get("access_token") or PATREON_CREATOR_ACCESS_TOKEN
    refresh = doc.get("refresh_token") or PATREON_CREATOR_REFRESH_TOKEN
    if not force_rotate and access:
        return access
    if not (refresh and PATREON_CLIENT_ID and PATREON_CLIENT_SECRET):
        return access or None
    try:
        async with httpx.AsyncClient(timeout=20) as hc:
            r = await hc.post("https://www.patreon.com/api/oauth2/token", data={
                "grant_type": "refresh_token", "refresh_token": refresh,
                "client_id": PATREON_CLIENT_ID, "client_secret": PATREON_CLIENT_SECRET,
            })
        td = r.json() if r.status_code == 200 else {}
        new_access = td.get("access_token")
        if not new_access:
            logger.warning(f"[patreon] creator token rotation failed HTTP {r.status_code}")
            return None
        await db.settings.update_one({"_id": "patreon_creator"}, {"$set": {
            "access_token": new_access,
            "refresh_token": td.get("refresh_token") or refresh,
            "rotated_at": now_iso(),
        }}, upsert=True)
        logger.info("[patreon] creator token rotated")
        return new_access
    except Exception as e:
        logger.warning(f"[patreon] creator token rotation: {e}")
        return None


async def _patreon_creator_get(url):
    """GET as the creator, rotating the token once on a 401."""
    access = await _patreon_creator_access()
    if not access:
        raise RuntimeError("no creator token available")
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.get(url, headers={"Authorization": f"Bearer {access}"})
    if r.status_code == 401:
        access = await _patreon_creator_access(force_rotate=True)
        if not access:
            raise RuntimeError("creator token rotation failed")
        async with httpx.AsyncClient(timeout=20) as hc:
            r = await hc.get(url, headers={"Authorization": f"Bearer {access}"})
    return r


_PATREON_WEBHOOK_TRIGGERS = ["members:create", "members:update", "members:delete",
                             "members:pledge:create", "members:pledge:update",
                             "members:pledge:delete"]


async def _patreon_ensure_webhook():
    """Adopt or register the members webhook on the campaign and store its secret
    for signature checks; un-pause it if Patreon paused it after past failures.
    Best-effort — the reconcile loop re-derives everything if this cannot run."""
    if not (PUBLIC_BASE_URL.startswith("https://") and PATREON_CAMPAIGN_ID):
        logger.info("[patreon] webhook registration skipped (needs https PUBLIC_BASE_URL + campaign id)")
        return False
    uri = f"{PUBLIC_BASE_URL}/api/patreon/webhook"
    try:
        r = await _patreon_creator_get(
            "https://www.patreon.com/api/oauth2/v2/webhooks?fields%5Bwebhook%5D=uri,secret,paused,triggers")
        if r.status_code != 200:
            logger.warning(f"[patreon] webhook list HTTP {r.status_code}")
            return False
        mine = None
        for w in (r.json().get("data") or []):
            if (w.get("attributes") or {}).get("uri") == uri:
                mine = w
                break
        access = await _patreon_creator_access()
        headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/vnd.api+json"}
        if mine is None:
            body = {"data": {"type": "webhook",
                             "attributes": {"triggers": _PATREON_WEBHOOK_TRIGGERS, "uri": uri},
                             "relationships": {"campaign": {"data": {
                                 "type": "campaign", "id": PATREON_CAMPAIGN_ID}}}}}
            async with httpx.AsyncClient(timeout=20) as hc:
                cr = await hc.post("https://www.patreon.com/api/oauth2/v2/webhooks",
                                   headers=headers, json=body)
            if cr.status_code not in (200, 201):
                logger.warning(f"[patreon] webhook create HTTP {cr.status_code}")
                return False
            mine = cr.json().get("data") or {}
            logger.info("[patreon] webhook registered for members events")
        secret = (mine.get("attributes") or {}).get("secret")
        if secret:
            await db.settings.update_one({"_id": "patreon_webhook"}, {"$set": {
                "uri": uri, "secret": secret, "webhook_id": mine.get("id"),
                "updated_at": now_iso(),
            }}, upsert=True)
        if (mine.get("attributes") or {}).get("paused"):
            body = {"data": {"id": mine.get("id"), "type": "webhook",
                             "attributes": {"paused": False}}}
            async with httpx.AsyncClient(timeout=20) as hc:
                pr = await hc.patch("https://www.patreon.com/api/oauth2/v2/webhooks/%s" % mine.get("id"),
                                    headers=headers, json=body)
            logger.info(f"[patreon] webhook was paused; unpause HTTP {pr.status_code}")
        return bool(secret)
    except Exception as e:
        logger.warning(f"[patreon] webhook registration: {e}")
        return False


async def _patreon_webhook_handle(raw, signature, event):
    """The whole webhook path, separated from the route so it is drivable directly:
    verify the MD5-HMAC signature Patreon sends, mirror the member, and apply it to
    the linked account if there is one. Returns (http_status, detail). Processing
    errors still return 200 — Patreon pauses a webhook that keeps failing, and the
    reconcile loop re-derives the same truth anyway."""
    doc = await db.settings.find_one({"_id": "patreon_webhook"}) or {}
    secret = doc.get("secret") or ""
    if not secret or not signature:
        return 403, "unconfigured"
    want = hmac.new(secret.encode("utf-8"), raw, hashlib.md5).hexdigest()
    if not hmac.compare_digest(want, str(signature).lower()):
        logger.warning(f"[patreon] webhook signature mismatch (event={event})")
        return 403, "bad signature"
    try:
        payload = json.loads(raw.decode("utf-8"))
        member = payload.get("data") or {}
        st = _member_state_from_resource(member, payload.get("included"))
        await _patreon_mirror_upsert(st)
        applied = False
        if st.get("patreon_id"):
            u = await db.users.find_one({"patreon_id": st["patreon_id"]})
            if u:
                await _apply_patreon_member_state(u["id"], st)
                await sync_discord_tier_roles(u["id"])
                applied = True
        logger.info(f"[patreon] webhook {event} patreon_id={st.get('patreon_id')} "
                    f"status={st.get('status')} tier={st.get('tier_name')} applied={applied}")
    except Exception as e:
        logger.warning(f"[patreon] webhook processing: {e}")
    return 200, "ok"


@api_router.post("/patreon/webhook")
async def patreon_webhook(request: Request):
    raw = await request.body()
    status, detail = await _patreon_webhook_handle(
        raw, request.headers.get("X-Patreon-Signature", ""),
        request.headers.get("X-Patreon-Event", ""))
    if status != 200:
        raise HTTPException(status_code=status, detail=detail)
    return {"ok": True}


async def patreon_creator_reconcile_once():
    """One creator-side pass: page the campaign member list, refresh the mirror,
    and apply any member whose stored status/tier/pledge drifted from campaign
    truth. Wall-clock-bounded and contained per member; returns a summary dict."""
    t0 = time.monotonic()
    deadline = t0 + 120
    url = ("https://www.patreon.com/api/oauth2/v2/campaigns/%s/members?" % PATREON_CAMPAIGN_ID) + urlencode({
        "fields[member]": "patron_status,currently_entitled_amount_cents,last_charge_date,"
                          "last_charge_status,next_charge_date,pledge_relationship_start,full_name",
        "include": "currently_entitled_tiers,user",
        "fields[tier]": "title",
        "fields[user]": "full_name",
        "page[count]": "100",
    })
    states = []
    pages = 0
    while url and pages < 10 and time.monotonic() < deadline:
        r = await _patreon_creator_get(url)
        if r.status_code != 200:
            raise RuntimeError(f"members page HTTP {r.status_code}")
        data = r.json()
        included = data.get("included") or []
        for m in (data.get("data") or []):
            states.append(_member_state_from_resource(m, included))
        url = (data.get("links") or {}).get("next")
        pages += 1
    seen = set()
    for st in states:
        await _patreon_mirror_upsert(st)
        if st.get("patreon_id"):
            seen.add(st["patreon_id"])
    # A member Patreon stopped listing is marked, not deleted — history stays visible.
    if seen:
        await db.patreon_members.update_many(
            {"patreon_id": {"$nin": list(seen)}, "missing_since": {"$exists": False}},
            {"$set": {"missing_since": now_iso()}})
    users_by_pid = {}
    if seen:
        async for u in db.users.find({"patreon_id": {"$in": list(seen)}}, {"_id": 0}):
            users_by_pid[str(u.get("patreon_id"))] = u
    applied = unlinked_paid = 0
    for st in states:
        pid = st.get("patreon_id")
        u = users_by_pid.get(pid) if pid else None
        if not u:
            if st.get("status") == "active_patron":
                unlinked_paid += 1
            continue
        if (u.get("patreon_patron_status") != st.get("status")
                or u.get("patreon_tier_name") != st.get("tier_name")
                or (st.get("pledge_cents") is not None
                    and u.get("patreon_pledge_cents") != st.get("pledge_cents"))):
            try:
                await _apply_patreon_member_state(u["id"], st)
                await sync_discord_tier_roles(u["id"])
                applied += 1
            except Exception as e:
                logger.warning(f"[patreon] reconcile apply {u.get('id')}: {e}")
            await asyncio.sleep(0.35)
    return {"members": len(states), "active": len([s for s in states if s.get("status") == "active_patron"]),
            "linked": len(users_by_pid), "applied": applied, "unlinked_paid": unlinked_paid,
            "ms": int((time.monotonic() - t0) * 1000)}


async def patreon_creator_reconcile_loop():
    """Every LIN_PATREON_RECONCILE_MINUTES (default 15): campaign-truth pass, plus a
    one-time webhook adopt/register at boot. Skips quietly when no creator token or
    campaign id is configured."""
    await asyncio.sleep(180)
    if not PATREON_CAMPAIGN_ID:
        logger.info("[patreon] creator reconcile disabled (no campaign id)")
        return
    try:
        await _patreon_ensure_webhook()
    except Exception as e:
        logger.warning(f"[patreon] webhook ensure: {e}")
    while True:
        try:
            s = await patreon_creator_reconcile_once()
            logger.info(f"[patreon] reconcile pass: members={s['members']} active={s['active']} "
                        f"linked={s['linked']} applied={s['applied']} "
                        f"unlinked_paid={s['unlinked_paid']} ms={s['ms']}")
        except Exception as e:
            logger.warning(f"[patreon] reconcile loop error: {e}")
        await asyncio.sleep(max(60, PATREON_RECONCILE_MINUTES * 60))


def _patreon_amber_owed(user):
    """What this account's joining Amberium SHOULD total, and what it has: the pair the
    audit below reconciles. `owed` is None when the tier cannot be priced at all."""
    tier_key = _patreon_tier_key((user or {}).get("patreon_tier_name"))
    owed = PATREON_TIER_AMBER.get(tier_key)
    paid = _patreon_welcome_amber_paid(user) if (user or {}).get("patreon_welcome_amber_at") else 0
    return tier_key, owed, paid


async def patreon_amber_audit_once(limit: int = 0):
    """One bounded pass of the joining-Amberium LEDGER: for every active patron, what
    the tier they hold is worth versus what they have actually been paid, repairing the
    gap.

    The upgrade top-up and the joining payment each fix the case they can see. This is
    the backstop that owes nothing to any of them noticing: it walks patrons
    OLDEST-AUDITED FIRST and squares them up whatever produced the gap — a webhook that
    never arrived, a sync that raised mid-flight, a tier that changed while Patreon was
    unreachable, a hand-edited row. A shortfall cannot outlive one pass.

    Ported from the Arkadia billing sweep, including its two hard-won properties:
      * BOUNDED — a fixed batch per pass, so a large campaign cannot turn one tick into
        a long-running write storm.
      * The audit stamp is written EVEN WHEN THE REPAIR FAILS, so one permanently bad
        row cannot sit at the head of the queue and starve every account behind it.

    It only ever pays UP to what the held tier is worth: it can never take Amberium
    away, and it can never pay past `PATREON_TIER_AMBER`. Anomalies it cannot price —
    an active patron on a tier name the code does not recognize (a renamed Patreon
    tier), or a row stamped as paid with no record of the amount — are counted and
    named rather than silently skipped, because both are money holes that would
    otherwise be invisible. Contained per user; returns a summary dict."""
    t0 = time.monotonic()
    limit = int(limit or PATREON_AMBER_AUDIT_BATCH)
    checked = repaired = paid_amber = errors = 0
    unpriced = []
    unrecorded = []
    # Ascending sort puts docs MISSING the stamp first, so an account this pass has
    # never looked at is always seen before one it audited a minute ago.
    cur = db.users.find({"patreon_patron_status": "active_patron"}, {"_id": 0}) \
                  .sort("patreon_amber_audited_at", 1).limit(max(1, limit))
    users = [u async for u in cur]
    for u in users:
        checked += 1
        try:
            tier_key, owed, _paid = _patreon_amber_owed(u)
            if owed is None:
                # An active patron whose tier the pricing table cannot name. Every paid
                # gate refuses this account today and nothing says so out loud.
                unpriced.append({"user_id": u.get("id"),
                                 "tier_name": u.get("patreon_tier_name")})
            elif not u.get("patreon_welcome_amber_at"):
                got = await _patreon_pay_welcome_amber(u)
                if got:
                    repaired += 1
                    paid_amber += owed
            elif _patreon_welcome_amber_paid(u) is None:
                unrecorded.append({"user_id": u.get("id"),
                                   "tier_name": u.get("patreon_tier_name")})
            else:
                got = await _patreon_topup_welcome_amber(u)
                if got:
                    repaired += 1
                    paid_amber += got
        except Exception as e:
            errors += 1
            logger.warning("[patreon] amber audit user=%s: %s", u.get("id"), e)
        finally:
            # ★Stamped whatever happened above — see the docstring.
            try:
                await db.users.update_one({"id": u.get("id")},
                                          {"$set": {"patreon_amber_audited_at": now_iso()}})
            except Exception as e:
                logger.warning("[patreon] amber audit stamp user=%s: %s", u.get("id"), e)
    for row in unpriced:
        logger.warning("[patreon] amber audit: active patron %s holds an UNPRICED tier %r "
                       "— every paid benefit refuses this account", row["user_id"], row["tier_name"])
    for row in unrecorded:
        logger.warning("[patreon] amber audit: user %s is stamped as paid with no recorded "
                       "amount — repair left to a human", row["user_id"])
    return {"checked": checked, "repaired": repaired, "amber": paid_amber,
            "unpriced": len(unpriced), "unrecorded": len(unrecorded), "errors": errors,
            "ms": int((time.monotonic() - t0) * 1000)}


async def patreon_amber_audit_loop():
    """Runs the ledger audit every LIN_PATREON_AMBER_AUDIT_MINUTES (default 15). Starts
    after the creator reconcile has had its first pass, so it audits against a mirror
    and tier set that campaign truth has already refreshed."""
    await asyncio.sleep(240)
    while True:
        try:
            s = await patreon_amber_audit_once()
            logger.info("[patreon] amber audit: checked=%s repaired=%s amber=%s "
                        "unpriced=%s unrecorded=%s errors=%s ms=%s",
                        s["checked"], s["repaired"], s["amber"], s["unpriced"],
                        s["unrecorded"], s["errors"], s["ms"])
        except Exception as e:
            logger.warning(f"[patreon] amber audit loop error: {e}")
        await asyncio.sleep(max(60, PATREON_AMBER_AUDIT_MINUTES * 60))


@api_router.get("/admin/patreon/members")
async def admin_patreon_members(admin=Depends(get_admin_user)):
    """Campaign truth vs site links: every Patreon member, who is paying, and which
    paying members never linked a site account (the ones support tickets come from)."""
    rows = [r async for r in db.patreon_members.find({}, {"_id": 0}).sort("since", 1)]
    ids = [r["patreon_id"] for r in rows if r.get("patreon_id")]
    users_by_pid = {}
    if ids:
        async for u in db.users.find({"patreon_id": {"$in": ids}},
                                     {"_id": 0, "id": 1, "patreon_id": 1,
                                      "persona_name": 1, "steam_id": 1,
                                      "patreon_patron_status": 1, "patreon_tier_name": 1,
                                      "patreon_welcome_amber_at": 1,
                                      "patreon_welcome_amber_tier": 1,
                                      "patreon_welcome_amber_total": 1,
                                      "patreon_amber_audited_at": 1}):
            users_by_pid[str(u.get("patreon_id"))] = u
    out = []
    for r in rows:
        u = users_by_pid.get(str(r.get("patreon_id")))
        # The money answer next to the membership: what their tier is worth, what they
        # have been paid, and the gap. This is the column that answers "he says he
        # bought it and got nothing" without opening the database.
        amber = {"owed": None, "paid": None, "short": None, "audited_at": None}
        if u:
            _k, owed, paid = _patreon_amber_owed(u)
            amber = {"owed": owed, "paid": paid,
                     "short": (max(0, owed - paid) if owed is not None and paid is not None
                               else None),
                     "audited_at": u.get("patreon_amber_audited_at")}
        out.append({**r, "linked": bool(u), "amber": amber,
                    "site_user": ({"id": u["id"], "persona_name": u.get("persona_name"),
                                   "steam_id": u.get("steam_id")} if u else None)})
    active = [r for r in out if r.get("status") == "active_patron"]
    short = [r for r in out if (r["amber"]["short"] or 0) > 0]
    return {"members": out, "summary": {
        "total": len(out), "active": len(active),
        "active_unlinked": len([r for r in active if not r["linked"]]),
        # Non-zero here means somebody is owed money right now. The audit pass drives
        # it back to zero on its own; a value that STAYS non-zero is a real fault.
        "amber_short_accounts": len(short),
        "amber_short_total": sum(r["amber"]["short"] or 0 for r in short),
        "amber_unpriced_active": len([r for r in active if r["linked"]
                                      and r["amber"]["owed"] is None]),
    }}


@api_router.get("/discord/callback")
async def discord_callback(request: Request):
    params = dict(request.query_params)
    state = params.get("state", "")
    code = params.get("code")
    user_id = read_state(state, "discord")
    if not user_id or not code:
        return _front_redirect("discord", "error", "invalid")
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            tr = await hc.post("https://discord.com/api/v10/oauth2/token", data={
                "code": code, "grant_type": "authorization_code",
                "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
                "redirect_uri": f"{PUBLIC_BASE_URL}/api/discord/callback",
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        td = tr.json()
        access = td.get("access_token")
        if not access:
            # invalid_client here = the app's client secret in .env is wrong/rotated.
            # Never log the raw body — a partial token response could carry a live token.
            logger.warning(f"[discord] token exchange failed HTTP {tr.status_code}: "
                           f"error={td.get('error')} desc={td.get('error_description')}")
            return _front_redirect("discord", "error", "token")
        async with httpx.AsyncClient(timeout=15) as hc:
            ur = await hc.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bearer {access}"})
        du = ur.json()
        username = du.get("global_name") or du.get("username")
        discord_id = du.get("id")
        in_guild = False
        if DISCORD_GUILD_ID:
            try:
                async with httpx.AsyncClient(timeout=15) as hc:
                    gr = await hc.get(f"https://discord.com/api/v10/users/@me/guilds/{DISCORD_GUILD_ID}/member",
                                      headers={"Authorization": f"Bearer {access}"})
                in_guild = gr.status_code == 200
            except Exception:
                in_guild = False
        prev = await db.users.find_one({"id": user_id})
        if prev:
            # Re-linking a different account: clean the OLD member + record first.
            await _discord_relink_cleanup(prev, discord_id)
        await db.users.update_one({"id": user_id}, {"$set": {
            "discord_id": discord_id, "discord_username": username, "discord_in_guild": in_guild,
        }})
        await maybe_grant_discord_vip(user_id)
        # Already an active patron? Their tier roles land the moment Discord links.
        await sync_discord_tier_roles(user_id)
        u = await db.users.find_one({"id": user_id})
        # Detect the Patreon tier role right at link time so access is immediate.
        await _patreon_access(u, force=True)
        await add_log(u.get("persona_name"), "link_discord", username)
    except Exception as e:
        logger.warning(f"discord callback error: {e}")
        return _front_redirect("discord", "error", "exception")
    return _front_redirect("discord", "ok")


@api_router.post("/discord/unlink")
async def discord_unlink(user=Depends(get_current_user)):
    # Take back site-granted roles while we still know the member id.
    try:
        # Re-read: a resync pass may have granted roles after this request's doc snapshot.
        user = await db.users.find_one({"id": user["id"]}) or user
        granted = [str(r) for r in (user.get("discord_site_roles") or [])]
        # The streamer role is granted directly (not tracked in discord_site_roles), so
        # strip it here too — unlinking must give up a site-granted role like any other.
        if user.get("discord_streamer_role") and DISCORD_STREAMER_ROLE_ID:
            granted = granted + [DISCORD_STREAMER_ROLE_ID]
        did = str(user.get("discord_id") or "")
        if did and granted and DISCORD_BOT_TOKEN and DISCORD_GUILD_ID:
            for rid in granted:
                await _discord_role_call("DELETE", did, rid)
            _DISCORD_MEMBER_CACHE.pop(did, None)
    except Exception as e:
        logger.warning(f"[discord-roles] unlink cleanup error: {e}")
    # Clear the streamer flag + amber clock too, else _is_subscriber (which reads the
    # STORED flag with no live call) would keep the streamer benefits alive forever once
    # discord_id is gone and _patreon_access can no longer re-check the role.
    await db.users.update_one({"id": user["id"]}, {"$unset": {
        "discord_id": "", "discord_username": "", "discord_in_guild": "", "discord_vip_role_granted": "",
        "discord_tier_role": "", "discord_site_roles": "", "discord_roles_synced_at": "",
        "discord_streamer_role": "", "streamer_amber_anchor": "", "streamer_amber_count": "",
    }})
    return {"success": True}


# ---------- seeding ----------
import math as _math

# ---------- the store's mutation picker ----------
# BUILT FROM mutation_catalog -- the same module that drives the vault editor,
# the diet rule and the redeem write. Until 2026-07-26 this was a hand-written
# 16-entry list with its own keys, English descriptions and costs, so the store
# offered 16 names while the editor offered 36: a Triceratops buyer was shown 11
# mutations where the editor showed that same Trike 30. Generating it from the
# catalog is what makes the two structurally unable to drift again.
#
# NEVER ADD A NAME HERE BY HAND. Add it to mutation_catalog -- and only after the
# MOD half is LIVE. The mod's validator (LaIslaNublarMutV2.known) rejects a name
# it does not know slot-by-slot on redeem AND sets mutations_ok false, and a
# not-ok verdict keeps the vault row alive next to a dino that already spawned.
# Offering a mutation the live mod refuses is a duplicate-dino path, not a
# cosmetic bug.
#
# KEYS ARE PERSISTED: db.inventory rows store these keys, and
# _inventory_dino_mutation_keys silently DROPS a key it cannot resolve -- i.e. a
# vanished key is a player losing a stored mutation. Every key the store has ever
# sold is therefore pinned in _LEGACY_STORE_MUTATIONS and force-kept, and the
# generator reproduces them exactly (all 16 were already
# lower(name).replace(" ", "_")).


def _store_mutation_key(name: str) -> str:
    return str(name).lower().replace(" ", "_")


# key -> (display name, PrimeMeat cost, original English blurb). These 16 are the
# only ones a purchase row can already reference. NOTE the store has never
# charged `cost` -- a dino's price is the store item's own price plus
# PRIME_SURCHARGE -- so it is published metadata, not money; new names take
# _DEFAULT_MUTATION_COST rather than inventing prices.
_LEGACY_STORE_MUTATIONS: dict[str, tuple[str, int, str]] = {
    "cellular_regeneration": ("Cellular Regeneration", 15, "Recovers health 15% faster."),
    "congenital_hypoalgesia": ("Congenital Hypoalgesia", 18, "Reduce 15% incoming damage when fighting larger species."),
    "efficient_digestion": ("Efficient Digestion", 12, "Food drains 20% slower."),
    "enlarged_meniscus": ("Enlarged Meniscus", 10, "Fall damage hits stamina before draining health."),
    "epidermal_fibrosis": ("Epidermal Fibrosis", 14, "15% increased bleed resistance."),
    "featherweight": ("Featherweight", 8, "Footprints fade 50% faster."),
    "hydrodynamic": ("Hydrodynamic", 10, "15% increased swimming speed."),
    "photosynthetic_tissue": ("Photosynthetic Tissue", 12, "5% faster health recovery and movement speed in daytime."),
    "accelerated_prey_drive": ("Accelerated Prey Drive", 16, "Deal 10% more damage to animals below 35% health."),
    "hematophagy": ("Hematophagy", 12, "Restore 15% thirst while eating corpses."),
    "hemomania": ("Hemomania", 14, "Deal 5% extra damage to bleeding targets."),
    "hypermetabolic_inanition": ("Hypermetabolic Inanition", 15, "The less hunger you have, the more damage you deal."),
    "enhanced_digestion": ("Enhanced Digestion", 20, "Nutrition decays even slower (unlocked via a good diet)."),
    "multichambered_lungs": ("Multichambered Lungs", 18, "Increased maximum stamina pool."),
    "reinforced_tendons": ("Reinforced Tendons", 12, "Reduced stamina cost when jumping."),
    "osteophagic": ("Osteophagic", 14, "Consume bones to regenerate fractures faster."),
}
_DEFAULT_MUTATION_COST = 12


def _build_store_mutations() -> list[dict]:
    """The catalog as store records, sorted by name (the vault editor sorts the
    same way, so a player reads one order on both screens).

    Descriptions come from the catalog, which is Spanish -- the rest of this site
    is Spanish and the picker was the last surface still showing English. A
    legacy name the catalog somehow does not carry keeps its original blurb
    rather than rendering blank.

    Never raises: this runs at import, and a bad row must not take the backend
    down. A legacy key the catalog stops producing is force-kept and logged.
    """
    names = set(mutation_catalog.PICKABLE)
    for key, (name, _cost, _blurb) in _LEGACY_STORE_MUTATIONS.items():
        if name not in names:
            logger.error(
                "[store] legacy mutation %r (%s) is no longer in mutation_catalog.PICKABLE; "
                "keeping it sellable so stored inventory keys still resolve", key, name)
            names.add(name)
    out = []
    for name in sorted(names):
        key = _store_mutation_key(name)
        legacy = _LEGACY_STORE_MUTATIONS.get(key)
        desc = mutation_catalog.DESCRIPTIONS.get(name) or (legacy[2] if legacy else "")
        out.append({
            "key": key,
            "name": name,
            "desc": desc,
            "cost": legacy[1] if legacy else _DEFAULT_MUTATION_COST,
        })
    produced = {m["key"] for m in out}
    lost = sorted(set(_LEGACY_STORE_MUTATIONS) - produced)
    if lost:
        # Only reachable if a legacy display name stops round-tripping through
        # _store_mutation_key. Re-add the raw legacy record so no inventory row
        # is ever orphaned.
        logger.error("[store] legacy mutation keys not regenerated: %s", lost)
        for key in lost:
            name, cost, blurb = _LEGACY_STORE_MUTATIONS[key]
            out.append({"key": key, "name": name, "desc": blurb, "cost": cost})
        out.sort(key=lambda m: m["name"])
    return out


MUTATIONS = _build_store_mutations()
MUTATIONS_BY_KEY = {m["key"]: m for m in MUTATIONS}
MAX_MUTATION_SLOTS = 6


@api_router.get("/skins")
async def list_skins():
    return [
        {"key": k, "name": v["name"], "rarity": v["rarity"],
         "color": v.get("color"), "theme": v.get("theme"), "evrima": v.get("evrima")}
        for k, v in seed_data.SKINS.items()
    ]


@api_router.get("/mutations")
async def list_mutations(dino_slug: Optional[str] = None):
    """The mutation catalog; with ?dino_slug=, only what that species can carry.

    The store picker offered all 16 to everyone while the purchase checked only
    that the key existed, so a Triceratops could be sold Hematophagy. The vault
    lane enforces the game's diet rule, so the picker has to agree with it.
    Unknown/absent slug returns the full list (unchanged default).
    """
    dino_class = _EVRIMA_CLASS_BY_SLUG.get(dino_slug or "")
    if not dino_class:
        return {"mutations": MUTATIONS, "max_slots": MAX_MUTATION_SLOTS}
    allowed = mutation_catalog.allowed_names_for_class(dino_class)
    muts = [m for m in MUTATIONS
            if (mutation_catalog.canonical_mutation_name(m["name"]) or "") in allowed]
    return {"mutations": muts, "max_slots": MAX_MUTATION_SLOTS}


def _live_active_dino(ad: dict) -> dict:
    """Compute live-simulated stats + a wandering position for the active dino."""
    now = datetime.now(timezone.utc)
    set_at = datetime.fromisoformat(ad["set_at"])
    elapsed_s = (now - set_at).total_seconds()
    elapsed_m = elapsed_s / 60.0
    muts = set(ad.get("mutations", []))
    efficient = 0.8 if ("efficient_digestion" in muts or "enhanced_digestion" in muts) else 1.0
    growth_rate = 0.6
    growth = min(100.0, ad.get("base_growth", 5) + elapsed_m * growth_rate)
    # hunger decays from the last time the dino ate (drop body) — falls back to deploy time.
    hunger_anchor = datetime.fromisoformat(ad.get("fed_at") or ad["set_at"])
    hunger_m = (now - hunger_anchor).total_seconds() / 60.0
    hunger = max(0.0, 100 - hunger_m * 0.8 * efficient)
    thirst = max(0.0, 100 - elapsed_m * 1.1 * efficient)
    starving = hunger <= 0 or thirst <= 0
    max_health = 100
    health = max(5.0, max_health - elapsed_m * 1.5) if starving else min(max_health, 70 + elapsed_m * 2)
    stamina = 60 + 40 * _math.sin(elapsed_s / 25.0)
    # wandering position across the map (0..100 %)
    x = 50 + 34 * _math.sin(elapsed_s / 47.0) + 6 * _math.cos(elapsed_s / 13.0)
    y = 50 + 28 * _math.cos(elapsed_s / 61.0) + 5 * _math.sin(elapsed_s / 17.0)
    x = max(4, min(96, x)); y = max(4, min(96, y))
    g = round(growth, 1); h = round(hunger)
    paused = bool(ad.get("growth_paused"))
    prime = bool(ad.get("prime"))
    if paused:
        # Safe-log: freeze growth & vitals at the snapshot taken when paused.
        g = round(ad.get("paused_growth", ad.get("base_growth", 5)), 1)
        h = round(ad.get("paused_hunger", h))
        health = 100; stamina = 100; starving = False
        thirst = ad.get("paused_thirst", thirst)
        x = ad.get("paused_x", x); y = ad.get("paused_y", y)
    return {
        **{k: ad[k] for k in ("slug", "name", "image", "type", "diet", "rarity")},
        "mutations": [MUTATIONS_BY_KEY[m] for m in ad.get("mutations", []) if m in MUTATIONS_BY_KEY],
        "skin": ad.get("active_skin"),
        "set_at": ad["set_at"], "base_stats": ad.get("base_stats", {}),
        "bodies_dropped": ad.get("bodies_dropped", 0),
        "recovery_id": ad.get("recovery_id"),
        "prime": prime,
        "growth_paused": paused,
        "can_drop_body": (not paused) and h < 30 and g < 60,
        "live": {
            "health": round(health), "stamina": round(max(0, min(100, stamina))),
            "hunger": h, "thirst": round(thirst), "growth": g,
            "max_health": max_health, "starving": starving,
        },
        "position": {"x": round(x, 1), "y": round(y, 1)},
    }


async def _upsert_dino_record(user, ad, growth, status):
    """Maintain a recoverable record of a dino keyed by its recovery_id."""
    rid = ad.get("recovery_id")
    if not rid:
        return
    now = now_iso()
    base = {
        "user_id": user["id"], "user_name": user.get("persona_name"),
        "slug": ad.get("slug"), "name": ad.get("name"), "rarity": ad.get("rarity"),
        "image": ad.get("image"), "diet": ad.get("diet"), "type": ad.get("type"),
        "growth": round(growth, 1), "mutations": ad.get("mutations", []),
        "status": status, "updated_at": now,
    }
    if status in ("slain", "lost"):
        base["lost_at"] = now
    await db.dino_records.update_one(
        {"recovery_id": rid},
        {"$set": base, "$setOnInsert": {"id": new_id(), "recovery_id": rid, "recovered": False, "created_at": now}},
        upsert=True,
    )


@api_router.get("/profile/dino-records")
async def my_dino_records(user=Depends(get_current_user)):
    items = await db.dino_records.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(300)
    return items


@api_router.get("/profile/redemptions")
async def my_redemptions(user=Depends(get_current_user)):
    items = await db.code_redemptions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


# ---------- friends & teleport ----------
# Presence is REAL: a friend is online when their Steam account is connected to
# the game server (RCON player list, 10s cache) or the mod has a fresh
# players.json row for them. The old web-sim active_dino flag is only a display
# fallback for the dino card, never the presence source (it kept everyone
# "Desconectado" while they were actually playing).
TELEPORT_REQUEST_TTL_SECS = 120       # pending request lifetime
TELEPORT_RESOLVED_KEEP_SECS = 120     # keep accepted/declined rows briefly so the requester's poll sees the outcome
TELEPORT_COUNTDOWN_ORPHAN_SECS = 20   # countdown rows this far past their end with no runner = backend bounced mid-hold


def _teleport_countdown_secs() -> int:
    """Owner rule 2026-07-18: accepting starts a hold (default 10 s) during
    which BOTH players must stand still before the teleport actually fires."""
    raw = (os.environ.get("LIN_TELEPORT_COUNTDOWN_SECS", "10") or "10").strip()
    try:
        return min(60, max(3, int(raw)))
    except ValueError:
        return 10


def _teleport_move_tolerance() -> float:
    """Movement threshold in engine units (~1 uu = 1 cm). Standing-still jitter
    stays well under this; a real step breaks it immediately."""
    raw = (os.environ.get("LIN_TELEPORT_MOVE_TOLERANCE_UU", "150") or "150").strip()
    try:
        return min(2000.0, max(10.0, float(raw)))
    except ValueError:
        return 150.0


def _teleport_min_stamina_pct() -> float:
    raw = (os.environ.get("LIN_TELEPORT_MIN_STAMINA_PCT", "0.60") or "0.60").strip()
    try:
        return min(1.0, max(0.0, float(raw)))
    except ValueError:
        return 0.60


def _teleport_stamina_gate(row, who: str | None = None):
    """Owner rule 2026-07-18: the player who teleports needs MORE than 60%
    stamina. Raises the named Spanish reason; fails closed on unreadable bars."""
    need = _teleport_min_stamina_pct()
    if need <= 0:
        return
    label = f"{who} necesita" if who else "necesitas"
    try:
        mx = float(row.get("max_stamina") or 0)
        cur = float(row.get("stamina") or 0)
    except (TypeError, ValueError):
        mx, cur = 0.0, 0.0
    if mx <= 0:
        raise HTTPException(status_code=400, detail="El servidor aún no cargó la energía del dino. Espera unos segundos.")
    pct = cur / mx
    if pct <= need + 1e-6:
        if who:
            msg = f"Energía de {who}: {pct*100:.0f}% — necesita más de {need*100:.0f}% para teletransportarse"
        else:
            msg = f"Energía {pct*100:.0f}% — necesitas más de {need*100:.0f}% para teletransportarte"
        raise HTTPException(status_code=400, detail=msg)


# Owner rule 2026-07-29: one friend-teleport per player every 30 minutes.
# The window belongs to the player who actually MOVES (the requester) — the
# friend who accepts is not spending anything of their own.
TELEPORT_COOLDOWN_DEFAULT_SECS = 1800


def _teleport_cooldown_secs():
    raw = os.environ.get("LIN_TELEPORT_COOLDOWN_SECS")
    raw = (raw or "").strip()
    if not raw:
        return TELEPORT_COOLDOWN_DEFAULT_SECS
    try:
        return max(0, int(raw))
    except ValueError:
        return TELEPORT_COOLDOWN_DEFAULT_SECS


def _teleport_cooldown_left(u, now: float | None = None) -> int:
    """Whole seconds until this user may teleport again; 0 when ready. Never
    raises — a missing or junk stamp reads as READY rather than locking a
    player out of the feature forever."""
    cooldown = _teleport_cooldown_secs()
    if cooldown <= 0:
        return 0
    try:
        last = float((u or {}).get("teleport_last_at") or 0)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(last) or last <= 0:
        return 0
    return max(0, int(round(last + cooldown - (time.time() if now is None else now))))


def _teleport_wait_phrase(wait: int) -> str:
    """'27 minutos' / '45 segundos'. Half an hour printed as 1.783 segundos is
    noise — anything from a minute up is said in minutes, rounded up so the
    number never promises sooner than it is."""
    if wait >= 60:
        mins = int(math.ceil(wait / 60.0))
        return f"{mins} minuto" if mins == 1 else f"{mins} minutos"
    secs = max(1, int(wait))
    return f"{secs} segundo" if secs == 1 else f"{secs} segundos"


async def _release_teleport_claim(user_id: str, claim_at: float, prev_stamp) -> None:
    """Hand back a cooldown window that was claimed for a teleport that never
    actually fired. Guarded on the exact stamp we wrote, so a newer claim is
    never clobbered. Best effort and fully contained: losing a release costs one
    player one cooldown, and must never take down the countdown runner."""
    try:
        if prev_stamp is None:
            await db.users.update_one({"id": user_id, "teleport_last_at": claim_at},
                                      {"$unset": {"teleport_last_at": ""}})
        else:
            await db.users.update_one({"id": user_id, "teleport_last_at": claim_at},
                                      {"$set": {"teleport_last_at": prev_stamp}})
    except Exception:
        logger.exception(f"[friends] teleport cooldown release failed user={user_id}")


async def _relationship(a, b):
    return await db.friends.find_one({"$or": [
        {"requester_id": a, "addressee_id": b},
        {"requester_id": b, "addressee_id": a},
    ]}, {"_id": 0})


def _row_pct(row, cur_key, max_key):
    """players.json current/max pair -> 0-100 percent, or None."""
    try:
        mx = float(row.get(max_key) or 0)
        if mx > 0:
            return max(0.0, min(100.0, float(row.get(cur_key) or 0) / mx * 100.0))
    except (TypeError, ValueError):
        pass
    return None


async def _friend_presence(u):
    """(online, dino_card) for a friend. Never raises: presence degrades to the
    web-sim flag only when both the mod feed and RCON are unavailable."""
    sid = str(u.get("steam_id") or "").strip()
    row = game_ipc.read_player_display(sid) if sid else None
    online = isinstance(row, dict)
    if not online:
        try:
            ids, names = await _rcon_online_players()
            online = bool(sid and sid in ids)
            if not online:
                pname = (u.get("persona_name") or "").strip().lower()
                online = bool(pname and pname in names)
            if not online and not rcon_client.is_configured() and not game_ipc.mod_alive():
                online = bool(u.get("active_dino"))  # both real sources down: legacy proxy
        except Exception:
            online = False
    dino = None
    if isinstance(row, dict):
        ad = u.get("active_dino")
        if ad:
            try:
                real = _real_active_dino(u, ad)
            except Exception:
                real = None
            if real:
                live = real.get("live") or {}
                dino = {"name": real.get("name"), "slug": real.get("slug"),
                        "health": live.get("health", 0), "stamina": live.get("stamina", 0),
                        "position": real.get("position")}
        if dino is None:
            species = str(row.get("dino") or "").replace("BP_", "").replace("_C", "").strip() or "Dinosaurio"
            hp, st = _row_pct(row, "health", "max_health"), _row_pct(row, "stamina", "max_stamina")
            pos = None
            try:
                pct = teleport_presets.to_percent(row.get("x"), row.get("y"))
                if pct is not None:
                    pos = {"x": round(pct[0], 1), "y": round(pct[1], 1)}
            except Exception:
                pos = None
            dino = {"name": species, "slug": None,
                    "health": round(hp) if hp is not None else 0,
                    "stamina": round(st) if st is not None else 0,
                    "position": pos}
    return online, dino


async def _friend_card_from_user(u):
    if not u:
        return None
    online, dino = await _friend_presence(u)
    return {"id": u["id"], "persona_name": u.get("persona_name"), "avatar": u.get("avatar"),
            "rank": u.get("rank"), "online": online, "dino": dino}


@api_router.get("/friends/search")
async def friends_search(q: str = "", user=Depends(get_current_user)):
    q = (q or "").strip()
    if len(q) < 2:
        return []
    rx = {"$regex": re.escape(q), "$options": "i"}
    users = await db.users.find({"persona_name": rx, "id": {"$ne": user["id"]}}, {"_id": 0}).to_list(20)
    out = []
    for u in users:
        rel = await _relationship(user["id"], u["id"])
        online, _ = await _friend_presence(u)
        out.append({"id": u["id"], "persona_name": u.get("persona_name"), "avatar": u.get("avatar"),
                    "online": online,
                    "status": rel["status"] if rel else None,
                    "outgoing": bool(rel and rel["status"] == "pending" and rel["requester_id"] == user["id"])})
    return out


@api_router.get("/friends/steam")
async def steam_friends(user=Depends(get_current_user)):
    """Import the signed-in player's Steam friend list. Requires a public friends list on Steam."""
    sid = user.get("steam_id")
    if not sid or not sid.isdigit():
        return {"available": False, "reason": "no_steam", "friends": []}
    if not STEAM_API_KEY:
        return {"available": False, "reason": "no_key", "friends": []}
    try:
        async with httpx.AsyncClient(timeout=12) as hc:
            fr = await hc.get("https://api.steampowered.com/ISteamUser/GetFriendList/v1/",
                              params={"key": STEAM_API_KEY, "steamid": sid, "relationship": "friend"})
            if fr.status_code in (401, 403):
                return {"available": False, "reason": "private", "friends": []}
            fl = (fr.json().get("friendslist") or {}).get("friends", [])
            if not fl:
                return {"available": True, "friends": []}
            ids = [f["steamid"] for f in fl][:150]
            summaries = {}
            for i in range(0, len(ids), 100):
                batch = ids[i:i + 100]
                rs = await hc.get("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
                                  params={"key": STEAM_API_KEY, "steamids": ",".join(batch)})
                for p in (rs.json().get("response") or {}).get("players", []):
                    summaries[p["steamid"]] = p
    except Exception as e:
        logger.warning(f"steam friends fetch failed: {e}")
        return {"available": False, "reason": "error", "friends": []}
    web = {u["steam_id"]: u for u in await db.users.find({"steam_id": {"$in": ids}}, {"_id": 0}).to_list(200)}
    out = []
    for sidf in ids:
        s = summaries.get(sidf, {})
        wu = web.get(sidf)
        rel = await _relationship(user["id"], wu["id"]) if wu else None
        out.append({
            "steam_id": sidf,
            "persona_name": s.get("personaname") or f"Steam {sidf[-4:]}",
            "avatar": s.get("avatarmedium") or s.get("avatar"),
            "last_logoff": s.get("lastlogoff"),
            "steam_online": int(s.get("personastate", 0) or 0) != 0,
            "on_platform": bool(wu),
            "user_id": wu["id"] if wu else None,
            "status": rel["status"] if rel else None,
        })
    out.sort(key=lambda x: (not x["on_platform"], not x["steam_online"], (x["persona_name"] or "").lower()))
    return {"available": True, "friends": out}


@api_router.post("/friends/request")
async def friends_request(data: FriendUserInput, user=Depends(get_current_user)):
    if data.user_id == user["id"]:
        raise HTTPException(status_code=400, detail="No puedes agregarte a ti mismo")
    target = await db.users.find_one({"id": data.user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Jugador no encontrado")
    rel = await _relationship(user["id"], data.user_id)
    if rel:
        if rel["status"] == "accepted":
            raise HTTPException(status_code=400, detail="Ya son amigos")
        raise HTTPException(status_code=400, detail="Ya hay una solicitud pendiente")
    await db.friends.insert_one({
        "id": new_id(), "requester_id": user["id"], "requester_name": user["persona_name"],
        "addressee_id": data.user_id, "addressee_name": target["persona_name"],
        "status": "pending", "created_at": now_iso(),
    })
    return {"success": True}


@api_router.post("/friends/steam-add")
async def friends_steam_add(data: SteamAddInput, user=Depends(get_current_user)):
    """Add ANY Steam user by profile link, custom (vanity) URL or SteamID64 — even non-friends / non-web users."""
    if not STEAM_API_KEY:
        raise HTTPException(status_code=400, detail="Steam no está configurado")
    q = (data.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Pega un enlace de Steam o un SteamID")
    steamid, vanity = None, None
    m = re.search(r"/profiles/(\d{17})", q)
    if m:
        steamid = m.group(1)
    if not steamid:
        m = re.search(r"steamcommunity\.com/id/([^/?#\s]+)", q)
        if m:
            vanity = m.group(1)
    if not steamid and not vanity:
        if re.fullmatch(r"\d{17}", q):
            steamid = q
        else:
            vanity = q  # bare token → treat as custom (vanity) URL name
    async with httpx.AsyncClient(timeout=12) as hc:
        if not steamid and vanity:
            rv = await hc.get("https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/",
                              params={"key": STEAM_API_KEY, "vanityurl": vanity})
            resp = (rv.json().get("response") or {})
            if resp.get("success") == 1:
                steamid = resp.get("steamid")
        if not steamid:
            raise HTTPException(status_code=404, detail="No encontré ese perfil. Usa el enlace completo del perfil o el SteamID de 17 dígitos.")
        rs = await hc.get("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
                          params={"key": STEAM_API_KEY, "steamids": steamid})
        players = (rs.json().get("response") or {}).get("players", [])
    if not players:
        raise HTTPException(status_code=404, detail="No se pudo obtener ese perfil de Steam")
    if steamid == user.get("steam_id"):
        raise HTTPException(status_code=400, detail="Ese eres tú 🙂")
    p = players[0]
    target = await db.users.find_one({"steam_id": steamid}, {"_id": 0})
    if not target:
        uid = new_id()
        target = {
            "id": uid, "steam_id": steamid,
            "persona_name": p.get("personaname") or f"Survivor_{steamid[-4:]}",
            "avatar": p.get("avatarmedium") or p.get("avatar"), "profile_url": p.get("profileurl"),
            "role": "user", "coins": 0, "vip_coins": 0, "playtime_minutes": 0,
            "created_at": now_iso(), "last_login": None, "last_daily_claim": None, "stub": True,
        }
        await db.users.insert_one(target)
    if target["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Ese eres tú 🙂")
    rel = await _relationship(user["id"], target["id"])
    if rel:
        raise HTTPException(status_code=400, detail="Ya son amigos" if rel["status"] == "accepted" else "Ya hay una solicitud pendiente")
    # Adding by Steam identity is treated as a confirmed contact (shows immediately in your list).
    await db.friends.insert_one({
        "id": new_id(), "requester_id": user["id"], "requester_name": user["persona_name"],
        "addressee_id": target["id"], "addressee_name": target["persona_name"],
        "status": "accepted", "created_at": now_iso(), "accepted_at": now_iso(), "via": "steam_add",
    })
    return {"success": True, "persona_name": target["persona_name"], "avatar": target.get("avatar"),
            "on_platform": not target.get("stub", False)}


@api_router.post("/friends/respond")
async def friends_respond(data: FriendRespondInput, user=Depends(get_current_user)):
    rel = await db.friends.find_one({"requester_id": data.user_id, "addressee_id": user["id"], "status": "pending"})
    if not rel:
        raise HTTPException(status_code=404, detail="No hay solicitud pendiente de este jugador")
    if data.accept:
        await db.friends.update_one({"id": rel["id"]}, {"$set": {"status": "accepted", "accepted_at": now_iso()}})
    else:
        await db.friends.delete_one({"id": rel["id"]})
    return {"success": True}


@api_router.delete("/friends/{friend_id}")
async def friends_remove(friend_id: str, user=Depends(get_current_user)):
    rel = await _relationship(user["id"], friend_id)
    if not rel:
        raise HTTPException(status_code=404, detail="No estas conectado con este jugador")
    await db.friends.delete_one({"id": rel["id"]})
    return {"success": True}


@api_router.get("/friends")
async def friends_list(user=Depends(get_current_user)):
    rels = await db.friends.find({"$or": [{"requester_id": user["id"]}, {"addressee_id": user["id"]}]}, {"_id": 0}).to_list(500)
    friends, incoming, outgoing = [], [], []
    accepted_ids = []
    for r in rels:
        other = r["addressee_id"] if r["requester_id"] == user["id"] else r["requester_id"]
        if r["status"] == "accepted":
            accepted_ids.append(other)
        elif r["status"] == "pending":
            if r["addressee_id"] == user["id"]:
                incoming.append({"user_id": r["requester_id"], "persona_name": r.get("requester_name")})
            else:
                outgoing.append({"user_id": r["addressee_id"], "persona_name": r.get("addressee_name")})
    if accepted_ids:
        docs = {u["id"]: u for u in await db.users.find({"id": {"$in": accepted_ids}}, {"_id": 0}).to_list(len(accepted_ids))}
        for oid in accepted_ids:
            card = await _friend_card_from_user(docs.get(oid))
            if card:
                friends.append(card)
    friends.sort(key=lambda c: (not c["online"], c["persona_name"] or ""))
    tp_incoming, tp_outgoing, tp_live = await _teleport_lists(user["id"])
    return {"friends": friends, "incoming": incoming, "outgoing": outgoing,
            "tp_incoming": tp_incoming, "tp_outgoing": tp_outgoing, "tp_live": tp_live,
            # seconds left on THIS player's own teleport cooldown, 0 when ready:
            # a 30-minute wait that is only discoverable by clicking and being
            # refused is not a feature the dock can be honest about.
            "tp_cooldown_left": _teleport_cooldown_left(user)}


async def _teleport_lists(uid):
    """(tp_incoming, tp_outgoing, tp_live) for the friends poll, after lazy
    cleanup of expired pending rows, orphaned countdowns (backend restarted
    mid-hold) and aged-out resolved rows. tp_live carries the countdown/outcome
    rows for BOTH sides so each player's dock can render the hold pop-up and
    the final toast. Never raises."""
    now = time.time()
    try:
        await db.teleport_requests.update_many(
            {"status": "countdown", "countdown_ends_at": {"$lt": now - TELEPORT_COUNTDOWN_ORPHAN_SECS}},
            {"$set": {"status": "cancelled",
                      "cancel_reason": "El servidor web se reinició durante la cuenta regresiva",
                      "resolved_at": now}})
        await db.teleport_requests.delete_many({"$or": [
            {"status": "pending", "expires_at": {"$lt": now}},
            {"status": {"$in": ["accepted", "declined", "cancelled", "completed"]},
             "resolved_at": {"$lt": now - TELEPORT_RESOLVED_KEEP_SECS}},
        ]})
        rows = await db.teleport_requests.find(
            {"$or": [{"requester_id": uid}, {"target_id": uid}]}, {"_id": 0}).to_list(100)
    except Exception:
        return [], [], []
    tp_in, tp_out, tp_live = [], [], []
    for t in rows:
        left = max(0, int(t.get("expires_at", 0) - now))
        status = t.get("status")
        if t.get("target_id") == uid and status == "pending":
            tp_in.append({"id": t["id"], "from_id": t["requester_id"],
                          "from_name": t.get("requester_name"), "seconds_left": left})
        elif t.get("requester_id") == uid:
            tp_out.append({"id": t["id"], "to_id": t["target_id"], "to_name": t.get("target_name"),
                           "status": status, "seconds_left": left})
        if status in ("countdown", "completed", "cancelled") and uid in (t.get("requester_id"), t.get("target_id")):
            role = "requester" if t.get("requester_id") == uid else "target"
            tp_live.append({
                "id": t["id"], "role": role, "status": status,
                "other_name": t.get("target_name") if role == "requester" else t.get("requester_name"),
                "countdown_seconds_left": (max(0, int(round(float(t.get("countdown_ends_at") or 0) - now)))
                                           if status == "countdown" else 0),
                "reason": t.get("cancel_reason"),
            })
    return tp_in, tp_out, tp_live


def _possessed_row_or_none(u):
    """Live row for this user's possessed dino, else None.

    read_player_live(), not read_player(): the heavy players.json row is
    rebuilt in shards and is routinely 10-40 s old, so the species it names and
    the position it carries can both be wrong by the time a teleport aims at
    them. The ~1 s positions snapshot overlays both; when it is unavailable
    this degrades to exactly the old players.json-only behaviour."""
    sid = str(u.get("steam_id") or "").strip()
    if not sid:
        return None
    row = game_ipc.read_player_live(sid, force_fresh=True)
    if not isinstance(row, dict) or not str(row.get("actor_name") or "").strip():
        return None
    return row


def _species_display(row):
    return str(row.get("dino") or "").replace("BP_", "").replace("_C", "").strip() or "Dinosaurio"


def _teleport_same_species_required() -> bool:
    raw = (os.environ.get("LIN_TELEPORT_SAME_SPECIES", "1") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _teleport_species_gate(my_row, other_row, other_name):
    """Same-species rule (owner ruling 2026-07-16, mirrors the game's own
    teleport restriction): both dinos must be the SAME species. Unknown/empty
    species fails closed. Raises the named Spanish reason when they differ."""
    if not _teleport_same_species_required():
        return
    a = str(my_row.get("dino") or "").strip()
    b = str(other_row.get("dino") or "").strip()
    if a and b and a == b:
        return
    raise HTTPException(status_code=400, detail=(
        f"El teletransporte requiere la misma especie: tú llevas {_species_display(my_row)} y "
        f"{other_name or 'tu amigo'} lleva {_species_display(other_row)}"))


@api_router.post("/friends/teleport-request")
async def friends_teleport_request(data: FriendUserInput, user=Depends(get_current_user)):
    """Ask a friend to let you teleport to their position. The friend must
    accept before anything moves; the actual teleport happens on accept."""
    rel = await _relationship(user["id"], data.user_id)
    if not rel or rel["status"] != "accepted":
        raise HTTPException(status_code=400, detail="Solo puedes teletransportarte con un amigo aceptado")
    wait = _teleport_cooldown_left(user)
    if wait > 0:
        raise HTTPException(status_code=429, detail=(
            f"Tu próximo teletransporte estará disponible en {_teleport_wait_phrase(wait)}"))
    my_row = _possessed_row_or_none(user)
    if not my_row:
        raise HTTPException(status_code=400, detail="Necesitas estar dentro del servidor con un dino para solicitar un teletransporte")
    friend = await db.users.find_one({"id": data.user_id}, {"_id": 0})
    if not friend:
        raise HTTPException(status_code=404, detail="Jugador no encontrado")
    fr_row = _possessed_row_or_none(friend)
    if not fr_row:
        raise HTTPException(status_code=400, detail="Tu amigo no está dentro del servidor con un dino en este momento")
    _teleport_species_gate(my_row, fr_row, friend.get("persona_name"))
    _teleport_stamina_gate(my_row)
    now = time.time()
    dup = await db.teleport_requests.find_one({
        "$or": [{"requester_id": user["id"], "target_id": data.user_id},
                {"requester_id": data.user_id, "target_id": user["id"]}],
        "$and": [{"$or": [{"status": "pending", "expires_at": {"$gte": now}},
                          {"status": "countdown"}]}]}, {"_id": 0})
    if dup:
        raise HTTPException(status_code=400, detail="Ya hay una solicitud de teletransporte pendiente con este amigo")
    req = {"id": new_id(), "requester_id": user["id"], "requester_name": user.get("persona_name"),
           "target_id": data.user_id, "target_name": friend.get("persona_name"),
           "status": "pending", "created_at": now_iso(), "expires_at": now + TELEPORT_REQUEST_TTL_SECS}
    await db.teleport_requests.insert_one(dict(req))
    logger.info(f"[friends] teleport request {req['id']}: {user.get('persona_name')} -> {friend.get('persona_name')}")
    return {"success": True, "request_id": req["id"], "expires_in": TELEPORT_REQUEST_TTL_SECS}


@api_router.post("/friends/teleport-respond")
async def friends_teleport_respond(data: TeleportRespondInput, user=Depends(get_current_user)):
    """Target accepts/declines a teleport request; the requester may cancel
    their own. Accepting teleports the REQUESTER to the target's position via
    the game mod (fail-closed when the mod is offline)."""
    req = await db.teleport_requests.find_one({"id": data.request_id}, {"_id": 0})
    if not req or req.get("status") not in ("pending", "countdown"):
        raise HTTPException(status_code=404, detail="La solicitud de teletransporte ya no existe")
    now = time.time()
    if req.get("status") == "pending" and req.get("expires_at", 0) < now:
        await db.teleport_requests.update_one({"id": req["id"], "status": "pending"},
                                              {"$set": {"status": "cancelled", "resolved_at": now}})
        raise HTTPException(status_code=400, detail="La solicitud de teletransporte expiró")

    async def _claim(new_status, from_statuses=("pending",), reason=None):
        # CAS on status so accept/decline/cancel race to exactly one winner
        upd = {"status": new_status, "resolved_at": now}
        if reason:
            upd["cancel_reason"] = reason
        res = await db.teleport_requests.update_one(
            {"id": req["id"], "status": {"$in": list(from_statuses)}},
            {"$set": upd})
        return bool(getattr(res, "modified_count", 0))

    if user["id"] == req["requester_id"]:
        if data.accept:
            raise HTTPException(status_code=400, detail="Solo tu amigo puede aceptar la solicitud")
        # the requester may abort a pending request AND an in-flight countdown
        if not await _claim("cancelled", ("pending", "countdown"),
                            reason=f"{req.get('requester_name') or 'Tu amigo'} canceló el teletransporte"):
            raise HTTPException(status_code=404, detail="La solicitud de teletransporte ya no existe")
        return {"success": True, "status": "cancelled"}
    if user["id"] != req["target_id"]:
        raise HTTPException(status_code=403, detail="Esta solicitud de teletransporte no es para ti")
    if not data.accept:
        if req.get("status") == "countdown":
            if not await _claim("cancelled", ("countdown",),
                                reason=f"{req.get('target_name') or 'Tu amigo'} canceló el teletransporte"):
                raise HTTPException(status_code=404, detail="La solicitud de teletransporte ya no existe")
            return {"success": True, "status": "cancelled"}
        if not await _claim("declined"):
            raise HTTPException(status_code=404, detail="La solicitud de teletransporte ya no existe")
        return {"success": True, "status": "declined"}
    if req.get("status") == "countdown":
        raise HTTPException(status_code=400, detail="La cuenta regresiva ya está en marcha — no se muevan")
    requester = await db.users.find_one({"id": req["requester_id"]}, {"_id": 0})
    if not requester:
        raise HTTPException(status_code=404, detail="El jugador que pidió el teletransporte ya no existe")
    req_row = _possessed_row_or_none(requester)
    if not req_row:
        raise HTTPException(status_code=400, detail=f"{req.get('requester_name') or 'Tu amigo'} ya no está dentro del servidor con un dino")
    my_row = _possessed_row_or_none(user)
    if not my_row:
        raise HTTPException(status_code=400, detail="Necesitas estar dentro del servidor con un dino para recibir a tu amigo")
    _teleport_species_gate(my_row, req_row, req.get("requester_name"))
    # The one who teleports is the requester — re-check their stamina LIVE at accept
    _teleport_stamina_gate(req_row, who=req.get("requester_name") or "Tu amigo")
    # …and their cooldown, for the same reason. A player may hold one pending
    # request per friend, so a burst fired off while the window was still clear
    # would otherwise be accepted one after another and spend it several times.
    # This is the fast, explanatory refusal; the countdown runner claims the
    # window atomically just before dispatch and is what actually enforces it.
    cd_left = _teleport_cooldown_left(requester)
    if cd_left > 0:
        raise HTTPException(status_code=429, detail=(
            f"{req.get('requester_name') or 'Tu amigo'} ya usó su teletransporte — "
            f"le quedan {_teleport_wait_phrase(cd_left)} de espera"))

    def _pos(row):
        out = {}
        for k in ("x", "y", "z"):
            try:
                out[k] = float(row.get(k) or 0)
            except (TypeError, ValueError):
                out[k] = 0.0
        return out

    cd_secs = _teleport_countdown_secs()
    res = await db.teleport_requests.update_one(
        {"id": req["id"], "status": "pending"},
        {"$set": {
            "status": "countdown",
            "countdown_started_at": now,
            "countdown_ends_at": now + cd_secs,
            "requester_sid": str(requester.get("steam_id") or "").strip(),
            "target_sid": str(user.get("steam_id") or "").strip(),
            "countdown_base": {"requester": _pos(req_row), "target": _pos(my_row)},
        }})
    if not getattr(res, "modified_count", 0):
        raise HTTPException(status_code=404, detail="La solicitud de teletransporte ya no existe")
    asyncio.create_task(_teleport_countdown_runner(req["id"]))
    logger.info(f"[friends] teleport countdown started {req['id']}: {req.get('requester_name')} -> "
                f"{user.get('persona_name')} ({cd_secs}s hold)")
    return {"success": True, "status": "countdown", "countdown_seconds": cd_secs,
            "message": f"Cuenta regresiva iniciada — no se muevan durante {cd_secs} segundos"}


async def _teleport_countdown_runner(req_id: str):
    """The 10-second hold after the target accepts: samples both players about
    once a second; ANY net movement past the tolerance (or leaving the server,
    or an unreadable position signal) cancels with a named Spanish reason. If
    the hold survives, the real mod teleport fires at the target's CURRENT
    position. Fully contained — this background task never raises out, and
    every transition is a CAS on status=="countdown" so a user cancel always
    wins cleanly."""
    try:
        req = await db.teleport_requests.find_one({"id": req_id}, {"_id": 0})
        if not req or req.get("status") != "countdown":
            return
        tol = _teleport_move_tolerance()
        base = req.get("countdown_base") or {}
        ends_at = float(req.get("countdown_ends_at") or 0)
        pairs = (("requester", str(req.get("requester_sid") or ""), req.get("requester_name") or "Tu amigo"),
                 ("target", str(req.get("target_sid") or ""), req.get("target_name") or "Tu amigo"))
        stale = {"requester": 0, "target": 0}
        rows = {}

        async def _cancel(reason: str) -> None:
            res = await db.teleport_requests.update_one(
                {"id": req_id, "status": "countdown"},
                {"$set": {"status": "cancelled", "cancel_reason": reason, "resolved_at": time.time()}})
            if getattr(res, "modified_count", 0):
                logger.info(f"[friends] teleport countdown cancelled {req_id}: {reason}")

        while True:
            cur = await db.teleport_requests.find_one({"id": req_id}, {"_id": 0, "status": 1})
            if not cur or cur.get("status") != "countdown":
                return  # resolved elsewhere (user cancel / lazy cleanup)
            for role, sid, name in pairs:
                row = await asyncio.to_thread(game_ipc.read_player_live, sid, force_fresh=True)
                if not (isinstance(row, dict) and str(row.get("actor_name") or "").strip()):
                    stale[role] += 1
                    if stale[role] >= 4:
                        await _cancel(f"Se perdió la señal de {name} — teletransporte cancelado")
                        return
                    continue
                stale[role] = 0
                rows[role] = row
                b = base.get(role) or {}
                try:
                    dx = float(row.get("x") or 0) - float(b.get("x") or 0)
                    dy = float(row.get("y") or 0) - float(b.get("y") or 0)
                    dz = float(row.get("z") or 0) - float(b.get("z") or 0)
                except (TypeError, ValueError):
                    continue
                if (dx * dx + dy * dy + dz * dz) ** 0.5 > tol:
                    await _cancel(f"{name} se movió durante la cuenta regresiva — teletransporte cancelado")
                    return
            now = time.time()
            if now >= ends_at:
                break
            await asyncio.sleep(min(1.0, max(0.2, ends_at - now)))

        tgt = rows.get("target")
        if not isinstance(tgt, dict):
            await _cancel(f"Se perdió la señal de {req.get('target_name') or 'tu amigo'} — teletransporte cancelado")
            return
        try:
            dest_x = float(tgt.get("x") or 0) + 120.0   # small side offset so the two dinos don't overlap
            dest_y = float(tgt.get("y") or 0)
            dest_z = float(tgt.get("z") or 0) + 40.0    # small lift so the arrival never clips into the ground
        except (TypeError, ValueError):
            await _cancel("No se pudo leer la posición del destino — teletransporte cancelado")
            return
        # CLAIM THE COOLDOWN IN THE SAME WRITE THAT PAYS IT, and do it BEFORE the
        # mod command goes out. Two accepted requests can be holding countdowns
        # at the same time (one per friend); the conditional update means exactly
        # one of them can win the window, and the loser is cancelled by name
        # instead of quietly teleporting for free. Claimed early so the claim can
        # be released if the dispatch itself never lands.
        cooldown = _teleport_cooldown_secs()
        claim_at = time.time()
        prev_stamp = None
        if cooldown > 0:
            prev = await db.users.find_one_and_update(
                {"id": req["requester_id"],
                 "$or": [{"teleport_last_at": {"$exists": False}},
                         {"teleport_last_at": None},
                         {"teleport_last_at": {"$lte": claim_at - cooldown}}]},
                {"$set": {"teleport_last_at": claim_at}},
                projection={"_id": 0, "teleport_last_at": 1})
            if prev is None:
                await _cancel(f"{req.get('requester_name') or 'Tu amigo'} ya usó su teletransporte — "
                              f"hay que esperar el tiempo de espera")
                return
            prev_stamp = prev.get("teleport_last_at")
        else:
            await db.users.update_one({"id": req["requester_id"]},
                                      {"$set": {"teleport_last_at": claim_at}})
        try:
            ok = await asyncio.to_thread(game_ipc.write_game_command, {
                "type": "teleport", "steamid": str(req.get("requester_sid") or "").strip(),
                "x": dest_x, "y": dest_y, "z": dest_z,
            })
        except Exception:
            await _release_teleport_claim(req["requester_id"], claim_at, prev_stamp)
            raise
        if not ok:
            await _release_teleport_claim(req["requester_id"], claim_at, prev_stamp)
            await _cancel("El servidor de juego no está disponible en este momento — teletransporte cancelado")
            return
        res = await db.teleport_requests.update_one(
            {"id": req_id, "status": "countdown"},
            {"$set": {"status": "completed", "resolved_at": time.time()}})
        if getattr(res, "modified_count", 0):
            logger.info(f"[friends] teleport completed {req_id}: {req.get('requester_name')} -> "
                        f"{req.get('target_name')} at ({dest_x:.0f},{dest_y:.0f},{dest_z:.0f}) "
                        f"cooldown={cooldown}s aim={tgt.get('pos_source') or 'snapshot'} "
                        f"aim_age={tgt.get('pos_age_s', '?')}s "
                        f"species={tgt.get('dino') or '?'}")
    except Exception:
        logger.exception("[friends] teleport countdown runner failed")
        try:
            await db.teleport_requests.update_one(
                {"id": req_id, "status": "countdown"},
                {"$set": {"status": "cancelled", "resolved_at": time.time(),
                          "cancel_reason": "Error interno — teletransporte cancelado"}})
        except Exception:
            pass


@api_router.post("/friends/teleport")
async def friends_teleport(data: FriendUserInput, user=Depends(get_current_user)):
    """Retired simulated endpoint, kept for browsers still on the previous
    bundle: point them at the new request/accept flow."""
    raise HTTPException(status_code=400, detail="El teletransporte ahora se envía como solicitud y tu amigo debe aceptarla. Actualiza la página para usar la nueva opción.")



def _real_active_dino(user, ad):
    """Overlay REAL vitals + position (from the mod's players.json) onto the
    stored active-dino identity, keeping _live_active_dino's response shape so
    the existing frontend keeps working. Returns None when there is no fresh
    real row (caller falls back to the simulation)."""
    sid = str(user.get("steam_id") or "").strip()
    if not sid:
        return None
    row = game_ipc.read_player_display(sid)
    if not isinstance(row, dict):
        return None
    # A positions-only row (fresh spawn, catalogue not built yet) has no maxima,
    # so every gauge below would silently keep the simulation's numbers while
    # the card claims "real" -- fall back to the marked simulation instead.
    # /me/state still serves the live-only row, so the Dino en Vivo page sees
    # the spawn within seconds either way.
    if row.get("heavy_missing"):
        return None
    base = _live_active_dino(ad)  # identity + cosmetics + response shape

    def _pct(cur, mx):
        try:
            m = float(row.get(mx) or 0)
            if m > 0:
                return max(0.0, min(100.0, float(row.get(cur) or 0) / m * 100.0))
        except (TypeError, ValueError):
            pass
        return None

    live = dict(base.get("live") or {})
    hp, st = _pct("health", "max_health"), _pct("stamina", "max_stamina")
    hu, th = _pct("hunger", "max_hunger"), _pct("thirst", "max_thirst")
    if hp is not None:
        live["health"] = round(hp)
    if st is not None:
        live["stamina"] = round(st)
    if hu is not None:
        live["hunger"] = round(hu)
    if th is not None:
        live["thirst"] = round(th)
    if row.get("growth") is not None:
        try:
            live["growth"] = round(float(row.get("growth")) * 100, 1)
        except (TypeError, ValueError):
            pass
    live["max_health"] = 100
    live["starving"] = bool((hu is not None and hu <= 0) or (th is not None and th <= 0))
    base["live"] = live
    pos = teleport_presets.to_percent(row.get("x"), row.get("y"))
    if pos is not None:
        base["position"] = {"x": round(pos[0], 1), "y": round(pos[1], 1)}
    return base


@api_router.get("/active-dino")
async def get_active_dino(user=Depends(get_current_user)):
    in_game = await _is_user_in_game(user)
    ad = user.get("active_dino")
    if not ad:
        return {"active": None, "in_game": in_game, "source": None}
    real = _real_active_dino(user, ad)
    if real is not None:
        return {"active": real, "in_game": in_game, "source": "real"}
    # No fresh real row — retain the simulation, explicitly marked.
    return {"active": _live_active_dino(ad), "in_game": in_game, "source": "sim"}


def _inventory_dino_mutation_keys(item: dict) -> tuple:
    """Legacy inventory dino -> (own, parent, elder_a, elder_b) mutation KEYS.

    Prefers the grouped editor value; falls back to the flat list a purchase
    used to store. Unknown keys are dropped rather than failing the move.
    """
    groups = item.get("mutation_groups") or {}

    def pick(name):
        return [k for k in (groups.get(name) or []) if k and k in MUTATIONS_BY_KEY]

    own = pick("child")
    if not own:
        own = [k for k in (item.get("mutations") or []) if k and k in MUTATIONS_BY_KEY]
    return own, pick("parent"), pick("elder_a"), pick("elder_b")


@api_router.post("/active-dino/deploy")
async def deploy_dino(data: EquipSkinInput, user=Depends(get_current_user)):
    """Move an inventory dinosaur into the real vault (La Boveda).

    This endpoint used to write Mongo ONLY -- it set user.active_dino, returned
    200 and the UI toasted "canjeado en tu partida", but it never sent the mod a
    command, so the dino never existed in-game (reported 2026-07-15). Dinosaurs now
    live in the vault, which is the only lane that actually spawns one, so this
    hands the dino over to that lane and points the player at La Boveda instead
    of pretending. New purchases go straight to the vault and never come here.
    """
    item = await db.inventory.find_one(
        {"id": data.inv_id, "user_id": user["id"], "category": "Dinosaurs"}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Dinosaurio no encontrado en tu inventario")
    sid = _steam_id_or_400(user)
    slug = item.get("dino_slug")
    if not slug and item.get("item_id"):
        st = await db.store_items.find_one({"id": item["item_id"]}, {"_id": 0, "dino_slug": 1})
        if st:
            slug = st.get("dino_slug")
    if not slug:
        nm = item["name"].replace(" Slot", "").strip()
        dino = await db.dinosaurs.find_one(
            {"name": {"$regex": f"^{re.escape(nm)}", "$options": "i"}}, {"_id": 0, "slug": 1})
        slug = (dino or {}).get("slug")
    dino_class = _EVRIMA_CLASS_BY_SLUG.get(slug or "")
    if not dino_class:
        raise HTTPException(status_code=400, detail="No se pudo resolver la especie de este dinosaurio")

    cap = _user_park_cap(user)
    if cap > 0 and await asyncio.to_thread(vault.count_parked, sid) >= cap:
        raise HTTPException(
            status_code=400,
            detail=f"Tu Boveda esta llena ({cap}). Recupera o libera un dino antes de mover este.")

    own, parent, elder_a, elder_b = _inventory_dino_mutation_keys(item)
    # Drop anything this species cannot carry instead of blocking the move: the
    # old lane never diet-checked, so legacy rows can hold illegal picks.
    allowed = mutation_catalog.allowed_names_for_class(dino_class)

    def canon(keys, limit):
        out = []
        for k in keys:
            c = mutation_catalog.canonical_mutation_name(MUTATIONS_BY_KEY[k]["name"])
            if c and c in allowed and c not in out:
                out.append(c)
        return out[:limit]

    def pad(xs, n):
        return mutation_catalog.join_segments(xs + ["None"] * (n - len(xs)))

    # INTERLEAVED, not blocked: elder_mutations is 1A,1B,2A,2B,3A,3B,4A,4B and
    # the mod is the only decoder that reaches the game. Concatenating the four
    # A picks then the four B picks (what this line did until 2026-07-26) put a
    # "Set A" pick into ElderMutationSlot1A/1B/2A/2B instead of 1A/2A/3A/4A.
    # mutation_catalog owns the order for both writers now.
    elder = mutation_catalog.elder_segments_from_sets(canon(elder_a, 4), canon(elder_b, 4))
    is_prime = bool(item.get("prime")) or item.get("tier") == "prime"
    parent_str = pad(canon(parent, _PARENT_MUT_SEGMENTS), _PARENT_MUT_SEGMENTS)
    elder_str = mutation_catalog.join_segments(elder)
    # No skin_code: the inventory "skin" field is a website cosmetic id, not a
    # game skin code. The player applies skins through the live skin lane.
    pd = {
        "dino": dino_class,
        "growth": max(0, min(100, int(item.get("saved_growth") or 75))) / 100.0,
        "is_prime": is_prime,
        "is_elder": is_prime,
        "mutations": pad(canon(own, _OWN_MUT_SEGMENTS), _OWN_MUT_SEGMENTS),
        "parent_mutations": parent_str,
        "elder_mutations": elder_str,
        # NO elder_stacks KEY, ON PURPOSE -- same reason as purchase_dino above.
        # This lane briefly stored a count derived from the inventory item's own
        # entomb_count so the vault editor would open the Anciano picks the
        # legacy inventory editor had allowed. But this column is not an editor
        # field: vault._run_redeem hands it to the mod as ElderReplicationStacks,
        # so the derived value granted the dino 1-3 in-game elder replication
        # stacks it never had (and one of them, 3, is a generation the site's own
        # entomb lane refuses to reach -- MAX_ENTOMB_GEN is 2). save_parked keeps
        # storing 0, exactly as this lane always did.
    }
    # CLAIM the inventory copy before writing the vault row. Reading it and
    # deleting it afterwards is a TOCTOU: two concurrent calls both read the
    # same item, both insert a parked_dinos row, and one dino becomes two. Both
    # branches below are single atomic document ops, so exactly one caller can
    # claim a given copy; the loser gets 404.
    claimed = await db.inventory.find_one_and_update(
        {"id": data.inv_id, "user_id": user["id"], "category": "Dinosaurs",
         "quantity": {"$gt": 1}},
        {"$inc": {"quantity": -1}})
    decremented = claimed is not None
    if claimed is None:
        claimed = await db.inventory.find_one_and_delete(
            {"id": data.inv_id, "user_id": user["id"], "category": "Dinosaurs"})
    if claimed is None:
        raise HTTPException(status_code=404, detail="Dinosaurio no encontrado en tu inventario")

    # Same statement as the store lane: this dict ASSERTS is_prime off the
    # inventory item, so it owes the mission bits that make the assertion true
    # in game. A non-prime item is untouched.
    pd = vault.mint_prime_state(pd)
    discord_id = await asyncio.to_thread(vault.resolve_discord_id, sid)
    try:
        row_id = await asyncio.to_thread(vault.save_parked, sid, discord_id, pd, cap)
    except Exception:
        logging.getLogger("laislanublar.vault").exception(
            "[vault] inventory->vault move crashed sid=%s inv=%s", sid, data.inv_id)
        row_id = None
    if row_id is None:
        # Vault write lost -> hand the claimed copy back; never eat the dino.
        if decremented:
            await db.inventory.update_one({"id": data.inv_id}, {"$inc": {"quantity": 1}})
        else:
            restore = {k: v for k, v in claimed.items() if k != "_id"}
            await db.inventory.insert_one(restore)
        raise HTTPException(status_code=400,
                            detail="No se pudo mover el dino a tu Boveda. Intentalo de nuevo.")

    return {"moved_to_vault": True, "vault_dino_id": row_id,
            "message": "Lo movimos a tu Boveda. Entra al juego como esa especie y pulsa Recuperar."}


@api_router.post("/active-dino/park")
async def park_dino(user=Depends(get_current_user)):
    """Park (safe-log) the live dino: it dies in-game but is saved to inventory with its stats."""
    ad = user.get("active_dino")
    if not ad:
        raise HTTPException(status_code=400, detail="No tienes un dino vivo para guardar")
    live = _live_active_dino(ad)
    dino = await db.dinosaurs.find_one({"slug": ad["slug"]}, {"_id": 0})
    await db.inventory.insert_one({
        "id": new_id(), "user_id": user["id"], "item_id": f"dino_{ad['slug']}",
        "name": dino["name"] if dino else ad["name"], "category": "Dinosaurs",
        "rarity": ad.get("rarity", "Common"), "image": ad.get("image"),
        "dino_slug": ad["slug"], "mutations": ad.get("mutations", []),
        "saved_growth": live["live"]["growth"], "parked": True, "quantity": 1,
        "recovery_id": ad.get("recovery_id"),
        "prime": bool(ad.get("prime")), "tier": ad.get("tier"),
        "skin": ad.get("active_skin"), "skin_image": ad.get("skin_image"),
        "order": 9999, "acquired_at": now_iso(),
    })
    await db.users.update_one({"id": user["id"]}, {"$set": {"active_dino": None}})
    await _upsert_dino_record(user, ad, live["live"]["growth"], "parked")
    return {"success": True, "saved_growth": live["live"]["growth"]}


@api_router.post("/active-dino/slay")
async def slay_dino(user=Depends(get_current_user)):
    """Slay the live dino — it dies and is permanently lost."""
    ad = user.get("active_dino")
    if not ad:
        raise HTTPException(status_code=400, detail="No tienes un dino vivo para sacrificar")
    live = _live_active_dino(ad)
    await db.users.update_one({"id": user["id"]}, {"$set": {"active_dino": None}})
    await _upsert_dino_record(user, ad, live["live"]["growth"], "slain")
    return {"success": True}


@api_router.post("/active-dino/drop-body")
async def drop_body(user=Depends(get_current_user)):
    """Drop a body to feed — only while hunger < 30% and growth < 60%. Refills hunger."""
    ad = user.get("active_dino")
    if not ad:
        raise HTTPException(status_code=400, detail="No tienes un dino vivo")
    live = _live_active_dino(ad)
    if live["live"]["hunger"] >= 30:
        raise HTTPException(status_code=400, detail="Solo puedes soltar un cuerpo cuando hunger is below 30%")
    if live["live"]["growth"] >= 60:
        raise HTTPException(status_code=400, detail="Ya no puedes soltar cuerpos despues de 60% de crecimiento")
    ad["fed_at"] = now_iso()
    ad["bodies_dropped"] = ad.get("bodies_dropped", 0) + 1
    await db.users.update_one({"id": user["id"]}, {"$set": {"active_dino": ad}})
    return {"active": _live_active_dino(ad)}


@api_router.post("/active-dino/toggle-growth")
async def toggle_growth(user=Depends(get_current_user)):
    """Pause/resume growth (safe-log). While paused, growth & vitals are frozen."""
    ad = user.get("active_dino")
    if not ad:
        raise HTTPException(status_code=400, detail="No tienes un dino vivo")
    live = _live_active_dino(ad)
    lv, pos = live["live"], live["position"]
    if ad.get("growth_paused"):
        # resume — continue growing from the frozen value
        ad["growth_paused"] = False
        ad["base_growth"] = lv["growth"]
        ad["set_at"] = now_iso()
        ad["fed_at"] = now_iso()
        for k in ("paused_growth", "paused_hunger", "paused_thirst", "paused_x", "paused_y"):
            ad.pop(k, None)
        paused = False
    else:
        ad["growth_paused"] = True
        ad["paused_growth"] = lv["growth"]
        ad["paused_hunger"] = lv["hunger"]
        ad["paused_thirst"] = lv["thirst"]
        ad["paused_x"] = pos["x"]
        ad["paused_y"] = pos["y"]
        paused = True
    await db.users.update_one({"id": user["id"]}, {"$set": {"active_dino": ad}})
    return {"active": _live_active_dino(ad), "paused": paused}


@api_router.post("/active-dino/set-prime")
async def set_prime_dino(user=Depends(get_current_user)):
    """Promote the live dino to a Prime Elder: full adult growth + boosted stats + bonus mutation slot."""
    ad = user.get("active_dino")
    if not ad:
        raise HTTPException(status_code=400, detail="No tienes un dino vivo")
    if ad.get("prime"):
        raise HTTPException(status_code=400, detail="Este dinosaurio ya es Prime")
    ad["prime"] = True
    ad["base_growth"] = PRIME_GROWTH
    ad["set_at"] = now_iso()
    ad["fed_at"] = now_iso()
    ad["growth_paused"] = False
    for k in ("paused_growth", "paused_hunger", "paused_thirst", "paused_x", "paused_y"):
        ad.pop(k, None)
    ad["base_stats"] = _apply_prime_stats(ad.get("base_stats", {}))
    ad["prime_at"] = now_iso()
    await db.users.update_one({"id": user["id"]}, {"$set": {"active_dino": ad}})
    live = _live_active_dino(ad)
    await _upsert_dino_record(user, ad, live["live"]["growth"], "active")
    return {"active": live}


@api_router.post("/active-dino/skin")
async def equip_active_skin(data: EquipSkinInput, user=Depends(get_current_user)):
    # A coded crate skin is a REAL in-game action: it paints the player's live
    # dinosaur through the mod. So it gates on the LIVE dino from the mod's
    # players.json — the same single source /api/apply, the glitch reward lane and
    # vault.do_growth_pause already use. It must NEVER gate on the web-sim
    # `active_dino` record: that document only exists for a dino DEPLOYED from La
    # Bóveda, so every player who spawned normally in-game (the usual case) was
    # refused with "Despliega un dinosaurio…" while standing in the game holding
    # the skin — the 2026-07-24 owner report. Display-only derived skins keep the
    # record gate: they have nothing to paint and only decorate the website card.
    ad = user.get("active_dino")
    item = await db.inventory.find_one(
        {"id": data.inv_id, "user_id": user["id"], "category": "Skins"}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Skin no encontrada en tu inventario")
    # `or ""` not `.get(..., "")`: a row storing item_id as an explicit null used
    # to reach .replace() on None and 500 the request.
    skin_key = item.get("skin_key") or ((item.get("item_id") or "").replace("skin_", "") or None)
    color = item.get("color")
    evrima = None
    srgb = None
    if skin_key and skin_key in seed_data.SKINS:
        color = seed_data.SKINS[skin_key].get("color", color)
        evrima = seed_data.SKINS[skin_key].get("evrima")
        srgb = seed_data.SKINS[skin_key].get("srgb")
    paints_ingame = bool(srgb)
    applied_ingame = False
    sid = ""
    dino = None
    if paints_ingame:
        sid = _steam_id_or_400(user)
        dino = await asyncio.to_thread(game_ipc.find_active_dino, sid)
        if not dino:
            raise HTTPException(status_code=409, detail="Entra al juego con tu dino para aplicar esta skin.")
        await asyncio.to_thread(_ghost_gate_check, sid, dino, "equip")
    elif not ad:
        # Display-only skin (the two VIP store skins) and no web card to put it
        # on. Nothing in the game changes either way, so refuse WITHOUT spending
        # a use and say why — the old copy told the player to "deploy a dino",
        # which no lane has created since dinosaurs moved to the vault.
        raise HTTPException(
            status_code=400,
            detail="Esta skin es solo decorativa para la web y no se puede pintar en tu dino dentro del juego.")
    # Reserve ONE use atomically BEFORE the paint: two racing clicks can no longer
    # both spend the same use (the old read-then-$set lost a decrement, handing
    # back a free use) and the counter can never go negative. Rows written before
    # the use counter existed self-heal from `quantity`, exactly-once via $exists.
    if "uses" not in item:
        await db.inventory.update_one(
            {"id": item["id"], "user_id": user["id"], "uses": {"$exists": False}},
            {"$set": {"uses": max(1, int(item.get("quantity") or 1))}})
    after = await db.inventory.find_one_and_update(
        {"id": item["id"], "user_id": user["id"], "category": "Skins", "uses": {"$gte": 1}},
        {"$inc": {"uses": -1}}, return_document=ReturnDocument.AFTER)
    if not after:
        raise HTTPException(status_code=400, detail="Esta skin ya no tiene usos disponibles")
    remaining = int(after.get("uses", 0) or 0)
    if paints_ingame:
        try:
            applied_ingame = await asyncio.to_thread(_paint_universal_skin_sync, skin_key, sid, dino)
        except Exception:
            logger.exception("[skins] equip paint failed sid=%s skin=%s", sid, skin_key)
            applied_ingame = False
        if not applied_ingame:
            # A failed apply never burns a use — hand the reserved one straight back.
            await db.inventory.update_one(
                {"id": item["id"], "user_id": user["id"]}, {"$inc": {"uses": 1}})
            raise HTTPException(status_code=500, detail="No se pudo aplicar la skin. Intenta de nuevo.")
    # Out of uses — the skin leaves the inventory. Conditional on the counter so a
    # concurrent refund can never be swept away with it.
    if remaining <= 0:
        await db.inventory.delete_one(
            {"id": item["id"], "user_id": user["id"], "uses": {"$lte": 0}})
    # The website card is optional now: store the cosmetic on it only when the
    # player actually has a deployed-from-the-vault dino to decorate.
    if ad:
        ad["active_skin"] = {
            "inv_id": item["id"], "name": item["name"],
            "rarity": item.get("rarity", "Common"), "image": item.get("image"),
            "color": color, "skin_key": skin_key,
            "config": evrima, "evrima": evrima,
        }
        await db.users.update_one({"id": user["id"]}, {"$set": {"active_dino": ad}})
    logger.info("[skins] equip user=%s skin=%s paints_ingame=%s applied_ingame=%s actor=%s "
                "uses_left=%d web_card=%s", user.get("id"), skin_key, paints_ingame,
                applied_ingame, (dino or {}).get("actor_name"), remaining, bool(ad))
    return {"active": _live_active_dino(ad) if ad else None, "uses_left": remaining,
            "evrima": evrima, "paints_ingame": paints_ingame, "applied_ingame": applied_ingame}


@api_router.post("/active-dino/skin/remove")
async def unequip_active_skin(user=Depends(get_current_user)):
    ad = user.get("active_dino")
    if not ad:
        raise HTTPException(status_code=400, detail="No tienes dinosaurio activo")
    ad["active_skin"] = None
    await db.users.update_one({"id": user["id"]}, {"$set": {"active_dino": ad}})
    return {"active": _live_active_dino(ad)}


def _is_subscriber(u):
    if not u:
        return False
    # Owner ruling 2026-07-18: only the server owner bypasses the subscriber
    # gates — staff ranks don't count as a subscription.
    if _is_owner(u):
        return True
    if u.get("patreon_id") or u.get("patreon_patron_status") == "active_patron":
        return True
    if u.get("discord_vip_role_granted"):
        return True
    if u.get("discord_tier_role"):
        return True
    if u.get("discord_streamer_role"):
        return True
    return False


@api_router.post("/active-dino/custom-skin")
async def apply_custom_skin(data: CustomSkinInput, user=Depends(get_current_user)):
    """Subscriber perk: apply a self-created custom skin to the live dino (no inventory needed)."""
    if not _is_subscriber(user):
        raise HTTPException(status_code=403, detail="El Skin Lab es solo para suscriptores")
    ad = user.get("active_dino")
    if not ad:
        raise HTTPException(status_code=400, detail="Debes desplegar (deploy) un dinosaurio antes de aplicar una skin personalizada")
    color = (data.color or "").strip()
    if not re.fullmatch(r"#(?:[0-9a-fA-F]{6})", color):
        raise HTTPException(status_code=400, detail="Color invalido")
    name = (data.name or "").strip()[:40] or "Custom Skin"
    preview = _validate_data_image(data.image, "image")
    ad["active_skin"] = {
        "inv_id": None, "name": name, "rarity": "Custom",
        "image": None, "color": color, "skin_key": None, "custom": True,
        "config": data.config or None, "preview": preview,
    }
    # keep a top-level copy so it survives park -> inventory -> marketplace
    if preview:
        ad["skin_image"] = preview
    await db.users.update_one({"id": user["id"]}, {"$set": {"active_dino": ad}})
    return {"active": _live_active_dino(ad)}


# ---------- 3D Skin Studio (save/load custom skin configs) ----------
class Skin3DInput(BaseModel):
    name: str = Field("My Skin", max_length=60)
    dino_slug: str
    config: dict


def _skin3d_public(s: dict) -> dict:
    return {k: s.get(k) for k in ("id", "name", "dino_slug", "config", "created_at", "updated_at")}


@api_router.get("/skins3d")
async def list_skins3d(user=Depends(get_current_user)):
    items = await db.skins3d.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return [_skin3d_public(s) for s in items]


@api_router.post("/skins3d")
async def save_skin3d(data: Skin3DInput, user=Depends(get_current_user)):
    config = _validated_skin3d_config(data.config)
    doc = {
        "id": new_id(), "user_id": user["id"],
        "name": (data.name or "My Skin").strip()[:60] or "My Skin",
        "dino_slug": data.dino_slug, "config": config,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.skins3d.insert_one(doc)
    return _skin3d_public(doc)


@api_router.put("/skins3d/{skin_id}")
async def update_skin3d(skin_id: str, data: Skin3DInput, user=Depends(get_current_user)):
    config = _validated_skin3d_config(data.config)
    res = await db.skins3d.update_one(
        {"id": skin_id, "user_id": user["id"]},
        {"$set": {"name": (data.name or "My Skin").strip()[:60] or "My Skin",
                  "dino_slug": data.dino_slug, "config": config, "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Skin no encontrada")
    doc = await db.skins3d.find_one({"id": skin_id}, {"_id": 0})
    return _skin3d_public(doc)


@api_router.delete("/skins3d/{skin_id}")
async def delete_skin3d(skin_id: str, user=Depends(get_current_user)):
    res = await db.skins3d.delete_one({"id": skin_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Skin no encontrada")
    return {"ok": True}


# ================= DINOSAUR POPULATION (popcontrol truth) =================
# The population tab mirrors the SAME state the bot's popcontrol enforces:
#   caps   = species_caps table in the bot DB (missing row = 100, negative =
#            unlimited — identical to popcontrol.py/_over_cap_species),
#   locks  = species_lock_state.json manual locks,
#   counts = live per-species players from the mod's players.json.
# No simulated numbers: if popcontrol caps Tyrannosaurus at 1 the card reads
# N/1, and a player in-game as a Rex is counted within ~players.json freshness.

def _pop_slug_for_class(cls):
    """BP_Tyrannosaurus_C -> 'trex' (game_telemetry's canonical slug map)."""
    return game_telemetry.EVRIMA_SPECIES.get(game_telemetry._clean_species(cls or ""), "")


def _popcontrol_slug_map():
    """{slug: BP class} for every supported species with a known slug."""
    out = {}
    for cls in pop_control.SUPPORTED_SPECIES:
        slug = _pop_slug_for_class(cls)
        if slug:
            out[slug] = cls
        else:
            logger.warning("[population] no slug mapping for %s — hidden from the population tab", cls)
    return out


_POPCONTROL_SLUGS = _popcontrol_slug_map()


def _popcontrol_live_view():
    """{slug: {class, cap, count, locked}} — cap None = unlimited (negative cap).
    Never raises: an unavailable bot DB / lock file / players.json degrades to
    open defaults (cap 100, count 0, unlocked) with a warning, so the page
    stays up while the bot stack restarts."""
    try:
        caps = pop_control.read_caps()
    except Exception as e:
        logger.warning("[population] species_caps unavailable (%s) — default caps", e)
        caps = {}
    try:
        locked = set(pop_control.read_locked())
    except Exception as e:
        logger.warning("[population] lock state unavailable (%s)", e)
        locked = set()
    try:
        counts = pop_control._counts()
    except Exception as e:
        logger.warning("[population] players.json counts unavailable (%s)", e)
        counts = {}
    view = {}
    for slug, cls in _POPCONTROL_SLUGS.items():
        try:
            cap = int(caps.get(cls, 100))
        except (TypeError, ValueError):
            cap = 100
        view[slug] = {"class": cls, "cap": (None if cap < 0 else cap),
                      "count": int(counts.get(cls, 0)), "locked": cls in locked}
    return view

POP_COOLDOWN_SEC = 300  # per-user cooldown for the RESPAWN button (per server+species, Mongo pop_cd)
# Unlock knobs (2026-07-16): the unlock now writes the REAL popcontrol state the
# bot enforces, so the window/cooldown are env-tunable and mirrored in the bot's
# .env (LAISLANUBLAR_POP_UNLOCK_SECONDS / _COOLDOWN_SECONDS) — keep them aligned.
POP_UNLOCK_SEC = int(os.environ.get("LIN_POP_UNLOCK_SECONDS", "300") or "300")          # how long a GLOBAL unlock stays active
# Owner ruling 2026-07-30: the wait between unlocks is 5 minutes, not an hour
# (it used to be 3600 here and in both .envs). It is still env-tunable.
POP_UNLOCK_COOLDOWN_SEC = int(os.environ.get("LIN_POP_UNLOCK_COOLDOWN_SECONDS", "300") or "300")  # per-user wait between unlocks
POP_SUB_ONLY = {"trex", "allo", "trike"}  # subscriber-only apex respawns

# ---- POPULATION RESPAWN = REAL in-game species swap (2026-07-16) ----
# The Respawn button swaps the caller's LIVE dino to the chosen species via
# the mod's spawn+possess lane: commands.json {"type":"swap",...} (flat JSON) →
# swap_status.json terminal ack (swap_ok / swap_failed). Access comes from the
# holder's Discord Patreon tier role, fetched LIVE through _patreon_access;
# growth is FLAT 25% for everyone, and the perk applies ONLY to species at max
# capacity — the personal counterpart of Desbloquear (owner rulings 2026-07-16).
# No prime / elder / mutations — growth only. Species needing the Apex tier =
# seed_data.POP_APEX (the cards' APEX+ chip). Kill switches: LIN_SWAP_ENABLED=0
# (web) and <Saved>\swap_disable.flag (mod).
_SWAP_ENABLED = (os.environ.get("LIN_SWAP_ENABLED", "1").strip() or "1") != "0"
SWAP_COOLDOWN_SEC = int(os.environ.get("LIN_SWAP_COOLDOWN_SECS", "300") or "300")
SWAP_ACK_TIMEOUT_SEC = max(5, int(os.environ.get("LIN_SWAP_ACK_TIMEOUT_SECS", "30") or "30"))
# Owner ruling 2026-07-16 (~21:4xZ): every swap arrives at 25% growth, flat —
# the tier ladder default is gone; the env knob remains for a future change.
_SWAP_TIER_GROWTH_DEFAULT = "Apex:25,Elder:25,Adult:25,Sub Adult:25,Juvie:25,Supporter:25"
_SWAP_FALLBACK_GROWTH_PCT = 25  # every allowed patron, admins included
_SWAP_INFLIGHT: dict[str, float] = {}  # sid -> monotonic start (single uvicorn worker)


_SWAP_TIER_GROWTH_CACHE: dict | None = None


def _swap_tier_growth_map() -> dict:
    """{lowercase tier label: growth pct 20..100} from LIN_SWAP_TIER_GROWTH
    ('Label:pct,Label:pct'). Safe-parse: malformed entries fall back to the
    default map so a bad env can never disable the perk. Memoized — env only
    changes across a backend bounce, and /population polls hit this per page."""
    global _SWAP_TIER_GROWTH_CACHE
    if _SWAP_TIER_GROWTH_CACHE is not None:
        return _SWAP_TIER_GROWTH_CACHE
    raw = os.environ.get("LIN_SWAP_TIER_GROWTH", "") or _SWAP_TIER_GROWTH_DEFAULT
    out = {}
    try:
        for part in raw.split(","):
            if ":" not in part:
                continue
            label, _, pct = part.rpartition(":")
            label = label.strip().lower()
            try:
                val = int(float(pct.strip()))
            except (TypeError, ValueError):
                continue
            if label:
                out[label] = min(100, max(20, val))
    except Exception:
        out = {}
    if not out:
        for part in _SWAP_TIER_GROWTH_DEFAULT.split(","):
            label, _, pct = part.rpartition(":")
            out[label.strip().lower()] = int(pct)
    _SWAP_TIER_GROWTH_CACHE = out
    return out


def _swap_growth_for(access: dict) -> tuple[int, str]:
    """(growth pct, tier label shown to the user) for an ALLOWED patreon-access
    decision. Flat 25% by owner ruling; unmapped tiers get the fallback pct."""
    if (access or {}).get("via") == "admin":
        return _SWAP_FALLBACK_GROWTH_PCT, "Admin"
    tier = str((access or {}).get("tier") or "").strip()
    # Streamer Pack (2026-08-25): a streamer holds no tier role, so the label
    # fell through to the literal word "Patreon" and the apex refusal read
    # "requiere el nivel Apex de Patreon - tu nivel actual es Patreon".
    if not tier and (access or {}).get("via") == "streamer":
        tier = "Streamer"
    growth_map = _swap_tier_growth_map()
    pct = growth_map.get(tier.lower())
    if pct is None:
        return _SWAP_FALLBACK_GROWTH_PCT, (tier or "Patreon")
    return pct, tier


def _swap_tier_view(user) -> tuple[int, str]:
    """Sync (no Discord call) tier view for GET /population — persisted fields
    only; the POST does the LIVE role read."""
    u = user or {}
    if _is_owner(u):
        return _SWAP_FALLBACK_GROWTH_PCT, "Admin"
    tier = str(u.get("discord_tier_role") or "").strip()
    if not tier and u.get("patreon_patron_status") == "active_patron":
        tier = str(_patreon_tier_key(u.get("patreon_tier_name")) or "")
    if not tier and u.get("discord_streamer_role"):
        tier = "Streamer"
    pct = _swap_tier_growth_map().get(tier.lower()) if tier else None
    if pct is None:
        return _SWAP_FALLBACK_GROWTH_PCT, (tier or "Patreon")
    return pct, tier


def _swap_global_cd_remaining(user) -> int:
    until = (user or {}).get("swap_cd_until")
    if not until:
        return 0
    try:
        end = datetime.fromisoformat(until)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    except Exception:
        return 0
    return max(0, int((end - datetime.now(timezone.utc)).total_seconds()))


# mod fail_reason -> Spanish the player can act on (names the rejected thing)
_SWAP_FAIL_ES = {
    "feature_disabled": "El respawn está temporalmente desactivado en el servidor.",
    "not_alive": "Tu dinosaurio debe estar vivo para hacer respawn.",
    "already_that_species": "Ya estás jugando como esa especie.",
    "bad_target_class": "Esa especie no está disponible ahora mismo.",
    "class_resolve_failed": "Esa especie no está disponible ahora mismo.",
    "no_spawn_candidate": "No hay espacio seguro para aparecer donde estás — muévete a una zona abierta e inténtalo de nuevo.",
    "possess_failed": "El respawn falló y conservaste tu dinosaurio actual. Inténtalo de nuevo.",
    "rolled_back": "El respawn falló y conservaste tu dinosaurio actual. Inténtalo de nuevo.",
    "possess_lost": "El respawn se interrumpió (¿saliste del servidor?). Revisa tu dino en el juego.",
    "lost_both": "El respawn se interrumpió — entra al juego y revisa tu dinosaurio.",
    "restore_in_progress": "Tienes una recuperación de la Bóveda en progreso — espera a que termine.",
    "swap_in_progress": "Ya hay un respawn en progreso.",
    "actor_not_found": "El servidor aún no te ve en partida — espera unos segundos e inténtalo de nuevo.",
    "no_controller": "El servidor aún no te ve en partida — espera unos segundos e inténtalo de nuevo.",
    "no_location": "No pudimos ubicar a tu dinosaurio — inténtalo de nuevo.",
    "no_world": "El servidor de juego no está listo — inténtalo de nuevo en unos segundos.",
}


# Swapped dinos arrive with empty nutrient meters. Give them a starter diet at
# ~30% (owner ask 2026-07-16 "ensure they get like 30% protein"): uniform
# carbs/protein/lipids at LIN_SWAP_DIET_FRACTION of the species' size-scaled max
# (full-adult baseline × growth), mirroring the proven vault-redeem diet model
# so it reads ~30% on the in-game meter regardless of species/growth.
_SWAP_DIET_FRACTION = float(os.environ.get("LIN_SWAP_DIET_FRACTION", "0.30") or "0.30")
_SWAP_DIET_FALLBACK = 800   # full-adult baseline for a species absent from the redeem table
# Species not in vault._REDEEM_DIET_BASELINES (Kentrosaurus was missing → its
# swaps/redeems came back empty). Mid-herbivore, ~Diabloceratops scale.
_SWAP_DIET_EXTRA = {"BP_Kentrosaurus_C": 1900}


def _swap_diet_payload(cls, growth_frac):
    """(carbs, protein, lipids) starter nutrients for a freshly-swapped dino."""
    cls = str(cls or "")
    full = _SWAP_DIET_EXTRA.get(cls)
    if full is None:
        base = vault._REDEEM_DIET_BASELINES.get(cls)
        full = base.get("protein") if isinstance(base, dict) else _SWAP_DIET_FALLBACK
    g = max(0.01, min(1.0, float(growth_frac or 0.25)))
    val = round(float(full) * g * _SWAP_DIET_FRACTION, 2)
    return (val, val, val)


def _cd_key(server, slug):
    return f"{server}:{slug}"

def _cooldown_remaining(user, server, slug):
    cds = user.get("pop_cd")
    if not isinstance(cds, dict):
        return 0
    cd = cds.get(_cd_key(server, slug))
    if not cd:
        return 0
    try:
        end = datetime.fromisoformat(cd)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    except Exception:
        return 0
    return max(0, int((end - datetime.now(timezone.utc)).total_seconds()))

def _unlock_actor_key(user):
    """Cooldown identity SHARED with the Discord unlock button: the same human
    gets one cooldown across both surfaces whenever Discord is linked."""
    did = str((user or {}).get("discord_id") or "").strip()
    return f"discord:{did}" if did else f"user:{(user or {}).get('id')}"


async def _active_unlocks(server):
    """Return {slug: seconds_remaining} for dinos GLOBALLY unlocked — read from
    the shared species_unlock_state.json that the bot's auto-enforce loop
    pushes to the game (the old Mongo pop_unlocks gold state was display-only
    and is retired). Degrades to {} with a warning, never raises."""
    try:
        by_class = await asyncio.to_thread(pop_control.active_unlocks)
    except Exception as e:
        logger.warning("[population] unlock state unavailable (%s)", e)
        return {}
    out = {}
    for cls, rem in by_class.items():
        slug = _pop_slug_for_class(cls)
        if slug:
            out[slug] = int(rem)
    return out

@api_router.get("/population")
async def get_population(server: str = "LIVE", user=Depends(get_current_user)):
    if not _is_subscriber(user):
        raise HTTPException(status_code=403, detail="Patreon Access es solo para suscriptores")
    # Single REAL server: total/details via RCON; caps/locks/per-species counts
    # from popcontrol truth (bot DB + lock file + players.json).
    try:
        details = await rcon_client.server_details() if rcon_client.is_configured() else {}
    except Exception:
        details = {}
    server_id = "LIVE"
    connected_ids, _names = await _rcon_online_players()
    view = await asyncio.to_thread(_popcontrol_live_view)
    unlocks = await _active_unlocks(server_id)
    # Global unlock cooldown (shared with the Discord button): shown on at-cap
    # cards so the Desbloquear button reflects the real wait.
    try:
        unlock_cd = await asyncio.to_thread(pop_control.unlock_cooldown_remaining, _unlock_actor_key(user))
    except Exception as e:
        logger.warning("[population] unlock cooldown unavailable (%s)", e)
        unlock_cd = 0
    dinos = {d["slug"]: d for d in seed_data.DINOSAURS}
    # Active dino: the mod's players.json row is the live truth; the log-tail
    # telemetry and the web active_dino card are display fallbacks only.
    sid = str(user.get("steam_id") or "").strip()
    my_row = await asyncio.to_thread(game_ipc.read_player_display, sid) if sid else None
    active_slug = None
    if isinstance(my_row, dict):
        active_slug = _pop_slug_for_class(
            my_row.get("dino") or my_row.get("dino_class") or my_row.get("class") or "")
    if not active_slug:
        live_me = game_tele.get_player(user.get("steam_id"))
        ad = user.get("active_dino") or {}
        active_slug = (live_me or {}).get("slug") or ad.get("slug")
    in_game = bool(isinstance(my_row, dict)) or await _is_user_in_game(user)
    species = []
    for slug, st in view.items():
        info = dinos.get(slug, {})
        cap = st["cap"]              # None = unlimited (popcontrol cap < 0)
        online = st["count"]
        unlock_rem = unlocks.get(slug, 0)
        unlocked = unlock_rem > 0
        # Locked in popcontrol (manual lock or auto cap-lock) = full for players,
        # exactly what the bot removes from the spawn menu via updateplayables.
        at_cap = st["locked"] or (cap is not None and online >= cap)
        if unlocked:
            status = "unlocked"          # someone bypassed the cap globally
        elif at_cap:
            status = "at_cap"            # full/locked, needs an unlock
        elif cap is not None and online >= cap * 0.8:
            status = "high"
        else:
            status = "playable"
        species.append({
            "slug": slug,
            "name": info.get("name", slug.title()),
            "diet": info.get("diet"),
            "image": info.get("image"),
            "render": info.get("render") or info.get("image"),
            "cap": cap,
            "unlimited": cap is None,
            "online": online,
            "over_cap": cap is not None and online > cap,
            "at_cap": at_cap,
            "locked": st["locked"],
            "unlocked": unlocked,
            "unlock_remaining": unlock_rem,
            "status": status,
            "apex": slug in seed_data.POP_APEX,
            "sub_only": slug in POP_SUB_ONLY,
            "is_active": in_game and active_slug == slug,
            "cooldown_remaining": max(
                _cooldown_remaining(user, server_id, slug),
                unlock_cd if at_cap else 0),
            # UNFOLDED per-slug cooldown for the Respawn button — the folded
            # field above absorbs the 1h GLOBAL unlock cooldown and must never
            # gate the swap perk (frontend pairs this with swap_cooldown_remaining)
            "respawn_cooldown_remaining": _cooldown_remaining(user, server_id, slug),
        })
    # full / unlocked (at max capacity) first, then by online desc
    species.sort(key=lambda s: (0 if (s["at_cap"] or s["unlocked"]) else 1, 0 if s["is_active"] else 1, -s["online"]))
    tracked = sum(st["count"] for st in view.values())
    total_players = details.get("players", len(connected_ids))
    servers = [{"id": server_id, "label": details.get("name", "Isla Nublar LATAM"),
                "players": total_players, "map": details.get("map"),
                "max_players": details.get("max_players")}]
    swap_view = _swap_tier_view(user)
    return {
        "server": server_id,
        "servers": servers,
        "total_players": total_players,
        "tracked_species": tracked,
        "unknown_players": max(0, int(total_players or 0) - tracked),
        "species": species,
        "in_game": in_game,
        "active_slug": active_slug,
        "cooldown_total": POP_COOLDOWN_SEC,
        "unlock_total": POP_UNLOCK_SEC,
        "unlock_cooldown_total": POP_UNLOCK_COOLDOWN_SEC,
        # respawn/swap view (persisted tier only — the POST does the LIVE read)
        "swap_enabled": _SWAP_ENABLED,
        "swap_growth_pct": swap_view[0],
        "swap_tier": swap_view[1],
        "swap_cooldown_remaining": _swap_global_cd_remaining(user),
        "source": "popcontrol",
    }

class PopSelectInput(BaseModel):
    server: str
    slug: str

@api_router.post("/population/unlock")
async def population_unlock(data: PopSelectInput, user=Depends(get_current_user)):
    """Patreon perk 'Bypass de Límites de Dinos': lift a CAP-locked species for
    POP_UNLOCK_SEC seconds for EVERYONE, for real — writes the shared
    species_unlock_state.json that the bot's popcontrol auto-enforce loop
    pushes to the game via RCON (<= one 60 s tick), not just page gold state.
    Access: admin, any configured Discord Patreon tier role (LIVE role read
    via _patreon_access), or an active patron. One global cooldown per human,
    shared with the Discord unlock button (keyed on the linked discord_id).
    Manual admin locks are NOT bypassable — caps only."""
    if not _is_subscriber(user):
        raise HTTPException(status_code=403, detail="Patreon Access es solo para suscriptores")
    if data.server not in ({s["id"] for s in seed_data.POP_SERVERS} | {"LIVE"}):
        raise HTTPException(status_code=400, detail="Servidor inválido")
    if data.slug not in _POPCONTROL_SLUGS:
        raise HTTPException(status_code=400, detail="Especie inválida")
    access = await _patreon_access(user)
    if not access.get("allowed"):
        raise HTTPException(status_code=403, detail=(
            "Para desbloquear necesitas un rol Patreon del Discord "
            "(Supporter / Apex / Elder / Adult / Sub Adult / Juvie) o ser patrón activo."))
    is_admin = access.get("via") == "admin"
    actor_key = _unlock_actor_key(user)
    if not is_admin:
        remaining = await asyncio.to_thread(pop_control.unlock_cooldown_remaining, actor_key)
        if remaining > 0:
            raise HTTPException(status_code=429, detail=f"Cooldown activo · {remaining}s")
    st = (await asyncio.to_thread(_popcontrol_live_view)).get(data.slug) or {}
    if st.get("locked"):
        raise HTTPException(status_code=400, detail=(
            "Esa especie fue bloqueada por un administrador — el bypass solo aplica a límites de capacidad."))
    cap = st.get("cap")
    if cap is None or int(st.get("count", 0)) < int(cap):
        raise HTTPException(status_code=400, detail="Esa especie no está al límite — ya es jugable.")
    cls = _POPCONTROL_SLUGS[data.slug]
    await asyncio.to_thread(
        pop_control.set_unlock, cls, POP_UNLOCK_SEC, actor_key,
        POP_UNLOCK_COOLDOWN_SEC, not is_admin)
    logger.info("[population] unlock accepted slug=%s cls=%s actor=%s admin=%d",
                data.slug, cls, actor_key, int(is_admin))
    return {"ok": True, "slug": data.slug, "server": data.server,
            "unlocked": True, "unlock_remaining": POP_UNLOCK_SEC,
            # the bot's fast unlock watcher applies the roster change in seconds
            "applies_in_s": 10,
            "cooldown_remaining": 0 if is_admin else POP_UNLOCK_COOLDOWN_SEC}

@api_router.post("/population/respawn")
async def population_respawn(data: PopSelectInput, user=Depends(get_current_user)):
    """Patreon perk: REAL in-game species swap ('like /swap'). Swaps the
    caller's LIVE dino to the chosen species at their Discord-tier growth via
    the mod's spawn+possess lane, holding the request open until the mod's
    terminal ack (<= SWAP_ACK_TIMEOUT_SEC). The old dino is destroyed only
    after the new one is verified alive+possessed; every failure keeps the
    original dino and returns a Spanish reason naming what was rejected."""
    if not _is_subscriber(user):
        raise HTTPException(status_code=403, detail="Patreon Access es solo para suscriptores")
    if not _SWAP_ENABLED:
        raise HTTPException(status_code=503, detail="El respawn está temporalmente desactivado.")
    if data.server not in ({s["id"] for s in seed_data.POP_SERVERS} | {"LIVE"}):
        raise HTTPException(status_code=400, detail="Servidor inválido")
    if data.slug not in _POPCONTROL_SLUGS:
        raise HTTPException(status_code=400, detail="Especie inválida")
    dinos = {d["slug"]: d for d in seed_data.DINOSAURS}
    sp_name = (dinos.get(data.slug) or {}).get("name", data.slug.title())

    # LIVE Discord tier-role read — the perk and its growth come from the role
    access = await _patreon_access(user)
    if not access.get("allowed"):
        raise HTTPException(status_code=403, detail=(
            "Para hacer respawn necesitas un rol Patreon del Discord "
            "(Apex / Elder / Adult / Sub Adult / Juvie) o ser patrón activo."))
    growth_pct, tier_label = _swap_growth_for(access)
    is_admin = access.get("via") == "admin"
    # Streamer Pack holders get the apex lane too (2026-08-25): the site already
    # grants them Desbloquear on the same cards, so refusing Respawn here was the
    # one surface where the free perk stopped half-way.
    is_streamer_access = access.get("via") == "streamer"
    if (data.slug in seed_data.POP_APEX and not is_admin and not is_streamer_access
            and str(tier_label).lower() != "apex"):
        raise HTTPException(status_code=403, detail=(
            f"{sp_name} requiere el nivel Apex de Patreon — tu nivel actual es {tier_label}."))

    # cooldowns: per-(server, especie) + one global respawn cooldown per user
    remaining = _cooldown_remaining(user, data.server, data.slug)
    if remaining > 0:
        raise HTTPException(status_code=429, detail=f"Cooldown activo · {remaining}s")
    g_remaining = _swap_global_cd_remaining(user)
    if g_remaining > 0 and not is_admin:
        raise HTTPException(status_code=429, detail=f"Espera {g_remaining}s antes de otro respawn.")

    # Owner ruling 2026-07-16 (~21:5xZ): respawn is the FULL-species perk — the
    # personal counterpart of Desbloquear. It only works INTO a species at max
    # capacity (that is the point: cap-locked species stay reachable for
    # patrons). Manual admin locks are still never bypassable.
    st = (await asyncio.to_thread(_popcontrol_live_view)).get(data.slug) or {}
    cls = _POPCONTROL_SLUGS[data.slug]
    if st.get("locked"):
        raise HTTPException(status_code=400, detail=(
            f"{sp_name} fue bloqueado por un administrador — el respawn no puede saltarse ese bloqueo."))
    cap = st.get("cap")
    at_cap = cap is not None and int(st.get("count", 0)) >= int(cap)
    if not at_cap:
        raise HTTPException(status_code=400, detail=(
            f"{sp_name} no está al límite — puedes elegirlo desde el menú de aparición del juego."))

    # the caller must be IN GAME with a live, healthy-enough dino
    sid = str(user.get("steam_id") or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Vincula tu cuenta de Steam primero.")
    row = await asyncio.to_thread(game_ipc.read_player, sid, True)
    if not isinstance(row, dict):
        raise HTTPException(status_code=400, detail=(
            "No estás en partida (o el servidor aún no te ve). Entra al servidor y espera unos segundos."))
    cur_slug = _pop_slug_for_class(row.get("dino") or row.get("dino_class") or "")
    if cur_slug == data.slug:
        raise HTTPException(status_code=400, detail=f"Ya estás jugando como {sp_name}.")
    # combat-escape guard: health + stamina only. NO hunger gate (owner ruling
    # 2026-07-16 — a starving dino may swap; the arrival gets full vitals anyway).
    if not (float(row.get("max_health") or 0) > 0 and float(row.get("max_stamina") or 0) > 0):
        raise HTTPException(status_code=409, detail=(
            "El servidor aún no cargó las estadísticas de tu dino. Espera unos segundos."))
    vital_fails = []
    hp = vault._pct(row, "health", "max_health")
    stp = vault._pct(row, "stamina", "max_stamina")
    if hp is not None and hp < vault.REDEEM_MIN_HEALTH_PCT:
        vital_fails.append(f"Demasiado herido: Salud {hp*100:.0f}% — necesitas {vault.REDEEM_MIN_HEALTH_PCT*100:.0f}%")
    if stp is not None and stp < vault.REDEEM_MIN_STAMINA_PCT:
        vital_fails.append(f"Demasiado cansado: Energía {stp*100:.0f}% — necesitas {vault.REDEEM_MIN_STAMINA_PCT*100:.0f}%")
    if vital_fails:
        raise HTTPException(status_code=409,
                            detail="No puedes hacer respawn todavía: " + " · ".join(vital_fails))
    try:
        redeem_pending = await asyncio.to_thread(vault._steam_has_fresh_redeem_pending, sid)
    except Exception as e:
        # bot-DB outage must not 500 the perk — the mod refuses mid-restore
        # swaps itself (restore_in_progress), so degrade open like the GET does
        logger.warning("[population] redeem-pending check unavailable sid=%s (%s)", sid, e)
        redeem_pending = False
    if redeem_pending:
        raise HTTPException(status_code=409, detail=(
            "Tienes una recuperación de la Bóveda en progreso — espera a que termine."))

    # single in-flight swap per player (single-worker uvicorn)
    now_mono = time.monotonic()
    started = _SWAP_INFLIGHT.get(sid)
    if started is not None and (now_mono - started) < 60:
        raise HTTPException(status_code=409, detail="Ya hay un respawn en progreso.")
    _SWAP_INFLIGHT[sid] = now_mono
    try:
        cmd_id = uuid.uuid4().hex
        cmd = {"type": "swap", "steamid": sid, "cmd_id": cmd_id,
               "target_class": cls, "growth": round(growth_pct / 100.0, 4)}
        wrote = await asyncio.to_thread(game_ipc.write_game_command, cmd)
        if not wrote:
            raise HTTPException(status_code=503, detail="El servidor de juego no está disponible ahora mismo.")
        logger.info("[population] swap start sid=%s slug=%s cls=%s growth=%d%% tier=%s cmd_id=%s",
                    sid, data.slug, cls, growth_pct, tier_label, cmd_id)
        deadline = time.monotonic() + SWAP_ACK_TIMEOUT_SEC
        status = None
        while time.monotonic() < deadline:
            status = await asyncio.to_thread(game_ipc.read_swap_status, sid, cmd_id)
            if isinstance(status, dict):
                break
            await asyncio.sleep(1.0)

        if isinstance(status, dict) and status.get("event") == "swap_ok":
            key = _cd_key(data.server, data.slug)
            cd_until = (datetime.now(timezone.utc) + timedelta(seconds=POP_COOLDOWN_SEC)).isoformat()
            swap_until = (datetime.now(timezone.utc) + timedelta(seconds=SWAP_COOLDOWN_SEC)).isoformat()
            try:
                if not isinstance(user.get("pop_cd"), dict):
                    await db.users.update_one({"id": user["id"]}, {"$unset": {"pop_cd": "", "pop_selection": ""}})
                await db.users.update_one({"id": user["id"]}, {"$set": {
                    f"pop_cd.{key}": cd_until, "swap_cd_until": swap_until}})
            except Exception as e:
                # a completed swap must never 500 on a cooldown stamp
                logger.warning("[population] swap cd stamp failed sid=%s (%s)", sid, e)
            online = int(st.get("count", 0)) + 1
            # Swapped dinos spawn with EMPTY nutrient meters — give them a
            # starter diet (~30% protein, owner ask 2026-07-16) via the same
            # guarded diet lane the vault redeem uses. Best-effort: a diet-write
            # failure must never fail an otherwise-completed swap.
            try:
                actor_name = str(status.get("actor_name") or "").strip()
                if actor_name:
                    dc, dp, dl = _swap_diet_payload(cls, growth_pct / 100.0)
                    await asyncio.to_thread(game_ipc.write_diet_command, {
                        "class": cls, "actor_name": actor_name, "steamid": sid,
                        "carbs": dc, "protein": dp, "lipids": dl})
                    logger.info("[population] swap diet sid=%s class=%s C/P/L=%.1f", sid, cls, dp)
            except Exception as e:
                logger.warning("[population] swap diet write failed sid=%s (%s)", sid, e)
            logger.info("[population] swap ok sid=%s slug=%s growth=%.3f actor=%s",
                        sid, data.slug, float(status.get("growth") or 0), status.get("actor_name") or "")
            return {"ok": True, "slug": data.slug, "server": data.server, "online": online,
                    "cap": cap, "over_cap": (cap is not None and online > cap),
                    "cooldown_remaining": POP_COOLDOWN_SEC, "growth_pct": growth_pct,
                    "tier": tier_label, "actor_name": status.get("actor_name") or ""}

        if isinstance(status, dict):  # swap_failed
            reason = str(status.get("fail_reason") or "")
            logger.info("[population] swap failed sid=%s slug=%s reason=%s", sid, data.slug, reason)
            raise HTTPException(status_code=409, detail=_SWAP_FAIL_ES.get(
                reason, f"El respawn falló ({reason or 'desconocido'}). Conservaste tu dinosaurio."))

        # timeout: the mod may still land it — short retry cooldown, honest copy
        swap_until = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
        try:
            await db.users.update_one({"id": user["id"]}, {"$set": {"swap_cd_until": swap_until}})
        except Exception as e:
            logger.warning("[population] swap timeout cd stamp failed sid=%s (%s)", sid, e)
        logger.warning("[population] swap ack timeout sid=%s slug=%s cmd_id=%s", sid, data.slug, cmd_id)
        raise HTTPException(status_code=409, detail=(
            "El respawn sigue en proceso — mira tu dinosaurio en el juego. "
            "Si no ocurrió nada, vuelve a intentarlo en 1 minuto."))
    finally:
        _SWAP_INFLIGHT.pop(sid, None)

@api_router.post("/population/leave")
async def population_leave(user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$unset": {"pop_selection": ""}})
    return {"ok": True}



# ================= CASINO (real games, virtual Survival coins) =================
CASINO_MIN_BET = 10
CASINO_MAX_BET = 100000
DICE_EDGE = 0.02
CRASH_EDGE = 0.03
CRASH_K = 0.8  # multiplier growth: m(t) = e^(k*t), t in seconds (shared with client; lower = slower/more realistic)
_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def _rank_val(rank):
    if rank == "A":
        return 11
    if rank in ("J", "Q", "K"):
        return 10
    return int(rank)


def _new_deck():
    deck = [r + s for s in "SHDC" for r in _RANKS]
    _random.shuffle(deck)
    return deck


def _hand_value(cards):
    total = sum(_rank_val(c[:-1]) for c in cards)
    aces = sum(1 for c in cards if c[:-1] == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


async def _casino_charge(user_id, amount):
    res = await db.users.update_one({"id": user_id, "coins": {"$gte": amount}}, {"$inc": {"coins": -amount}})
    if res.modified_count == 0:
        raise HTTPException(status_code=400, detail="Fondos insuficientes (Insufficient balance)")


async def _casino_credit(user_id, amount):
    if amount > 0:
        await db.users.update_one({"id": user_id}, {"$inc": {"coins": amount}})


async def _casino_balance(user_id):
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "coins": 1})
    return u["coins"] if u else 0


async def _feed_win(user, game, payout, multiplier, kind="casino"):
    await db.chat_messages.insert_one({
        "id": new_id(), "user_id": "system", "name": user.get("persona_name") or "Survivor",
        "avatar": user.get("avatar"), "role": "system", "channel": "feed",
        "text": f"won {payout:,} CC on {game}" + (f" ({round(multiplier, 2)}x)" if multiplier else ""),
        "win": {"game": game, "payout": payout, "multiplier": round(multiplier or 0, 2), "kind": kind},
        "created_at": now_iso(),
    })


async def _record_bet(user, game, bet, payout, multiplier, result):
    await db.casino_bets.insert_one({
        "id": new_id(), "user_id": user["id"], "user_name": user.get("persona_name"),
        "avatar": user.get("avatar"), "game": game, "bet": bet, "payout": payout,
        "net": payout - bet, "multiplier": round(multiplier, 2), "result": result,
        "created_at": now_iso(),
    })
    # feed only — hard-to-get / notable wins. Regular chats never show win spam.
    if result == "win" and (payout - bet >= 25000 or multiplier >= 5):
        await _feed_win(user, game.capitalize(), payout, multiplier, "casino")


def _validate_bet(bet):
    if not isinstance(bet, int) or bet < CASINO_MIN_BET or bet > CASINO_MAX_BET:
        raise HTTPException(status_code=400, detail=f"La apuesta debe estar entre {CASINO_MIN_BET} y {CASINO_MAX_BET}")


async def _pf_draw(user_id, n):
    """Draw n provably-fair floats from the player's active seed and advance the nonce once."""
    seed = await _pf_get_active(user_id)
    nonce = seed["nonce"]
    floats = [_pf_float_i(seed["server_seed"], seed["client_seed"], nonce, i) for i in range(max(1, n))]
    await db.pf_seeds.update_one({"id": seed["id"]}, {"$inc": {"nonce": 1}})
    proof = {"server_seed_hash": seed["server_seed_hash"], "client_seed": seed["client_seed"], "nonce": nonce}
    return floats, proof


# ---------- Blackjack ----------
class BjDealInput(BaseModel):
    bet: int


def _bj_state(g, reveal=False):
    finished = g["status"] != "playing"
    show_dealer = reveal or finished
    return {
        "id": g["id"], "bet": g["bet"], "status": g["status"], "result": g.get("result"),
        "player": g["player"], "player_value": _hand_value(g["player"]),
        "dealer": g["dealer"] if show_dealer else [g["dealer"][0], "??"],
        "dealer_value": _hand_value(g["dealer"]) if show_dealer else _rank_val(g["dealer"][0][:-1]),
        "can_double": g["status"] == "playing" and len(g["player"]) == 2,
        "payout": g.get("payout", 0),
        "fairness": g.get("fairness"),
    }


async def _bj_resolve(g, dealer_play=True):
    if dealer_play:
        while _hand_value(g["dealer"]) < 17:
            g["dealer"].append(g["deck"].pop())
    pv, dv = _hand_value(g["player"]), _hand_value(g["dealer"])
    bet = g["bet"]
    player_bj = len(g["player"]) == 2 and pv == 21 and not g.get("doubled")
    dealer_bj = len(g["dealer"]) == 2 and dv == 21
    if pv > 21:
        result, payout, mult = "lose", 0, 0
    elif player_bj and not dealer_bj:
        result, payout, mult = "blackjack", int(bet * 2.5), 2.5
    elif dv > 21 or pv > dv:
        result, payout, mult = "win", bet * 2, 2.0
    elif pv < dv:
        result, payout, mult = "lose", 0, 0
    else:
        result, payout, mult = "push", bet, 1.0
    g["status"], g["result"], g["payout"] = "finished", result, payout
    # ATOMIC SETTLE: two concurrent stand/hit/double calls both read the same
    # "playing" hand, so crediting first would pay the same hand twice. Flipping
    # the status IS the claim -- only the caller that actually moved it off
    # "playing" pays out.
    claimed = await db.casino_bj.update_one(
        {"id": g["id"], "status": "playing"},
        {"$set": {"deck": g["deck"], "dealer": g["dealer"], "player": g["player"],
                  "status": "finished", "result": result, "payout": payout,
                  "doubled": g.get("doubled", False)}})
    if claimed.modified_count == 0:
        return
    await _casino_credit(g["user_id"], payout)
    user = await db.users.find_one({"id": g["user_id"]}, {"_id": 0})
    await _record_bet(user, "blackjack", bet + (bet if g.get("doubled") else 0), payout, mult, "win" if payout > (bet + (bet if g.get("doubled") else 0)) else ("push" if result == "push" else "lose"))


async def _bj_get(user):
    g = await db.casino_bj.find_one({"user_id": user["id"], "status": "playing"}, {"_id": 0})
    return g


@api_router.get("/casino/blackjack")
async def bj_current(user=Depends(get_current_user)):
    g = await _bj_get(user)
    return {"game": _bj_state(g) if g else None, "balance": await _casino_balance(user["id"])}


@api_router.post("/casino/blackjack/deal")
async def bj_deal(data: BjDealInput, user=Depends(get_current_user)):
    _validate_bet(data.bet)
    if await _bj_get(user):
        raise HTTPException(status_code=400, detail="Termina tu mano actual primero")
    await _casino_charge(user["id"], data.bet)
    floats, proof = await _pf_draw(user["id"], 52)
    deck = _pf_shuffle([r + s for s in "SHDC" for r in _RANKS], floats)
    g = {"id": new_id(), "user_id": user["id"], "bet": data.bet, "deck": deck,
         "player": [deck.pop(), deck.pop()], "dealer": [deck.pop(), deck.pop()],
         "status": "playing", "doubled": False, "fairness": proof, "created_at": now_iso()}
    await db.casino_bj.insert_one(dict(g))
    if _hand_value(g["player"]) == 21 or _hand_value(g["dealer"]) == 21:
        await _bj_resolve(g, dealer_play=False)
    return {"game": _bj_state(g), "balance": await _casino_balance(user["id"])}


@api_router.post("/casino/blackjack/hit")
async def bj_hit(user=Depends(get_current_user)):
    g = await _bj_get(user)
    if not g:
        raise HTTPException(status_code=400, detail="No hay una mano activa")
    g["player"].append(g["deck"].pop())
    if _hand_value(g["player"]) >= 21:
        await _bj_resolve(g, dealer_play=_hand_value(g["player"]) <= 21)
    else:
        await db.casino_bj.update_one({"id": g["id"]}, {"$set": {"deck": g["deck"], "player": g["player"]}})
    return {"game": _bj_state(g), "balance": await _casino_balance(user["id"])}


@api_router.post("/casino/blackjack/stand")
async def bj_stand(user=Depends(get_current_user)):
    g = await _bj_get(user)
    if not g:
        raise HTTPException(status_code=400, detail="No hay una mano activa")
    await _bj_resolve(g, dealer_play=True)
    return {"game": _bj_state(g), "balance": await _casino_balance(user["id"])}


@api_router.post("/casino/blackjack/double")
async def bj_double(user=Depends(get_current_user)):
    g = await _bj_get(user)
    if not g or len(g["player"]) != 2:
        raise HTTPException(status_code=400, detail="No puedes doblar ahora")
    await _casino_charge(user["id"], g["bet"])
    g["doubled"] = True
    g["player"].append(g["deck"].pop())
    await _bj_resolve(g, dealer_play=_hand_value(g["player"]) <= 21)
    return {"game": _bj_state(g), "balance": await _casino_balance(user["id"])}


# ---------- Crash (multiplayer live loop defined near the bottom of this file) ----------


# ---------- Mines ----------
class MinesStartInput(BaseModel):
    bet: int
    mines: int = 3


def _mines_multiplier(mines, picks):
    if picks == 0:
        return 1.0
    m = 1.0
    for i in range(picks):
        m *= (25 - i) / (25 - mines - i)
    return math.floor(m * (1 - DICE_EDGE) * 100) / 100


@api_router.get("/casino/mines")
async def mines_current(user=Depends(get_current_user)):
    g = await db.casino_mines.find_one({"user_id": user["id"], "status": "active"}, {"_id": 0})
    if not g:
        return {"game": None, "balance": await _casino_balance(user["id"])}
    return {"game": {"id": g["id"], "bet": g["bet"], "mines": g["mines"], "revealed": g["revealed"],
            "multiplier": _mines_multiplier(g["mines"], len(g["revealed"])),
            "next_multiplier": _mines_multiplier(g["mines"], len(g["revealed"]) + 1)},
            "balance": await _casino_balance(user["id"])}


@api_router.post("/casino/mines/start")
async def mines_start(data: MinesStartInput, user=Depends(get_current_user)):
    _validate_bet(data.bet)
    if not 1 <= data.mines <= 24:
        raise HTTPException(status_code=400, detail="Las minas deben estar entre 1 y 24")
    await db.casino_mines.delete_many({"user_id": user["id"], "status": "active"})
    await _casino_charge(user["id"], data.bet)
    floats, proof = await _pf_draw(user["id"], 25)
    order = _pf_shuffle(list(range(25)), floats)
    positions = sorted(order[:data.mines])
    g = {"id": new_id(), "user_id": user["id"], "bet": data.bet, "mines": data.mines,
         "mine_positions": positions, "revealed": [], "status": "active", "fairness": proof, "created_at": now_iso()}
    await db.casino_mines.insert_one(dict(g))
    return {"game": {"id": g["id"], "bet": g["bet"], "mines": g["mines"], "revealed": [],
            "multiplier": 1.0, "next_multiplier": _mines_multiplier(data.mines, 1), "fairness": proof},
            "balance": await _casino_balance(user["id"])}


class MinesRevealInput(BaseModel):
    index: int


@api_router.post("/casino/mines/reveal")
async def mines_reveal(data: MinesRevealInput, user=Depends(get_current_user)):
    g = await db.casino_mines.find_one({"user_id": user["id"], "status": "active"}, {"_id": 0})
    if not g:
        raise HTTPException(status_code=400, detail="No hay juego activo")
    if not 0 <= data.index < 25 or data.index in g["revealed"]:
        raise HTTPException(status_code=400, detail="Casilla invalida")
    if data.index in g["mine_positions"]:
        busted = await db.casino_mines.update_one({"id": g["id"], "status": "active"}, {"$set": {"status": "busted"}})
        if busted.modified_count == 0:
            raise HTTPException(status_code=409, detail="Esta partida ya terminó")
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        await _record_bet(u, "mines", g["bet"], 0, 0, "lose")
        return {"result": "lose", "hit": data.index, "mine_positions": g["mine_positions"], "balance": await _casino_balance(user["id"])}
    g["revealed"].append(data.index)
    await db.casino_mines.update_one({"id": g["id"]}, {"$set": {"revealed": g["revealed"]}})
    safe_left = 25 - g["mines"] - len(g["revealed"])
    mult = _mines_multiplier(g["mines"], len(g["revealed"]))
    if safe_left == 0:  # cleared everything → auto cashout
        return await _mines_do_cashout(user, g, mult)
    return {"result": "safe", "revealed": g["revealed"], "multiplier": mult,
            "next_multiplier": _mines_multiplier(g["mines"], len(g["revealed"]) + 1),
            "balance": await _casino_balance(user["id"])}


async def _mines_do_cashout(user, g, mult):
    payout = int(g["bet"] * mult)
    # ATOMIC SETTLE: same claim as blackjack -- concurrent cashouts (or a cashout
    # racing the auto-cashout on the last safe tile) each read one active game, so
    # only the caller that moves it off "active" is allowed to pay it.
    claimed = await db.casino_mines.update_one({"id": g["id"], "status": "active"}, {"$set": {"status": "cashed"}})
    if claimed.modified_count == 0:
        raise HTTPException(status_code=409, detail="Esta partida ya fue cobrada")
    await _casino_credit(user["id"], payout)
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    await _record_bet(u, "mines", g["bet"], payout, mult, "win")
    return {"result": "cashout", "multiplier": mult, "payout": payout,
            "mine_positions": g["mine_positions"], "balance": await _casino_balance(user["id"])}


@api_router.post("/casino/mines/cashout")
async def mines_cashout(user=Depends(get_current_user)):
    g = await db.casino_mines.find_one({"user_id": user["id"], "status": "active"}, {"_id": 0})
    if not g or not g["revealed"]:
        raise HTTPException(status_code=400, detail="Revela al menos una casilla primero")
    return await _mines_do_cashout(user, g, _mines_multiplier(g["mines"], len(g["revealed"])))


# ---------- Dice ----------
class DiceInput(BaseModel):
    bet: int
    target: float
    direction: str  # "over" | "under"


@api_router.post("/casino/dice/roll")
async def dice_roll(data: DiceInput, user=Depends(get_current_user)):
    _validate_bet(data.bet)
    target = round(max(2.0, min(98.0, data.target)), 2)
    over = data.direction == "over"
    chance = (100 - target) if over else target
    if chance < 2 or chance > 98:
        raise HTTPException(status_code=400, detail="Objetivo invalido")
    await _casino_charge(user["id"], data.bet)
    floats, proof = await _pf_draw(user["id"], 1)
    roll = math.floor(floats[0] * 10000) / 100  # 0.00 - 99.99
    win = (roll > target) if over else (roll < target)
    mult = round((100 / chance) * (1 - DICE_EDGE), 4)
    payout = int(data.bet * mult) if win else 0
    await _casino_credit(user["id"], payout)
    await _record_bet(user, "dice", data.bet, payout, mult if win else 0, "win" if win else "lose")
    return {"roll": roll, "win": win, "multiplier": mult, "payout": payout,
            "target": target, "direction": data.direction, "fairness": proof, "balance": await _casino_balance(user["id"])}


# ---------- Dino Roll (multiplayer, server-driven) ----------
# NOTE: the live multiplayer Roll (continuous rounds + Triple Green Bonus Pool)
# is implemented near the bottom of this file (roll_loop / roll_state / roll_bet).


# ---------- Casino history / stats / leaderboard ----------
@api_router.get("/casino/history")
async def casino_history(user=Depends(get_current_user)):
    items = await db.casino_bets.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(30)
    return items


@api_router.get("/casino/stats")
async def casino_stats(user=Depends(get_current_user)):
    pipeline = [{"$match": {"user_id": user["id"]}},
                {"$group": {"_id": None, "wagered": {"$sum": "$bet"}, "won": {"$sum": "$payout"},
                            "net": {"$sum": "$net"}, "games": {"$sum": 1}, "biggest": {"$max": "$net"}}}]
    agg = await db.casino_bets.aggregate(pipeline).to_list(1)
    s = agg[0] if agg else {}
    wins = await db.casino_bets.count_documents({"user_id": user["id"], "result": "win"})
    return {"wagered": s.get("wagered", 0), "won": s.get("won", 0), "net": s.get("net", 0),
            "games": s.get("games", 0), "biggest_win": s.get("biggest", 0), "wins": wins}


@api_router.get("/casino/leaderboard")
async def casino_leaderboard():
    pipeline = [{"$group": {"_id": "$user_id", "name": {"$last": "$user_name"}, "avatar": {"$last": "$avatar"},
                            "net": {"$sum": "$net"}, "games": {"$sum": 1}, "biggest": {"$max": "$net"}}},
                {"$sort": {"net": -1}}, {"$limit": 20}]
    rows = await db.casino_bets.aggregate(pipeline).to_list(20)
    return [{"user_id": r["_id"], "name": r.get("name"), "avatar": r.get("avatar"),
             "net": r["net"], "games": r["games"], "biggest_win": r["biggest"]} for r in rows]


# ================= GLOBAL CHAT =================
CHAT_CHANNELS = ["global", "na", "eu", "au", "feed"]


class ChatInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=300)
    channel: str = "global"


async def _chat_online():
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
    return await db.chat_presence.count_documents({"ts": {"$gt": cutoff}})


async def _chat_channel_counts():
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
    counts = {c: 0 for c in CHAT_CHANNELS if c != "feed"}
    total = 0
    async for p in db.chat_presence.find({"ts": {"$gt": cutoff}}, {"_id": 0, "channel": 1}):
        total += 1
        ch = p.get("channel") or "global"
        if ch in counts:
            counts[ch] += 1
    return total, counts


@api_router.get("/chat/messages")
async def chat_messages(channel: str = "global", after: Optional[str] = None):
    ch = channel if channel in CHAT_CHANNELS else "global"
    q = {"channel": ch}
    if after:
        q["created_at"] = {"$gt": after}
    items = await db.chat_messages.find(q, {"_id": 0}).sort("created_at", -1).to_list(50)
    total, counts = await _chat_channel_counts()
    return {"messages": list(reversed(items)), "online": total, "channels": counts, "cooldown": await chat_cooldown_value()}


@api_router.get("/chat/poll")
async def chat_poll(channel: str = "global", after: Optional[str] = None, user=Depends(get_current_user)):
    ch = channel if channel in CHAT_CHANNELS else "global"
    await db.chat_presence.update_one({"user_id": user["id"]},
        {"$set": {"user_id": user["id"], "name": user.get("persona_name"), "channel": ch, "ts": now_iso()}}, upsert=True)
    return await chat_messages(channel=channel, after=after)


@api_router.post("/chat/send")
async def chat_send(data: ChatInput, user=Depends(get_current_user)):
    ch = data.channel if data.channel in CHAT_CHANNELS else "global"
    if ch == "feed":
        raise HTTPException(status_code=400, detail="El feed es de solo lectura")
    last = await db.chat_messages.find_one({"user_id": user["id"], "channel": {"$ne": "feed"}}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
    cd = await chat_cooldown_value()
    if last and cd > 0:
        delta = datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(last["created_at"]).timestamp()
        if delta < cd:
            raise HTTPException(status_code=429, detail=f"Modo lento: espera {int(cd - delta) + 1}s")
    text = data.text.strip()[:300]
    if not text:
        raise HTTPException(status_code=400, detail="Mensaje vacio")
    doc = {"id": new_id(), "user_id": user["id"], "name": user.get("persona_name") or "Survivor",
           "avatar": user.get("avatar"), "role": user.get("role"),
           "level": 1 + int((max(0, int(user.get("xp", 0))) ** 0.5) / 10),
           "staff_rank": user.get("staff_rank"), "staff_meta": staff_meta(user.get("staff_rank")),
           "cosmetics": resolve_cosmetics(user),
           "channel": ch, "text": text, "created_at": now_iso()}
    await db.chat_messages.insert_one(dict(doc))
    return {k: v for k, v in doc.items() if k != "_id"}


@api_router.delete("/chat/messages/{msg_id}")
async def chat_delete(msg_id: str, user=Depends(get_current_user)):
    if not _has_chat_mod(user):
        raise HTTPException(status_code=403, detail="No permitido")
    res = await db.chat_messages.update_one(
        {"id": msg_id},
        {"$set": {"deleted": True, "deleted_by": user.get("persona_name") or "Staff", "text": "", "cosmetics": None}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    await add_log(user.get("persona_name"), "chat_delete", msg_id, {})
    return {"ok": True}


class ChatSettingsInput(BaseModel):
    chat_cooldown_seconds: int


@api_router.get("/admin/settings")
async def admin_get_settings(admin=Depends(get_admin_user)):
    return {"chat_cooldown_seconds": await chat_cooldown_value()}


@api_router.patch("/admin/settings")
async def admin_update_settings(data: ChatSettingsInput, admin=Depends(get_admin_user)):
    global _chat_cooldown
    val = max(0, min(300, int(data.chat_cooldown_seconds)))
    await db.settings.update_one({"_id": "app"}, {"$set": {"chat_cooldown_seconds": val}}, upsert=True)
    _chat_cooldown = val
    await add_log(admin["persona_name"], "update_settings", "chat_cooldown", {"seconds": val})
    return {"chat_cooldown_seconds": val}


class RollChancesInput(BaseModel):
    green: float
    red: float
    black: float


@api_router.get("/admin/roll-config")
async def admin_get_roll_config(owner=Depends(get_owner_user)):
    cfg = await roll_config_value()
    return {"chances": cfg["chances"], "mult": cfg["mult"], "defaults": ROLL_CHANCES_DEFAULT}


@api_router.patch("/admin/roll-config")
async def admin_update_roll_config(data: RollChancesInput, owner=Depends(get_owner_user)):
    global _roll_cfg
    vals = {"green": max(0.0, float(data.green)), "red": max(0.0, float(data.red)), "black": max(0.0, float(data.black))}
    total = vals["green"] + vals["red"] + vals["black"]
    if total <= 0:
        raise HTTPException(status_code=400, detail="Las probabilidades deben sumar más de 0")
    # normalise to percentages that sum to 100 for clean storage/display
    chances = {k: round(v / total * 100, 3) for k, v in vals.items()}
    await db.settings.update_one({"_id": "app"}, {"$set": {"roll_chances": chances}}, upsert=True)
    _roll_cfg = None  # invalidate cache
    await add_log(owner["persona_name"], "update_roll_chances", "roll", chances)
    return {"chances": chances, "mult": ROLL_MULT}


class GiftDayInput(BaseModel):
    day: int
    coins: int = 0
    vip: int = 0
    xp: int = 0
    special: Optional[str] = None


class GiftScheduleInput(BaseModel):
    schedule: List[GiftDayInput]


@api_router.get("/admin/gift-schedule")
async def admin_get_gift(admin=Depends(get_admin_user)):
    tiers = [{"tier": t, "name": cosmetics_data.EGGS[t]["name"], "color": cosmetics_data.EGGS[t]["color"]}
             for t in cosmetics_data.EGG_TIERS]
    return {"schedule": await gift_schedule_value(), "egg_tiers": tiers}


@api_router.put("/admin/gift-schedule")
async def admin_put_gift(data: GiftScheduleInput, admin=Depends(get_admin_user)):
    global _gift_schedule
    sched = []
    for g in sorted(data.schedule, key=lambda x: x.day)[:7]:
        special = g.special if g.special in cosmetics_data.EGGS else None
        sched.append({"day": int(g.day), "coins": max(0, int(g.coins)),
                      "vip": max(0, int(g.vip)), "xp": max(0, int(g.xp)), "special": special})
    if not sched:
        raise HTTPException(status_code=400, detail="Schedule vacío")
    await db.settings.update_one({"_id": "gift_schedule"}, {"$set": {"schedule": sched}}, upsert=True)
    _gift_schedule = sched
    await add_log(admin["persona_name"], "update_gift_schedule", None, {"days": len(sched)})
    return {"schedule": sched}


# ---------- Quests (in-game action driven, seeded from quest_data) ----------
class MultiplierEventInput(BaseModel):
    species: str                     # one of quest_data.EVENT_SPECIES (any casing)
    duration_hours: int = quest_data.MULT_EVENT_DEFAULT_HOURS
    multiplier: int = quest_data.MULT_EVENT_DEFAULT


def _quest_period_key(category: str, ref: Optional[datetime] = None) -> str:
    """Period bucket a quest's progress belongs to (UTC)."""
    ref = ref or datetime.now(timezone.utc)
    if category == "weekly":
        iso = ref.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if category == "achievement":
        return "all"
    return ref.strftime("%Y-%m-%d")  # daily


def _quest_reset_seconds() -> dict:
    now = datetime.now(timezone.utc)
    next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    days_until_mon = (7 - now.weekday()) % 7 or 7
    next_week = (now + timedelta(days=days_until_mon)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"daily": int((next_day - now).total_seconds()),
            "weekly": int((next_week - now).total_seconds())}


def _quest_pk(quest: dict) -> str:
    """Progress period key for one quest (daily date / ISO week / 'all')."""
    return _quest_period_key(quest.get("category", "daily"))


async def _quest_progress_doc(user_id: str, quest: dict):
    return await db.quest_progress.find_one(
        {"user_id": user_id, "quest_id": quest["id"], "period_key": _quest_pk(quest)}, {"_id": 0})


async def _bump_quest_progress(user_id: str, q: dict, amount: int, absolute: Optional[int] = None):
    """Clamped, claim-guarded progress write shared by every tracker lane."""
    pk = _quest_pk(q)
    target = int(q.get("objective", {}).get("target", 1))
    cur = await db.quest_progress.find_one(
        {"user_id": user_id, "quest_id": q["id"], "period_key": pk}, {"_id": 0})
    if cur and cur.get("claimed"):
        return
    if absolute is not None:
        new_prog = min(target, max(int(cur.get("progress", 0)) if cur else 0, absolute))
    else:
        new_prog = min(target, (cur.get("progress", 0) if cur else 0) + amount)
    await db.quest_progress.update_one(
        {"user_id": user_id, "quest_id": q["id"], "period_key": pk},
        {"$set": {"progress": new_prog},
         "$setOnInsert": {"id": new_id(), "user_id": user_id, "quest_id": q["id"],
                          "period_key": pk, "claimed": False, "created_at": now_iso()}},
        upsert=True)


async def _track_quest_progress(user_id: str, action: str, amount: int = 1):
    """Advance progress for every active quest whose objective matches
    `action` (daily/weekly/achievement)."""
    if amount <= 0:
        return
    quests = await db.quests.find({"active": True, "objective.type": action}, {"_id": 0}).to_list(300)
    for q in quests:
        await _bump_quest_progress(user_id, q, amount)


async def _drain_kill_credits():
    """Credit the kill_dino quest objective for PVP kills observed since the last
    poll (game_telemetry.GameTelemetry.kills_out). Natural deaths never reach that
    queue -- see GameTelemetry._process's RX_KILL handling. Called from
    population_telemetry_loop right after each game_tele.poll()."""
    kills = await asyncio.to_thread(game_tele.drain_kills)
    if not kills:
        return
    # Killers AND victims resolve in one query: the leaderboard credits the
    # killer a kill and the victim a death from the same observed event.
    sids = sorted({str(k.get(f) or "").strip() for k in kills for f in ("killer_sid", "victim_sid")
                   if str(k.get(f) or "").strip()})
    if not sids:
        return
    users = await db.users.find({"steam_id": {"$in": sids}}, {"_id": 0, "id": 1, "steam_id": 1}).to_list(len(sids))
    by_sid = {str(u.get("steam_id")): u["id"] for u in users if u.get("steam_id")}
    for k in kills:
        victim_id = by_sid.get(str(k.get("victim_sid") or ""))
        if victim_id:
            await _lb_bump(victim_id, deaths=1)
        user_id = by_sid.get(str(k.get("killer_sid") or ""))
        if user_id:
            await _lb_bump(user_id, kills=1)
            await _track_quest_progress(user_id, "kill_dino", 1)
            try:
                await battle_pass.hook_kill_xp(user_id, k.get("victim_species"),
                                               k.get("victim_growth"), k.get("killer_sid"),
                                               k.get("victim_sid"))
            except Exception as e:
                logger.warning("[bp] hook failed: %r", e)
    try:
        await battle_pass.periodic()
    except Exception as e:
        logger.warning("[bp] hook failed: %r", e)


# ---------- Leaderboards (Overall / Kills / Misiones / Tiempo, monthly) -----
# Pure decision logic lives in leaderboards.py (tests_local, no Mongo);
# everything here is the I/O half. Every hook is exception-contained: a
# leaderboard failure must never break a payout, a quest claim or the
# telemetry loop.

async def _lb_bump(user_id: str, *, kills: int = 0, deaths: int = 0,
                   quests: int = 0, playtime_seconds: int = 0):
    """Atomically add deltas to the caller's CURRENT-season row and recompute
    the composite score in the same update (pipeline update — no read-modify-
    write race). All-time counters ride on the user doc."""
    try:
        inc = {"kills_month": kills, "deaths_month": deaths,
               "quests_month": quests, "playtime_seconds_month": playtime_seconds}
        inc = {k: v for k, v in inc.items() if v}
        if not inc or not user_id:
            return
        sid = leaderboards.season_id()
        try:
            await db.leaderboard_stats.update_one(
                {"user_id": user_id, "season_id": sid},
                leaderboards.bump_pipeline(inc, new_id(), now_iso()), upsert=True)
        except DuplicateKeyError:
            # Two first-ever bumps raced the upsert; the loser retries onto the
            # row the winner just created (unique index guarantees it exists).
            await db.leaderboard_stats.update_one(
                {"user_id": user_id, "season_id": sid},
                leaderboards.bump_pipeline(inc, new_id(), now_iso()))
        allinc = {}
        if kills:
            allinc["lb_kills_all"] = kills
        if deaths:
            allinc["lb_deaths_all"] = deaths
        if quests:
            allinc["lb_quests_all"] = quests
        if playtime_seconds:
            allinc["lb_playtime_seconds_all"] = playtime_seconds
        if allinc:
            await db.users.update_one({"id": user_id}, {"$inc": allinc})
    except Exception as e:
        logger.warning(f"[lb] bump failed for {user_id}: {e}")


async def _lb_board_rows(kind: str, sid: str, limit: int):
    field = leaderboards.KIND_TO_FIELD[kind]
    return await db.leaderboard_stats.find(
        {"season_id": sid, field: {"$gt": 0}}, {"_id": 0}
    ).sort(leaderboards.board_sort(kind)).limit(limit).to_list(limit)


@api_router.get("/leaderboards")
async def leaderboards_hub():
    """Public hub: every board's top rows + season meta in ONE request.
    Signed-out sees everything; signing in only marks your own row (the
    /leaderboards/me call). Personas only — no SteamID64 on this wire."""
    sid = leaderboards.season_id()
    boards = {}
    all_uids = set()
    per_kind_rows = {}
    for kind in leaderboards.VALID_KINDS:
        rows = await _lb_board_rows(kind, sid, leaderboards.TOP_N)
        per_kind_rows[kind] = rows
        all_uids.update(r.get("user_id") for r in rows if r.get("user_id"))
    users = {}
    if all_uids:
        docs = await db.users.find(
            {"id": {"$in": list(all_uids)}},
            {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1,
             "lb_kills_all": 1, "lb_deaths_all": 1}).to_list(len(all_uids))
        users = {u["id"]: u for u in docs}
    for kind, rows in per_kind_rows.items():
        boards[kind] = [leaderboards.public_row(kind, r, users.get(r.get("user_id")), i + 1)
                        for i, r in enumerate(rows)]
    players_total = await db.leaderboard_stats.count_documents({"season_id": sid})
    return {
        "season_id": sid,
        "season_name": battle_pass.season_display_name(sid),
        "seconds_remaining": leaderboards.seconds_remaining(sid),
        "prizes": {str(k): v for k, v in leaderboards.PRIZE_TABLE.items()},
        # Cosmetic riders, keyed by the same rank strings as `prizes`. Name +
        # colour proximity only — no payload, no picture, safe on this public
        # (signed-out) wire.
        "prize_skins": leaderboards.prize_skin_cards(),
        "players_total": players_total,
        "boards": boards,
    }


@api_router.get("/leaderboards/me")
async def leaderboards_me(user=Depends(get_current_user)):
    """The signed-in viewer's row + exact rank per board (same tiebreak as the
    board sort, so the pinned rank always matches what the list would show)."""
    sid = leaderboards.season_id()
    row = await db.leaderboard_stats.find_one(
        {"user_id": user["id"], "season_id": sid}, {"_id": 0})
    out = {}
    for kind in leaderboards.VALID_KINDS:
        field = leaderboards.KIND_TO_FIELD[kind]
        val = int((row or {}).get(field) or 0)
        if val <= 0:
            out[kind] = None
            continue
        ahead = await db.leaderboard_stats.count_documents(
            leaderboards.rank_filter(kind, sid, val, user["id"]))
        out[kind] = leaderboards.public_row(kind, row, user, ahead + 1)
    return {"season_id": sid, "me": out}


async def _leaderboard_backfill_once():
    """One-shot seed so the boards read ALL players from day one instead of
    starting empty: measured playtime from this month's verified passive-payout
    transactions, misiones from this month's claimed quest_progress rows, and
    all-time quest totals. $max semantics ⇒ idempotent (a crash mid-run or a
    double start can never double-count); marker flips to done only at the end."""
    meta = await db.leaderboard_meta.find_one({"key": "backfill_v1"}, {"_id": 0})
    if meta and meta.get("status") == "done":
        return
    sid = leaderboards.season_id()
    start_iso = leaderboards.season_bounds(sid)[0].isoformat()
    # Verified playtime: sum the paid cycles out of the payout labels.
    secs_by_user: dict = {}
    cur = db.transactions.find(
        {"type": "reward", "created_at": {"$gte": start_iso},
         "description": {"$regex": "^PrimeMeat por tiempo de juego"}},
        {"_id": 0, "user_id": 1, "description": 1})
    async for tx in cur:
        c = leaderboards.playtime_tx_cycles(tx.get("description"))
        if c and tx.get("user_id"):
            secs_by_user[tx["user_id"]] = secs_by_user.get(tx["user_id"], 0) + c * PASSIVE_INTERVAL_SECONDS
    # Misiones claimed this month.
    quests_by_user: dict = {}
    cur = db.quest_progress.find(
        {"claimed": True, "claimed_at": {"$gte": start_iso}},
        {"_id": 0, "user_id": 1})
    async for p in cur:
        if p.get("user_id"):
            quests_by_user[p["user_id"]] = quests_by_user.get(p["user_id"], 0) + 1
    for uid in set(secs_by_user) | set(quests_by_user):
        seed = {"playtime_seconds_month": secs_by_user.get(uid, 0),
                "quests_month": quests_by_user.get(uid, 0)}
        try:
            await db.leaderboard_stats.update_one(
                {"user_id": uid, "season_id": sid},
                leaderboards.seed_pipeline(seed, new_id(), now_iso()), upsert=True)
        except DuplicateKeyError:
            await db.leaderboard_stats.update_one(
                {"user_id": uid, "season_id": sid},
                leaderboards.seed_pipeline(seed, new_id(), now_iso()))
    # All-time misiones (no date filter) — $max keeps live $inc'd values safe.
    all_quests: dict = {}
    cur = db.quest_progress.find({"claimed": True}, {"_id": 0, "user_id": 1})
    async for p in cur:
        if p.get("user_id"):
            all_quests[p["user_id"]] = all_quests.get(p["user_id"], 0) + 1
    for uid, n in all_quests.items():
        await db.users.update_one({"id": uid}, {"$max": {"lb_quests_all": n}})
    await db.leaderboard_meta.update_one(
        {"key": "backfill_v1"},
        {"$set": {"status": "done", "finished_at": now_iso()},
         "$setOnInsert": {"key": "backfill_v1"}}, upsert=True)
    logger.info(f"[lb] backfill done: {len(secs_by_user)} playtime users, "
                f"{len(quests_by_user)} quest users this season")


async def _leaderboard_rollover_tick():
    """Award last season's overall top 3 exactly once after the month flips.
    Receipt doc first ($setOnInsert claims it), then per-rank payment markers —
    a restart mid-payout resumes the unpaid ranks and can never pay twice."""
    sid = leaderboards.season_id()
    prev = leaderboards.previous_season_id(sid)
    meta = await db.leaderboard_meta.find_one({"key": "last_awarded_season"}, {"_id": 0})
    if not meta:
        # First boot: adopt the previous season as already-settled so a fresh
        # install never pays a season that predates the leaderboard.
        await db.leaderboard_meta.update_one(
            {"key": "last_awarded_season"},
            {"$setOnInsert": {"key": "last_awarded_season", "season_id": prev}}, upsert=True)
        return
    if meta.get("season_id") == prev:
        return  # nothing has finished since the last award
    rows = await _lb_board_rows("overall", prev, 3)
    plan = leaderboards.plan_awards(rows)
    receipt = await db.leaderboard_awards.find_one({"season_id": prev}, {"_id": 0})
    if receipt is None:
        await db.leaderboard_awards.update_one(
            {"season_id": prev},
            {"$setOnInsert": {"season_id": prev, "winners": plan,
                              "paid_ranks": [], "created_at": now_iso()}}, upsert=True)
        receipt = await db.leaderboard_awards.find_one({"season_id": prev}, {"_id": 0})
    for w in (receipt or {}).get("winners", []):
        # The claim below is atomic: only the writer that ADDS the rank pays it.
        claimed = await db.leaderboard_awards.find_one_and_update(
            {"season_id": prev, "paid_ranks": {"$ne": w["rank"]}},
            {"$addToSet": {"paid_ranks": w["rank"]}})
        if claimed:
            await db.users.update_one({"id": w["user_id"]}, {"$inc": {"coins": int(w["prize"])}})
            await add_transaction(w["user_id"], "normal", int(w["prize"]), "reward",
                                  leaderboards.award_tx_label(prev, w["rank"]))
            logger.info(f"[lb] season {prev} rank {w['rank']} paid {w['prize']} to {w['user_id']}")
        # The cosmetic rider is claimed SEPARATELY (2026-08-16). Two markers, not
        # one: if the coins land and the grant then throws, the next tick must be
        # able to finish the skin WITHOUT re-paying the money — and vice versa.
        # A receipt written before this build carries no "skin" key at all; .get
        # keeps those seasons paying exactly what they always did.
        skin_id = w.get("skin") or leaderboards.PRIZE_SKIN_BY_RANK.get(w["rank"])
        if not skin_id:
            continue
        skin_claimed = await db.leaderboard_awards.find_one_and_update(
            {"season_id": prev, "paid_skin_ranks": {"$ne": w["rank"]}},
            {"$addToSet": {"paid_skin_ranks": w["rank"]}})
        if not skin_claimed:
            continue
        try:
            await _grant_prize_skin(
                w["user_id"], skin_id,
                leaderboards.award_skin_source(prev, w["rank"]))
        except Exception:
            # Hand the claim back so the next tick retries — a swallowed grant
            # would leave the champion permanently short of the prize he won.
            await db.leaderboard_awards.update_one(
                {"season_id": prev}, {"$pull": {"paid_skin_ranks": w["rank"]}})
            logger.exception(f"[lb] season {prev} rank {w['rank']} skin grant failed")
            continue
        logger.info(f"[lb] season {prev} rank {w['rank']} granted skin "
                    f"{skin_id} to {w['user_id']}")
    await db.leaderboard_meta.update_one(
        {"key": "last_awarded_season"}, {"$set": {"season_id": prev}}, upsert=True)


async def leaderboard_maintenance_loop():
    """Backfill once, then watch for season rollover. Guarded like every other
    background loop — one bad tick never kills it."""
    try:
        await _leaderboard_backfill_once()
    except Exception as e:
        logger.warning(f"[lb] backfill: {e}")
    while True:
        try:
            await _leaderboard_rollover_tick()
        except Exception as e:
            logger.warning(f"[lb] rollover: {e}")
        await asyncio.sleep(300)


async def _visit_poi_tracker_tick():
    """One pass of the visit_location quest tracker: read players_positions.json,
    resolve each row to the nearest named POI (quest_pois.py), and credit every
    active visit_location quest whose period hasn't already seen that POI. Pure
    decision logic lives in quest_pois.py (nearest_poi/should_credit_visit/
    quest_matches_poi) so it is exercised by backend/tests_local without Mongo."""
    positions = await asyncio.to_thread(game_ipc.read_players_positions_fresh)
    if not isinstance(positions, dict):
        return
    sid_xy: dict = {}
    for k, v in positions.items():
        if not isinstance(v, dict):
            continue
        sid = str(v.get("steamid") or v.get("steam_id") or k or "").strip()
        if not sid:
            continue
        try:
            x = float(v.get("x"))
            y = float(v.get("y"))
        except (TypeError, ValueError):
            continue
        if x != x or y != y:  # NaN guard
            continue
        sid_xy[sid] = (x, y)
    if not sid_xy:
        return
    users = await db.users.find({"steam_id": {"$in": list(sid_xy.keys())}}, {"_id": 0, "id": 1, "steam_id": 1}).to_list(len(sid_xy))
    if not users:
        return
    quests = await db.quests.find({"active": True, "objective.type": "visit_location"}, {"_id": 0}).to_list(300)
    if not quests:
        return
    day_key = _quest_period_key("daily")
    week_key = _quest_period_key("weekly")
    for u in users:
        sid = str(u.get("steam_id") or "")
        pos = sid_xy.get(sid)
        if not pos:
            continue
        # Liveness gate: only credit a player the mod currently reports as ONLINE
        # in a fresh players.json (read_player_status == "present"). This closes
        # the farm where a stale/lingering positions row would keep crediting an
        # offline player -- players.json carries the mod's authoritative
        # last_updated freshness window.
        status, _live_row = await asyncio.to_thread(game_ipc.read_player_status, sid)
        if status != "present":
            continue
        poi = quest_pois.nearest_poi(pos[0], pos[1])
        if not poi:
            continue
        user_id = u["id"]
        already_today = await db.quest_visits.find_one({"user_id": user_id, "poi": poi, "day_key": day_key}, {"_id": 0})
        if already_today:
            continue  # nothing new this tick -- already bookkept today for this POI
        already_this_week = await db.quest_visits.find_one({"user_id": user_id, "poi": poi, "week_key": week_key}, {"_id": 0})
        await db.quest_visits.insert_one({"user_id": user_id, "poi": poi, "day_key": day_key,
                                          "week_key": week_key, "created_at": now_iso()})
        for q in quests:
            if not quest_pois.quest_matches_poi(q.get("objective") or {}, poi):
                continue
            if quest_pois.should_credit_visit(already_today=False, already_this_week=bool(already_this_week),
                                              quest_category=q.get("category", "daily")):
                await _track_quest_progress(user_id, "visit_location", 1)


async def visit_poi_tracker_loop():
    """Background visit_location quest tracker, polling players_positions.json
    every 45s. Guarded like the other background loops -- one bad tick (missing
    file, transient DB hiccup) never kills the loop."""
    while True:
        try:
            await _visit_poi_tracker_tick()
        except Exception as e:
            logger.warning(f"visit POI tracker: {e}")
        await asyncio.sleep(45)


# ---------- Multiplier Events (species-targeted PrimeMeat earning boosts) ----
# Admin publishes "species + duration + multiplier"; while the event is active,
# every verified passive PrimeMeat payout for a player CURRENTLY playing that
# species is multiplied inside _credit_playtime's existing CAS-guarded write.
# Expiry is computed from ends_at at every read — no background loop to fail.
MULT_EVENTS_CACHE_SECONDS = 15
_mult_events_cache = {"ts": 0.0, "events": []}


async def _recent_multiplier_events(limit: int = 50) -> list:
    """Newest-first multiplier events (any status). Small collection by design."""
    return await db.multiplier_events.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)


async def _active_multiplier_events() -> list:
    """Events currently boosting, via a small in-proc cache so the per-user
    passive tick (every ~20s per open tab) never hammers Mongo. A fresh event
    starts boosting at worst MULT_EVENTS_CACHE_SECONDS late — far inside the
    240s payout interval."""
    import time as _t
    now = _t.time()
    if now - _mult_events_cache["ts"] > MULT_EVENTS_CACHE_SECONDS:
        try:
            _mult_events_cache["events"] = await _recent_multiplier_events(20)
            _mult_events_cache["ts"] = now
        except Exception as e:
            logger.warning(f"[multx] active events read failed: {e}")
            return []
    return [ev for ev in _mult_events_cache["events"]
            if quest_events.event_status(ev) == "active"]


def _invalidate_mult_events_cache():
    _mult_events_cache["ts"] = 0.0


async def _current_player_species(user) -> str:
    """The user's CURRENT in-game species from the mod's players.json ("" when
    offline/stale/unknown — the boost lane fails closed, base pay unaffected)."""
    sid = str((user or {}).get("steam_id") or "").strip()
    if not sid:
        return ""
    try:
        status, row = await asyncio.to_thread(game_ipc.read_player_status, sid)
    except Exception:
        return ""
    if status != "present" or not isinstance(row, dict):
        return ""
    return quest_events.normalize_species(row.get("dino") or row.get("dino_class"))


async def _playtime_boost(user):
    """(multiplier, event) to apply to this payout — (1, None) when no active
    event covers the player's current species."""
    events = await _active_multiplier_events()
    if not events:
        return 1, None
    species = await _current_player_species(user)
    return quest_events.pick_multiplier(events, species)


def _mult_event_view(ev: dict) -> dict:
    """Player/admin-safe view row with live countdown fields."""
    row = {k: ev.get(k) for k in ("id", "title", "species", "multiplier",
                                  "starts_at", "ends_at", "created_at")}
    row["event"] = quest_events.event_times(ev)
    return row


async def _resolve_quest_view(user_id: str, quests: list) -> list:
    by_id = {q["id"]: q for q in quests}
    # claimed set for prerequisites (current period per prereq category)
    out = []
    for q in quests:
        prog = await db.quest_progress.find_one(
            {"user_id": user_id, "quest_id": q["id"], "period_key": _quest_pk(q)}, {"_id": 0})
        progress = prog.get("progress", 0) if prog else 0
        claimed = bool(prog and prog.get("claimed"))
        target = int(q.get("objective", {}).get("target", 1))
        locked, requires_title = False, None
        req_id = q.get("requires")
        if req_id and req_id in by_id:
            req = by_id[req_id]
            requires_title = req["title"]
            rprog = await db.quest_progress.find_one(
                {"user_id": user_id, "quest_id": req_id, "period_key": _quest_pk(req)}, {"_id": 0})
            locked = not (rprog and rprog.get("claimed"))
        row = {**q, "progress": progress, "target": target,
               "completed": progress >= target, "claimed": claimed,
               "locked": locked, "requires_title": requires_title}
        out.append(row)
    return out


@api_router.get("/quests")
async def list_quests(user=Depends(get_current_user)):
    quests = await db.quests.find({"active": True, "category": {"$in": quest_data.QUEST_CATEGORIES}},
                                  {"_id": 0}).sort("created_at", 1).to_list(300)
    view = await _resolve_quest_view(user["id"], quests)
    counts = {"daily": 0, "weekly": 0, "achievement": 0}
    for q in view:
        counts[q.get("category", "daily")] = counts.get(q.get("category", "daily"), 0) + 1
    # Multiplier events ride the same payload: upcoming/active render with live
    # countdowns; expired ones disappear on their own (status computed per read).
    mult_events = [_mult_event_view(ev) for ev in await _recent_multiplier_events(20)
                   if quest_events.event_status(ev) in ("upcoming", "active")]
    counts["event"] = len(mult_events)
    return {"quests": view, "counts": counts, "resets": _quest_reset_seconds(),
            "multiplier_events": mult_events,
            "egg_names": {t: cosmetics_data.EGGS[t]["name"] for t in cosmetics_data.EGG_TIERS}}


@api_router.post("/quests/track")
async def track_quest(user=Depends(get_current_user)):
    # Retired 2026-07-16: this accepted an arbitrary user-chosen amount, letting
    # any signed-in player complete every quest instantly. All progress is now
    # credited server-side only: kill telemetry (_drain_kill_credits), the POI
    # visit tracker (_visit_poi_tracker_tick) and the verified passive play tick
    # (_credit_playtime). No frontend caller existed.
    raise HTTPException(status_code=410, detail=(
        "El registro manual de progreso de misiones está deshabilitado; "
        "el progreso se acredita automáticamente mientras juegas en el servidor."))


@api_router.post("/quests/{quest_id}/claim")
async def claim_quest(quest_id: str, user=Depends(get_current_user)):
    q = await db.quests.find_one({"id": quest_id, "active": True,
                                  "category": {"$in": quest_data.QUEST_CATEGORIES}}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Quest no disponible")
    pk = _quest_pk(q)
    prog = await db.quest_progress.find_one(
        {"user_id": user["id"], "quest_id": quest_id, "period_key": pk}, {"_id": 0})
    if prog and prog.get("claimed"):
        raise HTTPException(status_code=400, detail="Ya reclamaste esta quest")
    # prerequisite gate
    req_id = q.get("requires")
    if req_id:
        req = await db.quests.find_one({"id": req_id}, {"_id": 0})
        if req:
            rprog = await db.quest_progress.find_one(
                {"user_id": user["id"], "quest_id": req_id, "period_key": _quest_pk(req)}, {"_id": 0})
            if not (rprog and rprog.get("claimed")):
                raise HTTPException(status_code=400, detail="Completa primero la quest requerida")
    target = int(q.get("objective", {}).get("target", 1))
    if (prog.get("progress", 0) if prog else 0) < target:
        raise HTTPException(status_code=400, detail="Objetivo aún no completado")
    # CLAIM THE QUEST BEFORE PAYING IT. Reading `claimed` and only writing it after
    # the reward means several claims fired at once all read "not claimed" and all
    # pay -- coins, Amberium and the egg, once per request.
    if not prog:
        await db.quest_progress.update_one(
            {"user_id": user["id"], "quest_id": quest_id, "period_key": pk},
            {"$setOnInsert": {"id": new_id(), "user_id": user["id"], "quest_id": quest_id,
                              "period_key": pk, "progress": target, "claimed": False,
                              "created_at": now_iso()}}, upsert=True)
    claimed_now = await db.quest_progress.find_one_and_update(
        {"user_id": user["id"], "quest_id": quest_id, "period_key": pk, "claimed": {"$ne": True}},
        {"$set": {"claimed": True, "claimed_at": now_iso(), "progress": target}},
        return_document=ReturnDocument.AFTER)
    if not claimed_now:
        raise HTTPException(status_code=400, detail="Ya reclamaste esta quest")
    inc = {}
    if q.get("coins"):
        inc["coins"] = q["coins"]
    if q.get("vip"):
        inc["vip_coins"] = q["vip"]
    if q.get("xp"):
        inc["xp"] = q["xp"]
    if inc:
        await db.users.update_one({"id": user["id"]}, {"$inc": inc})
    label = f"Quest: {q['title']}"
    if q.get("coins"):
        await add_transaction(user["id"], "normal", q["coins"], "reward", label)
    if q.get("vip"):
        await add_transaction(user["id"], "vip", q["vip"], "reward", label)
    if q.get("egg") in cosmetics_data.EGGS:
        await _grant_egg(user["id"], q["egg"])
    try:
        await battle_pass.hook_quest_xp(user["id"], q.get("rarity"))
    except Exception as e:
        logger.warning("[bp] hook failed: %r", e)
    # Leaderboard: one successful claim = one mision (claimed_now above already
    # lost any duplicate race, so a replayed claim can never bump twice).
    await _lb_bump(user["id"], quests=1)
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {"success": True,
            "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"], "xp": fresh.get("xp", 0)}}


@api_router.get("/admin/multiplier-events")
async def admin_list_multiplier_events(admin=Depends(get_admin_user)):
    events = [_mult_event_view(ev) for ev in await _recent_multiplier_events()]
    return {"events": events,
            "species": quest_data.EVENT_SPECIES,
            "duration_presets": quest_data.EVENT_DURATION_PRESETS_H,
            "max_hours": quest_data.EVENT_MAX_HOURS,
            "defaults": {"duration_hours": quest_data.MULT_EVENT_DEFAULT_HOURS,
                         "multiplier": quest_data.MULT_EVENT_DEFAULT},
            "multiplier_min": quest_data.MULT_EVENT_MIN,
            "multiplier_max": quest_data.MULT_EVENT_MAX,
            "base_reward": PASSIVE_REWARD,
            "interval_seconds": PASSIVE_INTERVAL_SECONDS,
            "announce_available": event_feed.enabled()}


@api_router.post("/admin/multiplier-events")
async def admin_create_multiplier_event(data: MultiplierEventInput, admin=Depends(get_admin_user)):
    species = quest_events.normalize_species(data.species)
    if not species:
        raise HTTPException(status_code=400, detail=f"Especie desconocida: {data.species}")
    clamped = quest_events.validate_multiplier_fields(data.duration_hours, data.multiplier)
    starts = datetime.now(timezone.utc)
    ends = starts + timedelta(hours=clamped["duration_hours"])
    ev = {"id": new_id(), "title": f"Día de {species}", "species": species,
          "multiplier": clamped["multiplier"],
          "starts_at": starts.isoformat(), "ends_at": ends.isoformat(),
          "created_at": now_iso(), "created_by": admin.get("persona_name") or ""}
    await db.multiplier_events.insert_one(ev)
    _invalidate_mult_events_cache()
    ev.pop("_id", None)
    await add_log(admin["persona_name"], "create_multiplier_event", ev["id"],
                  {"species": species, "multiplier": clamped["multiplier"],
                   "duration_hours": clamped["duration_hours"]})
    logger.info(f"[multx] published '{ev['title']}' x{clamped['multiplier']} "
                f"for {clamped['duration_hours']}h by {admin.get('persona_name')}")
    event_feed.fire_event_published(ev, clamped["duration_hours"])
    return _mult_event_view(ev)


@api_router.patch("/admin/multiplier-events/{event_id}/end")
async def admin_end_multiplier_event(event_id: str, admin=Depends(get_admin_user)):
    """End a running event NOW (the boost stops within the cache window)."""
    ev = await db.multiplier_events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    if quest_events.event_status(ev) != "active":
        raise HTTPException(status_code=400, detail="Este evento ya terminó")
    # The new end must land strictly AFTER the start or the window turns
    # malformed (starts >= ends -> status "" -> invisible). Same-clock-tick
    # end-early is real on Windows' ~15ms timer.
    starts, _ends = quest_events.event_window(ev)
    end_dt = datetime.now(timezone.utc)
    if starts and end_dt <= starts:
        end_dt = starts + timedelta(seconds=1)
    await db.multiplier_events.update_one({"id": event_id}, {"$set": {"ends_at": end_dt.isoformat()}})
    _invalidate_mult_events_cache()
    await add_log(admin["persona_name"], "end_multiplier_event", event_id, {"title": ev.get("title")})
    logger.info(f"[multx] ended early '{ev.get('title')}' by {admin.get('persona_name')}")
    return {"ok": True, "ended_at": end_dt.isoformat()}


@api_router.delete("/admin/multiplier-events/{event_id}")
async def admin_delete_multiplier_event(event_id: str, admin=Depends(get_admin_user)):
    """Remove an event from the list entirely (running ones stop boosting too)."""
    res = await db.multiplier_events.delete_one({"id": event_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    _invalidate_mult_events_cache()
    await add_log(admin["persona_name"], "delete_multiplier_event", event_id, {})
    logger.info(f"[multx] deleted event {event_id} by {admin.get('persona_name')}")
    return {"ok": True}


# ---------- Account standing / strikes (moderation — RCON/Discord API ready) ----------
# Strikes accumulate; each threshold escalates the ban until permanent.
STRIKE_LADDER = [
    {"threshold": 2, "label": "1 hour ban", "seconds": 3600},
    {"threshold": 3, "label": "24 hour ban", "seconds": 86400},
    {"threshold": 4, "label": "7 day ban", "seconds": 604800},
    {"threshold": 5, "label": "Permanent ban", "seconds": None},
]


class StrikeInput(BaseModel):
    reason: str = "Rule violation"
    # Strikes stay active until an admin removes them or unbans — NO per-strike auto
    # expiry (it could never be reconciled: a lapsing strike would leave a stale DB ban
    # flag + orphan native ban that the enforcer keeps enforcing). Admin-managed only.


def _ladder_rung_for(count: int):
    """Highest strike-ladder rung whose threshold is met (None below the first ban
    threshold, i.e. a single strike = warning + kick with no ban)."""
    applicable = None
    for item in STRIKE_LADDER:
        if count >= item["threshold"]:
            applicable = item
    return applicable


async def _active_strikes(user_id: str):
    now = datetime.now(timezone.utc)
    strikes = await db.strikes.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    active = [s for s in strikes if s.get("active") and (not s.get("expires_at") or datetime.fromisoformat(s["expires_at"]) > now)]
    return strikes, active


def _fold_manual_ban(user: dict | None, update: dict) -> dict:
    """Fold a direct (non-ladder) ban — `manual_ban` on the user doc, written by the
    Discord bot's /ban — into a ladder-derived ban-field update, keeping the LONGER of
    the two. Without this, any strike add/remove recompute would overwrite the flag
    pair and silently lift a manual ban. A lapsed or unreadable manual entry carries
    no weight (ladder wins; never guess a duration)."""
    mb = (user or {}).get("manual_ban") or None
    if not mb:
        return update
    if mb.get("permanent"):
        return {"ban_permanent": True, "banned_until": None}
    try:
        m_until = datetime.fromisoformat(str(mb.get("until")))
    except (TypeError, ValueError):
        return update
    if m_until <= datetime.now(timezone.utc):
        return update
    if update.get("ban_permanent"):
        return update
    try:
        l_until = datetime.fromisoformat(update["banned_until"]) if update.get("banned_until") else None
    except (TypeError, ValueError):
        l_until = None
    if l_until is None or m_until > l_until:
        return {"ban_permanent": False, "banned_until": m_until.isoformat()}
    return update


async def _recompute_ban(user_id: str):
    _, active = await _active_strikes(user_id)
    count = len(active)
    applicable = _ladder_rung_for(count)
    if not applicable:
        update = {"ban_permanent": False, "banned_until": None}
    elif applicable["seconds"] is None:
        update = {"ban_permanent": True, "banned_until": None}
    else:
        update = {"ban_permanent": False,
                  "banned_until": (datetime.now(timezone.utc) + timedelta(seconds=applicable["seconds"])).isoformat()}
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "manual_ban": 1})
    update = _fold_manual_ban(u, update)
    await db.users.update_one({"id": user_id}, {"$set": update})
    return count


async def _enforce_strike(target: dict, count: int, reason: str, admin: dict) -> dict:
    """Apply the in-game consequence of a strike and report what happened for the UI.

    Ladder: strike 1 (below the first threshold) => warning + kick, no ban.
    Strikes >=2 => a durable native ban for the ladder's duration (auto-expiring via
    PlayerBans.json endBanTime) + a best-effort RCON ban (in-memory) + a kick to force
    the live disconnect. Never raises — the strike is already recorded; enforcement is
    additive and any failure is surfaced in `notes`, not thrown."""
    sid = str(target.get("steam_id") or "").strip()
    rung = _ladder_rung_for(count)
    res = {
        "steam_id": sid,
        "rcon_configured": rcon_client.is_configured(),
        "online": False,
        "kicked": False,
        "kick_dispatched": False,
        "banned": False,
        "action": "ban" if rung else "kick",
        "ban_label": rung["label"] if rung else None,
        "ban_permanent": bool(rung and rung["seconds"] is None),
        "ban_hours": (None if not rung or rung["seconds"] is None else rung["seconds"] // 3600),
        "notes": [],
    }
    if not sid:
        res["notes"].append("no_steam_id")
        return res
    try:
        ids, _ = await _rcon_online_players()
        res["online"] = sid in ids
    except Exception:
        pass
    # Durable native ban first (the only thing that blocks reconnection for the
    # duration), then the best-effort RCON ban, then the kick. Native file IO is
    # blocking + can sleep-retry under a game lock, so it runs off the event loop.
    if rung:
        hours = 0 if rung["seconds"] is None else rung["seconds"] // 3600
        added = await asyncio.to_thread(
            native_bans.add_ban, sid, reason, hours, target.get("persona_name"),
            admin.get("persona_name") or "La Isla Nublar", admin.get("steam_id") or "")
        if added:
            res["banned"] = True
        else:
            res["notes"].append("native_ban_unavailable")
        if rcon_client.is_configured():
            try:
                await rcon_client.ban(sid)
            except Exception as e:
                res["notes"].append(f"rcon_ban_error:{type(e).__name__}")
    if rcon_client.is_configured():
        try:
            await rcon_client.kick(sid)
            # NOT res["kicked"]. Evrima's RCON kick acknowledges and leaves the player
            # connected (fleet-proven, and re-proven on this box 2026-07-29: 394 acked
            # kick lines against a player who never left). Claiming the kick here is
            # what put "kicked": true on two Registros rows for players still in game.
            res["notes"].append("rcon_kick_sent")
        except Exception as e:
            res["notes"].append(f"rcon_kick_error:{type(e).__name__}")
    else:
        res["notes"].append("rcon_not_configured")
    # Evrima's RCON kick ACKS but does not remove a live player (fleet-proven) — the
    # kick that works is the mod's ban_commands lane (controller menu-return). Fire it
    # for every enforcement; the pending sweep then VERIFIES the player is gone.
    try:
        await _mod_kick(sid, reason, target.get("persona_name") or "",
                        admin.get("steam_id") or "")
        res["kick_dispatched"] = True
        res["notes"].append("mod_kick_dispatched")
    except Exception as e:
        res["notes"].append(f"mod_kick_error:{type(e).__name__}")
    # Tier-1 always arms the verified pending kick: online targets are re-kicked via
    # the mod lane until a fresh player list shows them GONE (the RCON ack lies both
    # ways); offline targets get it the moment they next spawn. Tier 2+ normally needs
    # no flag — the enforcer re-kicks everyone inside an active ban window off the
    # NATIVE file and the mod's BanSpawnGuard rejects banned spawns from
    # PlayerBans.json — but when the native write FAILED the file carries nothing to
    # enforce, so the verified kick arms as the bridge until the ~5-min self-heal.
    if not rung or not res["banned"]:
        try:
            await db.users.update_one({"id": target["id"]}, {"$set": {"pending_kick": {
                "reason": reason, "by": admin.get("persona_name") or "La Isla Nublar",
                "by_sid": admin.get("steam_id") or "",
                "name": target.get("persona_name") or "",
                "at": now_iso(), "attempts": 0}}})
            res["notes"].append("pending_kick_armed")
        except Exception as e:
            res["notes"].append(f"pending_kick_error:{type(e).__name__}")
    return res


async def _compute_standing(user: dict):
    _, active = await _active_strikes(user["id"])
    count = len(active)
    now = datetime.now(timezone.utc)
    ban_permanent = bool(user.get("ban_permanent"))
    banned_until = user.get("banned_until")
    is_banned = ban_permanent or bool(banned_until and datetime.fromisoformat(banned_until) > now)
    nxt = next((it for it in STRIKE_LADDER if it["threshold"] > count), STRIKE_LADDER[-1])
    if ban_permanent:
        status, label = "banned", "Permanently banned"
    elif is_banned:
        status, label = "suspended", "Suspended"
    elif count == 0:
        status, label = "good", "Good standing"
    else:
        status, label = "at_risk", "At risk"
    return {
        "active_strikes": count, "next_threshold": nxt["threshold"], "next_penalty": nxt["label"],
        "status": status, "status_label": label,
        "banned": is_banned, "ban_permanent": ban_permanent,
        "banned_until": banned_until if is_banned and not ban_permanent else None,
        "ladder": STRIKE_LADDER,
    }


@api_router.get("/profile/standing")
async def profile_standing(user=Depends(get_current_user)):
    all_strikes, _ = await _active_strikes(user["id"])
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or user
    return {"standing": await _compute_standing(fresh), "strikes": all_strikes}


async def _issue_strike_and_enforce(target: dict, raw_reason: str, actor: dict, idem: str = "") -> dict:
    """The one strike path, shared verbatim by the admin panel endpoint and the
    Discord bot's internal endpoint: record, recompute the ladder, enforce in game,
    audit-log, public feed, return {standing, strike, enforcement}. `actor` needs
    persona_name (audit + feed) and steam_id (the mod kick RPC prefers the issuing
    admin's controller); web admins pass their user doc, the bot a pseudo-actor
    carrying discord_id — the immutable audit identity a display name is not."""
    user_id = target["id"]
    reason = (raw_reason or "").strip() or "Rule violation"
    reason = "".join(ch for ch in reason if ch >= " " or ch == "\n")[:256]
    strike = {"id": new_id(), "user_id": user_id, "reason": reason,
              "issued_by": actor["persona_name"], "issued_by_id": actor.get("discord_id") or None,
              "active": True, "expires_at": None, "created_at": now_iso()}
    if idem:
        strike["idem"] = idem
    await db.strikes.insert_one(strike)
    await db.users.update_one({"id": user_id}, {"$unset": {"native_unban_pending": ""}})
    count = await _recompute_ban(user_id)
    enforcement = await _enforce_strike(target, count, reason, actor)
    await add_log(actor["persona_name"], "add_strike", target.get("persona_name"),
                  {"reason": reason, "count": count, "action": enforcement.get("action"),
                   "kicked": enforcement.get("kicked"),
                   "kick_dispatched": enforcement.get("kick_dispatched"),
                   "banned": enforcement.get("banned"),
                   "discord_id": actor.get("discord_id") or None})
    # Public sanctions channel: names the player and the consequence, never the staff.
    strike_feed.fire_strike_posted(
        persona=target.get("persona_name"), count=count,
        action=enforcement.get("action"), ban_permanent=enforcement.get("ban_permanent"),
        ban_hours=enforcement.get("ban_hours"), reason=reason, strike_id=strike["id"])
    fresh = await db.users.find_one({"id": user_id}, {"_id": 0})
    strike.pop("_id", None)
    return {"standing": await _compute_standing(fresh), "strike": strike, "enforcement": enforcement}


@api_router.post("/admin/users/{user_id}/strike")
async def admin_add_strike(user_id: str, data: StrikeInput, admin=Depends(get_admin_user)):
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # Anyone — the owner included — can be sanctioned, with full in-game enforcement.
    # The one hard line left: nobody sanctions themselves. The owner alone may lift
    # sanctions off their own account (remove_strike/unban bypass) so a rogue admin
    # cannot permanently lock the owner out of their own server.
    if target.get("id") == admin.get("id"):
        raise HTTPException(status_code=403, detail="No puedes sancionarte a ti mismo")
    return await _issue_strike_and_enforce(target, data.reason, admin)


@api_router.delete("/admin/strikes/{strike_id}")
async def admin_remove_strike(strike_id: str, admin=Depends(get_admin_user)):
    s = await db.strikes.find_one({"id": strike_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Strike no encontrado")
    # A sanctioned staffer still holds panel access — without this, striking staff is
    # toothless (they would erase their own record). Only the owner bypasses it.
    if s.get("user_id") == admin.get("id") and not _is_owner(admin):
        raise HTTPException(status_code=403, detail="No puedes retirar tus propias sanciones")
    await db.strikes.update_one({"id": strike_id}, {"$set": {"active": False, "removed_by": admin["persona_name"], "removed_at": now_iso()}})
    # Mercy also disarms a not-yet-applied tier-1 kick.
    await db.users.update_one({"id": s["user_id"]}, {"$unset": {"pending_kick": ""}})
    # De-escalate — but a leniency action must NEVER extend an active ban, so clamp the
    # new end to the SHORTER of (current end, new tier from now). We recompute the ban
    # here (not via _recompute_ban, which always resets the clock — correct for adding a
    # strike, wrong for removing one).
    u = await db.users.find_one({"id": s["user_id"]}, {"_id": 0}) or {}
    _, active = await _active_strikes(s["user_id"])
    count = len(active)
    rung = _ladder_rung_for(count)
    now = datetime.now(timezone.utc)
    sid = str(u.get("steam_id") or "").strip()
    reason = s.get("reason") or "Rule violation"
    banner = admin.get("persona_name") or "La Isla Nublar"
    _FAR = now + timedelta(days=36500)  # comparison sentinel for a permanent ban
    cur_cmp = _FAR if u.get("ban_permanent") else (
        datetime.fromisoformat(u["banned_until"]) if u.get("banned_until") else now)
    if rung is None:
        # Removing the last ban-tier strike clears the LADDER ban only — a direct
        # /ban (manual_ban) is its own sanction and must survive strike mercy.
        folded = _fold_manual_ban(u, {"ban_permanent": False, "banned_until": None})
        await db.users.update_one({"id": s["user_id"]}, {"$set": folded})
        if sid:
            if folded.get("ban_permanent") or folded.get("banned_until"):
                hrs = 0 if folded.get("ban_permanent") else max(1, math.ceil(
                    (datetime.fromisoformat(folded["banned_until"]) - now).total_seconds() / 3600))
                mb = u.get("manual_ban") or {}
                await asyncio.to_thread(native_bans.add_ban, sid, mb.get("reason") or reason, hrs,
                                        u.get("persona_name"), mb.get("by") or banner, "")
            else:
                await asyncio.to_thread(native_bans.remove_ban, sid)
    else:
        tgt_perm = rung["seconds"] is None
        # The de-escalated tier can never undercut an active manual_ban: fold first,
        # then apply only if the folded target is genuinely shorter than today.
        folded = _fold_manual_ban(u, {
            "ban_permanent": tgt_perm, "banned_until": None if tgt_perm else (now + timedelta(seconds=rung["seconds"])).isoformat()})
        tgt_perm = bool(folded.get("ban_permanent"))
        tgt_cmp = _FAR if tgt_perm else datetime.fromisoformat(folded["banned_until"])
        if tgt_cmp < cur_cmp:  # new tier genuinely shorter -> apply it; else leave (never extend)
            await db.users.update_one({"id": s["user_id"]}, {"$set": folded})
            if sid:
                hrs = 0 if tgt_perm else max(1, math.ceil((tgt_cmp - now).total_seconds() / 3600))
                await asyncio.to_thread(native_bans.add_ban, sid, reason, hrs, u.get("persona_name"), banner, admin.get("steam_id") or "")
    await add_log(admin["persona_name"], "remove_strike", s["user_id"], {"strike_id": strike_id, "count": count})
    strike_feed.fire_strike_removed(persona=u.get("persona_name"), remaining=count)
    fresh = await db.users.find_one({"id": s["user_id"]}, {"_id": 0})
    return {"standing": await _compute_standing(fresh)}


@api_router.post("/admin/users/{user_id}/unban")
async def admin_unban(user_id: str, admin=Depends(get_admin_user)):
    if user_id == admin.get("id") and not _is_owner(admin):
        raise HTTPException(status_code=403, detail="No puedes levantar tus propias sanciones")
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    # Unban is the full clear: ladder flags, a Discord-lane manual_ban, and the
    # not-yet-applied tier-1 kick all lift together.
    await db.users.update_one({"id": user_id}, {"$set": {"ban_permanent": False, "banned_until": None},
                                                 "$unset": {"pending_kick": "", "manual_ban": ""}})
    await db.strikes.update_many({"user_id": user_id, "active": True},
                                 {"$set": {"active": False, "removed_by": admin["persona_name"], "removed_at": now_iso()}})
    # Lift the in-game ban (remove from the native PlayerBans.json).
    native_removed = False
    if target:
        sid = str(target.get("steam_id") or "").strip()
        if sid:
            native_removed = await asyncio.to_thread(native_bans.remove_ban, sid)
            if native_removed:
                await db.users.update_one({"id": user_id}, {"$unset": {"native_unban_pending": ""}})
            else:
                # File locked/unreadable — the enforcer retries so the in-game ban
                # actually lifts instead of silently staying forever.
                await db.users.update_one({"id": user_id}, {"$set": {"native_unban_pending": sid}})
            # A raw-sid kick armed from Discord before this player linked an account
            # must not keep re-firing after a web unban — same clear as the bot lane.
            await db.manual_kicks.delete_one({"steam_id": sid})
    await add_log(admin["persona_name"], "unban", user_id, {"native_removed": native_removed})
    fresh = await db.users.find_one({"id": user_id}, {"_id": 0})
    return {"standing": await _compute_standing(fresh), "native_removed": native_removed}


@api_router.get("/admin/users/{user_id}/standing")
async def admin_user_standing(user_id: str, admin=Depends(get_admin_user)):
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    all_strikes, _ = await _active_strikes(user_id)
    try:
        online = await _is_user_in_game(target)
    except Exception:
        online = False
    return {
        "user": {"id": target["id"], "persona_name": target.get("persona_name"),
                 "avatar": target.get("avatar"), "steam_id": target.get("steam_id"),
                 "staff_rank": target.get("staff_rank"), "staff_meta": staff_meta(target.get("staff_rank"))},
        "standing": await _compute_standing(target),
        "strikes": all_strikes,
        "online": online,
    }


@api_router.get("/admin/moderation")
async def admin_moderation(admin=Depends(get_admin_user)):
    """Overview for the admin Sanciones tab: live server status + every user who is
    currently flagged (any active strike or an active ban), most-severe first."""
    server = {"online": False, "players": 0, "max_players": 0}
    if rcon_client.is_configured():
        try:
            d = await asyncio.wait_for(rcon_client.server_details(), timeout=2.5)
            server = {"online": True, "players": d.get("players", 0), "max_players": d.get("max_players", 0)}
        except Exception:
            pass
    try:
        online_ids, _ = await _rcon_online_players()
    except Exception:
        online_ids = set()

    # Candidate set: users with an active ban flag OR at least one active strike.
    users_by_id = {}
    async for u in db.users.find({"$or": [{"ban_permanent": True}, {"banned_until": {"$ne": None}}]}, {"_id": 0}):
        users_by_id[u["id"]] = u
    for uid in await db.strikes.distinct("user_id", {"active": True}):
        if uid not in users_by_id:
            u = await db.users.find_one({"id": uid}, {"_id": 0})
            if u:
                users_by_id[uid] = u

    flagged = []
    for u in users_by_id.values():
        try:
            st = await _compute_standing(u)
        except Exception:
            continue  # a single malformed record must never blank the whole tab
        if st["active_strikes"] == 0 and not st["banned"]:
            continue  # ban lapsed and no active strikes -> no longer flagged
        sid = str(u.get("steam_id") or "").strip()
        flagged.append({
            "id": u["id"], "persona_name": u.get("persona_name"), "avatar": u.get("avatar"),
            "steam_id": sid, "staff_rank": u.get("staff_rank"), "staff_meta": staff_meta(u.get("staff_rank")),
            "active_strikes": st["active_strikes"], "status": st["status"], "status_label": st["status_label"],
            "banned": st["banned"], "ban_permanent": st["ban_permanent"], "banned_until": st["banned_until"],
            "online": bool(sid and sid in online_ids),
        })
    sev = {"banned": 3, "suspended": 2, "at_risk": 1, "good": 0}
    flagged.sort(key=lambda f: (sev.get(f["status"], 0), f["active_strikes"]), reverse=True)
    return {"server": server, "ladder": STRIKE_LADDER, "flagged": flagged}


# ---------- Internal moderation API (the Discord bot's lane) ----------
# The bot's /ban /kick /unban /banlist /strike /strikes call these loopback endpoints
# so BOTH staff surfaces drive the ONE proven machine: the Mongo ladder + native
# PlayerBans.json (the durable reconnect block the mod's BanSpawnGuard reads live) +
# the mod ban_commands kick lane (the only kick that removes a live player on this
# build — Evrima's RCON kick acks and leaves them connected) + the 10s enforcer
# re-kick/verify loops. Same shared-secret gate as /internal/streamer/decide; these
# are reachable through the public /api proxy, so fail closed and compare
# constant-time.

def _require_internal_key(x_internal_key: str) -> None:
    if not LIN_INTERNAL_KEY or not hmac.compare_digest(
            (x_internal_key or "").encode("utf-8", "ignore"), LIN_INTERNAL_KEY.encode("utf-8", "ignore")):
        raise HTTPException(status_code=403, detail="forbidden")


def _internal_sid(raw: str) -> str:
    s = re.sub(r"[^0-9]", "", str(raw or ""))
    if len(s) != 17:
        raise HTTPException(status_code=400, detail="bad_steam_id")
    return s


class InternalModInput(BaseModel):
    steam_id: str
    reason: str = "Rule violation"
    hours: int = 0          # ban only: 0 = permanent
    by_name: str = ""
    by_sid: str = ""
    by_id: str = ""         # issuing staff's Discord snowflake — the immutable audit id
    idem: str = ""          # strike only: interaction id; a Discord retry must not double-strike


async def _arm_verified_kick(sid: str, reason: str, by_name: str, by_sid: str,
                             target_user: dict | None) -> list[str]:
    """Fire the mod-lane kick plus the RCON belt and arm the verify loop: the
    user-doc pending_kick when the target has a web account (the tab sees it),
    else a manual_kicks row keyed by sid — both swept by _sweep_pending_kicks
    with identical verified-gone semantics."""
    notes = []
    try:
        await _mod_kick(sid, reason, (target_user or {}).get("persona_name") or "", by_sid or "")
        notes.append("mod_kick_dispatched")
    except Exception as e:
        notes.append(f"mod_kick_error:{type(e).__name__}")
    if rcon_client.is_configured():
        try:
            await rcon_client.kick(sid)
            notes.append("rcon_kick_sent")
        except Exception as e:
            notes.append(f"rcon_kick_error:{type(e).__name__}")
    pend = {"reason": reason, "by": by_name or "La Isla Nublar", "by_sid": by_sid or "",
            "name": (target_user or {}).get("persona_name") or "", "at": now_iso(), "attempts": 0}
    try:
        if target_user:
            await db.users.update_one({"id": target_user["id"]}, {"$set": {"pending_kick": pend}})
        else:
            await db.manual_kicks.update_one({"steam_id": sid}, {"$set": {**pend, "steam_id": sid}}, upsert=True)
        notes.append("pending_kick_armed")
    except Exception as e:
        notes.append(f"pending_kick_error:{type(e).__name__}")
    return notes


@api_router.post("/internal/mod/kick")
async def internal_mod_kick(data: InternalModInput, x_internal_key: str = Header(default="")):
    _require_internal_key(x_internal_key)
    sid = _internal_sid(data.steam_id)
    reason = "".join(ch for ch in (data.reason or "").strip() if ch >= " ")[:256] or "Kicked by staff"
    target = await db.users.find_one({"steam_id": sid}, {"_id": 0})
    online = False
    try:
        ids, _ = await _rcon_online_players()
        online = sid in ids
    except Exception:
        pass
    notes = await _arm_verified_kick(sid, reason, data.by_name, data.by_sid, target)
    await add_log(data.by_name or "Discord", "kick", (target or {}).get("persona_name") or sid,
                  {"steam_id": sid, "reason": reason, "source": "discord_bot", "online": online,
                   "discord_id": re.sub(r"[^0-9]", "", str(data.by_id or ""))})
    return {"ok": True, "online": online, "account": bool(target),
            "persona_name": (target or {}).get("persona_name"), "notes": notes}


@api_router.post("/internal/mod/ban")
async def internal_mod_ban(data: InternalModInput, x_internal_key: str = Header(default="")):
    _require_internal_key(x_internal_key)
    sid = _internal_sid(data.steam_id)
    reason = "".join(ch for ch in (data.reason or "").strip() if ch >= " ")[:256] or "Banned by staff"
    hours = max(0, min(int(data.hours or 0), 24 * 3650))
    permanent = hours == 0
    until = None if permanent else (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    target = await db.users.find_one({"steam_id": sid}, {"_id": 0})
    eff_perm, eff_until, native_hours = permanent, until, hours
    if target:
        # A direct ban rides the user doc as manual_ban so the Sanciones tab, standing,
        # the enforcer self-heal and every ladder recompute see one truth. The flags are
        # folded against the CURRENT pair — deliberately NOT via _recompute_ban, whose
        # reset-the-clock is correct only when ADDING a strike: through it, a short /ban
        # would silently EXTEND an older, nearly-expired ladder ban.
        mb = {"reason": reason, "by": data.by_name or "Discord",
              "permanent": permanent, "until": until, "at": now_iso()}
        folded = _fold_manual_ban({"manual_ban": mb}, {
            "ban_permanent": bool(target.get("ban_permanent")),
            "banned_until": target.get("banned_until")})
        await db.users.update_one({"id": target["id"]}, {
            "$set": {"manual_ban": mb, **folded},
            "$unset": {"native_unban_pending": ""}})
        # The native file is what the spawn guard and the enforcer actually enforce, so
        # it must carry the EFFECTIVE (folded) window — writing the raw requested hours
        # would open a reconnect gap between the shorter file and the longer record.
        eff_perm = bool(folded.get("ban_permanent"))
        eff_until = None if eff_perm else folded.get("banned_until")
        if eff_perm:
            native_hours = 0
        else:
            try:
                _left = datetime.fromisoformat(eff_until) - datetime.now(timezone.utc)
                native_hours = max(1, math.ceil(_left.total_seconds() / 3600))
            except (TypeError, ValueError):
                native_hours = hours
    native_ok = await asyncio.to_thread(
        native_bans.add_ban, sid, reason, native_hours, (target or {}).get("persona_name") or "",
        data.by_name or "La Isla Nublar", data.by_sid or "")
    notes = []
    if not native_ok:
        notes.append("native_ban_unavailable")
    if rcon_client.is_configured():
        try:
            await rcon_client.ban(sid)
            notes.append("rcon_ban_sent")
        except Exception as e:
            notes.append(f"rcon_ban_error:{type(e).__name__}")
    notes += await _arm_verified_kick(sid, reason, data.by_name, data.by_sid, target)
    await add_log(data.by_name or "Discord", "ban", (target or {}).get("persona_name") or sid,
                  {"steam_id": sid, "reason": reason, "hours": hours, "permanent": permanent,
                   "source": "discord_bot", "native": native_ok, "discord_id": re.sub(r"[^0-9]", "", str(data.by_id or ""))})
    return {"ok": True, "banned": native_ok, "account": bool(target),
            "persona_name": (target or {}).get("persona_name"),
            "permanent": eff_perm, "until": eff_until, "notes": notes}


@api_router.post("/internal/mod/unban")
async def internal_mod_unban(data: InternalModInput, x_internal_key: str = Header(default="")):
    _require_internal_key(x_internal_key)
    sid = _internal_sid(data.steam_id)
    target = await db.users.find_one({"steam_id": sid}, {"_id": 0})
    native_removed = False
    strikes_cleared = 0
    if target:
        # Mirrors admin_unban: the full clear (ladder flags, manual_ban, pending kick,
        # active strikes) plus the native retry lane when the file is locked.
        await db.users.update_one({"id": target["id"]}, {
            "$set": {"ban_permanent": False, "banned_until": None},
            "$unset": {"pending_kick": "", "manual_ban": ""}})
        res = await db.strikes.update_many({"user_id": target["id"], "active": True},
                                           {"$set": {"active": False, "removed_by": data.by_name or "Discord",
                                                     "removed_at": now_iso()}})
        strikes_cleared = int(getattr(res, "modified_count", 0) or 0)
        native_removed = await asyncio.to_thread(native_bans.remove_ban, sid)
        if native_removed:
            await db.users.update_one({"id": target["id"]}, {"$unset": {"native_unban_pending": ""}})
        else:
            await db.users.update_one({"id": target["id"]}, {"$set": {"native_unban_pending": sid}})
    else:
        native_removed = await asyncio.to_thread(native_bans.remove_ban, sid)
    await db.manual_kicks.delete_one({"steam_id": sid})
    await add_log(data.by_name or "Discord", "unban", (target or {}).get("persona_name") or sid,
                  {"steam_id": sid, "source": "discord_bot", "native_removed": native_removed,
                   "strikes_cleared": strikes_cleared})
    return {"ok": True, "account": bool(target), "native_removed": native_removed,
            "persona_name": (target or {}).get("persona_name"), "strikes_cleared": strikes_cleared}


@api_router.post("/internal/mod/strike")
async def internal_mod_strike(data: InternalModInput, x_internal_key: str = Header(default="")):
    _require_internal_key(x_internal_key)
    sid = _internal_sid(data.steam_id)
    target = await db.users.find_one({"steam_id": sid}, {"_id": 0})
    if not target:
        # Strikes ride the site-account ladder; a raw Steam ID with no account has
        # nothing to accumulate on. The bot renders guidance toward /ban.
        raise HTTPException(status_code=404, detail="no_account")
    by_sid = re.sub(r"[^0-9]", "", str(data.by_sid or ""))
    by_id = re.sub(r"[^0-9]", "", str(data.by_id or ""))
    # Self-strike guard on BOTH identities: the linked Steam id when the staffer has
    # one, and the immutable Discord snowflake either way (an unlinked staffer must
    # not slip past a guard keyed only on an empty sid).
    if by_sid and str(target.get("steam_id") or "") == by_sid:
        raise HTTPException(status_code=403, detail="self_strike")
    if by_id and str(target.get("discord_id") or "") == by_id:
        raise HTTPException(status_code=403, detail="self_strike")
    # Idempotency: a Discord retry re-sends the SAME interaction id; the second
    # arrival must report the existing strike, never insert a new rung.
    idem = re.sub(r"[^0-9A-Za-z_-]", "", str(data.idem or ""))[:64]
    if idem:
        dup = await db.strikes.find_one({"idem": idem}, {"_id": 0})
        if dup:
            fresh = await db.users.find_one({"id": dup["user_id"]}, {"_id": 0}) or target
            return {"standing": await _compute_standing(fresh), "strike": dup,
                    "enforcement": {"already": True}, "already": True}
    actor = {"persona_name": data.by_name or "Discord", "steam_id": by_sid, "id": None,
             "discord_id": by_id}
    return await _issue_strike_and_enforce(target, data.reason, actor, idem=idem)


@api_router.get("/internal/mod/standing")
async def internal_mod_standing(steam_id: str = Query(...), x_internal_key: str = Header(default="")):
    _require_internal_key(x_internal_key)
    sid = _internal_sid(steam_id)
    target = await db.users.find_one({"steam_id": sid}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="no_account")
    all_strikes, _ = await _active_strikes(target["id"])
    return {"user": {"persona_name": target.get("persona_name"), "steam_id": sid},
            "standing": await _compute_standing(target), "strikes": all_strikes[:25]}


@api_router.get("/internal/mod/banlist")
async def internal_mod_banlist(x_internal_key: str = Header(default="")):
    _require_internal_key(x_internal_key)
    native = await asyncio.to_thread(native_bans.list_bans)
    now = datetime.now(timezone.utc)
    users = []
    async for u in db.users.find({"$or": [{"ban_permanent": True}, {"banned_until": {"$ne": None}}]},
                                 {"_id": 0, "persona_name": 1, "steam_id": 1, "ban_permanent": 1,
                                  "banned_until": 1, "manual_ban": 1}):
        perm = bool(u.get("ban_permanent"))
        bu = u.get("banned_until")
        try:
            active = perm or bool(bu and datetime.fromisoformat(bu) > now)
        except (TypeError, ValueError):
            active = perm
        if not active:
            continue
        users.append({"persona_name": u.get("persona_name"), "steam_id": str(u.get("steam_id") or ""),
                      "permanent": perm, "until": None if perm else bu,
                      "manual": bool(u.get("manual_ban"))})
    return {"native": native, "users": users}


# =============================================================================
# MARKET / AUCTION -- the owner-editable knob layer  (wave 2026-08-11)
# =============================================================================
# Every number the market decides money with lives in ONE Mongo document,
# db.market_config {_id: "market"}, merged over MARKET_DEFAULTS below. The
# constants in this file are the DEFAULTS, never the live value: every read
# goes through _mcfg(), so the owner changes a number without a deploy, an SSH
# session or a restart.
#
# THREE DISCIPLINES, chosen per knob and NOT interchangeable:
#
#   REFUSE (503)  -- every number that decides who gets paid or whether
#                    property moves. A CLAMPING reader answers a number the
#                    owner did not choose and says so nowhere: type 500 into
#                    the tax and a clamp quietly starts taking 95% of every
#                    sale. The precedent is the framework's own
#                    webcore/routes/auction.py tax_percent(), which refuses
#                    where every neighbouring knob clamps -- and it refuses
#                    where it is READ, so a broken knob blocks NEW listings
#                    while auctions already running settle off their snapshot.
#                    `bool` is rejected explicitly: True is an int in Python
#                    and would read as 1%, and an owner who typed `true` did
#                    not mean "one percent".
#   CLAMP         -- mechanical limits whose two ends are both sane.
#   REPLACE-WHOLE -- the two duration lists, when the stored node is not a
#                    non-empty list of numbers.
#
# THE PRICING ARITHMETIC, fixed (integer throughout -- see _merit / _tax_on):
#   priced_mutations = min(mutation_cap, count(mutations) + count(elder_mutations))
#   suggested        = species_base[slug] + per_mutation_bonus * priced_mutations
#   price_min        = max(abs_min_price, suggested * price_floor_pct   // 100)
#   price_max        = min(abs_max_price, suggested * price_ceiling_pct // 100)
#   tax              = price * tax_pct // 100      # INTEGER FLOOR, never round
#   net              = price - tax                 # price == tax + net, ALWAYS
# Owner's worked example lands to the coin: trex 1,000,000 + 12 x 400,000 =
# 5,800,000; rails 2,900,000 .. 17,400,000; at 25% the seller nets 4,350,000.

# --- retired-but-retained constants ------------------------------------------
# The last-5-sales suggestion model these three served was deleted in this wave
# (_suggested_price_info -> _market_stats_info, display only). They are kept as
# module names because the shipped gate tests_local/test_market_suggested_price.py
# extracts these literals by regex; the gate rewrite that replaces that file may
# delete them. NOTHING IN THE PRICING PATH READS THEM.
MARKET_MIN_PRICE = 100
MARKET_MAX_PRICE = 10_000_000
MARKET_RARITY_BASE = {"Common": 15000, "Uncommon": 25000, "Rare": 45000, "Epic": 80000,
                      "Legendary": 130000, "Mythic": 200000, "Apex": 260000}
# LIVE: how many recent sales the DISPLAY statistic reads (median of the last N).
MARKET_SUGGESTED_SALES_WINDOW = 10

# Legacy fee rates. Listings written before this wave carry a float `fee_rate`
# and no `tax_pct`; settlement derives an integer percent from it (see
# _listing_tax_pct) so a grandfathered row settles on the deal it was born with.
MARKET_SALE_FEE_RATE = 0.15       # flat platform fee for direct sales (pre-wave)
MARKET_AUCTION_FEE_RATE = 0.10    # flat platform fee for auctions (pre-wave)
MARKET_WITHDRAW_FEE_RATE = 0.10   # fee to pull an active listing back
MARKET_SALE_DURATIONS = [6, 24, 48, 72]        # direct-sale duration options (hours)
MARKET_AUCTION_DURATIONS = [0.5, 1, 2, 4, 8]   # auction duration options (hours)
MARKET_TIER_MUT_CAP = {"basic": 3, "prime": 6}

# THE 22-SPECIES BASE TABLE. Measured medians snapped to seven rungs; six of the
# 22 land exactly on their measured median (trex, cerato, allo, ptera, diablo,
# troodon), which is the evidence the ladder is calibrated rather than invented.
# Every median is partly a ratchet artifact of the retired last-5-average model,
# so thin samples are peer-set rather than followed.
SPECIES_BASE_DEFAULT = {
    "deino": 1_500_000,
    "trex": 1_000_000, "trike": 1_000_000,
    "carno": 800_000, "kentro": 800_000, "stego": 800_000,
    "austro": 600_000, "cerato": 600_000, "galli": 600_000, "raptor": 600_000,
    "allo": 500_000, "pachy": 500_000, "ptera": 500_000,
    "diablo": 400_000, "dilo": 400_000, "hypsi": 400_000, "maia": 400_000,
    "tenonto": 400_000,
    "beipiao": 300_000, "dryo": 300_000, "herrera": 300_000, "troodon": 300_000,
}

MARKET_DEFAULTS = {
    "min_growth_pct": 80,            # REFUSE 0..100
    "sale_tax_pct": 25,              # REFUSE 0..95
    "auction_tax_pct": 25,           # REFUSE 0..95   (equal on purpose: the
                                     #   cheaper lane is the wash lane)
    "withdraw_fee_flat": 25_000,     # REFUSE 0..1,000,000   (LIVE 2026-08-11:
                                     #   market_withdraw charges it and
                                     #   market_mine displays it, through ONE
                                     #   helper -- see _withdraw_fee)
    "per_mutation_bonus": 400_000,   # REFUSE 0..1,000,000
    "mutation_cap": 12,              # CLAMP 0..16
    "species_base": SPECIES_BASE_DEFAULT,
    "species_base_fallback": 400_000,  # REFUSE 50,000..2,000,000
    "price_floor_pct": 50,           # CLAMP 10..100
    "price_ceiling_pct": 300,        # CLAMP 100..1000
    "abs_min_price": 10_000,         # CLAMP 1..1,000,000
    "abs_max_price": 25_000_000,     # CLAMP 1,000,000..1,000,000,000
    "sale_durations_h": [6, 24, 48, 72],
    "auction_durations_h": [0.5, 1, 2, 4, 8],
    "max_listings_per_seller": 5,    # CLAMP 1..25
    "write_rate_per_min": 12,        # CLAMP 1..120
    # --- THE AUCTION, as a real auction (2026-08-11) --------------------------
    # Before this wave `min_bid = (current_bid or price - 1) + 1`, so ONE COIN
    # won a 5,800,000 auction. A step that is a flat number is 0.86% of that
    # auction and 33% of a 150,000 one, so the step is a PERCENTAGE WITH A FLOOR.
    "bid_step_min": 10_000,          # CLAMP 1..1,000,000
    "bid_step_pct": 2,               # CLAMP 0..100
    "bid_max": 50_000_000,           # CLAMP 1..1,000,000,000
    "antisnipe_secs": 60,            # CLAMP 0..3,600
    "antisnipe_max_total_secs": 600,  # CLAMP 0..86,400
    # --- the per-ANIMAL move cooldown ----------------------------------------
    # 0 DISABLES, which is his own established re-enable contract from
    # project_lin_vault_cooldown_removal_20260716. REFUSE, not clamp: this is a
    # number that decides whether property may move.
    "dino_move_cooldown_secs": 86_400,   # REFUSE 0..604,800 (0 = off)
    "dino_move_cooldown_on_sale": True,  # bool
    # --- THE TRADE SUBSYSTEM (R7, 2026-08-11) --------------------------------
    # "plus the live trade system with a cooldown of 24 hours" -- the owner's
    # own words, and 86,400 is that number. NO COINS ON EITHER SIDE of a trade:
    # a coin leg turns a trade into an untaxed sale and re-opens the fee the
    # market charges, so there is no knob for one and no field to put one in.
    "trade_enabled": True,               # bool
    "trade_cooldown_secs": 86_400,       # REFUSE 0..604,800 (0 = off)
    "trade_offer_ttl_secs": 172_800,     # REFUSE 300..604,800  (48 h)
    "trade_max_items_per_side": 3,       # CLAMP 1..5
    "trade_symmetry_pct": 25,            # CLAMP 0..100 (0 = the two sides must
                                         #   be worth exactly the same)
    "trade_max_open_offers": 5,          # CLAMP 1..25
    "trade_growth_gate": True,           # bool -- apply min_growth_pct to trades
    # --- THE BOARD: trades on the same surface as the sales (2026-08-11) ------
    # His words: "redesign so dinosaurs get traded on the same tab people can
    # see dinos for sale. no need to send anybody anything." A board entry is an
    # ADVERTISEMENT -- it escrows nothing and moves nothing -- so its two knobs
    # are the shape of a shop window, not of a settlement.
    "trade_board_ttl_secs": 259_200,     # REFUSE 3,600..604,800 (72 h, the same
                                         #   ceiling a sale listing may run for)
    "trade_max_board_per_player": 3,     # CLAMP 1..25
}

# Env seeds. An EXPLICIT env value replaces the shipped default; it does NOT
# bypass the discipline, so an out-of-band env value still refuses with the
# knob named. Unparseable env is ignored (with one warning) -- it is not a
# number at all, and refusing the whole market over a typo'd string would be
# the clamp mistake in a different costume.
MARKET_ENV_SEEDS = {
    "min_growth_pct": "LIN_MARKET_MIN_GROWTH_PCT",
    "sale_tax_pct": "LIN_MARKET_SALE_TAX_PCT",
    "auction_tax_pct": "LIN_MARKET_AUCTION_TAX_PCT",
    "withdraw_fee_flat": "LIN_MARKET_WITHDRAW_FEE_FLAT",
    "per_mutation_bonus": "LIN_MARKET_PER_MUTATION",
    "dino_move_cooldown_secs": "LIN_DINO_MOVE_COOLDOWN_SECS",
    "trade_cooldown_secs": "LIN_TRADE_COOLDOWN_SECS",
}

# Every knob, with the discipline that reads it and the band that discipline
# enforces. ONE table: the PATCH route validates from it, the GET route renders
# it, and a knob added to MARKET_DEFAULTS without a row here is refused by the
# admin route rather than silently accepted and then ignored by its reader.
#   "refuse" -> a whole int inside the band or the edit is refused, nothing changed
#   "clamp"  -> a whole int, snapped INTO the band (the value is reported back)
#   "bool"   -> a real bool; True/False only, never 0/1
#   "durations" -> replace-whole, a non-empty list of positive numbers
#   "table"  -> species_base; the WHOLE edit is refused, naming the bad slug
MARKET_KNOB_SPEC = {
    "min_growth_pct": ("refuse", 0, 100),
    "sale_tax_pct": ("refuse", 0, 95),
    "auction_tax_pct": ("refuse", 0, 95),
    "withdraw_fee_flat": ("refuse", 0, 1_000_000),
    "per_mutation_bonus": ("refuse", 0, 1_000_000),
    "species_base_fallback": ("refuse", 50_000, 2_000_000),
    "dino_move_cooldown_secs": ("refuse", 0, 604_800),
    "mutation_cap": ("clamp", 0, 16),
    "price_floor_pct": ("clamp", 10, 100),
    "price_ceiling_pct": ("clamp", 100, 1000),
    "abs_min_price": ("clamp", 1, 1_000_000),
    "abs_max_price": ("clamp", 1_000_000, 1_000_000_000),
    "max_listings_per_seller": ("clamp", 1, 25),
    "write_rate_per_min": ("clamp", 1, 120),
    "bid_step_min": ("clamp", 1, 1_000_000),
    "bid_step_pct": ("clamp", 0, 100),
    "bid_max": ("clamp", 1, 1_000_000_000),
    "antisnipe_secs": ("clamp", 0, 3_600),
    "antisnipe_max_total_secs": ("clamp", 0, 86_400),
    "dino_move_cooldown_on_sale": ("bool", None, None),
    "trade_enabled": ("bool", None, None),
    "trade_growth_gate": ("bool", None, None),
    "trade_cooldown_secs": ("refuse", 0, 604_800),
    "trade_offer_ttl_secs": ("refuse", 300, 604_800),
    "trade_max_items_per_side": ("clamp", 1, 5),
    "trade_symmetry_pct": ("clamp", 0, 100),
    "trade_max_open_offers": ("clamp", 1, 25),
    "trade_board_ttl_secs": ("refuse", 3_600, 604_800),
    "trade_max_board_per_player": ("clamp", 1, 25),
    "sale_durations_h": ("durations", None, None),
    "auction_durations_h": ("durations", None, None),
    "species_base": ("table", 50_000, 2_000_000),
}

_MARKET_WARNED_ONCE: set = set()
_MARKET_WARN_CAP = 500


def _market_warn_once(key: str, msg: str, *args) -> None:
    """One WARNING per distinct key per process. A log flood buries its own
    signal, so the fourth identical line is worth less than nothing. Bounded:
    a hostile stream of distinct keys cannot grow this set without limit."""
    if key in _MARKET_WARNED_ONCE:
        return
    if len(_MARKET_WARNED_ONCE) >= _MARKET_WARN_CAP:
        return
    _MARKET_WARNED_ONCE.add(key)
    logger.warning(msg, *args)


def _market_defaults() -> dict:
    """MARKET_DEFAULTS with any explicit env seed applied. Fresh dict every
    call (and a copy of the species table), so no caller can mutate the
    shipped defaults through the value it was handed."""
    cfg = dict(MARKET_DEFAULTS)
    cfg["species_base"] = dict(SPECIES_BASE_DEFAULT)
    cfg["sale_durations_h"] = list(MARKET_DEFAULTS["sale_durations_h"])
    cfg["auction_durations_h"] = list(MARKET_DEFAULTS["auction_durations_h"])
    for key, env_name in MARKET_ENV_SEEDS.items():
        raw = os.environ.get(env_name)
        if raw in (None, ""):
            continue
        try:
            cfg[key] = int(str(raw).strip())
        except (TypeError, ValueError):
            _market_warn_once("env:" + env_name,
                              "[MARKET] %s=%r is not a whole number - ignoring it and "
                              "using the shipped default %s", env_name, raw,
                              MARKET_DEFAULTS.get(key))
    return cfg


_market_cfg_cache = None
_market_cfg_cache_at = 0.0
# The cache exists so the hot path is not one Mongo read per request. It is
# short-lived AND explicitly invalidated: the TTL is what makes a hand-edit
# straight into Mongo (no admin route shipped yet) take effect within a minute
# instead of never, and the invalidator is what makes a future PATCH instant.
MARKET_CFG_CACHE_SECS = 30.0


def _market_cfg_invalidate() -> None:
    global _market_cfg_cache, _market_cfg_cache_at
    _market_cfg_cache = None
    _market_cfg_cache_at = 0.0


async def _mcfg() -> dict:
    """THE live market config: db.market_config {_id:"market"} merged OVER the
    defaults. Only keys the code knows about are merged, so a stray field in
    the document can never inject anything. A Mongo failure answers the
    DEFAULTS and is not cached -- the defaults are the owner's own shipped
    numbers, so falling back to them never opens a gate wider than he set."""
    global _market_cfg_cache, _market_cfg_cache_at
    now = time.time()
    if _market_cfg_cache is not None and (now - _market_cfg_cache_at) < MARKET_CFG_CACHE_SECS:
        return _market_cfg_cache
    cfg = _market_defaults()
    try:
        doc = await db.market_config.find_one({"_id": "market"}, {"_id": 0})
    except Exception:
        logger.exception("[MARKET] market_config read failed - serving defaults this pass")
        return cfg                       # deliberately NOT cached: retry next call
    if isinstance(doc, dict):
        for k, v in doc.items():
            if k in cfg:
                cfg[k] = v
    _market_cfg_cache = cfg
    _market_cfg_cache_at = now
    return cfg


# ---------- the discipline readers ----------
def _knob_int(cfg, key: str, lo: int, hi: int) -> int:
    """CLAMP. For a mechanical limit whose two ends are both sane. Junk falls
    back to the shipped default (warned once), never to zero."""
    raw = (cfg or {}).get(key, MARKET_DEFAULTS.get(key))
    try:
        if isinstance(raw, bool):
            raise ValueError("bool is not a number here")
        val = int(raw)
    except (TypeError, ValueError, OverflowError):
        val = int(MARKET_DEFAULTS.get(key, lo))
        _market_warn_once("knob:" + key,
                          "[MARKET] knob %s=%r is not a whole number - using the "
                          "shipped default %s", key, raw, val)
    return max(lo, min(hi, val))


def _knob_refuse_int(cfg, key: str, lo: int, hi: int,
                     label: str = "La configuración del mercado está mal configurada") -> int:
    """REFUSE (503). For every number that decides who gets paid or whether
    property moves. Names the knob, states the band, and states that NOTHING
    was changed. bool / float / str are rejected as TYPES, not coerced."""
    raw = (cfg or {}).get(key, MARKET_DEFAULTS.get(key))
    ok = isinstance(raw, int) and not isinstance(raw, bool) and lo <= raw <= hi
    if not ok:
        shown = raw if (isinstance(raw, int) and not isinstance(raw, bool)) else repr(raw)
        raise HTTPException(status_code=503, detail=(
            f"{label} ({key} = {shown}; debe ser un número entero entre {lo} y {hi}). "
            f"No se cambió nada. Avísale a un administrador."))
    return int(raw)


def _tax_pct(cfg, listing_type: str) -> int:
    """The platform's cut for this listing type, as a whole percent. REFUSES.
    Read BEFORE anything moves, so a broken knob blocks a NEW listing and
    never restrikes one already running (those settle off their snapshot)."""
    key = "auction_tax_pct" if listing_type == "auction" else "sale_tax_pct"
    return _knob_refuse_int(cfg, key, 0, 95,
                            label="La comisión del mercado está mal configurada")


def _tax_on(price, pct) -> int:
    """The cut on one price. INTEGER FLOOR, never a round.

    A half point rounded UP is a coin taken from a seller who never agreed to
    it, so this floors in the seller's favour: 5,800,006 at 25% pays the seller
    4,350,005, where int(round(price*0.75)) pays 4,350,004. `price == tax + net`
    holds for every legal pair, which is the property the receipt is built on.
    A price at or below zero taxes nothing -- a negative cut would PAY the
    seller out of the treasury."""
    try:
        p = int(price)
        q = int(pct)
    except (TypeError, ValueError, OverflowError):
        return 0
    if p <= 0 or q <= 0:
        return 0
    return p * q // 100


def _listing_tax_pct(l: dict) -> int:
    """The percent a listing settles at -- THE SNAPSHOT, NEVER THE KNOB. An
    owner editing the fee mid-flight must not be able to restrike a running
    auction. Grandfathered rows (pre-wave, no `tax_pct`) derive theirs from the
    float `fee_rate` they were born with, which is the deal their seller
    accepted; the derived integer is also what the receipt prints, closing the
    old f"-{int(rate*100)}%" line that printed 15 while charging 15.5%."""
    raw = l.get("tax_pct")
    if isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw <= 100:
        return int(raw)
    try:
        rate = float(l.get("fee_rate", MARKET_SALE_FEE_RATE))
    except (TypeError, ValueError):
        rate = MARKET_SALE_FEE_RATE
    return max(0, min(100, int(round(rate * 100))))


def _duration_tiers(cfg, listing_type: str) -> list:
    """REPLACE-WHOLE. A duration list that is not a non-empty list of numbers
    is replaced ENTIRELY by the shipped default -- half a list is not a menu."""
    key = "auction_durations_h" if listing_type == "auction" else "sale_durations_h"
    raw = (cfg or {}).get(key)
    out = []
    if isinstance(raw, (list, tuple)):
        for t in raw:
            if isinstance(t, bool) or not isinstance(t, (int, float)):
                out = []
                break
            if not (0 < float(t) <= 24 * 30):
                out = []
                break
            out.append(float(t))
    if not out:
        if raw is not None:
            _market_warn_once("durations:" + key,
                              "[MARKET] knob %s=%r is not a non-empty list of hours - "
                              "using the shipped default", key, raw)
        out = [float(t) for t in MARKET_DEFAULTS[key]]
    return out


def _fmt_hours_es(t: float) -> str:
    """One duration tier as the owner's players read it."""
    if abs(t - 0.5) < 1e-9:
        return "30 minutos"
    if abs(t - round(t)) < 1e-9:
        return str(int(round(t)))
    return ("%g" % t).replace(".", ",")


def _join_es(parts: list) -> str:
    """Spanish list join. `o` becomes `u` before a word that SOUNDS like it
    starts with o -- "6, 24, 48 o 72" but "1, 2, 4 u 8" (ocho)."""
    parts = [str(p) for p in parts]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    last = parts[-1]
    conj = "u" if last[:2] in ("8", "11") or last[:1] == "8" else "o"
    return ", ".join(parts[:-1]) + f" {conj} " + last


def _duration_or_400(hours, listing_type: str, cfg) -> float:
    """MEMBERSHIP TEST that names the set, replacing the nearest-tier SNAP.

    The retired _duration_fee_rate did
    `min(tiers, key=lambda t: abs(t - float(hours or default)))`, which turned a
    client's 999 into 72 and a `0` into the default without a word to anybody.
    A duration is a contract about when the animal comes home; it is chosen
    from a menu or it is refused."""
    tiers = _duration_tiers(cfg, listing_type)
    try:
        h = float(hours)
    except (TypeError, ValueError, OverflowError):
        h = None
    if h is not None and h == h and abs(h) != float("inf"):
        for t in tiers:
            if abs(t - h) < 1e-9:
                return float(t)
    menu = _join_es([_fmt_hours_es(t) for t in tiers])
    lane = "una subasta" if listing_type == "auction" else "una venta directa"
    raise HTTPException(status_code=400, detail=(
        f"Duración no válida. Para {lane} elige {menu} horas."))


def _knob_bool(cfg, key: str) -> bool:
    """A switch. Only a REAL bool is honoured -- 0/1/"true" are not bools, and
    reading them as one is how a switch ends up in a state nobody chose. Junk
    falls back to the shipped default, warned once."""
    raw = (cfg or {}).get(key, MARKET_DEFAULTS.get(key))
    if isinstance(raw, bool):
        return raw
    _market_warn_once("knobbool:" + key,
                      "[MARKET] knob %s=%r is not true/false - using the shipped "
                      "default %s", key, raw, MARKET_DEFAULTS.get(key))
    return bool(MARKET_DEFAULTS.get(key))


def _withdraw_fee(cfg) -> int:
    """THE withdraw fee, FLAT, read through ONE helper by both the display
    (market_mine) and the charge (market_withdraw).

    It replaces a 10% rate for two reasons, and the second is the one that
    matters. (1) At this wave's scale 10% of a 17,400,000 listing is 1,740,000
    against a hard `coins >= fee` refusal -- a percentage prices a seller out of
    their own animal, and a withdraw fee prices an ACTION, not a value the
    seller typed. (2) The pre-wave code had TWO formulas: market_mine displayed
    `(current_bid or price) * 0.10` and market_withdraw charged `price * 0.10`.
    A flat number read through one function cannot diverge BY CONSTRUCTION,
    which is a stronger guarantee than two call sites agreeing today."""
    return _knob_refuse_int(cfg, "withdraw_fee_flat", 0, 1_000_000,
                            label="La comisión de retiro está mal configurada")


def _bid_step(cfg, current: int) -> int:
    """What one raise must ADD. max(bid_step_min, current * bid_step_pct // 100).

    The pre-wave expression was `(current_bid or price - 1) + 1`: a ONE COIN
    raise won a 5,800,000 auction, and a bidder could hold the lead for the
    price of a rounding error. Integer floor on the percentage, so the step is
    exactly the number the page was shown."""
    try:
        cur = max(0, int(current))
    except (TypeError, ValueError, OverflowError):
        cur = 0
    return max(_knob_int(cfg, "bid_step_min", 1, 1_000_000),
               cur * _knob_int(cfg, "bid_step_pct", 0, 100) // 100)


def _min_next_bid(cfg, l: dict) -> int:
    """The lowest bid this server will accept on `l` right now. ONE expression,
    read by market_bid AND published by _market_public as `min_next_bid`, so the
    page and the validator cannot disagree about the number.

    The FIRST bid pays the opening price exactly (that is the seller's ask, and
    a step on top of it would make the advertised price unreachable); every bid
    after it pays current + one step."""
    try:
        cur = int(l.get("current_bid") or 0)
    except (TypeError, ValueError, OverflowError):
        cur = 0
    if cur <= 0:
        try:
            return int(l.get("price") or 0)
        except (TypeError, ValueError, OverflowError):
            return 0
    return cur + _bid_step(cfg, cur)


def _bid_max(cfg) -> int:
    """The ceiling on ONE bid, enforced on EVERY lane that can raise a price.
    The recorded donor defect (TWB) checked it only on the custom-amount lane,
    so an auto-click walked an auction past the ceiling one click at a time."""
    return _knob_int(cfg, "bid_max", 1, 1_000_000_000)


def _bid_charged(l: dict) -> int:
    """WHAT WAS ACTUALLY TAKEN from the current top bidder -- the number a
    refund must pay back. Never the nominal bid.

    The fleet law behind this: a bid placed on a lane that captured nothing (a
    waiver, a comp, a tiered buyer) must never be convertible into real currency
    by a later refund. LIN has vip_coins and tiered buyers, which is exactly the
    shape that breaks "the bid is what was charged".

    A row written BEFORE this wave carries no `current_bid_charged`. For those
    the nominal genuinely IS what was taken (the pre-wave route debited
    `data.amount` and set `current_bid` to the same number), so the fallback is
    correct rather than convenient -- and it says so out loud."""
    raw = l.get("current_bid_charged")
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return int(raw)
    try:
        nominal = int(l.get("current_bid") or 0)
    except (TypeError, ValueError, OverflowError):
        nominal = 0
    if nominal > 0:
        _market_warn_once("bidcharged:" + str(l.get("id") or "?"),
                          "[MARKET] listing %s has a bid with no current_bid_charged "
                          "(pre-wave escrow) - refunding the nominal %s",
                          l.get("id"), nominal)
    return max(0, nominal)


def _antisnipe_plan(cfg, l: dict, now=None) -> dict:
    """THE ANTI-SNIPE EXTENSION for ONE landing bid, as a pure decision.

    A sniper who bids in the last second wins an auction nobody else could
    answer, so a bid inside the window pushes the clock out. Two laws shape it,
    and both are the framework's (webcore/routes/auction.py place_bid):

      EXTEND FROM THE STORED END, NEVER FROM `now`. Extending from now would
      SHORTEN an auction whose last bid landed early inside the window --
      the guard would become the attack.

      A HARD TOTAL CAP. The framework has none; LIN gets one, because an
      unbounded extension is a bot holding one auction open all night. Every
      grant is drawn from ONE budget (`antisnipe_max_total_secs`) that is
      accumulated on the row as `extended_secs`, so N bids cannot buy N
      windows -- the (N+1)th grants whatever is left, then zero.

    Never raises and never shortens: both knobs are CLAMP readers, an
    unreadable clock simply grants nothing, and an `extended_secs` already
    past a lowered cap yields a grant of 0 rather than a negative one.

    Returns {"granted", "extended_secs", "ends_at", "fields"} -- `fields` is
    empty when nothing moved, so the caller merges it into the SAME atomic
    promotion that seats the bid. An extension that is not part of that update
    is an extension a LOST race still hands out."""
    out = {"granted": 0, "extended_secs": 0, "ends_at": None, "fields": {}}
    try:
        already = max(0, int(l.get("extended_secs") or 0))
    except (TypeError, ValueError, OverflowError):
        already = 0
    out["extended_secs"] = already
    window = _knob_int(cfg, "antisnipe_secs", 0, 3600)
    budget = _knob_int(cfg, "antisnipe_max_total_secs", 0, 86_400)
    if window <= 0:
        return out                       # the guard is switched off
    ends = _listing_ends_at(l)
    if ends is None:
        # No readable clock. The settle pass parks that row as needs_admin; a
        # guess at its end instant here would invent a deadline nobody set.
        return out
    now = now or datetime.now(timezone.utc)
    left = (ends - now).total_seconds()
    if left > window:
        return out                       # the bid did not land inside the window
    grant = min(window, max(0, budget - already))
    if grant <= 0:
        # AT THE CAP. The auction stops extending and the clock stands -- this
        # is the line that ends the all-night hold.
        return out
    out["granted"] = grant
    out["extended_secs"] = already + grant
    out["ends_at"] = (ends + timedelta(seconds=grant)).isoformat()
    out["fields"] = {"ends_at": out["ends_at"], "extended_secs": out["extended_secs"]}
    return out


def l_seller_identity(l: dict) -> dict:
    """The SELLER as `_same_person` reads an identity: their user id plus the
    steam id the listing itself can prove.

    market_buy has called this since the 2026-08-11 wave and NOTHING DEFINED IT
    -- a NameError on the first line of every direct-sale purchase, i.e. the buy
    lane answered 500 for everybody. It is defined here rather than made async
    on purpose: a vault-sourced listing carries the seller's own escrowed
    `parked_dinos` row, and `steam_id` on that row IS the seller's steam id at
    list time, so the check needs no extra database read on the hot path.

    An inventory-sourced listing has no steam identity to offer and answers
    None for it; `_same_person` then falls back to the user-id comparison,
    which is exactly the pre-wave behaviour for that lane and no weaker."""
    l = l or {}
    sid = l.get("seller_steam_id")
    if not sid and l.get("source") == "vault":
        sid = (l.get("vault_payload") or {}).get("steam_id")
    return {"id": l.get("seller_id"), "steam_id": None if sid is None else str(sid)}


# ---------- THE mutation counter, and THE growth reader ----------
def _priced_mut_count(cfg, *, vault_row=None, inv_item=None) -> int:
    """THE mutation count: the number the buyer reads AND the number the price
    was built from. Two storage shapes, ONE definition -- the animal's OWN
    slots plus its Elder sets.

    `parent_mutations` / the "parent" group are the PARENTS' lineage and are
    EXCLUDED: a player is not paid for their grandparent's genes. Measured
    ceiling over 2,878 live parked rows is 12 (4 active + 8 elder, a
    Deinosuchus), which is exactly what makes 1,000,000 + 12 x 400,000 =
    5,800,000 land on the owner's own worked example.

    OWNER RULING 2026-08-11, deliberate and NOT a bug: the paid vault mutation
    editor (`_mutation_edit_cost`, 20,000 per slot) writes into these same two
    columns, so a PURCHASED slot counts toward merit exactly like an earned
    one. He was asked and he said keep it at 20,000 and leave the arbitrage
    open for now. Do not "fix" this by subtracting purchased slots -- that is a
    provenance ledger, and it is his call to ask for one."""
    cap = _knob_int(cfg, "mutation_cap", 0, 16)
    if vault_row is not None:
        n = (vault._mutation_count(vault_row.get("mutations"))
             + vault._mutation_count(vault_row.get("elder_mutations")))
        return max(0, min(cap, n))
    item = inv_item or {}
    own, _parent, ea, eb = _inventory_dino_mutation_keys(item)
    if not item.get("mutation_groups"):
        # Pre-grouped-editor doc: _inventory_dino_mutation_keys falls back to
        # the FLAT list, which is child+parent+elder combined and cannot be
        # split. Counting it would OVER-price, so cap hard and SAY SO rather
        # than guess at which slots were the parents'.
        _market_warn_once("flatinv:" + str(item.get("id") or "?"),
                          "[MARKET] inventory dino %s has no mutation_groups - flat "
                          "count %s may include parent slots", item.get("id"), len(own))
    return max(0, min(cap, len(own) + len(ea) + len(eb)))


# One epsilon, used by BOTH the display and the gate. That is what makes the
# pairing law true BY CONSTRUCTION rather than by luck: for every value,
# _growth_pct_display(x) >= min  <=>  _growth_gate_ok(cfg, x). Put the epsilon
# in only one of the two and 0.7999999999999999 displays "79" while the gate
# admits it -- a card reading 79% for an animal the market accepted, or worse,
# a card reading 80% for one it refuses.
_GROWTH_EPS = 1e-9


def _growth_pct_exact(raw, source: str):
    """UNROUNDED percent from either unit system, or None on junk.

    Vault `parked_dinos.growth` is a 0..1 FRACTION (measured live: 0.898333,
    1.0, 0.263085, 0.800854). Website inventory `saved_growth` is ALREADY A
    PERCENT and may carry one decimal (park_dino stores round(growth,1) ->
    87.3). A gate written against the wrong unit refuses everything or
    refuses nothing, and both failures are silent.

    None on anything unreadable OR out of its own unit's range -- a gate must
    never pass on input it could not read."""
    try:
        val = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if val != val or val in (float("inf"), float("-inf")):   # NaN / inf
        return None
    if source == "vault":
        if not (0.0 <= val <= 1.0 + _GROWTH_EPS):
            return None
        return val * 100.0
    if not (0.0 <= val <= 100.0 + _GROWTH_EPS):
        return None
    return val


def _growth_pct_display(exact) -> int:
    """What the market SHOWS. FLOOR, never round -- a card must never advertise
    80% for an animal the gate refuses."""
    if exact is None:
        return 0
    try:
        return int(math.floor(float(exact) + _GROWTH_EPS))
    except (TypeError, ValueError, OverflowError):
        return 0


def _growth_gate_ok(cfg, exact) -> bool:
    """The 80% gate, on the exact percent. Reads min_growth_pct through the
    REFUSE reader: a broken gate knob blocks NEW listings loudly rather than
    letting a clamp pick a threshold the owner never chose."""
    if exact is None:
        return False
    min_pct = _knob_refuse_int(cfg, "min_growth_pct", 0, 100)
    return (float(exact) + _GROWTH_EPS) >= float(min_pct)


# ---------- merit + rails ----------
def _species_base_table(cfg) -> dict:
    """The live base table, entry-validated. An entry outside 50,000..2,000,000
    or of the wrong type is treated as ABSENT (so the slug takes the loud
    fallback), never silently coerced -- a price table decides who gets paid."""
    raw = (cfg or {}).get("species_base")
    if not isinstance(raw, dict):
        if raw is not None:
            _market_warn_once("speciesbase:type",
                              "[MARKET] species_base is %r, not a table - using the "
                              "shipped 22-row default", type(raw).__name__)
        return dict(SPECIES_BASE_DEFAULT)
    out = {}
    for slug, val in raw.items():
        if isinstance(val, int) and not isinstance(val, bool) and 50_000 <= val <= 2_000_000:
            out[str(slug)] = int(val)
        else:
            _market_warn_once("speciesbase:" + str(slug),
                              "[MARKET] species_base[%r]=%r is outside 50,000..2,000,000 - "
                              "that slug will take the fallback base", slug, val)
    return out


def _merit(cfg, slug: str, muts: int) -> dict:
    """What one ANIMAL is worth, and the rails around it. Integer arithmetic
    throughout; reads NO sales history at all, which is the structural kill for
    the runaway ratchet the old last-5-average model had -- a wash sale has
    nothing left to push.

    The rail and the absolute cap are BOTH real and whichever is TIGHTER binds.
    Under the shipped table the highest rail is 18,900,000 (deino at 12) against
    abs_max_price 25,000,000, so today the rail always binds -- but that is a
    fact about the current table, not an invariant, because both species_base
    and per_mutation_bonus are owner-editable."""
    slug = str(slug or "")
    table = _species_base_table(cfg)
    missing = slug not in table
    fallback = _knob_refuse_int(cfg, "species_base_fallback", 50_000, 2_000_000)
    base = int(table.get(slug, fallback))
    if missing:
        _market_warn_once("basemiss:" + slug,
                          "[MARKET] species_base MISS slug=%r -> fallback=%s", slug, fallback)
    per_mut = _knob_refuse_int(cfg, "per_mutation_bonus", 0, 1_000_000)
    n = max(0, int(muts))
    sug = base + per_mut * n
    floor_pct = _knob_int(cfg, "price_floor_pct", 10, 100)
    ceil_pct = _knob_int(cfg, "price_ceiling_pct", 100, 1000)
    abs_min = _knob_int(cfg, "abs_min_price", 1, 1_000_000)
    abs_max = _knob_int(cfg, "abs_max_price", 1_000_000, 1_000_000_000)
    rail_lo = sug * floor_pct // 100
    rail_hi = sug * ceil_pct // 100
    lo = max(abs_min, rail_lo)
    hi = min(abs_max, rail_hi)
    return {"suggested": sug, "min": lo, "max": max(lo, hi),
            "base": base, "base_source": "fallback" if missing else "table",
            "base_missing": missing, "mutations": n, "per_mutation": per_mut,
            "floor_pct": floor_pct, "ceiling_pct": ceil_pct,
            "abs_min": abs_min, "abs_max": abs_max,
            # which constraint actually bound, so a refusal can quote the real one
            "min_bound_by": "abs" if abs_min > rail_lo else "rail",
            "max_bound_by": "abs" if abs_max < rail_hi else "rail"}


def _market_clean_title(raw) -> str:
    """Printable-only listing title. Unicode category Cf is stripped (that is
    U+202E RTL-override and the zero-width joiners), other control/surrogate/
    private-use characters go with it, combining marks are capped at two in a
    row (that is Zalgo), whitespace runs collapse, 60 chars -- the existing
    limit. vault.clean_custom_name stays the FALLBACK SOURCE for a title, not
    the sanitiser."""
    text = str(raw or "")
    out = []
    combining = 0
    for ch in text:
        cat = unicodedata.category(ch)
        if cat == "Cf" or cat in ("Cs", "Co", "Cn"):
            continue
        if cat == "Cc":
            if ch in ("\t", "\n", "\r"):
                out.append(" ")
            continue
        if cat in ("Mn", "Mc", "Me"):
            combining += 1
            if combining > 2:
                continue
        else:
            combining = 0
        out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()[:60].strip()


def _es_num(n) -> str:
    """A whole number the way this owner's players read it: 5.800.000, not
    5,800,000. Pinned here so the number in the refusal copy and the number in
    the field are the same string."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError, OverflowError):
        return str(n)


# ---------- the refusals, shared by BOTH create lanes ----------
def _market_listing_type_or_400(raw) -> str:
    """A listing type is CHOSEN. The pre-wave lanes did
    `"auction" if data.type == "auction" else "sale"`, so every typo -- and the
    Spanish word for auction -- silently became a direct sale."""
    t = str(raw or "").strip().lower()
    if t in ("sale", "venta"):
        return "sale"
    if t in ("auction", "subasta"):
        return "auction"
    raise HTTPException(status_code=400,
                        detail="Tipo de publicación no válido. Usa «venta» o «subasta».")


def _market_growth_gate_or_409(cfg, growth_exact) -> None:
    """THE 80% GATE, identical on the vault lane and the inventory lane and on
    both listing types. Unreadable growth is REFUSED, not admitted: a gate that
    passes on input it could not read is not a gate."""
    if _growth_gate_ok(cfg, growth_exact):
        return
    min_pct = _knob_refuse_int(cfg, "min_growth_pct", 0, 100)
    if growth_exact is None:
        raise HTTPException(status_code=409, detail=(
            "No pudimos leer el crecimiento de este dinosaurio, así que no se puede "
            "publicar. Avísale a un administrador."))
    have = _growth_pct_display(growth_exact)
    raise HTTPException(status_code=409, detail=(
        f"Solo puedes publicar dinosaurios con {min_pct}% de crecimiento o más. "
        f"Este tiene {have}%. Le faltan {max(0, min_pct - have)} puntos."))


async def _market_listing_cap_or_409(cfg, seller_id: str) -> None:
    cap = _knob_int(cfg, "max_listings_per_seller", 1, 25)
    live = await db.market.count_documents({"seller_id": seller_id, "status": "active"})
    if live >= cap:
        raise HTTPException(status_code=409, detail=(
            f"Ya tienes {cap} publicaciones activas. Retira una antes de publicar otra."))


def _market_price_or_400(raw, merit: dict) -> int:
    """THE SELLER'S OWN NUMBER, validated against the absolute bounds and then
    against this ANIMAL's rails.

    Order matters and it is what makes the refusal quote the constraint that
    actually bound: merit["min"] is max(abs_min, rail_lo) and merit["max"] is
    min(abs_max, rail_hi), so whenever the ABSOLUTE bound is the tighter one it
    has already fired above and the rail message cannot reach the player with a
    number that was not the real limit."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise HTTPException(status_code=400, detail=(
            f"Escribe un precio. El sugerido para este dinosaurio es "
            f"{_es_num(merit['suggested'])} PrimeMeat."))
    # `True` is an int in Python and would price an animal at 1. It is refused
    # as a TYPE, not read as a number. So are 5.5, "5000", NaN and inf.
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise HTTPException(status_code=400,
                            detail="El precio debe ser un número entero de PrimeMeat, sin decimales.")
    price = int(raw)
    if price < merit["abs_min"]:
        raise HTTPException(status_code=400, detail=(
            f"El precio mínimo del mercado es {_es_num(merit['abs_min'])} PrimeMeat."))
    if price > merit["abs_max"]:
        raise HTTPException(status_code=400, detail=(
            f"El precio máximo del mercado es {_es_num(merit['abs_max'])} PrimeMeat."))
    if price < merit["min"]:
        raise HTTPException(status_code=400, detail=(
            f"Pediste {_es_num(price)}. El mínimo para este dinosaurio es "
            f"{_es_num(merit['min'])} — el {merit['floor_pct']}% de su valor de mercado de "
            f"{_es_num(merit['suggested'])}."))
    if price > merit["max"]:
        top = ("el triple" if merit["ceiling_pct"] == 300
               else f"el {merit['ceiling_pct']}%")
        raise HTTPException(status_code=400, detail=(
            f"Pediste {_es_num(price)}. El máximo para este dinosaurio es "
            f"{_es_num(merit['max'])} — {top} de su valor de mercado de "
            f"{_es_num(merit['suggested'])}."))
    return price


def _market_title_or_400(typed, *fallbacks) -> str:
    """The listing title, sanitised. A title the seller TYPED that sanitises
    away is a refusal, never a silent substitution of the species name -- the
    seller must know their text did not survive."""
    raw = str(typed or "")
    if raw.strip():
        clean = _market_clean_title(raw)
        if not clean:
            raise HTTPException(status_code=400,
                                detail="El nombre de la publicación no puede quedar vacío.")
        return clean
    for fb in fallbacks:
        clean = _market_clean_title(fb)
        if clean:
            return clean
    raise HTTPException(status_code=400,
                        detail="El nombre de la publicación no puede quedar vacío.")


# ---------- per-writer rate limit ----------
# In-process on purpose: a rate limiter that forgets on restart under-blocks
# for one minute and costs nobody an animal, which is the opposite of a
# COOLDOWN (a cooldown that forgets is a free extra turn, so those live in
# Mongo). Bounded: entries older than the window are pruned on every call and
# the map itself is capped.
MARKET_WRITE_WINDOW_SECS = 60.0
_market_write_hits: dict = {}
_MARKET_WRITE_MAP_CAP = 5000


def _market_write_gate(cfg, user_id: str) -> None:
    limit = _knob_int(cfg, "write_rate_per_min", 1, 120)
    now = time.time()
    cutoff = now - MARKET_WRITE_WINDOW_SECS
    hits = [t for t in _market_write_hits.get(str(user_id), ()) if t > cutoff]
    if len(hits) >= limit:
        wait = max(1, int(math.ceil(hits[0] + MARKET_WRITE_WINDOW_SECS - now)))
        _market_write_hits[str(user_id)] = hits
        raise HTTPException(status_code=429,
                            detail=f"Demasiadas acciones seguidas. Espera {wait} segundos.")
    hits.append(now)
    _market_write_hits[str(user_id)] = hits
    if len(_market_write_hits) > _MARKET_WRITE_MAP_CAP:
        for k in [k for k, v in _market_write_hits.items() if not v or v[-1] <= cutoff]:
            _market_write_hits.pop(k, None)


# =============================================================================
# THE FRONTEND CONTRACT, MADE REAL  (2026-08-11)
# =============================================================================
# The shipped page posts `expected_price` and `client_request_id` on buy, bid,
# withdraw and list. The backend implemented NEITHER, and because pydantic
# silently drops fields a model does not declare, nothing errored -- the page
# simply BELIEVED it had stale-price protection and replay protection that did
# not exist. A protection a caller believes in and does not have is worse than
# no protection at all, because it is the reason nobody looks again.
#
# `expected_price` -- the buyer/bidder sends the number they were SHOWN. Strict
# equality: a HIGHER expectation is refused too, because that is a stale page as
# well. Canonical shape: webcore/routes/auction.py place_bid().
#
# `client_request_id` -- one id per ATTEMPT. A replay of the same id returns the
# STORED outcome (including a stored refusal); a NEW id is a new attempt and is
# allowed. The ref carries the attempt id precisely so that a legitimately
# reversed attempt does not brick that player's retry forever, and the key is
# never cleared in a catch block -- a guard must not be disabled by exactly the
# failure it was built for.
MARKET_REQUEST_ID_MAX = 80
# A claim whose process died sits in `claimed` forever and would 409 that
# player's honest retry for good. After this long an unfinished claim may be
# taken over, exactly as /store/checkout re-claims a stale order key.
MARKET_OP_STALE_SECS = 300.0


def _client_request_id(raw, *, required: bool = False) -> str:
    """The attempt id, validated. Absent is allowed by default: the previous
    frontend sent no body at all and must keep working, and the claim
    (active->selling) is still the race wall on its own. What is NOT allowed is
    a shape we cannot key on -- that would silently disable the wall."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if required:
            raise HTTPException(status_code=400,
                                detail="Falta el identificador de la petición. Actualiza la página.")
        return ""
    if isinstance(raw, bool) or not isinstance(raw, str):
        raise HTTPException(status_code=400,
                            detail="El identificador de la petición no es válido. Actualiza la página.")
    rid = raw.strip()
    if len(rid) > MARKET_REQUEST_ID_MAX or not rid.isprintable():
        raise HTTPException(status_code=400,
                            detail="El identificador de la petición no es válido. Actualiza la página.")
    return rid


def _expected_price_or_409(expected, actual: int, *, lane: str) -> None:
    """THE STALE-CLICK REFUSAL. Strict equality against what the row says NOW.

    Absent is allowed (the pre-wave frontend sends no body); a value of the
    wrong TYPE is not, because `True == 1` would let a boolean pass as a price
    of one coin. A mismatch in EITHER direction is a stale page."""
    if expected is None:
        return
    if isinstance(expected, bool) or not isinstance(expected, int):
        raise HTTPException(status_code=400,
                            detail="El precio esperado debe ser un número entero de PrimeMeat.")
    if int(expected) == int(actual):
        return
    if lane == "auction":
        raise HTTPException(status_code=409, detail=(
            f"Alguien pujó justo ahora — la puja mínima es {_es_num(actual)} PrimeMeat. "
            f"Vuelve a pujar si todavía lo quieres."))
    raise HTTPException(status_code=409, detail=(
        f"El precio cambió: ahora es {_es_num(actual)} PrimeMeat. Actualiza la página."))


def _market_op_ref(kind: str, user_id: str, request_id: str) -> str:
    """The idempotency key. OWNER-SCOPED BY CONSTRUCTION: the user id is part of
    the ref, so two players who happen to mint the same uuid can never see each
    other's receipt and neither is refused because of the other. `_id` IS the
    ref, so uniqueness is Mongo's own primary key rather than an index somebody
    has to remember to create on a fresh database."""
    return "lin:market:%s:%s:%s" % (kind, user_id, request_id)


class _MarketOpReplay(Exception):
    """Internal: this attempt already has an outcome. Carries it."""

    def __init__(self, row: dict):
        super().__init__("replay")
        self.row = row or {}


async def _market_op_lookup(kind: str, user_id: str, request_id: str, scope: str):
    """Read-only replay check, run BEFORE the row is even looked up.

    It has to be first: a completed buy leaves the listing `sold`, so a genuine
    replay would otherwise be told "someone else bought it" -- a support ticket
    manufactured out of a correct refusal.

    A reused id pointing at a DIFFERENT listing is refused outright. That is a
    client bug, and the only safe answer to "the same attempt, somewhere else"
    is to do nothing at all."""
    if not request_id:
        return None
    ref = _market_op_ref(kind, user_id, request_id)
    try:
        row = await db.market_ops.find_one({"_id": ref})
    except Exception:
        logger.exception("[MARKETOP] lookup failed ref=%s", ref)
        return None
    if not row:
        return None
    if str(row.get("scope") or "") != str(scope):
        raise HTTPException(status_code=409, detail=(
            "Esa acción ya se usó para otra publicación. Actualiza la página."))
    state = str(row.get("state") or "")
    if state in ("done", "reversed"):
        raise _MarketOpReplay(row)
    if float(row.get("at") or 0) > (time.time() - MARKET_OP_STALE_SECS):
        raise HTTPException(status_code=409, detail=(
            "Esa petición todavía se está procesando. Espera un momento."))
    return row                      # stale claim: the caller may take it over


async def _market_op_claim(kind: str, user_id: str, request_id: str, scope: str,
                           amount: int = 0) -> str:
    """CLAIM the attempt before any money moves. The insert IS the race wall --
    of two simultaneous submissions exactly one can create the `_id`.

    Returns the ref, or "" when the caller sent no id (nothing to key on; the
    listing claim remains the wall for that older client)."""
    if not request_id:
        return ""
    ref = _market_op_ref(kind, user_id, request_id)
    now_ts = time.time()
    try:
        await db.market_ops.insert_one({
            "_id": ref, "user_id": str(user_id), "kind": str(kind),
            "scope": str(scope), "request_id": str(request_id),
            "state": "claimed", "amount": int(amount or 0), "result": None,
            "at": now_ts, "ts": now_iso()})
        return ref
    except DuplicateKeyError:
        pass
    except Exception:
        # Mongo is unhappy. A missing idempotency claim is not a reason to
        # refuse a player's money action outright -- the atomic listing claim is
        # still in force -- but it IS worth shouting about.
        logger.exception("[MARKETOP] claim insert failed ref=%s", ref)
        return ""
    row = await db.market_ops.find_one({"_id": ref})
    if row and str(row.get("state")) in ("done", "reversed"):
        raise _MarketOpReplay(row)
    # A claim that is still open: take it over only if it is stale, and only
    # through a conditional update, so of two racers exactly one wins.
    took = await db.market_ops.find_one_and_update(
        {"_id": ref, "state": "claimed", "at": {"$lt": now_ts - MARKET_OP_STALE_SECS}},
        {"$set": {"at": now_ts, "scope": str(scope), "amount": int(amount or 0)}})
    if took:
        logger.warning("[MARKETOP] re-claimed a stale attempt ref=%s", ref)
        return ref
    raise HTTPException(status_code=409, detail=(
        "Esa petición todavía se está procesando. Espera un momento."))


async def _market_op_done(ref: str, result: dict) -> None:
    """Store the outcome a replay will be answered with."""
    if not ref:
        return
    try:
        await db.market_ops.update_one({"_id": ref}, {"$set": {
            "state": "done", "result": result, "done_at": now_iso()}})
    except Exception:
        logger.exception("[MARKETOP] could not store the result ref=%s", ref)


async def _market_op_reversed(ref: str, exc: HTTPException) -> None:
    """Store a REFUSAL as the outcome. A replay of this exact attempt must be
    refused the same way rather than trying again -- the retry lane is a NEW
    attempt id, which the caller mints as soon as it has a definite answer."""
    if not ref:
        return
    try:
        await db.market_ops.update_one({"_id": ref}, {"$set": {
            "state": "reversed", "status_code": int(getattr(exc, "status_code", 400)),
            "detail": str(getattr(exc, "detail", "")), "done_at": now_iso()}})
    except Exception:
        logger.exception("[MARKETOP] could not store the refusal ref=%s", ref)


async def _market_op_answer(replay: "_MarketOpReplay", user_id: str) -> dict:
    """Answer a replay in the route's own shape. The stored result is replayed
    verbatim EXCEPT the balance, which is re-read live -- a receipt is a record
    of what happened, but a balance is a fact about right now."""
    row = replay.row
    if str(row.get("state")) == "reversed":
        raise HTTPException(status_code=int(row.get("status_code") or 409),
                            detail=str(row.get("detail") or "Esa petición ya fue rechazada."))
    result = dict(row.get("result") or {})
    fresh = await db.users.find_one({"id": user_id}, {"_id": 0}) or {}
    if "balance" in result or not result:
        result["balance"] = {"coins": fresh.get("coins", 0),
                             "vip_coins": fresh.get("vip_coins", 0)}
    result["replayed"] = True
    logger.info("[MARKETOP] replay answered ref=%s kind=%s user=%s",
                row.get("_id"), row.get("kind"), user_id)
    return result


async def _market_op_peek(kind: str, user, request_id: str, scope: str):
    """The read-only half, as a value: a ready-to-return replay answer, or None.

    Run BEFORE the listing is looked up, so a replay of a COMPLETED buy is
    answered with its own receipt instead of "someone else bought it"."""
    try:
        await _market_op_lookup(kind, user["id"], request_id, scope)
    except _MarketOpReplay as replay:
        return await _market_op_answer(replay, user["id"])
    return None


async def _market_op_take(kind: str, user, request_id: str, scope: str, amount: int = 0):
    """The claiming half. Returns (ref, answer): a non-None `answer` is a replay
    that the caller returns immediately, having moved nothing."""
    try:
        ref = await _market_op_claim(kind, user["id"], request_id, scope, amount)
    except _MarketOpReplay as replay:
        return "", await _market_op_answer(replay, user["id"])
    return ref, None


# =============================================================================
# THE PER-ANIMAL MOVE COOLDOWN  (2026-08-11)
# =============================================================================
# One animal may change hands once per `dino_move_cooldown_secs`. Without it the
# market is an UNCOOLED laundering lane sitting beside a cooled trade lane, and
# the trade cooldown is decorative.
#
# ★ THE TRAP, VERIFIED: `vault.save_parked` returns `int(cur.lastrowid)` -- A
# NEW ROW ID ON EVERY DELIVERY. An id-keyed cooldown is worthless the instant
# the animal moves, which is the only instant it exists to govern. So TWO keys
# are written and BOTH are checked:
#   row:<new_parked_id>   written AFTER delivery from save_parked's own return
#                         value. Precise, and it is the key the seller's next
#                         list attempt looks up first.
#   fp:<owner_sid>:<hash> written BEFORE the move, off the payload. Survives the
#                         id change. Hashes dino_class|skin_code|mutations|
#                         parent_mutations|elder_mutations|elder_stacks|is_prime
#                         -- deliberately NOT growth or custom name, which change
#                         in ordinary play and would make the key evaporate.
#
# NAMED RESIDUAL HOLE: a launderer redeems the animal, re-skins it at the
# customizer (a real coin cost) and re-parks it -- both keys are then clear, at
# the price of a full in-game round trip plus PARK_COOLDOWN_SECS plus a skin
# purchase, per animal.
# NAMED FALSE POSITIVE, and it is the SAFE direction: the fingerprint is
# owner-scoped, so a player who owns two IDENTICAL animals has both blocked when
# one of them moves. It over-blocks, never under-blocks, and the refusal says so.
MOVE_COOLDOWN_FP_COLS = ("dino_class", "skin_code", "mutations", "parent_mutations",
                         "elder_mutations", "elder_stacks", "is_prime")


def _dino_fingerprint(payload: dict) -> str:
    """Content identity of one animal, owner-independent half."""
    parts = []
    for col in MOVE_COOLDOWN_FP_COLS:
        val = (payload or {}).get(col)
        parts.append("" if val is None else str(val))
    return hashlib.sha1("|".join(parts).encode("utf-8", "replace")).hexdigest()


def _move_cooldown_keys(steam_id, payload: dict, row_id=None) -> list:
    """Both keys for one animal in one owner's hands."""
    keys = []
    if row_id is not None:
        try:
            keys.append("row:%d" % int(row_id))
        except (TypeError, ValueError):
            pass
    sid = str(steam_id or "").strip()
    if sid and payload:
        keys.append("fp:%s:%s" % (sid, _dino_fingerprint(payload)))
    return keys


def _move_cooldown_secs(cfg) -> int:
    """REFUSE, and 0 DISABLES -- his own re-enable contract from the 2026-07-16
    vault-cooldown removal. A knob nobody can turn off is a knob that gets
    turned off by editing code."""
    return _knob_refuse_int(cfg, "dino_move_cooldown_secs", 0, 604_800,
                            label="La espera entre movimientos está mal configurada")


def _wait_es(secs: int) -> str:
    """A wait, the way his players read it: «18 h», «45 min», «30 s»."""
    secs = max(0, int(secs))
    if secs >= 3600:
        hours = secs // 3600
        mins = (secs % 3600) // 60
        return f"{hours} h" if not mins else f"{hours} h {mins} min"
    if secs >= 60:
        return f"{secs // 60} min"
    return f"{secs} s"


async def _move_cooldown_state(cfg, steam_id, payload: dict, row_id=None) -> dict | None:
    """The blocking cooldown row for this animal, or None when it may move.

    FAILS OPEN on unreadable data and on a Mongo failure, and says so loudly.
    That direction is deliberate and it is the opposite of the growth gate: a
    jammed COOLDOWN is a permanent lockout of a player's own property, while a
    jammed GATE only lets one listing through. Same file, opposite defaults, and
    both are chosen rather than inherited."""
    if _move_cooldown_secs(cfg) <= 0:
        return None
    keys = _move_cooldown_keys(steam_id, payload, row_id)
    if not keys:
        return None
    now = time.time()
    try:
        rows = await db.dino_move_cooldowns.find({"_id": {"$in": keys}}).to_list(len(keys))
    except Exception:
        logger.exception("[MARKET] move-cooldown read failed - failing OPEN for keys=%s", keys)
        return None
    best = None
    for r in rows or []:
        try:
            until = float(r.get("until"))
        except (TypeError, ValueError):
            _market_warn_once("cooldownjunk:" + str(r.get("_id")),
                              "[MARKET] move cooldown %s has an unreadable `until`=%r - "
                              "failing OPEN", r.get("_id"), r.get("until"))
            continue
        # AT THE EXPIRY INSTANT THE COOLDOWN IS OVER: `until <= now` releases.
        # Written as a strict > so the boundary belongs to the player.
        if until > now and (best is None or until > best["until"]):
            best = {"until": until, "at": float(r.get("at") or 0), "key": r.get("_id"),
                    "why": r.get("why")}
    return best


async def _move_cooldown_or_429(cfg, steam_id, payload: dict, row_id=None) -> None:
    """The refusal, with BOTH numbers his copy asks for: how long ago the animal
    moved and how long is left."""
    state = await _move_cooldown_state(cfg, steam_id, payload, row_id)
    if not state:
        return
    now = time.time()
    total = _move_cooldown_secs(cfg)
    left = max(1, int(math.ceil(state["until"] - now)))
    since = state["at"] and max(0, int(now - state["at"])) or max(0, total - left)
    raise HTTPException(status_code=429, detail=(
        f"Este dinosaurio cambió de dueño hace {_wait_es(since)}. Cada dinosaurio "
        f"puede moverse una vez cada {_wait_es(total)} — faltan {_wait_es(left)}."))


async def _move_cooldown_stamp(cfg, steam_id, payload: dict, row_id=None,
                               why: str = "market_sale") -> None:
    """Write the clock. Contained: a cooldown that could not be written is a
    logged fact, never a failed sale -- the animal has already moved by the time
    this runs and raising here would unwind a completed delivery.

    NOT a Mongo TTL index, on purpose. A background TTL reaper delayed by a
    restart would silently SHORTEN a cooldown; every check compares `until`
    against `now` itself, so an unswept row is still enforced and a swept one is
    already expired."""
    try:
        secs = _move_cooldown_secs(cfg)
    except HTTPException:
        # A broken knob must not strand a delivered animal. Log and move on:
        # the check side refuses new listings loudly on the same broken knob.
        logger.exception("[MARKET] move-cooldown knob is broken - NOT stamping %s", why)
        return
    if secs <= 0:
        return
    keys = _move_cooldown_keys(steam_id, payload, row_id)
    if not keys:
        return
    now = time.time()
    for key in keys:
        try:
            await db.dino_move_cooldowns.update_one(
                {"_id": key},
                {"$set": {"until": now + secs, "at": now, "why": str(why),
                          "ts": now_iso()}},
                upsert=True)
        except Exception:
            logger.exception("[MARKET] could not stamp move cooldown key=%s", key)
    logger.info("[MARKET] move cooldown stamped why=%s secs=%s keys=%s", why, secs, keys)


async def _stamp_sale_cooldown(cfg, buyer_id: str, l: dict, out: dict | None) -> None:
    """Both halves of the clock for ONE completed market sale.

    The fingerprint key is written from the payload and the buyer's steam id --
    it does not need the delivery to have happened. The row key needs
    save_parked's return value, which is why `_give_dino` hands it back through
    `out`; if the delivery lane did not report one (an inventory-sourced
    listing, or an older caller) only the content key is written, and that is
    stated rather than silently skipped."""
    try:
        if not _knob_bool(cfg, "dino_move_cooldown_on_sale"):
            return
        if l.get("source") != "vault":
            # An inventory dino is a website abstraction: `_give_dino` mints a
            # brand-new inventory doc with a fresh uuid and there is no
            # steam-scoped content identity to key on. Stated here rather than
            # pretended: this lane is NOT cooled.
            return
        payload = l.get("vault_payload") or {}
        u = await db.users.find_one({"id": buyer_id}, {"_id": 0}) or {}
        sid = str(u.get("steam_id") or "").strip()
        if not sid:
            return
        await _move_cooldown_stamp(cfg, sid, payload, (out or {}).get("new_row_id"),
                                   why="market_sale:%s" % l.get("id"))
    except Exception:
        logger.exception("[MARKET] sale cooldown stamp failed listing=%s", (l or {}).get("id"))


def _listing_rails_ok(cfg, l: dict) -> tuple[bool, str]:
    """Is the price the SELLER SET still legal under TODAY'S rails?

    A listing must not outlive the rule that allowed it: the owner can move
    `species_base`, `per_mutation_bonus` or either rail percentage at any time
    without a deploy, and a 72-hour listing can easily outlive that edit.

    Scope, deliberately: this bounds what a SELLER MAY ASK, so it is checked
    where NEW money enters against that ask -- a direct-sale buy, and a bid on
    an auction whose opening ask is now illegal. It is NOT enforced at
    settlement. A hammer price is what the ROOM paid, not a number the seller
    typed, and refusing a settle would unwind an escrowed winner over a knob
    edit they had no part in.

    Rows written before this wave carry no `price_source` and skip the check:
    they were legal under the rule they were born under, and that rule is the
    deal their seller accepted. Returns (ok, reason)."""
    if str(l.get("price_source") or "") != "seller":
        return True, "legacy"
    try:
        price = int(l.get("price") or 0)
        muts = int(l.get("priced_mutations") or 0)
        merit = _merit(cfg, l.get("dino_slug") or "", muts)
    except HTTPException:
        # A broken REFUSE knob must not turn every listing on the board into a
        # refusal. The create lane already refuses NEW listings on it loudly.
        return True, "knob_broken"
    except (TypeError, ValueError, OverflowError):
        return True, "unreadable"
    if price < merit["min"]:
        return False, "below_%d" % merit["min"]
    if price > merit["max"]:
        return False, "above_%d" % merit["max"]
    return True, "ok"


def _rails_still_ok_or_409(cfg, l: dict) -> None:
    ok, why = _listing_rails_ok(cfg, l)
    if ok:
        if why == "legacy":
            logger.info("[MARKET] listing %s predates the rails - settling on the rule "
                        "it was born with", l.get("id"))
        return
    logger.warning("[MARKET] listing %s no longer meets today's rails (%s) - refusing "
                   "new money against it", l.get("id"), why)
    raise HTTPException(status_code=409,
                        detail="Esa publicación ya no cumple las reglas del mercado.")


def _same_person(a: dict, b: dict) -> bool:
    """TWO IDENTITIES, not one. LIN has no `discord_id` uniqueness, so one human
    already holds several site accounts -- but a steam id is a paid, single
    account, and a seller and a buyer sharing one are the same person whatever
    their user ids say. Alt shill-bidding your own auction is the canonical
    auction attack and the pre-wave check tested `user["id"]` alone."""
    if not a or not b:
        return False
    if a.get("id") and a.get("id") == b.get("id"):
        return True
    sa = str(a.get("steam_id") or "").strip()
    sb = str(b.get("steam_id") or "").strip()
    return bool(sa) and sa == sb


def _tier_mut_cap(tier):
    return MARKET_TIER_MUT_CAP.get(tier, MAX_MUTATION_SLOTS)


# slug -> bare species name == the /dino-assets/<species>/ directory, so listing
# cards can render the same live 3D model the vault cards use.
_MARKET_SLUG_TO_SPECIES = {v: k for k, v in game_telemetry.EVRIMA_SPECIES.items()}


def _market_verify_view(vp: dict) -> dict | None:
    """Buyer-inspection view of a vault-sourced listing: the SAME stored facts
    the seller's own Bóveda preview renders (mutation slots, elder sets, diet,
    vitals), derived from the escrowed payload so what the buyer verifies is
    exactly what gets delivered. Seller-private fields (ids, position, raw skin
    code) never leave. Returns None when the payload can't be shaped — the
    frontend then simply hides the inspector."""
    try:
        v = vault._dino_view(dict(vp))
    except Exception:
        return None
    for k in ("id", "parked_at", "redeem_pending"):
        v.pop(k, None)
    return v


def _market_public(l: dict, cfg: dict | None = None) -> dict:
    """The buyer's view of one listing.

    LIVE DEFECT CLOSED 2026-08-11: `mutations_count` was
    `vault._mutation_count(vp.get("mutations"))` -- the ACTIVE column ONLY. The
    widest real animal on the server is a Deinosuchus with 4 active + 8 elder =
    12 and it advertised "4 mutaciones" on its card and in the buyer's
    inspector; 410 of 2,878 parked rows (14.2%) carry elder mutations and every
    one of them was under-advertised. The count the buyer READS and the count
    the price is BUILT FROM now come from ONE helper, `_priced_mut_count`,
    which is the only construction under which they cannot diverge."""
    d = {k: l.get(k) for k in (
        "id", "seller_name", "dino_slug", "dino_name", "image", "rarity", "type",
        "price", "current_bid", "current_bidder_name", "ends_at", "status", "created_at",
        "title", "growth", "tier", "prime", "skin", "skin_image", "source")}
    d["prime"] = bool(l.get("prime")) or l.get("tier") == "prime"
    d["mutations"] = [MUTATIONS_BY_KEY[m]["name"] for m in l.get("mutations", []) if m in MUTATIONS_BY_KEY]
    # Vault-card parity fields. vault_payload is the opaque parked row snapshot;
    # only derived display values leave this function, never the payload itself.
    d["species"] = _MARKET_SLUG_TO_SPECIES.get(str(l.get("dino_slug") or ""))
    vp = l.get("vault_payload") or {}
    if cfg is None:
        cfg = _market_defaults()
    if l.get("source") == "vault":
        d["is_elder"] = bool(vp.get("is_elder"))
        d["priced_mutations"] = _priced_mut_count(cfg, vault_row=vp)
        d["skin_view"] = vault._parked_skin(vp.get("skin_data"))
        d["verify"] = _market_verify_view(vp)
    else:
        d["is_elder"] = False
        d["priced_mutations"] = _priced_mut_count(cfg, inv_item={
            "id": l.get("id"), "mutations": l.get("mutations") or [],
            "mutation_groups": l.get("mutation_groups")})
        d["skin_view"] = None
        d["verify"] = None
    # ONE number, published under both names. `mutations_count` is the key the
    # shipped frontend already renders; `priced_mutations` is the name the
    # pricing payload uses. They are the same integer by construction.
    d["mutations_count"] = d["priced_mutations"]
    # Growth, FLOORED -- the same floor the gate pairs with, so a card can never
    # advertise 80% for an animal the sell lane refuses. Pre-wave rows carry a
    # ROUNDED `growth` and no exact value; they are grandfathered and render it.
    if l.get("growth_pct_exact") is not None:
        d["growth_pct"] = _growth_pct_display(l.get("growth_pct_exact"))
    else:
        try:
            d["growth_pct"] = int(math.floor(float(l.get("growth") or 0)))
        except (TypeError, ValueError, OverflowError):
            d["growth_pct"] = 0
    # THE SNAPSHOT, never the knob: a bidder with money in escrow must be able
    # to reach their auction even while the owner has the tax knob broken, so
    # nothing on this path reads a REFUSE knob for the fee.
    d["tax_pct"] = _listing_tax_pct(l)
    d["price_source"] = l.get("price_source") or "legacy"
    # What the seller's own listing row recorded at list time. Absent on the 38
    # grandfathered listings, which is the honest answer for a row created
    # before the rule existed -- never a fabricated zero.
    for k in ("suggested_price", "species_base", "base_source", "price_min", "price_max"):
        d[k] = l.get(k)
    # The rails as they stand TODAY for this animal, so the page can show a
    # buyer what the market thinks it is worth. Wrapped: a broken REFUSE knob
    # must not take the board down while auctions are live.
    try:
        d["merit"] = _merit(cfg, l.get("dino_slug") or "", d["priced_mutations"])
        d["merit_error"] = None
    except HTTPException as exc:
        d["merit"] = None
        d["merit_error"] = exc.detail
    # Every rule the page renders comes from THIS payload. All of it is read
    # through CLAMP readers, which never raise, so a broken REFUSE knob can
    # never take the board down while bidders have money in escrow.
    d["sale_durations_h"] = _duration_tiers(cfg, "sale")
    d["auction_durations_h"] = _duration_tiers(cfg, "auction")
    try:
        d["withdraw_fee_flat"] = _withdraw_fee(cfg)
    except HTTPException:
        # Published as null rather than as the default: a seller must not be
        # shown a fee the route would refuse to charge.
        d["withdraw_fee_flat"] = None
    # The minimum this server will actually accept as the next bid, computed by
    # the SAME expression market_bid enforces. A page that pins its own copy of
    # a rule is a page that will one day disagree with the server about it.
    if l.get("type") == "auction":
        try:
            current = int(l.get("current_bid") or 0)
        except (TypeError, ValueError, OverflowError):
            current = 0
        d["min_next_bid"] = _min_next_bid(cfg, l)
        d["bid_step"] = _bid_step(cfg, current) if current > 0 else 0
        d["bid_max"] = _bid_max(cfg)
        d["antisnipe_secs"] = _knob_int(cfg, "antisnipe_secs", 0, 3600)
        d["antisnipe_max_total_secs"] = _knob_int(cfg, "antisnipe_max_total_secs", 0, 86400)
        try:
            d["extended_secs"] = max(0, int(l.get("extended_secs") or 0))
        except (TypeError, ValueError, OverflowError):
            d["extended_secs"] = 0
    else:
        d["min_next_bid"] = None
        d["bid_step"] = None
        d["bid_max"] = None
        d["antisnipe_secs"] = None
        d["antisnipe_max_total_secs"] = None
        d["extended_secs"] = 0
    return d


def _listing_ends_at(l: dict):
    """The listing's end instant as an aware datetime, or None when it has no
    readable clock. A naive stored string is read as UTC rather than raised on
    -- comparing naive to aware is the TypeError that used to abort a whole
    settle pass."""
    raw = l.get("ends_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def _market_gone_refusal(listing_id: str, lane: str) -> HTTPException:
    """The listing was not `active` when we looked. Say WHICH thing happened.

    The settle pass now runs at the top of buy and bid, so the most common
    reason a listing is missing from `active` is that this very request just
    expired it -- and telling that player "someone already bought it" is a
    support ticket built out of a correct refusal."""
    gone = await db.market.find_one({"id": listing_id}, {"_id": 0, "status": 1})
    status = (gone or {}).get("status")
    if status in ("expired", "resolving", "needs_admin"):
        return HTTPException(status_code=409, detail=(
            "Esa subasta acaba de terminar." if lane == "auction"
            else "Esa publicación acaba de expirar."))
    if status in ("sold", "selling"):
        return HTTPException(status_code=404, detail=(
            "Esa subasta ya terminó." if lane == "auction"
            else "Ese dinosaurio ya fue comprado. Actualiza el mercado."))
    return HTTPException(status_code=404, detail=(
        "Esa subasta ya no está disponible." if lane == "auction"
        else "Esa publicación ya no está disponible."))


def _listing_has_ended(l: dict, now=None) -> bool:
    """THE CLOCK IS THE LAW AT REQUEST TIME. LIN has no sweeper -- settlement is
    lazy on reads -- so before this wave an ended auction stayed `active` until
    somebody happened to load a page, and market_buy / market_bid (which are in
    NEITHER caller list) accepted money against it. A listing with no readable
    clock has not ended; the settle pass marks that row needs_admin instead."""
    dt = _listing_ends_at(l)
    if dt is None:
        return False
    return dt <= (now or datetime.now(timezone.utc))


async def _settle_listing_row(l: dict, now) -> None:
    """Settle ONE claimed (status == "resolving") listing. RESUMABLE.

    Every step that moves an animal or a coin is bracketed by a marker written
    to the listing row: the INTENT marker before, the DONE marker after. A
    process bounce between the two leaves a row whose markers say "we do not
    know", and the reaper sends exactly those rows to needs_admin instead of
    guessing -- guessing costs either a duplicated animal or a minted refund.
    Rows whose markers say nothing moved are simply re-settled."""
    lid = l["id"]
    is_vault = l.get("source") == "vault"

    async def mark(**fields):
        await db.market.update_one({"id": lid}, {"$set": fields})

    if _listing_ends_at(l) is None:
        # A malformed ends_at is what used to raise inside the loop and kill
        # every sibling settlement in the same pass. It is a data fault, not a
        # player action: park it where a human can see it.
        await mark(status="needs_admin", resolve_note="unreadable_ends_at")
        logger.warning("market listing %s has an unreadable ends_at=%r", lid, l.get("ends_at"))
        return

    if l.get("type") == "auction" and l.get("current_bidder_id"):
        buyer_id = l["current_bidder_id"]
        bid = int(l.get("current_bid") or 0)
        if not l.get("resolve_delivered_at"):
            if l.get("resolve_delivering_at"):
                await mark(status="needs_admin", resolve_note="delivery_outcome_unknown")
                logger.error("market listing %s: crashed mid-delivery, outcome unknown - "
                             "needs_admin (buyer=%s bid=%s)", lid, buyer_id, bid)
                return
            await mark(resolve_delivering_at=now_iso())
            gave: dict = {}
            ok = (not is_vault) or (await _vault_delivery_ready(l, buyer_id)
                                    and await _give_dino(buyer_id, l, out=gave))
            if not ok:
                # Winner cannot receive (vault full / delivery race). The auction
                # has ENDED and the winner's bid is already escrowed, so we must
                # NOT loop forever or pay the seller for an undelivered dino:
                # refund the winner and return the dino to the seller. If the
                # seller also can't receive, flag for admin (payload retained in
                # the listing) rather than stranding coins or the dino.
                # WHAT WAS TAKEN, not what was bid -- the same law the outbid
                # refund follows, because this is the same escrow.
                back = _bid_charged(l)
                await db.users.update_one({"id": buyer_id}, {"$inc": {"coins": back}})
                await add_transaction(buyer_id, "normal", back, "refund", f"Subasta no entregable (bóveda llena): {l['dino_name']}")
                if l.get("seller_id") and await _vault_delivery_ready(l, l["seller_id"]) and await _give_dino(l["seller_id"], l):
                    await mark(status="expired", resolve_note="winner_vault_full_returned_to_seller",
                               resolve_delivering_at=None)
                else:
                    await mark(status="needs_admin", resolve_note="winner_and_seller_vault_full",
                               resolve_delivering_at=None)
                    logger.warning("market auction %s undeliverable: winner and seller vault both full", lid)
                return
            if not is_vault:
                await _give_dino(buyer_id, l)
            await mark(resolve_delivered_at=now_iso())
            # THE ANIMAL CHANGED HANDS: start its clock. Stamped here rather
            # than at "sold" so a crash before the seller credit still leaves
            # the cooldown written -- over-blocking is the safe direction.
            await _stamp_sale_cooldown(await _mcfg(), buyer_id, l, gave)
        # Delivered. Pay the seller off the SNAPSHOTTED percent, integer floor.
        if l.get("seller_id") and not l.get("seller_paid_at"):
            if l.get("seller_paying_at"):
                await mark(status="needs_admin", resolve_note="seller_credit_outcome_unknown")
                logger.error("market listing %s: crashed mid seller-credit, outcome unknown", lid)
                return
            pct = _listing_tax_pct(l)
            tax = _tax_on(bid, pct)
            net = bid - tax
            await mark(seller_paying_at=now_iso(), sale_tax=tax, sale_net=net, tax_pct_charged=pct)
            await db.users.update_one({"id": l["seller_id"]}, {"$inc": {"coins": net}})
            await add_transaction(l["seller_id"], "normal", net, "earn",
                                  f"Subasta vendida (−{pct}% de comisión): {l['dino_name']}")
            await mark(seller_paid_at=now_iso())
        await mark(status="sold", buyer_id=buyer_id, buyer_name=l.get("current_bidder_name"),
                   sold_price=bid, sold_at=now_iso())
        return

    # sale expired, or auction with no bids -- return the dino to the seller
    if l.get("seller_id") and not l.get("resolve_delivered_at"):
        if l.get("resolve_delivering_at"):
            await mark(status="needs_admin", resolve_note="return_outcome_unknown")
            logger.error("market listing %s: crashed mid seller-return, outcome unknown", lid)
            return
        if is_vault:
            await mark(resolve_delivering_at=now_iso())
            if not await _vault_delivery_ready(l, l["seller_id"]) or not await _give_dino(l["seller_id"], l):
                # seller can't receive yet -> revert to active, retry next pass.
                # Nothing moved, so the intent marker is cleared with it.
                await mark(status="active", resolve_delivering_at=None, claimed_at=None)
                return
        else:
            await mark(resolve_delivering_at=now_iso())
            await _give_dino(l["seller_id"], l)
        await mark(resolve_delivered_at=now_iso())
    await db.market.update_one({"id": lid}, {"$set": {"status": "expired", "expired_at": now_iso()}})


async def _resolve_listings():
    """Lazy settlement, run on every market read. CONTAINED: before this wave
    one raising row -- a malformed ends_at into datetime.fromisoformat, a
    _give_dino throw -- aborted the whole pass and killed every sibling
    settlement in it. Now every row is settled inside its own try/except, a
    failure is logged on EVERY pass and counted, and the siblings still land."""
    now = datetime.now(timezone.utc)
    failed = 0
    try:
        expired = await db.market.find({"status": "active", "ends_at": {"$ne": None}}).to_list(500)
    except Exception:
        logger.exception("[MARKET] settle pass could not read active listings")
        return
    for l in expired:
        try:
            ends = _listing_ends_at(l)
            if ends is not None and ends > now:
                continue
            # ends is None here means an UNREADABLE clock, not "no clock": the
            # query already filtered ends_at != null. Those rows are claimed and
            # parked as needs_admin by _settle_listing_row rather than skipped,
            # because a row nobody can date is a row that never leaves the board.
            # ATOMIC CLAIM: _resolve_listings runs on every market read, so two
            # concurrent callers both see this listing "active". Flip active->resolving
            # so only one caller settles it -- otherwise a vault dino is delivered
            # twice and/or the seller is paid twice for one sale. `claimed_at` is
            # what lets the reaper find a claim stranded by a process bounce.
            claimed = await db.market.find_one_and_update(
                {"id": l["id"], "status": "active"},
                {"$set": {"status": "resolving", "claimed_at": time.time()}})
            if not claimed:
                continue
            await _settle_listing_row(l, now)
        except Exception:
            failed += 1
            logger.exception("[MARKET] settle FAILED for listing %s - siblings continue",
                             (l or {}).get("id"))
    if failed:
        logger.error("[MARKET] settle pass finished with %s failed listing(s)", failed)
    await _reap_stuck_listings()


# How long a claim may sit in selling/resolving before the reaper touches it.
# Comfortably longer than any single settle, short enough that a seller is not
# staring at a listing that market_mine (status:"active") cannot even show them.
MARKET_REAP_AFTER_SECS = 300.0
MARKET_REAP_EVERY_SECS = 60.0
_market_reap_last = 0.0


async def _reap_stuck_listings() -> None:
    """THE MISSING RECOVERY. `:9285` and `:9718` in the pre-wave file DO revert
    on their own failure paths -- the gap was never "nothing moves resolving
    back", it was that there is no TIME-BASED recovery for a claim stranded by
    a process bounce between the claim and any terminal write, and market_mine
    filters to status "active", so the seller cannot even SEE the stranded row.

    Rows claimed before this wave carry no `claimed_at` at all; they are by
    definition stranded from an older process, so they are swept too."""
    global _market_reap_last
    now = time.time()
    if (now - _market_reap_last) < MARKET_REAP_EVERY_SECS:
        return
    _market_reap_last = now
    cut = now - MARKET_REAP_AFTER_SECS
    try:
        stuck = await db.market.find({
            "status": {"$in": ["selling", "resolving"]},
            "$or": [{"claimed_at": {"$lt": cut}}, {"claimed_at": None},
                    {"claimed_at": {"$exists": False}}],
        }, {"_id": 0}).to_list(200)
    except Exception:
        logger.exception("[MARKET] reaper could not read stuck listings")
        return
    for l in stuck:
        try:
            lid = l.get("id")
            if l.get("status") == "selling":
                # market_buy's lane. The markers say exactly how far it got.
                if not l.get("charged_at"):
                    await db.market.update_one(
                        {"id": lid, "status": "selling"},
                        {"$set": {"status": "active", "claimed_at": None,
                                  "reap_note": "unclaimed_no_debit"}})
                    logger.warning("[MARKET] reap listing %s: claimed but never charged -> active", lid)
                elif l.get("delivered_at") and not l.get("seller_paid_at"):
                    await _finish_reaped_sale(l)
                elif not l.get("delivering_at"):
                    await _refund_reaped_buy(l, "charged_undelivered")
                else:
                    await db.market.update_one(
                        {"id": lid, "status": "selling"},
                        {"$set": {"status": "needs_admin",
                                  "reap_note": "delivery_outcome_unknown"}})
                    logger.error("[MARKET] reap listing %s: crashed mid-delivery, outcome "
                                 "unknown -> needs_admin", lid)
            else:
                # resolving: re-enter the single-row settle, which is itself
                # resumable off the same markers.
                logger.warning("[MARKET] reap listing %s: re-entering settle", lid)
                await _settle_listing_row(l, datetime.now(timezone.utc))
        except Exception:
            logger.exception("[MARKET] reap FAILED for listing %s", (l or {}).get("id"))


async def _finish_reaped_sale(l: dict) -> None:
    """A buy that delivered the animal and died before paying the seller.
    Finish it: the buyer has the dino and has been charged, so the only thing
    outstanding is the seller's money."""
    lid = l.get("id")
    price = int(l.get("charged_amount") or l.get("price") or 0)
    pct = _listing_tax_pct(l)
    tax = _tax_on(price, pct)
    net = price - tax
    if l.get("seller_id"):
        await db.market.update_one({"id": lid}, {"$set": {
            "seller_paying_at": now_iso(), "sale_tax": tax, "sale_net": net,
            "tax_pct_charged": pct}})
        await db.users.update_one({"id": l["seller_id"]}, {"$inc": {"coins": net}})
        await add_transaction(l["seller_id"], "normal", net, "earn",
                              f"Venta del mercado (−{pct}% de comisión): {l.get('dino_name')}")
        await db.market.update_one({"id": lid}, {"$set": {"seller_paid_at": now_iso()}})
    await db.market.update_one({"id": lid, "status": "selling"}, {"$set": {
        "status": "sold", "buyer_id": l.get("buy_user_id"), "sold_price": price,
        "sold_at": now_iso(), "reap_note": "completed_delivered_unpaid"}})
    logger.warning("[MARKET] reap listing %s: delivered but unpaid -> completed, seller +%s", lid, net)


async def _refund_reaped_buy(l: dict, note: str) -> None:
    """A buy that charged the buyer and died before delivery even started.
    Give the money back and put the listing back on the board."""
    lid = l.get("id")
    price = int(l.get("charged_amount") or 0)
    uid = l.get("buy_user_id")
    if uid and price > 0:
        await db.users.update_one({"id": uid}, {"$inc": {"coins": price}})
        await add_transaction(uid, "normal", price, "refund",
                              f"Reembolso de compra no completada: {l.get('dino_name')}")
    await db.market.update_one({"id": lid, "status": "selling"}, {"$set": {
        "status": "active", "claimed_at": None, "charged_at": None,
        "charged_amount": None, "buy_user_id": None, "reap_note": note}})
    logger.warning("[MARKET] reap listing %s: charged but undelivered -> refunded %s to %s, "
                   "listing back to active", lid, price, uid)


# backwards-compatible alias
_resolve_auctions = _resolve_listings


async def _vault_delivery_ready(l: dict, user_id: str) -> bool:
    """True when `user_id` has a free vault slot to receive listing `l`'s dino.
    Only meaningful for source=="vault" listings -- inventory delivery has no
    capacity limit and is always ready. Mirrors the SAME MAX_STORED_DINOS=10
    (LIN_PARK_CAP) semantics vault.py's own park flow enforces, via the same
    _user_park_cap() helper (admin bypass included)."""
    if l.get("source") != "vault":
        return True
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    sid = str((u or {}).get("steam_id") or "").strip()
    if not sid:
        return False
    cap = _user_park_cap(u or {})
    if cap <= 0:
        return True
    used = await asyncio.to_thread(vault.count_parked, sid)
    return used < cap


async def _give_dino(user_id, l, out: dict | None = None) -> bool:
    """Return/deliver the listed dino to user_id's account. Vault-sourced listings
    (l["source"]=="vault") restore a parked_dinos row via the SAME vault.save_parked()
    helper the park flow uses -- an opaque copy of l["vault_payload"], dup-safe,
    cap-checked. Callers MUST have already confirmed capacity via
    _vault_delivery_ready before moving any funds; this only performs the atomic
    insert and reports whether it landed (False on a rare cap race). Everything
    else delivers to the website inventory exactly as before (unconditional).

    `out` is an OPTIONAL write-back dict, added 2026-08-11 and nothing else about
    this function moved: the per-animal move cooldown has to be keyed on the id
    `vault.save_parked` just minted (it returns a NEW lastrowid on every
    delivery), and that id exists nowhere else. Callers that do not pass `out`
    are byte-for-byte unaffected; the ordering of the escrow lane is untouched."""
    if l.get("source") == "vault":
        payload = l.get("vault_payload") or {}
        u = await db.users.find_one({"id": user_id}, {"_id": 0}) or {}
        sid = str(u.get("steam_id") or "").strip()
        if not sid:
            return False
        cap = _user_park_cap(u)
        discord_id = await asyncio.to_thread(vault.resolve_discord_id, sid)
        new_row_id = await asyncio.to_thread(vault.save_parked, sid, discord_id, payload, cap)
        if out is not None:
            out["new_row_id"] = new_row_id
            out["steam_id"] = sid
        # CLOSE THE LEDGER. Every `list_removed` above is matched here by the
        # line that says where the animal went -- buyer, winner, or back to the
        # seller on withdraw/expiry. Without this the journal would only ever
        # record dinos leaving the vault and never arriving.
        await _market_escrow_record(
            "restore" if new_row_id is not None else "restore_failed",
            l.get("id"), sid, payload.get("id"), user_id,
            new_row_id=new_row_id, listing_status=l.get("status"))
        return new_row_id is not None
    await db.inventory.insert_one({
        "id": new_id(), "user_id": user_id, "item_id": f"dino_{l['dino_slug']}",
        "name": f"{l['dino_name']} Slot", "category": "Dinosaurs",
        "rarity": l.get("rarity", "Common"), "image": l["image"], "dino_slug": l["dino_slug"],
        "mutations": l.get("mutations", []), "saved_growth": l.get("growth", 5),
        "mutation_groups": l.get("mutation_groups"),
        "tier": l.get("tier"), "prime": bool(l.get("prime")) or l.get("tier") == "prime", "recovery_id": l.get("recovery_id"),
        "skin": l.get("skin"), "skin_image": l.get("skin_image"),
        "parked": True, "quantity": 1, "order": 9999, "acquired_at": now_iso(),
    })
    return True


# ---------- marketplace vault escrow journal ----------
#
# Listing a La Boveda dino REMOVES its parked_dinos row -- vault.delete_owned is
# a hard SQL DELETE, not a flag. Until 2026-08-07 that removal was completely
# silent, and the ONLY copy of the animal was the `vault_payload` snapshot
# inside the Mongo listing doc. Two real paths lost a player's dino outright
# while leaving no record anywhere that the site had taken it:
#   * the REMOVED_SPECIES sweep runs `db.market.delete_many({...})`, dropping
#     listings wholesale -- the payload, i.e. the only copy, goes with them;
#   * any Mongo loss or restore-to-an-earlier-point drops the escrow the same
#     way, and the sqlite row it came from is long gone.
# In both cases the dino is unrecoverable and not one log line says why.
#
# The fix is the shape the fleet already uses for anything that moves value
# (botcore economy.apply_delta_locked writes its ledger row FIRST; webcore
# market.do_buy writes "THE AUDIT ROW, before the commit that moves the
# dinosaur"): THE DURABLE RECORD LANDS BEFORE THE THING IT DESCRIBES MOVES.
# A write-ahead JSONL line carrying the FULL row payload is fsync'd to disk,
# and only then is the vault row deleted. If that write fails the listing is
# REFUSED and nothing is removed -- an unjournaled delete is precisely the
# defect being closed, so it is never allowed to happen at all.
#
# The journal is the reconstruction record: `list_escrow` carries every column
# of the parked row, so a dino can be restored from this file alone even if the
# Mongo listing doc no longer exists. Every removal is later matched by a
# `restore` line naming who received it, so the file reads as a closed ledger.
MARKET_ESCROW_JOURNAL_MAX_BYTES = int(
    os.environ.get("LIN_MARKET_ESCROW_JOURNAL_MAX_BYTES", str(8 * 1024 * 1024)))


def _market_escrow_journal_path() -> str:
    """Resolved per call off the LIVE game_ipc.DATA_DIR rather than frozen at
    import: a rebound DATA_DIR (the test lanes do exactly this) must not leave
    the journal writing into the old directory."""
    return os.path.join(game_ipc.DATA_DIR, "market_vault_escrow.jsonl")


def _market_escrow_append(record: dict) -> bool:
    """Append ONE json line to the escrow journal and fsync it. Blocking -- the
    callers run it through asyncio.to_thread, never on the event loop.

    Returns True only when the bytes are genuinely on disk; the caller treats
    False as "do not delete the vault row". Size-bounded: at
    MARKET_ESCROW_JOURNAL_MAX_BYTES the file rolls to `.1` (one generation
    kept), so an append-only journal can never grow the way backend.log did.
    A rotation failure is NOT a write failure -- the line is still appended to
    the existing file, because keeping the record matters more than the cap.
    """
    path = _market_escrow_journal_path()
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        try:
            if os.path.getsize(path) >= MARKET_ESCROW_JOURNAL_MAX_BYTES:
                prev = path + ".1"
                if os.path.exists(prev):
                    os.remove(prev)
                os.replace(path, prev)
        except OSError:
            # File absent (first run) or rotation refused -- neither is a reason
            # to skip the append below.
            pass
        line = json.dumps(record, ensure_ascii=False, default=str, separators=(",", ":"))
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True
    except Exception:
        logger.exception("[MARKETVAULT] escrow journal append FAILED path=%s", path)
        return False


async def _market_escrow_record(event: str, listing_id, steam_id, dino_id,
                                user_id, payload: dict | None = None, **extra) -> bool:
    """Write one escrow-journal line plus its matching log line. `payload` is
    the FULL vault row when present -- that copy is what makes a restore
    possible without the Mongo listing doc. Never raises: the journal helper
    contains its own failure and reports it as False."""
    rec = {"ts": now_iso(), "event": str(event), "listing_id": str(listing_id or ""),
           "steam_id": str(steam_id or ""), "dino_id": str(dino_id if dino_id is not None else ""),
           "user_id": str(user_id or "")}
    for k, v in extra.items():
        if v is not None:
            rec[k] = v
    if payload is not None:
        rec["vault_payload"] = payload
    try:
        ok = await asyncio.to_thread(_market_escrow_append, rec)
    except Exception:
        logger.exception("[MARKETVAULT] escrow journal thread FAILED event=%s listing=%s",
                         event, listing_id)
        ok = False
    logger.info("[MARKETVAULT] %s listing=%s dino_id=%s steam=%s user=%s payload=%s journal=%s%s",
                event, listing_id, dino_id, steam_id, user_id,
                ("yes" if payload is not None else "no"), ("ok" if ok else "FAILED"),
                ("" if not extra else " " + " ".join(
                    "%s=%s" % (k, v) for k, v in sorted(extra.items()) if v is not None)))
    return ok


async def _market_create_from_vault(data: "MarketListInput", user) -> dict:
    """POST /market/list {source:"vault", dino_id}: list a La Boveda (vault) dino.

    Steps 1-15 below ALL complete before anything moves. Step 16 is the escrow
    lane and it is UNCHANGED, byte for byte: insert the Mongo doc, write-ahead
    the fsync'd journal line carrying the FULL row, THEN delete the vault row,
    with the listing doc deleted as the rollback on either failure. That order
    is what it is on disk and it is not being "tidied" by this wave."""
    cfg = await _mcfg()
    # 0. REPLAY WALL, read-only, ahead of everything including the rate limit.
    #    A retry after a dropped socket is not a new action and must not be
    #    charged rate budget for one -- and if the first attempt DID land, the
    #    answer is that attempt's receipt, not a second listing.
    rid = _client_request_id(data.client_request_id)
    op_scope = "list:vault:%s" % (data.dino_id,)
    replayed = await _market_op_peek("list", user, rid, op_scope)
    if replayed is not None:
        return replayed
    # 1. write rate limit
    _market_write_gate(cfg, user["id"])
    # 2. listing type is CHOSEN, never inferred. The old
    #    `"auction" if data.type == "auction" else "sale"` read every typo as a
    #    direct sale, including "subasta".
    listing_type = _market_listing_type_or_400(data.type)
    # 3. duration MEMBERSHIP, never a nearest-tier snap
    duration = _duration_or_400(data.duration_hours, listing_type, cfg)
    # 4. steam linked
    if not data.dino_id:
        raise HTTPException(status_code=400, detail="Falta el dinosaurio de la bóveda a publicar.")
    sid = _steam_id_or_400(user)
    # 5. row exists AND is this player's. Wrong-owner is byte-identical to
    #    does-not-exist: the market is not an existence oracle for other
    #    people's animals.
    try:
        dino_id = int(data.dino_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Ese dinosaurio guardado no te pertenece o no existe.")
    row = await asyncio.to_thread(vault.get_parked_by_id, dino_id)
    if not row or str(row.get("steam_id")) != sid:
        raise HTTPException(status_code=404, detail="Ese dinosaurio guardado no te pertenece o no existe.")
    # 6. stale redeem resolution
    row = await asyncio.to_thread(vault.resolve_stale_redeem_pending, row)
    if not row:
        raise HTTPException(status_code=404, detail="Ese dinosaurio guardado no te pertenece o no existe.")
    # 7. no recovery in flight
    if str(row.get("redeem_pending_cmd_id") or "").strip():
        raise HTTPException(status_code=409, detail="Ese dinosaurio tiene una recuperación en progreso; no se puede publicar ahora.")
    # 8. NOT PROMISED TO SOMEBODY ELSE. This step number has been reserved since
    #    the first pass of this wave and had nothing behind it, because the trade
    #    lane did not exist yet. It does now.
    #    The direction that matters is the WANT side: an animal somebody has
    #    ASKED for is deliberately NOT escrowed (being asked must never freeze
    #    your property), so it is perfectly listable -- and selling it would
    #    strand the offer that names it. The OFFER side is covered structurally,
    #    because escrow already removed the row and step 5 cannot find it.
    held = await _pending_trade_hold(sid, dino_id)
    if held:
        raise HTTPException(status_code=409, detail=(
            "Ese dinosaurio está en una oferta de intercambio abierta. Rechaza o "
            "cancela la oferta antes de publicarlo."))

    species_bare = _bare_species(row.get("dino_class") or "")
    slug = game_telemetry.EVRIMA_SPECIES.get(species_bare, "")
    # 9. THE PER-ANIMAL MOVE COOLDOWN. Checked on BOTH keys -- the parked row id
    #    and the owner-scoped content fingerprint -- because save_parked mints a
    #    new row id on every delivery and an id-keyed clock evaporates at exactly
    #    the moment it exists to govern.
    await _move_cooldown_or_429(cfg, sid, row, dino_id)
    # 10. THE GROWTH GATE. Vault growth is a 0..1 FRACTION; the reader knows.
    growth_exact = _growth_pct_exact(row.get("growth"), "vault")
    _market_growth_gate_or_409(cfg, growth_exact)
    # 11. per-seller listing cap
    await _market_listing_cap_or_409(cfg, user["id"])
    # 12. THE FEE KNOB, read BEFORE anything moves. A broken knob refuses the
    #     NEW listing and never restrikes one already running.
    tax_pct = _tax_pct(cfg, listing_type)
    # 13. the one mutation count, and what this ANIMAL is worth
    muts = _priced_mut_count(cfg, vault_row=row)
    merit = _merit(cfg, slug, muts)
    # 14. THE SELLER'S OWN NUMBER, inside the rails
    price = _market_price_or_400(data.price, merit)

    dino_catalog = await db.dinosaurs.find_one({"slug": slug}, {"_id": 0}) if slug else None
    display_name = (dino_catalog or {}).get("name") or species_bare or "Dinosaurio"
    image = (dino_catalog or {}).get("image") or seed_data.DINO_IMG.get(slug) or ""
    rarity = (dino_catalog or {}).get("rarity", "Common")
    # 15. title sanitation. clean_custom_name stays the fallback SOURCE, not the
    #     sanitiser -- the sanitiser is ours and it runs on whichever wins.
    title = _market_title_or_400(data.title, vault.clean_custom_name(row.get("custom_name")),
                                 display_name)
    logger.info("market list (vault) slug=%s muts=%s base=%s(%s) suggested=%s rails=%s..%s "
                "seller_price=%s tax_pct=%s growth=%s",
                slug, muts, merit["base"], merit["base_source"], merit["suggested"],
                merit["min"], merit["max"], price, tax_pct, growth_exact)

    listing = {
        "id": new_id(), "seller_id": user["id"], "seller_name": user["persona_name"],
        "dino_slug": slug, "dino_name": display_name, "image": image, "rarity": rarity,
        "title": title, "mutations": [], "growth": _growth_pct_display(growth_exact), "mutation_groups": None,
        "tier": ("prime" if row.get("is_prime") else None), "prime": bool(row.get("is_prime")), "recovery_id": None,
        "skin": None, "skin_image": None,
        "type": listing_type,
        "price": price, "current_bid": None, "current_bidder_id": None, "current_bidder_name": None,
        "ends_at": (datetime.now(timezone.utc) + timedelta(hours=duration)).isoformat(),
        # `tax_pct` is the INT authority the settlement reads. `fee_rate` is
        # written one more release for rollback readability only -- nothing new
        # consumes it.
        "listing_fee": 0, "tax_pct": tax_pct, "fee_rate": round(tax_pct / 100.0, 4),
        "duration_hours": duration, "status": "active", "created_at": now_iso(),
        "suggested_price": merit["suggested"], "species_base": merit["base"],
        "base_source": merit["base_source"], "priced_mutations": muts,
        "price_min": merit["min"], "price_max": merit["max"], "price_source": "seller",
        "growth_pct_exact": growth_exact, "claimed_at": None,
        "extended_secs": 0, "sale_ref": new_id(), "client_request_id": rid or None,
        "source": "vault", "vault_payload": dict(row),
    }
    # 16. THE IDEMPOTENCY CLAIM, taken immediately before the animal moves. The
    #     insert IS the wall: of two simultaneous submits exactly one creates the
    #     `_id`, so a double click cannot produce two listings out of one row.
    op_ref, replayed = await _market_op_take("list", user, rid, op_scope, price)
    if replayed is not None:
        return replayed
    await db.market.insert_one(listing)
    # WRITE-AHEAD. The durable copy of the row reaches disk BEFORE the vault row
    # is deleted, so there is no instant at which the dino exists only in a Mongo
    # doc that something else may drop. If the journal cannot be written we
    # refuse the listing outright rather than perform an unjournaled removal --
    # that silent delete is the whole defect this closes.
    if not await _market_escrow_record("list_escrow", listing["id"], sid, data.dino_id,
                                       user["id"], payload=dict(row),
                                       species=slug or species_bare, price=price,
                                       listing_type=listing_type):
        await db.market.delete_one({"id": listing["id"]})
        exc = HTTPException(status_code=503, detail="No se pudo registrar la publicación de forma segura. Intenta de nuevo.")
        await _market_op_reversed(op_ref, exc)
        raise exc
    try:
        deleted = await asyncio.to_thread(vault.delete_owned, int(data.dino_id), sid)
    except Exception as exc:
        # delete_owned raised (e.g. a sqlite busy lock). The listing is already
        # inserted; drop it so the dino can never be BOTH parked (redeemable
        # in-game) AND for sale, then surface the failure.
        await db.market.delete_one({"id": listing["id"]})
        await _market_escrow_record("list_remove_raised", listing["id"], sid, data.dino_id,
                                    user["id"], error=str(exc)[:200])
        logger.warning("market vault-list delete_owned raised for dino_id=%s: %s", data.dino_id, exc)
        refusal = HTTPException(status_code=409, detail="No se pudo retirar el dinosaurio de la bóveda para publicarlo. Intenta de nuevo.")
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    if deleted != 1:
        # Nothing was removed (raced with a redeem/delete, or the row moved).
        # The write-ahead line above is now a claim that did NOT happen; this
        # outcome line is what tells a reader the vault still holds the dino.
        await db.market.delete_one({"id": listing["id"]})
        await _market_escrow_record("list_remove_noop", listing["id"], sid, data.dino_id,
                                    user["id"], deleted=deleted)
        refusal = HTTPException(status_code=409, detail="No se pudo retirar el dinosaurio de la bóveda para publicarlo. Intenta de nuevo.")
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    await _market_escrow_record("list_removed", listing["id"], sid, data.dino_id, user["id"])
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    result = {"success": True, "id": listing["id"], "price": price, "fee": 0,
              "tax_pct": tax_pct, "fee_rate": listing["fee_rate"],
              "suggested_price": merit["suggested"], "price_min": merit["min"],
              "price_max": merit["max"], "priced_mutations": muts,
              "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]}}
    await _market_op_done(op_ref, result)
    return result


@api_router.get("/market")
async def market_list():
    await _resolve_listings()
    cfg = await _mcfg()
    items = await db.market.find({"status": "active"}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [_market_public(l, cfg) for l in items]


@api_router.post("/market/list")
async def market_create(data: MarketListInput, user=Depends(get_current_user)):
    if data.source == "vault":
        return await _market_create_from_vault(data, user)
    # THE INVENTORY LANE RUNS THE IDENTICAL 15 STEPS. R3: both lanes, both
    # types. The only differences are where the animal is read from, that
    # growth arrives ALREADY AS A PERCENT here, and that the mutation count
    # comes from the grouped editor value rather than the parked row.
    cfg = await _mcfg()
    rid = _client_request_id(data.client_request_id)                       # 0
    op_scope = "list:inv:%s" % (data.inv_id,)
    replayed = await _market_op_peek("list", user, rid, op_scope)
    if replayed is not None:
        return replayed
    _market_write_gate(cfg, user["id"])                                    # 1
    listing_type = _market_listing_type_or_400(data.type)                  # 2
    duration = _duration_or_400(data.duration_hours, listing_type, cfg)    # 3
    item = await db.inventory.find_one({"id": data.inv_id, "user_id": user["id"], "category": "Dinosaurs"}, {"_id": 0})
    if not item:                                                           # 5
        raise HTTPException(status_code=404, detail="Ese dinosaurio no está en tu inventario o no existe.")
    slug = item.get("dino_slug")
    dino = await db.dinosaurs.find_one({"slug": slug}, {"_id": 0}) if slug else None
    if not dino:
        raise HTTPException(status_code=400, detail="Ese objeto no es un dinosaurio válido.")
    # 10. GROWTH GATE. Website inventory `saved_growth` is ALREADY A PERCENT.
    #     An inventory dino with no saved_growth reads NOTHING, not 5, and is
    #     refused -- an inventory dino is a website abstraction, not an earned
    #     animal, and this is the correct outcome for one that was never grown.
    growth_exact = _growth_pct_exact(item.get("saved_growth"), "inventory")
    _market_growth_gate_or_409(cfg, growth_exact)
    await _market_listing_cap_or_409(cfg, user["id"])                      # 11
    tax_pct = _tax_pct(cfg, listing_type)                                  # 12
    muts = _priced_mut_count(cfg, inv_item=item)                           # 13
    merit = _merit(cfg, dino["slug"], muts)
    price = _market_price_or_400(data.price, merit)                        # 14
    title = _market_title_or_400(data.title, item.get("custom_name"), dino["name"])   # 15
    logger.info("market list (inventory) slug=%s muts=%s base=%s(%s) suggested=%s "
                "rails=%s..%s seller_price=%s tax_pct=%s growth=%s",
                dino["slug"], muts, merit["base"], merit["base_source"], merit["suggested"],
                merit["min"], merit["max"], price, tax_pct, growth_exact)
    # no upfront listing fee — platform fee is taken from the seller's proceeds on sale
    listing = {
        "id": new_id(), "seller_id": user["id"], "seller_name": user["persona_name"],
        "dino_slug": dino["slug"], "dino_name": dino["name"], "image": dino["image"], "rarity": dino["rarity"],
        "title": title, "mutations": item.get("mutations", []), "growth": _growth_pct_display(growth_exact),
        "mutation_groups": item.get("mutation_groups"),
        "tier": item.get("tier"), "prime": bool(item.get("prime")) or item.get("tier") == "prime", "recovery_id": item.get("recovery_id"),
        "skin": item.get("skin"), "skin_image": item.get("skin_image"),
        "type": listing_type,
        "price": price, "current_bid": None, "current_bidder_id": None, "current_bidder_name": None,
        "ends_at": (datetime.now(timezone.utc) + timedelta(hours=duration)).isoformat(),
        "listing_fee": 0, "tax_pct": tax_pct, "fee_rate": round(tax_pct / 100.0, 4),
        "duration_hours": duration, "status": "active", "created_at": now_iso(),
        "suggested_price": merit["suggested"], "species_base": merit["base"],
        "base_source": merit["base_source"], "priced_mutations": muts,
        "price_min": merit["min"], "price_max": merit["max"], "price_source": "seller",
        "growth_pct_exact": growth_exact, "claimed_at": None,
        "extended_secs": 0, "sale_ref": new_id(), "client_request_id": rid or None,
    }
    # 16/17. THE CLAIM IS THE DELETE, and it mirrors the vault lane's proven
    #     order: insert the Mongo doc FIRST, then take the animal, then roll the
    #     doc back if the take did not land. The pre-wave order was
    #     `delete_one(...)` with the result discarded and the insert afterwards,
    #     so a double-submit had BOTH callers find the item, one delete, and
    #     BOTH insert -- two listings out of one inventory dino.
    op_ref, replayed = await _market_op_take("list", user, rid, op_scope, price)
    if replayed is not None:
        return replayed
    await db.market.insert_one(listing)
    taken = await db.inventory.delete_one({"id": item["id"], "user_id": user["id"]})
    if taken.deleted_count != 1:
        await db.market.delete_one({"id": listing["id"]})
        refusal = HTTPException(status_code=409, detail="Ese dinosaurio ya no está en tu inventario. Actualiza la página.")
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    result = {"success": True, "id": listing["id"], "price": price, "fee": 0,
              "tax_pct": tax_pct, "fee_rate": listing["fee_rate"],
              "suggested_price": merit["suggested"], "price_min": merit["min"],
              "price_max": merit["max"], "priced_mutations": muts,
              "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]}}
    await _market_op_done(op_ref, result)
    return result


async def _market_stats_info(slug: str) -> dict:
    """DISPLAY ONLY. What this species has RECENTLY SOLD FOR -- the median of
    the last MARKET_SUGGESTED_SALES_WINDOW real sales, feeding nothing.

    This replaces `_suggested_price_info`, which averaged the last 5 sales and
    then FORCED every new listing to that number. Each sale therefore raised
    the next suggestion and the series could only climb; the tell is in the
    owner's own live data, active listings repeating to the coin (3,549,734
    four times over). The price is now `_merit()` and reads NO sales at all,
    which is the structural kill: a wash sale has nothing left to push.

    `or s.get("price")` IS DELETED from the read. On a `sold` doc, `price` is
    the ASKING price -- that fallback let an ask become tomorrow's evidence."""
    sold = await db.market.find(
        {"dino_slug": slug, "status": "sold"},
        {"_id": 0, "sold_price": 1, "sold_at": 1},
    ).sort("sold_at", -1).to_list(MARKET_SUGGESTED_SALES_WINDOW)
    prices = []
    last_sold = None
    for s in sold:
        try:
            p = int(s.get("sold_price") or 0)
        except (TypeError, ValueError, OverflowError):
            continue
        if p > 0:
            prices.append(p)
            if last_sold is None:
                last_sold = {"price": p, "at": s.get("sold_at")}
    if not prices:
        return {"slug": slug, "samples": 0, "median": None, "low": None, "high": None,
                "last_sold": None, "window": MARKET_SUGGESTED_SALES_WINDOW}
    ordered = sorted(prices)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) // 2
    return {"slug": slug, "samples": len(ordered), "median": median,
            "low": ordered[0], "high": ordered[-1], "last_sold": last_sold,
            "window": MARKET_SUGGESTED_SALES_WINDOW}


async def _market_price_quote(cfg, slug: str, muts: int, listing_type: str = "sale") -> dict:
    """Everything the sell panel needs to price ONE animal, from the server:
    the merit price and its rails, the display statistic, the fee the listing
    will actually snapshot, and the live duration menus. The page reads every
    rule from this payload instead of pinning its own copy, so the input and
    the validator can never disagree about what "too crazy" means."""
    # Every rail knob is published at the TOP LEVEL as well as inside `merit`,
    # unconditionally and through the CLAMP readers (which never raise). The
    # page quotes "el 50% de su valor de mercado" off these, and it renders NO
    # copy for a rule it cannot read -- so a knob missing from this payload
    # silently deletes a sentence the seller needs.
    quote = {"slug": slug, "merit": None, "merit_error": None,
             "stats": await _market_stats_info(slug),
             "mutations": int(muts),
             "sale_durations_h": _duration_tiers(cfg, "sale"),
             "auction_durations_h": _duration_tiers(cfg, "auction"),
             "min_growth_pct": _knob_int(cfg, "min_growth_pct", 0, 100),
             "price_floor_pct": _knob_int(cfg, "price_floor_pct", 10, 100),
             "price_ceiling_pct": _knob_int(cfg, "price_ceiling_pct", 100, 1000),
             "abs_min": _knob_int(cfg, "abs_min_price", 1, 1_000_000),
             "abs_max": _knob_int(cfg, "abs_max_price", 1_000_000, 1_000_000_000),
             "max_listings_per_seller": _knob_int(cfg, "max_listings_per_seller", 1, 25)}
    try:
        quote["merit"] = _merit(cfg, slug, muts)
    except HTTPException as exc:
        quote["merit_error"] = exc.detail
    # A broken fee knob must not blank the whole panel: it is surfaced as an
    # error the seller can read, and the listing lane refuses on it anyway.
    for key, lane in (("sale_tax_pct", "sale"), ("auction_tax_pct", "auction")):
        try:
            quote[key] = _tax_pct(cfg, lane)
        except HTTPException as exc:
            quote[key] = None
            quote[key + "_error"] = exc.detail
    quote["tax_pct"] = quote.get("auction_tax_pct" if listing_type == "auction" else "sale_tax_pct")
    quote["tax_pct_error"] = quote.get(
        ("auction_tax_pct" if listing_type == "auction" else "sale_tax_pct") + "_error")
    return quote


@api_router.get("/market/suggested-price")
async def market_suggested_price(slug: str = "", species: str = "", dino_id: int = 0,
                                 inv_id: str = "", listing_type: str = "sale",
                                 user=Depends(get_current_user)):
    """What this ANIMAL is worth, not what its species averaged.

    THE CLIENT NEVER SENDS A MUTATION COUNT -- a client-sent count is a
    client-sent price with extra steps. Pass `dino_id` (a parked row) or
    `inv_id` (an inventory dino) and the server counts the slots itself off
    the row. A slug-only call still answers, at ZERO mutations, labelled
    `mutations_source: "species_only"`, so the old frontend keeps working."""
    await _resolve_listings()
    cfg = await _mcfg()
    slug = (slug or "").strip()
    species = (species or "").strip()
    muts = 0
    source = "species_only"
    growth_exact = None
    if dino_id:
        sid = _steam_id_or_400(user)
        row = await asyncio.to_thread(vault.get_parked_by_id, int(dino_id))
        if not row or str(row.get("steam_id")) != sid:
            raise HTTPException(status_code=404, detail="Ese dinosaurio guardado no te pertenece o no existe.")
        slug = game_telemetry.EVRIMA_SPECIES.get(_bare_species(row.get("dino_class") or ""), "")
        muts = _priced_mut_count(cfg, vault_row=row)
        growth_exact = _growth_pct_exact(row.get("growth"), "vault")
        source = "vault"
    elif inv_id:
        item = await db.inventory.find_one(
            {"id": inv_id, "user_id": user["id"], "category": "Dinosaurs"}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail="Ese dinosaurio no está en tu inventario o no existe.")
        slug = str(item.get("dino_slug") or "")
        muts = _priced_mut_count(cfg, inv_item=item)
        growth_exact = _growth_pct_exact(item.get("saved_growth"), "inventory")
        source = "inventory"
    elif not slug and species:
        slug = game_telemetry.EVRIMA_SPECIES.get(_bare_species(species), "")
    if not slug and not species:
        raise HTTPException(status_code=400, detail="Falta la especie.")
    quote = await _market_price_quote(cfg, slug, muts, listing_type)
    quote["mutations_source"] = source
    quote["growth_pct"] = None if growth_exact is None else _growth_pct_display(growth_exact)
    quote["market_eligible"] = None if source == "species_only" else _growth_gate_ok(cfg, growth_exact)
    # Back-compat for the shipped frontend, which reads `suggested` and renders
    # `samples`. Both now describe the merit model: `suggested` IS the merit
    # price, and it is the same integer the create lane validates against.
    if quote["merit"]:
        quote["suggested"] = quote["merit"]["suggested"]
        quote["low"] = quote["merit"]["min"]
        quote["high"] = quote["merit"]["max"]
        quote["based_on"] = "merit"
    quote["samples"] = quote["stats"]["samples"]
    return quote


@api_router.get("/market/mine")
async def market_mine(user=Depends(get_current_user)):
    """The signed-in player's own ACTIVE listings, so they can review or withdraw them."""
    await _resolve_listings()
    cfg = await _mcfg()
    items = await db.market.find({"seller_id": user["id"], "status": "active"}, {"_id": 0}).sort("created_at", -1).to_list(100)
    # THE DISPLAY AND THE CHARGE ARE THE SAME CALL. The pre-wave page displayed
    # `(current_bid or price) * 0.10` while the route charged `price * 0.10`;
    # two formulas for one number is a divergence waiting for the one listing
    # where both apply. A flat fee read through _withdraw_fee cannot diverge.
    try:
        fee = _withdraw_fee(cfg)
    except HTTPException:
        fee = None                  # broken knob: publish null, never a guess
    out = []
    for l in items:
        d = _market_public(l, cfg)
        d["withdraw_fee"] = fee
        d["has_bid"] = bool(l.get("current_bidder_id"))
        out.append(d)
    return out


@api_router.post("/market/{listing_id}/withdraw")
async def market_withdraw(listing_id: str, data: Optional[MarketActionInput] = None,
                          user=Depends(get_current_user)):
    """Pull your own active listing back into your inventory, for a FLAT fee.

    THE FEE IS FLAT AS OF 2026-08-11 and it is read through ONE helper that
    market_mine displays from. At the new scale 10% of a 17,400,000 listing was
    1,740,000 against a hard `coins >= fee` refusal -- a percentage priced a
    seller out of their own animal, and a withdraw fee prices an ACTION."""
    data = data or MarketActionInput()
    rid = _client_request_id(data.client_request_id)
    replayed = await _market_op_peek("withdraw", user, rid, "withdraw:%s" % listing_id)
    if replayed is not None:
        return replayed
    l = await db.market.find_one({"id": listing_id, "status": "active"}, {"_id": 0})
    if not l:
        raise HTTPException(status_code=404, detail="Publicación no disponible")
    if l.get("seller_id") != user["id"]:
        raise HTTPException(status_code=403, detail="No es tu publicación")
    if l.get("current_bidder_id"):
        raise HTTPException(status_code=400, detail="No puedes retirar una subasta que ya tiene pujas")
    if l.get("source") == "vault" and not await _vault_delivery_ready(l, user["id"]):
        raise HTTPException(status_code=400, detail="Tu bóveda está llena. Libera un espacio antes de retirar esta publicación.")
    fee = _withdraw_fee(await _mcfg())
    op_ref, replayed = await _market_op_take("withdraw", user, rid,
                                             "withdraw:%s" % listing_id, fee)
    if replayed is not None:
        return replayed
    # Conditional charge -- `user` is a request-time snapshot, so a plain $inc can
    # take a fee the player no longer has and push the balance negative. A fee of
    # zero still passes: `coins >= 0` is true for every real balance.
    paid = await db.users.update_one({"id": user["id"], "coins": {"$gte": fee}}, {"$inc": {"coins": -fee}})
    if paid.modified_count == 0:
        # The escape route is part of the refusal: nobody should have to guess
        # that the animal comes home free if they simply wait.
        refusal = HTTPException(status_code=400, detail=(
            f"Necesitas {_es_num(fee)} PrimeMeat para la comisión de retiro. Si no puedes "
            f"pagarla, la publicación vuelve a tu bóveda gratis cuando expire."))
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    await add_transaction(user["id"], "normal", -fee, "purchase", f"Retiro de publicación: {l['dino_name']}")
    delivered = await _give_dino(user["id"], l)  # return the escrowed dino (skin/prime/mutations preserved)
    if not delivered:
        # Vault delivery raced and lost after the pre-check above (rare) -- refund
        # the fee we just charged; nothing was lost, the listing stays active.
        await db.users.update_one({"id": user["id"]}, {"$inc": {"coins": fee}})
        await add_transaction(user["id"], "normal", fee, "refund", f"Reembolso de comisión de retiro: {l['dino_name']}")
        refusal = HTTPException(status_code=409, detail="No se pudo devolver el dinosaurio a la bóveda. Intenta de nuevo.")
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    await db.market.update_one({"id": listing_id}, {"$set": {"status": "withdrawn", "withdrawn_at": now_iso()}})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    result = {"success": True, "fee": fee,
              "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]}}
    await _market_op_done(op_ref, result)
    return result


@api_router.post("/market/{listing_id}/buy")
async def market_buy(listing_id: str, data: Optional[MarketActionInput] = None,
                     user=Depends(get_current_user)):
    """Buy a direct-sale listing. TWO LIVE DEFECTS CLOSED HERE 2026-08-11.

    DEFECT 1 -- THE ONLY UNGUARDED MONEY LANE OF THREE. The debit was a bare
    `$inc {"coins": -l["price"]}` behind a REQUEST-TIME SNAPSHOT check
    (`user.get("coins", 0) < l["price"]`). Two concurrent buys of two different
    listings both passed that check and both debited, driving a balance
    NEGATIVE. `market_withdraw` and `market_bid` both CAS on
    `{"coins": {"$gte": amount}}`; buy was the odd one out. It now CASes too.

    AND THE ORDER HAD TO MOVE WITH IT. The live order was claim -> deliver ->
    debit. Adding the guard without moving the debit converts an overdraw hole
    into a FREE ANIMAL hole: the buyer already has the dino when the CAS
    refuses. The correct shape was three routes away in this same file --
    market_withdraw charges, delivers, and refunds on delivery failure. That
    shape is copied here.

    DEFECT 2 -- NO CLOCK. This route never read `ends_at` and is in neither
    `_resolve_listings`' nor `_resolve_auctions`' caller list, so an ended sale
    stayed `active` and buyable until some OTHER endpoint happened to run a
    settle pass. The clock is now the law at request time.

    DEFECT 3 (the frontend contract) -- the page posts `expected_price` and
    `client_request_id` and NEITHER existed here; pydantic dropped both without
    a word, so the page believed in a stale-price guard and a replay guard it
    did not have. Both are real now, and the stored price is re-checked against
    TODAY's rails so a listing cannot outlive the rule that allowed it."""
    data = data or MarketActionInput()
    await _resolve_listings()
    cfg = await _mcfg()
    # THE REPLAY WALL COMES FIRST, before the row is even read. A completed buy
    # leaves the listing `sold`, so a genuine retry would otherwise be told
    # "someone else bought it" -- a support ticket built out of a correct
    # refusal. It is a read; it moves nothing.
    rid = _client_request_id(data.client_request_id)
    replayed = await _market_op_peek("buy", user, rid, "buy:%s" % listing_id)
    if replayed is not None:
        return replayed
    now = datetime.now(timezone.utc)
    l = await db.market.find_one({"id": listing_id, "status": "active"})
    if not l:
        raise await _market_gone_refusal(listing_id, "sale")
    if l["type"] != "sale":
        raise HTTPException(status_code=400, detail="Esto es una subasta — haz una puja.")
    # BOTH IDENTITIES. A seller and a buyer sharing a steam id are one person
    # whatever their user ids say, and LIN has no discord_id uniqueness.
    if _same_person(l_seller_identity(l), user) or l.get("seller_id") == user["id"]:
        raise HTTPException(status_code=400, detail="No puedes comprar tu propia publicación.")
    if _listing_has_ended(l, now):                                   # DEFECT 2
        raise HTTPException(status_code=409, detail="Esa publicación acaba de expirar.")
    price = int(l["price"])
    # THE STALE-PAGE GUARD. Strict equality against the row as it stands NOW.
    _expected_price_or_409(data.expected_price, price, lane="sale")
    # TODAY'S RAILS, not the rails the listing was born under.
    _rails_still_ok_or_409(cfg, l)
    is_vault = l.get("source") == "vault"
    if is_vault and not await _vault_delivery_ready(l, user["id"]):
        raise HTTPException(status_code=400, detail="Tu bóveda está llena. Libera un espacio antes de comprar este dinosaurio.")
    # ATOMIC CLAIM: flip active->selling so that of two concurrent buyers only one
    # proceeds. A vault listing is a single real parked row -- without this claim
    # both buyers pass the find_one above, both pay, and both receive a copy.
    # `claimed_at` + `buy_user_id` are what let the reaper recover this row if
    # the process dies before any terminal write.
    claimed = await db.market.find_one_and_update(
        {"id": listing_id, "status": "active"},
        {"$set": {"status": "selling", "claimed_at": time.time(), "buy_user_id": user["id"],
                  "charged_at": None, "charged_amount": None,
                  "delivering_at": None, "delivered_at": None}})
    if not claimed:
        raise HTTPException(status_code=409, detail="Ese dinosaurio ya fue comprado. Actualiza el mercado.")

    async def _release(**extra):
        fields = {"status": "active", "claimed_at": None, "buy_user_id": None,
                  "charged_at": None, "charged_amount": None,
                  "delivering_at": None, "delivered_at": None}
        fields.update(extra)
        await db.market.update_one({"id": listing_id, "status": "selling"}, {"$set": fields})

    # THE ATTEMPT CLAIM, after the listing claim and before any money. The ref
    # carries the attempt id, so a reversed attempt does not brick this buyer's
    # retry -- a NEW id is a new attempt, a replay of THIS one gets this answer.
    op_ref, replayed = await _market_op_take("buy", user, rid, "buy:%s" % listing_id, price)
    if replayed is not None:
        await _release()
        return replayed
    # DEFECT 1: GUARDED CAS DEBIT, and it happens BEFORE delivery.
    paid = await db.users.update_one({"id": user["id"], "coins": {"$gte": price}},
                                     {"$inc": {"coins": -price}})
    if paid.modified_count == 0:
        await _release()
        refusal = HTTPException(status_code=400, detail=f"Necesitas {_es_num(price)} PrimeMeat.")
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    await db.market.update_one({"id": listing_id}, {"$set": {"charged_at": now_iso(),
                                                             "charged_amount": price}})
    await add_transaction(user["id"], "normal", -price, "purchase", f"Mercado: {l['dino_name']}")
    # Deliver. The intent marker goes down FIRST so a crash inside the delivery
    # is distinguishable from a crash before it -- the reaper refunds the second
    # and sends the first to needs_admin rather than guessing.
    await db.market.update_one({"id": listing_id}, {"$set": {"delivering_at": now_iso()}})
    gave: dict = {}
    if not await _give_dino(user["id"], l, out=gave):
        await db.users.update_one({"id": user["id"]}, {"$inc": {"coins": price}})
        await add_transaction(user["id"], "normal", price, "refund",
                              f"Reembolso de compra no entregada: {l['dino_name']}")
        await _release()
        refusal = HTTPException(status_code=409, detail="No se pudo entregar el dinosaurio. Intenta de nuevo.")
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    await db.market.update_one({"id": listing_id}, {"$set": {"delivered_at": now_iso()}})
    # THE ANIMAL CHANGED HANDS: start its clock, on BOTH keys. Stamped before
    # the seller credit so a crash between the two still leaves the cooldown
    # written -- over-blocking is the safe direction for a laundering control.
    await _stamp_sale_cooldown(cfg, user["id"], l, gave)
    # Pay the seller off THE SNAPSHOT, integer floor, and print the integer the
    # settlement actually charged.
    pct = _listing_tax_pct(l)
    tax = _tax_on(price, pct)
    net = price - tax
    if l.get("seller_id"):
        await db.market.update_one({"id": listing_id}, {"$set": {
            "seller_paying_at": now_iso(), "sale_tax": tax, "sale_net": net, "tax_pct_charged": pct}})
        await db.users.update_one({"id": l["seller_id"]}, {"$inc": {"coins": net}})
        await add_transaction(l["seller_id"], "normal", net, "earn",
                              f"Venta del mercado (−{pct}% de comisión): {l['dino_name']}")
        await db.market.update_one({"id": listing_id}, {"$set": {"seller_paid_at": now_iso()}})
    await db.market.update_one({"id": listing_id}, {"$set": {"status": "sold", "buyer_id": user["id"], "buyer_name": user["persona_name"], "sold_price": price, "sold_at": now_iso()}})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    result = {"success": True, "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]}}
    await _market_op_done(op_ref, result)
    return result


def _bid_amount_or_400(cfg, data: "BidInput", need: int, cap: int) -> int:
    """THE NUMBER THIS BID PAYS, from either lane, validated the same way.

    TWO LANES, ONE CEILING. `amount` omitted is the page's own bid button: it
    sends the number it SHOWED (`expected_price`) and pays exactly the next
    legal amount. `amount` present is the custom-amount box. The recorded fleet
    defect on this exact feature (TWB) checked `bid_max` on the custom lane
    ONLY, so an auto-click walked an auction past the ceiling one click at a
    time and the winning number survived to settlement, where an integer add
    overflowed. The cap is therefore applied AFTER the two lanes converge, to
    the single `price` both produce -- there is no second place to forget it.

    Types are refused as TYPES, never coerced: `True` is an int in Python and
    would bid one coin, "50000" is a page that lost its number, and 5.5 is not
    PrimeMeat."""
    raw = data.amount
    if raw is None:
        # THE BID BUTTON. There is no amount to read, so the page must prove it
        # was current -- otherwise this lane silently pays whatever the auction
        # has climbed to since it rendered.
        if isinstance(data.expected_price, bool) or not isinstance(data.expected_price, int):
            raise HTTPException(status_code=400, detail=(
                "No recibimos el importe de la puja. Actualiza la página e inténtalo de nuevo."))
        _expected_price_or_409(data.expected_price, need, lane="auction")
        price = int(need)
    else:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise HTTPException(status_code=400,
                                detail="La puja debe ser un número entero de PrimeMeat, sin decimales.")
        price = int(raw)
        if price <= 0:
            raise HTTPException(status_code=400, detail="La puja debe ser mayor que cero.")
        # The custom box is checked against the SAME live minimum the button
        # pays, so the two lanes cannot disagree about what "the next bid" is.
        _expected_price_or_409(data.expected_price, need, lane="auction")
        if price < need:
            raise HTTPException(status_code=400,
                                detail=f"La puja mínima es {_es_num(need)} PrimeMeat.")
    if price > cap:
        raise HTTPException(status_code=409, detail=(
            f"La puja más alta permitida es {_es_num(cap)} PrimeMeat."))
    return price


@api_router.post("/market/{listing_id}/bid")
async def market_bid(listing_id: str, data: BidInput, user=Depends(get_current_user)):
    """Place a bid. THE AUCTION IS AN AUCTION AS OF 2026-08-11.

    DEFECT 2 (closed in the first pass): A BID WAS ACCEPTED AFTER THE AUCTION
    ENDED. This route never read `ends_at` and never called `_resolve_listings`
    -- every resolve call site was a READ route -- so on a server with no
    sweeper an ended auction stayed `active` until somebody loaded a page, and
    money kept arriving into it. The clock is the law at request time.

    WHAT THIS PASS ADDS, all of it previously OWED:
      * THE STEP. `min_bid = (current_bid or price - 1) + 1` meant ONE COIN won
        a 5,800,000 auction. It now reads `_min_next_bid`, which is the SAME
        expression `_market_public` publishes as `min_next_bid` -- the page and
        the validator cannot disagree about the number.
      * `bid_max` ON EVERY LANE (see `_bid_amount_or_400`).
      * THE ANTI-SNIPE EXTENSION, with a hard total budget, applied inside the
        SAME atomic promotion that seats the bid so a LOST race cannot extend
        the clock (see `_antisnipe_plan`).
      * THE OUTBID REFUND PAYS WHAT WAS CHARGED, read off the row through
        `_bid_charged`, never the nominal bid -- and the winner's escrow is
        recorded as `current_bid_charged` at the instant it is taken, so the
        settle path and the refund path read one number.
      * SELF-BIDDING ON BOTH IDENTITIES. LIN has no discord_id uniqueness, so
        one human already holds several site accounts; a steam id is the paid,
        single account. Shill-bidding your own auction from an alt is THE
        canonical auction attack and the pre-wave check tested `user["id"]`.
      * `expected_price` and `client_request_id`, which the shipped page has
        been posting into a route that declared neither."""
    await _resolve_listings()
    cfg = await _mcfg()
    # THE REPLAY WALL COMES FIRST, before the row is read: a bid that landed and
    # lost its socket must be answered with its own receipt, not with "someone
    # else bid first" -- that refusal is correct and still a support ticket.
    rid = _client_request_id(data.client_request_id)
    op_scope = "bid:%s" % listing_id
    replayed = await _market_op_peek("bid", user, rid, op_scope)
    if replayed is not None:
        return replayed
    now = datetime.now(timezone.utc)
    l = await db.market.find_one({"id": listing_id, "status": "active"})
    if not l:
        raise await _market_gone_refusal(listing_id, "auction")
    if l["type"] != "auction":
        raise HTTPException(status_code=404, detail="Esa subasta ya no está disponible.")
    if _same_person(l_seller_identity(l), user) or l.get("seller_id") == user["id"]:
        raise HTTPException(status_code=400, detail="No puedes pujar en tu propia subasta.")
    if _listing_has_ended(l, now):
        raise HTTPException(status_code=409, detail="Esa subasta acaba de terminar.")
    if l.get("current_bidder_id") and l.get("current_bidder_id") == user["id"]:
        # Raising your own top bid buys nothing in an ascending auction with a
        # full escrow: it moves coins out of the wallet and straight back, and
        # every one of those round trips is an anti-snipe extension the auction
        # did not need. The framework refuses it and so does this.
        raise HTTPException(status_code=409, detail="Ya tienes la puja más alta.")
    # TODAY'S RAILS. An auction whose opening ask is no longer legal takes no
    # new money; the settlement of one already running is untouched.
    _rails_still_ok_or_409(cfg, l)
    need = _min_next_bid(cfg, l)
    cap = _bid_max(cfg)
    price = _bid_amount_or_400(cfg, data, need, cap)
    # THE ATTEMPT CLAIM, before any money moves.
    op_ref, replayed = await _market_op_take("bid", user, rid, op_scope, price)
    if replayed is not None:
        return replayed
    # escrow new bid, refund previous bidder.
    # Both halves are claims, not reads. `user["coins"]` is a request-time snapshot,
    # so a plain $inc lets concurrent bids overdraw; and refunding off the listing we
    # READ lets N concurrent bids each refund the SAME previous bidder, which mints
    # coins out of nothing. The escrow is a CAS on the balance and the listing update
    # pins the exact bid being outbid, so only one bid displaces it and only that one
    # pays the refund.
    charged = await db.users.update_one({"id": user["id"], "coins": {"$gte": price}},
                                        {"$inc": {"coins": -price}})
    if charged.modified_count == 0:
        refusal = HTTPException(status_code=400, detail=(
            f"Necesitas {_es_num(price)} PrimeMeat para esta puja."))
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    # THE EXTENSION RIDES THE PROMOTION. Computed here, written in the same
    # find_one_and_update below -- an extension applied separately is one a bid
    # that LOST the race still handed out.
    snipe = _antisnipe_plan(cfg, l, now)
    seat = {"current_bid": price, "current_bid_charged": price,
            "current_bidder_id": user["id"], "current_bidder_name": user["persona_name"],
            "last_bid_at": now_iso()}
    seat.update(snipe["fields"])
    outbid = await db.market.find_one_and_update(
        {"id": listing_id, "status": "active", "type": "auction",
         "current_bid": l.get("current_bid"), "current_bidder_id": l.get("current_bidder_id")},
        {"$set": seat},
        return_document=ReturnDocument.BEFORE,
    )
    if not outbid:
        await db.users.update_one({"id": user["id"]}, {"$inc": {"coins": price}})
        refusal = HTTPException(status_code=409, detail="Otra puja llegó primero. Actualiza la subasta.")
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    await add_transaction(user["id"], "normal", -price, "purchase", f"Puja: {l['dino_name']}")
    if outbid.get("current_bidder_id"):
        # WHAT WAS ACTUALLY TAKEN, off the row we just displaced. Never the
        # nominal bid: a bid captured on a lane that charged nothing must not be
        # convertible into real currency by a later refund.
        back = _bid_charged(outbid)
        if back > 0:
            await db.users.update_one({"id": outbid["current_bidder_id"]}, {"$inc": {"coins": back}})
            await add_transaction(outbid["current_bidder_id"], "normal", back, "earn",
                                  f"Reembolso por puja superada: {l['dino_name']}")
    if snipe["granted"]:
        logger.info("[MARKET] anti-snipe listing=%s +%ss (total %ss of %ss) new_ends=%s",
                    listing_id, snipe["granted"], snipe["extended_secs"],
                    _knob_int(cfg, "antisnipe_max_total_secs", 0, 86_400), snipe["ends_at"])
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    result = {"success": True, "amount": price,
              "min_next_bid": price + _bid_step(cfg, price), "bid_max": cap,
              "ends_at": snipe["ends_at"] or l.get("ends_at"),
              "extended_secs": snipe["extended_secs"], "extended_by": snipe["granted"],
              "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]}}
    await _market_op_done(op_ref, result)
    return result


def _market_sale(l: dict) -> dict:
    return {k: l.get(k) for k in (
        "id", "seller_name", "buyer_name", "dino_slug", "dino_name", "image", "rarity",
        "type", "sold_price", "price", "sold_at", "status", "title")}


@api_router.get("/market/history")
async def market_history():
    """Recent completed marketplace sales (public feed)."""
    await _resolve_auctions()
    items = await db.market.find({"status": "sold"}, {"_id": 0}).sort("sold_at", -1).to_list(50)
    return [_market_sale(l) for l in items]


@api_router.get("/profile/sales")
async def my_market_activity(user=Depends(get_current_user)):
    """The signed-in player's marketplace history: items they sold and items they bought."""
    await _resolve_auctions()
    sold = await db.market.find({"seller_id": user["id"], "status": "sold"}, {"_id": 0}).sort("sold_at", -1).to_list(100)
    bought = await db.market.find({"buyer_id": user["id"], "status": "sold"}, {"_id": 0}).sort("sold_at", -1).to_list(100)
    return {"sold": [_market_sale(l) for l in sold], "bought": [_market_sale(l) for l in bought]}


# =============================================================================
# THE OWNER'S KNOB PANEL  (2026-08-11)
# =============================================================================
# `db.market_config` has been THE live source of every market number since the
# first pass of this wave -- and NOTHING WROTE IT. Every one of the ~30 knobs was
# reachable only by hand-editing Mongo over SSH, which on this owner's box means
# it was reachable by nobody: the whole config layer was documented, tested and
# undelivered. This pair is what makes it his.
#
# The route is the proven owner-knob shape from this same file
# (admin_get_roll_config / admin_update_roll_config): owner dependency, one GET
# that renders the live state, one PATCH that validates then invalidates the
# cache. What it adds is that the VALIDATION IS THE READERS' OWN DISCIPLINE,
# driven from MARKET_KNOB_SPEC rather than written twice -- a knob added to
# MARKET_DEFAULTS without a spec row is refused by this route rather than
# silently stored and then ignored by the reader that never learned about it.

MARKET_DURATION_TIERS_MAX = 12          # a menu, not a database
MARKET_SPECIES_TABLE_MAX = 200          # bounds the stored document
MARKET_SPECIES_SLUG_MAX = 32


def _durations_patch_or_400(key: str, raw) -> list:
    """A duration MENU, validated whole. REPLACE-WHOLE is the reader's
    discipline (`_duration_tiers`), so half a list is never stored: one bad
    entry refuses the entire edit and names it. Integral values are stored as
    ints so the panel renders «24» rather than «24.0»."""
    if not isinstance(raw, (list, tuple)) or not raw:
        raise HTTPException(status_code=400, detail=(
            f"«{key}» debe ser una lista de horas, por ejemplo [6, 24, 48, 72]. No se cambió nada."))
    if len(raw) > MARKET_DURATION_TIERS_MAX:
        raise HTTPException(status_code=400, detail=(
            f"«{key}» admite como máximo {MARKET_DURATION_TIERS_MAX} opciones. No se cambió nada."))
    out = []
    for t in raw:
        if isinstance(t, bool) or not isinstance(t, (int, float)):
            raise HTTPException(status_code=400, detail=(
                f"«{key}»: {t!r} no es un número de horas. No se cambió nada."))
        val = float(t)
        if val != val or not (0 < val <= 24 * 30):
            raise HTTPException(status_code=400, detail=(
                f"«{key}»: {t!r} está fuera de rango (más de 0 y hasta 720 horas). No se cambió nada."))
        val = int(val) if abs(val - round(val)) < 1e-9 else round(val, 4)
        if val not in out:          # a menu with the same tier twice renders twice
            out.append(val)
    return out


def _species_base_patch_or_400(cfg, key: str, raw, lo: int, hi: int) -> dict:
    """The species price table, edited AS A MERGE over the LIVE table.

    THE TRAP THIS CLOSES: `_mcfg` merges the stored document over the defaults
    KEY BY KEY, so a stored `species_base` REPLACES the shipped 22-row table
    ENTIRELY. A panel that PATCHed `{"trex": 1200000}` as sent would drop 21
    species onto `species_base_fallback` in one click, and nothing would say so
    -- every one of those animals would just quietly start pricing at 400,000.
    So the edit is merged over `_species_base_table(cfg)` (the live, entry-
    validated table) and the COMPLETE table is what gets stored.

    `null` for a slug REMOVES that override, which is the only way back to the
    fallback once a slug has one. The whole edit is refused naming the bad slug:
    a half-applied price table is a table nobody can reason about."""
    if not isinstance(raw, dict) or not raw:
        raise HTTPException(status_code=400, detail=(
            f"«{key}» debe ser una tabla de especie → precio base. No se cambió nada."))
    table = dict(_species_base_table(cfg))
    for slug, val in raw.items():
        name = str(slug or "").strip()
        if not name or len(name) > MARKET_SPECIES_SLUG_MAX or not name.isprintable():
            raise HTTPException(status_code=400, detail=(
                f"«{key}»: {slug!r} no es una especie válida. No se cambió nada."))
        if val is None:
            table.pop(name, None)
            continue
        if isinstance(val, bool) or not isinstance(val, int) or not (lo <= val <= hi):
            raise HTTPException(status_code=400, detail=(
                f"«{key}»: {name} = {val!r} está fuera de rango; debe ser un número "
                f"entero entre {_es_num(lo)} y {_es_num(hi)}. No se cambió nada."))
        table[name] = int(val)
    if not table:
        raise HTTPException(status_code=400, detail=(
            f"«{key}» no puede quedar vacía: todas las especies pasarían al precio "
            f"de reserva sin avisar. No se cambió nada."))
    if len(table) > MARKET_SPECIES_TABLE_MAX:
        raise HTTPException(status_code=400, detail=(
            f"«{key}» admite como máximo {MARKET_SPECIES_TABLE_MAX} especies. No se cambió nada."))
    return table


def _market_config_patch_or_400(cfg, raw) -> tuple[dict, list]:
    """Validate ONE owner edit against MARKET_KNOB_SPEC. PURE: it moves nothing,
    so every refusal below is literally true when it says nothing changed.

    Returns (patch, notes). A `note` is a CLAMP that snapped -- reported back
    rather than applied in silence, because the number the owner typed and the
    number the market now uses being different is exactly the thing a clamping
    reader hides. A REFUSE knob out of band, a bool where an int belongs, an int
    where a bool belongs, and an unknown key are all refusals of the WHOLE edit:
    a partially applied config is a config nobody can reason about."""
    if not isinstance(raw, dict) or not raw:
        raise HTTPException(status_code=400, detail="No enviaste ningún cambio.")
    unknown = sorted(k for k in raw if k not in MARKET_KNOB_SPEC)
    if unknown:
        # NEVER stored. A key nobody reads is a setting the owner believes he
        # changed, which is worse than a refusal he can see.
        raise HTTPException(status_code=400, detail=(
            f"No conozco el ajuste «{unknown[0]}», así que no se cambió nada. "
            f"Ajustes válidos: {', '.join(sorted(MARKET_KNOB_SPEC))}."))
    patch: dict = {}
    notes: list = []
    for key in sorted(raw):
        val = raw[key]
        kind, lo, hi = MARKET_KNOB_SPEC[key]
        if kind in ("refuse", "clamp"):
            if isinstance(val, bool) or not isinstance(val, int):
                raise HTTPException(status_code=400, detail=(
                    f"«{key}» debe ser un número entero entre {_es_num(lo)} y {_es_num(hi)}; "
                    f"recibimos {val!r}. No se cambió nada."))
            if kind == "refuse":
                if not (lo <= val <= hi):
                    raise HTTPException(status_code=400, detail=(
                        f"«{key}» = {_es_num(val)} está fuera de rango; debe ser un número "
                        f"entero entre {_es_num(lo)} y {_es_num(hi)}. No se cambió nada."))
                patch[key] = int(val)
            else:
                snapped = max(lo, min(hi, int(val)))
                if snapped != int(val):
                    notes.append({"key": key, "sent": int(val), "stored": snapped,
                                  "min": lo, "max": hi,
                                  "message": (f"«{key}»: {_es_num(val)} está fuera de rango, "
                                              f"lo guardamos como {_es_num(snapped)} "
                                              f"({_es_num(lo)}–{_es_num(hi)}).")})
                patch[key] = snapped
        elif kind == "bool":
            if not isinstance(val, bool):
                # 0/1/"true" are NOT bools, and reading one as a switch is how a
                # switch ends up in a state nobody chose -- the same law
                # `_knob_bool` enforces on the read side.
                raise HTTPException(status_code=400, detail=(
                    f"«{key}» debe ser verdadero o falso; recibimos {val!r}. No se cambió nada."))
            patch[key] = bool(val)
        elif kind == "durations":
            patch[key] = _durations_patch_or_400(key, val)
        elif kind == "table":
            patch[key] = _species_base_patch_or_400(cfg, key, val, lo, hi)
        else:                                    # unreachable by construction
            raise HTTPException(status_code=500, detail=(
                f"«{key}» tiene una disciplina desconocida ({kind}). No se cambió nada."))
    return patch, notes


def _market_knob_report(cfg) -> list:
    """Every knob, its discipline, its band, its default and ITS LIVE VALUE --
    plus, for the REFUSE knobs, whether the value stored RIGHT NOW is one the
    reader would throw a 503 on. That last column is the point: a broken REFUSE
    knob does not announce itself anywhere until a player is told the market is
    misconfigured, and this is the panel that shows it first."""
    out = []
    for key in sorted(MARKET_KNOB_SPEC):
        kind, lo, hi = MARKET_KNOB_SPEC[key]
        row = {"key": key, "discipline": kind, "min": lo, "max": hi,
               "value": (cfg or {}).get(key, MARKET_DEFAULTS.get(key)),
               "default": MARKET_DEFAULTS.get(key), "error": None, "effective": None}
        try:
            if kind == "refuse":
                row["effective"] = _knob_refuse_int(cfg, key, lo, hi)
            elif kind == "clamp":
                row["effective"] = _knob_int(cfg, key, lo, hi)
            elif kind == "bool":
                row["effective"] = _knob_bool(cfg, key)
            elif kind == "durations":
                row["effective"] = _duration_tiers(cfg, "auction" if "auction" in key else "sale")
            elif kind == "table":
                row["effective"] = _species_base_table(cfg)
        except HTTPException as exc:
            row["error"] = exc.detail
        out.append(row)
    return out


def _highest_reachable_rail(cfg) -> dict:
    """THE MOST EXPENSIVE LISTING THE LIVE KNOBS ALLOW, and which animal reaches
    it. Computed from the knobs as they stand, never from the shipped defaults.

    It exists so the owner sees a gap BEFORE a player does. Two gaps it makes
    visible the moment they open: `abs_max_price` quietly binding below the top
    species' rail (so the best animal on the server cannot be listed at what the
    table says it is worth), and `bid_max` sitting BELOW that ceiling -- which
    would let a seller open an auction at a price no bidder is allowed to pay."""
    try:
        muts = _knob_int(cfg, "mutation_cap", 0, 16)
        table = _species_base_table(cfg)
        slugs = sorted(table) or [""]          # "" misses the table -> fallback
        best = None
        for slug in slugs:
            merit = _merit(cfg, slug, muts)
            if best is None or merit["max"] > best[1]["max"]:
                best = (slug, merit)
        slug, merit = best
        cap = _bid_max(cfg)
        return {"slug": slug or None, "mutations": muts,
                "species_base": merit["base"], "base_source": merit["base_source"],
                "suggested": merit["suggested"], "price_min": merit["min"],
                "price_max": merit["max"], "bound_by": merit["max_bound_by"],
                "abs_max_price": merit["abs_max"], "bid_max": cap,
                "bid_max_covers": cap >= merit["max"], "error": None}
    except HTTPException as exc:
        # A broken REFUSE knob must not blank the panel that exists to show it.
        return {"error": exc.detail}
    except Exception:
        logger.exception("[MARKET] highest_reachable_rail failed")
        return {"error": "No se pudo calcular el techo del mercado."}


async def _market_missing_species(cfg) -> list:
    """Every species the site sells that the price table has NO base for.

    Those slugs are not broken -- they take `species_base_fallback` -- but they
    are all priced the SAME whatever they are, and the only symptom is a player
    listing a rare animal for the price of a common one. Named here, with the
    fallback they are currently taking, so it is a line in the panel rather than
    a support ticket."""
    try:
        rows = await db.dinosaurs.find({}, {"_id": 0, "slug": 1, "name": 1}).to_list(500)
    except Exception:
        logger.exception("[MARKET] missing-species scan could not read db.dinosaurs")
        return []
    table = _species_base_table(cfg)
    seen, out = set(), []
    for d in rows or []:
        slug = str((d or {}).get("slug") or "").strip()
        if not slug or slug in table or slug in seen:
            continue
        seen.add(slug)
        out.append({"slug": slug, "name": (d or {}).get("name") or slug})
    return sorted(out, key=lambda r: r["slug"])


async def _market_config_view(cfg) -> dict:
    """The whole panel, from the LIVE config. Shared by GET and by PATCH's
    answer, so the owner's next screen is never rendered from a different read
    than the one his edit just produced."""
    try:
        stored = await db.market_config.find_one({"_id": "market"}, {"_id": 0}) or {}
    except Exception:
        logger.exception("[MARKET] admin panel could not read market_config")
        stored = {}
    missing = await _market_missing_species(cfg)
    rail = _highest_reachable_rail(cfg)
    warnings = []
    for row in _market_knob_report(cfg):
        if row["error"]:
            warnings.append(row["error"])
    if missing:
        try:
            fb = _knob_refuse_int(cfg, "species_base_fallback", 50_000, 2_000_000)
            fb_txt = f" y se están cobrando al precio de reserva de {_es_num(fb)}"
        except HTTPException:
            fb_txt = ""
        warnings.append(
            f"{len(missing)} especie(s) no tienen precio base en la tabla{fb_txt}: "
            + ", ".join(m["slug"] for m in missing[:12])
            + ("…" if len(missing) > 12 else ""))
    if rail.get("error"):
        warnings.append(rail["error"])
    else:
        if rail["bound_by"] == "abs":
            warnings.append(
                f"El techo absoluto (abs_max_price = {_es_num(rail['abs_max_price'])}) está "
                f"por debajo del máximo que la tabla da a «{rail['slug']}» — ese dinosaurio "
                f"no se puede publicar por lo que vale.")
        if not rail["bid_max_covers"]:
            warnings.append(
                f"bid_max = {_es_num(rail['bid_max'])} es menor que el precio máximo "
                f"alcanzable ({_es_num(rail['price_max'])}): una subasta de «{rail['slug']}» "
                f"no se podría pujar hasta su techo.")
    return {"config": cfg, "stored": stored, "defaults": _market_defaults(),
            "knobs": _market_knob_report(cfg), "spec": {
                k: {"discipline": v[0], "min": v[1], "max": v[2]}
                for k, v in MARKET_KNOB_SPEC.items()},
            "missing_species": missing, "highest_reachable_rail": rail,
            "warnings": warnings, "cache_secs": MARKET_CFG_CACHE_SECS}


class MarketConfigInput(BaseModel):
    """The PATCH body: `{"knobs": {...}}`, or the knobs posted flat.

    ONE untyped dict, deliberately. A model with ~30 typed optional fields
    cannot tell "the owner left this knob alone" from "the owner sent null", and
    pydantic would answer a 422 in ENGLISH for a knob whose refusal owes this
    owner one exact Spanish sentence naming the band. Every value is validated
    against MARKET_KNOB_SPEC by `_market_config_patch_or_400` instead, which is
    the same table the readers were built from."""
    knobs: Optional[dict] = None
    model_config = {"extra": "allow"}


def _market_patch_body(data: "MarketConfigInput") -> dict:
    """Accept both shapes without letting either hide the other."""
    if data.knobs is not None and not isinstance(data.knobs, dict):
        raise HTTPException(status_code=400,
                            detail="«knobs» debe ser un objeto de ajuste → valor.")
    body = dict(getattr(data, "model_extra", None) or {})
    body.pop("knobs", None)
    body.update(dict(data.knobs or {}))
    return body


@api_router.get("/admin/market/config")
async def admin_get_market_config(owner=Depends(get_owner_user)):
    """THE MARKET, as the owner can see it: every knob with its live value, its
    discipline and its band; the two gap reports; and the defaults to compare
    against. Read through `_mcfg`, so this is the config the routes are actually
    using and not a second opinion about it."""
    return await _market_config_view(await _mcfg())


@api_router.patch("/admin/market/config")
async def admin_update_market_config(data: MarketConfigInput, owner=Depends(get_owner_user)):
    """Change market knobs. Validate EVERYTHING first, write once, invalidate.

    The order is the whole safety property: `_market_config_patch_or_400` is
    pure, so every refusal it raises really did leave the config untouched, and
    a five-knob edit with one bad value stores none of the five. The cache is
    invalidated in the same call that writes, so the change is live on the very
    next request instead of up to MARKET_CFG_CACHE_SECS later."""
    cfg = await _mcfg()
    patch, notes = _market_config_patch_or_400(cfg, _market_patch_body(data))
    try:
        await db.market_config.update_one({"_id": "market"}, {"$set": patch}, upsert=True)
    except Exception:
        logger.exception("[MARKET] could not store the owner's config edit %s", sorted(patch))
        raise HTTPException(status_code=503,
                            detail="No se pudo guardar la configuración. Inténtalo de nuevo.")
    # INVALIDATE, then re-read. Publishing the dict we just built would show the
    # owner what he asked for rather than what the market will now read.
    _market_cfg_invalidate()
    fresh = await _mcfg()
    await add_log(owner.get("persona_name"), "update_market_config", "market",
                  {"keys": sorted(patch), "clamped": [n["key"] for n in notes]})
    logger.warning("[MARKET] owner %s changed %s%s", owner.get("persona_name"),
                   sorted(patch), (" (clamped: %s)" % [n["key"] for n in notes]) if notes else "")
    view = await _market_config_view(fresh)
    view["changed"] = sorted(patch)
    view["clamped"] = notes
    view["success"] = True
    return view


# =============================================================================
# THE TRADE SUBSYSTEM  (R7, 2026-08-11)  --  "plus the live trade system with a
# cooldown of 24 hours"
# =============================================================================
# LIN had ZERO trade endpoints. Everything below is new, and every ruling it
# implements was made before a line of it was written:
#
#   TWO-SIDED, N-FOR-N ANIMALS, NO COINS ON EITHER SIDE. There is no coin field
#   on an offer and no knob for one. A coin leg turns a trade into an untaxed
#   sale and re-opens the 25% the market charges -- the trade lane would simply
#   become the cheap way to sell.
#
#   ESCROW ON THE OFFER SIDE ONLY. Being ASKED for an animal never freezes it:
#   a stranger could otherwise lock every animal on the server by asking for
#   them. What the SENDER offers leaves `parked_dinos` behind the same
#   write-ahead fsync'd journal line `_market_create_from_vault` uses -- the
#   same helper, not a second discipline.
#   ★WHY ESCROW AND NOT A LOCK COLUMN: LIN's Discord bot is a SECOND WRITER to
#   that sqlite table and DELETES from it. A query-side lock is a lock the bot
#   walks straight through; a row that is not there cannot be redeemed, sold,
#   listed or deleted by anybody.
#
#   ★★ESCROW FREES A VAULT SLOT. The sender can refill it the instant the offer
#   goes out, and then a restore has nowhere to land. So escrowed rows are
#   RESERVED against the park cap (`_reserved_park_slots`) -- the sender's own
#   pending offers count as slots already spoken for -- and a restore that
#   still cannot land is a RETRIED state (`restore_pending`), never a terminal
#   one. An animal is never written off because a vault was full for a minute.
#
#   COOLDOWN SCOPE: PER PLAYER, BOTH SIDES, CLAIMED IN THE WRITE THAT SETTLES.
#   Not per-pair -- three alts beat that. Not initiator-only -- role-swapping
#   halves it. The claim is a conditional write on the cooldown row itself, so
#   two offers accepted in the same instant cannot both settle: the second one
#   loses the claim and is put back. Default 86,400 s, `0` disables.
#   A completed trade ALSO stamps the per-ANIMAL `dino_move_cooldown_secs`
#   clock, so the trade lane is not the uncooled laundering path beside a
#   cooled market.
#
#   VALUE SYMMETRY on the SAME `_merit` numbers the market prices with, so a
#   6,300,000 animal cannot be traded for a 300,000 one.
#
#   RE-VALIDATED AT SETTLE against TODAY'S rules -- growth gate, both
#   cooldowns, symmetry, park cap, ownership. An offer is a proposal, not a
#   ticket that outlives the rules it was written under.

TRADE_STATUSES_OPEN = ("pending", "settling", "restore_pending")
TRADE_RESOLVE_EVERY_SECS = 30.0
_trade_resolve_last = 0.0


def _trade_enabled(cfg) -> bool:
    return _knob_bool(cfg, "trade_enabled")


def _trade_cooldown_secs(cfg) -> int:
    """REFUSE, and 0 DISABLES -- his own re-enable contract. A cooldown that
    cannot be turned off is one that gets turned off by editing code."""
    return _knob_refuse_int(cfg, "trade_cooldown_secs", 0, 604_800,
                            label="La espera entre intercambios está mal configurada")


def _trade_ttl_secs(cfg) -> int:
    return _knob_refuse_int(cfg, "trade_offer_ttl_secs", 300, 604_800,
                            label="La caducidad de las ofertas está mal configurada")


def _trade_symmetry_ok(cfg, a: int, b: int) -> bool:
    """THE VALUE BAND, in integers. The smaller side must be worth at least
    (100 - trade_symmetry_pct)% of the larger one.

    Integer arithmetic on both sides of the comparison, so the band EDGE is
    exact and belongs to the player: at 25%, 6,000,000 against 8,000,000 is
    600,000,000 >= 600,000,000 and trades; 5,999,999 does not. A float
    comparison here would make the edge a coin toss between two runs."""
    pct = _knob_int(cfg, "trade_symmetry_pct", 0, 100)
    lo, hi = min(int(a), int(b)), max(int(a), int(b))
    if hi <= 0:
        return True
    return lo * 100 >= (100 - pct) * hi


def _trade_cooldown_key(user_id) -> str:
    return "trade:%s" % str(user_id)


async def _trade_cooldown_state(cfg, user_id) -> dict | None:
    """The blocking trade cooldown for one player, or None.

    FAILS OPEN on a Mongo failure and says so -- the same direction the
    per-animal cooldown chose, and for the same reason: a jammed cooldown is a
    permanent lockout of a player's own property."""
    try:
        secs = _trade_cooldown_secs(cfg)
    except HTTPException:
        raise
    if secs <= 0:
        return None
    try:
        row = await db.trade_cooldowns.find_one({"_id": _trade_cooldown_key(user_id)})
    except Exception:
        logger.exception("[TRADE] cooldown read failed for %s - failing OPEN", user_id)
        return None
    if not row:
        return None
    try:
        until = float(row.get("until") or 0)
    except (TypeError, ValueError):
        return None
    # AT THE EXPIRY INSTANT THE COOLDOWN IS OVER. Strict `>`, so the boundary
    # belongs to the player -- the same law `_move_cooldown_state` follows.
    if until <= time.time():
        return None
    return {"until": until, "at": float(row.get("at") or 0), "why": row.get("why")}


async def _trade_cooldown_or_429(cfg, user, who: str) -> None:
    state = await _trade_cooldown_state(cfg, user["id"])
    if not state:
        return
    total = _trade_cooldown_secs(cfg)
    left = max(1, int(math.ceil(state["until"] - time.time())))
    if who == "self":
        raise HTTPException(status_code=429, detail=(
            f"Ya intercambiaste hace poco. Cada jugador puede intercambiar una vez "
            f"cada {_wait_es(total)} — te faltan {_wait_es(left)}."))
    raise HTTPException(status_code=429, detail=(
        f"Ese jugador intercambió hace poco. Puede volver a intercambiar en "
        f"{_wait_es(left)}."))


async def _trade_cooldown_claim(cfg, user_id, why: str) -> bool:
    """CLAIM one player's trade cooldown. THE CONDITIONAL WRITE IS THE WALL.

    Two offers accepted in the same instant by the same player must not both
    settle -- that is the "role-swapping halves it" hole in a different costume,
    and a plain `check then write` loses that race. The update only matches a
    row whose clock has already run out; if there is no row at all the INSERT
    is the wall, because `_id` is Mongo's own primary key. Whoever wins the
    claim is the one allowed to move animals.

    A cooldown of 0 (disabled) claims nothing and always wins."""
    try:
        secs = _trade_cooldown_secs(cfg)
    except HTTPException:
        raise
    if secs <= 0:
        return True
    now = time.time()
    key = _trade_cooldown_key(user_id)
    doc = {"until": now + secs, "at": now, "why": str(why), "ts": now_iso()}
    try:
        res = await db.trade_cooldowns.update_one({"_id": key, "until": {"$lte": now}},
                                                  {"$set": doc})
        if getattr(res, "modified_count", 0) == 1:
            return True
        await db.trade_cooldowns.insert_one(dict(doc, _id=key))
        return True
    except DuplicateKeyError:
        return False
    except Exception:
        # Mongo is unhappy. Refuse the SETTLE rather than move animals with no
        # cooldown written: an unclaimed trade is a free extra turn, and that is
        # the one direction this control must never fail in.
        logger.exception("[TRADE] cooldown claim failed for %s", user_id)
        return False


async def _trade_cooldown_release(user_id) -> None:
    """Hand the claim back when a settle did not happen. A player must not be
    locked out for 24 hours by an accept that refused."""
    try:
        await db.trade_cooldowns.update_one({"_id": _trade_cooldown_key(user_id)},
                                            {"$set": {"until": 0.0, "released_at": now_iso()}})
    except Exception:
        logger.exception("[TRADE] could not release the cooldown claim for %s", user_id)


async def _reserved_park_slots(steam_id: str, exclude_offer: str = "") -> int:
    """★★ HOW MANY VAULT SLOTS THIS PLAYER'S ESCROW IS HOLDING FOR THEM.

    Escrow REMOVES the parked row, which frees a slot the owner can refill in
    the same minute -- and then the animal has nowhere to come home to. Every
    row currently in market escrow or in a pending trade offer therefore counts
    against the cap as if it were still parked.

    `exclude_offer` is what makes a restore possible at all: when the slots are
    being counted FOR that offer's own restore, its own reservation is the
    thing being redeemed and must not block itself."""
    sid = str(steam_id or "").strip()
    if not sid:
        return 0
    n = 0
    try:
        # Counted in Mongo, not in Python: `vault_payload` carries a whole
        # parked row including the skin blob, and this runs on a lane a player
        # can hit repeatedly.
        n += await db.market.count_documents({
            "source": "vault", "status": {"$in": ["active", "selling", "resolving"]},
            "vault_payload.steam_id": sid})
    except Exception:
        logger.exception("[TRADE] could not count market escrow for %s", sid)
    try:
        # `offer_items` is the small metadata list; it is one entry per escrowed
        # animal by construction, so the projection never drags a payload back.
        offers = await db.trade_offers.find(
            {"status": {"$in": list(TRADE_STATUSES_OPEN)}, "from_steam": sid},
            {"_id": 0, "id": 1, "offer_items": 1}).to_list(200)
        for o in offers or []:
            if exclude_offer and o.get("id") == exclude_offer:
                continue
            n += len(o.get("offer_items") or [])
    except Exception:
        logger.exception("[TRADE] could not count trade escrow for %s", sid)
    return n


async def _trade_slots_free(user, steam_id: str, exclude_offer: str = "") -> int:
    """Free vault slots WITH escrow reserved. An admin (cap 0) is unbounded.

    RETURNS A SIGNED NUMBER, and the sign carries information the callers need:
    a NEGATIVE answer means this player has more animals promised than slots to
    put them in, which is exactly the state a clamp to zero would hide. The
    display sites clamp; the gates do not.

    The arithmetic that makes the reservation work: escrowing n animals moves n
    out of `used` and n into `reserved`, so this number does not change at
    escrow time -- which is the whole point. At settle the offer's own
    reservation is excluded, and the n slots it was holding become the n the
    restore lands in."""
    cap = _user_park_cap(user)
    if cap <= 0:
        return 1_000_000
    used = await asyncio.to_thread(vault.count_parked, steam_id)
    return cap - int(used) - await _reserved_park_slots(steam_id, exclude_offer)


async def _pending_trade_hold(steam_id: str, dino_id, exclude_offer: str = "") -> dict | None:
    """The pending offer that has a claim on this animal, or None.

    THE MUTUAL EXCLUSION, in the direction that is not structural. An animal on
    the OFFER side has already left `parked_dinos`, so the market lane refuses
    it by simply not finding it. An animal on the WANT side is untouched and
    perfectly listable -- and listing it (or auctioning it) would strand the
    offer that names it. So the market list lane asks this first."""
    sid = str(steam_id or "").strip()
    try:
        did = int(dino_id)
    except (TypeError, ValueError):
        return None
    if not sid:
        return None
    # ONE bounded query with a projection, never a scan-and-filter: this runs on
    # the market's own create lane and on every trade validation, and the offer
    # documents carry full vault payloads that must not travel for a yes/no.
    # `exclude_offer` is applied IN the query -- the offer being settled holds
    # its own animals by definition and must not refuse the settle it authorises.
    q = {"status": {"$in": list(TRADE_STATUSES_OPEN)},
         "$or": [{"to_steam": sid, "want_items.dino_id": did},
                 {"from_steam": sid, "offer_items.dino_id": did}]}
    if exclude_offer:
        q["id"] = {"$ne": str(exclude_offer)}
    try:
        return await db.trade_offers.find_one(
            q, {"_id": 0, "id": 1, "status": 1, "from_name": 1, "to_name": 1})
    except Exception:
        # FAIL OPEN, loudly. A Mongo hiccup must not block a player from
        # listing their own animal; the settle side re-validates ownership and
        # refuses there instead, which costs an offer rather than a sale.
        logger.exception("[TRADE] pending-hold lookup failed for %s/%s", sid, dino_id)
        return None


def _trade_item_view(cfg, row: dict) -> dict:
    """ONE animal as both sides read it, priced with the market's own `_merit`.
    The raw parked row never leaves this function."""
    species = _bare_species(row.get("dino_class") or "")
    slug = game_telemetry.EVRIMA_SPECIES.get(species, "")
    muts = _priced_mut_count(cfg, vault_row=row)
    growth = _growth_pct_exact(row.get("growth"), "vault")
    item = {"dino_id": int(row.get("id") or 0), "slug": slug,
            "species": species, "name": vault.clean_custom_name(row.get("custom_name")) or species,
            "growth_pct": _growth_pct_display(growth), "growth_pct_exact": growth,
            "mutations": muts, "prime": bool(row.get("is_prime")),
            "fingerprint": _dino_fingerprint(row), "value": 0, "value_error": None}
    try:
        item["value"] = _merit(cfg, slug, muts)["suggested"]
    except HTTPException as exc:
        item["value_error"] = exc.detail
    return item


def _trade_side_value(items) -> int:
    total = 0
    for it in items or []:
        try:
            total += max(0, int(it.get("value") or 0))
        except (TypeError, ValueError, OverflowError):
            continue
    return total


def _trade_public(o: dict, viewer_id: str = "") -> dict:
    """One offer as a player may see it. The escrowed payloads NEVER leave."""
    d = {k: o.get(k) for k in (
        "id", "status", "from_id", "from_name", "to_id", "to_name", "note",
        "created_at", "expires_at", "offer_value", "want_value", "symmetry_pct",
        "resolve_note", "settled_at", "closed_at", "board_id")}
    d["offer_items"] = [{k: v for k, v in (it or {}).items() if k != "fingerprint"}
                        for it in (o.get("offer_items") or [])]
    d["want_items"] = [{k: v for k, v in (it or {}).items() if k != "fingerprint"}
                       for it in (o.get("want_items") or [])]
    d["direction"] = ("outgoing" if viewer_id and o.get("from_id") == viewer_id
                      else "incoming" if viewer_id and o.get("to_id") == viewer_id else "other")
    d["can_accept"] = bool(viewer_id and o.get("to_id") == viewer_id and o.get("status") == "pending")
    d["can_cancel"] = bool(viewer_id and o.get("from_id") == viewer_id and o.get("status") == "pending")
    return d


async def _trade_escrow_take(offer_id: str, sid: str, user_id: str, rows: list):
    """WRITE-AHEAD, THEN DELETE, one row at a time -- byte-for-byte the order
    `_market_create_from_vault` uses, through the same journal helper.

    Returns (taken_payloads, refusal). On a refusal the caller restores every
    payload in `taken`: a partial escrow is the one outcome that loses animals,
    so the unwind is the caller's first move, not an afterthought."""
    taken = []
    for row in rows:
        did = row.get("id")
        if not await _market_escrow_record("trade_escrow", "trade:%s" % offer_id, sid, did,
                                           user_id, payload=dict(row), side="offer"):
            return taken, HTTPException(status_code=503, detail=(
                "No se pudo registrar el intercambio de forma segura. Intenta de nuevo."))
        try:
            deleted = await asyncio.to_thread(vault.delete_owned, int(did), sid)
        except Exception as exc:
            await _market_escrow_record("trade_remove_raised", "trade:%s" % offer_id, sid,
                                        did, user_id, error=str(exc)[:200])
            logger.warning("[TRADE] delete_owned raised for dino_id=%s: %s", did, exc)
            return taken, HTTPException(status_code=409, detail=(
                "No se pudo retirar un dinosaurio de la bóveda para el intercambio. "
                "Intenta de nuevo."))
        if deleted != 1:
            await _market_escrow_record("trade_remove_noop", "trade:%s" % offer_id, sid,
                                        did, user_id, deleted=deleted)
            return taken, HTTPException(status_code=409, detail=(
                "Uno de esos dinosaurios ya no está en tu bóveda. Actualiza la página."))
        await _market_escrow_record("trade_removed", "trade:%s" % offer_id, sid, did, user_id)
        taken.append(dict(row))
    return taken, None


async def _trade_restore(offer_id: str, user_id: str, payloads: list):
    """Put escrowed animals back. Returns (restored, still_missing).

    Each restore rides `_give_dino`, so the journal's `restore` line is written
    by the SAME function the market's restores go through and the ledger reads
    as one closed book."""
    back, lost = [], []
    for p in payloads or []:
        try:
            ok = await _give_dino(user_id, {"id": "trade:%s" % offer_id, "source": "vault",
                                            "vault_payload": dict(p), "status": "restore"})
        except Exception:
            logger.exception("[TRADE] restore raised offer=%s user=%s", offer_id, user_id)
            ok = False
        (back if ok else lost).append(p)
    return back, lost


async def _trade_close_with_restore(o: dict, user_id: str, payloads: list,
                                    final_status: str, note: str) -> bool:
    """Close an offer by giving the escrow back. A restore that cannot land is
    a RETRIED state, never a terminal one -- the payload stays on the doc and
    `_resolve_trade_offers` tries again on every trade read. An animal is never
    written off because a vault happened to be full for a minute."""
    back, lost = await _trade_restore(o["id"], user_id, payloads)
    if lost:
        await db.trade_offers.update_one({"id": o["id"]}, {"$set": {
            "status": "restore_pending", "restore_to": user_id, "restore_payloads": lost,
            "restore_next_status": final_status, "resolve_note": note,
            "restore_attempts": int(o.get("restore_attempts") or 0) + 1,
            "restore_last_at": now_iso()}})
        logger.warning("[TRADE] offer %s: %s of %s could not be restored to %s - RETRYING",
                       o["id"], len(lost), len(payloads or []), user_id)
        return False
    await db.trade_offers.update_one({"id": o["id"]}, {"$set": {
        "status": final_status, "restore_payloads": [], "restore_to": None,
        "resolve_note": note, "closed_at": now_iso()}})
    return True


async def _resolve_trade_offers() -> None:
    """Lazy settlement for the trade lane, on every trade read. LIN has no
    sweeper, so a TTL that only runs when somebody looks is the only TTL there
    is -- and the accept lane checks the clock itself, so a lagging pass can
    never let an expired offer settle.

    CONTAINED per row: one raising offer must not abort the pass and strand
    every sibling, which is the exact defect `_resolve_listings` was rebuilt
    around."""
    global _trade_resolve_last
    now = time.time()
    if (now - _trade_resolve_last) < TRADE_RESOLVE_EVERY_SECS:
        return
    _trade_resolve_last = now
    try:
        rows = await db.trade_offers.find(
            {"status": {"$in": ["pending", "restore_pending"]}}, {"_id": 0}).to_list(300)
    except Exception:
        logger.exception("[TRADE] resolve pass could not read offers")
        return
    for o in rows or []:
        try:
            if o.get("status") == "restore_pending":
                await _trade_close_with_restore(
                    o, o.get("restore_to") or o.get("from_id"),
                    o.get("restore_payloads") or [],
                    o.get("restore_next_status") or "expired", "restore_retry")
                continue
            try:
                if float(o.get("expires_at_ts") or 0) > now:
                    continue
            except (TypeError, ValueError):
                pass                     # unreadable clock -> treat as expired
            claimed = await db.trade_offers.find_one_and_update(
                {"id": o["id"], "status": "pending"},
                {"$set": {"status": "settling", "claimed_at": now,
                          "resolve_note": "ttl"}})
            if not claimed:
                continue
            await _trade_close_with_restore(o, o["from_id"],
                                            o.get("offer_payloads") or [], "expired", "ttl")
        except Exception:
            logger.exception("[TRADE] resolve FAILED for offer %s - siblings continue",
                             (o or {}).get("id"))
    await _reap_stuck_trades(now)


TRADE_REAP_AFTER_SECS = 300.0


async def _reap_stuck_trades(now: float) -> None:
    """THE RESTART BOUNDARY. A settle claim stranded by a process bounce sits in
    `settling` forever: the sender cannot cancel it, the receiver cannot accept
    it, and both are holding a cooldown they never spent.

    THE MARKERS SAY EXACTLY HOW FAR IT GOT, and where they say "we do not know"
    this parks the row for a human rather than guessing -- a guess here costs
    either a duplicated animal or a deleted one:
      no `to_escrow_at`      nothing of the receiver's moved. Put the offer back
                             and release both cooldown claims; the sender's
                             escrow is intact and the doc still holds it.
      `to_escrow_at` only    crashed INSIDE the receiver's escrow. Some rows may
                             be gone with only a journal line. needs_admin.
      `to_escrowed_at` set   both sides are out of both vaults and delivery may
                             have half happened. Re-running it could hand the
                             same animal out twice. needs_admin, both payload
                             sets retained on the doc."""
    cut = now - TRADE_REAP_AFTER_SECS
    try:
        stuck = await db.trade_offers.find({"status": "settling"}, {"_id": 0}).to_list(200)
    except Exception:
        logger.exception("[TRADE] reaper could not read settling offers")
        return
    for o in stuck or []:
        try:
            claimed_at = float(o.get("claimed_at") or 0)
        except (TypeError, ValueError):
            claimed_at = 0.0
        if claimed_at > cut:
            continue
        oid = o.get("id")
        try:
            if o.get("to_escrowed_at") or o.get("to_escrow_at"):
                note = ("delivery_outcome_unknown" if o.get("to_escrowed_at")
                        else "receiver_escrow_outcome_unknown")
                await db.trade_offers.update_one({"id": oid, "status": "settling"},
                                                 {"$set": {"status": "needs_admin",
                                                           "resolve_note": note}})
                logger.error("[TRADE] reap offer %s: %s -> needs_admin", oid, note)
                continue
            await _trade_cooldown_release(o.get("to_id"))
            await _trade_cooldown_release(o.get("from_id"))
            await db.trade_offers.update_one({"id": oid, "status": "settling"},
                                             {"$set": {"status": "pending", "claimed_at": None,
                                                       "resolve_note": "reaped_unstarted"}})
            logger.warning("[TRADE] reap offer %s: claimed but nothing moved -> pending", oid)
        except Exception:
            logger.exception("[TRADE] reap FAILED for offer %s", oid)


class TradeOfferInput(BaseModel):
    """A trade proposal. NOTE WHAT IS NOT HERE: there is no coins field, and
    there is no place to put one. A coin leg turns a trade into an untaxed sale
    and re-opens the fee the market charges."""
    # THE ONE FIELD THE REDESIGNED PAGE SENDS. A card id resolves the
    # counterparty AND the wanted animal server-side, which is what lets a
    # player trade without ever asking anybody for a row number. When it is
    # present, `to_*` and `want` are ignored: two sources for one fact is how
    # a page and a server end up disagreeing about who is being offered what.
    showcase_id: Optional[str] = None
    to_user_id: Optional[str] = None
    to_steam_id: Optional[str] = None
    to_name: Optional[str] = None
    # MY parked_dinos row ids (these get escrowed) and THEIRS (never touched).
    # Typed `Any` for the SAME reason `MarketListInput.price` is, and it is not
    # a style choice: pydantic v2 in lax mode turns `[True]` into `[1]` and
    # `["5"]` into `[5]`, so `List[int]` would hand this route a dino id of 1
    # that nobody typed, and answer every other wrong shape with an English 422.
    # `_trade_ids_or_400` validates the RAW value and owes one exact Spanish
    # sentence per wrong shape.
    offer: Any = None
    want: Any = None
    note: Optional[str] = None
    client_request_id: Any = None


class TradeActionInput(BaseModel):
    client_request_id: Any = None


def _trade_ids_or_400(raw, label: str, cap: int) -> list:
    """One side's animal list: whole ints, no duplicates, within the cap."""
    if not isinstance(raw, (list, tuple)) or not raw:
        raise HTTPException(status_code=400, detail=(
            f"Elige al menos un dinosaurio {label}."))
    if len(raw) > cap:
        raise HTTPException(status_code=400, detail=(
            f"Como máximo {cap} dinosaurio(s) por lado."))
    out = []
    for v in raw:
        if isinstance(v, bool) or not isinstance(v, int):
            raise HTTPException(status_code=400,
                                detail="Esa lista de dinosaurios no es válida.")
        if int(v) in out:
            raise HTTPException(status_code=400, detail=(
                "Repetiste el mismo dinosaurio en un lado del intercambio."))
        out.append(int(v))
    return out


async def _trade_partner_or_404(data: "TradeOfferInput", me: dict) -> dict:
    """Resolve the counterparty. Wrong-id and does-not-exist answer the SAME
    404: the trade page is not an existence oracle for other people's accounts."""
    q = None
    if data.to_user_id:
        q = {"id": str(data.to_user_id).strip()}
    elif data.to_steam_id:
        q = {"steam_id": str(data.to_steam_id).strip()}
    elif data.to_name:
        q = {"persona_name": str(data.to_name).strip()}
    if not q:
        raise HTTPException(status_code=400, detail="Elige con quién quieres intercambiar.")
    other = await db.users.find_one(q, {"_id": 0})
    if not other:
        raise HTTPException(status_code=404, detail="No encontramos a ese jugador.")
    if _same_person(other, me):
        # BOTH IDENTITIES. Trading with your own alt is how a per-player
        # cooldown gets laundered into no cooldown at all.
        raise HTTPException(status_code=400, detail="No puedes intercambiar contigo mismo.")
    return other


async def _trade_rows_or_404(cfg, sid: str, dino_ids: list, *, mine: bool,
                             exclude_offer: str = ""):
    """Read one side's parked rows and run every per-animal rule on them.

    The SAME gates the market list lane runs, in the same order, because a rule
    that only one of the two lanes enforces is a rule with a door beside it."""
    rows = []
    for did in dino_ids:
        row = await asyncio.to_thread(vault.get_parked_by_id, int(did))
        if not row or str(row.get("steam_id")) != str(sid):
            raise HTTPException(status_code=404, detail=(
                "Uno de esos dinosaurios ya no está en la bóveda de su dueño."
                if not mine else "Ese dinosaurio guardado no te pertenece o no existe."))
        row = await asyncio.to_thread(vault.resolve_stale_redeem_pending, row)
        if not row:
            raise HTTPException(status_code=404, detail=(
                "Ese dinosaurio guardado ya no está disponible."))
        if str(row.get("redeem_pending_cmd_id") or "").strip():
            raise HTTPException(status_code=409, detail=(
                "Ese dinosaurio tiene una recuperación en progreso; no se puede "
                "intercambiar ahora."))
        if _knob_bool(cfg, "trade_growth_gate"):
            _market_growth_gate_or_409(cfg, _growth_pct_exact(row.get("growth"), "vault"))
        await _move_cooldown_or_429(cfg, sid, row, int(did))
        held = await _pending_trade_hold(sid, did, exclude_offer)
        if held:
            raise HTTPException(status_code=409, detail=(
                "Ese dinosaurio ya está en otra oferta de intercambio. Cancélala primero."))
        rows.append(row)
    return rows


@api_router.get("/trade/config")
async def trade_config(user=Depends(get_current_user)):
    """Every rule the trade page renders, from the server. A page that pins its
    own copy of a rule is a page that will one day disagree with the server
    about it -- and here that disagreement costs somebody an animal."""
    cfg = await _mcfg()
    out = {"enabled": _trade_enabled(cfg),
           "max_items_per_side": _knob_int(cfg, "trade_max_items_per_side", 1, 5),
           "symmetry_pct": _knob_int(cfg, "trade_symmetry_pct", 0, 100),
           "max_open_offers": _knob_int(cfg, "trade_max_open_offers", 1, 25),
           "growth_gate": _knob_bool(cfg, "trade_growth_gate"),
           "min_growth_pct": _knob_int(cfg, "min_growth_pct", 0, 100),
           "max_board_per_player": _trade_board_cap(cfg),
           "coins_allowed": False}
    for key, fn in (("cooldown_secs", _trade_cooldown_secs), ("offer_ttl_secs", _trade_ttl_secs),
                    ("dino_move_cooldown_secs", _move_cooldown_secs),
                    ("board_ttl_secs", _trade_board_ttl_secs)):
        try:
            out[key] = fn(cfg)
        except HTTPException as exc:
            out[key] = None
            out[key + "_error"] = exc.detail
    try:
        state = await _trade_cooldown_state(cfg, user["id"])
    except HTTPException:
        state = None
    out["my_cooldown_until"] = state["until"] if state else None
    out["my_cooldown_left"] = (max(0, int(math.ceil(state["until"] - time.time())))
                               if state else 0)
    return out


@api_router.get("/trade/lookup")
async def trade_lookup(q: str = "", user=Depends(get_current_user)):
    """Resolve ONE player by exact name or steam id, so the page can address an
    offer. EXACT match only and one row at a time: this is an addressing helper,
    not a player directory, and a prefix search here would be a roster export."""
    needle = str(q or "").strip()
    if not needle:
        raise HTTPException(status_code=400, detail="Escribe el nombre o el Steam ID.")
    other = await db.users.find_one(
        {"$or": [{"persona_name": needle}, {"steam_id": needle}, {"id": needle}]}, {"_id": 0})
    if not other or _same_person(other, user):
        raise HTTPException(status_code=404, detail="No encontramos a ese jugador.")
    return {"id": other.get("id"), "name": other.get("persona_name"),
            "avatar": other.get("avatar"), "linked": bool(str(other.get("steam_id") or "").strip())}


@api_router.get("/trade/mine")
async def trade_mine(user=Depends(get_current_user)):
    """My offers, both directions, plus what I am allowed to do right now."""
    await _resolve_trade_offers()
    cfg = await _mcfg()
    try:
        rows = await db.trade_offers.find(
            {"$or": [{"from_id": user["id"]}, {"to_id": user["id"]}]}, {"_id": 0}
        ).to_list(200)
    except Exception:
        logger.exception("[TRADE] could not read offers for %s", user["id"])
        rows = []
    rows = sorted(rows, key=lambda o: str(o.get("created_at") or ""), reverse=True)
    incoming = [_trade_public(o, user["id"]) for o in rows
                if o.get("to_id") == user["id"] and o.get("status") == "pending"]
    outgoing = [_trade_public(o, user["id"]) for o in rows
                if o.get("from_id") == user["id"] and o.get("status") == "pending"]
    history = [_trade_public(o, user["id"]) for o in rows if o.get("status") != "pending"][:50]
    sid = str(user.get("steam_id") or "").strip()
    try:
        state = await _trade_cooldown_state(cfg, user["id"])
    except HTTPException:
        state = None
    return {"incoming": incoming, "outgoing": outgoing, "history": history,
            "cooldown_left": (max(0, int(math.ceil(state["until"] - time.time())))
                              if state else 0),
            # Clamped HERE and only here: a page renders "0 free", never "-2".
            "slots_free": (max(0, await _trade_slots_free(user, sid)) if sid else 0),
            "reserved_slots": (await _reserved_park_slots(sid) if sid else 0)}


@api_router.post("/trade/offer")
async def trade_create(data: TradeOfferInput, user=Depends(get_current_user)):
    """Send a trade offer. EVERY rule is checked BEFORE the first animal moves,
    and the escrow is the last thing that happens."""
    await _resolve_trade_offers()
    cfg = await _mcfg()
    rid = _client_request_id(data.client_request_id)
    # The scope is formatted, never ITERATED: `offer` is typed `Any` (see
    # TradeOfferInput), so a client sending `"offer": 5` must reach the Spanish
    # refusal in _trade_ids_or_400 rather than a TypeError out of this line.
    op_scope = "trade:new:%.80s" % (data.offer,)
    replayed = await _market_op_peek("trade", user, rid, op_scope)
    if replayed is not None:
        return replayed
    if not _trade_enabled(cfg):
        raise HTTPException(status_code=503,
                            detail="Los intercambios están desactivados por ahora.")
    _market_write_gate(cfg, user["id"])
    sid = _steam_id_or_400(user)
    # THE BOARD LANE. One card id, and the server reads BOTH the other player
    # and the animal being asked for off the card -- the sender never learns,
    # types or guesses a row number, and cannot name an animal its owner did
    # not put in the window.
    card = None
    if data.showcase_id:
        card = await _trade_board_open_or_404(data.showcase_id)
        if card.get("owner_id") == user["id"]:
            raise HTTPException(status_code=400, detail=(
                "Esa publicación es tuya. Quítala si ya no quieres intercambiarlo."))
        other = await db.users.find_one({"id": card.get("owner_id")}, {"_id": 0})
        if not other:
            raise HTTPException(status_code=404, detail="No encontramos a ese jugador.")
        if _same_person(other, user):
            raise HTTPException(status_code=400, detail="No puedes intercambiar contigo mismo.")
    else:
        other = await _trade_partner_or_404(data, user)
    other_sid = str(other.get("steam_id") or "").strip()
    if not other_sid:
        raise HTTPException(status_code=409, detail=(
            "Ese jugador todavía no vinculó su cuenta de Steam, así que no puede "
            "intercambiar."))
    per_side = _knob_int(cfg, "trade_max_items_per_side", 1, 5)
    mine_ids = _trade_ids_or_400(data.offer, "tuyo", per_side)
    theirs_ids = (_trade_ids_or_400([card.get("dino_id")], "suyo", per_side) if card
                  else _trade_ids_or_400(data.want, "suyo", per_side))
    if len(mine_ids) != len(theirs_ids):
        # N-FOR-N. The value band already governs fairness; equal counts is what
        # keeps the park cap arithmetic true on BOTH sides of the settle.
        raise HTTPException(status_code=400, detail=(
            f"Un intercambio es {len(mine_ids)} por {len(mine_ids)}: ofreces "
            f"{len(mine_ids)} y pides {len(theirs_ids)}."))
    # BOTH COOLDOWNS, before anything is escrowed. Refusing here costs a click;
    # refusing after the escrow costs a restore.
    await _trade_cooldown_or_429(cfg, user, "self")
    await _trade_cooldown_or_429(cfg, other, "other")
    open_cap = _knob_int(cfg, "trade_max_open_offers", 1, 25)
    try:
        live = await db.trade_offers.count_documents({"from_id": user["id"], "status": "pending"})
    except Exception:
        logger.exception("[TRADE] open-offer count failed for %s", user["id"])
        live = 0
    if live >= open_cap:
        raise HTTPException(status_code=409, detail=(
            f"Ya tienes {open_cap} ofertas abiertas. Cancela una antes de enviar otra."))
    if card is not None:
        # ONE OPEN OFFER PER CARD PER SENDER. The page hides the button once an
        # offer is out, but a rule only the page enforces is not a rule -- and
        # without this, an impatient double press escrows a second animal.
        try:
            already = await db.trade_offers.find_one(
                {"from_id": user["id"], "board_id": card["id"], "status": "pending"},
                {"_id": 0, "id": 1})
        except Exception:
            logger.exception("[BOARD] repeat-offer check failed for card %s", card["id"])
            already = None
        if already:
            raise HTTPException(status_code=409, detail=(
                "Ya tienes una oferta abierta por ese dinosaurio. Espera la respuesta "
                "o cancélala."))
    mine_rows = await _trade_rows_or_404(cfg, sid, mine_ids, mine=True)
    theirs_rows = await _trade_rows_or_404(cfg, other_sid, theirs_ids, mine=False)
    offer_items = [_trade_item_view(cfg, r) for r in mine_rows]
    want_items = [_trade_item_view(cfg, r) for r in theirs_rows]
    bad = [it for it in offer_items + want_items if it["value_error"]]
    if bad:
        raise HTTPException(status_code=503, detail=bad[0]["value_error"])
    offer_value = _trade_side_value(offer_items)
    want_value = _trade_side_value(want_items)
    if not _trade_symmetry_ok(cfg, offer_value, want_value):
        pct = _knob_int(cfg, "trade_symmetry_pct", 0, 100)
        raise HTTPException(status_code=409, detail=(
            f"Ese intercambio no está equilibrado: ofreces {_es_num(offer_value)} y pides "
            f"{_es_num(want_value)}. Los dos lados deben quedar dentro del {pct}%."))
    # ★★ THE SLOT THE ESCROW IS ABOUT TO FREE IS RESERVED, so this player can
    # still receive at settle even if they refill the vault in the meantime.
    # Escrowing n moves n out of `used` and n into `reserved`, so the number
    # below does not move at all when the offer goes out -- what it has to be is
    # NOT NEGATIVE, i.e. this player is not already promising more animals than
    # they have slots to receive them in.
    free = await _trade_slots_free(user, sid)
    if free < 0:
        raise HTTPException(status_code=409, detail=(
            f"Tienes {-free} espacio(s) de bóveda de más comprometidos en ofertas o "
            f"publicaciones abiertas. Cierra una antes de enviar otra."))
    ttl = _trade_ttl_secs(cfg)
    now = time.time()
    offer = {
        "id": new_id(), "status": "pending",
        "from_id": user["id"], "from_name": user.get("persona_name"), "from_steam": sid,
        "to_id": other.get("id"), "to_name": other.get("persona_name"), "to_steam": other_sid,
        "offer_items": offer_items, "want_items": want_items,
        "offer_payloads": [dict(r) for r in mine_rows],
        "offer_value": offer_value, "want_value": want_value,
        "symmetry_pct": _knob_int(cfg, "trade_symmetry_pct", 0, 100),
        "note": _market_clean_title(data.note) or None,
        "created_at": now_iso(), "expires_at_ts": now + ttl,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(),
        "client_request_id": rid or None, "restore_attempts": 0,
        "restore_payloads": [], "restore_to": None,
        # Which card this came from, or None for an addressed offer. The board
        # counts open offers off this field and the page hides a button with it.
        "board_id": (card["id"] if card else None),
    }
    op_ref, replayed = await _market_op_take("trade", user, rid, op_scope, 0)
    if replayed is not None:
        return replayed
    await db.trade_offers.insert_one(offer)
    taken, refusal = await _trade_escrow_take(offer["id"], sid, user["id"], mine_rows)
    if refusal is not None:
        # UNWIND FIRST. Whatever left the vault goes back before the offer doc
        # does, and an unrestorable animal keeps the doc alive as a retry rather
        # than deleting the only record of where it went.
        back, lost = await _trade_restore(offer["id"], user["id"], taken)
        if lost:
            await db.trade_offers.update_one({"id": offer["id"]}, {"$set": {
                "status": "restore_pending", "restore_to": user["id"],
                "restore_payloads": lost, "restore_next_status": "cancelled",
                "resolve_note": "escrow_unwind"}})
            logger.error("[TRADE] offer %s: escrow failed AND %s animal(s) could not be "
                         "restored - retrying", offer["id"], len(lost))
        else:
            await db.trade_offers.delete_one({"id": offer["id"]})
        await _market_op_reversed(op_ref, refusal)
        raise refusal
    logger.info("[TRADE] offer %s %s -> %s  %s for %s (%s vs %s)", offer["id"],
                user["id"], other.get("id"), len(mine_ids), len(theirs_ids),
                offer_value, want_value)
    result = {"success": True, "offer": _trade_public(offer, user["id"])}
    await _market_op_done(op_ref, result)
    return result


@api_router.post("/trade/{offer_id}/cancel")
async def trade_cancel(offer_id: str, data: Optional[TradeActionInput] = None,
                       user=Depends(get_current_user)):
    """The SENDER pulls their own offer back. Free -- the animal was never sold,
    and charging for a change of mind would leave offers open out of spite."""
    return await _trade_close(offer_id, user, actor="from", final="cancelled")


@api_router.post("/trade/{offer_id}/decline")
async def trade_decline(offer_id: str, data: Optional[TradeActionInput] = None,
                        user=Depends(get_current_user)):
    """The RECEIVER says no. Same machinery as cancel: the escrow goes home."""
    return await _trade_close(offer_id, user, actor="to", final="declined")


async def _trade_close(offer_id: str, user, *, actor: str, final: str) -> dict:
    """Cancel and decline are ONE code path with one claim, because they differ
    only in who is allowed to press the button."""
    await _resolve_trade_offers()
    o = await db.trade_offers.find_one({"id": offer_id}, {"_id": 0})
    if not o:
        raise HTTPException(status_code=404, detail="Esa oferta ya no existe.")
    owner_id = o.get("from_id") if actor == "from" else o.get("to_id")
    if owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="Esa oferta no es tuya.")
    if o.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Esa oferta ya no está abierta.")
    # ATOMIC CLAIM. Of two clicks exactly one gets to move the animals back.
    claimed = await db.trade_offers.find_one_and_update(
        {"id": offer_id, "status": "pending"},
        {"$set": {"status": "settling", "claimed_at": time.time(), "resolve_note": final}})
    if not claimed:
        raise HTTPException(status_code=409, detail="Esa oferta ya no está abierta.")
    ok = await _trade_close_with_restore(o, o["from_id"], o.get("offer_payloads") or [],
                                         final, final)
    fresh = await db.trade_offers.find_one({"id": offer_id}, {"_id": 0}) or {}
    return {"success": True, "restored": ok, "offer": _trade_public(fresh, user["id"])}


@api_router.post("/trade/{offer_id}/accept")
async def trade_accept(offer_id: str, data: Optional[TradeActionInput] = None,
                       user=Depends(get_current_user)):
    """Accept an offer and settle it. RE-VALIDATED AGAINST TODAY'S RULES.

    An offer is a proposal, not a ticket that outlives the rules it was written
    under: growth gate, both cooldowns, the value band, the park cap and plain
    ownership are all checked again HERE, on the numbers as they stand now.

    ORDER, and every step of it is deliberate:
      1. read + authorise + clock                (nothing has moved)
      2. re-validate everything                  (nothing has moved)
      3. ATOMIC CLAIM pending -> settling        <- an offer accepted twice
      4. CLAIM BOTH COOLDOWNS                    <- two offers settled at once
      5. escrow the receiver's animals           (write-ahead, then delete)
      6. deliver both sides, stamping the per-ANIMAL clock as each lands
    A failure after 4 releases the claims and puts the offer back, so an honest
    retry is not locked out for 24 hours by a refusal."""
    data = data or TradeActionInput()
    await _resolve_trade_offers()
    cfg = await _mcfg()
    rid = _client_request_id(data.client_request_id)
    op_scope = "trade:accept:%s" % offer_id
    replayed = await _market_op_peek("trade_accept", user, rid, op_scope)
    if replayed is not None:
        return replayed
    if not _trade_enabled(cfg):
        raise HTTPException(status_code=503,
                            detail="Los intercambios están desactivados por ahora.")
    o = await db.trade_offers.find_one({"id": offer_id}, {"_id": 0})
    if not o:
        raise HTTPException(status_code=404, detail="Esa oferta ya no existe.")
    if o.get("to_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Esa oferta no es para ti.")
    if o.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Esa oferta ya no está abierta.")
    # THE CLOCK IS THE LAW AT REQUEST TIME, independent of when the lazy pass
    # last ran -- exactly the defect the auction lane was rebuilt around.
    try:
        if float(o.get("expires_at_ts") or 0) <= time.time():
            raise HTTPException(status_code=409, detail="Esa oferta ya expiró.")
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Esa oferta ya no es válida.")
    sender = await db.users.find_one({"id": o.get("from_id")}, {"_id": 0})
    if not sender:
        raise HTTPException(status_code=409, detail="El otro jugador ya no existe.")
    my_sid = _steam_id_or_400(user)
    sender_sid = str(sender.get("steam_id") or "").strip()
    if not sender_sid:
        raise HTTPException(status_code=409, detail=(
            "El otro jugador ya no tiene su cuenta de Steam vinculada."))
    # --- 2. TODAY'S RULES ----------------------------------------------------
    await _trade_cooldown_or_429(cfg, user, "self")
    await _trade_cooldown_or_429(cfg, sender, "other")
    want_ids = [int(it.get("dino_id") or 0) for it in (o.get("want_items") or [])]
    my_rows = await _trade_rows_or_404(cfg, my_sid, want_ids, mine=True,
                                       exclude_offer=offer_id)
    payloads = [dict(p) for p in (o.get("offer_payloads") or [])]
    if len(payloads) != len(my_rows):
        raise HTTPException(status_code=409, detail=(
            "Esa oferta ya no cuadra. Pídele a quien la envió que la vuelva a hacer."))
    # The ESCROWED side is re-priced from its stored payload, and its per-animal
    # move cooldown is re-checked against the RECEIVER's steam id, because that
    # is who is about to own it.
    offer_items = [_trade_item_view(cfg, p) for p in payloads]
    want_items = [_trade_item_view(cfg, r) for r in my_rows]
    bad = [it for it in offer_items + want_items if it["value_error"]]
    if bad:
        raise HTTPException(status_code=503, detail=bad[0]["value_error"])
    if _knob_bool(cfg, "trade_growth_gate"):
        for p in payloads:
            _market_growth_gate_or_409(cfg, _growth_pct_exact(p.get("growth"), "vault"))
    offer_value = _trade_side_value(offer_items)
    want_value = _trade_side_value(want_items)
    if not _trade_symmetry_ok(cfg, offer_value, want_value):
        pct = _knob_int(cfg, "trade_symmetry_pct", 0, 100)
        raise HTTPException(status_code=409, detail=(
            f"Ese intercambio ya no está equilibrado ({_es_num(offer_value)} contra "
            f"{_es_num(want_value)}; el límite es {pct}%). Pídele una oferta nueva."))
    n = len(payloads)
    # PARK CAP, both sides, with escrow reserved. The receiver frees n slots the
    # instant their own animals are escrowed, so they need free >= 0; the sender
    # is receiving into slots THIS offer's escrow is holding for them, which is
    # why their own offer is excluded from the reservation count.
    if await _trade_slots_free(user, my_sid) < 0:
        raise HTTPException(status_code=409, detail=(
            "Tu bóveda está llena. Libera un espacio antes de aceptar."))
    if await _trade_slots_free(sender, sender_sid, o["id"]) < n:
        raise HTTPException(status_code=409, detail=(
            "La bóveda del otro jugador está llena; no puede recibir el intercambio "
            "ahora mismo."))
    # --- 3. THE CLAIM --------------------------------------------------------
    claimed = await db.trade_offers.find_one_and_update(
        {"id": offer_id, "status": "pending"},
        {"$set": {"status": "settling", "claimed_at": time.time(),
                  "accepted_by": user["id"], "accepted_at": now_iso()}})
    if not claimed:
        # ACCEPTED TWICE. The second one lands here having moved nothing.
        raise HTTPException(status_code=409, detail="Esa oferta ya no está abierta.")

    async def _put_back(note: str, exc: HTTPException):
        await _trade_cooldown_release(user["id"])
        await _trade_cooldown_release(o["from_id"])
        await db.trade_offers.update_one({"id": offer_id, "status": "settling"},
                                         {"$set": {"status": "pending", "claimed_at": None,
                                                   "resolve_note": note}})
        await _market_op_reversed(op_ref, exc)
        return exc

    try:
        op_ref, replayed = await _market_op_take("trade_accept", user, rid, op_scope, 0)
    except HTTPException:
        # The attempt ledger refused (a concurrent submit of the SAME id). The
        # offer claim above has already flipped this row to `settling` and
        # nothing has moved, so it goes straight back rather than waiting five
        # minutes for the reaper to work that out.
        await db.trade_offers.update_one({"id": offer_id, "status": "settling"},
                                         {"$set": {"status": "pending", "claimed_at": None,
                                                   "resolve_note": "op_claim_conflict"}})
        raise
    if replayed is not None:
        await db.trade_offers.update_one({"id": offer_id, "status": "settling"},
                                         {"$set": {"status": "pending", "claimed_at": None}})
        return replayed
    # --- 4. BOTH COOLDOWNS, CLAIMED BEFORE ANYTHING MOVES --------------------
    if not await _trade_cooldown_claim(cfg, user["id"], "trade:%s" % offer_id):
        raise await _put_back("cooldown_lost_self", HTTPException(
            status_code=429, detail="Ya tienes un intercambio en curso. Espera un momento."))
    if not await _trade_cooldown_claim(cfg, o["from_id"], "trade:%s" % offer_id):
        await _trade_cooldown_release(user["id"])
        raise await _put_back("cooldown_lost_other", HTTPException(
            status_code=429, detail=(
                "El otro jugador acaba de intercambiar. Inténtalo más tarde.")))
    # --- 5. ESCROW THE RECEIVER'S SIDE --------------------------------------
    await db.trade_offers.update_one({"id": offer_id}, {"$set": {"to_escrow_at": now_iso()}})
    taken, refusal = await _trade_escrow_take(offer_id, my_sid, user["id"], my_rows)
    if refusal is not None:
        back, lost = await _trade_restore(offer_id, user["id"], taken)
        if lost:
            await db.trade_offers.update_one({"id": offer_id}, {"$set": {
                "status": "restore_pending", "restore_to": user["id"],
                "restore_payloads": lost, "restore_next_status": "needs_admin",
                "resolve_note": "accept_escrow_unwind"}})
            await _trade_cooldown_release(user["id"])
            await _trade_cooldown_release(o["from_id"])
            await _market_op_reversed(op_ref, refusal)
            raise refusal
        raise await _put_back("accept_escrow_failed", refusal)
    await db.trade_offers.update_one({"id": offer_id}, {"$set": {
        "to_escrowed_at": now_iso(), "want_payloads": [dict(r) for r in my_rows]}})
    # --- 6. DELIVER BOTH SIDES ----------------------------------------------
    # Both halves are already OUT of every vault, so neither player can act on
    # them while this runs; a crash between the two leaves the payloads on the
    # doc and the retry pass finishes the job.
    stranded = []
    for target_id, target_sid, items, label in (
            (user["id"], my_sid, payloads, "to"),
            (o["from_id"], sender_sid, [dict(r) for r in my_rows], "from")):
        for p in items:
            gave: dict = {}
            ok = False
            try:
                ok = await _give_dino(target_id, {"id": "trade:%s" % offer_id, "source": "vault",
                                                  "vault_payload": dict(p),
                                                  "status": "settling"}, out=gave)
            except Exception:
                logger.exception("[TRADE] delivery raised offer=%s -> %s", offer_id, target_id)
            if not ok:
                stranded.append({"user_id": target_id, "payload": p})
                continue
            # THE ANIMAL CHANGED HANDS: start its clock, on BOTH keys, exactly
            # as a market sale does. Without this the trade lane is the uncooled
            # laundering path sitting beside a cooled market.
            await _move_cooldown_stamp(cfg, target_sid, p, gave.get("new_row_id"),
                                       why="trade:%s" % offer_id)
    if stranded:
        # RETRIED, NEVER TERMINAL. The payloads stay on the doc and the resolve
        # pass keeps trying; nobody's animal is written off.
        await db.trade_offers.update_one({"id": offer_id}, {"$set": {
            "status": "restore_pending",
            "restore_to": stranded[0]["user_id"],
            "restore_payloads": [s["payload"] for s in stranded],
            "restore_next_status": "accepted", "resolve_note": "delivery_incomplete",
            "settled_at": now_iso(), "offer_value": offer_value, "want_value": want_value}})
        logger.error("[TRADE] offer %s settled with %s undelivered animal(s) - RETRYING",
                     offer_id, len(stranded))
    else:
        await db.trade_offers.update_one({"id": offer_id}, {"$set": {
            "status": "accepted", "settled_at": now_iso(), "closed_at": now_iso(),
            "offer_value": offer_value, "want_value": want_value,
            "resolve_note": "settled"}})
        logger.info("[TRADE] offer %s SETTLED %s <-> %s (%s for %s)", offer_id,
                    o["from_id"], user["id"], offer_value, want_value)
    # THE CARD COMES DOWN. The animal it advertised is in somebody else's vault
    # now, so the window is a lie the moment this returns. The resolve pass
    # would catch it within 30 s anyway (the row is gone from this owner's
    # vault) -- this just closes it on the instant it stops being true, and
    # records WHY, which "gone" would not.
    if o.get("board_id"):
        await _trade_board_close(o["board_id"], "traded")
    fresh = await db.trade_offers.find_one({"id": offer_id}, {"_id": 0}) or {}
    result = {"success": True, "settled": not stranded,
              "offer": _trade_public(fresh, user["id"])}
    await _market_op_done(op_ref, result)
    return result


# ─────────────── THE TRADE BOARD — trading where the dinos are sold ──────────
# 2026-08-11, his words: "redesign so dinosaurs get traded on the same tab
# people can see dinos for sale. no need to send anybody anything."
#
# WHAT WAS WRONG WITH THE FIRST BUILD. An offer had to be ADDRESSED: the sender
# looked a player up by exact name and then TYPED that player's parked row
# numbers -- numbers NO route on this backend will hand out, so the only way to
# learn one was to message the other player somewhere else and ask. The rules
# were right and the door was unreachable. That is the "no need to send anybody
# anything" in his sentence, and it is a defect, not a preference.
#
# THE FIX IS A SHOP WINDOW, NOT A SECOND SETTLEMENT LANE. A player publishes a
# parked animal as open to offers; it renders in the market grid beside the
# sales and the auctions; a visitor presses one button and picks an animal of
# their own. `showcase_id` on POST /trade/offer resolves BOTH the counterparty
# and the wanted animal server-side, so a row number is never typed, never
# guessed, and -- see `_trade_board_public` -- never published to anybody but
# the animal's own owner.
#
# ★★ A BOARD ENTRY ESCROWS NOTHING. The animal stays parked, redeemable and
# sellable; the entry is an advertisement over the top of it. That is precisely
# what makes this safe to add beside the money lanes: the trade settlement, its
# write-ahead journal, both cooldowns and the park-cap arithmetic are UNTOUCHED
# by this section, and every rule is still enforced exactly where it was -- when
# the offer is sent, and again when it is accepted, against the live vault.
# The worst a stale card can cost anybody is a refusal with an exact sentence.

TRADE_BOARD_RESOLVE_EVERY_SECS = 30.0
_trade_board_resolve_last = 0.0


def _trade_board_ttl_secs(cfg) -> int:
    """How long a card stays up. REFUSE: a card that outlives its rules is a
    promise nobody can keep, and a clamp here would silently pick a window the
    owner did not choose."""
    return _knob_refuse_int(cfg, "trade_board_ttl_secs", 3_600, 604_800,
                            label="La duración de las publicaciones de intercambio "
                                  "está mal configurada")


def _trade_board_cap(cfg) -> int:
    return _knob_int(cfg, "trade_max_board_per_player", 1, 25)


def _trade_board_view(cfg, row: dict) -> dict:
    """The DISPLAY half of one card, derived from a parked row. Everything here
    is recomputed by the resolve pass, so a card cannot drift away from the
    animal it advertises while nobody is looking."""
    item = _trade_item_view(cfg, row)
    slug = item["slug"]
    return {"dino_slug": slug, "species": item["species"],
            "dino_name": item["species"] or "Dinosaurio",
            "growth_pct": item["growth_pct"], "growth_pct_exact": item["growth_pct_exact"],
            "priced_mutations": item["mutations"], "prime": item["prime"],
            "is_elder": bool(row.get("is_elder")),
            "skin_view": vault._parked_skin(row.get("skin_data")),
            "verify": _market_verify_view(row),
            "fingerprint": item["fingerprint"],
            "value": item["value"], "value_error": item["value_error"]}


def _trade_board_public(e: dict, viewer_id: str = "") -> dict:
    """One card as a visitor may read it.

    ★★ THE ROW NUMBER NEVER LEAVES for anybody but the owner. Publishing a card
    is opting an ANIMAL into being offered on, not opting its id into a public
    directory -- the offer lane takes `showcase_id` and looks the id up itself.
    The FIRST build's whole problem was that this number had to travel between
    two players by hand; the answer is not to broadcast it, it is to stop
    needing it.

    The key names deliberately mirror `_market_public`, so ONE card component in
    the frontend renders a sale, an auction and a trade without a second shape
    to keep in step. `type: "trade"` is what tells them apart."""
    mine = bool(viewer_id and e.get("owner_id") == viewer_id)
    d = {k: e.get(k) for k in (
        "id", "title", "note", "dino_slug", "dino_name", "image", "rarity",
        "species", "growth_pct", "priced_mutations", "prime", "is_elder",
        "skin_view", "verify", "created_at", "ends_at", "value")}
    d["type"] = "trade"
    d["source"] = "vault"
    d["seller_name"] = e.get("owner_name")
    d["seller_id"] = e.get("owner_id") if mine else None
    d["mine"] = mine
    # Published under both names for the same reason the market publishes it
    # twice: `mutations_count` is what the shipped card already renders.
    d["mutations_count"] = e.get("priced_mutations")
    d["dino_id"] = e.get("dino_id") if mine else None
    d["offers"] = int(e.get("offers") or 0)
    return d


async def _resolve_trade_board() -> None:
    """Expire, refresh and retire board cards. Lazy, like every other resolve
    pass on this box -- LIN has no sweeper.

    ★★ THROTTLED ON PURPOSE, and this is the load-bearing decision in the whole
    section: this pass is the ONLY thing that reads sqlite for the board, and
    the market page polls every 8 seconds per open tab. Validating each card
    per request would put N parked-row reads behind every poll of every viewer.
    A card can therefore be at most 30 s stale, which costs an exact refusal and
    nothing else, because the offer lane re-reads the live vault anyway.

    CONTAINED per row: one unreadable card must not strand its siblings, which
    is the defect `_resolve_listings` was rebuilt around."""
    global _trade_board_resolve_last
    now = time.time()
    if (now - _trade_board_resolve_last) < TRADE_BOARD_RESOLVE_EVERY_SECS:
        return
    _trade_board_resolve_last = now
    try:
        rows = await db.trade_board.find({"status": "active"}, {"_id": 0}).to_list(300)
    except Exception:
        logger.exception("[BOARD] resolve pass could not read cards")
        return
    if not rows:
        return
    cfg = await _mcfg()
    for e in rows or []:
        try:
            try:
                if float(e.get("expires_at_ts") or 0) <= now:
                    await _trade_board_close(e["id"], "ttl")
                    continue
            except (TypeError, ValueError):
                await _trade_board_close(e["id"], "bad_clock")
                continue
            row = await asyncio.to_thread(vault.get_parked_by_id, int(e.get("dino_id") or 0))
            # GONE, or in somebody else's hands: sold, redeemed, traded away, or
            # a row id that sqlite handed to a different animal after a delete.
            # The fingerprint is what catches that last one -- an id alone is
            # not an identity here.
            if not row or str(row.get("steam_id") or "") != str(e.get("owner_steam") or ""):
                await _trade_board_close(e["id"], "gone")
                continue
            view = _trade_board_view(cfg, row)
            if view["value_error"]:
                # Its price cannot be computed today (a broken knob, an unknown
                # species). An offer on it would be refused at 503 anyway, so the
                # card comes down rather than advertising a value it does not have.
                await _trade_board_close(e["id"], "unpriced")
                continue
            changed = {k: v for k, v in view.items()
                       if k not in ("value_error",) and e.get(k) != v}
            if changed:
                # REFRESHED, NOT RETIRED. A mutation edit or a knob change makes
                # the stored card wrong, and the honest answer is to redraw it,
                # not to punish the owner by taking their card down.
                await db.trade_board.update_one({"id": e["id"], "status": "active"},
                                                {"$set": changed})
        except Exception:
            logger.exception("[BOARD] resolve FAILED for card %s - siblings continue",
                             (e or {}).get("id"))


async def _trade_board_close(entry_id: str, note: str) -> None:
    try:
        await db.trade_board.update_one(
            {"id": entry_id, "status": "active"},
            {"$set": {"status": "closed", "close_note": note, "closed_at": now_iso()}})
    except Exception:
        logger.exception("[BOARD] could not close card %s (%s)", entry_id, note)


async def _trade_board_open_or_404(entry_id: str) -> dict:
    """One ACTIVE card, by id. A closed card and a card that never existed
    answer the same 404: the board is not an existence oracle either."""
    try:
        e = await db.trade_board.find_one({"id": str(entry_id or "").strip(),
                                           "status": "active"}, {"_id": 0})
    except Exception:
        logger.exception("[BOARD] card read failed for %s", entry_id)
        e = None
    if not e:
        raise HTTPException(status_code=404, detail=(
            "Esa publicación de intercambio ya no está disponible. Actualiza la página."))
    return e


class TradeBoardInput(BaseModel):
    """Put one of MY parked animals in the window. `dino_id` is typed `Any` for
    the same reason every other id on this backend is: pydantic in lax mode
    turns `True` into 1 and `"5"` into 5, and this route owes one exact Spanish
    sentence per wrong shape rather than an English 422."""
    dino_id: Any = None
    title: Optional[str] = None
    note: Optional[str] = None
    client_request_id: Any = None


def _board_dino_id_or_400(raw) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise HTTPException(status_code=400, detail="Elige un dinosaurio para publicar.")
    return int(raw)


@api_router.get("/trade/board")
async def trade_board(user=Depends(get_current_user)):
    """Every animal currently open to offers, newest first, plus the two rules
    the publish button needs. Signed-in only -- the same bar the market page
    already sets, and a board readable by nobody in particular is a roster of
    who owns what."""
    await _resolve_trade_board()
    cfg = await _mcfg()
    try:
        rows = await db.trade_board.find({"status": "active"}, {"_id": 0}
                                         ).sort("created_at", -1).to_list(200)
    except Exception:
        logger.exception("[BOARD] could not read the board")
        rows = []
    cards = [_trade_board_public(e, user["id"]) for e in rows]
    # ONE read answers both questions the page asks about offers: how many are
    # open on each card, and whether THIS viewer already sent one. Without the
    # second, the page shows a live "Ofrecer" button for an offer they already
    # have out, and the press earns a refusal they did not deserve to see.
    try:
        pend = await db.trade_offers.find(
            {"status": "pending", "board_id": {"$ne": None}},
            {"_id": 0, "board_id": 1, "from_id": 1}).to_list(500)
    except Exception:
        logger.exception("[BOARD] could not read pending offers for the board")
        pend = []
    counts: dict = {}
    offered = set()
    for o in pend or []:
        bid = str(o.get("board_id") or "")
        if not bid:
            continue
        counts[bid] = counts.get(bid, 0) + 1
        if o.get("from_id") == user["id"]:
            offered.add(bid)
    for c in cards:
        c["offers"] = counts.get(c["id"], 0)
        c["offered"] = c["id"] in offered
    out = {"cards": cards, "max_per_player": _trade_board_cap(cfg),
           "mine": len([c for c in cards if c["mine"]]), "ttl_secs": None,
           "ttl_secs_error": None}
    try:
        out["ttl_secs"] = _trade_board_ttl_secs(cfg)
    except HTTPException as exc:
        out["ttl_secs_error"] = exc.detail
    return out


@api_router.post("/trade/board")
async def trade_board_create(data: TradeBoardInput, user=Depends(get_current_user)):
    """Publish one parked animal as open to offers.

    THE SAME PER-ANIMAL GATES THE OFFER LANE RUNS, in the same order and through
    the same helper -- growth, redeem-in-progress, the per-animal move cooldown
    and the pending-offer hold. A card the offer lane would refuse is a card
    that wastes the visitor's click, so it is refused here where the owner can
    read why."""
    await _resolve_trade_board()
    cfg = await _mcfg()
    rid = _client_request_id(data.client_request_id)
    op_scope = "board:new:%.80s" % (data.dino_id,)
    replayed = await _market_op_peek("board", user, rid, op_scope)
    if replayed is not None:
        return replayed
    if not _trade_enabled(cfg):
        raise HTTPException(status_code=503,
                            detail="Los intercambios están desactivados por ahora.")
    _market_write_gate(cfg, user["id"])
    sid = _steam_id_or_400(user)
    dino_id = _board_dino_id_or_400(data.dino_id)
    ttl = _trade_board_ttl_secs(cfg)
    cap = _trade_board_cap(cfg)
    try:
        live = await db.trade_board.count_documents({"owner_id": user["id"], "status": "active"})
    except Exception:
        logger.exception("[BOARD] cap count failed for %s", user["id"])
        live = 0
    if live >= cap:
        raise HTTPException(status_code=409, detail=(
            f"Ya tienes {cap} dinosaurios publicados para intercambio. Quita uno "
            f"antes de publicar otro."))
    try:
        dupe = await db.trade_board.find_one({"dino_id": dino_id, "status": "active"},
                                             {"_id": 0, "id": 1, "owner_id": 1})
    except Exception:
        logger.exception("[BOARD] duplicate check failed for dino %s", dino_id)
        dupe = None
    if dupe:
        raise HTTPException(status_code=409, detail=(
            "Ese dinosaurio ya está publicado para intercambio."
            if dupe.get("owner_id") == user["id"]
            else "Ese dinosaurio ya está publicado por otra persona."))
    # ONE animal, through the offer lane's own validator.
    rows = await _trade_rows_or_404(cfg, sid, [dino_id], mine=True)
    row = rows[0]
    view = _trade_board_view(cfg, row)
    if view["value_error"]:
        raise HTTPException(status_code=503, detail=view["value_error"])
    slug = view["dino_slug"]
    catalog = await db.dinosaurs.find_one({"slug": slug}, {"_id": 0}) if slug else None
    display_name = (catalog or {}).get("name") or view["species"] or "Dinosaurio"
    now = time.time()
    entry = {
        "id": new_id(), "status": "active",
        "owner_id": user["id"], "owner_name": user.get("persona_name"), "owner_steam": sid,
        "dino_id": dino_id,
        "dino_name": display_name,
        "image": (catalog or {}).get("image") or seed_data.DINO_IMG.get(slug) or "",
        "rarity": (catalog or {}).get("rarity", "Common"),
        "title": _market_title_or_400(data.title, vault.clean_custom_name(row.get("custom_name")),
                                      display_name),
        "note": _market_clean_title(data.note) or None,
        "offers": 0,
        "created_at": now_iso(), "expires_at_ts": now + ttl,
        "ends_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(),
        "client_request_id": rid or None,
    }
    entry.update({k: v for k, v in view.items() if k != "value_error"})
    entry["dino_name"] = display_name          # the catalog name outranks the raw class
    op_ref, replayed = await _market_op_take("board", user, rid, op_scope, 0)
    if replayed is not None:
        return replayed
    try:
        await db.trade_board.insert_one(entry)
    except Exception as exc:
        logger.exception("[BOARD] insert failed for %s", user["id"])
        refusal = HTTPException(status_code=503, detail=(
            "No se pudo publicar el intercambio. Intenta de nuevo."))
        await _market_op_reversed(op_ref, refusal)
        raise refusal from exc
    logger.info("[BOARD] card %s by %s: dino=%s slug=%s value=%s", entry["id"],
                user["id"], dino_id, slug, entry.get("value"))
    result = {"success": True, "card": _trade_board_public(entry, user["id"])}
    await _market_op_done(op_ref, result)
    return result


@api_router.post("/trade/board/{entry_id}/close")
async def trade_board_remove(entry_id: str, data: Optional[TradeActionInput] = None,
                             user=Depends(get_current_user)):
    """Take my own card down. FREE and instant -- nothing was ever escrowed, so
    there is nothing to charge for and nothing to give back.

    Any offers already sent on it STAY OPEN. They hold the sender's animals in
    escrow and are a promise between two players; silently voiding them because
    the window closed would be the market's withdraw-fee mistake in a costume
    where somebody else pays it. The owner declines them if they mean no."""
    e = await _trade_board_open_or_404(entry_id)
    if e.get("owner_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Esa publicación no es tuya.")
    await _trade_board_close(e["id"], "owner")
    return {"success": True, "id": e["id"]}


# ---------- seeding ----------
async def seed():
    # Strip mutation keys nobody recognises out of stored data. Labelled a one-off, but
    # it is on the startup path and therefore runs on EVERY boot, and it DELETES player
    # data driven by a list that is now generated rather than hand-written. If the
    # catalog ever regresses - a name dropped from PICKABLE, a key that stops
    # round-tripping - this quietly wipes that mutation from every stored dinosaur with
    # no log and no undo. So: count first, say what it is about to do, and refuse to
    # run at all if the number looks like a regression rather than a bit of dirt.
    # STRIP_CEILING is deliberately small: real dirt is a handful of rows.
    valid_muts = list(MUTATIONS_BY_KEY.keys())
    STRIP_CEILING = 25
    dirty = {"$exists": True, "$elemMatch": {"$nin": valid_muts}}
    targets = [
        ("inventory", db.inventory, {"mutations": dirty}),
        ("dino_records", db.dino_records, {"mutations": dirty}),
        ("users.active_dino", db.users, {"active_dino.mutations": dirty}),
    ]
    counts = {}
    try:
        for name, coll, query in targets:
            counts[name] = await coll.count_documents(query)
    except Exception:
        logger.exception("[seed] mutation-key cleanup could not count; SKIPPING the strip")
        counts = None
    if counts is None:
        pass
    elif not any(counts.values()):
        logger.info("[seed] mutation-key cleanup: nothing to strip (%d valid keys)", len(valid_muts))
    elif sum(counts.values()) > STRIP_CEILING:
        logger.error(
            "[seed] mutation-key cleanup SKIPPED: %s documents carry an unrecognised "
            "mutation key against a %d-key catalog. That is a catalog regression, not "
            "dirty data - fix the catalog rather than deleting player mutations.",
            counts, len(valid_muts))
    else:
        logger.warning("[seed] mutation-key cleanup stripping unrecognised keys from %s", counts)
        mut_filter = [{"$set": {"mutations": {"$filter": {"input": "$mutations", "as": "m", "cond": {"$in": ["$$m", valid_muts]}}}}}]
        await db.inventory.update_many({"mutations": {"$exists": True}}, mut_filter)
        await db.dino_records.update_many({"mutations": {"$exists": True}}, mut_filter)
        await db.users.update_many(
            {"active_dino.mutations": {"$exists": True}},
            [{"$set": {"active_dino.mutations": {"$filter": {"input": "$active_dino.mutations", "as": "m", "cond": {"$in": ["$$m", valid_muts]}}}}}])
    existing_slugs = set(await db.dinosaurs.distinct("slug"))
    roster_slugs = set(d["slug"] for d in seed_data.DINOSAURS)
    for d in seed_data.DINOSAURS:
        if d["slug"] not in existing_slugs:
            doc = {**d, "id": new_id(), "created_at": now_iso()}
            await db.dinosaurs.insert_one(doc)
        else:
            # Keep image, rarity, stats and description in sync with the roster.
            await db.dinosaurs.update_one(
                {"slug": d["slug"]},
                {"$set": {k: d[k] for k in ("name", "type", "diet", "rarity", "description",
                                            "image", "stats", "abilities", "featured", "growth_minutes")}})
    # Remove dinos no longer in the official roster (e.g. Giganotosaurus, Puertasaurus).
    removed = existing_slugs - roster_slugs
    if removed:
        await db.dinosaurs.delete_many({"slug": {"$in": list(removed)}})
        await db.store_items.delete_many({"category": "Dinosaurs", "dino_slug": {"$in": list(removed)}})
        await db.market.delete_many({"dino_slug": {"$in": list(removed)}})
        logger.info(f"Removed off-roster dinos: {removed}")
    if existing_slugs != roster_slugs:
        logger.info("Synced dinosaur roster")
    # Ensure isolated studio renders are present on every dino doc (for the Skin Lab).
    for slug, render in seed_data.DINO_RENDER.items():
        await db.dinosaurs.update_one({"slug": slug}, {"$set": {"render": render}})
    # Ensure 3D model paths are present on every dino doc (for the 3D Skin Studio).
    for slug, model3d in seed_data.DINO_MODEL3D.items():
        await db.dinosaurs.update_one({"slug": slug}, {"$set": {"model3d": model3d}})
    if await db.store_items.count_documents({}) == 0:
        for s in seed_data.STORE_ITEMS:
            s = {**s, "id": new_id(), "created_at": now_iso()}
            await db.store_items.insert_one(s)
        logger.info("Seeded store items")
    # Ensure ALL official Evrima dinos are purchasable, with rarity-balanced VIP prices.
    # (Basic price = rarity price; Prime tier = 3x, applied at checkout.)
    # Descriptive fields always synced; price/currency/featured only set on first insert so
    # admin price edits persist across restarts.
    always = ("name", "description", "rarity", "image", "dino_slug")
    on_insert = ("price", "currency", "featured")
    for di in seed_data.DINO_STORE_ITEMS:
        await db.store_items.update_one(
            {"category": "Dinosaurs", "dino_slug": di["dino_slug"]},
            {"$set": {k: di[k] for k in always},
             "$setOnInsert": {"id": new_id(), "created_at": now_iso(), "category": "Dinosaurs",
                              **{k: di[k] for k in on_insert}}},
            upsert=True,
        )
    # Remove any legacy dino store items missing a species slug (old duplicates).
    await db.store_items.delete_many({"category": "Dinosaurs", "dino_slug": {"$in": [None, ""]}})
    # Backfill dino_slug on legacy inventory dinos (purchased before the field existed).
    store_dinos = await db.store_items.find({"category": "Dinosaurs"}, {"_id": 0, "id": 1, "dino_slug": 1}).to_list(100)
    sid_to_slug = {s["id"]: s.get("dino_slug") for s in store_dinos if s.get("dino_slug")}
    legacy = await db.inventory.find({"category": "Dinosaurs", "dino_slug": None}).to_list(5000)
    for it in legacy:
        slug = sid_to_slug.get(it.get("item_id"))
        if not slug:
            nm = it["name"].replace(" Slot", "").strip()
            d = await db.dinosaurs.find_one({"name": {"$regex": f"^{re.escape(nm)}", "$options": "i"}}, {"_id": 0, "slug": 1})
            slug = d["slug"] if d else None
        if slug:
            await db.inventory.update_one({"id": it["id"]}, {"$set": {"dino_slug": slug}})
    # Re-image ALL owned/listed dinos to the new transparent portraits (by species slug).
    for slug, img in seed_data.DINO_IMG.items():
        await db.inventory.update_many({"category": "Dinosaurs", "dino_slug": slug}, {"$set": {"image": img}})
        await db.market.update_many({"dino_slug": slug}, {"$set": {"image": img}})
        await db.dino_records.update_many({"dino_slug": slug}, {"$set": {"image": img}})
        await db.users.update_many({"active_dino.slug": slug}, {"$set": {"active_dino.image": img}})
    # Backfill uses on legacy skin inventory items (consumable charges).
    await db.inventory.update_many(
        {"category": "Skins", "uses": {"$exists": False}},
        {"$set": {"uses": SKIN_USES_PER_GRANT}})
    # Backfill uses on glitch reward skins won before the use-limit existed:
    # 25 per win, and quantity counts wins, so an x2 row heals to 50. Failure
    # never blocks boot — the apply lane lazily heals any row it touches.
    try:
        res = await db.reward_skins.update_many(
            {"uses": {"$exists": False}},
            [{"$set": {"uses": {"$multiply": [
                GLITCH_USES_PER_WIN,
                {"$max": [1, {"$ifNull": ["$quantity", 1]}]}]}}}])
        if res.modified_count:
            logger.info("Backfilled uses on %d glitch reward skins", res.modified_count)
    except Exception:
        logger.exception("reward_skins uses backfill failed (apply lane self-heals per row)")
    # Migration: replace legacy store crates with the two-tier game-coin crates.
    # price/currency/featured only on first insert — the /admin Store tab edits
    # them and /cases charges from that row (hand-in-hand with seed fallback),
    # so a restart must never clobber the admin's crate pricing.
    await db.store_items.delete_many({"category": "Crates", "name": {"$in": ["VIP Crate", "Survivor Crate"]}})
    for c in [s for s in seed_data.STORE_ITEMS if s["category"] == "Crates"]:
        await db.store_items.update_one(
            {"name": c["name"], "category": "Crates"},
            {"$set": {k: c[k] for k in ("name", "description", "rarity", "image", "category")},
             "$setOnInsert": {"id": new_id(), "created_at": now_iso(),
                              **{k: c[k] for k in ("price", "currency", "featured")}}},
            upsert=True,
        )
    if await db.news.count_documents({}) == 0:
        for n in seed_data.NEWS:
            n = {**n, "id": new_id(), "created_at": now_iso()}
            await db.news.insert_one(n)
    if await db.events.count_documents({}) == 0:
        for e in seed_data.EVENTS:
            e = {**e, "id": new_id()}
            await db.events.insert_one(e)
    if await db.codes.count_documents({}) == 0:
        starter = {
            "id": new_id(), "code": "WELCOME2026", "name": "Welcome Pack",
            "description": "A starter boost of Survival Coins for new survivors.",
            "start_date": None, "end_date": None, "max_uses": 0, "per_user": 1,
            "reward": {"coins": 500, "vip_coins": 0, "items": [], "dinos": [], "roles": []},
            "active": True, "uses": 0, "created_at": now_iso(),
        }
        vip = {
            "id": new_id(), "code": "PRIMALVIP", "name": "VIP Taster",
            "description": "A taste of premium VIP currency.",
            "start_date": None, "end_date": None, "max_uses": 100, "per_user": 1,
            "reward": {"coins": 0, "vip_coins": 10, "items": [], "dinos": [], "roles": []},
            "active": True, "uses": 0, "created_at": now_iso(),
        }
        await db.codes.insert_many([starter, vip])
        logger.info("Seeded codes")
    if SEED_DEMO_MARKET and await db.market.count_documents({}) == 0:
        demo_listings = [
            ("ApexHunter", "carno", "sale", 1800, None),
            ("DinoTrader", "stego", "sale", 2400, None),
            ("RexKing", "trex", "auction", 6000, 12),
            ("SwiftClaw", "raptor", "sale", 700, None),
            ("HerbLord", "trike", "auction", 3000, 8),
        ]
        for seller, slug, ltype, price, hours in demo_listings:
            d = await db.dinosaurs.find_one({"slug": slug}, {"_id": 0})
            if not d:
                continue
            await db.market.insert_one({
                "id": new_id(), "seller_id": None, "seller_name": seller,
                "dino_slug": slug, "dino_name": d["name"], "image": d["image"], "rarity": d["rarity"],
                "type": ltype, "price": price,
                "current_bid": None, "current_bidder_id": None, "current_bidder_name": None,
                "ends_at": (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat() if hours else None,
                "status": "active", "created_at": now_iso(),
            })
        logger.info("Seeded marketplace listings")

    # Quests: drop legacy (pre-objective) quests, then upsert the default in-game quests.
    await db.quests.delete_many({"objective": {"$exists": False}})
    for dq in quest_data.DEFAULT_QUESTS:
        obj = dict(dq["objective"])
        await db.quests.update_one(
            {"id": dq["key"]},
            {"$set": {"title": dq["title"], "description": dq["description"],
                      "category": dq["category"], "rarity": dq["rarity"], "objective": obj,
                      "coins": dq["coins"], "vip": dq["vip"], "xp": dq["xp"],
                      "egg": dq["egg"], "requires": dq["requires"], "active": True},
             "$setOnInsert": {"id": dq["key"], "created_at": now_iso()}},
            upsert=True)
    retired = getattr(quest_data, "RETIRED_QUEST_KEYS", [])
    if retired:
        await db.quests.update_many({"id": {"$in": retired}}, {"$set": {"active": False}})
    logger.info("Seeded default quests")


async def ensure_indexes():
    await db.users.create_index("steam_id", unique=True, sparse=True)
    await db.users.create_index("native_unban_pending", name="native_unban_retry",
                                partialFilterExpression={"native_unban_pending": {"$exists": True}})
    await db.users.create_index("pending_kick", name="pending_kick_sweep",
                                partialFilterExpression={"pending_kick": {"$exists": True}})
    await db.transactions.create_index([("user_id", 1), ("ts", -1)])
    await db.chat_messages.create_index("ts")
    await db.market.create_index("status")
    # The settle pass reads {status:"active", ends_at:{$ne:null}} on EVERY market
    # read; the reaper reads {status:{$in:["selling","resolving"]}, claimed_at:...};
    # the per-seller cap counts {seller_id, status}. background=True so a first
    # boot on 1,634 market docs does not block the health gate.
    await db.market.create_index([("status", 1), ("ends_at", 1)], name="market_settle_scan",
                                 background=True)
    await db.market.create_index([("status", 1), ("claimed_at", 1)], name="market_reap_scan",
                                 background=True)
    await db.market.create_index([("seller_id", 1), ("status", 1)], name="market_seller_active",
                                 background=True)
    await db.market.create_index([("dino_slug", 1), ("status", 1), ("sold_at", -1)],
                                 name="market_species_sales", background=True)
    await db.quest_progress.create_index("user_id")
    # One row per (user, season); unique so two racing upserts can never split
    # a player's stats across duplicate rows. The season+score index serves the
    # hub's sorted board reads.
    await db.leaderboard_stats.create_index([("user_id", 1), ("season_id", 1)], unique=True)
    await db.leaderboard_stats.create_index([("season_id", 1), ("score", -1)])
    await db.leaderboard_awards.create_index("season_id", unique=True)
    await db.leaderboard_meta.create_index("key", unique=True)
    await db.multiplier_events.create_index([("created_at", -1)])
    await db.casino_bets.create_index([("user_id", 1), ("ts", -1)])
    await db.inventory.create_index("user_id")
    await db.unboxings.create_index([("user_id", 1), ("ts", -1)])
    # Unique per (user, glitch) — the grant path upserts quantity on duplicates.
    await db.reward_skins.create_index([("user_id", 1), ("glitch_id", 1)], unique=True)
    await db.code_redemptions.create_index([("code", 1), ("user_id", 1)])
    # store_orders dedupes on _id (the cart key), which Mongo indexes uniquely
    # on its own -- this one is only so "what did this player order" is a lookup
    # and not a scan. The collection is bounded by DISTINCT (player, cart)
    # combinations, not by purchase count: a repeat of the same cart re-claims
    # the SAME document rather than inserting a new one.
    await db.store_orders.create_index([("user_id", 1), ("created_at", -1)])
    # Dino recovery. The unique death_key closes the two-admins-at-once race.
    # It is NOT the only guard — _grant_recovered_dino also reads the claim
    # first — because an index build can fail (a pre-existing duplicate, an
    # options conflict) and a silent absence would otherwise turn the whole
    # anti-duplicate guarantee off with no signal.
    # Contained on purpose: ensure_indexes() is awaited unguarded at the top of
    # startup, so an exception here would crash-loop the entire site over a
    # single admin-panel index.
    try:
        await db[dino_recovery.RECOVERY_COLLECTION].create_index("death_key", unique=True)
        await db[dino_recovery.SNAPSHOT_COLLECTION].create_index("steam_id", unique=True)
        await db[dino_recovery.PARK_MARK_COLLECTION].create_index("vault_row_id", unique=True)
        await db[dino_recovery.PARK_MARK_COLLECTION].create_index(
            [("steam_id", 1), ("parked_at_ts", -1)])
        # Capture history: the lookup the recovery lane does, and the TTL that
        # keeps the collection from growing without bound. NOT unique on
        # steam_id — the whole point is many rows per player. The TTL is on a
        # real date field because that is the only thing mongo will expire on.
        await db[dino_recovery.SNAPSHOT_HISTORY_COLLECTION].create_index(
            [("steam_id", 1), ("seen_at", -1)], name="recovery_history_lookup")
        await db[dino_recovery.SNAPSHOT_HISTORY_COLLECTION].create_index(
            "seen_dt", name="recovery_history_ttl",
            expireAfterSeconds=dino_recovery.SNAPSHOT_HISTORY_TTL_S)
    except Exception:
        logger.error("[recovery] index build FAILED — recovery still refuses duplicates via "
                     "its read-before-write check, but the race guard is off until this is "
                     "fixed", exc_info=True)
    # Pase de Batalla: one claim per (user, season, track, level), one grant per
    # Stripe session/event. battle_pass.ensure_indexes contains its own failure.
    try:
        await battle_pass.ensure_indexes()
    except Exception as e:
        logger.warning("[bp] hook failed: %r", e)


_WEB_BUILD_CACHE = {"ts": 0.0, "name": ""}
_WEB_INDEX_PATH = os.environ.get("LIN_FRONTEND_INDEX") or str(
    Path(__file__).resolve().parent.parent / "frontend" / "index.html")


def current_web_build() -> str:
    """Bundle hash the CURRENT frontend index.html references (e.g. "eb12a120").
    Disk-read with a 30s TTL so frontend flips (which never bounce the backend)
    surface here without a restart. Any read problem returns the last known
    value — this feeds the stale-tab self-heal and must never throw."""
    import time as _t
    now = _t.time()
    if now - _WEB_BUILD_CACHE["ts"] < 30 and _WEB_BUILD_CACHE["name"]:
        return _WEB_BUILD_CACHE["name"]
    name = _WEB_BUILD_CACHE["name"]
    try:
        with open(_WEB_INDEX_PATH, "r", encoding="utf-8", errors="ignore") as f:
            m = re.search(r"main\.([a-f0-9]+)\.js", f.read())
        if m:
            name = m.group(1)
    except Exception:
        pass
    _WEB_BUILD_CACHE.update({"ts": now, "name": name})
    return name


@api_router.get("/health")
async def health():
    result = {"mongo": "fail", "rcon": "absent", "time": now_iso(), "ok": False,
              "deploy_lane": "github", "web_build": current_web_build()}
    try:
        await db.command("ping")
        result["mongo"] = "ok"
    except Exception as e:
        result["mongo_error"] = str(e)

    if rcon_client.is_configured():
        try:
            await asyncio.wait_for(rcon_client.server_details(), timeout=2.5)
            result["rcon"] = "ok"
        except Exception as e:
            result["rcon"] = "fail"
            result["rcon_error"] = str(e)

    result["ok"] = result["mongo"] == "ok" and result["rcon"] in {"ok", "absent"}
    return result


@api_router.get("/")
async def root():
    return {"message": "Isla Nublar LATAM API online", "demo": ALLOW_DEMO_LOGIN}


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
    # The website-ban refusal rides a 401 with X-Web-Ban so the page can tell a
    # ban from an expired token; same-origin today, exposed for any origin.
    expose_headers=["X-Web-Ban"],
)


# ---------------------------------------------------------------------------
# Multiplayer Dino Roll (server-driven, always-on rounds + Triple Green jackpot)
# ---------------------------------------------------------------------------
ROLL_BET_SECS = 15
ROLL_SPIN_SECS = 8
ROLL_JACKPOT_RATE = 0.1067          # share of every bet that feeds the Bonus Pool
ROLL_MIN_BET = 100
# Roll was the one casino game with no ceiling -- every other game runs through
# _validate_bet (CASINO_MAX_BET). An uncapped stake is what let the settle bug
# below scale from a few thousand coins to billions, so Roll now shares the cap.
ROLL_MAX_BET = CASINO_MAX_BET
ROLL_MULT = {"red": 2, "black": 2, "green": 14}
# default win chances (%) per colour — owner-configurable via /admin/roll-config
ROLL_CHANCES_DEFAULT = {"green": 6.67, "red": 46.665, "black": 46.665}
_roll_cfg = None


async def roll_config_value():
    """Cached owner-configured roll chances (+ multipliers). Falls back to defaults."""
    global _roll_cfg
    if _roll_cfg is None:
        doc = await db.settings.find_one({"_id": "app"}) or {}
        rc = doc.get("roll_chances") or {}
        chances = {k: float(rc.get(k, ROLL_CHANCES_DEFAULT[k])) for k in ("green", "red", "black")}
        _roll_cfg = {"chances": chances, "mult": ROLL_MULT}
    return _roll_cfg


def _roll_pick(roll: float, sub: float, chances: dict):
    """Return (color, number) using configured colour probabilities.
    Number stays consistent with the wheel (green=0, red 1-7, black 8-14)."""
    total = max(0.0001, chances["green"] + chances["red"] + chances["black"])
    g = chances["green"] / total
    r = chances["red"] / total
    if roll < g:
        return "green", 0
    if roll < g + r:
        return "red", 1 + min(6, int(sub * 7))
    return "black", 8 + min(6, int(sub * 7))


class RollBetInput(BaseModel):
    color: str
    amount: int


async def _roll_settle(rnd: dict):
    color = rnd.get("result_color") or "black"
    mult = (await roll_config_value())["mult"]
    bets = rnd.get("bets", [])
    by_user, total = {}, 0
    for b in bets:
        by_user[b["user_id"]] = by_user.get(b["user_id"], 0) + b["amount"]
        total += b["amount"]
        if b["color"] == color:
            await _casino_credit(b["user_id"], int(b["amount"] * mult[color]))
    meta = await db.roll_meta.find_one({"id": "meta"}) or {"jackpot": 0.0, "green_streak": 0}
    pool = float(meta.get("jackpot", 0))  # jackpot grows live per-bet (see roll_bet)
    streak = (int(meta.get("green_streak", 0)) + 1) if color == "green" else 0
    await db.roll_history.insert_one({
        "id": new_id(), "round_no": rnd["round_no"], "result_color": color, "roll": rnd.get("roll"),
        "result_number": rnd.get("result_number"),
        "server_hash": rnd.get("server_hash"), "server_seed": rnd.get("server_seed"), "client_seed": rnd.get("client_seed"),
        "total": total, "by_user": {str(k): v for k, v in by_user.items()}, "created_at": now_iso(),
    })
    jackpot_won = None
    if color == "green" and streak >= 3:
        last3 = await db.roll_history.find({}, {"_id": 0, "by_user": 1, "total": 1, "round_no": 1}).sort("round_no", -1).to_list(3)
        winners = {}
        for r in last3:
            third, rtotal = pool / 3.0, (r.get("total") or 0)
            if rtotal <= 0:
                continue
            for uid, amt in (r.get("by_user") or {}).items():
                gain = int(third * (amt / rtotal))
                if gain > 0:
                    winners[uid] = winners.get(uid, 0) + gain
        for uid, gain in winners.items():
            await _casino_credit(uid, gain)
        jackpot_won = {"amount": int(pool), "rounds": [r["round_no"] for r in last3], "at": now_iso(), "winners": len(winners)}
        pool, streak = 0.0, 0
        base_ts = datetime.now(timezone.utc)
        for i, ch in enumerate(["global", "na", "eu", "au"]):
            await db.chat_messages.insert_one({
                "id": new_id(), "user_id": "system", "name": "TRIPLE GREEN", "avatar": None, "role": "system",
                "channel": ch, "text": f"🟢🟢🟢 ¡Bonus Pool de {jackpot_won['amount']:,} CC repartido entre {jackpot_won['winners']} jugadores!",
                "created_at": (base_ts + timedelta(microseconds=i)).isoformat(),
            })
    elif color == "green" and streak == 2:
        # 2 greens in a row → the jackpot round is LIVE. Alert every channel.
        alert = {"type": "triple_green_alert", "streak": 2, "jackpot": int(pool), "seconds": ROLL_BET_SECS}
        base_ts = datetime.now(timezone.utc)
        for i, ch in enumerate(["global", "na", "eu", "au"]):
            await db.chat_messages.insert_one({
                "id": new_id(), "user_id": "system", "name": "TRIPLE VERDE", "avatar": None, "role": "system",
                "channel": ch, "type": "triple_green_alert", "alert": alert,
                "text": f"🟢🟢 ¡Ronda jackpot EN VIVO! {int(pool):,} CC en el bonus pool — ¿caerá el tercer verde?",
                "created_at": (base_ts + timedelta(microseconds=i)).isoformat(),
            })
    await db.roll_meta.update_one({"id": "meta"}, {"$set": {"jackpot": pool, "green_streak": streak, "last_win": jackpot_won}}, upsert=True)
    old = await db.roll_history.find({}, {"_id": 1}).sort("round_no", -1).skip(120).to_list(50)
    if old:
        await db.roll_history.delete_many({"_id": {"$in": [o["_id"] for o in old]}})


async def roll_loop():
    await asyncio.sleep(4)
    if not await db.roll_meta.find_one({"id": "meta"}):
        await db.roll_meta.insert_one({"id": "meta", "round_no": 0, "jackpot": 0.0, "green_streak": 0, "last_win": None})
    while True:
        try:
            meta = await db.roll_meta.find_one({"id": "meta"})
            rn = int(meta.get("round_no", 0)) + 1
            server_seed = secrets.token_hex(16)
            server_hash = hashlib.sha256(server_seed.encode()).hexdigest()
            client_seed = secrets.token_hex(8)
            ends = datetime.now(timezone.utc) + timedelta(seconds=ROLL_BET_SECS)
            await db.roll_current.replace_one({"id": "current"}, {
                "id": "current", "round_no": rn, "phase": "betting", "phase_ends_at": ends.isoformat(),
                "server_hash": server_hash, "server_seed": server_seed, "client_seed": client_seed,
                "bets": [], "totals": {"red": 0, "green": 0, "black": 0}, "result_color": None, "roll": None,
            }, upsert=True)
            await db.roll_meta.update_one({"id": "meta"}, {"$set": {"round_no": rn}})
            await asyncio.sleep(ROLL_BET_SECS)
            roll = _pf_float(server_seed, client_seed, rn)
            sub = _pf_float(server_seed, client_seed, rn + 100000)
            cfg = await roll_config_value()
            color, number = _roll_pick(roll, sub, cfg["chances"])
            spin_ends = datetime.now(timezone.utc) + timedelta(seconds=ROLL_SPIN_SECS)
            await db.roll_current.update_one({"id": "current"}, {"$set": {"phase": "rolling", "result_color": color, "result_number": number, "roll": round(roll, 8), "phase_ends_at": spin_ends.isoformat()}})
            await asyncio.sleep(ROLL_SPIN_SECS)
            cur = await db.roll_current.find_one({"id": "current"}, {"_id": 0})
            if cur:
                await _roll_settle(cur)
        except Exception as e:
            logger.error(f"roll_loop error: {e}")
            await asyncio.sleep(3)


@api_router.get("/casino/roll/state")
async def roll_state(user=Depends(get_current_user)):
    cur = await db.roll_current.find_one({"id": "current"}, {"_id": 0, "server_seed": 0})
    meta = await db.roll_meta.find_one({"id": "meta"}, {"_id": 0})
    hist = await db.roll_history.find({}, {"_id": 0, "by_user": 0, "server_hash": 0}).sort("round_no", -1).to_list(50)
    my_bets = [b for b in (cur.get("bets", []) if cur else []) if b["user_id"] == user["id"]]
    cfg = await roll_config_value()
    return {
        "round": cur, "jackpot": round(float(meta["jackpot"]), 2) if meta else 0,
        "green_streak": int(meta.get("green_streak", 0)) if meta else 0,
        "last_win": meta.get("last_win") if meta else None,
        "history": hist, "my_bets": my_bets, "balance": await _casino_balance(user["id"]),
        "config": {"min_bet": ROLL_MIN_BET, "max_bet": ROLL_MAX_BET, "mult": cfg["mult"],
                   "jackpot_rate": ROLL_JACKPOT_RATE, "chances": cfg["chances"]},
    }


@api_router.post("/casino/roll/bet")
async def roll_bet(data: RollBetInput, user=Depends(get_current_user)):
    if data.color not in ("red", "green", "black"):
        raise HTTPException(status_code=400, detail="Color inválido")
    if data.amount < ROLL_MIN_BET:
        raise HTTPException(status_code=400, detail=f"La apuesta mínima es {ROLL_MIN_BET:,} CC")
    if data.amount > ROLL_MAX_BET:
        raise HTTPException(status_code=400, detail=f"La apuesta máxima es {ROLL_MAX_BET:,} CC")
    cur = await db.roll_current.find_one({"id": "current"}, {"_id": 0, "round_no": 1, "phase": 1})
    if not cur or cur.get("phase") != "betting":
        raise HTTPException(status_code=400, detail="Apuestas cerradas — espera la próxima ronda")
    round_no = cur["round_no"]
    # One bet per player: if the player already bet this round, MOVE it (refund old, then place new).
    # ATOMIC CLAIM. Read-then-refund is a money printer here: N concurrent moves all
    # read the same bets array, all pay the refund, and all push a fresh bet -- the
    # refunds cancel the charges, so the player ends the round holding N live bets
    # for the price of one and gets settled at N x the multiplier. The $pull below
    # IS the claim: MongoDB serialises findAndModify per document, so exactly one
    # racer removes the bet and is handed the amounts to refund; every other racer
    # sees no bet to pull, gets None, and refunds nothing.
    prev = await db.roll_current.find_one_and_update(
        {"id": "current", "round_no": round_no, "phase": "betting", "bets.user_id": user["id"]},
        {"$pull": {"bets": {"user_id": user["id"]}}},
        projection={"_id": 0, "bets": 1},
        return_document=ReturnDocument.BEFORE,
    )
    refund = 0
    if prev:
        mine = [b for b in (prev.get("bets") or []) if b["user_id"] == user["id"]]
        refund = sum(int(b["amount"]) for b in mine)
        if refund:
            dec = {}
            for b in mine:
                key = f"totals.{b['color']}"
                dec[key] = dec.get(key, 0) - int(b["amount"])
            await db.roll_current.update_one({"id": "current", "round_no": round_no}, {"$inc": dec})
            await _casino_credit(user["id"], refund)
            await db.roll_meta.update_one({"id": "meta"}, {"$inc": {"jackpot": -int(refund * ROLL_JACKPOT_RATE)}}, upsert=True)
    await _casino_charge(user["id"], data.amount)
    bet = {"user_id": user["id"], "name": user.get("persona_name") or "Survivor", "avatar": user.get("avatar"),
           "color": data.color, "amount": data.amount, "at": now_iso()}
    # Same claim on the way in: the push only lands while this round is still taking
    # bets AND this player has none, so a bet can neither be duplicated nor slipped
    # in after the wheel has already shown its colour.
    placed = await db.roll_current.find_one_and_update(
        {"id": "current", "round_no": round_no, "phase": "betting", "bets.user_id": {"$ne": user["id"]}},
        {"$push": {"bets": bet}, "$inc": {f"totals.{data.color}": data.amount}},
    )
    if not placed:
        await _casino_credit(user["id"], data.amount)  # the bet never landed -- hand it straight back
        raise HTTPException(status_code=400, detail="Apuestas cerradas — espera la próxima ronda")
    # jackpot updates INSTANTLY per bet (not at settle)
    await db.roll_meta.update_one({"id": "meta"}, {"$inc": {"jackpot": int(data.amount * ROLL_JACKPOT_RATE)}}, upsert=True)
    return {"success": True, "balance": await _casino_balance(user["id"]), "round_no": round_no, "moved": bool(refund)}


# ===========================================================================
# La Isla Nublar — game-mod web surface (LOCAL).
# Real player state / vault / positions / teleport / skins / population / voice.
# Heavy logic lives in game_ipc, vault, pop_control, voice_token,
# teleport_presets. All new user-facing "detail" strings are Spanish.
# ===========================================================================
import json
import time as _time

_SKIN_MAP_PATH = os.path.join(game_ipc.SKIN_META_DIR, "skin_color_label_map.json")
_MATERIAL_SCALARS_PATH = os.path.join(game_ipc.SKIN_META_DIR, "material_scalars.json")
_PRESETS_DIR = os.path.join(game_ipc.SKIN_META_DIR, "presets")
_VALID_SLOT_KEYS = frozenset({"body", "markings", "flank", "underbelly", "detail1", "male_display", "eyes"})
_skin_meta_lock = threading.Lock()


def _steam_id_or_400(user) -> str:
    sid = str(user.get("steam_id") or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Vincula tu cuenta de Steam para usar esta función.")
    return sid


# ---------- the ONE skin-apply budget, shared by /api/apply and apply-v2 ----
# THIS OWNER HAD NO APPLY BUDGET AT ALL on the free-form editor lane (measured
# 2026-08-24, re-measured on the live file 2026-08-25). `POST /api/apply` is
# entitlement-gated by `_patreon_access` + `_skin_creator_allowed` - and that
# helper honours the STREAMER PACK with no paid tier, so the lane was never
# "paid patrons only": a free streamer could post skin commands as fast as a
# session could send them. Meanwhile this site's OTHER skin-apply lane,
# `/api/me/rewards/skins/apply`, already accepts a 30 s cooldown
# (`_REWARD_APPLY_COOLDOWN_SECONDS` = 2/min).
#
# The contract-v2 engine REFUSES to wire an owner with no rate hooks, and it is
# right to: a v2-only budget beside an unmetered v1 is exactly the defect this
# wave exists to remove. So the budget is created ONCE here and BOTH lanes
# spend it. THAT MAKES /api/apply METERED WHERE IT WAS NOT - a real,
# player-visible change, at the fleet standard 10/min (Fangs and Ferns 10/min,
# German Dominion 10/min), which is FIVE TIMES more permissive than the
# 30 s cooldown this owner's own glitch-skin lane already imposes.
_SKIN_APPLY_WINDOW_SECONDS = 60.0
_SKIN_APPLY_MAX = 10
_skin_apply_hits: dict = {}
_skin_apply_lock = threading.Lock()


def _skin_apply_reserve(steam_id: str):
    """(ok, token). The token is this exact hit, so a rollback removes only it."""
    now = _time.monotonic()
    with _skin_apply_lock:
        hits = [value for value in _skin_apply_hits.get(steam_id, [])
                if value >= now - _SKIN_APPLY_WINDOW_SECONDS]
        if len(hits) >= _SKIN_APPLY_MAX:
            _skin_apply_hits[steam_id] = hits
            return False, None
        hits.append(now)
        _skin_apply_hits[steam_id] = hits
        # Keep the table bounded; a per-player dict that only grows is a leak.
        if len(_skin_apply_hits) > 4096:
            for key in [k for k, v in _skin_apply_hits.items()
                        if not v or v[-1] < now - _SKIN_APPLY_WINDOW_SECONDS]:
                _skin_apply_hits.pop(key, None)
    return True, (steam_id, now)


def _skin_apply_rate_reserve(steam_id: str):
    """The v2 engine's hook onto the shared budget above."""
    ok, token = _skin_apply_reserve(steam_id)
    return token if ok else _skin_v2_engine.RATE_DENIED


def _skin_apply_rate_rollback(token) -> None:
    """Refund a hit the engine reserved and then refused to land."""
    if not token:
        return
    steam_id, stamp = token
    with _skin_apply_lock:
        hits = _skin_apply_hits.get(steam_id)
        if not hits:
            return
        try:
            hits.remove(stamp)
        except ValueError:
            pass


def _enforce_skin_apply_rate(steam_id: str) -> None:
    """The v1 lane's hook onto the same budget. Raises, like its neighbours."""
    ok, _token = _skin_apply_reserve(steam_id)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail="Demasiadas skins seguidas — espera un momento e inténtalo de nuevo.")


async def _skin_v2_steam_id(user=Depends(get_current_user)) -> str:
    """The v2 routes' identity: the SAME dependency `/api/apply` uses, so the
    two lanes can never diverge on who is painting which dino."""
    return _steam_id_or_400(user)


def _web_is_admin(user) -> bool:
    return _is_owner(user) or user.get("role") == "admin" or user.get("staff_rank") in ("owner", "admin")


def _park_cap_default() -> int:
    """How many dinos a normal player may keep stored.

    Owner ruling 2026-07-30: 20 slots (was 10). The bot advertises the same
    number from its own MAX_STORED_DINOS default — move the two together.
    """
    try:
        return int(os.environ.get("LIN_PARK_CAP", "20") or "20")
    except ValueError:
        return 20


def _user_park_cap(user) -> int:
    if _web_is_admin(user):
        return 0
    return _park_cap_default()


def _req_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


def _srgb_to_linear(c: float) -> float:
    if c <= 0.0:
        return 0.0
    if c >= 1.0:
        return 1.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _bare_species(cls: str) -> str:
    s = str(cls or "")
    if s.startswith("BP_") and s.endswith("_C"):
        s = s[3:-2]
    return s


def _read_json_or(path, default):
    d = game_ipc.read_json_file(path)
    return d if d is not None else default


def _atomic_write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


# ---------- models ----------
class _DinoIdIn(BaseModel):
    dino_id: int = Field(ge=1)


class AdminTeleportIn(BaseModel):
    steamid: str = Field(min_length=1, max_length=32)
    x: float
    y: float
    z: float


class _RGBA(BaseModel):
    r: float = Field(ge=0, le=1)
    g: float = Field(ge=0, le=1)
    b: float = Field(ge=0, le=1)
    a: float = Field(default=1.0, ge=0, le=1)

    def as_list(self):
        return [self.r, self.g, self.b, self.a]


class SkinPayloadIn(BaseModel):
    female: bool = False
    variation: int = 0
    pattern: int = 0
    body: _RGBA
    markings: _RGBA
    flank: _RGBA
    underbelly: _RGBA
    detail1: _RGBA
    eyes: _RGBA
    male_display: _RGBA
    skin_code: str = ""

    def to_command(self, actor_name, dino_class, steam_id):
        import random
        # 2026-08-11 LINEAR RESTORE -- this SUPERSEDES the 2026-08-09 raw-sRGB
        # wave (fleet colour contract 24167035). CustomizerData's colour slots
        # are FLinearColor, which UE consumes LINEAR by definition, so a raw
        # picker fraction written there renders every mid-tone too bright: that
        # is the fleet's "washed out / lighter, and only on some colours" wave
        # which began the day of the raw flip. The original "one part of the
        # body goes dark" defect was the STUDIO DOUBLE ENCODE (a linear-space
        # frontend feeding a backend that encoded again), never this encode.
        # So the wire carries ONE srgb->linear encode of the raw picker
        # fraction and THIS IS THE ONLY PLACE IT HAPPENS -- encoding twice
        # lands a 0.5 pick on 0.0376 instead of 0.2149.
        # Framework canonical: webcore/skin_apply.py::_encode_linear.
        eps = random.uniform(1e-4, 1e-3)

        def _j(rgba):
            # ONE encode, then the 2026-08-10 bounds discipline kept but moved
            # INTO THE LINEAR DOMAIN: the per-apply eps still fires the engine's
            # struct-property delta, still lifts black off the client's all-zero
            # short-circuit, and still folds DOWNWARD within eps of 1.0 because
            # a channel at or above 1.0 reads as HDR glow on the client
            # ("skins look washed out"). srgb->linear fixes 1.0, so a saturated
            # pick still emits 1.0 - eps and the parked-recipe FOLD RECEIPT band
            # [0.9989, 0.99995] is unchanged (vault.py / dino.py
            # _parked_skin_recipe_grade -- keep the three in step).
            # 6dp, not 4: the encode crushes the dark end (a #0D pick is linear
            # 0.0025) and 4dp would quantise away the shadow detail the encode
            # exists to protect. Alpha rides through untouched -- it is the
            # editor's own per-slot slider, not part of the colour space.
            # Framework canonical: webcore/skin_apply.py::_encode_linear.
            out = []
            for i in range(3):
                v = _srgb_to_linear(min(1.0, max(0.0, float(rgba[i]))))
                v = v + eps if v <= 1.0 - eps else v - eps
                v = round(min(1.0, max(0.0, v)), 6)
                # ...and then the rails are closed ON THE ROUNDED VALUE, which
                # the canonical does not do. The 6dp round is the last step, so
                # a lifted channel sitting within 5e-7 under 1.0 - eps rounds
                # back ONTO 1.0 and re-enters the HDR band the fold exists to
                # avoid. No 8-bit pick can reach that window (byte 255 encodes
                # to exactly 1.0 and takes the fold-DOWN branch; byte 254 lands
                # at 0.9908, nine eps below the rail), but a direct API caller
                # posting a non-8-bit float can, so the last representable 6dp
                # value below each rail wins. tests_local/
                # test_skin_emission_float_band.py::F1 is what caught this.
                out.append(min(0.999999, max(0.000001, v)))
            out.append(rgba[3])
            return out

        # SkinVariation is the pattern TILING SIZE, and the client reverse-maps
        # it by EXACT key {Large 2.0, Medium 8.0, Small 16.0}. Anything else is
        # a value the client cannot map, which is why this snaps to a key and is
        # NEVER jittered: the eps exists for colour channels only, and adding it
        # here destroys the key and takes the pattern detail with it. Non-finite
        # and off-key inputs land on the game's own default (Medium 8.0), and
        # 0.0 is never emitted here -- exact 0.0 is the glitch shader's trigger
        # and belongs to glitch_catalog.build_glitch_command alone.
        # Framework canonical: webcore/skin_apply.py::variation_key.
        try:
            _v = float(self.variation)
        except (TypeError, ValueError):
            _v = 8.0
        variation = (2.0 if abs(_v - 2.0) <= 1e-6 else
                     8.0 if abs(_v - 8.0) <= 1e-6 else
                     16.0 if abs(_v - 16.0) <= 1e-6 else 8.0)

        return {
            "actor_name": actor_name, "class": dino_class, "steamid": steam_id,
            "female": self.female, "variation": variation,
            "pattern": int(self.pattern), "color_space": "linear",
            "body": _j(self.body.as_list()), "markings": _j(self.markings.as_list()),
            "flank": _j(self.flank.as_list()), "underbelly": _j(self.underbelly.as_list()),
            "detail1": _j(self.detail1.as_list()), "eyes": _j(self.eyes.as_list()),
            "male_display": _j(self.male_display.as_list()), "skin_code": (self.skin_code or "")[:512],
        }


def _paint_universal_skin_sync(skin_key: str, steam_id: str, dino: dict = None) -> bool:
    """Paint a won coded universal skin onto the player's LIVE in-game dino,
    reusing the EXACT skin_commands.json contract the Skin Studio /apply lane
    already uses in production (SkinPayloadIn.to_command -> ONE srgb->linear
    encode -> write_skin_command -> SkinKeeper capture). The `srgb` block below
    is a DESIGN-STORE key name, not a colour space: it holds RAW PICKER
    fractions, which is exactly what to_command's single encode expects.
    Only skins carrying a decoded
    'srgb' block (the coded Skin Studio designs) push to the game; single-colour
    derived skins stay website-display-only, byte-for-byte unchanged.

    `dino` may be a pre-resolved {actor_name, class} (the equip lane already
    looked it up to gate on being in-game); when None it is resolved here.
    Returns True iff a paint command was written to the mod. NEVER raises: any
    failure logs and returns False so the caller can react without a use ever
    being lost to a transient IPC error.
    """
    try:
        skin = seed_data.SKINS.get(skin_key) or {}
        srgb = skin.get("srgb")
        if not isinstance(srgb, dict) or not srgb.get("regions"):
            return False  # derived / uncoded skin -> display-only, unchanged
        if dino is None:
            dino = game_ipc.find_active_dino(steam_id)
        if not dino:
            return False  # not in-game -> nothing to paint
        if game_ipc.actor_live_in_engine(dino.get("actor_name")) is False:
            # Registry served a previous life's actor - painting it is waste.
            # Returning False rides the callers' existing refund paths.
            logger.info("[skins] ghost_gate refused sid=%s actor=%s lane=universal",
                        steam_id, dino.get("actor_name"))
            return False
        regions = srgb["regions"]
        # Every region must be present for a full 7-region apply; a partial code
        # falls back to display-only rather than painting a half-coloured dino.
        needed = ("body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display")
        if any(r not in regions for r in needed):
            logger.warning("[skins] universal paint skipped skin=%s reason=incomplete_srgb", skin_key)
            return False
        female = _live_female_or_none(dino["actor_name"])   # best-effort hint; mod overrides

        def _rgba(name):
            c = regions[name]
            return {"r": float(c[0]), "g": float(c[1]), "b": float(c[2]), "a": 1.0}

        payload = SkinPayloadIn(
            female=bool(female) if female is not None else False,
            variation=0, pattern=int(srgb.get("pattern", 0) or 0),
            body=_rgba("body"), markings=_rgba("markings"), flank=_rgba("flank"),
            underbelly=_rgba("underbelly"), detail1=_rgba("detail1"),
            eyes=_rgba("eyes"), male_display=_rgba("male_display"),
            skin_code=(skin.get("code") or "")[:512])
        cmd = payload.to_command(dino["actor_name"], dino["class"], steam_id)
        # The pawn's LIVE sex wins in the mod (fail-closed): the player won a
        # colour design, never a sex change. Byte-identical flag to the glitch lane.
        cmd["preserve_female"] = True
        if not game_ipc.write_skin_command(cmd):
            logger.warning("[skins] universal paint IPC write failed skin=%s sid=%s", skin_key, steam_id)
            return False
        # SkinKeeper capture (regular contract) so the design survives a relog,
        # exactly like a Studio self-apply. Keyed on the player's own steam_id.
        skinkeeper_web.record_apply(cmd, "regular")
        logger.info("[skins] universal skin painted in-game skin=%s sid=%s actor=%s",
                    skin_key, steam_id, dino["actor_name"])
        return True
    except Exception:
        logger.exception("[skins] universal paint failed skin=%s sid=%s", skin_key, steam_id)
        return False


class SkinMapIn(BaseModel):
    species: str = Field(min_length=1, max_length=64)
    mapping: dict[str, str]


class RawSkinSidecarIn(BaseModel):
    """Verbatim live-snapshot sidecar for an EXACT skin copy (skin_exact.py).

    Deliberately permissive field types — the single source of refusal rules is
    skin_exact.validate_raw, enforced in the preset routes (422) so the rules
    can never drift between this model and the apply-side re-validation."""
    variation: float
    pattern: int
    body: List[float]
    markings: List[float]
    flank: List[float]
    underbelly: List[float]
    detail1: List[float]
    eyes: List[float]
    male_display: List[float]


class SkinPresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    dino_class: str = Field(default="", max_length=64)
    payload: SkinPayloadIn
    # Optional exact-copy sidecar. Only stored after raw_matches_snapshot
    # proves the caller's live dino wears these bytes RIGHT NOW.
    raw: Optional[RawSkinSidecarIn] = None


class PopCapChange(BaseModel):
    species: str = Field(min_length=1, max_length=64)
    cap: int = Field(ge=-1, le=1000)


class PopPreviewIn(BaseModel):
    changes: List[PopCapChange] = Field(default_factory=list)
    lock: List[str] = Field(default_factory=list)
    unlock: List[str] = Field(default_factory=list)
    auto: Optional[bool] = None


class PopApplyIn(PopPreviewIn):
    reason: str = Field(default="", max_length=200)


# ---------- LIVE state: own current-dino vitals + prime progress ----------
def _prime_progress_summary(sid: str) -> dict:
    prow = game_ipc.read_prime_progress(sid)
    if not isinstance(prow, dict) or not prow:
        return {"available": False, "note": "El detalle por condición aún no está publicado por el mod."}
    return {
        "available": True,
        "pat": prow.get("pat") or {"n": 0, "cap": 4},
        "mig": prow.get("mig") or {"n": 0, "cap": 2},
        "conditions_met": int(prow.get("conditions_met") or 0),
        "conditions_total": int(prow.get("conditions_total") or 10),
        "conditions": prow.get("conditions") or {},
        "raw_bitmask": int(prow.get("raw_bitmask") or 0),
        "last_update": int(prow.get("last_update") or 0),
    }


def _dino_skin(actor_name: str):
    """dino.skin for me_state(): {pattern, colors:{body,markings,flank,underbelly,
    detail1,eyes,male_display}} straight from game_ipc.read_skin_snapshot(), same
    raw per-color RGBA shape GET /api/snapshot already returns unchanged (opaque
    copy -- SpeciesViewer3D.jsx converts linear RGBA -> hex the same way
    FleetDinoModel.jsx's getSpeciesDefaultColors already does). None when the
    actor has no snapshot on file yet -- callers degrade silently."""
    actor = str(actor_name or "").strip()
    if not actor:
        return None
    snap = game_ipc.read_skin_snapshot(actor)
    if not isinstance(snap, dict) or not snap:
        return None
    return {
        "pattern": snap.get("pattern"),
        "colors": {k: snap.get(k) for k in
                   ("body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display")},
    }


_livedino_src_last: dict = {}


def _livedino_source(row) -> str:
    """Which lane served this live-dino read (for the payload + the transition
    log): full=heavy row only, full+live=heavy with the 1 s positions overlay,
    carry+live=stale heavy carried forward under a fresh positions row,
    live-only=positions row alone (catalogue not built yet), offline=none."""
    if not isinstance(row, dict):
        return "offline"
    if row.get("heavy_missing"):
        return "live-only"
    if row.get("heavy_stale"):
        return "carry+live"
    return "full+live" if row.get("pos_source") == "live" else "full"


def _livedino_log_transition(sid: str, src: str) -> None:
    """One bounded log line per source CHANGE per SteamID -- the detection lane
    is polled every 3 s per open tab, so per-request logging would be spam."""
    try:
        if _livedino_src_last.get(sid) == src:
            return
        if len(_livedino_src_last) > 4096:
            _livedino_src_last.clear()
        _livedino_src_last[sid] = src
        logger.info(f"[livedino] {sid} source={src}")
    except Exception:
        pass


@api_router.get("/me/state")
def me_state(user=Depends(get_current_user)):
    sid = str(user.get("steam_id") or "").strip()
    empty = {"active": None, "prime_status": None, "prime_progress": None, "in_game": False,
             "position": None}
    if not sid:
        return empty
    row = game_ipc.read_player_display(sid)
    _livedino_log_transition(sid, _livedino_source(row))
    if not isinstance(row, dict):
        return empty

    def _pct(cur, mx):
        try:
            m = float(row.get(mx) or 0)
            if m > 0:
                return float(row.get(cur) or 0) / m
        except (TypeError, ValueError):
            pass
        return None

    # 0-100 percent variant of _pct for the primary vitals — MyDino.jsx's VitalRow
    # renders these values directly as a 0-100 gauge, so raw game units (e.g. health
    # 52.6/52.6) must be normalized here. None-safe: no usable max -> None ("pendiente").
    def _vital_pct(cur, mx):
        f = _pct(cur, mx)
        return None if f is None else max(0.0, min(100.0, f * 100.0))

    # 0-100 percent variant of _pct, for fields the frontend renders directly as a
    # gauge percentage (fractures, diet) rather than a 0-1 fraction.
    def _fpct(cur, mx):
        try:
            m = float(row.get(mx) or 0)
            c = float(row.get(cur) or 0)
            if m > 0 and c == c:  # NaN guard
                return max(0.0, min(100.0, (c / m) * 100.0))
        except (TypeError, ValueError):
            pass
        return None

    # blood/sprint/bite have no "current/max" pair on the wire (bleeding_stacks is a
    # stack count, movement_speed/bite_damage are raw game units) but MyDino.jsx's
    # VitalRow expects a single 0-100 gauge value like the other vitals. Normalize
    # against a documented reference ceiling so the gauge still reads sensibly.
    def _capped_pct(raw, ceiling):
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None
        if v != v:  # NaN guard
            return None
        return max(0.0, min(100.0, (v / ceiling) * 100.0))

    # blood integrity gauge: 100 = healthy/no bleed, drains toward 0 as bleeding_stacks
    # rises. Inverse of the bleed-severity ceiling used elsewhere (BLEED_MAX_STACKS),
    # so 0 stacks -> 100 (not 0).
    def _blood_integrity_pct(raw, max_stacks):
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None
        if v != v:  # NaN guard
            return None
        return max(0.0, min(100.0, 100.0 - (100.0 / max_stacks) * v))

    # raw (non-percent) display value for MyDino.jsx's bite row, e.g. 6.1 -- the
    # gauge itself keeps using the capped percent (dino.bite) below.
    def _round1(raw):
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None
        if v != v:  # NaN guard
            return None
        return round(v, 1)

    BLEED_MAX_STACKS = 10.0   # observed severe-bleed stack count -> 100%
    SPRINT_MAX_SPEED = 1000.0  # cm/s reference ceiling for apex sprint speed
    BITE_MAX_DAMAGE = 50.0    # reference ceiling for bite_damage units

    cls = row.get("dino") or row.get("dino_class") or row.get("class") or ""
    species_name = _bare_species(cls)

    # growth on the ipc row is a 0-1 fraction (same convention as the other growth
    # readers in this file, e.g. the active-dino "live" snapshot at ~L2879 and
    # vault.py's growth_pct) — MyDino.jsx renders it as Math.round(growth)+"%",
    # so it must be converted to a 0-100 percent here, not passed through raw.
    growth_raw = row.get("growth")
    try:
        growth_pct = round(float(growth_raw) * 100, 1) if growth_raw is not None else None
    except (TypeError, ValueError):
        growth_pct = None

    prime_summary = _prime_progress_summary(sid)
    prime_mig = (prime_summary.get("mig") or {}) if isinstance(prime_summary, dict) else {}
    prime_pat = (prime_summary.get("pat") or {}) if isinstance(prime_summary, dict) else {}

    dino = {
        "actor_name": row.get("actor_name") or "",
        "class": cls,
        "name": species_name,
        # MyDino.jsx reads dino.species (the backend's own display name field was
        # called "name" — alias it additively so the species header/3D viewer render).
        "species": species_name,
        "growth": growth_pct,
        # primary vitals as 0-100 percents (VitalRow renders them directly as gauge
        # values); the raw current values remain recoverable via *_pct * max_*.
        "health": _vital_pct("health", "max_health"), "max_health": row.get("max_health"),
        "stamina": _vital_pct("stamina", "max_stamina"), "max_stamina": row.get("max_stamina"),
        "hunger": _vital_pct("hunger", "max_hunger"), "max_hunger": row.get("max_hunger"),
        "thirst": _vital_pct("thirst", "max_thirst"), "max_thirst": row.get("max_thirst"),
        "oxygen": row.get("oxygen"), "max_oxygen": row.get("max_oxygen"),
        "health_pct": _pct("health", "max_health"),
        "stamina_pct": _pct("stamina", "max_stamina"),
        "hunger_pct": _pct("hunger", "max_hunger"),
        "thirst_pct": _pct("thirst", "max_thirst"),
        # blood / bleed + sprint + bite/damage (null -> frontend shows "pendiente")
        "bleeding_stacks": row.get("bleeding_stacks"),
        "sprint": _capped_pct(row.get("movement_speed"), SPRINT_MAX_SPEED),
        "movement_speed": row.get("movement_speed"),
        "bite_damage": row.get("bite_damage"),
        # MyDino.jsx VITAL_DEFS gauges — additive, derived from the raw fields above.
        # "blood" is a blood-integrity gauge (100 = healthy/no bleed), not a bleed-severity
        # gauge — 0 bleeding_stacks must render 100, not 0.
        "blood": _blood_integrity_pct(row.get("bleeding_stacks"), BLEED_MAX_STACKS),
        "bite": _capped_pct(row.get("bite_damage"), BITE_MAX_DAMAGE),
        # raw bite damage (e.g. 6.1) for MyDino.jsx's "Fuerza de Mordida" row text;
        # the bar above stays driven by the capped percent ("bite").
        "bite_value": _round1(row.get("bite_damage")),
        # per-limb fractures (flat, as before) ...
        "fracture_head": row.get("fracture_head"), "fracture_head_max": row.get("fracture_head_max"),
        "fracture_body": row.get("fracture_body"), "fracture_body_max": row.get("fracture_body_max"),
        "fracture_legs": row.get("fracture_legs"), "fracture_legs_max": row.get("fracture_legs_max"),
        # ... plus the nested dino.fractures.{head,body,legs} percent MyDino.jsx reads.
        "fractures": {
            "head": _fpct("fracture_head", "fracture_head_max"),
            "body": _fpct("fracture_body", "fracture_body_max"),
            "legs": _fpct("fracture_legs", "fracture_legs_max"),
        },
        # diet carb/protein/lipid (flat, as before) ...
        "diet_a": row.get("diet_a"), "diet_b": row.get("diet_b"), "diet_c": row.get("diet_c"),
        "diet_meter": row.get("diet_meter"), "diet_max": row.get("diet_max"),
        # ... plus the nested dino.diet.{carb,protein,lipid} percent MyDino.jsx reads.
        "diet": {
            "carb": _fpct("diet_a", "diet_max"),
            "protein": _fpct("diet_b", "diet_max"),
            "lipid": _fpct("diet_c", "diet_max"),
        },
        # mutations + prime
        "mutations": row.get("mutations") or "",
        "parent_mutations": row.get("parent_mutations") or "",
        "elder_mutations": row.get("elder_mutations") or "",
        "elder_stacks": row.get("elder_stacks"),
        # On a live-only row the catalogue has not been built yet, so prime/elder
        # are UNKNOWN -- serve None (badge hidden) rather than a hard False that
        # would claim a prime dino is not prime for the next shard's worth of time.
        "is_prime": None if row.get("heavy_missing") else bool(row.get("is_prime")),
        "is_elder": None if row.get("heavy_missing") else bool(row.get("is_elder")),
        "prime_conditions": row.get("prime_conditions"),
        "l_mig": row.get("l_mig"),
        "l_pat": row.get("l_pat"),
        # MyDino.jsx falls back to dino.prime_progress.{mig,pat}.{count,cap} when
        # l_mig/l_pat are absent — nest the same summary here (count, not the
        # backend's internal "n" key) so that fallback path also resolves.
        "prime_progress": {
            "mig": {"count": prime_mig.get("n", 0), "cap": prime_mig.get("cap", 2)},
            "pat": {"count": prime_pat.get("n", 0), "cap": prime_pat.get("cap", 4)},
        },
        # live in-game skin (None when the actor has no snapshot yet) -- SpeciesViewer3D.jsx
        # feeds this into FleetDinoModel's tint-mask material.
        "skin": _dino_skin(row.get("actor_name") or ""),
        # which lane served this read (see _livedino_source) + how old the heavy
        # catalogue behind it is. Additive: the frontend ignores unknown keys.
        "live_source": _livedino_source(row),
        "heavy_age_s": row.get("heavy_age_s"),
    }
    # live-map self-pin — MyDino.jsx passes meState.position straight to
    # InteractiveMap, which feeds worldToPct(position.x, position.y) with RAW UE
    # world coords (finite numbers required; it null-guards anything else). None-safe:
    # missing/non-numeric/NaN coords -> position None, frontend simply hides the pin.
    def _self_position():
        try:
            px = float(row.get("x"))
            py = float(row.get("y"))
        except (TypeError, ValueError):
            return None
        if px != px or py != py:  # NaN guard
            return None
        return {"x": px, "y": py}

    # "dino" is additive: MyDino.jsx reads meState.dino (not meState.active). Keep
    # "active" too in case any other consumer relies on the original key.
    return {"active": dino, "dino": dino, "prime_status": row.get("is_prime"),
            "prime_progress": prime_summary, "in_game": True,
            "position": _self_position()}


# ---------- live map: self position (RAW world coords) + AI creatures ----------
def _pos_row(sid, entry):
    try:
        ue_x = float(entry.get("x"))
        ue_y = float(entry.get("y"))
    except (TypeError, ValueError):
        return None
    if ue_x != ue_x or ue_y != ue_y:
        return None
    ts = int(entry.get("last_updated") or 0)
    return {"steam_id": str(sid), "ue_x": ue_x, "ue_y": ue_y, "dino": entry.get("dino"), "ts": ts}


@api_router.get("/positions")
def get_positions(all_: int = Query(0, alias="all"), user=Depends(get_current_user)):
    server_now = int(_time.time())
    sid = str(user.get("steam_id") or "").strip()
    if all_:
        if not _is_owner(user):
            raise HTTPException(status_code=403, detail="Solo el Dueño puede ver el mapa completo.")
        players = game_ipc.read_players_json() or {}
        rows = []
        for k, v in players.items():
            if not isinstance(v, dict):
                continue
            r = _pos_row(v.get("steamid") or k, v)
            if r:
                rows.append(r)
        return {"updated": server_now, "source": "local", "status": "ok",
                "players": rows, "count": len(rows), "server_now": server_now}
    empty = {"updated": 0, "source": "local", "status": "ok", "you": None,
             "players": [], "server_now": server_now, "you_age": None, "fresh": False}
    if not sid:
        return empty
    entry = game_ipc.read_player_display(sid)
    if not isinstance(entry, dict):
        return empty
    you = _pos_row(sid, entry)
    if you is None:
        return empty
    you_age = max(0, server_now - you["ts"]) if you["ts"] else None
    return {"updated": you["ts"], "source": "local", "status": "ok", "you": you,
            "players": [you], "server_now": server_now, "you_age": you_age,
            "fresh": (you_age is not None and you_age <= 30)}


_AI_TTL_SECS = 2.5
_AI_STALE_SECS = 120
_ai_cache = {"ts": 0.0, "body": None}
_ai_cache_lock = threading.Lock()


def _clean_ai_species(raw):
    s = str(raw or "").strip().split("_C_")[0]
    if s.startswith("BP_AI_"):
        s = s[6:]
    elif s.startswith("BP_"):
        s = s[3:]
    if s.endswith("_C"):
        s = s[:-2]
    for v in ("_Plains", "_Coastal", "_Highlands", "_Baby"):
        if s.endswith(v):
            s = s[:-len(v)]
    return s[:40]


@api_router.get("/ai_positions")
def get_ai_positions(user=Depends(get_current_user)):
    now = _time.monotonic()
    if _ai_cache["body"] is not None and now - _ai_cache["ts"] < _AI_TTL_SECS:
        return _ai_cache["body"]
    with _ai_cache_lock:
        now = _time.monotonic()
        if _ai_cache["body"] is not None and now - _ai_cache["ts"] < _AI_TTL_SECS:
            return _ai_cache["body"]
        body = {"updated": 0, "source": None, "status": "no_source", "count": 0, "ai": []}
        try:
            path = game_ipc.AI_POSITIONS_JSON
            if os.path.exists(path) and _time.time() - os.path.getmtime(path) <= _AI_STALE_SECS:
                raw = game_ipc.read_json_file(path) or {}
                ai = []
                for a in (raw.get("ai") or []):
                    if not isinstance(a, dict):
                        continue
                    try:
                        ax = float(a.get("ue_x", a.get("x")))
                        ay = float(a.get("ue_y", a.get("y")))
                    except (TypeError, ValueError):
                        continue
                    if ax != ax or ay != ay or (ax == 0.0 and ay == 0.0):
                        continue
                    rs = str(a.get("species") or a.get("class") or a.get("dino") or "")
                    if "Default__" in rs:
                        continue
                    sp = _clean_ai_species(rs)
                    if not sp or sp == "INVALID":
                        continue
                    ai.append({"species": sp, "ue_x": ax, "ue_y": ay, "ts": int(a.get("ts") or 0)})
                body = {"updated": int(raw.get("updated") or 0), "source": "local",
                        "status": "ok", "count": len(ai), "ai": ai}
        except Exception:
            pass
        _ai_cache["ts"] = now
        _ai_cache["body"] = body
        return body


# ---------- vault (La Bóveda): park / redeem / slay / list / delete ----------
@api_router.get("/me/vault")
def me_vault(user=Depends(get_current_user)):
    sid = _steam_id_or_400(user)
    return vault.summary(sid, _user_park_cap(user), _web_is_admin(user))


@api_router.post("/me/slay")
def me_slay(user=Depends(get_current_user)):
    return vault.do_slay(_steam_id_or_400(user))


@api_router.post("/me/bodydrop")
def me_bodydrop(user=Depends(get_current_user)):
    """Body Drop: the game drops a fresh corpse NEXT TO the caller's starving
    juvenile carnivore (it never touches the caller's own dino). Blocks up to
    ~25 s for the mod's body_drop_ok/failed ack — sync def, so it rides the
    threadpool like do_slay."""
    return vault.do_bodydrop(_steam_id_or_400(user))


class GrowthPauseInput(BaseModel):
    pause: bool


@api_router.post("/me/growth-pause")
def me_growth_pause(data: GrowthPauseInput, user=Depends(get_current_user)):
    """Pause/resume the caller's LIVE dino growth — the web twin of typing
    the removed in-game /pause + /unpause chat commands did (same queue, same
    C++ consumer, same
    75–100% growth gate; self-only by construction). Blocks up to ~7 s for the
    mod's logged decision — sync def, threadpool like do_slay."""
    return vault.do_growth_pause(_steam_id_or_400(user), bool(data.pause))


@api_router.delete("/me/vault/{dino_id}")
def me_vault_delete(dino_id: int, user=Depends(get_current_user)):
    return vault.do_delete(_steam_id_or_400(user), int(dino_id))


@api_router.post("/me/vault/{dino_id}/rename")
def me_vault_rename(dino_id: int, data: DinoRenameInput, user=Depends(get_current_user)):
    """Give a Bóveda (parked) dino a custom display name. Cosmetic only — shown
    on the vault card/preview and used as the default title when the dino is
    listed on the Mercado; it never reaches the game. Empty name clears it."""
    sid = _steam_id_or_400(user)
    name = vault.clean_custom_name(data.name)
    if (data.name or "").strip() and not name:
        raise HTTPException(status_code=400,
                            detail="Ese nombre no es válido. Usa letras, números o espacios (máximo 32 caracteres).")
    if vault.rename_owned(int(dino_id), sid, name) != 1:
        raise HTTPException(status_code=404, detail="Ese dinosaurio guardado no te pertenece o no existe.")
    return {"success": True, "custom_name": name or None}


@api_router.post("/me/vault/park")
def me_vault_park(user=Depends(get_current_user)):
    sid = _steam_id_or_400(user)
    return vault.start_park(sid, vault.resolve_discord_id(sid), _user_park_cap(user))


@api_router.post("/me/vault/redeem")
def me_vault_redeem(body: _DinoIdIn, user=Depends(get_current_user)):
    return vault.start_redeem(_steam_id_or_400(user), int(body.dino_id))


@api_router.get("/me/vault/job/{job_id}")
def me_vault_job(job_id: str, user=Depends(get_current_user)):
    sid = _steam_id_or_400(user)
    job = vault.get_job(job_id)
    if not job or str(job.get("steam_id")) != str(sid):
        raise HTTPException(status_code=404, detail="Trabajo desconocido o expirado.")
    return {"state": job.get("state"), "message": job.get("message"), "kind": job.get("kind"),
            "dino_id": job.get("dino_id"), "slots_used": job.get("slots_used")}


# ---------- vault mutation editor (paid, Dino Den style) ----------
def _mutation_edit_cost() -> int:
    # Owner ruling 2026-07-12: 20,000 PrimeMeat per added/changed mutation.
    try:
        return max(0, int(os.environ.get("LIN_MUTATION_EDIT_COST", "20000") or "20000"))
    except ValueError:
        return 20000


class _MutationSlotIn(BaseModel):
    slot: str = Field(min_length=2, max_length=4)
    mutation: str = Field(default="", max_length=64)


async def _owned_parked_or_404(dino_id: int, sid: str) -> dict:
    # sqlite (WAL, busy_timeout up to 5s) must never block the event loop.
    row = await asyncio.to_thread(vault.get_parked_by_id, int(dino_id))
    if not row or str(row.get("steam_id") or "") != str(sid):
        raise HTTPException(status_code=404, detail="Ese dinosaurio no está en tu bóveda.")
    # A redeem whose verify job died (bounce/crash/timeout) must not lock the
    # dino forever: resolve the stale marker; only a FRESH one blocks below.
    row = await asyncio.to_thread(vault.resolve_stale_redeem_pending, row)
    if not row:
        raise HTTPException(status_code=404, detail="Ese dinosaurio no está en tu bóveda.")
    return row


@api_router.get("/me/vault/{dino_id}/mutations")
async def me_vault_mutations(dino_id: int, user=Depends(get_current_user)):
    sid = _steam_id_or_400(user)
    row = await _owned_parked_or_404(dino_id, sid)
    # HOW MANY TIMES THIS DINO WAS REALLY BURIED — the recorded column, never the
    # derived count the gate uses. The UI prints this as "tu dino: N entierros",
    # so it may only ever be the number that is TRUE of the dino: a row whose
    # parent column proves a lineage step opens its four heredadas without the
    # dino ever having been buried, and publishing that 1 would make the legend
    # lie. Which slots are open travels in slot_locks instead, where it belongs.
    # NEVER int(float(...)) this column here: it is INTEGER in the bot schema
    # but a TEXT-typed column hands back "2.0" and a junk row hands back "abc",
    # and both used to raise right here, OUTSIDE the try below — a 500 on the
    # whole editor instead of a locked slot. elder_stack_count never raises and
    # answers None for anything nobody can stand behind.
    stacks = mutation_catalog.elder_stack_count(row)
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "coins": 1})
    # Per-slot lock state + the plain-Spanish reason, so the editor can show WHY
    # a slot is closed instead of just hiding it. slot_lock_map never raises;
    # the guard here is belt-and-braces so a malformed row can never 500 the
    # editor — it falls back to the same fail-closed answer the rule gives.
    try:
        locks = mutation_catalog.slot_lock_map(row)
        growth = mutation_catalog.growth_fraction(row)
        prime = mutation_catalog.is_prime_flag(row)
    except Exception:
        logging.getLogger("laislanublar.vault").exception(
            "[vault] slot lock map failed sid=%s dino_id=%s", sid, dino_id)
        # Fail closed on EVERY gated slot, own and inherited, each with the copy
        # that belongs to its own ladder.
        locks = {}
        for sid_ in mutation_catalog.SLOT_IDS:
            own_ = sid_ in ("n1", "n2", "n3", "n4")
            locks[sid_] = {
                "locked": True,
                "code": "growth_unknown" if own_ else "entomb_unknown",
                "reason": (mutation_catalog.LOCK_UNREADABLE if own_
                           else mutation_catalog.LOCK_ENTOMB_UNREADABLE),
                "requires_growth_pct": None, "requires_prime": False,
                "requires_entombs": None,
                # Every slot is drawn locked here, so the guarded two-press clear
                # is already the path a held mutation takes.
                "clear_closes": False,
                # ...and a locked slot takes nothing back, so neither way of
                # destroying what it holds can be walked back on this path. Say
                # so on BOTH fields rather than leave either one out: an absent
                # field is the older-server fallback, and the editor reads that
                # as "no answer", which is not what an unreadable row means.
                "clear_blocks_restore": True,
                "overwrite_blocks_restore": True,
                # Nothing was readable here, so nothing may be labelled: this
                # only drives an explanatory line, and a wrong one is worse than
                # none. False is what an unreadable row can honestly say.
                "holds_unlockable": False,
            }
        growth, prime = None, False
    return {
        "dino_id": int(dino_id),
        "slots": mutation_catalog.slots_from_row(row),
        "active_count": mutation_catalog.active_count(row),
        "max_slots": len(mutation_catalog.SLOT_IDS),
        # None when the stored column is unreadable — the UI must not print "0
        # entierros" for a value nobody could parse; slot_locks carries the
        # fail-closed answer either way.
        "elder_stacks": stacks,
        "slot_locks": locks,
        "growth_ladder": mutation_catalog.growth_ladder_view(),
        "entomb_ladder": mutation_catalog.entomb_ladder_view(),
        # THE SAME integer vault._dino_view puts on the card and on the preview
        # header this editor is rendered inside — one dino must never be shown
        # two different growth percentages on one screen. growth_display_pct IS
        # that shared definition; do not inline arithmetic here.
        "growth_pct": mutation_catalog.growth_display_pct(growth),
        "is_prime": prime,
        "unlocked": {
            # Each family now means "at least one slot in it is open" — every
            # ladder is per-slot, and slot_locks carries the real answer. The
            # elder entries used to call elder_set_unlocked, which always said
            # yes (superseded 2026-07-12 ruling); no caller consults a function
            # like that any more.
            "child": any(not locks[s]["locked"] for s in ("n1", "n2", "n3", "n4")),
            "parent": any(not locks[s]["locked"] for s in ("p1", "p2", "p3", "p4")),
            "elder_a": any(not locks[s]["locked"] for s in ("ea1", "ea2", "ea3", "ea4")),
            "elder_b": any(not locks[s]["locked"] for s in ("eb1", "eb2", "eb3", "eb4")),
        },
        "diet": mutation_catalog.dino_type(str(row.get("dino_class") or "")),
        # The full diet-legal catalog, unlockables included: this is what the
        # editor looks a STORED value up in to render its name and description,
        # so a dino already holding an unlockable in n1 keeps showing it.
        "catalog": mutation_catalog.catalog_for_class(str(row.get("dino_class") or "")),
        # WHICH of those names each slot will actually accept (owner ruling
        # 2026-07-27: n1 and n3 do not offer the mutations the game makes you
        # unlock; n2, n4 and all twelve inherited slots offer everything). The
        # picker filters on this, so it can never offer a name the POST would
        # then refuse — and it never has to know the rule, only the answer.
        #
        # SPARSE: only the slots whose list DIFFERS travel, and a slot that is
        # absent offers the whole `catalog` above. The other fourteen lists are
        # identical to it and to each other, so sending all sixteen was ~11 KB of
        # duplicated names per open on a route with no gzip in front of it. The
        # editor already had to handle an absent entry that way, because an older
        # server sends no such field at all.
        "slot_catalog": mutation_catalog.slot_catalog_overrides(str(row.get("dino_class") or "")),
        # Two server-written sentences for a slot whose list came back shorter,
        # so a missing mutation is explained rather than silently absent. The
        # second one is for a slot that ALREADY holds one of them: the row keeps
        # it (this rule gates new writes only) and the copy has to say so.
        # Named "unlockable", never "hidden" — see catalog_for_class: Tailwind's
        # token scan over web/frontend/src would turn the bare word into CSS.
        #
        # THE ROW GOES IN so the sentence can name the ranuras THIS dino can
        # reach right now. n2 wants 50% growth and n4 wants 75% AND Prime, so the
        # old unconditional "ponla en la 2ª o en la 4ª" was, on a young or
        # non-Prime dino, a move the player could not make.
        "unlockable_notice": mutation_catalog.hidden_notice(row),
        "unlockable_kept_notice": mutation_catalog.hidden_kept_notice(),
        "cost_per_change": _mutation_edit_cost(),
        "balance": int((fresh or {}).get("coins", 0)),
    }


@api_router.post("/me/vault/{dino_id}/mutations")
async def me_vault_mutations_set(dino_id: int, body: _MutationSlotIn, user=Depends(get_current_user)):
    sid = _steam_id_or_400(user)
    row = await _owned_parked_or_404(dino_id, sid)
    if str(row.get("redeem_pending_cmd_id") or "").strip():
        raise HTTPException(status_code=409, detail="Hay una recuperación en progreso para ese dinosaurio; inténtalo después.")

    # THE POST IS THE AUTHORITY. validate_slot_edit carries every rule — diet,
    # duplicates AND the growth/Prime ladder on n1..n4 — and it runs BEFORE the
    # cost is computed and before the PrimeMeat debit below, so a rejected edit
    # can never be charged. Keep it first if this block is ever reordered.
    # Clearing a slot stays allowed (and free) even when the slot is locked.
    try:
        new_value, current = mutation_catalog.validate_slot_edit(row, body.slot, body.mutation)
    except mutation_catalog.MutationEditError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cost = _mutation_edit_cost()
    # Clearing a slot and true no-ops are free; only adding/changing a mutation charges.
    same = (mutation_catalog.normalize_mutation_name(current)
            == mutation_catalog.normalize_mutation_name(new_value)) or (current == "None" and new_value == "None")
    if same:
        return {"changed": False, "charged": 0, "slots": mutation_catalog.slots_from_row(row),
                "active_count": mutation_catalog.active_count(row),
                "balance": int(user.get("coins", 0))}
    charge = 0 if new_value == "None" else cost

    if charge > 0:
        res = await db.users.update_one(
            {"id": user["id"], "coins": {"$gte": charge}}, {"$inc": {"coins": -charge}})
        if res.modified_count == 0:
            raise HTTPException(status_code=400, detail=f"PrimeMeat insuficiente: editar una mutación cuesta {charge:,}.")

    new_strings = mutation_catalog.apply_slot_edit(row, body.slot, new_value)
    error = None
    try:
        written, _reason = await asyncio.to_thread(
            vault.cas_update_mutations, int(dino_id), sid, row, new_strings)
    except HTTPException as e:
        written, error = False, e
    except Exception:
        logging.getLogger("laislanublar.vault").exception(
            "[vault] mutation edit write crashed sid=%s dino_id=%s slot=%s", sid, dino_id, body.slot)
        written = False
    if not written:
        if charge > 0:
            await db.users.update_one({"id": user["id"]}, {"$inc": {"coins": charge}})
        raise error or HTTPException(status_code=409, detail="El dinosaurio cambió mientras editabas; recarga e inténtalo de nuevo.")

    species = str(row.get("dino_class") or "").replace("BP_", "").replace("_C", "")
    if charge > 0:
        await add_transaction(user["id"], "normal", -charge, "purchase",
                              f"Edición de mutación: {new_value} ({species}, ranura {body.slot})")
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "coins": 1})
    updated = (await asyncio.to_thread(vault.get_parked_by_id, int(dino_id))) or {**row, **new_strings}
    logging.getLogger("laislanublar.vault").info(
        "[vault] mutation edit sid=%s dino_id=%s slot=%s value=%s charged=%d",
        sid, dino_id, body.slot, new_value, charge)
    return {"changed": True, "charged": charge,
            "slots": mutation_catalog.slots_from_row(updated),
            "active_count": mutation_catalog.active_count(updated),
            # THE LOCKS TRAVEL WITH THE EDIT, recomputed on the row as it now
            # stands. An edit can MOVE them: the heredadas of a row whose counter
            # says 0 are open only because that column holds a mutation, so
            # emptying the last one closes all four, and a UI still holding the
            # locks the GET sent would draw them open and, worse, would offer the
            # unguarded one-press "Quitar" on the next slot (slot_lock_map's
            # clear_closes is what arms that guard). Both never raise.
            "slot_locks": mutation_catalog.slot_lock_map(updated),
            "elder_stacks": mutation_catalog.elder_stack_count(updated),
            "dino": vault._dino_view(updated),
            "balance": int((fresh or {}).get("coins", 0))}


# ---------- teleport ----------
@api_router.post("/admin/teleport")
async def admin_teleport(body: AdminTeleportIn, user=Depends(get_owner_user)):
    if not teleport_presets.coords_in_bounds(body.x, body.y):
        raise HTTPException(status_code=400, detail="Coordenadas fuera de los límites del mapa.")
    ok = await asyncio.to_thread(game_ipc.write_game_command, {
        "type": "teleport", "steamid": str(body.steamid),
        "x": float(body.x), "y": float(body.y), "z": float(body.z)})
    if not ok:
        raise HTTPException(status_code=500, detail="No se pudo enviar el teletransporte.")
    return {"ok": True, "steamid": str(body.steamid)}


# ---------- skins ----------
@api_router.get("/species")
def list_species(user=Depends(get_current_user)):
    root = Path(game_ipc.DINO_ASSETS_ROOT)
    out = []
    for cls in pop_control.SUPPORTED_SPECIES:
        name = _bare_species(cls)
        d = root / name
        ready = (d / "mesh.glb").is_file() and (d / "tint_mask.png").is_file()
        # The species picker already renders `image` when we send one and falls
        # back to a generic palette glyph when we do not - which is what every
        # tile has been showing, so all 22 look identical and telling them apart
        # means reading the small caption. Send the transparent square render
        # (the same art the rest of the site uses for a species) so each tile
        # shows its own animal. Species with no art keep the glyph.
        slug = game_telemetry._slug(name)
        image = seed_data.DINO_RENDER.get(slug) or seed_data.DINO_IMG.get(slug)
        out.append({"name": name, "class": cls, "ready": ready, "image": image})
    return {"species": out}


_DINO_ASSET_EXTS = {".glb", ".webp", ".png", ".jpg", ".jpeg", ".bin", ".ktx2"}


@app.get("/dino-assets/{species}/{filename}")
async def dino_asset(request: Request, species: str, filename: str):
    # Public static game art: three.js loaders fetch without the auth header,
    # so this route stays open. Safety = resolved-path containment + extension
    # allowlist over a root that only holds shared species art.
    try:
        root = Path(game_ipc.DINO_ASSETS_ROOT).resolve()
    except OSError:
        raise HTTPException(status_code=404, detail="asset not found")
    target = (root / species / filename).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="path outside asset root")
    if target.suffix.lower() not in _DINO_ASSET_EXTS:
        raise HTTPException(status_code=404, detail="asset not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    # Species files get replaced on the box under the same names (asset waves), so
    # a year-immutable answer freezes a bad file into every browser that saw it.
    # Short freshness + revalidation makes swaps visible within minutes, and the
    # explicit ETag/304 pair keeps the re-checks near-free. A bare FileResponse
    # never answers 304 itself, so the conditional check must live here.
    stat = target.stat()
    etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
    cache_headers = {"Cache-Control": "public, max-age=300, must-revalidate", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cache_headers)
    return FileResponse(str(target), headers=cache_headers)


@api_router.get("/skin-map")
def get_skin_map(user=Depends(get_current_user)):
    d = _read_json_or(_SKIN_MAP_PATH, {})
    return {"map": d if isinstance(d, dict) else {}}


@api_router.put("/skin-map")
def put_skin_map(body: SkinMapIn, user=Depends(get_owner_user)):
    keys, vals = set(body.mapping.keys()), set(body.mapping.values())
    if keys - _VALID_SLOT_KEYS or vals - _VALID_SLOT_KEYS:
        raise HTTPException(status_code=400, detail="Claves de slot inválidas.")
    if len(set(body.mapping.values())) != len(body.mapping.values()):
        raise HTTPException(status_code=400, detail="Cada slot debe mapear a una región única.")
    with _skin_meta_lock:
        cur = _read_json_or(_SKIN_MAP_PATH, {})
        cur = dict(cur) if isinstance(cur, dict) else {}
        cur[body.species] = dict(body.mapping)
        _atomic_write_json(_SKIN_MAP_PATH, cur)
    return {"ok": True, "species": body.species, "mapping": body.mapping}


@api_router.get("/material-scalars")
def get_material_scalars(user=Depends(get_current_user)):
    d = _read_json_or(_MATERIAL_SCALARS_PATH, {})
    return {"scalars": d if isinstance(d, dict) else {}}


def _presets_path(sid):
    safe = re.sub(r"[^0-9A-Za-z_-]", "_", str(sid))[:32]
    return os.path.join(_PRESETS_DIR, f"{safe}.json")


def _read_presets(sid):
    d = game_ipc.read_json_file(_presets_path(sid))
    return d if isinstance(d, list) else []


def _write_presets(sid, presets):
    with _skin_meta_lock:
        _atomic_write_json(_presets_path(sid), presets)


@api_router.get("/presets")
def list_presets(user=Depends(get_current_user)):
    return {"presets": _read_presets(_steam_id_or_400(user))}


def _verified_raw_sidecar(sid, raw_model, glitch_entitled=False):
    """Validate + WITNESS an exact-copy sidecar against the caller's live dino.

    The save lane is free, so it must never become a door for minting arbitrary
    glitch-space payloads: a sidecar is stored only when the caller's own dino
    is wearing exactly these bytes right now (slot-for-slot snapshot match).
    Raises 422 (invalid shape/bounds/poison) or 409 (not witnessed live).

    glitch_entitled=True (server-verified Glitch Lab entitlement, NEVER a
    request field) is the 2026-08-23 authoring door: the sidecar is stamped
    glitch_grant (channel-sentinel waiver; pattern -8 still refuses) and the
    live-dino witness is waived — for these accounts authoring arbitrary
    glitch payloads IS the feature. Everyone else keeps the exact old rules."""
    raw = raw_model.model_dump()
    if glitch_entitled:
        raw[skin_exact.GLITCH_GRANT_KEY] = True
    ok, reason = skin_exact.validate_raw(raw)
    if not ok:
        raise HTTPException(status_code=422, detail="La copia exacta no es válida (%s)." % reason)
    if glitch_entitled:
        return raw
    dino = game_ipc.find_active_dino(sid)
    snap = game_ipc.read_skin_snapshot(dino["actor_name"]) if dino else None
    if not dino or not skin_exact.raw_matches_snapshot(raw, snap):
        raise HTTPException(status_code=409, detail=(
            "La copia exacta no coincide con la skin que tu dino lleva ahora — "
            "pulsa «Copiar mi skin actual» de nuevo."))
    return raw


async def _glitch_entitled_for_save(user):
    """Live Glitch Lab verdict for the preset save/update lanes. Fail-CLOSED:
    an access-check error means 'not entitled' (the witness path still works),
    never a 500 on the whole save."""
    try:
        access = await _patreon_access(user)
    except Exception:
        logger.exception("[glitchlab] access check failed sid=%s", user.get("steam_id"))
        return False
    return bool(_glitch_creator_verdict(user, access)["allowed"])


@api_router.post("/presets")
async def save_preset(body: SkinPresetIn, user=Depends(get_current_user)):
    sid = _steam_id_or_400(user)
    presets = await asyncio.to_thread(_read_presets, sid)
    pid = new_id()
    entry = {"id": pid, "name": body.name, "dino_class": body.dino_class,
             "payload": body.payload.model_dump()}
    if body.raw is not None:
        glitch_ok = await _glitch_entitled_for_save(user)
        entry["raw"] = await asyncio.to_thread(_verified_raw_sidecar, sid, body.raw, glitch_ok)
    presets.append(entry)
    if len(presets) > 100:
        presets = presets[-100:]
    await asyncio.to_thread(_write_presets, sid, presets)
    return {"id": pid}


@api_router.put("/presets/{preset_id}")
async def update_preset(preset_id: str, body: SkinPresetIn, user=Depends(get_current_user)):
    sid = _steam_id_or_400(user)
    presets = await asyncio.to_thread(_read_presets, sid)
    found = False
    for p in presets:
        if str(p.get("id")) == str(preset_id):
            p.update(name=body.name, dino_class=body.dino_class, payload=body.payload.model_dump())
            if body.raw is not None:
                glitch_ok = await _glitch_entitled_for_save(user)
                p["raw"] = await asyncio.to_thread(_verified_raw_sidecar, sid, body.raw, glitch_ok)
            else:
                # An edited payload is no longer the witnessed copy — drop the
                # sidecar rather than let it contradict what the editor shows.
                p.pop("raw", None)
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Preset no encontrado.")
    await asyncio.to_thread(_write_presets, sid, presets)
    return {"id": preset_id}


@api_router.delete("/presets/{preset_id}")
def del_preset(preset_id: str, user=Depends(get_current_user)):
    sid = _steam_id_or_400(user)
    presets = _read_presets(sid)
    kept = [p for p in presets if str(p.get("id")) != str(preset_id)]
    if len(kept) == len(presets):
        raise HTTPException(status_code=404, detail="Preset no encontrado.")
    _write_presets(sid, kept)
    return {"ok": True}


@api_router.post("/apply")
async def apply_skin(body: SkinPayloadIn, user=Depends(get_current_user)):
    # Patreon-only lane: live Discord tier-role check (or active Patreon pledge / admin).
    # The 403 detail is a structured object the skin editor renders as a full explanation.
    access = await _patreon_access(user)
    if not access["allowed"]:
        raise HTTPException(status_code=403, detail={"code": "patreon_required", "access": access})
    if not _skin_creator_allowed(access):
        _pretty = {"juvie": "Juvie", "sub": "Sub Adult", "adult": "Adult", "elder": "Elder", "apex": "Apex"}
        raw = str(access.get("tier") or "Patreon")
        tier_label = _pretty.get(_patreon_tier_key(raw) or "", raw)
        raise HTTPException(status_code=403, detail={
            "code": "tier_insufficient", "access": access,
            "message": f"El creador de skins está incluido desde el nivel Sub Adult en adelante — tu nivel actual ({tier_label}) no lo incluye."})
    sid = _steam_id_or_400(user)
    # THE ONE BUDGET, shared with /api/studio/apply-v2 (2026-08-25). This lane
    # was unmetered; see `_enforce_skin_apply_rate`. Checked before the roster
    # read so a rate-limited caller costs this box nothing.
    _enforce_skin_apply_rate(sid)
    dino = await asyncio.to_thread(game_ipc.find_active_dino, sid)
    if not dino:
        raise HTTPException(status_code=409, detail="No tienes un dino activo — entra al juego primero.")
    await asyncio.to_thread(_ghost_gate_check, sid, dino, "studio")
    # Session may apply ONLY to their own steamid: the command is built from the
    # session's own active dino + steam_id, never a client-supplied target.
    cmd = body.to_command(dino["actor_name"], dino["class"], sid)
    # The skin creator paints COLOURS -- it must never change the dinosaur's sex.
    # The editor has no sex control, so SkinPayloadIn.female always arrives as its
    # False default, and the mod writes the command's value straight into
    # CustomizerData.bIsFemale: every apply silently turned a female dino male
    # (owner report 2026-07-25). preserve_female makes the LIVE pawn's sex win,
    # fail-closed in the mod (an unreadable sex refuses the block into its own
    # retry lane instead of guessing a flip). The key is NOT transient, so the
    # SkinKeeper recipe stores it and the rejoin restore preserves sex as well.
    cmd["preserve_female"] = True
    if not await asyncio.to_thread(game_ipc.write_skin_command, cmd):
        raise HTTPException(status_code=500, detail="No se pudo aplicar la skin. Intenta de nuevo.")
    # SkinKeeper capture (studio self-apply). Keyed on the session's own sid.
    await asyncio.to_thread(skinkeeper_web.record_apply, cmd, "regular")
    return {"ok": True, "actor_name": dino["actor_name"], "class": dino["class"]}


class AdminApplyIn(BaseModel):
    steamid: str = Field(min_length=1, max_length=32)
    payload: SkinPayloadIn


@api_router.post("/admin/apply")
def admin_apply_skin(body: AdminApplyIn, user=Depends(get_owner_user)):
    """Apply a skin to another player's active dino. Owner-only: a regular
    session may only skin its OWN steamid via /api/apply, never a target."""
    dino = game_ipc.find_active_dino(str(body.steamid))
    if not dino:
        raise HTTPException(status_code=409, detail="Ese jugador no tiene un dino activo.")
    if game_ipc.actor_live_in_engine(dino.get("actor_name")) is False:
        logger.info("[skins] ghost_gate refused sid=%s actor=%s lane=admin",
                    str(body.steamid), dino.get("actor_name"))
        raise HTTPException(status_code=409, detail=(
            "Ese jugador acaba de cambiar de dino — reintenta en unos segundos."))
    cmd = body.payload.to_command(dino["actor_name"], dino["class"], str(body.steamid))
    # Same rule as /api/apply: an owner painting a player's dino changes its
    # colours, never its sex. The live pawn wins (fail-closed in the mod).
    cmd["preserve_female"] = True
    if not game_ipc.write_skin_command(cmd):
        raise HTTPException(status_code=500, detail="No se pudo aplicar la skin.")
    # SkinKeeper capture (admin apply) -- SYNC route, SYNC recorder. Keyed on the
    # TARGET player's sid (cmd['steamid'] == body.steamid), never the acting owner.
    skinkeeper_web.record_apply(cmd, "regular")
    return {"ok": True, "steamid": str(body.steamid), "actor_name": dino["actor_name"], "class": dino["class"]}


class ApplyPresetIn(BaseModel):
    preset_id: str = Field(min_length=1, max_length=64)


def _skin_creator_tier_403(access):
    """The same tier refusal POST /api/apply raises inline. Kept in lockstep by
    the gate-parity check in tests_local/test_skin_exact_copy.py."""
    _pretty = {"juvie": "Juvie", "sub": "Sub Adult", "adult": "Adult", "elder": "Elder", "apex": "Apex"}
    raw = str(access.get("tier") or "Patreon")
    tier_label = _pretty.get(_patreon_tier_key(raw) or "", raw)
    return HTTPException(status_code=403, detail={
        "code": "tier_insufficient", "access": access,
        "message": f"El creador de skins está incluido desde el nivel Sub Adult en adelante — tu nivel actual ({tier_label}) no lo incluye."})


@api_router.post("/apply-preset")
async def apply_preset_exact(body: ApplyPresetIn, user=Depends(get_current_user)):
    """Replay a saved EXACT copy (skin_exact sidecar) verbatim onto the caller's
    live dino. Same Patreon gate as POST /api/apply — copying and saving stay
    free, APPLYING is the perk. The editor lane cannot carry these payloads
    (SkinPayloadIn pins every channel to 0..1 and would decode+jitter them),
    which is the entire reason this door exists."""
    access = await _patreon_access(user)
    if not access["allowed"]:
        raise HTTPException(status_code=403, detail={"code": "patreon_required", "access": access})
    if not _skin_creator_allowed(access):
        raise _skin_creator_tier_403(access)
    sid = _steam_id_or_400(user)
    dino = await asyncio.to_thread(game_ipc.find_active_dino, sid)
    if not dino:
        raise HTTPException(status_code=409, detail="No tienes un dino activo — entra al juego primero.")
    await asyncio.to_thread(_ghost_gate_check, sid, dino, "preset")
    presets = await asyncio.to_thread(_read_presets, sid)
    p = next((x for x in presets if str(x.get("id")) == body.preset_id), None)
    if not p:
        raise HTTPException(status_code=404, detail="Preset no encontrado.")
    raw = p.get("raw")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail=(
            "Este preset no guarda una copia exacta — cárgalo en el editor y aplícalo desde ahí."))
    ok, reason = skin_exact.validate_raw(raw)
    if not ok:
        raise HTTPException(status_code=422, detail=(
            "La copia exacta guardada ya no es válida (%s) — vuelve a copiarla." % reason))
    cmd = skin_exact.build_exact_command(raw, dino["actor_name"], dino["class"], sid)
    if not await asyncio.to_thread(game_ipc.write_skin_command, cmd):
        raise HTTPException(status_code=500, detail="No se pudo aplicar la skin. Intenta de nuevo.")
    # Glitch-kind SkinKeeper capture: the recipe is the command as ENQUEUED and
    # the rejoin restore replays it VERBATIM — the exact copy survives relogs.
    await asyncio.to_thread(skinkeeper_web.record_apply, cmd, "glitch")
    return {"ok": True, "exact": True, "actor_name": dino["actor_name"], "class": dino["class"]}


# ---------- Glitch Lab (2026-08-23 owner order: custom glitch skin creator ----
# with raw numbers; access = website owners + Streamer role + Adult/Elder/Apex;
# copied/authored glitch skins must ACTUALLY apply in game) ----


class GlitchApplyIn(BaseModel):
    raw: RawSkinSidecarIn


@api_router.get("/glitch-access")
async def glitch_access(user=Depends(get_current_user)):
    """The Glitch Lab entitlement verdict for the UI. Live tier check (same
    _patreon_access the apply lanes trust), owner short-circuit."""
    try:
        access = await _patreon_access(user)
    except Exception:
        logger.exception("[glitchlab] access check failed sid=%s", user.get("steam_id"))
        access = {"allowed": False, "via": None, "tier": None}
    return _glitch_creator_verdict(user, access)


@api_router.post("/glitch/apply")
async def glitch_apply(body: GlitchApplyIn, user=Depends(get_current_user)):
    """Apply an AUTHORED glitch payload verbatim to the caller's own live dino.

    The Glitch Lab door: unlike /api/apply-preset there is no stored preset and
    no live-dino witness — the payload is whatever numbers the creator typed.
    Gate = website owners + Streamer role + Adult/Elder/Apex (server-verified
    per request, so a lapsed tier or removed role refuses immediately). The
    command is built exactly like the
    proven crate/exact lanes (raw floats, no sRGB decode, preserve_female) and
    recorded as a glitch SkinKeeper recipe so it survives relogs."""
    access = await _patreon_access(user)
    verdict = _glitch_creator_verdict(user, access)
    if not verdict["allowed"]:
        raise _glitch_tier_403(access, verdict)
    sid = _steam_id_or_400(user)
    dino = await asyncio.to_thread(game_ipc.find_active_dino, sid)
    if not dino:
        raise HTTPException(status_code=409, detail="No tienes un dino activo — entra al juego primero.")
    await asyncio.to_thread(_ghost_gate_check, sid, dino, "glitchlab")
    raw = body.raw.model_dump()
    # Server-side stamp, NEVER a request field (RawSkinSidecarIn drops extras):
    # the entitlement just verified above is the reason these bytes are legal.
    raw[skin_exact.GLITCH_GRANT_KEY] = True
    ok, reason = skin_exact.validate_raw(raw)
    if not ok:
        raise HTTPException(status_code=422, detail="El diseño glitch no es válido (%s)." % reason)
    # Session may apply ONLY to itself: actor/class/sid come from the caller's
    # own active dino, never the body.
    cmd = skin_exact.build_exact_command(raw, dino["actor_name"], dino["class"], sid)
    if not await asyncio.to_thread(game_ipc.write_skin_command, cmd):
        raise HTTPException(status_code=500, detail="No se pudo aplicar la skin. Intenta de nuevo.")
    await asyncio.to_thread(skinkeeper_web.record_apply, cmd, "glitch")
    logger.info("[glitchlab] apply sid=%s via=%s actor=%s", sid, verdict["via"], dino["actor_name"])
    return {"ok": True, "glitch": True, "actor_name": dino["actor_name"], "class": dino["class"]}


@api_router.get("/snapshot")
def skin_snapshot(user=Depends(get_current_user)):
    sid = str(user.get("steam_id") or "").strip()
    if not sid:
        return {"active": False}
    dino = game_ipc.find_active_dino(sid)
    if not dino:
        return {"active": False}
    return {"active": True, "actor_name": dino["actor_name"], "class": dino["class"],
            "skin": game_ipc.read_skin_snapshot(dino["actor_name"])}


# ---------- admin population control (PLAYER species caps; never AI/RCON) ------
@api_router.get("/admin/pop/state")
def admin_pop_state(user=Depends(get_owner_user)):
    return pop_control.state()


@api_router.post("/admin/pop/preview")
def admin_pop_preview(body: PopPreviewIn, user=Depends(get_owner_user)):
    return pop_control.preview({c.species: int(c.cap) for c in body.changes},
                               body.lock, body.unlock, body.auto)


@api_router.post("/admin/pop/apply")
def admin_pop_apply(body: PopApplyIn, user=Depends(get_owner_user)):
    actor = str(user.get("steam_id") or user.get("id") or "web-admin")
    return pop_control.apply({c.species: int(c.cap) for c in body.changes},
                             body.lock, body.unlock, body.auto, actor, body.reason)


@api_router.get("/admin/pop/audit")
def admin_pop_audit(limit: int = 100, user=Depends(get_owner_user)):
    return pop_control.audit(limit)


# ---------- voice ----------
@api_router.post("/voice/token")
def voice_token_endpoint(request: Request, user=Depends(get_current_user)):
    sid = _steam_id_or_400(user)
    return voice_token.mint_token(sid, _req_client_ip(request))


# =============================================================================
# CREATOR PROGRAM (2026-08-17, owner order — bundle v2 adapted to this backend)
#
# Referral system: an admin-made creator hands out a code; a new player applies
# it once, and when that player has REALLY joined the island (linked Steam +
# minimum minutes played, fed by the passive telemetry drain) both sides get
# PrimeMeat. Milestones pay one-time bonuses; the exclusive catalog glitch
# design "leyenda-creador" lands at `skin_target` referrals through the same
# reward_skins lane as every other won skin; the monthly top 3 creators win
# PrimeMeat AND the "supernova" design (owner order 2026-08-18: the podium
# skin is Supernova on both boards, and the pink glitter is Battle Pass
# only). All payouts are claim-gated (exactly-once across
# restarts); a paused or suspended creator earns nothing while held.
# =============================================================================
from fastapi import WebSocket, WebSocketDisconnect
import creator_program as cp_mod

# Monthly PrimeMeat prizes for the creator board (top 3 of each closed month).
CP_MONTHLY_TOP_PRIZES = [1_000_000, 500_000, 250_000]

# Owner order 2026-08-17 put the pink glitter (`constelacion`) on creator
# places 1/2/3. Owner order 2026-08-18 — "supernova for 123 place in
# leaderboard and constelacion for battlepass only" — REPLACES it with
# `supernova`: "battlepass only" is an exclusivity claim, and a podium that
# kept paying constelacion would be a second way to win it, so the two halves
# of that sentence are one change. The podium keeps a skin either way —
# emptying it would take back a prize he added the day before — and the
# PrimeMeat ladder (CP_MONTHLY_TOP_PRIZES) is untouched.
CP_PRIZE_SKIN_BY_RANK = {1: "supernova", 2: "supernova", 3: "supernova"}

# Anti-abuse: this many REWARDED referrals inside one hour auto-pauses the
# creator for 24h and raises an admin alert. The pause is a real gate (see
# _cp_creator_holds), not just a flag.
CP_BURST_LIMIT = 5
CP_BURST_WINDOW_HOURS = 1
CP_PAUSE_HOURS = 24

# WS hub hard cap — beyond this, new sockets get the snapshot then close.
CP_WS_MAX_CLIENTS = 500


def _cp_validate_prize_config() -> None:
    """Refuse to IMPORT on a prize or exclusive pointing at a design that does
    not exist (same shape as leaderboards._validate_prize_skins: a typo would
    otherwise sit silent until a month closes and then hand champions
    nothing)."""
    for rank, gid in CP_PRIZE_SKIN_BY_RANK.items():
        if rank not in (1, 2, 3):
            raise RuntimeError(f"[cp] prize skin at rank {rank} has no prize rank")
        if gid not in glitch_catalog.GLITCH_BY_ID:
            raise RuntimeError(f"[cp] prize skin {gid!r} is not in the glitch catalog")
    if cp_mod.DEFAULT_SKIN.get("glitch_id") not in glitch_catalog.GLITCH_BY_ID:
        raise RuntimeError("[cp] exclusive skin id is not in the glitch catalog")


_cp_validate_prize_config()


def _cp_skin_card(gid: str, extra: dict = None) -> dict:
    """Name + colour proximity card for a catalog design (never a picture)."""
    g = glitch_catalog.GLITCH_BY_ID.get(gid)
    if not g:
        return {"glitch_id": gid, "name": gid, "subtitle": "", "accent_hex": "#7CA842",
                "proximity": [], "rarity": glitch_catalog.GLITCH_RARITY, "image": "", **(extra or {})}
    prox = glitch_catalog.design_proximity(g)
    return {"glitch_id": gid, "name": g["name"], "subtitle": g.get("subtitle") or "",
            "accent_hex": g.get("accent_hex"), "proximity": prox["strip"],
            "rarity": glitch_catalog.GLITCH_RARITY, "image": "", **(extra or {})}


def _cp_prize_skin_cards() -> dict:
    """rank -> prize skin card for the creator leaderboard podium."""
    return {str(r): _cp_skin_card(gid, {"uses_per_win": GLITCH_USES_PER_WIN})
            for r, gid in CP_PRIZE_SKIN_BY_RANK.items()}


async def _cp_user_or_none(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Optional-auth dependency: a valid bearer resolves the user, anything
    else resolves None (public endpoints that enrich when signed in)."""
    if not creds:
        return None
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
        user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
        if user:
            banned, _row = await webban.check(user.get("steam_id"))
            if banned:
                return None
        return user
    except Exception:
        return None


async def _cp_ensure_indexes():
    try:
        await db.creators.create_index("code", unique=True)
        await db.creators.create_index("user_id", unique=True)
        # OWNER ORDER 2026-08-18: "users should support anyone with the code but
        # only one time". The old rule was a single-field UNIQUE index, i.e. ONE
        # code per player for life; the new rule is the PAIR.
        #
        # ORDER IS THE SAFE DIRECTION, NOT A DETAIL: the compound index is created
        # FIRST, so uniqueness is never absent for even a moment, and only then is
        # the stricter legacy index dropped. Doing it the other way opens a window
        # in which two racing applies could both write the same pair, and a
        # duplicate pair would then make the compound index impossible to build.
        # `referred_user_id` alone is still served by this index's PREFIX, so no
        # separate index is needed for the queries that ask by player.
        await db.referrals.create_index([("referred_user_id", 1), ("creator_id", 1)],
                                        unique=True, name="referred_creator_unique")
        try:
            await db.referrals.drop_index("referred_user_id_1")
            logger.info("[cp] dropped the legacy one-code-per-player index")
        except Exception:
            pass  # already dropped, or a fresh install that never had it
        await db.referrals.create_index("creator_id")
        await db.referrals.create_index("month")
        await db.referrals.create_index("status")
        await db.creator_notifications.create_index("creator_id")
        await db.hall_of_fame.create_index("month", unique=True)
        await db.creator_alerts.create_index("creator_id")
        await db.creator_alerts.create_index("created_at")
    except Exception as e:
        logger.warning(f"[cp] creator indexes: {e}")
    try:
        await _cp_backfill_welcome_claims_once()
    except Exception as e:
        logger.warning(f"[cp] welcome backfill: {e}")


async def _cp_backfill_welcome_claims_once():
    """Mark every player who ALREADY received a welcome bonus, once.

    ★ WITHOUT THIS THE OPEN-UP HANDS OUT A SECOND WELCOME BONUS. Every player
    referred under the old one-code rule was paid, but nothing recorded that on
    the PLAYER - the referral row was the only evidence, and it was unique per
    player so it never had to be. The moment a second code becomes possible,
    those players would claim an unclaimed `cp_welcome_paid` and be paid again.
    The backfill reads the payment history that already exists and writes the
    claim they should have had.

    Idempotent twice over: the update only touches users missing the flag, and a
    settings flag stops it re-running after the first boot."""
    settings = await _cp_get_settings()        # guarantees the doc exists
    if settings.get("welcome_backfill_done"):
        return 0
    uids = await db.referrals.distinct("referred_user_id",
                                       {"status": cp_mod.STATUS_REWARDED})
    n = 0
    if uids:
        res = await db.users.update_many(
            {"id": {"$in": list(uids)}, "cp_welcome_paid": {"$ne": True}},
            {"$set": {"cp_welcome_paid": True, "cp_welcome_paid_at": now_iso(),
                      "cp_welcome_paid_source": "backfill_20260818"}})
        n = int(res.modified_count or 0)
    await db.creator_settings.update_one(
        {"id": "settings"}, {"$set": {"welcome_backfill_done": True,
                                      "welcome_backfill_at": now_iso(),
                                      "welcome_backfill_count": n}})
    logger.info("[cp] welcome-bonus backfill: %d player(s) marked already paid", n)
    return n


def _cp_settings_defaults(doc: dict) -> dict:
    """Fill keys added AFTER this owner's settings doc was written.

    ★ A KNOB NOBODY CAN READ IS HALF A KNOB. Every decision path already falls
    back to the module default, so behaviour was never in doubt — but the admin
    settings surface reads this document DIRECTLY, and on an owner installed
    before 2026-08-18 it printed nothing at all where a live money knob is.
    Filled on the way OUT and never written back: a read must not write."""
    if not isinstance(doc, dict):
        return doc
    doc.setdefault("player_reward_once", cp_mod.DEFAULT_PLAYER_REWARD_ONCE)
    return doc


async def _cp_get_settings() -> dict:
    doc = await db.creator_settings.find_one({"id": "settings"}, {"_id": 0})
    if not doc:
        # FIRST BOOT ADOPTS THE PREVIOUS MONTH AS ALREADY CLOSED. Without this,
        # a mid-month deploy would "close" a month the program never ran and
        # write an empty Hall of Fame row for it (same adoption rule the season
        # leaderboard shipped with: history is never paid).
        now = datetime.now(timezone.utc)
        y, m = now.year, now.month
        prev = f"{y - 1:04d}-12" if m == 1 else f"{y:04d}-{m - 1:02d}"
        doc = {
            "id": "settings",
            "creator_reward":    cp_mod.DEFAULT_CREATOR_REWARD,
            "player_multiplier": cp_mod.DEFAULT_PLAYER_MULTIPLIER,
            "skin_target":       cp_mod.DEFAULT_SKIN_TARGET,
            "skin":              dict(cp_mod.DEFAULT_SKIN),
            "min_playtime_minutes": cp_mod.DEFAULT_MIN_PLAYTIME_MINUTES,
            "player_reward_once":   cp_mod.DEFAULT_PLAYER_REWARD_ONCE,
            "last_closed_month": prev,
            "updated_at":        now_iso(),
        }
        try:
            await db.creator_settings.insert_one(dict(doc))
        except Exception:
            fresh = await db.creator_settings.find_one({"id": "settings"}, {"_id": 0})
            if fresh:
                return _cp_settings_defaults(fresh)
    return _cp_settings_defaults(doc)


class CreatorHub:
    """WebSocket hub: pushes per-creator updates + broadcasts the leaderboard."""
    def __init__(self):
        self.clients: dict = {}   # ws -> user_id (None = anonymous viewer)
        self.dirty_leaderboard: bool = False
        self._pumping = False

    async def add(self, ws, user_id):
        self.clients[ws] = user_id

    async def remove(self, ws):
        self.clients.pop(ws, None)

    def mark_leaderboard_dirty(self):
        self.dirty_leaderboard = True

    async def push_to_user(self, user_id: str, payload: dict):
        dead = []
        for ws, uid in list(self.clients.items()):
            if uid == user_id:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)
        for ws in dead:
            self.clients.pop(ws, None)

    async def broadcast_leaderboard(self):
        if not self.clients:
            self.dirty_leaderboard = False
            return
        top_all = await _cp_leaderboard_snapshot(scope="all", limit=30)
        top_month = await _cp_leaderboard_snapshot(scope="month", limit=30)
        payload = {"type": "creator_leaderboard", "ts": now_iso(),
                   "all_time": top_all, "monthly": top_month,
                   "prize_skins": _cp_prize_skin_cards(),
                   "monthly_prizes": CP_MONTHLY_TOP_PRIZES}
        dead = []
        for ws in list(self.clients.keys()):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.pop(ws, None)
        self.dirty_leaderboard = False


creator_hub = CreatorHub()


async def _cp_broadcast_leaderboard_soon():
    creator_hub.mark_leaderboard_dirty()
    if creator_hub._pumping:
        return
    creator_hub._pumping = True

    async def _pump():
        try:
            await asyncio.sleep(0.5)
            if creator_hub.dirty_leaderboard:
                await creator_hub.broadcast_leaderboard()
        except Exception as e:
            logger.warning(f"[cp] leaderboard pump: {e}")
        finally:
            creator_hub._pumping = False

    asyncio.create_task(_pump())


async def _cp_notify(creator_id: str, ntype: str, title: str, message: str, meta: dict = None):
    doc = {"id": new_id(), "creator_id": creator_id, "type": ntype,
           "title": title, "message": message, "meta": meta or {},
           "read": False, "created_at": now_iso()}
    await db.creator_notifications.insert_one(dict(doc))
    doc.pop("_id", None)
    creator = await db.creators.find_one({"id": creator_id}, {"user_id": 1})
    if creator:
        await creator_hub.push_to_user(creator["user_id"], {"type": "creator_notification", "notification": doc})


async def _cp_leaderboard_snapshot(scope: str = "all", limit: int = 30):
    sort_field = "total_referrals" if scope == "all" else "monthly_referrals"
    cursor = db.creators.find(
        {"status": {"$ne": cp_mod.CREATOR_SUSPENDED}, sort_field: {"$gt": 0}},
        {"_id": 0}
    ).sort(sort_field, -1).limit(limit)
    rows = await cursor.to_list(length=limit)
    if not rows:
        return []
    user_ids = [r["user_id"] for r in rows]
    users = {}
    async for u in db.users.find({"id": {"$in": user_ids}},
                                 {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1, "avatar_url": 1}):
        users[u["id"]] = u
    return [cp_mod.public_creator(r, users.get(r["user_id"], {"id": r["user_id"]}), rank=i + 1)
            for i, r in enumerate(rows)]


async def _cp_recompute_creator_rank(user_id: str):
    c = await db.creators.find_one({"user_id": user_id}, {"_id": 0})
    if not c or int(c.get("total_referrals", 0)) <= 0:
        return None
    ahead = await db.creators.count_documents({
        "status": {"$ne": cp_mod.CREATOR_SUSPENDED},
        "total_referrals": {"$gt": int(c.get("total_referrals", 0))},
    })
    return ahead + 1


async def _cp_next_position_info(creator: dict):
    total = int(creator.get("total_referrals", 0))
    ahead = await db.creators.find({"total_referrals": {"$gt": total},
                                    "status": {"$ne": cp_mod.CREATOR_SUSPENDED}},
                                   {"_id": 0}).sort("total_referrals", 1).limit(1).to_list(length=1)
    if not ahead:
        return None
    nxt = ahead[0]
    u = await db.users.find_one({"id": nxt["user_id"]},
                                {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1, "avatar_url": 1})
    return {"creator": cp_mod.public_creator(nxt, u or {"id": nxt["user_id"]}),
            "gap": int(nxt["total_referrals"]) - total}


def _cp_paused_active(creator: dict) -> bool:
    """True while an anti-abuse pause is CURRENT (expired stamps read unpaused)."""
    pu = (creator or {}).get("paused_until")
    if not pu:
        return False
    try:
        t = datetime.fromisoformat(str(pu).replace("Z", "+00:00"))
        return t > datetime.now(timezone.utc)
    except Exception:
        return True  # unreadable stamp: fail closed until an admin clears it


def _cp_creator_holds(creator: dict) -> bool:
    """A held creator earns nothing: suspended, or inside an active pause."""
    if not creator:
        return True
    if (creator.get("status") or cp_mod.CREATOR_ACTIVE) == cp_mod.CREATOR_SUSPENDED:
        return True
    return _cp_paused_active(creator)

# Island presence credit: each sweep pass that SEES the referred player on the
# live roster (players_positions.json, freshness-gated — a stale file earns
# nothing) adds this many minutes to the REFERRAL doc. Sampling can only
# UNDERCOUNT (loop lag or a missed window drops credit, never invents it).
CP_SWEEP_MINUTES = 5
CP_ROSTER_FRESH_S = 120


def _cp_effective_minutes(user: dict, referral: dict | None) -> int:
    """Minutes played, best of BOTH lanes: the browser-driven passive counter
    (users.playtime_minutes — only accrues with the site open) and the
    island-presence counter sampled onto the referral by the sweep. MAX, not
    sum — both lanes measure the same played time, so adding them would
    double-count a player both lanes can see."""
    web = int((user or {}).get("playtime_minutes") or 0)
    island = int((referral or {}).get("play_minutes") or 0)
    return max(web, island)


def _cp_user_qualifies(user: dict, settings: dict) -> bool:
    """The owner's rule is "joins our server": a referral only pays once the
    referred account has a REAL linked Steam ID and has actually played on the
    island (playtime_minutes is fed exclusively by the passive telemetry
    drain, so it cannot be farmed from a browser)."""
    if not cp_mod.user_has_real_steam(user):
        return False
    need = int(settings.get("min_playtime_minutes", cp_mod.DEFAULT_MIN_PLAYTIME_MINUTES))
    return int((user or {}).get("playtime_minutes") or 0) >= max(0, need)


async def _cp_dashboard_payload(user_id: str):
    c = await db.creators.find_one({"user_id": user_id}, {"_id": 0})
    if not c:
        return None
    u = await db.users.find_one({"id": user_id},
                                {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1, "avatar_url": 1})
    rank = await _cp_recompute_creator_rank(user_id)
    settings = await _cp_get_settings()
    pub = cp_mod.public_creator(c, u, rank=rank)
    pub["paused"] = _cp_paused_active(c)
    monthly_rank = None
    if int(c.get("monthly_referrals", 0)) > 0:
        ahead = await db.creators.count_documents({
            "status": {"$ne": cp_mod.CREATOR_SUSPENDED},
            "monthly_referrals": {"$gt": int(c.get("monthly_referrals", 0))},
        })
        monthly_rank = ahead + 1
    nxt = await _cp_next_position_info(c)
    recent_refs = await db.referrals.find(
        {"creator_id": c["id"], "status": {"$in": [cp_mod.STATUS_VALIDATED, cp_mod.STATUS_REWARDED]}},
        {"_id": 0}
    ).sort("rewarded_at", -1).limit(8).to_list(length=8)
    ref_uids = list({r.get("referred_user_id") for r in recent_refs if r.get("referred_user_id")})
    ref_users = {}
    if ref_uids:
        async for ru in db.users.find({"id": {"$in": ref_uids}},
                                      {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1}):
            ref_users[ru["id"]] = ru
    recent = [cp_mod.public_referral(r, ref_users.get(r.get("referred_user_id"), {})) for r in recent_refs]
    skin_target = int(settings.get("skin_target", cp_mod.DEFAULT_SKIN_TARGET))
    total_refs = int(c.get("total_referrals", 0))
    reached = list(c.get("stages_reached") or [])
    ms_status = cp_mod.milestones_status(total_refs, reached)
    next_ms = None
    for m in cp_mod.MILESTONES:
        if total_refs < m["threshold"]:
            next_ms = {"key": m["key"], "title": m["title"], "medal": m["medal"], "color": m["color"],
                       "threshold": m["threshold"], "bonus": m["bonus"],
                       "remaining": m["threshold"] - total_refs}
            break
    month = cp_mod.month_id()
    visits_month = int((c.get("code_visits_month") or {}).get(month, 0))
    visits_total = int(c.get("code_visits_total", 0))
    conversion_rate = round(min(100.0, (total_refs / max(1, visits_total)) * 100.0), 1) if visits_total else 0.0
    skin_meta = settings.get("skin") or dict(cp_mod.DEFAULT_SKIN)
    skin_card = _cp_skin_card(skin_meta.get("glitch_id") or cp_mod.DEFAULT_SKIN["glitch_id"])
    return {
        "creator":      pub,
        "monthly_rank": monthly_rank,
        "next_position": nxt,
        "recent":       recent,
        "milestones":   {"stages": ms_status, "next": next_ms},
        "conversion": {
            "visits_month":  visits_month,
            "visits_total":  visits_total,
            "applies_month": int(c.get("monthly_referrals", 0)),
            "applies_total": total_refs,
            "rate_pct":      conversion_rate,
        },
        "settings": {
            "creator_reward": int(settings.get("creator_reward", cp_mod.DEFAULT_CREATOR_REWARD)),
            "player_reward":  int(int(settings.get("creator_reward", cp_mod.DEFAULT_CREATOR_REWARD))
                                  * float(settings.get("player_multiplier", cp_mod.DEFAULT_PLAYER_MULTIPLIER))),
            "min_playtime_minutes": int(settings.get("min_playtime_minutes", cp_mod.DEFAULT_MIN_PLAYTIME_MINUTES)),
            "skin_target":    skin_target,
            "skin":           {**skin_meta, "card": skin_card},
        },
        "skin_progress": {
            "current":   total_refs,
            "target":    skin_target,
            "remaining": max(0, skin_target - total_refs),
            "unlocked":  bool(c.get("exclusive_skin_unlocked")),
            "card":      skin_card,
        },
        "prizes": {"monthly_top": CP_MONTHLY_TOP_PRIZES, "prize_skins": _cp_prize_skin_cards()},
    }


async def _cp_validate_and_reward(referral_id: str):
    """Idempotently transition PENDING/VALIDATED -> REWARDED and pay both
    sides. Claim-gated on the referral status flip, so a concurrent second
    caller pays nobody. A held creator (suspended / active pause) earns
    nothing and the referral WAITS (stays PENDING for the sweep)."""
    r = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not r or r.get("status") not in (cp_mod.STATUS_PENDING, cp_mod.STATUS_VALIDATED):
        return None
    creator = await db.creators.find_one({"id": r["creator_id"]}, {"_id": 0})
    if not creator or _cp_creator_holds(creator):
        return None
    settings = await _cp_get_settings()
    creator_reward = int(settings.get("creator_reward", cp_mod.DEFAULT_CREATOR_REWARD))
    mult = float(settings.get("player_multiplier", cp_mod.DEFAULT_PLAYER_MULTIPLIER))
    player_reward = int(creator_reward * mult)

    # `player_reward_amount` is deliberately NOT written here: whether the player
    # is paid is decided by a claim further down, and a number written before the
    # claim would be a promise this row might not keep.
    upd = await db.referrals.update_one(
        {"id": referral_id, "status": {"$in": [cp_mod.STATUS_PENDING, cp_mod.STATUS_VALIDATED]}},
        {"$set": {"status": cp_mod.STATUS_REWARDED, "validated_at": r.get("validated_at") or now_iso(),
                  "rewarded_at": now_iso(), "reward_amount": creator_reward}},
    )
    if upd.modified_count == 0:
        return None

    prev_total = int(creator.get("total_referrals", 0))
    await db.users.update_one({"id": creator["user_id"]}, {"$inc": {"coins": creator_reward}})
    await add_transaction(creator["user_id"], "normal", creator_reward, "creator_reward",
                          f"Programa de Creadores · referido validado ({referral_id[:8]})")
    month = cp_mod.month_id()
    update = {"$inc": {"total_referrals": 1, "total_prime_meat_earned": creator_reward},
              "$set": {"updated_at": now_iso()}}
    if creator.get("current_month") != month:
        update["$set"].update({"current_month": month, "monthly_referrals": 1,
                               "monthly_prime_meat_earned": creator_reward})
    else:
        update["$inc"]["monthly_referrals"] = 1
        update["$inc"]["monthly_prime_meat_earned"] = creator_reward
    await db.creators.update_one({"id": creator["id"]}, update)

    fresh_creator = await db.creators.find_one({"id": creator["id"]}, {"_id": 0})
    new_total = int((fresh_creator or {}).get("total_referrals", prev_total + 1))

    # Exclusive skin at target — CLAIM-GATED flag flip, then a REAL grant
    # through the same reward_skins lane as crates/BP/leaderboard prizes.
    target = int(settings.get("skin_target", cp_mod.DEFAULT_SKIN_TARGET))
    if new_total >= target:
        claimed = await db.creators.find_one_and_update(
            {"id": creator["id"], "exclusive_skin_unlocked": {"$ne": True}},
            {"$set": {"exclusive_skin_unlocked": True, "skin_unlocked_at": now_iso()}},
        )
        if claimed:
            gid = (settings.get("skin") or {}).get("glitch_id") or cp_mod.DEFAULT_SKIN["glitch_id"]
            ok = await _grant_prize_skin(creator["user_id"], gid,
                                         "Programa de Creadores — skin exclusiva")
            if not ok:
                logger.error("[cp] exclusive skin %r failed to grant for creator %s", gid, creator["id"])
            await _cp_notify(creator["id"], "SKIN_UNLOCKED", "¡Skin Exclusiva Desbloqueada!",
                             f"¡Alcanzaste {target} referidos validados! La skin ya está en tu inventario de recompensas.",
                             meta={"glitch_id": gid, "target": target})

    # Milestones — the $addToSet filter IS the claim: two racing rewards can
    # both cross a threshold, only the one that lands the array insert pays.
    for m in cp_mod.newly_crossed_milestones(prev_total, new_total):
        claim = await db.creators.find_one_and_update(
            {"id": creator["id"], "stages_reached": {"$ne": m["key"]}},
            {"$addToSet": {"stages_reached": m["key"]},
             "$inc": {"total_prime_meat_earned": int(m["bonus"])}},
        )
        if not claim:
            continue
        bonus = int(m["bonus"])
        await db.users.update_one({"id": creator["user_id"]}, {"$inc": {"coins": bonus}})
        await add_transaction(creator["user_id"], "normal", bonus, "creator_milestone",
                              f"Programa de Creadores · hito {m['title']}")
        await _cp_notify(creator["id"], "MILESTONE",
                         f"{m['medal']} {m['title']} desbloqueado",
                         f"Superaste {m['threshold']} referidos · +{bonus:,} PrimeMeat",
                         meta={"amount": bonus, "milestone": m["key"], "threshold": m["threshold"]})

    await _cp_notify(creator["id"], "REWARD_RECEIVED", "Referido Recompensado",
                     f"+{creator_reward:,} PrimeMeat",
                     meta={"amount": creator_reward, "referral_id": referral_id})

    # Anti-abuse burst: pause is claim-gated on paused_until being absent so
    # racing rewards write exactly one alert.
    try:
        window_start = (datetime.now(timezone.utc) - timedelta(hours=CP_BURST_WINDOW_HOURS)).isoformat()
        burst = await db.referrals.count_documents({
            "creator_id": creator["id"], "status": cp_mod.STATUS_REWARDED,
            "rewarded_at": {"$gte": window_start},
        })
        if burst >= CP_BURST_LIMIT:
            pause_until = (datetime.now(timezone.utc) + timedelta(hours=CP_PAUSE_HOURS)).isoformat()
            # The claim admits: never paused, cleared, or an EXPIRED stamp
            # (ISO strings compare lexicographically) — an old pause must not
            # immunize a creator against ever being paused again.
            claimed = await db.creators.find_one_and_update(
                {"id": creator["id"],
                 "$or": [{"paused_until": {"$exists": False}}, {"paused_until": None},
                         {"paused_until": {"$lte": now_iso()}}]},
                {"$set": {"paused_until": pause_until,
                          "paused_reason": f"BURST_{burst}_REFS_{CP_BURST_WINDOW_HOURS}H"}},
            )
            if claimed:
                await db.creator_alerts.insert_one({
                    "id": new_id(), "creator_id": creator["id"], "user_id": creator["user_id"],
                    "code": creator.get("code"), "type": "BURST_DETECTED",
                    "burst_count": burst, "paused_until": pause_until,
                    "message": f"{burst} referidos recompensados en {CP_BURST_WINDOW_HOURS}h — creator auto-pausado {CP_PAUSE_HOURS}h",
                    "read": False, "created_at": now_iso(),
                })
                await _cp_notify(creator["id"], "MILESTONE", "Cuenta en revisión",
                                 f"Detectamos {burst} referidos en {CP_BURST_WINDOW_HOURS}h. Tu cuenta queda pausada {CP_PAUSE_HOURS}h mientras el staff revisa.")
                logger.warning("[cp] burst pause: creator=%s code=%s burst=%d",
                               creator["id"], creator.get("code"), burst)
    except Exception as e:
        logger.warning(f"[cp] anti-abuse check: {e}")

    payload = await _cp_dashboard_payload(creator["user_id"])
    if payload:
        # Same shape as GET /creator/dashboard: the page gates on is_creator, and a
        # push without it reads as "Todavía no sos Creator" for a real creator.
        await creator_hub.push_to_user(creator["user_id"],
                                       {"type": "creator_dashboard", "data": {"is_creator": True, **payload}})

    # ★★★★★ THE WELCOME BONUS IS ONCE PER PLAYER, AND THE CLAIM IS THE PROOF.
    # Since 2026-08-18 a player may support any number of creators, and the
    # creator is paid for every distinct player who supports them. The player's
    # own bonus is a JOINING bonus: the qualification behind it (linked Steam +
    # minutes played) belongs to the PLAYER, so once they qualify every further
    # code validates instantly and paying per code would mint the bonus once per
    # creator on the same ten minutes of play. `cp_welcome_paid` is claimed with
    # find_one_and_update, so two codes validating in the same second cannot both
    # pay it. Admins can set `player_reward_once: false` to pay it every time.
    # The claim happens AFTER the referral status claim above on purpose: burning
    # a player's one bonus on a referral this call did not win would lose it.
    if bool(settings.get("player_reward_once", cp_mod.DEFAULT_PLAYER_REWARD_ONCE)):
        won_welcome = await db.users.find_one_and_update(
            {"id": r["referred_user_id"], "cp_welcome_paid": {"$ne": True}},
            {"$set": {"cp_welcome_paid": True, "cp_welcome_paid_at": now_iso()}})
        if not won_welcome:
            player_reward = 0
    if player_reward > 0:
        await db.users.update_one({"id": r["referred_user_id"]}, {"$inc": {"coins": player_reward}})
        await add_transaction(r["referred_user_id"], "normal", player_reward, "creator_referral",
                              "Programa de Creadores · bono de bienvenida")
    await db.referrals.update_one({"id": referral_id},
                                  {"$set": {"player_reward_amount": player_reward}})

    await _cp_broadcast_leaderboard_soon()
    logger.info("[cp] referral rewarded id=%s creator=%s code=%s creator_pm=%d player_pm=%d total=%d",
                referral_id, creator["id"], creator.get("code"), creator_reward, player_reward, new_total)
    return {"referral_id": referral_id, "creator_reward": creator_reward, "player_reward": player_reward}


async def _cp_try_validate_for_user(user: dict):
    """From user context: pay EVERY pending code this player holds that is now
    eligible (by either minutes lane).

    ★ Since 2026-08-18 a player can hold several. Reading only the first would
    have left every code after it waiting for the 5-minute sweep instead of
    landing on the press, which reads to the player as "the second one is
    broken". One bad row never stops the rest."""
    if not user or not cp_mod.user_has_real_steam(user):
        return None
    rows = await db.referrals.find(
        {"referred_user_id": user["id"], "status": cp_mod.STATUS_PENDING},
        {"_id": 0, "id": 1, "play_minutes": 1}).sort("created_at", 1).to_list(length=100)
    if not rows:
        return None
    settings = await _cp_get_settings()
    need = int(settings.get("min_playtime_minutes", cp_mod.DEFAULT_MIN_PLAYTIME_MINUTES))
    first = None
    for row in rows:
        if _cp_effective_minutes(user, row) < max(0, need):
            continue
        try:
            got = await _cp_validate_and_reward(row["id"])
        except Exception as e:
            logger.warning(f"[cp] validate-for-user {row['id']}: {e}")
            continue
        if got and first is None:
            first = got
    return first


async def _cp_sweep_pending_once():
    """One sweep pass: credit island presence onto PENDING referrals, then
    validate every referral whose referred player has now REALLY played
    enough (by either lane — see _cp_effective_minutes). The island read is
    freshness-gated: a dead/stale roster file credits nobody (positive
    signal only, the same rule the quest tracker uses). Bounded batch; one
    bad row never kills the pass."""
    settings = await _cp_get_settings()
    pend = await db.referrals.find({"status": cp_mod.STATUS_PENDING},
                                   {"_id": 0, "id": 1, "referred_user_id": 1, "play_minutes": 1})                              .sort("created_at", 1).limit(200).to_list(length=200)
    if not pend:
        return 0
    uids = list({p["referred_user_id"] for p in pend})
    users = {}
    async for u in db.users.find({"id": {"$in": uids}},
                                 {"_id": 0, "id": 1, "steam_id": 1, "playtime_minutes": 1}):
        users[u["id"]] = u
    try:
        roster = game_ipc.read_players_positions_fresh(CP_ROSTER_FRESH_S) or {}
    except Exception:
        roster = {}
    need = int(settings.get("min_playtime_minutes", cp_mod.DEFAULT_MIN_PLAYTIME_MINUTES))
    rewarded = 0
    for p in pend:
        u = users.get(p["referred_user_id"])
        if not u or not cp_mod.user_has_real_steam(u):
            continue
        island = int(p.get("play_minutes") or 0)
        sid = str(u.get("steam_id") or "")
        if roster and sid and sid in roster:
            island += CP_SWEEP_MINUTES
            await db.referrals.update_one({"id": p["id"]},
                                          {"$set": {"play_minutes": island,
                                                    "last_seen_ingame_at": now_iso()}})
        if max(int(u.get("playtime_minutes") or 0), island) >= max(0, need):
            try:
                if await _cp_validate_and_reward(p["id"]):
                    rewarded += 1
            except Exception as e:
                logger.warning(f"[cp] sweep reward {p['id']}: {e}")
    return rewarded


async def creator_pending_sweep_loop():
    while True:
        try:
            n = await _cp_sweep_pending_once()
            if n:
                logger.info("[cp] sweep validated %d referral(s)", n)
        except Exception as e:
            logger.warning(f"[cp] pending sweep: {e}")
        await asyncio.sleep(300)

# ─── Creator Program endpoints ──────────────────────────────────────────────

class CpApplyCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


@api_router.post("/creator/apply-code")
async def creator_apply_code(body: CpApplyCodeIn, user=Depends(get_current_user)):
    code = cp_mod.normalize_code(body.code)
    if not cp_mod.is_valid_code(code):
        raise HTTPException(status_code=400, detail="Código inválido")
    creator = await db.creators.find_one({"code": code, "status": {"$ne": cp_mod.CREATOR_SUSPENDED}})
    if not creator:
        raise HTTPException(status_code=404, detail="CODE_NOT_FOUND")
    if creator["user_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="SELF_REFERRAL")
    if await db.creators.find_one({"user_id": user["id"]}):
        # A creator cannot be referred either — closes the two-account loop of
        # two creators pointing codes at each other from the same house.
        raise HTTPException(status_code=400, detail="CREATORS_CANT_BE_REFERRED")
    # ★ OWNER ORDER 2026-08-18: "users should support anyone with the code but
    #   only one time" — the gate is the PAIR now, not the player. The lookup
    #   also moved BELOW the code lookup, which fixes a real wrong answer: an
    #   already-referred player typing a code that does not exist used to be
    #   told "already used" instead of "no such code".
    # ★ The error id is deliberately UNCHANGED. A browser that has not reloaded
    #   is still running the previous bundle and matches on this exact string;
    #   only its MEANING narrowed, from "you already used a code" to "you
    #   already used THIS creator's code".
    existing = await db.referrals.find_one(
        {"referred_user_id": user["id"], "creator_id": creator["id"]})
    if existing:
        raise HTTPException(status_code=409, detail="REFERRAL_ALREADY_USED")
    rid = new_id()
    try:
        await db.referrals.insert_one({
            "id": rid, "creator_id": creator["id"], "referred_user_id": user["id"],
            "code": code, "status": cp_mod.STATUS_PENDING,
            "month": cp_mod.month_id(), "created_at": now_iso(),
        })
    except Exception:
        raise HTTPException(status_code=409, detail="REFERRAL_ALREADY_USED")
    settings = await _cp_get_settings()
    rewarded = None
    if _cp_user_qualifies(user, settings):
        rewarded = await _cp_validate_and_reward(rid)
    else:
        need = int(settings.get("min_playtime_minutes", cp_mod.DEFAULT_MIN_PLAYTIME_MINUTES))
        await _cp_notify(creator["id"], "NEW_REFERRAL", "Nuevo referido pendiente",
                         f"{user.get('persona_name', 'Un jugador')} usó tu código. Se valida cuando juegue en el servidor.")
        return {"success": True, "creator_code": code,
                "creator_name": creator.get("display_name") or creator.get("code"),
                "status": cp_mod.STATUS_PENDING,
                "pending_reason": f"Entrá al servidor y jugá al menos {need} minutos para validar el código.",
                "rewards": None}
    return {"success": True, "creator_code": code,
            "creator_name": creator.get("display_name") or creator.get("code"),
            "status": cp_mod.STATUS_REWARDED if rewarded else cp_mod.STATUS_PENDING,
            "rewards": rewarded}


@api_router.get("/creator/my-referral")
async def creator_my_referral(user=Depends(get_current_user)):
    """EVERY creator this player supports (owner order 2026-08-18: any number of
    creators, each exactly once).

    ★ THE OLD SINGLE-REFERRAL SHAPE IS KEPT AT THE TOP LEVEL, filled from the
    NEWEST row, and the list rides alongside in `referrals`. A browser that has
    not reloaded is still running the previous bundle and reads exactly those
    top-level keys — returning only a list would blank that card instead of
    showing the player something true. The new page reads `referrals`.
    """
    rows = await db.referrals.find({"referred_user_id": user["id"]}, {"_id": 0}) \
                             .sort("created_at", -1).to_list(length=200)
    if not rows:
        return {"used": False, "count": 0, "referrals": []}

    settings = await _cp_get_settings()
    need = int(settings.get("min_playtime_minutes", cp_mod.DEFAULT_MIN_PLAYTIME_MINUTES))
    full_player_reward = int(int(settings.get("creator_reward", cp_mod.DEFAULT_CREATOR_REWARD))
                             * float(settings.get("player_multiplier", cp_mod.DEFAULT_PLAYER_MULTIPLIER)))
    once = bool(settings.get("player_reward_once", cp_mod.DEFAULT_PLAYER_REWARD_ONCE))
    # Two oracles for "already had the welcome bonus", because the claim flag was
    # only introduced with this change: the flag itself, and the payment history
    # that predates it. Reading only the flag would promise a bonus that the
    # backfill (or a paid row) has already spent.
    welcome_used = bool(user.get("cp_welcome_paid")) or any(
        int(rw_.get("player_reward_amount") or 0) > 0 for rw_ in rows)

    cids = list({rw_.get("creator_id") for rw_ in rows if rw_.get("creator_id")})
    creators = {c["id"]: c for c in
                await db.creators.find({"id": {"$in": cids}}, {"_id": 0}).to_list(length=200)}
    cuids = list({c.get("user_id") for c in creators.values() if c.get("user_id")})
    cusers = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": cuids}},
        {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1, "avatar_url": 1}).to_list(length=200)}

    items = []
    for rw_ in rows:
        c = creators.get(rw_.get("creator_id"))
        item = {
            "id": rw_.get("id"), "code": rw_.get("code"), "status": rw_.get("status"),
            "reward_amount": (int(rw_.get("player_reward_amount") or 0)
                              if rw_.get("status") == cp_mod.STATUS_REWARDED else None),
            "created_at": rw_.get("created_at"), "validated_at": rw_.get("validated_at"),
            "creator": cp_mod.public_creator(c, cusers.get((c or {}).get("user_id"))) if c else None,
        }
        if rw_.get("status") == cp_mod.STATUS_PENDING:
            # Tell the player the TRUE remaining requirement, never a stale one.
            # On this site every account signs in WITH Steam, so the real gate is
            # almost always play time; the Steam sentence survives only for the
            # rare account that genuinely has no real Steam id.
            have = _cp_effective_minutes(user, rw_)
            if not cp_mod.user_has_real_steam(user):
                item["pending_reason"] = "Iniciá sesión con Steam para validar el código."
            else:
                item["pending_reason"] = (
                    f"Entrá al servidor y jugá al menos {need} minutos para cobrar (llevás {min(have, need)})."
                )
            item["pending_need_minutes"] = need
            item["pending_have_minutes"] = have
            # 0 once the welcome bonus is spent — the creator still earns from
            # this code, so the card must not promise the player money twice.
            item["player_reward_next"] = 0 if (once and welcome_used) else full_player_reward
        items.append(item)

    out = dict(items[0])
    out.update({"used": True, "count": len(items), "referrals": items,
                "welcome_bonus_used": welcome_used, "player_reward_once": once,
                "welcome_bonus_amount": full_player_reward})
    return out


@api_router.get("/creator/dashboard")
async def creator_dashboard(user=Depends(get_current_user)):
    payload = await _cp_dashboard_payload(user["id"])
    if not payload:
        return {"is_creator": False}
    return {"is_creator": True, **payload}


@api_router.get("/creator/referrals")
async def creator_referrals(user=Depends(get_current_user)):
    creator = await db.creators.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
    if not creator:
        raise HTTPException(status_code=403, detail="NOT_A_CREATOR")
    rows = await db.referrals.find({"creator_id": creator["id"]}, {"_id": 0}) \
                             .sort("created_at", -1).limit(200).to_list(length=200)
    user_ids = list({r["referred_user_id"] for r in rows})
    users = {}
    if user_ids:
        async for u in db.users.find({"id": {"$in": user_ids}},
                                     {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1}):
            users[u["id"]] = u
    return {"referrals": [cp_mod.public_referral(r, users.get(r["referred_user_id"], {})) for r in rows]}


@api_router.get("/creator/notifications")
async def creator_notifications_list(user=Depends(get_current_user)):
    creator = await db.creators.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
    if not creator:
        return {"notifications": []}
    rows = await db.creator_notifications.find({"creator_id": creator["id"]}, {"_id": 0}) \
                                         .sort("created_at", -1).limit(30).to_list(length=30)
    return {"notifications": rows}


@api_router.post("/creator/notifications/mark-read")
async def creator_notifications_read(user=Depends(get_current_user)):
    creator = await db.creators.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
    if creator:
        await db.creator_notifications.update_many(
            {"creator_id": creator["id"], "read": False}, {"$set": {"read": True}})
    return {"success": True}


@api_router.get("/creator/leaderboard")
async def creator_leaderboard(scope: str = "all", user=Depends(_cp_user_or_none)):
    scope = "month" if scope == "month" else "all"
    board = await _cp_leaderboard_snapshot(scope=scope, limit=30)
    me = None
    if user:
        c = await db.creators.find_one({"user_id": user["id"]}, {"_id": 0})
        if c:
            u = await db.users.find_one({"id": user["id"]},
                                        {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1})
            field = "total_referrals" if scope == "all" else "monthly_referrals"
            if int(c.get(field, 0)) > 0:
                ahead = await db.creators.count_documents({
                    "status": {"$ne": cp_mod.CREATOR_SUSPENDED},
                    field: {"$gt": int(c.get(field, 0))},
                })
                me = cp_mod.public_creator(c, u, rank=ahead + 1)
    return {"scope": scope, "board": board, "me": me,
            "prize_skins": _cp_prize_skin_cards(),
            "monthly_prizes": CP_MONTHLY_TOP_PRIZES}


@api_router.get("/creator/public/{code}")
async def creator_public(code: str):
    code = cp_mod.normalize_code(code)
    if not cp_mod.is_valid_code(code):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    c = await db.creators.find_one({"code": code, "status": {"$ne": cp_mod.CREATOR_SUSPENDED}}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    u = await db.users.find_one({"id": c["user_id"]},
                                {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1, "avatar_url": 1})
    rank = await _cp_recompute_creator_rank(c["user_id"])
    settings = await _cp_get_settings()
    return {"creator": cp_mod.public_creator(c, u, rank=rank),
            "skin_target": int(settings.get("skin_target", cp_mod.DEFAULT_SKIN_TARGET))}


@api_router.get("/creator/program-stats")
async def creator_program_stats():
    month = cp_mod.month_id()
    cur = db.creators.aggregate([
        {"$match": {"status": {"$ne": cp_mod.CREATOR_SUSPENDED}, "is_demo": {"$ne": True}}},
        {"$group": {"_id": None,
                    "monthly_refs":    {"$sum": {"$ifNull": ["$monthly_referrals", 0]}},
                    "monthly_pm":      {"$sum": {"$ifNull": ["$monthly_prime_meat_earned", 0]}},
                    "total_refs":      {"$sum": {"$ifNull": ["$total_referrals", 0]}},
                    "total_pm":        {"$sum": {"$ifNull": ["$total_prime_meat_earned", 0]}},
                    "active_creators": {"$sum": 1}}},
    ])
    row = None
    async for r in cur:
        row = r
        break
    return {"month": month,
            "monthly_refs": int((row or {}).get("monthly_refs", 0)),
            "monthly_pm": int((row or {}).get("monthly_pm", 0)),
            "total_refs": int((row or {}).get("total_refs", 0)),
            "total_pm": int((row or {}).get("total_pm", 0)),
            "active_creators": int((row or {}).get("active_creators", 0))}


# Soft per-IP+code throttle for the unauthenticated visit counter: beyond the
# allowance inside the window the hit is silently NOT counted (the response
# never reveals the throttle, so it leaks nothing to a spammer).
_cp_visit_hits: dict = {}
_CP_VISIT_WINDOW_S = 600.0
_CP_VISIT_MAX_PER_WINDOW = 30


class CpTrackVisitIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


@api_router.post("/creator/track-visit")
async def creator_track_visit(body: CpTrackVisitIn, request: Request):
    code = cp_mod.normalize_code(body.code)
    if not cp_mod.is_valid_code(code):
        return {"ok": False}
    ip = (request.client.host if request.client else "?") or "?"
    now_s = time.time()
    if len(_cp_visit_hits) > 4096:  # bounded memory whatever the traffic
        _cp_visit_hits.clear()
    key = f"{ip}|{code}"
    count, start = _cp_visit_hits.get(key, (0, now_s))
    if now_s - start > _CP_VISIT_WINDOW_S:
        count, start = 0, now_s
    _cp_visit_hits[key] = (count + 1, start)
    if count + 1 > _CP_VISIT_MAX_PER_WINDOW:
        return {"ok": True}
    r = await db.creators.update_one(
        {"code": code, "status": {"$ne": cp_mod.CREATOR_SUSPENDED}},
        {"$inc": {"code_visits_total": 1, f"code_visits_month.{cp_mod.month_id()}": 1}})
    return {"ok": bool(r.matched_count)}


@api_router.get("/creator/hall-of-fame")
async def creator_hall_of_fame(limit: int = 12):
    limit = max(1, min(int(limit or 12), 60))
    rows = await db.hall_of_fame.find({}, {"_id": 0}).sort("month", -1).limit(limit).to_list(length=limit)
    return {"months": rows}


@api_router.get("/creator/timeseries")
async def creator_timeseries(days: int = 30, user=Depends(get_current_user)):
    days = max(1, min(int(days or 30), 90))
    c = await db.creators.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
    if not c:
        raise HTTPException(status_code=403, detail="NOT_A_CREATOR")
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days - 1)
    cursor = db.referrals.find(
        {"creator_id": c["id"],
         "status": {"$in": [cp_mod.STATUS_VALIDATED, cp_mod.STATUS_REWARDED]},
         "created_at": {"$gte": start.isoformat()}},
        {"_id": 0, "created_at": 1, "reward_amount": 1})
    buckets = {}
    async for r in cursor:
        try:
            d = datetime.fromisoformat(str(r.get("created_at")).replace("Z", "+00:00")).date().isoformat()
        except Exception:
            continue
        b = buckets.setdefault(d, {"date": d, "refs": 0, "pm": 0})
        b["refs"] += 1
        b["pm"] += int(r.get("reward_amount") or 0)
    out = []
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        out.append(buckets.get(d, {"date": d, "refs": 0, "pm": 0}))
    return {"days": out}

# ─── Creator Program: admin endpoints ───────────────────────────────────────

class CpCreatorCreateIn(BaseModel):
    user_id: Optional[str] = None
    steam_id: Optional[str] = None
    code: str = Field(min_length=1, max_length=32)
    display_name: Optional[str] = Field(default=None, max_length=48)


@api_router.post("/creator/admin/create")
async def creator_admin_create(body: CpCreatorCreateIn, admin=Depends(get_admin_user)):
    code = cp_mod.normalize_code(body.code)
    if not cp_mod.is_valid_code(code):
        raise HTTPException(status_code=400, detail="INVALID_CODE")
    target = None
    if body.steam_id:
        sid = str(body.steam_id).strip()
        if not re.fullmatch(r"\d{17}", sid):
            raise HTTPException(status_code=400, detail="INVALID_STEAM_ID")
        target = await db.users.find_one({"steam_id": sid}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="STEAM_USER_NOT_FOUND")
    elif body.user_id:
        target = await db.users.find_one({"id": body.user_id}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    else:
        raise HTTPException(status_code=400, detail="STEAM_ID_OR_USER_ID_REQUIRED")
    existing = await db.creators.find_one({"$or": [{"user_id": target["id"]}, {"code": code}]})
    if existing:
        raise HTTPException(status_code=409, detail="ALREADY_EXISTS")
    doc = {
        "id": new_id(), "user_id": target["id"], "code": code,
        "status": cp_mod.CREATOR_ACTIVE,
        "display_name": body.display_name or target.get("persona_name") or code,
        "total_referrals": 0, "monthly_referrals": 0,
        "total_prime_meat_earned": 0, "monthly_prime_meat_earned": 0,
        "exclusive_skin_unlocked": False, "stages_reached": [],
        "code_visits_total": 0, "code_visits_month": {},
        "current_month": cp_mod.month_id(),
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    try:
        await db.creators.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="ALREADY_EXISTS")
    doc.pop("_id", None)
    logger.info("[cp] creator created code=%s user=%s by admin=%s", code, target["id"], admin.get("id"))
    await _cp_broadcast_leaderboard_soon()
    return {"success": True, "creator": doc}


class CpCreatorUpdateIn(BaseModel):
    user_id: str
    code: Optional[str] = Field(default=None, max_length=32)
    status: Optional[str] = None
    display_name: Optional[str] = Field(default=None, max_length=48)


@api_router.post("/creator/admin/update")
async def creator_admin_update(body: CpCreatorUpdateIn, admin=Depends(get_admin_user)):
    c = await db.creators.find_one({"user_id": body.user_id})
    if not c:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    upd = {}
    if body.code:
        code = cp_mod.normalize_code(body.code)
        if not cp_mod.is_valid_code(code):
            raise HTTPException(status_code=400, detail="INVALID_CODE")
        clash = await db.creators.find_one({"code": code, "user_id": {"$ne": body.user_id}})
        if clash:
            raise HTTPException(status_code=409, detail="CODE_TAKEN")
        upd["code"] = code
    if body.status in (cp_mod.CREATOR_ACTIVE, cp_mod.CREATOR_SUSPENDED):
        upd["status"] = body.status
    if body.display_name is not None:
        upd["display_name"] = str(body.display_name)[:48]
    if not upd:
        return {"success": True, "unchanged": True}
    upd["updated_at"] = now_iso()
    await db.creators.update_one({"id": c["id"]}, {"$set": upd})
    logger.info("[cp] creator updated user=%s fields=%s by admin=%s",
                body.user_id, sorted(upd.keys()), admin.get("id"))
    await _cp_broadcast_leaderboard_soon()
    return {"success": True}


class CpSettingsIn(BaseModel):
    creator_reward: Optional[int] = Field(default=None, ge=1, le=100_000_000)
    player_multiplier: Optional[float] = Field(default=None, gt=0, le=1)
    skin_target: Optional[int] = Field(default=None, ge=1, le=100_000)
    min_playtime_minutes: Optional[int] = Field(default=None, ge=0, le=10_000)
    # 2026-08-18: True = the player's welcome bonus is paid once per PLAYER
    # (their first validated code); False = once per code they apply.
    player_reward_once: Optional[bool] = None


@api_router.post("/creator/admin/settings")
async def creator_admin_settings(body: CpSettingsIn, admin=Depends(get_admin_user)):
    settings = await _cp_get_settings()
    upd = {}
    if body.creator_reward is not None:
        upd["creator_reward"] = int(body.creator_reward)
    if body.player_multiplier is not None:
        upd["player_multiplier"] = float(body.player_multiplier)
    if body.skin_target is not None:
        upd["skin_target"] = int(body.skin_target)
    if body.min_playtime_minutes is not None:
        upd["min_playtime_minutes"] = int(body.min_playtime_minutes)
    if body.player_reward_once is not None:
        upd["player_reward_once"] = bool(body.player_reward_once)
    if not upd:
        return {"success": True, "settings": settings}
    upd["updated_at"] = now_iso()
    await db.creator_settings.update_one({"id": "settings"}, {"$set": upd}, upsert=True)
    fresh = await _cp_get_settings()
    logger.info("[cp] settings updated fields=%s by admin=%s", sorted(upd.keys()), admin.get("id"))
    return {"success": True, "settings": fresh}


@api_router.get("/creator/admin/settings")
async def creator_admin_get_settings(admin=Depends(get_admin_user)):
    s = await _cp_get_settings()
    s["skin_card"] = _cp_skin_card((s.get("skin") or {}).get("glitch_id") or cp_mod.DEFAULT_SKIN["glitch_id"])
    s["prize_skins"] = _cp_prize_skin_cards()
    s["monthly_prizes"] = CP_MONTHLY_TOP_PRIZES
    return {"settings": s}


@api_router.get("/creator/admin/list")
async def creator_admin_list(admin=Depends(get_admin_user)):
    creators = await db.creators.find({}, {"_id": 0}).sort("total_referrals", -1).limit(200).to_list(length=200)
    user_ids = [c["user_id"] for c in creators]
    users = {}
    if user_ids:
        async for u in db.users.find({"id": {"$in": user_ids}},
                                     {"_id": 0, "id": 1, "persona_name": 1, "avatar": 1, "steam_id": 1}):
            users[u["id"]] = u
    out = []
    for c in creators:
        row = cp_mod.public_creator(c, users.get(c["user_id"], {}))
        row["paused"] = _cp_paused_active(c)
        row["steam_id"] = (users.get(c["user_id"]) or {}).get("steam_id")
        out.append(row)
    return {"creators": out}


@api_router.get("/creator/admin/alerts")
async def creator_admin_alerts(admin=Depends(get_admin_user)):
    rows = await db.creator_alerts.find({}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(length=100)
    return {"alerts": rows}


class CpAlertActionIn(BaseModel):
    alert_id: str
    action: str


@api_router.post("/creator/admin/alerts/action")
async def creator_admin_alerts_action(body: CpAlertActionIn, admin=Depends(get_admin_user)):
    a = await db.creator_alerts.find_one({"id": body.alert_id})
    if not a:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if body.action == "clear":
        await db.creator_alerts.update_one({"id": body.alert_id}, {"$set": {"read": True}})
    elif body.action == "reactivate":
        await db.creators.update_one({"id": a["creator_id"]},
                                     {"$set": {"status": cp_mod.CREATOR_ACTIVE},
                                      "$unset": {"paused_until": "", "paused_reason": ""}})
        await db.creator_alerts.update_one({"id": body.alert_id},
                                           {"$set": {"read": True, "resolved_at": now_iso()}})
    elif body.action == "suspend":
        await db.creators.update_one({"id": a["creator_id"]},
                                     {"$set": {"status": cp_mod.CREATOR_SUSPENDED}})
        await db.creator_alerts.update_one({"id": body.alert_id},
                                           {"$set": {"read": True, "resolved_at": now_iso()}})
    else:
        raise HTTPException(status_code=400, detail="INVALID_ACTION")
    logger.info("[cp] alert %s action=%s by admin=%s", body.alert_id, body.action, admin.get("id"))
    await _cp_broadcast_leaderboard_soon()
    return {"success": True}


def _cp_csv_cell(v) -> str:
    """Excel formula-injection guard for CSV export."""
    s = str(v if v is not None else "")
    if s[:1] in ("=", "+", "-", "@"):
        return "'" + s
    return s


@api_router.get("/creator/admin/payouts.csv")
async def creator_admin_payouts_csv(admin=Depends(get_admin_user)):
    import csv
    import io as _io
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "type", "creator_code", "creator_name", "referred_user_id",
                "referred_name", "amount_pm", "month", "referral_id"])
    rows = await db.referrals.find({"status": cp_mod.STATUS_REWARDED}, {"_id": 0}) \
                             .sort("rewarded_at", -1).limit(5000).to_list(length=5000)
    creator_ids = list({r.get("creator_id") for r in rows})
    ref_uids = list({r.get("referred_user_id") for r in rows})
    creators = {}
    if creator_ids:
        async for c in db.creators.find({"id": {"$in": creator_ids}},
                                        {"_id": 0, "id": 1, "code": 1, "display_name": 1}):
            creators[c["id"]] = c
    users = {}
    if ref_uids:
        async for u in db.users.find({"id": {"$in": ref_uids}}, {"_id": 0, "id": 1, "persona_name": 1}):
            users[u["id"]] = u
    for r in rows:
        c = creators.get(r.get("creator_id"), {})
        u = users.get(r.get("referred_user_id"), {})
        w.writerow([_cp_csv_cell(r.get("rewarded_at") or r.get("created_at")), "REFERRAL",
                    _cp_csv_cell(c.get("code")), _cp_csv_cell(c.get("display_name")),
                    _cp_csv_cell(r.get("referred_user_id")), _cp_csv_cell(u.get("persona_name")),
                    int(r.get("reward_amount") or 0), _cp_csv_cell(r.get("month")), _cp_csv_cell(r.get("id"))])
    async for m in db.hall_of_fame.find({}, {"_id": 0}).sort("month", -1):
        for entry in (m.get("top") or []):
            w.writerow([_cp_csv_cell(m.get("closed_at")), f"MONTHLY_TOP_{entry.get('rank')}",
                        _cp_csv_cell(entry.get("code")), _cp_csv_cell(entry.get("display_name")),
                        _cp_csv_cell(entry.get("user_id")), "",
                        int(entry.get("prize_pm") or 0), _cp_csv_cell(m.get("month")), ""])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="creator_payouts.csv"'})


@api_router.post("/creator/admin/seed-demo")
async def creator_admin_seed_demo(admin=Depends(get_admin_user)):
    # Demo rows on the LIVE public board are a real hazard; this only runs
    # when the operator has deliberately armed it in the environment.
    if os.environ.get("LIN_CREATOR_DEMO") != "1":
        raise HTTPException(status_code=403, detail="DEMO_DISABLED (set LIN_CREATOR_DEMO=1 to allow)")
    import random as _r
    existing = await db.creators.count_documents({"is_demo": True})
    if existing >= 20:
        return {"success": True, "skipped": True, "existing": existing}
    names = [("SHADOWFANG", "ShadowFang"), ("REXKING", "RexKing"), ("VENOMBITE", "VenomBite"),
             ("NIGHTHOWL", "NightHowl"), ("BLOODMOON", "BloodMoon"), ("PRIMEALPHA", "PrimeAlpha"),
             ("IRONSCALE", "IronScale"), ("EMBERWYRM", "EmberWyrm"), ("FROSTCLAW", "FrostClaw"),
             ("SKYPREDATOR", "SkyPredator"), ("TITANCRUSH", "TitanCrush"), ("GOLDENMAW", "GoldenMaw")]
    month = cp_mod.month_id()
    created = 0
    for i, (code, display) in enumerate(names):
        power = len(names) - i
        total = max(1, int(power * _r.uniform(3.5, 6.5)))
        monthly = max(1, int(total * _r.uniform(0.15, 0.6)))
        uid = f"cp_demo_{code.lower()}"
        await db.users.update_one(
            {"id": uid},
            {"$setOnInsert": {"id": uid, "persona_name": display, "coins": 0,
                              "steam_id": f"demo_{code.lower()}", "is_demo": True,
                              "avatar": None, "created_at": now_iso()}},
            upsert=True)
        try:
            await db.creators.insert_one({
                "id": new_id(), "user_id": uid, "code": code,
                "status": cp_mod.CREATOR_ACTIVE, "display_name": display,
                "total_referrals": total, "monthly_referrals": monthly,
                "total_prime_meat_earned": 0, "monthly_prime_meat_earned": 0,
                "exclusive_skin_unlocked": False, "stages_reached": [],
                "current_month": month, "is_demo": True,
                "created_at": now_iso(), "updated_at": now_iso()})
            created += 1
        except Exception:
            continue
    await _cp_broadcast_leaderboard_soon()
    return {"success": True, "created": created}


@api_router.post("/creator/admin/clear-demo")
async def creator_admin_clear_demo(admin=Depends(get_admin_user)):
    r1 = await db.creators.delete_many({"is_demo": True})
    r2 = await db.users.delete_many({"is_demo": True, "id": {"$regex": "^cp_demo_"}})
    await _cp_broadcast_leaderboard_soon()
    return {"success": True, "creators_deleted": r1.deleted_count, "users_deleted": r2.deleted_count}

# ─── Creator Program: monthly close (claim-gated, crash-resumable) ──────────

def _cp_prev_month(current: str) -> str:
    y, m = int(current[:4]), int(current[5:])
    return f"{y - 1:04d}-12" if m == 1 else f"{y:04d}-{m - 1:02d}"


async def _cp_close_month_if_needed():
    """At month rollover: snapshot the top 3, pay PrimeMeat + the prize skin
    (owner order: pink glitter to creator places 1/2/3), save the Hall of Fame,
    then reset monthly counters.

    Crash-safety shape (mirrors the season leaderboard rollover): the HoF doc
    is created ONCE ($setOnInsert, never overwritten), every payment is
    claim-gated on that doc (`paid_ranks` / `skin_paid_ranks` $addToSet), the
    marker flips only after payments, and the counter reset is an idempotent
    heal that also runs on every later tick. Any crash point re-runs to the
    same end state with nothing paid twice."""
    now = datetime.now(timezone.utc)
    current = cp_mod.month_id(now)
    prev = _cp_prev_month(current)
    settings = await _cp_get_settings()   # first boot seeds last_closed_month=prev (adoption)
    if settings.get("last_closed_month") != prev:
        top = await db.creators.find(
            {"status": {"$ne": cp_mod.CREATOR_SUSPENDED}, "is_demo": {"$ne": True},
             "monthly_referrals": {"$gt": 0}, "current_month": prev},
            {"_id": 0}
        ).sort("monthly_referrals", -1).limit(3).to_list(length=3)
        entries = []
        for i, c in enumerate(top):
            u = await db.users.find_one({"id": c["user_id"]},
                                        {"_id": 0, "persona_name": 1, "avatar": 1, "avatar_url": 1})
            entries.append({
                "rank": i + 1, "creator_id": c["id"], "user_id": c["user_id"],
                "code": c.get("code"),
                "display_name": c.get("display_name") or (u or {}).get("persona_name"),
                "avatar": (u or {}).get("avatar") or (u or {}).get("avatar_url"),
                "monthly_referrals": int(c.get("monthly_referrals", 0)),
                "monthly_prime_meat_earned": int(c.get("monthly_prime_meat_earned", 0)),
                "prize_pm": CP_MONTHLY_TOP_PRIZES[i] if i < len(CP_MONTHLY_TOP_PRIZES) else 0,
                "prize_skin": CP_PRIZE_SKIN_BY_RANK.get(i + 1),
            })
        await db.hall_of_fame.update_one(
            {"month": prev},
            {"$setOnInsert": {"month": prev, "top": entries, "closed_at": now_iso()}},
            upsert=True)
        hof = await db.hall_of_fame.find_one({"month": prev}, {"_id": 0}) or {"top": entries}
        for entry in (hof.get("top") or []):
            rank = int(entry.get("rank") or 0)
            uid = entry.get("user_id")
            cid = entry.get("creator_id")
            prize = int(entry.get("prize_pm") or 0)
            if prize and uid:
                claimed = await db.hall_of_fame.find_one_and_update(
                    {"month": prev, "paid_ranks": {"$ne": rank}},
                    {"$addToSet": {"paid_ranks": rank}})
                if claimed:
                    await db.users.update_one({"id": uid}, {"$inc": {"coins": prize}})
                    await add_transaction(uid, "normal", prize, "creator_monthly_top",
                                          f"Programa de Creadores · Top {rank} de {prev}")
                    if cid:
                        await db.creators.update_one({"id": cid},
                                                     {"$inc": {"total_prime_meat_earned": prize}})
                        await _cp_notify(cid, "REWARD_RECEIVED",
                                         f"Top {rank} del mes {prev}",
                                         f"Premio: +{prize:,} PrimeMeat",
                                         meta={"amount": prize, "month": prev, "rank": rank})
            gid = entry.get("prize_skin") or CP_PRIZE_SKIN_BY_RANK.get(rank)
            if gid and uid:
                claimed = await db.hall_of_fame.find_one_and_update(
                    {"month": prev, "skin_paid_ranks": {"$ne": rank}},
                    {"$addToSet": {"skin_paid_ranks": rank}})
                if claimed:
                    ok = await _grant_prize_skin(uid, gid,
                                                 f"Programa de Creadores — Top {rank} de {prev}")
                    if not ok:
                        logger.error("[cp] monthly prize skin %r failed for rank %d month %s", gid, rank, prev)
                    elif cid:
                        g = glitch_catalog.GLITCH_BY_ID.get(gid) or {}
                        await _cp_notify(cid, "REWARD_RECEIVED",
                                         f"Skin de campeón · Top {rank}",
                                         f"Ganaste la skin {g.get('name', gid)} por el Top {rank} de {prev}.",
                                         meta={"glitch_id": gid, "month": prev, "rank": rank})
        await db.creator_settings.update_one({"id": "settings"},
                                             {"$set": {"last_closed_month": prev}}, upsert=True)
        logger.info("[cp] month %s closed, %d podium entries", prev, len(hof.get("top") or []))
        await _cp_broadcast_leaderboard_soon()
    # Idempotent heal, every tick: any creator still carrying an old month gets
    # its monthly counters reset (covers a crash between marker and reset, and
    # creators whose month was never touched by a validate).
    await db.creators.update_many(
        {"current_month": {"$ne": current}},
        {"$set": {"monthly_referrals": 0, "monthly_prime_meat_earned": 0,
                  "current_month": current}})


async def creator_monthly_close_loop():
    while True:
        try:
            await _cp_close_month_if_needed()
        except Exception as e:
            logger.warning(f"[cp] monthly close loop: {e}")
        await asyncio.sleep(600)


# ─── Creator Program: WebSocket ─────────────────────────────────────────────

@app.websocket("/api/creator/ws")
async def creator_ws(ws: WebSocket):
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
        top_all = await _cp_leaderboard_snapshot(scope="all", limit=30)
        top_month = await _cp_leaderboard_snapshot(scope="month", limit=30)
        await ws.send_json({"type": "creator_leaderboard", "ts": now_iso(),
                            "all_time": top_all, "monthly": top_month,
                            "prize_skins": _cp_prize_skin_cards(),
                            "monthly_prizes": CP_MONTHLY_TOP_PRIZES})
        if user_id:
            payload = await _cp_dashboard_payload(user_id)
            if payload:
                # Same shape as GET /creator/dashboard (see push_to_user site).
                await ws.send_json({"type": "creator_dashboard", "data": {"is_creator": True, **payload}})
        if len(creator_hub.clients) >= CP_WS_MAX_CLIENTS:
            await ws.close()
            return
        await creator_hub.add(ws, user_id)
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[cp] creator_ws: {e}")
    finally:
        await creator_hub.remove(ws)

# ─── end Creator Program ────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════════
# CEMENTERIO & RESURRECCIÓN (FÓSIL)  — 2026-06
# Registro de dinos muertos + economía de Fósiles (comprados con Amberiums =
# vip_coins) + fósil gratis mensual + cooldown de resurrección de 24h +
# restricción de ahogamiento en combate (excepción Deinosuchus) + WebSocket.
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



# ---------- advanced skin contract v2 (ten colour slots) ----------
# Registered on `app` BEFORE include_router so the three v2 paths are resolved
# on the app itself and can never be shadowed by a later catch-all.
#
# Until this owner's GAME side publishes `skin_contract_capabilities.json` +
# `skin_contract_v2_alive.json`, `/api/studio/skin-contract-state` answers
# `enabled:false reason=no_writer_capability` and the studio keeps its seven
# slots. That is the honest state, not a failure.


def _skin_v2_queued(steam_id: str, cmd: dict, dino: dict, request) -> None:
    """Post-queue bookkeeping. Never fatal - the dino is already being painted."""
    try:
        logger.info("skin_apply_v2_queued steam_id=%s cmd_id=%s actor=%s class=%s",
                    steam_id, cmd.get("cmd_id"), dino.get("actor_name"),
                    dino.get("class"))
    except Exception:
        pass


_skin_v2_installed = _skin_v2_mount.install(
    app,
    _skin_v2_engine.OwnerAdapter(
        owner_key="laislanublar",
        saved_dir=game_ipc.SAVED_DIR,
        # THIS OWNER'S BEACON IS NOT `<slug>_mod_alive.json`. La Isla Nublar's
        # mod publishes the bare `mod_alive.json` - read off game_ipc rather
        # than assumed, because assuming the fleet's usual naming here would
        # have made a perfectly healthy writer read `no_active_boot` forever.
        # (Re-measured 2026-08-25 against the LIVE backend, not the staged copy:
        # game_ipc.py:50 on prod and in the repo both spell it `mod_alive.json`.)
        alive_leaf=os.path.basename(game_ipc.MOD_ALIVE_JSON),
        namespace="lin",
        manifest_sha256=lin_skinv2_manifest.SHA256,
        find_active_dino=lambda steam_id: game_ipc.find_active_dino(steam_id),
        rate_reserve=_skin_apply_rate_reserve,
        rate_rollback=_skin_apply_rate_rollback,
        on_queued=_skin_v2_queued,
    ),
    auth_dependency=_skin_v2_steam_id,
)


app.include_router(api_router)
app.include_router(crash_game.router, prefix="/api")
# Pase de Batalla: same dependency-injection handoff crash_game uses, then the
# router. configure() must run BEFORE the first request, not at import time.
battle_pass.configure(db, current_user_dep=get_current_user, admin_user_dep=get_admin_user,
                      add_transaction=add_transaction, add_log=add_log, park_cap=_user_park_cap)
app.include_router(battle_pass.router, prefix="/api")
# Baneos de la página web: same handoff. Owners only (get_owner_user); the
# owner list doubles as the "cannot be banned from here" list; the bot's sqlite
# is a read-only name source for the drop-down.
webban.configure(db, owner_ids=ADMIN_STEAM_IDS, current_user_dep=get_current_user,
                 owner_user_dep=get_owner_user, add_log=add_log, bot_db_path=game_ipc.BOT_DB_PATH)
app.include_router(webban.router, prefix="/api")
# GEN-Ø facility infection (2026-08-21): same handoff. The tracker loop reads
# the mod's ~1 s position feed on its own 8 s cadence (a 30 s dwell needs it;
# the 45 s quest tick cannot see one) and banners ride the monolith's own
# notify_commands.json queue — the /prime popup surface.
gen0_infection.configure(db)
app.include_router(gen0_infection.build_router(get_current_user), prefix="/api")
# Nublar Spin (2026-08-23): the daily wheel draws on the casino's own
# provably-fair seeds and pays through this file's lanes (crate currency,
# Battle Pass tokens, reward_skins, vault.save_parked, gen0_state).
wheel_routes.configure(
    db, current_user_dep=get_current_user, owner_user_dep=get_owner_user,
    add_transaction=add_transaction, add_log=add_log, new_id=new_id, now_iso=now_iso,
    patreon_tier_key=_patreon_tier_key,
    pf={"get_active": _pf_get_active, "float": _pf_float, "float_i": _pf_float_i,
        "pick": _pf_pick},
    glitch_uses_per_win=GLITCH_USES_PER_WIN)
app.include_router(wheel_routes.router, prefix="/api")


async def _streamer_amber_pass(nowt, period):
    """One Streamer Pack amber payout pass: flat STREAMER_AMBER (20k) bi-weekly, gated
    on a LIVE role recheck at each boundary so a removed role (ban / caught cheating)
    stops payment. Active patrons are excluded — their tier amber already covers them
    (no stacking; a streamer who later subscribes switches to tier amber)."""
    if not DISCORD_STREAMER_ROLE_ID:
        return
    scursor = db.users.find({
        "discord_streamer_role": {"$nin": ["", None]},
        "streamer_amber_anchor": {"$exists": True},
        "patreon_patron_status": {"$ne": "active_patron"},
    })
    async for u in scursor:
        try:
            base = datetime.fromisoformat(u["streamer_amber_anchor"])
        except Exception:
            continue
        done = int(u.get("streamer_amber_count", 0))
        due = int((nowt - base) / period)  # completed 14-day periods
        # Anyone holding the role who has never had the joining payment gets it here —
        # streamers approved before the instant payout existed, and any grant whose
        # inline attempt lost a race. Still gated on the live role check below.
        needs_welcome = not u.get("streamer_welcome_amber_at")
        if due <= done and not needs_welcome:
            continue
        did = str(u.get("discord_id") or "")
        if not did:
            continue
        in_guild, roles = await _discord_member_info(did, force=True)
        if in_guild is None:
            continue  # Discord unreachable — defer to next tick (catch-up preserves periods)
        if not _has_streamer_role(roles):
            # Role gone: revoke the stored flag so every benefit stops.
            await db.users.update_one({"id": u["id"]}, {"$set": {"discord_streamer_role": ""}})
            continue
        if needs_welcome and await _streamer_pay_welcome_amber(
                u["id"], did, u.get("persona_name") or ""):
            # Joining payment lands now and the clock restarts from this instant, exactly
            # as if they had just been approved — never both payments in one tick.
            await db.users.update_one({"id": u["id"]}, {"$set": {
                "streamer_amber_anchor": now_iso(), "streamer_amber_count": 0}})
            continue
        if due <= done:
            continue
        if (due - done) > 1:
            # More than one period is "due" ONLY after a gap in eligibility — the user was
            # an active patron (excluded from this pass) or their role was removed then
            # re-added. A continuously-eligible streamer is paid within 5 min of each 14-day
            # boundary, so due-done is always exactly 1. Never back-pay the gap: start a
            # fresh clock so only continuous streaming earns amber (closes the lump-sum
            # back-pay / patron-cancel double-dip).
            await db.users.update_one({"id": u["id"]}, {"$set": {
                "streamer_amber_anchor": now_iso(), "streamer_amber_count": 0}})
            continue
        total = STREAMER_AMBER  # exactly one period due
        await db.users.update_one({"id": u["id"]}, {
            "$inc": {"vip_coins": total, "streamer_amber_count": 1},
            "$set": {"last_amber_payout_at": now_iso()},
        })
        await add_transaction(u["id"], "vip", total, "reward", "Streamer Pack Amberium quincenal")
        await add_log(u.get("persona_name"), "amber_payout", "streamer", {"amount": total, "periods": 1})
        # Every payout is announced to the streamer. Fired, not awaited: a slow or closed
        # DM must never stall the loop or hold up the next user's payment.
        _fire(_streamer_notify_payout(did, total, first=False))


async def amber_payout_loop():
    """Grant bi-weekly Amberium (vip_coins) to active Patreon patrons based on their tier.
    Fires automatically once Patreon is connected. The JOINING payment is normally made by
    `sync_patreon_for_user` the moment someone subscribes; this loop carries a backstop for
    anyone who became a patron before that path existed, and DMs every recurring payout."""
    while True:
        try:
            nowt = datetime.now(timezone.utc)
            period = timedelta(days=PATREON_PAYOUT_DAYS)
            cursor = db.users.find({"patreon_patron_status": "active_patron", "amber_payout_anchor": {"$exists": True}})
            async for u in cursor:
                # One malformed row must never cost every patron behind it their payout —
                # and the streamer pass runs AFTER this loop, so an escape here used to
                # skip that too. Contained per user; the pass always reaches the end.
                try:
                    await _patreon_payout_one(u, nowt, period)
                except Exception as e:
                    logger.warning(f"[patreon] payout pass for {u.get('id')}: {e}")
            await _streamer_amber_pass(nowt, period)
        except Exception as e:
            logger.warning(f"amber payout loop: {e}")
        await asyncio.sleep(300)


async def primemeat_payout_loop():
    """Credit PrimeMeat to players connected in the server (real RCON presence), even if the website is closed."""
    while True:
        try:
            if rcon_client.is_configured():
                ids, _names = await _rcon_online_players()
                connected = set(str(i).strip() for i in ids)
                now = datetime.now(timezone.utc)
                if connected:
                    async for u in db.users.find({"steam_id": {"$in": list(connected)}}):
                        await _credit_playtime(u, now)
                async for u in db.users.find({"pm_session_start": {"$exists": True}}):
                    if str(u.get("steam_id") or "") not in connected:
                        await db.users.update_one({"id": u["id"]}, {"$unset": {"pm_session_start": "", "pm_session_earned": ""}})
        except Exception as e:
            logger.warning(f"primemeat payout loop: {e}")
        await asyncio.sleep(60)


DINO_SNAPSHOT_INTERVAL_S = max(5, int(os.environ.get("LIN_DINO_SNAPSHOT_INTERVAL_S", "20") or "20"))
# A quiet tick writes nothing, so say so on a slow clock — otherwise "is the
# recovery lane running?" has no answer in the log.
DINO_SNAPSHOT_HEARTBEAT_S = 900
_dino_snapshot_sigs: dict[str, str] = {}
# Highest vault row id already marked. `parked_dinos.id` is AUTOINCREMENT and
# never reused, so this is an exact "everything below here is done" and the
# steady-state tick reads zero rows instead of scanning the whole table.
_park_mark_high_water = -1


async def _record_park_marks():
    """Remember every vault row, so a park is never mistaken for a loss.

    Parking KILLS the dino, so a park writes a death line exactly like a real
    loss. The vault row tells them apart — but only until the player redeems it
    and the row disappears. A mark keeps that verdict after the row is gone, so
    a parked-then-redeemed dino is never offered as 'lost' and handed out twice.

    Marks are written for every row not marked yet, including on the first tick
    after a restart — the timestamp is the row's own parked_at, so there is no
    guesswork, and skipping that tick would lose every park made while the
    backend was down, which is exactly when the mark matters most.

    ★This MIRRORS an event rather than recording it: parked_dinos has writers
    that killed nothing (store purchase, marketplace delivery, and this very
    recovery lane), and a queued park replayed late lands outside the match
    window. The real fix is a park-event row written by the park path at the
    confirmed kill; that needs vault.py + the bot, so it is a follow-up.
    """
    global _park_mark_high_water
    if _park_mark_high_water < 0:
        top = await db[dino_recovery.PARK_MARK_COLLECTION].find_one(
            {}, {"_id": 0, "vault_row_id": 1}, sort=[("vault_row_id", -1)])
        _park_mark_high_water = int((top or {}).get("vault_row_id") or 0)

    rows = await asyncio.to_thread(
        dino_recovery.read_parked_rows, game_ipc.BOT_DB_PATH, None, _park_mark_high_water)
    if not rows:
        return 0
    # Rows this lane created are recoveries, not parks — marking them would let
    # a grant suppress a genuine death of the same species minutes later.
    granted_ids = set()
    ids = [int(r["id"]) for r in rows]
    async for claim in db[dino_recovery.RECOVERY_COLLECTION].find(
            {"vault_row_id": {"$in": ids}}, {"_id": 0, "vault_row_id": 1}):
        granted_ids.add(int(claim["vault_row_id"]))
    fresh = [r for r in rows if int(r["id"]) not in granted_ids]

    if fresh:
        await db[dino_recovery.PARK_MARK_COLLECTION].bulk_write([
            UpdateOne({"vault_row_id": int(r["id"])},
                      {"$setOnInsert": {
                          "vault_row_id": int(r["id"]), "steam_id": str(r["steam_id"]),
                          "dino_class": str(r["dino_class"] or ""),
                          "parked_at_ts": int(r["parked_at_ts"] or 0),
                          "created_at": now_iso()}},
                      upsert=True)
            for r in fresh], ordered=False)
    # Only advance once the writes landed, so a failed tick retries the same rows.
    _park_mark_high_water = max(ids)
    return len(fresh)


async def _write_dino_snapshots():
    """One tick of last-seen-alive capture. Returns (tracked, written)."""
    players = await asyncio.to_thread(game_ipc.read_players_json)
    if not isinstance(players, dict):
        return 0, 0
    now_s = int(time.time())
    live_sids, written = set(), 0
    for sid, row in players.items():
        if not isinstance(row, dict):
            continue
        snap = dino_recovery.snapshot_from_player_row(sid, row, now_s)
        if not snap:
            continue
        live_sids.add(snap["steam_id"])
        sig = dino_recovery.snapshot_signature(snap)
        if _dino_snapshot_sigs.get(snap["steam_id"]) == sig:
            continue
        await db[dino_recovery.SNAPSHOT_COLLECTION].update_one(
            {"steam_id": snap["steam_id"]}, {"$set": snap}, upsert=True)
        # ★AND KEEP THE OLD ONE. The rolling document above is overwritten by
        # this player's NEXT dino within one tick of their respawn, which is
        # why a recovery clicked a few minutes after a death used to hand back
        # an empty animal: the only record of what died had already been
        # replaced. This append-only copy is what the recovery lane binds
        # against. We are already inside the "the signature changed" branch, so
        # this writes exactly the state TRANSITIONS — not one row per tick —
        # and a TTL index trims it. seen_dt exists only because a mongo TTL
        # index needs a real date; seen_at stays the epoch everything else uses.
        history_doc = dict(snap)
        history_doc["seen_dt"] = datetime.fromtimestamp(
            int(snap.get("seen_at") or now_s), tz=timezone.utc)
        try:
            await db[dino_recovery.SNAPSHOT_HISTORY_COLLECTION].insert_one(history_doc)
        except Exception:
            # Contained: history is what makes a recovery COMPLETE, but the
            # rolling document above still makes it POSSIBLE. Losing history
            # must never stop the loop or the site.
            logger.warning("[recovery] snapshot history write failed sid=%s",
                           snap.get("steam_id"), exc_info=True)
        _dino_snapshot_sigs[snap["steam_id"]] = sig
        written += 1
    # Drop signatures for players who left so their next session writes a fresh
    # snapshot instead of being skipped as unchanged.
    for gone in [s for s in _dino_snapshot_sigs if s not in live_sids]:
        _dino_snapshot_sigs.pop(gone, None)
    return len(live_sids), written


async def dino_snapshot_loop():
    """Keep a last-seen-alive record of every live dino.

    This is what lets a recovered dino come back with its real mutations, prime
    state and growth: a death line only carries species and growth. Bounded by
    player count (one document per player, upserted), and it only writes when
    something actually changed.
    """
    await asyncio.sleep(15)
    heartbeat_at = 0.0
    while True:
        try:
            tracked, written = await _write_dino_snapshots()
            marked = await _record_park_marks()
            # BirthSkin (2026-07-30): hatchling inherited-skin sweep -
            # time-gated internally (default 600s), crash-contained,
            # never raises (see skinkeeper_web.maybe_start_birth_sweep).
            skinkeeper_web.maybe_start_birth_sweep()
            # Without this there is no way to grep whether the lane is alive:
            # a healthy quiet tick writes nothing at all. Throttled so it cannot
            # flood, and it always reports the counts a soak needs.
            now = time.time()
            if written or marked or (now - heartbeat_at) >= DINO_SNAPSHOT_HEARTBEAT_S:
                heartbeat_at = now
                logger.info("[recovery] snapshot tick tracked=%d written=%d park_marks=%d",
                            tracked, written, marked)
        except Exception as e:
            logger.warning(f"dino snapshot loop: {e}", exc_info=True)
        await asyncio.sleep(DINO_SNAPSHOT_INTERVAL_S)


async def population_telemetry_loop():
    """Poll the live server log over SFTP to keep the real per-species population fresh."""
    while True:
        try:
            await asyncio.to_thread(game_tele.poll)
            await _drain_kill_credits()
        except Exception as e:
            logger.warning(f"population telemetry poll: {e}")
        await asyncio.sleep(30)


_BAN_CMDS_LOCK = threading.Lock()


def _write_mod_kick_sync(sid: str, reason: str, name: str = "", actor_sid: str = "") -> None:
    """Append a kick command for the mod's ban_commands lane (atomic tmp+replace; the
    mod drains by renaming the file away, so a vanished file just means start a fresh
    list). Reason is sanitized — the Lua parser block-matches braces and bare
    braces/quotes/backslashes would corrupt it.

    `name` is the target's display name and `actor_sid` the SteamID of the staff
    member issuing the sanction. The mod runs the game's own admin Kick RPC, which is
    gated on the SteamID of the controller it executes on, so it needs a real admin to
    run through — preferring the person who actually pressed the button. Both fields
    are optional; the mod falls back to any online admin and a generic name."""
    import json as _json
    path = os.path.join(game_ipc.SAVED_DIR, "ban_commands.json")
    clean = re.sub(r"[{}\"\\]", " ", str(reason or "Sancion"))[:120].strip() or "Sancion"
    # The name is read straight back out by a Lua pattern and shown in-game, so it is
    # held to plain printable ASCII: ensure_ascii JSON would otherwise hand the mod a
    # literal \uXXXX escape to display.
    clean_name = re.sub(r"[^ -~]", "", re.sub(r"[{}\"\\]", " ", str(name or "")))[:48].strip()
    clean_actor = re.sub(r"[^0-9]", "", str(actor_sid or ""))[:20]
    with _BAN_CMDS_LOCK:
        rows = []
        try:
            txt = open(path, "rb").read().decode("utf-8-sig", "replace").strip()
            if txt:
                parsed = _json.loads(txt)
                if isinstance(parsed, list):
                    rows = parsed
        except (OSError, ValueError):
            rows = []
        row = {"action": "kick", "steamid": str(sid), "reason": clean}
        if clean_name:
            row["name"] = clean_name
        if clean_actor:
            row["actor_sid"] = clean_actor
        rows.append(row)
        tmp = path + ".webtmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(rows, f, ensure_ascii=True)
        os.replace(tmp, path)


async def _mod_kick(sid: str, reason: str, name: str = "", actor_sid: str = "") -> None:
    await asyncio.to_thread(_write_mod_kick_sync, sid, reason, name, actor_sid)


async def _sweep_pending_kicks(online: set, tick: int = 0) -> int:
    """Verified pending kicks: while the target shows in the online set, keep firing
    the mod-lane kick (RCON as belt) and count attempts; the flag clears ONLY when a
    later fresh player list shows the target GONE after >=1 attempt — acks are never
    trusted. A target that never appears stays armed for their next spawn. 12 attempts
    (~2 min) without disappearance gives up LOUDLY. Never raises."""
    applied = 0
    try:
        async for pu in db.users.find({"pending_kick": {"$exists": True}},
                                      {"_id": 0, "id": 1, "steam_id": 1, "persona_name": 1, "pending_kick": 1}):
            psid = str(pu.get("steam_id") or "").strip()
            if not psid:
                continue
            pk = pu.get("pending_kick") or {}
            attempts = int(pk.get("attempts") or 0)
            if psid in online:
                if attempts == 12:
                    # Still here after ~2 min — likely pawnless in the spawn menu (no
                    # controller the mod can resolve). Log ONCE but STAY ARMED: keep
                    # firing so the kick lands the instant they possess a pawn, and let
                    # the offline branch self-clear when they leave. Never abandon a
                    # live sanction.
                    await add_log("La Isla Nublar", "pending_kick_slow", pu.get("persona_name"),
                                  {"steam_id": psid, "reason": pk.get("reason"), "attempts": attempts})
                    logger.warning("[ban-enforcer] pending kick SLOW sid=%s (>=12 attempts, staying armed)", psid)
                # After the first ~2 minutes of 10s attempts, drop to one attempt a
                # minute. The sanction stays armed for as long as it takes — it is never
                # abandoned — but a target this lane cannot reach must not sit in a
                # permanent 10s retry loop: on 2026-07-29 one did, for 70 minutes, and
                # every single cycle also wrote an RCON line into the game log.
                if attempts >= 12 and (int(tick) % 6) != 0:
                    continue
                try:
                    await _mod_kick(psid, pk.get("reason") or "Sancion",
                                    pk.get("name") or pu.get("persona_name") or "",
                                    pk.get("by_sid") or "")
                except Exception as e:
                    logger.warning("[ban-enforcer] mod kick write failed sid=%s err=%s", psid, e)
                # The RCON belt runs only while the mod lane is still establishing
                # itself. It has never removed a live player on this build, so past the
                # first attempts it is pure game-log noise.
                if rcon_client.is_configured() and attempts < 12:
                    try:
                        await rcon_client.kick(psid)
                    except Exception:
                        pass
                await db.users.update_one({"id": pu["id"]}, {"$set": {"pending_kick.attempts": min(attempts + 1, 999)}})
            elif attempts >= 1:
                await db.users.update_one({"id": pu["id"]}, {"$unset": {"pending_kick": ""}})
                applied += 1
                await add_log(pk.get("by") or "La Isla Nublar", "pending_kick_applied", pu.get("persona_name"),
                              {"steam_id": psid, "reason": pk.get("reason"), "attempts": attempts})
                logger.info("[ban-enforcer] pending kick VERIFIED gone sid=%s after %d attempt(s)", psid, attempts)
    except Exception as e:
        logger.warning("[ban-enforcer] pending sweep error: %s", e)
    # Manual lane: raw-Steam-ID kicks from the Discord bot for players with no web
    # account. Identical verified-gone semantics; the row IS the armed flag, so a
    # verified disappearance deletes it.
    try:
        async for mk in db.manual_kicks.find({}, {"_id": 0}):
            msid = str(mk.get("steam_id") or "").strip()
            if not msid:
                continue
            attempts = int(mk.get("attempts") or 0)
            if msid in online:
                if attempts == 12:
                    await add_log("La Isla Nublar", "pending_kick_slow", mk.get("name") or msid,
                                  {"steam_id": msid, "reason": mk.get("reason"), "attempts": attempts})
                    logger.warning("[ban-enforcer] manual pending kick SLOW sid=%s (>=12 attempts, staying armed)", msid)
                if attempts >= 12 and (int(tick) % 6) != 0:
                    continue
                try:
                    await _mod_kick(msid, mk.get("reason") or "Sancion",
                                    mk.get("name") or "", mk.get("by_sid") or "")
                except Exception as e:
                    logger.warning("[ban-enforcer] manual mod kick write failed sid=%s err=%s", msid, e)
                if rcon_client.is_configured() and attempts < 12:
                    try:
                        await rcon_client.kick(msid)
                    except Exception:
                        pass
                await db.manual_kicks.update_one({"steam_id": msid}, {"$set": {"attempts": min(attempts + 1, 999)}})
            elif attempts >= 1:
                await db.manual_kicks.delete_one({"steam_id": msid})
                applied += 1
                await add_log(mk.get("by") or "La Isla Nublar", "pending_kick_applied", mk.get("name") or msid,
                              {"steam_id": msid, "reason": mk.get("reason"), "attempts": attempts})
                logger.info("[ban-enforcer] manual pending kick VERIFIED gone sid=%s after %d attempt(s)", msid, attempts)
    except Exception as e:
        logger.warning("[ban-enforcer] manual pending sweep error: %s", e)
    return applied


async def ban_enforcer_loop():
    """Make timed native bans actually hold on a LIVE server. A PlayerBans.json entry
    (and even an RCON ban) does not reliably block an immediate reconnect until the
    server restarts, so every ~30s we re-kick any connected player inside an active ban
    window and prune lapsed entries. Every ~5 min we also SELF-HEAL: re-derive the native
    ban for any web-banned user whose native entry is missing (covers a native write that
    failed under a transient file lock at strike time). Best-effort; never touches
    un-banned players or protected owners."""
    await asyncio.sleep(25)
    tick = 0
    while True:
        try:
            if rcon_client.is_configured() and native_bans.is_available():
                await asyncio.to_thread(native_bans.prune_expired)
                banned = await asyncio.to_thread(native_bans.active_banned_ids)
                # `now` is read by the unban-retry block EVERY tick — binding it only
                # inside the %30 branch left it up to 5 minutes stale, and unbound
                # entirely if the first pass ever skipped (RCON down at boot), which
                # made the blanket except kill the whole enforcer body on most ticks.
                now = datetime.now(timezone.utc)
                if tick % 30 == 0:  # ~5 min: reconcile web-banned users into the native file
                    async for hu in db.users.find(
                        {"$or": [{"ban_permanent": True}, {"banned_until": {"$gt": now.isoformat()}}]},
                        {"_id": 0, "steam_id": 1, "persona_name": 1, "ban_permanent": 1, "banned_until": 1}):
                        hsid = str(hu.get("steam_id") or "").strip()
                        if not hsid or hsid in banned:
                            continue
                        # Re-read the LIVE ban state immediately before writing: an
                        # unban / de-escalation between the cursor fetch and here must
                        # not be clobbered by a stale re-add (that would be a native
                        # lockout the panel shows as "unbanned" — un-liftable).
                        fresh = await db.users.find_one({"steam_id": hsid},
                                                        {"_id": 0, "ban_permanent": 1, "banned_until": 1})
                        if not fresh:
                            continue
                        fperm = bool(fresh.get("ban_permanent"))
                        fbu = fresh.get("banned_until")
                        if not (fperm or (fbu and fbu > now.isoformat())):
                            continue
                        if fperm:
                            hrs = 0
                        else:
                            try:
                                hrs = max(1, math.ceil((datetime.fromisoformat(fbu) - now).total_seconds() / 3600))
                            except Exception:
                                continue
                        if await asyncio.to_thread(native_bans.add_ban, hsid, "Sanción (auto-sync)", hrs, hu.get("persona_name"), "La Isla Nublar", ""):
                            banned.add(hsid)
                            logger.info("[ban-enforcer] self-healed native ban sid=%s", hsid)
                # Retry native unbans that failed under a transient file lock (targeted:
                # only sids the web explicitly unbanned — never touches game-authored
                # bans). Drops the pending flag if the user got re-banned meanwhile.
                async for uu in db.users.find({"native_unban_pending": {"$exists": True}},
                                              {"_id": 0, "id": 1, "steam_id": 1, "native_unban_pending": 1,
                                               "ban_permanent": 1, "banned_until": 1}):
                    usid = str(uu.get("native_unban_pending") or "").strip()
                    rebanned = bool(uu.get("ban_permanent")) or (uu.get("banned_until") and uu["banned_until"] > now.isoformat())
                    if not usid or rebanned or usid not in banned:
                        await db.users.update_one({"id": uu["id"]}, {"$unset": {"native_unban_pending": ""}})
                        continue
                    if await asyncio.to_thread(native_bans.remove_ban, usid):
                        await db.users.update_one({"id": uu["id"]}, {"$unset": {"native_unban_pending": ""}})
                        banned.discard(usid)
                        logger.info("[ban-enforcer] retried native unban sid=%s", usid)
                online, _ = await _rcon_online_players()
                if online:
                    # bounded by who is actually connected
                    to_kick = banned & online
                    for sid in to_kick:
                        try:
                            await _mod_kick(sid, "Sancion activa")
                            await rcon_client.kick(sid)
                            logger.info("[ban-enforcer] re-kicked banned sid=%s (mod+rcon)", sid)
                        except Exception as e:
                            logger.warning("[ban-enforcer] kick failed sid=%s err=%s", sid, e)
                    await _sweep_pending_kicks(online, tick)
        except Exception as e:
            logger.warning("[ban-enforcer] loop error: %s", e)
        tick += 1
        # 10s cadence rides the 10s-cached RCON player list — sanctions land within
        # seconds of a player spawning, at no extra RCON cost.
        await asyncio.sleep(10)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    try:
        # Nublar Spin (ADDITIVE): history seek index + the gen0_state steam_id
        # unique index the vial's race-safety rests on. Never blocks boot.
        await wheel_routes.ensure_indexes()
    except Exception as e:
        logging.getLogger("laislanublar.wheel").warning("ensure_indexes: %r", e)
    try:
        # web_bans (ADDITIVE collection): the gate's seek index + the op_ref
        # idempotency guarantee. Never blocks boot: without it the gate still
        # answers (a scan of a tiny collection) and the tab still works.
        await webban.ensure_indexes()
    except Exception:
        logger.warning("web_bans index init skipped", exc_info=True)
    await seed()
    # Hand the vault the running loop so its sync (threadpool) handlers can
    # schedule the background park/redeem confirmation coroutines onto it.
    vault.set_loop(asyncio.get_running_loop())
    try:
        await asyncio.to_thread(vault.ensure_custom_name_column)
    except Exception:
        logger.warning("vault custom_name schema upgrade skipped", exc_info=True)
    try:
        await asyncio.to_thread(vault.ensure_prime_state_columns)
    except Exception:
        logger.warning("vault prime-state schema upgrade skipped", exc_info=True)
    try:
        # Park never-lose (2026-07-30): recovery_id column + index. Must run
        # before the drain loop arms — the drain refuses to promote without it.
        await asyncio.to_thread(vault.ensure_recovery_id_column)
    except Exception:
        logger.warning("vault recovery_id schema upgrade skipped", exc_info=True)
    try:
        pop_control.ensure_settings()
    except Exception:
        logger.warning("pop_control settings init skipped", exc_info=True)
    try:
        # SkinKeeper: ensure the canonical skin_last_applied table from the web
        # boot too (either process may boot first). Byte-identical DDL to the bot.
        skinkeeper_web.ensure_web()
    except Exception:
        logger.warning("skinkeeper table init skipped", exc_info=True)
    asyncio.create_task(roll_loop())
    asyncio.create_task(crash_game.run_crash_loop())
    asyncio.create_task(amber_payout_loop())
    asyncio.create_task(patreon_creator_reconcile_loop())
    asyncio.create_task(patreon_amber_audit_loop())
    asyncio.create_task(streamer_repost_loop())
    asyncio.create_task(patreon_resync_loop())
    asyncio.create_task(primemeat_payout_loop())
    asyncio.create_task(visit_poi_tracker_loop())
    asyncio.create_task(leaderboard_maintenance_loop())
    asyncio.create_task(ban_enforcer_loop())
    asyncio.create_task(dino_snapshot_loop())
    asyncio.create_task(save_corrupt_rescue_loop())
    # Park never-lose journal drain: startup + every 5 min (logs an ARMED line).
    asyncio.create_task(vault.park_unsaved_drain_loop())
    # Stale redeem sweep: startup + every 2 min. Without it a leftover
    # row waits for its owner to open the site (logs an ARMED line).
    asyncio.create_task(vault.redeem_pending_sweep_loop())
    if game_telemetry.is_configured():
        asyncio.create_task(population_telemetry_loop())
    # Creator Program (2026-08-17): indexes never block boot; the close loop
    # pays month champions claim-gated; the sweep validates pending referrals
    # once the referred player has really played (logs its rewards).
    try:
        await _cp_ensure_indexes()
    except Exception:
        logger.warning("creator program index init skipped", exc_info=True)
    asyncio.create_task(creator_monthly_close_loop())
    asyncio.create_task(creator_pending_sweep_loop())
    # GEN-Ø facility infection tracker (2026-08-21): logs its own ARMED line;
    # GEN0_ENABLED=0 in .env retires it without a code change.
    asyncio.create_task(gen0_infection.gen0_tracker_loop())
    # Cementerio & Fósiles (2026-06): índices + semilla demo del cementerio.
    try:
        await _cem_ensure_indexes()
        await _cem_seed_demo()
    except Exception:
        logger.warning("[cemetery] startup init skipped", exc_info=True)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
