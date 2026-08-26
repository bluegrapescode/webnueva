/**
 * Player voice settings — the pure composition math + persistence validator.
 * The governing guarantees under test: default settings change NOTHING
 * (composeGain(curve) === curve), a mute always wins to 0, the applied gain can
 * never exceed unity in v1 (the boost region is not yet wired), and a corrupt
 * localStorage entry can never push NaN/out-of-range into a track volume.
 */
import {
  normalizeSettings, loadSettings, saveSettings, composeGain, curveConfig,
  withSpeaker, DEFAULT_SETTINGS, MAX_APPLIED_GAIN, PERSPEAKER_CAP, LS_KEY,
  audioCaptureOptions, DEFAULT_PTT_KEY, migrateV2, LEGACY_LS_KEY_V2,
  V2_BASIS_RADIUS_M, HEARING_MIN_M, HEARING_MAX_M, hearingSliderModel,
  effectiveFullFrac,
} from "./voiceSettings";
import { FULL_VOLUME_FRACTION } from "./voiceFalloff";

/** In-memory localStorage double: seed it with keys, read what was written. */
const memStore = (seed) => ({
  data: { ...(seed || {}) },
  getItem(k) { return this.data[k] === undefined ? null : this.data[k]; },
  setItem(k, v) { this.data[k] = v; },
});

describe("normalizeSettings / loadSettings", () => {
  test("clamps out-of-range, coerces types, prunes default speakers", () => {
    const s = normalizeSettings({
      master: 9, exponent: 100, hearingM: -1, fullFrac: 5,
      speakers: {
        keep: { volume: 0.5, muted: false },
        mutedOne: { volume: 1, muted: true },
        pruned: { volume: 1, muted: false }, // == default -> dropped
        junk: 42,
      },
    });
    expect(s.master).toBe(1.5);        // clamped to store max
    expect(s.exponent).toBe(3.0);      // clamped to MAX_FALLOFF_EXPONENT
    expect(s.hearingM).toBe(0);        // <= 0 means "follow the server range"
    expect(s.fullFrac).toBe(0.6);          // clamped to FULL_FRAC_MAX exactly
    expect(s.speakers.keep).toEqual({ volume: 0.5, muted: false });
    expect(s.speakers.mutedOne).toEqual({ volume: 1, muted: true });
    expect(s.speakers.pruned).toBeUndefined();
    expect(s.speakers.junk).toBeUndefined();
  });

  test("caps the per-speaker map size", () => {
    const speakers = {};
    for (let i = 0; i < PERSPEAKER_CAP + 50; i++) speakers[`p${i}`] = { volume: 0.5, muted: false };
    const s = normalizeSettings({ speakers });
    // toBe, not toBeLessThanOrEqual: the loose form also passes if sanitize
    // returns {} and so never proves the cap KEEPS anything.
    expect(Object.keys(s.speakers).length).toBe(PERSPEAKER_CAP);
  });

  test("corrupt JSON in storage -> defaults, never throws", () => {
    const store = { getItem: () => "{not json", setItem: () => {} };
    expect(loadSettings(store)).toEqual(normalizeSettings(null));
    const missing = { getItem: () => null, setItem: () => {} };
    expect(loadSettings(missing)).toEqual(normalizeSettings(null));
  });

  test("save then load round-trips through a fake store", () => {
    const store = memStore();
    const s = normalizeSettings({ master: 0.5, speakers: { z: { volume: 0.25, muted: false } } });
    saveSettings(s, store);
    expect(loadSettings(store)).toEqual(s);
  });

  test("a throwing storage never breaks load or save", () => {
    const store = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(loadSettings(store)).toEqual(normalizeSettings(null));
    expect(() => saveSettings(DEFAULT_SETTINGS, store)).not.toThrow();
  });
});

