# -*- coding: utf-8 -*-
"""BANEOS DE LA PÁGINA WEB — la pestaña "Baneos" del panel de admin (2026-08-17).

    "for every owner website lets add a ban sub tab on their admin tab. they
     should be able to type the persons website name, a drop down menu should
     appear, and they should be able to ban them from website. steam id should
     work too ... make it as player friendly as possible."   — the owner, 2026-08-17

WHAT THIS IS
  La Isla Nublar's port of the framework's website-ban console
  (theisle-framework/webcore: banadmin.py store semantics, bangate.py
  enforcement posture, playerfind.py name search, admin.mjs BANSADMIN flow).
  Same semantics, this site's own architecture: FastAPI + Motor on the web's
  own MongoDB, mounted like battle_pass.py / crash_game.py — this module NEVER
  imports server.py; the Mongo handle and the auth dependencies arrive through
  ``configure()`` beside the router include.

THE STORE — ``web_bans`` (ADDITIVE: a new collection, no existing collection's
  shape is touched). One document per ban:
    id, steam_id, player_name, reason, banned_by_sid, banned_by_name,
    banned_at, expires_at (None = para siempre), lifted_at, lifted_by, op_ref
    (UNIQUE ``webban:<op_id>`` — the idempotency key), created_at, updated_at.
  THE ROW IS THE TRUTH. Expiry is COMPUTED against ``now`` on every read and
  never swept — a stopped background job can never leave somebody banned.
  Two moderators, one incident: the LONGER window is kept and said out loud
  (``folded_kept_longer``); a longer one supersedes (``escalated``).

THE GATE — ``check()`` runs INSIDE server.py's ``get_current_user`` (the ONE
  place a bearer token becomes a user, every ``Depends(get_current_user)`` route
  goes through it) and inside the Steam callback BEFORE a token is minted, and
  inside the crash game's websocket auth. A banned account's session is refused
  with the plain-words sentence in ``message()``; a fresh sign-in is refused
  with the same words. Per-account TTL cache (45 s) + ``forget()`` on place and
  lift, so a ban is enforced on the NEXT request in this process. FAIL-OPEN on a
  store fault (a sign-in path that failed closed would sign everyone out on a
  Mongo hiccup) but COUNTED — ``faults()`` rides the overview and the tab says
  so, per the fail-open-guard-that-always-fires law.

ARM, THEN CONFIRM — ON THE SERVER. The first ``/admin/bans/place`` press (no
  ``confirm``) runs every gate, writes NOTHING and files an ARM keyed on the
  page's ``op_id`` + a fingerprint of the payload; the second press (``confirm:
  true``) SPENDS that arm. A confirm with no matching arm — a replayed curl, a
  stale page, a payload that drifted from the preview — is refused. Self-ban and
  owner-ban are refused before anything else.

WHO — owners only (``get_owner_user``: staff_rank owner or ADMIN_STEAM_IDS).

WHAT LEAVES THIS PROCESS. Every surface here is owner-gated, so rows carry the
  full SteamID64 (a masked id would make the pick unusable). Nothing here is
  ever handed to a non-owner.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

log = logging.getLogger("webban")

# =============================================================================
# shapes and bounds (mirror webcore/banadmin.py + playerfind.py)
# =============================================================================
COLLECTION = "web_bans"
OP_PREFIX = "webban:"
#: The page's idempotency key. Opaque; only its shape matters.
OP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
STEAM64_RE = re.compile(r"^7656119\d{10}$")
#: A moderator's words, shown to the banned player. Bounded, single-line.
REASON_MAX = 100
#: 87600 hours is ten years — past it, say permanent and mean it.
HOURS_MAX = 87600
LIST_LIMIT = 25
LIST_SCAN = 200
#: Fixed-width UTC. Lexicographic order IS chronological order at this width.
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"
#: The arm window: a preview is good for ten minutes, then the page asks again.
ARM_TTL_SECONDS = 600.0
ARM_MAX = 4096
#: The gate's per-account cache. Short enough that a ban placed by ANOTHER
#: process lands within a minute; the console's own forget() makes this
#: process's bans immediate.
CACHE_TTL_SECONDS = 45.0
FAULT_TTL_SECONDS = 5.0
CACHE_CAP = 8192
WARN_EVERY = 50
#: The drop-down: how many people one answer may name, how many each source may
#: contribute before the merge, how long a typed query may be.
SUGGEST_LIMIT = 8
PER_SOURCE = 32
QUERY_MAX = 64
NAME_MAX = 64
ALT_MAX = 2
DECORATE_MAX = 200
BUSY_TIMEOUT = 1.5

# =============================================================================
# the injected host: mongo handle, owner list, auth deps, audit
# =============================================================================
_db = None
_owner_ids = frozenset()
_current_user_dep = None
_owner_user_dep = None
_add_log = None
_bot_db_path = ""
_security = HTTPBearer(auto_error=False)


def configure(mongo_db, *, owner_ids, current_user_dep, owner_user_dep,
              add_log=None, bot_db_path: str = "") -> None:
    """One-shot dependency injection from server.py, beside the router include.
    Importable (and unit-testable) with no host at all."""
    global _db, _owner_ids, _current_user_dep, _owner_user_dep, _add_log, _bot_db_path
    _db = mongo_db
    _owner_ids = frozenset(clean_sid(o) for o in (owner_ids or ()) if clean_sid(o))
    _current_user_dep = current_user_dep
    _owner_user_dep = owner_user_dep
    _add_log = add_log
    _bot_db_path = str(bot_db_path or "")


def _col():
    if _db is None:
        raise HTTPException(status_code=503, detail=REASONS["db_not_configured"][1])
    return _db[COLLECTION]


async def ensure_indexes() -> None:
    """Additive indexes on the NEW collection only. The gate's read is one index
    seek on (steam_id, lifted_at); op_ref is the idempotency guarantee."""
    if _db is None:
        return
    col = _db[COLLECTION]
    await col.create_index([("steam_id", 1), ("lifted_at", 1)], name="webban_open_by_sid")
    await col.create_index("op_ref", name="webban_op_ref", unique=True, sparse=True)
    await col.create_index([("lifted_at", 1), ("banned_at", -1)], name="webban_active_recent")
    await col.create_index([("updated_at", -1)], name="webban_updated")


# =============================================================================
# time + cleaners
# =============================================================================

def _stamp(now) -> float:
    return time.time() if now is None else float(now)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime(ISO_FMT)


def parse_iso(text) -> Optional[float]:
    """A stored stamp back to unix seconds, or None when it is not one. A cell
    we cannot parse is NOT treated as expired — None flows to callers as "no
    computable end" and every one of them treats that as still banned."""
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, ISO_FMT).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def clean_sid(raw) -> str:
    """A SteamID64 or "". Spaces inside a pasted id are tolerated, nothing else."""
    text = str(raw or "").strip().replace(" ", "")
    return text if STEAM64_RE.match(text) else ""


