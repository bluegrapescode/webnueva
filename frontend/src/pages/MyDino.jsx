import React, { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Package, MapPin, RefreshCw, PowerOff, Check, X, AlertTriangle, Dna } from "lucide-react";
import { api } from "@/lib/api";
import { resolveMyDinoTab } from "@/lib/myDinoTabs";
import {
  vitalPair, rawPair, sprintInfo, biteInfo, bleedInfo, fractureOverall,
  dietInfo, stageFor, updatedAgo, buildLiveChecklist,
} from "@/lib/livePanel";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { HudCorners, HudGrid, StatusDot } from "@/components/common/Hud";
import { SpeciesViewer3D } from "@/components/skin3d/SpeciesViewer3D";
import { InteractiveMap } from "@/components/livemap/InteractiveMap";
import { VaultSection } from "@/components/inventory/VaultSection";
import { InventoryPanel } from "@/components/inventory/InventoryPanel";
import { Gen0VirusPanel } from "@/components/gen0/Gen0VirusPanel";

// ── Page identity ────────────────────────────────────────────────────────────
// 2026-08-07 owner redesign: the stats tab is a 1:1 recreation of the reference
// card he sent — "LIVE DINOSAUR" page title, the specimen panel on the left and
// one stats card on the right (vitals as current/max pairs over colour bars,
// nutrient diet, and the prime checklist WITH the two rows he added: sanctuary
// and perfect diet). Colours are inline hex on purpose — Tailwind only emits
// classes it can literally see in source, and these are page-local values.
const RED = "#E24A4A";
const GREEN = "#46C46B";
const CARD_BG = "#161311";
const PANEL_BG = "#0f0d0b";
const HAIRLINE = "rgba(255,255,255,0.07)";
const TRACK = "rgba(255,255,255,0.09)";
const MUTED = "rgba(255,255,255,0.5)";
const INK = "#F5F2ED";

const TABS = [
  { k: "stats", label: "Estadísticas", icon: Activity },
  { k: "equipo", label: "Equipo", icon: Package },
  { k: "map", label: "Mapa", icon: MapPin },
  { k: "gen0", label: "GEN-Ø", icon: Dna },
];

// The nine vital cells, in the reference card's exact order. `read` derives a
// {known,text,ratio}-shaped reading from the dino payload through lib/livePanel
// — all pure, all total, so a malformed poll can never blank the card.
const VITAL_DEFS = [
  { k: "health", label: "HEALTH", color: "#E2574A", read: (d) => vitalPair(d?.health, d?.max_health) },
  { k: "stamina", label: "STAMINA", color: "#E9C83D", read: (d) => vitalPair(d?.stamina, d?.max_stamina) },
  { k: "hunger", label: "HUNGER", color: "#E0812F", read: (d) => vitalPair(d?.hunger, d?.max_hunger) },
  { k: "thirst", label: "THIRST", color: "#4D9FE8", read: (d) => vitalPair(d?.thirst, d?.max_thirst) },
  { k: "oxygen", label: "OXYGEN", color: "#3EC1E8", read: (d) => rawPair(d?.oxygen, d?.max_oxygen) },
  { k: "bleeding", label: "BLEEDING", color: RED, read: (d) => bleedInfo(d?.bleeding_stacks) },
  { k: "sprint", label: "SPRINT SPEED", color: "#8B5CF6", read: (d) => sprintInfo(d?.movement_speed) },
  { k: "bite", label: "BITE DAMAGE", color: RED, read: (d) => biteInfo(d?.bite_value != null ? d.bite_value : d?.bite_damage) },
  { k: "fracture", label: "FRACTURE HEALTH", color: "#3FB960", read: (d) => fractureOverall(d?.fractures) },
];

const DIET_DEFS = [
  { k: "carb", label: "CARBOHYDRATES", color: "#E9C83D" },
  { k: "protein", label: "PROTEINS", color: "#E2574A" },
  { k: "lipid", label: "LIPIDS", color: "#5AB0DA" },
];

// One stat cell: label left, reading right, colour bar welded underneath. The
// fill is a DIV on purpose — an inline <span> ignores height/width and draws
// nothing while every computed style reads correct (recorded fleet defect).
function StatCell({ label, color, info, warn, testid }) {
  return (
    <div data-testid={testid}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] whitespace-nowrap" style={{ color: MUTED }}>
          {warn && <AlertTriangle size={11} style={{ color: RED, flex: "none" }} data-testid={`${testid}-warn`} />}
          {label}
        </span>
        <span className="font-display font-extrabold text-[13px] tabular-nums whitespace-nowrap" style={{ color: info.known ? INK : MUTED }}>
          {info.text}
        </span>
      </div>
      <div className="mt-1.5 rounded-full overflow-hidden" style={{ height: 5, background: TRACK }}>
        <div className="h-full rounded-full" style={{ width: `${Math.round(info.ratio * 100)}%`, background: color }} />
      </div>
    </div>
  );
}

