/**
 * The market's pricing, rails, receipt and refusals.
 *
 * Two halves, both against real things:
 *  1. the REAL helpers driven by REAL /market/suggested-price and /market
 *     payload shapes — the full key set the routes emit, not a two-key stub, so
 *     a fixture with the wrong contract cannot score a false green;
 *  2. the REAL Marketplace.jsx read off disk, proving the page is actually
 *     wired to those helpers. The arithmetic being right is worthless if the
 *     JSX still computes its own fee from a client constant.
 *
 * RED CONTROLS (these are the point — a rule with no mutation test rots):
 *  - `round()` instead of the integer floor is asserted to give a DIFFERENT,
 *    WRONG net on 5.800.006 @ 25% and on 100.009 @ 95%. Flipping `//` to a
 *    rounding division turns those two tests red.
 *  - the hardcoded `feeRate = 0.10 / 0.15` and the duplicated SALE_TIERS /
 *    AUCTION_TIERS literals are asserted ABSENT from Marketplace.jsx. Putting
 *    either back turns the source pins red.
 *
 * NEGATIVE CONTROL: against the unfixed tree every test here fails — the module
 * does not exist, and Marketplace.jsx still carries both literals.
 */
const fs = require("fs");
const path = require("path");

import {
  numOrNull, intOrNull, safeIntOrNull, numberList,
  fmtCoin, fmtDur, fmtMutations, fmtPoints,
  taxOn, feePreview,
  readQuote, EMPTY_QUOTE, readListing, durationTiers, defaultTier,
  suggestionRows, suggestionSubtitle, railSentence, fallbackBaseNotice, salesHistoryLine,
  validatePrice, submitBlockReason,
  blockLabel, dinoLabel, pickerLabel, gateEmptyState, GATE_EMPTY_BODY,
  nextBidLine, antisnipeLine, withdrawMessage, minBidRefusal, maxBidRefusal,
  newRequestId, attemptSettled,
} from "./marketPricing";

// A real GET /market/suggested-price body for his worked example: a
// 12-mutation Tyrannosaurus. Every key _market_price_quote emits.
function quoteBody(overrides = {}, meritOverrides = {}) {
  return {
    merit: {
      suggested: 5800000,
      min: 2900000,
      max: 17400000,
      base: 1000000,
      per_mutation: 400000,
      mutations: 12,
      base_source: "table",
      base_missing: false,
      ...meritOverrides,
    },
    stats: { samples: 10, median: 1000000, low: 800000, high: 3200000, last_sold: null },
    tax_pct: 25,
    abs_min: 10000,
    abs_max: 25000000,
    price_floor_pct: 50,
    price_ceiling_pct: 300,
    min_growth_pct: 80,
    sale_durations_h: [6, 24, 48, 72],
    auction_durations_h: [0.5, 1, 2, 4, 8],
    mutations_source: "vault",
    ...overrides,
  };
}

// A real auction row off GET /market.
function listingBody(overrides = {}) {
  return {
    id: "l1",
    type: "auction",
    price: 5800000,
    current_bid: 5800000,
    min_next_bid: 5916000,
    bid_step: 116000,
    bid_max: 50000000,
    antisnipe_secs: 60,
    growth_pct: 100,
    priced_mutations: 12,
    mutations_count: 4,
    tax_pct: 25,
    withdraw_fee: 25000,
    sale_durations_h: [6, 24, 48, 72],
    ends_at: "2026-08-11T12:00:00Z",
    ...overrides,
  };
}

/* ─────────────────────────── coercion ─────────────────────────── */

describe("coercion — a boolean is never a number", () => {
  test("true/false are refused by every reader", () => {
    // `True` is an int in Python and would read as 1%. The client must not
    // make the same mistake with a fee, a price or a mutation count.
    expect(numOrNull(true)).toBeNull();
    expect(intOrNull(true)).toBeNull();
    expect(safeIntOrNull(false)).toBeNull();
  });

  test("junk, empty and non-finite all read as absent", () => {
    for (const v of [null, undefined, "", "   ", "abc", NaN, Infinity, -Infinity, {}, []]) {
      expect(numOrNull(v)).toBeNull();
      expect(intOrNull(v)).toBeNull();
    }
  });

  test("numeric strings are accepted, decimals are not integers", () => {
    expect(numOrNull("5800000")).toBe(5800000);
    expect(intOrNull("5800000")).toBe(5800000);
    expect(intOrNull("5.5")).toBeNull();
    expect(intOrNull(5.5)).toBeNull();
  });

  test("a huge integer survives intOrNull so it can earn the max refusal, but not safeIntOrNull", () => {
    expect(intOrNull(1e18)).toBe(1e18);
    expect(safeIntOrNull(1e18)).toBeNull();
  });

  test("numberList keeps positive numbers, sorts, dedupes, and calls empty null", () => {
    expect(numberList([72, 6, 24, 48])).toEqual([6, 24, 48, 72]);
    expect(numberList([1, 1, 2])).toEqual([1, 2]);
    expect(numberList([0.5, 1, 2, 4, 8])).toEqual([0.5, 1, 2, 4, 8]);
    expect(numberList([])).toBeNull();
    expect(numberList([0, -1, "x", null])).toBeNull();
    expect(numberList("6,24")).toBeNull();
    expect(numberList(null)).toBeNull();
  });
});

