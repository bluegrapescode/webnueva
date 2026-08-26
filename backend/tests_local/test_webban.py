# -*- coding: utf-8 -*-
"""Baneos de la página web (webban.py) — store, gate, search, arm/confirm.

What this battery proves, WITHOUT a MongoDB (a small in-memory Motor stand-in
that speaks exactly the calls webban makes: find/find_one/insert_one/update_one
/update_many/count_documents/create_index, $or/$ne/$lte/$in/$regex, sort,
to_list, and a UNIQUE op_ref that raises DuplicateKeyError):

  * the STORE: place / fold-keeps-longer / escalate supersedes / duplicate
    op_id is one row / lift closes every open row and is honest when there is
    nothing to lift / expiry is computed against `now`, never swept;
  * the GATES: bad steam id, bad op_id, over-long reason, bad hours, SELF-BAN,
    OWNER-BAN (env list AND staff_rank owner) — all refused before any write;
  * the ARM: a confirm without a matching arm is refused; a drifted payload
    does not spend the arm; the arm is spent exactly once; a replay of a press
    that already landed is an idempotent success;
  * the SEARCH: prefix beats contains beats nothing, recency inside a tier,
    wildcards LITERAL (a typed "." or "%" matches itself), a typed Steam ID is
    one candidate (known / unknown), all-digits-not-an-id is said so, the bot's
    sqlite (accounts + identity_names, a REAL temp file) is merged read-only,
    banned state rides every candidate;
  * the ENFORCEMENT with a RED PROOF: server.py's REAL get_current_user is
    lifted by AST and run against a banned account -> 401 with the plain-words
    sentence and X-Web-Ban; the same function with the gate lines stripped
    (the mutant) lets the banned account through -> the proof bites;
  * the SIGN-IN door: server.py's REAL steam_callback (lifted) sends a banned
    account back to /auth/callback?error=banned with NO token minted and NO
    user row touched; a clean account still mints;
  * the crash websocket auth (crash_game._authenticate) refuses a banned user
    when the check is injected, and is unchanged when it is not.

Run: py -3.12 backend/tests_local/test_webban.py    (also collectable by pytest)
"""
import ast
import asyncio
import os
import re
import sqlite3
import sys
import tempfile
import time
from typing import Optional

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)

from fastapi import FastAPI, HTTPException, Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402

import webban  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# a tiny Motor stand-in — only what webban.py actually calls
# ---------------------------------------------------------------------------
def _match_value(cond, value):
    if isinstance(cond, dict) and any(str(k).startswith("$") for k in cond):
        for op, arg in cond.items():
            if op == "$ne":
                if value == arg:
                    return False
            elif op == "$lte":
                if value is None or not (value <= arg):
                    return False
            elif op == "$gte":
                if value is None or not (value >= arg):
                    return False
            elif op == "$in":
                if value not in arg:
                    return False
            elif op == "$regex":
                flags = re.I if "i" in str(cond.get("$options", "")) else 0
                if not isinstance(value, str) or not re.search(arg, value, flags):
                    return False
            elif op == "$options":
                continue
            elif op == "$exists":
                if bool(arg) != (value is not None):
                    return False
            else:
                raise NotImplementedError(op)
        return True
    return value == cond


def _match(doc, flt):
    for key, cond in (flt or {}).items():
        if key == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        if not _match_value(cond, doc.get(key)):
            return False
    return True


class _Cursor:
    def __init__(self, docs, proj):
        self._docs = list(docs)
        self._proj = proj

    def sort(self, key, direction=1):
        self._docs.sort(key=lambda d: (d.get(key) is None, d.get(key) or ""), reverse=(direction == -1))
        if direction == -1:
            # None sorts last either way
            self._docs.sort(key=lambda d: d.get(key) is None)
        return self

    async def to_list(self, n):
        return [_project(d, self._proj) for d in self._docs[: int(n)]]


def _project(doc, proj):
    out = {k: v for k, v in doc.items() if k != "_id"}
    if proj and any(v == 1 for k, v in proj.items() if k != "_id"):
        out = {k: v for k, v in out.items() if proj.get(k) == 1}
    return dict(out)


