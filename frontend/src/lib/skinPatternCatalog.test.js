import {
  PREVIEW_ART_BUILD, LEGACY_PATTERN_COUNT, PATTERN_COUNTS, ADVANCED_SLOTS,
  PREVIEW_CHANNEL_ASSERTIONS, UTILITY_MASK_FILE,
  canonicalSpecies, artPatternCount, patternCountFor, maxPatternIndex, clampPattern,
  normalizePreviewChannelMapping, previewChannelMappingFor, utilityChannelVector,
  paintableAdvancedSlots, patternFile, mappingKey,
} from "./skinPatternCatalog";

// A manifest in the published shape, at the build the art was measured on.
const manifestFor = (build, species) => ({ schema_version: 2, build, species });

const patterns = (n) => Array.from({ length: n }, (_, i) => ({ index: i, themes: [] }));

const AT_BUILD = manifestFor(PREVIEW_ART_BUILD, {
  Omniraptor: {
    pattern_count: 6,
    patterns: patterns(6),
    material: { preview_asset: "Omniraptor/tmc_mask.webp", preview_channel_mapping: { mouth: "g", claws: "b" } },
  },
  Carnotaurus: {
    pattern_count: 4,
    patterns: patterns(4),
    material: { preview_asset: "Carnotaurus/tmc_mask.webp", preview_channel_mapping: { teeth: "r" } },
  },
  Allosaurus: {
    pattern_count: 4,
    patterns: patterns(4),
    material: { preview_asset: "Allosaurus/tmc_mask.webp", preview_channel_mapping: null },
  },
});

describe("the table is the statement of what art ships", () => {
  test("names all 22 species of build 24664709 and every count is at least the legacy 3", () => {
    expect(Object.keys(PATTERN_COUNTS)).toHaveLength(22);
    Object.entries(PATTERN_COUNTS).forEach(([, n]) => {
      expect(Number.isInteger(n)).toBe(true);
      expect(n).toBeGreaterThanOrEqual(LEGACY_PATTERN_COUNT);
    });
  });

  test("the nine species that carry more than three are exactly the ones measured", () => {
    const wide = Object.entries(PATTERN_COUNTS).filter(([, n]) => n > LEGACY_PATTERN_COUNT)
      .map(([k]) => k).sort();
    expect(wide).toEqual([
      "Allosaurus", "Austroraptor", "Carnotaurus", "Herrerasaurus", "Omniraptor",
      "Pachycephalosaurus", "Stegosaurus", "Triceratops", "Tyrannosaurus",
    ]);
    // 16 pattern rows sit at index >= 3 across the fleet; that is the art this wave adds.
    const beyondLegacy = Object.values(PATTERN_COUNTS)
      .reduce((a, n) => a + Math.max(0, n - LEGACY_PATTERN_COUNT), 0);
    expect(beyondLegacy).toBe(16);
    expect(Object.values(PATTERN_COUNTS).reduce((a, n) => a + n, 0)).toBe(82);
  });

  test("the table and the assertions are frozen so nothing can mutate them at runtime", () => {
    expect(Object.isFrozen(PATTERN_COUNTS)).toBe(true);
    expect(Object.isFrozen(PREVIEW_CHANNEL_ASSERTIONS)).toBe(true);
    expect(Object.isFrozen(PREVIEW_CHANNEL_ASSERTIONS[24664709])).toBe(true);
  });
});

describe("artPatternCount", () => {
  test("answers the measured count for a known species, in any casing", () => {
    expect(artPatternCount("Omniraptor")).toBe(6);
    expect(artPatternCount("omniraptor")).toBe(6);
    expect(artPatternCount("  TRICERATOPS  ")).toBe(6);
    expect(artPatternCount("Gallimimus")).toBe(3);
  });

  test("A SPECIES THE TABLE DOES NOT KNOW KEEPS TODAY'S THREE — never a guess", () => {
    expect(artPatternCount("BrandNewDino")).toBe(LEGACY_PATTERN_COUNT);
    expect(artPatternCount("")).toBe(LEGACY_PATTERN_COUNT);
    expect(artPatternCount(null)).toBe(LEGACY_PATTERN_COUNT);
    expect(artPatternCount(undefined)).toBe(LEGACY_PATTERN_COUNT);
    expect(artPatternCount(42)).toBe(LEGACY_PATTERN_COUNT);
    expect(artPatternCount({})).toBe(LEGACY_PATTERN_COUNT);
  });

  test("canonicalSpecies resolves casing and refuses anything it does not name", () => {
    expect(canonicalSpecies("tYRANNOSAURUS")).toBe("Tyrannosaurus");
    expect(canonicalSpecies("Nope")).toBe("");
  });
});

