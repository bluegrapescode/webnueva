import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from "framer-motion";
import { toast } from "sonner";
import { Coins, Gem, Zap, Utensils, Shirt, Crown, Gift, ChevronLeft, ChevronRight, Trophy, History, Clock, Award, Sparkles, FlaskConical, Info } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { GlitchProx } from "@/components/common/GlitchProx";
import {
  cardContent, cardTheme, computeLayout, fmtNum, fmtTimeLeft, newCmdId, oddsText,
  poolItems, rarityLabel, relTime, rewardLine, segmentImage, spinTarget, spinsCopy, winnerKey,
} from "./wheelMath";

// Nublar Spin — the daily free wheel, a Mini Juegos tab (owner: "put it in
// casino tab ... kinda like forza horizon"). The horizontal card carousel is
// the owner's own bundle, adapted: this site's token key, api map, sound
// context and glitch face, tab-scoped (no fixed drawers over the navbar),
// replay-safe spins (one cmd_id per attempt, re-sent on a dropped answer).

const ICON = {
  coin: Coins, coin_big: Coins, amberium: Gem, amberium_big: Gem,
  growth: Zap, growth_big: Zap, diet: Utensils, skin: Shirt, dino: Trophy,
  crown: Crown, vial: FlaskConical, gift: Gift,
};
function IconFor({ name, size = 22, color, strokeWidth = 2 }) {
  const Cmp = ICON[name] || Gift;
  return <Cmp size={size} color={color} strokeWidth={strokeWidth} />;
}

// The outermost plates fade out at the stage edges instead of being sliced off
// by the container, which also keeps the nav arrows off a cut-off card.
const EDGE_FADE = "linear-gradient(90deg, transparent 0%, #000 7%, #000 93%, transparent 100%)";

const REPEATS = 12;
const SPIN_SECONDS = 6;
const REVEAL_DELAY_MS = 400;
const RETRY_MS = 600;
const RETRY_MAX = 8;

function wsUrl(token) {
  const base = process.env.REACT_APP_BACKEND_URL || window.location.origin;
  const q = token ? `?token=${encodeURIComponent(token)}` : "";
  return base.replace(/^http/, "ws") + "/api/wheel/ws" + q;
}

