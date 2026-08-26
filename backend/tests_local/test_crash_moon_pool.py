"""Moon Pool gate for crash_game.py -- run directly, no pytest plugins needed.

    <venv>\\python.exe tests_local\\test_crash_moon_pool.py --mongo mongodb://127.0.0.1:PORT
    <venv>\\python.exe tests_local\\test_crash_moon_pool.py --mongo ... --mutants

Everything below drives the REAL crash_game functions against a REAL mongod
through the REAL motor driver -- no hand-rolled Mongo double, because the whole
point of the payout lane is its atomic `$inc` / `$set` / positional-update
semantics and a double that got those subtly wrong would go green on code that
loses coins in production.

`--mutants` re-runs the suite against deliberately broken copies of the module's
logic and requires every one of them to turn the suite RED, so a green run means
the checks actually bite rather than merely passing.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crash_game  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name if condition else f"{name} :: {detail}")


# ---------------------------------------------------------------------------
# Recorder standing in for ConnectionManager. It implements the FULL surface the
# module calls on `manager`; anything the module gains later that this lacks
# raises AttributeError loudly instead of passing silently.
# ---------------------------------------------------------------------------
class Recorder:
    def __init__(self) -> None:
        self.broadcasts: list[dict] = []
        self.to_user: list[tuple[str, dict]] = []
        self.direct: list[dict] = []

    async def broadcast(self, message: dict) -> None:
        self.broadcasts.append(message)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        self.to_user.append((user_id, message))

    async def send(self, websocket, message: dict) -> None:
        self.direct.append(message)

    def register(self, websocket, user_id: str) -> None:
        pass

    def unregister(self, websocket) -> None:
        pass


def assert_recorder_matches_manager() -> None:
    """Precondition: the stand-in must cover every public method of the real
    ConnectionManager, or a contract drift would make this suite meaningless."""
    real = {n for n in dir(crash_game.ConnectionManager) if not n.startswith("_")}
    mine = {n for n in dir(Recorder) if not n.startswith("_")}
    check("precondition: recorder covers ConnectionManager surface", real <= mine,
          f"missing {sorted(real - mine)}")


# ---------------------------------------------------------------------------
# Pure math -- no DB
# ---------------------------------------------------------------------------
def test_config() -> None:
    """The tuned numbers, pinned. Every other check reads the threshold off the
    module so the LOGIC is verified whatever it is set to -- which means without
    this the owner's actual number would be the one thing nothing asserts."""
    # 2026-08-19, owner's call: the bar moved 50x -> 100x and the pool rate
    # 5% -> 2%. The rate had to move because nothing is ever deducted to fund the
    # pool -- at 5% against a 1/33 edge the game MINTED 1.97% of everything
    # wagered. See test_crash_house_edge.py for the whole story and the guard.
    check("threshold is the owner's 100x", crash_game.JACKPOT_MULTIPLIER == 100.0,
          str(crash_game.JACKPOT_MULTIPLIER))
    check("2% of every bet still feeds the pool", crash_game.JACKPOT_RATE == 0.02,
          str(crash_game.JACKPOT_RATE))
    check("the pool rate stays UNDER the house edge", crash_game.net_house_edge() > 0,
          f"net={crash_game.net_house_edge():.4f}")
    check("a pool under one whole coin rolls over", crash_game.JACKPOT_MIN_PAYOUT == 1,
          str(crash_game.JACKPOT_MIN_PAYOUT))


def test_qualifies() -> None:
    m = crash_game.JACKPOT_MULTIPLIER
    check("busted rider (cashed_at None) never qualifies",
          not crash_game.qualifies_for_jackpot({"amount": 999999, "cashed_at": None}))
    check("cashed_at 0 does not qualify",
          not crash_game.qualifies_for_jackpot({"amount": 1000, "cashed_at": 0}))
    check("just under the threshold loses",
          not crash_game.qualifies_for_jackpot({"amount": 1000, "cashed_at": m - 0.01}))
    check("exactly the threshold wins",
          crash_game.qualifies_for_jackpot({"amount": 1000, "cashed_at": m}))
    check("above the threshold wins",
          crash_game.qualifies_for_jackpot({"amount": 1000, "cashed_at": m + 118.14}))
    check("a bet with no cashed_at key at all loses",
          not crash_game.qualifies_for_jackpot({"amount": 1000}))


