# -*- coding: utf-8 -*-
r"""The skin creator must never change a dinosaur's sex -- REAL I/O gate.

Owner report 2026-07-25: "the skin creator changes the dino sex ... shouldn't
change the gender."

Root cause, two surfaces:
  1. POST /api/apply (and /api/admin/apply) built the mod command via
     SkinPayloadIn.to_command and shipped it WITHOUT ``preserve_female``. The
     editor has no sex control, so ``female`` always arrived as its ``False``
     default, and SkinSystem::WriteSkin writes the command's value straight into
     CustomizerData.bIsFemale -- so every apply turned a female dino male. The
     live mod already honoured ``preserve_female`` (boot marker
     ``[SkinSystem] capability preserve_female=1``); only the glitch-reward and
     crate-paint lanes ever set it.
  2. ``preserve_female`` is NOT a transient key, so the SkinKeeper recipe stored
     the sex-bearing payload, and the bot's rejoin lane replays that payload
     VERBATIM -- re-flipping the dino male on every relog, long after the apply.

This suite drives the REAL route coroutines against a REAL MongoDB, a REAL
players.json / skin_commands.json on disk and the REAL shared SkinKeeper sqlite,
plus the REAL bot ``_restore_one``; no fake db, no stubbed skin writer on the web
side. That is the layer that held the bug -- pure-model coverage would have gone
green the whole time it was live, because ``to_command`` was doing exactly what
it was written to do.

Run:  python backend/tests_local/test_skin_apply_never_changes_sex.py
      (set MONGO_URL to reuse a running mongod; otherwise the portable
       _localtest mongod is started on a temp dbpath and stopped again.
       Set LIN_BOT_DIR to the directory holding the bot's skinkeeper_bot.py /
       skinkeeper_shared.py to include the bot-restore section.)

Exit codes: 0 all pass / 1 a check failed / 2 the suite could NOT run -- 2 is
never a pass, a suite that did not run is a failed read.
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
import types
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
TMP = tempfile.mkdtemp(prefix="lin_skinsex_test_")


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
BOT_DB = os.path.join(TMP, "data", "laislanublar.db")

PLAYER_SID = "76561199000000111"
TARGET_SID = "76561199000000333"
OFFLINE_SID = "76561199000000222"
ACTOR = "BP_Tyrannosaurus_C_2147366068"
TARGET_ACTOR = "BP_Deinosuchus_C_2147366099"
DINO_CLASS = "BP_Tyrannosaurus_C"
TARGET_CLASS = "BP_Deinosuchus_C"


def write_players(rows):
    """Real players.json in the exact prod shape: {sid: {...}} with epoch-SECOND
    last_updated (that is what the mod writes -- game_ipc normalises to ms)."""
    now = int(time.time())
    data = {}
    for sid, (actor, klass) in rows.items():
        data[sid] = {"steamid": sid, "actor_name": actor, "dino": klass,
                     "growth": 0.87, "health": 100, "max_health": 100,
                     "hunger": 90, "max_hunger": 100, "last_updated": now}
    with open(PLAYERS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f)


write_players({PLAYER_SID: (ACTOR, DINO_CLASS), TARGET_SID: (TARGET_ACTOR, TARGET_CLASS)})

MONGO_URL = start_mongo()
os.environ["MONGO_URL"] = MONGO_URL
os.environ["DB_NAME"] = "lin_skinsex_test_%s" % uuid.uuid4().hex[:8]
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ["LIN_SAVED_DIR"] = SAVED
os.environ["BOT_DB_PATH"] = BOT_DB
os.environ["LAISLANUBLAR_SKIN_CAPTURE"] = "1"   # capture ON: the stored recipe IS under test
os.environ.setdefault("RCON_HOST", "")
os.environ.setdefault("ALLOW_DEMO_LOGIN", "0")

sys.path.insert(0, BACKEND)
import game_ipc                      # noqa: E402
import skinkeeper_shared as sk       # noqa: E402
import server                        # noqa: E402

check("game_ipc reads the fixture Saved dir", game_ipc.PLAYERS_JSON == PLAYERS_JSON,
      game_ipc.PLAYERS_JSON)
check("game_ipc writes the fixture skin_commands.json",
      game_ipc.SKIN_COMMANDS_JSON == SKIN_COMMANDS, game_ipc.SKIN_COMMANDS_JSON)
check("SkinKeeper capture is ON for this suite", server.skinkeeper_web._capture_enabled())

db = server.db

# HARD SAFETY GATE -- this suite calls delete_many({}) on users, and it is meant
# to be runnable ON THE BOX against the DEPLOYED bytes (pass MONGO_URL=the real
# mongod, DB_NAME stays the temp one set above). If DB_NAME ever resolved to a
# real database -- a .env read with override=True, a stray shell export, a
# future import that loads config earlier -- those deletes would land on
# production. Refuse to run against anything but this suite's own temp database.
if not db.name.startswith("lin_skinsex_test_"):
    print("CANNOT RUN: refusing to operate on database %r -- this suite deletes "
          "collections and must only ever touch its own temp db" % db.name)
    stop_mongo()
    sys.exit(2)
if os.path.abspath(game_ipc.BOT_DB_PATH) != os.path.abspath(BOT_DB):
    print("CANNOT RUN: refusing to write the SHARED bot sqlite %r -- the "
          "SkinKeeper capture under test must go to the temp db"
          % game_ipc.BOT_DB_PATH)
    stop_mongo()
    sys.exit(2)
if os.path.abspath(game_ipc.SKIN_COMMANDS_JSON) != os.path.abspath(SKIN_COMMANDS):
    print("CANNOT RUN: refusing to write the LIVE skin_commands.json %r -- that "
          "would repaint real players' dinosaurs" % game_ipc.SKIN_COMMANDS_JSON)
    stop_mongo()
    sys.exit(2)
check("isolated: temp mongo db + temp bot sqlite + temp skin_commands.json",
      True, db.name)


# ---------------------------------------------------------------------------
# helpers over the REAL routes
# ---------------------------------------------------------------------------
def rgba(r, g, b, a=1.0):
    return {"r": r, "g": g, "b": b, "a": a}


# A full 7-region design, every channel a DIFFERENT value so a dropped or
# transposed region cannot hide behind a shared default.
DESIGN = {
    "body": rgba(0.10, 0.20, 0.30),
    "markings": rgba(0.40, 0.50, 0.60),
    "flank": rgba(0.70, 0.80, 0.90),
    "underbelly": rgba(0.15, 0.25, 0.35),
    "detail1": rgba(0.45, 0.55, 0.65),
    "eyes": rgba(0.75, 0.85, 0.95),
    "male_display": rgba(0.05, 0.95, 0.55),
}


def payload_in(**over):
    body = dict(pattern=1, skin_code="LIN1-TEST", **DESIGN)
    body.update(over)
    return server.SkinPayloadIn(**body)


def read_commands():
    if not os.path.exists(SKIN_COMMANDS):
        return []
    with open(SKIN_COMMANDS, "r", encoding="utf-8") as f:
        return json.load(f)


async def reset_state():
    await db.users.delete_many({})
    if os.path.exists(SKIN_COMMANDS):
        os.remove(SKIN_COMMANDS)
    game_ipc._file_cache.clear()      # the reader caches players.json for 1.5 s


async def mk_user(sid, role="user"):
    uid = uuid.uuid4().hex
    await db.users.insert_one({"id": uid, "steam_id": sid, "email": "t@t", "role": role})
    return await db.users.find_one({"id": uid}, {"_id": 0})


async def apply_live(user, body):
    """Call the REAL /api/apply coroutine. Returns (status_or_200, payload_or_detail)."""
    try:
        return 200, await server.apply_skin(body, user=user)
    except server.HTTPException as e:
        return e.status_code, e.detail


def admin_apply(steamid, body):
    """Call the REAL /api/admin/apply route (it is a SYNC def)."""
    try:
        return 200, server.admin_apply_skin(
            server.AdminApplyIn(steamid=steamid, payload=body), user={"role": "owner"})
    except server.HTTPException as e:
        return e.status_code, e.detail


def stored_recipe(sid):
    import sqlite3
    conn = sqlite3.connect(BOT_DB, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM skin_last_applied WHERE steam_id=?", (sid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# The skin creator is Patreon-tier gated. The gate is NOT what this suite tests
# (test_streamer_skin_creator covers it), so open it for every caller -- with the
# REAL access shape the route consumes, so a contract drift still fails loudly.
_ACCESS_OK = {"allowed": True, "via": "admin", "tier": "apex", "skin_creator": True}


async def _access_open(_user):
    return dict(_ACCESS_OK)


server._patreon_access = _access_open
check("tier helper still accepts the access shape this suite injects",
      server._skin_creator_allowed(dict(_ACCESS_OK)) is True)


# ---------------------------------------------------------------------------
# the matrix
# ---------------------------------------------------------------------------
async def web_section():
    # ---- A. THE REPORTED BUG: a plain skin-creator apply ---------------------
    print("[A] POST /api/apply -- the reported bug")
    await reset_state()
    u = await mk_user(PLAYER_SID)
    st, body = await apply_live(u, payload_in())
    check("A1 applies", st == 200, "%s %r" % (st, body))
    cmds = read_commands()
    check("A2 exactly one skin command written", len(cmds) == 1, str(len(cmds)))
    c = cmds[0] if cmds else {}
    check("A3 preserve_female set -- the LIVE pawn's sex wins (THE FIX)",
          c.get("preserve_female") is True, repr(c.get("preserve_female")))
    check("A4 targets the caller's own live actor", c.get("actor_name") == ACTOR, repr(c.get("actor_name")))
    check("A5 carries the live class", c.get("class") == DINO_CLASS, repr(c.get("class")))
    check("A6 keyed on the caller's own steamid", c.get("steamid") == PLAYER_SID, repr(c.get("steamid")))
    # The whole point of the feature still has to work.
    check("A7 all 7 colour regions still land",
          all(isinstance(c.get(k), list) and len(c[k]) == 4 for k in DESIGN), repr(sorted(c)))
    check("A8 pattern preserved", c.get("pattern") == 1, repr(c.get("pattern")))
    check("A9 linear colour space (regular-lane mod contract)",
          c.get("color_space") == "linear", repr(c.get("color_space")))
    check("A10 alpha channel passed through untouched",
          c.get("body", [0, 0, 0, 0])[3] == 1.0, repr(c.get("body")))
    check("A11 skin_code preserved", c.get("skin_code") == "LIN1-TEST", repr(c.get("skin_code")))

    # ---- B. the stored recipe -> the relog restore ---------------------------
    print("[B] SkinKeeper capture (what the rejoin restore will replay)")
    rec = stored_recipe(PLAYER_SID)
    check("B1 recipe captured", rec is not None)
    stored = json.loads(rec["payload"]) if rec else {}
    check("B2 stored recipe carries preserve_female -- restores preserve sex too",
          stored.get("preserve_female") is True, repr(stored.get("preserve_female")))
    check("B3 preserve_female is NOT stripped as a transient key",
          "preserve_female" in sk.canonical_recipe({"preserve_female": True, "steamid": "1"}))
    check("B4 actor_name/steamid ARE stripped (transient contract intact)",
          "actor_name" not in stored and "steamid" not in stored, repr(sorted(stored)))
    check("B5 stored as the regular lane", rec and rec["kind"] == "regular", rec and rec["kind"])

    # ---- C. a client that ASKS for a sex change still cannot get one ---------
    print("[C] hostile client posts female=true")
    await reset_state()
    u = await mk_user(PLAYER_SID)
    st, _ = await apply_live(u, payload_in(female=True))
    c = (read_commands() or [{}])[0]
    check("C1 applies", st == 200, str(st))
    check("C2 preserve_female still set -- the mod overrides whatever was posted",
          c.get("preserve_female") is True, repr(c.get("preserve_female")))
    await reset_state()
    u = await mk_user(PLAYER_SID)
    st, _ = await apply_live(u, payload_in(female=False))
    c = (read_commands() or [{}])[0]
    check("C3 same for female=false -- the field is inert either way",
          c.get("preserve_female") is True, repr(c.get("preserve_female")))

    # ---- D. owner applying to ANOTHER player -------------------------------
    print("[D] POST /api/admin/apply -- owner paints a player's dino")
    await reset_state()
    st, body = await asyncio.to_thread(admin_apply, TARGET_SID, payload_in())
    check("D1 applies", st == 200, "%s %r" % (st, body))
    c = (read_commands() or [{}])[0]
    check("D2 preserve_female set -- an owner repaint never re-sexes the player",
          c.get("preserve_female") is True, repr(c.get("preserve_female")))
    check("D3 keyed on the TARGET sid, never the acting owner",
          c.get("steamid") == TARGET_SID, repr(c.get("steamid")))
    check("D4 targets the target's own live actor",
          c.get("actor_name") == TARGET_ACTOR, repr(c.get("actor_name")))
    rec = stored_recipe(TARGET_SID)
    check("D5 recipe captured against the TARGET sid", rec is not None)
    check("D6 stored recipe carries preserve_female",
          rec and json.loads(rec["payload"]).get("preserve_female") is True)

    # ---- E. offline: unchanged, still refused with nothing written ----------
    print("[E] not in the game")
    await reset_state()
    u = await mk_user(OFFLINE_SID)
    st, detail = await apply_live(u, payload_in())
    check("E1 409 refused", st == 409, "%s %r" % (st, detail))
    check("E2 no command written", read_commands() == [])

    # ---- F. the two lanes that were ALREADY correct stay correct ------------
    print("[F] regression: lanes that already preserved sex")
    await reset_state()
    src = open(os.path.join(BACKEND, "server.py"), "r", encoding="utf-8").read()
    check("F1 glitch reward lane still sets preserve_female",
          src.count('cmd["preserve_female"] = True') >= 4,
          "occurrences=%d" % src.count('cmd["preserve_female"] = True'))
    check("F2 park/redeem replay is NOT flagged (a redeemed dino keeps its "
          "PARKED sex -- that lane restores stored state on purpose)",
          'preserve_female' not in open(os.path.join(BACKEND, "vault.py"), "r",
                                        encoding="utf-8").read())


# ---------------------------------------------------------------------------
# G. the bot rejoin lane -- REAL _restore_one over the REAL shared helpers
# ---------------------------------------------------------------------------
async def bot_section(bot_dir):
    print("[G] bot rejoin restore (%s)" % bot_dir)
    written = []

    # Real contracts, not convenient stubs: mod_ipc.write_skin_command returns a
    # TUPLE (ok, reason) on the bot side (a bare bool here would let a regression
    # in the caller's unpack slip through), and read_player returns the
    # players.json row shape the readiness gate actually inspects.
    mod_ipc = types.ModuleType("mod_ipc")
    mod_ipc.write_skin_command = lambda cmd: (written.append(json.loads(json.dumps(cmd))), (True, ""))[1]
    mod_ipc.read_player = lambda sid: {"steamid": sid, "actor_name": ACTOR, "max_hunger": 100}
    cfg = types.ModuleType("config")
    cfg.DB_PATH = BOT_DB
    sys.modules["mod_ipc"] = mod_ipc
    sys.modules["config"] = cfg
    sys.path.insert(0, bot_dir)
    for stale in ("skinkeeper_shared", "skinkeeper_bot"):
        sys.modules.pop(stale, None)
    import skinkeeper_shared as bsk       # noqa: E402  (the BOT copy)
    import skinkeeper_bot                 # noqa: E402

    check("G1 bot + web carry a byte-identical skinkeeper_shared",
          open(bsk.__file__, "rb").read().replace(b"\r\n", b"\n")
          == open(sk.__file__, "rb").read().replace(b"\r\n", b"\n"))

    # A LEGACY row exactly as the pre-fix skin creator stored it.
    legacy = {"class": DINO_CLASS, "female": False, "variation": 0.004, "pattern": 1,
              "color_space": "linear", "body": [0.1, 0.2, 0.3, 1.0],
              "markings": [0.4, 0.5, 0.6, 1.0], "flank": [0.7, 0.8, 0.9, 1.0],
              "underbelly": [0.15, 0.25, 0.35, 1.0], "detail1": [0.45, 0.55, 0.65, 1.0],
              "eyes": [0.75, 0.85, 0.95, 1.0], "male_display": [0.05, 0.95, 0.55, 1.0],
              "skin_code": "LIN1-LEGACY"}
    verbatim = bsk.build_restore_command(legacy, PLAYER_SID, ACTOR, "rejoin-deadbeef")
    check("G2 the bug is real: a verbatim replay of a legacy recipe carries "
          "female=False and NO preserve_female",
          verbatim.get("female") is False and "preserve_female" not in verbatim,
          repr({k: verbatim.get(k) for k in ("female", "preserve_female")}))

    def seed_recipe(payload):
        """Store the recipe through the REAL shared writer, so _restore_one's
        re-verify read (active row + digest match) sees a genuine row."""
        import sqlite3
        pj = bsk.canonical_payload_json(payload)
        digest = bsk.compute_recipe_digest(PLAYER_SID, pj)
        conn = sqlite3.connect(BOT_DB, timeout=5.0, isolation_level=None)
        try:
            bsk.ensure_skin_last_applied(conn)
            bsk.record_skin_recipe(conn, PLAYER_SID, dino_class=DINO_CLASS,
                                   actor_name=ACTOR, kind="regular", payload_json=pj,
                                   recipe_digest=digest,
                                   updated_utc=bsk.datetime.now(bsk.timezone.utc).isoformat())
        finally:
            conn.close()
        return digest

    digest = seed_recipe(legacy)
    await skinkeeper_bot._restore_one(PLAYER_SID, legacy, DINO_CLASS,
                                      "TestPlayer", "", digest)

    check("G3 the restore actually wrote a command", len(written) == 1, str(len(written)))
    c = written[0] if written else {}
    check("G4 preserve_female set on the replay -- a relog no longer re-sexes "
          "the dino, INCLUDING for recipes stored before the fix",
          c.get("preserve_female") is True, repr(c.get("preserve_female")))
    check("G5 the replay is otherwise byte-identical to the stored recipe",
          all(c.get(k) == v for k, v in legacy.items()),
          repr({k: (v, c.get(k)) for k, v in legacy.items() if c.get(k) != v}))
    check("G6 restore stamps the rejoin marker (never re-captured as an apply)",
          bsk.is_restore_echo(c) is True, repr(c.get("request_id")))

    # A glitch recipe: its contract is the ABSENCE of color_space. The flag must
    # not disturb it, and it was already flagged, so this must be a no-op.
    written.clear()
    glitch = {"class": DINO_CLASS, "female": True, "variation": 0.0, "pattern": 0,
              "body": [-8.0, 12.0, -3.0, 1.0], "markings": [9.0, -4.0, 7.0, 1.0],
              "preserve_female": True}
    gdigest = seed_recipe(glitch)
    await skinkeeper_bot._restore_one(PLAYER_SID, glitch, DINO_CLASS,
                                      "TestPlayer", "", gdigest)
    g = written[0] if written else {}
    check("G7 glitch replay keeps color_space ABSENT", "color_space" not in g, repr(sorted(g)))
    check("G8 glitch raw values survive untouched",
          g.get("body") == [-8.0, 12.0, -3.0, 1.0] and g.get("variation") == 0.0, repr(g.get("body")))
    check("G9 preserve_female unchanged on a lane that already had it",
          g.get("preserve_female") is True)


async def main():
    await web_section()
    bot_dir = os.environ.get("LIN_BOT_DIR")
    if bot_dir and os.path.isfile(os.path.join(bot_dir, "skinkeeper_bot.py")):
        await bot_section(bot_dir)
    else:
        print("[G] SKIPPED -- set LIN_BOT_DIR to the bot directory to run the "
              "rejoin-restore section (it is NOT in this repo tree)")
        check("G0 bot section ran", False, "LIN_BOT_DIR not set or skinkeeper_bot.py missing")
    try:
        await server.client.drop_database(os.environ["DB_NAME"])
    except Exception as exc:
        print("  (warn) could not drop temp db: %s" % exc)


if __name__ == "__main__":
    rc = 1
    try:
        asyncio.run(main())
        print("\n%d passed, %d failed" % (PASS, FAIL))
        if _FAILED:
            print("FAILED: %s" % ", ".join(_FAILED))
        rc = 0 if FAIL == 0 else 1
    finally:
        stop_mongo()
    sys.exit(rc)
