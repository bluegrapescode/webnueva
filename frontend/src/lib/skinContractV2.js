// Skin contract v2 — the PURE half (no fetching, no React), so every branch the
// live site can hit is testable without a network or a renderer.
//
// The game side publishes two things:
//   GET /api/studio/skin-contract-state  -> tiny, ALWAYS 200 when mounted: is v2 on?
//   GET /api/studio/skin-contract        -> the immutable 761 KB capability table
// and takes POST /api/studio/apply-v2 with all TEN slots.
//
// Everything here is written so that a malformed, hostile or half-published
// answer degrades to "v2 is off" instead of throwing: the studio's v1 editor is
// the fallback and it must never be taken down by this file.

// Canonical order — this is exactly the key order POST /api/studio/apply-v2 expects.
export const V2_SLOTS = [
  "body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display",
  "teeth", "mouth", "claws",
];
// The seven the v1 editor already owns (same names, same 0-1 sRGB numbers it
// already sends on /api/apply) and the three v2 adds.
export const V1_SLOTS = V2_SLOTS.slice(0, 7);
export const V2_NEW_SLOTS = V2_SLOTS.slice(7);

export const V2_SLOT_LABELS = {
  body: "Cuerpo",
  markings: "Marcas",
  flank: "Costado",
  underbelly: "Vientre",
  detail1: "Detalle",
  eyes: "Ojos",
  male_display: "Exhibición Macho",
  teeth: "Dientes",
  mouth: "Boca",
  claws: "Garras",
};

// The engine's three variation keys — the same 2 / 8 / 16 the Glitch Lab uses.
export const V2_VARIATIONS = [2, 8, 16];

// The contract hands themes as bare integers, so the label stays a number too —
// naming them would be inventing product copy the game side never published.
export function themeLabel(i) { return `Tema ${i}`; }

const isIndex = (n) => Number.isInteger(n) && n >= 0;
const clamp01 = (c) => Math.max(0, Math.min(1, c));

// ===== state probe =====

function off(reason) {
  return { enabled: false, reason: String(reason || "unknown"), build: "", slots: [], themes: [] };
}

// Normalizes GET /api/studio/skin-contract-state's body into a verdict the UI can
// trust. ANY shape that isn't a schema_version 2 body with enabled === true and a
// non-empty capability is OFF — a capability that offers zero slots or zero themes
// can't render anything, so it is a disabled contract, not an empty v2 editor.
export function readContractState(body) {
  try {
    if (!body || typeof body !== "object") return off("malformed");
    const c = body.skin_contract;
    if (!c || typeof c !== "object") return off("malformed");
    if (c.schema_version !== 2) return off("schema_mismatch");
    if (c.enabled !== true) {
      return off(typeof c.reason === "string" && c.reason.trim() ? c.reason.trim() : "disabled");
    }
    const slots = V2_SLOTS.filter((s) => Array.isArray(c.slots) && c.slots.includes(s));
    const themes = normalizeIndexList(c.themes);
    if (!slots.length || !themes.length) return off("empty_capability");
    return {
      enabled: true,
      reason: "",
      build: c.build == null ? "" : String(c.build),
      slots,
      themes,
    };
  } catch (e) {
    return off("malformed");
  }
}

// Sorted, de-duplicated, non-negative integers. Anything else in the array is dropped.
export function normalizeIndexList(arr) {
  if (!Array.isArray(arr)) return [];
  const seen = new Set();
  arr.forEach((n) => { if (isIndex(n)) seen.add(n); });
  return [...seen].sort((a, b) => a - b);
}

// ===== capability table readers =====

// Species keys in the manifest are the game's own casing; the editor's key comes
// from the /api/species row, so match case-insensitively rather than miss.
export function speciesEntry(manifest, key) {
  try {
    const species = manifest?.species;
    if (!species || typeof species !== "object") return null;
    const want = String(key || "").trim().toLowerCase();
    if (!want) return null;
    if (species[key] && typeof species[key] === "object") return species[key];
    const hit = Object.keys(species).find((k) => String(k).toLowerCase() === want);
    return hit && typeof species[hit] === "object" ? species[hit] : null;
  } catch (e) {
    return null;
  }
}

// First entry wins for a given index: a table that repeats a pattern index is
// malformed, and picking the first is the only stable answer. Negative /
// non-integer indices are ignored outright.
function patternEntries(manifest, key) {
  const entry = speciesEntry(manifest, key);
  const list = Array.isArray(entry?.patterns) ? entry.patterns : [];
  const byIndex = new Map();
  list.forEach((p) => {
    if (!p || typeof p !== "object" || !isIndex(p.index)) return;
    if (!byIndex.has(p.index)) byIndex.set(p.index, p);
  });
  return byIndex;
}

// Pattern indices this species actually publishes, ascending. Empty = the species
// has nothing v2 can drive (zero patterns is a real, expected state).
export function listPatterns(manifest, key) {
  return [...patternEntries(manifest, key).keys()].sort((a, b) => a - b);
}

function themeEntries(manifest, key, pattern) {
  const p = patternEntries(manifest, key).get(pattern);
  const list = Array.isArray(p?.themes) ? p.themes : [];
  const byIndex = new Map();
  list.forEach((t) => {
    if (!t || typeof t !== "object" || !isIndex(t.index)) return;
    if (!byIndex.has(t.index)) byIndex.set(t.index, t);
  });
  return byIndex;
}

// A theme is offerable only when BOTH the capability's themes array and this
// species+pattern's own theme list allow it. Either side saying no means no.
export function listThemes(manifest, key, pattern, capThemes) {
  const allowed = new Set(normalizeIndexList(capThemes));
  return [...themeEntries(manifest, key, pattern).keys()]
    .filter((i) => allowed.has(i))
    .sort((a, b) => a - b);
}