describe("microphone settings", () => {
  test("defaults are today's behavior (opt-in, nothing changes out of the box)", () => {
    expect(DEFAULT_SETTINGS.micMode).toBe("open");
    expect(DEFAULT_SETTINGS.pttKey).toBe(DEFAULT_PTT_KEY);
    expect(DEFAULT_SETTINGS.noiseSuppression).toBe(true);
    expect(DEFAULT_SETTINGS.inputDeviceId).toBe("");
    expect(DEFAULT_SETTINGS.outputDeviceId).toBe("");
  });

  test("normalizeSettings clamps mic fields and rejects junk", () => {
    const s = normalizeSettings({ micMode: "weird", pttKey: "", noiseSuppression: "yes", inputDeviceId: 5, outputDeviceId: "x".repeat(400) });
    expect(s.micMode).toBe("open");        // unknown -> open
    expect(s.pttKey).toBe(DEFAULT_PTT_KEY); // empty -> default
    expect(s.noiseSuppression).toBe(true);  // non-bool -> default true
    expect(s.inputDeviceId).toBe("");       // non-string -> ""
    expect(s.outputDeviceId).toBe("");      // too long -> ""
  });

  test("valid mic fields pass through", () => {
    const s = normalizeSettings({ micMode: "ptt", pttKey: "KeyV", noiseSuppression: false, inputDeviceId: "mic-1", outputDeviceId: "spk-2" });
    expect(s).toMatchObject({ micMode: "ptt", pttKey: "KeyV", noiseSuppression: false, inputDeviceId: "mic-1", outputDeviceId: "spk-2" });
  });

  test("audioCaptureOptions keeps echo+AGC on, exposes noise + a chosen device only", () => {
    const on = audioCaptureOptions(normalizeSettings({ noiseSuppression: true }));
    expect(on).toMatchObject({ noiseSuppression: true, echoCancellation: true, autoGainControl: true });
    expect("deviceId" in on).toBe(false); // blank device omitted
    const off = audioCaptureOptions(normalizeSettings({ noiseSuppression: false, inputDeviceId: "mic-1" }));
    expect(off.noiseSuppression).toBe(false);
    expect(off.echoCancellation).toBe(true);
    expect(off.deviceId).toBe("mic-1");
  });
});

describe("composeGain", () => {
  test("EQUIVALENCE GUARD: default settings change nothing", () => {
    for (const curve of [0, 0.1, 0.37, 0.5, 1]) {
      expect(composeGain(curve, DEFAULT_SETTINGS, undefined)).toBeCloseTo(curve, 10);
      expect(composeGain(curve, DEFAULT_SETTINGS, "someid")).toBeCloseTo(curve, 10);
    }
  });

  test("a per-speaker mute always wins to 0", () => {
    const s = normalizeSettings({ master: 1, speakers: { X: { volume: 1, muted: true } } });
    expect(composeGain(1, s, "X")).toBe(0);
    expect(composeGain(0.9, s, "X")).toBe(0);
  });

  test("master * per-speaker * curve, composed", () => {
    const s = normalizeSettings({ master: 0.5, speakers: { X: { volume: 0.5, muted: false } } });
    expect(composeGain(0.8, s, "X")).toBeCloseTo(0.2, 10);
  });

  test("NEGATIVE CONTROL: master at max never pushes a near speaker over 100%", () => {
    const s = normalizeSettings({ master: 1.5 }); // stored boost
    expect(composeGain(1, s, "near")).toBe(MAX_APPLIED_GAIN); // capped at unity in v1
    expect(composeGain(1, s, "near")).toBeLessThanOrEqual(1);
  });

  test("junk curve/settings never yield NaN", () => {
    expect(Number.isFinite(composeGain(NaN, DEFAULT_SETTINGS, "x"))).toBe(true);
    expect(Number.isFinite(composeGain(0.5, null, "x"))).toBe(true);
    expect(Number.isFinite(composeGain(undefined, DEFAULT_SETTINGS, undefined))).toBe(true);
  });
});

describe("hearing range (absolute metres)", () => {
  test("the default follows the server range, whatever it is", () => {
    expect(DEFAULT_SETTINGS.hearingM).toBe(0);
    // 0 = no client cap, so the bridge's own range/hold radius is the only cut.
    expect(curveConfig(DEFAULT_SETTINGS, 100).maxHearingM).toBe(0);
    expect(curveConfig(DEFAULT_SETTINGS, 35).maxHearingM).toBe(0);
  });

  test("a chosen range is the METRES chosen, and does NOT rescale with the server", () => {
    const s = normalizeSettings({ hearingM: 40, exponent: 2 });
    // THE v2 BUG THIS REPLACES: as a fraction, 40-of-100 became 14 m at a 35 m
    // range and 80 m at 200 m. The metres the player picked now survive a retune.
    expect(curveConfig(s, 100).maxHearingM).toBe(40);
    expect(curveConfig(s, 200).maxHearingM).toBe(40);
    expect(curveConfig(s, 100).exponent).toBe(2);
  });

  test("it can only ever SHORTEN: a range past the server's is capped to it", () => {
    const s = normalizeSettings({ hearingM: 180 });
    expect(curveConfig(s, 100).maxHearingM).toBe(100);
    expect(curveConfig(s, 35).maxHearingM).toBe(35);
  });

  test("an unknown radius keeps an explicit choice and never invents a cap", () => {
    expect(curveConfig(DEFAULT_SETTINGS, 0).maxHearingM).toBe(0);
    expect(curveConfig(DEFAULT_SETTINGS, undefined).maxHearingM).toBe(0);
    expect(curveConfig(normalizeSettings({ hearingM: 30 }), 0).maxHearingM).toBe(30);
  });

  test("junk and out-of-range values clamp, never NaN", () => {
    for (const junk of [NaN, Infinity, -Infinity, "abc", null, undefined, {}, -5, 0]) {
      expect(normalizeSettings({ hearingM: junk }).hearingM).toBe(0);
    }
    expect(normalizeSettings({ hearingM: 1 }).hearingM).toBe(HEARING_MIN_M);
    expect(normalizeSettings({ hearingM: 9999 }).hearingM).toBe(HEARING_MAX_M);
    expect(normalizeSettings({ hearingM: 42.6 }).hearingM).toBe(43);
  });
});

