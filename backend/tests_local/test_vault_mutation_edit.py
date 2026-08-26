# -*- coding: utf-8 -*-
"""Vault mutation editor gate — catalog restrictions, slot encoding, CAS write.

Imports the REAL backend/mutation_catalog.py + vault.py against a temp SQLite
DB (game_ipc.BOT_DB_PATH monkeypatched), same harness as
test_marketplace_vault_escrow.py. The Mongo charge/refund server.py adds on
top is exercised by its own logic tests below (cost rules mirrored inline —
kept in sync with server.py me_vault_mutations_set).

Run: python backend/tests_local/test_vault_mutation_edit.py
"""
import os
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game_ipc  # noqa: E402
import mutation_catalog as mc  # noqa: E402
import vault  # noqa: E402

_PARKED_COLS = [
    "id", "steam_id", "discord_id", "dino_class", "growth",
    "health", "max_health", "stamina", "max_stamina",
    "hunger", "max_hunger", "thirst", "max_thirst",
    "oxygen", "max_oxygen", "x", "y", "z",
    "is_prime", "is_elder", "mutations", "parent_mutations",
    "elder_mutations", "elder_stacks", "skin_code", "skin_data",
    "diet_a", "diet_b", "diet_c",
    "parked_at", "redeem_pending_cmd_id", "redeem_pending_at",
]

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


def expect_ok(name, fn, want=None, want_current=None):
    """A call that MUST be allowed. Reports a clean FAIL instead of crashing the
    run when a rule regresses into rejecting it — otherwise one bad rule takes
    the whole suite down and hides which rule broke."""
    try:
        value, current = fn()
    except mc.MutationEditError as e:
        check(name, False, f"rejected: {e}")
        return None, None
    ok = (want is None or value == want) and (want_current is None or current == want_current)
    check(name, ok, f"got: value={value!r} current={current!r}")
    return value, current


def expect_error(name, fn, needle=""):
    try:
        fn()
    except mc.MutationEditError as e:
        check(name, needle.lower() in str(e).lower(), f"got: {e}")
        return
    check(name, False, "no MutationEditError raised")


def row(cls="BP_Tyrannosaurus_C", muts="", parent="", elder="", stacks=3, pending="",
        growth=1.0, is_prime=1):
    # growth/is_prime default to a full-grown Prime, and stacks to a
    # three-times-entombed dino, so the cases that predate either ladder keep
    # testing what they were written to test. Every ladder case passes its own.
    return {"id": 1, "steam_id": "76561199000000001", "dino_class": cls,
            "mutations": muts, "parent_mutations": parent,
            "elder_mutations": elder, "elder_stacks": stacks,
            "growth": growth, "is_prime": is_prime,
            "redeem_pending_cmd_id": pending}


print("[1] catalog / diet restriction matrix")
rex = row()
trike = row(cls="BP_Triceratops_C")
galli = row(cls="BP_Gallimimus_C")

v, cur = mc.validate_slot_edit(rex, "n1", "Hemomania")
check("carni mut on carnivore ok", v == "Hemomania" and cur == "None")
expect_error("carni mut on herbivore rejected",
             lambda: mc.validate_slot_edit(trike, "n1", "Hemomania"), "carnívoros")
v, _ = mc.validate_slot_edit(trike, "n1", "Tactile Endurance")
check("herbi mut on herbivore ok", v == "Tactile Endurance")
expect_error("herbi mut on carnivore rejected",
             lambda: mc.validate_slot_edit(rex, "n1", "Tactile Endurance"), "herbívoros")
expect_error("carni mut on gallimimus rejected",
             lambda: mc.validate_slot_edit(galli, "n1", "Hematophagy"), "carnívoros")
# Full game-truth restriction matrix (owner report 2026-07-12: the earlier 4/3
# split let Tactile Endurance etc. onto carnivores).
#
# SPELLED OUT BY HAND, NEVER read off mc.CARNIVORE_ONLY: a hand list is what
# makes this matrix an independent statement of the rule. Derive it from the
# module and a name silently DROPPED from the module set would simply stop being
# walked here, and the matrix would score green on the very regression it exists
# to catch. The counts check below closes the other direction -- a name ADDED to
# the module set without being added here fails the set-equality assert.
#
# Cannibalistic joined the carnivore side on 2026-07-27 when the catalog stopped
# holding it back (it was already carnivore-only in the mod's own
# validateMutationForSid, which is why it lands here and not in GENERIC).
CARNI_ONLY = ["Hemomania", "Hematophagy", "Accelerated Prey Drive",
              "Hypermetabolic Inanition", "Osteophagic", "Augmented Tapetum",
              "Cannibalistic"]
HERBI_ONLY = ["Xerocole Adaptation", "Photosynthetic Regeneration",
              "Truculency", "Hypervigilance", "Tactile Endurance"]
# THE ACCEPT SIDE RUNS ON n2, the REJECT side stays on n1. Both on purpose:
# n2 takes every name, so an accept there is a clean read on the DIET rule alone
# (two of CARNI_ONLY -- Osteophagic and Augmented Tapetum -- are unlockables, and
# on n1 they would now be refused for a reason that has nothing to do with diet,
# which would quietly stop this matrix from testing diet at all). The reject side
# stays on n1 because the diet check runs FIRST there, so a wrong-diet name still
# has to answer "carnívoros"/"herbívoros" and never the unlockable copy -- that
# is the "both reasons, no confusing message" case, pinned right here.
for name in CARNI_ONLY:
    expect_error(f"{name} rejected on herbivore",
                 lambda n=name: mc.validate_slot_edit(row(cls="BP_Triceratops_C"), "n1", n), "carnívoros")
    expect_ok(f"{name} ok on carnivore",
              lambda n=name: mc.validate_slot_edit(row(), "n2", n), name)
for name in HERBI_ONLY:
    expect_error(f"{name} rejected on carnivore",
                 lambda n=name: mc.validate_slot_edit(row(), "n1", n), "herbívoros")
    expect_ok(f"{name} ok on herbivore",
              lambda n=name: mc.validate_slot_edit(row(cls="BP_Triceratops_C"), "n2", n), name)
v, _ = mc.validate_slot_edit(rex, "n2", "Photosynthetic Tissue")
check("Photosynthetic Tissue is ALL-diet in-game (ok on carnivore)", v == "Photosynthetic Tissue")
check("restriction counts 7 carni / 5 herbi",
      len(mc.CARNIVORE_ONLY) == 7 and len(mc.HERBIVORE_ONLY) == 5,
      f"carni={sorted(mc.CARNIVORE_ONLY)!r} herbi={sorted(mc.HERBIVORE_ONLY)!r}")
# ...and the matrix above really walked every one of them. Without this the hand
# lists could fall behind the module and the walk would shrink in silence.
check("the diet matrix walked EVERY restricted name, both ways",
      set(CARNI_ONLY) == set(mc.CARNIVORE_ONLY)
      and set(HERBI_ONLY) == set(mc.HERBIVORE_ONLY),
      f"carni_missing={sorted(set(mc.CARNIVORE_ONLY) - set(CARNI_ONLY))!r} "
      f"herbi_missing={sorted(set(mc.HERBIVORE_ONLY) - set(HERBI_ONLY))!r}")
v, _ = mc.validate_slot_edit(galli, "n2", "Nocturnal")
check("generic mut on gallimimus ok", v == "Nocturnal")
expect_error("unknown name rejected",
             lambda: mc.validate_slot_edit(rex, "n1", "Super Bite"), "reconocida")
# THE MOD-KNOWN NAME THIS CATALOG DOES NOT OFFER. Until 2026-07-27 that probe
# was "Cannibalistic"; the catalog widening turned it into an ordinary pickable
# name, so the probe moved to the only name left in that class. "Traumatic
# Thrombosis" IS in the running mod's known table (block [8] below, re-pinned
# from the live payload) and is the one name there that PICKABLE does not carry,
# because the game removed it in 0.21.720. Parked rows captured before that still
# hold it verbatim, so it is a real value and not an invented one.
expect_error("a mod-known name the catalog does not offer is rejected",
             lambda: mc.validate_slot_edit(rex, "n1", "Traumatic Thrombosis"),
             "reconocida")
expect_error("unknown slot rejected",
             lambda: mc.validate_slot_edit(rex, "x9", "Nocturnal"), "ranura")

print("[2] normalization (game camel-case == spaced display)")
v, _ = mc.validate_slot_edit(rex, "n1", "acceleratedpreydrive")
check("camel/lower input canonicalizes", v == "Accelerated Prey Drive")
check("canonical lookup camel", mc.canonical_mutation_name("AcceleratedPreyDrive") == "Accelerated Prey Drive")

print("[3] duplicates across all 16 slots")
r = row(muts="Hemomania|None|None|None", parent="None|Nocturnal|None|None")
expect_error("dup vs child slot rejected",
             lambda: mc.validate_slot_edit(r, "p1", "Hemomania"), "duplicadas")
expect_error("dup vs parent slot rejected (camel form)",
             lambda: mc.validate_slot_edit(r, "n2", "nocturnal"), "duplicadas")
r_camel = row(muts="AcceleratedPreyDrive|None|None|None")
expect_error("dup vs game-captured camel value rejected",
             lambda: mc.validate_slot_edit(r_camel, "n3", "Accelerated Prey Drive"), "duplicadas")
v, _ = mc.validate_slot_edit(r, "n1", "Hemomania")
check("re-writing same value into its own slot allowed (no-op path)", v == "Hemomania")
r_legacy_dupes = row(muts="Nocturnal|Nocturnal|None|None")
v, _ = mc.validate_slot_edit(r_legacy_dupes, "n3", "Wader")
check("pre-existing dupes in untouched slots do not block other edits", v == "Wader")

print("[4] the twelve inherited slots are gated on the entomb count")
# Owner ruling 2026-07-26, verbatim: "if they entomb once then they can edit 4
# elder slots, if twice then 8, if 3 times then 12". This REPLACES the
# 2026-07-12 ruling ("even if they arent entombed its fine it works") that
# elder_set_unlocked encoded as an unconditional True — that function is gone,
# and nothing may consult a helper that always says yes.
check("the always-true elder helper no longer exists",
      not hasattr(mc, "elder_set_unlocked"))
_MC_SRC_EARLY = open(os.path.join(os.path.dirname(__file__), "..", "mutation_catalog.py"),
                     encoding="utf-8").read()
_SERVER_SRC_EARLY = open(os.path.join(os.path.dirname(__file__), "..", "server.py"),
                         encoding="utf-8").read()
check("no caller anywhere still consults it",
      "elder_set_unlocked(" not in _MC_SRC_EARLY
      and "elder_set_unlocked(" not in _SERVER_SRC_EARLY
      and "def elder_set_unlocked" not in _MC_SRC_EARLY)

_INHERITED = ("p1", "p2", "p3", "p4", "ea1", "ea2", "ea3", "ea4",
              "eb1", "eb2", "eb3", "eb4")


def open_inherited(stacks):
    r = row(stacks=stacks)
    return [s for s in _INHERITED if mc.slot_unlocked(r, s)]


_P = list(_INHERITED[0:4])
_EA = list(_INHERITED[4:8])
_EB = list(_INHERITED[8:12])
# --- every rung, exactly ------------------------------------------------------
check("0 entombs -> none of the twelve", open_inherited(0) == [])
check("1 entomb -> the four parent slots and nothing else", open_inherited(1) == _P)
check("2 entombs -> parent + elder A (8)", open_inherited(2) == _P + _EA)
check("3 entombs -> all twelve", open_inherited(3) == _P + _EA + _EB)
check("4 entombs -> still all twelve, never more than 12", open_inherited(4) == _P + _EA + _EB)
check("99 entombs -> all twelve", open_inherited(99) == _P + _EA + _EB)
check("the owner's counts really are 4 / 8 / 12",
      [len(open_inherited(n)) for n in (0, 1, 2, 3)] == [0, 4, 8, 12])
check("the own slots are NOT on this ladder (0 entombs, full-grown Prime)",
      [s for s in ("n1", "n2", "n3", "n4") if mc.slot_unlocked(row(stacks=0), s)]
      == ["n1", "n2", "n3", "n4"])
check("and the inherited slots are NOT on the growth ladder",
      open_inherited(3) == _P + _EA + _EB
      and [s for s in _INHERITED
           if mc.slot_unlocked(row(stacks=3, growth=0.01), s)] == list(_INHERITED))

# --- the POST is the authority ------------------------------------------------
expect_error("writing into a parent slot at 0 entombs is rejected",
             lambda: mc.validate_slot_edit(row(stacks=0), "p1", "Nocturnal"), "enterrado")
expect_error("writing into elder A at 1 entomb is rejected",
             lambda: mc.validate_slot_edit(row(stacks=1), "ea1", "Nocturnal"), "enterrado")
expect_error("writing into elder B at 2 entombs is rejected",
             lambda: mc.validate_slot_edit(row(stacks=2), "eb4", "Nocturnal"), "enterrado")
expect_ok("writing into elder B at 3 entombs works",
          lambda: mc.validate_slot_edit(row(stacks=3), "eb4", "Nocturnal"), "Nocturnal")
expect_ok("writing into a parent slot at 1 entomb works",
          lambda: mc.validate_slot_edit(row(stacks=1), "p4", "Wader"), "Wader")
expect_error("a locked inherited slot answers with the LOCK, not the diet rule",
             lambda: mc.validate_slot_edit(row(cls="BP_Triceratops_C", stacks=0),
                                           "p1", "Hemomania"), "enterrado")
expect_error("a locked inherited slot answers with the LOCK, not the unknown-name rule",
             lambda: mc.validate_slot_edit(row(stacks=0), "ea2", "Totally Fake Mutation"),
             "enterrado")
check("the lock reason names the entombs needed and the ones it has",
      (mc.slot_lock(row(stacks=1), "ea1") or ("", ""))[1]
      == "Se desbloquea cuando el dinosaurio ha sido enterrado al menos 2 veces (ahora: 1).",
      repr(mc.slot_lock(row(stacks=1), "ea1")))
check("the one-entomb rung says vez, not veces",
      "al menos 1 vez (ahora: 0)" in (mc.slot_lock(row(stacks=0), "p1") or ("", ""))[1])
check("the inherited lock code is its own, not a growth code",
      mc.slot_lock(row(stacks=0), "p1")[0] == "entomb"
      and mc.slot_lock(row(stacks=2), "eb1")[0] == "entomb")

# --- CLEARING is always allowed and always free, on all sixteen ---------------
expect_ok("clearing a locked parent slot at 0 entombs is allowed",
          lambda: mc.validate_slot_edit(
              row(stacks=0, parent="Nocturnal|None|None|None"), "p1", "None"),
          "None", "Nocturnal")
expect_ok("clearing a locked elder slot at 0 entombs is allowed",
          lambda: mc.validate_slot_edit(
              row(stacks=0, elder="Wader|None|None|None|None|None|None|None"), "ea1", ""),
          "None", "Wader")
expect_ok('clearing a locked elder slot with the literal "none" is allowed',
          lambda: mc.validate_slot_edit(
              row(stacks=0, elder="None|Wader|None|None|None|None|None|None"), "eb1", "none"),
          "None", "Wader")
_clear_refused = []
for _sid in mc.SLOT_IDS:
    _r0 = {"id": 1, "dino_class": "BP_Tyrannosaurus_C", "growth": 0.0, "is_prime": 0,
           "elder_stacks": 0, "mutations": "Wader|Wader|Wader|Wader",
           "parent_mutations": "Wader|Wader|Wader|Wader",
           "elder_mutations": "|".join(["Wader"] * 8)}
    try:
        _v, _cur = mc.validate_slot_edit(_r0, _sid, "None")
        if _v != "None" or _cur != "Wader":
            _clear_refused.append((_sid, _v, _cur))
    except mc.MutationEditError as _e:
        _clear_refused.append((_sid, str(_e)))
check("EVERY one of the 16 slots can still be emptied on a fully locked dino",
      not _clear_refused, f"refused: {_clear_refused!r}")
# (that emptying any of them is also FREE is proven against the real charge
#  rule in block [11], which mirrors server.py's own ordering)

# --- an existing row keeps what it holds -------------------------------------
_kept = row(stacks=0, parent="Hemomania|Nocturnal|Wader|Featherweight")
check("a 0-entomb row still REPORTS everything stored in its parent slots",
      [mc.slots_from_row(_kept)[s] for s in _P]
      == ["Hemomania", "Nocturnal", "Wader", "Featherweight"])
check("...and its active_count still counts them", mc.active_count(_kept) == 4)
# Its counter says 0, but four real inherited mutations are SITTING in the row,
# so its own columns prove generation 1 and the family is open -- block [4c]
# owns that rule and the regression it fixes.
expect_ok("...and it CAN replace one, because its own columns prove generation 1",
          lambda: mc.validate_slot_edit(_kept, "p1", "Osteosclerosis"),
          "Osteosclerosis", "Hemomania")
expect_error("a row with nothing inherited at all still cannot write into p1",
             lambda: mc.validate_slot_edit(row(stacks=0), "p1", "Nocturnal"), "enterrado")
expect_ok("...and it can still empty one",
          lambda: mc.validate_slot_edit(_kept, "p1", "None"), "None", "Hemomania")
check("...and emptying it touches nothing else",
      mc.apply_slot_edit(_kept, "p1", "None")["parent_mutations"]
      == "None|Nocturnal|Wader|Featherweight")

# --- elder_stacks fails CLOSED on anything it cannot trust --------------------
# Parsed like is_prime_flag, and for the same reason: the column is INTEGER in
# the bot schema but a TEXT-typed one hands back "2" or "2.0", and int("2.0")
# raises. A bool is not a count; half an entomb is not a count.
_STACK_BAD = [None, "", "   ", "abc", -1, -0.5, 1.5, "1.5", True, False,
              float("nan"), float("inf"), float("-inf"), "1e400", "inf", "nan",
              [], {}, (), object(), "2,0", "dos", b"abc", "-1", "0x2"]
_bad_open = [(v, [s for s in _INHERITED
                  if mc.slot_unlocked({"growth": 1.0, "is_prime": 1, "elder_stacks": v}, s)])
             for v in _STACK_BAD]
check("every unreadable elder_stacks locks ALL twelve",
      not [x for x in _bad_open if x[1]],
      f"opened: {[x for x in _bad_open if x[1]]!r}")
check("a row with NO elder_stacks key at all locks all twelve",
      [s for s in _INHERITED
       if mc.slot_unlocked({"growth": 1.0, "is_prime": 1}, s)] == [])
check("an unreadable count gets its own code, not a growth one",
      mc.slot_lock({"elder_stacks": "abc"}, "p1")[0] == "entomb_unknown"
      and "enterrado" in mc.slot_lock({"elder_stacks": "abc"}, "p1")[1])
_STACK_GOOD = [(0, 0), (1, 1), (2, 2), (3, 3), (10, 10), ("0", 0), ("2", 2), ("3", 3),
               ("2.0", 2), (" 3 ", 3), (2.0, 2), (b"2", 2), (bytearray(b"3"), 3),
               (memoryview(b"1"), 1), (10 ** 400, 10 ** 400)]
_stack_wrong = [(k, mc.elder_stack_count({"elder_stacks": k}), want)
                for k, want in _STACK_GOOD
                if mc.elder_stack_count({"elder_stacks": k}) != want]
check("every form that really is a count is read as that count",
      not _stack_wrong, f"misread: {_stack_wrong!r}")
check("every unreadable form answers None (the fail-closed signal)",
      [v for v in _STACK_BAD if mc.elder_stack_count({"elder_stacks": v}) is not None] == [],
      str([v for v in _STACK_BAD if mc.elder_stack_count({"elder_stacks": v}) is not None]))
check("True is never read as 1 entomb",
      mc.elder_stack_count({"elder_stacks": True}) is None
      and mc.elder_stack_count({"elder_stacks": False}) is None)
check("a huge whole count opens the twelve rather than raising",
      [s for s in _INHERITED
       if mc.slot_unlocked({"growth": 1.0, "is_prime": 1, "elder_stacks": 10 ** 400}, s)]
      == list(_INHERITED))
_stack_raised = []
for _v in _STACK_BAD + [k for k, _w in _STACK_GOOD] + [10 ** 400, -(10 ** 400)]:
    try:
        mc.elder_stack_count({"elder_stacks": _v})
    except Exception as _e:                        # noqa: BLE001 - that IS the bug
        _stack_raised.append((_v, type(_e).__name__))
check("elder_stack_count never raises, whatever it is handed",
      not _stack_raised, f"raised: {_stack_raised!r}")
check("elder_stack_count survives a junk ROW",
      mc.elder_stack_count(None) is None and mc.elder_stack_count("nope") is None
      and mc.elder_stack_count(42) is None)
check("the ladder view is the owner's 4 / 8 / 12",
      [(r_["slot"], r_["requires_entombs"]) for r_ in mc.entomb_ladder_view()]
      == [("p1", 1), ("p2", 1), ("p3", 1), ("p4", 1),
          ("ea1", 2), ("ea2", 2), ("ea3", 2), ("ea4", 2),
          ("eb1", 3), ("eb2", 3), ("eb3", 3), ("eb4", 3)])
check("the ladder view names a generation the UI can group on",
      [r_["generation"] for r_ in mc.entomb_ladder_view()] == [1] * 4 + [2] * 4 + [3] * 4)

print("[4b] the two web lanes store NO entomb count, and the game still gets 0")
# THE LADDER GATES ON A COLUMN ONLY THE GAME FILLS. Two lanes build a parked row
# from picks made on this website -- /store/purchase-dino and the inventory ->
# vault move -- and neither has an entomb count to store, so save_parked stores
# int(_num(None)) = 0 and every one of those dinos arrives recorded at 0
# entierros. On the store lane that locked mutations the player had just PAID for
# (the "Linaje Parental" picker writes straight into parent_mutations), leaving
# only the free, irreversible Quitar on them.
#
# THE FIX FOR THAT IS AT READ TIME (block [4c]), NOT AT INSERT. A previous pass
# had both lanes store a DERIVED elder_stacks instead, and that was wrong for a
# reason the editor cannot see: this column is not an editor field. vault._run_
# redeem puts it in the restore command and the mod writes it to the pawn --
# main.full.lua :9910 SetElderReplicationStacks(r.stack_to_restore) and :9918
# a.ElderReplicationStacks = r.elder_stacks -- so a store purchase with one
# Linaje Parental pick was granted 1 in-game elder replication stack it never
# earned, an inventory move up to 3, permanently, the moment it was redeemed.
# (3 is not even reachable through the site's own entomb lane: server.py's
# MAX_ENTOMB_GEN is 2.) These checks pin that neither lane writes the column.
_EMPTY4 = "None|None|None|None"
_EMPTY8 = "|".join(["None"] * 8)


def _elder_col(**slots):
    """{"ea1": "Wader"} -> the 8-segment elder string, INTERLEAVED, built through
    the same _SLOT_MAP the mod's order lives in."""
    segs = ["None"] * 8
    for sid, val in slots.items():
        segs[mc.slot_column(sid)[1]] = val
    return mc.join_segments(segs)


_purchase_pd = _SERVER_SRC_EARLY.split('@api_router.post("/store/purchase-dino")', 1)[-1] \
    .split("pd = {", 1)[-1].split("\n    }", 1)[0]
# Split on the dict's own closing brace at its indentation -- the comments inside
# name routes like /inventory/dino/{id}/entomb, so splitting on a bare "}" ends
# the block early and the check silently passes on nothing.
_deploy_pd = _SERVER_SRC_EARLY.split('@api_router.post("/active-dino/deploy")', 1)[-1] \
    .split("pd = {", 1)[-1].split("\n    }", 1)[0]
check("the store purchase lane sets no elder_stacks on the row it builds",
      '"elder_stacks"' not in _purchase_pd and "mut_parent" in _purchase_pd,
      repr(_purchase_pd[-400:]))
check("...and neither does the inventory -> vault move",
      '"elder_stacks"' not in _deploy_pd and "parent_mutations" in _deploy_pd,
      repr(_deploy_pd[-400:]))
check("no lane derives an entomb count for a row any more",
      "elder_stacks_for_new_row" not in _SERVER_SRC_EARLY
      and "elder_stacks_for_new_row" not in _MC_SRC_EARLY
      and not hasattr(mc, "elder_stacks_for_new_row"))
check("no lane invents an elder_stacks for a row it builds",
      'elder_stacks": 1' not in _SERVER_SRC_EARLY
      and 'elder_stacks": mutation_catalog' not in _purchase_pd
      and 'elder_stacks": mutation_catalog' not in _deploy_pd)
# save_parked is the sink: a lane that passes no key stores 0, which is the
# truth about a dino the game never buried.
_VAULT_SRC = open(os.path.join(os.path.dirname(__file__), "..", "vault.py"),
                  encoding="utf-8").read()
check("save_parked turns a missing key into a stored 0",
      'int(_num(pd.get("elder_stacks")))' in _VAULT_SRC)
check("the redeem still sends the STORED column and nothing derived",
      'int(_num(parked.get("elder_stacks")))' in _VAULT_SRC
      and "effective_elder_stacks" not in _VAULT_SRC
      and "lineage_generation" not in _VAULT_SRC)

# --- and the editor problem is still solved, on the row each lane really builds
_STORE_PARENT = "Wader|None|None|None"
_store_row = {"id": 1, "dino_class": "BP_Stegosaurus_C", "growth": 0.75,
              "is_prime": 1, "mutations": "Hydrodynamic|None|None|None",
              "parent_mutations": _STORE_PARENT, "elder_mutations": "",
              "elder_stacks": 0}
expect_ok("a bought parent mutation can be CHANGED, not only thrown away",
          lambda: mc.validate_slot_edit(_store_row, "p1", "Nocturnal"),
          "Nocturnal", "Wader")
check("a store dino opens its four heredadas and NOTHING else",
      [s for s in _INHERITED if mc.slot_unlocked(_store_row, s)] == _P)
check("...off a stored 0, with no key on the row moved at all",
      _store_row["elder_stacks"] == 0)
_bare_store = dict(_store_row, parent_mutations=_EMPTY4)
check("a store dino sold with no Linaje Parental keeps all twelve shut",
      [s for s in _INHERITED if mc.slot_unlocked(_bare_store, s)] == [])
# WHAT THE REVERT COSTS, stated out loud rather than hidden: the legacy inventory
# editor lets a Prime fill Anciano A at entomb_count >= 1 and B at >= 2, and the
# move stores no count, so those picks arrive in the vault locked. They were
# locked before this whole change too (the 2026-07-26 ladder is what shut them),
# nothing regressed, and the alternative -- storing the count -- is the in-game
# grant above. Elder content is never read as proof either, for the reason in
# [4c]. This is pinned so nobody "fixes" it by reaching for the column again.
_moved = {"id": 1, "dino_class": "BP_Stegosaurus_C", "growth": 0.75, "is_prime": 1,
          "mutations": _EMPTY4, "parent_mutations": _EMPTY4,
          "elder_mutations": _elder_col(ea1="Wader"), "elder_stacks": 0}