class _Result:
    def __init__(self, modified):
        self.modified_count = modified


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.unique = set()
        self.indexes = []

    async def create_index(self, keys, **kw):
        self.indexes.append((keys, kw))
        if kw.get("unique"):
            self.unique.add(keys if isinstance(keys, str) else keys[0][0])
        return "ok"

    def find(self, flt=None, proj=None):
        return _Cursor([d for d in self.docs if _match(d, flt)], proj)

    async def find_one(self, flt=None, proj=None, sort=None):
        docs = [d for d in self.docs if _match(d, flt)]
        return _project(docs[0], proj) if docs else None

    async def insert_one(self, doc):
        for key in self.unique:
            if doc.get(key) is not None and any(d.get(key) == doc.get(key) for d in self.docs):
                raise DuplicateKeyError("E11000 duplicate key " + key)
        self.docs.append(dict(doc))

    async def update_one(self, flt, update):
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return _Result(1)
        return _Result(0)

    async def update_many(self, flt, update):
        n = 0
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                n += 1
        return _Result(n)

    async def count_documents(self, flt=None, limit=None):
        n = len([d for d in self.docs if _match(d, flt)])
        return min(n, limit) if limit else n


class FakeDB:
    def __init__(self):
        self._cols = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, FakeCollection())

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


class BrokenDB(FakeDB):
    """Every read explodes: the fail-open-counted posture under test."""

    def __getitem__(self, name):
        class Boom:
            def find(self, *a, **k):
                raise RuntimeError("mongo down")

            async def find_one(self, *a, **k):
                raise RuntimeError("mongo down")

            async def count_documents(self, *a, **k):
                raise RuntimeError("mongo down")
        return Boom()


OWNER = {"id": "u-owner", "steam_id": "76561199532593593", "persona_name": "crysis",
         "role": "admin", "staff_rank": "owner"}
ISHAQ = {"id": "u-ishaq", "steam_id": "76561199318468901", "persona_name": "Nyxavrex", "role": "admin"}
REXY = {"id": "u-rexy", "steam_id": "76561198000000001", "persona_name": "Rexy",
        "avatar": "https://a/rexy.jpg", "last_login": "2026-08-17T10:00:00+00:00"}
REXTON = {"id": "u-rexton", "steam_id": "76561198000000002", "persona_name": "TRexton",
          "discord_username": "rexton_dc", "last_login": "2026-08-16T10:00:00+00:00"}
DOTTY = {"id": "u-dotty", "steam_id": "76561198000000003", "persona_name": "a.b",
         "last_login": "2026-08-15T10:00:00+00:00"}
AXB = {"id": "u-axb", "steam_id": "76561198000000004", "persona_name": "axb",
       "last_login": "2026-08-14T10:00:00+00:00"}
STAFF_OWNER = {"id": "u-so", "steam_id": "76561198000000009", "persona_name": "SegundoDueno",
               "staff_rank": "owner"}
TARGET = "76561198000000001"


def fresh_db():
    db = FakeDB()
    for u in (OWNER, ISHAQ, REXY, REXTON, DOTTY, AXB, STAFF_OWNER):
        db.users.docs.append(dict(u))
    return db


async def owner_dep_pass(user):
    if user.get("staff_rank") != "owner" and user.get("steam_id") not in ("76561199532593593", "76561199318468901"):
        raise HTTPException(status_code=403, detail="Solo el Dueño (Owner) puede hacer esto")
    return user


def make_app(db, *, current=None):
    async def current_user_dep(creds):
        if creds is None or not getattr(creds, "credentials", ""):
            raise HTTPException(status_code=401, detail="Inicia sesion para continuar")
        return current or dict(OWNER)

    logs = []

    async def add_log(actor, action, target=None, meta=None):
        logs.append((actor, action, target, meta))

    webban.configure(db, owner_ids={"76561199532593593", "76561199318468901"},
                     current_user_dep=current_user_dep, owner_user_dep=owner_dep_pass,
                     add_log=add_log, bot_db_path="")
    webban.arm_clear()
    webban.cache_clear()
    webban.faults_reset()
    run(webban.ensure_indexes())
    app = FastAPI()
    app.include_router(webban.router, prefix="/api")
    return TestClient(app), logs


H = {"Authorization": "Bearer owner-token"}


