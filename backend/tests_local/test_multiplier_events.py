"""
Multiplier Events pure-logic gate -- quest_events.py + event_feed embed.

quest_events.py is dependency-free by design (see its module docstring), so
this test imports it directly and drives the EXACT decision functions
server.py's passive-payout hook and admin routes call:

  - normalize_species: BP_/_C stripping, case folding, unknown -> ""
  - event_window / event_status / event_times: lifecycle from starts_at/ends_at
    (upcoming -> active -> over), malformed windows always dead
  - pick_multiplier: the payout boost decision (fail-closed on unknown species,
    highest-wins on overlap, never stacks, inactive events never boost)
  - validate_multiplier_fields: admin input clamps (duration, multiplier)
  - event_feed.build_published_embed: announce payload never pings and carries
    species + multiplier

Run: python backend/tests_local/test_multiplier_events.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import quest_data   # noqa: E402
import quest_events  # noqa: E402

NOW = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)


def _ev(species="Dryosaurus", mult=30, starts_off_h=-1, ends_off_h=23, **extra):
    ev = {"id": "ev1", "title": f"Día de {species}", "species": species, "multiplier": mult,
          "starts_at": (NOW + timedelta(hours=starts_off_h)).isoformat(),
          "ends_at": (NOW + timedelta(hours=ends_off_h)).isoformat()}
    ev.update(extra)
    return ev


def main() -> int:
    failures = []

    # 1) species normalisation: every raw shape lands on the canonical name.
    for raw in ("Dryosaurus", "dryosaurus", "BP_Dryosaurus_C", " BP_Dryosaurus_C "):
        if quest_events.normalize_species(raw) != "Dryosaurus":
            failures.append(f"normalize_species({raw!r}) must be 'Dryosaurus'")
    for raw in ("", None, "NotADino", "BP_Human_C", 42):
        if quest_events.normalize_species(raw) != "":
            failures.append(f"normalize_species({raw!r}) must fail closed to ''")
    if len(quest_data.EVENT_SPECIES) != 22:
        failures.append(f"EVENT_SPECIES must stay the 21-species fleet list (got {len(quest_data.EVENT_SPECIES)})")

    # 2) lifecycle: upcoming -> active -> over; malformed windows are dead.
    if quest_events.event_status(_ev(starts_off_h=1, ends_off_h=2), NOW) != "upcoming":
        failures.append("future start must be 'upcoming'")
    if quest_events.event_status(_ev(), NOW) != "active":
        failures.append("inside the window must be 'active'")
    if quest_events.event_status(_ev(starts_off_h=-3, ends_off_h=-1), NOW) != "over":
        failures.append("past end must be 'over' (auto-expiry)")
    for bad in ({}, _ev(starts_off_h=2, ends_off_h=2), _ev(starts_off_h=2, ends_off_h=1),
                {"starts_at": "garbage", "ends_at": "alsogarbage"}, None):
        if quest_events.event_status(bad, NOW) != "":
            failures.append(f"malformed window {bad!r} must have status ''")

    # Exactly at ends_at the event is over (now < ends is the active test).
    edge = _ev(starts_off_h=-1, ends_off_h=0)
    if quest_events.event_status(edge, NOW) != "over":
        failures.append("now == ends_at must already be 'over'")

    # 3) countdowns: never negative, status carried, naive iso tolerated.
    t = quest_events.event_times(_ev(starts_off_h=1, ends_off_h=3), NOW)
    if t["status"] != "upcoming" or t["starts_in"] != 3600 or t["ends_in"] != 3 * 3600:
        failures.append(f"upcoming countdowns wrong: {t}")
    t = quest_events.event_times(_ev(starts_off_h=-3, ends_off_h=-1), NOW)
    if t["starts_in"] != 0 or t["ends_in"] != 0:
        failures.append("expired countdowns must clamp to 0")
    naive = {"starts_at": "2026-07-17T11:00:00", "ends_at": "2026-07-17T13:00:00"}
    if quest_events.event_status(naive, NOW) != "active":
        failures.append("tz-naive ISO stamps must be treated as UTC")

    # 4) pick_multiplier: the payout boost decision.
    active = _ev()
    m, ev = quest_events.pick_multiplier([active], "BP_Dryosaurus_C", NOW)
    if m != 30 or ev is not active:
        failures.append(f"matching species must boost x30 (got {m})")
    m, ev = quest_events.pick_multiplier([active], "Tyrannosaurus", NOW)
    if m != 1 or ev is not None:
        failures.append("non-matching species must not boost")
    m, ev = quest_events.pick_multiplier([active], "", NOW)
    if m != 1 or ev is not None:
        failures.append("unknown player species must fail closed to x1")
    m, ev = quest_events.pick_multiplier([], "Dryosaurus", NOW)
    if m != 1:
        failures.append("no events -> x1")
    m, ev = quest_events.pick_multiplier(None, "Dryosaurus", NOW)
    if m != 1:
        failures.append("None events -> x1")
    # Inactive events never boost, whatever their multiplier says.
    for dead in (_ev(starts_off_h=1, ends_off_h=2, mult=500),
                 _ev(starts_off_h=-3, ends_off_h=-1, mult=500),
                 _ev(mult=500, starts_at="nope")):
        m, _ = quest_events.pick_multiplier([dead], "Dryosaurus", NOW)
        if m != 1:
            failures.append(f"non-active event must never boost (got x{m})")
    # Overlap: highest single multiplier wins -- never stacked, never the sum.
    m, ev = quest_events.pick_multiplier([_ev(mult=10), _ev(mult=40), _ev(mult=25)], "Dryosaurus", NOW)
    if m != 40:
        failures.append(f"overlapping events must pick the highest (got x{m})")
    # Garbage multiplier values are skipped, not crashed on.
    m, _ = quest_events.pick_multiplier([_ev(mult="banana"), _ev(mult=None), _ev(mult=12)], "Dryosaurus", NOW)
    if m != 12:
        failures.append(f"garbage multiplier rows must be skipped (got x{m})")
    m, _ = quest_events.pick_multiplier([_ev(mult="banana")], "Dryosaurus", NOW)
    if m != 1:
        failures.append("only-garbage multiplier must fall back to x1")

    # 5) admin clamps: bounds + defaults from quest_data.
    v = quest_events.validate_multiplier_fields(None, None)
    if v != {"duration_hours": quest_data.MULT_EVENT_DEFAULT_HOURS,
             "multiplier": quest_data.MULT_EVENT_DEFAULT}:
        failures.append(f"None inputs must land on defaults: {v}")
    v = quest_events.validate_multiplier_fields(99999, 99999)
    if v["duration_hours"] != quest_data.EVENT_MAX_HOURS or v["multiplier"] != quest_data.MULT_EVENT_MAX:
        failures.append(f"over-caps must clamp to maxima: {v}")
    v = quest_events.validate_multiplier_fields(0, 1)
    if v["duration_hours"] != 1 or v["multiplier"] != quest_data.MULT_EVENT_MIN:
        failures.append(f"under-floors must clamp to minima: {v}")
    v = quest_events.validate_multiplier_fields("48", "30")
    if v != {"duration_hours": 48, "multiplier": 30}:
        failures.append(f"numeric strings must parse: {v}")

    # 6) announce embed: species + multiplier present, mentions always empty.
    import event_feed
    payload = event_feed.build_published_embed(_ev(), 24)
    embed = payload["embeds"][0]
    if payload.get("allowed_mentions") != {"parse": []}:
        failures.append("embed must never allow mentions")
    if "Día de Dryosaurus" not in embed["title"]:
        failures.append(f"embed title must carry the event title: {embed['title']!r}")
    flat = str(embed)
    if "x30" not in flat or "Dryosaurus" not in flat or "1 día" not in flat:
        failures.append("embed must carry multiplier, species and duration")
    # Garbage event never raises -- the feed is fire-and-forget by contract.
    try:
        event_feed.build_published_embed({}, "junk")
    except Exception as e:  # noqa: BLE001
        failures.append(f"build_published_embed must not raise on garbage: {e}")

    if failures:
        print("FAIL -- multiplier events gate:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS -- species normalisation, lifecycle (upcoming/active/over + malformed-dead), "
          "boost decision (fail-closed, highest-wins, inactive-never), admin clamps and the "
          "announce embed all correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
