"""Streamer Pack — REAL server.py I/O tests (not a logic mirror).

Imports the actual backend/server.py with a fake motor driver injected, swaps in a
fake async Mongo that matches motor's contract for the methods the code uses, and
mocks ONLY the Discord seams (_discord_member_info roles read, _discord_role_call
role write, _discord_post_application message post). Everything under test — the
access decision, the payout writer, the apply/decide endpoints — is the real code.

Run:  python backend/tests_local/test_streamer_pack.py   (or pytest)
"""
import asyncio
import os
import sys
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# ── env BEFORE importing server ──────────────────────────────────────────────
STREAMER_ROLE = "1529887867793445045"
KEY = "test-internal-key-abc"
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "lin_test")
os.environ.setdefault("JWT_SECRET", "test")
os.environ["DISCORD_BOT_TOKEN"] = "botfake"
os.environ["DISCORD_GUILD_ID"] = "1523167556368859286"
os.environ["DISCORD_STREAMER_ROLE_ID"] = STREAMER_ROLE
os.environ["DISCORD_STREAMER_APPS_CHANNEL_ID"] = "9999"
os.environ["LIN_INTERNAL_KEY"] = KEY
os.environ["DISCORD_PATREON_ROLE_IDS"] = "111:Apex,222:Elder,333:Adult,444:Sub Adult,555:Juvie"
os.environ.setdefault("ADMIN_STEAM_IDS", "")

# ── fake motor so server imports without a real mongo/driver ─────────────────
_motor_pkg = types.ModuleType("motor")
_motor_async = types.ModuleType("motor.motor_asyncio")
class _StubClient:
    def __init__(self, *a, **k): pass
    def __getitem__(self, name): return object()
    def get_io_loop(self): return asyncio.get_event_loop()
_motor_async.AsyncIOMotorClient = _StubClient
_motor_pkg.motor_asyncio = _motor_async
sys.modules["motor"] = _motor_pkg
sys.modules["motor.motor_asyncio"] = _motor_async
# pymongo is only used for sentinels and the bulk-write/exception types — shim it too.
# ★Keep this in step with server.py and the modules it imports: a missing name is an
# ImportError at collection time, which reads as "the whole streamer guard vanished".
_pymongo = types.ModuleType("pymongo")
_pymongo.ReturnDocument = types.SimpleNamespace(AFTER=True, BEFORE=False)
_pymongo.DESCENDING = -1


class _UpdateOne:
    def __init__(self, filt, update, upsert=False):
        self.filter, self.update, self.upsert = filt, update, upsert


_pymongo.UpdateOne = _UpdateOne
_pymongo_errors = types.ModuleType("pymongo.errors")


class _DuplicateKeyError(Exception):
    pass


_pymongo_errors.DuplicateKeyError = _DuplicateKeyError
_pymongo.errors = _pymongo_errors
sys.modules["pymongo"] = _pymongo
sys.modules["pymongo.errors"] = _pymongo_errors

import server  # the REAL module

# ── fake async Mongo matching the contract server.py uses ────────────────────
_MISSING = object()

def _match(doc, query):
    for k, cond in query.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        val = doc.get(k, _MISSING)
        if isinstance(cond, dict) and any(op.startswith("$") for op in cond):
            for op, arg in cond.items():
                if op == "$exists":
                    if bool(arg) != (k in doc):
                        return False
                elif op == "$ne":
                    if val == arg:
                        return False
                elif op == "$nin":
                    if val is not _MISSING and val in arg:
                        return False
                elif op == "$in":
                    if val is _MISSING or val not in arg:
                        return False
                else:
                    return False
        else:
            if val is _MISSING or val != cond:
                return False
    return True

def _apply_update(doc, update):
    for op, fields in update.items():
        if op == "$set":
            doc.update(fields)
        elif op == "$inc":
            for f, n in fields.items():
                doc[f] = doc.get(f, 0) + n
        elif op == "$unset":
            for f in fields:
                doc.pop(f, None)

class _Cursor:
    def __init__(self, docs): self._docs = docs
    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield dict(d)
        return gen()

class FakeCollection:
    def __init__(self): self.docs = []
    async def find_one(self, query, projection=None, sort=None):
        matches = [d for d in self.docs if _match(d, query)]
        if sort:
            for key, direction in reversed(sort):
                matches.sort(key=lambda d: d.get(key) or "", reverse=(direction < 0))
        return dict(matches[0]) if matches else None
    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return types.SimpleNamespace(inserted_id="x")
    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                _apply_update(d, update)
                return types.SimpleNamespace(modified_count=1, matched_count=1)
        if upsert:
            nd = {}
            for k, v in query.items():
                if not isinstance(v, dict):
                    nd[k] = v
            _apply_update(nd, update)
            self.docs.append(nd)
        return types.SimpleNamespace(modified_count=0, matched_count=0)
    def find(self, query, projection=None):
        return _Cursor([d for d in self.docs if _match(d, query)])

