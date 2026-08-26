"""
BUILD-PACKET item B.2 gate -- visit_location quest tracker (quest_pois.py).

quest_pois.py has zero server.py/Mongo/FastAPI dependency by design (see its
module docstring), so this test imports it directly and drives the EXACT same
pure decision functions (nearest_poi / quest_matches_poi / should_credit_visit)
server.py's _visit_poi_tracker_tick calls. The Mongo quest_visits collection is
stood in for by a tiny in-memory FakeVisitStore, and _run_tick() below mirrors
_visit_poi_tracker_tick's per-user body verbatim (same order of operations:
already-today check -> insert bookkeeping doc -> per-quest credit decision).

Run: python backend/tests_local/test_visit_tracker.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import quest_pois  # noqa: E402

POI_A = next(p for p in quest_pois.POIS if p["name"] == "North Bay")
POI_B = next(p for p in quest_pois.POIS if p["name"] == "Port")
TOP_OF_DOME = next(p for p in quest_pois.POIS if p["name"] == "Top of Dome")


class FakeVisitStore:
    """Stands in for the Mongo `quest_visits` collection."""
    def __init__(self):
        self.docs = []

    def has_day(self, user_id, poi, day_key):
        return any(d["user_id"] == user_id and d["poi"] == poi and d["day_key"] == day_key for d in self.docs)

    def has_week(self, user_id, poi, week_key):
        return any(d["user_id"] == user_id and d["poi"] == poi and d["week_key"] == week_key for d in self.docs)

    def insert(self, user_id, poi, day_key, week_key):
        self.docs.append({"user_id": user_id, "poi": poi, "day_key": day_key, "week_key": week_key})


def run_tick(store, credits, user_id, x, y, day_key, week_key, quests):
    """Mirrors server.py's _visit_poi_tracker_tick per-user body verbatim."""
    poi = quest_pois.nearest_poi(x, y)
    if not poi:
        return None
    if store.has_day(user_id, poi, day_key):
        return poi  # nothing new this tick -- already bookkept today for this POI
    already_this_week = store.has_week(user_id, poi, week_key)
    store.insert(user_id, poi, day_key, week_key)
    for q in quests:
        if not quest_pois.quest_matches_poi(q.get("objective") or {}, poi):
            continue
        if quest_pois.should_credit_visit(already_today=False, already_this_week=already_this_week,
                                          quest_category=q.get("category", "daily")):
            credits.append((user_id, q["key"], poi))
    return poi