# ---------------------------------------------------------------------------
# 1. cleaners + words
# ---------------------------------------------------------------------------
def test_cleaners():
    check("clean_sid accepts a real id", webban.clean_sid(" 7656119 8000000001 ") == "76561198000000001")
    check("clean_sid refuses 16 digits", webban.clean_sid("7656119800000000") == "")
    check("clean_sid refuses a snowflake", webban.clean_sid("123456789012345678") == "")
    check("clean_reason folds control chars to spaces", webban.clean_reason("uno\ndos\x00tres") == "uno dos tres")
    check("clean_reason bounded", len(webban.clean_reason("x" * 500)) == webban.REASON_MAX)
    check("reason_too_long says so", webban.reason_too_long("x" * 101) and not webban.reason_too_long("x" * 100))
    check("clean_hours: blank is permanent", webban.clean_hours("") == (None, "ok"))
    check("clean_hours: 0 is permanent", webban.clean_hours(0) == (None, "ok"))
    check("clean_hours: 168 ok", webban.clean_hours(168) == (168, "ok"))
    check("clean_hours: '24' ok", webban.clean_hours("24") == (24, "ok"))
    check("clean_hours: bool refused", webban.clean_hours(True) == (None, "bad_hours"))
    check("clean_hours: negative refused", webban.clean_hours(-1) == (None, "bad_hours"))
    check("clean_hours: past ten years refused", webban.clean_hours(webban.HOURS_MAX + 1) == (None, "bad_hours"))
    check("clean_hours: 1.5 refused", webban.clean_hours(1.5) == (None, "bad_hours"))
    row_perm = {"expires_at": None, "reason": ""}
    check("message permanent, no reason",
          webban.message(row_perm) == "Esta cuenta está baneada de esta página web. Si crees que es un error, habla con el staff del servidor.")
    row_timed = {"expires_at": "2026-08-21T14:05:00Z", "reason": "Spam"}
    msg = webban.message(row_timed)
    check("message timed carries the date + reason", msg == "Esta cuenta está baneada de esta página web hasta el 21 ago 2026, 14:05 UTC. Motivo: Spam. Si crees que es un error, habla con el staff del servidor.", msg)
    check("message never leaks an id", "7656" not in webban.message({"steam_id": TARGET, "expires_at": None}))
    check("parse_iso round trip", webban.parse_iso(webban.iso(1_700_000_000)) == 1_700_000_000.0)
    check("parse_iso garbage is None (still banned)", webban.parse_iso("yesterday") is None)
    url = webban.banned_redirect_url("https://laislanublar.net/", row_perm)
    check("redirect url shape", url.startswith("https://laislanublar.net/auth/callback?error=banned&msg=Esta%20cuenta"), url)


