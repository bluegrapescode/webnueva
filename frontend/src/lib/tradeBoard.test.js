/**
 * @jest-environment node
 */
// THE TRADE BOARD GATE — the rules of trading on the market surface, proven
// without a browser.
//
// Every case here is a rule the SERVER also enforces (server.py: the board
// routes, `_trade_board_public`, `trade_create`'s `showcase_id` lane). This
// file exists to prove the page refuses the same things for the same reasons,
// because a page that lets a player build an offer the server will refuse is a
// page that wastes an animal's worth of hope on every click.
//
// The pins that this module contains no typed knob default and no glyph the
// site's font cannot draw live in tradeRules.test.js, which reads this file by
// name.

import {
  readBoardCard, readBoard, cardStatusLine, cardValueLine, publishBlockReason,
  alreadyOnBoard, publishConfirm, closeCardConfirm, cardOfferBlockReason,
  cardBandLine, pickVerdict, cardOfferConfirm, boardEmptyState,
} from "@/lib/tradeBoard";
import { readTradeConfig, readMine } from "@/lib/tradeRules";

// The shipped config as GET /api/trade/config answers it. Tests that care about
// a rule being ABSENT delete it from a copy — they never type a different one.
const RAW = Object.freeze({
  enabled: true,
  max_items_per_side: 3,
  symmetry_pct: 25,
  max_open_offers: 5,
  growth_gate: true,
  min_growth_pct: 80,
  max_board_per_player: 3,
  cooldown_secs: 60 * 60 * 24,
  offer_ttl_secs: 60 * 60 * 48,
  dino_move_cooldown_secs: 60 * 60 * 24,
  my_cooldown_left: 0,
});
const CFG = readTradeConfig(RAW);
// One rule changed or removed, every other rule intact. Handing in a stripped
// payload instead would prove `configBlockReason` fires, which is tradeRules'
// test, not this one.
const cfgWith = (over, ...drop) => {
  const next = { ...RAW, ...over };
  for (const k of drop) delete next[k];
  return readTradeConfig(next);
};

// One card as _trade_board_public publishes it to somebody who is NOT its owner.
const CARD = Object.freeze({
  id: "card-1",
  type: "trade",
  title: "Rex Titán",
  note: "busco Deino",
  seller_name: "Nubla",
  seller_id: null,
  species: "Tyrannosaurus",
  dino_name: "Tyrannosaurus Rex",
  growth_pct: 100,
  priced_mutations: 12,
  mutations_count: 12,
  prime: true,
  is_elder: false,
  value: 5800000,
  mine: false,
  offered: false,
  offers: 0,
  dino_id: null,
  ends_at: "2026-08-14T00:00:00+00:00",
  created_at: "2026-08-11T00:00:00+00:00",
});

const EMPTY_MINE = readMine(null);
const board = (over) => ({
  ok: true, cards: [], maxPerPlayer: 3, ttlSecs: 60 * 60 * 72, ttlError: null, mine: 0, ...over,
});
const option = (over) => ({
  id: 7, key: "vault:7", species: "Deinosuchus", name: "", growthPct: 95,
  mutations: 4, prime: false, eligible: true, blockReason: null,
  label: "Deinosuchus · 95% · 4 mutaciones", ...over,
});

/* ───────────────────────────── reading a card ───────────────────────────── */

