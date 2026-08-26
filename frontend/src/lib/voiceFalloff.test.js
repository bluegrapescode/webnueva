/**
 * Proximity-voice falloff — curve + the speakers/authoritative protocol + the
 * poll loop, all driven for real against injected timers/fetch. The invariant
 * under test everywhere: an authoritative reply fades (and hard-cuts a far
 * speaker to 0); ANY non-authoritative / degraded reply leaves every voice at
 * FULL volume. A failure makes voices louder, never silent.
 */
import {
  volumeForDistance,
  clampPollMs,
  volumesFromPositions,
  VoiceFalloff,
  DEFAULT_AUDIBLE_RADIUS_M,
  FULL_VOLUME_FRACTION,
  NEAR_ZONE_MAX_M,
  resolveCut,
  DEFAULT_POLL_MS,
  MIN_POLL_MS,
  MAX_POLL_MS,
  ERROR_BACKOFF_MS,
  TOKEN_REMINT_MIN_MS,
} from "./voiceFalloff";

// eslint-disable-next-line global-require
const fs = require("fs");
// eslint-disable-next-line global-require
const path = require("path");
const readSrc = (...parts) => fs.readFileSync(path.join(__dirname, "..", ...parts), "utf8");

const R = DEFAULT_AUDIBLE_RADIUS_M; // 100 — the server range
const HOLD = R + 5;                 // 105 — the bridge's release band = the hard cut

describe("volumeForDistance", () => {
  test("full volume inside the near zone, silent at/after the cut", () => {
    expect(volumeForDistance(0, HOLD, { nearRadiusM: R })).toBe(1);
    expect(volumeForDistance(5, HOLD, { nearRadiusM: R })).toBe(1);
    expect(volumeForDistance(HOLD, HOLD)).toBe(0);
    expect(volumeForDistance(HOLD + 1, HOLD)).toBe(0);
    expect(volumeForDistance(415, HOLD)).toBe(0);
    expect(volumeForDistance(3000, HOLD)).toBe(0);
  });

  test("monotonically quieter with distance", () => {
    let prev = 1.0001;
    for (let d = 0; d <= HOLD; d += 0.5) {
      const v = volumeForDistance(d, HOLD, { nearRadiusM: R });
      expect(v).toBeLessThanOrEqual(prev);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
      prev = v;
    }
  });

  test("default curve keeps a mid-range player CLEARLY AUDIBLE (anti-muffle guard)", () => {
    // The complaint this curve exists to prevent is a nearby player sounding
    // "muffled". Anyone inside the ~20 m full-volume bubble is untouched, and a
    // player across the clearing at 30-50 m must still be comfortably loud.
    expect(volumeForDistance(10, HOLD, { nearRadiusM: R })).toBe(1);
    expect(volumeForDistance(20, HOLD, { nearRadiusM: R })).toBe(1);
    expect(volumeForDistance(30, HOLD, { nearRadiusM: R })).toBeGreaterThan(0.75);
    expect(volumeForDistance(50, HOLD, { nearRadiusM: R })).toBeGreaterThan(0.55);
    expect(volumeForDistance(70, HOLD, { nearRadiusM: R })).toBeGreaterThan(0.35);
    // still a real cue, not flat: near beats far, and the very edge is quiet.
    expect(volumeForDistance(70, HOLD, { nearRadiusM: R })).toBeLessThan(volumeForDistance(30, HOLD, { nearRadiusM: R }));
    expect(volumeForDistance(100, HOLD, { nearRadiusM: R })).toBeLessThan(0.15);
  });

  test("REGRESSION GUARD: widening the range must not widen the full-volume zone", () => {
    // The near zone is a FRACTION of the range, so a retune silently rescales it.
    // Pinning it in metres is what stops a wider range from turning into "everyone
    // is at 100% at once" — the exact problem earlier range cuts were made for.
    const nearZoneM = R * FULL_VOLUME_FRACTION;
    expect(nearZoneM).toBeLessThanOrEqual(25);
    expect(nearZoneM).toBeGreaterThanOrEqual(12);
    expect(volumeForDistance(nearZoneM, HOLD, { nearRadiusM: R })).toBe(1);
    expect(volumeForDistance(nearZoneM + 1, HOLD, { nearRadiusM: R })).toBeLessThan(1);
  });

  test("legacy 2-arg call still works (cut == radius)", () => {
    expect(volumeForDistance(40, 35)).toBe(0);
    expect(volumeForDistance(5, 35)).toBe(1);
  });

  test("steeper exponent is strictly quieter at mid-range", () => {
    const mid = 50; // beyond the full-volume bubble, where the curve actually acts
    const soft = volumeForDistance(mid, HOLD, { nearRadiusM: R, exponent: 0.8 });
    const sharp = volumeForDistance(mid, HOLD, { nearRadiusM: R, exponent: 2.5 });
    expect(sharp).toBeLessThan(soft);
  });

  test("a wider full-volume fraction lifts the mid value", () => {
    const narrow = volumeForDistance(15, HOLD, { nearRadiusM: R, fullFrac: 0.1 });
    const wide = volumeForDistance(15, HOLD, { nearRadiusM: R, fullFrac: 0.5 });
    expect(wide).toBeGreaterThan(narrow);
  });

  test("a shorter cut silences a speaker that a longer cut still fades", () => {
    expect(volumeForDistance(25, HOLD, { nearRadiusM: R })).toBeGreaterThan(0); // within the hold radius
    expect(volumeForDistance(25, 20, { nearRadiusM: R })).toBe(0); // cut at 20 m
  });

  test("garbage fails SAFE to full volume, never to silence", () => {
    expect(volumeForDistance(NaN, HOLD)).toBe(1);
    expect(volumeForDistance(undefined, HOLD)).toBe(1);
    expect(volumeForDistance(10, 0)).toBe(1);
    expect(volumeForDistance(10, -5)).toBe(1);
    expect(volumeForDistance(10, NaN)).toBe(1);
    expect(volumeForDistance(Infinity, HOLD)).toBe(1); // unknown, not "infinitely far"
  });
});

