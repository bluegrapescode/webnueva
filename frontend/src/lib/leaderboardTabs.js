// Pure decisions for the Clasificación page — kept out of the component so
// backend-shape edge cases are pinned by jest without rendering.

export const LB_TABS = [
  { k: "overall", label: "General", tag: "puntos", accent: "#7CA842" },
  { k: "kills", label: "Kills", tag: "kills", accent: "#E24A4A" },
  { k: "quests", label: "Misiones", tag: "misiones", accent: "#34D399" },
  { k: "playtime", label: "Tiempo", tag: "tiempo", accent: "#38BDF8" },
];

export function isTabKey(k) {
  return LB_TABS.some((t) => t.k === k);
}

/** Split one board into podium (top 3) + list rows (4..N). Tolerates a null,
 * short, or malformed board — the page must render on every backend answer. */
export function splitBoard(rows) {
  const clean = Array.isArray(rows) ? rows.filter((r) => r && r.user_id) : [];
  return { podium: clean.slice(0, 3), list: clean.slice(3) };
}

/** The viewer's pinned row: only when signed in, ranked, and NOT already
 * visible in the rendered board (rank strictly beyond the last shown row). */
export function myPinnedRow(meRow, shownCount) {
  if (!meRow || typeof meRow.rank !== "number" || meRow.rank <= 0) return null;
  return meRow.rank > shownCount ? meRow : null;
}
