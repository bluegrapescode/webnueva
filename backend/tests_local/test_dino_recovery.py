"""dino_recovery: the data layer behind the admin Recuperación tab.

Fixtures are copies of REAL prod records (El Crazy's 2026-07-24 Carnotaurus that
starved at 98.41%, plus his T-Rex park on the same day), because the bug this
replaces was invisible to tests that seeded their own happy-path state.

Run:  py -3.12 web/backend/tests_local/test_dino_recovery.py
"""
import json
import os
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dino_recovery as dr

PASS = 0
FAIL = []


def check(name, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {extra}".strip())


# --- real prod records -------------------------------------------------------
SID = "76561199009325734"
CARNO_TS = 1784920089           # 2026-07-24T19:08:09Z, cause=starve, growth 0.984
TREX_PARK_TS = 1784911534       # 2026-07-24T16:45:34Z — a PARK, not a loss
DEATH_LINES = [
    '{"ts":1784895023,"sid":"76561199009325734","cause":"unknown","dino":"BP_Tyrannosaurus_C","growth":0.517,"oxy_pct":100,"hun_pct":33,"thi_pct":61,"bleed_stk":0,"venom":0,"fell":false}',
    '{"ts":1784911534,"sid":"76561199009325734","cause":"unknown","dino":"BP_Tyrannosaurus_C","growth":0.656,"oxy_pct":100,"hun_pct":33,"thi_pct":44,"bleed_stk":0,"venom":0,"fell":false}',
    '{"ts":1784912551,"sid":"76561199009325734","cause":"unknown","dino":"BP_Carnotaurus_C","growth":0.388,"oxy_pct":-1,"hun_pct":-1,"thi_pct":-1,"bleed_stk":0,"venom":0,"fell":false}',
    '{"ts":1784918012,"sid":"76561199009325734","cause":"unknown","dino":"BP_Carnotaurus_C","growth":0.952,"oxy_pct":-1,"hun_pct":-1,"thi_pct":-1,"bleed_stk":0,"venom":0,"fell":false}',
    '{"ts":1784920089,"sid":"76561199009325734","cause":"starve","dino":"BP_Carnotaurus_C","growth":0.984,"oxy_pct":100,"hun_pct":0,"thi_pct":21,"bleed_stk":0,"venom":0,"fell":false}',
    '{"ts":1784921000,"sid":"76561199705883012","cause":"killed","dino":"BP_Carnotaurus_C","growth":0.404,"oxy_pct":100,"hun_pct":43,"thi_pct":63,"bleed_stk":0,"venom":0,"fell":false}',
]
# A live players.json record, verbatim shape from prod.
LIVE_ROW = {
    "steamid": SID, "dino": "BP_Carnotaurus_C", "growth": 0.98409640789032,
    "health": 500.0, "max_health": 565.0, "stamina": 464.4, "max_stamina": 464.4,
    "hunger": 0.0, "max_hunger": 186.4, "thirst": 210.0, "max_thirst": 1000.0,
    "oxygen": 464.4, "max_oxygen": 464.4, "is_elder": False, "is_prime": True,
    "mutations": "Epidermal Fibrosis|None|Osteosclerosis|Gastronomic Regeneration",
    "parent_mutations": "None|None|None|None",
    "elder_mutations": "None|None|None|None|None|None|None|None", "elder_stacks": 0,
    "skin_code": "Carnotaurus010A8988DFFA78664FF82634DFF3E3430FFB0663FFF",
    "actor_name": "BP_Carnotaurus_C_2147356852",
    "diet_a": 100.7, "diet_b": 11.2, "diet_c": 11.1,
}

TMP = tempfile.mkdtemp(prefix="lin_recovery_")


def write_death_log(lines, name="death_causes.log"):
    d = tempfile.mkdtemp(dir=TMP)
    with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return d


# ============================ species helpers ================================
check("clean_species strips BP/_C", dr.clean_species("BP_Carnotaurus_C") == "Carnotaurus")
check("clean_species passthrough", dr.clean_species("Carnotaurus") == "Carnotaurus")
check("clean_species empty", dr.clean_species(None) == "")
check("to_class_name from bare", dr.to_class_name("Carnotaurus") == "BP_Carnotaurus_C")
check("to_class_name idempotent", dr.to_class_name("BP_Carnotaurus_C") == "BP_Carnotaurus_C")
check("to_class_name empty", dr.to_class_name("  ") == "")
check("to_class_name None", dr.to_class_name(None) == "")

# Death causes normalise to the mod's OWN vocabulary. A cause the mod does not
# emit must read as unknown rather than leaking a raw token into the panel.
check("cause: starve", dr.clean_cause("starve") == "starve")
check("cause: dehydrate is real (the UI used to call it 'thirst')",
      dr.clean_cause("dehydrate") == "dehydrate")
check("cause: poison is real (the UI used to call it 'venom')",
      dr.clean_cause("poison") == "poison")
check("cause: every mod cause survives",
      all(dr.clean_cause(c) == c for c in dr.DEATH_CAUSES))
check("cause: case tolerated", dr.clean_cause("STARVE") == "starve")
check("cause: a cause the mod never emits -> unknown", dr.clean_cause("thirst") == "unknown")
check("cause: junk -> unknown", dr.clean_cause("'; DROP TABLE") == "unknown")
check("cause: empty -> unknown", dr.clean_cause("") == "unknown")
check("cause: None -> unknown", dr.clean_cause(None) == "unknown")

# ============================ death log ======================================
saved = write_death_log(DEATH_LINES)
deaths = dr.read_recent_deaths(saved, SID, 50)
check("deaths: only this player", all(d["steam_id"] == SID for d in deaths))
check("deaths: count", len(deaths) == 5, f"got {len(deaths)}")
check("deaths: newest first", deaths[0]["ts"] == CARNO_TS, f"got {deaths[0]['ts']}")
check("deaths: species parsed", deaths[0]["species"] == "Carnotaurus")
check("deaths: class parsed", deaths[0]["dino_class"] == "BP_Carnotaurus_C")
check("deaths: growth", abs(deaths[0]["growth"] - 0.984) < 1e-9)
check("deaths: growth_pct", deaths[0]["growth_pct"] == 98, f"got {deaths[0]['growth_pct']}")
check("deaths: cause", deaths[0]["cause"] == "starve")
check("deaths: key stable",
      deaths[0]["death_key"] == f"{SID}:{CARNO_TS}:Carnotaurus", deaths[0]["death_key"])
check("deaths: limit respected", len(dr.read_recent_deaths(saved, SID, 2)) == 2)
check("deaths: other player excluded",
      all(d["steam_id"] != "76561199705883012" for d in deaths))
allp = dr.read_recent_deaths(saved, None, 50)
check("deaths: no sid filter returns everyone", len(allp) == 6, f"got {len(allp)}")

# --- the log is hostile ------------------------------------------------------
check("deaths: missing file -> []", dr.read_recent_deaths(os.path.join(TMP, "nope"), SID) == [])
check("deaths: empty saved_dir -> []", dr.read_recent_deaths("", SID) == [])
check("deaths: None saved_dir -> []", dr.read_recent_deaths(None, SID) == [])
bad = write_death_log([
    "not json at all",
    "{ truncated",
    '{"ts":"x","sid":"' + SID + '","dino":"BP_Carnotaurus_C","growth":"y"}',
    '{"ts":1784920089,"sid":"' + SID + '","cause":"starve","dino":"","growth":0.5}',
    '[1,2,3]',
    '{"ts":1784920099,"sid":"' + SID + '","cause":"starve","dino":"BP_Dilophosaurus_C","growth":0.5}',
])
badout = dr.read_recent_deaths(bad, SID, 50)
check("deaths: garbage lines skipped, good one kept", len(badout) == 2, f"got {len(badout)}")
check("deaths: unparseable ts -> 0", any(d["ts"] == 0 for d in badout))
check("deaths: blank species dropped",
      all(d["dino_class"] for d in badout))
pct = write_death_log(['{"ts":1784920089,"sid":"' + SID + '","cause":"starve","dino":"BP_Carnotaurus_C","growth":98.4}'])
check("deaths: percent growth normalised",
      abs(dr.read_recent_deaths(pct, SID)[0]["growth"] - 0.984) < 1e-9)
over = write_death_log(['{"ts":1784920089,"sid":"' + SID + '","cause":"starve","dino":"BP_Carnotaurus_C","growth":9999}'])
check("deaths: absurd growth clamped to 1.0",
      dr.read_recent_deaths(over, SID)[0]["growth"] == 1.0)
neg = write_death_log(['{"ts":1784920089,"sid":"' + SID + '","cause":"starve","dino":"BP_Carnotaurus_C","growth":-5}'])
check("deaths: negative growth clamped to 0", dr.read_recent_deaths(neg, SID)[0]["growth"] == 0.0)
inf = write_death_log(['{"ts":1784920089,"sid":"' + SID + '","cause":"starve","dino":"BP_Carnotaurus_C","growth":Infinity}'])
check("deaths: Infinity growth -> 0 not a crash", dr.read_recent_deaths(inf, SID)[0]["growth"] == 0.0)

# --- the tail window is bounded ---------------------------------------------
big = ['{"ts":%d,"sid":"%s","cause":"starve","dino":"BP_Carnotaurus_C","growth":0.5}' % (1700000000 + i, SID)
       for i in range(6000)]
bigdir = write_death_log(big)
bigsize = os.path.getsize(os.path.join(bigdir, "death_causes.log"))
t0 = time.time()
bigout = dr.read_recent_deaths(bigdir, SID, 15)
elapsed = time.time() - t0
check("deaths: huge log still bounded", len(bigout) == 15, f"got {len(bigout)}")
check("deaths: huge log is fast", elapsed < 1.0, f"{elapsed:.3f}s over {bigsize}B")
check("deaths: tail keeps the NEWEST", bigout[0]["ts"] == 1700000000 + 5999, str(bigout[0]["ts"]))
check("deaths: limit is capped", len(dr.read_recent_deaths(bigdir, SID, 99999)) <= dr.DEATH_LIMIT_MAX)
check("deaths: limit garbage -> default", len(dr.read_recent_deaths(bigdir, SID, "abc")) == dr.DEATH_LIMIT_DEFAULT)

# ============================ snapshots ======================================
snap = dr.snapshot_from_player_row(SID, LIVE_ROW, now_s=CARNO_TS)
check("snapshot: built", isinstance(snap, dict))
check("snapshot: class", snap["dino_class"] == "BP_Carnotaurus_C")
check("snapshot: precise growth kept", snap["growth"] == 0.98409640789032)
check("snapshot: prime", snap["is_prime"] is True)
check("snapshot: elder", snap["is_elder"] is False)
check("snapshot: mutations verbatim",
      snap["mutations"] == "Epidermal Fibrosis|None|Osteosclerosis|Gastronomic Regeneration")
check("snapshot: no row -> None", dr.snapshot_from_player_row(SID, None) is None)
check("snapshot: not a dict -> None", dr.snapshot_from_player_row(SID, "x") is None)
check("snapshot: no sid -> None", dr.snapshot_from_player_row("", LIVE_ROW) is None)
check("snapshot: no dino -> None", dr.snapshot_from_player_row(SID, {"growth": 0.5}) is None)
nanrow = dict(LIVE_ROW, growth=float("nan"), elder_stacks=float("inf"))
nansnap = dr.snapshot_from_player_row(SID, nanrow)
check("snapshot: NaN growth -> 0", nansnap["growth"] == 0.0)
check("snapshot: inf stacks -> 0", nansnap["elder_stacks"] == 0)
nomuts = dr.snapshot_from_player_row(SID, {"dino": "BP_Carnotaurus_C", "growth": 0.5})
check("snapshot: missing mutations default to empty slots",
      nomuts["mutations"] == dr.EMPTY_MUTATIONS)
check("snapshot: missing elder mutations default",
      nomuts["elder_mutations"] == dr.EMPTY_ELDER_MUTATIONS)

# --- signature only moves on a real change ----------------------------------
# Every comparison pins the SAME now_s, so only the field under test can move
# the signature (the time bucket is exercised separately below).
def sig_of(**over):
    return dr.snapshot_signature(
        dr.snapshot_from_player_row(SID, dict(LIVE_ROW, **over), now_s=CARNO_TS))


sig = dr.snapshot_signature(snap)
check("signature: stable", sig == dr.snapshot_signature(dict(snap)))
check("signature: 0.01% growth does NOT rewrite", sig_of(growth=0.98419640789032) == sig)
check("signature: 0.2% growth DOES rewrite", sig_of(growth=0.9861) != sig)
check("signature: mutation change rewrites",
      sig_of(mutations="Osteosclerosis|None|None|None") != sig)
check("signature: prime change rewrites", sig_of(is_prime=False) != sig)
check("signature: elder change rewrites", sig_of(is_elder=True) != sig)
check("signature: skin change rewrites", sig_of(skin_code="Carnotaurus0100") != sig)
check("signature: garbage -> ''", dr.snapshot_signature(None) == "")

# A FULLY-GROWN dino never changes any field. Without a clock term its snapshot
# would stop being rewritten, age past SNAPSHOT_MAX_AGE_S, and be rejected at
# death — the best dinos on the server would come back with no mutations.
grown = dict(LIVE_ROW, growth=1.0)
s_now = dr.snapshot_signature(dr.snapshot_from_player_row(SID, grown, now_s=CARNO_TS))
s_soon = dr.snapshot_signature(dr.snapshot_from_player_row(
    SID, grown, now_s=CARNO_TS + dr.SNAPSHOT_REFRESH_S // 5))
s_later = dr.snapshot_signature(dr.snapshot_from_player_row(
    SID, grown, now_s=CARNO_TS + dr.SNAPSHOT_REFRESH_S + 1))
check("signature: unchanged dino does NOT rewrite every tick", s_soon == s_now)
check("signature: unchanged dino DOES refresh on the clock", s_later != s_now)
check("refresh beats the trust window", dr.SNAPSHOT_REFRESH_S < dr.SNAPSHOT_MAX_AGE_S,
      f"{dr.SNAPSHOT_REFRESH_S} vs {dr.SNAPSHOT_MAX_AGE_S}")
# and the refreshed snapshot is still accepted for a death right after it
grown_snap = dr.snapshot_from_player_row(SID, grown, now_s=CARNO_TS + 3600)
check("fully-grown dino is still matchable an hour later",
      dr.snapshot_matches_death(grown_snap, dict(deaths[0], ts=CARNO_TS + 3600 + 30)) is True)

# --- a snapshot must describe the dino that DIED ----------------------------
carno_death = deaths[0]
trex_death = next(d for d in deaths if d["species"] == "Tyrannosaurus")
check("match: same species, seen just before death",
      dr.snapshot_matches_death(snap, carno_death) is True)
check("match: different species rejected",
      dr.snapshot_matches_death(snap, trex_death) is False)
# The species guard must stand on its own, not lean on the time window: a
# T-Rex death moments after a Carnotaurus snapshot must NOT inherit the
# Carnotaurus' mutations.
trex_death_same_moment = dict(trex_death, ts=CARNO_TS)
check("match: same moment but wrong species is still rejected",
      dr.snapshot_matches_death(snap, trex_death_same_moment) is False)
carno_snap_trex_death = dr.snapshot_from_player_row(
    SID, dict(LIVE_ROW, dino="BP_Tyrannosaurus_C"), now_s=CARNO_TS)
check("match: T-Rex snapshot vs T-Rex death at the same moment IS accepted",
      dr.snapshot_matches_death(carno_snap_trex_death, trex_death_same_moment) is True)
stale = dr.snapshot_from_player_row(SID, LIVE_ROW, now_s=CARNO_TS - dr.SNAPSHOT_MAX_AGE_S - 60)
check("match: stale snapshot rejected", dr.snapshot_matches_death(stale, carno_death) is False)
future = dr.snapshot_from_player_row(SID, LIVE_ROW, now_s=CARNO_TS + 600)
check("match: snapshot AFTER the death rejected (that's the next dino)",
      dr.snapshot_matches_death(future, carno_death) is False)
just_after = dr.snapshot_from_player_row(SID, LIVE_ROW, now_s=CARNO_TS + 20)
check("match: one loop tick past the death still counts",
      dr.snapshot_matches_death(just_after, carno_death) is True)
check("match: None snapshot", dr.snapshot_matches_death(None, carno_death) is False)
check("match: None death", dr.snapshot_matches_death(snap, None) is False)

# ============================ park correlation ===============================
# Parking KILLS the dino, so it writes a death line. It must never be offered.
vault_rows = [{"dino_class": "BP_Tyrannosaurus_C", "parked_at_ts": TREX_PARK_TS}]
check("park: the T-Rex park death is recognised as a park",
      dr.death_looks_parked(trex_death, vault_rows, []) is True)
check("park: the real carno loss is NOT a park",
      dr.death_looks_parked(carno_death, vault_rows, []) is False)
check("park: wrong species does not match",
      dr.death_looks_parked(carno_death, [{"dino_class": "BP_Carnotaurus_C",
                                           "parked_at_ts": TREX_PARK_TS}], []) is False)
far = [{"dino_class": "BP_Tyrannosaurus_C", "parked_at_ts": TREX_PARK_TS + 3600}]
check("park: an hour apart does not match", dr.death_looks_parked(trex_death, far, []) is False)
edge = [{"dino_class": "BP_Tyrannosaurus_C",
         "parked_at_ts": TREX_PARK_TS + dr.PARK_MATCH_WINDOW_S - 1}]
check("park: inside the window matches", dr.death_looks_parked(trex_death, edge, []) is True)
edge_out = [{"dino_class": "BP_Tyrannosaurus_C",
             "parked_at_ts": TREX_PARK_TS + dr.PARK_MATCH_WINDOW_S + 1}]
check("park: outside the window does not", dr.death_looks_parked(trex_death, edge_out, []) is False)
# The row is gone (redeemed) but the mark survives — the real point of marks.
check("park: a REDEEMED park is still caught by its mark",
      dr.death_looks_parked(trex_death, [],
                            [{"dino_class": "BP_Tyrannosaurus_C",
                              "parked_at_ts": TREX_PARK_TS}]) is True)
check("park: no data -> not parked", dr.death_looks_parked(trex_death, [], []) is False)
check("park: junk rows ignored", dr.death_looks_parked(trex_death, ["x", None], [None]) is False)
check("park: bad death -> False", dr.death_looks_parked(None, vault_rows, []) is False)

# ============================ the lost list ==================================
lost = dr.build_lost_list(deaths, vault_rows=vault_rows, park_marks=[],
                          recovered_keys=set(),
                          snapshot=snap)
check("lost: the parked T-Rex is filtered out",
      all(l["death_key"] != trex_death["death_key"] for l in lost))
check("lost: 4 remain", len(lost) == 4, f"got {len(lost)}")
check("lost: newest first", lost[0]["death_key"] == carno_death["death_key"])
check("lost: snapshot fills mutations",
      lost[0]["mutations"] == "Epidermal Fibrosis|None|Osteosclerosis|Gastronomic Regeneration")
check("lost: mutation count", lost[0]["mutations_count"] == 3, str(lost[0]["mutations_count"]))
check("lost: prime carried", lost[0]["is_prime"] is True)
check("lost: detail=full with a snapshot", lost[0]["detail"] == "full")
check("lost: snapshot growth beats the rounded log value",
      lost[0]["growth"] == 0.98409640789032, str(lost[0]["growth"]))
check("lost: without a snapshot -> partial", lost[1]["detail"] == "partial")
check("lost: partial has no invented mutations", lost[1]["mutations_count"] == 0)
check("lost: partial keeps the log growth", lost[1]["growth_pct"] == 95, str(lost[1]["growth_pct"]))
already = dr.build_lost_list(deaths, vault_rows=vault_rows,
                             recovered_keys={carno_death["death_key"]},
                             snapshot=None)
check("lost: an already-granted dino is flagged", already[0]["recovered"] is True)
check("lost: others are not flagged", already[1]["recovered"] is False)
check("lost: size cap honoured", len(dr.build_lost_list(deaths, size=2)) == 2)

# A death from before we were recording parks cannot be told apart from a park
# that was redeemed — flag it so nobody hands back a dino the player still has.
ledger = dr.build_lost_list(deaths, vault_rows=[], park_marks=[],
                            ledger_start_ts=CARNO_TS)
check("lost: deaths before the ledger are flagged unverified",
      all(l["park_unverified"] for l in ledger if l["ts"] < CARNO_TS),
      str([(l["ts"], l["park_unverified"]) for l in ledger]))
check("lost: the death AT the ledger start is trusted",
      next(l for l in ledger if l["ts"] == CARNO_TS)["park_unverified"] is False)
check("lost: with no ledger yet, nothing is flagged",
      not any(l["park_unverified"] for l in dr.build_lost_list(deaths, ledger_start_ts=0)))
check("lost: size garbage -> default",
      len(dr.build_lost_list(deaths, size="x")) == min(len(deaths), dr.LOST_LIST_SIZE))
check("lost: default size is 15", dr.LOST_LIST_SIZE == 15)
check("lost: empty input", dr.build_lost_list([]) == [])
check("lost: None input", dr.build_lost_list(None) == [])
check("lost: junk entries skipped", len(dr.build_lost_list(["x", None, carno_death])) == 1)

# ============================ mutation counting ==============================
check("count: 3 of 4 slots", dr.count_mutations("Epidermal Fibrosis|None|Osteosclerosis|Gastronomic Regeneration") == 3)
check("count: all empty", dr.count_mutations(dr.EMPTY_MUTATIONS) == 0)
check("count: blank", dr.count_mutations("") == 0)
check("count: None", dr.count_mutations(None) == 0)
check("count: case-insensitive none", dr.count_mutations("none|NONE|None|Osteosclerosis") == 1)

# ============================ the vault payload ==============================
payload = dr.build_recovery_payload("BP_Carnotaurus_C", 0.984, snapshot=snap,
                                    skin_data='{"class":"BP_Carnotaurus_C"}')
check("payload: class", payload["dino"] == "BP_Carnotaurus_C")
check("payload: snapshot growth wins over the log value",
      payload["growth"] == 0.984, str(payload["growth"]))
check("payload: prime from snapshot", payload["is_prime"] is True)
check("payload: mutations from snapshot",
      payload["mutations"] == "Epidermal Fibrosis|None|Osteosclerosis|Gastronomic Regeneration")
check("payload: skin carried", payload["skin_data"] == '{"class":"BP_Carnotaurus_C"}')
# THE SENTINEL. A recovered dino must not come back at the values that killed it.
for axis in ("health", "max_health", "stamina", "max_stamina", "hunger", "max_hunger",
             "thirst", "max_thirst", "oxygen", "max_oxygen"):
    check(f"payload: {axis} is the refill sentinel 0", payload[axis] == 0.0, str(payload[axis]))
for axis in ("x", "y", "z"):
    check(f"payload: {axis} is 0 (no park spot)", payload[axis] == 0.0)
check("payload: skin_code left empty (skin_data repaints)", payload["skin_code"] == "")
check("payload: diet reset to the species baseline",
      payload["diet_a"] == 0.0 and payload["diet_b"] == 0.0 and payload["diet_c"] == 0.0)

nosnap = dr.build_recovery_payload("BP_Carnotaurus_C", 0.984)
check("payload: no snapshot -> empty mutation slots", nosnap["mutations"] == dr.EMPTY_MUTATIONS)
check("payload: no snapshot -> not prime", nosnap["is_prime"] is False)
check("payload: no snapshot -> not elder", nosnap["is_elder"] is False)
check("payload: no snapshot -> elder slots empty",
      nosnap["elder_mutations"] == dr.EMPTY_ELDER_MUTATIONS)

manual = dr.build_recovery_payload("Carnotaurus", 80, is_prime=True, is_elder=True,
                                   mutations="Osteosclerosis|None|None|None")
check("payload: bare species accepted", manual["dino"] == "BP_Carnotaurus_C")
check("payload: percent growth normalised", manual["growth"] == 0.8, str(manual["growth"]))
check("payload: explicit prime beats absent snapshot", manual["is_prime"] is True)
check("payload: explicit elder", manual["is_elder"] is True)
check("payload: explicit mutations", manual["mutations"] == "Osteosclerosis|None|None|None")
override = dr.build_recovery_payload("BP_Carnotaurus_C", 0.5, snapshot=snap, is_prime=False)
check("payload: explicit False overrides a prime snapshot", override["is_prime"] is False)
check("payload: explicit growth overrides the snapshot", override["growth"] == 0.5)
check("payload: growth clamped high", dr.build_recovery_payload("x", 500)["growth"] == 1.0)
check("payload: growth clamped low", dr.build_recovery_payload("x", -1)["growth"] == 0.0)
check("payload: NaN growth -> 0", dr.build_recovery_payload("x", float("nan"))["growth"] == 0.0)
check("payload: elder_stacks int", isinstance(payload["elder_stacks"], int))

# ============================ skin read (real sqlite) ========================
skin_db = os.path.join(TMP, "skins.db")
con = sqlite3.connect(skin_db)
con.execute("""CREATE TABLE skin_last_applied (
    steam_id TEXT, dino_class TEXT, actor_name TEXT, kind TEXT, payload TEXT,
    active INTEGER, updated_utc TEXT, recipe_digest TEXT)""")
con.execute("INSERT INTO skin_last_applied VALUES (?,?,?,?,?,?,?,?)",
            (SID, "BP_Carnotaurus_C", "BP_Carnotaurus_C_2147364519", "regular",
             json.dumps({"class": "BP_Carnotaurus_C", "steamid": SID,
                         "actor_name": "BP_Carnotaurus_C_2147364519",
                         "pattern": 2, "body": [0.67, 0.19, 0.02, 1.0],
                         "preserve_female": True}),
             0, "2026-07-24T19:08:10Z", "sha256:x"))
con.execute("INSERT INTO skin_last_applied VALUES (?,?,?,?,?,?,?,?)",
            (SID, "BP_Stegosaurus_C", "a", "regular", "not json", 0, "t", "d"))
con.commit()
con.close()

got = dr.read_last_skin(skin_db, SID, "BP_Carnotaurus_C")
check("skin: found", bool(got))
skin_cmd = json.loads(got) if got else {}
check("skin: colours carried", skin_cmd.get("body") == [0.67, 0.19, 0.02, 1.0])
check("skin: class stamped", skin_cmd.get("class") == "BP_Carnotaurus_C")
check("skin: actor_name stripped (never repaint a bystander)", "actor_name" not in skin_cmd)
check("skin: steamid stripped", "steamid" not in skin_cmd)
check("skin: preserve_female kept", skin_cmd.get("preserve_female") is True)
check("skin: bare species accepted", bool(dr.read_last_skin(skin_db, SID, "Carnotaurus")))
check("skin: wrong species -> ''", dr.read_last_skin(skin_db, SID, "BP_Tyrannosaurus_C") == "")
check("skin: unknown player -> ''", dr.read_last_skin(skin_db, "765", "BP_Carnotaurus_C") == "")
check("skin: unparseable payload -> ''", dr.read_last_skin(skin_db, SID, "BP_Stegosaurus_C") == "")
check("skin: missing db -> ''", dr.read_last_skin(os.path.join(TMP, "no.db"), SID, "BP_Carnotaurus_C") == "")
check("skin: blank db path -> ''", dr.read_last_skin("", SID, "BP_Carnotaurus_C") == "")
check("skin: blank sid -> ''", dr.read_last_skin(skin_db, "", "BP_Carnotaurus_C") == "")
empty_db = os.path.join(TMP, "empty.db")
sqlite3.connect(empty_db).close()
check("skin: db without the table -> '' not a crash",
      dr.read_last_skin(empty_db, SID, "BP_Carnotaurus_C") == "")

# ============================ park-mark source ===============================
vault_db = os.path.join(TMP, "vault.db")
con = sqlite3.connect(vault_db)
con.execute("""CREATE TABLE parked_dinos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, steam_id TEXT, discord_id TEXT,
    dino_class TEXT, growth REAL, parked_at TEXT)""")
con.execute("INSERT INTO parked_dinos (steam_id, discord_id, dino_class, growth, parked_at)"
            " VALUES (?,?,?,?,?)",
            (SID, "", "BP_Tyrannosaurus_C", 0.656, "2026-07-24T16:45:34.974906+00:00"))
con.execute("INSERT INTO parked_dinos (steam_id, discord_id, dino_class, growth, parked_at)"
            " VALUES (?,?,?,?,?)", (SID, "", "BP_Carnotaurus_C", 0.984, "not a date"))
con.commit()
con.close()
marks = dr.read_parked_rows(vault_db)
check("marks: rows read", len(marks) == 2, f"got {len(marks)}")
check("marks: iso parsed to the park second",
      marks[0]["parked_at_ts"] == TREX_PARK_TS, str(marks[0]["parked_at_ts"]))
check("marks: bad date -> 0 not a crash", marks[1]["parked_at_ts"] == 0)
check("marks: missing db -> []", dr.read_parked_rows(os.path.join(TMP, "no.db")) == [])
check("marks: blank path -> []", dr.read_parked_rows("") == [])
check("marks: db without the table -> []", dr.read_parked_rows(empty_db) == [])
check("iso: Z suffix", dr.parse_iso_ts("2026-07-24T16:45:34+00:00") == TREX_PARK_TS)
check("iso: junk -> 0", dr.parse_iso_ts("tomorrow") == 0)
check("iso: None -> 0", dr.parse_iso_ts(None) == 0)

# ==================== NEGATIVE CONTROL: the bug this replaces ================
# The old lane keyed recovery off db.dino_records, written only from
# user["active_dino"]. Prod had 0 users with that field, so every real dino
# 404'd. Prove the new lane does NOT depend on it: with nothing but the mod's
# own death log we still produce a recoverable Carnotaurus.
only_log = dr.build_lost_list(dr.read_recent_deaths(saved, SID, 60), vault_rows=[], park_marks=[])
check("NEGATIVE CONTROL: recoverable with no web-side record at all",
      any(l["species"] == "Carnotaurus" and l["growth_pct"] == 98 for l in only_log),
      json.dumps(only_log[:1]))

print("\n%d passed, %d failed" % (PASS, len(FAIL)))
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
