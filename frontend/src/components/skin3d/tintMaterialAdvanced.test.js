/**
 * The teeth / mouth / claws (advanced) lane of the tint material.
 *
 * The one thing that matters more than the feature: WITH NO ADVANCED INPUT THE
 * SHADER MUST BE THE SHADER THAT SHIPPED. Every existing skin on this site is
 * rendered by that string, so a stray space in it is a fleet-wide repaint. The
 * first test below pins it character for character against a frozen copy of the
 * pre-2026-08-25 source.
 */
import * as THREE from "three";
import {
  makeTintedMaterial, updateAdvancedTint, ADVANCED_TINT_SLOTS,
} from "./tintMaterial";
import { utilityChannelVector } from "@/lib/skinPatternCatalog";

// A stub of what three.js hands onBeforeCompile.
function compile(material) {
  const sh = { uniforms: {}, fragmentShader: "void main(){\n#include <map_fragment>\n}" };
  material.onBeforeCompile(sh);
  return sh;
}

const tex = () => new THREE.Texture();
const COLORS = {
  body: { c: "#112233", a: 1 }, markings: { c: "#223344", a: 1 },
  flank: { c: "#334455", a: 1 }, underbelly: { c: "#445566", a: 1 },
  detail1: { c: "#556677", a: 1 }, male_display: { c: "#667788", a: 1 },
  eyes: { c: "#778899", a: 1 },
};

// ── The frozen pre-advanced shader, copied verbatim from the file as it shipped
//    in bundle main.75101664.js. Nothing in this literal may ever change. ──
const LEGACY_HEADER =
  "uniform vec3 cBody,cMarkings,cFlank,cUnderbelly,cDetail1,cMaleDisplay;\n" +
  "uniform float aBody,aMarkings,aFlank,aUnderbelly,aDetail1,aMaleDisplay;\n" +
  "uniform sampler2D uTintMask;\n";
const LEGACY_BODY = `#ifdef USE_MAP
          vec4 sampledDiffuseColor = texture2D( map, vMapUv );
          vec3 mskRGB = texture2D(uTintMask, vMapUv).rgb;
          float r = mskRGB.r, g = mskRGB.g, b = mskRGB.b;
          float wC = (1.-r)*g*b, wM = r*(1.-g)*b, wB = (1.-r)*(1.-g)*b;
          float wG = (1.-r)*g*(1.-b), wY = r*g*(1.-b), wR = r*(1.-g)*(1.-b), wK = (1.-r)*(1.-g)*(1.-b);
          float wSum = max(wC+wM+wB+wG+wY+wR+wK, 0.0001);
          vec3 region = (cBody*wC + cMarkings*wM + cFlank*wB + cUnderbelly*wG + cDetail1*wY + cMaleDisplay*wR + cBody*wK) / wSum;
          float aAvg = (aBody*wC + aMarkings*wM + aFlank*wB + aUnderbelly*wG + aDetail1*wY + aMaleDisplay*wR + aBody*wK) / wSum;
          float lum = dot(sampledDiffuseColor.rgb, vec3(0.299,0.587,0.114));
          vec3 shaded = region * (0.95 + 0.55 * lum);
          sampledDiffuseColor.rgb = mix(sampledDiffuseColor.rgb, shaded, clamp(aAvg, 0.0, 1.0));
          diffuseColor *= sampledDiffuseColor;
        #endif`;
const LEGACY_SHADER = `void main(){\n${LEGACY_HEADER}${LEGACY_BODY}\n}`
  .replace(`void main(){\n${LEGACY_HEADER}`, `${LEGACY_HEADER}void main(){\n`);

describe("★ THE UN-ADVANCED SHADER IS UNCHANGED, CHARACTER FOR CHARACTER", () => {
  const cases = [
    ["no fourth argument at all", undefined],
    ["an explicit null", null],
    ["an empty object", {}],
    ["a mask but no mapping", { texture: tex(), mapping: null }],
    ["a mapping but no mask (a 404 on tmc_mask.webp)", { texture: null, mapping: { claws: "b" } }],
    ["a mapping whose channels are all junk", { texture: tex(), mapping: { claws: "x", mouth: 4 } }],
    ["an empty mapping object", { texture: tex(), mapping: {} }],
  ];

  cases.forEach(([label, advanced]) => {
    test(label, () => {
      const sh = compile(makeTintedMaterial(tex(), tex(), COLORS, advanced));
      expect(sh.fragmentShader).toBe(LEGACY_SHADER);
      expect(sh.fragmentShader).not.toContain("uUtilMask");
      expect(sh.uniforms.uUtilMask).toBeUndefined();
    });
  });

  test("and it declares no advanced slots, so no caller can think it has one", () => {
    const m = makeTintedMaterial(tex(), tex(), COLORS);
    expect(m.userData.advancedSlots).toEqual([]);
    expect(m.userData.tintUniforms.uUtilMask).toBeUndefined();
  });
});

