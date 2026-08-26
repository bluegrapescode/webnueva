# -*- coding: utf-8 -*-
"""A dinosaur-loss RESTORE must ask the vault first: a banked dinosaur is not a lost one.

Born on Arkadia 2026-08-21 from two FleetView alerts that turned out to be one
lane ("something keeps failing" + "one dinosaur is counted twice").

=============================================================================
THE DEFECT, EXACTLY
=============================================================================
The safelog / native-loss restore lane keeps a logout snapshot of every
player's dinosaur and, when the game later reports that player's save as
NOT FOUND, spawns the snapshot back. Its only anti-park guard was the growth
shrink a park kill leaves behind (``growth <= 0.05``). Measured over ten days
of real Arkadia history (1,051 restores): **19 restores re-spawned a dinosaur
whose vault row was standing at the time and is STILL standing today** - the
player walked the dinosaur AND could cash the row in for a second copy.
Twelve of the nineteen were taken 1-5 seconds AFTER the park, on the SAME
pawn the park had just killed: the park itself triggers the restore. The
other seven were the escaped twin logging out later (growth drifted up by
0.002-0.027 in the meantime, which is why the sweep's exact matcher missed
them).

=============================================================================
THE RULE
=============================================================================
Before a restore spawns, look at the SAME PLAYER's stored rows. The snapshot
IS a banked dinosaur when

  * ``same_actor``   - the snapshot's pawn name equals a stored row's pawn
                       name (the park just killed that pawn); or
  * ``same_lineage`` - same species, the four base mutations equal, the four
                       parent mutations equal (case-insensitive, blank/None
                       folded), the snapshot's growth is not materially LOWER
                       than the stored growth (a banked dinosaur cannot have
                       shrunk - only grown - so a younger look-alike is a
                       different animal), and its elder stacks are not lower.
                       A row with NO real mutation anywhere (a plain dinosaur)
                       is weak evidence, so it additionally needs an equal,
                       non-empty skin code (``same_lineage_skin``).

Identity flags (prime / elder) are deliberately NOT compared: they read
all-false for seconds after every actor change (the prime export-hold law).
The skin code is NOT required for strong rows: a live twin can be re-skinned
from the skin site, and that must not reopen the door.

=============================================================================
THE DIRECTIONS, AND WHICH WAY EACH FAILURE FALLS
=============================================================================
* A false REFUSAL costs one restore of a dinosaur the player has a look-alike
  of in storage; the backup keeps its full snapshot and the receipt names the
  row, so staff can still hand it back by hand.
* A false ALLOW mints a second copy - the exploitable direction. So the
  lineage test is strict on what it needs and generous on what it ignores.
* Malformed rows are skipped, never matched; a malformed snapshot matches
  nothing. An internal error in the finder returns ``None`` (allow) and the
  host logs it - a database hiccup must not freeze every restore on the box,
  and a player cannot cause one.

The module is PURE: dicts in, a verdict out, no I/O, no clock, no imports
beyond ``math`` - so an owner bot can inline the block between the two CORE
markers VERBATIM (a kit gate byte-compares the inlined copy against this
file after stripping the owner prefix).
"""
from __future__ import annotations

import math

__all__ = [
    "DEFAULT_GROWTH_TOLERANCE",
    "FAMILIES",
    "Verdict",
    "empty_snapshot_reason",
    "find_banked_twin",
    "row_holds_snapshot",
    "receipt_text",
]

# === vaultgate core begin ===
#: A banked dinosaur can only have GROWN since it was parked. The snapshot may
#: read a hair under the stored growth through float round-trips and the
#: engine's own re-zero tick, so a small band is allowed below - never more.
DEFAULT_GROWTH_TOLERANCE = 0.02

#: (field, slot width) of the two families that fix a dinosaur's lineage. The
#: elder family is NOT part of identity: stacks are added over a life, so the
#: twin's elder slots can legitimately outgrow the stored row's.
FAMILIES = (("mutations", 4), ("parent_mutations", 4))

_BLANK = frozenset({"", "none", "null"})


class Verdict(tuple):
    """``(row_id, reason, detail)`` - truthy when a banked twin was found."""

    __slots__ = ()

    def __new__(cls, row_id, reason, detail):
        return tuple.__new__(cls, (row_id, reason, dict(detail)))

    @property
    def row_id(self):
        return self[0]

    @property
    def reason(self):
        return self[1]

    @property
    def detail(self):
        return self[2]


def _text(value):
    try:
        return "" if value is None else str(value).strip()
    except Exception:
        return ""


