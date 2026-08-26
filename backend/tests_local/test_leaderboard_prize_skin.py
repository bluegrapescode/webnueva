# -*- coding: utf-8 -*-
"""Season leaderboard COSMETIC PRIZE gate -- REAL mongod, REAL rollover writer.

2026-08-16 (owner order): the 1o place of the monthly Clasificacion wins the
"Supernova" glitch skin ON TOP of its 5.000.000 PrimeMeat. 2026-08-18 (owner
order, "supernova for 123 place in leaderboard"): the WHOLE PODIUM wears it.
The whole risk of that change is idempotency: the rollover tick runs every 300s
from a background loop forever, so anything it does that is not claim-gated is
done again five minutes later, and again after every restart -- and three riders
means three independent claims, where one shared marker would lose two skins the
moment one grant threw.

Why a REAL mongod and no double: the safety is `find_one_and_update` with
`{"paid_skin_ranks": {"$ne": rank}}` + `$addToSet` -- claim semantics a fake
would be free to get subtly wrong while the product grants a skin every 5
minutes in production. Same call the money half already makes, and the same
reason the casino race suite refuses to run without a real server.

WHAT IS PINNED
  * the money half is byte-for-byte unchanged (amount, tx label, one payment);
  * the skin lands once, with the right allowance and a readable source;
  * TWO INDEPENDENT MARKERS: coins paid + skin crashed => the retry finishes the
    skin and does NOT re-pay the coins (the failure this shape exists for);
  * a receipt written by the PREVIOUS build (no "skin" key) still grants -- the
    upgrade path, since a season can be mid-flight when the deploy lands;
  * ALL THREE places are granted, each under its OWN claim marker, and a place
    nobody earned is still never invented;
  * ONE place failing mid-payout leaves the other two granted and hands only
    the failed place back for retry (the risk the widening actually added);
  * a champion who ALREADY owns the design gets quantity+uses, never a crash on
    the unique (user_id, glitch_id) index;
  * repeated ticks, and concurrent ticks, grant exactly once.

Run:  <python312>\\python.exe tests_local\\test_leaderboard_prize_skin.py
Exit: 0 all pass / 1 a check failed / 2 the suite could NOT run (no mongod)
      -- 2 is never a pass; a suite that did not run is a failed read.
"""
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
TMP = tempfile.mkdtemp(prefix="lin_lb_prize_")


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
os.environ["DB_NAME"] = "lin_lb_prize_%s" % uuid.uuid4().hex[:8]
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ.setdefault("RCON_HOST", "")
os.environ.setdefault("ALLOW_DEMO_LOGIN", "0")
os.environ.setdefault("DISCORD_BOT_TOKEN", "bot-token-fake")
os.environ.setdefault("DISCORD_GUILD_ID", "1523167556368859286")

sys.path.insert(0, BACKEND)
import server  # noqa: E402
import leaderboards  # noqa: E402
import glitch_catalog  # noqa: E402

db = server.db

PRIZE_GID = "supernova"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
async def reset():
    for coll in ("users", "leaderboard_stats", "leaderboard_meta",
                 "leaderboard_awards", "reward_skins", "transactions"):
        await db[coll].delete_many({})
    # The unique index the grant upsert leans on. Created by the real startup
    # path in prod; a suite that skipped it would pass on a broken upsert.
    await db.reward_skins.create_index([("user_id", 1), ("glitch_id", 1)],
                                       unique=True)
    await db.leaderboard_awards.create_index("season_id", unique=True)


async def mk_player(name, score):
    uid = server.new_id()
    await db.users.insert_one({
        "id": uid, "steam_id": "7656119%010d" % (abs(hash(name)) % 10**10),
        "persona_name": name, "avatar": None, "role": "user",
        "coins": 0, "vip_coins": 0, "created_at": server.now_iso()})
    return uid


