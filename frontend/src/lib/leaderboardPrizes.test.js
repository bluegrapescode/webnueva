import { PRIZE_META, normalizeSkin, prizeCards } from "./leaderboardPrizes";

const SUPERNOVA = {
  glitch_id: "supernova",
  name: "Supernova",
  subtitle: "Estallido estelar — rojo, azul y blanco sobre negro",
  accent_hex: "#e0566e",
  accent: "#e0566e",
  category: "cosmos",
  rarity: "Legendary",
  image: "",
  proximity: ["#000000", "#000000", "#ffffff", "#000000", "#000000", "#ff00ff", "#00ffff"],
};

describe("leaderboardPrizes", () => {
  test("three cards, gold/silver/bronze, in rank order", () => {
    expect(PRIZE_META.map((m) => m.rank)).toEqual([1, 2, 3]);
    const cards = prizeCards({ 1: 5000000, 2: 3000000, 3: 1000000 }, {});
    expect(cards.map((c) => c.amount)).toEqual([5000000, 3000000, 1000000]);
    expect(cards.map((c) => c.label)).toEqual(["1º", "2º", "3º"]);
  });

  // Owner order 2026-08-18: "supernova for 123 place in leaderboard".
  test("the cosmetic rides the whole podium", () => {
    const cards = prizeCards({ 1: 5000000, 2: 3000000, 3: 1000000 },
                             { 1: SUPERNOVA, 2: SUPERNOVA, 3: SUPERNOVA });
    cards.forEach((c) => {
      expect(c.skin.name).toBe("Supernova");
      expect(c.skin.glitch_id).toBe("supernova");
    });
    // the skin ADDS, it never replaces: the money ladder is untouched
    expect(cards.map((c) => c.amount)).toEqual([5000000, 3000000, 1000000]);
  });

  // Still the shape a pre-2026-08-18 backend sends, and the shape any future
  // narrowing would send: a rank with no skin must still draw its money card.
  test("a rank with no cosmetic still draws", () => {
    const cards = prizeCards({ 1: 5000000, 2: 3000000, 3: 1000000 }, { 1: SUPERNOVA });
    expect(cards[0].skin.name).toBe("Supernova");
    expect(cards[1].skin).toBeNull();
    expect(cards[2].skin).toBeNull();
    expect(cards.map((c) => c.amount)).toEqual([5000000, 3000000, 1000000]);
  });

  test("a skin card never carries a picture, only a name and a colour strip", () => {
    const skin = normalizeSkin({ ...SUPERNOVA, image: "/glitch/previews/supernova.webp" });
    expect(skin.image).toBeUndefined();
    expect(Object.keys(skin).sort()).toEqual(["accent", "glitch_id", "name", "proximity"]);
    expect(skin.proximity).toHaveLength(7);
  });

  test("proximity hexes are validated before they can reach a style attribute", () => {
    const skin = normalizeSkin({
      ...SUPERNOVA,
      accent: "red; background:url(javascript:alert(1))",
      proximity: ["#000000", "not-a-hex", "#fff", 42, null, "#ABCDEF", "#00ff00; x"],
    });
    expect(skin.accent).toBeNull();
    expect(skin.proximity).toEqual(["#000000", "#ABCDEF"]);
  });

  test("degenerate backend answers still draw three cards", () => {
    for (const bad of [null, undefined, "boom", 7, []]) {
      const cards = prizeCards(bad, bad);
      expect(cards).toHaveLength(3);
      expect(cards.every((c) => c.amount === 0 && c.skin === null)).toBe(true);
    }
  });

  test("a malformed amount reads as zero, never NaN on a public page", () => {
    const cards = prizeCards({ 1: "lots", 2: -5, 3: null }, {});
    expect(cards.map((c) => c.amount)).toEqual([0, 0, 0]);
    expect(cards.every((c) => Number.isFinite(c.amount))).toBe(true);
    // a numeric string IS a number the API could legitimately send
    expect(prizeCards({ 1: "5000000" }, {})[0].amount).toBe(5000000);
  });

  test("a nameless or non-object skin is dropped, not half-rendered", () => {
    expect(normalizeSkin(null)).toBeNull();
    expect(normalizeSkin("supernova")).toBeNull();
    expect(normalizeSkin({ glitch_id: "supernova", name: "   " })).toBeNull();
    expect(normalizeSkin({ glitch_id: "supernova" })).toBeNull();
    expect(prizeCards({ 1: 5000000 }, { 1: { name: "" } })[0].skin).toBeNull();
  });

  test("a skin with no proximity strip still renders its name", () => {
    const skin = normalizeSkin({ glitch_id: "x", name: "Retirada", proximity: null });
    expect(skin.name).toBe("Retirada");
    expect(skin.proximity).toEqual([]);
  });
});
