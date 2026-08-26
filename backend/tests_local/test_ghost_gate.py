# -*- coding: utf-8 -*-
"""Ghost-paint gate - game_ipc.actor_live_in_engine tri-state contract.

The 2026-08-08 outage: the sid->actor registry served a two-restarts-old actor
name for a live player, so five glitch applies painted a body he no longer had
while uses burned. The gate turns "fresh engine snapshot provably lacks the
actor" into a refuse-before-spend. This battery proves the tri-state contract
on REAL temp files (no mocks of the I/O), including the dangerous direction
(absent-but-fresh MUST be False) and every fail-OPEN edge (missing, stale,
torn, empty, no-name). A mutant that flips the gate to fail-closed or breaks
the tri-state kills at least one check.

Also source-scans server.py: all six paint doors carry the gate (the count is
load-bearing - a new find_active_dino->write_skin_command door without a gate
should fail this until wired).

Run: py -3.12 backend/tests_local/test_ghost_gate.py
"""
import json
import os
import sys
import tempfile
import time

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)

import game_ipc  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def with_snapshot(content_bytes, age_s=0.0):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "wb") as f:
        f.write(content_bytes)
    if age_s:
        old = time.time() - age_s
        os.utime(path, (old, old))
    return path


def main():
    orig = game_ipc.SKIN_SNAPSHOTS_JSON
    snap = {"BP_Triceratops_C_111": {"class": "BP_Triceratops_C"},
            "BP_Tyrannosaurus_C_222": {"class": "BP_Tyrannosaurus_C"}}
    body = json.dumps(snap).encode("utf-8")

    # present + fresh -> True
    p = with_snapshot(body)
    game_ipc.SKIN_SNAPSHOTS_JSON = p
    check("present_fresh_true", game_ipc.actor_live_in_engine("BP_Triceratops_C_111") is True)
    # absent + fresh -> False (THE DANGEROUS DIRECTION: this is the refusal)
    check("absent_fresh_false", game_ipc.actor_live_in_engine("BP_Triceratops_C_999") is False)
    os.remove(p)

    # stale file -> None (fail OPEN)
    p = with_snapshot(body, age_s=600)
    game_ipc.SKIN_SNAPSHOTS_JSON = p
    check("stale_none", game_ipc.actor_live_in_engine("BP_Triceratops_C_999") is None)
    # custom max_age honours the knob
    check("stale_custom_age_true", game_ipc.actor_live_in_engine("BP_Triceratops_C_111", max_age_s=10_000) is True)
    os.remove(p)

    # missing file -> None
    game_ipc.SKIN_SNAPSHOTS_JSON = p + ".definitely_missing"
    check("missing_none", game_ipc.actor_live_in_engine("BP_Triceratops_C_111") is None)

    # torn/truncated json -> None
    p = with_snapshot(body[: len(body) // 2])
    game_ipc.SKIN_SNAPSHOTS_JSON = p
    check("torn_none", game_ipc.actor_live_in_engine("BP_Triceratops_C_111") is None)
    os.remove(p)

    # empty dict -> None (an empty walk is a booting/empty-island writer, not proof)
    p = with_snapshot(b"{}")
    game_ipc.SKIN_SNAPSHOTS_JSON = p
    check("empty_dict_none", game_ipc.actor_live_in_engine("BP_Triceratops_C_111") is None)
    os.remove(p)

    # non-dict json -> None
    p = with_snapshot(b"[1,2,3]")
    game_ipc.SKIN_SNAPSHOTS_JSON = p
    check("non_dict_none", game_ipc.actor_live_in_engine("BP_Triceratops_C_111") is None)
    os.remove(p)

    # empty / None name -> None regardless of snapshot state
    p = with_snapshot(body)
    game_ipc.SKIN_SNAPSHOTS_JSON = p
    check("empty_name_none", game_ipc.actor_live_in_engine("") is None)
    check("none_name_none", game_ipc.actor_live_in_engine(None) is None)
    os.remove(p)

    game_ipc.SKIN_SNAPSHOTS_JSON = orig

    # --- source scan: every paint door is gated ---
    src = open(os.path.join(BACKEND, "server.py"), encoding="utf-8").read()
    # Four async doors ride asyncio.to_thread(_ghost_gate_check, sid, dino, "<lane>");
    # two sync doors (universal paint + admin apply) call actor_live_in_engine inline.
    check("gate_async_doors_four", src.count("asyncio.to_thread(_ghost_gate_check,") == 4,
          detail=f"got {src.count('asyncio.to_thread(_ghost_gate_check,')}")
    check("gate_inline_doors",
          src.count("game_ipc.actor_live_in_engine(dino.get(\"actor_name\")) is False") == 3,
          detail="helper + universal + admin inline gates")
    for lane in ("reward", "equip", "studio", "preset"):
        check(f"gate_lane_{lane}", f'dino, "{lane}")' in src)
    check("gate_admin_inline", "lane=admin" in src)
    check("gate_universal_inline", "lane=universal" in src)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
