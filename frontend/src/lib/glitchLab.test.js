/**
 * Glitch Lab pure helpers (2026-08-23). LIN2 exact codes must round-trip
 * float-for-float (that is the entire fix for "copying someone else's skin
 * doesn't actually apply"), grant keys must never ride a code, and the
 * validation mirror must agree with backend skin_exact at the glitch-grant
 * level (channel sentinel legal, pattern -8 refused, |v| <= 1e12).
 */
import {
  GLITCH_SLOTS, GLITCH_FAMILIES, validateGlitchRaw, emptyGlitchFields,
  rawToFields, fieldsToRaw, encodeGlitchCode, decodeGlitchCode,
  rawNeedsGlitchLab, randomGlitchSlot, randomGlitchFields,
  GLITCH_CODE_PREFIX,
} from "./glitchLab";

// The owner's REAL worn payload family (2026-08-20 capture): sentinel-band
// channels, plain slots mixed in, variation 8, pattern 2.
const WORN = {
  pattern: 2, variation: 8.0,
  body: [-795233.5625, -7952343.5, -7952343.5, -794.234375],
  markings: [-7952343.5, -795233.5625, -7951.497559, -795145.9375],
  flank: [0.172337, 0.154838, 0.146566, 1.0],
  underbelly: [-795233.375, -79523440.0, -7952343.0, -794.234375],
  detail1: [-999999.0, -999999.0, -999999.0, -999667.0],
  eyes: [0.999205, 0.539818, 0.539818, 1.0],
  male_display: [0.682085, 0.020759, 0.020759, 1.0],
};
const INGAMUT = {
  pattern: 1, variation: 0.004,
  body: [0.1, 0.2, 0.3, 1.0], markings: [0.4, 0.5, 0.6, 1.0],
  flank: [0.7, 0.8, 0.9, 1.0], underbelly: [0.15, 0.25, 0.35, 0.5],
  detail1: [0.45, 0.55, 0.65, 1.0], eyes: [0.75, 0.85, 0.95, 1.0],
  male_display: [0.05, 0.95, 0.55, 1.0],
};

describe("validateGlitchRaw (mirror of backend glitch-grant level)", () => {
  test("sentinel-band payload is LEGAL here", () => {
    expect(validateGlitchRaw(WORN)).toEqual({ ok: true, reason: "" });
  });
  test("pattern -8 refused always (restart sentinel)", () => {
    expect(validateGlitchRaw({ ...WORN, pattern: -8 })).toEqual({ ok: false, reason: "poison_pattern" });
  });
  test("windows and shapes refuse with the field named", () => {
    expect(validateGlitchRaw({ ...WORN, pattern: 1.5 }).reason).toBe("pattern");
    expect(validateGlitchRaw({ ...WORN, pattern: 64 }).reason).toBe("pattern_range");
    expect(validateGlitchRaw({ ...WORN, variation: NaN }).reason).toBe("variation");
    expect(validateGlitchRaw({ ...WORN, variation: 2e12 }).reason).toBe("variation");
    expect(validateGlitchRaw({ ...WORN, body: [2e12, 0, 0, 1] }).reason).toBe("slot_body");
    expect(validateGlitchRaw({ ...WORN, body: [Infinity, 0, 0, 1] }).reason).toBe("slot_body");
    expect(validateGlitchRaw({ ...WORN, eyes: [1, 2, 3] }).reason).toBe("slot_eyes");
    expect(validateGlitchRaw({ ...WORN, flank: undefined }).reason).toBe("slot_flank");
    expect(validateGlitchRaw(null).reason).toBe("shape");
    expect(validateGlitchRaw([1]).reason).toBe("shape");
  });
  test("exactly 1e12 passes, just over refuses (boundary)", () => {
    expect(validateGlitchRaw({ ...WORN, body: [1e12, 0, 0, 1] }).ok).toBe(true);
    expect(validateGlitchRaw({ ...WORN, body: [1.0000001e12, 0, 0, 1] }).ok).toBe(false);
  });
});