class FakeDB:
    def __init__(self): self._c = {}
    def __getattr__(self, name):
        # collections are attributes: db.users, db.streamer_applications, ...
        c = self.__dict__.setdefault("_c", {})
        if name not in c:
            c[name] = FakeCollection()
        return c[name]

# ── install fakes + Discord seam mocks ───────────────────────────────────────
server.db = FakeDB()
MEMBER_INFO = {}          # discord_id -> (in_guild, roles)
ROLE_CALLS = []           # (method, discord_id, role_id)
POSTED = []

async def fake_member_info(discord_id, force=False):
    return MEMBER_INFO.get(str(discord_id), (None, None))

async def fake_role_call(method, discord_id, role_id):
    ROLE_CALLS.append((method, str(discord_id), str(role_id)))
    return True

async def fake_post_application(app):
    POSTED.append(dict(app))
    return "MSG-" + str(app.get("id"))

DMS = []                  # (discord_id, content) accepted by Discord
DM_OK = {"v": True}       # flip to False to simulate a closed DM inbox

async def fake_dm(discord_id, content):
    if not DM_OK["v"]:
        return False
    DMS.append((str(discord_id), content))
    return True

server._discord_member_info = fake_member_info
server._discord_role_call = fake_role_call
server._discord_post_application = fake_post_application
# Mock the LOWEST seam (the raw DM call) so the real _streamer_notify_payout logic —
# wording, first-vs-recurring, fallback routing — is the code under test.
server._discord_dm = fake_dm


async def drain():
    """Let _fire()'d notice tasks finish before asserting on them."""
    for _ in range(5):
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)


async def reset_dms():
    """Drain FIRST, then clear: a notice fired by an earlier block completes later and
    would otherwise land inside the next block's window and be counted as its own."""
    await drain()
    DMS.clear()

# don't let the real member cache interfere
server._DISCORD_MEMBER_CACHE = {}