async def seed_finished_season(players):
    """players = [(name, score)] highest first. Returns [user_id] in rank order.

    The season is seeded as the PREVIOUS month and `last_awarded_season` is set
    two months back, so the very next tick sees a finished, unpaid season."""
    sid = leaderboards.season_id()
    prev = leaderboards.previous_season_id(sid)
    uids = []
    for name, score in players:
        uid = await mk_player(name, score)
        uids.append(uid)
        await db.leaderboard_stats.insert_one({
            "id": server.new_id(), "user_id": uid, "season_id": prev,
            "kills_month": 0, "deaths_month": 0, "quests_month": 0,
            "playtime_seconds_month": 0, "score": int(score),
            "updated_at": server.now_iso()})
    await db.leaderboard_meta.update_one(
        {"key": "last_awarded_season"},
        {"$set": {"season_id": leaderboards.previous_season_id(prev)}},
        upsert=True)
    return prev, uids


async def coins_of(uid):
    u = await db.users.find_one({"id": uid}, {"_id": 0, "coins": 1})
    return int((u or {}).get("coins") or 0)


async def skins_of(uid):
    return await db.reward_skins.find({"user_id": uid}, {"_id": 0}).to_list(50)


async def receipt(sid):
    return await db.leaderboard_awards.find_one({"season_id": sid}, {"_id": 0})


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------
async def case_champion_wins_coins_and_the_skin():
    print("[case_champion_wins_coins_and_the_skin]")
    await reset()
    prev, uids = await seed_finished_season([("Champ", 900), ("Second", 500), ("Third", 100)])
    await server._leaderboard_rollover_tick()

    check("1o was paid the unchanged 5.000.000 PrimeMeat",
          await coins_of(uids[0]) == 5_000_000)
    check("2o and 3o were paid their unchanged amounts",
          await coins_of(uids[1]) == 3_000_000 and await coins_of(uids[2]) == 1_000_000)

    won = await skins_of(uids[0])
    check("1o holds exactly one reward skin", len(won) == 1, str(won))
    row = won[0] if won else {}
    check("...and it is the design the owner sent", row.get("glitch_id") == PRIZE_GID,
          str(row.get("glitch_id")))
    check("...with the standard per-win use allowance",
          int(row.get("uses") or 0) == server.GLITCH_USES_PER_WIN, str(row.get("uses")))
    check("...quantity 1", int(row.get("quantity") or 0) == 1, str(row.get("quantity")))
    check("...naming the season and the place in `source`",
          prev in str(row.get("source")) and "1" in str(row.get("source")),
          str(row.get("source")))
    check("...carrying NO render URL (fleet order 2026-08-11)",
          row.get("image") == "", repr(row.get("image")))
    check("...marked Legendary", row.get("rarity") == "Legendary", str(row.get("rarity")))

    # 2026-08-18 owner order: 2o and 3o wear it too, one copy each, and each
    # `source` names ITS OWN place -- a shared source line would tell a player
    # who came third that they won the championship.
    for idx, place in ((1, "2"), (2, "3")):
        rows = await skins_of(uids[idx])
        check("%so holds exactly one reward skin" % place, len(rows) == 1, str(rows))
        rw_ = rows[0] if rows else {}
        check("...and it is the same design", rw_.get("glitch_id") == PRIZE_GID,
              str(rw_.get("glitch_id")))
        check("...with the standard per-win use allowance",
              int(rw_.get("uses") or 0) == server.GLITCH_USES_PER_WIN, str(rw_.get("uses")))
        check("...naming ITS OWN place in `source`",
              prev in str(rw_.get("source")) and place in str(rw_.get("source")),
              str(rw_.get("source")))
        check("...carrying NO render URL", rw_.get("image") == "", repr(rw_.get("image")))

    r = await receipt(prev)
    check("the receipt claimed the money rank", (r or {}).get("paid_ranks") == [1, 2, 3],
          str((r or {}).get("paid_ranks")))
    check("the receipt claimed the skin ranks SEPARATELY",
          sorted((r or {}).get("paid_skin_ranks") or []) == [1, 2, 3],
          str((r or {}).get("paid_skin_ranks")))

    tx = await db.transactions.find({"user_id": uids[0]}, {"_id": 0}).to_list(10)
    check("the money transaction label is unchanged",
          len(tx) == 1 and "1" in tx[0]["description"] and prev in tx[0]["description"],
          str(tx))


