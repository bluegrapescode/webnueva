import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CalendarClock, Loader2, Trophy } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { GOLD, rewardSpoken } from "@/components/battlepass/RewardCard";
import { SeasonHeader, msLeft } from "@/components/battlepass/SeasonHeader";
import { RewardTrack } from "@/components/battlepass/RewardTrack";
import { PurchaseModal } from "@/components/battlepass/PurchaseModal";
import { DinoPicker } from "@/components/battlepass/DinoPicker";
import { TokenPanel } from "@/components/battlepass/TokenPanel";
import { BpSkinsStrip } from "@/components/battlepass/BpSkinsStrip";
import { ClaimBurst } from "@/components/battlepass/ClaimBurst";

const POLL_EVERY_MS = 2500;
const POLL_MAX_TRIES = 48; // 48 x 2.5 s = 2 minutes
const BANNER_DAYS = 3;

// Drop the one-shot Stripe return marker so a refresh does not re-run the poll,
// while leaving ?tab=battlepass (and anything else) intact.
function stripSessionParam() {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("bp_session")) return;
    url.searchParams.delete("bp_session");
    window.history.replaceState({}, "", url.pathname + (url.searchParams.toString() ? `?${url.searchParams}` : "") + url.hash);
  } catch (e) { /* history blocked — harmless, the poll is ref-guarded anyway */ }
}

