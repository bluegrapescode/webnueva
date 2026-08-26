# -*- coding: utf-8 -*-
"""Nublar Spin (daily wheel) gate -- REAL mongod, REAL route handlers, REAL
concurrency, REAL sqlite vault (the casino settle-race harness, reused).

What must be true before the wheel ships (owner ask 2026-08-23):
  * spins/day = 1 + Patreon rank (juvie..apex = +1..+5), ONLY for active_patron;
  * N concurrent spins pay EXACTLY the allowance, never one more (the casino
    settle-race law: claims are single-document conditional writes);
  * the same cmd_id replayed N times is ONE spin, ONE reward, ONE op doc;
  * the day key moves forward only (a backward clock cannot re-pay a day);
  * a grant that fails hands the spin back and is visible by name;
  * every plate pays into the REAL lane: crate currency, Battle Pass token
    rows the BP redeem accepts, reward_skins upsert, vault parked_dinos rows
    with class-legal mutations, the Vial consumable + gen0_state at 100;
  * the vial refuses while already infected/zombie and is never consumed on a
    refusal, and a stack of vials fired at once consumes exactly one;
  * admin saves are judged on the MERGED table and refuse unpayable tables.

Run:  C:\\Python312\\python.exe tests_local\\test_wheel_daily.py
      C:\\Python312\\python.exe tests_local\\test_wheel_daily.py --mutants

Exit codes: 0 all pass / 1 a check failed / 2 the suite could NOT run (no mongod)
-- 2 is never a pass, a suite that did not run is a failed read.
"""
import argparse
import asyncio
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))

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
TMP = tempfile.mkdtemp(prefix="lin_wheel_test_")


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
os.environ["DB_NAME"] = "lin_wheel_test_%s" % uuid.uuid4().hex[:8]
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ.setdefault("RCON_HOST", "")
os.environ.setdefault("ALLOW_DEMO_LOGIN", "0")
os.environ.setdefault("DISCORD_BOT_TOKEN", "bot-token-fake")
os.environ.setdefault("DISCORD_GUILD_ID", "1523167556368859286")

# ---- temp vault DB, wired before vault first connects (test_battle_pass shape)
_DB_PATH = os.path.join(TMP, "laislanublar.db")
_SAVED = os.path.join(TMP, "Saved")
os.makedirs(_SAVED, exist_ok=True)


