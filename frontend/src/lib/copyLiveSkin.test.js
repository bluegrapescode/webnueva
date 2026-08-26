/**
 * Copy-current-skin conversion. Invariants: never throws on any wire shape;
 * poisoned restart sentinels are refused, never rendered as colours.
 *
 * ★2026-08-11 LINEAR RESTORE — this pin MOVED WITH the contract. It used to
 * assert the conversion was gamma-FREE, on the retired premise that a snapshot
 * float is the picker's own n/255 fraction. CustomizerData's colour slots are
 * `FLinearColor`, so /api/apply emits ONE srgb->linear encode and the floats
 * read back here are LINEAR; the display conversion is lin2srgb.
 *
 * The decisive check is the PARITY one at the bottom: this module and
 * SpeciesViewer3D read the SAME payload (GET /api/snapshot -> data.skin) and
 * must therefore produce the SAME hex. That is the pin that would have caught
 * the 2026-08-09..08-11 split, when one file displayed lin2srgb and the other
 * displayed raw off one wire.
 */
import { snapshotToEditorSkin, bareClass, SKIN_SLOTS, SKIN_POISON_THRESHOLD } from "./copyLiveSkin";
import { linearToHex } from "@/components/skin3d/tintMaterial";

const fs = require("fs");
const path = require("path");
const readSrc = (...parts) => fs.readFileSync(path.join(__dirname, "..", ...parts), "utf8");

const DEFAULTS = Object.fromEntries(SKIN_SLOTS.map((k) => [k, { c: "#8a6b45", a: 1 }]));

describe("bareClass", () => {
  test("engine class names strip to the species key", () => {
    expect(bareClass("BP_Tyrannosaurus_C")).toBe("Tyrannosaurus");
    expect(bareClass("BP_Deinosuchus_C")).toBe("Deinosuchus");
  });
  test("already-bare and junk shapes pass through unharmed", () => {
    expect(bareClass("Tyrannosaurus")).toBe("Tyrannosaurus");
    expect(bareClass("")).toBe("");
    expect(bareClass(null)).toBe("");
    expect(bareClass("BP_")).toBe("BP_");
  });
});

