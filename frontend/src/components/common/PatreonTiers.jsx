import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Flame, Heart, Star, Check, ExternalLink, Crown, Gem, CalendarClock, Receipt, CreditCard, Gift } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { api, externalRedirect } from "@/lib/api";
import { toast } from "sonner";
import StreamerPack from "@/components/common/StreamerPack";

// Suscribirse opens the Patreon checkout for the tier (rid = live Patreon tier id,
// read from the campaign API 2026-07-17). Account LINKING stays in Cuentas Conectadas.
const PATREON_CAMPAIGN_URL = "https://www.patreon.com/LaislaNublar";
const patreonCheckoutUrl = (rid) => (rid ? `https://www.patreon.com/checkout/LaislaNublar?rid=${rid}` : PATREON_CAMPAIGN_URL);

// 5 subscription tiers — perk lists mirror the Patreon campaign copy exactly.
const TIERS = [
  { id: "apex", name: "Apex", rid: "29114889", tagline: "La experiencia definitiva", icon: Flame, accent: "#F97316", amber: 80000, boost: "3.5x", popular: true,
    perks: ["+80,000 Amberium cada dos semanas", "Multiplicador de 3.5x PrimeMeat", "Rol de Supporter en Discord", "Acceso al creador de Skins guardadas y personalizadas", "Invitaciones especiales a eventos y pruebas", "Canal exclusivo para miembros de Patreon"] },
  { id: "elder", name: "Elder", rid: "29114975", tagline: "Para veteranos de la isla", icon: Crown, accent: "#A855F7", amber: 60000, boost: "3x",
    perks: ["+60,000 Amberium cada dos semanas", "Multiplicador de 3.0x PrimeMeat", "Rol de Supporter en Discord", "Acceso al creador de Skins guardadas y personalizadas", "Canal exclusivo para miembros de Patreon"] },
  { id: "adult", name: "Adult", rid: "29115045", tagline: "El paquete equilibrado", icon: Star, accent: "#8B5CF6", amber: 40000, boost: "2.5x",
    perks: ["+40,000 Amberium cada dos semanas", "Potenciador de 2.5x PrimeMeat", "Acceso al creador de Skins guardadas y personalizadas", "Rol de Supporter en Discord", "Canal exclusivo para miembros de Patreon"] },
  { id: "sub", name: "Sub Adult", rid: "29115074", tagline: "Sube de nivel tu juego", icon: Heart, accent: "#F1465A", amber: 28000, boost: "2x",
    perks: ["+28,000 Amberium cada dos semanas", "Acceso al creador de Skins guardadas y personalizadas", "Potenciador de 2.0x PrimeMeat", "Canal exclusivo para miembros de Patreon", "Rol de Supporter en Discord"] },
  { id: "juvie", name: "Juvie", rid: "29115094", tagline: "Empieza tu apoyo", icon: Gem, accent: "#22C55E", amber: 18000, boost: "1.5x",
    perks: ["+18,000 Amberium cada dos semanas", "Potenciador de 1.5x PrimeMeat", "Rol de Supporter en Discord", "Canal exclusivo para miembros de Patreon"] },
];

const TIER_BY_ID = Object.fromEntries(TIERS.map((t) => [t.id, t]));

