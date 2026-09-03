/**
 * Pure display helpers for the proximity-voice radio panel.
 *
 * The bridge reports each speaker's distance in metres and the owner's audible
 * range; this module turns those raw numbers into the things the panel draws —
 * a 0..4 signal-bar count, a human caption, and the lit-segment count of the
 * microphone VU meter. It is pure and dependency-free so every number a player
 * reads is unit-tested without React, and so the page itself stays markup.
 *
 * Two rules hold everywhere here:
 *  - an UNKNOWN distance (null/undefined/NaN — a speaker the position lane has
 *    not placed yet) is never rendered as "0 m"; it reads as unknown, and it
 *    never claims a stronger signal than a measured distance would.
 *  - nothing here decides who you hear. `audible` comes from the room (the
 *    server's routing); these helpers only describe what already arrived.
 */

/** Total bars the signal indicator draws. */
export const SIGNAL_BARS = 4;
/** Segments in the microphone VU meter. */
export const VU_SEGMENTS = 12;
/** Segment index (0-based) at and above which the VU shows "hot". */
export const VU_HOT_FROM = 9;

/**
 * Coerce to a finite number, or null.
 *
 * The explicit null/""/boolean rejection is load-bearing, NOT defensive noise:
 * `Number(null)` and `Number("")` are 0, so a bare Number.isFinite check turns
 * "this player has no position yet" into a confident "0 m" — the exact lie every
 * helper here promises not to tell.
 */
const num = (n) => {
  if (typeof n !== "number" && typeof n !== "string") return null;
  if (typeof n === "string" && n.trim() === "") return null;
  const v = Number(n);
  return Number.isFinite(v) ? v : null;
};

/**
 * Signal strength as a bar count, 0..SIGNAL_BARS.
 *
 * 0 means "nothing to draw": out of range, or a distance we do not know. A
 * speaker who IS audible always keeps at least one bar even at the very edge of
 * the range, because zero bars beside a voice you can hear reads as a bug.
 */
export function signalBars(distanceM, radiusM, audible = true) {
  if (!audible) return 0;
  const d = num(distanceM);
  const r = num(radiusM);
  if (d === null || r === null || r <= 0) return 0;
  if (d <= 0) return SIGNAL_BARS;
  if (d >= r) return 1;
  const frac = 1 - d / r;                      // 1 at your feet, 0 at the edge
  return Math.max(1, Math.min(SIGNAL_BARS, Math.ceil(frac * SIGNAL_BARS)));
}

/** "18 m", or "—" when the distance is not known yet. */
export function distanceLabel(distanceM) {
  const d = num(distanceM);
  return d === null ? "—" : `${Math.max(0, Math.round(d))} m`;
}

/**
 * The line under a player's name: their distance plus what it means for how
 * they sound. `speaking` is the room's active-speaker signal, so a talker is
 * labelled as talking rather than by distance alone.
 */
export function rangeCaption(distanceM, radiusM, { audible = true, speaking = false } = {}) {
  if (!audible) return "fuera de alcance";
  const d = num(distanceM);
  const r = num(radiusM);
  if (d === null) return speaking ? "en alcance · hablando" : "en alcance";
  const label = distanceLabel(d);
  if (speaking) return `${label} · hablando`;
  if (r !== null && r > 0) {
    if (d <= r * 0.25) return `${label} · muy cerca`;
    if (d >= r * 0.75) return `${label} · señal débil`;
  }
  return label;
}

/**
 * Lit segments of the VU meter for a 0..1 microphone level.
 *
 * The level is scaled the same way the old meter's bar was (x1.6, capped), so
 * normal speech lights most of the meter instead of a sliver. Quantising here
 * is what keeps the meter cheap: the render loop only re-renders when this
 * integer changes, not on every animation frame.
 */
export function vuSegments(level, active = true) {
  if (!active) return 0;
  const v = num(level);
  if (v === null || v <= 0) return 0;
  return Math.max(0, Math.min(VU_SEGMENTS, Math.round(Math.min(1, v * 1.6) * VU_SEGMENTS)));
}

/**
 * Fraction of a dial's arc to sweep for a value inside [min, max], 0..1.
 * Degenerate or junk bounds sweep nothing rather than throwing or drawing NaN.
 */
export function dialFraction(value, min, max) {
  const v = num(value);
  const lo = num(min);
  const hi = num(max);
  if (v === null || lo === null || hi === null || hi <= lo) return 0;
  return Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
}
