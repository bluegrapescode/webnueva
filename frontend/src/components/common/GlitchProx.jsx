import React from "react";

// A glitch skin's public face. Since the 2026-08-11 fleet order a card carries
// a NAME and a COLOUR PROXIMITY, never a per-skin render — and since
// 2026-08-14 it wears the owner's glitch AURA art behind them (his image, ONE
// shared emblem for the whole family, so it claims nothing about any skin's
// in-game look). The neon pair below is sampled from that art. Why this face
// exists: the era catalog's channels sit at magnitudes the documented fold
// reads as black, so the old strip painted all 13 designs as identical black
// rectangles under the site's olive glow — the exact "palette color for
// glitch skins" complaint (owner via Ishaq, 2026-08-14) this replaces.
// Hexes are validated before they ever touch a style attribute.
const HEX_RE = /^#[0-9a-fA-F]{6}$/;
const safeHex = (h, fallback) => (HEX_RE.test(String(h || "")) ? h : fallback);

const AURA_SRC = "/glitch/aura.webp";
const NEON_MAGENTA = "#E14BEF";
const NEON_CYAN = "#38C7F0";

export function GlitchProx({ proximity, accent, compact = false, className = "" }) {
  const bands = (Array.isArray(proximity) ? proximity : []).map((h) => safeHex(h, "#000000"));
  // The strip stays only where the fold left it any colour to show; the era
  // designs fold all-black and a dead black bar over the art is pure noise.
  const lit = bands.some((h) => h !== "#000000");
  // accent is accepted for API stability with the callers; the glitch family
  // wears its own neon identity now, not the per-surface accent.
  void accent;
  return (
    <div className={`relative h-full w-full overflow-hidden ${className}`}
      style={{ background: "#07070d" }} data-testid="glitch-prox">
      <img src={AURA_SRC} alt="" aria-hidden="true" loading="lazy" draggable={false}
        className="absolute inset-0 h-full w-full object-cover"
        style={{ objectPosition: "center 42%" }} />
      <div className="absolute inset-0 pointer-events-none" style={{
        background: `radial-gradient(ellipse at 18% 108%, ${NEON_MAGENTA}59, transparent 58%), ` +
          `radial-gradient(ellipse at 85% -8%, ${NEON_CYAN}47, transparent 55%)`,
      }} />
      {lit && (
        <div className="absolute inset-x-0 bottom-1 flex h-1.5 gap-px px-1 opacity-90">
          {bands.map((h, i) => (
            <span key={i} className="h-full flex-1 rounded-sm" style={{ background: h }} />
          ))}
        </div>
      )}
      {!compact && (
        <span className="absolute inset-x-0 bottom-0 h-0.5" style={{
          background: `linear-gradient(90deg, ${NEON_MAGENTA}, ${NEON_CYAN})`,
          boxShadow: `0 0 10px ${NEON_MAGENTA}aa`,
        }} />
      )}
    </div>
  );
}

export default GlitchProx;
