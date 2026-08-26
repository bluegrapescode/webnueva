/**
 * Glitch Lab (2026-08-23 owner order): "custom glitch skin creator with
 * numbers ... make it advanced. website owners and adult elder apex patreon
 * tiers" + the later Streamer-role entitlement + "when copying someone elses
 * skins actually applies to the dino".
 *
 * Pure, dependency-free helpers:
 *   - LIN2- exact skin codes: unlike LIN1- (8-bit sRGB hex + pattern 0..2,
 *     which QUANTIZES normal skins and cannot carry glitch payloads at all),
 *     a LIN2 code carries the raw engine floats VERBATIM (7 slots RGBA +
 *     pattern + variation) — so a shared skin re-applies byte-for-byte.
 *   - the payload validation mirror (kept in lockstep with backend
 *     skin_exact.validate_raw at the glitch-grant level: channel sentinel
 *     allowed, pattern -8 refused, |value| <= 1e12, finite everywhere).
 *   - the randomizer, seeded from the RENDER-PROVEN era families (the owner's
 *     two photographed payloads: rails at hundreds, deep fields to -1e11,
 *     alpha rails, variation keys {2, 8, 16}) — random numbers in bands the
 *     engine has actually been seen to glitch on, never arbitrary noise.
 *
 * Security note: entitlement is NEVER decided here. The backend re-verifies
 * Owner/Streamer/Adult/Elder/Apex on every save and apply; these helpers only shape
 * and validate data. Codes never carry grant keys (owner_grant/glitch_grant
 * are stripped at encode) — the importer's own entitlement is what re-mints
 * a grant, server-side.
 */

export const GLITCH_SLOTS = ["body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display"];
export const GLITCH_SLOT_LABELS = {
  body: "Cuerpo", markings: "Marcas", flank: "Flanco", underbelly: "Vientre",
  detail1: "Detalle", eyes: "Ojos", male_display: "Display",
};
export const GLITCH_CHANNEL_ABS_MAX = 1.0e12;   // backend skin_exact.CHANNEL_ABS_MAX
export const GLITCH_PATTERN_ABS_MAX = 32;       // backend skin_exact.PATTERN_ABS_MAX
export const GLITCH_POISON_PATTERN = -8;        // refused ALWAYS (restart sentinel)
export const GLITCH_VARIATION_KEYS = [2, 8, 16]; // the engine's proven SkinVariation keys

// ---------------------------------------------------------------------------
// validation mirror (glitch-grant level)
// ---------------------------------------------------------------------------

function finite(v) { return typeof v === "number" && Number.isFinite(v); }

/**
 * {ok, reason} for a candidate raw payload at the Glitch Lab's own level.
 * Mirrors backend validate_raw with glitch_grant: channel sentinel band is
 * LEGAL, pattern -8 and anything past the windows refuse. reason names the
 * first offending field ("pattern", "variation", "slot_body", ...).
 */
export function validateGlitchRaw(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { ok: false, reason: "shape" };
  const pat = Number(raw.pattern);
  if (!Number.isFinite(pat) || Math.round(pat) !== pat) return { ok: false, reason: "pattern" };
  if (pat === GLITCH_POISON_PATTERN) return { ok: false, reason: "poison_pattern" };
  if (Math.abs(pat) > GLITCH_PATTERN_ABS_MAX) return { ok: false, reason: "pattern_range" };
  const variation = Number(raw.variation);
  if (!Number.isFinite(variation) || Math.abs(variation) > GLITCH_CHANNEL_ABS_MAX) {
    return { ok: false, reason: "variation" };
  }
  for (const k of GLITCH_SLOTS) {
    const arr = raw[k];
    if (!Array.isArray(arr) || arr.length !== 4) return { ok: false, reason: `slot_${k}` };
    for (const c of arr) {
      const v = Number(c);
      if (!Number.isFinite(v) || Math.abs(v) > GLITCH_CHANNEL_ABS_MAX) return { ok: false, reason: `slot_${k}` };
    }
  }
  return { ok: true, reason: "" };
}

// ---------------------------------------------------------------------------
// field-string model — inputs hold STRINGS so "-1e11" can be typed; parse on use
// ---------------------------------------------------------------------------

