import React from "react";

// Sinister, half-dead Halloween creepers drawn as crisp SVG (no image assets).
// Decorative only — always pointer-events-none so they never block clicks.
// The sway uses SMIL <animateTransform additive="sum"> so rotation COMPOSES with
// each strand's translate(x) (a CSS transform would override it and collapse
// every strand to x=0 — the old "bunched on the left" bug).

const STEM = "#26311d";        // withered dark stem
const STEM_DARK = "#141a10";
const THORN = "#39482a";
const LEAF = "#37451f";         // sickly, muted
const LEAF_DEAD = "#4a3717";    // dead brown
const LEAF_TOXIC = "#7bab38";   // eerie toxic highlight
const BERRY = "#8fd94a";        // faint toxic glow berry
const BERRY_BLOOD = "#7d1f1f";  // dried blood berry

// Small thorn triangle pointing outward from the stem.
function Thorn({ y, side }) {
  const s = side * 7;
  return <path d={`M0 ${y} L${s} ${y - 3} L${side * 2} ${y + 3} Z`} fill={THORN} />;
}

// One hanging, half-dead strand with thorns + drooping withered leaves.
function Strand({ x, len, delay = 0, flip = false }) {
  const parts = [];
  const step = 22;
  let idx = 0;
  for (let y = 16; y < len - 6; y += step) {
    const side = (idx % 2 === 0) !== flip ? 1 : -1;
    const kind = idx % 4;
    if (kind === 0) {
      parts.push(<Thorn key={`t${y}`} y={y} side={side} />);
    } else {
      // withered leaf, drooping downward
      const dead = kind === 2;
      const droop = side > 0 ? 55 : 125; // hang down
      parts.push(
        <g key={`l${y}`} transform={`translate(0 ${y}) rotate(${droop})`}>
          <path d={`M0 0 q ${side * 4} 4 ${side * 9} 2 q ${side * -3} 3 ${side * -9} -2 Z`}
                fill={dead ? LEAF_DEAD : idx % 3 === 0 ? LEAF_TOXIC : LEAF} opacity={dead ? 0.85 : 1} />
        </g>
      );
    }
    idx += 1;
  }
  // an occasional glowing berry near the tip
  const berry = (Math.round(x) % 3 === 0);
  const bloody = (Math.round(x) % 5 === 0);
  return (
    <g transform={`translate(${x} 0)`}>
      <animateTransform
        attributeName="transform" attributeType="XML" type="rotate" additive="sum"
        values="-2.2 0 0; 2.2 0 0; -2.2 0 0" keyTimes="0; 0.5; 1"
        dur={`${5 + (delay % 3)}s`} begin={`${delay}s`} repeatCount="indefinite"
      />
      {/* gnarled two-tone stem */}
      <path d={`M0 0 q ${flip ? 11 : -11} ${len * 0.4} ${flip ? 5 : -5} ${len * 0.7} q ${flip ? -6 : 6} ${len * 0.2} ${flip ? 3 : -3} ${len * 0.3}`}
            stroke={STEM_DARK} strokeWidth="3.4" fill="none" strokeLinecap="round" />
      <path d={`M0 0 q ${flip ? 11 : -11} ${len * 0.4} ${flip ? 5 : -5} ${len * 0.7} q ${flip ? -6 : 6} ${len * 0.2} ${flip ? 3 : -3} ${len * 0.3}`}
            stroke={STEM} strokeWidth="1.6" fill="none" strokeLinecap="round" />
      {parts}
      {berry && (
        <circle cx={flip ? 5 : -5} cy={len - 2} r="3"
                fill={bloody ? BERRY_BLOOD : BERRY}
                style={{ filter: `drop-shadow(0 0 4px ${bloody ? "rgba(150,30,30,0.8)" : "rgba(143,217,74,0.85)"})` }} />
      )}
    </g>
  );
}

