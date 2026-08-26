import React, { useEffect, useMemo, useRef, useState } from "react";
import { TransformWrapper, TransformComponent, KeepScale } from "react-zoom-pan-pinch";
import { Map as MapIcon, Crosshair, Plus, Minus, Maximize2, ChevronRight, ChevronLeft, Search, MapPin, Radio } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { worldToPct } from "@/lib/mapCalibration";

// Approximate positions on the Gateway map (percentages). Adjustable.
export const MAP_LOCATIONS = [
  { name: "North Bay", x: 36, y: 17 },
  { name: "Northern Jungle", x: 46, y: 30 },
  { name: "North Plains", x: 55, y: 33 },
  { name: "NE Cape", x: 82, y: 22 },
  { name: "NW Ridge", x: 31, y: 36 },
  { name: "Port", x: 88, y: 40 },
  { name: "Water Access", x: 78, y: 44 },
  { name: "Eastern Lake", x: 82, y: 47 },
  { name: "East Coast", x: 90, y: 55 },
  { name: "Forks Plains", x: 63, y: 49 },
  { name: "Highland", x: 49, y: 46 },
  { name: "Jungle I Sector", x: 59, y: 62 },
  { name: "Tide Pool", x: 73, y: 60 },
  { name: "West Coast", x: 15, y: 52 },
  { name: "West Rail", x: 24, y: 58 },
  { name: "The Pit", x: 45, y: 58 },
  { name: "Delta", x: 82, y: 62 },
  { name: "Mudflats", x: 68, y: 66 },
  { name: "Delta Bay", x: 84, y: 70 },
  { name: "South Plains", x: 42, y: 74 },
  { name: "Swamps", x: 62, y: 76 },
  { name: "Sandbank Bay", x: 54, y: 84 },
  { name: "Southern Beach", x: 40, y: 88 },
  { name: "Southern Beach E", x: 58, y: 89 },
];

// Official Gateway v8.21 Mega Migration Zones (MMZ)
const MIGRATION_ZONES = [
  { name: "Highlands MMZ", x: 49, y: 46, r: 11 },
  { name: "North Lake MMZ", x: 50, y: 28, r: 10 },
  { name: "East Lake MMZ", x: 82, y: 48, r: 9 },
  { name: "Delta MMZ", x: 80, y: 63, r: 10 },
  { name: "Swamp MMZ", x: 61, y: 77, r: 10 },
  { name: "West Rail MMZ", x: 25, y: 57, r: 9 },
];

// Drinking water — lakes, rivers, ponds & wallowing holes
const WATER_ZONES = [
  { name: "North Lake", x: 42, y: 24, r: 6 },
  { name: "Eastern Lake", x: 82, y: 47, r: 5 },
  { name: "Central River", x: 62, y: 53, r: 4 },
  { name: "River Fork", x: 57, y: 63, r: 4 },
  { name: "The Pit Pond", x: 45, y: 58, r: 3.5 },
  { name: "Delta Waters", x: 83, y: 66, r: 5 },
  { name: "Tide Pool", x: 73, y: 60, r: 3.5 },
  { name: "Swamp Wallows", x: 62, y: 76, r: 4.5 },
  { name: "West Pond", x: 17, y: 51, r: 3 },
];

// AI Patrol Zones (patrullajes) inside/around the MMZs
const PATROL_ZONES = [
  { name: "Highlands Patrol", x: 47, y: 44 },
  { name: "North Lake Patrol", x: 53, y: 31 },
  { name: "Forks Patrol", x: 63, y: 50 },
  { name: "East Coast Patrol", x: 86, y: 53 },
  { name: "Delta Patrol", x: 79, y: 61 },
  { name: "Swamp Patrol", x: 63, y: 78 },
  { name: "South Plains Patrol", x: 44, y: 73 },
  { name: "West Rail Patrol", x: 26, y: 60 },
];

const slug = (n) => n.toLowerCase().replace(/\s+/g, "-");

// world <-> map calibration lives in lib/mapCalibration.js (worldToPct) —
// one function for every overlay; see the law in that file's header.
const cleanClassName = (c) => String(c || "").replace(/^BP_/, "").replace(/_C$/, "");

