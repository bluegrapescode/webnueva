// Behaviour pins for @/lib/tradeRules — the rules, arithmetic and copy behind
// the Intercambios page.
//
// These tests pin BEHAVIOUR, not implementation: the exact band edge, the exact
// refusal sentences the server also returns, the exact order the server checks
// things in, and — the point of the whole file — that NOTHING is quoted that the
// payload did not carry.

const fs = require("fs");
const path = require("path");

import {
  pluralEs, waitEs, readTradeConfig, configBlockReason, symmetryOk, bandRange,
  bandLine, bandVerdict, readTradeItem, itemLabel, sideValue, statusLabel,
  statusNote, readTradeOffer, readMine, effectiveCooldownLeft, heldDinoIds, vaultTradeOption,
  vaultTradeOptions, offerEmptyState, tradeIdsOrError, parseWantIds,
  offerBlockReason, escrowNotice, cooldownNotice, moveCooldownNotice,
  reservedSlotsNotice, cooldownBanner, offerConfirm, acceptConfirm, closeConfirm,
  expiryState, actionState, networkRefusal,
} from "@/lib/tradeRules";

// A config with every rule present, shaped exactly as GET /api/trade/config
// answers it under the shipped defaults. Tests that care about a rule being
// ABSENT delete it from a copy — they never hand in a different literal.
const FULL = Object.freeze({
  enabled: true,
  max_items_per_side: 3,
  symmetry_pct: 25,
  max_open_offers: 5,
  growth_gate: true,
  min_growth_pct: 80,
  coins_allowed: false,
  cooldown_secs: 86400,
  offer_ttl_secs: 172800,
  dino_move_cooldown_secs: 86400,
  my_cooldown_until: null,
  my_cooldown_left: 0,
});
const cfgFull = () => readTradeConfig(FULL);
const cfgWith = (over) => readTradeConfig({ ...FULL, ...over });

/* ══════════════════════════ waitEs — the _wait_es twin ══════════════════════════ */

describe("waitEs mirrors server.py _wait_es exactly", () => {
  test.each([
    [86400, "24 h"],
    [172800, "48 h"],
    [604800, "168 h"],
    [3600, "1 h"],
    [5400, "1 h 30 min"],
    [3661, "1 h 1 min"],
    [3599, "59 min"],
    [60, "1 min"],
    [59, "59 s"],
    [0, "0 s"],
  ])("%i seconds -> %s", (secs, want) => {
    expect(waitEs(secs)).toBe(want);
  });

  test("an hour with no leftover minutes never prints ' 0 min'", () => {
    expect(waitEs(7200)).toBe("2 h");
    expect(waitEs(7259)).toBe("2 h");        // 59 leftover SECONDS, 0 minutes
  });

  test("negative clamps to zero, like max(0, int(secs))", () => {
    expect(waitEs(-5)).toBe("0 s");
  });

  test("truncates rather than rounds, like int()", () => {
    expect(waitEs(119.9)).toBe("1 min");
  });

  test("unreadable input answers null so the caller OMITS the line", () => {
    expect(waitEs(null)).toBeNull();
    expect(waitEs(undefined)).toBeNull();
    expect(waitEs("mañana")).toBeNull();
    expect(waitEs(NaN)).toBeNull();
    expect(waitEs(Infinity)).toBeNull();
  });
});

describe("pluralEs", () => {
  test("agrees in number", () => {
    expect(pluralEs(1, "espacio", "espacios")).toBe("1 espacio");
    expect(pluralEs(2, "espacio", "espacios")).toBe("2 espacios");
    expect(pluralEs(0, "espacio", "espacios")).toBe("0 espacios");
  });
  test("unreadable answers null", () => {
    expect(pluralEs(null, "a", "b")).toBeNull();
    expect(pluralEs("dos", "a", "b")).toBeNull();
  });
});

/* ══════════════════════════ the value band ══════════════════════════ */

describe("symmetryOk is the exact integer twin of _trade_symmetry_ok", () => {
  // The server's own docstring example. The edge belongs to the player.
  test("6.000.000 against 8.000.000 at 25% TRADES (600.000.000 >= 600.000.000)", () => {
    expect(symmetryOk(6000000, 8000000, 25)).toBe(true);
  });
  test("5.999.999 against 8.000.000 at 25% does NOT", () => {
    expect(symmetryOk(5999999, 8000000, 25)).toBe(false);
  });
  test("the comparison is symmetric in its two sides", () => {
    expect(symmetryOk(8000000, 6000000, 25)).toBe(true);
    expect(symmetryOk(8000000, 5999999, 25)).toBe(false);
  });
  test("0% means the two sides must be worth exactly the same", () => {
    expect(symmetryOk(500, 500, 0)).toBe(true);
    expect(symmetryOk(500, 499, 0)).toBe(false);
  });
  test("100% turns the band off", () => {
    expect(symmetryOk(1, 999999999, 100)).toBe(true);
  });
  test("both sides worth nothing is the server's early true", () => {
    expect(symmetryOk(0, 0, 25)).toBe(true);
  });
  test("the `hi <= 0` early-out is the server's, not an accident of the arithmetic", () => {
    // Python: min(-5, 0) = -5, max(-5, 0) = 0, `if hi <= 0: return True`.
    // Without that early-out the inequality would answer -500 >= 0 -> false.
    expect(symmetryOk(-5, 0, 25)).toBe(true);
    expect(symmetryOk(0, -5, 25)).toBe(true);
  });
  test("one side worth nothing fails any band under 100%", () => {
    expect(symmetryOk(0, 1000, 25)).toBe(false);
  });
  test("unanswerable input is null, NEVER false — a band the page cannot compute must not condemn a trade", () => {
    expect(symmetryOk(null, 100, 25)).toBeNull();
    expect(symmetryOk(100, 100, null)).toBeNull();
    expect(symmetryOk(100, 100, 101)).toBeNull();
    expect(symmetryOk(100, 100, -1)).toBeNull();
    expect(symmetryOk(1.5, 100, 25)).toBeNull();
    expect(symmetryOk(Number.MAX_SAFE_INTEGER, 100, 25)).toBeNull();
  });
});

describe("bandRange agrees with symmetryOk on every edge", () => {
  test("25% of 6.000.000 is 4.500.000 .. 8.000.000", () => {
    expect(bandRange(6000000, 25)).toEqual({ min: 4500000, max: 8000000 });
  });
  test("every boundary it publishes is one symmetryOk actually accepts", () => {
    for (const [value, pct] of [[6000000, 25], [8000000, 25], [300000, 10], [1234567, 37], [999, 1]]) {
      const r = bandRange(value, pct);
      expect(symmetryOk(value, r.min, pct)).toBe(true);
      expect(symmetryOk(value, r.max, pct)).toBe(true);
      // ...and one step outside is refused, which is what makes it a BAND
      // rather than a suggestion.
      expect(symmetryOk(value, r.min - 1, pct)).toBe(false);
      expect(symmetryOk(value, r.max + 1, pct)).toBe(false);
    }
  });
  test("0% collapses the window to the value itself", () => {
    expect(bandRange(5000, 0)).toEqual({ min: 5000, max: 5000 });
  });
  test("100% has no upper bound", () => {
    expect(bandRange(5000, 100)).toEqual({ min: 0, max: null });
  });
  test("unanswerable input is null", () => {
    expect(bandRange(null, 25)).toBeNull();
    expect(bandRange(5000, null)).toBeNull();
    expect(bandRange(-1, 25)).toBeNull();
    expect(bandRange(5000, 101)).toBeNull();
  });
});

