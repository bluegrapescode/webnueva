# -*- coding: utf-8 -*-
"""Self-executing lane test (repo convention — run directly, NOT pytest):

    py -3.12 backend/tests_local/test_bodydrop_lease_pregate.py

Covers the 2026-07-25 wave "the web answers a Body Drop cooldown locally":
game_ipc.read_feeder_lease, vault's re-implementation of the mod's lease
retention rule, the pre-gate at the top of vault.do_bodydrop, and the
stat-keyed restore_status.json parse cache the ack poll rides on.

I/O layer, not the pure layer: every assertion drives the REAL readers against
REAL files on disk — the lease rows below are copies of LIVE prod rows probed
2026-07-25 — because the entire risk in this change lives at the file boundary:
a torn row, a short row, a missing file, an unchanged mtime.

★ MIXED WEB TREES. The deployed vault.py comes from ghrepo/web/backend and the
deployed game_ipc.py from repo/backend. This test assembles that exact PAIR into
a temp package and imports from there, so it exercises the bytes that ship
together instead of either tree on its own.

★ NEGATIVE CONTROL. Every scenario is replayed against the UNFIXED pair
(vault.py at git HEAD, whose md5 is the deployed 1EB9E030, plus a game_ipc with
no read_feeder_lease). The refusals, the summary field and the parse-count win
must all be ABSENT there — a gate that passes against the unfixed code proves
nothing. The unfixed run also demonstrates the defect directly: it writes a real
game command and burns the ack wait to discover a cooldown the fixed code
answers without touching the game.

No prod contact: nothing outside the temp dir is read or written.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)                        # ghrepo/web/backend
GHREPO = os.path.abspath(os.path.join(BACKEND, "..", ".."))
WEBROOT = os.path.dirname(GHREPO)                      # C:\LaIslaNublarWeb
REPO_BACKEND = os.path.join(WEBROOT, "repo", "backend")

SID = "76561199205873798"          # live prod row, 2026-07-25
SID2 = "76561199533874089"         # live prod row, 2026-07-25
KEY = SID + "|deino_body_drop"
KEY2 = SID2 + "|deino_body_drop"
DINO = "BP_Deinosuchus_C"

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        failures.append(name)
        print(f"FAIL  {name}  {detail}")


# ─────────────────────────────────────────────────────────────────────────────
# child process: runs every scenario against whichever module pair it is given
# ─────────────────────────────────────────────────────────────────────────────
def _child(pkg_dir: str, saved_dir: str, db_path: str) -> dict:
    sys.path.insert(0, pkg_dir)
    import game_ipc
    import vault

    # Point every path at the temp tree BEFORE anything reads them.
    game_ipc.SAVED_DIR = saved_dir
    game_ipc.PLAYERS_JSON = os.path.join(saved_dir, "players.json")
    game_ipc.MOD_ALIVE_JSON = os.path.join(saved_dir, "mod_alive.json")
    game_ipc.COMMANDS_JSON = os.path.join(saved_dir, "commands.json")
    game_ipc.RESTORE_STATUS_JSON = os.path.join(saved_dir, "restore_status.json")
    game_ipc.BOT_DB_PATH = db_path
    lease_path = os.path.join(saved_dir, "cpp_corpse_feeder_lease.txt")
    if hasattr(game_ipc, "CORPSE_FEEDER_LEASE_TXT"):
        game_ipc.CORPSE_FEEDER_LEASE_TXT = lease_path
    # A short ack wait: the unfixed code has to go all the way to the game and
    # time out, and this test is not going to sit there for 25 s to watch it.
    vault.BODYDROP_ACK_TIMEOUT_SECS = 0.5

    out = {}
    now_ms = int(time.time() * 1000)

    def write_lease(*rows):
        with open(lease_path, "w", encoding="utf-8", newline="") as f:
            for r in rows:
                f.write("\t".join(str(c) for c in r) + "\n")

    def drop_lease():
        try:
            os.remove(lease_path)
        except OSError:
            pass

    def lease(sid):
        fn = getattr(game_ipc, "read_feeder_lease", None)
        if fn is None:
            return "NO_READER"
        return fn(sid)

    def cooldown_ms(sid):
        fn = getattr(vault, "bodydrop_cooldown_remaining", None)
        return "NO_ATTR" if fn is None else fn(sid)

    def cooldown_s(sid):
        fn = getattr(vault, "bodydrop_cooldown_secs", None)
        return "NO_ATTR" if fn is None else fn(sid)

    def summary_bodydrop_s():
        """summary()'s published cooldown, or a tagged string on any failure —
        this must never be the thing that breaks the whole vault panel."""
        try:
            return vault.summary(SID, 0, False).get("bodydrop_cooldown_s", "MISSING")
        except Exception as exc:
            return "ERR %s: %s" % (type(exc).__name__, exc)

    def call_bodydrop():
        """(http_status, detail_text) — never raises out of here."""
        try:
            r = vault.do_bodydrop(SID)
            return (200, json.dumps(r, ensure_ascii=False))
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            detail = getattr(exc, "detail", None)
            if status is None:
                return (-1, f"{type(exc).__name__}: {exc}")
            return (int(status), detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False))

    # ── the two PROVEN live rows, replayed with a live 9-minute cooldown ──────
    fed_ts, fed_cd = now_ms - 60_000, now_ms + 540_000
    write_lease(
        (KEY, "lua", "fed", fed_ts, fed_cd, f"web:{SID}:{fed_ts - 2000}"),
        (KEY2, "lua", "fed", now_ms - 30_000, now_ms + 570_000, f"web:{SID2}:{now_ms - 32_000}"),
    )
    out["lease_fed"] = lease(SID)
    out["lease_fed_other"] = lease(SID2)
    out["lease_unknown_sid"] = lease("76561190000000000")
    out["lease_blank_sid"] = lease("")
    out["cooldown_fed_ms"] = cooldown_ms(SID)
    out["cooldown_fed_s"] = cooldown_s(SID)

    # ── containment: every malformed shape must read as "no lease known" ──────
    drop_lease()
    out["lease_missing_file"] = lease(SID)
    out["cooldown_missing_file"] = cooldown_ms(SID)

    write_lease((KEY, "lua", "fed"))                      # torn mid-rewrite
    out["lease_torn_row"] = lease(SID)

    write_lease((KEY, "lua", "fed", "abc", "xyz", "s1"))  # non-numeric stamps
    out["lease_bad_ts"] = lease(SID)

    # Numeric corruption. int(float(x)) raises OverflowError -- NOT ValueError --
    # on these four, so a reader that catches only (TypeError, ValueError) lets
    # the exception escape a function whose docstring promises it never raises.
    for tag, stamp in (("inf", "inf"), ("neg_inf", "-inf"),
                       ("exp", "1e400"), ("longdigits", "9" * 400)):
        write_lease((KEY, "lua", "fed", stamp, stamp, "s1"))
        out[f"lease_overflow_{tag}"] = lease(SID)
        out[f"cooldown_overflow_{tag}"] = cooldown_ms(SID)

    # A corrupt-but-finite cooldown: parses cleanly, so only an upper bound can
    # catch it. Unclamped this refuses the player for ~3 billion years, which is
    # the one path where "I don't know" would mean "refuse" instead of "let the
    # game decide".
    write_lease((KEY, "lua", "fed", now_ms - 1000, 10 ** 20, "s1"))
    out["lease_absurd_cooldown"] = lease(SID)
    out["cooldown_absurd"] = cooldown_ms(SID)
    out["cooldown_absurd_s"] = cooldown_s(SID)
    out["bodydrop_absurd"] = call_bodydrop()
    # ...and the boundary either side of the clamp, so the clamp can never be
    # widened past the mod's own 600 s lease without this failing.
    write_lease((KEY, "lua", "fed", now_ms - 1000, now_ms + 890_000, "s1"))
    out["cooldown_under_clamp"] = cooldown_ms(SID)
    write_lease((KEY, "lua", "fed", now_ms - 1000, now_ms + 910_000, "s1"))
    out["cooldown_over_clamp"] = cooldown_ms(SID)

    write_lease((KEY, "lua", "fed", now_ms - 60_000, now_ms + 540_000, "s1", "legacy_extra"))
    out["lease_extra_column"] = lease(SID)                # 7th column tolerated

    # a SteamID that merely shares a prefix must not answer for another player
    write_lease((SID + "9|deino_body_drop", "lua", "fed", now_ms, now_ms + 540_000, "s1"))
    out["lease_prefix_not_matched"] = lease(SID)

    # the reader must stay cheap and correct when the row is not first
    big = [(f"7656119900000{i:04d}|deino_body_drop", "lua", "fed", now_ms, now_ms + 1000, "s")
           for i in range(2000)]
    big.append((KEY, "lua", "fed", fed_ts, fed_cd, "s_last"))
    t0 = time.monotonic()
    write_lease(*big)
    out["lease_big_file"] = lease(SID)
    out["lease_big_file_ms"] = round((time.monotonic() - t0) * 1000, 1)

    # unreadable path (a directory where the file should be) -> OSError -> None
    drop_lease()
    os.makedirs(lease_path, exist_ok=True)
    out["lease_unreadable"] = lease(SID)
    os.rmdir(lease_path)

    # ── the mod's OWN retention rule, replayed on real files ──────────────────
    write_lease((KEY, "lua", "fed", now_ms - 700_000, now_ms - 100_000, "s1"))
    out["cooldown_fed_expired"] = cooldown_ms(SID)

    write_lease((KEY, "lua", "pending", now_ms - 5_000, now_ms + 595_000, "s1"))
    out["cooldown_pending_fresh"] = cooldown_ms(SID)

    write_lease((KEY, "lua", "pending", now_ms - 31_000, now_ms + 569_000, "s1"))
    out["cooldown_pending_stale"] = cooldown_ms(SID)      # past the 30 s TTL

    write_lease((KEY, "lua", "pending", now_ms + 60_000, now_ms + 660_000, "s1"))
    out["cooldown_pending_future_ts"] = cooldown_ms(SID)  # clock skew

    write_lease((KEY, "lua", "pending", now_ms - 5_000, 0, "s1"))
    out["cooldown_pending_no_cd"] = cooldown_ms(SID)

    # ── do_bodydrop: a genuinely online, genuinely eligible carnivore ─────────
    def write_players(dino=DINO, online=True):
        stamp = int(time.time() * 1000)
        row = {
            "actor_name": dino + "_2147471852", "dino": dino,
            "growth": 0.31, "hunger": 4.0, "max_hunger": 40.0,
            "health": 100.0, "max_health": 100.0, "last_updated": stamp,
        }
        body = {"last_updated": stamp} if online else {"last_updated": stamp - 3_600_000}
        if online:
            body[SID] = row
        with open(game_ipc.PLAYERS_JSON, "w", encoding="utf-8") as f:
            json.dump(body, f)

    write_players()
    try:
        os.remove(game_ipc.COMMANDS_JSON)
    except OSError:
        pass

    write_lease((KEY, "lua", "fed", fed_ts, fed_cd, "s1"))
    out["bodydrop_cooldown"] = call_bodydrop()

    write_lease((KEY, "lua", "pending", int(time.time() * 1000) - 3_000,
                 int(time.time() * 1000) + 597_000, "s1"))
    out["bodydrop_pending"] = call_bodydrop()

    # ★ the greyed button and the refusal copy must name the SAME minute.
    # 240_500 ms left is exactly where rounding raw ms and rounding the
    # epsilon-adjusted value part company (5 min vs 4 min).
    skew_ms = 240_500
    now2 = int(time.time() * 1000)
    write_lease((KEY, "lua", "fed", now2 - (600_000 - skew_ms), now2 + skew_ms, "s1"))
    write_players()
    out["skew_button_secs"] = cooldown_s(SID)
    out["skew_refusal"] = call_bodydrop()

    # ★ the 2 s epsilon: a lease this close to release must go to the GAME.
    write_lease((KEY, "lua", "fed", int(time.time() * 1000) - 598_500,
                 int(time.time() * 1000) + 1_500, "s1"))
    write_players()
    out["bodydrop_inside_epsilon"] = call_bodydrop()

    # ★ ORDERING: the cooldown refusal sits AFTER the online / carnivore gates,
    # so a player who could never body drop is told WHY instead of being told to
    # come back in 8 minutes for something they can never have.
    write_lease((KEY, "lua", "fed", fed_ts, fed_cd, "s1"))
    write_players(dino="BP_Stegosaurus_C")
    out["bodydrop_herbivore_on_cooldown"] = call_bodydrop()
    out["summary_herbivore_cooldown_s"] = summary_bodydrop_s()

    write_players(online=False)
    out["bodydrop_offline_on_cooldown"] = call_bodydrop()
    out["summary_offline_cooldown_s"] = summary_bodydrop_s()

    # ★ LANE: the automatic feeder shares this lease. A player it fed never
    # asked for anything, so the copy must not tell them to wait before asking
    # "again". Behaviour is identical either way -- only the wording differs.
    write_players()
    write_lease((KEY, "lua", "fed", fed_ts, fed_cd, "lua:%s:%d" % (SID, fed_ts)))
    out["bodydrop_auto_fed"] = call_bodydrop()
    write_lease((KEY, "lua", "fed", fed_ts, fed_cd, "web:%s:%d" % (SID, fed_ts)))
    out["bodydrop_self_asked"] = call_bodydrop()

    drop_lease()
    write_players()
    out["bodydrop_no_lease"] = call_bodydrop()

    # An unreadable lease file must cost a round trip, never a wrong refusal.
    os.makedirs(lease_path, exist_ok=True)
    write_players()
    out["bodydrop_unreadable_lease"] = call_bodydrop()
    os.rmdir(lease_path)

    # Every command that reached commands.json is a round trip the fix was
    # supposed to avoid. The fixed pair must have written exactly the ones the
    # epsilon / no-lease / unreadable cases deliberately let through.
    try:
        with open(game_ipc.COMMANDS_JSON, "r", encoding="utf-8") as f:
            cmds = json.load(f)
    except (OSError, ValueError):
        cmds = []
    out["commands_written"] = len([c for c in cmds if c.get("type") == "body_drop"])

    # ── summary payload field (2c) ───────────────────────────────────────────
    write_lease((KEY, "lua", "fed", fed_ts, fed_cd, "s1"))
    try:
        summ = vault.summary(SID, 0, False)
        out["summary_has_field"] = "bodydrop_cooldown_s" in summ
        out["summary_value"] = summ.get("bodydrop_cooldown_s")
        out["summary_slay_field"] = summ.get("slay_cooldown_s")
    except Exception as exc:
        out["summary_has_field"] = f"ERR {type(exc).__name__}: {exc}"

    # ── restore_status.json parse cache (1c) ─────────────────────────────────
    cmd_a, cmd_b = "aaaa1111", "bbbb2222"

    def write_restore(entries):
        with open(game_ipc.RESTORE_STATUS_JSON, "w", encoding="utf-8") as f:
            json.dump({"entries": entries}, f)
        # mtime_ns must actually move between rewrites for any stat-keyed cache
        # to see the change; the ring file is rewritten far slower than this.
        time.sleep(0.02)

    write_restore([
        {"steamid": SID, "cmd_id": cmd_a, "event": "body_drop_ok", "corpse_class": DINO},
        {"steamid": SID2, "cmd_id": "zzzz", "event": "body_drop_ok"},
    ])

    real_read = game_ipc.read_json_file
    calls = {"n": 0}

    def counting(path):
        if path == game_ipc.RESTORE_STATUS_JSON:
            calls["n"] += 1
        return real_read(path)

    game_ipc.read_json_file = counting
    try:
        hit = None
        for _ in range(200):
            hit = game_ipc.read_restore_status(SID, None, "body_drop_ok", None, cmd_a)
        out["restore_found"] = bool(hit) and hit.get("cmd_id") == cmd_a
        out["restore_parses_200_polls"] = calls["n"]

        # cmd_id present but the steamid does not match -> no false ack
        out["restore_wrong_sid"] = game_ipc.read_restore_status("76561190000000000", None,
                                                                "body_drop_ok", None, cmd_a)
        # a real rewrite must be picked up
        write_restore([
            {"steamid": SID, "cmd_id": cmd_a, "event": "body_drop_ok"},
            {"steamid": SID, "cmd_id": cmd_b, "event": "body_drop_failed",
             "fail_reason": "body_drop_cooldown"},
        ])
        got = game_ipc.read_restore_status(SID, None, "body_drop_failed", None, cmd_b)
        out["restore_invalidates"] = bool(got) and got.get("fail_reason") == "body_drop_cooldown"
        out["restore_parses_after_change"] = calls["n"]

        # torn/garbage rewrite mid-poll must not blank an in-flight ack
        with open(game_ipc.RESTORE_STATUS_JSON, "w", encoding="utf-8") as f:
            f.write('{"entries": [{"steamid": "7656119')
        time.sleep(0.02)
        still = game_ipc.read_restore_status(SID, None, "body_drop_failed", None, cmd_b)
        out["restore_torn_fails_open"] = bool(still)
    finally:
        game_ipc.read_json_file = real_read

    return out


# ─────────────────────────────────────────────────────────────────────────────
# parent
# ─────────────────────────────────────────────────────────────────────────────
def _make_db(path):
    import sqlite3
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
             parked_at TEXT, redeem_pending_cmd_id TEXT, redeem_pending_at TEXT)"""
    )
    conn.commit()
    conn.close()


