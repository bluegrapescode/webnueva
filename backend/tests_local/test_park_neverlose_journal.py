"""Self-executing lane test (repo convention — run directly, NOT pytest):

    python tests_local/test_park_neverlose_journal.py

Covers the 2026-07-30 park never-lose wave (CI/IDRP port):
  * recovery_id schema upgrade (idempotent, index, readiness gate)
  * pre-kill journal append: stable content-hash identity, fail-closed ""
  * _run_park outcomes: kill-never-sent prunes; mod-refused kill prunes;
    ack timeout KEEPS the line + honest "unknown" job; kill via verified ack
    and via the health<=0 fallback both store + stamp recovery_id + prune;
    vault-full-at-save and save-crash both UPGRADE to a post-kill line with
    an "unknown your-dino-is-safe" job; a crash during the ack wait keeps
    the line (kill_issued, not confirmed)
  * drain: post-kill restores with the ORIGINAL parked_at + recovery_id and
    prunes; replay is a no-op (idempotent by recovery_id); pre-kill without
    death evidence is left; pre-kill WITH a real death_causes.log record of
    the same class in-window restores; wrong-class evidence does not count;
    bad JSON is left; vault-full leaves the line and a freed slot restores it
    on the next sweep; a same-class direct retry park nearby leaves the line;
    unmigrated DB (no recovery_id column) refuses to promote (fail-closed);
    prune is BY ID so a line appended mid-sweep survives
  * save_parked BEGIN EXCLUSIVE retry ladder wins against a 2s writer lock

Uses a throwaway sqlite DB + tmp journal/death-log; no game/prod contact.
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        failures.append(name)
        print(f"FAIL  {name}  {detail}")


SCHEMA = """CREATE TABLE parked_dinos (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     steam_id TEXT, discord_id TEXT, dino_class TEXT, growth REAL,
     health REAL, max_health REAL, stamina REAL, max_stamina REAL,
     hunger REAL, max_hunger REAL, thirst REAL, max_thirst REAL,
     oxygen REAL, max_oxygen REAL, x REAL, y REAL, z REAL,
     is_prime INTEGER, is_elder INTEGER, mutations TEXT,
     parent_mutations TEXT, elder_mutations TEXT, elder_stacks INTEGER,
     skin_code TEXT, skin_data TEXT, diet_a REAL, diet_b REAL, diet_c REAL,
     parked_at TEXT, redeem_pending_cmd_id TEXT, redeem_pending_at TEXT)"""

SID = "76561190000000001"
SNAP = {
    "steam_id": SID, "dino": "BP_Tyrannosaurus_C", "growth": 0.85,
    "health": 9000.0, "max_health": 9000.0, "stamina": 900.0, "max_stamina": 900.0,
    "hunger": 2000.0, "max_hunger": 2500.0, "thirst": 800.0, "max_thirst": 900.0,
    "oxygen": 100.0, "max_oxygen": 100.0, "x": 1.0, "y": 2.0, "z": 3.0,
    "is_prime": False, "is_elder": False, "mutations": "", "parent_mutations": "",
    "elder_mutations": "", "elder_stacks": 0, "skin_code": "", "skin_data": "",
    "diet_a": 1.0, "diet_b": 2.0, "diet_c": 3.0, "actor_name": "BP_Tyrannosaurus_C_1",
}


def fresh_db(path):
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    conn.commit()
    conn.close()


def journal_lines(vault):
    p = vault._park_unsaved_path()
    if not os.path.isfile(p):
        return []
    with open(p, "r", encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def rows(db_path, sid=SID):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM parked_dinos WHERE steam_id = ? ORDER BY id", (sid,))]
    finally:
        conn.close()


class IpcStub:
    """Scenario-programmable stand-ins for the three game_ipc reads _run_park uses."""
    def __init__(self):
        self.write_ok = True
        self.kill_ok_ack = None     # dict or None
        self.kill_failed_ack = None
        self.player = None          # players.json row or None
        self.write_calls = 0

    def write_game_command(self, cmd):
        self.write_calls += 1
        return self.write_ok

    def read_restore_status(self, sid, _a, event, _actor, _cmd):
        if event == "kill_ok":
            return self.kill_ok_ack
        if event == "kill_failed":
            return self.kill_failed_ack
        return None

    def read_restore_matches(self, sid, event, actor, cmd_id):
        if event != "kill_ok" or not self.kill_ok_ack:
            return []
        return [dict(self.kill_ok_ack)]

    def read_player(self, sid, force_fresh=False):
        return self.player

    def clear_swap_persist(self, sid):
        return True


def run_park(vault, stub, cap=10, rid=None):
    """Drive the REAL _run_park with the stubbed IPC. Returns (job, rid)."""
    import game_ipc
    game_ipc.write_game_command = stub.write_game_command
    game_ipc.read_restore_matches = stub.read_restore_matches
    game_ipc.read_restore_status = stub.read_restore_status
    game_ipc.read_player = stub.read_player
    game_ipc.clear_swap_persist = stub.clear_swap_persist
    if rid is None:
        rid = vault.append_unsaved_park(SID, "", SNAP, cap, vault._PARK_PREKILL_REASON)
    jid = vault._new_job("park", SID)
    asyncio.run(vault._run_park(jid, SID, "", dict(SNAP), SNAP["actor_name"],
                                "cmd" + os.urandom(4).hex(), cap, None, rid))
    return vault.get_job(jid), rid


def main():
    tmp = tempfile.mkdtemp(prefix="lin_park_neverlose_")
    db_path = os.path.join(tmp, "test.db")
    saved_dir = os.path.join(tmp, "Saved")
    os.makedirs(saved_dir, exist_ok=True)
    fresh_db(db_path)

    import game_ipc
    game_ipc.BOT_DB_PATH = db_path
    game_ipc.DATA_DIR = tmp
    game_ipc.SAVED_DIR = saved_dir
    import vault
    vault.PARK_ACK_TIMEOUT_SECS = 0.6  # keep the timeout scenarios fast
    gen0_resets = []

    async def _fake_gen0_reset(sid, reason):
        gen0_resets.append((sid, reason))
        return True

    vault._reset_gen0_after_dino_switch = _fake_gen0_reset

    # ── schema upgrade ────────────────────────────────────────────────────────
    check("recovery_id column added", vault.ensure_recovery_id_column() is True)
    check("recovery_id idempotent", vault.ensure_recovery_id_column() is True)
    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(parked_dinos)")]
    idx = [r[1] for r in conn.execute("PRAGMA index_list(parked_dinos)")]
    conn.close()
    check("column present", "recovery_id" in cols, cols)
    check("index present", any("idx_parked_recovery_id" in i for i in idx), idx)

    # ── journal append ────────────────────────────────────────────────────────
    rid1 = vault.append_unsaved_park(SID, "d1", SNAP, 10, vault._PARK_PREKILL_REASON)
    check("append returns rid", len(rid1) == 64, rid1)
    lines = journal_lines(vault)
    check("journal has the line", len(lines) == 1 and lines[0]["recovery_id"] == rid1)
    check("rid is stable on re-read", vault._queued_park_recovery_id(lines[0]) == rid1)
    vault._journal_prune({rid1}, "test cleanup")
    check("prune removes it", journal_lines(vault) == [])

    # append failure path -> "" (unwritable dir)
    real_dir = game_ipc.DATA_DIR
    game_ipc.DATA_DIR = os.path.join(tmp, "no_such_dir", "deeper")
    rid_bad = vault.append_unsaved_park(SID, "", SNAP, 10, vault._PARK_PREKILL_REASON)
    check("append fail-closed returns empty", rid_bad == "")
    game_ipc.DATA_DIR = real_dir

    # ── _run_park scenarios ──────────────────────────────────────────────────
    # a) kill order never sent -> failed + pruned
    stub = IpcStub(); stub.write_ok = False
    job, rid = run_park(vault, stub)
    check("no-send: job failed", job["state"] == "failed", job)
    check("no-send: journal pruned", journal_lines(vault) == [])
    check("no-send: no row", rows(db_path) == [])
    check("no-send: no GEN-0 reset", gen0_resets == [])

    # b) mod refuses the kill -> failed + pruned
    stub = IpcStub(); stub.kill_failed_ack = {"event": "kill_failed"}
    job, rid = run_park(vault, stub)
    check("refused: job failed", job["state"] == "failed", job)
    check("refused: journal pruned", journal_lines(vault) == [])
    check("refused: no GEN-0 reset", gen0_resets == [])

    # c) ack timeout -> job unknown, line KEPT (the 07-29/30 loss shape)
    stub = IpcStub()  # no acks, no player row
    job, rid = run_park(vault, stub)
    check("timeout: job unknown", job["state"] == "unknown", job)
    check("timeout: honest message", "autom" in (job["message"] or ""), job)
    check("timeout: NOT the old lie", "no se guardó nada." != (job["message"] or "").strip(), job)
    kept = journal_lines(vault)
    check("timeout: journal line kept", len(kept) == 1 and kept[0]["recovery_id"] == rid)
    check("timeout: no row yet", rows(db_path) == [])
    check("timeout: no GEN-0 reset", gen0_resets == [])
    vault._journal_prune({rid}, "test cleanup")

    # d) verified ack -> stored + stamped + pruned
    stub = IpcStub(); stub.kill_ok_ack = {"event": "kill_ok", "kill_verified": True}
    job, rid = run_park(vault, stub)
    r = rows(db_path)
    check("ack kill: job ok", job["state"] == "ok", job)
    check("ack kill: row stored", len(r) == 1 and r[0]["dino_class"] == "BP_Tyrannosaurus_C")
    check("ack kill: recovery_id stamped", r[0]["recovery_id"] == rid, r[0].get("recovery_id"))
    check("ack kill: journal pruned", journal_lines(vault) == [])
    check("ack kill: GEN-0 reset once",
          gen0_resets == [(SID, "park_confirmed")], gen0_resets)
    fresh_db(db_path); vault._RECOVERY_ID_READY = False; vault.ensure_recovery_id_column()

    # e) health<=0 fallback -> stored
    stub = IpcStub(); stub.player = {"steam_id": SID, "health": 0.0, "last_seen": time.time()}
    def _online(_row):
        return True
    real_online = vault._is_online; vault._is_online = _online
    job, rid = run_park(vault, stub)
    vault._is_online = real_online
    check("fallback kill: job ok", job["state"] == "ok", job)
    check("fallback kill: row stored", len(rows(db_path)) == 1)
    fresh_db(db_path); vault._RECOVERY_ID_READY = False; vault.ensure_recovery_id_column()

    # f) vault full at save -> upgraded post-kill line + unknown "safe" job
    stub = IpcStub(); stub.kill_ok_ack = {"event": "kill_ok", "kill_verified": True}
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO parked_dinos (steam_id, dino_class, parked_at) VALUES (?, 'BP_Gallimimus_C', '2026-01-01T00:00:00+00:00')", (SID,))
    conn.commit(); conn.close()
    job, rid = run_park(vault, stub, cap=1)
    kept = journal_lines(vault)
    check("cap: job unknown-safe", job["state"] == "unknown" and "a salvo" in job["message"], job)
    check("cap: upgraded to post-kill", len(kept) == 1
          and kept[0]["reason"] == "web_post_kill_vault_full"
          and kept[0]["recovery_id"] != rid, kept)
    check("cap: no rex row", all(x["dino_class"] != "BP_Tyrannosaurus_C" for x in rows(db_path)))
    # g) freed slot -> drain restores it (post-kill needs no evidence)
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM parked_dinos WHERE dino_class='BP_Gallimimus_C'")
    conn.commit(); conn.close()
    summary = vault.drain_park_unsaved_once()
    r = rows(db_path)
    check("drain: restored after slot freed", summary["restored"] == 1, summary)
    check("drain: original parked_at kept", len(r) == 1
          and r[0]["parked_at"] == kept[0]["queued_at"], r)
    check("drain: recovery_id stamped", r[0]["recovery_id"] == kept[0]["recovery_id"])
    check("drain: journal now empty", journal_lines(vault) == [])
    # h) replay is a no-op: re-append the SAME line and drain again
    with open(vault._park_unsaved_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({k: v for k, v in kept[0].items()},
                            ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = vault.drain_park_unsaved_once()
    check("drain replay: skipped as done", summary["restored"] == 0 and summary["left"] == 0, summary)
    check("drain replay: still one row", len(rows(db_path)) == 1)
    check("drain replay: line pruned", journal_lines(vault) == [])
    fresh_db(db_path); vault._RECOVERY_ID_READY = False; vault.ensure_recovery_id_column()

    # i) save crash after confirmed kill -> upgraded line + unknown job
    stub = IpcStub(); stub.kill_ok_ack = {"event": "kill_ok", "kill_verified": True}
    real_save = vault.save_parked
    def boom(*a, **k):
        raise sqlite3.OperationalError("database is locked (test)")
    vault.save_parked = boom
    job, rid = run_park(vault, stub)
    vault.save_parked = real_save
    kept = journal_lines(vault)
    check("crash: job unknown-safe", job["state"] == "unknown" and "a salvo" in job["message"], job)
    check("crash: upgraded post-kill line", len(kept) == 1
          and kept[0]["reason"] == "web_post_kill_save_error", kept)
    summary = vault.drain_park_unsaved_once()
    check("crash: drain restores it", summary["restored"] == 1 and len(rows(db_path)) == 1, summary)
    fresh_db(db_path); vault._RECOVERY_ID_READY = False; vault.ensure_recovery_id_column()

    # j) crash DURING the ack wait -> kill issued, line kept, job unknown
    stub = IpcStub()
    def ack_boom(*a, **k):
        raise RuntimeError("restore_status unreadable (test)")
    import game_ipc as gi
    gi.read_restore_matches = ack_boom
    gi.read_restore_status = ack_boom
    rid = vault.append_unsaved_park(SID, "", SNAP, 10, vault._PARK_PREKILL_REASON)
    gi.write_game_command = stub.write_game_command
    gi.read_player = stub.read_player
    gi.clear_swap_persist = stub.clear_swap_persist
    jid = vault._new_job("park", SID)
    asyncio.run(vault._run_park(jid, SID, "", dict(SNAP), SNAP["actor_name"], "cmdx", 10, None, rid))
    job = vault.get_job(jid)
    check("midwait crash: job unknown", job["state"] == "unknown", job)
    check("midwait crash: line kept", len(journal_lines(vault)) == 1)
    vault._journal_prune({rid}, "test cleanup")

    # ── drain evidence gates (pre-kill lines) ─────────────────────────────────
    # k) pre-kill line, NO death evidence -> left
    rid = vault.append_unsaved_park(SID, "", SNAP, 10, vault._PARK_PREKILL_REASON)
    summary = vault.drain_park_unsaved_once()
    check("prekill no-proof: left", summary["left"] == 1 and summary["restored"] == 0, summary)
    check("prekill no-proof: no row", rows(db_path) == [])
    # l) wrong-class death evidence -> still left
    qat = vault._iso_to_epoch(journal_lines(vault)[0]["queued_at"])
    with open(os.path.join(saved_dir, "death_causes.log"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": qat + 10, "sid": SID, "dino": "BP_Gallimimus_C",
                             "growth": 0.5, "cause": "unknown"}) + "\n")
    summary = vault.drain_park_unsaved_once()
    check("prekill wrong-class: left", summary["left"] == 1 and summary["restored"] == 0, summary)
    # m) same-class in-window death -> restored
    with open(os.path.join(saved_dir, "death_causes.log"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": qat + 12, "sid": SID, "dino": "BP_Tyrannosaurus_C",
                             "growth": 0.85, "cause": "unknown"}) + "\n")
    summary = vault.drain_park_unsaved_once()
    r = rows(db_path)
    check("prekill with proof: restored", summary["restored"] == 1 and len(r) == 1, summary)
    check("prekill with proof: journal empty", journal_lines(vault) == [])
    fresh_db(db_path); vault._RECOVERY_ID_READY = False; vault.ensure_recovery_id_column()
    os.remove(os.path.join(saved_dir, "death_causes.log"))

    # n) direct retry park nearby -> line left (dupe guard)
    rid = vault.append_unsaved_park(SID, "", SNAP, 10, "web_post_kill_db_busy")
    qat = journal_lines(vault)[0]["queued_at"]
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO parked_dinos (steam_id, dino_class, parked_at) VALUES (?, 'BP_Tyrannosaurus_C', ?)",
                 (SID, qat))
    conn.commit(); conn.close()
    summary = vault.drain_park_unsaved_once()
    check("retry-nearby: left", summary["left"] == 1 and summary["restored"] == 0, summary)
    check("retry-nearby: still one row", len(rows(db_path)) == 1)
    fresh_db(db_path); vault._RECOVERY_ID_READY = False; vault.ensure_recovery_id_column()
    vault._journal_prune({rid}, "test cleanup")

    # o) bad JSON is kept
    with open(vault._park_unsaved_path(), "w", encoding="utf-8") as fh:
        fh.write("{this is not json\n")
    summary = vault.drain_park_unsaved_once()
    check("bad json: left in place", summary["left"] == 1, summary)
    with open(vault._park_unsaved_path(), "r", encoding="utf-8") as fh:
        check("bad json: file intact", "{this is not json" in fh.read())
    os.remove(vault._park_unsaved_path())

    # p) unmigrated DB -> identity unreadable -> fail-closed left
    fresh_db(db_path)  # no recovery_id column
    vault._RECOVERY_ID_READY = False
    rid = vault.append_unsaved_park(SID, "", SNAP, 10, "web_post_kill_db_busy")
    summary = vault.drain_park_unsaved_once()
    check("unmigrated: left, never promoted", summary["left"] == 1 and summary["restored"] == 0, summary)
    check("unmigrated: no row", rows(db_path) == [])
    vault._journal_prune({rid}, "test cleanup")
    vault.ensure_recovery_id_column()

    # q) prune is BY ID: a line appended between read and prune survives
    ridA = vault.append_unsaved_park(SID, "", SNAP, 10, "web_post_kill_db_busy")
    ridB = vault.append_unsaved_park(SID, "", dict(SNAP, growth=0.5), 10, vault._PARK_PREKILL_REASON)
    removed = vault._journal_prune({ridA}, "test")
    kept = journal_lines(vault)
    check("prune by id: only target removed", removed == 1 and len(kept) == 1
          and kept[0]["recovery_id"] == ridB, kept)
    vault._journal_prune({ridB}, "test cleanup")

    # ── save_parked retry ladder ──────────────────────────────────────────────
    # The holder thread owns its OWN connection (sqlite objects are
    # thread-bound), takes EXCLUSIVE, holds it 2s, then releases.
    lock_taken = threading.Event()
    def hold_lock():
        h = sqlite3.connect(db_path, timeout=1.0, isolation_level=None)
        h.execute("BEGIN EXCLUSIVE")
        lock_taken.set()
        time.sleep(2.0)
        h.execute("ROLLBACK")
        h.close()
    t = threading.Thread(target=hold_lock)
    t.start()
    lock_taken.wait(5.0)
    t0 = time.time()
    new_id = vault.save_parked(SID, "", SNAP, 10, recovery_id="ridretry" + "0" * 56)
    took = time.time() - t0
    t.join()
    check("retry ladder: wins after lock frees", isinstance(new_id, int) and took >= 1.0,
          f"new_id={new_id} took={took:.1f}s")
    fresh_db(db_path); vault._RECOVERY_ID_READY = False; vault.ensure_recovery_id_column()

    # ── start_park: journal is fail-CLOSED (no journal, no kill) ─────────────
    stub = IpcStub()
    game_ipc.write_game_command = stub.write_game_command
    game_ipc.read_player = lambda sid, force_fresh=False: dict(SNAP)
    game_ipc.read_skin_snapshot = lambda actor: None
    game_ipc.read_diet_snapshot = lambda actor: None
    real_gate = vault.park_gate_failures
    real_pending = vault._steam_has_fresh_redeem_pending
    vault.park_gate_failures = lambda row: []
    vault._steam_has_fresh_redeem_pending = lambda sid: False
    from fastapi import HTTPException

    game_ipc.DATA_DIR = os.path.join(tmp, "no_such_dir", "deeper")  # unwritable
    got = None
    try:
        vault.start_park(SID, "", 10)
    except HTTPException as exc:
        got = exc
    check("start_park fail-closed: 503", got is not None and got.status_code == 503, got)
    check("start_park fail-closed: kill never sent", stub.write_calls == 0)
    game_ipc.DATA_DIR = tmp

    # The 2-minute park wait (owner rule 2026-07-31) is stamped by any earlier
    # completed park in this lane; clear it so the journal cases below test the
    # journal, then prove the wait itself refuses BEFORE any kill is written.
    def clear_park_wait():
        try:
            os.remove(vault._park_cooldowns_path())
        except OSError:
            pass

    clear_park_wait()
    vault.record_park(SID)
    calls_before = stub.write_calls
    got = None
    try:
        vault.start_park(SID, "", 10)
    except HTTPException as exc:
        got = exc
    check("park wait: refuses inside the window (429)",
          got is not None and got.status_code == 429, got)
    check("park wait: no kill written while waiting", stub.write_calls == calls_before)
    vault._release_action(("Park", SID))
    clear_park_wait()

    out = vault.start_park(SID, "", 10)
    kept = journal_lines(vault)
    check("start_park: returns job", isinstance(out, dict) and out.get("job_id"))
    check("start_park: pre-kill line on disk", len(kept) == 1
          and kept[0]["reason"] == vault._PARK_PREKILL_REASON, kept)
    vault._journal_prune({kept[0]["recovery_id"]}, "test cleanup")
    vault._release_action(("Park", SID))
    vault.park_gate_failures = real_gate
    vault._steam_has_fresh_redeem_pending = real_pending

    # ── kill switch: LIN_PARK_JOURNAL=0 restores the old behaviour ────────────
    os.environ["LIN_PARK_JOURNAL"] = "0"
    try:
        check("flag off: journal disabled", vault._park_journal_enabled() is False)
        stub = IpcStub()  # timeout scenario
        job, rid = run_park(vault, stub, rid="")
        check("flag off: timeout keeps OLD failed state", job["state"] == "failed", job)
        check("flag off: timeout keeps OLD wording",
              "a tiempo" in job["message"] and "nada" in job["message"], job)
        check("flag off: no journal line written", journal_lines(vault) == [])
        check("flag off: drain is a no-op", vault.drain_park_unsaved_once() ==
              {"scanned": 0, "restored": 0, "left": 0})
    finally:
        os.environ.pop("LIN_PARK_JOURNAL", None)

    print()
    if failures:
        print(f"{len(failures)} FAILURES: {failures}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