describe("LIN2 exact codes", () => {
  test("round-trips FLOAT-FOR-FLOAT (the copy-someone's-skin fix)", () => {
    const code = encodeGlitchCode("Tyrannosaurus", WORN);
    expect(code.startsWith(GLITCH_CODE_PREFIX)).toBe(true);
    const back = decodeGlitchCode(code);
    expect(back).not.toBeNull();
    expect(back.dinoClass).toBe("Tyrannosaurus");
    GLITCH_SLOTS.forEach((k) => expect(back.raw[k]).toEqual(WORN[k]));
    expect(back.raw.pattern).toBe(2);
    expect(back.raw.variation).toBe(8.0);
  });
  test("in-gamut payloads code too (normal skins share exactly, no 8-bit loss)", () => {
    const back = decodeGlitchCode(encodeGlitchCode("Cerato", INGAMUT));
    expect(back.raw.body).toEqual([0.1, 0.2, 0.3, 1.0]);
    expect(back.raw.variation).toBe(0.004);
  });
  test("grant keys are STRIPPED at encode — codes never carry entitlement", () => {
    const code = encodeGlitchCode("Rex", { ...WORN, owner_grant: true, glitch_grant: true });
    const json = JSON.parse(Buffer.from(
      code.slice(GLITCH_CODE_PREFIX.length).replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("binary"));
    expect(JSON.stringify(json)).not.toContain("grant");
    expect(decodeGlitchCode(code).raw.owner_grant).toBeUndefined();
  });
  test("malformed input returns null, never throws", () => {
    expect(decodeGlitchCode("")).toBeNull();
    expect(decodeGlitchCode(null)).toBeNull();
    expect(decodeGlitchCode("LIN1-abc")).toBeNull();
    expect(decodeGlitchCode("LIN2-")).toBeNull();
    expect(decodeGlitchCode("LIN2-!!!!")).toBeNull();
    expect(decodeGlitchCode("LIN2-eyJ2IjoyfQ")).toBeNull();          // {v:2} missing slots
    const good = encodeGlitchCode("Rex", WORN);
    expect(decodeGlitchCode(good.slice(0, good.length - 10))).toBeNull(); // truncated
  });
  test("out-of-window payloads refuse to encode AND to decode", () => {
    expect(encodeGlitchCode("Rex", { ...WORN, pattern: -8 })).toBeNull();
    // hand-build a code carrying 2e12 — decode must refuse it
    const body = { v: 2, d: "Rex", p: 2, vr: 8, s: {} };
    GLITCH_SLOTS.forEach((k) => { body.s[k] = [0, 0, 0, 1]; });
    body.s.body = [2e12, 0, 0, 1];
    const b64 = Buffer.from(JSON.stringify(body), "binary").toString("base64")
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    expect(decodeGlitchCode(GLITCH_CODE_PREFIX + b64)).toBeNull();
  });
});

describe("fields <-> raw", () => {
  test("scientific notation strings parse", () => {
    const f = rawToFields(WORN);
    f.slots.body[0] = "-1e11";
    const out = fieldsToRaw(f);
    expect(out.ok).toBe(true);
    expect(out.raw.body[0]).toBe(-1e11);
  });
  test("garbage names the field", () => {
    const f = rawToFields(WORN);
    f.slots.eyes[2] = "abc";
    expect(fieldsToRaw(f)).toEqual({ ok: false, reason: "slot_eyes" });
    const g = rawToFields(WORN);
    g.pattern = "x";
    expect(fieldsToRaw(g).reason).toBe("pattern");
  });
  test("empty lab state is valid (all zero, alpha 1) and round-trips", () => {
    const out = fieldsToRaw(emptyGlitchFields());
    expect(out.ok).toBe(true);
    expect(out.raw.body).toEqual([0, 0, 0, 1]);
  });
});

describe("rawNeedsGlitchLab", () => {
  test("sentinel band -> true, everything else -> false", () => {
    expect(rawNeedsGlitchLab(WORN)).toBe(true);
    expect(rawNeedsGlitchLab(INGAMUT)).toBe(false);
    expect(rawNeedsGlitchLab({ ...INGAMUT, body: [5.0, 0, 0, 1] })).toBe(false);  // mild out-of-gamut
    expect(rawNeedsGlitchLab(null)).toBe(false);
  });
});

describe("randomizer (era-proven bands, deterministic rng)", () => {
  const seq = (vals) => { let i = 0; return () => vals[(i++) % vals.length]; };
  test("every family produces values inside its own band (or plain 0..1)", () => {
    GLITCH_FAMILIES.filter((f) => f.lo !== null).forEach((f) => {
      const slot = randomGlitchSlot(f.id, seq([0.5, 0.9, 0.3, 0.7, 0.4, 0.6, 0.8, 0.2]));
      slot.slice(0, 3).forEach((v) => {
        const m = Math.abs(v);
        expect(Number.isFinite(v)).toBe(true);
        expect(m <= 1 || (m >= f.lo * 0.999 && m <= f.hi * 1.001)).toBe(true);
      });
    });
  });
  test("a full random field set validates and is glitch-space", () => {
    const fields = randomGlitchFields("mixto", seq([0.42, 0.87, 0.13, 0.66, 0.29, 0.74, 0.51, 0.98, 0.05, 0.33]));
    const out = fieldsToRaw(fields);
    expect(out.ok).toBe(true);
  });
});