// The growth ring beside the species name: percent inside, stage word under.
function GrowthRing({ growth }) {
  const g = typeof growth === "number" && Number.isFinite(growth) ? Math.max(0, Math.min(100, growth)) : null;
  const R = 30, C = 2 * Math.PI * R;
  const stage = stageFor(growth);
  return (
    <div className="flex flex-col items-center shrink-0" data-testid="growth-ring">
      <div className="relative" style={{ width: 76, height: 76 }}>
        <svg width={76} height={76} viewBox="0 0 76 76" style={{ transform: "rotate(-90deg)" }}>
          <circle cx={38} cy={38} r={R} fill="none" stroke={TRACK} strokeWidth={7} />
          {g != null && (
            <circle cx={38} cy={38} r={R} fill="none" stroke={RED} strokeWidth={7} strokeLinecap="round"
              strokeDasharray={C} strokeDashoffset={C * (1 - g / 100)} />
          )}
        </svg>
        <span className="absolute inset-0 flex items-center justify-center font-display font-extrabold text-[15px] tabular-nums" style={{ color: INK }} data-testid="growth-big">
          {g != null ? `${Math.round(g)}%` : "—"}
        </span>
      </div>
      <span className="mt-1.5 text-[9px] font-bold uppercase tracking-[0.2em]" style={{ color: MUTED }} data-testid="growth-stage">
        {stage || "—"}
      </span>
    </div>
  );
}

// One prime checklist row, right side per state: green "✓ Met", red "✗ Not met"
// / "✗ 0/2 visited", muted "— Not applicable" / "— No data".
function PrimeRow({ row, last }) {
  const counterText = `${row.count}/${row.cap} visited`;
  const right = row.state === "met" ? (
    <span className="inline-flex items-center gap-1.5 text-xs font-bold" style={{ color: GREEN }}>
      <Check size={13} /> {row.kind === "counter" ? counterText : "Met"}
    </span>
  ) : row.state === "not" ? (
    <span className="inline-flex items-center gap-1.5 text-xs font-bold" style={{ color: RED }}>
      <X size={13} /> {row.kind === "counter" ? counterText : "Not met"}
    </span>
  ) : (
    <span className="text-xs font-semibold" style={{ color: MUTED }}>
      — {row.state === "na" ? "Not applicable" : "No data"}
    </span>
  );
  return (
    <div className="flex items-center justify-between gap-3 py-[11px]" style={last ? undefined : { borderBottom: `1px solid ${HAIRLINE}` }}
      data-testid={`prime-row-${row.id}`} data-state={row.state}>
      <span className="text-[13px]" style={{ color: "#E6E2DA" }}>{row.label}</span>
      {right}
    </div>
  );
}

