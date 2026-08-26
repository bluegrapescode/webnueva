"""Retirement gate for crash_game.py -- run directly, no pytest.

    <venv>\\python.exe tests_local\\test_crash_retired.py --mongo mongodb://127.0.0.1:27017
    <venv>\\python.exe tests_local\\test_crash_retired.py --mongo ... --mutants

2026-08-20, the owner: "remopve crash game". Removed means: the loop announces
its receipt, refunds whatever the final round left flying, starts NO rounds and
completes; the websocket answers every visitor with words and closes BEFORE
authentication; no path can take a stake. The ledger and the module stay, so
flipping RETIRED back restores the game whole -- and this suite flips with it:
every check here is conditioned on the flag being True, and the first check
pins that it IS True (the owner's order; un-retiring is a deliberate edit here
too, not a drive-by).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crash_game  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name if condition else f"{name} :: {detail}")


class Recorder:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.broadcasts: list[dict] = []

    async def broadcast(self, message: dict) -> None:
        self.broadcasts.append(message)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        pass

    async def send(self, websocket, message: dict) -> None:
        self.sent.append(message)

    def register(self, websocket, user_id: str) -> None:
        pass

    def unregister(self, websocket) -> None:
        pass


class FakeSocket:
    """Only what the retired gate may touch. NO receive_text on purpose: if the
    gate ever falls through to authentication, the AttributeError turns this
    suite red -- the retired door must answer before asking who you are."""

    def __init__(self) -> None:
        self.accepted = False
        self.closed_with = None

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


async def fresh_db(mongo_url: str):
    import motor.motor_asyncio as ma
    client = ma.AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=8000)
    name = "gate_retired_" + uuid.uuid4().hex[:8]
    await client.drop_database(name)
    return client, client[name], name


def bet(uid: str, amount: int, cashed=None) -> dict:
    return {"user_id": uid, "name": "n_" + uid, "avatar": None,
            "amount": amount, "auto_cashout": None, "cashed_at": cashed, "payout": 0}


async def run_tests(db) -> None:
    check("RETIRED is the shipped state (the owner's order)", crash_game.RETIRED is True,
          repr(crash_game.RETIRED))
    check("the retired message speaks", "retirado" in crash_game._RETIRED_MSG)

    # -- the retired loop: announces, rescues the final round, starts nothing --
    await db.users.delete_many({})
    await db.casino_bets.delete_many({})
    await db.users.insert_one({"id": "u1", "coins": 1000})
    await db.crash_round.replace_one({"id": "current"}, {
        "id": "current", "round_no": 900, "phase": "running",
        "server_seed": "s", "server_hash": "h", "client_seed": "public",
        "crash_point": 2.0, "bets": [bet("u1", 400)],
        "betting_ends_at": 0.0, "running_started_at": 0.0}, upsert=True)
    await db.crash_meta.replace_one({"id": "meta"}, {"id": "meta", "last_round_no": 900}, upsert=True)

    saved_sleep = asyncio.sleep

    async def no_wait(_s):
        await saved_sleep(0)

    crash_game.asyncio.sleep = no_wait
    try:
        task = asyncio.get_event_loop().create_task(crash_game.run_crash_loop())
        for _ in range(300):
            await saved_sleep(0.01)
            if task.done():
                break
        loop_finished = task.done() and not task.cancelled()
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    finally:
        crash_game.asyncio.sleep = saved_sleep

    check("retired loop completes on its own", loop_finished)
    u1 = await db.users.find_one({"id": "u1"})
    check("the final round's flying stake was refunded", int(u1["coins"]) == 1400, str(u1["coins"]))
    doc = await db.crash_round.find_one({"id": "current"})
    check("the final round doc was frozen, never replaced",
          doc.get("round_no") == 900 and doc.get("phase") == "crashed" and doc.get("rescued") is True,
          repr({k: doc.get(k) for k in ("round_no", "phase", "rescued")}))
    meta = await db.crash_meta.find_one({"id": "meta"})
    check("no new round number was ever written", int(meta.get("last_round_no")) == 900,
          str(meta.get("last_round_no")))
    refunds = [r async for r in db.casino_bets.find({"game": "crash", "result": "refund"})]
    check("the refund reached the ledger at net zero",
          len(refunds) == 1 and refunds[0]["net"] == 0, str(len(refunds)))

    # -- running it again changes nothing (a watchdog restart is a no-op) -------
    crash_game.asyncio.sleep = no_wait
    try:
        await asyncio.wait_for(crash_game.run_crash_loop(), timeout=10)
    finally:
        crash_game.asyncio.sleep = saved_sleep
    u1 = await db.users.find_one({"id": "u1"})
    check("a second retired boot refunds nothing again", int(u1["coins"]) == 1400, str(u1["coins"]))

    # -- the websocket answers with words BEFORE authentication -----------------
    ws = FakeSocket()
    await crash_game.crash_socket(ws)
    check("retired socket is accepted then answered", ws.accepted is True)
    check("retired socket closes with the retired code", ws.closed_with == 4410, str(ws.closed_with))
    said = [m for m in crash_game.manager.sent if m.get("message") == crash_game._RETIRED_MSG]
    check("retired socket got the words", bool(said), repr(crash_game.manager.sent[-2:]))

    # -- no stake can be taken through the unit wall either ----------------------
    crash_game.manager.sent.clear()
    await crash_game._handle_bet(FakeSocket(), {"id": "u1", "coins": 1400}, {"amount": 100})
    u1 = await db.users.find_one({"id": "u1"})
    check("a bet against the retired game takes nothing", int(u1["coins"]) == 1400, str(u1["coins"]))
    check("and it answers with the retired words",
          any(m.get("message") == crash_game._RETIRED_MSG for m in crash_game.manager.sent))


MUTANTS = []


def mutant_unretired():
    return "RETIRED flipped off", {"RETIRED": False}


def mutant_silent_socket():
    async def silent(websocket):
        await websocket.accept()
        await websocket.close(code=4410)
    return "socket closes without words", {"crash_socket": silent}


def mutant_no_rescue():
    async def no_rescue():
        pass
    return "retirement skips the rescue", {"_rescue_abandoned_bets": no_rescue}


MUTANTS.extend([mutant_unretired, mutant_silent_socket, mutant_no_rescue])


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", required=True)
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()

    check("precondition: module under test is the repo copy",
          crash_game.__file__.replace("\\", "/").endswith("web/backend/crash_game.py"),
          crash_game.__file__)

    real_manager = crash_game.manager
    crash_game.manager = Recorder()
    client, db, name = await fresh_db(args.mongo)
    crash_game.configure(db, "gatesecret")
    try:
        await run_tests(db)
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
            crash_game.manager = Recorder()
            await client.drop_database(name)
            for k, v in patches.items():
                setattr(crash_game, k, v)
            try:
                await asyncio.wait_for(run_tests(db), timeout=30)
            except Exception:
                pass  # a mutant that crashes or hangs the suite is RED too
            finally:
                for k, v in saved.items():
                    setattr(crash_game, k, v)
                crash_game.manager = real_manager
            red = bool(FAIL)
            print(("  RED  " if red else "  GREEN(BAD) ") + label)
            all_red = all_red and red
        ok = ok and all_red

    await client.drop_database(name)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
