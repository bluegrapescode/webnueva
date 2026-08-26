// La Isla Nublar — the TRADE BOARD: the rules, the reading and the copy for
// trading a dinosaur on the same surface the dinosaurs are sold on. Pure
// functions only: no React, no network, no module state.
//
// ─────────────────────────────────────────────────────────────────────────────
// WHY THIS FILE EXISTS (owner, 2026-08-11)
//
//   "redesign so dinosaurs get traded on the same tab people can see dinos for
//    sale. no need to send anybody anything."
//
//   The first build put trading on its own page and made an offer something you
//   ADDRESSED: you looked a player up by exact name and then TYPED that player's
//   parked row numbers — numbers no route on this backend hands out. The only
//   way to learn one was to message the other player somewhere else and ask.
//   The rules were right and the door was unreachable.
//
//   A card fixes both halves at once. The animal is advertised in the market
//   grid beside the sales and the auctions, and an offer names a CARD, so the
//   server resolves the other player and the wanted animal itself. Nobody sends
//   anybody anything.
//
// ─────────────────────────────────────────────────────────────────────────────
// THE LAWS, inherited verbatim from @/lib/tradeRules and @/lib/marketPricing
//
//   EVERY RULE COMES FROM THE SERVER PAYLOAD. The card cap and the card TTL are
//   published by GET /api/trade/config and GET /api/trade/board and are read
//   here, never typed. A rule that is missing from the payload is NOT GUESSED:
//   its sentence is simply not rendered, and when the publish depends on it the
//   button is blocked with the server's own words.
//
//   THE ARITHMETIC IS NOT RE-IMPLEMENTED. The value band, the item labels, the
//   cooldown copy and the offer-block order all come from @/lib/tradeRules —
//   this file adds only what a CARD is, and delegates the rest. Two copies of
//   the band rule is how a page and a server end up disagreeing about whether
//   an offer is fair, and here that disagreement costs somebody an animal.
//
// ─────────────────────────────────────────────────────────────────────────────
// THE ONE FACT A CARD DOES NOT CARRY, AND WHY
//
//   `dinoId` is null on every card except your own. Publishing opts an ANIMAL
//   into being offered on; it does not opt its row number into a public
//   directory. The offer lane takes the CARD id and looks the animal up
//   server-side, so the number never needs to travel — which was the whole
//   defect this redesign closes, and broadcasting it would have been the lazy
//   way to close it.
//
// ─────────────────────────────────────────────────────────────────────────────
// AND THE ONE A CARD DOES NOT PROMISE
//
//   A CARD ESCROWS NOTHING. The animal stays in its owner's vault, redeemable
//   and sellable, until an offer is accepted. So a card can be stale, and the
//   copy says so out loud rather than letting a player discover it in a refusal.

import { intOrNull, fmtCoin } from "@/lib/marketPricing";
import {
  itemLabel, offerBlockReason, configBlockReason, activeWait, pluralEs, bandLine,
} from "@/lib/tradeRules";

/* ───────────────────────────── reading a card ───────────────────────────── */

