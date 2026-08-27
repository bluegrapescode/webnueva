import { useEffect } from "react";

// Procedural Halloween / crypt-graveyard ambience via Web Audio API — no asset.
// Renders nothing; controlled by `enabled`. Designed to sound eerie and
// atmospheric (dark drone + intermittent wind gusts + a distant graveyard
// bell), NOT like a constant fan. Levels are kept low and summed well below
// clipping so it never turns into a harsh buzz.
export default function CryptAmbience({ enabled }) {
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    const stops = [];
    const timers = [];

    // ---- Master (quiet, slow fade in) ----
    const master = ctx.createGain();
    master.gain.value = 0.0;
    master.connect(ctx.destination);
    const now0 = ctx.currentTime;
    master.gain.setValueAtTime(0.0, now0);
    master.gain.linearRampToValueAtTime(0.6, now0 + 4);

    // ---- 1) Dark ominous drone: two very low detuned sines (slow beating)
    //         + a hollow fifth for tension ----
    const droneBus = ctx.createGain();
    droneBus.gain.value = 0.14;
    droneBus.connect(master);
    [
      { f: 55, g: 1.0, type: "sine" },
      { f: 55.35, g: 0.9, type: "sine" }, // slight detune -> slow, uneasy beating
      { f: 82.4, g: 0.35, type: "sine" }, // bare fifth -> hollow, tense
      { f: 41.2, g: 0.4, type: "sine" }, // sub octave for weight
    ].forEach(({ f, g, type }) => {
      const o = ctx.createOscillator();
      o.type = type;
      o.frequency.value = f;
      const og = ctx.createGain();
      og.gain.value = g;
      o.connect(og).connect(droneBus);
      o.start();
      stops.push(o);
    });

    // Slow shimmer on the drone (LFO opening/closing a lowpass) for movement
    const droneLp = ctx.createBiquadFilter();
    droneLp.type = "lowpass";
    droneLp.frequency.value = 220;
    droneLp.Q.value = 0.6;
    // Re-route drone through the moving filter
    droneBus.disconnect();
    droneBus.connect(droneLp).connect(master);
    const shimmerLfo = ctx.createOscillator();
    shimmerLfo.frequency.value = 0.05;
    const shimmerDepth = ctx.createGain();
    shimmerDepth.gain.value = 90; // 130..310 Hz
    shimmerLfo.connect(shimmerDepth).connect(droneLp.frequency);
    shimmerLfo.start();
    stops.push(shimmerLfo);

    // ---- 2) Dissonant high tension pad (minor 2nd), extremely faint ----
    const padBus = ctx.createGain();
    padBus.gain.value = 0.018;
    padBus.connect(master);
    [233.0, 246.9].forEach((f) => {
      const o = ctx.createOscillator();
      o.type = "sine";
      o.frequency.value = f;
      o.connect(padBus);
      o.start();
      stops.push(o);
    });

    // ---- 3) Intermittent wind gusts (band-limited noise breathing in/out) ----
    const dur = 4,
      sr = ctx.sampleRate;
    const buf = ctx.createBuffer(1, Math.floor(sr * dur), sr);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * 0.5;
    const noise = ctx.createBufferSource();
    noise.buffer = buf;
    noise.loop = true;
    const windBp = ctx.createBiquadFilter();
    windBp.type = "bandpass";
    windBp.frequency.value = 520;
    windBp.Q.value = 0.9;
    const windGain = ctx.createGain();
    windGain.gain.value = 0.0; // driven by gust LFO -> gusts, not constant
    noise.connect(windBp).connect(windGain).connect(master);
    // Gust envelope: slow LFO that dips near silence between swells
    const gustLfo = ctx.createOscillator();
    gustLfo.frequency.value = 0.07;
    const gustDepth = ctx.createGain();
    gustDepth.gain.value = 0.11;
    const gustBias = ctx.createConstantSource();
    gustBias.offset.value = 0.05; // gust range roughly -0.06..0.16 -> gentle swells
    gustLfo.connect(gustDepth).connect(windGain.gain);
    gustBias.connect(windGain.gain);
    // Sweep the wind band for a whistling gust feel
    const windSweep = ctx.createOscillator();
    windSweep.frequency.value = 0.04;
    const windSweepDepth = ctx.createGain();
    windSweepDepth.gain.value = 260; // 260..780 Hz
    windSweep.connect(windSweepDepth).connect(windBp.frequency);
    noise.start();
    gustLfo.start();
    gustBias.start();
    windSweep.start();
    stops.push(noise, gustLfo, gustBias, windSweep);

    // ---- 4) Distant graveyard bell toll at random long intervals ----
    const tollBell = () => {
      const t = ctx.currentTime;
      const bellBus = ctx.createGain();
      bellBus.gain.value = 1;
      bellBus.connect(master);
      // Inharmonic partials -> metallic, church-bell-like
      [
        { f: 174.6, g: 0.09 },
        { f: 349.2, g: 0.05 },
        { f: 466.2, g: 0.03 },
        { f: 622.0, g: 0.02 },
      ].forEach(({ f, g }) => {
        const o = ctx.createOscillator();
        o.type = "sine";
        o.frequency.value = f;
        const og = ctx.createGain();
        og.gain.setValueAtTime(0.0001, t);
        og.gain.exponentialRampToValueAtTime(g, t + 0.02);
        og.gain.exponentialRampToValueAtTime(0.0001, t + 5.5);
        o.connect(og).connect(bellBus);
        o.start(t);
        o.stop(t + 6);
      });
      // schedule next toll (long, irregular gaps)
      const next = 16000 + Math.random() * 26000;
      timers.push(setTimeout(tollBell, next));
    };
    // first toll after a short suspense delay
    timers.push(setTimeout(tollBell, 6000 + Math.random() * 6000));

    const resume = () => {
      if (ctx.state === "suspended") ctx.resume();
    };
    resume();
    const gesture = () => resume();
    window.addEventListener("pointerdown", gesture, { once: true });

    return () => {
      window.removeEventListener("pointerdown", gesture);
      timers.forEach((id) => clearTimeout(id));
      try {
        const t = ctx.currentTime;
        master.gain.cancelScheduledValues(t);
        master.gain.setValueAtTime(master.gain.value, t);
        master.gain.linearRampToValueAtTime(0, t + 0.5);
      } catch (e) {}
      setTimeout(() => {
        stops.forEach((n) => {
          try {
            n.stop();
          } catch (e) {}
        });
        try {
          ctx.close();
        } catch (e) {}
      }, 600);
    };
  }, [enabled]);
  return null;
}
