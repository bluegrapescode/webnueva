# -*- coding: utf-8 -*-
"""Parthenogenesis joins the catalog — the cure for the "my 4th mutation is
bugged and I can't edit or apply it" ticket class (first reporter: a Prime
Deinosuchus entombed 3x, parked row 10377, n4 = "Parthenogenesis").

The game has rolled the name since 2026-07-29 (58 parked segments by 08-12)
while the site held it out of PICKABLE waiting on the C++ half that arms its
reproduction-unlock byte. That DLL is live (its string table carries the name),
so the catalog now recognises, renders, offers and re-accepts it — and any
FUTURE name the game grows that this catalog does not know is named once in
the log by slot_lock_map's beacon instead of surfacing as a player ticket.

Sensitivity: on the pre-fix module this file is red on the pinned-41 test, the
presence tests and the row-10377 walk-back tests.
"""
from __future__ import annotations

import logging
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

import mutation_catalog as mc  # noqa: E402


# ── the drift guard: the catalog IS the game's 41, verbatim ──────────────────
# Pinned as literals on purpose: comparing PICKABLE to itself is circular. This
# list is the exe-derived registry (43 entries less the 2 dev placeholders),
# the same derivation the HIDDEN block documents. A name silently dropped OR
# invented reddens this.
GAME_41 = {
    "Hemomania", "Hematophagy", "Accelerated Prey Drive", "Osteophagic",
    "Xerocole Adaptation", "Hypervigilance", "Truculency",
    "Photosynthetic Regeneration", "Cellular Regeneration",
    "Advanced Gestation", "Sustained Hydration", "Efficient Digestion",
    "Featherweight", "Osteosclerosis", "Wader", "Epidermal Fibrosis",
    "Congenital Hypoalgesia", "Photosynthetic Tissue", "Nocturnal",
    "Hydroregenerative", "Increased Inspiratory Capacity", "Hydrodynamic",
    "Submerged Optical Retention", "Enhanced Digestion", "Reinforced Tendons",
    "Multichambered Lungs", "Infrasound Communication", "Heightened Ghrelin",
    "Prolific Reproduction", "Gastronomic Regeneration", "Enlarged Meniscus",
    "Reniculate Kidneys", "Sequential Hermaphroditism", "Augmented Tapetum",
    "Cannibalistic", "Hypermetabolic Inanition", "Barometric Sensitivity",
    "Social Behavior", "Tactile Endurance", "Parthenogenesis",
    "Reabsorption",
}


def test_pickable_is_exactly_the_games_41():
    assert set(mc.PICKABLE) == GAME_41
    assert len(mc.PICKABLE) == 41            # and no duplicates in the tuple
    assert len(set(mc.PICKABLE)) == 41


# ── recognition ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("spelling", [
    "Parthenogenesis", "parthenogenesis", "PARTHENOGENESIS",
    " Parthenogenesis ", "partheno_genesis",
])
def test_canonical_resolves_every_spelling(spelling):
    assert mc.canonical_mutation_name(spelling) == "Parthenogenesis"


def test_description_exists_and_is_spanish():
    assert mc.DESCRIPTIONS["Parthenogenesis"] == "Permite anidar sin pareja."


def test_generic_diet_every_class_offers_it():
    # Registry group GenericExc -> no diet gate: carnivore, herbivore AND
    # gallimimus (which only ever sees GENERIC) all offer it.
    assert "Parthenogenesis" in mc.GENERIC
    for cls in ("BP_Deinosuchus_C", "BP_Kentrosaurus_C", "BP_Gallimimus_C"):
        assert "Parthenogenesis" in mc.allowed_names_for_class(cls), cls


def test_not_hidden_and_offered_on_every_slot():
    # The bHasRequirement set is exactly the exe's seven; Parthenogenesis's
    # gate is the reproduction-unlock byte, armed by the DLL at force-unlock —
    # NOT the owner's n1/n3 unlockable rule.
    assert not mc.is_hidden("Parthenogenesis")
    for slot in mc.SLOT_IDS:
        assert "Parthenogenesis" in mc.allowed_names_for_slot(
            "BP_Deinosuchus_C", slot), slot


# ── the reporter's exact row shape (parked id 10377) ─────────────────────────

