// The per-species PATTERN COUNT, and the teeth/mouth/claws mask channel map.
//
// ═══ WHY THIS FILE EXISTS ════════════════════════════════════════════════════
// Until 2026-08-25 every pattern lane on this site was hard-clamped to 0..2:
//
//   SkinEditor  <NumBox min={0} max={2}>        the picker
//   SkinEditor  decodeSkinCode  Math.min(2, …)  an imported LIN1- code
//   FleetDinoModel / SpeciesViewer3D            the texture the 3D specimen wears
//   copyLiveSkin                                a copied live design
//
// The game does not stop at three. Build 24664709 publishes 82 patterns over 22
// species and NINE species carry more than three — Omniraptor and Triceratops
// carry six. So a player who picked Pattern 4 in game was shown Pattern 3's
// texture on this website and told nothing, and a shared code carrying pattern 4
// silently imported as pattern 2.
//
// ═══ THE RULE: NEVER OFFER A PATTERN THE ART CANNOT BACK ═════════════════════
// The count below is not a copy of the manifest. It is the statement of WHICH
// PREVIEW ART THIS SITE ACTUALLY SHIPS, which is a different fact and the only
// one that decides whether the 3D specimen renders or 404s. It is keyed by game
// build so it can never outlive its evidence, and:
//
//   • the manifest may only NARROW it, never widen it (Math.min) — a manifest
//     that grows before the art does must not send the viewer at a missing file;
//   • a species this table does not name falls back to LEGACY_PATTERN_COUNT,
//     which is exactly today's live behaviour — a new species is never widened
//     on a guess;
//   • a manifest at any OTHER build is not allowed to change the count at all.
//
// web/frontend/src/lib/skinPatternCatalog.test.js re-derives every number here
// from theisle-framework's canonical skincontract/skin_capabilities.v2.json and
// from the shipped asset list, so a row typed here rather than measured goes red
// before it can reach a player.
//
// The live art is proven separately, over the public edge and WITH A NEGATIVE
// CONTROL, by servers/laislanublar/skinpatterns_20260825/asset_census.py — this
// origin is a React SPA whose catch-all answers 200 for anything, so an asset
// census without a bogus-path control here is worthless.

// Game build these counts and channel maps were measured on.
export const PREVIEW_ART_BUILD = "24664709";

// What every lane on this site did before the widening. An unknown species, an
// unknown build, or a missing table entry all land here — never on a guess.
export const LEGACY_PATTERN_COUNT = 3;

// Patterns per species AT PREVIEW_ART_BUILD, and preview art for every one of
// them is served from /dino-assets/<Species>/pattern_<i>.webp.
export const PATTERN_COUNTS = Object.freeze({
  Allosaurus: 4,
  Austroraptor: 4,
  Beipiaosaurus: 3,
  Carnotaurus: 4,
  Ceratosaurus: 3,
  Deinosuchus: 3,
  Diabloceratops: 3,
  Dilophosaurus: 3,
  Dryosaurus: 3,
  Gallimimus: 3,
  Herrerasaurus: 5,
  Hypsilophodon: 3,
  Kentrosaurus: 3,
  Maiasaura: 3,
  Omniraptor: 6,
  Pachycephalosaurus: 5,
  Pteranodon: 3,
  Stegosaurus: 4,
  Tenontosaurus: 3,
  Triceratops: 6,
  Troodon: 3,
  Tyrannosaurus: 5,
});

// The advanced-slot mask file, one per species, beside the pattern textures.
export const UTILITY_MASK_FILE = "tmc_mask.webp";

// The three slots the utility mask can paint. Order is the contract's.
export const ADVANCED_SLOTS = Object.freeze(["teeth", "mouth", "claws"]);

/* ★★★★★ A PREVIEW MAP IS EVIDENCE, NOT A FILENAME GUESS.
 *
 * Ported unchanged in behaviour from the fleet's own resolver (theisle-framework
 * webcore/frontend/js/shopview.mjs → normalizePreviewChannelMapping /
 * previewChannelMappingFor), because a second copy of this rule is the copy that
 * drifts.
 *
 * Build 24664709 originally shipped Carnotaurus {teeth: "b"}, reached by reading
 * the texture's FILENAME (T_Carno_Adult_Mouth-Claws-Teeth → "r=mouth, g=claws,
 * b=teeth"). Measured off the mesh instead — sample the mask at every body
 * vertex's UV and ask where those vertices sit — channel b on Carnotaurus is the
 * FEET. Carnotaurus p3/t0 is the ONLY row in all 166 species/pattern/theme rows
 * where a player can edit teeth at all, so the fleet's single teeth preview
 * painted toes. The manifest now declares the measured teeth: "r".
 *
 * The table below is that measurement, keyed by build. It is an ASSERTION, not
 * an override: it must AGREE with the manifest. On disagreement the slot is
 * DROPPED, not painted — because the two failures are not symmetric. An absent
 * preview costs a player a picture; a wrong one paints the animal's feet when
 * they asked for its teeth and says nothing. */