describe("resolveCut (one home for \"a personal range can only shorten\")", () => {
  test("no personal cap -> the bridge's hold radius", () => {
    expect(resolveCut(105, 0)).toBe(105);
    expect(resolveCut(105, undefined)).toBe(105);
    expect(resolveCut(105, NaN)).toBe(105);
    expect(resolveCut(105, -20)).toBe(105);
  });

  test("a personal cap only ever SHORTENS, never extends", () => {
    expect(resolveCut(105, 40)).toBe(40);
    expect(resolveCut(105, 200)).toBe(105);   // longer than the server routes
    expect(resolveCut(105, 105)).toBe(105);
    expect(resolveCut(35, 90)).toBe(35);      // after a range decrease
  });

  test("an unusable hold radius yields 0, which volumeForDistance fails SAFE on", () => {
    for (const bad of [0, -1, NaN, undefined, null, "abc"]) {
      expect(resolveCut(bad, 40)).toBe(0);
      expect(volumeForDistance(50, resolveCut(bad, 40))).toBe(1); // full volume, never silence
    }
  });
});

describe("the full-volume zone is bounded in METRES, not just by fraction", () => {
  test("a bigger range cannot widen the flat zone past the metre cap", () => {
    // The range is retunable on the box with no site deploy, up to 200 m, and no
    // test runs on that path - so the fraction alone is not the guard.
    for (const radius of [35, 100, 150, 200]) {
      const hold = radius + 5;
      const nearEdge = Math.min(radius * FULL_VOLUME_FRACTION, NEAR_ZONE_MAX_M);
      expect(nearEdge).toBeLessThanOrEqual(NEAR_ZONE_MAX_M);
      expect(volumeForDistance(nearEdge, hold, { nearRadiusM: radius })).toBe(1);
      expect(volumeForDistance(NEAR_ZONE_MAX_M + 1, hold, { nearRadiusM: radius })).toBeLessThan(1);
    }
  });
});

describe("clampPollMs", () => {
  test("defaults and clamps into range", () => {
    expect(clampPollMs(null)).toBe(DEFAULT_POLL_MS);
    expect(clampPollMs(0)).toBe(DEFAULT_POLL_MS);
    expect(clampPollMs("nope")).toBe(DEFAULT_POLL_MS);
    expect(clampPollMs(10)).toBe(MIN_POLL_MS);
    expect(clampPollMs(9_999_999)).toBe(MAX_POLL_MS);
    expect(clampPollMs(1500)).toBe(1500);
  });
});

const auth = (speakers, extra = {}) => ({ authoritative: true, audible_radius_m: R, hold_radius_m: HOLD, speakers, ...extra });