describe("the advanced lane, once a mask and a measured channel exist", () => {
  const advancedFor = (mapping) => ({
    texture: tex(),
    mapping,
    colors: { teeth: { c: "#ff00ff", a: 1 }, mouth: { c: "#00ff00", a: 1 }, claws: { c: "#0000ff", a: 1 } },
  });

  test("a second sampler and three one-hot channel uniforms appear", () => {
    const m = makeTintedMaterial(tex(), tex(), COLORS, advancedFor({ mouth: "g", claws: "b" }));
    const sh = compile(m);
    expect(sh.fragmentShader).toContain("uniform sampler2D uUtilMask;");
    expect(sh.fragmentShader).toContain("float wTe = clamp(dot(util, uTeethChan), 0.0, 1.0);");
    expect(sh.fragmentShader).toContain("float wMo = clamp(dot(util, uMouthChan), 0.0, 1.0);");
    expect(sh.fragmentShader).toContain("float wCl = clamp(dot(util, uClawsChan), 0.0, 1.0);");
    expect(m.userData.advancedSlots).toEqual(["mouth", "claws"]);
  });

  test("the seven base slots are untouched by it — the advanced mix rides ON TOP of `shaded`", () => {
    const sh = compile(makeTintedMaterial(tex(), tex(), COLORS, advancedFor({ teeth: "r" })));
    // Every base line of the legacy body still appears, in the legacy order.
    const legacyLines = LEGACY_BODY.split("\n").filter((l) => l.trim() && !l.includes("shaded, clamp(aAvg"));
    let cursor = 0;
    legacyLines.forEach((line) => {
      const at = sh.fragmentShader.indexOf(line, cursor);
      expect(at).toBeGreaterThanOrEqual(0);
      cursor = at;
    });
    // The advanced block sits AFTER `vec3 shaded = ...` and BEFORE the final mix.
    const shadedAt = sh.fragmentShader.indexOf("vec3 shaded = region");
    const utilAt = sh.fragmentShader.indexOf("vec3 util = texture2D(uUtilMask");
    const mixAt = sh.fragmentShader.indexOf("sampledDiffuseColor.rgb = mix(");
    expect(shadedAt).toBeLessThan(utilAt);
    expect(utilAt).toBeLessThan(mixAt);
  });

  test("★ AN ADVANCED REGION PAINTS AT FULL STRENGTH — a body alpha slider cannot fade the claws", () => {
    const sh = compile(makeTintedMaterial(tex(), tex(), COLORS, advancedFor({ claws: "b" })));
    expect(sh.fragmentShader).toContain("aAvg = max(aAvg, clamp(wTe + wMo + wCl, 0.0, 1.0));");
  });

  test("★ AN UNMAPPED SLOT GETS THE ZERO VECTOR — inert, never painted somewhere arbitrary", () => {
    const m = makeTintedMaterial(tex(), tex(), COLORS, advancedFor({ claws: "b" }));
    const u = m.userData.tintUniforms;
    expect(u.uClawsChan.value.toArray()).toEqual([0, 0, 1]);
    expect(u.uTeethChan.value.toArray()).toEqual([0, 0, 0]);
    expect(u.uMouthChan.value.toArray()).toEqual([0, 0, 0]);
    expect(m.userData.advancedSlots).toEqual(["claws"]);
  });

  test("the channel vectors agree with the catalog's, so the two copies cannot drift", () => {
    ["r", "g", "b", null, "x"].forEach((ch) => {
      const m = makeTintedMaterial(tex(), tex(), COLORS, advancedFor({ teeth: ch }));
      const u = m.userData.tintUniforms;
      const expected = utilityChannelVector(ch);
      if (!u.uTeethChan) { expect(expected).toEqual([0, 0, 0]); return; }
      expect(u.uTeethChan.value.toArray()).toEqual(expected);
    });
  });

  test("a slot with no colour supplied still compiles, on its own fallback", () => {
    const m = makeTintedMaterial(tex(), tex(), COLORS,
      { texture: tex(), mapping: { teeth: "r" }, colors: undefined });
    expect(() => compile(m)).not.toThrow();
    expect(m.userData.tintUniforms.cTeeth.value).toBeInstanceOf(THREE.Color);
  });

  test("two slots claiming one channel is not this file's job to refuse — it paints what it is told", () => {
    // The refusal lives in normalizePreviewChannelMapping, one layer up, and is
    // pinned there. This test exists so nobody adds a SECOND, drifting copy here.
    const m = makeTintedMaterial(tex(), tex(), COLORS, advancedFor({ teeth: "r", mouth: "r" }));
    expect(m.userData.advancedSlots).toEqual(["teeth", "mouth"]);
  });
});