def _row_10377():
    return {
        "id": 10377, "steam_id": "76561199517368855",
        "dino_class": "BP_Deinosuchus_C", "growth": 0.872792,
        "is_prime": 1, "elder_stacks": 3,
        "mutations": "Cellular Regeneration|Wader|Reniculate Kidneys|Parthenogenesis",
        "parent_mutations": "Enhanced Digestion|Multichambered Lungs|"
                            "Increased Inspiratory Capacity|Submerged Optical Retention",
        "elder_mutations": "Epidermal Fibrosis|Hydrodynamic|Gastronomic Regeneration|"
                           "Hypermetabolic Inanition|Osteosclerosis|Accelerated Prey Drive|"
                           "Congenital Hypoalgesia|Hemomania",
    }


def test_row_every_slot_open():
    row = _row_10377()
    assert mc.unlocked_slots(row) == frozenset(mc.SLOT_IDS)


def test_row_n4_is_walk_back_able_again():
    """Pre-fix, stored Parthenogenesis flagged BOTH one-way flags (the value
    could never come back), which is what made every touch of the slot feel
    broken. Recognised, diet-legal, slot-legal -> both flags drop."""
    row = _row_10377()
    lm = mc.slot_lock_map(row)["n4"]
    assert lm["locked"] is False
    assert lm["clear_blocks_restore"] is False
    assert lm["overwrite_blocks_restore"] is False
    assert lm["holds_unlockable"] is False


def test_row_overwrite_and_readd_cycle():
    row = _row_10377()
    # replace it…
    canon, current = mc.validate_slot_edit(row, "n4", "Nocturnal")
    assert (canon, current) == ("Nocturnal", "Parthenogenesis")
    # …and the row as it then stands takes it back (the pre-fix module raised
    # "no es una mutación reconocida" right here).
    after = {**row, **mc.apply_slot_edit(row, "n4", "None")}
    canon2, _ = mc.validate_slot_edit(after, "n4", "Parthenogenesis")
    assert canon2 == "Parthenogenesis"


def test_row_duplicate_still_refused():
    row = _row_10377()
    with pytest.raises(mc.MutationEditError, match="duplicadas"):
        mc.validate_slot_edit(row, "n1", "Parthenogenesis")


def test_apply_writes_canonical_spaced_name():
    row = _row_10377()
    cleared = {**row, **mc.apply_slot_edit(row, "n4", "None")}
    out = mc.apply_slot_edit(cleared, "n4", "Parthenogenesis")
    assert out["mutations"].split("|")[3] == "Parthenogenesis"


def test_parent_copy_proves_lineage():
    # A recognised name is what proves a lineage step; the new name must count
    # like any other so a store/nest row carrying it opens its four heredadas.
    assert mc.lineage_generation("Parthenogenesis|None|None|None") == 1


# ── ladders unmoved: the fix recognises a name, it does not widen a gate ─────

def test_non_prime_still_locked_out_of_n4():
    row = {**_row_10377(), "is_prime": 0}
    lock = mc.slot_lock(row, "n4")
    assert lock is not None and lock[0] == "prime"
    with pytest.raises(mc.MutationEditError):
        mc.validate_slot_edit(row, "n4", "Parthenogenesis")


def test_low_growth_still_locks_the_top_rungs():
    row = {**_row_10377(), "growth": 0.69}
    assert mc.slot_lock(row, "n3")[0] == "growth"
    assert mc.slot_lock(row, "n4")[0] == "growth"


# ── the beacon: the NEXT unknown name is a log line, not a ticket ────────────

def test_unknown_stored_name_warns_once_and_never_raises(caplog):
    mc._UNKNOWN_STORED_SEEN.discard("Quantum Gizzard")
    row = {**_row_10377(),
           "mutations": "Quantum Gizzard|None|None|None"}
    with caplog.at_level(logging.WARNING, logger="laislanublar.mutations"):
        first = mc.slot_lock_map(row)
        mc.slot_lock_map(row)              # second walk: no second line
    lines = [r for r in caplog.records if "stored name not in catalog" in r.getMessage()]
    assert len(lines) == 1
    assert "Quantum Gizzard" in lines[0].getMessage()
    # and the walk still answered for all 16 slots
    assert set(first) == set(mc.SLOT_IDS)


def test_known_names_never_trip_the_beacon(caplog):
    with caplog.at_level(logging.WARNING, logger="laislanublar.mutations"):
        mc.slot_lock_map(_row_10377())
    assert not [r for r in caplog.records
                if "stored name not in catalog" in r.getMessage()]


def test_beacon_set_is_bounded():
    try:
        for i in range(200):
            mc.slot_lock_map({**_row_10377(),
                              "mutations": f"Fake Mutation {i}|None|None|None"})
        assert len(mc._UNKNOWN_STORED_SEEN) <= 64
    finally:
        mc._UNKNOWN_STORED_SEEN.clear()