describe("volumesFromPositions (speakers protocol)", () => {
  test("PROVES THE LEAK CLOSES: a far-away subscribed speaker ends at volume 0", () => {
    expect(volumesFromPositions(auth({ B: { distance_m: 415 } }), ["B"]).get("B")).toBe(0);
    expect(volumesFromPositions(auth({ B: { distance_m: 3000 } }), ["B"]).get("B")).toBe(0);
  });

  test("mid faded, far cut, missing-position full", () => {
    const v = volumesFromPositions(auth({ A: { distance_m: 28 }, B: { distance_m: 415 }, C: { distance_m: null } }), ["A", "B", "C"]);
    expect(v.get("A")).toBeGreaterThan(0); // 28 m — audible but reduced
    expect(v.get("A")).toBeLessThan(1);
    expect(v.get("B")).toBe(0);            // 415 m — hard cut
    expect(v.get("C")).toBe(1);            // subscribed, in room, position missing this frame
  });

  test("NEGATIVE CONTROL: a non-authoritative reply leaves EVERY id at full volume", () => {
    for (const p of [{ authoritative: false }, { authoritative: false, speakers: { B: { distance_m: 415 } } }, {}, null, { speakers: null }]) {
      const v = volumesFromPositions(p, ["A", "B"]);
      expect(v.get("A")).toBe(1);
      expect(v.get("B")).toBe(1);
    }
  });

  test("absence grace: first absent poll keeps full, second silences, reappear re-fades", () => {
    const streak = new Map();
    const opts = { absentStreak: streak };
    // D is held but not in the speakers map
    expect(volumesFromPositions(auth({}), ["D"], opts).get("D")).toBe(1);   // 1st absent
    expect(volumesFromPositions(auth({}), ["D"], opts).get("D")).toBe(0);   // 2nd absent -> silence
    const back = volumesFromPositions(auth({ D: { distance_m: 10 } }), ["D"], opts);
    expect(back.get("D")).toBeGreaterThan(0);   // reappeared -> faded
    expect(streak.get("D")).toBe(0);            // streak cleared
  });

  test("absence streak is pruned when the id is no longer held", () => {
    const streak = new Map();
    volumesFromPositions(auth({}), ["D"], { absentStreak: streak });
    expect(streak.has("D")).toBe(true);
    volumesFromPositions(auth({ A: { distance_m: 5 } }), ["A"], { absentStreak: streak });
    expect(streak.has("D")).toBe(false);
  });

  test("the user's max-hearing setting can only shorten the range", () => {
    const full = volumesFromPositions(auth({ B: { distance_m: 25 } }), ["B"]);
    const capped = volumesFromPositions(auth({ B: { distance_m: 25 } }), ["B"], { maxHearingM: 20 });
    expect(full.get("B")).toBeGreaterThan(0); // 25 m is well within the server range
    expect(capped.get("B")).toBe(0);          // this player chose to stop at 20 m
  });

  test("volumes are always finite and within 0..1", () => {
    const v = volumesFromPositions(auth({ A: { distance_m: "NaN" }, B: { distance_m: -5 }, C: { distance_m: 1 } }), ["A", "B", "C"]);
    for (const [, x] of v) { expect(Number.isFinite(x)).toBe(true); expect(x).toBeGreaterThanOrEqual(0); expect(x).toBeLessThanOrEqual(1); }
  });
});

/** Manual clock + timer queue + scripted fetch. */
function harness(opts = {}) {
  const state = {
    now: 0, timers: [], volumes: [], distanceReports: [],
    identities: opts.identities === undefined ? ["A"] : opts.identities,
    token: opts.token === undefined ? "tok" : opts.token,
    fetchCalls: [], remints: 0, logs: [],
    curveConfig: opts.curveConfig,
  };
  const deps = {
    getToken: () => state.token,
    remintToken: async () => { state.remints += 1; state.token = "tok2"; return "tok2"; },
    getIdentities: () => state.identities,
    applyVolume: (id, v) => { state.volumes.push([id, v]); },
    getCurveConfig: () => state.curveConfig,
    reportDistances: (m, r) => { state.distanceReports.push([m, r]); },
    fetchImpl: async (url, init) => {
      state.fetchCalls.push({ url, init });
      const r = opts.respond(state.fetchCalls.length, init);
      if (r instanceof Error) throw r;
      return r;
    },
    setTimer: (fn, ms) => { const h = { fn, at: state.now + ms, ms }; state.timers.push(h); return h; },
    clearTimer: (h) => { state.timers = state.timers.filter((t) => t !== h); },
    now: () => state.now,
    onLog: (msg, extra) => state.logs.push([msg, extra]),
  };
  const engine = new VoiceFalloff(deps);
  state.flush = async () => { const due = state.timers.slice(); state.timers = []; for (const t of due) await t.fn(); };
  state.lastDelay = () => (state.timers.length ? state.timers[state.timers.length - 1].ms : null);
  return { engine, state };
}

