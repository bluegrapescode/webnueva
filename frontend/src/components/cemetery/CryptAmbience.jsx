import { useEffect } from "react";

// Subtle procedural crypt ambience (wind + low drone) via Web Audio API — no
// audio asset needed. Renders nothing; controlled by `enabled`.
export default function CryptAmbience({ enabled }) {
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    const stops = [];

    // Brownish noise buffer (looped) -> lowpass -> wind gain
    const dur = 2.2, sr = ctx.sampleRate;
    const buf = ctx.createBuffer(1, Math.floor(sr * dur), sr);
    const data = buf.getChannelData(0);
    let last = 0;
    for (let i = 0; i < data.length; i++) {
      const white = Math.random() * 2 - 1;
      last = (last + 0.02 * white) / 1.02;
      data[i] = last * 3.2;
    }
    const src = ctx.createBufferSource();
    src.buffer = buf; src.loop = true;
    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass"; lp.frequency.value = 500; lp.Q.value = 0.7;
    const windGain = ctx.createGain(); windGain.gain.value = 0.05;
    src.connect(lp).connect(windGain);

    // slow gusts
    const lfo = ctx.createOscillator(); lfo.frequency.value = 0.08;
    const lfoGain = ctx.createGain(); lfoGain.gain.value = 0.035;
    lfo.connect(lfoGain).connect(windGain.gain);

    // low crypt drone
    const drone = ctx.createOscillator(); drone.type = "sine"; drone.frequency.value = 52;
    const droneGain = ctx.createGain(); droneGain.gain.value = 0.016;
    drone.connect(droneGain);

    const master = ctx.createGain(); master.gain.value = 0.0001;
    windGain.connect(master); droneGain.connect(master); master.connect(ctx.destination);

    src.start(); lfo.start(); drone.start();
    stops.push(src, lfo, drone);
    try { master.gain.exponentialRampToValueAtTime(0.9, ctx.currentTime + 2.5); } catch (e) {}

    const resume = () => { if (ctx.state === "suspended") ctx.resume(); };
    resume();
    const gesture = () => resume();
    window.addEventListener("pointerdown", gesture, { once: true });

    return () => {
      window.removeEventListener("pointerdown", gesture);
      try {
        master.gain.cancelScheduledValues(ctx.currentTime);
        master.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.4);
      } catch (e) {}
      setTimeout(() => {
        stops.forEach((n) => { try { n.stop(); } catch (e) {} });
        try { ctx.close(); } catch (e) {}
      }, 500);
    };
  }, [enabled]);
  return null;
}