check("an Anciano pick moved in at a stored 0 stays locked, and is not proof",
      not mc.slot_unlocked(_moved, "ea1")
      and [s for s in _INHERITED if mc.slot_unlocked(_moved, s)] == [])
expect_ok("...but it can still be emptied, free",
          lambda: mc.validate_slot_edit(_moved, "ea1", "None"), "None", "Wader")

print("[4c] a row's own PARENT column proves the lineage step, at READ time")
# THE REGRESSION, verbatim: a parked row with elder_stacks 0 whose
# parent_mutations column already holds a real mutation got ZERO inherited slots
# open. A player who bought a dino with a "Linaje Parental" before 2026-07-26 has
# four parent mutations he PAID for, and the editor told him all four were locked
# until the dino had been entombed once. Every row the SITE built is in that
# state -- neither web lane has an entomb count to store (block [4b]).
#
# READ-TIME, AND ONLY READ-TIME. elder_stacks is also consumed by the redeem
# lane: vault._run_redeem hands it to the mod, which writes
# ElderReplicationStacks. Rewriting stored counters would change what the GAME
# receives on redeem -- a behaviour change nobody asked for, and not reversible.
# So the derivation lives in _entomb_state, the SINGLE place slot_lock reads the
# count, and the "it derives, it never writes" block below is what pins that.
#
# THE PARENT COLUMN ONLY, AND NEVER PAST GENERATION 1. This started out reading
# the elder column too -- elder A as generation 2, elder B as 3, ENTOMB_LADDER
# backwards. That is not how the mod lays a dino out. The FIRST entomb does not
# shift a generation, it FLATTENS: LaIslaNublarRedeemedEntombBuildTarget
# (main.full.lua :2935-3016) takes layoutMode "first_entomb_flatten" whenever the
# elder column is still empty and writes the dino's OWN mutations into
# ElderMutationSlot{i}A and its PARENT ones into {i}B (mapped[ai]=n, mapped[bi]=p),
# leaves parentTarget entirely "None", and sets ElderReplicationStacks to 1. The
# park capture (:14420-14428) reads those back in the same order. So elder
# content means ONE entomb, and reading it as a generation gave every genuinely
# entombed dino all twelve slots -- 12 at one entomb where the ladder grants 4,
# 12 at two where it grants 8. _MOD_FIRST_ENTOMB below is that layout, ported,
# and it is the oracle for the whole rule.


def _mod_first_entomb(own, parent):
    """LaIslaNublarRedeemedEntombBuildTarget's first_entomb_flatten branch,
    ported: mapped[(i-1)*2+1] = own_i, mapped[(i-1)*2+2] = parent_i. The parent
    column it leaves behind is empty (parentTarget is never assigned in that
    branch) and the normal slots are cleared."""
    segs = ["None"] * 8
    for i in range(4):
        segs[i * 2] = (own[i] if i < len(own) else "None") or "None"
        segs[i * 2 + 1] = (parent[i] if i < len(parent) else "None") or "None"
    return mc.join_segments(segs)


def _open_inh(r):
    return [s for s in _INHERITED if mc.slot_unlocked(r, s)]


_gen1 = row(stacks=0, parent="Hemomania|None|None|None")
check("stacks 0 + a real mutation in the parent column -> the four heredadas open",
      _open_inh(_gen1) == _P, repr(_open_inh(_gen1)))
check("...and Anciano A and B stay shut on that very same row",
      all(not mc.slot_unlocked(_gen1, s) for s in _EA + _EB))
check("every position in the parent family proves it, not just the first",
      [mc.lineage_generation(p) for p in
       ("Wader|None|None|None", "None|Wader|None|None",
        "None|None|Wader|None", "None|None|None|Wader")] == [1, 1, 1, 1])
check("nothing inherited proves nothing",
      mc.lineage_generation("") == 0 and mc.lineage_generation(_EMPTY4) == 0)
check("the derivation tops out at generation 1, by construction",
      mc.MAX_DERIVED_GENERATION == 1
      and max(mc.lineage_generation(p) for p in
              ("Wader|Nocturnal|Hemomania|Hydrodynamic",)) == 1)

# --- THE ELDER COLUMN IS NOT PROOF -------------------------------------------
_elder_proved = []
for _sid in _EA + _EB:
    _r = row(stacks=0, parent=_EMPTY4, elder=_elder_col(**{_sid: "Wader"}))
    if _open_inh(_r) or mc.effective_elder_stacks(_r) != 0:
        _elder_proved.append((_sid, _open_inh(_r), mc.effective_elder_stacks(_r)))
check("a value in ANY elder segment proves nothing at all",
      not _elder_proved, f"{_elder_proved!r}")
check("lineage_generation takes no elder argument to be handed by mistake",
      mc.lineage_generation.__code__.co_argcount == 1)
# The measured case, on the mod's own layout: a Rex with two OWN mutations and
# one PARENT mutation, entombed ONCE.
_E1 = _mod_first_entomb(["Accelerated Prey Drive", "Advanced Gestation"],
                        ["Augmented Tapetum"])
check("the ported layout really does put an own mutation in ea1 and a parent one in eb1",
      mc.split_segments(_E1, 8)[mc.slot_column("ea1")[1]] == "Accelerated Prey Drive"
      and mc.split_segments(_E1, 8)[mc.slot_column("eb1")[1]] == "Augmented Tapetum")
_once = row(stacks=1, parent=_EMPTY4, elder=_E1)
check("a dino the game entombed ONCE gets the four the owner ruled, not twelve",
      _open_inh(_once) == _P, repr(_open_inh(_once)))
_twice = row(stacks=2, parent="Hemomania|Nocturnal|None|None", elder=_E1)
check("...entombed TWICE gets eight, not twelve",
      _open_inh(_twice) == _P + _EA, repr(_open_inh(_twice)))
_thrice = row(stacks=3, parent="Hemomania|None|None|None", elder=_E1)
check("...entombed three times gets all twelve",
      _open_inh(_thrice) == _P + _EA + _EB)
check("the ladder the owner ruled is what a real dino walks: 0/4/8/12",
      [len(_open_inh(row(stacks=n, parent=_EMPTY4 if n < 2 else "Hemomania|None|None|None",
                         elder=_E1 if n else "")))
       for n in (0, 1, 2, 3)] == [0, 4, 8, 12])

# --- it can only ever RAISE the count ----------------------------------------
check("stacks 3 with entirely empty columns is still all twelve (never lowered)",
      _open_inh(row(stacks=3)) == _P + _EA + _EB
      and _open_inh(row(stacks=3, parent=_EMPTY4, elder=_EMPTY8)) == _P + _EA + _EB)
_never_lowered = [(n, mc.effective_elder_stacks(row(stacks=n, parent=p, elder=e)))
                  for n in (0, 1, 2, 3, 9)
                  for p, e in (("", ""), (_EMPTY4, _EMPTY8),
                               ("Hemomania|None|None|None", ""),
                               ("", _elder_col(ea1="Wader")),
                               ("", _elder_col(eb1="Wader")))]
check("the derivation only ever raises the count, never lowers it",
      all(eff >= n for n, eff in _never_lowered), repr(_never_lowered))
check("a recorded 2 with a parent-only column stays 2, it does not fall to 1",
      mc.effective_elder_stacks(row(stacks=2, parent="Wader|None|None|None")) == 2
      and _open_inh(row(stacks=2, parent="Wader|None|None|None")) == _P + _EA)
check("and it never raises one past the rung it can prove",
      max(mc.effective_elder_stacks(row(stacks=0, parent=p, elder=e))
          for p in ("Wader|Nocturnal|Hemomania|Hydrodynamic", _EMPTY4)
          for e in (_EMPTY8, _E1, _elder_col(eb4="Wader"))) == 1)

# --- junk is NOT proof: recognition is an ALLOWLIST ---------------------------
# A segment counts only when canonical_mutation_name resolves it to one of the 36
# catalog names (camel-case and spacing drift included). A bare `!= "None"` test
# would let "0", "null", "-", a truncated name or a stray fragment of another
# column open four PAID ranuras on a row that is merely corrupt -- the one
# fail-OPEN branch a module that fails closed everywhere else cannot have (the
# same lesson as is_prime_flag's allowlist).
#
# ACCEPTED COST, stated out loud: a mod-known name this catalog does not pick
# from ("Traumatic Thrombosis") and the mod-BANNED ones ("Melorheostosis",
# "Stereopsis") do not prove a generation either. That is the conservative
# side and it costs the player nothing usable -- validate_slot_edit refuses to
# write any of those names into any slot anyway -- while the store lane
# canonicalizes before writing, so nothing the SITE delivers can miss.
#
# "Cannibalistic" was the mod-known-not-pickable probe here until 2026-07-27 and
# is now an ordinary PICKABLE name, so it really does prove a generation and had
# to leave this list. Its CLASS of coverage did not: "Traumatic Thrombosis" is
# the one mod-known name PICKABLE still does not carry, and a second genuinely
# banned name went in beside Melorheostosis so the banned class did not thin out.
_JUNK = ["None", "none", "NONE", "", "   ", "0", "null", "NULL", "-", "n/a",
         "undefined", "false", "Super Bite", "Hemo", "omania", "Stereopsis",
         "Traumatic Thrombosis", "Melorheostosis", "|", "??", "[]", "{}",
         "True", "1", "BP_Tyrannosaurus_C"]
_junk_opened = []
for _j in _JUNK:
    for _label, _r in (("parent", row(stacks=0, parent="|".join([_j] * 4))),
                       ("elder", row(stacks=0, elder="|".join([_j] * 8)))):
        if _open_inh(_r):
            _junk_opened.append((_label, _j, _open_inh(_r)))
check("junk that is not a recognised mutation proves NOTHING",
      not _junk_opened, f"opened: {_junk_opened!r}")
check("...and every one of those rows still reads as zero entierros",
      {mc.effective_elder_stacks(row(stacks=0, parent="|".join([j] * 4)))
       for j in _JUNK} == {0})
check("a real name in ANY spelling the game or the mod writes still proves it",
      [mc.lineage_generation(n) for n in
       ("Hemomania|None|None|None", "AcceleratedPreyDrive|None|None|None",
        " accelerated prey drive |None|None|None", "wader|None|None|None",
        "Reniculate_Kidneys|None|None|None")] == [1, 1, 1, 1, 1])
check("the proof test really is the catalog lookup, not a truthiness test",
      mc._proves_lineage("Wader") is True
      and mc._proves_lineage("Traumatic Thrombosis") is False
      and mc._proves_lineage("None") is False and mc._proves_lineage("") is False)

# --- fail closed on BOTH halves ----------------------------------------------
_bad_and_proven = row(stacks="abc", parent="Hemomania|None|None|None")
check("an unreadable count contributes 0 while the parent column still counts",
      _open_inh(_bad_and_proven) == _P)
check("...and the slots the column does NOT reach keep the unreadable copy",
      mc.slot_lock(_bad_and_proven, "ea1") == ("entomb_unknown", mc.LOCK_ENTOMB_UNREADABLE),
      repr(mc.slot_lock(_bad_and_proven, "ea1")))
_bad_and_bare = row(stacks="abc")
check("an unreadable count with nothing proven still locks all twelve",
      _open_inh(_bad_and_bare) == []
      and all(mc.slot_lock(_bad_and_bare, s)[0] == "entomb_unknown" for s in _INHERITED))
_col_opened = []
for _v in (None, 5, [], {}, object(), b"Hemomania|None", True, 1.5, ("Wader",)):
    _r = {"growth": 1.0, "is_prime": 1, "elder_stacks": 0,
          "parent_mutations": _v, "elder_mutations": _v}
    try:
        _o = _open_inh(_r)
    except Exception as _e:                        # noqa: BLE001 - that IS the bug
        _o = [type(_e).__name__]
    if _o:
        _col_opened.append((_v, _o))
check("an unreadable COLUMN contributes 0 and never raises",
      not _col_opened, f"{_col_opened!r}")
_lru_raised = []
for _v in ([], {}, set(), {"a": 1}, [["x"]], bytearray(b"Wader")):
    try:
        mc.lineage_generation(_v)
    except Exception as _e:                        # noqa: BLE001
        _lru_raised.append((type(_v).__name__, type(_e).__name__))
check("an unhashable column never reaches the memo (lru_cache raises TypeError)",
      not _lru_raised, f"{_lru_raised!r}")
_gen_raised = []
for _bad in (None, 5, [], {}, object(), b"Wader|None", True, "Wader"):
    try:
        _g = mc.lineage_generation(_bad)
        if not isinstance(_g, int) or _g < 0 or _g > mc.MAX_DERIVED_GENERATION:
            _gen_raised.append((_bad, _g))
    except Exception as _e:                        # noqa: BLE001 - that IS the bug
        _gen_raised.append((_bad, type(_e).__name__))
check("lineage_generation never raises and never leaves 0..1",
      not _gen_raised, f"{_gen_raised!r}")
_state_raised = []
for _junk_row in (None, "not a row", 42, [], object(), {"elder_stacks": object()}):
    try:
        _h, _rec = mc._entomb_state(_junk_row)
        if not isinstance(_h, int) or _h < 0 or _rec is not None:
            _state_raised.append((_junk_row, _h, _rec))
    except Exception as _e:                        # noqa: BLE001
        _state_raised.append((_junk_row, type(_e).__name__))
check("_entomb_state never raises and fails closed on a junk row",
      not _state_raised, f"{_state_raised!r}")
check("effective_elder_stacks never raises on a junk row either",
      [mc.effective_elder_stacks(v) for v in (None, "nope", 42, [], object())]
      == [0] * 5)

# --- the reason a player reads stays TRUE ------------------------------------
# THE DERIVED COUNT IS NEVER A NUMBER THE PLAYER SEES. It can sit one above the
# truth -- a store dino that was never buried proves 1 -- so every sentence about
# entierros quotes the RECORDED count, and the GET publishes that same recorded
# count. A slot the column proved is simply open, with nothing to explain.
_lm_gen1 = mc.slot_lock_map(_gen1)
check("a slot the column proved is simply OPEN, with nothing to explain",
      mc.slot_lock(_gen1, "p1") is None
      and _lm_gen1["p1"]["locked"] is False and _lm_gen1["p1"]["code"] is None
      and _lm_gen1["p1"]["reason"] is None
      and _lm_gen1["p1"]["requires_entombs"] == 1, repr(_lm_gen1["p1"]))
check("a slot still short names the REAL requirement and the REAL entierro count",
      mc.slot_lock(_gen1, "ea1")
      == ("entomb", "Se desbloquea cuando el dinosaurio ha sido enterrado al menos "
                    "2 veces (ahora: 0)."), repr(mc.slot_lock(_gen1, "ea1")))
check("the derived count is never quoted as an entierro count",
      "(ahora: 1)" not in mc.slot_lock(_gen1, "ea1")[1]
      and "(ahora: 1)" not in mc.slot_lock(_gen1, "eb1")[1]
      and mc.effective_elder_stacks(_gen1) == 1
      and mc.elder_stack_count(_gen1) == 0)
check("a row with nothing proven still reads the honest zero",
      "al menos 1 vez (ahora: 0)" in mc.slot_lock(row(stacks=0), "p1")[1])
check("the GET publishes the RECORDED count, not the derived one",
      "mutation_catalog.elder_stack_count(row)" in _SERVER_SRC_EARLY
      and "effective_elder_stacks" not in _SERVER_SRC_EARLY)
check("a genuinely entombed dino still reads its own real count",
      mc.elder_stack_count(_once) == 1 and mc.elder_stack_count(_twice) == 2)

# --- a slot the column did NOT prove behaves exactly as it did before --------
expect_error("a locked Anciano A slot still refuses a write on a gen-1 row",
             lambda: mc.validate_slot_edit(_gen1, "ea1", "Nocturnal"), "al menos 2")
expect_error("...and answers with the LOCK, not the diet or unknown-name rule",
             lambda: mc.validate_slot_edit(_gen1, "eb1", "Totally Fake Mutation"),
             "al menos 3")
expect_ok("a slot the column DID prove takes a real write",
          lambda: mc.validate_slot_edit(_gen1, "p2", "Nocturnal"), "Nocturnal", "None")
check("a parent slot HOLDING a recognised mutation is open, it proves itself",
      all(mc.slot_unlocked(row(stacks=0, parent=_pc), _sid)
          for _sid, _pc in (("p1", "Wader|None|None|None"),
                            ("p4", "None|None|None|Wader"))))
_stuck = row(stacks=0, parent=_EMPTY4, elder=_elder_col(ea2="Traumatic Thrombosis"))
check("a closed inherited slot can still be holding an unrecognised value",
      not mc.slot_unlocked(_stuck, "ea2") and _open_inh(_stuck) == [])
expect_ok("...and emptying that one is still allowed",
          lambda: mc.validate_slot_edit(_stuck, "ea2", "None"),
          "None", "Traumatic Thrombosis")
expect_error("...but it still cannot be written into",
             lambda: mc.validate_slot_edit(_stuck, "ea2", "Nocturnal"), "al menos 2")

# --- clearing the LAST proof is irreversible, so it is flagged ---------------
# THE TRAP THE DERIVATION CREATED. p1 is open ONLY because it holds a mutation,
# so the free one-press "Quitar (gratis)" takes the proof with it and shuts all
# four heredadas -- and re-adding is then refused, because the ladder wants an
# entierro the dino has never had. Before the derivation those slots were LOCKED,
# so the very same press went down the guarded two-press path with its warning;
# the derivation moved the irreversible case into the UNGUARDED one. Clearing
# stays allowed and free (that rule never bends); what the backend owes the UI is
# the fact that THIS clear cannot be walked back.
_lm_gen1 = mc.slot_lock_map(_gen1)
check("the slot holding the only proof is flagged as a closing clear",
      _lm_gen1["p1"]["clear_closes"] is True)
check("...and an empty sibling in the same family is not",
      [_lm_gen1[s]["clear_closes"] for s in ("p2", "p3", "p4")] == [False] * 3)
check("...and neither is any own slot, on any row",
      [mc.slot_lock_map(row(stacks=0, muts="Hemomania|None|None|None",
                            parent="Wader|None|None|None"))[s]["clear_closes"]
       for s in ("n1", "n2", "n3", "n4")] == [False] * 4)
_two_proofs = row(stacks=0, parent="Wader|Nocturnal|None|None")
check("with two proofs in the family, neither clear closes anything",
      [mc.slot_lock_map(_two_proofs)[s]["clear_closes"] for s in _P] == [False] * 4)
check("...and once one is gone the remaining one IS flagged",
      mc.slot_lock_map(row(stacks=0, parent="Wader|None|None|None"))["p1"]["clear_closes"]
      is True)
check("a row whose stored counter already carries the family is never flagged",
      [mc.slot_lock_map(row(stacks=1, parent="Wader|None|None|None"))[s]["clear_closes"]
       for s in _P] == [False] * 4
      and [mc.slot_lock_map(_thrice)[s]["clear_closes"] for s in _INHERITED]
      == [False] * 12)
check("a locked slot is never flagged either, it already asks twice",
      [mc.slot_lock_map(row(stacks=0))[s]["clear_closes"] for s in _INHERITED]
      == [False] * 12)
# The flag has to be TRUE, and the outcome it predicts has to be REAL: clear it
# and the family really does shut, and the re-add really is refused.
_after = mc.apply_slot_edit(_gen1, "p1", "None")
_cleared = dict(_gen1, **_after)
check("the flag predicts a real outcome: the family really does shut",
      _open_inh(_cleared) == [] and mc.effective_elder_stacks(_cleared) == 0)
expect_error("...and putting it back really is refused afterwards",
             lambda: mc.validate_slot_edit(_cleared, "p1", "Hemomania"), "al menos 1")
expect_ok("clearing that slot is still ALLOWED and still free, flag or not",
          lambda: mc.validate_slot_edit(_gen1, "p1", "None"), "None", "Hemomania")
_flag_raised = []
for _bad_slot in (None, 42, [], "nope", "n1", object()):
    try:
        _f = mc.slot_clear_closes(_gen1, _bad_slot)
        if not isinstance(_f, bool):
            _flag_raised.append((_bad_slot, _f))
    except Exception as _e:                        # noqa: BLE001
        _flag_raised.append((_bad_slot, type(_e).__name__))
for _bad_row in (None, "not a row", 42, [], object()):
    try:
        _f = mc.slot_clear_closes(_bad_row, "p1")
        if not isinstance(_f, bool):
            _flag_raised.append((_bad_row, _f))
    except Exception as _e:                        # noqa: BLE001
        _flag_raised.append((_bad_row, type(_e).__name__))
check("slot_clear_closes never raises, on any row or any slot id",
      not _flag_raised, f"{_flag_raised!r}")
# The save has to carry the new map back, or the page keeps the one the GET sent
# and offers the unguarded press on the next slot in the family.
_POST_BLOCK = _SERVER_SRC_EARLY.split("async def me_vault_mutations_set", 1)[-1][:6000]
check("the mutation save returns the recomputed locks with the new slots",
      '"slot_locks": mutation_catalog.slot_lock_map(updated)' in _POST_BLOCK
      and '"elder_stacks": mutation_catalog.elder_stack_count(updated)' in _POST_BLOCK)

# --- the own ladder is untouched ---------------------------------------------
# Re-walked with the inherited columns FULL, which is the exact row shape the
# derivation now reads: proving a lineage must not move a single own rung.
_OWN = ["n1", "n2", "n3", "n4"]
_WALK = {(0.244, False): [], (0.244, True): [],
         (0.25, False): ["n1"], (0.25, True): ["n1"],
         (0.494, False): ["n1"], (0.494, True): ["n1"],
         (0.50, False): ["n1", "n2"], (0.50, True): ["n1", "n2"],
         (0.744, False): ["n1", "n2"], (0.744, True): ["n1", "n2"],
         (0.75, False): ["n1", "n2", "n3"], (0.75, True): ["n1", "n2", "n3", "n4"]}
_walk_bad = []
for (_g, _pr), _want in _WALK.items():
    for _label, _p, _e in (("bare", "", ""),
                           ("lineage proven", "Hemomania|None|None|None",
                            _elder_col(eb1="Wader")),
                           ("entombed thrice", "Hemomania|None|None|None", _E1)):
        _r = row(growth=_g, is_prime=1 if _pr else 0, stacks=0, parent=_p, elder=_e)
        _got = [s for s in _OWN if mc.slot_unlocked(_r, s)]
        if _got != _want:
            _walk_bad.append((_g, _pr, _label, _got, _want))
check("the own ladder walks .244/.25/.494/.50/.744/.75 the same, Prime or not, "
      "lineage or not", not _walk_bad, f"{_walk_bad!r}")
check("...and a fully proven lineage still cannot buy the Prime-only fourth slot",
      not mc.slot_unlocked(
          row(growth=1.0, is_prime=0, stacks=0, parent="Wader|None|None|None",
              elder=_elder_col(eb1="Hemomania")), "n4"))

# --- it DERIVES, it never WRITES ---------------------------------------------
# The stored counter reaches the game through the redeem (ElderReplicationStacks),
# so a read that rewrote it would change what the mod receives. The memo is keyed
# on the column STRING, so it cannot touch the row it was asked about either.
import copy as _copy  # noqa: E402

_probe = row(stacks=0, parent="Hemomania|None|None|None", elder=_elder_col(ea1="Wader"))
_before = _copy.deepcopy(_probe)
mc.slot_lock_map(_probe)
mc.unlocked_slots(_probe)
mc.effective_elder_stacks(_probe)
mc.slot_clear_closes(_probe, "p1")
mc.slots_from_row(_probe)
mc.validate_slot_edit(_probe, "p2", "Nocturnal")
check("reading the lock leaves the row byte-identical (no backfill, no memo key)",
      _probe == _before and _probe["elder_stacks"] == 0, repr(_probe))
check("...and adds no key of its own to it", set(_probe) == set(_before))
check("nothing in the module writes elder_stacks back onto a row",
      "row[\"elder_stacks\"]" not in _MC_SRC_EARLY
      and 'row["elder_stacks"] =' not in _MC_SRC_EARLY
      and '["elder_stacks"] =' not in _MC_SRC_EARLY)
check("the redeem lane still sends the STORED column, untouched by any of this",
      'int(_num(parked.get("elder_stacks")))' in _VAULT_SRC
      and "effective_elder_stacks" not in _VAULT_SRC)

# --- cheap: the row's column is PARSED once per GET, not sixteen times -------
# MISSES is the number that matters -- a miss splits the column and walks it, a
# hit is a dict lookup on a string already in hand. slot_lock asks per slot and
# the clear flag asks again on the open inherited ones, so the lookup count sits
# above 12; the parse count must not.
mc._lineage_generation_cached.cache_clear()
mc.slot_lock_map(row(stacks=3, parent="Hemomania|None|None|None"))
_ci = mc._lineage_generation_cached.cache_info()
check("one lock map over 16 slots parses the row's column exactly once",
      _ci.misses == 1, repr(_ci))
check("the memo is bounded, so a junk column cannot fill it without limit",
      mc._lineage_generation_cached.cache_info().maxsize == 512)
check("only the twelve inherited slots consult it at all, at most twice each",
      12 <= _ci.misses + _ci.hits <= 24, repr(_ci))
# The clear flag costs at most one MORE parse per row, and only on a row the
# derivation actually raised: every other slot short-circuits before it splits
# anything, and a row whose stored counter already carries the family never
# reaches the flag at all.
mc._lineage_generation_cached.cache_clear()
mc.slot_lock_map(row(stacks=0, parent="Hemomania|None|None|None"))
_ci2 = mc._lineage_generation_cached.cache_info()
check("the clear flag adds one parse on a derived row, not sixteen",
      _ci2.misses == 2, repr(_ci2))
mc._lineage_generation_cached.cache_clear()
mc.slot_lock_map(row(stacks=3))
check("...and none at all on a row the stored counter already carries",
      mc._lineage_generation_cached.cache_info().misses == 1)

print("[5] slot encoding / apply")
r = row(muts="Titan|None|Feral", elder="A|B|C|D|E|F|G|H", stacks=3)
slots = mc.slots_from_row(r)
check("short child string pads to 4", slots["n4"] == "None" and slots["n1"] == "Titan")
# The elder column is INTERLEAVED (1A,1B,2A,2B,...), so on "A|B|...|H" ea2 is
# segment 2 ("C") and eb1 is segment 1 ("B"). Until 2026-07-26 this line pinned
# the blocked reading (ea2 == "B", eb1 == "E") and was green, because it tested
# mutation_catalog against itself. Block [5b] below is the real oracle.
check("elder pairs are interleaved, not blocked",
      slots["ea1"] == "A" and slots["eb1"] == "B" and slots["ea2"] == "C"
      and slots["eb4"] == "H",
      repr({k: slots[k] for k in ("ea1", "eb1", "ea2", "eb4")}))