def _build_pkg(dst, vault_src, game_ipc_src):
    os.makedirs(dst, exist_ok=True)
    shutil.copyfile(vault_src, os.path.join(dst, "vault.py"))
    shutil.copyfile(game_ipc_src, os.path.join(dst, "game_ipc.py"))
    shutil.copyfile(os.path.join(BACKEND, "mutation_catalog.py"),
                    os.path.join(dst, "mutation_catalog.py"))


def _run_variant(tmp, name, vault_src, game_ipc_src):
    pkg = os.path.join(tmp, name)
    saved = os.path.join(tmp, name + "_saved")
    db = os.path.join(tmp, name + ".db")
    os.makedirs(saved, exist_ok=True)
    _build_pkg(pkg, vault_src, game_ipc_src)
    _make_db(db)
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--child", pkg, saved, db],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    for line in (proc.stdout or "").splitlines():
        if line.startswith("RESULT_JSON "):
            return json.loads(line[len("RESULT_JSON "):])
    raise SystemExit(f"child '{name}' produced no result\n"
                     f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")


def main():
    tmp = tempfile.mkdtemp(prefix="lin_bodydrop_lease_")
    try:
        unfixed_vault = os.path.join(tmp, "_head_vault.py")
        rc = subprocess.run(["git", "-C", GHREPO, "show", "HEAD:web/backend/vault.py"],
                            capture_output=True)
        if rc.returncode != 0:
            raise SystemExit("cannot read the unfixed vault.py from git HEAD — "
                             "the negative control cannot run: "
                             + rc.stderr.decode("utf-8", "replace"))
        with open(unfixed_vault, "wb") as f:
            f.write(rc.stdout)

        # game_ipc must come from HEAD too, NOT from the ghrepo working tree.
        # The lease reader now lives in BOTH web trees (the GitHub deploy lane
        # ships ghrepo's copy), so reading the working tree here would quietly
        # hand the control a FIXED file and the negative control would stop
        # controlling anything.
        unfixed_gipc = os.path.join(tmp, "_head_game_ipc.py")
        rc = subprocess.run(["git", "-C", GHREPO, "show", "HEAD:web/backend/game_ipc.py"],
                            capture_output=True)
        if rc.returncode != 0:
            raise SystemExit("cannot read the unfixed game_ipc.py from git HEAD — "
                             "the negative control cannot run: "
                             + rc.stderr.decode("utf-8", "replace"))
        with open(unfixed_gipc, "wb") as f:
            f.write(rc.stdout)

        print("[fixed pair: ghrepo vault.py + repo game_ipc.py]")
        fx = _run_variant(tmp, "fixed",
                          os.path.join(BACKEND, "vault.py"),
                          os.path.join(REPO_BACKEND, "game_ipc.py"))

        # ── reader ───────────────────────────────────────────────────────────
        row = fx["lease_fed"]
        check("lease row parses", isinstance(row, dict), repr(row))
        if isinstance(row, dict):
            check("lease owner", row.get("owner") == "lua", repr(row.get("owner")))
            check("lease state", row.get("state") == "fed", repr(row.get("state")))
            check("lease key", row.get("key") == KEY, repr(row.get("key")))
            check("lease ts is epoch ms int",
                  isinstance(row.get("ts_ms"), int) and row["ts_ms"] > 1_700_000_000_000,
                  repr(row.get("ts_ms")))
            check("lease cooldown is 600 s after ts",
                  row.get("cooldown_until_ms", 0) - row.get("ts_ms", 0) == 600_000,
                  repr(row))
            check("lease spawn_id kept", str(row.get("spawn_id", "")).startswith("web:"),
                  repr(row.get("spawn_id")))
        check("second live row parses independently",
              isinstance(fx["lease_fed_other"], dict)
              and fx["lease_fed_other"].get("key") == KEY2, repr(fx["lease_fed_other"]))
        check("unknown sid -> None", fx["lease_unknown_sid"] is None, repr(fx["lease_unknown_sid"]))
        check("blank sid -> None", fx["lease_blank_sid"] is None, repr(fx["lease_blank_sid"]))

        # ── containment (fail OPEN on every bad path) ────────────────────────
        for k, label in (("lease_missing_file", "missing file"),
                         ("lease_torn_row", "torn row"),
                         ("lease_bad_ts", "non-numeric stamps"),
                         ("lease_prefix_not_matched", "prefix-only key"),
                         ("lease_unreadable", "unreadable path")):
            check(f"fails open: {label} -> None", fx[k] is None, repr(fx[k]))
        check("missing lease -> cooldown 0", fx["cooldown_missing_file"] == 0,
              repr(fx["cooldown_missing_file"]))
        # OverflowError containment: the reader must return None, not raise, and
        # the caller must read that as "free", not as a refusal.
        for tag in ("inf", "neg_inf", "exp", "longdigits"):
            check(f"fails open: overflow stamp {tag} -> None",
                  fx[f"lease_overflow_{tag}"] is None, repr(fx[f"lease_overflow_{tag}"]))
            check(f"fails open: overflow stamp {tag} -> cooldown 0",
                  fx[f"cooldown_overflow_{tag}"] == 0, repr(fx[f"cooldown_overflow_{tag}"]))
        # A finite-but-absurd cooldown must ALLOW the request through, never
        # refuse it: this is the fail-open rule's sharpest edge.
        check("absurd cooldown parses (only the clamp can catch it)",
              isinstance(fx["lease_absurd_cooldown"], dict), repr(fx["lease_absurd_cooldown"]))
        check("absurd cooldown -> free, not a refusal", fx["cooldown_absurd"] == 0,
              repr(fx["cooldown_absurd"]))
        check("absurd cooldown -> button not greyed", fx["cooldown_absurd_s"] == 0,
              repr(fx["cooldown_absurd_s"]))
        check("absurd cooldown -> not a 429", fx["bodydrop_absurd"][0] != 429,
              repr(fx["bodydrop_absurd"]))
        check("clamp boundary: 890 s still refuses",
              isinstance(fx["cooldown_under_clamp"], int) and fx["cooldown_under_clamp"] > 0,
              repr(fx["cooldown_under_clamp"]))
        check("clamp boundary: 910 s is treated as corrupt -> free",
              fx["cooldown_over_clamp"] == 0, repr(fx["cooldown_over_clamp"]))
        check("legacy 7th column tolerated",
              isinstance(fx["lease_extra_column"], dict)
              and fx["lease_extra_column"].get("spawn_id") == "s1",
              repr(fx["lease_extra_column"]))
        check("2001-row file still resolves",
              isinstance(fx["lease_big_file"], dict)
              and fx["lease_big_file"].get("spawn_id") == "s_last",
              repr(fx["lease_big_file"]))

        # ── retention rule == the mod's ──────────────────────────────────────
        ms = fx["cooldown_fed_ms"]
        check("fed lease reports ms left", isinstance(ms, int) and 530_000 < ms <= 540_000, repr(ms))
        check("fed lease seconds field", isinstance(fx["cooldown_fed_s"], int)
              and 530 <= fx["cooldown_fed_s"] <= 540, repr(fx["cooldown_fed_s"]))
        check("expired fed lease -> free", fx["cooldown_fed_expired"] == 0,
              repr(fx["cooldown_fed_expired"]))
        check("fresh pending -> PENDING signal", fx["cooldown_pending_fresh"] == -1,
              repr(fx["cooldown_pending_fresh"]))
        check("pending past 30 s TTL -> free (mod would have dropped it)",
              fx["cooldown_pending_stale"] == 0, repr(fx["cooldown_pending_stale"]))
        check("pending stamped in the future -> free",
              fx["cooldown_pending_future_ts"] == 0, repr(fx["cooldown_pending_future_ts"]))
        check("pending with no cooldown -> free",
              fx["cooldown_pending_no_cd"] == 0, repr(fx["cooldown_pending_no_cd"]))

        # ── the pre-gate itself ──────────────────────────────────────────────
        st, detail = fx["bodydrop_cooldown"]
        check("live cooldown -> 429", st == 429, f"{st} {detail!r}")
        check("429 copy names the wait", any(u in str(detail) for u in (" min", " s"))
              and any(ch.isdigit() for ch in str(detail)), repr(detail))
        check("429 copy is Spanish", "Espera" in str(detail), repr(detail))
        st, detail = fx["bodydrop_pending"]
        check("pending drop -> 409", st == 409, f"{st} {detail!r}")
        bsecs, (st, detail) = fx["skew_button_secs"], fx["skew_refusal"]
        check("rounding-skew case still refuses", st == 429, f"{st} {detail!r}")
        check("greyed button and refusal copy name the same minute",
              isinstance(bsecs, int) and f"Espera {-(-bsecs // 60)} min" in str(detail),
              f"button {bsecs}s -> {-(-bsecs // 60) if isinstance(bsecs, int) else '?'} min "
              f"vs copy {detail!r}")
        st, detail = fx["bodydrop_inside_epsilon"]
        check("inside the 2 s epsilon the web does NOT refuse", st not in (429, 409),
              f"{st} {detail!r}")
        st, detail = fx["bodydrop_no_lease"]
        check("no lease -> not refused locally", st not in (429, 409), f"{st} {detail!r}")
        st, detail = fx["bodydrop_unreadable_lease"]
        check("unreadable lease -> not refused locally", st not in (429, 409),
              f"{st} {detail!r}")
        check("the 2 local refusals wrote no game command", fx["commands_written"] == 3,
              f"{fx['commands_written']} body_drop commands (expected exactly the 3 "
              f"deliberate fall-throughs — epsilon, no lease, unreadable lease — "
              f"and nothing from the 429 or the 409)")

        # ── summary field ────────────────────────────────────────────────────
        # ── ordering: who gets told WHAT, and in which order ─────────────────
        hst, hdetail = fx["bodydrop_herbivore_on_cooldown"]
        check("herbivore on cooldown is told it is a herbivore, not to wait",
              hst != 429 and "carn" in str(hdetail).lower(), f"{hst} {hdetail!r}")
        ost, odetail = fx["bodydrop_offline_on_cooldown"]
        check("offline player on cooldown is told they are offline, not to wait",
              ost != 429 and "partida" in str(odetail), f"{ost} {odetail!r}")
        # ...and neither of them pays for a lease read they can do nothing with.
        check("summary skips the lease read for a herbivore",
              fx["summary_herbivore_cooldown_s"] == 0,
              repr(fx["summary_herbivore_cooldown_s"]))
        check("summary skips the lease read for an offline player",
              fx["summary_offline_cooldown_s"] == 0,
              repr(fx["summary_offline_cooldown_s"]))

        # ── lane-aware copy: same refusal, honest wording ────────────────────
        ast_, adetail = fx["bodydrop_auto_fed"]
        wst, wdetail = fx["bodydrop_self_asked"]
        check("auto-fed player still refused with 429", ast_ == 429, f"{ast_} {adetail!r}")
        check("auto-fed copy does not blame the player for asking again",
              "volver a pedir" not in str(adetail), repr(adetail))
        check("auto-fed copy says the server fed them",
              "autom" in str(adetail).lower(), repr(adetail))
        check("auto-fed copy still names the wait",
              any(u in str(adetail) for u in (" min", " s")), repr(adetail))
        check("self-asked player refused with the asking-again copy",
              wst == 429 and "volver a pedir" in str(wdetail), f"{wst} {wdetail!r}")
        check("the two lanes differ in copy only, never in verdict", ast_ == wst,
              f"{ast_} vs {wst}")

        check("summary exposes bodydrop_cooldown_s", fx["summary_has_field"] is True,
              repr(fx["summary_has_field"]))
        check("summary field shape matches slay_cooldown_s (int seconds)",
              isinstance(fx["summary_value"], int)
              and type(fx["summary_value"]) is type(fx["summary_slay_field"]),
              f"{fx['summary_value']!r} vs slay {fx['summary_slay_field']!r}")
        check("summary greys the button while refused", fx["summary_value"] > 0,
              repr(fx["summary_value"]))

        # ── restore_status parse cache ───────────────────────────────────────
        check("ack still found through the cache", fx["restore_found"] is True,
              repr(fx["restore_found"]))
        check("200 ack polls parse the file once", fx["restore_parses_200_polls"] == 1,
              f"{fx['restore_parses_200_polls']} parses")
        check("cmd_id index does not cross SteamIDs", fx["restore_wrong_sid"] is None,
              repr(fx["restore_wrong_sid"]))
        check("a real rewrite invalidates the cache", fx["restore_invalidates"] is True,
              repr(fx["restore_invalidates"]))
        check("rewrite costs exactly one more parse",
              fx["restore_parses_after_change"] == 2, repr(fx["restore_parses_after_change"]))
        check("torn rewrite keeps serving the last good snapshot",
              fx["restore_torn_fails_open"] is True, repr(fx["restore_torn_fails_open"]))

        # ── NEGATIVE CONTROL ────────────────────────────────────────────────
        print("\n[negative control: UNFIXED pair (vault.py at git HEAD == deployed 1EB9E030)]")
        nx = _run_variant(tmp, "unfixed", unfixed_vault, unfixed_gipc)
        check("NEG: unfixed game_ipc has no lease reader",
              nx["lease_fed"] == "NO_READER", repr(nx["lease_fed"]))
        check("NEG: unfixed vault has no cooldown accessor",
              nx["cooldown_fed_ms"] == "NO_ATTR", repr(nx["cooldown_fed_ms"]))
        st, detail = nx["bodydrop_cooldown"]
        check("NEG: unfixed does NOT refuse a live cooldown locally", st != 429,
              f"{st} {detail!r}")
        check("NEG: unfixed pays the round trip and times out instead", st == 504,
              f"{st} {detail!r}")
        st, _ = nx["bodydrop_pending"]
        check("NEG: unfixed does NOT answer a pending drop locally", st != 409, str(st))
        check("NEG: unfixed writes a game command for every refusal",
              nx["commands_written"] > fx["commands_written"],
              f"unfixed {nx['commands_written']} vs fixed {fx['commands_written']}")
        check("NEG: unfixed summary has no bodydrop_cooldown_s",
              nx["summary_has_field"] is False, repr(nx["summary_has_field"]))
        check("NEG: unfixed re-parses restore_status on every poll",
              nx["restore_parses_200_polls"] == 200,
              f"{nx['restore_parses_200_polls']} parses")
        check("NEG: unfixed blanks an in-flight ack on a torn rewrite",
              nx["restore_torn_fails_open"] is False, repr(nx["restore_torn_fails_open"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        print("RESULT_JSON " + json.dumps(_child(sys.argv[2], sys.argv[3], sys.argv[4]),
                                          ensure_ascii=False))
    else:
        main()
