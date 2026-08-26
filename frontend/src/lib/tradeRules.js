// La Isla Nublar — "Intercambios": the rules, the arithmetic and the copy for
// direct player-to-player dinosaur trading. Pure functions only: no React, no
// network, no module state. The Mercado renders these (the offers panel and the
// offer modal under @/components/market, plus @/lib/tradeBoard for what a trade
// CARD is); nothing that renders them decides anything itself.
//
// ─────────────────────────────────────────────────────────────────────────────
// THE ONE LAW OF THIS FILE — inherited verbatim from @/lib/marketPricing
//
//   EVERY RULE COMES FROM THE SERVER PAYLOAD. Nothing here pins the cooldown,
//   the offer TTL, the symmetry percentage, the per-side item cap, the open
//   offer cap or the growth threshold. GET /api/trade/config publishes all six
//   and this file reads them. The page this wave replaced carried a hardcoded
//   fee that drifted from the server's; that is the exact failure a trade page
//   cannot afford, because here the disagreement costs somebody an ANIMAL.
//
//   If a rule is not in the payload, the copy that would have quoted it is NOT
//   RENDERED — never guessed — and, when it is a rule the SEND depends on, the
//   send is blocked with the server's own sentence for why.
//
// ─────────────────────────────────────────────────────────────────────────────
// THE ONE THING THAT IS PINNED, AND WHY
//
//   coinsAllowed is hard FALSE and is not read from the payload. This is not a
//   knob: TradeOfferInput (server.py) has no coins field and there is no place
//   to put one — "a coin leg turns a trade into an untaxed sale and re-opens the
//   fee the market charges". Reading a `coins_allowed: true` off some future
//   payload and rendering a coin box would build an input the API cannot accept.
//   A ruling with no field behind it is not a knob, and it is not read as one.
//
// ─────────────────────────────────────────────────────────────────────────────
// THE THREE SURPRISING RULES THIS FILE EXISTS TO SAY OUT LOUD
//
//   1. ESCROW IS OFFER-SIDE ONLY. Sending takes YOUR animals out of your vault
//      immediately; the animals you ASK for are never frozen. Said before the
//      confirm, not discovered after it.
//   2. BOTH SIDES BURN THE COOLDOWN. Accepting somebody else's offer costs YOU
//      your own day. Sending does not (the create lane only CHECKS both clocks;
//      trade_accept is what CLAIMS them), and that distinction is stated too.
//   3. ESCROWED ANIMALS STILL HOLD THEIR VAULT SLOTS (`reserved_slots`), so a
//      sender who parks something new can find the restore blocked. Surfaced as
//      a live number, not as a footnote.
//
// ─────────────────────────────────────────────────────────────────────────────
// DEGRADE RULES, chosen per field and not interchangeable
//
//   * A missing DISPLAY number  -> the line that would quote it is omitted.
//   * A missing INPUT rule      -> the send is blocked and says why, in the
//                                  server's own words when the server gave one.
//   * A missing GATE            -> fails OPEN on the client. The server's gate
//                                  fails CLOSED and its 409 carries the exact
//                                  wording; a client-side lockout of a player
//                                  the server would have accepted is a support
//                                  ticket for zero benefit.

import { intOrNull, numOrNull, safeIntOrNull, fmtCoin, fmtMutations } from "@/lib/marketPricing";

/* ───────────────────────────── small Spanish ───────────────────────────── */

// «2 espacios» / «1 espacio». Spanish singular is not cosmetic: these strings
// sit inside sentences a player reads before moving an animal.
export function pluralEs(n, one, many) {
  const v = intOrNull(n);
  if (v === null) return null;
  return `${v} ${Math.abs(v) === 1 ? one : many}`;
}

// A wait, the way his players read it: «24 h», «45 min», «30 s», «1 h 30 min».
// EXACT twin of server.py _wait_es, including the "h"/"min" spacing, so a wait
// quoted in the page and the same wait quoted in a 429 are the same string.
// Returns null — never "0 s" — for anything unreadable, so the caller omits the
// line instead of quoting a number the server never sent.
export function waitEs(secs) {
  const n = numOrNull(secs);
  if (n === null) return null;
  const s = Math.max(0, Math.trunc(n));
  if (s >= 3600) {
    const hours = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    return mins ? `${hours} h ${mins} min` : `${hours} h`;
  }
  if (s >= 60) return `${Math.floor(s / 60)} min`;
  return `${s} s`;
}

// A wait that is actually IN FORCE, or null.
//
// ★ ZERO IS NOT A DURATION, IT IS AN OFF SWITCH. `_trade_cooldown_state` and
// `_move_cooldown_state` both begin `if secs <= 0: return None`, and
// `_trade_cooldown_claim` returns True without writing anything — an owner who
// sets the knob to 0 has TURNED THE RULE OFF. Quoting «0 s» would promise a
// cooldown the server does not enforce, which is the same class of lie as
// pinning the wrong number. Every piece of copy that quotes a wait goes through
// here, so none of them can make that promise.
export function activeWait(secs) {
  const n = intOrNull(secs);
  if (n === null || n <= 0) return null;
  return waitEs(n);
}

/* ─────────────────────────── reading the config ─────────────────────────── */

