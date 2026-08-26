# -*- coding: utf-8 -*-
"""GEN-Ø facility infection gate — geometry, dwell, once-per-life, banners.

Drives the REAL backend/gen0_infection.py with a motor-shaped fake Mongo, a
recorded positions feed and a temp death_causes.log — nothing here contacts
the game, Mongo or prod.

Edge cases enumerated up front (four-leg charter):
  empty/zero/missing rows · NaN/inf/stale/overflow rows · logout mid-exposure
  · death mid-exposure · re-claim in the same life (must refuse) · claim again
  next life (must allow) · a LIVING pawn that reads health<=0 (restore grace /
  entomb transient — must NOT reset a life: the 2026-08-21 refuted exploit) ·
  park→redeem of the same dino (one life, no re-farm) · percent already 100
  (one doc read per visit, not per tick) · Mongo write fault mid-credit
  (retry, exactly-once) · Mongo down on the endpoint (503, never 500) ·
  first-run no state doc · death-log tail semantics (start at END, partial
  line, bad JSON, truncation) · notify file merge keeps a concurrent
  producer's blocks · a claimed queue that cannot be read is put BACK ·
  banner text can never break the mod's parser · dwell map hard bound ·
  the geometry itself re-proven against the surveyed ledger areas ·
  TRANSFORMATION LANE (2026-08-21): completion enqueues gen0_zombie in the
  same batch, exactly once · backfill only while seen alive · retry gate
  holds and reopens · "on" acks + stops retries, idempotent, never mints a
  doc · "off"/new-life apply ONE reset (zombie_active filter) · a DEATH LINE is
  NOT a zombie reset (park kill / safelog / logout reach the same latch) ·
  "on" lifts a reset bar back to 100 (parked zombie redeemed) · the full
  park -> other life -> redeem -> real death cycle
  · junk events dropped · missing/truncated events file survives · kill
  switch stops enqueues but resets still land · sweep survives Mongo down ·
  the no-facilities-route removal is pinned ·
  BETWEEN-FACILITY COOLDOWN (owner 2026-08-21 "far too easy to get"): a
  second facility inside the window refuses, banners the countdown, and never
  latches the stay dead · camping through expiry pays without re-entry ·
  death/new-life leave the stamp standing (die-to-skip refused) · knob 0
  restores the old behavior · junk/absent stamps read FREE, a clock jump
  costs at most one window · the endpoint reports cooldown_s for the site.

Run: python -m pytest backend/tests_local/test_gen0_infection.py
"""
import asyncio
import builtins
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

import gen0_infection as g0  # noqa: E402


# ─── fake motor db (only what gen0_infection touches) ────────────────────────
class _Res:
    def __init__(self, modified):
        self.modified_count = modified


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length=None):
        return self.rows if length is None else self.rows[:length]


class FakeCollection:
    def __init__(self):
        self.docs = {}
        self.fail_next_update = 0
        self.fail_find = False
        self.update_calls = 0
        self.find_calls = 0

    async def find_one(self, q, projection=None):
        self.find_calls += 1
        if self.fail_find:
            raise RuntimeError("injected mongo down")
        d = self.docs.get(q.get("steam_id"))
        return dict(d) if d else None

    async def update_one(self, q, update, upsert=False):
        self.update_calls += 1
        if self.fail_next_update > 0:
            self.fail_next_update -= 1
            raise RuntimeError("injected mongo fault")
        sid = q.get("steam_id")
        doc = self.docs.get(sid)
        # honor extra equality filters (e.g. {"zombie_active": True}) the way
        # Mongo does: a filter miss modifies nothing
        for k, v in q.items():
            if k == "steam_id":
                continue
            if doc is None or doc.get(k) != v:
                return _Res(0)
        if doc is None:
            if not upsert:
                return _Res(0)
            doc = {"steam_id": sid}
            for k, v in (update.get("$setOnInsert") or {}).items():
                doc[k] = v
        for k, v in (update.get("$set") or {}).items():
            doc[k] = v
        self.docs[sid] = doc
        return _Res(1)

    def find(self, q, projection=None):
        """$in on steam_id + $gte on percent — exactly what the zombify sweep
        issues; returns a cursor with to_list, motor-shaped."""
        self.find_calls += 1
        if self.fail_find:
            raise RuntimeError("injected mongo down")
        sids = (q.get("steam_id") or {}).get("$in") or []
        gte = (q.get("percent") or {}).get("$gte")
        rows = []
        for sid in sids:
            d = self.docs.get(sid)
            if d is None:
                continue
            try:
                pct = int(d.get("percent") or 0)
            except (TypeError, ValueError):
                pct = 0
            if gte is None or pct >= gte:
                rows.append(dict(d))
        return _FakeCursor(rows)


class FakeDB:
    def __init__(self):
        self.gen0_state = FakeCollection()


SID = "76561198425701464"
SID2 = "76561199602935964"
SID3 = "76561198000000001"

F2 = next(f for f in g0.FACILITIES if f["id"] == "lin_zombie_facility_2")
F2X = sum(p[0] for p in F2["poly"]) / 4
F2Y = sum(p[1] for p in F2["poly"]) / 4
F2Z = 22180.0
F4 = next(f for f in g0.FACILITIES if f["id"] == "lin_zombie_facility_4")
F4X = sum(p[0] for p in F4["poly"]) / 4
F4Y = sum(p[1] for p in F4["poly"]) / 4
F4Z = 20930.0
AWAY = dict(x=0.0, y=0.0, z=100.0)


def row(x=F2X, y=F2Y, z=F2Z, health=500.0, growth=0.5, dino="BP_Tyrannosaurus_C",
        last_updated=None):
    r = {"steamid": None, "x": x, "y": y, "z": z, "health": health,
         "growth": growth, "dino": dino}
    if last_updated is not None:
        r["last_updated"] = last_updated
    return r


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """Fresh module state per test: fake db, temp notify + death-log paths,
    stubbed positions feed."""
    db = FakeDB()
    notify = str(tmp_path / "notify_commands.json")
    deathlog = str(tmp_path / "death_causes.log")
    eventlog = str(tmp_path / "gen0_zombie_events.log")
    open(deathlog, "w").close()
    open(eventlog, "w").close()
    g0.configure(db, notify_path=notify, deathlog_path=deathlog,
                 eventlog_path=eventlog)
    g0._dwell.clear()
    feed = {"positions": None}

    def read_fresh(max_age_s=90):
        return feed["positions"]

    monkeypatch.setattr(g0.game_ipc, "read_players_positions_fresh", read_fresh)
    return {"db": db, "notify": notify, "deathlog": deathlog,
            "eventlog": eventlog, "feed": feed}


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


WALL0 = 1_787_300_000_000  # synthetic wall clock: now_ms = WALL0 + t_mono*1000


async def drive(env, steps):
    """steps: list of (t_mono, positions_dict). Each step = one full loop pass
    (death-log tick, then tracker tick). Returns all banner blocks. The wall
    clock the cooldown is judged against advances in lockstep with t_mono."""
    out = []
    for t, positions in steps:
        env["feed"]["positions"] = positions
        await g0._deathlog_tick()
        out.extend(await g0._tracker_tick(now_mono=t,
                                          now_ms=WALL0 + int(t * 1000)))
    return out


def death_line(env, sid, dino="BP_Tyrannosaurus_C", growth=0.5, raw=None):
    """Append one line to the fake death_causes.log the way the mod does."""
    with open(env["deathlog"], "a", encoding="utf-8") as f:
        if raw is not None:
            f.write(raw)
        else:
            f.write(json.dumps({"ts": 1787290144, "sid": sid, "cause": "unknown",
                                "dino": dino, "growth": growth}) + "\n")


# ─── geometry: the ledger is the oracle ──────────────────────────────────────
def _shoelace_m2(poly):
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0 / 10000.0


