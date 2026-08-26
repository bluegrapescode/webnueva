import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";

const LiveSimContext = createContext(null);

// ── Word pools that build believable, ever-changing server events (Spanish). ──
const NAME_A = ["Rex", "Draco", "Nyx", "Kaiju", "Vortex", "Bruma", "Zephyr", "Onyx", "Kira", "Tarv", "Loki", "Nova", "Sombra", "Titan", "Ember", "Furia", "Ghost", "Pyro", "Vega", "Raptor", "Cielo", "Colmillo", "Aztec", "Neon", "Volcán", "Trueno", "Selva", "Ámbar", "Zafiro", "Hydra"];
const NAME_B = ["_MX", "_AR", "_CO", "_CL", "_PE", "TV", "YT", "77", "_LATAM", "GG", "_prime", "X", "_09", "_king", "Pro", "_dino", "23", "_ISLA", "_gg", ""];
const DEFAULT_DINOS = ["Tyrannosaurus", "Carnotaurus", "Utahraptor", "Allosaurus", "Deinosuchus", "Ceratosaurus", "Dilophosaurus", "Herrerasaurus", "Omniraptor", "Maiasaura", "Tenontosaurus", "Pachycephalosaurus", "Diabloceratops", "Stegosaurus", "Gallimimus", "Troodon", "Beipiaosaurus", "Hypsilophodon"];
const LOCATIONS = ["Laguna Norte", "Bosque de Secuoyas", "Pantano Este", "Cañón Rojo", "Costa Salada", "Meseta Central", "Río Serpiente", "Cráter Sur", "Cuevas de Ámbar", "Llanura Ceniza"];
const SKINS = ["Aurora Boreal", "Ceniza Volcánica", "Jade Antiguo", "Sombra Espectral", "Oro Real", "Escarcha Ártica", "Fuego Primal", "Selva Neón"];

const rand = (arr) => arr[Math.floor(Math.random() * arr.length)];
const player = () => `${rand(NAME_A)}${rand(NAME_B)}`;
const money = () => (Math.floor(Math.random() * 90) + 5) * 100;

// Event templates. `hot` events also raise a toast. `kind` maps to icon+colour.
function makeEvent(dinos) {
  const dino = rand(dinos);
  const roll = Math.random();
  if (roll < 0.16) return { kind: "kill", hot: dino === "Tyrannosaurus" || Math.random() < 0.25, text: `${player()} cazó a ${player()} con un ${dino}` };
  if (roll < 0.32) return { kind: "join", text: `${player()} entró al servidor` };
  if (roll < 0.44) return { kind: "leave", text: `${player()} abandonó la isla` };
  if (roll < 0.58) return { kind: "sale", text: `${player()} vendió un ${dino} por ${money().toLocaleString()} 🩸` };
  if (roll < 0.70) return { kind: "win", hot: Math.random() < 0.3, text: `${player()} ganó ${money().toLocaleString()} en ${rand(["la Ruleta", "Blackjack", "Roll", "las Cajas"])}` };
  if (roll < 0.80) return { kind: "growth", text: `${player()} alcanzó la adultez con su ${dino}` };
  if (roll < 0.88) return { kind: "quest", text: `${player()} completó una misión en ${rand(LOCATIONS)}` };
  if (roll < 0.94) return { kind: "skin", hot: Math.random() < 0.2, text: `${player()} desbloqueó la skin "${rand(SKINS)}"` };
  if (roll < 0.98) return { kind: "nest", text: `Un nido de ${dino} eclosionó en ${rand(LOCATIONS)}` };
  return { kind: "record", hot: true, text: `¡${player()} rompió el récord del ${dino} más grande!` };
}

let seq = 0;

export function LiveSimProvider({ children }) {
  const { play } = useSound();
  const [maxPlayers, setMaxPlayers] = useState(120);
  const [players, setPlayers] = useState(() => 70 + Math.floor(Math.random() * 40));
  const [events, setEvents] = useState([]);
  const [now, setNow] = useState(Date.now());
  const dinosRef = useRef(DEFAULT_DINOS);
  const lastToast = useRef(0);
  const toastRef = useRef(null); // set by LiveTicker to surface hot events

  const registerToast = useCallback((fn) => { toastRef.current = fn; }, []);

  // Seed dino names + real server numbers once.
  useEffect(() => {
    api.serverStatus?.().then((r) => {
      if (r?.data?.max_players) setMaxPlayers(r.data.max_players);
      if (typeof r?.data?.players === "number") setPlayers(r.data.players);
    }).catch(() => {});
    api.dinosaurs?.().then((r) => {
      const names = (r?.data || []).map((d) => d.name || d.common_name || d.slug).filter(Boolean);
      if (names.length) dinosRef.current = names;
    }).catch(() => {});
  }, []);

  // Relative-time ticker (drives "hace Xs" without re-timing each event).
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // The heartbeat: push a new event and drift the player count.
  useEffect(() => {
    let alive = true;
    const tick = () => {
      if (!alive) return;
      const e = makeEvent(dinosRef.current);
      const entry = { id: ++seq, ts: Date.now(), ...e };
      setEvents((prev) => [entry, ...prev].slice(0, 40));

      // player count drifts naturally within a live-feeling band
      setPlayers((p) => {
        const lo = Math.round(maxPlayers * 0.5);
        const delta = Math.floor(Math.random() * 5) - 2; // -2..+2
        return Math.max(lo, Math.min(maxPlayers, p + delta));
      });

      // occasional toast for "hot" events, throttled
      if (entry.hot && Date.now() - lastToast.current > 12000 && toastRef.current) {
        lastToast.current = Date.now();
        toastRef.current(entry);
        play("notification");
      }

      const next = 1800 + Math.random() * 2600; // 1.8s – 4.4s
      timer = setTimeout(tick, next);
    };
    let timer = setTimeout(tick, 1200);
    return () => { alive = false; clearTimeout(timer); };
  }, [maxPlayers, play]);

  const value = { players, maxPlayers, events, now, registerToast, live: true };
  return <LiveSimContext.Provider value={value}>{children}</LiveSimContext.Provider>;
}

export const useLiveSim = () => useContext(LiveSimContext) || { players: 0, maxPlayers: 120, events: [], now: Date.now(), registerToast: () => {}, live: false };