def main() -> int:
    failures = []

    open_daily = {"key": "daily_any_poi", "category": "daily", "objective": {}}
    open_weekly = {"key": "weekly_cartographer", "category": "weekly", "objective": {}}
    dome_only = {"key": "daily_visit_dome", "category": "daily", "objective": {"poi": "Top of Dome"}}
    port_only_weekly = {"key": "weekly_port_only", "category": "weekly", "objective": {"poi": "Port"}}
    quests = [open_daily, open_weekly, dome_only, port_only_weekly]

    # 1) two ticks, same POI, same period -> 1 progress (for the open daily quest).
    store = FakeVisitStore()
    credits = []
    run_tick(store, credits, "u1", POI_A["x"], POI_A["y"], "2026-07-10", "2026-W28", quests)
    run_tick(store, credits, "u1", POI_A["x"], POI_A["y"], "2026-07-10", "2026-W28", quests)
    daily_credits = [c for c in credits if c[1] == "daily_any_poi"]
    if len(daily_credits) != 1:
        failures.append(f"same POI/same day twice: expected 1 daily credit, got {len(daily_credits)}: {daily_credits!r}")
    weekly_credits = [c for c in credits if c[1] == "weekly_cartographer"]
    if len(weekly_credits) != 1:
        failures.append(f"same POI/same week twice: expected 1 weekly credit, got {len(weekly_credits)}: {weekly_credits!r}")

    # 2) different POIs, same period -> 2 progress.
    store2 = FakeVisitStore()
    credits2 = []
    run_tick(store2, credits2, "u2", POI_A["x"], POI_A["y"], "2026-07-10", "2026-W28", quests)
    run_tick(store2, credits2, "u2", POI_B["x"], POI_B["y"], "2026-07-10", "2026-W28", quests)
    daily_credits2 = [c for c in credits2 if c[1] == "daily_any_poi"]
    if len(daily_credits2) != 2:
        failures.append(f"two distinct POIs same day: expected 2 daily credits, got {len(daily_credits2)}: {daily_credits2!r}")
    weekly_credits2 = [c for c in credits2 if c[1] == "weekly_cartographer"]
    if len(weekly_credits2) != 2:
        failures.append(f"two distinct POIs same week: expected 2 weekly credits (distinct POIs), got {len(weekly_credits2)}: {weekly_credits2!r}")

    # 2b) same POI revisited on a DIFFERENT day within the SAME week -> daily credits
    #     again (new day bucket) but the WEEKLY quest must NOT double-credit the same
    #     distinct POI a second time in the week.
    store2b = FakeVisitStore()
    credits2b = []
    run_tick(store2b, credits2b, "u2b", POI_A["x"], POI_A["y"], "2026-07-10", "2026-W28", quests)
    run_tick(store2b, credits2b, "u2b", POI_A["x"], POI_A["y"], "2026-07-11", "2026-W28", quests)  # next day, same ISO week
    daily_2b = [c for c in credits2b if c[1] == "daily_any_poi"]
    weekly_2b = [c for c in credits2b if c[1] == "weekly_cartographer"]
    if len(daily_2b) != 2:
        failures.append(f"same POI, two different days: expected 2 daily credits, got {len(daily_2b)}: {daily_2b!r}")
    if len(weekly_2b) != 1:
        failures.append(f"same POI, two different days SAME week: expected 1 weekly credit (not a new distinct POI), got {len(weekly_2b)}: {weekly_2b!r}")

    # 3) objective.poi restriction honored: dome_only/port_only_weekly must ONLY
    #    credit when the resolved POI is an exact match.
    store3 = FakeVisitStore()
    credits3 = []
    run_tick(store3, credits3, "u3", POI_A["x"], POI_A["y"], "2026-07-10", "2026-W28", quests)  # North Bay
    run_tick(store3, credits3, "u3", POI_B["x"], POI_B["y"], "2026-07-10", "2026-W28", quests)  # Port
    dome_credits = [c for c in credits3 if c[1] == "daily_visit_dome"]
    if dome_credits:
        failures.append(f"daily_visit_dome (poi='Top of Dome') must never credit from North Bay/Port: {dome_credits!r}")
    port_credits = [c for c in credits3 if c[1] == "weekly_port_only"]
    if len(port_credits) != 1 or port_credits[0][2] != "Port":
        failures.append(f"weekly_port_only (poi='Port') must credit exactly once, from Port only: {port_credits!r}")

    # 4) "Top of Dome" has coords None -- it can never be `nearest_poi`'s result, so
    #    daily_visit_dome is unreachable today (forward-compatible placeholder).
    if TOP_OF_DOME["x"] is not None or TOP_OF_DOME["y"] is not None:
        failures.append(f"Top of Dome must carry coords None today: {TOP_OF_DOME!r}")
    if quest_pois.nearest_poi(0, 0) == "Top of Dome":
        failures.append("nearest_poi() must never resolve to a coords-None POI")

    # 5) quest_matches_poi: no objective.poi -> any POI accepted; poi set -> exact match only.
    if not quest_pois.quest_matches_poi({}, "Anything"):
        failures.append("quest_matches_poi({}, ...) must default to True (no restriction)")
    if quest_pois.quest_matches_poi({"poi": "Port"}, "North Bay"):
        failures.append("quest_matches_poi must reject a non-matching poi")
    if not quest_pois.quest_matches_poi({"poi": "Port"}, "Port"):
        failures.append("quest_matches_poi must accept an exact poi match")

    if failures:
        print("FAIL -- visit tracker gate:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS -- visit_location dedupe (same POI/period -> 1, distinct POIs -> N), "
          "weekly distinct-POI semantics, and objective.poi restriction all correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
