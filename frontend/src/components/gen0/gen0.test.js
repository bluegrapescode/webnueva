/**
 * GEN-Ø frontend gate — the pure status ladder plus the page/hook/sound wiring
 * read off disk (the myDinoTabs.test.js idiom in this repo: no render library
 * is installed here, and the pure helper can be perfect while the page never
 * mounts the panel — the source assertions close that gap).
 */
const fs = require("fs");
const path = require("path");
const { gen0StatusFor, formatGen0Cooldown } = require("./useGen0Contamination");

describe("gen0StatusFor — the owner's five states at his exact thresholds", () => {
  test.each([
    [0, "clean"], [24.9, "clean"],
    [25, "initial"], [49.9, "initial"],
    [50, "active"], [74.9, "active"],
    [75, "advanced"], [99.9, "advanced"],
    [100, "complete"],
  ])("%s%% -> %s", (pct, key) => {
    expect(gen0StatusFor(pct).key).toBe(key);
  });

  test("hostile input clamps instead of blanking the panel", () => {
    for (const v of [NaN, null, undefined, -5, 400, "abc", {}]) {
      const s = gen0StatusFor(v);
      expect(["clean", "complete"]).toContain(s.key);
      expect(s.label).toBeTruthy();
    }
  });
});

describe("the wiring actually exists (read off disk)", () => {
  const src = (p) => fs.readFileSync(path.join(__dirname, "..", "..", p), "utf8");
  const here = (p) => fs.readFileSync(path.join(__dirname, p), "utf8");

  test("the hook is LIVE-wired to the backend, not the bundle's DEMO oscillator", () => {
    const hook = here("useGen0Contamination.js");
    // ★the repo's `api` is a NAMED-METHOD map with NO generic .get — calling
    // api.get() crashed the tab live ("Vm.get is not a function"). The hook
    // must use the named method, and the method must exist in api.js.
    expect(hook).toMatch(/api\s*\.\s*gen0Contamination\(\)/);
    expect(hook).not.toMatch(/api\s*\.\s*get\(/);
    expect(src("lib/api.js")).toMatch(/gen0Contamination: \(\) => client\.get\("\/gen0\/contamination"\)/);
    expect(hook).toMatch(/from "@\/lib\/api"/);
    expect(hook).toMatch(/Math\.max\(0, Math\.min\(100, p\)\)/); // clamped
    expect(hook).toMatch(/Number\.isFinite\(p\)/);               // NaN-guarded
    expect(hook).toMatch(/\.catch\(\(\) => \{\}\)/);             // fault keeps last value
    expect(hook).not.toMatch(/dir = 1/);                         // DEMO block gone
    expect(hook).toMatch(/setInterval\(load, 15_000\)/);         // README Option A cadence
    expect(hook).toMatch(/clearInterval/);                       // unmount cleans up
  });

  test("MyDino.jsx mounts the panel under a gen0 tab", () => {
    const page = src("pages/MyDino.jsx");
    expect(page).toMatch(/from "@\/components\/gen0\/Gen0VirusPanel"/);
    expect(page).toMatch(/\{ k: "gen0", label: "GEN-Ø", icon: Dna \}/);
    expect(page).toMatch(/tab === "gen0"/);
    expect(page).toMatch(/Dna/);
    // the tab has no meState dependency, so it must not sit behind the
    // "Cargando…" gate that waits on /me-state (refuter finding 2026-08-21)
    expect(page).toMatch(/meState === undefined && tab !== "equipo" && tab !== "gen0"/);
  });

  test("the panel never paints a NaN prop", () => {
    const panel = here("Gen0VirusPanel.jsx");
    expect(panel).toMatch(/Number\.isFinite\(percentProp\)/);
    expect(panel).not.toMatch(/typeof percentProp === "number"/);
  });

  test("the zombie roar exists in SOUNDS and the panel plays it at 100%", () => {
    expect(src("lib/sounds.js")).toMatch(/zombieRoar: \(\) => \{/);
    const panel = here("Gen0VirusPanel.jsx");
    expect(panel).toMatch(/play\("zombieRoar"\)/);
    // the demo-reset button never renders on the live feed
    expect(panel).toMatch(/source !== "live" && \(/);
  });

  test("?tab=gen0 deep link resolves", () => {
    const { resolveMyDinoTab } = require("../../lib/myDinoTabs");
    expect(resolveMyDinoTab("?tab=gen0")).toBe("gen0");
  });
});

describe("between-facility cooldown (owner 2026-08-21: countdown on the site)", () => {
  test.each([
    [0, "00:00:00"], [59, "00:00:59"], [60, "00:01:00"], [3661, "01:01:01"],
    [7200, "02:00:00"], [7199.6, "01:59:59"], [86399, "23:59:59"],
  ])("formatGen0Cooldown(%s) -> %s", (s, out) => {
    expect(formatGen0Cooldown(s)).toBe(out);
  });

  test("hostile input paints 00:00:00, never NaN or a crash", () => {
    for (const v of [NaN, null, undefined, -5, "abc", {}, Infinity, -Infinity]) {
      expect(formatGen0Cooldown(v)).toBe("00:00:00");
    }
  });

  const here = (p) => fs.readFileSync(path.join(__dirname, p), "utf8");

  test("the hook surfaces the backend's cooldown fields, NaN-guarded and anchored", () => {
    const hook = here("useGen0Contamination.js");
    expect(hook).toMatch(/Number\(r\?\.data\?\.cooldown_s\)/);
    expect(hook).toMatch(/Number\.isFinite\(cd\)/);          // junk never lands
    expect(hook).toMatch(/atMs: Date\.now\(\)/);             // local tick anchor
    expect(hook).toMatch(/cooldownS: cooldown\.s/);
  });

  test("the LIVE lock releases when the backend resets the bar (zombie died)", () => {
    // /validate refutation: `locked` froze the panel at 100% forever, so after
    // a zombie death + reset the countdown strip could never show again and
    // the bar lied at 100. The live feed dropping below 100 must unlock.
    const panel = here("Gen0VirusPanel.jsx");
    expect(panel).toMatch(/locked && source === "live" && rawPercent < 100/);
    const unlockBranch = panel.split('locked && source === "live"')[1] || "";
    expect(unlockBranch).toMatch(/setLocked\(false\)/);
    expect(unlockBranch).toMatch(/roaredRef\.current = false/);
  });

  test("the panel ticks the countdown locally and hides it at 100%", () => {
    const panel = here("Gen0VirusPanel.jsx");
    expect(panel).toMatch(/formatGen0Cooldown/);             // shared pure formatter
    expect(panel).toMatch(/data-testid="gen0-cooldown-timer"/);
    expect(panel).toMatch(/cdLeftS > 0 && clamped < 100 &&/); // hidden once mutated
    expect(panel).toMatch(/setInterval\(\(\) => setCdNowMs\(Date\.now\(\)\), 1000\)/);
    expect(panel).toMatch(/clearInterval\(t\)/);             // unmount cleans up
    expect(panel).toMatch(/Math\.max\(0, Math\.ceil\(cooldownS - \(cdNowMs - cooldownAtMs\) \/ 1000\)\)/);
  });
});
