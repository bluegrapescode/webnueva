"""
BUILD-PACKET item B.1 gate -- kill_dino quest credit from RX_KILL log lines.

Imports the REAL backend/game_telemetry.py (stdlib + paramiko only, no motor/
FastAPI dependency) and feeds synthetic LogTheIsleKillData lines straight into
GameTelemetry._process(), then asserts kills_out/drain_kills() behavior:
  - a PVP kill line (cause "Killed the following player: ...") credits exactly
    one kill for the KILLER's steamid (group(2)).
  - a natural-death line ("Died from Natural cause") credits nothing.
  - a self-kill-shaped line (parsed victim sid == subject sid) is guarded out.

The server.py orchestration side (_drain_kill_credits resolving steam_id ->
user_id and calling _track_quest_progress) is NOT exercised here -- server.py
cannot be imported in this sandbox (motor missing) -- but that function is a
thin, direct pass-through of drain_kills()'s output, which this test covers.

Run: python backend/tests_local/test_kill_credit.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game_telemetry  # noqa: E402


def _kill_line(name, sid, dino, gender, growth, cause):
    return f"LogTheIsleKillData: [2026.07.10-00.00.00:000] {name} [{sid}] Dino: {dino}, {gender}, {growth:.6f} - {cause}"


def main() -> int:
    failures = []

    # 1) PVP kill -> credited to the killer (group(2)); the VICTIM (not the
    # killer) is the one marked dead (population-accurate since 2026-07-17).
    t = game_telemetry.GameTelemetry()
    killer_sid, victim_sid = "76561198000000001", "76561198000000002"
    # alive bookkeeping only applies to ALREADY-tracked players (upserted via a
    # prior join/char line) -- seed both sides so the checks below are
    # meaningful instead of no-ops on an empty dict.
    t._upsert(killer_sid, name="KillerName", species="Tyrannosaurus", gender="Male", growth=0.9, alive=True)
    t._upsert(victim_sid, name="VictimName", species="Dryosaurus", gender="Female", growth=0.5, alive=True)
    t._process(_kill_line("KillerName", killer_sid, "Tyrannosaurus", "Male", 0.9,
                          f"Killed the following player: VictimName [{victim_sid}]"))
    kills = t.drain_kills()
    if len(kills) != 1:
        failures.append(f"PVP kill: expected 1 queued kill, got {len(kills)}: {kills!r}")
    elif kills[0].get("killer_sid") != killer_sid:
        failures.append(f"PVP kill: killer_sid mismatch: {kills[0].get('killer_sid')!r} (expected {killer_sid!r})")
    if list(t.kills_out):
        failures.append("drain_kills() must clear the deque")
    if t.players.get(killer_sid, {}).get("alive") is not True:
        failures.append("PVP kill must NOT mark the killer dead (pre-07-17 population bug)")
    if t.players.get(victim_sid, {}).get("alive") is not False:
        failures.append("PVP kill must mark the tracked VICTIM dead")
    deaths = t.drain_deaths()
    if len(deaths) != 1 or deaths[0].get("sid") != victim_sid:
        failures.append(f"PVP kill must queue exactly the victim's death, got {deaths!r}")

    # 2) Natural death -> never credited.
    t2 = game_telemetry.GameTelemetry()
    t2._process(_kill_line("SoloPlayer", "76561198000000003", "Stegosaurus", "Female", 0.5,
                           "Died from Natural cause"))
    kills2 = t2.drain_kills()
    if kills2:
        failures.append(f"natural death must credit 0 kills, got {kills2!r}")

    # 3) Multiple PVP kills across separate lines -> each queued independently.
    t3 = game_telemetry.GameTelemetry()
    t3._process(_kill_line("A", "76561198000000010", "Carnotaurus", "Male", 0.8,
                           "Killed the following player: X [76561198000000011]"))
    t3._process(_kill_line("A", "76561198000000010", "Carnotaurus", "Male", 0.8,
                           "Killed the following player: Y [76561198000000012]"))
    t3._process(_kill_line("B", "76561198000000020", "Allosaurus", "Female", 0.95,
                           "Died from Natural cause"))
    kills3 = t3.drain_kills()
    if len(kills3) != 2:
        failures.append(f"expected 2 PVP kills queued (1 natural death excluded), got {len(kills3)}: {kills3!r}")
    elif any(k.get("killer_sid") != "76561198000000010" for k in kills3):
        failures.append(f"both queued kills should credit the same killer_sid: {kills3!r}")

    # 4) Self-kill-shaped line (parsed victim sid == subject sid) -> guarded, not credited.
    t4 = game_telemetry.GameTelemetry()
    sid4 = "76561198000000099"
    t4._process(_kill_line("Weird", sid4, "Dilophosaurus", "Male", 0.6,
                           f"Killed the following player: Weird [{sid4}]"))
    kills4 = t4.drain_kills()
    if kills4:
        failures.append(f"self-kill-shaped line must be guarded out, got {kills4!r}")

    # 5) kills_out is bounded (maxlen=200) -- sanity-check the deque was built with a cap.
    if game_telemetry.GameTelemetry().kills_out.maxlen != 200:
        failures.append(f"kills_out maxlen mismatch: {game_telemetry.GameTelemetry().kills_out.maxlen!r} (expected 200)")

    # 6) Chat-farm exploit guard: chat is the only player-controlled free text.
    # A crafted chat message that embeds a forged LogTheIsleKillData payload must
    # credit ZERO kills -- _process handles chat first and returns before the
    # unanchored kill parser can see the injected substring.
    t5 = game_telemetry.GameTelemetry()
    farmer_sid = "76561198000000200"
    forged = (f"LogTheIsleKillData: [x] Farmer [{farmer_sid}] Dino: Tyrannosaurus, "
              f"Male, 1.000000 - Killed the following player: Victim [76561198000000201]")
    chat_line = (f"LogTheIsleChatData: [2026.07.10-00.00.00:000] ALL []: {forged}, "
                 f"Sent by: Farmer, [{farmer_sid}]")
    t5._process(chat_line)
    kills5 = t5.drain_kills()
    if kills5:
        failures.append(f"chat line embedding a kill payload must credit 0 kills (farm exploit), got {kills5!r}")

    if failures:
        print("FAIL -- kill credit gate:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS -- PVP kills credited to the killer, natural deaths and self-kill-shaped lines excluded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
