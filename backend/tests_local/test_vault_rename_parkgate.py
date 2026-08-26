"""Self-executing lane test (repo convention — run directly, NOT pytest):

    python tests_local/test_vault_rename_parkgate.py

Covers the 2026-07-18 wave:
  * parked_dinos.custom_name schema upgrade (idempotent, readiness-gated reads)
  * rename_owned ownership + sanitization + clear
  * save_parked carries custom_name through a market-style delivery payload
  * park gate: health requirement is 100% with float tolerance (a full bar
    that reads 0.9999997 must pass; 99% must fail and name the real value)
  * _dino_view exposes custom_name

Uses a throwaway sqlite DB; no game/prod contact.
"""
import os
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


def main():
    tmp = tempfile.mkdtemp(prefix="lin_vault_test_")
    db_path = os.path.join(tmp, "test.db")

    import sqlite3
    conn = sqlite3.connect(db_path)
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

    import game_ipc
    game_ipc.BOT_DB_PATH = db_path
    import vault

    # ── schema upgrade ────────────────────────────────────────────────────────
    check("ensure adds column", vault.ensure_custom_name_column() is True)
    check("ensure idempotent", vault.ensure_custom_name_column() is True)

    # ── sanitize ──────────────────────────────────────────────────────────────
    check("clean collapses spaces", vault.clean_custom_name("  Rex   del  Norte ") == "Rex del Norte")
    check("clean strips control chars", vault.clean_custom_name("Rex\x00\x07del\nNorte") == "Rexdel Norte")
    check("clean clamps 32", len(vault.clean_custom_name("x" * 99)) == 32)
    check("clean empty", vault.clean_custom_name("   ") == "")

    # ── rename + ownership ────────────────────────────────────────────────────
    pd = {"dino": "BP_Tyrannosaurus_C", "growth": 1.0, "health": 5000, "max_health": 5000,
          "stamina": 900, "max_stamina": 900, "hunger": 800, "max_hunger": 1000,
          "mutations": "Titan|None|Feral", "parent_mutations": "None|None",
          "elder_mutations": "", "elder_stacks": 0, "skin_code": "", "skin_data": "",
          "diet_a": 100, "diet_b": 100, "diet_c": 100}
    rid = vault.save_parked("76561190000000001", "d1", pd, cap=0)
    check("save_parked returns id", isinstance(rid, int))
    check("rename own row", vault.rename_owned(rid, "76561190000000001", "Furia") == 1)
    check("rename foreign row refused", vault.rename_owned(rid, "76561190000000002", "Robo") == 0)
    row = vault.get_parked_by_id(rid)
    check("stored name", row.get("custom_name") == "Furia", repr(row.get("custom_name")))
    view = vault._dino_view(row)
    check("view carries custom_name", view.get("custom_name") == "Furia")
    check("rename clear", vault.rename_owned(rid, "76561190000000001", "") == 1)
    check("cleared name -> None in view",
          vault._dino_view(vault.get_parked_by_id(rid)).get("custom_name") is None)

    # ── market-style delivery carries the name ───────────────────────────────
    vault.rename_owned(rid, "76561190000000001", "Furia")
    payload = dict(vault.get_parked_by_id(rid))  # what a listing snapshots
    buyer_row_id = vault.save_parked("76561190000000002", "d2", payload, cap=0)
    check("delivered row keeps name",
          vault.get_parked_by_id(buyer_row_id).get("custom_name") == "Furia")

    # ── park gate: 100% health ───────────────────────────────────────────────
    def live_row(hp_frac, growth=1.0):
        import time as _t
        return {"actor_name": "A1", "dino": "BP_Tyrannosaurus_C", "growth": growth,
                "health": 5000.0 * hp_frac, "max_health": 5000.0,
                "stamina": 900.0, "max_stamina": 900.0,
                "hunger": 800.0, "max_hunger": 1000.0,
                "last_updated": _t.time()}

    check("park min health is 1.0", abs(vault.PARK_MIN_HEALTH_PCT - 1.0) < 1e-9,
          repr(vault.PARK_MIN_HEALTH_PCT))
    full = vault.park_gate_failures(live_row(1.0))
    check("full health passes", not any("Salud" in f for f in full), repr(full))
    nearly = vault.park_gate_failures(live_row(0.9999997))
    check("float-noise full bar passes", not any("Salud" in f for f in nearly), repr(nearly))
    hurt = vault.park_gate_failures(live_row(0.99))
    named = [f for f in hurt if "Salud" in f]
    check("99% fails", bool(named), repr(hurt))
    check("failure names value and 100%", named and "99.0" in named[0] and "100%" in named[0],
          repr(named))

    # ── park gate: 25% growth floor (owner rule 2026-07-23, was 75%) ──────────
    check("park min growth is 0.25", abs(vault.PARK_MIN_GROWTH - 0.25) < 1e-9,
          repr(vault.PARK_MIN_GROWTH))
    at_floor = vault.park_gate_failures(live_row(1.0, growth=0.25))
    check("juvenile at 25% growth passes", not any("Crecimiento" in f for f in at_floor),
          repr(at_floor))
    below = vault.park_gate_failures(live_row(1.0, growth=0.24))
    gnamed = [f for f in below if "Crecimiento" in f]
    check("24% growth fails", bool(gnamed), repr(below))
    check("growth failure names value and 25%",
          bool(gnamed) and "24%" in gnamed[0] and "25%" in gnamed[0], repr(gnamed))
    hatch = vault.park_gate_failures(live_row(1.0, growth=0.10))
    check("hatchling (10%) still blocked", any("Crecimiento" in f for f in hatch), repr(hatch))

    # ── a low-growth park stores + redeems without a growth block ─────────────
    low_pd = {"dino": "BP_Tyrannosaurus_C", "growth": 0.25, "health": 5000, "max_health": 5000,
              "stamina": 900, "max_stamina": 900, "hunger": 1000, "max_hunger": 1000,
              "thirst": 500, "max_thirst": 500, "oxygen": 0, "max_oxygen": 0,
              "mutations": "", "parent_mutations": "", "elder_mutations": "", "elder_stacks": 0,
              "skin_code": "", "skin_data": "", "diet_a": 100, "diet_b": 100, "diet_c": 100}
    low_id = vault.save_parked("76561190000000009", "d9", low_pd, cap=0)
    stored = vault.get_parked_by_id(low_id)
    check("25% growth stored verbatim (no clamp)", abs(float(stored["growth"]) - 0.25) < 1e-9,
          repr(stored.get("growth")))
    # redeem gate must NOT block on the parked dino's low growth (it gates the
    # LIVE dino's health/stamina/hunger + species match, never growth).
    rfails = vault.redeem_gate_failures(live_row(1.0), stored)
    check("redeem not blocked by low parked growth",
          not any("recimiento" in f for f in rfails), repr(rfails))

    # ── the restore command writes the saved growth back VERBATIM ─────────────
    # Drive the real redeem writer (_run_redeem) with a captured write_game_command
    # that returns False, so it builds+writes the restore cmd then exits before the
    # in-game verify loop (no game/loop contact). Proves the low growth reaches the
    # mod unchanged — the value the mod's growth_ok ack then confirms in-game.
    import asyncio as _asyncio
    captured = {}
    _orig_write = game_ipc.write_game_command
    game_ipc.write_game_command = lambda cmd: (captured.update(cmd) or False)
    try:
        jid = vault._new_job("redeem", "76561190000000009")
        _asyncio.run(vault._run_redeem(jid, "76561190000000009", int(low_id), dict(stored), "cmdtest01"))
    finally:
        game_ipc.write_game_command = _orig_write
    check("restore cmd is a restore", captured.get("type") == "restore", repr(captured.get("type")))
    check("restore cmd carries growth 0.25 verbatim",
          captured.get("growth") is not None and abs(float(captured["growth"]) - 0.25) < 1e-9,
          repr(captured.get("growth")))
    check("restore cmd targets the parked species",
          captured.get("expected_species") == "BP_Tyrannosaurus_C", repr(captured.get("expected_species")))

    # ── staff feed builders (pure) ───────────────────────────────────────────
    import staff_feed
    e = staff_feed.build_grant_embed("StaffX", "StaffX", "vip", 50000, "prueba", True)
    check("self-grant flagged", "Auto-concesión" in e["title"] and "Amberium" in e["description"])
    check("self-grant red", e["color"] == staff_feed._COLOR_SELF_GRANT)
    e2 = staff_feed.build_grant_embed("StaffX", "PlayerY", "normal", 1234567, "premio", False)
    check("grant formats amount", "1.234.567" in e2["description"], e2["description"])
    check("grant names both", "StaffX" in e2["description"] and "PlayerY" in e2["description"])
    e3 = staff_feed.build_code_created_embed("StaffX", "VERANO24", {"coins": 5000, "spins": 3}, 100, 1, True)
    check("code embed", "VERANO24" in e3["description"] and any(
        f["value"].startswith("5.000") and "3 giros bonus" in f["value"]
        for f in e3["fields"] if f["name"] == "Recompensa"))

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    main()
