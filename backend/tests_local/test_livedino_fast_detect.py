"""
Live-dino fast-detection gate -- game_ipc.read_player_display().

The defect this guards against: /api/me/state answered liveness from the heavy
players.json row alone, which the mod rebuilds in SHARDS (one row can legally
be 10-75 s old at 100+ players, and read_player() refuses anything past 45 s),
so a freshly spawned player read as offline for minutes while the ~1 s
players_positions.json feed had them the whole time.

Imports the REAL backend/game_ipc.py (stdlib-only) and drives it against a
temp Saved dir, exactly like test_me_state_skin_bite.py. Every scenario also
asserts the STRICT readers kept their old behaviour -- they gate real actions
and must not learn liveness from the fast lane.

Run: python backend/tests_local/test_livedino_fast_detect.py
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game_ipc  # noqa: E402

SID = "76561198000000001"
ACTOR = "BP_Tyrannosaurus_C_2147471852"
NEW_ACTOR = "BP_Omniraptor_C_2147400001"

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def heavy_row(age_s, actor=ACTOR, dino="BP_Tyrannosaurus_C"):
    return {
        "steamid": SID, "actor_name": actor, "dino": dino,
        "health": 100.0, "max_health": 200.0,
        "hunger": 50.0, "max_hunger": 80.0,
        "stamina": 10.0, "max_stamina": 40.0,
        "thirst": 30.0, "max_thirst": 60.0,
        "diet_a": 5.0, "diet_b": 6.0, "diet_c": 7.0, "diet_max": 10.0,
        "growth": 0.5, "is_prime": True,
        "x": 100.0, "y": 200.0, "z": 300.0,
        "last_updated": time.time() - age_s,
    }


def pos_row(age_s, actor=ACTOR, dino="BP_Tyrannosaurus_C"):
    return {
        "steamid": SID, "actor_name": actor, "dino": dino,
        "growth": 0.51, "health": 150.0, "hunger": 60.0, "stamina": 33.0,
        "x": 111.0, "y": 222.0, "z": 333.0, "yaw": 90.0,
        "last_updated": time.time() - age_s,
    }


def write_files(heavy, pos, pos_file_age_s=0, pos_raw=None):
    """(Re)write both files and defeat every read cache."""
    with open(game_ipc.PLAYERS_JSON, "w", encoding="utf-8") as f:
        json.dump(heavy if heavy is not None else {}, f)
    with open(game_ipc.PLAYERS_POSITIONS_JSON, "w", encoding="utf-8") as f:
        if pos_raw is not None:
            f.write(pos_raw)
        else:
            json.dump(pos if pos is not None else {}, f)
    if pos_file_age_s:
        old = time.time() - pos_file_age_s
        os.utime(game_ipc.PLAYERS_POSITIONS_JSON, (old, old))
    game_ipc._file_cache.clear()


def mirror_vital_pct(row, cur, mx):
    """Mirrors server.py::me_state()'s _vital_pct verbatim."""
    try:
        m = float(row.get(mx) or 0)
        if m > 0:
            f = float(row.get(cur) or 0) / m
            return max(0.0, min(100.0, f * 100.0))
    except (TypeError, ValueError):
        pass
    return None