describe("readBoardCard", () => {
  test("a full card reads every field the grid needs", () => {
    const c = readBoardCard(CARD);
    expect(c.id).toBe("card-1");
    expect(c.type).toBe("trade");
    expect(c.title).toBe("Rex Titán");
    expect(c.ownerName).toBe("Nubla");
    expect(c.species).toBe("Tyrannosaurus");
    expect(c.growthPct).toBe(100);
    expect(c.mutations).toBe(12);
    expect(c.prime).toBe(true);
    expect(c.value).toBe(5800000);
    expect(c.note).toBe("busco Deino");
    expect(c.raw).toBe(CARD);
  });

  test("★ SOMEBODY ELSE'S CARD NEVER CARRIES THE ROW NUMBER", () => {
    // The whole defect this redesign closes was that a player had to obtain
    // this number by messaging the owner. Broadcasting it would be the lazy
    // way to close it, and the server does not publish it either.
    expect(readBoardCard(CARD).dinoId).toBeNull();
  });

  test("my OWN card does carry it, because it is my animal", () => {
    expect(readBoardCard({ ...CARD, mine: true, dino_id: 52 }).dinoId).toBe(52);
  });

  test("mine/offered are only true when the server said true", () => {
    const c = readBoardCard({ ...CARD, mine: "yes", offered: 1 });
    expect(c.mine).toBe(false);
    expect(c.offered).toBe(false);
  });

  test("a nonsense payload reads as an empty card rather than throwing", () => {
    for (const junk of [null, undefined, 5, "card", [], { id: {} }]) {
      const c = readBoardCard(junk);
      expect(c.type).toBe("trade");
      expect(c.value).toBeNull();
      expect(c.offers).toBe(0);
    }
  });

  test("a negative offer count clamps to zero", () => {
    expect(readBoardCard({ ...CARD, offers: -4 }).offers).toBe(0);
  });

  test("mutations fall back to mutations_count when priced_mutations is absent", () => {
    const { priced_mutations, ...rest } = CARD;
    expect(readBoardCard(rest).mutations).toBe(12);
  });
});

describe("readBoard", () => {
  test("a real payload reads ok, with the cap and the TTL", () => {
    const b = readBoard({ cards: [CARD], max_per_player: 3, ttl_secs: 100, ttl_secs_error: null });
    expect(b.ok).toBe(true);
    expect(b.cards).toHaveLength(1);
    expect(b.maxPerPlayer).toBe(3);
    expect(b.ttlSecs).toBe(100);
    expect(b.mine).toBe(0);
  });

  test("★ A FAILED READ IS NOT AN EMPTY BOARD", () => {
    // They look identical on screen and they are not the same fact: one is an
    // invitation to publish, the other is an apology.
    const b = readBoard(null);
    expect(b.ok).toBe(false);
    expect(b.cards).toEqual([]);
  });

  test("a payload with no cards array is not ok either", () => {
    expect(readBoard({ max_per_player: 3 }).ok).toBe(false);
  });

  test("the TTL error is carried, and the number is null beside it", () => {
    const b = readBoard({ cards: [], ttl_secs: null, ttl_secs_error: "está mal configurada" });
    expect(b.ttlSecs).toBeNull();
    expect(b.ttlError).toBe("está mal configurada");
  });

  test("it counts MY cards", () => {
    const b = readBoard({ cards: [CARD, { ...CARD, id: "c2", mine: true }] });
    expect(b.mine).toBe(1);
  });
});

/* ───────────────────────────── the two lines ───────────────────────────── */

describe("cardStatusLine", () => {
  test("my own card, with nothing yet", () => {
    expect(cardStatusLine(readBoardCard({ ...CARD, mine: true })))
      .toBe("Publicado por ti. Nadie ha ofrecido todavía.");
  });
  test("my own card, with offers, in Spanish singular", () => {
    expect(cardStatusLine(readBoardCard({ ...CARD, mine: true, offers: 1 })))
      .toContain("1 oferta ");
    expect(cardStatusLine(readBoardCard({ ...CARD, mine: true, offers: 3 })))
      .toContain("3 ofertas ");
  });
  test("a card I already offered on says so, and outranks the count", () => {
    expect(cardStatusLine(readBoardCard({ ...CARD, offered: true, offers: 2 })))
      .toBe("Ya enviaste una oferta por este dinosaurio.");
  });
  test("somebody else's quiet card says nothing at all", () => {
    expect(cardStatusLine(readBoardCard(CARD))).toBeNull();
  });
});

describe("cardValueLine", () => {
  test("it quotes the owner's own worked example to the coin", () => {
    expect(cardValueLine(readBoardCard(CARD))).toBe("Vale unos 5.800.000 PrimeMeat");
  });
  test("an unpriced card quotes NOTHING rather than zero", () => {
    expect(cardValueLine(readBoardCard({ ...CARD, value: null }))).toBeNull();
  });
});

/* ──────────────────────────── publishing a card ──────────────────────────── */