describe("bandLine quotes the band in exact numbers, or not at all", () => {
  test("names both ends and the percentage", () => {
    const s = bandLine(6000000, 25);
    expect(s).toContain("4.500.000");
    expect(s).toContain("8.000.000");
    expect(s).toContain("25%");
  });
  test("0% says the two sides must be equal", () => {
    expect(bandLine(5000, 0)).toContain("exactamente lo mismo");
  });
  test("100% says there is no limit", () => {
    expect(bandLine(5000, 100)).toContain("no hay límite");
  });
  test("with no percentage published it renders NOTHING rather than a guess", () => {
    expect(bandLine(6000000, null)).toBeNull();
    expect(bandLine(null, 25)).toBeNull();
  });
});

describe("bandVerdict only judges an offer whose BOTH sides it was given", () => {
  test("inside the band", () => {
    expect(bandVerdict(6000000, 8000000, 25)).toEqual({ ok: true, text: expect.stringContaining("25%") });
  });
  test("outside the band names both numbers", () => {
    const v = bandVerdict(300000, 6300000, 25);
    expect(v.ok).toBe(false);
    expect(v.text).toContain("300.000");
    expect(v.text).toContain("6.300.000");
  });
  test("a missing side renders no verdict at all", () => {
    expect(bandVerdict(6000000, null, 25)).toBeNull();
    expect(bandVerdict(6000000, 8000000, null)).toBeNull();
  });
});

/* ══════════════════════════ reading the config ══════════════════════════ */

describe("readTradeConfig", () => {
  test("reads every rule off the payload", () => {
    const c = cfgFull();
    expect(c.maxItemsPerSide).toBe(3);
    expect(c.symmetryPct).toBe(25);
    expect(c.maxOpenOffers).toBe(5);
    expect(c.minGrowthPct).toBe(80);
    expect(c.cooldownSecs).toBe(86400);
    expect(c.offerTtlSecs).toBe(172800);
    expect(c.moveCooldownSecs).toBe(86400);
    expect(c.growthGate).toBe(true);
    expect(c.ok).toBe(true);
  });

  test("a null knob carries the server's own error sentence beside it", () => {
    const c = readTradeConfig({
      ...FULL, cooldown_secs: null,
      cooldown_secs_error: "La espera entre intercambios está mal configurada",
    });
    expect(c.cooldownSecs).toBeNull();
    expect(c.cooldownError).toBe("La espera entre intercambios está mal configurada");
  });

  test("COINS ARE PINNED FALSE and are not read from the payload", () => {
    // There is no coins field on TradeOfferInput, so a payload claiming
    // otherwise must not make the page grow an input the API cannot accept.
    expect(readTradeConfig({ ...FULL, coins_allowed: true }).coinsAllowed).toBe(false);
    expect(cfgFull().coinsAllowed).toBe(false);
  });

  test("a missing `enabled` flag fails OPEN; only an explicit false disables", () => {
    expect(readTradeConfig({}).enabled).toBe(true);
    expect(readTradeConfig({ enabled: false }).enabled).toBe(false);
    expect(readTradeConfig({ enabled: 0 }).enabled).toBe(true);
  });

  test("growth_gate is a SERVER BOOL and is never truthy-coerced", () => {
    // _knob_bool answers a real bool. A 1 or a "yes" is a payload this page does
    // not understand, and the gate's documented degrade is to fail OPEN.
    expect(readTradeConfig({ ...FULL, growth_gate: 1 }).growthGate).toBe(false);
    expect(readTradeConfig({ ...FULL, growth_gate: "yes" }).growthGate).toBe(false);
    expect(readTradeConfig({ ...FULL, growth_gate: true }).growthGate).toBe(true);
  });

  test("garbage in is nulls out, never invented numbers", () => {
    const c = readTradeConfig({ max_items_per_side: "tres", symmetry_pct: 1.5, cooldown_secs: true });
    expect(c.maxItemsPerSide).toBeNull();
    expect(c.symmetryPct).toBeNull();
    expect(c.cooldownSecs).toBeNull();
  });

  test("my_cooldown_left is clamped at zero at the point it is READ", () => {
    // Clamping only at the point of USE would leave a negative in the normalised
    // config for the next consumer to trip over.
    expect(readTradeConfig({ ...FULL, my_cooldown_left: -5 }).myCooldownLeft).toBe(0);
    expect(readTradeConfig({ ...FULL, my_cooldown_left: "pronto" }).myCooldownLeft).toBe(0);
    expect(readTradeConfig({ ...FULL, my_cooldown_left: 3600 }).myCooldownLeft).toBe(3600);
  });

  test("a non-object payload is not ok", () => {
    expect(readTradeConfig(null).ok).toBe(false);
    expect(readTradeConfig("nope").ok).toBe(false);
  });
});

describe("configBlockReason blocks the send in the server's own order", () => {
  test("a healthy config blocks nothing", () => {
    expect(configBlockReason(cfgFull())).toBeNull();
  });
  test("an unreadable payload says what to do next", () => {
    const r = configBlockReason(readTradeConfig(null));
    expect(r).toContain("Actualiza la página");
  });
  test("disabled uses the server's own 503 sentence", () => {
    expect(configBlockReason(cfgWith({ enabled: false })))
      .toBe("Los intercambios están desactivados por ahora.");
  });
  test("a broken cooldown knob surfaces the SERVER'S sentence, not ours", () => {
    const c = readTradeConfig({
      ...FULL, cooldown_secs: null,
      cooldown_secs_error: "La espera entre intercambios está mal configurada",
    });
    expect(configBlockReason(c)).toBe("La espera entre intercambios está mal configurada");
  });
  test("a broken TTL knob does too", () => {
    const c = readTradeConfig({
      ...FULL, offer_ttl_secs: null,
      offer_ttl_secs_error: "La caducidad de las ofertas está mal configurada",
    });
    expect(configBlockReason(c)).toBe("La caducidad de las ofertas está mal configurada");
  });
  test("disabled is checked BEFORE a knob error — the earlier refusal wins", () => {
    const c = readTradeConfig({
      ...FULL, enabled: false, cooldown_secs: null, cooldown_secs_error: "knob roto",
    });
    expect(configBlockReason(c)).toBe("Los intercambios están desactivados por ahora.");
  });
  test("a null knob with no error sentence still blocks", () => {
    expect(configBlockReason(cfgWith({ cooldown_secs: null }))).toContain("incompletas");
    expect(configBlockReason(cfgWith({ offer_ttl_secs: null }))).toContain("incompletas");
    expect(configBlockReason(cfgWith({ dino_move_cooldown_secs: null }))).toContain("incompletas");
  });
  test("a missing per-side cap or band blocks, because the page could not explain the rule first", () => {
    expect(configBlockReason(cfgWith({ max_items_per_side: null }))).toContain("límites");
    expect(configBlockReason(cfgWith({ symmetry_pct: null }))).toContain("límites");
  });
});

/* ══════════════════════════ offers and items ══════════════════════════ */

const ITEM = Object.freeze({
  dino_id: 41, slug: "rex", species: "Rex", name: "Titán",
  growth_pct: 100, growth_pct_exact: 100.0, mutations: 12, prime: true,
  value: 6300000, value_error: null,
});