/* ─────────────────────── the fee, to the coin ─────────────────────── */

describe("taxOn — INTEGER FLOOR, never round", () => {
  test("his worked example lands to the coin", () => {
    // trex 1.000.000 + 12 x 400.000 = 5.800.000; at 25% the seller nets 4.350.000
    const r = feePreview(5800000, 25);
    expect(r.ok).toBe(true);
    expect(r.tax).toBe(1450000);
    expect(r.net).toBe(4350000);
  });

  test("RED CONTROL — 5.800.006 @ 25%: the old page's two numbers did not even add up", () => {
    // NOTE the spec's control number (net 4.350.004) is PYTHON's round(), which
    // is banker's rounding; JS Math.round(x.5) goes up, so the same defect
    // surfaces on the FEE line here instead of the net line. Both halves are
    // asserted so a `//`->rounding regression cannot pass either way.
    const price = 5800006;
    const r = feePreview(price, 25);
    expect(r.tax).toBe(1450001);
    expect(r.net).toBe(4350005);

    // exactly what Marketplace.jsx used to compute, asserted DIFFERENT and WRONG
    const oldFee = Math.round(price * 0.25);
    const oldNet = Math.round(price * (1 - 0.25));
    expect(oldFee).toBe(1450002);
    expect(r.tax).not.toBe(oldFee);
    // and the old pair claimed one coin that never existed
    expect(oldFee + oldNet).toBe(5800007);
    expect(oldFee + oldNet).not.toBe(price);
    expect(r.tax + r.net).toBe(price);
  });

  test("RED CONTROL — band top 100.009 @ 95%: tax 95.008, net 5.001; round() control gives 95.009", () => {
    const r = feePreview(100009, 95);
    expect(r.tax).toBe(95008);
    expect(r.net).toBe(5001);
    expect(Math.round(100009 * 0.95)).toBe(95009);
    expect(r.tax).not.toBe(Math.round(100009 * 0.95));
  });

  test("the seller is never paid zero, even at the band ceiling", () => {
    // abs_min_price 10.000 at 95% still leaves 500 — that is what the 95 ceiling buys
    const r = feePreview(10000, 95);
    expect(r.tax).toBe(9500);
    expect(r.net).toBe(500);
    expect(r.net).toBeGreaterThan(0);
  });

  test("price === tax + net for every legal (price, pct)", () => {
    for (const price of [1, 2, 3, 9999, 10000, 150000, 2900000, 5800001, 5800006, 17400000, 25000000]) {
      for (let pct = 0; pct <= 95; pct++) {
        const r = feePreview(price, pct);
        expect(r.ok).toBe(true);
        expect(r.tax + r.net).toBe(price);
        expect(r.tax).toBeGreaterThanOrEqual(0);
        expect(r.net).toBeGreaterThanOrEqual(0);
      }
    }
  });

  test("0% takes nothing, and a zero/negative price cannot mint a fee", () => {
    expect(taxOn(5800000, 0)).toBe(0);
    expect(taxOn(0, 25)).toBe(0);
    expect(taxOn(-1, 25)).toBe(0);
  });

  test("an unreadable pct yields NO preview rather than a guessed one", () => {
    for (const bad of [null, undefined, 25.0001, true, false, NaN, Infinity, -1, 101, 1000, "abc", ""]) {
      expect(taxOn(5800000, bad)).toBeNull();
      expect(feePreview(5800000, bad).ok).toBe(false);
    }
    // a stringified whole number is still whole — the SERVER refuses a badly
    // typed knob at 503; the client must not blank a working seller's receipt
    // over a serialiser quirk
    expect(taxOn(5800000, "25")).toBe(1450000);
  });

  test("a price too large to floor exactly declines to answer", () => {
    expect(taxOn(1e18, 25)).toBeNull();
    expect(feePreview(1e18, 25).ok).toBe(false);
  });
});

/* ─────────────────── the quote payload, and every hole in it ─────────────────── */