def main() -> int:
    tmpdir = tempfile.mkdtemp(prefix="lin_livedino_")
    saved_dir = os.path.join(tmpdir, "Saved")
    os.makedirs(saved_dir, exist_ok=True)
    game_ipc.SAVED_DIR = saved_dir
    game_ipc.PLAYERS_JSON = os.path.join(saved_dir, "players.json")
    game_ipc.PLAYERS_POSITIONS_JSON = os.path.join(saved_dir, "players_positions.json")

    # A. fresh heavy + fresh positions -> heavy row with live overlay
    write_files({SID: heavy_row(2)}, {SID: pos_row(1)})
    row = game_ipc.read_player_display(SID)
    check(isinstance(row, dict), "A: row must be served")
    if isinstance(row, dict):
        check(row.get("health") == 150.0, f"A: current health must come from positions (got {row.get('health')!r})")
        check(row.get("max_health") == 200.0, "A: maxima must stay the heavy row's")
        check(row.get("pos_source") == "live", "A: pos_source must be live")
        check(row.get("x") == 111.0, "A: position must come from positions")
        check(not row.get("heavy_stale") and not row.get("heavy_missing"), "A: fresh heavy must not be flagged")
        check(mirror_vital_pct(row, "health", "max_health") == 75.0, "A: gauge = live current / heavy max")

    # B. heavy REFUSED (120 s) + fresh positions, SAME pawn -> carried forward.
    # This is the exact reported bug: read_player() says None, the player is alive.
    write_files({SID: heavy_row(120)}, {SID: pos_row(1)})
    check(game_ipc.read_player(SID) is None, "B: strict read_player must still refuse a 120 s row")
    check(game_ipc.read_player_status(SID)[0] == "stale", "B: read_player_status must still say stale")
    row = game_ipc.read_player_display(SID)
    check(isinstance(row, dict), "B: display read must serve the alive player")
    if isinstance(row, dict):
        check(row.get("heavy_stale") is True, "B: carried row must be flagged heavy_stale")
        check(row.get("max_health") == 200.0, "B: carried row keeps maxima")
        check(row.get("health") == 150.0, "B: current vitals from positions")
        check(row.get("diet_a") == 5.0, "B: carried row keeps diet")
        check(isinstance(row.get("heavy_age_s"), int) and 115 <= row["heavy_age_s"] <= 130,
              f"B: heavy_age_s must be ~120 (got {row.get('heavy_age_s')!r})")

    # C. heavy refused + fresh positions, DIFFERENT pawn (respawned) -> live-only
    # row; the old pawn's catalogue must NOT dress up the new dino.
    write_files({SID: heavy_row(120)}, {SID: pos_row(1, actor=NEW_ACTOR, dino="BP_Omniraptor_C")})
    row = game_ipc.read_player_display(SID)
    check(isinstance(row, dict), "C: respawned player must read alive")
    if isinstance(row, dict):
        check(row.get("heavy_missing") is True, "C: must be flagged heavy_missing")
        check(row.get("dino") == "BP_Omniraptor_C", "C: species from positions")
        check(row.get("max_health") is None, "C: old pawn's max_health must NOT leak")
        check(row.get("diet_a") is None, "C: old pawn's diet must NOT leak")
        check(row.get("health") == 150.0, "C: raw current health still served")
        check(mirror_vital_pct(row, "health", "max_health") is None,
              "C: gauge must be None (Sin datos), never a percent built on the old pawn")

    # D. no heavy row at all + fresh positions -> live-only row
    write_files({}, {SID: pos_row(1)})
    row = game_ipc.read_player_display(SID)
    check(isinstance(row, dict) and row.get("heavy_missing") is True, "D: brand-new player must read alive as live-only")

    # E. heavy refused + positions ROW stale (20 s > 12 s window) -> offline.
    # A stale heavy row alone must never resurrect liveness.
    write_files({SID: heavy_row(120)}, {SID: pos_row(20)})
    check(game_ipc.read_player_display(SID) is None, "E: no fresh positions row -> offline, stale heavy must not resurrect")

    # F. positions FILE frozen (60 s mtime > 15 s window) + fresh heavy -> exactly today's answer
    write_files({SID: heavy_row(2)}, {SID: pos_row(1)}, pos_file_age_s=60)
    row = game_ipc.read_player_display(SID)
    check(isinstance(row, dict) and row.get("pos_source") == "snapshot", "F: frozen positions file -> heavy-only row")
    if isinstance(row, dict):
        check(row.get("health") == 100.0, "F: no overlay from a frozen file")

    # G. heavy older than the carry ceiling (700 s) + fresh positions same pawn -> live-only, not carried
    write_files({SID: heavy_row(700)}, {SID: pos_row(1)})
    row = game_ipc.read_player_display(SID)
    check(isinstance(row, dict) and row.get("heavy_missing") is True,
          "G: an ancient heavy row must not be carried forward")

    # H. malformed positions file + fresh heavy -> degrades to heavy row
    write_files({SID: heavy_row(2)}, None, pos_raw="{not json")
    row = game_ipc.read_player_display(SID)
    check(isinstance(row, dict) and row.get("pos_source") == "snapshot", "H: malformed positions -> heavy-only row")

    # I. both gone -> offline
    write_files({}, {})
    check(game_ipc.read_player_display(SID) is None, "I: no data -> offline")

    # J. strict readers never learned the fast lane: refused heavy + fresh positions
    write_files({SID: heavy_row(120)}, {SID: pos_row(1)})
    check(game_ipc.read_player(SID) is None, "J: read_player must stay strict under a fresh positions row")
    check(game_ipc.read_player(SID, force_fresh=True) is None, "J: force_fresh path stays strict")

    if failures:
        print(f"FAIL -- livedino fast-detect gate ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS -- livedino fast-detect gate: 9 scenarios, strict readers unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
