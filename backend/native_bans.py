"""Game-native ban file writer for The Isle: Evrima (moderation strikes).

The Isle stores its authoritative ban list in ``<Saved>/PlayerData/PlayerBans.json``
as a UTF-16 document ``{"bannedPlayerData": [ {steamId, playerName, banReason,
bannedTime, endBanTime, bannerName, bannerSteamId}, ... ]}``. This is the ONLY file
that carries a per-ban expiry (``endBanTime``) and durably blocks reconnection —
RCON ban (0x20) is permanent-only and does not reliably pre-block a live reconnect.

We read-modify-write that file atomically (preserving the game's UTF-16 encoding),
mirroring the proven FangsAndFerns bot lane. Timestamps use the game's
``%Y.%m.%d-%H.%M.%S`` format in server-local naive time (matching how the game writes
them). A permanent ban uses the ``9999.12.31-23.59.59`` sentinel.

Timezone note: the web backend enforces timed bans primarily by RE-KICKING banned
players (see server.ban_enforcer_loop) using active_banned_ids(), which compares the
endBanTime we wrote against our OWN datetime.now() — so enforcement is self-consistent
regardless of how Evrima interprets the string. If the game reads endBanTime in a
different zone, the worst case is the game under-blocks (thinks expired early) and our
re-kick loop still enforces the real window; it never over-bans an innocent player.

Design guards (moderation touches the game's authoritative ban file on a shared box):
 * Every mutation is sync and MUST be dispatched via asyncio.to_thread from the async
   layer — the blocking file IO + os.replace retry runs off the event loop.
 * A module-level lock serialises the web's own concurrent writers (to_thread runs them
   on separate threads) and shrinks the read->replace window vs the game.
 * A present-but-UNREADABLE file (locked / mid-write / non-strict JSON) is NEVER
   overwritten — add_ban/remove_ban/prune abort rather than clobber existing (possibly
   game-authored) bans. Only a genuinely-missing file is treated as empty.
 * Foreign entries whose endBanTime we cannot parse are left untouched and are NOT
   force-kicked (the game owns those).
"""
import json
import os
import threading
import logging
from datetime import datetime, timedelta

import game_ipc

logger = logging.getLogger("laislanublar.native_bans")

PLAYER_BANS_JSON = os.environ.get("LIN_PLAYER_BANS_JSON") or os.path.join(
    game_ipc.SAVED_DIR, "PlayerData", "PlayerBans.json"
)

_GAME_TS_FMT = "%Y.%m.%d-%H.%M.%S"
_PERMANENT_END = "9999.12.31-23.59.59"

# Serialises this process's own read-modify-write cycles (to_thread => real threads).
_lock = threading.Lock()


def _fmt(dt: datetime) -> str:
    return dt.strftime(_GAME_TS_FMT)


