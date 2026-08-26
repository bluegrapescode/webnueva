/**
 * /my-dino tab split.
 *
 * Two halves, both real:
 *  1. resolveMyDinoTab() driven directly, including hostile input;
 *  2. the REAL MyDino.jsx and App.js read off disk, proving the page actually
 *     wires the helper up, that the belongings live in their OWN tab branch and
 *     not stapled to the bottom of the live panel, and that /inventory lands on
 *     the belongings tab.
 *
 * The source assertions matter: the pure helper can be perfect while the page
 * still renders the vault under the stats tab, which is exactly the layout this
 * change removes.
 */
const fs = require("fs");
const path = require("path");
const { resolveMyDinoTab, MY_DINO_TABS, MY_DINO_DEFAULT_TAB } = require("./myDinoTabs");

describe("resolveMyDinoTab", () => {
  test("the four tabs are the ones the page renders", () => {
    expect(MY_DINO_TABS).toEqual(["stats", "equipo", "map", "gen0"]);
    expect(MY_DINO_DEFAULT_TAB).toBe("stats");
  });

  test.each(MY_DINO_TABS)("?tab=%s resolves to itself", (k) => {
    expect(resolveMyDinoTab(`?tab=${k}`)).toBe(k);
    expect(resolveMyDinoTab(`tab=${k}`)).toBe(k); // leading "?" optional
  });

  test("the belongings tab is reachable by link", () => {
    expect(resolveMyDinoTab("?tab=equipo")).toBe("equipo");
    expect(resolveMyDinoTab("?foo=1&tab=equipo&bar=2")).toBe("equipo");
  });

  test("no query string opens the live panel", () => {
    expect(resolveMyDinoTab("")).toBe("stats");
    expect(resolveMyDinoTab("?")).toBe("stats");
    expect(resolveMyDinoTab("?other=equipo")).toBe("stats");
  });

  test("an unknown or hostile tab falls back instead of blanking the page", () => {
    const hostile = [
      "?tab=vault", "?tab=EQUIPO", "?tab=equipo%20", "?tab=", "?tab=__proto__",
      "?tab=constructor", "?tab=" + "x".repeat(5000), "?tab=<script>",
      null, undefined, 0, {}, [], NaN, true,
    ];
    for (const h of hostile) expect(resolveMyDinoTab(h)).toBe("stats");
  });

  test("only ever returns a real tab key", () => {
    const samples = ["?tab=map", "?tab=nope", "", "?tab=equipo", "???", "?tab=1&tab=2"];
    for (const s of samples) expect(MY_DINO_TABS).toContain(resolveMyDinoTab(s));
  });
});

describe("MyDino.jsx wiring", () => {
  const src = fs.readFileSync(path.resolve(__dirname, "../pages/MyDino.jsx"), "utf8");

  test("the page reads its tab from the shared helper, not its own parser", () => {
    expect(src).toContain('import { resolveMyDinoTab } from "@/lib/myDinoTabs"');
    expect(src).toContain("resolveMyDinoTab(window.location.search)");
    expect(src).toContain("resolveMyDinoTab(location.search)");
  });

  test("Equipo is a tab of its own", () => {
    expect(src).toContain('{ k: "equipo", label: "Equipo", icon: Package }');
    expect(src).toContain('tab === "equipo"');
  });

  test("the vault and inventory render ONLY inside the equipo branch", () => {
    const equipo = src.indexOf('tab === "equipo"');
    const map = src.indexOf('tab === "map"');
    expect(equipo).toBeGreaterThan(-1);
    expect(map).toBeGreaterThan(equipo); // equipo branch sits before the map branch
    for (const marker of ["<VaultSection />", "<InventoryPanel />", 'data-testid="mydino-equipment"']) {
      const first = src.indexOf(marker);
      expect(first).toBeGreaterThan(equipo); // never above the branch it belongs to
      expect(first).toBeLessThan(map);       // and never below it
      expect(src.indexOf(marker, first + 1)).toBe(-1); // exactly one copy
    }
  });

  test("the 2026-08-07 reference redesign carries no per-tab subtitle at all", () => {
    // The owner's reference card has a bare red-bar page title and nothing
    // else; the old SUBTITLES block must not creep back with stale live-claim
    // copy on the belongings tab.
    expect(src).not.toContain("SUBTITLES");
    expect(src).toContain('data-testid="livedino-title"');
  });

  test("the belongings are no longer stapled to the bottom of the stats tab", () => {
    // the old layout's own marker: the block carried mt-12 to push it away from
    // the Prime route it sat under.
    expect(src).not.toContain('className="mt-12" data-testid="mydino-equipment"');
  });
});

describe("App.js routing", () => {
  const src = fs.readFileSync(path.resolve(__dirname, "../App.js"), "utf8");

  test("the retired /inventory route lands on the belongings tab", () => {
    expect(src).toContain('<Route path="/inventory" element={<Navigate to="/my-dino?tab=equipo" replace />} />');
  });
});
