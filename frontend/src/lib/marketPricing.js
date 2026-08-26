// La Isla Nublar — market pricing, rails, fee preview, and the copy that quotes
// them. Pure functions only: no React, no network, no module state.
//
// ─────────────────────────────────────────────────────────────────────────────
// THE ONE LAW OF THIS FILE
//
//   EVERY RULE COMES FROM THE SERVER PAYLOAD. Nothing here pins a fee rate, a
//   duration tier, a growth threshold, a price floor or a price ceiling.
//
// Marketplace.jsx used to carry `const feeRate = form.type === "auction" ? 0.10
// : 0.15` and its own SALE_TIERS / AUCTION_TIERS literals. That is how an input
// and a validator drift apart until the page promises a number the server
// refuses — the framework wrote the same warning in webcore/frontend/js/market.js
// (:390-392): "the fee preview is computed from the SAME percentage the settle
// uses ... a page that typed its own number would eventually quote a fee the
// server does not charge." Those literals are gone. If a rule is not in the
// payload, the copy that would have quoted it is NOT RENDERED — never guessed.
//
// ─────────────────────────────────────────────────────────────────────────────
// THE ARITHMETIC MUST MATCH THE SERVER TO THE COIN
//
//   tax = price * pct // 100     INTEGER FLOOR, never round
//   net = price - tax            so price === tax + net, ALWAYS
//
// The floor is in the SELLER's favour and it is load-bearing: 5.800.006 at 25%
// nets the seller 4.350.005, where the naive round() gives 4.350.004. One coin,
// and it is theirs. The old client used Math.round on both halves, so it could
// quote a net the settlement would not pay. Framework twin: webcore/routes/
// auction.py tax_on() (:180).
//
// ─────────────────────────────────────────────────────────────────────────────
// DEGRADE RULES, chosen per field and not interchangeable
//
//   * A missing DISPLAY number  -> the line that would quote it is omitted.
//     Never "0", never "—" inside a sentence, never an invented value.
//   * A missing INPUT rule (duration tiers, tax pct) -> the caller blocks the
//     submit and says why. The panel refuses to send anything it could not
//     first describe to the seller in exact numbers.
//   * A missing GATE (market_eligible, min growth) -> fails OPEN on the client.
//     The server's gate fails CLOSED and its 409 carries the exact wording; a
//     client-side lockout of a seller the server would have accepted is a
//     support ticket for zero benefit.

// The market's money format, pinned once. Spanish grouping: 5.800.000.
// Everything the market renders as an amount goes through here so the number in
// the copy and the number beside it are the same string.
export const MONEY_LOCALE = "es-ES";

// Display-only: how close to the end the countdown turns crimson. This is a
// visual affordance, not a rule the server enforces, so it does not come from
// the payload. The ANTI-SNIPE window is a rule and does — see antisnipeLine().
export const URGENT_SECS = 60;

/* ───────────────────────────── coercion ───────────────────────────── */

