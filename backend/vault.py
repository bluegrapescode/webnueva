"""Web-side dino vault (La Bóveda): park / redeem / slay / list / delete.

A faithful port of the La Isla Nublar bot's utility panel (bot-src/dino.py +
database.py), adapted to the web session auth. It shares the SAME artefacts as
the bot so the two never double-act on a slot:

  * parked_dinos table in the bot SQLite DB (BOT_DB_PATH) — the EXACT LIN
    schema (no prime_conditions / reconcile columns; those are donor-only).
  * commands.json / restore_status.json game IPC via game_ipc (LIN bare-array
    command shapes — kill / restore / slay match bot-src/dino.py byte-for-byte).
  * slay_cooldowns.json / redeem_cooldowns.json in the bot DATA_DIR.

Two writers (bot + web) hit the DB, so every write uses WAL + a busy_timeout and
short transactions. Redeem is dup-safe: a row is claimed under BEGIN IMMEDIATE
before the restore is written and deleted only on the winning cmd_id ack.

All player-facing "detail" strings are Spanish.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from threading import Lock

from fastapi import HTTPException

import dino_recovery
import game_ipc
from mutation_catalog import CARNIVORES, growth_display_pct

log = logging.getLogger("laislanublar.vault")

# ── event loop captured at startup (sync handlers run in a threadpool) ────────
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _schedule(coro) -> None:
    if _loop is not None:
        asyncio.run_coroutine_threadsafe(coro, _loop)
    else:
        try:
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            log.warning("[vault] no event loop to schedule background job")


# ── constants (mirror the bot's LIN config) ──────────────────────────────────
def _cooldown_env_secs(name: str) -> int:
    raw = str(os.environ.get(name, "") or "").strip()
    try:
        return max(0, int(raw)) if raw else 0
    except ValueError:
        log.warning("[vault] invalid %s=%r — cooldown disabled (0)", name, raw)
        return 0


def _cooldown_env_secs_default(name: str, default_secs: int) -> int:
    """Same knob, but with a non-zero built-in default. A blank/absent env var
    keeps the default; an explicit 0 disables the wait; a typo falls back to the
    default rather than silently removing a gate the owner asked for."""
    raw = str(os.environ.get(name, "") or "").strip()
    if not raw:
        return max(0, default_secs)
    try:
        return max(0, int(raw))
    except ValueError:
        log.warning("[vault] invalid %s=%r — using default %ss", name, raw, default_secs)
        return max(0, default_secs)


# Vault cooldowns removed at the owner's request (2026-07-16): 0 = no wait
# between slays/redeems. Set SLAY_COOLDOWN_SECS / REDEEM_COOLDOWN_SECS in the
# backend .env to re-enable (the bot reads the same names from its own .env).
SLAY_COOLDOWN_SECS = _cooldown_env_secs("SLAY_COOLDOWN_SECS")
REDEEM_COOLDOWN_SECS = _cooldown_env_secs("REDEEM_COOLDOWN_SECS")
# Owner rule 2026-07-31: park gets a 2-minute per-SteamID wait (it never had
# one). Stamped only on a dino that actually reached the vault — a refused or
# failed park must not burn the wait. PARK_COOLDOWN_SECS=0 removes it again.
PARK_COOLDOWN_SECS = _cooldown_env_secs_default("PARK_COOLDOWN_SECS", 120)
LIVE_FRESH_SECS = 45.0
PARK_ACK_TIMEOUT_SECS = 90.0
# Doubles as the redeem-pending lock freshness TTL (_redeem_pending_fresh).
# Must exceed the mod's own restore terminal window: the game delivers its
# definitive not_ready_timeout verdict at up to +80s after the command
# (observed live 2026-07-13, cmd 866a9c0d). The old 47s window gave up before
# that verdict landed and orphaned the pending marker — and a lock that
# expires while the game can still act opens a duplicate-dino window.
REDEEM_VERIFY_TIMEOUT_SECS = 100.0
RESTORE_DIET_READY_POLLS = 30
RESTORE_DIET_READY_INTERVAL = 0.5

def _pct_env(name: str, default: str) -> float:
    """Threshold knob (0..1). Bad values fall back to the built-in default so a
    typo in .env can never take the park/redeem gates down."""
    raw = str(os.environ.get(name, "") or "").strip()
    try:
        v = float(raw) if raw else float(default)
    except ValueError:
        log.warning("[vault] invalid %s=%r — using %s", name, raw, default)
        return float(default)
    return min(1.0, max(0.0, v))


# Owner rule 2026-07-18: parking requires FULL health (100%). The rest of the
# thresholds keep their historical values. The bot reads the same env names
# from its own .env — keep both .envs in sync when overriding.
# Owner rule 2026-07-23: lower the park GROWTH floor to 25% so any dino from
# juvenile (25%) up to fully grown (100%) can be parked — was 75%. The saved
# growth is written back verbatim on redeem (see _run_redeem) and the mod's
# growth_ok ack gates the restore, so a lower floor restores exactly like a
# higher one.
PARK_MIN_GROWTH = _pct_env("PARK_MIN_GROWTH", "0.25")
PARK_MIN_HEALTH_PCT = _pct_env("PARK_MIN_HEALTH_PCT", "1.00")
PARK_MIN_STAMINA_PCT = _pct_env("PARK_MIN_STAMINA_PCT", "0.70")
# Owner rule 2026-07-31: hunger floor 20% -> 50% (stamina stays 70%).
PARK_MIN_HUNGER_PCT = _pct_env("PARK_MIN_HUNGER_PCT", "0.50")
REDEEM_MIN_HEALTH_PCT = _pct_env("REDEEM_MIN_HEALTH_PCT", "0.80")
REDEEM_MIN_STAMINA_PCT = _pct_env("REDEEM_MIN_STAMINA_PCT", "0.70")
REDEEM_MIN_HUNGER_PCT = _pct_env("REDEEM_MIN_HUNGER_PCT", "0.50")


# ★A REDEEM NEVER MOVES THE PLAYER (owner ruling 2026-07-29, replacing the
# 2026-07-24 rule). You come back standing where you redeemed from, the same way
# Arkadia does it — the redeem-to-park-spot teleport, its LIN_REDEEM_SPAWN_AT_PARK
# switch and its landing readback are GONE from both surfaces (web + bot), not
# defaulted off, so nothing can wake them by accident. The rest of the parked
# condition is untouched: vitals still come back at their parked percentages and
# the stored diet still replays. park_dino still records x/y/z — the column stays
# so no row loses data — it simply has no consumer on the way back out.
# Float tolerance for the percentage gates: a genuinely-full bar can read
# 0.9999997 after the mod's float round-trip; that must still count as 100%.
_PCT_GATE_EPS = 1e-4

# ── Body Drop (requested corpse feed) ─────────────────────────────────────────
# The server drops a fresh corpse NEXT TO a starving juvenile carnivore so it
# can eat — it never touches the requester's own dino. Gates MUST stay in
# lockstep with the mod's HandleBodyDropRequest (main.full.lua): a gate we
# allow that the mod refuses becomes a player-visible promise with no body.
# Thresholds: hunger < 30% (hungrier = lower); growth < 65% (owner ruling
# 2026-07-16 — was 50%).
# The mod's 10-min per-SteamID feeder lease is the limiter. The web does not
# own that cooldown — it READS the mod's own lease file up front
# (bodydrop_cooldown_remaining) instead of burning a full web->Lua->C++->Lua->web
# round trip only to be told "body_drop_cooldown". The game still re-gates
# everything; this is a pre-gate, never the authority.
BODYDROP_MAX_HUNGER_PCT = 0.30
BODYDROP_MAX_GROWTH = 0.65
# Mod ack ~2.9s typical, measured on LIN 2026-07-25 (the corpse spawn still
# rides the 30s PE-dispatch/GT drain, so the tail runs far past the median).
# ★ ORDERING LAW: client abort > this server wait > measured latency. The web
# client aborts at 30 s (frontend src/lib/api.js REQUEST_TIMEOUT_MS), so this
# value must stay BELOW 30 s. Raise it past that and a player is shown a
# connection error for a drop that landed and already stamped a 10-min lease.
BODYDROP_ACK_TIMEOUT_SECS = 25.0
# One quiet retry when the game reports a contained native fault while placing
# the corpse (fail_reason native_fault_*): the half-spawned body was destroyed
# and the 10-min lease was NOT stamped, so a fresh attempt is safe and lands
# (2026-08-03, live: both faulting players fed themselves by retrying within
# seconds). Timeouts are NEVER retried — a late ack can still land the corpse
# and a second command would double-drop. The whole request (both attempts)
# must still finish under the client's 30 s abort (ORDERING LAW above), hence
# the total budget + a minimum useful window for the second attempt.
BODYDROP_MAX_ATTEMPTS = 2
BODYDROP_RETRY_DELAY_SECS = 2.0
BODYDROP_TOTAL_BUDGET_SECS = 28.0
BODYDROP_RETRY_MIN_WINDOW_SECS = 8.0
# Same 10 classes as the mod's LaIslaNublarBodyDropRecipient table.
BODYDROP_RECIPIENT_CLASSES = frozenset(CARNIVORES)

# parked_dinos column order — EXACTLY bot-src/database.py PARKED_COLS.
_PARKED_COLS = [
    "id", "steam_id", "discord_id", "dino_class", "growth",
    "health", "max_health", "stamina", "max_stamina",
    "hunger", "max_hunger", "thirst", "max_thirst",
    "oxygen", "max_oxygen", "x", "y", "z",
    "is_prime", "is_elder", "mutations", "parent_mutations",
    "elder_mutations", "elder_stacks", "skin_code", "skin_data",
    "diet_a", "diet_b", "diet_c",
    "parked_at", "redeem_pending_cmd_id", "redeem_pending_at",
]
_PARKED_SELECT = ", ".join(_PARKED_COLS)

# Optional display-name column (2026-07-18): added by ensure_custom_name_column()
# at web startup. Display-only — never sent to the game. Reads only include it
# once the schema upgrade is confirmed, so a failed upgrade can never break the
# vault's SELECTs.
_CUSTOM_NAME_READY = False

# Prime MISSION STATE (2026-07-29): the ten bPrimeConditionN bits plus the two
# route counters. players.json publishes all three for every live player and the
# mod parses and applies all three on restore — the vault was simply the only
# hop that never carried them, so a stored dino arrived with zero bits and the
# mod then GUESSED from growth: at >=75% or elder it force-ticks all ten, below
# that it drops Prime entirely. That guess is what players report as "my dino
# isn't Prime any more".
#
# ★NULLABLE, and NULL means something. NULL = "parked before this shipped, we
# never recorded it"; 0 = "recorded, nothing done". Writing 0 for an unknown
# would permanently disguise the first as the second.
_PRIME_STATE_COLS = ("prime_conditions", "prime_route_mig", "prime_route_pat")
_PRIME_STATE_READY = False


def _parked_select() -> str:
    cols = _PARKED_SELECT
    if _CUSTOM_NAME_READY:
        cols += ", custom_name"
    if _PRIME_STATE_READY:
        cols += ", " + ", ".join(_PRIME_STATE_COLS)
    return cols


def clean_custom_name(raw) -> str:
    """Sanitized display name: printable chars, single-spaced, max 32. Empty
    string means "no custom name" (fall back to the species name)."""
    s = str(raw or "")
    s = " ".join(s.split())  # any whitespace run (incl. newlines/tabs) -> one space
    s = "".join(ch for ch in s if ch.isprintable())
    return s[:32].strip()

# Per-species full-grown nutrient baselines, copied 1:1 from bot-src/dino.py.
_REDEEM_DIET_BASELINES = {
    "BP_Tyrannosaurus_C": {"carbs": 4049, "protein": 4049, "lipids": 4049},
    "BP_Allosaurus_C": {"carbs": 1211, "protein": 1211, "lipids": 1211},
    "BP_Carnotaurus_C": {"carbs": 593, "protein": 593, "lipids": 593},
    "BP_Ceratosaurus_C": {"carbs": 642, "protein": 642, "lipids": 642},
    "BP_Deinosuchus_C": {"carbs": 3550, "protein": 3550, "lipids": 3550},
    "BP_Diabloceratops_C": {"carbs": 1937, "protein": 1937, "lipids": 1937},
    "BP_Dilophosaurus_C": {"carbs": 322, "protein": 322, "lipids": 322},
    "BP_Dryosaurus_C": {"carbs": 92, "protein": 92, "lipids": 92},
    "BP_Gallimimus_C": {"carbs": 280, "protein": 280, "lipids": 280},
    "BP_Herrerasaurus_C": {"carbs": 71, "protein": 71, "lipids": 71},
    "BP_Hypsilophodon_C": {"carbs": 12, "protein": 12, "lipids": 12},
    "BP_Maiasaura_C": {"carbs": 2674, "protein": 2674, "lipids": 2674},
    "BP_Omniraptor_C": {"carbs": 218, "protein": 218, "lipids": 218},
    "BP_Pachycephalosaurus_C": {"carbs": 395, "protein": 395, "lipids": 395},
    "BP_Pteranodon_C": {"carbs": 19.77, "protein": 19.77, "lipids": 19.77},
    "BP_Stegosaurus_C": {"carbs": 4636, "protein": 4636, "lipids": 4636},
    "BP_Tenontosaurus_C": {"carbs": 914, "protein": 914, "lipids": 914},
    "BP_Triceratops_C": {"carbs": 6249, "protein": 6249, "lipids": 6249},
    "BP_Troodon_C": {"carbs": 26, "protein": 26, "lipids": 26},
    "BP_Beipiaosaurus_C": {"carbs": 46, "protein": 46, "lipids": 46},
    # Kentrosaurus was missing from this table while server.py's
    # _SWAP_DIET_EXTRA already carried 1900 for it as the same "full-grown
    # nutrient" quantity (that override exists precisely because this lookup had
    # no row). Same number, so a redeemed Kentrosaurus stops falling back to the
    # {100,100,100} sentinel and matches what a species swap already gives it.
    "BP_Kentrosaurus_C": {"carbs": 1900, "protein": 1900, "lipids": 1900},
    # Austroraptor: adult diet capacity 115.5 = adult max_health 350.0 x 0.33
    # carnivore hunger ratio (same identity the rows above obey).
    "BP_Austroraptor_C": {"carbs": 115.5, "protein": 115.5, "lipids": 115.5},
}


def _friendly(cls: str) -> str:
    return str(cls or "").replace("BP_", "").replace("_C", "")


def _mutation_count(raw) -> int:
    """Non-"None" segments in the game's "|"-delimited mutation string (e.g.
    "Titan|None|Feral|None" -> 2). Matches the on-disk parked_dinos / restore
    command mutation encoding -- see _run_redeem's restore cmd, which passes
    this same string through to the game unchanged."""
    if not raw:
        return 0
    return sum(1 for part in str(raw).split("|") if part.strip() and part.strip() != "None")


def _num(value, default=0.0) -> float:
    # OverflowError is float()'s answer to an int too big for a double (10**400)
    # — the same "no usable number here" as the other two, and the one shape that
    # escaped a helper whose whole job is to answer the default instead of
    # raising. mutation_catalog.growth_fraction catches it for the same reason.
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── DB access (shared bot SQLite DB) ──────────────────────────────────────────
def _connect_rw():
    if not os.path.isfile(game_ipc.BOT_DB_PATH):
        raise HTTPException(503, "La bóveda no está disponible en este momento.")
    conn = sqlite3.connect(game_ipc.BOT_DB_PATH, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _row_to_dict(row):
    return dict(row) if row is not None else None


def count_parked(steam_id: str) -> int:
    conn = _connect_rw()
    try:
        r = conn.execute("SELECT COUNT(*) AS n FROM parked_dinos WHERE steam_id = ?", (str(steam_id),)).fetchone()
        return int(r["n"] if r else 0)
    finally:
        conn.close()


def get_parked(steam_id: str) -> list[dict]:
    conn = _connect_rw()
    try:
        rows = conn.execute(
            f"SELECT {_parked_select()} FROM parked_dinos WHERE steam_id = ? ORDER BY id",
            (str(steam_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_parked_by_id(dino_id: int) -> dict | None:
    conn = _connect_rw()
    try:
        r = conn.execute(f"SELECT {_parked_select()} FROM parked_dinos WHERE id = ?", (int(dino_id),)).fetchone()
        return _row_to_dict(r)
    finally:
        conn.close()


def resolve_discord_id(steam_id: str) -> str:
    try:
        conn = _connect_rw()
    except HTTPException:
        return ""
    try:
        r = conn.execute("SELECT discord_id FROM accounts WHERE steam_id = ? LIMIT 1", (str(steam_id),)).fetchone()
        return str(r["discord_id"]) if r and r["discord_id"] else ""
    except sqlite3.OperationalError:
        return ""
    finally:
        conn.close()


# ── park never-lose journal (2026-07-30) ─────────────────────────────────────
# Ported from the CretaceousIsle perma-fix (live_actions_routes.py fa51ebd8ce26,
# itself the IsleDeutschlandRP vault_db pattern — both verified live) after the
# fleet post-kill audit: once the kill is confirmed the dino is dead in-world,
# so whatever happens to the INSERT *is* the player's dinosaur. The snapshot is
# journaled to disk BEFORE the kill order; every resolved outcome prunes its
# line; anything unresolved stays in the file and the drain promotes it once
# the mod's own death log proves the kill. Fail-closed everywhere: an entry the
# drain cannot positively resolve is kept, never dropped.
_PARK_JOURNAL_LOCK = Lock()
_PARK_PREKILL_REASON = "web_park_journal_prekill"
_RECOVERY_ID_READY = False
# Request path: bounded ladder (the caller holds a threadpool worker; each
# attempt already waits busy_timeout=5000ms). Drain path: patient ladder —
# nobody is waiting on a background sweep, so contention just gets outwaited.
_PARK_DB_BEGIN_ATTEMPTS = 3
_PARK_DB_BEGIN_SLEEP_SECS = 0.25
_PARK_DB_BEGIN_ATTEMPTS_PATIENT = 5
_PARK_DB_BEGIN_SLEEP_PATIENT_SECS = 1.5
# Evidence windows around queued_at (epoch secs), donor values: a park kill
# lands within seconds, so a death of that class inside the window is the kill.
_PARK_KILL_EVIDENCE_BEFORE_SECS = 120.0
_PARK_KILL_EVIDENCE_AFTER_SECS = 900.0
_PARK_RETRY_NEARBY_AFTER_SECS = 1020.0  # must cover the kill-evidence window
# (900s) + margin: a retry park landing in the 600..900s band used to be
# invisible to _parked_row_near while the SAME death still proved the old
# journal line - one dino, two rows (2026-08-07 dupe wave forensics).


def _park_journal_enabled() -> bool:
    """Kill switch (LIN_PARK_JOURNAL=0). Default ON — flag-off restores the
    pre-2026-07-30 behaviour byte-for-byte."""
    return str(os.environ.get("LIN_PARK_JOURNAL", "1")).strip().lower() not in (
        "0", "false", "no", "off")


def _park_unsaved_path() -> str:
    return os.path.join(game_ipc.DATA_DIR, "park_unsaved.jsonl")


def _iso_to_epoch(value) -> float | None:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


def _queued_park_recovery_id(item: dict) -> str:
    """Stable idempotency key for ONE journal line (donor vault_db parity): a
    content hash, so re-reads always agree and two different parks can never
    collide."""
    if not isinstance(item, dict):
        return ""
    existing = str(item.get("recovery_id") or "").strip()
    if existing:
        return existing
    material = {
        "steam_id": str(item.get("steam_id", "")),
        "discord_id": str(item.get("discord_id", "")),
        "player_data": item.get("player_data") or {},
        "cap": item.get("cap"),
        "reason": str(item.get("reason", "")),
        "queued_at": str(item.get("queued_at", "")),
    }
    encoded = json.dumps(material, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8", "surrogatepass")
    return hashlib.sha256(encoded).hexdigest()


def append_unsaved_park(steam_id: str, discord_id: str, player_data: dict,
                        cap, reason: str) -> str:
    """Append one park snapshot to park_unsaved.jsonl. Returns the line's
    recovery_id, or "" on failure — start_park fails CLOSED on "" (a park the
    player can retry beats a dino that silently evaporates)."""
    path = _park_unsaved_path()
    try:
        try:
            cap_val = int(cap) if cap else 0
        except (TypeError, ValueError):
            cap_val = 0
        payload = {
            "steam_id": str(steam_id),
            "discord_id": str(discord_id or ""),
            "player_data": dict(player_data or {}),
            "cap": cap_val,
            "reason": str(reason or ""),
            "queued_at": _iso_now(),
        }
        rid = _queued_park_recovery_id(payload)
        payload["recovery_id"] = rid
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with _PARK_JOURNAL_LOCK:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        log.info("[vault] park journal sid=%s ok=True reason=%s rid=%s",
                 steam_id, reason, rid[:12])
        return rid
    except Exception:
        log.exception("[vault] park journal sid=%s ok=False reason=append_error",
                      steam_id)
        return ""


def _write_park_unsaved_lines(path: str, keep: list) -> bool:
    """Atomic journal rewrite (same-dir temp + os.replace) so a crash mid-write
    can never leave a truncated file. CALLER MUST HOLD _PARK_JOURNAL_LOCK."""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for raw in keep:
                fh.write(raw + "\n")
        os.replace(tmp, path)
        return True
    except Exception:
        log.exception("[vault] park journal rewrite ok=False (journal left intact)")
        return False


def _journal_prune(recovery_ids: set, reason: str) -> int:
    """Atomically drop the given recovery_ids from the journal — a resolved park
    owes nothing, and a leftover line would let the drain resurrect a dino that
    is alive and well. Prunes BY ID under the lock (never a stale rewrite): a
    park appending mid-sweep must not be erased. Never raises."""
    ids = {str(r).strip() for r in (recovery_ids or set()) if str(r).strip()}
    if not ids:
        return 0
    path = _park_unsaved_path()
    with _PARK_JOURNAL_LOCK:
        try:
            if not os.path.isfile(path):
                return 0
            with open(path, "r", encoding="utf-8") as fh:
                raw_lines = [ln.rstrip("\r\n") for ln in fh if ln.strip()]
        except Exception:
            log.exception("[vault] park journal prune_read ok=False")
            return 0
        kept: list[str] = []
        removed = 0
        for raw in raw_lines:
            rid = ""
            try:
                item = json.loads(raw)
                if isinstance(item, dict):
                    rid = _queued_park_recovery_id(item)
            except Exception:
                rid = ""
            if rid and rid in ids:
                removed += 1
                continue
            kept.append(raw)
        if not removed:
            return 0
        if not _write_park_unsaved_lines(path, kept):
            return 0
    log.info("[vault] park journal prune ok=True removed=%d reason=%s", removed, reason)
    return removed


def ensure_recovery_id_column() -> bool:
    """One-time schema upgrade: parked_dinos.recovery_id + its index — what makes
    a drained row provably the SAME dino as its journal line. Additive, exactly
    like custom_name before it (the bot's explicit-column INSERT/SELECTs are
    unaffected). Idempotent, never raises; on failure the drain simply refuses
    to promote (fail-closed) instead of risking a duplicate."""
    global _RECOVERY_ID_READY
    if _RECOVERY_ID_READY:
        return True
    try:
        conn = _connect_rw()
    except Exception:
        log.warning("[vault] park schema ok=False reason=db_unavailable")
        return False
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(parked_dinos)")]
        if not cols:
            log.warning("[vault] park schema ok=False reason=no_parked_dinos_table")
            return False
        if "recovery_id" not in cols:
            conn.execute("ALTER TABLE parked_dinos ADD COLUMN recovery_id TEXT")
            log.warning("[vault] park schema ok=True reason=recovery_id_column_added")
        else:
            log.info("[vault] park schema ok=True reason=already_present")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_parked_recovery_id "
                     "ON parked_dinos(recovery_id)")
        _RECOVERY_ID_READY = True
        return True
    except Exception:
        log.exception("[vault] park schema ok=False reason=alter_failed")
        return False
    finally:
        conn.close()


def _park_recovery_state(recovery_id: str) -> str:
    """'found' | 'absent' | 'error'. Deliberately three-valued: the drain
    DELETES journal lines, so "could not read" must never be mistaken for
    "already stored" — that would drop a line whose dino was never restored."""
    rid = str(recovery_id or "").strip()
    if not rid:
        return "error"
    try:
        conn = _connect_rw()
    except Exception:
        return "error"
    try:
        r = conn.execute(
            "SELECT 1 FROM parked_dinos WHERE recovery_id = ? LIMIT 1", (rid,)
        ).fetchone()
        return "found" if r is not None else "absent"
    except sqlite3.OperationalError:
        return "error"  # column not migrated yet — keep the line
    except Exception:
        log.exception("[vault] park drain recovery_read ok=False rid=%s", rid[:12])
        return "error"
    finally:
        conn.close()


def _death_evidence_between(steam_id: str, dino_class: str, lo: float, hi: float) -> bool:
    """True iff the mod's own death log holds a death of this class for this sid
    inside [lo, hi] epoch secs — the same source the admin recovery panel
    trusts, and exactly how the 2026-07-29 lost parks were hand-recovered (a
    park kill lands in death_causes.log like any other death). Never raises."""
    try:
        deaths = dino_recovery.read_recent_deaths(
            game_ipc.SAVED_DIR, str(steam_id), dino_recovery.DEATH_SCAN_SIZE)
    except Exception:
        return False
    cls = str(dino_class or "").strip()
    for d in deaths or []:
        if str(d.get("dino_class") or "") != cls:
            continue
        try:
            ts = float(d.get("ts"))
        except (TypeError, ValueError):
            continue
        if lo <= ts <= hi:
            return True
    return False


def _similar_parked_row_exists(steam_id: str, dino_class: str, pd: dict) -> bool:
    """True iff a SURVIVING row of this sid+class is near-identical to the journal
    snapshot (growth within 0.002, or max_health within 0.02 when the snapshot
    carries a positive one). Two honest parks of a growing dinosaur sit minutes of
    growth apart; identical numbers mean the same park promoting twice (the
    2026-08-07 phantom class). Errors return True: skip is fail-safe, a double
    insert is not."""
    try:
        g = float(pd.get("growth"))
    except (TypeError, ValueError):
        g = None
    try:
        mh = float(pd.get("max_health"))
    except (TypeError, ValueError):
        mh = None
    if g is None and (mh is None or mh <= 0):
        return False
    try:
        conn = _connect_rw()
    except Exception:
        return True
    try:
        rows = conn.execute(
            "SELECT growth, max_health FROM parked_dinos WHERE steam_id = ? AND dino_class = ?",
            (str(steam_id), str(dino_class)),
        ).fetchall()
        for r in rows:
            try:
                if g is not None and r["growth"] is not None and abs(float(r["growth"]) - g) <= 0.002:
                    return True
                if mh is not None and mh > 0 and r["max_health"] is not None and abs(float(r["max_health"]) - mh) <= 0.02:
                    return True
            except (TypeError, ValueError):
                continue
        return False
    except Exception:
        return True
    finally:
        conn.close()


def _parked_row_near(steam_id: str, dino_class: str, lo: float, hi: float) -> bool:
    """True iff a parked row of this class for this sid has parked_at inside the
    window — a manual retry park already stored this dino, so promoting the
    journal line too would hand the player a second copy. Errors return True:
    skip is fail-safe, a double insert is not."""
    try:
        conn = _connect_rw()
    except Exception:
        return True
    try:
        rows = conn.execute(
            "SELECT parked_at FROM parked_dinos WHERE steam_id = ? AND dino_class = ?",
            (str(steam_id), str(dino_class)),
        ).fetchall()
        for r in rows:
            t = _iso_to_epoch(r["parked_at"])
            if t is not None and lo <= t <= hi:
                return True
        return False
    except Exception:
        return True
    finally:
        conn.close()


def save_parked(steam_id: str, discord_id: str, pd: dict, cap: int,
                recovery_id: str | None = None, parked_at: str | None = None,
                patient: bool = False) -> int | None:
    """Cap-checked INSERT under BEGIN EXCLUSIVE (ports database.save_parked_dino).
    cap<=0 = unlimited. Returns new row id, or None at capacity.

    2026-07-30 (park never-lose): BEGIN EXCLUSIVE now retries SQLITE_BUSY on a
    fresh connection instead of surrendering after one 5s busy_timeout — by the
    time this runs the kill is confirmed, so a lost lock used to cost the dino.
    `recovery_id` is stamped in the SAME transaction as the row so a row can
    never exist without its journal identity; `parked_at` lets the drain stamp
    the moment the player actually parked, not the recovery time; `patient`
    widens the ladder for the background drain (nobody is waiting on it)."""
    # A dino that CHANGES HANDS drops its park position (2026-07-24). Redeem
    # now spawns a dino on its stored spot, and the marketplace/withdraw lane
    # feeds this function the SELLER's whole row — replaying that would drop the
    # buyer on a location the seller never agreed to share. Only a payload
    # already owned by this steam_id (a real park, or a seller reclaiming their
    # own listing) keeps its coordinates; the rest fall back to the all-zero
    # no-position sentinel and redeem exactly as they did before this feature.
    source_sid = str(pd.get("steam_id") or "").strip()
    transferred = bool(source_sid) and source_sid != str(steam_id)
    if transferred:
        pd = dict(pd)
        pd["x"] = pd["y"] = pd["z"] = 0.0
        log.info("[vault] transfer to sid=%s from sid=%s — park position dropped",
                 steam_id, source_sid)
    attempts = _PARK_DB_BEGIN_ATTEMPTS_PATIENT if patient else _PARK_DB_BEGIN_ATTEMPTS
    retry_sleep = _PARK_DB_BEGIN_SLEEP_PATIENT_SECS if patient else _PARK_DB_BEGIN_SLEEP_SECS
    conn = _connect_rw()
    for attempt in range(1, attempts + 1):
        try:
            conn.execute("BEGIN EXCLUSIVE")
            if attempt > 1:
                log.info("[vault] park db_begin sid=%s ok=True reason=won_on_retry attempt=%d",
                         steam_id, attempt)
            break
        except sqlite3.OperationalError as exc:
            log.warning("[vault] park db_begin sid=%s ok=False reason=db_busy attempt=%d/%d err=%s",
                        steam_id, attempt, attempts, exc)
            try:
                conn.close()
            except sqlite3.Error:
                pass
            if attempt >= attempts:
                raise
            time.sleep(retry_sleep)
            conn = _connect_rw()
    try:
        if cap and cap > 0:
            r = conn.execute("SELECT COUNT(*) AS n FROM parked_dinos WHERE steam_id = ?", (str(steam_id),)).fetchone()
            if int(r["n"]) >= cap:
                conn.execute("ROLLBACK")
                return None
        cur = conn.execute(
            """INSERT INTO parked_dinos
                 (steam_id, discord_id, dino_class, growth, health, max_health,
                  stamina, max_stamina, hunger, max_hunger, thirst, max_thirst,
                  oxygen, max_oxygen, x, y, z, is_prime, is_elder, mutations,
                  parent_mutations, elder_mutations, elder_stacks, skin_code,
                  skin_data, diet_a, diet_b, diet_c, parked_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(steam_id), str(discord_id),
                pd.get("dino") or pd.get("dino_class") or "Unknown",
                _num(pd.get("growth")), _num(pd.get("health")), _num(pd.get("max_health")),
                _num(pd.get("stamina")), _num(pd.get("max_stamina")),
                _num(pd.get("hunger")), _num(pd.get("max_hunger")),
                _num(pd.get("thirst")), _num(pd.get("max_thirst")),
                _num(pd.get("oxygen")), _num(pd.get("max_oxygen")),
                _num(pd.get("x")), _num(pd.get("y")), _num(pd.get("z")),
                1 if pd.get("is_prime") else 0,
                1 if pd.get("is_elder") else 0,
                pd.get("mutations", ""), pd.get("parent_mutations", ""),
                pd.get("elder_mutations", ""), int(_num(pd.get("elder_stacks"))),
                pd.get("skin_code", ""), pd.get("skin_data", ""),
                _num(pd.get("diet_a")), _num(pd.get("diet_b")), _num(pd.get("diet_c")),
                str(parked_at or "").strip() or _iso_now(),
            ),
        )
        new_id = cur.lastrowid
        if _PRIME_STATE_READY:
            # An UPDATE inside the same transaction rather than three more
            # INSERT columns, so the INSERT column list stays byte-identical to
            # bot-src/database.py PARKED_COLS — the bot writes this same table.
            # Only fires for values the payload actually carried; everything
            # else stays NULL.
            state = _prime_state_from_payload(pd)
            if state:
                conn.execute(
                    "UPDATE parked_dinos SET %s WHERE id = ?"
                    % ", ".join("%s = ?" % c for c in state),
                    tuple(state.values()) + (new_id,))
            # Logged for every park, captured or not: a row that silently records
            # nothing is the failure mode this lane already had once, and "absent"
            # in the log is the only way to see it without opening the DB.
            log.info("[vault] park prime-state row_id=%s %s", new_id,
                     " ".join("%s=%s" % (c, state.get(c, "absent"))
                              for c in _PRIME_STATE_COLS))
        if _CUSTOM_NAME_READY:
            # Carry a display name through market transfers (the buy lane passes
            # the listing's vault_payload back in here). Cosmetic only.
            name = clean_custom_name(pd.get("custom_name"))
            if name:
                conn.execute("UPDATE parked_dinos SET custom_name = ? WHERE id = ?", (name, new_id))
        if recovery_id:
            # Same transaction as the INSERT: a row must never exist without its
            # journal identity, or the drain could insert it a second time. A
            # follow-up UPDATE (not an INSERT column) so an unmigrated DB still
            # parks normally — the drain then refuses to promote (fail-closed).
            try:
                conn.execute("UPDATE parked_dinos SET recovery_id = ? WHERE id = ?",
                             (str(recovery_id), new_id))
            except sqlite3.OperationalError:
                log.warning("[vault] park recovery_stamp sid=%s ok=False reason=no_column",
                            steam_id)
        conn.execute("COMMIT")
        # gen0park2 (2026-08-23): AFTER the commit only — a mark for a row that
        # rolled back would stamp the mod's zombie ledger with a ghost id.
        if not recovery_id and not transferred:
            _gen0_parkmark(str(steam_id), int(new_id), _num(pd.get("growth")))
        return int(new_id)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _gen0_parkmark(sid: str, dino_id: int, growth: float = 0.0) -> None:
    """gen0park2 (2026-08-23): hand the mod the vault row id of a LIVE park so
    its GEN-0 zombie ledger matches redeems by IDENTITY instead of by the
    species/growth/skin tuple (two same-tuple rows alias — codex rank 2).
    Fire-and-forget: the mod no-ops for a sid with nothing in its ledger, a
    repeat mark is idempotent, and a lost mark leaves the row on the v2
    tuple-match grace. growth_pct (int, 0..100) is the mark's echo: the mod
    stamps only a FRESH ledger row whose growth agrees, so a same-sid vault
    insert that is NOT the zombie park (e.g. a seller reclaiming a listing)
    can never claim the zombie's ledger row. Recovery drains and market
    transfers deliberately do NOT mark — their rows are not the walked zombie
    the ledger recorded. Until the gen0park2 bin arms, the old bin logs the
    block as notify_skip reason=unknown_gen0_parkmark (bounded, the proven
    08-21 pre-arm shape). Never raises into the park lane."""
    try:
        from gen0_infection import write_notify_blocks
        digits = "".join(ch for ch in str(sid) if ch.isdigit())
        if not digits or int(dino_id) <= 0:
            return
        pct = int(round(max(0.0, min(1.0, float(growth or 0.0))) * 100))
        block = '{"action":"gen0_parkmark","steamid":"%s","dino_id":%d,"growth_pct":%d}' % (
            digits, int(dino_id), pct)
        if not write_notify_blocks([block]):
            log.warning("[vault] gen0_parkmark sid=%s dino=%s ok=False reason=queue_write", sid, dino_id)
    except Exception as exc:  # noqa: BLE001 — a mark must never break a park
        log.warning("[vault] gen0_parkmark sid=%s dino=%s ok=False err=%s", sid, dino_id, exc)


