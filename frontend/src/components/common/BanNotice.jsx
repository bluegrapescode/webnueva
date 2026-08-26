import React from "react";
import { Ban, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

// The sentence a banned player reads (2026-08-17). Drawn under the navbar when
// the server refused this browser's session or sign-in with a website ban -
// the server's own plain words, nothing invented here. Dismissable; comes back
// on the next refusal.
export function BanNotice() {
  const { banNotice, setBanNotice } = useAuth();
  if (!banNotice) return null;
  return (
    <div className="relative z-20 max-w-7xl mx-auto px-6 pt-4" data-testid="ban-notice">
      <div className="flex items-start gap-3 rounded-2xl p-4 text-sm"
        style={{ background: "rgba(226,74,74,0.10)", border: "1px solid rgba(226,74,74,0.5)", color: "#F3F4F6" }}>
        <Ban size={18} className="mt-0.5 shrink-0" style={{ color: "#E24A4A" }} />
        <p className="flex-1 leading-relaxed">{banNotice}</p>
        <button onClick={() => setBanNotice("")} aria-label="Cerrar" data-testid="ban-notice-close"
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-white/5"><X size={16} /></button>
      </div>
    </div>
  );
}