def test_polygons_match_surveyed_areas():
    expect = {"lin_zombie_facility_1": 17686.7, "lin_zombie_facility_2": 10696.4,
              "lin_zombie_facility_3": 19376.2, "lin_zombie_facility_4": 6007.4}
    assert len(g0.FACILITIES) == 4
    for f in g0.FACILITIES:
        assert abs(_shoelace_m2(f["poly"]) - expect[f["id"]]) < 0.5, f["id"]


def test_point_in_poly_rotated_not_a_box():
    xs = [p[0] for p in F2["poly"]]
    ys = [p[1] for p in F2["poly"]]
    assert g0.point_in_poly(F2X, F2Y, F2["poly"]) is True
    assert g0.point_in_poly(min(xs) + 20.0, min(ys) + 20.0, F2["poly"]) is False


def test_facility_at_z_band():
    assert g0.facility_at(F2X, F2Y, F2Z) is not None
    assert g0.facility_at(F2X, F2Y, F2Z + g0.Z_ABOVE_CM + 200000) is None
    assert g0.facility_at(F2X, F2Y, F2Z - g0.Z_BELOW_CM - 200000) is None
    assert g0.facility_at(0.0, 0.0, 0.0) is None


def test_facility_3_irregular_quad_contains_centroid():
    f3 = next(f for f in g0.FACILITIES if f["id"] == "lin_zombie_facility_3")
    cx = sum(p[0] for p in f3["poly"]) / 4
    cy = sum(p[1] for p in f3["poly"]) / 4
    assert g0.point_in_poly(cx, cy, f3["poly"]) is True


