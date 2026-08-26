"""
BUILD-PACKET item 1 gate — MyDino.jsx / GET /api/me/state contract parity.

Standalone (no FastAPI/motor/mongo import — this sandbox has neither `motor` installed
nor a backend/.env, so importing server.py directly is not possible here). Instead this
mirrors the exact `dino` dict construction added to backend/server.py::me_state()
(~lines 5235-5347) against the real prod sample row from the BUILD-PACKET, then asserts
every `dino.`/`dino?.` key frontend/src/pages/MyDino.jsx reads is present and — wherever
MyDino.jsx does a `typeof x === "number" && Number.isFinite(x)` check (VitalRow, and the
`typeof dino?.growth === "number"` growth display) — that the value is a finite number.

Keys read by MyDino.jsx (grepped directly from the file):
  dino.species, dino.is_prime, dino.growth, dino.l_mig, dino.l_pat, dino.fractures,
  dino.diet, dino.prime_progress
  VITAL_DEFS (VitalRow, finite-number gate): health, hunger, thirst, stamina, blood, sprint, bite
  FRACTURE_DEFS (VitalRow, finite-number gate): fractures.head, fractures.body, fractures.legs
  DIET_DEFS (VitalRow, finite-number gate): diet.carb, diet.protein, diet.lipid
  primeProgress fallback (only reached if l_mig/l_pat absent): prime_progress.mig.count/cap,
  prime_progress.pat.count/cap

Run: python backend/tests_local/test_me_state_contract.py
"""
import math
import sys

SAMPLE_ROW = {
    "health": 52.6168, "max_health": 52.6168, "stamina": 330.8879, "max_stamina": 330.8879,
    "hunger": 14.6004, "max_hunger": 17.3636, "thirst": 886.3081, "max_thirst": 1000.0,
    "growth": 0.256542, "movement_speed": 716.9047, "bite_damage": 6.1234, "bleeding_stacks": 0,
    "fracture_head": 5.2617, "fracture_head_max": 5.2617, "fracture_body": 7.8925,
    "fracture_body_max": 7.8925, "fracture_legs": 3.9463, "fracture_legs_max": 3.9463,
    "diet_a": 4.957331, "diet_b": 0.0, "diet_c": 0.0, "diet_max": 17.3636,
    "dino": "BP_Tyrannosaurus_C", "actor_name": "BP_Tyrannosaurus_C_2147471852",
    "mutations": "None|None|None|None", "is_elder": False, "is_prime": False,
    "l_mig": 1, "l_pat": 1, "oxygen": 330.8879, "max_oxygen": 330.8879,
    "diet_meter": None, "prime_conditions": 192.0,
    "x": -130342.55, "y": -163966.21,
}


def _bare_species(cls: str) -> str:
    s = str(cls or "")
    if s.startswith("BP_") and s.endswith("_C"):
        s = s[3:-2]
    return s


