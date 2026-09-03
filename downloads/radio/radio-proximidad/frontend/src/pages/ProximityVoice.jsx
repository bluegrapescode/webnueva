import React, { useState, useEffect, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Radio, Mic, MicOff, PhoneOff, Power, Users, Volume2, VolumeX, Signal, Plus, Minus, Keyboard, Waves, Activity, Star, Ban, Search, History as HistoryIcon, Play, Loader2, ShieldOff } from "lucide-react";
import { useSound } from "@/context/SoundContext";
import { useProximitySim, useMicLevel } from "@/lib/proximitySim";

/* ───────────────────────── tactical comms tokens ───────────────────────── */
const SHELL = { background: "linear-gradient(180deg,#1C2016 0%,#11140D 100%)", boxShadow: "inset 0 1px 0 rgba(255,255,255,.06), inset 0 0 0 1px rgba(124,168,66,.10), 0 30px 70px rgba(0,0,0,.6)" };
const PLATE = { background: "radial-gradient(120% 100% at 50% 0%, #0D1207 0%, #070A05 100%)", border: "1px solid rgba(124,168,66,.30)", boxShadow: "inset 0 0 42px rgba(124,168,66,.10), inset 0 1px 0 rgba(163,201,107,.10)" };
const SUBPLATE = { background: "rgba(124,168,66,.045)", border: "1px solid rgba(124,168,66,.14)", boxShadow: "inset 0 1px 0 rgba(255,255,255,.03)" };
const KEYCAP_LIVE = { background: "linear-gradient(180deg,#5A6B3C,#2A3410)", boxShadow: "inset 0 2px 0 rgba(255,255,255,.16), inset 0 0 26px rgba(240,180,41,.20), 0 3px 0 #10130A" };
const KEYCAP_IDLE = { background: "linear-gradient(180deg,#3A4030,#20240F)", boxShadow: "inset 0 2px 0 rgba(255,255,255,.10), 0 7px 0 #10130A" };
const LCD_GLOW = { textShadow: "0 0 12px rgba(163,201,107,.45)" };

const VU_SEGMENTS = 16;
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
  return Math.max(1, Math.round(Math.pow(frac, 1 / exponent) * SIGNAL_BARS));
}

/* ── multi-segment LED VU meter (real mic RMS) ── */
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
  const WARN = VU_SEGMENTS - 5, HOT = VU_SEGMENTS - 2;
  return (
    <div className="flex gap-[3px]" data-testid="voice-mic-meter" data-lit={lit}>
      {Array.from({ length: VU_SEGMENTS }, (_, i) => {
        const on = i < lit;
        const color = i >= HOT ? "#E24A4A" : i >= WARN ? "#F0B429" : "#A3C96B";
        return <span key={i} className="flex-1 h-[13px] rounded-[1px] transition-colors duration-75"
          style={{ background: on ? color : "rgba(163,201,107,.10)", boxShadow: on ? `0 0 7px ${color}aa` : "none" }} />;
      })}
    </div>
  );
}

function SignalMeter({ bars, danger }) {
  return (
    <span className="flex items-end gap-[2.5px] h-4 shrink-0" data-testid="voice-signal" data-bars={bars}>
      {Array.from({ length: SIGNAL_BARS }, (_, i) => (
        <span key={i} className="w-1 rounded-sm transition-colors"
          style={{ height: 5 + i * 3.7, background: i < bars ? (danger ? "#E24A4A" : "#34d399") : "rgba(255,255,255,.15)" }} />
      ))}
    </span>
  );
}

