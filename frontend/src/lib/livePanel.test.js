/**
 * Live-panel derivations. Invariants: no input shape throws; an unknown
 * reading is a dash, never a confident zero; the prime checklist keys rows by
 * CONDITION ID string/number (proven on sparse payloads both ways — the fleet
 * has already shipped an off-by-one bitmask display once, and the proof that
 * catches it is a sparse mask, not a full one).
 *
 * The bottom of the file pins the WIRING: MyDino renders the reference panel
 * through this module, and the two owner-added rows (sanctuary, perfect diet)
 * are really on the card.
 */
import {
  vitalPair,
  rawPair,
  sprintInfo,
  biteInfo,
  bleedInfo,
  fractureOverall,
  dietInfo,
  stageFor,
  updatedAgo,
  buildLiveChecklist,
  speciesHasBonus,
  CHECKLIST_ROWS,
} from "./livePanel";

const fs = require("fs");
const path = require("path");
const readSrc = (...parts) => fs.readFileSync(path.join(__dirname, "..", ...parts), "utf8");

describe("vitalPair", () => {
  test("recovers the reference card's exact figures", () => {
    expect(vitalPair(100, 50)).toEqual({ known: true, text: "50 / 50", ratio: 1 });
    expect(vitalPair(99.8, 1000)).toEqual({ known: true, text: "998 / 1000", ratio: 0.998 });
    expect(vitalPair(100, 17)).toEqual({ known: true, text: "17 / 17", ratio: 1 });
  });
  test("a big elder max stays exact to the int", () => {
    expect(vitalPair((12499 / 12500) * 100, 12500).text).toBe("12499 / 12500");
  });
  test("unknown inputs are a dash, never 0 / 0", () => {
    [[null, 50], [50, null], [NaN, 50], [50, NaN], [50, 0], [50, -1], [Infinity, 50], ["x", 50]].forEach(([p, m]) => {
      expect(vitalPair(p, m)).toEqual({ known: false, text: "—", ratio: 0 });
    });
  });
  test("string numbers coerce; negatives clamp to 0", () => {
    expect(vitalPair("50", "100")).toEqual({ known: true, text: "50 / 100", ratio: 0.5 });
    expect(vitalPair(-5, 100).text).toBe("0 / 100");
  });
  test("over-100 percent clamps the bar but keeps the honest text", () => {
    const v = vitalPair(120, 100);
    expect(v.ratio).toBe(1);
    expect(v.text).toBe("120 / 100");
  });
});

describe("rawPair (oxygen)", () => {
  test("the reference's 325 / 325", () => {
    expect(rawPair(325, 325)).toEqual({ known: true, text: "325 / 325", ratio: 1 });
  });
  test("zero current is a real reading", () => {
    expect(rawPair(0, 325)).toEqual({ known: true, text: "0 / 325", ratio: 0 });
  });
  test("missing either side is unknown", () => {
    expect(rawPair(null, 325).known).toBe(false);
    expect(rawPair(325, null).known).toBe(false);
    expect(rawPair(325, 0).known).toBe(false);
  });
});

describe("sprintInfo", () => {
  test("cm/s becomes the reference's km/h", () => {
    // 705.6 cm/s ≈ 25.4 km/h (the reference card's figure)
    expect(sprintInfo(705.6).text).toBe("25.4 km/h");
    expect(sprintInfo(705.6).ratio).toBeCloseTo(0.7056);
  });
  test("always one decimal, even on a round figure", () => {
    expect(sprintInfo(1000).text).toBe("36.0 km/h");
  });
  test("zero is a real reading; negatives and garbage are not", () => {
    expect(sprintInfo(0)).toEqual({ known: true, text: "0.0 km/h", ratio: 0 });
    expect(sprintInfo(-3).known).toBe(false);
    expect(sprintInfo(NaN).known).toBe(false);
    expect(sprintInfo(null).known).toBe(false);
  });
});

describe("biteInfo", () => {
  test("the reference's weak hatchling bite warns", () => {
    const b = biteInfo(4);
    expect(b.text).toBe("4");
    expect(b.warn).toBe(true);
  });
  test("a strong bite does not warn; a fractional bite keeps its decimal", () => {
    expect(biteInfo(30).warn).toBe(false);
    expect(biteInfo(6.1).text).toBe("6.1");
  });
  test("unknown never warns — no-data and weak-bite must differ", () => {
    expect(biteInfo(null)).toEqual({ known: false, text: "—", ratio: 0, warn: false });
    expect(biteInfo(-1).known).toBe(false);
  });
});

describe("bleedInfo", () => {
  test("zero stacks is the reference's Stable", () => {
    expect(bleedInfo(0)).toEqual({ known: true, text: "Stable", ratio: 0, active: false });
  });
  test("stacks show a count, singular and plural, and fill the bar", () => {
    expect(bleedInfo(1).text).toBe("1 stack");
    expect(bleedInfo(4).text).toBe("4 stacks");
    expect(bleedInfo(4).active).toBe(true);
    expect(bleedInfo(25).ratio).toBe(1);
  });
  test("negative clamps to Stable; garbage is unknown", () => {
    expect(bleedInfo(-2).text).toBe("Stable");
    expect(bleedInfo(NaN).known).toBe(false);
    expect(bleedInfo(undefined).known).toBe(false);
  });
});