describe("readQuote — the page reads every rule from the payload", () => {
  test("the real body parses to his numbers", () => {
    const q = readQuote(quoteBody());
    expect(q.ok).toBe(true);
    expect(q.legacy).toBe(false);
    expect(q.suggested).toBe(5800000);
    expect(q.base).toBe(1000000);
    expect(q.perMutation).toBe(400000);
    expect(q.mutations).toBe(12);
    expect(q.min).toBe(2900000);
    expect(q.max).toBe(17400000);
    expect(q.taxPct).toBe(25);
    expect(q.absMin).toBe(10000);
    expect(q.absMax).toBe(25000000);
    expect(q.minGrowthPct).toBe(80);
    expect(q.saleDurations).toEqual([6, 24, 48, 72]);
    expect(q.auctionDurations).toEqual([0.5, 1, 2, 4, 8]);
  });

  test("FIRST RUN / total failure — null, {} and junk all give the same safe empty quote", () => {
    for (const raw of [null, undefined, {}, "nope", 7, []]) {
      const q = readQuote(raw);
      expect(q.ok).toBe(false);
      expect(q.suggested).toBeNull();
      expect(q.taxPct).toBeNull();
      expect(q.min).toBeNull();
      expect(q.max).toBeNull();
      expect(q.saleDurations).toBeNull();
      expect(q.auctionDurations).toBeNull();
    }
    expect(EMPTY_QUOTE.ok).toBe(false);
  });

  test("the fee is NEVER defaulted — a payload without tax_pct reports null, not 25", () => {
    const q = readQuote(quoteBody({ tax_pct: null }));
    expect(q.taxPct).toBeNull();
    expect(feePreview(5800000, q.taxPct).ok).toBe(false);
  });

  test("a broken tax knob carries the server's own words through", () => {
    const q = readQuote(quoteBody({ tax_pct: null, tax_pct_error: "La comisión del mercado está mal configurada." }));
    expect(q.taxPct).toBeNull();
    expect(q.taxError).toBe("La comisión del mercado está mal configurada.");
  });

  test("the page follows the payload's fee, whatever it is", () => {
    expect(feePreview(5800000, readQuote(quoteBody({ tax_pct: 25 })).taxPct).net).toBe(4350000);
    expect(feePreview(5800000, readQuote(quoteBody({ tax_pct: 10 })).taxPct).net).toBe(5220000);
    expect(feePreview(5800000, readQuote(quoteBody({ tax_pct: 0 })).taxPct).net).toBe(5800000);
  });

  test("ZERO MUTATIONS — the suggestion is the base exactly", () => {
    const q = readQuote(quoteBody({}, { suggested: 1000000, mutations: 0, min: 500000, max: 3000000 }));
    expect(q.suggested).toBe(1000000);
    expect(q.suggested).toBe(q.base);
  });

  test("LEGACY BACKEND — a flat {suggested} still seeds the field, but claims no itemisation", () => {
    const q = readQuote({ suggested: 3549734, samples: 5, based_on: "market" });
    expect(q.ok).toBe(true);
    expect(q.legacy).toBe(true);
    expect(q.suggested).toBe(3549734);
    expect(suggestionRows(q, "Tyrannosaurus")).toEqual([]);
  });

  test("durationTiers and defaultTier come from the list, never from a constant", () => {
    const q = readQuote(quoteBody());
    expect(durationTiers(q, "sale")).toEqual([6, 24, 48, 72]);
    expect(durationTiers(q, "auction")).toEqual([0.5, 1, 2, 4, 8]);
    expect(defaultTier(durationTiers(q, "sale"))).toBe(24);
    expect(defaultTier(durationTiers(q, "auction"))).toBe(1);
    // an owner who reduces the list to one rung gets that rung, not a pinned 24
    expect(defaultTier([12])).toBe(12);
    expect(defaultTier([])).toBeNull();
    expect(defaultTier(null)).toBeNull();
    // and a payload with no lists offers nothing to choose from
    const empty = readQuote(quoteBody({ sale_durations_h: null, auction_durations_h: [] }));
    expect(durationTiers(empty, "sale")).toBeNull();
    expect(durationTiers(empty, "auction")).toBeNull();
  });
});

/* ───────────────── the suggestion, shown as a checkable claim ───────────────── */

