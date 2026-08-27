// Pure presentation helpers for the Cemetery. Shared by the page + admin tab.

export const CEM_STATUS = {
  ELEGIBLE:     { label: "Elegible",     color: "#34D399", bg: "rgba(52,211,153,0.12)", border: "rgba(52,211,153,0.35)" },
  RESUCITADO:   { label: "Resucitado",   color: "#7CA842", bg: "rgba(124,168,66,0.14)", border: "rgba(124,168,66,0.4)" },
  NO_REVIVIBLE: { label: "No revivible", color: "#E24A4A", bg: "rgba(226,74,74,0.12)",  border: "rgba(226,74,74,0.35)" },
};

export const CEM_RARITY = {
  Apex:     "#E24A4A",
  Rare:     "#A855F7",
  Uncommon: "#38BDF8",
  Common:   "#94A3B8",
};

export const CEM_CAUSES = [
  "Combate", "Ahogamiento", "Caída", "Inanición",
  "Enfermedad", "Emboscada", "Deshidratación", "Otro",
];

export const CEM_SORTS = [
  { id: "recent", label: "Más recientes" },
  { id: "oldest", label: "Más antiguos" },
  { id: "kills", label: "Más asesinatos" },
  { id: "playtime", label: "Mayor supervivencia" },
  { id: "growth", label: "Mayor tamaño" },
];

export function rarityColor(r) {
  return CEM_RARITY[r] || CEM_RARITY.Common;
}

export function statusMeta(s) {
  return CEM_STATUS[s] || CEM_STATUS.ELEGIBLE;
}

export function fmtPlaytime(mins) {
  const m = Math.max(0, Number(mins) || 0);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

export function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch (e) {
    return iso;
  }
}

export function fmtCountdown(iso) {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return null;
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  return `${h}h ${m}m`;
}
