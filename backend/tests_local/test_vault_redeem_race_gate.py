"""Redeem->park race gate for vault.py -- run directly, no pytest.

    <venv>\\python.exe tests_local\\test_vault_redeem_race_gate.py

Scratch SQLite only (game_ipc.BOT_DB_PATH is pointed at a temp file); no mongod
and no game needed. The defect this pins (2026-08-20, row 15175): start_park
reads the pawn from the mod's players.json export, which lags the engine by a
few seconds, so a park pressed right after a redeem captured the throwaway
27.8% beach spawn while the engine applied the real 81.7% / prime / 16-mutation
stego two seconds AFTER the capture. The gate refuses that park with words; it
must NEVER refuse an honest one, and every internal failure must answer None.
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game_ipc  # noqa: E402
import vault  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name if condition else f"{name} :: {detail}")


REDEEMED = {
    "dino_class": "BP_Stegosaurus_C", "growth": 0.816528,
    "mutations": "Hydroregenerative|Enlarged Meniscus|Hypervigilance|Efficient Digestion",
    "parent_mutations": "Gastronomic Regeneration|Photosynthetic Tissue|Nocturnal|Photosynthetic Regeneration",
    "elder_mutations": "Xerocole Adaptation|Congenital Hypoalgesia|Truculency|Osteosclerosis|"
                       "Multichambered Lungs|Epidermal Fibrosis|Tactile Endurance|Cellular Regeneration",
    "is_prime": 1,
}
LAGGING_PAWN = {"dino": "BP_Stegosaurus_C", "growth": 0.278347,
                "mutations": "None|None|None|None", "parent_mutations": "None|None|None|None",
                "elder_mutations": "None|None|None|None|None|None|None|None", "is_prime": 0}
APPLIED_PAWN = dict(REDEEMED, dino="BP_Stegosaurus_C")


def fresh_scratch_db() -> str:
    fd, path = tempfile.mkstemp(prefix="race_gate_", suffix=".db")
    os.close(fd)
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS parked_dinos (id INTEGER PRIMARY KEY, steam_id TEXT)")
    conn.commit()
    conn.close()
    return path


def run_tests() -> None:
    sid = "76500000000000001"

    # -- the incident: fresh memo + lagging pawn -> refusal ---------------------
    vault._note_redeem_for_race_gate(sid, REDEEMED)
    r = vault._redeem_race_refusal(sid, dict(LAGGING_PAWN))
    check("lagging pawn refused", bool(r), repr(r))
    check("refusal speaks to the player", r is not None and "aplicando" in r, repr(r))

    # -- refusal does NOT consume the memo: an instant retry is judged again ----
    r2 = vault._redeem_race_refusal(sid, dict(LAGGING_PAWN))
    check("still refused while pawn lags", bool(r2), repr(r2))

    # -- pawn caught up -> allowed AND memo retired -----------------------------
    r3 = vault._redeem_race_refusal(sid, dict(APPLIED_PAWN))
    check("applied pawn allowed", r3 is None, repr(r3))
    r4 = vault._redeem_race_refusal(sid, dict(LAGGING_PAWN))
    check("memo retired after the match", r4 is None, repr(r4))

    # -- each lag dimension alone refuses ---------------------------------------
    vault._note_redeem_for_race_gate(sid, REDEEMED)
    muts_only = dict(APPLIED_PAWN, mutations="None|None|None|None",
                     parent_mutations="None|None|None|None",
                     elder_mutations="None|None|None|None|None|None|None|None")
    check("mutation lag alone refused", bool(vault._redeem_race_refusal(sid, muts_only)))
    vault._note_redeem_for_race_gate(sid, REDEEMED)
    prime_only = dict(APPLIED_PAWN, is_prime=0)
    check("prime lag alone refused", bool(vault._redeem_race_refusal(sid, prime_only)))
    vault._note_redeem_for_race_gate(sid, REDEEMED)
    growth_only = dict(APPLIED_PAWN, growth=0.5)
    check("growth lag alone refused", bool(vault._redeem_race_refusal(sid, growth_only)))

    # -- growth slack boundary: a pawn within slack of the memo passes ----------
    vault._note_redeem_for_race_gate(sid, dict(REDEEMED, mutations="None|None|None|None",
                                               parent_mutations="None|None|None|None",
                                               elder_mutations="", is_prime=0))
    near = dict(APPLIED_PAWN, growth=0.816528 - vault.REDEEM_RACE_GROWTH_SLACK + 0.001,
                is_prime=0, mutations="None|None|None|None",
                parent_mutations="None|None|None|None", elder_mutations="")
    check("pawn within slack allowed", vault._redeem_race_refusal(sid, near) is None)

    # -- different species than the redeem: honest park, allowed ----------------
    vault._note_redeem_for_race_gate(sid, REDEEMED)
    other = dict(LAGGING_PAWN, dino="BP_Tyrannosaurus_C")
    check("different species allowed", vault._redeem_race_refusal(sid, other) is None)
    check("memo survives a different-species park",
          bool(vault._redeem_race_refusal(sid, dict(LAGGING_PAWN))))

    # -- stale memo self-clears ---------------------------------------------------
    vault._note_redeem_for_race_gate(sid, REDEEMED)
    conn = vault._connect_rw()
    conn.execute("UPDATE redeem_race_memo SET redeemed_at = ? WHERE steam_id = ?",
                 (time.time() - vault.REDEEM_RACE_WINDOW_SECS - 5, sid))
    conn.close()
    check("stale memo allows", vault._redeem_race_refusal(sid, dict(LAGGING_PAWN)) is None)
    check("stale memo was deleted", vault._redeem_race_refusal(sid, dict(LAGGING_PAWN)) is None)

    # -- future-dated memo (clock skew) self-clears ------------------------------
    vault._note_redeem_for_race_gate(sid, REDEEMED)
    conn = vault._connect_rw()
    conn.execute("UPDATE redeem_race_memo SET redeemed_at = ? WHERE steam_id = ?",
                 (time.time() + 9999, sid))
    conn.close()
    check("future-dated memo allows", vault._redeem_race_refusal(sid, dict(LAGGING_PAWN)) is None)

    # -- no memo at all -----------------------------------------------------------
    check("no memo allows", vault._redeem_race_refusal("76599999999999999", dict(LAGGING_PAWN)) is None)

    # -- no table yet: fail-open ---------------------------------------------------
    conn = vault._connect_rw()
    conn.execute("DROP TABLE IF EXISTS redeem_race_memo")
    conn.close()
    check("missing table fails open", vault._redeem_race_refusal(sid, dict(LAGGING_PAWN)) is None)

    # -- vault DB gone entirely: both sides contained -------------------------------
    real_path = game_ipc.BOT_DB_PATH
    game_ipc.BOT_DB_PATH = real_path + ".does_not_exist"
    try:
        check("gate fails open with no DB", vault._redeem_race_refusal(sid, dict(LAGGING_PAWN)) is None)
        try:
            vault._note_redeem_for_race_gate(sid, REDEEMED)
            check("memo write contained with no DB", True)
        except Exception as e:  # noqa: BLE001
            check("memo write contained with no DB", False, repr(e))
    finally:
        game_ipc.BOT_DB_PATH = real_path

    # -- wiring: the gate sits in start_park, the memo in the redeem ok path -------
    check("start_park wires the gate",
          "_redeem_race_refusal(" in inspect.getsource(vault.start_park))
    redeem_src = inspect.getsource(vault)
    ok_at = redeem_src.find("_note_redeem_for_race_gate, steam_id, parked")
    log_at = redeem_src.find('redeem ok sid=')
    check("memo lands before the ok is announced", 0 < ok_at < log_at,
          f"memo@{ok_at} ok@{log_at}")

    # -- helper sanity ---------------------------------------------------------------
    check("mut counter ignores None slots", vault._mut_count("None|None|None|None") == 0)
    check("mut counter counts real slots", vault._mut_count("A|None|B|") == 2)
    check("mut counter survives None input", vault._mut_count(None) == 0)


MUTANTS = []


def mutant_gate_disabled():
    return "gate always allows", {"_redeem_race_refusal": lambda sid, row: None}


def mutant_window_zero():
    return "window collapsed to zero", {"REDEEM_RACE_WINDOW_SECS": 0.0}


def mutant_class_blind():
    real = vault._redeem_race_refusal

    def class_blind(sid, row):
        row = dict(row)
        row["dino"] = "BP_Stegosaurus_C"
        row["dino_class"] = "BP_Stegosaurus_C"
        return real(sid, row)
    return "species check removed", {"_redeem_race_refusal": class_blind}


MUTANTS.extend([mutant_gate_disabled, mutant_window_zero, mutant_class_blind])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", action="store_true")
    args, _ = ap.parse_known_args()

    check("precondition: module under test is the repo copy",
          vault.__file__.replace("\\", "/").endswith("web/backend/vault.py"), vault.__file__)

    real_path = game_ipc.BOT_DB_PATH
    scratch = fresh_scratch_db()
    game_ipc.BOT_DB_PATH = scratch
    try:
        run_tests()
    finally:
        game_ipc.BOT_DB_PATH = real_path

    print(f"\nGATE {len(PASS)}/{len(PASS) + len(FAIL)}")
    for f in FAIL:
        print("  RED  " + f)
    ok = not FAIL

    if args.mutants and ok:
        print("\nMUTATION SENSITIVITY")
        all_red = True
        for factory in MUTANTS:
            label, patches = factory()
            saved = {k: getattr(vault, k) for k in patches}
            PASS.clear()
            FAIL.clear()
            scratch2 = fresh_scratch_db()
            game_ipc.BOT_DB_PATH = scratch2
            for k, v in patches.items():
                setattr(vault, k, v)
            try:
                run_tests()
            except Exception:
                pass  # a mutant that crashes the suite is RED too
            finally:
                for k, v in saved.items():
                    setattr(vault, k, v)
                game_ipc.BOT_DB_PATH = real_path
                try:
                    os.unlink(scratch2)
                except OSError:
                    pass
            red = bool(FAIL)
            print(("  RED  " if red else "  GREEN(BAD) ") + label)
            all_red = all_red and red
        ok = ok and all_red

    try:
        os.unlink(scratch)
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
