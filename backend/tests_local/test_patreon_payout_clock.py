# -*- coding: utf-8 -*-
"""Patreon bi-weekly Amberium CLOCK -- freeze / resume gate. REAL I/O.

Owner ruling 2026-08-16, from a paying Adult patron's report: "he was 5 days for
payout now went back again to 13 ... if someone disconnects the reconnects timer
shouldnt reset."

Before this, `/patreon/unlink` `$unset` the anchor and the count, so the next link
started a fresh 14 days and every served day was gone. Measured on prod the same
day: 7 accounts had been re-anchored that way (the reporter 7.16 days in, another
active patron 12.71 days in) and 12 more sit unlinked with the clock deleted.

The fix is a FREEZE, not "stop clearing the anchor" -- that naive version would have
opened the opposite hole: unlink for two months, relink, collect four periods of
back-pay. So the clock is stamped when entitlement ends and the anchor is slid
forward by the exact freeze length when it returns. Progress kept, gap never paid.

Drives the REAL writers against a REAL MongoDB (no fake Mongo: the freeze leans on
`$exists: False` and the resume on a two-field CAS -- a double with the wrong
contract would pass here while production slid the anchor twice):

  * ``server.patreon_unlink``          -- the route the accident goes through
  * ``server._amber_freeze_cycle`` / ``_amber_resume_cycle``
  * ``server._after_patreon_status_update`` -- every status writer's shared tail
  * ``server._patreon_payout_one``     -- the money pass
  * ``server.patreon_status``          -- what the payout panel reads
  * ``server.sync_patreon_for_user``   -- the end-to-end relink

Run:  python backend/tests_local/test_patreon_payout_clock.py
Exit: 0 all pass / 1 a check failed / 2 the suite could NOT run (never a pass).
"""
import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import uuid
from datetime import datetime, timedelta, timezone

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
TMP = tempfile.mkdtemp(prefix="lin_amber_clock_")


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
os.environ["DB_NAME"] = "lin_amber_clock_%s" % uuid.uuid4().hex[:8]
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ["DISCORD_BOT_TOKEN"] = "bot-token-fake"
os.environ["DISCORD_GUILD_ID"] = "1523167556368859286"
os.environ["DISCORD_PATREON_NOTICE_CHANNEL_ID"] = ""
os.environ.setdefault("RCON_HOST", "")
os.environ.setdefault("ALLOW_DEMO_LOGIN", "0")
os.environ.setdefault("PATREON_CLIENT_ID", "client-id-test")
os.environ.setdefault("PATREON_CLIENT_SECRET", "client-secret-test")
os.environ.setdefault("PATREON_CAMPAIGN_ID", "campaign-1")
os.environ.setdefault("PUBLIC_BASE_URL", "https://laislanublar.net")
os.environ.setdefault("DISCORD_PATREON_ROLE_IDS",
                      "9001:Apex,9002:Elder,9003:Adult,9004:Sub Adult,9005:Juvie,9006:Supporter")

sys.path.insert(0, BACKEND)
import server  # noqa: E402

db = server.db
PERIOD = timedelta(days=server.PATREON_PAYOUT_DAYS)


# ---------------------------------------------------------------------------
# HTTP seam: only Patreon identity + Discord are faked
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text or "{}"
        self.content = b"{}"

    def json(self):
        return self._payload


class HTTP:
    patreon_status = "active_patron"
    patreon_tier = "Adult"
    patreon_user_id = "patreon-user-1"

    @classmethod
    def reset(cls):
        cls.patreon_status = "active_patron"
        cls.patreon_tier = "Adult"
        cls.patreon_user_id = "patreon-user-1"


def _identity_payload():
    return {"data": {"id": HTTP.patreon_user_id, "attributes": {"full_name": "Test Patron"}},
            "included": [{
                "type": "member", "id": "member-1",
                "attributes": {"patron_status": HTTP.patreon_status,
                               "currently_entitled_amount_cents": 500,
                               "last_charge_date": "2026-07-01T00:00:00+00:00",
                               "next_charge_date": "2026-08-01T00:00:00+00:00",
                               "pledge_relationship_start": "2026-07-01T00:00:00+00:00"},
                "relationships": {"currently_entitled_tiers": {"data": [{"id": "tier-1"}]},
                                  "campaign": {"data": {"id": "campaign-1"}}},
            }, {"type": "tier", "id": "tier-1", "attributes": {"title": HTTP.patreon_tier}}]}


class FakeAsyncClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, **k):
        if "patreon.com/api/oauth2/v2/identity" in url:
            return _Resp(200, _identity_payload())
        return _Resp(200, {"data": []})

    async def post(self, url, **k):
        return _Resp(200, {"id": "dm-1"})

    async def put(self, url, **k):
        return _Resp(204, {})

    async def delete(self, url, **k):
        return _Resp(204, {})

    async def patch(self, url, **k):
        return _Resp(200, {})


server.httpx = types.SimpleNamespace(AsyncClient=FakeAsyncClient)


# ---------------------------------------------------------------------------
# helpers over the REAL db
# ---------------------------------------------------------------------------
async def drain():
    for _ in range(60):
        pending = [t for t in server._BG_TASKS if not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)


async def reset_state():
    await db.users.delete_many({})
    await db.transactions.delete_many({})
    await db.logs.delete_many({})
    HTTP.reset()


async def mk_user(**over):
    uid = uuid.uuid4().hex
    doc = {"id": uid, "steam_id": "7656119900000%04d" % (abs(hash(uid)) % 10000),
           "email": "t@t", "role": "user", "persona_name": "Tester",
           "discord_id": "discord-%s" % uid[:6], "vip_coins": 0, "coins": 0}
    doc.update(over)
    await db.users.insert_one(dict(doc))
    return await db.users.find_one({"id": uid}, {"_id": 0})


async def get(uid):
    return await db.users.find_one({"id": uid}, {"_id": 0})