def test_split() -> None:
    sj = crash_game.split_jackpot
    check("one winner takes the whole pool",
          sj(15_185_195, [{"amount": 10_000}]) == [15_185_195])
    check("two equal stakes split evenly",
          sj(1_000_000, [{"amount": 5000}, {"amount": 5000}]) == [500_000, 500_000])
    check("stakes 1:3 split 25/75",
          sj(1_000_000, [{"amount": 100_000}, {"amount": 300_000}]) == [250_000, 750_000])
    check("empty pool pays nothing", sj(0, [{"amount": 100}]) == [0])
    check("negative pool pays nothing", sj(-5, [{"amount": 100}]) == [0])
    check("no winners returns an empty split", sj(1000, []) == [])
    check("all-zero stakes pay nothing (cannot happen: MIN_BET>0)",
          sj(1000, [{"amount": 0}, {"amount": 0}]) == [0, 0])
    check("a missing amount is treated as zero, not a crash",
          sj(1000, [{"amount": 1000}, {}]) == [1000, 0])
    # The remainder rule, stated exactly: 100 over stakes 1/1/1 is 33/33/34 with
    # the extra going to the largest stake -- here a tie, so the first of them.
    check("rounding remainder lands on the largest stake",
          sj(100, [{"amount": 10}, {"amount": 30}, {"amount": 10}]) == [20, 60, 20])
    check("indivisible remainder is not dropped",
          sum(sj(100, [{"amount": 3}, {"amount": 3}, {"amount": 3}])) == 100)

    rng = random.Random(20260728)
    exact = True
    never_negative = True
    for _ in range(500):
        pool = rng.randint(1, 50_000_000)
        winners = [{"amount": rng.randint(crash_game.MIN_BET, crash_game.MAX_BET)}
                   for _ in range(rng.randint(1, 8))]
        shares = sj(pool, winners)
        exact = exact and sum(shares) == pool
        never_negative = never_negative and all(s >= 0 for s in shares)
    check("500 random splits sum to EXACTLY the pool", exact)
    check("500 random splits never produce a negative share", never_negative)


# ---------------------------------------------------------------------------
# Live-DB lane
# ---------------------------------------------------------------------------
async def fresh_db(mongo_url: str):
    import motor.motor_asyncio as ma
    client = ma.AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=8000)
    await client.admin.command("ping")           # precondition: mongod is really there
    name = "crashgate_%d" % random.randint(10**6, 10**7)
    await client.drop_database(name)
    return client, client[name], name


async def seed(db, *, jackpot: float, bets: list[dict], round_no: int = 1) -> None:
    await db.crash_meta.delete_many({})
    await db.crash_round.delete_many({})
    await db.crash_history.delete_many({})
    await db.crash_jackpot_wins.delete_many({})
    await db.users.delete_many({})
    await db.crash_meta.insert_one({"id": "meta", "jackpot": jackpot})
    for bet in bets:
        await db.users.insert_one({"id": bet["user_id"], "persona_name": bet.get("name"), "coins": 0})
    await db.crash_round.insert_one({
        "id": "current", "round_no": round_no, "phase": "running", "server_seed": "s",
        "server_hash": "h", "client_seed": "public", "crash_point": 168.14, "bets": bets,
        "betting_ends_at": 0, "running_started_at": 0,
    })


def bet(uid: str, amount: int, cashed_at, name: str | None = None) -> dict:
    return {"user_id": uid, "name": name or uid, "avatar": None, "amount": amount,
            "auto_cashout": cashed_at, "cashed_at": cashed_at,
            "payout": int(amount * (cashed_at or 0))}


async def coins(db, uid: str) -> int:
    row = await db.users.find_one({"id": uid})
    return int((row or {}).get("coins", 0))


async def pool(db) -> float:
    meta = await db.crash_meta.find_one({"id": "meta"})
    return float((meta or {}).get("jackpot", 0.0))


