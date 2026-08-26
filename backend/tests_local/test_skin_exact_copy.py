# -*- coding: utf-8 -*-
r"""Exact-copy sidecar — "Copiar mi skin actual" must copy the SAME skin.

Owner report 2026-08-08: "i see the skin when i hatch and grow is perfect but
then when i copy the current skin is different." The copy lane's editor
conversion clamps every channel into display gamut (0..1) and folds pattern
into 0..2 — a hatched/crate glitch skin (channels at hundreds, alpha rails)
came back re-authored. The fix: the copy stores a server-WITNESSED verbatim
sidecar (skin_exact.py) and POST /api/apply-preset replays it byte-for-byte
through the glitch-lane command shape (no sRGB decode, no eps jitter).

REAL-I/O suite on the same harness as test_skin_apply_never_changes_sex: real
mongod, real Saved/ + skin_meta/ fixture dirs, the REAL route coroutines and
the REAL shared-module SkinKeeper capture. Pure-model coverage would have gone
green while the bug was live — the clamp sat between two green halves.

Run:  python backend/tests_local/test_skin_exact_copy.py

Exit codes: 0 all pass / 1 a check failed / 2 the suite could NOT run — 2 is
never a pass, a suite that did not run is a failed read.
"""
import asyncio
import json
import math
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
# mongod (portable, temp dbpath) — the suite refuses to "pass" without one
# ---------------------------------------------------------------------------
PORTABLE_MONGOD = r"C:\LaIslaNublarWeb\_localtest\mongodb-7.0.28\mongodb-win32-x86_64-windows-7.0.28\bin\mongod.exe"
_mongo_proc = None
TMP = tempfile.mkdtemp(prefix="lin_exactcopy_test_")


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
# env -> import the REAL server module (fixture Saved + skin_meta dirs)
# ---------------------------------------------------------------------------
SAVED = os.path.join(TMP, "Saved")
SKIN_META = os.path.join(TMP, "skin_meta")
os.makedirs(SAVED, exist_ok=True)
os.makedirs(SKIN_META, exist_ok=True)
PLAYERS_JSON = os.path.join(SAVED, "players.json")
SKIN_COMMANDS = os.path.join(SAVED, "skin_commands.json")
SKIN_SNAPSHOTS = os.path.join(SAVED, "skin_snapshots.json")
BOT_DB = os.path.join(TMP, "data", "laislanublar.db")

PLAYER_SID = "76561199000000444"
OFFLINE_SID = "76561199000000555"
ACTOR = "BP_Ceratosaurus_C_2147366444"
DINO_CLASS = "BP_Ceratosaurus_C"


def write_players(rows):
    now = int(time.time())
    data = {}
    for sid, (actor, klass) in rows.items():
        data[sid] = {"steamid": sid, "actor_name": actor, "dino": klass,
                     "growth": 0.92, "health": 100, "max_health": 100,
                     "hunger": 90, "max_hunger": 100, "last_updated": now}
    with open(PLAYERS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f)


write_players({PLAYER_SID: (ACTOR, DINO_CLASS)})

MONGO_URL = start_mongo()
os.environ["MONGO_URL"] = MONGO_URL
os.environ["DB_NAME"] = "lin_exactcopy_test_%s" % uuid.uuid4().hex[:8]
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ["LIN_SAVED_DIR"] = SAVED
os.environ["LIN_SKIN_META_DIR"] = SKIN_META
os.environ["BOT_DB_PATH"] = BOT_DB
os.environ["LAISLANUBLAR_SKIN_CAPTURE"] = "1"   # the stored recipe IS under test
os.environ.setdefault("RCON_HOST", "")
os.environ.setdefault("ALLOW_DEMO_LOGIN", "0")

sys.path.insert(0, BACKEND)
import game_ipc                      # noqa: E402
import skin_exact                    # noqa: E402
import server                        # noqa: E402

check("game_ipc reads the fixture Saved dir", game_ipc.PLAYERS_JSON == PLAYERS_JSON,
      game_ipc.PLAYERS_JSON)
check("presets store lives in the fixture skin_meta dir",
      server._PRESETS_DIR.startswith(TMP), server._PRESETS_DIR)

db = server.db

# HARD SAFETY GATES — refuse to touch anything but this suite's own temp world.
if not db.name.startswith("lin_exactcopy_test_"):
    print("CANNOT RUN: refusing db %r" % db.name)
    stop_mongo()
    sys.exit(2)
if os.path.abspath(game_ipc.SKIN_COMMANDS_JSON) != os.path.abspath(SKIN_COMMANDS):
    print("CANNOT RUN: refusing LIVE skin_commands.json %r" % game_ipc.SKIN_COMMANDS_JSON)
    stop_mongo()
    sys.exit(2)
