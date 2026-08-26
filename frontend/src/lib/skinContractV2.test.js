import {
  V2_SLOTS, V1_SLOTS, V2_NEW_SLOTS, V2_VARIATIONS, themeLabel,
  readContractState, normalizeIndexList, speciesEntry, listPatterns, listThemes,
  listSupportedSlots, listSwatches, srgb01FromHex, pickVariation, buildApplyV2Body,
  serverRefusalMessage,
} from "./skinContractV2";

const ON = {
  ok: true,
  skin_contract: { schema_version: 2, enabled: true, build: "918", slots: V2_SLOTS, themes: [0, 1, 2] },
};
const OFF = { ok: true, skin_contract: { schema_version: 2, enabled: false, reason: "no_writer_capability" } };

// A minimal manifest in the published shape.
const MANIFEST = {
  schema_version: 2,
  build: 918,
  species: {
    Trex: {
      patterns: [
        {
          index: 0,
          themes: [
            {
              index: 0,
              supported_slots: [
                { slot: "body", swatches: [[1, 0, 0], [0.5, 0.5, 0.5]] },
                { slot: "teeth", swatches: [[255, 255, 255], [0, 128, 64]] },
                { slot: "not_a_slot", swatches: [] },
              ],
            },
            { index: 5, supported_slots: [{ slot: "body", swatches: [] }] }, // outside the capability
          ],
        },
        { index: 2, themes: [{ index: 1, supported_slots: V2_SLOTS.map((s) => ({ slot: s, swatches: [] })) }] },
        { index: 2, themes: [] },      // duplicate index — first entry wins
        { index: -1, themes: [] },     // negative — ignored
        { index: 1.5, themes: [] },    // non-integer — ignored
        { index: 3, themes: [] },      // real pattern with zero themes
      ],
    },
    Dilo: { patterns: [] },            // species with zero patterns
  },
};

describe("skinContractV2 — slot contract", () => {
  test("ten slots, canonical order, v1 seven first", () => {
    expect(V2_SLOTS).toEqual(["body", "markings", "flank", "underbelly", "detail1", "eyes", "male_display", "teeth", "mouth", "claws"]);
    expect(V1_SLOTS).toHaveLength(7);
    expect(V2_NEW_SLOTS).toEqual(["teeth", "mouth", "claws"]);
    expect(V2_VARIATIONS).toEqual([2, 8, 16]);
    expect(themeLabel(2)).toBe("Tema 2");
  });
});

describe("readContractState — anything that is not a live v2 contract is OFF", () => {
  test("enabled contract normalizes", () => {
    const v = readContractState(ON);
    expect(v.enabled).toBe(true);
    expect(v.build).toBe("918");
    expect(v.slots).toEqual(V2_SLOTS);
    expect(v.themes).toEqual([0, 1, 2]);
  });

  test("disabled contract keeps the server's named reason", () => {
    const v = readContractState(OFF);
    expect(v.enabled).toBe(false);
    expect(v.reason).toBe("no_writer_capability");
  });

  test("every malformed answer is OFF, never a throw", () => {
    [null, undefined, "", 0, "nope", {}, { ok: true }, { skin_contract: "x" }, { skin_contract: null }]
      .forEach((b) => expect(readContractState(b).enabled).toBe(false));
    // a future schema we cannot read is OFF, not a guess
    expect(readContractState({ skin_contract: { schema_version: 3, enabled: true, slots: V2_SLOTS, themes: [0] } }).enabled).toBe(false);
    // enabled but nothing to offer renders nothing -> OFF
    expect(readContractState({ skin_contract: { schema_version: 2, enabled: true, slots: [], themes: [0] } }).reason).toBe("empty_capability");
    expect(readContractState({ skin_contract: { schema_version: 2, enabled: true, slots: V2_SLOTS, themes: [] } }).reason).toBe("empty_capability");
    // truthy-but-not-true never opens the gate
    expect(readContractState({ skin_contract: { schema_version: 2, enabled: 1, slots: V2_SLOTS, themes: [0] } }).enabled).toBe(false);
  });

  test("unknown slot names and junk theme indices are dropped", () => {
    const v = readContractState({ skin_contract: { schema_version: 2, enabled: true, build: 7, slots: ["claws", "body", "wings"], themes: [2, 2, -1, "1", null, 0] } });
    expect(v.slots).toEqual(["body", "claws"]); // canonical order, "wings" gone
    expect(v.themes).toEqual([0, 2]);
    expect(v.build).toBe("7");
  });

  test("normalizeIndexList", () => {
    expect(normalizeIndexList([3, 1, 1, -2, 2.5, "0", null])).toEqual([1, 3]);
    expect(normalizeIndexList("nope")).toEqual([]);
  });
});