def _printable(raw) -> str:
    text = "".join(ch if ch.isprintable() else " " for ch in str(raw or ""))
    return " ".join(text.split())


def clean_reason(raw) -> str:
    """Bounded, single-line, printable. A control character becomes a SPACE,
    never nothing — dropping a newline welds two words the moderator wrote."""
    return _printable(raw)[:REASON_MAX].strip()


def reason_too_long(raw) -> bool:
    """The gate's own check, on the UNTRUNCATED cleaned text: a reason past the
    bound is refused with a sentence, never silently cut."""
    return len(_printable(raw)) > REASON_MAX


def clean_name(raw) -> str:
    text = "".join(ch if ch.isprintable() else " " for ch in str(raw or ""))
    return " ".join(text.split())[:NAME_MAX].strip()


def clean_query(raw) -> str:
    return clean_name(raw)[:QUERY_MAX]


def clean_hours(raw) -> tuple[Optional[int], str]:
    """(hours, reason). None hours means PERMANENT. 0/None/"" are permanent;
    anything else must land in 1..HOURS_MAX."""
    if raw is None or raw == "":
        return None, "ok"
    if isinstance(raw, bool):
        return None, "bad_hours"
    try:
        span = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None, "bad_hours"
    if isinstance(raw, float) and float(raw) != span:
        return None, "bad_hours"
    if span == 0:
        return None, "ok"
    if span < 0 or span > HOURS_MAX:
        return None, "bad_hours"
    return span, "ok"


def _end_iso(start: float, hours) -> Optional[str]:
    return None if hours is None else iso(start + int(hours) * 3600)


def _tail(value) -> str:
    text = str(value or "")
    return text[-4:] if len(text) >= 4 else ""


def _is_longer(new_end: Optional[str], old_end) -> bool:
    """Does the NEW window outlast the OLD one? None is permanent and therefore
    longest. An OLD end we cannot parse is treated as LONGER (keep it)."""
    if new_end is None:
        return old_end is not None
    if old_end is None:
        return False
    old = parse_iso(old_end)
    if old is None:
        return False
    new = parse_iso(new_end)
    return new is not None and new > old


# =============================================================================
# the words — refusals (HTTP) and the sentence a banned player reads
# =============================================================================
#: reason -> (status, plain-Spanish sentence). Every refusal this lane can
#: produce is named here; an unmapped reason lands as a 400 with the generic
#: line rather than a traceback.
REASONS = {
    "bad_steam_id": (400, "Eso no es un Steam ID. Debe tener 17 dígitos y empezar por 7656."),
    "bad_op_id": (400, "La solicitud venía mal formada. Recarga la página e inténtalo otra vez."),
    "bad_reason": (400, f"El motivo puede tener como máximo {REASON_MAX} caracteres."),
    "bad_hours": (400, f"Indica un número entero de horas entre 1 y {HOURS_MAX:,}, o déjalo vacío para un baneo permanente."),
    "self_ban": (409, "No puedes banearte a ti mismo."),
    "owner_ban": (409, "Esa cuenta es de un dueño (Owner) y no se puede banear desde aquí."),
    "not_banned": (404, "Esa cuenta no está baneada."),
    "not_armed": (409, "No se baneó a nadie. Revisa la vista previa otra vez y luego confirma."),
    "duplicate_gone": (409, "Ese baneo no se pudo confirmar. Recarga la página antes de intentarlo de nuevo."),
    "db_not_configured": (503, "Esta página no está conectada a la lista de baneos."),
    "db_unreadable": (503, "La lista de baneos no se pudo leer ahora mismo. No se cambió nada."),
    "db_unwritable": (503, "La lista de baneos no se pudo guardar ahora mismo. No se cambió nada."),
}
GENERIC = "Eso no funcionó, y no se cambió nada."


def _refuse(reason: str) -> HTTPException:
    status, text = REASONS.get(str(reason), (400, GENERIC))
    return HTTPException(status_code=status, detail=text)


_MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def until_text(row: Optional[dict]) -> str:
    """"hasta el 21 ago 2026, 14:05 UTC" or "" for a permanent ban."""
    if not row or not row.get("expires_at"):
        return ""
    end = parse_iso(row.get("expires_at"))
    if end is None:
        return ""
    d = datetime.fromtimestamp(end, timezone.utc)
    return f"hasta el {d.day} {_MONTHS_ES[d.month - 1]} {d.year}, {d.hour:02d}:{d.minute:02d} UTC"


def message(row: Optional[dict]) -> str:
    """The sentence a banned player reads. Plain words, no ids, no jargon; the
    reason only when the moderator wrote one."""
    when = until_text(row)
    head = ("Esta cuenta está baneada de esta página web " + when + "."
            if when else "Esta cuenta está baneada de esta página web.")
    reason = str((row or {}).get("reason") or "").strip()
    if reason:
        head += " Motivo: " + reason + "."
    return head + " Si crees que es un error, habla con el staff del servidor."


# =============================================================================
# the arm table — the server's own memory of what was previewed
# =============================================================================
# ``confirm: true`` and ``op_id`` are both fields the CLIENT sets. If those were
# the only two things between a request and a ban, the two-step would be
# decoration: a stale page or a replayed curl would place the ban on its FIRST
# request and nobody ever saw what it would do. So the arm is a record HERE,
# in-process on purpose (a ten-minute handshake, not a fact about the world; a
# restart between preview and confirm loses the arm and the honest answer is
# "preview it again").
_ARM_LOCK = threading.Lock()
_ARMED: dict[str, tuple[str, str, float]] = {}


def arm_signature(*, steam_id, reason, hours, replace) -> str:
    """A fingerprint of EVERYTHING THAT CHANGES WHAT THE BAN DOES, every field
    normalised through the same cleaner the write uses. Joined on \\x1f, a byte
    clean_reason can never emit, so two splits of the same text cannot collide."""
    span, _why = clean_hours(hours)
    parts = "\x1f".join((
        clean_sid(steam_id),
        clean_reason(reason),
        "permanent" if span is None else str(int(span)),
        "replace" if replace else "fold",
    ))
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def _arm_prune(now: float) -> None:
    for key in [k for k, (_a, _s, ends) in _ARMED.items() if ends <= now]:
        _ARMED.pop(key, None)
    while len(_ARMED) > ARM_MAX:
        _ARMED.pop(next(iter(_ARMED)), None)


def arm_record(op_id, actor_sid, signature, now=None) -> bool:
    ref = str(op_id or "").strip()
    if not OP_ID_RE.match(ref):
        return False
    stamp = _stamp(now)
    with _ARM_LOCK:
        _ARMED.pop(ref, None)
        _ARMED[ref] = (clean_sid(actor_sid), str(signature or ""), stamp + ARM_TTL_SECONDS)
        _arm_prune(stamp)
    return True


def arm_take(op_id, actor_sid, signature, now=None) -> bool:
    """SPEND an arm. True exactly once per preview. A MISMATCH IS NOT A
    CONSUMPTION: the moderator can still confirm the ban they actually
    previewed."""
    ref = str(op_id or "").strip()
    stamp = _stamp(now)
    with _ARM_LOCK:
        _arm_prune(stamp)
        held = _ARMED.get(ref)
        if held is None:
            return False
        actor, sig, ends = held
        if ends <= stamp or actor != clean_sid(actor_sid) or sig != str(signature or ""):
            return False
        _ARMED.pop(ref, None)
        return True


def arm_clear() -> None:
    with _ARM_LOCK:
        _ARMED.clear()


def arm_size() -> int:
    with _ARM_LOCK:
        return len(_ARMED)


# =============================================================================
# the gate's cache + fault counter
# =============================================================================
_CACHE: dict[str, tuple[float, bool, Optional[dict]]] = {}
_CACHE_LOCK = threading.Lock()
_FAULTS = {"count": 0}


def _cache_get(sid: str, now: float):
    with _CACHE_LOCK:
        hit = _CACHE.get(sid)
        if hit is None:
            return None
        ends, banned, row = hit
        if ends <= now:
            _CACHE.pop(sid, None)
            return None
        return banned, row


def _cache_put(sid: str, banned: bool, row: Optional[dict], now: float, ttl: float) -> None:
    with _CACHE_LOCK:
        _CACHE.pop(sid, None)
        _CACHE[sid] = (now + ttl, banned, row)
        if len(_CACHE) > CACHE_CAP:
            for key in [k for k, (ends, _b, _r) in _CACHE.items() if ends <= now]:
                _CACHE.pop(key, None)
            while len(_CACHE) > CACHE_CAP:
                _CACHE.pop(next(iter(_CACHE)), None)


def forget(steam_id) -> None:
    """Drop one account's cached answer. Called after a place or a lift, so the
    change is enforced on the very next request in this process."""
    with _CACHE_LOCK:
        _CACHE.pop(clean_sid(steam_id) or str(steam_id or ""), None)


def cache_clear() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def faults() -> int:
    return int(_FAULTS.get("count") or 0)


def faults_reset() -> None:
    _FAULTS["count"] = 0


# =============================================================================
# reads
# =============================================================================

def _row_dict(doc: dict, *, now: float) -> dict:
    """One document as the console sees it (owner surface: full id)."""
    sid = str(doc.get("steam_id") or "")
    expires = doc.get("expires_at") or None
    end = parse_iso(expires)
    lifted = str(doc.get("lifted_at") or "")
    if lifted:
        state = "lifted"
    elif expires and end is not None and end <= now:
        state = "expired"
    else:
        state = "active"
    return {
        "id": str(doc.get("id") or ""),
        "steam_id": sid,
        "steam_tail": _tail(sid),
        "player_name": str(doc.get("player_name") or ""),
        "avatar": str(doc.get("avatar") or ""),
        "reason": str(doc.get("reason") or ""),
        "by_tail": _tail(doc.get("banned_by_sid")),
        "by_name": str(doc.get("banned_by_name") or ""),
        "banned_at": str(doc.get("banned_at") or ""),
        "expires_at": str(expires or "") or None,
        "permanent": not expires,
        "lifted_at": lifted or None,
        "lifted_by": str(doc.get("lifted_by") or "") or None,
        "state": state,
    }


