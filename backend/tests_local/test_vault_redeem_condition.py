"""Self-executing lane test (repo convention — run directly, NOT pytest):

    python tests_local/test_vault_redeem_condition.py

Covers the 2026-07-24 owner fix "a redeemed dino comes back the way it was
parked" — hunger / thirst / stamina / diet / location instead of a full bar on
every axis and a spawn wherever the game feels like.

Everything here drives the REAL writers (`vault._run_redeem`,
`vault._apply_redeem_side_effects`) against a REAL sqlite parked_dinos table,
with only the game IPC boundary captured — a seeded-state test would have missed
the original bug entirely (the pre-fix code read `max_*` and every fixture was
already full). Row fixtures are copies of REAL prod rows probed 2026-07-24.

No game / prod contact: every game_ipc write is swapped for a recorder.
"""
import contextlib
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


def main():
    tmp = tempfile.mkdtemp(prefix="lin_redeem_cond_")
    db_path = os.path.join(tmp, "test.db")
    _make_db(db_path)

    import game_ipc
    game_ipc.BOT_DB_PATH = db_path
    import vault
    import asyncio

    @contextlib.contextmanager
    def patched(**attrs):
        """Swap game_ipc / vault attributes for one block and ALWAYS put them
        back — a site that forgets to restore leaks a stub into every later
        assertion in the same process, and the failure then reads like a
        product bug rather than a test bug."""
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

    # ── REAL prod rows (probed 2026-07-24, read-only) ────────────────────────
    # id=72 Ceratosaurus, prime, growth 0.780: hunger 50.3%, thirst 75.1%
    cerato = {"dino": "BP_Ceratosaurus_C", "growth": 0.780,
              "health": 1568.9, "max_health": 1568.9,
              "stamina": 1000.0, "max_stamina": 1000.0,
              "hunger": 260.4, "max_hunger": 517.7,
              "thirst": 751.0, "max_thirst": 1000.0,
              "x": 454250.0, "y": -172925.0, "z": 26312.0,
              "is_prime": 1, "is_elder": 0,
              "mutations": "", "parent_mutations": "", "elder_mutations": "",
              "elder_stacks": 0, "skin_code": "", "skin_data": "",
              "diet_a": 130.2, "diet_b": 242.2, "diet_c": 0.0}
    # id=76 Deinosuchus, prime, growth 0.572: stamina 71.1%, hunger 84.9%
    deino = dict(cerato, dino="BP_Deinosuchus_C", growth=0.572,
                 health=1547.6, max_health=1547.6,
                 stamina=483.3, max_stamina=679.8,
                 hunger=433.6, max_hunger=510.7,
                 thirst=1000.0, max_thirst=1000.0,
                 x=179176.0, y=-62998.0, z=19324.0,
                 diet_a=280.8, diet_b=239.3, diet_c=221.2)
    # id=64 legacy row: every max at 0, no position, no diet
    legacy = dict(cerato, dino="BP_Tyrannosaurus_C", growth=1.0,
                  health=0.0, max_health=0.0, stamina=0.0, max_stamina=0.0,
                  hunger=0.0, max_hunger=0.0, thirst=0.0, max_thirst=0.0,
                  x=0.0, y=0.0, z=0.0, diet_a=0.0, diet_b=0.0, diet_c=0.0)

    ids = {}
    for key, pd in (("cerato", cerato), ("deino", deino), ("legacy", legacy)):
        ids[key] = vault.save_parked(SID, "d1", pd, cap=0)
    rows = {k: vault.get_parked_by_id(v) for k, v in ids.items()}

    def drive_redeem(row):
        """Run the REAL _run_redeem writer; the captured write returns False so
        it builds + writes the restore command then exits before the in-game
        verify loop. Returns the exact command the mod would have received."""
        captured = {}
        with patched(write_game_command=lambda cmd: (captured.update(cmd) or False)):
            jid = vault._new_job("redeem", SID)
            asyncio.run(vault._run_redeem(jid, SID, int(row["id"]), dict(row), "cmdtest"))
        return captured

    # ── 1. the reported bug: vitals come back at the PARKED fraction ──────────
    cmd = drive_redeem(rows["cerato"])
    check("restore is a restore", cmd.get("type") == "restore", repr(cmd.get("type")))
    # 50.3% hunger of the ceiling the mod will set: floor(1568.9 * 0.33) = 517
    check("hunger restored at the parked 50.3%, not the full 517.7 (the old bug)",
          abs(cmd["hunger"] - 260.0) <= 1.0, repr(cmd.get("hunger")))
    check("thirst restored at the parked 75.1%",
          abs(cmd["thirst"] - 751.0) <= 1.0, repr(cmd.get("thirst")))
    check("full health stays full", abs(cmd["health"] - 1568.9) <= 0.5, repr(cmd.get("health")))
    check("full stamina stays full", abs(cmd["stamina"] - 1000.0) <= 0.5, repr(cmd.get("stamina")))
    check("growth still verbatim", abs(float(cmd["growth"]) - 0.780) < 1e-9, repr(cmd.get("growth")))

    cmd_d = drive_redeem(rows["deino"])
    check("partial stamina restored at 71.1%",
          abs(cmd_d["stamina"] - 483.3) <= 1.0, repr(cmd_d.get("stamina")))
    # 84.9% of floor(1547.6 * 0.33) = floor(510.7) = 510  ->  433
    check("hunger 84.9% against the mod's own ceiling",
          abs(cmd_d["hunger"] - 433.0) <= 2.0, repr(cmd_d.get("hunger")))

    # ── 2. vomit guard: current food never exceeds the ceiling the mod sets ───
    # reuses the two commands already driven above — the payload is a pure
    # function of the row, so re-running the whole redeem job would add cost
    # and no coverage.
    for name, c, row in (("cerato", cmd, rows["cerato"]), ("deino", cmd_d, rows["deino"])):
        ceiling = vault._hunger_ceiling(row)
        check(f"{name}: hunger <= mod ceiling ({ceiling})",
              c["hunger"] <= ceiling, f"{c['hunger']} > {ceiling}")
    overfull = dict(rows["cerato"])
    overfull["hunger"] = overfull["max_hunger"] * 1.0000004  # float round-trip noise
    v = vault._redeem_vitals_payload(overfull)
    check("a 1.0000004 full bar cannot exceed the ceiling",
          v["hunger"] <= vault._hunger_ceiling(overfull), repr(v["hunger"]))

    # ── 3. the mod's ceiling formula is mirrored exactly ─────────────────────
    check("ceiling = floor(max_health x 0.33) for a carnivore",
          vault._hunger_ceiling(rows["cerato"]) == 517.0,
          repr(vault._hunger_ceiling(rows["cerato"])))
    herb = dict(rows["cerato"], dino_class="BP_Triceratops_C", max_health=7534.415)
    check("ceiling = floor(max_health x 0.50) for a herbivore",
          vault._hunger_ceiling(herb) == 3767.0, repr(vault._hunger_ceiling(herb)))
    unlisted = dict(rows["cerato"], dino_class="BP_FuturePatchDino_C")
    check("unlisted species falls back to the stored ceiling",
          vault._hunger_ceiling(unlisted) == 517.7, repr(vault._hunger_ceiling(unlisted)))

    # ── 4. degenerate row: fall back to the mod's refill sentinel, not zeroes ─
    cmd_l = drive_redeem(rows["legacy"])
    check("legacy row sends the health sentinel (mod refills from live maxes)",
          cmd_l["health"] == 0.0, repr(cmd_l.get("health")))
    check("legacy row sends the hunger sentinel", cmd_l["hunger"] == 0.0, repr(cmd_l.get("hunger")))
    check("legacy row stamina rides the same sentinel", cmd_l["stamina"] == 0.0,
          repr(cmd_l.get("stamina")))
    # one broken axis must take the whole trio to the sentinel, never restore a
    # dino with zero stamina it can never regain
    half_broken = dict(rows["cerato"], max_stamina=0.0, stamina=0.0)
    v = vault._redeem_vitals_payload(half_broken)
    check("one broken axis -> whole health/stamina/thirst trio to the sentinel",
          v["health"] == 0.0 and v["stamina"] == 0.0 and v["thirst"] == 0.0, repr(v))
    check("...but hunger still restores from its own good pair", v["hunger"] > 0, repr(v))

    # ── 5. a parked-empty dino stays empty (never silently refilled) ──────────
    starving = dict(rows["cerato"], hunger=0.0, thirst=0.0, stamina=0.0)
    v = vault._redeem_vitals_payload(starving)
    check("0% hunger comes back at the sentinel floor, not full",
          v["hunger"] == 1.0, repr(v["hunger"]))
    # The mod's own post-restore check (VitalAtLeast) treats expected <= 0 as a
    # FAILED axis, which flips stats_ok false and makes a landed restore report
    # as a failure — live dino AND the vault row survives. So NO axis may ever
    # go out at exactly 0 while the row has a usable snapshot.
    for axis in ("health", "stamina", "hunger", "thirst"):
        check(f"a 0%-parked {axis} never leaves as 0 (mod would call the restore failed)",
              v[axis] >= 1.0, f"{axis}={v[axis]!r}")
    for axis in ("health", "stamina", "thirst"):
        empty = dict(rows["cerato"], **{axis: 0.0})
        check(f"{axis} alone at 0% still leaves as a positive value",
              vault._redeem_vitals_payload(empty)[axis] >= 1.0, repr(empty[axis]))

    # ── 5b. a garbage float from the engine can never crash the redeem ───────
    for bad in (float("inf"), float("-inf"), float("nan")):
        poisoned = dict(rows["cerato"], max_health=bad, hunger=bad, max_hunger=bad,
                        x=bad, y=bad, z=bad)
        v = vault._redeem_vitals_payload(poisoned)   # must not raise
        check(f"{bad}: hunger falls back to the sentinel", v["hunger"] == 0.0, repr(v))
        check(f"{bad}: no non-finite reaches the command",
              all(isinstance(n, float) and n == n and abs(n) != float("inf")
                  for n in v.values()), repr(v))

    # ── 5c. the mod's HUNGER_RATIO table is the source of truth ──────────────
    # A length check is not enough: a wrong ratio silently mis-sizes every
    # hunger target. Parse the real table out of the mod Lua and compare.
    # SKIP, never fail, when the mod source tree is absent — this suite also
    # runs on the server box, which carries only the compiled artifact.
    LUA = r"C:\LaIslaNublarMod\lua\LaIslaNublarDataMod\Scripts\main.full.lua"
    if not os.path.exists(LUA):
        print("  --  ratio cross-check SKIPPED (mod source tree not on this machine)")
    if os.path.exists(LUA):
        import re
        with open(LUA, "r", encoding="utf-8", errors="replace") as fh:
            body = fh.read()
        m = re.search(r"local HUNGER_RATIO = \{(.*?)\n\}", body, re.S)
        mod_table = {}
        if m:
            for cls, val in re.findall(r"(BP_\w+)\s*=\s*([0-9.]+)", m.group(1)):
                mod_table[cls] = float(val)
        check("parsed the mod's HUNGER_RATIO table", len(mod_table) > 0, repr(len(mod_table)))
        check("python ratio table == the mod's table, exactly",
              mod_table == vault._HUNGER_RATIO,
              f"only-in-mod={set(mod_table) - set(vault._HUNGER_RATIO)} "
              f"only-in-python={set(vault._HUNGER_RATIO) - set(mod_table)} "
              f"value-diff={{k: (mod_table[k], vault._HUNGER_RATIO[k]) for k in mod_table if k in vault._HUNGER_RATIO and mod_table[k] != vault._HUNGER_RATIO[k]}}")

    # ── 6. side effects: stored diet, and NOBODY IS MOVED ────────────────────
    # Owner ruling 2026-07-29: a redeem leaves the player where they redeemed
    # from, like Arkadia. The discriminating fixture is `cerato`, which carries a
    # REAL parked x/y/z — that is exactly the row the retired lane teleported.
    _UNSET = object()

    def drive_side_effects(row, status_actor="BP_Ceratosaurus_C_2147480000", live_row=_UNSET):
        """Drives the real post-redeem task the way _run_redeem schedules it."""
        rec = {"game": [], "diet": [], "skin": []}

        async def _run():
            await vault._apply_redeem_side_effects(SID, dict(row), {"actor_name": status_actor})

        with patched(
            write_game_command=lambda c: (rec["game"].append(dict(c)) or True),
            write_diet_command=lambda c: (rec["diet"].append(dict(c)) or True),
            write_skin_command=lambda c: (rec["skin"].append(dict(c)) or True),
            read_player=(live_row if live_row is not _UNSET else
                         (lambda sid, fresh=False: {"actor_name": status_actor,
                                                    "max_hunger": 500.0,
                                                    "x": 1.0, "y": 2.0, "z": 3.0})),
        ):
            asyncio.run(_run())
        return rec

    rec = drive_side_effects(rows["cerato"])
    check("a row WITH a parked position dispatches NO teleport",
          not [c for c in rec["game"] if c.get("type") == "teleport"], repr(rec["game"]))
    check("diet replays the STORED nutrients verbatim",
          len(rec["diet"]) == 1 and rec["diet"][0]["carbs"] == 130.2
          and rec["diet"][0]["protein"] == 242.2 and rec["diet"][0]["lipids"] == 0.0,
          repr(rec["diet"]))

    rec_l = drive_side_effects(rows["legacy"])
    check("a legacy row dispatches NO teleport either",
          not [c for c in rec_l["game"] if c.get("type") == "teleport"], repr(rec_l["game"]))
    check("legacy row still gets its diet (baseline fallback)",
          len(rec_l["diet"]) == 1 and rec_l["diet"][0]["carbs"] > 0, repr(rec_l["diet"]))

    # a dead command file must still not cost the redeem its diet
    rec2 = {"diet": []}

    def _boom(_c):
        raise OSError("commands.json is gone")

    raised = None
    with patched(write_game_command=_boom,
                 write_diet_command=lambda c: (rec2["diet"].append(dict(c)) or True),
                 write_skin_command=lambda c: True,
                 read_player=lambda sid, fresh=False: {"actor_name": "A1", "max_hunger": 500.0}):
        try:
            asyncio.run(vault._apply_redeem_side_effects(
                SID, dict(rows["cerato"]), {"actor_name": "A1"}))
        except Exception as e:  # must not happen
            raised = e
    check("the side-effect lane is contained", raised is None, repr(raised))
    check("a dead command file still lets the diet through", len(rec2["diet"]) == 1,
          repr(rec2["diet"]))

    rec3 = drive_side_effects(rows["cerato"], live_row=lambda sid, fresh=False: None)
    check("a dead player feed still dispatches no teleport",
          not [c for c in rec3["game"] if c.get("type") == "teleport"], repr(rec3["game"]))

    # ── 6b. over-max fixtures ────────────────────────────────────────────────
    # a corrupt row claiming more than its own ceiling must
    # still never send a value above what the mod will allow, on ANY axis.
    for axis, mx in (("health", "max_health"), ("stamina", "max_stamina"),
                     ("hunger", "max_hunger"), ("thirst", "max_thirst")):
        over = dict(rows["cerato"])
        over[axis] = float(over[mx]) * 3.0
        ov = vault._redeem_vitals_payload(over)
        cap = (vault._hunger_ceiling(over) if axis == "hunger"
               else vault._finite(over[mx]))
        check(f"over-max {axis} is clamped to the ceiling", ov[axis] <= cap,
              f"{ov[axis]} > {cap}")

    # ── 7. the lane is REMOVED, not switched off ─────────────────────────────
    # A default-off flag is one env line away from teleporting players again, so
    # the ruling is enforced structurally: the symbols must not exist at all, and
    # the module's source must contain no teleport command anywhere.
    for gone in ("_restore_park_position", "_park_spot", "REDEEM_SPAWN_AT_PARK",
                 "REDEEM_PARK_SPOT_LIFT_UU", "REDEEM_PARK_SPOT_READBACK_SECS",
                 "REDEEM_PARK_SPOT_LANDED_UU", "_flag_env"):
        check(f"vault.{gone} no longer exists", not hasattr(vault, gone))
    with open(vault.__file__, "r", encoding="utf-8", errors="replace") as fh:
        vault_src = fh.read()
    check("vault.py emits no teleport command at all",
          '"type": "teleport"' not in vault_src and "'type': 'teleport'" not in vault_src)
    # control needle: the scan really is reading the file it thinks it is
    check("(control) the source scan can find a live string",
          '"type": "restore"' in vault_src or "restore" in vault_src)

    # ── 8. diet fallback boundary ────────────────────────────────────────────
    one_axis = dict(rows["cerato"], diet_a=0.0, diet_b=0.0, diet_c=17.5)
    check("a single non-zero axis counts as a real snapshot",
          vault._redeem_diet_payload(one_axis) == (0.0, 0.0, 17.5),
          repr(vault._redeem_diet_payload(one_axis)))
    none_stored = dict(rows["cerato"], diet_a=0.0, diet_b=0.0, diet_c=0.0)
    fb = vault._redeem_diet_payload(none_stored)
    check("no snapshot -> the old species baseline still applies",
          all(v > 0 for v in fb), repr(fb))

    # ── 9. a dino that CHANGES HANDS still loses its park position ───────────
    # Nothing reads x/y/z on the way out any more, but the belt stays: the column
    # is still written at park, and a seller's base must never travel with a sale.
    def _has_spot(row):
        return not (abs(float(row["x"])) < 1.0 and abs(float(row["y"])) < 1.0
                    and abs(float(row["z"])) < 1.0)

    seller_row = dict(rows["cerato"])          # carries steam_id + real x/y/z
    buyer_id = vault.save_parked("76561190000000099", "d2", seller_row, cap=0)
    bought = vault.get_parked_by_id(buyer_id)
    check("a market delivery drops the seller's coordinates", not _has_spot(bought),
          repr((bought["x"], bought["y"], bought["z"])))
    check("...but keeps the vitals it was parked with",
          abs(float(bought["hunger"]) - 260.4) < 0.01, repr(bought["hunger"]))
    rec_b = drive_side_effects(bought)
    check("a bought dino dispatches NO teleport",
          not [c for c in rec_b["game"] if c.get("type") == "teleport"], repr(rec_b["game"]))
    self_back = vault.save_parked(SID, "d1", dict(rows["cerato"]), cap=0)
    check("the same owner reclaiming their own row keeps the recorded spot",
          _has_spot(vault.get_parked_by_id(self_back)))

    # ── 10. NEGATIVE CONTROL: restore the old max_* behaviour, fail loudly ────
    def old_payload(parked):
        return {"health": parked.get("max_health"), "stamina": parked.get("max_stamina"),
                "hunger": parked.get("max_hunger"), "thirst": parked.get("max_thirst")}

    orig_payload = vault._redeem_vitals_payload
    vault._redeem_vitals_payload = old_payload
    try:
        broken = drive_redeem(rows["cerato"])
    finally:
        vault._redeem_vitals_payload = orig_payload
    check("NEGATIVE CONTROL: the pre-fix code hands back a full belly",
          abs(broken["hunger"] - 517.7) < 0.01 and abs(broken["thirst"] - 1000.0) < 0.01,
          repr(broken))

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    main()