out = mc.apply_slot_edit(r, "p3", "Wader")
check("apply pads parent to full 4 segments", out["parent_mutations"] == "None|None|Wader|None")
check("apply keeps other columns normalized",
      out["mutations"] == "Titan|None|Feral|None" and out["elder_mutations"] == "A|B|C|D|E|F|G|H")
out2 = mc.apply_slot_edit(r, "eb2", "None")
check("clear elder B2 -> segment index 3 (2B) None",
      out2["elder_mutations"] == "A|B|C|None|E|F|G|H", out2["elder_mutations"])
check("active_count counts non-None across 16",
      mc.active_count(r) == 2 + 8)

print("[5b] the elder mapping, asserted against THE MOD'S OWN ORDERING")
# WHY THIS BLOCK EXISTS: the check it replaces compared mutation_catalog to
# mutation_catalog, so six of the eight elder labels pointed at the wrong game
# property for two weeks and every run was green. The oracle here is the mod —
# the only decoder that reaches the game — reimplemented from its own loop and
# cross-checked against its source text, never imported from the module under
# test.
#
# The mod walks `for i = 1,4 do for si,suf in ipairs({"A","B"})` and indexes
# (i-1)*2+si, at main.full.lua:437-443 (capture), :7679-7694 (ApplyElder-
# Mutations, the sole game-facing decoder) and :14420-14428 (telemetry), with
# the canonical name table at :197-202 written out in that same order.
MOD_ELDER_ORDER = tuple(                      # transcribed from that loop
    f"ElderMutationSlot{i}{suf}" for i in (1, 2, 3, 4) for suf in ("A", "B"))
MOD_PROP_FOR = {**{f"ea{n}": f"ElderMutationSlot{n}A" for n in (1, 2, 3, 4)},
                **{f"eb{n}": f"ElderMutationSlot{n}B" for n in (1, 2, 3, 4)}}


def mod_encode(props: dict) -> str:
    """What the MOD stores after capturing a pawn: c[(i-1)*2+si]."""
    segs = [None] * 8
    for i in (1, 2, 3, 4):
        for si, suf in enumerate(("A", "B"), start=1):
            segs[(i - 1) * 2 + si - 1] = props.get(f"ElderMutationSlot{i}{suf}", "None")
    return "|".join(segs)


def mod_decode(estr: str) -> dict:
    """What the MOD writes back onto the pawn: the same walk, idx 1..8."""
    parts = (estr or "").split("|")
    out, idx = {}, 0
    for i in (1, 2, 3, 4):
        for suf in ("A", "B"):
            out[f"ElderMutationSlot{i}{suf}"] = parts[idx] if idx < len(parts) else "None"
            idx += 1
    return out


# The transcription above is checked against the mod source itself, so a
# re-ordered mod cannot leave this file quietly asserting the old order.
_MOD_LUA = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                        "mod", "lua", "LaIslaNublarDataMod", "Scripts", "main.full.lua")
if os.path.exists(_MOD_LUA):
    _lua = open(_MOD_LUA, encoding="utf-8", errors="ignore").read()
    _tbl = re.search(r"LAISLANUBLAR_MUTATION_ELDER_SLOT_NAMES\s*=\s*\{(.*?)\}", _lua, re.S)
    _names = tuple(re.findall(r'"(ElderMutationSlot\d[AB])"', _tbl.group(1) if _tbl else ""))
    check("the mod's own canonical name table really is 1A,1B,2A,2B,3A,3B,4A,4B",
          _names == MOD_ELDER_ORDER, f"{_names!r}")
    check("the mod's game-facing decoder really walks for-i / for-suffix",
          re.search(r'for i = 1, 4 do\s*\n\s*for _, suffix in ipairs\(\{"A", "B"\}\)', _lua)
          is not None)
    # both captures and all three entomb builders, whitespace-tolerantly
    _idx_sites = len(re.findall(r"\(i\s*-\s*1\)\s*\*\s*2\s*\+\s*(?:si|1)\b", _lua))
    check("the mod really indexes the elder pairs as (i-1)*2+si everywhere",
          _idx_sites >= 5, f"{_idx_sites} sites")
    check("the mod's propFor is label-correct (ea{N} -> {N}A, eb{N} -> {N}B)",
          'if a then return "ElderMutationSlot"..a.."A" end' in _lua
          and 'if b then return "ElderMutationSlot"..b.."B" end' in _lua)
else:
    check("mod source available to cross-check the transcription", False, _MOD_LUA)

# DIRECTION 1 — WRITE. A value the web puts in ea2 has to come out of the mod's
# decoder as ElderMutationSlot2A, the property the label claims.
_write_wrong = []
for _sid, _prop in MOD_PROP_FOR.items():
    _col = mc.apply_slot_edit(row(stacks=3), _sid, "Wader")["elder_mutations"]
    _seen = [p for p, v in mod_decode(_col).items() if v == "Wader"]
    if _seen != [_prop]:
        _write_wrong.append((_sid, _prop, _seen))
check("a write to each elder slot id lands in the property the mod calls by that name",
      not _write_wrong, f"(slot, expected, mod actually got) {_write_wrong!r}")

# DIRECTION 2 — READ. A string the MOD captured has to decode back to the same
# labels the mod would give it.
_read_wrong = []
for _sid, _prop in MOD_PROP_FOR.items():
    _captured = mod_encode({_prop: "Wader"})
    _slots = mc.slots_from_row(row(stacks=3, elder=_captured))
    _seen = [s for s in ("ea1", "ea2", "ea3", "ea4", "eb1", "eb2", "eb3", "eb4")
             if _slots[s] == "Wader"]
    if _seen != [_sid]:
        _read_wrong.append((_prop, _sid, _seen))
check("a mod-captured string decodes to the labels the mod would give it",
      not _read_wrong, f"(property, expected slot, web actually read) {_read_wrong!r}")

# ROUND TRIP — all eight at once, both ways, with distinct values.
_full = {p: f"M{i}" for i, p in enumerate(MOD_ELDER_ORDER)}
_slots_rt = mc.slots_from_row(row(stacks=3, elder=mod_encode(_full)))
check("all eight elder properties survive a full round trip through the web labels",
      {p: _slots_rt[s] for s, p in MOD_PROP_FOR.items()} == _full,
      repr({p: _slots_rt[s] for s, p in MOD_PROP_FOR.items()}))
check("the module's published segment order matches the mod's",
      mc.ELDER_SEGMENT_PROPERTIES == MOD_ELDER_ORDER)
# The exact six labels that were wrong before the fix, spelled out so a
# regression names itself instead of just failing a set comparison.
check("the six labels that used to resolve to the wrong property are right now",
      [mod_decode(mc.apply_slot_edit(row(stacks=3), s, "Wader")["elder_mutations"])
       [MOD_PROP_FOR[s]] for s in ("ea2", "ea3", "ea4", "eb1", "eb2", "eb3")]
      == ["Wader"] * 6)

# THE SECOND WRITER. server.py's inventory -> vault deploy builds the whole
# column at once; it packed the four A picks then the four B picks, which is the
# same bug one lane over. Both writers go through mutation_catalog now.
_deployed = mc.join_segments(mc.elder_segments_from_sets(["A1", "A2"], ["B1", "B2", "B3"]))
_dec = mod_decode(_deployed)
check("the deploy builder's Set A picks land in 1A,2A (not 1A,1B)",
      _dec["ElderMutationSlot1A"] == "A1" and _dec["ElderMutationSlot2A"] == "A2"
      and _dec["ElderMutationSlot1B"] == "B1", repr(_dec))
check("the deploy builder's Set B picks land in the B properties",
      [_dec[f"ElderMutationSlot{i}B"] for i in (1, 2, 3, 4)] == ["B1", "B2", "B3", "None"])
check("the deploy builder always emits exactly 8 segments",
      len(mc.elder_segments_from_sets([], [])) == 8
      and mc.elder_segments_from_sets([], []) == ["None"] * 8
      and len(mc.elder_segments_from_sets(list("abcdefg"), list("hijklmn"))) == 8)
check("the deploy builder is junk-tolerant (never raises, blanks become None)",
      mc.elder_segments_from_sets([None, "", "  ", "none"], None)
      == ["None"] * 8)
check("the deploy builder agrees with the per-slot writer for the same picks",
      mc.elder_segments_from_sets(["A1", "A2", "A3", "A4"], ["B1", "B2", "B3", "B4"])
      == [mc.slots_from_row(
          {"elder_mutations": mc.join_segments(
              mc.elder_segments_from_sets(["A1", "A2", "A3", "A4"],
                                          ["B1", "B2", "B3", "B4"]))})[s]
          for s in ("ea1", "eb1", "ea2", "eb2", "ea3", "eb3", "ea4", "eb4")])
check("server.py's deploy lane really calls the shared builder, not its own concat",
      "mutation_catalog.elder_segments_from_sets(" in _SERVER_SRC_EARLY
      and 'elder = ea + ["None"] * (4 - len(ea))' not in _SERVER_SRC_EARLY)

print("[6] CAS write against real sqlite")
fd, dbpath = tempfile.mkstemp(prefix="lin_mut_edit_", suffix=".db")
os.close(fd)
conn = sqlite3.connect(dbpath)
cols_sql = ", ".join(
    "id INTEGER PRIMARY KEY AUTOINCREMENT" if c == "id" else f"{c} TEXT"
    for c in _PARKED_COLS)
conn.execute(f"CREATE TABLE parked_dinos ({cols_sql})")
conn.execute(
    "INSERT INTO parked_dinos (steam_id, dino_class, mutations, parent_mutations, elder_mutations, elder_stacks) "
    "VALUES ('76561199000000001', 'BP_Tyrannosaurus_C', 'Hemomania|None|None|None', '', '', '0')")
conn.commit()
conn.close()
game_ipc.BOT_DB_PATH = dbpath

db_row = vault.get_parked_by_id(1)
new_strings = mc.apply_slot_edit(db_row, "n2", "Nocturnal")
ok, reason = vault.cas_update_mutations(1, "76561199000000001", db_row, new_strings)
check("CAS write succeeds on fresh row", ok is True)
after = vault.get_parked_by_id(1)
check("row holds normalized strings",
      after["mutations"] == "Hemomania|Nocturnal|None|None"
      and after["parent_mutations"] == "None|None|None|None"
      and after["elder_mutations"] == "None|None|None|None|None|None|None|None")

stale_expected = db_row  # pre-write snapshot: now stale
ok2, reason2 = vault.cas_update_mutations(1, "76561199000000001", stale_expected,
                                          mc.apply_slot_edit(db_row, "n3", "Wader"))
check("CAS rejects stale expected state", ok2 is False and reason2 == "state_changed")

ok3, _ = vault.cas_update_mutations(1, "76561199999999999", after,
                                    mc.apply_slot_edit(after, "n3", "Wader"))
check("CAS rejects wrong owner", ok3 is False)

conn = sqlite3.connect(dbpath)
conn.execute("UPDATE parked_dinos SET redeem_pending_cmd_id='abc' WHERE id=1")
conn.commit()
conn.close()
pending_row = vault.get_parked_by_id(1)
ok4, _ = vault.cas_update_mutations(1, "76561199000000001", pending_row,
                                    mc.apply_slot_edit(pending_row, "n3", "Wader"))
check("CAS rejects redeem-pending row", ok4 is False)

print("[6b] stale redeem-pending self-heal (resolve_stale_redeem_pending)")
import json as _json  # noqa: E402
import time as _time  # noqa: E402
_status_dir = tempfile.mkdtemp(prefix="lin_restore_status_")
game_ipc.REDEEM_COOLDOWNS_JSON = os.path.join(_status_dir, "redeem_cooldowns.json")


def _point_status(name, entries):
    # distinct filename per fixture so no read cache can serve a stale doc
    game_ipc.RESTORE_STATUS_JSON = os.path.join(_status_dir, name)
    with open(game_ipc.RESTORE_STATUS_JSON, "w", encoding="utf-8") as f:
        _json.dump({"entries": entries}, f)


def _set_pending(cmd_id, at_ms):
    c = sqlite3.connect(dbpath)
    c.execute("UPDATE parked_dinos SET redeem_pending_cmd_id=?, redeem_pending_at=? WHERE id=1",
              (cmd_id, at_ms))
    c.commit()
    c.close()


SID = "76561199000000001"
now_ms = int(_time.time() * 1000)
stale_ms = now_ms - int((vault.REDEEM_VERIFY_TIMEOUT_SECS + 5) * 1000)

_point_status("empty.json", [])
_set_pending("fresh1", now_ms)
r = vault.resolve_stale_redeem_pending(vault.get_parked_by_id(1))
check("fresh marker untouched (redeem may still land)",
      r is not None and r.get("redeem_pending_cmd_id") == "fresh1")

_set_pending("stale1", stale_ms)
r = vault.resolve_stale_redeem_pending(vault.get_parked_by_id(1))
check("stale marker w/o status entry cleared (bounce/crash leak)",
      r is not None and not str(r.get("redeem_pending_cmd_id") or "").strip())
after_heal = vault.get_parked_by_id(1)
check("marker cleared in DB", not str(after_heal.get("redeem_pending_cmd_id") or "").strip())
ok_heal, _ = vault.cas_update_mutations(1, SID, after_heal,
                                        mc.apply_slot_edit(after_heal, "n3", "Wader"))
check("mutation edit proceeds after self-heal", ok_heal is True)

_set_pending("stale2", stale_ms)
_point_status("failed.json", [{"event": "restore_failed", "steamid": SID, "cmd_id": "stale2",
                               "dino_id": 1, "definitive_failure": True}])
r = vault.resolve_stale_redeem_pending(vault.get_parked_by_id(1))
check("stale marker with definitive failure cleared",
      r is not None and not str(r.get("redeem_pending_cmd_id") or "").strip())

_set_pending("stale3", stale_ms)
_point_status("success.json", [{"event": "restore", "steamid": SID, "cmd_id": "stale3",
                                "dino_id": 1, "prime_ok": True, "mutations_ok": True,
                                "growth_ok": True, "stats_ok": True,
                                "max_stats_observed_ok": True}])
r = vault.resolve_stale_redeem_pending(vault.get_parked_by_id(1))
check("late-success restore finalised exactly-once (row deleted, returns None)",
      r is None and vault.get_parked_by_id(1) is None)

check("verify window covers the mod's 80s terminal verdict",
      vault.REDEEM_VERIFY_TIMEOUT_SECS >= 95.0)

print("[7] cost rules (mirror of server.py me_vault_mutations_set)")
def charge_for(current, new_value, cost=20000):
    same = (mc.normalize_mutation_name(current) == mc.normalize_mutation_name(new_value)) \
        or (current == "None" and new_value == "None")
    if same:
        return None  # no-op, free, no write
    return 0 if new_value == "None" else cost

check("adding a mutation charges", charge_for("None", "Nocturnal") == 20000)
check("replacing a mutation charges", charge_for("Wader", "Nocturnal") == 20000)
check("server default cost is 20k (owner ruling 2026-07-12)",
      __import__("re").search(r'LIN_MUTATION_EDIT_COST", "20000"',
                              open(os.path.join(os.path.dirname(__file__), "..", "server.py"),
                                   encoding="utf-8").read()) is not None)
check("clearing is free", charge_for("Nocturnal", "None") == 0)
check("no-op same value is free no-write", charge_for("Nocturnal", "nocturnal") is None)
check("no-op empty slot clear is free no-write", charge_for("None", "None") is None)

print("[8] catalog parity vs mod known/banned tables")
# THESE TWO SETS ARE A PIN ON THE RUNNING MOD, and they MUST move in the same
# wave the mod does. Offering a name the live validator refuses is the whole
# reason this block exists: validateMutationForSid turns it down, ApplyMutations
# skips the slot, the restore reports failure, and the bot keeps the vault row
# beside a dinosaur that already spawned -- one stored dino becomes two.
#
# WHERE THIS TRUTH CAME FROM (2026-07-27 re-pin, after the catalog went to 41):
#   * the running payload's own source, C:\ServerStaging\lin_mutknown_20260726\
#     main.full.WAVE.lua lines 7377-7434, transcribed key for key;
#   * that source compiles to luac.out sha256 906BE480... which is BYTE-IDENTICAL
#     to new_payload.luac, the payload inside laislanublar_lua.new.bin;
#   * that bin hashes to E823770E738D9F3E6BE488CB694E475ED1655DFB988279A074C3AC42
#     FC3F5B68 -- the same sha the game's live Scripts\laislanublar_lua.bin reads
#     today, and the same constant bot/mutation_names.py::_WAVE_BIN_SHA256 gates
#     its own widening on;
#   * the apply hook's marker C:\LaIslaNublar\data\lin_mutwave_live.flag exists
#     ("mutation wave already present 2026-07-27T08:50:36Z", written inside the
#     08:50:35->08:50:36Z restart down window) and its arm file
#     data\lin_muts_on.armed is gone, i.e. the hook fired and disarmed.
# So the mod half went live BEFORE the catalog commit, which is the required
# order. The PRE-wave tables (38 known / 11 banned, with socialbehavior and
# reabsorption still banned) are what used to sit here.
#
# NEVER edit these to make a red suite green. Red here means the site is about to
# offer a name the running mod refuses, and that is the dupe path, not a stale
# test. The only correct reason to touch them is a mod wave that is PROVEN live
# by the four facts above.
MOD_KNOWN = {
    "hemomania", "acceleratedpreydrive", "hypermetabolicinanition", "osteophagic",
    "augmentedtapetum", "xerocoleadaptation", "tactileendurance", "hematophagy",
    "truculency", "photosyntheticregeneration", "cellularregeneration",
    "advancedgestation", "sustainedhydration", "efficientdigestion", "featherweight",
    "osteosclerosis", "wader", "epidermalfibrosis", "congenitalhypoalgesia",
    "photosynthetictissue", "nocturnal", "hydroregenerative",
    "increasedinspiratorycapacity", "hydrodynamic", "submergedopticalretention",
    "enhanceddigestion", "reinforcedtendons", "multichamberedlungs",
    "infrasoundcommunication", "heightenedghrelin", "prolificreproduction",
    "gastronomicregeneration", "cannibalistic", "hypervigilance", "enlargedmeniscus",
    "reniculatekidneys", "saltwater", "sequentialhermaphroditism",
    "traumaticthrombosis",
    # The 2026-07-26 wave. The first two were in the BANNED set below until that
    # boot; the second two were simply absent from the table.
    "reabsorption", "socialbehavior", "barometricsensitivity", "parthenogenesis",
}
MOD_BANNED = {
    "melorheostosis", "hyperreflexia", "intraspecificaggression",
    "remodelingambulation", "stereopsis", "pitorgan", "patternrecognition",
    "paratrepsis", "constrictedglands",
}
unknown = [n for n in mc.PICKABLE if mc.normalize_mutation_name(n) not in MOD_KNOWN]
banned = [n for n in mc.PICKABLE if mc.normalize_mutation_name(n) in MOD_BANNED]
check("every pickable name is mod-known", not unknown, str(unknown))
check("no pickable name is mod-banned", not banned, str(banned))
# THE SIZES ARE PINNED TOO, because the two checks above can also be satisfied by
# quietly WIDENING MOD_KNOWN or EMPTYING MOD_BANNED. Those are the two edits that
# would make this block stop being an oracle without deleting a line of it.
# 43 known keys (42 display names -- "saltwater" is the mod's own alias for
# Reniculate Kidneys) and 9 banned, counted off main.full.WAVE.lua.
check("the mod tables are pinned at the sizes the live payload really has",
      len(MOD_KNOWN) == 43 and len(MOD_BANNED) == 9,
      f"known={len(MOD_KNOWN)} banned={len(MOD_BANNED)}")
check("...and nothing is on both sides of the mod's own gate",
      not (MOD_KNOWN & MOD_BANNED), f"{sorted(MOD_KNOWN & MOD_BANNED)!r}")
# The catalog is a STRICT SUBSET, never equal, and each name it holds back is held
# back for a STATED reason - listed here so neither can drift silently:
#   traumaticthrombosis  removed content since 0.21.720; it is also the name every
#                        "not in the catalog" case in this file uses, so it must
#                        never drift INTO PICKABLE or those cases hollow out.
# parthenogenesis LEFT this list 2026-08-12, per its own exit clause: the C++
# half that arms its reproduction-unlock byte is live (the on-box main.dll's
# string table carries the name), so the site now offers it — see
# tests_local/test_parthenogenesis_pickable.py for the cure battery.
# If the above stops being true, delete it from here in the same edit.
_MOD_ONLY = MOD_KNOWN - {mc.normalize_mutation_name(n) for n in mc.PICKABLE} - {"saltwater"}
check("the catalog holds back exactly the names we said we hold back",
      _MOD_ONLY == {"traumaticthrombosis"}, f"{sorted(_MOD_ONLY)!r}")
check("all descriptions present", all(mc.DESCRIPTIONS.get(n) for n in mc.PICKABLE))
check("16 slot ids", len(mc.SLOT_IDS) == 16)
check("21-species roster classified",
      len(mc.CARNIVORES) == 10 and len(mc.HERBIVORES) == 10 and len(mc.GALLIMIMUS) == 1)

print("[9] growth / Prime ladder on the own slots (owner ruling 2026-07-25)")
# "25% first mut only. 50% first and second. 75% first second and third, and if
# prime and at 75% then first, second, third, and fourth. if not prime no
# fourth." growth is a FRACTION 0..1 on a parked row.
def lrow(growth, prime=False, muts="", parent=""):
    return row(growth=growth, is_prime=1 if prime else 0, muts=muts, parent=parent)


def open_n(growth, prime=False):
    r = lrow(growth, prime)
    return [s for s in ("n1", "n2", "n3", "n4") if mc.slot_unlocked(r, s)]


# --- every rung, and the EXACT boundaries -------------------------------------
# The rung is measured against the percent THE SITE SHOWS (round(), matching
# vault._dino_view) — see the equality block below. So 0.2499, which the vault
# card renders as "25%", gets the 25% rung: the gate agrees with the number the
# player is reading, instead of refusing a rung his own card says he reached.
check("below 25% -> nothing open", open_n(0.24) == [])
check("0% -> nothing open", open_n(0.0) == [])
check("boundary 0.25 exactly -> n1 only", open_n(0.25) == ["n1"])
check("0.2499 shows as 25%, so it GETS the 25% rung", open_n(0.2499) == ["n1"])
check("0.244 shows as 24% and stays below the 25% rung", open_n(0.244) == [])
check("0.49 -> still n1 only", open_n(0.49) == ["n1"])
check("boundary 0.50 exactly -> n1,n2", open_n(0.50) == ["n1", "n2"])
check("0.4999 shows as 50%, so it GETS the 50% rung", open_n(0.4999) == ["n1", "n2"])
check("0.494 shows as 49% and stays below the 50% rung", open_n(0.494) == ["n1"])
check("0.74 -> n1,n2", open_n(0.74) == ["n1", "n2"])
check("boundary 0.75 exactly (non-prime) -> n1,n2,n3", open_n(0.75) == ["n1", "n2", "n3"])
check("0.7499 shows as 75%, so it GETS the 75% rung", open_n(0.7499) == ["n1", "n2", "n3"])
check("0.744 shows as 74% and stays below the 75% rung", open_n(0.744) == ["n1", "n2"])
check("100% non-prime -> still only three (no fourth)", open_n(1.0) == ["n1", "n2", "n3"])

# --- prime vs non-prime at 75% for n4 ----------------------------------------
check("boundary 0.75 + prime -> all four", open_n(0.75, True) == ["n1", "n2", "n3", "n4"])
check("100% prime -> all four", open_n(1.0, True) == ["n1", "n2", "n3", "n4"])
check("0.7499 + prime shows as 75%, so the fourth opens too",
      open_n(0.7499, True) == ["n1", "n2", "n3", "n4"])
check("prime below 75% does NOT get n4", open_n(0.74, True) == ["n1", "n2"])
check("0.744 + prime shows as 74% and still does NOT get n4",
      open_n(0.744, True) == ["n1", "n2"])
check("prime at 50% does NOT get n4", open_n(0.50, True) == ["n1", "n2"])
check("non-prime NEVER gets n4 at any growth",
      all("n4" not in open_n(g) for g in (0.0, 0.25, 0.5, 0.75, 0.9, 1.0)))

# --- ONE growth percent on the whole site ------------------------------------
# The vault card (VaultSection) and the preview header (VaultDinoPreview) render
# vault._dino_view's growth_pct; the editor legend renders the GET's growth_pct
# and the lock reason quotes it again a few pixels below. Those numbers must be
# the SAME integer, and the ladder must be measured against it. Asserted against
# the REAL vault module — never a re-typed copy of its formula, which would
# drift with it and prove nothing.
_PCT_SPREAD = (0.0, 0.01, 0.24, 0.244, 0.2499, 0.25, 0.29, 0.49, 0.494, 0.4999,
               0.5, 0.58, 0.74, 0.744, 0.745, 0.7499, 0.75, 0.9, 0.999, 1.0, 1.0005)


def card_pct(g):
    """What the player's own vault card says, straight out of vault.py."""
    return vault._dino_view({"id": 1, "dino_class": "BP_Tyrannosaurus_C", "growth": g})["growth_pct"]


_pct_mismatch = [(g, card_pct(g), mc.growth_display_pct(mc.growth_fraction({"growth": g})))
                 for g in _PCT_SPREAD
                 if card_pct(g) != mc.growth_display_pct(mc.growth_fraction({"growth": g}))]
check("editor percent == vault card percent for every growth in the spread",
      not _pct_mismatch, f"(growth, card, editor) mismatches: {_pct_mismatch}")
check("the spread really covers the values int() truncation got wrong",
      [card_pct(g) for g in (0.29, 0.58, 0.745, 0.7499, 0.999)] == [29, 58, 74, 75, 100]
      and [int(g * 100) for g in (0.29, 0.58, 0.745, 0.7499, 0.999)] == [28, 57, 74, 74, 99])

_ladder_pcts = {r["slot"]: r["requires_growth_pct"] for r in mc.growth_ladder_view()}
_gate_mismatch = []
for _g in _PCT_SPREAD:
    _prime_row = {"id": 1, "dino_class": "BP_Tyrannosaurus_C", "growth": _g, "is_prime": 1}
    for _sid, _need in _ladder_pcts.items():
        _want_open = card_pct(_g) >= _need          # prime row: only growth decides
        if mc.slot_unlocked(_prime_row, _sid) != _want_open:
            _gate_mismatch.append((_g, _sid, card_pct(_g), _need))
check("the gate opens exactly the rungs the shown percent has reached",
      not _gate_mismatch, f"(growth, slot, shown, needs) mismatches: {_gate_mismatch}")

_reason_mismatch = []
for _g in _PCT_SPREAD:
    for _sid in ("n1", "n2", "n3", "n4"):
        _lk = mc.slot_lock({"growth": _g, "is_prime": 1}, _sid)
        if not _lk or _lk[0] != "growth":
            continue
        _m = __import__("re").search(r"ahora: (\d+)%", _lk[1])
        if not _m or int(_m.group(1)) != card_pct(_g):
            _reason_mismatch.append((_g, _sid, _lk[1], card_pct(_g)))