def _make_vault_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE parked_dinos (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             steam_id TEXT, discord_id TEXT, dino_class TEXT, growth REAL,
             health REAL, max_health REAL, stamina REAL, max_stamina REAL,
             hunger REAL, max_hunger REAL, thirst REAL, max_thirst REAL,
             oxygen REAL, max_oxygen REAL, x REAL, y REAL, z REAL,
             is_prime INTEGER, is_elder INTEGER, mutations TEXT,
             parent_mutations TEXT, elder_mutations TEXT, elder_stacks INTEGER,
             skin_code TEXT, skin_data TEXT, diet_a REAL, diet_b REAL, diet_c REAL,
             parked_at TEXT, redeem_pending_cmd_id TEXT, redeem_pending_at INTEGER)""")
    conn.commit()
    conn.close()


_make_vault_db(_DB_PATH)

sys.path.insert(0, BACKEND)
import game_ipc  # noqa: E402

game_ipc.BOT_DB_PATH = _DB_PATH
game_ipc.SAVED_DIR = _SAVED

import vault  # noqa: E402

vault.ensure_prime_state_columns()

import server  # noqa: E402
import wheel_routes as wr  # noqa: E402
import battle_pass  # noqa: E402
import glitch_catalog  # noqa: E402
import mutation_catalog  # noqa: E402
from fastapi import HTTPException  # noqa: E402

db = server.db


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _uid():
    return uuid.uuid4().hex


async def mk_user(**over):
    uid = _uid()
    doc = {"id": uid, "steam_id": "7656119%09d" % (int(uid[:8], 16) % 10**9),
           "persona_name": "Tester-" + uid[:4], "avatar": None,
           "coins": 0, "vip_coins": 0, "role": "user", "created_at": server.now_iso()}
    doc.update(over)
    await db.users.insert_one(dict(doc))
    return await db.users.find_one({"id": uid}, {"_id": 0})


async def fresh(uid):
    return await db.users.find_one({"id": uid}, {"_id": 0})


async def set_config(**over):
    """Write a config straight into Mongo (the admin lane is tested on its own)."""
    cfg = wr.default_config()
    cfg.update(over)
    cfg.pop("revision", None)
    await db.wheel_config.update_one({"_id": wr.CONFIG_ID}, {"$set": cfg}, upsert=True)
    return cfg


def only(kind, **extra):
    """A one-plate table: every spin lands on `kind` (deterministic grant tests)."""
    seg = dict(next(s for s in wr.DEFAULT_SEGMENTS if s["kind"] == kind))
    seg.update(extra)
    seg["weight"] = 100
    return [seg]


async def spin(user, cmd=None):
    cmd = cmd or ("t-" + uuid.uuid4().hex[:12])
    return await wr.wheel_spin(wr.SpinIn(cmd_id=cmd), user)


async def spin_code(user, cmd=None):
    try:
        r = await spin(user, cmd)
        return 200, r
    except HTTPException as e:
        return e.status_code, e.detail
    except Exception as e:  # planted crashes / pydantic refusals
        return 599, repr(e)


async def parked_rows(sid):
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM parked_dinos WHERE steam_id=?", (sid,))]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# the suite
# ---------------------------------------------------------------------------
async def t_allowance():
    print("[allowance]")
    cfg = wr.default_config()
    check("non-patron = 1", wr.allowance_for({}, cfg)["allowance"] == 1)
    check("gifted_no_charge apex = 1 (paid perk stays paid)",
          wr.allowance_for({"patreon_patron_status": "gifted_no_charge",
                            "patreon_tier_name": "Apex"}, cfg)["allowance"] == 1)
    for name, want in (("Juvie", 2), ("Sub Adult", 3), ("Adult", 4), ("Elder", 5), ("Apex", 6)):
        got = wr.allowance_for({"patreon_patron_status": "active_patron",
                                "patreon_tier_name": name}, cfg)
        check("active %s = %d" % (name, want), got["allowance"] == want, got)
    got = wr.allowance_for({"patreon_patron_status": "active_patron",
                            "patreon_tier_name": "\U0001fa77 Sub Adult"}, cfg)
    check("decorated 'Sub Adult' is rank 2 (3 spins), not Adult", got["allowance"] == 3, got)
    got = wr.allowance_for({"patreon_patron_status": "active_patron",
                            "patreon_tier_name": "Megalodon"}, cfg)
    check("unknown active tier = 1", got["allowance"] == 1, got)
    cfg2 = dict(cfg, patreon_bonus=False)
    got = wr.allowance_for({"patreon_patron_status": "active_patron",
                            "patreon_tier_name": "Apex"}, cfg2)
    check("patreon_bonus knob off -> apex = base 1", got["allowance"] == 1, got)
    cfg3 = dict(cfg, base_spins=0)
    check("base_spins 0 -> 0 daily (bonus lane only)",
          wr.allowance_for({}, cfg3)["allowance"] == 0)
    check("base_spins is clamped to MAX", wr._coerce_config({"base_spins": 999})["base_spins"] == wr.MAX_BASE_SPINS)
    check("corrupt segments type falls back to defaults",
          len(wr._coerce_config({"segments": "nope"})["segments"]) == len(wr.DEFAULT_SEGMENTS))


async def t_config_seed():
    print("[config singleton]")
    await db.wheel_config.delete_many({})
    cfgs = await asyncio.gather(*[wr._get_config() for _ in range(12)])
    n = await db.wheel_config.count_documents({})
    check("12 concurrent first reads seed ONE _id=wheel_config doc", n == 1, n)
    check("seeded table is the shipped one", len(cfgs[0]["segments"]) == len(wr.DEFAULT_SEGMENTS))
    pubs = wr.public_segments(cfgs[0]["segments"])
    total = sum(p["probability"] for p in pubs)
    check("public odds sum to ~100 over the whole table", abs(total - 100.0) < 0.2, total)
    check("no weight leaves the server", all("weight" not in p for p in pubs))
    one = wr._public_one(cfgs[0]["segments"][0], cfgs[0]["segments"])
    check("a single plate reports its TABLE odds, never 100%", one["probability"] == pubs[0]["probability"], one)
    check("table is payable as shipped", wr.payability_errors(cfgs[0]) == [], wr.payability_errors(cfgs[0]))


async def t_spin_race():
    print("[concurrent distinct spins = exactly the allowance]")
    await set_config(segments=only("primemeat", amount=1000))
    u = await mk_user(patreon_patron_status="active_patron", patreon_tier_name="Sub Adult")
    res = await asyncio.gather(*[spin_code(u) for _ in range(14)])
    ok = [r for r in res if r[0] == 200]
    refused = [r for r in res if r[0] == 429]
    check("exactly 3 of 14 paid (allowance 3)", len(ok) == 3, [r[0] for r in res])
    check("the other 11 refused 429 NO_SPINS", len(refused) == 11 and all(r[1]["code"] == "NO_SPINS" for r in refused))
    f = await fresh(u["id"])
    check("users.wheel_spins_today == 3", f.get("wheel_spins_today") == 3, f.get("wheel_spins_today"))
    check("coins == 3 * 1000 exactly", f.get("coins") == 3000, f.get("coins"))
    n_ops = await db.wheel_spins.count_documents({"user_id": u["id"], "status": "granted"})
    check("3 granted op docs", n_ops == 3, n_ops)
    n_tx = await db.transactions.count_documents({"user_id": u["id"], "type": "reward"})
    check("3 ledger rows", n_tx == 3, n_tx)
    check("answer carries fairness proof + table snapshot",
          all("server_seed_hash" in r[1]["fairness"] and len(r[1]["segments"]) == 1 for r in ok))
    check("429 carries next_reset + used/allowance", all(r[1].get("next_reset") and r[1].get("allowance") == 3 for r in refused))


async def t_rollover_loser_retries_same_day():
    print("[rollover loser retries today's atomic allowance]")

    class Result:
        def __init__(self, modified):
            self.modified_count = modified

    class FakeUsers:
        def __init__(self):
            self.calls = []

        async def update_one(self, query, update):
            self.calls.append((query, update))
            # 1: our first same-day try saw no day yet. 2: another request won
            # rollover first. 3: today's retry claims one remaining allowance.
            return Result(1 if len(self.calls) == 3 else 0)

    class FakeDb:
        def __init__(self):
            self.users = FakeUsers()

    old_db = wr._db
    fake = FakeDb()
    wr._db = fake
    today = wr.today_key()
    try:
        lane = await wr.claim_spin({"id": "u-rollover", "wheel_day": None}, today, 3)
    finally:
        wr._db = old_db
    third = fake.users.calls[2][0] if len(fake.users.calls) >= 3 else {}
    check("a request that loses rollover retries the remaining daily allowance",
          lane == "daily" and len(fake.users.calls) == 3
          and third.get("wheel_day") == today
          and third.get("wheel_spins_today") == {"$lt": 3},
          (lane, fake.users.calls))


async def t_replay():
    print("[same cmd_id replayed = one spin]")
    await set_config(segments=only("primemeat", amount=700))
    u = await mk_user()
    cmd = "replay-" + uuid.uuid4().hex[:8]
    res = await asyncio.gather(*[spin_code(u, cmd) for _ in range(8)])
    codes = sorted(r[0] for r in res)
    ok = [r for r in res if r[0] == 200]
    pend = [r for r in res if r[0] == 409 and r[1].get("code") == "PENDING"]
    check("8 identical requests: >=1 paid, the rest PENDING (409), nothing else",
          len(ok) >= 1 and len(ok) + len(pend) == 8, codes)
    keys = {r[1]["op_key"] for r in ok}
    check("one op_key", len(keys) == 1, keys)
    n_ops = await db.wheel_spins.count_documents({"user_id": u["id"]})
    check("one op doc", n_ops == 1, n_ops)
    f = await fresh(u["id"])
    check("coins == 700 once", f.get("coins") == 700, f.get("coins"))
    check("spins_today == 1 (duplicates never reached the claim)", f.get("wheel_spins_today") == 1, f.get("wheel_spins_today"))
    r2 = await spin(u, cmd)
    check("a later replay says replayed=True with the same reward", r2.get("replayed") is True and r2["reward"]["amount"] == 700)
    code, d = await spin_code(u)
    check("a NEW cmd_id after the daily spin refuses 429", code == 429, code)
    cmd2 = "refused-" + uuid.uuid4().hex[:8]
    code, d = await spin_code(u, cmd2)
    code2, d2 = await spin_code(u, cmd2)
    check("replaying a refused cmd_id answers the SAME refusal", code == 429 and code2 == 429 and d2["code"] == "NO_SPINS", (code, code2))
    # an op whose owner died before claiming (status new, stale) is retaken
    u3 = await mk_user()
    old = (datetime.now(timezone.utc) - timedelta(seconds=wr.GRANTING_STALE_S + 5)).isoformat()
    cmd3 = "stale-" + uuid.uuid4().hex[:8]
    await db.wheel_spins.insert_one({"_id": "lin:wheel:%s:%s" % (u3["id"], cmd3), "user_id": u3["id"],
                                     "status": "new", "at": old})
    code, d = await spin_code(u3, cmd3)
    check("a stale 'new' op is retaken and completes", code == 200 and d["reward"]["amount"] == 700, (code, d))
    cmd4 = "live-" + uuid.uuid4().hex[:8]
    await db.wheel_spins.insert_one({"_id": "lin:wheel:%s:%s" % (u3["id"], cmd4), "user_id": u3["id"],
                                     "status": "new", "at": server.now_iso()})
    code, d = await spin_code(u3, cmd4)
    check("a fresh in-flight 'new' op answers PENDING", code == 409 and d["code"] == "PENDING", (code, d))


async def t_day_rollover():
    print("[day key: forward only]")
    await set_config(segments=only("primemeat", amount=10))
    today = wr.today_key()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    u = await mk_user(wheel_day=yesterday, wheel_spins_today=1)
    code, r = await spin_code(u)
    check("yesterday's used spin does not block today (rollover)", code == 200, (code, r))
    f = await fresh(u["id"])
    check("rollover wrote today + spins_today 1", f.get("wheel_day") == today and f.get("wheel_spins_today") == 1, f)
    u2 = await mk_user(wheel_day=tomorrow, wheel_spins_today=1)
    code, r = await spin_code(u2)
    check("a stored FUTURE day (clock went forward then back) cannot re-pay today", code == 429, (code, r))
    f2 = await fresh(u2["id"])
    check("future day untouched", f2.get("wheel_day") == tomorrow and f2.get("wheel_spins_today") == 1, f2)
    u3 = await mk_user(wheel_day=None)
    code, _ = await spin_code(u3)
    check("wheel_day None = never played -> first spin", code == 200, code)


async def t_bonus_lane():
    print("[bonus spins]")
    await set_config(segments=only("primemeat", amount=5))
    u = await mk_user(wheel_bonus_spins=2)
    r1 = await spin(u)
    check("daily first: lane=daily", r1["lane"] == "daily", r1["lane"])
    u = await fresh(u["id"])
    res = await asyncio.gather(*[spin_code(u) for _ in range(10)])
    ok = [r for r in res if r[0] == 200]
    check("exactly 2 bonus spins paid out of 10 concurrent", len(ok) == 2 and all(r[1]["lane"] == "bonus" for r in ok), [r[0] for r in res])
    f = await fresh(u["id"])
    check("bonus counter never negative", f.get("wheel_bonus_spins") == 0, f.get("wheel_bonus_spins"))
    check("spin_count == 3", f.get("wheel_spin_count") == 3, f.get("wheel_spin_count"))
    st = wr._status_view(f, await wr._get_config())
    check("status: can_spin False, used 1/1, bonus 0", st["can_spin"] is False and st["used_today"] == 1 and st["bonus_spins"] == 0, st)


async def t_grant_failure_restores():
    print("[grant failure hands the spin back, by name]")
    await set_config(segments=only("primemeat", amount=5))
    u = await mk_user()
    real = wr.grant

    async def boom(*a, **k):
        raise RuntimeError("planted grant failure")
    wr.grant = boom
    try:
        cmd = "fail-" + uuid.uuid4().hex[:8]
        code, d = await spin_code(u, cmd)
        check("failed grant answers 500", code == 500, (code, d))
        f = await fresh(u["id"])
        check("spin handed back (spins_today 0)", (f.get("wheel_spins_today") or 0) == 0, f.get("wheel_spins_today"))
        row = await db.wheel_spins.find_one({"_id": "lin:wheel:%s:%s" % (u["id"], cmd)})
        check("op row says grant_failed with the error named", row["status"] == "grant_failed" and "planted" in row.get("error", ""), row)
        code, d = await spin_code(u, cmd)
        check("replaying the failed cmd_id -> 409 GRANT_FAILED (spin again)", code == 409 and d["code"] == "GRANT_FAILED", (code, d))
    finally:
        wr.grant = real
    code, r = await spin_code(u)
    check("a fresh cmd_id spins normally afterwards", code == 200, code)
    f = await fresh(u["id"])
    check("exactly one paid spin on the books", f.get("wheel_spins_today") == 1 and f.get("coins") == 5, f)


async def t_drawn_resume():
    print("[an op that died between draw and grant resumes once]")
    await set_config(segments=only("primemeat", amount=11))
    u = await mk_user()
    cmd = "drawn-" + uuid.uuid4().hex[:8]
    real_settle = wr._settle

    async def die(*a, **k):
        raise RuntimeError("planted crash before grant")
    wr._settle = die
    try:
        code, d = await spin_code(u, cmd)
        check("first attempt crashed (planted)", code != 200)
    finally:
        wr._settle = real_settle
    row = await db.wheel_spins.find_one({"_id": "lin:wheel:%s:%s" % (u["id"], cmd)})
    check("op doc left in 'drawn'", row and row["status"] == "drawn", row and row["status"])
    res = await asyncio.gather(*[spin_code(u, cmd) for _ in range(5)])
    ok = [r for r in res if r[0] == 200]
    pend = [r for r in res if r[0] == 409 and r[1].get("code") == "PENDING"]
    check("5 concurrent replays: exactly ONE finishes the grant, the rest PENDING",
          len(ok) == 1 and len(pend) == 4, [r[0] for r in res])
    code, d = await spin_code(u, cmd)
    check("the next replay answers the recorded win", code == 200 and d.get("replayed") is True, (code, d))
    f = await fresh(u["id"])
    check("paid exactly once", f.get("coins") == 11, f.get("coins"))
    granted = await db.wheel_spins.count_documents({"user_id": u["id"], "status": "granted"})
    check("one granted op", granted == 1, granted)


async def t_switches():
    print("[switches + payability before any claim]")
    await set_config(enabled=False)
    u = await mk_user()
    code, d = await spin_code(u)
    check("disabled -> 400 WHEEL_DISABLED", code == 400 and d == "WHEEL_DISABLED", (code, d))
    await set_config(segments=only("dino_basic"), dino_pools={"basic": ["not-a-species"], "prime": []})
    code, d = await spin_code(u)
    check("unpayable table -> 503 BEFORE any claim", code == 503, (code, d))
    f = await fresh(u["id"])
    check("nothing was claimed", (f.get("wheel_spins_today") or 0) == 0 and (f.get("wheel_spin_count") or 0) == 0, f)
    await set_config(segments=[dict(only("primemeat")[0], weight=0)])
    code, d = await spin_code(u)
    check("all-zero weights -> 503, not a uniform draw", code == 503, (code, d))
    code, d = await spin_code(u, "x")
    check("cmd_id too short refused by the model", code in (400, 422, 599), code)
    f = await fresh(u["id"])
    check("a refused spin claimed nothing", (f.get("wheel_spins_today") or 0) == 0, f)


async def t_grant_tokens():
    print("[tokens = real Battle Pass rows]")
    for kind, flavor, item_id in (("growth_token", "basic", "bp_token_growth_basic"),
                                  ("growth_token", "premium", "bp_token_growth_premium"),
                                  ("diet_token", "basic", "bp_token_diet_basic")):
        await set_config(segments=only(kind, flavor=flavor))
        u = await mk_user()
        r = await spin(u)
        row = await db.inventory.find_one({"user_id": u["id"], "category": "Tokens"}, {"_id": 0})
        check("%s/%s -> %s with token+token_tier" % (kind, flavor, item_id),
              row and row["item_id"] == item_id and row["token"] in ("growth", "diet") and row["token_tier"] == flavor, row)
        check("answer names the token", r["reward"]["kind"] == kind and r["reward"]["inv_id"] == row["id"], r["reward"])


async def t_grant_glitch():
    print("[glitch skin = reward_skins upsert, crate-eligible pool]")
    await set_config(segments=only("glitch_skin"))
    pool = wr.glitch_pool()
    check("pool is the crate-eligible family", pool and all(glitch_catalog.crate_eligible(g) for g in pool), pool)
    u = await mk_user(wheel_bonus_spins=5)
    rewards = []
    for _ in range(6):
        u = await fresh(u["id"])
        r = await spin(u)
        rewards.append(r["reward"])
    rows = await db.reward_skins.find({"user_id": u["id"]}, {"_id": 0}).to_list(50)
    total_q = sum(int(x.get("quantity") or 0) for x in rows)
    check("6 wins = 6 quantity across (user, glitch) rows (no twins)", total_q == 6 and len(rows) == len({x["glitch_id"] for x in rows}), rows)
    check("uses accrue GLITCH_USES_PER_WIN per win",
          all(int(x["uses"]) == int(x["quantity"]) * server.GLITCH_USES_PER_WIN for x in rows), rows)
    check("every won id is in the pool and the answer carries name + proximity (no picture)",
          all(rw["glitch_id"] in pool and rw.get("name") and "proximity" in rw for rw in rewards), rewards[0])


async def t_grant_dino():
    print("[dinos = vault.save_parked, store payload, cap ignored]")
    for kind in ("dino_basic", "dino_prime"):
        await set_config(segments=only(kind))
        u = await mk_user()
        r = await spin(u)
        rows = await parked_rows(u["steam_id"])
        check("%s -> one parked_dinos row" % kind, len(rows) == 1, rows)
        row = rows[0]
        prime = kind == "dino_prime"
        pool = wr.resolve_pool(wr.default_config(), "prime" if prime else "basic")
        cls = row["dino_class"]
        check("class is from the %s pool" % kind, cls in {wr._CLASS_BY_SLUG[s] for s in pool}, cls)
        check("growth 0.75", abs(float(row["growth"]) - 0.75) < 1e-9, row["growth"])
        check("is_prime/is_elder == %s" % prime, bool(row["is_prime"]) == prime and bool(row["is_elder"]) == prime, row)
        muts = [m for m in (row["mutations"] or "").split("|") if m and m != "None"]
        allowed = mutation_catalog.allowed_names_for_class(cls)
        check("%d mutations, all legal for the class, distinct" % (4 if prime else 3),
              len(muts) == (4 if prime else 3) and all(m in allowed for m in muts) and len(set(muts)) == len(muts), muts)
        check("diet %s" % ("300%" if prime else "150%"),
              abs(float(row["diet_a"]) - (1.0 if prime else 0.5)) < 1e-9, row["diet_a"])
        check("elder_stacks stays 0 (no elder replication minted)", int(row["elder_stacks"] or 0) == 0, row["elder_stacks"])
        check("answer names species + vault row", r["reward"]["vault_row"] == row["id"] and r["reward"]["name"], r["reward"])
        if prime:
            check("prime state minted (prime_conditions present)",
                  any(k.startswith("prime_") and row.get(k) not in (None, "") for k in row.keys()), {k: row[k] for k in row if k.startswith("prime_")})
    # replay determinism: the same op_key rerolls nothing
    a = wr.pick_mutations("BP_Carnotaurus_C", 4, "lin:wheel:u:cmd", "BP_Carnotaurus_C")
    b = wr.pick_mutations("BP_Carnotaurus_C", 4, "lin:wheel:u:cmd", "BP_Carnotaurus_C")
    c = wr.pick_mutations("BP_Carnotaurus_C", 4, "lin:wheel:u:other", "BP_Carnotaurus_C")
    check("mutation pick is seeded by the op key (same op = same picks)", a == b and a != c, (a, c))
    # a crowded vault still receives the prize (cap ignored)
    await set_config(segments=only("dino_basic"))
    u = await mk_user()
    conn = sqlite3.connect(_DB_PATH)
    for _ in range(30):
        conn.execute("INSERT INTO parked_dinos (steam_id, discord_id, dino_class, growth) VALUES (?,?,?,?)",
                     (u["steam_id"], "", "BP_Hypsilophodon_C", 0.5))
    conn.commit()
    conn.close()
    code, r = await spin_code(u)
    check("a Bóveda with 30 dinos still receives the won one (cap=0)", code == 200 and len(await parked_rows(u["steam_id"])) == 31, code)
    # no steam id -> grant fails -> spin restored
    u = await mk_user(steam_id="")
    code, d = await spin_code(u)
    f = await fresh(u["id"])
    check("no steam_id: dino grant refuses, spin handed back", code == 500 and (f.get("wheel_spins_today") or 0) == 0, (code, f.get("wheel_spins_today")))


async def t_vial():
    print("[Vial GEN-Ø]")
    await set_config(segments=only("gen0_vial"))
    u = await mk_user(wheel_bonus_spins=1)
    r1 = await spin(u)
    u = await fresh(u["id"])
    r2 = await spin(u)
    vials = await db.inventory.find({"user_id": u["id"], "item_id": wr.VIAL_ITEM_ID}, {"_id": 0}).to_list(10)
    check("two wins stack into ONE row, quantity 2", len(vials) == 1 and vials[0]["quantity"] == 2 and vials[0]["category"] == "Consumables", vials)
    inv_id = vials[0]["id"]
    # not mine
    other = await mk_user()
    try:
        await wr.wheel_use_vial(wr.VialIn(inv_id=inv_id), other)
        check("another user cannot use my vial", False)
    except HTTPException as e:
        check("another user cannot use my vial (404)", e.status_code == 404, e.status_code)
    # no steam
    nosteam = await mk_user(steam_id="")
    await db.inventory.insert_one({"id": "v-" + nosteam["id"], "user_id": nosteam["id"], "item_id": wr.VIAL_ITEM_ID,
                                   "name": "Vial GEN-Ø", "category": "Consumables", "quantity": 1})
    try:
        await wr.wheel_use_vial(wr.VialIn(inv_id="v-" + nosteam["id"]), nosteam)
        check("no steam -> refused", False)
    except HTTPException as e:
        left = await db.inventory.find_one({"id": "v-" + nosteam["id"]})
        check("no steam -> 400 and the vial is kept", e.status_code == 400 and left["quantity"] == 1, e.status_code)
    # eligible use
    res = await wr.wheel_use_vial(wr.VialIn(inv_id=inv_id), u)
    st = await db.gen0_state.find_one({"steam_id": u["steam_id"]}, {"_id": 0})
    v = await db.inventory.find_one({"id": inv_id}, {"_id": 0})
    check("use -> gen0_state percent 100 (doc minted with claims {})", res["success"] and st["percent"] == 100 and st.get("claims") == {}, st)
    check("one vial consumed, one left", v and v["quantity"] == 1, v)
    # already at 100: refused BEFORE consuming
    try:
        await wr.wheel_use_vial(wr.VialIn(inv_id=inv_id), u)
        check("already 100% -> refused", False)
    except HTTPException as e:
        v = await db.inventory.find_one({"id": inv_id}, {"_id": 0})
        check("already 100% -> 400 and the vial is kept", e.status_code == 400 and v["quantity"] == 1, (e.status_code, v))
    # zombie_active refusal
    await db.gen0_state.update_one({"steam_id": u["steam_id"]}, {"$set": {"percent": 40, "zombie_active": True}})
    try:
        await wr.wheel_use_vial(wr.VialIn(inv_id=inv_id), u)
        check("walking zombie -> refused", False)
    except HTTPException as e:
        check("walking zombie -> 400, vial kept", e.status_code == 400 and (await db.inventory.find_one({"id": inv_id}))["quantity"] == 1, e.status_code)
    # race: a stack of 3 vials, 8 concurrent uses -> exactly one consumed
    await db.gen0_state.update_one({"steam_id": u["steam_id"]}, {"$set": {"percent": 75, "zombie_active": False}})
    await db.inventory.update_one({"id": inv_id}, {"$set": {"quantity": 3}})
    outs = await asyncio.gather(*[wr.wheel_use_vial(wr.VialIn(inv_id=inv_id), u) for _ in range(8)], return_exceptions=True)
    oks = [o for o in outs if isinstance(o, dict)]
    vrows = await db.inventory.find({"user_id": u["id"], "item_id": wr.VIAL_ITEM_ID}, {"_id": 0}).to_list(10)
    left = sum(int(x.get("quantity") or 0) for x in vrows)
    st = await db.gen0_state.find_one({"steam_id": u["steam_id"]}, {"_id": 0})
    n_docs = await db.gen0_state.count_documents({"steam_id": u["steam_id"]})
    check("8 concurrent uses: exactly 1 consumed, 2 left, percent 100, ONE gen0 doc",
          len(oks) == 1 and left == 2 and st["percent"] == 100 and n_docs == 1, (len(oks), left, st and st["percent"], n_docs))
    inv_id = vrows[0]["id"]
    await db.inventory.update_one({"id": inv_id}, {"$set": {"quantity": 1}})
    for extra in vrows[1:]:
        await db.inventory.delete_one({"id": extra["id"]})
    # the existing facility fields survive
    await db.gen0_state.update_one({"steam_id": u["steam_id"]}, {"$set": {"percent": 50, "claims": {"F1": "x"}, "cooldown_until_ms": 123}})
    await wr.wheel_use_vial(wr.VialIn(inv_id=inv_id), u)
    st = await db.gen0_state.find_one({"steam_id": u["steam_id"]}, {"_id": 0})
    check("a vial on a partial bar keeps claims + cooldown (only percent moves)",
          st["percent"] == 100 and st["claims"] == {"F1": "x"} and st["cooldown_until_ms"] == 123, st)


async def t_admin():
    print("[admin]")
    owner = await mk_user(role="owner")
    await set_config()
    base = await wr.wheel_admin_config(owner)
    check("admin config carries species, glitch pool, kinds, rank ladder, problems=[]",
          base["species"] and base["glitch_pool"] and base["kinds"] == list(wr.KINDS) and base["patreon_rank"]["apex"] == 5 and base["problems"] == [], base.get("problems"))

    async def save(**body):
        try:
            return 200, await wr.wheel_admin_save(wr.ConfigIn(**body), owner)
        except HTTPException as e:
            return e.status_code, e.detail
        except Exception as e:  # pydantic
            return 422, str(e)

    code, d = await save(segments=[{"kind": "lottery", "label": "x", "amount": 1, "weight": 1}])
    check("unknown kind -> 400", code == 400, (code, d))
    code, d = await save(segments=[{"kind": "primemeat", "label": "x", "amount": -5, "weight": 1}])
    check("negative amount refused", code in (400, 422), code)
    code, d = await save(segments=[{"kind": "primemeat", "label": "x", "amount": 10, "weight": 0}])
    check("all-zero weights refused", code == 400, (code, d))
    code, d = await save(segments=[{"kind": "primemeat", "label": "x", "amount": 10, "weight": 1, "color": "red"}])
    check("bad colour refused", code == 400, (code, d))
    code, d = await save(segments=[{"kind": "primemeat", "label": "a", "amount": 10, "weight": 1, "key": "k"},
                                   {"kind": "amberium", "label": "b", "amount": 10, "weight": 1, "key": "k"}])
    check("duplicate keys refused", code == 400, (code, d))
    code, d = await save(dino_pools={"basic": ["trex", "nope"]})
    check("unknown species in a pool refused", code == 400, (code, d))
    code, d = await save(dino_pools={"basic": []}, segments=wr.DEFAULT_SEGMENTS)
    check("a save that would leave a dino plate unpayable is refused on the MERGED table", code == 400, (code, d))
    code, d = await save(enabled=False, dino_pools={"basic": []})
    check("...but the same save with the wheel OFF is accepted (fix it while closed)", code == 200, (code, d))
    code, d = await save(enabled=True)
    check("re-enabling with the empty pool is refused", code == 400, (code, d))
    code, d = await save(dino_pools={"basic": ["hypsi", "dryo"]}, enabled=True)
    check("pool restored + enabled -> 200", code == 200 and d["dino_pools"]["basic"] == ["hypsi", "dryo"], (code, d if code != 200 else d["dino_pools"]))
    code, d = await save(base_spins=2)
    cfg = await wr._get_config()
    check("partial save keeps the segments", code == 200 and cfg["base_spins"] == 2 and len(cfg["segments"]) == len(wr.DEFAULT_SEGMENTS), (code, cfg["base_spins"]))
    check("revision increments once per ACCEPTED save (3 so far; refusals don't count)", cfg["revision"] == 3, cfg["revision"])
    logs = await db.logs.count_documents({"action": "wheel_config"}) if "logs" in await db.list_collection_names() else -1
    check("owner saves are audit-logged", logs != 0, logs)
    code, d = await save(segments=[{"kind": "primemeat", "label": "x", "amount": 10, "weight": 1}] * 25)
    check("more than MAX_SEGMENTS refused", code == 400, code)
    # grant spins
    u = await mk_user()
    r = await wr.wheel_admin_grant_spins(wr.GrantSpinsIn(user_id=u["id"], amount=3, reason="test"), owner)
    check("gift 3 bonus spins", r["bonus_spins"] == 3, r)
    try:
        await wr.wheel_admin_grant_spins(wr.GrantSpinsIn(user_id=u["id"], amount=-5), owner)
        check("taking back more than held refused", False)
    except HTTPException as e:
        check("taking back more than held refused (400)", e.status_code == 400, e.status_code)
    r = await wr.wheel_admin_grant_spins(wr.GrantSpinsIn(user_id=u["id"], amount=-3), owner)
    check("take back exactly 3 -> 0", r["bonus_spins"] == 0, r)
    try:
        await wr.wheel_admin_grant_spins(wr.GrantSpinsIn(user_id="nobody", amount=1), owner)
        check("unknown user refused", False)
    except HTTPException as e:
        check("unknown user refused (404)", e.status_code == 404, e.status_code)
    r = await wr.wheel_admin_reset(owner)
    check("reset restores the shipped table", len(r["segments"]) == len(wr.DEFAULT_SEGMENTS) and r["base_spins"] == 1, r["base_spins"])
    # a player cannot reach the owner lane
    player = await mk_user()
    try:
        await server.get_owner_user(player)
        check("player is not an owner", False)
    except HTTPException as e:
        check("owner dependency refuses a player (403)", e.status_code == 403, e.status_code)


async def t_code_spin_rewards():
    print("[promo-code spin rewards]")
    for bad in (-1, 101, True, 1.5, "3"):
        try:
            server.RewardModel(spins=bad)
            check("promo-code spins refuse %r" % bad, False)
        except Exception:
            check("promo-code spins refuse %r" % bad, True)

    u = await mk_user(wheel_bonus_spins=2)
    granted = await server.apply_reward(u["id"], {"spins": 3}, "focused test")
    f = await fresh(u["id"])
    check("apply_reward adds promo spins to the bonus lane",
          f.get("wheel_bonus_spins") == 5 and granted.get("spins") == 3,
          (f.get("wheel_bonus_spins"), granted))
    check("public user rows expose the stored bonus balance",
          server.public_user(f).get("wheel_bonus_spins") == 5,
          server.public_user(f).get("wheel_bonus_spins"))
    malformed = dict(f, wheel_bonus_spins="not-a-number")
    check("a malformed legacy balance cannot crash the user list",
          server.public_user(malformed).get("wheel_bonus_spins") == 0,
          server.public_user(malformed).get("wheel_bonus_spins"))

    u2 = await mk_user()
    code_id = "spin-code-" + uuid.uuid4().hex[:8]
    await db.codes.insert_one({
        "id": code_id, "code": "SPIN" + uuid.uuid4().hex[:8].upper(),
        "name": "Spin reward", "active": True, "max_uses": 1,
        "per_user": 1, "uses": 0, "reward": {"spins": 4},
        "created_at": server.now_iso(),
    })
    code = await db.codes.find_one({"id": code_id})
    out = await server.redeem_code(server.RedeemInput(code=code["code"]), u2)
    f2 = await fresh(u2["id"])
    receipt = await db.code_redemptions.find_one({"code_id": code_id, "user_id": u2["id"]})
    check("redeeming a spin code grants and reports four spins",
          out["granted"]["spins"] == 4 and f2.get("wheel_bonus_spins") == 4,
          (out, f2.get("wheel_bonus_spins")))
    check("the redemption receipt preserves the spin reward",
          (receipt or {}).get("granted", {}).get("spins") == 4, receipt)

    u3 = await mk_user()
    bad_id = "bad-spin-code-" + uuid.uuid4().hex[:8]
    bad_code = "BADSPIN" + uuid.uuid4().hex[:6].upper()
    await db.codes.insert_one({
        "id": bad_id, "code": bad_code, "name": "Bad spin reward",
        "active": True, "max_uses": 1, "per_user": 1, "uses": 0,
        "reward": {"spins": 101}, "created_at": server.now_iso(),
    })
    try:
        await server.redeem_code(server.RedeemInput(code=bad_code), u3)
        check("a malformed stored reward is refused", False)
    except HTTPException as e:
        check("a malformed stored reward is refused before payout", e.status_code == 500, e.status_code)
    bad_after = await db.codes.find_one({"id": bad_id})
    u3_after = await fresh(u3["id"])
    check("a malformed stored reward burns no use and grants no spin",
          bad_after.get("uses") == 0 and (u3_after.get("wheel_bonus_spins") or 0) == 0,
          (bad_after.get("uses"), u3_after.get("wheel_bonus_spins")))


async def t_history_immutable():
    print("[history keeps the plate as drawn]")
    await set_config(segments=only("primemeat", amount=42, label="Cuarenta y dos"))
    u = await mk_user()
    await spin(u)
    await set_config(segments=only("primemeat", amount=1, label="Otra cosa"))
    h = await wr.wheel_history(u)
    row = h["history"][0]
    check("history row keeps label/amount as drawn after a config edit",
          row["segment"]["label"] == "Cuarenta y dos" and row["reward"]["amount"] == 42, row)
    check("history has no user id / op key", "user_id" not in row and "_id" not in row, list(row.keys()))
    st = wr._status_view(await fresh(u["id"]), await wr._get_config())
    check("status shape", set(["can_spin", "allowance", "used_today", "left_today", "bonus_spins", "next_reset", "tier_key"]) <= set(st.keys()), st.keys())


# ---------------------------------------------------------------------------
# mutants — each MUST turn a check red, or the check proves nothing
# ---------------------------------------------------------------------------
async def mutant_read_then_write():
    """The bundle's shape: read eligibility, then write. Race test must go RED."""
    real = wr.claim_spin

    async def bad(user, today, allowance):
        f = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        used = wr.spins_used_today(f, today)
        if used < allowance:
            await asyncio.sleep(0.01)
            await db.users.update_one({"id": user["id"]}, {"$set": {"wheel_day": today, "wheel_spins_today": used + 1},
                                                           "$inc": {"wheel_spin_count": 1}})
            return "daily"
        return None
    wr.claim_spin = bad
    try:
        await t_spin_race()
    finally:
        wr.claim_spin = real


