import React, { useEffect, useState } from "react";
import { useSpring } from "framer-motion";

export function AnimatedNumber({ value, className, prefix = "", suffix = "", duration = 0.7 }) {
  const [display, setDisplay] = useState(value);
  const spring = useSpring(value, { stiffness: 120, damping: 22, duration });
  useEffect(() => { spring.set(value); }, [value, spring]);
  useEffect(() => {
    const unsub = spring.on("change", (v) => setDisplay(Math.round(v)));
    return unsub;
  }, [spring]);
  return (
    <span className={className}>
      {prefix}{display.toLocaleString()}{suffix}
    </span>
  );
}
