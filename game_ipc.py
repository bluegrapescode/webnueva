"""Game-file IPC bridge for the La Isla Nublar web backend.

The La Isla Nublar box runs the SAME forked game mod as the Discord bot, so the
on-disk protocol here is byte-identical to the bot's ``mod_ipc.py`` /
``helpers.py``:

  * commands.json    -> BARE JSON ARRAY, one command dict per element, each
                        stamped with ``created_at`` (LIN ``mod_ipc.write_command``
                        format -- NOT the legacy donor {"commands":[...]} shape).
  * skin_commands.json / diet_commands.json -> bare arrays, deduped on
                        (steamid, actor_name).
  * players.json / restore_status.json / skin_snapshots.json /
    diet_snapshots.json / ai_positions.json / prime_progress_state.json are
    written by the mod; we only read them.

All game-file paths come from env with sane defaults so a dev box with no game
installed still imports cleanly. Cross-process writes use a short-lived lockfile
(the mod/bot ignore the ``.lock`` sidecar) so concurrent web workers never
clobber each other's append.
"""
from __future__ import annotations

import copy
import json
import mimetypes
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (env-driven; defaults per the build packet)
# ---------------------------------------------------------------------------
SAVED_DIR = os.environ.get(
    "LIN_SAVED_DIR",
    r"C:\Program Files (x86)\Steam\steamapps\common\The Isle Dedicated Server\TheIsle\Saved",
)
BOT_DB_PATH = os.environ.get("BOT_DB_PATH", r"C:\LaIslaNublar\data\laislanublar.db")
DINO_ASSETS_ROOT = os.environ.get("DINO_ASSETS_ROOT", r"C:\LaIslaNublar\web\assets\dinos")
# Skin reference metadata + per-user presets (donor stored these in its own DB;
# LIN keeps the skins surface self-contained as atomic JSON files).
SKIN_META_DIR = os.environ.get("LIN_SKIN_META_DIR", r"C:\LaIslaNublar\web\skin_meta")

# DATA_DIR mirrors the bot: cooldown files + the species lock state file live
# next to the bot DB so the bot and the web share them.
DATA_DIR = str(Path(BOT_DB_PATH).resolve().parent)

PLAYERS_JSON = os.path.join(SAVED_DIR, "players.json")
MOD_ALIVE_JSON = os.path.join(SAVED_DIR, "mod_alive.json")
COMMANDS_JSON = os.path.join(SAVED_DIR, "commands.json")
RESTORE_STATUS_JSON = os.path.join(SAVED_DIR, "restore_status.json")
SWAP_STATUS_JSON = os.path.join(SAVED_DIR, "swap_status.json")
SWAP_PERSIST_PREFIX = os.path.join(SAVED_DIR, "swap_persist_")
SKIN_SNAPSHOTS_JSON = os.path.join(SAVED_DIR, "skin_snapshots.json")
DIET_SNAPSHOTS_JSON = os.path.join(SAVED_DIR, "diet_snapshots.json")
SKIN_COMMANDS_JSON = os.path.join(SAVED_DIR, "skin_commands.json")
DIET_COMMANDS_JSON = os.path.join(SAVED_DIR, "diet_commands.json")
AI_POSITIONS_JSON = os.path.join(SAVED_DIR, "ai_positions.json")
PRIME_PROGRESS_JSON = os.path.join(SAVED_DIR, "prime_progress_state.json")
# Bulk per-player position snapshot: dict keyed by SteamID, carrying steamid /
# dino / actor_name / x / y / z / yaw / growth / health / hunger / stamina /
# last_updated for EVERY live player, rewritten by the mod about once a second.
# Verified against the live prod file 2026-07-31 (104 rows, one shared
# last_updated equal to the file write). Reads degrade to None like every other
# reader in this module when the file is missing/malformed.
PLAYERS_POSITIONS_JSON = os.path.join(SAVED_DIR, "players_positions.json")
# Body Drop feeder lease, written by the mod (NOT json): one TAB-separated row
# per live lease, keyed "<steamid>|deino_body_drop". This is the game's own
# source of truth for the 10-min per-SteamID Body Drop cooldown -- see
# read_feeder_lease() for the column layout.
CORPSE_FEEDER_LEASE_TXT = os.path.join(SAVED_DIR, "cpp_corpse_feeder_lease.txt")

SPECIES_LOCK_STATE_FILE = os.path.join(DATA_DIR, "species_lock_state.json")
# Patreon species unlocks (shared with the bot, which enforces them via its
# popcontrol auto-enforce loop): time-boxed cap bypasses + unlock cooldowns.
SPECIES_UNLOCK_STATE_FILE = os.path.join(DATA_DIR, "species_unlock_state.json")
SLAY_COOLDOWNS_JSON = os.path.join(DATA_DIR, "slay_cooldowns.json")
REDEEM_COOLDOWNS_JSON = os.path.join(DATA_DIR, "redeem_cooldowns.json")
# Owner rule 2026-07-31: parking gained its own per-SteamID wait, in the same
# DATA_DIR — the website and the bot share ONE park_cooldowns.json, so a park on
# either surface starts the wait on both. Deliberately NOT a constant here:
# vault._park_cooldowns_path() resolves it per call off the live DATA_DIR, so a
# rebound DATA_DIR (test lanes) cannot write into the real data directory.

