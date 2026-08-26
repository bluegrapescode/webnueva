// ── world <-> map calibration (La Isla Nublar Gateway map) ────────────────
// Gateway UE-cm world bounds, ground-truthed against real live player
// positions on this exact map framing (2026-07-15 calibration pass): the
// screen column tracks world X and the screen row tracks world Y — there is
// NO axis swap. (An earlier revision swapped the axes, which drew every
// player roughly mirrored across the island's diagonal.)
//
// ONE rule, ONE function: every overlay that places a world coordinate on the
// map (the player marker, AI dots, the GEN-Ø facilities) goes through
// worldToPct. A second transform beside it is how two "correct" calibrations
// drift apart. Moved here verbatim from InteractiveMap.jsx on 2026-08-21 so
// pure helpers and tests can import it without importing a component.
export const W_MIN_X = -505000, W_MAX_X = 607000; // world X -> screen column (left %)
export const W_MIN_Y = -607000, W_MAX_Y = 509000; // world Y -> screen row (top %)
export const clampPct = (n) => Math.max(0, Math.min(100, n));
export function worldToPct(x, y) {
  if (typeof x !== "number" || typeof y !== "number" || !Number.isFinite(x) || !Number.isFinite(y)) return null;
  return {
    left: clampPct(((x - W_MIN_X) / (W_MAX_X - W_MIN_X)) * 100),
    top: clampPct(((y - W_MIN_Y) / (W_MAX_Y - W_MIN_Y)) * 100),
  };
}