def build_dino(row: dict, prime_summary: dict | None = None) -> dict:
    """Mirrors backend/server.py::me_state()'s dino-dict construction verbatim."""
    def _pct(cur, mx):
        try:
            m = float(row.get(mx) or 0)
            if m > 0:
                return float(row.get(cur) or 0) / m
        except (TypeError, ValueError):
            pass
        return None

    def _vital_pct(cur, mx):
        f = _pct(cur, mx)
        return None if f is None else max(0.0, min(100.0, f * 100.0))

    def _fpct(cur, mx):
        try:
            m = float(row.get(mx) or 0)
            c = float(row.get(cur) or 0)
            if m > 0 and c == c:
                return max(0.0, min(100.0, (c / m) * 100.0))
        except (TypeError, ValueError):
            pass
        return None

    def _capped_pct(raw, ceiling):
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None
        if v != v:
            return None
        return max(0.0, min(100.0, (v / ceiling) * 100.0))

    def _blood_integrity_pct(raw, max_stacks):
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None
        if v != v:
            return None
        return max(0.0, min(100.0, 100.0 - (100.0 / max_stacks) * v))

    BLEED_MAX_STACKS = 10.0
    SPRINT_MAX_SPEED = 1000.0
    BITE_MAX_DAMAGE = 50.0

    cls = row.get("dino") or row.get("dino_class") or row.get("class") or ""
    species_name = _bare_species(cls)

    growth_raw = row.get("growth")
    try:
        growth_pct = round(float(growth_raw) * 100, 1) if growth_raw is not None else None
    except (TypeError, ValueError):
        growth_pct = None

    prime_summary = prime_summary or {"mig": {"n": 0, "cap": 2}, "pat": {"n": 0, "cap": 4}}
    prime_mig = prime_summary.get("mig") or {}
    prime_pat = prime_summary.get("pat") or {}

    dino = {
        "actor_name": row.get("actor_name") or "",
        "class": cls,
        "name": species_name,
        "species": species_name,
        "growth": growth_pct,
        "health": _vital_pct("health", "max_health"), "max_health": row.get("max_health"),
        "stamina": _vital_pct("stamina", "max_stamina"), "max_stamina": row.get("max_stamina"),
        "hunger": _vital_pct("hunger", "max_hunger"), "max_hunger": row.get("max_hunger"),
        "thirst": _vital_pct("thirst", "max_thirst"), "max_thirst": row.get("max_thirst"),
        "oxygen": row.get("oxygen"), "max_oxygen": row.get("max_oxygen"),
        "health_pct": _pct("health", "max_health"),
        "stamina_pct": _pct("stamina", "max_stamina"),
        "hunger_pct": _pct("hunger", "max_hunger"),
        "thirst_pct": _pct("thirst", "max_thirst"),
        "bleeding_stacks": row.get("bleeding_stacks"),
        "sprint": _capped_pct(row.get("movement_speed"), SPRINT_MAX_SPEED),
        "movement_speed": row.get("movement_speed"),
        "bite_damage": row.get("bite_damage"),
        "blood": _blood_integrity_pct(row.get("bleeding_stacks"), BLEED_MAX_STACKS),
        "bite": _capped_pct(row.get("bite_damage"), BITE_MAX_DAMAGE),
        "fracture_head": row.get("fracture_head"), "fracture_head_max": row.get("fracture_head_max"),
        "fracture_body": row.get("fracture_body"), "fracture_body_max": row.get("fracture_body_max"),
        "fracture_legs": row.get("fracture_legs"), "fracture_legs_max": row.get("fracture_legs_max"),
        "fractures": {
            "head": _fpct("fracture_head", "fracture_head_max"),
            "body": _fpct("fracture_body", "fracture_body_max"),
            "legs": _fpct("fracture_legs", "fracture_legs_max"),
        },
        "diet_a": row.get("diet_a"), "diet_b": row.get("diet_b"), "diet_c": row.get("diet_c"),
        "diet_meter": row.get("diet_meter"), "diet_max": row.get("diet_max"),
        "diet": {
            "carb": _fpct("diet_a", "diet_max"),
            "protein": _fpct("diet_b", "diet_max"),
            "lipid": _fpct("diet_c", "diet_max"),
        },
        "mutations": row.get("mutations") or "",
        "parent_mutations": row.get("parent_mutations") or "",
        "elder_mutations": row.get("elder_mutations") or "",
        "elder_stacks": row.get("elder_stacks"),
        "is_prime": bool(row.get("is_prime")),
        "is_elder": bool(row.get("is_elder")),
        "prime_conditions": row.get("prime_conditions"),
        "l_mig": row.get("l_mig"),
        "l_pat": row.get("l_pat"),
        "prime_progress": {
            "mig": {"count": prime_mig.get("n", 0), "cap": prime_mig.get("cap", 2)},
            "pat": {"count": prime_pat.get("n", 0), "cap": prime_pat.get("cap", 4)},
        },
    }
    return dino


def build_position(row: dict):
    """Mirrors backend/server.py::me_state()'s _self_position() verbatim."""
    try:
        px = float(row.get("x"))
        py = float(row.get("y"))
    except (TypeError, ValueError):
        return None
    if px != px or py != py:
        return None
    return {"x": px, "y": py}