async def mutant_day_ne():
    """Rollover filter `$ne today` instead of forward-only `$lt`: the future-day
    test must go RED."""
    real = wr.claim_spin

    async def bad(user, today, allowance):
        r = await db.users.update_one({"id": user["id"], "wheel_day": {"$ne": today}},
                                      {"$set": {"wheel_day": today, "wheel_spins_today": 1},
                                       "$inc": {"wheel_spin_count": 1}})
        if r.modified_count == 1:
            return "daily"
        return await real(user, today, allowance)
    wr.claim_spin = bad
    try:
        await t_day_rollover()
    finally:
        wr.claim_spin = real


class _Gen0Mutant:
    """`db.gen0_state` is a NEW Motor collection object on every attribute
    access, so the mutant has to sit in front of the database handle the
    module holds, not on one collection instance."""

    def __init__(self, real_db, drop_read, drop_filter):
        self._real = real_db
        self._drop_read = drop_read
        self._drop_filter = drop_filter

    def __getattr__(self, name):
        coll = getattr(self._real, name)
        if name != "gen0_state":
            return coll
        me = self

        class _Coll:
            def __getattr__(self, n):
                return getattr(coll, n)

            async def find_one(self, flt, *a, **kw):
                if me._drop_read and set(flt.keys()) == {"steam_id"} and a and a[0].get("zombie_active") == 1:
                    return None  # "never infected" — the read belt is gone
                return await coll.find_one(flt, *a, **kw)

            async def update_one(self, flt, upd, **kw):
                if me._drop_filter and "steam_id" in flt and "$set" in upd and upd["$set"].get("percent") == 100:
                    flt = {"steam_id": flt["steam_id"]}
                return await coll.update_one(flt, upd, **kw)
        return _Coll()


