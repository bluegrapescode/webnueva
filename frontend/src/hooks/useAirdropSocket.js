import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";

// Estado GLOBAL del Airdrop sincronizado por el servidor. Un WebSocket (token
// opcional) con reconexión. El backend es la única fuente de verdad: el front
// NO usa temporizadores propios que deriven, calcula todo desde `server_time`
// (offset del reloj) y los sellos `drop_at` / `land_at` / `expire_at` / `next_at`.
// Reenvía cada evento a onEvent: sync | incoming | falling | available |
// claimed | rewards | expired | next | disabled.
export function useAirdropSocket(onEvent) {
  const [state, setState] = useState(null);
  const [connected, setConnected] = useState(false);
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;
  const offsetRef = useRef(0);

  const apply = useCallback((event, data) => {
    if (data && data.server_time) {
      offsetRef.current = new Date(data.server_time).getTime() - Date.now();
    }
    setState((prev) => {
      let next = prev ? { ...prev } : {};
      if (data && typeof data === "object") {
        if (data.state) next = { ...data };
        else next = { ...next, ...data };
      }
      if (event === "airdrop:claimed") {
        next.state = "claimed";
        if (data && data.winner) next.winner = data.winner;
        if (data && data.cooldown_until) next.cooldown_until = data.cooldown_until;
        if (data && data.rarity) next.rarity = data.rarity;
      } else if (event === "airdrop:expired") {
        next.state = "expired";
        if (data && data.cooldown_until) next.cooldown_until = data.cooldown_until;
      } else if (event === "airdrop:disabled") {
        next.state = "disabled";
      } else if (event === "airdrop:rewards") {
        if (data && data.rewards) next.my_rewards = data.rewards;
        if (data && data.rarity) next.rarity = data.rarity;
      }
      return next;
    });
    cbRef.current && cbRef.current(event, data);
  }, []);

  // Carga REST inicial para tener datos al instante (WS confirma después).
  useEffect(() => {
    let alive = true;
    api.airdropState()
      .then((r) => { if (alive) apply("airdrop:sync", r.data); })
      .catch(() => {});
    return () => { alive = false; };
  }, [apply]);

  useEffect(() => {
    let ws = null, closed = false, retry = 0, ping = null;
    const connect = () => {
      if (closed) return;
      let url;
      try { url = api.airdropWsUrl(); } catch (e) { schedule(); return; }
      try { ws = new WebSocket(url); } catch (e) { schedule(); return; }
      ws.onopen = () => {
        retry = 0; setConnected(true);
        ping = setInterval(() => { try { ws.readyState === 1 && ws.send(JSON.stringify({ event: "ping" })); } catch (e) {} }, 25000);
      };
      ws.onmessage = (ev) => {
        try { const m = JSON.parse(ev.data); if (m.event === "pong") return; apply(m.event, m.data); } catch (e) {}
      };
      ws.onclose = () => { setConnected(false); ping && clearInterval(ping); schedule(); };
      ws.onerror = () => { try { ws.close(); } catch (e) {} };
    };
    const schedule = () => { if (closed) return; retry += 1; setTimeout(connect, Math.min(15000, 1000 * Math.pow(1.6, retry))); };
    connect();
    return () => { closed = true; ping && clearInterval(ping); try { ws && ws.close(); } catch (e) {} };
  }, [apply]);

  const serverNow = useCallback(() => Date.now() + offsetRef.current, []);

  return { state, setState, connected, serverNow };
}
