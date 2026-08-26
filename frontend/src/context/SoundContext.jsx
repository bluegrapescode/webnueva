import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { SOUNDS } from "@/lib/sounds";

const SoundContext = createContext(null);

export function SoundProvider({ children }) {
  const [enabled, setEnabled] = useState(() => {
    const v = localStorage.getItem("primal_sound");
    return v === null ? true : v === "true";
  });
  const lastHover = useRef(0);

  useEffect(() => {
    localStorage.setItem("primal_sound", String(enabled));
  }, [enabled]);

  const play = useCallback((name, ...args) => {
    if (!enabled) return;
    // Throttle hover so the global listener and per-component handlers never stack.
    if (name === "hover") {
      const now = performance.now();
      if (now - lastHover.current < 90) return;
      lastHover.current = now;
    }
    try { SOUNDS[name]?.(...args); } catch (e) { /* noop */ }
  }, [enabled]);

  const toggle = useCallback(() => setEnabled((e) => !e), []);

  // Global hover sound for every interactive element (buttons, links, role=button).
  useEffect(() => {
    if (!enabled) return;
    let lastEl = null;
    const onOver = (e) => {
      const t = e.target;
      const el = t && t.closest ? t.closest('button, a[href], [role="button"], input[type="checkbox"], select, [data-hover-sound]') : null;
      if (!el || el === lastEl) return;
      if (el.disabled || el.getAttribute("aria-disabled") === "true") return;
      lastEl = el;
      play("hover");
    };
    const onOut = (e) => {
      if (lastEl && (!e.relatedTarget || !lastEl.contains(e.relatedTarget))) lastEl = null;
    };
    document.addEventListener("pointerover", onOver, true);
    document.addEventListener("pointerout", onOut, true);
    return () => {
      document.removeEventListener("pointerover", onOver, true);
      document.removeEventListener("pointerout", onOut, true);
    };
  }, [enabled, play]);

  return (
    <SoundContext.Provider value={{ enabled, toggle, play }}>
      {children}
    </SoundContext.Provider>
  );
}

export const useSound = () => useContext(SoundContext);