function TierCard({ t, big, myTier, onSubscribe }) {
  const Icon = t.icon;
  const mine = myTier && myTier.toLowerCase() === t.id;
  return (
    <div className="relative overflow-hidden" data-testid={`patreon-tier-${t.id}`}
      style={{ borderRadius: 4, border: `1px solid ${t.accent}${big ? "" : "55"}`, background: "#0b0b0e", boxShadow: big ? `0 0 40px ${t.accent}22` : "none" }}>
      <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(120% 90% at 100% 0%, ${t.accent}18, transparent 60%)` }} />
      {t.popular && (
        <div className="relative flex items-center gap-1.5 px-5 pt-4 text-[11px] font-extrabold uppercase tracking-widest" style={{ color: t.accent }}>
          <Star size={12} fill={t.accent} /> Más popular
        </div>
      )}
      <div className={`relative flex items-center gap-3 px-5 ${t.popular ? "pt-2" : "pt-5"} pb-4`}>
        <div className="w-12 h-12 flex items-center justify-center shrink-0" style={{ borderRadius: 6, background: `${t.accent}22`, color: t.accent }}>
          <Icon size={big ? 28 : 24} />
        </div>
        <div>
          <h3 className="font-display font-extrabold text-2xl leading-none" style={{ color: t.accent }}>{t.name}</h3>
          <p className="text-xs text-muted-foreground mt-1">{t.tagline}</p>
        </div>
      </div>

      <div className="relative grid grid-cols-2 gap-2 px-5">
        <div className="p-3" style={{ borderRadius: 4, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.02)" }}>
          <div className="flex items-center gap-1.5">
            <img src={MEDIA.coinVip} alt="" className="w-4 h-4 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
            <span className="font-mono font-extrabold text-lg" style={{ color: "#EAB308" }}>{t.amber.toLocaleString()}</span>
          </div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">Amberium quincenal</p>
        </div>
        <div className="p-3" style={{ borderRadius: 4, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.02)" }}>
          <span className="font-mono font-extrabold text-lg text-emerald">{t.boost}</span>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">Boost de monedas</p>
        </div>
      </div>

      <div className="relative px-5 py-4 space-y-2">
        {t.perks.map((p, i) => (
          <div key={i} className="flex items-start gap-2 text-[13px]">
            <Check size={15} className="shrink-0 mt-0.5" style={{ color: t.accent }} />
            <span className="text-foreground/85">{p}</span>
          </div>
        ))}
      </div>

      <div className="relative px-5 pb-5 flex items-center justify-between gap-3">
        {mine ? (
          <span className="inline-flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-wide px-3 py-2.5" style={{ borderRadius: 4, color: t.accent, border: `1px solid ${t.accent}`, background: `${t.accent}18` }} data-testid={`patreon-tier-${t.id}-current`}>
            <Crown size={13} /> Tu nivel
          </span>
        ) : <span />}
        <button onClick={() => onSubscribe(t)} data-testid={`patreon-tier-${t.id}-subscribe`}
          className="inline-flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-widest px-4 py-2.5 transition-all hover:brightness-110"
          style={{ borderRadius: 4, border: `1px solid ${t.accent}`, color: t.accent }}>
          Suscribirse <ExternalLink size={12} />
        </button>
      </div>
    </div>
  );
}

const RED = "#E5484D";
const GOLD = "#EAB308";
const TEAL = "#2DD4BF";

// Patreon keeps a server-gifted free membership as the member's ACTIVE membership and
// never bills someone who already holds the tier — so while the gift stands, checkout
// totals $0 and no purchase can go through. Only the member (or the campaign owner)
// can end the gift; the site's job is to say so instead of letting the $0 loop read
// as "buying is broken". Exported for the mounted test.
const PATREON_MEMBERSHIPS_URL = "https://www.patreon.com/settings/memberships";

export function GiftedMembershipNotice({ user }) {
  const pat = user && user.patreon;
  if (!pat || !pat.linked || pat.patron_status !== "gifted_no_charge") return null;
  const openMemberships = () => {
    // Same popup-safe open as Suscribirse: never pass "noopener" (null on success);
    // sever opener by hand; blocked popup falls back to a top-level navigation.
    let win = null;
    try { win = window.open(PATREON_MEMBERSHIPS_URL, "_blank"); } catch { win = null; }
    if (win) { try { win.opener = null; } catch { /* cross-origin — already unreachable */ } }
    else externalRedirect(PATREON_MEMBERSHIPS_URL);
  };
  return (
    <div className="relative overflow-hidden" data-testid="patreon-gifted-notice"
      style={{ borderRadius: 6, border: `1px solid ${GOLD}66`, background: "#0b0b0e", boxShadow: `0 0 45px ${GOLD}14` }}>
      <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(120% 100% at 100% 0%, ${GOLD}10, transparent 55%)` }} />
      <div className="relative p-5 sm:p-6">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-9 h-9 flex items-center justify-center shrink-0" style={{ borderRadius: 6, background: `${GOLD}1c`, color: GOLD }}>
            <Gift size={20} />
          </div>
          <h3 className="font-display font-extrabold text-xl leading-tight" style={{ color: GOLD }}>
            Tienes una membresía de regalo activa en Patreon
          </h3>
        </div>
        <p className="text-sm text-foreground/85 leading-relaxed">
          El servidor te regaló una membresía gratis. Mientras ese regalo siga activo, Patreon no puede
          cobrarte: al intentar comprar un nivel, el pago sale en <b style={{ color: GOLD }}>$0</b> y la compra
          no se realiza. La membresía de regalo ya no incluye los beneficios del servidor.
        </p>
        <p className="text-sm text-foreground/85 leading-relaxed mt-2.5">
          Para comprar una membresía de verdad: <b>primero cancela la membresía de regalo</b> en Patreon
          (Ajustes → Membresías → La Isla Nublar → Cancelar), o pide al staff en Discord que la retire.
          Después vuelve aquí y pulsa <b>Suscribirse</b> en tu nivel.
        </p>
        <button onClick={openMemberships} data-testid="patreon-gifted-open-memberships"
          className="mt-4 inline-flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-widest px-4 py-2.5 transition-all hover:brightness-110"
          style={{ borderRadius: 4, border: `1px solid ${GOLD}`, color: GOLD }}>
          Abrir mis membresías en Patreon <ExternalLink size={12} />
        </button>
      </div>
    </div>
  );
}