check('every "(ahora: N%)" lock reason quotes the card\'s own percent',
      not _reason_mismatch, str(_reason_mismatch))
check("the helper is None-safe (unreadable growth has no percent to show)",
      mc.growth_display_pct(None) is None
      and mc.growth_display_pct(mc.growth_fraction({"growth": None})) is None)
check("the ladder rungs themselves are the owner's 25/50/75 as whole percents",
      _ladder_pcts == {"n1": 25, "n2": 50, "n3": 75, "n4": 75})

# --- null / missing / malformed growth fails CLOSED --------------------------
for bad, label in ((None, "None"), ("", "empty string"), ("   ", "blank string"),
                   ("abc", "non-numeric"), (float("nan"), "NaN"),
                   (float("inf"), "infinity"), (-0.5, "negative"),
                   (75, "percent-scaled 75"), (True, "bool True")):
    r_bad = {"id": 1, "dino_class": "BP_Tyrannosaurus_C", "growth": bad, "is_prime": 1}
    check(f"growth {label} fails closed (all own slots locked)",
          [s for s in ("n1", "n2", "n3", "n4") if mc.slot_unlocked(r_bad, s)] == [],
          f"open={[s for s in ('n1','n2','n3','n4') if mc.slot_unlocked(r_bad, s)]}")
r_missing = {"id": 1, "dino_class": "BP_Tyrannosaurus_C"}   # no growth key at all
check("missing growth KEY fails closed", not mc.slot_unlocked(r_missing, "n1"))
check("growth None reason is the unreadable one",
      (mc.slot_lock({"growth": None}, "n1") or ("", ""))[0] == "growth_unknown")
check("growth as a numeric STRING is read (sqlite TEXT column)",
      mc.growth_fraction({"growth": "0.75"}) == 0.75
      and mc.slot_unlocked({"growth": "0.75", "is_prime": 0}, "n3"))
check("growth 1.0005 float noise clamps to full grown",
      mc.growth_fraction({"growth": 1.0005}) == 1.0)

# --- is_prime parsing: bool("0") is True in Python ---------------------------
check('is_prime "0" (TEXT column) is NOT prime', not mc.is_prime_flag({"is_prime": "0"}))
check('is_prime "false" is NOT prime', not mc.is_prime_flag({"is_prime": "false"}))
check("is_prime missing is NOT prime", not mc.is_prime_flag({}))
check("is_prime 0 is NOT prime", not mc.is_prime_flag({"is_prime": 0}))
check('is_prime "1" IS prime', mc.is_prime_flag({"is_prime": "1"}))
check("is_prime 1 IS prime", mc.is_prime_flag({"is_prime": 1}))
check("is_prime True IS prime", mc.is_prime_flag({"is_prime": True}))
check('n4 stays locked for a "0" text prime at 100%',
      not mc.slot_unlocked({"growth": 1.0, "is_prime": "0"}, "n4"))

# The flag is read with an ALLOWLIST, not a denylist of falsey words. A denylist
# is the one fail-OPEN branch a fail-closed module cannot have: every value it
# has not heard of reads as Prime and hands out the Prime-only fourth slot.
# These are the exact values that got it wrong — "0.00" and b"0" are zero by any
# reading, and str(b"0") is "b'0'", which matches no falsey word at all.
_NOT_PRIME_VALUES = [
    "0.00", "00", "-0", "0e0", "abc", b"0", bytearray(b"0"), memoryview(b"0"),
    [], {}, (), set(), object(), "", "   ", "0", "0.0", "false", "False", "FALSE",
    "no", "none", "null", "off", "f", "n", "nope", "maybe", "2", "-1", "true!",
    " prime ", 0, 0.0, -0.0, False, None, float("nan"),
]
_wrongly_prime = [v for v in _NOT_PRIME_VALUES if mc.is_prime_flag({"is_prime": v})]
check("every unreadable / zero is_prime value reads as NOT prime (allowlist)",
      not _wrongly_prime, f"read as prime: {_wrongly_prime!r}")
# ...and the forms that GENUINELY mean true still do. Sources: vault.park and
# bot/database.py store INTEGER 1; bot/dino.py builds bool(prime); the mod emits
# "true" (main.full.lua tostring); a TEXT-typed column hands back "1"/"1.0".
_PRIME_VALUES = [1, 1.0, True, "1", " 1 ", "1.0", "true", "True", "TRUE", "t",
                 "yes", "Y", "on", "si", "Sí", "SÍ", b"1", b"true", 2, -3, 0.5]
_wrongly_not_prime = [v for v in _PRIME_VALUES if not mc.is_prime_flag({"is_prime": v})]
check("every form that really means true still reads as prime",
      not _wrongly_not_prime, f"read as NOT prime: {_wrongly_not_prime!r}")
check("is_prime_flag never raises on a junk row",
      mc.is_prime_flag(None) is False and mc.is_prime_flag("nope") is False
      and mc.is_prime_flag(42) is False)
# The gate is what the fail-open branch actually cost: the fourth own slot.
_open_n4 = [v for v in _NOT_PRIME_VALUES
            if mc.slot_unlocked({"growth": 1.0, "is_prime": v}, "n4")]
check("no unreadable is_prime value opens the Prime-only fourth slot at 100%",
      not _open_n4, f"opened n4: {_open_n4!r}")
check("a real prime still opens the fourth slot at 100%",
      all(mc.slot_unlocked({"growth": 1.0, "is_prime": v}, "n4") for v in _PRIME_VALUES),
      "a true is_prime form was refused n4")

# --- growth_display_pct really never raises ----------------------------------
# server.py reads it OUTSIDE the try/except that wraps the rest of the mutations
# GET, so anything that escapes here 500s the editor instead of locking a slot.
# int(round(x)) raises OverflowError (NOT ValueError) on infinity, and float()
# raises it on an int too large for a double.
_NO_PCT = [float("inf"), float("-inf"), float("nan"), 10**400, -(10**400),
           10**308, 1e307, -1e307, "inf", "-inf", "nan", "abc", "", [], {},
           object(), None]
_pct_raised, _pct_not_none = [], []
for _v in _NO_PCT:
    try:
        _got = mc.growth_display_pct(_v)
    except Exception as _e:                       # noqa: BLE001 - that IS the bug
        _pct_raised.append((_v, type(_e).__name__))
        continue
    if _got is not None:
        _pct_not_none.append((_v, _got))
check("growth_display_pct never raises, whatever it is handed",
      not _pct_raised, f"raised: {_pct_raised!r}")
check("infinite / NaN / oversized growth has no percent to show (None)",
      not _pct_not_none, f"returned a percent: {_pct_not_none!r}")
_raw_raises = []
for _v in (float("inf"), float("-inf"), 10**400):
    try:
        int(round(float(_v) * 100))
    except Exception as _e:                       # noqa: BLE001
        _raw_raises.append(type(_e).__name__)
check("the guard is load-bearing: the naive arithmetic really does raise on these",
      _raw_raises == ["OverflowError"] * 3, f"{_raw_raises!r}")
check("a readable growth still gets its percent",
      [mc.growth_display_pct(g) for g in (0.0, 0.25, 0.5, 0.7499, 1.0, "0.75")]
      == [0, 25, 50, 75, 100, 75])
# Same contract one layer up: the lock path must answer, not explode, on them.
_lock_raised = []
for _v in _NO_PCT:
    try:
        if mc.slot_unlocked({"growth": _v, "is_prime": 1}, "n1"):
            _lock_raised.append((_v, "OPENED n1"))
    except Exception as _e:                       # noqa: BLE001
        _lock_raised.append((_v, type(_e).__name__))
check("an unshowable growth locks the ladder instead of raising",
      not _lock_raised, f"{_lock_raised!r}")
# ...and it does it WITHOUT letting an exception reach slot_lock's catch-all,
# which answered correctly but logged a traceback per call. float() answers
# OverflowError, not ValueError, for an int too large for a double.
_gf_raised = []
for _v in _NO_PCT:
    try:
        mc.growth_fraction({"growth": _v})
    except Exception as _e:                       # noqa: BLE001
        _gf_raised.append((_v, type(_e).__name__))
check("growth_fraction really never raises, as its docstring promises",
      not _gf_raised, f"raised: {_gf_raised!r}")

# --- the gate is on the WRITE path, and only for own slots -------------------
expect_error("writing into a locked n2 at 30% is rejected",
             lambda: mc.validate_slot_edit(lrow(0.30), "n2", "Nocturnal"), "50%")
expect_error("writing into n4 on a 100% NON-prime is rejected",
             lambda: mc.validate_slot_edit(lrow(1.0), "n4", "Nocturnal"), "prime")
expect_error("locked slot answers with the LOCK, not the diet rule",
             lambda: mc.validate_slot_edit(lrow(0.30, muts=""), "n3", "Tactile Endurance"), "75%")
expect_error("locked slot answers with the LOCK, not the unknown-name rule",
             lambda: mc.validate_slot_edit(lrow(0.30), "n3", "Totally Fake Mutation"), "75%")
expect_ok("writing into the OPEN n1 at 30% still works",
          lambda: mc.validate_slot_edit(lrow(0.30), "n1", "Nocturnal"), "Nocturnal")
# The two ladders are INDEPENDENT: growth never gates an inherited slot, and the
# entomb count never gates an own one. lrow's rows are entombed three times, so
# what is being measured below really is growth alone.
expect_ok("inherited p1 is NOT on the growth ladder",
          lambda: mc.validate_slot_edit(lrow(0.26), "p1", "Nocturnal"), "Nocturnal")
expect_ok("inherited p2 is NOT on the growth ladder",
          lambda: mc.validate_slot_edit(lrow(0.26), "p2", "Wader"), "Wader")
expect_ok("elder set A is NOT on the growth ladder",
          lambda: mc.validate_slot_edit(lrow(0.26), "ea1", "Wader"), "Wader")
expect_ok("elder set B is NOT on the growth ladder",
          lambda: mc.validate_slot_edit(lrow(0.26), "eb4", "Wader"), "Wader")
expect_ok("an entombed dino's inherited slots stay writable even when growth is unreadable",
          lambda: mc.validate_slot_edit(
              {"id": 1, "dino_class": "BP_Tyrannosaurus_C", "growth": None,
               "elder_stacks": 3},
              "p1", "Wader"), "Wader")
check("...and open, for both families",
      mc.slot_unlocked({"growth": None, "elder_stacks": 3}, "p1")
      and mc.slot_unlocked({"growth": None, "elder_stacks": 3}, "ea1"))
check("a full-grown Prime with 0 entombs still has every own slot open",
      [s for s in ("n1", "n2", "n3", "n4")
       if mc.slot_unlocked({"growth": 1.0, "is_prime": 1, "elder_stacks": 0}, s)]
      == ["n1", "n2", "n3", "n4"])

# --- CLEARING a locked slot is always allowed, and free ----------------------
legacy = lrow(0.30, muts="Hemomania|Nocturnal|Wader|Featherweight")
expect_ok("clearing a locked n2 is allowed",
          lambda: mc.validate_slot_edit(legacy, "n2", "None"), "None", "Nocturnal")
expect_ok("clearing a locked n4 (empty string) is allowed",
          lambda: mc.validate_slot_edit(legacy, "n4", ""), "None", "Featherweight")
expect_ok('clearing a locked slot with the literal "none" is allowed',
          lambda: mc.validate_slot_edit(legacy, "n3", "none"), "None")
expect_ok("clearing an EMPTY locked slot is a free no-op, not an error",
          lambda: mc.validate_slot_edit(lrow(0.30), "n4", "None"), "None", "None")
check("clearing a locked slot costs 0", charge_for("Nocturnal", "None") == 0)
out = mc.apply_slot_edit(legacy, "n2", "None")
check("clearing a locked slot writes None and touches nothing else",
      out["mutations"] == "Hemomania|None|Wader|Featherweight")

# --- an existing OVER-LADDER row keeps its values (non-destructive) ----------
over = lrow(0.30, muts="Hemomania|Nocturnal|Wader|Featherweight")
check("over-ladder row still reports all four stored values",
      list(mc.slots_from_row(over)[s] for s in ("n1", "n2", "n3", "n4"))
      == ["Hemomania", "Nocturnal", "Wader", "Featherweight"])
check("over-ladder row's active_count is unchanged", mc.active_count(over) == 4)
expect_error("over-ladder row cannot REPLACE a locked value",
             lambda: mc.validate_slot_edit(over, "n4", "Wader"), "prime")
expect_ok("over-ladder row can still edit its OPEN slot",
          lambda: mc.validate_slot_edit(over, "n1", "Hematophagy"), "Hematophagy")
check("nothing in the catalog wipes or strips a row",
      mc.apply_slot_edit(over, "n1", "Hematophagy")["mutations"]
      == "Hematophagy|Nocturnal|Wader|Featherweight")

# --- lock map / ladder view shape (what the GET sends the UI) ---------------
lm = mc.slot_lock_map(lrow(0.55))
check("lock map covers all 16 slots", len(lm) == 16 and set(lm) == set(mc.SLOT_IDS))
check("lock map: n1/n2 open, n3/n4 locked at 55% non-prime",
      lm["n1"]["locked"] is False and lm["n2"]["locked"] is False
      and lm["n3"]["locked"] is True and lm["n4"]["locked"] is True)
check("lock map: n3 reason names the 75% rung and the current growth",
      "75%" in (lm["n3"]["reason"] or "") and "55%" in (lm["n3"]["reason"] or ""),
      repr(lm["n3"]["reason"]))
check("lock map: n4 on a non-prime reports the prime code",
      lm["n4"]["code"] == "prime" and "Prime" in (lm["n4"]["reason"] or ""),
      repr(lm["n4"]))
check("lock map: reasons are Spanish (no English leakage)",
      all(("unlock" not in (v["reason"] or "").lower() and "growth" not in (v["reason"] or "").lower())
          for v in lm.values()))
check("lock map: requirements are exposed as percentages",
      lm["n2"]["requires_growth_pct"] == 50 and lm["n4"]["requires_growth_pct"] == 75
      and lm["n4"]["requires_prime"] is True and lm["n1"]["requires_prime"] is False)
check("lock map: p/elder slots carry no GROWTH requirement",
      lm["p1"]["requires_growth_pct"] is None and lm["ea1"]["requires_growth_pct"] is None)
check("lock map: p/elder slots carry their ENTOMB requirement instead",
      [lm[s]["requires_entombs"] for s in ("p1", "ea1", "eb1")] == [1, 2, 3]
      and lm["n1"]["requires_entombs"] is None)
check("lock map: a three-times-entombed dino has all twelve open",
      all(lm[s]["locked"] is False for s in _INHERITED))
_lm0 = mc.slot_lock_map(row(stacks=0, growth=1.0, is_prime=1))
check("lock map: a never-entombed dino has all twelve closed, with the entomb code",
      all(_lm0[s]["locked"] and _lm0[s]["code"] == "entomb" for s in _INHERITED)
      and all(_lm0[s]["locked"] is False for s in ("n1", "n2", "n3", "n4")))
check("lock map: the entomb reasons are Spanish and name the entierros",
      all("enterrado" in (_lm0[s]["reason"] or "") for s in _INHERITED))
_lm_bad = mc.slot_lock_map(row(stacks="abc", growth=1.0, is_prime=1))
check("lock map: an unreadable count locks the twelve with entomb_unknown",
      all(_lm_bad[s]["code"] == "entomb_unknown" for s in _INHERITED))
check("open slots carry no reason", lm["n1"]["reason"] is None and lm["n1"]["code"] is None)
lv = mc.growth_ladder_view()
check("ladder view is the owner's four rungs",
      [(r["slot"], r["requires_growth_pct"], r["requires_prime"]) for r in lv]
      == [("n1", 25, False), ("n2", 50, False), ("n3", 75, False), ("n4", 75, True)])
check("ladder view is 1-indexed for the UI",
      [r["index"] for r in lv] == [1, 2, 3, 4])
check("unlocked_slots returns every writable slot id",
      mc.unlocked_slots(lrow(0.55)) == frozenset(
          set(mc.SLOT_IDS) - {"n3", "n4"}))
check("unlocked_slots on a 55% dino that has never been entombed is n1,n2 only",
      mc.unlocked_slots(row(growth=0.55, is_prime=0, stacks=0)) == frozenset({"n1", "n2"}))
check("unlocked_slots walks BOTH ladders at once",
      mc.unlocked_slots(row(growth=0.55, is_prime=0, stacks=2))
      == frozenset({"n1", "n2"} | set(_P) | set(_EA)))

# --- crash containment: a malformed row must never 500 the editor -----------
for junk in (None, "not a row", 42, [], object()):
    try:
        locked = not mc.slot_unlocked(junk, "n1")
        crashed = False
    except Exception:
        locked, crashed = False, True
    check(f"slot_unlocked survives a {type(junk).__name__} row and fails closed",
          not crashed and locked)
try:
    mc.slot_lock({"growth": 0.5}, None)
    mc.slot_lock({"growth": 0.5}, 7)
    mc.slot_lock({"growth": 0.5}, ["n1"])
    check("slot_lock survives a non-string slot id", True)
except Exception as e:
    check("slot_lock survives a non-string slot id", False, str(e))
try:
    bad_map = mc.slot_lock_map(None)
    check("slot_lock_map survives a None row and locks EVERY gated slot",
          len(bad_map) == 16 and all(bad_map[s]["locked"] for s in mc.SLOT_IDS)
          and bad_map["n1"]["code"] == "growth_unknown"
          and bad_map["p1"]["code"] == "entomb_unknown",
          repr({s: bad_map[s]["code"] for s in ("n1", "p1", "ea1", "eb1")}))
except Exception as e:
    check("slot_lock_map survives a None row and locks EVERY gated slot", False, str(e))
for junk in (None, "not a row", 42, [], object()):
    try:
        opened = [s for s in _INHERITED if mc.slot_unlocked(junk, s)]
        crashed = False
    except Exception:
        opened, crashed = ["<raised>"], True
    check(f"the entomb gate survives a {type(junk).__name__} row and fails closed",
          not crashed and not opened, f"opened: {opened!r}")

print("[10] ladder over the REAL sqlite round trip (production column types)")
# The pure layer above proves the rule; this proves the rule still holds on the
# bytes sqlite actually hands back (growth REAL, is_prime INTEGER — see
# bot/database.py), which is where a units/typing bug would really live.
fd2, dbpath2 = tempfile.mkstemp(prefix="lin_mut_ladder_", suffix=".db")
os.close(fd2)
c2 = sqlite3.connect(dbpath2)
c2.execute("""CREATE TABLE parked_dinos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, steam_id TEXT NOT NULL,
    discord_id TEXT NOT NULL, dino_class TEXT, growth REAL,
    health REAL, max_health REAL, stamina REAL, max_stamina REAL,
    hunger REAL, max_hunger REAL, thirst REAL, max_thirst REAL,
    oxygen REAL, max_oxygen REAL, x REAL, y REAL, z REAL,
    is_prime INTEGER DEFAULT 0, is_elder INTEGER DEFAULT 0,
    mutations TEXT DEFAULT "", parent_mutations TEXT DEFAULT "",
    elder_mutations TEXT DEFAULT "", elder_stacks INTEGER DEFAULT 0,
    skin_code TEXT DEFAULT "", skin_data TEXT DEFAULT "",
    diet_a REAL DEFAULT 0, diet_b REAL DEFAULT 0, diet_c REAL DEFAULT 0,
    parked_at TEXT, redeem_pending_cmd_id TEXT, redeem_pending_at INTEGER)""")
c2.executemany(
    "INSERT INTO parked_dinos (steam_id, discord_id, dino_class, growth, is_prime, mutations) "
    "VALUES (?, '1', 'BP_Tyrannosaurus_C', ?, ?, ?)",
    [("76561199000000001", 0.25, 0, "None|None|None|None"),     # id 1
     ("76561199000000001", 0.75, 0, "None|None|None|None"),     # id 2
     ("76561199000000001", 0.75, 1, "None|None|None|None"),     # id 3
     ("76561199000000001", None, 1, "None|None|None|None"),     # id 4 (null growth)
     ("76561199000000001", 0.30, 0, "Hemomania|Nocturnal|Wader|Featherweight")])  # id 5
c2.commit()
c2.close()
game_ipc.BOT_DB_PATH = dbpath2

db25 = vault.get_parked_by_id(1)
check("sqlite REAL growth survives the round trip as a fraction",
      isinstance(db25.get("growth"), float) and db25["growth"] == 0.25)
check("db row at 25% opens n1 only",
      [s for s in ("n1", "n2", "n3", "n4") if mc.slot_unlocked(db25, s)] == ["n1"])
db75 = vault.get_parked_by_id(2)
check("db row at 75% non-prime opens three",
      [s for s in ("n1", "n2", "n3", "n4") if mc.slot_unlocked(db75, s)] == ["n1", "n2", "n3"])
db75p = vault.get_parked_by_id(3)
check("db row at 75% PRIME opens four",
      [s for s in ("n1", "n2", "n3", "n4") if mc.slot_unlocked(db75p, s)] == ["n1", "n2", "n3", "n4"])
dbnull = vault.get_parked_by_id(4)
check("db row with NULL growth fails closed even though it is prime",
      dbnull.get("growth") is None
      and [s for s in ("n1", "n2", "n3", "n4") if mc.slot_unlocked(dbnull, s)] == [])
dbover = vault.get_parked_by_id(5)
check("db over-ladder row keeps every stored value",
      mc.slots_from_row(dbover)["n4"] == "Featherweight" and mc.active_count(dbover) == 4)
new_strings = mc.apply_slot_edit(dbover, "n3", "None")
ok_clear, _ = vault.cas_update_mutations(5, "76561199000000001", dbover, new_strings)
after_clear = vault.get_parked_by_id(5)
check("clearing a locked slot writes through to sqlite",
      ok_clear is True and after_clear["mutations"] == "Hemomania|Nocturnal|None|Featherweight")

# --- the ENTOMB ladder over the same real round trip -------------------------
# elder_stacks is INTEGER in the bot schema; this is where a typing bug would
# really live. Row 6 also carries a stored value in a slot its count keeps shut.
c3 = sqlite3.connect(dbpath2)
c3.executemany(
    "INSERT INTO parked_dinos (steam_id, discord_id, dino_class, growth, is_prime, "
    "elder_stacks, parent_mutations, elder_mutations) "
    "VALUES (?, '1', 'BP_Tyrannosaurus_C', 1.0, 1, ?, ?, ?)",
    [("76561199000000001", 0, "Hemomania|None|None|None", ""),   # id 6: 0 stored, p1 held
     ("76561199000000001", 1, "", ""),                            # id 7
     ("76561199000000001", 2, "", ""),                            # id 8
     ("76561199000000001", 3, "", ""),                            # id 9
     ("76561199000000001", 0, "", "")])                           # id 10: really 0
c3.commit()
c3.close()
_db_rungs = {n: [s for s in _INHERITED if mc.slot_unlocked(vault.get_parked_by_id(n), s)]
             for n in (6, 7, 8, 9, 10)}
check("sqlite INTEGER elder_stacks survives the round trip as an int",
      isinstance(vault.get_parked_by_id(7).get("elder_stacks"), int))
check("db rows open exactly 0 / 4 / 8 / 12 by their stored entomb count",
      [len(_db_rungs[n]) for n in (10, 7, 8, 9)] == [0, 4, 8, 12], repr(_db_rungs))
# Row 6 IS the regression, on the bytes sqlite hands back: counter 0, a real
# mutation sitting in the parent column. Its own column proves generation 1.
check("a db row recorded at 0 with a filled parent column opens its four heredadas",
      _db_rungs[6] == _P, repr(_db_rungs[6]))
db0 = vault.get_parked_by_id(6)
check("a db row recorded at 0 still reports the value stored in p1",
      mc.slots_from_row(db0)["p1"] == "Hemomania" and mc.active_count(db0) == 1)
check("...the gate reads 1 off that column while the GET still publishes the real 0",
      mc.effective_elder_stacks(db0) == 1
      and mc.elder_stack_count(db0) == 0 and db0.get("elder_stacks") == 0)
expect_ok("...and the write path lets him re-pick what he paid for",
          lambda: mc.validate_slot_edit(db0, "p1", "Wader"), "Wader", "Hemomania")
expect_error("...while Anciano A on that same row is still refused",
             lambda: mc.validate_slot_edit(db0, "ea1", "Wader"), "al menos 2")
ok_p1, _ = vault.cas_update_mutations(
    6, "76561199000000001", db0, mc.apply_slot_edit(db0, "p1", "None"))
check("...but emptying it writes through to sqlite",
      ok_p1 is True
      and vault.get_parked_by_id(6)["parent_mutations"] == "None|None|None|None")
check("...and once the column is empty the row is back to nothing proven",
      [s for s in _INHERITED if mc.slot_unlocked(vault.get_parked_by_id(6), s)] == []
      and mc.effective_elder_stacks(vault.get_parked_by_id(6)) == 0)

# --- the WEB LANES' own INSERT, through the real save_parked -----------------
# save_parked reads pd["elder_stacks"] and stores int(_num(...)), so a lane that
# omits the key stores 0. BOTH web lanes omit it ON PURPOSE (block [4b]): that
# column is what the redeem hands the mod as ElderReplicationStacks, so a derived
# value there is an in-game grant, not an editor permission. These dicts are the
# shapes /store/purchase-dino and /active-dino/deploy really hand it, key and all
# absent, and what is proven here is that the EDITOR is fine anyway -- which is
# the entire argument for deriving at read time instead of at insert.
_STORE_P = "Wader|None|None|None"
_store_id = vault.save_parked("76561199000000021", "d1", {
    "dino": "BP_Stegosaurus_C", "growth": 0.75, "is_prime": True, "is_elder": True,
    "mutations": "Hydrodynamic|None|None|None", "parent_mutations": _STORE_P,
    "elder_mutations": "",
}, 0)
_store_back = vault.get_parked_by_id(_store_id)
check("a store purchase row lands in sqlite at 0, the truth about a dino nobody buried",
      _store_back.get("elder_stacks") == 0,
      f"stored: {_store_back.get('elder_stacks')!r}")
check("...and that row really can re-pick the parent mutation it was sold",
      mc.slot_unlocked(_store_back, "p1")
      and [s for s in _INHERITED if mc.slot_unlocked(_store_back, s)] == _P)
expect_ok("...through the real validate, on the row sqlite handed back",
          lambda: mc.validate_slot_edit(_store_back, "p1", "Nocturnal"),
          "Nocturnal", "Wader")
check("...and the redeem would still hand the game the 0 it always did",
      int(vault._num(_store_back.get("elder_stacks"))) == 0)
