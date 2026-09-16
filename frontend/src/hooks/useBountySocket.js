import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";

// Estado en vivo del Sistema de Bounties. Un solo WebSocket público (sin polling)
// con reconexión exponencial. Expone { snapshot, lastEvent } y refresca el
// snapshot ante cada evento del servidor.
export function useBountySocket(onEvent) {
  const [snapshot, setSnapshot] = useState(null);
  const [lastEvent, setLastEvent] = useState(null);
  const [connected, setConnected] = useState(false);
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  const applyEvent = useCallback((event, data) => {
    setLastEvent({ event, data, at: Date.now() });
    if (event === "bounty:state") {
      setSnapshot(data);
      return;
    }
    setSnapshot((prev) => {
      const cfg = (prev && prev.config) || (data && data.config) || null;
      if (event === "bounty:new" || event === "bounty:active" || event === "bounty:target_returned") {
        return { ...(prev || {}), phase: "active", paused: false, bounty: data.bountyId ? data : (prev && prev.bounty) };
      }
      if (event === "bounty:target_disconnected") {
        const b = prev && prev.bounty ? { ...prev.bounty, status: "suspended", suspendUntil: data.suspendUntil } : prev?.bounty;
        return { ...(prev || {}), phase: "active", bounty: b };
      }
      if (event === "bounty:completed") {
        return { ...(prev || {}), phase: "waiting", bounty: data, nextAt: data.nextAt, config: cfg };
      }
      if (event === "bounty:cancelled") {
        return { ...(prev || {}), phase: "waiting", bounty: null, config: cfg };
      }
      if (event === "bounty:waiting") {
        return { ...(prev || {}), phase: "waiting", bounty: null, nextAt: data.nextAt, config: cfg };
      }
      if (event === "bounty:paused") {
        return { ...(prev || {}), paused: !!data.paused };
      }
      if (event === "bounty:config") {
        return { ...(prev || {}), config: data };
      }
      return prev;
    });
    cbRef.current && cbRef.current(event, data);
  }, []);

  useEffect(() => {
    let ws = null, closed = false, retry = 0, pingTimer = null;

    const connect = () => {
      if (closed) return;
      let url;
      try { url = api.bountyWsUrl(); } catch (e) { scheduleReconnect(); return; }
      try { ws = new WebSocket(url); } catch (e) { scheduleReconnect(); return; }
      ws.onopen = () => {
        retry = 0; setConnected(true);
        pingTimer = setInterval(() => { try { ws.readyState === 1 && ws.send("ping"); } catch (e) {} }, 25000);
      };
      ws.onmessage = (ev) => {
        if (ev.data === "pong") return;
        try { const m = JSON.parse(ev.data); applyEvent(m.event, m.data); } catch (e) {}
      };
      ws.onclose = () => { setConnected(false); pingTimer && clearInterval(pingTimer); scheduleReconnect(); };
      ws.onerror = () => { try { ws.close(); } catch (e) {} };
    };
    const scheduleReconnect = () => {
      if (closed) return;
      retry += 1;
      setTimeout(connect, Math.min(15000, 1000 * Math.pow(1.6, retry)));
    };

    connect();
    return () => { closed = true; pingTimer && clearInterval(pingTimer); try { ws && ws.close(); } catch (e) {} };
  }, [applyEvent]);

  return { snapshot, lastEvent, connected };
}