if not os.path.abspath(server._PRESETS_DIR).startswith(os.path.abspath(TMP)):
    print("CANNOT RUN: refusing LIVE presets dir %r" % server._PRESETS_DIR)
    stop_mongo()
    sys.exit(2)
check("isolated: temp mongo + temp Saved + temp presets", True, db.name)


# ---------------------------------------------------------------------------
# fixtures — a REAL glitch-space snapshot (PI-regime shape: signed channels,
# alpha rails, in-domain pattern) and an in-gamut editor-made one
# ---------------------------------------------------------------------------
GLITCH_SNAP = {
    "female": False, "variation": 0.0, "pattern": 2,
    "body": [-2.4, 9.455, -3.163, -999.0],
    "markings": [-6.56, -3.575, -9.411, -999.0],
    "flank": [-7.974, 2.019, 5.68, -999.0],
    "underbelly": [6.911, 7.633, 9.792, -999.0],
    "detail1": [-6.545, -4.241, -6.744, -777.0],
    "eyes": [-9.731, 5.732, 4.071, -555.0],
    "male_display": [-1.659, -1.234, -3.192, 999.0],
}
INGAMUT_SNAP = {
    "female": True, "variation": 0.004, "pattern": 1,
    "body": [0.1, 0.2, 0.3, 1.0], "markings": [0.4, 0.5, 0.6, 1.0],
    "flank": [0.7, 0.8, 0.9, 1.0], "underbelly": [0.15, 0.25, 0.35, 0.5],
    "detail1": [0.45, 0.55, 0.65, 1.0], "eyes": [0.75, 0.85, 0.95, 1.0],
    "male_display": [0.05, 0.95, 0.55, 1.0],
}
# A REAL worn glitch look whose magnitudes fall PAST the -900000 sentinel —
# captured verbatim off a live La Isla Nublar pawn 2026-08-20. Three slots are
# ordinary in-gamut colour, which is what makes it provably a worn design and
# not a restart-window unset read. This is the payload the owner-grant lane
# exists for; the player copy lane still refuses it.
POISON_SNAP = {
    "female": False, "variation": 8.0, "pattern": 2,
    "body": [-795233.5625, -7952343.5, -7952343.5, -794.234375],
    "markings": [-7952343.5, -795233.5625, -7951.497559, -795145.9375],
    "flank": [0.172337, 0.154838, 0.146566, 1.0],
    "underbelly": [-795233.375, -79523440.0, -7952343.0, -794.234375],
    "detail1": [-999999.0, -999999.0, -999999.0, -999667.0],
    "eyes": [0.999205, 0.539818, 0.539818, 1.0],
    "male_display": [0.682085, 0.020759, 0.020759, 1.0],
}
SLOTS = list(skin_exact.SLOT_KEYS)


def write_snapshot(snap, actor=ACTOR):
    with open(SKIN_SNAPSHOTS, "w", encoding="utf-8") as f:
        json.dump({actor: snap} if snap is not None else {}, f)
    game_ipc._file_cache.clear()


def raw_from(snap):
    return {k: list(snap[k]) for k in SLOTS} | {"pattern": snap["pattern"], "variation": snap["variation"]}


def read_commands():
    if not os.path.exists(SKIN_COMMANDS):
        return []
    with open(SKIN_COMMANDS, "r", encoding="utf-8") as f:
        return json.load(f)


def read_presets_file(sid):
    p = server._presets_path(sid)
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


async def reset_state():
    await db.users.delete_many({})
    for f in (SKIN_COMMANDS, server._presets_path(PLAYER_SID)):
        if os.path.exists(f):
            os.remove(f)
    game_ipc._file_cache.clear()


async def mk_user(sid):
    uid = uuid.uuid4().hex
    await db.users.insert_one({"id": uid, "steam_id": sid, "email": "t@t", "role": "user"})
    return await db.users.find_one({"id": uid}, {"_id": 0})


def preset_body(raw=None, name="Skin actual — Cerato", payload_pattern=1):
    body = {
        "name": name, "dino_class": "Ceratosaurus",
        "payload": dict(pattern=payload_pattern, skin_code="",
                        **{k: {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0} for k in SLOTS}),
    }
    if raw is not None:
        body["raw"] = raw
    return server.SkinPresetIn(**body)


async def save_preset(user, body):
    try:
        return 200, await server.save_preset(body, user=user)
    except server.HTTPException as e:
        return e.status_code, e.detail


async def update_preset(user, pid, body):
    try:
        return 200, await server.update_preset(pid, body, user=user)
    except server.HTTPException as e:
        return e.status_code, e.detail


async def apply_preset(user, pid):
    try:
        return 200, await server.apply_preset_exact(server.ApplyPresetIn(preset_id=pid), user=user)
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


