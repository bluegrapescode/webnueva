"""Points of interest for the `visit_location` quest objective (La Isla Nublar).

POIS below are ported VERBATIM (same names, same on-screen positions) from
frontend/src/components/livemap/InteractiveMap.jsx's MAP_LOCATIONS array, then
converted from that file's screen-percent coordinates to raw UE world
coordinates using the SAME calibration constants InteractiveMap.jsx documents
(ported there from the donor Arkadia skin site, map/index.inline1.js:16-18),
so this module can be compared directly against players_positions.json's raw
world x/y without importing any frontend/React code.

InteractiveMap.jsx's worldToPct() (2026-07-16 calibration fix — screen column
tracks world X, screen row tracks world Y, no axis swap):
    left = ((x - W_MIN_X) / (W_MAX_X - W_MIN_X)) * 100    # loc.x -> screen left%
    top  = ((y - W_MIN_Y) / (W_MAX_Y - W_MIN_Y)) * 100    # loc.y -> screen top%

_world() below is the inverse of that mapping.

"Top of Dome" has no published on-map position yet (it is referenced only by
the daily_visit_dome quest's objective.poi) -- it is carried here as a
coords-None placeholder so the quest def can reference it today and start
working the moment real coordinates are published, with zero further code
changes. nearest_poi() always skips coords-None entries (never a candidate).

This module has NO dependency on server.py/FastAPI/motor -- it is imported
directly by backend/tests_local tests as well as by server.py's visit-tracker
loop, so both sides exercise the exact same decision logic.
"""
from __future__ import annotations

# World bounds -- must stay equal to InteractiveMap.jsx (W_MIN_X/W_MAX_X/W_MIN_Y/W_MAX_Y).
W_MIN_X, W_MAX_X = -505000.0, 607000.0   # world X (screen column / left%)
W_MIN_Y, W_MAX_Y = -607000.0, 509000.0   # world Y (screen row / top%)

# Default proximity radius, in UE world units ("uu"). MAP_LOCATIONS in
# InteractiveMap.jsx carries no per-location radius (unlike MIGRATION_ZONES/
# WATER_ZONES, which do) -- so every named POI uses this single flat radius.
DEFAULT_RADIUS_UU = 12000.0


def _world(x_pct: float, y_pct: float) -> tuple[float, float]:
    """Inverse of InteractiveMap.jsx's worldToPct(): screen percent -> raw UE world (x, y)."""
    wx = W_MIN_X + (x_pct / 100.0) * (W_MAX_X - W_MIN_X)
    wy = W_MIN_Y + (y_pct / 100.0) * (W_MAX_Y - W_MIN_Y)
    return (wx, wy)


# name, (screen x%, screen y%) -- ported verbatim from InteractiveMap.jsx's
# exported MAP_LOCATIONS array (24 entries, in the same order).
_MAP_LOCATIONS_PCT: list[tuple[str, float, float]] = [
    ("North Bay", 36, 17),
    ("Northern Jungle", 46, 30),
    ("North Plains", 55, 33),
    ("NE Cape", 82, 22),
    ("NW Ridge", 31, 36),
    ("Port", 88, 40),
    ("Water Access", 78, 44),
    ("Eastern Lake", 82, 47),
    ("East Coast", 90, 55),
    ("Forks Plains", 63, 49),
    ("Highland", 49, 46),
    ("Jungle I Sector", 59, 62),
    ("Tide Pool", 73, 60),
    ("West Coast", 15, 52),
    ("West Rail", 24, 58),
    ("The Pit", 45, 58),
    ("Delta", 82, 62),
    ("Mudflats", 68, 66),
    ("Delta Bay", 84, 70),
    ("South Plains", 42, 74),
    ("Swamps", 62, 76),
    ("Sandbank Bay", 54, 84),
    ("Southern Beach", 40, 88),
    ("Southern Beach E", 58, 89),
]

# The 24 real POIs (world coords derived above) + the "Top of Dome" placeholder
# (coords None -- see module docstring). 25 entries total.
POIS: list[dict] = [
    {"name": name, "x": _world(x_pct, y_pct)[0], "y": _world(x_pct, y_pct)[1]}
    for name, x_pct, y_pct in _MAP_LOCATIONS_PCT
] + [
    {"name": "Top of Dome", "x": None, "y": None},
]


def nearest_poi(x, y, radius: float = DEFAULT_RADIUS_UU, pois=None) -> str | None:
    """Name of the nearest POI to raw world (x, y) within `radius` UE units, or
    None when nothing is in range (or x/y aren't usable numbers). POIs with
    coords None (e.g. "Top of Dome") are never candidates."""
    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return None
    if x != x or y != y:  # NaN guard
        return None
    candidates = pois if pois is not None else POIS
    best_name, best_d2 = None, None
    for p in candidates:
        px, py = p.get("x"), p.get("y")
        if px is None or py is None:
            continue
        d2 = (px - x) ** 2 + (py - y) ** 2
        if best_d2 is None or d2 < best_d2:
            best_d2, best_name = d2, p.get("name")
    if best_name is None or best_d2 > radius * radius:
        return None
    return best_name


def quest_matches_poi(objective: dict, poi_name: str) -> bool:
    """objective.poi (if present) restricts a visit_location quest to that exact
    POI name; quests without objective.poi accept any resolved POI."""
    want = (objective or {}).get("poi")
    return not want or want == poi_name


def should_credit_visit(already_today: bool, already_this_week: bool, quest_category: str) -> bool:
    """Pure decision mirror of the visit-tracker loop's crediting rule
    (server.py's _visit_poi_tracker_tick): a "weekly" category quest credits at
    most once per POI per ISO week; every other category (daily/achievement)
    credits at most once per POI per UTC day. Exercised directly by
    backend/tests_local (no Mongo needed)."""
    if quest_category == "weekly":
        return not already_this_week
    return not already_today