function prefersReducedMotion() {
  try { return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (_) { return false; }
}

export default function Wheel({ balance, setBalance, onResolved }) {
  const { user } = useAuth();
  const { play } = useSound();
  const [cfg, setCfg] = useState(null);
  const [status, setStatus] = useState(null);
  const [vip, setVip] = useState(user?.vip_coins ?? 0);
  const [spinning, setSpinning] = useState(false);
  const [reveal, setReveal] = useState(null);
  const [history, setHistory] = useState([]);
  const [liveFeed, setLiveFeed] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsStats, setWsStats] = useState({ online: 0, spins_24h: 0 });
  const [flash, setFlash] = useState(false);
  const [tick, setTick] = useState(0);
  const [winner, setWinner] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [layout, setLayout] = useState(() => computeLayout(typeof window !== "undefined" ? window.innerWidth : 1200));
  const { CARD_W, CARD_H, STEP_X, VIEW_H } = layout;
  const x = useMotionValue(0);
  const xNeg = useTransform(x, (v) => -v);
  const confettiRef = useRef(null);
  const inflight = useRef(null);

  const loadAll = useCallback(async () => {
    try {
      const c = await api.wheelConfig();
      setCfg(c.data);
      setStatus(c.data.wheel);
      setLoadError(false);
    } catch (_) { setLoadError(true); }
    try { const h = await api.wheelHistory(); setHistory(h.data?.history || []); } catch (_) { /* optional */ }
  }, []);
  useEffect(() => { if (user) loadAll(); }, [user, loadAll]);
  useEffect(() => { setVip(user?.vip_coins ?? 0); }, [user?.vip_coins]);

  // 1 Hz countdown only while there is nothing to spin (never during a spin).
  useEffect(() => {
    if (spinning || status?.can_spin) return undefined;
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [spinning, status?.can_spin]);

  useLayoutEffect(() => {
    const onResize = () => setLayout(computeLayout(window.innerWidth));
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Live wins feed (bounded on the server; persona + plate only, no ids).
  useEffect(() => {
    if (!user) return undefined;
    const token = localStorage.getItem("primal_token");
    let closed = false, reconnectT = null, pingT = null;
    const wsRef = { current: null };
    const connect = () => {
      try {
        const ws = new WebSocket(wsUrl(token));
        wsRef.current = ws;
        ws.onopen = () => setWsConnected(true);
        ws.onclose = () => { setWsConnected(false); if (!closed) reconnectT = setTimeout(connect, 5000); };
        ws.onerror = () => {};
        ws.onmessage = (ev) => {
          if (ev.data === "pong") return;
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "wheel_recent") { setLiveFeed(msg.items || []); if (msg.stats) setWsStats(msg.stats); }
            else if (msg.type === "wheel_win") { setLiveFeed((prev) => [msg, ...prev].slice(0, 20)); if (msg.stats) setWsStats(msg.stats); }
            else if (msg.type === "wheel_config_updated") loadAll();
          } catch (_) { /* ignore a bad frame */ }
        };
      } catch (_) { reconnectT = setTimeout(connect, 5000); }
    };
    connect();
    pingT = setInterval(() => { const ws = wsRef.current; if (ws && ws.readyState === WebSocket.OPEN) { try { ws.send("ping"); } catch (_) { /* noop */ } } }, 25000);
    return () => {
      closed = true;
      if (reconnectT) clearTimeout(reconnectT);
      if (pingT) clearInterval(pingT);
      const ws = wsRef.current; if (ws) { try { ws.close(); } catch (_) { /* noop */ } }
    };
  }, [user?.id, loadAll]); // eslint-disable-line react-hooks/exhaustive-deps

  const segments = useMemo(() => (cfg && Array.isArray(cfg.segments) ? cfg.segments : []), [cfg]);
  const segCount = segments.length;
  const strip = useMemo(() => {
    const arr = [];
    for (let r = 0; r < REPEATS; r++) for (let i = 0; i < segCount; i++) arr.push({ ...segments[i], _key: `${r}-${i}`, _srcIdx: i });
    return arr;
  }, [segments, segCount]);
  const CENTER_IDX = Math.floor(strip.length / 2);

  useEffect(() => { if (segCount && !spinning) x.set(0); }, [segCount]); // eslint-disable-line react-hooks/exhaustive-deps

  // POST the spin; a dropped answer or an in-flight duplicate re-sends the
  // SAME cmd_id so the server answers with the recorded spin, never a second.
  const requestSpin = async (cmdId) => {
    let lastErr = null;
    for (let i = 0; i < RETRY_MAX; i++) {
      try {
        const r = await api.wheelSpin(cmdId);
        return r.data;
      } catch (e) {
        const st = e?.response?.status;
        const detail = e?.response?.data?.detail;
        if (st === 409 && detail?.code === "PENDING") { await new Promise((res) => setTimeout(res, RETRY_MS)); continue; }
        if (!e?.response) { lastErr = e; await new Promise((res) => setTimeout(res, RETRY_MS)); continue; }
        throw e;
      }
    }
    throw lastErr || new Error("PENDING");
  };

  const doSpin = async () => {
    if (spinning || !segCount || !status?.can_spin || inflight.current) return;
    const cmdId = newCmdId();
    inflight.current = cmdId;
    setSpinning(true); setReveal(null); setWinner(null);
    try {
      const data = await requestSpin(cmdId);
      const { segment_index, segment, reward } = data;
      // The table the spin was settled on is authoritative: an admin edit
      // between load and spin would otherwise land the dial on a wrong plate.
      let segs = segments;
      if (Array.isArray(data.segments) && JSON.stringify(data.segments) !== JSON.stringify(segments)) {
        segs = data.segments;
        setCfg((c) => ({ ...(c || {}), segments: segs }));
      }
      const n = segs.length;
      const { resetX, targetSteps, targetX } = spinTarget(x.get(), STEP_X, n, segment_index);
      x.set(resetX);
      const centerIdx = Math.floor((REPEATS * n) / 2);
      const dur = prefersReducedMotion() ? 0.8 : SPIN_SECONDS;
      let lastTick = Math.round(x.get() / STEP_X) + centerIdx;
      try { play("wheelStart"); } catch (_) { /* noop */ }
      animate(x, targetX, {
        duration: dur, type: "tween", ease: "easeOut",
        onUpdate: (v) => {
          const idx = Math.round(v / STEP_X) + centerIdx;
          if (idx !== lastTick && idx >= 0) { lastTick = idx; try { play("wheelTick"); } catch (_) { /* noop */ } }
        },
        onComplete: () => {
          try { play("wheelStop"); } catch (_) { /* noop */ }
          setWinner(winnerKey(centerIdx, targetSteps, n, segment_index));
          setTimeout(() => {
            const rarity = segment?.rarity || "common";
            setReveal({ segment, reward, replayed: !!data.replayed });
            try {
              play("wheelReveal", rarity);
              if (reward?.kind === "gen0_vial") play("zombieRoar");
              else if (rarity === "legendary") play("wheelJackpot");
            } catch (_) { /* noop */ }
            if (rarity === "legendary" || rarity === "epic") {
              fireConfetti(confettiRef.current, rarity === "legendary");
              setFlash(true); setTimeout(() => setFlash(false), 700);
            }
            if (data.wheel) setStatus(data.wheel);
            if (data.balance) { if (typeof setBalance === "function") setBalance(data.balance.coins); setVip(data.balance.vip_coins); }
            setSpinning(false);
            inflight.current = null;
            if (typeof onResolved === "function") onResolved();
            loadAll();
          }, REVEAL_DELAY_MS);
        },
      });
    } catch (e) {
      setSpinning(false);
      inflight.current = null;
      const st = e?.response?.status;
      const detail = e?.response?.data?.detail;
      if (st === 429) { toast.error("No te quedan giros hoy. Vuelve mañana — o sube de nivel en Patreon."); }
      else if (detail === "WHEEL_DISABLED") toast.error("La ruleta está cerrada ahora mismo.");
      else if (st === 409 && detail?.code === "GRANT_FAILED") toast.error("Ese giro falló y fue devuelto. Gira de nuevo.");
      else if (st === 503) toast.error("La ruleta está en mantenimiento. Avisa al staff.");
      else if (typeof detail === "string" && detail) toast.error(detail);
      else toast.error("No se pudo girar. Inténtalo de nuevo.");
      loadAll();
    }
  };

  if (loadError && !cfg) {
    return <div className="glass rounded-2xl p-10 text-center text-sm text-muted-foreground" data-testid="wheel-error">No pudimos cargar la ruleta. <button className="underline" onClick={loadAll}>Reintentar</button></div>;
  }
  if (!cfg) return <div className="glass rounded-2xl p-10 text-center text-sm text-muted-foreground" data-testid="wheel-loading">Cargando ruleta…</div>;

  const canSpin = !!status?.can_spin && segCount > 0;
  const copy = spinsCopy(status);

  return (
    <div className="relative rounded-2xl overflow-hidden text-white" data-testid="wheel-page"
      style={{ boxShadow: "0 30px 80px rgba(0,0,0,0.55), inset 0 0 0 1px rgba(255,255,255,0.06)" }}>
      <AmbientBackdrop />
      <canvas ref={confettiRef} className="pointer-events-none absolute inset-0 z-[45]" aria-hidden="true" />

      {/* Top bar */}
      <div className="relative flex flex-col lg:flex-row lg:items-start justify-between px-4 sm:px-6 md:px-8 pt-5 sm:pt-6 gap-3">
        <GameTitle />
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap lg:justify-end">
          <LiveStatsHud stats={wsStats} connected={wsConnected} />
          <BalanceHud label="PRIMEMEAT" amount={balance ?? user?.coins ?? 0} icon={Coins} tone="#FF2489" testId="wheel-balance-hud" />
          <BalanceHud label="AMBERIUM" amount={vip} icon={Gem} tone="#F59E0B" testId="wheel-amber-hud" />
        </div>
      </div>

      {/* Stage */}
      <div className="relative flex flex-col justify-center py-3 sm:py-5">
        <IndicatorTriangle />
        <SideArrow side="left" />
        <SideArrow side="right" />
        <div className="relative mx-auto w-full max-w-[1600px] overflow-hidden" data-testid="wheel-carousel"
          style={{ height: VIEW_H, maskImage: EDGE_FADE, WebkitMaskImage: EDGE_FADE }}>
          {/* The pointer's halo paints BEHIND the plates. It used to sit above
              them, and a pink radial over the centre card is exactly why the
              winning plate read as washed-out and broken. */}
          <CenterFrame layout={layout} layer="glow" />
          <StageBar />
          <motion.div className="absolute left-1/2 top-1/2 z-10" style={{ x: xNeg, willChange: "transform" }}>
            {strip.map((seg, i) => (
              <CarouselCard key={seg._key} seg={seg} index={i} centerIdx={CENTER_IDX} x={x} layout={layout} isWinner={winner === seg._key} />
            ))}
          </motion.div>
          <CenterFrame layout={layout} layer="rim" />
          {segCount === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-white/60" data-testid="wheel-empty">La ruleta no tiene premios configurados.</div>
          )}
        </div>
        <AnimatePresence>{reveal && <RevealCaption reveal={reveal} />}</AnimatePresence>
      </div>

      {/* Controls */}
      <div className="relative px-4 sm:px-6 md:px-8 pb-5 grid grid-cols-1 md:grid-cols-3 items-center md:items-end gap-3 md:gap-4">
        <div className="order-2 md:order-1 flex md:justify-start justify-center">
          <PatreonHint copy={copy} status={status} />
        </div>
        <div className="order-1 md:order-2 flex justify-center">
          <SpinControls spinning={spinning} canSpin={canSpin} copy={copy} status={status} onSpin={doSpin}
            countdown={fmtTimeLeft(status?.next_reset)} tick={tick} />
        </div>
        <div className="order-3 flex md:justify-end justify-center">
          <ExclusiveHint />
        </div>
      </div>

      <LiveTicker feed={liveFeed} connected={wsConnected} myName={user?.persona_name} />

      {/* Prize pool + my history, inside the tab (no fixed drawers, no inner
          scrollers — every plate and every recent spin is on the surface). */}
      <div className="relative px-4 sm:px-6 md:px-8 pb-6 pt-4 space-y-3">
        <PrizePool segments={segments} />
        <SpinHistory history={history} />
      </div>

      <AnimatePresence>
        {flash && (
          <motion.div className="pointer-events-none absolute inset-0 z-[50]" initial={{ opacity: 0 }}
            animate={{ opacity: [0, 1, 0.4, 0] }} exit={{ opacity: 0 }} transition={{ duration: 0.7, times: [0, 0.15, 0.4, 1] }}
            style={{ background: "radial-gradient(ellipse at center, rgba(255,255,255,0.85) 0%, rgba(236,72,153,0.35) 45%, transparent 75%)", mixBlendMode: "screen" }} />
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Confetti — a 60-line canvas burst, no dependency (canvas-confetti is not
// in this tree and a deploy must not grow the install surface for one effect).
function fireConfetti(canvas, big) {
  if (!canvas || prefersReducedMotion()) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = canvas.width = canvas.offsetWidth || 800;
  const H = canvas.height = canvas.offsetHeight || 600;
  const colors = big ? ["#FF2489", "#EC4899", "#FFD54F", "#F59E0B", "#FFFFFF", "#84CC16"] : ["#EC4899", "#F472B6", "#A78BFA", "#C084FC"];
  const N = big ? 220 : 110;
  const parts = [];
  for (let i = 0; i < N; i++) {
    const fromLeft = i % 2 === 0;
    parts.push({
      x: fromLeft ? W * 0.12 : W * 0.88, y: H * 0.75,
      vx: (fromLeft ? 1 : -1) * (3 + Math.random() * 9), vy: -(9 + Math.random() * 11),
      g: 0.28 + Math.random() * 0.12, s: 4 + Math.random() * 6, r: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.3, c: colors[i % colors.length], life: 1,
      shape: i % 3 === 0 ? "circle" : "rect",
    });
  }
  const start = performance.now();
  const total = big ? 3200 : 1600;
  let raf = 0;
  const frame = (now) => {
    const t = now - start;
    ctx.clearRect(0, 0, W, H);
    if (big && t < 1800 && Math.random() < 0.8) {
      parts.push({ x: Math.random() * W, y: -10, vx: (Math.random() - 0.5) * 2, vy: 2 + Math.random() * 3, g: 0.06, s: 4 + Math.random() * 5,
        r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.2, c: colors[Math.floor(Math.random() * colors.length)], life: 1, shape: "rect" });
    }
    for (const p of parts) {
      p.vy += p.g; p.x += p.vx; p.y += p.vy; p.vx *= 0.985; p.r += p.vr;
      p.life = Math.max(0, 1 - t / total);
      ctx.save(); ctx.globalAlpha = p.life; ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c;
      if (p.shape === "circle") { ctx.beginPath(); ctx.arc(0, 0, p.s / 2, 0, Math.PI * 2); ctx.fill(); }
      else ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2);
      ctx.restore();
    }
    if (t < total) raf = requestAnimationFrame(frame);
    else ctx.clearRect(0, 0, W, H);
  };
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(frame);
}

// ─── Backdrop, title, HUDs ────────────────────────────────────────────────
function AmbientBackdrop() {
  return (
    <>
      <div className="pointer-events-none absolute inset-0 -z-0" style={{
        background: "radial-gradient(ellipse 70% 55% at 50% 30%, #3B0A2E 0%, #180418 35%, #060008 75%), linear-gradient(180deg, #060008 0%, #0A0208 100%)",
      }} />
      <div className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-[6%] h-[55%] w-[80%] rounded-full opacity-40 blur-3xl" style={{ background: "radial-gradient(circle, #EC4899 0%, transparent 70%)" }} />
      <svg className="pointer-events-none absolute top-0 left-0 w-full h-[30%] opacity-25" viewBox="0 0 1600 500" preserveAspectRatio="none" aria-hidden="true">
        <defs><linearGradient id="wheel-palm-g" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#000" stopOpacity="0.85" /><stop offset="1" stopColor="#000" stopOpacity="0.2" /></linearGradient></defs>
        <path d="M120,500 L130,220 Q140,180 175,175 Q145,180 130,150 Q120,120 165,110 Q120,90 140,50 Q170,90 175,140 Q180,90 220,80 Q195,120 190,160 Q220,120 260,120 Q225,160 205,190 Q235,190 260,175 Q225,200 190,220 L200,500 Z" fill="url(#wheel-palm-g)" />
        <path d="M1450,500 L1460,240 Q1475,200 1510,195 Q1480,200 1465,170 Q1455,140 1500,130 Q1455,110 1475,70 Q1505,110 1510,160 Q1515,110 1555,100 Q1530,140 1525,180 Q1555,140 1595,140 Q1560,180 1540,210 L1530,500 Z" fill="url(#wheel-palm-g)" />
      </svg>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[35%]" style={{ background: "linear-gradient(0deg, rgba(236,72,153,0.15) 0%, rgba(236,72,153,0.03) 40%, transparent 100%)" }} />
    </>
  );
}

function GameTitle() {
  return (
    <div className="relative select-none">
      <div className="relative flex items-baseline gap-2 pl-1">
        <h2 className="font-black italic tracking-[0.02em] leading-none text-3xl sm:text-4xl md:text-5xl" style={{ color: "#FFF", textShadow: "0 2px 12px rgba(0,0,0,0.7)" }}>NUBLAR</h2>
        <h2 className="font-black italic tracking-[0.02em] leading-none text-3xl sm:text-4xl md:text-5xl" style={{
          background: "linear-gradient(180deg, #FF3D9A 0%, #EC4899 55%, #BE185D 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
          filter: "drop-shadow(0 0 18px rgba(236,72,153,0.55))",
        }}>SPIN</h2>
      </div>
      <div className="mt-1.5 pl-1 text-[10px] sm:text-[11px] font-black tracking-[0.35em] text-white/85 uppercase">Ruleta diaria · gira gratis cada día</div>
    </div>
  );
}

function LiveStatsHud({ stats, connected }) {
  return (
    <div className="relative flex items-stretch h-11 rounded-md overflow-hidden shrink-0" style={{ background: "linear-gradient(180deg, #12040F 0%, #060004 100%)", boxShadow: "0 8px 24px rgba(0,0,0,0.55), inset 0 0 0 1px rgba(255,255,255,0.08)" }} data-testid="wheel-live-stats">
      <div className="pl-3 pr-2 flex items-center gap-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-white/30"}`} />
        <span className="text-[9px] font-black tracking-[0.3em] uppercase" style={{ color: connected ? "#22C55E" : "#94A3B8" }}>{connected ? "LIVE" : "OFF"}</span>
      </div>
      <div className="px-2.5 flex flex-col justify-center border-l border-white/10 min-w-[64px]">
        <div className="text-[9px] font-black tracking-[0.25em] text-white/55 uppercase">Online</div>
        <div className="text-sm font-black text-white tabular-nums leading-none">{stats?.online ?? 0}</div>
      </div>
      <div className="px-2.5 flex flex-col justify-center border-l border-white/10 min-w-[84px]">
        <div className="text-[9px] font-black tracking-[0.25em] text-white/55 uppercase">Giros 24h</div>
        <div className="text-sm font-black text-pink-300 tabular-nums leading-none" style={{ textShadow: "0 0 10px rgba(236,72,153,0.55)" }}>{fmtNum(stats?.spins_24h ?? 0)}</div>
      </div>
    </div>
  );
}

function BalanceHud({ label, amount, icon: Icon, tone, testId }) {
  return (
    <div className="relative flex items-stretch h-11 rounded-md overflow-hidden shrink-0" style={{ background: "linear-gradient(180deg, #12040F 0%, #060004 100%)", boxShadow: `0 8px 24px rgba(0,0,0,0.55), inset 0 0 0 1px ${tone}88` }} data-testid={testId}>
      <div className="pl-3 pr-2 flex items-center text-[9px] sm:text-[10px] font-black tracking-[0.3em] text-white/70 uppercase">{label}</div>
      <div className="relative flex items-center px-3 min-w-[96px]" style={{ background: `linear-gradient(180deg, ${tone} 0%, ${tone}aa 100%)`, boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.15)" }}>
        <span className="text-base sm:text-lg font-black tabular-nums text-white" style={{ textShadow: "0 2px 8px rgba(0,0,0,0.6)" }}>{fmtNum(amount)}</span>
        <div className="ml-2 h-5 w-5 rounded-sm flex items-center justify-center" style={{ background: "rgba(0,0,0,0.35)" }}><Icon size={12} color="#fff" strokeWidth={2.5} /></div>
      </div>
    </div>
  );
}

// ─── Stage furniture ──────────────────────────────────────────────────────
function IndicatorTriangle() {
  return (
    <motion.div className="pointer-events-none absolute left-1/2 -translate-x-1/2 z-30" style={{ top: 2 }} animate={{ y: [0, 6, 0] }} transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}>
      <div className="relative">
        <div style={{ width: 0, height: 0, borderLeft: "20px solid transparent", borderRight: "20px solid transparent", borderTop: "24px solid #FFFFFF", filter: "drop-shadow(0 0 18px rgba(236,72,153,0.9)) drop-shadow(0 0 40px rgba(236,72,153,0.55))" }} />
        <div className="absolute left-1/2 -translate-x-1/2 top-0" style={{ width: 0, height: 0, borderLeft: "14px solid transparent", borderRight: "14px solid transparent", borderTop: "16px solid #EC4899" }} />
      </div>
    </motion.div>
  );
}

// The perspective floor the plates stand on. It used to hang at the TOP of the
// stage, where it read as a stray hairline drawn across the cards; a stage bar
// belongs under the feet of the thing standing on it.
function StageBar() {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-[3%] mx-auto max-w-[1700px] px-6 z-0">
      <svg viewBox="0 0 1700 60" className="w-full h-[60px]" preserveAspectRatio="none" aria-hidden="true">
        <defs><linearGradient id="wheel-stage-g" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stopColor="rgba(120,10,80,0)" /><stop offset="0.35" stopColor="rgba(236,72,153,0.65)" /><stop offset="0.5" stopColor="rgba(255,255,255,0.85)" /><stop offset="0.65" stopColor="rgba(236,72,153,0.65)" /><stop offset="1" stopColor="rgba(120,10,80,0)" /></linearGradient></defs>
        <path d="M0 30 Q 850 -10 1700 30" fill="none" stroke="url(#wheel-stage-g)" strokeWidth="2" />
        <path d="M0 30 Q 850 4 1700 30" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
      </svg>
      <div className="absolute inset-x-0 top-[26px] h-16" style={{ background: "radial-gradient(50% 100% at 50% 0%, rgba(236,72,153,0.30) 0%, transparent 70%)", filter: "blur(6px)" }} />
    </div>
  );
}

function SideArrow({ side }) {
  const isLeft = side === "left";
  const Icon = isLeft ? ChevronLeft : ChevronRight;
  return (
    <motion.div className="pointer-events-none absolute z-30 top-1/2 -translate-y-1/2 hidden sm:block" style={{ [isLeft ? "left" : "right"]: 12 }} animate={{ x: isLeft ? [0, -6, 0] : [0, 6, 0] }} transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}>
      <div className="h-12 w-12 rounded-lg flex items-center justify-center opacity-80" style={{ background: "rgba(0,0,0,0.55)", boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.12), 0 4px 14px rgba(0,0,0,0.5)" }}><Icon size={32} color="#FFF" strokeWidth={3} /></div>
    </motion.div>
  );
}

// The pointer frame is drawn in TWO passes around the plates: `glow` is the
// soft magenta halo and goes UNDER the strip, `rim` is the neon ring and goes
// over it. Painting the halo on top is what desaturated the centre plate and
// its art — a filled layer over a card is never "framing". The rim's old tick
// rows hung OUTSIDE it, through the pointer triangle and the stage floor, so
// they are gone: rim + halo + triangle already say "this one".
function CenterFrame({ layout, layer = "rim" }) {
  const { CARD_W, CARD_H } = layout;
  const W = Math.round(CARD_W * 1.18) + 16;
  const H = Math.round(CARD_H * 1.18) + 20;
  const box = { width: W, height: H };
  if (layer === "glow") {
    return (
      <div className="pointer-events-none absolute z-0 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" style={box} data-testid="wheel-center-glow">
        <div className="absolute -inset-10 rounded-[2rem]" style={{ background: "radial-gradient(58% 52% at 50% 50%, rgba(236,72,153,0.70) 0%, rgba(236,72,153,0.20) 55%, transparent 80%)", filter: "blur(22px)" }} />
      </div>
    );
  }
  return (
    <div className="pointer-events-none absolute z-20 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" style={box} data-testid="wheel-center-frame">
      <div className="absolute inset-0 rounded-2xl" style={{ boxShadow: "0 0 0 2px rgba(255,255,255,0.55), 0 0 0 4px rgba(236,72,153,0.9), 0 0 14px 3px rgba(236,72,153,0.45)" }} />
      <motion.div className="absolute inset-0 rounded-2xl" style={{ boxShadow: "0 0 0 2px rgba(255,255,255,0.75), 0 0 0 4px rgba(236,72,153,1), 0 0 22px 5px rgba(236,72,153,0.70)", willChange: "opacity" }} animate={{ opacity: [0, 1, 0] }} transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut", times: [0, 0.5, 1] }} />
    </div>
  );
}

// ─── Cards ────────────────────────────────────────────────────────────────
const CarouselCard = React.memo(function CarouselCard({ seg, index, centerIdx, x, layout, isWinner }) {
  const { CARD_W, CARD_H, STEP_X } = layout;
  const offset = (index - centerIdx) * STEP_X;
  const distance = useTransform(x, (v) => Math.abs(offset - v));
  const scale = useTransform(distance, [0, STEP_X, 2 * STEP_X, 3 * STEP_X], [1.18, 0.92, 0.74, 0.58]);
  const opacity = useTransform(distance, [0, STEP_X, 2 * STEP_X, 3 * STEP_X], [1, 0.85, 0.42, 0]);
  const ty = useTransform(distance, [0, STEP_X, 2 * STEP_X, 3 * STEP_X], [-6, 6, 22, 40]);
  const visibility = useTransform(distance, (d) => (d > 3.2 * STEP_X ? "hidden" : "visible"));
  const cc = cardContent(seg);
  const th = cardTheme(seg);
  return (
    <motion.div className="absolute" style={{ left: offset - CARD_W / 2, top: -CARD_H / 2, width: CARD_W, height: CARD_H, scale, opacity, y: ty, visibility, transformOrigin: "50% 50%", willChange: "transform, opacity", zIndex: isWinner ? 40 : 1 }}
      data-testid={`wheel-card-${seg._srcIdx}`}>
      <motion.div className="absolute inset-0" animate={isWinner ? { x: [0, -3, 3, -3, 3, -2, 2, 0], rotate: [0, -1, 1, -1, 1, -0.5, 0.5, 0] } : { x: 0, rotate: 0 }} transition={isWinner ? { duration: 0.55, repeat: Infinity, repeatType: "loop", ease: "easeInOut" } : { duration: 0.2 }}>
        <div className="relative w-full h-full rounded-xl overflow-hidden" style={{ background: th.bg, boxShadow: "0 20px 40px rgba(0,0,0,0.55), inset 0 0 0 1px rgba(255,255,255,0.06), inset 0 -60px 80px rgba(0,0,0,0.35)" }}>
          <div className="pointer-events-none absolute inset-0" style={{ background: "linear-gradient(160deg, rgba(255,255,255,0.16) 0%, rgba(255,255,255,0.04) 25%, transparent 55%)" }} />
          <div className="pointer-events-none absolute inset-0 opacity-40" style={{ background: "repeating-linear-gradient(-24deg, transparent 0 22px, rgba(255,255,255,0.03) 22px 23px)" }} />
          {/* Rarity ribbon — the plate says what class of prize it is without
              the player having to open a list somewhere else. */}
          <div className="absolute top-0 left-0 right-0 flex justify-center">
            <span className="px-3 py-[3px] rounded-b-md text-[9px] font-black tracking-[0.3em] uppercase whitespace-nowrap"
              style={{ background: `linear-gradient(180deg, ${th.accent}, ${th.accent}aa)`, color: "#0B0208", boxShadow: `0 2px 10px ${th.accent}66` }}>
              {rarityLabel(seg.rarity)}
            </span>
          </div>
          <div className="relative h-full flex flex-col items-center px-4 pt-7 pb-3">
            <div className="text-[11px] font-black tracking-[0.35em] text-white/80 uppercase">{cc.category}</div>
            <div className="mt-1 h-px w-16 bg-white/25" />
            <div className="mt-2 text-white font-black tracking-tight uppercase text-center leading-[0.95]" style={{ fontSize: cc.title.length > 8 ? 26 : 34, textShadow: "0 2px 10px rgba(0,0,0,0.55)", letterSpacing: cc.title.length > 8 ? "-0.01em" : "-0.02em" }}>{cc.title}</div>
            <div className="mt-1 text-[10px] font-black tracking-[0.28em] text-white/75 uppercase text-center leading-tight">{cc.subtitle}</div>
            <div className="relative mt-2 flex-1 w-full flex items-center justify-center">
              <div className="absolute inset-x-4 inset-y-2 rounded-full opacity-70" style={{ background: `radial-gradient(60% 45% at 50% 55%, ${th.accent}55 0%, transparent 65%)` }} />
              <RewardArt seg={seg} accent={th.accent} />
            </div>
            {/* Odds footer — the number the pool prints, on the plate itself. */}
            <div className="mt-1 relative flex items-center gap-2">
              <HexTag accent={th.accent}><IconFor name={seg.icon} size={13} color={th.accent} strokeWidth={2.5} /></HexTag>
              {oddsText(seg.probability) && (
                <span className="text-[11px] font-black tabular-nums tracking-[0.14em] uppercase" style={{ color: th.accent }}
                  data-testid={`wheel-card-odds-${seg._srcIdx}`}>{oddsText(seg.probability)}</span>
              )}
            </div>
          </div>
          <div className="pointer-events-none absolute inset-y-0 left-0 w-6" style={{ background: "linear-gradient(90deg, rgba(0,0,0,0.35), transparent)" }} />
          <div className="pointer-events-none absolute inset-y-0 right-0 w-6" style={{ background: "linear-gradient(-90deg, rgba(0,0,0,0.35), transparent)" }} />
        </div>
      </motion.div>
    </motion.div>
  );
});

function RewardArt({ seg, accent }) {
  const img = segmentImage(seg);
  if (seg?.kind === "glitch_skin") {
    return (
      <div className="relative h-[116px] w-[116px] rounded-full overflow-hidden" style={{ border: `2px solid ${accent}`, boxShadow: `0 12px 30px rgba(0,0,0,0.55), 0 0 40px ${accent}66` }}>
        <GlitchProx proximity={[]} accent={accent} compact />
      </div>
    );
  }
  return (
    <div className="relative flex items-center justify-center h-[150px] w-[150px]">
      <div className="absolute inset-0 rounded-full" style={{ background: `radial-gradient(circle at 35% 30%, ${accent}dd 0%, ${accent}66 40%, transparent 75%)`, filter: "blur(2px)" }} />
      <div className="relative flex items-center justify-center h-[110px] w-[110px] rounded-full" style={{ background: `radial-gradient(circle at 40% 30%, rgba(255,255,255,0.35), rgba(255,255,255,0.05) 40%, transparent 70%), radial-gradient(circle at 50% 60%, ${accent} 0%, ${accent}88 55%, ${accent}22 100%)`, border: `2px solid ${accent}`, boxShadow: `0 12px 30px rgba(0,0,0,0.55), 0 0 40px ${accent}66, inset 0 -12px 24px rgba(0,0,0,0.35)` }}>
        {img ? <img src={img} alt="" className="h-[86px] w-[86px] object-contain" style={{ filter: `drop-shadow(0 4px 10px ${accent}88) drop-shadow(0 0 14px rgba(255,255,255,0.35))` }} loading="lazy" draggable={false} />
             : <IconFor name={seg.icon} size={72} color="#FFF" strokeWidth={2.2} />}
      </div>
      <span className="absolute -top-1 left-6 h-1.5 w-1.5 rounded-full bg-white/80" style={{ boxShadow: "0 0 6px #fff" }} />
      <span className="absolute bottom-3 right-4 h-1 w-1 rounded-full bg-white/70" style={{ boxShadow: "0 0 5px #fff" }} />
    </div>
  );
}

function HexTag({ children, accent }) {
  return <div className="relative h-7 w-7 flex items-center justify-center" style={{ background: `linear-gradient(180deg, ${accent}22, ${accent}0d)`, clipPath: "polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)", boxShadow: `inset 0 0 0 1.5px ${accent}88` }}>{children}</div>;
}

// ─── Controls ─────────────────────────────────────────────────────────────
function SpinControls({ spinning, canSpin, copy, status, onSpin, countdown, tick }) {
  const usingBonus = copy.available > 0 && Number(status?.left_today || 0) === 0 && copy.bonus > 0;
  return (
    <div className="relative flex flex-col items-center gap-1.5" data-testid="wheel-spin-controls">
      <div className="relative flex items-center gap-2 h-8 px-4 rounded-md" style={{ background: "linear-gradient(180deg, #12040F 0%, #060004 100%)", boxShadow: copy.available > 0 ? "inset 0 0 0 1px rgba(236,72,153,0.55), 0 0 14px rgba(236,72,153,0.25)" : "inset 0 0 0 1px rgba(255,255,255,0.08)" }} data-testid="wheel-spins-chip">
        <span className="text-white text-lg font-black tabular-nums" style={{ textShadow: "0 0 12px rgba(236,72,153,0.7)" }}>{copy.available}</span>
        <span className="text-[11px] font-black tracking-[0.3em] text-white/85 uppercase">{copy.line}</span>
        {copy.bonus > 0 && <span className="ml-1 text-[9px] font-black tracking-[0.25em] uppercase text-pink-300">+{copy.bonus} bonus</span>}
      </div>
      <button onClick={onSpin} disabled={spinning || !canSpin} data-testid="wheel-spin-btn"
        className="relative h-14 sm:h-16 min-w-[260px] sm:min-w-[340px] px-8 rounded-lg overflow-hidden disabled:opacity-70 disabled:cursor-not-allowed"
        style={{ background: canSpin ? "linear-gradient(180deg, #FF3D9A 0%, #EC4899 55%, #BE185D 100%)" : "linear-gradient(180deg, #3A0A24 0%, #1B0410 100%)",
          boxShadow: canSpin ? "0 0 40px rgba(236,72,153,0.75), 0 12px 28px rgba(0,0,0,0.55), inset 0 -6px 0 rgba(0,0,0,0.35), inset 0 2px 0 rgba(255,255,255,0.25)" : "0 8px 16px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(255,255,255,0.08)" }}>
        {canSpin && !spinning && (
          <motion.div className="absolute inset-0 pointer-events-none" animate={{ backgroundPositionX: ["-100%", "220%"] }} transition={{ duration: 2.2, repeat: Infinity, ease: "linear" }}
            style={{ backgroundImage: "linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.4) 50%, transparent 70%)", backgroundSize: "50% 100%", backgroundRepeat: "no-repeat" }} />
        )}
        <span className="relative text-2xl sm:text-3xl font-black tracking-[0.35em] text-white" style={{ textShadow: "0 2px 8px rgba(0,0,0,0.5)" }}>{spinning ? "GIRANDO…" : "GIRAR"}</span>
      </button>
      <div className="mt-1 flex items-center gap-2 h-7 px-3 rounded-md" style={{ background: "linear-gradient(180deg, #12040F 0%, #060004 100%)", boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.05)" }} data-testid="wheel-cost-line">
        <div className="h-4 w-4 rounded-sm flex items-center justify-center" style={{ background: "linear-gradient(180deg, #FF2489, #C2185B)" }}><Gift size={10} color="#fff" strokeWidth={2.6} /></div>
        {canSpin ? (
          <span className="text-[11px] font-black tracking-[0.3em] text-white/95 uppercase">{usingBonus ? "GIRO BONUS · REGALO" : `GRATIS · ${copy.daily}`}</span>
        ) : status?.enabled === false ? (
          <span className="text-[11px] font-black tracking-[0.3em] text-white/70 uppercase">CERRADA</span>
        ) : (
          <span key={tick} className="text-[11px] font-black tracking-[0.3em] text-white/95 uppercase tabular-nums">PRÓXIMO GIRO EN {countdown}</span>
        )}
      </div>
    </div>
  );
}

// Both bottom hints are fixed two-line chips with no wrapping: at the old
// max-width the Patreon line broke after "POR" and the reset line orphaned
// "UTC" on a line of its own, which read as a layout fault.
function PatreonHint({ copy, status }) {
  return (
    <div className="flex items-center gap-3 select-none" data-testid="wheel-patreon-hint">
      <div className="h-9 w-9 rounded-full flex items-center justify-center shrink-0" style={{ background: "rgba(0,0,0,0.55)", boxShadow: "inset 0 0 0 1.5px rgba(245,158,11,0.85), 0 0 12px rgba(245,158,11,0.35)" }}><Crown size={16} color="#F59E0B" /></div>
      <div className="leading-tight min-w-0">
        <div className="text-[11px] font-black tracking-[0.18em] text-white/85 uppercase whitespace-nowrap">{copy.patreon}</div>
        <div className="text-[10px] font-black tracking-[0.14em] text-white/55 uppercase whitespace-nowrap">{status?.tier_key ? `${status.allowance} giros cada día` : "Juvie 2 · Sub 3 · Adult 4 · Elder 5 · Apex 6"}</div>
      </div>
    </div>
  );
}

function ExclusiveHint() {
  return (
    <div className="hidden sm:flex items-center gap-3 select-none" data-testid="wheel-exclusive-hint">
      <div className="h-9 w-9 rounded-full flex items-center justify-center shrink-0" style={{ background: "rgba(0,0,0,0.55)", boxShadow: "inset 0 0 0 1.5px rgba(236,72,153,0.85), 0 0 12px rgba(236,72,153,0.35)" }}><Info size={16} color="#FF3D9A" /></div>
      <div className="leading-tight min-w-0">
        <div className="text-[11px] font-black tracking-[0.18em] text-white/85 uppercase whitespace-nowrap">Se reinicia a medianoche UTC</div>
        <div className="text-[10px] font-black tracking-[0.14em] text-white/60 uppercase whitespace-nowrap">Dinos, skins, fichas <span className="text-pink-400">y el Vial GEN-Ø</span></div>
      </div>
    </div>
  );
}

// ─── Reveal ───────────────────────────────────────────────────────────────
function RevealCaption({ reveal }) {
  const cc = cardContent(reveal.segment);
  const r = reveal.reward || {};
  const th = cardTheme(reveal.segment);
  return (
    <motion.div initial={{ opacity: 0, y: 10, scale: 0.94 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8 }} transition={{ type: "spring", stiffness: 220, damping: 18 }} data-testid="wheel-reveal-caption" className="mt-3 mx-auto max-w-xl text-center px-4">
      <div className="inline-flex items-center gap-2 rounded-full px-4 py-1 text-[10px] font-black tracking-[0.4em] text-white uppercase" style={{ background: "linear-gradient(90deg, #EC4899, #BE185D)", boxShadow: "0 0 22px rgba(236,72,153,0.55)" }}>{reveal.replayed ? "TU GIRO ANTERIOR" : "¡GANASTE!"}</div>
      <div className="mt-2 text-2xl sm:text-3xl font-black tracking-tight text-white uppercase" style={{ textShadow: "0 0 24px rgba(236,72,153,0.7)" }}>
        {r.kind === "glitch_skin" && r.name ? r.name : r.kind?.startsWith("dino") && r.name ? `${r.name}${r.tier === "prime" ? " PRIME" : ""}` : cc.title}
        {cc.subtitle && !(r.kind === "glitch_skin" || r.kind?.startsWith("dino")) && <span className="text-pink-300"> · {cc.subtitle}</span>}
      </div>
      <div className="mt-1 text-[11px] font-black tracking-[0.25em] uppercase" style={{ color: th.accent }} data-testid="wheel-reveal-line">{rewardLine(r)}</div>
      {r.kind === "glitch_skin" && (
        <div className="mx-auto mt-2 h-10 w-40 rounded-md overflow-hidden"><GlitchProx proximity={r.proximity || []} accent={r.accent_hex} compact /></div>
      )}
      {Array.isArray(r.mutations) && r.mutations.length > 0 && (
        <div className="mt-1 text-[10px] font-black tracking-[0.25em] text-pink-300 uppercase">+ {r.mutations.length} mutaciones: {r.mutations.join(" · ")}</div>
      )}
    </motion.div>
  );
}

// ─── Feed, pool, history ──────────────────────────────────────────────────
function LiveTicker({ feed, connected, myName }) {
  if (!feed || feed.length === 0) return null;
  return (
    <div className="relative border-t border-white/[0.06]" style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.75) 100%)" }} data-testid="wheel-live-feed">
      <div className="flex items-center gap-4 px-4 sm:px-6 py-2 overflow-hidden">
        <div className="shrink-0 flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-white/25"}`} />
          <span className="text-[10px] font-black tracking-[0.35em]" style={{ color: connected ? "#22C55E" : "#94A3B8" }}>{connected ? "LIVE" : "OFFLINE"}</span>
        </div>
        <div className="flex items-center gap-3 overflow-x-auto scrollbar-none">
          {feed.slice(0, 15).map((w, i) => {
            const isMe = myName && w.name === myName;
            const th = cardTheme(w.segment || {});
            return (
              <div key={`${w.at}-${i}`} className="shrink-0 flex items-center gap-2 rounded-md px-2.5 py-1.5" style={{ background: isMe ? "rgba(236,72,153,0.15)" : "rgba(0,0,0,0.4)", boxShadow: isMe ? "inset 0 0 0 1px #EC4899" : "inset 0 0 0 1px rgba(255,255,255,0.06)" }}>
                <div className="h-6 w-6 rounded-full flex items-center justify-center font-black text-[10px] uppercase overflow-hidden" style={{ background: th.accent + "22", border: `1.5px solid ${th.accent}`, color: th.accent }}>
                  {w.avatar ? <img src={w.avatar} alt="" className="h-full w-full object-cover" /> : (w.name || "?")[0]}
                </div>
                <span className="text-[11px] font-black text-white/90 whitespace-nowrap">{w.name || "Superviviente"}{isMe && <span className="ml-1 text-pink-300">(TÚ)</span>}</span>
                <span className="text-white/25">→</span>
                <span className="text-[11px] font-black whitespace-nowrap" style={{ color: th.accent }}>{(w.segment?.label || "").toUpperCase()}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Panel({ icon: Icon, title, count, hint, children, testId }) {
  return (
    <div className="rounded-xl overflow-hidden" style={{ background: "linear-gradient(180deg, rgba(24,4,24,0.92) 0%, rgba(6,0,4,0.92) 100%)", boxShadow: "inset 0 0 0 1px rgba(236,72,153,0.25)" }} data-testid={testId}>
      <div className="px-4 py-2.5 flex items-center justify-between gap-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-2 min-w-0">
          <Icon size={13} className="text-pink-400 shrink-0" />
          <span className="text-[11px] font-black tracking-[0.3em] text-white uppercase whitespace-nowrap">{title}</span>
          {count > 0 && <span className="rounded-sm px-1.5 py-0.5 text-[9px] font-black tabular-nums shrink-0" style={{ background: "#EC4899", color: "#fff" }}>{count}</span>}
        </div>
        {hint && <span className="hidden sm:block text-[9px] font-black tracking-[0.25em] text-white/40 uppercase truncate">{hint}</span>}
      </div>
      {/* No inner scroller: everything the panel holds is on the surface. */}
      <div>{children}</div>
    </div>
  );
}

// Every plate, always visible — a grid, not a six-row window onto fourteen
// prizes with the seventh sliced in half by the scroll box.
function PrizePool({ segments }) {
  const items = useMemo(() => poolItems(segments), [segments]);
  return (
    <Panel icon={Award} title="Premios posibles" count={items.length} hint="Probabilidades reales de cada giro" testId="wheel-prize-pool">
      {items.length === 0 ? <div className="px-4 py-8 text-center text-[11px] text-white/40 italic">Sin premios configurados.</div> : (
        <ul className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-px" style={{ background: "rgba(10,2,8,0.92)" }}>
          {items.map(({ seg, prob, barPct }, i) => {
            const th = cardTheme(seg); const cc = cardContent(seg); const img = segmentImage(seg);
            return (
              <li key={`${seg.key || seg.kind}-${i}`} className="px-3 py-2.5 flex items-center gap-3 hover:bg-white/[0.03]"
                style={{ background: "linear-gradient(180deg, rgba(24,4,24,0.92) 0%, rgba(6,0,4,0.92) 100%)" }}
                data-testid={`wheel-pool-${seg.key}`}>
                <div className="shrink-0 h-11 w-11 rounded-md flex items-center justify-center overflow-hidden" style={{ background: `radial-gradient(circle at 40% 30%, ${th.accent}55, ${th.accent}22)`, border: `1.5px solid ${th.accent}88` }}>
                  {seg.kind === "glitch_skin" ? <GlitchProx proximity={[]} accent={th.accent} compact /> : img ? <img src={img} alt="" className="h-8 w-8 object-contain" draggable={false} loading="lazy" /> : <IconFor name={seg.icon} size={18} color={th.accent} strokeWidth={2.3} />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] font-black text-white uppercase truncate">{seg.label}</div>
                  <div className="text-[9px] font-black tracking-[0.2em] text-white/50 uppercase truncate">{cc.subtitle}</div>
                  <div className="mt-1 h-1.5 w-full rounded-full bg-white/[0.07] overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${barPct}%`, background: `linear-gradient(90deg, ${th.accent}, ${th.accent}88)` }} />
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-[13px] font-black text-white tabular-nums leading-none">{oddsText(prob) || "—"}</div>
                  <div className="mt-1 text-[8px] font-black tracking-[0.2em] uppercase whitespace-nowrap" style={{ color: th.accent }}>{rarityLabel(seg.rarity)}</div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function SpinHistory({ history }) {
  const list = (history || []).slice(0, 12);
  return (
    <Panel icon={History} title="Tus últimos giros" count={list.length} hint={list.length ? "Los 12 más recientes" : ""} testId="wheel-history">
      {list.length === 0 ? (
        <div className="px-4 py-4 text-center text-[11px] text-white/40 italic">Aún no giraste. ¡Es hora de probar suerte!</div>
      ) : (
        <ul className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-px" style={{ background: "rgba(10,2,8,0.92)" }}>
          {list.map((row, i) => {
            const seg = row.segment || {}; const th = cardTheme(seg); const r = row.reward || {};
            return (
              <li key={`${row.at}-${i}`} className="px-3 py-2 flex items-center gap-3 hover:bg-white/[0.03]"
                style={{ background: "linear-gradient(180deg, rgba(24,4,24,0.92) 0%, rgba(6,0,4,0.92) 100%)" }}>
                <div className="shrink-0 h-9 w-9 rounded-md flex items-center justify-center" style={{ background: `radial-gradient(circle at 40% 30%, ${th.accent}55, ${th.accent}22)`, border: `1.5px solid ${th.accent}88` }}><IconFor name={seg.icon} size={15} color={th.accent} strokeWidth={2.3} /></div>
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] font-black text-white uppercase truncate">{r.name ? `${r.name}${r.tier === "prime" ? " PRIME" : ""}` : seg.label}</div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[9px] font-black tracking-[0.3em] uppercase" style={{ color: th.accent }}>{rarityLabel(seg.rarity)}</span>
                    <span className="text-white/25">·</span>
                    <span className="text-[10px] text-white/45 flex items-center gap-1 whitespace-nowrap"><Clock size={9} /> {relTime(row.at)}</span>
                    {row.lane === "bonus" && <span className="text-[9px] font-black text-pink-300 uppercase">bonus</span>}
                  </div>
                </div>
                {row.fairness?.nonce !== undefined && <span className="shrink-0 text-[9px] text-white/30 tabular-nums" title="Nonce provably fair"><Sparkles size={9} className="inline mr-0.5" />#{row.fairness.nonce}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
