import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/**
 * useGen0Contamination — Hook que devuelve { percent, source, updatedAt }.
 *
 * CONECTADO AL BACKEND REAL (Opción A del bundle GEN-Ø, 2026-08-21):
 * consulta GET /api/gen0/contamination cada 15 s — el porcentaje lo calcula el
 * rastreador de instalaciones contaminadas del backend (gen0_infection.py).
 * El bloque DEMO original del bundle queda reemplazado por este fetch; el chip
 * del panel pasa solo a "LIVE FEED" en cuanto llega la primera respuesta.
 *
 * Retorno:
 *   { percent, source, updatedAt, cooldownS, cooldownTotalS, cooldownAtMs }
 *   - percent:   número 0..100 (0 hasta la primera respuesta)
 *   - source:    "demo" | "live"  ("live" desde la primera respuesta real)
 *   - updatedAt: ISO string de última actualización
 *   - cooldownS: segundos restantes del enfriamiento ENTRE instalaciones
 *                (orden del dueño 2026-08-21: tras cada instalación, las
 *                demás no cuentan durante 2 h) — 0 si no hay enfriamiento
 *   - cooldownTotalS: duración completa de la ventana (para contexto visual)
 *   - cooldownAtMs:   Date.now() del momento en que cooldownS se midió; el
 *                     panel descuenta localmente contra este ancla
 *
 * Un error de red conserva el último porcentaje conocido y reintenta en el
 * próximo intervalo — la barra nunca se blanquea por un fallo transitorio.
 */
export function useGen0Contamination() {
  const [percent, setPercent] = useState(0);
  const [source, setSource] = useState("demo");
  const [updatedAt, setUpdatedAt] = useState(() => new Date().toISOString());
  const [cooldown, setCooldown] = useState({ s: 0, totalS: 0, atMs: 0 });
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    // ★ api is this repo's NAMED-METHOD map over a private axios client — it
    // has no generic .get (calling one crashed the tab: "Vm.get is not a
    // function", caught live 2026-08-21). Every endpoint gets a named method.
    const load = () =>
      api
        .gen0Contamination()
        .then((r) => {
          if (!alive.current) return;
          const p = Number(r?.data?.percent);
          if (Number.isFinite(p)) {
            setPercent(Math.max(0, Math.min(100, p)));
            setSource("live");
            setUpdatedAt(new Date().toISOString());
          }
          const cd = Number(r?.data?.cooldown_s);
          if (Number.isFinite(cd)) {
            setCooldown({
              s: Math.max(0, cd),
              totalS: Math.max(0, Number(r?.data?.cooldown_total_s) || 0),
              atMs: Date.now(),
            });
          }
        })
        .catch(() => {}); // transitorio: conserva el último valor y reintenta
    load();
    const t = setInterval(load, 15_000);
    return () => {
      alive.current = false;
      clearInterval(t);
    };
  }, []);

  return {
    percent, source, updatedAt,
    cooldownS: cooldown.s,
    cooldownTotalS: cooldown.totalS,
    cooldownAtMs: cooldown.atMs,
  };
}

/**
 * Formatea segundos de enfriamiento como HH:MM:SS (reloj fijo, sin saltos de
 * ancho). Entrada hostil (NaN, negativos, strings) pinta 00:00:00 — el
 * temporizador nunca puede romper el panel. Función pura, testeable.
 */
export function formatGen0Cooldown(totalSeconds) {
  const n = Number(totalSeconds);
  const s = Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0;
  const pad = (v) => String(v).padStart(2, "0");
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

/**
 * Devuelve el metadato del estado actual según el porcentaje.
 * Función pura, sin side-effects: útil también para tests.
 */
export function gen0StatusFor(percent) {
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  if (p >= 100)     return { key: "complete",      label: "MUTACIÓN COMPLETA",       color: "#B91C1C", accent: "#EF4444", tone: "critical",  intensity: 4 };
  if (p >= 75)      return { key: "advanced",      label: "MUTACIÓN AVANZADA",       color: "#DC2626", accent: "#F87171", tone: "critical",  intensity: 3 };
  if (p >= 50)      return { key: "active",        label: "INFECCIÓN ACTIVA",        color: "#F59E0B", accent: "#FBBF24", tone: "warning",   intensity: 2 };
  if (p >= 25)      return { key: "initial",       label: "CONTAMINACIÓN INICIAL",   color: "#EAB308", accent: "#FACC15", tone: "caution",   intensity: 1 };
  return                    { key: "clean",         label: "LIMPIO",                  color: "#22C55E", accent: "#4ADE80", tone: "safe",      intensity: 0 };
}
