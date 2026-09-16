import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import { Skull, Droplet, X, ChevronRight } from "lucide-react";
import { useBounty } from "@/context/BountyContext";
import { useSound } from "@/context/SoundContext";
import { MEDIA } from "@/lib/media";
import { fmtNum, fmtCountdown, dinoGlyph, featuredBounty } from "@/lib/bountyMeta";

// Widget flotante global: muestra el bounty más jugoso del tablón en toda la web.
export function BountyWidget() {
  const location = useLocation();
  const navigate = useNavigate();
  const { play } = useSound();
  const { board, lastEvent } = useBounty();
  const [dismissed, setDismissed] = useState(null);
  const [, tick] = useState(0);

  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { if (lastEvent && (lastEvent.event === "bounty:contract_new" || lastEvent.event === "bounty:self_started")) play("bountyAlert"); }, [lastEvent, play]);

  if (location.pathname.startsWith("/bounty")) return null;

  const b = featuredBounty(board);
  const key = b && (b.bountyId || b.targetId);
  const show = b && dismissed !== key;
  const isSelf = b && b.type === "self";

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key={key}
          initial={{ opacity: 0, x: -30, scale: 0.9 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: -30, scale: 0.9 }}
          transition={{ type: "spring", stiffness: 260, damping: 22 }}
          className="fixed bottom-5 left-5 z-[70] w-[290px]"
          data-testid="bounty-widget"
        >
          <div
            className="relative rounded-xl border overflow-hidden cursor-pointer group"
            style={{ background: isSelf ? "linear-gradient(150deg, #1a0a06, #0b0b0d 70%)" : "linear-gradient(150deg, #1a0709, #0b0b0d 70%)", borderColor: isSelf ? "rgba(240,180,41,0.5)" : "rgba(225,29,42,0.5)", boxShadow: `0 0 40px -14px ${isSelf ? "rgba(240,180,41,0.6)" : "rgba(225,29,42,0.6)"}` }}
            onClick={() => { play("click"); navigate("/bounty"); }}
          >
            <div className="absolute inset-0 pointer-events-none bounty-scan opacity-25" />
            <button data-testid="bounty-widget-close" onClick={(e) => { e.stopPropagation(); setDismissed(key); }} className="absolute top-1.5 right-1.5 z-10 p-1 rounded text-white/40 hover:text-white/80"><X className="w-3.5 h-3.5" /></button>
            <div className="relative flex items-center gap-3 p-3.5">
              <div className="relative w-12 h-12 shrink-0 rounded-full flex items-center justify-center" style={{ background: `radial-gradient(circle, ${isSelf ? "rgba(240,180,41,0.22)" : "rgba(225,29,42,0.22)"}, transparent 70%)`, border: `1px solid ${isSelf ? "rgba(240,180,41,0.35)" : "rgba(225,29,42,0.35)"}` }}><span className="text-2xl">{dinoGlyph(b.slug)}</span></div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  {isSelf ? <Droplet className="w-3 h-3 text-[#F0B429]" /> : <Skull className="w-3 h-3 text-[#E11D2A]" />}
                  <span className="text-[9px] font-bold uppercase tracking-[0.22em]" style={{ color: isSelf ? "#F0B429" : "#E11D2A" }}>{isSelf ? "Precio a su cabeza" : "Bounty activo"}</span>
                  <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: isSelf ? "#F0B429" : "#E11D2A" }} />
                </div>
                <p className="text-sm font-bold text-white truncate mt-0.5">{b.targetName}</p>
                <p className="text-[10px] text-white/45 truncate flex items-center gap-1">
                  {isSelf ? <>🥩 {fmtNum(b.primePerMin)}/min · {fmtCountdown(b.endsAt)}</> : <>🥩 {fmtNum(b.reward.primeMeat)}{b.reward.amberium > 0 && <> · <img src={MEDIA.coinVip} alt="" className="w-3 h-3 inline" /> {fmtNum(b.reward.amberium)}</>}</>}
                </p>
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
