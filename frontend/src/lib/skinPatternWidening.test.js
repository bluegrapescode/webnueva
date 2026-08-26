/**
 * The pattern widening, at the four places it actually reaches a player.
 *
 * The behaviour of the rule itself is pinned in skinPatternCatalog.test.js. This
 * file pins that the four lanes CALL it — three of them live inside
 * pages/SkinEditor.jsx and components/skin3d/*, which drag three.js and React
 * Three Fiber in with them, so they are read as source text, the same technique
 * copyLiveSkin.test.js already uses to pin that page's imports. A text pin is a
 * weak instrument (it cannot see a duplicate declaration, and it is not a
 * substitute for the rendered proof), so every rule it points at is separately
 * proven by execution below or in the catalog suite.
 */
import fs from "fs";
import path from "path";
import { snapshotToEditorSkin } from "./copyLiveSkin";
import { PATTERN_COUNTS, LEGACY_PATTERN_COUNT } from "./skinPatternCatalog";

const read = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const PAGE = read("pages/SkinEditor.jsx");
const FLEET = read("components/skin3d/FleetDinoModel.jsx");
const VIEWER = read("components/skin3d/SpeciesViewer3D.jsx");
const COPY = read("lib/copyLiveSkin.js");
const PANEL = read("components/skin3d/SkinContractV2Panel.jsx");

const DEFAULTS = {
  body: { c: "#000000", a: 1 }, markings: { c: "#000000", a: 1 },
  flank: { c: "#000000", a: 1 }, underbelly: { c: "#000000", a: 1 },
  detail1: { c: "#000000", a: 1 }, male_display: { c: "#000000", a: 1 },
  eyes: { c: "#000000", a: 1 },
};
const snap = (pattern) => ({
  pattern,
  body: [0.5, 0.5, 0.5, 1], markings: [0.4, 0.4, 0.4, 1], flank: [0.3, 0.3, 0.3, 1],
  underbelly: [0.2, 0.2, 0.2, 1], detail1: [0.1, 0.1, 0.1, 1],
  male_display: [0.6, 0.6, 0.6, 1], eyes: [0.7, 0.7, 0.7, 1],
});

