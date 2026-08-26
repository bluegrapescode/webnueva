/**
 * Nublar Spin frontend gate — the pure carousel maths + copy, and the wiring
 * read off disk (the gen0.test.js idiom: no render library here; a helper can
 * be perfect while the tab is never mounted, so the source assertions close
 * that gap).
 */
const fs = require("fs");
const path = require("path");
const {
  cardContent, cardTheme, computeLayout, fmtTimeLeft, newCmdId, oddsText, poolItems, rarityLabel,
  relTime, rewardLine, segmentImage, spinTarget, spinsCopy, winnerKey,
} = require("./wheelMath");

const src = (p) => fs.readFileSync(path.join(__dirname, "..", "..", p), "utf8");
const here = (p) => fs.readFileSync(path.join(__dirname, p), "utf8");

describe("spinTarget — always forward, lands exactly on the drawn plate", () => {
  const STEP = 200, N = 14;
  test.each([
    [0, 0], [0, 5], [0, 13], [3 * STEP, 1], [37 * STEP, 9], [(4 * N + 2) * STEP, 2],
  ])("from x=%s to plate %s", (x, idx) => {
    const t = spinTarget(x, STEP, N, idx);
    // visually identical reset (same plate under the pointer)
    expect(Math.round(t.resetX / STEP) % N).toBe(((Math.round(x / STEP) % N) + N) % N);
    // at least 4 full turns forward
    expect(t.targetSteps - Math.round(t.resetX / STEP)).toBeGreaterThanOrEqual(4 * N);
    expect(t.targetSteps - Math.round(t.resetX / STEP)).toBeLessThan(5 * N);
    // lands on the drawn plate
    expect(((t.targetSteps % N) + N) % N).toBe(idx);
    expect(t.targetX).toBe(t.targetSteps * STEP);
  });
  test("an out-of-range index is folded, never NaN", () => {
    const t = spinTarget(0, 200, 14, 30);
    expect(((t.targetSteps % 14) + 14) % 14).toBe(2);
    expect(Number.isFinite(t.targetX)).toBe(true);
  });
  test("empty table → no travel", () => {
    expect(spinTarget(0, 200, 0, 0)).toEqual({ resetX: 0, targetSteps: 0, targetX: 0 });
  });
  test("winnerKey names the strip card under the pointer", () => {
    const N = 14, center = Math.floor((12 * N) / 2);
    const t = spinTarget(0, 200, N, 5);
    expect(winnerKey(center, t.targetSteps, N, 5)).toBe(`${Math.floor((center + t.targetSteps) / N)}-5`);
  });
});

