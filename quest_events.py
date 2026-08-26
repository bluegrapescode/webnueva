"""Pure decision logic for Multiplier Events (admin-created, time-boxed
PrimeMeat earning multipliers, e.g. "Dia de Dryosaurus - x30 PrimeMeat").

Everything here is deliberately dependency-free (no Mongo, no game modules) so
backend/tests_local exercises every branch without prod services — the same
pattern as quest_pois.py. server.py owns all I/O (event CRUD, players.json
reads, the passive-payout hook) and calls into these helpers for every
decision.

Fail-closed rule: the boost is a bonus lane. Whenever the live value needed to
apply it is unknown (missing species row, malformed event window), the answer
is "no boost" — the base payout is never blocked by this module.
"""
from datetime import datetime, timezone

import quest_data

# ---------------------------------------------------------------------------
# species normalisation
# ---------------------------------------------------------------------------
_SPECIES_BY_FOLD = {s.lower(): s for s in quest_data.EVENT_SPECIES}


def normalize_species(raw) -> str:
    """Canonical clean species name ("Tyrannosaurus") from any of the shapes the
    stack uses: "BP_Tyrannosaurus_C", "Tyrannosaurus", "tyrannosaurus".
    Unknown/empty -> "" (callers treat that as fail-closed vs constraints)."""
    s = str(raw or "").strip()
    if s.startswith("BP_"):
        s = s[3:]
    if s.endswith("_C"):
        s = s[:-2]
    return _SPECIES_BY_FOLD.get(s.strip().lower(), "")


def species_matches(constraint, actual) -> bool:
    """True when `actual` satisfies an optional species constraint.
    No constraint -> always True. Constraint set + unknown actual -> False."""
    want = normalize_species(constraint)
    if not want:
        return True
    return normalize_species(actual) == want


# ---------------------------------------------------------------------------
# event window
# ---------------------------------------------------------------------------
def _parse_iso(value):
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def event_window(event):
    """(starts_dt, ends_dt) for an event, or (None, None) when malformed."""
    starts = _parse_iso((event or {}).get("starts_at"))
    ends = _parse_iso((event or {}).get("ends_at"))
    if not starts or not ends or ends <= starts:
        return None, None
    return starts, ends


def event_status(event, now=None) -> str:
    """Lifecycle bucket for a multiplier event:
      'upcoming' — before starts_at (visible, no boosting)
      'active'   — inside the window (earnings multiplied)
      'over'     — past ends_at (auto-expired, hidden from players)
      ''         — malformed window (never boosts, never renders)"""
    starts, ends = event_window(event)
    if not starts:
        return ""
    now = now or datetime.now(timezone.utc)
    if now < starts:
        return "upcoming"
    if now < ends:
        return "active"
    return "over"


def event_times(event, now=None) -> dict:
    """Countdown fields (whole seconds, never negative) for the player view."""
    now = now or datetime.now(timezone.utc)
    starts, ends = event_window(event)
    if not starts:
        return {"status": "", "starts_in": 0, "ends_in": 0}
    return {
        "status": event_status(event, now),
        "starts_in": max(0, int(starts.timestamp() - now.timestamp())),
        "ends_in": max(0, int(ends.timestamp() - now.timestamp())),
    }


# ---------------------------------------------------------------------------
# payout boost decision
# ---------------------------------------------------------------------------
def pick_multiplier(events, player_species, now=None):
    """The multiplier to apply to one passive PrimeMeat payout.

    events: candidate multiplier-event dicts (any status — filtered here).
    player_species: the player's CURRENT dino (any raw shape; "" = unknown).

    Returns (multiplier, event) — (1, None) when nothing applies. When several
    active events cover the same species the HIGHEST multiplier wins (never
    stacked: stacking would make overlapping events multiplicative by accident).
    Unknown player species -> no boost (fail-closed on the bonus only)."""
    species = normalize_species(player_species)
    if not species:
        return 1, None
    best_mult, best_ev = 1, None
    for ev in events or []:
        if event_status(ev, now) != "active":
            continue
        if normalize_species((ev or {}).get("species")) != species:
            continue
        try:
            mult = int((ev or {}).get("multiplier") or 0)
        except (TypeError, ValueError):
            continue
        if mult > best_mult:
            best_mult, best_ev = mult, ev
    return best_mult, best_ev


# ---------------------------------------------------------------------------
# admin input validation (server clamps through these — one place, one rule)
# ---------------------------------------------------------------------------
def clamp_int(value, lo, hi, default):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def validate_multiplier_fields(duration_hours, multiplier):
    """Normalise the two numeric event knobs to safe bounds. The caller raises
    on the one hard error (unknown species)."""
    return {
        "duration_hours": clamp_int(duration_hours, 1, quest_data.EVENT_MAX_HOURS,
                                    quest_data.MULT_EVENT_DEFAULT_HOURS),
        "multiplier": clamp_int(multiplier, quest_data.MULT_EVENT_MIN,
                                quest_data.MULT_EVENT_MAX,
                                quest_data.MULT_EVENT_DEFAULT),
    }
