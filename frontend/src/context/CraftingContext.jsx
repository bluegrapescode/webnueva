import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, craftingWsUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const CraftingCtx = createContext(null);
export const useCrafting = () => useContext(CraftingCtx);

const uuid = () => (window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

export function CraftingProvider({ children }) {
  const { user } = useAuth();
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState({});          // recipe_id / job_id -> true
  const wsRef = useRef(null);
  const retryRef = useRef(null);

  const refresh = useCallback(async () => {
    try { const { data } = await api.craftingState(); setState(data); }
    catch { setState((s) => s || { materials: [], recipes: [], inventory: [], active_jobs: [], settings: {}, craft_limit: 1 }); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (user) refresh(); else { setState(null); setLoading(false); } }, [user, refresh]);

  // WebSocket — eventos en vivo, sin polling. Reconexión + heartbeat.
  useEffect(() => {
    if (!user) return;
    let stop = false, ping = null;
    const connect = () => {
      if (stop) return;
      let ws;
      try { ws = new WebSocket(craftingWsUrl()); } catch { return; }
      wsRef.current = ws;
      ws.onopen = () => { ping = setInterval(() => { try { ws.readyState === 1 && ws.send("ping"); } catch {} }, 25000); };
      ws.onmessage = (ev) => {
        if (ev.data === "pong") return;
        let msg; try { msg = JSON.parse(ev.data); } catch { return; }
        const notif = state?.settings?.notifications_enabled !== false;
        switch (msg.event) {
          case "materials:updated":
            setState((s) => s ? { ...s, inventory: msg.data.inventory } : s);
            refresh(); // re-evalúa checks ✅/❌ y el botón CRAFT al instante
            break;
          case "material:collected":
            if (notif) { const m = state?.materials?.find((x) => x.id === msg.data.material_id); toast.success(`+${msg.data.amount} ${m?.name || "material"}`); }
            break;
          case "crafting:started": if (notif) toast.info(`Crafteo iniciado: ${msg.data.job?.recipe?.name || ""}`); refresh(); break;
          case "crafting:completed": if (notif) toast.success(`¡Tu skin ${msg.data.job?.recipe?.name || ""} está lista!`, { icon: "🔔" }); refresh(); break;
          case "crafting:claimed": if (notif) toast.success(`${msg.data.recipe?.name || "Skin"} añadida a tu colección.`); refresh(); break;
          case "crafting:cancelled": refresh(); break;
          case "recipe:updated": case "material:updated": case "settings:updated": refresh(); break;
          default: break;
        }
      };
      ws.onclose = () => { if (ping) clearInterval(ping); if (!stop) retryRef.current = setTimeout(connect, 2500); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    connect();
    return () => { stop = true; if (ping) clearInterval(ping); if (retryRef.current) clearTimeout(retryRef.current); try { wsRef.current?.close(); } catch {} };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const setBusyKey = (k, v) => setBusy((b) => ({ ...b, [k]: v }));

  const craft = useCallback(async (recipeId) => {
    if (busy[recipeId]) return;
    setBusyKey(recipeId, true);
    try {
      const { data } = await api.craftingCraft(recipeId, uuid());
      await refresh();
      return data;
    } catch (e) { toast.error(e?.response?.data?.detail || "No se pudo iniciar el crafteo"); }
    finally { setBusyKey(recipeId, false); }
  }, [busy, refresh]);

  const claim = useCallback(async (jobId) => {
    if (busy[jobId]) return;
    setBusyKey(jobId, true);
    try { const { data } = await api.craftingClaim(jobId, uuid()); await refresh(); return data; }
    catch (e) { toast.error(e?.response?.data?.detail || "No se pudo reclamar"); }
    finally { setBusyKey(jobId, false); }
  }, [busy, refresh]);

  const cancel = useCallback(async (jobId) => {
    if (busy[jobId]) return;
    setBusyKey(jobId, true);
    try { await api.craftingCancel(jobId); toast.message("Crafteo cancelado, materiales reembolsados."); await refresh(); }
    catch (e) { toast.error(e?.response?.data?.detail || "No se pudo cancelar"); }
    finally { setBusyKey(jobId, false); }
  }, [busy, refresh]);

  const qtyOf = useCallback((mid) => (state?.inventory || []).find((i) => i.material_id === mid)?.quantity || 0, [state]);
  const matById = useCallback((mid) => (state?.materials || []).find((m) => m.id === mid), [state]);

  return (
    <CraftingCtx.Provider value={{ state, loading, busy, refresh, craft, claim, cancel, qtyOf, matById }}>
      {children}
    </CraftingCtx.Provider>
  );
}