async def mutant_vial_unguarded():
    """Both vial belts removed — the cheap eligibility READ and the write's
    own filter: the already-100% / walking-zombie checks must go RED (the
    vial gets consumed and a zombie's bar gets rewritten)."""
    real = wr._db
    wr._db = _Gen0Mutant(real, drop_read=True, drop_filter=True)
    try:
        await t_vial()
    finally:
        wr._db = real


async def mutant_vial_write_only():
    """Only the READ belt removed: the write filter alone must still hold
    every vial check GREEN (this one is a control — it must NOT go red)."""
    real = wr._db
    wr._db = _Gen0Mutant(real, drop_read=True, drop_filter=False)
    try:
        await t_vial()
    finally:
        wr._db = real


async def main(mutants=False):
    global PASS, FAIL, _FAILED
    check("precondition: mongod answers", (await db.command("ping")).get("ok") == 1.0)
    await wr.ensure_indexes()
    idx = await db.gen0_state.index_information()
    check("gen0_state.steam_id unique index built", any(v.get("unique") and v["key"][0][0] == "steam_id" for v in idx.values()), list(idx))
    if mutants:
        results = {}
        for name, fn, want_red in (("read-then-write claim", mutant_read_then_write, True),
                                   ("day key $ne instead of $lt", mutant_day_ne, True),
                                   ("vial: both belts removed", mutant_vial_unguarded, True),
                                   ("vial: read belt removed, write filter alone (control)", mutant_vial_write_only, False)):
            PASS, FAIL, _FAILED = 0, 0, []
            print("\n=== MUTANT: %s ===" % name)
            try:
                await fn()
            except Exception as e:
                FAIL += 1
                print("  (mutant raised %r — counts as RED)" % e)
            results[name] = (FAIL > 0, want_red)
        print("\nMUTANTS:")
        allok = True
        for name, (red, want_red) in results.items():
            ok = red == want_red
            print("  %s %s%s" % ("RED  " if red else "GREEN", name, "" if ok else "   <-- WRONG"))
            allok = allok and ok
        return 0 if allok else 1
    for t in (t_allowance, t_config_seed, t_spin_race, t_rollover_loser_retries_same_day,
              t_replay, t_day_rollover, t_bonus_lane,
              t_grant_failure_restores, t_drawn_resume, t_switches, t_grant_tokens, t_grant_glitch,
              t_grant_dino, t_vial, t_admin, t_code_spin_rewards, t_history_immutable):
        try:
            await t()
        except Exception as e:
            import traceback
            traceback.print_exc()
            check("%s did not crash" % t.__name__, False, repr(e))
    print("\n%d passed, %d failed" % (PASS, FAIL))
    for n in _FAILED:
        print("  - " + n)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", action="store_true")
    args = ap.parse_args()
    try:
        rc = asyncio.run(main(mutants=args.mutants))
    finally:
        stop_mongo()
    sys.exit(rc)