_bare_id = vault.save_parked("76561199000000021", "d1", {
    "dino": "BP_Stegosaurus_C", "growth": 0.75, "is_prime": True, "is_elder": True,
    "mutations": "Hydrodynamic|None|None|None", "parent_mutations": _EMPTY4,
    "elder_mutations": "",
}, 0)
_bare_back = vault.get_parked_by_id(_bare_id)
check("a purchase with no Linaje Parental stays at 0 and stays shut",
      _bare_back.get("elder_stacks") == 0
      and [s for s in _INHERITED if mc.slot_unlocked(_bare_back, s)] == [])
_MOVED_E = _elder_col(ea1="Wader")
_moved_id = vault.save_parked("76561199000000021", "d1", {
    "dino": "BP_Stegosaurus_C", "growth": 0.75, "is_prime": True, "is_elder": True,
    "mutations": _EMPTY4, "parent_mutations": _EMPTY4, "elder_mutations": _MOVED_E,
}, 0)
_moved_back = vault.get_parked_by_id(_moved_id)
# The cost of the revert, pinned rather than glossed: an Anciano pick the legacy
# inventory editor allowed arrives locked, because the row records no entierro
# and the elder column is never read as proof. It was locked before this change
# too, and the alternative is granting the pawn elder replication stacks.
check("an inventory move that carried an Anciano A pick still lands at 0",
      _moved_back.get("elder_stacks") == 0
      and not mc.slot_unlocked(_moved_back, "ea1"),
      f"stored: {_moved_back.get('elder_stacks')!r}")
expect_ok("...and that pick can still be emptied for free",
          lambda: mc.validate_slot_edit(_moved_back, "ea1", "None"), "None", "Wader")
_omitted_back = _store_back
# The read-time derivation rescues the EDITOR on such a row -- that is the whole
# point of it -- and it deliberately does NOT move the number the redeem hands
# the game, because that one is read straight off the column.
check("the editor is rescued by the derivation, the stored number is not",
      mc.slot_unlocked(_omitted_back, "p1")
      and mc.effective_elder_stacks(_omitted_back) == 1
      and _omitted_back.get("elder_stacks") == 0)
# The whole reason the label fix needed no migration: the mod's own bytes go in
# and come back out unchanged, only the NAME the web gives a segment moved.
c4 = sqlite3.connect(dbpath2)
c4.execute("UPDATE parked_dinos SET elder_mutations=? WHERE id=9",
           (mod_encode({p: f"M{i}" for i, p in enumerate(MOD_ELDER_ORDER)}),))
c4.commit()
c4.close()
db9 = vault.get_parked_by_id(9)
check("a mod-written elder string round-trips through sqlite unchanged",
      mod_decode(db9["elder_mutations"])
      == {p: f"M{i}" for i, p in enumerate(MOD_ELDER_ORDER)})
_edited = mc.apply_slot_edit(db9, "ea3", "Wader")
ok_e, _ = vault.cas_update_mutations(9, "76561199000000001", db9, _edited)
check("editing ea3 through the web moves ONLY ElderMutationSlot3A in the stored row",
      ok_e is True
      and mod_decode(vault.get_parked_by_id(9)["elder_mutations"])
      == {**{p: f"M{i}" for i, p in enumerate(MOD_ELDER_ORDER)},
          "ElderMutationSlot3A": "Wader"},
      repr(mod_decode(vault.get_parked_by_id(9)["elder_mutations"])))

print("[11] no PrimeMeat is charged for a rejected edit (server.py ordering)")
_SERVER_SRC = open(os.path.join(os.path.dirname(__file__), "..", "server.py"),
                   encoding="utf-8").read()


def simulate_post(row_, slot, mutation, balance, cost=20000):
    """Mirror of me_vault_mutations_set's charge path. Returns
    (status, balance_after). Kept in step with server.py by the source-order
    assertions below."""
    try:
        new_value, current = mc.validate_slot_edit(row_, slot, mutation)
    except mc.MutationEditError:
        return 400, balance                     # rejected BEFORE any debit
    same = (mc.normalize_mutation_name(current) == mc.normalize_mutation_name(new_value)) \
        or (current == "None" and new_value == "None")
    if same:
        return 200, balance
    charge = 0 if new_value == "None" else cost
    if charge > balance:
        return 400, balance
    return 200, balance - charge


st, bal = simulate_post(lrow(0.30), "n2", "Nocturnal", 100000)
check("locked-slot edit is rejected 400 and charges nothing", st == 400 and bal == 100000)
st, bal = simulate_post(lrow(1.0, prime=False), "n4", "Nocturnal", 100000)
check("non-prime n4 edit is rejected 400 and charges nothing", st == 400 and bal == 100000)
st, bal = simulate_post(lrow(0.30, muts="None|Nocturnal|None|None"), "n2", "None", 100000)
check("clearing a locked slot succeeds and charges nothing", st == 200 and bal == 100000)
st, bal = simulate_post(lrow(0.30), "n1", "Nocturnal", 100000)
check("an ALLOWED edit still charges", st == 200 and bal == 80000)
st, bal = simulate_post(lrow(1.0, prime=True), "n4", "Nocturnal", 100000)
check("a prime's n4 edit at 100% still charges", st == 200 and bal == 80000)

# --- the entomb gate on the charge path --------------------------------------
_charged_locked = []
for _n, _sid in ((0, "p1"), (0, "ea1"), (0, "eb1"), (1, "ea1"), (1, "eb1"), (2, "eb1"),
                 ("abc", "p1"), (None, "ea4")):
    _st, _bal = simulate_post(row(stacks=_n), _sid, "Nocturnal", 100000)
    if _st != 400 or _bal != 100000:
        _charged_locked.append((_n, _sid, _st, _bal))
check("a locked inherited slot is rejected 400 and charges nothing, on every rung",
      not _charged_locked, f"(stacks, slot, status, balance) {_charged_locked!r}")
_free_clear = []
for _sid in mc.SLOT_IDS:
    _held = {"id": 1, "dino_class": "BP_Tyrannosaurus_C", "growth": 0.0, "is_prime": 0,
             "elder_stacks": 0, "mutations": "Wader|Wader|Wader|Wader",
             "parent_mutations": "Wader|Wader|Wader|Wader",
             "elder_mutations": "|".join(["Wader"] * 8)}
    _st, _bal = simulate_post(_held, _sid, "None", 100000)
    if _st != 200 or _bal != 100000:
        _free_clear.append((_sid, _st, _bal))
check("emptying ANY of the 16 slots on a fully locked dino is allowed and free",
      not _free_clear, f"(slot, status, balance) {_free_clear!r}")
st, bal = simulate_post(row(stacks=1), "p2", "Nocturnal", 100000)
check("an allowed inherited edit still charges", st == 200 and bal == 80000)
st, bal = simulate_post(row(stacks=3), "eb2", "Nocturnal", 100000)
check("an allowed elder B edit at 3 entombs still charges", st == 200 and bal == 80000)

# --- the read-time derivation on the charge path (block [4c]) ----------------
_derived = row(stacks=0, parent="Hemomania|None|None|None")
st, bal = simulate_post(_derived, "ea1", "Nocturnal", 100000)
check("a slot the columns did NOT prove is still 400 and still charges nothing",
      st == 400 and bal == 100000)
st, bal = simulate_post(_derived, "p2", "Nocturnal", 100000)
check("a slot the columns DID prove charges the normal price, not zero",
      st == 200 and bal == 80000)
st, bal = simulate_post(row(stacks=0, elder=_elder_col(ea2="Traumatic Thrombosis")),
                        "ea2", "None", 100000)
check("emptying a closed slot holding an unrecognised value is allowed and free",
      st == 200 and bal == 100000)
_derived_charged = []
for _sid in _EA + _EB:
    _st, _bal = simulate_post(_derived, _sid, "Nocturnal", 100000)
    if _st != 400 or _bal != 100000:
        _derived_charged.append((_sid, _st, _bal))
check("none of the eight Anciano slots is opened by a parent-only lineage",
      not _derived_charged, f"(slot, status, balance) {_derived_charged!r}")

_i_validate = _SERVER_SRC.find("mutation_catalog.validate_slot_edit(row, body.slot")
_i_debit = _SERVER_SRC.find('{"$inc": {"coins": -charge}}')
check("server.py validates BEFORE it debits PrimeMeat",
      _i_validate > 0 and _i_debit > 0 and _i_validate < _i_debit,
      f"validate@{_i_validate} debit@{_i_debit}")
check("the GET route publishes per-slot lock state",
      "mutation_catalog.slot_lock_map(row)" in _SERVER_SRC
      and '"slot_locks": locks' in _SERVER_SRC)
check("the GET route publishes the ladder for the UI legend",
      "mutation_catalog.growth_ladder_view()" in _SERVER_SRC)
check("the GET route publishes the ENTOMB ladder too",
      "mutation_catalog.entomb_ladder_view()" in _SERVER_SRC
      and '"entomb_ladder"' in _SERVER_SRC)
check("the GET route is exception-contained around the lock map",
      "[vault] slot lock map failed" in _SERVER_SRC)
# int(float(row["elder_stacks"])) sat OUTSIDE that try, so "abc" or "2.0" in a
# TEXT-typed column 500'd the whole editor instead of locking twelve slots.
check("the GET route no longer int(float(...))s the entomb column",
      "int(float(row.get(\"elder_stacks\") or 0))" not in _SERVER_SRC
      and "mutation_catalog.elder_stack_count(row)" in _SERVER_SRC)
# The legend prints this number as "tu dino: N entierros", so it must be the
# RECORDED count. The derived one can sit a rung above the truth -- a store dino
# proves 1 off its parent column without ever having been buried -- and printing
# that would be a lie the player can neither check nor act on. Which slots are
# usable travels in slot_locks instead.
check("the GET route publishes the RECORDED count, never the derived one",
      "stacks = mutation_catalog.elder_stack_count(row)" in _SERVER_SRC
      and "effective_elder_stacks" not in _SERVER_SRC)
check("the GET route's fail-closed fallback locks the inherited slots too",
      "entomb_unknown" in _SERVER_SRC and "LOCK_ENTOMB_UNREADABLE" in _SERVER_SRC)
# DRIVEN, not grepped: _dino_view is what the mutation-edit POST hands back, so
# anything that escapes it is a 500 on a save the player already paid for. _num
# was not enough on its own -- it catches TypeError/ValueError, but float("nan")
# and float("inf") SUCCEED, and int(nan) then raises ValueError, int(inf)
# OverflowError, and round() does the same on the growth column and on a diet
# one. Every column that reaches a number, against every shape a TEXT-typed or
# mod-written column can hold.
_VIEW_BAD = ("nan", "NaN", "-nan", "inf", "-inf", "Infinity", "1e400", "abc",
             "", "  ", None, True, False, [], {}, b"2", float("nan"),
             float("inf"), float("-inf"), 10**400, "2.0", "2", 2.0, 0)
_view_raised = []
for _col in ("elder_stacks", "growth", "diet_a", "diet_b", "diet_c",
             "health", "max_health"):
    for _bad in _VIEW_BAD:
        _vrow = {"id": 1, "dino_class": "BP_Tyrannosaurus_C", "growth": 1.0,
                 "elder_stacks": 3, "mutations": "", "parent_mutations": "",
                 "elder_mutations": "", "diet_a": 1.0, "diet_b": 1.0, "diet_c": 1.0}
        _vrow[_col] = _bad
        try:
            vault._dino_view(_vrow)
        except Exception as _e:                    # noqa: BLE001
            _view_raised.append((_col, repr(_bad), type(_e).__name__, str(_e)))
check("vault._dino_view cannot raise on any of those columns (the POST returns it)",
      not _view_raised, f"{_view_raised[:6]!r}")
# ...and the shapes that used to raise now answer the same thing the field
# already answers for a missing column: 0 entierros, and no percent at all.
_nan_view = vault._dino_view({"id": 1, "dino_class": "BP_Tyrannosaurus_C",
                              "growth": "nan", "elder_stacks": "inf",
                              "diet_a": float("nan"), "diet_b": 1.0, "diet_c": 1.0})
check("an unreadable entomb column reads 0, and an unreadable growth has no percent",
      _nan_view["elder_stacks"] == 0 and _nan_view["growth_pct"] is None
      and "a" not in _nan_view["diet_pct"] and _nan_view["diet_pct"]["b"] is not None,
      f"got: {_nan_view['elder_stacks']!r} {_nan_view['growth_pct']!r} {_nan_view['diet_pct']!r}")
# ...AND THE VIEW MUST ACTUALLY BE SENDABLE. Repairing growth_pct/elder_stacks
# was NOT enough: the RAW growth, stats and diet columns are echoed one key
# above them, sqlite REAL really can hold inf, and Starlette renders with
# allow_nan=False -- so a non-finite float there is still a 500 on the save that
# the mutation-edit POST returns this view from. Serialising is the only honest
# test; asserting the fields individually would miss the next one added.
_unsendable = {"id": 1, "dino_class": "BP_Tyrannosaurus_C",
               "growth": float("inf"), "health": float("nan"),
               "max_health": float("inf"), "diet_a": float("nan"),
               "diet_b": 1.0, "diet_c": float("-inf"), "elder_stacks": "nan"}
try:
    _json.dumps(vault._dino_view(_unsendable), allow_nan=False)
    _sendable_ok = True
except (ValueError, OverflowError) as _e:
    _sendable_ok, _sendable_err = False, _e
check("the whole view still renders as JSON when raw columns hold inf/NaN",
      _sendable_ok,
      f"the POST would answer 500: {_sendable_err!r}" if not _sendable_ok else "")
# ...and a well-formed row is echoed byte-for-byte, so the guard never edits data.
_sendable_wf = vault._dino_view({
    "id": 2, "dino_class": "BP_Tyrannosaurus_C", "growth": 0.58,
    "health": 120.5, "max_health": 910, "diet_a": 30, "diet_b": 40, "diet_c": 50,
    "elder_stacks": 2})
check("a well-formed row is echoed exactly as before the guard",
      _sendable_wf["growth"] == 0.58 and _sendable_wf["stats"]["health"] == 120.5
      and _sendable_wf["stats"]["max_health"] == 910
      and _sendable_wf["diet"] == {"a": 30, "b": 40, "c": 50},
      f"got growth={_sendable_wf['growth']!r} stats={_sendable_wf['stats']!r} "
      f"diet={_sendable_wf['diet']!r}")
# NOTHING WELL-FORMED MOVED. The same rows, before and after, still publish the
# integer they always did -- a TEXT "2.0" included, which is why _num was there.
_view_wellformed = [
    ({"elder_stacks": 3, "growth": 0.58}, 3, 58),
    ({"elder_stacks": "2.0", "growth": "0.75"}, 2, 75),
    ({"elder_stacks": "0", "growth": 1.0}, 0, 100),
    ({"elder_stacks": None, "growth": 0}, 0, 0),
    ({"elder_stacks": 2.9, "growth": 0.2499}, 2, 25),
    ({"elder_stacks": "", "growth": ""}, 0, 0),
]
_view_moved = []
for _over, _want_stacks, _want_pct in _view_wellformed:
    _vrow = {"id": 1, "dino_class": "BP_Tyrannosaurus_C", **_over}
    _got = vault._dino_view(_vrow)
    if (_got["elder_stacks"], _got["growth_pct"]) != (_want_stacks, _want_pct):
        _view_moved.append((_over, _got["elder_stacks"], _got["growth_pct"]))
check("...and every well-formed row still returns exactly what it did",
      not _view_moved, f"{_view_moved!r}")
check("the raising shape is gone from the source, both columns",
      'int(_num(r.get("elder_stacks")))' not in _VAULT_SRC
      and 'round(float(r.get("growth") or 0) * 100)' not in _VAULT_SRC
      and 'int(_finite(r.get("elder_stacks")))' in _VAULT_SRC)
# One shared definition of the displayed percent, so the route can never grow a
# second convention next to vault._dino_view's.
_MC_SRC = open(os.path.join(os.path.dirname(__file__), "..", "mutation_catalog.py"),
               encoding="utf-8").read()
check("the GET route publishes the SHARED displayed percent, not its own arithmetic",
      "mutation_catalog.growth_display_pct(growth)" in _SERVER_SRC
      and "int(growth * 100)" not in _SERVER_SRC)
# Every growth-to-percent multiplication in the catalog must live INSIDE the one
# helper — a second one anywhere else is the bug this whole block exists to stop.
_HELPER_SRC = _MC_SRC.split("def growth_display_pct(", 1)[-1].split("\n\n\n", 1)[0]
check("no truncating growth-to-percent arithmetic survives in either module",
      "int(growth * 100)" not in _MC_SRC and "int(growth * 100)" not in _SERVER_SRC
      and _MC_SRC.count("* 100") == _HELPER_SRC.count("* 100") > 0,
      f'"* 100" in module: {_MC_SRC.count("* 100")}, in the helper: {_HELPER_SRC.count("* 100")}')
_EDITOR_SRC = open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                                "src", "components", "inventory", "MutationEditor.jsx"),
                   encoding="utf-8").read()
check("the editor reads the server's per-slot lock state",
      "slot_locks" in _EDITOR_SRC and "lock?.reason" in _EDITOR_SRC)
check("the editor's legend is built from the server's ladder, not hardcoded",
      "growth_ladder" in _EDITOR_SRC and "requires_growth_pct" in _EDITOR_SRC
      and "0.25" not in _EDITOR_SRC and "0.75" not in _EDITOR_SRC)
# The clear button's own disabled expression — everything from its <button> to
# its test id — must be free of any lock term, or a locked slot would trap
# whatever it holds. Asking for a CONFIRMATION first is allowed (below); staying
# disabled is not.
_clear_btn = _EDITOR_SRC.split('data-testid="mutation-picker-clear"')[0].rsplit("<button", 1)[-1]
_clear_disabled = _clear_btn.split("disabled=", 1)[-1]
check("the editor keeps the free clear available on a locked slot",
      _EDITOR_SRC.count('data-testid="mutation-picker-clear"') == 1
      and _clear_disabled.lstrip().startswith("{busy || !hasValue}")
      and "lock" not in _clear_disabled.lower(),
      f"clear disabled expr: {_clear_disabled.strip()!r}")
check("the clear button's enable test is the slot's VALUE, not the lock",
      'const hasValue = !!slotValue && slotValue !== "None";' in _EDITOR_SRC)
# Clearing a LOCKED slot destroys player property that can never be put back
# (the same rule that locked the slot refuses every write into it, and a parked
# dino's growth never moves), so that one case takes a second, explicit press.
# An UNLOCKED slot keeps its one-press clear — no friction where it is undoable.
#
# WHAT A PLAYER CAN ACTUALLY DO WITH THESE BUTTONS IS NOT A GREP QUESTION and is
# not answered here. A double press, a close-and-reopen, and the one-press clear
# on an open slot are all proven by mounting the real component, in
#   web/frontend/src/components/inventory/MutationEditor.clearConfirm.test.js
#   (cd web/frontend && CI=true npx craco test --watchAll=false)
# An earlier version of this block grepped for the exact onClick that let a
# double press through — it PINNED the defect instead of catching it. What is
# left here is only structure a grep can judge honestly.
_PICKER_SRC = _EDITOR_SRC.split("function PickerModal(", 1)[-1] \
    .split("export function MutationEditor", 1)[0]
_PARENT_SRC = _EDITOR_SRC.split("export function MutationEditor", 1)[-1]
# THE ASK IS ARMED BY REVERSIBILITY, NOT BY THE LOCK (2026-07-26). This check
# used to pin the expression `hasValue && (isLocked || clearClosesSlots)` letter
# for letter, which PINNED A DEFECT: an OPEN 1ª propia holding one of the game's
# unlockable mutations is neither locked nor closing anything, and the save
# refuses to write that name back into it, so the plain one-press "Quitar" threw
# it away for good. What is asserted now is that the condition consults the
# server's per-ranura reversibility answer at all; whether a player gets one
# press or two is proven by mounting the component (see the two test files named
# below), never by this grep.
check("a clear that cannot be walked back asks before it clears",
      "const clearIsIrreversible = hasValue && (isLocked || clearClosesSlots"
      " || clearBlocksRestore);" in _EDITOR_SRC
      and "const clearBlocksRestore = lockMissing || !!lock?.clear_blocks_restore;"
      in _EDITOR_SRC
      and 'data-testid="mutation-clear-confirm"' in _EDITOR_SRC)
# ...AND A RANURA THE PAYLOAD NEVER DESCRIBED HAS NO ANSWER TO GIVE. An absent
# lock OBJECT made every one of those questions read false at once, so a ranura
# holding a one-way value took the single unguarded press on BOTH controls. The
# server warns whenever it cannot tell (_blocks_restore) and the page now does
# the same. Structure only here; the presses themselves are driven in
#   web/frontend/src/components/inventory/MutationEditor.oneWayPress.test.js
check("...and a ranura with no entry at all in slot_locks fails closed",
      "const lockMissing = lock == null;" in _EDITOR_SRC
      and 'const clearKind = lockMissing ? "unknown"' in _EDITOR_SRC
      and "(clearClosesSlots || lockMissing)" in _EDITOR_SRC)
# THE TWO REASONS CAN BOTH BE TRUE AT ONCE, and the wording has to carry both:
# a last-proof heredada holding a value the ranura refuses on its own terms is
# not made whole by entombing the dino again.
check("a closing clear over an unacceptable value says BOTH things",
      'valueBlocksRestore ? "lineage_value" : "lineage"' in _EDITOR_SRC
      and "const valueBlocksRestore = !!lock?.overwrite_blocks_restore;" in _EDITOR_SRC
      and "lineage_value: (held) =>" in _EDITOR_SRC)
# THE SECOND IRREVERSIBLE CASE, added 2026-07-26 with the read-time derivation.
# An OPEN heredada that is the row's last proof of its own lineage closes all
# four the instant it is emptied, so it takes the same two-press path. The rule
# is the SERVER's (slot_locks[slot].clear_closes) -- this file must not re-derive
# it, or the two answers drift.
check("an OPEN slot that would close its family asks too, on the server's word",
      "clearClosesSlots = !isLocked && !!lock?.clear_closes" in _EDITOR_SRC
      and "clear_closes" in _MC_SRC
      and _EDITOR_SRC.count("lineage_generation") == 0)
check("the press that asks and the press that removes are DIFFERENT controls",
      _EDITOR_SRC.count('data-testid="mutation-picker-clear"') == 1
      and _EDITOR_SRC.count('data-testid="mutation-clear-confirm"') == 1
      and "setConfirmClear(true) : onClear()" not in _EDITOR_SRC,
      "the arming press and the removing press are the same button again")
_confirm_btn = _EDITOR_SRC.split('data-testid="mutation-clear-confirm"')[0].rsplit("<button", 1)[-1]
# It saves the value the QUESTION was armed with, never the picker's live
# selection: a pick changed after arming must not be written behind the sentence
# that described the old one. And it re-arms nothing, or the panel's own control
# would become a second thing to press twice.
check("the control that actually acts saves the armed value, no re-arming",
      "onClick={onConfirmPending}" in _confirm_btn
      and "onConfirmPending={() => pending && doSet(editingSlot, pending.value)}"
      in _EDITOR_SRC, f"confirm button attrs: {_confirm_btn.strip()!r}")
check("the confirm step states plainly that it cannot be undone while locked",
      'data-testid="mutation-clear-warning"' in _EDITOR_SRC
      and "no podrás volver a ponerle nada mientras la ranura siga bloqueada" in _EDITOR_SRC)
check("the warning no longer tells the player to press the same button again",
      "Pulsa otra vez para confirmar" not in _EDITOR_SRC)
check("a REVERSIBLE clear keeps its ONE press (the ask is gated on that alone)",
      '? (armedForClear ? onCancelPending() : onArm("clear", "None"))' in _EDITOR_SRC
      and ": onClear())" in _EDITOR_SRC
      and _EDITOR_SRC.count('onArm("clear"') == 1)
# ...and so does a REVERSIBLE paid swap. The same shape, on the other button:
# arm only when the value cannot come back, act only from the panel.
check("a REVERSIBLE overwrite keeps its ONE press too",
      "if (!overwriteIsIrreversible) { onPick(selected); return; }" in _EDITOR_SRC
      and 'onArm("overwrite", selected)' in _EDITOR_SRC
      and _EDITOR_SRC.count('onArm("overwrite"') == 1)
# The confirm is the PARENT's state. Held inside the picker it survived a close
# and a reopen of the SAME slot: its reset effect was keyed on [slotId, open],
# `open` is passed as a literal, and closing the picker is not a remount
# (framer-motion holds a leaving child and cancels the exit when it comes back),
# so the picker reopened already armed and the next press removed the mutation.
check("the confirm state cannot live in the picker, where a reopen inherits it",
      "const [pending, setPending] = useState(null);" in _PARENT_SRC
      and _PICKER_SRC.count("setPending") == 0
      and "const [pending" not in _PICKER_SRC
      and "[slotId, open])" not in _EDITOR_SRC,
      "the picker still owns the confirm, or still resets it on a dep that cannot change")
check("every open of the picker goes through the one place that wipes it",
      "const openPicker = (slotId) => {" in _PARENT_SRC
      and "setPending(null);" in _PARENT_SRC.split("const openPicker = ", 1)[-1]
                                            .split("};", 1)[0]
      and "onEdit={() => openPicker(sid)}" in _PARENT_SRC
      and "setEditingSlot(sid)" not in _PARENT_SRC)
check("the picker's own scratch state resets on a token that really changes",
      "useEffect(() => { setQuery(\"\"); setSelected(null); }, [slotId, openToken]);" in _PICKER_SRC
      and "openToken={pickerOpens}" in _PARENT_SRC)
check("clearing stays FREE on both paths",
      _EDITOR_SRC.count("(gratis)") == 2)
# A parked dino's growth is FROZEN: vault.park writes it once at INSERT and
# every other UPDATE against parked_dinos touches only redeem_pending_*,
# custom_name and the three mutation columns. So no copy may promise a locked
# slot opens by itself — it opens when the player redeems it, grows it in game
# and parks it again.
check("no copy promises a locked slot opens by itself",
      "se abrirá sola" not in _EDITOR_SRC and "se abrirá solo" not in _EDITOR_SRC)
# ...and "grow it and park it again" is only TRUE for the growth rung. slot_lock
# answers "prime" BEFORE it looks at growth, so a non-Prime dino gets that code
# on n4 at ANY growth — telling that owner to redeem his dino and raise it sends
# a real dinosaur back into the game for a slot that will still be closed. So
# these checks read the copy PER LOCK CODE instead of grepping the file for the
# sentence: the codes come out of the REAL rule, and each one's copy is judged
# on its own. A grep for the sentence passes no matter who is shown it.
#
# These are still source checks. What a player ACTUALLY ends up reading is
# proven by mounting the real component, in
#   web/frontend/src/components/inventory/MutationEditor.lockCopy.test.js
#   (cd web/frontend && CI=true npx craco test --watchAll=false)
# which presses the slot button under each lock code and reads the panel back.
# Keep the two in step: this half pins WHICH codes exist, that half pins what
# each one shows.
_HOWTO_BLOCK = _EDITOR_SRC.split("const LOCK_HOWTO = {", 1)[-1].split("\n};", 1)[0]
_HOWTO = dict(re.findall(r'(\w+):\s*\n?\s*"((?:[^"\\]|\\.)*)"', _HOWTO_BLOCK))
_GROW_IT = "hacerlo crecer en el juego y volver a guardarlo"
# Every lock code the backend can actually put on the wire, from the rule itself.
_CODES = {mc.slot_lock(lrow(g, p), s)[0]
          for g in (0.0, 0.24, 0.5, 0.75, 1.0) for p in (False, True)
          for s in ("n1", "n2", "n3", "n4")
          if mc.slot_lock(lrow(g, p), s) is not None}