# ── test helpers ─────────────────────────────────────────────────────────────
_results = {"pass": 0, "fail": 0}
def check(name, cond):
    ok = bool(cond)
    _results["pass" if ok else "fail"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok

async def seed_user(**kw):
    u = {"id": kw.get("id"), "steam_id": kw.get("steam_id", "steam-" + str(kw.get("id"))),
         "persona_name": kw.get("persona_name", "P" + str(kw.get("id"))), "coins": 0, "vip_coins": 0}
    u.update(kw)
    await server.db.users.insert_one(u)
    return await server.db.users.find_one({"id": u["id"]})

def now(): return datetime.now(timezone.utc)


async def run():
    print("== _has_streamer_role ==")
    check("role present -> True", server._has_streamer_role([STREAMER_ROLE, "999"]) is True)
    check("role absent -> False", server._has_streamer_role(["999"]) is False)
    check("empty -> False", server._has_streamer_role([]) is False)

    print("== _patreon_access (streamer branch) ==")
    MEMBER_INFO["d1"] = (True, [STREAMER_ROLE])
    u = await seed_user(id="u1", discord_id="d1")
    acc = await server._patreon_access(u, force=True)
    check("streamer allowed", acc["allowed"] is True)
    check("via == streamer", acc["via"] == "streamer")
    check("streamer flag True", acc["streamer"] is True)
    check("skin_creator True for streamer", acc["skin_creator"] is True)
    stored = await server.db.users.find_one({"id": "u1"})
    check("discord_streamer_role persisted", stored.get("discord_streamer_role") == STREAMER_ROLE)
    check("_is_subscriber True for streamer", server._is_subscriber(stored) is True)

    # role removed -> access revoked + stored flag cleared
    MEMBER_INFO["d1"] = (True, ["999"])
    acc2 = await server._patreon_access(await server.db.users.find_one({"id": "u1"}), force=True)
    check("role gone -> not allowed", acc2["allowed"] is False and acc2["streamer"] is False)
    stored2 = await server.db.users.find_one({"id": "u1"})
    check("stored streamer flag cleared", not stored2.get("discord_streamer_role"))
    check("_is_subscriber False after revoke", server._is_subscriber(stored2) is False)

    # tier role AND streamer: tier via wins, streamer flag still set, skin_creator True
    MEMBER_INFO["d2"] = (True, ["555", STREAMER_ROLE])  # Juvie + streamer
    ut = await seed_user(id="u2", discord_id="d2")
    acct = await server._patreon_access(ut, force=True)
    check("tier+streamer: via discord_role", acct["via"] == "discord_role")
    check("tier+streamer: streamer flag True", acct["streamer"] is True)
    check("tier+streamer: skin_creator True (juvie alone would be False)", acct["skin_creator"] is True)

    # Discord unreachable keeps a previously-verified streamer
    MEMBER_INFO["d3"] = (None, None)
    us = await seed_user(id="u3", discord_id="d3", discord_streamer_role=STREAMER_ROLE, discord_in_guild=True)
    accs = await server._patreon_access(us, force=True)
    check("unreachable -> stale streamer grant holds", accs["streamer"] is True and accs["allowed"] is True)

    print("== _streamer_status_for ==")
    MEMBER_INFO["d4"] = (True, [])  # linked, in guild, no role
    u4 = await seed_user(id="u4", discord_id="d4", discord_in_guild=True)
    st = await server._streamer_status_for(u4)
    check("eligible: can_apply True", st["can_apply"] is True and st["is_streamer"] is False)
    check("status configured", st["configured"] is True)
    # not in guild -> cannot apply
    MEMBER_INFO["d5"] = (False, [])
    u5 = await seed_user(id="u5", discord_id="d5")
    st5 = await server._streamer_status_for(u5)
    check("not in guild: can_apply False", st5["can_apply"] is False and st5["in_guild"] is False)
    # not discord-linked
    u6 = await seed_user(id="u6")
    st6 = await server._streamer_status_for(u6)
    check("no discord: can_apply False", st6["can_apply"] is False and st6["discord_linked"] is False)

    print("== streamer_apply ==")
    from fastapi import HTTPException
    body = server.StreamerApplyInput(platform="Twitch", channel_url="https://twitch.tv/x",
                                     followers="1000", avg_viewers="30", about="I stream the isle daily.")
    r = await server.streamer_apply(body, user=await server.db.users.find_one({"id": "u4"}))
    check("apply ok -> pending", r["ok"] and r["status"] == "pending")
    posted = await server.db.streamer_applications.find_one({"user_id": "u4"})
    check("application stored pending", posted and posted["status"] == "pending")
    check("message posted + id saved", posted.get("message_id", "").startswith("MSG-") and posted.get("posted") is True)
    # duplicate pending
    try:
        await server.streamer_apply(body, user=await server.db.users.find_one({"id": "u4"}))
        check("duplicate pending rejected", False)
    except HTTPException as e:
        check("duplicate pending -> 409 already_pending", e.status_code == 409 and e.detail == "already_pending")
    # already streamer
    MEMBER_INFO["d1"] = (True, [STREAMER_ROLE])
    try:
        await server.streamer_apply(body, user=await server.db.users.find_one({"id": "u1"}))
        check("already streamer rejected", False)
    except HTTPException as e:
        check("already streamer -> 409", e.status_code == 409 and e.detail == "already_streamer")
    # linked but not in guild -> guild_join_required (NOT discord_required — distinct action)
    try:
        await server.streamer_apply(body, user=await server.db.users.find_one({"id": "u5"}))
        check("not-in-guild rejected", False)
    except HTTPException as e:
        check("not in guild -> 400 guild_join_required", e.status_code == 400 and e.detail == "guild_join_required")
    # no discord linked at all -> discord_link_required
    await seed_user(id="unolink")
    try:
        await server.streamer_apply(body, user=await server.db.users.find_one({"id": "unolink"}))
        check("no-discord rejected", False)
    except HTTPException as e:
        check("no discord -> 400 discord_link_required", e.status_code == 400 and e.detail == "discord_link_required")
    # owner (short-circuits _patreon_access) with a real in-guild discord CAN apply now
    MEMBER_INFO["downer"] = (True, [])
    await seed_user(id="uowner", discord_id="downer", staff_rank="owner", discord_in_guild=True)
    r_owner = await server.streamer_apply(body, user=await server.db.users.find_one({"id": "uowner"}))
    check("owner in-guild can apply (no false discord_required)", r_owner.get("status") == "pending")
    # incomplete (short about)
    bad = server.StreamerApplyInput(platform="Twitch", channel_url="https://twitch.tv/x", about="hi")
    try:
        await server.streamer_apply(bad, user=await server.db.users.find_one({"id": "u4"}))  # u4 already pending though
        check("incomplete rejected", False)
    except HTTPException as e:
        check("incomplete/pending -> 4xx", e.status_code in (400, 409))

    print("== streamer_decide (approve/reject/idempotent/key) ==")
    # wrong key
    dbody = server.StreamerDecideInput(message_id=posted["message_id"], action="approve", moderator_name="mod")
    try:
        await server.streamer_decide(dbody, x_internal_key="WRONG")
        check("bad key rejected", False)
    except HTTPException as e:
        check("bad key -> 403", e.status_code == 403)
    # not found
    try:
        await server.streamer_decide(server.StreamerDecideInput(message_id="nope", action="approve"), x_internal_key=KEY)
        check("not found rejected", False)
    except HTTPException as e:
        check("unknown message -> 404", e.status_code == 404)
    # approve
    ROLE_CALLS.clear()
    res = await server.streamer_decide(dbody, x_internal_key=KEY)
    check("approve -> approved", res["decision"] == "approved")
    check("role PUT called with streamer role", ("PUT", "d4", STREAMER_ROLE) in ROLE_CALLS)
    au = await server.db.users.find_one({"id": "u4"})
    check("user flagged streamer", au.get("discord_streamer_role") == STREAMER_ROLE)
    check("amber anchor seeded + count 0", au.get("streamer_amber_anchor") and au.get("streamer_amber_count") == 0)
    ap = await server.db.streamer_applications.find_one({"message_id": posted["message_id"]})
    check("application status approved", ap["status"] == "approved")
    # idempotent second approve
    res2 = await server.streamer_decide(dbody, x_internal_key=KEY)
    check("second decide idempotent", res2.get("already") is True)
    # reject flow on a fresh application
    MEMBER_INFO["d7"] = (True, [])
    u7 = await seed_user(id="u7", discord_id="d7", discord_in_guild=True)
    await server.streamer_apply(body, user=await server.db.users.find_one({"id": "u7"}))
    p7 = await server.db.streamer_applications.find_one({"user_id": "u7"})
    rj = await server.streamer_decide(server.StreamerDecideInput(message_id=p7["message_id"], action="reject",
                                                                moderator_name="mod", reason="no cumple"), x_internal_key=KEY)
    check("reject -> rejected", rj["decision"] == "rejected")
    p7b = await server.db.streamer_applications.find_one({"user_id": "u7"})
    check("rejected stored + reason", p7b["status"] == "rejected" and p7b.get("reason") == "no cumple")
    u7b = await server.db.users.find_one({"id": "u7"})
    check("rejected user NOT flagged streamer", not u7b.get("discord_streamer_role"))

    print("== _streamer_amber_pass (payout writer + live revoke) ==")
    period = timedelta(days=server.PATREON_PAYOUT_DAYS)
    # a streamer 15 days in -> one 20k payout
    MEMBER_INFO["d8"] = (True, [STREAMER_ROLE])
    # welcome payment already taken (these users test the RECURRING lane, not the joining one)
    await seed_user(id="u8", discord_id="d8", discord_streamer_role=STREAMER_ROLE,
                    streamer_welcome_amber_at=(now() - timedelta(days=15)).isoformat(),
                    streamer_amber_anchor=(now() - timedelta(days=15)).isoformat(), streamer_amber_count=0)
    await server._streamer_amber_pass(now(), period)
    p8 = await server.db.users.find_one({"id": "u8"})
    check("streamer paid 20k", p8["vip_coins"] == server.STREAMER_AMBER and p8["streamer_amber_count"] == 1)
    # second pass same time -> no double pay
    await server._streamer_amber_pass(now(), period)
    p8b = await server.db.users.find_one({"id": "u8"})
    check("no double pay in same period", p8b["vip_coins"] == server.STREAMER_AMBER and p8b["streamer_amber_count"] == 1)
    # active patron streamer is EXCLUDED (no stacking)
    MEMBER_INFO["d9"] = (True, [STREAMER_ROLE])
    await seed_user(id="u9", discord_id="d9", discord_streamer_role=STREAMER_ROLE,
                    patreon_patron_status="active_patron",
                    streamer_amber_anchor=(now() - timedelta(days=30)).isoformat(), streamer_amber_count=0)
    await server._streamer_amber_pass(now(), period)
    p9 = await server.db.users.find_one({"id": "u9"})
    check("active patron excluded from streamer amber", p9["vip_coins"] == 0)
    # role removed at boundary -> no pay + flag cleared
    MEMBER_INFO["d10"] = (True, [])  # role gone
    await seed_user(id="u10", discord_id="d10", discord_streamer_role=STREAMER_ROLE,
                    streamer_amber_anchor=(now() - timedelta(days=15)).isoformat(), streamer_amber_count=0)
    await server._streamer_amber_pass(now(), period)
    p10 = await server.db.users.find_one({"id": "u10"})
    check("revoked streamer not paid", p10["vip_coins"] == 0)
    check("revoked streamer flag cleared", not p10.get("discord_streamer_role"))
    # Discord unreachable at boundary -> defer (no pay, flag kept)
    MEMBER_INFO["d11"] = (None, None)
    await seed_user(id="u11", discord_id="d11", discord_streamer_role=STREAMER_ROLE,
                    streamer_amber_anchor=(now() - timedelta(days=15)).isoformat(), streamer_amber_count=0)
    await server._streamer_amber_pass(now(), period)
    p11 = await server.db.users.find_one({"id": "u11"})
    check("unreachable -> deferred (no pay)", p11["vip_coins"] == 0)
    check("unreachable -> flag kept", p11.get("discord_streamer_role") == STREAMER_ROLE)

    print("== #1 fix: gap in eligibility is NOT back-paid ==")
    # 45 days stale anchor (was a patron / re-added role) -> gap of 3 periods -> re-anchor, pay 0
    MEMBER_INFO["d12"] = (True, [STREAMER_ROLE])
    stale = (now() - timedelta(days=45)).isoformat()
    await seed_user(id="u12", discord_id="d12", discord_streamer_role=STREAMER_ROLE,
                    streamer_welcome_amber_at=stale,
                    streamer_amber_anchor=stale, streamer_amber_count=0)
    await server._streamer_amber_pass(now(), period)
    p12 = await server.db.users.find_one({"id": "u12"})
    check("gap>1 -> NOT back-paid (0 amber)", p12["vip_coins"] == 0)
    check("gap>1 -> clock re-anchored to now", p12.get("streamer_amber_anchor") != stale and p12.get("streamer_amber_count") == 0)
    # after re-anchor, 15 days later pays exactly one period
    p12b = await server.db.users.find_one({"id": "u12"})
    await server._streamer_amber_pass(datetime.fromisoformat(p12b["streamer_amber_anchor"]) + timedelta(days=15), period)
    p12c = await server.db.users.find_one({"id": "u12"})
    check("after re-anchor -> one clean 20k period", p12c["vip_coins"] == server.STREAMER_AMBER and p12c["streamer_amber_count"] == 1)

    print("== streamer PrimeMeat multiplier (2.0x) ==")
    check("streamer -> 2.0x", server._payout_multiplier({"discord_streamer_role": STREAMER_ROLE}) == server.STREAMER_MULT)
    check("streamer mult default is 2.0", server.STREAMER_MULT == 2.0)
    check("non-streamer non-patron -> 1.0", server._payout_multiplier({}) == 1.0)
    check("patron+streamer -> higher wins (apex 3.5 > 2.0)",
          server._payout_multiplier({"discord_streamer_role": STREAMER_ROLE, "patreon_patron_status": "active_patron", "patreon_tier_name": "Apex"}) == 3.5)
    check("low patron+streamer -> streamer 2.0 wins (juvie 1.5 < 2.0)",
          server._payout_multiplier({"discord_streamer_role": STREAMER_ROLE, "patreon_patron_status": "active_patron", "patreon_tier_name": "Juvie"}) == 2.0)
    check("revoked streamer (no flag) -> 1.0", server._payout_multiplier({"discord_streamer_role": ""}) == 1.0)
    # status exposes the boost
    MEMBER_INFO["dmx"] = (True, [STREAMER_ROLE])
    umx = await seed_user(id="umx", discord_id="dmx", discord_in_guild=True)
    stmx = await server._streamer_status_for(umx)
    check("status.multiplier == 2.0", stmx["multiplier"] == 2.0)

    print("== #2 fix: discord unlink clears streamer flag + amber + strips role ==")
    MEMBER_INFO["d13"] = (True, [STREAMER_ROLE])
    await seed_user(id="u13", discord_id="d13", discord_streamer_role=STREAMER_ROLE,
                    streamer_amber_anchor=now().isoformat(), streamer_amber_count=2, discord_in_guild=True)
    before = await server.db.users.find_one({"id": "u13"})
    check("pre-unlink: _is_subscriber True", server._is_subscriber(before) is True)
    ROLE_CALLS.clear()
    await server.discord_unlink(user=before)
    after = await server.db.users.find_one({"id": "u13"})
    check("unlink cleared streamer flag", not after.get("discord_streamer_role"))
    check("unlink cleared amber anchor+count", "streamer_amber_anchor" not in after and "streamer_amber_count" not in after)
    check("unlink cleared discord_id", not after.get("discord_id"))
    check("unlink stripped streamer role in Discord", ("DELETE", "d13", STREAMER_ROLE) in ROLE_CALLS)
    check("post-unlink: _is_subscriber False", server._is_subscriber(after) is False)
    check("unlink does NOT clear the welcome flag (anti-farm)",
          "streamer_welcome_amber_at" not in {k for k in after if k == "streamer_welcome_amber_at"}
          or after.get("streamer_welcome_amber_at") == before.get("streamer_welcome_amber_at"))

    print("== instant joining Amberium + a Discord notice on EVERY payout ==")
    A = server.STREAMER_AMBER

    # 1. approval pays 20k on the spot and DMs the streamer
    await reset_dms()
    MEMBER_INFO["dw1"] = (True, [STREAMER_ROLE])
    await seed_user(id="uw1", discord_id="dw1", persona_name="Wanda")
    await server.db.streamer_applications.insert_one({
        "id": "aw1", "user_id": "uw1", "discord_id": "dw1", "persona_name": "Wanda",
        "steam_id": "765w1", "status": "pending", "message_id": "MSG-aw1",
        "created_at": now().isoformat()})
    r_w = await server.streamer_decide(
        server.StreamerDecideInput(action="approve", message_id="MSG-aw1", moderator_name="mod"),
        x_internal_key=KEY)
    await drain()
    uw1 = await server.db.users.find_one({"id": "uw1"})
    check("approve pays the joining amber INSTANTLY", uw1["vip_coins"] == A)
    check("approve reports the amount paid", r_w.get("welcome_amber") == A)
    check("welcome stamped once", bool(uw1.get("streamer_welcome_amber_at")))
    check("clock starts at approval, count still 0",
          bool(uw1.get("streamer_amber_anchor")) and uw1.get("streamer_amber_count") == 0)
    tx = [t for t in server.db.transactions.docs if t["user_id"] == "uw1"]
    check("joining amber leaves a transaction row",
          len(tx) == 1 and tx[0]["amount"] == A and tx[0]["currency"] == "vip")
    check("streamer got a DM", len(DMS) == 1 and DMS[0][0] == "dw1")
    check("DM says welcome + the real amount + the 14-day cadence",
          "Bienvenido" in DMS[0][1] and "20.000" in DMS[0][1]
          and str(server.PATREON_PAYOUT_DAYS) in DMS[0][1])

    # 2. never twice: a second decide, and a role removed then re-added
    await reset_dms()
    await server.streamer_decide(
        server.StreamerDecideInput(action="approve", message_id="MSG-aw1", moderator_name="mod2"),
        x_internal_key=KEY)
    await drain()
    check("re-approval does not pay a second joining amber",
          (await server.db.users.find_one({"id": "uw1"}))["vip_coins"] == A)
    MEMBER_INFO["dw1"] = (True, [])                       # role stripped
    await server._patreon_access(await server.db.users.find_one({"id": "uw1"}), force=True)
    MEMBER_INFO["dw1"] = (True, [STREAMER_ROLE])          # and handed back
    await server._patreon_access(await server.db.users.find_one({"id": "uw1"}), force=True)
    await drain()
    check("revoke + re-grant cannot mint a second joining amber",
          (await server.db.users.find_one({"id": "uw1"}))["vip_coins"] == A)
    check("no duplicate DM either", len(DMS) == 0)

    # 3. role handed out manually in Discord (no application) still pays instantly
    await reset_dms()
    MEMBER_INFO["dw2"] = (True, [STREAMER_ROLE])
    uw2 = await seed_user(id="uw2", discord_id="dw2", persona_name="Manual")
    await server._patreon_access(uw2, force=True)
    await drain()
    p_w2 = await server.db.users.find_one({"id": "uw2"})
    check("manual role grant pays the joining amber too", p_w2["vip_coins"] == A)
    check("manual grant DMs the streamer", len(DMS) == 1 and DMS[0][0] == "dw2")

    # 3b. ALTS: nothing enforces one site account per discord_id, so a second account on
    #     the SAME Discord must not mint the joining payment a second time
    await reset_dms()
    uw2b = await seed_user(id="uw2b", discord_id="dw2", persona_name="ManualAlt")
    await server._patreon_access(uw2b, force=True)
    await drain()
    check("alt account on the same Discord gets NO second joining amber",
          (await server.db.users.find_one({"id": "uw2b"}))["vip_coins"] == 0)
    check("alt account was not stamped as paid",
          not (await server.db.users.find_one({"id": "uw2b"})).get("streamer_welcome_amber_at"))
    check("no DM to the alt", len(DMS) == 0)

    # 4. an active patron gets no joining amber (same no-stacking rule as the recurring pass)
    MEMBER_INFO["dw3"] = (True, [STREAMER_ROLE])
    uw3 = await seed_user(id="uw3", discord_id="dw3", patreon_patron_status="active_patron")
    await server._patreon_access(uw3, force=True)
    await drain()
    check("active patron gets no joining amber",
          (await server.db.users.find_one({"id": "uw3"}))["vip_coins"] == 0)

    # 5. BACKFILL: a streamer from before this existed is paid by the next pass, and the
    #    14-day clock restarts from that instant (this is lyngta's case)
    await reset_dms()
    MEMBER_INFO["dw4"] = (True, [STREAMER_ROLE])
    old_anchor = (now() - timedelta(days=2)).isoformat()
    await seed_user(id="uw4", discord_id="dw4", discord_streamer_role=STREAMER_ROLE,
                    streamer_amber_anchor=old_anchor, streamer_amber_count=0)
    await server._streamer_amber_pass(now(), period)
    await drain()
    p_w4 = await server.db.users.find_one({"id": "uw4"})
    check("existing streamer is back-filled the joining amber", p_w4["vip_coins"] == A)
    check("back-fill restarts the clock from now",
          p_w4["streamer_amber_anchor"] != old_anchor and p_w4["streamer_amber_count"] == 0)
    check("back-fill DMs them", len(DMS) == 1 and DMS[0][0] == "dw4")
    await server._streamer_amber_pass(now(), period)
    await drain()
    check("back-fill never runs twice",
          (await server.db.users.find_one({"id": "uw4"}))["vip_coins"] == A)

    # 6. and 14 days after the back-fill the RECURRING payout lands, with its own notice
    await reset_dms()
    base_w4 = datetime.fromisoformat(
        (await server.db.users.find_one({"id": "uw4"}))["streamer_amber_anchor"])
    await server._streamer_amber_pass(base_w4 + timedelta(days=15), period)
    await drain()
    p_w4b = await server.db.users.find_one({"id": "uw4"})
    check("recurring 20k still pays 14 days later",
          p_w4b["vip_coins"] == A * 2 and p_w4b["streamer_amber_count"] == 1)
    # scoped to dw4: this pass runs 15 days ahead, which also matures every OTHER seeded
    # streamer, so each of them legitimately fires a notice of their own here
    mine = [c for d, c in DMS if d == "dw4"]
    check("recurring payout DMs too, with NON-welcome wording",
          len(mine) == 1 and "Bienvenido" not in mine[0] and "20.000" in mine[0])

    # 7. no role at the boundary -> no joining amber (live check still governs)
    MEMBER_INFO["dw5"] = (True, [])
    await seed_user(id="uw5", discord_id="dw5", discord_streamer_role=STREAMER_ROLE,
                    streamer_amber_anchor=now().isoformat(), streamer_amber_count=0)
    await server._streamer_amber_pass(now(), period)
    check("role gone -> no joining amber",
          (await server.db.users.find_one({"id": "uw5"}))["vip_coins"] == 0)

    # 8. THE MONEY IS NOT HOSTAGE TO DISCORD: a closed DM inbox must not undo a payout
    DM_OK["v"] = False
    await reset_dms()
    MEMBER_INFO["dw6"] = (True, [STREAMER_ROLE])
    uw6 = await seed_user(id="uw6", discord_id="dw6")
    await server._patreon_access(uw6, force=True)
    await drain()
    check("DM failure does NOT roll back the joining amber",
          (await server.db.users.find_one({"id": "uw6"}))["vip_coins"] == A)
    check("failed DM delivered nothing (and did not raise)", len(DMS) == 0)
    ok_direct = await server._streamer_notify_payout("dw6", A, first=True)
    check("notify reports failure honestly when it cannot deliver", ok_direct is False)
    DM_OK["v"] = True

    print("== skin creator: the REAL POST /apply gate (not just the reported field) ==")
    # The 2026-07-24 owner report: a pure streamer saw "Acceso activo" and still got
    # 403 tier_insufficient on Aplicar, because the endpoint called the tier-only
    # helper while only the REPORTED field knew about streamers. These tests drive the
    # actual endpoint function, so the field and the gate can never diverge again.
    rgba = {"r": 0.5, "g": 0.4, "b": 0.3, "a": 1.0}
    payload = server.SkinPayloadIn(**{k: dict(rgba) for k in (
        "body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display")})
    WROTE = []
    _real_find, _real_write = server.game_ipc.find_active_dino, server.game_ipc.write_skin_command
    _real_record = server.skinkeeper_web.record_apply
    server.game_ipc.find_active_dino = lambda sid: {"actor_name": "Actor_1", "class": "BP_Dilo_C"}
    server.game_ipc.write_skin_command = lambda cmd: (WROTE.append(cmd), True)[1]
    server.skinkeeper_web.record_apply = lambda cmd, kind: None
    try:
        async def apply_as(uid, roles, **seed):
            """Run the real endpoint for a user holding `roles`; return (ok, code)."""
            MEMBER_INFO["dx-" + uid] = (True, list(roles))
            u = await seed_user(id=uid, discord_id="dx-" + uid, steam_id="765" + uid, **seed)
            try:
                r = await server.apply_skin(payload, user=u)
                return bool(r.get("ok")), None
            except server.HTTPException as e:
                d = e.detail
                return False, (d.get("code") if isinstance(d, dict) else str(d))

        ok, code = await apply_as("sk1", [STREAMER_ROLE])
        check("pure streamer CAN apply (was 403 tier_insufficient)", ok and code is None)
        check("pure streamer apply reached the game IPC", len(WROTE) == 1)

        # the field the frontend reads and the gate the endpoint enforces must agree
        acc_sk = await server._patreon_access(await server.db.users.find_one({"id": "sk1"}), force=True)
        check("reported field == enforced gate (streamer)",
              acc_sk["skin_creator"] is server._skin_creator_allowed(acc_sk) is True)

        # NOT widened: the paid-tier rule is untouched for everyone else
        ok2, code2 = await apply_as("sk2", ["555"])            # Juvie only
        check("juvie-only still refused tier_insufficient", ok2 is False and code2 == "tier_insufficient")
        ok3, code3 = await apply_as("sk3", ["444"])            # Sub Adult
        check("sub adult still allowed", ok3 is True)
        ok4, code4 = await apply_as("sk4", ["999"])            # no relevant role
        check("no role still refused patreon_required", ok4 is False and code4 == "patreon_required")
        ok5, code5 = await apply_as("sk5", ["555", STREAMER_ROLE])   # juvie + streamer
        check("juvie + streamer allowed (streamer carries it)", ok5 is True)

        # The owner path: the helper is now load-bearing for admins too, and an owner's
        # dict carries tier=None — without its own branch the tier rule would lock the
        # owner out of his own Aplicar with the rest of the suite still green.
        ok6, code6 = await apply_as("sk6", [], staff_rank="owner")
        check("owner can still apply (admin branch of the helper is pinned)", ok6 is True)

        # And the invariant the whole fix rests on, asserted for EVERY shape rather than
        # just the streamer one: what is reported always equals what is enforced.
        for uid, roles, seed in (("iv1", [STREAMER_ROLE], {}), ("iv2", ["555"], {}),
                                 ("iv3", ["444"], {}), ("iv4", ["999"], {}),
                                 ("iv5", [], {"staff_rank": "owner"}),
                                 ("iv6", ["555", STREAMER_ROLE], {})):
            MEMBER_INFO["dx-" + uid] = (True, list(roles))
            iu = await seed_user(id=uid, discord_id="dx-" + uid, steam_id="765" + uid, **seed)
            acc_i = await server._patreon_access(iu, force=True)
            check(f"reported field == enforced gate ({uid})",
                  acc_i["skin_creator"] is server._skin_creator_allowed(acc_i))

        # a revoked role must close the creator again on the very next apply
        MEMBER_INFO["dx-sk1"] = (True, ["999"])
        u_rev = await server.db.users.find_one({"id": "sk1"})
        try:
            await server.apply_skin(payload, user=u_rev)
            check("role removed -> apply refused", False)
        except server.HTTPException as e:
            check("role removed -> apply refused patreon_required",
                  e.status_code == 403 and e.detail.get("code") == "patreon_required")
    finally:
        server.game_ipc.find_active_dino = _real_find
        server.game_ipc.write_skin_command = _real_write
        server.skinkeeper_web.record_apply = _real_record


def test_streamer_pack():
    asyncio.run(run())
    assert _results["fail"] == 0, f"{_results['fail']} checks failed"


if __name__ == "__main__":
    asyncio.run(run())
    print(f"\n{_results['pass']} passed, {_results['fail']} failed")
    sys.exit(1 if _results["fail"] else 0)