describe("suggestionRows — the number is a claim the player can check", () => {
  test("his box, itemised", () => {
    const rows = suggestionRows(readQuote(quoteBody()), "Tyrannosaurus Rex");
    expect(rows).toHaveLength(2);
    expect(rows[0].label).toBe("Base Tyrannosaurus Rex");
    expect(rows[0].value).toBe(1000000);
    expect(rows[1].label).toBe("12 mutaciones × 400.000");
    expect(rows[1].value).toBe(4800000);
    expect(rows[1].sign).toBe("+");
    expect(rows[0].value + rows[1].value).toBe(5800000);
  });

  test("one mutation is singular", () => {
    const q = readQuote(quoteBody({}, { suggested: 1400000, mutations: 1 }));
    expect(suggestionRows(q, "Rex")[1].label).toBe("1 mutación × 400.000");
  });

  test("zero mutations still itemises honestly and sums to the base", () => {
    const q = readQuote(quoteBody({}, { suggested: 1000000, mutations: 0 }));
    const rows = suggestionRows(q, "Rex");
    expect(rows[1].label).toBe("0 mutaciones × 400.000");
    expect(rows[1].value).toBe(0);
    expect(rows[0].value + rows[1].value).toBe(q.suggested);
  });

  test("an itemisation that does NOT add up is not rendered at all", () => {
    // better a bare number than an arithmetic that invites checking and fails it
    const q = readQuote(quoteBody({}, { suggested: 9999999 }));
    expect(suggestionRows(q, "Rex")).toEqual([]);
  });

  test("missing parts drop the breakdown, never fake it", () => {
    expect(suggestionRows(readQuote(quoteBody({}, { base: null })), "Rex")).toEqual([]);
    expect(suggestionRows(readQuote(quoteBody({}, { per_mutation: null })), "Rex")).toEqual([]);
    expect(suggestionRows(readQuote(quoteBody({}, { mutations: null })), "Rex")).toEqual([]);
    expect(suggestionRows(EMPTY_QUOTE, "Rex")).toEqual([]);
  });

  test("the subtitle replaces the old sales count", () => {
    expect(suggestionSubtitle(readQuote(quoteBody()), "Rex"))
      .toBe("Valor base de la especie más 400.000 por cada mutación. Este Rex tiene 12.");
    // no species known -> the rule is still stated, the animal is not invented
    expect(suggestionSubtitle(readQuote(quoteBody()), ""))
      .toBe("Valor base de la especie más 400.000 por cada mutación.");
    expect(suggestionSubtitle(EMPTY_QUOTE, "Rex")).toBeNull();
  });
});

describe("the lines around the price field", () => {
  test("the rail sentence", () => {
    expect(railSentence(readQuote(quoteBody())))
      .toBe("Puedes pedir entre 2.900.000 y 17.400.000 PrimeMeat para este dinosaurio.");
    expect(railSentence(EMPTY_QUOTE)).toBeNull();
  });

  test("a species with no configured base says so, in amber, with the number", () => {
    const q = readQuote(quoteBody({}, { base: 400000, base_source: "fallback", base_missing: true }));
    expect(fallbackBaseNotice(q)).toBe(
      "Esta especie todavía no tiene valor base configurado. "
      + "Estamos usando el valor general de 400.000 PrimeMeat. Avísale a un administrador."
    );
    expect(fallbackBaseNotice(readQuote(quoteBody()))).toBeNull();
  });

  test("sales history is subordinate, and silent when there is no range behind it", () => {
    expect(salesHistoryLine(readQuote(quoteBody()), "Tyrannosaurus")).toBe(
      "Otros Tyrannosaurus se han vendido entre 800.000 y 3.200.000 "
      + "(mediana 1.000.000, últimas 10 ventas)."
    );
    // maia: no sales ever. A normal listing, not a warning.
    const none = readQuote(quoteBody({ stats: { samples: 0, median: null, low: null, high: null } }));
    expect(salesHistoryLine(none, "Maiasaura")).toBeNull();
    const one = readQuote(quoteBody({ stats: { samples: 1, median: 10000, low: 10000, high: 10000 } }));
    expect(salesHistoryLine(one, "Tenontosaurus")).toBeNull();
    expect(salesHistoryLine(EMPTY_QUOTE, "Rex")).toBeNull();
  });
});

/* ─────────────────────────── price validation ─────────────────────────── */

