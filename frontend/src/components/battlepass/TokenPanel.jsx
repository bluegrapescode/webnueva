import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { X, Loader2, Package, Radio, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import { GOLD } from "@/components/battlepass/RewardCard";

const LIVE_WAIT_MS = 20000;

// Exported: the /my-dino equipment panel renders the same tokens with the same
// modal (owner ask 2026-08-07: "everything should go here").
export const tokenArt = (kind) => (kind === "diet" ? "/tokens/diet.png" : "/tokens/growth.png");
export const tokenName = (kind) => (kind === "diet" ? "Token de Dieta" : "Token de Crecimiento");
export const tokenEffect = (kind, tier) => (kind === "diet" ? (tier === "premium" ? "Dino EN VIVO: dieta al 300%" : "Dino EN VIVO: +150% de dieta — dos llegan al 300%") : "Dino EN VIVO: crece al 70% + comida al 100%");
export const tierLabel = (tier) => (tier === "premium" ? "PREMIUM" : "BÁSICO");
export const tokenId = (t) => t.inv_id || t.id;

function TokenChip({ token, onUse }) {
  const kind = token.token;
  const premium = token.tier === "premium";
  return (
    <div
      className="relative flex items-center gap-3 rounded-xl border p-3"
      style={{
        borderColor: premium ? `${GOLD}55` : "rgba(255,255,255,0.1)",
        background: premium ? `${GOLD}0d` : "rgba(255,255,255,0.02)",
      }}
      data-testid={`bp-token-${tokenId(token)}`}
    >
      <img
        src={tokenArt(kind)}
        alt=""
        className="h-12 w-12 shrink-0 object-contain drop-shadow-[0_0_10px_rgba(0,0,0,0.6)]"
        onError={(e) => { e.currentTarget.style.visibility = "hidden"; }}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <p className="truncate text-sm font-bold">{tokenName(kind)}</p>
          <span
            className="rounded px-1.5 py-[1px] text-[9px] font-extrabold"
            style={premium
              ? { background: `${GOLD}22`, color: GOLD, border: `1px solid ${GOLD}55` }
              : { background: "rgba(255,255,255,0.06)", color: "#9CA3AF", border: "1px solid rgba(255,255,255,0.12)" }}
          >
            {tierLabel(token.tier)}
          </span>
        </div>
        <p className="mt-0.5 text-[11px] text-muted-foreground">{tokenEffect(kind, token.tier)}</p>
      </div>
      <button
        type="button"
        onClick={() => onUse(token)}
        data-testid={`bp-token-use-${tokenId(token)}`}
        className="shrink-0 rounded-lg bg-gold px-3 py-2 text-xs font-bold text-background transition-all hover:brightness-110"
      >
        Usar
      </button>
    </div>
  );
}

export function RedeemModal({ token, onClose, onDone }) {
  const { play } = useSound();
  // ★ EVERY pass token is LIVE-ONLY (owner orders 2026-08-07): the vault
  // target is gone — one path, the dinosaur being played right now.
  const [mode] = useState("live");
  const [busy, setBusy] = useState(false);
  const [waited, setWaited] = useState(false);
  const timerRef = useRef(null);
  useEffect(() => () => clearTimeout(timerRef.current), []);

  const redeem = async () => {
    if (busy) return;
    play("click");
    setBusy(true);
    setWaited(false);
    // The live lane crosses into the game server. Bound the wait and say plainly
    // that nothing was spent if the ack never lands.
    if (mode === "live") timerRef.current = setTimeout(() => setWaited(true), LIVE_WAIT_MS);
    try {
      const body = { inv_id: tokenId(token), target: "live" };
      const r = await api.bpTokenRedeem(body);
      clearTimeout(timerRef.current);
      if (r.data?.ok) {
        onDone(r.data.effects || []);
        return;
      }
      play("error");
      toast.error(r.data?.error || "No se pudo usar el token");
      setBusy(false);
      setWaited(false);
    } catch (e) {
      clearTimeout(timerRef.current);
      play("error");
      toast.error(e?.response?.data?.detail || e?.response?.data?.error || "No se pudo usar el token");
      setBusy(false);
      setWaited(false);
    }
  };

  const liveBlocked = !token.liveEnabled;
  const canConfirm = !busy && !liveBlocked;

  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/80 p-3 backdrop-blur-md sm:p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}
      data-testid="bp-token-redeem-modal"
    >
      <motion.div
        initial={{ scale: 0.92, y: 20, opacity: 0 }}
        animate={{ scale: 1, y: 0, opacity: 1 }}
        exit={{ scale: 0.92, y: 20, opacity: 0 }}
        transition={{ type: "spring", stiffness: 320, damping: 26 }}
        className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border p-5 sm:p-6"
        style={{ borderColor: `${GOLD}44`, background: "#0b0b0e" }}
      >
        <button
          type="button"
          onClick={() => { play("close"); onClose(); }}
          disabled={busy}
          aria-label="Cerrar"
          data-testid="bp-token-redeem-close"
          className="absolute right-3 top-3 rounded-full bg-white/5 p-2 text-foreground/70 transition-all hover:bg-white/10 hover:text-foreground disabled:opacity-40"
        >
          <X size={18} />
        </button>

        <div className="flex items-center gap-3">
          <img src={tokenArt(token.token)} alt="" className="h-12 w-12 object-contain" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />
          <div>
            <h3 className="font-display text-xl font-extrabold tracking-tight">{tokenName(token.token)}</h3>
            <p className="text-sm text-muted-foreground">{tokenEffect(token.token, token.tier)}</p>
          </div>
        </div>

        <div className="mt-5 rounded-xl border p-3" data-testid="bp-token-liveonly"
          style={{ borderColor: `${GOLD}44`, background: `${GOLD}0d` }}>
          <p className="flex items-center gap-2 text-sm font-bold"><Radio size={16} style={{ color: GOLD }} /> Solo para tu dino EN VIVO</p>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {token.liveEnabled
              ? "Se aplicará al dinosaurio con el que estás jugando ahora mismo. Espera la confirmación del servidor sin cerrar esta ventana."
              : "El servidor no está aceptando fichas en este momento. Inténtalo en unos minutos — tu ficha no se gasta."}
          </p>
        </div>

        {waited && busy && (
          <div
            className="mt-4 flex items-start gap-2 rounded-xl border p-3 text-[13px]"
            style={{ borderColor: "rgba(226,74,74,0.45)", background: "rgba(226,74,74,0.08)", color: "#E24A4A" }}
            data-testid="bp-token-live-timeout"
          >
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <span>El servidor no confirmó — tu token NO se gastó. Vuelve a intentarlo en un momento.</span>
          </div>
        )}

        <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => { play("close"); onClose(); }}
            disabled={busy}
            data-testid="bp-token-redeem-cancel"
            className="rounded-lg border border-white/10 px-4 py-2.5 text-sm font-bold text-muted-foreground transition-all hover:text-foreground disabled:opacity-40"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={redeem}
            disabled={!canConfirm}
            data-testid="bp-token-redeem"
            className="inline-flex items-center justify-center gap-2 rounded-lg px-5 py-2.5 text-sm font-extrabold text-black transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            style={{ background: GOLD }}
          >
            {busy && <Loader2 size={15} className="animate-spin" />}
            {busy ? "Esperando confirmación…" : "Usar el token"}
          </button>
        </div>
      </motion.div>
    </motion.div>,
    document.body
  );
}