// GET /api/trade/config. Shape (server.py trade_config):
//   { enabled, max_items_per_side, symmetry_pct, max_open_offers, growth_gate,
//     min_growth_pct, coins_allowed,
//     cooldown_secs | cooldown_secs_error,
//     offer_ttl_secs | offer_ttl_secs_error,
//     dino_move_cooldown_secs | dino_move_cooldown_secs_error,
//     my_cooldown_until, my_cooldown_left }
//
// The three `*_secs` keys are the ones the server answers with null + an
// `_error` sentence when the owner has mis-set the knob. Each of those knobs is
// read by trade_create on the way in, so a null there means EVERY send will be
// refused — the page must block and say so rather than let a player pick three
// animals and then eat a 503.
export function readTradeConfig(raw) {
  const c = raw && typeof raw === "object" ? raw : {};
  const pair = (key) => {
    const v = intOrNull(c[key]);
    const e = typeof c[`${key}_error`] === "string" && c[`${key}_error`].trim()
      ? c[`${key}_error`].trim() : null;
    return [v, e];
  };
  const [cooldownSecs, cooldownError] = pair("cooldown_secs");
  const [offerTtlSecs, offerTtlError] = pair("offer_ttl_secs");
  const [moveCooldownSecs, moveCooldownError] = pair("dino_move_cooldown_secs");
  return {
    // `ok` is only "the payload was a payload". It is NOT "every rule is
    // present" — that question is configBlockReason's, and the two must not be
    // confused by a caller.
    ok: !!raw && typeof raw === "object",
    // enabled: a MISSING flag is not a disabled trade lane. Only an explicit
    // false disables (fails open, per the degrade rules above).
    enabled: c.enabled === false ? false : true,
    maxItemsPerSide: intOrNull(c.max_items_per_side),
    symmetryPct: intOrNull(c.symmetry_pct),
    maxOpenOffers: intOrNull(c.max_open_offers),
    growthGate: c.growth_gate === true,
    minGrowthPct: intOrNull(c.min_growth_pct),
    // How many animals one player may have in the trade window at once. A CLAMP
    // knob, so the server always answers a number; null here means the payload
    // did not carry it, and the board's own reply carries it too.
    maxBoardPerPlayer: intOrNull(c.max_board_per_player),
    // PINNED. See the header: there is no coins field on TradeOfferInput.
    coinsAllowed: false,
    cooldownSecs, cooldownError,
    offerTtlSecs, offerTtlError,
    moveCooldownSecs, moveCooldownError,
    myCooldownLeft: Math.max(0, intOrNull(c.my_cooldown_left) || 0),
  };
}

// The reason the SEND button is dead, or null. Ordered by what the server checks
// first, so a player never fixes a late complaint and then meets an earlier one.
// Every string here is the server's own, because the server is what will refuse.
export function configBlockReason(cfg) {
  const c = cfg || {};
  if (!c.ok) {
    return "No pudimos leer las reglas de los intercambios. Actualiza la página; "
      + "si sigue igual, avísale a un administrador.";
  }
  if (c.enabled === false) return "Los intercambios están desactivados por ahora.";
  // The three knob errors, in the order trade_create would hit them. Each is the
  // server's own sentence, so the page and the 503 read the same.
  if (c.cooldownError) return c.cooldownError;
  if (c.offerTtlError) return c.offerTtlError;
  if (c.moveCooldownError) return c.moveCooldownError;
  if (c.cooldownSecs === null || c.offerTtlSecs === null || c.moveCooldownSecs === null) {
    return "Las reglas de los intercambios están incompletas ahora mismo. "
      + "Vuelve a intentarlo en un momento.";
  }
  if (c.maxItemsPerSide === null || c.symmetryPct === null) {
    return "No pudimos leer los límites de un intercambio, así que no podemos "
      + "explicártelos antes de enviarlo. Actualiza la página.";
  }
  return null;
}

/* ─────────────────────────── the value band ─────────────────────────── */

// EXACT twin of server.py _trade_symmetry_ok, in integers on BOTH sides of the
// comparison so the band EDGE is the same here as it is there: at 25%, 6.000.000
// against 8.000.000 is 600.000.000 >= 600.000.000 and trades; 5.999.999 does
// not. A float comparison would make the edge a coin toss between the two.
//
// Returns null — not false — when it cannot be answered exactly. A band the page
// cannot compute must show nothing, never a red "no se puede" over a trade the
// server would have taken.
export function symmetryOk(a, b, pct) {
  const x = safeIntOrNull(a);
  const y = safeIntOrNull(b);
  const p = intOrNull(pct);
  if (x === null || y === null || p === null || p < 0 || p > 100) return null;
  const lo = Math.min(x, y);
  const hi = Math.max(x, y);
  if (hi <= 0) return true;                       // the server's own early true
  const left = lo * 100;
  const right = (100 - p) * hi;
  if (!Number.isSafeInteger(left) || !Number.isSafeInteger(right)) return null;
  return left >= right;
}

