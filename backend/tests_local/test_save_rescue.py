"""Battery for save_rescue (pure layer) - SCRIPT, plain python, sys.exit.

Fixture lines are REAL lines lifted from this box's TheIsle.log of
2026-08-14 (boot 03:31:38Z), not invented shapes.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone

# runs from tests_local: the modules live one directory up
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import save_rescue as SR  # noqa: E402

checks, fails = 0, []


def chk(name, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        fails.append("%s :: %s" % (name, detail))
        print("FAIL %s :: %s" % (name, detail))


REAL_CORRUPT_A = ("[2026.08.14-03.32.53:600][567]LogTheIsleJoinData: Warning: "
                  "Save file is corrupt for 76561198670165087. NewKey=1.000000 "
                  "CurrentKey=0.000000 BackupKey=0.000000")
REAL_CORRUPT_B = ("[2026.08.14-05.00.05:817][584]LogTheIsleJoinData: Warning: "
                  "Save file is corrupt for 76561199742286287. NewKey=0.000000 "
                  "CurrentKey=11854.000000 BackupKey=20043.000000")
REAL_VICTIM = ("[2026.08.14-03.31.24:044][195]LogTheIsleKillData: "
               "[2026.08.13-20.31.24]  [] Dino: Stegosaurus, Male, 1.000000 - "
               "Killed the following player: あ Sxntyy ꫟, "
               "[76561198670165087], Dino: Carnotaurus, Male, 0.258468")
REAL_HEALTHY_JOIN = ("[2026.08.14-03.33.42:611][ 34]LogTheIsleJoinData: "
                     "[2026.08.13-20.33.42] Rama [76561198354212373] Joined The "
                     "Server. Save file found Dino: BP_Tenontosaurus_C, Gender: "
                     "Male, Growth: 0.421432")

# --- stamp parsing --------------------------------------------------------
want = int(datetime(2026, 8, 14, 3, 32, 53, tzinfo=timezone.utc).timestamp())
chk("stamp parses to the right epoch", SR.parse_log_stamp("2026.08.14-03.32.53") == want,
    str(SR.parse_log_stamp("2026.08.14-03.32.53")))
chk("garbage stamp -> 0", SR.parse_log_stamp("not-a-stamp") == 0)
chk("empty stamp -> 0", SR.parse_log_stamp("") == 0 and SR.parse_log_stamp(None) == 0)
chk("month 13 -> 0 (timegm rejects)", SR.parse_log_stamp("2026.13.99-99.99.99") == 0)

# --- corrupt-line parsing -------------------------------------------------
ev = SR.parse_corrupt_line(REAL_CORRUPT_A)
chk("corrupt A parses", ev is not None and ev["sid"] == "76561198670165087")
chk("corrupt A ts", ev["ts"] == want, str(ev["ts"]))
chk("corrupt A keys", ev["new_key"] == 1.0 and ev["current_key"] == 0.0
    and ev["backup_key"] == 0.0)
chk("corrupt A shape", SR.key_shape(ev) == "server_keys_zeroed")

evb = SR.parse_corrupt_line(REAL_CORRUPT_B)
chk("corrupt B parses", evb is not None and evb["current_key"] == 11854.0)
chk("corrupt B shape", SR.key_shape(evb) == "client_key_lost")
chk("shape on garbage", SR.key_shape(None) == "other")
# ★ THE FAIL-OPEN key_shape carries and keys_readable closes: an event with NO
# key fields reads as the very shape that authorises a grant.
chk("keyless event still SHAPES as zeroed", SR.key_shape({}) == "server_keys_zeroed")
chk("...but is not READABLE", SR.keys_readable({}) is False)
chk("real keys are readable", SR.keys_readable(ev) is True and SR.keys_readable(evb) is True)
chk("string keys parse", SR.keys_readable({"new_key": "1", "current_key": "0", "backup_key": "0"}) is True)
chk("one missing key -> unreadable",
    SR.keys_readable({"new_key": 1.0, "current_key": 0.0}) is False)
chk("None key -> unreadable",
    SR.keys_readable({"new_key": 1.0, "current_key": None, "backup_key": 0.0}) is False)
chk("junk key -> unreadable",
    SR.keys_readable({"new_key": "x", "current_key": 0.0, "backup_key": 0.0}) is False)
chk("bool key -> unreadable",
    SR.keys_readable({"new_key": True, "current_key": 0.0, "backup_key": 0.0}) is False)
chk("NaN key -> unreadable",
    SR.keys_readable({"new_key": float("nan"), "current_key": 0.0, "backup_key": 0.0}) is False)
chk("inf key -> unreadable",
    SR.keys_readable({"new_key": float("inf"), "current_key": 0.0, "backup_key": 0.0}) is False)
chk("non-dict -> unreadable", SR.keys_readable(None) is False and SR.keys_readable("x") is False)

chk("healthy join is NOT a corrupt event", SR.parse_corrupt_line(REAL_HEALTHY_JOIN) is None)
chk("victim line is NOT a corrupt event", SR.parse_corrupt_line(REAL_VICTIM) is None)
chk("empty/None never raise", SR.parse_corrupt_line("") is None and SR.parse_corrupt_line(None) is None)

# --- victim parsing -------------------------------------------------------
vk = SR.parse_victim_line(REAL_VICTIM)
chk("victim parses sid", vk is not None and vk["sid"] == "76561198670165087", str(vk))
chk("victim ts", vk["ts"] == int(datetime(2026, 8, 14, 3, 31, 24,
    tzinfo=timezone.utc).timestamp()), str(vk))
chk("corrupt line is NOT a victim", SR.parse_victim_line(REAL_CORRUPT_A) is None)
chk("victim on garbage never raises", SR.parse_victim_line("x") is None and SR.parse_victim_line(None) is None)

# --- rescue key -----------------------------------------------------------
chk("rescue key stable", SR.rescue_key("76561198670165087", want) ==
    "savecorrupt:76561198670165087:%d" % want)

# --- snapshot picking -----------------------------------------------------
T = ev["ts"]
snapA = {"steam_id": "s", "dino_class": "BP_Carnotaurus_C", "growth": 0.5, "seen_at": T - 600}
snapB = {"steam_id": "s", "dino_class": "BP_Carnotaurus_C", "growth": 0.6, "seen_at": T - 60}
snapNext = {"steam_id": "s", "dino_class": "BP_Carnotaurus_C", "growth": 0.25, "seen_at": T + 120}
chk("pick newest before the event", SR.pick_rescue_snapshot([snapA, snapB, snapNext], T) is snapB)
chk("the NEXT life is never picked", SR.pick_rescue_snapshot([snapNext], T) is None)
chk("just-after within grace picked",
    SR.pick_rescue_snapshot([{"dino_class": "BP_Rex_C", "seen_at": T + 3, "growth": 1}], T) is not None)
chk("no candidates -> None", SR.pick_rescue_snapshot([], T) is None
    and SR.pick_rescue_snapshot(None, T) is None)
chk("classless candidate ignored",
    SR.pick_rescue_snapshot([{"seen_at": T - 10, "growth": 1}], T) is None)
chk("bad ts -> None", SR.pick_rescue_snapshot([snapB], 0) is None)
chk("garbage rows ignored", SR.pick_rescue_snapshot(["x", None, 5, snapB], T) is snapB)

# --- decide matrix --------------------------------------------------------
SID = "76561198670165087"
base_ev = {"sid": SID, "ts": T, "new_key": 1.0, "current_key": 0.0, "backup_key": 0.0}
good_snap = {"steam_id": SID, "dino_class": "BP_Carnotaurus_C", "growth": 0.62, "seen_at": T - 300}


def D(ev=base_ev, snap=good_snap, deaths=(), parks=(), kills=(), n24=0):
    return SR.decide(ev, snap, list(deaths), list(parks), list(kills), n24)


chk("clean event grants", D() == (True, "ok"), str(D()))
chk("no capture refuses", D(snap=None) == (False, "no_capture"))
chk("empty capture refuses", D(snap={}) == (False, "no_capture"))
chk("unstamped capture refuses", D(snap={"dino_class": "BP_X_C"}) == (False, "capture_unstamped"))
chk("capture after event refuses",
    D(snap={"dino_class": "BP_X_C", "seen_at": T + 60}) == (False, "capture_after_event"))
chk("capture too old refuses",
    D(snap={"dino_class": "BP_X_C", "seen_at": T - SR.RESCUE_SNAPSHOT_MAX_AGE_S - 1})
    == (False, "capture_too_old"))
chk("capture at exactly max age grants",
    D(snap={"dino_class": "BP_X_C", "seen_at": T - SR.RESCUE_SNAPSHOT_MAX_AGE_S})[0] is True)
chk("classless capture refuses",
    D(snap={"seen_at": T - 10}) == (False, "capture_no_class"))

death_in = {"steam_id": SID, "ts": T - 100, "cause": "starve", "dino_class": "BP_Carnotaurus_C"}
death_before = {"steam_id": SID, "ts": good_snap["seen_at"] - SR.RESCUE_EVIDENCE_GRACE_S - 5,
                "cause": "combat", "dino_class": "BP_Carnotaurus_C"}
death_grace = {"steam_id": SID, "ts": good_snap["seen_at"] - 30, "cause": "fall",
               "dino_class": "BP_Carnotaurus_C"}
death_other = {"steam_id": "76561190000000000", "ts": T - 100, "cause": "starve",
               "dino_class": "BP_Rex_C"}
chk("death in window refuses with cause", D(deaths=[death_in]) == (False, "died_starve"))
chk("PARK-kill death refuses too",
    D(deaths=[dict(death_in, cause="parked")]) == (False, "died_parked"))
chk("old death (before window) grants", D(deaths=[death_before])[0] is True)
chk("death just before capture (grace) refuses", D(deaths=[death_grace]) == (False, "died_fall"))
chk("someone ELSE's death never refuses", D(deaths=[death_other])[0] is True)
chk("malformed death rows ignored", D(deaths=["x", None, {}])[0] is True)

kill_in = {"sid": SID, "ts": T - 50}
kill_old = {"sid": SID, "ts": good_snap["seen_at"] - SR.RESCUE_EVIDENCE_GRACE_S - 10}
kill_other = {"sid": "76561190000000001", "ts": T - 50}
chk("game-log kill in window refuses", D(kills=[kill_in]) == (False, "killed_in_log"))
chk("old kill grants", D(kills=[kill_old])[0] is True)
chk("other victim grants", D(kills=[kill_other])[0] is True)

park_in = {"dino_class": "BP_Carnotaurus_C", "parked_at_ts": T - 60}
park_old = {"dino_class": "BP_Carnotaurus_C",
            "parked_at_ts": good_snap["seen_at"] - SR.RESCUE_EVIDENCE_GRACE_S - 10}
chk("recent park refuses", D(parks=[park_in]) == (False, "parked_recently"))
chk("old park grants", D(parks=[park_old])[0] is True)
chk("malformed park rows ignored", D(parks=[{"parked_at_ts": "x"}, None])[0] is True)

chk("daily cap refuses", D(n24=SR.RESCUE_DAILY_CAP) == (False, "daily_cap"))
chk("below cap grants", D(n24=SR.RESCUE_DAILY_CAP - 1)[0] is True)
chk("garbage cap refuses", D(n24="lots") == (False, "daily_cap"))

chk("bad event refuses", D(ev=None) == (False, "bad_event")
    and D(ev={"sid": "", "ts": T}) == (False, "bad_event")
    and D(ev={"sid": SID, "ts": 0}) == (False, "bad_event"))

# --- IS IT ACTUALLY GONE? the key-shape gate (2026-08-15 duplication) ------
# The safelog->relog race leaves the SERVER's save intact, so that player is
# holding the dino on their next clean join. Granting one was the duplication
# a player reported ("redeem, refresh fast, and it is in game and in the
# vault"); it paid out twice on the live box before this gate existed.
race_ev = SR.parse_corrupt_line(REAL_CORRUPT_B)
race_snap = {"steam_id": race_ev["sid"], "dino_class": "BP_Tyrannosaurus_C",
             "growth": 0.9, "seen_at": race_ev["ts"] - 55}
chk("safelog-race player is REFUSED (server save intact)",
    SR.decide(race_ev, race_snap, [], [], [], 0) == (False, "server_save_intact"),
    str(SR.decide(race_ev, race_snap, [], [], [], 0)))
chk("...and no other gate can talk it into a grant",
    SR.decide(race_ev, race_snap, [], [], [], 0)[0] is False)
chk("'other' shape is refused too (fail closed)",
    D(ev=dict(base_ev, new_key=7.0, current_key=3.0, backup_key=9.0))
    == (False, "server_save_intact"))
chk("one surviving backup key is still a save",
    D(ev=dict(base_ev, new_key=0.0, current_key=0.0, backup_key=20043.0))
    == (False, "server_save_intact"))
chk("keyless event refuses BEFORE it can be read as zeroed",
    SR.decide({"sid": SID, "ts": T}, good_snap, [], [], [], 0) == (False, "keys_unreadable"))
chk("the genuine zeroed pair still grants", D() == (True, "ok"), str(D()))
chk("the gate runs ahead of the daily cap (a non-loss spends no budget)",
    SR.decide(race_ev, race_snap, [], [], [], SR.RESCUE_DAILY_CAP)
    == (False, "server_save_intact"))

# --- the Sxntyy control: died 3 s before the crash, rejoined to corrupt ----
# His death IS in the kill log; the rescue must refuse him (his dino died
# fairly) even though his key pair is the genuine zeroed shape.
sxntyy_kill = SR.parse_victim_line(REAL_VICTIM)
sxntyy_snap = {"steam_id": SID, "dino_class": "BP_Carnotaurus_C", "growth": 0.26,
               "seen_at": sxntyy_kill["ts"] - 30}
chk("Sxntyy (died pre-crash) is REFUSED",
    SR.decide(base_ev, sxntyy_snap, [], [], [sxntyy_kill], 0) == (False, "killed_in_log"))

# --- MUTANTS: each must be caught by the block above ----------------------
# 1. gate dropped entirely  -> "safelog-race player is REFUSED" goes red.
# 2. gate reads the LINE not the keys (accept any parsed event) -> same.
# 3. gate accepts client_key_lost as a loss shape -> same.
# 4. keys_readable dropped  -> "keyless event refuses" goes red.
# 5. gate placed AFTER the daily cap -> "runs ahead of the daily cap" goes red.
# 6. gate inverted (only client_key_lost grants) -> "genuine zeroed pair still
#    grants" goes red, and so does every pre-existing grant case above.
chk("mutant 3 control: the two live shapes decide OPPOSITELY",
    SR.key_shape(base_ev) == SR.RESCUE_LOSS_SHAPE
    and SR.key_shape(race_ev) != SR.RESCUE_LOSS_SHAPE
    and D()[0] is True
    and SR.decide(race_ev, race_snap, [], [], [], 0)[0] is False)

# --- read_new_lines -------------------------------------------------------
tmp = tempfile.mkdtemp()
p = os.path.join(tmp, "TheIsle.log")
with open(p, "wb") as fh:
    fh.write(b"line one\nline two\npartial")
lines, pos, rot = SR.read_new_lines(p, 0, 1 << 20)
chk("reads complete lines only", lines == ["line one", "line two"] and not rot, str(lines))
chk("partial tail not consumed", pos == len(b"line one\nline two\n"), str(pos))
with open(p, "ab") as fh:
    fh.write(b" now complete\nnext\n")
lines2, pos2, rot2 = SR.read_new_lines(p, pos, 1 << 20)
chk("continues from pos", lines2 == ["partial now complete", "next"] and not rot2, str(lines2))
with open(p, "wb") as fh:
    fh.write(b"fresh boot\n")
lines3, pos3, rot3 = SR.read_new_lines(p, pos2, 1 << 20)
chk("shrunk file = rotation, reads from top", rot3 and lines3 == ["fresh boot"], str((rot3, lines3)))
chk("missing file never raises", SR.read_new_lines(os.path.join(tmp, "nope.log"), 5, 100) == ([], 5, False))
with open(p, "wb") as fh:
    fh.write(b"A" * 50 + b"\n" + b"B" * 500 + b"\n")
linesc, posc, _ = SR.read_new_lines(p, 0, 60)
chk("cap bounds the read", linesc == ["A" * 50] and posc == 51, str((len(linesc), posc)))
chk("no newline in window -> wait", SR.read_new_lines(p, 51, 20)[0] == [])

# --- sweep the REAL current boot log: parser finds all 56 corrupt lines ----
# Point SAVE_RESCUE_LOG_FIXTURE at a real TheIsle.log to run the sweep; the
# 2026-08-14 boot log (56 corrupt lines) is the reference fixture. Absent =
# skipped, not failed - the fixture is a prod artifact, not a repo file.
CUR = os.environ.get("SAVE_RESCUE_LOG_FIXTURE", "")
if CUR and os.path.exists(CUR):
    n_corrupt, n_victim = 0, 0
    with open(CUR, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if SR.parse_corrupt_line(ln.rstrip("\n")):
                n_corrupt += 1
            elif SR.parse_victim_line(ln.rstrip("\n")):
                n_victim += 1
    chk("real-log sweep finds corrupt lines (>0)", n_corrupt > 0, str(n_corrupt))
    chk("real-log sweep finds victim lines (>0)", n_victim > 0, str(n_victim))
else:
    print("SKIP real-log sweep (set SAVE_RESCUE_LOG_FIXTURE to run it)")

print("\nRESULT save_rescue battery checks=%d fails=%d" % (checks, len(fails)))
for f in fails:
    print("  FAILED: " + f)
sys.exit(0 if not fails else 1)
