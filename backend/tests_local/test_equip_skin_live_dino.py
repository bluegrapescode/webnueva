# -*- coding: utf-8 -*-
"""Crate-skin equip lane -- REAL I/O gate.

Why this file exists: the equip route used to demand a web-sim ``active_dino``
record (only created by deploying a dino from La Boveda) before it would paint a
coded crate skin onto the LIVE dinosaur. Every player who spawned normally in
the game therefore got 400 "Despliega un dinosaurio antes de equipar una skin"
while standing in the game holding the skin (owner report 2026-07-24). The gate
now reads the mod's players.json, exactly like /api/apply, the glitch reward
lane and vault.do_growth_pause.

This suite drives the REAL ``server.equip_active_skin`` coroutine against a REAL
MongoDB and a REAL players.json / skin_commands.json on disk -- no fake db, no
stubbed IPC -- because that is the layer that held the bug. A fake double with
the wrong contract ($gte / $exists / $lte filters, ReturnDocument.AFTER) would
have passed while production stayed broken.

Run:  python backend/tests_local/test_equip_skin_live_dino.py
      (set MONGO_URL to reuse a running mongod; otherwise the portable
       _localtest mongod is started on a temp dbpath and stopped again.)

Exit codes: 0 all pass / 1 a check failed / 2 the suite could NOT run
(no mongod) -- 2 is never a pass, a suite that did not run is a failed read.
"""
import asyncio
import json
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
TMP = tempfile.mkdtemp(prefix="lin_equip_test_")


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
SAVED = os.path.join(TMP, "Saved")
os.makedirs(SAVED, exist_ok=True)
PLAYERS_JSON = os.path.join(SAVED, "players.json")
SKIN_COMMANDS = os.path.join(SAVED, "skin_commands.json")

IN_GAME_SID = "76561199000000111"
OFFLINE_SID = "76561199000000222"
ACTOR = "BP_Allosaurus_C_2147471431"
DINO_CLASS = "BP_Allosaurus_C"


def write_players(rows):
    """Real players.json in the exact prod shape: {sid: {...}} with epoch-SECOND
    last_updated (that is what the mod writes -- game_ipc normalises to ms)."""
    now = int(time.time())
    data = {}
    for sid, actor in rows.items():
        data[sid] = {"steamid": sid, "actor_name": actor, "dino": DINO_CLASS,
                     "growth": 0.87, "health": 100, "max_health": 100,
                     "last_updated": now}
    with open(PLAYERS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f)


write_players({IN_GAME_SID: ACTOR})

MONGO_URL = start_mongo()
os.environ["MONGO_URL"] = MONGO_URL
os.environ["DB_NAME"] = "lin_equip_test_%s" % uuid.uuid4().hex[:8]
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ["LIN_SAVED_DIR"] = SAVED
os.environ["BOT_DB_PATH"] = os.path.join(TMP, "data", "laislanublar.db")
os.environ.setdefault("LAISLANUBLAR_SKIN_CAPTURE", "0")   # sqlite capture off: not under test
os.environ.setdefault("RCON_HOST", "")
os.environ.setdefault("ALLOW_DEMO_LOGIN", "0")

sys.path.insert(0, BACKEND)
import game_ipc                      # noqa: E402
import seed_data                     # noqa: E402
import server                        # noqa: E402

check("game_ipc reads the fixture Saved dir", game_ipc.PLAYERS_JSON == PLAYERS_JSON,
      game_ipc.PLAYERS_JSON)

# The two skin shapes under test, taken from the REAL catalog (never invented).
CODED_KEY = next((k for k, v in seed_data.SKINS.items() if isinstance(v.get("srgb"), dict)
                  and v["srgb"].get("regions")), None)
DERIVED_KEY = next((k for k, v in seed_data.SKINS.items() if not v.get("srgb")), None)
check("catalog has a coded (paints in-game) skin", CODED_KEY is not None)
check("catalog has a derived (display-only) skin", DERIVED_KEY is not None)


# ---------------------------------------------------------------------------
# helpers over the REAL db
# ---------------------------------------------------------------------------
db = server.db


async def reset_state():
    await db.users.delete_many({})
    await db.inventory.delete_many({})
    for p in (SKIN_COMMANDS,):
        if os.path.exists(p):
            os.remove(p)
    game_ipc._file_cache.clear()      # the reader caches players.json for 1.5 s


