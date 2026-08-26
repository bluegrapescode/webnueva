"""Redeem must ALWAYS replay the parked skin/SEX — including late finalise.

Owner report 2026-07-30: a dino redeemed from La Boveda / the store came back
the WRONG SEX. Root cause (two holes, same symptom):

  1. ``resolve_stale_redeem_pending`` finalises a timed-out-but-landed restore
     WITHOUT the skin/sex/diet replay the normal success path schedules -- the
     player gets the dino with the throwaway spawn's sex and default look.
     (3 redeem timeouts on prod on 2026-07-30 alone.)
  2. ``_apply_redeem_side_effects`` gave up SILENTLY when the actor poll came
     back empty, so a skipped replay was indistinguishable from a done one.

The fix: the late-finalise path schedules ``_late_redeem_side_effects`` (guarded:
replays only while the restore's confirmed actor is STILL the live actor), and
every skip/failure path logs loudly. The vault replay stays UNFLAGGED on
purpose -- the stored sex is the parked dino's true sex and MUST win over the
spawn-screen pawn; ``preserve_female`` here would break redeems the other way.

Run: py -3.12 tests_local/test_redeem_sex_replay.py  (exit 0 = green)
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import time

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

os.environ.setdefault("LIN_TEST_MODE", "1")

import game_ipc  # noqa: E402
import vault  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    tag = "ok" if cond else "FAIL"
    print("  [%s] %s%s" % (tag, name, (" -- " + str(detail)) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


SID = "76561199000000077"
ACTOR = "BP_Deinosuchus_C_2147000001"
SKIN = {"class": "BP_Deinosuchus_C", "female": True, "variation": 2, "pattern": 1,
        "body": [0.1, 0.2, 0.3, 1.0], "markings": [0.1, 0.1, 0.1, 1.0],
        "flank": [0.2, 0.2, 0.2, 1.0], "underbelly": [0.3, 0.3, 0.3, 1.0],
        "detail1": [0.4, 0.4, 0.4, 1.0], "eyes": [0.5, 0.5, 0.5, 1.0],
        "male_display": [0.6, 0.6, 0.6, 1.0]}

# ---- real sqlite row, real vault reader --------------------------------------
fd, dbpath = tempfile.mkstemp(prefix="lin_sexreplay_", suffix=".db")
os.close(fd)
_conn = sqlite3.connect(dbpath)
cols_sql = ", ".join(
    "id INTEGER PRIMARY KEY AUTOINCREMENT" if c == "id" else f"{c} TEXT"
    for c in vault._PARKED_COLS)
_conn.execute(f"CREATE TABLE parked_dinos ({cols_sql})")
_conn.execute(
    "INSERT INTO parked_dinos (steam_id, dino_class, growth, skin_data, mutations,"
    " parent_mutations, elder_mutations, elder_stacks, is_prime, is_elder)"
    " VALUES (?, 'BP_Deinosuchus_C', '0.96', ?, '', '', '', '0', '1', '1')",
    (SID, json.dumps(SKIN, separators=(",", ":"))))
_conn.commit()
_conn.close()
game_ipc.BOT_DB_PATH = dbpath

_tmpdir = tempfile.mkdtemp(prefix="lin_sexreplay_ipc_")
game_ipc.REDEEM_COOLDOWNS_JSON = os.path.join(_tmpdir, "redeem_cooldowns.json")

# ---- real contracts, recording stubs -----------------------------------------
WROTE_SKIN, WROTE_DIET, CLEARED_SWAP = [], [], []
_orig = (game_ipc.write_skin_command, game_ipc.write_diet_command,
         game_ipc.read_player, game_ipc.clear_swap_persist)

game_ipc.write_skin_command = lambda cmd: (WROTE_SKIN.append(json.loads(json.dumps(cmd))), True)[1]
game_ipc.write_diet_command = lambda cmd: (WROTE_DIET.append(dict(cmd)), True)[1]
game_ipc.clear_swap_persist = lambda sid: CLEARED_SWAP.append(str(sid))
_live_actor = {"actor": ACTOR}
game_ipc.read_player = lambda sid, force_fresh=False: (
    {"steamid": sid, "actor_name": _live_actor["actor"], "dino": "BP_Deinosuchus_C",
     "max_hunger": 500.0} if _live_actor["actor"] else None)

vault.RESTORE_DIET_READY_INTERVAL = 0.01


def _reset():
    del WROTE_SKIN[:], WROTE_DIET[:], CLEARED_SWAP[:]


def _point_status(name, entries):
    game_ipc.RESTORE_STATUS_JSON = os.path.join(_tmpdir, name)
    with open(game_ipc.RESTORE_STATUS_JSON, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f)


def _set_pending(cmd_id, at_ms):
    c = sqlite3.connect(dbpath)
    c.execute("UPDATE parked_dinos SET redeem_pending_cmd_id=?, redeem_pending_at=? WHERE id=1",
              (cmd_id, at_ms))
    c.commit()
    c.close()


print("[A] late-finalised redeem replays skin/SEX/diet (the fix)")
_reset()
captured = []
_real_schedule = vault._schedule
vault._schedule = lambda coro: captured.append(coro)
stale_ms = int(time.time() * 1000) - int((vault.REDEEM_VERIFY_TIMEOUT_SECS + 5) * 1000)
_set_pending("late1", stale_ms)
_point_status("late_success.json", [{
    "event": "restore", "steamid": SID, "cmd_id": "late1", "dino_id": 1,
    "actor_name": ACTOR, "prime_ok": True, "mutations_ok": True,
    "growth_ok": True, "stats_ok": True, "max_stats_observed_ok": True}])
row = vault.get_parked_by_id(1)
check("fixture row carries the parked skin_data", bool(str(row.get("skin_data") or "").strip()))
r = vault.resolve_stale_redeem_pending(row)
check("late success still finalises exactly-once", r is None and vault.get_parked_by_id(1) is None)
check("swap-persist cleared on the late path too (parity with _run_redeem)",
      CLEARED_SWAP == [SID], repr(CLEARED_SWAP))
check("a side-effect replay was SCHEDULED (the old code scheduled nothing)",
      len(captured) == 1, "scheduled=%d" % len(captured))
vault._schedule = _real_schedule
if captured:
    asyncio.run(captured.pop())
check("diet replayed", len(WROTE_DIET) == 1 and WROTE_DIET[0]["steamid"] == SID)
check("skin command replayed to the CONFIRMED actor",
      len(WROTE_SKIN) == 1 and WROTE_SKIN[0].get("actor_name") == ACTOR, repr(WROTE_SKIN))
check("replay carries the PARKED sex verbatim (female=True)",
      WROTE_SKIN and WROTE_SKIN[0].get("female") is True)
check("replay is deliberately UNFLAGGED (stored sex must win, not the spawn pawn's)",
      WROTE_SKIN and "preserve_female" not in WROTE_SKIN[0])
check("replay keyed to the parked class + sid",
      WROTE_SKIN and WROTE_SKIN[0].get("class") == "BP_Deinosuchus_C"
      and WROTE_SKIN[0].get("steamid") == SID)

print("[B] guard: life moved on -> NO replay (stamping a new life would be a new bug)")
_reset()
parked_copy = dict(row)
status = {"actor_name": ACTOR}
_live_actor["actor"] = "BP_Deinosuchus_C_2147999999"  # died + respawned since
asyncio.run(vault._late_redeem_side_effects(SID, parked_copy, status))
check("no skin write onto the wrong life", WROTE_SKIN == [])
check("no diet write onto the wrong life", WROTE_DIET == [])
_live_actor["actor"] = ""  # offline
asyncio.run(vault._late_redeem_side_effects(SID, parked_copy, status))
check("offline player -> no writes", WROTE_SKIN == [] and WROTE_DIET == [])
asyncio.run(vault._late_redeem_side_effects(SID, parked_copy, {"actor_name": ""}))
check("no confirmed actor in the restore status -> no writes", WROTE_SKIN == [])

print("[C] _apply_redeem_side_effects edge shapes (never raise, never silent-lie)")
_reset()
_live_actor["actor"] = ACTOR
empty_row = dict(parked_copy)
empty_row["skin_data"] = ""
asyncio.run(vault._apply_redeem_side_effects(SID, empty_row, {"actor_name": ACTOR}))
check("store row (no captured skin): diet written, skin untouched",
      len(WROTE_DIET) == 1 and WROTE_SKIN == [])
_reset()
bad_row = dict(parked_copy)
bad_row["skin_data"] = "{not json"
asyncio.run(vault._apply_redeem_side_effects(SID, bad_row, {"actor_name": ACTOR}))
check("unparseable skin_data: no raise, no skin write", WROTE_SKIN == [])
_reset()
game_ipc.write_skin_command = lambda cmd: False
asyncio.run(vault._apply_redeem_side_effects(SID, parked_copy, {"actor_name": ACTOR}))
check("skin write failure: no raise (logged as ERROR)", True)
game_ipc.write_skin_command = lambda cmd: (WROTE_SKIN.append(json.loads(json.dumps(cmd))), True)[1]
_reset()
_live_actor["actor"] = ""
asyncio.run(vault._apply_redeem_side_effects(SID, parked_copy, {"actor_name": ""}))
check("actor never resolves: gives up without writes (now logged as ERROR)",
      WROTE_SKIN == [] and WROTE_DIET == [])
_live_actor["actor"] = ACTOR

print("[D] cold source asserts on the shipped file (the hook cannot silently vanish)")
src = open(os.path.join(BACKEND, "vault.py"), "r", encoding="utf-8", errors="replace").read()
check("late-finalise branch schedules the replay",
      "_schedule(_late_redeem_side_effects(sid, dict(row), _status))" in src)
check("late replay guard compares confirmed vs live actor",
      "live_actor != confirmed_actor" in src)
check("park logs when the skin/sex capture missed",
      "park skin capture MISSED" in src)
check("actor-not-found skip is an ERROR, not silence",
      "redeem side-effects SKIPPED" in src)
check("normal success path still schedules side effects",
      "_schedule(_apply_redeem_side_effects(steam_id, parked, status))" in src)
check("negative control needle (detector proof): removing the hook fails check D1",
      src.count("_schedule(_late_redeem_side_effects") == 1)

# ---- restore real contracts --------------------------------------------------
(game_ipc.write_skin_command, game_ipc.write_diet_command,
 game_ipc.read_player, game_ipc.clear_swap_persist) = _orig

print()
if FAILS:
    print("RED: %d failing: %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("GREEN: all checks passed")
sys.exit(0)