describe("readTradeItem / itemLabel", () => {
  test("reads the published fields", () => {
    const i = readTradeItem(ITEM);
    expect(i).toMatchObject({ dinoId: 41, species: "Rex", name: "Titán", growthPct: 100, mutations: 12, prime: true, value: 6300000, valueError: null });
  });
  test("a pricing failure is kept, because it is why the whole offer is refused", () => {
    const i = readTradeItem({ ...ITEM, value: 0, value_error: "Falta el precio base" });
    expect(i.valueError).toBe("Falta el precio base");
  });
  test("labels species, custom name, growth, mutations and prime", () => {
    expect(itemLabel(readTradeItem(ITEM))).toBe("Rex «Titán» · 100% · 12 mutaciones · prime");
  });
  test("a custom name equal to the species is not repeated", () => {
    expect(itemLabel(readTradeItem({ ...ITEM, name: "Rex", prime: false, mutations: 1 })))
      .toBe("Rex · 100% · 1 mutación");
  });
  test("a nameless, growthless animal still renders something", () => {
    expect(itemLabel(readTradeItem({}))).toBe("Dinosaurio");
  });
  test("garbage in is not a crash", () => {
    expect(readTradeItem(null).dinoId).toBeNull();
    expect(readTradeItem("x").species).toBe("");
  });
});

describe("sideValue", () => {
  test("sums the priced animals", () => {
    const v = sideValue([ITEM, { ...ITEM, dino_id: 42, value: 700000 }]);
    expect(v.total).toBe(7000000);
    expect(v.missing).toBe(0);
  });
  test("ONE unpriced animal makes the whole total unknown — half a total is a wrong total", () => {
    const v = sideValue([ITEM, { ...ITEM, dino_id: 42, value: 0, value_error: "roto" }]);
    expect(v.total).toBeNull();
    expect(v.missing).toBe(1);
  });
  test("an empty side is worth nothing, not unknown", () => {
    expect(sideValue([]).total).toBe(0);
    expect(sideValue(null).total).toBe(0);
  });
  test("negative published values never subtract, matching max(0, int(...))", () => {
    expect(sideValue([{ ...ITEM, value: -500 }]).total).toBe(0);
  });
});

describe("readTradeOffer", () => {
  const RAW = {
    id: "abc", status: "pending", from_id: "u1", to_id: "u2",
    from_name: "Ana", to_name: "Beto", note: "hola",
    created_at: "2026-08-11T10:00:00Z", expires_at: "2026-08-13T10:00:00Z",
    offer_items: [ITEM], want_items: [{ ...ITEM, dino_id: 9, value: 6000000 }],
    offer_value: 6300000, want_value: 6000000, symmetry_pct: 25,
    direction: "incoming", can_accept: true, can_cancel: false,
  };
  test("normalises both sides and the viewer's permissions", () => {
    const o = readTradeOffer(RAW);
    expect(o.offerItems).toHaveLength(1);
    expect(o.wantItems[0].dinoId).toBe(9);
    expect(o.canAccept).toBe(true);
    expect(o.canCancel).toBe(false);
    expect(o.direction).toBe("incoming");
  });
  test("permissions come from the SERVER and are never truthy-coerced", () => {
    expect(readTradeOffer({ ...RAW, can_accept: "yes" }).canAccept).toBe(false);
    expect(readTradeOffer({ ...RAW, can_accept: 1 }).canAccept).toBe(false);
  });
  test("a missing persona name renders a placeholder, never the raw user id", () => {
    const o = readTradeOffer({ ...RAW, from_name: null });
    expect(o.fromName).toBe("Jugador");
    expect(o.fromName).not.toContain("u1");
  });
  test("an unknown direction is 'other', never guessed from ids", () => {
    expect(readTradeOffer({ ...RAW, direction: "weird" }).direction).toBe("other");
  });
  test("garbage in is not a crash", () => {
    const o = readTradeOffer(null);
    expect(o.offerItems).toEqual([]);
    expect(o.canAccept).toBe(false);
  });
});

describe("readMine", () => {
  test("reads the three lists and the three numbers", () => {
    const m = readMine({
      incoming: [{ id: "a" }], outgoing: [], history: [{ id: "b" }],
      cooldown_left: 3600, slots_free: 2, reserved_slots: 3,
    });
    expect(m.incoming).toHaveLength(1);
    expect(m.cooldownLeft).toBe(3600);
    expect(m.slotsFree).toBe(2);
    expect(m.reservedSlots).toBe(3);
    expect(m.ok).toBe(true);
  });
  test("a first-run player with nothing at all renders as empty, not as broken", () => {
    const m = readMine({ incoming: [], outgoing: [], history: [], cooldown_left: 0, slots_free: 5, reserved_slots: 0 });
    expect(m.incoming).toEqual([]);
    expect(m.cooldownLeft).toBe(0);
    expect(m.reservedSlots).toBe(0);
  });
  test("a failed read degrades to empty lists rather than throwing", () => {
    const m = readMine(null);
    expect(m.ok).toBe(false);
    expect(m.incoming).toEqual([]);
    expect(m.outgoing).toEqual([]);
    expect(m.history).toEqual([]);
  });
  test("negative or junk numbers clamp at zero", () => {
    const m = readMine({ cooldown_left: -9, slots_free: "x", reserved_slots: null });
    expect(m.cooldownLeft).toBe(0);
    expect(m.slotsFree).toBe(0);
    expect(m.reservedSlots).toBe(0);
  });
});

describe("effectiveCooldownLeft picks WHICH reading of the clock to believe", () => {
  test("a successful /trade/mine wins — it is the POLLED reader", () => {
    expect(effectiveCooldownLeft(readMine({ cooldown_left: 60 }), cfgWith({ my_cooldown_left: 3600 }))).toBe(60);
    expect(effectiveCooldownLeft(readMine({ cooldown_left: 3600 }), cfgWith({ my_cooldown_left: 60 }))).toBe(3600);
  });
  test("A FINISHED COOLDOWN IS NOT HELD UP BY THE CONFIG'S LOAD-TIME COPY", () => {
    // The config is fetched once. Maxing the two would keep the banner and the
    // dead «Nueva oferta» button on screen for the rest of the session, long
    // after the server had let this player trade again.
    expect(effectiveCooldownLeft(readMine({ cooldown_left: 0 }), cfgWith({ my_cooldown_left: 86400 }))).toBe(0);
  });
  test("a FAILED /trade/mine cannot hide a cooldown /trade/config reported", () => {
    // This is the gap: readMine(null) degrades cooldownLeft to 0, and without
    // the config's copy the page would show no banner and walk the player into
    // a 429 on the very next click.
    expect(effectiveCooldownLeft(readMine(null), cfgWith({ my_cooldown_left: 7200 }))).toBe(7200);
  });
  test("a FAILED /trade/config cannot hide one /trade/mine reported", () => {
    expect(effectiveCooldownLeft(readMine({ cooldown_left: 7200 }), readTradeConfig(null))).toBe(7200);
  });
  test("no cooldown anywhere is zero", () => {
    expect(effectiveCooldownLeft(readMine({ cooldown_left: 0 }), cfgFull())).toBe(0);
    expect(effectiveCooldownLeft(null, null)).toBe(0);
  });
  test("a negative or junk reading never becomes a live cooldown", () => {
    expect(effectiveCooldownLeft(readMine({ cooldown_left: -99 }), cfgWith({ my_cooldown_left: -5 }))).toBe(0);
    expect(effectiveCooldownLeft({ cooldownLeft: "pronto" }, { myCooldownLeft: "luego" })).toBe(0);
  });
  test("it clamps on its OWN, not only on what the readers already clamped", () => {
    // Handed un-normalised objects — which any caller may do, since this takes
    // plain shapes — it must still never answer a negative. A negative "left"
    // renders as a cooldown that is simultaneously running and finished.
    expect(effectiveCooldownLeft({ cooldownLeft: -99 }, { myCooldownLeft: -5 })).toBe(0);
    expect(effectiveCooldownLeft({ cooldownLeft: -1 }, {})).toBe(0);
    // ...including down the TRUSTED branch, which returns its reading directly
    // and so has no outer Math.max left to catch a negative for it.
    expect(effectiveCooldownLeft({ ok: true, cooldownLeft: -99 }, {})).toBe(0);
    expect(effectiveCooldownLeft({ ok: true, cooldownLeft: -1 }, { myCooldownLeft: 60 })).toBe(0);
  });
  test("the send is blocked off the COMBINED clock, not off /trade/mine alone", () => {
    const r = offerBlockReason({
      cfg: cfgWith({ my_cooldown_left: 3600 }),
      mine: readMine(null),
      partner: { id: "u2", linked: true },
      offerIds: [1], wantIds: [2],
    });
    expect(r).toContain("te faltan 1 h");
  });
});

