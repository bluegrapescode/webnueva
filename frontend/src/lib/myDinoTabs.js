// Which tab /my-dino opens on.
//
// The page has three: the live dinosaur, the player's belongings (bóveda +
// inventario) and the map. The belongings used to hang off the bottom of the
// live panel — the way Arkadia's page still does — and are now a tab of their
// own, so the retired /inventory route needs a way to land straight on them.
//
// This is deliberately a pure function with no React and no window access so it
// can be driven directly by a test; the page passes it `location.search`.

export const MY_DINO_TABS = ["stats", "equipo", "map", "gen0"];

export const MY_DINO_DEFAULT_TAB = "stats";

/**
 * Resolve the ?tab= value of a query string to a real tab key.
 * Anything unknown, empty or malformed falls back to the live panel rather than
 * rendering a page with no content.
 *
 * @param {string} search - e.g. "?tab=equipo" (a leading "?" is optional)
 * @returns {string} one of MY_DINO_TABS
 */
export function resolveMyDinoTab(search) {
  if (typeof search !== "string" || search === "") return MY_DINO_DEFAULT_TAB;
  let t = null;
  try {
    t = new URLSearchParams(search).get("tab");
  } catch {
    return MY_DINO_DEFAULT_TAB;
  }
  return MY_DINO_TABS.includes(t) ? t : MY_DINO_DEFAULT_TAB;
}

export default resolveMyDinoTab;
