import * as THREE from "three";
import DONOR_DEFAULT_PALETTES from "@/data/skin_default_palettes.json";

// Shared tint-mask colour material + per-species default palette, factored out of
// FleetDinoModel.jsx so SpeciesViewer3D.jsx (MyDino's live viewer) can reuse the
// SAME material/colour code without a circular import between the two files
// (FleetDinoModel already imports loadSpeciesGlb/pickIdleClip FROM SpeciesViewer3D).
// FleetDinoModel.jsx re-exports these names unchanged, so every existing import
// site (SkinEditor.jsx) keeps working exactly as before.

// Colour slots the fleet skin designer exposes — matches POST /api/apply's
// colors:{body,markings,flank,underbelly,detail1,eyes,male_display} shape 1:1.
// "eyes" is intentionally excluded from FLEET_SLOTS (rendered through the tint-mask
// shader below): the donor ports eyes as a separate emissive material keyed off the
// mesh/material name, matching how these GLBs actually split eye geometry out.
export const FLEET_SLOTS = ["body", "markings", "flank", "underbelly", "detail1", "male_display"];
export const DEFAULT_FLEET_COLORS = {
  body: { c: "#8a6b45", a: 1 },
  markings: { c: "#2a2118", a: 1 },
  flank: { c: "#a67c4e", a: 1 },
  underbelly: { c: "#d9c9a8", a: 1 },
  detail1: { c: "#5c3f26", a: 1 },
  male_display: { c: "#c9c9c9", a: 1 },
  eyes: { c: "#e2c53a", a: 1 },
};

const colorOf = (colors, key, fallback) => new THREE.Color(colors?.[key]?.c || fallback);
const alphaOf = (colors, key) => (typeof colors?.[key]?.a === "number" ? colors[key].a : 1);

// ── Per-species default palettes ────────────────────────────────────────────
// Donor file (skin_default_palettes.json from the donor skin site)
// ports game-default CustomizerData tuples per species, already remapped from raw engine
// layer names to IPC channel names by its own `_schema.layer_to_ipc_mapping`
// (Color1_RedLayer->male_display, Color2_GreenLayer->underbelly, Color3_BlueLayer->flank,
// Color4_CyanLayer->body, Color5_MagentaLayer->markings, Color6_YellowLayer->detail1).
// Those IPC names are IDENTICAL to this file's FLEET_SLOTS + "eyes" keys, so no further
// remapping is needed here — each entry is {body,markings,flank,underbelly,detail1,
// male_display,eyes: [r,g,b,a]} and maps 1:1 onto the editor's channels.
//
// ★COLOUR-SPACE CONTRACT (2026-08-11 LINEAR RESTORE) — THE PALETTE TABLE IS IN
// CustomizerData's SPACE, AND THAT SPACE IS LINEAR.
//
// The measured half of this comment has never moved and still holds: the table's
// numbers ARE the game's own CustomizerData numbers. LIN's own birth captures say
// so — 35 birth rows across 14 species (the engine reading CustomizerData back for
// a native creation skin) match the palette table's floats 23 times and a
// transformed copy of them 0 times, identical 23/0 against the pre-08-09 control,
// plus 5/0 from skin_snapshots.json; fleet-wide 3,405/0 over 15 owners.
//
// ★What was WRONG from 2026-08-09 to 2026-08-11 was the second step: reading
// "table == CustomizerData" as "table == the PICKER's fractions". CustomizerData's
// colour slots are `FLinearColor`, which UE consumes LINEAR by definition, so the
// table is a table of LINEAR floats and a colour picker — which speaks sRGB bytes —
// must DISPLAY it through lin2srgb. Seeding it raw is what made the studio open
// DARK (Tyrannosaurus.body 0.25 -> #402d1a instead of #897559) and it is the
// display half of the same reversal that put the backend wire back on one
// srgb->linear encode (server.py::SkinPayloadIn.to_command). The two must agree:
// the seed a player sees and the float the emitter writes are the same colour.
// ★NEVER encode on the way OUT. The studio's outbound wire stays raw picker
// fractions (SkinEditor's srgb01FromHex) and the backend owns the single encode;
// a frontend that encodes too is the DOUBLE ENCODE that produced the fleet's
// original "one part of the body goes dark".
// ★Deciding it again on some other owner/table is a BIRTH-CAPTURE question, never
// a naming or filename question (both spaces are arbitrary floats): compare FLOATS
// not formatted strings, and filter slots whose channels are all 0.0/1.0 — lin2srgb
// fixes 0 and 1, so black and white match their own brightened form and inflate the
// tally. Same contract, same wording, as theisle-framework's canonical
// `home/web-shared/terminal-theme/studio/skinwire.mjs` defaultsFor().
const PALETTE_INDEX = Object.fromEntries(
  Object.entries(DONOR_DEFAULT_PALETTES)
    .filter(([k]) => k !== "_schema")
    .map(([k, v]) => [k.toLowerCase(), v])
);

