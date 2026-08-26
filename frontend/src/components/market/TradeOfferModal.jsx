import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowLeftRight, X, Send, AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { Notice } from "@/components/market/TradeOffersPanel";
import { fmtCoin, readQuote, newRequestId, attemptSettled } from "@/lib/marketPricing";
import {
  heldDinoIds, vaultTradeOptions, offerEmptyState, escrowNotice, networkRefusal,
} from "@/lib/tradeRules";
import {
  cardOfferBlockReason, cardOfferConfirm, cardBandLine, pickVerdict, cardValueLine,
} from "@/lib/tradeBoard";

// "OFRECER EL MÍO" — an offer made ON A CARD, which is the whole point of the
// redesign.
//
// WHAT IS NOT IN HERE, and its absence is the feature: there is no player
// search, and there is no field to type the other player's dinosaur number
// into. The card the button was pressed on IS the address. `showcase_id` goes
// to the server and the server reads both the counterparty and the wanted
// animal off that card, so the number this page used to demand players obtain
// by messaging each other is never needed and never shown.
//
// ONE ANIMAL, because a card is one animal: the server's own N-for-N rule makes
// 1-for-1 the only shape an offer on a card can take, so the picker is a single
// choice rather than a checklist that can build a refusal.
//
// NO COINS. There is no coin field here and no place for one — see
// @/lib/tradeRules.

