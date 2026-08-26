# -*- coding: utf-8 -*-
"""Casino settle-race gate -- REAL mongod, REAL writers, REAL concurrency.

2026-07-29: three site accounts held 3.94 BILLION of a 4.29 billion PrimeMeat
economy with a transaction ledger that accounted for none of it. The casino
credit paths write no ledger row, and `POST /api/casino/roll/bet` settled its
"one bet per player -- move it" rule with a read-then-write:

    existing = [b for b in cur["bets"] if b["user_id"] == me]   # READ
    if existing: credit(refund); pull(me)                       # WRITE
    charge(amount); push(new bet)

N concurrent requests all read the same array, all pay the refund and all push a
bet. The refunds cancel the charges exactly, so the player ends the round holding
N live bets having paid for ONE -- and `_roll_settle` pays every one of them. Bet
red and black in the same race and one of them wins 2x every single round.

Roll was also the only game with no maximum stake (every other game runs through
`_validate_bet` / CASINO_MAX_BET), which is what let it scale to billions.

This suite drives the REAL route handlers against a REAL MongoDB through the REAL
motor driver. No Mongo double: the whole fix is `find_one_and_update` claim
semantics and `modified_count`, and a double that got those subtly wrong would go
green on code that mints coins in production.

Run:  <venv>\\python.exe tests_local\\test_casino_settle_races.py
      <venv>\\python.exe tests_local\\test_casino_settle_races.py --mutants

Exit codes: 0 all pass / 1 a check failed / 2 the suite could NOT run (no mongod)
-- 2 is never a pass, a suite that did not run is a failed read.
"""
import argparse
import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

PASS = 0
FAIL = 0
_FAILED = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS %s" % name)
    else:
        FAIL += 1
        _FAILED.append(name)
        print("  FAIL %s %s" % (name, detail))