// ★SPLIT CONVERTER, NEVER A FLIPPED SHARED HELPER. Two converters live here on
// purpose and they must stay two: `linearToHex` is the DISPLAY one (a stored/tabled
// linear float -> the sRGB byte a picker or a 3D preview shows) and `rawToHex` is
// the gamma-free one (a value that is ALREADY in picker space -> its own byte).
// Under the 2026-08-11 linear restore both the seed and SpeciesViewer3D's live
// preview are display lanes, so both go through `linearToHex`; `rawToHex` stays
// exported and pinned because the moment some lane genuinely holds picker-space
// floats, POINTING IT AT `rawToHex` is the fix — editing the body of `linearToHex`
// is not. Flipping one shared helper to serve both is how a colour fix silently
// repaints a second lane it was never measured against.
// tintMaterial.test.js pins both, in both directions.
function linearToSrgb(c) {
  const v = Math.max(0, Math.min(1, c));
  return v <= 0.0031308 ? v * 12.92 : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
}
export function linearToHex([r, g, b, a]) {
  const toByte = (c) => Math.round(linearToSrgb(c) * 255).toString(16).padStart(2, "0");
  return { c: `#${toByte(r)}${toByte(g)}${toByte(b)}`, a: typeof a === "number" ? a : 1 };
}

// Raw picker fraction -> hex. NO transfer function, by the colour-space contract above.
// Canonical shape: theisle-framework `home/web-shared/terminal-theme/studio/skinwire.mjs`
// rawToHex() — clamp to 0..1, round(v * 255), two hex digits — which is byte-exact with
// the fleet's field-proven exporter. Alpha is carried through unchanged (the editor's
// per-slot alpha slider is not part of the colour space).
export function rawToHex([r, g, b, a]) {
  const toByte = (c) => Math.round(Math.max(0, Math.min(1, c)) * 255).toString(16).padStart(2, "0");
  return { c: `#${toByte(r)}${toByte(g)}${toByte(b)}`, a: typeof a === "number" ? a : 1 };
}

// Seed the colour picker from the game's own per-species default, falling back to
// DEFAULT_FLEET_COLORS (below) when the species has no palette entry.
// ★Seeds through `linearToHex`: the table is CustomizerData's own LINEAR floats and a
// picker speaks sRGB bytes (contract above; reverts 5ff6c98, which was correct under
// the retired raw contract and is wrong under this one).
export function getSpeciesDefaultColors(species) {
  const key = (typeof species === "string" ? species : (species?.slug || species?.name || species?.id) || "").toLowerCase();
  const entry = PALETTE_INDEX[key];
  if (!entry) return DEFAULT_FLEET_COLORS;
  const out = {};
  [...FLEET_SLOTS, "eyes"].forEach((k) => { out[k] = entry[k] ? linearToHex(entry[k]) : DEFAULT_FLEET_COLORS[k]; });
  return out;
}

// The teeth / mouth / claws slots the SECOND mask sampler can paint, in contract order.
export const ADVANCED_TINT_SLOTS = ["teeth", "mouth", "claws"];
const ADVANCED_UNIFORM = { teeth: "cTeeth", mouth: "cMouth", claws: "cClaws" };
const ADVANCED_CHANNEL_UNIFORM = { teeth: "uTeethChan", mouth: "uMouthChan", claws: "uClawsChan" };
const ADVANCED_FALLBACK = { teeth: "#ffffff", mouth: "#7a3b3b", claws: "#d8d2c4" };

// One-hot channel picker for the utility mask. An unmapped slot gets the ZERO
// vector, so its weight is dot(util, 0) == 0 everywhere: the region is inert
// rather than painted over some arbitrary channel. Kept here (not imported from
// skinPatternCatalog) so this file stays a leaf with no dependency on the
// contract reader — the catalog exports the identical function and
// tintMaterial.test.js pins the two against each other.
function channelVector(channel) {
  if (channel === "r") return new THREE.Vector3(1, 0, 0);
  if (channel === "g") return new THREE.Vector3(0, 1, 0);
  if (channel === "b") return new THREE.Vector3(0, 0, 1);
  return new THREE.Vector3(0, 0, 0);
}