describe("statusLabel / statusNote", () => {
  test("every status the server can write has a Spanish label", () => {
    for (const s of ["pending", "settling", "restore_pending", "accepted",
      "declined", "cancelled", "expired", "needs_admin"]) {
      expect(statusLabel(s)).not.toBe("Desconocido");
    }
  });
  test("an unknown status does not render a raw key at a player", () => {
    expect(statusLabel("brand_new_state")).toBe("Desconocido");
    expect(statusLabel(null)).toBe("Desconocido");
  });
  test("the three in-flight states tell the player what to DO", () => {
    expect(statusNote({ status: "settling" })).toContain("Actualiza");
    expect(statusNote({ status: "restore_pending" })).toContain("libera un espacio");
    expect(statusNote({ status: "needs_admin" })).toContain("administrador");
  });
  test("needs_admin tells them NOT to retry — a retry there costs an animal", () => {
    expect(statusNote({ status: "needs_admin" })).toContain("no vuelvas a intentarlo");
  });
  test("a settled status has no instruction", () => {
    expect(statusNote({ status: "accepted" })).toBeNull();
  });
});

/* ══════════════════════════ my animals ══════════════════════════ */

const VROW = Object.freeze({
  id: 41, species: "Rex", custom_name: "Titán", growth_pct: 100,
  mutations_count: 12, is_prime: true, redeem_pending: false,
});

describe("heldDinoIds finds MY animals an incoming offer already claimed", () => {
  test("collects the want side of every incoming offer", () => {
    const mine = readMine({
      incoming: [{ want_items: [{ dino_id: 41 }, { dino_id: 7 }] }],
      outgoing: [], history: [],
    });
    const held = heldDinoIds(mine);
    expect(held.has(41)).toBe(true);
    expect(held.has(7)).toBe(true);
  });
  test("an OUTGOING offer's items are not held — escrow already removed them from the vault", () => {
    const mine = readMine({ incoming: [], outgoing: [{ offer_items: [{ dino_id: 99 }] }], history: [] });
    expect(heldDinoIds(mine).has(99)).toBe(false);
  });
  test("nothing incoming is an empty set, not a crash", () => {
    expect(heldDinoIds(readMine(null)).size).toBe(0);
    expect(heldDinoIds(null).size).toBe(0);
  });
});

describe("vaultTradeOption applies the SERVER'S gates in the SERVER'S order", () => {
  const cfg = cfgFull();
  test("an adult, unclaimed animal is offerable", () => {
    const o = vaultTradeOption(VROW, cfg, new Set());
    expect(o.eligible).toBe(true);
    expect(o.blockReason).toBeNull();
    expect(o.label).toBe("Rex «Titán» · 100% · 12 mutaciones · prime");
  });
  test("a redeem in progress blocks BEFORE the growth gate — the server checks it first", () => {
    const o = vaultTradeOption({ ...VROW, redeem_pending: true, growth_pct: 10 }, cfg, new Set());
    expect(o.eligible).toBe(false);
    expect(o.blockReason).toContain("recuperación en progreso");
  });
  test("under the threshold names the exact threshold", () => {
    const o = vaultTradeOption({ ...VROW, growth_pct: 74 }, cfg, new Set());
    expect(o.eligible).toBe(false);
    expect(o.blockReason).toBe("no se puede intercambiar (mínimo 80%)");
  });
  test("AT the threshold is offerable — the boundary belongs to the player", () => {
    expect(vaultTradeOption({ ...VROW, growth_pct: 80 }, cfg, new Set()).eligible).toBe(true);
  });
  test("unreadable growth is REFUSED, matching _growth_gate_ok(None) === False", () => {
    const o = vaultTradeOption({ ...VROW, growth_pct: null }, cfg, new Set());
    expect(o.eligible).toBe(false);
    expect(o.blockReason).toContain("crecimiento");
  });
  test("with the growth gate OFF, a hatchling is offerable", () => {
    const o = vaultTradeOption({ ...VROW, growth_pct: 5 }, cfgWith({ growth_gate: false }), new Set());
    expect(o.eligible).toBe(true);
  });
  test("with NO threshold published the gate blocks nobody — it fails OPEN on the client", () => {
    const o = vaultTradeOption({ ...VROW, growth_pct: 5 }, cfgWith({ min_growth_pct: null }), new Set());
    expect(o.eligible).toBe(true);
  });
  test("an animal an incoming offer already named is blocked with a reason, not a 409", () => {
    const o = vaultTradeOption(VROW, cfg, new Set([41]));
    expect(o.eligible).toBe(false);
    expect(o.blockReason).toContain("ya está comprometido");
  });
  test("the growth gate is checked BEFORE the claim, matching _trade_rows_or_404", () => {
    const o = vaultTradeOption({ ...VROW, growth_pct: 74 }, cfg, new Set([41]));
    expect(o.blockReason).toContain("mínimo 80%");
  });
  test("an unreadable row id cannot be offered at all", () => {
    const o = vaultTradeOption({ ...VROW, id: null }, cfg, new Set());
    expect(o.eligible).toBe(false);
    expect(o.blockReason).toContain("número");
  });
  test("vaultTradeOptions maps a list and survives junk", () => {
    expect(vaultTradeOptions([VROW, null], cfg, new Set())).toHaveLength(2);
    expect(vaultTradeOptions(null, cfg, new Set())).toEqual([]);
  });
});