describe("patternCountFor — the manifest may narrow, never widen", () => {
  test("no manifest at all leaves the art table in charge", () => {
    expect(patternCountFor(null, "Omniraptor")).toBe(6);
    expect(patternCountFor(undefined, "Omniraptor")).toBe(6);
    expect(patternCountFor({}, "Omniraptor")).toBe(6);
    expect(patternCountFor({ species: "not an object" }, "Omniraptor")).toBe(6);
  });

  test("a manifest at the art build that agrees changes nothing", () => {
    expect(patternCountFor(AT_BUILD, "Omniraptor")).toBe(6);
    expect(patternCountFor(AT_BUILD, "Carnotaurus")).toBe(4);
  });

  test("★ A MANIFEST THAT DECLARES MORE THAN THE ART CANNOT WIDEN THE PICKER", () => {
    const greedy = manifestFor(PREVIEW_ART_BUILD, { Gallimimus: { patterns: patterns(9) } });
    expect(patternCountFor(greedy, "Gallimimus")).toBe(3);
  });

  test("a manifest that declares FEWER narrows it — the picker must not offer a row the table dropped", () => {
    const shrunk = manifestFor(PREVIEW_ART_BUILD, { Omniraptor: { patterns: patterns(2) } });
    expect(patternCountFor(shrunk, "Omniraptor")).toBe(2);
  });

  test("★ A MANIFEST AT ANOTHER BUILD IS IGNORED FOR THIS QUESTION — its art is not on this box", () => {
    const other = manifestFor("99999999", { Omniraptor: { patterns: patterns(12) } });
    expect(patternCountFor(other, "Omniraptor")).toBe(6);
    const otherSmall = manifestFor("99999999", { Omniraptor: { patterns: patterns(1) } });
    expect(patternCountFor(otherSmall, "Omniraptor")).toBe(6);
  });

  test("a numeric build is not the string build — a skewed type must not silently arm the narrowing", () => {
    const numeric = { schema_version: 2, build: 24664709, species: { Omniraptor: { patterns: patterns(1) } } };
    expect(patternCountFor(numeric, "Omniraptor")).toBe(6);
  });

  test("a species the manifest does not carry falls back to the art table", () => {
    expect(patternCountFor(AT_BUILD, "Stegosaurus")).toBe(4);
  });

  test("an EMPTY pattern list is read as no declaration, never as zero patterns", () => {
    const empty = manifestFor(PREVIEW_ART_BUILD, { Omniraptor: { patterns: [] } });
    expect(patternCountFor(empty, "Omniraptor")).toBe(6);
    expect(maxPatternIndex(empty, "Omniraptor")).toBe(5);
  });

  test("the count is read off the ROWS, not off a pattern_count header that disagrees", () => {
    const lying = manifestFor(PREVIEW_ART_BUILD, { Omniraptor: { pattern_count: 6, patterns: patterns(2) } });
    expect(patternCountFor(lying, "Omniraptor")).toBe(2);
  });

  test("duplicate and junk indices are counted once and ignored respectively", () => {
    const messy = manifestFor(PREVIEW_ART_BUILD, {
      Omniraptor: {
        patterns: [{ index: 0 }, { index: 0 }, { index: 1 }, { index: -3 }, { index: 1.5 }, null, "x"],
      },
    });
    expect(patternCountFor(messy, "Omniraptor")).toBe(2);
  });

  test("a hostile manifest never throws and never widens", () => {
    [[], "manifest", 7, { species: [] }, { species: { Omniraptor: [] } },
      { build: PREVIEW_ART_BUILD, species: { Omniraptor: { patterns: "no" } } }].forEach((m) => {
      expect(() => patternCountFor(m, "Omniraptor")).not.toThrow();
      expect(patternCountFor(m, "Omniraptor")).toBe(6);
    });
  });

  test("the offered count is never below 1", () => {
    const zero = manifestFor(PREVIEW_ART_BUILD, { Omniraptor: { patterns: [{ index: 0 }] } });
    expect(patternCountFor(zero, "Omniraptor")).toBe(1);
    expect(maxPatternIndex(zero, "Omniraptor")).toBe(0);
  });
});