// One card as `_trade_board_public` publishes it. The key names deliberately
// mirror a market listing, because ONE card component in the grid renders a
// sale, an auction and a trade — `type` is what tells them apart.
export function readBoardCard(raw) {
  const c = raw && typeof raw === "object" ? raw : {};
  const species = typeof c.species === "string" ? c.species.trim() : "";
  const title = typeof c.title === "string" ? c.title.trim() : "";
  return {
    id: typeof c.id === "string" ? c.id : "",
    type: "trade",
    title,
    note: typeof c.note === "string" && c.note.trim() ? c.note.trim() : null,
    ownerName: typeof c.seller_name === "string" ? c.seller_name.trim() : "",
    species,
    dinoName: typeof c.dino_name === "string" ? c.dino_name.trim() : species,
    growthPct: intOrNull(c.growth_pct),
    mutations: intOrNull(c.priced_mutations) !== null
      ? intOrNull(c.priced_mutations) : intOrNull(c.mutations_count),
    prime: c.prime === true,
    isElder: c.is_elder === true,
    value: intOrNull(c.value),
    // MINE / OFFERED are the two facts that decide which button this card gets.
    mine: c.mine === true,
    offered: c.offered === true,
    offers: Math.max(0, intOrNull(c.offers) || 0),
    // Only ever a number on my OWN card. See the header.
    dinoId: intOrNull(c.dino_id),
    endsAt: typeof c.ends_at === "string" ? c.ends_at : null,
    // The payload as it arrived, carried rather than copied field by field.
    // The grid renders a trade card through the SAME media and meta components
    // a sale uses, and those read the server's key names — which is exactly why
    // `_trade_board_public` publishes them. Duplicating that shape here would
    // be a second place for the card to drift from the listing beside it.
    raw: c,
  };
}

// The whole board payload. A failed read degrades to an EMPTY board with `ok`
// false — never to a board that looks empty and is indistinguishable from one.
export function readBoard(raw) {
  const b = raw && typeof raw === "object" ? raw : {};
  const cards = (Array.isArray(b.cards) ? b.cards : []).map(readBoardCard);
  const ttl = intOrNull(b.ttl_secs);
  const ttlError = typeof b.ttl_secs_error === "string" && b.ttl_secs_error.trim()
    ? b.ttl_secs_error.trim() : null;
  return {
    ok: !!raw && typeof raw === "object" && Array.isArray(b.cards),
    cards,
    maxPerPlayer: intOrNull(b.max_per_player),
    ttlSecs: ttl,
    ttlError,
    mine: cards.filter((c) => c.mine).length,
  };
}

// The label under a card, and it is never decoration: each branch is the reason
// this card's button is what it is.
export function cardStatusLine(card) {
  const c = card || {};
  if (c.mine) {
    return c.offers > 0
      ? `Tienes ${pluralEs(c.offers, "oferta", "ofertas")} por este dinosaurio.`
      : "Publicado por ti. Nadie ha ofrecido todavía.";
  }
  if (c.offered) return "Ya enviaste una oferta por este dinosaurio.";
  if (c.offers > 0) return `${pluralEs(c.offers, "oferta abierta", "ofertas abiertas")}.`;
  return null;
}

// What a card is worth, as a sentence. Absent when the server did not price it.
export function cardValueLine(card) {
  const v = intOrNull((card || {}).value);
  if (v === null) return null;
  return `Vale unos ${fmtCoin(v)} PrimeMeat`;
}

/* ─────────────────────────── publishing a card ─────────────────────────── */

// Why the PUBLISH button is dead, or null. In the server's order, with the
// server's own sentences — refusing here costs a click, and every one of these
// is a 4xx the publish lane would have answered anyway.
export function publishBlockReason({ cfg, board, option } = {}) {
  const c = cfg || {};
  const b = board || {};
  const cfgBlock = configBlockReason(c);
  if (cfgBlock) return cfgBlock;
  // The card TTL is a REFUSE knob on the server: a broken one refuses every
  // publish, so the button must not pretend otherwise.
  if (b.ttlError) return b.ttlError;
  const cap = intOrNull(b.maxPerPlayer) !== null
    ? intOrNull(b.maxPerPlayer) : intOrNull(c.maxBoardPerPlayer);
  const mine = Math.max(0, intOrNull(b.mine) || 0);
  if (cap !== null && mine >= cap) {
    return `Ya tienes ${cap} dinosaurios publicados para intercambio. Quita uno `
      + "antes de publicar otro.";
  }
  const o = option || null;
  if (!o) return "Elige un dinosaurio para publicar.";
  if (o.eligible === false) {
    return o.blockReason
      ? `Ese dinosaurio ${o.blockReason}.`
      : "Ese dinosaurio no se puede intercambiar ahora mismo.";
  }
  if (alreadyOnBoard(b, o)) return "Ese dinosaurio ya está publicado para intercambio.";
  return null;
}