// The window the OTHER side must land in for a given side value, derived from
// the same inequality: lo * 100 >= (100 - pct) * hi.
//   pct = 0   -> the two sides must be worth exactly the same.
//   pct = 100 -> the band is off; there is no upper bound.
// `max` is null when unbounded. Returns null when it cannot be answered exactly.
export function bandRange(value, pct) {
  const v = safeIntOrNull(value);
  const p = intOrNull(pct);
  if (v === null || p === null || p < 0 || p > 100 || v < 0) return null;
  if (v === 0) return { min: 0, max: p >= 100 ? null : 0 };
  if (p >= 100) return { min: 0, max: null };
  const min = Math.ceil(((100 - p) * v) / 100);
  const max = Math.floor((v * 100) / (100 - p));
  if (!Number.isSafeInteger(min) || !Number.isSafeInteger(max)) return null;
  return { min, max };
}

// «Con 6.000.000 de tu lado, lo que pidas debe valer entre 4.500.000 y
//  8.000.000 (banda del 25%).»
// The refusal becomes predictable instead of mysterious, which is the whole
// point of publishing the band at all.
export function bandLine(value, pct) {
  const r = bandRange(value, pct);
  const p = intOrNull(pct);
  if (!r || p === null) return null;
  if (p >= 100) return "Ahora mismo no hay límite de diferencia entre los dos lados.";
  if (p === 0) {
    return `Los dos lados deben valer exactamente lo mismo: ${fmtCoin(value)} PrimeMeat.`;
  }
  return `Con ${fmtCoin(value)} de tu lado, lo que pidas debe valer entre `
    + `${fmtCoin(r.min)} y ${fmtCoin(r.max)} PrimeMeat (banda del ${p}%).`;
}

// The verdict on an offer whose BOTH sides are known — i.e. one the server has
// already priced and handed back. Never invents a side it was not given.
export function bandVerdict(offerValue, wantValue, pct) {
  const ok = symmetryOk(offerValue, wantValue, pct);
  if (ok === null) return null;
  const p = intOrNull(pct);
  if (ok) return { ok: true, text: `Equilibrado dentro de la banda del ${p}%.` };
  return {
    ok: false,
    text: `Fuera de la banda del ${p}%: ${fmtCoin(offerValue)} contra ${fmtCoin(wantValue)}.`,
  };
}

/* ─────────────────────────── reading the offers ─────────────────────────── */

// One animal on one side of an offer, as _trade_item_view publishes it (minus
// `fingerprint`, which _trade_public strips and which therefore must never be
// referenced here).
export function readTradeItem(raw) {
  const it = raw && typeof raw === "object" ? raw : {};
  const species = typeof it.species === "string" ? it.species.trim() : "";
  const name = typeof it.name === "string" ? it.name.trim() : "";
  return {
    dinoId: intOrNull(it.dino_id),
    species,
    name,
    growthPct: intOrNull(it.growth_pct),
    mutations: intOrNull(it.mutations),
    prime: it.prime === true,
    value: intOrNull(it.value),
    // A per-animal pricing failure. trade_create and trade_accept BOTH refuse
    // the whole offer on the first one of these (503), so it is not decoration.
    valueError: typeof it.value_error === "string" && it.value_error.trim()
      ? it.value_error.trim() : null,
  };
}

// «Rex «Titán» · 100% · 12 mutaciones · prime» — the same shape the market's
// picker rows use, so one animal never reads two ways across two pages.
export function itemLabel(item) {
  const i = item || {};
  const species = (i.species || "").trim();
  const name = (i.name || "").trim();
  const head = species && name && name !== species ? `${species} «${name}»`
    : species || name || "Dinosaurio";
  const parts = [head];
  if (i.growthPct !== null && i.growthPct !== undefined) parts.push(`${i.growthPct}%`);
  const muts = fmtMutations(i.mutations);
  if (muts) parts.push(muts);
  if (i.prime) parts.push("prime");
  return parts.join(" · ");
}

// Total for one side. Mirrors server.py _trade_side_value for the animals it CAN
// price, and reports the ones it cannot separately — because the create lane
// refuses outright on the first value_error rather than quoting a partial total.
// `total` is null whenever anything is unpriced: half a total is a wrong total.
export function sideValue(items) {
  const list = Array.isArray(items) ? items : [];
  let total = 0;
  let missing = 0;
  for (const raw of list) {
    const it = raw && typeof raw === "object" && "valueError" in raw ? raw : readTradeItem(raw);
    if (it.valueError || it.value === null) { missing += 1; continue; }
    total += Math.max(0, it.value);
  }
  // An unsafe running total cannot be quoted to the coin, so it is reported as
  // unknown rather than as a number that is silently wrong.
  if (!Number.isSafeInteger(total)) return { total: null, missing, partial: null };
  return { total: missing ? null : total, missing, partial: total };
}

const STATUS_LABELS = {
  pending: "Pendiente",
  settling: "Cerrando",
  restore_pending: "Devolviendo",
  accepted: "Aceptado",
  declined: "Rechazado",
  cancelled: "Cancelado",
  expired: "Caducado",
  needs_admin: "Necesita un administrador",
};

export function statusLabel(status) {
  const s = typeof status === "string" ? status : "";
  return STATUS_LABELS[s] || "Desconocido";
}