def _safe_field(v) -> str:
    """A string safe to put in ANY field of a native ban entry.

    THE FENCE IS A BYTE SCANNER, NOT A JSON PARSER. BanSpawnGuard in
    mod/lua/LaIslaNublarDataMod/Scripts/main.full.lua reads this file as RAW BYTES
    and strips every NUL before block-matching a Lua pattern:

        local f = io.open(path, "rb")          -- :15683
        return (s:gsub("%z", ""))              -- :15687   every NUL removed
        for block in native:gmatch("{[^{}]*}") -- :15753

    A literal { or } inside any string field therefore breaks block matching, and
    the consequence is not a parse error - it is the whole entry going INVISIBLE,
    so the banned player reconnects freely while every gate reports success.

    ★AND THE BRACE DOES NOT HAVE TO BE IN THE STRING. This file is UTF-16, so a
    codepoint whose UTF-16LE byte pair contains 0x7B SYNTHESISES a "{" in the
    fence's NUL-stripped view even though the Python string holds no brace at all:
    Ż U+017B (7B 01), ѻ U+047B (7B 04), the entire U+7B00-U+7BFF CJK row (xx 7B),
    ｻ U+FF7B (7B FF), emoji U+1F37B / U+1F47B, and 17,000+ more. The synthesised
    brace lands AFTER "steamId", so the block the fence matches starts there and
    carries no steamId - the ban does nothing. 0x7D is the mirror image: it closes
    the block EARLY, "endBanTime" falls outside it, and main.full.lua:15744 reads
    an absent endBanTime as `return true` - a TIMED ban silently becomes PERMANENT.
    Stripping braces after the fact cannot help; there is no brace to strip.

    THE INPUT IS ATTACKER-CONTROLLED AND REFRESHES ON EVERY LOGIN. player_name is
    the player's own Steam persona name (server.py:802/:813), passed here from
    server.py:8536, :8707, :8723, :8950 and :11851 (the unattended enforcer loop).
    A player renames themselves and walks back in. There is no second net: the
    fence's other source, banned_players.json (main.full.lua:15751), has no writer
    anywhere in this backend.

    ★WHY THIS OWNER DOES NOT STRIP ALL NON-ASCII. The fleet-canonical form
    (theisle-framework/webcore/nativebans.py::_safe_field) removes every non-ASCII
    character. That is safe but LOSSY, and this owner is Spanish: server.py:11851
    writes "Sanción (auto-sync)", which that form would file as "Sancin". The
    surgical form below removes ONLY the codepoints that can synthesise a brace,
    which is strictly stronger than the .replace() line it replaced and leaves
    every accent, every ñ and every Cyrillic name byte-identical.

    ★THE THREE-PASS ORDER IS LOAD-BEARING, all three ways:
      1. non-printable -> SPACE. Dropping the newline out of "spawn killing\\n
         second offence" welds two words together and quietly changes what a
         moderator wrote. It must become a space, never nothing.
      2. it also runs first because a LONE SURROGATE (category Cs, not printable,
         and reachable - json.loads accepts "\\ud800" straight out of a request
         body) makes .encode("utf-16-le") in pass 3 RAISE. Today that exception
         escapes _write_doc, add_ban swallows it, and the ban is silently never
         written at all. Pass 1 turns it into a space before pass 3 can see it.
      3. brace-synthesising -> REMOVED. This subsumes the old
         .replace("{","(").replace("}",")") entirely: U+007B encodes 7B 00 and
         U+007D encodes 7D 00, so a literal brace is caught by the same filter.
    """
    text = "".join(c if c.isprintable() else " " for c in str(v))
    return "".join(c for c in text
                   if 0x7B not in c.encode("utf-16-le")
                   and 0x7D not in c.encode("utf-16-le"))


def _end_state(end_str):
    """Classify an endBanTime: ('permanent', None) | ('timed', dt) | ('unknown', None).
    'unknown' = a foreign string we cannot parse (leave the game to own it)."""
    s = str(end_str or "").strip()
    if not s or s.startswith("9999"):
        return ("permanent", None)
    try:
        return ("timed", datetime.strptime(s, _GAME_TS_FMT))
    except (ValueError, TypeError):
        return ("unknown", None)


def _read_doc():
    """Return (doc, encoding, status). status ∈ {"ok","missing","unreadable"}.
    CRUCIAL: a present-but-unparseable file with ACTUAL content (game mid-write / lock /
    non-strict JSON) is reported as 'unreadable' — distinct from a genuinely-missing file
    — so callers never overwrite live ban data they merely failed to read. An empty /
    whitespace / BOM-only file counts as 'missing' (no bans, safe to write) — NOT
    'unreadable' (which would permanently refuse all native bans)."""
    if not os.path.exists(PLAYER_BANS_JSON):
        return {"bannedPlayerData": []}, "utf-16", "missing"
    try:
        raw = open(PLAYER_BANS_JSON, "rb").read()
    except OSError:
        return {"bannedPlayerData": []}, "utf-16", "unreadable"
    if not raw.strip():  # 0-byte / whitespace-only == no bans, safely writable
        return {"bannedPlayerData": []}, "utf-16", "missing"
    for enc in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            text = raw.decode(enc)
        except (UnicodeError, ValueError):
            continue
        if not text.strip():  # decoded to nothing (BOM-only) == no bans
            return {"bannedPlayerData": []}, "utf-16", "missing"
        try:
            doc = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(doc, dict):
            doc.setdefault("bannedPlayerData", [])
            return doc, enc, "ok"
    return {"bannedPlayerData": []}, "utf-16", "unreadable"