FRESH_SECONDS = 120          # mod-alive liveness window (matches bot mod_ipc)
PLAYERS_MAX_STALE_MS = 45_000  # per-player snapshot trust window (matches bot)
_CACHE_TTL = 1.5

_lock_stale_seconds = 3.0
_file_cache: dict[str, tuple] = {}
_cmd_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# mimetypes: Windows registry often lacks these, which breaks StaticFiles /
# FileResponse content-types for the 3D dino assets. Register at import.
# ---------------------------------------------------------------------------
def register_mimetypes() -> None:
    mimetypes.add_type("image/webp", ".webp")
    mimetypes.add_type("model/gltf-binary", ".glb")
    mimetypes.add_type("model/gltf+json", ".gltf")
    mimetypes.add_type("application/wasm", ".wasm")


register_mimetypes()


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fresh(path: str, max_age_s: int = FRESH_SECONDS) -> bool:
    try:
        return (time.time() - os.path.getmtime(path)) < max_age_s
    except OSError:
        return False


def mod_alive() -> bool:
    return _fresh(MOD_ALIVE_JSON, FRESH_SECONDS) or _fresh(PLAYERS_JSON, FRESH_SECONDS)


def _read_json_cached(path: str, ttl: float = _CACHE_TTL):
    now = time.monotonic()
    entry = _file_cache.get(path)
    if entry and ttl > 0 and (now - entry[1]) < ttl:
        return copy.deepcopy(entry[0])
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        _file_cache[path] = (data, now)
        return copy.deepcopy(data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        if entry:
            return copy.deepcopy(entry[0])
        return None


def read_json_file(path: str):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _epoch_ms(value) -> int | None:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    if ts < 10_000_000_000:  # seconds -> ms
        ts *= 1000
    return int(ts)


def _snapshot_stale(data: dict, player: dict) -> bool:
    ts_ms = _epoch_ms(player.get("last_updated"))
    if ts_ms is None:
        ts_ms = _epoch_ms(data.get("last_updated"))
    if ts_ms is None:
        return False
    return (int(time.time() * 1000) - ts_ms) > PLAYERS_MAX_STALE_MS


def _players_file_fresh(data: dict) -> bool | None:
    if not isinstance(data, dict):
        return None
    ts_ms = _epoch_ms(data.get("last_updated"))
    if ts_ms is None:
        return None
    return (int(time.time() * 1000) - ts_ms) <= PLAYERS_MAX_STALE_MS


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------
def read_players_json() -> dict | None:
    data = _read_json_cached(PLAYERS_JSON, ttl=_CACHE_TTL)
    return data if isinstance(data, dict) else None


def read_players_positions() -> dict | None:
    """Bulk {steamid: {..., x, y, ...}} position snapshot for the visit_location
    quest tracker (server.py's visit_poi_tracker_loop / quest_pois.py). Read-only,
    uncached (polled on a slow 45s loop, not a request hot path); None when the
    file is missing/unavailable so the tracker just skips the tick."""
    return read_json_file(PLAYERS_POSITIONS_JSON)


def read_players_positions_fresh(max_age_s: int = 90) -> dict | None:
    """players_positions.json, but only when the mod is actively writing it
    (file mtime within max_age_s). The mod rewrites this file about once a
    second while the server is up, so a stale/frozen file means the server is
    down or crashed -- its last-known positions must NOT earn visit_location
    quest credit. None => the visit tracker skips the tick."""
    if not _fresh(PLAYERS_POSITIONS_JSON, max_age_s):
        return None
    return read_json_file(PLAYERS_POSITIONS_JSON)


# players_positions.json is a FULL snapshot of every live player, rewritten by
# the mod about once a second. players.json is the HEAVY row (vitals, maxima,
# mutations, skin) and the mod rebuilds it in SHARDS -- players_snapshot_status
# shows rows_built=19 of player_count=100 per tick -- so one player's row there
# is typically 10-40 s old and legally up to PLAYERS_MAX_STALE_MS. Measured on
# prod 2026-07-31 with 100 players: 22 of 100 rows past the 45 s window, and of
# the rows still INSIDE it the recorded position was p90 87 m / p99 267 m /
# worst 4,859 m away from where the player actually was.
#
# So: anything that answers "where is this player RIGHT NOW" or "what is this
# player flying RIGHT NOW" must read the positions snapshot, not the heavy row.
POSITIONS_MAX_AGE_S = 15      # file mtime window: older = the mod stopped writing
POSITIONS_ROW_MAX_AGE_S = 12  # per-row last_updated window inside a fresh file
_POSITIONS_CACHE_TTL = 0.5    # shared across concurrent countdown runners


def read_position_live(steam_id: str) -> dict | None:
    """One player's ~1 s position/species row from players_positions.json, or
    None when the file is missing, frozen, malformed, or has no fresh row for
    this SteamID. Read-only and fully contained -- every failure mode returns
    None so callers fall back to the heavy row."""
    try:
        if not _fresh(PLAYERS_POSITIONS_JSON, POSITIONS_MAX_AGE_S):
            return None
        data = _read_json_cached(PLAYERS_POSITIONS_JSON, ttl=_POSITIONS_CACHE_TTL)
        if not isinstance(data, dict):
            return None
        p = data.get(str(steam_id))
        if not isinstance(p, dict):
            return None
        ts_ms = _epoch_ms(p.get("last_updated"))
        if ts_ms is not None and (int(time.time() * 1000) - ts_ms) > POSITIONS_ROW_MAX_AGE_S * 1000:
            return None
        return p
    except Exception:
        return None


def read_player_live(steam_id: str, force_fresh: bool = False) -> dict | None:
    """read_player(), with SPECIES and POSITION overlaid from the ~1 s
    players_positions.json snapshot.

    Use this for anything that AIMS at a player -- the friend-teleport
    destination, its same-species gate, its don't-move hold. Use plain
    read_player() when you want the heavy fields (maxima, mutations, skin),
    which this row still carries unchanged.

    Fail-safe by construction: it starts from read_player() and only overwrites
    fields when a fresh snapshot row exists, so it can never return a row that
    read_player() would have refused, and a dead/frozen snapshot file degrades
    to exactly today's behaviour."""
    row = read_player(steam_id, force_fresh=force_fresh)
    if not isinstance(row, dict):
        return None
    live = read_position_live(steam_id)
    if not isinstance(live, dict):
        row["pos_source"] = "snapshot"
        return row
    for k in ("dino", "actor_name", "x", "y", "z", "yaw", "growth"):
        if live.get(k) is not None:
            row[k] = live[k]
    row["pos_source"] = "live"
    row["pos_age_s"] = 0
    try:
        ts_ms = _epoch_ms(live.get("last_updated"))
        if ts_ms is not None:
            row["pos_age_s"] = max(0, int((time.time() * 1000 - ts_ms) / 1000))
    except Exception:
        pass
    return row


STALE_HEAVY_MAX_AGE_S = 600  # display-only ceiling for carrying a stale heavy row forward


def _same_pawn(heavy: dict, live: dict) -> bool:
    """Do a heavy players.json row and a positions row describe the SAME pawn?
    Prefers the exact actor instance name; falls back to species when either
    side lacks it. A respawn as a new dino fails this, which is the point --
    the old pawn's catalogue (maxima, diet, mutations) must not dress up the
    new one."""
    ha, la = str(heavy.get("actor_name") or ""), str(live.get("actor_name") or "")
    if ha and la:
        return ha == la
    hd, ld = str(heavy.get("dino") or ""), str(live.get("dino") or "")
    return bool(hd and ld and hd == ld)


def _overlay_positions(row: dict, live: dict) -> dict:
    """Overwrite the fields the ~1 s positions row carries onto a heavy row:
    identity/position plus the CURRENT vitals (health/hunger/stamina raw game
    units -- same units as the heavy row's own current fields, verified against
    prod 2026-08-02). Maxima and the rest of the catalogue stay the heavy
    row's. Only fields the live row actually has overwrite anything."""
    for k in ("dino", "actor_name", "x", "y", "z", "yaw", "growth",
              "health", "hunger", "stamina", "last_updated"):
        if live.get(k) is not None:
            row[k] = live[k]
    row["pos_source"] = "live"
    row["pos_age_s"] = 0
    try:
        ts_ms = _epoch_ms(live.get("last_updated"))
        if ts_ms is not None:
            row["pos_age_s"] = max(0, int((time.time() * 1000 - ts_ms) / 1000))
    except Exception:
        pass
    return row


def read_player_stale(steam_id: str, max_age_s: int = STALE_HEAVY_MAX_AGE_S) -> dict | None:
    """The last heavy players.json row for this SteamID IGNORING the 45 s trust
    window, as long as it is younger than max_age_s. Display fallback only:
    callers must pair it with a fresh positions row proving the player is alive
    NOW -- on its own this row says nothing about liveness."""
    data = _read_json_cached(PLAYERS_JSON, ttl=_CACHE_TTL)
    if not isinstance(data, dict):
        return None
    p = data.get(str(steam_id))
    if not isinstance(p, dict):
        return None
    ts_ms = _epoch_ms(p.get("last_updated"))
    if ts_ms is None:
        ts_ms = _epoch_ms(data.get("last_updated"))
    age_s = None
    if ts_ms is not None:
        age_s = max(0, int((time.time() * 1000 - ts_ms) / 1000))
        if age_s > max_age_s:
            return None
    row = copy.deepcopy(p)
    if age_s is not None:
        row["heavy_age_s"] = age_s
    return row


def read_player_display(steam_id: str) -> dict | None:
    """Liveness-first read for the DISPLAY surfaces (/me/state, /active-dino,
    the self map pin, friend presence).

    players.json is rebuilt in shards: at 100+ players one row is typically
    10-75 s old and read_player() refuses it past 45 s, so a player who just
    spawned -- or whose shard is simply late -- reads as offline for minutes
    while players_positions.json has been publishing them every second. This
    read treats the positions row as the liveness oracle and the heavy row as
    the slow catalogue it is:

      * fresh heavy + fresh positions -> heavy row with the live identity and
        current vitals overlaid (a gauge can never be a shard old)
      * fresh heavy only              -> exactly read_player() (today's answer)
      * positions only                -> the player IS alive: carry the last
        heavy row forward when it describes the SAME pawn (bounded by
        STALE_HEAVY_MAX_AGE_S), else serve a positions-only row flagged
        heavy_missing (maxima/diet arrive with the next shard)
      * neither                       -> None (offline), unchanged

    NEVER use this for anything that gates an action -- park kill verify,
    teleport aim, redeem verify keep their strict readers. Any internal
    surprise degrades to read_player()'s own answer."""
    try:
        row = read_player(steam_id)
        live = read_position_live(steam_id)
        if isinstance(row, dict):
            if isinstance(live, dict):
                return _overlay_positions(row, live)
            row["pos_source"] = "snapshot"
            return row
        if not isinstance(live, dict):
            return None
        stale = read_player_stale(steam_id)
        if isinstance(stale, dict) and _same_pawn(stale, live):
            stale["heavy_stale"] = True
            return _overlay_positions(stale, live)
        minimal = {
            "steamid": str(steam_id),
            "heavy_missing": True,
        }
        return _overlay_positions(minimal, live)
    except Exception:
        return read_player(steam_id)


def read_player(steam_id: str, force_fresh: bool = False) -> dict | None:
    """One player row by SteamID, or None when missing/stale. force_fresh
    bypasses the short cache (used by the park post-kill verify)."""
    sid = str(steam_id)
    ttl = 0.0 if force_fresh else _CACHE_TTL
    data = _read_json_cached(PLAYERS_JSON, ttl=ttl)
    if not isinstance(data, dict):
        return None
    p = data.get(sid)
    if not isinstance(p, dict):
        return None
    if _snapshot_stale(data, p):
        return None
    return copy.deepcopy(p)


def read_player_status(steam_id: str) -> tuple[str, dict | None]:
    """Tri-state liveness read for the park kill gate:
    ('present', row) / ('absent', None) / ('stale', None) / ('unavailable', None)."""
    sid = str(steam_id)
    data = _read_json_cached(PLAYERS_JSON, ttl=0.0)
    if not isinstance(data, dict):
        return ("unavailable", None)
    p = data.get(sid)
    if isinstance(p, dict):
        if _snapshot_stale(data, p):
            return ("stale", None)
        return ("present", copy.deepcopy(p))
    return ("absent", None) if _players_file_fresh(data) is True else ("stale", None)


# restore_status.json parse cache. The body-drop / park / redeem ack loops poll
# this file every 200 ms for up to 25-100 s per request, and the mod only
# rewrites it when something actually happens -- re-parsing an unchanged file on
# every tick is the hottest read in the backend. Keyed on the file's identity +
# stamp, so ANY rewrite (mtime or size) invalidates it. os.stat is one syscall
# against a full JSON parse of the whole ring.
#
# ★ Published by REBINDING ONE TUPLE, never by mutating in place: these readers
# run in sync defs on the FastAPI threadpool, so a half-updated structure would
# be visible to another request mid-write. A reader binds the tuple once and
# therefore sees either the whole old snapshot or the whole new one.
_RESTORE_CACHE_EMPTY: tuple = (None, (), {})
_restore_cache: tuple = _RESTORE_CACHE_EMPTY     # (stat_key, entries, by_cmd_id)


def _restore_snapshot() -> tuple:
    """(entries, by_cmd_id) for restore_status.json, re-parsed only when the
    file actually changes. The returned structures are SHARED and must be
    treated as read-only; callers copy whatever they hand out.

    Fails open in both directions: an unreadable file or a torn/half-written
    JSON keeps serving the last good snapshot rather than blanking every
    in-flight ack poll, and a failed parse does NOT claim the new stat key, so
    the next poll re-reads instead of caching the damage."""
    global _restore_cache
    cached = _restore_cache          # bind once -- see the rebind note above
    try:
        st = os.stat(RESTORE_STATUS_JSON)
        key = (st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size)
    except OSError:
        return (cached[1], cached[2])
    if cached[0] == key:
        return (cached[1], cached[2])
    data = read_json_file(RESTORE_STATUS_JSON)
    if isinstance(data, dict):
        raw = data.get("entries", [])
    elif isinstance(data, list):
        raw = data
    else:
        # Missing or mid-write: hold the previous snapshot, retry next call.
        return (cached[1], cached[2])
    if not isinstance(raw, list):
        return (cached[1], cached[2])
    entries = tuple(i for i in raw if isinstance(i, dict))
    by_cmd: dict[str, list] = {}
    for item in entries:
        cid = str(item.get("cmd_id") or "").strip()
        if cid:
            by_cmd.setdefault(cid, []).append(item)
    _restore_cache = (key, entries, by_cmd)
    return (entries, by_cmd)


def read_restore_status(steam_id, dino_id=None, event=None, actor_name=None, cmd_id=None):
    """Latest restore_status.json entry matching the filters, or None."""
    sid = str(steam_id or "").strip()
    if not sid:
        return None
    target_actor = str(actor_name or "").strip()
    target_cmd = str(cmd_id or "").strip()
    entries, by_cmd = _restore_snapshot()
    # A cmd_id-keyed poll (every ack loop) hits the index instead of walking the
    # whole ring on each 200 ms tick; the unfiltered case keeps the old scan.
    candidates = by_cmd.get(target_cmd, ()) if target_cmd else entries
    target_dino = None
    if dino_id is not None:
        try:
            target_dino = int(dino_id)
        except (TypeError, ValueError):
            target_dino = None
    for item in reversed(candidates):
        if not isinstance(item, dict):
            continue
        if str(item.get("steamid", "")).strip() != sid:
            continue
        if target_cmd and str(item.get("cmd_id", "")).strip() != target_cmd:
            continue
        if event is not None and str(item.get("event", "")) != str(event):
            continue
        if target_actor:
            ia = str(item.get("actor_name", "")).strip()
            if ia and ia != target_actor:
                continue
        if target_dino is not None:
            try:
                if int(item.get("dino_id", -1)) != target_dino:
                    continue
            except (TypeError, ValueError):
                continue
        return copy.deepcopy(item)
    return None


def read_swap_status(steam_id, cmd_id) -> dict | None:
    """Latest swap_status.json entry for (steamid, cmd_id), or None. The mod
    writes only terminal events (swap_ok / swap_failed) into its own ring file
    — never restore_status.json — so the bot reconciler stays undisturbed."""
    sid = str(steam_id or "").strip()
    target_cmd = str(cmd_id or "").strip()
    if not sid or not target_cmd:
        return None
    data = read_json_file(SWAP_STATUS_JSON)
    entries = data.get("entries", []) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return None
    for item in reversed(entries):
        if not isinstance(item, dict):
            continue
        if str(item.get("steamid", "")).strip() != sid:
            continue
        if str(item.get("cmd_id", "")).strip() != target_cmd:
            continue
        return copy.deepcopy(item)
    return None


def clear_swap_persist(steam_id: str) -> None:
    """Drop a pending population-swap persistence record. Called on park /
    slay / redeem success: those lanes moved the player's save state past the
    swap, so the offline .sav watcher must never re-apply it (dupe risk)."""
    sid = str(steam_id or "").strip()
    if not sid:
        return
    for suffix in (".swap", ".tmp"):
        try:
            os.remove(SWAP_PERSIST_PREFIX + sid + suffix)
        except OSError:
            pass


def read_restore_entries() -> list[dict]:
    # deepcopy, not dict(): the snapshot is now SHARED across requests, so a
    # shallow copy would let a caller that mutates a nested value poison every
    # other request's view until the file changes. The module already uses
    # deepcopy for the same reason on the skin/diet snapshots below.
    entries, _ = _restore_snapshot()
    return [copy.deepcopy(i) for i in entries]


def read_skin_snapshot(actor_name: str):
    data = _read_json_cached(SKIN_SNAPSHOTS_JSON)
    if not isinstance(data, dict):
        return None
    p = data.get(actor_name)
    return copy.deepcopy(p) if p else None


# ---------------------------------------------------------------------------
# GHOST-GATE WITNESS PREDICATE (2026-08-16 fix wave). THIS BLOCK IS SHIPPED
# BYTE-IDENTICAL IN bot/skinkeeper_bot.py AND web/backend/game_ipc.py -- one
# function shape, two files, so the two surfaces cannot drift. The battery
# gates on that identity (test_ghostgate.py::T_IDENTITY).
#
# LAW: memory/feedback_gate_on_a_positive_no_capability_signal_never_on_absence.md
#      (second firing, the LIVENESS edition) -- refuse ONLY on a positive "no",
#      NEVER on the absence of a "yes".
#
# WHAT WAS WRONG. The 2026-08-08 gate judged skin_snapshots.json "fresh" by
# FILE MTIME (<=120s) and then read "the resolved actor is ABSENT from it" as
# proof the pawn is a ghost. But the mod rewrites that file only every ~31s
# (measured on the live box 2026-08-16: 30.67 / 31.56 / 30.78 / 31.61s), so a
# pawn born after the last write is absent from a witness that is seconds old
# and yet CANNOT YET TESTIFY ABOUT IT. Measured damage: 102 ghost_gate skips
# against 421 restore_queued across the same four bot logs = 19.5% of restore
# decisions dropped, p50 14s after the join -- every drop inside one snapshot
# period. One player was declared a ghost at 2026-08-15 20:23:04 box-local
# while riding the very actor the skip line named -- still online on that same
# actor, and still wearing the wrong skin, 7.5 hours later. (The sid, the actor
# and both colour recipes are in the wave kit, deliberately not in this file.)
#
# THE FIXED PREDICATE. A witness may only support the verdict "actor X does not
# exist" if it was WRITTEN AFTER X PROVABLY EXISTED. The earliest moment this
# process can vouch for X is the first time it saw the name (bot: the
# players.json poll inside _resolve_actor that produced it; web: the first call
# that asked about it). So, with that first sighting as the witness bar:
#
#   snapshot HAS X                                   -> "live"          positive YES
#   snapshot lacks X, mtime >  first_seen + margin    -> "ghost"         positive NO
#   snapshot lacks X, mtime <= first_seen + margin    -> "unverifiable"  no competent witness
#   snapshot missing / stale / torn / future-stamped  -> "unknown"       FAIL OPEN
#
# "unverifiable" is NOT a refusal. The bot REQUEUES and re-tests on the restore
# queue's own cadence until a competent witness exists; the web -- a one-shot
# synchronous apply by a player who is present by construction from a live
# session -- fails open. "unknown" keeps the pre-2026-08-08 behaviour byte for
# byte (a dead snapshot writer must never kill restores or applies).
#
# THE 2026-08-08 PURPOSE SURVIVES. A genuinely stale registry name is still
# refused; it is just refused one snapshot generation later, once a snapshot
# written after we first saw the name still lacks it. At steady state every
# online actor IS in the snapshot (measured 2026-08-16: 111/111 online players'
# actors present), so the healthy path pays exactly one verdict evaluation and
# resolves "live" on the first look.
#
# NOT re-keyed on players.json, and the measurement says why: the resolved
# actor name COMES FROM players.json, so that file cannot corroborate itself,
# and its per-sid actor_name carries the documented 60-100s stale-row lag that
# IS the 2026-08-08 mis-paint vector. Its measured ~4.6s rewrite cadence also
# means the newest row almost always postdates the newest snapshot (~85% of the
# time), so using a row timestamp as the witness bar would have turned the gate
# into a no-op. The witness bar is this process's own first sighting, on this
# process's own clock -- the same clock st_mtime is stamped on, so no cross-
# writer skew can enter the comparison.
_GHOST_WITNESS_MARGIN_S = 5.0
_GHOST_FUTURE_SKEW_S = 60.0
_GHOST_SEEN_LIMIT = 4096
_GHOST_SEEN_TTL_S = 3600.0
# (mtime, size) -> frozenset of actor names. Rebound as ONE tuple so a reader
# can never observe a new key against old names.
_ghost_snap_cache = (None, frozenset())
_ghost_seen: dict = {}


def _ghost_snapshot_generation(path: str):
    """(mtime, actor-name set) for the engine snapshot, parsed at most ONCE per
    file generation no matter how many callers are waiting on it. Returns
    (None, None) when the file is missing / torn / not a non-empty dict -- a
    torn read never poisons the cache.

    No lock on purpose: the cache is a single tuple rebind under the GIL, so
    the worst a race can cost is one redundant parse, never a wrong answer."""
    global _ghost_snap_cache
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    key = (st.st_mtime, st.st_size)
    cached_key, cached_names = _ghost_snap_cache
    if cached_key == key:
        return st.st_mtime, cached_names
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None, None
    if not isinstance(data, dict) or not data:
        return None, None
    names = frozenset(data)
    _ghost_snap_cache = (key, names)
    return st.st_mtime, names


def _ghost_first_seen(actor_name: str, now=None) -> float:
    """Wall clock of the FIRST moment this process saw this actor name -- the
    witness bar. IDEMPOTENT: a name already known keeps its original stamp, so
    repeated checks can never push the bar forward and turn a competent witness
    back into an incompetent one. Bounded memo (rebuilt, never mutated during
    iteration, so a concurrent insert cannot raise)."""
    global _ghost_seen
    ts = time.time() if now is None else float(now)
    seen = _ghost_seen
    first = seen.get(actor_name)
    if first is not None:
        return first
    if len(seen) >= _GHOST_SEEN_LIMIT:
        try:
            pruned = {k: v for k, v in seen.items() if v >= ts - _GHOST_SEEN_TTL_S}
        except RuntimeError:  # another thread inserted mid-comprehension
            pruned = {}
        if len(pruned) >= _GHOST_SEEN_LIMIT:
            pruned = {}
        pruned[actor_name] = ts
        _ghost_seen = pruned
        return ts
    seen[actor_name] = ts
    return ts


def _ghost_verdict(actor_name: str, witness_ts, snapshot_path: str,
                   max_age_s: int = 120, now=None) -> str:
    """"live" | "ghost" | "unverifiable" | "unknown" -- see the block header.

    Total cost: one os.stat, plus one json parse per snapshot generation shared
    across every caller. Never raises."""
    name = str(actor_name or "").strip()
    if not name:
        return "unknown"
    ts = time.time() if now is None else float(now)
    mtime, names = _ghost_snapshot_generation(snapshot_path)
    if mtime is None:
        return "unknown"                       # missing / torn / empty
    if (ts - mtime) > max_age_s:
        return "unknown"                       # writer down -> FAIL OPEN (unchanged)
    if mtime > ts + _GHOST_FUTURE_SKEW_S:
        # A future-stamped snapshot would postdate EVERY witness bar and so
        # would manufacture a ghost verdict for every absent actor. It is not a
        # witness. Fail open -- and note this exits, so it can never wedge the
        # requeue either.
        return "unknown"
    if name in names:
        return "live"                          # positive YES
    try:
        witness = float(witness_ts)
    except (TypeError, ValueError):
        return "unknown"
    if not (witness > 0.0) or witness > ts + _GHOST_FUTURE_SKEW_S:
        return "unknown"                       # unusable witness bar -> FAIL OPEN
    if mtime > witness + _GHOST_WITNESS_MARGIN_S:
        # POSITIVE NO: this snapshot walked the world after the pawn provably
        # existed and still does not carry it.
        return "ghost"
    # The witness predates the pawn it is being asked about. Not a refusal.
    return "unverifiable"
# ---------------------------------------------------------------------------


def actor_live_in_engine(actor_name: str, max_age_s: int = 120):
    """Tri-state liveness of actor_name against the ENGINE-TRUTH skin snapshot
    (SkinSystem's periodic walk of real in-world actors, keyed by actor name).

    Why this exists (2026-08-08): the sid->actor registry (players.json and the
    players_positions fallback) can serve a binding from the player's PREVIOUS
    life, or even a previous BOOT - five glitch applies painted a two-restarts-
    old actor name while the player watched nothing happen, and the mod's
    FindByActorName honours any non-empty name with no steamid cross-check.

    REPAIRED 2026-08-16 (ghost-gate wave): "absent from a FRESH snapshot" was
    never proof. The mod rewrites that file every ~31s, so a pawn born after
    the last write is absent from a witness seconds old -- 25 applies were
    refused on lanes equip / reward / studio that way. The refusal now needs
    POSITIVE testimony: a snapshot written AFTER this process first saw the
    name and still lacking it. See the GHOST-GATE WITNESS PREDICATE block above
    (shipped byte-identical in bot/skinkeeper_bot.py) and
    feedback_gate_on_a_positive_no_capability_signal_never_on_absence.md.

    The four call sites in server.py test `is False`, so the tri-state contract
    is deliberately unchanged and NO call site is edited:
      True  - the name is in the snapshot (in the world; may still be a
              lingering corpse - this check cannot see sids, so it narrows,
              never proves ownership).
      False - a snapshot that POSTDATES the pawn still lacks the name: provably
              not in the world. Callers refuse without spending anything.
      None  - unknown OR not-yet-verifiable (snapshot missing / stale / torn /
              future-stamped, or written before we first saw this actor).
              Callers MUST fail OPEN and behave as before -- a witness that
              cannot yet testify must never refuse a player's apply, and a dead
              snapshot writer must never block applies.

    The web deliberately maps "unverifiable" to fail-open where the bot
    requeues: an apply is a one-shot synchronous request from a player who is
    present by construction from a live session, and parking him on a queue is
    banned (feedback_a_review_queue_is_a_stuck_dino). The PREDICATE is
    identical; only this disposition differs, and it differs in the safe
    direction."""
    name = str(actor_name or "").strip()
    if not name:
        return None
    verdict = _ghost_verdict(name, _ghost_first_seen(name), SKIN_SNAPSHOTS_JSON,
                             max_age_s=max_age_s)
    if verdict == "live":
        return True
    if verdict == "ghost":
        return False
    return None


def read_diet_snapshot(actor_name: str):
    data = _read_json_cached(DIET_SNAPSHOTS_JSON)
    if not isinstance(data, dict):
        return None
    p = data.get(actor_name)
    return copy.deepcopy(p) if p else None


def read_prime_progress(steam_id: str) -> dict | None:
    data = read_json_file(PRIME_PROGRESS_JSON)
    if not isinstance(data, dict):
        return None
    row = data.get(str(steam_id))
    return dict(row) if isinstance(row, dict) else None


# Rows are TAB-separated and fixed-width in columns (the mod tolerates a stray
# 7th column from an older writer, so we only require the first six):
#   key <TAB> owner <TAB> state <TAB> ts_ms <TAB> cooldown_until_ms <TAB> spawn_id
_FEEDER_LEASE_COLS = 6
_FEEDER_LEASE_KEY_SUFFIX = "|deino_body_drop"
# The mod rewrites this file whole and drops every expired row, so it holds at
# most one line per SteamID with a lease live in the last 10 minutes. The cap is
# only there so a corrupted file can never spin a request thread.
_FEEDER_LEASE_MAX_LINES = 4096


def read_feeder_lease(steam_id: str) -> dict | None:
    """The caller's Body Drop feeder-lease row, or None when there isn't one.

    ``state`` is "pending" (a corpse is queued) or "fed" (one was delivered);
    ``ts_ms`` / ``cooldown_until_ms`` are unix epoch MILLISECONDS on the same
    wall clock as ``time.time() * 1000``. Retention is NOT applied here -- an
    expired row still parses; the caller decides what is still live.

    Deliberately does not take the mod's ``.lock``: this sits on the request
    hot path and blocking a player behind the game's writer would cost far more
    than the stale read it avoids. EVERY failure -- missing file, OSError,
    permission denied, a line torn mid-rewrite, a short row, a non-numeric
    stamp -- returns None, i.e. "no lease known", so the caller falls through
    to the game exactly as it did before this reader existed. A Body Drop must
    never be refused because this read had a bad day."""
    sid = str(steam_id or "").strip()
    if not sid:
        return None
    key = sid + _FEEDER_LEASE_KEY_SUFFIX
    try:
        with open(CORPSE_FEEDER_LEASE_TXT, "r", encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f):
                if n >= _FEEDER_LEASE_MAX_LINES:
                    break
                # startswith prefilter: non-matching rows are never split, so a
                # busy file costs one comparison per line and nothing else.
                if not line.startswith(key):
                    continue
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) < _FEEDER_LEASE_COLS or parts[0] != key:
                    continue
                try:
                    ts_ms = int(float(parts[3] or 0))
                    cooldown_until_ms = int(float(parts[4] or 0))
                except (TypeError, ValueError, OverflowError):
                    # OverflowError is not optional here: int(float("inf")) and
                    # any digit run long enough to overflow a float both land on
                    # it, and this function promises never to raise.
                    return None      # torn/garbled row -> no lease known
                return {
                    "key": key,
                    "owner": parts[1],
                    "state": parts[2],
                    "ts_ms": ts_ms,
                    "cooldown_until_ms": cooldown_until_ms,
                    "spawn_id": parts[5],
                }
    except (OSError, ValueError, OverflowError):
        return None
    return None


