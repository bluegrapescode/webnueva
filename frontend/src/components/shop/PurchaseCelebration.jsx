import React, { useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { rarityOf } from "./shopRarity";

// Full-screen golden celebration when a skin is acquired. Auto-dismisses.
export function PurchaseCelebration({ skin, onDone, play }) {
  const r = rarityOf(skin?.rarity);
  const particles = useMemo(
    () => Array.from({ length: 30 }).map((_, i) => ({
      id: i,
      angle: (i / 30) * Math.PI * 2,
      dist: 120 + Math.random() * 260,
      size: 4 + Math.random() * 8,
      delay: Math.random() * 0.25,
    })),
    [skin?.id]
  );

  useEffect(() => {
    if (!skin) return;
    play?.("skinUnlocked");
    const t = setTimeout(() => onDone?.(), 4200);
    return () => clearTimeout(t);
  }, [skin, onDone, play]);

  return (
    <AnimatePresence>
      {skin && (
        <motion.div
          className="fixed inset-0 z-[200] flex items-center justify-center overflow-hidden"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          data-testid="purchase-celebration"
          onClick={() => onDone?.()}
        >
          <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" />
          <motion.div
            className="absolute inset-0"
            initial={{ opacity: 0 }} animate={{ opacity: [0, 0.8, 0] }} transition={{ duration: 0.7 }}
            style={{ background: `radial-gradient(circle at 50% 45%, ${r.color}88, transparent 60%)` }}
          />
          {particles.map((p) => (
            <motion.span key={p.id}
              className="absolute rounded-full"
              style={{ width: p.size, height: p.size, background: r.color, left: "50%", top: "45%" }}
              initial={{ x: 0, y: 0, opacity: 1 }}
              animate={{ x: Math.cos(p.angle) * p.dist, y: Math.sin(p.angle) * p.dist, opacity: 0 }}
              transition={{ duration: 1.6, delay: p.delay, ease: "easeOut" }}
            />
          ))}
          <motion.div
            className="relative text-center px-6"
            initial={{ scale: 0.6, y: 30 }} animate={{ scale: 1, y: 0 }} transition={{ type: "spring", stiffness: 220, damping: 16 }}
          >
            <motion.div
              className="mx-auto w-52 h-52 rounded-2xl overflow-hidden border-2 mb-5"
              style={{ borderColor: r.color, boxShadow: `0 0 60px ${r.color}` }}
              animate={{ y: [0, -8, 0] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            >
              <img src={skin.image_url} alt={skin.name} className="w-full h-full object-cover" />
            </motion.div>
            <p className="label-overline text-xs" style={{ color: r.color }}>¡Skin desbloqueada!</p>
            <h2 className="font-display font-extrabold text-4xl tracking-tight mt-1">{skin.name}</h2>
            <p className="text-white/45 text-sm mt-3">Toca para continuar</p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