describe("clampPattern — the dangerous direction", () => {
  test("★ EVERY PATTERN A PLAYER ALREADY OWNS (0,1,2) IS UNTOUCHED FOR EVERY SPECIES", () => {
    Object.keys(PATTERN_COUNTS).concat(["UnknownSpecies", "", null]).forEach((sp) => {
      [0, 1, 2].forEach((p) => {
        expect(clampPattern(p, null, sp)).toBe(p);
        expect(clampPattern(p, AT_BUILD, sp)).toBe(p);
      });
    });
  });

  test("a wide species now keeps its real index instead of collapsing onto 2", () => {
    expect(clampPattern(5, null, "Omniraptor")).toBe(5);
    expect(clampPattern(4, null, "Tyrannosaurus")).toBe(4);
    expect(clampPattern(3, null, "Stegosaurus")).toBe(3);
  });

  test("an index beyond the species' count is pulled down to its highest real one", () => {
    expect(clampPattern(9, null, "Omniraptor")).toBe(5);
    expect(clampPattern(9, null, "Gallimimus")).toBe(2);
    expect(clampPattern(3, null, "UnknownSpecies")).toBe(2);
  });

  test("negative, fractional, NaN, boolean, bigint-ish and absent all land on 0", () => {
    [-1, -32, -0.4, NaN, Infinity, -Infinity, undefined, null, "", "abc", {}, [], false]
      .forEach((v) => expect(clampPattern(v, null, "Omniraptor")).toBe(0));
    expect(clampPattern(true, null, "Omniraptor")).toBe(1);   // Number(true) === 1, a real index
    expect(clampPattern("4", null, "Omniraptor")).toBe(4);
    expect(clampPattern(3.6, null, "Omniraptor")).toBe(4);
  });
});

describe("normalizePreviewChannelMapping", () => {
  test("accepts an explicit one-hot map and a partial one", () => {
    expect(normalizePreviewChannelMapping({ teeth: "r" })).toEqual({ teeth: "r" });
    expect(normalizePreviewChannelMapping({ mouth: "g", claws: "b" })).toEqual({ mouth: "g", claws: "b" });
    expect(normalizePreviewChannelMapping({ assignment: { claws: "b" } })).toEqual({ claws: "b" });
  });

  test("★ TWO SLOTS ON ONE CHANNEL IS REFUSED OUTRIGHT — it would paint two regions the same", () => {
    expect(normalizePreviewChannelMapping({ teeth: "r", mouth: "r" })).toBeNull();
  });

  test("a channel that is not r/g/b refuses the whole map", () => {
    expect(normalizePreviewChannelMapping({ teeth: "a" })).toBeNull();
    expect(normalizePreviewChannelMapping({ teeth: 0 })).toBeNull();
    expect(normalizePreviewChannelMapping({ teeth: "R" })).toBeNull();
  });

  test("null, empty, array and non-object are all 'no map'", () => {
    [null, undefined, {}, [], "r", 3, { body: "r" }].forEach((v) => {
      expect(normalizePreviewChannelMapping(v)).toBeNull();
    });
  });
});