// Is this animal already in the window? Only answerable for MY cards, which is
// the only place it matters — the server refuses a duplicate either way.
export function alreadyOnBoard(board, option) {
  const id = intOrNull((option || {}).id);
  if (id === null) return false;
  return (((board || {}).cards) || []).some((c) => c.mine && c.dinoId === id);
}

// The confirmation before a card goes up. Short on purpose: publishing is the
// one action in this whole subsystem that moves NOTHING, and dressing it up
// with escrow warnings would teach players to click through the ones that do.
export function publishConfirm({ cfg, board, option } = {}) {
  const o = option || {};
  const lines = [];
  const label = itemLabel(o);
  lines.push(`${label || "Ese dinosaurio"} aparece en el Mercado como disponible `
    + "para intercambio.");
  lines.push("No sale de tu bóveda: sigue siendo tuyo, lo puedes recuperar, vender "
    + "o quitar del Mercado cuando quieras.");
  const ttl = activeWait((board || {}).ttlSecs);
  if (ttl) lines.push(`La publicación se retira sola en ${ttl}.`);
  const cd = activeWait((cfg || {}).cooldownSecs);
  if (cd) {
    lines.push("Publicar no gasta tu intercambio del día. Se gasta cuando aceptas "
      + `una oferta: en ese momento los dos quedáis en espera ${cd}.`);
  }
  return { title: "¿Publicarlo para intercambio?", lines, warning: null,
           confirmLabel: "Publicar para intercambio" };
}

// Taking my own card down. Also free, and it says the one thing that is NOT
// obvious: offers already sent stay alive, because they hold somebody else's
// animals in escrow and are not ours to void.
export function closeCardConfirm(card) {
  const c = card || {};
  const lines = ["Deja de aparecer en el Mercado. Tu dinosaurio no se mueve: nunca "
    + "salió de tu bóveda."];
  if (c.offers > 0) {
    lines.push(`Las ${pluralEs(c.offers, "oferta que ya recibiste sigue", "ofertas que ya recibiste siguen")} `
      + "abiertas: quien las envió tiene sus dinosaurios retenidos, así que "
      + "recházalas si ya no te interesan.");
  }
  return { title: "¿Quitarlo del Mercado?", lines, warning: null,
           confirmLabel: "Quitar del Mercado" };
}

/* ────────────────────── offering on somebody's card ────────────────────── */

// Why the OFFER button is dead, or null. Delegates the whole cooldown / cap /
// count order to tradeRules.offerBlockReason so the two send paths cannot drift
// apart, and adds only what is specific to a card.
//
// ★ The partner handed down is the CARD's owner as the page knows them: an id
// and a name, with `linked` deliberately left unset. The page cannot see
// whether that player still has Steam linked, and the server refuses on it with
// an exact sentence — a client-side lockout of a player the server would have
// accepted is the failure mode this codebase already ruled against.
export function cardOfferBlockReason({ cfg, mine, card, offerIds } = {}) {
  const c = card || {};
  if (!c.id) return "Esa publicación ya no está disponible. Actualiza la página.";
  if (c.mine) return "Esa publicación es tuya.";
  if (c.offered) {
    return "Ya tienes una oferta abierta por ese dinosaurio. Espera la respuesta o "
      + "cancélala.";
  }
  const ids = Array.isArray(offerIds) ? offerIds : [];
  // ONE FOR ONE from a card, and the reason is the server's N-for-N rule: a
  // card is exactly one animal, so an offer against it is exactly one animal.
  if (ids.length > 1) {
    return "Un intercambio es 1 por 1: puedes ofrecer un dinosaurio por este.";
  }
  return offerBlockReason({
    cfg,
    mine,
    partner: { id: c.id, name: c.ownerName },
    offerIds: ids,
    wantIds: ids.length ? [1] : [],
  });
}