export default function MyDino() {
  const { user } = useAuth();
  const { play } = useSound();
  const [meState, setMeState] = useState(undefined); // undefined=loading, null=no data yet
  const [loadErr, setLoadErr] = useState(null); // null | "auth" | "net"
  const [lastOkAt, setLastOkAt] = useState(null); // ms epoch of the last good poll (footer honesty)
  const [refreshing, setRefreshing] = useState(false);
  const location = useLocation();
  const [tab, setTab] = useState(() => resolveMyDinoTab(window.location.search));
  useEffect(() => {
    setTab(resolveMyDinoTab(location.search));
  }, [location.search]);
  const [aiPositions, setAiPositions] = useState([]);
  const statsTimer = useRef(null);
  const aiTimer = useRef(null);

  const load = () => api.meState()
    .then((r) => { setMeState(r.data); setLoadErr(null); setLastOkAt(Date.now()); })
    .catch((e) => {
      setLoadErr(e?.response?.status === 401 ? "auth" : "net");
      // Never wipe an already-loaded state on a transient poll error; only the first load resolves to null.
      setMeState((prev) => (prev === undefined ? null : prev));
    });

  useEffect(() => {
    if (!user) return undefined;
    load();
    statsTimer.current = setInterval(load, 3000);
    return () => clearInterval(statsTimer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  useEffect(() => {
    if (!user || tab !== "map") return undefined;
    const loadAi = () => api.aiPositions().then((r) => setAiPositions(r.data?.ai || [])).catch(() => {});
    loadAi();
    aiTimer.current = setInterval(loadAi, 5000);
    return () => clearInterval(aiTimer.current);
  }, [user, tab]);

  if (!user) return <div className="max-w-7xl mx-auto px-6 py-14"><SignInPrompt title="Dino en Vivo" sub="Inicia sesión para monitorear tu dinosaurio en vivo." /></div>;

  const reload = () => {
    play("click");
    setRefreshing(true);
    Promise.resolve(load()).finally(() => setTimeout(() => setRefreshing(false), 400));
  };

  const inGame = !!meState?.in_game;
  const dino = meState?.dino || null;
  const diet = dino?.diet || {};
  const checklist = buildLiveChecklist(meState);
  const speciesName = String(dino?.species || dino?.name || "").toUpperCase();

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      {/* ===== Page title — the reference's red-bar "LIVE DINOSAUR" ===== */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
        className="mb-5 flex items-center gap-3" data-testid="livedino-title">
        <span style={{ width: 4, height: 24, background: RED, borderRadius: 1 }} />
        <h1 className="font-display font-extrabold text-[22px] tracking-[0.06em]" style={{ color: INK }}>LIVE DINOSAUR</h1>
      </motion.div>

      <div className="flex gap-0 mb-6 border-b" style={{ borderColor: HAIRLINE }} data-testid="livedino-tabs">
        {TABS.map((t) => (
          <button key={t.k} onClick={() => { setTab(t.k); play("click"); }} data-testid={`livedino-tab-${t.k}`}
            className="inline-flex items-center gap-2 px-5 py-3 text-[11px] font-bold uppercase tracking-[0.18em] transition-colors -mb-px border-b-2"
            style={{
              color: tab === t.k ? RED : "rgba(255,255,255,0.42)",
              borderBottomColor: tab === t.k ? RED : "transparent",
            }}>
            <t.icon size={13} /> {t.label}
          </button>
        ))}
      </div>

      {loadErr === "auth" && (
        <div className="p-4 mb-6 border border-crimson/30 text-sm text-crimson inline-flex items-center gap-2" style={{ borderRadius: 8, background: PANEL_BG }} data-testid="livedino-auth-error">
          <PowerOff size={15} /> Tu sesión expiró. Inicia sesión de nuevo con Steam para ver tu dinosaurio en vivo.
        </div>
      )}
      {loadErr === "net" && meState === null && tab !== "equipo" && (
        <div className="p-4 mb-6 border text-sm text-muted-foreground" style={{ borderRadius: 8, borderColor: HAIRLINE, background: PANEL_BG }} data-testid="livedino-net-error">
          No se pudo contactar al rastreador. Reintentando automáticamente…
        </div>
      )}

      {meState === undefined && tab !== "equipo" && tab !== "gen0" ? <p className="text-muted-foreground">Cargando…</p> : (
        <AnimatePresence mode="wait">
          {tab === "stats" && meState !== undefined && (
            <motion.div key="stats" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
              {!inGame || !dino ? (
                <div className="relative border p-12 text-center overflow-hidden" style={{ background: PANEL_BG, borderRadius: 12, borderColor: HAIRLINE }} data-testid="no-active-dino">
                  <HudCorners color="rgba(226,74,74,0.5)" />
                  <HudGrid color="rgba(226,74,74,0.04)" cell={34} />
                  <div className="relative">
                    <div className="flex justify-center mb-4"><StatusDot online={false} label="Sin conexión" testid="dino-status-offline" /></div>
                    <PowerOff size={36} className="text-muted-foreground/60 mx-auto mb-4" />
                    <h3 className="font-display font-bold text-xl mb-2.5">No estás en el juego ahora</h3>
                    <p className="text-sm text-muted-foreground max-w-md mx-auto leading-relaxed">Únete a un servidor conectado para ver el panel de tu dinosaurio. La página se actualizará automáticamente cuando aparezcas.</p>
                  </div>
                </div>
              ) : (
                <div className="grid lg:grid-cols-[380px_1fr] gap-6 items-start" data-testid="active-dino-card">
                  {/* ===== LEFT — the specimen panel ===== */}
                  <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                    className="relative overflow-hidden border h-[300px] lg:h-[430px] min-w-0"
                    style={{ background: `radial-gradient(120% 90% at 50% 40%, #16120f, ${PANEL_BG} 80%)`, borderRadius: 12, borderColor: HAIRLINE }}
                    data-testid="dino-stage">
                    {/* Owner ruling 2026-07-27 (unchanged by the redesign): still pose, side
                        profile, no animation. interactive=false = the reference's bare
                        specimen panel — no drag chip, fixed camera. */}
                    <SpeciesViewer3D species={dino?.species} active={!!dino?.species} skin={dino?.skin} animate={false} view="side" interactive={false} />
                  </motion.div>

                  {/* ===== RIGHT — the stats card, 1:1 to the reference ===== */}
                  {/* min-w-0 on both grid items: the species name's min-content must never
                      widen the single-column track past a phone viewport (the site clips
                      overflow-x, so a wide track reads as a cut-off card, not a scroll). */}
                  <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
                    className="relative border p-5 sm:p-6 min-w-0" style={{ background: CARD_BG, borderRadius: 12, borderColor: HAIRLINE }}>
                    {/* header strip */}
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] font-bold tracking-[0.22em]" style={{ color: MUTED }}>LIVE DINOSAUR STATS</span>
                      <span className="text-[10px] font-extrabold px-2.5 py-[3px] rounded-full border" data-testid="dino-status"
                        style={{ color: GREEN, borderColor: "rgba(70,196,107,0.4)", background: "rgba(70,196,107,0.1)" }}>LIVE</span>
                      <button onClick={reload} data-testid="livedino-refresh" title="Refresh"
                        className="ml-auto p-1.5 rounded-md transition-colors hover:bg-white/5"
                        style={{ color: MUTED }}>
                        <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
                      </button>
                    </div>

                    {/* species + growth ring */}
                    <div className="flex items-start justify-between gap-4 mt-4">
                      <h2 className="font-display font-black text-3xl sm:text-[34px] leading-tight tracking-tight uppercase min-w-0" style={{ color: INK, overflowWrap: "anywhere" }} data-testid="rail-species">
                        {speciesName || "—"}
                      </h2>
                      <GrowthRing growth={dino?.growth} />
                    </div>

                    {/* ===== VITALS ===== */}
                    <p className="text-[10px] font-bold tracking-[0.22em] mt-2 mb-3.5" style={{ color: MUTED }}>VITALS</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-x-7 gap-y-5" data-testid="vitals-grid">
                      {VITAL_DEFS.map((v) => {
                        const info = v.read(dino);
                        return <StatCell key={v.k} label={v.label} color={v.color} info={info} warn={!!info.warn} testid={`vital-${v.k}`} />;
                      })}
                    </div>

                    {/* ===== NUTRIENT DIET ===== */}
                    <p className="text-[10px] font-bold tracking-[0.22em] mt-6 mb-3.5" style={{ color: MUTED }}>NUTRIENT DIET</p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-7 gap-y-5" data-testid="diet-grid">
                      {DIET_DEFS.map((d) => (
                        <StatCell key={d.k} label={d.label} color={d.color} info={dietInfo(diet[d.k])} testid={`diet-${d.k}`} />
                      ))}
                    </div>

                    {/* ===== PRIME STATUS — the reference's five rows + sanctuary + perfect diet ===== */}
                    <div className="mt-6 border rounded-[10px] px-4 py-4" style={{ background: "rgba(255,255,255,0.03)", borderColor: HAIRLINE }} data-testid="prime-block">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] font-bold tracking-[0.22em]" style={{ color: MUTED }}>PRIME STATUS</span>
                        <span className="text-xs font-bold tabular-nums" style={{ color: INK }} data-testid="prime-status-badge">
                          {checklist.met} of {checklist.total}
                        </span>
                      </div>
                      {checklist.rows.map((row, i) => (
                        <PrimeRow key={row.id} row={row} last={i === checklist.rows.length - 1} />
                      ))}
                    </div>

                    <p className="text-right text-[11px] mt-3.5" style={{ color: "rgba(255,255,255,0.35)" }} data-testid="live-updated">
                      {updatedAgo(lastOkAt != null ? Date.now() - lastOkAt : null)}
                    </p>
                  </motion.div>
                </div>
              )}
            </motion.div>
          )}

          {/* ===== EQUIPO — bóveda e inventario, su propia pestaña; no depende de
               estar en el juego, así que se ve igual estando fuera ===== */}
          {tab === "equipo" && (
            <motion.div key="equipo" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
              data-testid="mydino-equipment">
              <VaultSection />
              <InventoryPanel />
            </motion.div>
          )}

          {tab === "map" && meState !== undefined && (
            <motion.div key="map" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
              {inGame ? (
                <>
                  <InteractiveMap position={meState?.position} aiPositions={aiPositions} />
                  <p className="text-xs text-muted-foreground mt-3">Desplaza o pellizca para acercar, arrastra para mover el mapa. Activa ubicaciones, zonas de migración y patrulla, y usa la mira para centrar en tu dinosaurio.</p>
                </>
              ) : <p className="text-muted-foreground">No hay dino en vivo para rastrear. Aparece en un servidor conectado para verlo aquí.</p>}
            </motion.div>
          )}

          {tab === "gen0" && (
            <motion.div key="gen0" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
              data-testid="livedino-tab-content-gen0">
              {/* ☣️ GEN-Ø — la fuente de datos vive en useGen0Contamination.js
                  (GET /api/gen0/contamination cada 15 s; el porcentaje lo acumula
                  el rastreador de instalaciones contaminadas del backend). */}
              <Gen0VirusPanel />
              <p className="text-xs text-muted-foreground mt-3">
                Panel de contención biológica de nivel 4. Visita instalaciones contaminadas de Nublar y permanece
                dentro para acumular exposición al virus. Al alcanzar el 100% la mutación GEN-Ø se completa.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      )}
    </div>
  );
}