# Patreon gate: opened for most sections (the gate itself is section G).
# tier deliberately "sub": skin-creator allowed, NOT Glitch-Lab-entitled -- the
# witness sections below pin the non-entitled contract (2026-08-23 change).
_ACCESS_OK = {"allowed": True, "via": "admin", "tier": "sub", "skin_creator": True}


async def _access_open(_user):
    return dict(_ACCESS_OK)


_real_patreon_access = server._patreon_access
server._patreon_access = _access_open


# ---------------------------------------------------------------------------
# [U] pure module — extraction, lossiness, matching, command build
# ---------------------------------------------------------------------------
def unit_section():
    print("[U] skin_exact pure units")
    raw = skin_exact.extract_raw(GLITCH_SNAP)
    check("U1 glitch snapshot extracts", raw is not None)
    check("U2 extraction is VERBATIM (every float identical, no fold)",
          raw is not None and all(raw[k] == [float(c) for c in GLITCH_SNAP[k]] for k in SLOTS)
          and raw["pattern"] == 2 and raw["variation"] == 0.0)
    check("U3 glitch payload is lossy for the editor", skin_exact.is_lossy(raw) is True)
    ing = skin_exact.extract_raw(INGAMUT_SNAP)
    check("U4 in-gamut snapshot extracts too (sidecar as insurance)", ing is not None)
    check("U5 in-gamut payload is NOT lossy (editor copy already faithful)",
          skin_exact.is_lossy(ing) is False)
    check("U6 editor's own variation jitter is not lossy",
          skin_exact.is_lossy(dict(ing, variation=0.01)) is False)
    check("U7 out-of-editor pattern alone IS lossy",
          skin_exact.is_lossy(dict(ing, pattern=12)) is True)

    # Refusals — never folded, never partial
    for name, snap in [
        ("poison channel", dict(GLITCH_SNAP, body=[-999999.0, 0, 0, 1])),
        ("poison pattern", dict(GLITCH_SNAP, pattern=-8)),
        ("short slot (no alpha)", dict(GLITCH_SNAP, eyes=[1, 2, 3])),
        ("missing slot", {k: v for k, v in GLITCH_SNAP.items() if k != "flank"}),
        ("non-finite", dict(GLITCH_SNAP, body=[float("nan"), 0, 0, 1])),
        # 2026-08-13: the shared glitch ceiling rose to 1e12 (owner-proven
        # -1e11 payloads) — the over-window literal rises with it.
        ("over window", dict(GLITCH_SNAP, body=[2.0e12, 0, 0, 1])),
        ("fractional pattern", dict(GLITCH_SNAP, pattern=1.5)),
        ("huge pattern", dict(GLITCH_SNAP, pattern=64)),
        ("missing variation", {k: v for k, v in GLITCH_SNAP.items() if k != "variation"}),
        ("not a dict", None),
    ]:
        check("U8 refuses %s" % name, skin_exact.extract_raw(snap) is None)

    ok, _ = skin_exact.validate_raw(raw_from(GLITCH_SNAP))
    check("U9 validate_raw accepts the witnessed shape", ok is True)
    check("U10 match: identical passes",
          skin_exact.raw_matches_snapshot(raw_from(GLITCH_SNAP), GLITCH_SNAP) is True)
    tweaked = raw_from(GLITCH_SNAP)
    tweaked["body"] = [-2.4, 9.455, -3.163, -998.0]
    check("U11 match: a single changed float REFUSES (no minting)",
          skin_exact.raw_matches_snapshot(tweaked, GLITCH_SNAP) is False)
    check("U12 match: float round-trip noise within 1e-6 passes",
          skin_exact.raw_matches_snapshot(
              {**raw_from(GLITCH_SNAP), "variation": 1e-9}, GLITCH_SNAP) is True)

    cmd = skin_exact.build_exact_command(raw, ACTOR, DINO_CLASS, PLAYER_SID)
    check("U13 command is VERBATIM — no eps jitter on any channel",
          all(cmd[k] == raw[k] for k in SLOTS) and cmd["variation"] == 0.0 and cmd["pattern"] == 2)
    check("U14 command has NO color_space key (glitch-lane shape, no decode)",
          "color_space" not in cmd)
    check("U15 command preserves the live pawn's sex (preserve_female)",
          cmd.get("preserve_female") is True)
    # The dangerous direction, pinned: routing this payload through the editor
    # lane's to_command would decode+jitter it — prove the shapes DIFFER.
    editor_like = server.SkinPayloadIn(
        pattern=2, **{k: {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0} for k in SLOTS}
    ).to_command(ACTOR, DINO_CLASS, PLAYER_SID)
    check("U16 editor lane provably jitters/decodes (mutant pin: exact lane must never route there)",
          "color_space" in editor_like and editor_like["body"] != [0.1, 0.2, 0.3, 1.0])

    # -- owner grant (2026-08-20): the sentinel waiver, and ONLY the sentinel --
    check("V1 a PLAYER copy of a past-sentinel look still refuses (door unchanged)",
          skin_exact.extract_raw(POISON_SNAP) is None)
    gr = skin_exact.extract_raw(POISON_SNAP, owner_grant=True)
    check("V2 an OWNER grant extracts the same snapshot", gr is not None)
    check("V3 the stamp rides into the sidecar as the record of WHY",
          gr is not None and gr.get("owner_grant") is True)
    check("V4 grant extraction is VERBATIM (no fold, no clamp)",
          gr is not None and all(gr[k] == [float(c) for c in POISON_SNAP[k]] for k in SLOTS)
          and gr["pattern"] == 2 and gr["variation"] == 8.0)
    ok, reason = skin_exact.validate_raw(gr)
    check("V5 validate_raw accepts the granted sidecar", ok is True, reason)
    ok, reason = skin_exact.validate_raw({k: v for k, v in gr.items() if k != "owner_grant"})
    check("V6 the SAME bytes without the flag still refuse (the flag is what carries it)",
          ok is False and reason == "poison_body", "%r %r" % (ok, reason))
    check("V7 the grant waives the SENTINEL and nothing else", all(
        skin_exact.validate_raw(dict(gr, **mut))[0] is False for mut in (
            {"body": [2.0e12, 0, 0, 1]},          # over the 1e12 window
            {"eyes": [float("nan"), 0, 0, 1]},    # non-finite
            {"flank": [1, 2, 3]},                 # short slot
            {"pattern": 1.5},                     # fractional
            {"pattern": 64},                      # out of replay range
            {"variation": 2.0e12},                # variation window
        )))
    check("V8 only the literal True is a grant — no truthy strings, ints or absent keys",
          all(skin_exact.is_owner_grant(dict(gr, owner_grant=v)) is False
              for v in ("yes", 1, "True", None, [])) 
          and skin_exact.is_owner_grant({k: v for k, v in gr.items() if k != "owner_grant"}) is False)
    check("V9 grant is witnessed against the live pawn at its own grant level",
          skin_exact.raw_matches_snapshot(gr, POISON_SNAP) is True)
    check("V10 a single changed float still REFUSES the witness (no minting)",
          skin_exact.raw_matches_snapshot(dict(gr, eyes=[0.5, 0.5, 0.5, 1.0]), POISON_SNAP) is False)
    check("V11 an UNgranted sidecar is still witnessed the old way (regression)",
          skin_exact.raw_matches_snapshot(raw_from(GLITCH_SNAP), GLITCH_SNAP) is True
          and skin_exact.raw_matches_snapshot(
              {k: v for k, v in gr.items() if k != "owner_grant"}, POISON_SNAP) is False)
    check("V12 a granted glitch payload is LOSSY -> the editor arms verbatim apply",
          skin_exact.is_lossy(gr) is True)
    gcmd = skin_exact.build_exact_command(gr, ACTOR, DINO_CLASS, PLAYER_SID)
    check("V13 the wire command is verbatim and carries NO owner_grant key to the mod",
          "owner_grant" not in gcmd and all(gcmd[k] == gr[k] for k in SLOTS)
          and gcmd["pattern"] == 2 and gcmd["variation"] == 8.0 and "color_space" not in gcmd)


