"""Admin PLAYER-species population control (NOT AI).

Reads/writes the SAME artefacts the bot's popcontrol.py enforces:
  * species_caps table in the bot DB (per-species playable cap).
  * species_lock_state.json in the bot DATA_DIR (which species are locked).
  * pop_control_audit table (append-only audit trail).
  * a settings row `popcontrol_auto` (create the settings table if absent) that
    the bot's auto-population loop reads.

The web only performs DB / file writes; the bot's loop is what actually enforces
the roster via RCON. This module NEVER touches Game.ini or RCON.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

import game_ipc

log = logging.getLogger("laislanublar.pop")

# Default Gateway playable roster (mirrors the PROD bot config.py _DEFAULT_SPECIES,
# 22 species including Kentrosaurus and Austroraptor); env-overridable so the
# web and bot agree.
_DEFAULT_SPECIES = [
    "BP_Tyrannosaurus_C", "BP_Allosaurus_C", "BP_Carnotaurus_C", "BP_Ceratosaurus_C",
    "BP_Deinosuchus_C", "BP_Dilophosaurus_C", "BP_Herrerasaurus_C", "BP_Troodon_C",
    "BP_Stegosaurus_C", "BP_Triceratops_C", "BP_Maiasaura_C", "BP_Diabloceratops_C",
    "BP_Pachycephalosaurus_C", "BP_Tenontosaurus_C", "BP_Beipiaosaurus_C",
    "BP_Dryosaurus_C", "BP_Hypsilophodon_C", "BP_Gallimimus_C", "BP_Omniraptor_C",
    "BP_Pteranodon_C", "BP_Kentrosaurus_C",
    # 2026-08-04, Isle build 24542870: enabled in Game.ini AllowedClasses.
    "BP_Austroraptor_C",
]


def _species_from_env() -> list[str]:
    raw = os.environ.get("LAISLANUBLAR_SPECIES", "").strip()
    if not raw:
        return list(_DEFAULT_SPECIES)
    return [s.strip() for s in raw.split(",") if s.strip()]


SUPPORTED_SPECIES = _species_from_env()


def canonical_species(raw: str) -> str:
    name = str(raw or "").strip()
    if name in SUPPORTED_SPECIES:
        return name
    if name.startswith("BP_") and name.endswith("_C"):
        name = name[3:-2]
    by_key = {s.casefold(): s for s in SUPPORTED_SPECIES}
    return by_key.get(name.casefold(), "")


def _connect():
    if not os.path.isfile(game_ipc.BOT_DB_PATH):
        raise HTTPException(503, "La base de datos del bot no está disponible.")
    conn = sqlite3.connect(game_ipc.BOT_DB_PATH, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def ensure_settings(conn: sqlite3.Connection | None = None) -> None:
    """Create the settings table if the bot has not yet (the bot reads
    popcontrol_auto from it). Safe to call repeatedly."""
    own = conn is None
    if own:
        if not os.path.isfile(game_ipc.BOT_DB_PATH):
            return
        conn = _connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings ("
            "key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
        )
    finally:
        if own:
            conn.close()


# ── reads ─────────────────────────────────────────────────────────────────────
def read_caps() -> dict[str, int]:
    conn = _connect()
    try:
        try:
            rows = conn.execute("SELECT species, cap FROM species_caps").fetchall()
        except sqlite3.OperationalError:
            return {}
        return {str(r["species"]): int(r["cap"]) for r in rows}
    finally:
        conn.close()


def read_locked() -> list[str]:
    data = game_ipc.read_json_file(game_ipc.SPECIES_LOCK_STATE_FILE)
    locked = data.get("locked", []) if isinstance(data, dict) else []
    return [s for s in locked if s in SUPPORTED_SPECIES]


def read_auto() -> bool:
    conn = _connect()
    try:
        ensure_settings(conn)
        r = conn.execute("SELECT value FROM settings WHERE key = 'popcontrol_auto'").fetchone()
        return str((r["value"] if r else "0")).strip().lower() in {"1", "true", "yes", "on"}
    finally:
        conn.close()


def _counts() -> dict[str, int]:
    players = game_ipc.read_players_json()
    if not isinstance(players, dict):
        return {}
    counts: Counter = Counter()
    for row in players.values():
        if not isinstance(row, dict):
            continue
        sp = canonical_species(row.get("dino") or row.get("dino_class") or row.get("class") or "")
        if sp:
            counts[sp] += 1
    return dict(counts)


def _state(caps: dict[str, int], locked: set[str], auto: bool) -> dict:
    counts = _counts()
    return {
        "species": [
            {
                "species": sp,
                "cap": int(caps.get(sp, 100)),
                "count": int(counts.get(sp, 0)),
                "locked": sp in locked,
            }
            for sp in SUPPORTED_SPECIES
        ],
        "locked": sorted(locked),
        "playable": [sp for sp in SUPPORTED_SPECIES if sp not in locked],
        "auto": bool(auto),
        "counts_available": bool(counts) or game_ipc.read_players_json() is not None,
    }


def state() -> dict:
    caps = read_caps() or {sp: 100 for sp in SUPPORTED_SPECIES}
    return _state(caps, set(read_locked()), read_auto())


def preview(cap_changes: dict[str, int], lock: list[str] | None,
            unlock: list[str] | None, auto: bool | None) -> dict:
    caps = read_caps() or {sp: 100 for sp in SUPPORTED_SPECIES}
    for sp, cap in cap_changes.items():
        c = canonical_species(sp)
        if c:
            caps[c] = int(cap)
    locked = set(read_locked())
    old_locked = set(locked)
    for sp in (lock or []):
        c = canonical_species(sp)
        if c:
            locked.add(c)
    for sp in (unlock or []):
        c = canonical_species(sp)
        if c:
            locked.discard(c)
    cur_auto = read_auto()
    out = _state(caps, locked, cur_auto if auto is None else bool(auto))
    out["would_lock"] = sorted(locked - old_locked)
    out["would_unlock"] = sorted(old_locked - locked)
    return out


# ── patreon unlocks (state SHARED with the bot's popcontrol.py) ───────────────
# species_unlock_state.json: {"unlocks": {"BP_X_C": {"until": iso, "actor": ...,
# "via": ...}}, "cooldowns": {"discord:<id>"|"user:<id>": iso}, "updated_at": iso}.
# The web only WRITES state here; the bot's auto-enforce loop is what re-adds an
# unlocked species to the in-game roster (<= one tick, 60 s). Readers fail OPEN
# to "no unlocks"; expired rows are pruned on every write.

def _parse_iso(value):
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def read_unlock_state() -> dict:
    data = game_ipc.read_json_file(game_ipc.SPECIES_UNLOCK_STATE_FILE)
    if not isinstance(data, dict):
        return {"unlocks": {}, "cooldowns": {}}
    unlocks = data.get("unlocks")
    cooldowns = data.get("cooldowns")
    return {"unlocks": unlocks if isinstance(unlocks, dict) else {},
            "cooldowns": cooldowns if isinstance(cooldowns, dict) else {}}


def active_unlocks() -> dict[str, int]:
    """{BP class: seconds remaining} — the REAL unlock state the bot enforces."""
    now = datetime.now(timezone.utc)
    out: dict[str, int] = {}
    for cls, row in read_unlock_state().get("unlocks", {}).items():
        if cls not in SUPPORTED_SPECIES or not isinstance(row, dict):
            continue
        until = _parse_iso(row.get("until"))
        if until is None:
            continue
        remaining = int((until - now).total_seconds())
        if remaining > 0:
            out[cls] = remaining
    return out


def unlock_cooldown_remaining(actor_key: str) -> int:
    until = _parse_iso(read_unlock_state().get("cooldowns", {}).get(str(actor_key)))
    if until is None:
        return 0
    return max(0, int((until - datetime.now(timezone.utc)).total_seconds()))


def set_unlock(cls: str, seconds: int, actor_key: str,
               cooldown_seconds: int, enforce_cooldown: bool = True) -> int:
    """Merge one unlock (+ the actor's cooldown when enforced) into the shared
    state file. Atomic tmp+replace; prunes expired rows; audits patreon_unlock.
    Returns the unlock window in seconds."""
    canonical = canonical_species(cls)
    if not canonical:
        raise HTTPException(400, "Especie inválida")
    now = datetime.now(timezone.utc)
    state = read_unlock_state()
    unlocks: dict[str, dict] = {}
    for sp, row in state.get("unlocks", {}).items():
        if sp not in SUPPORTED_SPECIES or not isinstance(row, dict):
            continue
        until = _parse_iso(row.get("until"))
        if until is not None and until > now:
            unlocks[sp] = row
    cooldowns: dict[str, str] = {}
    for key, value in state.get("cooldowns", {}).items():
        until = _parse_iso(value)
        if until is not None and until > now:
            cooldowns[str(key)] = str(value)
    until = now + timedelta(seconds=max(5, int(seconds)))
    unlocks[canonical] = {"until": until.isoformat(), "actor": str(actor_key), "via": "web"}
    if enforce_cooldown and int(cooldown_seconds) > 0:
        cooldowns[str(actor_key)] = (now + timedelta(seconds=int(cooldown_seconds))).isoformat()
    payload = {"unlocks": unlocks, "cooldowns": cooldowns, "updated_at": now.isoformat()}
    os.makedirs(os.path.dirname(game_ipc.SPECIES_UNLOCK_STATE_FILE), exist_ok=True)
    tmp = game_ipc.SPECIES_UNLOCK_STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp, game_ipc.SPECIES_UNLOCK_STATE_FILE)
    try:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO pop_control_audit (action, species, actor, source, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("patreon_unlock", canonical, str(actor_key), "web",
                 f"until={until.isoformat()}", now.isoformat()),
            )
        finally:
            conn.close()
    except Exception as e:  # audit is best-effort; the unlock itself already landed
        log.warning("pop unlock audit write failed: %s", e)
    log.info("[population] patreon_unlock species=%s actor=%s until=%s",
             canonical, actor_key, until.isoformat())
    return int(seconds)


# ── writes ────────────────────────────────────────────────────────────────────
def _write_locked_file(locked: set[str], reason: str) -> None:
    os.makedirs(os.path.dirname(game_ipc.SPECIES_LOCK_STATE_FILE), exist_ok=True)
    payload = {
        "locked": sorted(locked),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "reason": str(reason),
    }
    tmp = game_ipc.SPECIES_LOCK_STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp, game_ipc.SPECIES_LOCK_STATE_FILE)


def apply(cap_changes: dict[str, int], lock: list[str] | None, unlock: list[str] | None,
          auto: bool | None, actor: str, reason: str) -> dict:
    """DB + file writes only — the bot loop enforces. Returns the new state."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    audit_rows = 0
    try:
        ensure_settings(conn)
        for sp, cap in cap_changes.items():
            c = canonical_species(sp)
            if not c:
                continue
            conn.execute(
                "INSERT INTO species_caps (species, cap, updated_at, updated_by) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(species) DO UPDATE SET cap = excluded.cap, updated_at = excluded.updated_at, "
                "updated_by = excluded.updated_by",
                (c, int(cap), now, str(actor)),
            )
            conn.execute(
                "INSERT INTO pop_control_audit (action, species, actor, source, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("cap_update", c, str(actor), "web", str(reason), now),
            )
            audit_rows += 1
        locked = set(read_locked())
        lock_changed = False
        for sp in (lock or []):
            c = canonical_species(sp)
            if c and c not in locked:
                locked.add(c)
                lock_changed = True
                conn.execute(
                    "INSERT INTO pop_control_audit (action, species, actor, source, reason, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("manual_lock", c, str(actor), "web", str(reason), now),
                )
                audit_rows += 1
        for sp in (unlock or []):
            c = canonical_species(sp)
            if c and c in locked:
                locked.discard(c)
                lock_changed = True
                conn.execute(
                    "INSERT INTO pop_control_audit (action, species, actor, source, reason, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("manual_unlock", c, str(actor), "web", str(reason), now),
                )
                audit_rows += 1
        if lock_changed:
            _write_locked_file(locked, f"web:{actor}")
        if auto is not None:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ('popcontrol_auto', ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                ("1" if auto else "0", now),
            )
            conn.execute(
                "INSERT INTO pop_control_audit (action, species, actor, source, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("auto_" + ("on" if auto else "off"), "", str(actor), "web", str(reason), now),
            )
            audit_rows += 1
        caps = read_caps() or {sp: 100 for sp in SUPPORTED_SPECIES}
        for sp, cap in cap_changes.items():
            c = canonical_species(sp)
            if c:
                caps[c] = int(cap)
        out = _state(caps, locked, read_auto() if auto is None else bool(auto))
        out["audit_rows"] = audit_rows
        return out
    except sqlite3.OperationalError as e:
        log.warning("pop apply failed: %s", e)
        raise HTTPException(503, "No se pudo escribir en la base de datos del bot.")
    finally:
        conn.close()


def audit(limit: int = 100) -> dict:
    limit = max(1, min(int(limit), 500))
    conn = _connect()
    try:
        try:
            rows = conn.execute(
                "SELECT id, action, species, actor, source, reason, created_at "
                "FROM pop_control_audit ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return {"items": [], "note": "El registro de auditoría aún no existe."}
        return {"items": [dict(r) for r in rows], "note": None}
    finally:
        conn.close()