// Full-width hanging canopy for the top of the whole cemetery (crypt look).
export function VineStrip({ className = "", height = 280 }) {
  const strands = [];
  let i = 0;
  for (let x = 20; x <= 1580; x += 42) {
    const seed = (i * 73) % 100;
    const len = 44 + (seed % 5) * 44 + (seed > 70 ? 66 : 0); // 44 .. ~250
    strands.push({ x, len: Math.min(len, height - 8), delay: (i % 7) * 0.4, flip: i % 2 === 0 });
    i += 1;
  }
  return (
    <svg
      className={`pointer-events-none select-none ${className}`}
      viewBox={`0 0 1600 ${height}`} preserveAspectRatio="none"
      width="100%" height={height} aria-hidden
    >
      {/* gnarled horizontal branch */}
      <line x1="0" y1="6" x2="1600" y2="6" stroke={STEM_DARK} strokeWidth="6" opacity="0.85" />
      <line x1="0" y1="6" x2="1600" y2="6" stroke={STEM} strokeWidth="2.4" opacity="0.7" />
      {strands.map((s, k) => <Strand key={k} {...s} />)}
    </svg>
  );
}

// Vertical creeper that climbs a page edge (crypt frame).
export function VineSide({ side = "left", className = "", height = 900 }) {
  const flip = side === "right";
  const parts = [];
  const step = 32;
  let idx = 0;
  for (let y = 26; y < height - 20; y += step) {
    const dir = idx % 2 === 0 ? 1 : -1;
    if (idx % 3 === 0) {
      parts.push(<path key={`t${y}`} d={`M18 ${y} L${18 + dir * 9} ${y - 4} L${18 + dir * 3} ${y + 4} Z`} fill={THORN} />);
    } else {
      const dead = idx % 2 === 0;
      parts.push(
        <g key={`l${y}`} transform={`translate(18 ${y}) rotate(${dir * 46})`}>
          <path d={`M0 0 q ${dir * 5} 5 ${dir * 11} 2 q ${dir * -4} 4 ${dir * -11} -2 Z`} fill={dead ? LEAF_DEAD : idx % 5 === 0 ? LEAF_TOXIC : LEAF} />
        </g>
      );
    }
    idx += 1;
  }
  return (
    <svg
      className={`pointer-events-none select-none ${className}`}
      style={flip ? { transform: "scaleX(-1)" } : undefined}
      viewBox={`0 0 60 ${height}`} preserveAspectRatio="none"
      width="60" height="100%" aria-hidden
    >
      <path d={`M18 0 q 22 ${height * 0.25} 6 ${height * 0.5} q -16 ${height * 0.25} 8 ${height}`} stroke={STEM_DARK} strokeWidth="4" fill="none" strokeLinecap="round" />
      <path d={`M18 0 q 22 ${height * 0.25} 6 ${height * 0.5} q -16 ${height * 0.25} 8 ${height}`} stroke={STEM} strokeWidth="1.8" fill="none" strokeLinecap="round" />
      {parts}
    </svg>
  );
}