/* ── precision rotary dial ── */
function Dial({ label, value, min, max, step, display, onChange, accent = "#A3C96B", testid }) {
  const frac = Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
  const R = 30, C = 2 * Math.PI * R, SWEEP = 0.75, angle = -135 + 270 * frac;
  return (
    <div className="text-center rounded-xl px-2 py-3" style={SUBPLATE}>
      <svg width="78" height="78" viewBox="0 0 78 78" className="mx-auto block">
        <circle cx="39" cy="39" r={R} fill="none" stroke="rgba(255,255,255,.09)" strokeWidth="5" strokeLinecap="round" strokeDasharray={`${C * SWEEP} ${C}`} transform="rotate(135 39 39)" />
        <circle cx="39" cy="39" r={R} fill="none" stroke={accent} strokeWidth="5" strokeLinecap="round" strokeDasharray={`${C * SWEEP * frac} ${C}`} transform="rotate(135 39 39)" style={{ transition: "stroke-dasharray .2s ease", filter: `drop-shadow(0 0 4px ${accent}88)` }} />
        <circle cx="39" cy="39" r="19" fill="#12160C" stroke="rgba(255,255,255,.10)" />
        <circle cx="39" cy="39" r="19" fill="none" stroke="rgba(0,0,0,.5)" strokeWidth="2" transform="translate(0 1)" />
        <line x1="39" y1="39" x2="39" y2="23" stroke="#DCE7C4" strokeWidth="2.5" strokeLinecap="round" transform={`rotate(${angle} 39 39)`} style={{ transition: "transform .2s ease" }} />
      </svg>
      <span className="block text-[10px] font-extrabold tracking-widest uppercase mt-1.5" style={{ color: "#8C967A" }}>{label}</span>
      <span className="block text-sm font-extrabold tabular-nums font-mono" style={{ color: "#DCE7C4", ...LCD_GLOW }} data-testid={`${testid}-value`}>{display}</span>
      <input type="range" min={min} max={max} step={step} value={value} aria-label={label} onChange={(e) => onChange(Number(e.target.value))} data-testid={testid}
        className="w-full h-1 mt-2.5 rounded-full bg-white/10 accent-gold cursor-pointer" />
    </div>
  );
}