export const PREVIEW_CHANNEL_ASSERTIONS = Object.freeze({
  24664709: Object.freeze({
    Carnotaurus: Object.freeze({ teeth: "r" }),
    Dryosaurus: Object.freeze({ claws: "b" }),
    Herrerasaurus: Object.freeze({ mouth: "g", claws: "b" }),
    Omniraptor: Object.freeze({ mouth: "g", claws: "b" }),
    Pachycephalosaurus: Object.freeze({ claws: "b" }),
    Triceratops: Object.freeze({ claws: "b" }),
    Troodon: Object.freeze({ mouth: "g" }),
  }),
});

const isIndex = (n) => Number.isInteger(n) && n >= 0;

// The manifest keys species by the game's own casing and so does /api/species,
// but a lookup must never miss on a case skew — speciesEntry in skinContractV2.js
// resolves the manifest the same way.
const CANONICAL_SPECIES = Object.freeze(
  Object.fromEntries(Object.keys(PATTERN_COUNTS).map((k) => [k.toLowerCase(), k]))
);

/** The table's own name for a species key, or "" when it does not name it. */
export function canonicalSpecies(key) {
  const want = String(key == null ? "" : key).trim().toLowerCase();
  if (!want) return "";
  return CANONICAL_SPECIES[want] || "";
}

/** How many patterns this site SHIPS PREVIEW ART FOR. Never zero: a species the
 *  table does not name keeps today's three, which is what already renders. */
export function artPatternCount(speciesKey) {
  const name = canonicalSpecies(speciesKey);
  const n = name ? PATTERN_COUNTS[name] : undefined;
  return isIndex(n) && n > 0 ? n : LEGACY_PATTERN_COUNT;
}

// The species entry under the manifest's own casing, resolved case-insensitively.
// Returns [canonicalName, entry] or ["", null].
function manifestSpecies(manifest, speciesKey) {
  const species = manifest && manifest.species;
  if (!species || typeof species !== "object" || Array.isArray(species)) return ["", null];
  const want = String(speciesKey == null ? "" : speciesKey).trim().toLowerCase();
  if (!want) return ["", null];
  let name = Object.prototype.hasOwnProperty.call(species, speciesKey) ? speciesKey : null;
  if (name == null) name = Object.keys(species).find((k) => String(k).toLowerCase() === want);
  const entry = name == null ? null : species[name];
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return ["", null];
  return [name, entry];
}

/** The count the manifest declares for a species, or null when it declares none.
 *  Counts the pattern ROWS rather than trusting pattern_count, so a table whose
 *  header disagrees with its own body is read as its body. */
function manifestPatternCount(manifest, speciesKey) {
  try {
    const [, entry] = manifestSpecies(manifest, speciesKey);
    if (!entry || !Array.isArray(entry.patterns)) return null;
    const seen = new Set();
    entry.patterns.forEach((p) => { if (p && isIndex(p.index)) seen.add(p.index); });
    return seen.size ? seen.size : null;
  } catch (e) {
    return null;
  }
}

/** How many patterns to OFFER for a species.
 *
 *  The art table decides; a manifest at the SAME build may narrow it and may
 *  never widen it; a manifest at any other build is ignored for this question
 *  entirely (its species may well have more patterns — this site has no art for
 *  them, and offering one is a 404 wearing a picker). */
export function patternCountFor(manifest, speciesKey) {
  const art = artPatternCount(speciesKey);
  const build = manifest && typeof manifest.build === "string" ? manifest.build : "";
  if (build !== PREVIEW_ART_BUILD) return art;
  const declared = manifestPatternCount(manifest, speciesKey);
  if (declared == null) return art;
  return Math.max(1, Math.min(art, declared));
}

/** Highest offerable pattern index. Always >= 0. */
export function maxPatternIndex(manifest, speciesKey) {
  return patternCountFor(manifest, speciesKey) - 1;
}

/** Force any value onto a real, art-backed pattern index for this species.
 *  Junk, absent, negative and fractional all land on 0 — the same answer every
 *  clamp on this site already gave them. */
export function clampPattern(value, manifest, speciesKey) {
  const n = Math.round(Number(value));
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(maxPatternIndex(manifest, speciesKey), n));
}