// What a player should DO about a status that is not simply open or finished.
// The three in-flight states are the ones where an animal is between two vaults,
// and a page that shows them without a next step reads as a lost dinosaur.
export function statusNote(offer) {
  const o = offer || {};
  if (o.status === "settling") {
    return "Se está cerrando ahora mismo. Actualiza en un momento.";
  }
  if (o.status === "restore_pending") {
    return "Estamos devolviendo un dinosaurio a su bóveda. Se reintenta solo; "
      + "libera un espacio si tu bóveda está llena.";
  }
  if (o.status === "needs_admin") {
    return "Este intercambio quedó a medias y lo tiene que revisar un administrador. "
      + "Tus dinosaurios están guardados; no vuelvas a intentarlo.";
  }
  return null;
}

export function readTradeOffer(raw) {
  const o = raw && typeof raw === "object" ? raw : {};
  const offerItems = (Array.isArray(o.offer_items) ? o.offer_items : []).map(readTradeItem);
  const wantItems = (Array.isArray(o.want_items) ? o.want_items : []).map(readTradeItem);
  return {
    id: typeof o.id === "string" ? o.id : "",
    status: typeof o.status === "string" ? o.status : "",
    fromId: typeof o.from_id === "string" ? o.from_id : "",
    toId: typeof o.to_id === "string" ? o.to_id : "",
    // A missing persona name is rendered as a placeholder, never as the raw id:
    // the frontend is plaintext by design and must publish nothing the API has
    // not already published for this viewer.
    fromName: (typeof o.from_name === "string" && o.from_name.trim()) || "Jugador",
    toName: (typeof o.to_name === "string" && o.to_name.trim()) || "Jugador",
    note: (typeof o.note === "string" && o.note.trim()) || null,
    createdAt: typeof o.created_at === "string" ? o.created_at : null,
    expiresAt: typeof o.expires_at === "string" ? o.expires_at : null,
    offerItems,
    wantItems,
    offerValue: intOrNull(o.offer_value),
    wantValue: intOrNull(o.want_value),
    symmetryPct: intOrNull(o.symmetry_pct),
    direction: o.direction === "incoming" || o.direction === "outgoing" ? o.direction : "other",
    // The SERVER decides who may press what. The page never derives this from
    // ids of its own: can_accept/can_cancel already encode viewer + status.
    canAccept: o.can_accept === true,
    canCancel: o.can_cancel === true,
    resolveNote: typeof o.resolve_note === "string" ? o.resolve_note : null,
    settledAt: typeof o.settled_at === "string" ? o.settled_at : null,
    closedAt: typeof o.closed_at === "string" ? o.closed_at : null,
  };
}

// GET /api/trade/mine. `slots_free` is already clamped at zero by the server;
// `reserved_slots` is not a free number, it is how many slots this player's own
// escrow is HOLDING so a restore has somewhere to land.
export function readMine(raw) {
  const m = raw && typeof raw === "object" ? raw : {};
  const list = (v) => (Array.isArray(v) ? v : []).map(readTradeOffer);
  return {
    ok: !!raw && typeof raw === "object",
    incoming: list(m.incoming),
    outgoing: list(m.outgoing),
    history: list(m.history),
    cooldownLeft: Math.max(0, intOrNull(m.cooldown_left) || 0),
    slotsFree: Math.max(0, intOrNull(m.slots_free) || 0),
    reservedSlots: Math.max(0, intOrNull(m.reserved_slots) || 0),
  };
}

// HOW LONG THIS PLAYER'S OWN COOLDOWN STILL HAS TO RUN.
//
// /trade/config and /trade/mine each publish the same clock, and they are
// separate requests that fail separately — so the page has to say which one it
// believes, and WHY, rather than combining them.
//
//   /trade/mine is the POLLED reader. When it answered, it IS the current clock
//   and the config's load-time copy is simply older. MAXING THE TWO would be a
//   bug in the other direction: a page opened with an hour left would keep the
//   banner and the dead «Nueva oferta» button until the player reloaded, long
//   after the server had let them go.
//
//   When /trade/mine did NOT answer, readMine degrades cooldownLeft to zero,
//   and that zero would hide the clock entirely and walk the player into a 429.
//   Then the older reading is the only one there is, and it is used.
//
// `mine.ok` is what distinguishes the two cases, which is the whole reason
// readMine publishes it.
export function effectiveCooldownLeft(mine, cfg) {
  const m = mine || {};
  const fresh = Math.max(0, intOrNull(m.cooldownLeft) || 0);
  if (m.ok === true) return fresh;
  const atLoad = Math.max(0, intOrNull((cfg || {}).myCooldownLeft) || 0);
  return Math.max(fresh, atLoad);
}

/* ───────────────────── my animals, and which are spoken for ───────────────────── */

// The animals of MINE that an INCOMING offer has already named. They are still
// in my vault and still look perfectly offerable — and _pending_trade_hold is
// what refuses them, with "Ese dinosaurio ya está en otra oferta de intercambio."
// Pre-empting it here turns a 409 into a greyed row with a reason.
//
// The animals I have already OFFERED need no such list: escrow deleted the row,
// so they are not in /me/vault at all.
export function heldDinoIds(mine) {
  const out = new Set();
  const m = mine || {};
  for (const o of Array.isArray(m.incoming) ? m.incoming : []) {
    for (const it of (o && o.wantItems) || []) {
      if (it && it.dinoId !== null && it.dinoId !== undefined) out.add(it.dinoId);
    }
  }
  return out;
}