# ─── row sanitation ─────────────────────────────────────────────────────────
def test_sanitize_row_refuses_junk():
    now_ms = 1_000_000_000_000
    assert g0.sanitize_row("123", row(), now_ms) is None            # not steam64
    assert g0.sanitize_row(SID, None, now_ms) is None               # not a dict
    assert g0.sanitize_row(SID, {"x": "a", "y": 1, "z": 1}, now_ms) is None
    bad = row(); bad["x"] = float("nan")
    assert g0.sanitize_row(SID, bad, now_ms) is None
    bad = row(); bad["z"] = float("inf")
    assert g0.sanitize_row(SID, bad, now_ms) is None
    assert g0.sanitize_row(SID, row(last_updated=(now_ms // 1000) - 60), now_ms) is None
    assert g0.sanitize_row(SID, row(last_updated=(now_ms // 1000) - 2), now_ms) is not None
    # a PRESENT stamp that cannot be read is never "fresh" (refuter finding)
    assert g0.sanitize_row(SID, row(last_updated="1e400"), now_ms) is None   # Overflow
    assert g0.sanitize_row(SID, row(last_updated=float("inf")), now_ms) is None
    assert g0.sanitize_row(SID, row(last_updated="abc"), now_ms) is None
    # missing vitals invalidate the row (never default to 0)
    nh = {k: v for k, v in row().items() if k != "health"}
    ng = {k: v for k, v in row().items() if k != "growth"}
    assert g0.sanitize_row(SID, nh, now_ms) is None
    assert g0.sanitize_row(SID, ng, now_ms) is None


def test_is_new_life():
    assert g0.is_new_life(None, {"dino": "A", "growth": 0.5}) is False
    assert g0.is_new_life({"dino": "A", "growth": 0.5}, {"dino": "B", "growth": 0.5}) is True
    assert g0.is_new_life({"dino": "A", "growth": 0.5}, {"dino": "A", "growth": 0.31}) is True
    assert g0.is_new_life({"dino": "A", "growth": 0.5}, {"dino": "A", "growth": 0.51}) is False
    assert g0.is_new_life({"dino": "A", "growth": float("nan")}, {"dino": "A", "growth": 0.5}) is False


# ─── the dwell machine ──────────────────────────────────────────────────────
def test_full_exposure_credits_25_and_banners(env):
    async def main():
        pos = {SID: row()}
        banners = await drive(env, [(0, pos), (10, pos), (20, pos), (32, pos)])
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 25
        assert "lin_zombie_facility_2" in doc["claims"]
        joined = "".join(banners)
        assert "ADVERTENCIA" in joined and "25%" in joined
        assert "MUTACION COMPLETA" not in joined
    run(main())


def test_reclaim_same_life_refused_and_silent(env):
    async def main():
        pos = {SID: row()}
        await drive(env, [(0, pos), (32, pos)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
        banners = await drive(env, [(50, {SID: row(**AWAY)}), (80, pos), (90, pos), (120, pos)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
        assert banners == []
    run(main())


def test_claim_again_next_life_allowed_by_signature(env):
    """Fallback path: no death line seen, but the respawn growth fell far
    below the stored signature — still a new life."""
    async def main():
        await drive(env, [(0, {SID: row(growth=0.6)}), (32, {SID: row(growth=0.6)})])
        fresh = {SID: row(growth=0.3)}
        cd = g0.COOLDOWN_S  # the re-claim also has to outlive the facility cooldown
        await drive(env, [(60, {SID: row(growth=0.6, **AWAY)}),
                          (cd + 100, fresh), (cd + 135, fresh)])
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 50                    # percent PERSISTED + new claim
        assert doc["life_sig"]["growth"] == 0.3
    run(main())


def test_death_mid_exposure_no_credit(env):
    async def main():
        alive = {SID: row()}
        dead = {SID: row(health=0.0)}
        await drive(env, [(0, alive), (10, alive), (20, dead), (32, dead), (40, dead)])
        assert SID not in env["db"].gen0_state.docs
        assert SID not in g0._dwell
    run(main())


def test_living_pawn_at_zero_health_never_resets_a_life(env):
    """THE REFUTED EXPLOIT: the mod publishes health<=0 rows for LIVING pawns
    (restore grace up to 120 s, entomb transients). Such rows must end the
    stay and nothing else — the same facility must NOT pay twice."""
    async def main():
        pos = {SID: row(growth=0.50)}
        await drive(env, [(0, pos), (32, pos)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
        zero = {SID: row(health=0.0, growth=0.50, **AWAY)}
        await drive(env, [(40, zero), (48, zero), (56, zero)])       # 16 s at 0 hp
        back = {SID: row(growth=0.52)}                                # same life, grew
        await drive(env, [(64, back), (72, back), (96, back), (104, back)])
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 25                                   # NOT paid twice
        assert "lin_zombie_facility_2" in doc["claims"]
    run(main())


def test_death_line_lets_low_growth_respawn_reclaim(env):
    """THE DENIAL BUG: claim at 0.30, grow to 0.90, die, respawn at 0.31. The
    signature frozen at the last credit cannot see that death; the mod's
    death line ratchets it to the growth-at-death, so the respawn is a new
    life and the same facility claims again."""
    async def main():
        await drive(env, [(0, {SID: row(growth=0.30)}), (32, {SID: row(growth=0.30)})])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
        await drive(env, [(60, {SID: row(growth=0.90, **AWAY)})])
        death_line(env, SID, growth=0.90)                              # evicted; no 0hp row seen
        await drive(env, [(68, {})])                                   # row gone from the feed
        assert env["db"].gen0_state.docs[SID]["life_sig"]["growth"] == 0.90
        assert "lin_zombie_facility_2" in env["db"].gen0_state.docs[SID]["claims"]  # not cleared yet
        fresh = {SID: row(growth=0.31)}
        cd = g0.COOLDOWN_S
        await drive(env, [(cd + 120, fresh), (cd + 152, fresh)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 50
    run(main())


def test_park_then_redeem_same_dino_is_one_life(env):
    """A park kill writes a death line too. Redeeming the SAME dino (same
    species, growth intact) must read as the same life: no re-farm."""
    async def main():
        await drive(env, [(0, {SID: row(growth=0.90)}), (32, {SID: row(growth=0.90)})])
        death_line(env, SID, growth=0.90)
        await drive(env, [(40, {})])
        redeemed = {SID: row(growth=0.90)}
        banners = await drive(env, [(100, redeemed), (140, redeemed)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
        assert banners == []
    run(main())


def test_death_line_never_mints_a_doc_and_ends_a_stay(env):
    async def main():
        await drive(env, [(0, {SID2: row(x=F4X, y=F4Y, z=F4Z)})])
        assert SID2 in g0._dwell
        death_line(env, SID2)
        await drive(env, [(8, {SID2: row(x=F4X, y=F4Y, z=F4Z)})])
        assert SID2 not in env["db"].gen0_state.docs        # no upsert by dying
    run(main())


def test_deathlog_tail_starts_at_end_and_consumes_only_new(env):
    # history present BEFORE the first read must never be replayed
    death_line(env, SID, growth=0.9)
    death_line(env, SID, growth=0.9)
    assert g0._read_new_deaths() == []
    death_line(env, SID, growth=0.8)
    got = g0._read_new_deaths()
    assert [d["growth"] for d in got] == [0.8]
    assert g0._read_new_deaths() == []                        # nothing new
    # partial line waits for its end; bad JSON and junk sids are skipped
    death_line(env, SID, raw='{"sid":"%s","dino":"A","gro' % SID)
    assert g0._read_new_deaths() == []
    death_line(env, SID, raw='wth":0.7}\nnot json\n{"sid":"123","growth":0.5}\n')
    got = g0._read_new_deaths()
    assert [d["growth"] for d in got] == [0.7]
    # truncation / rotation restarts from 0 without raising
    open(env["deathlog"], "w").close()
    assert g0._read_new_deaths() == []
    death_line(env, SID, growth=0.6)
    assert [d["growth"] for d in g0._read_new_deaths()] == [0.6]
    # missing file: contained
    g0.configure(env["db"], notify_path=env["notify"], deathlog_path=env["deathlog"] + ".nope")
    assert g0._read_new_deaths() == []


def test_logout_mid_exposure_resets_stay(env):
    async def main():
        pos = {SID: row()}
        await drive(env, [(0, pos), (10, pos)])
        await drive(env, [(30, {}), (45, {})])
        assert SID not in g0._dwell
        await drive(env, [(60, pos), (70, pos), (85, pos), (95, pos)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
    run(main())


def test_hysteresis_short_gap_keeps_the_stay(env):
    async def main():
        inside = {SID: row()}
        outside = {SID: row(**AWAY)}
        await drive(env, [(0, inside), (8, outside), (16, inside), (32, inside)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
    run(main())


def test_four_facilities_reach_100_and_complete_banner(env):
    async def main():
        pcts = []
        t = 0
        b = []
        for fac in g0.FACILITIES:
            cx = sum(p[0] for p in fac["poly"]) / len(fac["poly"])
            cy = sum(p[1] for p in fac["poly"]) / len(fac["poly"])
            cz = (fac["z_min"] + fac["z_max"]) / 2
            pos = {SID: row(x=cx, y=cy, z=cz)}
            b = await drive(env, [(t, pos), (t + 32, pos)])
            pcts.append(env["db"].gen0_state.docs[SID]["percent"])
            t += g0.COOLDOWN_S + 100        # outlive the between-facility window
            env["feed"]["positions"] = {}
            await g0._tracker_tick(now_mono=t - 50, now_ms=WALL0 + (t - 50) * 1000)
        assert pcts == [25, 50, 75, 100]
        assert env["db"].gen0_state.docs[SID]["complete_at"]
        assert "MUTACION COMPLETA" in "".join(b)
        # a fifth stay accrues nothing, stays silent, and reads the doc ONCE
        # for the whole visit (not once per tick — refuter finding)
        before = env["db"].gen0_state.find_calls
        pos = {SID: row()}
        b2 = await drive(env, [(t, pos), (t + 8, pos), (t + 16, pos), (t + 40, pos)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 100
        assert b2 == []
        assert env["db"].gen0_state.find_calls - before == 1
    run(main())


def test_mongo_fault_mid_credit_retries_exactly_once(env):
    async def main():
        env["db"].gen0_state.fail_next_update = 1
        pos = {SID: row()}
        await drive(env, [(0, pos), (32, pos)])
        assert SID not in env["db"].gen0_state.docs
        await drive(env, [(40, pos)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
        await drive(env, [(48, pos), (56, pos)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
    run(main())


def test_credit_race_against_existing_claim_refused(env):
    async def main():
        pos = {SID: row()}
        await drive(env, [(0, pos)])
        env["db"].gen0_state.docs[SID] = {
            "steam_id": SID, "percent": 25,
            "claims": {"lin_zombie_facility_2": "2026-08-21T00:00:00+00:00"},
            "life_sig": {"dino": "BP_Tyrannosaurus_C", "growth": 0.5},
            "complete_at": None}
        banners = await drive(env, [(32, pos)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
        assert all("25%" not in b for b in banners)
    run(main())


def test_two_players_independent(env):
    async def main():
        pos = {SID: row(), SID2: row(x=F4X, y=F4Y, z=F4Z, growth=0.8)}
        await drive(env, [(0, pos), (32, pos)])
        assert env["db"].gen0_state.docs[SID]["claims"].keys() == {"lin_zombie_facility_2"}
        assert env["db"].gen0_state.docs[SID2]["claims"].keys() == {"lin_zombie_facility_4"}
    run(main())


def test_walking_between_facilities_restarts_dwell(env):
    async def main():
        a = {SID: row()}
        b = {SID: row(x=F4X, y=F4Y, z=F4Z)}
        await drive(env, [(0, a), (20, b), (32, b)])
        assert SID not in env["db"].gen0_state.docs
        await drive(env, [(52, b)])
        assert env["db"].gen0_state.docs[SID]["claims"].keys() == {"lin_zombie_facility_4"}
    run(main())


def test_frozen_feed_no_progress(env):
    async def main():
        await drive(env, [(0, {SID: row()})])
        banners = await drive(env, [(15, None), (32, None)])
        assert banners == []
        assert SID not in env["db"].gen0_state.docs
    run(main())


def test_dwell_map_hard_bound_refuses_then_admits(env, monkeypatch):
    monkeypatch.setattr(g0, "DWELL_MAP_MAX", 2)

    async def main():
        three = {SID: row(), SID2: row(), SID3: row()}
        banners = await drive(env, [(0, three)])
        assert len(g0._dwell) == 2
        assert len([b for b in banners if "ADVERTENCIA" in b]) == 2   # the third is refused, silently
        # a slot frees (one player leaves long enough) -> the third is admitted
        await drive(env, [(20, {SID2: row(), SID3: row()})])   # SID absent
        await drive(env, [(40, {SID2: row(), SID3: row()})])   # SID pruned (>RESET_S)
        assert SID3 in g0._dwell and SID not in g0._dwell
    run(main())


# ─── the between-facility cooldown (owner 2026-08-21: "2 hours … then repeat")
def test_cooldown_left_ms_pure(monkeypatch):
    now = WALL0
    assert g0.cooldown_left_ms(None, now) == 0                 # first run: free
    assert g0.cooldown_left_ms("junk", now) == 0               # broken stamp: free
    assert g0.cooldown_left_ms(float("nan"), now) == 0
    assert g0.cooldown_left_ms(float("inf"), now) == 0
    assert g0.cooldown_left_ms(now - 1, now) == 0              # expired
    assert g0.cooldown_left_ms(now, now) == 0                  # boundary: exactly now = free
    assert g0.cooldown_left_ms(now + 5000, now) == 5000
    # clock-skew contract (the /validate refutation: clamping only the READING
    # left a far-future stamp re-clamping forever = permanent lockout in 2 h
    # slices): up to TWO windows out the reading clamps to one window; beyond
    # two windows the stamp is broken and reads FREE.
    win = g0.COOLDOWN_S * 1000
    assert g0.cooldown_left_ms(now + int(1.5 * win), now) == win
    assert g0.cooldown_left_ms(now + 2 * win, now) == win      # boundary: kept
    assert g0.cooldown_left_ms(now + 2 * win + 1, now) == 0    # broken: free
    assert g0.cooldown_left_ms(now + 10**12, now) == 0         # absurd: free
    # OverflowError class reads FREE, never raises (10**400 breaks float())
    assert g0.cooldown_left_ms(10**400, now) == 0
    assert g0.cooldown_left_ms(-(10**400), now) == 0
    monkeypatch.setattr(g0, "COOLDOWN_S", 0)
    assert g0.cooldown_left_ms(now + 5000, now) == 0           # knob off = no gate


def test_far_future_stamp_frees_instead_of_permanent_lockout(env):
    """END-TO-END for the refuted lockout: a stamp a year out (clock was ahead
    at credit time, then corrected) must NOT hold the player in endless 2 h
    slices — it reads broken/free and the next stay credits normally."""
    async def main():
        env["db"].gen0_state.docs[SID] = {
            "steam_id": SID, "percent": 25,
            "claims": {"lin_zombie_facility_2": "x"},
            "life_sig": {"dino": "BP_Tyrannosaurus_C", "growth": 0.5},
            "complete_at": None,
            "cooldown_until_ms": WALL0 + 365 * 24 * 3600 * 1000}
        pos4 = {SID: row(x=F4X, y=F4Y, z=F4Z)}
        await drive(env, [(0, pos4), (32, pos4)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 50   # freed, paid
    run(main())


def test_already_claimed_revisit_never_restamps_the_window(env):
    """Survived-mutant gap G-4: the already-claimed branch refreshes only the
    life-signature ratchet — it must never move cooldown_until_ms."""
    async def main():
        stamp = WALL0 + 123_000
        env["db"].gen0_state.docs[SID] = {
            "steam_id": SID, "percent": 25,
            "claims": {"lin_zombie_facility_2": "x"},
            "life_sig": {"dino": "BP_Tyrannosaurus_C", "growth": 0.5},
            "complete_at": None, "cooldown_until_ms": stamp}
        r = {"x": F2X, "y": F2Y, "z": F2Z, "health": 500.0, "growth": 0.6,
             "dino": "BP_Tyrannosaurus_C"}
        res = await g0._credit_facility(SID, F2, r, now_ms=WALL0 + 10_000_000)
        assert res is None
        assert env["db"].gen0_state.docs[SID]["cooldown_until_ms"] == stamp
    run(main())


def test_second_facility_refused_inside_window_then_fresh_stay_pays(env):
    async def main():
        pos2 = {SID: row()}
        pos4 = {SID: row(x=F4X, y=F4Y, z=F4Z)}
        await drive(env, [(0, pos2), (32, pos2)])
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 25
        assert doc["cooldown_until_ms"] == WALL0 + 32_000 + g0.COOLDOWN_S * 1000
        # facility 4, a full stay, still inside the window: NO credit; the
        # entry banner is the countdown, and the "stay to continue" pool
        # lines never fire (they would be a lie)
        b = await drive(env, [(100, pos4), (110, pos4), (140, pos4), (200, pos4)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
        joined = "".join(b)
        assert "recarga" in joined and "ADVERTENCIA" not in joined
        assert all(line not in joined for line in g0.BANNER_POOL)
        # survived-mutant gap G-3: pin the MINUTES the banner shows (cd left
        # at entry t=100 is 7,132,000 ms -> ceil = 119 min), not just the word
        assert "en 119 min" in joined
        # leave, come back AFTER the window: a fresh stay pays normally
        t = g0.COOLDOWN_S + 300
        b2 = await drive(env, [(220, {SID: row(**AWAY)}),
                               (t, pos4), (t + 32, pos4)])
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 50
        assert "50%" in "".join(b2) and "ADVERTENCIA" in "".join(b2)
        # and the NEW credit re-stamped the next window ("then repeat")
        assert doc["cooldown_until_ms"] == WALL0 + (t + 32) * 1000 + g0.COOLDOWN_S * 1000
    run(main())


def test_camping_through_expiry_pays_without_reentry(env):
    """The stay is HELD during the window, never latched dead: a player who
    walks in early and waits pays at the first tick past expiry."""
    async def main():
        pos2 = {SID: row()}
        pos4 = {SID: row(x=F4X, y=F4Y, z=F4Z)}
        await drive(env, [(0, pos2), (32, pos2)])              # window ends at 7232 s
        cd_end = 32 + g0.COOLDOWN_S
        b = await drive(env, [(100, pos4), (140, pos4),
                              (cd_end - 5, pos4),              # dwell done, still held
                              (cd_end + 5, pos4)])             # first tick past: pays
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 50
        assert "lin_zombie_facility_4" in doc["claims"]
        assert "50%" in "".join(b)
    run(main())


def test_death_and_new_life_never_clear_the_cooldown(env):
    """Die-to-skip must not work: a death line and a smaller respawn clear
    CLAIMS (new life) but the wall-clock window keeps refusing until it
    passes — then the same facility pays again in the new life."""
    async def main():
        await drive(env, [(0, {SID: row(growth=0.6)}), (32, {SID: row(growth=0.6)})])
        stamped = env["db"].gen0_state.docs[SID]["cooldown_until_ms"]
        death_line(env, SID, growth=0.6)
        await drive(env, [(40, {})])                           # death applies
        assert env["db"].gen0_state.docs[SID]["cooldown_until_ms"] == stamped
        fresh = {SID: row(growth=0.2)}                         # respawned smaller
        b = await drive(env, [(100, fresh), (140, fresh)])     # same facility, new life
        assert env["db"].gen0_state.docs[SID]["percent"] == 25  # refused: window holds
        assert "recarga" in "".join(b)
        t = g0.COOLDOWN_S + 300
        await drive(env, [(200, {SID: row(growth=0.2, **AWAY)}),
                          (t, fresh), (t + 32, fresh)])
        assert env["db"].gen0_state.docs[SID]["percent"] == 50  # new life re-claim lands
    run(main())


def test_credit_gate_itself_refuses_on_cooldown_read_only(env):
    """The AUTHORITATIVE belt inside _credit_facility (not just the tracker's
    in-memory hold): a doc still in its window refuses with the marker and
    writes NOTHING — a stale tracker state can never slip a credit through."""
    async def main():
        env["db"].gen0_state.docs[SID] = {
            "steam_id": SID, "percent": 25,
            "claims": {"lin_zombie_facility_2": "x"},
            "life_sig": {"dino": "BP_Tyrannosaurus_C", "growth": 0.5},
            "complete_at": None,
            "cooldown_until_ms": WALL0 + 600_000}
        writes = env["db"].gen0_state.update_calls
        r = {"x": F4X, "y": F4Y, "z": F4Z, "health": 500.0, "growth": 0.5,
             "dino": "BP_Tyrannosaurus_C"}
        res = await g0._credit_facility(SID, F4, r, now_ms=WALL0)
        assert res == {"on_cooldown": True, "left_ms": 600_000}
        assert env["db"].gen0_state.update_calls == writes          # read-only
        assert env["db"].gen0_state.docs[SID]["percent"] == 25
        # window passed: the same call pays and re-stamps
        res = await g0._credit_facility(SID, F4, r, now_ms=WALL0 + 600_001)
        assert res == {"percent": 50, "complete": False, "first": False}
        assert env["db"].gen0_state.docs[SID]["cooldown_until_ms"] == \
            WALL0 + 600_001 + g0.COOLDOWN_S * 1000
    run(main())


def test_cooldown_knob_zero_restores_back_to_back_credits(env, monkeypatch):
    monkeypatch.setattr(g0, "COOLDOWN_S", 0)

    async def main():
        pos2 = {SID: row()}
        pos4 = {SID: row(x=F4X, y=F4Y, z=F4Z)}
        await drive(env, [(0, pos2), (32, pos2), (50, pos4), (82, pos4)])
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 50                            # no gate at all
        assert doc.get("cooldown_until_ms") in (None, 0) or "cooldown_until_ms" not in doc
    run(main())


# ─── the endpoint ───────────────────────────────────────────────────────────
def _endpoint(user):
    async def dep():
        return user
    r = g0.build_router(dep)
    # by PATH, never by index — the router carries more than one route
    return next(rt.endpoint for rt in r.routes if rt.path.endswith("/gen0/contamination"))


def test_endpoint_shapes_and_503(env):
    from fastapi import HTTPException

    async def main():
        ep = _endpoint({"steam_id": ""})
        body = await ep(user={"steam_id": ""})
        assert body == {"percent": 0, "complete": False, "linked": False, "claims": {},
                        "facilities_total": 4, "cooldown_s": 0,
                        "cooldown_total_s": g0.COOLDOWN_S, "updated_at": None}
        env["db"].gen0_state.docs[SID] = {"steam_id": SID, "percent": 999, "claims": {"a": "t"},
                                          "life_sig": None, "complete_at": "x", "updated_at": "u"}
        body = await ep(user={"steam_id": SID})
        assert body["percent"] == 100 and body["complete"] is True and body["linked"] is True
        assert body["cooldown_s"] == 0 and body["cooldown_total_s"] == g0.COOLDOWN_S
        # a live cooldown surfaces as remaining seconds (ceil, never 0 early)
        import time as _time
        env["db"].gen0_state.docs[SID]["cooldown_until_ms"] = int(_time.time() * 1000) + 60_000
        body = await ep(user={"steam_id": SID})
        assert 1 <= body["cooldown_s"] <= 61
        # survived-mutant gap G-2: pin the CEIL — 60.9 s left must read 61,
        # never 60 (a floor shows 00:00:00 for the last 999 ms of every window
        # while the gate still refuses)
        env["db"].gen0_state.docs[SID]["cooldown_until_ms"] = int(_time.time() * 1000) + 60_900
        assert (await ep(user={"steam_id": SID}))["cooldown_s"] == 61
        env["db"].gen0_state.docs[SID]["cooldown_until_ms"] = "junk"   # broken stamp = free
        assert (await ep(user={"steam_id": SID}))["cooldown_s"] == 0
        # OverflowError-class stamp: 200 with cooldown_s 0, never a 500
        env["db"].gen0_state.docs[SID]["cooldown_until_ms"] = 10**400
        assert (await ep(user={"steam_id": SID}))["cooldown_s"] == 0
        env["db"].gen0_state.docs[SID]["percent"] = "abc"
        assert (await ep(user={"steam_id": SID}))["percent"] == 0
        assert (await ep(user={"steam_id": SID2}))["percent"] == 0      # first-run, no doc
        env["db"].gen0_state.fail_find = True
        with pytest.raises(HTTPException) as ei:
            await ep(user={"steam_id": SID})
        assert ei.value.status_code == 503                              # never a 500
    run(main())


def test_no_route_serves_the_facility_polygons(env):
    """Owner order 2026-08-21: the facilities came OFF the public map, so no
    route may serve the geometry — the removal is pinned, not assumed."""
    for route in g0.build_router(lambda: None).routes:
        assert "facilities" not in route.path
    assert not hasattr(g0, "facilities_public")
    assert not hasattr(g0, "facility_centroid")


# ─── notify queue writer ────────────────────────────────────────────────────
def test_notify_write_merges_concurrent_producer(env):
    other = '{"action":"prime_objective","steamid":"%s","label":"Dieta"}' % SID2
    with open(env["notify"], "w", encoding="utf-8") as f:
        f.write("[" + other + "]")
    assert g0.write_notify_blocks([g0._notify_block(SID, "hola")], path=env["notify"])
    content = open(env["notify"], encoding="utf-8").read()
    assert "prime_objective" in content and "notify_line" in content
    # every block still parseable the way the MOD drains it ({[^}]*})
    assert len(re.findall(r"\{[^}]*\}", content)) == 2


def test_notify_write_absent_file_and_failure_paths(env, tmp_path):
    assert g0.write_notify_blocks([g0._notify_block(SID, "x")], path=env["notify"])
    assert os.path.exists(env["notify"])
    assert g0.write_notify_blocks([], path=env["notify"]) is False
    assert g0.write_notify_blocks(['{"a":1}'], path=str(tmp_path / "nope" / "n.json")) is False
    d = tmp_path / "adir"
    d.mkdir()
    assert g0.write_notify_blocks(['{"a":1}'], path=str(d)) is False      # not a regular file
    assert d.is_dir()                                                       # and untouched


def test_notify_claimed_queue_unreadable_is_put_back(env, monkeypatch):
    """A failed read after the claim must RESTORE the mod's queue and write
    nothing — writing ours-only would delete the mod's pending banners."""
    original = '[{"action":"prime_complete","steamid":"%s"}]' % SID2
    with open(env["notify"], "w", encoding="utf-8") as f:
        f.write(original)
    real_open = builtins.open

    def flaky_open(path, *a, **k):
        if str(path).endswith(".web_gen0_staging") and (a and "r" in a[0] or k.get("mode", "").startswith("r")):
            raise OSError(5, "injected read fault")
        return real_open(path, *a, **k)

    monkeypatch.setattr(builtins, "open", flaky_open)
    assert g0.write_notify_blocks([g0._notify_block(SID, "x")], path=env["notify"]) is False
    monkeypatch.setattr(builtins, "open", real_open)
    assert open(env["notify"], encoding="utf-8").read() == original
    assert not os.path.exists(env["notify"] + ".web_gen0_staging")


def test_banner_text_cannot_break_the_mods_parser():
    s = g0.sanitize_banner_text('¡Peligro! {"x":1} \\ ñ\x00emoji☣ ' + "A" * 500)
    assert "{" not in s and "}" not in s and '"' not in s and "\\" not in s
    assert all(ord(c) < 0x7F for c in s)
    assert len(s) <= 240 and "\x00" not in s
    blk = g0._notify_block(SID, "hola")
    assert "first_ms" not in blk and "next_ms" not in blk and "retries" not in blk


def test_shipped_banner_lines_survive_shaping_verbatim():
    for line in (g0.BANNER_ENTRY, g0.BANNER_CREDIT.format(pct=50),
                 g0.BANNER_COMPLETE,
                 g0.BANNER_COOLDOWN.format(mins=120)) + g0.BANNER_POOL:
        assert g0.sanitize_banner_text(line) == line


# ─── the transformation lane (zombify at 100 %) ─────────────────────────────
def event_line(env, sid, event="on", reason="paint", raw=None):
    """Append one line to the fake gen0_zombie_events.log the way the mod does."""
    with open(env["eventlog"], "a", encoding="utf-8") as f:
        if raw is not None:
            f.write(raw)
        else:
            f.write(json.dumps({"event": event, "sid": sid, "reason": reason,
                                "ms": 1787290144000}) + "\n")


async def full_pass(env, t, positions):
    """One pass shaped exactly like gen0_tracker_loop: death-log tick, events
    tick, tracker tick, zombify sweep — returns every block of the batch that
    would ride the ONE notify write."""
    env["feed"]["positions"] = positions
    await g0._deathlog_tick()
    await g0._events_tick()
    out = await g0._tracker_tick(now_mono=t, now_ms=WALL0 + int(t * 1000))
    out.extend(await g0._zombify_sweep(now_mono=t))
    return out


def seed100(env, sid=SID, active=False, growth=0.5, dino="BP_Tyrannosaurus_C"):
    doc = {"steam_id": sid, "percent": 100,
           "claims": {f["id"]: "x" for f in g0.FACILITIES},
           "life_sig": {"dino": dino, "growth": growth},
           "complete_at": "2026-08-21T00:00:00+00:00", "updated_at": "x"}
    if active:
        doc["zombie_active"] = True
        doc["zombie_at"] = "x"
        doc["zombie_life_sig"] = {"dino": dino, "growth": growth}
    env["db"].gen0_state.docs[sid] = doc
    return doc


def test_action_block_is_closed_and_parser_safe():
    blk = g0._action_block("gen0_zombie", SID)
    assert blk == '{"action":"gen0_zombie","steamid":"%s"}' % SID
    assert "text" not in blk and "first_ms" not in blk and "retries" not in blk
    assert g0._action_block("notify_line", SID) == ""            # closed set
    assert g0._action_block("gen0_zombie", 'x"}]{7656') == \
        '{"action":"gen0_zombie","steamid":"7656"}'              # digits only


def test_completion_enqueues_the_transform_in_the_same_batch(env):
    async def main():
        seed100(env)
        env["db"].gen0_state.docs[SID]["percent"] = 75
        env["db"].gen0_state.docs[SID]["claims"].pop("lin_zombie_facility_2")
        env["db"].gen0_state.docs[SID]["complete_at"] = None
        pos = {SID: row()}                                        # inside F2
        b = []
        b += await full_pass(env, 0, pos)
        b += await full_pass(env, 32, pos)
        joined = "".join(b)
        assert env["db"].gen0_state.docs[SID]["percent"] == 100
        assert "MUTACION COMPLETA" in joined
        assert joined.count('"action":"gen0_zombie"') == 1        # once, same batch
        # the sweep in the SAME pass and the next pass inside the retry window
        # add nothing (the credit stamped the gate)
        b2 = await full_pass(env, 40, pos)
        assert '"action":"gen0_zombie"' not in "".join(b2)
    run(main())


def test_backfill_enqueues_only_while_seen_alive_and_respects_retry(env):
    async def main():
        seed100(env)                                              # the broken-rn cohort
        away = {SID: row(**AWAY)}                                 # online, outside
        b = await full_pass(env, 0, away)
        assert "".join(b).count('"action":"gen0_zombie"') == 1    # backfill fires
        assert "".join(await full_pass(env, 10, away)) == ""      # gate holds
        assert "".join(await full_pass(env, g0.ZOMBIFY_RETRY_S - 1, away)) == ""
        b3 = await full_pass(env, g0.ZOMBIFY_RETRY_S + 1, away)
        assert "".join(b3).count('"action":"gen0_zombie"') == 1   # gate reopens
        # gone from the feed -> nothing enqueues, dead row -> nothing enqueues
        assert "".join(await full_pass(env, 400, {})) == ""
        assert "".join(await full_pass(env, 800, {SID: row(**AWAY, health=0.0)})) == ""
    run(main())


def test_on_event_acks_and_stops_retries_and_is_idempotent(env):
    async def main():
        seed100(env)
        away = {SID: row(**AWAY)}
        assert '"gen0_zombie"' in "".join(await full_pass(env, 0, away))
        event_line(env, SID, "on")
        event_line(env, SID, "on", reason="reack")                # duplicate
        b = await full_pass(env, g0.ZOMBIFY_RETRY_S + 5, away)
        doc = env["db"].gen0_state.docs[SID]
        # the signature is the PAWN's (row: Tyrannosaurus @ 0.5), not the ratchet
        assert doc["zombie_active"] is True
        assert doc["zombie_life_sig"] == {"dino": "BP_Tyrannosaurus_C", "growth": 0.5}
        assert "".join(b) == ""                                   # acked: no more enqueues
        # an "on" for a sid with NO doc mints nothing (no upsert)
        event_line(env, SID3, "on")
        await g0._events_tick()
        assert SID3 not in env["db"].gen0_state.docs
    run(main())


def test_off_event_resets_exactly_once_and_noop_when_not_active(env):
    async def main():
        await g0._events_tick()                                   # prime the tail (starts at END)
        seed100(env, active=True)
        event_line(env, SID, "off", reason="death")
        event_line(env, SID, "off", reason="death")               # double delivery
        await g0._events_tick()
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 0 and doc["claims"] == {} and doc["complete_at"] is None
        assert doc["zombie_active"] is False and doc["zombie_reset_at"]
        stamp = doc["zombie_reset_at"]
        # not active any more: a third "off" is a no-op (exactly-once via filter)
        event_line(env, SID, "off")
        await g0._events_tick()
        assert env["db"].gen0_state.docs[SID]["zombie_reset_at"] == stamp
        # and an "off" for a doc that was never active changes nothing
        seed100(env, sid=SID2, active=False)
        event_line(env, SID2, "off")
        await g0._events_tick()
        assert env["db"].gen0_state.docs[SID2]["percent"] == 100
    run(main())


def test_dino_switch_reset_closes_missed_on_ack_and_preserves_cooldown(env):
    """A confirmed switch clears the exact inactive-100% missed-ack state,
    preserves anti-skip cooldown state, mints nothing, and is idempotent.
    The mod's off:park event is an independent fallback for the same boundary.
    """
    async def main():
        doc = seed100(env, active=False)
        doc["cooldown_until_ms"] = WALL0 + 123456
        g0._dwell[SID] = {"old": "pawn"}
        g0._last_alive[SID] = row(**AWAY)
        g0._zombify_next[SID] = 999.0
        assert await g0.reset_for_dino_switch(SID, "park_confirmed") is True
        clean = env["db"].gen0_state.docs[SID]
        assert clean["percent"] == 0 and clean["claims"] == {}
        assert clean["complete_at"] is None and clean["zombie_active"] is False
        assert clean["life_sig"] is None and clean["zombie_life_sig"] is None
        assert clean["cooldown_until_ms"] == WALL0 + 123456
        assert SID not in g0._dwell and SID not in g0._last_alive
        assert SID not in g0._zombify_next
        stamp = clean["dino_switch_reset_at"]
        writes = env["db"].gen0_state.update_calls
        assert await g0.reset_for_dino_switch(SID, "duplicate") is False
        assert env["db"].gen0_state.update_calls == writes
        assert env["db"].gen0_state.docs[SID]["dino_switch_reset_at"] == stamp

        # Progress below 100 belongs to the parked dinosaur too.
        env["db"].gen0_state.docs[SID2] = {
            "steam_id": SID2, "percent": 25, "claims": {"f1": "x"},
            "life_sig": {"dino": "BP_Carnotaurus_C", "growth": 0.4},
            "complete_at": None, "zombie_active": False,
        }
        assert await g0.reset_for_dino_switch(SID2) is True
        assert env["db"].gen0_state.docs[SID2]["percent"] == 0

        missing = "76561198000000777"
        assert await g0.reset_for_dino_switch(missing) is False
        assert missing not in env["db"].gen0_state.docs
        assert await g0.reset_for_dino_switch("not-a-steamid") is False

        # Reproduce the lost-on shape through the event backup path.
        await g0._events_tick()                                  # tail starts at END
        seed100(env, sid=SID3, active=False)
        event_line(env, SID3, "off", reason="park")
        await g0._events_tick()
        assert env["db"].gen0_state.docs[SID3]["percent"] == 0
    run(main())


def test_switch_reset_wins_over_an_inflight_old_dino_credit(env, monkeypatch):
    """Force the dangerous interleave: old-dino credit has begun, then the
    park reset arrives.  The bounded state lock must leave the final bar at 0,
    never resurrected to 100 by the stale credit write."""
    async def main():
        doc = seed100(env, active=False)
        doc["percent"] = 75
        doc["complete_at"] = None
        doc["claims"].pop(F2["id"])
        coll = env["db"].gen0_state
        real_update = coll.update_one
        update_entered = asyncio.Event()
        release_update = asyncio.Event()

        async def delayed_update(q, update, upsert=False):
            if (update.get("$set") or {}).get("percent") == 100:
                update_entered.set()
                await release_update.wait()
            return await real_update(q, update, upsert=upsert)

        monkeypatch.setattr(coll, "update_one", delayed_update)
        credit = asyncio.create_task(g0._credit_facility(SID, F2, row(), WALL0))
        await update_entered.wait()
        reset = asyncio.create_task(g0.reset_for_dino_switch(SID, "park_confirmed"))
        await asyncio.sleep(0)
        assert not reset.done()
        release_update.set()
        result, did_reset = await asyncio.gather(credit, reset)
        assert result["percent"] == 100 and did_reset is True
        assert env["db"].gen0_state.docs[SID]["percent"] == 0
    run(main())


def test_vault_switch_reset_helper_contains_backend_failure(env, monkeypatch):
    """A Mongo/reset failure cannot turn a confirmed park into a lost dino."""
    import vault

    async def boom(_sid, _reason):
        raise RuntimeError("injected reset failure")

    monkeypatch.setattr(g0, "reset_for_dino_switch", boom)
    assert run(vault._reset_gen0_after_dino_switch(SID, "park_confirmed")) is False


def test_death_line_is_not_a_zombie_reset_but_still_ratchets_the_claim_sig(env):
    """2026-08-22 park/relog survival: the mod writes a death line on its
    health<=0 latch, which a park kill, a safelog and a plain logout all reach
    (82/379 consecutive live lines were the same life continuing). A zombie
    who parks or relogs must keep the bar; only the mod's "off" (judged on the
    next living pawn) or the sweep's new-life belt resets it."""
    async def main():
        await g0._deathlog_tick()                                 # prime the tails (start at END)
        await g0._events_tick()
        seed100(env, active=True)
        death_line(env, SID, growth=0.9)
        await g0._deathlog_tick()
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 100 and doc["zombie_active"] is True   # NOT reset
        assert doc["life_sig"] == {"dino": "BP_Tyrannosaurus_C", "growth": 0.9}  # claim sig ratcheted
        # a death of a NON-zombie at 100 (mod not armed yet) resets nothing:
        # the transformation stays owed
        seed100(env, sid=SID2, active=False)
        death_line(env, SID2, growth=0.9)
        await g0._deathlog_tick()
        assert env["db"].gen0_state.docs[SID2]["percent"] == 100
        # the backstops still work: the mod's own "off" resets …
        event_line(env, SID, "off", reason="death")
        await g0._events_tick()
        assert env["db"].gen0_state.docs[SID]["percent"] == 0
        # … and so does the sweep's new-life belt (species change while alive)
        seed100(env, sid=SID3, active=True, dino="BP_Tyrannosaurus_C")
        await full_pass(env, 0, {SID3: row(**AWAY, dino="BP_Carnotaurus_C", growth=0.5)})
        assert env["db"].gen0_state.docs[SID3]["percent"] == 0
    run(main())


def test_on_event_lifts_a_reset_bar_back_to_100_only_when_below(env):
    """PARK SURVIVAL: the park's own "off" reset the doc to 0; the redeem's
    "on" (reason=restore) must put a walking zombie back at 100 + active +
    complete_at. An "on" for a doc already at 100 touches neither percent
    nor complete_at; an active doc is left alone; no doc = nothing minted."""
    async def main():
        await g0._events_tick()                                   # prime the tail (starts at END)
        env["db"].gen0_state.docs[SID] = {"steam_id": SID, "percent": 0, "claims": {},
                                          "life_sig": None, "complete_at": None,
                                          "zombie_active": False, "updated_at": "x"}
        event_line(env, SID, "on", reason="restore")
        await g0._events_tick()
        doc = env["db"].gen0_state.docs[SID]
        assert doc["zombie_active"] is True and doc["percent"] == 100
        assert doc["complete_at"]                                  # stamped now
        # already at 100 with its own stamp: untouched apart from the flag
        seed100(env, sid=SID2, active=False)
        stamp = env["db"].gen0_state.docs[SID2]["complete_at"]
        event_line(env, SID2, "on", reason="command")
        await g0._events_tick()
        d2 = env["db"].gen0_state.docs[SID2]
        assert d2["zombie_active"] is True and d2["percent"] == 100 and d2["complete_at"] == stamp
        # junk percent reads as 0 -> lifted, never a crash
        env["db"].gen0_state.docs[SID3] = {"steam_id": SID3, "percent": "junk", "claims": {},
                                           "life_sig": None, "complete_at": None,
                                           "zombie_active": False, "updated_at": "x"}
        event_line(env, SID3, "on", reason="paint")
        await g0._events_tick()
        assert env["db"].gen0_state.docs[SID3]["percent"] == 100
        # no doc -> nothing minted (no upsert), even for a restore
        event_line(env, "76561198000000777", "on", reason="restore")
        await g0._events_tick()
        assert "76561198000000777" not in env["db"].gen0_state.docs
    run(main())


def test_park_then_redeem_cycle_end_to_end(env):
    """The whole park story as the web sees it: zombie at 100 -> park (mod
    "off" reason=park + the park kill's death line) -> bar 0, inactive ->
    other life plays, farms nothing new -> redeem (mod "on" reason=restore)
    -> bar 100, active, sig = the redeemed pawn -> real death (mod "off"
    reason=death) -> bar 0, cycle free again. Exactly one reset per boundary."""
    async def main():
        await g0._events_tick()
        await g0._deathlog_tick()
        seed100(env, active=True, growth=0.85)
        # park: the mod parks the hold and the latch writes a death line
        event_line(env, SID, "off", reason="park")
        death_line(env, SID, growth=0.85)
        await full_pass(env, 0, {})
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 0 and doc["zombie_active"] is False and doc["claims"] == {}
        first_reset = doc["zombie_reset_at"]
        # another life walks meanwhile: no zombie, no reset churn
        await full_pass(env, 10, {SID: row(**AWAY, dino="BP_Carnotaurus_C", growth=0.3)})
        assert env["db"].gen0_state.docs[SID]["zombie_reset_at"] == first_reset
        # redeem: the mod re-holds and acks. The last pass still holds the
        # Carnotaurus row - a restore ack must NOT seed the signature from it
        # (the sweep would read the Tyrannosaurus as a species change and
        # reset the zombie it just re-armed); the redeemed pawn's first alive
        # sighting is captured instead.
        event_line(env, SID, "on", reason="restore")
        await full_pass(env, 20, {SID: row(**AWAY, dino="BP_Tyrannosaurus_C", growth=0.85)})
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 100 and doc["zombie_active"] is True
        assert doc["zombie_life_sig"] == {"dino": "BP_Tyrannosaurus_C", "growth": 0.85}
        # the zombie keeps growing: still the same life, still a zombie
        await full_pass(env, 30, {SID: row(**AWAY, dino="BP_Tyrannosaurus_C", growth=0.90)})
        assert env["db"].gen0_state.docs[SID]["zombie_active"] is True
        # a relog's death line changes nothing
        death_line(env, SID, growth=0.90)
        await full_pass(env, 40, {SID: row(**AWAY, dino="BP_Tyrannosaurus_C", growth=0.91)})
        assert env["db"].gen0_state.docs[SID]["percent"] == 100
        # the real death: the mod judged the respawn a new life
        event_line(env, SID, "off", reason="death")
        await full_pass(env, 50, {SID: row(**AWAY, dino="BP_Tyrannosaurus_C", growth=0.25)})
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 0 and doc["zombie_active"] is False
        assert doc["zombie_reset_at"] != first_reset
    run(main())


def test_new_life_belt_fires_on_fall_and_species_change_never_on_rise(env):
    async def main():
        seed100(env, active=True, growth=0.5)
        grown = {SID: row(**AWAY, growth=0.9)}                    # same life, grew
        await full_pass(env, 0, grown)
        assert env["db"].gen0_state.docs[SID]["zombie_active"] is True
        fallen = {SID: row(**AWAY, growth=0.3)}                   # respawned smaller
        await full_pass(env, 10, fallen)
        assert env["db"].gen0_state.docs[SID]["percent"] == 0     # reset fired
        seed100(env, sid=SID2, active=True, dino="BP_Tyrannosaurus_C")
        swapped = {SID2: row(**AWAY, dino="BP_Carnotaurus_C", growth=0.5)}
        await full_pass(env, 20, swapped)
        assert env["db"].gen0_state.docs[SID2]["percent"] == 0    # species change
    run(main())


def test_zombify_kill_switch_stops_enqueues_but_events_still_apply(env, monkeypatch):
    async def main():
        monkeypatch.setattr(g0, "ZOMBIFY_ON", False)
        seed100(env)
        away = {SID: row(**AWAY)}
        assert "".join(await full_pass(env, 0, away)) == ""       # no enqueue
        event_line(env, SID, "on")
        await g0._events_tick()
        assert env["db"].gen0_state.docs[SID]["zombie_active"] is True
        event_line(env, SID, "off")
        await g0._events_tick()
        assert env["db"].gen0_state.docs[SID]["percent"] == 0     # resets still land
    run(main())


def test_event_reader_rejects_junk_and_survives_files(env):
    async def main():
        event_line(env, "123", "on")                              # not steam64
        event_line(env, SID, "explode")                           # unknown event
        event_line(env, SID, raw='{"event":"on","sid":"%s"' % SID)   # partial line
        event_line(env, SID, raw="not json at all\n")
        await g0._events_tick()                                   # nothing applied
        assert "zombie_active" not in (env["db"].gen0_state.docs.get(SID) or {})
        # missing file = silent
        os.remove(env["eventlog"])
        await g0._events_tick()
        # recreated + truncation restarts from 0 (cursor beyond new size)
        event_line(env, SID, "on")
        seed100(env)
        await g0._events_tick()
        assert env["db"].gen0_state.docs[SID]["zombie_active"] is True
    run(main())


def test_sweep_survives_mongo_down_and_bad_docs(env):
    async def main():
        seed100(env)
        env["db"].gen0_state.fail_find = True
        b = await full_pass(env, 0, {SID: row(**AWAY)})           # loop shape survives
        assert '"gen0_zombie"' not in "".join(b)
        env["db"].gen0_state.fail_find = False
        env["db"].gen0_state.docs["badsid"] = {"steam_id": None, "percent": 100}
        b2 = await full_pass(env, g0.ZOMBIFY_RETRY_S + 1, {SID: row(**AWAY)})
        assert "".join(b2).count('"gen0_zombie"') == 1            # good doc still served
    run(main())


def test_transform_batch_is_one_notify_write(env):
    """The action block rides the SAME write_notify_blocks call as banners and
    the mod's regex parser sees every block."""
    seed100(env)
    blocks = [g0._notify_block(SID, "hola"), g0._action_block("gen0_zombie", SID)]
    assert g0.write_notify_blocks(blocks, path=env["notify"])
    content = open(env["notify"], encoding="utf-8").read()
    found = re.findall(r"\{[^}]*\}", content)
    assert len(found) == 2 and '"action":"gen0_zombie"' in content


def test_persisted_percent_backfill_captures_the_pawn_not_the_ratchet(env):
    """LIVE DEFECT 2026-08-21: a player whose 100 % persisted from an OLDER
    life (stored life_sig growth 0.9) is transformed in his CURRENT life
    (growth 0.3). The ack must freeze the pawn's signature — seeding it from
    the ratchet made the belt reset him one sweep after the mod painted him."""
    async def main():
        seed100(env, growth=0.9)                                  # ratchet: the old life
        now = {SID: row(**AWAY, growth=0.3)}                      # the life being transformed
        assert '"gen0_zombie"' in "".join(await full_pass(env, 0, now))
        event_line(env, SID, "on", reason="command")
        await full_pass(env, 10, now)                             # ack applies, sweep judges
        doc = env["db"].gen0_state.docs[SID]
        assert doc["zombie_active"] is True and doc["percent"] == 100
        assert doc["zombie_life_sig"] == {"dino": "BP_Tyrannosaurus_C", "growth": 0.3}
        for t in (20, 30, 200):                                   # stays a zombie, no reset
            await full_pass(env, t, now)
            assert env["db"].gen0_state.docs[SID]["zombie_active"] is True
        grown = {SID: row(**AWAY, growth=0.6)}                    # growth RISE never resets
        await full_pass(env, 210, grown)
        assert env["db"].gen0_state.docs[SID]["percent"] == 100
        fallen = {SID: row(**AWAY, growth=0.27)}                  # below captured 0.3 - 0.02
        await full_pass(env, 220, fallen)
        doc = env["db"].gen0_state.docs[SID]
        assert doc["percent"] == 0 and doc["zombie_active"] is False   # reset fired once
        stamp = doc["zombie_reset_at"]
        await full_pass(env, 230, fallen)
        assert env["db"].gen0_state.docs[SID]["zombie_reset_at"] == stamp
    run(main())


def test_on_without_a_known_row_captures_lazily_then_judges(env):
    """Ack arrives before any alive row is known (player mid-join, feed down):
    the signature stays None — the belt is NOT armed — and the first alive
    sighting captures it without a reset; a later species change resets."""
    async def main():
        await g0._events_tick()                                   # prime the tail (starts at END)
        seed100(env, growth=0.9)
        assert g0._last_alive == {}                               # nothing seen yet
        event_line(env, SID, "on")
        await g0._events_tick()
        doc = env["db"].gen0_state.docs[SID]
        assert doc["zombie_active"] is True and doc["zombie_life_sig"] is None
        low = {SID: row(**AWAY, growth=0.2)}                      # far below the ratchet
        await full_pass(env, 0, low)                              # capture pass: no judgement
        doc = env["db"].gen0_state.docs[SID]
        assert doc["zombie_active"] is True and doc["percent"] == 100
        assert doc["zombie_life_sig"] == {"dino": "BP_Tyrannosaurus_C", "growth": 0.2}
        await full_pass(env, 10, low)                             # same life: still a zombie
        assert env["db"].gen0_state.docs[SID]["zombie_active"] is True
        swapped = {SID: row(**AWAY, dino="BP_Carnotaurus_C", growth=0.2)}
        await full_pass(env, 20, swapped)                         # species change = new life
        assert env["db"].gen0_state.docs[SID]["percent"] == 0
    run(main())


def test_reack_never_rewrites_a_captured_signature(env):
    async def main():
        seed100(env, growth=0.9)
        await full_pass(env, 0, {SID: row(**AWAY, growth=0.3)})
        event_line(env, SID, "on")
        await full_pass(env, 10, {SID: row(**AWAY, growth=0.3)})
        event_line(env, SID, "on", reason="reack")               # pawn grew meanwhile
        await full_pass(env, 20, {SID: row(**AWAY, growth=0.5)})
        assert env["db"].gen0_state.docs[SID]["zombie_life_sig"]["growth"] == 0.3
    run(main())


def test_last_alive_is_pruned_to_the_pass_and_bounded(env, monkeypatch):
    async def main():
        both = {SID: row(**AWAY), SID2: row(**AWAY, growth=0.7)}
        await g0._tracker_tick(now_mono=0)
        await g0._tracker_tick(now_mono=0)                        # idempotent
        env["feed"]["positions"] = both
        await g0._tracker_tick(now_mono=1)
        assert set(g0._last_alive) == {SID, SID2}
        env["feed"]["positions"] = {SID2: row(**AWAY, growth=0.7),
                                    SID: row(**AWAY, health=0.0)}  # SID now at 0 hp
        await g0._tracker_tick(now_mono=2)
        assert set(g0._last_alive) == {SID2}                      # pruned to alive-this-pass
        env["feed"]["positions"] = None                           # feed down
        await g0._tracker_tick(now_mono=3)
        assert g0._last_alive == {}                               # nothing stale survives
        monkeypatch.setattr(g0, "DWELL_MAP_MAX", 1)
        env["feed"]["positions"] = both
        await g0._tracker_tick(now_mono=4)
        assert len(g0._last_alive) == 1                           # hard bound
    run(main())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