def _write_doc(doc: dict) -> None:
    """Atomically write PlayerBans.json in the game's canonical UTF-16 (never drift to
    another encoding). os.replace is atomic; if the game momentarily holds the file
    (Windows share lock) the replace can raise PermissionError — retry with backoff.

    ★ensure_ascii=True IS THE SECOND HALF OF THE BRACE FIX, and it covers the half
    _safe_field cannot reach. _safe_field only touches the fields WE fill. This is a
    read-modify-write over a file the GAME also writes: an in-game admin banning a
    player whose persona carries U+017B lands a row that is invisible to the fence
    the moment the game writes it, and every rewrite we did preserved that codepoint
    verbatim. With ensure_ascii=True json emits \\u017b - six ASCII bytes, none of
    them 0x7B - so the hostile codepoint can no longer synthesise a brace no matter
    which author put it there, and the enforcer loop (server.py:11851) REPAIRS those
    rows as a side effect of its next write. It is lossless (a \\uXXXX escape is
    standard JSON, parses back to the identical string, and the file stays UTF-16),
    so no name or reason is altered - only its on-disk spelling.

    Both halves ship because neither covers the other: ensure_ascii does not escape
    a literal ASCII "{" (JSON has no reason to), and _safe_field does not reach
    foreign rows."""
    import time as _t
    os.makedirs(os.path.dirname(PLAYER_BANS_JSON), exist_ok=True)
    tmp = PLAYER_BANS_JSON + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-16") as f:
            json.dump(doc, f, ensure_ascii=True, indent=2)
    except Exception:
        try: os.remove(tmp)
        except OSError: pass
        raise
    last = None
    for _ in range(10):
        try:
            os.replace(tmp, PLAYER_BANS_JSON)
            return
        except PermissionError as e:
            last = e
            _t.sleep(0.2)
    try:
        os.remove(tmp)
    except OSError:
        pass
    raise last if last else RuntimeError("PlayerBans.json replace failed")


def is_available() -> bool:
    """True only when the game Saved dir exists on this box (guards against silently
    materialising a bogus ban tree if the path is misconfigured)."""
    try:
        return os.path.isdir(game_ipc.SAVED_DIR)
    except OSError:
        return False


def _entry(steamid, reason, hours, player_name, banner_name, banner_steamid) -> dict:
    """One native ban entry.

    steamId is deliberately NOT put through _safe_field: it is the IDENTITY KEY that
    add_ban, remove_ban, active_banned_ids and list_bans all match on, and
    normalising it on write but not on the compare would leave an unban matching
    nothing. Every live call site already guarantees digits - server.py:8915
    _internal_sid rejects anything that is not exactly 17 digits, and the other four
    (:8536, :8707, :8723, :11851) read steam_id off a Steam-OpenID user document.
    bannerSteamId has no such guarantee (server.py:8951 passes InternalModInput.by_sid
    straight through) and is pure payload the fence never matches on, so it goes
    through the sanitiser - which is identity for any real SteamID64.
    """
    now = datetime.now()
    if hours and int(hours) > 0:
        try:
            end = _fmt(now + timedelta(hours=int(hours)))
        except OverflowError:
            end = _PERMANENT_END
    else:
        end = _PERMANENT_END
    return {
        "steamId": str(steamid),
        "playerName": _safe_field(player_name or "Unknown"),
        "banReason": _safe_field(reason or "Rule violation"),
        "bannedTime": _fmt(now),
        "endBanTime": end,
        "bannerName": _safe_field(banner_name or "La Isla Nublar"),
        "bannerSteamId": _safe_field(banner_steamid or ""),
    }


