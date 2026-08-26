"""Automatic rescue when the GAME's save-key check eats a dino at join.

WHY THIS EXISTS
---------------
Evrima guards every player save with a key pair (CurrentKey/BackupKey) and
refuses the save when the joining client's key does not match:

    LogTheIsleJoinData: Warning: Save file is corrupt for <sid>.
        NewKey=1.000000 CurrentKey=0.000000 BackupKey=0.000000

The player is then forced to RequestRespawn loadSaved=0 — their dino is gone.
Measured on this box 2026-08-13/14: 53 distinct players in one 2-hour boot and
95 in the boot before it, in two shapes:

  * ``NewKey=1 CurrentKey=0 BackupKey=0`` — the server-side key columns were
    zeroed, en masse, around the engine AV crashes (the boot ending
    2026.08.14-03.31.27 died in LaunchWindowsStartup.ExceptionHandler). Every
    affected player hits "corrupt" whenever they next join, minutes or hours
    later.
  * ``NewKey=0 CurrentKey=<random>`` — the game's own safelog/relog key
    handshake losing the client half (observed: safelog 03:44:10Z, rejoin
    03:45:02Z, save refused). Nothing server-side can prevent this one.

We cannot repair the game's key store (TheIslePersistence.db is SQLCipher).
What we CAN do is what an admin already does by hand in /admin Recuperación:
hand the dino back from our own last-seen-alive capture. This module is the
pure decision layer for doing that AUTOMATICALLY, the moment the corrupt-join
line appears — the vault write itself rides the exact recovery lane admins
use (``server._grant_recovered_dino``), including its claim CAS, its park-cap
handling and its action-log receipt.

THE DANGEROUS DIRECTION
-----------------------
Minting a vault row for a dino that is not actually LOST is a free copy, so
eligibility is closed by EVIDENCE, not by clock:

  * the SERVER's own key pair must both be ZERO (``RESCUE_LOSS_SHAPE``) — see
    "A CORRUPT JOIN IS NOT A LOST DINO" below — anything else -> refuse;
  * no capture, or a capture older than ``RESCUE_SNAPSHOT_MAX_AGE_S``, or a
    capture taken AFTER the corrupt join (that is the NEXT life) -> refuse;
  * any death in the mod's ``death_causes.log`` between capture and corrupt
    join (organic or park-kill) -> refuse;
  * any game-log "Killed the following player" line for that sid in the same
    window (independent oracle for deaths the classifier missed) -> refuse;
  * any park mark at/after the capture (the vault already owns that animal)
    -> refuse;
  * more than ``RESCUE_DAILY_CAP`` auto-grants per player per day -> refuse
    (staff can still hand-grant from the panel).

A CORRUPT JOIN IS NOT A LOST DINO (2026-08-15, player-reported duplication)
---------------------------------------------------------------------------
The two shapes above look identical in the log line and mean OPPOSITE things:

  * ``CurrentKey=0 BackupKey=0`` — the server holds NO key. Nothing can ever
    load that dino again. It is LOST, and the rescue is the whole point.
  * ``NewKey=0 CurrentKey=<n>`` — the CLIENT arrived without its half of the
    handshake (the safelog->relog race). The server's save is INTACT and loads
    on the player's very next clean join. Nothing was lost.

The lane originally granted on both, because it read the log LINE as the proof
instead of the key NUMBERS in it. A player who redeems a dino and then relogs
fast enough to provoke the race therefore ended holding the animal in game AND
a fresh copy of it in the vault — reported 2026-08-15 ("redeem, refresh fast,
and it is in game and in the vault"), and measured twice on the live box:
vault row 12060 (Prime Kentrosaurus 0.902, sid ...29842, granted 2 minutes
after that player's own redeem of a Kentrosaurus) and vault row 12238 (Prime
Dilophosaurus 0.736, sid ...24599). 55 of the 57 grants to that date were the
genuine zeroed-key shape and were correct.

★ THE LESSON, which is not about keys: a rescue must be authorised by proof
that the thing is GONE, never by the error message that announced it. An error
means "this attempt failed", and "an attempt failed" and "the property was
destroyed" are two different claims.

Residual risk, accepted and documented: a death in the final instants before
a server crash can be missing from BOTH oracles; such a player would be
resurrected. That window is the crash itself, which the engine-AV clamp wave
is closing.

Everything here is pure and total: no mongo, no files, no clock reads — the
loop in server.py owns io, and bad input yields a refusal, never a raise.
"""
from __future__ import annotations

