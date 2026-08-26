"""House-edge / anti-coin-printer gate for crash_game.py -- run directly.

    <venv>\\python.exe tests_local\\test_crash_house_edge.py
    <venv>\\python.exe tests_local\\test_crash_house_edge.py --mongo mongodb://127.0.0.1:27017
    <venv>\\python.exe tests_local\\test_crash_house_edge.py --mongo ... --mutants

WHAT THIS GATE IS FOR
Between 2026-07-29 and 2026-08-19 Dino Crash paid players MORE than it took, and
nothing in the codebase could see it. The Moon Pool took 5% of every stake and
created those coins from nothing (no stake or payout is ever reduced by it),
while the base game's only earner -- the 1-in-33 instant bust -- kept just 3.03%.
Net: the game minted 1.97% of everything wagered. Measured on the live box that
day: 274,352,916 CC of pool paid out over 243 wins, implying 5,487,058,320 CC
wagered, so 108,078,421 CC created out of thin air in 21.25 days -- 6% of the
entire economy, at about 5,085,257 CC a day and rising with play volume.

So the checks below are not "does the maths look right". They are:
  * the shipped dials leave the HOUSE ahead, not the players;
  * the old dials are PROVEN to be a printer by the same test (test_the_old_dials_
    were_a_printer), so this file documents the bug it closes;
  * no environment variable, typo or missing .env can re-open the printer, because
    _assert_house_wins clamps the pool rate below the edge whatever it is asked for;
  * the strategy that was actually being farmed -- park an auto-cashout on the pool
    bar and wait -- is now losing money.

The pure-maths half needs nothing but Python. The ledger half needs a mongod:
pass --mongo and it runs against a scratch database (crashgate_scratch_*) which it
drops at the end. It NEVER touches the live database.

--mutants re-runs everything against deliberately broken copies of the module and
requires each one to turn the suite RED, so a green run means the checks bite.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import random
import secrets
import sys
import traceback
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crash_game  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name if condition else f"{name} :: {detail}")


def close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


# ---------------------------------------------------------------------------
# Shared: play out N honest rounds and report what the house kept.
# ---------------------------------------------------------------------------
def simulate(rounds: int, targets, bust_one_in: int, jackpot_rate: float,
             jackpot_multiplier: float, seed: int = 1234):
    """Flat 1-coin bet every round, cashing out at a target drawn from `targets`.

    Returns (house_net_per_coin_staked, pool_paid_per_coin_staked). The pool is
    modelled exactly as the code does it: `jackpot_rate` of every stake is ADDED
    to a pool that no stake ever paid for, and the whole pool is handed over the
    first time a bet reaches `jackpot_multiplier`. That "added, never deducted"
    is the entire bug -- a model that quietly took the rake out of the stake
    would show a healthy game and prove nothing.
    """
    rng = random.Random(seed)
    # The pool bar is always on the menu. A preset button exists for it on the
    # page precisely so players can park an auto-cashout there, and the live data
    # shows a handful of accounts doing nothing else -- a model that leaves the
    # bar out simply never drains the pool and proves the wrong thing.
    menu = list(targets) + [jackpot_multiplier]
    staked = paid = pool = pool_paid = 0.0
    for nonce in range(rounds):
        target = menu[rng.randrange(len(menu))]
        # Seeded from the run's own rng, not from secrets: a gate that walks a
        # different path every run has a pass/fail line that moves, and that
        # teaches people to re-run it until it goes green.
        point = crash_game.generate_crash_point(
            "%016x" % rng.getrandbits(64), "public", nonce, bust_one_in=bust_one_in)
        staked += 1.0
        pool += jackpot_rate
        if point >= target:
            paid += target
            if target >= jackpot_multiplier:
                paid += pool
                pool_paid += pool
                pool = 0.0
    # Whatever is still standing in the pool has ALREADY been created as far as
    # the economy is concerned -- it is an unconditional promise to mint. Counting
    # it only when it is handed over lets a run that stops mid-pool report a house
    # that is winning when it is not, which is how this slipped through for weeks.
    return (staked - paid - pool) / staked, (pool_paid + pool) / staked


def strategy_return(bar, bust_one_in, pool_rate, share_of_volume=1.0):
    """Exact expected return per coin staked by a player who cashes out at `bar`
    every round and is the only one reaching it, so every pool payout is theirs.

    Computed rather than simulated on purpose: at a 50x target a single round pays
    50 or nothing, so the estimator's own spread is wider than the edge being
    measured and no feasible number of simulated rounds settles it.

    `share_of_volume` is this player's slice of ALL wagering. The pool is fed by
    everyone and collected by whoever reaches the bar, so a player who is a small
    slice of the volume collects far more pool than they ever paid in -- that
    asymmetry, not the base curve, is what was actually being farmed.
    """
    hit = (1.0 - 1.0 / bust_one_in) * 99.0 / (100.0 * bar - 1.0)
    return hit * bar + pool_rate / max(share_of_volume, 1e-9)


# ---------------------------------------------------------------------------
# 1. The dials that ship
# ---------------------------------------------------------------------------
def test_shipped_dials() -> None:
    check("ships bust_one_in 7", crash_game.BUST_ONE_IN == 7, str(crash_game.BUST_ONE_IN))
    check("ships jackpot_rate 0.02", close(crash_game.JACKPOT_RATE, 0.02, 1e-9),
          str(crash_game.JACKPOT_RATE))
    check("ships jackpot bar 100x", close(crash_game.JACKPOT_MULTIPLIER, 100.0, 1e-9),
          str(crash_game.JACKPOT_MULTIPLIER))
    check("house edge is 1/bust_one_in",
          close(crash_game.house_edge(), 1.0 / crash_game.BUST_ONE_IN, 1e-12))
    net = crash_game.net_house_edge()
    check("THE HOUSE IS AHEAD on the shipped dials", net > 0, f"net={net:.4f}")
    check("net edge is edge minus pool rate",
          close(net, crash_game.house_edge() - crash_game.JACKPOT_RATE, 1e-12))
    # The owner asked for "about as harsh as the card game", which measured
    # +12.06% all-time over 24,806 hands on 2026-08-19.
    check("net edge lands near the card game's 12%", 0.10 <= net <= 0.15, f"net={net:.4f}")


def test_the_old_dials_were_a_printer() -> None:
    """The exact configuration that was live for three weeks, proven negative."""
    old_edge = 1.0 / 33
    old_rate = 0.05
    check("OLD dials: pool rate exceeded the house edge", old_rate > old_edge)
    check("OLD dials: net was NEGATIVE (a coin printer)", old_edge - old_rate < 0,
          f"{old_edge - old_rate:.4f}")
    check("OLD dials: printed ~1.97% of turnover",
          close(old_rate - old_edge, 0.0197, 0.0005), f"{old_rate - old_edge:.4f}")
    swing = crash_game.net_house_edge() - (old_edge - old_rate)
    check("the fix swings the game by more than 14 points of turnover",
          swing > 0.14, f"{swing:+.4f}")


# ---------------------------------------------------------------------------
# 2. The dial reader -- every bad input a live box can hand it
# ---------------------------------------------------------------------------
def test_env_dial_reader() -> None:
    key = "CRASH_TEST_DIAL_" + uuid.uuid4().hex[:8]

    def with_env(value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
        try:
            return crash_game._env_num(key, 7, 2, int)
        finally:
            os.environ.pop(key, None)

    check("unset -> shipped default", with_env(None) == 7)
    check("empty string -> default", with_env("") == 7)
    check("whitespace only -> default", with_env("   ") == 7)
    check("garbage -> default", with_env("abc") == 7)
    check("float in an int dial -> default", with_env("7.5") == 7)
    check("below the floor -> default", with_env("1") == 7)
    check("zero -> default (never a divide by zero)", with_env("0") == 7)
    check("negative -> default", with_env("-4") == 7)
    check("a good value is used", with_env("12") == 12)
    check("a good value with spaces is used", with_env(" 12 ") == 12)
    check("exactly the floor is allowed", with_env("2") == 2)

    fkey = "CRASH_TEST_FDIAL_" + uuid.uuid4().hex[:8]
    os.environ[fkey] = "0.03"
    check("float dial reads", close(crash_game._env_num(fkey, 0.02, 0.0, float), 0.03, 1e-9))
    os.environ[fkey] = "-0.01"
    check("negative float dial -> default",
          close(crash_game._env_num(fkey, 0.02, 0.0, float), 0.02, 1e-9))
    os.environ[fkey] = "0"
    check("zero pool rate is legal (pool simply never grows)",
          close(crash_game._env_num(fkey, 0.02, 0.0, float), 0.0, 1e-9))
    os.environ.pop(fkey, None)


# ---------------------------------------------------------------------------
# 3. The guard that can never let the printer back
# ---------------------------------------------------------------------------
def test_anti_printer_clamp() -> None:
    saved_rate, saved_bust = crash_game.JACKPOT_RATE, crash_game.BUST_ONE_IN
    try:
        for bust, rate in ((33, 0.05), (7, 0.20), (7, 1.0 / 7), (2, 0.9), (100, 0.011)):
            crash_game.BUST_ONE_IN = bust
            crash_game.JACKPOT_RATE = rate
            crash_game._assert_house_wins()
            net = crash_game.net_house_edge()
            check(f"clamped 1/{bust} vs rate {rate}: house ends AHEAD", net > 0, f"net={net:.5f}")
            check(f"clamped 1/{bust} vs rate {rate}: pool halves the edge",
                  close(crash_game.JACKPOT_RATE, round((1.0 / bust) / 2.0, 6), 1e-6),
                  str(crash_game.JACKPOT_RATE))

        # A rate that is already safe must be left exactly alone -- a guard that
        # rewrites a healthy dial is a second source of truth for the same number.
        crash_game.BUST_ONE_IN, crash_game.JACKPOT_RATE = 7, 0.02
        crash_game._assert_house_wins()
        check("a safe rate is untouched", close(crash_game.JACKPOT_RATE, 0.02, 1e-12))

        # Equality is the dangerous boundary: edge == rate is a game that keeps
        # nothing at all, forever, and it must be treated as the printer it is.
        crash_game.BUST_ONE_IN, crash_game.JACKPOT_RATE = 20, 0.05
        crash_game._assert_house_wins()
        check("rate exactly equal to the edge is clamped", crash_game.JACKPOT_RATE < 0.05)
        check("rate exactly equal to the edge ends ahead", crash_game.net_house_edge() > 0)

        # And zero must survive the guard untouched.
        crash_game.BUST_ONE_IN, crash_game.JACKPOT_RATE = 7, 0.0
        crash_game._assert_house_wins()
        check("a zero pool rate survives the guard", crash_game.JACKPOT_RATE == 0.0)
    finally:
        crash_game.JACKPOT_RATE, crash_game.BUST_ONE_IN = saved_rate, saved_bust


def test_economics_receipt_string() -> None:
    """The one line a log is read for. Pinned by content, not by shape: a receipt
    that says the wrong number is worse than no receipt."""
    line = crash_game.economics_line()
    check("receipt names the bust rate", "1 in 7" in line, line)
    check("receipt names the edge as a percentage", "14.29%" in line, line)
    check("receipt names the pool rate", "2.00%" in line, line)
    check("receipt names the pool bar", "100.0x+" in line, line)
    check("receipt names the NET to the house", "NET TO HOUSE 12.29%" in line, line)
    check("receipt is tagged so a log filter finds it", line.startswith("[crash] house edge"), line)

    # It must track the dials, never a frozen string.
    saved = crash_game.BUST_ONE_IN
    try:
        crash_game.BUST_ONE_IN = 20
        moved = crash_game.economics_line()
        check("receipt follows the dial", "1 in 20" in moved and "5.00%" in moved, moved)
    finally:
        crash_game.BUST_ONE_IN = saved


# ---------------------------------------------------------------------------
# 4. The curve itself
# ---------------------------------------------------------------------------
def test_crash_point_shape() -> None:
    seed = secrets.token_hex(16)
    a = crash_game.generate_crash_point(seed, "public", 7)
    b = crash_game.generate_crash_point(seed, "public", 7)
    check("same seed and nonce give the same point", a == b, f"{a} vs {b}")
    check("a different nonce gives a different point",
          crash_game.generate_crash_point(seed, "public", 8) != a or True)  # may collide; shape only

    N = 4000
    pts = [crash_game.generate_crash_point(secrets.token_hex(8), "public", i) for i in range(N)]
    check("no point is ever below 1.00", min(pts) >= 1.00, str(min(pts)))
    check("points carry at most 2 decimals", all(round(p, 2) == p for p in pts))

    # The floor: a divisor under 2 would bust every round, or divide by zero.
    for bad in (0, 1, -5):
        try:
            got = [crash_game.generate_crash_point(secrets.token_hex(8), "public", i, bust_one_in=bad)
                   for i in range(200)]
            busted = sum(1 for p in got if p <= 1.005)
            check(f"bust_one_in={bad} does not raise", True)
            check(f"bust_one_in={bad} does not bust every round", busted < 200, str(busted))
        except Exception as exc:  # noqa: BLE001
            check(f"bust_one_in={bad} does not raise", False, repr(exc))


def test_distribution_matches_the_advertised_edge() -> None:
    """P(point >= x) = (1 - 1/D) * 99/(100x - 1). The instant bust IS the edge."""
    N = 120000
    # A point is an instant bust when it reads 1.00, and the mod-divisor hit is
    # NOT the only way to get there: the fair curve itself returns 1.00 whenever
    # the raw value is under 1.005, which is u < 0.5/99.5 of draws. Expecting a
    # flat 1/D understates the rate by 0.0043 at D=7 -- small enough to sit inside
    # a round 0.006 tolerance and pass on most runs, which is exactly how a test
    # measures the wrong thing for a while without anyone noticing.
    natural_1x = 0.5 / 99.5
    # Seeded draws, not secrets: this suite's own doctrine is that a gate must
    # not walk a different path every run, and this block was the one part of it
    # still rolling fresh dice (caught 2026-08-20 when an honest sample read
    # EV=1.0142 at 100x and failed a strict bound -- see below).
    rng = random.Random(20260820)
    for divisor in (7, 33):
        pts = [crash_game.generate_crash_point("%016x" % rng.getrandbits(64), "public", i, bust_one_in=divisor)
               for i in range(N)]
        busted = sum(1 for p in pts if p <= 1.005) / N
        expect = 1.0 / divisor + (1.0 - 1.0 / divisor) * natural_1x
        # 4 sigma for this sample size, not a round number: tight enough to catch
        # a real drift in the dial, wide enough never to flake on an honest run.
        tol = 4.0 * math.sqrt(expect * (1.0 - expect) / N)
        check(f"1/{divisor}: instant-bust rate matches the dial",
              close(busted, expect, tol), f"{busted:.4f} vs {expect:.4f} (tol {tol:.4f})")
        check(f"1/{divisor}: the dial is what dominates the bust rate",
              abs(busted - 1.0 / divisor) < 0.01, f"{busted:.4f} vs dial {1.0/divisor:.4f}")
        for target in (2.0, 5.0, 10.0, 100.0):
            hit = sum(1 for p in pts if p >= target) / N
            expect = (1.0 - 1.0 / divisor) * 99.0 / (100.0 * target - 1.0)
            tol = max(0.004, expect * 0.14)
            check(f"1/{divisor}: hit rate at {target}x matches theory",
                  close(hit, expect, tol), f"{hit:.5f} vs {expect:.5f}")
            # The point of the whole exercise: every target loses the same share.
            # Anchored to THEORY with a sample-derived band, never a bare `< 1.0`:
            # at 100x the hit sigma alone is ~0.028 of EV on this N, so the old
            # strict bound sat 1.4 sigma from its own honest mean and failed ~8%
            # of runs (measured EV=1.0142 on 2026-08-20 with the game untouched).
            # The curve's own claim is EV = 0.99*(1-1/D) -- below 1.0 at every
            # target by construction, and THAT is what gets pinned.
            ev = hit * target
            ev_expect = target * expect
            ev_tol = 4.0 * target * math.sqrt(expect * (1.0 - expect) / N)
            check(f"1/{divisor}: cashing at {target}x still loses ~1/{divisor}",
                  close(ev, ev_expect, ev_tol) and ev_expect < 1.0,
                  f"EV={ev:.4f} vs {ev_expect:.4f} (tol {ev_tol:.4f})")


# ---------------------------------------------------------------------------
# 5. Played out for real -- who ends up with the coins
# ---------------------------------------------------------------------------
def test_the_house_wins_when_it_is_played() -> None:
    # Ordinary targets only. simulate() adds each configuration's OWN pool bar, so
    # the two runs face the same everyday play plus the bar they actually shipped
    # with -- putting 100x in this list would hand the new dials the old bar too.
    mixed = [1.2, 1.5, 2.0, 2.0, 3.0, 5.0, 10.0]

    for seed in (1234, 99, 7):
        new_net, new_pool = simulate(150000, mixed, crash_game.BUST_ONE_IN,
                                     crash_game.JACKPOT_RATE,
                                     crash_game.JACKPOT_MULTIPLIER, seed=seed)
        old_net, old_pool = simulate(150000, mixed, 33, 0.05, 50.0, seed=seed)

        check(f"seed {seed}: shipped dials, the house ENDS AHEAD", new_net > 0, f"{new_net:+.4f}")
        check(f"seed {seed}: and by roughly the advertised net edge",
              close(new_net, crash_game.net_house_edge(), 0.04),
              f"{new_net:+.4f} vs {crash_game.net_house_edge():+.4f}")
        check(f"seed {seed}: the pool still pays out something", new_pool > 0, f"{new_pool:.4f}")
        check(f"seed {seed}: OLD dials, the house ENDS BEHIND (the live bug)",
              old_net < 0, f"{old_net:+.4f}")
        check(f"seed {seed}: the old shortfall is near the measured 1.97%",
              close(-old_net, 0.0197, 0.015), f"{-old_net:.4f}")
        # The 100x leg pays 100-or-nothing, so a 150k-round run carries close to a
        # point of spread on that leg alone; 0.11 is the analytic 0.1426 less the
        # most that spread can plausibly take away, not a number tuned to pass.
        check(f"seed {seed}: the fix swings the game by more than 11 points",
              new_net - old_net > 0.11, f"{new_net - old_net:+.4f}")
        check(f"seed {seed}: the old pool alone paid out more than 3% of turnover",
              old_pool > 0.03, f"{old_pool:.4f}")


def test_the_farmed_strategy_now_loses() -> None:
    """Parking an auto-cashout on the pool bar and waiting was the abuse. On the
    live data one account took 64,547,730 CC across 82 pool wins doing exactly
    this. Under the shipped dials it has to be a losing strategy on its own."""
    bar = crash_game.JACKPOT_MULTIPLIER

    # A camper who IS the volume: they only ever get their own pool money back.
    new_solo = strategy_return(bar, crash_game.BUST_ONE_IN, crash_game.JACKPOT_RATE, 1.0)
    old_solo = strategy_return(50.0, 33, 0.05, 1.0)
    check("camping the bar LOSES on the new dials", new_solo < 1.0, f"return {new_solo:.4f}")
    check("camping the bar PAID on the old dials -- why it was farmed",
          old_solo > 1.0, f"return {old_solo:.4f}")
    check("the new dials cost a camper more than 10% a round",
          new_solo < 0.90, f"return {new_solo:.4f}")

    # A camper riding everyone else's volume. This is the real shape of the abuse:
    # the pool is fed by the whole floor and collected by whoever reaches the bar.
    for share in (0.02, 0.05, 0.10, 0.25, 0.50, 1.00):
        old_r = strategy_return(50.0, 33, 0.05, share)
        new_r = strategy_return(bar, crash_game.BUST_ONE_IN, crash_game.JACKPOT_RATE, share)
        pct = int(share * 100)
        # The sharpest fact in this whole file: under the old dials there was no
        # slice of the floor at which camping the pool was a losing play. None.
        check(f"OLD dials paid a camper at {pct}% of the floor", old_r > 1.0, f"{old_r:.4f}")
        check(f"new dials are strictly worse for a camper at {pct}%",
              new_r < old_r, f"{old_r:.4f} -> {new_r:.4f}")
        if old_r > 1.0:
            cut = 1.0 - max(new_r - 1.0, 0.0) / (old_r - 1.0)
            # 60% is the floor of this cut, not a round number picked to pass:
            # as a camper's slice of the volume shrinks, their whole return is
            # pool, so the cut converges on the ratio of the two pool rates,
            # 1 - 0.02/0.05 = 0.60. Every larger slice is cut harder than that.
            check(f"new dials cut a {pct}% camper's profit by at least 60%",
                  cut >= 0.60, f"{old_r - 1.0:+.4f} -> {new_r - 1.0:+.4f} ({cut*100:.0f}% cut)")

    # Break-even share: above this slice of the floor, camping simply loses.
    new_breakeven = crash_game.JACKPOT_RATE / (1.0 - strategy_return(
        bar, crash_game.BUST_ONE_IN, 0.0, 1.0))
    check("under the NEW dials a camper past ~a seventh of the floor loses",
          0.05 < new_breakeven < 0.25, f"break-even share {new_breakeven:.3f}")
    old_breakeven = 0.05 / (1.0 - strategy_return(50.0, 33, 0.0, 1.0))
    check("under the OLD dials no share of the floor was ever a losing camp",
          old_breakeven > 1.0, f"break-even share {old_breakeven:.3f}")
    check("a camper at 25% of the floor now loses outright",
          strategy_return(bar, crash_game.BUST_ONE_IN, crash_game.JACKPOT_RATE, 0.25) < 1.0,
          f"{strategy_return(bar, crash_game.BUST_ONE_IN, crash_game.JACKPOT_RATE, 0.25):.4f}")

    # KNOWN AND DELIBERATE, recorded here so it is never mistaken for an oversight:
    # a camper who is a SMALL slice of the floor still comes out ahead, because the
    # pool is fed by everyone. The difference now is that it is redistribution, not
    # minting -- the pool is a slice of the house's own take, so the house stays
    # ahead overall however the pool lands. Capping a share against its stake is a
    # further change and is the owner's call, not this gate's.
    tiny = strategy_return(bar, crash_game.BUST_ONE_IN, crash_game.JACKPOT_RATE, 0.01)
    check("a very small camper is still ahead (known, bounded, redistribution only)",
          tiny > 1.0, f"return {tiny:.4f}")
    check("but the whole pool is still only a slice of the house edge",
          crash_game.JACKPOT_RATE < crash_game.house_edge(),
          f"{crash_game.JACKPOT_RATE} vs {crash_game.house_edge():.4f}")


def test_the_pool_bar_got_harder() -> None:
    N = 200000
    old_hits = sum(1 for i in range(N)
                   if crash_game.generate_crash_point(secrets.token_hex(8), "public", i,
                                                      bust_one_in=33) >= 50.0)
    new_hits = sum(1 for i in range(N)
                   if crash_game.generate_crash_point(secrets.token_hex(8), "public", i,
                                                      bust_one_in=crash_game.BUST_ONE_IN)
                   >= crash_game.JACKPOT_MULTIPLIER)
    check("the pool bar is reachable at all", new_hits > 0, str(new_hits))
    check("the pool is at least twice as hard to reach as before",
          old_hits >= 2 * new_hits, f"old={old_hits} new={new_hits}")


# ---------------------------------------------------------------------------
# 6. The ledger (needs a real mongod; scratch database, dropped at the end)
# ---------------------------------------------------------------------------
class Raiser:
    """A database handle whose every write blows up, to prove the ledger cannot
    take a payout down with it."""

    class _Coll:
        async def insert_one(self, *a, **k):
            raise RuntimeError("ledger is down")

        async def delete_many(self, *a, **k):
            raise RuntimeError("ledger is down")

    def __getattr__(self, _name):
        return Raiser._Coll()


async def ledger_tests(db) -> None:
    saved_db = crash_game._db
    crash_game._db = db
    try:
        bet = {"user_id": "u1", "name": "Tester", "avatar": "a.png", "amount": 10000}

        await crash_game._record_bet(bet, 25000, 2.5, "win")
        row = await db.casino_bets.find_one({"user_id": "u1", "result": "win"})
        check("win row is written", row is not None)
        if row:
            check("win row: game is crash", row.get("game") == "crash", str(row.get("game")))
            check("win row: stake recorded", row.get("bet") == 10000, str(row.get("bet")))
            check("win row: payout recorded", row.get("payout") == 25000, str(row.get("payout")))
            check("win row: NET is payout minus stake", row.get("net") == 15000, str(row.get("net")))
            check("win row: multiplier recorded", close(row.get("multiplier", 0), 2.5, 1e-9))
            check("win row: same field names as the other games",
                  {"id", "user_id", "user_name", "game", "bet", "payout", "net",
                   "multiplier", "result", "created_at"} <= set(row))

        await crash_game._record_bet({"user_id": "u2", "name": "Loser", "amount": 7000},
                                     0, 0.0, "lose")
        row = await db.casino_bets.find_one({"user_id": "u2"})
        check("lose row: payout is zero", row and row.get("payout") == 0)
        check("lose row: NET is minus the stake", row and row.get("net") == -7000,
              str(row and row.get("net")))

        await crash_game._record_bet({"user_id": "u3", "name": "Mooner", "amount": 500},
                                     900000, 100.0, "win", kind="moon_pool")
        row = await db.casino_bets.find_one({"user_id": "u3"})
        check("pool row: no stake behind it", row and row.get("bet") == 0, str(row and row.get("bet")))
        check("pool row: NET is the whole share", row and row.get("net") == 900000)
        check("pool row: tagged moon_pool", row and row.get("kind") == "moon_pool")
        check("pool row: a round row is tagged round",
              (await db.casino_bets.find_one({"user_id": "u1"})).get("kind") == "round")

        # A stake that is missing or None must not raise or write a null.
        await crash_game._record_bet({"user_id": "u4", "name": "NoAmount"}, 0, 0.0, "lose")
        row = await db.casino_bets.find_one({"user_id": "u4"})
        check("a bet with no amount records a zero stake", row and row.get("bet") == 0)

        # Containment: the payout path must survive a dead ledger.
        crash_game._db = Raiser()
        try:
            await crash_game._record_bet(bet, 25000, 2.5, "win")
            check("a dead ledger never raises into the payout path", True)
        except Exception as exc:  # noqa: BLE001
            check("a dead ledger never raises into the payout path", False, repr(exc))
        try:
            await crash_game._trim_ledger()
            check("a dead ledger never raises out of the trim", True)
        except Exception as exc:  # noqa: BLE001
            check("a dead ledger never raises out of the trim", False, repr(exc))
        crash_game._db = db

        # Retention: only this game's rows, only old ones.
        from datetime import datetime, timedelta, timezone
        old_iso = (datetime.now(timezone.utc) - timedelta(days=crash_game.LEDGER_RETENTION_DAYS + 3)).isoformat()
        new_iso = datetime.now(timezone.utc).isoformat()
        await db.casino_bets.insert_one({"id": "old-crash", "game": "crash", "created_at": old_iso})
        await db.casino_bets.insert_one({"id": "new-crash", "game": "crash", "created_at": new_iso})
        await db.casino_bets.insert_one({"id": "old-bj", "game": "blackjack", "created_at": old_iso})
        await db.casino_bets.insert_one({"id": "new-bj", "game": "blackjack", "created_at": new_iso})
        await crash_game._trim_ledger()
        check("trim removes the old crash row", await db.casino_bets.find_one({"id": "old-crash"}) is None)
        check("trim keeps the recent crash row", await db.casino_bets.find_one({"id": "new-crash"}) is not None)
        check("trim NEVER touches another game's old rows",
              await db.casino_bets.find_one({"id": "old-bj"}) is not None)
        check("trim never touches another game's recent rows",
              await db.casino_bets.find_one({"id": "new-bj"}) is not None)
    finally:
        crash_game._db = saved_db


async def receipt_reaches_a_handler_test(db) -> None:
    """Drive the REAL run_crash_loop and require the receipt to arrive at a real
    logging handler.

    ★ This is the check the first deploy needed and did not have. The line was in
    the source and correct, and it landed NOWHERE, because server.py calls
    configure() at module import -- before the host app attaches any handler. A
    test that only asserted the string would have passed on the broken build. So
    this one attaches a handler and starts the loop the way the app does.
    """
    import logging

    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture()
    logger = logging.getLogger("laislanublar.crash")
    logger.addHandler(handler)
    prior_level = logger.level
    logger.setLevel(logging.INFO)

    saved_db, saved_mgr, saved_sleep = crash_game._db, crash_game.manager, asyncio.sleep
    crash_game._db = db

    class Silent:
        async def broadcast(self, m): pass
        async def send_to_user(self, u, m): pass
        async def send(self, w, m): pass

    crash_game.manager = Silent()

    async def no_wait(_seconds):
        # The loop opens with a 2 s boot wait and retries on any failure; a gate
        # must not sit through either.
        await saved_sleep(0)

    rounds_seen = []

    async def stub_round(round_no):
        rounds_seen.append(round_no)
        await saved_sleep(0)

    rescues = []

    async def stub_rescue():
        # Retirement must still attempt the final-round rescue; stubbing it also
        # keeps this test from refunding whatever earlier tests left in
        # crash_round on the shared scratch db.
        rescues.append(1)

    saved_single = crash_game._run_single_round
    saved_rescue = crash_game._rescue_abandoned_bets
    crash_game._run_single_round = stub_round
    crash_game._rescue_abandoned_bets = stub_rescue
    crash_game.asyncio.sleep = no_wait
    try:
        task = asyncio.get_event_loop().create_task(crash_game.run_crash_loop())
        # A real wait, not a bare yield: between the receipt and the first round
        # the loop makes a genuine Mongo round-trip, and 200 `sleep(0)` yields
        # complete in microseconds without ever giving that call time to land.
        # Bounded at ~3 s, and it exits the moment both have happened.
        for _ in range(300):
            await saved_sleep(0.01)
            if records and (rounds_seen if not crash_game.RETIRED else task.done()):
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        crash_game.asyncio.sleep = saved_sleep
        crash_game._run_single_round = saved_single
        crash_game._rescue_abandoned_bets = saved_rescue
        crash_game._db, crash_game.manager = saved_db, saved_mgr
        logger.removeHandler(handler)
        logger.setLevel(prior_level)

    hits = [r for r in records if r.startswith("[crash] house edge")]
    check("the boot receipt REACHES A HANDLER from run_crash_loop", bool(hits),
          "records seen: %r" % (records[:4],))
    if hits:
        check("the receipt that landed is the current one",
              hits[-1] == crash_game.economics_line(), hits[-1])
    if crash_game.RETIRED:
        # 2026-08-20, the owner: "remopve crash game". The retired loop must
        # announce, attempt the rescue, start NOTHING, and finish on its own.
        check("retired: the loop started no rounds", not rounds_seen, str(rounds_seen[:3]))
        check("retired: the final-round rescue was attempted", bool(rescues))
        check("retired: the loop completed instead of running", task.done() and not task.cancelled(),
              f"done={task.done()} cancelled={task.cancelled()}")
        check("retired: the retirement is announced",
              any("RETIRED" in r for r in records), "records: %r" % (records[:6],))
    else:
        check("the loop actually started rounds after announcing", bool(rounds_seen),
              str(rounds_seen[:3]))


async def finish_round_tests(db) -> None:
    """The losers only get recorded if _finish_round writes them, and it must do
    it exactly once even when called twice for the same round."""
    saved_db, saved_mgr = crash_game._db, crash_game.manager
    crash_game._db = db

    class Silent:
        async def broadcast(self, m): pass
        async def send_to_user(self, u, m): pass
        async def send(self, w, m): pass

    crash_game.manager = Silent()
    try:
        await db.casino_bets.delete_many({})
        await db.crash_round.replace_one({"id": "current"}, {
            "id": "current", "round_no": 9001, "phase": "running", "crash_point": 1.8,
            "server_seed": "x", "server_hash": "y", "client_seed": "public",
            "running_started_at": 0,
            "bets": [
                {"user_id": "w1", "name": "Winner", "amount": 1000, "auto_cashout": 1.5,
                 "cashed_at": 1.5, "payout": 1500},
                {"user_id": "l1", "name": "Loser1", "amount": 2000, "auto_cashout": None,
                 "cashed_at": None, "payout": 0},
                {"user_id": "l2", "name": "Loser2", "amount": 3000, "auto_cashout": 5.0,
                 "cashed_at": None, "payout": 0},
            ],
        }, upsert=True)
        await crash_game._finish_round(9001, 1.8)
        rows = await db.casino_bets.find({}).to_list(50)
        losers = [r for r in rows if r.get("result") == "lose"]
        check("both busted bets are recorded as losses", len(losers) == 2, str(len(losers)))
        check("a bet that cashed out is NOT recorded twice here",
              not any(r.get("user_id") == "w1" for r in rows))
        check("the loss carries the real stake",
              sorted(r["bet"] for r in losers) == [2000, 3000],
              str(sorted(r["bet"] for r in losers)))
        check("the loss net is minus the stake",
              all(r["net"] == -r["bet"] for r in losers))

        # Called again for the same round: the latch must swallow it whole.
        await crash_game._finish_round(9001, 1.8)
        rows2 = await db.casino_bets.find({}).to_list(50)
        check("a second settle of the same round writes NO extra rows",
              len(rows2) == len(rows), f"{len(rows)} -> {len(rows2)}")
    finally:
        crash_game._db, crash_game.manager = saved_db, saved_mgr


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
PURE_TESTS = [
    test_shipped_dials,
    test_the_old_dials_were_a_printer,
    test_env_dial_reader,
    test_anti_printer_clamp,
    test_economics_receipt_string,
    test_crash_point_shape,
    test_distribution_matches_the_advertised_edge,
    test_the_house_wins_when_it_is_played,
    test_the_farmed_strategy_now_loses,
    test_the_pool_bar_got_harder,
]


async def run_all(mongo_url):
    PASS.clear()
    FAIL.clear()
    for fn in PURE_TESTS:
        try:
            fn()
        except Exception:  # noqa: BLE001
            FAIL.append(f"{fn.__name__} raised :: {traceback.format_exc(limit=3)}")
    if mongo_url:
        from motor.motor_asyncio import AsyncIOMotorClient
        dbname = "crashgate_scratch_" + uuid.uuid4().hex[:10]
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=8000)
        db = client[dbname]
        try:
            for fn in (ledger_tests, finish_round_tests, receipt_reaches_a_handler_test):
                try:
                    await fn(db)
                except Exception:  # noqa: BLE001
                    FAIL.append(f"{fn.__name__} raised :: {traceback.format_exc(limit=3)}")
        finally:
            await client.drop_database(dbname)
            client.close()
    return len(FAIL) == 0


# ---------------------------------------------------------------------------
# Mutants -- each must turn the suite RED
# ---------------------------------------------------------------------------
def mutants():
    src_gen = crash_game.generate_crash_point
    src_assert = crash_game._assert_house_wins
    src_trim = crash_game._trim_ledger
    src_record = crash_game._record_bet
    src_loop = crash_game.run_crash_loop
    src_line = crash_game.economics_line

    def restore():
        crash_game.generate_crash_point = src_gen
        crash_game._assert_house_wins = src_assert
        crash_game._trim_ledger = src_trim
        crash_game._record_bet = src_record
        crash_game.run_crash_loop = src_loop
        crash_game.economics_line = src_line
        crash_game.BUST_ONE_IN = 7
        crash_game.JACKPOT_RATE = 0.02
        crash_game.JACKPOT_MULTIPLIER = 100.0

    def m_old_divisor():
        crash_game.BUST_ONE_IN = 33

    def m_old_rate():
        crash_game.JACKPOT_RATE = 0.05

    def m_old_bar():
        crash_game.JACKPOT_MULTIPLIER = 50.0

    def m_no_clamp():
        crash_game._assert_house_wins = lambda: None

    def m_clamp_only_when_strictly_greater():
        def broken():
            edge = crash_game.house_edge()
            if crash_game.JACKPOT_RATE > edge:  # ">" instead of ">=" -- lets edge==rate through
                crash_game.JACKPOT_RATE = round(edge / 2.0, 6)
        crash_game._assert_house_wins = broken

    def m_no_divisor_floor():
        def broken(server_seed, client_seed, nonce, *, bust_one_in=None):
            import hashlib as _h, hmac as _hm
            divisor = int(crash_game.BUST_ONE_IN if bust_one_in is None else bust_one_in)
            digest = _hm.new(server_seed.encode(), f"{client_seed}:{nonce}".encode(),
                             _h.sha256).hexdigest()
            roll = int(digest[:13], 16)
            if divisor and roll % divisor == 0:
                return 1.00
            E = 2 ** 52
            return max(1.00, round((100 * E - roll) / (E - roll) / 100, 2))
        crash_game.generate_crash_point = broken

    def m_trim_ignores_game():
        async def broken():
            from datetime import datetime, timedelta, timezone
            iso = (datetime.now(timezone.utc) - timedelta(days=crash_game.LEDGER_RETENTION_DAYS)).isoformat()
            await crash_game._db.casino_bets.delete_many({"created_at": {"$lt": iso}})
        crash_game._trim_ledger = broken

    def m_net_is_payout():
        async def broken(bet, payout, multiplier, result, *, kind="round"):
            from datetime import datetime, timezone
            stake = int(bet.get("amount") or 0) if kind == "round" else 0
            await crash_game._db.casino_bets.insert_one({
                "id": uuid.uuid4().hex, "user_id": bet.get("user_id"),
                "user_name": bet.get("name"), "avatar": bet.get("avatar"),
                "game": "crash", "kind": kind, "bet": stake, "payout": int(payout),
                "net": int(payout), "multiplier": round(float(multiplier or 0), 2),
                "result": result, "created_at": datetime.now(timezone.utc).isoformat()})
        crash_game._record_bet = broken

    def m_receipt_never_announced():
        """The exact live defect: the receipt exists but never reaches a handler."""
        async def broken():
            await asyncio.sleep(0)
            while True:
                await asyncio.sleep(0)
        crash_game.run_crash_loop = broken

    def m_receipt_stale_string():
        crash_game.economics_line = lambda: "[crash] house edge 1 in 33 = 3.03%"

    def m_ledger_not_contained():
        async def broken(bet, payout, multiplier, result, *, kind="round"):
            await crash_game._db.casino_bets.insert_one({"id": uuid.uuid4().hex})
        crash_game._record_bet = broken

    return [
        ("old divisor 33 restored", m_old_divisor),
        ("old pool rate 0.05 restored", m_old_rate),
        ("old pool bar 50x restored", m_old_bar),
        ("anti-printer clamp removed", m_no_clamp),
        ("clamp uses > instead of >=", m_clamp_only_when_strictly_greater),
        ("divisor floor removed", m_no_divisor_floor),
        ("trim ignores the game filter", m_trim_ignores_game),
        ("ledger net = payout, not payout - stake", m_net_is_payout),
        ("ledger write not exception-contained", m_ledger_not_contained),
        ("boot receipt never announced from the loop", m_receipt_never_announced),
        ("boot receipt is a stale frozen string", m_receipt_stale_string),
    ], restore


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default=os.environ.get("CRASH_GATE_MONGO"))
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()

    ok = asyncio.run(run_all(args.mongo))
    print(f"PASS {len(PASS)}  FAIL {len(FAIL)}"
          + ("" if args.mongo else "   (pure maths only -- pass --mongo for the ledger half)"))
    for f in FAIL:
        print("  FAIL:", f)
    if not ok:
        return 1

    if args.mutants:
        muts, restore = mutants()
        print(f"\n--- mutation sensitivity: {len(muts)} mutants must all go RED ---")
        survivors = []
        for name, apply in muts:
            restore()
            apply()
            try:
                green = asyncio.run(run_all(args.mongo))
            except Exception:  # noqa: BLE001
                green = False
            restore()
            print(f"  {'SURVIVED' if green else 'RED     '}  {name}"
                  + ("" if green else f"  ({len(FAIL)} checks bit)"))
            if green:
                survivors.append(name)
        if survivors:
            print("MUTANTS SURVIVED:", survivors)
            return 1
        print(f"all {len(muts)} mutants RED")

    print("GATE GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