def _finite_float(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _int_or_zero(value):
    out = _finite_float(value)
    return 0 if out is None else int(out)


def _slots(raw, width):
    """Normalised slot tuple, or None when the family is absent or malformed.

    A MISSING family is not an EMPTY one: letting them match would make every
    blank row collide with every other blank row.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        parts = raw.split("|")
    elif isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        return None
    out = []
    for part in parts:
        name = _text(part).lower()
        out.append("" if name in _BLANK else name)
    if len(out) > width:
        return None
    out.extend([""] * (width - len(out)))
    return tuple(out)


def _species(row):
    return _text(row.get("dino_class") or row.get("dino")).lower()


def _actor(row):
    return _text(row.get("actor_name")).lower()


def _skin(row):
    return _text(row.get("skin_code")).upper()


def _player(row):
    return _text(row.get("steam_id") or row.get("steamid") or row.get("sid"))


def _real_slots(*families):
    return sum(1 for fam in families if fam for slot in fam if slot)


def row_holds_snapshot(snapshot, row, *, growth_tolerance=DEFAULT_GROWTH_TOLERANCE):
    """Is this stored ``row`` the dinosaur in ``snapshot``? Verdict or None.

    Both are expected to belong to one player; when both carry a player id and
    they differ, the answer is None whatever the stats say.
    """
    if not isinstance(snapshot, dict) or not isinstance(row, dict):
        return None
    snap_player, row_player = _player(snapshot), _player(row)
    if snap_player and row_player and snap_player != row_player:
        return None
    species = _species(snapshot)
    if not species or species != _species(row):
        return None
    row_id = row.get("id")
    detail = {"species": species}

    snap_actor, row_actor = _actor(snapshot), _actor(row)
    if snap_actor and row_actor and snap_actor == row_actor:
        detail["actor"] = row_actor
        return Verdict(row_id, "same_actor", detail)

    snap_growth, row_growth = _finite_float(snapshot.get("growth")), _finite_float(row.get("growth"))
    if snap_growth is None or row_growth is None:
        return None
    tol = _finite_float(growth_tolerance)
    tol = DEFAULT_GROWTH_TOLERANCE if tol is None or tol < 0 else tol
    if snap_growth < row_growth - tol:
        return None  # younger than the banked one: a different animal
    if _int_or_zero(snapshot.get("elder_stacks")) < _int_or_zero(row.get("elder_stacks")):
        return None

    fams_snap = [_slots(snapshot.get(field), width) for field, width in FAMILIES]
    fams_row = [_slots(row.get(field), width) for field, width in FAMILIES]
    if any(f is None for f in fams_snap) or any(f is None for f in fams_row):
        return None
    if fams_snap != fams_row:
        return None
    detail.update({"snap_growth": snap_growth, "row_growth": row_growth})

    if _real_slots(*fams_row) == 0:
        snap_skin, row_skin = _skin(snapshot), _skin(row)
        if not snap_skin or not row_skin or snap_skin != row_skin:
            return None
        detail["skin"] = row_skin
        return Verdict(row_id, "same_lineage_skin", detail)
    return Verdict(row_id, "same_lineage", detail)


def find_banked_twin(snapshot, rows, *, growth_tolerance=DEFAULT_GROWTH_TOLERANCE):
    """First stored row that holds the snapshot's dinosaur, else None.

    ``same_actor`` wins over a lineage match when both exist, so the receipt
    names the pawn the park actually killed. Malformed rows are skipped.
    """
    if not isinstance(snapshot, dict) or rows is None:
        return None
    best = None
    try:
        iterator = iter(rows)
    except TypeError:
        return None
    for row in iterator:
        if not isinstance(row, dict):
            continue
        verdict = row_holds_snapshot(snapshot, row, growth_tolerance=growth_tolerance)
        if verdict is None:
            continue
        if verdict.reason == "same_actor":
            return verdict
        if best is None:
            best = verdict
    return best


def empty_snapshot_reason(snapshot):
    """Why this snapshot cannot be restored at all, or None when it can be tried.

    Measured on Arkadia over ten days: 735 of 788 FAILED restores carried a
    BLANK species (the logout snapshot was read after the pawn was already torn
    down) and not one of the 1,051 successful restores did. Issuing a restore
    for such a snapshot is a command the game can only refuse - the "something
    the server started never finished" alert, two or three times an hour.
    """
    if not isinstance(snapshot, dict):
        return "no_snapshot"
    if not _species(snapshot):
        return "blank_species"
    return None


def receipt_text(verdict, backup_id=None):
    """One log-friendly line naming the refused backup, the row and why."""
    if not isinstance(verdict, tuple) or len(verdict) != 3:
        return "vault_holds_row reason=malformed_verdict"
    row_id, reason, detail = verdict
    parts = ["vault_holds_row", "row_id=%s" % (row_id,), "why=%s" % (reason,)]
    if backup_id is not None:
        parts.insert(1, "backup_id=%s" % (backup_id,))
    if isinstance(detail, dict):
        for key in ("species", "snap_growth", "row_growth", "actor"):
            if key in detail:
                value = detail[key]
                if isinstance(value, float):
                    parts.append("%s=%.4f" % (key, value))
                else:
                    parts.append("%s=%s" % (key, value))
    return " ".join(parts)
# === vaultgate core end ===
