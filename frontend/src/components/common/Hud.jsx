import React from "react";

// L-shaped corner brackets for the "dossier" HUD look. Place inside a relative container.
export function HudCorners({ color = "rgba(52,211,153,0.7)", size = 16, thickness = 2 }) {
  const base = "absolute pointer-events-none z-20";
  const s = { width: size, height: size, borderColor: color, borderWidth: 0 };
  return (
    <>
      <span className={base} style={{ ...s, top: -1, left: -1, borderTopWidth: thickness, borderLeftWidth: thickness }} />
      <span className={base} style={{ ...s, top: -1, right: -1, borderTopWidth: thickness, borderRightWidth: thickness }} />
      <span className={base} style={{ ...s, bottom: -1, left: -1, borderBottomWidth: thickness, borderLeftWidth: thickness }} />
      <span className={base} style={{ ...s, bottom: -1, right: -1, borderBottomWidth: thickness, borderRightWidth: thickness }} />
    </>
  );
}

// Faint tech grid background. Place inside a relative container as an absolute layer.
export function HudGrid({ color = "rgba(52,211,153,0.06)", cell = 26 }) {
  return (
    <div className="absolute inset-0 pointer-events-none" style={{
      backgroundImage: `linear-gradient(${color} 1px, transparent 1px), linear-gradient(90deg, ${color} 1px, transparent 1px)`,
      backgroundSize: `${cell}px ${cell}px`,
    }} />
  );
}

// Segmented flat stat bar (dashed track + glowing solid fill).
export function SegBar({ value = 0, max = 100, color = "#34D399", height = 8 }) {
  const pct = Math.max(0, Math.min((value / max) * 100, 100));
  return (
    <div className="relative w-full overflow-hidden bg-white/[0.04]" style={{ height }}>
      <div className="absolute inset-0 opacity-40" style={{ backgroundImage: "repeating-linear-gradient(90deg, transparent 0, transparent 6px, rgba(255,255,255,0.14) 6px, rgba(255,255,255,0.14) 7px)" }} />
      <div className="absolute inset-y-0 left-0 transition-[width] duration-500" style={{ width: `${pct}%`, background: color, boxShadow: `0 0 8px ${color}` }} />
    </div>
  );
}

// Pulsing online/offline status indicator. Green = online/alive, red = offline/dead.
export function StatusDot({ online = true, size = 8, label, testid, className = "" }) {
  const color = online ? "#34D399" : "#E24A4A";
  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`} data-testid={testid}>
      <span className="relative flex" style={{ height: size, width: size }}>
        <span className="animate-ping absolute inline-flex rounded-full opacity-75" style={{ height: size, width: size, background: color }} />
        <span className="relative inline-flex rounded-full" style={{ height: size, width: size, background: color, boxShadow: `0 0 6px ${color}` }} />
      </span>
      {label && <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color }}>{label}</span>}
    </span>
  );
}
