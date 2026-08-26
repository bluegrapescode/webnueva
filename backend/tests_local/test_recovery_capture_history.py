"""Gate for the recovery capture-history wave (2026-07-29).

WHAT THIS PROVES
----------------
A dino recovered through /admin Recuperacion used to come back BARE — right
species, right size, no mutations, no Prime, no entomb stacks — whenever the
admin clicked more than a few seconds after the death. The cause was that
``dino_snapshots`` held exactly ONE document per player, overwritten every 20 s,
so the dead dino's state was destroyed by its owner's own respawn.

Fixtures below are REAL prod records, named where they came from. The
discriminating case is the live incident: sid 76561199023620899 (@ninjayas_),
Allosaurus, died 2026-07-29 15:01:17Z at 87.7% growth, recovered 17:21:55Z into
vault row 1707, redeemed 17:27 with mutation_expected_total = 0.

Run:  py -3.12 -m pytest tests_local/test_recovery_capture_history.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dino_recovery as dr


# ---------------------------------------------------------------------------
# REAL prod records
# ---------------------------------------------------------------------------
SID = "76561199023620899"

# From Saved/death_causes.log, verbatim ts/growth/cause.
DEATH_ALLO_1501 = {
    "death_key": "76561199023620899:1785337277:Allosaurus",
    "steam_id": SID, "ts": 1785337277, "dino_class": "BP_Allosaurus_C",
    "species": "Allosaurus", "growth": 0.877, "growth_pct": 88, "cause": "bleed",
}
DEATH_TREX_1647 = {
    "death_key": "76561199023620899:1785343643:Tyrannosaurus",
    "steam_id": SID, "ts": 1785343643, "dino_class": "BP_Tyrannosaurus_C",
    "species": "Tyrannosaurus", "growth": 0.284, "growth_pct": 28, "cause": "unknown",
}
DEATH_ALLO_1721 = {
    "death_key": "76561199023620899:1785345693:Allosaurus",
    "steam_id": SID, "ts": 1785345693, "dino_class": "BP_Allosaurus_C",
    "species": "Allosaurus", "growth": 0.544, "growth_pct": 54, "cause": "unknown",
}


def capture(cls, seen_at, growth, mutations=dr.EMPTY_MUTATIONS, parents=dr.EMPTY_MUTATIONS,
            elders=dr.EMPTY_ELDER_MUTATIONS, stacks=0, prime=False, elder=False,
            conditions=dr.ABSENT, mig=dr.ABSENT, pat=dr.ABSENT):
    return {
        "steam_id": SID, "dino_class": cls, "species": dr.clean_species(cls),
        "growth": growth, "is_prime": prime, "is_elder": elder,
        "mutations": mutations, "parent_mutations": parents, "elder_mutations": elders,
        "elder_stacks": stacks, "prime_conditions": conditions,
        "prime_route_mig": mig, "prime_route_pat": pat,
        "skin_code": "Allosaurus10082766FFF726555FF4A4740FF252526FF6F3B2AFF",
        "diet_a": 0.0, "diet_b": 0.0, "diet_c": 0.0, "seen_at": seen_at,
    }


# The state his Allosaurus was last seen in, 17 s before it bled out. The mod's
# own [Prime/baseline] line at 15:01:17Z reads `done=6 eligible=true`, so six of
# the ten missions were complete: 0b0000111111 = 63.
CAPTURE_ALLO_ALIVE = capture(
    "BP_Allosaurus_C", 1785337260, 0.87683,
    mutations="Hemomania|Gastronomic Regeneration|Osteosclerosis|Epidermal Fibrosis",
    parents="Accelerated Prey Drive|Hemomania|None|None",
    prime=True, conditions=63, mig=1, pat=2)

# What overwrote it 14 s after the death: the fresh Allosaurus he respawned as.
CAPTURE_ALLO_FRESH = capture("BP_Allosaurus_C", 1785337291, 0.05)
# ...and then a Tyrannosaurus, and then another Allosaurus. This is the rolling
# document as it actually stood when the admin clicked at 17:21:55Z.
CAPTURE_TREX = capture("BP_Tyrannosaurus_C", 1785342778, 0.2757,
                       mutations="Osteosclerosis|None|None|None")
CAPTURE_ALLO_LATER = capture("BP_Allosaurus_C", 1785345660, 0.544, prime=True)

HISTORY = [CAPTURE_ALLO_ALIVE, CAPTURE_ALLO_FRESH, CAPTURE_TREX, CAPTURE_ALLO_LATER]
ROLLING_AT_CLICK = CAPTURE_ALLO_LATER


def test_fixture_precondition_history_has_more_than_one_capture():
    """A history test on a one-document history proves nothing about history."""
    assert len(HISTORY) > 1
    assert len({c["seen_at"] for c in HISTORY}) == len(HISTORY)
    assert len({c["dino_class"] for c in HISTORY}) > 1
    # And the incident must actually be a long-lag one, or it is not this bug.
    assert DEATH_ALLO_1501["ts"] - CAPTURE_ALLO_ALIVE["seen_at"] > 0
    assert 1785345715 - DEATH_ALLO_1501["ts"] > 2 * 60 * 60  # admin clicked 2h20m later


# ---------------------------------------------------------------------------
# 1. the incident, both ways round
# ---------------------------------------------------------------------------
def test_negative_control_the_rolling_document_alone_cannot_describe_the_death():
    """This is the bug, reproduced: the only surviving capture is the wrong dino."""
    assert dr.snapshot_reject_reason(ROLLING_AT_CLICK, DEATH_ALLO_1501) == "after_death"
    assert dr.snapshot_matches_death(ROLLING_AT_CLICK, DEATH_ALLO_1501) is False


def test_history_binds_the_capture_taken_while_the_dino_was_alive():
    got = dr.pick_history_snapshot(HISTORY, DEATH_ALLO_1501)
    assert got is CAPTURE_ALLO_ALIVE
    assert dr.count_mutations(got["mutations"]) == 4
    assert got["is_prime"] is True
    assert got["prime_conditions"] == 63


def test_the_grant_that_was_made_bare_now_carries_everything():
    payload = dr.build_recovery_payload(
        DEATH_ALLO_1501["dino_class"], DEATH_ALLO_1501["growth"],
        snapshot=dr.pick_history_snapshot(HISTORY, DEATH_ALLO_1501), skin_data="")
    assert payload["is_prime"] is True
    assert dr.count_mutations(payload["mutations"]) == 4
    assert dr.count_mutations(payload["parent_mutations"]) == 2
    assert payload["prime_conditions"] == 63
    assert payload["prime_route_mig"] == 1
    assert payload["prime_route_pat"] == 2
    assert dr.payload_is_bare(payload) is False


def test_without_history_the_same_call_is_bare_and_says_so():
    payload = dr.build_recovery_payload(
        DEATH_ALLO_1501["dino_class"], DEATH_ALLO_1501["growth"],
        snapshot=None, skin_data="")
    assert dr.payload_is_bare(payload) is True
    assert payload["mutations"] == dr.EMPTY_MUTATIONS
    assert payload["is_prime"] is False
    assert payload["prime_conditions"] is dr.ABSENT


# ---------------------------------------------------------------------------
# 2. each death binds its OWN capture
# ---------------------------------------------------------------------------
def test_every_death_in_the_list_gets_its_own_capture_not_just_one():
    deaths = [DEATH_ALLO_1721, DEATH_TREX_1647, DEATH_ALLO_1501]  # newest first
    lost = dr.build_lost_list(deaths, history=HISTORY, snapshot=ROLLING_AT_CLICK)
    by_key = {item["death_key"]: item for item in lost}
    assert by_key[DEATH_ALLO_1501["death_key"]]["mutations_count"] == 4
    assert by_key[DEATH_TREX_1647["death_key"]]["mutations_count"] == 1
    assert by_key[DEATH_TREX_1647["death_key"]]["detail"] == "full"


def test_a_later_death_never_inherits_an_earlier_dinos_capture():
    """Binding must look BACKWARD from the death, never forward."""
    got = dr.pick_history_snapshot([CAPTURE_ALLO_LATER], DEATH_ALLO_1501)
    assert got is None


def test_the_trex_death_does_not_take_the_allosaurus_mutations():
    got = dr.pick_history_snapshot(HISTORY, DEATH_TREX_1647)
    assert got is CAPTURE_TREX
    assert got["dino_class"] == "BP_Tyrannosaurus_C"


# ---------------------------------------------------------------------------
# 3. the window is a label, not a gate
# ---------------------------------------------------------------------------
def test_an_eleven_hour_lag_still_binds():
    old = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] - 11 * 3600, 0.87,
                  mutations="Hemomania|None|None|None", prime=True)
    assert dr.pick_history_snapshot([old], DEATH_ALLO_1501) is old
    assert dr.snapshot_age_s(old, DEATH_ALLO_1501) == 11 * 3600


def test_the_old_thirty_minute_gate_would_have_rejected_that_same_capture():
    old = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] - 11 * 3600, 0.87)
    assert dr.snapshot_reject_reason(
        old, DEATH_ALLO_1501, max_age_s=dr.SNAPSHOT_STRICT_AGE_S) == "too_old"


def test_a_capture_beyond_retention_is_still_refused():
    ancient = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] - dr.SNAPSHOT_MAX_AGE_S - 60, 0.5)
    assert dr.pick_history_snapshot([ancient], DEATH_ALLO_1501) is None


def test_a_capture_a_few_seconds_after_the_death_still_counts():
    """A 20 s loop can stamp a tick just past the kill; that is the same dino."""
    late = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] + 30, 0.877,
                   mutations="Hemomania|None|None|None")
    assert dr.pick_history_snapshot([late], DEATH_ALLO_1501) is late


# ---------------------------------------------------------------------------
# 4. NULL is not 0
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw", [None, "", "   ", "abc", [], {}, True, False])
def test_unusable_mission_bits_are_absent_never_zero(raw):
    assert dr.prime_conditions_value(raw) is dr.ABSENT


def test_a_real_zero_survives_as_zero():
    assert dr.prime_conditions_value(0) == 0
    assert dr.prime_conditions_value("0") == 0


def test_absent_and_zero_are_different_signatures():
    a = capture("BP_Allosaurus_C", 100, 0.5, conditions=dr.ABSENT)
    b = capture("BP_Allosaurus_C", 100, 0.5, conditions=0)
    assert dr.snapshot_signature(a) != dr.snapshot_signature(b)


def test_a_capture_with_no_mission_bits_does_not_zero_the_payload():
    snap = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] - 10, 0.877,
                   mutations="Hemomania|None|None|None", prime=True, conditions=dr.ABSENT)
    payload = dr.build_recovery_payload("BP_Allosaurus_C", 0.877, snapshot=snap)
    assert payload["prime_conditions"] is dr.ABSENT


# ---------------------------------------------------------------------------
# 5. we never invent a completed Prime quest
# ---------------------------------------------------------------------------
def test_knowing_a_dino_was_prime_never_becomes_all_ten_missions():
    """The mod inflates absent bits to 1023 for any elder row at ANY growth.

    Doing it here as well would put an entomb juvenile's force-completed Prime
    quest beyond the reach of any web-side fix.
    """
    snap = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] - 10, 0.30,
                   prime=True, elder=True, stacks=4, conditions=dr.ABSENT)
    payload = dr.build_recovery_payload("BP_Allosaurus_C", 0.30, snapshot=snap)
    assert payload["prime_conditions"] is not dr.PRIME_CONDITIONS_ALL
    assert payload["prime_conditions"] is dr.ABSENT
    assert payload["is_prime"] is True  # the flag is honest; the bits are not invented


def test_mission_bits_are_clamped_to_the_ten_that_exist():
    assert dr.prime_conditions_value(99999) == dr.PRIME_CONDITIONS_ALL
    assert dr.prime_conditions_value(-5) == 0


def test_an_engine_infinity_saturates_to_the_ceiling_not_the_floor():
    """★int(float('inf')) RAISES; a naive except-branch would return the FLOOR.

    Reading a maxed-out counter as zero is the worst possible direction for
    this field — it would look like a player had completed nothing.
    """
    assert dr.prime_conditions_value(float("inf")) == dr.PRIME_CONDITIONS_ALL
    assert dr.prime_conditions_value(float("-inf")) == 0
    assert dr.prime_route_values(float("inf"), float("inf")) == (
        dr.PRIME_ROUTE_MIG_MAX, dr.PRIME_ROUTE_PAT_MAX)


def test_the_payload_never_upgrades_a_prime_flag_into_completed_missions():
    """The one seam through which inflation could enter: the payload builder."""
    snap = capture("BP_Allosaurus_C", 100, 0.99, prime=True, elder=True, stacks=3,
                   conditions=dr.ABSENT)
    payload = dr.build_recovery_payload("BP_Allosaurus_C", 0.99, snapshot=snap)
    assert payload["is_prime"] is True
    assert payload["prime_conditions"] is dr.ABSENT
    # and an explicitly recorded partial stays partial
    snap2 = capture("BP_Allosaurus_C", 100, 0.99, prime=True, conditions=63)
    assert dr.build_recovery_payload(
        "BP_Allosaurus_C", 0.99, snapshot=snap2)["prime_conditions"] == 63


def test_route_counters_clamp_to_the_mods_own_limits():
    assert dr.prime_route_values(9, 9) == (dr.PRIME_ROUTE_MIG_MAX, dr.PRIME_ROUTE_PAT_MAX)
    assert dr.prime_route_values(-1, -1) == (0, 0)
    assert dr.prime_route_values(None, None) == (dr.ABSENT, dr.ABSENT)


# ---------------------------------------------------------------------------
# 6. slots are positional
# ---------------------------------------------------------------------------
def test_a_blank_slot_survives_as_a_slot():
    assert dr.normalize_slots("A||C|", 4) == "A|None|C|None"


def test_slot_widths_are_enforced_in_both_directions():
    assert dr.normalize_slots("A", 4) == "A|None|None|None"
    assert dr.normalize_slots("A|B|C|D|E|F", 4) == "A|B|C|D"
    assert dr.normalize_slots("", 8) == dr.EMPTY_ELDER_MUTATIONS


def test_elder_interleave_order_is_preserved_verbatim():
    """1A,1B,2A,2B,3A,3B,4A,4B — a blocked ordering swaps six of the eight."""
    wire = "M1A|M1B|M2A|M2B|M3A|M3B|M4A|M4B"
    assert dr.normalize_slots(wire, dr.ELDER_MUTATION_SLOTS) == wire
    payload = dr.build_recovery_payload(
        "BP_Allosaurus_C", 0.9,
        snapshot=capture("BP_Allosaurus_C", 100, 0.9, elders=wire, stacks=4))
    assert payload["elder_mutations"] == wire


def test_elder_slots_without_entombs_are_flagged_not_swallowed():
    assert dr.elder_slots_look_corrupt("Aa|None|None|None|None|None|None|None", 0) is True
    assert dr.elder_slots_look_corrupt("Aa|None|None|None|None|None|None|None", 2) is False
    assert dr.elder_slots_look_corrupt(dr.EMPTY_ELDER_MUTATIONS, 0) is False


# ---------------------------------------------------------------------------
# 7. the failure is loud, and the log line is discriminating
# ---------------------------------------------------------------------------
def test_every_reject_has_a_named_reason():
    assert dr.snapshot_reject_reason(None, DEATH_ALLO_1501) == "no_capture"
    assert dr.snapshot_reject_reason(CAPTURE_TREX, DEATH_ALLO_1501) == "class_mismatch"
    assert dr.snapshot_reject_reason(CAPTURE_ALLO_LATER, DEATH_ALLO_1501) == "after_death"
    assert dr.snapshot_reject_reason(
        capture("BP_Allosaurus_C", 0, 0.5), DEATH_ALLO_1501) == "no_timestamp"
    assert dr.snapshot_reject_reason(CAPTURE_ALLO_ALIVE, DEATH_ALLO_1501) == ""


def test_the_log_summary_tells_a_bare_grant_from_a_complete_one():
    """★The whole life of this bug, both printed the same line."""
    full = dr.payload_summary(dr.build_recovery_payload(
        "BP_Allosaurus_C", 0.877, snapshot=CAPTURE_ALLO_ALIVE))
    bare = dr.payload_summary(dr.build_recovery_payload("BP_Allosaurus_C", 0.877))
    assert full != bare
    assert "muts=4" in full and "prime=1" in full and "conditions=63" in full
    assert "muts=0" in bare and "prime=0" in bare and "conditions=absent" in bare


def test_bare_detection_counts_every_kind_of_state():
    base = dict(dr.build_recovery_payload("BP_Allosaurus_C", 0.5))
    assert dr.payload_is_bare(base) is True
    for key, value in (("is_prime", True), ("is_elder", True), ("elder_stacks", 3),
                       ("mutations", "Hemomania|None|None|None"),
                       ("parent_mutations", "Hemomania|None|None|None"),
                       ("elder_mutations", "Hemomania|None|None|None|None|None|None|None")):
        one = dict(base)
        one[key] = value
        assert dr.payload_is_bare(one) is False, key


# ---------------------------------------------------------------------------
# 8. last-known-good is a labelled fallback, never a silent one
# ---------------------------------------------------------------------------
# The realistic shape of an unbindable death: the LAST thing captured before it
# was a different species, so the player swapped and nothing we hold describes
# the animal that died. An earlier capture of the right species is all there is.
SWAP_BEFORE = capture("BP_Tyrannosaurus_C", DEATH_ALLO_1501["ts"] - 120, 0.30,
                      mutations="Osteosclerosis|None|None|None")
EARLIER_ALLO = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] - 7200, 0.40,
                       mutations="Hemomania|None|None|None", prime=True)


def test_lkg_only_fires_when_nothing_binds():
    # The newest capture before the death is the wrong species -> no exact bind.
    assert dr.pick_history_snapshot([SWAP_BEFORE, EARLIER_ALLO], DEATH_ALLO_1501) is None
    assert dr.pick_lkg_snapshot([SWAP_BEFORE, EARLIER_ALLO], DEATH_ALLO_1501) is EARLIER_ALLO


def test_a_stale_same_species_capture_with_nothing_in_between_is_an_exact_bind():
    """No swap happened, so the last state we saw IS the dino that died.

    Age alone does not demote it — gating on age was the original bug.
    """
    assert dr.pick_history_snapshot([EARLIER_ALLO], DEATH_ALLO_1501) is EARLIER_ALLO


def test_lkg_never_reaches_forward_in_time():
    later = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] + 3600, 0.9,
                    mutations="Hemomania|None|None|None", prime=True)
    assert dr.pick_lkg_snapshot([later], DEATH_ALLO_1501) is None


def test_lkg_never_launders_an_empty_capture_into_a_guess():
    empty = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] - 3600, 0.4)
    assert dr.pick_lkg_snapshot([empty], DEATH_ALLO_1501) is None


def test_lkg_is_labelled_in_the_list_and_keeps_the_deaths_own_growth():
    lost = dr.build_lost_list([DEATH_ALLO_1501], history=[SWAP_BEFORE, EARLIER_ALLO])
    assert lost[0]["detail"] == "lkg"
    # 0.877 from the death, NOT 0.40 from the other animal.
    assert lost[0]["growth"] == pytest.approx(0.877)
    assert lost[0]["mutations_count"] == 1


def test_lkg_can_be_switched_off():
    lost = dr.build_lost_list([DEATH_ALLO_1501], history=[SWAP_BEFORE, EARLIER_ALLO],
                              allow_lkg=False)
    assert lost[0]["detail"] == "partial"
    assert lost[0]["mutations_count"] == 0


# ---------------------------------------------------------------------------
# 9. the list reports what it bound
# ---------------------------------------------------------------------------
def test_the_list_shows_how_old_the_capture_is():
    lost = dr.build_lost_list([DEATH_ALLO_1501], history=HISTORY)
    assert lost[0]["snapshot_age_s"] == DEATH_ALLO_1501["ts"] - CAPTURE_ALLO_ALIVE["seen_at"]
    assert lost[0]["prime_missions_done"] == 6  # 0b111111
    assert lost[0]["parent_mutations_count"] == 2


def test_an_unbound_death_reports_nothing_rather_than_something_false():
    lost = dr.build_lost_list([DEATH_ALLO_1501], history=[], snapshot=None)
    item = lost[0]
    assert item["detail"] == "partial"
    assert item["mutations_count"] == 0
    assert item["prime_conditions"] is dr.ABSENT
    assert item["prime_missions_done"] is None
    assert item["snapshot_age_s"] == 0


# ---------------------------------------------------------------------------
# 10. still total — a recovery surface that 500s is worse than one showing nothing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("junk", [None, 0, "", [], {}, object(), float("nan"), float("inf")])
def test_hostile_inputs_never_raise(junk):
    dr.snapshot_reject_reason(junk, DEATH_ALLO_1501)
    dr.snapshot_matches_death(junk, junk)
    dr.snapshot_age_s(junk, junk)
    dr.pick_history_snapshot([junk], DEATH_ALLO_1501)
    dr.pick_lkg_snapshot([junk], DEATH_ALLO_1501)
    dr.normalize_slots(junk, 4)
    dr.payload_is_bare(junk)
    dr.payload_summary(junk)
    dr.prime_conditions_value(junk)
    dr.prime_route_values(junk, junk)
    dr.build_lost_list([DEATH_ALLO_1501], history=[junk])


def test_a_capture_carrying_infinity_does_not_poison_the_payload():
    snap = capture("BP_Allosaurus_C", DEATH_ALLO_1501["ts"] - 10, float("inf"),
                   stacks=float("inf"))
    payload = dr.build_recovery_payload("BP_Allosaurus_C", 0.877, snapshot=snap)
    assert 0.0 <= payload["growth"] <= 1.0
    assert payload["elder_stacks"] == 0


def test_history_scan_is_bounded():
    assert dr.SNAPSHOT_HISTORY_SCAN > 0
    assert dr.SNAPSHOT_MAX_AGE_S >= dr.SNAPSHOT_HISTORY_TTL_S
