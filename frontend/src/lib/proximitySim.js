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

function spawn(id, favs, blocked) {
  const name = `${rand(A)}${rand(B)}`;
  return {
    id: `p${id}`,
    name,
    dino: rand(SPECIES),
    angle: Math.random() * Math.PI * 2,
    dist: 30 + Math.random() * (SERVER_RADIUS_M * 1.15),
    // per-player motion: radial + angular velocity (metres/sec, rad/sec)
    vr: (Math.random() - 0.5) * 26,
    va: (Math.random() - 0.5) * 0.25,
    speaking: false,
    talkUntil: 0,
    vol: favs.includes(name) ? 1 : 0.85,
    muted: blocked.includes(name), // blocked players start silenced
  };
}

const loadList = (key) => { try { return JSON.parse(localStorage.getItem(key) || "[]"); } catch { return []; } };
const saveList = (key, arr) => { try { localStorage.setItem(key, JSON.stringify(arr)); } catch { /* noop */ } };

export function useProximitySim() {
  const [on, setOn] = useState(false);
  const [hearing, setHearing] = useState(150); // metres — the Alcance dial
  const [players, setPlayers] = useState([]);
  const [favorites, setFavorites] = useState(() => loadList("prox_favs"));
  const [blocked, setBlocked] = useState(() => loadList("prox_blocked"));
  const [history, setHistory] = useState([]); // last speakers [{name, dino, at}]
  const favRef = useRef(favorites); favRef.current = favorites;
  const blockRef = useRef(blocked); blockRef.current = blocked;
  const [, force] = useState(0);
  const raf = useRef(0);
  const last = useRef(0);

  const connect = useCallback(() => {
    const n = 6 + Math.floor(Math.random() * 3); // 6–8 nearby
    setPlayers(Array.from({ length: n }, (_, i) => spawn(i + 1, favRef.current, blockRef.current)));
    setHistory([]);
    setOn(true);
  }, []);
  const disconnect = useCallback(() => { setOn(false); setPlayers([]); }, []);

  const isFavorite = useCallback((name) => favRef.current.includes(name), []);
  const isBlocked = useCallback((name) => blockRef.current.includes(name), []);
  const toggleFavorite = useCallback((name) => {
    setFavorites((prev) => {
      const next = prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name];
      saveList("prox_favs", next);
      // favouriting a live player boosts them to full volume immediately
      if (next.includes(name)) setPlayers((ps) => ps.map((p) => (p.name === name ? { ...p, vol: 1 } : p)));
      return next;
    });
  }, []);
  const toggleBlock = useCallback((name) => {
    setBlocked((prev) => {
      const next = prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name];
      saveList("prox_blocked", next);
      const nowBlocked = next.includes(name);
      setPlayers((ps) => ps.map((p) => (p.name === name ? { ...p, muted: nowBlocked } : p)));
      return next;
    });
  }, []);


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
          // record the moment a non-blocked player starts talking in range
          if (speaking && !p.speaking && !p.muted) {
            setHistory((h) => [{ name: p.name, dino: p.dino, at: Date.now() }, ...h.filter((x) => x.name !== p.name)].slice(0, 8));
          }
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
  const setAllMuted = useCallback((muted) => setPlayers((p) => p.map((x) => ({ ...x, muted }))), []);

  return {
    on, connect, disconnect, hearing, setHearing, players, setVol, toggleMute, setAllMuted,
    favorites, blocked, history, isFavorite, isBlocked, toggleFavorite, toggleBlock,
    serverRadius: SERVER_RADIUS_M,
  };
}