// One /me/vault row as the offer picker reads it. The eligibility order is the
// SERVER'S order in _trade_rows_or_404 — redeem in progress, then the growth
// gate, then an existing claim — so a player never clears a late complaint only
// to meet an earlier one.
//
// The per-animal move cooldown is NOT here: /me/vault does not publish it, so it
// can only refuse at submit time and the page shows the server's 429 verbatim.
export function vaultTradeOption(row, cfg, heldIds) {
  const r = row && typeof row === "object" ? row : {};
  const c = cfg || {};
  const held = heldIds instanceof Set ? heldIds : new Set();
  const id = intOrNull(r.id);
  const species = typeof r.species === "string" ? r.species.trim() : "";
  const name = typeof r.custom_name === "string" ? r.custom_name.trim() : "";
  const growthPct = intOrNull(r.growth_pct);
  const opt = {
    id,
    key: `vault:${id === null ? "?" : id}`,
    species,
    name,
    growthPct,
    mutations: intOrNull(r.mutations_count),
    prime: r.is_prime === true,
    eligible: true,
    blockReason: null,
  };
  opt.label = itemLabel(opt);
  if (id === null) {
    opt.eligible = false;
    opt.blockReason = "no se puede intercambiar (no pudimos leer su número)";
    return opt;
  }
  if (r.redeem_pending === true) {
    opt.eligible = false;
    opt.blockReason = "no se puede intercambiar (recuperación en progreso)";
    return opt;
  }
  // THE GATE FAILS OPEN HERE and closed on the server. With growth_gate off, or
  // with no threshold published, this blocks nobody.
  if (c.growthGate === true && c.minGrowthPct !== null && c.minGrowthPct !== undefined) {
    if (growthPct === null) {
      opt.eligible = false;
      opt.blockReason = "no se puede intercambiar (no pudimos leer su crecimiento)";
      return opt;
    }
    if (growthPct < c.minGrowthPct) {
      opt.eligible = false;
      opt.blockReason = `no se puede intercambiar (mínimo ${c.minGrowthPct}%)`;
      return opt;
    }
  }
  if (held.has(id)) {
    opt.eligible = false;
    opt.blockReason = "ya está comprometido en una oferta que recibiste";
    return opt;
  }
  return opt;
}

export function vaultTradeOptions(rows, cfg, heldIds) {
  return (Array.isArray(rows) ? rows : []).map((r) => vaultTradeOption(r, cfg, heldIds));
}

// The empty state, when nothing this player owns can be offered. Without it the
// page reads as broken rather than as a rule they can act on. Each branch is a
// DIFFERENT fact and they are not interchangeable.
export function offerEmptyState(options, cfg) {
  const list = Array.isArray(options) ? options : [];
  const c = cfg || {};
  if (list.length === 0) {
    return {
      headline: "Todavía no tienes dinosaurios guardados en La Bóveda.",
      body: "Un intercambio mueve dinosaurios guardados, no el que estás jugando. "
        + "Guarda uno en La Bóveda desde Dino en Vivo y vuelve aquí.",
    };
  }
  if (list.some((o) => o && o.eligible)) return null;
  const held = list.filter((o) => o && o.blockReason
    && o.blockReason.startsWith("ya está comprometido"));
  if (held.length === list.length) {
    return {
      headline: "Todos tus dinosaurios ya están comprometidos en ofertas que recibiste.",
      body: "Rechaza alguna de las ofertas que te llegaron, o espera a que caduquen, "
        + "y esos dinosaurios vuelven a estar disponibles.",
    };
  }
  const min = intOrNull(c.minGrowthPct);
  const headline = c.growthGate === true && min !== null
    ? `Ninguno de tus dinosaurios llega al ${min}% de crecimiento todavía.`
    : "Ninguno de tus dinosaurios se puede intercambiar todavía.";
  // The biggest one, and exactly how far short it is — the same shape the
  // market's growth gate uses, so the two pages explain the rule identically.
  let best = null;
  for (const o of list) {
    const g = intOrNull(o && o.growthPct);
    if (g === null) continue;
    if (best === null || g > intOrNull(best.growthPct)) best = o;
  }
  let biggest = null;
  if (best && min !== null && c.growthGate === true) {
    const g = intOrNull(best.growthPct);
    const diff = min > g ? min - g : null;
    biggest = diff !== null
      ? `Tu más grande es ${itemLabel(best)} — ${diff === 1 ? "le falta" : "le faltan"} ${pluralEs(diff, "punto", "puntos")}.`
      : `Tu más grande es ${itemLabel(best)}.`;
  }
  return {
    headline,
    body: "Solo se intercambian adultos, igual que en el Mercado.",
    biggest,
  };
}

/* ───────────────────── the other side, typed by number ───────────────────── */

