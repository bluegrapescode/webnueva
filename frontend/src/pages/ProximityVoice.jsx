import React, { useState, useEffect, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Radio, Mic, MicOff, PhoneOff, Phone, Users, Volume2, VolumeX, Signal, Plus, Minus, Keyboard, Crosshair } from "lucide-react";
import { useSound } from "@/context/SoundContext";
import { useProximitySim, useMicLevel } from "@/lib/proximitySim";

const SHELL = { background: "linear-gradient(180deg,#24261F,#15170F)", boxShadow: "inset 0 1px 0 rgba(255,255,255,.07), 0 24px 60px rgba(0,0,0,.55)" };
const PLATE = { background: "#0B0F08", border: "1px solid rgba(124,168,66,.30)", boxShadow: "inset 0 0 40px rgba(124,168,66,.10)" };
const KEYCAP_LIVE = { background: "linear-gradient(180deg,#4C5A38,#28300F)", boxShadow: "inset 0 2px 0 rgba(255,255,255,.14), 0 3px 0 #12140A" };
const KEYCAP_IDLE = { background: "linear-gradient(180deg,#3A4030,#20240F)", boxShadow: "inset 0 2px 0 rgba(255,255,255,.10), 0 6px 0 #12140A" };
const LCD_GLOW = { textShadow: "0 0 10px rgba(124,168,66,.55)" };

const VU_SEGMENTS = 14;
const SIGNAL_BARS = 5;
const PTT_KEYS = [
  { code: "Space", label: "Espacio" },
  { code: "KeyV", label: "V" },
  { code: "KeyT", label: "T" },
  { code: "KeyC", label: "C" },
];

function signalBars(dist, hearing, exponent) {
  if (dist == null || dist > hearing) return 0;
  const frac = 1 - dist / hearing;
  const shaped = Math.pow(frac, 1 / exponent);
  return Math.max(1, Math.round(shaped * SIGNAL_BARS));
}

