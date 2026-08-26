// Canonical account-standing status styles — the SINGLE source of truth shared by the
// player-facing AccountStanding widget and the admin Sanciones panel, so one standing
// status renders one colour everywhere (player and moderator see the same thing).
import { ShieldCheck, ShieldAlert, ShieldX, Gavel } from "lucide-react";

export const STANDING_STYLE = {
  good: { c: "#34d399", label: "Buen estado", Icon: ShieldCheck, bg: "rgba(52,211,153,0.06)", bd: "rgba(52,211,153,0.35)" },
  at_risk: { c: "#7CA842", label: "En riesgo", Icon: ShieldAlert, bg: "rgba(124, 168, 66,0.06)", bd: "rgba(124, 168, 66,0.35)" },
  suspended: { c: "#ef4444", label: "Suspendido", Icon: ShieldX, bg: "rgba(239,68,68,0.06)", bd: "rgba(239,68,68,0.4)" },
  banned: { c: "#ef4444", label: "Baneado", Icon: Gavel, bg: "rgba(239,68,68,0.08)", bd: "rgba(239,68,68,0.5)" },
};
