import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link, useNavigate } from "react-router-dom";
import { Clock, Award, Hash, ExternalLink, Receipt, Gift, Store as StoreIcon, Ticket, Bone, Package, ShieldCheck, Palette, Gavel, Heart, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { MEDIA } from "@/lib/media";
import { CoinChip } from "@/components/common/CoinChip";
import { RarityBadge } from "@/components/common/RarityBadge";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { LinkedAccounts } from "@/components/common/LinkedAccounts";
import { SkinIcon } from "@/components/common/SkinIcon";
import { ProvablyFairPanel } from "@/components/common/ProvablyFair";
import Decorations from "@/components/cosmetics/Decorations";
import { AccountStanding } from "@/components/common/AccountStanding";
import PatreonTiers from "@/components/common/PatreonTiers";
import PayoutPanel from "@/components/common/PayoutPanel";
import { ApplyCodeCard } from "@/components/creator/ApplyCodeCard";
import { MyReferralCard } from "@/components/creator/MyReferralCard";

const STATUS_STYLE = {
  active: "bg-emerald/15 text-emerald border-emerald/30",
  parked: "bg-sky-400/15 text-sky-300 border-sky-400/30",
  slain: "bg-crimson/15 text-crimson border-crimson/30",
  lost: "bg-crimson/15 text-crimson border-crimson/30",
  recovered: "bg-gold/15 text-gold border-gold/30",
};
const STATUS_LABEL = { active: "Active", parked: "Saved", slain: "Slain", lost: "Lost", recovered: "Recovered" };

const TABS = [
  { k: "patreon", label: "Patreon", icon: Heart },
  { k: "payout", label: "Payout", icon: Zap },
  { k: "decorations", label: "Decoraciones", icon: Palette },
  { k: "purchases", label: "Compras", icon: Receipt },
  { k: "redemptions", label: "Canjes", icon: Ticket },
  { k: "unboxings", label: "Aperturas", icon: Gift },
  { k: "market", label: "Mercado", icon: StoreIcon },
  { k: "dinos", label: "Registros de Dino", icon: Bone },
  { k: "strikes", label: "Historial de Strikes", icon: Gavel },
  { k: "fairness", label: "Juego Justo", icon: ShieldCheck },
];

export default function Profile() {
  const { user } = useAuth();
  const { play } = useSound();
  const navigate = useNavigate();
  // ★ The pass moved to its own page (owner order 2026-08-07). Old deep links
  // and IN-FLIGHT Stripe returns still point here (?tab=battlepass and/or
  // ?bp_session=…, baked into checkout sessions minted before the move) —
  // forward them to /battle-pass with every query param intact so the payment
  // poll still runs.
  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search);
      if (q.get("bp_session") || q.get("tab") === "battlepass") {
        q.delete("tab");
        navigate("/battle-pass" + (q.toString() ? `?${q}` : ""), { replace: true });
      }
    } catch (e) { /* no URL access — nothing to forward */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Deep link: ?tab=<key> opens that tab directly. Otherwise: returning from a
  // Discord link started in the Streamer Pack section lands on Patreon so the
  // apply form is right there (StreamerPack re-opens it).
  const [tab, setTab] = useState(() => {
    try {
      const q = new URLSearchParams(window.location.search);
      const want = q.get("tab");
      if (want && TABS.some((t) => t.k === want)) return want;
    } catch (e) { /* no URL access — fall through to the defaults */ }
    try { return localStorage.getItem("streamer_intent") ? "patreon" : "purchases"; } catch { return "purchases"; }
  });
  const [history, setHistory] = useState([]);
  const [redemptions, setRedemptions] = useState([]);
  const [unboxings, setUnboxings] = useState([]);
  const [sales, setSales] = useState({ sold: [], bought: [] });
  const [records, setRecords] = useState([]);
  const [strikes, setStrikes] = useState([]);

  useEffect(() => {
    if (!user) return;
    api.purchaseHistory().then((r) => setHistory(r.data)).catch(() => {});
    api.redemptions().then((r) => setRedemptions(r.data)).catch(() => {});
    api.unboxings().then((r) => setUnboxings(r.data)).catch(() => {});
    api.mySales().then((r) => setSales(r.data)).catch(() => {});
    api.dinoRecords().then((r) => setRecords(r.data)).catch(() => {});
    api.profileStanding().then((r) => setStrikes(r.data.strikes || [])).catch(() => {});
  }, [user]);

  if (!user) return <div className="max-w-7xl mx-auto px-6 py-14"><SignInPrompt title="Tu perfil" sub="Inicia sesión para ver tus conexiones, historial y registros de dino." /></div>;

  const playHours = Math.round(user.playtime_minutes / 60);

  return (
    <div className="max-w-7xl mx-auto px-6 py-14">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
        className="relative glass-strong rounded-3xl p-8 overflow-hidden grain mb-8" data-testid="profile-header">
        <img src={MEDIA.heroBg} alt="" className="absolute inset-0 w-full h-full object-cover opacity-10" />
        <div className="relative flex flex-col sm:flex-row items-center gap-6">
          <img src={user.avatar || MEDIA.logo} alt="" className="w-24 h-24 rounded-2xl object-cover border-2 border-gold/40 gold-glow" />
          <div className="text-center sm:text-left flex-1">
            <span className="label-overline text-[10px] text-gold">{user.role === "admin" ? "Administrator" : "Survivor"}</span>
            <h1 className="font-display font-extrabold text-3xl sm:text-4xl tracking-tight">{user.persona_name}</h1>
            <div className="flex flex-wrap gap-4 mt-3 justify-center sm:justify-start text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1.5"><Hash size={14} /> {user.steam_id}</span>
              <span className="inline-flex items-center gap-1.5"><Award size={14} className="text-gold" /> {user.rank}</span>
              <span className="inline-flex items-center gap-1.5"><Clock size={14} /> {playHours}h played</span>
              {user.profile_url && <a href={user.profile_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-gold hover:underline"><ExternalLink size={14} /> Steam</a>}
            </div>
          </div>
          <div className="flex flex-col gap-3 items-center">
            <div className="flex gap-3">
              <div className="glass rounded-xl px-4 py-3 text-center"><CoinChip type="normal" amount={user.coins} size="md" /></div>
              <div className="glass rounded-xl px-4 py-3 text-center"><CoinChip type="vip" amount={user.vip_coins} size="md" /></div>
            </div>
            <Link to="/my-dino" data-testid="profile-inventory-link" onClick={() => play("click")}
              className="w-full inline-flex items-center justify-center gap-2 bg-gold text-background font-bold text-sm px-4 py-2 rounded-lg hover:brightness-110 transition-all">
              <Package size={15} /> Ver mi equipo
            </Link>
          </div>
        </div>
      </motion.div>

      {/* Account standing */}
      <AccountStanding />

      {/* Creator Program — apply a creator's code (shows the apply-card OR
          the referral card if this account already used one) */}
      <div className="mb-8 grid gap-4 md:grid-cols-2">
        <ApplyCodeCard />
        <MyReferralCard />
      </div>

      {/* Connections */}
      <LinkedAccounts />

      {/* History tabs */}
      <div className="flex gap-2 mb-6 flex-wrap" data-testid="profile-tabs">
        {TABS.map((t) => (
          <button key={t.k} onClick={() => { setTab(t.k); play("click"); }} onMouseEnter={() => play("hover")} data-testid={`profile-tab-${t.k}`}
            className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all ${tab === t.k ? "bg-gold text-background" : "glass text-muted-foreground hover:text-foreground"}`}>
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {tab === "patreon" && <PatreonTiers key="patreon" />}
        {tab === "payout" && <PayoutPanel key="payout" active={tab === "payout"} />}

        {tab === "decorations" && (
          <motion.div key="decorations" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}>
            <Decorations />
          </motion.div>
        )}

        {tab === "purchases" && (
          <motion.div key="purchases" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
            className="glass rounded-2xl p-6 space-y-2" data-testid="history-list">
            {history.length === 0 ? <p className="text-muted-foreground py-8 text-center text-sm">Aún no hay compras.</p>
              : history.map((h, i) => (
                <motion.div key={h.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}
                  className="flex items-center justify-between glass rounded-xl p-4">
                  <div><p className="font-semibold text-sm">{h.name}</p><p className="text-xs text-muted-foreground">{new Date(h.created_at).toLocaleString()}</p></div>
                  <CoinChip type={h.currency} amount={h.price} size="sm" />
                </motion.div>
              ))}
          </motion.div>
        )}

        {tab === "redemptions" && (
          <motion.div key="redemptions" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
            className="glass rounded-2xl p-6 space-y-2" data-testid="redemptions-list">
            {redemptions.length === 0 ? <p className="text-muted-foreground py-8 text-center text-sm">Aún no has canjeado códigos.</p>
              : redemptions.map((r, i) => (
                <motion.div key={r.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}
                  className="flex items-center justify-between glass rounded-xl p-4" data-testid={`redemption-${r.id}`}>
                  <div>
                    <p className="font-display font-bold text-gold tracking-wide">{r.code}</p>
                    <p className="text-xs text-muted-foreground">{new Date(r.created_at).toLocaleString()}</p>
                  </div>
                  <div className="flex gap-2 text-xs">
                    {r.granted?.coins > 0 && <CoinChip type="normal" amount={r.granted.coins} size="sm" />}
                    {r.granted?.vip_coins > 0 && <CoinChip type="vip" amount={r.granted.vip_coins} size="sm" />}
                    {r.granted?.spins > 0 && <span className="inline-flex items-center gap-1 rounded-lg border border-pink-500/40 bg-pink-500/10 px-2 py-1 font-bold text-pink-300">✨ {r.granted.spins} spins</span>}
                  </div>
                </motion.div>
              ))}
          </motion.div>
        )}

        {tab === "unboxings" && (
          <motion.div key="unbox" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
            className="glass rounded-2xl p-6 space-y-2" data-testid="unboxings-list">
            {unboxings.length === 0 ? <p className="text-muted-foreground py-8 text-center text-sm">Aún no has abierto cajas.</p>
              : unboxings.map((u, i) => (
                <motion.div key={u.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}
                  className="flex items-center gap-3 glass rounded-xl p-4" data-testid={`unboxing-${u.id}`}>
                  <div className="w-11 h-11 rounded-lg overflow-hidden shrink-0">
                    {u.reward?.type === "skin" ? <SkinIcon rarity={u.reward.rarity} /> : <img src={u.reward?.image} alt="" className="w-full h-full object-cover" />}
                  </div>
                  <div className="flex-1 min-w-0"><p className="font-semibold text-sm truncate">{u.reward?.label}</p><p className="text-xs text-muted-foreground">{u.case_name} · {new Date(u.created_at).toLocaleString()}</p></div>
                  <RarityBadge rarity={u.reward?.rarity} />
                </motion.div>
              ))}
          </motion.div>
        )}

        {tab === "market" && (
          <motion.div key="market" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
            className="grid md:grid-cols-2 gap-6" data-testid="market-activity">
            <div className="glass rounded-2xl p-6 space-y-2">
              <h3 className="font-display font-bold text-lg mb-2">Vendido</h3>
              {sales.sold.length === 0 ? <p className="text-muted-foreground py-6 text-center text-sm">Aún no has vendido nada.</p>
                : sales.sold.map((s) => (
                  <div key={s.id} className="flex items-center gap-3 glass rounded-xl p-3" data-testid={`sale-sold-${s.id}`}>
                    <img src={s.image} alt="" className="w-10 h-10 rounded-lg object-cover" />
                    <div className="flex-1 min-w-0"><p className="font-semibold text-sm truncate">{s.dino_name}</p><p className="text-xs text-muted-foreground">to {s.buyer_name || "—"} · {s.sold_at ? new Date(s.sold_at).toLocaleDateString() : ""}</p></div>
                    <CoinChip type="normal" amount={s.sold_price || s.price} size="sm" />
                  </div>
                ))}
            </div>
            <div className="glass rounded-2xl p-6 space-y-2">
              <h3 className="font-display font-bold text-lg mb-2">Comprado</h3>
              {sales.bought.length === 0 ? <p className="text-muted-foreground py-6 text-center text-sm">Aún no has comprado en el mercado.</p>
                : sales.bought.map((s) => (
                  <div key={s.id} className="flex items-center gap-3 glass rounded-xl p-3" data-testid={`sale-bought-${s.id}`}>
                    <img src={s.image} alt="" className="w-10 h-10 rounded-lg object-cover" />
                    <div className="flex-1 min-w-0"><p className="font-semibold text-sm truncate">{s.dino_name}</p><p className="text-xs text-muted-foreground">from {s.seller_name || "—"} · {s.sold_at ? new Date(s.sold_at).toLocaleDateString() : ""}</p></div>
                    <CoinChip type="normal" amount={s.sold_price || s.price} size="sm" />
                  </div>
                ))}
            </div>
          </motion.div>
        )}

        {tab === "dinos" && (
          <motion.div key="dinos" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
            className="space-y-3" data-testid="dino-records-list">
            <div className="glass rounded-xl p-4 text-xs text-muted-foreground">
              Each deployed dino gets a unique <span className="text-gold font-semibold">ID de Recuperación</span>. If a dino dies to a bug or is lost on a server restart, give its ID to an admin to get it back with all its stats.
            </div>
            {records.length === 0 ? <p className="text-muted-foreground py-8 text-center text-sm">Aún no hay registros de dino. Despliega un dinosaurio desde tu inventario para empezar a rastrear.</p>
              : records.map((d, i) => (
                <motion.div key={d.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}
                  className="flex items-center gap-4 glass rounded-xl p-4" data-testid={`dino-record-${d.recovery_id}`}>
                  <img src={d.image} alt="" className="w-12 h-12 rounded-lg object-contain shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-sm">{d.name}</p>
                      <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border ${STATUS_STYLE[d.status] || "bg-white/10 text-muted-foreground border-white/10"}`}>{STATUS_LABEL[d.status] || d.status}</span>
                    </div>
                    <p className="font-mono text-xs text-gold mt-0.5 select-all" data-testid={`recovery-id-${d.recovery_id}`}>{d.recovery_id}</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {Math.round(d.growth)}% growth · {(d.mutations || []).length} mutations
                      {d.lost_at && ` · lost ${new Date(d.lost_at).toLocaleDateString()}`}
                      {d.updated_at && !d.lost_at && ` · ${new Date(d.updated_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <RarityBadge rarity={d.rarity} />
                </motion.div>
              ))}
          </motion.div>
        )}

        {tab === "strikes" && (
          <motion.div key="strikes" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
            className="glass rounded-2xl p-6 space-y-2" data-testid="strikes-list">
            <div className="text-xs text-muted-foreground mb-2">
              Las infracciones suman strikes. A los <span className="text-gold font-semibold">2 strikes</span> recibes un ban de 1 hora, y escala (24h → 7 días → permanente) con cada nuevo strike.
            </div>
            {strikes.length === 0 ? <p className="text-muted-foreground py-8 text-center text-sm">Sin strikes en el registro. ¡Mantén tu buena reputación!</p>
              : strikes.map((s, i) => {
                const expired = !s.active || (s.expires_at && new Date(s.expires_at) < new Date());
                return (
                  <motion.div key={s.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}
                    className="flex items-center gap-4 glass rounded-xl p-4" data-testid={`strike-${s.id}`}>
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${expired ? "bg-white/5 text-muted-foreground/50" : "bg-crimson/15 text-crimson"}`}>
                      <Gavel size={18} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm truncate">{s.reason}</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {new Date(s.created_at).toLocaleDateString()} · por {s.issued_by || "staff"}
                        {s.expires_at && ` · expira ${new Date(s.expires_at).toLocaleDateString()}`}
                      </p>
                    </div>
                    <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border ${expired ? "bg-white/10 text-muted-foreground border-white/10" : "bg-crimson/15 text-crimson border-crimson/30"}`}>
                      {expired ? "EXPIRED" : "ACTIVE"}
                    </span>
                  </motion.div>
                );
              })}
          </motion.div>
        )}

        {tab === "fairness" && (
          <motion.div key="fairness" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
            className="grid lg:grid-cols-[1fr_360px] gap-6" data-testid="fairness-tab">
            <div className="glass rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center"><ShieldCheck size={20} className="text-emerald-400" /></div>
                <div>
                  <p className="label-overline text-[10px] text-emerald-400">Aleatoriedad verificable</p>
                  <h3 className="font-display font-bold text-xl">Tus semillas</h3>
                </div>
              </div>
              <ProvablyFairPanel active={tab === "fairness"} />
            </div>
            <div className="glass rounded-2xl p-6">
              <h3 className="font-display font-bold text-lg mb-3">Tiradas verificadas recientes</h3>
              {unboxings.filter((u) => u.fairness).length === 0 ? (
                <p className="text-muted-foreground py-6 text-center text-sm">Abre una caja para ver tiradas verificables aquí.</p>
              ) : (
                <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1" data-testid="fairness-roll-history">
                  {unboxings.filter((u) => u.fairness).slice(0, 30).map((u) => (
                    <div key={u.id} className="glass rounded-lg p-3 text-[11px] font-mono" data-testid={`fairness-roll-${u.id}`}>
                      <div className="flex items-center justify-between mb-1 font-sans">
                        <span className="font-semibold text-sm">{u.reward?.label}</span>
                        <RarityBadge rarity={u.reward?.rarity} />
                      </div>
                      <p className="text-muted-foreground truncate">hash: {u.fairness.server_seed_hash?.slice(0, 16)}…</p>
                      <p className="text-muted-foreground">nonce: {u.fairness.nonce} · roll: <span className="text-gold">{u.fairness.roll}</span></p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