export default function TradeOfferModal({ card, cfg, mine, onClose, onDone }) {
  const { play } = useSound();
  const reduce = useReducedMotion();
  const [vault, setVault] = useState(null);            // null = still loading
  const [vaultError, setVaultError] = useState(null);
  const [picked, setPicked] = useState(null);          // ONE dino id, or null
  const [note, setNote] = useState("");
  const [quotes, setQuotes] = useState({});            // dino id -> int | "error"
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const reqIdRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    api.meVault()
      .then((r) => { if (!cancelled) { setVault(r.data?.dinos || []); setVaultError(null); } })
      .catch((err) => {
        if (cancelled) return;
        setVault([]);
        setVaultError(networkRefusal(err, "No pudimos leer tu bóveda. Actualiza la página."));
      });
    return () => { cancelled = true; };
  }, []);

  const held = useMemo(() => heldDinoIds(mine), [mine]);
  const options = useMemo(
    () => vaultTradeOptions(vault || [], cfg, held), [vault, cfg, held]);
  const empty = vault === null ? null : offerEmptyState(options, cfg);

  // ONE quote for the ONE picked animal, cached by id so re-picking never
  // refetches. This is the market's own /market/suggested-price — the SAME
  // `_merit` integer the server bands a trade against — so the number shown
  // here and the number the refusal would quote are one number.
  useEffect(() => {
    if (picked === null || quotes[picked] !== undefined) return undefined;
    let cancelled = false;
    const opt = options.find((o) => o.id === picked);
    api.marketSuggestedPrice({ dino_id: picked, species: opt ? opt.species : "" })
      .then((r) => {
        if (cancelled) return;
        const v = readQuote(r.data).suggested;
        setQuotes((q) => ({ ...q, [picked]: v === null ? "error" : v }));
      })
      .catch(() => { if (!cancelled) setQuotes((q) => ({ ...q, [picked]: "error" })); });
    return () => { cancelled = true; };
  }, [picked, options, quotes]);

  const myValue = typeof quotes[picked] === "number" ? quotes[picked] : null;
  const pickedOpt = picked === null ? null : options.find((o) => o.id === picked) || null;
  const block = cardOfferBlockReason({
    cfg, mine, card, offerIds: picked === null ? [] : [picked],
  });
  const verdict = pickVerdict(card, myValue, (cfg || {}).symmetryPct);
  const band = cardBandLine(card, (cfg || {}).symmetryPct);
  const worth = cardValueLine(card);
  const confirm = cardOfferConfirm({ cfg, card, item: pickedOpt || {} });

  const submit = async () => {
    setBusy(true);
    if (!reqIdRef.current) reqIdRef.current = newRequestId();
    const rid = reqIdRef.current;
    try {
      await api.tradeOffer({
        showcase_id: card.id,
        offer: [picked],
        note: note.trim() || null,
        client_request_id: rid,
      });
      reqIdRef.current = null;
      play("success");
      toast.success("Oferta enviada. Tu dinosaurio queda retenido hasta que se cierre.");
      setConfirming(false);
      onDone();
    } catch (err) {
      // A response of ANY status is a definite outcome, so the next press is a
      // new attempt. No response at all may have landed, so the id is KEPT and
      // the next press replays it rather than escrowing a second time.
      if (attemptSettled(err)) reqIdRef.current = null;
      play("error");
      toast.error(networkRefusal(err, "No se pudo enviar la oferta. Vuelve a intentarlo."));
      setConfirming(false);
    } finally { setBusy(false); }
  };

  return (
    // z-[110] and NOT the market modal's z-[100000]: ConfirmModal portals to
    // <body> at z-[120], so a higher wrapper here would bury the confirmation
    // step behind its own parent — the one step that must never be skippable.
    <div className="fixed inset-0 z-[110] flex items-start sm:items-center justify-center p-3 sm:p-4 overflow-y-auto" data-testid="trade-offer-modal">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={busy ? undefined : onClose} />
      <motion.div
        initial={reduce ? false : { scale: 0.96, y: 16, opacity: 0 }}
        animate={reduce ? {} : { scale: 1, y: 0, opacity: 1 }}
        transition={{ duration: 0.2 }}
        className="relative glass-strong rounded-2xl w-full max-w-lg p-5 sm:p-6 my-4 max-h-[94vh] overflow-y-auto"
      >
        <button onClick={onClose} disabled={busy} className="absolute top-4 right-4 p-2 rounded-lg hover:bg-white/10 disabled:opacity-40" aria-label="Cerrar">
          <X size={18} />
        </button>
        <h3 className="font-display font-bold text-xl sm:text-2xl mb-1 pr-10">Ofrecer un intercambio</h3>
        <p className="text-sm text-muted-foreground mb-4">
          Dinosaurio por dinosaurio, sin PrimeMeat de por medio.
        </p>

        {/* 1. WHAT YOU ARE ASKING FOR — the card, restated, so the offer is
            made against something the player can still see. */}
        <div className="glass rounded-xl px-3 py-3 mb-4" data-testid="trade-offer-target">
          <p className="label-overline text-[10px] text-muted-foreground mb-1">Pides</p>
          <p className="font-display font-bold text-[15px] leading-snug break-words">
            {card.title || card.dinoName}
          </p>
          <p className="text-[12px] text-muted-foreground leading-snug break-words">
            de {card.ownerName || "otro jugador"}
            {card.growthPct !== null ? ` · Crecimiento ${card.growthPct}%` : ""}
            {card.mutations !== null ? ` · ${card.mutations} mutaciones` : ""}
          </p>
          {worth && <p className="text-[12px] text-gold mt-1 tabular-nums">{worth}</p>}
          {card.note && <p className="text-[12px] text-muted-foreground mt-1 break-words">«{card.note}»</p>}
        </div>

        <div className="mb-4"><Notice tone="gold" icon={<AlertTriangle size={14} />} testid="trade-escrow-notice">
          {escrowNotice(cfg)}
        </Notice></div>

        {/* 2. WHAT YOU GIVE — one of yours. */}
        <div className="mb-4">
          <span className="label-overline text-[10px] text-muted-foreground block mb-1.5">
            Qué ofreces a cambio
          </span>
          {vault === null ? (
            <p className="text-sm text-muted-foreground py-3">Cargando tu bóveda…</p>
          ) : vaultError ? (
            <Notice tone="danger" icon={<AlertTriangle size={14} />}>{vaultError}</Notice>
          ) : empty ? (
            <div className="py-2 space-y-1.5" data-testid="trade-offer-empty">
              <p className="font-display font-bold text-[15px] leading-snug">{empty.headline}</p>
              <p className="text-[13px] text-muted-foreground leading-snug">{empty.body}</p>
              {empty.biggest && <p className="text-[13px] text-gold leading-snug">{empty.biggest}</p>}
            </div>
          ) : (
            <ul className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {options.map((o) => (
                <li key={o.key}>
                  <label className={`flex items-start gap-2.5 rounded-lg px-3 py-2 text-[13px] leading-snug ${o.eligible ? "glass cursor-pointer hover:border-gold/40" : "opacity-50 cursor-not-allowed"}`}>
                    <input
                      type="radio"
                      name="trade-offer-pick"
                      className="mt-0.5 shrink-0 accent-[#7CA842]"
                      disabled={!o.eligible}
                      checked={picked === o.id}
                      onChange={() => {
                        // A different animal is a DIFFERENT attempt: carrying
                        // the old id over would let a replay hand back the
                        // previous selection's stored result.
                        reqIdRef.current = null;
                        setPicked(o.id);
                      }}
                      data-testid={`trade-pick-${o.id}`}
                    />
                    <span className="min-w-0 break-words">
                      {o.label}
                      {!o.eligible && o.blockReason && (
                        <span className="block text-[11px] text-muted-foreground">— {o.blockReason}</span>
                      )}
                      {picked === o.id && quotes[o.id] === "error" && (
                        <span className="block text-[11px] text-crimson">
                          No pudimos calcular su valor. Elige otro o inténtalo más tarde.
                        </span>
                      )}
                      {picked === o.id && typeof quotes[o.id] === "number" && (
                        <span className="block text-[11px] text-muted-foreground tabular-nums">
                          {fmtCoin(quotes[o.id])} PrimeMeat
                        </span>
                      )}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          {/* The band BEFORE a pick (what would be accepted at all), the verdict
              AFTER one (whether this particular animal is). Never both. */}
          {picked === null
            ? band && <p className="text-[12px] text-gold mt-2 leading-snug" data-testid="trade-band-line">{band}</p>
            : verdict && (
              <p className={`text-[12px] mt-2 leading-snug ${verdict.ok ? "text-muted-foreground" : "text-crimson"}`} data-testid="trade-pick-verdict">
                {verdict.text}
              </p>
            )}
        </div>

        <label className="block mb-4">
          <span className="label-overline text-[10px] text-muted-foreground block mb-1.5">Nota (opcional)</span>
          <input
            className="w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={60}
            placeholder="Ejemplo: te cambio mi Rex por tu Deino"
            data-testid="trade-note"
          />
        </label>

        {block && (
          <div className="mb-3"><Notice tone="warn" icon={<AlertTriangle size={14} />} testid="trade-block-reason">{block}</Notice></div>
        )}

        <button
          onClick={() => { play("click"); setConfirming(true); }}
          disabled={!!block || busy || picked === null}
          data-testid="trade-send"
          className="w-full inline-flex items-center justify-center gap-2 bg-gold text-background font-bold px-4 py-3 rounded-xl hover:brightness-110 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? <Loader2 size={16} className="animate-spin motion-reduce:animate-none" /> : <Send size={16} />}
          Revisar y enviar
        </button>

        <ConfirmModal
          open={confirming}
          loading={busy}
          onClose={() => setConfirming(false)}
          onConfirm={submit}
          tone="gold"
          icon={<ArrowLeftRight size={28} />}
          title={confirm.title}
          confirmLabel={confirm.confirmLabel}
          abortLabel="Volver"
          warning={confirm.warning}
          message={
            <ul className="text-left space-y-2">
              {confirm.lines.map((l, i) => (
                <li key={i} className="leading-snug break-words">· {l}</li>
              ))}
            </ul>
          }
        />
      </motion.div>
    </div>
  );
}