async def _open_rows(sid: str) -> list[dict]:
    cur = _col().find({"steam_id": sid, "lifted_at": None}, {"_id": 0}).sort("banned_at", DESCENDING)
    return await cur.to_list(LIST_LIMIT)


async def is_banned_web(steam_id, now=None) -> tuple[Optional[dict], str]:
    """Is this account barred from the website RIGHT NOW? (row, reason).
    Reasons: ok (banned, row) / not_banned / bad_steam_id / db_*.
    CALLERS BRANCH ON THE REASON, never on the row being falsy: None with
    db_unreadable means WE DO NOT KNOW."""
    sid = clean_sid(steam_id)
    if not sid:
        return None, "bad_steam_id"
    if _db is None:
        return None, "db_not_configured"
    stamp = _stamp(now)
    try:
        rows = await _open_rows(sid)
    except Exception as exc:  # noqa: BLE001 - any store fault is one reason
        log.warning("web ban check failed (%s)", type(exc).__name__)
        return None, "db_unreadable"
    for doc in rows:
        expires = doc.get("expires_at") or None
        end = parse_iso(expires)
        if expires and end is not None and end <= stamp:
            continue
        return _row_dict(doc, now=stamp), "ok"
    return None, "not_banned"


async def check(steam_id, now=None, *, fresh: bool = False) -> tuple[bool, Optional[dict]]:
    """THE GATE. (banned, row). NEVER raises. Cached per account; a store fault
    answers NOT BANNED for a short window and is COUNTED."""
    sid = clean_sid(steam_id)
    if not sid or _db is None:
        return False, None
    stamp = _stamp(now)
    if not fresh:
        hit = _cache_get(sid, stamp)
        if hit is not None:
            return hit
    try:
        row, why = await is_banned_web(sid, stamp)
    except Exception:  # noqa: BLE001
        row, why = None, "gate_raised"
    if why == "ok" and row is not None:
        _cache_put(sid, True, row, stamp, CACHE_TTL_SECONDS)
        return True, row
    if why in ("not_banned", "bad_steam_id"):
        _cache_put(sid, False, None, stamp, CACHE_TTL_SECONDS)
        return False, None
    _FAULTS["count"] = int(_FAULTS.get("count") or 0) + 1
    count = _FAULTS["count"]
    if count == 1 or count % WARN_EVERY == 0:
        log.warning("website ban check could not read the store (%s) - answering NOT BANNED "
                    "for %ss; %d fault(s) so far", why, FAULT_TTL_SECONDS, count)
    _cache_put(sid, False, None, stamp, FAULT_TTL_SECONDS)
    return False, None


async def _active_doc(sid: str, stamp: float) -> Optional[dict]:
    for doc in await _open_rows(sid):
        expires = doc.get("expires_at") or None
        end = parse_iso(expires)
        if expires and end is not None and end <= stamp:
            continue
        return doc
    return None


async def list_active(now=None) -> list[dict]:
    stamp = _stamp(now)
    cur = _col().find({"lifted_at": None}, {"_id": 0}).sort("banned_at", DESCENDING)
    docs = await cur.to_list(LIST_SCAN)
    out = []
    for doc in docs:
        row = _row_dict(doc, now=stamp)
        if row["state"] == "active":
            out.append(row)
        if len(out) >= LIST_LIMIT * 2:
            break
    return out


async def list_history(now=None) -> list[dict]:
    """Past bans: lifted or expired, newest change first."""
    stamp = _stamp(now)
    query = {"$or": [{"lifted_at": {"$ne": None}},
                     {"expires_at": {"$ne": None, "$lte": iso(stamp)}}]}
    cur = _col().find(query, {"_id": 0}).sort("updated_at", DESCENDING)
    docs = await cur.to_list(LIST_LIMIT)
    return [_row_dict(d, now=stamp) for d in docs]


async def counts(now=None) -> dict:
    active = await list_active(now)
    total = await _col().count_documents({}, limit=100000)
    return {"active": len(active), "total": int(total)}


# =============================================================================
# gates + writes
# =============================================================================

async def _is_owner_account(sid: str) -> bool:
    """OWNER-BAN. The env owner list AND anyone the site itself ranks owner."""
    if sid in _owner_ids:
        return True
    if _db is None:
        return False
    try:
        doc = await _db.users.find_one({"steam_id": sid, "staff_rank": "owner"}, {"_id": 0, "id": 1})
    except Exception:  # noqa: BLE001 - a read fault must not let an owner ban through
        return True
    return doc is not None


async def _gates(*, steam_id, reason, op_id, hours, actor_sid) -> tuple[Optional[dict], str]:
    """Every shape and policy check, in one place and in a fixed order."""
    sid = clean_sid(steam_id)
    if not sid:
        return None, "bad_steam_id"
    ref = str(op_id or "").strip()
    if not OP_ID_RE.match(ref):
        return None, "bad_op_id"
    if reason_too_long(reason):
        return None, "bad_reason"
    words = clean_reason(reason)
    span, why = clean_hours(hours)
    if why != "ok":
        return None, why
    actor = clean_sid(actor_sid)
    if actor and actor == sid:
        return None, "self_ban"
    if await _is_owner_account(sid):
        return None, "owner_ban"
    return {"steam_id": sid, "op_id": ref, "reason": words, "hours": span, "actor": actor}, "ok"