describe("hearingSliderModel (what the player actually sees and drags)", () => {
  test("an untouched player sits at the server's full range", () => {
    const m = hearingSliderModel(DEFAULT_SETTINGS, 100);
    expect(m.value).toBe(100);
    expect(m.max).toBe(100);
    expect(m.min).toBe(HEARING_MIN_M);
    expect(m.display).toBe("100 m");
  });

  test("the slider can never offer more than the server routes", () => {
    expect(hearingSliderModel(normalizeSettings({ hearingM: 200 }), 100).max).toBe(100);
    expect(hearingSliderModel(normalizeSettings({ hearingM: 200 }), 100).value).toBe(100);
    // and if the owner ever lowers the range, an old longer choice is capped
    expect(hearingSliderModel(normalizeSettings({ hearingM: 90 }), 35).value).toBe(35);
  });

  test("a chosen range shows the metres chosen", () => {
    const m = hearingSliderModel(normalizeSettings({ hearingM: 40 }), 100);
    expect(m.value).toBe(40);
    expect(m.display).toBe("40 m");
  });

  test("dragging to the top stores 'follow the server', not today's number", () => {
    const m = hearingSliderModel(normalizeSettings({ hearingM: 40 }), 100);
    expect(m.toStore(100)).toBe(0);   // at the top -> follow the server
    expect(m.toStore(120)).toBe(0);   // and above it too
    expect(m.toStore(60)).toBe(60);   // anything shorter is an explicit choice
    expect(m.toStore(1)).toBe(HEARING_MIN_M);
  });

  test("a missing/garbage server radius still yields a usable, finite slider", () => {
    for (const r of [0, -1, NaN, undefined, null, "abc"]) {
      const m = hearingSliderModel(DEFAULT_SETTINGS, r);
      expect(Number.isFinite(m.value)).toBe(true);
      expect(m.min).toBeLessThanOrEqual(m.max);
      expect(m.value).toBeGreaterThanOrEqual(m.min);
      expect(m.value).toBeLessThanOrEqual(m.max);
    }
  });
});

