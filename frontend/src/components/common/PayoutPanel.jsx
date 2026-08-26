import React, { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Zap, TrendingUp, Wallet, Radio } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { api } from "@/lib/api";
import { usePayoutTimer } from "@/hooks/usePayoutTimer";

const GOLD = "#EAB308";
const TEAL = "#2DD4BF";
const GREEN = "#22C55E";
const RED = "#E5484D";
const AMBER = "#F59E0B";

function fmtDur(s) {
  if (s == null) return "--";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return `${h > 0 ? h + "h " : ""}${String(m).padStart(2, "0")}m ${String(sec).padStart(2, "0")}s`;
}

const pad2 = (n) => String(n).padStart(2, "0");

function amberParts(s) {
  const t = Math.max(0, Math.floor(s || 0));
  return [
    ["d", Math.floor(t / 86400)],
    ["h", Math.floor((t % 86400) / 3600)],
    ["m", Math.floor((t % 3600) / 60)],
    ["s", Math.floor(t % 60)],
  ];
}

export default function PayoutPanel({ active }) {
  const [st, setSt] = useState(null);
  const [rem, setRem] = useState(null);
  const [sess, setSess] = useState(null);
  const [pat, setPat] = useState(null);
  const [amberRem, setAmberRem] = useState(null);
  const barRef = useRef(null);
  const remTextRef = useRef(null);
  const lastSec = useRef(-1);

  useEffect(() => {
    if (!active) return undefined;
    let alive = true;
    const load = () => api.payoutStatus().then((r) => {
      if (!alive) return;
      setSt(r.data); setRem(r.data.seconds_remaining); setSess(r.data.session_seconds);
    }).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, [active]);

  // Only the session clock ticks per-second here; the payout bar + countdown are
  // driven continuously by usePayoutTimer so they stay smooth and in sync.
  useEffect(() => {
    if (!st?.in_game) return undefined;
    const t = setInterval(() => {
      setSess((s) => (s == null ? s : s + 1));
    }, 1000);
    return () => clearInterval(t);
  }, [st?.in_game]);

  usePayoutTimer({
    secondsRemaining: rem,
    intervalSeconds: st?.interval_seconds,
    active: !!st?.in_game,
    onTick: (r, progress) => {
      if (barRef.current) barRef.current.style.width = `${progress * 100}%`;
      const s = Math.ceil(r);
      if (s !== lastSec.current && remTextRef.current) {
        lastSec.current = s;
        remTextRef.current.textContent = fmtDur(s);
      }
    },
  });

  useEffect(() => {
    if (!active) return undefined;
    let alive = true;
    api.patreonStatus().then((r) => {
      if (!alive) return;
      setPat(r.data);
      setAmberRem(r.data?.seconds_remaining ?? null);
    }).catch(() => {});
    return () => { alive = false; };
  }, [active]);

  useEffect(() => {
    if (amberRem == null) return undefined;
    const t = setInterval(() => setAmberRem((s) => (s != null && s > 0 ? s - 1 : s)), 1000);
    return () => clearInterval(t);
  }, [amberRem == null]);

  if (!st) return <div className="text-sm text-muted-foreground" data-testid="payout-loading">Cargando payout…</div>;

  const playing = st.in_game;
  const accent = playing ? GREEN : RED;
  const boostLabel = st.multiplier > 1 ? `${st.multiplier}x` : "1x";

  const Row = ({ icon: Icon, label, value, valueColor }) => (
    <div className="flex items-center gap-2.5 text-sm">
      <Icon size={16} className="text-muted-foreground shrink-0" />
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold" style={valueColor ? { color: valueColor } : undefined}>{value}</span>
    </div>
  );

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
      className="space-y-4" data-testid="payout-tab">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-gold/15 text-gold border border-gold/30 inline-flex items-center gap-1"><Zap size={10} /> PAYOUT</span>
        <p className="text-sm text-muted-foreground">Gana PrimeMeat en tiempo real mientras juegas dentro del servidor.</p>
      </div>

      <div className="relative overflow-hidden" data-testid="payout-card"
        style={{ borderRadius: 6, border: `1px solid ${accent}55`, background: "#0b0b0e", boxShadow: `0 0 45px ${accent}18` }}>
        <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(120% 100% at 100% 0%, ${accent}12, transparent 55%)` }} />
        <div className="relative p-6 sm:p-7">
          {/* header */}
          <div className="flex items-start gap-5 mb-6">
            <div className="w-20 h-20 flex items-center justify-center shrink-0" style={{ borderRadius: 6, background: playing ? "#0d1a12" : "#1a0d0e", border: `1px solid ${accent}55` }}>
              <img src={MEDIA.coinNormal} alt="" className="w-12 h-12 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
            </div>
            <div className="pt-1">
              <p className="text-[11px] font-extrabold uppercase tracking-[0.25em] text-muted-foreground">Playtime Payout</p>
              <h3 className="font-display font-extrabold text-3xl leading-none mt-1.5 flex items-center gap-2" style={{ color: accent }} data-testid="payout-status">
                {playing ? <><Radio size={20} className="animate-pulse" /> Jugando ahora</> : "No conectado"}
              </h3>
              <p className="text-sm text-muted-foreground mt-2">
                {playing ? "Tu cuenta de Steam está conectada al servidor." : "Conéctate al servidor con tu Steam vinculado para generar PrimeMeat."}
              </p>
            </div>
          </div>

          {/* stat boxes */}
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div className="p-4" style={{ borderRadius: 6, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.015)" }}>
              <div className="flex items-center gap-2">
                <img src={MEDIA.coinNormal} alt="" className="w-6 h-6 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <span className="font-display font-extrabold text-2xl" style={{ color: GOLD }} data-testid="payout-per-hour">{(st.per_hour || 0).toLocaleString()}</span>
              </div>
              <p className="text-[11px] text-muted-foreground mt-1.5">PrimeMeat por hora</p>
            </div>
            <div className="p-4" style={{ borderRadius: 6, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.015)" }}>
              <div className="flex items-center gap-2">
                <Zap size={20} style={{ color: TEAL }} />
                <span className="font-display font-extrabold text-2xl" style={{ color: TEAL }}>{boostLabel} Boost</span>
              </div>
              <p className="text-[11px] text-muted-foreground mt-1.5">{st.multiplier > 1 ? "Multiplicador de Patreon" : "Sin suscripción"}</p>
            </div>
          </div>

          {/* live session */}
          <div className="p-4 mb-5" style={{ borderRadius: 6, border: `1px solid ${GOLD}44`, background: `${GOLD}0a` }}>
            <div className="flex items-center justify-between text-[11px] font-extrabold uppercase tracking-[0.2em] mb-3" style={{ color: GOLD }}>
              <span className="flex items-center gap-2"><img src={MEDIA.coinNormal} alt="" className="w-4 h-4 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} /> Sesión actual</span>
              {playing && <span className="text-muted-foreground normal-case tracking-normal font-semibold">{fmtDur(sess)}</span>}
            </div>
            <div className="flex items-baseline gap-2">
              <span className="font-mono font-extrabold text-3xl sm:text-4xl leading-none" style={{ color: GOLD }} data-testid="payout-session-earned">+{(st.session_earned || 0).toLocaleString()}</span>
              <span className="text-sm text-muted-foreground">PrimeMeat esta sesión</span>
            </div>
            {playing && (
              <>
                <div className="mt-3 h-[6px] w-full overflow-hidden" style={{ borderRadius: 3, background: "rgba(255,255,255,0.08)" }}>
                  <div ref={barRef} className="h-full" style={{ width: "0%", background: GOLD, boxShadow: `0 0 8px ${GOLD}88` }} />
                </div>
                <p className="text-[11px] text-muted-foreground mt-1.5">Próximo pago de <b style={{ color: GOLD }}>{(st.reward_per_tick || 0).toLocaleString()}</b> en <span ref={remTextRef} className="tabular-nums">{fmtDur(rem)}</span></p>
              </>
            )}
          </div>

          {/* amberium bi-weekly payout */}
          {pat?.active && amberRem != null ? (
            <div className="p-4 mb-5" style={{ borderRadius: 6, border: `1px solid ${AMBER}44`, background: `${AMBER}0a` }} data-testid="payout-amber-card">
              <div className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.2em] mb-3" style={{ color: AMBER }}>
                <img src={MEDIA.coinVip} alt="" className="w-4 h-4 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                Próximo pago de Amberium
              </div>
              <div className="flex items-center flex-wrap gap-x-3 gap-y-2" data-testid="payout-amber-countdown">
                {amberParts(amberRem).map(([u, val], i) => (
                  <React.Fragment key={u}>
                    <div className="flex items-baseline gap-1.5">
                      <span className="font-mono font-extrabold text-3xl sm:text-4xl leading-none" style={{ color: AMBER }}>{pad2(val)}</span>
                      <span className="text-xs font-bold text-muted-foreground">{u}</span>
                    </div>
                    {i < 3 && <span className="text-2xl font-bold text-muted-foreground/50 leading-none">:</span>}
                  </React.Fragment>
                ))}
                <span className="text-sm text-muted-foreground/70 ml-1">hasta +{(pat.amber_per_payout || 0).toLocaleString()} Amberium</span>
              </div>
              <p className="text-[11px] text-muted-foreground mt-2" data-testid="payout-amber-note">
                Pago quincenal por tu nivel de Patreon{pat.tier_name ? ` (${pat.tier_name})` : ""}.
                {pat.welcome_paid_at ? " Tu pago de bienvenida ya está en tu balance." : ""}
              </p>
            </div>
          ) : pat && !pat.active ? (
            <div className="p-4 mb-5 flex items-center gap-3" style={{ borderRadius: 6, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.015)" }} data-testid="payout-amber-locked">
              <img src={MEDIA.coinVip} alt="" className="w-6 h-6 object-contain shrink-0" onError={(e) => { e.currentTarget.style.display = "none"; }} />
              <p className="text-xs text-muted-foreground">
                Los miembros de Patreon reciben su <b style={{ color: AMBER }}>Amberium al suscribirse</b> y después <b style={{ color: AMBER }}>cada 14 días</b>. Vincula tu Patreon en la pestaña Patreon para activar el contador.
              </p>
            </div>
          ) : null}

          {/* rows */}
          <div className="space-y-2.5">
            <Row icon={TrendingUp} label="Total generado jugando:" value={`${(st.total_earned || 0).toLocaleString()} PrimeMeat`} valueColor={GOLD} />
            <Row icon={Wallet} label="Balance actual:" value={`${(st.coins || 0).toLocaleString()} PrimeMeat`} />
          </div>

          <div className="mt-5 pt-4 border-t border-white/10">
            <p className="text-xs text-muted-foreground/70">
              Ganas <b style={{ color: GOLD }}>{(st.reward_per_tick || 0).toLocaleString()} PrimeMeat</b> cada {Math.round(st.interval_seconds / 60)} min mientras estás conectado. Los niveles de Patreon multiplican esta cantidad.
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