describe("offerEmptyState distinguishes the reasons nothing can be offered", () => {
  const cfg = cfgFull();
  test("an EMPTY vault is a different fact from a blocked one, and says so", () => {
    const e = offerEmptyState([], cfg);
    expect(e.headline).toContain("Todavía no tienes dinosaurios");
    expect(e.body).toContain("La Bóveda");
  });
  test("something offerable means no empty state at all", () => {
    expect(offerEmptyState(vaultTradeOptions([VROW], cfg, new Set()), cfg)).toBeNull();
  });
  test("everything already claimed says exactly that, and how to free them", () => {
    const opts = vaultTradeOptions([VROW], cfg, new Set([41]));
    const e = offerEmptyState(opts, cfg);
    expect(e.headline).toContain("comprometidos");
    expect(e.body).toContain("Rechaza");
  });
  test("all under the gate names the threshold and how far the biggest is short", () => {
    const opts = vaultTradeOptions([{ ...VROW, growth_pct: 74 }], cfg, new Set());
    const e = offerEmptyState(opts, cfg);
    expect(e.headline).toContain("80%");
    expect(e.biggest).toContain("le faltan 6 puntos");
  });
  test("one point short says «le falta 1 punto», not «le faltan 1 puntos»", () => {
    const opts = vaultTradeOptions([{ ...VROW, growth_pct: 79 }], cfg, new Set());
    expect(offerEmptyState(opts, cfg).biggest).toContain("le falta 1 punto");
  });
  test("with no threshold published it states the rule WITHOUT inventing a number", () => {
    const c = cfgWith({ min_growth_pct: null });
    const opts = [{ id: 1, eligible: false, blockReason: "x", growthPct: 10, species: "Rex", name: "" }];
    const e = offerEmptyState(opts, c);
    expect(e.headline).not.toMatch(/\d/);
    // ...and no `null%` either — a missing number that reaches a template
    // renders as the word "null", which has no digits and would slip past the
    // check above while promising a threshold nobody set.
    expect(e.headline).not.toContain("null");
    expect(e.headline).not.toContain("%");
    expect(e.biggest).toBeNull();
  });
  test("with the growth gate OFF the headline promises no threshold either", () => {
    const c = cfgWith({ growth_gate: false });
    const opts = [{ id: 1, eligible: false, blockReason: "x", growthPct: 10, species: "Rex", name: "" }];
    expect(offerEmptyState(opts, c).headline).not.toContain("%");
  });
});

/* ══════════════════════════ the two id lists ══════════════════════════ */

describe("tradeIdsOrError mirrors _trade_ids_or_400 sentence for sentence", () => {
  test("an empty side asks for at least one, using the side's own word", () => {
    expect(tradeIdsOrError([], "tuyo", 3).error).toBe("Elige al menos un dinosaurio tuyo.");
    expect(tradeIdsOrError(null, "suyo", 3).error).toBe("Elige al menos un dinosaurio suyo.");
  });
  test("over the cap quotes the cap", () => {
    expect(tradeIdsOrError([1, 2, 3, 4], "tuyo", 3).error).toBe("Como máximo 3 dinosaurio(s) por lado.");
  });
  test("AT the cap is allowed", () => {
    expect(tradeIdsOrError([1, 2, 3], "tuyo", 3).ids).toEqual([1, 2, 3]);
  });
  test("a boolean is NEVER a dino id — the server's isinstance(v, bool) guard", () => {
    expect(tradeIdsOrError([true], "tuyo", 3).error).toBe("Esa lista de dinosaurios no es válida.");
  });
  test("a decimal and a string are refused too", () => {
    expect(tradeIdsOrError([1.5], "tuyo", 3).error).toBe("Esa lista de dinosaurios no es válida.");
    expect(tradeIdsOrError(["5"], "tuyo", 3).error).toBe("Esa lista de dinosaurios no es válida.");
  });
  test("a repeat inside one side is refused with the server's wording", () => {
    expect(tradeIdsOrError([7, 7], "tuyo", 3).error)
      .toBe("Repetiste el mismo dinosaurio en un lado del intercambio.");
  });
  test("with no cap published it refuses nothing on length", () => {
    expect(tradeIdsOrError([1, 2, 3, 4, 5, 6], "tuyo", null).ids).toHaveLength(6);
  });
});

describe("parseWantIds turns what the player typed into the server's own refusals", () => {
  test("commas, spaces and newlines all separate", () => {
    expect(parseWantIds("12, 34\n56", 3).ids).toEqual([12, 34, 56]);
  });
  test("an empty box asks for at least one of THEIRS", () => {
    expect(parseWantIds("", 3).error).toBe("Elige al menos un dinosaurio suyo.");
    expect(parseWantIds("   ", 3).error).toBe("Elige al menos un dinosaurio suyo.");
  });
  test("anything that is not a whole number is refused", () => {
    for (const bad of ["1.0", "1e3", "0x10", "-4", "abc", "12a"]) {
      expect(parseWantIds(bad, 3).error).toBe("Esa lista de dinosaurios no es válida.");
    }
  });
  test("zero is not a dino id", () => {
    expect(parseWantIds("0", 3).error).toBe("Esa lista de dinosaurios no es válida.");
  });
  test("a repeat is caught before it reaches the server", () => {
    expect(parseWantIds("7 7", 3).error).toBe("Repetiste el mismo dinosaurio en un lado del intercambio.");
  });
  test("over the cap quotes the cap the SERVER published", () => {
    expect(parseWantIds("1 2 3 4", 3).error).toBe("Como máximo 3 dinosaurio(s) por lado.");
    expect(parseWantIds("1 2 3 4", 5).ids).toEqual([1, 2, 3, 4]);
  });
  test("a non-string is not a crash", () => {
    expect(parseWantIds(null, 3).error).toBe("Elige al menos un dinosaurio suyo.");
  });
});

/* ══════════════════════════ what stops the send ══════════════════════════ */

describe("offerBlockReason checks what trade_create checks, in trade_create's order", () => {
  const partner = { id: "u2", name: "Beto", linked: true };
  const empty = readMine({ incoming: [], outgoing: [], history: [], cooldown_left: 0, slots_free: 5, reserved_slots: 0 });
  const good = { cfg: cfgFull(), mine: empty, partner, offerIds: [1], wantIds: [2] };

  test("a complete, legal offer is not blocked", () => {
    expect(offerBlockReason(good)).toBeNull();
  });
  test("a broken config wins over everything else", () => {
    expect(offerBlockReason({ ...good, cfg: cfgWith({ enabled: false }) }))
      .toBe("Los intercambios están desactivados por ahora.");
  });
  test("MY cooldown quotes both numbers, exactly as the 429 does", () => {
    const mine = readMine({ incoming: [], outgoing: [], history: [], cooldown_left: 3600 });
    const r = offerBlockReason({ ...good, mine });
    expect(r).toContain("cada 24 h");
    expect(r).toContain("te faltan 1 h");
  });
  test("a running cooldown with a BROKEN cooldown knob is caught by the config first", () => {
    // The knob is what the server reads to answer «how long» at all, so a null
    // there means every send is refused before the clock is even consulted.
    const mine = readMine({ incoming: [], outgoing: [], history: [], cooldown_left: 3600 });
    const r = offerBlockReason({ ...good, cfg: cfgWith({ cooldown_secs: null }), mine });
    expect(r).toContain("incompletas");
  });
  test("with the cooldown turned OFF (0) a stale cooldown_left promises no number", () => {
    const mine = readMine({ incoming: [], outgoing: [], history: [], cooldown_left: 3600 });
    const r = offerBlockReason({ ...good, cfg: cfgWith({ cooldown_secs: 0 }), mine });
    expect(r).toBe("Ya intercambiaste hace poco. Espera a que termine tu tiempo de espera.");
    expect(r).not.toContain("0 s");
  });
  test("no partner chosen yet asks for one", () => {
    expect(offerBlockReason({ ...good, partner: null })).toContain("Busca al jugador");
  });
  test("an unlinked partner is refused with the server's own 409", () => {
    expect(offerBlockReason({ ...good, partner: { id: "u2", linked: false } }))
      .toBe("Ese jugador todavía no vinculó su cuenta de Steam, así que no puede intercambiar.");
  });
  test("the open-offer cap quotes the cap the server published", () => {
    const mine = readMine({ incoming: [], outgoing: [{ id: "a" }, { id: "b" }], history: [] });
    expect(offerBlockReason({ ...good, cfg: cfgWith({ max_open_offers: 2 }), mine }))
      .toBe("Ya tienes 2 ofertas abiertas. Cancela una antes de enviar otra.");
  });
  test("under the cap does not block", () => {
    const mine = readMine({ incoming: [], outgoing: [{ id: "a" }], history: [] });
    expect(offerBlockReason({ ...good, cfg: cfgWith({ max_open_offers: 2 }), mine })).toBeNull();
  });
  test("N-FOR-N is refused with the server's own sentence, verbatim", () => {
    // The server quotes the OFFER count twice by construction — «es 2 por 2» —
    // and this mirror must not quietly "improve" it, or the client refusal and
    // the 400 stop reading the same.
    expect(offerBlockReason({ ...good, offerIds: [1, 2], wantIds: [3] }))
      .toBe("Un intercambio es 2 por 2: ofreces 2 y pides 1.");
    expect(offerBlockReason({ ...good, offerIds: [1], wantIds: [3, 4, 5] }))
      .toBe("Un intercambio es 1 por 1: ofreces 1 y pides 3.");
  });
  test("equal counts on both sides do NOT trip the N-for-N refusal", () => {
    expect(offerBlockReason({ ...good, offerIds: [1, 2], wantIds: [3, 4] })).toBeNull();
  });
  test("nothing picked on my side is caught before the want side", () => {
    expect(offerBlockReason({ ...good, offerIds: [], wantIds: [3] }))
      .toBe("Elige al menos un dinosaurio tuyo.");
  });
  test("a want side that would not parse blocks too", () => {
    expect(offerBlockReason({ ...good, wantIds: null })).toBe("Elige al menos un dinosaurio suyo.");
  });
  test("called with nothing at all it does not throw", () => {
    expect(typeof offerBlockReason()).toBe("string");
  });
});