describe("fractureOverall", () => {
  test("the worst limb governs", () => {
    expect(fractureOverall({ head: 100, body: 40, legs: 90 }).text).toBe("40%");
  });
  test("all healthy reads the reference's 100%", () => {
    expect(fractureOverall({ head: 100, body: 100, legs: 100 })).toEqual({ known: true, text: "100%", ratio: 1 });
  });
  test("partial payload uses what arrived; empty is unknown", () => {
    expect(fractureOverall({ head: 70 }).text).toBe("70%");
    expect(fractureOverall({}).known).toBe(false);
    expect(fractureOverall(null).known).toBe(false);
    expect(fractureOverall({ head: NaN }).known).toBe(false);
  });
});

describe("dietInfo", () => {
  test("the reference's 33% carbs and REAL 0% proteins", () => {
    expect(dietInfo(33).text).toBe("33%");
    expect(dietInfo(0)).toEqual({ known: true, text: "0%", ratio: 0 });
  });
  test("null is a dash — never a lying 0%", () => {
    expect(dietInfo(null).text).toBe("—");
    expect(dietInfo(NaN).known).toBe(false);
  });
});

describe("stageFor", () => {
  test("the reference's 25% is HATCHLING", () => {
    expect(stageFor(25)).toBe("HATCHLING");
  });
  test("band edges", () => {
    expect(stageFor(0)).toBe("HATCHLING");
    expect(stageFor(25.1)).toBe("JUVENILE");
    expect(stageFor(50)).toBe("JUVENILE");
    expect(stageFor(75)).toBe("SUB-ADULT");
    expect(stageFor(75.1)).toBe("ADULT");
    expect(stageFor(100)).toBe("ADULT");
    expect(stageFor(120)).toBe("ADULT");
  });
  test("unknown growth has no stage", () => {
    expect(stageFor(null)).toBe(null);
    expect(stageFor(NaN)).toBe(null);
  });
});

describe("updatedAgo", () => {
  test("fresh polls read like the reference", () => {
    expect(updatedAgo(0)).toBe("Updated less than a minute ago");
    expect(updatedAgo(59_000)).toBe("Updated less than a minute ago");
  });
  test("ages honestly when polls fail", () => {
    expect(updatedAgo(61_000)).toBe("Updated 1 minute ago");
    expect(updatedAgo(180_000)).toBe("Updated 3 minutes ago");
    expect(updatedAgo(3_700_000)).toBe("Updated 1 hour ago");
  });
  test("no timestamp is a dash", () => {
    expect(updatedAgo(null)).toBe("—");
    expect(updatedAgo(-5)).toBe("—");
  });
});

describe("speciesHasBonus", () => {
  test("the game's five bonus species match by prefix", () => {
    ["Hypsilophodon", "Troodon", "Beipiaosaurus", "Dryosaurus", "Deinosuchus", "deino"].forEach((s) => {
      expect(speciesHasBonus(s)).toBe(true);
    });
  });
  test("everyone else is false; unknown species is null, not a guess", () => {
    expect(speciesHasBonus("Tyrannosaurus")).toBe(false);
    expect(speciesHasBonus("")).toBe(null);
    expect(speciesHasBonus(null)).toBe(null);
  });
});