# ---------------------------------------------------------------------------
# route matrix
# ---------------------------------------------------------------------------
async def route_sections():
    # ---- A. witnessed save stores the sidecar --------------------------------
    print("[A] POST /api/presets with a witnessed raw sidecar")
    await reset_state()
    write_snapshot(GLITCH_SNAP)
    u = await mk_user(PLAYER_SID)
    st, out = await save_preset(u, preset_body(raw=raw_from(GLITCH_SNAP)))
    check("A1 saves", st == 200, "%s %r" % (st, out))
    rows = read_presets_file(PLAYER_SID)
    check("A2 one preset stored", len(rows) == 1, str(len(rows)))
    stored = rows[0] if rows else {}
    check("A3 sidecar stored VERBATIM",
          stored.get("raw") == raw_from(GLITCH_SNAP), json.dumps(stored.get("raw"))[:120])
    check("A4 clamped payload still stored beside it (editor display contract)",
          isinstance(stored.get("payload"), dict) and "body" in stored.get("payload", {}))

    # ---- B. unwitnessed raw refused ------------------------------------------
    print("[B] the free save lane can NOT mint payloads the dino never wore")
    tweaked = raw_from(GLITCH_SNAP)
    tweaked["eyes"] = [0.0, 0.0, 0.0, 99999.0]   # in-window, but never worn
    st, out = await save_preset(u, preset_body(raw=tweaked))
    check("B1 mismatched sidecar -> 409", st == 409, "%s %r" % (st, out))
    check("B2 nothing extra stored", len(read_presets_file(PLAYER_SID)) == 1)
    write_snapshot(GLITCH_SNAP, actor="BP_Other_C_1")   # caller has no snapshot row
    st, out = await save_preset(u, preset_body(raw=raw_from(GLITCH_SNAP)))
    check("B3 no live snapshot -> 409", st == 409, "%s %r" % (st, out))
    write_snapshot(GLITCH_SNAP)
    off = await mk_user(OFFLINE_SID)
    st, out = await save_preset(off, preset_body(raw=raw_from(GLITCH_SNAP)))
    check("B4 not in game -> 409", st == 409, "%s %r" % (st, out))

    # ---- C. invalid raw shapes 422 -------------------------------------------
    print("[C] invalid sidecars are refused, never folded")
    for name, mut in [
        ("poison channel", {"body": [-999999.0, 0, 0, 1]}),
        ("poison pattern", {"pattern": -8}),
        ("over window", {"flank": [2.0e12, 0, 0, 1]}),
        ("huge pattern", {"pattern": 64}),
    ]:
        bad = raw_from(GLITCH_SNAP) | mut
        st, out = await save_preset(u, preset_body(raw=bad))
        check("C %s -> 422" % name, st == 422, "%s %r" % (st, out))

    # ---- D. exact apply replays verbatim -------------------------------------
    print("[D] POST /api/apply-preset — the verbatim replay door")
    pid = read_presets_file(PLAYER_SID)[0]["id"]
    st, out = await apply_preset(u, pid)
    check("D1 applies", st == 200 and out.get("exact") is True, "%s %r" % (st, out))
    cmds = read_commands()
    check("D2 exactly one command written", len(cmds) == 1, str(len(cmds)))
    c = cmds[0] if cmds else {}
    check("D3 every channel BYTE-EQUAL to the witnessed snapshot (no jitter, no decode)",
          all(c.get(k) == [float(x) for x in GLITCH_SNAP[k]] for k in SLOTS),
          json.dumps({k: c.get(k) for k in ("body",)}))
    check("D4 pattern + variation verbatim", c.get("pattern") == 2 and c.get("variation") == 0.0)
    check("D5 no color_space key (never the editor decode lane)", "color_space" not in c)
    check("D6 preserve_female present — live pawn's sex wins", c.get("preserve_female") is True)
    check("D7 targeted at the caller's own live dino only",
          c.get("steamid") == PLAYER_SID and c.get("actor_name") == ACTOR and c.get("class") == DINO_CLASS)
    rec = stored_recipe(PLAYER_SID)
    check("D8 SkinKeeper recipe captured kind=glitch (relog replays the exact copy)",
          rec is not None and rec.get("kind") == "glitch", repr(rec)[:120])
    if rec:
        rp = json.loads(rec["payload"])
        check("D9 recipe payload == the enqueued verbatim command",
              all(rp.get(k) == c.get(k) for k in SLOTS) and rp.get("pattern") == 2)

    # ---- E. refusal matrix on apply ------------------------------------------
    print("[E] apply-preset refusals")
    st, out = await apply_preset(u, "nope-" + uuid.uuid4().hex[:6])
    check("E1 unknown preset -> 404", st == 404, "%s %r" % (st, out))
    st2, out2 = await save_preset(u, preset_body())          # no sidecar
    pid_plain = out2["id"] if st2 == 200 else None
    st, out = await apply_preset(u, pid_plain)
    check("E2 preset without sidecar -> 400 (editor lane owns it)", st == 400, "%s %r" % (st, out))
    rows = read_presets_file(PLAYER_SID)
    for r in rows:
        if r["id"] == pid:
            r["raw"]["body"] = [0, 0, 0, 5.0e12]       # corrupted-on-disk future shape
    server._write_presets(PLAYER_SID, rows)
    st, out = await apply_preset(u, pid)
    check("E3 stored sidecar re-validated at apply -> 422 (bound-raise mutant dies here)",
          st == 422, "%s %r" % (st, out))
    write_players({})                                   # player logs off
    game_ipc._file_cache.clear()
    st, out = await apply_preset(u, pid_plain)
    check("E4 no active dino -> 409", st == 409, "%s %r" % (st, out))
    write_players({PLAYER_SID: (ACTOR, DINO_CLASS)})
    game_ipc._file_cache.clear()

    # ---- F. update semantics --------------------------------------------------
    print("[F] PUT /presets — an edited preset stops being an exact copy")
    await reset_state()
    write_snapshot(GLITCH_SNAP)
    u = await mk_user(PLAYER_SID)
    st, out = await save_preset(u, preset_body(raw=raw_from(GLITCH_SNAP)))
    pid = out["id"]
    st, out = await update_preset(u, pid, preset_body(name="renombrado"))
    check("F1 update without raw drops the sidecar", st == 200
          and "raw" not in read_presets_file(PLAYER_SID)[0])
    st, out = await update_preset(u, pid, preset_body(raw=raw_from(GLITCH_SNAP)))
    check("F2 update WITH raw re-witnesses and re-stores", st == 200
          and read_presets_file(PLAYER_SID)[0].get("raw") == raw_from(GLITCH_SNAP))

    # ---- G. the Patreon gate is IDENTICAL to /api/apply -----------------------
    print("[G] gate parity with POST /api/apply")
    async def _closed(_user):
        return {"allowed": False, "reason": "none"}
    server._patreon_access = _closed
    st, out = await apply_preset(u, pid)
    check("G1 not allowed -> 403 patreon_required",
          st == 403 and isinstance(out, dict) and out.get("code") == "patreon_required",
          "%s %r" % (st, str(out)[:80]))

    async def _juvie(_user):
        return {"allowed": True, "via": "patreon", "tier": "juvie"}
    server._patreon_access = _juvie
    st_a, out_a = await apply_preset(u, pid)
    try:
        await server.apply_skin(server.SkinPayloadIn(
            pattern=1, **{k: {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0} for k in SLOTS}), user=u)
        st_b, out_b = 200, {}
    except server.HTTPException as e:
        st_b, out_b = e.status_code, e.detail
    check("G2 juvie tier -> 403 tier_insufficient on BOTH routes",
          st_a == 403 and st_b == 403
          and out_a.get("code") == "tier_insufficient" == out_b.get("code"))
    check("G3 the two routes raise the SAME message (no gate drift)",
          out_a.get("message") == out_b.get("message"),
          "%r vs %r" % (str(out_a.get("message"))[:60], str(out_b.get("message"))[:60]))
    server._patreon_access = _access_open
    check("G4 free lane really is free: save with sidecar needs NO patreon",
          (await save_preset(u, preset_body(raw=raw_from(GLITCH_SNAP))))[0] == 200)

    # ---- H. regression: the pre-sidecar contract is untouched -----------------
    print("[H] normal copies byte-identical to the old behaviour")
    await reset_state()
    write_snapshot(INGAMUT_SNAP)
    u = await mk_user(PLAYER_SID)
    st, out = await save_preset(u, preset_body())
    check("H1 plain save (no raw field) stores NO sidecar key",
          st == 200 and "raw" not in read_presets_file(PLAYER_SID)[0])
    st, out = await save_preset(u, preset_body(raw=raw_from(INGAMUT_SNAP)))
    check("H2 in-gamut sidecar still witnesses + stores (insurance)", st == 200)
    listed = server.list_presets(user=u)
    check("H3 GET /presets returns both, sidecar included",
          len(listed["presets"]) == 2 and listed["presets"][1].get("raw") is not None)

    # ---- I. owner grant: reachable from the owner tool, NEVER from the wire --
    print("[I] owner-granted exact copy (past-sentinel worn look)")
    await reset_state()
    write_snapshot(POISON_SNAP)
    u = await mk_user(PLAYER_SID)
    st, out = await save_preset(u, preset_body(raw=raw_from(POISON_SNAP)))
    check("I1 a player copying this look is still refused -> 422", st == 422, "%s %r" % (st, out))
    st, out = await save_preset(u, preset_body(raw=raw_from(POISON_SNAP) | {"owner_grant": True}))
    check("I2 a request body CANNOT mint the flag (model emits declared fields only) -> 422",
          st == 422, "%s %r" % (st, out))
    check("I3 nothing was stored by either attempt", read_presets_file(PLAYER_SID) == [])

    # what the owner tool writes: the clamped payload + a witnessed granted sidecar
    granted = skin_exact.extract_raw(game_ipc.read_skin_snapshot(ACTOR), owner_grant=True)
    check("I4 the tool's own witness passes on the live snapshot", granted is not None)
    server._write_presets(PLAYER_SID, [{
        "id": "owner-grant-test", "name": "Skin guardada por el staff",
        "dino_class": DINO_CLASS, "raw": granted,
        "payload": server.SkinPayloadIn(
            pattern=2, **{k: {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0} for k in SLOTS}
        ).model_dump(),
    }])
    st, out = await apply_preset(u, "owner-grant-test")
    check("I5 the granted preset APPLIES (not a dead button)",
          st == 200 and out.get("exact") is True, "%s %r" % (st, out))
    cmds = read_commands()
    c = cmds[-1] if cmds else {}
    check("I6 every channel BYTE-EQUAL to the worn look — no fold, no jitter, no decode",
          all(c.get(k) == [float(x) for x in POISON_SNAP[k]] for k in SLOTS)
          and c.get("pattern") == 2 and c.get("variation") == 8.0
          and "color_space" not in c and "owner_grant" not in c,
          json.dumps({k: c.get(k) for k in ("body", "detail1")}))
    rec = stored_recipe(PLAYER_SID)
    check("I7 SkinKeeper captured it kind=glitch — the grant survives a relog",
          rec is not None and rec.get("kind") == "glitch", repr(rec)[:120])
    rows = read_presets_file(PLAYER_SID)
    rows[0]["raw"] = {k: v for k, v in rows[0]["raw"].items() if k != "owner_grant"}
    server._write_presets(PLAYER_SID, rows)
    st, out = await apply_preset(u, "owner-grant-test")
    check("I8 strip the flag on disk and it refuses again -> 422 (mutant pin)",
          st == 422, "%s %r" % (st, out))