describe("previewChannelMappingFor — disagreement DROPS, never overrides", () => {
  test("manifest and measurement agreeing gives the map", () => {
    expect(previewChannelMappingFor(AT_BUILD, "Omniraptor")).toEqual({ mouth: "g", claws: "b" });
    expect(previewChannelMappingFor(AT_BUILD, "Carnotaurus")).toEqual({ teeth: "r" });
  });

  test("★ A MANIFEST THAT CONTRADICTS THE MESH LOSES THAT SLOT — the toes case", () => {
    const warn = jest.spyOn(console, "warn").mockImplementation(() => {});
    const wrong = manifestFor(PREVIEW_ART_BUILD, {
      Dryosaurus: { material: { preview_channel_mapping: { claws: "r" } } },
    });
    expect(previewChannelMappingFor(wrong, "Dryosaurus")).toBeNull();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  test("a species with no declared map has no advanced preview at all", () => {
    expect(previewChannelMappingFor(AT_BUILD, "Allosaurus")).toBeNull();
    expect(previewChannelMappingFor(AT_BUILD, "NotThere")).toBeNull();
    expect(previewChannelMappingFor(null, "Omniraptor")).toBeNull();
  });

  test("a manifest at another build is read exactly as it comes — the assertion cannot outlive its evidence", () => {
    const other = manifestFor("99999999", {
      Dryosaurus: { material: { preview_channel_mapping: { claws: "r" } } },
    });
    expect(previewChannelMappingFor(other, "Dryosaurus")).toEqual({ claws: "r" });
  });

  test("every asserted species declares only slots the contract knows", () => {
    Object.values(PREVIEW_CHANNEL_ASSERTIONS[24664709]).forEach((m) => {
      Object.keys(m).forEach((slot) => expect(ADVANCED_SLOTS).toContain(slot));
      expect(normalizePreviewChannelMapping(m)).toEqual(m);
    });
  });

  test("a hostile manifest never throws", () => {
    [[], "x", 1, { species: 5 }, { species: { Omniraptor: { material: 7 } } }].forEach((m) => {
      expect(() => previewChannelMappingFor(m, "Omniraptor")).not.toThrow();
    });
  });
});

describe("utilityChannelVector / paintableAdvancedSlots", () => {
  test("one-hot per channel, and the zero vector for anything else", () => {
    expect(utilityChannelVector("r")).toEqual([1, 0, 0]);
    expect(utilityChannelVector("g")).toEqual([0, 1, 0]);
    expect(utilityChannelVector("b")).toEqual([0, 0, 1]);
    [null, undefined, "", "a", 0, {}].forEach((c) => expect(utilityChannelVector(c)).toEqual([0, 0, 0]));
  });

  test("★ A SPECIES WITH NO MOUTH ROW RENDERS NOTHING — no invented control", () => {
    expect(paintableAdvancedSlots(null, ["teeth", "mouth", "claws"])).toEqual([]);
    expect(paintableAdvancedSlots({ claws: "b" }, ["mouth"])).toEqual([]);
    expect(paintableAdvancedSlots({ claws: "b" }, [])).toEqual([]);
  });

  test("only slots that are BOTH supported by the row and mapped on the mask are painted", () => {
    expect(paintableAdvancedSlots({ mouth: "g", claws: "b" }, ["claws"])).toEqual(["claws"]);
    expect(paintableAdvancedSlots({ mouth: "g", claws: "b" }, ["mouth", "claws", "teeth"]))
      .toEqual(["mouth", "claws"]);
  });

  test("an absent supported list means the mask alone decides", () => {
    expect(paintableAdvancedSlots({ teeth: "r" }, null)).toEqual(["teeth"]);
    expect(paintableAdvancedSlots({ teeth: "r" }, undefined)).toEqual(["teeth"]);
  });
});

describe("mappingKey — equal maps must key equal", () => {
  test("★ A REBUILT-BUT-IDENTICAL MAP KEYS THE SAME (this is what stops a scene re-clone per colour tick)", () => {
    expect(mappingKey({ mouth: "g", claws: "b" })).toBe(mappingKey({ claws: "b", mouth: "g" }));
    expect(mappingKey({ teeth: "r" })).toBe(mappingKey({ ...{ teeth: "r" } }));
  });

  test("a real channel change keys differently", () => {
    expect(mappingKey({ claws: "b" })).not.toBe(mappingKey({ claws: "g" }));
    expect(mappingKey({ claws: "b" })).not.toBe(mappingKey({ mouth: "b" }));
    expect(mappingKey({ claws: "b" })).not.toBe(mappingKey({ claws: "b", mouth: "g" }));
  });

  test("no map, an empty map and junk all key to the falsy empty string", () => {
    [null, undefined, {}, [], "r", 5, { body: "r" }].forEach((v) => expect(mappingKey(v)).toBe(""));
  });
});

describe("patternFile", () => {
  test("names the file the asset route serves", () => {
    expect(patternFile(0)).toBe("pattern_0.webp");
    expect(patternFile(5)).toBe("pattern_5.webp");
  });

  test("junk can never build a path — it lands on pattern_0", () => {
    [-1, NaN, undefined, null, "x", {}, Infinity].forEach((v) => {
      expect(patternFile(v)).toBe("pattern_0.webp");
    });
  });

  test("the mask filename is the one the manifest declares", () => {
    expect(UTILITY_MASK_FILE).toBe("tmc_mask.webp");
  });
});
