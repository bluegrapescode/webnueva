import React from "react";
import { useBounty } from "@/context/BountyContext";
import { BountyCard } from "@/components/bounty/BountyCard";
import { featuredBounty } from "@/lib/bountyMeta";

// Vista limpia para OBS / streaming: fondo transparente, solo el bounty destacado.
// ?bg=1 para un fondo sólido oscuro (chroma alternativo).
export default function BountyOverlay() {
  const { board } = useBounty();
  const b = featuredBounty(board);
  const solid = new URLSearchParams(window.location.search).get("bg") === "1";
  return (
    <div className="min-h-screen flex items-center justify-center p-6" style={{ background: solid ? "#0B0B0D" : "transparent" }} data-testid="bounty-overlay">
      <BountyCard bounty={b} />
    </div>
  );
}