/** Accept only explicit one-hot channel declarations, and reject aliases that
 *  would paint two editable regions over the same pixels. A partial map is
 *  valid: an unnamed channel stays visually inert. */
export function normalizePreviewChannelMapping(value) {
  const raw = value && value.assignment ? value.assignment : value;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const out = {};
  const used = new Set();
  for (const slot of ADVANCED_SLOTS) {
    const channel = raw[slot];
    if (channel == null) continue;
    if (channel !== "r" && channel !== "g" && channel !== "b") return null;
    if (used.has(channel)) return null;
    used.add(channel);
    out[slot] = channel;
  }
  return Object.keys(out).length ? out : null;
}

// Reported once per species+slot. A silent drop would look exactly like a
// species that simply has no mask.
const PREVIEW_ASSERTION_WARNED = new Set();

function warnPreviewAssertion(species, slot, declared, measured) {
  const key = `${species}/${slot}`;
  if (PREVIEW_ASSERTION_WARNED.has(key)) return;
  PREVIEW_ASSERTION_WARNED.add(key);
  try {
    // eslint-disable-next-line no-console
    console.warn(`skin preview: manifest says ${species}.${slot}='${declared}' but the `
      + `measured channel is '${measured}' - dropping this slot's preview rather than `
      + "painting a region the mesh contradicts");
  } catch (e) { /* a console that throws must not cost the studio its render */ }
}

/** The channel map a species' preview should actually use: the manifest's own
 *  declaration, with every slot the build-keyed measurement contradicts dropped.
 *  null means "this species has no advanced preview" — render nothing. */
export function previewChannelMappingFor(manifest, speciesKey) {
  try {
    const [name, entry] = manifestSpecies(manifest, speciesKey);
    const material = entry && entry.material;
    const declared = normalizePreviewChannelMapping(material && material.preview_channel_mapping);
    const table = manifest && PREVIEW_CHANNEL_ASSERTIONS[manifest.build];
    const asserted = table && name && Object.prototype.hasOwnProperty.call(table, name)
      ? table[name] : null;
    if (!asserted || !declared) return declared;
    const agreed = {};
    let dropped = false;
    for (const slot of Object.keys(declared)) {
      const measured = asserted[slot];
      if (measured == null || measured === declared[slot]) { agreed[slot] = declared[slot]; continue; }
      warnPreviewAssertion(name, slot, declared[slot], measured);
      dropped = true;
    }
    if (!dropped) return declared;
    return normalizePreviewChannelMapping(agreed);
  } catch (e) {
    return null;
  }
}

/** One-hot vector for a mask channel, as the shader's dot(util, chan) wants.
 *  An unmapped slot gets the zero vector: it contributes nothing, so the region
 *  is inert rather than painted somewhere arbitrary. */
export function utilityChannelVector(channel) {
  if (channel === "r") return [1, 0, 0];
  if (channel === "g") return [0, 1, 0];
  if (channel === "b") return [0, 0, 1];
  return [0, 0, 0];
}

/** The advanced slots that may be PAINTED for this exact species/pattern/theme:
 *  the ones the capability table supports AND the mask has a measured channel
 *  for. Anything else renders nothing — a species with no mouth row must not be
 *  given an invented control.
 *
 *  `supported` is the already-narrowed list from
 *  skinContractV2.listSupportedSlots (capability ∩ table), so this function only
 *  adds the mask question. */
export function paintableAdvancedSlots(mapping, supported) {
  if (!mapping) return [];
  const have = Array.isArray(supported) ? new Set(supported) : null;
  return ADVANCED_SLOTS.filter((s) => mapping[s] && (!have || have.has(s)));
}

/** A STABLE, CONTENT-ADDRESSED key for a channel map.
 *
 *  ★ The reason this exists rather than passing the object around: the studio
 *  panel rebuilds its {teeth:'r',…} on every colour drag, and the 3D viewer
 *  keys the memo that CLONES THE WHOLE SCENE AND RECOMPILES A SHADER PER MESH
 *  on it. Keying on identity would do all of that on every tick of a colour
 *  picker — the exact GL-program leak FleetDinoModel's disposal comment was
 *  written for. Equal maps must produce equal keys, and only a real change to a
 *  channel may produce a different one. */
export function mappingKey(mapping) {
  if (!mapping || typeof mapping !== "object") return "";
  const parts = ADVANCED_SLOTS.map((s) => `${s}:${mapping[s] || ""}`);
  return parts.join(",") === "teeth:,mouth:,claws:" ? "" : parts.join(",");
}

/** URL-safe filename for a pattern index. */
export function patternFile(index) {
  const n = Math.round(Number(index));
  return `pattern_${Number.isFinite(n) && n > 0 ? n : 0}.webp`;
}