describe("snapshotToEditorSkin", () => {
  test("a live snapshot copies every slot linear->hex and keeps alpha", () => {
    const snap = { pattern: 1, body: [1, 0, 0, 0.5], eyes: [0, 0, 0, 1] };
    const r = snapshotToEditorSkin(snap, DEFAULTS);
    expect(r.ok).toBe(true);
    expect(r.pattern).toBe(1);
    expect(r.colors.body).toEqual({ c: "#ff0000", a: 0.5 });
    expect(r.colors.eyes).toEqual({ c: "#000000", a: 1 });
    expect(r.copiedSlots.sort()).toEqual(["body", "eyes"]);
  });
  test("a stored mid-grey is DECODED for display (linear 0.5 -> #bcbcbc)", () => {
    // The stored float is linear, so the byte a picker must show is
    // lin2srgb(0.5)*255 = 0xbc. The retired direct value*255 emitted #808080 and
    // showed every copied skin DARKER than the dino actually is.
    const r = snapshotToEditorSkin({ body: [0.5, 0.5, 0.5, 1] }, DEFAULTS);
    expect(r.colors.body.c).toBe("#bcbcbc");
    // the foil, named out loud so a future reader sees the two candidates
    expect(r.colors.body.c).not.toBe("#808080");
  });
  test("the seeded wire triple this backend emits copies back to the pick", () => {
    // server.py::to_command turns picks 0.0 / 0.5 / 1.0 into these stored floats
    // (tests_local/test_skin_emission_float_band.py block A). Copying them back
    // must land on the player's own pick, +/- the eps and the 8-bit round.
    const r = snapshotToEditorSkin(
      { body: [0.0009, 0.214941, 0.9991, 1] }, DEFAULTS
    );
    // 0.0 -> 0x03 (the eps lift off the client's all-zero sentinel is visible in
    // the darkest byte and nowhere else), 0.5 -> 0x80 exactly, 1.0 -> 0xff.
    expect(r.colors.body.c).toBe("#0380ff");
  });
  test("slots the snapshot lacks keep the species default, never black", () => {
    const r = snapshotToEditorSkin({ body: [1, 1, 1, 1] }, DEFAULTS);
    expect(r.colors.markings).toEqual(DEFAULTS.markings);
  });
  test("a poisoned sentinel slot is refused; a fully-poisoned snapshot fails honestly", () => {
    const half = snapshotToEditorSkin({ body: [-999999, -999999, -999999, -999999], flank: [0, 1, 0, 1] }, DEFAULTS);
    expect(half.ok).toBe(true);
    expect(half.copiedSlots).toEqual(["flank"]);
    expect(half.colors.body).toEqual(DEFAULTS.body); // sentinel never becomes a colour
    const all = snapshotToEditorSkin({ body: [SKIN_POISON_THRESHOLD, 0, 0, 1] }, DEFAULTS);
    expect(all).toEqual({ ok: false, reason: "poisoned" });
  });
  test("the restart pattern sentinel (-8) and glitch negatives clamp into 0-2", () => {
    expect(snapshotToEditorSkin({ pattern: -8, body: [1, 1, 1, 1] }, DEFAULTS).pattern).toBe(0);
    expect(snapshotToEditorSkin({ pattern: -3, body: [1, 1, 1, 1] }, DEFAULTS).pattern).toBe(0);
    expect(snapshotToEditorSkin({ pattern: 7, body: [1, 1, 1, 1] }, DEFAULTS).pattern).toBe(2);
    expect(snapshotToEditorSkin({ pattern: "x", body: [1, 1, 1, 1] }, DEFAULTS).pattern).toBe(0);
  });
  test("HDR components above 1 clamp instead of overflowing the hex byte", () => {
    const r = snapshotToEditorSkin({ body: [3.2, 1, 0.5, 1] }, DEFAULTS);
    expect(r.colors.body.c).toMatch(/^#[0-9a-f]{6}$/);
    expect(r.colors.body.c.slice(1, 3)).toBe("ff");
  });
  test("no snapshot, junk shapes, NaN channels and short arrays never throw", () => {
    expect(snapshotToEditorSkin(null, DEFAULTS)).toEqual({ ok: false, reason: "none" });
    expect(snapshotToEditorSkin([], DEFAULTS).ok).toBe(false);
    expect(snapshotToEditorSkin("x", DEFAULTS).ok).toBe(false);
    expect(snapshotToEditorSkin({ body: [NaN, 0, 0, 1] }, DEFAULTS)).toEqual({ ok: false, reason: "poisoned" });
    expect(snapshotToEditorSkin({ body: [1, 0] }, DEFAULTS)).toEqual({ ok: false, reason: "poisoned" });
    expect(snapshotToEditorSkin({ body: [0, 1, 0, "x"] }, DEFAULTS).colors.body.a).toBe(1);
  });
  test("alpha outside 0-1 clamps", () => {
    expect(snapshotToEditorSkin({ body: [0, 1, 0, 5] }, DEFAULTS).colors.body.a).toBe(1);
    expect(snapshotToEditorSkin({ body: [0, 1, 0, -1] }, DEFAULTS).colors.body.a).toBe(0);
  });
});

describe("parity — the colour contract holds across the shipped sources", () => {
  // ★2026-08-11: this block used to assert copyLiveSkin was gamma-FREE. Under the
  // linear restore that is exactly backwards, so the pin MOVED rather than being
  // deleted — and it moved to the strongest available form: BEHAVIOURAL parity with
  // the other consumer of the same wire, plus a source-text guard that the transfer
  // function is actually present.
  test("★ONE WIRE, ONE COLOUR SPACE: the copy lane and SpeciesViewer3D's preview " +
    "lane produce the SAME hex from the SAME /api/snapshot payload", () => {
    // SkinEditor.jsx passes GET /api/snapshot's `data.skin` to snapshotToEditorSkin;
    // SpeciesViewer3D.jsx passes the same object to colorsFromRawSkin, which uses
    // tintMaterial's linearToHex. Any divergence is the 08-09..08-11 split returning.
    const probes = [
      [0.0009, 0.214941, 0.9991, 1],   // the seeded wire triple
      [0.1, 0.5, 0.9, 1],
      [0.0, 0.0031308, 1.0, 0.5],
      [0.02, 0.37, 0.64, 1],
    ];
    let decisive = 0;
    probes.forEach((p) => {
      const snap = { body: p };
      const mine = snapshotToEditorSkin(snap, DEFAULTS).colors.body.c;
      expect(mine).toBe(linearToHex(p).c);
      // ★non-vacuous: count the probes where the retired raw conversion would have
      // disagreed, so this cannot pass on degenerate 0/1-only data.
      const rawHex = "#" + p.slice(0, 3)
        .map((c) => Math.round(Math.max(0, Math.min(1, c)) * 255).toString(16).padStart(2, "0"))
        .join("");
      if (rawHex !== mine) decisive += 1;
    });
    expect(decisive).toBe(probes.length);
  });
  test("the transfer function is present and is the IEC curve, not an invention", () => {
    const ours = readSrc("lib", "copyLiveSkin.js");
    ["0.0031308", "12.92", "1.055", "1 / 2.4"].forEach((c) => {
      expect(ours).toContain(c);
    });
    // ...and the OUTBOUND direction stays raw: the backend owns the single encode,
    // so the srgb->LINEAR direction (its own distinct constants) must NOT appear
    // here. That would be the DOUBLE ENCODE.
    expect(ours).not.toContain("0.04045");
    expect(ours).not.toContain("+ 0.055) / 1.055");
  });
  test("the poison threshold matches SpeciesViewer3D's", () => {
    expect(readSrc("components", "skin3d", "SpeciesViewer3D.jsx")).toContain("-900000");
    expect(SKIN_POISON_THRESHOLD).toBe(-900000);
  });
  test("wiring: the skin editor really mounts the feature", () => {
    const page = readSrc("pages", "SkinEditor.jsx");
    expect(page).toMatch(/from "@\/lib\/copyLiveSkin"/);
    expect(page).toContain("copy-live-skin");
    expect(page).toMatch(/presetsSave\(/);
  });
});

// ---------------------------------------------------------------------------
// Exact-copy sidecar (owner report 2026-08-08: a copied glitch skin "changes
// some parts"). Mirrors backend skin_exact.py — the shapes must stay lockstep.
// ---------------------------------------------------------------------------
const { extractRawSnapshot, rawIsLossy } = require("./copyLiveSkin");

const GLITCH_SNAP = {
  female: false, variation: 0, pattern: 2,
  body: [-2.4, 9.455, -3.163, -999],
  markings: [-6.56, -3.575, -9.411, -999],
  flank: [-7.974, 2.019, 5.68, -999],
  underbelly: [6.911, 7.633, 9.792, -999],
  detail1: [-6.545, -4.241, -6.744, -777],
  eyes: [-9.731, 5.732, 4.071, -555],
  male_display: [-1.659, -1.234, -3.192, 999],
};
const INGAMUT_SNAP = {
  female: true, variation: 0.004, pattern: 1,
  body: [0.1, 0.2, 0.3, 1], markings: [0.4, 0.5, 0.6, 1],
  flank: [0.7, 0.8, 0.9, 1], underbelly: [0.15, 0.25, 0.35, 0.5],
  detail1: [0.45, 0.55, 0.65, 1], eyes: [0.75, 0.85, 0.95, 1],
  male_display: [0.05, 0.95, 0.55, 1],
};

describe("extractRawSnapshot — verbatim sidecar", () => {
  test("a glitch snapshot extracts every float VERBATIM (no clamp, no fold)", () => {
    const raw = extractRawSnapshot(GLITCH_SNAP);
    expect(raw).not.toBeNull();
    SKIN_SLOTS.forEach((k) => expect(raw[k]).toEqual(GLITCH_SNAP[k]));
    expect(raw.pattern).toBe(2);
    expect(raw.variation).toBe(0);
  });
  test("the editor conversion RE-AUTHORS the same payload (why the sidecar exists)", () => {
    const converted = snapshotToEditorSkin(GLITCH_SNAP, DEFAULTS);
    expect(converted.ok).toBe(true);
    // -999 alpha and 9.455 channels cannot survive display gamut: the clamped
    // copy differs from the live bytes while the raw sidecar carries them.
    expect(converted.colors.body.a).toBe(0);          // was -999
    expect(converted.colors.body.c).toBe("#00ff00");  // [-2.4, 9.455, -3.163] clamps to pure green
  });
  test("refusals return null, never a partial sidecar", () => {
    expect(extractRawSnapshot({ ...GLITCH_SNAP, body: [-999999, 0, 0, 1] })).toBeNull();   // poison
    expect(extractRawSnapshot({ ...GLITCH_SNAP, pattern: -8 })).toBeNull();                // restart sentinel
    expect(extractRawSnapshot({ ...GLITCH_SNAP, pattern: 1.5 })).toBeNull();               // non-integral
    expect(extractRawSnapshot({ ...GLITCH_SNAP, pattern: 64 })).toBeNull();                // out of replay window
    expect(extractRawSnapshot({ ...GLITCH_SNAP, eyes: [1, 2, 3] })).toBeNull();            // no alpha
    expect(extractRawSnapshot({ ...GLITCH_SNAP, flank: undefined })).toBeNull();           // missing slot
    expect(extractRawSnapshot({ ...GLITCH_SNAP, body: [NaN, 0, 0, 1] })).toBeNull();       // non-finite
    expect(extractRawSnapshot({ ...GLITCH_SNAP, body: [2e12, 0, 0, 1] })).toBeNull();      // over the 1e12 window
    const noVar = { ...GLITCH_SNAP };
    delete noVar.variation;
    expect(extractRawSnapshot(noVar)).toBeNull();                                          // exactness needs the field
    expect(extractRawSnapshot(null)).toBeNull();
    expect(extractRawSnapshot([1, 2])).toBeNull();
    expect(extractRawSnapshot("x")).toBeNull();
  });
  test("2026-08-23 cap parity: magnitudes past the retired 999999 now extract (backend allows 1e12)", () => {
    // The owner's real worn Rex carried body -7952343.5 — the browser used to
    // refuse it before the backend was ever asked. Positive-huge is legal
    // without any grant (only the NEGATIVE sentinel band is poison).
    const raw = extractRawSnapshot({ ...GLITCH_SNAP, body: [7952343.5, 0, 0, 1] });
    expect(raw).not.toBeNull();
    expect(raw.body[0]).toBe(7952343.5);
  });
  test("allowGlitch waives ONLY the channel sentinel (Glitch Lab entitlement)", () => {
    const worn = { ...GLITCH_SNAP, body: [-7952343.5, -79523440.0, -999999.0, -794.234375] };
    expect(extractRawSnapshot(worn)).toBeNull();                                  // default: refused
    const raw = extractRawSnapshot(worn, { allowGlitch: true });
    expect(raw).not.toBeNull();                                                   // entitled: verbatim
    expect(raw.body).toEqual([-7952343.5, -79523440.0, -999999.0, -794.234375]);
    // pattern -8 and the 1e12 window refuse REGARDLESS of the flag
    expect(extractRawSnapshot({ ...worn, pattern: -8 }, { allowGlitch: true })).toBeNull();
    expect(extractRawSnapshot({ ...worn, body: [-2e12, 0, 0, 1] }, { allowGlitch: true })).toBeNull();
  });
});

describe("rawIsLossy — when the pickers cannot hold the truth", () => {
  test("glitch payload is lossy; in-gamut payload is not", () => {
    expect(rawIsLossy(extractRawSnapshot(GLITCH_SNAP))).toBe(true);
    expect(rawIsLossy(extractRawSnapshot(INGAMUT_SNAP))).toBe(false);
  });
  test("out-of-editor pattern alone is lossy; apply-lane variation jitter is not", () => {
    expect(rawIsLossy({ ...extractRawSnapshot(INGAMUT_SNAP), pattern: 12 })).toBe(true);
    expect(rawIsLossy({ ...extractRawSnapshot(INGAMUT_SNAP), variation: 0.01 })).toBe(false);
    expect(rawIsLossy({ ...extractRawSnapshot(INGAMUT_SNAP), variation: 5 })).toBe(true);
  });
  test("never throws on junk", () => {
    expect(rawIsLossy(null)).toBe(false);
    expect(rawIsLossy({})).toBe(false);
    expect(rawIsLossy({ body: "zz" })).toBe(false);
  });
});