# ---------------------------------------------------------------------------
# 2. the store
# ---------------------------------------------------------------------------
def test_store():
    db = fresh_db()
    make_app(db)
    now = 1_800_000_000.0

    async def go():
        # nobody banned
        row, why = await webban.is_banned_web(TARGET, now)
        check("empty store: not_banned", (row, why) == (None, "not_banned"))
        # place a 7-day ban
        res, why = await webban.place_ban(steam_id=TARGET, reason="Spam en el chat", op_id="op-00000001",
                                          hours=168, actor_sid=OWNER["steam_id"], actor_name="crysis",
                                          player_name="Rexy", now=now)
        check("place: ok/placed", why == "ok" and res["outcome"] == "placed", (res, why))
        check("place: expires in 7 days", res["expires_at"] == webban.iso(now + 168 * 3600))
        check("place: not permanent", res["permanent"] is False)
        row, why = await webban.is_banned_web(TARGET, now + 10)
        check("banned right after", why == "ok" and row["state"] == "active")
        row, why = await webban.is_banned_web(TARGET, now + 168 * 3600 + 1)
        check("expiry computed against now (never swept)", why == "not_banned")
        # duplicate op_id -> the same row, once
        res2, why2 = await webban.place_ban(steam_id=TARGET, reason="Spam en el chat", op_id="op-00000001",
                                            hours=168, actor_sid=OWNER["steam_id"], now=now + 5)
        check("duplicate op_id -> duplicate, one row", why2 == "ok" and res2["duplicate"] and res2["id"] == res["id"]
              and len(db[webban.COLLECTION].docs) == 1)
        # a SHORTER ban folds into the longer one
        res3, why3 = await webban.place_ban(steam_id=TARGET, reason="otra", op_id="op-00000002",
                                            hours=24, actor_sid=OWNER["steam_id"], now=now + 10)
        check("shorter ban folds, longer kept", why3 == "folded_kept_longer" and res3["folded"] and res3["id"] == res["id"])
        check("fold wrote nothing", len(db[webban.COLLECTION].docs) == 1)
        # a LONGER ban (permanent) escalates + supersedes
        res4, why4 = await webban.place_ban(steam_id=TARGET, reason="permanente", op_id="op-00000003",
                                            hours=None, actor_sid=OWNER["steam_id"], now=now + 20)
        check("permanent escalates", why4 == "ok" and res4["outcome"] == "escalated" and res4["permanent"])
        check("superseded row closed", res4["superseded_id"] == res["id"]
              and any(d["id"] == res["id"] and d["lifted_by"] == "superseded" for d in db[webban.COLLECTION].docs))
        active = await webban.list_active(now + 30)
        check("one active row", len(active) == 1 and active[0]["id"] == res4["id"])
        hist = await webban.list_history(now + 30)
        check("history holds the superseded one", any(h["id"] == res["id"] and h["state"] == "lifted" for h in hist))
        # lift closes it
        lifted, why5 = await webban.lift_ban(TARGET, actor_sid=OWNER["steam_id"], actor_name="crysis", now=now + 40)
        check("lift ok", why5 == "ok" and lifted["lifted"] == 1)
        row, why = await webban.is_banned_web(TARGET, now + 41)
        check("not banned after lift", why == "not_banned")
        lifted2, why6 = await webban.lift_ban(TARGET, actor_sid=OWNER["steam_id"], now=now + 42)
        check("lift again is honest: not_banned", (lifted2, why6) == (None, "not_banned"))
        # gates
        for label, kw, want in [
            ("bad steam id", dict(steam_id="123", reason="x", op_id="op-00000004"), "bad_steam_id"),
            ("bad op id", dict(steam_id=TARGET, reason="x", op_id="short"), "bad_op_id"),
            ("reason too long", dict(steam_id=TARGET, reason="y" * 101, op_id="op-00000005"), "bad_reason"),
            ("bad hours", dict(steam_id=TARGET, reason="x", op_id="op-00000006", hours=-5), "bad_hours"),
            ("self ban", dict(steam_id=OWNER["steam_id"], reason="x", op_id="op-00000007", actor_sid=OWNER["steam_id"]), "self_ban"),
            ("owner ban (env list)", dict(steam_id=ISHAQ["steam_id"], reason="x", op_id="op-00000008", actor_sid=OWNER["steam_id"]), "owner_ban"),
            ("owner ban (staff_rank owner)", dict(steam_id=STAFF_OWNER["steam_id"], reason="x", op_id="op-00000009", actor_sid=OWNER["steam_id"]), "owner_ban"),
        ]:
            r, w = await webban.place_ban(now=now, **kw)
            check("gate: " + label, r is None and w == want, (r, w))
        check("gates wrote nothing new", len(db[webban.COLLECTION].docs) == 2)
        # empty reason is allowed (optional on this site)
        r, w = await webban.place_ban(steam_id="76561198000000004", reason="", op_id="op-00000010",
                                      actor_sid=OWNER["steam_id"], now=now)
        check("empty reason accepted", w == "ok" and r["reason"] == "")
        check("message without reason has no 'Motivo'", "Motivo" not in webban.message(r))
        # replace=True narrows even a longer ban
        r2, w2 = await webban.place_ban(steam_id="76561198000000004", reason="corto", op_id="op-00000011",
                                        hours=1, actor_sid=OWNER["steam_id"], replace=True, now=now + 1)
        check("replace overrides the fold", w2 == "ok" and r2["outcome"] == "replaced" and r2["superseded_id"] == r["id"])
    run(go())


# ---------------------------------------------------------------------------
# 3. the gate cache + fail-open counted
# ---------------------------------------------------------------------------
def test_gate_cache():
    db = fresh_db()
    make_app(db)
    now = 1_800_000_000.0

    async def go():
        banned, row = await webban.check(TARGET, now)
        check("check: not banned, cached", banned is False)
        await webban.place_ban(steam_id=TARGET, reason="x", op_id="op-cache-0001", actor_sid=OWNER["steam_id"], now=now)
        banned, row = await webban.check(TARGET, now + 1)
        check("cached NOT-banned answer still served inside the window", banned is False)
        webban.forget(TARGET)
        banned, row = await webban.check(TARGET, now + 2)
        check("forget -> the next check sees the ban", banned is True and row["state"] == "active")
        banned, row = await webban.check(TARGET, now + webban.CACHE_TTL_SECONDS + 3, fresh=True)
        check("fresh=True reads the store", banned is True)
        # store fault: fail open, counted
        webban.configure(BrokenDB(), owner_ids=set(), current_user_dep=None, owner_user_dep=None)
        webban.cache_clear()
        webban.faults_reset()
        banned, row = await webban.check(TARGET, now + 100)
        check("store fault answers NOT banned (fail-open)", banned is False)
        check("...and is COUNTED", webban.faults() == 1)
        banned, row = await webban.check(TARGET, now + 101)
        check("fault answer cached only briefly (no second count inside 5s)", webban.faults() == 1)
        banned, row = await webban.check(TARGET, now + 100 + webban.FAULT_TTL_SECONDS + 1)
        check("after the fault window the store is retried and counted again", webban.faults() == 2)
    run(go())