import calendar
import os
import re

import dino_recovery

# A capture can be hours old (an idle adult's signature stops changing and the
# refresh clock is 300 s buckets) but a MUCH older one probably describes a
# life this corrupt join is not about. 72 h also caps how far a wiped key row
# can reach back.
RESCUE_SNAPSHOT_MAX_AGE_S = 72 * 60 * 60
# A capture stamped just after the corrupt line is still the SAME life (clock
# jitter between the box clock and the log stamp), anything later is the next
# life's fresh spawn.
RESCUE_SNAPSHOT_FUTURE_GRACE_S = 5
# Death/park evidence slightly BEFORE the capture still refuses: the capture
# loop runs on 20 s ticks, so a death and a stale capture can be re-ordered by
# one tick.
RESCUE_EVIDENCE_GRACE_S = 120
# Auto-grants per player per rolling day. The second corrupt join in a day is
# already unusual; the third is somebody probing the lane.
RESCUE_DAILY_CAP = 2
RESCUE_DAILY_WINDOW_S = 24 * 60 * 60

RESCUE_SOURCE = "save_corrupt_auto"
RESCUE_ACTOR = "AutoRescate"

#: The ONE key shape that proves the dino is unrecoverable: the SERVER's own
#: pair is zero, so no later join can load it. Every other shape leaves a
#: loadable save on the server and must never be paid out — see the module
#: header, "A CORRUPT JOIN IS NOT A LOST DINO".
RESCUE_LOSS_SHAPE = "server_keys_zeroed"

#: The three key fields decide() requires to be present AND finite before it
#: will read a shape off them.
RESCUE_KEY_FIELDS = ("new_key", "current_key", "backup_key")

# [2026.08.14-03.32.53:600][567]LogTheIsleJoinData: Warning: Save file is
#   corrupt for 76561198670165087. NewKey=1.000000 CurrentKey=0.000000 ...
_CORRUPT_RE = re.compile(
    r"^\[(?P<stamp>[0-9.]+-[0-9.]+):[0-9]+\]\[\s*\d+\]"
    r"LogTheIsleJoinData: Warning: Save file is corrupt for (?P<sid>\d{15,20})\."
    r"\s*NewKey=(?P<new>[0-9.]+)\s+CurrentKey=(?P<cur>[0-9.]+)\s+BackupKey=(?P<bak>[0-9.]+)")

# [2026.08.14-03.31.24:044][195]LogTheIsleKillData: ... - Killed the following
#   player: <name>, [<sid>] ...   (victim sid is the LAST bracketed id)
_VICTIM_RE = re.compile(
    r"^\[(?P<stamp>[0-9.]+-[0-9.]+):[0-9]+\]\[\s*\d+\]"
    r"LogTheIsleKillData:.*Killed\s+the\s+following\s+player:.*?"
    r"\[(?P<sid>\d{15,20})\]")

_STAMP_RE = re.compile(
    r"^(\d{4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2})$")


def parse_log_stamp(stamp: str) -> int:
    """``2026.08.14-03.32.53`` (UTC, the game log's clock) -> epoch seconds.

    0 for anything malformed — a caller treating 0 as "unknown" refuses, which
    is the safe direction.
    """
    m = _STAMP_RE.match(str(stamp or ""))
    if not m:
        return 0
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    try:
        return calendar.timegm((y, mo, d, h, mi, s, 0, 0, 0))
    except (ValueError, OverflowError):
        return 0