_CODES |= {mc.slot_lock(lrow(None), "n1")[0]}      # unreadable growth
_CODES |= {mc.slot_lock(row(stacks=n), s)[0]
           for n in (0, 1, 2, "abc", None)
           for s in _INHERITED
           if mc.slot_lock(row(stacks=n), s) is not None}
check("the backend emits exactly the five lock codes the editor knows of",
      _CODES == {"prime", "growth", "growth_unknown", "entomb", "entomb_unknown"},
      f"codes: {sorted(_CODES)}")
check("the locked-slot how-to is keyed on the server's lock code, not unconditional",
      "const lockHowto = " in _EDITOR_SRC and "LOCK_HOWTO[lock" in _EDITOR_SRC
      and "{lockHowto && (" in _EDITOR_SRC
      and _EDITOR_SRC.count(_GROW_IT) == 1)
check('"grow it and park it again" is shown ONLY under the growth-rung code',
      [c for c, t in _HOWTO.items() if _GROW_IT in t] == ["growth"],
      f"codes carrying it: {[c for c, t in _HOWTO.items() if _GROW_IT in t]}")
check("the growth-rung copy still says what actually opens that slot",
      _GROW_IT in _HOWTO.get("growth", ""))
# The Prime lock is not a growth lock. Its copy has to say so, or the player
# pays a redeem to learn it.
check("the Prime lock has its own copy and it denies that growing helps",
      "crecimiento" in _HOWTO.get("prime", "")
      and "nunca" in _HOWTO.get("prime", "")
      and _GROW_IT not in _HOWTO.get("prime", ""),
      f"prime copy: {_HOWTO.get('prime')!r}")
check("an unreadable growth is NOT told to go grow the dino",
      _GROW_IT not in _HOWTO.get("growth_unknown", ""))
check("the editor carries copy only for codes the backend can send",
      set(_HOWTO) <= _CODES, f"unknown keys: {sorted(set(_HOWTO) - _CODES)}")
# The entomb lock is not a growth lock either. Its copy has to send the player
# to the right action, and elder_stacks is as frozen on a parked row as growth
# is (written once, at INSERT), so it may not promise the slot opens by itself.
_BURY_IT = "enterrarlo en el juego las veces que haga falta y volver a guardarlo"
check("the entomb lock has its own copy and it names burying, not growing",
      _BURY_IT in _HOWTO.get("entomb", "")
      and _GROW_IT not in _HOWTO.get("entomb", ""),
      f"entomb copy: {_HOWTO.get('entomb')!r}")
check("the entomb copy says the count is the one it had when it was stored",
      "tenía al guardarlo" in _HOWTO.get("entomb", ""))
check("an unreadable entomb count is NOT told to go bury the dino",
      _BURY_IT not in _HOWTO.get("entomb_unknown", ""))
check('"grow it and park it again" is still shown ONLY under the growth code',
      [c for c, t in _HOWTO.items() if _GROW_IT in t] == ["growth"])
check("the editor draws all four families, inherited ones included",
      all(f'"{k}"' in _EDITOR_SRC for k in ("child", "parent", "elder_a", "elder_b"))
      and '"ea1", "ea2", "ea3", "ea4"' in _EDITOR_SRC
      and '"eb1", "eb2", "eb3", "eb4"' in _EDITOR_SRC
      and '"p1", "p2", "p3", "p4"' in _EDITOR_SRC)
check("the editor never writes the entomb requirement down itself",
      "entomb_ladder" in _EDITOR_SRC and "requires_entombs" in _EDITOR_SRC)
check("the count chip still counts the slots that are DRAWN",
      "VISIBLE_SLOTS.filter" in _EDITOR_SRC
      and "const VISIBLE_SLOTS = GROUPS.flatMap((g) => g.slots);" in _EDITOR_SRC)
# ...and its DENOMINATOR is what this dino can actually reach, not a hardcoded
# sixteen. A never-buried dino can only ever fill four of the sixteen, so
# "2/16" told him fourteen ranuras were free when two were.
check("the chip's denominator is derived, never the constant sixteen",
      "const availableCount = slots" in _EDITOR_SRC
      and "lockFor(sid)?.locked" in _EDITOR_SRC
      and "VISIBLE_SLOTS.length} activas" not in _EDITOR_SRC
      and "/16" not in _EDITOR_SRC)
check("the duplicate pre-check still spans the whole payload, not the drawn list",
      "Object.entries(slots || {})" in _EDITOR_SRC)
check("the ladder legend names the growth it actually counts",
      "crecimiento que tenía al guardarlo" in _EDITOR_SRC)
check("the reassurance line no longer contradicts the button beneath it",
      "No pierdes nada de lo que ya tiene guardado" not in _EDITOR_SRC
      and "Lo que ya tiene guardado sigue ahí mientras tú no lo quites." in _EDITOR_SRC)
print("[12] unlockable mutations are not offered in n1/n3 (owner ruling 2026-07-27)")
# THE SET IS THE GAME'S OWN bHasRequirement FLAG, decoded from LIN's prod server
# exe — see the block over mutation_catalog.HIDDEN for the RVAs and for how each
# registry position was tied to a name. Pinned here by name AND by size, because
# every name in it blocks a mutation on two ranuras: a wrong one denies a player
# something he is entitled to and gives him no way to tell why.
_UNLOCKABLE = ["Osteophagic", "Enhanced Digestion", "Reinforced Tendons",
               "Reniculate Kidneys", "Multichambered Lungs", "Augmented Tapetum",
               "Heightened Ghrelin"]
check("the unlockable set is exactly the seven bHasRequirement names",
      mc.HIDDEN == frozenset(_UNLOCKABLE) and len(mc.HIDDEN) == 7,
      f"got: {sorted(mc.HIDDEN)!r}")
check("every one of them is a real catalog name, spelled the catalog's way",
      all(mc.canonical_mutation_name(n) == n for n in _UNLOCKABLE)
      and set(_UNLOCKABLE) <= set(mc.PICKABLE))
check("the ranuras closed to them are exactly n1 and n3",
      mc.HIDDEN_BLOCKED_SLOTS == frozenset({"n1", "n3"}))
# The oracle classifies all 43 registry entries, so no catalog name is left
# unclassified. If that ever stops being true, the unclassified one must stay
# OFFERED — is_hidden answers False for anything it does not recognise.
check("an unrecognised name is treated as NOT unlockable (never blocked on a guess)",
      mc.is_hidden("Some Name That Does Not Exist") is False
      and mc.is_hidden("") is False and mc.is_hidden(None) is False)
check("the membership test goes through the normaliser, not a raw compare",
      mc.is_hidden("AugmentedTapetum") and mc.is_hidden("augmented  tapetum".replace("  ", " "))
      and mc.is_hidden("reniculate_kidneys"))

# --- the offer matrix ---------------------------------------------------------
# row() is a full-grown Prime with 3 entombs, so every ladder is open and the
# only rule that can refuse anything here is this one.
_wrongly_allowed, _wrongly_refused = [], []
for _n in _UNLOCKABLE:
    for _sid in ("n1", "n3"):
        try:
            mc.validate_slot_edit(row(), _sid, _n)
            _wrongly_allowed.append((_sid, _n))
        except mc.MutationEditError:
            pass
    for _sid in ("n2", "n4", *_INHERITED):
        try:
            mc.validate_slot_edit(row(), _sid, _n)
        except mc.MutationEditError as e:
            _wrongly_refused.append((_sid, _n, str(e)))
check("n1 and n3 refuse every unlockable name",
      not _wrongly_allowed, f"allowed: {_wrongly_allowed!r}")
check("n2, n4 and all TWELVE inherited ranuras accept every unlockable name",
      not _wrongly_refused, f"refused: {_wrongly_refused!r}")
_over_blocked = []
for _n in mc.PICKABLE:
    if _n in mc.HIDDEN or _n in mc.HERBIVORE_ONLY:
        continue
    for _sid in ("n1", "n3"):
        try:
            mc.validate_slot_edit(row(), _sid, _n)
        except mc.MutationEditError as e:
            _over_blocked.append((_sid, _n, str(e)))
check("n1 and n3 still take every OTHER diet-legal name",
      not _over_blocked, f"{_over_blocked!r}")
# The HERBIVORE half of the same sweep. The diet matrix in block [1] moved its
# accept side to n2 (two CARNI_ONLY names are unlockables and would be refused on
# n1 for a reason that has nothing to do with diet), so n1/n3 acceptance has to
# be re-asserted here for BOTH diets or this change would have quietly deleted
# half that coverage.
_herb_blocked = []
for _n in mc.PICKABLE:
    if _n in mc.HIDDEN or _n in mc.CARNIVORE_ONLY:
        continue
    for _sid in ("n1", "n3"):
        try:
            mc.validate_slot_edit(row(cls="BP_Triceratops_C"), _sid, _n)
        except mc.MutationEditError as e:
            _herb_blocked.append((_sid, _n, str(e)))
check("a herbivore's n1 and n3 still take every OTHER name it can carry",
      not _herb_blocked, f"{_herb_blocked!r}")

# --- what the GET hands the picker -------------------------------------------
_rex_map = mc.slot_catalog_map("BP_Tyrannosaurus_C")
_trike_map = mc.slot_catalog_map("BP_Triceratops_C")
check("the per-ranura map covers all 16 ranuras", set(_rex_map) == set(mc.SLOT_IDS))
# WHAT THESE TWO PIN, and why they no longer pin integers. The rule is "n1 and n3
# lose EXACTLY the unlockables this species could have carried, and no other
# ranura loses anything at all". Frozen sizes (24/31, 25/30) stated that rule
# only in silhouette: they broke on 2026-07-27 for a reason that was not a
# defect -- the catalog grew by five names -- and they could never have caught a
# swap that keeps the size and changes the membership.
#
# THE EXPECTATION IS BUILT FROM THE HAND LISTS, not from the module sets it is
# judging: CARNI_ONLY / HERBI_ONLY (block [1]) and _UNLOCKABLE (the seven
# bHasRequirement names, pinned by name at the head of this block). Reading
# mc.HIDDEN or mc.CARNIVORE_ONLY here would move the expectation in lockstep with
# the very data a defect corrupts -- swap a member of HIDDEN and both sides slide
# together and this scores green. The hand lists are themselves pinned equal to
# the module sets, so the green case is identical and only the defect diverges.
# PICKABLE is read live on purpose: the pool GROWING is not a defect, and pinning
# it is what made these checks break on 2026-07-27 for no reason.
#
# It is strictly stronger than the counts were: it names every member, and it
# walks all FOURTEEN untouched ranuras instead of the six the size assert reached.
_UNLOCKABLE_SET = frozenset(_UNLOCKABLE)
_rex_diet = set(mc.PICKABLE) - set(HERBI_ONLY)        # what a carnivore may carry
_rex_lost = _rex_diet & _UNLOCKABLE_SET               # all seven, on a carnivore
check("a carnivore's n1/n3 lose all SEVEN and nothing else loses any",
      len(_rex_lost) == 7
      and set(_rex_map.get("n1", ())) == set(_rex_map.get("n3", ()))
      == _rex_diet - _rex_lost
      and all(set(_rex_map.get(s, ())) == _rex_diet
              for s in mc.SLOT_IDS if s not in ("n1", "n3")),
      f'n1={len(_rex_map.get("n1", ()))} n2={len(_rex_map.get("n2", ()))} '
      f'lost={sorted(_rex_lost)!r} '
      f'n1_extra={sorted(set(_rex_map.get("n1", ())) - (_rex_diet - _rex_lost))!r}')
# Only 5 of the 7 are diet-legal on a herbivore (Osteophagic and Augmented
# Tapetum are carnivore-only), so a herbivore's n1 loses 5, not 7. The two rules
# compose; neither is applied twice.
_trike_diet = set(mc.PICKABLE) - set(CARNI_ONLY)
_trike_lost = _trike_diet & _UNLOCKABLE_SET
check("a herbivore's n1 loses only the five it could ever have carried",
      len(_trike_lost) == 5
      and set(_trike_map.get("n1", ())) == set(_trike_map.get("n3", ()))
      == _trike_diet - _trike_lost
      and all(set(_trike_map.get(s, ())) == _trike_diet
              for s in mc.SLOT_IDS if s not in ("n1", "n3")),
      f'n1={len(_trike_map.get("n1", ()))} n2={len(_trike_map.get("n2", ()))} '
      f'lost={sorted(_trike_lost)!r}')
# The two ranuras really do differ from each other in the way the rule says, so
# neither of the asserts above can be passing on an accident of equal sizes.
check("the herbivore loses two FEWER names than the carnivore, and they are the two carnivore-only unlockables",
      _rex_lost - _trike_lost == mc.HIDDEN & mc.CARNIVORE_ONLY
      and _rex_lost - _trike_lost == _UNLOCKABLE_SET & set(CARNI_ONLY)
      and _rex_lost - _trike_lost == {"Osteophagic", "Augmented Tapetum"},
      f"{sorted(_rex_lost - _trike_lost)!r}")
check("no unlockable name appears in ANY n1/n3 list",
      not [n for s in ("n1", "n3") for m in (_rex_map, _trike_map)
           for n in m[s] if n in mc.HIDDEN])
check("everything the map offers, the POST would actually accept",
      all(set(_rex_map[s]) == mc.allowed_names_for_slot("BP_Tyrannosaurus_C", s)
          for s in mc.SLOT_IDS))
check("each ranura gets its own list object (no shared aliasing)",
      _rex_map["n2"] is not _rex_map["n4"])
# WHAT ACTUALLY GOES ON THE WIRE is the sparse form: only the ranuras whose list
# DIFFERS from the shared catalog, because the other fourteen are identical to it
# and to each other. Sending all sixteen was ~11 KB of duplicated names on every
# open of the editor, on a route with no gzip middleware in front of it.
_rex_over = mc.slot_catalog_overrides("BP_Tyrannosaurus_C")
_trike_over = mc.slot_catalog_overrides("BP_Triceratops_C")
check("only the ranuras that actually differ travel",
      set(_rex_over) == set(_trike_over) == {"n1", "n3"}, f"{sorted(_rex_over)!r}")
check("the sparse form says the same thing as the complete one",
      all(_rex_over.get(s, sorted(mc.allowed_names_for_class("BP_Tyrannosaurus_C")))
          == _rex_map[s] for s in mc.SLOT_IDS))
# Both of the generic-pool cases below name their expected list the same way the
# two diet cases above do: live PICKABLE minus the HAND-pinned sets, so a catalog
# that grows again moves them by itself while a wrong MEMBER is still caught and
# not just a wrong size. A gallimimus carries neither diet's exclusive names.
# .get() everywhere a key may be absent: the whole point of the first clause is
# that the override map can come back EMPTY, and an eager f-string detail that
# subscripts it would turn a clean red into a KeyError that kills the run.
_gen_diet = set(mc.PICKABLE) - set(CARNI_ONLY) - set(HERBI_ONLY)
_gen_lost = _gen_diet & _UNLOCKABLE_SET
_galli_over = mc.slot_catalog_overrides("BP_Gallimimus_C")
check("a gallimimus (generic-only) still trims its n1/n3",
      set(_galli_over) == {"n1", "n3"}
      and len(_gen_lost) == 5
      and set(_galli_over.get("n1", ())) == set(_galli_over.get("n3", ()))
      == _gen_diet - _gen_lost,
      f'ranuras={sorted(_galli_over)!r} n1={len(_galli_over.get("n1", ()))} '
      f'lost={sorted(_gen_lost)!r}')
# An unknown species falls back to the generic pool; it must still trim, and must
# never come back empty (an empty n1 list would offer the player nothing at all).
_unk_over = mc.slot_catalog_overrides("BP_NotARealDino_C")
check("an unknown species still trims and never empties a ranura",
      set(_unk_over) == {"n1", "n3"}
      and len(_gen_lost) == 5
      and set(_unk_over.get("n1", ())) == _gen_diet - _gen_lost
      and _unk_over.get("n1"),
      f'ranuras={sorted(_unk_over)!r} n1={len(_unk_over.get("n1", ()))}')
import json as _json  # noqa: E402 - local to this size assertion
_wire = _json.dumps({"slot_catalog": _rex_over}, ensure_ascii=False)
check("the sparse payload is a fraction of the complete one",
      len(_wire) < 2000
      and len(_wire) < len(_json.dumps({"slot_catalog": _rex_map}, ensure_ascii=False)) / 5,
      f"sparse={len(_wire)}B full={len(_json.dumps({'slot_catalog': _rex_map}, ensure_ascii=False))}B")
# The shared `catalog` stays FULL on purpose: it is what the editor looks a
# STORED value up in to render its name and description.
check("the shared catalog still carries every diet-legal name, unlockables included",
      {c["name"] for c in mc.catalog_for_class("BP_Tyrannosaurus_C")} == _rex_diet
      and len(mc.catalog_for_class("BP_Tyrannosaurus_C")) == len(_rex_diet)
      and {c["name"] for c in mc.catalog_for_class("BP_Tyrannosaurus_C")
           if c["unlockable"]} == set(_UNLOCKABLE),
      f'catalog={len(mc.catalog_for_class("BP_Tyrannosaurus_C"))} diet={len(_rex_diet)}')

# --- the DIET rule is unchanged, and composes --------------------------------
expect_error("a herbivore is still refused a carnivore-only name in n2",
             lambda: mc.validate_slot_edit(row(cls="BP_Triceratops_C"), "n2", "Hemomania"),
             "carnívoros")
# BOTH reasons are true on a herbivore's n1. The answer must be the DIET one: a
# Triceratops can never carry Osteophagic in ANY ranura, so "put it in the 2nd
# instead" would be advice that cannot work.
expect_error("an unlockable carnivore-only name on a herbivore's n1 answers DIET",
             lambda: mc.validate_slot_edit(row(cls="BP_Triceratops_C"), "n1", "Osteophagic"),
             "carnívoros")
try:
    mc.validate_slot_edit(row(cls="BP_Triceratops_C"), "n1", "Osteophagic")
    _both_msg = ""
except mc.MutationEditError as e:
    _both_msg = str(e)
check("...and that message does NOT also send him to another ranura",
      "carnívoros" in _both_msg and "ranura" not in _both_msg, f"got: {_both_msg}")
try:
    mc.validate_slot_edit(row(), "n1", "Osteophagic")
    _slot_msg = ""
except mc.MutationEditError as e:
    _slot_msg = str(e)
check("the ranura refusal names both the closed ranuras and the open ones",
      all(o in _slot_msg for o in ("1ª", "3ª", "2ª", "4ª")), f"got: {_slot_msg}")
# Only two of the seven have a known unlock threshold, so the copy may not
# invent one for the other five.
check("...and it never invents an unlock task or a number",
      not re.search(r"\d\d", _slot_msg) and "salada" not in _slot_msg.lower())
check("no em-dash in any of the new player-facing copy",
      not any("—" in s for s in (_slot_msg, mc.hidden_notice(), mc.hidden_kept_notice())))

# The copy is GENERATED from HIDDEN_BLOCKED_SLOTS, so a re-ruling cannot leave a
# sentence still claiming the old ranuras — that is what makes it a one-line edit.
_orig_blocked = mc.HIDDEN_BLOCKED_SLOTS
try:
    mc.HIDDEN_BLOCKED_SLOTS = frozenset({"n2"})
    _flipped = mc._hidden_reason("Osteophagic")
    _flipped_notice = mc.hidden_notice()
finally:
    mc.HIDDEN_BLOCKED_SLOTS = _orig_blocked
check("the Spanish copy follows the rule instead of restating it",
      "2ª ranura propia" in _flipped and "2ª" not in _flipped.split("Ponla")[1]
      and "2ª ranura propia" in _flipped_notice, f"got: {_flipped}")
check("...and the real ruling is back afterwards",
      mc.HIDDEN_BLOCKED_SLOTS == frozenset({"n1", "n3"})
      and "1ª ni en la 3ª" in mc._hidden_reason("Osteophagic"))

# --- AN EXISTING UNLOCKABLE IN n1 IS NEVER BROKEN ----------------------------
# Parked rows are captured verbatim off live dinos that legitimately EARNED
# these, and the store / inventory lanes can write one into n1 too. This rule is
# stricter than the mod's own write path (validateMutationForSid takes no slot
# argument at all), so it may only ever refuse NEW writes. Nothing is wiped,
# nothing is taken off screen, and removing it stays free.
_held = row(muts="Osteophagic|None|None|None")
check("the stored value still reads back out of n1",
      mc.slots_from_row(_held)["n1"] == "Osteophagic")
check("it still counts as an active mutation", mc.active_count(_held) == 1)
check("this rule never LOCKS the ranura (the two ladders still decide that)",
      mc.slot_lock(_held, "n1") is None and mc.slot_unlocked(_held, "n1"))
check("the editor can still render its name and its Spanish description",
      any(c["name"] == "Osteophagic" and c["description"]
          for c in mc.catalog_for_class("BP_Tyrannosaurus_C")))
# expect_ok, not a bare call: every one of these MUST be allowed, and a bare
# call turns a regression into a traceback that takes the whole run down and
# hides which rule broke (the reason expect_ok exists at the top of this file).
expect_ok("removing it is allowed",
          lambda: mc.validate_slot_edit(_held, "n1", "None"), "None", "Osteophagic")
_st, _bal = simulate_post(_held, "n1", "None", 100000)
check("...and removing it is FREE", _st == 200 and _bal == 100000)
expect_ok("re-sending the value already in the ranura is not refused",
          lambda: mc.validate_slot_edit(_held, "n1", "Osteophagic"), "Osteophagic")
_st, _bal = simulate_post(_held, "n1", "Osteophagic", 100000)
check("...and that no-op charges nothing", _st == 200 and _bal == 100000)
expect_ok("a camel-case stored capture is recognised as the same value too",
          lambda: mc.validate_slot_edit(row(muts="AugmentedTapetum|None|None|None"),
                                        "n1", "Augmented Tapetum"), "Augmented Tapetum")
expect_error("a DIFFERENT unlockable still cannot be written into n1",
             lambda: mc.validate_slot_edit(_held, "n1", "Reinforced Tendons"),
             "desbloquearla")
# COPYING IT INTO n3 IS REFUSED FOR THE OTHER REASON NOW, and that is the fix of
# 2026-07-26: the dino already carries it in n1, so it is a DUPLICATE, and the
# duplicate scan runs first. The old answer sent him to "la 2ª o la 4ª" for a
# mutation he already owns, which is advice he cannot act on. That n3 refuses a
# first-time unlockable on its own is pinned by the offer matrix above.
expect_error("the held one cannot be copied into n3 either (as a duplicate)",
             lambda: mc.validate_slot_edit(_held, "n3", "Osteophagic"),
             "duplicadas")
_after = mc.apply_slot_edit(_held, "n2", "Nocturnal")
check("editing another ranura leaves the held unlockable exactly where it was",
      mc.split_segments(_after["mutations"], 4)[0] == "Osteophagic")
# Every one of the seven, in both closed ranuras, survives being stored there.
_broken_rows = []
for _n in _UNLOCKABLE:
    for _sid, _col in (("n1", 0), ("n3", 2)):
        _segs = ["None"] * 4
        _segs[_col] = _n
        _r = row(muts=mc.join_segments(_segs))
        if mc.slots_from_row(_r)[_sid] != _n or mc.active_count(_r) != 1:
            _broken_rows.append((_sid, _n))
        if simulate_post(_r, _sid, "None", 100000) != (200, 100000):
            _broken_rows.append((_sid, _n, "clear not free"))
check("all seven survive in both closed ranuras, and all clear for free",
      not _broken_rows, f"{_broken_rows!r}")

# --- a refused write is never charged ----------------------------------------
_st, _bal = simulate_post(row(), "n1", "Osteophagic", 100000)
check("a refused unlockable write is 400 and charges nothing",
      _st == 400 and _bal == 100000)
_charged = []
for _n in _UNLOCKABLE:
    for _sid in ("n1", "n3"):
        if simulate_post(row(), _sid, _n, 100000) != (400, 100000):
            _charged.append((_sid, _n))
check("...on every one of the seven, in both ranuras", not _charged, f"{_charged!r}")
_st, _bal = simulate_post(row(), "n2", "Osteophagic", 100000)
check("the same name in n2 still charges the normal price", _st == 200 and _bal == 80000)

# --- BOTH LADDERS ARE UNTOUCHED, re-walked rather than trusted ---------------
# This rule sits on a THIRD axis (which names a ranura may be GIVEN). It must not
# have moved either of the other two, and it must never LOCK anything.
check("the growth ladder still reads 25 / 50 / 75 / 75+Prime",
      list(mc.GROWTH_LADDER) == [("n1", 0.25, False), ("n2", 0.50, False),
                                 ("n3", 0.75, False), ("n4", 0.75, True)])
check("the entomb ladder still reads 1,1,1,1 / 2,2,2,2 / 3,3,3,3",
      list(mc.ENTOMB_LADDER) == [("p1", 1), ("p2", 1), ("p3", 1), ("p4", 1),
                                 ("ea1", 2), ("ea2", 2), ("ea3", 2), ("ea4", 2),
                                 ("eb1", 3), ("eb2", 3), ("eb3", 3), ("eb4", 3)])
_rungs = []
# 0.749 belongs on the OPEN side: the rung is measured against the percent the
# site shows (round -> 75%), so a dino whose own card says 75% gets the 75% rung.
# 0.744 shows 74% and is the real boundary. Both pinned here so this section
# re-walks the ladder as it actually is, not as it reads at a glance.
for _g, _p, _want in ((0.24, False, []), (0.25, False, ["n1"]),
                      (0.50, False, ["n1", "n2"]), (0.744, False, ["n1", "n2"]),
                      (0.749, False, ["n1", "n2", "n3"]),
                      (0.75, False, ["n1", "n2", "n3"]),
                      (1.0, False, ["n1", "n2", "n3"]),
                      (0.75, True, ["n1", "n2", "n3", "n4"])):
    if open_n(_g, _p) != _want:
        _rungs.append((_g, _p, open_n(_g, _p), _want))
check("every growth rung still opens exactly the same ranuras", not _rungs, f"{_rungs!r}")
_ent = []
for _n, _want in ((0, []), (1, _P), (2, _P + _EA), (3, _P + _EA + _EB)):
    if open_inherited(_n) != _want:
        _ent.append((_n, open_inherited(_n), _want))