describe("manifest readers", () => {
  test("species lookup is case-insensitive and never throws", () => {
    expect(speciesEntry(MANIFEST, "trex")).toBeTruthy();
    expect(speciesEntry(MANIFEST, "TREX")).toBeTruthy();
    expect(speciesEntry(MANIFEST, "ghost")).toBeNull();
    expect(speciesEntry(null, "trex")).toBeNull();
    expect(speciesEntry({}, "")).toBeNull();
  });

  test("patterns: duplicates, negatives and non-integers ignored", () => {
    expect(listPatterns(MANIFEST, "Trex")).toEqual([0, 2, 3]);
    expect(listPatterns(MANIFEST, "Dilo")).toEqual([]);   // zero patterns
    expect(listPatterns(MANIFEST, "ghost")).toEqual([]);
    expect(listPatterns(null, "Trex")).toEqual([]);
  });

  test("themes: capability AND the pattern must both allow it", () => {
    expect(listThemes(MANIFEST, "Trex", 0, [0, 1, 2])).toEqual([0]);   // theme 5 is outside the capability
    expect(listThemes(MANIFEST, "Trex", 0, [5])).toEqual([5]);         // capability widened -> now offerable
    expect(listThemes(MANIFEST, "Trex", 3, [0, 1, 2])).toEqual([]);    // pattern with zero themes
    expect(listThemes(MANIFEST, "Trex", 99, [0, 1, 2])).toEqual([]);
    expect(listThemes(MANIFEST, "Trex", 0, [])).toEqual([]);
  });

  test("supported slots: fewer than ten is normal, order is canonical", () => {
    expect(listSupportedSlots(MANIFEST, "Trex", 0, 0, V2_SLOTS)).toEqual(["body", "teeth"]);
    expect(listSupportedSlots(MANIFEST, "Trex", 2, 1, V2_SLOTS)).toEqual(V2_SLOTS);
    // the capability narrows it further
    expect(listSupportedSlots(MANIFEST, "Trex", 2, 1, ["claws", "body"])).toEqual(["body", "claws"]);
    expect(listSupportedSlots(MANIFEST, "Trex", 0, 9, V2_SLOTS)).toEqual([]);
    expect(listSupportedSlots(null, "Trex", 0, 0, V2_SLOTS)).toEqual([]);
  });

  test("swatches: 0-1 and 0-255 triples both land on the right hex", () => {
    expect(listSwatches(MANIFEST, "Trex", 0, 0, "body")).toEqual(["#ff0000", "#808080"]);
    expect(listSwatches(MANIFEST, "Trex", 0, 0, "teeth")).toEqual(["#ffffff", "#008040"]);
    expect(listSwatches(MANIFEST, "Trex", 0, 0, "claws")).toEqual([]);
    expect(listSwatches(MANIFEST, "Trex", 0, 0, "body", 1)).toEqual(["#ff0000"]);
    expect(listSwatches(null, "Trex", 0, 0, "body")).toEqual([]);
  });
});

describe("apply-v2 payload", () => {
  test("hex -> the SAME 0-1 sRGB numbers /api/apply already gets", () => {
    expect(srgb01FromHex("#ff8000")).toEqual({ r: 1, g: 128 / 255, b: 0 });
    expect(srgb01FromHex("bad")).toEqual({ r: 1, g: 1, b: 1 });
    expect(srgb01FromHex(null)).toEqual({ r: 1, g: 1, b: 1 });
  });

  test("pickVariation snaps to a real engine key", () => {
    expect(pickVariation(8)).toBe(8);
    expect(pickVariation("16")).toBe(16);
    expect(pickVariation(3)).toBe(2);
    expect(pickVariation(undefined)).toBe(2);
  });

  test("all ten slots, alpha EXACTLY 1", () => {
    const body = buildApplyV2Body({
      pattern: 2, variation: 16, theme: 1,
      hexColors: { body: "#000000", teeth: "#ffffff" },
    });
    expect(body.contract_version).toBe(2);
    expect(body.pattern).toBe(2);
    expect(body.variation).toBe(16);
    expect(body.theme).toBe(1);
    V2_SLOTS.forEach((s) => {
      expect(body[s]).toBeDefined();
      expect(body[s].a).toBe(1);
    });
    expect(body.body).toEqual({ r: 0, g: 0, b: 0, a: 1 });
    // a slot the caller had no colour for still ships (white), never missing
    expect(body.claws).toEqual({ r: 1, g: 1, b: 1, a: 1 });
    expect(Object.keys(body)).toHaveLength(4 + V2_SLOTS.length);
  });

  test("junk indices fall back instead of poisoning the payload", () => {
    const body = buildApplyV2Body({ pattern: -3, variation: 99, theme: "1", hexColors: {} });
    expect(body.pattern).toBe(0);
    expect(body.theme).toBe(0);
    expect(body.variation).toBe(2);
  });
});

describe("serverRefusalMessage", () => {
  test("named reasons come back in Spanish", () => {
    expect(serverRefusalMessage({ reason: "over_budget" })).toBe("Espera un momento — demasiadas aplicaciones seguidas.");
    expect(serverRefusalMessage({ error: "no_writer_capability" })).toBe("El servidor de juego aún no acepta skins v2.");
    expect(serverRefusalMessage({ detail: { reason: "not_in_game" } })).toBe("Despliega un dino primero — se aplica a tu Dino en Vivo.");
  });

  test("an unmapped reason is shown verbatim, never swallowed", () => {
    expect(serverRefusalMessage({ reason: "algo_raro" })).toBe("algo_raro");
    expect(serverRefusalMessage({ detail: "Texto del servidor" })).toBe("Texto del servidor");
  });

  test("nothing to show returns empty, never throws", () => {
    expect(serverRefusalMessage(null)).toBe("");
    expect(serverRefusalMessage({})).toBe("");
    expect(serverRefusalMessage({ reason: "   " })).toBe("");
    expect(serverRefusalMessage("plain")).toBe("");
  });
});
