import React, { useEffect, useRef, useState } from "react";

// Self-contained ticking countdown. Only THIS component re-renders each second
// (local state), never the whole page. Shows "Permanente" when there is no end.
function fmt(ms) {
  if (ms <= 0) return "0s";
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${sec}s`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

export function Countdown({ endAt, className = "", prefix = "", onExpire }) {
  const [now, setNow] = useState(Date.now());
  const firedRef = useRef(false);
  useEffect(() => {
    if (!endAt) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [endAt]);

  if (!endAt) return <span className={className}>Permanente</span>;
  const end = new Date(endAt).getTime();
  const remaining = end - now;
  if (remaining <= 0 && !firedRef.current) {
    firedRef.current = true;
    onExpire?.();
  }
  return (
    <span className={className} data-testid="countdown">
      {prefix}
      {remaining <= 0 ? "Agotado" : fmt(remaining)}
    </span>
  );
}
