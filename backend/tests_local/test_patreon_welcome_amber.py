# -*- coding: utf-8 -*-
"""Patreon joining Amberium -- REAL I/O gate.

Owner ruling 2026-07-24: every Patreon tier is paid its Amberium the moment the
person subscribes, the 14-day countdown starts from that instant, and a Discord
message goes out on EVERY payout (joining and recurring). This is the same rule
the Streamer Pack got on 2026-07-24 02:52Z, widened to all five tiers.

This suite drives the REAL writers against a REAL MongoDB:

  * ``server.sync_patreon_for_user``   -- the path a subscriber actually travels
    (OAuth callback / the Sincronizar button / the 12-hourly resync loop), with
    only the Patreon HTTP call and Discord's HTTP API replaced by fakes.
  * ``server._patreon_pay_welcome_amber`` -- the once-per-account claim.
  * ``server._patreon_payout_one``     -- one patron's turn in the bi-weekly pass.
  * ``server.patreon_status``          -- the field the payout panel reads.

No fake Mongo: the claim leans on ``$exists`` / ``$lte`` / ``$in: [0, None]`` /
``$or`` and on ``modified_count``, and a double with the wrong contract would
pass here while production paid twice (see the 07-22 equip-route lesson --
seeded state proved nothing because no live writer produced the field).

Run:  python backend/tests_local/test_patreon_welcome_amber.py
      (set MONGO_URL to reuse a running mongod; otherwise the portable
       _localtest mongod is started on a temp dbpath and stopped again.)

Exit codes: 0 all pass / 1 a check failed / 2 the suite could NOT run (no
mongod) -- 2 is never a pass, a suite that did not run is a failed read.
"""
import asyncio
import hashlib
import hmac
import json as _json
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

# The failure detail printed below can carry the Spanish DM text, emoji and all. On a
# cp1252 console that raised INSIDE check() and killed the run at the first failure --
# a suite that cannot report a failure is a broken oracle, so force UTF-8 out.
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
TMP = tempfile.mkdtemp(prefix="lin_patreon_amber_")


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


# ---------------------------------------------------------------------------
# env -> import the REAL server module
# ---------------------------------------------------------------------------
MONGO_URL = start_mongo()
os.environ["MONGO_URL"] = MONGO_URL
os.environ["DB_NAME"] = "lin_patreon_amber_%s" % uuid.uuid4().hex[:8]
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ["DISCORD_BOT_TOKEN"] = "bot-token-fake"
os.environ["DISCORD_GUILD_ID"] = "1523167556368859286"
# Deliberately EMPTY for most of the run: prod has no patron notice channel today,
# so the default path (DM only, undelivered notice logged) is what ships.
os.environ["DISCORD_PATREON_NOTICE_CHANNEL_ID"] = ""
os.environ.setdefault("RCON_HOST", "")
os.environ.setdefault("ALLOW_DEMO_LOGIN", "0")
# Creator-side truth lane (webhook + reconcile): campaign id matches the id every
# faked identity/member payload carries; tier role ids are fake but well-formed so
# the REAL sync_discord_tier_roles runs against the faked Discord transport.
os.environ.setdefault("PATREON_CLIENT_ID", "client-id-test")
os.environ.setdefault("PATREON_CLIENT_SECRET", "client-secret-test")
os.environ.setdefault("PATREON_CREATOR_ACCESS_TOKEN", "creator-access-0")
os.environ.setdefault("PATREON_CREATOR_REFRESH_TOKEN", "creator-refresh-0")
os.environ.setdefault("PATREON_CAMPAIGN_ID", "campaign-1")
os.environ.setdefault("PUBLIC_BASE_URL", "https://laislanublar.net")
os.environ.setdefault("DISCORD_PATREON_ROLE_IDS",
                      "9001:Apex,9002:Elder,9003:Adult,9004:Sub Adult,9005:Juvie,9006:Supporter")

sys.path.insert(0, BACKEND)
import server  # noqa: E402

db = server.db


# ---------------------------------------------------------------------------
# HTTP seam: the ONLY thing faked. Routes by URL, records every Discord call.
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
    """State the fake transport reads/writes. One place, reset per test."""
    patreon_status = "active_patron"
    patreon_tier = "Apex"
    patreon_entitled = None  # list of tier titles; overrides patreon_tier when set
    patreon_user_id = "patreon-user-1"
    dm_open_ok = True        # POST /users/@me/channels
    dm_send_ok = True        # POST /channels/<dm>/messages
    channel_post_ok = True   # POST /channels/<notice channel>/messages
    dms = []                 # [(recipient_id, content)]
    channel_posts = []       # [(channel_id, content, allowed_mentions)]
    # creator-side truth lane (webhook + reconcile)
    campaign_members = []     # dicts: pid,status,titles,cents,since,last_charge,charge_status,name
    campaign_two_pages = False
    creator_expired = False   # creator GETs 401 until a successful rotation
    creator_rotate_ok = True
    webhooks = []             # webhook resources already on the campaign
    webhook_secret_new = "wh-secret-created"
    patched = []              # [(url, json)] webhook PATCHes
    role_calls = []           # [(method, role_id)] Discord role PUT/DELETEs
    guild_member_roles = {}   # discord_id -> current role ids (missing => [])

    @classmethod
    def reset(cls):
        cls.patreon_status = "active_patron"
        cls.patreon_tier = "Apex"
        cls.patreon_entitled = None
        cls.patreon_user_id = "patreon-user-1"
        cls.dm_open_ok = True
        cls.dm_send_ok = True
        cls.channel_post_ok = True
        cls.dms = []
        cls.channel_posts = []
        cls.campaign_members = []
        cls.campaign_two_pages = False
        cls.creator_expired = False
        cls.creator_rotate_ok = True
        cls.webhooks = []
        cls.webhook_secret_new = "wh-secret-created"
        cls.patched = []
        cls.role_calls = []
        cls.guild_member_roles = {}


def _patreon_identity_payload():
    # A membership may be entitled to SEVERAL tiers at once (live example: the free
    # tier stays entitled beside the paid one after a free member upgrades). The
    # single-title shape stays the default so every older test keeps its payload.
    titles = (list(HTTP.patreon_entitled) if HTTP.patreon_entitled is not None
              else ([HTTP.patreon_tier] if HTTP.patreon_tier else []))
    refs = [{"id": "tier-%d" % i} for i in range(1, len(titles) + 1)]
    included = [{
        "type": "member", "id": "member-1",
        "attributes": {"patron_status": HTTP.patreon_status,
                       "currently_entitled_amount_cents": 500,
                       "last_charge_date": "2026-07-01T00:00:00+00:00",
                       "next_charge_date": "2026-08-01T00:00:00+00:00",
                       "pledge_relationship_start": "2026-07-01T00:00:00+00:00"},
        "relationships": {"currently_entitled_tiers": {"data": refs},
                          "campaign": {"data": {"id": "campaign-1"}}},
    }]
    for i, title in enumerate(titles, 1):
        included.append({"type": "tier", "id": "tier-%d" % i,
                         "attributes": {"title": title}})
    return {"data": {"id": HTTP.patreon_user_id,
                     "attributes": {"full_name": "Test Patron"}},
            "included": included}


def _member_resource(m):
    """One JSON:API member resource + its included tier resources, the shape both
    the members endpoint and the webhook payload carry."""
    titles = m.get("titles") or []
    tids = [{"id": "ct-%s-%d" % (m["pid"], i)} for i in range(len(titles))]
    inc = [{"type": "tier", "id": t["id"], "attributes": {"title": title}}
           for t, title in zip(tids, titles)]
    res = {"type": "member", "id": "member-%s" % m["pid"],
           "attributes": {"patron_status": m.get("status"),
                          "currently_entitled_amount_cents": m.get("cents"),
                          "last_charge_date": m.get("last_charge"),
                          "last_charge_status": m.get("charge_status"),
                          "next_charge_date": m.get("next_charge"),
                          "pledge_relationship_start": m.get("since"),
                          "full_name": m.get("name")},
           "relationships": {"currently_entitled_tiers": {"data": tids},
                             "user": {"data": {"type": "user", "id": str(m["pid"])}},
                             "campaign": {"data": {"id": "campaign-1"}}}}
    return res, inc


class FakeAsyncClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, **k):
        if "patreon.com/api/oauth2/v2/identity" in url:
            return _Resp(200, _patreon_identity_payload())
        if "patreon.com/api/oauth2/v2/webhooks" in url:
            if HTTP.creator_expired:
                return _Resp(401, {}, "unauthorized")
            return _Resp(200, {"data": [dict(w) for w in HTTP.webhooks]})
        if "patreon.com/api/oauth2/v2/campaigns/" in url and "/members" in url:
            if HTTP.creator_expired:
                return _Resp(401, {}, "unauthorized")
            data, included = [], []
            for m in HTTP.campaign_members:
                res, inc = _member_resource(m)
                data.append(res)
                included.extend(inc)
            if HTTP.campaign_two_pages:
                half = max(1, len(data) // 2)
                if "cursorpage2" not in url:
                    return _Resp(200, {"data": data[:half], "included": included,
                                       "links": {"next": url + "&cursorpage2=1"}})
                return _Resp(200, {"data": data[half:], "included": included})
            return _Resp(200, {"data": data, "included": included})
        if "discord.com" in url and "/guilds/" in url and "/members/" in url:
            did = url.rsplit("/members/", 1)[1].split("/")[0]
            return _Resp(200, {"roles": list(HTTP.guild_member_roles.get(did, [])),
                               "user": {"id": did}})
        raise AssertionError("unexpected GET %s" % url)

    async def request(self, method, url, headers=None, **k):
        if "discord.com" in url and "/roles/" in url:
            HTTP.role_calls.append((method, url.rsplit("/roles/", 1)[1]))
            return _Resp(204, {})
        raise AssertionError("unexpected %s %s" % (method, url))

    async def put(self, url, headers=None, **k):
        return await self.request("PUT", url, headers=headers, **k)

    async def patch(self, url, headers=None, json=None, **k):
        if "patreon.com/api/oauth2/v2/webhooks/" in url:
            HTTP.patched.append((url, json))
            for w in HTTP.webhooks:
                if url.endswith("/" + w["id"]):
                    w["attributes"]["paused"] = False
            return _Resp(200, {"data": {}})
        raise AssertionError("unexpected PATCH %s" % url)

    async def post(self, url, headers=None, json=None, data=None, **k):
        if "patreon.com/api/oauth2/token" in url:
            d = data or {}
            # Only the CREATOR refresh lane is driven here; the seeds make it explicit.
            if d.get("grant_type") == "refresh_token" and str(d.get("refresh_token", "")).startswith("creator-refresh"):
                if not HTTP.creator_rotate_ok:
                    return _Resp(400, {"error": "invalid_grant"})
                HTTP.creator_expired = False
                return _Resp(200, {"access_token": "creator-access-1",
                                   "refresh_token": "creator-refresh-1", "expires_in": 2678400})
            return _Resp(400, {"error": "unsupported_grant_type"})
        if "patreon.com/api/oauth2/v2/webhooks" in url:
            if HTTP.creator_expired:
                return _Resp(401, {})
            att = ((json or {}).get("data") or {}).get("attributes") or {}
            w = {"type": "webhook", "id": "wh-%d" % (len(HTTP.webhooks) + 1),
                 "attributes": {"uri": att.get("uri"), "secret": HTTP.webhook_secret_new,
                                "paused": False, "triggers": list(att.get("triggers") or [])}}
            HTTP.webhooks.append(w)
            return _Resp(201, {"data": w})
        json = json or {}
        if url.endswith("/users/@me/channels"):
            if not HTTP.dm_open_ok:
                return _Resp(403, {}, "cannot send messages to this user")
            HTTP._pending_dm = str(json.get("recipient_id") or "")
            return _Resp(200, {"id": "dm-%s" % HTTP._pending_dm})
        if "/channels/" in url and url.endswith("/messages"):
            chan = url.split("/channels/")[1].split("/")[0]
            content = str(json.get("content") or "")
            if chan.startswith("dm-"):
                if not HTTP.dm_send_ok:
                    return _Resp(500, {}, "boom")
                HTTP.dms.append((chan[3:], content))
                return _Resp(200, {"id": "msg"})
            if not HTTP.channel_post_ok:
                return _Resp(500, {}, "boom")
            HTTP.channel_posts.append((chan, content, json.get("allowed_mentions")))
            return _Resp(200, {"id": "msg"})
        raise AssertionError("unexpected POST %s" % url)


_fake_httpx = types.SimpleNamespace(AsyncClient=FakeAsyncClient)
server.httpx = _fake_httpx


async def drain():
    """Let every _fire()'d notice finish. The notices are deliberately not awaited
    by the money path, so a test that asserts on a DM must wait for them."""
    for _ in range(60):
        pending = [t for t in server._BG_TASKS if not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)
    return


# ---------------------------------------------------------------------------
# helpers over the REAL db
# ---------------------------------------------------------------------------
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


async def txns(uid):
    return [t async for t in db.transactions.find({"user_id": uid}, {"_id": 0})]


# ---------------------------------------------------------------------------
# 1. the subscriber path: sync_patreon_for_user pays instantly
# ---------------------------------------------------------------------------
async def t_sync_pays_on_subscribe():
    print("\n[1] a new subscriber is paid by the REAL sync path")
    for tier_name, key, amount in [("Apex", "apex", 80000), ("Elder", "elder", 60000),
                                   ("Adult", "adult", 40000), ("Sub Adult", "sub", 28000),
                                   ("Juvie", "juvie", 18000)]:
        await reset_state()
        HTTP.patreon_tier = tier_name
        HTTP.patreon_user_id = "patreon-%s" % key
        u = await mk_user(vip_coins=555)
        t0 = datetime.now(timezone.utc)
        status, pid = await server.sync_patreon_for_user(u["id"], "access-token")
        await drain()
        after = await get(u["id"])
        check("%s: sync reports active_patron" % tier_name, status == "active_patron", str(status))
        check("%s: paid %d Amberium on top of the balance" % (tier_name, amount),
              after.get("vip_coins") == 555 + amount, str(after.get("vip_coins")))
        check("%s: joining stamp written" % tier_name,
              bool(after.get("patreon_welcome_amber_at")), "no stamp")
        anchor = after.get("amber_payout_anchor")
        check("%s: the countdown is anchored AT the payment" % tier_name,
              anchor == after.get("patreon_welcome_amber_at")
              and datetime.fromisoformat(anchor) >= t0, str(anchor))
        check("%s: period counter starts at 0" % tier_name,
              after.get("amber_payout_count") == 0, str(after.get("amber_payout_count")))
        rows = await txns(u["id"])
        check("%s: one transaction row explains the coins" % tier_name,
              len(rows) == 1 and rows[0]["amount"] == amount and rows[0]["currency"] == "vip"
              and "bienvenida" in rows[0]["description"], str(rows))
        check("%s: the transaction names the tier" % tier_name,
              bool(rows) and key in rows[0]["description"], str(rows))
        check("%s: exactly one Discord DM went out" % tier_name,
              len(HTTP.dms) == 1, str(HTTP.dms))
        if HTTP.dms:
            msg = HTTP.dms[0][1]
            check("%s: the DM is addressed to the patron's discord id" % tier_name,
                  HTTP.dms[0][0] == after.get("discord_id"), HTTP.dms[0][0])
            check("%s: the DM states the amount" % tier_name,
                  server._amber_es(amount) in msg, msg)
            check("%s: the DM says the next one is in 14 days" % tier_name,
                  "14 d" in msg, msg)
            check("%s: the DM names the tier" % tier_name, tier_name in msg, msg)


async def t_sync_is_idempotent():
    print("\n[2] re-syncing an existing patron never pays again")
    await reset_state()
    u = await mk_user()
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    first = await get(u["id"])
    for _ in range(3):
        await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("balance unchanged after 3 more syncs",
          after.get("vip_coins") == first.get("vip_coins"), str(after.get("vip_coins")))
    check("stamp unchanged", after.get("patreon_welcome_amber_at") == first.get("patreon_welcome_amber_at"))
    check("still exactly one transaction row", len(await txns(u["id"])) == 1)
    check("still exactly one DM", len(HTTP.dms) == 1, str(len(HTTP.dms)))


async def t_free_tier_then_upgrade():
    print("\n[3] an unpriced membership pays nothing, and pays when it becomes a real tier")
    await reset_state()
    HTTP.patreon_tier = "Free"
    u = await mk_user()
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    mid = await get(u["id"])
    check("Free tier paid nothing", mid.get("vip_coins") == 0, str(mid.get("vip_coins")))
    check("Free tier left no stamp", not mid.get("patreon_welcome_amber_at"))
    check("Free tier sent no DM", not HTTP.dms, str(HTTP.dms))
    HTTP.patreon_tier = "Juvie"
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("upgrading off Free pays that tier at once", after.get("vip_coins") == 18000,
          str(after.get("vip_coins")))
    check("one DM on the upgrade", len(HTTP.dms) == 1, str(HTTP.dms))


async def t_multi_tier_entitlement_prefers_paid():
    print("\n[3b] a membership entitled to Free AND a paid tier is paid the paid tier")
    # The live 2026-07-26 shape: joined the free membership first, upgraded to a
    # paid tier, Patreon lists BOTH with "Free" first -- the stored tier must be
    # the paid one and the joining Amberium must go out.
    await reset_state()
    u = await mk_user(vip_coins=100)
    HTTP.patreon_user_id = "patreon-multi-free-first"
    HTTP.patreon_entitled = ["Free", "Juvie"]
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("free-first: the stored tier is the PAID one",
          after.get("patreon_tier_name") == "Juvie", str(after.get("patreon_tier_name")))
    check("free-first: the joining Amberium was paid",
          after.get("vip_coins") == 100 + 18000, str(after.get("vip_coins")))
    check("free-first: joining stamp written", bool(after.get("patreon_welcome_amber_at")))
    check("free-first: one DM went out", len(HTTP.dms) == 1, str(HTTP.dms))

    # Same entitlement with the paid tier first must behave identically.
    await reset_state()
    u = await mk_user()
    HTTP.patreon_user_id = "patreon-multi-paid-first"
    HTTP.patreon_entitled = ["Sub Adult", "Free"]
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("paid-first: the stored tier is the paid one",
          after.get("patreon_tier_name") == "Sub Adult", str(after.get("patreon_tier_name")))
    check("paid-first: paid the sub amount", after.get("vip_coins") == 28000,
          str(after.get("vip_coins")))

    # Two PAID tiers entitled at once: the higher one wins, whatever the order.
    await reset_state()
    u = await mk_user()
    HTTP.patreon_user_id = "patreon-multi-two-paid"
    HTTP.patreon_entitled = ["Juvie", "Apex"]
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("two paid: the higher tier is stored",
          after.get("patreon_tier_name") == "Apex", str(after.get("patreon_tier_name")))
    check("two paid: paid the higher amount", after.get("vip_coins") == 80000,
          str(after.get("vip_coins")))

    # Free alone still pays nothing and is still shown as Free.
    await reset_state()
    u = await mk_user()
    HTTP.patreon_user_id = "patreon-multi-free-only"
    HTTP.patreon_entitled = ["Free"]
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("free only: tier stored as Free", after.get("patreon_tier_name") == "Free",
          str(after.get("patreon_tier_name")))
    check("free only: nothing paid", after.get("vip_coins") == 0, str(after.get("vip_coins")))
    check("free only: no stamp", not after.get("patreon_welcome_amber_at"))

    # An unrecognized title alone keeps today's behaviour: stored, never paid.
    await reset_state()
    u = await mk_user()
    HTTP.patreon_user_id = "patreon-multi-unknown"
    HTTP.patreon_entitled = ["Gold Supporter"]
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("unknown title: stored verbatim", after.get("patreon_tier_name") == "Gold Supporter",
          str(after.get("patreon_tier_name")))
    check("unknown title: nothing paid", after.get("vip_coins") == 0, str(after.get("vip_coins")))


async def t_tier_upgrade_pays_the_difference():
    print("\n[3c] moving UP a tier pays the difference, once, and never restarts the clock")
    # The live 2026-07-29 shape: gerald joined Juvie at 22:52 and upgraded to Sub Adult
    # at 04:26 the next morning. He kept the 18.000 and never saw the 28.000 the Sub
    # Adult tier is sold with.
    await reset_state()
    HTTP.patreon_user_id = "patreon-upgrade-juvie-sub"
    HTTP.patreon_tier = "Juvie"
    u = await mk_user(vip_coins=25)
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    joined = await get(u["id"])
    check("upgrade: joining payment landed at the juvie amount",
          joined.get("vip_coins") == 25 + 18000, str(joined.get("vip_coins")))
    check("upgrade: the exact figure paid is recorded",
          joined.get("patreon_welcome_amber_total") == 18000,
          str(joined.get("patreon_welcome_amber_total")))
    anchor0 = joined.get("amber_payout_anchor")
    stamp0 = joined.get("patreon_welcome_amber_at")

    HTTP.patreon_tier = "Sub Adult"
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("upgrade: the DIFFERENCE was paid, not a second full payment",
          after.get("vip_coins") == 25 + 28000, str(after.get("vip_coins")))
    check("upgrade: the running total is now the new tier's amount",
          after.get("patreon_welcome_amber_total") == 28000,
          str(after.get("patreon_welcome_amber_total")))
    check("upgrade: the paid-tier key moved with it",
          after.get("patreon_welcome_amber_tier") == "sub",
          str(after.get("patreon_welcome_amber_tier")))
    check("upgrade: stamped with when the top-up happened",
          bool(after.get("patreon_welcome_amber_upgraded_at")))
    check("upgrade: the 14-day countdown is NOT restarted",
          after.get("amber_payout_anchor") == anchor0, str(after.get("amber_payout_anchor")))
    check("upgrade: the original joining stamp is untouched",
          after.get("patreon_welcome_amber_at") == stamp0)
    rows = await txns(u["id"])
    check("upgrade: exactly two transaction rows", len(rows) == 2, str(rows))
    top = [r for r in rows if r["amount"] == 10000]
    check("upgrade: the top-up row is the difference and names the new tier",
          len(top) == 1 and "sub" in top[0]["description"] and "mejora" in top[0]["description"],
          str(rows))
    check("upgrade: a second DM went out", len(HTTP.dms) == 2, str(HTTP.dms))
    if len(HTTP.dms) == 2:
        msg = HTTP.dms[1][1]
        check("upgrade: the DM says it is the difference", "diferencia" in msg, msg)
        check("upgrade: the DM states the amount", server._amber_es(10000) in msg, msg)
        check("upgrade: the DM does not claim a fresh subscription",
              "suscribirte" not in msg, msg)

    # Re-syncing at the same tier pays nothing more, however many times it runs.
    for _ in range(3):
        await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    settled = await get(u["id"])
    check("upgrade: further syncs at the same tier pay nothing",
          settled.get("vip_coins") == 25 + 28000, str(settled.get("vip_coins")))
    check("upgrade: still exactly two rows", len(await txns(u["id"])) == 2)
    check("upgrade: still exactly two DMs", len(HTTP.dms) == 2, str(len(HTTP.dms)))


async def t_tier_upgrade_edges():
    print("\n[3d] the top-up refuses every case that is not a real upgrade")
    # A DOWNGRADE pays nothing and claws nothing back.
    await reset_state()
    HTTP.patreon_user_id = "patreon-downgrade"
    HTTP.patreon_tier = "Apex"
    u = await mk_user()
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    HTTP.patreon_tier = "Juvie"
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("downgrade: balance untouched", after.get("vip_coins") == 80000,
          str(after.get("vip_coins")))
    check("downgrade: the running total still reads the higher amount",
          after.get("patreon_welcome_amber_total") == 80000,
          str(after.get("patreon_welcome_amber_total")))
    check("downgrade: one transaction row only", len(await txns(u["id"])) == 1)

    # ...and re-upgrading afterwards pays NOTHING, because the account has already had
    # the apex joining value. This is the anti-farm invariant.
    HTTP.patreon_tier = "Apex"
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    again = await get(u["id"])
    check("down-then-up: still exactly the apex joining value once",
          again.get("vip_coins") == 80000, str(again.get("vip_coins")))
    check("down-then-up: still one transaction row", len(await txns(u["id"])) == 1)

    # A patron who NEVER had a joining payment is not topped up behind the joining
    # payment's back -- the joining claim owns that case.
    await reset_state()
    u = await mk_user(patreon_id="p-nojoin", patreon_patron_status="active_patron",
                      patreon_tier_name="Apex", vip_coins=7)
    paid = await server._patreon_topup_welcome_amber(await get(u["id"]))
    after = await get(u["id"])
    check("no joining payment: the top-up refuses", paid == 0, str(paid))
    check("no joining payment: balance untouched", after.get("vip_coins") == 7,
          str(after.get("vip_coins")))

    # A lapsed patron is never topped up.
    await reset_state()
    u = await mk_user(patreon_id="p-lapsed", patreon_patron_status="former_patron",
                      patreon_tier_name="Apex", vip_coins=3,
                      patreon_welcome_amber_at=iso_ago(days=2),
                      patreon_welcome_amber_tier="juvie")
    paid = await server._patreon_topup_welcome_amber(await get(u["id"]))
    check("lapsed patron: the top-up refuses", paid == 0, str(paid))
    check("lapsed patron: balance untouched", (await get(u["id"])).get("vip_coins") == 3)

    # An UNPRICED new tier ("Free") never pays and never rewrites the stored total.
    await reset_state()
    u = await mk_user(patreon_id="p-tofree", patreon_patron_status="active_patron",
                      patreon_tier_name="Free", vip_coins=18000,
                      patreon_welcome_amber_at=iso_ago(days=1),
                      patreon_welcome_amber_tier="juvie",
                      patreon_welcome_amber_total=18000)
    paid = await server._patreon_topup_welcome_amber(await get(u["id"]))
    after = await get(u["id"])
    check("to Free: the top-up refuses", paid == 0, str(paid))
    check("to Free: the stored total is untouched",
          after.get("patreon_welcome_amber_total") == 18000)

    # A LEGACY row -- paid before the total was recorded -- is priced from its tier key
    # and topped up correctly. This is the shape every live patron carries today.
    await reset_state()
    u = await mk_user(patreon_id="p-legacy", patreon_patron_status="active_patron",
                      patreon_tier_name="🩷 Sub Adult", vip_coins=100,
                      patreon_welcome_amber_at=iso_ago(days=1),
                      patreon_welcome_amber_tier="juvie")
    paid = await server._patreon_topup_welcome_amber(await get(u["id"]))
    await drain()
    after = await get(u["id"])
    check("legacy row: priced from the tier key it was paid at", paid == 10000, str(paid))
    check("legacy row: balance topped up", after.get("vip_coins") == 100 + 10000,
          str(after.get("vip_coins")))
    check("legacy row: total now recorded exactly",
          after.get("patreon_welcome_amber_total") == 28000)
    check("legacy row: the emoji tier name still resolves to sub",
          after.get("patreon_welcome_amber_tier") == "sub",
          str(after.get("patreon_welcome_amber_tier")))

    # Concurrency: several syncs racing pay the difference exactly ONCE.
    await reset_state()
    u = await mk_user(patreon_id="p-race", patreon_patron_status="active_patron",
                      patreon_tier_name="Apex", vip_coins=0,
                      patreon_welcome_amber_at=iso_ago(days=1),
                      patreon_welcome_amber_tier="juvie",
                      patreon_welcome_amber_total=18000)
    doc = await get(u["id"])
    results = await asyncio.gather(*[server._patreon_topup_welcome_amber(dict(doc))
                                     for _ in range(6)])
    await drain()
    after = await get(u["id"])
    check("race: exactly one caller paid", sum(1 for r in results if r) == 1, str(results))
    check("race: the difference was paid once", after.get("vip_coins") == 62000,
          str(after.get("vip_coins")))
    check("race: exactly one transaction row", len(await txns(u["id"])) == 1,
          str(await txns(u["id"])))

    # ★A row stamped as paid with NO record of the amount (no total, no tier key) must
    # refuse. Pricing it as "nothing paid yet" would hand it a SECOND full joining
    # payment -- this exact shape is what the bi-weekly fixture carries, and the first
    # draft of the top-up paid it 28.000 twice.
    await reset_state()
    u = await mk_user(patreon_id="p-amountless", patreon_patron_status="active_patron",
                      patreon_tier_name="Sub Adult", vip_coins=500,
                      patreon_welcome_amber_at=iso_ago(days=5))
    paid = await server._patreon_topup_welcome_amber(await get(u["id"]))
    after = await get(u["id"])
    check("unknown amount paid: the top-up refuses", paid == 0, str(paid))
    check("unknown amount paid: balance untouched", after.get("vip_coins") == 500,
          str(after.get("vip_coins")))
    check("unknown amount paid: no transaction row", len(await txns(u["id"])) == 0)
    check("unknown amount paid: reader reports unknown, not zero",
          server._patreon_welcome_amber_paid(after) is None,
          str(server._patreon_welcome_amber_paid(after)))

    # A recorded total of exactly the tier amount is honoured as "already square".
    await reset_state()
    u = await mk_user(patreon_id="p-square", patreon_patron_status="active_patron",
                      patreon_tier_name="Sub Adult", vip_coins=28000,
                      patreon_welcome_amber_at=iso_ago(days=5),
                      patreon_welcome_amber_tier="sub",
                      patreon_welcome_amber_total=28000)
    check("already square: the top-up pays nothing",
          await server._patreon_topup_welcome_amber(await get(u["id"])) == 0)

    # ★The race above is also held by the tier CAS, because the tier key changes with
    # the payment. The RUNNING TOTAL is the only thing holding this shape: the stored
    # tier key already equals the tier being paid while the recorded total is behind it
    # (a half-applied write, or a hand-repaired row). Here the update does NOT change
    # the tier, so a CAS on the tier alone still matches after the first payment and
    # every racer pays the difference again.
    await reset_state()
    u = await mk_user(patreon_id="p-race-total", patreon_patron_status="active_patron",
                      patreon_tier_name="Apex", vip_coins=0,
                      patreon_welcome_amber_at=iso_ago(days=1),
                      patreon_welcome_amber_tier="apex",
                      patreon_welcome_amber_total=18000)
    doc = await get(u["id"])
    results = await asyncio.gather(*[server._patreon_topup_welcome_amber(dict(doc))
                                     for _ in range(6)])
    await drain()
    after = await get(u["id"])
    check("stale-total race: exactly one caller paid",
          sum(1 for r in results if r) == 1, str(results))
    check("stale-total race: the difference was paid exactly once",
          after.get("vip_coins") == 62000, str(after.get("vip_coins")))
    check("stale-total race: exactly one transaction row",
          len(await txns(u["id"])) == 1, str(await txns(u["id"])))

    # The alt guard: another account already holds this membership's joining stamp.
    await reset_state()
    await mk_user(id="owner-acct", patreon_welcome_amber_patreon_id="p-shared",
                  patreon_welcome_amber_at=iso_ago(days=3))
    alt = await mk_user(patreon_id="p-shared", patreon_patron_status="active_patron",
                        patreon_tier_name="Apex", vip_coins=0,
                        patreon_welcome_amber_at=iso_ago(days=1),
                        patreon_welcome_amber_tier="juvie")
    paid = await server._patreon_topup_welcome_amber(await get(alt["id"]))
    check("alt account: the top-up refuses", paid == 0, str(paid))
    check("alt account: balance untouched", (await get(alt["id"])).get("vip_coins") == 0)


async def t_upgrade_backstop_in_payout_pass():
    print("\n[3e] the bi-weekly pass squares up an upgrade the sync paths missed")
    await reset_state()
    u = await mk_user(patreon_id="p-backstop", patreon_patron_status="active_patron",
                      patreon_tier_name="Apex", vip_coins=0,
                      patreon_welcome_amber_at=iso_ago(days=1),
                      patreon_welcome_amber_tier="juvie",
                      patreon_welcome_amber_total=18000,
                      amber_payout_anchor=iso_ago(days=1), amber_payout_count=0)
    nowt = datetime.now(timezone.utc)
    period = timedelta(days=server.PATREON_PAYOUT_DAYS)
    got = await server._patreon_payout_one(await get(u["id"]), nowt, period)
    await drain()
    after = await get(u["id"])
    check("backstop: no bi-weekly period is due yet", got == 0, str(got))
    check("backstop: the upgrade difference was still paid",
          after.get("vip_coins") == 62000, str(after.get("vip_coins")))
    check("backstop: total updated", after.get("patreon_welcome_amber_total") == 80000)

    # A pass that ALSO owes a recurring period pays both, and the recurring one is
    # priced at the NEW tier.
    await reset_state()
    u = await mk_user(patreon_id="p-backstop2", patreon_patron_status="active_patron",
                      patreon_tier_name="Apex", vip_coins=0,
                      patreon_welcome_amber_at=iso_ago(days=20),
                      patreon_welcome_amber_tier="juvie",
                      patreon_welcome_amber_total=18000,
                      amber_payout_anchor=iso_ago(days=20), amber_payout_count=0)
    got = await server._patreon_payout_one(await get(u["id"]), nowt, period)
    await drain()
    after = await get(u["id"])
    check("backstop+recurring: the recurring period paid the NEW tier amount",
          got == 80000, str(got))
    check("backstop+recurring: both payments landed",
          after.get("vip_coins") == 62000 + 80000, str(after.get("vip_coins")))
    check("backstop+recurring: the period counter moved once",
          after.get("amber_payout_count") == 1, str(after.get("amber_payout_count")))


async def t_amber_ledger_audit():
    print("\n[3f] the ledger audit repairs every shape of shortfall on its own")
    await reset_state()
    # Four active patrons, four different faults, plus two that must be left alone.
    short_up = await mk_user(patreon_id="a-up", patreon_patron_status="active_patron",
                             patreon_tier_name="Apex", vip_coins=18000,
                             patreon_welcome_amber_at=iso_ago(days=2),
                             patreon_welcome_amber_tier="juvie",
                             patreon_welcome_amber_total=18000)
    never = await mk_user(patreon_id="a-never", patreon_patron_status="active_patron",
                          patreon_tier_name="🟣Adult", vip_coins=0)
    legacy = await mk_user(patreon_id="a-legacy", patreon_patron_status="active_patron",
                           patreon_tier_name="🩷 Sub Adult", vip_coins=18000,
                           patreon_welcome_amber_at=iso_ago(days=3),
                           patreon_welcome_amber_tier="juvie")
    renamed = await mk_user(patreon_id="a-renamed", patreon_patron_status="active_patron",
                            patreon_tier_name="Guardián del Parque", vip_coins=5,
                            patreon_welcome_amber_at=iso_ago(days=1),
                            patreon_welcome_amber_tier="sub",
                            patreon_welcome_amber_total=28000)
    square = await mk_user(patreon_id="a-square", patreon_patron_status="active_patron",
                           patreon_tier_name="🔥Apex", vip_coins=80000,
                           patreon_welcome_amber_at=iso_ago(days=4),
                           patreon_welcome_amber_tier="apex",
                           patreon_welcome_amber_total=80000)
    lapsed = await mk_user(patreon_id="a-lapsed", patreon_patron_status="former_patron",
                           patreon_tier_name="Apex", vip_coins=0,
                           patreon_welcome_amber_at=iso_ago(days=9),
                           patreon_welcome_amber_tier="juvie",
                           patreon_welcome_amber_total=18000)
    s = await server.patreon_amber_audit_once()
    await drain()
    check("audit: only active patrons are checked", s["checked"] == 5, str(s))
    check("audit: three accounts repaired", s["repaired"] == 3, str(s))
    check("audit: the repaired Amberium is reported",
          s["amber"] == 62000 + 40000 + 10000, str(s))
    check("audit: the unpriceable tier is counted, not skipped silently",
          s["unpriced"] == 1, str(s))
    check("audit: no errors", s["errors"] == 0, str(s))
    check("audit: an upgrade shortfall is squared up",
          (await get(short_up["id"])).get("vip_coins") == 80000,
          str((await get(short_up["id"])).get("vip_coins")))
    check("audit: a patron who never got the joining payment is paid",
          (await get(never["id"])).get("vip_coins") == 40000,
          str((await get(never["id"])).get("vip_coins")))
    check("audit: a legacy row with no recorded total is priced from its tier",
          (await get(legacy["id"])).get("vip_coins") == 28000,
          str((await get(legacy["id"])).get("vip_coins")))
    check("audit: a renamed tier pays nothing and takes nothing",
          (await get(renamed["id"])).get("vip_coins") == 5,
          str((await get(renamed["id"])).get("vip_coins")))
    check("audit: an account already square is untouched",
          (await get(square["id"])).get("vip_coins") == 80000)
    check("audit: a lapsed patron is never touched",
          (await get(lapsed["id"])).get("vip_coins") == 0)
    stamps = [(await get(u["id"])).get("patreon_amber_audited_at")
              for u in (short_up, never, legacy, renamed, square)]
    check("audit: every account it looked at is stamped", all(stamps), str(stamps))
    check("audit: it did not stamp the lapsed account",
          not (await get(lapsed["id"])).get("patreon_amber_audited_at"))

    # A SECOND pass is a no-op: the ledger is square, so nothing is paid twice.
    s2 = await server.patreon_amber_audit_once()
    await drain()
    check("audit: the second pass repairs nothing", s2["repaired"] == 0, str(s2))
    check("audit: the second pass still reports the unpriced tier", s2["unpriced"] == 1, str(s2))
    check("audit: balances unchanged by the second pass",
          (await get(short_up["id"])).get("vip_coins") == 80000
          and (await get(never["id"])).get("vip_coins") == 40000
          and (await get(legacy["id"])).get("vip_coins") == 28000)


async def t_amber_audit_is_bounded_and_never_starves():
    print("\n[3g] the audit is bounded, rotates oldest-first, and one bad row cannot block it")
    await reset_state()
    for i in range(7):
        await mk_user(patreon_id="b-%d" % i, patreon_patron_status="active_patron",
                      patreon_tier_name="Juvie", vip_coins=0)
    s = await server.patreon_amber_audit_once(limit=3)
    check("bounded: the batch limit is honoured", s["checked"] == 3, str(s))
    stamped = await db.users.count_documents({"patreon_amber_audited_at": {"$exists": True}})
    check("bounded: exactly the batch was stamped", stamped == 3, str(stamped))
    s2 = await server.patreon_amber_audit_once(limit=3)
    check("rotation: the next pass takes the NEXT three, never the same three",
          s2["checked"] == 3 and
          await db.users.count_documents({"patreon_amber_audited_at": {"$exists": True}}) == 6,
          str(s2))

    # ★A row whose repair RAISES must still be stamped, or it sits at the head of the
    # queue forever and every account behind it is never audited again.
    await reset_state()
    bad = await mk_user(patreon_id="b-bad", patreon_patron_status="active_patron",
                        patreon_tier_name="Apex", vip_coins=0,
                        patreon_welcome_amber_at=iso_ago(days=2),
                        patreon_welcome_amber_tier="juvie",
                        patreon_welcome_amber_total=18000)
    good = await mk_user(patreon_id="b-good", patreon_patron_status="active_patron",
                         patreon_tier_name="Juvie", vip_coins=0)
    real_topup = server._patreon_topup_welcome_amber

    async def boom(u):
        if u.get("patreon_id") == "b-bad":
            raise RuntimeError("simulated repair failure")
        return await real_topup(u)

    server._patreon_topup_welcome_amber = boom
    try:
        s = await server.patreon_amber_audit_once()
        await drain()
    finally:
        server._patreon_topup_welcome_amber = real_topup
    check("containment: the failure is counted", s["errors"] == 1, str(s))
    check("containment: the healthy account behind it was still paid",
          (await get(good["id"])).get("vip_coins") == 18000,
          str((await get(good["id"])).get("vip_coins")))
    check("containment: ★the FAILED row is stamped anyway, so it cannot starve rotation",
          bool((await get(bad["id"])).get("patreon_amber_audited_at")))
    check("containment: the failed row was not paid", (await get(bad["id"])).get("vip_coins") == 0)


async def t_admin_view_reports_the_money_gap():
    print("\n[3h] the admin view answers 'is anybody owed money right now?'")
    await reset_state()
    await _wipe_creator_state()
    await db.patreon_members.insert_many([
        {"patreon_id": "m-short", "member_id": "mm-1", "status": "active_patron",
         "tier_name": "Apex", "pledge_cents": 5500, "since": iso_ago(days=3)},
        {"patreon_id": "m-square", "member_id": "mm-2", "status": "active_patron",
         "tier_name": "Juvie", "pledge_cents": 1650, "since": iso_ago(days=2)},
        {"patreon_id": "m-unlinked", "member_id": "mm-3", "status": "active_patron",
         "tier_name": "Juvie", "pledge_cents": 1650, "since": iso_ago(days=1)},
    ])
    await mk_user(patreon_id="m-short", persona_name="Shorty",
                  patreon_patron_status="active_patron", patreon_tier_name="Apex",
                  patreon_welcome_amber_at=iso_ago(days=3),
                  patreon_welcome_amber_tier="juvie", patreon_welcome_amber_total=18000)
    await mk_user(patreon_id="m-square", persona_name="Square",
                  patreon_patron_status="active_patron", patreon_tier_name="Juvie",
                  patreon_welcome_amber_at=iso_ago(days=2),
                  patreon_welcome_amber_tier="juvie", patreon_welcome_amber_total=18000)
    payload = await server.admin_patreon_members(admin={"id": "admin", "role": "admin"})
    by_pid = {m["patreon_id"]: m for m in payload["members"]}
    check("admin view: the short account names the exact gap",
          by_pid["m-short"]["amber"] == {"owed": 80000, "paid": 18000, "short": 62000,
                                         "audited_at": None},
          str(by_pid["m-short"]["amber"]))
    check("admin view: a square account reads zero short",
          by_pid["m-square"]["amber"]["short"] == 0, str(by_pid["m-square"]["amber"]))
    check("admin view: an unlinked payer has no money row to report",
          by_pid["m-unlinked"]["amber"]["owed"] is None and not by_pid["m-unlinked"]["linked"],
          str(by_pid["m-unlinked"]))
    s = payload["summary"]
    check("admin view: the summary counts who is owed", s["amber_short_accounts"] == 1, str(s))
    check("admin view: the summary totals what is owed", s["amber_short_total"] == 62000, str(s))
    check("admin view: unlinked payers are still counted", s["active_unlinked"] == 1, str(s))

    # After the audit runs, the summary must read zero -- that is the whole promise.
    await server.patreon_amber_audit_once()
    await drain()
    after = await server.admin_patreon_members(admin={"id": "admin", "role": "admin"})
    check("admin view: ★the audit drives 'owed right now' to zero",
          after["summary"]["amber_short_accounts"] == 0
          and after["summary"]["amber_short_total"] == 0, str(after["summary"]))
    check("admin view: the audit stamp is surfaced",
          bool({m["patreon_id"]: m for m in after["members"]}["m-short"]["amber"]["audited_at"]))


async def _wipe_creator_state():
    await db.patreon_members.delete_many({})
    await db.settings.delete_many({"_id": {"$in": ["patreon_webhook", "patreon_creator"]}})


async def t_webhook_lane():
    print("\n[3c] the members webhook: signature gate, instant apply, containment")
    await reset_state()
    await _wipe_creator_state()
    await db.settings.insert_one({"_id": "patreon_webhook", "secret": "s3cr3t",
                                  "uri": "https://laislanublar.net/api/patreon/webhook"})
    u = await mk_user()
    await db.users.update_one({"id": u["id"]}, {"$set": {"patreon_id": "777001"}})
    res, inc = _member_resource({"pid": "777001", "status": "active_patron",
                                 "titles": ["Free", "Juvie"], "cents": 1650,
                                 "since": "2026-07-26T00:00:00+00:00",
                                 "last_charge": "2026-07-26T00:00:01+00:00",
                                 "charge_status": "Paid", "name": "Hook Patron"})
    raw = _json.dumps({"data": res, "included": inc}).encode("utf-8")
    good = hmac.new(b"s3cr3t", raw, hashlib.md5).hexdigest()
    code, _d = await server._patreon_webhook_handle(raw, "deadbeefdeadbeefdeadbeefdeadbeef", "members:update")
    check("bad signature is refused", code == 403, str(code))
    after = await get(u["id"])
    check("bad signature wrote nothing", after.get("patreon_patron_status") is None)
    code, _d = await server._patreon_webhook_handle(raw, good, "members:update")
    await drain()
    check("good signature accepted", code == 200, str(code))
    after = await get(u["id"])
    check("webhook stored the PAID tier", after.get("patreon_tier_name") == "Juvie",
          str(after.get("patreon_tier_name")))
    check("webhook paid the joining amber instantly", after.get("vip_coins") == 18000,
          str(after.get("vip_coins")))
    check("webhook DM went out", len(HTTP.dms) == 1, str(HTTP.dms))
    puts = sorted(r[1] for r in HTTP.role_calls if r[0] == "PUT")
    check("tier + supporter roles granted by the webhook", puts == ["9005", "9006"], str(HTTP.role_calls))
    mrow = await db.patreon_members.find_one({"patreon_id": "777001"}, {"_id": 0})
    check("member mirrored", bool(mrow) and mrow.get("status") == "active_patron", str(mrow))
    code, _d = await server._patreon_webhook_handle(raw, good, "members:update")
    await drain()
    check("a redelivered event never pays again",
          (await get(u["id"])).get("vip_coins") == 18000)
    res2, inc2 = _member_resource({"pid": "777002", "status": "active_patron",
                                   "titles": ["Apex"], "cents": 8000, "name": "Never Linked"})
    raw2 = _json.dumps({"data": res2, "included": inc2}).encode("utf-8")
    code, _d = await server._patreon_webhook_handle(
        raw2, hmac.new(b"s3cr3t", raw2, hashlib.md5).hexdigest(), "members:pledge:create")
    check("a paid member with no site account is accepted", code == 200)
    check("and lands in the mirror",
          bool(await db.patreon_members.find_one({"patreon_id": "777002"})))
    rawj = b"this is not json"
    code, _d = await server._patreon_webhook_handle(
        rawj, hmac.new(b"s3cr3t", rawj, hashlib.md5).hexdigest(), "members:update")
    check("junk body with a valid signature is contained (200)", code == 200, str(code))
    res3, inc3 = _member_resource({"pid": "777001", "status": None, "titles": [],
                                   "name": "Hook Patron"})
    raw3 = _json.dumps({"data": res3, "included": inc3}).encode("utf-8")
    await server._patreon_webhook_handle(
        raw3, hmac.new(b"s3cr3t", raw3, hashlib.md5).hexdigest(), "members:delete")
    after3 = await get(u["id"])
    check("a delete event clears the status", after3.get("patreon_patron_status") is None)
    check("and never touches the money", after3.get("vip_coins") == 18000)
    code, _d = await server._patreon_webhook_handle(raw, "", "members:update")
    check("missing signature is refused", code == 403)


async def t_creator_reconcile():
    print("\n[3d] the reconcile pass: campaign truth with NO user tokens involved")
    await reset_state()
    await _wipe_creator_state()
    u = await mk_user()
    await db.users.update_one({"id": u["id"]}, {"$set": {"patreon_id": "888001"}})
    HTTP.campaign_members = [
        {"pid": "888001", "status": "active_patron", "titles": ["Free", "Sub Adult"],
         "cents": 2550, "since": "2026-07-25T00:00:00+00:00",
         "last_charge": "2026-07-26T01:00:00+00:00", "charge_status": "Paid",
         "name": "Silent Sub"},
        {"pid": "888002", "status": "active_patron", "titles": ["Apex"], "cents": 8000,
         "name": "Paid Unlinked"},
        {"pid": "888003", "status": None, "titles": ["Free"], "cents": 0, "name": "Free Join"},
    ]
    s = await server.patreon_creator_reconcile_once()
    await drain()
    check("pass saw every member", s["members"] == 3, str(s))
    check("pass counted both payers", s["active"] == 2, str(s))
    check("pass applied exactly the linked payer", s["applied"] == 1, str(s))
    check("pass flagged the paid-but-unlinked member", s["unlinked_paid"] == 1, str(s))
    after = await get(u["id"])
    check("reconcile stored the PAID tier", after.get("patreon_tier_name") == "Sub Adult",
          str(after.get("patreon_tier_name")))
    check("reconcile paid the welcome with NO user token", after.get("vip_coins") == 28000,
          str(after.get("vip_coins")))
    check("reconcile DM went out", len(HTTP.dms) == 1, str(HTTP.dms))
    check("mirror holds all three", await db.patreon_members.count_documents({}) == 3)
    HTTP.dms = []
    s2 = await server.patreon_creator_reconcile_once()
    await drain()
    check("steady state applies nothing", s2["applied"] == 0, str(s2))
    check("steady state pays nothing", (await get(u["id"])).get("vip_coins") == 28000)
    HTTP.campaign_members[0]["titles"] = ["Free", "Apex"]
    HTTP.campaign_members[0]["cents"] = 8000
    s3 = await server.patreon_creator_reconcile_once()
    await drain()
    after3 = await get(u["id"])
    check("a tier upgrade lands within one pass",
          after3.get("patreon_tier_name") == "Apex" and s3["applied"] == 1, str(s3))
    # The creator lane pays an upgrade the same way the OAuth lane does: the DIFFERENCE
    # up to the new tier (28.000 sub already paid, apex is 80.000, so +52.000) and never
    # a second full joining payment (which would have read 108.000 here).
    check("an upgrade pays the difference through the reconciler",
          after3.get("vip_coins") == 80000, str(after3.get("vip_coins")))
    check("an upgrade never repays the whole welcome",
          after3.get("vip_coins") != 28000 + 80000, str(after3.get("vip_coins")))
    check("the reconciler records the new running total",
          after3.get("patreon_welcome_amber_total") == 80000,
          str(after3.get("patreon_welcome_amber_total")))
    s4 = await server.patreon_creator_reconcile_once()
    await drain()
    check("a second pass at the upgraded tier pays nothing more",
          (await get(u["id"])).get("vip_coins") == 80000, str(s4))
    HTTP.campaign_members[0]["status"] = "former_patron"
    await server.patreon_creator_reconcile_once()
    after4 = await get(u["id"])
    check("a cancel lands within one pass",
          after4.get("patreon_patron_status") == "former_patron")
    check("a cancel never touches the balance", after4.get("vip_coins") == 80000,
          str(after4.get("vip_coins")))
    gone = HTTP.campaign_members.pop(1)
    await server.patreon_creator_reconcile_once()
    row = await db.patreon_members.find_one({"patreon_id": "888002"}, {"_id": 0})
    check("a vanished member is marked, not deleted",
          bool(row) and bool(row.get("missing_since")), str(row))
    HTTP.campaign_members.append(gone)
    await server.patreon_creator_reconcile_once()
    row = await db.patreon_members.find_one({"patreon_id": "888002"}, {"_id": 0})
    check("a returning member is unmarked", bool(row) and not row.get("missing_since"))
    HTTP.campaign_two_pages = True
    s5 = await server.patreon_creator_reconcile_once()
    check("a paged member list is read to the end", s5["members"] == 3, str(s5))
    HTTP.campaign_two_pages = False


async def t_creator_token_rotation():
    print("\n[3e] creator token: a 401 rotates once and persists the new pair")
    await reset_state()
    await _wipe_creator_state()
    HTTP.campaign_members = [{"pid": "999001", "status": None, "titles": ["Free"],
                              "name": "Bystander"}]
    HTTP.creator_expired = True
    HTTP.creator_rotate_ok = True
    s = await server.patreon_creator_reconcile_once()
    check("a pass survives an expired creator token", s["members"] == 1, str(s))
    doc = await db.settings.find_one({"_id": "patreon_creator"}) or {}
    check("the rotated pair is persisted",
          doc.get("access_token") == "creator-access-1"
          and doc.get("refresh_token") == "creator-refresh-1", str(sorted(doc)))
    await _wipe_creator_state()
    HTTP.creator_expired = True
    HTTP.creator_rotate_ok = False
    failed = False
    try:
        await server.patreon_creator_reconcile_once()
    except Exception:
        failed = True
    check("a failed rotation raises (the loop logs and retries next pass)", failed)
    HTTP.creator_expired = False
    HTTP.creator_rotate_ok = True


async def t_webhook_registration():
    print("\n[3f] webhook self-registration: create, adopt, unpause")
    await reset_state()
    await _wipe_creator_state()
    HTTP.webhooks = []
    ok = await server._patreon_ensure_webhook()
    check("a webhook is created when none exists", ok is True and len(HTTP.webhooks) == 1,
          str(HTTP.webhooks))
    doc = await db.settings.find_one({"_id": "patreon_webhook"}) or {}
    check("its secret is persisted for the signature gate",
          doc.get("secret") == "wh-secret-created", str(sorted(doc)))
    check("it listens to all six member events",
          set(HTTP.webhooks[0]["attributes"]["triggers"]) == set(server._PATREON_WEBHOOK_TRIGGERS))
    ok2 = await server._patreon_ensure_webhook()
    check("an existing webhook is adopted, never duplicated",
          ok2 is True and len(HTTP.webhooks) == 1)
    HTTP.webhooks[0]["attributes"]["paused"] = True
    HTTP.patched = []
    await server._patreon_ensure_webhook()
    check("a paused webhook is unpaused",
          HTTP.webhooks[0]["attributes"]["paused"] is False and len(HTTP.patched) == 1,
          str(HTTP.patched))


async def t_admin_members_view():
    print("\n[3g] admin view: who paid vs who linked")
    await reset_state()
    await _wipe_creator_state()
    u = await mk_user()
    await db.users.update_one({"id": u["id"]}, {"$set": {"patreon_id": "555001"}})
    await server._patreon_mirror_upsert({"patreon_id": "555001", "member_id": "m1",
                                         "status": "active_patron", "tier_name": "Juvie",
                                         "pledge_cents": 1650,
                                         "since": "2026-07-01T00:00:00+00:00",
                                         "full_name": "Linked Larry"})
    await server._patreon_mirror_upsert({"patreon_id": "555002", "member_id": "m2",
                                         "status": "active_patron", "tier_name": "Apex",
                                         "pledge_cents": 8000,
                                         "since": "2026-07-02T00:00:00+00:00",
                                         "full_name": "Ghost Gary"})
    await server._patreon_mirror_upsert({"patreon_id": "555003", "member_id": "m3",
                                         "status": None, "tier_name": "Free",
                                         "full_name": "Free Fred"})
    out = await server.admin_patreon_members(admin={"id": "admin"})
    check("summary counts the campaign",
          out["summary"] == {"total": 3, "active": 2, "active_unlinked": 1,
                             "amber_short_accounts": 0, "amber_short_total": 0,
                             "amber_unpriced_active": 1},
          str(out["summary"]))
    # Larry is mirrored as an active Juvie but his USER row carries no status or tier,
    # so nothing on the site would price him -- exactly the "linked but never applied"
    # hole the unpriced counter exists to surface.
    check("a linked payer whose user row was never applied is surfaced as unpriced",
          out["summary"]["amber_unpriced_active"] == 1, str(out["summary"]))
    by_pid = {m["patreon_id"]: m for m in out["members"]}
    check("a linked member carries the site account",
          by_pid["555001"]["linked"] and by_pid["555001"]["site_user"]["id"] == u["id"])
    check("a paying member with no site account is exposed",
          by_pid["555002"]["linked"] is False and by_pid["555002"]["site_user"] is None)


async def t_not_active_pays_nothing():
    print("\n[4] a membership that is not active_patron is never paid")
    for st in ("declined_patron", "former_patron", None):
        await reset_state()
        HTTP.patreon_status = st
        u = await mk_user()
        await server.sync_patreon_for_user(u["id"], "tok")
        await drain()
        after = await get(u["id"])
        check("status=%s pays nothing" % st, after.get("vip_coins") == 0, str(after.get("vip_coins")))
        check("status=%s leaves no stamp" % st, not after.get("patreon_welcome_amber_at"))
        check("status=%s sends no DM" % st, not HTTP.dms)


# ---------------------------------------------------------------------------
# 2. the money guards
# ---------------------------------------------------------------------------
async def t_alt_account_guard():
    print("\n[5] the same Patreon membership cannot be paid twice from two site accounts")
    await reset_state()
    a = await mk_user()
    await server.sync_patreon_for_user(a["id"], "tok")
    await drain()
    b = await mk_user()
    await server.sync_patreon_for_user(b["id"], "tok")   # same HTTP.patreon_user_id
    await drain()
    after_b = await get(b["id"])
    check("the alt account was refused", after_b.get("vip_coins") == 0, str(after_b.get("vip_coins")))
    check("the alt account carries no stamp", not after_b.get("patreon_welcome_amber_at"))
    check("only the first account got a DM", len(HTTP.dms) == 1, str(HTTP.dms))


async def t_alt_guard_survives_unlink():
    print("\n[6] unlink-here / relink-there cannot mint a second joining payment")
    await reset_state()
    a = await mk_user()
    await server.sync_patreon_for_user(a["id"], "tok")
    await drain()
    paid_a = await get(a["id"])
    check("account A was paid", paid_a.get("vip_coins") == 80000, str(paid_a.get("vip_coins")))
    check("A stores the durable membership id",
          paid_a.get("patreon_welcome_amber_patreon_id") == HTTP.patreon_user_id,
          str(paid_a.get("patreon_welcome_amber_patreon_id")))
    # The REAL unlink route's write, not a hand-rolled one.
    await server.patreon_unlink(user=paid_a)
    unlinked = await get(a["id"])
    check("unlink cleared patreon_id", not unlinked.get("patreon_id"))
    check("unlink kept the joining stamp", bool(unlinked.get("patreon_welcome_amber_at")))
    # NEGATIVE CONTROL: the guard we shipped BEFORE this fix looked for a twin by
    # patreon_id + stamp. After the unlink above that query finds nobody -- i.e. the
    # old shape would have paid the same membership a second time.
    old_shape = await db.users.find_one(
        {"patreon_id": HTTP.patreon_user_id, "id": {"$ne": "x"},
         "patreon_welcome_amber_at": {"$exists": True}})
    check("negative control: the old patreon_id-only guard sees no twin here",
          old_shape is None, str(old_shape))
    b = await mk_user()
    await server.sync_patreon_for_user(b["id"], "tok")
    await drain()
    after_b = await get(b["id"])
    check("the second account is still refused", after_b.get("vip_coins") == 0,
          str(after_b.get("vip_coins")))
    check("no DM for the refused account", len(HTTP.dms) == 1, str(HTTP.dms))


async def t_relink_same_account():
    print("\n[7] unlink then relink the SAME account: the countdown is KEPT, money does not repeat")
    # Behaviour CHANGED 2026-08-16 on the owner's ruling ("if someone disconnects the
    # reconnects timer shouldnt reset"). This test used to assert the opposite -- that
    # the relink re-anchored -- which is exactly the defect a paying Adult patron
    # reported after losing 7.16 days of a 14-day cycle to one accidental unlink.
    await reset_state()
    u = await mk_user()
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    # Serve 9 days of the cycle before the accident, so a reset would be unmistakable.
    served = iso_ago(days=9)
    await db.users.update_one({"id": u["id"]}, {"$set": {"amber_payout_anchor": served}})
    paid = await get(u["id"])
    await server.patreon_unlink(user=paid)
    unlinked = await get(u["id"])
    check("unlink no longer deletes the anchor", unlinked.get("amber_payout_anchor") == served,
          str(unlinked.get("amber_payout_anchor")))
    check("unlink froze the clock", bool(unlinked.get("amber_payout_paused_at")),
          str(unlinked.get("amber_payout_paused_at")))
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("balance is still one payment", after.get("vip_coins") == 80000, str(after.get("vip_coins")))
    check("only one transaction row", len(await txns(u["id"])) == 1)
    check("only one DM", len(HTTP.dms) == 1, str(HTTP.dms))
    check("the relink cleared the freeze", not after.get("amber_payout_paused_at"),
          str(after.get("amber_payout_paused_at")))
    kept = datetime.fromisoformat(after["amber_payout_anchor"])
    age_days = (datetime.now(timezone.utc) - kept).total_seconds() / 86400.0
    # Upper bound is not 9.0: the resume slides the anchor by the measured freeze, which
    # is a few hundred microseconds longer than the freeze itself.
    check("the 9 served days survived the relink", 8.9 < age_days < 9.1, "%.6f days" % age_days)
    check("NEGATIVE CONTROL: the anchor is not a fresh 'now' (the old behaviour)",
          age_days > 1.0, "%.4f days" % age_days)


async def t_long_standing_patron_no_windfall():
    print("\n[8] a patron who has already collected cycles gets no retroactive joining pay")
    await reset_state()
    u = await mk_user(patreon_patron_status="active_patron", patreon_tier_name="Elder",
                      patreon_id="pat-old", vip_coins=120000,
                      amber_payout_anchor=iso_ago(days=40), amber_payout_count=2)
    paid = await server._patreon_pay_welcome_amber(await get(u["id"]))
    await drain()
    after = await get(u["id"])
    check("no joining payment", paid is False and after.get("vip_coins") == 120000,
          str(after.get("vip_coins")))
    check("no stamp written", not after.get("patreon_welcome_amber_at"))
    check("no DM", not HTTP.dms)


async def t_legacy_patron_backstop():
    print("\n[9] a patron who subscribed BEFORE this feature is paid by the pass, once")
    await reset_state()
    u = await mk_user(patreon_patron_status="active_patron", patreon_tier_name="Adult",
                      patreon_id="pat-legacy", vip_coins=10,
                      amber_payout_anchor=iso_ago(days=3))
    nowt = datetime.now(timezone.utc)
    period = timedelta(days=server.PATREON_PAYOUT_DAYS)
    paid = await server._patreon_payout_one(await get(u["id"]), nowt, period)
    await drain()
    after = await get(u["id"])
    check("the pass paid the tier amount", paid == 40000 and after.get("vip_coins") == 40010,
          str((paid, after.get("vip_coins"))))
    check("the countdown re-anchored to now",
          datetime.fromisoformat(after["amber_payout_anchor"]) >= nowt - timedelta(seconds=5),
          after.get("amber_payout_anchor"))
    check("one DM went out", len(HTTP.dms) == 1, str(HTTP.dms))
    again = await server._patreon_payout_one(await get(u["id"]), nowt, period)
    await drain()
    check("a second pass pays nothing", again == 0, str(again))
    check("balance still one payment", (await get(u["id"])).get("vip_coins") == 40010)
    check("still one DM", len(HTTP.dms) == 1, str(HTTP.dms))


# ---------------------------------------------------------------------------
# 3. the recurring pass still works, and now announces
# ---------------------------------------------------------------------------
async def t_recurring_pays_and_dms():
    print("\n[10] the bi-weekly payout still pays and now sends a Discord message")
    await reset_state()
    u = await mk_user(patreon_patron_status="active_patron", patreon_tier_name="Sub Adult",
                      patreon_id="pat-r", vip_coins=0, amber_payout_count=0,
                      patreon_welcome_amber_at=iso_ago(days=15),
                      amber_payout_anchor=iso_ago(days=15))
    nowt = datetime.now(timezone.utc)
    period = timedelta(days=server.PATREON_PAYOUT_DAYS)
    paid = await server._patreon_payout_one(await get(u["id"]), nowt, period)
    await drain()
    after = await get(u["id"])
    check("one period paid", paid == 28000 and after.get("vip_coins") == 28000, str(paid))
    check("period counter advanced", after.get("amber_payout_count") == 1,
          str(after.get("amber_payout_count")))
    check("the recurring DM went out", len(HTTP.dms) == 1, str(HTTP.dms))
    if HTTP.dms:
        msg = HTTP.dms[0][1]
        check("recurring wording is NOT the welcome wording",
              "bienvenid" not in msg.lower() and server._amber_es(28000) in msg, msg)
        check("recurring DM names the tier", "Sub Adult" in msg, msg)
    rows = await txns(u["id"])
    check("the recurring transaction row is the quincenal one",
          len(rows) == 1 and "quincenal" in rows[0]["description"], str(rows))


async def t_recurring_catch_up_and_cas():
    print("\n[11] a missed cycle is caught up once, and a stale pass cannot re-pay it")
    await reset_state()
    u = await mk_user(patreon_patron_status="active_patron", patreon_tier_name="Juvie",
                      patreon_id="pat-c", vip_coins=0, amber_payout_count=0,
                      patreon_welcome_amber_at=iso_ago(days=30),
                      amber_payout_anchor=iso_ago(days=30))
    nowt = datetime.now(timezone.utc)
    period = timedelta(days=server.PATREON_PAYOUT_DAYS)
    stale = await get(u["id"])           # the doc a concurrent pass would still hold
    paid = await server._patreon_payout_one(await get(u["id"]), nowt, period)
    await drain()
    check("two periods paid at once", paid == 36000, str(paid))
    check("balance is two periods", (await get(u["id"])).get("vip_coins") == 36000)
    check("counter is 2", (await get(u["id"])).get("amber_payout_count") == 2)
    check("one DM for the catch-up (not one per period)", len(HTTP.dms) == 1, str(HTTP.dms))
    again = await server._patreon_payout_one(stale, nowt, period)
    await drain()
    check("the CAS rejected the stale pass", again == 0, str(again))
    check("balance did not move", (await get(u["id"])).get("vip_coins") == 36000)
    check("no second DM", len(HTTP.dms) == 1, str(HTTP.dms))


async def t_malformed_rows_are_contained():
    print("\n[12] a malformed row costs that row only, never the pass")
    await reset_state()
    nowt = datetime.now(timezone.utc)
    period = timedelta(days=server.PATREON_PAYOUT_DAYS)
    bad_anchor = await mk_user(patreon_patron_status="active_patron", patreon_tier_name="Apex",
                               patreon_welcome_amber_at=iso_ago(days=20),
                               amber_payout_anchor="not-a-date")
    r1 = await server._patreon_payout_one(await get(bad_anchor["id"]), nowt, period)
    check("unparseable anchor pays nothing and does not raise", r1 == 0, str(r1))
    bad_count = await mk_user(patreon_patron_status="active_patron", patreon_tier_name="Apex",
                              vip_coins=0, patreon_welcome_amber_at=iso_ago(days=20),
                              amber_payout_anchor=iso_ago(days=20), amber_payout_count="")
    r2 = await server._patreon_payout_one(await get(bad_count["id"]), nowt, period)
    await drain()
    check("a non-numeric period counter is treated as zero and still pays", r2 == 80000, str(r2))
    repaired = await get(bad_count["id"])
    check("and the junk counter is repaired to a number", repaired.get("amber_payout_count") == 1,
          repr(repaired.get("amber_payout_count")))
    r2b = await server._patreon_payout_one(repaired, nowt, period)
    check("the repaired row is not paid twice", r2b == 0, str(r2b))
    naive = await mk_user(patreon_patron_status="active_patron", patreon_tier_name="Elder",
                          vip_coins=0, patreon_welcome_amber_at=iso_ago(days=20),
                          amber_payout_anchor=(datetime.now(timezone.utc) - timedelta(days=20))
                          .replace(tzinfo=None).isoformat())
    r_naive = await server._patreon_payout_one(await get(naive["id"]), nowt, period)
    await drain()
    check("an anchor with no timezone is read as UTC and still pays", r_naive == 60000, str(r_naive))
    no_tier = await mk_user(patreon_patron_status="active_patron", patreon_tier_name=None,
                            patreon_welcome_amber_at=iso_ago(days=20),
                            amber_payout_anchor=iso_ago(days=20))
    r3 = await server._patreon_payout_one(await get(no_tier["id"]), nowt, period)
    check("a membership with no priced tier is skipped", r3 == 0, str(r3))


# ---------------------------------------------------------------------------
# 4. the Discord notice itself
# ---------------------------------------------------------------------------
async def t_dm_failure_never_touches_the_money():
    print("\n[13] a closed DM inbox cannot undo or block a payment")
    await reset_state()
    HTTP.dm_open_ok = False          # Discord refuses to open the DM channel
    u = await mk_user()
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after = await get(u["id"])
    check("the money landed anyway", after.get("vip_coins") == 80000, str(after.get("vip_coins")))
    check("the stamp landed anyway", bool(after.get("patreon_welcome_amber_at")))
    check("no DM was recorded", not HTTP.dms, str(HTTP.dms))
    check("nothing was posted to a channel (none configured)", not HTTP.channel_posts,
          str(HTTP.channel_posts))
    await reset_state()
    HTTP.dm_send_ok = False          # channel opens, the message itself fails
    u2 = await mk_user()
    await server.sync_patreon_for_user(u2["id"], "tok")
    await drain()
    check("a failed send still leaves the money", (await get(u2["id"])).get("vip_coins") == 80000)


async def t_fallback_channel_when_configured():
    print("\n[14] with a notice channel configured, an undeliverable DM is re-routed")
    await reset_state()
    HTTP.dm_open_ok = False
    prev = server.DISCORD_PATREON_NOTICE_CHANNEL_ID
    server.DISCORD_PATREON_NOTICE_CHANNEL_ID = "9001"
    try:
        ok = await server._patreon_notify_payout("discord-abc", 80000, "Apex", first=True)
        check("the notice reports delivered", ok is True, str(ok))
        check("it went to the configured channel", len(HTTP.channel_posts) == 1
              and HTTP.channel_posts[0][0] == "9001", str(HTTP.channel_posts))
        if HTTP.channel_posts:
            content = HTTP.channel_posts[0][1]
            mentions = HTTP.channel_posts[0][2]
            check("the patron is mentioned", content.startswith("<@discord-abc>"), content)
            check("only that user can be pinged",
                  (mentions or {}).get("users") == ["discord-abc"], str(mentions))
            check("the amount is in the fallback message", server._amber_es(80000) in content, content)
    finally:
        server.DISCORD_PATREON_NOTICE_CHANNEL_ID = prev
    # And with no discord link at all it is a quiet no-op, never an exception.
    await reset_state()
    ok2 = await server._patreon_notify_payout("", 18000, "Juvie")
    check("no discord id -> no notice, no crash", ok2 is False, str(ok2))


async def t_notice_never_raises():
    print("\n[15] the notice path swallows a transport blow-up")
    await reset_state()

    class Boom(FakeAsyncClient):
        async def post(self, *a, **k):
            raise RuntimeError("network gone")

    server.httpx = types.SimpleNamespace(AsyncClient=Boom)
    try:
        ok = await server._patreon_notify_payout("discord-x", 40000, "Adult", first=True)
        check("a transport failure returns False instead of raising", ok is False, str(ok))
    finally:
        server.httpx = _fake_httpx


# ---------------------------------------------------------------------------
# 5. what the website shows
# ---------------------------------------------------------------------------
async def t_status_route_exposes_welcome():
    print("\n[16] /api/patreon/status tells the panel the joining payment landed")
    await reset_state()
    u = await mk_user()
    before = await server.patreon_status(user=await get(u["id"]))
    check("a non-patron has no welcome stamp in the payload",
          before.get("welcome_paid_at") in (None, ""), str(before.get("welcome_paid_at")))
    await server.sync_patreon_for_user(u["id"], "tok")
    await drain()
    after_doc = await get(u["id"])
    st = await server.patreon_status(user=after_doc)
    check("the payload carries welcome_paid_at once paid",
          st.get("welcome_paid_at") == after_doc.get("patreon_welcome_amber_at"),
          str(st.get("welcome_paid_at")))
    check("the tier amount is still reported", st.get("amber_per_payout") == 80000,
          str(st.get("amber_per_payout")))
    secs = st.get("seconds_remaining")
    check("the countdown starts at a full period",
          isinstance(secs, (int, float)) and secs > (13 * 86400), str(secs))


# ---------------------------------------------------------------------------
# 6. the shipped copy actually says it
# ---------------------------------------------------------------------------
def t_frontend_copy():
    print("\n[17] the two panels tell the player the new rule")
    root = os.path.abspath(os.path.join(BACKEND, "..", "frontend", "src", "components", "common"))
    tiers = open(os.path.join(root, "PatreonTiers.jsx"), encoding="utf-8").read()
    payout = open(os.path.join(root, "PayoutPanel.jsx"), encoding="utf-8").read()
    check("the Patreon tier list states the instant payout",
          'data-testid="patreon-instant-note"' in tiers and "al momento de suscribirte" in tiers)
    check("the locked payout card no longer implies a 14-day wait for the first payment",
          "al suscribirse" in payout and "cada 14 d" in payout)
    check("the active payout card reads welcome_paid_at", "welcome_paid_at" in payout)
    check("the tier list states that an upgrade pays the difference",
          "mejoras a un nivel superior" in tiers and "diferencia" in tiers)
    check("the status route serves that field", "welcome_paid_at" in
          open(os.path.join(BACKEND, "server.py"), encoding="utf-8").read())


# ---------------------------------------------------------------------------
async def main():
    try:
        await t_sync_pays_on_subscribe()
        await t_sync_is_idempotent()
        await t_free_tier_then_upgrade()
        await t_multi_tier_entitlement_prefers_paid()
        await t_tier_upgrade_pays_the_difference()
        await t_tier_upgrade_edges()
        await t_upgrade_backstop_in_payout_pass()
        await t_amber_ledger_audit()
        await t_amber_audit_is_bounded_and_never_starves()
        await t_admin_view_reports_the_money_gap()
        await t_webhook_lane()
        await t_creator_reconcile()
        await t_creator_token_rotation()
        await t_webhook_registration()
        await t_admin_members_view()
        await t_not_active_pays_nothing()
        await t_alt_account_guard()
        await t_alt_guard_survives_unlink()
        await t_relink_same_account()
        await t_long_standing_patron_no_windfall()
        await t_legacy_patron_backstop()
        await t_recurring_pays_and_dms()
        await t_recurring_catch_up_and_cas()
        await t_malformed_rows_are_contained()
        await t_dm_failure_never_touches_the_money()
        await t_fallback_channel_when_configured()
        await t_notice_never_raises()
        await t_status_route_exposes_welcome()
        t_frontend_copy()
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
