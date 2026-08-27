import React from "react";

// Prehistoric hanging creepers, drawn as crisp SVG (no image assets). Decorative
// only — always pointer-events-none so they never block clicks.

const LEAF = "#4a6b32";
const LEAF_DARK = "#2f4a20";
const LEAF_LIGHT = "#5f8440";
const STEM = "#3c5526";

// One hanging strand. `len` controls how far it drapes; `x` its horizontal spot.
// NOTE: the sway uses SMIL <animateTransform additive="sum"> so the rotation
// COMPOSES with the translate(x) instead of overriding it. (A CSS `transform`
// animation would override the translate attribute and collapse every strand to
// x=0 — the "all vines bunched on the left" bug.)
function Strand({ x, len, delay = 0, flip = false }) {
  const leaves = [];
  const step = 24;
  for (let y = 18; y < len - 8; y += step) {
    const side = (Math.floor(y / step) % 2 === 0) !== flip ? 1 : -1;
    const light = Math.floor(y / step) % 3 === 0;
    leaves.push(
      <g key={y} transform={`translate(0 ${y}) rotate(${side * 34})`}>
        <ellipse cx={side * 5} cy={0} rx="6.5" ry="3.1" fill={light ? LEAF_LIGHT : side > 0 ? LEAF : LEAF_DARK} />
      </g>
    );
  }
  const dur = 5 + (delay % 3);
  return (
    <g transform={`translate(${x} 0)`}>
      <animateTransform
        attributeName="transform" attributeType="XML" type="rotate" additive="sum"
        values="-2 0 0; 2 0 0; -2 0 0" keyTimes="0; 0.5; 1"
        dur={`${dur}s`} begin={`${delay}s`} repeatCount="indefinite"
      />
      <path d={`M0 0 q ${flip ? 10 : -10} ${len * 0.45} ${flip ? 4 : -4} ${len}`} stroke={STEM} strokeWidth="2.6" fill="none" strokeLinecap="round" />
      {leaves}
      <circle cx={flip ? 4 : -4} cy={len} r="3.2" fill={LEAF_LIGHT} />
    </g>
  );
}

// Full-width hanging canopy for the top of the whole cemetery (pantheon look).
// Strands vary a lot in length so it reads as overgrown, not a flat strip.
export function VineStrip({ className = "", height = 240 }) {
  const strands = [];
  let i = 0;
  for (let x = 20; x <= 1580; x += 46) {
    const seed = (i * 73) % 100;
    const len = 40 + (seed % 5) * 42 + (seed > 70 ? 60 : 0); // 40 .. ~230
    strands.push({ x, len: Math.min(len, height - 8), delay: (i % 7) * 0.35, flip: i % 2 === 0 });
    i += 1;
  }
  return (
    <svg
      className={`pointer-events-none select-none ${className}`}
      viewBox={`0 0 1600 ${height}`} preserveAspectRatio="none"
      width="100%" height={height} aria-hidden
    >
      <line x1="0" y1="5" x2="1600" y2="5" stroke={STEM} strokeWidth="4" opacity="0.75" />
      <line x1="0" y1="10" x2="1600" y2="10" stroke={LEAF_DARK} strokeWidth="2" opacity="0.5" />
      {strands.map((s, k) => <Strand key={k} {...s} />)}
    </svg>
  );
}

// Vertical creeper that climbs a page edge (left/right frame of the pantheon).
export function VineSide({ side = "left", className = "", height = 900 }) {
  const flip = side === "right";
  const leaves = [];
  const step = 34;
  for (let y = 30; y < height - 20; y += step) {
    const dir = Math.floor(y / step) % 2 === 0 ? 1 : -1;
    const light = Math.floor(y / step) % 3 === 0;
    leaves.push(
      <g key={y} transform={`translate(18 ${y}) rotate(${dir * 40})`}>
        <ellipse cx={dir * 8} cy={0} rx="8" ry="3.6" fill={light ? LEAF_LIGHT : dir > 0 ? LEAF : LEAF_DARK} />
      </g>
    );
  }
  return (
    <svg
      className={`pointer-events-none select-none ${className}`}
      style={flip ? { transform: "scaleX(-1)" } : undefined}
      viewBox={`0 0 60 ${height}`} preserveAspectRatio="none"
      width="60" height="100%" aria-hidden
    >
      <path d={`M18 0 q 22 ${height * 0.25} 6 ${height * 0.5} q -16 ${height * 0.25} 8 ${height}`} stroke={STEM} strokeWidth="3" fill="none" strokeLinecap="round" />
      {leaves}
    </svg>
  );
}

// Small corner creeper for card tops.
export function VineCorner({ className = "" }) {
  return (
    <svg className={`pointer-events-none select-none ${className}`} width="66" height="50" viewBox="0 0 66 50" aria-hidden>
      <path d="M2 2 q18 6 28 20 q8 10 6 24" stroke={STEM} strokeWidth="2" fill="none" strokeLinecap="round" />
      <ellipse cx="15" cy="11" rx="5.2" ry="2.6" fill={LEAF} transform="rotate(30 15 11)" />
      <ellipse cx="28" cy="22" rx="5.2" ry="2.6" fill={LEAF_DARK} transform="rotate(-20 28 22)" />
      <ellipse cx="35" cy="37" rx="4.8" ry="2.5" fill={LEAF_LIGHT} transform="rotate(40 35 37)" />
      <circle cx="35" cy="48" r="2.3" fill={LEAF_LIGHT} />
    </svg>
  );
}
