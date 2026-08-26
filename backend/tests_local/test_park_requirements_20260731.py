"""Self-executing lane test (repo convention — run directly, NOT pytest):

    python tests_local/test_park_requirements_20260731.py

Covers the 2026-07-31 owner rule for parking:
  * stamina floor 70% (unchanged, asserted so a future edit cannot drift it)
  * hunger floor 20% -> 50%, and the refusal names the real value
  * a 2-minute per-SteamID park wait: stamped, counted down, expiring, and
    disable-able with PARK_COOLDOWN_SECS=0
  * web and bot agree on every threshold and on the cooldown file

No game, no prod, no network: the cooldown map is written under a tmp dir.
"""
import os
import sys
import tempfile
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


def live_row(**over):
    row = {
        "actor_name": "Rex_1", "growth": 1.0,
        "health": 100.0, "max_health": 100.0,
        "stamina": 100.0, "max_stamina": 100.0,
        "hunger": 100.0, "max_hunger": 100.0,
        "thirst": 100.0, "max_thirst": 100.0,
        "last_updated": time.time(),
    }
    row.update(over)
    return row


def main():
    tmp = tempfile.mkdtemp(prefix="lin_park_req_")
    os.environ["BOT_DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ.pop("PARK_MIN_HUNGER_PCT", None)
    os.environ.pop("PARK_MIN_STAMINA_PCT", None)
    os.environ.pop("PARK_COOLDOWN_SECS", None)

    import game_ipc
    import vault
    game_ipc.DATA_DIR = tmp

    # ── thresholds ───────────────────────────────────────────────────────────
    check("stamina floor is 70%", abs(vault.PARK_MIN_STAMINA_PCT - 0.70) < 1e-9,
          vault.PARK_MIN_STAMINA_PCT)
    check("hunger floor is 50%", abs(vault.PARK_MIN_HUNGER_PCT - 0.50) < 1e-9,
          vault.PARK_MIN_HUNGER_PCT)
    check("health floor still 100%", abs(vault.PARK_MIN_HEALTH_PCT - 1.0) < 1e-9,
          vault.PARK_MIN_HEALTH_PCT)

    check("full bars pass", vault.park_gate_failures(live_row()) == [],
          vault.park_gate_failures(live_row()))

    at_floor = vault.park_gate_failures(live_row(hunger=50.0, stamina=70.0))
    check("exactly at both floors passes", at_floor == [], at_floor)

    hungry = vault.park_gate_failures(live_row(hunger=49.0))
    check("49% hunger fails", any("Hambre" in f for f in hungry), hungry)
    check("hunger refusal names 49 and 50",
          any("49" in f and "50" in f for f in hungry), hungry)

    tired = vault.park_gate_failures(live_row(stamina=69.0))
    check("69% stamina fails", any("Energía" in f for f in tired), tired)
    check("stamina refusal names 69 and 70",
          any("69" in f and "70" in f for f in tired), tired)

    # 20% hunger was legal before this wave — the whole point is that it is not.
    check("NEGATIVE CONTROL: 20% hunger is now refused",
          any("Hambre" in f for f in vault.park_gate_failures(live_row(hunger=20.0))))

    # ── the 2-minute wait ────────────────────────────────────────────────────
    check("park wait defaults to 120s", vault.PARK_COOLDOWN_SECS == 120,
          vault.PARK_COOLDOWN_SECS)
    sid = "76561198000000001"
    check("ready before any park", vault.park_cooldown_remaining(sid) == 0)
    vault.record_park(sid)
    left = vault.park_cooldown_remaining(sid)
    check("stamped: waits ~2 min", 100 <= left <= 120, left)
    check("wait file lands under DATA_DIR",
          os.path.dirname(vault._park_cooldowns_path()) == tmp,
          vault._park_cooldowns_path())
    check("another player is unaffected",
          vault.park_cooldown_remaining("76561198000000002") == 0)

    # An expired stamp must free the player without any sweep running.
    import json
    with open(vault._park_cooldowns_path(), "w", encoding="utf-8") as f:
        json.dump({sid: time.time() - 121}, f)
    check("expired stamp reads as ready", vault.park_cooldown_remaining(sid) == 0)

    # Wording: seconds under a minute, so a 2-minute wait never reads "1 min"
    # for its last 59 seconds.
    check("wait text: seconds under a minute", vault._wait_text_es(45) == "45 s",
          vault._wait_text_es(45))
    check("wait text: rounds minutes up", vault._wait_text_es(61) == "2 min",
          vault._wait_text_es(61))
    check("wait text: exact minute", vault._wait_text_es(120) == "2 min",
          vault._wait_text_es(120))

    # Kill switch: 0 = no wait at all, even with a fresh stamp on disk.
    real_secs = vault.PARK_COOLDOWN_SECS
    vault.PARK_COOLDOWN_SECS = 0
    vault.record_park(sid)
    check("PARK_COOLDOWN_SECS=0 removes the wait",
          vault.park_cooldown_remaining(sid) == 0)
    vault.PARK_COOLDOWN_SECS = real_secs

    # A bad env value must keep the owner's default, never silently drop the gate.
    check("typo falls back to the default",
          vault._cooldown_env_secs_default("LIN_NO_SUCH_KNOB", 120) == 120)
    os.environ["LIN_TEST_BAD_COOLDOWN"] = "two minutes"
    check("unparseable value falls back to the default",
          vault._cooldown_env_secs_default("LIN_TEST_BAD_COOLDOWN", 120) == 120)
    os.environ["LIN_TEST_BAD_COOLDOWN"] = "0"
    check("explicit 0 disables",
          vault._cooldown_env_secs_default("LIN_TEST_BAD_COOLDOWN", 120) == 0)
    os.environ.pop("LIN_TEST_BAD_COOLDOWN", None)

    # ── the summary the panel greys its button on ────────────────────────────
    check("summary exposes park_cooldown_s",
          "park_cooldown_s" in vault.summary.__code__.co_consts
          or "park_cooldown_s" in open(os.path.join(os.path.dirname(HERE), "vault.py"),
                                       encoding="utf-8").read())

    # ── web and bot must not drift ───────────────────────────────────────────
    bot_dir = os.path.abspath(os.path.join(os.path.dirname(HERE), "..", "..", "bot"))
    cfg = open(os.path.join(bot_dir, "config.py"), encoding="utf-8").read()
    check("bot hunger default is 0.50", '"PARK_MIN_HUNGER_PCT", "0.50"' in cfg)
    check("bot stamina default is 0.70", '"PARK_MIN_STAMINA_PCT", "0.70"' in cfg)
    check("bot park wait default is 120", '"PARK_COOLDOWN_SECS", 120' in cfg)
    check("bot writes the SAME wait file the web reads",
          'PARK_COOLDOWNS_JSON = os.path.join(DATA_DIR, "park_cooldowns.json")' in cfg)
    dino_src = open(os.path.join(bot_dir, "dino.py"), encoding="utf-8").read()
    check("bot park checks the wait", "get_park_cooldown_remaining" in dino_src)
    # The stamp must sit AFTER the queued/failed returns, i.e. after the final
    # count read on the success path — never next to the gate.
    check("bot stamps only after a stored dino",
          dino_src.index("record_park_used, steam_id")
          > dino_src.index("get_park_cooldown_remaining, steam_id"))

    print()
    if failures:
        print(f"FAILED: {len(failures)} — " + ", ".join(failures))
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
