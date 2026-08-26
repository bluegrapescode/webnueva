import React, { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Radio, Mic, MicOff, PhoneOff, Phone, Users, Loader2, Volume2, VolumeX, SlidersHorizontal, RotateCcw, Keyboard, Headphones } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useVoice } from "@/context/VoiceContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { hearingSliderModel } from "@/lib/voiceSettings";
import { signalBars, rangeCaption, vuSegments, dialFraction, SIGNAL_BARS, VU_SEGMENTS, VU_HOT_FROM } from "@/lib/voiceRoster";

// Radio chrome. Kept as inline style objects rather than Tailwind arbitrary
// values: these are one-off device gradients, and a bare arbitrary class in a
// comment or a test name is enough to move the CSS bundle hash on a JS-only
// change (see the note in tailwind.config.js).
const SHELL = {
  background: "linear-gradient(180deg,#24261F,#15170F)",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,.07), 0 24px 60px rgba(0,0,0,.55)",
};
const PLATE = {
  background: "#0B0F08",
  border: "1px solid rgba(124,168,66,.30)",
  boxShadow: "inset 0 0 40px rgba(124,168,66,.10)",
};
const KEYCAP_LIVE = {
  background: "linear-gradient(180deg,#4C5A38,#28300F)",
  boxShadow: "inset 0 2px 0 rgba(255,255,255,.14), 0 3px 0 #12140A",
};
const KEYCAP_IDLE = {
  background: "linear-gradient(180deg,#3A4030,#20240F)",
  boxShadow: "inset 0 2px 0 rgba(255,255,255,.10), 0 6px 0 #12140A",
};
const LCD_GLOW = { textShadow: "0 0 10px rgba(124,168,66,.55)" };

const STATE_META = {
  idle: { label: "FUERA DE LÍNEA", color: "#7C8590", sub: "Enciende la radio para hablar con quien tengas cerca." },
  connecting: { label: "SINTONIZANDO…", color: "#38bdf8", sub: "Abriendo el canal de proximidad." },
  connected: { label: "EN LÍNEA", color: "#A3C96B", sub: null },
  // Kept short on purpose: the LCD line truncates, and "RECUPERANDO SEÑA…" is
  // what the longer wording actually rendered as at this width.
  reconnecting: { label: "RECUPERANDO…", color: "#f59e0b", sub: "Perdiste la señal. No cierres la pestaña: la radio vuelve sola." },
  error: { label: "SIN SEÑAL", color: "#E24A4A", sub: "La radio no pudo abrir el canal." },
};

const pct = (x) => `${Math.round((Number(x) || 0) * 100)}%`;

// KeyboardEvent.code -> a short friendly label for the PTT key.
function keyLabel(code) {
  if (!code) return "—";
  if (code === "Space") return "Espacio";
  if (code.startsWith("Key")) return code.slice(3);
  if (code.startsWith("Digit")) return code.slice(5);
  if (code.startsWith("Arrow")) return code.slice(5);
  if (code === "ControlLeft" || code === "ControlRight") return "Ctrl";
  if (code === "ShiftLeft" || code === "ShiftRight") return "Shift";
  if (code === "AltLeft" || code === "AltRight") return "Alt";
  return code;
}

/**
 * The radio's microphone VU meter. Self-contained rAF loop reading getLevel() so
 * it never re-renders the rest of the app, and it re-renders ITSELF only when
 * the lit-segment count actually changes — the level moves every frame, the
 * picture does not. Idle (and loop stopped) when the mic is not live.
 */