describe("validatePrice — one exact refusal each, naming what to change", () => {
  const q = readQuote(quoteBody());

  test("no price at all names the suggestion instead of defaulting to it", () => {
    for (const empty of ["", "   ", null, undefined]) {
      expect(validatePrice(empty, q).detail)
        .toBe("Escribe un precio. El sugerido para este dinosaurio es 5.800.000 PrimeMeat.");
    }
    // and with no suggestion to name, it still asks — it never invents one
    expect(validatePrice("", EMPTY_QUOTE).detail).toBe("Escribe un precio.");
  });

  test("a non-integer is refused as a type", () => {
    for (const bad of ["5.5", 5.5, "abc", NaN, Infinity, true, "1e400"]) {
      expect(validatePrice(bad, q).detail)
        .toBe("El precio debe ser un número entero de PrimeMeat, sin decimales.");
    }
  });

  test("the market's absolute band", () => {
    expect(validatePrice(9999, q).detail).toBe("El precio mínimo del mercado es 10.000 PrimeMeat.");
    expect(validatePrice(0, q).detail).toBe("El precio mínimo del mercado es 10.000 PrimeMeat.");
    expect(validatePrice(-1, q).detail).toBe("El precio mínimo del mercado es 10.000 PrimeMeat.");
    expect(validatePrice(1, q).detail).toBe("El precio mínimo del mercado es 10.000 PrimeMeat.");
    // 10**18 is an integer, so it must reach the MAX message, not the type one
    expect(validatePrice(1e18, q).detail).toBe("El precio máximo del mercado es 25.000.000 PrimeMeat.");
  });

  test("this animal's rails, with the percentage that actually bound", () => {
    expect(validatePrice(400000, q).detail).toBe(
      "Pediste 400.000. El mínimo para este dinosaurio es 2.900.000 — el 50% de su valor de mercado de 5.800.000."
    );
    expect(validatePrice(20000000, q).detail).toBe(
      "Pediste 20.000.000. El máximo para este dinosaurio es 17.400.000 — el triple de su valor de mercado de 5.800.000."
    );
  });

  test("a ceiling the owner moved is stated as a percent, never as prose that would be a lie", () => {
    const q250 = readQuote(quoteBody({ price_ceiling_pct: 250 }, { max: 14500000 }));
    expect(validatePrice(20000000, q250).detail).toBe(
      "Pediste 20.000.000. El máximo para este dinosaurio es 14.500.000 — el 250% de su valor de mercado de 5.800.000."
    );
  });

  test("a payload without the percentages still gives exact numbers, and claims no percentage", () => {
    const bare = readQuote(quoteBody({ price_floor_pct: null, price_ceiling_pct: null }));
    expect(validatePrice(400000, bare).detail)
      .toBe("Pediste 400.000. El mínimo para este dinosaurio es 2.900.000.");
  });

  test("BOUNDARY — exactly at the floor and exactly at the ceiling are ACCEPTED, one off each is not", () => {
    expect(validatePrice(2900000, q)).toEqual({ ok: true, price: 2900000 });
    expect(validatePrice(2899999, q).ok).toBe(false);
    expect(validatePrice(17400000, q)).toEqual({ ok: true, price: 17400000 });
    expect(validatePrice(17400001, q).ok).toBe(false);
  });

  test("with no rails published, the client refuses nothing and the server keeps the last word", () => {
    const bare = readQuote({ merit: { suggested: 5800000 }, tax_pct: 25 });
    expect(validatePrice(1, bare)).toEqual({ ok: true, price: 1 });
  });
});

describe("submitBlockReason — the panel refuses to send what it could not describe", () => {
  test("nothing loaded yet", () => {
    expect(submitBlockReason(EMPTY_QUOTE, "sale", false))
      .toBe("Estamos calculando el precio de este dinosaurio. Espera un momento.");
  });

  test("the quote failed", () => {
    expect(submitBlockReason(EMPTY_QUOTE, "sale", true))
      .toBe("No pudimos calcular el valor de este dinosaurio. Vuelve a intentarlo o avísale a un administrador.");
  });

  test("no fee means the seller cannot see their net, so nothing is sent", () => {
    const q = readQuote(quoteBody({ tax_pct: null }));
    expect(submitBlockReason(q, "sale", true)).toMatch(/no podemos decirte cuánto recibirías/);
    // the server's own words win when it sent them
    const withErr = readQuote(quoteBody({ tax_pct: null, tax_pct_error: "Mal configurada." }));
    expect(submitBlockReason(withErr, "sale", true)).toBe("Mal configurada.");
  });

  test("no duration tiers for THAT type blocks only that type", () => {
    const q = readQuote(quoteBody({ auction_durations_h: null }));
    expect(submitBlockReason(q, "sale", true)).toBeNull();
    expect(submitBlockReason(q, "auction", true))
      .toBe("No pudimos leer las duraciones permitidas para este tipo de publicación. Avísale a un administrador.");
  });

  test("a complete quote blocks nothing", () => {
    const q = readQuote(quoteBody());
    expect(submitBlockReason(q, "sale", true)).toBeNull();
    expect(submitBlockReason(q, "auction", true)).toBeNull();
  });
});

/* ─────────────────────────── the growth gate ─────────────────────────── */

