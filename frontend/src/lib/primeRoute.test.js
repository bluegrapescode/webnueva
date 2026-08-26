/**
 * Prime route derivation. The invariant everywhere: a payload the mod has not
 * filled in yet must read as "not done", never as done and never as a throw —
 * the panel polls this every 3 s and a throw blanks the live dino page.
 *
 * The pure layer alone proves nothing, so the bottom of this file also pins the
 * WIRING: that MyDino renders the route and no longer carries the old
 * checklist, and that the component reads its data through this module.
 */
import {
  buildPrimeRoute,
  readCondition,
  stationHint,
  PRIME_CONDITION_LABELS,
  PRIME_CONDITION_SHORT,
  PRIME_COUNTER_IDS,
  PRIME_DEFAULT_CAPS,
} from "./primeRoute";

// eslint-disable-next-line global-require
const fs = require("fs");
// eslint-disable-next-line global-require
const path = require("path");
const readSrc = (...parts) => fs.readFileSync(path.join(__dirname, "..", ...parts), "utf8");

const live = (over = {}) => ({
  dino: { is_prime: false, l_mig: 2, l_pat: 3, ...(over.dino || {}) },
  prime_progress: { conditions: { 5: { n: 2, cap: 2 }, 6: { n: 3, cap: 4 }, 7: true, 8: true, 10: false }, ...(over.prime_progress || {}) },
});

describe("readCondition", () => {
  test("flags", () => {
    expect(readCondition(true)).toMatchObject({ met: true, kind: "flag" });
    expect(readCondition(false)).toMatchObject({ met: false, kind: "flag" });
    expect(readCondition(undefined)).toMatchObject({ met: false, kind: "flag" });
    expect(readCondition(null)).toMatchObject({ met: false, kind: "flag" });
  });

  test("counters are met only at or above the cap", () => {
    expect(readCondition({ n: 3, cap: 4 }).met).toBe(false);
    expect(readCondition({ n: 4, cap: 4 }).met).toBe(true);
    expect(readCondition({ n: 9, cap: 4 }).met).toBe(true);
    expect(readCondition({ count: 2, cap: 2 }).met).toBe(true);
  });

  test("a zero cap cannot make an empty counter 'met'", () => {
    // 0 >= 0 would be true; the cap floors at 1 so an unstarted counter is pending.
    expect(readCondition({ n: 0, cap: 0 }).met).toBe(false);
  });

  test("garbage never throws and never reads as done", () => {
    // `!!value` would call [], Infinity and any stray string DONE. Only an
    // explicit yes counts, so a malformed payload under-reports, never over.
    [[], "x", NaN, Infinity, -1, {}, { n: "abc", cap: "abc" }, { cap: null }].forEach((v) => {
      expect(() => readCondition(v)).not.toThrow();
      expect(readCondition(v).met).toBe(false);
    });
  });

  test("the explicit yes spellings the payload may use", () => {
    [true, 1, "1", "true"].forEach((v) => expect(readCondition(v).met).toBe(true));
  });
});

