import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, turfWsUrl } from "@/lib/api";

// Turf Wars — estado en vivo de zonas + leaderboard vía WebSocket público.
export function useTurf(enabled = true) {
  const [state, setState] = useState({ zones: [], leaderboard: [], config: {}, my_clan_id: null, my_rally: null });
  const [busy, setBusy] = useState(false);
  const wsRef = useRef(null);

  const load = useCallback(async () => {
    try { const { data } = await api.turfState(); setState((s) => ({ ...data, my_clan_id: data.my_clan_id ?? s.my_clan_id })); }
    catch { /* sin sesión */ }
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    load();
    let stop = false, ping = null, retry = null;
    const connect = () => {
      if (stop) return;
      let ws; try { ws = new WebSocket(turfWsUrl()); } catch { return; }
      wsRef.current = ws;
      ws.onopen = () => { ping = setInterval(() => { try { ws.readyState === 1 && ws.send("ping"); } catch {} }, 25000); };
      ws.onmessage = (ev) => {
        if (ev.data === "pong") return;
        let m; try { m = JSON.parse(ev.data); } catch { return; }
        if (m.event === "turf:state") setState((s) => ({ ...m.data, my_clan_id: s.my_clan_id, my_rally: s.my_rally }));
        else if (m.event === "turf:captured") {
          const o = m.data.owner || {};
          toast.message(`⚔️ ${m.data.zone_name} capturada por [${o.tag}] ${o.name}`);
          load();
        }
      };
      ws.onclose = () => { if (ping) clearInterval(ping); if (!stop) retry = setTimeout(connect, 2500); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    connect();
    return () => { stop = true; if (ping) clearInterval(ping); if (retry) clearTimeout(retry); try { wsRef.current?.close(); } catch {} };
  }, [enabled, load]);

  const rally = useCallback(async (zoneId) => {
    if (busy) return;
    setBusy(true);
    try { const { data } = await api.turfRally(zoneId); toast.success(`📣 ¡Rally lanzado! Refuerza la zona ${data.seconds}s`); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "No se pudo lanzar el rally"); }
    finally { setBusy(false); }
  }, [busy, load]);

  return { ...state, busy, rally, refresh: load };
}
