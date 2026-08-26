"""
gen0park2 (2026-08-23) -- the parkmark producer in vault.save_parked().

A LIVE park (no recovery_id, no transfer) must enqueue EXACTLY ONE
{"action":"gen0_parkmark","steamid":<digits>,"dino_id":<new row id>} block
AFTER the commit; recovery drains and market transfers must NOT mark; the
mark failing (write refused or module error) must never break the park.

Imports the REAL backend/vault.py against a temp SQLite DB (the marketplace
escrow test's fixture pattern), monkeypatching gen0_infection.write_notify_blocks.

Run: python backend/tests_local/test_gen0_parkmark.py
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game_ipc  # noqa: E402
import gen0_infection  # noqa: E402
import vault  # noqa: E402

_PARKED_COLS = [
    "id", "steam_id", "discord_id", "dino_class", "growth",
    "health", "max_health", "stamina", "max_stamina",
    "hunger", "max_hunger", "thirst", "max_thirst",
    "oxygen", "max_oxygen", "x", "y", "z",
    "is_prime", "is_elder", "mutations", "parent_mutations",
    "elder_mutations", "elder_stacks", "skin_code", "skin_data",
    "diet_a", "diet_b", "diet_c",
    "parked_at", "redeem_pending_cmd_id", "redeem_pending_at",
]


def _make_temp_db() -> str:
    fd, path = tempfile.mkstemp(prefix="lin_gen0_parkmark_", suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    cols_sql = ", ".join(
        "id INTEGER PRIMARY KEY AUTOINCREMENT" if c == "id" else f"{c} TEXT"
        for c in _PARKED_COLS
    )
    conn.execute(f"CREATE TABLE parked_dinos ({cols_sql})")
    conn.commit()
    conn.close()
    return path


PD = {"dino": "BP_Carnotaurus_C", "growth": 0.7, "health": 100, "max_health": 100,
      "stamina": 50, "max_stamina": 50, "hunger": 10, "max_hunger": 20,
      "thirst": 30, "max_thirst": 40, "oxygen": 50, "max_oxygen": 50,
      "x": 1.0, "y": 2.0, "z": 3.0, "mutations": "", "parent_mutations": "",
      "elder_mutations": "", "elder_stacks": 0, "skin_code": "", "skin_data": "",
      "diet_a": 0, "diet_b": 0, "diet_c": 0}

checks, fails = [], []


def chk(name, cond, detail=""):
    checks.append(name)
    if not cond:
        fails.append("%s %s" % (name, detail))


def main():
    db = _make_temp_db()
    game_ipc.BOT_DB_PATH = db
    vault.game_ipc.BOT_DB_PATH = db

    sent = []
    real_write = gen0_infection.write_notify_blocks
    gen0_infection.write_notify_blocks = lambda blocks, path=None: (sent.extend(blocks) or True)
    try:
        # 1. a LIVE park marks once, with the committed row id
        rid = vault.save_parked("76561198000000001", "d1", dict(PD), 0)
        chk("live park inserted", isinstance(rid, int) and rid > 0, rid)
        chk("one parkmark block", len(sent) == 1, sent)
        chk("block carries action+sid+dino_id+growth echo",
            sent and sent[0] == '{"action":"gen0_parkmark","steamid":"76561198000000001","dino_id":%d,"growth_pct":70}' % rid,
            sent)

        # 2. a recovery drain does NOT mark
        sent.clear()
        rid2 = vault.save_parked("76561198000000001", "d1", dict(PD), 0, recovery_id="r" * 16)
        chk("recovery park inserted", isinstance(rid2, int) and rid2 > 0, rid2)
        chk("recovery park does not mark", sent == [], sent)

        # 3. a market transfer does NOT mark
        sent.clear()
        pd3 = dict(PD)
        pd3["steam_id"] = "76561198000000009"   # the SELLER's row = a transfer
        rid3 = vault.save_parked("76561198000000001", "d1", pd3, 0)
        chk("transfer park inserted", isinstance(rid3, int) and rid3 > 0, rid3)
        chk("transfer park does not mark", sent == [], sent)

        # 4. cap refusal inserts nothing and marks nothing
        sent.clear()
        rid4 = vault.save_parked("76561198000000001", "d1", dict(PD), 1)
        chk("cap refusal returns None", rid4 is None, rid4)
        chk("cap refusal does not mark", sent == [], sent)

        # 5. a refused queue write is logged, never raised
        gen0_infection.write_notify_blocks = lambda blocks, path=None: False
        rid5 = vault.save_parked("76561198000000002", "d2", dict(PD), 0)
        chk("park survives a refused mark write", isinstance(rid5, int) and rid5 > 0, rid5)

        # 6. a broken writer (raises) never breaks the park
        def _boom(blocks, path=None):
            raise RuntimeError("queue exploded")
        gen0_infection.write_notify_blocks = _boom
        rid6 = vault.save_parked("76561198000000003", "d3", dict(PD), 0)
        chk("park survives a crashing mark writer", isinstance(rid6, int) and rid6 > 0, rid6)

        # 7. sid folded to digits, bad dino_id refused inside the helper
        gen0_infection.write_notify_blocks = lambda blocks, path=None: (sent.extend(blocks) or True)
        sent.clear()
        vault._gen0_parkmark("sid<76561198000000004>", 77, 0.5)
        chk("sid folded to digits", sent and '"steamid":"76561198000000004"' in sent[0], sent)
        sent.clear()
        vault._gen0_parkmark("76561198000000004", 0, 0.5)
        chk("zero dino_id sends nothing", sent == [], sent)
        sent.clear()
        vault._gen0_parkmark("76561198000000004", 5, 7.5)   # out-of-range growth clamps
        chk("growth echo clamped to 0..100", sent and '"growth_pct":100' in sent[0], sent)
        sent.clear()
        vault._gen0_parkmark("76561198000000004", 5, None)  # absent growth = 0
        chk("absent growth folds to 0", sent and '"growth_pct":0' in sent[0], sent)
    finally:
        gen0_infection.write_notify_blocks = real_write
        try:
            os.remove(db)
        except OSError:
            pass

    print("gen0_parkmark: %d checks, %d failed -> %s" % (
        len(checks), len(fails), "GREEN" if not fails else "RED"))
    for f in fails:
        print("  FAIL " + f)
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