async def preview_ban(*, steam_id, reason, op_id, hours=None, actor_sid="",
                      replace=False, now=None) -> tuple[Optional[dict], str]:
    """THE ARM STEP. Runs every gate and reports the outcome WITHOUT WRITING."""
    stamp = _stamp(now)
    fields, why = await _gates(steam_id=steam_id, reason=reason, op_id=op_id,
                               hours=hours, actor_sid=actor_sid)
    if fields is None:
        return None, why
    try:
        existing = await _active_doc(fields["steam_id"], stamp)
        replayed = await _col().find_one({"op_ref": OP_PREFIX + fields["op_id"]}, {"_id": 0, "id": 1})
    except Exception as exc:  # noqa: BLE001
        log.warning("preview_ban could not read the store (%s)", type(exc).__name__)
        return None, "db_unreadable"
    end = _end_iso(stamp, fields["hours"])
    if replayed is not None:
        outcome = "duplicate"
    elif existing is None:
        outcome = "placed"
    elif replace:
        outcome = "replaced"
    else:
        outcome = "escalated" if _is_longer(end, existing.get("expires_at")) else "folded_kept_longer"
    return {"outcome": outcome, "steam_id": fields["steam_id"], "steam_tail": _tail(fields["steam_id"]),
            "reason": fields["reason"], "expires_at": end, "permanent": end is None,
            "existing": _row_dict(existing, now=stamp) if existing else None}, "ok"


async def place_ban(*, steam_id, reason, op_id, hours=None, actor_sid="", actor_name="",
                    player_name="", avatar="", replace=False, now=None) -> tuple[Optional[dict], str]:
    """Place a ban. (result, reason). Reasons: ok (result["outcome"] placed /
    escalated / replaced / duplicate), folded_kept_longer (NOT a failure: the
    existing longer ban was kept), or a gate/store reason."""
    stamp = _stamp(now)
    fields, why = await _gates(steam_id=steam_id, reason=reason, op_id=op_id,
                               hours=hours, actor_sid=actor_sid)
    if fields is None:
        return None, why
    op_ref = OP_PREFIX + fields["op_id"]
    end = _end_iso(stamp, fields["hours"])
    col = _col()
    try:
        # 1. A REPLAY OF THIS EXACT PRESS WINS OUTRIGHT (idempotent success).
        replay = await col.find_one({"op_ref": op_ref}, {"_id": 0})
        if replay is not None:
            answer = _row_dict(replay, now=stamp)
            answer.update({"duplicate": True, "folded": False, "superseded_id": None, "outcome": "duplicate"})
            return answer, "ok"
        # 2. THE FOLD: the LONGER window wins unless the moderator said replace.
        existing = await _active_doc(fields["steam_id"], stamp)
        superseded = None
        if existing is not None:
            if not replace and not _is_longer(end, existing.get("expires_at")):
                answer = _row_dict(existing, now=stamp)
                answer.update({"duplicate": False, "folded": True, "superseded_id": None,
                               "outcome": "folded_kept_longer"})
                return answer, "folded_kept_longer"
            superseded = str(existing.get("id") or "")
            await col.update_one({"id": superseded, "lifted_at": None},
                                 {"$set": {"lifted_at": iso(stamp), "lifted_by": "superseded",
                                           "updated_at": iso(stamp)}})
        doc = {
            "id": uuid.uuid4().hex,
            "steam_id": fields["steam_id"],
            "player_name": clean_name(player_name)[:64] or None,
            "avatar": str(avatar or "")[:512] or None,
            "reason": fields["reason"],
            "banned_by_sid": fields["actor"] or None,
            "banned_by_name": clean_name(actor_name)[:64] or None,
            "banned_at": iso(stamp),
            "expires_at": end,
            "lifted_at": None,
            "lifted_by": None,
            "op_ref": op_ref,
            "created_at": iso(stamp),
            "updated_at": iso(stamp),
        }
        try:
            await col.insert_one(dict(doc))
        except DuplicateKeyError:
            # Two presses of the same op_id raced past the pre-check. The index
            # is the real guarantee; answer with the row that won.
            row = await col.find_one({"op_ref": op_ref}, {"_id": 0})
            if row is None:
                return None, "duplicate_gone"
            answer = _row_dict(row, now=stamp)
            answer.update({"duplicate": True, "folded": False, "superseded_id": None, "outcome": "duplicate"})
            return answer, "ok"
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("place_ban failed (%s)", type(exc).__name__)
        return None, "db_unwritable"
    answer = _row_dict(doc, now=stamp)
    answer.update({"duplicate": False, "folded": False, "superseded_id": superseded,
                   "outcome": ("replaced" if (superseded and replace) else "escalated" if superseded else "placed")})
    return answer, "ok"