// Sinister corner: a spiderweb + thorny creeper + tiny spider for the card tops.
export function VineCorner({ className = "" }) {
  return (
    <svg className={`pointer-events-none select-none ${className}`} width="72" height="60" viewBox="0 0 72 60" aria-hidden>
      {/* spiderweb radiating from the corner */}
      <g stroke="#5a6b48" strokeWidth="0.7" fill="none" opacity="0.55">
        <line x1="1" y1="1" x2="30" y2="6" />
        <line x1="1" y1="1" x2="24" y2="24" />
        <line x1="1" y1="1" x2="6" y2="30" />
        <path d="M14 3 Q10 10 3 14" />
        <path d="M22 5 Q15 16 5 22" />
        <path d="M30 6 Q20 22 6 30" />
      </g>
      {/* thorny withered creeper */}
      <path d="M2 2 q20 5 30 22 q7 11 5 30" stroke={STEM} strokeWidth="2" fill="none" strokeLinecap="round" />
      <path d="M20 15 l6 -3 l-1 6 Z" fill={THORN} />
      <ellipse cx="30" cy="26" rx="5" ry="2.4" fill={LEAF_DEAD} transform="rotate(40 30 26)" />
      <ellipse cx="36" cy="42" rx="4.6" ry="2.3" fill={LEAF} transform="rotate(50 36 42)" />
      <circle cx="36" cy="55" r="2.3" fill={BERRY} style={{ filter: "drop-shadow(0 0 3px rgba(143,217,74,0.8))" }} />
      {/* tiny spider on a thread */}
      <line x1="52" y1="0" x2="52" y2="16" stroke="#5a6b48" strokeWidth="0.7" opacity="0.6" />
      <g transform="translate(52 18)">
        <ellipse cx="0" cy="0" rx="2.6" ry="3.2" fill="#0e130a" />
        <g stroke="#0e130a" strokeWidth="0.8">
          <path d="M-2 -1 L-6 -3 M-2 1 L-6 3 M2 -1 L6 -3 M2 1 L6 3" />
        </g>
      </g>
    </svg>
  );
}


// Fixed, subtle spiderweb anchored in a page corner. `corner`: tl | tr | bl | br.
export function CornerWeb({ corner = "tl", size = 150, className = "" }) {
  const flip = { tl: "none", tr: "scaleX(-1)", bl: "scaleY(-1)", br: "scale(-1,-1)" }[corner];
  const anchors = [0, 20, 42, 66, 90]; // degrees from the corner
  const rad = (d) => (d * Math.PI) / 180;
  const radials = anchors.map((a) => {
    const x = 2 + size * Math.cos(rad(a));
    const y = 2 + size * Math.sin(rad(a));
    return `M2 2 L${x.toFixed(1)} ${y.toFixed(1)}`;
  });
  // sagging threads between adjacent radials at a few radii
  const rings = [0.34, 0.58, 0.82].map((f) => {
    const r = size * f;
    let d = "";
    for (let i = 0; i < anchors.length - 1; i++) {
      const a0 = rad(anchors[i]), a1 = rad(anchors[i + 1]);
      const x0 = 2 + r * Math.cos(a0), y0 = 2 + r * Math.sin(a0);
      const x1 = 2 + r * Math.cos(a1), y1 = 2 + r * Math.sin(a1);
      const am = rad((anchors[i] + anchors[i + 1]) / 2);
      const cx = 2 + r * 0.82 * Math.cos(am), cy = 2 + r * 0.82 * Math.sin(am); // sag toward corner
      d += `M${x0.toFixed(1)} ${y0.toFixed(1)} Q${cx.toFixed(1)} ${cy.toFixed(1)} ${x1.toFixed(1)} ${y1.toFixed(1)} `;
    }
    return d;
  });
  return (
    <svg
      className={`pointer-events-none select-none ${className}`}
      style={{ transform: flip }}
      width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden
    >
      <g stroke="#6b7a58" strokeWidth="0.8" fill="none" opacity="0.7">
        {radials.map((d, i) => <path key={`r${i}`} d={d} />)}
        {rings.map((d, i) => <path key={`c${i}`} d={d} opacity={0.85 - i * 0.12} />)}
      </g>
      {/* a couple of broken/dangling silk threads */}
      <g stroke="#6b7a58" strokeWidth="0.7" fill="none" opacity="0.4">
        <path d={`M${(size * 0.5).toFixed(0)} 2 q6 ${(size * 0.2).toFixed(0)} -2 ${(size * 0.34).toFixed(0)}`} />
        <path d={`M2 ${(size * 0.5).toFixed(0)} q${(size * 0.2).toFixed(0)} 6 ${(size * 0.32).toFixed(0)} -2`} />
      </g>
    </svg>
  );
}