describe("the growth gate, as the seller meets it", () => {
  test("his three picker rows, exactly", () => {
    expect(pickerLabel({ species: "Rex", customName: "Titán", growthPct: 100, mutations: 12, prime: true }, 80))
      .toBe("Rex «Titán» · 100% · 12 mutaciones · prime");
    expect(pickerLabel({ species: "Deinosuchus", customName: "Fauces", growthPct: 92, mutations: 8 }, 80))
      .toBe("Deinosuchus «Fauces» · 92% · 8 mutaciones");
    expect(pickerLabel({
      species: "Rex", customName: "Cría", growthPct: 74, mutations: 3,
      eligible: false, blockReason: "growth_low_74",
    }, 80)).toBe("Rex «Cría» · 74% · 3 mutaciones — no se puede publicar (mínimo 80%)");
  });

  test("an unknown minimum states the rule without inventing the number", () => {
    expect(blockLabel("growth_low_74", null)).toBe("no se puede publicar (crecimiento insuficiente)");
    expect(blockLabel("growth_low_74", 80)).toBe("no se puede publicar (mínimo 80%)");
  });

  test("the other three block reasons each say something a player can act on", () => {
    expect(blockLabel("redeem_pending", 80)).toBe("no se puede publicar (recuperación en progreso)");
    expect(blockLabel("in_trade", 80)).toBe("no se puede publicar (comprometido en un intercambio)");
    expect(blockLabel("move_cooldown", 80)).toBe("no se puede publicar (cambió de dueño hace poco)");
    expect(blockLabel(undefined, 80)).toBe("no se puede publicar");
  });

  test("a nameless animal still renders", () => {
    expect(dinoLabel({ species: "Rex" })).toBe("Rex");
    expect(dinoLabel({ customName: "Titán" })).toBe("Titán");
    expect(dinoLabel({ species: "Rex", customName: "Rex" })).toBe("Rex");
    expect(dinoLabel(null)).toBe("Dinosaurio");
  });

  test("EMPTY STATE — nothing qualifies", () => {
    const s = gateEmptyState([
      { species: "Rex", customName: "Titán", growthPct: 74 },
      { species: "Rex", customName: "Cría", growthPct: 30 },
    ], 80);
    expect(s.headline).toBe("Ninguno de tus dinosaurios llega al 80% de crecimiento todavía.");
    expect(s.body).toBe(GATE_EMPTY_BODY);
    expect(s.biggest).toBe("Tu más grande es Rex «Titán» con 74% — le faltan 6 puntos.");
  });

  test("EMPTY STATE — one point short is singular", () => {
    expect(gateEmptyState([{ species: "Rex", growthPct: 79 }], 80).biggest)
      .toBe("Tu más grande es Rex con 79% — le falta 1 punto.");
  });

  test("EMPTY STATE — first run: no dinos at all, and no minimum published", () => {
    const none = gateEmptyState([], 80);
    expect(none.headline).toBe("Ninguno de tus dinosaurios llega al 80% de crecimiento todavía.");
    expect(none.biggest).toBeNull();
    const noMin = gateEmptyState([{ species: "Rex", growthPct: 74 }], null);
    expect(noMin.headline).toBe("Ninguno de tus dinosaurios llega al crecimiento mínimo todavía.");
    expect(noMin.biggest).toBe("Tu más grande es Rex con 74%.");
  });
});

/* ──────────────────────── listings, cards, auction ──────────────────────── */

describe("readListing — the card and the gate can never disagree", () => {
  test("growth FLOORS, so a card never shows 80% for an animal the gate refuses", () => {
    // the 0,7951 case: round() printed 80 and the 80% gate refused it
    expect(readListing({ growth: 79.51 }).growthPct).toBe(79);
    expect(readListing({ growth: 79.9 }).growthPct).toBe(79);
    expect(readListing({ growth: 80.0 }).growthPct).toBe(80);
    // the server's own floored field wins when it is there
    expect(readListing({ growth_pct: 79, growth: 79.9 }).growthPct).toBe(79);
    expect(readListing({}).growthPct).toBeNull();
  });

  test("the PRICED mutation count is advertised — the 4+8 Deinosuchus reads 12, not 4", () => {
    expect(readListing({ priced_mutations: 12, mutations_count: 4 }).mutations).toBe(12);
    expect(readListing({ mutations_count: 4 }).mutations).toBe(4);
    expect(readListing({ priced_mutations: 0, mutations_count: 4 }).mutations).toBe(0);
    expect(readListing({}).mutations).toBeNull();
  });

  test("the current amount is the bid when there is one, the ask when there is not", () => {
    expect(readListing({ price: 5800000, current_bid: 5900000 }).currentAmount).toBe(5900000);
    expect(readListing({ price: 5800000, current_bid: 0 }).currentAmount).toBe(5800000);
    expect(readListing({ price: 5800000, current_bid: null }).currentAmount).toBe(5800000);
  });

  test("a listing that is already gone reads as all-null and renders nothing", () => {
    const r = readListing(null);
    expect(r.minNextBid).toBeNull();
    expect(r.withdrawFee).toBeNull();
    expect(r.growthPct).toBeNull();
  });
});

