"""Named Gateway teleport presets (world coords) + world<->map helpers.

Coordinates are UE cm, derived from the real Gateway POI area anchors in
C:\\IsleSkinWeb\\tools\\map_data\\pois.json. The anchor dataset stores each
point as (north-south, west-east) — i.e. its first field is engine Y and its
second field is engine X — so the presets below carry the SWAPPED reading
(fixed 2026-07-16; the original import copied the fields verbatim, which
teleported players to the mirrored spot across the island's diagonal).
Engine-axis ranges (ground-truthed against live player positions):

    ue_x (west-east)   in [-505000, +607000]
    ue_y (north-south) in [-607000, +509000]

The POI dataset carries NO elevation, so Z is a best-effort constant (the mod
ground-snaps a teleport); it MUST be verified in-game before relying on it.
"""
from __future__ import annotations

# Engine-axis ranges — the authority for "plausible in-bounds".
MIN_X, MAX_X = -505000, 607000
MIN_Y, MAX_Y = -607000, 509000

# No elevation in map_data; a modest positive height the mod snaps to ground.
_DEFAULT_Z = 20000

# key -> (display name, ue_x, ue_y). pois.json "areas" stores (ue_y, ue_x) —
# each tuple below is the anchor's fields SWAPPED into engine order.
_RAW_PRESETS: dict[str, tuple[str, int, int]] = {
    "delta_bay":      ("Delta Bay", 338000, 211000),
    "east_coast":     ("Costa Este", 538000, -97000),
    "highland":       ("Tierras Altas", -71000, -61000),
    "north_plains":   ("Llanuras del Norte", 353000, -345000),
    "oceanport":      ("Puerto (Oceanport)", 545000, -300000),
    "south_plains":   ("Llanuras del Sur", -182000, 185000),
    "swamps":         ("Pantanos", 51000, 302000),
    "west_coast":     ("Costa Oeste", -393000, -21000),
    "central_jungle": ("Jungla Central", 125000, -96000),
    "water_access":   ("Acceso al Agua", 87000, -214000),
}


def _in_bounds(x: int, y: int) -> bool:
    return MIN_X <= x <= MAX_X and MIN_Y <= y <= MAX_Y


# Fail fast at import if an edit introduces an out-of-bounds preset.
PRESETS: dict[str, dict] = {}
for _key, (_name, _x, _y) in _RAW_PRESETS.items():
    if not _in_bounds(_x, _y):
        raise ValueError(f"teleport preset {_key!r} is outside the map bounds: ({_x}, {_y})")
    PRESETS[_key] = {"key": _key, "name": _name, "x": float(_x), "y": float(_y), "z": float(_DEFAULT_Z)}


def list_presets() -> list[dict]:
    return [dict(v) for v in PRESETS.values()]


def get_preset(key: str) -> dict | None:
    v = PRESETS.get(str(key or "").strip())
    return dict(v) if v else None


def coords_in_bounds(x: float, y: float) -> bool:
    try:
        return _in_bounds(float(x), float(y))
    except (TypeError, ValueError):
        return False


def to_percent(ue_x: float, ue_y: float) -> tuple[float, float] | None:
    """World UE coords -> (px, py) in 0..100 for the map pin, matching
    InteractiveMap.jsx's worldToPct (screen X from ue_x, screen Y from ue_y —
    no axis swap; fixed 2026-07-16 alongside the live-map calibration)."""
    try:
        x = float(ue_x)
        y = float(ue_y)
    except (TypeError, ValueError):
        return None
    if x != x or y != y:  # NaN
        return None
    px = (x - MIN_X) / (MAX_X - MIN_X) * 100.0
    py = (y - MIN_Y) / (MAX_Y - MIN_Y) * 100.0
    return (max(0.0, min(100.0, px)), max(0.0, min(100.0, py)))