// EXACT twin of server.py _trade_ids_or_400, including every refusal sentence.
// `label` is "tuyo" for the side you offer and "suyo" for the side you ask for —
// the same two words the route passes.
//
// Booleans are NEVER numbers here, matching the server's `isinstance(v, bool)`
// guard: pydantic in lax mode would otherwise turn `[true]` into a dino id of 1
// that nobody typed.
export function tradeIdsOrError(raw, label, cap) {
  const list = Array.isArray(raw) ? raw : null;
  if (!list || list.length === 0) {
    return { ids: null, error: `Elige al menos un dinosaurio ${label}.` };
  }
  const c = intOrNull(cap);
  if (c !== null && list.length > c) {
    return { ids: null, error: `Como máximo ${c} dinosaurio(s) por lado.` };
  }
  const out = [];
  for (const v of list) {
    if (typeof v === "boolean" || typeof v !== "number" || !Number.isInteger(v)) {
      return { ids: null, error: "Esa lista de dinosaurios no es válida." };
    }
    if (out.includes(v)) {
      return { ids: null, error: "Repetiste el mismo dinosaurio en un lado del intercambio." };
    }
    out.push(v);
  }
  return { ids: out, error: null };
}

// The "what they give you" box takes NUMBERS, because the API has no route that
// lists another player's animals — /api/trade/lookup answers identity only
// ({id, name, avatar, linked}) and there is no second lookup. So a player asks
// their partner for the numbers, and this parses what they typed: commas,
// spaces and newlines all separate.
//
// A token that is not a whole positive number earns the SERVER'S OWN refusal
// rather than an invented one, so a client refusal and a server refusal read the
// same to the player.
export function parseWantIds(text, cap) {
  const s = typeof text === "string" ? text : "";
  const tokens = s.split(/[\s,;]+/).map((t) => t.trim()).filter(Boolean);
  if (tokens.length === 0) return { ids: null, error: "Elige al menos un dinosaurio suyo." };
  const nums = [];
  for (const t of tokens) {
    // /^\d+$/ and not Number(): "1e3", "0x10", " 1 " and "1.0" must all be
    // refused, because the server takes whole ints and nothing else.
    if (!/^\d+$/.test(t)) return { ids: null, error: "Esa lista de dinosaurios no es válida." };
    const n = Number(t);
    if (!Number.isSafeInteger(n) || n <= 0) {
      return { ids: null, error: "Esa lista de dinosaurios no es válida." };
    }
    nums.push(n);
  }
  return tradeIdsOrError(nums, "suyo", cap);
}

/* ──────────────────────── what stops the send ──────────────────────── */

// Everything trade_create checks that this page can check FIRST, in the server's
// own order and with the server's own sentences. Refusing here costs a click;
// refusing after the escrow costs a restore.
export function offerBlockReason({ cfg, mine, partner, offerIds, wantIds } = {}) {
  const c = cfg || {};
  const cfgBlock = configBlockReason(c);
  if (cfgBlock) return cfgBlock;
  const m = mine || {};
  // MY cooldown, then the open-offer cap — the order trade_create uses. Read
  // through effectiveCooldownLeft so a failed /trade/mine cannot hide a clock
  // /trade/config already reported.
  const myLeft = effectiveCooldownLeft(m, c);
  if (myLeft > 0) {
    const left = waitEs(myLeft);
    const total = activeWait(c.cooldownSecs);
    if (left && total) {
      return `Ya intercambiaste hace poco. Cada jugador puede intercambiar una vez `
        + `cada ${total} — te faltan ${left}.`;
    }
    return "Ya intercambiaste hace poco. Espera a que termine tu tiempo de espera.";
  }
  if (!partner || !partner.id) return "Busca al jugador con quien quieres intercambiar.";
  if (partner.linked === false) {
    return "Ese jugador todavía no vinculó su cuenta de Steam, así que no puede intercambiar.";
  }
  const cap = intOrNull(c.maxOpenOffers);
  const open = Array.isArray(m.outgoing) ? m.outgoing.length : 0;
  if (cap !== null && open >= cap) {
    return `Ya tienes ${cap} ofertas abiertas. Cancela una antes de enviar otra.`;
  }
  const a = tradeIdsOrError(offerIds, "tuyo", c.maxItemsPerSide);
  if (a.error) return a.error;
  const b = tradeIdsOrError(wantIds, "suyo", c.maxItemsPerSide);
  if (b.error) return b.error;
  if (a.ids.length !== b.ids.length) {
    // The server's own sentence, verbatim — it quotes the OFFER count twice by
    // construction ("Un intercambio es 2 por 2: ofreces 2 y pides 3.").
    return `Un intercambio es ${a.ids.length} por ${a.ids.length}: ofreces `
      + `${a.ids.length} y pides ${b.ids.length}.`;
  }
  return null;
}

/* ─────────────── the three surprising rules, as sentences ─────────────── */

// RULE 1 — escrow is offer-side only, and it happens on SEND.
export function escrowNotice(cfg) {
  const ttl = activeWait((cfg || {}).offerTtlSecs);
  const tail = ttl
    ? ` Si nadie responde en ${ttl}, la oferta caduca sola y vuelven a tu bóveda.`
    : " Si nadie responde, la oferta caduca sola y vuelven a tu bóveda.";
  return "Al enviar, los dinosaurios que ofreces salen de tu bóveda en ese momento y "
    + "quedan retenidos. Los que pides NO se congelan: su dueño puede venderlos o "
    + "intercambiarlos mientras tanto." + tail;
}