export function TokenPanel({ liveEnabled, refreshKey, onEffects }) {
  const { play } = useSound();
  const [tokens, setTokens] = useState(null);
  const [failed, setFailed] = useState(false);
  const [active, setActive] = useState(null);

  const load = useCallback(() => {
    setFailed(false);
    api.bpTokens()
      .then((r) => setTokens(Array.isArray(r.data) ? r.data : (r.data?.tokens || [])))
      .catch(() => { setTokens([]); setFailed(true); });
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  const finish = (effects) => {
    setActive(null);
    load();
    play("reward");
    onEffects(effects);
  };

  return (
    <div className="glass rounded-2xl p-5 sm:p-6" data-testid="bp-token-panel">
      <div className="mb-1 flex items-center gap-2">
        <Package size={16} style={{ color: GOLD }} />
        <p className="label-overline text-[10px]" style={{ color: GOLD }}>Tus tokens</p>
      </div>
      <p className="mb-4 text-sm text-muted-foreground">
        Los tokens del pase se usan en tu dino EN VIVO, dentro del juego. El de crecimiento lo sube al 70% y le
        llena la comida; el de dieta se la rellena.
      </p>

      {tokens === null ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Cargando tus tokens…</p>
      ) : failed ? (
        <div className="rounded-xl border border-white/10 p-6 text-center" data-testid="bp-token-panel-error">
          <p className="text-sm text-muted-foreground">No pudimos cargar tus tokens.</p>
          <button type="button" onClick={load} data-testid="bp-token-panel-retry" className="mt-3 rounded-lg bg-gold px-4 py-2 text-xs font-bold text-background hover:brightness-110">
            Reintentar
          </button>
        </div>
      ) : tokens.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground" data-testid="bp-token-panel-empty">
          No tienes tokens todavía — súbelos en el pase.
        </p>
      ) : (
        <div className="grid gap-2.5 sm:grid-cols-2">
          {tokens.map((t) => (
            <TokenChip key={tokenId(t)} token={t} onUse={(tok) => { play("open"); setActive(tok); }} />
          ))}
        </div>
      )}

      <AnimatePresence>
        {active && (
          <RedeemModal
            token={{ ...active, liveEnabled }}
            onClose={() => { setActive(null); }}
            onDone={finish}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

export default TokenPanel;