# ---------------------------------------------------------------------------
# writes (cross-process lockfile + atomic replace)
# ---------------------------------------------------------------------------
def _acquire_lock(lockpath: str) -> bool:
    delay = 0.02
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            fd = os.open(lockpath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            try:
                age = time.time() - os.path.getmtime(lockpath)
            except OSError:
                age = 0
            if age > _lock_stale_seconds:
                try:
                    os.remove(lockpath)
                except OSError:
                    pass
                continue
            time.sleep(delay)
            delay = min(delay * 1.5, 0.1)
    return False


def _release_lock(lockpath: str) -> None:
    try:
        os.remove(lockpath)
    except OSError:
        pass


def _read_existing_array(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
        if not content:
            return []
        data = json.loads(content)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _append_array(path: str, payload: dict, *, dedupe_keys: tuple = (),
                  max_len: int = 0) -> bool:
    lockpath = path + ".lock"
    if not _acquire_lock(lockpath):
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        existing = _read_existing_array(path)
        if dedupe_keys:
            keyset = tuple(str(payload.get(k, "")) for k in dedupe_keys)
            existing = [
                row for row in existing
                if not (isinstance(row, dict)
                        and tuple(str(row.get(k, "")) for k in dedupe_keys) == keyset)
            ]
        existing.append(dict(payload))
        if max_len and len(existing) > max_len:
            existing = existing[-max_len:]
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(existing, f, separators=(",", ":"))
        os.replace(tmp, path)
        return True
    except Exception:
        return False
    finally:
        _release_lock(lockpath)


def write_game_command(cmd: dict) -> bool:
    """Append one command to commands.json in LIN's bare-array format with a
    ``created_at`` stamp. Fail-closed when the mod is offline, exactly like the
    bot's ``mod_ipc.write_command``. Serialised in-process + cross-process."""
    if not mod_alive():
        return False
    payload = dict(cmd)
    payload.setdefault("created_at", _iso_now())
    # Freshness stamp (2026-08-07): epoch ms, same clock the mod's NowMs()
    # reads (one box). The lua refuses stale kill/restore replays after a
    # wedge or restart - the 2026-08-06 22:41Z wedge queued park kills for up
    # to 28 minutes and executed them on rejoin, which both killed rejoiners
    # and let one death promote several journal lines.
    payload.setdefault("issued_at_ms", int(time.time() * 1000))
    with _cmd_write_lock:
        return _append_array(COMMANDS_JSON, payload)


def write_skin_command(cmd: dict) -> bool:
    return _append_array(SKIN_COMMANDS_JSON, cmd, dedupe_keys=("steamid", "actor_name"), max_len=50)


def write_diet_command(cmd: dict) -> bool:
    return _append_array(DIET_COMMANDS_JSON, cmd, dedupe_keys=("steamid", "actor_name"), max_len=50)


# ---------------------------------------------------------------------------
# active-dino resolution (players.json is the truth on LIN)
# ---------------------------------------------------------------------------
_ACTIVE_DINO_STALE_SECS = 90


def find_active_dino(steam_id: str) -> dict | None:
    """{actor_name, class} for the caller's currently-possessed dino, or None."""
    p = read_player(steam_id)
    if isinstance(p, dict):
        actor_name = str(p.get("actor_name") or "").strip()
        if actor_name:
            return {"actor_name": actor_name, "class": p.get("dino") or p.get("dino_class") or ""}
    # 2026-08-08 shard fallback: above ~100 players the mod rebuilds players.json
    # in SHARDS (rows_built ~19 per tick), so a LIVE player's row can be absent
    # here for tens of seconds - the owner hit "No tienes un dino activo" while
    # standing in game (95 rows in players.json vs 105 in positions at the time).
    # players_positions.json is the FULL ~1s snapshot and carries exactly the two
    # fields this function returns. Consult it before answering "not in game".
    # Freshness 30s: a frozen positions file means the server is down, and a
    # down server must still answer None.
    pos = read_players_positions_fresh(30)
    if isinstance(pos, dict):
        row = pos.get(str(steam_id))
        if not isinstance(row, dict):
            for v in pos.values():
                if isinstance(v, dict) and str(v.get("steamid") or "") == str(steam_id):
                    row = v
                    break
        if isinstance(row, dict):
            actor_name = str(row.get("actor_name") or "").strip()
            if actor_name:
                return {"actor_name": actor_name, "class": row.get("dino") or row.get("dino_class") or ""}
    return None