function pad2(n) { return String(n).padStart(2, "0"); }

function fmtDate(iso) {
  if (!iso) return null;
  try { return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return null; }
}

function daysUntil(iso) {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  if (isNaN(ms)) return null;
  return Math.max(0, Math.ceil(ms / 86400000));
}

function ActivePatronCard() {
  const [status, setStatus] = useState(null);
  const [secs, setSecs] = useState(null);
  const { play } = useSound();
  useEffect(() => {
    let alive = true;
    api.patreonStatus().then((r) => { if (alive) { setStatus(r.data); setSecs(r.data.seconds_remaining); } }).catch(() => {});
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (secs == null) return undefined;
    const t = setInterval(() => setSecs((s) => (s > 0 ? s - 1 : 0)), 1000);
    return () => clearInterval(t);
  }, [secs == null]);
  if (!status || !status.active) return null;

  const t = TIER_BY_ID[status.tier_key] || {};
  const Icon = t.icon || Flame;
  const s = secs == null ? 0 : secs;
  const parts = [["D", Math.floor(s / 86400)], ["H", Math.floor((s % 86400) / 3600)], ["M", Math.floor((s % 3600) / 60)], ["S", Math.floor(s % 60)]];
  const renewalDays = daysUntil(status.next_renewal);

  const disconnect = async () => {
    play("click");
    try { await api.patreonUnlink(); toast.success("Patreon desvinculado"); window.location.reload(); }
    catch { toast.error("No se pudo desvincular"); }
  };

  const Row = ({ icon: RowIcon, label, value, extra, valueColor }) => (
    <div className="flex items-center gap-2.5 text-sm">
      <RowIcon size={16} className="text-muted-foreground shrink-0" />
      <span className="text-muted-foreground">{label}</span>
      {value != null && <span className="font-semibold" style={valueColor ? { color: valueColor } : undefined}>{value}</span>}
      {extra && <span className="text-muted-foreground/70 text-xs">{extra}</span>}
    </div>
  );

  return (
    <div className="relative overflow-hidden" data-testid="patreon-active-card"
      style={{ borderRadius: 6, border: `1px solid ${RED}66`, background: "#0b0b0e", boxShadow: `0 0 45px ${RED}18` }}>
      <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(120% 100% at 100% 0%, ${RED}12, transparent 55%)` }} />
      <div className="relative p-6 sm:p-7">
        {/* header */}
        <div className="flex items-start gap-5 mb-6">
          <div className="w-20 h-20 flex items-center justify-center shrink-0" style={{ borderRadius: 6, background: "#1a0d0e", border: `1px solid ${RED}55` }}>
            <Icon size={40} style={{ color: "#F97316" }} />
          </div>
          <div className="pt-1">
            <p className="text-[11px] font-extrabold uppercase tracking-[0.25em] text-muted-foreground">Active Patron</p>
            <h3 className="font-display font-extrabold text-4xl leading-none mt-1" style={{ color: RED }} data-testid="patreon-active-tier">{t.name || status.tier_name}</h3>
            {status.supporting_since && <p className="text-sm text-muted-foreground mt-2">Supporting since {fmtDate(status.supporting_since)}</p>}
          </div>
        </div>

        {/* stat boxes */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div className="p-4" style={{ borderRadius: 6, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.015)" }}>
            <div className="flex items-center gap-2">
              <img src={MEDIA.coinVip} alt="" className="w-6 h-6 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
              <span className="font-display font-extrabold text-2xl" style={{ color: GOLD }}>{(status.amber_per_payout || 0).toLocaleString()}</span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1.5">Amberium bi-weekly</p>
          </div>
          <div className="p-4" style={{ borderRadius: 6, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.015)" }}>
            <div className="flex items-center gap-2">
              <img src={MEDIA.coinNormal} alt="" className="w-6 h-6 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
              <span className="font-display font-extrabold text-2xl" style={{ color: TEAL }}>{status.boost || t.boost} Boost</span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1.5">PrimeMeat multiplier</p>
          </div>
        </div>

        {/* payout countdown */}
        <div className="p-4 mb-5" style={{ borderRadius: 6, border: `1px solid ${GOLD}44`, background: `${GOLD}0a` }}>
          <div className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.2em] mb-3" style={{ color: GOLD }}>
            <img src={MEDIA.coinVip} alt="" className="w-4 h-4 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
            Next Amberium Payout
          </div>
          <div className="flex items-center flex-wrap gap-x-3 gap-y-2" data-testid="patreon-countdown">
            {parts.map(([u, val], i) => (
              <React.Fragment key={u}>
                <div className="flex items-baseline gap-1.5">
                  <span className="font-mono font-extrabold text-3xl sm:text-4xl leading-none" style={{ color: GOLD }}>{pad2(val)}</span>
                  <span className="text-xs font-bold text-muted-foreground">{u}</span>
                </div>
                {i < 3 && <span className="text-2xl font-bold text-muted-foreground/50 leading-none">:</span>}
              </React.Fragment>
            ))}
            <span className="text-sm text-muted-foreground/70 ml-1">until {(status.amber_per_payout || 0).toLocaleString()} Amberium</span>
          </div>
        </div>

        {/* info rows */}
        <div className="space-y-2.5">
          {status.next_renewal && <Row icon={CalendarClock} label="Next renewal:" value={fmtDate(status.next_renewal)} valueColor={TEAL} extra={renewalDays != null ? `(in ${renewalDays}d)` : null} />}
          {status.last_payment && <Row icon={Receipt} label="Last payment:" value={fmtDate(status.last_payment)} />}
          {status.pledge && <Row icon={CreditCard} label="Pledge:" value={status.pledge} />}
        </div>

        {/* footer */}
        <div className="mt-5 pt-4 border-t border-white/10 flex items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground/70">
            {status.patreon_name ? `${status.patreon_name} · ` : ""}Synced {fmtDate(status.synced_at) || "—"}
          </p>
          <button onClick={disconnect} data-testid="patreon-disconnect-btn" className="text-sm font-semibold transition-all hover:brightness-110" style={{ color: RED }}>
            Disconnect
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PatreonTiers() {
  const { user } = useAuth();
  const { play } = useSound();
  const myTier = user?.patreon?.tier_name;

  // Straight to the Patreon subscribe page for the clicked tier — no API hop, nothing to fail.
  // New tab (the button shows an external-link icon); if a blocker eats it, navigate top-level.
  // NOTE: never pass "noopener" in the features arg — window.open then returns null ON SUCCESS,
  // which would fire the blocked-fallback too and hijack this tab. Sever opener by hand instead.
  const onSubscribe = (t) => {
    play("click");
    const url = patreonCheckoutUrl(t.rid);
    let win = null;
    try { win = window.open(url, "_blank"); } catch { win = null; }
    if (win) { try { win.opener = null; } catch { /* cross-origin — already unreachable */ } }
    else externalRedirect(url);
  };

  const apex = TIERS[0];
  const rest = TIERS.slice(1);

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
      className="space-y-4" data-testid="patreon-tab">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-gold/15 text-gold border border-gold/30 inline-flex items-center gap-1"><Heart size={10} /> PATREON</span>
        <p className="text-sm text-muted-foreground">Elige un nivel de apoyo y desbloquea beneficios en el servidor.</p>
      </div>
      {/* The per-tier perk bullets mirror the Patreon campaign copy word for word, so the
          payout timing is stated once HERE instead of being edited into all five lists. */}
      <p className="text-xs text-muted-foreground/90 -mt-1" data-testid="patreon-instant-note">
        Recibes el <b className="text-gold">Amberium de tu nivel al momento de suscribirte</b>, y el siguiente pago cada 14 días.
        {" "}Si <b className="text-gold">mejoras a un nivel superior</b> te añadimos la diferencia al instante, y tu fecha de pago no cambia.
      </p>
      <GiftedMembershipNotice user={user} />
      <ActivePatronCard />
      <TierCard t={apex} big myTier={myTier} onSubscribe={onSubscribe} />
      <div className="grid sm:grid-cols-2 gap-4">
        {rest.map((t) => <TierCard key={t.id} t={t} myTier={myTier} onSubscribe={onSubscribe} />)}
      </div>

      {/* Free, application-only Streamer Pack — its own section below the paid tiers */}
      <div className="pt-2 mt-2 border-t border-white/10" />
      <StreamerPack />
    </motion.div>
  );
}