def _drain_one_park_unsaved(raw: str, promoted_this_sweep: set | None = None) -> str:
    """Resolve ONE journal line. Returns 'restored' (inserted this pass), 'done'
    (positively proven already stored — safe to prune) or 'left' (unresolved —
    kept for the next sweep). Never raises."""
    try:
        ent = json.loads(raw)
    except Exception:
        log.warning("[vault] park drain parse ok=False reason=bad_json (left)")
        return "left"
    if not isinstance(ent, dict):
        log.warning("[vault] park drain parse ok=False reason=not_an_object (left)")
        return "left"
    sid = str(ent.get("steam_id") or "").strip()
    pd = ent.get("player_data") if isinstance(ent.get("player_data"), dict) else {}
    dino_cls = str(pd.get("dino") or pd.get("dino_class") or "").strip()
    if not sid or not dino_cls:
        log.warning("[vault] park drain validate ok=False reason=incomplete sid=%s cls=%s",
                    sid or "?", dino_cls or "?")
        return "left"
    rid = _queued_park_recovery_id(ent)
    rstate = _park_recovery_state(rid) if rid else "error"
    if rstate == "found":
        log.info("[vault] park drain sid=%s skip ok=True reason=already_restored rid=%s",
                 sid, rid[:12])
        return "done"
    if rstate == "error":
        # LIN has no secondary marker table: an unreadable identity check keeps
        # the line (fail-closed) rather than risking a duplicate insert.
        log.warning("[vault] park drain sid=%s skip ok=False reason=identity_unreadable (left)",
                    sid)
        return "left"
    if promoted_this_sweep is not None and (sid, dino_cls) in promoted_this_sweep:
        # One death proves at most ONE park. A second line for the same
        # sid+class in the SAME sweep is a copy of the row just promoted
        # (2026-08-06 wedge pileup: 12 players x 2-4 copies) - hold it; the
        # next sweep re-judges it against the freshly inserted row.
        log.warning("[vault] park drain sid=%s skip ok=False "
                    "reason=sibling_promoted_this_sweep cls=%s (left)", sid, dino_cls)
        return "left"
    qat = _iso_to_epoch(ent.get("queued_at"))
    if qat is None:
        # 2026-08-07 phantom-printer fix: a line with no/unparseable queued_at
        # loses every evidence window below (they collapse to now +/- 1h) and a
        # blind promotion resurrects parks long since redeemed back out (80
        # phantom rows minted at the 00:43/13:15/15:01/18:11 boot drains today).
        # No timestamp = no promotion, ever - the line stays for hand review.
        log.warning("[vault] park drain sid=%s skip ok=False reason=no_queued_at "
                    "cls=%s (left - hand review)", sid, dino_cls)
        return "left"
    if str(ent.get("reason") or "") == _PARK_PREKILL_REASON:
        # A pre-kill line's dino may still be ALIVE (the kill was never
        # confirmed) — promoting it blind would hand the player a second copy
        # of a dinosaur they are still riding. Demand the death log's proof.
        klo = (qat - _PARK_KILL_EVIDENCE_BEFORE_SECS) if qat else (time.time() - 3600.0)
        khi = (qat + _PARK_KILL_EVIDENCE_AFTER_SECS) if qat else time.time()
        if not _death_evidence_between(sid, dino_cls, klo, khi):
            log.info("[vault] park drain sid=%s skip ok=True reason=prekill_no_kill_proof "
                     "cls=%s (dino presumed alive; left)", sid, dino_cls)
            return "left"
        log.warning("[vault] park drain sid=%s prekill_kill_confirmed cls=%s rid=%s",
                    sid, dino_cls, rid[:12])
    lo = (qat - _PARK_RETRY_NEARBY_AFTER_SECS) if qat else (time.time() - 3600.0)
    hi = (qat + _PARK_RETRY_NEARBY_AFTER_SECS) if qat else time.time()
    if _parked_row_near(sid, dino_cls, lo, hi):
        log.warning("[vault] park drain sid=%s skip ok=False reason=direct_park_nearby cls=%s "
                    "(left — clear by hand once confirmed)", sid, dino_cls)
        return "left"
    if _similar_parked_row_exists(sid, dino_cls, pd):
        log.warning("[vault] park drain sid=%s skip ok=False reason=similar_row_exists "
                    "cls=%s (left - hand review)", sid, dino_cls)
        return "left"
    try:
        cap = int(ent.get("cap") or 0)
    except (TypeError, ValueError):
        cap = 0
    try:
        # Stamp the row with the moment the player actually parked, not the
        # moment we recovered it.
        new_id = save_parked(sid, str(ent.get("discord_id") or ""), pd, cap,
                             recovery_id=rid,
                             parked_at=str(ent.get("queued_at") or ""),
                             patient=True)
    except Exception:
        log.exception("[vault] park drain sid=%s insert ok=False (left for next sweep)", sid)
        return "left"
    if new_id is None:
        log.warning("[vault] park drain sid=%s insert ok=False reason=vault_full "
                    "(left until a slot frees up)", sid)
        return "left"
    log.warning("[vault] park drain sid=%s restore ok=True row_id=%s cls=%s growth=%s "
                "queued_at=%s reason=%s",
                sid, new_id, dino_cls, pd.get("growth"), ent.get("queued_at"),
                ent.get("reason"))
    if promoted_this_sweep is not None:
        promoted_this_sweep.add((sid, dino_cls))
    return "restored"


def drain_park_unsaved_once() -> dict:
    """Promote every journaled park the live path could not persist, then prune
    what resolved. Cost when the journal is absent (the normal case) is one
    os.path.isfile. Never raises: the caller is a background loop."""
    summary = {"scanned": 0, "restored": 0, "left": 0}
    if not _park_journal_enabled():
        return summary
    path = _park_unsaved_path()
    if not os.path.isfile(path):
        return summary
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw_lines = [ln.rstrip("\r\n") for ln in fh if ln.strip()]
    except Exception:
        log.exception("[vault] park drain read ok=False")
        return summary
    summary["scanned"] = len(raw_lines)
    if not raw_lines:
        return summary
    resolved: set[str] = set()
    promoted_this_sweep: set = set()
    for raw in raw_lines:
        try:
            verdict = _drain_one_park_unsaved(raw, promoted_this_sweep)
        except Exception:
            log.exception("[vault] park drain entry ok=False (left)")
            verdict = "left"
        if verdict == "left":
            summary["left"] += 1
            continue
        if verdict == "restored":
            summary["restored"] += 1
        try:
            rid = _queued_park_recovery_id(json.loads(raw))
        except Exception:
            rid = ""
        if rid:
            resolved.add(rid)
    if resolved:
        _journal_prune(resolved, "drained")
    log.info("[vault] park drain %s", summary)
    return summary


async def park_unsaved_drain_loop(interval_secs: float = 300.0) -> None:
    """Startup + every 5 minutes. The ARMED line is deliberate: a lane that logs
    only when it restores something is undiagnosable when it silently dies."""
    log.info("[vault] park drain ARMED path=%s interval=%ss enabled=%s recovery_col=%s",
             _park_unsaved_path(), int(interval_secs), _park_journal_enabled(),
             _RECOVERY_ID_READY)
    while True:
        try:
            await asyncio.to_thread(drain_park_unsaved_once)
        except Exception:
            log.exception("[vault] park drain loop ok=False")
        await asyncio.sleep(interval_secs)


def _upgrade_journal_to_postkill(recovery_id: str, steam_id: str, discord_id: str,
                                 snapshot: dict, cap: int, cause: str) -> bool:
    """The kill is CONFIRMED and the save failed: replace the pre-kill line with
    a post-kill line, which the drain promotes with no death-log evidence (the
    ack already proved the death). UPGRADE, never duplicate. Returns True when
    a durable line — either shape — survives on disk."""
    if not _park_journal_enabled():
        return False
    new_rid = append_unsaved_park(steam_id, discord_id, snapshot, cap,
                                  "web_post_kill_%s" % cause)
    if new_rid:
        if recovery_id:
            _journal_prune({recovery_id}, "upgraded to post-kill entry")
        return True
    if recovery_id:
        # Append failed, so the pre-kill line stays. The kill DID land, so the
        # death log will prove it and the drain still promotes — slower, not lost.
        log.error("[vault] park journal upgrade sid=%s ok=False (pre-kill line kept)",
                  steam_id)
        return True
    return False


def delete_owned(dino_id: int, steam_id: str) -> int:
    conn = _connect_rw()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "DELETE FROM parked_dinos WHERE id = ? AND steam_id = ? "
            "AND (redeem_pending_cmd_id IS NULL OR redeem_pending_cmd_id = '')",
            (int(dino_id), str(steam_id)),
        )
        n = int(cur.rowcount or 0)
        conn.execute("COMMIT")
        return n
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def ensure_custom_name_column() -> bool:
    """One-time schema upgrade: parked_dinos.custom_name (display-only, shared
    DB — the bot's explicit-column INSERT/SELECTs are unaffected). Idempotent
    and contained: on failure the vault keeps working and rename reports itself
    unavailable. Called once at web startup."""
    global _CUSTOM_NAME_READY
    if _CUSTOM_NAME_READY:
        return True
    try:
        conn = _connect_rw()
        try:
            cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(parked_dinos)").fetchall()}
            if "custom_name" not in cols:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("ALTER TABLE parked_dinos ADD COLUMN custom_name TEXT")
                conn.execute("COMMIT")
                log.info("[vault] parked_dinos.custom_name column added")
            _CUSTOM_NAME_READY = True
        finally:
            conn.close()
    except Exception:
        log.exception("[vault] custom_name schema upgrade failed — rename unavailable")
    return _CUSTOM_NAME_READY


