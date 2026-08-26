"""SkinKeeper -- La Isla Nublar WEB side (capture).

Records the EXACT skin command ("recipe") the player just applied into the SHARED
bot sqlite (game_ipc.BOT_DB_PATH), so the bot's killfeed rejoin lane can replay it
on the next relog. Web is the schema owner alongside the bot (both carry a
byte-identical skinkeeper_shared.py); whichever process boots first creates the
table.

Capture is sited at the THREE genuine apply entry points only, keyed on the
TARGET sid (server.py /api/apply, /api/admin/apply, /api/me/rewards/skins/apply):
  * NEVER the two redeem/park replay lanes (vault.py:1510 _apply_redeem_side_effects
    and the bot's dino.py:662 _fast_skin_restore) -- both replay parked_dinos.
    skin_data, which is a game_ipc.read_skin_snapshot READBACK (set at park time,
    vault.py:1396 / bot dino.py:909). A glitch skin IS its extreme/negative
    values and they do NOT survive the ReadSkin round-trip, so recording a
    readback would persist a permanently flattened recipe. SKIP THEM.
  * NEVER a snapshot readback of any kind. The recipe is the command as ENQUEUED.

Never fatal: a bookkeeping miss must not fail an apply the dino already got.
Kill switch: LAISLANUBLAR_SKIN_CAPTURE=0 (default on).
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone

import game_ipc
import skinkeeper_shared as sk

logger = logging.getLogger("laislanublar.web.skinkeeper")


def _capture_enabled() -> bool:
    raw = os.environ.get("LAISLANUBLAR_SKIN_CAPTURE")
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _connect() -> sqlite3.Connection:
    """Autocommit connection to the SHARED bot DB. Creates the file if the bot
    has not booted yet (web-first boot) -- the 'either process may boot first'
    guarantee; the bot's init_db later adds its own tables to the same file."""
    os.makedirs(os.path.dirname(game_ipc.BOT_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(game_ipc.BOT_DB_PATH, timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def ensure_web() -> None:
    """Startup ensure (server.py on_startup, beside pop_control.ensure_settings).
    Idempotent; never raises out (a failure here must not block web startup)."""
    try:
        conn = _connect()
        try:
            sk.ensure_skin_last_applied(conn)
        finally:
            conn.close()
    except Exception as exc:  # RuntimeError (legacy shape) or sqlite -- log, do not raise
        logger.warning("[SkinKeeper] ensure_web skipped: %s", exc)


def record_apply(cmd: dict, kind: str) -> bool:
    """Record the recipe just enqueued. cmd is the EXACT command handed to
    game_ipc.write_skin_command (after to_command / build_glitch_command and any
    in-place clamp), keyed on cmd['steamid'] (the TARGET player, never the acting
    admin). `kind` is 'regular' or 'glitch' -- diagnostic on LIN (a single write
    lane) but stored load-bearing; the glitch/regular distinction is preserved
    structurally by the verbatim payload (color_space present vs absent,
    variation 0.0). Returns True on a persisted change; never raises."""
    if not _capture_enabled():
        return False
    try:
        if not isinstance(cmd, dict):
            return False
        # Defensive: a restore echo (our own rejoin- re-queue) must never be
        # re-captured. LIN's apply routes never set request_id, so this is a
        # no-op guard today, kept for fleet parity + future-proofing.
        if sk.is_restore_echo(cmd):
            return False
        sid = str(cmd.get("steamid") or "").strip()
        if not sk.is_valid_sid(sid):
            logger.warning("[SkinKeeper] skin_recipe_record_skipped reason=bad_sid sid=%r kind=%s",
                           sid, kind)
            return False
        recipe = sk.canonical_recipe(cmd)
        payload_json = sk.canonical_payload_json(recipe)
        digest = sk.compute_recipe_digest(sid, payload_json)
        conn = _connect()
        try:
            sk.ensure_skin_last_applied(conn)
            changed = sk.record_skin_recipe(
                conn, sid,
                dino_class=str(cmd.get("class") or ""),
                actor_name=str(cmd.get("actor_name") or ""),
                kind=str(kind or ""),
                payload_json=payload_json,
                recipe_digest=digest,
                updated_utc=datetime.now(timezone.utc).isoformat(),
            )
        finally:
            conn.close()
        logger.info("[SkinKeeper] skin_apply_recorded sid=%s kind=%s class=%s changed=%s",
                    sid, kind, str(cmd.get("class") or ""), changed)
        return changed
    except Exception as exc:  # capture is NEVER fatal
        logger.warning("[SkinKeeper] skin_recipe_record_failed sid=%s kind=%s err=%s",
                       str(cmd.get("steamid") if isinstance(cmd, dict) else "?"), kind, exc)
        return False


# ============================================================
# BirthSkin (2026-07-30) - hatchling inherited-skin persistence.
# Ported from the Arkadia reference (LIVE 2026-07-30); LaIslaNublar adaptation
# of the fleet port spec PORT_SPEC_BIRTHSKIN_20260730.
#
# WHY: a nest-birthed hatchling inherits its parents' full palette at birth and
# the ENGINE SAVES IT (TheIslePersistence.db, rails included) -- but the LOGIN
# validator strips OUT-OF-RANGE channel values when the pawn is rebuilt, so a
# baby born to a store/glitch-skinned parent visibly loses the inherited look
# on every relog/crash/safe-log reconnect. Buyers are repainted by SkinKeeper;
# birthed babies never applied anything, so no recipe exists. This lane
# synthesizes that missing recipe FROM THE GAME'S OWN SAVE ROW (the save holds
# the TRUE raw values -- no pawn readback, so nothing flattens) and the
# EXISTING SkinKeeper rejoin lane (bot skinkeeper_bot.dispatch_batch) does
# every repaint. No new restore code.
#
# LIFECYCLE ("if they die then no" -- owner order 2026-07-30):
#  * Observed death        -> the existing bot death lane deactivates the
#    recipe (skinkeeper_bot.deactivate_recipes, victim-keyed).
#  * Unobserved death      -> the game DELETES the save row at death; the next
#    sweep sees the row gone and retires the birth recipe (reconcile). A
#    "Save file found" rejoin structurally REQUIRES the save row to exist, so
#    a dead life can never be repainted by this lane even inside the window.
#  * Death + rebirth       -> new character Id in the save row; reconcile
#    retires the old recipe and capture re-captures the NEW baby same sweep.
#  * Real apply (web/store)-> upserts the same PK row with kind regular/glitch;
#    capture never touches an ACTIVE non-birth row (guard is IN the SQL, so a
#    concurrent web apply cannot be clobbered by a sweep race).
#  * Park/redeem           -> a park kills the pawn and the save row goes with
#    it -> reconcile retires, exactly like a death; a redeem creates a fresh
#    save row (new life) and is re-evaluated on its own saved values.
#  * Class change (redeem swap) -> reconcile retires the birth recipe.
#  * Recipe-age expiry (LIN-ONLY adaptation) -> the bot rejoin lane bounds
#    recipe age (LAISLANUBLAR_SKIN_RECIPE_MAX_AGE_SECONDS, default 7d, the
#    unobserved-death backstop) and retires an expired recipe at the next
#    rejoin. For a birth recipe on a STILL-LIVING life (save row present with
#    the SAME class+Id -- a death deletes the row) that would strand the baby
#    unpainted forever behind the capture-once ledger. The sweep's reconcile
#    clears the ledger entry for exactly that shape, so capture re-captures
#    the living life next pass. A ledger sid superseded by a REAL apply (any
#    non-birth row, active or not) is left alone -- the applied look owns
#    that life now.
#
# SCOPE: only birthed rows carrying at least one OUT-OF-RANGE channel value
# (deviation > LAISLANUBLAR_SKIN_BIRTH_MIN_DEVIATION, default 0.01) are
# captured -- in-range inherited colours survive the login validator natively
# (census-proven), so restoring them adds only risk.
# LAISLANUBLAR_SKIN_BIRTH_CAPTURE_ALL=1 widens to every birthed row if a
# future game build changes the validator.
#
# DIALECT: payload keys mirror LIN's live GLITCH apply dialect exactly
# (sampled from prod skin_last_applied rows 2026-07-30): the 7 colour slots +
# class/female/pattern/preserve_female/skin_code/variation, color_space
# ABSENT (the raw-verbatim contract -- rails replay untouched),
# preserve_female True (LIN keeps the pawn's own sex on every replay; the
# 2026-07-25 sex-flip fix), values VERBATIM from the save, variation exact.
# The bot restore lane replays the payload byte-for-byte and stamps
# preserve_female=True itself, so this is idempotent there.
#
# PERF: one bounded pass per LAISLANUBLAR_SKIN_BIRTH_SWEEP_SECONDS (default
# 600) in a worker thread: one file copy of the persistence db (the game's
# live handle is NEVER opened -- the db is legacy-journal so a plain copy is
# coherent-or-fails-parse), one SQL-prefiltered parse, a handful of tiny
# writes on this module's own short-lived _connect(). Sweeps are scheduled
# from server.dino_snapshot_loop's ~20s pass, time-gated here.
# Kill switch: LAISLANUBLAR_SKIN_BIRTH_CAPTURE=0.
# ============================================================

import asyncio
import json
import shutil
import time


def _birth_env_flag(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _birth_env_int(name, default, lo, hi):
    try:
        v = int(str(os.environ.get(name, "")).strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _birth_env_float(name, default, lo, hi):
    try:
        v = float(str(os.environ.get(name, "")).strip() or default)
    except (TypeError, ValueError):
        v = default
    return min(hi, max(lo, v))


BIRTH_CAPTURE_ENABLED = _birth_env_flag("LAISLANUBLAR_SKIN_BIRTH_CAPTURE", True)
BIRTH_SWEEP_SECONDS = _birth_env_int("LAISLANUBLAR_SKIN_BIRTH_SWEEP_SECONDS", 600, 120, 86400)
BIRTH_ROW_CAP = _birth_env_int("LAISLANUBLAR_SKIN_BIRTH_ROW_CAP", 1000, 50, 100000)
BIRTH_CAPTURE_ALL = _birth_env_flag("LAISLANUBLAR_SKIN_BIRTH_CAPTURE_ALL", False)
BIRTH_MIN_DEVIATION = _birth_env_float("LAISLANUBLAR_SKIN_BIRTH_MIN_DEVIATION", 0.01, 0.0, 100.0)
BIRTH_PERSIST_DB = (str(os.environ.get("LAISLANUBLAR_PERSIST_DB_PATH", "")).strip()
                    or os.path.join(game_ipc.SAVED_DIR, "PlayerData", "TheIslePersistence.db"))
BIRTH_COPY_PATH = (str(os.environ.get("LAISLANUBLAR_BIRTH_SWEEP_COPY_PATH", "")).strip()
                   or os.path.join(game_ipc.DATA_DIR, "birthskin_persist_copy.tmp.db"))

# save CustomizedData key -> skin command key (the exact dialect LIN's live
# glitch applies store; sampled from prod skin_last_applied rows 2026-07-30).
# color_space is deliberately ABSENT: save values are raw engine floats and
# the absent marker is the raw-verbatim (glitch) contract, so rails replay
# untouched.
_BIRTH_SLOT_MAP = (
    ("body", "bodyColor"), ("markings", "markingsColor"), ("flank", "flankColor"),
    ("underbelly", "underbellyColor"), ("detail1", "detail1Color"),
    ("eyes", "eyesColor"), ("male_display", "maleDisplayColor"),
)
_BIRTH_EMPTY_ANCESTORS_MARKER = '"Ancestors": []'
_birth_last_sweep_mono = -1.0e9
_birth_sweep_task = None
_birth_armed_logged = False
_birth_bg_tasks = set()


def _birth_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _birth_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


def _birth_class_bp(class_path):
    """'/Game/...BP_Tyrannosaurus.BP_Tyrannosaurus_C' -> 'BP_Tyrannosaurus_C'.
    Empty string on anything that does not look like a pawn class."""
    tail = str(class_path or "").rsplit(".", 1)[-1].strip()
    if tail.startswith("BP_") and tail.endswith("_C") and len(tail) > 5:
        return tail
    return ""


def _birth_norm_class(value):
    """Mirror of the bot's skinkeeper_bot._norm_class (its rejoin class gate)."""
    return str(value or "").replace("BP_", "").replace("_C", "").strip().lower()


def _birth_rgba(cd, key):
    v = cd.get(key)
    if not isinstance(v, dict):
        return None
    return [_birth_float(v.get("r")), _birth_float(v.get("g")),
            _birth_float(v.get("b")), _birth_float(v.get("a"), 1.0)]


def _birth_deviation(slots):
    """Max distance outside [0,1] across every channel of every slot. 0.0 for a
    fully in-range palette. Rails (999 / -999 / 2.4 ...) dominate instantly."""
    worst = 0.0
    for rgba in slots.values():
        for x in rgba:
            if x < 0.0:
                worst = max(worst, -x)
            elif x > 1.0:
                worst = max(worst, x - 1.0)
    return worst


def _birth_payload(cd, cls_bp):
    """Recipe payload in the EXACT live LIN glitch apply dialect (raw-verbatim
    contract: color_space absent, preserve_female True, values verbatim,
    variation exact -- 0.0 stays the glitch-shader trigger if that is what the
    baby actually wore)."""
    slots = {}
    for cmd_key, save_key in _BIRTH_SLOT_MAP:
        rgba = _birth_rgba(cd, save_key)
        if rgba is None:
            return None, None
        slots[cmd_key] = rgba
    payload = {
        "class": cls_bp,
        "female": _birth_bool(cd.get("bIsFemale")),
        "preserve_female": True,
        "variation": _birth_float(cd.get("skinVariation")),
        "pattern": int(_birth_float(cd.get("patternIndex"))),
        "skin_code": str(cd.get("skinCode") or "")[:512],
    }
    payload.update(slots)
    return payload, slots


def _birth_identity(cls_bp, char_id):
    return "%s|%s" % (cls_bp, char_id)


def _birth_read_save_rows():
    """Copy the game's persistence db (never open the live file: a torn copy
    fails parse and skips the sweep; a reader lock on the game's own db is not
    ours to hold) and parse the birthed rows. Returns (rows, stats) or (None,
    err_string)."""
    shutil.copyfile(BIRTH_PERSIST_DB, BIRTH_COPY_PATH)
    rows = []
    stats = {"total": 0, "prefiltered": 0, "parse_fail": 0}
    conn = sqlite3.connect(BIRTH_COPY_PATH, timeout=5)
    try:
        cur = conn.execute("SELECT COUNT(*) FROM ti_player_saves")
        stats["total"] = int(cur.fetchone()[0])
        cur.close()
        cur = conn.execute(
            "SELECT steam_id, payload FROM ti_player_saves "
            "WHERE payload NOT LIKE ? LIMIT ?",
            ("%" + _BIRTH_EMPTY_ANCESTORS_MARKER + "%", BIRTH_ROW_CAP))
        fetched = cur.fetchall()
        cur.close()
        stats["prefiltered"] = len(fetched)
        for sid, payload in fetched:
            try:
                p = json.loads(payload)
                anc = p.get("Ancestors") or []
                if not anc:
                    continue
                cd = p.get("CustomizedData") or {}
                cls_bp = _birth_class_bp(p.get("Class"))
                if not cls_bp or not isinstance(cd, dict):
                    stats["parse_fail"] += 1
                    continue
                pl, slots = _birth_payload(cd, cls_bp)
                if pl is None:
                    stats["parse_fail"] += 1
                    continue
                rows.append({
                    "sid": str(sid), "cls_bp": cls_bp,
                    "char_id": p.get("Id"), "payload": pl,
                    "deviation": _birth_deviation(slots),
                })
            except (ValueError, TypeError, KeyError):
                stats["parse_fail"] += 1
        return rows, stats
    finally:
        conn.close()


def _birth_save_row_state(sid):
    """(exists, cls_bp, char_id) for ONE sid, read from the sweep's copy."""
    conn = sqlite3.connect(BIRTH_COPY_PATH, timeout=5)
    try:
        cur = conn.execute(
            "SELECT payload FROM ti_player_saves WHERE steam_id = ?", (str(sid),))
        row = cur.fetchone()
        cur.close()
        if not row:
            return False, "", None
        try:
            p = json.loads(row[0])
        except (ValueError, TypeError):
            return True, "", None
        return True, _birth_class_bp(p.get("Class")), p.get("Id")
    finally:
        conn.close()


_BIRTH_UPSERT_SQL = (
    "INSERT INTO skin_last_applied "
    "(steam_id, dino_class, actor_name, kind, payload, active, updated_utc, recipe_digest) "
    "VALUES (?, ?, '', 'birth', ?, 1, ?, ?) "
    "ON CONFLICT(steam_id) DO UPDATE SET "
    "  dino_class=excluded.dino_class, actor_name='', kind='birth', "
    "  payload=excluded.payload, active=1, updated_utc=excluded.updated_utc, "
    "  recipe_digest=excluded.recipe_digest "
    # The apply-precedence guard lives IN the SQL so a web apply landing between
    # any pre-read and this write can never be clobbered: an ACTIVE non-birth
    # row always wins. The digest predicate keeps an unchanged re-capture a
    # true no-op (updated_utc does not move; the bot's recipe-age gate stays
    # honest).
    "WHERE (skin_last_applied.kind = 'birth' OR skin_last_applied.active <> 1) "
    "  AND (skin_last_applied.recipe_digest <> excluded.recipe_digest "
    "       OR skin_last_applied.active <> 1)"
)


def _birth_sweep_once():
    """One full sweep: reconcile (retire dead/changed lives, revive the
    age-expired living) then capture. Sync, runs in a worker thread, NEVER
    raises, ALWAYS logs one summary line."""
    t0 = time.monotonic()
    counts = {"retired": 0, "captured": 0, "ledger_cleared": 0,
              "skipped_inrange": 0, "skipped_captured": 0,
              "skipped_apply": 0, "skipped_guard": 0}
    stats = {"total": 0, "prefiltered": 0, "parse_fail": 0}
    err = None
    try:
        rows, stats_or_err = _birth_read_save_rows()
        if rows is None:
            raise RuntimeError(str(stats_or_err))
        stats = stats_or_err
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = _connect()
        try:
            cur = conn.execute(
                "CREATE TABLE IF NOT EXISTS birth_skin_ledger ("
                " steam_id TEXT PRIMARY KEY,"
                " identity TEXT NOT NULL,"
                " captured_utc TEXT)")
            cur.close()

            # ---- A) reconcile: active birth recipes vs the game's own truth.
            cur = conn.execute(
                "SELECT steam_id, dino_class FROM skin_last_applied "
                "WHERE active = 1 AND kind = 'birth'")
            active_birth = cur.fetchall()
            cur.close()
            ledger = {}
            cur = conn.execute("SELECT steam_id, identity FROM birth_skin_ledger")
            for lsid, lident in cur.fetchall():
                ledger[str(lsid)] = str(lident)
            cur.close()
            retire = []
            for bsid, bclass in active_birth:
                bsid = str(bsid)
                exists, cls_bp, char_id = _birth_save_row_state(bsid)
                if not exists:
                    retire.append((bsid, "row_gone"))
                    continue
                if cls_bp and _birth_norm_class(cls_bp) != _birth_norm_class(bclass):
                    retire.append((bsid, "class_changed"))
                    continue
                led = ledger.get(bsid)
                if (led and char_id is not None
                        and led != _birth_identity(cls_bp or bclass, char_id)):
                    retire.append((bsid, "new_life"))
            for bsid, why in retire:
                cur = conn.execute(
                    "UPDATE skin_last_applied SET active = 0, updated_utc = ? "
                    "WHERE steam_id = ? AND kind = 'birth' AND active = 1",
                    (now_iso, bsid))
                cur.close()
                cur = conn.execute(
                    "DELETE FROM birth_skin_ledger WHERE steam_id = ?", (bsid,))
                cur.close()
                ledger.pop(bsid, None)
                counts["retired"] += 1
                logger.info("[BirthSkin] retired sid=%s reason=%s", bsid, why)

            # ---- A2) LIN adaptation: reconcile the LEDGER residue (sids with
            # no ACTIVE birth recipe). The bot's rejoin lane retires recipes
            # older than LAISLANUBLAR_SKIN_RECIPE_MAX_AGE_SECONDS (its
            # unobserved-death backstop); for a birth recipe on a still-living
            # life that would otherwise strand the baby unpainted forever
            # behind the capture-once ledger. Shapes:
            #  * save row GONE or identity changed -> the captured life ended;
            #    drop the stale ledger entry (hygiene).
            #  * save row ALIVE with the SAME identity and the sid's recipe row
            #    is an INACTIVE kind='birth' row (or absent) -> the retire was
            #    the age bound, not a death (a death deletes the save row);
            #    drop the ledger entry so capture re-captures this life.
            #  * any NON-birth recipe row (active or not) -> a real apply owns
            #    this life; leave the ledger entry alone.
            active_birth_sids = {str(b[0]) for b in active_birth}
            residue = [s for s in ledger if s not in active_birth_sids]
            row_kind = {}
            if residue:
                cur = conn.execute(
                    "SELECT steam_id, kind, active FROM skin_last_applied "
                    "WHERE steam_id IN (%s)"
                    % ",".join("?" for _ in residue), residue)
                for rsid, rkind, ractive in cur.fetchall():
                    row_kind[str(rsid)] = (str(rkind or ""), int(ractive or 0))
                cur.close()
            for rsid in residue:
                kind_active = row_kind.get(rsid)
                if kind_active is not None and kind_active[0] != "birth":
                    continue
                exists, cls_bp, char_id = _birth_save_row_state(rsid)
                alive_same = (exists and char_id is not None
                              and ledger.get(rsid) == _birth_identity(cls_bp, char_id))
                why = "revive_expired" if alive_same else "life_ended"
                cur = conn.execute(
                    "DELETE FROM birth_skin_ledger WHERE steam_id = ?", (rsid,))
                cur.close()
                ledger.pop(rsid, None)
                counts["ledger_cleared"] += 1
                logger.info("[BirthSkin] ledger cleared sid=%s reason=%s", rsid, why)

            # ---- B) capture: one recipe per LIFE, save row is the source.
            birthed_sids = [r["sid"] for r in rows if sk.is_valid_sid(r["sid"])]
            applied_active = set()
            if birthed_sids:
                cur = conn.execute(
                    "SELECT steam_id FROM skin_last_applied "
                    "WHERE active = 1 AND kind <> 'birth' AND steam_id IN (%s)"
                    % ",".join("?" for _ in birthed_sids), birthed_sids)
                applied_active = {str(r[0]) for r in cur.fetchall()}
                cur.close()
            for r in rows:
                sid = r["sid"]
                if not sk.is_valid_sid(sid):
                    continue
                if not (BIRTH_CAPTURE_ALL or r["deviation"] > BIRTH_MIN_DEVIATION):
                    counts["skipped_inrange"] += 1
                    continue
                identity = _birth_identity(r["cls_bp"], r["char_id"])
                if ledger.get(sid) == identity:
                    counts["skipped_captured"] += 1
                    continue
                if sid in applied_active:
                    counts["skipped_apply"] += 1
                    continue
                payload_json = sk.canonical_payload_json(r["payload"])
                digest = sk.compute_recipe_digest(sid, payload_json)
                cur = conn.execute(
                    _BIRTH_UPSERT_SQL,
                    (sid, r["cls_bp"], payload_json, now_iso, digest))
                wrote = cur.rowcount > 0
                cur.close()
                cur = conn.execute(
                    "INSERT OR REPLACE INTO birth_skin_ledger "
                    "(steam_id, identity, captured_utc) VALUES (?, ?, ?)",
                    (sid, identity, now_iso))
                cur.close()
                ledger[sid] = identity
                if wrote:
                    counts["captured"] += 1
                    logger.info("[BirthSkin] captured sid=%s class=%s "
                                "deviation=%.3f digest=%s",
                                sid, r["cls_bp"], r["deviation"], digest[:18])
                else:
                    counts["skipped_guard"] += 1
        finally:
            conn.close()
    except Exception as e:
        err = repr(e)
    logger.info("[BirthSkin] sweep ok=%s rows=%d prefiltered=%d birthed_parsed=%d "
                "parse_fail=%d captured=%d retired=%d ledger_cleared=%d "
                "skipped_inrange=%d skipped_captured=%d skipped_apply=%d "
                "skipped_guard=%d ms=%d err=%s",
                "1" if err is None else "0", stats.get("total", 0),
                stats.get("prefiltered", 0),
                stats.get("prefiltered", 0) - stats.get("parse_fail", 0),
                stats.get("parse_fail", 0), counts["captured"], counts["retired"],
                counts["ledger_cleared"], counts["skipped_inrange"],
                counts["skipped_captured"], counts["skipped_apply"],
                counts["skipped_guard"], int((time.monotonic() - t0) * 1000), err)


def _birth_sweep_done(task):
    _birth_bg_tasks.discard(task)
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        logger.warning("[BirthSkin] sweep task failed err=%r", exc)


def maybe_start_birth_sweep():
    """Called from server.dino_snapshot_loop's ~20s pass. Time-gated, one sweep
    in flight, never raises into the loop. First call logs the ARMED line (log
    ARMED + what it SEES, with a %.3f-bearing field as the build marker)."""
    global _birth_last_sweep_mono, _birth_sweep_task, _birth_armed_logged
    try:
        if not _birth_armed_logged:
            _birth_armed_logged = True
            logger.info("[BirthSkin] armed enabled=%s sweep_s=%d min_dev=%.3f "
                        "capture_all=%s persist_db_exists=%s db=%s",
                        "1" if BIRTH_CAPTURE_ENABLED else "0", BIRTH_SWEEP_SECONDS,
                        BIRTH_MIN_DEVIATION,
                        "1" if BIRTH_CAPTURE_ALL else "0",
                        "1" if os.path.exists(BIRTH_PERSIST_DB) else "0",
                        BIRTH_PERSIST_DB)
        if not BIRTH_CAPTURE_ENABLED:
            return
        now = time.monotonic()
        if now - _birth_last_sweep_mono < BIRTH_SWEEP_SECONDS:
            return
        if _birth_sweep_task is not None and not _birth_sweep_task.done():
            return
        _birth_last_sweep_mono = now
        task = asyncio.create_task(asyncio.to_thread(_birth_sweep_once))
        _birth_sweep_task = task
        _birth_bg_tasks.add(task)
        task.add_done_callback(_birth_sweep_done)
    except Exception as e:
        logger.warning("[BirthSkin] scheduler failed err=%r", e)

# =========================================================================
# HATCHLING ANCESTOR FEED (2026-08-06). Appended after this module's own
# definitions, so the two readers below REPLACE the ones above; the sweep
# resolves both by name at call time (verified: 1 def, no rebinds).
# LaIslaNublar keeps SAVED_DIR on game_ipc rather than as a module global,
# so the reader derives the Saved directory from BIRTH_PERSIST_DB - proven
# against this file's OWN helpers on a real feed: 6 rows / 6 nest-born /
# 0 parse_fail.
# =========================================================================
# -*- coding: ascii -*-
# Hatchling capture off the mod's OWN live feeds (2026-08-06).
#
# Isle build 24542870 sealed the player persistence db with SQLCipher, so
# _birth_read_save_rows could no longer OPEN it at all and every sweep on every
# owner died with DatabaseError("file is not a database"). The C++ publishes the
# same values per LIVE actor into skin_snapshots.json, and as of this wave that
# includes AncestorIds' length (the born-from-a-nest filter) plus a stable
# per-life key (which replaces the save record's Id as the identity).
#
# These defs are appended AFTER the exec of the live killfeed bytecode, so each
# one REPLACES the module-level name the sweep resolves at call time.
#
# Design note: we rebuild the CustomizedData shape the save row used to have and
# hand it to THIS FORK'S OWN _birth_payload / _birth_deviation. That way the
# recipe dialect stays exactly whatever this owner already shipped -- no fork's
# payload contract is re-implemented here, and no fork can drift from it.

import io as _anc_io
import os as _anc_os


def _anc_env_path(suffix):
    """Honour any <OWNER>_BIRTH_* override without knowing the owner's prefix."""
    try:
        for k, v in _anc_os.environ.items():
            if k.endswith(suffix) and str(v).strip():
                return str(v).strip()
    except Exception:
        pass
    return ""


def _anc_saved_dir():
    """The game's Saved directory, resolved LAZILY.

    Nothing here may run at import time: SAVED_DIR is a module-level global on
    most forks but only a local inside a function on at least one (IslaSegunda),
    where touching it at import crashed the bot into a restart loop. So look it
    up when it is actually needed, and fall back to deriving it from the fork's
    own persistence-db path (`...\\Saved\\PlayerData\\TheIslePersistence.db`)
    before giving up. Giving up is safe: the readers below then find no feed and
    return no rows, which is the same as an empty sweep.
    """
    g = globals()
    v = g.get("SAVED_DIR")
    if isinstance(v, str) and v.strip():
        return v
    db = g.get("BIRTH_PERSIST_DB")
    if isinstance(db, str) and db.strip():
        parent = _anc_os.path.dirname(_anc_os.path.dirname(db))
        if parent:
            return parent
    return ""


def _anc_feed_paths():
    """(snapshot path, players path) or ('','') if neither can be resolved."""
    snap = _anc_env_path("_BIRTH_SNAPSHOT_PATH")
    players = _anc_env_path("_BIRTH_PLAYERS_PATH")
    if snap and players:
        return snap, players
    base = _anc_saved_dir()
    if not base:
        return snap, players
    return (snap or _anc_os.path.join(base, "skin_snapshots.json"),
            players or _anc_os.path.join(base, "players.json"))

# THE CONTRACT. These seven keys are what our own C++ publishes per record, and
# the values are the game's own CustomizedData field names - the game's, not the
# fork's, so they are identical on every owner. Slots are built from THIS, never
# from the fork's map: a fork whose map happens to name a channel our snapshot
# does not carry would otherwise fail every single row (proven on Arkadia -
# `prefiltered=6 birthed_parsed=0 parse_fail=6` on real nest-born dinosaurs).
# The fork's own map is advisory on top: if it calls a field something else, the
# value is written under BOTH names.
_ANC_FALLBACK = {
    "body": "BodyColor",
    "markings": "MarkingsColor",
    "flank": "FlankColor",
    "underbelly": "UnderbellyColor",
    "detail1": "Detail1Color",
    "eyes": "EyesColor",
    "male_display": "MaleDisplayColor",
}


_ANC_SLOT_CACHE = {}


def _anc_build_slot_map():
    """snapshot/command key -> the save-row field name this fork expects.

    Resolved lazily and memoized, for the same reason as the paths: nothing may
    touch a module global at import time. _BIRTH_SLOT_MAP points one direction on
    some forks and the other on others, so detect it rather than assume - the
    save-side names are the game's PascalCase fields, the command-side names are
    lowercase.
    """
    cached = _ANC_SLOT_CACHE.get("map")
    if cached is not None:
        return cached
    out = {}
    try:
        for a, b in dict(globals().get("_BIRTH_SLOT_MAP") or {}).items():
            a, b = str(a), str(b)
            if a == a.lower() and b != b.lower():
                out[a] = b
            elif b == b.lower() and a != a.lower():
                out[b] = a
    except Exception:
        out = {}
    # ADVISORY ONLY - deliberately NOT merged with _ANC_FALLBACK. Anything here
    # that our snapshot cannot supply is an alias, never a requirement.
    _ANC_SLOT_CACHE["map"] = out
    return out


def _anc_read_feeds():
    """(snapshot, players) or (None, None). Never raises."""
    try:
        snap_path, players_path = _anc_feed_paths()
        if not snap_path or not players_path:
            return None, None
        with _anc_io.open(snap_path, "r", encoding="utf-8", errors="replace") as fh:
            snap = json.load(fh)
        with _anc_io.open(players_path, "r", encoding="utf-8", errors="replace") as fh:
            players = json.load(fh)
    except Exception:
        return None, None
    if not isinstance(snap, dict) or not isinstance(players, dict):
        return None, None
    return snap, players


def _anc_actor_index(players):
    """actor_name -> sid, from the live player feed."""
    out = {}
    try:
        items = players.items()
    except Exception:
        return out
    for sid, row in items:
        if isinstance(row, dict):
            actor = str(row.get("actor_name") or "").strip()
            if actor:
                out[actor] = str(sid)
    return out


def _anc_slots_from_record(rec):
    """{snapshot key: {r,g,b,a}} or None if any channel is missing/malformed.

    Driven by the SNAPSHOT's contract, not by the fork's map - see _ANC_FALLBACK.
    """
    slots = {}
    for cmd_key in _ANC_FALLBACK:
        v = rec.get(cmd_key)
        if not isinstance(v, (list, tuple)) or len(v) != 4:
            return None
        slots[cmd_key] = {"r": _birth_float(v[0]), "g": _birth_float(v[1]),
                          "b": _birth_float(v[2]), "a": _birth_float(v[3])}
    return slots


def _anc_customized_data(rec, slots):
    """The save row's CustomizedData shape, rebuilt from the live feed, so the
    fork's own _birth_payload can do the rest."""
    cd = {}
    fork = _anc_build_slot_map()
    for cmd_key, value in slots.items():
        cd[_ANC_FALLBACK[cmd_key]] = value
        alias = fork.get(cmd_key)
        if alias and alias not in cd:
            # This fork calls the same channel something else; write both, so a
            # renamed field is covered and a missing one can never fail a row.
            cd[alias] = value
    cd["bIsFemale"] = _birth_bool(rec.get("female"))
    cd["skinVariation"] = _birth_float(rec.get("variation"))
    try:
        cd["patternIndex"] = int(_birth_float(rec.get("pattern")))
    except (TypeError, ValueError):
        cd["patternIndex"] = 0
    # The save row's skinCode has no live equivalent; the recipe is fully
    # described by the slots plus variation and pattern.
    cd["skinCode"] = ""
    return cd


def _anc_local_deviation(slots):
    """Max distance outside [0,1] across every channel. Only used if the fork's
    own deviation helper cannot be fed - never let it drop a real capture."""
    worst = 0.0
    try:
        for slot in slots.values():
            for v in slot.values():
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    continue
                d = (v - 1.0) if v > 1.0 else ((0.0 - v) if v < 0.0 else 0.0)
                if d > worst:
                    worst = float(d)
    except Exception:
        return 0.0
    return worst


def _anc_payload_and_deviation(cd, cls_bp, my_slots):
    """(payload, deviation) using THIS fork's own builder, whatever shape it has.

    Forks differ in two ways that both silently cost every capture:
      * some return the payload alone, Arkadia's returns (payload, slots);
      * their _birth_deviation wants THE SLOTS THEIR OWN BUILDER MADE - Arkadia's
        are sequences, ours were mappings, and feeding it ours raised inside the
        sweep so every nest-born row counted as a parse failure.
    So take the pair from the fork when it offers one, and hand its own slots
    back to its own deviation helper. Fall back locally rather than lose a row.
    """
    payload = _birth_payload(cd, cls_bp)
    dev_slots = my_slots
    if isinstance(payload, tuple) and len(payload) == 2:
        payload, dev_slots = payload[0], payload[1]
    if not payload:
        return None, 0.0
    try:
        dev = _birth_deviation(dev_slots)
    except Exception:
        try:
            dev = _birth_deviation(my_slots)
        except Exception:
            dev = _anc_local_deviation(my_slots)
    if not isinstance(dev, (int, float)) or isinstance(dev, bool):
        dev = _anc_local_deviation(my_slots)
    return payload, float(dev)


def _birth_read_save_rows():
    """Birthed rows from the mod's own live feed, in EXACTLY the shape the db
    reader returned.

    born-from-a-nest filter: the C++ publishes AncestorIds' length as
    `ancestors`, and -1 means IT COULD NOT READ IT. Unknown is not zero -- an
    unreadable record is skipped, exactly as an unparseable save row was.
    """
    stats = {"total": 0, "prefiltered": 0, "parse_fail": 0}
    rows = []
    snap, players = _anc_read_feeds()
    if snap is None:
        stats["parse_fail"] += 1
        return rows, stats
    stats["total"] = len(snap)
    actor_to_sid = _anc_actor_index(players)
    # Same lazy rule as the paths: read the fork's cap if it has one, otherwise
    # use a sane bound rather than letting a NameError turn every row into a
    # parse failure.
    cap = globals().get("BIRTH_ROW_CAP")
    if not isinstance(cap, int) or cap <= 0:
        cap = 500
    for actor, rec in snap.items():
        try:
            if len(rows) >= cap:
                break
            if not isinstance(rec, dict):
                stats["parse_fail"] += 1
                continue
            anc = rec.get("ancestors")
            if not isinstance(anc, int) or isinstance(anc, bool) or anc <= 0:
                continue
            stats["prefiltered"] += 1
            sid = actor_to_sid.get(str(actor))
            if not sid:
                # A live pawn with no player row this instant; the two feeds are
                # written independently. Not a parse failure - the next sweep
                # sees it.
                continue
            cls_bp = _birth_class_bp(rec.get("class"))
            if not cls_bp:
                stats["parse_fail"] += 1
                continue
            slots = _anc_slots_from_record(rec)
            if not slots:
                stats["parse_fail"] += 1
                continue
            cd = _anc_customized_data(rec, slots)
            payload, deviation = _anc_payload_and_deviation(cd, cls_bp, slots)
            if not payload:
                # The fork's own builder refused this record; count it exactly as
                # the db reader did rather than storing an empty recipe.
                stats["parse_fail"] += 1
                continue
            rows.append({
                "sid": sid,
                "cls_bp": cls_bp,
                "char_id": str(rec.get("anc_key") or ""),
                "payload": payload,
                "deviation": deviation,
            })
        except Exception:
            stats["parse_fail"] += 1
    return rows, stats


def _birth_save_row_state(sid):
    """(exists, cls_bp, char_id) for ONE sid, from the same live feed.

    FAIL-CLOSED CONTRACT, and this is the whole reason this function is
    overridden rather than left alone. The old source was the game's save db,
    which held a row for every player whether online or not, so exists=False
    genuinely meant "that life is over" and the reconcile RETIRES the stored
    birth skin on it. The live feed only knows who is online RIGHT NOW, so
    answering False for an offline player would wipe the stored birth skin of
    everyone not logged in. Absent therefore returns (True, "", None) --
    "still there as far as we can tell, nothing to compare" -- which every
    caller already treats as skip-and-leave-alone.
    """
    try:
        snap, players = _anc_read_feeds()
        if snap is None:
            return True, "", None
        row = players.get(str(sid))
        if not isinstance(row, dict):
            return True, "", None
        actor = str(row.get("actor_name") or "").strip()
        rec = snap.get(actor) if actor else None
        if not isinstance(rec, dict):
            return True, "", None
        anc = rec.get("ancestors")
        if not isinstance(anc, int) or isinstance(anc, bool) or anc < 0:
            return True, "", None
        return True, _birth_class_bp(rec.get("class")), str(rec.get("anc_key") or "")
    except Exception:
        return True, "", None