describe("v2 -> v3 migration", () => {
  test("an untouched v2 slider adopts the CURRENT server range, not the old one", () => {
    // fraction 1.0 was v2's default. Migrating it to 35 m would have silently
    // pinned every existing player to the retired range.
    expect(migrateV2({ hearingFraction: 1.0 }).hearingM).toBe(0);
    expect(migrateV2({}).hearingM).toBe(0);
    expect(migrateV2(null).hearingM).toBe(0);
  });

  test("a deliberately shortened v2 range keeps the metres it meant", () => {
    // The basis is the HOLD radius v2 actually displayed and cut against (40 m),
    // NOT the 35 m range - using the range would hand a player who set "20 m" an
    // 18 m range, quietly narrowing the choice this migration exists to preserve.
    expect(V2_BASIS_RADIUS_M).toBe(40);
    expect(migrateV2({ hearingFraction: 0.5 }).hearingM).toBe(20);  // showed "20 m"
    expect(migrateV2({ hearingFraction: 0.25 }).hearingM).toBe(10); // showed "10 m"
    expect(migrateV2({ hearingFraction: 0.1 }).hearingM).toBe(HEARING_MIN_M); // 4 -> floored at 5
  });

  test("the player's other choices survive; the curve default does not stick", () => {
    const m = migrateV2({
      hearingFraction: 0.5, master: 0.4, exponent: 2.2, fullFrac: 0.5,
      micMode: "ptt", pttKey: "KeyV", noiseSuppression: false,
      speakers: { X: { volume: 0.3, muted: true } },
    });
    expect(m.master).toBe(0.4);
    expect(m.exponent).toBe(2.2);
    expect(m.micMode).toBe("ptt");
    expect(m.pttKey).toBe("KeyV");
    expect(m.noiseSuppression).toBe(false);
    expect(m.speakers.X).toEqual({ volume: 0.3, muted: true });
    expect(m.hearingFraction).toBeUndefined();
    // fullFrac never had a control, so NOTHING is stored (0 = follow the current
    // default) and the curve actually in force is today's default. Storing a copy
    // of any default is what pins a player to a retired curve on the next retune.
    expect(m.fullFrac).toBe(0);
    expect(effectiveFullFrac(m)).toBe(FULL_VOLUME_FRACTION);
  });

  test("loadSettings migrates once, then prefers v3 and never re-reads v2", () => {
    const store = memStore({ [LEGACY_LS_KEY_V2]: JSON.stringify({ hearingFraction: 0.5, master: 0.4 }) });
    const first = loadSettings(store);
    expect(first.hearingM).toBe(Math.round(0.5 * V2_BASIS_RADIUS_M));
    expect(first.master).toBe(0.4);
    // Once a v3 entry exists it wins outright, even with v2 still sitting there.
    saveSettings({ ...first, hearingM: 60 }, store);
    expect(loadSettings(store).hearingM).toBe(60);
  });

  test("a corrupt v2 entry falls back to defaults instead of throwing", () => {
    const store = {
      getItem: (k) => (k === LEGACY_LS_KEY_V2 ? "{not json" : null),
      setItem: () => {},
    };
    expect(() => loadSettings(store)).not.toThrow();
    expect(loadSettings(store)).toEqual(normalizeSettings(null));
  });
});

describe("withSpeaker", () => {
  test("updates one speaker and prunes it back to default", () => {
    let s = withSpeaker(DEFAULT_SETTINGS, "P", { volume: 0.3 });
    expect(s.speakers.P).toEqual({ volume: 0.3, muted: false });
    s = withSpeaker(s, "P", { muted: true });
    expect(s.speakers.P).toEqual({ volume: 0.3, muted: true });
    // back to default (vol 1, unmuted) -> pruned
    s = withSpeaker(s, "P", { volume: 1, muted: false });
    expect(s.speakers.P).toBeUndefined();
  });
});

describe("settings survive a future retune", () => {
  test("migrateV2 is genuinely idempotent - re-running never widens a range", () => {
    // It used to read Number(undefined) -> NaN -> 0 on a second pass, silently
    // resetting a chosen range back to the full server range.
    const once = migrateV2({ hearingFraction: 0.5, master: 0.4 });
    expect(once.hearingM).toBe(20);
    expect(migrateV2(once).hearingM).toBe(20);
    expect(migrateV2(migrateV2(once)).hearingM).toBe(20);
    // a blob under the legacy key that ALREADY holds metres keeps them
    expect(migrateV2({ hearingM: 60 }).hearingM).toBe(60);
    // and an explicit fraction still converts
    expect(migrateV2({ hearingM: 60, hearingFraction: 0.25 }).hearingM).toBe(10);
  });

  test("a saved blob never pins the player to a retired full-volume curve", () => {
    // fullFrac has no control, so persisting a COPY of the code default would
    // freeze that player's curve the next time the default is retuned - the
    // exact trap the hearing range had as a fraction.
    expect(curveConfig(normalizeSettings({}), 100).fullFrac).toBe(FULL_VOLUME_FRACTION);
    const store = memStore();
    saveSettings(normalizeSettings({ master: 0.5 }), store);
    expect(JSON.parse(store.data[LS_KEY]).fullFrac).toBe(0);
    // an explicit value would still win if a control is ever added
    expect(curveConfig(normalizeSettings({ fullFrac: 0.45 }), 100).fullFrac).toBe(0.45);
  });

  test("the slider never offers notches that all store the same value", () => {
    // Above HEARING_MAX_M every notch would clamp to one number, so the top of
    // the track would look stuck. Capped instead.
    const m = hearingSliderModel(DEFAULT_SETTINGS, 250);
    expect(m.max).toBe(HEARING_MAX_M);
    expect(m.toStore(m.max)).toBe(0);
    // exhaustive round-trip: every integer notch stores and redisplays itself
    for (const radius of [5, 35, 100, 200]) {
      const s = hearingSliderModel(DEFAULT_SETTINGS, radius);
      for (let v = s.min; v <= s.max; v += 1) {
        const stored = s.toStore(v);
        const back = hearingSliderModel(normalizeSettings({ hearingM: stored }), radius);
        expect(back.value).toBe(v);
      }
    }
  });
});