// RULE 2 — both sides burn the cooldown, and it is ACCEPTING that spends it.
// Returns null when the server did not publish the number, rather than saying
// "un tiempo" and letting a player guess.
export function cooldownNotice(cfg, otherName) {
  const total = activeWait((cfg || {}).cooldownSecs);
  if (!total) return null;
  const who = (typeof otherName === "string" && otherName.trim()) || "la otra persona";
  return `Aceptar gasta TU intercambio del día, no solo el de ${who}: los dos quedan `
    + `en espera ${total} antes del siguiente. Enviar una oferta no lo gasta — se `
    + `gasta cuando alguien acepta.`;
}

// RULE 2b — the per-ANIMAL clock a completed trade also stamps, so the trade
// lane is not the uncooled path beside a cooled market.
export function moveCooldownNotice(cfg) {
  const total = activeWait((cfg || {}).moveCooldownSecs);
  if (!total) return null;
  return `Cada dinosaurio que cambia de dueño no se puede volver a mover en ${total}.`;
}

// RULE 3 — escrowed animals still hold their vault slots. `mine.reservedSlots`
// is the live number; the message only exists when there is something to say.
export function reservedSlotsNotice(mine) {
  const m = mine || {};
  const reserved = intOrNull(m.reservedSlots);
  if (reserved === null || reserved <= 0) return null;
  const n = pluralEs(reserved, "espacio", "espacios");
  const free = pluralEs(m.slotsFree, "espacio libre", "espacios libres");
  const head = `Tienes ${n} de bóveda reservados por ofertas abiertas: siguen contando `
    + "como ocupados para que tus dinosaurios tengan dónde volver.";
  if (m.slotsFree === 0) {
    return `${head} No te queda ningún espacio libre: cierra una oferta antes de `
      + "guardar otro dinosaurio.";
  }
  return free ? `${head} Te ${m.slotsFree === 1 ? "queda" : "quedan"} ${free}.` : head;
}

// The banner across the top while a player's own day is spent.
export function cooldownBanner(secondsLeft, cfg) {
  const left = waitEs(secondsLeft);
  const n = intOrNull(secondsLeft);
  if (!left || n === null || n <= 0) return null;
  const total = activeWait((cfg || {}).cooldownSecs);
  if (total) {
    return `Ya intercambiaste hace poco. Cada jugador puede intercambiar una vez cada `
      + `${total} — te faltan ${left}.`;
  }
  return `Ya intercambiaste hace poco — te faltan ${left}.`;
}

/* ──────────────────── the confirmation steps ──────────────────── */

// An action that moves real animals restates what LEAVES the vault and what the
// cooldown COSTS, before the button. Each of these returns a title plus a list
// of lines; a line whose number the server did not publish is simply absent.

export function offerConfirm({ cfg, items, partnerName, wantCount } = {}) {
  const c = cfg || {};
  const list = Array.isArray(items) ? items : [];
  const who = (typeof partnerName === "string" && partnerName.trim()) || "ese jugador";
  const names = list.map((i) => itemLabel(i)).filter(Boolean);
  const lines = [];
  if (names.length) {
    lines.push(`${names.length === 1 ? "Sale" : "Salen"} de tu bóveda AHORA: ${names.join(", ")}.`);
  }
  const n = intOrNull(wantCount);
  if (n !== null) {
    lines.push(`Le pides ${pluralEs(n, "dinosaurio", "dinosaurios")} a ${who}. `
      + "Esos NO se congelan: puede venderlos o intercambiarlos mientras tu oferta está abierta.");
  }
  const ttl = activeWait(c.offerTtlSecs);
  if (ttl) {
    lines.push(`Si ${who} no responde en ${ttl}, la oferta caduca sola y tus `
      + "dinosaurios vuelven a tu bóveda.");
  }
  if (names.length) {
    lines.push(`Mientras la oferta esté abierta, ${pluralEs(names.length, "ese espacio", "esos espacios")} `
      + `de bóveda ${names.length === 1 ? "sigue" : "siguen"} contando como ocupado`
      + `${names.length === 1 ? "" : "s"}, para que tengan dónde volver.`);
  }
  const cd = activeWait(c.cooldownSecs);
  if (cd) {
    lines.push(`Enviar no gasta tu intercambio del día. Se gasta cuando ${who} acepte: `
      + `en ese momento los dos quedan en espera ${cd}.`);
  }
  return {
    title: "¿Enviar este intercambio?",
    lines,
    warning: names.length ? "TUS DINOSAURIOS SALEN DE LA BÓVEDA AL ENVIAR" : null,
    confirmLabel: "Enviar oferta",
  };
}

export function acceptConfirm({ cfg, offer } = {}) {
  const c = cfg || {};
  const o = offer || {};
  const who = (typeof o.fromName === "string" && o.fromName.trim()) || "la otra persona";
  const mine = (o.wantItems || []).map((i) => itemLabel(i)).filter(Boolean);
  const theirs = (o.offerItems || []).map((i) => itemLabel(i)).filter(Boolean);
  const lines = [];
  if (mine.length) {
    lines.push(`${mine.length === 1 ? "Sale" : "Salen"} de tu bóveda: ${mine.join(", ")}.`);
  }
  if (theirs.length) lines.push(`Recibes: ${theirs.join(", ")}.`);
  const cd = activeWait(c.cooldownSecs);
  if (cd) {
    lines.push(`Aceptar gasta TU intercambio del día, no solo el de ${who}: los dos `
      + `quedan en espera ${cd} antes del siguiente.`);
  }
  const move = moveCooldownNotice(c);
  if (move) lines.push(move);
  lines.push("Esto no se puede deshacer.");
  return {
    title: "¿Aceptar este intercambio?",
    lines,
    // With the cooldown knob at 0 the owner has turned the rule OFF, so the
    // banner must not promise a wait that will not happen. What is still true
    // with the cooldown off is that the animals have changed hands for good.
    warning: cd ? `ACEPTAR GASTA TU ESPERA DE ${cd}` : "ESTO NO SE PUEDE DESHACER",
    confirmLabel: "Aceptar intercambio",
  };
}