function Switch({ on, onClick, testid }) {
  return (
    <button onClick={onClick} data-testid={testid} role="switch" aria-checked={on}
      className="relative w-10 h-[22px] rounded-full transition-all shrink-0 border cursor-pointer"
      style={{
        background: on ? "#10b981" : "rgba(255,255,255,0.10)",
        borderColor: on ? "#34d399" : "rgba(255,255,255,0.18)",
        boxShadow: on ? "0 0 8px rgba(16,185,129,0.5)" : "none",
      }}>
      <span className="absolute top-1/2 rounded-full bg-white transition-all duration-200"
        style={{ height: 16, width: 16, left: on ? 21 : 2, transform: "translateY(-50%)", boxShadow: "0 1px 2px rgba(0,0,0,0.55)" }} />
    </button>
  );
}

function OverlayRow({ title, sub, on, onToggle, testid }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-foreground/90">{title}</p>
        <p className="text-[11px] text-muted-foreground truncate">{sub}</p>
      </div>
      <Switch on={on} onClick={onToggle} testid={testid} />
    </div>
  );
}

// Compact professional player marker
function CompassMarker() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" className="drop-shadow-md">
      <circle cx="12" cy="12" r="10" fill="rgba(225,29,72,0.14)" stroke="rgba(225,29,72,0.55)" strokeWidth="1" />
      <circle cx="12" cy="12" r="4.5" fill="#E11D48" stroke="#fff" strokeWidth="1.5" />
    </svg>
  );
}

// AI dino marker (distinct from the player's own compass dot and other-player dots).
function AiMarker() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" className="drop-shadow-md">
      <circle cx="12" cy="12" r="9" fill="rgba(168,85,247,0.16)" stroke="rgba(168,85,247,0.6)" strokeWidth="1" />
      <circle cx="12" cy="12" r="3.4" fill="#a855f7" stroke="#fff" strokeWidth="1.2" />
    </svg>
  );
}