# ---------------------------------------------------------------------------
# 4. the search
# ---------------------------------------------------------------------------
def make_bot_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE accounts (discord_id TEXT PRIMARY KEY, steam_id TEXT UNIQUE, linked_at TEXT);
        CREATE TABLE identity_names (discord_id TEXT PRIMARY KEY, username TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '', first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL);
        INSERT INTO accounts VALUES ('d1', '76561198000000007', '2026-08-01T00:00:00');
        INSERT INTO accounts VALUES ('d2', '76561198000000001', '2026-08-01T00:00:00');
        INSERT INTO accounts VALUES ('d3', NULL, '2026-08-01T00:00:00');
        INSERT INTO identity_names VALUES ('d1', 'rex_bot_only', 'Rex Bot Only', '2026-08-01T00:00:00', '2026-08-10T00:00:00');
        INSERT INTO identity_names VALUES ('d2', 'rexy_dc', 'Rexy en Discord', '2026-08-01T00:00:00', '2026-08-12T00:00:00');
        INSERT INTO identity_names VALUES ('d3', 'rex_unlinked', 'Rex Unlinked', '2026-08-01T00:00:00', '2026-08-12T00:00:00');
    """)
    conn.commit()
    conn.close()
    return path


def test_search():
    db = fresh_db()
    make_app(db)
    bot = make_bot_db()
    webban._bot_db_path = bot

    async def go():
        people, kind = await webban.find("rex")
        check("kind name", kind == "name")
        names = [p["name"] for p in people]
        check("prefix beats contains: Rexy before TRexton", names.index("Rexy") < names.index("TRexton"), names)
        rexy = next(p for p in people if p["steam_id"] == TARGET)
        check("website + discord sources merged for the same account", "website" in rexy["sources"] and "discord" in rexy["sources"], rexy)
        check("alt name carried", any(a.lower().startswith("rexy") for a in rexy["alt_names"]), rexy)
        check("bot-only account found through the bot db", any(p["steam_id"] == "76561198000000007" for p in people))
        check("unlinked bot row (no steam id) never appears", all(p["steam_id"] != "" for p in people))
        check("avatar carried from the site", rexy["avatar"] == "https://a/rexy.jpg")
        check("known True for a seen account", rexy["known"] is True)
        # discord username of a site user matches
        people, kind = await webban.find("rexton_dc")
        check("discord username on the site is searchable", any(p["steam_id"] == REXTON["steam_id"] for p in people))
        # wildcards literal
        people, _ = await webban.find("a.b")
        check("'.' is literal: a.b found, axb not", [p["name"] for p in people] == ["a.b"], [p["name"] for p in people])
        people, _ = await webban.find("%")
        check("'%' is literal: nobody", people == [])
        # steam id typed
        people, kind = await webban.find(TARGET)
        check("steam id typed -> one known candidate", kind == "steam" and len(people) == 1 and people[0]["known"] and people[0]["name"] == "Rexy")
        people, kind = await webban.find("76561198999999999")
        check("unknown steam id -> offered, known False", kind == "steam" and people[0]["known"] is False and people[0]["steam_id"] == "76561198999999999")
        people, kind = await webban.find("12345")
        check("digits that are not an id -> not_an_id", (people, kind) == ([], "not_an_id"))
        people, kind = await webban.find("   ")
        check("empty -> empty", (people, kind) == ([], "empty"))
        people, _ = await webban.find("r" * 500)
        check("over-long query is cut, never refused", people == [])
        # a bot db that is not there costs nothing
        webban._bot_db_path = os.path.join(tempfile.gettempdir(), "nope_no_such.db")
        people, kind = await webban.find("rexy")
        check("missing bot db: web source still answers", any(p["name"] == "Rexy" for p in people))
    run(go())
    try:
        os.remove(bot)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 5. the routes: owner gate, arm/confirm, suggest, lift, overview
# ---------------------------------------------------------------------------
def test_routes():
    db = fresh_db()
    client, logs = make_app(db)

    r = client.get("/api/admin/bans/overview")
    check("signed-out overview is 401", r.status_code == 401, r.text)
    r = client.post("/api/admin/bans/place", json={"steam_id": TARGET, "op_id": "op-route-0001"})
    check("signed-out place is 401", r.status_code == 401)

    r = client.get("/api/admin/bans/overview", headers=H)
    check("overview 200", r.status_code == 200 and r.json()["available"] is True, r.text)
    check("overview empty", r.json()["active"] == [] and r.json()["counts"]["active"] == 0)
    check("overview limits", r.json()["limits"]["reason_max"] == 100 and r.json()["gate_faults"] == 0)

    r = client.get("/api/admin/bans/suggest", params={"q": "rex"}, headers=H)
    check("suggest 200 with people", r.status_code == 200 and len(r.json()["people"]) >= 2, r.text)
    check("suggest: nobody banned yet", all(p["banned"] is False for p in r.json()["people"]))

    # confirm with NO arm -> refused, nothing written
    body = {"steam_id": TARGET, "player_name": "Rexy", "reason": "Spam", "hours": 72, "op_id": "op-route-0002", "confirm": True}
    r = client.post("/api/admin/bans/place", json=body, headers=H)
    check("confirm without arm -> 409 not_armed", r.status_code == 409 and "vista previa" in r.json()["detail"], r.text)
    check("...and nothing was written", len(db[webban.COLLECTION].docs) == 0)

    # arm
    arm = dict(body)
    arm.pop("confirm")
    r = client.post("/api/admin/bans/place", json=arm, headers=H)
    check("arm -> 200 armed, preview placed", r.status_code == 200 and r.json()["armed"] and r.json()["preview"]["outcome"] == "placed", r.text)
    check("arm wrote nothing", len(db[webban.COLLECTION].docs) == 0)
    # drifted payload does not spend the arm
    drift = dict(body)
    drift["hours"] = 24
    r = client.post("/api/admin/bans/place", json=drift, headers=H)
    check("drifted confirm -> 409", r.status_code == 409 and len(db[webban.COLLECTION].docs) == 0, r.text)
    # the real confirm
    r = client.post("/api/admin/bans/place", json=body, headers=H)
    check("confirm -> placed", r.status_code == 200 and r.json()["confirmed"] and r.json()["ban"]["outcome"] == "placed", r.text)
    check("one row", len(db[webban.COLLECTION].docs) == 1)
    check("audit line written", any(l[1] == "web_ban" for l in logs))
    # replay of the same press: idempotent success, still one row
    r = client.post("/api/admin/bans/place", json=body, headers=H)
    check("replayed confirm -> duplicate ok", r.status_code == 200 and r.json()["ban"]["duplicate"] is True, r.text)
    check("still one row", len(db[webban.COLLECTION].docs) == 1)

    r = client.get("/api/admin/bans/suggest", params={"q": "rexy"}, headers=H)
    rexy = next(p for p in r.json()["people"] if p["steam_id"] == TARGET)
    check("suggest shows banned state", rexy["banned"] is True and rexy["banned_reason"] == "Spam")

    r = client.get("/api/admin/bans/overview", headers=H)
    row = r.json()["active"][0]
    check("overview lists the ban with name + avatar", row["player_name"] == "Rexy" and row["avatar"] == "https://a/rexy.jpg" and row["state"] == "active", row)

    # self ban and owner ban refused at the arm step
    r = client.post("/api/admin/bans/place", json={"steam_id": OWNER["steam_id"], "reason": "x", "op_id": "op-route-0003"}, headers=H)
    check("self ban refused 409", r.status_code == 409 and "ti mismo" in r.json()["detail"], r.text)
    r = client.post("/api/admin/bans/place", json={"steam_id": ISHAQ["steam_id"], "reason": "x", "op_id": "op-route-0004"}, headers=H)
    check("owner ban refused 409", r.status_code == 409 and "dueño" in r.json()["detail"].lower(), r.text)
    r = client.post("/api/admin/bans/place", json={"steam_id": "nope", "reason": "x", "op_id": "op-route-0005"}, headers=H)
    check("bad steam id 400 with words", r.status_code == 400 and "17" in r.json()["detail"])

    # lift, then lift again
    r = client.post("/api/admin/bans/lift", json={"steam_id": TARGET}, headers=H)
    check("lift 200", r.status_code == 200 and r.json()["lifted"] == 1, r.text)
    r = client.post("/api/admin/bans/lift", json={"steam_id": TARGET}, headers=H)
    check("lift again 404 honest", r.status_code == 404)
    r = client.get("/api/admin/bans/overview", headers=H)
    check("overview: active empty, history has the lifted row", r.json()["active"] == [] and any(h["state"] == "lifted" for h in r.json()["history"]))

    # a non-owner admin is refused everywhere with the same 403
    admin_only = {"id": "u-adm", "steam_id": "76561198000000050", "persona_name": "Mod", "role": "admin", "staff_rank": "admin"}
    client2, _ = make_app(db, current=admin_only)
    for path, method, payload in [("/api/admin/bans/overview", "get", None), ("/api/admin/bans/suggest?q=rex", "get", None),
                                  ("/api/admin/bans/place", "post", {"steam_id": TARGET, "op_id": "op-route-0006"}),
                                  ("/api/admin/bans/lift", "post", {"steam_id": TARGET})]:
        r = client2.get(path, headers=H) if method == "get" else client2.post(path, json=payload, headers=H)
        check("non-owner refused 403 " + path, r.status_code == 403, r.text)


# ---------------------------------------------------------------------------
# 6. THE ENFORCEMENT — server.py's real get_current_user, lifted by AST + RED
# ---------------------------------------------------------------------------
SERVER = os.path.join(BACKEND, "server.py")


def _lift(src, names, extra_ns):
    tree = ast.parse(src)
    wanted = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    mod = ast.Module(body=wanted, type_ignores=[])
    ns = dict(extra_ns)
    exec(compile(ast.fix_missing_locations(mod), "<lifted server.py>", "exec"), ns)
    return ns


class _Creds:
    def __init__(self, token):
        self.credentials = token


class _FakeJwt:
    class PyJWTError(Exception):
        pass

    @staticmethod
    def decode(token, secret, algorithms=None):
        if token == "good":
            return {"sub": "u-rexy"}
        raise _FakeJwt.PyJWTError("bad")


class _FakeWebban:
    def __init__(self, banned, row=None):
        self.banned = banned
        self.row = row
        self.calls = []

    async def check(self, sid, now=None, fresh=False):
        self.calls.append((sid, fresh))
        return (self.banned, self.row) if self.banned else (False, None)

    def message(self, row):
        return webban.message(row)

    def banned_redirect_url(self, frontend, row):
        return webban.banned_redirect_url(frontend, row)


class _Users:
    def __init__(self, docs):
        self.docs = docs
        self.updated = []
        self.inserted = []

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                return dict(d)
        return None

    async def update_one(self, flt, update):
        self.updated.append((flt, update))
        return _Result(1)

    async def insert_one(self, doc):
        self.inserted.append(doc)


class _DBShim:
    def __init__(self, users):
        self.users = users


def test_enforcement_red_proof():
    with open(SERVER, "r", encoding="utf-8") as f:
        src = f.read()
    users = _Users([dict(REXY)])
    ban_row = {"expires_at": None, "reason": "Trampas"}
    fake_webban = _FakeWebban(True, ban_row)

    def ns_for(source, wb):
        return _lift(source, {"get_current_user"}, {
            "Optional": Optional, "HTTPAuthorizationCredentials": object, "Depends": Depends,
            "security": None, "HTTPException": HTTPException, "jwt": _FakeJwt, "JWT_SECRET": "s",
            "JWT_ALGO": "HS256", "db": _DBShim(users), "webban": wb,
        })

    ns = ns_for(src, fake_webban)
    get_current_user = ns["get_current_user"]

    # a clean account still resolves
    clean = _FakeWebban(False)
    ns_clean = ns_for(src, clean)
    user = run(ns_clean["get_current_user"](_Creds("good")))
    check("clean account resolves through the real get_current_user", user["id"] == "u-rexy")
    check("the gate was asked with the account's steam id", clean.calls and clean.calls[0][0] == TARGET)

    # a banned account is refused with the words + the header
    try:
        run(get_current_user(_Creds("good")))
        check("banned account refused", False, "no exception")
    except HTTPException as exc:
        check("banned -> 401", exc.status_code == 401, exc.status_code)
        check("banned -> plain-words sentence", exc.detail.startswith("Esta cuenta está baneada de esta página web") and "Trampas" in exc.detail, exc.detail)
        check("banned -> X-Web-Ban header", (exc.headers or {}).get("X-Web-Ban") == "1", exc.headers)
    # a bad token is still the old refusal (the gate never runs)
    try:
        run(get_current_user(_Creds("bad")))
        check("bad token refused", False)
    except HTTPException as exc:
        check("bad token -> 401 sesion invalida (gate untouched)", exc.status_code == 401 and "Sesion" in exc.detail)
    try:
        run(get_current_user(None))
        check("no creds refused", False)
    except HTTPException as exc:
        check("no creds -> 401", exc.status_code == 401)

    # THE RED PROOF: strip the gate lines and the banned account walks in.
    lines = src.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if "banned, ban_row = await webban.check(user.get(\"steam_id\"))" in l)
    mutant_lines = [l for i, l in enumerate(lines) if not (start <= i <= start + 3)]
    mutant = "".join(mutant_lines)
    check("mutant really lost the gate", "banned, ban_row = await webban.check(user.get" not in mutant.split("async def get_admin_user")[0].split("async def get_current_user")[1])
    ns_mut = ns_for(mutant, _FakeWebban(True, ban_row))
    try:
        user = run(ns_mut["get_current_user"](_Creds("good")))
        red = user is not None and user["id"] == "u-rexy"
    except HTTPException:
        red = False
    check("RED: with the gate stripped the banned account is served (so the gate is what refuses)", red)


# ---------------------------------------------------------------------------
# 7. THE SIGN-IN DOOR — server.py's real steam_callback, lifted
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, text="", js=None):
        self.text = text
        self._js = js or {}

    def json(self):
        return self._js


class _FakeHttpx:
    class AsyncClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data=None):
            return _Resp("ns:http://specs.openid.net/auth/2.0\nis_valid:true\n")

        async def get(self, url, params=None):
            return _Resp(js={"response": {"players": [{"personaname": "Rexy", "avatarfull": "a", "profileurl": "p"}]}})


class _Req:
    def __init__(self, sid):
        self.query_params = {"openid.claimed_id": f"https://steamcommunity.com/openid/id/{sid}", "openid.mode": "id_res"}


class _Redirect:
    def __init__(self, url):
        self.url = url


def test_signin_door():
    with open(SERVER, "r", encoding="utf-8") as f:
        src = f.read()
    minted = []

    async def upsert(steam_id, persona, avatar, profile_url):
        minted.append(steam_id)
        return "tok"

    class _Router:
        """The decorator on the lifted route: registers nothing, returns the fn."""
        def get(self, *a, **k):
            return lambda fn: fn

    def ns_for(wb):
        return _lift(src, {"steam_callback"}, {
            "api_router": _Router(),
            "Request": object, "RedirectResponse": _Redirect, "httpx": _FakeHttpx, "re": re,
            "STEAM_OPENID_URL": "https://steamcommunity.com/openid/login", "FRONTEND_URL": "https://laislanublar.net",
            "STEAM_API_KEY": "k", "logger": webban.log, "webban": wb, "upsert_steam_user": upsert,
        })

    banned = _FakeWebban(True, {"expires_at": None, "reason": ""})
    resp = run(ns_for(banned)["steam_callback"](_Req(TARGET)))
    check("banned sign-in -> back to /auth/callback?error=banned", "/auth/callback?error=banned&msg=" in resp.url, resp.url)
    check("banned sign-in -> NO token minted", minted == [])
    check("the door asked the store directly (fresh=True)", banned.calls and banned.calls[0] == (TARGET, True), banned.calls)
    clean = _FakeWebban(False)
    resp = run(ns_for(clean)["steam_callback"](_Req(TARGET)))
    check("clean sign-in mints as before", minted == [TARGET] and "#token=tok" in resp.url, resp.url)


# ---------------------------------------------------------------------------
# 8. the crash websocket door
# ---------------------------------------------------------------------------
def test_crash_ws_door():
    import crash_game
    import jwt as real_jwt

    class _WS:
        def __init__(self, token):
            self._token = token

        async def receive_text(self):
            return '{"type":"auth","token":"%s"}' % self._token

    users = _Users([dict(REXY)])
    token = real_jwt.encode({"sub": "u-rexy"}, "sec", algorithm="HS256")
    crash_game.configure(_DBShim(users), "sec")
    user = run(crash_game._authenticate(_WS(token)))
    check("crash ws: no check injected -> old behaviour (user)", user is not None and user["id"] == "u-rexy")

    async def banned_check(sid):
        return True, {"expires_at": None}

    crash_game.configure(_DBShim(users), "sec", ban_check=banned_check)
    user = run(crash_game._authenticate(_WS(token)))
    check("crash ws: banned -> None (no socket)", user is None)

    async def clean_check(sid):
        return False, None
    crash_game.configure(_DBShim(users), "sec", ban_check=clean_check)
    user = run(crash_game._authenticate(_WS(token)))
    check("crash ws: clean -> user", user is not None)


def main():
    print("webban battery")
    for fn in (test_cleaners, test_store, test_gate_cache, test_search, test_routes,
               test_enforcement_red_proof, test_signin_door, test_crash_ws_door):
        print(f"--- {fn.__name__}")
        fn()
    print(f"\n{PASS} passed, {FAIL} failed")
    return FAIL == 0


def test_all():
    assert main()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
