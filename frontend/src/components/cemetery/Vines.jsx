import React from "react";

// Prehistoric hanging creepers, drawn as crisp SVG (no image assets). Decorative
// only — always pointer-events-none so they never block clicks.

const LEAF = "#4a6b32";
const LEAF_DARK = "#2f4a20";
const STEM = "#3c5526";

// One hanging strand. `len` controls how far it drapes; `x` its horizontal spot.
function Strand({ x, len, delay = 0, flip = false }) {
  const leaves = [];
  const step = 26;
  for (let y = 22; y < len - 8; y += step) {
    const side = (Math.floor(y / step) % 2 === 0) ^ flip ? 1 : -1;
    leaves.push(
      <g key={y} transform={`translate(0 ${y}) rotate(${side * 32})`}>
        <ellipse cx={side * 5} cy={0} rx="6.5" ry="3.2" fill={side > 0 ? LEAF : LEAF_DARK} />
      </g>
    );
  }
  return (
    <g transform={`translate(${x} 0)`} style={{ animation: `vineSway 6s ease-in-out ${delay}s infinite`, transformOrigin: `${x}px 0px` }}>
      <path d={`M0 0 q ${flip ? 8 : -8} ${len * 0.4} 0 ${len}`} stroke={STEM} strokeWidth="2.4" fill="none" strokeLinecap="round" />
      {leaves}
      <circle cx="0" cy={len} r="3" fill={LEAF} />
    </g>
  );
}

// Horizontal strip of hanging creepers for the top edge of a section.
export function VineStrip({ className = "", height = 130 }) {
  const strands = [
    { x: 40, len: 96, delay: 0 }, { x: 130, len: 64, delay: 0.6, flip: true },
    { x: 230, len: 118, delay: 0.2 }, { x: 340, len: 74, delay: 0.9, flip: true },
    { x: 460, len: 104, delay: 0.4 }, { x: 560, len: 58, delay: 1.1, flip: true },
    { x: 680, len: 126, delay: 0.1 }, { x: 800, len: 80, delay: 0.7, flip: true },
    { x: 910, len: 100, delay: 0.35 }, { x: 1010, len: 62, delay: 1.0, flip: true },
    { x: 1120, len: 112, delay: 0.5 }, { x: 1220, len: 70, delay: 0.85, flip: true },
  ];
  return (
    <svg
      className={`pointer-events-none select-none ${className}`}
      viewBox={`0 0 1280 ${height}`} preserveAspectRatio="none"
      width="100%" height={height} aria-hidden
    >
      <line x1="0" y1="6" x2="1280" y2="6" stroke={STEM} strokeWidth="3" opacity="0.7" />
      {strands.map((s, i) => <Strand key={i} {...s} />)}
    </svg>
  );
}

// Small corner creeper for card tops.
export function VineCorner({ className = "" }) {
  return (
    <svg className={`pointer-events-none select-none ${className}`} width="70" height="54" viewBox="0 0 70 54" aria-hidden>
      <path d="M2 2 q18 6 30 22 q8 11 6 26" stroke={STEM} strokeWidth="2" fill="none" strokeLinecap="round" />
      <ellipse cx="16" cy="12" rx="5.5" ry="2.8" fill={LEAF} transform="rotate(30 16 12)" />
      <ellipse cx="30" cy="24" rx="5.5" ry="2.8" fill={LEAF_DARK} transform="rotate(-20 30 24)" />
      <ellipse cx="38" cy="40" rx="5" ry="2.6" fill={LEAF} transform="rotate(40 38 40)" />
      <circle cx="38" cy="52" r="2.4" fill={LEAF} />
    </svg>
  );
}