function VuMeter({ getLevel, active }) {
  const [lit, setLit] = useState(0);
  const raf = useRef(0);
  useEffect(() => {
    if (!active) { setLit(0); return undefined; }
    let alive = true;
    const tick = () => {
      if (!alive) return;
      const n = Math.round((getLevel() || 0) * VU_SEGMENTS);
      setLit((prev) => (n !== prev ? n : prev));
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => { alive = false; cancelAnimationFrame(raf.current); };
  }, [getLevel, active]);
  const HOT = VU_SEGMENTS - 4;
  return (
    <div className="flex gap-[3px] mt-3.5" data-testid="voice-mic-meter" data-lit={lit}>
      {Array.from({ length: VU_SEGMENTS }, (_, i) => (
        <span key={i} className="flex-1 h-[15px] rounded-[2px] transition-colors duration-75"
          style={{ background: i < lit ? (i >= HOT ? "#F0B429" : "#A3C96B") : "rgba(163,201,107,.12)", boxShadow: i < lit ? "0 0 8px rgba(124,168,66,.55)" : "none" }} />
      ))}
    </div>
  );
}

function SignalMeter({ bars }) {
  return (
    <span className="flex items-end gap-[2.5px] h-4 shrink-0" data-testid="voice-signal" data-bars={bars}>
      {Array.from({ length: SIGNAL_BARS }, (_, i) => (
        <span key={i} className={`w-1 rounded-sm transition-colors ${i < bars ? "bg-emerald-400" : "bg-white/15"}`} style={{ height: 5 + i * 3.7 }} />
      ))}
    </span>
  );
}

function Dial({ label, value, min, max, step, display, onChange, accent = "#A3C96B", testid }) {
  const frac = Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
  const R = 27, C = 2 * Math.PI * R, SWEEP = 0.75, angle = -135 + 270 * frac;
  return (
    <div className="text-center">
      <svg width="70" height="70" viewBox="0 0 70 70" className="mx-auto block">
        <circle cx="35" cy="35" r={R} fill="none" stroke="rgba(255,255,255,.10)" strokeWidth="5" strokeLinecap="round" strokeDasharray={`${C * SWEEP} ${C}`} transform="rotate(135 35 35)" />
        <circle cx="35" cy="35" r={R} fill="none" stroke={accent} strokeWidth="5" strokeLinecap="round" strokeDasharray={`${C * SWEEP * frac} ${C}`} transform="rotate(135 35 35)" style={{ transition: "stroke-dasharray .2s ease" }} />
        <circle cx="35" cy="35" r="17" fill="#1B1E14" stroke="rgba(255,255,255,.10)" />
        <line x1="35" y1="35" x2="35" y2="21" stroke="#DCE7C4" strokeWidth="2.5" strokeLinecap="round" transform={`rotate(${angle} 35 35)`} style={{ transition: "transform .2s ease" }} />
      </svg>
      <span className="block text-[10px] font-extrabold tracking-widest uppercase mt-1.5" style={{ color: "#9AA487" }}>{label}</span>
      <span className="block text-xs font-extrabold tabular-nums" style={{ color: "#DCE7C4" }} data-testid={`${testid}-value`}>{display}</span>
      <input type="range" min={min} max={max} step={step} value={value} aria-label={label} onChange={(e) => onChange(Number(e.target.value))} data-testid={testid}
        className="w-full h-1 mt-2 rounded-full bg-white/10 accent-gold cursor-pointer" />
    </div>
  );
}

// Proximity radar: you at centre, concentric range rings, a rotating sweep and a
// blip per nearby player positioned by live angle + distance. In-range players
// glow green, speakers pulse gold, out-of-range fade to the edge.
function Radar({ players, hearing, serverRadius, connected }) {
  const SIZE = 300, C = SIZE / 2, MAXR = C - 14;
  const scale = MAXR / (serverRadius * 1.25);
  const hearingR = Math.min(MAXR, hearing * scale);
  return (
    <div className="relative mx-auto" style={{ width: SIZE, height: SIZE }} data-testid="voice-radar">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} className="block">
        <defs>
          <radialGradient id="radarbg" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#12180C" /><stop offset="100%" stopColor="#080A05" />
          </radialGradient>
          <linearGradient id="sweep" x1="50%" y1="50%" x2="100%" y2="50%">
            <stop offset="0%" stopColor="rgba(124,168,66,.45)" /><stop offset="100%" stopColor="rgba(124,168,66,0)" />
          </linearGradient>
        </defs>
        <circle cx={C} cy={C} r={MAXR} fill="url(#radarbg)" stroke="rgba(124,168,66,.20)" strokeWidth="1.5" />
        {[0.33, 0.66, 1].map((f) => (
          <circle key={f} cx={C} cy={C} r={MAXR * f} fill="none" stroke="rgba(124,168,66,.12)" strokeWidth="1" />
        ))}
        <line x1={C} y1="14" x2={C} y2={SIZE - 14} stroke="rgba(124,168,66,.10)" strokeWidth="1" />
        <line x1="14" y1={C} x2={SIZE - 14} y2={C} stroke="rgba(124,168,66,.10)" strokeWidth="1" />
        {/* hearing ring — the range you can hear */}
        <circle cx={C} cy={C} r={hearingR} fill="rgba(124,168,66,.06)" stroke="#F0B429" strokeWidth="1.5" strokeDasharray="4 4" style={{ transition: "r .25s ease" }} data-testid="voice-radar-range-ring" />
        {/* rotating sweep */}
        {connected && (
          <g style={{ transformOrigin: `${C}px ${C}px`, animation: "radarSweep 4s linear infinite" }}>
            <path d={`M${C},${C} L${SIZE - 14},${C} A${MAXR},${MAXR} 0 0 1 ${C + MAXR * Math.cos(-0.6)},${C + MAXR * Math.sin(-0.6)} Z`} fill="url(#sweep)" />
          </g>
        )}
      </svg>
      {/* centre = you */}
      <div className="absolute" style={{ left: C, top: C, transform: "translate(-50%,-50%)" }}>
        <div className="relative flex items-center justify-center">
          <span className="absolute h-8 w-8 rounded-full border border-gold/40 animate-ping" style={{ opacity: connected ? 0.5 : 0 }} />
          <Crosshair size={18} className="text-gold" />
        </div>
      </div>
      {/* blips */}
      <AnimatePresence>
        {connected && players.map((p) => {
          const r = Math.min(MAXR, p.dist * scale);
          const x = C + r * Math.cos(p.angle);
          const y = C + r * Math.sin(p.angle);
          const inR = p.dist <= hearing;
          const speaking = inR && p.speaking && !p.muted;
          return (
            <motion.div key={p.id} initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}
              className="absolute" style={{ left: x, top: y, transform: "translate(-50%,-50%)" }}
              data-testid={`voice-radar-blip-${p.id}`} data-inrange={inR} data-speaking={speaking} title={`${p.name} · ${Math.round(p.dist)} m`}>
              {speaking && <span className="absolute inset-0 -m-1.5 rounded-full bg-gold/40 animate-ping" />}
              <span className="block rounded-full" style={{
                width: speaking ? 13 : 10, height: speaking ? 13 : 10,
                background: p.muted ? "#8A5050" : inR ? (speaking ? "#F0B429" : "#7CA842") : "rgba(150,160,140,.35)",
                boxShadow: inR ? `0 0 10px ${speaking ? "#F0B429" : "#7CA842"}` : "none",
                border: "1px solid rgba(0,0,0,.5)", transition: "all .2s ease",
              }} />
            </motion.div>
          );
        })}
      </AnimatePresence>
      <style>{`@keyframes radarSweep{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

export default function ProximityVoice() {
  const { play } = useSound();
  const sim = useProximitySim();
  const mic = useMicLevel();
  const [micMode, setMicMode] = useState("ptt");
  const [pttKey, setPttKey] = useState("Space");
  const [micMuted, setMicMuted] = useState(false);
  const [transmitting, setTransmitting] = useState(false);
  const [master, setMaster] = useState(0.8);
  const [allMuted, setAllMuted] = useState(false);
  const [exponent, setExponent] = useState(1.6);

  const connected = sim.on;
  const micActive = connected && !micMuted && (micMode === "ptt" ? transmitting : true);
  const pttLabel = PTT_KEYS.find((k) => k.code === pttKey)?.label || "Espacio";

  useEffect(() => {
    if (!connected || micMode !== "ptt") return undefined;
    const down = (e) => { if (e.code === pttKey && !e.repeat) { if (e.code === "Space") e.preventDefault(); setTransmitting(true); } };
    const up = (e) => { if (e.code === pttKey) { if (e.code === "Space") e.preventDefault(); setTransmitting(false); } };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); setTransmitting(false); };
  }, [connected, micMode, pttKey]);

  const handleConnect = async () => { play("open"); sim.connect(); await mic.start(); };
  const handleDisconnect = () => { play("close"); sim.disconnect(); mic.stop(); setTransmitting(false); };

  const stepMaster = (d) => { play("click"); setMaster((m) => Math.max(0, Math.min(1, Math.round((m + d) * 100) / 100))); };
  const toggleMuteAll = () => { play("click"); const next = !allMuted; setAllMuted(next); sim.setAllMuted(next); };

  const inRange = useMemo(() => sim.players.filter((p) => p.dist <= sim.hearing), [sim.players, sim.hearing]);
  const outRange = useMemo(() => sim.players.filter((p) => p.dist > sim.hearing), [sim.players, sim.hearing]);
  const speakingNow = useMemo(() => inRange.filter((p) => p.speaking && !p.muted).length, [inRange]);
  const sortByDist = (a, b) => a.dist - b.dist;

  const meta = connected ? { label: "EN LÍNEA", color: "#A3C96B" } : { label: "FUERA DE LÍNEA", color: "#7C8590" };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-14">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="mb-8 flex items-end justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Radio className="text-gold" size={26} />
          <div>
            <p className="label-overline text-xs text-gold">Comunicación en el juego</p>
            <h1 className="font-display font-extrabold text-4xl tracking-tighter">Radio de Proximidad</h1>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          {connected && (
            <span className="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-lg glass border border-emerald-500/25 text-emerald-400 text-xs font-bold" data-testid="voice-inrange-count">
              <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-70 animate-ping" /><span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" /></span>
              {inRange.length} en rango{speakingNow > 0 ? ` · ${speakingNow} hablando` : ""}
            </span>
          )}
          {connected ? (
            <button onClick={handleDisconnect} data-testid="voice-disconnect" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-crimson text-white font-bold text-sm hover:brightness-110 transition-all">
              <PhoneOff size={16} /> Apagar radio
            </button>
          ) : (
            <button onClick={handleConnect} data-testid="voice-connect" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gold text-background font-bold text-sm hover:brightness-110 hover:gold-glow transition-all">
              <Phone size={16} /> Encender radio
            </button>
          )}
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-[400px_minmax(0,1fr)] gap-6 items-start">
        {/* ------- handset / control panel ------- */}
        <div className="rounded-[22px] border border-white/10 p-5 space-y-[18px]" style={SHELL} data-testid="voice-panel">
          {/* LCD */}
          <div className="rounded-xl p-4 sm:p-[18px]" style={PLATE}>
            <div className="flex items-start justify-between gap-3">
              <div className="font-mono min-w-0" style={LCD_GLOW}>
                <p className="text-[10px] tracking-[0.20em] opacity-75" style={{ color: "#A3C96B" }}>CANAL DE PROXIMIDAD</p>
                <p className="text-2xl sm:text-[27px] font-bold leading-tight truncate" style={{ color: meta.color }}>{meta.label}</p>
                <p className="text-[11px] opacity-80" style={{ color: "#A3C96B" }}>ALCANCE {sim.hearing} m · {connected ? `${inRange.length} EN ESCUCHA` : "CANAL CERRADO"}</p>
              </div>
              <div className="text-right font-mono shrink-0" style={{ ...LCD_GLOW, color: "#A3C96B" }}>
                <p className="text-[10px] opacity-70">EN CANAL</p>
                <p className="text-xl font-bold tabular-nums" data-testid="voice-participant-count">{sim.players.length}</p>
              </div>
            </div>
            <VuMeter getLevel={mic.getLevel} active={micActive} />
            <div className="flex justify-between mt-1.5 font-mono text-[10px] opacity-70" style={{ color: "#A3C96B" }}>
              <span>NIVEL DE MICRÓFONO</span>
              <span>{micMuted ? "SILENCIADO" : micActive ? (mic.granted ? "ABIERTO" : "SIN PERMISO") : "EN ESPERA"}</span>
            </div>
          </div>

          {/* mic mode */}
          <div className="flex gap-2">
            <button onClick={() => { setMicMode("ptt"); setTransmitting(false); play("click"); }} data-testid="voice-mic-mode-ptt" className={`flex-1 text-xs font-bold px-3 py-2.5 rounded-lg border transition-all ${micMode === "ptt" ? "bg-gold/15 text-gold border-gold/40" : "glass border-white/15 text-muted-foreground hover:text-foreground"}`}>Pulsar para hablar</button>
            <button onClick={() => { setMicMode("open"); play("click"); }} data-testid="voice-mic-mode-open" className={`flex-1 text-xs font-bold px-3 py-2.5 rounded-lg border transition-all ${micMode === "open" ? "bg-gold/15 text-gold border-gold/40" : "glass border-white/15 text-muted-foreground hover:text-foreground"}`}>Micrófono abierto</button>
          </div>

          {/* PTT key selector (only in PTT mode) */}
          {micMode === "ptt" && (
            <div className="rounded-lg glass border border-white/10 px-3 py-2.5" data-testid="voice-ptt-key-row">
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 inline-flex items-center gap-1.5"><Keyboard size={12} /> Tecla para hablar</p>
              <div className="flex gap-1.5">
                {PTT_KEYS.map((k) => (
                  <button key={k.code} onClick={() => { setPttKey(k.code); play("click"); }} data-testid={`voice-ptt-key-${k.code}`}
                    className={`flex-1 text-xs font-bold py-1.5 rounded-md border transition-all ${pttKey === k.code ? "bg-gold/20 text-gold border-gold/50" : "border-white/10 text-muted-foreground hover:text-foreground"}`}>{k.label}</button>
                ))}
              </div>
            </div>
          )}

          {/* big talk / mute button */}
          {micMode === "ptt" ? (
            <button
              data-testid="voice-ptt-button"
              onMouseDown={() => connected && setTransmitting(true)}
              onMouseUp={() => setTransmitting(false)}
              onMouseLeave={() => setTransmitting(false)}
              onTouchStart={(e) => { e.preventDefault(); connected && setTransmitting(true); }}
              onTouchEnd={() => setTransmitting(false)}
              disabled={!connected || micMuted}
              className="w-full py-5 px-4 rounded-2xl border border-white/10 text-center select-none disabled:opacity-60 disabled:cursor-default"
              style={connected && transmitting && !micMuted ? KEYCAP_LIVE : KEYCAP_IDLE}>
              <span className="block text-lg font-extrabold tracking-wider" style={{ color: connected && transmitting && !micMuted ? "#DDF3B6" : "#DCE7C4" }}>
                {micMuted ? "MIC SILENCIADO" : connected && transmitting ? "TRANSMITIENDO" : <>MANTÉN&nbsp; [ {pttLabel} ]</>}
              </span>
              <span className="block text-[11px]" style={{ color: "#9AA487" }}>
                {!connected ? "enciende la radio para hablar" : micMuted ? "reactiva el micrófono abajo" : transmitting ? "suelta para volver a escuchar" : `mantén pulsado o la tecla ${pttLabel}`}
              </span>
            </button>
          ) : (
            <button onClick={() => { setMicMuted((m) => !m); play("click"); }} disabled={!connected} data-testid="voice-mute-toggle"
              className="w-full py-5 px-4 rounded-2xl border border-white/10 text-center transition-all disabled:opacity-60"
              style={connected && !micMuted ? KEYCAP_LIVE : KEYCAP_IDLE}>
              <span className="flex items-center justify-center gap-2 text-lg font-extrabold tracking-wider" style={{ color: micMuted ? "#C99" : connected ? "#DDF3B6" : "#DCE7C4" }}>
                {micMuted ? <MicOff size={19} /> : <Mic size={19} />} {micMuted ? "MICRÓFONO SILENCIADO" : "MICRÓFONO ABIERTO"}
              </span>
              <span className="block text-[11px]" style={{ color: "#9AA487" }}>{connected ? (micMuted ? "pulsa para volver a hablar" : "pulsa para silenciarte") : "enciende la radio para hablar"}</span>
            </button>
          )}

          {/* extra mic mute for PTT mode */}
          {micMode === "ptt" && (
            <button onClick={() => { setMicMuted((m) => !m); play("click"); }} disabled={!connected} data-testid="voice-mic-mute-ptt"
              className={`w-full inline-flex items-center justify-center gap-2 text-xs font-bold px-3 py-2.5 rounded-lg border transition-all disabled:opacity-50 ${micMuted ? "bg-crimson/15 text-crimson border-crimson/30" : "glass border-white/15 text-muted-foreground hover:text-foreground"}`}>
              {micMuted ? <MicOff size={14} /> : <Mic size={14} />} {micMuted ? "Micrófono silenciado" : "Silenciar mi micrófono"}
            </button>
          )}

          {/* master volume */}
          <div className="rounded-lg glass border border-white/10 px-3 py-3" data-testid="voice-master-control">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground inline-flex items-center gap-1.5"><Volume2 size={12} /> Volumen general</span>
              <span className="text-xs font-extrabold tabular-nums text-gold" data-testid="voice-master-value">{Math.round(master * 100)}%</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => stepMaster(-0.05)} data-testid="voice-master-minus" aria-label="Bajar volumen" className="w-9 h-9 shrink-0 rounded-md bg-white/10 border border-white/10 text-gold hover:bg-white/15 transition-colors inline-flex items-center justify-center"><Minus size={15} /></button>
              <input type="range" min={0} max={100} step={1} value={Math.round(master * 100)} onChange={(e) => setMaster(Number(e.target.value) / 100)} aria-label="Volumen general" data-testid="voice-set-master"
                className="flex-1 h-1.5 rounded-full bg-white/10 accent-gold cursor-pointer" />
              <button onClick={() => stepMaster(0.05)} data-testid="voice-master-plus" aria-label="Subir volumen" className="w-9 h-9 shrink-0 rounded-md bg-white/10 border border-white/10 text-gold hover:bg-white/15 transition-colors inline-flex items-center justify-center"><Plus size={15} /></button>
            </div>
            <button onClick={toggleMuteAll} disabled={!connected} data-testid="voice-mute-all"
              className={`w-full mt-2.5 inline-flex items-center justify-center gap-2 text-xs font-bold px-3 py-2 rounded-md border transition-all disabled:opacity-50 ${allMuted ? "bg-crimson/15 text-crimson border-crimson/30" : "border-white/10 text-muted-foreground hover:text-foreground"}`}>
              {allMuted ? <VolumeX size={14} /> : <Volume2 size={14} />} {allMuted ? "Todos silenciados — reactivar" : "Silenciar a todos"}
            </button>
          </div>

          {/* dials */}
          <div className="grid grid-cols-2 gap-3">
            <Dial label="Nitidez" value={exponent} min={0.6} max={3} step={0.1} display={exponent.toFixed(1)} onChange={setExponent} testid="voice-set-exponent" />
            <Dial label="Alcance" accent="#F0B429" value={sim.hearing} min={20} max={sim.serverRadius} step={5} display={`${sim.hearing} m`} onChange={sim.setHearing} testid="voice-set-hearing" />
          </div>

          <p className="text-[11px] leading-relaxed" style={{ color: "#7E8672" }}>
            El dial <b style={{ color: "#F0B429" }}>Alcance</b> define hasta dónde oyes. Baja el radio y verás cómo los jugadores lejanos salen del anillo del radar y de la lista en tiempo real.
          </p>
        </div>

        {/* ------- radar + roster ------- */}
        <div className="space-y-6">
          {/* radar */}
          <div className="glass rounded-2xl p-5" data-testid="voice-radar-card">
            <div className="flex items-center justify-between gap-3 mb-4">
              <p className="label-overline text-[10px] text-muted-foreground inline-flex items-center gap-1.5"><Crosshair size={12} /> Radar de proximidad</p>
              {connected && <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-gold/10 text-gold border border-gold/25">anillo = tu alcance ({sim.hearing} m)</span>}
            </div>
            <Radar players={sim.players} hearing={sim.hearing} serverRadius={sim.serverRadius} connected={connected} />
            {connected && (
              <div className="flex items-center justify-center gap-4 mt-4 text-[10.5px] text-muted-foreground">
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#7CA842]" /> en rango</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#F0B429]" /> hablando</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#8A5050]" /> silenciado</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-white/25" /> fuera</span>
              </div>
            )}
          </div>

          {/* roster */}
          <div className="glass rounded-2xl overflow-hidden" data-testid="voice-participants-list">
            <div className="flex items-center justify-between gap-3 px-4 py-3.5 border-b border-white/10">
              <p className="label-overline text-[10px] text-muted-foreground inline-flex items-center gap-1.5"><Users size={12} /> Canales cerca de ti</p>
              {connected && <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">{inRange.length} en rango · {outRange.length} fuera</span>}
            </div>

            {!connected ? (
              <p className="text-sm text-muted-foreground py-10 px-4 text-center">Enciende la radio para ver quién está cerca de ti en el juego.</p>
            ) : (
              <div>
                <AnimatePresence initial={false}>
                  {[...inRange].sort(sortByDist).map((p) => {
                    const bars = signalBars(p.dist, sim.hearing, exponent);
                    return (
                      <motion.div key={p.id} layout initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }} transition={{ duration: 0.25 }}
                        className={`flex items-center gap-3.5 px-4 py-3.5 border-b border-white/10 last:border-b-0 transition-colors ${p.speaking && !p.muted ? "bg-gold/[0.06]" : ""}`} data-testid={`voice-participant-${p.id}`} data-speaking={p.speaking && !p.muted}>
                        <SignalMeter bars={p.muted ? 0 : bars} />
                        <span className="flex-1 min-w-0">
                          <span className="flex items-center gap-2">
                            <span className="block text-sm font-semibold truncate" data-testid={`voice-persona-${p.id}`}>{p.name}</span>
                            {p.speaking && !p.muted && <span className="relative flex h-2 w-2 shrink-0" data-testid={`voice-speaking-${p.id}`}><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-gold opacity-70" /><span className="relative inline-flex rounded-full h-2 w-2 bg-gold" /></span>}
                          </span>
                          <span className="block text-[10.5px] font-mono text-muted-foreground/80 truncate" data-testid={`voice-range-${p.id}`}>
                            {p.dino} · {Math.round(p.dist)} m {p.muted ? "· silenciado" : p.speaking ? "· hablando" : ""}
                          </span>
                        </span>
                        <input type="range" min={0} max={100} step={1} value={Math.round(p.vol * 100)} disabled={p.muted} onChange={(e) => sim.setVol(p.id, Number(e.target.value) / 100)}
                          aria-label={`Volumen de ${p.name}`} data-testid={`voice-speaker-vol-${p.id}`}
                          className="hidden sm:block w-24 md:w-32 h-1.5 rounded-full bg-white/10 accent-emerald-400 cursor-pointer disabled:opacity-40 shrink-0" />
                        <button onClick={() => sim.toggleMute(p.id)} data-testid={`voice-speaker-mute-${p.id}`} aria-label={p.muted ? "Reactivar" : "Silenciar"}
                          className={`inline-flex items-center justify-center h-8 w-8 shrink-0 rounded-lg border transition-all ${p.muted ? "bg-crimson/15 text-crimson border-crimson/30" : "glass border-white/15 text-muted-foreground hover:text-foreground"}`}>
                          {p.muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
                        </button>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>

                {inRange.length === 0 && <p className="text-sm text-muted-foreground py-6 px-4 text-center">Nadie en rango. Sube el <b className="text-gold">Alcance</b> o espera a que alguien se acerque.</p>}

                {outRange.length > 0 && (
                  <div className="bg-black/20">
                    <p className="px-4 pt-3 pb-1 label-overline text-[10px] text-muted-foreground/60 inline-flex items-center gap-1.5"><Signal size={11} /> Fuera de rango</p>
                    {[...outRange].sort(sortByDist).map((p) => (
                      <div key={p.id} className="flex items-center gap-3.5 px-4 py-2.5 border-t border-white/5 opacity-45" data-testid={`voice-participant-${p.id}`}>
                        <SignalMeter bars={0} />
                        <span className="flex-1 min-w-0">
                          <span className="block text-sm font-semibold truncate">{p.name}</span>
                          <span className="block text-[10.5px] font-mono text-muted-foreground/70 truncate" data-testid={`voice-range-${p.id}`}>{p.dino} · {Math.round(p.dist)} m · fuera de alcance</span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