async def mk_user(sid, with_active_dino):
    uid = uuid.uuid4().hex
    doc = {"id": uid, "steam_id": sid, "email": "t@t", "role": "user"}
    if with_active_dino:
        # LEGACY web-sim card. Nothing in the current codebase creates one any
        # more (the deploy route hands dinos to the real vault since 2026-07-15)
        # -- only pre-rework accounts still carry it, which is exactly why the
        # old gate locked everyone else out. Keys mirror _live_active_dino's
        # hard requirements so this is the real contract, not a convenient stub.
        doc["active_dino"] = {"slug": "allosaurus", "name": "Allosaurus",
                              "image": None, "type": "Carnivore", "diet": "Carnivore",
                              "rarity": "Epic", "base_growth": 50.0,
                              "set_at": server.now_iso(), "fed_at": server.now_iso(),
                              "base_stats": {}, "mutations": []}
    await db.users.insert_one(dict(doc))
    return await db.users.find_one({"id": uid}, {"_id": 0})


async def mk_skin(user, skin_key, uses=3, legacy_no_uses=False, quantity=1):
    iid = uuid.uuid4().hex
    doc = {"id": iid, "user_id": user["id"], "category": "Skins",
           "name": seed_data.SKINS[skin_key]["name"], "skin_key": skin_key,
           "rarity": seed_data.SKINS[skin_key].get("rarity", "Common"),
           "quantity": quantity}
    if not legacy_no_uses:
        doc["uses"] = uses
    await db.inventory.insert_one(doc)
    return iid


async def equip(user, inv_id):
    """Call the REAL route coroutine. Returns (status_or_200, payload_or_detail)."""
    try:
        r = await server.equip_active_skin(server.EquipSkinInput(inv_id=inv_id), user=user)
        return 200, r
    except server.HTTPException as e:
        return e.status_code, e.detail


def read_commands():
    if not os.path.exists(SKIN_COMMANDS):
        return []
    with open(SKIN_COMMANDS, "r", encoding="utf-8") as f:
        return json.load(f)


async def uses_of(inv_id):
    row = await db.inventory.find_one({"id": inv_id}, {"_id": 0})
    return None if row is None else row.get("uses")


