/**
 * The species-default SEED colour space.
 *
 * ★2026-08-11 LINEAR RESTORE — this pin MOVED WITH the contract, it was not
 * deleted. Its previous form (2026-08-10) pinned the seed RAW, on the premise
 * that CustomizerData holds the picker's own n/255 fractions. The measured half
 * of that premise still stands and is not in dispute: LIN's own birth captures
 * match the palette table's floats 23 times and a transformed copy 0 times
 * (identical 23/0 against the pre-08-09 control, +5/0 from skin_snapshots.json;
 * 3,405/0 fleet-wide). What was wrong was the SECOND step — reading "the table
 * is CustomizerData" as "the table is the picker's space". CustomizerData's
 * colour slots are `FLinearColor`, which UE consumes LINEAR, so the table is
 * LINEAR and a colour picker (which speaks sRGB bytes) must display it through
 * lin2srgb. The backend wire moved back to one srgb->linear encode in the same
 * ship; the seed and the emitter now describe the same colour.
 *
 * The pin is still written BY BEHAVIOUR, not by source text: the hex the studio
 * seeds must equal lin2srgb(table). Every check below is written so that
 * dropping the encode DARKENS it — see "the mutation guard" at the bottom,
 * which refuses to pass vacuously.
 *
 * Expected values are recomputed here from the JSON with inline arithmetic
 * instead of by calling the module's own converter, so a mutated converter
 * cannot mark its own homework.
 */
import PALETTES from "@/data/skin_default_palettes.json";
import {
  FLEET_SLOTS,
  DEFAULT_FLEET_COLORS,
  getSpeciesDefaultColors,
  rawToHex,
  linearToHex,
} from "@/components/skin3d/tintMaterial";

const fs = require("fs");
const path = require("path");
const SRC = fs.readFileSync(path.join(__dirname, "tintMaterial.js"), "utf8");

const ALL_SLOTS = [...FLEET_SLOTS, "eyes"];
const SPECIES = Object.keys(PALETTES).filter((k) => k !== "_schema");

// ── independent reference arithmetic (NOT the module's) ──────────────────────
const clamp01 = (c) => Math.max(0, Math.min(1, c));
const hex2 = (n) => n.toString(16).padStart(2, "0");
/** the RETIRED (gamma-free) seed — kept as the foil, and still the contract of
 *  `rawToHex` itself, which stays exported for any lane genuinely holding
 *  picker-space floats */
const rawByte = (c) => Math.round(clamp01(c) * 255);
const rawHexOf = (t) => `#${hex2(rawByte(t[0]))}${hex2(rawByte(t[1]))}${hex2(rawByte(t[2]))}`;
/** what the CORRECT (lin2srgb) seed must produce */
const linByte = (c) => {
  const v = clamp01(c);
  return Math.round((v <= 0.0031308 ? v * 12.92 : 1.055 * Math.pow(v, 1 / 2.4) - 0.055) * 255);
};
const linHexOf = (t) => `#${hex2(linByte(t[0]))}${hex2(linByte(t[1]))}${hex2(linByte(t[2]))}`;

/**
 * ★The degenerate filter the fleet law requires: lin2srgb FIXES 0.0 and 1.0, so a
 * black or white channel matches its own raw form and would let an un-encoded
 * seed pass. A channel only DISTINGUISHES the two spaces when the two bytes differ.
 */
const isDecisive = (c) => rawByte(c) !== linByte(c);