def ensure_prime_state_columns() -> bool:
    """One-time schema upgrade: the three nullable Prime mission-state columns.

    Modelled on ensure_custom_name_column above — additive, idempotent and
    contained. Every reader of parked_dinos on this box is dict-shaped or
    pinned to its own explicit column list (the bot's positional zip is zipped
    against its OWN select), so ADD COLUMN cannot break any of them; custom_name
    already set that precedent.

    On failure the vault keeps working on the old wire shape: a dino still
    redeems, it just redeems the way it did before this shipped.
    """
    global _PRIME_STATE_READY
    if _PRIME_STATE_READY:
        return True
    try:
        conn = _connect_rw()
        try:
            cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(parked_dinos)").fetchall()}
            missing = [c for c in _PRIME_STATE_COLS if c not in cols]
            if missing:
                conn.execute("BEGIN IMMEDIATE")
                for col in missing:
                    conn.execute("ALTER TABLE parked_dinos ADD COLUMN %s INTEGER" % col)
                conn.execute("COMMIT")
                log.info("[vault] parked_dinos prime-state columns added: %s", ", ".join(missing))
            _PRIME_STATE_READY = True
        finally:
            conn.close()
    except Exception:
        log.exception("[vault] prime-state schema upgrade failed — a redeemed dino will "
                      "keep arriving without its mission bits until this is fixed")
    return _PRIME_STATE_READY


# ★The park payload and the stored row spell the route counters DIFFERENTLY, and
# only one of the two ever reaches this function from each caller. The mod publishes
# them in players.json as l_mig / l_pat (live: 39 of 39 rows) and never as
# prime_route_mig / prime_route_pat (0 of 39), so a park that looks the column names
# up finds nothing and the two columns stay NULL forever — which is exactly what the
# live DB showed before this: 0 of 570 rows with a route counter, against a bitmask
# that was already being captured.
#
# Ported from Arkadia, the owner proven to carry route counters through park/redeem:
# it reads l_mig / l_pat at park (database.py:1207-1210) and the column names at
# redeem (dino.py:5414-5415), with a primary-then-fallback reader for callers that
# may pass either shape (dino.py:1606-1613 _safelog_prime_route).
#
# The COLUMN name stays primary so the replay lanes — market withdraw, dino recovery,
# store purchase, inventory→vault — which hand a stored row straight back into
# save_parked, still match first and keep round-tripping. Nothing else changes: a
# payload carrying neither spelling still contributes no key, so the column stays
# NULL and "we never recorded it" remains distinguishable from "recorded, none done".
_PRIME_STATE_SOURCE_ALIASES = {
    "prime_route_mig": "l_mig",
    "prime_route_pat": "l_pat",
}


def _prime_state_from_payload(pd: dict) -> dict:
    """The mission-state values a payload actually carried — ABSENT keys omitted.

    ★Returns only what was SUPPLIED. A caller that knows nothing produces {},
    and the row's columns stay NULL. Defaulting the missing ones to 0 here would
    stamp "recorded, nothing done" onto every /adddino grant and every recovery
    built from a capture that predates the mission-bit fields, and no later heal
    could ever tell those apart from a genuine zero again.
    """
    out = {}
    if not isinstance(pd, dict):
        return out
    limits = {"prime_conditions": 1023, "prime_route_mig": 2, "prime_route_pat": 4}
    for col, hi in limits.items():
        value = pd.get(col)
        if value in (None, ""):
            # Arkadia's primary-then-fallback read. An empty string counts as
            # not-supplied here exactly as it does there, so a blank field falls
            # through to the players.json spelling instead of being discarded.
            value = pd.get(_PRIME_STATE_SOURCE_ALIASES.get(col, col))
        if value is None or isinstance(value, bool):
            continue
        try:
            raw = float(value)
        except (TypeError, ValueError):
            continue
        if raw != raw:  # NaN
            continue
        if raw == float("inf"):
            out[col] = hi
            continue
        if raw == float("-inf"):
            out[col] = 0
            continue
        out[col] = max(0, min(hi, int(raw)))
    return out


# ===========================================================================
# MINT-TIME PRIME STATE  (2026-08-08)
# ===========================================================================
# ★A MINTED PRIME IS A FACT, NOT AN OBSERVATION.
#
# The lanes that CREATE a prime dino out of nothing -- store purchase, the
# battle pass premium row, the legacy inventory->vault move -- set is_prime=1
# and stopped there. _prime_state_from_payload (above) then found no mission
# bits to report, correctly contributed no keys, and the row landed with
# prime_conditions / prime_route_mig / prime_route_pat NULL.
#
# That is not cosmetic. The mod's redeem plans a prime restore leg from the
# CONDITIONS MASK, not from the flag, and vault._run_redeem only forwards the
# three columns a row actually recorded (see the ★ comment at the redeem cmd
# below). NULL therefore means "plan no prime leg", so every purchased prime
# was delivered as an ordinary animal. 478 live rows are in that state.
#
# WHY THIS IS NOT FIXED INSIDE _prime_state_from_payload: that function is the
# shared reader for the REPLAY lanes too -- market withdraw, dino recovery, the
# park journal drain -- where "absent" is the honest answer and defaulting it
# would stamp "recorded, nothing done" onto captures that predate the mission
# fields, permanently indistinguishable from a genuine zero. Its docstring says
# so, and it stays exactly as it is. The knowledge that a row is prime-complete
# belongs to the MINT, which is the only caller that can state it as a fact, so
# the statement is made there and nowhere else.
_PRIME_MINT_STATE = {
    "prime_conditions": 1023,   # all ten condition bits
    "prime_route_mig": 2,       # migration route at cap
    "prime_route_pat": 4,       # patrol route at cap
}


def mint_prime_state(pd: dict) -> dict:
    """Return `pd` with a freshly-minted prime's mission state filled in.

    Returns a NEW dict when it adds anything and the ORIGINAL object otherwise,
    so a caller may always reassign. Contract, in the order it is checked:

      * NOT PRIME -> returned untouched. A non-prime mint (the battle pass
        regular row, a basic store dino) is byte-identical to before this
        existed: no key is added, so save_parked contributes nothing and the
        columns stay NULL exactly as they always did.
      * ALREADY CARRIES A REAL VALUE -> that value is kept. "Carries" is decided
        by _prime_state_from_payload itself, never by a second look at the dict,
        so the alias spellings (l_mig / l_pat), the empty-string-is-absent rule
        and the clamps cannot drift apart from the reader that stores them. A
        real recorded 0 is a value and survives; None and '' are absent and fill.
      * OTHERWISE -> the mint constants above.

    NEVER RAISES, and never loses the mint. A payload that somehow breaks the
    reader comes back as the object that went in, so save_parked still runs and
    the dino still lands -- it simply lands the way it did before this shipped,
    which is the outcome this function exists to improve, not a new failure.
    Pure dict work: no connection, no query, nothing added to the park hot path.
    """
    try:
        if not isinstance(pd, dict) or not pd.get("is_prime"):
            return pd
        supplied = _prime_state_from_payload(pd)
        missing = {c: v for c, v in _PRIME_MINT_STATE.items() if c not in supplied}
        if not missing:
            return pd
        out = dict(pd)
        out.update(missing)
        log.info("[vault] mint prime-state stamped %s (carried %s)",
                 " ".join("%s=%s" % kv for kv in sorted(missing.items())),
                 " ".join("%s=%s" % kv for kv in sorted(supplied.items())) or "nothing")
        return out
    except Exception:
        # Containment, deliberately broad: enrichment is an improvement on the
        # mint, never a precondition for it.
        log.exception("[vault] mint prime-state FAILED — the dino still parks, "
                      "but it parks without its mission bits")
        return pd


def rename_owned(dino_id: int, steam_id: str, name: str) -> int:
    """Set/clear the display name on an owned parked row. Returns rows hit."""
    if not ensure_custom_name_column():
        raise HTTPException(503, "El renombrado no está disponible en este momento. Intenta más tarde.")
    conn = _connect_rw()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE parked_dinos SET custom_name = ? WHERE id = ? AND steam_id = ?",
            (name or None, int(dino_id), str(steam_id)),
        )
        n = int(cur.rowcount or 0)
        conn.execute("COMMIT")
        return n
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _redeem_pending_fresh(row: dict | None, now_ms: int | None = None) -> bool:
    if not isinstance(row, dict) or not str(row.get("redeem_pending_cmd_id") or "").strip():
        return False
    try:
        started = int(row.get("redeem_pending_at"))
    except (TypeError, ValueError):
        return False
    now = _now_ms() if now_ms is None else int(now_ms)
    return now - started <= int(REDEEM_VERIFY_TIMEOUT_SECS * 1000)


def _steam_has_fresh_redeem_pending(steam_id: str) -> bool:
    conn = _connect_rw()
    try:
        rows = conn.execute(
            "SELECT redeem_pending_cmd_id, redeem_pending_at FROM parked_dinos "
            "WHERE steam_id = ? AND redeem_pending_cmd_id IS NOT NULL AND redeem_pending_cmd_id != ''",
            (str(steam_id),),
        ).fetchall()
        return any(_redeem_pending_fresh(dict(r)) for r in rows)
    finally:
        conn.close()


def mark_redeem_pending(dino_id: int, steam_id: str, cmd_id: str,
                        pending_at_ms: int) -> tuple[bool, dict | None, str]:
    """Claim a row under BEGIN IMMEDIATE — the cross-process lock the bot also
    honours. Ports database.mark_redeem_pending. Returns (marked, row, reason)."""
    conn = _connect_rw()
    try:
        conn.execute("BEGIN IMMEDIATE")
        # ★Deliberately the SAME shape as get_parked_by_id. This row is
        # currently discarded by start_redeem — it feeds _run_redeem from
        # get_parked_by_id instead — but the two SELECTs having different
        # column sets is a loaded gun: the day anyone feeds the restore from
        # this one, every added field silently vanishes from the wire and every
        # unit assertion stays green. One shape, no trap.
        r = conn.execute(f"SELECT {_parked_select()} FROM parked_dinos WHERE id = ?", (int(dino_id),)).fetchone()
        row = _row_to_dict(r)
        if not row:
            conn.execute("ROLLBACK")
            return False, None, "missing"
        if str(row.get("steam_id", "")) != str(steam_id):
            conn.execute("ROLLBACK")
            return False, row, "owner_mismatch"
        if _redeem_pending_fresh(row, pending_at_ms):
            conn.execute("ROLLBACK")
            return False, row, "pending_locked"
        cur = conn.execute(
            "UPDATE parked_dinos SET redeem_pending_cmd_id = ?, redeem_pending_at = ? "
            "WHERE id = ? AND steam_id = ?",
            (str(cmd_id), int(pending_at_ms), int(dino_id), str(steam_id)),
        )
        if cur.rowcount != 1:
            conn.execute("ROLLBACK")
            return False, row, "update_missed"
        conn.execute("COMMIT")
        row["redeem_pending_cmd_id"] = str(cmd_id)
        row["redeem_pending_at"] = int(pending_at_ms)
        return True, row, "marked"
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def clear_redeem_pending(dino_id: int, steam_id: str, cmd_id: str) -> int:
    conn = _connect_rw()
    try:
        cur = conn.execute(
            "UPDATE parked_dinos SET redeem_pending_cmd_id = NULL, redeem_pending_at = NULL "
            "WHERE id = ? AND steam_id = ? AND redeem_pending_cmd_id = ?",
            (int(dino_id), str(steam_id), str(cmd_id)),
        )
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def resolve_stale_redeem_pending(row: dict | None) -> dict | None:
    """Self-heal a redeem-pending marker whose verify job is gone (verify-window
    timeout, backend bounce, or game crash mid-redeem). Fresh markers are
    returned untouched — that redeem may still land. A stale marker is resolved
    the same way the bot's boot reconciler does: a confirmed restore finalises
    the redeem (row deleted, exactly-once), anything else unlocks the row.
    Returns the row (marker cleared if it was stale), or None when the row was
    finalised away / no longer exists. Callers gate on the marker AFTER this,
    so only a genuinely in-flight redeem can block edit/delete/publish.

    ★A row is unlocked ONLY when the dino provably did NOT reach the world.
    Unlocking a delivered dino is how a player ends up with two of the same
    animal (2026-08-05: prime_final_verify_ok arrived False on an otherwise
    perfect restore, the state read "ambiguous", and the stored copy was handed
    straight back). Delivery is judged on the world, never on a cosmetic tick."""
    if not isinstance(row, dict):
        return row
    cmd_id = str(row.get("redeem_pending_cmd_id") or "").strip()
    if not cmd_id or _redeem_pending_fresh(row):
        return row
    dino_id = int(row.get("id") or 0)
    sid = str(row.get("steam_id") or "")
    state, _status = _restore_terminal_state(cmd_id, sid, dino_id)
    delivered = state == "success"
    if not delivered and state == "ambiguous" and _restore_reached_world(_status):
        # It landed. Something non-essential failed to confirm itself, which is
        # a reason to look at the restore - never a reason to hand out a copy.
        log.warning("[vault] stale redeem AMBIGUOUS but delivered - finalising "
                    "sid=%s dino_id=%s cmd_id=%s actor=%s", sid, dino_id, cmd_id,
                    str((_status or {}).get("live_actor_name") or "?"))
        delivered = True
    elif (not delivered and state == "failed" and _restore_reached_world(_status)
            and (_finite_float((_status or {}).get("health_observed")) or 0.0) > 0.0):
        # Definitive-failure verdict but a LIVING body was read back in-world:
        # the animal is in the player's hands and unlocking mints a duplicate
        # (2026-08-06 store stego 7060, twice through this exact shape). A
        # dead/zero-health spawn gets no carve - the row stays in custody.
        log.warning("[vault] stale redeem FAILED verdict but delivered - finalising "
                    "sid=%s dino_id=%s cmd_id=%s actor=%s", sid, dino_id, cmd_id,
                    str((_status or {}).get("live_actor_name") or "?"))
        delivered = True
    elif not delivered and state == "none":
        if _world_holds_parked_dino(row):
            # The record aged out, but the player is standing in the world
            # holding this exact animal. The stored row is a leftover.
            log.warning("[vault] stale redeem has NO ledger record but the world "
                        "holds it - finalising sid=%s dino_id=%s cmd_id=%s",
                        sid, dino_id, cmd_id)
            delivered = True
        else:
            # No record and the world is not holding it, so this unlocks - which
            # is right when the restore never ran, and wrong when it ran and its
            # record has since aged out of the ring. The two are not tellable
            # apart here (the ring's own timestamps interleave two clocks, so
            # "how far back does it reach" cannot be answered). What keeps that
            # window shut is CADENCE: the sweep runs every two minutes, so a
            # marker is judged while its record still exists. A marker that
            # reaches this point old is therefore a fault in its own right, and
            # it is logged loudly rather than resolved quietly.
            age_ms = _now_ms() - int(row.get("redeem_pending_at") or 0)
            if age_ms > 30 * 60 * 1000:
                log.error("[vault] redeem resolved with NO evidence after %d min "
                          "- record aged out before anything judged it "
                          "sid=%s dino_id=%s cmd_id=%s redeem_unresolved",
                          int(age_ms / 60000), sid, dino_id, cmd_id)
    if delivered:
        # The restore actually granted the dino in-game after the verify job
        # died: complete the redeem exactly-once instead of unlocking a copy.
        if delete_if_redeem_cmd(dino_id, sid, cmd_id) == 1:
            record_redeem(sid)
            game_ipc.clear_swap_persist(sid)
            log.warning("[vault] stale redeem finalised late sid=%s dino_id=%s cmd_id=%s",
                        sid, dino_id, cmd_id)
            # The normal success path replays skin/SEX/diet onto the restored
            # pawn; this path never did, which returned the dino with the
            # throwaway spawn's sex (owner report 2026-07-30). Guarded inside:
            # replays only while the confirmed actor is still the live one.
            _schedule(_late_redeem_side_effects(sid, dict(row), _status))
            return None
        return get_parked_by_id(dino_id)
    if clear_redeem_pending(dino_id, sid, cmd_id) == 1:
        log.warning("[vault] stale redeem-pending auto-cleared sid=%s dino_id=%s cmd_id=%s state=%s",
                    sid, dino_id, cmd_id, state)
        row = dict(row)
        row["redeem_pending_cmd_id"] = None
        row["redeem_pending_at"] = None
        return row
    # Raced with a concurrent redeem/delete on the same row: re-read the truth.
    return get_parked_by_id(dino_id)


def sweep_stale_redeem_pending_once() -> dict:
    """Resolve every stale redeem marker, without waiting for the owner to come
    back to the site.

    resolve_stale_redeem_pending only ever ran when somebody happened to read
    that row, so a leftover could sit for hours (dino 6497 sat from 11:47).
    Nothing here decides anything new - it is the same judgement, applied on a
    timer instead of on a visit."""
    out = {"checked": 0, "finalised": 0, "unlocked": 0, "held": 0}
    conn = _connect_rw()
    try:
        rows = conn.execute(
            f"SELECT {_parked_select()} FROM parked_dinos "
            "WHERE redeem_pending_cmd_id IS NOT NULL AND redeem_pending_cmd_id != '' "
            "ORDER BY redeem_pending_at ASC"
        ).fetchall()
    finally:
        conn.close()
    for raw in rows:
        row = _row_to_dict(raw)
        if not row or _redeem_pending_fresh(row):
            continue  # still in flight; its own verify job owns it
        out["checked"] += 1
        dino_id = int(row.get("id") or 0)
        try:
            after = resolve_stale_redeem_pending(row)
        except Exception:
            log.exception("[vault] redeem sweep failed dino_id=%s", dino_id)
            out["held"] += 1
            continue
        if after is None:
            out["finalised"] += 1
        elif not str((after or {}).get("redeem_pending_cmd_id") or "").strip():
            out["unlocked"] += 1
        else:
            out["held"] += 1
    if out["checked"]:
        log.info("[vault] redeem sweep checked=%(checked)d finalised=%(finalised)d "
                 "unlocked=%(unlocked)d held=%(held)d" % out)
    return out


async def redeem_pending_sweep_loop(interval_secs: float = 120.0) -> None:
    """Startup + every two minutes. The ARMED line is deliberate: a lane that
    only speaks when it acts is undiagnosable when it silently dies."""
    log.info("[vault] redeem sweep ARMED interval=%ss", int(interval_secs))
    while True:
        try:
            await asyncio.to_thread(sweep_stale_redeem_pending_once)
        except Exception:
            log.exception("[vault] redeem sweep loop ok=False")
        await asyncio.sleep(interval_secs)


def cas_update_mutations(dino_id: int, steam_id: str,
                         expected: dict, new_strings: dict) -> tuple[bool, str]:
    """Write the three mutation columns under BEGIN IMMEDIATE, guarded on the
    OLD raw column values (optimistic CAS) so a concurrent edit / redeem can
    never be silently overwritten after the caller already charged coins.
    `expected` holds the raw values as read (None-safe); `new_strings` holds
    normalized full-segment "|"-strings. Returns (written, reason)."""
    conn = _connect_rw()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE parked_dinos SET mutations = ?, parent_mutations = ?, elder_mutations = ? "
            "WHERE id = ? AND steam_id = ? "
            "AND (redeem_pending_cmd_id IS NULL OR redeem_pending_cmd_id = '') "
            "AND IFNULL(mutations, '') = ? AND IFNULL(parent_mutations, '') = ? "
            "AND IFNULL(elder_mutations, '') = ?",
            (str(new_strings["mutations"]), str(new_strings["parent_mutations"]),
             str(new_strings["elder_mutations"]),
             int(dino_id), str(steam_id),
             str(expected.get("mutations") or ""),
             str(expected.get("parent_mutations") or ""),
             str(expected.get("elder_mutations") or "")),
        )
        n = int(cur.rowcount or 0)
        conn.execute("COMMIT")
        if n == 1:
            return True, ""
        return False, "state_changed"
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def delete_if_redeem_cmd(dino_id: int, steam_id: str, cmd_id: str) -> int:
    """Delete a restored row only while it still carries the winning cmd_id —
    this is what makes redeem exactly-once."""
    conn = _connect_rw()
    try:
        cur = conn.execute(
            "DELETE FROM parked_dinos WHERE id = ? AND steam_id = ? AND redeem_pending_cmd_id = ?",
            (int(dino_id), str(steam_id), str(cmd_id)),
        )
        return int(cur.rowcount or 0)
    finally:
        conn.close()


# ── cooldown files (shared on-disk with the bot, in DATA_DIR) ─────────────────
_cooldown_lock = Lock()


def _read_cooldown_map(path: str) -> dict:
    data = game_ipc.read_json_file(path)
    return data if isinstance(data, dict) else {}


def _trim_cooldown_map(data: dict, cooldown_secs: int, now: float) -> dict:
    out: dict[str, float] = {}
    for sid, raw in data.items():
        sid = str(sid or "").strip()
        if not sid:
            continue
        try:
            ts = float(raw)
        except (TypeError, ValueError):
            continue
        if ts > 0 and now - ts < cooldown_secs:
            out[sid] = ts
    return out


def _write_cooldown_map(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, path)


def _record_cooldown(path: str, steam_id: str, cooldown_secs: int) -> None:
    with _cooldown_lock:
        now = time.time()
        data = _trim_cooldown_map(_read_cooldown_map(path), cooldown_secs, now)
        data[str(steam_id)] = now
        _write_cooldown_map(path, data)


def _cooldown_remaining(path: str, steam_id: str, cooldown_secs: int) -> int:
    if not steam_id or cooldown_secs <= 0:
        return 0
    data = _read_cooldown_map(path)
    last = float(data.get(str(steam_id), 0) or 0)
    elapsed = time.time() - last
    return 0 if elapsed >= cooldown_secs else int(cooldown_secs - elapsed)


def slay_cooldown_remaining(sid: str) -> int:
    return _cooldown_remaining(game_ipc.SLAY_COOLDOWNS_JSON, sid, SLAY_COOLDOWN_SECS)


def record_slay(sid: str) -> None:
    try:
        _record_cooldown(game_ipc.SLAY_COOLDOWNS_JSON, sid, SLAY_COOLDOWN_SECS)
    except OSError:
        log.warning("[vault] slay cooldown write failed sid=%s", sid)


def redeem_cooldown_remaining(sid: str) -> int:
    return _cooldown_remaining(game_ipc.REDEEM_COOLDOWNS_JSON, sid, REDEEM_COOLDOWN_SECS)


def record_redeem(sid: str) -> None:
    try:
        _record_cooldown(game_ipc.REDEEM_COOLDOWNS_JSON, sid, REDEEM_COOLDOWN_SECS)
    except OSError:
        log.warning("[vault] redeem cooldown write failed sid=%s", sid)


def _wait_text_es(secs: int) -> str:
    """Short Spanish wait for a sub-hour cooldown. Seconds under a minute so a
    2-minute wait never reads as a flat '1 min' for 59 of its last 60 seconds."""
    secs = max(0, int(secs))
    if secs < 60:
        return f"{secs} s"
    return f"{(secs + 59) // 60} min"