describe("publishBlockReason", () => {
  test("nothing is wrong -> null", () => {
    expect(publishBlockReason({ cfg: CFG, board: board(), option: option() })).toBeNull();
  });

  test("trades switched off blocks it, with the server's sentence", () => {
    const off = cfgWith({ enabled: false });
    expect(publishBlockReason({ cfg: off, board: board(), option: option() }))
      .toBe("Los intercambios están desactivados por ahora.");
  });

  test("★ A BROKEN TTL KNOB BLOCKS THE BUTTON", () => {
    // It is a REFUSE knob on the server: every publish would 503. A button that
    // stays live on a rule the server cannot read is a button that lies.
    const msg = "La duración de las publicaciones de intercambio está mal configurada";
    expect(publishBlockReason({ cfg: CFG, board: board({ ttlError: msg }), option: option() }))
      .toBe(msg);
  });

  test("the cap is quoted with the server's own number", () => {
    const r = publishBlockReason({ cfg: CFG, board: board({ mine: 3 }), option: option() });
    expect(r).toContain("3 dinosaurios publicados");
  });

  test("the cap comes from the BOARD payload, and falls back to the config", () => {
    const b = board({ maxPerPlayer: null, mine: 3 });
    expect(publishBlockReason({ cfg: CFG, board: b, option: option() })).toContain("3");
  });

  test("no cap published anywhere blocks nobody", () => {
    const noCap = cfgWith({}, "max_board_per_player");
    expect(publishBlockReason({ cfg: noCap, board: board({ maxPerPlayer: null, mine: 9 }),
                                option: option() })).toBeNull();
  });

  test("nothing picked", () => {
    expect(publishBlockReason({ cfg: CFG, board: board(), option: null }))
      .toBe("Elige un dinosaurio para publicar.");
  });

  test("an ineligible animal quotes the picker's own reason", () => {
    const o = option({ eligible: false, blockReason: "no se puede intercambiar (mínimo 80%)" });
    expect(publishBlockReason({ cfg: CFG, board: board(), option: o }))
      .toBe("Ese dinosaurio no se puede intercambiar (mínimo 80%).");
  });

  test("an ineligible animal with no reason still refuses", () => {
    const o = option({ eligible: false, blockReason: null });
    expect(publishBlockReason({ cfg: CFG, board: board(), option: o }))
      .toBe("Ese dinosaurio no se puede intercambiar ahora mismo.");
  });

  test("★ THE SAME ANIMAL CANNOT BE PUBLISHED TWICE", () => {
    const mineCard = readBoardCard({ ...CARD, mine: true, dino_id: 7 });
    const b = board({ cards: [mineCard], mine: 1 });
    expect(publishBlockReason({ cfg: CFG, board: b, option: option({ id: 7 }) }))
      .toBe("Ese dinosaurio ya está publicado para intercambio.");
    expect(publishBlockReason({ cfg: CFG, board: b, option: option({ id: 8 }) })).toBeNull();
  });
});

describe("alreadyOnBoard", () => {
  test("only MY cards can answer it — theirs never carry a row number", () => {
    const theirs = readBoardCard({ ...CARD, mine: false, dino_id: 7 });
    expect(alreadyOnBoard(board({ cards: [theirs] }), option({ id: 7 }))).toBe(false);
  });
  test("an option with no id is not on the board", () => {
    expect(alreadyOnBoard(board(), option({ id: null }))).toBe(false);
  });
});

describe("publishConfirm", () => {
  test("★ IT SAYS THE ANIMAL DOES NOT MOVE", () => {
    const c = publishConfirm({ cfg: CFG, board: board(), option: option() });
    expect(c.title).toBe("¿Publicarlo para intercambio?");
    expect(c.lines.join(" ")).toContain("No sale de tu bóveda");
    expect(c.lines.join(" ")).toContain("Deinosuchus");
    expect(c.warning).toBeNull();     // nothing moves, so nothing is shouted
  });
  test("it states when the card comes down, from the board's own TTL", () => {
    expect(publishConfirm({ cfg: CFG, board: board(), option: option() }).lines.join(" "))
      .toContain("se retira sola en 72 h");
  });
  test("a TTL the server did not publish is NOT guessed", () => {
    const lines = publishConfirm({ cfg: CFG, board: board({ ttlSecs: null }), option: option() }).lines;
    expect(lines.join(" ")).not.toContain("se retira sola");
  });
  test("it distinguishes publishing from spending the daily trade", () => {
    expect(publishConfirm({ cfg: CFG, board: board(), option: option() }).lines.join(" "))
      .toContain("Publicar no gasta tu intercambio del día");
  });
});

