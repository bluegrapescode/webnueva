import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, Users, ShieldCheck, Trophy, Info, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/lib/api";
import { useSound } from "@/context/SoundContext";

// GROWTH_RATE debe ser IDÉNTICO a crash_game.GROWTH_RATE en el backend
const GROWTH_RATE = 0.10;
const RECONNECT_DELAY_MS = 2000;
const WS_URL = API.replace(/^http/, "ws") + "/ws/casino/crash";

const QUICK = [["10K", 10000], ["50K", 50000], ["100K", 100000], ["500K", 500000]];
// El último preset es el umbral del Moon Pool: sin él, apuntar al pozo obligaría
// a esperar ~39 s y hacer clic a mano en el instante exacto.
const AUTO_PRESETS = [1.5, 2, 5, 10, 100];
const MULT_TIERS = [
  { min: 10, color: "#A855F7" },
  { min: 5, color: "#3B9EE5" },
  { min: 2, color: "#10B981" },
  { min: 1.5, color: "#EAB308" },
  { min: 0, color: "#E24A4A" },
];

const multColor = (m) => (MULT_TIERS.find((t) => (m || 0) >= t.min) || MULT_TIERS[MULT_TIERS.length - 1]).color;
const fmt = (n) => Math.round(n || 0).toLocaleString();

const W = 640, H = 320, PAD = 14;

