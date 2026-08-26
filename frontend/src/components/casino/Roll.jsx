import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Info, ShieldCheck, Loader2, Link2, Inbox } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";

const COL = { green: "#10B981", red: "#F32C2C", black: "#3a3a4a" };
const BET_COLORS = [
  { k: "red", label: "Rojo", c: COL.red },
  { k: "green", label: "Verde", c: COL.green },
  { k: "black", label: "Negro", c: COL.black },
];
const numOf = (roll) => Math.max(0, Math.min(14, Math.floor((roll ?? 0) * 15)));
const colorOf = (n) => (n === 0 ? "green" : n <= 7 ? "red" : "black");
const BASE = [0, 1, 14, 2, 13, 3, 12, 4, 11, 5, 10, 6, 9, 7, 8];
const TILE = 66, TH = 66, GAP = 10, STEP = TILE + GAP, LOOP = BASE.length * STEP;
const STRIP_LEN = 90, TARGET = 66;
// The stake ceiling is the SERVER's number (state.config.max_bet), never a second
// copy here -- a UI that offers a chip the backend refuses just hands the player a
// red toast. The fallback matches the house maximum every other game uses.
const MAXBET_FALLBACK = 100000;
const QUICK_STEPS = [1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000];
const shortNum = (n) => (n >= 1000000 ? `${n / 1000000}M` : n >= 1000 ? `${n / 1000}K` : `${n}`);
const quickChips = (min, max) => {
  const chips = QUICK_STEPS.filter((v) => v >= min && v <= max);
  if (!chips.includes(max)) chips.push(max);
  return chips.slice(-6).map((v) => [shortNum(v), v]);
};
const fmt = (n) => Math.round(n || 0).toLocaleString();

function ReelTile({ n, active }) {
  const col = colorOf(n);
  const baseShadow = col === "green" ? `0 0 18px ${COL[col]}88` : "inset 0 -3px 8px rgba(0,0,0,0.35)";
  return (
    <motion.div className="shrink-0 rounded-md flex items-center justify-center font-display font-extrabold text-2xl"
      style={{
        width: TILE, height: TH,
        background: `linear-gradient(165deg, ${COL[col]}, ${COL[col]}cc)`,
        color: col === "black" ? "#e7e7ef" : "#0a0806",
      }}
      animate={active
        ? { scale: [1, 1.28, 1.1, 1.16], rotate: [0, -5, 5, -3, 3, 0], x: [0, -4, 4, -2, 2, 0],
            boxShadow: `0 0 0 3px #7CA842, 0 0 30px ${COL[col]}, 0 0 46px ${COL[col]}aa` }
        : { scale: 1, rotate: 0, x: 0, boxShadow: baseShadow }}
      transition={active ? { duration: 0.55, ease: "easeOut" } : { duration: 0.2 }}>
      {n}
    </motion.div>
  );
}

