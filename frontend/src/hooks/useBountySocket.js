import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";

// Estado en vivo del Sistema de Cacería. Un WebSocket (autenticado si hay token)
// con reconexión. Mantiene { board, config } y reenvía cada evento a onEvent
// (contract_new, completed, self_started, self_tick, self_ended, self_expired,
// self_invite, self_mine, board, config).
export function useBountySocket(onEvent) {
  const [board, setBoard] = useState({ contracts: [], self: [] });
  const [config, setConfig] = useState(null);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  const apply = useCallback((event, data) => {
    setLastEvent({ event, data, at: Date.now() });
    if (event === "bounty:state") {
      if (data.board) setBoard(data.board);
      if (data.config) setConfig(data.config);
    } else if (event === "bounty:board") {
      setBoard(data);
    } else if (event === "bounty:config") {
      setConfig(data);
    }
    cbRef.current && cbRef.current(event, data);
  }, []);

  useEffect(() => {
    let ws = null, closed = false, retry = 0, ping = null;
    const connect = () => {
      if (closed) return;
      let url;
      try { url = api.bountyWsUrl(); } catch (e) { schedule(); return; }
      try { ws = new WebSocket(url); } catch (e) { schedule(); return; }
      ws.onopen = () => { retry = 0; setConnected(true); ping = setInterval(() => { try { ws.readyState === 1 && ws.send("ping"); } catch (e) {} }, 25000); };
      ws.onmessage = (ev) => { if (ev.data === "pong") return; try { const m = JSON.parse(ev.data); apply(m.event, m.data); } catch (e) {} };
      ws.onclose = () => { setConnected(false); ping && clearInterval(ping); schedule(); };
      ws.onerror = () => { try { ws.close(); } catch (e) {} };
    };
    const schedule = () => { if (closed) return; retry += 1; setTimeout(connect, Math.min(15000, 1000 * Math.pow(1.6, retry))); };
    connect();
    return () => { closed = true; ping && clearInterval(ping); try { ws && ws.close(); } catch (e) {} };
  }, [apply]);

  return { board, config, connected, lastEvent };
}