/** Default lab state: everything 0, alpha 1, pattern 2, variation 8 (donor keys). */
export function emptyGlitchFields() {
  const slots = {};
  GLITCH_SLOTS.forEach((k) => { slots[k] = ["0", "0", "0", "1"]; });
  return { pattern: "2", variation: "8", slots };
}

/** Raw payload (numbers) -> field strings, for loading an import into the lab. */
export function rawToFields(raw) {
  const f = emptyGlitchFields();
  if (!raw || typeof raw !== "object") return f;
  if (raw.pattern !== undefined) f.pattern = String(raw.pattern);
  if (raw.variation !== undefined) f.variation = String(raw.variation);
  GLITCH_SLOTS.forEach((k) => {
    const arr = raw[k];
    if (Array.isArray(arr) && arr.length >= 4) f.slots[k] = arr.slice(0, 4).map((c) => String(c));
  });
  return f;
}

/**
 * Field strings -> {ok, raw?, reason?}. Numbers parse via Number() (accepts
 * scientific notation); empty/garbage fields fail with the field named so the
 * UI can point at it.
 */
export function fieldsToRaw(fields) {
  if (!fields || typeof fields !== "object") return { ok: false, reason: "shape" };
  const raw = {};
  const pat = Number(String(fields.pattern).trim());
  raw.pattern = pat;
  const variation = Number(String(fields.variation).trim());
  raw.variation = variation;
  for (const k of GLITCH_SLOTS) {
    const arr = (fields.slots || {})[k];
    if (!Array.isArray(arr) || arr.length !== 4) return { ok: false, reason: `slot_${k}` };
    raw[k] = arr.map((s) => Number(String(s).trim()));
  }
  const v = validateGlitchRaw(raw);
  return v.ok ? { ok: true, raw } : { ok: false, reason: v.reason };
}

// ---------------------------------------------------------------------------
// LIN2 exact codes
// ---------------------------------------------------------------------------

export const GLITCH_CODE_PREFIX = "LIN2-";
const GRANT_KEYS = ["owner_grant", "glitch_grant"];

