import React, { useEffect, useRef, useState } from "react";
import {
  ArrowLeftRight, Clock, Inbox, Send, History, Crown, AlertTriangle, Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { SkeletonCard } from "@/components/common/PageLoader";
import { fmtCoin, intOrNull, newRequestId, attemptSettled } from "@/lib/marketPricing";
import {
  effectiveCooldownLeft, escrowNotice, cooldownNotice, moveCooldownNotice,
  reservedSlotsNotice, cooldownBanner, acceptConfirm, closeConfirm, expiryState,
  actionState, statusLabel, statusNote, itemLabel, sideValue, bandVerdict,
  networkRefusal, pluralEs,
} from "@/lib/tradeRules";

// "MIS OFERTAS" — the inbox half of Intercambios, now a tab of the Mercado
// rather than a page of its own.
//
// This is the offer surface lifted OUT of @/pages/Trades, unchanged in
// behaviour: the same three lists, the same three surprising rules stated
// before anything is clicked, the same confirmation copy from @/lib/tradeRules.
// What went away with the page was the part the owner asked us to remove — the
// "look a player up and type their dinosaur's number" flow. Offers are made on
// the market grid now, on the card of the animal being asked for.
//
// It decides nothing itself. Every rule it renders comes from GET
// /api/trade/config, read by the parent and handed down as `cfg`.

/* ─────────────────────────────── chrome ─────────────────────────────── */

function Panel({ children, className = "", ...rest }) {
  return (
    <div className={`glass rounded-2xl p-4 sm:p-5 ${className}`} {...rest}>{children}</div>
  );
}

export function Notice({ tone = "muted", icon, children, testid }) {
  const tones = {
    muted: "border-white/10 text-muted-foreground",
    gold: "border-gold/40 text-gold",
    warn: "border-orange-400/40 text-orange-300",
    danger: "border-crimson/40 text-crimson",
  };
  return (
    <div
      className={`flex items-start gap-2.5 rounded-xl border px-3 py-2.5 text-[13px] leading-snug ${tones[tone] || tones.muted}`}
      data-testid={testid}
    >
      {icon ? <span className="shrink-0 mt-0.5">{icon}</span> : null}
      <span className="min-w-0 break-words">{children}</span>
    </div>
  );
}

/* ─────────────────────────── one offer card ─────────────────────────── */

// The TTL clock. One interval per open card, cleared on unmount; a card that is
// not pending does not run a timer at all, because its clock cannot change.
function useExpiry(iso, live) {
  const [state, setState] = useState(() => expiryState(iso));
  useEffect(() => {
    setState(expiryState(iso));
    if (!live) return undefined;
    const t = setInterval(() => setState(expiryState(iso)), 1000);
    return () => clearInterval(t);
  }, [iso, live]);
  return state;
}

function ItemList({ items, label, testid }) {
  const value = sideValue(items);
  return (
    <div className="min-w-0" data-testid={testid}>
      <p className="label-overline text-[10px] text-muted-foreground mb-1.5">{label}</p>
      {items.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">—</p>
      ) : (
        <ul className="space-y-1">
          {items.map((it, i) => (
            <li key={`${it.dinoId}-${i}`} className="text-[13px] leading-snug break-words">
              {it.prime && <Crown size={11} className="inline mr-1 text-gold" aria-hidden />}
              {itemLabel(it)}
              {it.dinoId !== null && (
                <span className="text-muted-foreground text-[11px]"> · nº {it.dinoId}</span>
              )}
              {/* A per-animal pricing failure is why the whole offer would be
                  refused at 503, so it is shown on the animal it belongs to. */}
              {it.valueError && (
                <span className="block text-[11px] text-crimson">{it.valueError}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {value.total !== null && items.length > 0 && (
        <p className="text-[11px] text-muted-foreground mt-1 tabular-nums">
          Valor: {fmtCoin(value.total)} PrimeMeat
        </p>
      )}
    </div>
  );
}

function OfferCard({ offer, mine, cfg, busyId, onAccept, onDecline, onCancel }) {
  const live = offer.status === "pending";
  const exp = useExpiry(offer.expiresAt, live);
  const act = actionState(offer, exp, mine, cfg);
  const busy = busyId === offer.id;
  const verdict = bandVerdict(offer.offerValue, offer.wantValue, offer.symmetryPct);
  const note = statusNote(offer);
  const other = offer.direction === "incoming" ? offer.fromName : offer.toName;

  return (
    <Panel data-testid={`trade-offer-${offer.id}`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-3">
        <span className="font-display font-bold text-sm break-words min-w-0">
          {offer.direction === "incoming" ? `${other} te ofrece` : `Le ofreciste a ${other}`}
        </span>
        <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full glass shrink-0">
          {statusLabel(offer.status)}
        </span>
        {live && (
          <span
            className={`text-[11px] inline-flex items-center gap-1 tabular-nums shrink-0 ${exp.expired ? "text-crimson font-bold" : "text-muted-foreground"}`}
            data-testid={`trade-expiry-${offer.id}`}
          >
            <Clock size={11} /> {exp.text}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <ItemList
          items={offer.direction === "incoming" ? offer.offerItems : offer.wantItems}
          label={offer.direction === "incoming" ? "Recibes" : "Pides"}
          testid={`trade-in-${offer.id}`}
        />
        <ItemList
          items={offer.direction === "incoming" ? offer.wantItems : offer.offerItems}
          label={offer.direction === "incoming" ? "Entregas" : "Entregaste (retenidos)"}
          testid={`trade-out-${offer.id}`}
        />
      </div>

      {offer.note && (
        <p className="text-[12px] text-muted-foreground mt-3 break-words">«{offer.note}»</p>
      )}
      {verdict && (
        <p
          className={`text-[11px] mt-2 ${verdict.ok ? "text-muted-foreground" : "text-crimson"}`}
          data-testid={`trade-band-${offer.id}`}
        >
          {verdict.text}
        </p>
      )}
      {note && <div className="mt-3"><Notice tone="warn" icon={<AlertTriangle size={14} />}>{note}</Notice></div>}
      {!act.canAct && act.reason && live && (
        <div className="mt-3"><Notice tone="warn" icon={<Clock size={14} />}>{act.reason}</Notice></div>
      )}

      {(offer.canAccept || offer.canCancel) && (
        <div className="flex flex-col sm:flex-row gap-2 mt-4">
          {offer.canAccept && (
            <>
              <button
                onClick={() => onAccept(offer)}
                disabled={busy || !act.canAct}
                data-testid={`trade-accept-${offer.id}`}
                className="flex-1 inline-flex items-center justify-center gap-2 bg-gold text-background font-bold text-sm px-4 py-2.5 rounded-xl hover:brightness-110 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {busy ? <Loader2 size={15} className="animate-spin motion-reduce:animate-none" /> : <ArrowLeftRight size={15} />}
                Aceptar
              </button>
              <button
                onClick={() => onDecline(offer)}
                disabled={busy}
                data-testid={`trade-decline-${offer.id}`}
                className="flex-1 glass font-semibold text-sm px-4 py-2.5 rounded-xl hover:border-crimson/40 transition-colors disabled:opacity-40"
              >
                Rechazar
              </button>
            </>
          )}
          {offer.canCancel && (
            <button
              onClick={() => onCancel(offer)}
              disabled={busy}
              data-testid={`trade-cancel-${offer.id}`}
              className="flex-1 glass font-semibold text-sm px-4 py-2.5 rounded-xl hover:border-crimson/40 transition-colors disabled:opacity-40"
            >
              {busy ? "…" : "Cancelar oferta"}
            </button>
          )}
        </div>
      )}
    </Panel>
  );
}

/* ───────────────────────────── the panel ───────────────────────────── */

export default function TradeOffersPanel({ cfg, mine, mineError, loading, onReload }) {
  const { play } = useSound();
  const [tab, setTab] = useState("incoming");
  const [pending, setPending] = useState(null);     // {kind, offer, copy}
  const [busyId, setBusyId] = useState(null);
  const reqIds = useRef({});

  const m = mine || {};
  const cooldownLeft = effectiveCooldownLeft(m, cfg);
  const mineView = { ...m, cooldownLeft };

  const act = async (kind, offer) => {
    const key = `${kind}:${offer.id}`;
    setBusyId(offer.id);
    if (!reqIds.current[key]) reqIds.current[key] = newRequestId();
    const rid = reqIds.current[key];
    const call = kind === "accept" ? api.tradeAccept
      : kind === "decline" ? api.tradeDecline : api.tradeCancel;
    try {
      const r = await call(offer.id, { client_request_id: rid });
      delete reqIds.current[key];
      play("success");
      if (kind === "accept") {
        toast.success(r.data?.settled === false
          ? "Intercambio aceptado. Estamos terminando de entregar; actualiza en un momento."
          : "¡Intercambio hecho! Los dinosaurios ya están en las bóvedas.");
      } else if (kind === "cancel") {
        toast.success("Oferta cancelada. Tus dinosaurios vuelven a tu bóveda.");
      } else {
        toast.success("Oferta rechazada.");
      }
    } catch (err) {
      // A response of ANY status is a definite outcome, so the next press is a
      // new attempt. No response at all may have landed, so the id is KEPT.
      if (attemptSettled(err)) delete reqIds.current[key];
      play("error");
      toast.error(networkRefusal(err, "No se pudo completar. Actualiza la página."));
    } finally {
      setBusyId(null);
      setPending(null);
      if (onReload) await onReload();
    }
  };

  const banner = cooldownBanner(cooldownLeft, cfg);
  const reserved = reservedSlotsNotice(m);
  const cdNote = cooldownNotice(cfg, "la otra persona");
  const moveNote = moveCooldownNotice(cfg);
  const lists = { incoming: m.incoming || [], outgoing: m.outgoing || [], history: m.history || [] };
  const rows = lists[tab] || [];
  const TABS = [
    { id: "incoming", label: "Recibidas", icon: <Inbox size={14} />, n: lists.incoming.length },
    { id: "outgoing", label: "Enviadas", icon: <Send size={14} />, n: lists.outgoing.length },
    { id: "history", label: "Historial", icon: <History size={14} />, n: lists.history.length },
  ];
  const openCap = intOrNull((cfg || {}).maxOpenOffers);

  return (
    <div data-testid="trade-offers-panel">
      {/* THE THREE SURPRISING RULES, before anything is clicked. */}
      <div className="space-y-2 mb-5">
        {banner && <Notice tone="warn" icon={<Clock size={14} />} testid="trades-cooldown">{banner}</Notice>}
        <Notice tone="gold" icon={<ArrowLeftRight size={14} />} testid="trades-escrow">{escrowNotice(cfg)}</Notice>
        {cdNote && <Notice tone="gold" icon={<Clock size={14} />} testid="trades-cooldown-rule">{cdNote}</Notice>}
        {reserved && <Notice tone="warn" icon={<AlertTriangle size={14} />} testid="trades-reserved">{reserved}</Notice>}
        {moveNote && <Notice icon={<Clock size={14} />} testid="trades-move-rule">{moveNote}</Notice>}
        {mineError && (
          <Notice tone="danger" icon={<AlertTriangle size={14} />} testid="trades-mine-error">
            {mineError}{" "}
            <button onClick={onReload} className="underline font-semibold">Volver a intentar</button>
          </Notice>
        )}
      </div>

      <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => { play("click"); setTab(t.id); }}
            data-testid={`trades-tab-${t.id}`}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-semibold transition-colors shrink-0 ${tab === t.id ? "bg-gold text-background" : "glass text-muted-foreground hover:text-foreground"}`}
          >
            {t.icon} {t.label} <span className="tabular-nums">({t.n})</span>
          </button>
        ))}
      </div>

      {loading ? (
        <SkeletonCard />
      ) : rows.length === 0 ? (
        <Panel className="text-center" data-testid={`trades-empty-${tab}`}>
          <p className="font-display font-bold text-base mb-1">
            {tab === "incoming" ? "Nadie te ha ofrecido un intercambio todavía."
              : tab === "outgoing" ? "No tienes ofertas abiertas."
                : "Todavía no has cerrado ningún intercambio."}
          </p>
          <p className="text-sm text-muted-foreground leading-snug">
            {tab === "incoming"
              ? "Publica un dinosaurio para intercambio y las ofertas llegarán aquí, con lo que entregas y lo que recibes antes de decidir."
              : tab === "outgoing"
                ? `Busca un dinosaurio en Intercambios y pulsa «Ofrecer el mío».${openCap !== null ? ` Puedes tener ${pluralEs(openCap, "oferta abierta", "ofertas abiertas")} a la vez.` : ""}`
                : "Aquí quedarán los intercambios aceptados, rechazados, cancelados y caducados."}
          </p>
        </Panel>
      ) : (
        <div className="space-y-3">
          {rows.map((o) => (
            <OfferCard
              key={o.id}
              offer={o}
              mine={mineView}
              cfg={cfg}
              busyId={busyId}
              onAccept={(x) => setPending({ kind: "accept", offer: x, copy: acceptConfirm({ cfg, offer: x }) })}
              onDecline={(x) => setPending({ kind: "decline", offer: x, copy: closeConfirm({ offer: x, kind: "decline" }) })}
              onCancel={(x) => setPending({ kind: "cancel", offer: x, copy: closeConfirm({ offer: x, kind: "cancel" }) })}
            />
          ))}
        </div>
      )}

      <ConfirmModal
        open={!!pending}
        loading={!!busyId}
        onClose={() => setPending(null)}
        onConfirm={() => pending && act(pending.kind, pending.offer)}
        tone={pending?.kind === "accept" ? "gold" : "danger"}
        icon={<ArrowLeftRight size={28} />}
        title={pending?.copy?.title || ""}
        confirmLabel={pending?.copy?.confirmLabel || "Confirmar"}
        abortLabel="Volver"
        warning={pending?.copy?.warning}
        message={
          <ul className="text-left space-y-2">
            {(pending?.copy?.lines || []).map((l, i) => (
              <li key={i} className="leading-snug break-words">· {l}</li>
            ))}
          </ul>
        }
      />
    </div>
  );
}