/* ══════════════ the three surprising rules, said before the click ══════════════ */

describe("RULE 1 — escrow is OFFER-SIDE ONLY, and it happens on SEND", () => {
  test("says the offered animals leave the vault at that moment", () => {
    const s = escrowNotice(cfgFull());
    expect(s).toContain("salen de tu bóveda en ese momento");
  });
  test("says the ASKED-FOR animals are NOT frozen", () => {
    expect(escrowNotice(cfgFull())).toContain("NO se congelan");
  });
  test("and never ALSO claims they are frozen — the notice must not contradict itself", () => {
    // Asserting the positive alone is not enough: a sentence appended after it
    // leaves «NO se congelan» intact while telling the player the opposite.
    expect(escrowNotice(cfgFull())).not.toMatch(/quedan congelados/);
    expect(escrowNotice(cfgFull()).match(/congela/g)).toHaveLength(1);
  });
  test("quotes the TTL the server published", () => {
    expect(escrowNotice(cfgFull())).toContain("48 h");
  });
  test("with no TTL published it still states the rule, without a number", () => {
    const s = escrowNotice(cfgWith({ offer_ttl_secs: null }));
    expect(s).toContain("caduca sola");
    expect(s).not.toContain("48");
  });
});

describe("RULE 2 — BOTH sides burn the cooldown, and ACCEPTING is what spends it", () => {
  test("names the accepter's own cost, not just the sender's", () => {
    const s = cooldownNotice(cfgFull(), "Beto");
    expect(s).toContain("gasta TU intercambio del día");
    expect(s).toContain("no solo el de Beto");
  });
  test("says both sides wait, and for how long — the server's own 24 h", () => {
    expect(cooldownNotice(cfgFull(), "Beto")).toContain("los dos quedan en espera 24 h");
  });
  test("distinguishes SENDING (free) from ACCEPTING (spends it)", () => {
    const s = cooldownNotice(cfgFull(), "Beto");
    expect(s).toContain("Enviar una oferta no lo gasta");
    // The second half is the half that answers «then when?». Without it the
    // sentence says a cost exists and never says who pays it or when.
    expect(s).toContain("se gasta cuando alguien acepta");
  });
  test("a different server number produces a different sentence — nothing is pinned", () => {
    expect(cooldownNotice(cfgWith({ cooldown_secs: 3600 }), "Beto")).toContain("1 h");
    expect(cooldownNotice(cfgWith({ cooldown_secs: 3600 }), "Beto")).not.toContain("24 h");
  });
  test("with the cooldown disabled (0) there is NO cooldown promise at all", () => {
    expect(cooldownNotice(cfgWith({ cooldown_secs: 0 }), "Beto")).toBeNull();
  });
  test("with no cooldown published it says nothing rather than guessing", () => {
    expect(cooldownNotice(cfgWith({ cooldown_secs: null }), "Beto")).toBeNull();
  });
  test("a missing partner name degrades to a phrase, never to an id", () => {
    // The fallback must not start with "el": the sentence reads "...no solo el de
    // {who}", and "de el" is not Spanish -- it contracts to "del". A neutral
    // fallback sidesteps the contraction instead of special-casing it.
    expect(cooldownNotice(cfgFull(), null)).toContain("no solo el de la otra persona");
    expect(cooldownNotice(cfgFull(), null)).not.toContain("de el ");
  });
});

describe("RULE 2b — the per-ANIMAL move clock a settled trade also stamps", () => {
  test("quotes the server's number", () => {
    expect(moveCooldownNotice(cfgFull())).toContain("24 h");
  });
  test("silent when it is off or unpublished", () => {
    expect(moveCooldownNotice(cfgWith({ dino_move_cooldown_secs: 0 }))).toBeNull();
    expect(moveCooldownNotice(cfgWith({ dino_move_cooldown_secs: null }))).toBeNull();
  });
});

describe("RULE 3 — escrowed animals still hold their vault slots", () => {
  test("names how many are reserved and why", () => {
    const s = reservedSlotsNotice(readMine({ reserved_slots: 2, slots_free: 3 }));
    expect(s).toContain("2 espacios");
    expect(s).toContain("siguen contando");
    expect(s).toContain("dónde volver");
  });
  test("agrees in number for a single reserved slot", () => {
    expect(reservedSlotsNotice(readMine({ reserved_slots: 1, slots_free: 1 }))).toContain("1 espacio ");
  });
  test("with NO free slots left it says what to do — this is the blocked restore", () => {
    const s = reservedSlotsNotice(readMine({ reserved_slots: 3, slots_free: 0 }));
    expect(s).toContain("No te queda ningún espacio libre");
    expect(s).toContain("cierra una oferta");
  });
  test("nothing reserved says nothing at all", () => {
    expect(reservedSlotsNotice(readMine({ reserved_slots: 0, slots_free: 5 }))).toBeNull();
    expect(reservedSlotsNotice(null)).toBeNull();
  });
});

describe("cooldownBanner", () => {
  test("quotes both the total and what is left", () => {
    const s = cooldownBanner(5400, cfgFull());
    expect(s).toContain("cada 24 h");
    expect(s).toContain("te faltan 1 h 30 min");
  });
  test("no cooldown running renders no banner", () => {
    expect(cooldownBanner(0, cfgFull())).toBeNull();
    expect(cooldownBanner(null, cfgFull())).toBeNull();
  });
  test("with no total published it still reports the wait", () => {
    const s = cooldownBanner(60, cfgWith({ cooldown_secs: null }));
    expect(s).toContain("te faltan 1 min");
  });
});

