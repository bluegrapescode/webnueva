"""
BUILD-PACKET item A gate -- GET /api/me/state's new dino.bite_value / dino.skin.

Unlike test_me_state_contract.py (a pure mirror, since server.py cannot be
imported here -- no motor/.env in this sandbox), this test imports the REAL
backend/game_ipc.py module (stdlib-only, no motor/FastAPI dependency) and
monkeypatches its SAVED_DIR-derived path constants to point at a temp
directory holding a synthetic players.json + skin_snapshots.json. It then
calls the REAL game_ipc.read_player()/read_skin_snapshot() against those temp
files, and mirrors ONLY the me_state()/_dino_skin() dict-construction logic
(the part that genuinely can't run without server.py/motor) on top of that
real IPC output.

Run: python backend/tests_local/test_me_state_skin_bite.py
"""
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game_ipc  # noqa: E402


def _round1(raw):
    """Mirrors server.py::me_state()'s nested _round1 verbatim."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    return round(v, 1)


def _dino_skin(actor_name):
    """Mirrors server.py::_dino_skin() verbatim (module-level helper, not nested)."""
    actor = str(actor_name or "").strip()
    if not actor:
        return None
    snap = game_ipc.read_skin_snapshot(actor)
    if not isinstance(snap, dict) or not snap:
        return None
    return {
        "pattern": snap.get("pattern"),
        "colors": {k: snap.get(k) for k in
                   ("body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display")},
    }


def main() -> int:
    failures = []
    tmpdir = tempfile.mkdtemp(prefix="lin_me_state_skin_")
    saved_dir = os.path.join(tmpdir, "Saved")
    os.makedirs(saved_dir, exist_ok=True)

    players_path = os.path.join(saved_dir, "players.json")
    skins_path = os.path.join(saved_dir, "skin_snapshots.json")

    actor_name = "BP_Tyrannosaurus_C_2147471852"
    sid = "76561198000000001"
    players_payload = {
        sid: {
            "actor_name": actor_name, "dino": "BP_Tyrannosaurus_C",
            "bite_damage": 6.1234, "health": 50.0, "max_health": 50.0,
            # last_updated intentionally omitted -- _snapshot_stale() treats that as fresh.
        }
    }
    skin_payload = {
        actor_name: {
            "class": "BP_Tyrannosaurus_C", "female": False, "variation": 2, "pattern": 1,
            "body": [0.5, 0.3, 0.1, 1.0], "markings": [0.05, 0.04, 0.03, 1.0],
            "flank": [0.4, 0.25, 0.08, 1.0], "underbelly": [0.7, 0.6, 0.5, 1.0],
            "detail1": [0.2, 0.1, 0.05, 1.0], "eyes": [0.9, 0.8, 0.1, 1.0],
            "male_display": [0.6, 0.6, 0.6, 1.0],
        }
    }
    with open(players_path, "w", encoding="utf-8") as f:
        json.dump(players_payload, f)
    with open(skins_path, "w", encoding="utf-8") as f:
        json.dump(skin_payload, f)

    # Monkeypatch the SAVED_DIR-derived path constants game_ipc's readers use.
    game_ipc.SAVED_DIR = saved_dir
    game_ipc.PLAYERS_JSON = players_path
    game_ipc.SKIN_SNAPSHOTS_JSON = skins_path
    game_ipc._file_cache.clear()  # avoid any stale cache entry under these exact paths

    # --- real game_ipc reads ---
    row = game_ipc.read_player(sid)
    if not isinstance(row, dict):
        failures.append(f"game_ipc.read_player() returned {row!r}, expected the synthetic row")
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    bite_value = _round1(row.get("bite_damage"))
    if bite_value != 6.1:
        failures.append(f"bite_value mismatch: {bite_value!r} (expected 6.1)")
    if not (isinstance(bite_value, float) and math.isfinite(bite_value)):
        failures.append(f"bite_value not a finite float: {bite_value!r}")

    skin = _dino_skin(row.get("actor_name") or "")
    if not isinstance(skin, dict):
        failures.append(f"dino.skin missing for an actor WITH a snapshot on file: {skin!r}")
    else:
        if skin.get("pattern") != 1:
            failures.append(f"skin.pattern mismatch: {skin.get('pattern')!r} (expected 1)")
        colors = skin.get("colors") or {}
        for k in ("body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display"):
            if colors.get(k) != skin_payload[actor_name][k]:
                failures.append(f"skin.colors.{k} not passed through opaquely: {colors.get(k)!r}")

    # --- degrade-silently paths ---
    if _dino_skin("") is not None:
        failures.append("dino.skin must be None for an empty actor_name")
    if _dino_skin("BP_SomeOtherDino_C_999") is not None:
        failures.append("dino.skin must be None when the actor has no snapshot on file")
    if _round1(None) is not None:
        failures.append("bite_value must be None when bite_damage is missing")
    if _round1("not-a-number") is not None:
        failures.append("bite_value must be None for a non-numeric bite_damage")

    if failures:
        print("FAIL -- me_state skin/bite gate:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"PASS -- dino.bite_value={bite_value!r} dino.skin={skin!r}")
    print("PASS -- degrade-silently paths (no actor_name / no snapshot / non-numeric bite_damage) all return None")
    return 0


if __name__ == "__main__":
    sys.exit(main())