async def lift_ban(steam_id, *, actor_sid="", actor_name="", now=None) -> tuple[Optional[dict], str]:
    """Lift EVERY open ban on an account. Idempotent and honest: lifting somebody
    who is not banned returns not_banned — never a fake success."""
    sid = clean_sid(steam_id)
    if not sid:
        return None, "bad_steam_id"
    stamp = _stamp(now)
    col = _col()
    by = clean_name(actor_name)[:64] or (("..." + _tail(actor_sid)) if clean_sid(actor_sid) else "staff")
    try:
        rows = await _open_rows(sid)
        if not rows:
            return None, "not_banned"
        res = await col.update_many({"steam_id": sid, "lifted_at": None},
                                    {"$set": {"lifted_at": iso(stamp), "lifted_by": by,
                                              "updated_at": iso(stamp)}})
    except Exception as exc:  # noqa: BLE001
        log.warning("lift_ban failed (%s)", type(exc).__name__)
        return None, "db_unwritable"
    if int(getattr(res, "modified_count", 0) or 0) == 0:
        return None, "not_banned"
    return {"steam_id": sid, "steam_tail": _tail(sid), "lifted": int(res.modified_count),
            "ids": [str(r.get("id") or "") for r in rows],
            "rows": [_row_dict(r, now=stamp) for r in rows]}, "ok"


# =============================================================================
# WHO IS THAT? — the drop-down's name search
# =============================================================================
# The website name the owner means is the Steam persona this site shows
# (users.persona_name), then the Discord name the site knows (discord_username),
# then the bot's own link table (accounts + identity_names, read-only sqlite) for
# people who linked Discord but never opened the website. Wildcards are literal
# (regex-escaped for Mongo, ESCAPE'd for LIKE), every source is a bounded read,
# and a source that cannot be read costs that source and never the answer.
# Ranking is boring on purpose: prefix beats contains, then most recent, then
# the name. Nothing fuzzy — a fuzzy match is a wrong player banned with
# confidence.

class _Book:
    __slots__ = ("people",)

    def __init__(self) -> None:
        self.people: dict[str, dict] = {}

    def add(self, sid, name, *, source, avatar="", last_seen=0.0, prefix=False, user_id="") -> None:
        sid = clean_sid(sid)
        label = clean_name(name)
        if not sid:
            return
        try:
            seen = max(0.0, float(last_seen or 0.0))
        except (TypeError, ValueError):
            seen = 0.0
        entry = self.people.get(sid)
        if entry is None:
            entry = {"steam_id": sid, "name": label, "alt_names": [], "avatar": "",
                     "sources": [], "last_seen": 0.0, "known": True, "user_id": "", "prefix": False}
            self.people[sid] = entry
        if source not in entry["sources"]:
            entry["sources"].append(source)
        if label:
            if not entry["name"]:
                entry["name"] = label
            elif (label.lower() != entry["name"].lower()
                  and label.lower() not in [a.lower() for a in entry["alt_names"]]
                  and len(entry["alt_names"]) < ALT_MAX):
                entry["alt_names"].append(label)
        if avatar and not entry["avatar"]:
            entry["avatar"] = str(avatar)
        if user_id and not entry["user_id"]:
            entry["user_id"] = str(user_id)
        if seen > entry["last_seen"]:
            entry["last_seen"] = seen
        if prefix:
            entry["prefix"] = True

    def ranked(self, limit: int) -> list[dict]:
        rows = list(self.people.values())
        rows.sort(key=lambda e: (0 if e["prefix"] else 1, -e["last_seen"], e["name"].lower(), e["steam_id"]))
        out = []
        for entry in rows[:limit]:
            shaped = dict(entry)
            shaped.pop("prefix", None)
            out.append(shaped)
        return out


def _seen_of(user: dict) -> float:
    for key in ("last_login", "created_at"):
        raw = user.get(key)
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw).timestamp()
            except ValueError:
                continue
    return 0.0


_USER_FIELDS = {"_id": 0, "id": 1, "steam_id": 1, "persona_name": 1, "discord_username": 1,
                "avatar": 1, "last_login": 1, "created_at": 1}


async def _web_by_name(book: _Book, fragment: str) -> None:
    if _db is None:
        return
    rx = re.escape(fragment)
    try:
        cur = _db.users.find({"$or": [{"persona_name": {"$regex": rx, "$options": "i"}},
                                      {"discord_username": {"$regex": rx, "$options": "i"}}]},
                             _USER_FIELDS).sort("last_login", DESCENDING)
        users = await cur.to_list(PER_SOURCE)
    except Exception as exc:  # noqa: BLE001
        log.warning("name search (web) failed (%s)", type(exc).__name__)
        return
    low = fragment.lower()
    for u in users:
        persona = str(u.get("persona_name") or "")
        discord = str(u.get("discord_username") or "")
        seen = _seen_of(u)
        if persona:
            book.add(u.get("steam_id"), persona, source="website", avatar=str(u.get("avatar") or ""),
                     last_seen=seen, prefix=persona.lower().startswith(low), user_id=str(u.get("id") or ""))
        if discord and low in discord.lower():
            book.add(u.get("steam_id"), discord, source="discord", avatar=str(u.get("avatar") or ""),
                     last_seen=seen, prefix=discord.lower().startswith(low), user_id=str(u.get("id") or ""))


async def _web_by_sid(book: _Book, sid: str) -> None:
    if _db is None:
        return
    try:
        u = await _db.users.find_one({"steam_id": sid}, _USER_FIELDS)
    except Exception as exc:  # noqa: BLE001
        log.warning("sid lookup (web) failed (%s)", type(exc).__name__)
        return
    if not u:
        return
    book.add(sid, str(u.get("persona_name") or ""), source="website", avatar=str(u.get("avatar") or ""),
             last_seen=_seen_of(u), user_id=str(u.get("id") or ""))
    if u.get("discord_username"):
        book.add(sid, str(u.get("discord_username")), source="discord", last_seen=_seen_of(u))