def iso_ago(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def age_days(iso):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 86400.0


async def frozen_patron(served_days, away_days, **over):
    """An account that served `served_days` of the cycle and has since been unlinked
    for `away_days`.

    Built by driving the REAL unlink route and THEN back-dating the anchor and the
    freeze stamp together. Both have to move: back-dating only the stamp describes a
    clock that froze before it started, and the resume arithmetic is then measuring a
    state production can never be in.
    """
    u = await patron(served_days, **over)
    await server.patreon_unlink(user=u)
    await db.users.update_one({"id": u["id"]}, {"$set": {
        "amber_payout_anchor": iso_ago(days=served_days + away_days),
        "amber_payout_paused_at": iso_ago(days=away_days)}})
    return await get(u["id"])


async def back_online(uid):
    """Re-assert the patron fields WITHOUT the shared tail -- the `link_dead` shape."""
    await db.users.update_one({"id": uid}, {"$set": {
        "patreon_patron_status": "active_patron", "patreon_tier_name": "Adult",
        "patreon_id": "pat-1"}})


async def patron(days_served, **over):
    """An active patron who has already served `days_served` of the 14-day cycle."""
    doc = {"patreon_patron_status": "active_patron", "patreon_tier_name": "Adult",
           "patreon_id": "pat-1", "vip_coins": 0,
           "amber_payout_anchor": iso_ago(days=days_served), "amber_payout_count": 0,
           "patreon_welcome_amber_at": iso_ago(days=days_served),
           "patreon_welcome_amber_patreon_id": "pat-1",
           "patreon_welcome_amber_tier": "adult", "patreon_welcome_amber_total": 40000}
    doc.update(over)
    return await mk_user(**doc)


# ---------------------------------------------------------------------------
# 1. the freeze
# ---------------------------------------------------------------------------
async def t_unlink_freezes_instead_of_deleting():
    print("\n[1] /patreon/unlink freezes the clock; it no longer deletes it")
    await reset_state()
    u = await patron(9)
    anchor = u["amber_payout_anchor"]
    await server.patreon_unlink(user=u)
    after = await get(u["id"])
    check("the anchor survived", after.get("amber_payout_anchor") == anchor,
          str(after.get("amber_payout_anchor")))
    check("the count survived", after.get("amber_payout_count") == 0,
          str(after.get("amber_payout_count")))
    check("a freeze stamp was written", bool(after.get("amber_payout_paused_at")))
    check("the link itself IS gone", not after.get("patreon_id") and not after.get("patreon_access_token"))
    check("the patron status IS gone", not after.get("patreon_patron_status"))
    check("the joining stamp still blocks a second payment",
          bool(after.get("patreon_welcome_amber_at")))


async def t_second_freeze_never_moves_the_stamp():
    print("\n[2] a second freeze keeps the FIRST stamp (re-stamping would gift time)")
    await reset_state()
    u = await patron(9)
    await server._amber_freeze_cycle(u["id"])
    first = (await get(u["id"]))["amber_payout_paused_at"]
    await asyncio.sleep(0.05)
    again = await server._amber_freeze_cycle(u["id"])
    second = (await get(u["id"]))["amber_payout_paused_at"]
    check("the second freeze reported no write", again is False, str(again))
    check("the stamp did not move", first == second, "%s vs %s" % (first, second))


async def t_freeze_without_a_clock_writes_nothing():
    print("\n[3] freezing an account that never had a clock writes nothing")
    await reset_state()
    u = await mk_user()
    did = await server._amber_freeze_cycle(u["id"])
    after = await get(u["id"])
    check("nothing was written", did is False and "amber_payout_paused_at" not in after,
          str(after.get("amber_payout_paused_at")))
    # And the unlink route on a never-linked account is still a clean no-op.
    await server.patreon_unlink(user=after)
    after2 = await get(u["id"])
    check("unlink on a never-linked account stays clean",
          "amber_payout_paused_at" not in after2 and "amber_payout_anchor" not in after2)


# ---------------------------------------------------------------------------
# 2. the resume
# ---------------------------------------------------------------------------
async def t_resume_keeps_the_served_days():
    print("\n[4] resuming slides the anchor by the freeze, so served days survive")
    await reset_state()
    u = await frozen_patron(served_days=9, away_days=3)
    did = await server._amber_resume_cycle(u["id"])
    after = await get(u["id"])
    check("the resume reported the write", did is True)
    check("the freeze stamp is gone", "amber_payout_paused_at" not in after)
    served = age_days(after["amber_payout_anchor"])
    check("served 9, away 3, resumes at 9 served (anchor slid 3 days)",
          8.99 < served < 9.01, "%.5f days served" % served)
    check("NEGATIVE CONTROL: not re-anchored to now", served > 1.0, "%.5f" % served)
    check("NEGATIVE CONTROL: the gap was not counted as progress", served < 12.0, "%.5f" % served)


async def t_a_long_freeze_pays_nothing_on_return():
    print("\n[5] MONEY: away for 60 days then back = zero back-pay")
    await reset_state()
    u = await frozen_patron(served_days=9, away_days=60)
    # They come back the way a real relink comes back: through the shared tail.
    await back_online(u["id"])
    await server._after_patreon_status_update(u["id"], "active_patron")
    await drain()
    back = await get(u["id"])
    check("no money was minted by the return", back.get("vip_coins") == 0,
          str(back.get("vip_coins")))
    paid = await server._patreon_payout_one(back, datetime.now(timezone.utc), PERIOD)
    await drain()
    after = await get(u["id"])
    check("the payout pass owes nothing for the 60 days away", paid == 0, str(paid))
    check("balance untouched", after.get("vip_coins") == 0, str(after.get("vip_coins")))
    served = age_days(after["amber_payout_anchor"])
    check("and they resume 9 days in, not 69", 8.9 < served < 9.1, "%.4f" % served)
    check("no transaction row", len(await txns_of(u["id"])) == 0)


async def txns_of(uid):
    return [t async for t in db.transactions.find({"user_id": uid}, {"_id": 0})]


async def t_double_resume_slides_once():
    print("\n[6] the REAL double fire: two relinks 1s apart slide the anchor ONCE")
    # Not hypothetical -- the reporting account's own log carries two `link_patreon`
    # rows 1.0 s apart for one relink (OAuth callback + creator reconcile).
    await reset_state()
    u = await frozen_patron(served_days=9, away_days=3)
    await back_online(u["id"])
    r = await asyncio.gather(server._amber_resume_cycle(u["id"]),
                             server._amber_resume_cycle(u["id"]),
                             server._amber_resume_cycle(u["id"]))
    after = await get(u["id"])
    check("exactly one resume won the CAS", sum(1 for x in r if x) == 1, str(r))
    served = age_days(after["amber_payout_anchor"])
    check("the anchor slid exactly once (9 days served, not 6 or 3)",
          8.99 < served < 9.01, "%.5f days served" % served)


async def t_future_pause_stamp_never_slides_backwards():
    print("\n[7] a pause stamp in the future (clock step) slides nothing")
    await reset_state()
    u = await patron(9)
    await server._amber_freeze_cycle(u["id"])
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    await db.users.update_one({"id": u["id"]}, {"$set": {"amber_payout_paused_at": future}})
    before = (await get(u["id"]))["amber_payout_anchor"]
    await server._amber_resume_cycle(u["id"])
    after = await get(u["id"])
    check("the anchor did not move backwards", after["amber_payout_anchor"] == before,
          "%s vs %s" % (before, after.get("amber_payout_anchor")))
    check("the stamp was cleared", "amber_payout_paused_at" not in after)
    paid = await server._patreon_payout_one(after, datetime.now(timezone.utc), PERIOD)
    check("and no payout became due from it", paid == 0, str(paid))


async def t_junk_anchor_is_repaired_not_frozen_forever():
    print("\n[8] an unusable anchor is cleared so the account re-anchors, not stuck")
    await reset_state()
    u = await patron(9, amber_payout_anchor="not-a-date")
    await server._amber_freeze_cycle(u["id"])
    check("it froze (an anchor field is present)", bool((await get(u["id"])).get("amber_payout_paused_at")))
    await server._amber_resume_cycle(u["id"])
    after = await get(u["id"])
    check("the junk anchor was dropped", "amber_payout_anchor" not in after,
          str(after.get("amber_payout_anchor")))
    check("the freeze stamp was dropped", "amber_payout_paused_at" not in after)
    # The shared tail now gives it a real anchor instead of leaving it unpayable.
    await server._after_patreon_status_update(u["id"], "active_patron")
    await drain()
    healed = await get(u["id"])
    check("the tail re-anchored it", age_days(healed["amber_payout_anchor"]) < 0.01,
          str(healed.get("amber_payout_anchor")))


# ---------------------------------------------------------------------------
# 3. nothing is lost, nothing is double-paid
# ---------------------------------------------------------------------------
async def t_a_due_payout_survives_the_freeze():
    print("\n[9] a payout already DUE when the clock froze is still owed on return")
    await reset_state()
    # 15 days served = one full period elapsed and the pass had not run yet when the
    # account went away for 20 days.
    u = await frozen_patron(served_days=15, away_days=20)
    check("frozen while owed", bool(u.get("amber_payout_paused_at")))
    await back_online(u["id"])
    await server._after_patreon_status_update(u["id"], "active_patron")
    await drain()
    paid = await server._patreon_payout_one(await get(u["id"]), datetime.now(timezone.utc), PERIOD)
    await drain()
    after = await get(u["id"])
    check("the owed period was paid exactly once", paid == 40000, str(paid))
    check("balance shows one period", after.get("vip_coins") == 40000, str(after.get("vip_coins")))
    check("the count advanced by one", after.get("amber_payout_count") == 1,
          str(after.get("amber_payout_count")))
    again = await server._patreon_payout_one(await get(u["id"]), datetime.now(timezone.utc), PERIOD)
    check("a second pass pays nothing", again == 0, str(again))


async def t_payout_pass_resumes_a_stranded_row():
    print("\n[10] the money pass resumes a still-frozen active row instead of back-paying it")
    # Reproduces the link_dead shape: a status writer that does not go through the tail.
    await reset_state()
    u = await frozen_patron(served_days=9, away_days=45)
    await back_online(u["id"])  # active again, still frozen: nothing called the tail
    paid = await server._patreon_payout_one(await get(u["id"]), datetime.now(timezone.utc), PERIOD)
    await drain()
    after = await get(u["id"])
    check("the 45 frozen days were not paid", paid == 0, str(paid))
    check("balance untouched", after.get("vip_coins") == 0, str(after.get("vip_coins")))
    check("the row was resumed, not left stranded", "amber_payout_paused_at" not in after)
    served = age_days(after["amber_payout_anchor"])
    check("it resumes 9 days in", 8.9 < served < 9.1, "%.4f" % served)


async def t_count_survives_so_the_joining_guard_still_bites():
    print("\n[11] keeping the count keeps the no-windfall guard armed across an unlink")
    await reset_state()
    # A long-standing patron who has collected cycles but never had a joining payment.
    u = await patron(40, amber_payout_count=2, vip_coins=120000)
    await db.users.update_one({"id": u["id"]}, {"$unset": {
        "patreon_welcome_amber_at": "", "patreon_welcome_amber_patreon_id": "",
        "patreon_welcome_amber_tier": "", "patreon_welcome_amber_total": ""}})
    before = await get(u["id"])
    refused = await server._patreon_pay_welcome_amber(before)
    check("refused while linked (count > 0)", refused is False, str(refused))
    await server.patreon_unlink(user=before)
    await db.users.update_one({"id": u["id"]}, {"$set": {
        "patreon_patron_status": "active_patron", "patreon_tier_name": "Adult",
        "patreon_id": "pat-1"}})
    await server._after_patreon_status_update(u["id"], "active_patron")
    await drain()
    after = await get(u["id"])
    check("still refused after unlink+relink", after.get("vip_coins") == 120000,
          str(after.get("vip_coins")))
    check("the count was never cleared", after.get("amber_payout_count") == 2,
          str(after.get("amber_payout_count")))
    check("no joining stamp was minted", not after.get("patreon_welcome_amber_at"))


# ---------------------------------------------------------------------------
# 4. what the player sees, and the whole road
# ---------------------------------------------------------------------------
async def t_status_route_holds_the_countdown():
    print("\n[12] the payout panel shows a HELD countdown, not one quietly not running")
    await reset_state()
    u = await patron(9)
    live = await server.patreon_status(user=await get(u["id"]))
    check("running: about 5 days left", 4.9 < live["seconds_remaining"] / 86400.0 < 5.1,
          str(live["seconds_remaining"]))
    check("running: not flagged paused", live["cycle_paused"] is False)
    await server._amber_freeze_cycle(u["id"])
    # Still an active patron in the DB, so the panel renders -- but the clock is held.
    await asyncio.sleep(1.1)
    held = await server.patreon_status(user=await get(u["id"]))
    check("paused is reported", held["cycle_paused"] is True)
    check("the held countdown did not tick down with the wall clock",
          held["seconds_remaining"] == live["seconds_remaining"] or
          abs(held["seconds_remaining"] - live["seconds_remaining"]) <= 1,
          "%s vs %s" % (live["seconds_remaining"], held["seconds_remaining"]))


async def t_end_to_end_through_the_real_routes():
    print("\n[13] END TO END: subscribe -> serve 9 days -> unlink -> relink")
    await reset_state()
    u = await mk_user()
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    joined = await get(u["id"])
    check("the joining Amberium landed", joined.get("vip_coins") == 40000,
          str(joined.get("vip_coins")))
    await db.users.update_one({"id": u["id"]}, {"$set": {"amber_payout_anchor": iso_ago(days=9)}})
    before = await server.patreon_status(user=await get(u["id"]))
    await server.patreon_unlink(user=await get(u["id"]))
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after_doc = await get(u["id"])
    after = await server.patreon_status(user=after_doc)
    check("balance unchanged by the round trip", after_doc.get("vip_coins") == 40000,
          str(after_doc.get("vip_coins")))
    drift = abs(after["seconds_remaining"] - before["seconds_remaining"])
    check("the countdown came back where it was (within a second)", drift <= 2,
          "%s -> %s" % (before["seconds_remaining"], after["seconds_remaining"]))
    check("NEGATIVE CONTROL: it is NOT a fresh 14 days",
          after["seconds_remaining"] < 6 * 86400, str(after["seconds_remaining"]))
    check("not left flagged as paused", after["cycle_paused"] is False)


async def main():
    try:
        await t_unlink_freezes_instead_of_deleting()
        await t_second_freeze_never_moves_the_stamp()
        await t_freeze_without_a_clock_writes_nothing()
        await t_resume_keeps_the_served_days()
        await t_a_long_freeze_pays_nothing_on_return()
        await t_double_resume_slides_once()
        await t_future_pause_stamp_never_slides_backwards()
        await t_junk_anchor_is_repaired_not_frozen_forever()
        await t_a_due_payout_survives_the_freeze()
        await t_payout_pass_resumes_a_stranded_row()
        await t_count_survives_so_the_joining_guard_still_bites()
        await t_status_route_holds_the_countdown()
        await t_end_to_end_through_the_real_routes()
    finally:
        try:
            await db.client.drop_database(os.environ["DB_NAME"])
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        stop_mongo()
    print("\n%d passed, %d failed" % (PASS, FAIL))
    if _FAILED:
        for n in _FAILED:
            print("  FAILED: %s" % n)
    sys.exit(1 if FAIL else 0)
