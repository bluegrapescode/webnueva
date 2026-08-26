"""Self-executing lane test (repo convention — run directly, NOT pytest):

    python tests_local/test_vault_prime_route_capture.py

DELTA on commit 112908d. That wave shipped the three prime mission-state columns, the
migration, the read and the redeem send, and its bitmask half works — parked rows now
carry a real `prime_conditions`. Its ROUTE half never fired: `_prime_state_from_payload`
looked the values up under the COLUMN names only, while the mod publishes the two route
counters in players.json as `l_mig` / `l_pat`. Probed live 2026-07-29:

    players.json:   l_mig / l_pat            present in 39 of 39 rows
                    prime_route_mig / _pat   present in  0 of 39 rows
    parked_dinos:   prime_conditions  NULL=568 zero=0 nonzero=2
                    prime_route_mig   NULL=570 zero=0 nonzero=0
                    prime_route_pat   NULL=570 zero=0 nonzero=0
                    bitmask recorded AND route recorded: 0

Fix ported from Arkadia (l_mig/l_pat at park, column names at redeem, primary-then-
fallback reader). Section 0 pins the donor text so a later edit that drifts from it
turns this suite red.

Drives the REAL writers against a REAL sqlite. Nothing contacts prod.
"""
import contextlib
import io
import os
import re
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        failures.append(name)
        print(f"FAIL  {name}  {detail}")


DONOR_DINO = r"C:\Arkadia\dino.py"
DONOR_DB = r"C:\Arkadia\database.py"
SHIPPED_LUA = r"C:\ServerStaging\lin_strikekick_20260729\main.full.WAVE.lua"