export function BattlePassSection() {
  const { user, applyBalance } = useAuth();
  const { play } = useSound();

  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [busyKey, setBusyKey] = useState(null);
  const [claimingAll, setClaimingAll] = useState(false);
  const [purchaseOpen, setPurchaseOpen] = useState(false);
  const [picker, setPicker] = useState(null);
  const [burst, setBurst] = useState(null);
  const [tokenKey, setTokenKey] = useState(0);
  const [checkingPayment, setCheckingPayment] = useState(false);

  const claimLockRef = useRef(null);
  const pollStartedRef = useRef(false);
  // Identity, not the object: `user` is replaced on every balance change, and
  // keying the effects below on the object would re-flash the skeleton after a
  // claim and cancel an in-flight payment poll.
  const userId = user?.id;

  const load = useCallback(async (silent) => {
    if (!silent) setLoading(true);
    try {
      const r = await api.bpStatus();
      setStatus(r.data);
      setFailed(false);
    } catch (e) {
      if (!silent) setFailed(true);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { if (userId) load(false); }, [userId, load]);

  // Every burst carries its own id + lifetime, so a second claim replaces the
  // first cleanly and the timer is scoped to the effect instead of a ref.
  const showBurst = useCallback((payload, ms) => {
    setBurst({ ...payload, id: Date.now(), ms: ms || 2200 });
  }, []);

  useEffect(() => {
    if (!burst) return undefined;
    const t = setTimeout(() => setBurst(null), burst.ms);
    return () => clearTimeout(t);
  }, [burst]);

  // ── Stripe return ────────────────────────────────────────────────────────
  // Checkout sends the player back with ?bp_session=…; the pass only flips once
  // the webhook has been verified server-side, so poll for that answer instead
  // of trusting the redirect.
  useEffect(() => {
    if (!userId || pollStartedRef.current) return undefined;
    let sid = null;
    try { sid = new URLSearchParams(window.location.search).get("bp_session"); } catch (e) { sid = null; }
    if (!sid) return undefined;
    pollStartedRef.current = true;
    setCheckingPayment(true);

    let cancelled = false;
    let timer = null;
    let tries = 0;

    const stop = () => { setCheckingPayment(false); stripSessionParam(); };

    const tick = async () => {
      if (cancelled) return;
      tries += 1;
      try {
        const r = await api.bpPayment(sid);
        const st = r.data?.payment_status;
        if (st === "paid") {
          stop();
          play("purchase");
          toast.success("¡Pase activado! Ya puedes reclamar la fila del pase.");
          load(true);
          setTokenKey((k) => k + 1);
          return;
        }
        if (st === "expired") {
          stop();
          play("error");
          toast.error("El pago expiró y no se cobró nada. Puedes volver a intentarlo cuando quieras.");
          return;
        }
      } catch (e) { /* transient failure is not an answer — keep polling */ }
      if (tries >= POLL_MAX_TRIES) {
        stop();
        toast("Stripe todavía no confirma el pago. Si ya pagaste, el pase se activa solo en cuanto llegue la confirmación.");
        return;
      }
      timer = setTimeout(tick, POLL_EVERY_MS);
    };

    timer = setTimeout(tick, 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [userId, load, play]);

  // ── derived ──────────────────────────────────────────────────────────────
  // v2 rows (regular_track/premium_track); the old names ride as fallbacks so a
  // mid-deploy mix of bundle and backend never blanks the page.
  const regularTrack = useMemo(
    () => status?.regular_track || status?.free_track || [], [status]);
  const premiumTrack = useMemo(
    () => status?.premium_track || status?.pass_track || [], [status]);

  // The apex roster ({slug,name,rarity}) — feeds the track legend, the premium
  // picker's ÁPEX badges and the regular picker's locked section.
  const apexSpecies = useMemo(() => status?.dino_bands?.apex || [], [status]);

  const nameBySlug = useMemo(() => {
    const out = {};
    const bands = status?.dino_bands || {};
    Object.keys(bands).forEach((k) => {
      (bands[k] || []).forEach((sp) => { if (sp && sp.slug) out[sp.slug] = sp.name || sp.slug; });
    });
    return out;
  }, [status]);

  const pendingPicks = useMemo(() => {
    if (!status) return 0;
    const hasAnyPass = status.tier === "regular" || status.tier === "premium_plus";
    const count = (cells, track) => (cells || []).filter((c) =>
      c.type === "dino" && !c.slug &&
      c.level <= status.level &&
      !status.claimed?.[`${track}:${c.level}`] &&
      hasAnyPass &&
      !(track === "premium" && status.tier !== "premium_plus")
    ).length;
    return count(regularTrack, "regular") + count(premiumTrack, "premium");
  }, [status, regularTrack, premiumTrack]);

  const daysLeft = useMemo(() => {
    const ms = msLeft(status?.season?.ends_at);
    return ms == null ? null : ms / 86400000;
  }, [status]);

  // ── actions ──────────────────────────────────────────────────────────────
  const doClaim = useCallback(async (track, cell, choice) => {
    const key = `${track}:${cell.level}`;
    if (claimLockRef.current) return;
    claimLockRef.current = key;
    setBusyKey(key);
    try {
      const body = { track, level: cell.level };
      if (choice) body.choice = choice;
      const r = await api.bpClaim(body);
      if (r.data?.ok) {
        applyBalance(r.data);
        play("reward");
        setPicker(null);
        showBurst({ reward: r.data.reward });
        load(true);
        if (cell.type === "token") setTokenKey((k) => k + 1);
      } else {
        play("error");
        toast.error(r.data?.error || "No se pudo reclamar esta recompensa");
      }
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || e?.response?.data?.error || "No se pudo reclamar esta recompensa");
    } finally {
      claimLockRef.current = null;
      setBusyKey(null);
    }
  }, [applyBalance, play, load, showBurst]);

  // A dino cell is a choice: open the picker first, claim after the pick.
  const onClaim = useCallback((track, cell) => {
    if (cell.type === "dino" && !cell.slug) {
      play("open");
      setPicker({ track, cell });
      return;
    }
    doClaim(track, cell, null);
  }, [doClaim, play]);

  const claimAll = useCallback(async () => {
    if (claimingAll) return;
    setClaimingAll(true);
    try {
      const r = await api.bpClaimAll();
      const rows = r.data?.claimed || [];
      if (r.data?.ok === false) {
        play("error");
        toast.error(r.data?.error || "No se pudo reclamar");
      } else if (rows.length === 0) {
        toast("No hay nada que reclamar automáticamente. Los dinos se eligen uno a uno.");
      } else {
        applyBalance(r.data);
        play("reward");
        const lines = rows.slice(0, 6).map((c) =>
          `Nivel ${c.level} · ${rewardSpoken(c.reward || {}, c.track, status?.tier, nameBySlug)}`
        );
        if (rows.length > 6) lines.push(`y ${rows.length - 6} más`);
        showBurst({ title: rows.length === 1 ? "1 recompensa reclamada" : `${rows.length} recompensas reclamadas`, effects: lines }, 3200);
        setTokenKey((k) => k + 1);
      }
      load(true);
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || e?.response?.data?.error || "No se pudo reclamar");
    } finally {
      setClaimingAll(false);
    }
  }, [claimingAll, applyBalance, play, load, showBurst, status, nameBySlug]);

  const onEffects = useCallback((effects) => {
    showBurst({ title: "Token aplicado", effects: effects && effects.length ? effects : ["El token se aplicó correctamente."] }, 3200);
  }, [showBurst]);

  // ── render ───────────────────────────────────────────────────────────────
  if (!user) {
    return (
      <motion.div key="battlepass" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }} data-testid="battlepass-tab">
        <SignInPrompt title="Pase de Batalla" sub="Inicia sesión para ver tu nivel, tus recompensas y tus tokens." />
      </motion.div>
    );
  }

  if (loading) {
    return (
      <motion.div key="battlepass" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-4" data-testid="battlepass-tab">
        <div className="skeleton h-44 rounded-2xl" />
        <div className="skeleton h-[330px] rounded-2xl" />
      </motion.div>
    );
  }

  if (failed || !status) {
    return (
      <motion.div key="battlepass" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}
        className="glass rounded-2xl p-10 text-center" data-testid="bp-error">
        <AlertTriangle size={30} className="mx-auto mb-3 text-crimson" />
        <h3 className="font-display text-xl font-extrabold">No pudimos cargar el pase</h3>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          El servidor no respondió. Tu progreso y tus recompensas están a salvo — solo hay que volver a pedirlos.
        </p>
        <button type="button" onClick={() => { play("click"); load(false); }} data-testid="bp-retry"
          className="mt-5 inline-flex items-center gap-2 rounded-lg bg-gold px-5 py-2.5 text-sm font-bold text-background transition-all hover:brightness-110">
          Reintentar
        </button>
      </motion.div>
    );
  }

  const showBanner = daysLeft != null && daysLeft < BANNER_DAYS && pendingPicks > 0;

  return (
    <motion.div
      key="battlepass"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.3 }}
      className="space-y-5"
      data-testid="battlepass-tab"
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-bold"
          style={{ color: GOLD, borderColor: `${GOLD}55`, background: `${GOLD}14` }}>
          <Trophy size={10} /> PASE DE BATALLA
        </span>
        {checkingPayment && (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="bp-payment-checking">
            <Loader2 size={12} className="animate-spin" /> Confirmando tu pago con Stripe…
          </span>
        )}
      </div>

      <SeasonHeader
        season={status.season}
        level={status.level}
        xp={status.xp}
        tier={status.tier}
        tierSource={status.tier_source}
        claimableCount={status.claimable_count}
        claimingAll={claimingAll}
        onClaimAll={claimAll}
        onOpenPurchase={() => setPurchaseOpen(true)}
      />

      {showBanner && (
        <div
          className="flex items-start gap-3 rounded-2xl border p-4"
          style={{ borderColor: "rgba(226,74,74,0.45)", background: "rgba(226,74,74,0.08)" }}
          data-testid="bp-season-end-banner"
        >
          <CalendarClock size={18} className="mt-0.5 shrink-0 text-crimson" />
          <p className="text-sm text-foreground/90">
            El pase resetea el 1º — reclama y elige tus dinos antes.
            <span className="ml-1 text-muted-foreground">
              Te {pendingPicks === 1 ? "queda 1 dino" : `quedan ${pendingPicks} dinos`} sin elegir.
            </span>
          </p>
        </div>
      )}

      <RewardTrack
        regularCells={regularTrack}
        premiumCells={premiumTrack}
        claimed={status.claimed || {}}
        level={status.level}
        viewerTier={status.tier}
        nameBySlug={nameBySlug}
        busyKey={busyKey}
        onClaim={onClaim}
        apexNames={apexSpecies.map((sp) => sp.name || sp.slug)}
      />

      <TokenPanel
        liveEnabled={!!status.live_tokens_enabled}
        refreshKey={tokenKey}
        onEffects={onEffects}
      />

      <BpSkinsStrip key={`skins-${tokenKey}`} />

      <PurchaseModal
        open={purchaseOpen}
        onClose={() => setPurchaseOpen(false)}
        currentTier={status.tier}
      />

      <DinoPicker
        open={!!picker}
        onClose={() => setPicker(null)}
        cell={picker?.cell}
        track={picker?.track}
        band={picker ? (status.dino_bands?.[picker.cell.band] || []) : []}
        apexSpecies={apexSpecies}
        viewerTier={status.tier}
        busy={!!busyKey}
        onConfirm={(slug) => picker && doClaim(picker.track, picker.cell, slug)}
      />

      <ClaimBurst
        show={!!burst}
        reward={burst?.reward}
        effects={burst?.effects}
        title={burst?.title}
        nameBySlug={nameBySlug}
      />
    </motion.div>
  );
}

export default BattlePassSection;