function VuMeter({ getLevel, active }) {
  const [lit, setLit] = useState(0);
  const litRef = useRef(0);
  const rafRef = useRef(0);
  useEffect(() => {
    if (!active) { litRef.current = 0; setLit(0); return undefined; }
    let alive = true;
    const tick = () => {
      if (!alive) return;
      let n = 0;
      try { n = vuSegments(getLevel(), true); } catch (e) { n = 0; }
      if (n !== litRef.current) { litRef.current = n; setLit(n); }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { alive = false; cancelAnimationFrame(rafRef.current); };
  }, [getLevel, active]);
  return (
    <div className="flex gap-[3px] mt-3.5" data-testid="voice-mic-meter" data-lit={lit}>
      {Array.from({ length: VU_SEGMENTS }, (_, i) => (
        <span key={i} className="flex-1 h-[15px] rounded-[2px]"
          style={{
            background: i < lit ? (i >= VU_HOT_FROM ? "#F0B429" : "#A3C96B") : "rgba(163,201,107,.12)",
            boxShadow: i < lit ? "0 0 8px rgba(124,168,66,.55)" : "none",
          }} />
      ))}
    </div>
  );
}

/** Signal-strength bars beside a player's name (0..SIGNAL_BARS lit). */
function SignalMeter({ bars }) {
  const n = Number(bars) || 0;
  return (
    <span className="flex items-end gap-[2.5px] h-4 shrink-0" data-testid="voice-signal" data-bars={n} aria-hidden="true">
      {Array.from({ length: SIGNAL_BARS }, (_, i) => (
        <span key={i} className={`w-1 rounded-sm ${i < n ? "bg-emerald-400" : "bg-white/15"}`}
          style={{ height: 5 + i * 3.7 }} />
      ))}
    </span>
  );
}

/**
 * A radio dial: a 270° gauge with a needle, plus the real <input type=range>
 * underneath it. The gauge is the picture; the slider is the control, so the
 * knob stays keyboard-reachable, screen-reader-labelled and testable exactly as
 * a plain slider — the look never costs the player an interaction.
 */
function Dial({ label, hint, value, min, max, step, display, onChange, disabled, testid }) {
  const frac = dialFraction(value, min, max);
  const R = 27;
  const C = 2 * Math.PI * R;
  const SWEEP = 0.75; // 270° of the circle
  const angle = -135 + 270 * frac;
  return (
    <div className="text-center">
      <svg width="70" height="70" viewBox="0 0 70 70" className="mx-auto block" aria-hidden="true">
        <circle cx="35" cy="35" r={R} fill="none" stroke="rgba(255,255,255,.10)" strokeWidth="5" strokeLinecap="round"
          strokeDasharray={`${C * SWEEP} ${C}`} transform="rotate(135 35 35)" />
        <circle cx="35" cy="35" r={R} fill="none" stroke={disabled ? "#4A5140" : "#A3C96B"} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={`${C * SWEEP * frac} ${C}`} transform="rotate(135 35 35)" />
        <circle cx="35" cy="35" r="17" fill="#1B1E14" stroke="rgba(255,255,255,.10)" />
        <line x1="35" y1="35" x2="35" y2="21" stroke={disabled ? "#6C7361" : "#DCE7C4"} strokeWidth="2.5" strokeLinecap="round"
          transform={`rotate(${angle} 35 35)`} />
      </svg>
      <span className="block text-[10px] font-extrabold tracking-widest uppercase mt-1.5" style={{ color: "#9AA487" }}>{label}</span>
      <span className="block text-xs font-extrabold tabular-nums" style={{ color: "#DCE7C4" }} data-testid={`${testid}-value`}>{display}</span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        aria-label={hint ? `${label} — ${hint}` : label}
        onChange={(e) => onChange(Number(e.target.value))}
        data-testid={testid}
        className="w-full h-1 mt-2 rounded-full bg-white/10 accent-gold cursor-pointer disabled:opacity-40 disabled:cursor-default" />
    </div>
  );
}

function DeviceSelect({ label, icon, value, devices, onChange, testid }) {
  return (
    <label className="block py-1.5">
      <span className="flex items-center gap-1.5 text-sm font-semibold mb-1">{icon} {label}</span>
      <select value={value || ""} onChange={(e) => onChange(e.target.value)} data-testid={testid}
        className="w-full text-sm rounded-lg bg-black/30 border border-white/15 px-2.5 py-2 text-foreground focus:border-gold/50 outline-none">
        <option value="">Predeterminado del sistema</option>
        {(devices || []).map((d, i) => (
          <option key={d.deviceId} value={d.deviceId}>{d.label || `Dispositivo ${i + 1}`}</option>
        ))}
      </select>
    </label>
  );
}

/**
 * Proximity voice — the radio panel. Pure display over the app-level voice
 * session (context/VoiceContext.jsx). The session itself survives navigating
 * anywhere on the site; this page renders its state as a handheld transceiver
 * (status plate, VU meter, push-to-talk key, three dials) and the players around
 * you as open channels, each with its own signal strength, distance and fader.
 *
 * Nothing on this page can make you hear a player the server did not route to
 * you, and the range dial can only ever SHORTEN your hearing. The distances are
 * the ones the bridge already reports to place voices in space — the panel only
 * draws them.
 */
export default function ProximityVoice() {
  const { user } = useAuth();
  const {
    connState, muted, participants, speakers, audioBlocked, notice, personaNames, distances,
    connect, disconnect, toggleMute, enableAudio,
    settings, serverRadiusM, setMaster, setExponent, setHearingM,
    setSpeakerVolume, toggleSpeakerMute, resetSettings,
    devices, transmitting, getMicLevel, refreshDevices,
    setMicMode, setPttKey, setNoiseSuppression, setInputDevice, setOutputDevice,
  } = useVoice();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [capturingKey, setCapturingKey] = useState(false);

  // Populate device labels when the advanced panel opens (labels need a session).
  useEffect(() => {
    if (showAdvanced) refreshDevices();
  }, [showAdvanced, refreshDevices]);

  // PTT key rebind: capture the next key press.
  useEffect(() => {
    if (!capturingKey) return undefined;
    const onKey = (e) => {
      e.preventDefault();
      if (e.code !== "Escape") setPttKey(e.code);
      setCapturingKey(false);
    };
    window.addEventListener("keydown", onKey, { once: true });
    return () => window.removeEventListener("keydown", onKey);
  }, [capturingKey, setPttKey]);

  if (!user) return <div className="max-w-4xl mx-auto px-6 py-14"><SignInPrompt title="Radio de Proximidad" sub="Inicia sesión para hablar por voz con los jugadores cercanos en el juego." /></div>;

  const meta = STATE_META[connState] || STATE_META.idle;
  const connected = connState === "connected";
  const reconnecting = connState === "reconnecting";
  const live = connected || reconnecting;
  // Slider bounds/value/label all come from one tested helper, so this page stays
  // markup and the numbers a player sees are covered by real unit tests.
  const hearing = hearingSliderModel(settings, serverRadiusM);
  const ptt = settings.micMode === "ptt";
  const micActive = connected && (ptt ? transmitting : !muted);
  const dist = distances || {};
  const inRange = participants.filter((p) => p.audible).length;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-14">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
        className="mb-8 flex items-end justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Radio className="text-gold" size={26} />
          <div>
            <p className="label-overline text-xs text-gold">Comunicación en el juego</p>
            <h1 className="font-display font-extrabold text-4xl tracking-tighter">Radio de Proximidad</h1>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          {live && (
            <button onClick={() => setShowAdvanced((s) => !s)} data-testid="voice-settings-toggle"
              aria-label="Ajustes avanzados de voz"
              className={`inline-flex items-center gap-2 px-3 py-2.5 rounded-lg font-bold text-sm transition-all border ${showAdvanced ? "bg-gold/15 text-gold border-gold/40" : "glass border-white/15 text-foreground hover:border-gold/40"}`}>
              <SlidersHorizontal size={16} /> <span className="hidden sm:inline">Ajustes avanzados</span>
            </button>
          )}
          {live ? (
            <button onClick={() => disconnect()} data-testid="voice-disconnect"
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-crimson text-white font-bold text-sm hover:brightness-110 transition-all">
              {/* labelled at every width: an unlabelled red button that hangs up
                  the call is not a guess anyone should have to make */}
              <PhoneOff size={16} /> Apagar radio
            </button>
          ) : (
            <button onClick={connect} disabled={connState === "connecting"} data-testid="voice-connect"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gold text-background font-bold text-sm hover:brightness-110 transition-all disabled:opacity-60">
              {connState === "connecting" ? <Loader2 size={16} className="animate-spin" /> : <Phone size={16} />} Encender radio
            </button>
          )}
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-[420px_minmax(0,1fr)] gap-6 items-start">

        {/* ---------------------------- the handset ---------------------------- */}
        <div className="rounded-[22px] border border-white/10 p-5" style={SHELL} data-testid="voice-panel">
          <div className="rounded-xl p-4 sm:p-[18px]" style={PLATE} data-testid="voice-status-line">
            <div className="flex items-start justify-between gap-3">
              <div className="font-mono min-w-0" style={LCD_GLOW}>
                <p className="text-[10px] tracking-[0.20em] opacity-75" style={{ color: "#A3C96B" }}>CANAL DE PROXIMIDAD</p>
                <p className="text-2xl sm:text-[27px] font-bold leading-tight truncate" style={{ color: meta.color }}>{meta.label}</p>
                <p className="text-[11px] opacity-80" style={{ color: "#A3C96B" }}>
                  ALCANCE {hearing.max} m · {connected ? `${inRange} EN ESCUCHA` : "CANAL CERRADO"}
                </p>
              </div>
              <div className="text-right font-mono shrink-0" style={{ ...LCD_GLOW, color: "#A3C96B" }}>
                <p className="text-[10px] opacity-70">EN CANAL</p>
                <p className="text-xl font-bold tabular-nums" data-testid="voice-participant-count">{participants.length}</p>
              </div>
            </div>
            <VuMeter getLevel={getMicLevel} active={micActive} />
            <div className="flex justify-between mt-1.5 font-mono text-[10px] opacity-70" style={{ color: "#A3C96B" }}>
              <span>NIVEL DE MICRÓFONO</span>
              <span>{micActive ? "ABIERTO" : "SILENCIO"}</span>
            </div>
          </div>

          {/* The big key: push-to-talk in PTT mode, the mute switch in open mode.
              Which control shows follows the MODE, not the connection — the panel
              must not swap controls under the player the moment the radio comes
              up — and the lit style is reserved for a mic that is actually open,
              so an offline radio never looks like it is transmitting. */}
          {ptt ? (
            <div data-testid="voice-ptt-indicator"
              className="mt-[18px] w-full py-5 px-4 rounded-2xl border border-white/10 text-center"
              style={connected && transmitting ? KEYCAP_LIVE : KEYCAP_IDLE}>
              <span className="block text-lg font-extrabold tracking-wider" style={{ color: connected && transmitting ? "#DDF3B6" : "#DCE7C4" }}>
                {connected && transmitting ? "TRANSMITIENDO" : <>MANTÉN &nbsp;[ {keyLabel(settings.pttKey)} ]</>}
              </span>
              <span className="block text-[11px]" style={{ color: "#9AA487" }}>
                {!connected ? "enciende la radio para hablar"
                  : transmitting ? "suéltala para volver a escuchar" : "para hablar — suéltala para escuchar"}
              </span>
            </div>
          ) : (
            <button onClick={toggleMute} disabled={!connected} data-testid="voice-mute-toggle"
              className="mt-[18px] w-full py-5 px-4 rounded-2xl border border-white/10 text-center transition-all disabled:opacity-60 disabled:cursor-default"
              style={connected && !muted ? KEYCAP_LIVE : KEYCAP_IDLE}>
              <span className="flex items-center justify-center gap-2 text-lg font-extrabold tracking-wider"
                style={{ color: muted ? "#C99" : connected ? "#DDF3B6" : "#DCE7C4" }}>
                {muted ? <MicOff size={19} /> : <Mic size={19} />} {muted ? "MICRÓFONO SILENCIADO" : "MICRÓFONO ABIERTO"}
              </span>
              <span className="block text-[11px]" style={{ color: "#9AA487" }}>
                {connected ? (muted ? "pulsa para volver a hablar" : "pulsa para silenciarte") : "enciende la radio para hablar"}
              </span>
            </button>
          )}

          <div className="flex gap-2 mt-4" data-testid="voice-mic-mode">
            <button onClick={() => setMicMode("ptt")} data-testid="voice-mic-mode-ptt"
              className={`flex-1 text-xs font-bold px-3 py-2.5 rounded-lg border transition-all ${ptt ? "bg-gold/15 text-gold border-gold/40" : "glass border-white/15 text-muted-foreground hover:text-foreground"}`}>
              Pulsar para hablar
            </button>
            <button onClick={() => setMicMode("open")} data-testid="voice-mic-mode-open"
              className={`flex-1 text-xs font-bold px-3 py-2.5 rounded-lg border transition-all ${!ptt ? "bg-gold/15 text-gold border-gold/40" : "glass border-white/15 text-muted-foreground hover:text-foreground"}`}>
              Micrófono abierto
            </button>
          </div>

          <div className="grid grid-cols-3 gap-3 mt-[18px]">
            <Dial label="Volumen" hint="Qué tan fuerte se oye todo el chat de voz"
              value={Math.round((Number(settings.master) || 0) * 100)} min={0} max={100} step={1}
              display={pct(settings.master)} onChange={(v) => setMaster(v / 100)} testid="voice-set-master" />
            <Dial label="Nitidez" hint="Más alto = las voces lejanas se apagan antes"
              value={settings.exponent} min={0.6} max={3} step={0.1}
              display={(Number(settings.exponent) || 0).toFixed(1)} onChange={setExponent} testid="voice-set-exponent" />
            <Dial label="Alcance" hint={`Deja de oír a quienes estén más lejos. El servidor llega a ${hearing.max} m; puedes acortarlo, no ampliarlo`}
              value={hearing.value} min={hearing.min} max={hearing.max} step={1}
              display={hearing.display} onChange={(v) => setHearingM(hearing.toStore(v))} testid="voice-set-hearing" />
          </div>

          {live && showAdvanced && (
            <div className="mt-5 pt-4 border-t border-white/10" data-testid="voice-settings">
              <div className="flex items-center justify-between mb-2">
                <p className="label-overline text-[10px] text-gold inline-flex items-center gap-1.5"><SlidersHorizontal size={12} /> Ajustes avanzados</p>
                <button onClick={resetSettings} data-testid="voice-settings-reset"
                  className="inline-flex items-center gap-1.5 text-[11px] font-bold text-muted-foreground hover:text-foreground transition-colors">
                  <RotateCcw size={12} /> Restablecer
                </button>
              </div>

              {ptt && (
                <div className="flex items-center justify-between gap-3 mb-3 text-sm">
                  <span className="flex items-center gap-1.5"><Keyboard size={14} /> Tecla para hablar</span>
                  <button onClick={() => setCapturingKey(true)} data-testid="voice-ptt-rebind"
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all ${capturingKey ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/40 animate-pulse" : "glass border-white/15 hover:border-gold/40"}`}>
                    {capturingKey ? "Pulsa una tecla…" : <kbd className="font-mono">{keyLabel(settings.pttKey)}</kbd>}
                  </button>
                </div>
              )}

              <div className="flex items-center justify-between gap-3 py-1.5">
                <span className="text-sm font-semibold">Reducción de ruido</span>
                <button onClick={() => setNoiseSuppression(!settings.noiseSuppression)} data-testid="voice-noise-toggle"
                  role="switch" aria-checked={!!settings.noiseSuppression}
                  className={`relative h-6 w-11 rounded-full transition-colors ${settings.noiseSuppression ? "bg-emerald-500/70" : "bg-white/15"}`}>
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${settings.noiseSuppression ? "left-[22px]" : "left-0.5"}`} />
                </button>
              </div>

              <DeviceSelect label="Micrófono" icon={<Mic size={13} />} value={settings.inputDeviceId}
                devices={devices.inputs} onChange={setInputDevice} testid="voice-device-input" />
              <DeviceSelect label="Altavoz" icon={<Headphones size={13} />} value={settings.outputDeviceId}
                devices={devices.outputs} onChange={setOutputDevice} testid="voice-device-output" />
            </div>
          )}

          {meta.sub && <p className="text-[11px] mt-4 leading-relaxed" style={{ color: "#7E8672" }}>{meta.sub}</p>}
          {live && !showAdvanced && !meta.sub && (
            <p className="text-[11px] mt-4 leading-relaxed" style={{ color: "#7E8672" }}>
              Reducción de ruido {settings.noiseSuppression ? "activada" : "desactivada"} · la radio sigue encendida mientras navegas por el resto del sitio.
            </p>
          )}
        </div>

        {/* ---------------------------- the channels --------------------------- */}
        <div>
          {notice && (
            <p className="glass rounded-xl px-4 py-3 text-sm text-muted-foreground mb-4" data-testid="voice-notice">{notice}</p>
          )}

          {audioBlocked && connected && (
            <button onClick={enableAudio} data-testid="voice-audio-unlock"
              className="w-full mb-4 inline-flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-amber-500/15 text-amber-300 border border-amber-500/40 font-bold text-sm hover:bg-amber-500/25 transition-all">
              <Volume2 size={16} /> Activar audio — tu navegador bloqueó la reproducción, haz clic aquí para escuchar
            </button>
          )}

          <div className="glass rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between gap-3 px-4 py-3.5 border-b border-white/10">
              <p className="label-overline text-[10px] text-muted-foreground inline-flex items-center gap-1.5"><Users size={12} /> Canales abiertos cerca de ti</p>
              {connected && participants.length > 0 && (
                <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
                  {inRange} en rango · {participants.length - inRange} fuera
                </span>
              )}
            </div>

            {!connected ? (
              <p className="text-sm text-muted-foreground py-10 px-4 text-center">
                {reconnecting
                  ? "Recuperando la señal — no cierres la pestaña, volverás a estar en línea automáticamente."
                  : "Enciende la radio para ver quién está cerca de ti en el juego."}
              </p>
            ) : participants.length === 0 ? (
              <p className="text-sm text-muted-foreground py-10 px-4 text-center" data-testid="voice-participants-empty">
                Nadie más tiene la radio encendida todavía.
              </p>
            ) : (
              <div data-testid="voice-participants-list">
                {participants.map((p) => {
                  const speaking = p.audible && speakers.has(p.identity);
                  const spk = settings.speakers && settings.speakers[p.identity];
                  const spkMuted = !!(spk && spk.muted);
                  const spkVol = spk && Number.isFinite(Number(spk.volume)) ? Number(spk.volume) : 1;
                  const persona = personaNames && personaNames[p.identity];
                  const d = Object.prototype.hasOwnProperty.call(dist, p.identity) ? dist[p.identity] : null;
                  return (
                    <div key={p.identity} data-testid={`voice-participant-${p.identity}`}
                      className={`flex items-center gap-3.5 px-4 py-3.5 border-b border-white/10 last:border-b-0 ${p.audible ? "" : "opacity-50"}`}>
                      <SignalMeter bars={signalBars(d, serverRadiusM, p.audible)} />
                      <span className="flex-1 min-w-0">
                        <span className="flex items-center gap-2">
                          <span className="block text-sm font-semibold truncate" data-testid={`voice-persona-${p.identity}`}>{persona || p.identity}</span>
                          {speaking && <span className="relative flex h-2 w-2 shrink-0">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-70" />
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
                          </span>}
                        </span>
                        <span className="block text-[10.5px] font-mono text-muted-foreground/80 truncate" data-testid={`voice-range-${p.identity}`}>
                          {rangeCaption(d, serverRadiusM, { audible: p.audible, speaking })}
                        </span>
                        {persona && <span className="block text-[10px] font-mono text-muted-foreground/60 truncate select-all">{p.identity}</span>}
                      </span>
                      <input type="range" min={0} max={100} step={1} value={Math.round(spkVol * 100)} disabled={spkMuted}
                        onChange={(e) => setSpeakerVolume(p.identity, Number(e.target.value) / 100)}
                        aria-label={`Volumen de ${persona || p.identity}`}
                        data-testid={`voice-speaker-vol-${p.identity}`}
                        className="hidden sm:block w-24 md:w-32 h-1.5 rounded-full bg-white/10 accent-emerald-400 cursor-pointer disabled:opacity-40 shrink-0" />
                      <span className="hidden sm:block shrink-0 w-10 text-right text-[11px] font-bold tabular-nums text-muted-foreground">{spkMuted ? "—" : pct(spkVol)}</span>
                      <button onClick={() => toggleSpeakerMute(p.identity)} data-testid={`voice-speaker-mute-${p.identity}`}
                        aria-label={spkMuted ? "Reactivar jugador" : "Silenciar jugador"}
                        className={`inline-flex items-center justify-center h-8 w-8 shrink-0 rounded-lg border transition-all ${spkMuted ? "bg-crimson/15 text-crimson border-crimson/30" : "glass border-white/15 text-muted-foreground hover:text-foreground"}`}>
                        {spkMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
                      </button>
                    </div>
                  );
                })}
                {/* the per-player fader is hidden on phones, where the row has no
                    space for it; muting stays reachable everywhere */}
                <p className="sm:hidden text-[11px] text-muted-foreground/70 px-4 py-3">Gira el teléfono para ajustar el volumen de cada jugador.</p>
              </div>
            )}
          </div>

          <div className="glass rounded-2xl px-4 sm:px-5 py-4 mt-4">
            <p className="label-overline text-[10px] text-muted-foreground mb-2">Cómo funciona</p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              El servidor decide a quién puedes oír: solo los jugadores que estén físicamente cerca de ti dentro del juego,
              y su voz se apaga con la distancia. Las barras de señal junto a cada nombre son esa distancia real. Con los
              diales ajustas el volumen general, la nitidez con la que se apagan las voces lejanas y tu propio alcance de
              escucha — que solo puede acortar el del servidor, nunca ampliarlo — y con cada canal bajas o silencias a un
              jugador concreto. Puedes navegar por el resto del sitio o dejar la pestaña en segundo plano: la radio sigue
              encendida y se recupera sola tras cualquier corte.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
