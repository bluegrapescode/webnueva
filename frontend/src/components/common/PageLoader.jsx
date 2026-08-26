import React from "react";
import { motion } from "framer-motion";

export function PageLoader({ label = "Loading" }) {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center gap-6" data-testid="page-loader">
      <div className="relative w-16 h-16">
        <motion.span
          className="absolute inset-0 rounded-full border-2 border-gold/30 border-t-gold"
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
        />
        <motion.span
          className="absolute inset-2 rounded-full border-2 border-crimson/20 border-b-crimson"
          animate={{ rotate: -360 }}
          transition={{ repeat: Infinity, duration: 1.4, ease: "linear" }}
        />
      </div>
      <p className="label-overline text-xs text-muted-foreground animate-glow-pulse">{label}</p>
    </div>
  );
}

export function SkeletonCard({ className = "" }) {
  return <div className={`skeleton rounded-xl ${className}`} />;
}