describe("the auction surface", () => {
  test("the next legal bid, with the arithmetic under it", () => {
    expect(nextBidLine(listingBody())).toBe(
      "Siguiente puja mínima: 5.916.000 (puja actual 5.800.000 + incremento 116.000)."
    );
  });

  test("no published step degrades to the bare minimum, never to a made-up increment", () => {
    expect(nextBidLine(listingBody({ bid_step: null }))).toBe("Siguiente puja mínima: 5.916.000.");
  });

  test("no published minimum says nothing at all", () => {
    expect(nextBidLine(listingBody({ min_next_bid: null }))).toBeNull();
    expect(nextBidLine(null)).toBeNull();
  });

  test("the bid refusals are the server's own wording", () => {
    expect(minBidRefusal(listingBody())).toBe(
      "La puja mínima es 5.916.000 PrimeMeat (puja actual 5.800.000 + incremento 116.000)."
    );
    expect(minBidRefusal(listingBody({ bid_step: null }))).toBe("La puja mínima es 5.916.000 PrimeMeat.");
    expect(minBidRefusal(listingBody({ min_next_bid: null }))).toBeNull();
    expect(maxBidRefusal(listingBody())).toBe("La puja máxima permitida es 50.000.000 PrimeMeat.");
    expect(maxBidRefusal(listingBody({ bid_max: null }))).toBeNull();
  });

  test("anti-snipe is announced inside the SERVER's window and nowhere else", () => {
    const l = listingBody();
    expect(antisnipeLine(l, 45)).toBe(
      "Últimos 60 segundos: cada puja añade 60 segundos. Nadie gana solo por llegar tarde."
    );
    expect(antisnipeLine(l, 60)).not.toBeNull();
    expect(antisnipeLine(l, 61)).toBeNull();
    expect(antisnipeLine(l, 0)).toBeNull();
    // an owner who turned it off must not have the card keep promising it
    expect(antisnipeLine(listingBody({ antisnipe_secs: 0 }), 10)).toBeNull();
    expect(antisnipeLine(listingBody({ antisnipe_secs: null }), 10)).toBeNull();
    // a 90 s window is announced as 90, not as a pinned 60
    expect(antisnipeLine(listingBody({ antisnipe_secs: 90 }), 80))
      .toBe("Últimos 90 segundos: cada puja añade 90 segundos. Nadie gana solo por llegar tarde.");
  });
});

describe("withdraw — the flat number and the free escape", () => {
  test("the fee is the payload's, and the escape is stated", () => {
    expect(withdrawMessage(listingBody(), "vault")).toBe(
      "Retirar cuesta 25.000 PrimeMeat. Si no quieres pagarla, la publicación vuelve a tu bóveda "
      + "gratis cuando expire (máximo 72 horas)."
    );
    expect(withdrawMessage(listingBody(), "inventory")).toMatch(/vuelve a tu inventario/);
  });

  test("no published fee and no published window still produce a sentence", () => {
    expect(withdrawMessage(listingBody({ withdraw_fee: null, sale_durations_h: null }), "vault"))
      .toBe("Retirar tiene una comisión. Si no quieres pagarla, la publicación vuelve a tu bóveda gratis cuando expire.");
  });

  test("the message never says 10%", () => {
    expect(withdrawMessage(listingBody(), "vault")).not.toMatch(/10\s*%/);
  });
});

/* ───────────────────────────── formatting ───────────────────────────── */

describe("one money format for the whole market", () => {
  test("es-ES grouping, so the copy and the field agree", () => {
    expect(fmtCoin(5800000)).toBe("5.800.000");
    expect(fmtCoin(400000)).toBe("400.000");
    expect(fmtCoin(0)).toBe("0");
    expect(fmtCoin("5800000")).toBe("5.800.000");
  });

  test("an absent amount is an em dash, never a zero", () => {
    // "0" beside "Recibes al vender" is a lie; "—" is the truth
    expect(fmtCoin(null)).toBe("—");
    expect(fmtCoin(undefined)).toBe("—");
    expect(fmtCoin("abc")).toBe("—");
    expect(fmtCoin(NaN)).toBe("—");
  });

  test("durations and counts", () => {
    expect(fmtDur(0.5)).toBe("30m");
    expect(fmtDur(1)).toBe("1h");
    expect(fmtDur(72)).toBe("72h");
    expect(fmtDur(null)).toBe("—");
    expect(fmtMutations(12)).toBe("12 mutaciones");
    expect(fmtMutations(1)).toBe("1 mutación");
    expect(fmtMutations(0)).toBe("0 mutaciones");
    expect(fmtMutations(null)).toBeNull();
    expect(fmtPoints(6)).toBe("6 puntos");
    expect(fmtPoints(1)).toBe("1 punto");
  });
});