describe("the species-default seed is lin2srgb(table) — the table is CustomizerData's LINEAR space", () => {
  test("Tyrannosaurus.body seeds the displayable colour, not the linear float's raw byte", () => {
    const t = PALETTES.Tyrannosaurus.body; // [0.25, 0.17751, 0.1, 1]
    const got = getSpeciesDefaultColors("Tyrannosaurus").body.c;

    expect(got).toBe(linHexOf(t)); // #897559
    expect(got).toBe("#897559");

    // the foil, named out loud so a future reader sees the two candidates
    expect(rawHexOf(t)).toBe("#402d1a");
    expect(got).not.toBe(rawHexOf(t));

    // ★non-vacuous: the two candidates are 73 8-bit levels apart on the red channel,
    // so this assertion cannot be satisfied by both spaces at once.
    expect(Math.abs(rawByte(t[0]) - linByte(t[0]))).toBeGreaterThanOrEqual(40);
  });

  test("every species, every slot: the seeded hex equals lin2srgb(table value)", () => {
    let decisiveChannels = 0;
    expect(SPECIES.length).toBe(23);

    SPECIES.forEach((sp) => {
      const seeded = getSpeciesDefaultColors(sp);
      ALL_SLOTS.forEach((slot) => {
        const t = PALETTES[sp][slot];
        if (!t) return;
        expect(seeded[slot].c).toBe(linHexOf(t));
        [0, 1, 2].forEach((i) => { if (isDecisive(t[i])) decisiveChannels += 1; });
      });
    });

    // ★non-vacuous: the sweep only means something if the table actually contains
    // channels where raw and encoded disagree. If a future table were all 0/1 this
    // number collapses and the test says so instead of passing silently.
    expect(decisiveChannels).toBeGreaterThanOrEqual(100);
  });

  test("alpha rides through the seed untouched, never through the transfer function", () => {
    expect(getSpeciesDefaultColors("Tyrannosaurus").body.a).toBe(1);
    expect(linearToHex([0, 0, 0, 0.25]).a).toBe(0.25);
    expect(linearToHex([0, 0, 0]).a).toBe(1); // no alpha in the tuple -> opaque
    expect(rawToHex([0, 0, 0, 0.25]).a).toBe(0.25);
    expect(rawToHex([0, 0, 0]).a).toBe(1);
  });
});

describe("★SPLIT CONVERTER — two converters, and they must stay two", () => {
  test("linearToHex encodes and rawToHex is still gamma-free", () => {
    // The canonical fleet probe: a 0.5 stored float / a 0.5 picker fraction.
    expect(linearToHex([0.5, 0.5, 0.5, 1]).c).toBe("#bcbcbc");
    expect(rawToHex([0.5, 0.5, 0.5, 1]).c).toBe("#808080");
    // ★If someone "tidies up" by flipping the shared helper instead of pointing its
    // caller at the other one, THIS reddens — that is the point of keeping both pins.
    expect(rawToHex([0.5, 0.5, 0.5, 1]).c).not.toBe(linearToHex([0.5, 0.5, 0.5, 1]).c);
  });

  test("both converters clamp out-of-band channels instead of overflowing the byte", () => {
    expect(rawToHex([-5, 0.5, 9.9, 1]).c).toBe("#0080ff");
    expect(rawToHex([0, 0, 0, 1]).c).toBe("#000000");
    expect(rawToHex([1, 1, 1, 1]).c).toBe("#ffffff");
    expect(linearToHex([-5, 0.5, 9.9, 1]).c).toBe("#00bcff");
    expect(linearToHex([0, 0, 0, 1]).c).toBe("#000000");
    expect(linearToHex([1, 1, 1, 1]).c).toBe("#ffffff");
  });

  test("the seed call site goes through the DISPLAY converter, and only that one", () => {
    expect(SRC).toContain("linearToHex(entry[k])");
    expect(SRC).not.toContain("rawToHex(entry[k])");
    // ★rawToHex is NOT deleted: it stays defined and exported so that a lane which
    // genuinely holds picker-space floats can be POINTED at it, instead of someone
    // editing linearToHex's body and repainting every display lane at once.
    expect(SRC).toContain("export function rawToHex");
    expect(typeof rawToHex).toBe("function");
  });
});

