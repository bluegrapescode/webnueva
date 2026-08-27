import React, { useEffect } from "react";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";

// Full-screen resurrection sequence: the fossil cracks & dissolves while the dino
// materializes from a burst of toxic-green particles. Auto-dismisses.
export default function ResurrectionFX({ dino, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3000);
    return () => clearTimeout(t);
  }, [onDone]);

  const particles = Array.from({ length: 26 });
  const G = "#8fd94a";

  return (
    <motion.div
      data-testid="resurrection-fx"
      className="fixed inset-0 z-[200] flex items-center justify-center overflow-hidden cursor-pointer"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={onDone}
    >
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" />
      {/* radial glow */}
      <motion.div className="absolute rounded-full"
        style={{ width: 520, height: 520, background: `radial-gradient(circle, ${G}33 0%, ${G}11 40%, transparent 70%)` }}
        initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: [0.4, 1.2, 1], opacity: [0, 0.9, 0.7] }}
        transition={{ duration: 1.6, ease: "easeOut" }} />
      {/* shockwave ring */}
      <motion.div className="absolute rounded-full border-2"
        style={{ borderColor: G }}
        initial={{ width: 60, height: 60, opacity: 0.8 }}
        animate={{ width: 620, height: 620, opacity: 0 }}
        transition={{ duration: 1.1, delay: 0.7, ease: "easeOut" }} />

      <div className="relative flex flex-col items-center">
        <div className="relative w-64 h-64 flex items-center justify-center">
          {/* fossil dissolving */}
          <motion.img src="/fossil.png" alt="Fósil"
            className="absolute w-44 object-contain"
            initial={{ opacity: 1, scale: 1, filter: "brightness(1)" }}
            animate={{ opacity: [1, 1, 0], scale: [1, 1.06, 0.7], rotate: [0, -3, 4, 0], filter: ["brightness(1)", "brightness(1.8)", "brightness(2.4)"] }}
            transition={{ duration: 1.2, times: [0, 0.6, 1] }} />
          {/* dino materializing */}
          {dino?.image && (
            <motion.img src={dino.image} alt={dino.species_name}
              className="absolute w-52 object-contain"
              style={{ filter: `drop-shadow(0 0 22px ${G}) drop-shadow(0 10px 18px rgba(0,0,0,0.6))` }}
              initial={{ opacity: 0, scale: 0.5, y: 10 }}
              animate={{ opacity: [0, 0, 1], scale: [0.5, 0.5, 1], y: [10, 10, 0] }}
              transition={{ duration: 1.6, delay: 0.5, times: [0, 0.35, 1], ease: "easeOut" }} />
          )}
          {/* particles */}
          {particles.map((_, i) => {
            const ang = (i / particles.length) * Math.PI * 2;
            const dist = 90 + Math.random() * 120;
            const dx = Math.cos(ang) * dist;
            const dy = Math.sin(ang) * dist;
            return (
              <motion.span key={i} className="absolute rounded-full"
                style={{ width: 4 + Math.random() * 5, height: 4 + Math.random() * 5, background: G, boxShadow: `0 0 6px ${G}` }}
                initial={{ x: 0, y: 0, opacity: 0 }}
                animate={{ x: dx, y: dy, opacity: [0, 1, 0], scale: [1, 0.5] }}
                transition={{ duration: 1.4, delay: 0.6 + Math.random() * 0.3, ease: "easeOut" }} />
            );
          })}
        </div>
        <motion.div className="mt-2 text-center"
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.3, duration: 0.5 }}>
          <div className="inline-flex items-center gap-2 text-[#A3C96B] text-sm font-semibold uppercase tracking-widest">
            <Sparkles size={16} /> Resucitado
          </div>
          <h2 className="mt-1 text-3xl font-black text-white">{dino?.species_name}</h2>
          <p className="mt-1 text-xs text-white/45">Devuelto a tu bóveda con todos sus stats</p>
        </motion.div>
      </div>
    </motion.div>
  );
}