# ---------------------------------------------------------------------------
# [J] Glitch Lab: website owners + Streamer role + Adult/Elder/Apex author
# arbitrary glitch payloads (numbers, not copies); everyone else keeps the
# witness rules verbatim. Same real-I/O harness.
# ---------------------------------------------------------------------------

async def _acc_sub(_user):
    return {"allowed": True, "via": "patreon", "tier": "Sub Adult", "skin_creator": True}


async def _acc_streamer(_user):
    return {"allowed": True, "via": "streamer", "tier": None,
            "streamer": True, "skin_creator": True}


async def _acc_apex(_user):
    return {"allowed": True, "via": "patreon", "tier": "Apex", "skin_creator": True}


def glitch_unit_section():
    print("[JU] glitch-grant pure units")
    base = raw_from(POISON_SNAP)
    ok, reason = skin_exact.validate_raw(base)
    check("JU1 authored poison-band raw refused without any grant",
          not ok and reason.startswith("poison"), reason)
    ok, reason = skin_exact.validate_raw(base | {"glitch_grant": True})
    check("JU2 glitch_grant waives the channel sentinel", ok, reason)
    ok, reason = skin_exact.validate_raw(base | {"glitch_grant": True, "pattern": -8})
    check("JU3 pattern -8 stays refused under glitch_grant (owner-only waiver)",
          not ok and reason == "poison_pattern", reason)
    ok, _r = skin_exact.validate_raw(base | {"owner_grant": True, "pattern": -8})
    check("JU4 owner_grant still waives pattern -8", ok, _r)
    check("JU5 is_glitch_grant is literal-True only",
          skin_exact.is_glitch_grant({"glitch_grant": True}) is True
          and not skin_exact.is_glitch_grant({"glitch_grant": "true"})
          and not skin_exact.is_glitch_grant({"glitch_grant": 1})
          and not skin_exact.is_glitch_grant(None))
    big = dict(base) | {"glitch_grant": True}
    big["body"] = [2.0e12, 0.0, 0.0, 1.0]
    ok, reason = skin_exact.validate_raw(big)
    check("JU6 the 1e12 ceiling still refuses under glitch_grant",
          not ok and reason == "range_body", reason)