describe("card copy + theme", () => {
  test("every plate kind has copy and a rarity theme", () => {
    for (const kind of ["primemeat", "amberium", "growth_token", "diet_token", "glitch_skin", "dino_basic", "dino_prime", "gen0_vial"]) {
      const cc = cardContent({ kind, amount: 2500, label: "x" });
      expect(cc.category).toBeTruthy(); expect(cc.title).toBeTruthy();
    }
    expect(cardContent({ kind: "primemeat", amount: 2500 }).title).toBe("2.500");
    expect(cardContent({ kind: "growth_token", flavor: "premium" }).subtitle).toMatch(/PRIME/);
    expect(cardContent(null).title).toBe("?");
    for (const r of ["common", "rare", "epic", "legendary"]) expect(cardTheme({ rarity: r }).accent).toMatch(/^#/);
    expect(cardTheme({ rarity: "nope" }).accent).toMatch(/^#/);
    expect(rarityLabel("legendary")).toBe("LEGENDARIO");
  });
  test("a glitch skin plate has NO picture (fleet order: name + colour proximity)", () => {
    expect(segmentImage({ kind: "glitch_skin" })).toBeNull();
    expect(segmentImage({ kind: "dino_prime" })).toBeNull();
    expect(segmentImage({ kind: "gen0_vial" })).toBe("/tokens/vial-gen0.png");
    expect(segmentImage({ kind: "primemeat" })).toBe("/coins/meat.png");
  });
  test("rewardLine tells the winner where the prize landed", () => {
    expect(rewardLine({ kind: "dino_prime", name: "Carnotaurus" })).toMatch(/Bóveda/);
    expect(rewardLine({ kind: "growth_token", flavor: "premium" })).toMatch(/PRIME/);
    expect(rewardLine({ kind: "gen0_vial" })).toMatch(/inventario/i);
    expect(rewardLine({ kind: "primemeat", amount: 20000 })).toBe("+20.000 PrimeMeat en tu cuenta");
    expect(rewardLine(null)).toBe("");
  });
});

describe("spins chip copy", () => {
  test("non-patron with the free spin", () => {
    const c = spinsCopy({ enabled: true, allowance: 1, used_today: 0, left_today: 1, bonus_spins: 0, tier_key: null });
    expect(c.available).toBe(1); expect(c.line).toBe("giro disponible"); expect(c.daily).toBe("0 de 1 hoy"); expect(c.patreon).toMatch(/\+1 giro diario por nivel/);
  });
  test("apex patron mid-day + bonus", () => {
    const c = spinsCopy({ enabled: true, allowance: 6, used_today: 4, left_today: 2, bonus_spins: 3, tier_key: "apex", patreon_bonus: 5 });
    expect(c.available).toBe(5); expect(c.line).toBe("giros disponibles");
    expect(c.line).not.toMatch(/\d/); // the chip shows the count once, as the big number expect(c.daily).toBe("4 de 6 hoy"); expect(c.patreon).toBe("Patreon Apex: +5 por día"); expect(c.bonus).toBe(3);
  });
  test("nothing left / closed / hostile input", () => {
    expect(spinsCopy({ enabled: true, allowance: 1, used_today: 1, left_today: 0, bonus_spins: 0 }).line).toMatch(/vuelve mañana/);
    expect(spinsCopy({ enabled: false, allowance: 1, used_today: 0, left_today: 1 }).line).toMatch(/cerrada/);
    expect(spinsCopy(null).available).toBe(0);
    expect(spinsCopy({ left_today: -3, bonus_spins: "x" }).available).toBe(0);
  });
});

describe("time + ids", () => {
  test("fmtTimeLeft counts down to the UTC reset and clamps at 00:00:00", () => {
    const now = Date.parse("2026-08-23T21:30:15Z");
    expect(fmtTimeLeft("2026-08-24T00:00:00+00:00", now)).toBe("02:29:45");
    expect(fmtTimeLeft("2026-08-23T00:00:00+00:00", now)).toBe("00:00:00");
    expect(fmtTimeLeft(null, now)).toBe("");
    expect(fmtTimeLeft("garbage", now)).toBe("");
  });
  test("relTime", () => {
    const now = Date.parse("2026-08-23T10:00:00Z");
    expect(relTime("2026-08-23T09:59:30Z", now)).toBe("hace 30s");
    expect(relTime("2026-08-23T08:00:00Z", now)).toBe("hace 2h");
    expect(relTime("2026-08-20T08:00:00Z", now)).toBe("hace 3d");
  });
  test("newCmdId is unique per attempt and matches the server's CMD_RE", () => {
    const a = newCmdId(), b = newCmdId();
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[A-Za-z0-9_.:-]{6,64}$/);
  });
  test("computeLayout keeps the viewport taller than the 1.18x centre card", () => {
    // The centre plate is scaled 1.18 and the frame adds tick marks above and
    // below it; a VIEW_H under that clips the winning card at every breakpoint.
    for (const w of [320, 600, 900, 1200, 1600]) {
      const L = computeLayout(w);
      expect(L.VIEW_H).toBeGreaterThanOrEqual(Math.round(L.CARD_H * 1.18) + 20);
      expect(L.STEP_X).toBeGreaterThan(L.CARD_W); // plates never overlap
    }
  });

  test("computeLayout is monotonic in width", () => {
    const ws = [320, 600, 900, 1200, 1600].map(computeLayout);
    for (let i = 1; i < ws.length; i++) expect(ws[i].CARD_W).toBeGreaterThanOrEqual(ws[i - 1].CARD_W);
  });
});

describe("the wiring actually exists (read off disk)", () => {
  test("api.js carries the named wheel methods (no generic .get on this api map)", () => {
    const api = src("lib/api.js");
    for (const m of ["wheelConfig", "wheelStatus", "wheelSpin", "wheelHistory", "wheelUseVial", "wheelAdminConfig", "wheelAdminSave", "wheelAdminReset", "wheelAdminGrantSpins", "wheelAdminRecent"]) {
      expect(api).toMatch(new RegExp(`\\b${m}\\s*:`));
    }
    expect(api).toMatch(/wheelSpin:\s*\(cmd_id\)\s*=>\s*client\.post\("\/wheel\/spin",\s*\{\s*cmd_id\s*\}\)/);
  });
  test("Casino mounts the wheel as a tab and gives it the full width", () => {
    const casino = src("pages/Casino.jsx");
    expect(casino).toMatch(/import Wheel from "@\/components\/casino\/Wheel"/);
    expect(casino).toMatch(/\{\s*k:\s*"wheel",\s*label:\s*"Ruleta Diaria"/);
    expect(casino).toMatch(/FULL_WIDTH\s*=\s*\[[^\]]*"wheel"/);
  });
  test("the tab uses this site's token key, sound context and glitch face", () => {
    const wheel = here("Wheel.jsx");
    expect(wheel).toMatch(/localStorage\.getItem\("primal_token"\)/);
    expect(wheel).not.toMatch(/localStorage\.getItem\("token"\)/);
    expect(wheel).toMatch(/useSound\(\)/);
    expect(wheel).toMatch(/GlitchProx/);
    expect(wheel).not.toMatch(/\/skins\/glitch\.png|\/skins\/epic\.png/);
    expect(wheel).not.toMatch(/from "canvas-confetti"/);
    expect(wheel).toMatch(/api\.wheelSpin\(cmdId\)/);
    expect(wheel).toMatch(/PENDING/);          // in-flight duplicate → re-send the same cmd_id
    expect(wheel).toMatch(/data\.segments/);   // settles on the table the server drew from
  });
  test("sounds.js registers the wheel events and keeps the creator sounds", () => {
    const s = src("lib/sounds.js");
    for (const k of ["wheelStart", "wheelTick", "wheelStop", "wheelReveal", "wheelJackpot"]) expect(s).toMatch(new RegExp(`\\n  ${k}:`));
    expect(s).toMatch(/\n  newReferral:/);
    expect(s).toMatch(/\n  rewardReceived:/);
    expect(s).toMatch(/\n  zombieRoar:/);
  });
  test("the wheel audio files the pool names are shipped", () => {
    const pub = path.join(__dirname, "..", "..", "..", "public");
    for (const f of ["whoosh", "tick", "impact", "coin", "sparkle", "reveal_rare", "reveal_legendary", "jackpot"]) {
      expect(fs.existsSync(path.join(pub, "sounds", "wheel", `${f}.mp3`))).toBe(true);
    }
    for (const f of ["coins/meat.png", "coins/amber.png", "tokens/growth.png", "tokens/diet.png", "tokens/vial-gen0.png"]) {
      expect(fs.existsSync(path.join(pub, f))).toBe(true);
    }
  });
  test("Admin mounts the owner-only Ruleta tab", () => {
    const admin = src("pages/Admin.jsx");
    expect(admin).toMatch(/import \{ WheelAdminTab \} from "@\/components\/admin\/WheelAdminTab"/);
    expect(admin).toMatch(/\{\s*k:\s*"wheel",\s*label:\s*"Ruleta"/);
    expect(admin).toMatch(/tab === "wheel" && user\.is_owner && <WheelAdminTab \/>/);
  });
  test("the inventory shows the Vial GEN-Ø under Fichas with a two-press use", () => {
    const inv = src("components/inventory/InventoryPanel.jsx");
    expect(inv).toMatch(/c === "Consumables"\) \? "Fichas"/);
    expect(inv).toMatch(/const VIAL_ITEM_ID = "wheel_gen0_vial"/);
    expect(inv).toMatch(/it\.item_id === VIAL_ITEM_ID/);
    // the card shows the owner's GEN-Ø render even for rows Mongo wrote
    // with the old placeholder path
    expect(inv).toMatch(/const VIAL_ART = "\/tokens\/vial-gen0\.png"/);
    expect(inv).toMatch(/it\.item_id === VIAL_ITEM_ID \? VIAL_ART/);
    expect(inv).toMatch(/api\.wheelUseVial\(invId\)/);
    expect(inv).toMatch(/use-inv-vial-confirm-/);
  });
});

describe("admin odds helper", () => {
  const { oddsOf } = require("../admin/WheelAdminTab");
  test("normalises any weights; zero table → all 0", () => {
    expect(oddsOf([{ weight: 1 }, { weight: 3 }])).toEqual([25, 75]);
    expect(oddsOf([{ weight: 0 }, { weight: 0 }])).toEqual([0, 0]);
    expect(oddsOf([{ weight: -5 }, { weight: 5 }])).toEqual([0, 100]);
    expect(oddsOf([])).toEqual([]);
  });
});

describe("prize pool", () => {
  const segs = [
    { key: "a", probability: 20, rarity: "common" },
    { key: "b", probability: 2.5, rarity: "epic" },
    { key: "c", probability: 10, rarity: "rare" },
    { key: "d", probability: 0, rarity: "legendary" },
  ];

  test("poolItems sorts best odds first and keeps every plate", () => {
    const out = poolItems(segs);
    expect(out).toHaveLength(4);
    expect(out.map((it) => it.seg.key)).toEqual(["a", "c", "b", "d"]);
  });

  test("poolItems normalises the bar to the likeliest plate, never to the raw %", () => {
    const out = poolItems(segs);
    expect(out[0].barPct).toBe(100);          // 20% is the max -> full bar
    expect(out[1].barPct).toBe(50);           // 10% of 20% -> half
    // 2.5% of 20% is 12.5 -> 13, which is still a VISIBLE bar. Raw-percent
    // widths made 20% and 16% the same three pixels, which is why the odds
    // column read as broken.
    expect(out[2].barPct).toBe(13);
    expect(out[3].barPct).toBe(4);            // a zero-odds plate keeps a floor
  });

  test("poolItems survives junk", () => {
    expect(poolItems(null)).toEqual([]);
    expect(poolItems([{ key: "x" }])[0].prob).toBe(0);
    expect(poolItems([{ key: "x" }])[0].barPct).toBe(0);
  });

  test("oddsText prints one decimal above 1% and two below, and nothing for none", () => {
    expect(oddsText(20)).toBe("20.0%");
    expect(oddsText(2.5)).toBe("2.5%");
    expect(oddsText(0.75)).toBe("0.75%");
    expect(oddsText(0)).toBe("");
    expect(oddsText(undefined)).toBe("");
    expect(oddsText("nope")).toBe("");
  });
});