def parse_corrupt_line(line: str) -> dict | None:
    """One game-log line -> the corrupt-join event, or None.

    ``ts`` 0 (unparseable stamp) is returned rather than dropped so the caller
    can count it; decide() refuses ts=0.
    """
    m = _CORRUPT_RE.match(str(line or ""))
    if not m:
        return None
    return {
        "sid": m.group("sid"),
        "ts": parse_log_stamp(m.group("stamp")),
        "new_key": _f(m.group("new")),
        "current_key": _f(m.group("cur")),
        "backup_key": _f(m.group("bak")),
    }


def parse_victim_line(line: str) -> dict | None:
    """One game-log kill line -> {sid, ts} for the VICTIM, or None."""
    m = _VICTIM_RE.match(str(line or ""))
    if not m:
        return None
    return {"sid": m.group("sid"), "ts": parse_log_stamp(m.group("stamp"))}


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def rescue_key(sid: str, ts: int) -> str:
    """Stable identity for one corrupt-join event.

    Rides dino_recoveries' unique death_key index, so one event can be granted
    at most once no matter how often the loop replays the log window.
    """
    return "savecorrupt:%s:%d" % (str(sid or ""), int(ts or 0))


def key_shape(event) -> str:
    """'server_keys_zeroed' / 'client_key_lost' / 'other' — receipt vocabulary.

    The shapes matter operationally: a burst of server_keys_zeroed follows a
    crash; client_key_lost is the game's own relog race and arrives as singles.
    """
    if not isinstance(event, dict):
        return "other"
    cur, bak, new = (_f(event.get("current_key")), _f(event.get("backup_key")),
                     _f(event.get("new_key")))
    if cur == 0.0 and bak == 0.0:
        return "server_keys_zeroed"
    if new == 0.0 and (cur > 0.0 or bak > 0.0):
        return "client_key_lost"
    return "other"


def keys_readable(event) -> bool:
    """True only when the event carries all three key numbers, finite.

    ★ Why this is not paranoia: ``key_shape`` reads an ABSENT key as 0.0
    through ``_f``, and zero/zero is precisely the shape that AUTHORISES a
    grant — so an event that never carried the fields at all would be read as
    the strongest possible proof of loss. The parser cannot produce such an
    event (its regex requires all three), but ``decide`` is a public pure
    function and a future caller, a replayed journal line or a hand-built test
    fixture can. Gate on the numbers being THERE, never on their absence.
    """
    if not isinstance(event, dict):
        return False
    for name in RESCUE_KEY_FIELDS:
        if name not in event:
            return False
        value = event.get(name)
        if isinstance(value, bool) or value is None:
            return False
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        # NaN != NaN, and an infinity compares > 0.0 without being a key.
        if number != number or number in (float("inf"), float("-inf")):
            return False
    return True


def pick_rescue_snapshot(candidates, corrupt_ts: int):
    """Newest capture taken AT OR BEFORE the corrupt join = the lost life.

    The rolling snapshot alone is NOT safe here: by the time a catch-up pass
    processes an old corrupt line, the player has respawned and the rolling
    document already describes the NEW dino. Candidates therefore carry both
    the rolling doc and the append-only history, and anything stamped after
    the corrupt join (+ grace) is ignored.
    """
    corrupt_ts = int(corrupt_ts or 0)
    if corrupt_ts <= 0:
        return None
    best = None
    for snap in candidates or ():
        if not isinstance(snap, dict):
            continue
        try:
            seen = int(snap.get("seen_at") or 0)
        except (TypeError, ValueError):
            seen = 0
        if seen <= 0 or seen > corrupt_ts + RESCUE_SNAPSHOT_FUTURE_GRACE_S:
            continue
        if not dino_recovery.to_class_name(snap.get("dino_class")):
            continue
        if best is None or seen > int(best.get("seen_at") or 0):
            best = snap
    return best