def add_ban(steamid, reason="Rule violation", hours=0, player_name="Unknown",
            banner_name="La Isla Nublar", banner_steamid="") -> bool:
    """Add / refresh a native ban entry (dedup-by-sid REPLACE so an escalated tier's
    endBanTime takes effect). hours<=0 => permanent. Returns True on a successful write.
    Aborts (returns False) rather than clobber when the file exists but is unreadable."""
    sid = str(steamid or "").strip()
    if not sid or not is_available():
        return False
    with _lock:
        try:
            doc, _enc, status = _read_doc()
            if status == "unreadable":
                logger.warning("add_ban abort: PlayerBans.json present but unreadable sid=%s", sid)
                return False
            arr = [b for b in (doc.get("bannedPlayerData") or [])
                   if str(b.get("steamId")) != sid]
            arr.append(_entry(sid, reason, hours, player_name, banner_name, banner_steamid))
            doc["bannedPlayerData"] = arr
            _write_doc(doc)
            return True
        except Exception as e:
            logger.warning("add_ban failed sid=%s err=%s", sid, e)
            return False


def remove_ban(steamid) -> bool:
    """Remove a sid from the native ban file (the file-level 'unban'). Returns True if
    an entry was removed. Aborts on an unreadable file (never clobbers)."""
    sid = str(steamid or "").strip()
    if not sid or not is_available():
        return False
    with _lock:
        try:
            doc, _enc, status = _read_doc()
            if status == "unreadable":
                logger.warning("remove_ban abort: PlayerBans.json unreadable sid=%s", sid)
                return False
            arr = doc.get("bannedPlayerData") or []
            new = [b for b in arr if str(b.get("steamId")) != sid]
            if len(new) == len(arr):
                return False
            doc["bannedPlayerData"] = new
            _write_doc(doc)
            return True
        except Exception as e:
            logger.warning("remove_ban failed sid=%s err=%s", sid, e)
            return False


def active_banned_ids() -> set:
    """Set of Steam64 ids under an active native ban (permanent, or timed & not yet
    expired). Foreign entries with an unparseable endBanTime are skipped — the game owns
    those and we must not force-kick on a format we don't understand."""
    now = datetime.now()
    out = set()
    try:
        with _lock:  # read under the same lock writers hold (avoid racing os.replace)
            doc, _enc, status = _read_doc()
        if status == "unreadable":
            return out
        for b in doc.get("bannedPlayerData") or []:
            sid = str(b.get("steamId") or "").strip()
            if not sid:
                continue
            state, dt = _end_state(b.get("endBanTime"))
            if state == "permanent" or (state == "timed" and dt > now):
                out.add(sid)
    except Exception as e:
        logger.warning("active_banned_ids failed err=%s", e)
    return out


def list_bans() -> list[dict]:
    """Read-only snapshot of every native entry with a parsed activity flag, for the
    Discord /banlist view. Foreign entries with an unparseable endBanTime report
    active=None (the game owns those; we display them without claiming a state)."""
    now = datetime.now()
    out = []
    try:
        with _lock:
            doc, _enc, status = _read_doc()
        if status == "unreadable":
            return out
        for b in doc.get("bannedPlayerData") or []:
            sid = str(b.get("steamId") or "").strip()
            if not sid:
                continue
            state, dt = _end_state(b.get("endBanTime"))
            active = True if state == "permanent" else (dt > now if state == "timed" else None)
            out.append({
                "steam_id": sid,
                "player_name": str(b.get("playerName") or ""),
                "reason": str(b.get("banReason") or ""),
                "banner": str(b.get("bannerName") or ""),
                "end": str(b.get("endBanTime") or ""),
                "permanent": state == "permanent",
                "active": active,
            })
    except Exception as e:
        logger.warning("list_bans failed err=%s", e)
    return out


def prune_expired() -> int:
    """Drop entries WE understand to be expired (timed & past). Permanent and foreign
    (unparseable) entries are kept. Returns the number removed. Aborts on unreadable."""
    now = datetime.now()
    with _lock:
        try:
            doc, _enc, status = _read_doc()
            if status != "ok":
                return 0
            arr = doc.get("bannedPlayerData") or []
            kept = []
            for b in arr:
                state, dt = _end_state(b.get("endBanTime"))
                if state == "timed" and dt <= now:
                    continue  # our lapsed temporary ban
                kept.append(b)
            removed = len(arr) - len(kept)
            if removed:
                doc["bannedPlayerData"] = kept
                _write_doc(doc)
            return removed
        except Exception as e:
            logger.warning("prune_expired failed err=%s", e)
            return 0