/* ──────────────────── idempotency across a dropped socket ──────────────────── */

describe("attempt ids", () => {
  test("every id is distinct and non-empty", () => {
    const seen = new Set();
    for (let i = 0; i < 200; i++) {
      const id = newRequestId();
      expect(typeof id).toBe("string");
      expect(id.length).toBeGreaterThan(7);
      seen.add(id);
    }
    expect(seen.size).toBe(200);
  });

  test("a definite answer settles the attempt; a dropped socket does NOT", () => {
    expect(attemptSettled(null)).toBe(true);                       // success
    expect(attemptSettled({ response: { status: 400 } })).toBe(true);  // a refusal is an outcome
    expect(attemptSettled({ message: "timeout of 30000ms exceeded" })).toBe(false);
    expect(attemptSettled({ code: "ECONNABORTED" })).toBe(false);
  });
});

/* ────────── the page is actually wired to all of this (source pins) ────────── */

describe("Marketplace.jsx no longer pins its own copy of the rules", () => {
  const src = fs.readFileSync(
    path.join(__dirname, "..", "pages", "Marketplace.jsx"), "utf8"
  );

  // NOTE these pins are deliberately SHAPE-matched, not bare-number matched.
  // Marketplace.jsx legitimately contains 0.15 (a useInView viewport threshold)
  // and 0.10 (an rgba alpha), and a pin that condemned those would be a check
  // that reads the wrong node and condemns working code.
  test("the hardcoded feeRate is GONE", () => {
    expect(src).not.toMatch(/feeRate/);
    expect(src).not.toMatch(/0\.10\s*:\s*0\.15/);
    expect(src).not.toMatch(/Math\.round\(\s*Number\(\s*form\.price/);
  });

  test("the duplicated duration tiers are GONE", () => {
    expect(src).not.toMatch(/SALE_TIERS/);
    expect(src).not.toMatch(/AUCTION_TIERS/);
    expect(src).not.toMatch(/\[\s*0\.5\s*,\s*1\s*,\s*2\s*,\s*4\s*,\s*8\s*\]/);
    expect(src).not.toMatch(/\[\s*6\s*,\s*24\s*,\s*48\s*,\s*72\s*\]/);
  });

  test("the read-only price field and its lie are GONE", () => {
    expect(src).not.toMatch(/Fijado por el mercado/);
    expect(src).toMatch(/data-testid="sell-price"/);
    expect(src).toMatch(/type="number"/);
  });

  test("the old rarity-base and sales-count subtitles are GONE", () => {
    expect(src).not.toMatch(/venta\(s\)/);
    expect(src).not.toMatch(/base por rareza/);
  });

  test("the hardcoded withdraw percentage is GONE", () => {
    expect(src).not.toMatch(/\(10%\)/);
  });

  test("the placeholder no longer advertises 16 mutations", () => {
    expect(src).not.toMatch(/Rex con 16 mutaciones/);
    expect(src).toMatch(/Rex Titán con 12 mutaciones/);
  });

  test("the page renders the decision, not its own inline arithmetic", () => {
    expect(src).toMatch(/from "@\/lib\/marketPricing"/);
    expect(src).toMatch(/feePreview\(/);
    expect(src).toMatch(/validatePrice\(/);
    expect(src).toMatch(/submitBlockReason\(/);
    expect(src).not.toMatch(/Math\.round\(\s*feeRate/);
  });

  test("money is formatted once, through the pinned locale", () => {
    // no bare toLocaleString() left to disagree with the copy beside it
    expect(src).not.toMatch(/toLocaleString\(\)/);
  });

  test("every money call carries an attempt id", () => {
    expect(src).toMatch(/client_request_id/);
    expect(src).toMatch(/expected_price/);
  });
});

describe("DinoManageModal.jsx — the second sell surface uses the same one copy", () => {
  const src = fs.readFileSync(
    path.join(__dirname, "..", "components", "inventory", "DinoManageModal.jsx"), "utf8"
  );

  test("all five duplicated constants are GONE", () => {
    expect(src).not.toMatch(/SALE_DURATIONS/);
    expect(src).not.toMatch(/AUCTION_DURATIONS/);
    expect(src).not.toMatch(/SALE_FEE_RATE/);
    expect(src).not.toMatch(/AUCTION_FEE_RATE/);
    expect(src).not.toMatch(/TIER_CAP/);
  });

  test("it reads the same module the Mercado page does", () => {
    expect(src).toMatch(/from "@\/lib\/marketPricing"/);
    expect(src).toMatch(/feePreview\(/);
  });

  test("its own 'Fijado por el mercado' is GONE", () => {
    expect(src).not.toMatch(/Fijado por el mercado/);
  });
});