check("every entomb rung still opens exactly the same ranuras", not _ent, f"{_ent!r}")
check("a fully grown, thrice-entombed Prime still has all 16 ranuras open",
      mc.unlocked_slots(row()) == frozenset(mc.SLOT_IDS))

# --- the contract the picker draws from --------------------------------------
check("the GET route publishes the per-ranura catalog, in the SPARSE form",
      "mutation_catalog.slot_catalog_overrides(" in _SERVER_SRC
      and '"slot_catalog"' in _SERVER_SRC
      and "mutation_catalog.slot_catalog_map(" not in _SERVER_SRC)
check("the GET route still publishes the FULL shared catalog beside it",
      "mutation_catalog.catalog_for_class(" in _SERVER_SRC and '"catalog"' in _SERVER_SRC)
check("the GET route publishes both explanatory sentences",
      '"unlockable_notice"' in _SERVER_SRC and '"unlockable_kept_notice"' in _SERVER_SRC)
check("the editor filters on the SERVER's list and holds no rule of its own",
      "meta?.slot_catalog?.[slotId]" in _EDITOR_SRC
      and "HIDDEN" not in _EDITOR_SRC
      and "Osteophagic" not in _EDITOR_SRC)
check("a name the ranura does not offer is left out, never drawn as 'En uso'",
      "allowedNorms.has(norm(c.name))" in _EDITOR_SRC
      and "const narrowed = offered.length < catalog.length;" in _EDITOR_SRC)
check("a payload without the field falls back to the full catalog (errs OPEN)",
      "Array.isArray(names) ? new Set(names.map(norm)) : null" in _EDITOR_SRC)
# TAILWIND SCANS web/frontend/src AS PLAIN TOKENS, comments and test titles
# included, and the bare adjective for "not shown" is a real utility
# (display:none) — tailwind.config.js names it in its own warning. That is why
# every wire field and every comment on this feature says "unlockable" instead.
# Pinned to the TWO pre-existing hits (one real overflow class, one older
# sentence about the card) so a rename cannot walk it back and ship CSS on a
# JS-only change.
check("the editor gained no new bare utility token for this concept",
      len(re.findall(r"\bhidden\b", _EDITOR_SRC)) == 2
      and _EDITOR_SRC.count("overflow-hidden") == 1
      and "card's hidden overflow" in _EDITOR_SRC,
      f'hits: {re.findall(r".{0,28}hidden.{0,12}", _EDITOR_SRC)!r}')
check("the catalog module records the oracle, not just the answer",
      "bHasRequirement" in _MC_SRC and "0xF7E6E8" in _MC_SRC
      and "TheIsleServer-24167035-B1BCBEE1.exe" in _MC_SRC
      and "0xF7E805" in _MC_SRC)

print("[13] the cold-audit wave (2026-07-26)")
# FOUR FINDINGS, all four real when the code was read:
#   1. an OPEN n1/n3 holding one of the seven took the plain one-press "Quitar",
#      because the confirmation was armed by the ranura being LOCKED -- and the
#      POST refuses to write that name back into it, so the press was one-way;
#   2. the refusal and the picker notice sent the player to the 2ª/4ª even when
#      those are locked on his dino, and answered a DUPLICATE with slot advice;
#   3. "keeps an unlockable" was inferred from "stored, and not in the offer
#      list", which is also true of a legacy or staff-granted name;
#   4. the oracle comment cited the per-dino unlock pool at +0x958.
# THE RULE ITSELF DID NOT MOVE: the seven names, the growth ladder and the entomb
# ladder are re-walked at the end of this block, not assumed.

_COL_KWARG = {"mutations": "muts", "parent_mutations": "parent",
              "elder_mutations": "elder"}


def row_holding(sid, name, cls="BP_Tyrannosaurus_C", **kw):
    """A full-grown, thrice-entombed row whose ONLY stored mutation is `name`,
    in ranura `sid` -- built through slot_column so the elder column stays
    interleaved and this helper cannot drift from the encoding."""
    col, idx, cnt = mc.slot_column(sid)
    segs = ["None"] * cnt
    segs[idx] = name
    return row(cls=cls, **{_COL_KWARG[col]: mc.join_segments(segs)}, **kw)


# --- 1. the guard is armed by REVERSIBILITY, not by the lock -----------------
# THE TRAP, pinned first: this ranura is OPEN and its clear closes nothing, so
# every flag the old guard consulted says "ordinary, one press" -- and the re-add
# is refused all the same.
_open_hidden = row(muts="Osteophagic|None|None|None")
_lm_oh = mc.slot_lock_map(_open_hidden)
check("the trap's shape: n1 is open and emptying it closes no ranura",
      _lm_oh["n1"]["locked"] is False and _lm_oh["n1"]["clear_closes"] is False)
_oh_cleared = dict(_open_hidden, **mc.apply_slot_edit(_open_hidden, "n1", "None"))
expect_error("...and yet putting it back afterwards really is refused",
             lambda: mc.validate_slot_edit(_oh_cleared, "n1", "Osteophagic"),
             "desbloquearla")
check("so the server flags that clear as one the player cannot walk back",
      _lm_oh["n1"]["clear_blocks_restore"] is True)
# The same name one ranura over is genuinely reversible and must stay a single
# press -- a warning on every clear would be no warning at all.
_n2_hidden = row(muts="None|Osteophagic|None|None")
_n2_cleared = dict(_n2_hidden, **mc.apply_slot_edit(_n2_hidden, "n2", "None"))
expect_ok("the same value in the 2ª really can be put back",
          lambda: mc.validate_slot_edit(_n2_cleared, "n2", "Osteophagic"), "Osteophagic")
check("...so that one is not flagged",
      mc.slot_lock_map(_n2_hidden)["n2"]["clear_blocks_restore"] is False)
check("an ordinary name in n1 is not flagged either",
      mc.slot_lock_map(row(muts="Nocturnal|None|None|None"))["n1"]["clear_blocks_restore"]
      is False)
# A legacy capture the catalog does not carry: the POST refuses it in EVERY
# ranura, so that clear is one-way too, and for a different reason.
#
# "Traumatic Thrombosis" is the real value this case is about, and it replaced
# "Cannibalistic" here on 2026-07-27 when the catalog started offering that one.
# The game removed Traumatic Thrombosis in 0.21.720 and the 2026-07-26 down
# window deleted it from Game.ini, so nothing can write it any more -- but the
# mod's validator still knows the name (block [8]) and vault.park captured it
# verbatim off dinos that had it, so parked rows genuinely still hold it and this
# ranura genuinely cannot take it back.
_legacy = row(muts="Traumatic Thrombosis|None|None|None")
check("a name the catalog never carried is flagged in an open ranura",
      mc.slot_lock_map(_legacy)["n1"]["clear_blocks_restore"] is True)
expect_error("...and the POST really would refuse to put it back",
             lambda: mc.validate_slot_edit(row(), "n1", "Traumatic Thrombosis"),
             "reconocida")
# A diet-illegal stored value (a herbivore holding a carnivore-only name) is the
# third way a ranura will not take its own value back.
_wrongdiet = row(cls="BP_Triceratops_C", muts="Hemomania|None|None|None")
check("a value the species cannot carry is flagged as well",
      mc.slot_lock_map(_wrongdiet)["n1"]["clear_blocks_restore"] is True)
check("a locked ranura that holds something is flagged",
      mc.slot_lock_map(row(growth=0.30, is_prime=0,
                           muts="None|None|Nocturnal|None"))["n3"]["clear_blocks_restore"]
      is True)
_last_proof = mc.slot_lock_map(row(stacks=0, parent="Hemomania|None|None|None"))["p1"]
check("the last-proof heredada is flagged by BOTH facts, and they agree",
      _last_proof["clear_closes"] is True
      and _last_proof["clear_blocks_restore"] is True, repr(_last_proof))
_empty_flagged = []
for _r in (row(), row(stacks=0), row(growth=0.1, is_prime=0), _open_hidden):
    _m, _s = mc.slot_lock_map(_r), mc.slots_from_row(_r)
    _empty_flagged += [sid for sid in mc.SLOT_IDS
                       if _s[sid] == "None" and _m[sid]["clear_blocks_restore"]]
check("an EMPTY ranura is never flagged, on any row",
      not _empty_flagged, f"{_empty_flagged!r}")
# THE FLAG HAS TO PREDICT THE POST, not merely look plausible: for every ranura
# and every name a row could hold, empty it for real and ask the real validator
# whether it goes back. One value per row, so no duplicate can muddy the answer
# (the duplicate rule is deliberately outside this flag -- it is walk-back-able).
_flag_wrong = []
for _cls in ("BP_Tyrannosaurus_C", "BP_Triceratops_C"):
    for _sid in mc.SLOT_IDS:
        for _name in (*mc.PICKABLE, "Cannibalistic", "Traumatic Thrombosis"):
            _r = row_holding(_sid, _name, cls=_cls)
            _flag = mc.slot_lock_map(_r)[_sid]["clear_blocks_restore"]
            _cleared = dict(_r, **mc.apply_slot_edit(_r, _sid, "None"))
            try:
                mc.validate_slot_edit(_cleared, _sid, _name)
                _really = False
            except mc.MutationEditError:
                _really = True
            if _flag is not _really:
                _flag_wrong.append((_cls, _sid, _name, _flag, _really))
check("the flag matches what the POST really does, over every ranura and name",
      not _flag_wrong, f"{len(_flag_wrong)} mismatches, first: {_flag_wrong[:3]!r}")
# It is ADVICE, never a gate: clearing stays allowed and free in every one of
# these cases, which is the rule this whole feature is built on.
_not_free = []
for _r, _sid in ((_open_hidden, "n1"), (_legacy, "n1"), (_wrongdiet, "n1"),
                 (row(stacks=0, parent="Hemomania|None|None|None"), "p1"),
                 (row(growth=0.30, is_prime=0, muts="None|None|Nocturnal|None"), "n3")):
    if simulate_post(_r, _sid, "None", 100000) != (200, 100000):
        _not_free.append((_sid, mc.slots_from_row(_r)[_sid]))
check("every flagged clear is still ALLOWED and still free", not _not_free, f"{_not_free!r}")
_blocked_raised = []
for _bad in (None, "not a row", 42, [], object()):
    for _sid in (None, 42, "n1", "nope", []):
        try:
            if not isinstance(mc.clear_blocks_restore(_bad, _sid), bool):
                _blocked_raised.append((_bad, _sid))
        except Exception as _e:                    # noqa: BLE001
            _blocked_raised.append((type(_bad).__name__, _sid, type(_e).__name__))
    try:
        _m = mc.slot_lock_map(_bad)
        if set(_m) != set(mc.SLOT_IDS):
            _blocked_raised.append((_bad, "map short"))
    except Exception as _e:                        # noqa: BLE001
        _blocked_raised.append((type(_bad).__name__, "map", type(_e).__name__))
check("neither the flag nor the map raises on any row or any ranura id",
      not _blocked_raised, f"{_blocked_raised!r}")
# ...and it is CHEAP: the two new per-ranura facts read the row's columns once
# for all sixteen, and they must not make the lineage memo work any harder than
# the counts pinned in block [4].
mc._lineage_generation_cached.cache_clear()
mc.slot_lock_map(row(stacks=3, parent="Hemomania|None|None|None",
                     muts="Nocturnal|Wader|None|None", elder=_elder_col(ea1="Hemomania")))
_ci13 = mc._lineage_generation_cached.cache_info()
check("a full row still parses the lineage column exactly once per lock map",
      _ci13.misses == 1 and _ci13.misses + _ci13.hits <= 24, repr(_ci13))

# --- 1b. THE PAID PRESS DESTROYS THE SAME VALUE (2026-07-27) ------------------
# The guard above was armed only for the FREE "Quitar". The paid "Confirmar", in
# the same picker, overwrote the identical one-way value on a SINGLE press, with
# no warning at all, and CHARGED for it. Worked example, driven here: a parked
# Rex whose ea1 holds "Traumatic Thrombosis" -- a real registry name the game
# rolled and vault.park captured verbatim, which this catalog does not offer. The
# ranura is open, the value is gone the moment the swap lands, and nothing puts
# it back.
#
# The example WAS "Cannibalistic" until 2026-07-27; the catalog widening made
# that one pickable, which would have turned the refusal below into a harmless
# no-op re-send and quietly deleted this whole case. Same fixture, same shape,
# the one value that is still genuinely unrestorable.
_legacy_ea1 = row(elder=_elder_col(ea1="Traumatic Thrombosis"), stacks=3)
_lm_legacy = mc.slot_lock_map(_legacy_ea1)["ea1"]
check("the trap's shape: ea1 is open, and the server already knew the clear was one-way",
      _lm_legacy["locked"] is False and _lm_legacy["clear_blocks_restore"] is True
      and _lm_legacy["holds_unlockable"] is False, repr(_lm_legacy))
_legacy_swapped = dict(_legacy_ea1, **mc.apply_slot_edit(_legacy_ea1, "ea1", "Wader"))
expect_error("...and after a PAID swap the same value really is refused for good",
             lambda: mc.validate_slot_edit(_legacy_swapped, "ea1", "Traumatic Thrombosis"),
             "reconocida")
check("so the server now answers the paid question too, per ranura",
      _lm_legacy["overwrite_blocks_restore"] is True)
# THE TWO QUESTIONS ARE NOT THE SAME QUESTION, and this row is the whole reason
# the server answers both instead of the page reusing one flag. Emptying the
# last-proof heredada shuts its family; SWAPPING it keeps the family open,
# because every value the POST accepts is a recognised name and a recognised name
# is exactly what proves the lineage. So the swap is REVERSIBLE and must keep its
# single press -- friction over a move the player can undo is a defect of its own.
_lp_row = row(stacks=0, parent="Hemomania|None|None|None")
_lp = mc.slot_lock_map(_lp_row)["p1"]
_lp_swapped = dict(_lp_row, **mc.apply_slot_edit(_lp_row, "p1", "Wader"))
expect_ok("the last-proof heredada really does take its old value back after a swap",
          lambda: mc.validate_slot_edit(_lp_swapped, "p1", "Hemomania"), "Hemomania")
check("...so the clear is flagged and the overwrite is NOT, on the same ranura",
      _lp["clear_blocks_restore"] is True
      and _lp["overwrite_blocks_restore"] is False, repr(_lp))
check("...and the family really does stay open after that swap",
      mc.slot_lock_map(_lp_swapped)["p4"]["locked"] is False
      and mc.slot_lock_map(dict(_lp_row, **mc.apply_slot_edit(_lp_row, "p1", "None")))
      ["p4"]["locked"] is True)
# A diet-illegal capture sitting in that SAME position is one-way both ways: the
# family stays open, but the species can never carry the value again.
_wd_lastproof = row(cls="BP_Triceratops_C", stacks=0, parent="Hemomania|None|None|None")
_wd_lp = mc.slot_lock_map(_wd_lastproof)["p1"]
check("a diet-illegal last proof is flagged for BOTH presses",
      _wd_lp["clear_closes"] is True and _wd_lp["clear_blocks_restore"] is True
      and _wd_lp["overwrite_blocks_restore"] is True, repr(_wd_lp))
# THE PAID FLAG HAS TO PREDICT THE POST as hard as the free one does: for every
# ranura, every class and every name a row could hold, really overwrite it and
# ask the real validator whether the old value goes back in. "Wader" is the probe
# because it is generic (both diets carry it) and no ranura refuses it; when the
# row already holds Wader the probe swaps to another generic name, so the swap is
# always a real change.
#
# BOTH ENTOMB COUNTS ARE WALKED, and 0 is the one that matters: only there does a
# heredada open on the strength of the column itself, which is the single shape
# where the two answers diverge. A walk at stacks=3 alone never reaches it and
# would score green with the paid flag copied straight off the free one.
_ow_wrong = []
for _cls in ("BP_Tyrannosaurus_C", "BP_Triceratops_C"):
  for _stacks in (0, 3):
    for _sid in mc.SLOT_IDS:
        for _name in (*mc.PICKABLE, "Cannibalistic", "Traumatic Thrombosis"):
            _probe = "Nocturnal" if mc.normalize_mutation_name(_name) == "wader" else "Wader"
            _r = row_holding(_sid, _name, cls=_cls, stacks=_stacks)
            if mc.slot_lock(_r, _sid) is not None:
                continue                      # a closed ranura has no paid press
            _flag = mc.slot_lock_map(_r)[_sid]["overwrite_blocks_restore"]
            _after = dict(_r, **mc.apply_slot_edit(_r, _sid, _probe))
            try:
                mc.validate_slot_edit(_after, _sid, _name)
                _really = False
            except mc.MutationEditError:
                _really = True
            if _flag is not _really:
                _ow_wrong.append((_cls, _stacks, _sid, _name, _flag, _really))
check("the paid flag matches what the POST really does, over every ranura and name",
      not _ow_wrong, f"{len(_ow_wrong)} mismatches, first: {_ow_wrong[:3]!r}")
# The two flags differ on exactly ONE shape, and it is the one named above. If a
# future rule ever widens that, this count is what says so out loud.
_differ = []
for _cls in ("BP_Tyrannosaurus_C", "BP_Triceratops_C"):
    for _stacks in (0, 3):
        for _sid in mc.SLOT_IDS:
            for _name in ("Hemomania", "Nocturnal", "Osteophagic",
                          "Traumatic Thrombosis"):
                _r = row_holding(_sid, _name, cls=_cls, stacks=_stacks)
                _m = mc.slot_lock_map(_r)[_sid]
                if _m["clear_blocks_restore"] != _m["overwrite_blocks_restore"]:
                    _differ.append((_cls, _stacks, _sid, _name, _m["clear_closes"]))
check("the two answers differ ONLY where emptying closes the family",
      _differ and all(d[4] is True for d in _differ), f"{_differ[:4]!r}")
check("an EMPTY ranura is never flagged for the paid press either",
      not [sid for _r in (row(), row(stacks=0), _open_hidden, _legacy_ea1)
           for sid in mc.SLOT_IDS
           if mc.slots_from_row(_r)[sid] == "None"
           and mc.slot_lock_map(_r)[sid]["overwrite_blocks_restore"]])
# Same crash contract as its twin: never raises, on any row and any ranura id.
_ow_raised = []
for _bad in (None, "not a row", 42, [], object()):
    for _sid in (None, 42, "n1", "nope", []):
        try:
            if not isinstance(mc.overwrite_blocks_restore(_bad, _sid), bool):
                _ow_raised.append((_bad, _sid))
        except Exception as _e:                    # noqa: BLE001
            _ow_raised.append((type(_bad).__name__, _sid, type(_e).__name__))
check("overwrite_blocks_restore never raises either", not _ow_raised, f"{_ow_raised!r}")
# The standalone helpers and the map must agree; two answers to one question is
# how a rule quietly forks.
_pair_wrong = [(sid, k) for _r in (_legacy_ea1, _lp_row, _wd_lastproof, _open_hidden, _legacy)
               for sid in mc.SLOT_IDS
               for k, fn in (("clear", mc.clear_blocks_restore),
                             ("overwrite", mc.overwrite_blocks_restore))
               if fn(_r, sid) is not mc.slot_lock_map(_r)[sid][f"{k}_blocks_restore"]]
check("the standalone helpers and the lock map give the same answer",
      not _pair_wrong, f"{_pair_wrong[:4]!r}")
# A paid swap is still CHARGED once and only once, and a refused one is free.
# THE REFUSED ONE HAS TO STAY A REFUSAL, not a no-op: re-sending the value the
# ranura already holds is free for a different reason entirely, and if the probe
# name ever becomes pickable this check goes on passing while testing nothing.
# That is exactly what happened to "Cannibalistic" on 2026-07-27.
check("a flagged paid swap is charged exactly once, at the normal price",
      simulate_post(_legacy_ea1, "ea1", "Wader", 100000) == (200, 80000))
check("...and a refused one takes nothing",
      simulate_post(_legacy_ea1, "ea1", "Traumatic Thrombosis", 100000)[1] == 100000)
check("...and that refusal really is a refusal, not a free no-op re-send",
      simulate_post(_legacy_ea1, "ea1", "Traumatic Thrombosis", 100000)[0] == 400,
      repr(simulate_post(_legacy_ea1, "ea1", "Traumatic Thrombosis", 100000)))

# --- 2a. the advice names ranuras this dino can actually use -----------------
# stacks=0 ON PURPOSE, on both: these two rows are here to test the OWN ranuras,
# and a dino with entierros has open heredadas that the advice now (correctly)
# names first. The entombed cases are section 2a-bis below.
_young = row(growth=0.30, is_prime=0, stacks=0)   # n2 wants 50%, n4 75%+Prime
_half = row(growth=0.50, is_prime=0, stacks=0)    # n2 open, n4 still Prime-only
check("the young dino really has neither permitted ranura open",
      mc.slot_lock(_young, "n2") is not None and mc.slot_lock(_young, "n4") is not None)
check("...and no inherited ranura either, so nothing at all takes an unlockable",
      not (mc.unlocked_slots(_young) - {"n1", "n3"}))
try:
    mc.validate_slot_edit(_young, "n1", "Osteophagic")
    _young_msg = ""
except mc.MutationEditError as e:
    _young_msg = str(e)
check("it is not told to put it in a ranura it cannot open",
      "Ponla" not in _young_msg, f"got: {_young_msg}")
check("...it is told what those ranuras need instead, from the ladder",
      "2ª necesita 50% de crecimiento" in _young_msg
      and "4ª necesita 75% de crecimiento y ser Prime" in _young_msg, f"got: {_young_msg}")
check("the picker notice says the same thing on the same dino",
      "Ponla" not in mc.hidden_notice(_young)
      and "2ª necesita 50%" in mc.hidden_notice(_young))
try:
    mc.validate_slot_edit(_half, "n1", "Osteophagic")
    _half_msg = ""
except mc.MutationEditError as e:
    _half_msg = str(e)
check("a dino with ONE permitted ranura open is sent to that one only",
      "Ponla en la 2ª." in _half_msg and "4ª" not in _half_msg, f"got: {_half_msg}")
check("...and the notice matches it",
      "Sí puedes ponerlas en la 2ª." in mc.hidden_notice(_half)
      and "4ª" not in mc.hidden_notice(_half))
_both_open = row(stacks=0)                     # full-grown Prime, never buried
try:
    mc.validate_slot_edit(_both_open, "n1", "Osteophagic")
    _both_open_msg = ""
except mc.MutationEditError as e:
    _both_open_msg = str(e)
check("a dino with both own ranuras open and no entierros reads as it always did",
      _both_open_msg.endswith("Ponla en la 2ª o en la 4ª.")
      and mc.hidden_notice(_both_open).endswith("Sí puedes ponerlas en la 2ª o en la 4ª."),
      f"got: {_both_open_msg}")
check("...and a caller with no row at all still gets every permitted destination",
      mc.hidden_notice(row()) == mc.hidden_notice()
      and mc.hidden_notice().endswith(
          "Sí puedes ponerlas en la 2ª, en la 4ª, en una heredada, "
          "en una de Anciano A o en una de Anciano B."),
      f"got: {mc.hidden_notice()}")

# --- 2a-bis. AN OPEN HEREDADA IS A PLACE THE MUTATION CAN GO ------------------
# The advice only ever considered n2 and n4, so with both of those still closed
# it asserted "las ranuras que sí las admiten todavía no están disponibles en
# este dinosaurio" -- FALSE on every entombed dino, because the same ruling that
# closed n1 and n3 opens all twelve inherited ranuras, and validate_slot_edit
# accepts that exact write. Driven against the validator, never against a
# re-typed rule: whatever the copy names, the POST has to take.
_entombed_young = row(growth=0.30, is_prime=0, stacks=3)   # nothing own but n1
_one_entomb = row(growth=0.30, is_prime=0, stacks=1)       # heredadas only
check("the premise: this dino really cannot open n2 or n4",
      mc.slot_lock(_entombed_young, "n2") is not None
      and mc.slot_lock(_entombed_young, "n4") is not None)
check("...and the POST really does accept the unlockable in its heredada",
      mc.validate_slot_edit(_entombed_young, "p1", "Osteophagic")[0] == "Osteophagic")
try:
    mc.validate_slot_edit(_entombed_young, "n1", "Osteophagic")
    _ey_msg = ""
except mc.MutationEditError as e:
    _ey_msg = str(e)
check("the refusal no longer claims nothing takes it while a heredada is open",
      "todavía no están disponibles" not in _ey_msg
      and "Ponla en una heredada" in _ey_msg, f"got: {_ey_msg}")
check("...and it names every family that is open, and only those",
      "Anciano A" in _ey_msg and "Anciano B" in _ey_msg
      and "Anciano A" not in mc.hidden_notice(_one_entomb)
      and "una heredada" in mc.hidden_notice(_one_entomb), f"got: {_ey_msg}")
check("the picker notice says the same thing on the same dino",
      mc.hidden_notice(_entombed_young).endswith(
          "Sí puedes ponerlas en una heredada, en una de Anciano A "
          "o en una de Anciano B."), f"got: {mc.hidden_notice(_entombed_young)}")
# EVERY NAMED DESTINATION IS A WRITE THE POST TAKES, and every destination the
# POST takes is either named or (own ranuras aside) not a family at all. This is
# the check that makes the sentence a fact instead of a hope.
_advice_wrong = []
for _r, _label in ((_entombed_young, "3 entierros"), (_one_entomb, "1 entierro"),
                   (_half, "no entierros"), (_both_open, "grown, no entierros")):
    _open_names = {"la 2ª": "n2", "la 4ª": "n4", "una heredada": "p1",
                   "una de Anciano A": "ea1", "una de Anciano B": "eb1"}
    _said, _ = mc._unlockable_destinations(_r, {"Osteophagic"})
    for _phrase, _sid in _open_names.items():
        _named = _phrase in _said
        try:
            mc.validate_slot_edit(_r, _sid, "Osteophagic")
            _takes = True
        except mc.MutationEditError:
            _takes = False
        if _named != _takes:
            _advice_wrong.append((_label, _phrase, _named, _takes))
check("every destination the advice names is one the POST accepts, and no other",
      not _advice_wrong, f"{_advice_wrong!r}")
# The "nothing yet" sentence is now reachable ONLY when nothing is: a dino with
# no entierros AND no growth. And there it lists the entomb path too, read off
# ENTOMB_LADDER, because that is the cheaper of the two things he can do.
check("the nothing-yet sentence survives where it is still true",
      "todavía no están disponibles" in mc.hidden_notice(_young)
      and "las heredadas necesitan 1 entierro" in mc.hidden_notice(_young)
      and "las de Anciano B necesitan 3 entierros" in mc.hidden_notice(_young),
      f"got: {mc.hidden_notice(_young)}")
_orig_entomb = mc._ENTOMB
try:
    mc._ENTOMB = {**_orig_entomb, "p1": 4, "p2": 4, "p3": 4, "p4": 4}
    _entomb_flip = mc.hidden_notice(_young)
finally:
    mc._ENTOMB = _orig_entomb
