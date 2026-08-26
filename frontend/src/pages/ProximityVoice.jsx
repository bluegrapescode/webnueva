import React, { useState, useEffect, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Radio, Mic, MicOff, PhoneOff, Phone, Users, Volume2, VolumeX, RotateCcw, Radar, Signal } from "lucide-react";
import { useSound } from "@/context/SoundContext";
import { useProximitySim, useMicLevel } from "@/lib/proximitySim";

const SHELL = { background: "linear-gradient(180deg,#24261F,#15170F)", boxShadow: "inset 0 1px 0 rgba(255,255,255,.07), 0 24px 60px rgba(0,0,0,.55)" };
const PLATE = { background: "#0B0F08", border: "1px solid rgba(124,168,66,.30)", boxShadow: "inset 0 0 40px rgba(124,168,66,.10)" };
const KEYCAP_LIVE = { background: "linear-gradient(180deg,#4C5A38,#28300F)", boxShadow: "inset 0 2px 0 rgba(255,255,255,.14), 0 3px 0 #12140A" };
const KEYCAP_IDLE = { background: "linear-gradient(180deg,#3A4030,#20240F)", boxShadow: "inset 0 2px 0 rgba(255,255,255,.10), 0 6px 0 #12140A" };
const LCD_GLOW = { textShadow: "0 0 10px rgba(124,168,66,.55)" };

const VU_SEGMENTS = 14;
const SIGNAL_BARS = 5;

