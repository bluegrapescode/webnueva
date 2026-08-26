"""Recovery twin gate: a grant must ask the vault first.

Fixtures are the REAL rows of the 2026-08-20 "one dinosaur is counted twice"
FleetView alerts, read off the box the night they fired:

* sid ...427130176 — AutoRescate paid ONE corrupt save twice, 15 minutes apart
  (rows 14013 + 14029, identical Rex 0.873341). 14029 was redeemed and walks;
  14013 stood cashable. The second grant is replayed here and must refuse.
* sid ...257861252 — the panel granted row 15318 (Rex 0.883) while row 15251
  (same lineage, 0.879) was already banked beside two earlier grants. Replayed;
  must refuse naming the banked row.

Run:  py -3.12 web/backend/tests_local/test_recovery_twin_gate.py
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dino_recovery as dr
import vaultrestoregate

PASS = 0
FAIL = []


def check(name, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {extra}".strip())


# --- real prod rows (2026-08-20, La Isla Nublar) -----------------------------
SID_A = "76561199427130176"   # AutoRescate double
SID_B = "76561199257861252"   # panel double

ROW_14013 = {
    "id": 14013, "steam_id": SID_A, "dino_class": "BP_Tyrannosaurus_C",
    "growth": 0.873341,
    "mutations": "Congenital Hypoalgesia|Accelerated Prey Drive|Hemomania|Multichambered Lungs",
    "parent_mutations": "Osteosclerosis|Epidermal Fibrosis|Cannibalistic|None",
    "elder_stacks": 0, "skin_code": "",
}
ROW_15251 = {
    "id": 15251, "steam_id": SID_B, "dino_class": "BP_Tyrannosaurus_C",
    "growth": 0.879,
    "mutations": "Hematophagy|Osteophagic|Efficient Digestion|Hydrodynamic",
    "parent_mutations": "Hemomania|Cellular Regeneration|Nocturnal|Photosynthetic Tissue",
    "elder_stacks": 2, "skin_code": "",
}


def payload(cls, growth, muts, parents, stacks):
    """The slice of build_recovery_payload the gate reads."""
    return {"dino": cls, "growth": growth, "mutations": muts,
            "parent_mutations": parents, "elder_stacks": stacks}


# The grant AutoRescate issued at 05:09Z — identical to what it paid at 04:54Z.
GRANT_A = payload("BP_Tyrannosaurus_C", 0.873341, ROW_14013["mutations"],
                  ROW_14013["parent_mutations"], 0)
# The grant the panel issued as row 15318 (the Rex had grown 0.879 -> 0.883).
GRANT_B = payload("BP_Tyrannosaurus_C", 0.883, ROW_15251["mutations"],
                  ROW_15251["parent_mutations"], 2)

# --- G1/G2: both real leaks refuse, naming the banked row --------------------
v = dr.find_grant_twin(SID_A, GRANT_A, [ROW_14013])
check("G1 autorescate double refused", v is not None and v.row_id == 14013
      and v.reason == "same_lineage", repr(v))
v = dr.find_grant_twin(SID_B, GRANT_B, [ROW_15251])
check("G2 panel double refused", v is not None and v.row_id == 15251
      and v.reason == "same_lineage", repr(v))

# --- G3: honest re-grant — row consumed, vault empty -> grant proceeds -------
check("G3 empty vault grants", dr.find_grant_twin(SID_A, GRANT_A, []) is None)

# --- G4: a YOUNGER look-alike is a different animal -> grant proceeds --------
young = payload("BP_Tyrannosaurus_C", 0.70, ROW_14013["mutations"],
                ROW_14013["parent_mutations"], 0)
check("G4 younger is different", dr.find_grant_twin(SID_A, young, [ROW_14013]) is None)

# --- G5: different lineage same species -> grant proceeds --------------------
other = payload("BP_Tyrannosaurus_C", 0.873341,
                "Hematophagy|Osteophagic|Efficient Digestion|Hydrodynamic",
                ROW_14013["parent_mutations"], 0)
check("G5 different mutations grant", dr.find_grant_twin(SID_A, other, [ROW_14013]) is None)

# --- G6: plain dinosaurs stay ungated (documented: no skin on the payload) ---
plain_row = {"id": 9, "steam_id": SID_A, "dino_class": "BP_Herrerasaurus_C",
             "growth": 0.75, "mutations": "None|None|None|None",
             "parent_mutations": "None|None|None|None", "elder_stacks": 0,
             "skin_code": "HERRERA0FFAA"}
plain_grant = payload("BP_Herrerasaurus_C", 0.75, "None|None|None|None",
                      "None|None|None|None", 0)
check("G6 plain dino ungated", dr.find_grant_twin(SID_A, plain_grant, [plain_row]) is None)

# --- G7: wrong species never matches -----------------------------------------
cross = payload("BP_Carnotaurus_C", 0.879, ROW_15251["mutations"],
                ROW_15251["parent_mutations"], 2)
check("G7 species mismatch", dr.find_grant_twin(SID_B, cross, [ROW_15251]) is None)

# --- G8: fail-open on garbage ------------------------------------------------
check("G8a payload not a dict", dr.find_grant_twin(SID_A, "junk", [ROW_14013]) is None)
check("G8b rows not iterable", dr.find_grant_twin(SID_A, GRANT_A, 7) is None)
check("G8c malformed row skipped",
      dr.find_grant_twin(SID_A, GRANT_A, ["junk", ROW_14013]) is not None)

# --- G9: the receipt names the row ------------------------------------------
v = dr.find_grant_twin(SID_A, GRANT_A, [ROW_14013])
text = dr.grant_twin_receipt(v)
check("G9 receipt", "row_id=14013" in text and "same_lineage" in text, text)

# --- R1/R2: read_twin_rows off a real sqlite file ----------------------------
tmp = os.path.join(tempfile.mkdtemp(prefix="lin_twin_"), "bot.db")
con = sqlite3.connect(tmp)
con.execute("""CREATE TABLE parked_dinos (
    id INTEGER PRIMARY KEY, steam_id TEXT, dino_class TEXT, growth REAL,
    mutations TEXT, parent_mutations TEXT, elder_stacks INTEGER,
    skin_code TEXT, parked_at TEXT)""")
con.execute("INSERT INTO parked_dinos (id, steam_id, dino_class, growth,"
            " mutations, parent_mutations, elder_stacks, skin_code, parked_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (14013, SID_A, "BP_Tyrannosaurus_C", 0.873341,
             ROW_14013["mutations"], ROW_14013["parent_mutations"], 0, "",
             "2026-08-18T04:54:08+00:00"))
con.commit()
con.close()
rows = dr.read_twin_rows(tmp, SID_A)
check("R1 rows read", len(rows) == 1 and rows[0]["id"] == 14013
      and rows[0]["mutations"] == ROW_14013["mutations"], repr(rows)[:120])
check("R1b other sid empty", dr.read_twin_rows(tmp, "76561190000000000") == [])
check("R2 missing db fails open", dr.read_twin_rows(tmp + ".nope", SID_A) == [])
check("R2b blank sid", dr.read_twin_rows(tmp, "") == [])

# --- E1: end to end through the sqlite file, the real replay -----------------
v = dr.find_grant_twin(SID_A, GRANT_A, dr.read_twin_rows(tmp, SID_A))
check("E1 replay through sqlite", v is not None and v.row_id == 14013)

# --- M1/M2: mutants — prove the load-bearing fields are load-bearing ---------
# M1: parent mutations. Base-equal / parents-differ must GRANT under the real
# gate, and a parents-ignoring mutant must call it a twin — so a gate that
# silently dropped the parent family cannot pass this pair.
parents_differ = payload("BP_Tyrannosaurus_C", 0.873341, ROW_14013["mutations"],
                         "Hemomania|None|None|None", 0)
check("M1a parents-only difference grants",
      dr.find_grant_twin(SID_A, parents_differ, [ROW_14013]) is None)
_saved = vaultrestoregate.FAMILIES
try:
    vaultrestoregate.FAMILIES = (("mutations", 4),)
    check("M1b parents-ignoring mutant caught", dr.find_grant_twin(
        SID_A, parents_differ, [ROW_14013]) is not None,
        "parents-ignoring mutant not detectable")
finally:
    vaultrestoregate.FAMILIES = _saved

# M2: growth direction — a tolerance that swallows the whole scale lets the
# younger look-alike match; G4 is the tripwire.
check("M2 tolerance mutant caught", dr.find_grant_twin(
    SID_A, young, [ROW_14013], growth_tolerance=1.0) is not None,
    "G4 would not catch a dead growth direction")

# --- module absence: gate silently off, never a crash ------------------------
_saved_gate = dr._twin_gate
try:
    dr._twin_gate = None
    check("A1 gate absent grants", dr.find_grant_twin(SID_A, GRANT_A, [ROW_14013]) is None)
    check("A2 receipt absent", dr.grant_twin_receipt(v) == "")
finally:
    dr._twin_gate = _saved_gate

print(f"PASS {PASS}  FAIL {len(FAIL)}")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