/* ══════════════════════════ the confirmation steps ══════════════════════════ */

describe("offerConfirm restates what leaves the vault and what the cooldown costs", () => {
  const items = [{ species: "Rex", name: "Titán", growthPct: 100, mutations: 12, prime: true }];
  const c = offerConfirm({ cfg: cfgFull(), items, partnerName: "Beto", wantCount: 1 });

  test("names the animals that leave RIGHT NOW", () => {
    expect(c.lines.join(" ")).toContain("Sale de tu bóveda AHORA: Rex «Titán»");
  });
  test("says the asked-for animals are not frozen", () => {
    expect(c.lines.join(" ")).toContain("NO se congelan");
  });
  test("quotes the TTL", () => {
    expect(c.lines.join(" ")).toContain("48 h");
  });
  test("says the slots stay reserved while the offer is open", () => {
    expect(c.lines.join(" ")).toContain("contando como ocupado");
  });
  test("says SENDING does not spend the day but ACCEPTING will, with the number", () => {
    const all = c.lines.join(" ");
    expect(all).toContain("Enviar no gasta tu intercambio del día");
    expect(all).toContain("los dos quedan en espera 24 h");
  });
  test("the warning banner is about the vault, because that is what is irreversible here", () => {
    expect(c.warning).toContain("SALEN DE LA BÓVEDA");
  });
  test("plurals agree for two animals", () => {
    const two = offerConfirm({
      cfg: cfgFull(),
      items: [{ species: "Rex" }, { species: "Deino" }],
      partnerName: "Beto", wantCount: 2,
    });
    expect(two.lines.join(" ")).toContain("Salen de tu bóveda AHORA");
    expect(two.lines.join(" ")).toContain("esos espacios");
    expect(two.lines.join(" ")).toContain("2 dinosaurios");
  });
  test("EVERY quoted number disappears when the server published none", () => {
    const bare = offerConfirm({
      cfg: readTradeConfig({}), items, partnerName: "Beto", wantCount: null,
    });
    const all = bare.lines.join(" ");
    expect(all).not.toContain("24 h");
    expect(all).not.toContain("48 h");
    // ...and the vault line, which needs no server number, survives.
    expect(all).toContain("Sale de tu bóveda AHORA");
  });
  test("called with nothing at all it still returns a usable shape", () => {
    const none = offerConfirm();
    expect(none.title).toContain("Enviar");
    expect(Array.isArray(none.lines)).toBe(true);
  });
});

describe("acceptConfirm makes the both-sides cooldown impossible to miss", () => {
  const offer = readTradeOffer({
    id: "x", status: "pending", from_name: "Beto",
    offer_items: [{ ...ITEM, name: "Titán" }],
    want_items: [{ ...ITEM, dino_id: 9, species: "Deino", name: "Kai", mutations: 3, prime: false }],
    can_accept: true,
  });
  const c = acceptConfirm({ cfg: cfgFull(), offer });

  test("names what LEAVES this player's vault", () => {
    expect(c.lines.join(" ")).toContain("Sale de tu bóveda: Deino «Kai»");
  });
  test("names what ARRIVES", () => {
    expect(c.lines.join(" ")).toContain("Recibes: Rex «Titán»");
  });
  test("says accepting costs the ACCEPTER their own day, and names the other player", () => {
    const all = c.lines.join(" ");
    expect(all).toContain("gasta TU intercambio del día");
    expect(all).toContain("no solo el de Beto");
    expect(all).toContain("los dos quedan en espera 24 h");
  });
  test("the warning banner carries the cooldown, not a generic «cannot be undone»", () => {
    expect(c.warning).toContain("24 h");
  });
  test("also names the per-animal move clock", () => {
    expect(c.lines.join(" ")).toContain("no se puede volver a mover en 24 h");
  });
  test("always says it cannot be undone", () => {
    expect(c.lines.join(" ")).toContain("no se puede deshacer");
  });
  test("with the cooldown disabled the warning does not promise one", () => {
    const off = acceptConfirm({ cfg: cfgWith({ cooldown_secs: 0 }), offer });
    expect(off.warning).not.toContain("24 h");
    expect(off.lines.join(" ")).not.toContain("los dos quedan en espera");
  });
  test("called with nothing at all it still returns a usable shape", () => {
    expect(acceptConfirm().title).toContain("Aceptar");
  });
});

describe("closeConfirm — cancel and decline move animals but cost nothing", () => {
  const offer = readTradeOffer({
    from_name: "Beto", offer_items: [{ ...ITEM, name: "Titán" }], want_items: [],
  });
  test("cancel says the offered animals come back to ME", () => {
    const c = closeConfirm({ offer, kind: "cancel" });
    expect(c.lines.join(" ")).toContain("Vuelve a tu bóveda: Rex «Titán»");
    expect(c.lines.join(" ")).toContain("No gastas tu intercambio del día");
  });
  test("decline says nothing of MINE moves", () => {
    const c = closeConfirm({ offer, kind: "decline" });
    expect(c.lines.join(" ")).toContain("Vuelve a la bóveda de Beto");
    expect(c.lines.join(" ")).toContain("Ninguno de tus dinosaurios se mueve");
  });
  test("neither carries a scary warning banner, because neither can lose anything", () => {
    expect(closeConfirm({ offer, kind: "cancel" }).warning).toBeNull();
    expect(closeConfirm({ offer, kind: "decline" }).warning).toBeNull();
  });
  test("called with nothing at all it still returns a usable shape", () => {
    expect(closeConfirm().title).toContain("Rechazar");
  });
});

/* ══════════════════════════ the TTL clock ══════════════════════════ */

describe("expiryState", () => {
  const T0 = Date.parse("2026-08-11T12:00:00Z");
  test("counts down while the offer lives", () => {
    const e = expiryState("2026-08-11T13:00:00Z", T0);
    expect(e.expired).toBe(false);
    expect(e.secondsLeft).toBe(3600);
    expect(e.text).toBe("Caduca en 1 h");
  });
  test("an offer that expired WHILE THE PLAYER LOOKED reads as caducada", () => {
    expect(expiryState("2026-08-11T11:59:59Z", T0)).toMatchObject({ expired: true, text: "Caducada" });
  });
  test("the expiry instant itself is expired", () => {
    expect(expiryState("2026-08-11T12:00:00Z", T0).expired).toBe(true);
  });
  test("an unreadable clock reads as EXPIRED, never as «NaNh»", () => {
    expect(expiryState("no soy una fecha", T0)).toMatchObject({ expired: true, text: "Caducada" });
    expect(expiryState(null, T0).expired).toBe(true);
    expect(expiryState(undefined, T0).expired).toBe(true);
  });
});