export default function Roll({ balance, setBalance, onResolved }) {
  const { play } = useSound();
  const [bet, setBet] = useState(10000);
  const [state, setState] = useState(null);
  const [secs, setSecs] = useState(0);
  const [busy, setBusy] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const [stage, setStage] = useState("bet"); // bet | waiting | spin | landed
  const [reel, setReel] = useState({ x: 0, dur: 0 });
  const [contW, setContW] = useState(900);
  const stripWrap = useRef(null);
  const prevPhase = useRef(null);
  const lastRound = useRef(null);
  const waitTimer = useRef(null);
  const tickTimer = useRef(null);
  const landTimer = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.rollState();
      setState(data);
      if (typeof data.balance === "number") setBalance?.(data.balance);
      const r = data.round || {};
      if (lastRound.current && prevPhase.current === "rolling" && r.phase === "betting") onResolved?.();
      lastRound.current = r.round_no;
    } catch (e) { /* keep last */ }
  };
  useEffect(() => { load(); const t = setInterval(load, 1000); return () => clearInterval(t); }, []);

  useEffect(() => {
    const el = stripWrap.current; if (!el) return;
    const update = () => setContW(el.clientWidth);
    update();
    const ro = new ResizeObserver(update); ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const round = state?.round;
  const phase = round?.phase;
  const betting = phase === "betting";
  const rolling = phase === "rolling";
  const history = state?.history || [];
  const counts = history.reduce((a, h) => { a[h.result_color] = (a[h.result_color] || 0) + 1; return a; }, { red: 0, green: 0, black: 0 });
  const minBet = Number(state?.config?.min_bet) || 100;
  const maxBet = Number(state?.config?.max_bet) || MAXBET_FALLBACK;
  const QUICK = useMemo(() => quickChips(minBet, maxBet), [minBet, maxBet]);
  const myBets = state?.my_bets || [];
  const myTotal = myBets.reduce((a, b) => a + b.amount, 0);
  const myColor = myBets[0]?.color || null;
  const betsByColor = (c) => (round?.bets || []).filter((b) => b.color === c);
  const winNum = round?.result_number != null ? round.result_number : numOf(round?.roll);
  const mult = state?.config?.mult || { red: 2, black: 2, green: 14 };
  const landed = stage === "landed";
  const showResult = landed && rolling;
  const winColor = showResult ? round?.result_color : null;
  const blockNo = round?.server_hash ? (parseInt(round.server_hash.slice(0, 9), 16) % 900000000 + 100000000) : null;

  useEffect(() => {
    const t = setInterval(() => {
      const end = round?.phase_ends_at;
      if (end && betting) setSecs(Math.max(0, (new Date(end).getTime() - Date.now()) / 1000));
    }, 90);
    return () => clearInterval(t);
  }, [round?.phase_ends_at, betting]);

  const startTicks = (durMs) => {
    clearTimeout(tickTimer.current);
    const t0 = performance.now();
    const tickAt = () => {
      const el = performance.now() - t0;
      if (el >= durMs) return;
      play("tick");
      const p = Math.min(1, el / durMs);
      tickTimer.current = setTimeout(tickAt, 34 + p * p * 320);
    };
    tickAt();
  };

  useEffect(() => {
    clearTimeout(waitTimer.current); clearTimeout(landTimer.current);
    if (rolling) {
      if (prevPhase.current === "betting") {
        setStage("waiting"); play("click");
        waitTimer.current = setTimeout(() => {
          setStage("spin");
          const end = round?.phase_ends_at ? new Date(round.phase_ends_at).getTime() : Date.now() + 6500;
          const spinMs = Math.max(1600, (end - Date.now()) - 2500);
          const targetX = contW / 2 - (TARGET * STEP + TILE / 2);   // land winner dead-centre under the marker
          setReel({ x: targetX, dur: spinMs / 1000 });
          startTicks(spinMs);
          landTimer.current = setTimeout(() => { setStage("landed"); play("rollLand"); }, spinMs);
        }, 1400);
      } else setStage("landed");
    } else if (betting) { setStage("bet"); clearTimeout(tickTimer.current); }
    prevPhase.current = phase;
    return () => { clearTimeout(waitTimer.current); clearTimeout(landTimer.current); };
    // eslint-disable-next-line
  }, [phase, round?.round_no]);

  useEffect(() => () => { clearTimeout(waitTimer.current); clearTimeout(tickTimer.current); clearTimeout(landTimer.current); }, []);

  const place = async (color) => {
    if (!betting) { play("error"); return toast.error("Apuestas cerradas — espera la próxima ronda"); }
    if (bet > balance + myTotal) { play("error"); return toast.error("Saldo insuficiente"); }
    setBusy(true); play("coins");
    try {
      const { data } = await api.rollBet(color, Number(bet));
      setBalance?.(data.balance); play("click");
      toast.success(data.moved ? `Apuesta movida a ${color.toUpperCase()}` : `Apuesta de ${fmt(bet)} CC a ${color.toUpperCase()}`);
      load();
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo apostar"); }
    finally { setBusy(false); }
  };

  const reelTiles = useMemo(() => Array.from({ length: BASE.length * 5 }, (_, i) => BASE[i % BASE.length]), []);
  const strip = useMemo(() => {
    const rn = round?.round_no || 0;
    const arr = [];
    for (let i = 0; i < STRIP_LEN; i++) arr.push(i === TARGET && rolling ? winNum : BASE[(i * 3 + rn) % BASE.length]);
    return arr;
  }, [round?.round_no, round?.roll, rolling, winNum]);
  const spinning = stage === "spin" || stage === "landed";

  return (
    <div data-testid="game-roll" className="relative max-w-6xl mx-auto">
      {/* atmospheric dino background */}
      <div className="absolute inset-0 rounded-3xl overflow-hidden pointer-events-none">
        <img src="/casino-trex.png" alt="" className="w-full h-full object-cover object-center" style={{ opacity: 0.5 }} />
        <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(6,8,7,0.72) 0%, rgba(6,8,7,0.5) 42%, rgba(6,8,7,0.88) 100%)" }} />
      </div>
      <div className="relative z-10 p-2 sm:p-4">
      {/* ===== TOP BAR: history + jackpot ===== */}
      <div className="grid lg:grid-cols-[1fr_auto] gap-3 mb-3">
        <div className="glass rounded-xl px-4 py-3">
          <div className="flex items-center gap-3 mb-2">
            <span className="label-overline text-[10px] text-muted-foreground">Últimas {history.length}</span>
            <span className="flex items-center gap-3 text-[11px] font-bold">
              <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-crimson" />{counts.red}</span>
              <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: COL.black }} />{counts.black}</span>
              <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400" />{counts.green}</span>
            </span>
          </div>
          <div className="flex gap-1.5 overflow-hidden" data-testid="roll-history">
            {history.slice(0, 14).map((h) => (
              <span key={h.round_no} className="shrink-0 w-7 h-7 rounded-md flex items-center justify-center text-[11px] font-bold text-white" style={{ background: COL[h.result_color] }}>{h.result_number != null ? h.result_number : numOf(h.roll)}</span>
            ))}
          </div>
        </div>
        <div className="glass rounded-xl px-5 py-3 min-w-[280px] border border-gold/25 flex items-center gap-4" data-testid="roll-jackpot">
          <div className="flex-1">
            <p className="label-overline text-[10px] text-gold inline-flex items-center gap-1.5"><Trophy size={12} /> Triple Verde
              <button onClick={() => setShowInfo(true)} data-testid="roll-info-btn" className="text-muted-foreground/70 hover:text-gold"><Info size={11} /></button>
            </p>
            <p className="font-display font-extrabold text-3xl text-gold tabular-nums leading-none mt-1" data-testid="roll-jackpot-amount">{fmt(state?.jackpot)}</p>
          </div>
          <div className="flex flex-col items-center gap-1.5">
            <div className="flex items-center gap-1.5">
              {[0, 1, 2].map((i) => <span key={i} className={`w-4 h-4 rounded-md ${i < (state?.green_streak || 0) ? "bg-emerald-400" : "bg-white/10"}`} />)}
            </div>
            <span className="text-[9px] text-muted-foreground tracking-wide">{state?.green_streak || 0}/3 VERDES</span>
          </div>
        </div>
      </div>

      {/* ===== REEL PANEL ===== */}
      <div className="relative rounded-2xl overflow-hidden border border-white/10 mb-1"
        style={{ background: "linear-gradient(180deg, rgba(8,10,9,0.85), rgba(4,6,5,0.92))" }}>
        <div ref={stripWrap} className="relative h-[128px] overflow-hidden" data-testid="roll-strip">
          {/* edge fades */}
          <div className="absolute inset-y-0 left-0 w-20 z-20 pointer-events-none" style={{ background: "linear-gradient(90deg, rgba(4,6,5,0.95), transparent)" }} />
          <div className="absolute inset-y-0 right-0 w-20 z-20 pointer-events-none" style={{ background: "linear-gradient(270deg, rgba(4,6,5,0.95), transparent)" }} />
          {/* gold center marker (only while spinning/landed) */}
          {spinning && (
            <>
              <div className="absolute left-1/2 top-1/2 z-[25] pointer-events-none -translate-x-1/2 -translate-y-1/2 rounded-full" style={{ width: 170, height: 170, background: "radial-gradient(circle, rgba(124, 168, 66,0.38), rgba(124, 168, 66,0.08) 55%, transparent 72%)", filter: "blur(3px)" }} />
              <div className="absolute left-1/2 top-0 bottom-0 z-30 pointer-events-none" style={{ transform: "translateX(-50%)" }}>
                <div className="w-0 h-0 mx-auto" style={{ borderLeft: "7px solid transparent", borderRight: "7px solid transparent", borderTop: "9px solid #7CA842" }} />
                <div className="w-[2px] mx-auto bg-gold" style={{ height: "calc(100% - 18px)", boxShadow: "0 0 12px #7CA842" }} />
                <div className="w-0 h-0 mx-auto" style={{ borderLeft: "7px solid transparent", borderRight: "7px solid transparent", borderBottom: "9px solid #7CA842" }} />
              </div>
            </>
          )}
          {/* reel */}
          {spinning ? (
            <motion.div key="land" className="absolute top-1/2 flex items-center" style={{ gap: GAP, translateY: "-50%" }}
              initial={{ x: 0 }} animate={{ x: reel.x }} transition={{ duration: reel.dur, ease: [0.06, 0.75, 0.1, 1] }}>
              {strip.map((n, i) => <ReelTile key={i} n={n} active={i === TARGET && stage === "landed"} />)}
            </motion.div>
          ) : (
            <motion.div key="drift" className="absolute top-1/2 flex items-center" style={{ gap: GAP, translateY: "-50%", filter: "blur(3px)", opacity: 0.5 }}
              animate={{ x: [0, -LOOP] }} transition={{ duration: 7, repeat: Infinity, ease: "linear" }}>
              {reelTiles.map((n, i) => <ReelTile key={i} n={n} />)}
            </motion.div>
          )}

          {/* center content: betting countdown + EOS wait only */}
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center text-center px-4 pointer-events-none">
            <AnimatePresence mode="wait">
              {betting && (
                <motion.div key="bet" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  <p className="inline-flex items-center gap-2 text-emerald-400 font-display font-bold text-sm mb-0.5"><span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" /> Hagan sus apuestas</p>
                  <p className="font-display font-extrabold text-5xl tabular-nums leading-none" data-testid="roll-countdown">{secs.toFixed(2)}<span className="text-xl text-muted-foreground">s</span></p>
                </motion.div>
              )}
              {stage === "waiting" && (
                <motion.div key="wait" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-1.5" data-testid="roll-eos-wait">
                  <Loader2 size={22} className="text-sky-400 animate-spin" />
                  <p className="text-sky-400 font-display font-bold text-sm">Waiting for EOS Block</p>
                  {blockNo && <span className="text-[10px] font-mono text-sky-400/70 border border-sky-400/30 rounded px-2 py-0.5">Bloque #{blockNo}</span>}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
        {/* countdown progress bar */}
        <div className="h-[3px] bg-white/5">
          <motion.div className="h-full bg-emerald-400" style={{ boxShadow: "0 0 8px #10B981" }} animate={{ width: betting ? `${Math.min(100, (secs / 15) * 100)}%` : "0%" }} transition={{ ease: "linear", duration: 0.1 }} />
        </div>
        {/* footer */}
        <div className="flex items-center justify-between px-4 py-2 text-[10px] text-muted-foreground/60 font-mono">
          <span className="inline-flex items-center gap-1.5 truncate max-w-[60%]"><ShieldCheck size={11} className="text-emerald-400/70" /> {round?.server_hash ? round.server_hash.slice(0, 40) : "—"} <span className="text-sky-400/60">◈ EOS #{blockNo}</span></span>
          <span className="inline-flex items-center gap-1.5 shrink-0"><Info size={10} /> Provably Fair</span>
        </div>
      </div>

      {/* ===== PLACE BETS ===== */}
      <div className="glass-strong rounded-2xl p-4 mt-3">
        <p className="label-overline text-[10px] text-gold mb-3">Hacer Apuesta</p>
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <div className="flex items-center gap-2 bg-black/40 rounded-lg px-3 py-2.5 flex-1 min-w-[180px] border border-white/5">
            <Link2 size={15} className="text-gold" />
            <input type="number" min={minBet} max={maxBet} value={bet} onChange={(e) => setBet(Math.max(minBet, Math.min(maxBet, parseInt(e.target.value) || minBet)))}
              data-testid="roll-bet-input" className="w-full bg-transparent text-sm font-bold focus:outline-none" />
            <span className="text-[10px] text-muted-foreground shrink-0">CC</span>
          </div>
          {QUICK.map(([l, v]) => (
            <button key={l} onClick={() => setBet(v)} data-testid={`roll-quick-${l}`} className="px-3 py-2.5 rounded-lg bg-white/5 text-xs font-bold text-muted-foreground hover:text-gold hover:bg-gold/10 transition-colors">{l}</button>
          ))}
          <button onClick={() => setBet((b) => Math.max(minBet, Math.floor(b / 2)))} className="px-3 py-2.5 rounded-lg bg-white/5 text-xs font-bold text-muted-foreground hover:text-gold hover:bg-gold/10 transition-colors">½</button>
          <button onClick={() => setBet((b) => Math.min(maxBet, b * 2))} className="px-3 py-2.5 rounded-lg bg-white/5 text-xs font-bold text-muted-foreground hover:text-gold hover:bg-gold/10 transition-colors">2×</button>
          <button onClick={() => setBet(Math.min(maxBet, Math.max(minBet, Math.floor(balance + myTotal))))} className="px-3 py-2.5 rounded-lg bg-gold/15 text-xs font-bold text-gold hover:bg-gold/25 transition-colors">MAX</button>
        </div>
        <p className="text-[10px] text-muted-foreground mt-2" data-testid="roll-bet-limits">
          Apuesta entre {fmt(minBet)} y {fmt(maxBet)} CC por ronda.
        </p>

        <div className="grid grid-cols-3 gap-3">
          {BET_COLORS.map((b) => {
            const active = myColor === b.k;
            return (
              <button key={b.k} onClick={() => place(b.k)} disabled={busy || !betting} data-testid={`roll-bet-${b.k}`}
                className="relative rounded-xl py-7 font-display font-extrabold transition-all active:scale-[0.98] disabled:opacity-45 disabled:cursor-not-allowed border"
                style={{ background: `linear-gradient(160deg, ${b.c}33, ${b.c}0d)`, borderColor: active ? b.c : `${b.c}55`, boxShadow: active ? `0 0 0 1px ${b.c}, 0 0 22px ${b.c}44` : "none" }}>
                <span className="block text-xl uppercase tracking-wide" style={{ color: b.k === "black" ? "#fff" : b.c }}>{b.label}</span>
                <span className="block text-sm mt-1" style={{ color: b.k === "black" ? "#fff9" : `${b.c}` }}>×{mult[b.k]}</span>
                {active && <span className="absolute top-2 right-2 text-[9px] font-bold text-gold bg-gold/15 px-1.5 py-0.5 rounded">TU APUESTA</span>}
              </button>
            );
          })}
        </div>
        <p className="text-[10px] text-muted-foreground/60 text-center mt-2">Solo puedes apostar a un color — apostar a otro moverá tu apuesta.</p>
      </div>

      {/* ===== ACTIVE BETS ===== */}
      <div className="mt-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="label-overline text-[10px] text-emerald-400">Apuestas activas</span>
          <span className="flex-1 h-px bg-white/10" />
        </div>
        <div className="grid grid-cols-3 gap-3">
          {BET_COLORS.map((b) => {
            const list = betsByColor(b.k);
            const total = round?.totals?.[b.k] || 0;
            return (
              <div key={b.k} className="glass rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="inline-flex items-center gap-2 text-sm font-bold">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ background: b.c }} />{b.label}
                    <span className="text-[10px] text-muted-foreground bg-white/5 rounded px-1.5">{list.length}</span>
                  </span>
                  <span className="text-xs font-bold tabular-nums" style={{ color: b.c }}>{fmt(total)} CC</span>
                </div>
                <div className="space-y-1 h-[96px] overflow-y-auto pr-0.5">
                  {list.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center gap-1 text-muted-foreground/30">
                      <Inbox size={16} /><span className="text-[10px]">Sin apuestas aún</span>
                    </div>
                  ) : list.map((bt, i) => (
                    <div key={i} className="flex items-center gap-2" data-testid={`roll-bet-row-${b.k}`}>
                      <img src={bt.avatar || "/logo192.png"} alt="" className="w-5 h-5 rounded object-cover shrink-0" />
                      <span className="flex-1 min-w-0 text-[11px] truncate">{bt.name}</span>
                      <span className="text-[11px] font-bold tabular-nums text-gold">{fmt(bt.amount)}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* jackpot info modal */}
      <AnimatePresence>
        {showInfo && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setShowInfo(false)}>
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
            <div className="relative glass-strong rounded-2xl p-6 max-w-md w-full border border-gold/30" onClick={(e) => e.stopPropagation()} data-testid="roll-info-modal">
              <h3 className="font-display font-extrabold text-xl text-gold mb-1">Bonus Triple Verde</h3>
              <p className="text-sm text-muted-foreground mb-4">Un pozo que crece con cada apuesta y se paga cuando salen tres verdes seguidos.</p>
              <ol className="space-y-2 text-sm">
                <li><span className="text-gold font-bold">1.</span> El <b>10.67%</b> de cada apuesta se añade al Bonus Pool <b>al instante</b>.</li>
                <li><span className="text-gold font-bold">2.</span> El Bonus se gana cuando salen <b>3 verdes seguidos</b>.</li>
                <li><span className="text-gold font-bold">3.</span> Todos los que jugaron en cualquiera de las 3 rondas reciben una parte.</li>
                <li><span className="text-gold font-bold">4.</span> El pozo se divide en tercios repartidos proporcionalmente según lo apostado.</li>
              </ol>
              <p className="mt-4 text-[11px] text-muted-foreground">Provably Fair: el número sale de <b>HMAC-SHA256(server_seed + client_seed : nonce)</b>; el hash se publica antes de cada ronda.</p>
              <button onClick={() => setShowInfo(false)} className="mt-4 w-full bg-gold text-background font-bold py-2.5 rounded-xl">Entendido</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      </div>
    </div>
  );
}
