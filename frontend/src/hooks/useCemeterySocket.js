import { useEffect, useRef } from "react";

// Real-time cemetery feed. Reconnects with backoff; forwards every JSON frame
// to onMessage. Token (if present) lets the server push per-user fossil balance.
export function useCemeterySocket(onMessage) {
  const cbRef = useRef(onMessage);
  cbRef.current = onMessage;

  useEffect(() => {
    let ws = null;
    let closed = false;
    let retry = 0;
    let pingTimer = null;

    const connect = () => {
      if (closed) return;
      const base = process.env.REACT_APP_BACKEND_URL || "";
      const wsBase = base.replace(/^http/i, "ws");
      const token = localStorage.getItem("primal_token");
      const url = `${wsBase}/api/cemetery/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
      try {
        ws = new WebSocket(url);
      } catch (e) {
        scheduleReconnect();
        return;
      }
      ws.onopen = () => {
        retry = 0;
        pingTimer = setInterval(() => {
          try { ws.readyState === 1 && ws.send("ping"); } catch (e) {}
        }, 25000);
      };
      ws.onmessage = (ev) => {
        if (ev.data === "pong") return;
        try {
          const msg = JSON.parse(ev.data);
          cbRef.current && cbRef.current(msg);
        } catch (e) {}
      };
      ws.onclose = () => {
        pingTimer && clearInterval(pingTimer);
        scheduleReconnect();
      };
      ws.onerror = () => { try { ws.close(); } catch (e) {} };
    };

    const scheduleReconnect = () => {
      if (closed) return;
      retry += 1;
      const delay = Math.min(15000, 1000 * Math.pow(1.6, retry));
      setTimeout(connect, delay);
    };

    connect();
    return () => {
      closed = true;
      pingTimer && clearInterval(pingTimer);
      try { ws && ws.close(); } catch (e) {}
    };
  }, []);
}
