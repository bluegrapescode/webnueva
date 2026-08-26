// Nublar Spin — pure helpers (no React, no DOM) so the carousel maths, card
// copy and rarity theming are unit-testable the way this repo tests things.

export const RARITY_THEMES = {
  common:    { bg: "linear-gradient(180deg, #4B5563 0%, #1F2937 100%)", accent: "#9CA3AF", label: "COMÚN" },
  rare:      { bg: "linear-gradient(180deg, #1E40AF 0%, #0B1E4F 100%)", accent: "#3B82F6", label: "RARO" },
  epic:      { bg: "linear-gradient(180deg, #6D28D9 0%, #2E1065 100%)", accent: "#A855F7", label: "ÉPICO" },
  legendary: { bg: "linear-gradient(180deg, #B45309 0%, #4A2803 100%)", accent: "#F59E0B", label: "LEGENDARIO" },
};
const NEUTRAL = { bg: "linear-gradient(180deg, #1E293B 0%, #0F172A 100%)", accent: "#94A3B8", label: "" };

export function cardTheme(seg) {
  const r = seg && seg.rarity;
  return (r && RARITY_THEMES[r]) || NEUTRAL;
}

export function rarityLabel(rarity) {
  return (RARITY_THEMES[rarity] || {}).label || String(rarity || "").toUpperCase();
}

export function fmtNum(n) {
  const v = Number(n || 0);
  return v >= 1000 ? v.toLocaleString("es-AR") : String(v);
}

// CATEGORY / TITLE / SUBTITLE per plate, in the site's own words. Tokens and
// dinos say WHERE the prize lands so a winner knows the next step.
export function cardContent(seg) {
  const k = seg ? seg.kind : "";
  const lbl = ((seg && seg.label) || "").toUpperCase();
  if (k === "primemeat")    return { category: "PRIMEMEAT", title: fmtNum(seg.amount), subtitle: "PRIMEMEAT" };
  if (k === "amberium")     return { category: "AMBERIUM",  title: fmtNum(seg.amount), subtitle: "AMBERIUM" };
  if (k === "growth_token") return { category: "FICHA", title: seg.flavor === "premium" ? "CRECIMIENTO" : "CRECIMIENTO", subtitle: seg.flavor === "premium" ? "PREMIUM · PRIME" : "70% EN VIVO" };
  if (k === "diet_token")   return { category: "FICHA", title: "DIETA", subtitle: "+150% EN VIVO" };
  if (k === "glitch_skin")  return { category: "SKIN", title: "GLITCH", subtitle: "ALEATORIA" };
  if (k === "dino_basic")   return { category: "DINO", title: "SALVAJE", subtitle: "75% · BÓVEDA" };
  if (k === "dino_prime")   return { category: "DINO", title: "PRIME", subtitle: "75% · 4 MUTACIONES" };
  if (k === "gen0_vial")    return { category: "GEN-Ø", title: "VIAL", subtitle: "INFECCIÓN 100%" };
  return { category: "PREMIO", title: lbl || "?", subtitle: "" };
}

// Art per plate. Glitch skins are a NAME + colour proximity on this fleet,
// never a picture (order 2026-08-11) — so they return null on purpose.
export function segmentImage(seg) {
  const k = seg ? seg.kind : "";
  if (k === "growth_token") return "/tokens/growth.png";
  if (k === "diet_token")   return "/tokens/diet.png";
  if (k === "amberium")     return "/coins/amber.png";
  if (k === "primemeat")    return "/coins/meat.png";
  if (k === "gen0_vial")    return "/tokens/vial-gen0.png";
  return null;
}

// Responsive card geometry by viewport width. These are the bundle's own
// dimensions: the earlier port shrank every plate to fit a cramped tab, which
// is what made the stage read as squashed.
export function computeLayout(w) {
  // VIEW_H leaves room for the 1.18x centre card plus the frame's tick marks.
  if (w < 480)  return { CARD_W: 130, CARD_H: 230, STEP_X: 145, VIEW_H: 340 };
  if (w < 768)  return { CARD_W: 160, CARD_H: 280, STEP_X: 175, VIEW_H: 400 };
  if (w < 1024) return { CARD_W: 180, CARD_H: 330, STEP_X: 200, VIEW_H: 460 };
  if (w < 1440) return { CARD_W: 210, CARD_H: 380, STEP_X: 230, VIEW_H: 520 };
  return               { CARD_W: 230, CARD_H: 420, STEP_X: 250, VIEW_H: 580 };
}

// The prize pool, best odds first, with a bar width NORMALISED to the most
// likely plate. Raw percentages on a short bar make 20% and 16% the same
// three pixels — the number stays exact, the bar carries the comparison.
export function poolItems(segments) {
  const list = (Array.isArray(segments) ? segments : [])
    .map((seg) => ({ seg, prob: Number(seg && seg.probability) || 0 }))
    .sort((a, b) => b.prob - a.prob);
  const max = list.reduce((m, it) => (it.prob > m ? it.prob : m), 0);
  return list.map((it) => ({
    ...it,
    barPct: max > 0 ? Math.max(4, Math.round((it.prob / max) * 100)) : 0,
  }));
}