function b64urlEncode(json) {
  const b = typeof btoa === "function" ? btoa(json) : Buffer.from(json, "binary").toString("base64");
  return b.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlDecode(b64u) {
  let b64 = b64u.replace(/-/g, "+").replace(/_/g, "/");
  if (!b64 || /[^A-Za-z0-9+/]/.test(b64)) return null;
  while (b64.length % 4) b64 += "=";
  try { return typeof atob === "function" ? atob(b64) : Buffer.from(b64, "base64").toString("binary"); }
  catch (e) { return null; }
}

/**
 * Raw payload -> "LIN2-…" or null when the payload does not validate. Grant
 * keys are STRIPPED (codes are public text; entitlement is the importer's).
 * JSON carries full float64 precision, so decode(encode(raw)) is exact.
 */
export function encodeGlitchCode(dinoClass, raw) {
  const clean = {};
  if (raw && typeof raw === "object") {
    Object.keys(raw).forEach((k) => { if (!GRANT_KEYS.includes(k)) clean[k] = raw[k]; });
  }
  const v = validateGlitchRaw(clean);
  if (!v.ok) return null;
  const body = { v: 2, d: String(dinoClass || ""), p: clean.pattern, vr: clean.variation, s: {} };
  GLITCH_SLOTS.forEach((k) => { body.s[k] = clean[k].map(Number); });
  return GLITCH_CODE_PREFIX + b64urlEncode(JSON.stringify(body));
}

/**
 * "LIN2-…" -> {dinoClass, raw} or null on ANY malformed/out-of-window input —
 * never throws. The returned raw has NO grant keys by construction.
 */
export function decodeGlitchCode(text) {
  try {
    const trimmed = String(text || "").trim();
    if (!trimmed.startsWith(GLITCH_CODE_PREFIX)) return null;
    const json = b64urlDecode(trimmed.slice(GLITCH_CODE_PREFIX.length));
    if (!json) return null;
    const obj = JSON.parse(json);
    if (!obj || obj.v !== 2 || typeof obj.d !== "string" || !obj.s || typeof obj.s !== "object") return null;
    const raw = { pattern: Number(obj.p), variation: Number(obj.vr) };
    for (const k of GLITCH_SLOTS) {
      const arr = obj.s[k];
      if (!Array.isArray(arr) || arr.length !== 4) return null;
      raw[k] = arr.map(Number);
    }
    return validateGlitchRaw(raw).ok ? { dinoClass: obj.d, raw } : null;
  } catch (e) { return null; }
}

/** True when this raw payload needs the Glitch Lab (any channel in the engine's
 * sentinel band) — the import gate: these need Owner/Streamer/Adult/Elder/Apex. */
export function rawNeedsGlitchLab(raw) {
  if (!raw || typeof raw !== "object") return false;
  const POISON = -900000; // copyLiveSkin.SKIN_POISON_THRESHOLD (kept numeric: pure module)
  for (const k of GLITCH_SLOTS) {
    const arr = raw[k];
    if (Array.isArray(arr) && arr.some((c) => Number(c) <= POISON)) return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// the randomizer — era-proven magnitude families
// ---------------------------------------------------------------------------

/** Named bands the engine has actually been seen to shader-glitch on. */
export const GLITCH_FAMILIES = [
  { id: "rails",  label: "Raíles",   lo: 100, hi: 999 },        // classic ±999-rail era
  { id: "deep",   label: "Profundo", lo: 1e4, hi: 1e8 },        // supernova-family field
  { id: "abyss",  label: "Abismo",   lo: 1e8, hi: 1e11 },       // constelación-family field
  { id: "mixto",  label: "Mixto",    lo: null, hi: null },      // draws from all three
];
// Alpha rails observed across the proven payloads (glitch_catalog docstring).
const ALPHA_RAILS = [-999, -777, -555, -888, -9999, 999, 22000, 33000, -99999];

function pick(rng, arr) { return arr[Math.floor(rng() * arr.length)]; }
function bandValue(rng, lo, hi) {
  // log-uniform magnitude inside the band, random sign — matches how the era
  // payloads spread (values cluster per decade, both signs appear).
  const mag = Math.exp(Math.log(lo) + (Math.log(hi) - Math.log(lo)) * rng());
  const sign = rng() < 0.62 ? -1 : 1; // the proven payloads skew negative
  return Math.round(sign * mag * 1000) / 1000;
}

/**
 * One randomized slot [r,g,b,a] from a family. familyId "mixto" (or unknown)
 * draws each channel from a random concrete family. rng defaults to
 * Math.random; tests inject a deterministic one.
 */
export function randomGlitchSlot(familyId, rng) {
  const r = typeof rng === "function" ? rng : Math.random;
  const concrete = GLITCH_FAMILIES.filter((f) => f.lo !== null);
  const fam = GLITCH_FAMILIES.find((f) => f.id === familyId && f.lo !== null);
  const chan = () => {
    const f = fam || pick(r, concrete);
    return bandValue(r, f.lo, f.hi);
  };
  // ~1 in 4 channels stays an ordinary colour fraction — the proven worn looks
  // mix plain slots with glitch slots, which is what reads as a "design".
  const maybePlain = (v) => (r() < 0.25 ? Math.round(r() * 1000) / 1000 : v);
  return [maybePlain(chan()), maybePlain(chan()), maybePlain(chan()), pick(r, ALPHA_RAILS)];
}

/** A full randomized field set (strings, ready for the lab inputs). */
export function randomGlitchFields(familyId, rng) {
  const r = typeof rng === "function" ? rng : Math.random;
  const f = emptyGlitchFields();
  GLITCH_SLOTS.forEach((k) => { f.slots[k] = randomGlitchSlot(familyId, r).map((c) => String(c)); });
  f.pattern = String(pick(r, [0, 1, 2, 3]));                  // donor patterns incl. proven 3
  f.variation = String(pick(r, GLITCH_VARIATION_KEYS));
  return f;
}

// (glitchProximityStrip removed 2026-08-23 on the owner's order: the folded
// magnitude colours were not representative of the in-game look, so the
// identity card shows the NAME only — no colour claim of any kind.)
