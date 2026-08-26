import { useEffect, useRef, useState, useCallback } from "react";

// Server hearing radius, in metres, and the roster of players around you. This is
// a self-contained proximity simulation: each nearby player drifts (walks) around
// the map, and whether you can hear them is decided ONLY by their live distance
// vs. your hearing radius — so the Alcance dial genuinely changes who is in range.
export const SERVER_RADIUS_M = 300;

const A = ["Rex", "Draco", "Nyx", "Vortex", "Bruma", "Onyx", "Kira", "Loki", "Sombra", "Ember", "Furia", "Pyro", "Vega", "Colmillo", "Neon", "Trueno", "Ámbar", "Zafiro"];
const B = ["_MX", "_AR", "_CO", "_CL", "TV", "77", "_LATAM", "GG", "_prime", "_dino", "_ISLA", ""];
const SPECIES = ["Tyrannosaurus", "Carnotaurus", "Utahraptor", "Allosaurus", "Deinosuchus", "Dilophosaurus", "Maiasaura", "Stegosaurus", "Troodon"];
const rand = (arr) => arr[Math.floor(Math.random() * arr.length)];

function spawn(id) {
  return {
    id: `p${id}`,
    name: `${rand(A)}${rand(B)}`,
    dino: rand(SPECIES),
    angle: Math.random() * Math.PI * 2,
    dist: 30 + Math.random() * (SERVER_RADIUS_M * 1.15),
    // per-player motion: radial + angular velocity (metres/sec, rad/sec)
    vr: (Math.random() - 0.5) * 26,
    va: (Math.random() - 0.5) * 0.25,
    speaking: false,
    talkUntil: 0,
    vol: 1,
    muted: false,
  };
}

export function useProximitySim() {
  const [on, setOn] = useState(false);
  const [hearing, setHearing] = useState(150); // metres — the Alcance dial
  const [players, setPlayers] = useState([]);
  const [, force] = useState(0);
  const raf = useRef(0);
  const last = useRef(0);

  const connect = useCallback(() => {
    const n = 6 + Math.floor(Math.random() * 3); // 6–8 nearby
    setPlayers(Array.from({ length: n }, (_, i) => spawn(i + 1)));
    setOn(true);
  }, []);
  const disconnect = useCallback(() => { setOn(false); setPlayers([]); }, []);

  // Movement + speaking loop. Mutates in place through a ref-free setPlayers so
  // the radar animates smoothly; we throttle React commits to ~12 fps.
  useEffect(() => {
    if (!on) return undefined;
    let alive = true;
    const step = (t) => {
      if (!alive) return;
      const dt = last.current ? Math.min(0.1, (t - last.current) / 1000) : 0.016;
      last.current = t;
      setPlayers((prev) =>
        prev.map((p) => {
          let dist = p.dist + p.vr * dt;
          let vr = p.vr;
          if (dist < 10) { dist = 10; vr = Math.abs(vr); }
          if (dist > SERVER_RADIUS_M * 1.25) { dist = SERVER_RADIUS_M * 1.25; vr = -Math.abs(vr); }
          // occasional gentle change of direction so motion looks alive
          if (Math.random() < 0.01) vr = (Math.random() - 0.5) * 26;
          const angle = p.angle + p.va * dt;
          const inRange = dist <= hearing;
          let speaking = p.speaking;
          let talkUntil = p.talkUntil;
          if (inRange) {
            if (speaking && t > talkUntil) speaking = false;
            else if (!speaking && Math.random() < 0.006) { speaking = true; talkUntil = t + 1200 + Math.random() * 2600; }
          } else { speaking = false; }
          return { ...p, dist, vr, angle, speaking, talkUntil };
        })
      );
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    const commit = setInterval(() => force((x) => x + 1), 250);
    return () => { alive = false; cancelAnimationFrame(raf.current); clearInterval(commit); last.current = 0; };
  }, [on, hearing]);

  const setVol = useCallback((id, v) => setPlayers((p) => p.map((x) => (x.id === id ? { ...x, vol: v } : x))), []);
  const toggleMute = useCallback((id) => setPlayers((p) => p.map((x) => (x.id === id ? { ...x, muted: !x.muted } : x))), []);

  return { on, connect, disconnect, hearing, setHearing, players, setVol, toggleMute, serverRadius: SERVER_RADIUS_M };
}

// Real microphone level (0..1 RMS) via getUserMedia — makes the VU meter react
// to your actual voice. Returns a getLevel() and start/stop controls.
export function useMicLevel() {
  const ctxRef = useRef(null);
  const analyserRef = useRef(null);
  const streamRef = useRef(null);
  const dataRef = useRef(null);
  const [granted, setGranted] = useState(false);

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      streamRef.current = stream;
      const AC = window.AudioContext || window.webkitAudioContext;
      const ctx = new AC();
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      ctxRef.current = ctx;
      analyserRef.current = analyser;
      dataRef.current = new Uint8Array(analyser.frequencyBinCount);
      setGranted(true);
      return true;
    } catch (e) {
      setGranted(false);
      return false;
    }
  }, []);

  const stop = useCallback(() => {
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch (e) { /* noop */ }
    try { ctxRef.current?.close(); } catch (e) { /* noop */ }
    streamRef.current = null; ctxRef.current = null; analyserRef.current = null; setGranted(false);
  }, []);

  const getLevel = useCallback(() => {
    const a = analyserRef.current, d = dataRef.current;
    if (!a || !d) return 0;
    a.getByteTimeDomainData(d);
    let sum = 0;
    for (let i = 0; i < d.length; i++) { const x = (d[i] - 128) / 128; sum += x * x; }
    return Math.min(1, Math.sqrt(sum / d.length) * 2.4);
  }, []);

  useEffect(() => () => stop(), [stop]);
  return { start, stop, getLevel, granted };
}