// A finite number, or null. Booleans are NEVER numbers here: `true` must not
// read as 1 on any surface, the same discipline the server applies to the fee
// knob and to a submitted price.
export function numOrNull(v) {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string") {
    const s = v.trim();
    if (!s) return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

// A finite integer, or null. May be larger than MAX_SAFE_INTEGER: a hostile
// 10**18 must reach the range check and earn the exact "el precio máximo es N"
// refusal, not be misfiled as "sin decimales".
export function intOrNull(v) {
  const n = numOrNull(v);
  return n !== null && Number.isInteger(n) ? n : null;
}

// A finite integer small enough for exact arithmetic. Anything bigger cannot be
// floored to the coin, so the fee preview declines to answer rather than quote
// a number it cannot stand behind.
export function safeIntOrNull(v) {
  const n = intOrNull(v);
  return n !== null && Number.isSafeInteger(n) ? n : null;
}

// A list of positive finite numbers, deduped and ascending, or null. Duration
// tiers arrive this way; anything else is not a tier list and is not treated as
// one (an empty list is null, so "no tiers" and "unreadable tiers" behave alike).
export function numberList(v) {
  if (!Array.isArray(v)) return null;
  const out = [];
  for (const raw of v) {
    const n = numOrNull(raw);
    if (n === null || n <= 0) continue;
    if (!out.includes(n)) out.push(n);
  }
  out.sort((a, b) => a - b);
  return out.length ? out : null;
}

/* ───────────────────────────── formatting ───────────────────────────── */

// An amount as the market writes it, or the em-dash placeholder. Never throws:
// a locale-less runtime falls back to the plain digits rather than blanking a
// price the seller is about to commit to.
export function fmtCoin(v) {
  const n = numOrNull(v);
  if (n === null) return "—";
  try {
    return n.toLocaleString(MONEY_LOCALE);
  } catch (e) {
    return String(n);
  }
}

// Duration label. 0.5 -> "30m", 24 -> "24h". Shared by both sell surfaces so
// they cannot describe the same tier two ways.
export function fmtDur(h) {
  const n = numOrNull(h);
  if (n === null) return "—";
  return n < 1 ? `${Math.round(n * 60)}m` : `${n}h`;
}

// "12 mutaciones" / "1 mutación". Spanish singular is not cosmetic here: the
// suggestion box shows this string beside the money it accounts for.
export function fmtMutations(n) {
  const v = intOrNull(n);
  if (v === null) return null;
  return `${v} ${v === 1 ? "mutación" : "mutaciones"}`;
}

// "6 puntos" / "1 punto".
export function fmtPoints(n) {
  const v = numOrNull(n);
  if (v === null) return null;
  const r = Math.round(v);
  return `${r} ${r === 1 ? "punto" : "puntos"}`;
}

/* ───────────────────────── the fee, to the coin ───────────────────────── */

// INTEGER FLOOR, computed without ever dividing an inexact float: raw is a safe
// integer, raw % 100 is exact, and (raw - rem) is an exact multiple of 100, so
// the division is exact too. Returns null when it cannot be answered exactly —
// the caller then shows nothing rather than a number that is one coin wrong.
//
// A STRINGIFIED whole number is tolerated ("25" reads as 25), the same
// degrade-tolerantly rule vaultCooldown.js uses on its own server fields: the
// SERVER is the one that refuses a badly-typed fee knob, at 503, before
// anything moves. Blanking a working seller's receipt over a serialiser quirk
// would help nobody. A decimal, a bool and junk are still refused outright.
export function taxOn(price, pct) {
  const p = safeIntOrNull(price);
  const t = intOrNull(pct);
  if (p === null || t === null) return null;
  if (t < 0 || t > 100) return null;          // outside any band the server accepts
  if (p <= 0 || t === 0) return 0;
  const raw = p * t;
  if (!Number.isSafeInteger(raw)) return null;
  const rem = raw % 100;
  return (raw - rem) / 100;
}

// The seller's receipt. `ok` is the only thing a caller should branch on.
// INVARIANT, pinned by test: ok === true implies price === tax + net.
export function feePreview(price, pct) {
  const p = safeIntOrNull(price);
  const t = intOrNull(pct);
  const tax = taxOn(p, t);
  if (p === null || t === null || tax === null) {
    return { ok: false, price: p, pct: t, tax: null, net: null };
  }
  return { ok: true, price: p, pct: t, tax, net: p - tax };
}

/* ─────────────────────── reading the quote payload ─────────────────────── */

// GET /market/suggested-price. Shape (server.py _market_price_quote):
//   { merit: {suggested, min, max, base, per_mutation, mutations,
//             base_source, base_missing},
//     stats: {samples, median, low, high, last_sold},
//     tax_pct, tax_pct_error, abs_min, abs_max,
//     price_floor_pct, price_ceiling_pct, min_growth_pct,
//     sale_durations_h, auction_durations_h, mutations_source }
//
// LEGACY FALLBACK: the pre-wave server answered a FLAT {suggested, samples,
// low, high, avg, based_on}. If `merit` is absent we still take that top-level
// `suggested` so the panel keeps working against an un-upgraded or rolled-back
// backend — but we set `legacy` and render NO itemisation, because there is no
// base and no per-mutation part to itemise and inventing one would be the exact
// lie this wave exists to delete.
export function readQuote(raw) {
  const q = raw && typeof raw === "object" ? raw : {};
  const m = q.merit && typeof q.merit === "object" ? q.merit : {};
  const hasMerit = intOrNull(m.suggested) !== null;
  const suggested = hasMerit ? intOrNull(m.suggested) : intOrNull(q.suggested);
  const base = intOrNull(m.base);
  const perMutation = intOrNull(m.per_mutation);
  const mutations = intOrNull(m.mutations);
  const baseMissing = m.base_missing === true || m.base_source === "fallback";

  return {
    ok: suggested !== null,
    legacy: !hasMerit && suggested !== null,
    suggested,
    base,
    perMutation,
    mutations,
    min: intOrNull(m.min),
    max: intOrNull(m.max),
    baseSource: typeof m.base_source === "string" ? m.base_source : null,
    baseMissing: hasMerit ? baseMissing : false,
    taxPct: intOrNull(q.tax_pct),
    taxError: typeof q.tax_pct_error === "string" && q.tax_pct_error ? q.tax_pct_error : null,
    absMin: intOrNull(q.abs_min),
    absMax: intOrNull(q.abs_max),
    floorPct: intOrNull(q.price_floor_pct),
    ceilingPct: intOrNull(q.price_ceiling_pct),
    minGrowthPct: intOrNull(q.min_growth_pct),
    saleDurations: numberList(q.sale_durations_h),
    auctionDurations: numberList(q.auction_durations_h),
    mutationsSource: typeof q.mutations_source === "string" ? q.mutations_source : null,
    stats: readStats(q.stats),
  };
}

// The empty quote: what the panel holds before anything has loaded, and after a
// failed load. Every consumer must render sensibly off this object alone.
export const EMPTY_QUOTE = readQuote(null);

function readStats(raw) {
  const s = raw && typeof raw === "object" ? raw : {};
  return {
    samples: intOrNull(s.samples),
    median: intOrNull(s.median),
    low: intOrNull(s.low),
    high: intOrNull(s.high),
  };
}

// The legal duration tiers for a listing type, straight off the quote. null
// means "the server did not tell us" — the caller must then block the submit,
// because choosing a tier itself is the page inventing an input.
export function durationTiers(quote, type) {
  const q = quote || EMPTY_QUOTE;
  return type === "auction" ? q.auctionDurations : q.saleDurations;
}

// Which tier to preselect, expressed as an index into the payload's own list.
// The second rung when there is one (today: 24h of [6,24,48,72] and 1h of
// [0.5,1,2,4,8] — the values the panel used to hardcode), the first otherwise.
// Derived from the list, so it holds whatever the owner sets the list to.
export function defaultTier(tiers) {
  if (!Array.isArray(tiers) || tiers.length === 0) return null;
  return tiers.length > 1 ? tiers[1] : tiers[0];
}

/* ──────────────────── reading a listing's own rule fields ──────────────────── */

// GET /market and GET /market/mine publish each listing's rules with it, so a
// card, its bid box and the validator cannot disagree about the same auction.
export function readListing(l) {
  const row = l && typeof l === "object" ? l : {};
  const bid = intOrNull(row.current_bid);
  const price = intOrNull(row.price);
  const growthFloor = intOrNull(row.growth_pct);
  const growthRaw = numOrNull(row.growth);
  return {
    price,
    currentBid: bid !== null && bid > 0 ? bid : null,
    // What the next bidder is bidding against.
    currentAmount: bid !== null && bid > 0 ? bid : price,
    minNextBid: intOrNull(row.min_next_bid),
    bidStep: intOrNull(row.bid_step),
    bidMax: intOrNull(row.bid_max),
    antisnipeSecs: intOrNull(row.antisnipe_secs),
    withdrawFee: intOrNull(row.withdraw_fee),
    maxSaleHours: maxOf(numberList(row.sale_durations_h)),
    // Market surfaces FLOOR growth. A card must never read "80%" for an animal
    // the 80% gate refuses, which is exactly what Math.round() did at 79,51%.
    growthPct: growthFloor !== null ? growthFloor
      : (growthRaw !== null ? Math.floor(growthRaw) : null),
    // The PRICED count — the animal's own slots plus its Elder sets. Parent
    // lineage is excluded: a player is not paid for their grandparent's genes,
    // so advertising it would overstate what the buyer is paying for.
    mutations: intOrNull(row.priced_mutations) !== null
      ? intOrNull(row.priced_mutations)
      : intOrNull(row.mutations_count),
  };
}

function maxOf(list) {
  return Array.isArray(list) && list.length ? list[list.length - 1] : null;
}

/* ───────────────────── the suggestion, itemised ───────────────────── */

// The rows under "PRECIO SUGERIDO", so the number is a claim the seller can
// check rather than a magic figure:
//
//   Base Tyrannosaurus Rex        1.000.000
//   12 mutaciones x 400.000      +4.800.000
//                                 ─────────
//                                 5.800.000
//
// Returns [] — and the caller then shows the headline number with no breakdown
// — when the parts are missing OR when they do not add up to the suggestion.
// An itemisation whose arithmetic is visibly wrong is worse than none: it
// invites the seller to check it and then tells them we cannot count.
export function suggestionRows(quote, speciesLabel) {
  const q = quote || EMPTY_QUOTE;
  if (!q.ok || q.legacy) return [];
  if (q.base === null || q.perMutation === null || q.mutations === null) return [];
  const mutPart = q.perMutation * q.mutations;
  if (!Number.isSafeInteger(mutPart)) return [];
  if (q.base + mutPart !== q.suggested) return [];
  const rows = [
    { key: "base", label: `Base ${speciesLabel || "de la especie"}`, value: q.base, sign: "" },
  ];
  const muts = fmtMutations(q.mutations);
  rows.push({
    key: "muts",
    label: `${muts} × ${fmtCoin(q.perMutation)}`,
    value: mutPart,
    sign: "+",
  });
  return rows;
}

// The button subtitle. Replaces the old "${samples} venta(s)", which described
// a pricing model that no longer exists.
//   «Valor base de la especie más 400.000 por cada mutación. Este Rex tiene 12.»
export function suggestionSubtitle(quote, speciesLabel) {
  const q = quote || EMPTY_QUOTE;
  if (q.perMutation === null) return null;
  const head = `Valor base de la especie más ${fmtCoin(q.perMutation)} por cada mutación.`;
  if (!speciesLabel || q.mutations === null) return head;
  return `${head} Este ${speciesLabel} tiene ${q.mutations}.`;
}

// The rail sentence under the price field.
//   «Puedes pedir entre 2.900.000 y 17.400.000 PrimeMeat para este dinosaurio.»
export function railSentence(quote) {
  const q = quote || EMPTY_QUOTE;
  if (q.min === null || q.max === null) return null;
  return `Puedes pedir entre ${fmtCoin(q.min)} y ${fmtCoin(q.max)} PrimeMeat para este dinosaurio.`;
}

// The amber line for a species with no configured base. Never silent — the
// owner is told by the admin page, the player is told here.
export function fallbackBaseNotice(quote) {
  const q = quote || EMPTY_QUOTE;
  if (!q.baseMissing) return null;
  const head = "Esta especie todavía no tiene valor base configurado.";
  const tail = "Avísale a un administrador.";
  if (q.base === null) return `${head} ${tail}`;
  return `${head} Estamos usando el valor general de ${fmtCoin(q.base)} PrimeMeat. ${tail}`;
}

// Sales history, demoted to a subordinate display line that feeds nothing.
//   «Otros Tyrannosaurus se han vendido entre 800.000 y 3.200.000
//    (mediana 1.000.000, últimas 10 ventas).»
// Rendered only with a real range behind it: one sale is not a range, and zero
// sales is a normal state for a species nobody has listed yet (maia), not a
// warning to dress up.
export function salesHistoryLine(quote, speciesLabel) {
  const s = (quote || EMPTY_QUOTE).stats;
  if (!speciesLabel) return null;
  if (s.samples === null || s.samples < 2) return null;
  if (s.low === null || s.high === null || s.median === null) return null;
  if (s.high <= s.low) return null;
  return `Otros ${speciesLabel} se han vendido entre ${fmtCoin(s.low)} y ${fmtCoin(s.high)} `
    + `(mediana ${fmtCoin(s.median)}, últimas ${s.samples} ventas).`;
}

/* ─────────────────────────── price validation ─────────────────────────── */

// The client's copy of the server's steps 14a-14f, in the server's order, with
// the server's wording. It exists to spend a refusal locally instead of a round
// trip — it is NOT the authority, and every branch degrades to silence rather
// than invent a bound the payload did not carry.
//
// Returns { ok: true, price } or { ok: false, detail } where `detail` is a
// finished Spanish sentence naming the number and what to change it to.
export function validatePrice(rawPrice, quote) {
  const q = quote || EMPTY_QUOTE;
  const text = typeof rawPrice === "string" ? rawPrice.trim() : rawPrice;

  // 14a — present at all.
  if (text === "" || text === null || text === undefined) {
    return {
      ok: false,
      detail: q.suggested !== null
        ? `Escribe un precio. El sugerido para este dinosaurio es ${fmtCoin(q.suggested)} PrimeMeat.`
        : "Escribe un precio.",
    };
  }

  // 14b — a whole number of PrimeMeat. Booleans, decimals, NaN and Infinity all
  // land here; there is no reading of them that is a price.
  const p = intOrNull(text);
  if (p === null) {
    return { ok: false, detail: "El precio debe ser un número entero de PrimeMeat, sin decimales." };
  }

  // 14c / 14d — the market's absolute band.
  if (q.absMin !== null && p < q.absMin) {
    return { ok: false, detail: `El precio mínimo del mercado es ${fmtCoin(q.absMin)} PrimeMeat.` };
  }
  if (q.absMax !== null && p > q.absMax) {
    return { ok: false, detail: `El precio máximo del mercado es ${fmtCoin(q.absMax)} PrimeMeat.` };
  }

  // 14e / 14f — this animal's own rails. The percentage clause is only written
  // when the server sent the percentage; the numbers are always exact.
  if (q.min !== null && p < q.min) {
    return { ok: false, detail: railRefusal("min", p, q) };
  }
  if (q.max !== null && p > q.max) {
    return { ok: false, detail: railRefusal("max", p, q) };
  }

  return { ok: true, price: p };
}

function railRefusal(side, asked, q) {
  const bound = side === "min" ? q.min : q.max;
  const word = side === "min" ? "El mínimo" : "El máximo";
  const head = `Pediste ${fmtCoin(asked)}. ${word} para este dinosaurio es ${fmtCoin(bound)}`;
  const pct = side === "min" ? q.floorPct : q.ceilingPct;
  if (pct === null || q.suggested === null) return `${head}.`;
  // 300% is "el triple" in his copy; any other setting is stated as a percent
  // rather than as prose that would be wrong the moment he changes the knob.
  const share = side === "max" && pct === 300 ? "el triple" : `el ${pct}%`;
  return `${head} — ${share} de su valor de mercado de ${fmtCoin(q.suggested)}.`;
}

// Why the panel will not submit yet, or null when it will. One coherent rule:
// THE PANEL REFUSES TO SEND ANYTHING IT COULD NOT FIRST DESCRIBE TO THE SELLER.
//   * no quote            -> it knows neither the rails nor the cut
//   * no tax_pct          -> it cannot show the net before they commit, which
//                            is the whole point of the receipt
//   * no duration tiers   -> choosing one would be the page inventing an input
// A missing tier list or fee is also exactly what a broken owner knob looks
// like, and the server refuses that at 503 anyway.
export function submitBlockReason(quote, type, loaded) {
  if (!loaded) return "Estamos calculando el precio de este dinosaurio. Espera un momento.";
  const q = quote || EMPTY_QUOTE;
  if (!q.ok) {
    return "No pudimos calcular el valor de este dinosaurio. Vuelve a intentarlo o avísale a un administrador.";
  }
  if (q.taxPct === null) {
    return q.taxError
      || "No pudimos leer la comisión del mercado, así que no podemos decirte cuánto recibirías. Avísale a un administrador.";
  }
  if (!durationTiers(q, type)) {
    return "No pudimos leer las duraciones permitidas para este tipo de publicación. Avísale a un administrador.";
  }
  return null;
}

/* ──────────────────────────── the growth gate ──────────────────────────── */

// The inline reason on a picker row the market will not take. The growth case
// is his wording; the other three are short forms of the server's own 409s,
// which the seller sees in full if they get that far.
export function blockLabel(reason, minGrowthPct) {
  const r = typeof reason === "string" ? reason : "";
  if (r.startsWith("growth_low")) {
    return minGrowthPct !== null && minGrowthPct !== undefined
      ? `no se puede publicar (mínimo ${minGrowthPct}%)`
      : "no se puede publicar (crecimiento insuficiente)";
  }
  if (r === "redeem_pending") return "no se puede publicar (recuperación en progreso)";
  if (r === "in_trade") return "no se puede publicar (comprometido en un intercambio)";
  if (r === "move_cooldown") return "no se puede publicar (cambió de dueño hace poco)";
  return "no se puede publicar";
}

// "Rex «Titán»" — species first, the player's own name in his quotes. Falls
// back cleanly when either half is missing.
export function dinoLabel(opt) {
  const o = opt || {};
  const species = (o.species || "").trim();
  const custom = (o.customName || "").trim();
  if (species && custom && custom !== species) return `${species} «${custom}»`;
  return species || custom || "Dinosaurio";
}

// The full picker row:
//   Rex «Titán» · 100% · 12 mutaciones · prime
//   Rex «Cría» · 74% · 3 mutaciones — no se puede publicar (mínimo 80%)
export function pickerLabel(opt, minGrowthPct) {
  const o = opt || {};
  const parts = [dinoLabel(o)];
  const g = intOrNull(o.growthPct);
  if (g !== null) parts.push(`${g}%`);
  const muts = fmtMutations(o.mutations);
  if (muts) parts.push(muts);
  if (o.prime) parts.push("prime");
  const line = parts.join(" · ");
  if (o.eligible === false) return `${line} — ${blockLabel(o.blockReason, minGrowthPct)}`;
  return line;
}

// The empty state, when nothing the player owns clears the gate. Without it the
// page reads as broken rather than as a rule they can act on.
//
//   Ninguno de tus dinosaurios llega al 80% de crecimiento todavía.
//   El mercado solo acepta adultos. Es lo que hace que cada publicación valga la pena.
//   Tu más grande es Rex «Titán» con 74% — le faltan 6 puntos.
export const GATE_EMPTY_BODY =
  "El mercado solo acepta adultos. Es lo que hace que cada publicación valga la pena.";

export function gateEmptyState(options, minGrowthPct) {
  const min = intOrNull(minGrowthPct);
  const headline = min !== null
    ? `Ninguno de tus dinosaurios llega al ${min}% de crecimiento todavía.`
    : "Ninguno de tus dinosaurios llega al crecimiento mínimo todavía.";
  const list = Array.isArray(options) ? options : [];
  let best = null;
  for (const o of list) {
    const g = intOrNull(o && o.growthPct);
    if (g === null) continue;
    if (best === null || g > intOrNull(best.growthPct)) best = o;
  }
  let biggest = null;
  if (best) {
    const g = intOrNull(best.growthPct);
    const diff = min !== null && min > g ? min - g : null;
    // "le faltan 6 puntos" but "le falta 1 punto" — the verb agrees too, not
    // just the noun.
    biggest = diff !== null
      ? `Tu más grande es ${dinoLabel(best)} con ${g}% — ${diff === 1 ? "le falta" : "le faltan"} ${fmtPoints(diff)}.`
      : `Tu más grande es ${dinoLabel(best)} con ${g}%.`;
  }
  return { headline, body: GATE_EMPTY_BODY, biggest };
}

/* ──────────────────────────── the auction ──────────────────────────── */

// «Siguiente puja mínima: 5.916.000 (puja actual 5.800.000 + incremento 116.000).»
// The arithmetic is spelled out so a bidder can see why their 1-coin raise was
// refused. Degrades to the bare minimum when the step is not published, and to
// nothing at all when the minimum itself is not.
export function nextBidLine(listing) {
  const r = readListing(listing);
  if (r.minNextBid === null) return null;
  if (r.bidStep === null || r.currentAmount === null) {
    return `Siguiente puja mínima: ${fmtCoin(r.minNextBid)}.`;
  }
  return `Siguiente puja mínima: ${fmtCoin(r.minNextBid)} `
    + `(puja actual ${fmtCoin(r.currentAmount)} + incremento ${fmtCoin(r.bidStep)}).`;
}

// The refusals the bid box spends locally instead of a round trip. Same
// wording the server uses, so a client refusal and a server refusal read the
// same to the player. Both return null when the payload did not carry the
// bound — the client then refuses nothing and the server keeps the last word.
export function minBidRefusal(listing) {
  const r = readListing(listing);
  if (r.minNextBid === null) return null;
  const head = `La puja mínima es ${fmtCoin(r.minNextBid)} PrimeMeat`;
  if (r.bidStep === null || r.currentAmount === null) return `${head}.`;
  return `${head} (puja actual ${fmtCoin(r.currentAmount)} + incremento ${fmtCoin(r.bidStep)}).`;
}

export function maxBidRefusal(listing) {
  const r = readListing(listing);
  if (r.bidMax === null) return null;
  return `La puja máxima permitida es ${fmtCoin(r.bidMax)} PrimeMeat.`;
}

// «Últimos 60 segundos: cada puja añade 60 segundos. Nadie gana solo por llegar tarde.»
// Shown only inside the window the SERVER published, and only when there is a
// window at all — an owner who sets antisnipe_secs to 0 has turned it off and
// the card must not keep promising it.
export function antisnipeLine(listing, secondsLeft) {
  const r = readListing(listing);
  const left = numOrNull(secondsLeft);
  if (r.antisnipeSecs === null || r.antisnipeSecs <= 0) return null;
  if (left === null || left <= 0 || left > r.antisnipeSecs) return null;
  return `Últimos ${r.antisnipeSecs} segundos: cada puja añade ${r.antisnipeSecs} segundos. `
    + "Nadie gana solo por llegar tarde.";
}

/* ──────────────────────────── the withdraw fee ──────────────────────────── */

// The flat fee, plus the escape. The old modal said "(10%)" in fixed text while
// the server charged something else entirely.
export function withdrawMessage(listing, where) {
  const r = readListing(listing);
  const dest = where === "vault" ? "bóveda" : "inventario";
  const head = r.withdrawFee !== null
    ? `Retirar cuesta ${fmtCoin(r.withdrawFee)} PrimeMeat.`
    : "Retirar tiene una comisión.";
  const tail = r.maxSaleHours !== null
    ? `Si no quieres pagarla, la publicación vuelve a tu ${dest} gratis cuando expire (máximo ${r.maxSaleHours} horas).`
    : `Si no quieres pagarla, la publicación vuelve a tu ${dest} gratis cuando expire.`;
  return `${head} ${tail}`;
}

/* ──────────────────────── idempotency for money calls ──────────────────────── */

// One attempt id per attempt. A REPLAY of the same id returns the stored
// outcome; a NEW id is a new attempt. Callers keep the id across a transport
// failure (where the server may well have completed the write) and mint a fresh
// one only after a definite answer — that is what stops a timed-out listing
// from being created twice by an honest second click.
export function newRequestId() {
  try {
    const c = typeof globalThis !== "undefined" ? globalThis.crypto : null;
    if (c && typeof c.randomUUID === "function") return c.randomUUID();
    if (c && typeof c.getRandomValues === "function") {
      const b = new Uint8Array(16);
      c.getRandomValues(b);
      return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
    }
  } catch (e) {
    // No crypto in this runtime — fall through to the time+random id.
  }
  return `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

// A response came back (any status) => the attempt has a definite outcome and
// the next click is a NEW attempt. No response at all (timeout, dropped socket)
// => the server may have completed it, so the next click must REPLAY the same
// id rather than risk a second listing.
export function attemptSettled(err) {
  if (!err) return true;                       // success
  return !!(err && err.response);              // a real refusal is still an outcome
}
