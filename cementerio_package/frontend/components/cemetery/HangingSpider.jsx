import React from "react";
import { motion } from "framer-motion";

// A little spider dangling from a silk thread in a corner, bobbing up and down.
const MiniSpider = () => (
  <svg width="30" height="30" viewBox="-16 -12 32 28" aria-hidden>
    <g stroke="#0c110a" strokeWidth="1.6" fill="none" strokeLinecap="round"
       style={{ transformOrigin: "0px 0px", animation: "spiderScuttleA 0.5s ease-in-out infinite" }}>
      <path d="M-3 -4 L-10 -9 L-14 -5" />
      <path d="M-3 0 L-11 -1 L-15 3" />
      <path d="M-3 3 L-10 6 L-14 11" />
    </g>
    <g stroke="#0c110a" strokeWidth="1.6" fill="none" strokeLinecap="round"
       style={{ transformOrigin: "0px 0px", animation: "spiderScuttleB 0.5s ease-in-out infinite" }}>
      <path d="M3 -4 L10 -9 L14 -5" />
      <path d="M3 0 L11 -1 L15 3" />
      <path d="M3 3 L10 6 L14 11" />
    </g>
    <ellipse cx="0" cy="4" rx="5" ry="6" fill="#0d120a" />
    <circle cx="0" cy="-3" r="3.2" fill="#12180d" />
    <circle cx="-1.2" cy="-3" r="0.7" fill="#c0392b" />
    <circle cx="1.2" cy="-3" r="0.7" fill="#c0392b" />
  </svg>
);

export default function HangingSpider({ side = "right", offset = 60, className = "" }) {
  return (
    <div
      data-testid="cemetery-hanging-spider"
      aria-hidden
      className={`pointer-events-none absolute top-0 z-30 flex flex-col items-center ${className}`}
      style={{ [side]: offset }}
    >
      <motion.div
        style={{ width: 1.5, background: "linear-gradient(#6b7a58, #2f3a26)", opacity: 0.7 }}
        animate={{ height: [120, 195, 120] }}
        transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
      />
      <MiniSpider />
    </div>
  );
}
