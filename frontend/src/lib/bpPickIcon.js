/**
 * Stand-in artwork for a battle-pass dino cell that is still a PICK.
 *
 * A dino cell arrives one of two ways: FIXED (it carries `slug`, e.g. the
 * level-100 Triceratops / Tyrannosaurus) or a PICK (it carries only `band`, and
 * the player chooses the species in DinoPicker after claiming). Fixed cells have
 * always shown real dino art; pick cells fell through to a generic crown badge,
 * so the biggest cells on the track looked emptier than a coin cell.
 *
 * Owner order 2026-08-08: a dino cell shows a dino either way. Each band gets
 * ONE stand-in species. The premium row's picks are unrestricted ("Todas +
 * Ápex"), so those rotate by pick level instead of putting the same animal on
 * all three cells right next to the fixed rex at level 100.
 *
 * The picture is decoration, never a promise: the card still prints
 * "ELIGE DINO" plus the band name, and the claim still opens the picker.
 */

// Regular-row bands. Kept to species the band actually contains, so the art is
// never a lie about what the bracket offers (backend BANDS: low/mid/high).
export const PICK_ICON_BY_BAND = {
  low: "galli",
  mid: "carno",
  high: "allo",
  apex: "trex",
};

// Premium-row picks ("all" = whole roster, apexes included) by their level.
export const PICK_ICON_ALL_BY_LEVEL = {
  25: "raptor",
  50: "trike",
  75: "deino",
};

// Used when a cell arrives with an unknown or missing band, and as the "all"
// fallback if the pick levels ever move: an apex is always inside the "all"
// pool, so the card degrades to a real reward picture rather than a hole.
export const PICK_ICON_FALLBACK = "trex";

/**
 * The species whose picture stands in for a pick cell, or null when the cell is
 * not a pick (fixed dino, coins, tokens, skins, empty).
 */
export function pickIconSlug(cell) {
  if (!cell || cell.type !== "dino") return null;
  if (cell.slug) return null;
  if (cell.band === "all") {
    return PICK_ICON_ALL_BY_LEVEL[Number(cell.level)] || PICK_ICON_FALLBACK;
  }
  return PICK_ICON_BY_BAND[cell.band] || PICK_ICON_FALLBACK;
}

export default pickIconSlug;