function StatCell({ label, value, accent = "#DCE7C4" }) {
  return (
    <div className="rounded-md px-1 py-1.5 text-center" style={SUBPLATE}>
      <p className="text-[8.5px] font-mono tracking-[0.15em] opacity-60" style={{ color: "#A3C96B" }}>{label}</p>
      <p className="text-lg font-extrabold tabular-nums font-mono leading-tight" style={{ color: accent, ...LCD_GLOW }}>{value}</p>
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
  const [preset, setPreset] = useState("");
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState("dist"); // dist | name
  const [selfSpeaking, setSelfSpeaking] = useState(false);

  const connected = sim.on;
  const micActive = connected && !micMuted && (micMode === "ptt" ? transmitting : true);
  const pttLabel = PTT_KEYS.find((k) => k.code === pttKey)?.label || "Espacio";

  // VAD: light up when the real mic level crosses a threshold while transmitting.
  useEffect(() => {
    if (!micActive) { setSelfSpeaking(false); return undefined; }
    let alive = true, raf = 0;
    const tick = () => { if (!alive) return; setSelfSpeaking((mic.getLevel() || 0) > 0.08); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => { alive = false; cancelAnimationFrame(raf); };
  }, [micActive, mic]);

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

  const applyPreset = (id) => {
    play("click"); setPreset(id);
    if (id === "manada") { sim.setHearing(60); setMaster(0.85); }
    else if (id === "explorar") { sim.setHearing(sim.serverRadius); setMaster(0.8); }
    else if (id === "sigilo") { sim.setHearing(100); setMaster(0.3); }
  };
  useEffect(() => { setPreset(""); }, [sim.hearing, master]); // any manual tweak clears the active preset badge

  const doTestMic = async () => { play("click"); await mic.testMic(); };

  const filterSort = (list) => {
    const q = query.trim().toLowerCase();
    let out = q ? list.filter((p) => p.name.toLowerCase().includes(q) || (p.dino || "").toLowerCase().includes(q)) : list;
    out = [...out].sort(sortBy === "name" ? (a, b) => a.name.localeCompare(b.name) : (a, b) => a.dist - b.dist);
    // favourites float to the top of the in-range list
    return out.sort((a, b) => (sim.isFavorite(b.name) ? 1 : 0) - (sim.isFavorite(a.name) ? 1 : 0));
  };
  const inRange = useMemo(() => filterSort(sim.players.filter((p) => p.dist <= sim.hearing)), [sim.players, sim.hearing, query, sortBy, sim.favorites]);
  const outRange = useMemo(() => filterSort(sim.players.filter((p) => p.dist > sim.hearing)), [sim.players, sim.hearing, query, sortBy, sim.favorites]);
  const speakingNow = useMemo(() => sim.players.filter((p) => p.dist <= sim.hearing && p.speaking && !p.muted).length, [sim.players, sim.hearing]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start max-w-7xl mx-auto px-4 sm:px-6 py-10">
      {/* ═══════════ header hero (full width) ═══════════ */}
      <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="lg:col-span-12 flex items-end justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <div className="relative h-14 w-14 rounded-2xl flex items-center justify-center shrink-0" style={{ background: "linear-gradient(180deg,#2A3418,#141a0c)", border: "1px solid rgba(124,168,66,.30)", boxShadow: "inset 0 0 20px rgba(124,168,66,.15)" }}>
            <Radio className="text-gold" size={26} />
            {connected && <span className="absolute -top-1 -right-1 h-3.5 w-3.5 rounded-full bg-emerald-400 border-2 border-[#11140D]" style={{ boxShadow: "0 0 10px #34d399" }} />}
          </div>
          <div>
            <p className="text-[11px] font-bold tracking-[0.2em] uppercase font-mono text-gold">Comunicación en el juego</p>
            <h1 className="font-display font-extrabold text-3xl sm:text-4xl lg:text-5xl tracking-tighter leading-none">Radio de Proximidad</h1>
            <p className="text-xs text-muted-foreground mt-1 font-mono">Canal de voz espacial en tiempo real · The Isle: Evrima LATAM</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          {connected && (
            <span className="inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl glass border border-emerald-500/25 text-emerald-400 text-xs font-bold font-mono" data-testid="voice-inrange-count">
              <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-70 animate-ping" /><span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" /></span>
              {inRange.length} EN RANGO{speakingNow > 0 ? ` · ${speakingNow} HABLANDO` : ""}
            </span>
          )}
          {connected ? (
            <button onClick={handleDisconnect} data-testid="voice-disconnect" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-crimson text-white font-bold text-sm hover:brightness-110 transition-all">
              <PhoneOff size={16} /> Apagar radio
            </button>
          ) : (
            <button onClick={handleConnect} data-testid="voice-connect" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gold text-background font-bold text-sm hover:brightness-110 hover:gold-glow transition-all">
              <Power size={16} /> Encender radio
            </button>
          )}
        </div>
      </motion.div>

      {/* ═══════════ left · transceiver console ═══════════ */}
      <motion.div initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.05 }}
        className="lg:col-span-5 rounded-[24px] p-5 space-y-4" style={SHELL} data-testid="voice-panel">

        {/* LCD display deck */}
        <div className="rounded-2xl p-4 sm:p-[18px] transition-all" style={{ ...PLATE, ...(selfSpeaking ? { borderColor: "rgba(52,211,153,.6)", boxShadow: "inset 0 0 42px rgba(52,211,153,.16), 0 0 22px rgba(52,211,153,.28)" } : {}) }} data-testid="voice-vad" data-active={selfSpeaking}>
          <div className="flex items-start justify-between gap-3">
            <div className="font-mono min-w-0" style={LCD_GLOW}>
              <p className="text-[10px] tracking-[0.20em] opacity-70" style={{ color: "#A3C96B" }}>CANAL DE PROXIMIDAD</p>
              <p className="text-2xl sm:text-[30px] font-extrabold leading-tight truncate" style={{ color: connected ? "#A3C96B" : "#7C8590" }}>{connected ? "EN LÍNEA" : "FUERA DE LÍNEA"}</p>
            </div>
            <span className="inline-flex items-center gap-1.5 shrink-0 px-2 py-1 rounded-md font-mono text-[10px] font-bold"
              style={{ background: connected ? "rgba(52,211,153,.12)" : "rgba(255,255,255,.05)", border: `1px solid ${connected ? "rgba(52,211,153,.3)" : "rgba(255,255,255,.1)"}`, color: connected ? "#34d399" : "#8C967A" }}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: connected ? "#34d399" : "#8C967A", boxShadow: connected ? "0 0 6px #34d399" : "none" }} /> {connected ? "RX/TX" : "STANDBY"}
            </span>
          </div>

          {/* telemetry grid */}
          <div className="grid grid-cols-4 gap-1.5 mt-3.5">
            <StatCell label="ALCANCE" value={`${sim.hearing}`} accent="#F0B429" />
            <StatCell label="EN CANAL" value={<span data-testid="voice-participant-count">{sim.players.length}</span>} />
            <StatCell label="EN RANGO" value={connected ? inRange.length : "—"} accent="#A3C96B" />
            <StatCell label="HABLANDO" value={connected ? speakingNow : "—"} accent="#F0B429" />
          </div>

          {/* VU meter */}
          <div className="mt-3.5">
            <VuMeter getLevel={mic.getLevel} active={micActive} />
            <div className="flex justify-between mt-1.5 font-mono text-[10px] opacity-70" style={{ color: "#A3C96B" }}>
              <span className="inline-flex items-center gap-1"><Activity size={10} /> NIVEL DE MICRÓFONO</span>
              <span>{micMuted ? "SILENCIADO" : micActive ? (mic.granted ? "ABIERTO" : "SIN PERMISO") : "EN ESPERA"}</span>
            </div>
          </div>
        </div>

        {/* mic mode selector */}
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 font-mono">Modo de micrófono</p>
          <div className="flex gap-2">
            <button onClick={() => { setMicMode("ptt"); setTransmitting(false); play("click"); }} data-testid="voice-mic-mode-ptt" className={`flex-1 inline-flex items-center justify-center gap-1.5 text-xs font-bold px-3 py-3 rounded-xl border transition-all ${micMode === "ptt" ? "bg-gold/15 text-gold border-gold/45" : "glass border-white/12 text-muted-foreground hover:text-foreground"}`}><Keyboard size={13} /> Pulsar para hablar</button>
            <button onClick={() => { setMicMode("open"); play("click"); }} data-testid="voice-mic-mode-open" className={`flex-1 inline-flex items-center justify-center gap-1.5 text-xs font-bold px-3 py-3 rounded-xl border transition-all ${micMode === "open" ? "bg-gold/15 text-gold border-gold/45" : "glass border-white/12 text-muted-foreground hover:text-foreground"}`}><Waves size={13} /> Micrófono abierto</button>
          </div>
        </div>

        {/* PTT key binding */}
        {micMode === "ptt" && (
          <div className="rounded-xl px-3 py-3" style={SUBPLATE} data-testid="voice-ptt-key-row">
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 inline-flex items-center gap-1.5 font-mono"><Keyboard size={12} /> Tecla para hablar</p>
            <div className="flex gap-1.5">
              {PTT_KEYS.map((k) => (
                <button key={k.code} onClick={() => { setPttKey(k.code); play("click"); }} data-testid={`voice-ptt-key-${k.code}`}
                  className={`flex-1 text-xs font-extrabold py-2 rounded-lg border transition-all ${pttKey === k.code ? "bg-gold/20 text-gold border-gold/50" : "border-white/10 text-muted-foreground hover:text-foreground"}`}
                  style={pttKey === k.code ? {} : KEYCAP_IDLE}>{k.label}</button>
              ))}
            </div>
          </div>
        )}

        {/* master talk / mute keycap */}
        {micMode === "ptt" ? (
          <button data-testid="voice-ptt-button"
            onMouseDown={() => connected && setTransmitting(true)} onMouseUp={() => setTransmitting(false)} onMouseLeave={() => setTransmitting(false)}
            onTouchStart={(e) => { e.preventDefault(); connected && setTransmitting(true); }} onTouchEnd={() => setTransmitting(false)}
            disabled={!connected || micMuted}
            className="w-full py-6 px-4 rounded-2xl text-center select-none disabled:opacity-60 disabled:cursor-default transition-all"
            style={{ ...(connected && transmitting && !micMuted ? KEYCAP_LIVE : KEYCAP_IDLE), border: `1px solid ${connected && transmitting && !micMuted ? "rgba(240,180,41,.5)" : "rgba(255,255,255,.08)"}` }}>
            <span className="flex items-center justify-center gap-2 text-lg font-extrabold tracking-wider" style={{ color: connected && transmitting && !micMuted ? "#F7E39B" : "#DCE7C4" }}>
              <Mic size={20} /> {micMuted ? "MIC SILENCIADO" : connected && transmitting ? "TRANSMITIENDO" : <>MANTÉN&nbsp; [ {pttLabel} ]</>}
            </span>
            <span className="block text-[11px] mt-0.5" style={{ color: "#8C967A" }}>
              {!connected ? "enciende la radio para hablar" : micMuted ? "reactiva el micrófono abajo" : transmitting ? "suelta para volver a escuchar" : `mantén pulsado o la tecla ${pttLabel}`}
            </span>
          </button>
        ) : (
          <button onClick={() => { setMicMuted((m) => !m); play("click"); }} disabled={!connected} data-testid="voice-mute-toggle"
            className="w-full py-6 px-4 rounded-2xl text-center transition-all disabled:opacity-60"
            style={{ ...(connected && !micMuted ? KEYCAP_LIVE : KEYCAP_IDLE), border: `1px solid ${connected && !micMuted ? "rgba(240,180,41,.5)" : "rgba(255,255,255,.08)"}` }}>
            <span className="flex items-center justify-center gap-2 text-lg font-extrabold tracking-wider" style={{ color: micMuted ? "#E9A" : connected ? "#F7E39B" : "#DCE7C4" }}>
              {micMuted ? <MicOff size={20} /> : <Mic size={20} />} {micMuted ? "MICRÓFONO SILENCIADO" : "MICRÓFONO ABIERTO"}
            </span>
            <span className="block text-[11px] mt-0.5" style={{ color: "#8C967A" }}>{connected ? (micMuted ? "pulsa para volver a hablar" : "pulsa para silenciarte") : "enciende la radio para hablar"}</span>
          </button>
        )}

        {micMode === "ptt" && (
          <button onClick={() => { setMicMuted((m) => !m); play("click"); }} disabled={!connected} data-testid="voice-mic-mute-ptt"
            className={`w-full inline-flex items-center justify-center gap-2 text-xs font-bold px-3 py-2.5 rounded-xl border transition-all disabled:opacity-50 ${micMuted ? "bg-crimson/15 text-crimson border-crimson/30" : "glass border-white/12 text-muted-foreground hover:text-foreground"}`}>
            {micMuted ? <MicOff size={14} /> : <Mic size={14} />} {micMuted ? "Micrófono silenciado" : "Silenciar mi micrófono"}
          </button>
        )}

        {/* master output gain dock */}
        <div className="rounded-xl px-3.5 py-3.5" style={SUBPLATE} data-testid="voice-master-control">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground inline-flex items-center gap-1.5 font-mono"><Volume2 size={12} /> Volumen general</span>
            <span className="text-sm font-extrabold tabular-nums font-mono text-gold" style={LCD_GLOW} data-testid="voice-master-value">{Math.round(master * 100)}%</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => stepMaster(-0.05)} data-testid="voice-master-minus" aria-label="Bajar volumen" className="w-10 h-10 shrink-0 rounded-lg text-gold inline-flex items-center justify-center transition-all hover:brightness-125" style={KEYCAP_IDLE}><Minus size={16} /></button>
            <input type="range" min={0} max={100} step={1} value={Math.round(master * 100)} onChange={(e) => setMaster(Number(e.target.value) / 100)} aria-label="Volumen general" data-testid="voice-set-master"
              className="flex-1 h-2 rounded-full bg-white/10 accent-gold cursor-pointer" />
            <button onClick={() => stepMaster(0.05)} data-testid="voice-master-plus" aria-label="Subir volumen" className="w-10 h-10 shrink-0 rounded-lg text-gold inline-flex items-center justify-center transition-all hover:brightness-125" style={KEYCAP_IDLE}><Plus size={16} /></button>
          </div>
          <button onClick={toggleMuteAll} disabled={!connected} data-testid="voice-mute-all"
            className={`w-full mt-3 inline-flex items-center justify-center gap-2 text-xs font-bold px-3 py-2.5 rounded-lg border transition-all disabled:opacity-50 ${allMuted ? "bg-crimson/15 text-crimson border-crimson/35" : "border-white/10 text-muted-foreground hover:text-foreground"}`}>
            {allMuted ? <VolumeX size={14} /> : <Volume2 size={14} />} {allMuted ? "Todos silenciados — reactivar" : "Silenciar a todos"}
          </button>
        </div>

        {/* spatial dials */}
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 font-mono">Audio espacial</p>
          <div className="grid grid-cols-2 gap-3">
            <Dial label="Nitidez" value={exponent} min={0.6} max={3} step={0.1} display={exponent.toFixed(1)} onChange={setExponent} testid="voice-set-exponent" />
            <Dial label="Alcance" accent="#F0B429" value={sim.hearing} min={20} max={sim.serverRadius} step={5} display={`${sim.hearing} m`} onChange={sim.setHearing} testid="voice-set-hearing" />
          </div>
          <p className="text-[11px] mt-3 leading-relaxed" style={{ color: "#7E8672" }}>
            <b style={{ color: "#F0B429" }}>Alcance</b> define hasta dónde oyes; <b style={{ color: "#A3C96B" }}>Nitidez</b> ajusta cómo cae el volumen con la distancia. Baja el alcance y los jugadores lejanos salen de rango en vivo.
          </p>
        </div>

        {/* quick presets */}
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 font-mono">Presets rápidos</p>
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: "manada", label: "Manada", sub: "rango corto" },
              { id: "explorar", label: "Explorar", sub: "rango largo" },
              { id: "sigilo", label: "Sigilo", sub: "volumen bajo" },
            ].map((pr) => (
              <button key={pr.id} onClick={() => applyPreset(pr.id)} data-testid={`voice-preset-${pr.id}`}
                className={`rounded-xl px-2 py-2.5 text-center border transition-all ${preset === pr.id ? "bg-gold/15 border-gold/50 text-gold" : "glass border-white/12 text-muted-foreground hover:text-foreground"}`}>
                <span className="block text-xs font-extrabold">{pr.label}</span>
                <span className="block text-[9px] opacity-70 font-mono">{pr.sub}</span>
              </button>
            ))}
          </div>
        </div>

        {/* audio devices + noise suppression + mic test */}
        <div className="rounded-xl px-3.5 py-3.5 space-y-3" style={SUBPLATE} data-testid="voice-devices">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground inline-flex items-center gap-1.5 font-mono"><Activity size={12} /> Dispositivos de audio</p>
          <label className="block">
            <span className="text-[10px] font-mono opacity-70" style={{ color: "#A3C96B" }}>Micrófono</span>
            <select value={mic.inputId} onChange={(e) => mic.changeInput(e.target.value)} onFocus={mic.listDevices} data-testid="voice-input-device"
              className="mt-1 w-full text-xs rounded-lg bg-black/40 border border-white/12 px-2.5 py-2 outline-none focus:border-gold/50 text-foreground">
              <option value="">Predeterminado del sistema</option>
              {mic.devices.inputs.map((d) => <option key={d.deviceId} value={d.deviceId}>{d.label}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] font-mono opacity-70" style={{ color: "#A3C96B" }}>Altavoz</span>
            <select value={mic.outputId} onChange={(e) => mic.changeOutput(e.target.value)} onFocus={mic.listDevices} data-testid="voice-output-device"
              className="mt-1 w-full text-xs rounded-lg bg-black/40 border border-white/12 px-2.5 py-2 outline-none focus:border-gold/50 text-foreground">
              <option value="">Predeterminado del sistema</option>
              {mic.devices.outputs.map((d) => <option key={d.deviceId} value={d.deviceId}>{d.label}</option>)}
            </select>
          </label>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[11px] font-semibold inline-flex items-center gap-1.5"><Waves size={13} className="text-muted-foreground" /> Supresión de ruido</span>
            <button onClick={() => { mic.setNoiseSuppression(!mic.noiseSuppression); play("click"); }} data-testid="voice-noise-suppression" role="switch" aria-checked={mic.noiseSuppression}
              className={`relative h-6 w-11 rounded-full transition-colors ${mic.noiseSuppression ? "bg-emerald-500/70" : "bg-white/15"}`}>
              <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${mic.noiseSuppression ? "left-[22px]" : "left-0.5"}`} />
            </button>
          </div>
          <button onClick={doTestMic} disabled={!!mic.testing} data-testid="voice-test-mic"
            className="w-full inline-flex items-center justify-center gap-2 text-xs font-bold px-3 py-2.5 rounded-lg border border-white/12 glass text-foreground hover:border-gold/40 transition-all disabled:opacity-70">
            {mic.testing === "rec" ? <><Loader2 size={14} className="animate-spin" /> Grabando 3s…</> : mic.testing === "play" ? <><Loader2 size={14} className="animate-spin" /> Reproduciendo…</> : <><Play size={14} /> Probar micrófono</>}
          </button>
          <p className="text-[10px] leading-relaxed" style={{ color: "#7E8672" }}>Graba 3 segundos y te los reproduce para confirmar que se te escucha.</p>
        </div>
      </motion.div>

      {/* ═══════════ right · spatial roster ═══════════ */}
      <motion.div initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.1 }} className="lg:col-span-7 space-y-5">
        <div className="glass rounded-2xl overflow-hidden" data-testid="voice-participants-list">
          <div className="px-4 py-4 border-b border-white/10" style={{ background: "rgba(124,168,66,.04)" }}>
            <div className="flex items-center justify-between gap-3">
              <p className="text-lg font-extrabold tracking-wide font-display inline-flex items-center gap-2"><Users size={17} className="text-gold" /> Canales cerca de ti</p>
              {connected && <span className="text-[10px] font-bold uppercase tracking-wide px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 font-mono">{inRange.length} en rango · {outRange.length} fuera</span>}
            </div>
            {connected && (
              <div className="flex items-center gap-2 mt-3">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar jugador o dino…" data-testid="voice-search"
                    className="w-full pl-8 pr-3 py-2 rounded-lg bg-black/40 border border-white/12 text-sm outline-none focus:border-gold/50" />
                </div>
                <div className="flex rounded-lg overflow-hidden border border-white/12 shrink-0">
                  <button onClick={() => { setSortBy("dist"); play("click"); }} data-testid="voice-sort-dist" className={`text-[11px] font-bold px-3 py-2 transition-colors ${sortBy === "dist" ? "bg-gold/20 text-gold" : "text-muted-foreground hover:text-foreground"}`}>Cercanía</button>
                  <button onClick={() => { setSortBy("name"); play("click"); }} data-testid="voice-sort-name" className={`text-[11px] font-bold px-3 py-2 transition-colors ${sortBy === "name" ? "bg-gold/20 text-gold" : "text-muted-foreground hover:text-foreground"}`}>Nombre</button>
                </div>
              </div>
            )}
          </div>

          {!connected ? (
            <div className="py-16 px-4 text-center">
              <div className="mx-auto h-14 w-14 rounded-2xl flex items-center justify-center mb-4" style={{ background: "rgba(124,168,66,.06)", border: "1px solid rgba(124,168,66,.15)" }}><Radio size={24} className="text-muted-foreground" /></div>
              <p className="text-sm text-muted-foreground max-w-xs mx-auto">Enciende la radio para ver quién está cerca de ti en el juego y controlar a cada jugador.</p>
            </div>
          ) : (
            <div className="p-3 sm:p-4 space-y-2.5">
              <AnimatePresence initial={false}>
                {inRange.map((p) => {
                  const bars = signalBars(p.dist, sim.hearing, exponent);
                  const talking = p.speaking && !p.muted;
                  const fav = sim.isFavorite(p.name);
                  const blk = sim.isBlocked(p.name);
                  return (
                    <motion.div key={p.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 14 }} transition={{ duration: 0.22 }}
                      className="relative flex items-center gap-3 pl-4 pr-3 py-3 rounded-xl border overflow-hidden transition-colors"
                      style={{ background: talking ? "rgba(240,180,41,.07)" : fav ? "rgba(240,180,41,.04)" : "rgba(255,255,255,.02)", borderColor: talking ? "rgba(240,180,41,.35)" : fav ? "rgba(240,180,41,.22)" : "rgba(255,255,255,.08)" }}
                      data-testid={`voice-participant-${p.id}`} data-speaking={talking}>
                      <span className="absolute left-0 top-0 bottom-0 w-1" style={{ background: blk ? "#E24A4A" : talking ? "#F0B429" : fav ? "#F0B429" : "#7CA842", boxShadow: talking ? "0 0 10px #F0B429" : "none" }} />
                      <SignalMeter bars={p.muted ? 0 : bars} danger={p.muted} />
                      <span className="flex-1 min-w-0">
                        <span className="flex items-center gap-2">
                          {fav && <Star size={12} className="text-gold shrink-0 fill-current" />}
                          <span className="block text-sm font-bold truncate" data-testid={`voice-persona-${p.id}`}>{p.name}</span>
                          {talking && <span className="relative flex h-2.5 w-2.5 shrink-0" data-testid={`voice-speaking-${p.id}`}><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-gold opacity-70" /><span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-gold" /></span>}
                          {blk && <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-crimson/15 text-crimson border border-crimson/25 shrink-0">bloqueado</span>}
                        </span>
                        <span className="block text-[10.5px] font-mono text-muted-foreground/80 truncate" data-testid={`voice-range-${p.id}`}>
                          {p.dino} · {Math.round(p.dist)} m {p.muted ? "· silenciado" : talking ? "· hablando" : ""}
                        </span>
                      </span>
                      <span className="hidden sm:flex items-center gap-1.5 shrink-0">
                        <VolumeX size={12} className="text-muted-foreground/50" />
                        <input type="range" min={0} max={100} step={1} value={Math.round(p.vol * 100)} disabled={p.muted} onChange={(e) => sim.setVol(p.id, Number(e.target.value) / 100)}
                          aria-label={`Volumen de ${p.name}`} data-testid={`voice-speaker-vol-${p.id}`}
                          className="w-20 md:w-28 h-1.5 rounded-full bg-white/10 accent-emerald-400 cursor-pointer disabled:opacity-40" />
                      </span>
                      <button onClick={() => { sim.toggleFavorite(p.name); play("click"); }} data-testid={`voice-fav-${p.id}`} aria-label={fav ? "Quitar de favoritos" : "Marcar favorito"}
                        className={`inline-flex items-center justify-center h-9 w-9 shrink-0 rounded-lg border transition-all ${fav ? "bg-gold/15 text-gold border-gold/40" : "glass border-white/12 text-muted-foreground hover:text-foreground"}`}>
                        <Star size={15} className={fav ? "fill-current" : ""} />
                      </button>
                      <button onClick={() => { sim.toggleBlock(p.name); play("click"); }} data-testid={`voice-block-${p.id}`} aria-label={blk ? "Desbloquear" : "Bloquear"}
                        className={`inline-flex items-center justify-center h-9 w-9 shrink-0 rounded-lg border transition-all ${blk ? "bg-crimson/20 text-crimson border-crimson/40" : "glass border-white/12 text-muted-foreground hover:text-crimson"}`}>
                        {blk ? <ShieldOff size={15} /> : <Ban size={15} />}
                      </button>
                      <button onClick={() => sim.toggleMute(p.id)} data-testid={`voice-speaker-mute-${p.id}`} aria-label={p.muted ? "Reactivar" : "Silenciar"}
                        className={`inline-flex items-center justify-center h-9 w-9 shrink-0 rounded-lg border transition-all ${p.muted ? "bg-crimson/15 text-crimson border-crimson/30" : "glass border-white/12 text-muted-foreground hover:text-foreground"}`}>
                        {p.muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
                      </button>
                    </motion.div>
                  );
                })}
              </AnimatePresence>

              {inRange.length === 0 && (
                <p className="text-sm text-muted-foreground py-8 px-4 text-center">Nadie en rango. Sube el <b className="text-gold">Alcance</b> o espera a que alguien se acerque.</p>
              )}

              {outRange.length > 0 && (
                <div className="pt-2">
                  <p className="px-1 pb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60 inline-flex items-center gap-1.5 font-mono"><Signal size={11} /> Fuera de rango</p>
                  <div className="space-y-1.5">
                    {outRange.map((p) => (
                      <div key={p.id} className="flex items-center gap-3.5 px-4 py-2.5 rounded-lg opacity-45" style={{ background: "rgba(255,255,255,.015)" }} data-testid={`voice-participant-${p.id}`}>
                        <SignalMeter bars={0} />
                        <span className="flex-1 min-w-0">
                          <span className="block text-sm font-semibold truncate">{p.name}</span>
                          <span className="block text-[10.5px] font-mono text-muted-foreground/70 truncate" data-testid={`voice-range-${p.id}`}>{p.dino} · {Math.round(p.dist)} m · fuera de alcance</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* talk history */}
        {connected && (
          <div className="glass rounded-2xl overflow-hidden" data-testid="voice-history">
            <div className="flex items-center justify-between gap-3 px-4 py-3.5 border-b border-white/10" style={{ background: "rgba(124,168,66,.04)" }}>
              <p className="text-sm font-extrabold tracking-wide font-display inline-flex items-center gap-2"><HistoryIcon size={15} className="text-gold" /> Últimos en hablar</p>
            </div>
            {sim.history.length === 0 ? (
              <p className="text-xs text-muted-foreground py-6 px-4 text-center">Aún nadie ha hablado cerca de ti. Cuando alguien transmita en rango aparecerá aquí.</p>
            ) : (
              <div className="p-2 space-y-1">
                {sim.history.map((h, i) => (
                  <div key={`${h.name}-${h.at}`} className="flex items-center gap-3 px-3 py-2 rounded-lg" style={{ background: i === 0 ? "rgba(240,180,41,.05)" : "transparent" }} data-testid={`voice-history-${i}`}>
                    <span className="h-7 w-7 rounded-full flex items-center justify-center shrink-0" style={{ background: "rgba(124,168,66,.12)", border: "1px solid rgba(124,168,66,.2)" }}><Mic size={12} className="text-gold" /></span>
                    <span className="flex-1 min-w-0">
                      <span className="block text-xs font-bold truncate">{h.name}</span>
                      <span className="block text-[10px] font-mono text-muted-foreground/70 truncate">{h.dino}</span>
                    </span>
                    <span className="text-[10px] font-mono text-muted-foreground/60 shrink-0">{new Date(h.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </motion.div>
    </div>
  );
}