async def case_repeat_ticks_never_grant_twice():
    print("[case_repeat_ticks_never_grant_twice]")
    await reset()
    prev, uids = await seed_finished_season([("Champ", 900)])
    for _ in range(5):
        await server._leaderboard_rollover_tick()
    check("five ticks paid the coins once", await coins_of(uids[0]) == 5_000_000,
          str(await coins_of(uids[0])))
    won = await skins_of(uids[0])
    # Indexed defensively: a mutant that never grants must produce a NAMED
    # failure, not an IndexError that reads like a broken suite.
    check("five ticks granted the skin once",
          len(won) == 1 and int(won[0]["quantity"]) == 1, str(won))
    check("five ticks left one use allowance",
          len(won) == 1 and int(won[0]["uses"]) == server.GLITCH_USES_PER_WIN, str(won))


async def case_concurrent_ticks_never_grant_twice():
    print("[case_concurrent_ticks_never_grant_twice]")
    await reset()
    prev, uids = await seed_finished_season([("Champ", 900)])
    await asyncio.gather(*[server._leaderboard_rollover_tick() for _ in range(6)])
    check("six concurrent ticks paid the coins once",
          await coins_of(uids[0]) == 5_000_000, str(await coins_of(uids[0])))
    won = await skins_of(uids[0])
    check("six concurrent ticks granted the skin once",
          len(won) == 1 and int(won[0]["quantity"]) == 1, str(won))


async def case_a_failed_grant_retries_without_re_paying():
    print("[case_a_failed_grant_retries_without_re_paying]")
    await reset()
    prev, uids = await seed_finished_season([("Champ", 900)])

    real = server._grant_prize_skin
    calls = {"n": 0}

    async def boom(*a, **kw):
        calls["n"] += 1
        raise RuntimeError("mongo went away mid-grant")

    server._grant_prize_skin = boom
    try:
        await server._leaderboard_rollover_tick()
    finally:
        server._grant_prize_skin = real

    check("the coins landed even though the skin threw",
          await coins_of(uids[0]) == 5_000_000, str(await coins_of(uids[0])))
    check("no skin was granted", await skins_of(uids[0]) == [])
    r = await receipt(prev)
    check("the skin claim was HANDED BACK for the retry",
          (r or {}).get("paid_skin_ranks") in ([], None), str((r or {}).get("paid_skin_ranks")))
    check("the money claim was NOT handed back", (r or {}).get("paid_ranks") == [1],
          str((r or {}).get("paid_ranks")))

    # The dangerous direction: the retry must finish the skin and must NOT
    # re-pay the money. `last_awarded_season` already advanced, so the retry
    # comes from a fresh receipt read -- exactly what a restarted process does.
    await db.leaderboard_meta.update_one(
        {"key": "last_awarded_season"},
        {"$set": {"season_id": leaderboards.previous_season_id(prev)}})
    await server._leaderboard_rollover_tick()
    check("the retry granted the skin", len(await skins_of(uids[0])) == 1)
    check("the retry did NOT re-pay the coins",
          await coins_of(uids[0]) == 5_000_000, str(await coins_of(uids[0])))