// The band, stated for a specific card: what MY side has to be worth for this
// card's animal to be a legal trade. Null when either number is missing —
// quoting half a band is worse than quoting none.
export function cardBandLine(card, symmetryPct) {
  const v = intOrNull((card || {}).value);
  if (v === null) return null;
  const line = bandLine(v, symmetryPct);
  if (!line) return null;
  return line.replace("de tu lado, lo que pidas", "de su lado, lo que ofrezcas");
}

// The verdict on ONE picked animal against this card, before anything is sent.
// Returns null when either side is unpriced.
export function pickVerdict(card, myValue, symmetryPct) {
  const want = intOrNull((card || {}).value);
  const mineV = intOrNull(myValue);
  if (want === null || mineV === null) return null;
  const p = intOrNull(symmetryPct);
  if (p === null) return null;
  const lo = Math.min(want, mineV);
  const hi = Math.max(want, mineV);
  const ok = hi <= 0 ? true : lo * 100 >= (100 - p) * hi;
  if (ok) {
    return { ok: true, text: `Equilibrado: ${fmtCoin(mineV)} por ${fmtCoin(want)}.` };
  }
  return {
    ok: false,
    text: `Fuera de la banda del ${p}%: ofreces ${fmtCoin(mineV)} por ${fmtCoin(want)}.`,
  };
}

// The confirmation before an offer leaves. The escrow warning is the headline
// because it is the one thing that happens the instant the button is pressed.
export function cardOfferConfirm({ cfg, card, item } = {}) {
  const c = cfg || {};
  const k = card || {};
  const who = (k.ownerName || "").trim() || "ese jugador";
  const label = itemLabel(item || {});
  const lines = [];
  if (label) lines.push(`Sale de tu bóveda AHORA: ${label}.`);
  lines.push(`Pides ${k.title || k.dinoName || "ese dinosaurio"} a ${who}. Ese NO se `
    + "congela: puede venderlo o intercambiarlo mientras tu oferta está abierta.");
  const ttl = activeWait(c.offerTtlSecs);
  if (ttl) {
    lines.push(`Si ${who} no responde en ${ttl}, la oferta caduca sola y tu `
      + "dinosaurio vuelve a tu bóveda.");
  }
  lines.push("Mientras la oferta esté abierta, ese espacio de bóveda sigue contando "
    + "como ocupado, para que tenga dónde volver.");
  const cd = activeWait(c.cooldownSecs);
  if (cd) {
    lines.push(`Enviar no gasta tu intercambio del día. Se gasta cuando ${who} `
      + `acepte: en ese momento los dos quedáis en espera ${cd}.`);
  }
  return {
    title: "¿Enviar esta oferta?",
    lines,
    warning: label ? "TU DINOSAURIO SALE DE LA BÓVEDA AL ENVIAR" : null,
    confirmLabel: "Enviar oferta",
  };
}

/* ──────────────────────────── the empty states ──────────────────────────── */

// Nothing in the window. The two cases are NOT the same fact and must not share
// a sentence: a board nobody has published to is an invitation, and a filter
// that hid everything is a filter.
export function boardEmptyState({ board, mineOnly } = {}) {
  const b = board || {};
  if (b.ok === false) {
    return {
      headline: "No pudimos leer los intercambios.",
      body: "Actualiza la página. Tus dinosaurios no se han movido.",
    };
  }
  if (mineOnly) {
    return {
      headline: "No tienes ningún dinosaurio publicado para intercambio.",
      body: "Publica uno y aparecerá aquí, en el Mercado, junto a los que están a "
        + "la venta. No sale de tu bóveda mientras espera.",
    };
  }
  return {
    headline: "Nadie ha publicado un dinosaurio para intercambio todavía.",
    body: "Publica el tuyo y cualquiera podrá ofrecerte el suyo desde esta misma "
      + "página, sin escribirle a nadie.",
  };
}
