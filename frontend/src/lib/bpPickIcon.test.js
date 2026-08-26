/**
 * Battle-pass dino PICK cells must show dino art, not the generic crown badge
 * (owner order 2026-08-08, pointing at the level-50 cells on both rows).
 *
 * Two halves, both real:
 *  1. pickIconSlug() driven directly, including hostile input;
 *  2. the REAL RewardCard.jsx and the REAL public/dinos folder read off disk,
 *     proving the card actually routes pick cells through the helper and that
 *     every stand-in species has a picture to serve. A perfect helper with the
 *     card still rendering <Crown/>, or a slug with no PNG behind it, is exactly
 *     the failure this change removes — and a 404 is invisible in a unit test.
 */
const fs = require("fs");
const path = require("path");
const {
  pickIconSlug,
  PICK_ICON_BY_BAND,
  PICK_ICON_ALL_BY_LEVEL,
  PICK_ICON_FALLBACK,
} = require("./bpPickIcon");

const CARD = fs.readFileSync(
  path.join(__dirname, "..", "components", "battlepass", "RewardCard.jsx"),
  "utf8"
);
const DINO_DIR = path.join(__dirname, "..", "..", "public", "dinos");

describe("pickIconSlug", () => {
  test("a regular-row pick shows its band's stand-in", () => {
    expect(pickIconSlug({ type: "dino", band: "low", level: 25 })).toBe("galli");
    expect(pickIconSlug({ type: "dino", band: "mid", level: 50 })).toBe("carno");
    expect(pickIconSlug({ type: "dino", band: "high", level: 75 })).toBe("allo");
  });

  test("the premium row's unrestricted picks rotate, never repeating one animal", () => {
    const shown = [25, 50, 75].map((level) => pickIconSlug({ type: "dino", band: "all", level }));
    expect(shown).toEqual(["raptor", "trike", "deino"]);
    expect(new Set(shown).size).toBe(3);
  });

  test("a premium pick never wears the level-100 rex the same row already grants", () => {
    for (const level of [25, 50, 75]) {
      expect(pickIconSlug({ type: "dino", band: "all", level })).not.toBe("trex");
    }
  });

  test("a FIXED dino cell keeps its own species - the helper stands aside", () => {
    expect(pickIconSlug({ type: "dino", band: "apex", level: 100, slug: "trex" })).toBeNull();
    expect(pickIconSlug({ type: "dino", band: "apex", level: 100, slug: "trike" })).toBeNull();
  });

  test("cells that are not dinos get nothing", () => {
    expect(pickIconSlug({ type: "coins", amount: 16210, level: 49 })).toBeNull();
    expect(pickIconSlug({ type: "amber", amount: 40, level: 30 })).toBeNull();
    expect(pickIconSlug({ type: "token", token: "diet", level: 20 })).toBeNull();
    expect(pickIconSlug({ type: "skin", skin: { name: "x" }, level: 35 })).toBeNull();
    expect(pickIconSlug({ type: "empty", level: 35 })).toBeNull();
  });

  test("hostile and first-run input degrades to a real picture, never a crash", () => {
    expect(pickIconSlug(null)).toBeNull();
    expect(pickIconSlug(undefined)).toBeNull();
    expect(pickIconSlug({})).toBeNull();
    // A dino cell with no band at all, an unknown band, or a moved pick level:
    // all still name a species that exists.
    expect(pickIconSlug({ type: "dino", level: 50 })).toBe(PICK_ICON_FALLBACK);
    expect(pickIconSlug({ type: "dino", band: "titan", level: 50 })).toBe(PICK_ICON_FALLBACK);
    expect(pickIconSlug({ type: "dino", band: "all", level: 51 })).toBe(PICK_ICON_FALLBACK);
    expect(pickIconSlug({ type: "dino", band: "all", level: null })).toBe(PICK_ICON_FALLBACK);
    expect(pickIconSlug({ type: "dino", band: "all", level: "50" })).toBe("trike");
    expect(pickIconSlug({ type: "dino", slug: "", band: "mid", level: 50 })).toBe("carno");
  });
});

describe("every stand-in species has a picture on disk", () => {
  const slugs = [
    ...Object.values(PICK_ICON_BY_BAND),
    ...Object.values(PICK_ICON_ALL_BY_LEVEL),
    PICK_ICON_FALLBACK,
  ];

  test.each([...new Set(slugs)])("/dinos/%s.png exists and is not empty", (slug) => {
    const p = path.join(DINO_DIR, `${slug}.png`);
    expect(fs.existsSync(p)).toBe(true);
    expect(fs.statSync(p).size).toBeGreaterThan(1024);
  });
});

describe("RewardCard actually renders the stand-in", () => {
  test("the card imports the helper", () => {
    expect(CARD).toMatch(/import\s*\{\s*pickIconSlug\s*\}\s*from\s*"@\/lib\/bpPickIcon"/);
  });

  test("rewardIcon falls back to the stand-in when a dino cell has no slug", () => {
    expect(CARD).toMatch(/pickIconSlug\(cell\)/);
    // The old shape returned null for a slugless dino cell; that line is gone.
    expect(CARD).not.toMatch(/cell\.type === "dino" && cell\.slug/);
  });

  test("a picture that fails to load falls back to the badge, not to a hole", () => {
    expect(CARD).toMatch(/setBadIcon\(icon\)/);
    expect(CARD).not.toMatch(/currentTarget\.style\.visibility = "hidden"/);
  });
});