def decide(event, snapshot, deaths, park_marks, victim_kills,
           auto_grant_count_24h) -> tuple[bool, str]:
    """The whole eligibility ruling for one corrupt-join event.

    Pure: every argument is data the caller already read. Returns
    (True, "ok") or (False, <machine reason>); unknown/malformed input always
    refuses.
    """
    if not isinstance(event, dict):
        return False, "bad_event"
    sid = str(event.get("sid") or "")
    ts = int(event.get("ts") or 0)
    if not sid or ts <= 0:
        return False, "bad_event"

    # IS IT ACTUALLY GONE? — asked FIRST, ahead of every other gate, because
    # every gate below is about whether a LOST dino may be paid back, and they
    # are all the wrong question when nothing was lost. Only a server-side key
    # pair of 0/0 proves the save can never load again; the safelog->relog race
    # (NewKey=0 with the server's keys intact) leaves the animal exactly where
    # it was and hands it back on the next clean join. Header: "A CORRUPT JOIN
    # IS NOT A LOST DINO".
    if not keys_readable(event):
        return False, "keys_unreadable"
    if key_shape(event) != RESCUE_LOSS_SHAPE:
        return False, "server_save_intact"

    try:
        if int(auto_grant_count_24h or 0) >= RESCUE_DAILY_CAP:
            return False, "daily_cap"
    except (TypeError, ValueError):
        return False, "daily_cap"

    if not isinstance(snapshot, dict) or not snapshot:
        return False, "no_capture"
    try:
        seen = int(snapshot.get("seen_at") or 0)
    except (TypeError, ValueError):
        seen = 0
    if seen <= 0:
        return False, "capture_unstamped"
    if seen > ts + RESCUE_SNAPSHOT_FUTURE_GRACE_S:
        return False, "capture_after_event"
    if ts - seen > RESCUE_SNAPSHOT_MAX_AGE_S:
        return False, "capture_too_old"
    if not dino_recovery.to_class_name(snapshot.get("dino_class")):
        return False, "capture_no_class"

    window_lo = seen - RESCUE_EVIDENCE_GRACE_S
    for d in deaths or ():
        if not isinstance(d, dict) or str(d.get("steam_id") or "") != sid:
            continue
        dts = int(d.get("ts") or 0)
        if window_lo <= dts <= ts:
            return False, "died_%s" % (str(d.get("cause") or "unknown") or "unknown")

    for k in victim_kills or ():
        if not isinstance(k, dict) or str(k.get("sid") or "") != sid:
            continue
        kts = int(k.get("ts") or 0)
        if window_lo <= kts <= ts:
            return False, "killed_in_log"

    for mark in park_marks or ():
        if not isinstance(mark, dict):
            continue
        try:
            pts = int(mark.get("parked_at_ts") or 0)
        except (TypeError, ValueError):
            continue
        if pts >= window_lo:
            return False, "parked_recently"

    return True, "ok"


def read_new_lines(path: str, pos: int, cap: int) -> tuple[list[str], int, bool]:
    """Complete new lines since pos -> (lines, new_pos, rotated).

    Bounded by cap; a partial trailing line stays unread
    until it is complete. A shrunken file is the game's boot rotation: start
    over at 0 so the new boot's join burst is seen.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], pos, False
    rotated = size < pos
    if rotated:
        pos = 0
    if size <= pos:
        return [], pos, rotated
    take = min(size - pos, int(cap))
    try:
        with open(path, "rb") as fh:
            fh.seek(pos)
            blob = fh.read(take)
    except OSError:
        return [], pos, rotated
    cut = blob.rfind(b"\n")
    if cut < 0:
        return [], pos, rotated
    return blob[:cut].decode("utf-8", "replace").splitlines(), pos + cut + 1, rotated
