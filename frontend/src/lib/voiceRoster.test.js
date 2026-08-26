/**
 * Proximity-radio display helpers. The guarantees under test: an unknown
 * distance never renders as "0 m" and never outranks a measured one, an audible
 * speaker never drops to zero bars, out-of-range never claims signal, and junk
 * input (NaN, null, negative or inverted bounds) can never push NaN into the
 * markup.
 */
import {
  signalBars, distanceLabel, rangeCaption, vuSegments, dialFraction,
  SIGNAL_BARS, VU_SEGMENTS,
} from "./voiceRoster";

describe("signalBars", () => {
  test("full at your feet, weakest at the edge, monotonic in between", () => {
    expect(signalBars(0, 100)).toBe(SIGNAL_BARS);
    expect(signalBars(10, 100)).toBe(SIGNAL_BARS);
    expect(signalBars(40, 100)).toBe(3);
    expect(signalBars(60, 100)).toBe(2);
    expect(signalBars(90, 100)).toBe(1);
    const seq = [5, 20, 45, 70, 95].map((d) => signalBars(d, 100));
    expect(seq).toEqual([...seq].sort((a, b) => b - a)); // never rises with distance
  });

  test("an audible speaker keeps a bar even past the nominal range", () => {
    expect(signalBars(100, 100)).toBe(1);
    expect(signalBars(140, 100)).toBe(1);
  });

  test("out of range draws nothing, whatever the distance says", () => {
    expect(signalBars(5, 100, false)).toBe(0);
    expect(signalBars(null, 100, false)).toBe(0);
  });

  test("unknown distance or unusable radius draws nothing, never NaN", () => {
    for (const bad of [null, undefined, NaN, "x"]) {
      expect(signalBars(bad, 100)).toBe(0);
      expect(signalBars(20, bad)).toBe(0);
    }
    expect(signalBars(20, 0)).toBe(0);
    expect(signalBars(20, -50)).toBe(0);
  });

  test("never exceeds the drawable bar count", () => {
    for (const d of [-10, 0, 1, 50, 99, 1e6]) {
      const n = signalBars(d, 100);
      expect(Number.isInteger(n)).toBe(true);
      expect(n).toBeGreaterThanOrEqual(0);
      expect(n).toBeLessThanOrEqual(SIGNAL_BARS);
    }
  });
});

describe("distanceLabel", () => {
  test("rounds to whole metres", () => {
    expect(distanceLabel(18.4)).toBe("18 m");
    expect(distanceLabel(18.6)).toBe("19 m");
    expect(distanceLabel(0)).toBe("0 m");
  });
  test("unknown reads as unknown, not as zero", () => {
    for (const bad of [null, undefined, NaN, "x"]) expect(distanceLabel(bad)).toBe("—");
  });
  test("a negative distance never renders below zero", () => {
    expect(distanceLabel(-3)).toBe("0 m");
  });
});

describe("rangeCaption", () => {
  test("describes closeness relative to the live range", () => {
    expect(rangeCaption(10, 100)).toBe("10 m · muy cerca");
    expect(rangeCaption(50, 100)).toBe("50 m");
    expect(rangeCaption(90, 100)).toBe("90 m · señal débil");
  });
  test("the same distance changes meaning when the owner retunes the range", () => {
    expect(rangeCaption(30, 100)).toBe("30 m");
    expect(rangeCaption(30, 35)).toBe("30 m · señal débil");
  });
  test("a talker is labelled as talking", () => {
    expect(rangeCaption(41, 100, { speaking: true })).toBe("41 m · hablando");
    expect(rangeCaption(null, 100, { speaking: true })).toBe("en alcance · hablando");
  });
  test("out of range wins over any distance", () => {
    expect(rangeCaption(5, 100, { audible: false })).toBe("fuera de alcance");
    expect(rangeCaption(5, 100, { audible: false, speaking: true })).toBe("fuera de alcance");
  });
  test("unknown distance still reads as in range", () => {
    expect(rangeCaption(undefined, 100)).toBe("en alcance");
    expect(rangeCaption(20, null)).toBe("20 m");
  });
});

describe("vuSegments", () => {
  test("silence is empty, speech lights most of the meter, loud fills it", () => {
    expect(vuSegments(0)).toBe(0);
    expect(vuSegments(0.5)).toBe(10);
    expect(vuSegments(1)).toBe(VU_SEGMENTS);
  });
  test("clamps above unity and below zero", () => {
    expect(vuSegments(9)).toBe(VU_SEGMENTS);
    expect(vuSegments(-1)).toBe(0);
  });
  test("an inactive mic is empty no matter the level", () => {
    expect(vuSegments(0.9, false)).toBe(0);
  });
  test("junk is empty, never NaN", () => {
    for (const bad of [null, undefined, NaN, "x"]) expect(vuSegments(bad)).toBe(0);
  });
  test("quantised to whole segments so the meter re-renders only on a visible change", () => {
    expect(vuSegments(0.3)).toBe(vuSegments(0.305));
    for (const v of [0, 0.13, 0.42, 0.77, 1]) expect(Number.isInteger(vuSegments(v))).toBe(true);
  });
});

describe("dialFraction", () => {
  test("maps a value onto its 0..1 sweep", () => {
    expect(dialFraction(0.6, 0.6, 3)).toBe(0);
    expect(dialFraction(3, 0.6, 3)).toBe(1);
    expect(dialFraction(50, 0, 100)).toBeCloseTo(0.5, 6);
  });
  test("clamps outside the band instead of overdrawing the arc", () => {
    expect(dialFraction(-40, 0, 100)).toBe(0);
    expect(dialFraction(400, 0, 100)).toBe(1);
  });
  test("degenerate or junk bounds sweep nothing", () => {
    expect(dialFraction(5, 10, 10)).toBe(0);
    expect(dialFraction(5, 10, 1)).toBe(0);
    for (const bad of [null, undefined, NaN, "x"]) {
      expect(dialFraction(bad, 0, 100)).toBe(0);
      expect(dialFraction(5, bad, 100)).toBe(0);
      expect(dialFraction(5, 0, bad)).toBe(0);
    }
  });
});