def _like(fragment: str) -> str:
    escaped = fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _bot_query(sql: str, args: tuple) -> list:
    """READ-ONLY, bounded, never raises. The bot's sqlite is a guest table."""
    path = str(_bot_db_path or "").strip()
    if not path:
        return []
    try:
        uri = "file:%s?mode=ro" % path.replace("\\", "/")
        conn = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT)
    except sqlite3.Error:
        return []
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def _bot_by_name_sync(fragment: str) -> list[dict]:
    like = _like(fragment.lower())
    rows = _bot_query(
        "SELECT a.steam_id AS steam_id, i.username AS username, i.display_name AS display_name, "
        "i.last_seen_at AS last_seen_at FROM identity_names i JOIN accounts a ON a.discord_id = i.discord_id "
        "WHERE a.steam_id IS NOT NULL AND (LOWER(i.username) LIKE ? ESCAPE '\\' "
        "OR LOWER(i.display_name) LIKE ? ESCAPE '\\') LIMIT ?",
        (like, like, PER_SOURCE))
    return [dict(r) for r in rows]


def _bot_by_sid_sync(sid: str) -> list[dict]:
    rows = _bot_query(
        "SELECT a.steam_id AS steam_id, i.username AS username, i.display_name AS display_name, "
        "i.last_seen_at AS last_seen_at FROM accounts a LEFT JOIN identity_names i ON i.discord_id = a.discord_id "
        "WHERE a.steam_id = ? LIMIT 2", (sid,))
    return [dict(r) for r in rows]


def _bot_seen(raw) -> float:
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


async def _bot_by_name(book: _Book, fragment: str) -> None:
    try:
        rows = await asyncio.to_thread(_bot_by_name_sync, fragment)
    except Exception:  # noqa: BLE001
        return
    low = fragment.lower()
    for r in rows:
        for key in ("display_name", "username"):
            name = str(r.get(key) or "")
            if name and low in name.lower():
                book.add(r.get("steam_id"), name, source="discord", last_seen=_bot_seen(r.get("last_seen_at")),
                         prefix=name.lower().startswith(low))


async def _bot_by_sid(book: _Book, sid: str) -> None:
    try:
        rows = await asyncio.to_thread(_bot_by_sid_sync, sid)
    except Exception:  # noqa: BLE001
        return
    for r in rows:
        name = str(r.get("display_name") or r.get("username") or "")
        book.add(sid, name, source="discord", last_seen=_bot_seen(r.get("last_seen_at")))


async def find(query, *, limit: int = SUGGEST_LIMIT) -> tuple[list[dict], str]:
    """Candidates for what a moderator typed. (people, kind): kind is ``steam``
    (a SteamID64 — ONE candidate, known False when no source has seen it),
    ``name`` (a fragment; up to limit people, best first), ``not_an_id`` (all
    digits and not a Steam ID) or ``empty``. Never raises."""
    bound = max(1, min(12, int(limit or SUGGEST_LIMIT)))
    text = clean_query(query)
    if not text:
        return [], "empty"
    book = _Book()
    sid = clean_sid(text)
    if sid:
        await _web_by_sid(book, sid)
        await _bot_by_sid(book, sid)
        if sid not in book.people:
            return [{"steam_id": sid, "name": "", "alt_names": [], "avatar": "", "sources": [],
                     "last_seen": 0.0, "known": False, "user_id": ""}], "steam"
        return book.ranked(1), "steam"
    if text.isdigit():
        return [], "not_an_id"
    await _web_by_name(book, text)
    await _bot_by_name(book, text)
    return book.ranked(bound), "name"


async def _decorate(rows: list[dict]) -> None:
    """Names/avatars for a whole list in ONE read of users, never one per row.
    A stored name wins (it is what the moderator saw when banning)."""
    if _db is None or not rows:
        return
    sids = []
    for r in rows:
        if r.get("steam_id") and r["steam_id"] not in sids:
            sids.append(r["steam_id"])
        if len(sids) >= DECORATE_MAX:
            break
    if not sids:
        return
    try:
        cur = _db.users.find({"steam_id": {"$in": sids}}, _USER_FIELDS)
        users = {u.get("steam_id"): u for u in await cur.to_list(len(sids))}
    except Exception:  # noqa: BLE001
        return
    for r in rows:
        u = users.get(r.get("steam_id"))
        if not u:
            continue
        if not r.get("player_name"):
            r["player_name"] = str(u.get("persona_name") or "")
        if not r.get("avatar"):
            r["avatar"] = str(u.get("avatar") or "")
        r["current_name"] = str(u.get("persona_name") or "")


# =============================================================================
# the routes — /api/admin/bans/* (owners only)
# =============================================================================
router = APIRouter()


async def _require_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_security)):
    if _current_user_dep is None:
        raise HTTPException(status_code=503, detail=REASONS["db_not_configured"][1])
    return await _current_user_dep(creds)


async def _require_owner(user=Depends(_require_user)):
    if _owner_user_dep is None:
        raise HTTPException(status_code=503, detail=REASONS["db_not_configured"][1])
    return await _owner_user_dep(user)


class PlaceIn(BaseModel):
    steam_id: str = ""
    player_name: str = ""
    avatar: str = ""
    reason: str = ""
    hours: Optional[Any] = None
    op_id: str = ""
    confirm: bool = False
    replace: bool = False


class LiftIn(BaseModel):
    steam_id: str = ""


def _limits() -> dict:
    return {"reason_max": REASON_MAX, "hours_max": HOURS_MAX, "suggest_max": SUGGEST_LIMIT}