async def run_db_tests(db) -> None:
    rec = Recorder()
    crash_game.manager = rec
    M = crash_game.JACKPOT_MULTIPLIER

    # -- 1. THE BUG THIS WAVE FIXES: a qualifying cashout is actually paid -----
    await seed(db, jackpot=15_185_195.0, bets=[bet("u1", 10_000, M + 5)])
    rec.broadcasts.clear(); rec.to_user.clear()
    await crash_game._finish_round(1, 168.14)
    check("winner at the threshold is credited the whole pool",
          await coins(db, "u1") == 15_185_195, f"got {await coins(db, 'u1')}")
    check("pool is emptied after it is won", await pool(db) == 0.0, f"got {await pool(db)}")
    check("winner gets a private jackpot message with their share and balance",
          any(m.get("type") == "jackpot" and m.get("won") == 15_185_195
              and m.get("coins") == 15_185_195 for _, m in rec.to_user))
    check("the room is told who won",
          any(m.get("type") == "jackpot" and m.get("won_total") == 15_185_195
              and [w["name"] for w in m.get("winners", [])] == ["u1"] for m in rec.broadcasts))
    meta = await db.crash_meta.find_one({"id": "meta"})
    check("last_win is persisted for the pool card",
          (meta.get("last_win") or {}).get("amount") == 15_185_195)
    check("the win is written to its own audit collection",
          await db.crash_jackpot_wins.count_documents({"round_no": 1}) == 1)

    # -- 2. Rollover: nobody qualified, the pool must not move ----------------
    await seed(db, jackpot=777_000.0, bets=[bet("u1", 10_000, M - 0.01), bet("u2", 500_000, None)])
    rec.broadcasts.clear(); rec.to_user.clear()
    await crash_game._finish_round(1, M - 0.01)
    check("pool rolls over untouched when nobody reaches the threshold",
          await pool(db) == 777_000.0, f"got {await pool(db)}")
    check("no coins are handed out on a rollover round",
          await coins(db, "u1") == 0 and await coins(db, "u2") == 0)
    check("no jackpot message on a rollover round",
          not any(m.get("type") == "jackpot" for m in rec.broadcasts + [m for _, m in rec.to_user]))

    # -- 3. Two winners split by stake; a third who busted gets nothing --------
    await seed(db, jackpot=1_000_000.0, bets=[
        bet("small", 100_000, M), bet("big", 300_000, M + 60), bet("busted", 900_000, None)])
    await crash_game._finish_round(1, 168.14)
    check("smaller stake takes its proportional quarter", await coins(db, "small") == 250_000,
          f"got {await coins(db, 'small')}")
    check("larger stake takes its proportional three quarters", await coins(db, "big") == 750_000,
          f"got {await coins(db, 'big')}")
    check("the player who busted gets no share", await coins(db, "busted") == 0)
    check("the split hands out the pool exactly, no more no less",
          await coins(db, "small") + await coins(db, "big") == 1_000_000)

    # -- 4. Sub-coin dust stays in the pool instead of being rounded away -----
    await seed(db, jackpot=100.7, bets=[bet("u1", 10_000, M)])
    await crash_game._finish_round(1, 168.14)
    check("whole coins are paid, dust is kept", await coins(db, "u1") == 100)
    check("the sub-coin remainder is returned to the pool",
          abs(await pool(db) - 0.7) < 1e-9, f"got {await pool(db)}")

    # -- 5. A pool too small to pay rolls over rather than paying zero --------
    await seed(db, jackpot=0.4, bets=[bet("u1", 10_000, M)])
    await crash_game._finish_round(1, 168.14)
    check("a sub-coin pool pays nothing", await coins(db, "u1") == 0)
    check("a sub-coin pool is left intact", abs(await pool(db) - 0.4) < 1e-9,
          f"got {await pool(db)}")

    # -- 6. Latch: settling the same round twice must not pay twice -----------
    await seed(db, jackpot=500_000.0, bets=[bet("u1", 10_000, M)])
    await crash_game._finish_round(1, 168.14)
    first = await coins(db, "u1")
    await db.crash_meta.update_one({"id": "meta"}, {"$set": {"jackpot": 500_000.0}})
    await crash_game._finish_round(1, 168.14)   # replay of the SAME round
    check("a replayed round does not pay the pool a second time",
          await coins(db, "u1") == first == 500_000, f"got {await coins(db, 'u1')}")
    check("a replayed round leaves the refilled pool alone",
          await pool(db) == 500_000.0, f"got {await pool(db)}")
    check("a replayed round does not append a second history row",
          await db.crash_history.count_documents({"round_no": 1}) == 1)

    # -- 7. A share that cannot be delivered goes back to the pool ------------
    await seed(db, jackpot=800_000.0, bets=[bet("gone", 10_000, M), bet("here", 10_000, M)])
    await db.users.delete_one({"id": "gone"})       # account vanished mid-round
    await crash_game._finish_round(1, 168.14)
    check("the reachable winner is still paid their share", await coins(db, "here") == 400_000,
          f"got {await coins(db, 'here')}")
    check("the undeliverable share returns to the pool, not the house",
          await pool(db) == 400_000.0, f"got {await pool(db)}")

    # -- 8. Atomic claim contract --------------------------------------------
    await db.crash_meta.update_one({"id": "meta"}, {"$set": {"jackpot": 123.5}}, upsert=True)
    claimed = await crash_game._claim_jackpot()
    check("_claim_jackpot returns the value it took", claimed == 123.5, f"got {claimed}")
    check("_claim_jackpot leaves the pool at zero", await pool(db) == 0.0)

    # -- 9. A missing user row is a reported failure, never a silent zero -----
    await db.users.delete_many({})
    check("_add_coins returns None when there is no row to credit",
          await crash_game._add_coins("nobody", 100) is None)

    # -- 10. The pool number is re-broadcast once per round -------------------
    await db.crash_meta.update_one({"id": "meta"}, {"$set": {"jackpot": 4242.0}}, upsert=True)
    rec.broadcasts.clear()
    await crash_game._start_betting_phase(99)
    check("phase_betting carries the authoritative pool for re-sync",
          any(m.get("type") == "phase_betting" and m.get("jackpot") == 4242.0
              for m in rec.broadcasts))


