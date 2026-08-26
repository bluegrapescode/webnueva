import React from "react";

const FX_CLASS = {
  glow: "fx-glow", neon: "fx-neon", pulse: "fx-pulse", shimmer: "fx-shimmer",
  fire: "fx-fire", gradient: "fx-gradient", rainbow: "fx-rainbow",
};

// Build className + inline style for a name from a resolved cosmetics object
// { color, border, effect, font, chat_bg } (any may be null).
export function buildNameStyle(cos) {
  let className = "";
  const style = {};
  const color = cos?.color, effect = cos?.effect, font = cos?.font;
  if (font?.value) style.fontFamily = font.value;
  if (color) {
    if (color.gradient) {
      className += " deco-color-grad" + (color.animated ? " deco-color-anim" : "");
      style["--deco-grad"] = color.gradient;
    } else if (color.value) {
      style.color = color.value;
    }
  }
  if (effect) {
    className += " " + (FX_CLASS[effect.kind] || "");
    if (effect.color) style["--fx"] = effect.color;
    if (effect.colors) style["--fx-grad"] = `linear-gradient(90deg, ${effect.colors.join(",")})`;
  }
  return { className: className.trim(), style };
}

// Background style for a chat message row from cos.chat_bg.
export function buildBgStyle(cos) {
  const bg = cos?.chat_bg;
  if (!bg?.value) return { className: "", style: {} };
  return { className: bg.animated ? "deco-bg-anim" : "", style: { background: bg.value } };
}

// A player name with color + effect + font applied.
export function DecoName({ cosmetics, children, className = "", baseStyle = {} }) {
  const { className: c, style } = buildNameStyle(cosmetics);
  return <span className={`deco-name ${c} ${className}`} style={{ ...baseStyle, ...style }}>{children}</span>;
}

// Avatar with an optional decorative border (solid, glowing or gradient/animated ring).
export function DecoAvatar({ src, cosmetics, size = 36, ringColor = "rgba(255,255,255,0.08)", testid }) {
  const border = cosmetics?.border;
  const px = { width: size, height: size };
  if (border?.gradient) {
    return (
      <span className={`inline-block rounded-full shrink-0 ${border.animated ? "deco-ring-anim" : ""}`}
        style={{ ...px, background: border.gradient, padding: 2 }} data-testid={testid}>
        <img src={src || "/favicon.ico"} alt="" className="w-full h-full rounded-full object-cover" style={{ background: "#0a0a0c" }} />
      </span>
    );
  }
  const c = border?.value || ringColor;
  const shadow = border?.glow ? `0 0 0 2px ${c}, 0 0 10px ${c}` : `0 0 0 2px ${c}`;
  return <img src={src || "/favicon.ico"} alt="" className="rounded-full object-cover shrink-0" style={{ ...px, boxShadow: shadow }} data-testid={testid} />;
}

// A small representative preview of a single decoration item (used on catalog cards & reels).
export function DecoPreview({ item, size = 64 }) {
  const cat = item.category;
  if (cat === "emote") {
    return <span style={{ fontSize: size * 0.6, lineHeight: 1 }}>{item.emote}</span>;
  }
  if (cat === "font") {
    return <span style={{ fontFamily: item.value, fontSize: size * 0.5, fontWeight: 700 }} className="text-foreground">Aa</span>;
  }
  if (cat === "color") {
    return <DecoName cosmetics={{ color: item }} className="font-display font-extrabold" baseStyle={{ fontSize: size * 0.32 }}>Jugador</DecoName>;
  }
  if (cat === "effect") {
    return <DecoName cosmetics={{ effect: item }} className="font-display font-extrabold text-foreground" baseStyle={{ fontSize: size * 0.32 }}>Jugador</DecoName>;
  }
  if (cat === "border") {
    return <DecoAvatar src="/favicon.ico" cosmetics={{ border: item }} size={size * 0.7} />;
  }
  if (cat === "chat_bg") {
    return (
      <div className={`w-full px-2 py-1.5 rounded ${item.animated ? "deco-bg-anim" : ""}`} style={{ background: item.value }}>
        <span className="text-[10px] font-semibold text-foreground/90">Mensaje de ejemplo</span>
      </div>
    );
  }
  return null;
}