export function InteractiveMap({ position, aiPositions = [] }) {
  const [showLabels, setShowLabels] = useState(true);
  const [showMigration, setShowMigration] = useState(false);
  const [showWater, setShowWater] = useState(true);
  const [showPatrol, setShowPatrol] = useState(false);
  const [showAi, setShowAi] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState("");
  const [mapSrc, setMapSrc] = useState(MEDIA.gatewayMap);
  const wrapperRef = useRef(null);
  const markerRef = useRef(null);
  const labelRefs = useRef({});

  // GEN-Ø facilities were shown here 2026-08-21 and REMOVED the same day on
  // the owner's order ("players are finding it easily"): the exposure zones
  // are meant to be discovered in-world, so the map draws nothing for them
  // and the backend no longer serves their geometry at all.

  const filtered = useMemo(
    () => MAP_LOCATIONS.filter((l) => l.name.toLowerCase().includes(query.toLowerCase())),
    [query]
  );
  const selfPct = worldToPct(position?.x, position?.y);

  const flyTo = (name) => {
    const node = labelRefs.current[name];
    if (node && wrapperRef.current) wrapperRef.current.zoomToElement(node, 3.2, 700);
  };
  const recenter = () => {
    if (markerRef.current && wrapperRef.current) wrapperRef.current.zoomToElement(markerRef.current, 2.6, 700);
    else wrapperRef.current?.resetTransform(500);
  };

  return (
    <div className="relative rounded-2xl overflow-hidden border border-emerald-500/15 flex h-[600px] w-full" style={{ background: "#0a0f14" }} data-testid="live-map">
      {/* Sidebar */}
      <aside className={`shrink-0 border-r border-emerald-500/10 flex flex-col transition-all duration-300 ${collapsed ? "w-0 opacity-0" : "w-72 opacity-100"}`} style={{ background: "linear-gradient(180deg, #0b1016, #080b0f)" }} data-testid="map-sidebar">
        <div className="p-4 border-b border-emerald-500/10">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg border border-emerald-500/40 bg-emerald-500/10 flex items-center justify-center"><MapIcon size={17} className="text-emerald-400" /></div>
              <div className="leading-tight">
                <p className="text-[9px] tracking-[0.2em] text-emerald-500/70 font-bold uppercase">La Isla Nublar</p>
                <h3 className="font-display font-extrabold text-base">Gateway</h3>
              </div>
            </div>
            <button onClick={() => setCollapsed(true)} className="p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground" data-testid="map-sidebar-collapse"><ChevronLeft size={16} /></button>
          </div>
          <div className="flex items-center gap-2 mt-3 text-[11px]">
            <span className="inline-flex items-center gap-1.5 text-emerald-400 font-bold"><Radio size={12} className="animate-pulse" /> LIVE</span>
            <span className="text-muted-foreground">· Field tracker active</span>
          </div>
        </div>

        {/* Search */}
        <div className="p-3.5">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar ubicaciones…" data-testid="map-search"
              className="w-full bg-black/40 border border-white/[0.08] rounded-lg pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/40" />
          </div>
        </div>

        {/* Overlays */}
        <div className="px-3.5 pb-2">
          <p className="text-[10px] tracking-[0.18em] text-muted-foreground font-bold uppercase mb-2.5">Capas</p>
          <div className="space-y-2">
            <OverlayRow title="Ubicaciones" sub={`Named POIs · ${MAP_LOCATIONS.length} zones`} on={showLabels} onToggle={() => setShowLabels((v) => !v)} testid="map-toggle-labels" />
            <OverlayRow title="Zonas de Migración" sub={`Official MMZ paths · ${MIGRATION_ZONES.length} zones`} on={showMigration} onToggle={() => setShowMigration((v) => !v)} testid="map-toggle-migration" />
            <OverlayRow title="Zonas de Patrulla" sub={`AI patrullajes · ${PATROL_ZONES.length} points`} on={showPatrol} onToggle={() => setShowPatrol((v) => !v)} testid="map-toggle-patrol" />
            <OverlayRow title="Agua Potable" sub={`Rivers, lakes & wallows · ${WATER_ZONES.length}`} on={showWater} onToggle={() => setShowWater((v) => !v)} testid="map-toggle-water" />
            <OverlayRow title="Criaturas Silvestres" sub={`Posiciones de IA en el mapa · ${aiPositions.length} · actualización lenta (~4 min)`} on={showAi} onToggle={() => setShowAi((v) => !v)} testid="map-toggle-ai" />
          </div>
        </div>

        {/* Location list */}
        <div className="px-3.5 pt-2 pb-1 flex items-center justify-between">
          <p className="text-[10px] tracking-[0.18em] text-muted-foreground font-bold uppercase">Ubicaciones</p>
          <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 rounded px-1.5 py-0.5">{filtered.length}</span>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3" data-testid="map-location-list">
          {filtered.map((l) => (
            <button key={l.name} onClick={() => flyTo(l.name)} data-testid={`map-location-${slug(l.name)}`}
              className="w-full group flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-emerald-500/[0.08] transition-colors text-left">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
              <span className="flex-1 text-sm text-foreground/85 group-hover:text-foreground truncate">{l.name}</span>
              <ChevronRight size={15} className="text-muted-foreground/50 group-hover:text-emerald-400 transition-colors" />
            </button>
          ))}
          {filtered.length === 0 && <p className="text-center text-xs text-muted-foreground py-6">No hay ubicaciones que coincidan.</p>}
        </div>
      </aside>

      {/* Map area */}
      <div className="relative flex-1 min-w-0">
        {collapsed && (
          <button onClick={() => setCollapsed(false)} data-testid="map-sidebar-expand"
            className="absolute top-3 left-3 z-30 glass-strong rounded-lg p-2 hover:bg-white/10"><ChevronRight size={16} /></button>
        )}

        <TransformWrapper ref={wrapperRef} initialScale={1} minScale={1} maxScale={7} centerOnInit
          doubleClick={{ mode: "zoomIn", step: 0.7 }} wheel={{ step: 0.14 }} panning={{ velocityDisabled: true }}>
          {({ zoomIn, zoomOut, resetTransform }) => (
            <>
              <TransformComponent wrapperStyle={{ width: "100%", height: "600px" }} contentStyle={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div className="relative">
                  <img
                    src={mapSrc}
                    onError={() => { if (mapSrc !== MEDIA.gatewayMapFallback) setMapSrc(MEDIA.gatewayMapFallback); }}
                    alt="Mapa de La Isla Nublar" className="block select-none max-h-[600px] w-auto" draggable={false}
                  />

                  {/* Migration zones */}
                  {MIGRATION_ZONES.map((z) => (
                    <div key={z.name} className="absolute pointer-events-none transition-opacity duration-300" style={{
                      left: `${z.x}%`, top: `${z.y}%`, width: `${z.r * 2}%`, aspectRatio: "1", transform: "translate(-50%, -50%)",
                      opacity: showMigration ? 1 : 0, borderRadius: "50%", background: "rgba(16,185,129,0.13)",
                      border: "2px dashed rgba(16,185,129,0.7)", boxShadow: "inset 0 0 30px rgba(16,185,129,0.25)",
                    }}>
                      <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap text-[8px] font-bold uppercase tracking-wide text-emerald-300" style={{ textShadow: "0 1px 3px rgba(0,0,0,0.9)" }}>{z.name}</span>
                    </div>
                  ))}

                  {/* Drinking water */}
                  {WATER_ZONES.map((w) => (
                    <div key={w.name} className="absolute pointer-events-none transition-opacity duration-300 group/water" style={{
                      left: `${w.x}%`, top: `${w.y}%`, width: `${w.r * 2}%`, aspectRatio: "1", transform: "translate(-50%, -50%)",
                      opacity: showWater ? 1 : 0, borderRadius: "50%", background: "radial-gradient(circle, rgba(56,189,248,0.35), rgba(56,189,248,0.12))",
                      border: "1.5px solid rgba(56,189,248,0.65)", boxShadow: "inset 0 0 16px rgba(56,189,248,0.3)",
                    }} data-testid={`map-water-${slug(w.name)}`}>
                      <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-[7px] font-bold uppercase tracking-wide text-sky-200 whitespace-nowrap" style={{ textShadow: "0 1px 3px rgba(0,0,0,0.9)" }}>{w.name}</span>
                    </div>
                  ))}

                  {/* AI Patrol zones */}
                  {PATROL_ZONES.map((p) => (
                    <div key={p.name} ref={(el) => (labelRefs.current[p.name] = el)} data-testid={`map-patrol-${slug(p.name)}`}
                      className="absolute z-[7] pointer-events-none transition-opacity duration-300"
                      style={{ left: `${p.x}%`, top: `${p.y}%`, transform: "translate(-50%, -50%)", opacity: showPatrol ? 1 : 0 }}>
                      <KeepScale>
                        <div className="relative flex items-center justify-center">
                          <span className="absolute w-5 h-5 rounded-full animate-ping" style={{ background: "rgba(245,158,11,0.3)" }} />
                          <span className="relative w-3 h-3 rotate-45 border border-amber-200" style={{ background: "#F59E0B", boxShadow: "0 0 8px rgba(245,158,11,0.8)" }} />
                          <span className="absolute top-full mt-1 whitespace-nowrap text-[7px] font-bold uppercase tracking-wide text-amber-300" style={{ textShadow: "0 1px 3px rgba(0,0,0,0.95)" }}>{p.name}</span>
                        </div>
                      </KeepScale>
                    </div>
                  ))}

                  {/* Location labels — Dino-Den style boxes */}
                  {MAP_LOCATIONS.map((loc) => (
                    <div key={loc.name} ref={(el) => (labelRefs.current[loc.name] = el)} data-testid={`map-label-${slug(loc.name)}`}
                      className="absolute z-[6] pointer-events-none transition-opacity duration-300"
                      style={{ left: `${loc.x}%`, top: `${loc.y}%`, transform: "translate(-50%, -50%)", opacity: showLabels ? 1 : 0 }}>
                      <KeepScale>
                        <div className="inline-flex items-center gap-1.5 rounded-md border border-emerald-500/50 bg-black/75 px-2 py-1 backdrop-blur-sm" style={{ boxShadow: "0 2px 8px rgba(0,0,0,0.5)" }}>
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" style={{ boxShadow: "0 0 6px #10B981" }} />
                          <span className="font-display font-bold text-[10px] uppercase tracking-wide text-white whitespace-nowrap">{loc.name}</span>
                        </div>
                      </KeepScale>
                    </div>
                  ))}

                  {/* AI dinosaur positions — GET /api/ai_positions rows are {species, ue_x, ue_y, ts};
                      species already comes pre-cleaned from the backend (_clean_ai_species). */}
                  {showAi && aiPositions.map((a, i) => {
                    const p = worldToPct(a.ue_x, a.ue_y);
                    if (!p) return null;
                    return (
                      <div key={`ai-${i}`} className="absolute z-[8] group/ai" style={{ left: `${p.left}%`, top: `${p.top}%`, transform: "translate(-50%, -50%)" }} data-testid={`map-ai-dot-${i}`} title={a.species || cleanClassName(a.class)}>
                        <KeepScale>
                          <div className="relative flex flex-col items-center">
                            <AiMarker />
                            <span className="mt-0.5 whitespace-nowrap text-[7px] font-bold uppercase tracking-wide text-purple-300 opacity-0 group-hover/ai:opacity-100 transition-opacity" style={{ textShadow: "0 1px 3px rgba(0,0,0,0.9)" }}>{a.species || cleanClassName(a.class)}</span>
                          </div>
                        </KeepScale>
                      </div>
                    );
                  })}

                  {/* Player marker (self) */}
                  {selfPct && (
                    <div ref={markerRef} className="absolute z-10" style={{ left: `${selfPct.left}%`, top: `${selfPct.top}%`, transform: "translate(-50%, -50%)" }} data-testid="map-marker">
                      <KeepScale>
                        <div className="relative flex items-center justify-center">
                          <span className="absolute w-5 h-5 rounded-full bg-crimson/30 animate-ping" />
                          <CompassMarker />
                        </div>
                      </KeepScale>
                    </div>
                  )}
                </div>
              </TransformComponent>

              {/* Top badge */}
              <span className="absolute top-3 right-3 z-30 text-[10px] tracking-[0.18em] font-bold uppercase glass-strong px-2.5 py-1 rounded-full inline-flex items-center gap-1.5"><MapPin size={11} className="text-emerald-400" /> Gateway · Live</span>

              {/* Zoom + recenter — compact control cluster */}
              <div className="absolute bottom-3 right-3 z-30 flex flex-col items-end gap-1.5">
                <div className="flex flex-col glass-strong rounded-lg overflow-hidden border border-white/10 shadow-lg">
                  <button onClick={() => zoomIn(0.4)} data-testid="map-zoom-in" title="Acercar" className="p-1.5 hover:bg-white/10 text-foreground/80 hover:text-foreground transition-colors border-b border-white/10"><Plus size={14} /></button>
                  <button onClick={() => zoomOut(0.4)} data-testid="map-zoom-out" title="Alejar" className="p-1.5 hover:bg-white/10 text-foreground/80 hover:text-foreground transition-colors border-b border-white/10"><Minus size={14} /></button>
                  <button onClick={() => resetTransform(400)} data-testid="map-reset" title="Restablecer vista" className="p-1.5 hover:bg-white/10 text-foreground/80 hover:text-foreground transition-colors"><Maximize2 size={13} /></button>
                </div>
                <button onClick={recenter} data-testid="map-recenter" title="Centrar en mi dino"
                  className="w-8 h-8 rounded-lg text-white flex items-center justify-center hover:brightness-110 active:scale-95 transition-all"
                  style={{ background: "#10b981", boxShadow: "0 2px 10px rgba(16,185,129,0.45)" }}>
                  <Crosshair size={15} />
                </button>
              </div>

              {/* Coordinates (raw world units) */}
              {selfPct && (
                <div className="absolute bottom-3 left-3 z-30 glass-strong rounded-lg px-3 py-1.5 text-[11px] font-mono text-crimson" data-testid="map-legend">
                  {Math.round(position.x).toLocaleString()}, {Math.round(position.y).toLocaleString()}
                </div>
              )}
            </>
          )}
        </TransformWrapper>
      </div>
    </div>
  );
}