const ok = (body) => ({ status: 200, json: async () => body });

describe("VoiceFalloff loop", () => {
  test("applies per-speaker curve from an authoritative payload and reports distances", async () => {
    const { engine, state } = harness({
      identities: ["A", "B"],
      respond: () => ok(auth({ A: { distance_m: 5 }, B: { distance_m: 415 } }, { poll_ms: 1500 })),
    });
    engine.start();
    await state.flush();
    expect(state.fetchCalls[0].url).toBe("/positions");
    expect(state.fetchCalls[0].init.headers.Authorization).toBe("Bearer tok");
    const map = new Map(state.volumes);
    expect(map.get("A")).toBe(1);     // 5 m near
    expect(map.get("B")).toBe(0);     // 415 m leaked -> cut
    // distances handed to the UI, with the hold radius
    const [dm, holdR] = state.distanceReports[state.distanceReports.length - 1];
    expect(dm.get("A")).toBe(5);
    expect(dm.get("B")).toBe(415);
    expect(holdR).toBe(HOLD);
    expect(state.lastDelay()).toBe(1500);
    engine.stop();
  });

  test("getCurveConfig feeds the user's max-hearing so a mid speaker is cut", async () => {
    const { engine, state } = harness({
      curveConfig: { exponent: 1.4, fullFrac: 0.2, maxHearingM: 15 },
      identities: ["B"],
      respond: () => ok(auth({ B: { distance_m: 25 } })),
    });
    engine.start();
    await state.flush();
    expect(new Map(state.volumes).get("B")).toBe(0); // cut at 15 m
    engine.stop();
  });

  test("a NON-authoritative 200 leaves everyone at full volume", async () => {
    const { engine, state } = harness({ respond: () => ok({ authoritative: false }) });
    engine.start();
    await state.flush();
    expect(state.volumes).toEqual([["A", 1]]);
    engine.stop();
  });

  test("a dead bridge, 404/429/500, and no-token all fail safe to full volume", async () => {
    for (const respond of [() => new Error("down"), () => ({ status: 404, json: async () => ({}) }), () => ({ status: 500, json: async () => ({}) })]) {
      const { engine, state } = harness({ respond });
      engine.start();
      await state.flush();
      expect(state.volumes).toEqual([["A", 1]]);
      expect(state.lastDelay()).toBe(ERROR_BACKOFF_MS);
      engine.stop();
    }
    const { engine, state } = harness({ token: null, respond: () => ok(auth({})) });
    engine.start();
    await state.flush();
    expect(state.fetchCalls).toHaveLength(0);
    expect(state.volumes).toEqual([["A", 1]]);
    engine.stop();
  });

  test("an expired token re-mints ONCE per window", async () => {
    const { engine, state } = harness({ respond: () => ({ status: 401, json: async () => ({}) }) });
    engine.start();
    await state.flush();
    expect(state.remints).toBe(1);
    await state.flush();
    expect(state.remints).toBe(1);
    state.now += TOKEN_REMINT_MIN_MS + 1;
    await state.flush();
    expect(state.remints).toBe(2);
    engine.stop();
  });

  test("hearing nobody never polls", async () => {
    const { engine, state } = harness({ identities: [], respond: () => ok(auth({})) });
    engine.start();
    await state.flush();
    expect(state.fetchCalls).toHaveLength(0);
    expect(state.lastDelay()).toBe(DEFAULT_POLL_MS);
    engine.stop();
  });

  test("stop() ends the loop for good", async () => {
    const { engine, state } = harness({ respond: () => ok(auth({})) });
    engine.start();
    await state.flush();
    const n = state.fetchCalls.length;
    engine.stop();
    await state.flush();
    expect(state.fetchCalls).toHaveLength(n);
    expect(state.timers).toHaveLength(0);
  });

  test("poke() re-polls at once but cannot be spammed", async () => {
    const { engine, state } = harness({ respond: () => ok(auth({})) });
    engine.start();
    await state.flush();
    state.now += MIN_POLL_MS + 1;
    engine.poke();
    expect(state.lastDelay()).toBe(0);
    await state.flush();
    engine.poke();
    expect(state.lastDelay()).not.toBe(0);
    engine.stop();
  });

  test("an applyVolume that throws never breaks the loop", async () => {
    const { engine, state } = harness({ respond: () => ok(auth({ A: { distance_m: 5 } })) });
    engine.deps.applyVolume = () => { throw new Error("element detached"); };
    engine.start();
    await expect(state.flush()).resolves.toBeUndefined();
    expect(state.timers.length).toBeGreaterThan(0);
    engine.stop();
  });

  test("the falloff is actually WIRED into the voice session (autoSubscribe:false + plumbing)", () => {
    const src = readSrc("context", "VoiceContext.jsx");
    // sole-subscriber: the client must connect subscribed to nobody, in BOTH branches
    expect(src).toContain("autoSubscribe: false, rtcConfig:");
    expect(src).toContain("{ autoSubscribe: false }");
    // the engine is fed the live token, track list, curve config and distance sink
    expect(src).toContain("import { VoiceFalloff, volumeForDistance, resolveCut, DEFAULT_AUDIBLE_RADIUS_M, DEFAULT_HOLD_RADIUS_M }");
    // The curve is configured against the AUDIBLE radius (the owner's range, and
    // the top of the player's own slider), NOT the hold radius — feeding it the
    // hold radius would offer a range a few metres wider than the owner ever set.
    expect(src).toContain("getCurveConfig: () => curveConfig(settingsRef.current, audibleRadiusRef.current)");
    expect(src).toContain("reportDistances:");
    // The roster's distances are a PUBLISHED COPY of the poll's map, cleared with
    // the session. Routing and gain keep reading the ref, never this copy — a
    // display value must never become an input to who you hear.
    expect(src).toContain("publishDistances(lastDistanceRef.current)");
    expect(src).toMatch(/lastDistanceRef\.current\.clear\(\);[\s\S]{0,400}setDistances\(\{\}\)/);
    // Both paths resolve the hard cut through the SAME exported helper, so "can
    // only ever shorten" has one home and is unit-tested rather than duplicated.
    expect(src).toContain("resolveCut(holdRadiusRef.current, cfg.maxHearingM)");
    // the hard cut is seeded from the HOLD default, never the audible one
    expect(src).toContain("useRef(DEFAULT_HOLD_RADIUS_M)");
    expect(src).toMatch(/TrackSubscribed,\s*\(track,\s*publication,\s*participant\)/);
    expect(src).toContain("attachAudio(track, participant && participant.identity)");
    expect(src).toContain("ensureFalloff().poke()");
    // settings + setters exposed to the UI
    expect(src).toContain("setMaster, setExponent, setHearingM, setSpeakerVolume, toggleSpeakerMute, resetSettings");
    // microphone lane: PTT is fail-safe (released on blur/hide) and the mic
    // controls + device list reach the UI
    expect(src).toContain('window.addEventListener("blur", release)');
    expect(src).toContain("audioCaptureOptions(s)");
    expect(src).toContain("setMicMode, setPttKey, setNoiseSuppression, setInputDevice, setOutputDevice");
    expect(src).toContain('s.micMode === "ptt" ? transmittingRef.current : !mutedRef.current');
  });

  test("the range control on the voice page is in METRES and cannot exceed the server", () => {
    // No React test renderer in this repo, so the page contract is guarded at
    // source level. What must hold: the slider tops out at the server's range,
    // it is labelled in metres, and dragging it to the top stores 0 = "follow the
    // server" so a later retune lifts that player with it instead of pinning them.
    const src = readSrc("pages", "ProximityVoice.jsx");
    // The model is built by the shared helper. (It used to be built only while
    // the settings drawer was open; the radio panel shows the dials always, so
    // the needle asserts the CALL, not the old lazy spelling.)
    expect(src).toContain("hearingSliderModel(settings, serverRadiusM)");
    expect(src).toContain("value={hearing.value} min={hearing.min} max={hearing.max}");
    expect(src).toContain("display={hearing.display}");
    expect(src).toContain("onChange={(v) => setHearingM(hearing.toStore(v))}");
    // The page derives NOTHING about the range itself - no hardcoded fallback and
    // no second sanitising pass that could disagree with the helper's.
    expect(src).not.toMatch(/serverRadiusM\)\s*\|\|\s*\d/);
    expect(src).not.toContain("DEFAULT_AUDIBLE_RADIUS_M");
  });
});