def _is_finite_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def main() -> int:
    dino = build_dino(SAMPLE_ROW)
    failures = []

    def check_present(path, value):
        if value is None:
            failures.append(f"MISSING: dino.{path} is None")

    def check_finite(path, value):
        if not _is_finite_number(value):
            failures.append(f"NOT FINITE: dino.{path} = {value!r}")

    # Top-level keys MyDino.jsx reads directly.
    check_present("species", dino.get("species"))
    assert dino.get("species") == "Tyrannosaurus", f"species mismatch: {dino.get('species')!r}"
    assert isinstance(dino.get("is_prime"), bool), "is_prime must be a bool"
    check_finite("growth", dino.get("growth"))
    check_finite("l_mig", dino.get("l_mig"))
    check_finite("l_pat", dino.get("l_pat"))

    # VITAL_DEFS — every one must be a finite number so VitalRow renders (not "Sin datos").
    for k in ("health", "hunger", "thirst", "stamina", "blood", "sprint", "bite"):
        check_present(k, dino.get(k))
        check_finite(k, dino.get(k))

    # blood is integrity (100=healthy), not bleed-severity: SAMPLE_ROW has
    # bleeding_stacks=0, so blood must be 100 (fully healthy blood), not 0.
    assert dino.get("blood") == 100, f"blood mismatch for 0 bleeding_stacks: {dino.get('blood')!r}"

    # Primary vitals must be 0-100 percents (VitalRow renders them directly as gauge
    # values). Sample row: full health/stamina, hunger 14.6004/17.3636, thirst 886.3081/1000.
    assert dino.get("health") == 100, f"health must be 100: {dino.get('health')!r}"
    assert dino.get("stamina") == 100, f"stamina must be 100: {dino.get('stamina')!r}"
    assert abs(dino.get("hunger") - 84.1) < 0.05, f"hunger must be ~84.1: {dino.get('hunger')!r}"
    assert abs(dino.get("thirst") - 88.6) < 0.05, f"thirst must be ~88.6: {dino.get('thirst')!r}"

    # live-map self-pin: me_state.position = raw UE world coords {x, y} for
    # InteractiveMap's worldToPct; must be present + finite for the sample row.
    pos = build_position(SAMPLE_ROW)
    assert isinstance(pos, dict), f"position missing for sample row: {pos!r}"
    check_finite("position.x", pos.get("x"))
    check_finite("position.y", pos.get("y"))
    assert pos == {"x": -130342.55, "y": -163966.21}, f"position mismatch: {pos!r}"
    assert build_position({}) is None, "position must be None-safe when x/y absent"

    # FRACTURE_DEFS — dino.fractures.{head,body,legs}, each a finite percent.
    fx = dino.get("fractures") or {}
    for k in ("head", "body", "legs"):
        check_present(f"fractures.{k}", fx.get(k))
        check_finite(f"fractures.{k}", fx.get(k))

    # DIET_DEFS — dino.diet.{carb,protein,lipid}, each a finite percent.
    diet = dino.get("diet") or {}
    for k in ("carb", "protein", "lipid"):
        check_present(f"diet.{k}", diet.get(k))
        check_finite(f"diet.{k}", diet.get(k))

    # prime_progress fallback shape (only reached if l_mig/l_pat are absent, but must
    # still exist as a well-formed object so `primeProgress.mig?.count` never throws).
    pp = dino.get("prime_progress") or {}
    for grp in ("mig", "pat"):
        g = pp.get(grp) or {}
        check_finite(f"prime_progress.{grp}.count", g.get("count"))
        check_finite(f"prime_progress.{grp}.cap", g.get("cap"))

    if failures:
        print("FAIL — me_state contract test:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS — all MyDino.jsx dino.*/dino?.* keys present and finite where required.")
    print(f"  species={dino['species']!r} growth={dino['growth']} blood={dino['blood']} "
          f"sprint={round(dino['sprint'], 1)} bite={round(dino['bite'], 1)} "
          f"fractures={ {k: round(v, 1) for k, v in fx.items()} } "
          f"diet={ {k: round(v, 1) for k, v in diet.items()} }")
    return 0


if __name__ == "__main__":
    sys.exit(main())