// Real microphone level (0..1 RMS) via getUserMedia — makes the VU meter react
// to your actual voice. Returns a getLevel() and start/stop controls.
export function useMicLevel() {
  const ctxRef = useRef(null);
  const analyserRef = useRef(null);
  const streamRef = useRef(null);
  const dataRef = useRef(null);
  const [granted, setGranted] = useState(false);
  const [devices, setDevices] = useState({ inputs: [], outputs: [] });
  const [inputId, setInputId] = useState("");
  const [outputId, setOutputId] = useState("");
  const [noiseSuppression, setNoiseSuppression] = useState(true);
  const [testing, setTesting] = useState(""); // "" | "rec" | "play"
  const nsRef = useRef(true); nsRef.current = noiseSuppression;
  const inRef = useRef(""); inRef.current = inputId;

  const listDevices = useCallback(async () => {
    try {
      const list = await navigator.mediaDevices.enumerateDevices();
      const map = (kind, fallback) => list.filter((d) => d.kind === kind && d.deviceId)
        .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `${fallback} ${i + 1}` }));
      setDevices({ inputs: map("audioinput", "Micrófono"), outputs: map("audiooutput", "Altavoz") });
    } catch (e) { /* enumeration blocked */ }
  }, []);

  const start = useCallback(async () => {
    try {
      const audio = { echoCancellation: true, noiseSuppression: nsRef.current };
      if (inRef.current) audio.deviceId = { exact: inRef.current };
      const stream = await navigator.mediaDevices.getUserMedia({ audio });
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
      listDevices(); // labels are available once permission is granted
      return true;
    } catch (e) {
      setGranted(false);
      return false;
    }
  }, [listDevices]);

  const stop = useCallback(() => {
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch (e) { /* noop */ }
    try { ctxRef.current?.close(); } catch (e) { /* noop */ }
    streamRef.current = null; ctxRef.current = null; analyserRef.current = null; setGranted(false);
  }, []);

  // Re-acquire the mic on a device / noise-suppression change so it takes effect.
  const republish = useCallback(async () => { if (streamRef.current) { stop(); await start(); } }, [start, stop]);
  const changeInput = useCallback((id) => { setInputId(id); }, []);
  const changeOutput = useCallback((id) => { setOutputId(id); }, []);
  const changeNoiseSuppression = useCallback((v) => { setNoiseSuppression(v); }, []);
  useEffect(() => { if (streamRef.current) republish(); /* eslint-disable-next-line */ }, [inputId, noiseSuppression]);

  // Record ~3s from the mic and play it back so the user can confirm they are heard.
  const testMic = useCallback(async (ms = 3000) => {
    try {
      const own = !streamRef.current;
      const audioConstraints = { echoCancellation: true, noiseSuppression: nsRef.current };
      if (inRef.current) audioConstraints.deviceId = { exact: inRef.current };
      const stream = streamRef.current || await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
      if (typeof MediaRecorder === "undefined") return false;
      const rec = new MediaRecorder(stream);
      const chunks = [];
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      const done = new Promise((r) => { rec.onstop = r; });
      setTesting("rec");
      rec.start();
      await new Promise((r) => setTimeout(r, ms));
      rec.stop();
      await done;
      if (own) stream.getTracks().forEach((t) => t.stop());
      const url = URL.createObjectURL(new Blob(chunks, { type: "audio/webm" }));
      const el = new Audio(url);
      if (outputId && el.setSinkId) { try { await el.setSinkId(outputId); } catch (e) { /* unsupported */ } }
      setTesting("play");
      el.onended = () => { setTesting(""); URL.revokeObjectURL(url); };
      await el.play();
      return true;
    } catch (e) { setTesting(""); return false; }
  }, [outputId]);

  const getLevel = useCallback(() => {
    const a = analyserRef.current, d = dataRef.current;
    if (!a || !d) return 0;
    a.getByteTimeDomainData(d);
    let sum = 0;
    for (let i = 0; i < d.length; i++) { const x = (d[i] - 128) / 128; sum += x * x; }
    return Math.min(1, Math.sqrt(sum / d.length) * 2.4);
  }, []);

  useEffect(() => () => stop(), [stop]);
  return {
    start, stop, getLevel, granted,
    devices, listDevices, inputId, outputId, changeInput, changeOutput,
    noiseSuppression, setNoiseSuppression: changeNoiseSuppression, testMic, testing,
  };
}