async def case_one_places_grant_fails_the_others_still_land():
    """THE RISK THE 2026-08-18 WIDENING ADDED. With one rider a failed grant
    was simply retried. With three, a failure on the middle place must not
    take the other two down with it, must not re-pay anybody's money, and must
    hand back ONLY its own claim -- otherwise the next tick either re-grants a
    skin somebody already holds or leaves 2o empty for ever."""
    print("[case_one_places_grant_fails_the_others_still_land]")
    await reset()
    prev, uids = await seed_finished_season([("Champ", 900), ("Second", 500), ("Third", 100)])

    real = server._grant_prize_skin

    async def flaky(uid, gid, source):
        if uid == uids[1]:
            raise RuntimeError("mongo went away mid-grant")
        return await real(uid, gid, source)

    server._grant_prize_skin = flaky
    try:
        await server._leaderboard_rollover_tick()
    finally:
        server._grant_prize_skin = real

    check("1o still got its skin", len(await skins_of(uids[0])) == 1)
    check("3o still got its skin", len(await skins_of(uids[2])) == 1)
    check("2o got none (its grant threw)", await skins_of(uids[1]) == [])
    check("every place was still paid its money",
          await coins_of(uids[0]) == 5_000_000
          and await coins_of(uids[1]) == 3_000_000
          and await coins_of(uids[2]) == 1_000_000)
    r = await receipt(prev)
    check("ONLY the failed place handed its skin claim back",
          sorted((r or {}).get("paid_skin_ranks") or []) == [1, 3],
          str((r or {}).get("paid_skin_ranks")))
    check("no money claim was handed back",
          sorted((r or {}).get("paid_ranks") or []) == [1, 2, 3],
          str((r or {}).get("paid_ranks")))

    # the retry, exactly as a restarted process performs it
    await db.leaderboard_meta.update_one(
        {"key": "last_awarded_season"},
        {"$set": {"season_id": leaderboards.previous_season_id(prev)}})
    await server._leaderboard_rollover_tick()
    check("the retry finished 2o", len(await skins_of(uids[1])) == 1)
    still_one = []
    for u in (uids[0], uids[2]):
        rows = await skins_of(u)
        still_one.append(len(rows) == 1 and int(rows[0].get("quantity") or 0) == 1)
    check("...and did NOT hand 1o or 3o a second copy", all(still_one), str(still_one))
    check("...and did NOT re-pay anybody",
          await coins_of(uids[0]) == 5_000_000
          and await coins_of(uids[1]) == 3_000_000
          and await coins_of(uids[2]) == 1_000_000)


async def case_an_old_receipt_without_the_skin_key_still_grants():
    print("[case_an_old_receipt_without_the_skin_key_still_grants]")
    await reset()
    prev, uids = await seed_finished_season([("Champ", 900)])
    # A receipt exactly as the PREVIOUS build wrote it: no "skin" key anywhere.
    await db.leaderboard_awards.insert_one({
        "season_id": prev, "created_at": server.now_iso(), "paid_ranks": [],
        "winners": [{"rank": 1, "user_id": uids[0], "prize": 5_000_000}]})
    await server._leaderboard_rollover_tick()
    won = await skins_of(uids[0])
    check("a pre-upgrade receipt still grants the skin",
          len(won) == 1 and won[0]["glitch_id"] == PRIZE_GID, str(won))
    check("...and still pays the money exactly once",
          await coins_of(uids[0]) == 5_000_000, str(await coins_of(uids[0])))


async def case_champion_who_already_owns_it():
    print("[case_champion_who_already_owns_it]")
    await reset()
    prev, uids = await seed_finished_season([("Champ", 900)])
    await server._grant_prize_skin(uids[0], PRIZE_GID, "Caja")
    before = ((await skins_of(uids[0])) or [{}])[0]
    await server._leaderboard_rollover_tick()
    rows = await skins_of(uids[0])
    after = (rows or [{}])[0]
    check("owning it already does not crash the unique index", len(rows) == 1, str(rows))
    check("...quantity went up instead", int(after.get("quantity") or 0) == int(before.get("quantity") or 0) + 1,
          "%s -> %s" % (before.get("quantity"), after.get("quantity")))
    check("...and so did the use allowance",
          int(after.get("uses") or 0) == int(before.get("uses") or 0) + server.GLITCH_USES_PER_WIN,
          "%s -> %s" % (before.get("uses"), after.get("uses")))
    check("...the acquired_at of the original row is preserved",
          bool(before.get("acquired_at"))
          and after.get("acquired_at") == before.get("acquired_at"))
    check("...but `source` now names the prize",
          prev in str(after.get("source")), str(after.get("source")))


async def case_nobody_scored_pays_nothing():
    print("[case_nobody_scored_pays_nothing]")
    await reset()
    prev, uids = await seed_finished_season([("Zero", 0)])
    await server._leaderboard_rollover_tick()
    check("a zero-score season pays no coins", await coins_of(uids[0]) == 0)
    check("a zero-score season grants no skin", await skins_of(uids[0]) == [])
    r = await receipt(prev)
    check("the receipt holds no winners", ((r or {}).get("winners") or []) == [],
          str((r or {}).get("winners")))