describe("★ THE TWO SHADERS MUST NOT SHARE A PROGRAM CACHE KEY", () => {
  // three.js keys its program cache on customProgramCacheKey(), whose DEFAULT is
  // onBeforeCompile.toString(). This file emits two shaders from one function
  // body, so without an explicit key the renderer hands the second variant the
  // first one's program. Measured live: an Allosaurus with no channel map at all
  // rendered ENTIRELY MAGENTA, because it reused the advanced program, WebGL
  // bound the default white texture to the missing uUtilMask sampler, and cClaws
  // still held the previous material's colour.
  const adv = () => ({ texture: tex(), mapping: { claws: "b" }, colors: {} });

  test("the default (source-text) key would have collided - so an explicit one exists", () => {
    const basic = makeTintedMaterial(tex(), tex(), COLORS);
    const advanced = makeTintedMaterial(tex(), tex(), COLORS, adv());
    expect(typeof basic.customProgramCacheKey).toBe("function");
    expect(basic.onBeforeCompile.toString()).toBe(advanced.onBeforeCompile.toString());
    expect(basic.customProgramCacheKey()).not.toBe(advanced.customProgramCacheKey());
  });

  test("every basic material shares one key and every advanced material shares another", () => {
    const b1 = makeTintedMaterial(tex(), tex(), COLORS).customProgramCacheKey();
    const b2 = makeTintedMaterial(tex(), tex(), {}, { texture: null, mapping: { claws: "b" } })
      .customProgramCacheKey();
    const a1 = makeTintedMaterial(tex(), tex(), COLORS, adv()).customProgramCacheKey();
    const a2 = makeTintedMaterial(tex(), tex(), COLORS, {
      texture: tex(), mapping: { mouth: "g", claws: "b" }, colors: {},
    }).customProgramCacheKey();
    expect(b1).toBe(b2);
    expect(a1).toBe(a2);
    expect(b1).not.toBe(a1);
  });

  test("the key follows the SHADER, not the mapping - channels are uniforms, not defines", () => {
    const one = makeTintedMaterial(tex(), tex(), COLORS, { texture: tex(), mapping: { teeth: "r" }, colors: {} });
    const two = makeTintedMaterial(tex(), tex(), COLORS, { texture: tex(), mapping: { claws: "g" }, colors: {} });
    expect(one.customProgramCacheKey()).toBe(two.customProgramCacheKey());
  });
});

describe("updateAdvancedTint", () => {
  test("repaints the three uniforms in place, with no recompile", () => {
    const m = makeTintedMaterial(tex(), tex(), COLORS, {
      texture: tex(), mapping: { teeth: "r", mouth: "g", claws: "b" },
      colors: { teeth: { c: "#000000" }, mouth: { c: "#000000" }, claws: { c: "#000000" } },
    });
    expect(updateAdvancedTint(m, {
      teeth: { c: "#ff0000" }, mouth: { c: "#00ff00" }, claws: { c: "#0000ff" },
    })).toBe(true);
    const u = m.userData.tintUniforms;
    expect(u.cTeeth.value.getHexString()).toBe("ff0000");
    expect(u.cMouth.value.getHexString()).toBe("00ff00");
    expect(u.cClaws.value.getHexString()).toBe("0000ff");
  });

  test("is a silent no-op on a material with no advanced lane, and on junk", () => {
    expect(updateAdvancedTint(makeTintedMaterial(tex(), tex(), COLORS), { teeth: { c: "#fff" } })).toBe(false);
    [null, undefined, {}, { userData: {} }, { userData: { tintUniforms: {} } }].forEach((m) => {
      expect(updateAdvancedTint(m, {})).toBe(false);
    });
  });

  test("an absent colour falls back rather than throwing", () => {
    const m = makeTintedMaterial(tex(), tex(), COLORS, { texture: tex(), mapping: { claws: "b" } });
    expect(() => updateAdvancedTint(m, null)).not.toThrow();
    expect(() => updateAdvancedTint(m, { claws: null })).not.toThrow();
  });

  test("the slot list is the contract's, in the contract's order", () => {
    expect(ADVANCED_TINT_SLOTS).toEqual(["teeth", "mouth", "claws"]);
  });
});