describe("actionState decides what a button may do", () => {
  const cfg = cfgFull();
  const mine = readMine({ cooldown_left: 0 });
  const pending = { status: "pending", canAccept: true };
  test("a live offer with no cooldown may be acted on", () => {
    expect(actionState(pending, { expired: false }, mine, cfg).canAct).toBe(true);
  });
  test("an offer that expired under the cursor cannot — pressing it would earn «ya expiró»", () => {
    const s = actionState(pending, { expired: true }, mine, cfg);
    expect(s.canAct).toBe(false);
    expect(s.reason).toContain("caducó");
  });
  test("a running cooldown blocks accepting and quotes both numbers", () => {
    const s = actionState(pending, { expired: false }, readMine({ cooldown_left: 3600 }), cfg);
    expect(s.canAct).toBe(false);
    expect(s.reason).toContain("te faltan 1 h");
  });
  test("a cooldown does NOT block an offer this viewer can only cancel", () => {
    const s = actionState({ status: "pending", canAccept: false, canCancel: true },
      { expired: false }, readMine({ cooldown_left: 3600 }), cfg);
    expect(s.canAct).toBe(true);
  });
  test("a non-pending offer explains its own state instead", () => {
    const s = actionState({ status: "needs_admin" }, { expired: false }, mine, cfg);
    expect(s.canAct).toBe(false);
    expect(s.reason).toContain("administrador");
  });
  test("called with nothing at all it does not throw", () => {
    expect(typeof actionState().canAct).toBe("boolean");
  });
});

/* ══════════════════════════ failed calls ══════════════════════════ */

describe("networkRefusal always says what to do next", () => {
  test("the SERVER'S own Spanish detail wins", () => {
    const err = { response: { status: 409, data: { detail: "Esa oferta ya expiró." } } };
    expect(networkRefusal(err, "algo")).toBe("Esa oferta ya expiró.");
  });
  test("NO response at all tells the player to LOOK, not to press again", () => {
    const r = networkRefusal({ message: "timeout of 30000ms exceeded" }, "algo");
    expect(r).toContain("actualiza la página");
    expect(r).not.toContain("vuelve a pulsar");
  });
  test("a 401 sends them back to Steam", () => {
    expect(networkRefusal({ response: { status: 401, data: {} } })).toContain("Steam");
  });
  test("a 404 says it is gone", () => {
    expect(networkRefusal({ response: { status: 404, data: {} } })).toContain("Actualiza la página");
  });
  test("a 500 does not blame the player", () => {
    expect(networkRefusal({ response: { status: 500, data: {} } })).toContain("El servidor");
  });
  test("a non-string detail (a 422 list) falls back rather than rendering [object Object]", () => {
    const err = { response: { status: 422, data: { detail: [{ msg: "bad" }] } } };
    const r = networkRefusal(err, "No se pudo enviar la oferta.");
    expect(r).toBe("No se pudo enviar la oferta.");
    expect(r).not.toContain("object");
  });
  test("no error at all is a success and returns the fallback", () => {
    expect(networkRefusal(null, "listo")).toBe("listo");
  });
  test("with no fallback given there is still a sentence", () => {
    expect(networkRefusal({ response: { status: 418, data: {} } })).toContain("Vuelve a intentarlo");
  });
});

/* ══════════════════ THE SOURCE PIN — no rule may be typed ══════════════════ */

// The page this wave replaced carried a hardcoded fee that silently drifted from
// the server's. These two files must never grow the trade lane's equivalent.
describe("no server-owned rule is pinned in the source", () => {
  const SRC = path.join(__dirname, "tradeRules.js");
  // The trade surfaces, after the 2026-08-11 redesign moved trading onto the
  // Mercado: the rules module, the board module, and the two components that
  // render them. @/pages/Trades is GONE — a pin that names a deleted file
  // passes by accident, so this list is the live one.
  const BOARD = path.join(__dirname, "tradeBoard.js");
  const PANEL = path.join(__dirname, "..", "components", "market", "TradeOffersPanel.jsx");
  const MODAL = path.join(__dirname, "..", "components", "market", "TradeOfferModal.jsx");
  const read = (p) => fs.readFileSync(p, "utf8");

  // The shipped defaults of every knob GET /trade/config publishes. If one of
  // these appears as a literal, somebody has typed a rule instead of reading it.
  const DEFAULTS = ["86400", "86_400", "172800", "172_800", "604800", "604_800"];

  test.each([["tradeRules.js", () => read(SRC)], ["tradeBoard.js", () => read(BOARD)],
             ["TradeOffersPanel.jsx", () => read(PANEL)],
             ["TradeOfferModal.jsx", () => read(MODAL)]])(
    "%s contains no knob default as a literal", (_name, get) => {
      // Comments are stripped first: the files DESCRIBE the defaults in prose
      // and that documentation is the point, not a drift risk.
      const code = get()
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^[ \t]*\/\/.*$/gm, "");
      for (const lit of DEFAULTS) {
        expect(code).not.toContain(lit);
      }
    });

  test("neither file mentions coins, PrimeMeat prices aside — a trade has no coin leg", () => {
    const code = read(SRC).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
    // No input, no field, no body key. `coinsAllowed` is the ruling itself.
    expect(code).not.toMatch(/coins\s*:/);
    expect(code).not.toMatch(/\bcoin_amount\b/);
  });

  test("every rule the page quotes is reachable from readTradeConfig", () => {
    // A structural guard: if a future edit reads a knob straight off a raw
    // payload instead of the normalised config, this catches the shape.
    for (const f of [PANEL, MODAL, path.join(__dirname, "..", "pages", "Marketplace.jsx")]) {
      expect(read(f)).not.toMatch(/\.data\.(cooldown_secs|offer_ttl_secs|symmetry_pct|max_items_per_side|max_board_per_player)/);
    }
  });
});

// ── The glyph budget ────────────────────────────────────────────────────────
// A character the site's webfont does not carry draws as a BOX, and a player
// reads that as corrupted text. It is invisible to every other test here
// because the STRING is correct -- only the rendering is wrong.
//
// The rule is not "no unicode": Spanish needs its accents, and the site has
// been drawing em dashes and ellipses on every page for months, so those are
// proven. The rule is that this feature may not introduce a codepoint the rest
// of the site has never asked the font to draw. U+2022 BULLET appeared zero
// times in the codebase before this wave, and U+2212 MINUS SIGN (the
// typographic minus, not the ASCII hyphen) only twice.
describe("player-facing copy stays inside the proven glyph set", () => {
  const fs = require("fs");
  const path = require("path");
  const SRC = path.join(__dirname, "..");
  const FILES = ["lib/tradeRules.js", "lib/marketPricing.js", "lib/tradeBoard.js",
                 "components/market/TradeOffersPanel.jsx",
                 "components/market/TradeOfferModal.jsx", "pages/Marketplace.jsx"];
  // strip comments -- a codepoint in a comment never reaches a player
  const strip = (t) => t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  const BANNED = [
    ["•", "BULLET -- use · MIDDLE DOT, which the cards already use"],
    ["−", "MINUS SIGN -- use the ASCII hyphen '-', which every font has"],
    ["●", "BLACK CIRCLE -- draw a dot with CSS instead"],
    ["�", "REPLACEMENT CHARACTER -- the file is mis-encoded"],
  ];
  for (const rel of FILES) {
    for (const [ch, why] of BANNED) {
      test(`${rel} contains no U+${ch.codePointAt(0).toString(16).toUpperCase().padStart(4,"0")} (${why.split(" -- ")[0]})`, () => {
        const body = strip(fs.readFileSync(path.join(SRC, rel), "utf8"));
        expect(body.includes(ch)).toBe(false);
      });
    }
  }
  test("the guard can actually fail", () => {
    expect(strip("const s = \"a • b\";").includes("•")).toBe(true);
    expect(strip("// a • comment").includes("•")).toBe(false);
  });
});