describe("buildLiveChecklist", () => {
  const LIVE_SHAPE = {
    // A real prod row shape (prime_progress_state.json, 2026-08-07): all ten
    // conditions always published as 0/1 under STRING keys.
    prime_progress: {
      available: true,
      conditions: { 1: 0, 2: 0, 3: 1, 4: 0, 5: 1, 6: 1, 7: 0, 8: 1, 9: 0, 10: 1 },
      mig: { n: 2, cap: 2 },
      pat: { n: 4, cap: 4 },
    },
    dino: { species: "Deinosuchus", l_mig: 2, l_pat: 4, prime_progress: { mig: { count: 2, cap: 2 }, pat: { count: 4, cap: 4 } } },
  };

  test("the seven rows, in the reference order plus the two owner-added ones", () => {
    const { rows } = buildLiveChecklist(LIVE_SHAPE);
    expect(rows.map((r) => r.label)).toEqual([
      "No muscular spasms",
      "No infertility",
      "Migration zones visited",
      "Patrol zones visited",
      "Sanctuary visited",
      "Perfect diet achieved",
      "Species bonus",
    ]);
  });

  test("a live prod row resolves every state by ID, not by position", () => {
    const { rows, met, total } = buildLiveChecklist(LIVE_SHAPE);
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
    expect(byId[8].state).toBe("met");      // spasms met
    expect(byId[7].state).toBe("not");      // infertility NOT met
    expect(byId[5]).toMatchObject({ state: "met", count: 2, cap: 2 });
    expect(byId[6]).toMatchObject({ state: "met", count: 4, cap: 4 });
    expect(byId[1].state).toBe("not");      // sanctuary not met
    expect(byId[3].state).toBe("met");      // perfect diet met
    expect(byId[10].state).toBe("met");     // bonus species, met
    expect(met).toBe(5);
    expect(total).toBe(7);
  });

  test("SPARSE payload: one lone condition lands on ITS row and nowhere else", () => {
    const { rows } = buildLiveChecklist({ prime_progress: { conditions: { "3": 1 } }, dino: { species: "Tyrannosaurus" } });
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
    expect(byId[3].state).toBe("met");            // the one published condition
    expect(byId[1].state).toBe("unknown");        // its NEIGHBOURS are unknown,
    expect(byId[8].state).toBe("unknown");        // never shifted onto
    expect(byId[7].state).toBe("unknown");
    expect(byId[10].state).toBe("na");            // rex: bonus not applicable
  });

  test("numeric and string condition keys both resolve", () => {
    const a = buildLiveChecklist({ prime_progress: { conditions: { 8: 1 } }, dino: {} });
    const b = buildLiveChecklist({ prime_progress: { conditions: { "8": "1" } }, dino: {} });
    expect(a.rows.find((r) => r.id === 8).state).toBe("met");
    expect(b.rows.find((r) => r.id === 8).state).toBe("met");
  });

  test("the reference card itself: rex with nothing done reads 2 of 7", () => {
    const { rows, met, total } = buildLiveChecklist({
      prime_progress: { conditions: { 1: 0, 3: 0, 5: 0, 6: 0, 7: 1, 8: 1, 10: 0 } },
      dino: { species: "Tyrannosaurus", l_mig: 0, l_pat: 0 },
    });
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
    expect(byId[5]).toMatchObject({ state: "not", count: 0, cap: 2 });
    expect(byId[6]).toMatchObject({ state: "not", count: 0, cap: 4 });
    expect(byId[10].state).toBe("na"); // "Not applicable", exactly the reference
    expect(met).toBe(2);
    expect(total).toBe(7);
  });

  test("counter precedence: live l_mig wins over a stale conditions copy", () => {
    const { rows } = buildLiveChecklist({
      prime_progress: { conditions: { 5: { n: 0, cap: 2 } } },
      dino: { l_mig: 2 },
    });
    expect(rows.find((r) => r.id === 5)).toMatchObject({ count: 2, cap: 2, state: "met" });
  });

  test("bonus met beats eligibility — published data outranks the species list", () => {
    const { rows } = buildLiveChecklist({ prime_progress: { conditions: { 10: 1 } }, dino: { species: "Tyrannosaurus" } });
    expect(rows.find((r) => r.id === 10).state).toBe("met");
  });

  test("no species named: an unmet bonus is unknown, never a guessed NA", () => {
    const { rows } = buildLiveChecklist({ prime_progress: { conditions: { 10: 0 } }, dino: {} });
    expect(rows.find((r) => r.id === 10).state).toBe("unknown");
  });

  test("garbage payloads never throw and land on the safe states", () => {
    [null, undefined, 42, "x", [], { prime_progress: "x" }, { prime_progress: { conditions: [] } }].forEach((junk) => {
      const { rows, met, total } = buildLiveChecklist(junk);
      expect(total).toBe(7);
      expect(met).toBe(0);
      expect(rows.find((r) => r.id === 5)).toMatchObject({ count: 0, cap: 2 });
      expect(rows.find((r) => r.id === 6)).toMatchObject({ count: 0, cap: 4 });
    });
  });

  test("negative counts and zero caps cannot fake progress", () => {
    const { rows } = buildLiveChecklist({ prime_progress: { conditions: {} }, dino: { l_mig: -3, prime_progress: { mig: { cap: 0 } } } });
    expect(rows.find((r) => r.id === 5)).toMatchObject({ count: 0, cap: 2, state: "not" });
  });
});

describe("wiring — the page renders the reference panel through this module", () => {
  const page = readSrc("pages", "MyDino.jsx");

  test("MyDino derives through livePanel, not inline math", () => {
    expect(page).toMatch(/from "@\/lib\/livePanel"/);
    expect(page).toMatch(/buildLiveChecklist\(/);
    expect(page).toMatch(/vitalPair\(/);
  });
  test("the reference card's sections are all on the page", () => {
    ["LIVE DINOSAUR STATS", "VITALS", "NUTRIENT DIET", "PRIME STATUS"].forEach((s) => {
      expect(page).toContain(s);
    });
  });
  test("the two owner-added prime rows really render (via the shared row table)", () => {
    expect(readSrc("lib", "livePanel.js")).toContain("Sanctuary visited");
    expect(readSrc("lib", "livePanel.js")).toContain("Perfect diet achieved");
    expect(page).toMatch(/prime-row-/);
  });
  test("the ids anything else may probe survive the redesign", () => {
    ["active-dino-card", "no-active-dino", "livedino-tab-", "livedino-refresh"].forEach((id) => {
      expect(page).toContain(id);
    });
  });
  test("CHECKLIST_ROWS stays seven rows in the reference order", () => {
    expect(CHECKLIST_ROWS.map((r) => r.id)).toEqual([8, 7, 5, 6, 1, 3, 10]);
  });
});