// Ported minimal core from the donor skin site (skin/index.inline1.module.js:253-294):
// a per-pixel UV tint-mask texture classifies each surface point into one of the RGB
// cube's 7 usable corners; each corner is wired to a colour slot; the diffuse texture's
// luminance survives as shading detail under the flat tint. Extended here with a
// per-slot alpha (matches the colour-picker's existing alpha slider) that blends
// between the original diffuse pixel and the tinted one.
//
// ═══ THE ADVANCED (teeth / mouth / claws) LANE, 2026-08-25 ═══════════════════
// The seven base slots are all the RGB cube has room for: its eight corners are
// spoken for, so a re-authored base mask cannot carry three more regions. The
// contract's answer — and the fleet's, in webcore/frontend/js/shopview.mjs's
// makeTintedMaterial, which this mirrors — is a SECOND sampler: `uUtilMask`
// (<Species>/tmc_mask.webp), read with three INDEPENDENT one-hot channels. Three
// channels, three regions, no competition with the seven.
//
// ★ IT IS STRICTLY ADDITIVE. `advanced` absent, or carrying no texture, or
// carrying no mapped slot, produces the EXACT fragment shader this file produced
// before the lane existed — byte for byte, pinned by
// tintMaterial.test.js ("the un-advanced shader is unchanged"). So a species with
// no mask, a 404 on the mask, or a contract that is off all render exactly as
// today, with no branch a player can see.
//
// ★ AN ADVANCED REGION PAINTS AT FULL STRENGTH. The outer blend is the base
// slots' own alpha average (`aAvg`); teeth/mouth/claws have no alpha control at
// all — the contract pins every v2 colour to a:1 and the server refuses anything
// else — so leaving them under `aAvg` would let a player's *body* alpha slider
// silently fade the claws they just picked. `aAvg` is lifted by the advanced
// weight instead.
//
// @param advanced {{texture: THREE.Texture, mapping: Object, colors: Object}=}
export function makeTintedMaterial(diffuseTex, maskTex, colors, advanced) {
  const m = new THREE.MeshStandardMaterial({ map: diffuseTex, roughness: 0.62, metalness: 0.05 });
  const u = {
    cBody: { value: colorOf(colors, "body", "#8a6b45") },
    cMarkings: { value: colorOf(colors, "markings", "#2a2118") },
    cFlank: { value: colorOf(colors, "flank", "#a67c4e") },
    cUnderbelly: { value: colorOf(colors, "underbelly", "#d9c9a8") },
    cDetail1: { value: colorOf(colors, "detail1", "#5c3f26") },
    cMaleDisplay: { value: colorOf(colors, "male_display", "#c9c9c9") },
    aBody: { value: alphaOf(colors, "body") },
    aMarkings: { value: alphaOf(colors, "markings") },
    aFlank: { value: alphaOf(colors, "flank") },
    aUnderbelly: { value: alphaOf(colors, "underbelly") },
    aDetail1: { value: alphaOf(colors, "detail1") },
    aMaleDisplay: { value: alphaOf(colors, "male_display") },
    uTintMask: { value: maskTex },
  };

  // A slot counts as advanced only when the mask exists AND that slot has a
  // measured channel on it. Anything else stays out of the shader entirely.
  const mapping = (advanced && advanced.mapping) || null;
  const utilTex = (advanced && advanced.texture) || null;
  const liveSlots = utilTex && mapping
    ? ADVANCED_TINT_SLOTS.filter((s) => mapping[s] === "r" || mapping[s] === "g" || mapping[s] === "b")
    : [];
  const useAdvanced = liveSlots.length > 0;

  if (useAdvanced) {
    u.uUtilMask = { value: utilTex };
    ADVANCED_TINT_SLOTS.forEach((slot) => {
      u[ADVANCED_UNIFORM[slot]] = {
        value: colorOf(advanced.colors, slot, ADVANCED_FALLBACK[slot]),
      };
      // A slot the mask does not carry keeps the zero vector, so it contributes
      // nothing even though its uniform exists.
      u[ADVANCED_CHANNEL_UNIFORM[slot]] = {
        value: channelVector(liveSlots.includes(slot) ? mapping[slot] : null),
      };
    });
  }

  m.userData.tintUniforms = u;
  m.userData.advancedSlots = liveSlots;

  // ★★★★★ TWO SHADERS OUT OF ONE `onBeforeCompile` NEED TWO PROGRAM CACHE KEYS.
  //
  // three.js keys its compiled-program cache on `customProgramCacheKey()`, whose
  // DEFAULT is `onBeforeCompile.toString()` - the function's SOURCE TEXT. This
  // file emits two different fragment shaders out of one function body, so both
  // variants hash to the same key and the renderer hands the second one the
  // FIRST one's program. Two ways that shows, and both were measured live on
  // 2026-08-25 before this line existed:
  //
  //   * basic compiled first -> the advanced material reuses it, there is no
  //     `uUtilMask` sampler at all, and teeth/mouth/claws paint NOTHING;
  //   * advanced compiled first -> a basic material reuses it, `uUtilMask` is
  //     never uploaded so WebGL binds the default WHITE texture, every channel
  //     reads 1.0, and `cClaws` still holds the previous material's value -
  //     THE WHOLE ANIMAL TURNS THAT COLOUR. An Allosaurus, which has no
  //     measured channel map and correctly showed no claws row, rendered
  //     entirely magenta.
  //
  // Which one you get depends only on which species the player clicked first,
  // which is why this flapped between "the feature does nothing" and "the
  // feature paints everything" on identical code.
  m.customProgramCacheKey = () => (useAdvanced ? "lin-tint-v2-advanced" : "lin-tint-v1-basic");

  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, u);
    const advancedHeader = useAdvanced
      ? "uniform vec3 cTeeth,cMouth,cClaws;\nuniform sampler2D uUtilMask;\n"
        + "uniform vec3 uTeethChan,uMouthChan,uClawsChan;\n"
      : "";
    const advancedMix = useAdvanced ? `
          vec3 util = texture2D(uUtilMask, vMapUv).rgb;
          float wTe = clamp(dot(util, uTeethChan), 0.0, 1.0);
          float wMo = clamp(dot(util, uMouthChan), 0.0, 1.0);
          float wCl = clamp(dot(util, uClawsChan), 0.0, 1.0);
          shaded = mix(shaded, cTeeth * (0.95 + 0.55 * lum), wTe);
          shaded = mix(shaded, cMouth * (0.95 + 0.55 * lum), wMo);
          shaded = mix(shaded, cClaws * (0.95 + 0.55 * lum), wCl);
          aAvg = max(aAvg, clamp(wTe + wMo + wCl, 0.0, 1.0));` : "";
    sh.fragmentShader =
      "uniform vec3 cBody,cMarkings,cFlank,cUnderbelly,cDetail1,cMaleDisplay;\n" +
      "uniform float aBody,aMarkings,aFlank,aUnderbelly,aDetail1,aMaleDisplay;\n" +
      "uniform sampler2D uTintMask;\n" + advancedHeader +
      sh.fragmentShader.replace(
        "#include <map_fragment>",
        `#ifdef USE_MAP
          vec4 sampledDiffuseColor = texture2D( map, vMapUv );
          vec3 mskRGB = texture2D(uTintMask, vMapUv).rgb;
          float r = mskRGB.r, g = mskRGB.g, b = mskRGB.b;
          float wC = (1.-r)*g*b, wM = r*(1.-g)*b, wB = (1.-r)*(1.-g)*b;
          float wG = (1.-r)*g*(1.-b), wY = r*g*(1.-b), wR = r*(1.-g)*(1.-b), wK = (1.-r)*(1.-g)*(1.-b);
          float wSum = max(wC+wM+wB+wG+wY+wR+wK, 0.0001);
          vec3 region = (cBody*wC + cMarkings*wM + cFlank*wB + cUnderbelly*wG + cDetail1*wY + cMaleDisplay*wR + cBody*wK) / wSum;
          float aAvg = (aBody*wC + aMarkings*wM + aFlank*wB + aUnderbelly*wG + aDetail1*wY + aMaleDisplay*wR + aBody*wK) / wSum;
          float lum = dot(sampledDiffuseColor.rgb, vec3(0.299,0.587,0.114));
          vec3 shaded = region * (0.95 + 0.55 * lum);${advancedMix}
          sampledDiffuseColor.rgb = mix(sampledDiffuseColor.rgb, shaded, clamp(aAvg, 0.0, 1.0));
          diffuseColor *= sampledDiffuseColor;
        #endif`
      );
  };
  return m;
}

/** Push a fresh teeth/mouth/claws colour set into a material this file built.
 *  A material with no advanced lane is a no-op, so the caller never has to ask. */
export function updateAdvancedTint(material, advancedColors) {
  const u = material && material.userData && material.userData.tintUniforms;
  if (!u || !u.uUtilMask) return false;
  ADVANCED_TINT_SLOTS.forEach((slot) => {
    const holder = u[ADVANCED_UNIFORM[slot]];
    if (holder && holder.value && holder.value.set) {
      holder.value.set(colorOf(advancedColors, slot, ADVANCED_FALLBACK[slot]));
    }
  });
  return true;
}