check("...and that number is read off the ladder, not written down",
      "las heredadas necesitan 4 entierros" in _entomb_flip
      and "las heredadas necesitan 1 entierro" in mc.hidden_notice(_young),
      f"got: {_entomb_flip}")
# GENERATED FROM THE LADDER, not written down: move the rungs and every sentence
# follows. A hardcoded "50%" fails this.
_orig_ladder = mc._LADDER
try:
    # Both permitted ranuras stay out of this dino's reach (it is at 30% and not
    # Prime), so the sentence still has to name what they need — with the NEW
    # numbers. A hardcoded "50%" survives neither half of this.
    mc._LADDER = {"n1": (5, False), "n2": (60, False), "n3": (65, False),
                  "n4": (95, True)}
    _flip_msg = mc._hidden_reason("Osteophagic", _young)
    _flip_notice = mc.hidden_notice(_young)
finally:
    mc._LADDER = _orig_ladder
check("the requirement in the copy is read off the ladder, not written down",
      "60% de crecimiento" in _flip_msg and "95% de crecimiento y ser Prime" in _flip_msg
      and "50%" not in _flip_msg and "75%" not in _flip_msg
      and "60% de crecimiento" in _flip_notice,
      f"got: {_flip_msg}")
check("...and the real ladder is back afterwards",
      "2ª necesita 50% de crecimiento" in mc._hidden_reason("Osteophagic", _young))
# The permitted RANURAS are still generated from the same one set as before, and
# the two halves compose: flip the ruling AND the ladder and both follow.
_orig_blocked2 = mc.HIDDEN_BLOCKED_SLOTS
try:
    mc.HIDDEN_BLOCKED_SLOTS = frozenset({"n1", "n2", "n3"})
    _one_left = mc._hidden_reason("Osteophagic", _both_open)
    _one_left_young = mc._hidden_reason("Osteophagic", _young)
finally:
    mc.HIDDEN_BLOCKED_SLOTS = _orig_blocked2
check("closing another ranura moves both halves of the sentence",
      _one_left.endswith("Ponla en la 4ª.")
      and "4ª necesita 75% de crecimiento y ser Prime" in _one_left_young
      and "2ª" not in _one_left_young.split("dinosaurio:")[-1], f"got: {_one_left_young}")
check("no em-dash, and no promise that a ranura opens by itself",
      not any("—" in s for s in (_young_msg, _half_msg, mc.hidden_notice(_young)))
      and not any(w in _young_msg + mc.hidden_notice(_young)
                  for w in ("con el tiempo", "se abrirá", "espera")))

# --- 2b. a duplicate is answered as a duplicate ------------------------------
# Both rules are true at once when the dino already carries the name somewhere
# else. The unlockable copy would answer "ponla en la 2ª" -- which is where it
# already is -- so the duplicate, the one he can act on, has to answer first.
_dup_wrong = []
for _n in _UNLOCKABLE:
    for _held_slot, _target in (("n2", "n1"), ("n4", "n3"), ("p1", "n1"), ("eb4", "n3")):
        try:
            mc.validate_slot_edit(row_holding(_held_slot, _n), _target, _n)
            _dup_wrong.append((_n, _held_slot, _target, "allowed"))
        except mc.MutationEditError as e:
            if "duplicadas" not in str(e):
                _dup_wrong.append((_n, _held_slot, _target, str(e)))
check("a duplicate unlockable is refused AS a duplicate, wherever it is held",
      not _dup_wrong, f"{_dup_wrong!r}")
_st, _bal = simulate_post(row(muts="None|Osteophagic|None|None"), "n1", "Osteophagic", 100000)
check("...and that refusal is still a 400 that charges nothing",
      _st == 400 and _bal == 100000)
# THE DIET CHECK STAYS FIRST. All three rules fire on this row, and diet is still
# the only one that is true in every ranura, so it is still the answer.
expect_error("diet still wins over both, on a herbivore holding it elsewhere",
             lambda: mc.validate_slot_edit(
                 row(cls="BP_Triceratops_C", muts="None|Osteophagic|None|None"),
                 "n1", "Osteophagic"),
             "carnívoros")
# A name that is only a duplicate, and one that is only an unlockable, each still
# get their own answer -- the reorder must not have merged the two.
expect_error("an ordinary duplicate still answers duplicate",
             lambda: mc.validate_slot_edit(row(muts="Nocturnal|None|None|None"),
                                           "n2", "Nocturnal"), "duplicadas")
expect_error("a first-time unlockable in n1 still answers with the ranura rule",
             lambda: mc.validate_slot_edit(row(), "n1", "Osteophagic"), "desbloquearla")
expect_ok("re-sending the value already in n1 is still the harmless no-op",
          lambda: mc.validate_slot_edit(_open_hidden, "n1", "Osteophagic"), "Osteophagic")

# --- 3. only a real unlockable is labelled as one ----------------------------
check("the server says, per ranura, whether the value it holds is unlockable",
      mc.slot_lock_map(_open_hidden)["n1"]["holds_unlockable"] is True
      and mc.slot_lock_map(row(muts="AugmentedTapetum|None|None|None"))["n1"]
      ["holds_unlockable"] is True)
check("a legacy name is NOT labelled as one, though it is missing from the list",
      mc.slot_lock_map(_legacy)["n1"]["holds_unlockable"] is False
      and "Traumatic Thrombosis"
      not in mc.slot_catalog_map("BP_Tyrannosaurus_C")["n1"])
check("...and neither is an ordinary name, nor an empty ranura",
      mc.slot_lock_map(row(muts="Nocturnal|None|None|None"))["n1"]["holds_unlockable"]
      is False
      and not [s for s in mc.SLOT_IDS if mc.slot_lock_map(row())[s]["holds_unlockable"]])
_label_wrong = [(s, n) for n in (*mc.PICKABLE, "Traumatic Thrombosis", "None")
                for s in ("n1", "n2", "p3", "eb4")
                if mc.slot_lock_map(row_holding(s, n))[s]["holds_unlockable"]
                is not (n in mc.HIDDEN)]
check("the label is exactly the seven, in every family", not _label_wrong, f"{_label_wrong!r}")

# --- 4. the citation names the offset the binary really states ---------------
check("the per-dino unlock pool is cited at +0x960",
      "+0x960" in _MC_SRC and "0x958" not in _MC_SRC)
check("...and the rest of the citation is intact, not weakened",
      "TheIsleServer-24167035-B1BCBEE1.exe" in _MC_SRC and "0xF7E6E8" in _MC_SRC
      and "0x08EF3F70" in _MC_SRC and "0xF7E805" in _MC_SRC
      and "185,213,952 B" in _MC_SRC)
check("...and it records how that number is auditable, like the rest",
      "0x08F5AA40" in _MC_SRC and "ArrayDim" in _MC_SRC)

# --- the three rules this wave must not have moved ---------------------------
check("the seven unlockable names are byte-identical to before the wave",
      mc.HIDDEN == frozenset(_UNLOCKABLE) and len(mc.HIDDEN) == 7
      and mc.HIDDEN_BLOCKED_SLOTS == frozenset({"n1", "n3"}))
check("the growth ladder is byte-identical to before the wave",
      list(mc.GROWTH_LADDER) == [("n1", 0.25, False), ("n2", 0.50, False),
                                 ("n3", 0.75, False), ("n4", 0.75, True)]
      and [(r["slot"], r["requires_growth_pct"], r["requires_prime"])
           for r in mc.growth_ladder_view()]
      == [("n1", 25, False), ("n2", 50, False), ("n3", 75, False), ("n4", 75, True)])
check("the entomb ladder is byte-identical to before the wave",
      list(mc.ENTOMB_LADDER) == [("p1", 1), ("p2", 1), ("p3", 1), ("p4", 1),
                                 ("ea1", 2), ("ea2", 2), ("ea3", 2), ("ea4", 2),
                                 ("eb1", 3), ("eb2", 3), ("eb3", 3), ("eb4", 3)])
_rungs13 = [(g, p, open_n(g, p)) for g, p, w in
            ((0.24, False, []), (0.25, False, ["n1"]), (0.50, False, ["n1", "n2"]),
             (0.75, False, ["n1", "n2", "n3"]), (0.75, True, ["n1", "n2", "n3", "n4"]))
            if open_n(g, p) != w]
check("...and every rung still opens exactly the same ranuras", not _rungs13, f"{_rungs13!r}")
check("...and every entomb rung too",
      [open_inherited(n) for n in (0, 1, 2, 3)]
      == [[], _P, _P + _EA, _P + _EA + _EB])
check("an existing unlockable in n1 is still kept, still read back, still free "
      "to remove",
      mc.slots_from_row(_open_hidden)["n1"] == "Osteophagic"
      and mc.active_count(_open_hidden) == 1
      and mc.slot_lock(_open_hidden, "n1") is None
      and simulate_post(_open_hidden, "n1", "None", 100000) == (200, 100000))

# --- what the route and the editor do with the two new facts ----------------
check("the GET hands the notice the ROW, so it can name reachable ranuras",
      "mutation_catalog.hidden_notice(row)" in _SERVER_SRC)
check("the GET's own fail-closed map carries both new fields too",
      '"clear_blocks_restore": True' in _SERVER_SRC
      and '"holds_unlockable": False' in _SERVER_SRC)
# ...and the paid answer travels on that path as well. An ABSENT field is the
# older-server fallback and the editor reads it as "no answer given", which is
# not what an unreadable row means -- there, nothing can be put back at all.
check("the fail-closed map answers the paid question too",
      '"overwrite_blocks_restore": True' in _SERVER_SRC)
check("every slot the lock map describes carries both answers",
      all(set(v) >= {"clear_blocks_restore", "overwrite_blocks_restore"}
          for v in mc.slot_lock_map(row(muts="Osteophagic|None|None|None")).values()))
# THE ROOT OF THE 2026-07-27 FINDING: the guard belongs to the VALUE, not to the
# button. Both destructive presses have to consult a reversibility answer, and
# the paid one may not reuse the free one's flag (they differ on the last-proof
# heredada). What a player actually gets -- one press or two, which sentence,
# and whether the charge lands -- is proven by mounting the real component in
#   web/frontend/src/components/inventory/MutationEditor.oneWayPress.test.js
# (cd web/frontend && CI=true npx craco test --watchAll=false), which drives all
# eight row shapes against BOTH presses.
check("the PAID press is armed by its own server answer, not by the clear's",
      "overwrite_blocks_restore" in _EDITOR_SRC
      and "const overwriteIsIrreversible = hasValue && (overwriteAnswered" in _EDITOR_SRC
      and "onClick={() => selected && onPick(selected)}" not in _EDITOR_SRC,
      "the paid press still saves straight from one click")
check("both presses arm the SAME panel, and only that panel acts",
      _EDITOR_SRC.count('data-testid="mutation-clear-warning"') == 1
      and _EDITOR_SRC.count('data-testid="mutation-clear-confirm"') == 1
      # exactly one control saves the armed value, and it is the panel's own
      and _EDITOR_SRC.count("onClick={onConfirmPending}") == 1
      and _EDITOR_SRC.count("onConfirmPending={") == 1)
check("the paid confirming control still carries its price",
      "Sí, cambiarla ({Number(cost).toLocaleString(\"es\")} PrimeMeat)" in _EDITOR_SRC)
# The wording is GENERATED from the case and the stored name, in one place both
# surfaces read. A constant sentence could not name what is being lost and would
# read the same for every mutation on the dinosaur.
check("the one-way wording is generated from the data, in one place",
      "const ONE_WAY_TEXT = {" in _EDITOR_SRC
      and _EDITOR_SRC.count("const ONE_WAY_TEXT") == 1
      and all(f"  {k}: (held) =>" in _EDITOR_SRC
              for k in ("lineage", "locked", "value", "unknown"))
      and "const oneWayLead = (held, nextName) =>" in _EDITOR_SRC)
check("a ranura holding a one-way value says so before anything is pressed",
      'data-testid="mutation-oneway-notice"' in _EDITOR_SRC
      and _EDITOR_SRC.count('data-testid="mutation-oneway-notice"') == 1
      and "{clearIsIrreversible && !pending && heldName && (" in _EDITOR_SRC)
# Source greps only pin that the editor READS the server's answer. What a player
# actually gets -- one press or two, and which sentence -- is proven by mounting
# the real component in
#   web/frontend/src/components/inventory/MutationEditor.unlockableSlots.test.js
# (cd web/frontend && CI=true npx craco test --watchAll=false), which presses the
# buttons on an OPEN ranura holding one of the seven.
check("the editor arms its confirm on the server's reversibility answer",
      "clear_blocks_restore" in _EDITOR_SRC
      and "clearBlocksRestore" in _EDITOR_SRC
      and "isLocked || clearClosesSlots || clearBlocksRestore" in _EDITOR_SRC)
check("the editor takes the unlockable label from the server, not a set difference",
      "lock?.holds_unlockable" in _EDITOR_SRC)
check("the three warnings are one panel with one confirm control, not three",
      _EDITOR_SRC.count('data-testid="mutation-clear-warning"') == 1
      and _EDITOR_SRC.count('data-testid="mutation-clear-confirm"') == 1)

# Markdown hard-wraps, so match against a whitespace-flattened copy — otherwise
# a sentence that merely wrapped reads as a missing sentence.
_FEATURES_SRC = open(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                  "docs", "FEATURES.md"), encoding="utf-8").read()
_FEATURES_FLAT = " ".join(_FEATURES_SRC.split())
check("FEATURES.md documents that a locked slot never opens by itself",
      "no se abre sola con el tiempo" in _FEATURES_FLAT
      and "hacerlo crecer en el juego y volver a guardarlo" in _FEATURES_FLAT)
check("FEATURES.md documents the single displayed percent",
      "growth_display_pct" in _FEATURES_FLAT
      and "la escalera se compara contra ese número" in _FEATURES_FLAT)
check("FEATURES.md documents the confirmation on a locked clear",
      "pide una confirmación" in _FEATURES_FLAT
      and "En los dos casos quitar es gratis." in _FEATURES_FLAT)
check("FEATURES.md says the confirming press is a different button",
      "quien quita es un botón distinto" in _FEATURES_FLAT)
# THE ONE-PERCENT CLAIM IS SCOPED TO WHERE IT IS TRUE. It holds on the vault
# card and the mutation editor (the two surfaces on the same screen, both fed by
# growth_display_pct / vault._dino_view). It does NOT hold site-wide: the live
# dino page publishes round(x*100, 1) and renders it with JS Math.round.
check("FEATURES.md no longer claims the one percent holds across the whole site",
      "Un solo porcentaje en toda la web" not in _FEATURES_FLAT
      and "Un solo porcentaje en la bóveda" in _FEATURES_FLAT)
check("FEATURES.md records the live-dino divergence as a decided, known thing",
      "Mi Dino" in _FEATURES_FLAT and "Math.round" in _FEATURES_FLAT
      and "1 de cada 20" in _FEATURES_FLAT and "Es a propósito" in _FEATURES_FLAT)


def _mydino_pct(g):
    """What the LIVE dino page ends up showing: server.py publishes
    round(x*100, 1) (~L8790) and MyDino.jsx renders it with JS Math.round, which
    rounds a half UP where Python's round() sends it to the even side."""
    import math as _math
    return _math.floor(round(float(g) * 100, 1) + 0.5)


_MYDINO_SRC = open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                                "src", "pages", "MyDino.jsx"), encoding="utf-8").read()
check("the live-dino lane really is the other convention (pinned to both sources)",
      "round(float(growth_raw) * 100, 1)" in _SERVER_SRC
      and "Math.round(dino.growth)" in _MYDINO_SRC)
check("the divergence FEATURES.md quotes is the one the code really produces",
      [(_mydino_pct(g), card_pct(g)) for g in (0.745, 0.585, 0.625)]
      == [(75, 74), (59, 58), (63, 62)],
      str([(g, _mydino_pct(g), card_pct(g)) for g in (0.745, 0.585, 0.625)]))
_diverged = [i / 1000.0 for i in range(1001) if _mydino_pct(i / 1000.0) != card_pct(i / 1000.0)]
check("...and it really is about 1 growth value in 20, as the doc says",
      len(_diverged) == 50 and round(1001 / len(_diverged)) == 20,
      f"{len(_diverged)} of 1001 growth values diverge")
check("the vault's own two surfaces still agree with each other exactly",
      all(card_pct(i / 1000.0) == mc.growth_display_pct(mc.growth_fraction({"growth": i / 1000.0}))
          for i in range(1001)))
check("FEATURES.md no longer says the slot opens on its own",
      "hasta que la ranura se abra" not in _FEATURES_FLAT)
check("FEATURES.md documents that the how-to is chosen by the lock code",
      "La cuarta ranura no es una ranura de crecimiento" in _FEATURES_FLAT
      and "`prime` / `growth` / `growth_unknown`" in _FEATURES_FLAT)
check("FEATURES.md documents the entomb ladder in plain Spanish",
      "enterrado una vez puede editar las cuatro" in _FEATURES_FLAT
      and "enterrado dos veces" in _FEATURES_FLAT
      and "enterrado tres veces" in _FEATURES_FLAT
      and "nunca se ha enterrado no puede editar ninguna de las doce" in _FEATURES_FLAT)
check("FEATURES.md records the 2026-07-12 ruling as REPLACED, not just gone",
      "Sustituye a la regla del 2026-07-12" in _FEATURES_FLAT
      and "elder_set_unlocked" in _FEATURES_FLAT
      and "ya no existe y nadie la consulta" in _FEATURES_FLAT)
check("FEATURES.md says an entomb-locked slot never opens by itself either",
      "no se abre sola con el tiempo" in _FEATURES_FLAT
      and "enterrarlo en el juego las veces que haga falta y volver a guardarlo"
      in _FEATURES_FLAT)
check("FEATURES.md keeps quitar free on all sixteen",
      "siempre es gratis** en las dieciséis ranuras" in _FEATURES_FLAT)
check("FEATURES.md records the elder label fix and that no data moved",
      "1A, 1B, 2A, 2B, 3A, 3B, 4A, 4B" in _FEATURES_FLAT
      and "Los datos guardados nunca estuvieron mal" in _FEATURES_FLAT
      and "elder_segments_from_sets" in _FEATURES_FLAT)
check("FEATURES.md documents the READ-TIME derivation for the rows the site builds",
      "se arreglan al leerlas, no migrando" in _FEATURES_FLAT
      and "el mayor de dos números" in _FEATURES_FLAT
      and "Solo sube, nunca baja" in _FEATURES_FLAT
      and "_entomb_state" in _FEATURES_FLAT
      and "el número nunca se inventa a partir del nivel ni del Prime"
      in _FEATURES_FLAT)
check("FEATURES.md documents the parent-only cap AND the mod layout behind it",
      "MAX_DERIVED_GENERATION" in _FEATURES_FLAT
      and "first_entomb_flatten" in _FEATURES_FLAT
      and "no asciende una generación, la aplana" in _FEATURES_FLAT
      and "12 con un entierro donde la regla da 4" in _FEATURES_FLAT)
check("FEATURES.md says out loud why NO lane stores a derived count",
      "ElderReplicationStacks" in _FEATURES_FLAT
      and "no es un permiso del editor, es un regalo dentro del juego"
      in _FEATURES_FLAT
      and "no guardan la columna" in _FEATURES_FLAT
      and "llega a la bóveda bloqueado" in _FEATURES_FLAT)
check("FEATURES.md says WHY it is not a backfill (the redeem reads the same column)",
      "el canje sigue mandando lo que siempre mandó" in _FEATURES_FLAT
      and "solo cambia **lo que el editor permite**" in _FEATURES_FLAT)
check("FEATURES.md records that the visible number is the REAL one",
      "El número que se enseña es el REAL, no el derivado" in _FEATURES_FLAT
      and "elder_stack_count" in _FEATURES_FLAT
      and "sería mentirle al jugador" in _FEATURES_FLAT
      and "Ya están abiertas porque este dinosaurio ya trae mutaciones heredadas"
      in _FEATURES_FLAT)
check("FEATURES.md records the guarded clear on the last proof",
      "clear_closes" in _FEATURES_FLAT
      and "Quitar la ÚLTIMA heredada cierra la familia" in _FEATURES_FLAT
      and "Solo la última" in _FEATURES_FLAT
      and "Quitar sigue siendo gratis" in _FEATURES_FLAT)
check("FEATURES.md states what counts as proof, and the cost of that choice",
      "una mutación reconocida, no un hueco no vacío" in _FEATURES_FLAT
      and "canonical_mutation_name" in _FEATURES_FLAT
      and "Cannibalistic" in _FEATURES_FLAT)
check("FEATURES.md records the honest denominator on the count chip",
      "cuenta sobre lo alcanzable" in _FEATURES_FLAT
      and "catorce ranuras libres cuando había dos" in _FEATURES_FLAT)
check("FEATURES.md names both ladders as the one source of the rule",
      "`GROWTH_LADDER` y `ENTOMB_LADDER`" in _FEATURES_FLAT
      and "`entomb` / `entomb_unknown`" in _FEATURES_FLAT)
check("FEATURES.md states the 2026-07-27 ruling and lists the seven names",
      "La 1ª y la 3ª ranura propia no ofrecen las mutaciones que hay que desbloquear jugando"
      in _FEATURES_FLAT
      and "slot 1 shouldnt have hidden mutations neither should slot 3" in _FEATURES_FLAT
      and all(n in _FEATURES_FLAT for n in _UNLOCKABLE))
check("FEATURES.md names the ORACLE, not just the answer",
      "bHasRequirement" in _FEATURES_FLAT
      and "0xF7E6E8" in _FEATURES_FLAT
      and "no se ha adivinado: lo dice el propio juego" in _FEATURES_FLAT
      and "1.674 tiradas" in _FEATURES_FLAT)
check("FEATURES.md says an unclassifiable name stays OFFERED",
      "se trata como NO oculto y se sigue ofreciendo" in _FEATURES_FLAT
      and "es peor fallo que ofrecérsela de más" in _FEATURES_FLAT)
check("FEATURES.md promises existing rows are never broken",
      "la conserva" in _FEATURES_FLAT
      and "quitarla sigue siendo gratis" in _FEATURES_FLAT
      and "No se borra ni se migra nada" in _FEATURES_FLAT
      and "solo afecta a lo que se escribe de nuevo" in _FEATURES_FLAT)
check("FEATURES.md records how diet composes, and which reason wins",
      "en un herbívoro pierde solo cinco" in _FEATURES_FLAT
      and "contesta **el de dieta**" in _FEATURES_FLAT)
check("FEATURES.md points at the one-line re-ruling and the honest UI",
      "`HIDDEN_BLOCKED_SLOTS`" in _FEATURES_FLAT
      and "`slot_catalog`" in _FEATURES_FLAT
      and 'ni se marcan "En uso"' in _FEATURES_FLAT)
# --- the 2026-07-26 audit wave, documented ----------------------------------
check("FEATURES.md documents that the ask is armed by reversibility",
      "la pregunta la decide si el cambio se puede deshacer, no si la ranura está"
      in _FEATURES_FLAT
      and "clear_blocks_restore" in _FEATURES_FLAT
      and "Cubre tres casos" in _FEATURES_FLAT
      and "quitar sigue siendo gratis" in _FEATURES_FLAT.lower())
check("FEATURES.md keeps the single press where the clear can be walked back",
      "se queda en un solo toque" in _FEATURES_FLAT
      and "un aviso en todos los vaciados no sería un aviso" in _FEATURES_FLAT)
# --- the 2026-07-27 wave: the PAID press, documented -------------------------
check("FEATURES.md records that the paid press destroyed the same value",
      "sobrescribía exactamente el mismo valor irrecuperable de un solo toque"
      in _FEATURES_FLAT
      and "Cannibalistic" in _FEATURES_FLAT
      and "la regla es del valor, no del botón" in _FEATURES_FLAT
      and "lleva su precio escrito en el botón que confirma" in _FEATURES_FLAT)
check("FEATURES.md records WHY there are two answers and not one",
      "overwrite_blocks_restore" in _FEATURES_FLAT
      and "cambiarla no la cierra" in _FEATURES_FLAT
      and "Las dos cosas son fallos." in _FEATURES_FLAT)
check("FEATURES.md records the standing notice on ANY one-way ranura",
      "lo dice nada más abrirla" in _FEATURES_FLAT
      and "ONE_WAY_TEXT" in _FEATURES_FLAT
      and "en las otras catorce ranuras no había aviso de ningún tipo"
      in _FEATURES_FLAT)
check("FEATURES.md documents that the advice only names reachable ranuras",
      "El consejo solo nombra ranuras que ese dino puede usar hoy" in _FEATURES_FLAT
      and "la 2ª necesita 50% de crecimiento" in _FEATURES_FLAT
      and "GROWTH_LADDER" in _FEATURES_FLAT)
check("...and that it asks about all sixteen, not just the own four",
      "ese consejo mira las dieciséis ranuras" in _FEATURES_FLAT
      and "allowed_names_for_slot" in _FEATURES_FLAT
      and "ENTOMB_LADDER" in _FEATURES_FLAT)
check("FEATURES.md records the two fail-closed repairs on the editor",
      "Una ranura que no viene en el payload pregunta igual" in _FEATURES_FLAT
      and "cuando los dos motivos son ciertos a la vez, se dicen los dos"
      in _FEATURES_FLAT)
check("FEATURES.md documents the check order, diet still first",
      "El orden completo es dieta, duplicado, ranura." in _FEATURES_FLAT
      and "un duplicado se contesta como duplicado" in _FEATURES_FLAT
      and "La dieta sigue siendo la primera comprobación de las tres"
      in _FEATURES_FLAT)
check("FEATURES.md documents that the unlockable label is the server's",
      "holds_unlockable" in _FEATURES_FLAT
      and "no una resta de listas" in _FEATURES_FLAT
      and "puesto por staff" in _FEATURES_FLAT)
# The legacy inventory lane (DinoManageModal + server.py CHILD_GROWTH_REQ_*)
# still states 20/50/100 and is DELIBERATELY untouched: its save rebuilds the
# stored array and drops locked slots, so re-pointing it at the new ladder can
# wipe a mutation. Pinned here so the divergence stays a decision, not a drift
# somebody "fixes" by halves — the pair must move together or not at all.
_MANAGE_SRC = open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                                "src", "components", "inventory", "DinoManageModal.jsx"),
                   encoding="utf-8").read()
check("legacy lane frontend/backend still agree with EACH OTHER",
      "const CHILD_REQ_PRIME = [20, 50, 100, 100];" in _MANAGE_SRC
      and "const CHILD_REQ_BASE = [20, 50, 100];" in _MANAGE_SRC
      and "CHILD_GROWTH_REQ_PRIME = [20, 50, 100, 100]" in _SERVER_SRC
      and "CHILD_GROWTH_REQ_BASE = [20, 50, 100]" in _SERVER_SRC)
check("the vault ladder is NOT the legacy lane's numbers (separate rules today)",
      [r["requires_growth_pct"] for r in lv] == [25, 50, 75, 75])

os.remove(dbpath2)
os.remove(dbpath)
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