def _park_cooldowns_path() -> str:
    """Resolved per call off the LIVE game_ipc.DATA_DIR rather than frozen at
    import: a rebound DATA_DIR (test lanes do exactly this) must not leave the
    park wait writing into the real data directory."""
    return os.path.join(game_ipc.DATA_DIR, "park_cooldowns.json")


def park_cooldown_remaining(sid: str) -> int:
    return _cooldown_remaining(_park_cooldowns_path(), sid, PARK_COOLDOWN_SECS)


def record_park(sid: str) -> None:
    # Never fail a completed park on a cooldown write: the dino is already
    # stored, and a missing stamp costs one early re-park, not a lost dino.
    try:
        _record_cooldown(_park_cooldowns_path(), sid, PARK_COOLDOWN_SECS)
    except OSError:
        log.warning("[vault] park cooldown write failed sid=%s", sid)


# ── Body Drop feeder lease (the GAME owns this cooldown; we only read it) ─────
# Unlike slay/redeem above, there is no web-side cooldown map to write: the mod
# writes cpp_corpse_feeder_lease.txt and is the authority. What IS re-implemented
# here is the mod's own retention rule (main.full.lua FeederLeaseLoadLocked), so
# the two can never disagree about whether a row is still live — a row the mod
# would already have dropped must never block a player on the website.
_BODYDROP_PENDING_TTL_MS = 30_000     # corpseSpawnState.pendingTtl, 30 s
# A "fed" lease is released the instant the MOD's clock passes cooldown_until_ms.
# ★ Load-bearing: the web must NEVER refuse a lease the mod would have released.
# Inside the last 2 s we stop being certain the lease is still held, so the
# request goes to the game and the game decides. This epsilon is the whole
# reason a local pre-gate is safe; without it the web starts inventing refusals
# in the final second of every cooldown.
BODYDROP_COOLDOWN_EPS_MS = 2000
# Distinct from 0 (free) and from any positive ms wait: a drop is already coming.
BODYDROP_PENDING = -1
# The mod's lease is CORPSE_COOLDOWN = 600 s. A row claiming more than this is
# corrupt, not a very long cooldown, and "corrupt" has exactly one safe reading:
# fall through to the game. Without this clamp a garbled stamp becomes a refusal
# measured in centuries — the one path where an unknown would refuse a player.
_BODYDROP_LEASE_MAX_MS = 900_000

_bodydrop_lease_reader_warned = False
_bodydrop_lease_error_warned = False


def _bodydrop_lease_state(sid: str) -> tuple[str, int, str]:
    """('', 0, '') no live lease | ('fed'|'pending', ms_left, lane).

    ``lane`` is "lua" when the AUTOMATIC feeder spent this lease and "web" when
    the player asked for it — both lanes share one key, so the copy has to be
    able to tell them apart even though the refusal is identical.

    Fails OPEN to ('', 0, '') on every unknown — a game_ipc without the reader,
    an unreadable file, a torn row, a junk stamp, an out-of-range cooldown.
    "I don't know" must always mean "let the game decide", never "refuse the
    player"."""
    global _bodydrop_lease_reader_warned, _bodydrop_lease_error_warned
    if not sid:
        return ("", 0, "")
    reader = getattr(game_ipc, "read_feeder_lease", None)
    if reader is None:
        # Mixed web trees on the box: a game_ipc.py without the lease reader
        # degrades to the old round-trip behaviour instead of 500ing the lane.
        if not _bodydrop_lease_reader_warned:
            _bodydrop_lease_reader_warned = True
            log.warning("[vault] bodydrop pre-gate OFF — game_ipc has no read_feeder_lease")
        return ("", 0, "")
    try:
        row = reader(sid)
        if not isinstance(row, dict):
            return ("", 0, "")
        state = str(row.get("state") or "")
        ts_ms = int(row.get("ts_ms") or 0)
        cd_ms = int(row.get("cooldown_until_ms") or 0)
        lane = "lua" if str(row.get("spawn_id") or "").startswith("lua:") else "web"
    except Exception:
        # LATCHED: this sits under summary(), which every panel polls every ~8 s.
        # One corrupt byte in a shared file would otherwise write a traceback per
        # player per poll — tens of thousands of lines an hour on a box whose mod
        # log has hit 25 MB before.
        if not _bodydrop_lease_error_warned:
            _bodydrop_lease_error_warned = True
            log.warning("[vault] bodydrop lease read failed sid=%s — deferring to the game",
                        sid, exc_info=True)
        return ("", 0, "")
    now_ms = int(time.time() * 1000)
    # Retention, verbatim from the mod: a pending row counts only inside its 30 s
    # TTL and only while the cooldown it claimed is still ahead of us; a fed row
    # counts only until that cooldown expires.
    if state == "pending":
        if ts_ms <= 0 or now_ms < ts_ms or (now_ms - ts_ms) >= _BODYDROP_PENDING_TTL_MS:
            return ("", 0, "")
        left = cd_ms - now_ms
        if cd_ms <= 0 or left <= 0 or left > _BODYDROP_LEASE_MAX_MS:
            return ("", 0, "")
        return ("pending", left, lane)
    if state == "fed":
        left = cd_ms - now_ms
        if cd_ms <= 0 or left <= 0 or left > _BODYDROP_LEASE_MAX_MS:
            return ("", 0, "")
        return ("fed", left, lane)
    return ("", 0, "")


def bodydrop_cooldown_remaining(sid: str) -> int:
    """Milliseconds left on the mod's per-SteamID Body Drop feeder lease:
    0 = free, > 0 = wait that long, BODYDROP_PENDING = a drop is already in
    flight for this player. Same shape as slay_/redeem_cooldown_remaining, but
    the source of truth is the GAME's lease file, not a web-owned map."""
    state, ms, _lane = _bodydrop_lease_state(str(sid or "").strip())
    if state == "pending":
        return BODYDROP_PENDING
    return ms if state == "fed" else 0


