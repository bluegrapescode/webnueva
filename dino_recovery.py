"""Recovering a dino a player lost — the data layer behind /admin Recuperación.

WHY THIS EXISTS
---------------
The old Recovery tab read ``db.dino_records``, whose only writer is
``server._upsert_dino_record(user, ad, ...)`` fed from ``user["active_dino"]``.
That web-sim card stopped being created on 2026-07-15, when dinosaurs moved to
the real vault: on prod 2026-07-24 **0 of 62 users had an active_dino and
dino_records held 3 documents, all from 07-15**. So the tab listed nothing
current and ``POST /admin/recover-dino`` answered 404 for every real dino — the
owner hit exactly that 404 while trying to give a player his Carnotaurus back.
Worse, the grant inserted into ``db.inventory``, the pre-07-15 surface, not the
vault where dinos actually live now.

This module rebuilds the lane on sources that are still alive:

  * ``Saved/death_causes.log`` — the mod writes one JSON line per death
    (ts, sid, cause, dino, growth). That is the list of dinos a player lost.
  * ``db.dino_snapshots`` — a rolling last-seen-alive record per player, kept
    by server.dino_snapshot_loop() straight off players.json. It carries the
    things a death line does not: mutations, parent/elder mutations, elder
    stacks, prime/elder flags, skin code, diet and exact growth.
  * ``parked_dinos.skin_last_applied`` in the bot DB — the paint the player had
    on that species, so a recovered dino comes back looking like itself.

Everything here is READ-ONLY and pure: no mongo, no FastAPI, no writes. The
route layer in server.py owns the database and the vault INSERT. That split
keeps this file unit-testable off-box, but the routes are covered by their own
tests against the real endpoints — a pure layer passing proves nothing on its
own.

CRASH POLICY
------------
Every public function is total: bad JSON, a missing file, a truncated line, a
non-finite float or a wrong type yields an empty/defaulted result and never
raises. A recovery surface that 500s is worse than one that shows nothing.

BOUNDS
------
The death log is read as a bounded tail (``DEATH_LOG_TAIL_BYTES``) and capped at
``DEATH_LIMIT_MAX`` records, so the endpoint cost does not grow with uptime.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from datetime import datetime, timezone

# Tail window over Saved/death_causes.log. A death line is ~150 B, so 256 KB is
# on the order of 1700 deaths — far more than any admin scrolls, and the cost is
# flat no matter how long the server has been up.
DEATH_LOG_TAIL_BYTES = 256 * 1024
DEATH_LIMIT_MAX = 200
# The admin surface shows a player's last 15 LOST dinos — enough history to find
# the one being asked about without turning the panel into a log reader.
LOST_LIST_SIZE = 15
DEATH_LIMIT_DEFAULT = LOST_LIST_SIZE
# Park deaths are dropped from that list, so scan wider than we show.
DEATH_SCAN_SIZE = LOST_LIST_SIZE * 4

# The mod's own cause vocabulary (main.full.lua ClassifyDeathCause): fall,
# drown, dehydrate, starve, bleed, poison, unknown. Anything it grows later
# falls through to "unknown" here rather than reaching the UI as a raw token.
DEATH_CAUSES = ("fall", "drown", "dehydrate", "starve", "bleed", "poison", "unknown")

# A park kills the dino to store it, so parking writes a death line too. When a
# vault row (or a remembered park mark) for the same player+species sits within
# this window of a death, that death was a park, not a loss.
PARK_MATCH_WINDOW_S = 180

# How far back a capture may sit before the death it is asked to describe.
#
# ★This used to be 30 minutes, and it used to be the only knob — because there
# was only ever ONE snapshot document per player, overwritten every 20 s. The
# dead dino's state was therefore destroyed by its own owner's respawn, and a
# recovery clicked more than a few seconds after the death handed back a bare
# animal: no mutations, no prime, no elder. Measured over the last 200 deaths on
# prod: 27.5% bound, 36.0% were rejected because the player had already
# respawned as another species, 36.5% because the only surviving capture was
# taken AFTER the death. Median admin lag from death to click is 24 minutes.
#
# With SNAPSHOT_HISTORY_COLLECTION keeping the transitions, the pre-respawn
# capture still exists, so the window becomes a retention question, not a race.
# It must be at least as long as the history TTL or the TTL is dead weight.
SNAPSHOT_MAX_AGE_S = 7 * 24 * 60 * 60
# Kept under its old name because a caller may still want the strict reading;
# nothing in this module gates on it any more.
SNAPSHOT_STRICT_AGE_S = 30 * 60

SNAPSHOT_COLLECTION = "dino_snapshots"
# Append-only transitions of the above. One document per state change per
# player (the loop already computes that change signature), so the dino that
# died is still described after its owner respawns. Trimmed by a TTL index.
SNAPSHOT_HISTORY_COLLECTION = "dino_snapshot_history"
SNAPSHOT_HISTORY_TTL_S = 7 * 24 * 60 * 60
# Ceiling on how many history documents one recovery request will read. A busy
# player transitions on the order of a few hundred times a day; this keeps the
# per-request cost flat no matter how long they have been playing.
SNAPSHOT_HISTORY_SCAN = 600
RECOVERY_COLLECTION = "dino_recoveries"
PARK_MARK_COLLECTION = "dino_park_marks"

# Mirrors the mod's own slot strings so a recovered dino restores through the
# same contract park/redeem use.
EMPTY_MUTATIONS = "None|None|None|None"
EMPTY_ELDER_MUTATIONS = "None|None|None|None|None|None|None|None"

# Slot widths, from the mod: own 4, inherited-from-parents 4, elder 8. The elder
# string is INTERLEAVED 1A,1B,2A,2B,3A,3B,4A,4B — the apply loop walks
# `for i=1,4 do for _,suffix in {"A","B"}` and the capture indexes
# `eparts[(i-1)*2 + si]`. A blocked 1A,2A,3A,4A,1B,... ordering silently swaps
# six of the eight slots.
MUTATION_SLOTS = 4
ELDER_MUTATION_SLOTS = 8

# The ten Prime mission bits, as one integer. 2**10 - 1 = every mission done.
PRIME_CONDITIONS_ALL = 1023
# NumberOfPrimeCondition5 (migration) and 6 (patrol) are counters, not bits, and
# the mod clamps them on the way in.
PRIME_ROUTE_MIG_MAX = 2
PRIME_ROUTE_PAT_MAX = 4

# ★NULL is not 0. NULL = "we never recorded this dino's mission bits"; 0 =
# "we recorded them and none were done". Conflating the two is what lets a
# heal-the-legacy-rows policy either skip a row that needs it or overwrite a row
# that truthfully has nothing done. Every producer below returns ABSENT, never
# 0, when the source did not carry the field.
ABSENT = None


# ---------------------------------------------------------------------------
# small total helpers
# ---------------------------------------------------------------------------
def _num(value, default: float = 0.0) -> float:
    """float() that never raises and never returns inf/nan.

    The mod prints players.json floats with %f, so an engine inf/nan parses
    cleanly, survives every ``<= 0`` guard and then blows up downstream maths.
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def _text(value, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return default


def _epoch_s(value) -> int:
    """Accept seconds or milliseconds; 0 when unusable."""
    ts = _num(value, 0.0)
    if ts <= 0:
        return 0
    if ts > 10_000_000_000:  # milliseconds
        ts /= 1000.0
    return int(ts)


def _int_or_absent(value, lo: int, hi: int):
    """Clamped int, or ABSENT when the source did not carry a usable value.

    Returns ABSENT — not 0 — for None/''/garbage, so "never recorded" stays
    distinguishable from "recorded, none". A bool is rejected on purpose: the
    fields this guards are multi-bit states and a True silently reading as 1
    would be a one-bit answer to a ten-bit question.
    """
    if value is None or isinstance(value, bool):
        return ABSENT
    if isinstance(value, str) and not value.strip():
        return ABSENT
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return ABSENT
    if math.isnan(raw):
        return ABSENT
    # ★int(float('inf')) RAISES OverflowError — it does not clamp. Saturating
    # here rather than inside the try is deliberate: an engine +inf must land on
    # the CEILING, and letting int() throw would have collapsed it to the floor
    # in any except-branch that returned a default.
    if math.isinf(raw):
        return hi if raw > 0 else lo
    try:
        out = int(raw)
    except (OverflowError, ValueError):
        return ABSENT
    return max(lo, min(hi, out))


def normalize_slots(raw, width: int) -> str:
    """A mutation string with exactly `width` slots, blanks preserved as slots.

    The mod addresses these by POSITION, so a slot may never be dropped: losing
    an empty one shifts every mutation after it into the wrong socket. Missing
    slots are padded with 'None', extra slots are truncated, and whitespace-only
    entries become 'None'.
    """
    try:
        width = int(width)
    except (TypeError, ValueError):
        width = MUTATION_SLOTS
    width = max(1, width)
    parts = _text(raw).split("|") if _text(raw) else []
    out = []
    for i in range(width):
        part = parts[i].strip() if i < len(parts) else ""
        out.append(part if part else "None")
    return "|".join(out)


def elder_slots_look_corrupt(elder_mutations, elder_stacks) -> bool:
    """Elder mutation tokens with no entombs behind them = a broken capture.

    Not silently repaired: the caller logs it. A dino carrying elder slots it
    never earned is either a bad read or a grant that should not have happened,
    and both are worth seeing.
    """
    if count_mutations(elder_mutations) <= 0:
        return False
    return int(_num(elder_stacks)) <= 0


def prime_conditions_value(raw):
    """The ten Prime mission bits to store, or ABSENT when unknown.

    ★Takes the recorded value and NOTHING ELSE — deliberately no is_prime /
    is_elder / growth input, so there is no seam through which "we know it was
    Prime" could become "all ten missions were done". The mod already does that
    inflation itself when it receives no bits at all, and it does it for ANY
    elder row at ANY growth: an entomb offspring reads IsPrimeElder()=true as a
    juvenile with zero earned conditions and comes back with the whole Prime
    quest force-completed. Repeating that here would put it beyond the reach of
    any web-side fix. We send what we recorded, or we send nothing.
    """
    return _int_or_absent(raw, 0, PRIME_CONDITIONS_ALL)


def prime_route_values(mig_raw, pat_raw):
    """(migration, patrol) route counters clamped to the mod's own limits."""
    return (_int_or_absent(mig_raw, 0, PRIME_ROUTE_MIG_MAX),
            _int_or_absent(pat_raw, 0, PRIME_ROUTE_PAT_MAX))


def clean_species(raw) -> str:
    """'BP_Carnotaurus_C' -> 'Carnotaurus'. Mirrors game_telemetry._clean_species."""
    s = _text(raw).strip()
    if s.startswith("BP_"):
        s = s[3:]
    if s.endswith("_C"):
        s = s[:-2]
    return s


def to_class_name(raw) -> str:
    """'Carnotaurus' / 'carno-ish input' -> 'BP_Carnotaurus_C'. '' when unusable."""
    s = _text(raw).strip()
    if not s:
        return ""
    if s.startswith("BP_") and s.endswith("_C"):
        return s
    bare = clean_species(s)
    if not bare:
        return ""
    return "BP_%s_C" % bare


def clean_cause(raw) -> str:
    """The mod's death token, or 'unknown' for anything it did not emit.

    Keeps the UI mapping against ONE vocabulary: a cause the mod grows later
    reads as unknown instead of leaking a raw token into the panel.
    """
    cause = _text(raw).strip().lower()
    return cause if cause in DEATH_CAUSES else "unknown"


def death_key(steam_id, ts, dino_class) -> str:
    """Stable identity for one death, so it can be granted at most once."""
    return "%s:%d:%s" % (_text(steam_id), _epoch_s(ts), clean_species(dino_class))


# ---------------------------------------------------------------------------
# death log
# ---------------------------------------------------------------------------
def death_log_path(saved_dir: str) -> str:
    return os.path.join(_text(saved_dir), "death_causes.log")


def read_recent_deaths(saved_dir: str, steam_id=None, limit: int = DEATH_LIMIT_DEFAULT) -> list[dict]:
    """Newest-first deaths from the mod's own log, optionally for one player.

    Returns [] for a missing/unreadable log — never raises.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEATH_LIMIT_DEFAULT
    limit = max(1, min(DEATH_LIMIT_MAX, limit))
    want_sid = _text(steam_id).strip() or None

    path = death_log_path(saved_dir)
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > DEATH_LOG_TAIL_BYTES:
                fh.seek(size - DEATH_LOG_TAIL_BYTES)
                fh.readline()  # drop the partial first line
            blob = fh.read()
    except (OSError, ValueError):
        return []

    try:
        lines = blob.decode("utf-8", "replace").splitlines()
    except Exception:
        return []

    out: list[dict] = []
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw or raw[0] != "{":
            continue
        # Cheap reject before the parse. A SteamID64 is a distinctive 17-digit
        # token and no other field in a death line can collide with it, so this
        # turns ~1700 json.loads per call into the handful that can match.
        if want_sid and want_sid not in raw:
            continue
        try:
            rec = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict):
            continue
        sid = _text(rec.get("sid")).strip()
        if not sid or (want_sid and sid != want_sid):
            continue
        cls = to_class_name(rec.get("dino"))
        if not cls:
            continue
        ts = _epoch_s(rec.get("ts"))
        growth = _num(rec.get("growth"))
        if growth > 1.0:  # some writers emit percent
            growth = growth / 100.0
        growth = max(0.0, min(1.0, growth))
        out.append({
            "death_key": death_key(sid, ts, cls),
            "steam_id": sid,
            "ts": ts,
            "dino_class": cls,
            "species": clean_species(cls),
            "growth": growth,
            "growth_pct": int(round(growth * 100)),
            "cause": clean_cause(rec.get("cause")),
        })
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# last-seen-alive snapshot
# ---------------------------------------------------------------------------
def snapshot_from_player_row(steam_id, row, now_s=None) -> dict | None:
    """One players.json record -> the snapshot document we persist.

    None when the record is not a usable live dino.
    """
    if not isinstance(row, dict):
        return None
    sid = _text(steam_id).strip()
    if not sid:
        return None
    cls = to_class_name(row.get("dino"))
    if not cls:
        return None
    now_s = int(now_s if now_s is not None else time.time())
    growth = max(0.0, min(1.0, _num(row.get("growth"))))
    # ★THE NAME FLIP IS REAL AND LOAD-BEARING. The mod PUBLISHES the two route
    # counters as l_mig / l_pat in players.json, but PARSES them as
    # prime_route_mig / prime_route_pat off the restore command, and it does no
    # renaming of its own. Capture under the names the restore lane will need,
    # accepting either spelling here so a future publisher rename cannot quietly
    # zero them.
    mig, pat = prime_route_values(
        row.get("l_mig") if row.get("l_mig") is not None else row.get("prime_route_mig"),
        row.get("l_pat") if row.get("l_pat") is not None else row.get("prime_route_pat"))
    return {
        "steam_id": sid,
        "dino_class": cls,
        "species": clean_species(cls),
        "actor_name": _text(row.get("actor_name")),
        "growth": growth,
        "is_prime": bool(row.get("is_prime")),
        "is_elder": bool(row.get("is_elder")),
        # The ten Prime mission bits. Stored as ABSENT rather than 0 when
        # players.json does not carry them, so a capture from an older mod build
        # is never mistaken for "this dino had completed nothing".
        "prime_conditions": prime_conditions_value(row.get("prime_conditions")),
        "prime_route_mig": mig,
        "prime_route_pat": pat,
        "mutations": normalize_slots(
            _text(row.get("mutations"), EMPTY_MUTATIONS) or EMPTY_MUTATIONS, MUTATION_SLOTS),
        "parent_mutations": normalize_slots(
            _text(row.get("parent_mutations"), EMPTY_MUTATIONS) or EMPTY_MUTATIONS, MUTATION_SLOTS),
        "elder_mutations": normalize_slots(
            _text(row.get("elder_mutations"), EMPTY_ELDER_MUTATIONS) or EMPTY_ELDER_MUTATIONS,
            ELDER_MUTATION_SLOTS),
        "elder_stacks": int(_num(row.get("elder_stacks"))),
        "skin_code": _text(row.get("skin_code")),
        "diet_a": _num(row.get("diet_a")),
        "diet_b": _num(row.get("diet_b")),
        "diet_c": _num(row.get("diet_c")),
        "seen_at": now_s,
    }


# A snapshot is only trusted for SNAPSHOT_MAX_AGE_S after it was taken, so it
# has to be refreshed on a clock as well as on change. Without this, a
# FULLY-GROWN dino — growth pinned at 1.0, mutations settled, skin unchanged —
# produces an identical signature forever, stops being rewritten, ages out, and
# is then rejected at death: the most valuable dinos on the server would come
# back with no mutations at all. Bucketing keeps that to at most one write per
# player per bucket instead of one per tick.
SNAPSHOT_REFRESH_S = 300


def snapshot_signature(snap) -> str:
    """Change key for the snapshot loop.

    Growth is bucketed to 0.1% so a growing dino costs about one write per
    0.1% instead of one per tick, while every mutation / prime / skin change
    still writes immediately. The time bucket guarantees a refresh even when
    nothing about the dino changes — see SNAPSHOT_REFRESH_S.
    """
    if not isinstance(snap, dict):
        return ""
    seen = _epoch_s(snap.get("seen_at"))
    return "|".join((
        _text(snap.get("dino_class")),
        "%.3f" % _num(snap.get("growth")),
        _text(snap.get("mutations")),
        _text(snap.get("parent_mutations")),
        _text(snap.get("elder_mutations")),
        str(int(_num(snap.get("elder_stacks")))),
        "1" if snap.get("is_prime") else "0",
        "1" if snap.get("is_elder") else "0",
        # The mission bits move independently of everything above: a player can
        # complete a Prime objective without their growth, mutations or skin
        # changing at all. Leaving them out of the signature would hold the
        # history at the pre-objective state for up to SNAPSHOT_REFRESH_S and
        # lose the completion if they died inside that window. "absent" is its
        # own token so gaining a real 0 still counts as a transition.
        "absent" if snap.get("prime_conditions") is ABSENT else str(int(_num(snap.get("prime_conditions")))),
        "absent" if snap.get("prime_route_mig") is ABSENT else str(int(_num(snap.get("prime_route_mig")))),
        "absent" if snap.get("prime_route_pat") is ABSENT else str(int(_num(snap.get("prime_route_pat")))),
        _text(snap.get("skin_code")),
        str(seen // SNAPSHOT_REFRESH_S) if seen else "0",
    ))


# A tick can land a second or two past the death, so a capture stamped just
# after it still belongs to the dino that died.
SNAPSHOT_AFTER_DEATH_GRACE_S = 60


def snapshot_reject_reason(snapshot, death, max_age_s=None) -> str:
    """Why this capture cannot describe that death — '' when it can.

    Named reasons exist so the failure can be LOGGED. Before this, the binding
    silently degraded to "no snapshot" and the payload silently degraded to an
    empty dino: there was no line anywhere saying it had happened, and the
    granted line looked identical to a complete one. The owner's ticket was the
    only detector the bug had.
    """
    if not isinstance(snapshot, dict) or not snapshot:
        return "no_capture"
    if not isinstance(death, dict):
        return "no_death"
    if _text(snapshot.get("dino_class")) != _text(death.get("dino_class")):
        return "class_mismatch"
    seen = _epoch_s(snapshot.get("seen_at"))
    ts = _epoch_s(death.get("ts"))
    if not seen or not ts:
        return "no_timestamp"
    age = ts - seen
    if age < -SNAPSHOT_AFTER_DEATH_GRACE_S:
        return "after_death"
    limit = SNAPSHOT_MAX_AGE_S if max_age_s is None else int(max_age_s)
    if age > limit:
        return "too_old"
    return ""


def snapshot_matches_death(snapshot, death, max_age_s=None) -> bool:
    """Is this snapshot describing the dino that died?

    Same species, and seen alive within `max_age_s` before the death (a snapshot
    taken meaningfully AFTER the death belongs to whatever they spawned next).
    """
    return snapshot_reject_reason(snapshot, death, max_age_s) == ""


def snapshot_age_s(snapshot, death) -> int:
    """Seconds between the capture and the death; 0 when either is unusable.

    Reported to the admin as a LABEL — "captured 11 h before it died" — rather
    than used as a gate. The gate was the bug.
    """
    if not isinstance(snapshot, dict) or not isinstance(death, dict):
        return 0
    seen = _epoch_s(snapshot.get("seen_at"))
    ts = _epoch_s(death.get("ts"))
    if not seen or not ts:
        return 0
    return max(0, ts - seen)


def pick_history_snapshot(history, death, max_age_s=None):
    """The capture that honestly describes `death`, or None.

    THE RULE: take the last capture written at or before the death — whatever
    species it is — and accept it only if that species matches what died. That
    capture IS the last state the player's live dino was seen in, so if the
    species agrees it is the animal that died, and if it disagrees the player
    swapped after it and nothing we hold describes the dead one.

    ★Two things this is deliberately NOT:

    * NOT "the newest same-species capture within a grace window". The player
      respawns in seconds — 14 s in the incident this was written for — so a
      capture stamped just after the death is the NEW dino, and it is both
      newer and the same species. Preferring it hands back a fresh hatchling's
      empty state and calls it a full restore. Anything at or before the death
      always wins over anything after it.
    * NOT gated on age. A 30-minute window was the original bug. Age is
      reported as a label; the species agreement is the real evidence.

    `max_age_s` remains as an outer bound (default: the retention window) so a
    capture from beyond what we still keep cannot bind.
    """
    ts = _epoch_s((death or {}).get("ts"))
    if not ts:
        return None
    before, before_seen = None, -1
    after, after_seen = None, 1 << 62
    for snap in (history or ()):
        if not isinstance(snap, dict):
            continue
        seen = _epoch_s(snap.get("seen_at"))
        if not seen:
            continue
        if seen <= ts:
            if seen > before_seen:
                before, before_seen = snap, seen
        elif seen <= ts + SNAPSHOT_AFTER_DEATH_GRACE_S and seen < after_seen:
            after, after_seen = snap, seen
    # Only if nothing at all was captured before the death do we consider a tick
    # that landed just past it — the "the loop stamped it two seconds late" case.
    best = before if before is not None else after
    if best is None:
        return None
    return None if snapshot_reject_reason(best, death, max_age_s) else best


def pick_lkg_snapshot(history, death):
    """Last-known-good: an EARLIER capture of the same species, when nothing binds.

    Used only when `pick_history_snapshot` finds nothing at all. It carries the
    slow-moving things — mutations, prime, elder, skin, diet — from the last
    time we saw this player on this species, while identity (species, growth,
    when) still comes from the death itself. It is a best effort and MUST be
    labelled as one everywhere it surfaces: the mutations may be from an earlier
    animal of the same species, not the one that died.
    """
    cls = _text((death or {}).get("dino_class"))
    ts = _epoch_s((death or {}).get("ts"))
    if not cls or not ts:
        return None
    best, best_seen = None, -1
    for snap in (history or ()):
        if not isinstance(snap, dict):
            continue
        if _text(snap.get("dino_class")) != cls:
            continue
        seen = _epoch_s(snap.get("seen_at"))
        if seen <= 0 or seen > ts + SNAPSHOT_AFTER_DEATH_GRACE_S:
            continue
        # An empty capture teaches nothing; it would only launder "we know
        # nothing" into a labelled guess.
        if count_mutations(snap.get("mutations")) <= 0 and not snap.get("is_prime"):
            continue
        if seen > best_seen:
            best, best_seen = snap, seen
    return best


# ---------------------------------------------------------------------------
# park correlation — a park kills the dino, so it writes a death line too
# ---------------------------------------------------------------------------
def death_looks_parked(death, vault_rows, park_marks) -> bool:
    """True when this death was a park (the dino is safe in the vault), not a loss.

    Vault rows and park marks carry the same two fields and are checked the same
    way: a row still holding the dino, or a remembered mark for a row that has
    since been redeemed.
    """
    if not isinstance(death, dict):
        return False
    ts = _epoch_s(death.get("ts"))
    cls = _text(death.get("dino_class"))
    if not ts or not cls:
        return False
    for row in list(vault_rows or ()) + list(park_marks or ()):
        if not isinstance(row, dict) or _text(row.get("dino_class")) != cls:
            continue
        parked = _epoch_s(row.get("parked_at_ts"))
        if parked and abs(parked - ts) <= PARK_MATCH_WINDOW_S:
            return True
    return False


# ---------------------------------------------------------------------------
# read-only access to the bot DB (parked_dinos + skin_last_applied live there)
# ---------------------------------------------------------------------------
def _ro_query(bot_db_path: str, sql: str, params=()) -> list:
    """Run one read-only query, or return [] on ANY failure.

    The recovery panel must degrade to "nothing to show" rather than 500 when
    the bot DB is missing, locked or mid-migration.
    """
    if not _text(bot_db_path):
        return []
    conn = None
    try:
        uri = "file:%s?mode=ro" % _text(bot_db_path).replace("\\", "/")
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# the paint the player had on that species
# ---------------------------------------------------------------------------
def read_last_skin(bot_db_path: str, steam_id: str, dino_class: str) -> str:
    """The stored skin command for this player+species as a JSON string, or ''.

    Read-only against the bot DB. The redeem lane re-stamps class / steamid /
    actor_name itself and fails closed on a class mismatch, so only the colours
    are carried here.
    """
    sid = _text(steam_id).strip()
    cls = to_class_name(dino_class)
    if not sid or not cls:
        return ""
    rows = _ro_query(
        bot_db_path,
        "SELECT payload FROM skin_last_applied WHERE steam_id = ? AND dino_class = ?",
        (sid, cls))
    if not rows:
        return ""
    payload = _text(rows[0]["payload"]).strip()
    if not payload:
        return ""
    try:
        cmd = json.loads(payload)
    except (ValueError, TypeError):
        return ""
    if not isinstance(cmd, dict):
        return ""
    for key in ("actor_name", "steamid", "cmd_id"):
        cmd.pop(key, None)
    cmd["class"] = cls
    try:
        return json.dumps(cmd)
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# the vault row to write
# ---------------------------------------------------------------------------
def build_recovery_payload(dino_class, growth, snapshot=None, skin_data="",
                           is_prime=None, is_elder=None, mutations=None,
                           parent_mutations=None, elder_mutations=None,
                           elder_stacks=None, prime_conditions=None,
                           prime_route_mig=None, prime_route_pat=None) -> dict:
    """The ``pd`` dict for vault.save_parked describing the recovered dino.

    Vitals are stored as 0 ON PURPOSE. That is the mod's documented refill
    sentinel: on restore, ``health <= 0`` refills health/stamina/thirst from the
    live GetMax*, and ``hunger <= 0`` refills hunger. A dino that was lost to
    starvation or a fight must not come back at the values that killed it, and
    a stored juvenile ceiling replayed as an absolute would hand back a starving
    animal. Position is 0 as well: there is no park spot to return to.

    Explicit arguments win over the snapshot, so an admin can correct anything.
    """
    cls = to_class_name(dino_class)
    snap = snapshot if isinstance(snapshot, dict) else {}

    def pick(explicit, key, default):
        if explicit is not None:
            return explicit
        if key in snap and snap.get(key) is not None:
            return snap.get(key)
        return default

    g = _num(growth if growth is not None else snap.get("growth"))
    if g > 1.0:  # tolerate a percent
        g = g / 100.0
    g = max(0.0, min(1.0, g))

    muts = normalize_slots(
        _text(pick(mutations, "mutations", EMPTY_MUTATIONS)) or EMPTY_MUTATIONS, MUTATION_SLOTS)
    parents = normalize_slots(
        _text(pick(parent_mutations, "parent_mutations", EMPTY_MUTATIONS)) or EMPTY_MUTATIONS,
        MUTATION_SLOTS)
    elders = normalize_slots(
        _text(pick(elder_mutations, "elder_mutations", EMPTY_ELDER_MUTATIONS))
        or EMPTY_ELDER_MUTATIONS, ELDER_MUTATION_SLOTS)

    # ABSENT all the way through: an explicit None from the caller means "not
    # supplied", the snapshot may itself hold ABSENT, and only a real recorded
    # number reaches the row. The vault writer must leave the column NULL for
    # ABSENT so a legacy-heal policy can still tell the two apart.
    conditions = prime_conditions_value(
        prime_conditions if prime_conditions is not None else snap.get("prime_conditions"))
    mig, pat = prime_route_values(
        prime_route_mig if prime_route_mig is not None else snap.get("prime_route_mig"),
        prime_route_pat if prime_route_pat is not None else snap.get("prime_route_pat"))

    return {
        "dino": cls,
        "growth": g,
        "health": 0.0, "max_health": 0.0,
        "stamina": 0.0, "max_stamina": 0.0,
        "hunger": 0.0, "max_hunger": 0.0,
        "thirst": 0.0, "max_thirst": 0.0,
        "oxygen": 0.0, "max_oxygen": 0.0,
        "x": 0.0, "y": 0.0, "z": 0.0,
        "is_prime": bool(pick(is_prime, "is_prime", False)),
        "is_elder": bool(pick(is_elder, "is_elder", False)),
        "mutations": muts,
        "parent_mutations": parents,
        "elder_mutations": elders,
        "elder_stacks": int(_num(pick(elder_stacks, "elder_stacks", 0))),
        "prime_conditions": conditions,
        "prime_route_mig": mig,
        "prime_route_pat": pat,
        # The Evrima skin_code on a snapshot describes the LIVE paint; the
        # restore lane repaints from skin_data, so the code is left empty and
        # the command carries the colours.
        "skin_code": "",
        "skin_data": _text(skin_data),
        "diet_a": 0.0, "diet_b": 0.0, "diet_c": 0.0,
    }


def payload_is_bare(payload) -> bool:
    """True when this grant would hand back an EMPTY dino: species and growth only.

    A bare grant is exactly what the recovery lane used to do silently whenever
    the capture failed to bind — the player got the right animal at the right
    size with none of what made it his. It is still a legal thing to do
    deliberately, so this does not refuse it; the route uses it to ask first.
    """
    if not isinstance(payload, dict):
        return True
    if payload.get("is_prime") or payload.get("is_elder"):
        return False
    if int(_num(payload.get("elder_stacks"))) > 0:
        return False
    for key in ("mutations", "parent_mutations", "elder_mutations"):
        if count_mutations(payload.get(key)) > 0:
            return False
    return True


def payload_summary(payload) -> str:
    """One-line description of what a grant actually carries, for the log.

    ★The old granted line printed sid / class / growth / row / admin only, so a
    bare grant and a complete one were INDISTINGUISHABLE in the log for the
    whole life of the bug. Anything that can silently degrade must say what it
    degraded to.
    """
    if not isinstance(payload, dict):
        return "payload=invalid"
    conditions = payload.get("prime_conditions")
    return ("prime=%d elder=%d stacks=%d muts=%d parents=%d elders=%d "
            "conditions=%s mig=%s pat=%s skin=%d" % (
                1 if payload.get("is_prime") else 0,
                1 if payload.get("is_elder") else 0,
                int(_num(payload.get("elder_stacks"))),
                count_mutations(payload.get("mutations")),
                count_mutations(payload.get("parent_mutations")),
                count_mutations(payload.get("elder_mutations")),
                "absent" if conditions is ABSENT else str(conditions),
                "absent" if payload.get("prime_route_mig") is ABSENT else str(payload.get("prime_route_mig")),
                "absent" if payload.get("prime_route_pat") is ABSENT else str(payload.get("prime_route_pat")),
                1 if _text(payload.get("skin_data")).strip() else 0))


def read_parked_rows(bot_db_path: str, steam_id=None, since_id=None) -> list[dict]:
    """Vault rows as (id, steam_id, dino_class, parked_at_ts) — ONE shape.

    Serves both readers: `steam_id` for one player's rows (the recovery panel),
    `since_id` for the park-mark tick, which only ever needs rows it has not
    seen. `parked_dinos.id` is AUTOINCREMENT and never reused, so `id > since_id`
    is an exact "what is new" and keeps the steady-state tick at zero rows
    instead of scanning the whole table.
    """
    where, params = [], []
    if steam_id is not None:
        where.append("steam_id = ?")
        params.append(str(steam_id))
    if since_id is not None:
        where.append("id > ?")
        params.append(int(since_id))
    sql = "SELECT id, steam_id, dino_class, parked_at FROM parked_dinos"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id"

    out: list[dict] = []
    for row in _ro_query(bot_db_path, sql, tuple(params)):
        try:
            out.append({
                "id": int(row["id"]),
                "steam_id": _text(row["steam_id"]),
                "dino_class": _text(row["dino_class"]),
                "parked_at_ts": parse_iso_ts(row["parked_at"]),
            })
        except (TypeError, ValueError, KeyError, IndexError):
            continue
    return out


# ---------------------------------------------------------------------------
# the twin gate — a recovery grant must ask the vault first
# ---------------------------------------------------------------------------
# The matcher is the framework's banked-twin rule (vaultrestoregate, born on
# Arkadia's restore lane 2026-08-21). A grant is a spawn-from-evidence exactly
# like a restore, and both real leaks here were grants of a dinosaur the vault
# already held: the auto-rescue paid ONE corrupt save twice 15 minutes apart
# (rows 14013+14029), and the panel granted a Rex whose two earlier grants
# were still banked (row 15251 beside 14649/14650) — one walking animal plus
# cashable spares, flagged by vault_world_check until a human looked.
try:
    import vaultrestoregate as _twin_gate
except ImportError:  # deploy-ordering guard: gate silently OFF until the file lands
    _twin_gate = None


def read_twin_rows(bot_db_path: str, steam_id) -> list[dict]:
    """One player's vault rows with the identity fields the twin gate compares.

    Read-only and total like every _ro_query caller: an unreadable bot DB
    yields [] — the gate then finds no twin and the grant proceeds (fail OPEN),
    because a database hiccup must never block an honest recovery.
    """
    sid = _text(steam_id).strip()
    if not sid:
        return []
    rows = _ro_query(
        bot_db_path,
        "SELECT id, steam_id, dino_class, growth, mutations, parent_mutations,"
        " elder_stacks, skin_code FROM parked_dinos WHERE steam_id = ?"
        " ORDER BY id",
        (sid,))
    out: list[dict] = []
    for row in rows:
        try:
            out.append({key: row[key] for key in row.keys()})
        except (TypeError, ValueError, KeyError, IndexError):
            continue
    return out


def find_grant_twin(steam_id, payload, rows, growth_tolerance=0.02):
    """The banked row already holding this grant's dinosaur, or None.

    Pure seam over vaultrestoregate.find_banked_twin so the refusal rule is
    testable without the web app. The payload never carries a wire skin_code,
    so a dinosaur with no real mutation anywhere stays ungated by design (the
    framework's plain-row rule needs an equal non-empty skin on both sides).
    Any internal error returns None — fail OPEN, the caller logs it.
    """
    if _twin_gate is None or not isinstance(payload, dict):
        return None
    try:
        snapshot = {
            "steam_id": _text(steam_id).strip(),
            "dino_class": payload.get("dino"),
            "growth": payload.get("growth"),
            "mutations": payload.get("mutations"),
            "parent_mutations": payload.get("parent_mutations"),
            "elder_stacks": payload.get("elder_stacks"),
            "skin_code": "",
        }
        return _twin_gate.find_banked_twin(
            snapshot, rows, growth_tolerance=growth_tolerance)
    except Exception:
        return None


def grant_twin_receipt(verdict) -> str:
    """Log line for a refused grant, or '' when the module is absent."""
    if _twin_gate is None:
        return ""
    try:
        return _twin_gate.receipt_text(verdict)
    except Exception:
        return "vault_holds_row reason=receipt_failed"


def parse_iso_ts(value) -> int:
    """ISO-8601 (with or without Z) -> epoch seconds; 0 when unusable."""
    text = _text(value).strip()
    if not text:
        return 0
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
    except (ValueError, TypeError):
        return 0
    if dt.tzinfo is None:
        # TIMEZONE-CRITICAL: every writer stamps datetime.now(timezone.utc), but
        # parked_at is untyped TEXT in a DB with several writers. A naive stamp
        # is UTC — reading it as box-local would shift every park comparison by
        # the box offset (7h here), so a park stops being recognised and its
        # dino gets offered as "lost" and handed out a second time.
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return int(dt.timestamp())
    except (OSError, OverflowError, ValueError):
        return 0


def build_lost_list(deaths, vault_rows=None, park_marks=None, recovered_keys=None,
                    snapshot=None, size: int = LOST_LIST_SIZE,
                    ledger_start_ts: int = 0, history=None, allow_lkg: bool = True) -> list[dict]:
    """The player's last N LOST dinos, newest first — what the admin picks from.

    ``deaths`` should already be newest-first for ONE player. Deaths that were
    really parks (the dino went to the vault, it was never lost) are dropped, so
    the list means what it says. Deaths already granted stay in the list but are
    flagged ``recovered`` so the same dino can never be handed out twice — the
    unique index on the recovery record is the real guarantee, this is the UI
    telling the truth about it.
    """
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = LOST_LIST_SIZE
    size = max(1, min(DEATH_LIMIT_MAX, size))
    recovered_keys = set(recovered_keys or ())
    # `history` is the append-only capture log; `snapshot` is the single rolling
    # document. History is authoritative when present and the rolling document
    # is folded in as one more candidate, so this still behaves correctly on a
    # backend that has not written any history yet.
    candidates = [s for s in (history or ()) if isinstance(s, dict)]
    if isinstance(snapshot, dict) and snapshot:
        candidates.append(snapshot)
    # ★Each death binds its OWN capture. The old code picked at most one death
    # for the single rolling document, so every other death in the list was
    # shown — and granted — as bare, whatever we actually knew about it.
    out: list[dict] = []
    for death in (deaths or []):
        if not isinstance(death, dict):
            continue
        if death_looks_parked(death, vault_rows, park_marks):
            continue  # parked, not lost
        key = _text(death.get("death_key"))
        snap = pick_history_snapshot(candidates, death)
        detail = "full" if snap else ""
        if snap is None and allow_lkg:
            snap = pick_lkg_snapshot(candidates, death)
            detail = "lkg" if snap else ""
        item = dict(death)
        item["recovered"] = key in recovered_keys
        # A park is only distinguishable from a loss once we were recording
        # parks. Before that, a dino parked and then redeemed left nothing
        # behind, so its death line looks exactly like a real loss — handing it
        # back would be a duplicate. Flag it instead of hiding it: the admin can
        # still recover it, but knowingly.
        item["park_unverified"] = bool(
            ledger_start_ts and _epoch_s(death.get("ts")) < ledger_start_ts)
        if isinstance(snap, dict):
            item["mutations"] = _text(snap.get("mutations"), EMPTY_MUTATIONS)
            item["mutations_count"] = count_mutations(item["mutations"])
            item["parent_mutations_count"] = count_mutations(snap.get("parent_mutations"))
            item["elder_mutations_count"] = count_mutations(snap.get("elder_mutations"))
            item["is_prime"] = bool(snap.get("is_prime"))
            item["is_elder"] = bool(snap.get("is_elder"))
            item["elder_stacks"] = int(_num(snap.get("elder_stacks")))
            conditions = snap.get("prime_conditions")
            item["prime_conditions"] = conditions
            item["prime_missions_done"] = (
                bin(int(conditions)).count("1") if conditions is not ABSENT else None)
            # How long before the death this capture was taken. A LABEL for the
            # admin, never a gate — gating on it is what broke this lane.
            item["snapshot_age_s"] = snapshot_age_s(snap, death)
            # The snapshot's growth is the precise live value; the death line
            # rounds to 3 decimals. Only trust it on an exact bind: an LKG
            # capture describes a DIFFERENT animal, whose size means nothing
            # here, and overwriting the death's own growth with it would hand
            # back the wrong-sized dino.
            snap_growth = _num(snap.get("growth"))
            if snap_growth > 0 and detail == "full":
                item["growth"] = max(0.0, min(1.0, snap_growth))
                item["growth_pct"] = int(round(item["growth"] * 100))
            item["detail"] = detail or "full"
        else:
            item["mutations"] = ""
            item["mutations_count"] = 0
            item["parent_mutations_count"] = 0
            item["elder_mutations_count"] = 0
            item["is_prime"] = False
            item["is_elder"] = False
            item["elder_stacks"] = 0
            item["prime_conditions"] = ABSENT
            item["prime_missions_done"] = None
            item["snapshot_age_s"] = 0
            # No capture: species + growth + when are known, the rest is not.
            # Granting this hands back a bare dino, and the route now says so
            # rather than doing it quietly.
            item["detail"] = "partial"
        out.append(item)
        if len(out) >= size:
            break
    return out


def count_mutations(mutations) -> int:
    """How many real mutation slots are filled ('None' is an empty slot)."""
    out = 0
    for part in _text(mutations).split("|"):
        part = part.strip()
        if part and part.lower() != "none":
            out += 1
    return out
