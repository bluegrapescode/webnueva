// Meta puro (sin React) para el Sistema Global de Bounties.

export const BOUNTY_COLORS = {
  bg: "#0B0B0D",
  carbon: "#141417",
  danger: "#E11D2A",
  dangerDeep: "#7A0C13",
  amber: "#F0B429",
  white: "#F5F5F7",
  muted: "#8A8A93",
};

// Silueta/emoji de respaldo por especie (los assets 3D 404 en preview, así que
// la tarjeta se apoya en la tipografía + un glifo del depredador).
const DINO_GLYPH = {
  trex: "🦖", spino: "🦖", allo: "🦖", carno: "🦖", austro: "🦖",
  cerato: "🦖", herrera: "🦖", raptor: "🦖", dilo: "🦖",
  deino: "🐊", trike: "🦕", stego: "🦕", ptera: "🦅",
};

export function dinoGlyph(slug) {
  return DINO_GLYPH[slug] || "☠";
}

export function fmtNum(n) {
  const v = Number(n || 0);
  return v.toLocaleString("es-MX");
}

// mm:ss a partir de un timestamp de servidor (ms) — el frontend calcula con
// Date.now(), el servidor nunca manda un contador por segundo.
export function fmtCountdown(targetMs) {
  if (!targetMs) return "00:00";
  const left = Math.max(0, Math.floor((targetMs - Date.now()) / 1000));
  const m = Math.floor(left / 60);
  const s = left % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// ISO -> ms
export function isoMs(iso) {
  if (!iso) return 0;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
}