// One plate's odds, printed the way the pool prints them.
export function oddsText(prob) {
  const v = Number(prob);
  if (!Number.isFinite(v) || v <= 0) return "";
  return `${v >= 1 ? v.toFixed(1) : v.toFixed(2)}%`;
}

// Where the strip must travel to land on `segmentIndex`, ALWAYS forward by
// `revolutions` full turns + the delta, from a silently-reset position that is
// visually identical (the strip is `segCount` plates repeated).
export function spinTarget(currentX, STEP_X, segCount, segmentIndex, revolutions = 4) {
  if (!segCount || STEP_X <= 0) return { resetX: 0, targetSteps: 0, targetX: 0 };
  const currentSteps = Math.round(currentX / STEP_X);
  const currentMod = ((currentSteps % segCount) + segCount) % segCount;
  const idx = ((Number(segmentIndex) % segCount) + segCount) % segCount;
  const delta = ((idx - currentMod) + segCount) % segCount;
  const targetSteps = currentMod + revolutions * segCount + delta;
  return { resetX: currentMod * STEP_X, targetSteps, targetX: targetSteps * STEP_X };
}

// Which strip card (repeat-index "r-i") sits under the pointer after a spin.
export function winnerKey(centerIdx, targetSteps, segCount, segmentIndex) {
  const finalStripIdx = centerIdx + targetSteps;
  return `${Math.floor(finalStripIdx / segCount)}-${segmentIndex}`;
}

export function fmtTimeLeft(iso, now = Date.now()) {
  if (!iso) return "";
  const diff = Math.max(0, new Date(iso).getTime() - now);
  if (!Number.isFinite(diff)) return "";
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function relTime(iso, now = Date.now()) {
  if (!iso) return "";
  const diff = Math.max(0, now - new Date(iso).getTime());
  if (!Number.isFinite(diff)) return "";
  const s = Math.floor(diff / 1000);
  if (s < 60) return `hace ${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `hace ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `hace ${h}h`;
  return `hace ${Math.floor(h / 24)}d`;
}

// The spins chip: "2 de 3 hoy" + the Patreon line. `status` is the backend's
// status view (allowance/used_today/left_today/bonus_spins/tier_key).
export const TIER_NAMES = { juvie: "Juvie", sub: "Sub Adult", adult: "Adult", elder: "Elder", apex: "Apex" };

const nat = (v) => { const n = Math.floor(Number(v)); return Number.isFinite(n) && n > 0 ? n : 0; };

export function spinsCopy(status) {
  const st = status || {};
  const left = nat(st.left_today);
  const bonus = nat(st.bonus_spins);
  const allowance = nat(st.allowance);
  const used = nat(st.used_today);
  const available = left + bonus;
  const tier = st.tier_key ? TIER_NAMES[st.tier_key] || st.tier_key : null;
  // `line` sits NEXT TO the big count in the chip, so it never repeats it.
  let line;
  if (st.enabled === false) line = "Ruleta cerrada por el staff";
  else if (available > 0) line = available === 1 ? "giro disponible" : "giros disponibles";
  else line = "Sin giros — vuelve mañana";
  const daily = `${Math.min(used, allowance)} de ${allowance} hoy`;
  const patreon = tier
    ? `Patreon ${tier}: +${st.patreon_bonus || 0} por día`
    : "Patreon: +1 giro diario por nivel";
  return { available, line, daily, patreon, bonus };
}

// One id per ATTEMPT (marketplace client_request_id rule).
export function newCmdId() {
  const rnd = (typeof crypto !== "undefined" && crypto.getRandomValues)
    ? Array.from(crypto.getRandomValues(new Uint8Array(8))).map((b) => b.toString(16).padStart(2, "0")).join("")
    : Math.random().toString(16).slice(2, 18);
  return `w-${Date.now().toString(36)}-${rnd}`;
}

// Reward copy for the reveal card, per kind.
export function rewardLine(reward) {
  const r = reward || {};
  switch (r.kind) {
    case "primemeat": return `+${fmtNum(r.amount)} PrimeMeat en tu cuenta`;
    case "amberium": return `+${fmtNum(r.amount)} Amberium en tu cuenta`;
    case "growth_token": return r.flavor === "premium" ? "Ficha Premium: 70% + PRIME en tu dino en vivo (Inventario → Fichas)" : "Ficha de Crecimiento: 70% en tu dino en vivo (Inventario → Fichas)";
    case "diet_token": return "Ficha de Dieta: +150% en tu dino en vivo (Inventario → Fichas)";
    case "glitch_skin": return `${r.name || "Skin glitch"} en tus skins de recompensa`;
    case "dino_basic": return `${r.name || "Dino"} al 75% en tu Bóveda — entra al juego y pulsa Recuperar`;
    case "dino_prime": return `${r.name || "Dino"} PRIME al 75% en tu Bóveda — entra al juego y pulsa Recuperar`;
    case "gen0_vial": return "Vial GEN-Ø en tu inventario — úsalo cuando quieras transformarte";
    default: return r.text || "";
  }
}
