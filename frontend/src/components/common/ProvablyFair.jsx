import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, X, RefreshCw, Copy, Check, Dice5 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";

const short = (s, n = 10) => (s && s.length > n * 2 ? `${s.slice(0, n)}…${s.slice(-n)}` : s || "—");

function CopyRow({ label, value, testid }) {
  const [copied, setCopied] = useState(false);
  const copy = () => { navigator.clipboard?.writeText(value || ""); setCopied(true); setTimeout(() => setCopied(false), 1200); };
  return (
    <div className="flex items-center justify-between gap-3 glass rounded-lg px-3 py-2" data-testid={testid}>
      <div className="min-w-0">
        <p className="text-[10px] label-overline text-muted-foreground">{label}</p>
        <p className="text-xs font-mono truncate">{value || "—"}</p>
      </div>
      {value && (
        <button onClick={copy} className="shrink-0 p-1.5 rounded-md hover:bg-white/10 transition-colors" data-testid={`${testid}-copy`}>
          {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
        </button>
      )}
    </div>
  );
}

// Small badge + inline proof of the last roll.
export function FairnessProof({ proof }) {
  if (!proof) return null;
  return (
    <div className="glass rounded-lg px-3 py-2 text-[11px] font-mono text-muted-foreground space-y-0.5" data-testid="fairness-proof">
      <div className="flex items-center gap-1.5 text-emerald-400 font-sans font-semibold text-[10px] mb-1">
        <ShieldCheck size={12} /> PROVABLY FAIR RESULT
      </div>
      <div>hash: <span className="text-foreground">{short(proof.server_seed_hash, 8)}</span></div>
      <div>client: <span className="text-foreground">{proof.client_seed}</span> · nonce: <span className="text-foreground">{proof.nonce}</span></div>
      <div>roll: <span className="text-gold">{proof.roll}</span></div>
    </div>
  );
}

// Reusable seed-management panel (used both inside the modal and on the Profile page).
export function ProvablyFairPanel({ active = true, showIntro = true }) {
  const { play } = useSound();
  const [current, setCurrent] = useState(null);
  const [clientSeed, setClientSeed] = useState("");
  const [revealed, setRevealed] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!active) return;
    api.fairnessCurrent().then((r) => { setCurrent(r.data); setClientSeed(r.data.client_seed); }).catch(() => {});
    setRevealed(null);
  }, [active]);

  const saveSeed = async () => {
    setBusy(true);
    try {
      const { data } = await api.fairnessSetClientSeed(clientSeed);
      setCurrent(data); setClientSeed(data.client_seed);
      play("success"); toast.success("Semilla de cliente actualizada");
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo actualizar la semilla"); }
    finally { setBusy(false); }
  };

  const rotate = async () => {
    setBusy(true);
    try {
      const { data } = await api.fairnessRotate();
      setRevealed(data.revealed); setCurrent(data.current); setClientSeed(data.current.client_seed);
      play("reward"); toast.success("Nueva semilla de servidor generada", { description: "Tu semilla anterior ahora está revelada para verificación." });
    } catch (e) { play("error"); toast.error("No se pudo rotar la semilla"); }
    finally { setBusy(false); }
  };

  return (
    <div data-testid="fairness-panel">
      {showIntro && (
        <p className="text-xs text-muted-foreground mb-5">
          Every crate result is decided by <span className="text-foreground">HMAC-SHA256(server seed, client seed:nonce)</span>. The server seed hash is shown before you open — rotate it anytime to reveal the original and verify past rolls.
        </p>
      )}
      <div className="space-y-2.5 mb-5">
        <CopyRow label="Server seed (hashed)" value={current?.server_seed_hash} testid="fairness-server-hash" />
        <CopyRow label="Nonce (rolls this seed)" value={String(current?.nonce ?? 0)} testid="fairness-nonce" />
        <div>
          <p className="text-[10px] label-overline text-muted-foreground mb-1.5">Tu semilla de cliente</p>
          <div className="flex gap-2">
            <input value={clientSeed} maxLength={64} onChange={(e) => setClientSeed(e.target.value)} data-testid="fairness-client-seed-input"
              className="flex-1 glass rounded-lg px-3 py-2 text-xs font-mono bg-transparent focus:outline-none focus:ring-2 focus:ring-emerald-500/40" />
            <button onClick={saveSeed} disabled={busy || !clientSeed.trim()} data-testid="fairness-save-seed"
              className="px-3 py-2 rounded-lg bg-emerald-500 text-background font-bold text-xs hover:brightness-110 transition-all disabled:opacity-50">Guardar</button>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Set your own seed to influence the outcome — the server can't predict it.</p>
        </div>
      </div>

      <button onClick={rotate} disabled={busy} data-testid="fairness-rotate"
        className="w-full inline-flex items-center justify-center gap-2 glass border border-emerald-500/30 text-emerald-400 font-semibold py-2.5 rounded-xl hover:bg-emerald-500/10 transition-all disabled:opacity-50">
        <RefreshCw size={15} /> Rotate & reveal server seed
      </button>

      <AnimatePresence>
        {revealed && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-5 pt-5 border-t border-white/10 space-y-2.5" data-testid="fairness-revealed">
            <div className="flex items-center gap-1.5 text-gold text-xs font-semibold"><Dice5 size={14} /> Previous seed revealed — verify it now</div>
            <CopyRow label="Revealed server seed" value={revealed.server_seed} testid="fairness-revealed-seed" />
            <CopyRow label="Its SHA-256 (must match the hash shown before)" value={revealed.server_seed_hash} testid="fairness-revealed-hash" />
            <CopyRow label="Client seed" value={revealed.client_seed} testid="fairness-revealed-client" />
            <CopyRow label="Rolls used with this seed" value={String(revealed.rolls_used)} testid="fairness-revealed-rolls" />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function ProvablyFairModal({ open, onClose }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[100001] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="fairness-modal">
          <div className="absolute inset-0 bg-black/85 backdrop-blur-md" onClick={onClose} />
          <motion.div initial={{ scale: 0.94, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.94, y: 20 }}
            className="relative glass-strong rounded-3xl w-full max-w-lg overflow-hidden max-h-[90vh] overflow-y-auto">
            <button onClick={onClose} data-testid="fairness-modal-close" className="absolute top-4 right-4 z-10 p-2 rounded-lg hover:bg-white/10"><X size={18} /></button>
            <div className="p-6 sm:p-7">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center"><ShieldCheck size={20} className="text-emerald-400" /></div>
                <div>
                  <p className="label-overline text-[10px] text-emerald-400">Verificable</p>
                  <h3 className="font-display font-bold text-2xl">Juego Justo</h3>
                </div>
              </div>
              <ProvablyFairPanel active={open} />
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function FairnessButton({ className = "" }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)} data-testid="fairness-open"
        className={`inline-flex items-center gap-1.5 glass rounded-lg px-3 py-2 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/10 border border-emerald-500/25 transition-all ${className}`}>
        <ShieldCheck size={14} /> Provably Fair
      </button>
      <ProvablyFairModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
