# -*- coding: utf-8 -*-
"""Creator Program gate -- REAL mongod, REAL handlers (2026-08-17).

The owner's system: a creator's code pays creator 50.000 / referred player
25.000 PrimeMeat once the referred player has REALLY joined the island
(linked Steam + minimum minutes played); milestones pay one-time bonuses;
the exclusive catalog design "leyenda-creador" lands at skin_target; the
monthly top 3 win 1M/500K/250K PrimeMeat + "supernova" (owner order
2026-08-18: "supernova for 123 place in leaderboard and constelacion for
battlepass only" -- the pink glitter held these places from 08-17 until
that order made it Battle Pass only, so the podium swapped to Supernova
rather than going empty).

Why a REAL mongod: every payout in this lane is claim-gated ($addToSet /
find_one_and_update filters + the unique referred_user_id index). A fake
would be free to get claim semantics subtly wrong while the close loop and
the sweep re-run forever in production.

WHAT IS PINNED (the dangerous directions, each proven CORRECT, not merely
non-crashing):
  * a player supports ANY number of creators, each creator's code exactly ONCE
    (owner order 2026-08-18) - 409 on a repeat of the SAME creator, and the
    (player, creator) unique index settles the race;
  * the PLAYER's welcome bonus is paid ONCE per player and the CREATOR is paid
    every time - including under a race, under the admin knob, and for players
    who were already paid under the old one-code rule (the backfill);
  * self-referral / creator-as-referred / unknown / suspended codes refused;
  * a player who has not PLAYED yet stays PENDING (with the Spanish reason)
    and the sweep pays them only once playtime crosses the bar;
  * concurrent validation of one referral pays exactly once;
  * milestone bonus pays exactly once under concurrency;
  * the exclusive skin lands ONCE as a real reward_skins doc and never again;
  * a paused creator earns NOTHING while held, earns after reactivation;
  * burst >= 5/h pauses + one alert;
  * monthly close: exact prizes, supernova to ranks 1/2/3, idempotent
    across re-runs AND across a crash that loses the marker; the HoF snapshot
    is never overwritten; counters reset; a fresh install ADOPTS the previous
    month (history is never paid);
  * demo seeding refuses without the env arm; CSV cells are formula-guarded;
  * the exclusive design is crate-ineligible and payload-distinct.

Run:  <python312>\python.exe tests_local\test_creator_program.py
Exit: 0 all pass / 1 a check failed / 2 the suite could NOT run (no mongod)
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
# mongod (portable, temp dbpath)
# ---------------------------------------------------------------------------
PORTABLE_MONGOD = r"C:\LaIslaNublarWeb\_localtest\mongodb-7.0.28\mongodb-win32-x86_64-windows-7.0.28\bin\mongod.exe"
_mongo_proc = None
TMP = tempfile.mkdtemp(prefix="lin_cp_")


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
os.environ["DB_NAME"] = "lin_cp_%s" % uuid.uuid4().hex[:8]
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ.setdefault("RCON_HOST", "")
os.environ.setdefault("ALLOW_DEMO_LOGIN", "0")
os.environ.setdefault("DISCORD_BOT_TOKEN", "bot-token-fake")
os.environ.setdefault("DISCORD_GUILD_ID", "1523167556368859286")
os.environ.pop("LIN_CREATOR_DEMO", None)

sys.path.insert(0, BACKEND)
import server  # noqa: E402
import creator_program as cp_mod  # noqa: E402
import glitch_catalog  # noqa: E402
from fastapi import HTTPException  # noqa: E402

db = server.db

EXCL_GID = "leyenda-creador"
# 2026-08-18 owner order. Was "constelacion" from 08-17; "battlepass only"
# is an exclusivity claim, and a podium still paying it would be a second
# door onto the design, so the two halves of that sentence are one change.
PRIZE_GID = "supernova"
PASS_ONLY_GID = "constelacion"


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, host="10.0.0.1"):
        self.client = _FakeClient(host)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
async def reset():
    for coll in ("users", "creators", "referrals", "creator_settings",
                 "creator_notifications", "hall_of_fame", "creator_alerts",
                 "reward_skins", "transactions"):
        await db[coll].delete_many({})
    server._cp_visit_hits.clear()
    await server._cp_ensure_indexes()
    await db.reward_skins.create_index([("user_id", 1), ("glitch_id", 1)], unique=True)


async def mk_user(uid, steam=None, playtime=0, coins=0, persona=None):
    doc = {"id": uid, "steam_id": steam, "persona_name": persona or uid,
           "avatar": None, "coins": coins, "vip_coins": 0,
           "playtime_minutes": playtime, "role": "user", "created_at": server.now_iso()}
    await db.users.insert_one(dict(doc))
    return doc


async def mk_creator(uid, code, **over):
    doc = {"id": server.new_id(), "user_id": uid, "code": code,
           "status": cp_mod.CREATOR_ACTIVE, "display_name": code,
           "total_referrals": 0, "monthly_referrals": 0,
           "total_prime_meat_earned": 0, "monthly_prime_meat_earned": 0,
           "exclusive_skin_unlocked": False, "stages_reached": [],
           "code_visits_total": 0, "code_visits_month": {},
           "current_month": cp_mod.month_id(),
           "created_at": server.now_iso(), "updated_at": server.now_iso()}
    doc.update(over)
    await db.creators.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def _cp_settings_set(**kw):
    await server._cp_get_settings()          # make sure the doc exists
    await db.creator_settings.update_one({"id": "settings"}, {"$set": dict(kw)})


async def coins_of(uid):
    u = await db.users.find_one({"id": uid})
    return int((u or {}).get("coins") or 0)


async def apply_code(user_doc, code):
    return await server.creator_apply_code(
        body=server.CpApplyCodeIn(code=code), user=user_doc)


def expect_http(status):
    class _Ctx:
        def __init__(self):
            self.got = None

        def __enter__(self):
            return self

        def __exit__(self, et, ev, tb):
            if et is HTTPException and ev.status_code == status:
                self.got = ev
                return True
            return False
    return _Ctx()


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------
async def t_catalog_entry():
    print("[catalog] the exclusive design")
    g = glitch_catalog.GLITCH_BY_ID.get(EXCL_GID)
    check("exclusive in catalog", bool(g))
    check("crate ineligible", glitch_catalog.crate_eligible(EXCL_GID) is False)
    check("not in GLITCH_SKINS (crate pool source list)",
          all(x["id"] != EXCL_GID for x in glitch_catalog.GLITCH_SKINS))
    check("not in BP_SKINS", all(x["id"] != EXCL_GID for x in glitch_catalog.BP_SKINS))
    keys = ("body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display")
    pl = [tuple(g["payload"][k]) for k in keys]
    dup = [o["id"] for o in glitch_catalog.GLITCH_SKINS + glitch_catalog.BP_SKINS
           if [tuple(o["payload"][k]) for k in keys] == pl]
    check("payload distinct from every other design", dup == [], str(dup))
    don = glitch_catalog.GLITCH_BY_ID["constelacion"]["payload"]
    same = all(sorted(g["payload"][k][:3]) == sorted(don[k][:3])
               and g["payload"][k][3] == don[k][3] for k in keys)
    check("donor A values verbatim per slot (R3 method)", same)
    check("proximity strip renders", len(glitch_catalog.design_proximity(g)["strip"]) > 0)
    cmd = glitch_catalog.build_glitch_command(EXCL_GID, "BP_Rex_C_1", "BP_Rex_C", "765x", False)
    check("build_glitch_command resolves it", isinstance(cmd, dict))
    check("prize config validated at import",
          server.CP_PRIZE_SKIN_BY_RANK == {1: PRIZE_GID, 2: PRIZE_GID, 3: PRIZE_GID})
    # the other half of the 2026-08-18 order, gated at THIS door too
    check("the pass-only design is not a creator prize any more",
          PASS_ONLY_GID not in server.CP_PRIZE_SKIN_BY_RANK.values())
    check("the pass-only design cannot be won from a crate either",
          glitch_catalog.crate_eligible(PASS_ONLY_GID) is False
          and any(x["id"] == PASS_ONLY_GID for x in glitch_catalog.BP_SKINS))
    check("the creator podium skin is NOT itself pass-exclusive",
          not glitch_catalog.GLITCH_BY_ID[PRIZE_GID].get("bp_exclusive"))


async def t_apply_happy():
    print("[apply] happy path: played player -> both sides paid")
    await reset()
    cu = await mk_user("u_creator", steam="76561198000000001", playtime=999)
    c = await mk_creator("u_creator", "GHESSY")
    pu = await mk_user("u_player", steam="76561198000000002", playtime=30)
    out = await apply_code(pu, "ghessy")   # lowercase in, normalized
    check("status REWARDED", out["status"] == cp_mod.STATUS_REWARDED, out)
    check("creator +50000", await coins_of("u_creator") == 50_000)
    check("player +25000", await coins_of("u_player") == 25_000)
    r = await db.referrals.find_one({"referred_user_id": "u_player"})
    check("referral doc rewarded", r and r["status"] == cp_mod.STATUS_REWARDED
          and r["reward_amount"] == 50_000 and r["player_reward_amount"] == 25_000)
    tx = await db.transactions.find({"user_id": "u_creator"}).to_list(10)
    check("creator tx labeled", any(t["type"] == "creator_reward" for t in tx))
    fresh = await db.creators.find_one({"id": c["id"]})
    check("creator counters", fresh["total_referrals"] == 1 and fresh["monthly_referrals"] == 1
          and fresh["total_prime_meat_earned"] == 50_000)


async def t_apply_pending_then_sweep():
    print("[apply] not played yet -> PENDING with reason; sweep pays after playtime")
    await reset()
    await mk_user("u_c2", steam="76561198000000011", playtime=999)
    await mk_creator("u_c2", "CODE2")
    pu = await mk_user("u_p2", steam="76561198000000012", playtime=0)
    out = await apply_code(pu, "CODE2")
    check("status PENDING", out["status"] == cp_mod.STATUS_PENDING)
    check("Spanish pending reason present", "minutos" in (out.get("pending_reason") or ""))
    check("nobody paid yet", await coins_of("u_c2") == 0 and await coins_of("u_p2") == 0)
    # playtime rises -> the sweep's per-user path pays
    await db.users.update_one({"id": "u_p2"}, {"$set": {"playtime_minutes": 15}})
    u = await db.users.find_one({"id": "u_p2"})
    got = await server._cp_try_validate_for_user(u)
    check("sweep path rewards once played", bool(got))
    check("player paid after playing", await coins_of("u_p2") == 25_000)


async def t_apply_refusals():
    print("[apply] refusal edges")
    await reset()
    await mk_user("u_c3", steam="76561198000000021", playtime=999)
    await mk_creator("u_c3", "CODE3")
    await mk_user("u_c3b", steam="76561198000000022", playtime=999)
    await mk_creator("u_c3b", "CODE3B", status=cp_mod.CREATOR_SUSPENDED)
    pu = await mk_user("u_p3", steam="76561198000000023", playtime=60)
    with expect_http(400):
        await apply_code(pu, "!!bad code!!")
        check("invalid code 400", False)
    with expect_http(404):
        await apply_code(pu, "NOSUCH")
        check("unknown code 404", False)
    with expect_http(404):
        await apply_code(pu, "CODE3B")
        check("suspended code 404", False)
    cu = await db.users.find_one({"id": "u_c3"})
    with expect_http(400):
        await apply_code(cu, "CODE3")
        check("self referral 400", False)
    cub = await db.users.find_one({"id": "u_c3b"})
    with expect_http(400):
        await apply_code(cub, "CODE3")
        check("creator-as-referred 400", False)
    check("refusal edges raised", True)
    out = await apply_code(pu, "CODE3")
    check("then applies fine", out["success"] is True)
    pu = await db.users.find_one({"id": "u_p3"})
    with expect_http(409):
        await apply_code(pu, "CODE3")
        check("the SAME creator twice 409s", False)
    check("one code PER CREATOR enforced", await db.referrals.count_documents({}) == 1)
    # ★ The pair check moved BELOW the code lookup on 2026-08-18, which fixed a
    #   real wrong answer: an already-referred player typing a code that does not
    #   exist used to be told "already used" instead of "no such code".
    with expect_http(404):
        await apply_code(pu, "STILLNOSUCH")
        check("an unknown code still 404s AFTER the player has referrals", False)
    check("refusal ordering pinned", True)


async def t_my_referral_pending_reason():
    print("[my-referral] pending shows the TRUE requirement, never a stale steam sentence")
    await reset()
    await mk_user("u_mr_c", steam="76561198000000201", playtime=999)
    await mk_creator("u_mr_c", "MRCODE")
    # signed-in-with-Steam player who has not played yet -> PLAY sentence
    pu = await mk_user("u_mr_p", steam="76561198000000202", playtime=3)
    await apply_code(pu, "MRCODE")
    out = await server.creator_my_referral(user=await db.users.find_one({"id": "u_mr_p"}))
    check("pending carries play sentence", "jug" in (out.get("pending_reason") or "").lower()
          and "Steam" not in (out.get("pending_reason") or ""), out.get("pending_reason"))
    check("need/have minutes on the wire", out.get("pending_need_minutes") == 10
          and out.get("pending_have_minutes") == 3)
    check("pending shows the configured bonus", out.get("player_reward_next") == 25_000)
    # account with NO real steam -> steam sentence survives for that rare case
    nu = await mk_user("u_mr_n", steam="demo_tester", playtime=50)
    rid = server.new_id()
    c = await db.creators.find_one({"code": "MRCODE"})
    await db.referrals.insert_one({
        "id": rid, "creator_id": c["id"], "referred_user_id": "u_mr_n",
        "code": "MRCODE", "status": cp_mod.STATUS_PENDING,
        "month": cp_mod.month_id(), "created_at": server.now_iso()})
    out2 = await server.creator_my_referral(user=await db.users.find_one({"id": "u_mr_n"}))
    check("no-steam edge keeps steam sentence", "Steam" in (out2.get("pending_reason") or ""))
    # rewarded -> no pending fields
    await db.users.update_one({"id": "u_mr_p"}, {"$set": {"playtime_minutes": 15}})
    await server._cp_try_validate_for_user(await db.users.find_one({"id": "u_mr_p"}))
    out3 = await server.creator_my_referral(user=await db.users.find_one({"id": "u_mr_p"}))
    check("rewarded drops pending fields", out3.get("status") == cp_mod.STATUS_REWARDED
          and "pending_reason" not in out3 and out3.get("reward_amount") == 25_000)


async def t_island_presence_lane():
    print("[island] presence on the live roster pays the code with the website CLOSED")
    await reset()
    import game_ipc as _gi
    real_reader = _gi.read_players_positions_fresh
    try:
        await mk_user("u_is_c", steam="76561198000000301", playtime=999)
        c = await mk_creator("u_is_c", "ISLAND")
        # player NEVER opens the site after applying: web playtime stays 0
        pu = await mk_user("u_is_p", steam="76561198000000302", playtime=0)
        out = await apply_code(pu, "ISLAND")
        check("starts PENDING at zero web minutes", out["status"] == cp_mod.STATUS_PENDING)
        # 1) stale/dead roster file => the sweep credits NOBODY
        _gi.read_players_positions_fresh = lambda max_age_s=90: None
        await server._cp_sweep_pending_once()
        r = await db.referrals.find_one({"referred_user_id": "u_is_p"})
        check("stale roster earns nothing", int(r.get("play_minutes") or 0) == 0
              and r["status"] == cp_mod.STATUS_PENDING)
        # 2) player ON the island: one sweep pass = one credit
        _gi.read_players_positions_fresh = lambda max_age_s=90: {"76561198000000302": {"x": 1}}
        await server._cp_sweep_pending_once()
        r = await db.referrals.find_one({"referred_user_id": "u_is_p"})
        check("one pass credits the interval", int(r.get("play_minutes") or 0) == 5
              and r.get("last_seen_ingame_at"))
        # my-referral now reports the ISLAND minutes (web still 0)
        mr = await server.creator_my_referral(user=await db.users.find_one({"id": "u_is_p"}))
        check("card counts island minutes", mr.get("pending_have_minutes") == 5
              and "(llevás 5)" in (mr.get("pending_reason") or ""))
        # 3) MAX not SUM: bump web to 7 — still under 10, one more island pass pays
        await db.users.update_one({"id": "u_is_p"}, {"$set": {"playtime_minutes": 7}})
        await server._cp_sweep_pending_once()
        r = await db.referrals.find_one({"referred_user_id": "u_is_p"})
        check("island lane alone reaches the bar and pays",
              r["status"] == cp_mod.STATUS_REWARDED and int(r.get("play_minutes") or 0) == 10)
        check("both sides paid", await coins_of("u_is_c") == 50_000
              and await coins_of("u_is_p") == 25_000)
        # 4) web lane still validates on its own (site-open players unpunished)
        await mk_user("u_is_p2", steam="76561198000000303", playtime=60)
        u2 = await db.users.find_one({"id": "u_is_p2"})
        out2 = await apply_code(u2, "ISLAND")
        check("web lane still instant", out2["status"] == cp_mod.STATUS_REWARDED)
    finally:
        _gi.read_players_positions_fresh = real_reader


async def t_concurrent_single_pay():
    print("[race] concurrent validation of one referral pays once")
    await reset()
    await mk_user("u_c4", steam="76561198000000031", playtime=999)
    c = await mk_creator("u_c4", "CODE4")
    await mk_user("u_p4", steam="76561198000000032", playtime=60)
    rid = server.new_id()
    await db.referrals.insert_one({
        "id": rid, "creator_id": c["id"], "referred_user_id": "u_p4",
        "code": "CODE4", "status": cp_mod.STATUS_PENDING,
        "month": cp_mod.month_id(), "created_at": server.now_iso()})
    res = await asyncio.gather(*[server._cp_validate_and_reward(rid) for _ in range(6)])
    paid = [r for r in res if r]
    check("exactly one winner", len(paid) == 1, str(len(paid)))
    check("creator paid once", await coins_of("u_c4") == 50_000)
    check("player paid once", await coins_of("u_p4") == 25_000)


async def t_milestone_and_skin():
    print("[milestones] one-time bonuses + the exclusive skin grant")
    await reset()
    await mk_user("u_c5", steam="76561198000000041", playtime=999)
    c = await mk_creator("u_c5", "CODE5")
    await db.creator_settings.delete_many({})
    s = await server._cp_get_settings()
    await db.creator_settings.update_one({"id": "settings"}, {"$set": {"skin_target": 10}})
    # walk 10 referrals through the real lane, SPREAD IN TIME (backdating each
    # rewarded_at right after it pays keeps the burst window at 1 — the burst
    # gate itself is proven in its own test below)
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    old_ts = (_dt.now(_tz.utc) - _td(hours=3)).isoformat()
    for i in range(10):
        uid = "u_p5_%d" % i
        await mk_user(uid, steam="7656119800000005%d" % i, playtime=60)
        u = await db.users.find_one({"id": uid})
        await apply_code(u, "CODE5")
        await db.referrals.update_many({"creator_id": c["id"]},
                                       {"$set": {"rewarded_at": old_ts}})
    fresh = await db.creators.find_one({"id": c["id"]})
    check("10 referrals counted", fresh["total_referrals"] == 10)
    check("juvie milestone recorded once", fresh["stages_reached"] == ["juvie"])
    tx = await db.transactions.find({"user_id": "u_c5", "type": "creator_milestone"}).to_list(50)
    check("milestone bonus paid once", len(tx) == 1 and tx[0]["amount"] == 7_500)
    check("skin flag set", fresh["exclusive_skin_unlocked"] is True)
    doc = await db.reward_skins.find_one({"user_id": "u_c5", "glitch_id": EXCL_GID})
    check("exclusive skin doc granted", doc and doc["quantity"] == 1
          and doc["uses"] == server.GLITCH_USES_PER_WIN)
    check("skin source names the program", "Creadores" in (doc or {}).get("source", ""))
    # replay the last referral's validate -> nothing moves
    last = await db.referrals.find_one({"referred_user_id": "u_p5_9"})
    again = await server._cp_validate_and_reward(last["id"])
    doc2 = await db.reward_skins.find_one({"user_id": "u_c5", "glitch_id": EXCL_GID})
    check("replay grants nothing", again is None and doc2["quantity"] == 1
          and doc2["uses"] == doc["uses"])
    # coins: 10 * 50k + 7.5k bonus
    check("creator total exact", await coins_of("u_c5") == 507_500,
          await coins_of("u_c5"))


async def t_burst_pause_and_recovery():
    print("[abuse] burst pauses at 5/h; a held creator earns nothing; reactivation pays the queue")
    await reset()
    await mk_user("u_c6", steam="76561198000000061", playtime=999)
    c = await mk_creator("u_c6", "CODE6")
    for i in range(5):
        uid = "u_p6_%d" % i
        await mk_user(uid, steam="7656119800000006%d" % i, playtime=60)
        u = await db.users.find_one({"id": uid})
        await apply_code(u, "CODE6")
    fresh = await db.creators.find_one({"id": c["id"]})
    check("paused after 5 in an hour", server._cp_paused_active(fresh) is True,
          fresh.get("paused_until"))
    alerts = await db.creator_alerts.find({"creator_id": c["id"]}).to_list(10)
    check("exactly one alert", len(alerts) == 1)
    # 6th player: applies -> stays PENDING (held creator earns nothing)
    await mk_user("u_p6_x", steam="76561198000000699", playtime=60)
    ux = await db.users.find_one({"id": "u_p6_x"})
    out = await apply_code(ux, "CODE6")
    check("6th stays PENDING while paused", out["status"] == cp_mod.STATUS_PENDING, out)
    check("6th not paid", await coins_of("u_p6_x") == 0)
    before = await coins_of("u_c6")
    # admin reactivates via the alert action
    admin = {"id": "admin1", "role": "admin"}
    await server.creator_admin_alerts_action(
        body=server.CpAlertActionIn(alert_id=alerts[0]["id"], action="reactivate"), admin=admin)
    got = await server._cp_try_validate_for_user(ux)
    check("queue pays after reactivation", bool(got))
    check("creator resumed earning", await coins_of("u_c6") == before + 50_000)
    # expired pause also releases (no admin needed)
    await db.creators.update_one({"id": c["id"]},
                                 {"$set": {"paused_until": "2020-01-01T00:00:00+00:00"}})
    fresh = await db.creators.find_one({"id": c["id"]})
    check("expired pause reads unpaused", server._cp_paused_active(fresh) is False)
    # ...and an expired stamp does NOT immunize against a NEW burst pause:
    # push the recent-rewards window hot again and reward one more referral.
    from datetime import datetime as _dt2, timezone as _tz2
    hot = _dt2.now(_tz2.utc).isoformat()
    await db.referrals.update_many({"creator_id": c["id"], "status": cp_mod.STATUS_REWARDED},
                                   {"$set": {"rewarded_at": hot}})
    await mk_user("u_p6_y", steam="76561198000000698", playtime=60)
    uy = await db.users.find_one({"id": "u_p6_y"})
    await apply_code(uy, "CODE6")
    fresh = await db.creators.find_one({"id": c["id"]})
    check("re-pause after expiry works", server._cp_paused_active(fresh) is True,
          fresh.get("paused_until"))


async def t_monthly_close():
    print("[close] exact prizes + supernova to 1/2/3, idempotent across re-runs and lost marker")
    await reset()
    current = cp_mod.month_id()
    prev = server._cp_prev_month(current)
    for i, (uid, code, monthly) in enumerate(
            [("u_m1", "TOPONE", 40), ("u_m2", "TOPTWO", 30), ("u_m3", "TOPTHREE", 20),
             ("u_m4", "FOURTH", 10)]):
        await mk_user(uid, steam="7656119800000007%d" % i, playtime=999)
        await mk_creator(uid, code, monthly_referrals=monthly,
                         total_referrals=monthly, current_month=prev)
    # settings exist with marker != prev (a month actually elapsed)
    await server._cp_get_settings()
    await db.creator_settings.update_one({"id": "settings"},
                                         {"$set": {"last_closed_month": server._cp_prev_month(prev)}})
    await server._cp_close_month_if_needed()
    check("prizes exact", await coins_of("u_m1") == 1_000_000
          and await coins_of("u_m2") == 500_000 and await coins_of("u_m3") == 250_000)
    check("4th unpaid", await coins_of("u_m4") == 0)
    for uid in ("u_m1", "u_m2", "u_m3"):
        doc = await db.reward_skins.find_one({"user_id": uid, "glitch_id": PRIZE_GID})
        check("podium skin granted %s" % uid, doc and doc["quantity"] == 1)
    check("4th got no skin",
          await db.reward_skins.find_one({"user_id": "u_m4", "glitch_id": PRIZE_GID}) is None)
    hof = await db.hall_of_fame.find_one({"month": prev})
    check("HoF doc", hof and len(hof["top"]) == 3 and hof["top"][0]["code"] == "TOPONE"
          and hof["top"][0]["prize_skin"] == PRIZE_GID)
    check("claims recorded", sorted(hof.get("paid_ranks") or []) == [1, 2, 3]
          and sorted(hof.get("skin_paid_ranks") or []) == [1, 2, 3])
    m1 = await db.creators.find_one({"user_id": "u_m1"})
    check("counters reset + month adopted", m1["monthly_referrals"] == 0
          and m1["current_month"] == current)
    # re-run: nothing moves
    await server._cp_close_month_if_needed()
    check("re-run pays nothing", await coins_of("u_m1") == 1_000_000)
    # crash shape: the marker is lost AFTER payments -> re-run still pays nothing
    await db.creator_settings.update_one({"id": "settings"},
                                         {"$set": {"last_closed_month": server._cp_prev_month(prev)}})
    await server._cp_close_month_if_needed()
    d1 = await db.reward_skins.find_one({"user_id": "u_m1", "glitch_id": PRIZE_GID})
    check("lost-marker re-run pays nothing", await coins_of("u_m1") == 1_000_000
          and d1["quantity"] == 1 and d1["uses"] == server.GLITCH_USES_PER_WIN)
    hof2 = await db.hall_of_fame.find_one({"month": prev})
    check("HoF snapshot never clobbered", len(hof2["top"]) == 3
          and hof2["closed_at"] == hof["closed_at"])


async def t_first_boot_adoption():
    print("[close] a fresh install adopts the previous month (history never paid)")
    await reset()
    await mk_user("u_a1", steam="76561198000000091", playtime=999)
    prev = server._cp_prev_month(cp_mod.month_id())
    await mk_creator("u_a1", "OLDGUY", monthly_referrals=99, total_referrals=99,
                     current_month=prev)
    # no settings doc at all = first boot
    await server._cp_close_month_if_needed()
    check("no HoF for the un-run month", await db.hall_of_fame.find_one({"month": prev}) is None)
    check("nobody paid", await coins_of("u_a1") == 0)
    s = await db.creator_settings.find_one({"id": "settings"})
    check("marker adopted", s and s.get("last_closed_month") == prev)
    a1 = await db.creators.find_one({"user_id": "u_a1"})
    check("stale counters healed anyway", a1["monthly_referrals"] == 0)


async def t_public_surfaces():
    print("[public] leaderboard / stats / track-visit / timeseries")
    await reset()
    await mk_user("u_l1", steam="76561198000000101", playtime=999, persona="Uno")
    await mk_user("u_l2", steam="76561198000000102", playtime=999, persona="Dos")
    await mk_user("u_l3", steam="76561198000000103", playtime=999, persona="Sus")
    await mk_creator("u_l1", "LEAD1", total_referrals=9, monthly_referrals=9)
    await mk_creator("u_l2", "LEAD2", total_referrals=5, monthly_referrals=5)
    await mk_creator("u_l3", "LEADSUS", total_referrals=50, monthly_referrals=50,
                     status=cp_mod.CREATOR_SUSPENDED)
    out = await server.creator_leaderboard(scope="all", user=None)
    check("board ordered + suspended hidden",
          [b["code"] for b in out["board"]] == ["LEAD1", "LEAD2"])
    check("prize skins on the wire, 3 ranks, proximity strips, no picture",
          set(out["prize_skins"].keys()) == {"1", "2", "3"}
          and all(len(cd["proximity"]) > 0 and cd.get("image", "") == ""
                  for cd in out["prize_skins"].values())
          and out["monthly_prizes"] == [1_000_000, 500_000, 250_000])
    u1 = await db.users.find_one({"id": "u_l1"})
    out2 = await server.creator_leaderboard(scope="all", user=u1)
    check("me row ranked", out2["me"] and out2["me"]["rank"] == 1)
    stats = await server.creator_program_stats()
    check("stats exclude suspended", stats["total_refs"] == 14 and stats["active_creators"] == 2)
    # track-visit: counts, refuses junk, throttles
    req = _FakeRequest("10.9.9.9")
    r1 = await server.creator_track_visit(body=server.CpTrackVisitIn(code="LEAD1"), request=req)
    check("visit counted", r1["ok"] is True)
    rbad = await server.creator_track_visit(body=server.CpTrackVisitIn(code="??"), request=req)
    check("junk code not counted", rbad["ok"] is False)
    for _ in range(40):
        await server.creator_track_visit(body=server.CpTrackVisitIn(code="LEAD1"), request=req)
    c1 = await db.creators.find_one({"code": "LEAD1"})
    check("throttle caps the counter", c1["code_visits_total"] == server._CP_VISIT_MAX_PER_WINDOW,
          c1["code_visits_total"])
    # dashboard payload carries the exclusive card by name, never a picture
    payload = await server._cp_dashboard_payload("u_l1")
    card = payload["skin_progress"]["card"]
    check("exclusive card name+proximity", card["glitch_id"] == EXCL_GID
          and len(card["proximity"]) > 0 and card.get("image", "") == "")
    ts = await server.creator_timeseries(days=30, user=u1)
    check("timeseries 30 buckets", len(ts["days"]) == 30)


async def t_admin_surfaces():
    print("[admin] create/update/settings/demo-gate/CSV guard")
    await reset()
    admin = {"id": "admin1", "role": "admin"}
    await mk_user("u_ad1", steam="76561198000000111", playtime=999, persona="=SUMA(1)")
    out = await server.creator_admin_create(
        body=server.CpCreatorCreateIn(steam_id="76561198000000111", code="newguy"), admin=admin)
    check("create normalizes code", out["creator"]["code"] == "NEWGUY")
    with expect_http(400):
        await server.creator_admin_create(
            body=server.CpCreatorCreateIn(steam_id="123", code="OTHER"), admin=admin)
        check("bad steam refused", False)
    with expect_http(409):
        await server.creator_admin_create(
            body=server.CpCreatorCreateIn(steam_id="76561198000000111", code="TWICE"), admin=admin)
        check("dup creator refused", False)
    check("admin create edges", True)
    s = await server.creator_admin_settings(
        body=server.CpSettingsIn(creator_reward=60_000, min_playtime_minutes=20), admin=admin)
    check("settings persist", s["settings"]["creator_reward"] == 60_000
          and s["settings"]["min_playtime_minutes"] == 20)
    # the 2026-08-18 knob is settable through the same endpoint
    s2 = await server.creator_admin_settings(
        body=server.CpSettingsIn(player_reward_once=False), admin=admin)
    check("the welcome-bonus knob is settable by an admin",
          s2["settings"]["player_reward_once"] is False)
    # ★ A KNOB NOBODY CAN READ IS HALF A KNOB. An owner installed before this
    #   change has a settings doc with no such key at all: every decision path
    #   already falls back to the module default, but the ADMIN PAGE reads this
    #   document directly and printed a blank where a live money knob is.
    await db.creator_settings.update_one({"id": "settings"},
                                         {"$unset": {"player_reward_once": ""}})
    eff = await server._cp_get_settings()
    check("a pre-08-18 settings doc still reports the knob's EFFECTIVE value",
          eff.get("player_reward_once") is True, str(eff.get("player_reward_once")))
    raw = await db.creator_settings.find_one({"id": "settings"}, {"_id": 0})
    check("...and reading it wrote nothing back (a GET must not write)",
          "player_reward_once" not in raw, str(sorted(raw.keys())))
    with expect_http(403):
        await server.creator_admin_seed_demo(admin=admin)
        check("demo refused without env arm", False)
    check("demo gate closed", True)
    # CSV formula guard: a rewarded referral whose player name starts with '='
    c = await db.creators.find_one({"code": "NEWGUY"})
    await mk_user("u_ad2", steam="76561198000000112", playtime=999, persona="=cmd|calc")
    rid = server.new_id()
    await db.referrals.insert_one({
        "id": rid, "creator_id": c["id"], "referred_user_id": "u_ad2",
        "code": "NEWGUY", "status": cp_mod.STATUS_PENDING,
        "month": cp_mod.month_id(), "created_at": server.now_iso()})
    await server._cp_validate_and_reward(rid)
    resp = await server.creator_admin_payouts_csv(admin=admin)
    body = resp.body.decode("utf-8")
    check("csv has the row", "NEWGUY" in body)
    check("csv formula guarded", "'=cmd|calc" in body and "\n=cmd" not in body)



# ---------------------------------------------------------------------------
# 2026-08-18 OWNER ORDER: "players should support others with their codes not
# only one person" + "users should support anyone with the code but only one
# time". A player may support ANY number of creators; each creator's code
# exactly once. The creator is paid for every distinct player who supports
# them; the PLAYER's welcome bonus is paid once per player.
# ---------------------------------------------------------------------------
async def t_multi_creator_support():
    print("[multi] a player supports MANY creators, each exactly ONCE")
    await reset()
    for i, (uid, code) in enumerate([("u_mc1", "MCONE"), ("u_mc2", "MCTWO"),
                                     ("u_mc3", "MCTHREE")]):
        await mk_user(uid, steam="7656119800000030%d" % i, playtime=999)
        await mk_creator(uid, code)
    p = await mk_user("u_mcp", steam="76561198000000399", playtime=60)

    a = await apply_code(p, "MCONE")
    check("first code rewards", a["status"] == cp_mod.STATUS_REWARDED, str(a))
    p = await db.users.find_one({"id": "u_mcp"})
    b = await apply_code(p, "MCTWO")
    check("a SECOND creator is accepted (the whole point of the order)",
          b["status"] == cp_mod.STATUS_REWARDED, str(b))
    p = await db.users.find_one({"id": "u_mcp"})
    c3 = await apply_code(p, "MCTHREE")
    check("and a third", c3["status"] == cp_mod.STATUS_REWARDED, str(c3))
    check("three referral rows, one per creator",
          await db.referrals.count_documents({"referred_user_id": "u_mcp"}) == 3)

    p = await db.users.find_one({"id": "u_mcp"})
    with expect_http(409):
        await apply_code(p, "MCONE")
        check("the SAME creator a second time 409s", False)
    check("and no fourth row was written",
          await db.referrals.count_documents({"referred_user_id": "u_mcp"}) == 3)

    for uid in ("u_mc1", "u_mc2", "u_mc3"):
        got = await coins_of(uid)
        check("creator %s was paid in full" % uid, got == 50_000, str(got))

    # THE DANGEROUS DIRECTION: the player's welcome bonus is a JOINING bonus.
    # Paying it per code would mint it once per creator on the same ten minutes
    # of play, from nothing.
    got = await coins_of("u_mcp")
    check("the player's welcome bonus was paid EXACTLY ONCE", got == 25_000, str(got))
    u = await db.users.find_one({"id": "u_mcp"})
    check("...and the claim flag is what says so", u.get("cp_welcome_paid") is True)
    rows = await db.referrals.find({"referred_user_id": "u_mcp"}) \
                             .sort("created_at", 1).to_list(10)
    paid = sorted(int(r.get("player_reward_amount") or 0) for r in rows)
    check("each row records what the PLAYER really got", paid == [0, 0, 25_000], str(paid))
    check("...while every row records the FULL creator reward",
          [int(r.get("reward_amount") or 0) for r in rows] == [50_000] * 3)
    txs = await db.transactions.count_documents(
        {"user_id": "u_mcp", "type": "creator_referral"})
    check("one welcome-bonus transaction, not three", txs == 1, str(txs))
    counted = []
    for uid in ("u_mc1", "u_mc2", "u_mc3"):
        cdoc = await db.creators.find_one({"user_id": uid})
        counted.append(int((cdoc or {}).get("total_referrals") or 0))
    check("every creator counts the referral", counted == [1, 1, 1], str(counted))


async def t_pair_uniqueness_is_the_index():
    print("[multi] the pre-08-18 index is MIGRATED, and the pair is settled by the INDEX")
    await reset()
    # ★★★★★ BUILD THE PRECONDITION, NEVER ASSUME IT. A fresh test database has
    # never carried the pre-2026-08-18 unique index, so "referred_user_id_1 is
    # gone" passes on one whether the migration runs or not -- measured: the
    # mutant that skips the drop entirely ran GREEN against the first version of
    # this test. Recreate the LIVE shape first, then migrate onto it, which is
    # the only way this gate says anything about the real database.
    await db.referrals.drop_indexes()
    await db.referrals.create_index("referred_user_id", unique=True)
    check("the pre-08-18 one-code-per-player index is there to begin with",
          "referred_user_id_1" in (await db.referrals.index_information()))
    await server._cp_ensure_indexes()
    idx_after = await db.referrals.index_information()
    check("the migration DROPPED it", "referred_user_id_1" not in idx_after,
          str(sorted(idx_after)))
    check("...and put the pair index in its place, unique",
          bool(idx_after.get("referred_creator_unique", {}).get("unique")),
          str(sorted(idx_after)))
    # and it is safe to run again on an already-migrated database
    await server._cp_ensure_indexes()
    check("re-running the migration is a no-op",
          "referred_user_id_1" not in (await db.referrals.index_information()))

    await mk_user("u_px_c", steam="76561198000000401", playtime=999)
    c = await mk_creator("u_px_c", "PAIRCODE")
    await mk_user("u_px_p", steam="76561198000000402", playtime=60)
    # Two racing inserts of the SAME pair. The read-before-write cannot settle
    # this; only the unique index can, which is why it exists.
    async def ins():
        try:
            await db.referrals.insert_one({
                "id": server.new_id(), "creator_id": c["id"], "referred_user_id": "u_px_p",
                "code": "PAIRCODE", "status": cp_mod.STATUS_PENDING,
                "month": cp_mod.month_id(), "created_at": server.now_iso()})
            return True
        except Exception:
            return False
    got = await asyncio.gather(*[ins() for _ in range(6)])
    check("exactly one insert survived", sum(1 for g in got if g) == 1, str(got))
    check("one row on disk", await db.referrals.count_documents({}) == 1)
    # ...and a DIFFERENT creator for the same player is not blocked by it
    await mk_user("u_px_c2", steam="76561198000000403", playtime=999)
    c2 = await mk_creator("u_px_c2", "PAIRCODE2")
    await db.referrals.insert_one({
        "id": server.new_id(), "creator_id": c2["id"], "referred_user_id": "u_px_p",
        "code": "PAIRCODE2", "status": cp_mod.STATUS_PENDING,
        "month": cp_mod.month_id(), "created_at": server.now_iso()})
    check("a second CREATOR for the same player is allowed",
          await db.referrals.count_documents({"referred_user_id": "u_px_p"}) == 2)
    idx = await db.referrals.index_information()
    check("the legacy one-code-per-player index is GONE",
          "referred_user_id_1" not in idx, str(sorted(idx)))
    check("the pair index is present and unique",
          bool(idx.get("referred_creator_unique", {}).get("unique")), str(sorted(idx)))


async def t_welcome_bonus_race_and_knob():
    print("[multi] the welcome bonus survives a race, and the admin knob turns it off")
    await reset()
    await mk_user("u_wb_c1", steam="76561198000000411", playtime=999)
    c1 = await mk_creator("u_wb_c1", "WBONE")
    await mk_user("u_wb_c2", steam="76561198000000412", playtime=999)
    c2 = await mk_creator("u_wb_c2", "WBTWO")
    await mk_user("u_wb_p", steam="76561198000000413", playtime=60)
    rids = []
    for c, code in ((c1, "WBONE"), (c2, "WBTWO")):
        rid = server.new_id()
        rids.append(rid)
        await db.referrals.insert_one({
            "id": rid, "creator_id": c["id"], "referred_user_id": "u_wb_p",
            "code": code, "status": cp_mod.STATUS_PENDING,
            "month": cp_mod.month_id(), "created_at": server.now_iso()})
    # BOTH codes validate in the same instant.
    await asyncio.gather(*[server._cp_validate_and_reward(r) for r in rids])
    got = await coins_of("u_wb_p")
    check("the welcome bonus is paid ONCE even under a race", got == 25_000, str(got))
    check("both creators were still paid in full",
          await coins_of("u_wb_c1") == 50_000 and await coins_of("u_wb_c2") == 50_000)

    # The knob: the owner can pay it on every code instead.
    await reset()
    await mk_user("u_kb_c1", steam="76561198000000421", playtime=999)
    await mk_creator("u_kb_c1", "KBONE")
    await mk_user("u_kb_c2", steam="76561198000000422", playtime=999)
    await mk_creator("u_kb_c2", "KBTWO")
    await _cp_settings_set(player_reward_once=False)
    p = await mk_user("u_kb_p", steam="76561198000000423", playtime=60)
    await apply_code(p, "KBONE")
    p = await db.users.find_one({"id": "u_kb_p"})
    await apply_code(p, "KBTWO")
    got = await coins_of("u_kb_p")
    check("player_reward_once=false pays the bonus on EVERY code",
          got == 50_000, str(got))


async def t_welcome_backfill_protects_existing_players():
    print("[multi] a player already paid under the OLD one-code rule is not paid twice")
    await reset()
    await mk_user("u_bf_c1", steam="76561198000000431", playtime=999)
    c1 = await mk_creator("u_bf_c1", "BFONE", total_referrals=1, monthly_referrals=1)
    await mk_user("u_bf_c2", steam="76561198000000432", playtime=999)
    await mk_creator("u_bf_c2", "BFTWO")
    # THE PRE-08-18 WORLD, exactly as it exists on the live database: a REWARDED
    # referral that paid the player, and NO claim flag anywhere, because nothing
    # ever needed one while a player could only hold one code.
    await mk_user("u_bf_p", steam="76561198000000433", playtime=60, coins=25_000)
    await db.referrals.insert_one({
        "id": server.new_id(), "creator_id": c1["id"], "referred_user_id": "u_bf_p",
        "code": "BFONE", "status": cp_mod.STATUS_REWARDED, "reward_amount": 50_000,
        "player_reward_amount": 25_000, "month": cp_mod.month_id(),
        "created_at": server.now_iso(), "rewarded_at": server.now_iso()})
    await db.creator_settings.update_one({"id": "settings"},
                                         {"$unset": {"welcome_backfill_done": ""}})
    n = await server._cp_backfill_welcome_claims_once()
    check("the backfill marked the already-paid player", n == 1, str(n))
    u = await db.users.find_one({"id": "u_bf_p"})
    check("...on the player document", u.get("cp_welcome_paid") is True)
    check("...and it moved no money", int(u.get("coins") or 0) == 25_000)
    check("re-running it is a no-op",
          await server._cp_backfill_welcome_claims_once() == 0)

    p = await db.users.find_one({"id": "u_bf_p"})
    out = await apply_code(p, "BFTWO")
    check("their next code still rewards the CREATOR",
          out["status"] == cp_mod.STATUS_REWARDED and await coins_of("u_bf_c2") == 50_000)
    check("but hands the player NO second welcome bonus",
          await coins_of("u_bf_p") == 25_000, str(await coins_of("u_bf_p")))


async def t_my_referral_lists_every_creator():
    print("[multi] /creator/my-referral answers with every creator, old shape kept on top")
    await reset()
    await mk_user("u_ml_c1", steam="76561198000000441", playtime=999)
    await mk_creator("u_ml_c1", "MLONE")
    await mk_user("u_ml_c2", steam="76561198000000442", playtime=999)
    await mk_creator("u_ml_c2", "MLTWO")
    p = await mk_user("u_ml_p", steam="76561198000000443", playtime=60)
    await apply_code(p, "MLONE")
    p = await db.users.find_one({"id": "u_ml_p"})
    await apply_code(p, "MLTWO")
    p = await db.users.find_one({"id": "u_ml_p"})
    out = await server.creator_my_referral(user=p)
    check("used + count", out["used"] is True and out["count"] == 2, str(out.get("count")))
    codes = [r["code"] for r in out["referrals"]]
    check("both codes listed, newest first", codes == ["MLTWO", "MLONE"], str(codes))
    # ★ A browser that has not reloaded still reads the TOP-LEVEL keys.
    check("the legacy single-referral shape survives on top",
          out.get("code") == "MLTWO" and out.get("creator") is not None
          and "status" in out, str(sorted(out.keys())))
    check("the welcome bonus is reported as spent",
          out.get("welcome_bonus_used") is True and out.get("player_reward_once") is True)
    # a player with nothing
    empty = await mk_user("u_ml_none", steam="76561198000000444", playtime=1)
    none_out = await server.creator_my_referral(user=empty)
    check("a player with no codes reads empty, never a crash",
          none_out == {"used": False, "count": 0, "referrals": []}, str(none_out))


async def t_every_pending_code_validates_on_the_press():
    print("[multi] validating from user context pays EVERY eligible pending code")
    await reset()
    await mk_user("u_ev_c1", steam="76561198000000451", playtime=999)
    c1 = await mk_creator("u_ev_c1", "EVONE")
    await mk_user("u_ev_c2", steam="76561198000000452", playtime=999)
    c2 = await mk_creator("u_ev_c2", "EVTWO")
    # the player has NOT played yet, so both codes sit PENDING
    p = await mk_user("u_ev_p", steam="76561198000000453", playtime=0)
    await apply_code(p, "EVONE")
    p = await db.users.find_one({"id": "u_ev_p"})
    await apply_code(p, "EVTWO")
    check("both sit pending",
          await db.referrals.count_documents({"referred_user_id": "u_ev_p",
                                              "status": cp_mod.STATUS_PENDING}) == 2)
    # now they play enough
    await db.users.update_one({"id": "u_ev_p"}, {"$set": {"playtime_minutes": 60}})
    p = await db.users.find_one({"id": "u_ev_p"})
    await server._cp_try_validate_for_user(p)
    left = await db.referrals.count_documents({"referred_user_id": "u_ev_p",
                                               "status": cp_mod.STATUS_PENDING})
    check("NO code is left waiting for the 5-minute sweep", left == 0, str(left))
    check("both creators paid",
          await coins_of("u_ev_c1") == 50_000 and await coins_of("u_ev_c2") == 50_000)
    check("the player still got exactly one welcome bonus",
          await coins_of("u_ev_p") == 25_000, str(await coins_of("u_ev_p")))


async def t_ws_push_carries_rest_shape():
    print("[ws] a creator_dashboard push carries the REST shape (is_creator gate)")
    # 2026-08-20 owner report: creators saw "Todavía no sos Creator" while the
    # real panel flickered underneath. The page gates on data.is_creator; the
    # socket lane sent the raw payload WITHOUT it, so every push stomped a real
    # creator back to the not-registered screen. Pin: every creator_dashboard
    # push must carry the same shape GET /creator/dashboard answers with.
    await reset()
    await mk_user("u_ws_c", steam="76561198000000911", playtime=999)
    c = await mk_creator("u_ws_c", "WSSHAPE")
    await mk_user("u_ws_p", steam="76561198000000912", playtime=60)
    rid = server.new_id()
    await db.referrals.insert_one({
        "id": rid, "creator_id": c["id"], "referred_user_id": "u_ws_p",
        "code": "WSSHAPE", "status": cp_mod.STATUS_PENDING,
        "month": cp_mod.month_id(), "created_at": server.now_iso()})
    captured = []
    async def spy(uid, msg):
        captured.append((uid, msg))
    server.creator_hub.push_to_user = spy
    try:
        await server._cp_validate_and_reward(rid)
    finally:
        del server.creator_hub.push_to_user
    dash = [m for _, m in captured if m.get("type") == "creator_dashboard"]
    check("reward path pushed a dashboard", len(dash) >= 1, str(len(captured)))
    check("push data carries is_creator True",
          all(m["data"].get("is_creator") is True for m in dash))
    check("push data still carries the payload",
          all(m["data"].get("creator", {}).get("code") == "WSSHAPE" for m in dash))
    check("push went to the creator's user id",
          all(uid == "u_ws_c" for uid, m in captured if m.get("type") == "creator_dashboard"))


async def main():
    t0 = time.time()
    await t_catalog_entry()
    await t_apply_happy()
    await t_apply_pending_then_sweep()
    await t_apply_refusals()
    await t_multi_creator_support()
    await t_pair_uniqueness_is_the_index()
    await t_welcome_bonus_race_and_knob()
    await t_welcome_backfill_protects_existing_players()
    await t_my_referral_lists_every_creator()
    await t_every_pending_code_validates_on_the_press()
    await t_my_referral_pending_reason()
    await t_island_presence_lane()
    await t_concurrent_single_pay()
    await t_milestone_and_skin()
    await t_burst_pause_and_recovery()
    await t_monthly_close()
    await t_first_boot_adoption()
    await t_public_surfaces()
    await t_admin_surfaces()
    await t_ws_push_carries_rest_shape()
    print("\n%d PASS / %d FAIL in %.1fs" % (PASS, FAIL, time.time() - t0))
    if _FAILED:
        print("failed:", ", ".join(_FAILED))
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    finally:
        stop_mongo()
    sys.exit(rc)
