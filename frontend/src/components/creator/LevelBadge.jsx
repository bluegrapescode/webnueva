import React from "react";

export function LevelBadge({ level, size = "md", showLabel = true }) {
  if (!level) return null;
  const sz = size === "sm" ? "text-[9px] px-2 py-0.5" : size === "lg" ? "text-xs px-3 py-1.5" : "text-[10px] px-2.5 py-1";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border font-black tracking-widest uppercase ${sz}`}
      style={{ borderColor: level.color + "55", background: level.color + "18", color: level.color }}
      data-testid={`creator-level-${level.key}`}
    >
      <span aria-hidden>{level.medal}</span>
      {showLabel && <span>{level.label}</span>}
    </span>
  );
}