describe("seed edge cases — a studio that opens is worth more than a studio that is right and blank", () => {
  test("an unknown species falls back to the fleet defaults, never black or undefined", () => {
    expect(getSpeciesDefaultColors("Nothingsaurus")).toEqual(DEFAULT_FLEET_COLORS);
    expect(getSpeciesDefaultColors("")).toEqual(DEFAULT_FLEET_COLORS);
    expect(getSpeciesDefaultColors(null)).toEqual(DEFAULT_FLEET_COLORS);
    expect(getSpeciesDefaultColors(undefined)).toEqual(DEFAULT_FLEET_COLORS);
    expect(getSpeciesDefaultColors({})).toEqual(DEFAULT_FLEET_COLORS);
  });

  test("species objects resolve by slug, name or id, case-insensitively", () => {
    const want = getSpeciesDefaultColors("Tyrannosaurus");
    expect(getSpeciesDefaultColors("tyrannosaurus")).toEqual(want);
    expect(getSpeciesDefaultColors("TYRANNOSAURUS")).toEqual(want);
    expect(getSpeciesDefaultColors({ slug: "Tyrannosaurus" })).toEqual(want);
    expect(getSpeciesDefaultColors({ name: "Tyrannosaurus" })).toEqual(want);
    expect(getSpeciesDefaultColors({ id: "Tyrannosaurus" })).toEqual(want);
  });

  test("every seeded slot is a well-formed hex for every species", () => {
    SPECIES.forEach((sp) => {
      const seeded = getSpeciesDefaultColors(sp);
      ALL_SLOTS.forEach((slot) => {
        expect(seeded[slot].c).toMatch(/^#[0-9a-f]{6}$/);
        expect(typeof seeded[slot].a).toBe("number");
      });
    });
  });
});

/**
 * ★THE PALETTE-SHAPE GUARD (Isle build 24664709).
 *
 * That build added 48 skin palette gradient textures across 9 species and removed
 * none. Three change the SHAPE of a palette rather than adding a whole new one:
 * Tyrannosaurus gains a 6th `YellowLayer`, Dryosaurus and Hypsilophodon gain a
 * `ClawColor`, and — the dangerous one — Omniraptor's ALREADY-EXISTING `Palette2`
 * gained a `MouthColor`. An existing palette changing shape is the case that breaks a
 * skin creator, because a creator built against the old shape either drops a layer or
 * maps the new one into the wrong picker.
 *
 * This studio is structurally immune: `getSpeciesDefaultColors` walks a FIXED slot
 * list (`[...FLEET_SLOTS, "eyes"]`) and never the row's own keys, so an unknown layer
 * is unreachable rather than merely unused. These tests pin that immunity, so a future
 * "tidy-up" to `Object.keys(entry)` reddens HERE instead of shipping a mis-mapped
 * picker to players.
 *
 * ★They run the REAL module against an INJECTED palette file (jest.isolateModules +
 * doMock), because the shipped JSON does not contain the new layers — asserting
 * against it would prove only that absent keys are absent.
 */
describe("★the palette-shape guard — a species row that GAINS layers must not move the studio", () => {
  /** Load a pristine copy of the module with a substituted palette file. */
  const seedWithPalette = (paletteFile) => {
    let mod;
    jest.isolateModules(() => {
      jest.doMock("@/data/skin_default_palettes.json", () => paletteFile);
      mod = require("@/components/skin3d/tintMaterial");
    });
    return mod;
  };

  // The three 24664709 shape changes, applied at once to ONE existing row. Values are
  // deliberately vivid and mutually distinct so a leak into any picker is unmistakable.
  const NEW_LAYERS = {
    MouthColor: [0.94, 0.06, 0.06, 1], // Omniraptor Palette2's new layer
    ClawColor: [0.06, 0.94, 0.06, 1], // Dryosaurus / Hypsilophodon's new layer
    Color6_YellowLayer: [0.06, 0.06, 0.94, 1], // a RAW engine layer name, never an IPC key
  };
  const MUTATED = {
    _schema: PALETTES._schema,
    Omniraptor: { ...PALETTES.Omniraptor, ...NEW_LAYERS },
  };

  test("the injected row really does carry the new layers (the guard is armed)", () => {
    // ★Without this the whole block could pass by injecting nothing.
    expect(Object.keys(MUTATED.Omniraptor)).toEqual(
      expect.arrayContaining(["MouthColor", "ClawColor", "Color6_YellowLayer"])
    );
    expect(Object.keys(MUTATED.Omniraptor).length).toBe(ALL_SLOTS.length + 3);
    // and the shipped file does NOT — so the injection is what is being measured
    expect(Object.keys(PALETTES.Omniraptor)).not.toContain("MouthColor");
  });

  test("a row that gained three layers seeds byte-for-byte what it seeded before", () => {
    const before = getSpeciesDefaultColors("Omniraptor");
    const after = seedWithPalette(MUTATED).getSpeciesDefaultColors("Omniraptor");
    expect(after).toEqual(before);
  });

  test("the seeded slot set stays exactly seven — no layer is added, none displaced", () => {
    const after = seedWithPalette(MUTATED).getSpeciesDefaultColors("Omniraptor");
    expect(Object.keys(after).sort()).toEqual([...ALL_SLOTS].sort());
    expect(after.MouthColor).toBeUndefined();
    expect(after.ClawColor).toBeUndefined();
  });

  test("no new layer's colour reaches ANY picker (the mis-map case)", () => {
    const after = seedWithPalette(MUTATED).getSpeciesDefaultColors("Omniraptor");
    // ★checked in the SEED's own space (lin2srgb), which is what a leak would
    // actually look like on screen — #f74848 / #48f748 / #4848f7. The raw forms are
    // listed too so the guard cannot be dodged by a seed that skipped the encode.
    const leaked = [
      ...Object.values(NEW_LAYERS).map(linHexOf),
      ...Object.values(NEW_LAYERS).map(rawHexOf),
    ];
    ALL_SLOTS.forEach((slot) => expect(leaked).not.toContain(after[slot].c));
    // ★non-vacuous: those are real, distinct hexes and would be visible if leaked
    expect(new Set(leaked).size).toBe(6);
  });

  test("the seed walks the fixed slot list, never the row's own keys", () => {
    // The structural reason the four tests above hold. A refactor to dynamic key
    // iteration flips this pin before it can flip the behaviour ones.
    expect(SRC).toContain('[...FLEET_SLOTS, "eyes"].forEach');
    expect(SRC).not.toContain("Object.keys(entry)");
    expect(SRC).not.toContain("Object.entries(entry)");
  });
});

/**
 * ★THE PARTIAL-ROW GUARD. Austroraptor ships SIX slots, not seven — it has no `eyes`
 * default (the donor extraction never carried one, and the fleet rule is that a number
 * shown to players is measured or absent, never guessed; cf. seed_data.py's growth
 * table, which leaves Austroraptor out for the same reason). The seed must therefore
 * fall back for that ONE slot and keep the species' own five... six real ones.
 */
describe("★the partial-row guard — a species missing a slot still opens on its own colours", () => {
  const PARTIAL = SPECIES.filter((sp) => ALL_SLOTS.some((s) => !PALETTES[sp][s]));

  test("Austroraptor is the only partial row, and it is missing exactly eyes", () => {
    expect(PARTIAL).toEqual(["Austroraptor"]);
    expect(ALL_SLOTS.filter((s) => !PALETTES.Austroraptor[s])).toEqual(["eyes"]);
  });

  test("the missing slot falls back to the fleet default, and ONLY that slot does", () => {
    const seeded = getSpeciesDefaultColors("Austroraptor");
    expect(seeded.eyes).toEqual(DEFAULT_FLEET_COLORS.eyes);
    // every other slot still comes from Austroraptor's own table, not the fallback
    FLEET_SLOTS.forEach((slot) => {
      expect(seeded[slot].c).toBe(linHexOf(PALETTES.Austroraptor[slot]));
    });
    // ★non-vacuous: the fallback and the real body colour are genuinely different, so
    // a seed that quietly returned DEFAULT_FLEET_COLORS wholesale would redden here.
    expect(seeded.body.c).not.toBe(DEFAULT_FLEET_COLORS.body.c);
  });
});

describe("★the mutation guard — a raw (un-encoded) seed must redden this file", () => {
  test("no species default is seeded at its un-encoded value", () => {
    // Runs the REAL seed over the REAL table and asserts, per decisive channel,
    // that what came out is the lin2srgb byte and NOT the raw one. Pointing
    // getSpeciesDefaultColors back at rawToHex flips every one of these.
    const offenders = [];
    let checked = 0;
    SPECIES.forEach((sp) => {
      const seeded = getSpeciesDefaultColors(sp);
      ALL_SLOTS.forEach((slot) => {
        const t = PALETTES[sp][slot];
        if (!t) return;
        if (![0, 1, 2].some((i) => isDecisive(t[i]))) return; // degenerate slot, proves nothing
        checked += 1;
        if (seeded[slot].c === rawHexOf(t)) offenders.push(`${sp}.${slot} = ${seeded[slot].c}`);
      });
    });
    expect(checked).toBeGreaterThanOrEqual(100); // the guard has real subjects
    expect(offenders).toEqual([]);
  });

  test("the guard is armed: it can tell the two spaces apart on real data", () => {
    // A self-check on the guard itself — if raw and encoded ever agreed on the
    // probe, the test above would be decorative. They differ by 73 levels.
    const t = PALETTES.Tyrannosaurus.body;
    expect(rawHexOf(t)).not.toBe(linHexOf(t));
    expect(rawByte(t[0])).toBe(0x40);
    expect(linByte(t[0])).toBe(0x89);
  });

  test("the seed and the live-preview lane agree — one app, one colour space", () => {
    // SpeciesViewer3D renders GET /api/snapshot's stored floats through linearToHex.
    // The seed now uses the same converter, so a table value and a stored value that
    // happen to be equal MUST show the same hex. This is the pin that would have
    // caught the 2026-08-09..08-11 split, where one file displayed lin2srgb and the
    // other displayed raw off the same wire.
    const t = PALETTES.Tyrannosaurus.body;
    expect(getSpeciesDefaultColors("Tyrannosaurus").body.c).toBe(linearToHex(t).c);
  });
});
