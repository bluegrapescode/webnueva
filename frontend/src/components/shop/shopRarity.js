// Rarity palette for the Fortnite-style skins shop (matches design_guidelines.json).
export const RARITY = {
  common: { label: "Común", color: "#8e9297" },
  uncommon: { label: "Poco común", color: "#34D399" },
  rare: { label: "Raro", color: "#38bdf8" },
  epic: { label: "Épico", color: "#a855f7" },
  legendary: { label: "Legendario", color: "#f59e0b" },
  mythic: { label: "Mítico", color: "#ef4444" },
};

export const RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary", "mythic"];
export const rarityOf = (r) => RARITY[r] || RARITY.common;

export const SECTION_LABEL = {
  destacados: "Destacados",
  diario: "Diario",
  temporada: "Temporada",
};