def _make_db(path):
    """parked_dinos as prod has it AFTER commit 112908d's migration."""
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
             parked_at TEXT, redeem_pending_cmd_id TEXT, redeem_pending_at TEXT,
             custom_name TEXT,
             prime_conditions INTEGER, prime_route_mig INTEGER, prime_route_pat INTEGER)"""
    )
    conn.commit()
    conn.close()


def main():
    tmp = tempfile.mkdtemp(prefix="lin_prime_route_")
    db_path = os.path.join(tmp, "test.db")
    _make_db(db_path)

    import game_ipc
    game_ipc.BOT_DB_PATH = db_path
    import vault
    import asyncio

    PATCHED = hasattr(vault, "_PRIME_STATE_SOURCE_ALIASES")
    print("mode: %s" % ("PATCHED" if PATCHED else "NEGATIVE CONTROL (112908d as deployed)"))

    @contextlib.contextmanager
    def patched(**attrs):
        targets = {k: (vault if hasattr(vault, k) and not hasattr(game_ipc, k) else game_ipc)
                   for k in attrs}
        saved = {k: getattr(targets[k], k) for k in attrs}
        for k, v in attrs.items():
            setattr(targets[k], k, v)
        try:
            yield
        finally:
            for k, v in saved.items():
                setattr(targets[k], k, v)

    SID = "76561190000000042"
    vault.ensure_prime_state_columns()

    # ── 0. the baseline this delta assumes, and the donor it copies ──────────
    check("baseline carries commit 112908d's helper", hasattr(vault, "_prime_state_from_payload"))
    check("baseline carries its column tuple",
          getattr(vault, "_PRIME_STATE_COLS", None)
          == ("prime_conditions", "prime_route_mig", "prime_route_pat"))
    try:
        donor_dino = io.open(DONOR_DINO, encoding="utf-8").read()
        donor_db = io.open(DONOR_DB, encoding="utf-8").read()
    except OSError:
        donor_dino = donor_db = None
    if donor_dino is None:
        check("Arkadia donor readable (cannot prove this is a port without it)", False, DONOR_DINO)
    else:
        check("donor still reads primary-then-fallback (dino.py _safelog_prime_route)",
              'value = row.get(primary)' in donor_dino
              and 'if value in (None, ""):' in donor_dino
              and 'value = row.get(fallback)' in donor_dino)
        check("donor still captures the players.json spelling at park (database.py)",
              '_prime_route_value(player_data, "l_mig", 2),' in donor_db
              and '_prime_route_value(player_data, "l_pat", 4),' in donor_db)
        check("donor sends the COLUMN spelling at redeem (dino.py)",
              '_prime_route_value(parked, "prime_route_mig", 2)' in donor_dino
              and '_prime_route_value(parked, "prime_route_pat", 4)' in donor_dino)
    if PATCHED:
        check("LIN's alias map is exactly the donor's two mappings",
              vault._PRIME_STATE_SOURCE_ALIASES
              == {"prime_route_mig": "l_mig", "prime_route_pat": "l_pat"},
              repr(getattr(vault, "_PRIME_STATE_SOURCE_ALIASES", None)))

    # ── 1. the mod publishes l_mig / l_pat, never the column spelling ────────
    try:
        lua = io.open(SHIPPED_LUA, encoding="utf-8", errors="replace").read()
    except OSError:
        lua = None
    if lua is None:
        check("shipped lua readable", False, SHIPPED_LUA)
    else:
        check('shipped mod publishes "l_mig" in players.json', '"l_mig": ' in lua)
        check('shipped mod publishes "l_pat" in players.json', '"l_pat": ' in lua)
        check("shipped mod NEVER publishes the column spelling — this is the whole bug",
              '"prime_route_mig": ' not in lua and '"prime_route_pat": ' not in lua)
        check("shipped mod DOES parse the column spelling off the restore command",
              "prime_route_mig  = tonumber(raw:match(" in lua)

    # ── 2. a REAL players.json park row (the live shape) ─────────────────────
    # Copy of D4rkPhantom's row 1438 park, plus the keys players.json really carries.
    park_row = {"dino": "BP_Tyrannosaurus_C", "growth": 0.775253,
                "health": 10748.7, "max_health": 10748.7,
                "stamina": 728.6, "max_stamina": 728.6,
                "hunger": 1104.0, "max_hunger": 2594.0,
                "thirst": 778.1, "max_thirst": 1000.0,
                "x": -111869.0, "y": 62799.0, "z": 26065.0,
                "is_prime": 1, "is_elder": 1, "elder_stacks": 1,
                "mutations": "Enhanced Digestion|Hypermetabolic Inanition",
                "parent_mutations": "", "elder_mutations": "",
                "skin_code": "", "skin_data": "",
                "diet_a": 130.2, "diet_b": 242.2, "diet_c": 0.0,
                "prime_conditions": 245, "l_mig": 2, "l_pat": 4}

    pid = vault.save_parked(SID, "d1", park_row, cap=0)
    prow = vault.get_parked_by_id(pid)
    check("bitmask was already being captured before this delta (112908d works)",
          prow["prime_conditions"] == 245, repr(prow.get("prime_conditions")))
    if PATCHED:
        check("THE FIX: l_mig is captured into prime_route_mig",
              prow["prime_route_mig"] == 2, repr(prow.get("prime_route_mig")))
        check("THE FIX: l_pat is captured into prime_route_pat",
              prow["prime_route_pat"] == 4, repr(prow.get("prime_route_pat")))
    else:
        check("NEG CONTROL: route counters are NULL — reproduces the live 0-of-570",
              prow["prime_route_mig"] is None and prow["prime_route_pat"] is None,
              repr((prow.get("prime_route_mig"), prow.get("prime_route_pat"))))

    # ── 2b. the park log IS the post-deploy oracle, so assert it fires ───────
    # Without this the whole lane can silently stop capturing again and the only
    # way to notice would be opening the database — which is how the route half
    # stayed at 0 of 570 rows unnoticed in the first place.
    if PATCHED:
        import logging

        class _Grab(logging.Handler):
            def __init__(self):
                super().__init__()
                self.lines = []

            def emit(self, record):
                try:
                    self.lines.append(record.getMessage())
                except Exception:
                    pass

        grab = _Grab()
        vlog = logging.getLogger("laislanublar.vault")
        vlog.addHandler(grab)
        prev_level, prev_prop = vlog.level, vlog.propagate
        vlog.setLevel(logging.INFO)
        try:
            lid = vault.save_parked(SID, "d1", park_row, cap=0)
        finally:
            vlog.removeHandler(grab)
            vlog.setLevel(prev_level)
            vlog.propagate = prev_prop
        park_lines = [l for l in grab.lines if "park prime-state" in l]
        check("park logs exactly one prime-state line", len(park_lines) == 1, repr(grab.lines[-4:]))
        if park_lines:
            check("the park log names all three columns and their captured values",
                  all(f"{c}=" in park_lines[0] for c in vault._PRIME_STATE_COLS)
                  and "prime_conditions=245" in park_lines[0]
                  and "prime_route_mig=2" in park_lines[0]
                  and "prime_route_pat=4" in park_lines[0],
                  repr(park_lines[0]))
        # a payload that carries nothing must still log, saying "absent"
        grab2 = _Grab()
        vlog.addHandler(grab2)
        vlog.setLevel(logging.INFO)
        try:
            bare = dict(park_row)
            for k in ("prime_conditions", "l_mig", "l_pat"):
                del bare[k]
            vault.save_parked(SID, "d1", bare, cap=0)
        finally:
            vlog.removeHandler(grab2)
            vlog.setLevel(prev_level)
        bare_lines = [l for l in grab2.lines if "park prime-state" in l]
        check("a park that captured NOTHING still logs, and says absent",
              len(bare_lines) == 1 and bare_lines[0].count("absent") == 3,
              repr(bare_lines))

    # ── 3. the replay lanes still round-trip (column spelling stays PRIMARY) ─
    replay = dict(park_row)
    del replay["l_mig"], replay["l_pat"]
    replay["prime_route_mig"], replay["prime_route_pat"] = 1, 3
    rid = vault.save_parked(SID, "d1", replay, cap=0)
    rrow = vault.get_parked_by_id(rid)
    check("stored-row replay (market/recovery/store/inventory) still captured",
          rrow["prime_route_mig"] == 1 and rrow["prime_route_pat"] == 3,
          repr((rrow.get("prime_route_mig"), rrow.get("prime_route_pat"))))
    if PATCHED:
        both = dict(park_row)
        both["prime_route_mig"], both["prime_route_pat"] = 1, 3
        brow = vault.get_parked_by_id(vault.save_parked(SID, "d1", both, cap=0))
        check("when BOTH spellings are present the stored column wins (donor order)",
              brow["prime_route_mig"] == 1 and brow["prime_route_pat"] == 3,
              repr((brow.get("prime_route_mig"), brow.get("prime_route_pat"))))
        blank = dict(park_row)
        blank["prime_route_mig"], blank["prime_route_pat"] = "", ""
        krow = vault.get_parked_by_id(vault.save_parked(SID, "d1", blank, cap=0))
        check("an EMPTY stored value falls through to the players.json key (donor rule)",
              krow["prime_route_mig"] == 2 and krow["prime_route_pat"] == 4,
              repr((krow.get("prime_route_mig"), krow.get("prime_route_pat"))))

    # ── 4. NULL still means "never recorded" — the contract 112908d set ──────
    unknown = dict(park_row)
    for k in ("prime_conditions", "l_mig", "l_pat"):
        del unknown[k]
    urow = vault.get_parked_by_id(vault.save_parked(SID, "d1", unknown, cap=0))
    check("a payload carrying neither spelling still leaves all three NULL",
          urow["prime_conditions"] is None and urow["prime_route_mig"] is None
          and urow["prime_route_pat"] is None,
          repr({c: urow[c] for c in vault._PRIME_STATE_COLS}))
    zero = dict(park_row, prime_conditions=0, l_mig=0, l_pat=0)
    zrow = vault.get_parked_by_id(vault.save_parked(SID, "d1", zero, cap=0))
    check("an explicit zero is still recorded as 0, NOT collapsed to NULL",
          zrow["prime_conditions"] == 0 and zrow["prime_route_mig"] == 0
          and zrow["prime_route_pat"] == 0,
          repr({c: zrow[c] for c in vault._PRIME_STATE_COLS}))

    # ── 5. clamps and hostile input (112908d's, unchanged by this delta) ─────
    if PATCHED:
        for mig, pat, want in ((99, 99, (2, 4)), (-5, -5, (0, 0)), (2.9, 4.9, (2, 4)),
                               (float("inf"), float("inf"), (2, 4)),
                               (float("-inf"), float("-inf"), (0, 0))):
            r = vault.get_parked_by_id(vault.save_parked(
                SID, "d1", dict(park_row, l_mig=mig, l_pat=pat), cap=0))
            check(f"l_mig={mig!r} l_pat={pat!r} -> {want}",
                  (r["prime_route_mig"], r["prime_route_pat"]) == want,
                  repr((r["prime_route_mig"], r["prime_route_pat"])))
        for bad in ("junk", float("nan"), [], {}, True):
            r = vault.get_parked_by_id(vault.save_parked(
                SID, "d1", dict(park_row, l_mig=bad, l_pat=bad), cap=0))
            check(f"junk l_mig={bad!r} leaves the column NULL, never raises",
                  r["prime_route_mig"] is None, repr(r["prime_route_mig"]))

    # ── 6. redeem now carries the routes end to end, through start_redeem ────
    if PATCHED:
        captured = {}
        pending = []
        with patched(_schedule=lambda coro: pending.append(coro),
                     read_player=lambda sid, force_fresh=False: {"dino": "BP_Tyrannosaurus_C"},
                     redeem_gate_failures=lambda row, parked: [],
                     redeem_cooldown_remaining=lambda sid: 0,
                     write_game_command=lambda cmd: (captured.update(cmd) or False)):
            res = vault.start_redeem(SID, int(pid))
            check("start_redeem scheduled the job", bool(res.get("job_id")), repr(res))
            for coro in pending:
                asyncio.run(coro)
        check("E2E: the restore command carries prime_conditions",
              captured.get("prime_conditions") == 245, repr(sorted(captured)))
        check("E2E: the restore command carries BOTH route counters",
              captured.get("prime_route_mig") == 2 and captured.get("prime_route_pat") == 4,
              repr({k: v for k, v in captured.items() if k.startswith("prime_")}))
        check("nothing else was added to the wire",
              set(captured) - {"prime_conditions", "prime_route_mig", "prime_route_pat"}
              >= {"type", "steamid", "growth", "is_prime", "is_elder", "mutations"})

    print()
    total = len(failures)
    print(f"{'FAILED' if total else 'PASSED'}: {total} failure(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