async def _audit(actor: dict, action: str, target: str, meta: dict) -> None:
    if _add_log is None:
        return
    try:
        await _add_log(actor.get("persona_name") or "owner", action, target, meta)
    except Exception:  # noqa: BLE001 - the audit line must never cost the action
        log.warning("web ban audit line failed", exc_info=True)


@router.get("/admin/bans/overview")
async def bans_overview(owner=Depends(_require_owner)):
    """What the tab shows before anybody is looked up."""
    now = time.time()
    try:
        active = await list_active(now)
        history = await list_history(now)
        totals = {"active": len(active), "total": int(await _col().count_documents({}, limit=100000))}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("bans overview could not read the store (%s)", type(exc).__name__)
        # A 200 with available:false — the page renders an honest sentence
        # instead of looking broken when the store is only busy.
        return {"ok": True, "available": False, "message": REASONS["db_unreadable"][1],
                "counts": {}, "active": [], "history": [], "limits": _limits(),
                "gate_faults": faults()}
    await _decorate(active + history)
    return {"ok": True, "available": True, "counts": totals, "active": active,
            "history": [r for r in history if r["state"] != "active"],
            "limits": _limits(), "gate_faults": faults()}


@router.get("/admin/bans/suggest")
async def bans_suggest(q: str = "", owner=Depends(_require_owner)):
    """THE DROP-DOWN. Read-only, bounded end to end; each candidate says whether
    they are banned RIGHT NOW."""
    raw = str(q or "")[:QUERY_MAX]
    now = time.time()
    people, kind = await find(raw)
    for person in people:
        row, why = await is_banned_web(person["steam_id"], now)
        person["banned"] = why == "ok" and row is not None
        person["banned_until"] = (row or {}).get("expires_at") if person["banned"] else None
        person["banned_reason"] = (row or {}).get("reason", "") if person["banned"] else ""
    return {"ok": True, "kind": kind, "query": clean_query(raw), "people": people}


@router.post("/admin/bans/place")
async def bans_place(data: PlaceIn, owner=Depends(_require_owner)):
    """ARM, then CONFIRM. Without confirm NOTHING is written; with it, the arm
    is spent and the row lands. A confirm with no arm — or one whose payload no
    longer matches what was previewed — is refused."""
    actor = str(owner.get("steam_id") or "")
    now = time.time()
    common = dict(steam_id=data.steam_id, reason=data.reason, op_id=data.op_id,
                  hours=data.hours, actor_sid=actor, replace=bool(data.replace), now=now)
    signature = arm_signature(steam_id=data.steam_id, reason=data.reason, hours=data.hours,
                              replace=bool(data.replace))
    if not data.confirm:
        preview, reason = await preview_ban(**common)
        if preview is None:
            raise _refuse(reason)
        arm_record(data.op_id, actor, signature, now)
        return {"ok": True, "armed": True, "confirmed": False, "preview": preview}

    if not arm_take(data.op_id, actor, signature, now):
        # A REPLAY of a press that already placed a row is an idempotent success
        # (its arm was spent by the press that worked); a malformed payload gets
        # its own honest refusal. preview_ban is read-only and settles both.
        replay, why = await preview_ban(**common)
        if replay is None:
            raise _refuse(why)
        if replay.get("outcome") != "duplicate":
            raise _refuse("not_armed")

    result, reason = await place_ban(actor_name=str(owner.get("persona_name") or ""),
                                     player_name=data.player_name, avatar=data.avatar, **common)
    if reason not in ("ok", "folded_kept_longer"):
        raise _refuse(reason)
    # THE GATE LEARNS ON THE SPOT: whatever the outcome, the account's cached
    # answer is dropped so its very next request meets the ban.
    forget(data.steam_id)
    if reason == "folded_kept_longer":
        return {"ok": True, "confirmed": True, "folded": True, "ban": result,
                "message": "Ya tenía un baneo más largo, así que se mantuvo ese. No se acortó nada."}
    if not result.get("duplicate"):
        await _audit(owner, "web_ban", result.get("player_name") or result.get("steam_id"), {
            "steam_id": result.get("steam_id"), "reason": result.get("reason"),
            "expires_at": result.get("expires_at") or "para siempre",
            "outcome": result.get("outcome"), "ban_id": result.get("id")})
        log.info("web ban placed by ...%s -> ...%s (%s, %s)", actor[-4:], result["steam_tail"],
                 result.get("outcome"), "permanent" if result["permanent"] else result["expires_at"])
    return {"ok": True, "confirmed": True, "folded": False, "ban": result}


@router.post("/admin/bans/lift")
async def bans_lift(data: LiftIn, owner=Depends(_require_owner)):
    """Lift every open ban on an account. Idempotent and honest."""
    actor = str(owner.get("steam_id") or "")
    result, reason = await lift_ban(data.steam_id, actor_sid=actor,
                                    actor_name=str(owner.get("persona_name") or ""), now=time.time())
    if result is None:
        raise _refuse(reason)
    forget(data.steam_id)
    await _audit(owner, "web_unban", (result["rows"][0].get("player_name") if result["rows"] else "") or result["steam_id"],
                 {"steam_id": result["steam_id"], "lifted": result["lifted"]})
    log.info("web ban lifted by ...%s -> ...%s (%d row(s))", actor[-4:], result["steam_tail"], result["lifted"])
    return {"ok": True, **result}


def banned_redirect_url(frontend_url: str, row: Optional[dict]) -> str:
    """The Steam callback's answer for a banned account: back to the site with
    the plain-words sentence, and NO token minted."""
    return f"{str(frontend_url or '').rstrip('/')}/auth/callback?error=banned&msg={quote(message(row))}"