// Cancel and decline move animals too — the escrow goes home — but nobody can
// lose anything and no cooldown is spent. Saying so is what stops a player
// hesitating over a button that is free.
export function closeConfirm({ offer, kind } = {}) {
  const o = offer || {};
  const cancelling = kind === "cancel";
  const theirs = (o.offerItems || []).map((i) => itemLabel(i)).filter(Boolean);
  const lines = [];
  if (cancelling) {
    lines.push(theirs.length
      ? `${theirs.length === 1 ? "Vuelve" : "Vuelven"} a tu bóveda: ${theirs.join(", ")}.`
      : "Lo que ofreciste vuelve a tu bóveda.");
    lines.push("No gastas tu intercambio del día y no cuesta nada.");
  } else {
    lines.push(theirs.length
      ? `${theirs.length === 1 ? "Vuelve" : "Vuelven"} a la bóveda de ${o.fromName || "quien la envió"}: ${theirs.join(", ")}.`
      : "Lo que ofrecieron vuelve a su bóveda.");
    lines.push("Ninguno de tus dinosaurios se mueve y no gastas tu intercambio del día.");
  }
  return {
    title: cancelling ? "¿Cancelar tu oferta?" : "¿Rechazar esta oferta?",
    lines,
    warning: null,
    confirmLabel: cancelling ? "Cancelar oferta" : "Rechazar oferta",
  };
}

/* ──────────────────────────── the TTL clock ──────────────────────────── */

// An offer can expire while a player is looking at it. A missing or malformed
// `expires_at` reads as EXPIRED rather than rendering "NaNh": an offer whose
// clock cannot be read is one the accept lane refuses anyway ("Esa oferta ya no
// es válida"), so the safe direction here is the server's direction.
export function expiryState(iso, nowMs) {
  const now = numOrNull(nowMs) !== null ? nowMs : Date.now();
  const end = new Date(typeof iso === "string" ? iso : "").getTime();
  if (!Number.isFinite(end)) return { expired: true, secondsLeft: 0, text: "Caducada" };
  const diff = end - now;
  if (diff <= 0) return { expired: true, secondsLeft: 0, text: "Caducada" };
  const secs = Math.floor(diff / 1000);
  return { expired: false, secondsLeft: secs, text: `Caduca en ${waitEs(secs)}` };
}

// The button state for an offer the viewer may act on. An offer that expired
// under the player's cursor must not present a live Accept: pressing it earns
// "Esa oferta ya expiró." and nothing else.
export function actionState(offer, expiry, mine, cfg) {
  const o = offer || {};
  const e = expiry || {};
  const m = mine || {};
  if (e.expired) {
    return { canAct: false, reason: "Esta oferta caducó. Actualiza la página." };
  }
  if (o.status !== "pending") {
    return { canAct: false, reason: statusNote(o) || "Esta oferta ya no está abierta." };
  }
  if (o.canAccept && m.cooldownLeft > 0) {
    return { canAct: false, reason: cooldownBanner(m.cooldownLeft, cfg) };
  }
  // Accepting escrows MY side first, then delivers into slots this offer is
  // already holding. The server refuses at `_trade_slots_free(user) < 0`; a
  // clamped zero here is the display twin and only ever a WARNING, never a lock,
  // because the signed number the gate uses is not published.
  return { canAct: true, reason: null };
}

/* ──────────────────────── when a call fails ──────────────────────── */

// Every network call on this page is exception-contained, and a failure has to
// say what to do NEXT. The server's own `detail` wins whenever there is one:
// it is already Spanish, already exact, and already the sentence the player
// would have seen from any other lane.
export function networkRefusal(err, fallback) {
  const fb = typeof fallback === "string" && fallback.trim()
    ? fallback.trim()
    : "No se pudo completar la acción. Vuelve a intentarlo.";
  if (!err) return fb;
  const res = err.response;
  if (!res) {
    // No response at all: a timeout or a dropped socket. The write may well have
    // landed, so the instruction is to LOOK, not to press again.
    return "No pudimos conectar con el servidor. Revisa tu conexión y actualiza la "
      + "página antes de volver a intentarlo.";
  }
  const detail = res.data && res.data.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (res.status === 401 || res.status === 403) {
    return "Tu sesión caducó o no tienes permiso. Vuelve a iniciar sesión con Steam.";
  }
  if (res.status === 404) return "Eso ya no existe. Actualiza la página.";
  if (res.status === 429) return "Demasiadas acciones seguidas. Espera un momento.";
  if (res.status >= 500) {
    return "El servidor no pudo responder. Espera un momento y actualiza la página.";
  }
  return fb;
}