# ---------------------------------------------------------------------------
# the matrix
# ---------------------------------------------------------------------------
async def main():
    # ---- A. THE REPORTED BUG: in-game, no website-deployed dino -------------
    print("[A] in-game player with NO active_dino record (the reported bug)")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=3)
    st, body = await equip(u, iid)
    check("A1 equips (was 400 'Despliega un dinosaurio')", st == 200, "%s %r" % (st, body))
    check("A2 painted in-game", st == 200 and body.get("applied_ingame") is True, repr(body))
    check("A3 one use spent", await uses_of(iid) == 2, str(await uses_of(iid)))
    cmds = read_commands()
    check("A4 exactly one skin command written", len(cmds) == 1, str(len(cmds)))
    if cmds:
        c = cmds[0]
        check("A5 command targets the LIVE actor from players.json", c.get("actor_name") == ACTOR, repr(c.get("actor_name")))
        check("A6 command carries the live class", c.get("class") == DINO_CLASS, repr(c.get("class")))
        check("A7 command keyed on the caller's own steamid", c.get("steamid") == IN_GAME_SID, repr(c.get("steamid")))
        check("A8 preserve_female set (live pawn sex wins)", c.get("preserve_female") is True, repr(c.get("preserve_female")))
        check("A9 linear colour space (mod contract)", c.get("color_space") == "linear", repr(c.get("color_space")))
    check("A10 response 'active' is null with no web card", st == 200 and body.get("active") is None, repr(body.get("active") if st == 200 else body))
    check("A11 no active_dino fabricated on the user",
          (await db.users.find_one({"id": u["id"]}, {"_id": 0})).get("active_dino") is None)

    # ---- B. offline: still refused, and it costs nothing --------------------
    print("[B] coded skin, player NOT in the game")
    await reset_state()
    u = await mk_user(OFFLINE_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=3)
    st, detail = await equip(u, iid)
    check("B1 409 refused", st == 409, "%s %r" % (st, detail))
    check("B2 message names the real requirement", isinstance(detail, str) and "juego" in detail.lower(), repr(detail))
    check("B3 no use spent", await uses_of(iid) == 3, str(await uses_of(iid)))
    check("B4 no command written", read_commands() == [])

    # ---- C. regression: the deployed-dino path still stores the web card ----
    print("[C] coded skin, in-game AND a deployed web dino (pre-existing path)")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=True)
    iid = await mk_skin(u, CODED_KEY, uses=2)
    st, body = await equip(u, iid)
    check("C1 equips", st == 200, "%s %r" % (st, body))
    check("C2 painted in-game", st == 200 and body.get("applied_ingame") is True)
    stored = (await db.users.find_one({"id": u["id"]}, {"_id": 0})).get("active_dino") or {}
    check("C3 active_skin stored on the card", (stored.get("active_skin") or {}).get("skin_key") == CODED_KEY, repr(stored.get("active_skin")))
    check("C4 card inv_id matches the item", (stored.get("active_skin") or {}).get("inv_id") == iid)
    check("C5 response 'active' populated", st == 200 and body.get("active") is not None)

    # ---- D/E. display-only derived skins keep the web-card gate -------------
    print("[D] derived (display-only) skin without a web card")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, DERIVED_KEY, uses=2)
    st, detail = await equip(u, iid)
    check("D1 400 (nothing to paint, nothing to decorate)", st == 400, "%s %r" % (st, detail))
    check("D2 no use spent", await uses_of(iid) == 2)
    check("D3 no command written", read_commands() == [])
    check("D4 message no longer points at the dead deploy lane",
          isinstance(detail, str) and "despliega" not in detail.lower()
          and "decorativa" in detail.lower(), repr(detail))

    print("[E] derived skin WITH a web card")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=True)
    iid = await mk_skin(u, DERIVED_KEY, uses=2)
    st, body = await equip(u, iid)
    check("E1 equips", st == 200, "%s %r" % (st, body))
    check("E2 NOT painted in-game", st == 200 and body.get("applied_ingame") is False and body.get("paints_ingame") is False, repr(body))
    check("E3 no command written (display-only)", read_commands() == [])
    check("E4 one use spent", await uses_of(iid) == 1)

    # ---- F. last use removes the row ---------------------------------------
    print("[F] last use")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=1)
    st, body = await equip(u, iid)
    check("F1 equips on the last use", st == 200, "%s %r" % (st, body))
    check("F2 uses_left 0 reported", st == 200 and body.get("uses_left") == 0, repr(body))
    check("F3 row deleted from inventory", await uses_of(iid) is None)

    # ---- G. exhausted row ---------------------------------------------------
    print("[G] a row already at 0 uses")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=0)
    st, detail = await equip(u, iid)
    check("G1 400 no uses", st == 400, "%s %r" % (st, detail))
    check("G2 counter not driven negative", await uses_of(iid) == 0, str(await uses_of(iid)))
    check("G3 no command written", read_commands() == [])

    # ---- H. legacy row written before the use counter existed ---------------
    print("[H] legacy row with no 'uses' field")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, legacy_no_uses=True, quantity=2)
    st, body = await equip(u, iid)
    check("H1 equips", st == 200, "%s %r" % (st, body))
    check("H2 self-healed from quantity then spent one", await uses_of(iid) == 1, str(await uses_of(iid)))

    # ---- I. IPC failure refunds the use ------------------------------------
    print("[I] mod IPC write fails")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=3)
    real_write = game_ipc.write_skin_command
    game_ipc.write_skin_command = lambda cmd: False
    try:
        st, detail = await equip(u, iid)
    finally:
        game_ipc.write_skin_command = real_write
    check("I1 500 surfaced", st == 500, "%s %r" % (st, detail))
    check("I2 the use was refunded", await uses_of(iid) == 3, str(await uses_of(iid)))

    print("[I'] mod IPC raises")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=3)

    def _boom(cmd):
        raise RuntimeError("ipc exploded")

    game_ipc.write_skin_command = _boom
    try:
        st, detail = await equip(u, iid)
    finally:
        game_ipc.write_skin_command = real_write
    check("I3 contained as 500, never a 500-with-traceback leak", st == 500, "%s %r" % (st, detail))
    check("I4 the use was refunded", await uses_of(iid) == 3, str(await uses_of(iid)))

    # ---- J. no linked Steam account ----------------------------------------
    print("[J] account with no steam_id")
    await reset_state()
    u = await mk_user("", with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=3)
    st, detail = await equip(u, iid)
    check("J1 400 asks for the Steam link", st == 400, "%s %r" % (st, detail))
    check("J2 no use spent", await uses_of(iid) == 3)

    # ---- K. two racing clicks on a one-use skin -----------------------------
    print("[K] concurrency: two simultaneous equips, one use left")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=1)
    res = await asyncio.gather(equip(u, iid), equip(u, iid), return_exceptions=True)
    codes = sorted(r[0] for r in res if isinstance(r, tuple))
    # The loser sees 400 (row still there at 0 uses) or 404 (winner's delete of
    # the exhausted row landed first). Both are honest refusals; what must never
    # happen is two 200s off one use.
    check("K1 exactly one succeeded, one refused",
          len(codes) == 2 and codes.count(200) == 1 and codes[1] in (400, 404),
          str(codes) + " " + repr(res))
    check("K2 row gone, counter never negative", await uses_of(iid) is None)

    print("[K'] concurrency: two racing clicks, three uses left")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=3)
    res = await asyncio.gather(equip(u, iid), equip(u, iid))
    check("K3 both succeed", [r[0] for r in res] == [200, 200], repr(res))
    check("K4 exactly two uses spent (no lost decrement)", await uses_of(iid) == 1, str(await uses_of(iid)))

    # ---- L. not the caller's item ------------------------------------------
    print("[L] someone else's inventory row")
    await reset_state()
    owner = await mk_user(IN_GAME_SID, with_active_dino=False)
    other = await mk_user(OFFLINE_SID, with_active_dino=False)
    iid = await mk_skin(owner, CODED_KEY, uses=3)
    st, detail = await equip(other, iid)
    check("L1 404 not found for the other account", st == 404, "%s %r" % (st, detail))
    check("L2 owner's uses untouched", await uses_of(iid) == 3)
    st, detail = await equip(owner, uuid.uuid4().hex)
    check("L3 404 for an unknown inv_id", st == 404, "%s %r" % (st, detail))

    # ---- O. row with skin_key AND item_id stored as explicit nulls ----------
    print("[O] row whose skin_key and item_id are both null (store-purchase shape)")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    oid = uuid.uuid4().hex
    await db.inventory.insert_one({"id": oid, "user_id": u["id"], "category": "Skins",
                                   "name": "Golden Scales Skin", "skin_key": None,
                                   "item_id": None, "rarity": "Legendary", "uses": 2})
    st, detail = await equip(u, oid)
    check("O1 400 not a 500 (no .replace on None)", st == 400, "%s %r" % (st, detail))
    check("O2 no use spent", await uses_of(oid) == 2)
    u2 = await mk_user(OFFLINE_SID, with_active_dino=True)
    oid2 = uuid.uuid4().hex
    await db.inventory.insert_one({"id": oid2, "user_id": u2["id"], "category": "Skins",
                                   "name": "Golden Scales Skin", "skin_key": None,
                                   "item_id": None, "rarity": "Legendary", "uses": 2})
    st, body = await equip(u2, oid2)
    check("O3 equips display-only when a card exists", st == 200, "%s %r" % (st, body))
    check("O4 nothing pushed to the game", read_commands() == [])

    # ---- M. stale players.json is treated as offline ------------------------
    print("[M] players.json frozen (mod/game down) -> refused, nothing spent")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=3)
    with open(PLAYERS_JSON, "w", encoding="utf-8") as f:
        json.dump({IN_GAME_SID: {"steamid": IN_GAME_SID, "actor_name": ACTOR,
                                 "dino": DINO_CLASS,
                                 "last_updated": int(time.time()) - 600}}, f)
    game_ipc._file_cache.clear()
    st, detail = await equip(u, iid)
    check("M1 409 on a stale snapshot", st == 409, "%s %r" % (st, detail))
    check("M2 no use spent", await uses_of(iid) == 3)
    check("M3 no command written", read_commands() == [])

    # ---- N. in-game but the mod has not registered an actor yet -------------
    print("[N] present in players.json but actor_name empty (mid-spawn)")
    await reset_state()
    u = await mk_user(IN_GAME_SID, with_active_dino=False)
    iid = await mk_skin(u, CODED_KEY, uses=3)
    write_players({IN_GAME_SID: ""})
    game_ipc._file_cache.clear()
    st, detail = await equip(u, iid)
    check("N1 409 until the actor exists", st == 409, "%s %r" % (st, detail))
    check("N2 no use spent", await uses_of(iid) == 3)
    write_players({IN_GAME_SID: ACTOR})
    game_ipc._file_cache.clear()

    await db.client.drop_database(os.environ["DB_NAME"])


try:
    asyncio.run(main())
finally:
    stop_mongo()

print("\n%d passed, %d failed" % (PASS, FAIL))
if _FAILED:
    print("failed: " + ", ".join(_FAILED))
sys.exit(1 if FAIL else 0)