async def case_first_boot_never_pays_history():
    print("[case_first_boot_never_pays_history]")
    await reset()
    sid = leaderboards.season_id()
    prev = leaderboards.previous_season_id(sid)
    uid = await mk_player("Champ", 900)
    await db.leaderboard_stats.insert_one({
        "id": server.new_id(), "user_id": uid, "season_id": prev,
        "kills_month": 0, "deaths_month": 0, "quests_month": 0,
        "playtime_seconds_month": 0, "score": 900, "updated_at": server.now_iso()})
    # No last_awarded_season doc at all = a fresh install.
    await server._leaderboard_rollover_tick()
    check("a fresh install grants no skin for a season that predates it",
          await skins_of(uid) == [])
    check("...and pays no coins", await coins_of(uid) == 0)


async def case_an_unknown_design_refuses_instead_of_granting_nothing():
    print("[case_an_unknown_design_refuses_instead_of_granting_nothing]")
    await reset()
    uid = await mk_player("Champ", 900)
    ok = await server._grant_prize_skin(uid, "no-such-design", "test")
    check("an unknown id returns False", ok is False, str(ok))
    check("...and writes no row", await skins_of(uid) == [])
    check("a real id returns True",
          await server._grant_prize_skin(uid, PRIZE_GID, "test") is True)


async def case_the_public_hub_carries_the_card():
    print("[case_the_public_hub_carries_the_card]")
    await reset()
    hub = await server.leaderboards_hub()
    check("prizes are unchanged", hub["prizes"] == {"1": 5_000_000, "2": 3_000_000, "3": 1_000_000},
          str(hub["prizes"]))
    cards = hub.get("prize_skins") or {}
    check("the hub carries a card for the whole podium",
          set(cards) == {"1", "2", "3"}, str(set(cards)))
    # every card is checked, not just the one that existed before the widening
    for place in ("1", "2", "3"):
        card = cards.get(place) or {}
        check("%so names the design" % place, card.get("name") == "Supernova",
              str(card.get("name")))
        check("...with no picture", card.get("image") == "", repr(card.get("image")))
        check("...with a full 7-slot proximity strip",
              len(card.get("proximity") or []) == 7, str(card.get("proximity")))
        blob = repr(card)
        leaked = [v for v in ("-999999", "-9999999", "22000", "variation", "payload") if v in blob]
        check("...and no channel of the paid recipe on the public wire",
              leaked == [], str(leaked))


async def case_the_wire_command_is_his_payload():
    print("[case_the_wire_command_is_his_payload]")
    cmd = glitch_catalog.build_glitch_command(PRIZE_GID, "A", "C", "7656", female=False)
    owner = {
        "variation": 8.0, "pattern": 2,
        "body": [-999999.0, -9999999.0, -9999999.0, -999.0],
        "markings": [-9999999.0, -999999.0, -9999.0, -999889.0],
        "flank": [25.0, 4.0, 25.0, -99999.0],
        "underbelly": [-999999.0, -99999999.0, -9999999.0, -999.0],
        "detail1": [-999999.0, -999999.0, -999999.0, -999667.0],
        "eyes": [255.0, -999999.0, 60.0, 22000.0],
        "male_display": [-9999998.0, 1987.0, 1019.0, -999.0],
    }
    for k, want in owner.items():
        check("the wire carries his %s verbatim" % k, cmd[k] == want,
              "%r != %r" % (cmd[k], want))


async def main():
    for case in (case_champion_wins_coins_and_the_skin,
                 case_repeat_ticks_never_grant_twice,
                 case_concurrent_ticks_never_grant_twice,
                 case_a_failed_grant_retries_without_re_paying,
                 case_one_places_grant_fails_the_others_still_land,
                 case_an_old_receipt_without_the_skin_key_still_grants,
                 case_champion_who_already_owns_it,
                 case_nobody_scored_pays_nothing,
                 case_first_boot_never_pays_history,
                 case_an_unknown_design_refuses_instead_of_granting_nothing,
                 case_the_public_hub_carries_the_card,
                 case_the_wire_command_is_his_payload):
        await case()
    print()
    if FAIL:
        print("%d FAILURE(S): %s" % (FAIL, _FAILED))
    else:
        print("ALL OK - %d checks passed" % PASS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        stop_mongo()
    sys.exit(1 if FAIL else 0)