async def glitch_route_sections():
    print("[J] Glitch Lab routes")
    await reset_state()
    # Authored payloads are NOT worn: the live snapshot is plain in-gamut, so
    # any witness consult would refuse -- proving the grant path never needs it.
    write_snapshot(INGAMUT_SNAP)
    u = await mk_user(PLAYER_SID)
    authored = raw_from(POISON_SNAP)

    async def glitch_apply(user, raw):
        try:
            return 200, await server.glitch_apply(server.GlitchApplyIn(raw=raw), user=user)
        except server.HTTPException as e:
            return e.status_code, e.detail

    server._patreon_access = _acc_sub
    st, out = await glitch_apply(u, authored)
    check("J1 Sub Adult refused -> 403 glitch_tier_insufficient",
          st == 403 and isinstance(out, dict) and out.get("code") == "glitch_tier_insufficient",
          "%s %r" % (st, str(out)[:90]))
    v = await server.glitch_access(user=u)
    check("J2 /glitch-access not allowed for Sub Adult",
          v["allowed"] is False and v["via"] is None, repr(v))

    server._patreon_access = _acc_streamer
    v = await server.glitch_access(user=u)
    check("J2S /glitch-access allows the dedicated Streamer role",
          v["allowed"] is True and v["via"] == "streamer" and v["tier_key"] is None,
          repr(v))
    st, out = await glitch_apply(u, authored)
    check("J2T a pure Streamer authors a past-sentinel payload -> 200",
          st == 200 and out.get("glitch") is True, "%s %r" % (st, str(out)[:90]))
    st, out = await save_preset(u, preset_body(raw=authored, name="glitch streamer"))
    streamer_rows = read_presets_file(PLAYER_SID)
    check("J2U a pure Streamer saves an authored preset with the server stamp",
          st == 200 and bool(streamer_rows)
          and streamer_rows[-1].get("raw", {}).get("glitch_grant") is True,
          "%s %r" % (st, str(streamer_rows)[-120:]))

    server._patreon_access = _acc_apex
    v = await server.glitch_access(user=u)
    check("J3 /glitch-access allows Apex via tier",
          v["allowed"] is True and v["via"] == "tier" and v["tier_key"] == "apex", repr(v))
    st, out = await glitch_apply(u, authored)
    check("J4 Apex authors a past-sentinel payload -> 200",
          st == 200 and out.get("glitch") is True, "%s %r" % (st, str(out)[:90]))
    cmds = read_commands()
    c = cmds[-1] if cmds else {}
    check("J5 command BYTE-EQUAL, no grant keys, sex preserved, no decode",
          all(c.get(k) == [float(x) for x in POISON_SNAP[k]] for k in SLOTS)
          and c.get("pattern") == 2 and c.get("variation") == 8.0
          and "glitch_grant" not in c and "owner_grant" not in c
          and c.get("preserve_female") is True and "color_space" not in c,
          json.dumps({k: c.get(k) for k in ("body",)}))
    rec = stored_recipe(PLAYER_SID)
    check("J6 SkinKeeper recipe kind=glitch (survives relog)",
          rec is not None and rec.get("kind") == "glitch", repr(rec)[:100])
    st, out = await glitch_apply(u, dict(authored) | {"pattern": -8})
    check("J7 authored pattern -8 -> 422 even for Apex", st == 422, "%s %r" % (st, out))
    bad = dict(authored)
    bad["body"] = [2.0e12, 0.0, 0.0, 1.0]
    st, out = await glitch_apply(u, bad)
    check("J8 channel past the 1e12 ceiling -> 422", st == 422, "%s %r" % (st, out))

    st, out = await save_preset(u, preset_body(raw=authored, name="glitch autorada"))
    stored = read_presets_file(PLAYER_SID)
    check("J9 Apex saves an authored (unworn) glitch preset; sidecar stamped glitch_grant",
          st == 200 and bool(stored) and stored[-1].get("raw", {}).get("glitch_grant") is True,
          "%s %r" % (st, str(stored)[-120:]))
    pid = stored[-1]["id"] if stored else None
    server._patreon_access = _access_open  # skin-creator allowed, NOT glitch-entitled
    st, out = await apply_preset(u, pid)
    check("J10 stored grant rides: apply-preset works on the ordinary creator gate",
          st == 200 and out.get("exact") is True, "%s %r" % (st, out))
    rows = read_presets_file(PLAYER_SID)
    for r in rows:
        if r.get("id") == pid:
            r["raw"] = {k: x for k, x in r["raw"].items() if k != "glitch_grant"}
    server._write_presets(PLAYER_SID, rows)
    st, out = await apply_preset(u, pid)
    check("J11 strip the stamp on disk -> 422 again (mutant pin)", st == 422, "%s %r" % (st, out))

    await reset_state()
    write_snapshot(INGAMUT_SNAP)
    u = await mk_user(PLAYER_SID)
    server._patreon_access = _acc_sub
    st, out = await save_preset(u, preset_body(raw=authored))
    check("J12 Sub Adult cannot mint: authored poison sidecar refused",
          st in (409, 422), "%s %r" % (st, out))
    st, out = await save_preset(u, preset_body(raw=dict(authored) | {"glitch_grant": True}))
    check("J13 request body cannot mint glitch_grant (model drops it)",
          st in (409, 422), "%s %r" % (st, out))
    check("J14 nothing stored by either attempt", read_presets_file(PLAYER_SID) == [])

    async def _acc_no(_user):
        return {"allowed": False, "via": None, "tier": None}
    server._patreon_access = _acc_no
    owner_uid = uuid.uuid4().hex
    await db.users.insert_one({"id": owner_uid, "steam_id": "76561199000000777",
                               "email": "o@t", "role": "user", "staff_rank": "owner"})
    ow = await db.users.find_one({"id": owner_uid}, {"_id": 0})
    v = await server.glitch_access(user=ow)
    check("J15 website owner with NO patreon -> allowed via owner",
          v["allowed"] is True and v["via"] == "owner", repr(v))
    admin_uid = uuid.uuid4().hex
    await db.users.insert_one({"id": admin_uid, "steam_id": "76561199000000778",
                               "email": "a@t", "role": "user", "staff_rank": "admin"})
    ad = await db.users.find_one({"id": admin_uid}, {"_id": 0})
    v = await server.glitch_access(user=ad)
    check("J16 staff admin (not owner, no tier) stays refused",
          v["allowed"] is False, repr(v))
    server._patreon_access = _access_open


def main():
    unit_section()
    glitch_unit_section()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(route_sections())
        loop.run_until_complete(glitch_route_sections())
    finally:
        loop.close()
        server._patreon_access = _real_patreon_access
        stop_mongo()
    print("\n%d passed, %d failed" % (PASS, FAIL))
    if _FAILED:
        print("FAILED: %s" % ", ".join(_FAILED))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
