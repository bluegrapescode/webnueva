"""Abandoned-round rescue gate for crash_game.py -- run directly, no pytest.

    <venv>\\python.exe tests_local\\test_crash_abandoned_rescue.py --mongo mongodb://127.0.0.1:27017
    <venv>\\python.exe tests_local\\test_crash_abandoned_rescue.py --mongo ... --mutants

Drives the REAL _rescue_abandoned_bets against a REAL mongod (scratch database,
dropped after): the whole point of the rescue is its find_one_and_update latch
semantics, and a double that got those wrong would go green on code that double
-refunds or eats stakes in production.

The defect this pins (2026-08-20): a round that died mid-flight (mongod
terminated by an FTDC rename collision) was silently REPLACED by the next
round's _start_betting_phase -- its un-cashed stakes, already deducted at bet
time, vanished unrecorded, and the stale "betting" doc kept accepting new
stakes into a round nothing would ever settle.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crash_game  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name if condition else f"{name} :: {detail}")


class Recorder:
    def __init__(self) -> None:
        self.broadcasts: list[dict] = []

    async def broadcast(self, message: dict) -> None:
        self.broadcasts.append(message)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        pass

    async def send(self, websocket, message: dict) -> None:
        pass

    def register(self, websocket, user_id: str) -> None:
        pass

    def unregister(self, websocket) -> None:
        pass


async def fresh_db(mongo_url: str):
    import motor.motor_asyncio as ma
    client = ma.AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=8000)
    name = "gate_rescue_" + uuid.uuid4().hex[:8]
    await client.drop_database(name)
    return client, client[name], name


def bet(uid: str, amount: int, cashed=None) -> dict:
    return {"user_id": uid, "name": "n_" + uid, "avatar": None,
            "amount": amount, "auto_cashout": None, "cashed_at": cashed, "payout": 0}


async def seed_round(db, round_no: int, phase: str, bets: list[dict], rescued=None) -> None:
    doc = {"id": "current", "round_no": round_no, "phase": phase,
           "server_seed": "s", "server_hash": "h", "client_seed": "public",
           "crash_point": 2.0, "bets": bets,
           "betting_ends_at": 0.0, "running_started_at": 0.0}
    if rescued is not None:
        doc["rescued"] = rescued
    await db.crash_round.replace_one({"id": "current"}, doc, upsert=True)


async def coins(db, uid: str) -> int:
    u = await db.users.find_one({"id": uid})
    return int((u or {}).get("coins", -1))


async def run_db_tests(db) -> None:
    # -- 1. the incident shape: running round, one cashed, two flying ---------
    await db.users.delete_many({})
    await db.casino_bets.delete_many({})
    for uid in ("a", "b", "c"):
        await db.users.insert_one({"id": uid, "coins": 1000})
    await seed_round(db, 500, "running",
                     [bet("a", 300), bet("b", 250), bet("c", 100, cashed=1.5)])
    await crash_game._rescue_abandoned_bets()
    check("flying stake A refunded", await coins(db, "a") == 1300, str(await coins(db, "a")))
    check("flying stake B refunded", await coins(db, "b") == 1250, str(await coins(db, "b")))
    check("cashed bet C not touched", await coins(db, "c") == 1000, str(await coins(db, "c")))
    doc = await db.crash_round.find_one({"id": "current"})
    check("doc frozen crashed", doc.get("phase") == "crashed", str(doc.get("phase")))
    check("doc carries rescued marker", doc.get("rescued") is True, str(doc.get("rescued")))
    rows = [r async for r in db.casino_bets.find({"game": "crash", "result": "refund"})]
    check("two refund ledger rows", len(rows) == 2, str(len(rows)))
    check("refund rows are net zero", all(r["net"] == 0 and r["bet"] == r["payout"] for r in rows),
          str([(r["bet"], r["payout"], r["net"]) for r in rows]))

    # -- 2. idempotent: a second rescue pays nothing again --------------------
    await crash_game._rescue_abandoned_bets()
    check("second rescue refunds nothing (A)", await coins(db, "a") == 1300, str(await coins(db, "a")))
    rows = [r async for r in db.casino_bets.find({"game": "crash", "result": "refund"})]
    check("still exactly two refund rows", len(rows) == 2, str(len(rows)))

    # -- 3. a NORMALLY crashed round is never refunded -------------------------
    await db.users.update_one({"id": "a"}, {"$set": {"coins": 1000}})
    await seed_round(db, 501, "crashed", [bet("a", 400)])  # loss recorded by _finish_round in real life
    await crash_game._rescue_abandoned_bets()
    check("normal loss never refunded", await coins(db, "a") == 1000, str(await coins(db, "a")))

    # -- 4. abandoned during BETTING refunds too --------------------------------
    await seed_round(db, 502, "betting", [bet("b", 111)])
    await crash_game._rescue_abandoned_bets()
    check("betting-phase stake refunded", await coins(db, "b") == 1361, str(await coins(db, "b")))

    # -- 5. after the freeze, the bet-push filter can no longer match -----------
    pushed = await db.crash_round.find_one_and_update(
        {"id": "current", "phase": "betting", "bets.user_id": {"$ne": "z"}},
        {"$push": {"bets": bet("z", 50)}})
    check("frozen doc rejects new stakes", pushed is None, str(pushed))

    # -- 6. no doc / no flying bets are clean no-ops ----------------------------
    await db.crash_round.delete_many({})
    await crash_game._rescue_abandoned_bets()
    check("no doc is a no-op", True)
    await seed_round(db, 503, "running", [bet("c", 70, cashed=1.2)])
    await crash_game._rescue_abandoned_bets()
    doc = await db.crash_round.find_one({"id": "current"})
    check("all-cashed round left for the loop", doc.get("phase") == "running", str(doc.get("phase")))

    # -- 7. credit blows up mid-rescue: claim released, retry pays exactly once -
    await db.users.update_one({"id": "a"}, {"$set": {"coins": 500}})
    await seed_round(db, 504, "running", [bet("a", 200)])
    real_add = crash_game._add_coins
    calls = {"n": 0}

    async def exploding_add(uid, amount):
        calls["n"] += 1
        raise RuntimeError("mongo went away")

    crash_game._add_coins = exploding_add
    try:
        try:
            await crash_game._rescue_abandoned_bets()
        except RuntimeError:
            pass
        check("credit failure propagated to the loop", calls["n"] == 1, str(calls["n"]))
        check("stake not paid on failure", await coins(db, "a") == 500, str(await coins(db, "a")))
    finally:
        crash_game._add_coins = real_add
    await crash_game._rescue_abandoned_bets()
    check("retry after failure pays exactly once", await coins(db, "a") == 700, str(await coins(db, "a")))

    # -- 8. credit reports no-user-row: logged loss, others still refunded ------
    await db.users.update_one({"id": "b"}, {"$set": {"coins": 100}})
    await seed_round(db, 505, "running", [bet("ghost-user", 999), bet("b", 40)])
    await crash_game._rescue_abandoned_bets()
    check("bet beside a lost credit still refunded", await coins(db, "b") == 140, str(await coins(db, "b")))

    # -- 9. the loop actually calls the rescue ----------------------------------
    src = inspect.getsource(crash_game.run_crash_loop)
    check("run_crash_loop wires the rescue", "_rescue_abandoned_bets()" in src)


MUTANTS = []


def mutant_no_rescued_marker():
    async def freeze_without_marker():
        db = crash_game._db
        doc = await db.crash_round.find_one({"id": "current"})
        if not doc:
            return
        # broken: refunds NORMALLY crashed rounds too (no rescued distinction)
        for b in (doc.get("bets") or []):
            if b.get("cashed_at") is None:
                await crash_game._add_coins(b["user_id"], int(b["amount"]))
        await db.crash_round.update_one({"id": "current"}, {"$set": {"phase": "crashed"}})
    return "refunds settled rounds (no rescued marker)", {"_rescue_abandoned_bets": freeze_without_marker}


def mutant_no_claim():
    orig = crash_game._rescue_abandoned_bets

    async def no_idempotency():
        db = crash_game._db
        doc = await db.crash_round.find_one({"id": "current"})
        if not doc or (doc.get("phase") == "crashed" and not doc.get("rescued")):
            return
        flying = [b for b in (doc.get("bets") or []) if b.get("cashed_at") is None]
        if doc.get("phase") != "crashed":
            if not flying:
                return
            await db.crash_round.update_one(
                {"id": "current"}, {"$set": {"phase": "crashed", "rescued": True}})
        # broken: pays on every call, no per-bet claim
        for b in flying:
            await crash_game._add_coins(b["user_id"], int(b["amount"]))
            await crash_game._record_bet(b, int(b["amount"]), 1.0, "refund")
    return "pays every call (no per-bet claim)", {"_rescue_abandoned_bets": no_idempotency}


def mutant_zero_refund():
    async def zero():
        db = crash_game._db
        doc = await db.crash_round.find_one({"id": "current"})
        if not doc or doc.get("phase") == "crashed":
            return
        if any(b.get("cashed_at") is None for b in (doc.get("bets") or [])):
            await db.crash_round.update_one(
                {"id": "current"}, {"$set": {"phase": "crashed", "rescued": True}})
        # broken: freezes but never credits anyone
    return "freezes without refunding", {"_rescue_abandoned_bets": zero}


MUTANTS.extend([mutant_no_rescued_marker, mutant_no_claim, mutant_zero_refund])


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", required=True)
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()

    real_manager = crash_game.manager
    crash_game.manager = Recorder()
    client, db, name = await fresh_db(args.mongo)
    crash_game.configure(db, "gatesecret")

    check("precondition: module under test is the repo copy",
          crash_game.__file__.replace("\\", "/").endswith("web/backend/crash_game.py"),
          crash_game.__file__)

    try:
        await run_db_tests(db)
    finally:
        crash_game.manager = real_manager

    print(f"\nGATE {len(PASS)}/{len(PASS) + len(FAIL)}")
    for f in FAIL:
        print("  RED  " + f)
    ok = not FAIL

    if args.mutants and ok:
        print("\nMUTATION SENSITIVITY")
        all_red = True
        for factory in MUTANTS:
            label, patches = factory()
            saved = {k: getattr(crash_game, k) for k in patches}
            PASS.clear()
            FAIL.clear()
            for k, v in patches.items():
                setattr(crash_game, k, v)
            try:
                await run_db_tests(db)
            except Exception:
                pass  # a mutant that crashes the suite is RED too
            finally:
                for k, v in saved.items():
                    setattr(crash_game, k, v)
            red = bool(FAIL)
            print(("  RED  " if red else "  GREEN(BAD) ") + label)
            all_red = all_red and red
        ok = ok and all_red

    await client.drop_database(name)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