describe("closeCardConfirm", () => {
  test("it promises the animal never left", () => {
    const c = closeCardConfirm(readBoardCard({ ...CARD, mine: true }));
    expect(c.lines.join(" ")).toContain("nunca salió de tu bóveda");
  });
  test("★ IT WARNS THAT OPEN OFFERS SURVIVE THE CARD", () => {
    // They hold somebody else's animals in escrow. Voiding them silently
    // because the window closed would make a third party pay for it.
    const c = closeCardConfirm(readBoardCard({ ...CARD, mine: true, offers: 2 }));
    expect(c.lines.join(" ")).toContain("siguen");
    expect(c.lines.join(" ")).toContain("retenidos");
  });
  test("with no offers it does not invent any", () => {
    const c = closeCardConfirm(readBoardCard({ ...CARD, mine: true }));
    expect(c.lines.join(" ")).not.toContain("retenidos");
  });
});

/* ────────────────────── offering on somebody's card ────────────────────── */

describe("cardOfferBlockReason", () => {
  const card = readBoardCard(CARD);

  test("one of mine picked, nothing wrong -> null", () => {
    expect(cardOfferBlockReason({ cfg: CFG, mine: EMPTY_MINE, card, offerIds: [7] })).toBeNull();
  });

  test("a card that vanished under the page", () => {
    expect(cardOfferBlockReason({ cfg: CFG, mine: EMPTY_MINE, card: {}, offerIds: [7] }))
      .toContain("ya no está disponible");
  });

  test("my own card is not something I can offer on", () => {
    const own = readBoardCard({ ...CARD, mine: true });
    expect(cardOfferBlockReason({ cfg: CFG, mine: EMPTY_MINE, card: own, offerIds: [7] }))
      .toBe("Esa publicación es tuya.");
  });

  test("★ A SECOND OFFER ON THE SAME CARD IS REFUSED HERE", () => {
    // The server refuses it too (one open offer per card per sender); without
    // this the second press escrows a second animal before finding out.
    const done = readBoardCard({ ...CARD, offered: true });
    expect(cardOfferBlockReason({ cfg: CFG, mine: EMPTY_MINE, card: done, offerIds: [7] }))
      .toContain("Ya tienes una oferta abierta");
  });

  test("★ A CARD IS ONE ANIMAL, SO AN OFFER ON IT IS ONE ANIMAL", () => {
    expect(cardOfferBlockReason({ cfg: CFG, mine: EMPTY_MINE, card, offerIds: [7, 8] }))
      .toBe("Un intercambio es 1 por 1: puedes ofrecer un dinosaurio por este.");
  });

  test("nothing picked yet", () => {
    expect(cardOfferBlockReason({ cfg: CFG, mine: EMPTY_MINE, card, offerIds: [] }))
      .toContain("al menos un dinosaurio");
  });

  test("it delegates the cooldown to tradeRules rather than re-deciding it", () => {
    const cooling = cfgWith({ my_cooldown_left: 3600 });
    const r = cardOfferBlockReason({ cfg: cooling, mine: EMPTY_MINE, card, offerIds: [7] });
    expect(r).toContain("Ya intercambiaste hace poco");
  });

  test("it delegates the open-offer cap too", () => {
    const mine = readMine({ incoming: [], outgoing: [{ id: "a" }, { id: "b" }, { id: "c" },
                                                     { id: "d" }, { id: "e" }], history: [] });
    expect(cardOfferBlockReason({ cfg: CFG, mine, card, offerIds: [7] }))
      .toContain("5 ofertas abiertas");
  });
});

