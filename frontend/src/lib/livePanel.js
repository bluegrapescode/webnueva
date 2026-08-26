/**
 * Live-dinosaur panel derivations (the 2026-08-07 owner-reference redesign of
 * the /my-dino stats tab). Everything here is pure and total: any payload shape
 * (null, strings, NaN, Infinity, negatives) yields a valid rendering answer,
 * never a throw — the page polls /api/me/state every 3 s and a throw would
 * blank it. Honesty rule carried from the fleet's canonical live card: an
 * unknown reading renders as a dash, never as a confident zero.
 */
import { readCondition } from "./primeRoute";

function isPlainObject(v) {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

export function finiteOrNull(v) {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

const clamp01 = (v) => Math.max(0, Math.min(1, v));

/**
 * A current/max vital from the /me/state shape (0-100 percent + raw max).
 * The current value is recovered as pct/100*max — the backend derives the
 * percent from the same pair, so the round trip is exact to the rounded int.
 */
export function vitalPair(pct, max) {
  const p = finiteOrNull(pct);
  const m = finiteOrNull(max);
  if (p == null || m == null || m <= 0) return { known: false, text: "—", ratio: 0 };
  const cur = Math.max(0, Math.round((p / 100) * m));
  return { known: true, text: `${cur} / ${Math.round(m)}`, ratio: clamp01(p / 100) };
}

/** A vital published as raw current+max (oxygen). */
export function rawPair(cur, max) {
  const c = finiteOrNull(cur);
  const m = finiteOrNull(max);
  if (c == null || m == null || m <= 0) return { known: false, text: "—", ratio: 0 };
  return { known: true, text: `${Math.max(0, Math.round(c))} / ${Math.round(m)}`, ratio: clamp01(c / m) };
}

/** movement_speed arrives in cm/s; the card prints km/h like the reference. */
export const SPRINT_CEILING_CMS = 1000; // same reference ceiling the backend gauges against
export function sprintInfo(cmPerS) {
  const v = finiteOrNull(cmPerS);
  if (v == null || v < 0) return { known: false, text: "—", ratio: 0 };
  const kmh = Math.round(v * 0.036 * 10) / 10;
  return { known: true, text: `${kmh.toFixed(1)} km/h`, ratio: clamp01(v / SPRINT_CEILING_CMS) };
}

/** Bite damage in raw game units; the warning triangle only ever shows on a
 *  KNOWN low reading — "no data" and "weak bite" must never look the same. */
export const BITE_CEILING = 50;
export function biteInfo(raw) {
  const v = finiteOrNull(raw);
  if (v == null || v < 0) return { known: false, text: "—", ratio: 0, warn: false };
  const ratio = clamp01(v / BITE_CEILING);
  const rounded = Math.round(v * 10) / 10;
  return { known: true, text: `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded}`, ratio, warn: ratio < 0.15 };
}

/** bleeding_stacks: 0 -> "Stable" (the reference's wording); >0 -> the count. */
export const BLEED_MAX_STACKS = 10;
export function bleedInfo(stacks) {
  const v = finiteOrNull(stacks);
  if (v == null) return { known: false, text: "—", ratio: 0, active: false };
  if (v <= 0) return { known: true, text: "Stable", ratio: 0, active: false };
  const n = Math.round(v);
  return { known: true, text: `${n} stack${n === 1 ? "" : "s"}`, ratio: clamp01(v / BLEED_MAX_STACKS), active: true };
}

/** One overall fracture figure: the worst (lowest) known limb governs. */
export function fractureOverall(fractures) {
  if (!isPlainObject(fractures)) return { known: false, text: "—", ratio: 0 };
  const parts = ["head", "body", "legs"].map((k) => finiteOrNull(fractures[k])).filter((v) => v != null);
  if (!parts.length) return { known: false, text: "—", ratio: 0 };
  const worst = Math.max(0, Math.min(100, Math.min(...parts)));
  return { known: true, text: `${Math.round(worst)}%`, ratio: worst / 100 };
}

/** A diet nutrient percent. 0 is a REAL reading (renders 0%), null is not. */
export function dietInfo(pct) {
  const v = finiteOrNull(pct);
  if (v == null) return { known: false, text: "—", ratio: 0 };
  const p = Math.max(0, Math.min(100, v));
  return { known: true, text: `${Math.round(p)}%`, ratio: p / 100 };
}

/** Growth stage label under the ring, per the reference (25% -> HATCHLING). */
export function stageFor(growthPct) {
  const g = finiteOrNull(growthPct);
  if (g == null) return null;
  if (g <= 25) return "HATCHLING";
  if (g <= 50) return "JUVENILE";
  if (g <= 75) return "SUB-ADULT";
  return "ADULT";
}

/** "Updated …" footer. Ages honestly when polls keep failing. */
export function updatedAgo(ageMs) {
  const v = finiteOrNull(ageMs);
  if (v == null || v < 0) return "—";
  const mins = Math.floor(v / 60000);
  if (mins < 1) return "Updated less than a minute ago";
  if (mins < 60) return `Updated ${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  return `Updated ${hours} hour${hours === 1 ? "" : "s"} ago`;
}

// ── Prime status checklist ──────────────────────────────────────────────────
// The reference card's five rows plus the two the owner added on 2026-08-07
// (sanctuary + perfect diet). Ids are the mod's own condition ids (the same
// map primeRoute.js documents); labels are the reference card's exact wording.
export const CHECKLIST_ROWS = [
  { id: 8, label: "No muscular spasms", kind: "flag" },
  { id: 7, label: "No infertility", kind: "flag" },
  { id: 5, label: "Migration zones visited", kind: "counter", cap: 2 },
  { id: 6, label: "Patrol zones visited", kind: "counter", cap: 4 },
  { id: 1, label: "Sanctuary visited", kind: "flag" },
  { id: 3, label: "Perfect diet achieved", kind: "flag" },
  { id: 10, label: "Species bonus", kind: "bonus" },
];

// Condition 10 only exists for these species (the game's own list).
const BONUS_SPECIES_PREFIXES = ["hypsi", "troodon", "beipi", "dryo", "deino"];
export function speciesHasBonus(speciesName) {
  const s = String(speciesName || "").trim().toLowerCase();
  if (!s) return null; // unknown species -> unknown eligibility, never a guess
  return BONUS_SPECIES_PREFIXES.some((p) => s.startsWith(p));
}

function conditionValue(conditions, id) {
  if (!isPlainObject(conditions)) return undefined;
  if (conditions[id] !== undefined) return conditions[id];
  return conditions[String(id)];
}

/**
 * Build the seven checklist rows from the whole /api/me/state payload.
 * Counter precedence mirrors primeRoute.js exactly (top-level dino counter,
 * then dino.prime_progress, then the conditions copy, then the default cap) so
 * the two surfaces can never disagree about the same number.
 */
export function buildLiveChecklist(meState) {
  const state = isPlainObject(meState) ? meState : {};
  const dino = isPlainObject(state.dino) ? state.dino : {};
  const summary = isPlainObject(state.prime_progress) ? state.prime_progress : {};
  const conditions = isPlainObject(summary.conditions) ? summary.conditions : {};
  const dinoProgress = isPlainObject(dino.prime_progress) ? dino.prime_progress : {};

  const rows = CHECKLIST_ROWS.map((def) => {
    if (def.kind === "counter") {
      const key = def.id === 5 ? "mig" : "pat";
      const nested = isPlainObject(dinoProgress[key]) ? dinoProgress[key] : {};
      const fromConditions = readCondition(conditionValue(conditions, def.id));
      const top = finiteOrNull(dino[def.id === 5 ? "l_mig" : "l_pat"]);
      const nestedCount = finiteOrNull(nested.count);
      const cap = finiteOrNull(nested.cap);
      const count = Math.max(0, top != null ? top : nestedCount != null ? nestedCount : fromConditions.count != null ? fromConditions.count : 0);
      const resolvedCap = Math.max(1, cap != null && cap > 0 ? cap : fromConditions.cap != null && fromConditions.cap > 0 ? fromConditions.cap : def.cap);
      return { ...def, count, cap: resolvedCap, state: count >= resolvedCap ? "met" : "not" };
    }
    const raw = conditionValue(conditions, def.id);
    const read = readCondition(raw);
    if (def.kind === "bonus") {
      if (read.met) return { ...def, state: "met" };
      const eligible = speciesHasBonus(dino.species || dino.name);
      if (eligible === false) return { ...def, state: "na" };
      if (raw === undefined || eligible === null) return { ...def, state: "unknown" };
      return { ...def, state: "not" };
    }
    if (raw === undefined) return { ...def, state: "unknown" };
    return { ...def, state: read.met ? "met" : "not" };
  });

  return {
    rows,
    met: rows.reduce((n, r) => n + (r.state === "met" ? 1 : 0), 0),
    total: rows.length,
  };
}