describe("★ NOT ONE HARD-CODED 0..2 PATTERN CLAMP IS LEFT IN A LIVE LANE", () => {
  test("the picker's ceiling is the species' own, not the literal 2", () => {
    expect(PAGE).toContain('<NumBox label="Patrón" value={pattern} min={0} max={patternMax}');
    expect(PAGE).not.toContain('label="Patrón" value={pattern} min={0} max={2}');
  });

  test("an imported LIN1- code is clamped against the code's OWN species", () => {
    expect(PAGE).toContain("clampPattern(obj.p, null, bareClass(obj.d))");
    expect(PAGE).not.toMatch(/Math\.min\(2, obj\.p\)/);
  });

  test("the Glitch Lab's display payload uses the same rule", () => {
    expect(PAGE).toContain("const payload = { pattern: clampPattern(fields.pattern, null, selKey) };");
  });

  test("both 3D lanes resolve the index through the catalog", () => {
    expect(FLEET).toContain("const patternIdx = clampPattern(pattern, manifest, species);");
    expect(FLEET).toContain("patternFile(patternIdx)");
    expect(VIEWER).toContain("const patternIdx = clampPattern(resolved.pattern, null, species);");
    expect(FLEET).not.toMatch(/Math\.min\(2, pattern/);
    expect(VIEWER).not.toMatch(/Math\.min\(2, Number\(resolved\.pattern\)/);
  });

  test("every copy-live callsite now names the species", () => {
    // Balanced-paren extraction: `getSpeciesDefaultColors(...)` is nested inside
    // the call, so a lazy /\([^)]*\)/ reads a TRUNCATED argument list and would
    // report a widened callsite as un-widened (it did, first run).
    const calls = [];
    let at = PAGE.indexOf("snapshotToEditorSkin(");
    while (at !== -1) {
      let i = PAGE.indexOf("(", at);
      let depth = 0;
      for (; i < PAGE.length; i += 1) {
        if (PAGE[i] === "(") depth += 1;
        else if (PAGE[i] === ")") { depth -= 1; if (depth === 0) break; }
      }
      calls.push(PAGE.slice(at, i + 1));
      at = PAGE.indexOf("snapshotToEditorSkin(", i);
    }
    expect(calls.length).toBe(3);
    calls.forEach((c) => {
      // Top-level commas only — the ones that separate the call's own arguments.
      let depth = 0;
      let args = 1;
      for (const ch of c.slice("snapshotToEditorSkin".length)) {
        if (ch === "(") depth += 1;
        else if (ch === ")") depth -= 1;
        else if (ch === "," && depth === 1) args += 1;
      }
      expect(args).toBe(3);
    });
  });

  test("switching species pulls an out-of-range pattern back in", () => {
    expect(PAGE).toContain("setPattern((p) => clampPattern(p, null, selKey));");
  });

  test("★ THE SCENE MEMO IS KEYED ON THE MAPPING'S CONTENT, NOT ITS IDENTITY", () => {
    // The panel rebuilds its {teeth:'r',…} on every colour drag. Keying the memo
    // that clones the scene on that object would recompile a shader per mesh on
    // every tick of a colour picker.
    expect(FLEET).toContain("const mapKey = mappingKey(advancedMapping);");
    expect(FLEET).toContain("[utilTex, mapKey]);");
    expect(FLEET).not.toContain("[utilTex, advancedMapping]);");
  });

  test("★ THE ADVANCED MAP IS DROPPED BY NAME WHEN IT IS NOT THIS SPECIES'", () => {
    // Measured 2026-08-25: switching a magenta-clawed Omniraptor to Allosaurus
    // (no measured channel at all) left 1,130 magenta pixels on the Allosaurus,
    // because the viewer remounts one commit before the panel's effect can clear
    // the map. A species-scoped read makes that unrepresentable.
    expect(PANEL).toContain("onAdvancedPreview({ species: speciesKey, mapping, colors: painted });");
    expect(PAGE).toContain("const v2AdvancedForSpecies = (v2Advanced && v2Advanced.species === selKey) ? v2Advanced : null;");
    expect(PAGE).toContain("advancedColors={v2AdvancedForSpecies?.colors || null}");
    expect(PAGE).toContain("advancedMapping={v2AdvancedForSpecies?.mapping || null}");
    expect(PAGE).not.toContain("advancedMapping={v2Advanced?.mapping");
  });

  test("a 404 on a pattern or a mask degrades, it does not blank the viewer", () => {
    expect(FLEET).toContain("function useOptionalTexture(url)");
    expect(FLEET).toContain("const maskTex = patternTex || fallbackTex;");
    // The mask is only ever requested when a channel map exists for the species.
    expect(FLEET).toContain('useOptionalTexture(advancedMapping ? dinoAssetUrl(species, UTILITY_MASK_FILE) : "")');
  });
});

describe("snapshotToEditorSkin — the species decides how far a pattern travels", () => {
  test("★ AN EXISTING CALLER THAT NAMES NO SPECIES KEEPS THE OLD CEILING OF 2", () => {
    expect(snapshotToEditorSkin(snap(5), DEFAULTS).pattern).toBe(2);
    expect(snapshotToEditorSkin(snap(5), DEFAULTS, undefined).pattern).toBe(2);
    expect(snapshotToEditorSkin(snap(5), DEFAULTS, null).pattern).toBe(2);
  });

  test("a wide species keeps the pattern it is actually wearing", () => {
    expect(snapshotToEditorSkin(snap(5), DEFAULTS, "Omniraptor").pattern).toBe(5);
    expect(snapshotToEditorSkin(snap(4), DEFAULTS, "Tyrannosaurus").pattern).toBe(4);
    expect(snapshotToEditorSkin(snap(3), DEFAULTS, "Carnotaurus").pattern).toBe(3);
  });

  test("a three-pattern species is untouched, and so is an unknown one", () => {
    expect(snapshotToEditorSkin(snap(5), DEFAULTS, "Gallimimus").pattern).toBe(2);
    expect(snapshotToEditorSkin(snap(5), DEFAULTS, "SomethingNew").pattern).toBe(2);
  });

  test("★ PATTERNS PLAYERS ALREADY OWN (0,1,2) ARE UNCHANGED ON EVERY SPECIES", () => {
    Object.keys(PATTERN_COUNTS).forEach((sp) => {
      [0, 1, 2].forEach((p) => expect(snapshotToEditorSkin(snap(p), DEFAULTS, sp).pattern).toBe(p));
    });
  });

  test("the restart sentinel and glitch negatives still land on 0", () => {
    [-8, -32, -1, NaN, "x", undefined].forEach((p) => {
      expect(snapshotToEditorSkin(snap(p), DEFAULTS, "Omniraptor").pattern).toBe(0);
    });
  });

  test("a poisoned or empty snapshot still refuses, widening or not", () => {
    expect(snapshotToEditorSkin(null, DEFAULTS, "Omniraptor").ok).toBe(false);
    expect(snapshotToEditorSkin({ pattern: 4 }, DEFAULTS, "Omniraptor")).toEqual({ ok: false, reason: "poisoned" });
  });

  test("the module stayed pure — it imports only the catalog, not the 3D tree", () => {
    const imports = COPY.match(/^import .*$/gm) || [];
    expect(imports).toEqual(['import { clampPattern } from "@/lib/skinPatternCatalog";']);
  });
});

describe("the widening is a real change, not a no-op", () => {
  test("nine species gain rows and thirteen do not", () => {
    const wide = Object.values(PATTERN_COUNTS).filter((n) => n > LEGACY_PATTERN_COUNT).length;
    expect(wide).toBe(9);
    expect(Object.keys(PATTERN_COUNTS).length - wide).toBe(13);
  });
});