describe("the fairness band, on a card", () => {
  const card = readBoardCard(CARD);          // worth 5.800.000

  test("★ THE BAND IS STATED BEFORE ANYTHING IS PICKED", () => {
    // 25% band on 5.800.000 -> 4.350.000 .. 7.733.333, and the sentence is
    // rewritten from the sender's point of view.
    const line = cardBandLine(card, 25);
    expect(line).toContain("4.350.000");
    expect(line).toContain("7.733.333");
    expect(line).toContain("lo que ofrezcas");
  });

  test("an unpriced card states no band at all", () => {
    expect(cardBandLine(readBoardCard({ ...CARD, value: null }), 25)).toBeNull();
  });

  test("a missing band knob states nothing rather than guessing", () => {
    expect(cardBandLine(card, null)).toBeNull();
  });

  test("a pick inside the band reads as balanced", () => {
    const v = pickVerdict(card, 5000000, 25);
    expect(v.ok).toBe(true);
    expect(v.text).toContain("5.000.000");
  });

  test("a pick below the band is refused, with both numbers", () => {
    const v = pickVerdict(card, 1000000, 25);
    expect(v.ok).toBe(false);
    expect(v.text).toContain("1.000.000");
    expect(v.text).toContain("5.800.000");
  });

  test("★ THE EXACT EDGE IS INSIDE, and one coin under is not", () => {
    // The server's own inequality: lo * 100 >= (100 - pct) * hi.
    expect(pickVerdict(card, 4350000, 25).ok).toBe(true);
    expect(pickVerdict(card, 4349999, 25).ok).toBe(false);
  });

  test("a band of 0 means exactly equal", () => {
    expect(pickVerdict(card, 5800000, 0).ok).toBe(true);
    expect(pickVerdict(card, 5799999, 0).ok).toBe(false);
  });

  test("a band of 100 accepts anything", () => {
    expect(pickVerdict(card, 1, 100).ok).toBe(true);
  });

  test("an unknown side gives no verdict at all", () => {
    expect(pickVerdict(card, null, 25)).toBeNull();
    expect(pickVerdict(readBoardCard({ ...CARD, value: null }), 100, 25)).toBeNull();
  });
});

describe("cardOfferConfirm", () => {
  const card = readBoardCard(CARD);
  const item = { species: "Deinosuchus", growthPct: 95, mutations: 4 };

  test("★ THE ESCROW IS THE HEADLINE", () => {
    const c = cardOfferConfirm({ cfg: CFG, card, item });
    expect(c.warning).toBe("TU DINOSAURIO SALE DE LA BÓVEDA AL ENVIAR");
    expect(c.lines[0]).toContain("Sale de tu bóveda AHORA");
    expect(c.lines[0]).toContain("Deinosuchus");
  });

  test("it says the OTHER side is not frozen", () => {
    expect(cardOfferConfirm({ cfg: CFG, card, item }).lines.join(" "))
      .toContain("NO se congela");
  });

  test("it names the owner it is addressed to", () => {
    expect(cardOfferConfirm({ cfg: CFG, card, item }).lines.join(" ")).toContain("Nubla");
  });

  test("a TTL the server did not publish is not quoted", () => {
    const noTtl = cfgWith({}, "offer_ttl_secs");
    expect(cardOfferConfirm({ cfg: noTtl, card, item }).lines.join(" "))
      .not.toContain("caduca sola");
  });

  test("with nothing picked there is no escrow warning to shout", () => {
    expect(cardOfferConfirm({ cfg: CFG, card, item: {} }).warning).toBeTruthy();
  });
});

/* ───────────────────────────── the empty states ───────────────────────────── */

describe("boardEmptyState", () => {
  test("a board nobody has published to invites publishing", () => {
    const e = boardEmptyState({ board: board(), mineOnly: false });
    expect(e.headline).toContain("Nadie ha publicado");
    expect(e.body).toContain("sin escribirle a nadie");
  });
  test("my own empty shelf says something different", () => {
    expect(boardEmptyState({ board: board(), mineOnly: true }).headline)
      .toContain("No tienes ningún dinosaurio publicado");
  });
  test("★ A BOARD WE COULD NOT READ APOLOGISES, IT DOES NOT INVITE", () => {
    const e = boardEmptyState({ board: readBoard(null), mineOnly: false });
    expect(e.headline).toContain("No pudimos leer");
    expect(e.body).toContain("no se han movido");
  });
});
