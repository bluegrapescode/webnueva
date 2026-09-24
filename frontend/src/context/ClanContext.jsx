import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, clansWsUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

const ClanCtx = createContext(null);
export const useClan = () => useContext(ClanCtx);

export function ClanProvider({ children }) {
  const { user, refresh: refreshAuth } = useAuth();
  const { play } = useSound();
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState([]);
  const [globalMessages, setGlobalMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const wsRef = useRef(null);

  const refresh = useCallback(async () => {
    try { const { data } = await api.clanMe(); setMe(data); }
    catch { setMe({ clan: null, invites: [], config: {} }); }
    finally { setLoading(false); }
  }, []);

  const loadChat = useCallback(async () => {
    try { const { data } = await api.clanChatHistory(60, "clan"); setMessages(data.messages || []); } catch { /* no clan */ }
  }, []);
  const loadGlobalChat = useCallback(async () => {
    try { const { data } = await api.clanChatHistory(60, "global"); setGlobalMessages(data.messages || []); } catch { /* no clan */ }
  }, []);

  useEffect(() => { if (user) refresh(); else { setMe(null); setLoading(false); } }, [user, refresh]);
  useEffect(() => { if (me?.clan) { loadChat(); loadGlobalChat(); } else { setMessages([]); setGlobalMessages([]); } }, [me?.clan?.id]);  // eslint-disable-line

  useEffect(() => {
    if (!user) return;
    let stop = false, ping = null, retry = null;
    const connect = () => {
      if (stop) return;
      let ws; try { ws = new WebSocket(clansWsUrl()); } catch { return; }
      wsRef.current = ws;
      ws.onopen = () => { ping = setInterval(() => { try { ws.readyState === 1 && ws.send("ping"); } catch {} }, 25000); };
      ws.onmessage = (ev) => {
        if (ev.data === "pong") return;
        let m; try { m = JSON.parse(ev.data); } catch { return; }
        switch (m.event) {
          case "clan:message":
            setMessages((s) => [...s.slice(-99), m.data]);
            if (!m.data.system) play?.("click");
            break;
          case "clan:global":
            setGlobalMessages((s) => [...s.slice(-99), m.data]);
            break;
          case "clan:updated": refresh(); break;
          case "clan:removed": toast.message("Ya no perteneces al clan."); refresh(); setMessages([]); setGlobalMessages([]); break;
          case "clan:invited": play?.("open"); toast.info(`Invitación al clan [${m.data.tag}] ${m.data.name}`); refresh(); break;
          case "clan:config": refresh(); break;
          default: break;
        }
      };
      ws.onclose = () => { if (ping) clearInterval(ping); if (!stop) retry = setTimeout(connect, 2500); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    connect();
    return () => { stop = true; if (ping) clearInterval(ping); if (retry) clearTimeout(retry); try { wsRef.current?.close(); } catch {} };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const act = useCallback(async (fn, okMsg, sound = "success") => {
    if (busy) return;
    setBusy(true);
    try { const r = await fn(); if (okMsg) { play?.(sound); toast.success(okMsg); } await refresh(); refreshAuth?.(); return r?.data ?? r; }
    catch (e) { play?.("error"); toast.error(e?.response?.data?.detail || "Error"); throw e; }
    finally { setBusy(false); }
  }, [busy, refresh, refreshAuth, play]);

  const sendChat = useCallback(async (text, channel = "clan") => {
    try { await api.clanChatSend(text, channel); } catch (e) { toast.error(e?.response?.data?.detail || "No se pudo enviar"); }
  }, []);

  return (
    <ClanCtx.Provider value={{ me, loading, busy, messages, globalMessages, refresh, sendChat, act, api }}>
      {children}
    </ClanCtx.Provider>
  );
}
