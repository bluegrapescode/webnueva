import React, { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { MEDIA } from "@/lib/media";
import { LoginGift } from "@/components/common/LoginGift";
import { usePayoutTimer } from "@/hooks/usePayoutTimer";

const fmt = (n) => Number(n || 0).toLocaleString();

// Top-right currency balances. Each currency is its own bordered pill so large
// numbers (millions) never collide. PrimeMeat carries a passive-earn progress bar.
export function BalanceHUD() {
  const { user, refresh, applyBalance } = useAuth();
  const [remaining, setRemaining] = useState(240);
  const [span, setSpan] = useState(240);
  const [inGame, setInGame] = useState(false);
  const pollRef = useRef(null);
  const fillRef = useRef(null);
  const timeRef = useRef(null);
  const lastSec = useRef(-1);

  useEffect(() => {
    if (!user) return;
    let mounted = true;
    const tick = async () => {
      try {
        const { data } = await api.passiveTick();
        if (!mounted) return;
        setInGame(data.in_game);
        setSpan(data.interval_seconds || 240);
        setRemaining(data.seconds_remaining ?? 240);
        // Reflect passive earnings on the PrimeMeat bar INSTANTLY from the tick's own
        // authoritative balance; fall back to a full re-sync if it omits coins.
        if (typeof data.coins === "number") applyBalance({ coins: data.coins });
        else if (data.awarded > 0) refresh?.();
      } catch { /* ignore transient poll errors */ }
    };
    tick();
    pollRef.current = setInterval(tick, 20000);
    return () => { mounted = false; clearInterval(pollRef.current); };
    // eslint-disable-next-line
  }, [user?.id]);

  // Continuous rAF fill + mm:ss counter, kept in sync with the payout panel.
  usePayoutTimer({
    secondsRemaining: remaining,
    intervalSeconds: span,
    active: inGame,
    onTick: (rem, progress) => {
      if (fillRef.current) fillRef.current.style.width = `${Math.max(progress * 100, 4)}%`;
      const s = Math.ceil(rem);
      if (s !== lastSec.current && timeRef.current) {
        lastSec.current = s;
        timeRef.current.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
      }
    },
  });

  // Reset the bar to empty the moment the player leaves the server.
  useEffect(() => {
    if (!inGame && fillRef.current) fillRef.current.style.width = "0%";
  }, [inGame]);

  if (!user) return null;
  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");

  return (
    <div className="hidden md:flex items-center gap-2.5">
      {/* Login gift — to the LEFT of PrimeMeat */}
      <LoginGift />
      {/* PrimeMeat */}
      <div className="group relative flex flex-col justify-center px-2.5 py-1 border border-white/10 bg-white/[0.03] min-w-[100px]" style={{ borderRadius: 2 }} data-testid="balance-primemeat">
        <div className="flex items-center gap-1.5">
          <img src={MEDIA.coinNormal} alt="PrimeMeat" className="w-4 h-4 object-contain shrink-0" />
          <span className="text-sm font-semibold tabular-nums text-emerald-400 leading-none">{fmt(user.coins)}</span>
        </div>
        <div className="mt-1 h-[4px] w-full bg-white/10 overflow-hidden" style={{ borderRadius: 2 }} data-testid="passive-bar">
          <div ref={fillRef} className="h-full" style={{ width: inGame ? "4%" : "0%", background: "#FACC15", boxShadow: inGame ? "0 0 7px #FACC15" : "none" }} />
        </div>
        <div className="absolute top-full right-0 mt-2 w-max max-w-[220px] px-3 py-2 border border-emerald-500/30 text-[11px] opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-[60]" style={{ background: "#080d0b", borderRadius: 2 }} data-testid="passive-tooltip">
          {inGame
            ? <>Próximo PrimeMeat en <span ref={timeRef} className="text-emerald-400 font-bold tabular-nums">{mm}:{ss}</span></>
            : <span className="text-muted-foreground">Únete al servidor para ganar PrimeMeat</span>}
          <p className="text-muted-foreground text-[10px] mt-0.5">+300 cada 4 min mientras estás en el servidor</p>
        </div>
      </div>
      {/* Amberium */}
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 border border-gold/20 bg-gold/[0.04] min-w-[88px]" style={{ borderRadius: 2 }} data-testid="balance-amberium">
        <img src={MEDIA.coinVip} alt="Amberium" className="w-4 h-4 object-contain shrink-0" />
        <span className="text-sm font-semibold tabular-nums text-gold leading-none">{fmt(user.vip_coins)}</span>
      </div>
    </div>
  );
}