// bars 0..5 from a live distance vs hearing radius, sharpened by "nitidez".
function signalBars(dist, hearing, exponent) {
  if (dist == null || dist > hearing) return 0;
  const frac = 1 - dist / hearing; // 1 near, 0 at the edge
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

// The proximity radar: concentric range rings, a rotating sweep, the highlighted
// hearing ring (scales with the Alcance dial) and a blip for each nearby player.
function ProximityRadar({ players, hearing, serverRadius }) {
  const SIZE = 320, C = SIZE / 2, MAX_R = 138;
  const scale = MAX_R / serverRadius;
  const hearingR = hearing * scale;
  return (
    <div className="relative mx-auto" style={{ width: SIZE, height: SIZE }} data-testid="voice-radar">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} className="absolute inset-0">
        <defs>
          <radialGradient id="radarBg" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#0e1a0a" />
            <stop offset="100%" stopColor="#080b06" />
          </radialGradient>
        </defs>
        <circle cx={C} cy={C} r={MAX_R} fill="url(#radarBg)" stroke="rgba(124,168,66,.25)" strokeWidth="1.5" />
        {[0.25, 0.5, 0.75].map((f) => (
          <circle key={f} cx={C} cy={C} r={MAX_R * f} fill="none" stroke="rgba(124,168,66,.14)" strokeWidth="1" />
        ))}
        <line x1={C} y1={C - MAX_R} x2={C} y2={C + MAX_R} stroke="rgba(124,168,66,.12)" strokeWidth="1" />
        <line x1={C - MAX_R} y1={C} x2={C + MAX_R} y2={C} stroke="rgba(124,168,66,.12)" strokeWidth="1" />
        {/* hearing radius — the range that actually decides who you hear */}
        <circle cx={C} cy={C} r={hearingR} fill="rgba(240,180,41,.06)" stroke="#F0B429" strokeWidth="1.5" strokeDasharray="4 4" style={{ transition: "r .25s ease" }} />
      </svg>

      {/* rotating sweep */}
      <div className="absolute inset-0 rounded-full overflow-hidden pointer-events-none" style={{ padding: (SIZE - MAX_R * 2) / 2 }}>
        <div className="w-full h-full rounded-full radar-sweep" style={{ background: "conic-gradient(from 0deg, rgba(124,168,66,.35), rgba(124,168,66,0) 60deg, transparent 320deg)" }} />
      </div>

      {/* you (center) */}
      <div className="absolute" style={{ left: C, top: C, transform: "translate(-50%,-50%)" }}>
        <span className="relative flex h-3 w-3">
          <span className="absolute inline-flex h-full w-full rounded-full bg-gold opacity-60 animate-ping" />
          <span className="relative inline-flex rounded-full h-3 w-3 bg-gold" style={{ boxShadow: "0 0 10px rgba(240,180,41,.8)" }} />
        </span>
      </div>

      {/* player blips */}
      {players.map((p) => {
        const d = Math.min(p.dist, serverRadius);
        const x = C + Math.cos(p.angle) * d * scale;
        const y = C + Math.sin(p.angle) * d * scale;
        const inRange = p.dist <= hearing;
        const color = inRange ? (p.speaking ? "#3FB960" : "#A3C96B") : "#5b6350";
        return (
          <div key={p.id} className="absolute -translate-x-1/2 -translate-y-1/2 group" style={{ left: x, top: y, transition: "left .25s linear, top .25s linear" }} data-testid={`radar-blip-${p.id}`} data-inrange={inRange}>
            {p.speaking && inRange && <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-5 w-5 rounded-full animate-ping" style={{ background: "rgba(63,185,96,.5)" }} />}
            <span className="relative block rounded-full" style={{ width: inRange ? 9 : 7, height: inRange ? 9 : 7, background: color, boxShadow: inRange ? `0 0 8px ${color}` : "none", opacity: inRange ? 1 : 0.55 }} />
            <span className="absolute left-1/2 -translate-x-1/2 top-3 whitespace-nowrap text-[9px] font-bold px-1.5 py-0.5 rounded bg-black/70 border border-white/10 opacity-0 group-hover:opacity-100 transition-opacity" style={{ color }}>
              {p.name} · {Math.round(p.dist)}m
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function ProximityVoice() {
  const { play } = useSound();
  const sim = useProximitySim();
  const mic = useMicLevel();
  const [micMode, setMicMode] = useState("ptt"); // ptt | open
  const [muted, setMuted] = useState(false);
  const [transmitting, setTransmitting] = useState(false);
  const [master, setMaster] = useState(0.8);
  const [exponent, setExponent] = useState(1.6);

  const connected = sim.on;
  const micActive = connected && (micMode === "ptt" ? transmitting : !muted);

  // Push-to-talk via spacebar (hold).
  useEffect(() => {
    if (!connected || micMode !== "ptt") return undefined;
    const down = (e) => { if (e.code === "Space" && !e.repeat) { e.preventDefault(); setTransmitting(true); } };
    const up = (e) => { if (e.code === "Space") { e.preventDefault(); setTransmitting(false); } };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); setTransmitting(false); };
  }, [connected, micMode]);

  const handleConnect = async () => { play("open"); sim.connect(); await mic.start(); };
  const handleDisconnect = () => { play("close"); sim.disconnect(); mic.stop(); setTransmitting(false); };

  const inRange = useMemo(() => sim.players.filter((p) => p.dist <= sim.hearing), [sim.players, sim.hearing]);
  const outRange = useMemo(() => sim.players.filter((p) => p.dist > sim.hearing), [sim.players, sim.hearing]);
  const sortByDist = (a, b) => a.dist - b.dist;

  const meta = connected
    ? { label: "EN LÍNEA", color: "#A3C96B" }
    : { label: "FUERA DE LÍNEA", color: "#7C8590" };

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
            <span className="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-lg glass border border-emerald-500/25 text-emerald-400 text-xs font-bold">
              <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-70 animate-ping" /><span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" /></span>
              {inRange.length} en rango
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
        {/* ------- handset ------- */}
        <div className="rounded-[22px] border border-white/10 p-5" style={SHELL} data-testid="voice-panel">
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
              <span>{micActive ? (mic.granted ? "ABIERTO" : "SIN PERMISO") : "SILENCIO"}</span>
            </div>
          </div>

          {micMode === "ptt" ? (
            <button
              data-testid="voice-ptt-button"
              onMouseDown={() => connected && setTransmitting(true)}
              onMouseUp={() => setTransmitting(false)}
              onMouseLeave={() => setTransmitting(false)}
              onTouchStart={(e) => { e.preventDefault(); connected && setTransmitting(true); }}
              onTouchEnd={() => setTransmitting(false)}
              disabled={!connected}
              className="mt-[18px] w-full py-5 px-4 rounded-2xl border border-white/10 text-center select-none disabled:opacity-60 disabled:cursor-default"
              style={connected && transmitting ? KEYCAP_LIVE : KEYCAP_IDLE}>
              <span className="block text-lg font-extrabold tracking-wider" style={{ color: connected && transmitting ? "#DDF3B6" : "#DCE7C4" }}>
                {connected && transmitting ? "TRANSMITIENDO" : <>MANTÉN&nbsp; [ Espacio ]</>}
              </span>
              <span className="block text-[11px]" style={{ color: "#9AA487" }}>
                {!connected ? "enciende la radio para hablar" : transmitting ? "suelta para volver a escuchar" : "mantén pulsado o barra espaciadora"}
              </span>
            </button>
          ) : (
            <button onClick={() => setMuted((m) => !m)} disabled={!connected} data-testid="voice-mute-toggle"
              className="mt-[18px] w-full py-5 px-4 rounded-2xl border border-white/10 text-center transition-all disabled:opacity-60"
              style={connected && !muted ? KEYCAP_LIVE : KEYCAP_IDLE}>
              <span className="flex items-center justify-center gap-2 text-lg font-extrabold tracking-wider" style={{ color: muted ? "#C99" : connected ? "#DDF3B6" : "#DCE7C4" }}>
                {muted ? <MicOff size={19} /> : <Mic size={19} />} {muted ? "MICRÓFONO SILENCIADO" : "MICRÓFONO ABIERTO"}
              </span>
              <span className="block text-[11px]" style={{ color: "#9AA487" }}>{connected ? (muted ? "pulsa para volver a hablar" : "pulsa para silenciarte") : "enciende la radio para hablar"}</span>
            </button>
          )}

          <div className="flex gap-2 mt-4">
            <button onClick={() => { setMicMode("ptt"); play("click"); }} data-testid="voice-mic-mode-ptt" className={`flex-1 text-xs font-bold px-3 py-2.5 rounded-lg border transition-all ${micMode === "ptt" ? "bg-gold/15 text-gold border-gold/40" : "glass border-white/15 text-muted-foreground hover:text-foreground"}`}>Pulsar para hablar</button>
            <button onClick={() => { setMicMode("open"); play("click"); }} data-testid="voice-mic-mode-open" className={`flex-1 text-xs font-bold px-3 py-2.5 rounded-lg border transition-all ${micMode === "open" ? "bg-gold/15 text-gold border-gold/40" : "glass border-white/15 text-muted-foreground hover:text-foreground"}`}>Micrófono abierto</button>
          </div>

          <div className="grid grid-cols-3 gap-3 mt-[18px]">
            <Dial label="Volumen" value={Math.round(master * 100)} min={0} max={100} step={1} display={`${Math.round(master * 100)}%`} onChange={(v) => setMaster(v / 100)} testid="voice-set-master" />
            <Dial label="Nitidez" value={exponent} min={0.6} max={3} step={0.1} display={exponent.toFixed(1)} onChange={setExponent} testid="voice-set-exponent" />
            <Dial label="Alcance" accent="#F0B429" value={sim.hearing} min={20} max={sim.serverRadius} step={5} display={`${sim.hearing} m`} onChange={sim.setHearing} testid="voice-set-hearing" />
          </div>

          <p className="text-[11px] mt-4 leading-relaxed" style={{ color: "#7E8672" }}>
            El dial <b style={{ color: "#F0B429" }}>Alcance</b> define hasta dónde oyes. Baja el radio y verás cómo los jugadores más lejanos salen de rango en tiempo real en el radar y en la lista.
          </p>
        </div>

        {/* ------- radar + channels ------- */}
        <div className="space-y-6">
          <div className="glass rounded-2xl p-5" data-testid="voice-radar-card">
            <div className="flex items-center justify-between mb-4">
              <p className="label-overline text-[10px] text-muted-foreground inline-flex items-center gap-1.5"><Radar size={12} className="text-gold" /> Radar de proximidad</p>
              <div className="flex items-center gap-3 text-[10px] font-semibold">
                <span className="inline-flex items-center gap-1.5 text-muted-foreground"><span className="h-2 w-2 rounded-full bg-gold" /> Tú</span>
                <span className="inline-flex items-center gap-1.5 text-emerald-400"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Hablando</span>
                <span className="inline-flex items-center gap-1.5" style={{ color: "#5b6350" }}><span className="h-2 w-2 rounded-full" style={{ background: "#5b6350" }} /> Fuera</span>
              </div>
            </div>
            {connected ? (
              <ProximityRadar players={sim.players} hearing={sim.hearing} serverRadius={sim.serverRadius} />
            ) : (
              <div className="h-[320px] grid place-items-center text-center">
                <div>
                  <Radar size={40} className="mx-auto text-muted-foreground/40 mb-3" />
                  <p className="text-sm text-muted-foreground">Enciende la radio para escanear a los jugadores cercanos.</p>
                </div>
              </div>
            )}
          </div>

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
                        className="flex items-center gap-3.5 px-4 py-3.5 border-b border-white/10 last:border-b-0" data-testid={`voice-participant-${p.id}`}>
                        <SignalMeter bars={bars} />
                        <span className="flex-1 min-w-0">
                          <span className="flex items-center gap-2">
                            <span className="block text-sm font-semibold truncate" data-testid={`voice-persona-${p.id}`}>{p.name}</span>
                            {p.speaking && <span className="relative flex h-2 w-2 shrink-0"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-70" /><span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" /></span>}
                          </span>
                          <span className="block text-[10.5px] font-mono text-muted-foreground/80 truncate" data-testid={`voice-range-${p.id}`}>
                            {p.dino} · {Math.round(p.dist)} m {p.speaking ? "· hablando" : ""}
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
