import React, { useEffect, useState } from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";

// Soft glow that follows the cursor (desktop only).
export function MouseGlow() {
  const [visible, setVisible] = useState(false);
  const x = useMotionValue(-200);
  const y = useMotionValue(-200);
  const sx = useSpring(x, { stiffness: 120, damping: 20, mass: 0.4 });
  const sy = useSpring(y, { stiffness: 120, damping: 20, mass: 0.4 });

  useEffect(() => {
    if (window.matchMedia("(pointer: coarse)").matches) return;
    const move = (e) => { x.set(e.clientX - 250); y.set(e.clientY - 250); setVisible(true); };
    window.addEventListener("mousemove", move);
    return () => window.removeEventListener("mousemove", move);
  }, [x, y]);

  return (
    <motion.div
      aria-hidden
      className="fixed top-0 left-0 z-0 pointer-events-none rounded-full"
      style={{
        x: sx, y: sy, width: 500, height: 500,
        background: "radial-gradient(circle, rgba(124, 168, 66,0.08), transparent 60%)",
        opacity: visible ? 1 : 0,
      }}
    />
  );
}
