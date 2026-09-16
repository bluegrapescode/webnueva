import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import { Skull, X, ChevronRight } from "lucide-react";
import { useBountySocket } from "@/hooks/useBountySocket";
import { useSound } from "@/context/SoundContext";
import { fmtNum, fmtCountdown, dinoGlyph } from "@/lib/bountyMeta";

// Widget flotante global: aparece en toda la web cuando hay un bounty activo /
// suspendido, y brevemente al completarse. Clic -> página /bounty.
export function BountyWidget() {
  const location = useLocation();
  const navigate = useNavigate();
  const { play } = useSound();
  const [dismissed, setDismissed] = useState(null);        // bountyId descartado
  const [flash, setFlash] = useState(false);
  const [, tick] = useState(0);

  const { snapshot, lastEvent } = useBountySocket((event) => {
    if (event === "bounty:new") { setFlash(true); play("bountyAlert"); setTimeout(() => setFlash(false), 2200); }
    if (event === "bounty:completed") play("bountyComplete");
    if (event === "bounty:target_disconnected") play("bountyDisconnect");
  });

  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // No mostrar en las páginas dedicadas del bounty.
  if (location.pathname.startsWith("/bounty")) return null;

  const b = snapshot && snapshot.bounty;
  const active = b && (b.status === "active" || b.status === "suspended");
  const completed = b && b.status === "completed";
  const nextMs = completed && b.nextAt ? Date.parse(b.nextAt) : 0;

  const show = (active && dismissed !== b.bountyId) || (completed && flash);
  const suspended = b && b.status === "suspended";

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key={b.bountyId + b.status}
          initial={{ opacity: 0, x: -30, scale: 0.9 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={{ opacity: 0, x: -30, scale: 0.9 }}
          transition={{ type: "spring", stiffness: 260, damping: 22 }}
          className="fixed bottom-5 left-5 z-[70] w-[290px] pointer-events-auto"
          data-testid="bounty-widget"
        >
          <div
            className="relative rounded-xl border overflow-hidden cursor-pointer group"
            style={{
              background: "linear-gradient(150deg, #1a0709 0%, #0b0b0d 70%)",
              borderColor: suspended ? "rgba(240,180,41,0.45)" : "rgba(225,29,42,0.5)",
              boxShadow: "0 0 40px -14px rgba(225,29,42,0.6)",
            }}
            onClick={() => { play("click"); navigate("/bounty"); }}
          >
            {active && <div className="absolute inset-0 pointer-events-none bounty-scan opacity-30" />}
            <button
              data-testid="bounty-widget-close"
              onClick={(e) => { e.stopPropagation(); setDismissed(b.bountyId); }}
              className="absolute top-1.5 right-1.5 z-10 p-1 rounded text-white/40 hover:text-white/80"
            >
              <X className="w-3.5 h-3.5" />
            </button>

            <div className="relative flex items-center gap-3 p-3.5">
              <div className="relative w-12 h-12 shrink-0 rounded-full flex items-center justify-center"
                style={{ background: "radial-gradient(circle, rgba(225,29,42,0.22), transparent 70%)", border: "1px solid rgba(225,29,42,0.35)" }}>
                <span className="text-2xl">{dinoGlyph(b.slug)}</span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <Skull className="w-3 h-3" style={{ color: suspended ? "#F0B429" : "#E11D2A" }} />
                  <span className="text-[9px] font-bold uppercase tracking-[0.22em]" style={{ color: suspended ? "#F0B429" : "#E11D2A" }}>
                    {completed ? "Completado" : suspended ? "Desconectado" : "Bounty Activo"}
                  </span>
                  {active && !suspended && <span className="w-1.5 h-1.5 rounded-full bg-[#E11D2A] animate-pulse" />}
                </div>
                <p className="text-sm font-bold text-white truncate mt-0.5">
                  {completed ? b.killerName : b.targetName}
                </p>
                <p className="text-[10px] text-white/45 truncate">
                  {completed ? `eliminó a ${b.targetName}` : `${b.dinosaur} · 🟠 ${fmtNum(b.rewards.amberium)}`}
                </p>
                {completed && nextMs > 0 && (
                  <p className="text-[10px] text-white/40 mt-0.5">Nuevo en {fmtCountdown(nextMs)}</p>
                )}
              </div>
              <ChevronRight className="w-4 h-4 text-white/30 group-hover:text-white/60 transition-colors shrink-0" />
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default BountyWidget;
