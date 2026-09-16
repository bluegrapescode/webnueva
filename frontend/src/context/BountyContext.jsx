import React, { createContext, useContext } from "react";
import { useBountySocket } from "@/hooks/useBountySocket";
import { useSound } from "@/context/SoundContext";

// Un único WebSocket compartido para todo el Sistema de Cacería (evita abrir varias
// conexiones). Reproduce sonidos globales y expone { board, config, connected, lastEvent }.
const BountyCtx = createContext(null);

export function BountyProvider({ children }) {
  const { play } = useSound();
  const value = useBountySocket((event) => {
    if (event === "bounty:contract_new" || event === "bounty:self_started") play("bountyAlert");
    else if (event === "bounty:completed") play("bountyComplete");
    else if (event === "bounty:self_invite") play("bountyAlert");
  });
  return <BountyCtx.Provider value={value}>{children}</BountyCtx.Provider>;
}

export const useBounty = () => useContext(BountyCtx) || { board: { contracts: [], self: [] }, config: null, connected: false, lastEvent: null };