export default function Crash({ balance, setBalance, onResolved }) {
  const { play } = useSound();

  // ESTADOS DE APUESTA Y JUEGO
  const [bet, setBet] = useState(10000);
  const [autoOn, setAutoOn] = useState(false);
  const [autoVal, setAutoVal] = useState("2.00");
  const [state, setState] = useState(null);
  const [mult, setMult] = useState(1.0);
  const [secs, setSecs] = useState(0);
  const [busy, setBusy] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const [eosWait, setEosWait] = useState(false);

  // REFERENCIAS Y TIMERS
  const wsRef = useRef(null);
  const eosTimer = useRef(null);
  const raf = useRef(null);
  const points = useRef([]);
  const phaseRef = useRef(null);
  const cashingRef = useRef(false);
  const lastSoundTick = useRef(0);
  const wiggle = useRef(0);
  const roundRef = useRef(null);
  const autoRef = useRef({ on: false, val: 2 });

  const lastTickRef = useRef({ mult: 1, elapsed: 0, perfAt: 0 });
  const tickSeenRef = useRef(false);
  // El servidor manda al ganador su propio premio y luego el anuncio para todos;
  // esta marca evita que el ganador vea dos avisos de la misma ronda.
  const wonPoolRef = useRef(false);

  useEffect(() => {
    autoRef.current = { on: autoOn, val: parseFloat(autoVal) || 0 };
  }, [autoOn, autoVal]);

  const round = state?.round;
  const phase = round?.phase;
  const myBet = state?.my_bet;
  const bets = round?.bets || [];
  const history = (state?.history || []).map((h) => h.crash_point);
  const totalWagered = useMemo(() => bets.reduce((sum, b) => sum + (b.amount || 0), 0), [bets]);

  // Ranking en vivo: retirados primero (mayor pago primero), luego quienes
  // siguen en juego por tamaño de apuesta. Depende de round?.bets (no de la
  // variable local `bets`, cuya referencia cambia en cada render si round.bets
  // no existe) para no reordenar en cada uno de los renders del multiplicador.
  const rankedBets = useMemo(() => {
    const list = round?.bets || [];
    return [...list].sort((a, b) => {
      const aCashed = a.cashed_at != null, bCashed = b.cashed_at != null;
      if (aCashed !== bCashed) return aCashed ? -1 : 1;
      if (aCashed && bCashed) return (b.payout || 0) - (a.payout || 0);
      return (b.amount || 0) - (a.amount || 0);
    });
  }, [round?.bets]);

  useEffect(() => {
    roundRef.current = round;
  }, [round]);

  // Cualquier cambio de saldo (apuesta, retiro, snapshot inicial) sube al padre
  // desde un único lugar, en vez de repetir setBalance en cada manejador.
  useEffect(() => {
    if (typeof state?.coins === "number") setBalance?.(state.coins);
  }, [state?.coins, setBalance]);

  const send = (message) => {
    const socket = wsRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      toast.error("Sin conexión con la ronda en vivo, reconectando...");
      return false;
    }
    socket.send(JSON.stringify(message));
    return true;
  };

  // EFECTOS COLATERALES DE CAMBIOS DE FASE
  useEffect(() => {
    const r = round || {};
    if (phaseRef.current !== r.phase) {
      if (r.phase === "running") {
        points.current = [{ t: 0, m: 1 }];
        cashingRef.current = false;
        setEosWait(true);
        tickSeenRef.current = false;
        play("click");
        clearTimeout(eosTimer.current);

        // El snapshot "state" trae current_multiplier/elapsed cuando nos unimos
        // a mitad de una ronda ya corriendo; una ronda que arranca en vivo para
        // todos empieza en (elapsed 0, mult 1). El próximo "tick" real corrige
        // cualquiera de los dos casos de inmediato.
        const seedElapsed = r.elapsed ?? 0;
        const seedMult = r.current_multiplier ?? 1;
        lastTickRef.current = { mult: seedMult, elapsed: seedElapsed, perfAt: performance.now() };
        setMult(seedMult);

        // Margen por si el primer tick real se retrasa o se pierde.
        eosTimer.current = setTimeout(() => setEosWait(false), 400);
      }
      if (r.phase === "crashed") {
        onResolved?.();
        play("crashBoom");
        if (r.crash_point) setMult(r.crash_point);
      }
      if (r.phase === "betting") {
        setEosWait(false);
        clearTimeout(eosTimer.current);
        setMult(1.0);
      }
    }
    phaseRef.current = r.phase;
  }, [round?.phase, round?.running_started_at, round?.crash_point, play, onResolved]);

  // 1. CONEXIÓN WEBSOCKET (única fuente de verdad: sin REST, sin polling)
  useEffect(() => {
    let closedByCleanup = false;
    let reconnectTimer = null;

    const handleMessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        return;
      }

      if (data.type === "tick") {
        const now = performance.now();
        const prev = lastTickRef.current;
        const predictedDt = Math.max(0, (now - prev.perfAt) / 1000);
        const predictedElapsed = prev.elapsed + predictedDt;
        lastTickRef.current = data.elapsed >= predictedElapsed
          ? { mult: data.multiplier, elapsed: data.elapsed, perfAt: now }
          : { mult: prev.mult * Math.exp(GROWTH_RATE * predictedDt), elapsed: predictedElapsed, perfAt: now };
        if (!tickSeenRef.current) {
          tickSeenRef.current = true;
          clearTimeout(eosTimer.current);
          setEosWait(false);
        }
        return;
      }

      switch (data.type) {
        case "state":
          setState(data);
          break;

        case "phase_betting":
          wonPoolRef.current = false;
          setState((prev) => ({
            ...prev,
            // El pozo viaja una vez por ronda: si se perdió un bet_placed o un
            // aviso de jackpot, el número se corrige aquí en vez de quedar a la
            // deriva toda la sesión.
            jackpot: typeof data.jackpot === "number" ? data.jackpot : prev?.jackpot,
            round: {
              round_no: data.round_no, phase: "betting", server_hash: data.server_hash,
              betting_ends_at: data.betting_ends_at, bets: [],
            },
            my_bet: null,
          }));
          break;

        case "phase_running":
          setState((prev) => ({
            ...prev,
            round: { ...prev.round, phase: "running", running_started_at: data.running_started_at },
          }));
          break;

        case "phase_crashed":
          setState((prev) => {
            const nextRound = { ...prev.round, phase: "crashed", crash_point: data.crash_point };
            const nextHistory = [{ round_no: nextRound.round_no, crash_point: data.crash_point, ts: Date.now() / 1000 },
                                 ...(prev.history || [])].slice(0, 24);
            return { ...prev, round: nextRound, history: nextHistory };
          });
          break;

        case "bet_placed":
          setState((prev) => {
            const currentBets = prev.round?.bets || [];
            if (currentBets.some((b) => b.user_id === data.bet.user_id)) return prev;
            return {
              ...prev,
              jackpot: data.jackpot ?? prev.jackpot,
              round: { ...prev.round, bets: [...currentBets, data.bet] },
            };
          });
          break;

        case "user_cashout":
          setState((prev) => {
            const currentBets = (prev.round?.bets || []).map((b) => (
              b.user_id === data.user_id ? { ...b, cashed_at: data.multiplier, payout: data.payout } : b
            ));
            const myBetUpdated = prev.my_bet?.user_id === data.user_id
              ? { ...prev.my_bet, cashed_at: data.multiplier, payout: data.payout }
              : prev.my_bet;
            return { ...prev, round: { ...prev.round, bets: currentBets }, my_bet: myBetUpdated };
          });
          break;

        case "bet_ack":
          setBusy(false);
          setState((prev) => ({
            ...prev, coins: data.coins,
            my_bet: { user_id: data.user_id, amount: data.amount, auto_cashout: data.auto_cashout, cashed_at: null, payout: 0 },
          }));
          toast.success(`Apuesta de ${fmt(data.amount)} CC${data.auto_cashout ? ` · auto ${data.auto_cashout}×` : ""}`);
          break;

        case "cashout_ack":
          cashingRef.current = false;
          play("crashCashout");
          setState((prev) => ({
            ...prev, coins: data.coins,
            my_bet: prev.my_bet ? { ...prev.my_bet, cashed_at: data.multiplier, payout: data.payout } : prev.my_bet,
          }));
          toast.success(`¡Retiraste a ${data.multiplier}×! +${fmt(data.payout)} CC`);
          break;

        // MOON POOL. Llegan hasta dos mensajes por ronda ganada: primero el del
        // ganador (trae "won" y su saldo nuevo), después el anuncio para toda la
        // sala (trae "winners" y el pozo ya reiniciado).
        case "jackpot":
          setState((prev) => {
            const next = { ...prev };
            if (typeof data.jackpot === "number") next.jackpot = data.jackpot;
            if (typeof data.coins === "number") next.coins = data.coins;
            if (data.winners?.length) {
              next.last_win = {
                round_no: data.round_no, amount: data.won_total, ts: Date.now() / 1000,
                multiplier: data.multiplier, winners: data.winners,
              };
            }
            return next;
          });
          if (typeof data.won === "number") {
            wonPoolRef.current = true;
            play("reward");
            toast.success(`¡MOON POOL! +${fmt(data.won)} CC`, { duration: 9000 });
          } else if (data.winners?.length && !wonPoolRef.current) {
            toast(`Moon Pool para ${data.winners.map((w) => w.name).join(", ")} · ${fmt(data.won_total)} CC`,
                  { duration: 7000 });
          }
          break;

        case "error":
          setBusy(false);
          cashingRef.current = false;
          toast.error(data.message || "Ocurrió un error");
          break;

        default:
          break;
      }
    };

    const connect = () => {
      const socket = new WebSocket(WS_URL);
      wsRef.current = socket;

      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "auth", token: localStorage.getItem("primal_token") }));
      };

      socket.onmessage = handleMessage;

      socket.onerror = () => {
        socket.close();
      };

      socket.onclose = () => {
        if (wsRef.current === socket) wsRef.current = null;
        if (!closedByCleanup) reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
    };

    connect();

    return () => {
      closedByCleanup = true;
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [play]);

  // Cronómetro regresivo para la fase de apuestas (betting_ends_at es un
  // epoch en segundos que manda el servidor, nunca calculado por el cliente).
  useEffect(() => {
    const t = setInterval(() => {
      if (round?.phase === "betting" && round?.betting_ends_at) {
        setSecs(Math.max(0, round.betting_ends_at - Date.now() / 1000));
      }
    }, 100);
    return () => clearInterval(t);
  }, [round?.phase, round?.betting_ends_at]);

  // 2. BUCLE PRINCIPAL DE ANIMACIÓN FLUIDA A 60 FPS
  useEffect(() => {
    cancelAnimationFrame(raf.current);

    if (phase === "running" && !eosWait) {
      wiggle.current = 0;
      if (points.current.length === 0) points.current.push({ t: 0, m: 1 });

      const loop = () => {
        const currentRound = roundRef.current;

        // A) SI EL SERVIDOR YA MARCÓ "CRASHED", CONGELAR EN EL VALOR REAL
        if (currentRound && currentRound.phase === "crashed") {
          setMult(currentRound.crash_point || lastTickRef.current.mult || 1.0);
          return;
        }

        // B) EXTRAPOLAR DESDE EL ÚLTIMO TICK DEL SERVIDOR: m(t+dt) = m(t) * e^(k*dt).
        // Como el ancla se corrige con cada tick real (~50ms), nunca se acumula
        // diferencia frente a lo que ven los demás jugadores.
        const { mult: tickMult, elapsed: tickElapsed, perfAt } = lastTickRef.current;
        const dt = Math.max(0, (performance.now() - perfAt) / 1000);
        let m = tickMult * Math.exp(GROWTH_RATE * dt);
        const elapsed = tickElapsed + dt;

        // C) NUNCA MOSTRAR MÁS QUE EL PUNTO DE CRASH REAL
        if (currentRound?.crash_point && m >= currentRound.crash_point) {
          m = currentRound.crash_point;
          setMult(m);
          return;
        }

        setMult(m);
        wiggle.current += (Math.random() - 0.5) * m * 0.05;
        wiggle.current = Math.max(-m * 0.06, Math.min(m * 0.06, wiggle.current * 0.9));
        const mViz = Math.max(1, m + wiggle.current);

        points.current.push({ t: elapsed, m: mViz });
        if (points.current.length > 600) points.current.shift();

        const tickNow = performance.now();
        if (tickNow - lastSoundTick.current > 460) {
          play("crashNote", m);
          lastSoundTick.current = tickNow;
        }

        // Auto-retiro local instantáneo
        const a = autoRef.current;
        if (myBet && myBet.cashed_at == null && a.on && a.val >= 1.01 && m >= a.val && !cashingRef.current) {
          cashout();
        }

        raf.current = requestAnimationFrame(loop);
      };

      raf.current = requestAnimationFrame(loop);
    } else if (phase === "crashed" && round?.crash_point) {
      setMult(round.crash_point);
    } else if (phase === "betting") {
      setMult(1.0);
    }

    return () => cancelAnimationFrame(raf.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, round?.crash_point, myBet?.cashed_at, eosWait]);

  // ACCIONES
  const place = () => {
    if (phase !== "betting") { play("error"); return toast.error("Apuestas cerradas"); }
    if (myBet) { play("error"); return toast.error("Ya apostaste en esta ronda"); }
    if (bet > balance) { play("error"); return toast.error("Saldo insuficiente"); }
    const auto = autoOn ? parseFloat(autoVal) : null;
    if (!send({ type: "bet", amount: Number(bet), auto_cashout: auto })) return;
    setBusy(true);
    play("coins");
  };

  const cashout = () => {
    if (cashingRef.current) return;
    cashingRef.current = true;
    if (!send({ type: "cashout" })) cashingRef.current = false;
  };

  // CÁLCULOS VISUALES DEL SVG Y PUNTOS DE LA GRÁFICA
  const tip = points.current.length ? points.current[points.current.length - 1] : { t: 0, m: 1 };
  const peak = Math.max(1.02, mult, ...(points.current.length ? points.current.map((p) => p.m) : [1]));
  const yMax = peak * 1.05;
  const maxT = Math.max(0.25, tip.t);
  const GAMMA = 1.8;
  const yNorm = (m) => Math.pow(Math.max(0, Math.max(1, m) - 1) / Math.max(0.0001, yMax - 1), GAMMA);
  const yF = (m) => H - PAD - yNorm(m) * (H - 2 * PAD);
  const xF = (t) => PAD + (t / maxT) * (W - 2 * PAD);
  const axisVals = [1, 1 + (yMax - 1) * 0.33, 1 + (yMax - 1) * 0.66, yMax];
  const path = points.current.length > 1
    ? "M " + points.current.map((p) => `${xF(p.t).toFixed(1)} ${yF(p.m).toFixed(1)}`).join(" L ")
    : `M ${PAD} ${H - PAD}`;
  const curveColor = phase === "crashed" ? "#E24A4A" : multColor(mult);
  const rocketLeft = (xF(tip.t) / W) * 100;
  const rocketTop = (yF(tip.m) / H) * 100;
  const running = phase === "running";

  return (
    <div data-testid="game-crash" className="max-w-6xl mx-auto">
      {/* HEADER */}
      <div className="flex items-center gap-3 mb-4">
        <div className="w-11 h-11 rounded-xl border border-emerald-400/40 bg-emerald-400/10 flex items-center justify-center">
          <TrendingUp size={22} className="text-emerald-400" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-extrabold text-2xl leading-tight">Dino Crash</h2>
          <p className="text-xs text-muted-foreground italic">Retírate antes de que reviente · multijugador en vivo</p>
        </div>
        <span className="inline-flex items-center gap-1.5 text-[11px] text-emerald-400 font-bold">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" /> EN VIVO
        </span>
      </div>

      {/* HISTORIAL */}
      <div className="flex items-center gap-1.5 mb-3 overflow-x-auto pb-1" data-testid="crash-history">
        {history.map((m, i) => {
          const c = multColor(m);
          return (
            <span key={i} style={{ color: c, borderColor: `${c}66`, background: `${c}1a` }} className="shrink-0 text-[11px] font-bold px-2.5 py-1 rounded-md border">
              {m.toFixed(2)}×
            </span>
          );
        })}
        {history.length === 0 && <span className="text-[11px] text-muted-foreground/50">Sin historial aún…</span>}
      </div>

      <div className="grid lg:grid-cols-[1fr_340px] gap-4">
        {/* PANEL GRÁFICO */}
        <div className="relative rounded-2xl overflow-hidden border-2 border-white/10 min-h-[360px] flex items-center justify-center"
          style={{ background: "radial-gradient(120% 110% at 50% 10%, #10241c 0%, #060a09 68%)" }}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 w-full h-full z-[1]">
            {axisVals.map((m, i) => (
              <line key={i} x1={PAD} x2={W - PAD} y1={yF(m)} y2={yF(m)} stroke="rgba(255,255,255,0.06)" strokeWidth="1" strokeDasharray="4 6" />
            ))}
            <defs>
              <linearGradient id="crashFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={curveColor} stopOpacity="0.25" />
                <stop offset="100%" stopColor={curveColor} stopOpacity="0" />
              </linearGradient>
            </defs>
            {(phase === "running" || phase === "crashed") && points.current.length > 1 && (
              <>
                <path d={`${path} L ${xF(tip.t)} ${H - PAD} L ${PAD} ${H - PAD} Z`} fill="url(#crashFill)" />
                <path d={path} fill="none" stroke={curveColor} strokeWidth="1.6" strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 3px ${curveColor}88)` }} />
              </>
            )}
          </svg>

          <div className="absolute inset-0 z-[2] pointer-events-none">
            {axisVals.map((m, i) => (
              <span key={i} className="absolute left-2 -translate-y-1/2 text-[9px] font-mono text-white/30" style={{ top: `${(yF(m) / H) * 100}%` }}>
                {m.toFixed(2)}×
              </span>
            ))}
          </div>

          {running && points.current.length > 1 && (
            <div className="absolute z-[3] rounded-full" style={{ left: `${rocketLeft}%`, top: `${rocketTop}%`, width: 9, height: 9, transform: "translate(-50%,-50%)", background: curveColor, boxShadow: `0 0 12px 2px ${curveColor}` }} />
          )}

          <div className="relative z-10 text-center px-4">
            <AnimatePresence mode="wait">
              {phase === "betting" && (
                <motion.div key="bet" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} data-testid="crash-betting">
                  <span className="block w-3 h-3 rounded-full bg-emerald-400 mx-auto mb-3 animate-pulse" style={{ filter: "drop-shadow(0 0 8px #10B981)" }} />
                  <p className="font-display font-bold text-lg text-emerald-400">Hagan sus apuestas</p>
                  <p className="font-display font-extrabold text-6xl tabular-nums text-crimson mt-1">{secs.toFixed(2)}<span className="text-2xl">s</span></p>
                </motion.div>
              )}
              {phase === "running" && eosWait && (
                <motion.div key="eos" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-2" data-testid="crash-eos-wait">
                  <Loader2 size={26} className="text-sky-400 animate-spin" />
                  <p className="text-sky-400 font-display font-bold text-base">Iniciando ronda...</p>
                  {round?.server_hash && <span className="text-[11px] font-mono text-sky-400/70 border border-sky-400/30 rounded px-2 py-0.5">Bloque #{parseInt(round.server_hash.slice(0, 9), 16) % 900000000 + 100000000}</span>}
                </motion.div>
              )}
              {phase === "running" && !eosWait && (
                <motion.div key="run" initial={{ opacity: 0 }} animate={{ opacity: 1 }} data-testid="crash-running">
                  <p className="font-display font-extrabold text-8xl tabular-nums" style={{ color: curveColor, textShadow: `0 0 34px ${curveColor}77` }} data-testid="crash-mult">
                    {mult.toFixed(2)}×
                  </p>
                  {myBet && myBet.cashed_at == null && <p className="text-emerald-400/90 text-sm mt-2">Ganarías <b>{fmt(myBet.amount * mult)}</b> CC</p>}
                </motion.div>
              )}
              {phase === "crashed" && (
                <motion.div key="boom" initial={{ scale: 0.85, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} data-testid="crash-boom">
                  <p className="font-display font-extrabold text-8xl text-crimson tabular-nums" style={{ textShadow: "0 0 28px rgba(226,74,74,0.45)" }}>
                    {(round?.crash_point || mult).toFixed(2)}×
                  </p>
                  <p className="text-crimson/70 font-semibold mt-2 tracking-[0.4em] text-sm">REVENTÓ</p>
                </motion.div>
              )}
              {!phase && <motion.p key="idle" className="text-muted-foreground text-sm">Conectando a la ronda en vivo…</motion.p>}
            </AnimatePresence>
          </div>

          <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between text-[10px] text-muted-foreground/70 z-10">
            <span className="inline-flex items-center gap-1.5 font-mono truncate max-w-[55%]">
              <ShieldCheck size={11} className="text-emerald-400/80" /> {round?.server_hash ? `${round.server_hash.slice(0, 18)}…` : "—"}
            </span>
            <span className="inline-flex items-center gap-1.5">Ronda #{round?.round_no ?? "—"} · Provably Fair</span>
          </div>
        </div>

        {/* CONTROLES / SIDEBAR */}
        <div className="space-y-3">
          <div className="glass-strong rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="label-overline text-[11px] text-emerald-400">Hacer Apuesta</span>
              <span className="flex-1 h-px bg-white/10" />
            </div>

            <div className="flex items-center gap-2 bg-black/30 rounded-lg px-3 py-2.5 mb-2">
              <img src="/coins/meat.png" alt="" className="w-4 h-4 object-contain" />
              <input type="number" min={100} value={bet} onChange={(e) => setBet(Math.max(100, Math.min(1000000, parseInt(e.target.value) || 100)))}
                data-testid="crash-bet-input" className="w-full bg-transparent text-sm font-bold focus:outline-none" />
              <span className="text-[11px] text-muted-foreground shrink-0">CC</span>
            </div>

            <div className="grid grid-cols-6 gap-1.5 mb-3">
              {QUICK.map(([l, v]) => (
                <button key={l} onClick={() => setBet(v)} data-testid={`crash-quick-${l}`} className="py-1.5 rounded-md bg-white/5 text-[10px] font-bold text-muted-foreground hover:text-gold hover:bg-gold/10 transition-colors">{l}</button>
              ))}
              <button onClick={() => setBet((b) => Math.max(100, Math.floor(b / 2)))} className="py-1.5 rounded-md bg-white/5 text-[10px] font-bold text-muted-foreground hover:text-gold hover:bg-gold/10">½</button>
              <button onClick={() => setBet((b) => Math.min(1000000, b * 2))} className="py-1.5 rounded-md bg-white/5 text-[10px] font-bold text-muted-foreground hover:text-gold hover:bg-gold/10">2×</button>
            </div>

            {/* AUTO RETIRO */}
            <div className="flex items-center justify-between mb-2">
              <button onClick={() => setAutoOn((v) => !v)} data-testid="crash-auto-toggle" className="flex items-center gap-2">
                <span className={`w-9 h-5 rounded-full transition-colors relative ${autoOn ? "bg-emerald-500" : "bg-white/15"}`}>
                  <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${autoOn ? "left-4" : "left-0.5"}`} />
                </span>
                <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Auto retiro</span>
              </button>
              {autoOn && (
                <div className="flex items-center gap-1 bg-black/30 rounded-lg px-2 py-1">
                  <input type="number" step="0.1" min="1.01" value={autoVal} onChange={(e) => setAutoVal(e.target.value)} data-testid="crash-auto-input" className="w-14 bg-transparent text-xs font-bold text-right focus:outline-none" />
                  <span className="text-xs text-muted-foreground">×</span>
                </div>
              )}
            </div>

            {autoOn && (
              <div className="grid grid-cols-5 gap-1.5 mb-3">
                {AUTO_PRESETS.map((v) => (
                  <button key={v} onClick={() => setAutoVal(v.toFixed(2))} className={`py-1 rounded-md text-[10px] font-bold transition-colors ${parseFloat(autoVal) === v ? "bg-emerald-500/20 text-emerald-400" : "bg-white/5 text-muted-foreground hover:text-emerald-400"}`}>{v}×</button>
                ))}
              </div>
            )}

            {/* BOTONES DE ACCIÓN */}
            {running && myBet && myBet.cashed_at == null ? (
              <button onClick={cashout} data-testid="crash-cashout" className="w-full py-3.5 rounded-xl font-display font-extrabold text-lg bg-emerald-500 text-background hover:brightness-110 transition-all active:scale-[0.98]">
                RETIRAR · {fmt(myBet.amount * mult)}
              </button>
            ) : myBet ? (
              <div data-testid="crash-mybet-status" className={`w-full py-3.5 rounded-xl font-display font-extrabold text-center ${myBet.cashed_at ? "bg-emerald-400/15 text-emerald-400 border border-emerald-400/30" : "bg-white/5 text-muted-foreground border border-white/10"}`}>
                {myBet.cashed_at ? `RETIRADO ${myBet.cashed_at}× · +${fmt(myBet.payout)}` : phase === "crashed" ? "REVENTÓ" : "EN JUEGO…"}
              </div>
            ) : (
              <button onClick={place} disabled={busy || phase !== "betting"} data-testid="crash-bet-btn" className="w-full py-3.5 rounded-xl font-display font-extrabold text-lg bg-emerald-500 text-background hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed">
                {phase === "betting" ? "APOSTAR" : "APUESTAS CERRADAS"}
              </button>
            )}
          </div>

          {/* MOON POOL (JACKPOT) */}
          <div className="glass rounded-xl p-3 border border-gold/25" data-testid="crash-jackpot">
            <div className="flex items-center justify-between">
              <span className="label-overline text-[10px] text-gold inline-flex items-center gap-1.5"><Trophy size={12} /> Moon Pool</span>
              <button onClick={() => setShowInfo(true)} data-testid="crash-info-btn" className="text-muted-foreground hover:text-gold"><Info size={13} /></button>
            </div>
            <p className="font-display font-extrabold text-2xl text-gold tabular-nums" data-testid="crash-jackpot-amount">{fmt(state?.jackpot)}</p>
            <p className="text-[10px] text-muted-foreground">Retírate a {state?.config?.jackpot_multiplier ?? 100}×+ para llevártelo</p>
            {state?.last_win?.amount > 0 && (
              <p className="text-[10px] text-emerald-400/80 truncate mt-1" data-testid="crash-jackpot-lastwin">
                Último pozo: {fmt(state.last_win.amount)} CC · {(state.last_win.winners || []).map((w) => w.name).join(", ") || "—"}
              </p>
            )}
          </div>

          {/* JUGADORES DE LA RONDA */}
          <div className="glass rounded-xl p-3" data-testid="crash-players">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400 inline-flex items-center gap-1.5"><Users size={12} /> Jugadores ({bets.length})</span>
              <span className="text-[11px] text-gold font-bold tabular-nums">{fmt(totalWagered)} CC</span>
            </div>
            <div className="space-y-1 max-h-[220px] overflow-y-auto pr-1">
              {rankedBets.length === 0 ? <p className="text-[11px] text-muted-foreground/50 py-3 text-center">Nadie ha apostado todavía</p> : rankedBets.map((b, i) => (
                <div key={b.user_id} className={`flex items-center gap-2 py-1.5 px-2 rounded-lg ${b.cashed_at ? "bg-emerald-400/10" : "hover:bg-white/5"}`} data-testid="crash-player-row">
                  <span className={`w-4 shrink-0 text-center text-[10px] font-bold ${i === 0 ? "text-gold" : i === 1 ? "text-slate-300" : i === 2 ? "text-amber-600" : "text-muted-foreground/40"}`}>{i + 1}</span>
                  <img src={b.avatar || "/logo192.png"} alt="" className="w-5 h-5 rounded object-cover shrink-0" />
                  <span className="flex-1 min-w-0 text-[12px] font-semibold truncate">{b.name}</span>
                  <span className="text-[11px] text-muted-foreground tabular-nums">{fmt(b.amount)}</span>
                  <span className={`text-[10px] font-bold w-14 text-right ${b.cashed_at ? "text-emerald-400" : "text-muted-foreground/70"}`}>{b.cashed_at ? `+${fmt(b.payout)}` : phase === "running" ? "Jugando" : "En espera"}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* MODAL INFORMATIVO MOON POOL */}
      <AnimatePresence>
        {showInfo && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setShowInfo(false)}>
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
            <div className="relative glass-strong rounded-2xl p-6 max-w-md w-full border border-gold/30" onClick={(e) => e.stopPropagation()} data-testid="crash-info-modal">
              <h3 className="font-display font-extrabold text-xl text-gold mb-1">Moon Pool</h3>
              <p className="text-sm text-muted-foreground mb-4">Un pozo acumulativo que crece con las apuestas de los jugadores.</p>
              <ol className="space-y-2 text-sm">
                <li><span className="text-gold font-bold">1.</span> El <b>{Math.round((state?.config?.jackpot_rate ?? 0.02) * 100)}%</b> de cada apuesta ingresa al Moon Pool.</li>
                <li><span className="text-gold font-bold">2.</span> Si te retiras en <b>{state?.config?.jackpot_multiplier ?? 100}× o más</b>, te llevas el pozo.</li>
                <li><span className="text-gold font-bold">3.</span> Se reparte proporcionalmente entre los ganadores de la ronda, según lo apostado.</li>
                <li><span className="text-gold font-bold">4.</span> Si nadie llega a {state?.config?.jackpot_multiplier ?? 100}×, el pozo se acumula para la siguiente ronda.</li>
              </ol>
              <button onClick={() => setShowInfo(false)} className="mt-4 w-full bg-gold text-background font-bold py-2.5 rounded-xl">Entendido</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
