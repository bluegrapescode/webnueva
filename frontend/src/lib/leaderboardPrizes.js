// The three prize cards of the Clasificación, decided in one pure place so the
// component only lays out what this returns.
//
// It exists for the same reason leaderboardTabs.js does: /api/leaderboards is a
// PUBLIC endpoint the page renders before anyone signs in, so every degenerate
// answer (missing key, null, a string, a number where an object belongs) has to
// degrade into a card that still draws — a leaderboard that throws on a bad
// prize block would take the whole boards page down with it.
//
// 2026-08-16: rank 1 also carries a cosmetic (`prize_skins["1"]`). 2026-08-18
// (owner order "supernova for 123 place in leaderboard"): all three do. Nothing
// here had to change for that — the card list is built from PRIZE_META and each
// rank looks its own skin up, so a rank simply gains a card when the API starts
// sending one, and still draws without one if it ever stops.
//
// A skin is a NAME + COLOUR PROXIMITY and never a picture (fleet order
// 2026-08-11), so the normaliser deliberately drops `image` on the floor rather
// than passing it through — a stored render URL from any older grant doc cannot
// reach the DOM even if the API ever started sending one again.

export const PRIZE_META = [
  { rank: 1, medal: "🥇", color: "#D4AF37", label: "1º" },
  { rank: 2, medal: "🥈", color: "#C0C6D0", label: "2º" },
  { rank: 3, medal: "🥉", color: "#CD7F32", label: "3º" },
];

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

function safeAmount(v) {
  const n = Number(v);
  // NaN, Infinity, negatives and non-numbers all read as "no amount yet"
  // rather than printing "NaN" on a public page.
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

export function normalizeSkin(raw) {
  if (!raw || typeof raw !== "object") return null;
  const name = typeof raw.name === "string" ? raw.name.trim() : "";
  if (!name) return null; // a card with no name is not a card
  const proximity = Array.isArray(raw.proximity)
    ? raw.proximity.filter((h) => HEX_RE.test(String(h || "")))
    : [];
  return {
    glitch_id: typeof raw.glitch_id === "string" ? raw.glitch_id : "",
    name,
    accent: HEX_RE.test(String(raw.accent || "")) ? raw.accent : null,
    proximity,
  };
}

export function prizeCards(prizes, prizeSkins) {
  const amounts = prizes && typeof prizes === "object" ? prizes : {};
  const skins = prizeSkins && typeof prizeSkins === "object" ? prizeSkins : {};
  return PRIZE_META.map((m) => ({
    ...m,
    amount: safeAmount(amounts[String(m.rank)]),
    skin: normalizeSkin(skins[String(m.rank)]),
  }));
}