describe("buildPrimeRoute", () => {
  test("a live payload becomes an ordered route", () => {
    const r = buildPrimeRoute(live());
    expect(r.stations.map((s) => s.id)).toEqual([5, 6, 7, 8, 10]);
    expect(r.total).toBe(5);
    expect(r.doneCount).toBe(3); // 5 (2/2), 7, 8
    expect(r.pct).toBe(60);
    expect(r.isPrime).toBe(false);
  });

  test("current is the first pending station, next the one after it", () => {
    const r = buildPrimeRoute(live());
    expect(r.current.id).toBe(6);
    expect(r.next.id).toBe(10);
  });

  test("a finished route has no current and no next", () => {
    const r = buildPrimeRoute({
      dino: { is_prime: true, l_mig: 2, l_pat: 4 },
      prime_progress: { conditions: { 5: { n: 2, cap: 2 }, 6: { n: 4, cap: 4 }, 7: true } },
    });
    expect(r.current).toBeNull();
    expect(r.next).toBeNull();
    expect(r.pct).toBe(100);
    expect(r.isPrime).toBe(true);
  });

  test("the two counter stations exist even with no conditions payload at all", () => {
    const r = buildPrimeRoute({ dino: { l_mig: 1, l_pat: 0 } });
    expect(r.stations.map((s) => s.id)).toEqual(PRIME_COUNTER_IDS);
    expect(r.stations[0]).toMatchObject({ count: 1, cap: PRIME_DEFAULT_CAPS[5], met: false });
    expect(r.stations[1]).toMatchObject({ count: 0, cap: PRIME_DEFAULT_CAPS[6], met: false });
  });

  test("the top-level dino counter wins over the conditions copy", () => {
    // The ledger the display used to derive from could be wiped on relog; the
    // dino field is the honest one, so it must not be overridden.
    const r = buildPrimeRoute({
      dino: { l_mig: 2, l_pat: 4 },
      prime_progress: { conditions: { 5: { n: 0, cap: 2 }, 6: { n: 0, cap: 4 } } },
    });
    expect(r.stations.find((s) => s.id === 5)).toMatchObject({ count: 2, met: true });
    expect(r.stations.find((s) => s.id === 6)).toMatchObject({ count: 4, met: true });
  });

  test("dino.prime_progress {mig,pat} is used when the top-level counter is absent", () => {
    const r = buildPrimeRoute({ dino: { prime_progress: { mig: { count: 1, cap: 3 }, pat: { count: 2, cap: 2 } } } });
    expect(r.stations.find((s) => s.id === 5)).toMatchObject({ count: 1, cap: 3, met: false });
    expect(r.stations.find((s) => s.id === 6)).toMatchObject({ count: 2, cap: 2, met: true });
  });

  test("a missing count is 0 progress, never a confident wrong number", () => {
    // Number(null) and Number("") are 0 — the guard rejects by type first, so a
    // null count falls through to the next source instead of asserting zero.
    const r = buildPrimeRoute({
      dino: { l_mig: null, l_pat: "" },
      prime_progress: { conditions: { 5: { n: 2, cap: 2 }, 6: { n: 1, cap: 4 } } },
    });
    expect(r.stations.find((s) => s.id === 5)).toMatchObject({ count: 2, met: true });
    expect(r.stations.find((s) => s.id === 6)).toMatchObject({ count: 1, met: false });
  });

  test("string condition keys and numeric keys both resolve", () => {
    const r = buildPrimeRoute({ dino: {}, prime_progress: { conditions: { "7": true, "9": false } } });
    expect(r.stations.map((s) => s.id)).toEqual([5, 6, 7, 9]);
    expect(r.stations.find((s) => s.id === 7).met).toBe(true);
    expect(r.stations.find((s) => s.id === 9).met).toBe(false);
  });

  test("an id the labels table has never seen still renders with a readable name", () => {
    const r = buildPrimeRoute({ dino: {}, prime_progress: { conditions: { 11: true } } });
    const s = r.stations.find((x) => x.id === 11);
    expect(s).toBeTruthy();
    expect(typeof s.label).toBe("string");
    expect(s.label.length).toBeGreaterThan(0);
  });

  test("junk input yields an empty-but-valid route instead of throwing", () => {
    [null, undefined, 0, "", [], "nope", { dino: "x", prime_progress: 7 }].forEach((v) => {
      expect(() => buildPrimeRoute(v)).not.toThrow();
      const r = buildPrimeRoute(v);
      expect(Array.isArray(r.stations)).toBe(true);
      expect(Number.isFinite(r.pct)).toBe(true);
      expect(r.doneCount).toBeLessThanOrEqual(r.total);
    });
  });

  test("pct is never NaN and never over 100", () => {
    const r = buildPrimeRoute({ dino: { l_mig: 99, l_pat: 99 }, prime_progress: { conditions: {} } });
    expect(r.pct).toBe(100);
  });

  test("every station carries a short caption for the marker", () => {
    buildPrimeRoute(live()).stations.forEach((s) => {
      expect(typeof s.short).toBe("string");
      expect(s.short.length).toBeGreaterThan(0);
    });
  });

  test("labels and short captions cover all ten ids", () => {
    for (let i = 1; i <= 10; i += 1) {
      expect(PRIME_CONDITION_LABELS[i]).toBeTruthy();
      expect(PRIME_CONDITION_SHORT[i]).toBeTruthy();
    }
  });

  test("the labels are the words the GAME says, not the retired ones", () => {
    // The mod says "De cría, pisa un Santuario" from 2026-07-28. If the site
    // drifts back to the old wording, a requirement has two different names
    // depending on where the player reads it.
    expect(PRIME_CONDITION_LABELS[1]).toBe("De cría, pisa un Santuario");
    expect(PRIME_CONDITION_LABELS[6]).toBe("Marca 4 territorios de Patrulla");
    expect(PRIME_CONDITION_LABELS[7]).toBe("Llega fértil hasta el final");
    Object.values(PRIME_CONDITION_LABELS).forEach((l) => {
      expect(l).not.toBe("Juvenil en Santuario");
      expect(l).not.toBe("Zonas de Patrulla Visitadas");
      expect(l).not.toBe("Nunca Infértil");
    });
  });
});

