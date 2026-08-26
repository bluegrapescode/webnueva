import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Gift, Ticket, Sparkles, Check } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { CoinChip } from "@/components/common/CoinChip";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { ParticleField } from "@/components/effects/ParticleField";

export default function RedeemCode() {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  if (!user) return <div className="max-w-7xl mx-auto px-6 py-14"><SignInPrompt title="Redeem a code" sub="Sign in to redeem reward codes for coins, VIP currency, items and dinosaurs." /></div>;

  const submit = async (e) => {
    e.preventDefault();
    if (!code.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const { data } = await api.redeemCode(code.trim());
      play("reward");
      setResult(data.granted);
      toast.success("¡Código canjeado!", { description: "Recompensas añadidas a tu cuenta." });
      setCode("");
      await refresh();
    } catch (err) {
      play("error");
      toast.error(err?.response?.data?.detail || "Could not redeem code.");
    } finally {
      setLoading(false);
    }
  };

  const hasRewards = result && (result.coins || result.vip_coins || result.spins || result.items?.length || result.dinos?.length || result.roles?.length);

  return (
    <div className="relative max-w-2xl mx-auto px-6 py-20">
      <div className="absolute inset-0 overflow-hidden -z-10"><ParticleField density={40} /></div>
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="text-center mb-10">
        <Ticket className="mx-auto text-gold mb-4 animate-float" size={40} />
        <p className="label-overline text-xs text-gold mb-2">Recompensas</p>
        <h1 className="font-display font-extrabold text-4xl sm:text-5xl tracking-tighter">Canjear código</h1>
        <p className="text-muted-foreground mt-3">Ingresa un código de eventos, Patreon o del staff para reclamar tus recompensas.</p>
      </motion.div>

      <motion.form onSubmit={submit} initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }}
        className="glass-strong rounded-2xl p-6 flex flex-col sm:flex-row gap-3">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="INGRESA-CÓDIGO"
          data-testid="redeem-input"
          className="flex-1 glass rounded-xl px-4 py-3.5 text-lg font-display font-bold tracking-widest text-center bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/50 uppercase"
        />
        <button type="submit" disabled={loading} data-testid="redeem-button"
          className="inline-flex items-center justify-center gap-2 bg-gold text-background font-bold px-6 py-3.5 rounded-xl hover:brightness-110 hover:gold-glow transition-all disabled:opacity-60">
          <Gift size={18} /> {loading ? "Canjeando…" : "Canjear"}
        </button>
      </motion.form>

      <AnimatePresence>
        {hasRewards && (
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="glass-strong rounded-2xl p-8 mt-6 text-center gold-glow" data-testid="redeem-result"
          >
            <Sparkles className="mx-auto text-gold mb-3" size={28} />
            <h3 className="font-display font-bold text-2xl mb-5">¡Recompensas Reclamadas!</h3>
            <div className="flex flex-wrap justify-center gap-3">
              {result.coins > 0 && <div className="glass rounded-xl px-4 py-3"><CoinChip type="normal" amount={result.coins} size="md" /></div>}
              {result.vip_coins > 0 && <div className="glass rounded-xl px-4 py-3"><CoinChip type="vip" amount={result.vip_coins} size="md" /></div>}
              {result.spins > 0 && <div className="inline-flex items-center gap-2 glass rounded-xl px-4 py-3 text-sm font-bold text-pink-300" data-testid="redeem-spins"><Sparkles size={16} /> {result.spins} Nublar Spins</div>}
              {result.items?.map((n) => <span key={n} className="inline-flex items-center gap-1.5 glass rounded-xl px-4 py-3 text-sm"><Check size={14} className="text-emerald" /> {n}</span>)}
              {result.dinos?.map((n) => <span key={n} className="inline-flex items-center gap-1.5 glass rounded-xl px-4 py-3 text-sm"><Check size={14} className="text-emerald" /> {n} Slot</span>)}
              {result.roles?.map((n) => <span key={n} className="inline-flex items-center gap-1.5 glass rounded-xl px-4 py-3 text-sm text-gold"><Check size={14} /> Role: {n}</span>)}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
