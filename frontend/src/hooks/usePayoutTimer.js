import { useEffect, useRef } from "react";

// Continuous, requestAnimationFrame-driven countdown shared by every PrimeMeat
// payout UI (HUD bar + payout panel). Anchoring to an absolute deadline makes
// the progress fill and its mm:ss counter buttery smooth (no 1s stepping) and
// keeps every consumer perfectly in sync with the same server timer. Feed it a
// fresh `secondsRemaining` on each poll and it re-anchors without a visible jump.
export function usePayoutTimer({ secondsRemaining, intervalSeconds, active, onTick }) {
  const anchor = useRef(null);
  const cb = useRef(onTick);
  cb.current = onTick;

  useEffect(() => {
    if (!active || secondsRemaining == null || !intervalSeconds) {
      anchor.current = null;
      return;
    }
    anchor.current = {
      deadline: performance.now() + secondsRemaining * 1000,
      interval: intervalSeconds,
    };
  }, [secondsRemaining, intervalSeconds, active]);

  useEffect(() => {
    if (!active) return undefined;
    let raf;
    const loop = (now) => {
      const a = anchor.current;
      if (a) {
        let remMs = a.deadline - now;
        // Locally wrap to the next cycle when the tick elapses so the bar keeps
        // flowing smoothly until the next server poll re-anchors it.
        if (remMs <= 0) {
          const cycle = a.interval * 1000;
          remMs = cycle - ((-remMs) % cycle);
          a.deadline = now + remMs;
        }
        const remaining = remMs / 1000;
        const progress = Math.max(0, Math.min(1, (a.interval - remaining) / a.interval));
        cb.current?.(remaining, progress);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active]);
}