def _bodydrop_wait_secs(lease_ms: int) -> int:
    """ms of lease left -> whole seconds the player still has to wait, epsilon
    already taken off. ONE place on purpose: the greyed button's countdown and
    the refusal copy are both derived from this, so they can never disagree by
    a minute on the same request."""
    ms = int(lease_ms) - BODYDROP_COOLDOWN_EPS_MS
    return 0 if ms <= 0 else int((ms + 999) // 1000)


def bodydrop_cooldown_secs(sid: str) -> int:
    """Whole seconds the panel should keep the Body Drop button greyed — the
    SAME verdict do_bodydrop enforces, epsilon included, so the UI can never
    offer a click the API is about to refuse. Mirrors slay_cooldown_s: int
    seconds, 0 = ready."""
    _state, ms, _lane = _bodydrop_lease_state(str(sid or "").strip())
    return _bodydrop_wait_secs(ms)


# ── restore_status.json ack gates (port bot-src/dino.py) ──────────────────────
def _finite_float(value) -> float | None:
    """float() that refuses NaN/inf — a NaN would silently pass every `>` guard
    in the decayed-vitals check below. Ported from the Arkadia donor."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _restore_decayed_vitals_ok(s: dict | None) -> bool:
    """★THE DUPE FIX — web twin of bot dino.py `_restore_status_decayed_vitals_
    success`, ported 1:1 from Arkadia (live there). A redeem whose ONLY failure
    is post-restore vital DECAY is a real success: the dino DID come back, the
    bar just drained between the write and the mod's live re-observation. The
    mod preserves the vault row on any failure (by design, against data loss) —
    but on a delivered dino that preserved row IS the duplicate: the player has
    the dino in-game and can park or redeem the same row again.

    Two classes, same growth/max/ack guards, different near-max requirement:
      legacy (hunger/thirst not full)  : health & stamina must still be near max.
      new    (stamina/health not full) : NO near-max requirement — that decay is
                                         exactly the false-fail being fixed (a
                                         flying Ptera or swimming Deino burns
                                         stamina far past the 2 % tolerance).
    Every no-delivery reason (actor_missing, growth_mismatch, max_stats_missing,
    read_failed, apply_stats_no_ack, not_ready_timeout, timeout) still fails
    definitively and still keeps the row."""
    if not isinstance(s, dict) or s.get("dropped"):
        return False
    reason = str(s.get("fail_reason") or s.get("live_vitals_reason") or "")
    legacy_reasons = {
        "live_vitals_failed:hunger_not_full", "live_vitals_failed:thirst_not_full",
        "hunger_not_full", "thirst_not_full",
    }
    new_reasons = {
        "live_vitals_failed:stamina_not_full", "stamina_not_full",
        "live_vitals_failed:health_not_full", "health_not_full",
    }
    is_legacy = reason in legacy_reasons
    is_new = reason in new_reasons
    if not (is_legacy or is_new):
        return False
    # Shared guards: the C++ apply_stats ack landed for THIS cmd, no
    # mutation/prime apply failure, the live pawn still reads the stored growth,
    # and hunger/thirst maxes + values are positive (a live, fed pawn).
    if s.get("stats_ack_ok") is not True:
        return False
    if s.get("mutation_apply_ok") is False:
        return False
    if s.get("prime_apply_ok") is False:
        return False
    expected = _finite_float(s.get("live_growth_expected"))
    observed = _finite_float(s.get("live_growth_observed"))
    if expected is None or observed is None or abs(observed - expected) > 0.02:
        return False
    max_hunger = _finite_float(s.get("max_hunger_observed"))
    max_thirst = _finite_float(s.get("max_thirst_observed"))
    if max_hunger is None or max_hunger <= 0 or max_thirst is None or max_thirst <= 0:
        return False
    hunger = _finite_float(s.get("hunger_observed"))
    thirst = _finite_float(s.get("thirst_observed"))
    if hunger is None or hunger <= 0 or thirst is None or thirst <= 0:
        return False
    if is_legacy:
        # hunger/thirst were the false-fail; health & stamina must still be near max.
        for value_field, max_field in (
            ("health_observed", "max_health_observed"),
            ("stamina_observed", "max_stamina_observed"),
        ):
            value = _finite_float(s.get(value_field))
            maximum = _finite_float(s.get(max_field))
            if value is None or maximum is None or maximum <= 0:
                return False
            if value + max(2.0, maximum * 0.02) < maximum:
                return False
        return True
    # new class: stamina/health decay IS the false-fail — no near-max requirement.
    # Require positive maxes and a LIVING dino (health > 0); stamina may be 0.
    max_health = _finite_float(s.get("max_health_observed"))
    max_stamina = _finite_float(s.get("max_stamina_observed"))
    if max_health is None or max_health <= 0 or max_stamina is None or max_stamina <= 0:
        return False
    health = _finite_float(s.get("health_observed"))
    if health is None or health <= 0:
        return False
    return True


def _restore_status_ok(s: dict | None) -> bool:
    if not isinstance(s, dict) or s.get("dropped"):
        return False
    event = str(s.get("event") or "").strip()
    decayed_restore = _restore_decayed_vitals_ok(s)
    if event != "restore" and not decayed_restore:
        return False
    new_stats_ok = s.get("stats_ok")
    new_max_obs = s.get("max_stats_observed_ok")
    if bool(
        s.get("prime_ok") is True
        and s.get("mutations_ok") is True
        and s.get("growth_ok") is True
        and (new_stats_ok is None or new_stats_ok is True)
        and (new_max_obs is None or new_max_obs is True)
    ):
        return True
    return decayed_restore


def _restore_terminal(s: dict | None) -> bool:
    if not isinstance(s, dict):
        return False
    ev = str(s.get("event") or "").strip()
    return ev in ("restore", "restore_failed") or s.get("definitive_failure") is True


def _restore_definitive_failure(s: dict | None) -> bool:
    if not isinstance(s, dict):
        return False
    return str(s.get("event") or "").strip() == "restore_failed" or s.get("definitive_failure") is True


def _restore_reached_world(s: dict | None) -> bool:
    """Did the animal actually arrive in the world on this restore?

    This is the ONLY question that decides whether a redeem may be unlocked.
    The mod names the live actor it found and reads that actor's growth back;
    either one is proof the player is holding the dino. Cosmetic verifications
    that ticked late or not at all (prime_final_verify_ok) do NOT take the dino
    back out of their hands, so they must never unlock the stored copy.
    """
    if not isinstance(s, dict):
        return False
    actor = str(s.get("live_actor_name") or s.get("actor_name") or "").strip()
    if actor:
        return True
    return _finite_float(s.get("live_growth_observed")) is not None


def _world_holds_parked_dino(row: dict | None) -> bool:
    """Last-resort world check for a redeem whose ledger entry is GONE.

    Same owner, same species, same growth = they are holding it right now.
    A negative here proves nothing (they may have switched dinos since), so it
    is only ever used to CONFIRM delivery, never to rule it out.
    """
    if not isinstance(row, dict):
        return False
    sid = str(row.get("steam_id") or "").strip()
    if not sid:
        return False
    try:
        live = game_ipc.read_player_live(sid)
    except Exception:
        log.exception("[vault] world check failed sid=%s", sid)
        return False  # unknown is never treated as proof
    if not isinstance(live, dict) or not _is_online(live):
        return False
    live_class = str(live.get("dino") or live.get("dino_class") or "").strip()
    if not live_class or live_class != str(row.get("dino_class") or "").strip():
        return False
    lg, sg = _finite_float(live.get("growth")), _finite_float(row.get("growth"))
    if lg is None or sg is None:
        return False
    return abs(lg - sg) <= 0.005


def _restore_terminal_state(cmd_id: str, sid: str, dino_id: int) -> tuple[str, dict | None]:
    for item in reversed(game_ipc.read_restore_entries()):
        if str(item.get("cmd_id") or "").strip() != str(cmd_id):
            continue
        if str(item.get("steamid", "")).strip() != str(sid):
            continue
        try:
            if int(item.get("dino_id", -1)) != int(dino_id):
                continue
        except (TypeError, ValueError):
            continue
        if not _restore_terminal(item):
            continue
        # ★ORDER IS LOAD-BEARING, DO NOT "FIX" IT. _restore_status_ok is asked
        # FIRST on purpose: the mod marks a restore failed on ANY post-delivery
        # gate and preserves the vault row against data loss, and
        # _restore_decayed_vitals_ok is the deliberate carve-out that overrides
        # that refusal for a dino which DID come back. Judging the refusal first
        # turns every delivered-but-decayed redeem back into a duplicate - 22 of
        # 127 finished redeems on this box. Every genuine no-delivery reason
        # (actor_missing, growth_mismatch, apply_stats_no_ack, timeouts) is
        # excluded inside that carve-out and still lands as "failed" below.
        if _restore_status_ok(item):
            return "success", item
        if _restore_definitive_failure(item):
            return "failed", item
        return "ambiguous", item
    return "none", None


# ── liveness helpers ──────────────────────────────────────────────────────────
def _is_online(row: dict | None) -> bool:
    if not isinstance(row, dict):
        return False
    try:
        ts = float(row.get("last_updated") or 0)
    except (TypeError, ValueError):
        return False
    if ts > 1e11:
        ts /= 1000.0
    return (time.time() - ts) <= LIVE_FRESH_SECS


def _pct(row: dict, cur: str, mx: str) -> float | None:
    try:
        m = float(row.get(mx) or 0)
        if m > 0:
            return float(row.get(cur) or 0) / m
    except Exception:
        pass
    return None


# ── the mod acked, but did it actually kill anything? ─────────────────────────
# ★★★★★ THE PARK DUPE DOOR, closed 2026-08-19.
#
# The mod's kill handler short-circuits when the pawn reads not-alive or
# health<=0: it emits kill_ok with kill_verified=true and NEVER dispatches a
# kill -- and, because that branch returns before the else, it never runs the
# crash-dupe owner gate either. The game's own safe-log ("put the dino to
# sleep") drives the pawn to exactly alive=false / hp=0.0, so a player who hits
# Guardar as the sleep timer reaches 0 banks the animal in the vault while the
# engine's logout save keeps it alive in-world. Repeatable at will.
#
# The two emitters are distinguishable BY CONSTRUCTION, not by guesswork. The
# live bytecode holds exactly two `event="kill_ok"` sites:
#
#   short-circuit : prime_ok=true, mutations_ok=true, growth_ok=true (literals)
#   honest        : those three omitted -> false; emitted ONLY after the mod's
#                   own players poll observes health<=0 with a live kill stash
#
# and the C++ EmitKillOk never sets kill_verified. Measured on the live ring:
# (kill_verified, prime_ok) = (True,False) x98 honest, (True,True) x12
# short-circuit, (False,True) x98 C++. So the pair below is a positive "no",
# never an inference from absence.
# LAW: memory/feedback_gate_on_a_positive_no_capability_signal_never_on_absence.md
def _kill_ack_unkilled(ack: dict | None) -> bool:
    """True iff this kill_ok is the mod's already-dead short-circuit -- an ack
    for a kill that was never dispatched. Errors answer False: an unreadable
    ack is judged by the caller's other walls, never silently treated as fraud.
    """
    if not isinstance(ack, dict):
        return False
    if not ack.get("kill_verified"):
        return False
    try:
        return bool(ack.get("prime_ok")) and bool(ack.get("mutations_ok")) \
            and bool(ack.get("growth_ok"))
    except Exception:
        return False


# How long a park keeps waiting for an HONEST ack once it has seen only
# short-circuit ones. A re-processed kill command can emit the short-circuit ack
# after the honest one, so we must not refuse on the first sighting; but the mod
# will never dispatch a kill for this command now, so waiting the full
# PARK_ACK_TIMEOUT_SECS just leaves the player watching a spinner.
_UNKILLED_ACK_GRACE_SECS = 15.0

_PARK_UNKILLED_MSG = (
    "Tu dino no estaba activo en la partida cuando pulsaste Guardar — estaba "
    "durmiendo, cerrando sesión o muriendo. No se guardó nada y tu dino sigue "
    "como estaba. Inténtalo de nuevo mientras juegas con normalidad."
)


# ── gate evaluation (Spanish; mirror the bot's thresholds) ────────────────────
def park_gate_failures(row: dict | None) -> list[str]:
    if not _is_online(row):
        return ["No estás en partida (o tus datos están desactualizados)."]
    fails: list[str] = []
    if not str(row.get("actor_name") or "").strip():
        fails.append("Tu dino aún no está listo.")
    if not (float(row.get("max_health") or 0) > 0 and float(row.get("max_stamina") or 0) > 0
            and float(row.get("max_hunger") or 0) > 0):
        return ["El servidor aún no cargó las estadísticas de tu dino. Espera unos segundos."]
    g = float(row.get("growth") or 0)
    hp, st, hg = _pct(row, "health", "max_health"), _pct(row, "stamina", "max_stamina"), _pct(row, "hunger", "max_hunger")
    if g < PARK_MIN_GROWTH:
        fails.append(f"Crecimiento {g*100:.0f}% — necesitas {PARK_MIN_GROWTH*100:.0f}%")
    if hp is not None and hp < PARK_MIN_HEALTH_PCT - _PCT_GATE_EPS:
        # One decimal on the current value: with the 100% requirement, a 99.6%
        # dino must never read "Salud 100% — necesitas 100%".
        fails.append(f"Salud {hp*100:.1f}% — necesitas {PARK_MIN_HEALTH_PCT*100:.0f}%")
    if st is not None and st < PARK_MIN_STAMINA_PCT - _PCT_GATE_EPS:
        fails.append(f"Energía {st*100:.0f}% — necesitas {PARK_MIN_STAMINA_PCT*100:.0f}%")
    if hg is not None and hg < PARK_MIN_HUNGER_PCT - _PCT_GATE_EPS:
        fails.append(f"Hambre {hg*100:.0f}% — necesitas {PARK_MIN_HUNGER_PCT*100:.0f}%")
    return fails


def redeem_gate_failures(row: dict | None, parked: dict) -> list[str]:
    if not _is_online(row):
        return ["No estás en partida."]
    fails: list[str] = []
    cur_class = str(row.get("dino") or "")
    want_class = str(parked.get("dino_class") or "")
    if want_class and cur_class != want_class:
        fails.append(f"Eres {_friendly(cur_class)} — necesitas estar como {_friendly(want_class)}")
    hp, st, hg = _pct(row, "health", "max_health"), _pct(row, "stamina", "max_stamina"), _pct(row, "hunger", "max_hunger")
    if hp is not None and hp < REDEEM_MIN_HEALTH_PCT:
        fails.append(f"Demasiado herido: Salud {hp*100:.0f}% — necesitas {REDEEM_MIN_HEALTH_PCT*100:.0f}%")
    if st is not None and st < REDEEM_MIN_STAMINA_PCT:
        fails.append(f"Demasiado cansado: Energía {st*100:.0f}% — necesitas {REDEEM_MIN_STAMINA_PCT*100:.0f}%")
    if hg is not None and hg < REDEEM_MIN_HUNGER_PCT:
        fails.append(f"Demasiada hambre: {hg*100:.0f}% — necesitas {REDEEM_MIN_HUNGER_PCT*100:.0f}%")
    return fails


# ── job store (in-memory background park/redeem progress) ─────────────────────
_jobs: dict[str, dict] = {}
_jobs_lock = Lock()
_JOB_TTL = 600.0


def _prune_jobs(now: float) -> None:
    for k in [k for k, v in _jobs.items() if now - v.get("updated", now) > _JOB_TTL]:
        _jobs.pop(k, None)


def _new_job(kind: str, steam_id: str = "") -> str:
    jid = uuid.uuid4().hex
    now = time.time()
    with _jobs_lock:
        _prune_jobs(now)
        _jobs[jid] = {"kind": kind, "state": "pending", "message": "En progreso…",
                      "steam_id": str(steam_id), "created": now, "updated": now}
    return jid


def _set_job(jid: str, state: str, message: str, **extra) -> None:
    with _jobs_lock:
        j = _jobs.get(jid)
        if j:
            j.update(state=state, message=message, updated=time.time(), **extra)


def get_job(jid: str) -> dict | None:
    with _jobs_lock:
        j = _jobs.get(jid)
        return dict(j) if j else None


# ── single-flight action claim (SweetScales / FangsAndFerns `_claim_action`) ───
# ★THE SECOND DUPE PATH. `/me/vault/park` is a SYNC route, so FastAPI runs it in
# the threadpool and two clicks land in two real threads. Both pass the same live
# gate, both write a `kill`, both watch the SAME death, and both save a row —
# live prod rows 1030/1031 are one Deinosuchus stored twice, 0.09 s apart, same
# growth and same mutations. The bot's Discord park already has this guard
# (`_park_locks`, "You are already parking a dino"); the website never got it.
# One uvicorn worker (`--workers 1`), so an in-process claim is a real guard.
_action_inflight: dict[tuple[str, str], float] = {}
_action_inflight_lock = Lock()
# A claim must never be able to wedge a player out of parking forever. The park
# job's own ceiling is PARK_ACK_TIMEOUT_SECS (90 s) plus the save, so anything
# older than this is not a live job — it is a leak (a background task that was
# never scheduled because the loop was gone), and the next click takes it over.
_ACTION_CLAIM_TTL_SECS = 180.0


def _claim_action(kind: str, steam_id: str) -> tuple[str, str]:
    key = (str(kind), str(steam_id))
    now = time.time()
    with _action_inflight_lock:
        for stale in [k for k, at in _action_inflight.items() if now - at > _ACTION_CLAIM_TTL_SECS]:
            _action_inflight.pop(stale, None)
            log.warning("[vault] stale action claim reclaimed kind=%s sid=%s", stale[0], stale[1])
        if key in _action_inflight:
            if str(kind) == "Park":
                raise HTTPException(
                    409, "Ya estás guardando un dino. Espera a que termine el intento anterior.")
            raise HTTPException(409, f"Ya hay una acción de {kind} en progreso.")
        _action_inflight[key] = now
    return key


def _release_action(key: tuple[str, str] | None) -> None:
    if key is None:
        return
    with _action_inflight_lock:
        _action_inflight.pop(key, None)


# ── snapshot / list / slay / delete ───────────────────────────────────────────
_SKIN_VIEW_COLOR_KEYS = ("body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display")
_SKIN_POISON_THRESHOLD = -900000.0


def _parked_skin(skin_data) -> dict | None:
    """{pattern, colors:{body,...,male_display}} for a parked row's skin_data JSON
    (the verbatim skin_snapshots.json entry captured at park time), or None when
    absent, malformed, or sentinel-poisoned. Poisoned = ANY color component
    <= -900000 -- the fleet color-only rule: a park taken between a server
    restart and the player's skin re-apply captures the unset-sentinel family
    (-999999 colors); those must never render as real colors. Negative PATTERNS
    are legitimate glitch skins and are NOT grounds for rejection."""
    raw = str(skin_data or "").strip()
    if not raw:
        return None
    try:
        snap = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(snap, dict):
        return None
    colors = {}
    for key in _SKIN_VIEW_COLOR_KEYS:
        val = snap.get(key)
        if not isinstance(val, (list, tuple)) or not val:
            continue
        try:
            comps = [float(c) for c in val]
        except (TypeError, ValueError):
            continue
        if any(c <= _SKIN_POISON_THRESHOLD for c in comps):
            return None
        colors[key] = list(val)
    if not colors:
        return None
    return {"pattern": snap.get("pattern"), "colors": colors}


def _skin_norm_class(value) -> str:
    return (str(value or "").replace("BP_", "").replace("_C", "")
            .strip().lower())


def _park_skin_preferring_recipe(steam_id: str, parked_dino: str,
                                 snapshot_json: str) -> tuple:
    """SKIN-5 fleet port, web twin of bot dino._park_skin_preferring_recipe
    (2026-08-07; Isla Segunda donor 2026-08-02 - keep the twins in step):
    choose what park stores as skin_data. The ledger snapshot lags queued
    paints, the engine repaints DEFAULT on stat re-inits, and a snapshot
    readback flattens glitch values - while the player's ACTIVE SkinKeeper
    recipe is the exact original apply bytes, updated on every apply and
    retired on death. When an active recipe exists for this class it is the
    truer capture. SEX-MERGE: the recipe carries preserve_female=True (the
    mod then keeps the redeem spawn's sex), while the snapshot's female field
    is the parked truth with no preserve flag - so the recipe's colours are
    merged with the snapshot's sex authority (and ancestry), or the redeem
    replay would stop restoring the parked sex (owner report 2026-07-30).
    Read-only; fails OPEN to the snapshot on any error; returns
    (skin_json, source) with source in {'recipe', 'snapshot'}."""
    try:
        import sqlite3

        import skinkeeper_shared

        sid = skinkeeper_shared.clean_sid(steam_id)
        cls = str(parked_dino or "").strip()
        if not sid or not cls:
            return snapshot_json, "snapshot"
        conn = sqlite3.connect(game_ipc.BOT_DB_PATH, timeout=10)
        try:
            conn.execute("PRAGMA busy_timeout=8000")
            if not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='skin_last_applied'").fetchone():
                return snapshot_json, "snapshot"
            row = conn.execute(
                "SELECT dino_class, payload, active FROM skin_last_applied "
                "WHERE steam_id = ?", (sid,)).fetchone()
        finally:
            conn.close()
        if not row or int(row[2] or 0) != 1:
            return snapshot_json, "snapshot"
        if _skin_norm_class(row[0]) != _skin_norm_class(cls):
            return snapshot_json, "snapshot"
        recipe_cmd = json.loads(str(row[1] or ""))
        if not isinstance(recipe_cmd, dict) or not recipe_cmd:
            return snapshot_json, "snapshot"
        try:
            snap = json.loads(str(snapshot_json or ""))
        except (TypeError, ValueError):
            snap = None
        if isinstance(snap, dict):
            if "female" in snap:
                recipe_cmd["female"] = snap["female"]
                recipe_cmd.pop("preserve_female", None)
            for k in ("anc_key", "ancestors"):
                if k in snap and k not in recipe_cmd:
                    recipe_cmd[k] = snap[k]
        return json.dumps(recipe_cmd, separators=(",", ":")), "recipe"
    except Exception:
        log.warning("[SkinKeeper] park capture recipe preference failed; "
                    "using ledger snapshot", exc_info=True)
        return snapshot_json, "snapshot"


def _revive_skin_recipe_after_redeem(steam_id: str, parked_dino: str,
                                     confirmed_actor: str) -> str:
    """SkinKeeper revive-at-redeem, web twin of bot
    dino._revive_skin_recipe_after_success (2026-08-07; Isla Segunda donor):
    the park kill retired the player's recipe via the death lane, and the
    redeem replay repaints only THIS session - a snapshot readback is
    flattened for glitch values, so it must never be recorded as a recipe.
    When the stored recipe's class matches the redeemed class, re-activate
    the stored recipe (exact original apply bytes) as kind='redeem' and stamp
    the confirmed redeemed actor, so the next relog / server restart repaints
    the true look. Sync (call via asyncio.to_thread); returns the outcome
    string; never raises."""
    try:
        import sqlite3
        from datetime import datetime, timezone

        import skinkeeper_shared

        sid = skinkeeper_shared.clean_sid(steam_id)
        cls = str(parked_dino or "").strip()
        if not sid or not cls:
            return "bad_args"
        actor = str(confirmed_actor or "").strip()
        if actor and not actor.startswith(cls + "_"):
            actor = ""
        conn = sqlite3.connect(game_ipc.BOT_DB_PATH, timeout=10)
        try:
            conn.execute("PRAGMA busy_timeout=8000")
            skinkeeper_shared.ensure_skin_last_applied(conn)
            row = conn.execute(
                "SELECT dino_class, kind, active FROM skin_last_applied "
                "WHERE steam_id = ?", (sid,)).fetchone()
            if not row:
                return "no_recipe"
            rec_class, rec_kind, rec_active = str(row[0]), str(row[1]), int(row[2] or 0)
            if _skin_norm_class(rec_class) != _skin_norm_class(cls):
                return "class_mismatch recipe=%s redeemed=%s" % (rec_class, cls)
            now_utc = datetime.now(timezone.utc).isoformat()
            if actor:
                cur = conn.execute(
                    "UPDATE skin_last_applied SET active = 1, kind = 'redeem', "
                    "updated_utc = ?, actor_name = ? WHERE steam_id = ?",
                    (now_utc, actor, sid))
            else:
                cur = conn.execute(
                    "UPDATE skin_last_applied SET active = 1, kind = 'redeem', "
                    "updated_utc = ? WHERE steam_id = ?", (now_utc, sid))
            conn.commit()
            return ("revived prev_kind=%s prev_active=%d rows=%d actor=%s"
                    % (rec_kind, rec_active, cur.rowcount, actor or "kept"))
        finally:
            conn.close()
    except Exception:
        log.warning("[SkinKeeper] redeem revive failed", exc_info=True)
        return "error"


_RECIPE_SLOT_KEYS = ("body", "markings", "flank", "underbelly", "detail1",
                     "eyes", "male_display")


def _parked_skin_recipe_grade(cmd: dict) -> str:
    """'' when the parked skin_data is provably WEBSITE-APPLY bytes and safe to
    record as the player's recipe; else the refusal reason. color_space present
    is the regular site-apply contract, and so is a non-empty skin_code (only
    site commands carry one). A colour channel outside [0,1] is true glitch
    bytes (a snapshot READBACK is flattened in-range by ReadSkin, so an extreme
    proves original apply bytes). A non-finite channel refuses outright
    (json.dumps would emit Infinity and poison the stored payload).
    2026-08-10 FOLD RECEIPT: the HDR-band wave ended >1.0 overshoot on regular
    applies, so an overshoot no longer identifies a readback of OUR OWN paint
    (the heal folded 500 such parked rows in-range - grading them by the old
    rule loses the player's look at redeem). Its durable replacement is the
    emitter's own arithmetic: site paint jitters every saturated pick DOWNWARD
    to 1.0-eps (eps in [1e-4,1e-3]), so our readbacks carry a top channel
    inside [0.9989, 0.99995] - a band the engine's native variation measurably
    never writes (0/1315 native-labeled parked rows; ground truth = the
    pass-2 heal backup, 500/500 healed rows carry it) and the rails of native
    or flattened bytes (exact 0.0 / exact 1.0) cannot enter. variation exactly
    0.0 (the glitch shader's own trigger) still refuses ahead of the receipt.
    In-range markerless rows WITHOUT the receipt stay refused: engine-native
    births and flattened glitch readbacks - freezing those as a recipe is the
    exact defect the capture exclusion exists to prevent (skinkeeper_web
    module docstring). TWIN of bot dino.py::_parked_skin_recipe_grade -
    keep the twins in step."""
    import math

    extreme = False
    fold_top = False
    for key in _RECIPE_SLOT_KEYS:
        v = cmd.get(key)
        if isinstance(v, dict):
            v = list(v.values())
        if not isinstance(v, (list, tuple)):
            continue
        for idx, ch in enumerate(v):
            if isinstance(ch, bool) or not isinstance(ch, (int, float)):
                continue
            x = float(ch)
            if not math.isfinite(x):
                return "non_finite_channel"
            if x < 0.0 or x > 1.0:
                extreme = True
            elif idx < 3 and 0.9989 <= x <= 0.99995:
                fold_top = True     # RGB only: alpha never carries the receipt
    if "color_space" in cmd or extreme:
        return ""
    if cmd.get("skin_code"):
        return ""
    try:
        glitch_variation = float(cmd.get("variation", 0.5)) == 0.0
    except (TypeError, ValueError):
        glitch_variation = False
    if fold_top and not glitch_variation:
        return ""
    return "in_range_no_marker"


def _record_parked_recipe_fallback(steam_id: str, parked_dino: str,
                                   confirmed_actor: str, skin_data: str) -> str:
    """SkinKeeper record-at-redeem fallback, web twin of bot
    dino._record_parked_recipe_fallback (2026-08-07 - keep the twins in step):
    the revive lane can only re-arm a stored recipe whose class matches the
    redeemed dino, and the store is one row per player, so a redeem onto a
    DIFFERENT species (or a player with no recorded row) still lost its look
    at the next relog. When the parked skin_data is provably website-apply
    bytes (_parked_skin_recipe_grade) it IS the exact recipe the redeem paint
    replays, so record it as the active recipe kind='redeem'. A same-class
    stored row is ALWAYS left to the revive lane (its payload is the truer
    original-apply bytes), so the two lanes can never fight. Never records a
    flattened readback or an engine-native palette. Sync (call via
    asyncio.to_thread); returns the outcome string; never raises."""
    try:
        import sqlite3
        from datetime import datetime, timezone

        import skinkeeper_shared

        def _norm(v):
            return (str(v or "").replace("BP_", "").replace("_C", "")
                    .strip().lower())

        sid = skinkeeper_shared.clean_sid(steam_id)
        cls = str(parked_dino or "").strip()
        if not sid or not cls:
            return "bad_args"
        raw = str(skin_data or "").strip()
        if not raw:
            return "no_skin_data"
        try:
            cmd = json.loads(raw)
        except (ValueError, TypeError):
            return "bad_skin_data"
        if not isinstance(cmd, dict) or not cmd:
            return "bad_skin_data"
        grade = _parked_skin_recipe_grade(cmd)
        if grade:
            return "skipped reason=%s" % grade
        actor = str(confirmed_actor or "").strip()
        if actor and not actor.startswith(cls + "_"):
            actor = ""
        recipe = skinkeeper_shared.canonical_recipe(cmd)
        for k in ("ancestors", "anc_key"):
            # Park-merge extras (ancestry riders for the redeem replay), not
            # part of any apply recipe - a rejoin repaint must not carry them.
            recipe.pop(k, None)
        recipe["class"] = cls
        payload_json = skinkeeper_shared.canonical_payload_json(recipe)
        digest = skinkeeper_shared.compute_recipe_digest(sid, payload_json)
        conn = sqlite3.connect(game_ipc.BOT_DB_PATH, timeout=10)
        try:
            conn.execute("PRAGMA busy_timeout=8000")
            skinkeeper_shared.ensure_skin_last_applied(conn)
            row = conn.execute(
                "SELECT dino_class FROM skin_last_applied WHERE steam_id = ?",
                (sid,)).fetchone()
            if row is not None and _norm(row[0]) == _norm(cls):
                return "left_to_revive"
            changed = skinkeeper_shared.record_skin_recipe(
                conn, sid, dino_class=cls, actor_name=actor, kind="redeem",
                payload_json=payload_json, recipe_digest=digest,
                updated_utc=datetime.now(timezone.utc).isoformat())
            conn.commit()
            return "recorded changed=%s prev_class=%s" % (
                changed, str(row[0]) if row else "none")
        finally:
            conn.close()
    except Exception:
        log.warning("[SkinKeeper] redeem record_fallback failed", exc_info=True)
        return "error"


def _diet_pct(r: dict) -> dict:
    """Diet as % of the dino's capacity AT ITS PARKED GROWTH (baseline scales
    with growth — the same capacity model _redeem_diet_payload refills against).
    Species without a baseline entry (e.g. Kentrosaurus) get no percentages and
    the frontend falls back to the absolute number."""
    baseline = _REDEEM_DIET_BASELINES.get(str(r.get("dino_class") or ""))
    if not baseline:
        return {}
    growth = min(1.0, max(_num(r.get("growth")), 0.01))
    out = {}
    for key, bkey in (("a", "carbs"), ("b", "protein"), ("c", "lipids")):
        v = r.get(f"diet_{key}")
        # FINITE as well as numeric: a NaN or inf diet column IS a float, so it
        # walks straight past the type test and round(nan/cap*100) then raises
        # ValueError (OverflowError for inf) out of the view the mutation-edit
        # POST returns — a 500 on a save. The mod prints players.json floats with
        # %f, so a bad engine float arrives parseable and park stores it verbatim
        # (_num keeps it: float("nan") does not raise). `_finite(v) != v` is
        # exactly "not a finite number" — NaN, ±inf and an int too big for a
        # double all fail it, every real reading passes it unchanged. No
        # percentage is the honest answer for a value nobody can read; the
        # frontend already falls back to the absolute number for a species with
        # no baseline at all.
        if not isinstance(v, (int, float)) or _finite(v) != v:
            continue
        cap = baseline[bkey] * growth
        # CLAMPED BEFORE THE ROUND, not after: a finite but absurd stored value
        # (1e308) divided by a small capacity overflows to inf, and round(inf)
        # raises OverflowError where min(100.0, inf) is simply 100. Same integer
        # as before for every value in range — the clamp only ever moves what was
        # already out of range.
        out[key] = round(max(0.0, min(100.0, v / cap * 100))) if cap > 0 else 0
    return out


def _json_number(value):
    """A stored column echoed VERBATIM, minus the one shape that cannot be sent.
    Everything is passed through untouched — ints, strings, None, well-formed
    floats all keep the exact value this view has always returned — except a
    non-finite float, which becomes None.

    Why it has to exist: sqlite REAL really can hold inf, and Starlette renders
    with allow_nan=False, so `json.dumps({"growth": inf})` raises "Out of range
    float values are not JSON compliant" and the mutation-edit POST — which
    returns this view — answers 500 on a save. Repairing growth_pct and
    elder_stacks alone did not close it: the RAW growth, stats and diet columns
    are echoed one key above them and are just as unsendable."""
    return None if isinstance(value, float) and not math.isfinite(value) else value


def _dino_view(r: dict) -> dict:
    cls = r.get("dino_class") or ""
    return {
        "id": int(r.get("id")),
        "class": cls,
        "species": _friendly(cls),
        "custom_name": (clean_custom_name(r.get("custom_name")) or None),
        "growth": _json_number(r.get("growth")),
        # THE SHARED DEFINITION, not a second copy of the arithmetic: this is the
        # very percent growth_display_pct's docstring names as the card's, and it
        # is what the editor a few pixels below renders, so one dino can never be
        # shown two numbers. It also NEVER RAISES, which the inline
        # round(float(growth) * 100) did: float("nan") and float("inf") both
        # PARSE, and round(nan) then raises ValueError and round(inf)
        # OverflowError — a 500 on the mutation-edit POST, which returns this
        # view. Unreadable now answers None, exactly as it does in the editor.
        # (`or 0` kept verbatim so a falsy-but-present column — "" , [] — still
        # reads 0 and not None, the answer this field has always given.)
        "growth_pct": (growth_display_pct(r.get("growth") or 0)
                       if r.get("growth") is not None else None),
        "mutations": str(r.get("mutations") or ""),
        "mutations_count": _mutation_count(r.get("mutations")),
        "parent_mutations": str(r.get("parent_mutations") or ""),
        "elder_mutations": str(r.get("elder_mutations") or ""),
        # via _finite: the column is INTEGER in the schema, but a TEXT-typed one
        # hands back "2.0" and int("2.0") raises — and this view is returned by
        # the mutation-edit POST, so that raise was a 500 on a save. _num alone
        # did not close it: it catches TypeError/ValueError, but float("nan") and
        # float("inf") SUCCEED, and int(nan) then raises ValueError and int(inf)
        # OverflowError. _finite collapses both to 0, which is the answer this
        # field has always given for a missing column.
        "elder_stacks": int(_finite(r.get("elder_stacks"))),
        "is_elder": bool(r.get("is_elder")),
        "is_prime": bool(r.get("is_prime")),
        "parked_at": r.get("parked_at"),
        "redeem_pending": bool(str(r.get("redeem_pending_cmd_id") or "").strip()),
        # Stored-at-park detail for the web preview. skin is the EXACT captured
        # skin (poison-guarded); stats/diet keep the raw ABSOLUTE game values,
        # plus diet_pct (owner ruling 2026-07-11: the preview DISPLAYS
        # percentages; diet's denominator only exists back here).
        "skin": _parked_skin(r.get("skin_data")),
        "stats": {k: _json_number(r.get(k)) for k in (
            "health", "max_health", "stamina", "max_stamina",
            "hunger", "max_hunger", "thirst", "max_thirst",
            "oxygen", "max_oxygen")},
        "diet": {"a": _json_number(r.get("diet_a")),
                 "b": _json_number(r.get("diet_b")),
                 "c": _json_number(r.get("diet_c"))},
        "diet_pct": _diet_pct(r),
    }


def summary(steam_id: str, cap: int, is_admin: bool) -> dict:
    """Everything the vault panel needs in one call. cap<=0 = unlimited."""
    dinos = get_parked(steam_id)
    used = len(dinos)
    live_row = game_ipc.read_player(steam_id)
    online = _is_online(live_row)
    live = None
    if online:
        gate = park_gate_failures(live_row)
        live = {
            "species": _friendly(live_row.get("dino") or ""),
            "class": live_row.get("dino") or "",
            "growth": live_row.get("growth"),
            "growth_pct": (round(float(live_row.get("growth") or 0) * 100)
                           if live_row.get("growth") is not None else None),
            "eligible_to_park": len(gate) == 0,
            "gate_failures": gate,
            # paused/active badge — actor-keyed mirror of the in-game bit
            "growth_paused": growth_pause_current(steam_id, live_row),
        }
    return {
        "is_admin": is_admin,
        "slots_used": used,
        "slots_cap": (None if cap <= 0 else cap),
        # The panel reads `slots_total` (see VaultSection.jsx). Nothing ever
        # sent it, so every player was shown "N de ∞" while the park route
        # still refused them at the cap. Same value as slots_cap, None =
        # unlimited (admins), which the panel already renders as ∞.
        "slots_total": (None if cap <= 0 else cap),
        "slots_remaining": (None if cap <= 0 else max(0, cap - used)),
        "unlimited": cap <= 0,
        "online": online,
        "live": live,
        "dinos": [_dino_view(r) for r in dinos],
        "slay_cooldown_s": slay_cooldown_remaining(steam_id),
        "redeem_cooldown_s": redeem_cooldown_remaining(steam_id),
        # Same convention (int seconds, 0 = ready) so the panel can grey the
        # Aparcar button on the wait it would actually be refused on.
        "park_cooldown_s": park_cooldown_remaining(steam_id),
        # Same name/shape as the two above (int seconds, 0 = ready) so the panel
        # can grey the Body Drop button on the cooldown it will actually be
        # refused on. Read off the mod's lease file, not a web-owned map.
        # Only read for a player the button is live for: the lease file is
        # shared and rewritten by the mod, and every panel polls this every few
        # seconds, so an offline player or a herbivore must not pay for a read
        # whose answer can never change what they see.
        "bodydrop_cooldown_s": (
            bodydrop_cooldown_secs(steam_id)
            if online and str((live_row or {}).get("dino") or "").strip() in BODYDROP_RECIPIENT_CLASSES
            else 0
        ),
        "park_min": {"growth": PARK_MIN_GROWTH, "health": PARK_MIN_HEALTH_PCT,
                     "stamina": PARK_MIN_STAMINA_PCT, "hunger": PARK_MIN_HUNGER_PCT},
        "bodydrop_max": {"hunger": BODYDROP_MAX_HUNGER_PCT,
                         "growth": BODYDROP_MAX_GROWTH,
                         # Carnivores only — the mod refuses the rest, so the
                         # dashboard can say so before the click. Read the RAW
                         # row: the `live` view above exposes the class as
                         # "class", NOT "dino" (reading "dino" off the view
                         # silently disabled the same button for EVERYONE on a sibling build,
                         # owner report 2026-07-14).
                         "species_ok": str((live_row or {}).get("dino") or "").strip()
                         in BODYDROP_RECIPIENT_CLASSES},
        "growth_pause": {"min": GROWTH_PAUSE_MIN, "max": GROWTH_PAUSE_MAX,
                         "enabled": growth_pause_enabled()},
    }


def do_slay(steam_id: str) -> dict:
    remaining = slay_cooldown_remaining(steam_id)
    if remaining > 0:
        raise HTTPException(429, f"Espera {(remaining + 59)//60} min antes de volver a usar Eliminar.")
    if not _is_online(game_ipc.read_player(steam_id)):
        raise HTTPException(400, "No estás en partida.")
    if not game_ipc.write_game_command({"type": "kill", "steamid": str(steam_id)}):
        raise HTTPException(500, "No pude escribir la orden al servidor. Intenta de nuevo.")
    record_slay(steam_id)
    # a pending population-swap persistence record must never outlive the dino
    # it described (the offline watcher would resurrect it on next login)
    game_ipc.clear_swap_persist(steam_id)
    log.info("[vault] slay sid=%s ok", steam_id)
    return {"ok": True, "slay_cooldown_s": SLAY_COOLDOWN_SECS}


# ── body drop (requested corpse feed) ─────────────────────────────────────────
# One in-flight Body Drop per SteamID: a double click must not write two game
# commands (the mod's lease would refuse the second, but it would burn the
# player's 25 s wait on a guaranteed failure).
_bodydrop_inflight: set[str] = set()
_bodydrop_inflight_lock = Lock()

# The mod's body_drop_failed fail_reason values, in player Spanish. Anything
# unmapped falls through to a generic line naming the raw reason.
_BODYDROP_FAIL_ES = {
    "corpse_drops_disabled": "Body Drop está desactivado en el servidor ahora mismo.",
    "actor_not_found": "El juego no encontró a tu dinosaurio activo.",
    "actor_not_in_cache": "El juego aún no registró a tu dinosaurio activo. Intenta en unos segundos.",
    "source_class_not_eligible": "Body Drop alimenta solo a carnívoros.",
    "source_not_alive": "Tu dinosaurio no está vivo.",
    "restore_in_flight": "Tienes una recuperación en progreso. Espera a que termine.",
    "source_growth_invalid": "El juego no pudo leer tu crecimiento.",
    "source_growth_above_limit": "Ya creciste demasiado para un Body Drop (necesitas menos del 65%).",
    "stats_not_loaded": "El servidor aún no cargó las estadísticas de tu dino. Espera unos segundos.",
    "source_not_hungry": "Aún no tienes suficiente hambre para un Body Drop (necesitas menos del 30%).",
    "no_controller_self": "El juego no pudo resolver tu control. Intenta en unos segundos.",
    "no_spawn_location": "El juego no encontró un lugar junto a ti para dejar el cuerpo.",
    "corpse_class_growth_limit": "No hay una especie de cuerpo disponible para tu tamaño.",
    "missing_class": "No hay una especie de cuerpo disponible. Avisa a un admin.",
    "invalid_fname": "El juego no pudo preparar el cuerpo. Intenta de nuevo.",
    "actor_name_missing": "El juego aún no registró a tu dinosaurio. Intenta en unos segundos.",
    "life_key_missing": "El juego aún no registró a tu dinosaurio. Intenta en unos segundos.",
    "body_drop_cooldown": "Body Drop tiene una espera de 10 minutos entre usos. Intenta más tarde.",
    "body_drop_in_progress": "Ya hay un Body Drop en camino para ti. Espera a que llegue.",
    "lease_unavailable": "El servidor está ocupado con otro Body Drop. Intenta en un momento.",
    "queue_failed": "El servidor no pudo encolar el cuerpo. Intenta de nuevo.",
    "spawn_actor_failed": "El juego no pudo colocar el cuerpo. Intenta de nuevo.",
    "cap_reached": "El servidor está colocando otro cuerpo ahora mismo. Intenta en un momento.",
    "corpse_command_stale": "La orden tardó demasiado en llegar al juego. Intenta de nuevo.",
}


def _bodydrop_fail_message(status: dict | None) -> str:
    reason = str((status or {}).get("fail_reason") or (status or {}).get("reason") or "").strip()
    if reason in _BODYDROP_FAIL_ES:
        return _BODYDROP_FAIL_ES[reason]
    if reason.startswith("native_fault_"):
        # Contained engine fault while placing the body — nothing was left in
        # the world and the lease was not stamped, so "try again" is honest.
        return ("El juego tropezó al colocar el cuerpo y el intento se canceló "
                "sin dejar nada. Inténtalo de nuevo en unos segundos.")
    if reason:
        return f"El juego rechazó el Body Drop: {reason.replace('_', ' ')}."
    return "El juego rechazó el Body Drop sin dar un motivo."


def do_bodydrop(steam_id: str) -> dict:
    """Ask the game to drop a fresh corpse NEXT TO a starving juvenile
    carnivore so it can eat. It never touches the caller's own dinosaur
    (2026-07-14 lesson: this lane must never ride the kill op).

    Web writes {"type": "body_drop"} -> mod HandleBodyDropRequest resolves the
    live location, picks a corpse species and queues the native spawn -> the
    corpse result handler answers with body_drop_ok / body_drop_failed under
    our cmd_id. Gates mirror the mod exactly (carnivore, alive, hunger < 30%,
    growth < 65%), and the mod's 10-min lease is pre-read off its own file so a
    player already on cooldown is answered in microseconds instead of paying a
    full round trip to the game to be told the same thing."""
    sid = str(steam_id)
    # The game's own feeder lease, read off its file. This is the refusal that
    # fires most — cooldown is the bulk of all Body Drop failures — and reading
    # it here answers in microseconds instead of paying a full round trip to the
    # game to be told the same thing. Fails open (see _bodydrop_lease_state), so
    # an unreadable lease file costs a round trip, never a wrongly-refused drop.
    lease_state, lease_ms, lease_lane = _bodydrop_lease_state(sid)
    # "A drop is already coming" is true no matter what else is wrong with the
    # request, so it answers first.
    if lease_state == "pending":
        log.info("[vault] bodydrop sid=%s pre-gate=pending ms_left=%d (no game round trip)",
                 sid, lease_ms)
        raise HTTPException(409, "Ya hay un Body Drop en camino para ti. Espera a que llegue.")
    live = game_ipc.read_player(steam_id, force_fresh=True)
    if not _is_online(live):
        raise HTTPException(400, "No estás en partida.")
    actor = str((live or {}).get("actor_name") or "").strip()
    if not actor:
        raise HTTPException(409, "Tu dinosaurio aún no está registrado. Intenta en unos segundos.")
    if not float(live.get("max_hunger") or 0) > 0:
        raise HTTPException(409, "El servidor aún no cargó las estadísticas de tu dino. Espera unos segundos.")
    dino_class = str((live or {}).get("dino") or "").strip()
    if dino_class not in BODYDROP_RECIPIENT_CLASSES:
        raise HTTPException(400, {
            "message": "No puedes pedir un Body Drop.",
            "reasons": [f"{_friendly(dino_class) or 'Tu dinosaurio'} no es carnívoro — Body Drop alimenta solo a carnívoros."],
        })
    # Cooldown sits AFTER the online/registered/carnivore checks on purpose: it
    # is the same refusal either way, but telling a herbivore to come back in
    # 8 minutes for something they can never have is worse than telling them why.
    # Everything above this point is local file reads; the round trip this still
    # saves is write_game_command plus the 25 s ack wait, further down.
    if lease_state == "fed" and lease_ms > BODYDROP_COOLDOWN_EPS_MS:
        log.info("[vault] bodydrop sid=%s pre-gate=cooldown lane=%s ms_left=%d (no game round trip)",
                 sid, lease_lane, lease_ms)
        secs = _bodydrop_wait_secs(lease_ms)
        espera = f"{(secs + 59) // 60} min" if secs >= 60 else f"{secs} s"
        if lease_lane == "lua":
            # The AUTOMATIC feeder shares this lease. Telling a player to wait
            # before asking "again" is wrong when they never asked in the first
            # place — the server fed them.
            raise HTTPException(
                429,
                f"El servidor ya te dejó un cuerpo automáticamente hace poco. "
                f"Puedes pedir otro en {espera}.",
            )
        raise HTTPException(
            429,
            f"Espera {espera} antes de volver a pedir un Body Drop (uno cada 10 minutos).",
        )
    hg = _pct(live, "hunger", "max_hunger")
    growth = float(live.get("growth") or 0)
    fails: list[str] = []
    if hg is not None and hg >= BODYDROP_MAX_HUNGER_PCT:
        fails.append(f"Hambre {hg*100:.0f}% — Body Drop requiere menos del {BODYDROP_MAX_HUNGER_PCT*100:.0f}% (cuanto más bajo, más hambriento).")
    if growth >= BODYDROP_MAX_GROWTH:
        fails.append(f"Crecimiento {growth*100:.0f}% — Body Drop es solo para jóvenes (menos del {BODYDROP_MAX_GROWTH*100:.0f}%).")
    if fails:
        raise HTTPException(400, {"message": "No puedes pedir un Body Drop todavía.", "reasons": fails})

    with _bodydrop_inflight_lock:
        if sid in _bodydrop_inflight:
            raise HTTPException(409, "Ya hay un Body Drop en progreso.")
        _bodydrop_inflight.add(sid)
    try:
        total_deadline = time.monotonic() + BODYDROP_TOTAL_BUDGET_SECS
        attempt = 0
        while True:
            attempt += 1
            cmd_id = uuid.uuid4().hex
            if not game_ipc.write_game_command({
                "type": "body_drop",
                "steamid": sid,
                "actor_name": actor,
                "cmd_id": cmd_id,
            }):
                raise HTTPException(503, "No pude escribir la orden al servidor. Intenta de nuevo.")
            attempt_start = time.monotonic()
            deadline = min(attempt_start + BODYDROP_ACK_TIMEOUT_SECS, total_deadline)
            failed = None
            while time.monotonic() < deadline:
                failed = game_ipc.read_restore_status(sid, None, "body_drop_failed", None, cmd_id)
                if failed:
                    break
                ok_ack = game_ipc.read_restore_status(sid, None, "body_drop_ok", None, cmd_id)
                if ok_ack:
                    ack_actor = str(ok_ack.get("actor_name") or "").strip()
                    if ack_actor and ack_actor != actor:
                        log.info("[vault] bodydrop sid=%s cmd_id=%s ack=actor_mismatch ours=%s theirs=%s",
                                 sid, cmd_id, actor, ack_actor)
                        raise HTTPException(
                            502,
                            "El servidor confirmó a otro dinosaurio; no se cambió nada. Intenta de nuevo.",
                        )
                    corpse = _friendly(str(ok_ack.get("corpse_class") or "")) or "cuerpo"
                    log.info("[vault] bodydrop sid=%s cmd_id=%s ack=body_drop_ok corpse=%s",
                             sid, cmd_id, ok_ack.get("corpse_class"))
                    return {
                        "ok": True,
                        "message": f"Body Drop confirmado — un {corpse} fresco cayó junto a ti. ¡A comer!",
                        "cmd_id": cmd_id,
                    }
                time.sleep(0.2)
            if failed is None:
                # A late ack means the corpse can still land AFTER this response (the
                # spawn rides the game's ~30 s drain), so this message must not claim
                # "no body was dropped" - that can be false, and the stamped lease then
                # makes the player's retry say "wait 10 min" for a body they were told
                # never came. Timeouts are never auto-retried for the same reason: a
                # second command behind a late-landing corpse would double-drop.
                log.info("[vault] bodydrop sid=%s cmd_id=%s ack=timeout waited=%.0fs",
                         sid, cmd_id, time.monotonic() - attempt_start)
                raise HTTPException(
                    504,
                    "El juego no confirmó el Body Drop a tiempo. Si en unos segundos no "
                    "aparece un cuerpo junto a ti, espera unos minutos e intenta de nuevo.",
                )
            reason = str(failed.get("fail_reason") or failed.get("reason") or "") or "none_given"
            can_retry = (
                reason.startswith("native_fault_")
                and attempt < BODYDROP_MAX_ATTEMPTS
                and (total_deadline - time.monotonic() - BODYDROP_RETRY_DELAY_SECS)
                    >= BODYDROP_RETRY_MIN_WINDOW_SECS
            )
            # The game's fail_reason otherwise dies with this response: the
            # mod prints it to a console LIN keeps off, so this line is the
            # only durable record of WHY drops fail.
            log.info("[vault] bodydrop sid=%s cmd_id=%s ack=body_drop_failed reason=%s retrying=%d",
                     sid, cmd_id, reason, 1 if can_retry else 0)
            if not can_retry:
                raise HTTPException(502, _bodydrop_fail_message(failed))
            # Contained native fault: the mod destroyed the half-spawned body and
            # did NOT stamp the lease, so one fresh command is safe. New cmd_id
            # isolates this attempt's acks from the failed one's.
            time.sleep(BODYDROP_RETRY_DELAY_SECS)
    finally:
        with _bodydrop_inflight_lock:
            _bodydrop_inflight.discard(sid)


# ── growth pause (since 2026-07-27 the ONLY surface; in-game chat lane removed) ─────
# The web writes the SAME queue the Lua chat handler writes
# (growth_pause_commands.json) and the mod's C++ GrowthPauseSystem consumes it
# (2026-07-16 wave). Self-only by construction: steamid == invoker == caller.
# The C++ has no ack file — its per-command decision goes to the mod log as
#   [GrowthPause] decision=<d> ... cmd_id=<id>
# so the ack poll greps the log tail for our cmd_id. Gates mirror the in-game
# lane (online, actor registered, growth 75–100%); the C++ re-gates everything.
GROWTH_PAUSE_COMMANDS_JSON = os.path.join(game_ipc.SAVED_DIR, "growth_pause_commands.json")
GROWTH_PAUSE_ENABLE_FLAG = os.path.join(game_ipc.SAVED_DIR, "growth_pause_enable.flag")
GROWTH_PAUSE_ENABLE_BARE = os.path.join(game_ipc.SAVED_DIR, "growth_pause_enable")
GROWTH_PAUSE_MOD_LOG = os.path.join(game_ipc.SAVED_DIR, "laislanublar_mod.log")
GROWTH_PAUSE_MIN = 0.75
GROWTH_PAUSE_MAX = 1.0
GROWTH_PAUSE_ACK_TIMEOUT_SECS = 7.0
_GROWTH_PAUSE_LOCK_STALE_MS = 5000       # matches Lua + C++ eviction window
_GROWTH_PAUSE_MAX_QUEUE_BYTES = 524288   # matches Lua writer + C++ consumer cap
_growthpause_inflight: set[str] = set()
_growthpause_inflight_lock = Lock()


def growth_pause_enabled() -> bool:
    return os.path.isfile(GROWTH_PAUSE_ENABLE_FLAG) or os.path.isfile(GROWTH_PAUSE_ENABLE_BARE)


# ── growth pause STATE (paused/active badge on the web UI) ────────────────────
# The authoritative bit lives on the in-game pawn and RESETS whenever the pawn
# is recreated (respawn, relog, server restart). The web mirror therefore keys
# each recorded state to the ACTOR NAME it was applied to: current actor !=
# recorded actor -> the badge falls back to "active" automatically, exactly
# like the real bit. Sources: our own successful web actions, plus in-game
# picked up from the mod log's decision=ok lines (dedup by
# cmd_id; append-only log, LAST match wins).
GROWTH_PAUSE_STATE_JSON = os.path.join(game_ipc.DATA_DIR, "growth_pause_state.json")
_gp_state_lock = Lock()
_gp_state_cache: dict | None = None
_gp_scan_last: dict[str, float] = {}


def _gp_state_load() -> dict:
    global _gp_state_cache
    if _gp_state_cache is not None:
        return _gp_state_cache
    try:
        with open(GROWTH_PAUSE_STATE_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        _gp_state_cache = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        _gp_state_cache = {}
    return _gp_state_cache


def _gp_state_set(sid: str, paused: bool, actor_name: str, source: str, cmd_id: str) -> None:
    with _gp_state_lock:
        state = _gp_state_load()
        state[str(sid)] = {
            "paused": bool(paused),
            "actor_name": str(actor_name or ""),
            "source": source,
            "cmd_id": str(cmd_id or ""),
            "ts": int(time.time()),
        }
        tmp = GROWTH_PAUSE_STATE_JSON + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, separators=(",", ":"))
            os.replace(tmp, GROWTH_PAUSE_STATE_JSON)
        except OSError as e:
            log.warning("[vault] growthpause state write failed: %s", e)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass


def _gp_scan_log_for_sid(sid: str, live_actor: str) -> None:
    """Pick up every growth-pause decision the game made (including any web
    action whose ack we missed) from
    the mod log's newest decision=ok line for this sid. Throttled to one scan
    per sid per 2 s — summary() polls every 8 s per open page."""
    now = time.monotonic()
    if now - _gp_scan_last.get(sid, 0.0) < 2.0:
        return
    _gp_scan_last[sid] = now
    try:
        with open(GROWTH_PAUSE_MOD_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 262144))
            tail = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return
    needle = f"decision=ok sid={sid} "
    for ln in reversed(tail.splitlines()):
        if needle not in ln:
            continue
        pause = "detail=masked_write_paused" in ln
        if not pause and "detail=masked_write_unpaused" not in ln:
            return
        cmd_id = ln.split("cmd_id=", 1)[1].split()[0].strip() if "cmd_id=" in ln else ""
        with _gp_state_lock:
            prev = _gp_state_load().get(str(sid)) or {}
        if cmd_id and prev.get("cmd_id") == cmd_id:
            return  # newest decision already recorded
        src = "web" if cmd_id.startswith("web-") else "chat"
        _gp_state_set(sid, pause, live_actor, src, cmd_id)
        return


def growth_pause_current(sid: str, live_row: dict | None) -> bool | None:
    """Badge truth for the UI: True/False when the caller is online, keyed to
    the live actor (None when offline). Actor mismatch = the pawn was
    recreated since the record -> the real bit reset -> report active."""
    if not _is_online(live_row):
        return None
    live_actor = str((live_row or {}).get("actor_name") or "").strip()
    if not live_actor:
        return None
    _gp_scan_log_for_sid(str(sid), live_actor)
    with _gp_state_lock:
        rec = _gp_state_load().get(str(sid)) or {}
    if rec.get("paused") is True and str(rec.get("actor_name") or "") == live_actor:
        return True
    return False


def _growth_pause_queue_append(line: str) -> str | None:
    """Append one command line under the Lua/C++-compatible lock protocol.
    Lock = exclusive-create by rename (os.rename fails if the target exists on
    Windows, same semantics as the Lua os.rename and the C++ MoveFileExA
    flags=0); a lock older than 5 s is stale and evicted, mirroring both
    runtimes. Returns None on success, else a short machine reason."""
    lock_path = GROWTH_PAUSE_COMMANDS_JSON + ".lock"
    now_ms = int(time.time() * 1000)
    tmp = f"{lock_path}.web.{now_ms}.{uuid.uuid4().hex[:6]}"

    def _try_claim() -> bool:
        try:
            with open(tmp, "w", encoding="ascii") as f:
                f.write(f"ts_ms={int(time.time() * 1000)}\nowner=web_growth_pause\n")
            os.rename(tmp, lock_path)
            return True
        except FileExistsError:
            return False
        except OSError:
            return False
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    claimed = _try_claim()
    if not claimed:
        # stale-evict path (holder died mid-write); fresh locks are respected
        try:
            with open(lock_path, "r", encoding="ascii", errors="ignore") as f:
                body = f.read(256)
            ts = int(str(body).split("ts_ms=", 1)[1].split()[0]) if "ts_ms=" in body else 0
        except (OSError, ValueError, IndexError):
            ts = 0
        if ts <= 0 or int(time.time() * 1000) - ts > _GROWTH_PAUSE_LOCK_STALE_MS:
            try:
                os.remove(lock_path)
            except OSError:
                pass
            claimed = _try_claim()
    if not claimed:
        return "lock_busy"
    try:
        try:
            if os.path.exists(GROWTH_PAUSE_COMMANDS_JSON) and \
                    os.path.getsize(GROWTH_PAUSE_COMMANDS_JSON) > _GROWTH_PAUSE_MAX_QUEUE_BYTES:
                return "queue_oversized"
            with open(GROWTH_PAUSE_COMMANDS_JSON, "a", encoding="ascii") as f:
                f.write(line + "\n")
            return None
        except OSError as e:
            log.warning("[vault] growthpause queue append failed: %s", e)
            return "write_failed"
    finally:
        try:
            os.remove(lock_path)
        except OSError:
            pass


def _growth_pause_find_decision(cmd_id: str) -> str | None:
    """Grep the mod-log tail for our cmd_id decision line; returns the raw
    decision token or None. Tail-bounded read (256 KB) — the consumer answers
    within one 500 ms tick, so the line is always near the end."""
    try:
        with open(GROWTH_PAUSE_MOD_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 262144))
            tail = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    marker = f"cmd_id={cmd_id}"
    for ln in reversed(tail.splitlines()):
        if marker in ln and "decision=" in ln:
            try:
                return ln.split("decision=", 1)[1].split()[0].strip()
            except IndexError:
                return None
    return None


_GROWTH_PAUSE_FAIL_ES = {
    "disabled": (503, "La pausa de crecimiento está desactivada en el servidor ahora mismo."),
    "no_actor": (409, "El juego no encontró a tu dinosaurio activo. Intenta en unos segundos."),
    "guard_busy": (503, "El servidor está ocupado ahora mismo. Intenta de nuevo en unos segundos."),
    "offset_failed": (502, "El juego no pudo aplicar el cambio. Intenta de nuevo."),
    "write_failed": (502, "El juego no pudo aplicar el cambio. Intenta de nuevo."),
    "not_owner": (500, "El juego rechazó la orden."),
    "bad_command": (500, "El juego rechazó la orden."),
}


def do_growth_pause(steam_id: str, pause: bool) -> dict:
    """Pause or resume the caller's live dino growth — the same action as
    the website is the only surface that offers - the in-game /pause + /unpause
    chat commands were removed 2026-07-27. Writes the shared queue and
    waits for the mod's logged decision under our cmd_id."""
    if not growth_pause_enabled():
        raise HTTPException(503, "La pausa de crecimiento está desactivada en el servidor ahora mismo.")
    live = game_ipc.read_player(steam_id, force_fresh=True)
    if not _is_online(live):
        raise HTTPException(400, "No estás en partida.")
    actor = str((live or {}).get("actor_name") or "").strip()
    if not actor:
        raise HTTPException(409, "Tu dinosaurio aún no está registrado. Intenta en unos segundos.")
    growth = float(live.get("growth") or 0)
    if growth < GROWTH_PAUSE_MIN or growth > GROWTH_PAUSE_MAX:
        raise HTTPException(400, {
            "message": "No puedes cambiar la pausa de crecimiento todavía.",
            "reasons": [f"Necesitas entre {GROWTH_PAUSE_MIN*100:.0f}% y {GROWTH_PAUSE_MAX*100:.0f}% "
                        f"de crecimiento. Actual: {growth*100:.0f}%."],
        })

    sid = str(steam_id)
    with _growthpause_inflight_lock:
        if sid in _growthpause_inflight:
            raise HTTPException(409, "Ya hay un cambio de pausa en progreso.")
        _growthpause_inflight.add(sid)
    cmd_id = f"web-{uuid.uuid4().hex[:12]}"
    try:
        line = json.dumps({
            "type": "growth_pause",
            "steamid": sid,
            "invoker_steamid": sid,
            "pause": bool(pause),
            "actor_name": actor,
            "cmd_id": cmd_id,
            "ts_ms": int(time.time() * 1000),
        }, separators=(",", ":"))
        qerr = _growth_pause_queue_append(line)
        if qerr == "lock_busy":
            raise HTTPException(503, "El servidor está ocupado. Intenta de nuevo en unos segundos.")
        if qerr:
            raise HTTPException(500, "No pude escribir la orden al servidor. Intenta de nuevo.")

        deadline = time.monotonic() + GROWTH_PAUSE_ACK_TIMEOUT_SECS
        decision = None
        while time.monotonic() < deadline:
            decision = _growth_pause_find_decision(cmd_id)
            if decision:
                break
            time.sleep(0.25)
        log.info("[vault] growthpause sid=%s pause=%s cmd_id=%s decision=%s",
                 sid, pause, cmd_id, decision or "timeout")
        if decision == "ok":
            _gp_state_set(sid, bool(pause), actor, "web", cmd_id)
            return {
                "ok": True,
                "paused": bool(pause),
                "message": "Crecimiento pausado." if pause else "Crecimiento reanudado.",
                "cmd_id": cmd_id,
            }
        if decision == "not_in_range":
            raise HTTPException(400, {
                "message": "No puedes cambiar la pausa de crecimiento todavía.",
                "reasons": [f"Necesitas entre {GROWTH_PAUSE_MIN*100:.0f}% y "
                            f"{GROWTH_PAUSE_MAX*100:.0f}% de crecimiento."],
            })
        if decision in _GROWTH_PAUSE_FAIL_ES:
            code, msg = _GROWTH_PAUSE_FAIL_ES[decision]
            raise HTTPException(code, msg)
        if decision:
            raise HTTPException(502, f"El juego rechazó la orden: {decision.replace('_', ' ')}.")
        raise HTTPException(504, "El juego no confirmó a tiempo. El cambio puede aplicarse "
                                 "igualmente en unos segundos.")
    finally:
        with _growthpause_inflight_lock:
            _growthpause_inflight.discard(sid)


def do_delete(steam_id: str, dino_id: int) -> dict:
    parked = get_parked_by_id(dino_id)
    if not parked or str(parked.get("steam_id")) != str(steam_id):
        raise HTTPException(404, "Ese dino guardado no te pertenece o no existe.")
    parked = resolve_stale_redeem_pending(parked)
    if not parked:
        raise HTTPException(404, "Ese dino ya no está en la bóveda (su recuperación terminó).")
    if str(parked.get("redeem_pending_cmd_id") or "").strip():
        raise HTTPException(409, "Ese dino tiene una recuperación en progreso; no se puede borrar ahora.")
    if delete_owned(dino_id, steam_id) != 1:
        raise HTTPException(409, "No se pudo borrar (¿ya no existe?).")
    log.info("[vault] delete sid=%s dino_id=%s ok", steam_id, dino_id)
    return {"ok": True, "species": _friendly(parked.get("dino_class") or "")}


# ── redeem→park race gate ─────────────────────────────────────────────────────
# 2026-08-20: a player redeemed a market-bought 81% / prime / 16-mutation stego
# and pressed Guardar seconds later. start_park reads the pawn from the mod's
# players.json export, which lags the engine by a few seconds — so the park
# captured the throwaway 27.8% beach spawn (row 15175) while the engine's own
# snapshot proves the real dino landed on the SAME actor two seconds AFTER the
# capture. The redeem lane leaves a short-lived memo of what it just delivered;
# a park whose pawn reads materially BELOW that memo is refused with words
# instead of silently storing the wrong dinosaur. The memo lives in the shared
# SQLite (not process memory) so the bot's park lane can adopt the same gate.
# Fail-open everywhere: this gate must never be able to block an honest park.
REDEEM_RACE_WINDOW_SECS = 120.0
REDEEM_RACE_GROWTH_SLACK = 0.10


def _mut_count(pipe) -> int:
    return sum(1 for m in str(pipe or "").split("|")
               if m.strip() and m.strip().lower() != "none")


def _note_redeem_for_race_gate(steam_id: str, parked: dict) -> None:
    """Called once per confirmed redeem, BEFORE the ok is announced: record what
    was just delivered so an instant park can be judged against it."""
    try:
        conn = _connect_rw()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS redeem_race_memo ("
                " steam_id TEXT PRIMARY KEY, dino_class TEXT, growth REAL,"
                " mut_count INTEGER, is_prime INTEGER, redeemed_at REAL)")
            conn.execute(
                "INSERT OR REPLACE INTO redeem_race_memo VALUES (?,?,?,?,?,?)",
                (str(steam_id), str(parked.get("dino_class") or ""),
                 _num(parked.get("growth")),
                 _mut_count(parked.get("mutations"))
                 + _mut_count(parked.get("parent_mutations"))
                 + _mut_count(parked.get("elder_mutations")),
                 1 if parked.get("is_prime") else 0, time.time()))
        finally:
            conn.close()
    except Exception:
        log.exception("[vault] redeem race memo write failed sid=%s "
                      "(the race gate will not cover this redeem)", steam_id)


def _redeem_race_refusal(steam_id: str, row: dict):
    """The reason this pawn must not be parked yet, or None. Read-only judgment
    against the freshest redeem memo; every failure mode answers None."""
    try:
        conn = _connect_rw()
        try:
            try:
                memo = conn.execute(
                    "SELECT * FROM redeem_race_memo WHERE steam_id = ?",
                    (str(steam_id),)).fetchone()
            except sqlite3.OperationalError:
                return None    # table not created yet: nothing was memoed
            if not memo:
                return None
            age = time.time() - float(memo["redeemed_at"] or 0)
            if age > REDEEM_RACE_WINDOW_SECS or age < 0:
                conn.execute("DELETE FROM redeem_race_memo WHERE steam_id = ?",
                             (str(steam_id),))
                return None
            pawn_class = str(row.get("dino") or row.get("dino_class") or "")
            if pawn_class != str(memo["dino_class"] or ""):
                return None    # parking a different species than the redeem
            pawn_growth = _num(row.get("growth"))
            pawn_muts = (_mut_count(row.get("mutations"))
                         + _mut_count(row.get("parent_mutations"))
                         + _mut_count(row.get("elder_mutations")))
            pawn_prime = bool(row.get("is_prime"))
            lag_growth = pawn_growth < _num(memo["growth"]) - REDEEM_RACE_GROWTH_SLACK
            lag_muts = int(memo["mut_count"] or 0) > 0 and pawn_muts == 0
            lag_prime = bool(memo["is_prime"]) and not pawn_prime
            if lag_growth or lag_muts or lag_prime:
                log.warning("[vault] park REFUSED redeem-race sid=%s "
                            "memo(g=%.3f m=%s p=%s) pawn(g=%.3f m=%s p=%s) age=%.0fs",
                            steam_id, _num(memo["growth"]), memo["mut_count"],
                            memo["is_prime"], pawn_growth, pawn_muts,
                            int(pawn_prime), age)
                return ("Tu dino recuperado aún se está aplicando en el juego. "
                        "Espera unos segundos y vuelve a pulsar Guardar.")
            # The pawn already matches what was delivered — the memo is done.
            conn.execute("DELETE FROM redeem_race_memo WHERE steam_id = ?",
                         (str(steam_id),))
            return None
        finally:
            conn.close()
    except HTTPException:
        return None    # vault DB briefly unavailable: keep parks on old behavior
    except Exception:
        log.exception("[vault] redeem race gate failed open sid=%s", steam_id)
        return None


# ── park (background) ─────────────────────────────────────────────────────────
def start_park(steam_id: str, discord_id: str, cap: int) -> dict:
    # Claimed FIRST, before any gate: two threads that both read a live dino
    # would otherwise both pass, both kill, and both store the same pawn. Every
    # exit below releases it; the accepted path hands it to _run_park, which
    # releases in a finally.
    action_key = _claim_action("Park", steam_id)
    try:
        waiting = park_cooldown_remaining(steam_id)
        if waiting > 0:
            raise HTTPException(429, f"Espera {_wait_text_es(waiting)} antes de volver a guardar un dino.")
        row = game_ipc.read_player(steam_id, force_fresh=True)
        fails = park_gate_failures(row)
        if fails:
            raise HTTPException(400, {"message": "No puedes guardar todavía.", "reasons": fails})
        if _steam_has_fresh_redeem_pending(steam_id):
            raise HTTPException(409, "Ya hay una recuperación en progreso. Espera a que termine antes de guardar.")
        race = _redeem_race_refusal(steam_id, row)
        if race:
            raise HTTPException(409, race)
        if cap and cap > 0 and count_parked(steam_id) >= cap:
            raise HTTPException(409, {"message": f"Bóveda llena ({cap}/{cap}). Borra o recupera un dino primero."})

        snapshot = dict(row)
        actor = str(snapshot.get("actor_name") or "").strip()
        # Capture skin + diet snapshots BEFORE the kill so redeem can restore them.
        try:
            skin_entry = game_ipc.read_skin_snapshot(actor) if actor else None
            snapshot["skin_data"] = json.dumps(skin_entry, separators=(",", ":")) if skin_entry else ""
        except Exception:
            snapshot["skin_data"] = ""
        # SKIN-5 web twin (2026-08-07): an ACTIVE same-class SkinKeeper recipe
        # is the exact original apply bytes and outranks the ledger snapshot
        # readback (which lags queued paints and flattens glitch values). Sex
        # authority stays with the snapshot inside the helper; fails open.
        snapshot["skin_data"], _park_skin_src = _park_skin_preferring_recipe(
            steam_id, str(snapshot.get("dino") or snapshot.get("dino_class") or ""),
            snapshot["skin_data"])
        if snapshot["skin_data"]:
            log.info("[vault] park skin capture sid=%s source=%s", steam_id, _park_skin_src)
        if not snapshot["skin_data"]:
            # The snapshot file is a best-effort ~30s subset, so a just-spawned
            # or just-relogged pawn can be absent. The row then carries no skin
            # AND no sex, and the redeem replay has nothing to write back — the
            # dino returns with whatever sex the throwaway spawn had (owner
            # report 2026-07-30: "dino changed sex on redeem"). Not recoverable
            # here without guessing; say it loudly instead of parking silently.
            log.warning("[vault] park skin capture MISSED sid=%s actor=%s — row will carry "
                        "no skin/sex; a redeem of this row keeps the spawn-screen sex",
                        steam_id, actor or "?")
        try:
            diet_snap = game_ipc.read_diet_snapshot(actor) if actor else None
            if diet_snap:
                snapshot["diet_a"] = _num(diet_snap.get("carbs"))
                snapshot["diet_b"] = _num(diet_snap.get("protein"))
                snapshot["diet_c"] = _num(diet_snap.get("lipids"))
        except Exception:
            pass
        cmd_id = uuid.uuid4().hex
        # Journal BEFORE the kill order (park never-lose, 2026-07-30): the
        # snapshot is complete and nothing after this point can rebuild it —
        # players.json drops this sid the moment the kill lands. Fail-CLOSED:
        # refuse to kill a dino we could not first write down.
        recovery_id = ""
        if _park_journal_enabled():
            recovery_id = append_unsaved_park(
                steam_id, discord_id or "", snapshot, cap, _PARK_PREKILL_REASON)
            if not recovery_id:
                raise HTTPException(
                    503, "No pude asegurar el guardado. Tu dino sigue en partida; "
                         "inténtalo de nuevo en unos segundos.")
        jid = _new_job("park", steam_id)
        log.info("[vault] park start sid=%s actor=%s cmd_id=%s job=%s rid=%s",
                 steam_id, actor, cmd_id, jid, recovery_id[:12])
        coro = _run_park(jid, steam_id, discord_id or "", snapshot, actor, cmd_id, cap,
                         action_key, recovery_id)
        try:
            _schedule(coro)
        except Exception:
            coro.close()
            if recovery_id:
                # The kill order was never issued — nothing is owed, and a
                # leftover pre-kill line could later promote a living dino.
                _journal_prune({recovery_id}, "park aborted before the kill")
            raise
        return {"job_id": jid}
    except Exception:
        _release_action(action_key)
        raise


async def _reset_gen0_after_dino_switch(steam_id: str, reason: str) -> bool:
    """Best-effort GEN-0 reset which can never break a confirmed park.

    The import stays lazy because vault and the infection router are both
    assembled by the backend bootstrap.  Mongo/event failures are contained;
    the mod's durable ``off:park`` event remains an independent retry path.
    """
    try:
        import gen0_infection
        return bool(await gen0_infection.reset_for_dino_switch(steam_id, reason))
    except Exception:  # noqa: BLE001 - never trade a player's dino for a side reset
        log.exception("[vault] GEN-0 dino-switch reset failed sid=%s reason=%s",
                      steam_id, reason)
        return False


async def _run_park(jid, steam_id, discord_id, snapshot, actor, cmd_id, cap,
                    action_key=None, recovery_id=""):
    kill_issued = False     # the order reached the IPC file — it can still land
    kill_confirmed = False  # the death was positively observed
    try:
        ok = await asyncio.to_thread(
            game_ipc.write_game_command,
            {"type": "kill", "steamid": steam_id, "actor_name": actor, "cmd_id": cmd_id},
        )
        if not ok:
            # The kill order never reached the IPC file — the dino is alive and
            # nothing is owed, so the journal line must not outlive the attempt.
            if recovery_id:
                await asyncio.to_thread(_journal_prune, {recovery_id}, "kill never sent")
            _set_job(jid, "failed", "No pude escribir la orden al servidor. Intenta de nuevo.")
            return
        kill_issued = True
        _set_job(jid, "pending", "Eliminando tu dino para guardarlo… (hasta ~90 s)")
        deadline = time.monotonic() + PARK_ACK_TIMEOUT_SECS
        killed = False
        unkilled_since = None   # first tick on which EVERY verified ack was a
                                # short-circuit — see _kill_ack_unkilled
        while time.monotonic() < deadline:
            acks = await asyncio.to_thread(
                game_ipc.read_restore_matches, steam_id, "kill_ok", actor, cmd_id)
            verified = [a for a in acks if a.get("kill_verified")]
            if any(not _kill_ack_unkilled(a) for a in verified):
                # An honest ack exists for this command. It outranks any
                # short-circuit ack that landed beside it: the honest one is
                # only ever emitted after the mod watched the health hit zero.
                killed = True
                break
            if verified and unkilled_since is None:
                unkilled_since = time.monotonic()
                log.warning("[vault] park ack UNKILLED sid=%s cmd_id=%s actor=%s — the mod "
                            "short-circuited on an already-dead/sleeping pawn and dispatched "
                            "no kill; holding %.0fs for a real one",
                            steam_id, cmd_id, actor, _UNKILLED_ACK_GRACE_SECS)
            if await asyncio.to_thread(game_ipc.read_restore_status, steam_id, None, "kill_failed", None, cmd_id):
                # The mod REFUSED the kill — the dino is alive by the mod's own
                # word, so the pre-kill line is retired.
                if recovery_id:
                    await asyncio.to_thread(_journal_prune, {recovery_id}, "kill refused by mod")
                _set_job(jid, "failed", "El servidor no pudo eliminar tu dino. Intenta de nuevo.")
                return
            if unkilled_since is None:
                # players.json health<=0 is a real death observation ONLY while
                # the mod has not told us it skipped the kill. A safe-logging
                # pawn also reads zero health, so once the short-circuit is on
                # the record this reading proves nothing.
                fresh = await asyncio.to_thread(game_ipc.read_player, steam_id, True)
                if fresh is not None and _is_online(fresh) and float(fresh.get("health") or 0) <= 0:
                    killed = True
                    break
            elif (time.monotonic() - unkilled_since) >= _UNKILLED_ACK_GRACE_SECS:
                break
            await asyncio.sleep(0.5)
        if not killed and unkilled_since is not None:
            # ★ THE DUPE DOOR. Nothing was killed, so nothing is owed and
            # nothing may ever be promoted: the pre-kill journal line goes, or
            # the drain would hand out a copy of an animal still being ridden.
            # The cooldown is NOT stamped — the player never got a park.
            if recovery_id:
                await asyncio.to_thread(
                    _journal_prune, {recovery_id}, "mod acked without killing")
            log.warning("[vault] park REFUSED unkilled-ack sid=%s cmd_id=%s actor=%s rid=%s "
                        "cls=%s growth=%s — dino left alive, nothing stored",
                        steam_id, cmd_id, actor, (recovery_id or "")[:12],
                        snapshot.get("dino") or snapshot.get("dino_class") or "?",
                        snapshot.get("growth"))
            _set_job(jid, "failed", _PARK_UNKILLED_MSG)
            return
        if not killed:
            # Kill UNCONFIRMED — the order is already queued and can still land
            # after this window (exactly how the 2026-07-29/30 parks were lost:
            # the kill executed 6-24s in, the ack never verifies, and the
            # health<=0 read lost the race against the mod's health_zero evict).
            # The pre-kill journal line STAYS: if the death log proves the kill,
            # the drain stores the dino; if it stayed alive, nothing promotes.
            # Never again claim "no se guardó nada" here — that was a lie. The
            # automatic-restore promise is only made when a journal line exists
            # to pay it (LIN_PARK_JOURNAL=0 keeps the old wording).
            log.warning("[vault] park kill unconfirmed sid=%s cmd_id=%s rid=%s (journal kept)",
                        steam_id, cmd_id, (recovery_id or "")[:12])
            if recovery_id:
                _set_job(jid, "unknown",
                         "El servidor no confirmó la eliminación a tiempo. Si tu dino murió, "
                         "aparecerá en tu bóveda automáticamente en unos minutos; si sigue "
                         "vivo en tu partida, no se guardó nada.")
            else:
                _set_job(jid, "failed",
                         "El servidor no confirmó la eliminación a tiempo. Tu dino sigue en partida; no se guardó nada.")
            return
        kill_confirmed = True
        # A confirmed park is the authoritative dinosaur-switch boundary.
        # Reset GEN-0 here instead of depending solely on the mod's JSONL
        # event, whose first-tail/end semantics can miss both acknowledgements
        # across a backend bounce.  Containment lives in the helper: infection
        # persistence must never turn a safely killed dinosaur into a lost park.
        await _reset_gen0_after_dino_switch(steam_id, "park_confirmed")
        new_id = await asyncio.to_thread(save_parked, steam_id, discord_id, snapshot, cap,
                                         recovery_id or None)
        if new_id is None:
            # Cap reached between the request gate and the save — the dino is
            # already dead, so this used to be a silent loss. Upgrade the line:
            # the drain re-inserts the moment a slot frees up.
            durable = await asyncio.to_thread(
                _upgrade_journal_to_postkill, recovery_id, steam_id, discord_id,
                snapshot, cap, "vault_full")
            if durable:
                _set_job(jid, "unknown",
                         "Tu bóveda estaba llena al guardar, pero tu dino está a salvo: "
                         "libera un espacio y aparecerá automáticamente en unos minutos.")
            else:
                _set_job(jid, "failed",
                         "Bóveda llena al guardar. Borra o recupera un dino e inténtalo otra vez.")
            return
        used = await asyncio.to_thread(count_parked, steam_id)
        if recovery_id:
            # Stored for real — nothing is owed. Done AFTER the committed INSERT:
            # if this prune never runs, the drain finds the row by recovery_id
            # and retires the line then. The safe direction.
            await asyncio.to_thread(_journal_prune, {recovery_id}, "park stored")
        # the parked dino's save state supersedes any pending swap record
        await asyncio.to_thread(game_ipc.clear_swap_persist, steam_id)
        # Stamp the wait only here — on the path where a dino really reached
        # the vault. A refusal, a failed kill or a queued save must never cost
        # the player two minutes for a park that did not happen.
        await asyncio.to_thread(record_park, steam_id)
        log.info("[vault] park ok sid=%s row_id=%s used=%s", steam_id, new_id, used)
        _set_job(jid, "ok", "¡Guardado en La Bóveda!", dino_id=new_id, slots_used=used)
    except Exception as e:
        log.exception("[vault] park job crashed sid=%s cmd_id=%s", steam_id, cmd_id)
        if kill_confirmed:
            # The dino is DEAD in-world; whatever crashed the save, the journal
            # must carry the dino forward. Post-kill lines drain with no further
            # evidence, so this is minutes of delay, not a loss.
            durable = False
            try:
                durable = await asyncio.to_thread(
                    _upgrade_journal_to_postkill, recovery_id, steam_id, discord_id,
                    snapshot, cap, "save_error")
            except Exception:
                log.exception("[vault] park journal upgrade crashed sid=%s", steam_id)
            if durable:
                _set_job(jid, "unknown",
                         "Hubo un error al guardar, pero tu dino está a salvo: aparecerá "
                         "en tu bóveda automáticamente en unos minutos.")
            else:
                _set_job(jid, "failed", f"Error inesperado al guardar ({e}).")
        elif kill_issued and recovery_id:
            # The order is out but the death was never observed (the crash hit
            # the ack wait). The pre-kill line STAYS — it is evidence-gated, so
            # a kill that lands promotes and a dino that lived on never does.
            log.warning("[vault] park crashed after kill order sid=%s rid=%s (journal kept)",
                        steam_id, (recovery_id or "")[:12])
            _set_job(jid, "unknown",
                     "Hubo un error mientras esperaba la confirmación. Si tu dino murió, "
                     "aparecerá en tu bóveda automáticamente en unos minutos; si sigue "
                     "vivo en tu partida, no se guardó nada.")
        else:
            if recovery_id:
                try:
                    await asyncio.to_thread(_journal_prune, {recovery_id},
                                            "park aborted before the kill")
                except Exception:
                    log.exception("[vault] park journal cleanup crashed sid=%s", steam_id)
            _set_job(jid, "failed", f"Error inesperado al guardar ({e}).")
    finally:
        _release_action(action_key)


# ── redeem (background) ───────────────────────────────────────────────────────
# Owner rule 2026-07-24 ("if they park with 30% food it should redeem and spawn
# with 30%"): a redeemed dino comes back in the CONDITION it was parked in.
# Park already snapshots the live current/max pair for every axis, so what we
# replay is the parked FRACTION — never the stored max (the pre-fix behaviour:
# every redeem handed back a full dino) and never the raw stored absolute (a row
# captured inside the growth settle carries a juvie ceiling, and replaying that
# number against a grown dino hands back a starving one).
#
# What the mod does with these four numbers (main.full.lua ApplyAllStats + the
# C++ HandleApplyStats vtable batch — both read before this was written):
#   * health / stamina / thirst are written verbatim. MaxHealth is NOT written
#     (the Lua queues max_health=0 and the species growth curve owns it), and
#     growth is restored verbatim, so the live ceiling at redeem is the same
#     curve point it was at park — the stored max is the right denominator.
#   * hunger is written verbatim, but only after the mod raises MaxHunger to
#     floor(live GetMaxHealth × HUNGER_RATIO[species]). Current food above the
#     ceiling is the Evrima regurgitate ("vomit") trap, so the hunger target is
#     computed with the mod's OWN formula and hard-clamped to that ceiling.
#   * health <= 0 is the mod's admin-add sentinel: it refills health, stamina
#     AND thirst from the live maxes. hunger <= 0 refills hunger to the ceiling.
#     Any row with no usable snapshot (legacy rows and market transfers — live
#     prod has one, id 64, with every max at 0) falls back to exactly that
#     sentinel, i.e. the old "comes back full" behaviour, so a degenerate row
#     can never come back crippled.
#
# HUNGER_RATIO is 1:1 with the mod's own table (main.full.lua ~L9260). Checked
# against live prod rows 2026-07-24: T-Rex max_health 12274.0 → max_hunger
# 4050.4 (×0.33), Triceratops 7534.4 → 3767.2 (×0.50), Kentrosaurus 2250 → 1125
# (×0.50) — the ratio reproduces the engine's own ceiling exactly. A species
# missing from the table (a future patch dino) falls back to the stored
# max_hunger, which is what the game's own ceiling stays at when the mod skips
# its SetMaxHunger write for an unlisted class.
_HUNGER_RATIO = {
    "BP_Tyrannosaurus_C": 0.33,
    "BP_Allosaurus_C": 0.33,
    "BP_Carnotaurus_C": 0.33,
    "BP_Ceratosaurus_C": 0.33,
    "BP_Deinosuchus_C": 0.33,
    "BP_Dilophosaurus_C": 0.33,
    "BP_Herrerasaurus_C": 0.33,
    "BP_Troodon_C": 0.33,
    "BP_Omniraptor_C": 0.33,
    "BP_Pteranodon_C": 0.33,
    # Austroraptor, released in Isle build 24542870. Carnivore, so 0.33 by the
    # same rule every other row here follows and the mod's own HUNGER_RATIO
    # table states in its comments ("Carnivores: 0.33 / Omnivores: 0.33 /
    # Herbivores: 0.50"). Shipped in the same wave as the mod-side entry.
    "BP_Austroraptor_C": 0.33,
    "BP_Stegosaurus_C": 0.50,
    "BP_Triceratops_C": 0.50,
    "BP_Maiasaura_C": 0.50,
    "BP_Diabloceratops_C": 0.50,
    "BP_Pachycephalosaurus_C": 0.50,
    "BP_Tenontosaurus_C": 0.50,
    "BP_Beipiaosaurus_C": 0.50,
    "BP_Dryosaurus_C": 0.50,
    "BP_Hypsilophodon_C": 0.50,
    "BP_Gallimimus_C": 0.50,
    "BP_Kentrosaurus_C": 0.50,
}


def _finite(value) -> float:
    """_num, but inf/NaN also collapse to 0. The mod prints players.json floats
    with %f, so a bad engine float would arrive as a parseable inf/nan — which
    then survives every `<= 0` guard and blows up math.floor. 0 routes it to the
    refill sentinel instead."""
    v = _num(value)
    return v if math.isfinite(v) else 0.0


def _vital_fraction(parked: dict, cur_key: str, max_key: str) -> float | None:
    """How full one axis was at park, 0..1 — or None when the row has no usable
    pair (max <= 0 / non-numeric / non-finite). Clamped both ends: a full bar
    can read 1.0000001 after the mod's float round-trip, and current must never
    come out above the ceiling."""
    mx = _finite(parked.get(max_key))
    if mx <= 0:
        return None
    return min(1.0, max(0.0, _finite(parked.get(cur_key)) / mx))


def _hunger_ceiling(parked: dict) -> float:
    """The MaxHunger the mod will set during this restore — the same
    floor(max_health × species ratio) arithmetic ApplyAllStats runs against the
    live actor. Falls back to the stored ceiling for an unlisted species."""
    ratio = _HUNGER_RATIO.get(str(parked.get("dino_class") or ""))
    max_health = _finite(parked.get("max_health"))
    if ratio and max_health > 0:
        return float(math.floor(max_health * ratio))
    return _finite(parked.get("max_hunger"))


def _redeem_vitals_payload(parked: dict) -> dict:
    """health / stamina / hunger / thirst absolutes for the restore command."""
    f_health = _vital_fraction(parked, "health", "max_health")
    f_stamina = _vital_fraction(parked, "stamina", "max_stamina")
    f_thirst = _vital_fraction(parked, "thirst", "max_thirst")
    f_hunger = _vital_fraction(parked, "hunger", "max_hunger")

    # The mod's sentinel refills health, stamina AND thirst off r.health alone,
    # so those three are all-or-nothing here: if any one of them has no usable
    # snapshot, hand the whole trio back to the sentinel rather than restore a
    # dino with, say, zero stamina it can never regain.
    if f_health is None or f_stamina is None or f_thirst is None:
        health = stamina = thirst = 0.0
    else:
        # All three are floored at 1, never 0. Health at 0 would trip the mod's
        # refill sentinel — and an exactly-zero stamina or thirst is worse: the
        # mod's own post-restore check (VitalAtLeast, main.full.lua ~L9964)
        # returns FALSE for any expected <= 0, which drives stats_ok false and
        # makes a restore that actually LANDED report as a failure — leaving the
        # player with a live dino AND the vault row still sitting there.
        health = max(1.0, round(f_health * _finite(parked.get("max_health")), 2))
        stamina = max(1.0, round(f_stamina * _finite(parked.get("max_stamina")), 2))
        thirst = max(1.0, round(f_thirst * _finite(parked.get("max_thirst")), 2))

    ceiling = _hunger_ceiling(parked)
    if f_hunger is None or ceiling <= 0:
        hunger = 0.0  # sentinel: let the mod fill to its own computed ceiling
    else:
        # floor(), then clamp to the ceiling: current food must never exceed
        # max food at any instant, or Evrima makes the dino regurgitate.
        hunger = max(1.0, min(float(math.floor(f_hunger * ceiling)), ceiling))
    return {"health": health, "stamina": stamina, "hunger": hunger, "thirst": thirst}


def _redeem_diet_payload(parked: dict) -> tuple[float, float, float]:
    """Nutrients to re-apply after a redeem. The park snapshot wins whenever the
    row has one (owner rule 2026-07-24: the dino comes back with the diet it was
    parked with) — the mod reads and writes the same NutrientsStruct
    Carb/Protein/Lipid floats, so a stored triple replays verbatim. One axis at
    0 is REAL (a dino that ate no fat), so "has a snapshot" means ANY axis above
    0; rows saved before diet capture existed keep the species-baseline estimate
    below."""
    stored = (_num(parked.get("diet_a")), _num(parked.get("diet_b")), _num(parked.get("diet_c")))
    if any(v > 0 for v in stored):
        return (round(stored[0], 2), round(stored[1], 2), round(stored[2], 2))
    parked_dino = str(parked.get("dino_class") or "")
    baseline = _REDEEM_DIET_BASELINES.get(parked_dino, {"carbs": 100, "protein": 100, "lipids": 100})
    growth = _num(parked.get("growth"))
    prime_mult = 1.0 if parked.get("is_prime") else 0.70
    if baseline["carbs"] <= 20:
        return (round(baseline["carbs"] * prime_mult * 0.30, 2),
                round(baseline["protein"] * prime_mult * 0.30, 2),
                round(baseline["lipids"] * prime_mult * 0.30, 2))
    return (max(1, round(baseline["carbs"] * prime_mult * growth * 0.345)),
            max(1, round(baseline["protein"] * prime_mult * growth * 0.345)),
            max(1, round(baseline["lipids"] * prime_mult * growth * 0.345)))


async def _await_restore_actor_ready(steam_id: str, confirmed_actor: str) -> str:
    target = str(confirmed_actor or "").strip()
    for attempt in range(1, RESTORE_DIET_READY_POLLS + 1):
        cp = await asyncio.to_thread(game_ipc.read_player, steam_id, True) or {}
        polled = str(cp.get("actor_name", "") or "").strip()
        if polled and not target:
            target = polled
        if target and _num(cp.get("max_hunger")) > 0:
            break
        if attempt < RESTORE_DIET_READY_POLLS:
            await asyncio.sleep(RESTORE_DIET_READY_INTERVAL)
    return target


async def _apply_redeem_side_effects(steam_id: str, parked: dict, success_status: dict | None) -> None:
    try:
        parked_dino = str(parked.get("dino_class") or "")
        confirmed_actor = str((success_status or {}).get("actor_name") or "").strip()
        # SkinKeeper revive-at-redeem (web twin, 2026-08-07): the park kill
        # retired the recipe and this replay repaints only THIS session, so
        # every website park->redeem lost the skin at the next relog / server
        # restart. Revive FIRST (before actor resolution) so even an
        # actor_not_found redeem heals at the player's next relog.
        revive_outcome = await asyncio.to_thread(
            _revive_skin_recipe_after_redeem, steam_id, parked_dino, confirmed_actor)
        log.info("[SkinKeeper] redeem revive sid=%s class=%s outcome=%s",
                 steam_id, parked_dino, revive_outcome)
        # Record fallback (2026-08-07): the revive covers only a same-class
        # stored row; a cross-species redeem (one recipe row per player, a
        # multi-species vault) or a no-row player still lost the look at the
        # next relog. Gated on the revive outcome so the true recipe always
        # outranks the parked copy.
        if revive_outcome == "no_recipe" or revive_outcome.startswith("class_mismatch"):
            fallback_outcome = await asyncio.to_thread(
                _record_parked_recipe_fallback, steam_id, parked_dino,
                confirmed_actor, str(parked.get("skin_data") or ""))
            log.info("[SkinKeeper] redeem record_fallback sid=%s class=%s outcome=%s",
                     steam_id, parked_dino, fallback_outcome)
        target_actor = await _await_restore_actor_ready(steam_id, confirmed_actor)
        target_actor = confirmed_actor or target_actor
        if not target_actor:
            # This replay is what puts the parked skin AND SEX back on the
            # restored pawn — skipping it silently is how a redeemed dino came
            # back the wrong sex (owner report 2026-07-30). The restore itself
            # confirmed, so a missing actor here is worth an ERROR, not silence.
            log.error("[vault] redeem side-effects SKIPPED sid=%s dino=%s "
                      "reason=actor_not_found — skin/sex/diet NOT replayed",
                      steam_id, parked_dino)
            return
        c, p, l = _redeem_diet_payload(parked)
        await asyncio.to_thread(game_ipc.write_diet_command, {
            "class": parked_dino, "actor_name": target_actor, "steamid": steam_id,
            "carbs": c, "protein": p, "lipids": l,
        })
        skin_data = str(parked.get("skin_data") or "")
        if skin_data.strip():
            try:
                skin_cmd = json.loads(skin_data)
            except (ValueError, json.JSONDecodeError):
                skin_cmd = None
            if isinstance(skin_cmd, dict):
                skin_cmd["class"] = parked_dino
                skin_cmd["steamid"] = steam_id
                skin_cmd["actor_name"] = target_actor
                wrote = await asyncio.to_thread(game_ipc.write_skin_command, skin_cmd)
                if wrote:
                    log.info("[vault] redeem skin+sex replay sid=%s actor=%s female=%s",
                             steam_id, target_actor, skin_cmd.get("female"))
                else:
                    log.error("[vault] redeem skin+sex replay WRITE FAILED sid=%s actor=%s "
                              "female=%s — dino keeps the spawn-screen sex",
                              steam_id, target_actor, skin_cmd.get("female"))
            else:
                log.error("[vault] redeem skin replay sid=%s actor=%s "
                          "reason=skin_data_unparseable — sex NOT replayed",
                          steam_id, target_actor)
        else:
            # Store-bought rows (and parks whose snapshot capture missed) have
            # nothing to replay: the dino keeps the sex of the pawn it was
            # redeemed onto. Stated per-redeem so a sex complaint is diagnosable.
            log.info("[vault] redeem skin replay sid=%s actor=%s skin_data=absent "
                     "— sex stays as spawned", steam_id, target_actor)
    except Exception:
        log.exception("[vault] redeem side-effects failed sid=%s", steam_id)


async def _late_redeem_side_effects(steam_id: str, parked: dict, status: dict | None) -> None:
    """Replay skin/sex/diet for a redeem finalised AFTER its verify job died
    (timeout / backend bounce). The normal success path replays these; the late
    path never did, so a timed-out-but-landed redeem handed back a dino with
    the throwaway spawn's sex and default look (owner report 2026-07-30).

    Fail-closed guard: the finalise can run long after the restore landed, so
    only replay when the restore's own confirmed actor is STILL the player's
    live actor — a death/respawn in between means this life is no longer the
    redeemed dino and stamping the old skin/sex onto it would be a new bug."""
    try:
        confirmed_actor = str((status or {}).get("actor_name") or "").strip()
        if not confirmed_actor:
            log.warning("[vault] late redeem side-effects skipped sid=%s "
                        "reason=no_confirmed_actor", steam_id)
            return
        current = await asyncio.to_thread(game_ipc.read_player, steam_id, True) or {}
        live_actor = str(current.get("actor_name") or "").strip()
        if live_actor != confirmed_actor:
            log.warning("[vault] late redeem side-effects skipped sid=%s confirmed=%s "
                        "live=%s reason=life_moved_on", steam_id, confirmed_actor,
                        live_actor or "offline")
            return
        await _apply_redeem_side_effects(steam_id, parked, status)
    except Exception:
        log.exception("[vault] late redeem side-effects failed sid=%s", steam_id)


def start_redeem(steam_id: str, dino_id: int) -> dict:
    parked = get_parked_by_id(dino_id)
    if not parked or str(parked.get("steam_id")) != str(steam_id):
        raise HTTPException(404, "Ese dino guardado no te pertenece o no existe.")
    if _redeem_pending_fresh(parked):
        raise HTTPException(409, "Ya hay una recuperación en progreso para ese dino.")
    remaining = redeem_cooldown_remaining(steam_id)
    if remaining > 0:
        raise HTTPException(429, f"Espera {(remaining + 59)//60} min antes de volver a recuperar.")
    row = game_ipc.read_player(steam_id)
    fails = redeem_gate_failures(row, parked)
    if fails:
        raise HTTPException(400, {"message": "No puedes recuperar todavía.", "reasons": fails})

    cmd_id = uuid.uuid4().hex
    marked, _row, reason = mark_redeem_pending(dino_id, steam_id, cmd_id, _now_ms())
    if not marked:
        msg = {"missing": "Ese dino ya no existe.",
               "owner_mismatch": "Ese dino no te pertenece.",
               "pending_locked": "Ya hay una recuperación en progreso para ese dino.",
               "update_missed": "No se pudo iniciar la recuperación. Intenta de nuevo."}.get(reason, "No se pudo iniciar.")
        raise HTTPException(409, msg)

    jid = _new_job("redeem", steam_id)
    log.info("[vault] redeem start sid=%s dino_id=%s cmd_id=%s job=%s", steam_id, dino_id, cmd_id, jid)
    _schedule(_run_redeem(jid, steam_id, int(dino_id), parked, cmd_id))
    return {"job_id": jid}


async def _run_redeem(jid, steam_id, dino_id, parked, cmd_id):
    cmd_sent = False
    try:
        # LIN dino.py restore shape, now WITH the prime mission state when the
        # row has it. Vitals come back at the fraction they were parked at (see
        # _redeem_vitals_payload) — this used to send the stored max_* on every
        # axis, which is why every redeem handed back a full dino.
        vitals = _redeem_vitals_payload(parked)
        cmd = {
            "type": "restore",
            "steamid": steam_id,
            "cmd_id": cmd_id,
            "dino_id": dino_id,
            "expected_species": parked.get("dino_class"),
            "expected_class": parked.get("dino_class"),
            "growth": parked.get("growth"),
            "health": vitals["health"],
            "stamina": vitals["stamina"],
            "hunger": vitals["hunger"],
            "thirst": vitals["thirst"],
            "is_prime": bool(parked.get("is_prime")),
            "is_elder": bool(parked.get("is_elder")),
            "mutations": parked.get("mutations") or "",
            "parent_mutations": parked.get("parent_mutations") or "",
            "elder_mutations": parked.get("elder_mutations") or "",
            "elder_stacks": int(_num(parked.get("elder_stacks"))),
            "skin_code": parked.get("skin_code") or "",
            "diet_a": _num(parked.get("diet_a")),
            "diet_b": _num(parked.get("diet_b")),
            "diet_c": _num(parked.get("diet_c")),
            # CAPACITY FLOOR (2026-08-05): the stored max_health rides along so
            # the mod can verify the species-curve recompute reached the parked
            # capacity and re-assert state when it fell short ("came back
            # lighter"). A mod without the parser field ignores unknown keys,
            # so this is additive and inert on its own.
            "max_health": _num(parked.get("max_health")),
        }
        # ★Only sent when the row RECORDED them. Sending 0 for a row that never
        # recorded anything would tell the mod "this dino completed no missions"
        # — which is a different claim from "we don't know", and it is the claim
        # that strips Prime off a sub-75% dino. Absent, the mod keeps doing
        # exactly what it does today, so a legacy row is unchanged rather than
        # newly wrong.
        prime_state = _prime_state_from_payload(parked)
        cmd.update(prime_state)
        log.info("[vault] redeem prime-state sid=%s dino_id=%s %s",
                 steam_id, dino_id,
                 " ".join("%s=%s" % (k, prime_state.get(k, "absent"))
                          for k in _PRIME_STATE_COLS))
        log.info("[vault] redeem vitals sid=%s dino_id=%s h=%.1f st=%.1f hu=%.1f th=%.1f "
                 "(parked %.0f%%/%.0f%%/%.0f%%/%.0f%% of max)",
                 steam_id, dino_id, vitals["health"], vitals["stamina"],
                 vitals["hunger"], vitals["thirst"],
                 100.0 * (_vital_fraction(parked, "health", "max_health") or 0.0),
                 100.0 * (_vital_fraction(parked, "stamina", "max_stamina") or 0.0),
                 100.0 * (_vital_fraction(parked, "hunger", "max_hunger") or 0.0),
                 100.0 * (_vital_fraction(parked, "thirst", "max_thirst") or 0.0))
        log.info("[vault] redeem capacity sid=%s dino_id=%s max_health=%.1f",
                 steam_id, dino_id, _num(parked.get("max_health")))
        ok = await asyncio.to_thread(game_ipc.write_game_command, cmd)
        if not ok:
            await asyncio.to_thread(clear_redeem_pending, dino_id, steam_id, cmd_id)
            _set_job(jid, "failed", "No pude escribir la orden al servidor. Intenta de nuevo.")
            return
        cmd_sent = True
        _set_job(jid, "pending", "Recuperando tu dino… no cierres esta página (hasta ~100 s).")
        deadline = time.monotonic() + REDEEM_VERIFY_TIMEOUT_SECS
        while time.monotonic() < deadline:
            state, status = await asyncio.to_thread(_restore_terminal_state, cmd_id, steam_id, dino_id)
            if _restore_reached_world(status) and (
                    state == "ambiguous"
                    or (state == "failed"
                        and (_finite_float((status or {}).get("health_observed")) or 0.0) > 0.0)):
                # The dino is in their hands: either only a non-essential
                # confirmation is missing (ambiguous), or the verify refused a
                # delivery whose LIVING body was read back (failed + health>0,
                # the growth/health mismatch class - store stego 7060 was
                # delivered twice through the failed branch 2026-08-06).
                # Unlocking a delivered dino mints a duplicate. A dead or
                # zero-health spawn is NOT carved - custody stays with the
                # vault (dino 6303 class kept its row correctly).
                if state == "failed":
                    log.warning("[vault] redeem FAILED verdict but delivered - finalising "
                                "sid=%s dino_id=%s actor=%s", steam_id, dino_id,
                                str((status or {}).get("live_actor_name") or "?"))
                else:
                    log.warning("[vault] redeem AMBIGUOUS but delivered - finalising "
                                "sid=%s dino_id=%s actor=%s", steam_id, dino_id,
                                str((status or {}).get("live_actor_name") or "?"))
                state = "success"
            if state == "success":
                deleted = await asyncio.to_thread(delete_if_redeem_cmd, dino_id, steam_id, cmd_id)
                if deleted == 1 or (await asyncio.to_thread(get_parked_by_id, dino_id)) is None:
                    await asyncio.to_thread(record_redeem, steam_id)
                    # the restored dino's save state supersedes any pending swap record
                    await asyncio.to_thread(game_ipc.clear_swap_persist, steam_id)
                    used = await asyncio.to_thread(count_parked, steam_id)
                    # Skin and diet replay behind the players.json actor poll.
                    # Nothing here moves the player: a redeem leaves them exactly
                    # where they redeemed from (owner ruling 2026-07-29).
                    _schedule(_apply_redeem_side_effects(steam_id, parked, status))
                    # Memo BEFORE announcing ok, so a park pressed the same
                    # second is already judged against this delivery.
                    await asyncio.to_thread(_note_redeem_for_race_gate, steam_id, parked)
                    log.info("[vault] redeem ok sid=%s dino_id=%s", steam_id, dino_id)
                    _set_job(jid, "ok", "✅ Recuperación confirmada.", slots_used=used,
                             redeem_cooldown_s=REDEEM_COOLDOWN_SECS)
                    return
            if state == "failed":
                await asyncio.to_thread(clear_redeem_pending, dino_id, steam_id, cmd_id)
                log.info("[vault] redeem failed sid=%s dino_id=%s", steam_id, dino_id)
                _set_job(jid, "failed", "La recuperación falló. Tu dino guardado sigue a salvo.")
                return
            await asyncio.sleep(1.0)
        # timeout: leave the pending marker; once it goes stale (TTL above) the
        # gates self-heal it via resolve_stale_redeem_pending — no admin needed.
        log.warning("[vault] redeem timeout sid=%s dino_id=%s cmd_id=%s", steam_id, dino_id, cmd_id)
        _set_job(jid, "pending",
                 "Recuperación aún pendiente. Si falló, tu dino se desbloqueará solo en unos minutos; no reintentes todavía.")
    except Exception as e:
        log.exception("[vault] redeem job crashed sid=%s cmd_id=%s", steam_id, cmd_id)
        if not cmd_sent:
            # The restore order never reached the game: nothing can deliver,
            # unlocking is safe and the player may retry at once.
            try:
                await asyncio.to_thread(clear_redeem_pending, dino_id, steam_id, cmd_id)
            except Exception:
                pass
            _set_job(jid, "failed", f"Error inesperado al recuperar ({e}).")
        else:
            # The order is OUT. A blind unlock here is the crash-window twin of
            # the FAILED-verdict door (store stego 7060): if the mod delivers
            # while we are down, the unlocked row mints a duplicate. Keep the
            # marker - resolve_stale_redeem_pending judges it in ~minutes on
            # world evidence and unlocks or finalises exactly-once.
            log.warning("[vault] redeem crashed AFTER order sent - marker kept "
                        "sid=%s dino_id=%s cmd_id=%s (stale sweep will resolve)",
                        steam_id, dino_id, cmd_id)
            _set_job(jid, "pending",
                     "Recuperación aún pendiente. Si falló, tu dino se desbloqueará "
                     "solo en unos minutos; no reintentes todavía.")