describe("stationHint", () => {
  test("a counter says what is left, singular and plural", () => {
    expect(stationHint({ kind: "counter", count: 3, cap: 4 })).toBe("Llevas 3 de 4 · te falta una");
    expect(stationHint({ kind: "counter", count: 1, cap: 4 })).toBe("Llevas 1 de 4 · te faltan 3");
    expect(stationHint({ kind: "counter", count: 4, cap: 4 })).toBe("Ya la tienes");
  });

  test("a flag says whether it has started", () => {
    expect(stationHint({ kind: "flag", met: false })).toBe("Aún sin empezar");
    expect(stationHint({ kind: "flag", met: true })).toBe("Ya la tienes");
  });

  test("no station, no crash", () => {
    expect(stationHint(null)).toBe("");
    expect(stationHint(undefined)).toBe("");
  });
});

describe("wiring — prime on the live page (2026-08-07 reference redesign)", () => {
  // The stats tab now renders the owner's reference card: prime is the
  // checklist INSIDE the card (lib/livePanel's buildLiveChecklist, which
  // resolves counters through THIS module's readCondition + precedence rules).
  // PrimeRoute survives as a tested standalone component, but the page must
  // not mount BOTH designs at once.
  const page = readSrc("pages", "MyDino.jsx");

  test("MyDino renders the checklist, not the retired route, and never both", () => {
    expect(page).toContain('from "@/lib/livePanel"');
    expect(page).toMatch(/buildLiveChecklist\(meState\)/);
    expect(page).not.toContain("PrimeRoute");
  });

  test("the old checklist bars stay retired from the page", () => {
    expect(page).not.toContain("PrimeProgressBar");
    expect(page).not.toContain("BooleanConditionRow");
    expect(page).not.toContain("Progreso Prime");
  });

  test("the checklist derives through livePanel, which reuses readCondition", () => {
    const lib = readSrc("lib", "livePanel.js");
    expect(lib).toContain('import { readCondition } from "./primeRoute"');
    expect(lib).toContain("buildLiveChecklist");
  });

  test("the ids anything else may probe survive the redesign", () => {
    ["prime-block", "prime-status-badge"].forEach((id) => {
      expect(page).toContain(id);
    });
    // The two zone counters stay addressable, now as per-id checklist rows.
    ["prime-row-5", "prime-row-6"].forEach((id) => {
      expect(page.includes("prime-row-${row.id}") || page.includes(id)).toBe(true);
    });
  });
});