# ---------------------------------------------------------------------------
# Mutants -- each must turn the suite RED
# ---------------------------------------------------------------------------
def mutant_no_settlement():
    async def noop(round_no, round_doc):
        return None
    return "settlement removed (reproduces the live bug)", {"_settle_jackpot": noop}


def mutant_strict_threshold():
    def q(b):
        c = b.get("cashed_at")
        return c is not None and float(c) > crash_game.JACKPOT_MULTIPLIER
    return "threshold uses > instead of >=", {"qualifies_for_jackpot": q}


def mutant_busted_wins():
    def q(b):
        target = b.get("auto_cashout")
        return target is not None and float(target) >= crash_game.JACKPOT_MULTIPLIER
    return "qualifies on the auto-cashout target instead of the real cashout", {"qualifies_for_jackpot": q}


def mutant_equal_shares():
    def s(p, w):
        if p <= 0 or not w:
            return [0] * len(w)
        each = p // len(w)
        out = [each] * len(w)
        out[0] += p - sum(out)
        return out
    return "pool split evenly instead of by stake", {"split_jackpot": s}


def mutant_drop_remainder():
    def s(p, w):
        if p <= 0 or not w:
            return [0] * len(w)
        total = sum(int(x.get("amount") or 0) for x in w) or 1
        return [p * int(x.get("amount") or 0) // total for x in w]
    return "rounding remainder silently dropped", {"split_jackpot": s}


def mutant_threshold_ten():
    return "threshold left at the old 10x", {"JACKPOT_MULTIPLIER": 10.0}


MUTANTS = [mutant_no_settlement, mutant_strict_threshold, mutant_busted_wins,
           mutant_equal_shares, mutant_drop_remainder, mutant_threshold_ten]


# ---------------------------------------------------------------------------
async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", required=True)
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()

    real_manager = crash_game.manager
    client, db, name = await fresh_db(args.mongo)
    crash_game.configure(db, "gatesecret")

    # Preconditions: assert the world this suite believes in, so a dead fixture
    # or a drifted constant reads as a setup failure rather than a code failure.
    check("precondition: module under test is the repo copy",
          crash_game.__file__.replace("\\", "/").endswith("web/backend/crash_game.py"),
          crash_game.__file__)
    assert_recorder_matches_manager()

    try:
        test_config()
        test_qualifies()
        test_split()
        await run_db_tests(db)
    finally:
        crash_game.manager = real_manager

    ok = not FAIL
    print(f"\nGATE {len(PASS)}/{len(PASS) + len(FAIL)}")
    for f in FAIL:
        print("  RED  " + f)

    if args.mutants:
        print("\nMUTATION SENSITIVITY")
        all_red = True
        for factory in MUTANTS:
            label, patches = factory()
            saved = {k: getattr(crash_game, k) for k in patches}
            PASS.clear(); FAIL.clear()
            for k, v in patches.items():
                setattr(crash_game, k, v)
            try:
                test_config(); test_qualifies(); test_split(); await run_db_tests(db)
            except Exception:
                FAIL.append("raised: " + traceback.format_exc(limit=1).strip())
            finally:
                for k, v in saved.items():
                    setattr(crash_game, k, v)
                crash_game.manager = real_manager
            red = bool(FAIL)
            all_red = all_red and red
            print(f"  {'RED ' if red else 'GREEN(!)'} {label}  ({len(FAIL)} failing)")
        ok = ok and all_red
        print(f"  -> {'all mutants caught' if all_red else 'A MUTANT SURVIVED'}")

    await client.drop_database(name)
    client.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
