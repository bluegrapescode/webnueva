import React, { useEffect, useState } from "react";
import { Clock } from "lucide-react";

/** Countdown ribbon — self-updating every second. Fires onTick when seconds change (throttled). */
export function CountdownRibbon({ secondsRemaining, onTick }) {
  const [seconds, setSeconds] = useState(secondsRemaining);
  useEffect(() => { setSeconds(secondsRemaining); }, [secondsRemaining]);
  useEffect(() => {
    if (!secondsRemaining) return undefined;
    const id = setInterval(() => setSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [secondsRemaining]);
  // Tick sound trigger — only on the last 10s of each hour or last minute
  useEffect(() => {
    if (!onTick) return;
    if (seconds <= 60 && seconds > 0 && seconds % 1 === 0) {
      // Only on the last 10 seconds
      if (seconds <= 10) onTick();
    }
  }, [seconds, onTick]);

  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;

  const urgent = seconds < 3600; // last hour → red pulse

  return (
    <div className={`relative inline-flex items-center gap-3 rounded-md border px-4 py-2 ${urgent ? "border-crimson/50 bg-crimson/10" : "border-gold/30 bg-gold/[0.05]"}`}
      data-testid="lb-countdown"
    >
      <Clock size={14} className={urgent ? "text-crimson" : "text-gold"} />
      <div>
        <div className={`text-[9px] font-black tracking-[0.3em] ${urgent ? "text-crimson/80" : "text-gold/70"}`}>
          {urgent ? "ÚLTIMOS MINUTOS" : "PRÓXIMOS GANADORES EN"}
        </div>
        <div className="font-mono text-base sm:text-lg font-black whitespace-nowrap tabular-nums">
          {d > 0 && <><span className={urgent ? "text-crimson" : "text-gold"}>{d}</span><span className="text-white/40">d </span></>}
          <span className={urgent ? "text-crimson" : "text-gold"}>{String(h).padStart(2, "0")}</span>
          <span className="text-white/40">:</span>
          <span className={urgent ? "text-crimson" : "text-gold"}>{String(m).padStart(2, "0")}</span>
          <span className="text-white/40">:</span>
          <span className={urgent ? "text-crimson" : "text-gold"}>{String(s).padStart(2, "0")}</span>
        </div>
      </div>
    </div>
  );
}
