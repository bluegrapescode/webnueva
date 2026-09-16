import React from "react";
import { useBountySocket } from "@/hooks/useBountySocket";
import { BountyCard } from "@/components/bounty/BountyCard";

// Vista limpia para OBS / streaming: fondo transparente, solo la tarjeta del
// bounty. Añade ?bg=1 a la URL para un fondo sólido oscuro (chroma alternativo).
export default function BountyOverlay() {
  const { snapshot, lastEvent } = useBountySocket();
  const params = new URLSearchParams(window.location.search);
  const solid = params.get("bg") === "1";
  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: solid ? "#0B0B0D" : "transparent" }}
      data-testid="bounty-overlay"
    >
      <BountyCard snapshot={snapshot} lastEvent={lastEvent} />
    </div>
  );
}
