"""
Leaderboards pure-logic gate — imports the REAL backend/leaderboards.py (stdlib
only, no motor/FastAPI) and pins every decision the server.py I/O half leans on.

Edge cases enumerated up front (four-leg charter):
  empty/zero/missing input · boundary values (month/year rollover, season end)
  · dupes/replays (idempotent seed, award plan) · wrong/absent user docs ·
  never-used states (empty boards) · the dangerous direction (negative bumps
  minting rank; SteamID64 leaking onto the public wire).

Run: python -m pytest backend/tests_local/test_leaderboards.py
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import glitch_catalog  # noqa: E402
import leaderboards  # noqa: E402


# ─── score ──────────────────────────────────────────────────────────────────
def test_score_weights():
    assert leaderboards.compute_score(0, 0, 0) == 0
    assert leaderboards.compute_score(1, 0, 0) == 100
    assert leaderboards.compute_score(0, 1, 0) == 50
    assert leaderboards.compute_score(0, 0, 3600) == 20
    # truncates, never rounds up (parity with the Mongo $toInt pipeline)
    assert leaderboards.compute_score(0, 0, 1800) == 10
    assert leaderboards.compute_score(0, 0, 179) == 0
    assert leaderboards.compute_score(10, 4, 7200) == 1000 + 200 + 40


# ─── seasons ────────────────────────────────────────────────────────────────
def test_season_id_and_bounds():
    now = datetime(2026, 8, 11, 22, 0, tzinfo=timezone.utc)
    assert leaderboards.season_id(now) == "2026-08"
    start, end = leaderboards.season_bounds("2026-08")
    assert start == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_season_december_rollover():
    start, end = leaderboards.season_bounds("2026-12")
    assert end == datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert leaderboards.previous_season_id("2027-01") == "2026-12"
    assert leaderboards.previous_season_id("2026-08") == "2026-07"


def test_seconds_remaining_never_negative():
    past = datetime(2026, 9, 2, tzinfo=timezone.utc)  # after 2026-08 ended
    assert leaderboards.seconds_remaining("2026-08", past) == 0
    almost = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)
    assert leaderboards.seconds_remaining("2026-08", almost) == 1


# ─── bump pipeline (the atomic write server.py sends to Mongo) ──────────────
def test_bump_pipeline_shape():
    p = leaderboards.bump_pipeline({"kills_month": 1}, "row1", "2026-08-11T00:00:00")
    assert isinstance(p, list) and len(p) == 1 and "$set" in p[0]
    s = p[0]["$set"]
    # every bumpable field present (untouched ones as $ifNull passthrough)
    for k in ("kills_month", "deaths_month", "quests_month", "playtime_seconds_month"):
        assert k in s
    assert s["kills_month"] == {"$add": [{"$ifNull": ["$kills_month", 0]}, 1]}
    assert s["deaths_month"] == {"$ifNull": ["$deaths_month", 0]}
    # score recomputed in the SAME update — no read-modify-write window
    assert "$toInt" in s["score"]
    assert s["id"] == {"$ifNull": ["$id", "row1"]}
    assert s["updated_at"] == "2026-08-11T00:00:00"


def test_bump_pipeline_refuses_the_dangerous_direction():
    # a negative delta could mint rank — refused, never written
    for bad in ({"kills_month": -1}, {"quests_month": 2.5}, {"nope": 1}):
        try:
            leaderboards.bump_pipeline(bad, "r", "t")
            assert False, f"accepted {bad!r}"
        except ValueError:
            pass


def test_seed_pipeline_is_max_semantics():
    p = leaderboards.seed_pipeline({"playtime_seconds_month": 240}, "r", "t")
    s = p[0]["$set"]
    assert s["playtime_seconds_month"] == {"$max": [{"$ifNull": ["$playtime_seconds_month", 0]}, 240]}
    # a re-run (replay) writes the same $max — idempotent by construction
    assert leaderboards.seed_pipeline({"playtime_seconds_month": 240}, "r", "t")[0]["$set"][
        "playtime_seconds_month"] == s["playtime_seconds_month"]
    try:
        leaderboards.seed_pipeline({"quests_month": -3}, "r", "t")
        assert False
    except ValueError:
        pass


# ─── backfill parser ────────────────────────────────────────────────────────
def test_playtime_tx_cycles():
    assert leaderboards.playtime_tx_cycles("PrimeMeat por tiempo de juego (3x)") == 3
    # boost-suffixed label still parses (the live _credit_playtime appends it)
    assert leaderboards.playtime_tx_cycles("PrimeMeat por tiempo de juego (2x) · Evento x2") == 2
    # everything else: 0, never a raise
    assert leaderboards.playtime_tx_cycles("Quest: Cazador") == 0
    assert leaderboards.playtime_tx_cycles("") == 0
    assert leaderboards.playtime_tx_cycles(None) == 0
    assert leaderboards.playtime_tx_cycles("PrimeMeat por tiempo de juego (0x)") == 0
    assert leaderboards.playtime_tx_cycles("PrimeMeat por tiempo de juego (999999x)") == 0


# ─── ranking determinism ────────────────────────────────────────────────────
def test_board_sort_and_rank_filter_tiebreak_agree():
    assert leaderboards.board_sort("kills") == [("kills_month", -1), ("user_id", 1)]
    f = leaderboards.rank_filter("kills", "2026-08", 5, "u42")
    assert f == {"season_id": "2026-08",
                 "$or": [{"kills_month": {"$gt": 5}},
                         {"kills_month": 5, "user_id": {"$lt": "u42"}}]}


# ─── wire shape ─────────────────────────────────────────────────────────────
def test_public_row_never_leaks_ids():
    row = {"user_id": "u1", "kills_month": 7, "deaths_month": 2, "quests_month": 1,
           "playtime_seconds_month": 3900, "score": 771}
    user = {"id": "u1", "persona_name": "Rex", "avatar": "a.jpg", "steam_id": "76561198000000001",
            "lb_kills_all": 30, "lb_deaths_all": 10}
    out = leaderboards.public_row("overall", row, user, 1)
    flat = repr(out)
    assert "7656119" not in flat and "steam" not in flat
    assert out["name"] == "Rex" and out["rank"] == 1
    assert out["kd_ratio"] == 3.0
    assert out["display"] == {"primary": "771", "secondary": "puntos"}


def test_public_row_missing_user_doc():
    out = leaderboards.public_row("kills", {"user_id": "u9", "kills_month": 2}, None, 4)
    assert out["name"] == "Cazador" and out["avatar"] is None
    assert out["kd_ratio"] == 0.0  # 0 kills_all / max(1, 0 deaths) — never divides by zero
    assert out["display"] == {"primary": "2", "secondary": "kills"}


def test_display_value_playtime_format():
    d = leaderboards.display_value("playtime", {"playtime_seconds_month": 3661})
    assert d == {"primary": "1h 01m", "secondary": "en el servidor"}
    assert leaderboards.display_value("playtime", {}) == {"primary": "0h 00m", "secondary": "en el servidor"}


# ─── awards ─────────────────────────────────────────────────────────────────
def test_plan_awards_full_and_partial():
    rows = [{"user_id": "a", "score": 900}, {"user_id": "b", "score": 500}, {"user_id": "c", "score": 100},
            {"user_id": "d", "score": 90}]
    plan = leaderboards.plan_awards(rows)
    # 2026-08-18 owner order ("supernova for 123 place in leaderboard"): the
    # rider is on ALL THREE places now. The money ladder is untouched, which
    # is the half this pin exists to defend -- the cosmetic ADDS, it never
    # replaces, so 5M/3M/1M must read exactly as it did before the widening.
    assert plan == [{"rank": 1, "user_id": "a", "prize": 5_000_000, "skin": "supernova"},
                    {"rank": 2, "user_id": "b", "prize": 3_000_000, "skin": "supernova"},
                    {"rank": 3, "user_id": "c", "prize": 1_000_000, "skin": "supernova"}]
    # a SHORT podium still only pays the places that were actually earned --
    # widening the rider must not invent a 2nd or 3rd place that nobody won
    assert leaderboards.plan_awards([{"user_id": "a", "score": 10},
                                     {"user_id": "b", "score": 4}]) == [
        {"rank": 1, "user_id": "a", "prize": 5_000_000, "skin": "supernova"},
        {"rank": 2, "user_id": "b", "prize": 3_000_000, "skin": "supernova"}]
    # fewer than 3 scorers → fewer prizes; zero-score rows never win
    assert leaderboards.plan_awards([{"user_id": "a", "score": 10}, {"user_id": "b", "score": 0}]) == [
        {"rank": 1, "user_id": "a", "prize": 5_000_000, "skin": "supernova"}]
    # never-used state: empty season pays nobody
    assert leaderboards.plan_awards([]) == []
    # malformed row (no user_id) is skipped, not paid and not raised on
    assert leaderboards.plan_awards([{"score": 50}]) == []


def test_award_tx_label():
    lbl = leaderboards.award_tx_label("2026-08", 1)
    assert "2026-08" in lbl and "1º" in lbl


# ─── cosmetic prize rider (2026-08-16) ──────────────────────────────────────
def test_prize_skin_is_the_owners_payload_byte_for_byte():
    """The 1º prize must emit the EXACT CustomizerData the owner handed over
    (his payload 2 — pattern 2 / variation 8). Pinned on the WIRE command, not
    just the table, because emission is where a fold would repaint it."""
    gid = leaderboards.PRIZE_SKIN_BY_RANK[1]
    assert gid == "supernova"
    cmd = glitch_catalog.build_glitch_command(gid, "Actor", "Class", "765", female=False)
    assert cmd["variation"] == 8.0 and cmd["pattern"] == 2
    assert cmd["body"] == [-999999.0, -9999999.0, -9999999.0, -999.0]
    assert cmd["markings"] == [-9999999.0, -999999.0, -9999.0, -999889.0]
    assert cmd["flank"] == [25.0, 4.0, 25.0, -99999.0]
    assert cmd["underbelly"] == [-999999.0, -99999999.0, -9999999.0, -999.0]
    assert cmd["detail1"] == [-999999.0, -999999.0, -999999.0, -999667.0]
    assert cmd["eyes"] == [255.0, -999999.0, 60.0, 22000.0]
    assert cmd["male_display"] == [-9999998.0, 1987.0, 1019.0, -999.0]


def test_prize_skin_ranks_are_real_ranks_and_real_designs():
    for rank, gid in leaderboards.PRIZE_SKIN_BY_RANK.items():
        assert rank in leaderboards.PRIZE_TABLE
        assert gid in glitch_catalog.GLITCH_BY_ID


def test_the_whole_podium_wears_supernova_2026_08_18():
    """Owner order: "supernova for 123 place in leaderboard". Pinned as the
    exact table rather than "rank 2 is not None", so a half-applied widening
    (say 1 and 2 only, or 2 and 3 pointing at a different design) is red."""
    assert leaderboards.PRIZE_SKIN_BY_RANK == {
        1: "supernova", 2: "supernova", 3: "supernova"}
    # the money ladder is the OTHER half of the same sentence and did not move
    assert leaderboards.PRIZE_TABLE == {1: 5_000_000, 2: 3_000_000, 3: 1_000_000}


def test_the_pass_only_design_is_never_a_leaderboard_prize():
    """The other half of the 2026-08-18 order -- "constelacion for battlepass
    only". A prize table naming it would be a second door onto an exclusive
    design, and this board is the surface it was on until today."""
    assert "constelacion" not in leaderboards.PRIZE_SKIN_BY_RANK.values()
    assert glitch_catalog.crate_eligible("constelacion") is False
    # ...and the design this board DOES pay is not itself pass-exclusive
    for gid in leaderboards.PRIZE_SKIN_BY_RANK.values():
        assert not glitch_catalog.GLITCH_BY_ID[gid].get("bp_exclusive")


def test_prize_skin_validator_refuses_a_typo(monkeypatch):
    """The dangerous direction: a prize pointing at nothing. It must refuse at
    import rather than hand the champion an empty grant a month later."""
    monkeypatch.setattr(leaderboards, "PRIZE_SKIN_BY_RANK", {1: "no-such-skin"})
    with pytest.raises(RuntimeError):
        leaderboards._validate_prize_skins()
    monkeypatch.setattr(leaderboards, "PRIZE_SKIN_BY_RANK", {9: "supernova"})
    with pytest.raises(RuntimeError):
        leaderboards._validate_prize_skins()


def test_prize_skin_cards_never_leak_a_picture_or_the_payload():
    """This rides the PUBLIC, signed-out hub. A glitch card is a name + colour
    proximity — no render URL, and no channel value the recipe could be read
    back from (every negative channel folds to #000000)."""
    cards = leaderboards.prize_skin_cards()
    # three cards since 2026-08-18 -- and the leak checks run on EVERY one of
    # them, because a widening that only sanitised the card it already had is
    # exactly how a paid recipe reaches a signed-out page.
    assert set(cards) == {"1", "2", "3"}
    for rank in ("1", "2", "3"):
        card = cards[rank]
        assert card["glitch_id"] == "supernova" and card["name"] == "Supernova"
        assert card["image"] == ""
        blob = repr(card)
        for leaked in ("-999999", "-9999999", "22000", "payload", "variation"):
            assert leaked not in blob
        assert all(h.startswith("#") and len(h) == 7 for h in card["proximity"])


def test_award_skin_source_names_the_season_and_the_place():
    src = leaderboards.award_skin_source("2026-08", 1)
    assert "2026-08" in src and "1º" in src