# ---------------------------------------------------------------------------
# mongod (portable, temp dbpath) -- the suite refuses to "pass" without one
# ---------------------------------------------------------------------------
PORTABLE_MONGOD = r"C:\LaIslaNublarWeb\_localtest\mongodb-7.0.28\mongodb-win32-x86_64-windows-7.0.28\bin\mongod.exe"
_mongo_proc = None
TMP = tempfile.mkdtemp(prefix="lin_casino_race_")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_mongo():
    global _mongo_proc
    url = os.environ.get("MONGO_URL")
    if url:
        print("[mongo] using MONGO_URL from env")
        return url
    if not os.path.isfile(PORTABLE_MONGOD):
        print("CANNOT RUN: no MONGO_URL and portable mongod missing at %s" % PORTABLE_MONGOD)
        sys.exit(2)
    dbpath = os.path.join(TMP, "db")
    os.makedirs(dbpath, exist_ok=True)
    port = _free_port()
    _mongo_proc = subprocess.Popen(
        [PORTABLE_MONGOD, "--dbpath", dbpath, "--port", str(port), "--bind_ip", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 40
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
            s.close()
            print("[mongo] portable mongod up on %d" % port)
            return "mongodb://127.0.0.1:%d" % port
        except OSError:
            if _mongo_proc.poll() is not None:
                print("CANNOT RUN: mongod exited rc=%s" % _mongo_proc.returncode)
                sys.exit(2)
            time.sleep(0.5)
    print("CANNOT RUN: mongod did not accept connections in 40s")
    sys.exit(2)


def stop_mongo():
    if _mongo_proc is not None and _mongo_proc.poll() is None:
        _mongo_proc.terminate()
        try:
            _mongo_proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            _mongo_proc.kill()
    shutil.rmtree(TMP, ignore_errors=True)


MONGO_URL = start_mongo()
os.environ["MONGO_URL"] = MONGO_URL
os.environ["DB_NAME"] = "lin_casino_race_%s" % uuid.uuid4().hex[:8]
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ.setdefault("RCON_HOST", "")
os.environ.setdefault("ALLOW_DEMO_LOGIN", "0")
os.environ.setdefault("DISCORD_BOT_TOKEN", "bot-token-fake")
os.environ.setdefault("DISCORD_GUILD_ID", "1523167556368859286")

sys.path.insert(0, BACKEND)
import server  # noqa: E402
import quest_data  # noqa: E402
from fastapi import HTTPException  # noqa: E402

db = server.db


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
async def mk_user(name, coins):
    uid = server.new_id()
    doc = {"id": uid, "steam_id": "7656119%010d" % (abs(hash(name)) % 10**10),
           "persona_name": name, "avatar": None, "role": "user",
           "coins": coins, "vip_coins": 0, "created_at": server.now_iso()}
    await db.users.insert_one(dict(doc))
    return await db.users.find_one({"id": uid}, {"_id": 0})


async def coins_of(uid):
    u = await db.users.find_one({"id": uid}, {"_id": 0, "coins": 1})
    return int(u["coins"])


async def open_round(round_no):
    await db.roll_current.replace_one({"id": "current"}, {
        "id": "current", "round_no": round_no, "phase": "betting",
        "phase_ends_at": server.now_iso(), "server_hash": "h", "server_seed": "s",
        "client_seed": "c", "bets": [], "totals": {"red": 0, "green": 0, "black": 0},
        "result_color": None, "roll": None}, upsert=True)
    await db.roll_meta.update_one({"id": "meta"},
                                  {"$set": {"round_no": round_no, "jackpot": 0.0, "green_streak": 0, "last_win": None}},
                                  upsert=True)


async def live_bets(uid):
    cur = await db.roll_current.find_one({"id": "current"}, {"_id": 0, "bets": 1})
    return [b for b in (cur.get("bets") or []) if b["user_id"] == uid]


async def gather_bets(user, calls):
    """Fire `calls` = [(color, amount), ...] truly concurrently at the REAL route."""
    async def one(color, amount):
        try:
            return await server.roll_bet(server.RollBetInput(color=color, amount=amount), user=user)
        except HTTPException as e:
            return {"error": e.status_code}
    return await asyncio.gather(*[one(c, a) for c, a in calls])


# ---------------------------------------------------------------------------
# 1. Roll -- the exploit itself
# ---------------------------------------------------------------------------
async def test_roll_duplicate_bet_race():
    print("\n[roll] concurrent move-bet cannot duplicate a live bet")
    u = await mk_user("racer", 1_000_000)
    await open_round(1)
    # honest opening bet
    await server.roll_bet(server.RollBetInput(color="red", amount=10_000), user=u)
    start = await coins_of(u["id"])
    check("one honest bet is live", len(await live_bets(u["id"])) == 1)

    # 6 concurrent "moves" -- the shape the exploit used (same round, mixed colours)
    await gather_bets(u, [("black", 10_000), ("red", 10_000), ("black", 10_000),
                          ("green", 10_000), ("red", 10_000), ("black", 10_000)])
    mine = await live_bets(u["id"])
    check("a racing player still holds exactly ONE live bet", len(mine) == 1,
          "held %d: %s" % (len(mine), [(b["color"], b["amount"]) for b in mine]))

    after = await coins_of(u["id"])
    staked = sum(int(b["amount"]) for b in mine)
    check("coins moved by exactly the one live stake", after == start + 10_000 - staked,
          "start=%d after=%d staked=%d" % (start, after, staked))

    cur = await db.roll_current.find_one({"id": "current"}, {"_id": 0, "totals": 1, "bets": 1})
    tot = cur["totals"]
    real = {"red": 0, "green": 0, "black": 0}
    for b in cur["bets"]:
        real[b["color"]] += int(b["amount"])
    check("displayed colour totals match the bets actually held", tot == real,
          "totals=%s real=%s" % (tot, real))


async def test_roll_settle_pays_one_stake():
    print("\n[roll] the settle pays the stake once, not once per racing request")
    u = await mk_user("racer2", 500_000)
    await open_round(2)
    await server.roll_bet(server.RollBetInput(color="red", amount=20_000), user=u)
    await gather_bets(u, [("red", 20_000)] * 5)
    before = await coins_of(u["id"])
    mine = await live_bets(u["id"])
    staked = sum(int(b["amount"]) for b in mine)
    cur = await db.roll_current.find_one({"id": "current"}, {"_id": 0})
    cur["result_color"] = "red"
    await server._roll_settle(cur)
    won = await coins_of(u["id"]) - before
    check("payout is exactly 2x the ONE stake held", won == staked * 2 and staked == 20_000,
          "won=%d staked=%d" % (won, staked))
    hist = await db.roll_history.find_one({"round_no": 2}, {"_id": 0})
    check("round total counts the stake once", (hist or {}).get("total") == 20_000,
          str((hist or {}).get("total")))


async def test_roll_cross_colour_race_cannot_profit():
    print("\n[roll] betting every colour at once cannot turn a profit")
    u = await mk_user("racer3", 300_000)
    await open_round(3)
    await server.roll_bet(server.RollBetInput(color="red", amount=30_000), user=u)
    await gather_bets(u, [("red", 30_000), ("black", 30_000), ("green", 30_000)])
    before = await coins_of(u["id"])
    mine = await live_bets(u["id"])
    colours = {b["color"] for b in mine}
    check("only one colour is covered", len(colours) <= 1, str(colours))
    worst = None
    for colour in ("red", "black", "green"):
        cur = await db.roll_current.find_one({"id": "current"}, {"_id": 0})
        cur["result_color"] = colour
        stake = sum(int(b["amount"]) for b in mine if b["color"] == colour)
        mult = server.ROLL_MULT[colour]
        gain = stake * mult
        worst = gain if worst is None else min(worst, gain)
    check("at least one colour pays this player nothing", worst == 0, str(worst))


async def test_roll_bet_cap():
    print("\n[roll] stake bounds")
    u = await mk_user("whale", 10_000_000_000)
    await open_round(4)
    check("Roll now shares the house maximum", server.ROLL_MAX_BET == server.CASINO_MAX_BET,
          "%s vs %s" % (server.ROLL_MAX_BET, server.CASINO_MAX_BET))
    try:
        await server.roll_bet(server.RollBetInput(color="red", amount=server.ROLL_MAX_BET + 1), user=u)
        check("a stake above the cap is refused", False, "accepted")
    except HTTPException as e:
        check("a stake above the cap is refused", e.status_code == 400, str(e.status_code))
    try:
        await server.roll_bet(server.RollBetInput(color="red", amount=server.ROLL_MIN_BET - 1), user=u)
        check("a stake below the minimum is refused", False, "accepted")
    except HTTPException as e:
        check("a stake below the minimum is refused", e.status_code == 400, str(e.status_code))
    r = await server.roll_bet(server.RollBetInput(color="red", amount=server.ROLL_MAX_BET), user=u)
    check("a stake exactly at the cap is accepted", r.get("success") is True)
    # The bet UI reads its ceiling off this payload. Without it the page would keep
    # its own copy of the number and offer chips the server refuses.
    st = await server.roll_state(user=u)
    check("roll/state advertises the cap to the UI",
          st["config"].get("max_bet") == server.ROLL_MAX_BET
          and st["config"].get("min_bet") == server.ROLL_MIN_BET, str(st["config"]))


async def test_roll_bet_needs_an_open_round():
    print("\n[roll] a bet cannot land after the wheel has shown its colour")
    u = await mk_user("late", 100_000)
    await open_round(5)
    before = await coins_of(u["id"])
    await db.roll_current.update_one({"id": "current"},
                                     {"$set": {"phase": "rolling", "result_color": "green"}})
    try:
        await server.roll_bet(server.RollBetInput(color="green", amount=10_000), user=u)
        check("a bet during the spin is refused", False, "accepted")
    except HTTPException as e:
        check("a bet during the spin is refused", e.status_code == 400, str(e.status_code))
    check("a refused bet costs the player nothing", await coins_of(u["id"]) == before)
    check("no bet leaked into the round", len(await live_bets(u["id"])) == 0)


async def test_roll_honest_move_still_works():
    print("\n[roll] the ordinary 'move my bet' still behaves")
    u = await mk_user("mover", 200_000)
    await open_round(6)
    await server.roll_bet(server.RollBetInput(color="red", amount=5_000), user=u)
    mid = await coins_of(u["id"])
    r = await server.roll_bet(server.RollBetInput(color="black", amount=8_000), user=u)
    check("the move reports itself as a move", r.get("moved") is True, str(r))
    mine = await live_bets(u["id"])
    check("the new bet replaced the old one", len(mine) == 1 and mine[0]["color"] == "black"
          and mine[0]["amount"] == 8_000, str(mine))
    check("only the difference was charged", await coins_of(u["id"]) == mid + 5_000 - 8_000,
          "mid=%d now=%d" % (mid, await coins_of(u["id"])))
    cur = await db.roll_current.find_one({"id": "current"}, {"_id": 0, "totals": 1})
    check("the old colour total was released", cur["totals"] == {"red": 0, "green": 0, "black": 8_000},
          str(cur["totals"]))
    meta = await db.roll_meta.find_one({"id": "meta"}, {"_id": 0, "jackpot": 1})
    check("the bonus pool tracks the live stake only",
          int(meta["jackpot"]) == int(8_000 * server.ROLL_JACKPOT_RATE),
          str(meta["jackpot"]))


async def test_roll_insufficient_funds_leaves_no_bet():
    print("\n[roll] a bet the player cannot afford leaves nothing behind")
    u = await mk_user("broke", 4_000)
    await open_round(7)
    try:
        await server.roll_bet(server.RollBetInput(color="red", amount=9_000), user=u)
        check("an unaffordable bet is refused", False, "accepted")
    except HTTPException as e:
        check("an unaffordable bet is refused", e.status_code == 400, str(e.status_code))
    check("the player keeps their coins", await coins_of(u["id"]) == 4_000)
    check("nothing was pushed into the round", len(await live_bets(u["id"])) == 0)


# ---------------------------------------------------------------------------
# 2. Siblings that settle the same way
# ---------------------------------------------------------------------------
async def test_blackjack_double_settle():
    print("\n[blackjack] a hand cannot be settled twice")
    u = await mk_user("bj", 100_000)
    await server.bj_deal(server.BjDealInput(bet=1_000), user=u)
    # Pin the hand to a WINNING one. A random deal usually loses, and a losing hand
    # pays 0 -- crediting zero four times looks identical to crediting it once, so
    # an unpinned hand makes this check unable to fail. Player 20 vs a dealer who
    # stands on 17: payout is a real 2,000.
    await db.casino_bj.update_many({"user_id": u["id"]}, {"$set": {
        "status": "playing", "bet": 1_000, "player": ["KS", "QH"], "dealer": ["9C", "8D"],
        "deck": ["2S", "3H", "4D", "5C", "6S", "7H"], "doubled": False,
        "result": None, "payout": 0}})
    g = await db.casino_bj.find_one({"user_id": u["id"], "status": "playing"}, {"_id": 0})
    check("precondition: a live winning hand exists",
          g is not None and server._hand_value(g["player"]) == 20
          and server._hand_value(g["dealer"]) == 17,
          str(g and (g["player"], g["dealer"])))
    if not g:
        return
    before = await coins_of(u["id"])

    async def stand():
        try:
            return await server.bj_stand(user=u)
        except HTTPException as e:
            return {"error": e.status_code}
    await asyncio.gather(stand(), stand(), stand(), stand())
    final = await db.casino_bj.find_one({"id": g["id"]}, {"_id": 0})
    paid = await coins_of(u["id"]) - before
    check("the winning hand paid 2,000 exactly once",
          paid == 2_000 and int(final.get("payout") or 0) == 2_000,
          "paid=%d payout=%s" % (paid, final.get("payout")))


async def test_mines_double_cashout():
    print("\n[mines] a game cannot be cashed out twice")
    u = await mk_user("mines", 100_000)
    await server.mines_start(server.MinesStartInput(bet=1_000, mines=1), user=u)
    g = await db.casino_mines.find_one({"user_id": u["id"], "status": "active"}, {"_id": 0})
    safe = next(i for i in range(25) if i not in g["mine_positions"])
    await server.mines_reveal(server.MinesRevealInput(index=safe), user=u)
    before = await coins_of(u["id"])
    mult = server._mines_multiplier(g["mines"], 1)

    async def cash():
        try:
            return await server.mines_cashout(user=u)
        except HTTPException as e:
            return {"error": e.status_code}
    await asyncio.gather(cash(), cash(), cash(), cash())
    paid = await coins_of(u["id"]) - before
    check("the game paid its cashout exactly once", paid == int(1_000 * mult),
          "paid=%d expected=%d" % (paid, int(1_000 * mult)))


async def test_market_outbid_refund_race():
    print("\n[market] one outbid, one refund")
    seller = await mk_user("seller", 0)
    first = await mk_user("bidder1", 100_000)
    second = await mk_user("bidder2", 1_000_000)
    lid = server.new_id()
    await db.market.insert_one({
        "id": lid, "type": "auction", "status": "active", "seller_id": seller["id"],
        "seller_name": seller["persona_name"], "dino_name": "Rex", "dino_slug": "rex",
        "price": 1_000, "current_bid": None, "current_bidder_id": None,
        "current_bidder_name": None, "fee_rate": 0.05, "source": "inventory",
        "created_at": server.now_iso(), "ends_at": server.now_iso(), "duration_hours": 24})
    await server.market_bid(lid, server.BidInput(amount=50_000), user=first)
    first_after_bid = await coins_of(first["id"])

    async def bid(n):
        try:
            return await server.market_bid(lid, server.BidInput(amount=n),
                                           user=await db.users.find_one({"id": second["id"]}, {"_id": 0}))
        except HTTPException as e:
            return {"error": e.status_code}
    await asyncio.gather(*[bid(60_000 + i) for i in range(5)])
    refunded = await coins_of(first["id"]) - first_after_bid
    check("the outbid player is refunded exactly their one escrowed bid", refunded == 50_000,
          "refunded=%d" % refunded)
    listing = await db.market.find_one({"id": lid}, {"_id": 0})
    escrowed = 1_000_000 - await coins_of(second["id"])
    check("the new leader has exactly the winning bid escrowed",
          escrowed == int(listing["current_bid"]),
          "escrowed=%d current_bid=%s" % (escrowed, listing["current_bid"]))


async def test_market_bid_cannot_overdraw():
    print("\n[market] concurrent bids cannot overdraw a balance")
    seller = await mk_user("seller2", 0)
    poor = await mk_user("poor", 10_000)
    lid = server.new_id()
    await db.market.insert_one({
        "id": lid, "type": "auction", "status": "active", "seller_id": seller["id"],
        "seller_name": seller["persona_name"], "dino_name": "Trike", "dino_slug": "trike",
        "price": 1_000, "current_bid": None, "current_bidder_id": None,
        "current_bidder_name": None, "fee_rate": 0.05, "source": "inventory",
        "created_at": server.now_iso(), "ends_at": server.now_iso(), "duration_hours": 24})

    async def bid(n):
        try:
            return await server.market_bid(lid, server.BidInput(amount=n),
                                           user=await db.users.find_one({"id": poor["id"]}, {"_id": 0}))
        except HTTPException as e:
            return {"error": e.status_code}
    await asyncio.gather(*[bid(9_000 + i) for i in range(4)])
    check("the balance never goes negative", await coins_of(poor["id"]) >= 0,
          str(await coins_of(poor["id"])))


# ---------------------------------------------------------------------------
# 3. The same shape outside the casino: anything that reads a "did you already
#    claim this?" flag and only writes it after paying out
# ---------------------------------------------------------------------------
async def test_code_redeem_race():
    print("\n[codes] a one-per-player code pays once")
    u = await mk_user("coder", 0)
    cid = server.new_id()
    await db.codes.insert_one({
        "id": cid, "code": "RACE1", "name": "RACE1", "active": True, "per_user": 1,
        "max_uses": 0, "uses": 0, "reward": {"coins": 1_500_000, "vip_coins": 5_000},
        "created_at": server.now_iso()})

    async def redeem():
        try:
            return await server.redeem_code(server.RedeemInput(code="RACE1"),
                                            user=await db.users.find_one({"id": u["id"]}, {"_id": 0}))
        except HTTPException as e:
            return {"error": e.status_code}
    res = await asyncio.gather(*[redeem() for _ in range(6)])
    ok = [r for r in res if r.get("success")]
    fresh = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    check("exactly one redemption succeeds", len(ok) == 1, "%d succeeded" % len(ok))
    check("the code paid its reward once", fresh["coins"] == 1_500_000 and fresh["vip_coins"] == 5_000,
          "coins=%s vip=%s" % (fresh["coins"], fresh["vip_coins"]))
    code = await db.codes.find_one({"id": cid}, {"_id": 0, "uses": 1})
    check("the use counter counts one", int(code["uses"]) == 1, str(code["uses"]))


async def test_code_max_uses_race():
    print("\n[codes] a limited code cannot be over-issued")
    cid = server.new_id()
    await db.codes.insert_one({
        "id": cid, "code": "RACE2", "name": "RACE2", "active": True, "per_user": 1,
        "max_uses": 2, "uses": 0, "reward": {"coins": 1_000}, "created_at": server.now_iso()})
    users = [await mk_user("limited%d" % i, 0) for i in range(6)]

    async def redeem(uu):
        try:
            return await server.redeem_code(server.RedeemInput(code="RACE2"),
                                            user=await db.users.find_one({"id": uu["id"]}, {"_id": 0}))
        except HTTPException as e:
            return {"error": e.status_code}
    res = await asyncio.gather(*[redeem(uu) for uu in users])
    ok = [r for r in res if r.get("success")]
    check("max_uses=2 issues exactly 2", len(ok) == 2, "%d succeeded" % len(ok))
    paid = 0
    for uu in users:
        if int((await db.users.find_one({"id": uu["id"]}))["coins"]) > 0:
            paid += 1
    check("only 2 players were paid", paid == 2, str(paid))


async def test_code_history_still_counts():
    print("\n[codes] redemptions made before this fix still count against the limit")
    u = await mk_user("veteran", 0)
    cid = server.new_id()
    await db.codes.insert_one({
        "id": cid, "code": "RACE3", "name": "RACE3", "active": True, "per_user": 1,
        "max_uses": 0, "uses": 1, "reward": {"coins": 777}, "created_at": server.now_iso()})
    await db.code_redemptions.insert_one({
        "id": server.new_id(), "code_id": cid, "code": "RACE3", "user_id": u["id"],
        "granted": {}, "created_at": server.now_iso()})
    try:
        await server.redeem_code(server.RedeemInput(code="RACE3"),
                                 user=await db.users.find_one({"id": u["id"]}, {"_id": 0}))
        check("an old redemption still blocks a new one", False, "accepted")
    except HTTPException as e:
        check("an old redemption still blocks a new one", e.status_code == 400, str(e.status_code))
    check("nothing was paid", (await db.users.find_one({"id": u["id"]}))["coins"] == 0)


async def test_quest_claim_race():
    print("\n[quests] a quest pays its reward once")
    u = await mk_user("quester", 0)
    qid = server.new_id()
    await db.quests.insert_one({
        "id": qid, "title": "Race quest", "active": True,
        "category": quest_data.QUEST_CATEGORIES[0], "objective": {"target": 1},
        "coins": 50_000, "vip": 100, "xp": 10, "period": "daily", "created_at": server.now_iso()})
    q = await db.quests.find_one({"id": qid}, {"_id": 0})
    await db.quest_progress.insert_one({
        "id": server.new_id(), "user_id": u["id"], "quest_id": qid,
        "period_key": server._quest_pk(q), "progress": 5, "claimed": False,
        "created_at": server.now_iso()})

    async def claim():
        try:
            return await server.claim_quest(qid, user=await db.users.find_one({"id": u["id"]}, {"_id": 0}))
        except HTTPException as e:
            return {"error": e.status_code}
    res = await asyncio.gather(*[claim() for _ in range(5)])
    ok = [r for r in res if r.get("success")]
    fresh = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    check("exactly one claim succeeds", len(ok) == 1, "%d succeeded" % len(ok))
    check("the quest paid once", fresh["coins"] == 50_000 and fresh["vip_coins"] == 100,
          "coins=%s vip=%s" % (fresh["coins"], fresh["vip_coins"]))


async def test_inventory_crate_race():
    print("\n[inventory] one owned crate opens once")
    u = await mk_user("crater", 0)
    case = server.seed_data.CASES[0]
    name = next((n for n, cid in server.CRATE_NAME_TO_CASE.items() if cid == case["id"]), None)
    check("precondition: a crate name maps to a case", name is not None)
    if not name:
        return
    inv_id = server.new_id()
    await db.inventory.insert_one({
        "id": inv_id, "user_id": u["id"], "category": "Crates", "name": name,
        "quantity": 1, "order": 9999, "acquired_at": server.now_iso()})

    async def open_it():
        try:
            return await server.open_crate_from_inventory(server.EquipSkinInput(inv_id=inv_id),
                                                          user=await db.users.find_one({"id": u["id"]}, {"_id": 0}))
        except HTTPException as e:
            return {"error": e.status_code}
    res = await asyncio.gather(*[open_it() for _ in range(5)])
    ok = [r for r in res if isinstance(r, dict) and "reward" in r]
    check("one owned crate yields exactly one open", len(ok) == 1, "%d opened" % len(ok))
    left = await db.inventory.find_one({"id": inv_id})
    check("the crate is gone from the inventory", left is None or int(left.get("quantity") or 0) <= 0,
          str(left and left.get("quantity")))


async def test_egg_open_race():
    print("\n[eggs] one owned egg opens once")
    u = await mk_user("egger", 0)
    tier = sorted(server.cosmetics_data.EGGS.keys())[0]
    inv_id = server.new_id()
    await db.inventory.insert_one({
        "id": inv_id, "user_id": u["id"], "category": "Eggs", "tier": tier,
        "name": "egg", "quantity": 1, "order": 9999, "acquired_at": server.now_iso()})

    async def open_it():
        try:
            return await server.cosmetics_egg_open(server.EggOpenInput(tier=tier),
                                                   user=await db.users.find_one({"id": u["id"]}, {"_id": 0}))
        except HTTPException as e:
            return {"error": e.status_code}
    res = await asyncio.gather(*[open_it() for _ in range(5)])
    ok = [r for r in res if isinstance(r, dict) and "error" not in r]
    check("one owned egg yields exactly one open", len(ok) == 1, "%d opened" % len(ok))
    left = await db.inventory.find_one({"id": inv_id})
    check("the egg is gone from the inventory", left is None or int(left.get("quantity") or 0) <= 0,
          str(left and left.get("quantity")))


async def test_daily_and_gift_race():
    print("\n[daily/gift] today's reward pays once")
    u = await mk_user("dailyguy", 0)

    async def daily():
        try:
            return await server.claim_daily(user=await db.users.find_one({"id": u["id"]}, {"_id": 0}))
        except HTTPException as e:
            return {"error": e.status_code}
    res = await asyncio.gather(*[daily() for _ in range(5)])
    ok = [r for r in res if "reward" in r]
    check("the daily reward is paid once", len(ok) == 1 and
          (await db.users.find_one({"id": u["id"]}))["coins"] == 250,
          "%d succeeded, coins=%s" % (len(ok), (await db.users.find_one({"id": u["id"]}))["coins"]))

    g = await mk_user("giftguy", 0)

    async def gift():
        try:
            return await server.gift_claim(user=await db.users.find_one({"id": g["id"]}, {"_id": 0}))
        except HTTPException as e:
            return {"error": e.status_code}
    res = await asyncio.gather(*[gift() for _ in range(5)])
    ok = [r for r in res if "error" not in r]
    fresh = await db.users.find_one({"id": g["id"]}, {"_id": 0})
    day1 = server._gift_reward_for(await server.gift_schedule_value(), 1)
    check("the login gift is paid once", len(ok) == 1
          and fresh["coins"] == (day1["coins"] or 0) and fresh["vip_coins"] == (day1["vip"] or 0),
          "%d succeeded, coins=%s vip=%s (day1=%s)" % (len(ok), fresh["coins"], fresh["vip_coins"], day1))


# ---------------------------------------------------------------------------
ALL_TESTS = [
    test_roll_duplicate_bet_race,
    test_roll_settle_pays_one_stake,
    test_roll_cross_colour_race_cannot_profit,
    test_roll_bet_cap,
    test_roll_bet_needs_an_open_round,
    test_roll_honest_move_still_works,
    test_roll_insufficient_funds_leaves_no_bet,
    test_blackjack_double_settle,
    test_mines_double_cashout,
    test_market_outbid_refund_race,
    test_market_bid_cannot_overdraw,
    test_code_redeem_race,
    test_code_max_uses_race,
    test_code_history_still_counts,
    test_quest_claim_race,
    test_inventory_crate_race,
    test_egg_open_race,
    test_daily_and_gift_race,
]


async def run_all():
    for t in ALL_TESTS:
        await t()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()

    print("=" * 74)
    print("CASINO SETTLE-RACE GATE   db=%s" % os.environ["DB_NAME"])
    print("=" * 74)
    # Preconditions: assert the world this suite believes in, so a dead fixture or a
    # drifted constant reads as a setup failure rather than a code failure.
    check("precondition: module under test is the repo copy",
          server.__file__.replace("\\", "/").endswith("web/backend/server.py"), server.__file__)
    check("precondition: mongod answers", (await db.command("ping")).get("ok") == 1.0)
    check("precondition: the roll route is the real handler",
          server.roll_bet.__module__ == "server")

    await run_all()

    ok = FAIL == 0
    print("\nGATE %d/%d" % (PASS, PASS + FAIL))
    for f in _FAILED:
        print("  RED  " + f)

    if args.mutants and ok:
        print("\nMUTATION SENSITIVITY (every mutant must turn the suite RED)")
        all_red = True
        for label, apply_mutant in MUTANTS:
            saved = _snapshot()
            globals()["PASS"] = 0
            globals()["FAIL"] = 0
            _FAILED.clear()
            apply_mutant()
            try:
                await run_all()
            except Exception as e:
                _FAILED.append("raised: %r" % e)
                globals()["FAIL"] = globals()["FAIL"] + 1
            finally:
                _restore(saved)
            red = FAIL > 0
            all_red = all_red and red
            print("  %s %s  (%d failing)" % ("RED " if red else "GREEN(!)", label, FAIL))
        ok = all_red
        print("  -> %s" % ("all mutants caught" if all_red else "A MUTANT SURVIVED"))

    await db.client.drop_database(os.environ["DB_NAME"])
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# mutants -- each one puts back a piece of the bug the fix removed
# ---------------------------------------------------------------------------
_MUTABLE = ("roll_bet", "_bj_resolve", "_mines_do_cashout", "market_bid", "ROLL_MAX_BET",
            "redeem_code", "claim_quest", "open_crate_from_inventory", "claim_daily", "gift_claim")


def _snapshot():
    return {k: getattr(server, k) for k in _MUTABLE}


def _restore(saved):
    for k, v in saved.items():
        setattr(server, k, v)


def mutant_roll_read_then_refund():
    """The exact pre-fix body: read the bets array, then refund off that read."""
    async def broken(data, user):
        if data.color not in ("red", "green", "black"):
            raise HTTPException(status_code=400, detail="Color invalido")
        if data.amount < server.ROLL_MIN_BET:
            raise HTTPException(status_code=400, detail="min")
        if data.amount > server.ROLL_MAX_BET:
            raise HTTPException(status_code=400, detail="max")
        cur = await server.db.roll_current.find_one({"id": "current"})
        if not cur or cur.get("phase") != "betting":
            raise HTTPException(status_code=400, detail="cerradas")
        existing = [b for b in cur.get("bets", []) if b["user_id"] == user["id"]]
        if existing:
            refund = sum(b["amount"] for b in existing)
            await server._casino_credit(user["id"], refund)
            dec = {}
            for b in existing:
                key = "totals.%s" % b["color"]
                dec[key] = dec.get(key, 0) - b["amount"]
            await server.db.roll_current.update_one(
                {"id": "current"}, {"$pull": {"bets": {"user_id": user["id"]}}, "$inc": dec})
            await server.db.roll_meta.update_one(
                {"id": "meta"}, {"$inc": {"jackpot": -int(refund * server.ROLL_JACKPOT_RATE)}}, upsert=True)
        await server._casino_charge(user["id"], data.amount)
        bet = {"user_id": user["id"], "name": user.get("persona_name") or "Survivor",
               "avatar": user.get("avatar"), "color": data.color, "amount": data.amount,
               "at": server.now_iso()}
        await server.db.roll_current.update_one(
            {"id": "current"}, {"$push": {"bets": bet}, "$inc": {"totals.%s" % data.color: data.amount}})
        await server.db.roll_meta.update_one(
            {"id": "meta"}, {"$inc": {"jackpot": int(data.amount * server.ROLL_JACKPOT_RATE)}}, upsert=True)
        return {"success": True, "balance": await server._casino_balance(user["id"]),
                "round_no": cur["round_no"], "moved": bool(existing)}
    server.roll_bet = broken


def mutant_roll_push_unguarded():
    """Claim the pull but push without the phase / one-bet guard."""
    real = server.roll_bet

    async def broken(data, user):
        cur = await server.db.roll_current.find_one({"id": "current"}, {"_id": 0, "round_no": 1, "phase": 1})
        if not cur:
            raise HTTPException(status_code=400, detail="cerradas")
        if data.amount < server.ROLL_MIN_BET or data.amount > server.ROLL_MAX_BET:
            raise HTTPException(status_code=400, detail="bounds")
        prev = await server.db.roll_current.find_one_and_update(
            {"id": "current", "bets.user_id": user["id"]},
            {"$pull": {"bets": {"user_id": user["id"]}}},
            projection={"_id": 0, "bets": 1}, return_document=server.ReturnDocument.BEFORE)
        if prev:
            mine = [b for b in (prev.get("bets") or []) if b["user_id"] == user["id"]]
            refund = sum(int(b["amount"]) for b in mine)
            if refund:
                dec = {}
                for b in mine:
                    dec["totals.%s" % b["color"]] = dec.get("totals.%s" % b["color"], 0) - int(b["amount"])
                await server.db.roll_current.update_one({"id": "current"}, {"$inc": dec})
                await server._casino_credit(user["id"], refund)
        await server._casino_charge(user["id"], data.amount)
        bet = {"user_id": user["id"], "name": user.get("persona_name") or "S", "avatar": None,
               "color": data.color, "amount": data.amount, "at": server.now_iso()}
        await server.db.roll_current.update_one(
            {"id": "current"}, {"$push": {"bets": bet}, "$inc": {"totals.%s" % data.color: data.amount}})
        return {"success": True, "balance": await server._casino_balance(user["id"]),
                "round_no": cur["round_no"], "moved": bool(prev)}
    server.roll_bet = broken
    assert real is not broken


def mutant_roll_no_cap():
    server.ROLL_MAX_BET = 10 ** 15


def mutant_bj_credit_first():
    async def broken(g, dealer_play=True):
        if dealer_play:
            while server._hand_value(g["dealer"]) < 17:
                g["dealer"].append(g["deck"].pop())
        pv, dv = server._hand_value(g["player"]), server._hand_value(g["dealer"])
        bet = g["bet"]
        player_bj = len(g["player"]) == 2 and pv == 21 and not g.get("doubled")
        dealer_bj = len(g["dealer"]) == 2 and dv == 21
        if pv > 21:
            result, payout, mult = "lose", 0, 0
        elif player_bj and not dealer_bj:
            result, payout, mult = "blackjack", int(bet * 2.5), 2.5
        elif dv > 21 or pv > dv:
            result, payout, mult = "win", bet * 2, 2.0
        elif pv < dv:
            result, payout, mult = "lose", 0, 0
        else:
            result, payout, mult = "push", bet, 1.0
        g["status"], g["result"], g["payout"] = "finished", result, payout
        await server._casino_credit(g["user_id"], payout)
        await server.db.casino_bj.update_one({"id": g["id"]}, {"$set": {
            "deck": g["deck"], "dealer": g["dealer"], "player": g["player"],
            "status": "finished", "result": result, "payout": payout,
            "doubled": g.get("doubled", False)}})
    server._bj_resolve = broken


def mutant_mines_no_claim():
    async def broken(user, g, mult):
        payout = int(g["bet"] * mult)
        await server.db.casino_mines.update_one({"id": g["id"]}, {"$set": {"status": "cashed"}})
        await server._casino_credit(user["id"], payout)
        u = await server.db.users.find_one({"id": user["id"]}, {"_id": 0})
        await server._record_bet(u, "mines", g["bet"], payout, mult, "win")
        return {"result": "cashout", "multiplier": mult, "payout": payout,
                "mine_positions": g["mine_positions"], "balance": await server._casino_balance(user["id"])}
    server._mines_do_cashout = broken


def mutant_market_refund_off_the_read():
    async def broken(listing_id, data, user):
        l = await server.db.market.find_one({"id": listing_id, "status": "active"})
        if not l or l["type"] != "auction":
            raise HTTPException(status_code=404, detail="no")
        min_bid = (l["current_bid"] or l["price"] - 1) + 1
        if data.amount < min_bid:
            raise HTTPException(status_code=400, detail="low")
        await server.db.users.update_one({"id": user["id"]}, {"$inc": {"coins": -data.amount}})
        if l.get("current_bidder_id"):
            await server.db.users.update_one({"id": l["current_bidder_id"]},
                                             {"$inc": {"coins": l["current_bid"]}})
        await server.db.market.update_one({"id": listing_id}, {"$set": {
            "current_bid": data.amount, "current_bidder_id": user["id"],
            "current_bidder_name": user["persona_name"]}})
        fresh = await server.db.users.find_one({"id": user["id"]}, {"_id": 0})
        return {"success": True, "balance": {"coins": fresh["coins"], "vip_coins": fresh["vip_coins"]}}
    server.market_bid = broken


def mutant_code_count_then_grant():
    """The pre-fix body: count redemptions, then grant."""
    async def broken(data, user):
        code_str = data.code.strip().upper()
        code = await server.db.codes.find_one({"code": code_str})
        if not code:
            raise HTTPException(status_code=404, detail="Codigo invalido")
        max_uses = code.get("max_uses", 0) or 0
        if max_uses and code.get("uses", 0) >= max_uses:
            raise HTTPException(status_code=400, detail="limite")
        n = await server.db.code_redemptions.count_documents(
            {"code_id": code["id"], "user_id": user["id"]})
        if n >= (code.get("per_user", 1) or 1):
            raise HTTPException(status_code=400, detail="ya canjeado")
        granted = await server.apply_reward(user["id"], code.get("reward", {}), "Code: %s" % code["name"])
        await server.db.codes.update_one({"id": code["id"]}, {"$inc": {"uses": 1}})
        await server.db.code_redemptions.insert_one({
            "id": server.new_id(), "code_id": code["id"], "code": code_str,
            "user_id": user["id"], "granted": granted, "created_at": server.now_iso()})
        return {"success": True, "granted": granted}
    server.redeem_code = broken


def mutant_code_claim_ignores_history():
    """Counter starts at zero, so redemptions made before the fix stop counting."""
    real = server.redeem_code

    async def broken(data, user):
        rows = server.db.code_redemptions
        orig = rows.count_documents

        async def zero(*a, **k):
            return 0
        rows.count_documents = zero
        try:
            return await real(data, user)
        finally:
            rows.count_documents = orig
    server.redeem_code = broken


def mutant_quest_pay_then_mark():
    async def broken(quest_id, user):
        q = await server.db.quests.find_one({"id": quest_id, "active": True}, {"_id": 0})
        if not q:
            raise HTTPException(status_code=404, detail="no")
        pk = server._quest_pk(q)
        prog = await server.db.quest_progress.find_one(
            {"user_id": user["id"], "quest_id": quest_id, "period_key": pk}, {"_id": 0})
        if prog and prog.get("claimed"):
            raise HTTPException(status_code=400, detail="ya")
        target = int(q.get("objective", {}).get("target", 1))
        if (prog.get("progress", 0) if prog else 0) < target:
            raise HTTPException(status_code=400, detail="incompleto")
        inc = {}
        if q.get("coins"):
            inc["coins"] = q["coins"]
        if q.get("vip"):
            inc["vip_coins"] = q["vip"]
        if q.get("xp"):
            inc["xp"] = q["xp"]
        if inc:
            await server.db.users.update_one({"id": user["id"]}, {"$inc": inc})
        await server.db.quest_progress.update_one(
            {"user_id": user["id"], "quest_id": quest_id, "period_key": pk},
            {"$set": {"claimed": True, "claimed_at": server.now_iso(), "progress": target}}, upsert=True)
        return {"success": True}
    server.claim_quest = broken


def mutant_inventory_crate_read_then_delete():
    async def broken(data, user):
        item = await server.db.inventory.find_one(
            {"id": data.inv_id, "user_id": user["id"], "category": "Crates"}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail="no")
        case_id = server.CRATE_NAME_TO_CASE.get(item.get("name", "").strip().lower())
        case = next((c for c in server.seed_data.CASES if c["id"] == case_id), None)
        if not case:
            raise HTTPException(status_code=400, detail="no")
        if item.get("quantity", 1) > 1:
            await server.db.inventory.update_one({"id": item["id"]}, {"$inc": {"quantity": -1}})
        else:
            await server.db.inventory.delete_one({"id": item["id"]})
        return await server._grant_case_reward(user, case)
    server.open_crate_from_inventory = broken


def mutant_daily_and_gift_unstamped():
    async def broken_daily(user):
        last = user.get("last_daily_claim")
        if last:
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            if _dt.now(_tz.utc) - _dt.fromisoformat(last) < _td(hours=20):
                raise HTTPException(status_code=400, detail="ya")
        await server.db.users.update_one({"id": user["id"]},
                                         {"$inc": {"coins": 250},
                                          "$set": {"last_daily_claim": server.now_iso()}})
        return {"reward": 250, "currency": "normal"}
    server.claim_daily = broken_daily


MUTANTS = [
    ("roll: read-then-refund (the live bug)", mutant_roll_read_then_refund),
    ("roll: claimed pull but unguarded push", mutant_roll_push_unguarded),
    ("roll: stake cap removed again", mutant_roll_no_cap),
    ("blackjack: credit before the status claim", mutant_bj_credit_first),
    ("mines: cashout without the status claim", mutant_mines_no_claim),
    ("market: refund the bidder read off the listing", mutant_market_refund_off_the_read),
    ("codes: count redemptions then grant", mutant_code_count_then_grant),
    ("codes: per-user counter forgets old redemptions", mutant_code_claim_ignores_history),
    ("quests: pay then mark claimed", mutant_quest_pay_then_mark),
    ("inventory: read the crate then delete it", mutant_inventory_crate_read_then_delete),
    ("daily: stamp written without pinning the old one", mutant_daily_and_gift_unstamped),
]


if __name__ == "__main__":
    rc = 1
    try:
        rc = asyncio.run(main())
    finally:
        stop_mongo()
    sys.exit(rc)
