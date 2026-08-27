import React, { useEffect, useMemo, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Skull, Sparkles, Crown, ShieldOff, Search, Coins, Gift, Clock,
  Trophy, Swords, MapPin, Users, Timer, X, Flame, Droplet, Bone,
  RotateCcw, ChevronRight, Dna, Gem, Ghost,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { PageLoader } from "@/components/common/PageLoader";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { useCemeterySocket } from "@/hooks/useCemeterySocket";
import { VineStrip, VineSide, VineCorner, CornerWeb } from "@/components/cemetery/Vines";
import SpiderRunner from "@/components/cemetery/SpiderRunner";
import FlyingCritters from "@/components/cemetery/FlyingCritters";
import {
  statusMeta, rarityColor, fmtPlaytime, fmtDate, fmtCountdown,
  CEM_CAUSES, CEM_SORTS,
} from "@/lib/cemeteryMeta";

const SPECIES_FILTERS = [
  { slug: "", name: "Todas" },
  { slug: "trex", name: "T. Rex" }, { slug: "trike", name: "Triceratops" },
  { slug: "carno", name: "Carnotaurus" }, { slug: "allo", name: "Allosaurus" },
  { slug: "raptor", name: "Omniraptor" }, { slug: "deino", name: "Deinosuchus" },
  { slug: "cerato", name: "Ceratosaurus" }, { slug: "stego", name: "Stegosaurus" },
  { slug: "dilo", name: "Dilophosaurus" }, { slug: "ptera", name: "Pteranodon" },
  { slug: "troodon", name: "Troodon" }, { slug: "diablo", name: "Diabloceratops" },
];

const STATUS_FILTERS = [
  { id: "", label: "Todos" },
  { id: "ELEGIBLE", label: "Elegibles" },
  { id: "RESUCITADO", label: "Resucitados" },
  { id: "NO_REVIVIBLE", label: "No revivibles" },
];

/* ── Stat pill ── */
const StatPill = ({ icon: Icon, label, value, color }) => (
  <div className="flex items-center gap-2 rounded-lg bg-white/[0.03] border border-white/5 px-3 py-2">
    <Icon size={15} style={{ color: color || "#7CA842" }} />
    <div className="leading-tight">
      <div className="text-[10px] uppercase tracking-wider text-white/40">{label}</div>
      <div className="text-sm font-semibold text-white/90">{value}</div>
    </div>
  </div>
);

/* ── Status badge ── */
const StatusBadge = ({ status, size = "sm" }) => {
  const m = statusMeta(status);
  const Icon = status === "RESUCITADO" ? Crown : status === "NO_REVIVIBLE" ? ShieldOff : Sparkles;
  return (
    <span
      data-testid={`status-badge-${status}`}
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${size === "lg" ? "text-xs px-3 py-1" : "text-[10px] px-2 py-0.5"}`}
      style={{ color: m.color, backgroundColor: m.bg, border: `1px solid ${m.border}` }}
    >
      <Icon size={size === "lg" ? 13 : 11} /> {m.label}
    </span>
  );
};

/* ── Dino card ── */
const DinoCard = ({ rec, onOpen, fx = true }) => {
  const d = rec.dino || {};
  const rc = rarityColor(d.rarity);
  return (
    <motion.button
      layout
      data-testid={`cemetery-card-${rec.id}`}
      onClick={() => onOpen(rec)}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4 }}
      transition={{ duration: 0.25 }}
      className="group text-left relative overflow-hidden rounded-2xl bg-[#141418] border border-white/[0.06] hover:border-white/[0.14] transition-colors"
    >
      <div className="absolute inset-x-0 top-0 h-[3px]" style={{ background: `linear-gradient(90deg, ${rc}, transparent)` }} />
      {fx && <VineCorner className="absolute -top-1 left-1 z-10 opacity-50" />}
      <div className="relative h-40 flex items-center justify-center bg-gradient-to-b from-white/[0.02] to-black/40 overflow-hidden">
        <div className="absolute inset-0 opacity-[0.06]" style={{ backgroundImage: "radial-gradient(circle at 30% 20%, #fff 1px, transparent 1px)", backgroundSize: "22px 22px" }} />
        {d.image ? (
          <img src={d.image} alt={d.species_name} className="max-h-32 object-contain drop-shadow-2xl transition-transform duration-500 group-hover:scale-110" style={{ filter: rec.status === "NO_REVIVIBLE" ? "grayscale(0.7) brightness(0.7)" : "none" }} />
        ) : (
          <Bone size={48} className="text-white/20" />
        )}
        <div className="absolute top-2.5 right-2.5"><StatusBadge status={rec.status} /></div>
        {d.prime && (
          <span className="absolute top-2.5 left-2.5 inline-flex items-center gap-1 rounded-full bg-black/60 border border-[#7CA842]/40 px-2 py-0.5 text-[10px] font-bold text-[#A3C96B]">
            <Flame size={10} /> PRIME
          </span>
        )}
      </div>
      <div className="p-4">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-[15px] font-bold text-white truncate">{d.species_name}</h3>
          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0" style={{ color: rc, backgroundColor: `${rc}1a` }}>{d.rarity}</span>
        </div>
        <div className="mt-1 text-xs text-white/40 truncate">{rec.owner?.persona_name || "Desconocido"}</div>
        <div className="mt-3 grid grid-cols-3 gap-1.5 text-center">
          <div className="rounded-lg bg-white/[0.03] py-1.5">
            <div className="text-[10px] text-white/40">Tamaño</div>
            <div className="text-xs font-bold text-white/90">{Math.round(d.growth || 0)}%</div>
          </div>
          <div className="rounded-lg bg-white/[0.03] py-1.5">
            <div className="text-[10px] text-white/40">Kills</div>
            <div className="text-xs font-bold text-white/90">{rec.kills || 0}</div>
          </div>
          <div className="rounded-lg bg-white/[0.03] py-1.5">
            <div className="text-[10px] text-white/40">Vivió</div>
            <div className="text-xs font-bold text-white/90">{fmtPlaytime(rec.playtime_minutes)}</div>
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between text-[11px] text-white/35">
          <span className="inline-flex items-center gap-1"><Droplet size={11} /> {rec.cause}</span>
          <span>{fmtDate(rec.died_at)}</span>
        </div>
      </div>
    </motion.button>
  );
};

/* ── Fossil balance panel ── */
const FossilPanel = ({ fossils, onBuy, onClaim, onOpenTx }) => {
  const cd = fmtCountdown(fossils?.cooldown_until);
  return (
    <div data-testid="fossil-panel" className="relative overflow-hidden rounded-2xl border border-[#7CA842]/20 bg-gradient-to-br from-[#171a12] to-[#121216] p-5">
      <img src="/fossil.png" alt="" aria-hidden className="absolute -right-6 -top-6 w-40 opacity-[0.08] pointer-events-none" />
      <div className="flex items-center gap-2 text-[#A3C96B]">
        <img src="/fossil.png" alt="Fósil" className="w-5 h-5 object-contain" /> <span className="text-sm font-bold uppercase tracking-wider">Fósiles</span>
      </div>
      <div className="mt-3 flex items-end gap-2">
        <span data-testid="fossil-balance" className="text-5xl font-black text-white leading-none">{fossils?.fossils ?? 0}</span>
        <span className="text-xs text-white/40 mb-1">disponibles</span>
      </div>
      <div className="mt-1 text-xs text-white/40">1 Fósil = 1 resurrección · Precio: {(fossils?.fossil_price ?? 8000).toLocaleString()} Amberiums</div>

      <div className="mt-4 flex items-center gap-2 text-xs text-white/50">
        <Coins size={14} className="text-[#D4AF37]" />
        <span data-testid="amber-balance">{(fossils?.amber_balance ?? 0).toLocaleString()} Amberiums</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <button
          data-testid="claim-free-fossil-btn"
          disabled={!fossils?.can_claim_free}
          onClick={onClaim}
          className="inline-flex items-center justify-center gap-1.5 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-white/[0.05] hover:bg-white/[0.1] text-white border border-white/10"
        >
          <Gift size={15} /> {fossils?.can_claim_free ? "Gratis mensual" : "Reclamado"}
        </button>
        <button
          data-testid="buy-fossil-btn"
          onClick={onBuy}
          className="inline-flex items-center justify-center gap-1.5 rounded-xl px-3 py-2.5 text-sm font-bold transition-all bg-[#34D399] hover:bg-[#2bbd88] text-black shadow-lg shadow-emerald-500/20"
        >
          <Gem size={15} /> Comprar
        </button>
      </div>
      {cd && (
        <div data-testid="cooldown-indicator" className="mt-3 flex items-center gap-2 rounded-lg bg-[#E24A4A]/10 border border-[#E24A4A]/25 px-3 py-2 text-xs text-[#f0a3a3]">
          <Clock size={14} /> Cooldown de resurrección: {cd}
        </div>
      )}
      <button data-testid="open-fossil-tx-btn" onClick={onOpenTx} className="mt-3 w-full text-center text-[11px] text-white/35 hover:text-white/60 transition-colors">
        Ver historial de transacciones →
      </button>
    </div>
  );
};

/* ── Modal shell ── */
const Modal = ({ children, onClose, testid, wide }) => (
  <div className="fixed inset-0 z-[120] flex items-center justify-center p-4" data-testid={testid}>
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} className="absolute inset-0 bg-black/80 backdrop-blur-sm" />
    <motion.div
      initial={{ opacity: 0, scale: 0.94, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.94, y: 20 }}
      transition={{ type: "spring", damping: 26, stiffness: 300 }}
      className={`relative w-full ${wide ? "max-w-3xl" : "max-w-md"} max-h-[90vh] overflow-y-auto rounded-2xl border border-white/10 bg-[#121216] shadow-2xl`}
    >
      {children}
    </motion.div>
  </div>
);

/* ── Profile modal ── */
const ProfileModal = ({ rec, onClose, canResurrect, onResurrect }) => {
  const d = rec.dino || {};
  const rc = rarityColor(d.rarity);
  const owner = rec.owner || {};
  return (
    <Modal onClose={onClose} testid="cemetery-profile-modal" wide>
      <div className="relative h-48 bg-gradient-to-b from-white/[0.04] to-black/50 flex items-center justify-center overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-1" style={{ background: `linear-gradient(90deg, ${rc}, transparent)` }} />
        {d.image && <img src={d.image} alt={d.species_name} className="max-h-40 object-contain drop-shadow-2xl" style={{ filter: rec.status === "NO_REVIVIBLE" ? "grayscale(0.7) brightness(0.7)" : "none" }} />}
        <button data-testid="profile-close-btn" onClick={onClose} className="absolute top-3 right-3 rounded-full bg-black/50 hover:bg-black/80 p-2 text-white/70 hover:text-white transition-colors"><X size={18} /></button>
        <div className="absolute bottom-3 left-4 flex items-center gap-2">
          <StatusBadge status={rec.status} size="lg" />
          {d.prime && <span className="inline-flex items-center gap-1 rounded-full bg-black/60 border border-[#7CA842]/40 px-2.5 py-1 text-[11px] font-bold text-[#A3C96B]"><Flame size={12} /> PRIME</span>}
          {d.elder && <span className="inline-flex items-center gap-1 rounded-full bg-black/60 border border-white/20 px-2.5 py-1 text-[11px] font-bold text-white/80">ELDER</span>}
        </div>
      </div>

      <div className="p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-2xl font-black text-white">{d.species_name}</h2>
            <div className="mt-0.5 text-sm" style={{ color: rc }}>{d.rarity} · {d.type} · {d.diet || "—"}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wider text-white/40">Falleció</div>
            <div className="text-sm text-white/80">{fmtDate(rec.died_at)}</div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-2">
          <StatPill icon={Dna} label="Tamaño" value={`${Math.round(d.growth || 0)}%`} />
          <StatPill icon={Swords} label="Asesinatos" value={rec.kills || 0} color="#E24A4A" />
          <StatPill icon={Timer} label="Supervivencia" value={fmtPlaytime(rec.playtime_minutes)} color="#38BDF8" />
          <StatPill icon={Sparkles} label="Mutaciones" value={d.mutations_count || 0} color="#A855F7" />
        </div>

        <div className="mt-4 grid sm:grid-cols-2 gap-3 text-sm">
          <div className="rounded-xl bg-white/[0.03] border border-white/5 p-4 space-y-2.5">
            <div className="flex items-center justify-between"><span className="text-white/40 inline-flex items-center gap-1.5"><Users size={14} /> Dueño</span><span className="text-white/90 font-medium">{owner.persona_name || "—"}</span></div>
            <div className="flex items-center justify-between"><span className="text-white/40">Steam ID</span><span className="text-white/70 font-mono text-xs">{owner.steam_id || "—"}</span></div>
            <div className="flex items-center justify-between"><span className="text-white/40 inline-flex items-center gap-1.5"><MapPin size={14} /> Ubicación</span><span className="text-white/90">{rec.location || "—"}</span></div>
            <div className="flex items-center justify-between"><span className="text-white/40">Grupo / Manada</span><span className="text-white/90">{rec.group || "Solitario"}</span></div>
          </div>
          <div className="rounded-xl bg-white/[0.03] border border-white/5 p-4 space-y-2.5">
            <div className="flex items-center justify-between"><span className="text-white/40 inline-flex items-center gap-1.5"><Droplet size={14} /> Causa</span><span className="text-white/90">{rec.cause}{rec.in_combat ? " (en combate)" : ""}</span></div>
            <div className="flex items-center justify-between"><span className="text-white/40 inline-flex items-center gap-1.5"><Skull size={14} /> Asesino</span><span className="text-white/90">{rec.killer?.name || "—"}</span></div>
            <div className="flex items-center justify-between"><span className="text-white/40">Especie asesino</span><span className="text-white/90">{rec.killer?.species || "—"}</span></div>
            <div className="flex items-center justify-between"><span className="text-white/40">Skin</span><span className="text-white/90">{d.skin_name || "Por defecto"}</span></div>
          </div>
        </div>

        {d.mutations?.length > 0 && (
          <div className="mt-4">
            <div className="text-[10px] uppercase tracking-wider text-white/40 mb-2">Mutaciones</div>
            <div className="flex flex-wrap gap-1.5">
              {d.mutations.map((m, i) => (
                <span key={i} className="text-xs rounded-full bg-[#A855F7]/10 border border-[#A855F7]/25 text-[#c99bf5] px-2.5 py-1">{typeof m === "string" ? m : (m.name || "Mutación")}</span>
              ))}
            </div>
          </div>
        )}

        {rec.status === "NO_REVIVIBLE" && (
          <div className="mt-5 rounded-xl bg-[#E24A4A]/10 border border-[#E24A4A]/25 p-4 flex items-start gap-3">
            <ShieldOff size={18} className="text-[#E24A4A] mt-0.5" />
            <div className="text-sm text-[#f0a3a3]">{rec.not_revivable_reason || "Este dino no puede ser revivido."}</div>
          </div>
        )}

        {rec.status === "RESUCITADO" && (
          <div className="mt-5 rounded-xl bg-[#7CA842]/10 border border-[#7CA842]/25 p-4 flex items-start gap-3">
            <Crown size={18} className="text-[#A3C96B] mt-0.5" />
            <div className="text-sm text-[#c3dd97]">
              Este dino fue resucitado el {fmtDate(rec.resurrected_at)} y devuelto a la bóveda con todos sus stats, mutaciones y skin.
              {fmtCountdown(rec.redeem_cooldown_until) && (
                <div className="mt-2 flex items-center gap-1.5 text-[#8fd0e8]"><Clock size={13} /> No se puede redimir por {fmtCountdown(rec.redeem_cooldown_until)} (anti revenge-kill).</div>
              )}
            </div>
          </div>
        )}

        {rec.status === "ELEGIBLE" && (
          canResurrect ? (
            <button
              data-testid="open-resurrect-btn"
              onClick={() => onResurrect(rec)}
              className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-xl bg-[#34D399] hover:bg-[#2bbd88] text-black font-bold py-3.5 shadow-lg shadow-emerald-500/20 transition-all"
            >
              <RotateCcw size={18} /> Resucitar — 1 Fósil
            </button>
          ) : (
            <div className="mt-5 rounded-xl bg-white/[0.03] border border-white/5 p-4 text-sm text-white/50 text-center">
              Solo el dueño de este dino puede resucitarlo.
            </div>
          )
        )}
      </div>
    </Modal>
  );
};

/* ── Confirm resurrect ── */
const ConfirmResurrect = ({ rec, busy, onClose, onConfirm }) => {
  const d = rec.dino || {};
  return (
    <Modal onClose={busy ? () => {} : onClose} testid="resurrect-confirm-modal">
      <div className="p-6 text-center">
        <div className="mx-auto w-14 h-14 rounded-full bg-[#34D399]/12 border border-[#34D399]/30 flex items-center justify-center"><RotateCcw size={26} className="text-[#34D399]" /></div>
        <h3 className="mt-4 text-xl font-black text-white">¿Resucitar a {d.species_name}?</h3>
        <p className="mt-2 text-sm text-white/50">Se gastará <b className="text-[#A3C96B]">1 Fósil</b> y el dino volverá a tu bóveda tal cual estaba: {Math.round(d.growth || 0)}% de tamaño, {d.mutations_count || 0} mutaciones{d.prime ? ", PRIME" : ""} y su skin. Iniciará un cooldown de 24h y no podrás redimirlo por 2h (anti revenge-kill).</p>
        <div className="mt-6 grid grid-cols-2 gap-3">
          <button data-testid="resurrect-cancel-btn" disabled={busy} onClick={onClose} className="rounded-xl bg-white/[0.05] hover:bg-white/[0.1] text-white font-semibold py-3 border border-white/10 transition-colors disabled:opacity-40">Cancelar</button>
          <button data-testid="resurrect-confirm-btn" disabled={busy} onClick={onConfirm} className="rounded-xl bg-[#34D399] hover:bg-[#2bbd88] text-black font-bold py-3 shadow-lg shadow-emerald-500/20 transition-all disabled:opacity-60">{busy ? "Resucitando…" : "Confirmar"}</button>
        </div>
      </div>
    </Modal>
  );
};

/* ── Buy modal ── */
const BuyModal = ({ price, amber, busy, onClose, onConfirm }) => {
  const [qty, setQty] = useState(1);
  const total = qty * price;
  const affordable = amber >= total;
  return (
    <Modal onClose={busy ? () => {} : onClose} testid="buy-fossil-modal">
      <div className="p-6">
        <div className="flex items-center gap-2 text-[#A3C96B]"><Gem size={18} /><h3 className="text-lg font-bold text-white">Comprar Fósiles</h3></div>
        <p className="mt-1 text-sm text-white/45">1 Fósil = {price.toLocaleString()} Amberiums</p>
        <div className="mt-5 flex items-center justify-center gap-4">
          <button data-testid="buy-qty-minus" onClick={() => setQty((q) => Math.max(1, q - 1))} className="w-11 h-11 rounded-xl bg-white/[0.05] hover:bg-white/10 text-white text-xl font-bold border border-white/10">−</button>
          <div className="text-center min-w-[80px]">
            <div data-testid="buy-qty-value" className="text-4xl font-black text-white">{qty}</div>
            <div className="text-[11px] text-white/40">fósiles</div>
          </div>
          <button data-testid="buy-qty-plus" onClick={() => setQty((q) => q + 1)} className="w-11 h-11 rounded-xl bg-white/[0.05] hover:bg-white/10 text-white text-xl font-bold border border-white/10">+</button>
        </div>
        <div className="mt-5 rounded-xl bg-white/[0.03] border border-white/5 p-4 flex items-center justify-between text-sm">
          <span className="text-white/50">Costo total</span>
          <span className={`font-bold ${affordable ? "text-white" : "text-[#E24A4A]"}`}>{total.toLocaleString()} Amberiums</span>
        </div>
        {!affordable && <div className="mt-2 text-xs text-[#E24A4A] text-center">No tienes suficientes Amberiums.</div>}
        <div className="mt-5 grid grid-cols-2 gap-3">
          <button data-testid="buy-cancel-btn" disabled={busy} onClick={onClose} className="rounded-xl bg-white/[0.05] hover:bg-white/[0.1] text-white font-semibold py-3 border border-white/10 disabled:opacity-40">Cancelar</button>
          <button data-testid="buy-confirm-btn" disabled={busy || !affordable} onClick={() => onConfirm(qty)} className="rounded-xl bg-[#34D399] hover:bg-[#2bbd88] text-black font-bold py-3 shadow-lg shadow-emerald-500/20 disabled:opacity-40">{busy ? "Comprando…" : "Comprar"}</button>
        </div>
      </div>
    </Modal>
  );
};

/* ── Transactions modal ── */
const TxModal = ({ items, onClose }) => {
  const KIND = { buy: "Compra", claim_free: "Fósil gratis", resurrect: "Resurrección", admin_grant: "Ajuste admin", admin_set: "Ajuste admin" };
  return (
    <Modal onClose={onClose} testid="fossil-tx-modal">
      <div className="p-6">
        <div className="flex items-center justify-between"><h3 className="text-lg font-bold text-white">Historial de Fósiles</h3><button onClick={onClose} className="text-white/50 hover:text-white"><X size={18} /></button></div>
        <div className="mt-4 space-y-1.5 max-h-[55vh] overflow-y-auto">
          {(!items || items.length === 0) && <div className="text-sm text-white/40 text-center py-8">Sin movimientos todavía.</div>}
          {items?.map((t) => (
            <div key={t.id} className="flex items-center justify-between rounded-lg bg-white/[0.03] border border-white/5 px-3 py-2.5">
              <div>
                <div className="text-sm text-white/90">{KIND[t.kind] || t.kind}</div>
                <div className="text-[11px] text-white/35">{fmtDate(t.created_at)}</div>
              </div>
              <div className={`text-sm font-bold ${t.amount >= 0 ? "text-[#34D399]" : "text-[#E24A4A]"}`}>{t.amount >= 0 ? "+" : ""}{t.amount}</div>
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
};

/* ── Hall of Fame ── */
const HallOfFame = ({ data, onOpen }) => {
  const cats = [
    { key: "longest_survival", label: "Mayor supervivencia", icon: Timer, color: "#38BDF8", stat: (r) => fmtPlaytime(r.playtime_minutes) },
    { key: "most_kills", label: "Más letales", icon: Swords, color: "#E24A4A", stat: (r) => `${r.kills} kills` },
    { key: "biggest", label: "Colosos Prime", icon: Flame, color: "#7CA842", stat: (r) => `${Math.round(r.dino?.growth || 0)}%` },
    { key: "resurrected", label: "Regresados", icon: Crown, color: "#D4AF37", stat: (r) => fmtDate(r.resurrected_at) },
  ];
  if (!data) return null;
  return (
    <div className="mt-14" data-testid="hall-of-fame">
      <div className="flex items-center gap-2 mb-5"><Trophy size={20} className="text-[#D4AF37]" /><h2 className="text-lg font-bold text-white">Salón de la Fama</h2></div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {cats.map((c) => {
          const rows = data[c.key] || [];
          const Icon = c.icon;
          return (
            <div key={c.key} className="rounded-2xl bg-[#141418] border border-white/[0.06] p-4">
              <div className="flex items-center gap-2 mb-3"><Icon size={15} style={{ color: c.color }} /><span className="text-sm font-semibold text-white/80">{c.label}</span></div>
              <div className="space-y-1.5">
                {rows.length === 0 && <div className="text-xs text-white/30 py-4 text-center">Sin datos</div>}
                {rows.map((r, i) => (
                  <button key={r.id} onClick={() => onOpen(r)} className="w-full flex items-center gap-2.5 rounded-lg hover:bg-white/[0.04] px-2 py-1.5 transition-colors text-left">
                    <span className="text-xs font-black w-4" style={{ color: c.color }}>{i + 1}</span>
                    {r.dino?.image ? <img src={r.dino.image} alt="" className="w-7 h-7 object-contain" /> : <Bone size={16} className="text-white/30" />}
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-white/90 truncate">{r.dino?.species_name}</div>
                      <div className="text-[10px] text-white/40 truncate">{r.owner?.persona_name || "—"}</div>
                    </div>
                    <span className="text-[11px] font-semibold" style={{ color: c.color }}>{c.stat(r)}</span>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default function Cementerio() {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [feed, setFeed] = useState(null);
  const [stats, setStats] = useState(null);
  const [fossils, setFossils] = useState(null);
  const [hof, setHof] = useState(null);
  const [filters, setFilters] = useState({ search: "", species: "", status: "", sort: "recent" });
  const [selected, setSelected] = useState(null);
  const [confirmRec, setConfirmRec] = useState(null);
  const [showBuy, setShowBuy] = useState(false);
  const [showTx, setShowTx] = useState(false);
  const [txItems, setTxItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [fx, setFx] = useState(() => (typeof localStorage !== "undefined" ? localStorage.getItem("cem_halloween") !== "0" : true));
  const toggleFx = () => setFx((v) => { const nv = !v; try { localStorage.setItem("cem_halloween", nv ? "1" : "0"); } catch (e) {} return nv; });

  const loadFeed = useCallback(() => {
    if (!user) return;
    const params = {};
    if (filters.search) params.search = filters.search;
    if (filters.species) params.species = filters.species;
    if (filters.status) params.status = filters.status;
    if (filters.sort) params.sort = filters.sort;
    api.cemFeed(params).then((r) => { setFeed(r.data.items); setStats(r.data.stats); }).catch(() => setFeed([]));
  }, [filters, user]);

  const loadFossils = useCallback(() => {
    if (!user) return;
    api.cemFossils().then((r) => setFossils(r.data)).catch(() => {});
  }, [user]);

  useEffect(() => { loadFeed(); }, [loadFeed]);
  useEffect(() => { loadFossils(); }, [loadFossils]);
  useEffect(() => { if (user) api.cemHallOfFame().then((r) => setHof(r.data)).catch(() => {}); }, [user]);

  /* Real-time */
  useCemeterySocket((msg) => {
    if (!msg || !msg.type) return;
    if (msg.type === "cemetery_death" && msg.record) {
      setFeed((prev) => (prev ? [msg.record, ...prev] : [msg.record]));
      setStats((s) => (s ? { ...s, total: s.total + 1, eligible: s.eligible + (msg.record.status === "ELEGIBLE" ? 1 : 0), not_revivable: s.not_revivable + (msg.record.status === "NO_REVIVIBLE" ? 1 : 0) } : s));
      toast(`☠ Nuevo caído: ${msg.record.dino?.species_name}`, { description: msg.record.owner?.persona_name });
    } else if ((msg.type === "cemetery_resurrection" || msg.type === "cemetery_update") && msg.record) {
      setFeed((prev) => prev?.map((r) => (r.id === msg.record.id ? msg.record : r)));
      setSelected((sel) => (sel && sel.id === msg.record.id ? msg.record : sel));
    } else if (msg.type === "cemetery_delete") {
      setFeed((prev) => prev?.filter((r) => r.id !== msg.record_id));
    } else if (msg.type === "fossil_balance") {
      setFossils((f) => (f ? { ...f, fossils: msg.fossils ?? f.fossils, amber_balance: msg.amber_balance ?? f.amber_balance } : f));
    } else if (msg.type === "cemetery_config") {
      setFossils((f) => (f ? { ...f, fossil_price: msg.fossil_price } : f));
    }
  });

  const ownsRecord = (rec) => {
    if (!user || !rec) return false;
    const o = rec.owner || {};
    return (o.user_id && o.user_id === user.id) || (o.steam_id && o.steam_id === user.steam_id);
  };

  const doClaim = () => {
    api.cemClaimFree().then((r) => {
      play("success"); toast.success("¡Fósil gratis reclamado!");
      setFossils((f) => ({ ...f, fossils: r.data.fossils, can_claim_free: false }));
    }).catch((e) => toast.error(e?.response?.data?.detail || "No se pudo reclamar"));
  };

  const doBuy = (qty) => {
    setBusy(true);
    api.cemBuyFossils(qty).then((r) => {
      play("success"); toast.success(`Compraste ${qty} Fósil${qty > 1 ? "es" : ""}`);
      setFossils((f) => ({ ...f, fossils: r.data.fossils, amber_balance: r.data.amber_balance }));
      setShowBuy(false); refresh && refresh();
    }).catch((e) => toast.error(e?.response?.data?.detail || "No se pudo comprar")).finally(() => setBusy(false));
  };

  const doResurrect = () => {
    if (!confirmRec) return;
    setBusy(true);
    api.cemResurrect(confirmRec.id).then((r) => {
      play("success"); toast.success(`¡${confirmRec.dino?.species_name} resucitado y devuelto a tu bóveda!`);
      setFeed((prev) => prev?.map((x) => (x.id === r.data.record.id ? r.data.record : x)));
      setFossils((f) => ({ ...f, fossils: r.data.fossils, cooldown_active: true, cooldown_until: r.data.cooldown_until }));
      setConfirmRec(null); setSelected(null); refresh && refresh();
    }).catch((e) => toast.error(e?.response?.data?.detail || "No se pudo resucitar")).finally(() => setBusy(false));
  };

  const openTx = () => { api.cemTransactions().then((r) => { setTxItems(r.data.items); setShowTx(true); }).catch(() => setShowTx(true)); };

  if (!user) return <div className="max-w-7xl mx-auto px-6 py-14"><SignInPrompt title="Tu cementerio te espera" sub="Inicia sesión para ver tus dinos caídos, tus Fósiles y resucitar a los tuyos. Solo tú puedes ver tu propio cementerio." /></div>;
  if (feed === null) return <PageLoader label="Entrando al cementerio" />;

  const STAT_CARDS = [
    { label: "Caídos", value: stats?.total ?? 0, icon: Skull, color: "#94A3B8" },
    { label: "Elegibles", value: stats?.eligible ?? 0, icon: Sparkles, color: "#34D399" },
    { label: "Resucitados", value: stats?.resurrected ?? 0, icon: Crown, color: "#7CA842" },
    { label: "No revivibles", value: stats?.not_revivable ?? 0, icon: ShieldOff, color: "#E24A4A" },
  ];

  return (
    <div className="relative max-w-7xl mx-auto px-6 py-12" data-testid="cementerio-page">
      {fx && <SpiderRunner />}
      {fx && <FlyingCritters />}
      {fx && (
        <>
          {/* Telarañas fijas en las esquinas superiores izquierda y derecha */}
          <CornerWeb corner="tl" size={150} className="absolute top-16 left-0 z-30 opacity-60" />
          <CornerWeb corner="tr" size={150} className="absolute top-16 right-0 z-30 opacity-60" />
          {/* Neblina tóxica detrás del dosel (ambiente de muerte) */}
          <div aria-hidden className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-0 w-screen h-72 z-0"
            style={{ background: "radial-gradient(120% 100% at 50% -10%, rgba(84,120,44,0.16) 0%, rgba(20,26,16,0.10) 35%, transparent 70%)" }} />
          {/* Dosel de enredaderas cubriendo TODO el cementerio (estilo panteón) */}
          <div aria-hidden data-testid="cemetery-vine-canopy" className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-0 w-screen z-20">
            <VineStrip height={280} className="opacity-95" />
          </div>
          <VineSide side="left" className="absolute left-0 top-52 h-[65%] z-0 opacity-40 hidden lg:block" />
          <VineSide side="right" className="absolute right-0 top-52 h-[65%] z-0 opacity-40 hidden lg:block" />
        </>
      )}
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="relative z-10 overflow-hidden rounded-3xl border border-white/[0.06] bg-gradient-to-br from-[#141418] to-[#0e0e11] p-8 mb-8 mt-6">
        {/* Fósil levitando con pulso de fondo */}
        <div className="pointer-events-none absolute right-6 sm:right-12 top-1/2 -translate-y-1/2 hidden sm:flex items-center justify-center">
          <motion.div
            aria-hidden
            className="absolute rounded-full"
            style={{ width: 260, height: 260, background: "radial-gradient(circle, rgba(124,168,66,0.35) 0%, rgba(124,168,66,0.08) 45%, transparent 70%)" }}
            animate={{ scale: [1, 1.18, 1], opacity: [0.5, 0.85, 0.5] }}
            transition={{ duration: 3.4, repeat: Infinity, ease: "easeInOut" }}
          />
          <motion.img
            src="/fossil.png"
            alt="Fósil"
            data-testid="cemetery-hero-fossil"
            className="relative w-44 lg:w-56 object-contain"
            style={{ filter: "drop-shadow(0 22px 30px rgba(0,0,0,0.55)) drop-shadow(0 0 18px rgba(124,168,66,0.35))" }}
            animate={{ y: [0, -16, 0], rotate: [-2, 2, -2] }}
            transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
          />
        </div>
        <div className="relative">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="inline-flex items-center gap-2 rounded-full bg-white/[0.05] border border-white/10 px-3 py-1 text-[11px] uppercase tracking-widest text-white/50">
              <span className="w-1.5 h-1.5 rounded-full bg-[#34D399] animate-pulse" /> Registro en tiempo real
            </div>
            <button
              onClick={toggleFx}
              data-testid="halloween-toggle"
              title="Activar o desactivar los efectos de terror (arañas, enredaderas, bichos)"
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-wider transition-colors ${fx ? "border-[#7CA842]/40 bg-[#7CA842]/10 text-[#A3C96B]" : "border-white/10 bg-white/[0.03] text-white/45 hover:text-white/70"}`}
            >
              <Ghost size={13} /> Modo Halloween: {fx ? "ON" : "OFF"}
            </button>
          </div>
          <h1 className="mt-4 text-4xl sm:text-5xl font-black text-white tracking-tight flex items-center gap-3"><Skull className="text-[#7CA842]" size={40} /> Cementerio</h1>
          <p className="mt-2 text-white/45 max-w-2xl">Cada dino caído queda inmortalizado aquí. Usa <b className="text-[#A3C96B]">Fósiles</b> para resucitar a los tuyos y devolverlos a la bóveda con todos sus stats, mutaciones y skin.</p>
          <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-3">
            {STAT_CARDS.map((s) => (
              <div key={s.label} className="rounded-xl bg-white/[0.03] border border-white/5 p-3">
                <s.icon size={16} style={{ color: s.color }} />
                <div className="mt-1.5 text-2xl font-black text-white">{s.value}</div>
                <div className="text-[11px] text-white/40">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </motion.div>

      <div className="relative z-10 grid lg:grid-cols-[1fr_320px] gap-8">
        {/* Main */}
        <div>
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2.5 mb-6" data-testid="cemetery-filters">
            <div className="relative flex-1 min-w-[220px]">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
              <input
                data-testid="cemetery-search"
                value={filters.search}
                onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
                placeholder="Buscar especie, dueño, asesino…"
                className="w-full bg-[#141418] border border-white/10 focus:border-[#34D399]/50 rounded-xl pl-9 pr-3 py-2.5 text-sm text-white placeholder:text-white/30 outline-none transition-colors"
              />
            </div>
            <select data-testid="filter-species" value={filters.species} onChange={(e) => setFilters((f) => ({ ...f, species: e.target.value }))} className="bg-[#141418] border border-white/10 rounded-xl px-3 py-2.5 text-sm text-white/80 outline-none">
              {SPECIES_FILTERS.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
            </select>
            <select data-testid="filter-sort" value={filters.sort} onChange={(e) => setFilters((f) => ({ ...f, sort: e.target.value }))} className="bg-[#141418] border border-white/10 rounded-xl px-3 py-2.5 text-sm text-white/80 outline-none">
              {CEM_SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>

          {/* Status tabs */}
          <div className="flex flex-wrap gap-2 mb-6">
            {STATUS_FILTERS.map((s) => (
              <button
                key={s.id}
                data-testid={`status-tab-${s.id || "all"}`}
                onClick={() => setFilters((f) => ({ ...f, status: s.id }))}
                className={`text-xs font-semibold rounded-full px-3.5 py-1.5 border transition-colors ${filters.status === s.id ? "bg-[#34D399] text-black border-[#34D399]" : "bg-white/[0.03] text-white/60 border-white/10 hover:border-white/20"}`}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* Grid */}
          {feed.length === 0 ? (
            <div className="rounded-2xl border border-white/[0.06] bg-[#141418] p-16 text-center">
              <Skull size={48} className="mx-auto text-white/15" />
              <p className="mt-4 text-white/40">No hay caídos que coincidan con tu búsqueda.</p>
            </div>          ) : (
            <motion.div layout className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              <AnimatePresence>
                {feed.map((rec) => <DinoCard key={rec.id} rec={rec} onOpen={setSelected} fx={fx} />)}
              </AnimatePresence>
            </motion.div>
          )}

          <HallOfFame data={hof} onOpen={setSelected} />
        </div>

        {/* Sidebar */}
        <div className="lg:sticky lg:top-24 self-start space-y-4">
          {user ? (
            fossils && <FossilPanel fossils={fossils} onBuy={() => setShowBuy(true)} onClaim={doClaim} onOpenTx={openTx} />
          ) : (
            <div className="rounded-2xl border border-white/[0.06] bg-[#141418] p-6 text-center">
              <img src="/fossil.png" alt="Fósil" className="mx-auto w-12 object-contain drop-shadow-[0_0_10px_rgba(124,168,66,0.4)]" />
              <p className="mt-3 text-sm text-white/50">Inicia sesión para ver tus Fósiles y resucitar a tus dinos caídos.</p>
            </div>
          )}
          <div className="rounded-2xl border border-white/[0.06] bg-[#141418] p-5">
            <div className="flex items-center gap-2 text-white/70 mb-3"><Droplet size={15} className="text-[#38BDF8]" /><span className="text-sm font-semibold">Reglas del más allá</span></div>
            <ul className="space-y-2 text-xs text-white/45">
              <li className="flex gap-2"><ChevronRight size={13} className="text-[#34D399] mt-0.5 shrink-0" /> 1 Fósil = 1 resurrección. Solo el dueño puede resucitar.</li>
              <li className="flex gap-2"><ChevronRight size={13} className="text-[#34D399] mt-0.5 shrink-0" /> Cooldown de 24h tras cada resurrección.</li>
              <li className="flex gap-2"><ChevronRight size={13} className="text-[#34D399] mt-0.5 shrink-0" /> 1 Fósil gratis cada mes calendario.</li>
              <li className="flex gap-2"><Clock size={13} className="text-[#38BDF8] mt-0.5 shrink-0" /> El dino resucitado no se puede redimir por 2h (anti revenge-kill).</li>
              <li className="flex gap-2"><ShieldOff size={13} className="text-[#E24A4A] mt-0.5 shrink-0" /> Ahogamiento en combate = no revivible… salvo el Deinosuchus.</li>
              <li className="flex gap-2"><Skull size={13} className="text-white/40 mt-0.5 shrink-0" /> Tu cementerio es privado: solo tú ves tus dinos caídos.</li>
            </ul>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {selected && <ProfileModal key="profile" rec={selected} onClose={() => setSelected(null)} canResurrect={ownsRecord(selected)} onResurrect={(r) => { setConfirmRec(r); }} />}
        {confirmRec && <ConfirmResurrect key="confirm" rec={confirmRec} busy={busy} onClose={() => setConfirmRec(null)} onConfirm={doResurrect} />}
        {showBuy && fossils && <BuyModal key="buy" price={fossils.fossil_price} amber={fossils.amber_balance} busy={busy} onClose={() => setShowBuy(false)} onConfirm={doBuy} />}
        {showTx && <TxModal key="tx" items={txItems} onClose={() => setShowTx(false)} />}
      </AnimatePresence>
    </div>
  );
}