// The slots this exact species+pattern+theme supports, in canonical order, further
// narrowed by the capability's slot list. A theme that publishes fewer than ten is
// normal — the caller offers only these and leaves the rest at their v1 value.
export function listSupportedSlots(manifest, key, pattern, theme, capSlots) {
  const t = themeEntries(manifest, key, pattern).get(theme);
  const raw = Array.isArray(t?.supported_slots) ? t.supported_slots : [];
  const named = new Set();
  raw.forEach((s) => {
    const name = typeof s === "string" ? s : s && typeof s === "object" ? s.slot : null;
    if (typeof name === "string" && V2_SLOTS.includes(name)) named.add(name);
  });
  const cap = Array.isArray(capSlots) && capSlots.length ? new Set(capSlots) : null;
  return V2_SLOTS.filter((s) => named.has(s) && (!cap || cap.has(s)));
}

// Swatch RGB triples the table suggests for one slot, as hex for <input type=color>.
// The table ships bare [r,g,b] triples with no stated range, so the scale is read
// off the data: any component above 1 means it is a 0-255 triple, otherwise 0-1.
export function listSwatches(manifest, key, pattern, theme, slot, limit = 8) {
  try {
    const t = themeEntries(manifest, key, pattern).get(theme);
    const raw = Array.isArray(t?.supported_slots) ? t.supported_slots : [];
    const hit = raw.find((s) => s && typeof s === "object" && s.slot === slot);
    const sw = Array.isArray(hit?.swatches) ? hit.swatches : [];
    const out = [];
    for (const s of sw) {
      if (out.length >= limit) break;
      if (!Array.isArray(s) || s.length < 3) continue;
      const nums = s.slice(0, 3).map((n) => (typeof n === "number" && Number.isFinite(n) ? n : 0));
      const scale = nums.some((n) => n > 1) ? 255 : 1;
      const hex = `#${nums.map((n) => Math.round(clamp01(n / scale) * 255).toString(16).padStart(2, "0")).join("")}`;
      if (!out.includes(hex)) out.push(hex);
    }
    return out;
  } catch (e) {
    return [];
  }
}

// ===== payload =====

// Same decode the v1 editor uses on /api/apply: DISPLAY (sRGB) 0-1, no gamma
// pre-decode. v2 must not rescale — the server does the one sRGB->linear step.
export function srgb01FromHex(hex) {
  const s = typeof hex === "string" && /^#[0-9a-fA-F]{6}$/.test(hex.trim()) ? hex.trim() : "#ffffff";
  const n = parseInt(s.slice(1), 16);
  return { r: clamp01(((n >> 16) & 255) / 255), g: clamp01(((n >> 8) & 255) / 255), b: clamp01((n & 255) / 255) };
}

// Snap to a real engine variation key — the server refuses anything else.
export function pickVariation(v) {
  const n = Number(v);
  return V2_VARIATIONS.includes(n) ? n : V2_VARIATIONS[0];
}

// Builds the exact POST /api/studio/apply-v2 body: contract_version 2, all TEN
// slots present, every colour carrying "a":1 exactly (any other alpha is refused
// server-side, so alpha is not a v2 control at all).
export function buildApplyV2Body({ pattern, variation, theme, hexColors }) {
  const body = {
    contract_version: 2,
    pattern: isIndex(pattern) ? pattern : 0,
    variation: pickVariation(variation),
    theme: isIndex(theme) ? theme : 0,
  };
  V2_SLOTS.forEach((slot) => {
    body[slot] = { ...srgb01FromHex(hexColors?.[slot]), a: 1 };
  });
  return body;
}

// ===== refusals =====

// Named refusals the game side can hand back on 403/409/503, in Spanish. An
// unmapped token falls through verbatim rather than being swallowed — a reason we
// have never seen is still more useful to the player than a generic failure.
export const V2_REFUSAL_ES = {
  no_writer_capability: "El servidor de juego aún no acepta skins v2.",
  contract_disabled: "El contrato de skins v2 está desactivado ahora mismo.",
  contract_stale: "La tabla de skins cambió — recarga la página.",
  not_in_game: "Despliega un dino primero — se aplica a tu Dino en Vivo.",
  patreon_required: "Aplicar requiere Patreon.",
  tier_insufficient: "Tu nivel de Patreon no incluye el creador de skins.",
  over_budget: "Espera un momento — demasiadas aplicaciones seguidas.",
  rate_limited: "Espera un momento — demasiadas aplicaciones seguidas.",
  cooldown: "Espera un momento antes de volver a aplicar.",
  species_unsupported: "Esta especie no está en la tabla de skins v2.",
  slot_unsupported: "Ese color no está disponible en este tema.",
  theme_unsupported: "Ese tema no está disponible para este patrón.",
  busy: "El servidor está ocupado — inténtalo en un momento.",
};

// Digs the server's own words out of a refusal body ({reason} / {error} / FastAPI's
// {detail}) and translates a known token. Returns "" when there is nothing to show.
export function serverRefusalMessage(data) {
  try {
    const pick = (v) => {
      if (typeof v === "string" && v.trim()) return v.trim();
      if (v && typeof v === "object") {
        return pick(v.reason) || pick(v.error) || pick(v.message) || pick(v.detail);
      }
      return "";
    };
    const raw = pick(data?.reason) || pick(data?.error) || pick(data?.detail) || pick(data?.message);
    if (!raw) return "";
    return V2_REFUSAL_ES[raw] || raw;
  } catch (e) {
    return "";
  }
}
