import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Skull, Droplet } from "lucide-react";
import { useBountySocket } from "@/hooks/useBountySocket";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";

// Un único WebSocket compartido para todo el Sistema de Cacería. Reproduce sonidos
// globales, dispara alertas (toast) en cualquier página y mantiene un feed en vivo.
const BountyCtx = createContext(null);

const MAX_FEED = 14;

export function BountyProvider({ children }) {
  const { play } = useSound();
  const { user } = useAuth();
  const mySid = user?.steam_id;
  const myName = user?.name;
  const meRef = useRef({ mySid, myName });
  meRef.current = { mySid, myName };

  const [feed, setFeed] = useState([]);

  const value = useBountySocket((event, data) => {
    const { mySid, myName } = meRef.current;
    // Sonidos globales
    if (event === "bounty:contract_new" || event === "bounty:self_started") play("bountyAlert");
    else if (event === "bounty:completed") play("bountyComplete");
    else if (event === "bounty:self_invite") play("bountyAlert");

    // Feed en vivo (nuevos contratos + cacerías completadas)
    if (event === "bounty:contract_new" && data) {
      setFeed((f) => [{ id: `c-${Date.now()}-${Math.random()}`, kind: "contract", targetName: data.targetName || data.target_name || "Objetivo", prime: data.reward?.primeMeat || data.prime || 0, at: Date.now() }, ...f].slice(0, MAX_FEED));
    } else if (event === "bounty:completed" && data) {
      setFeed((f) => [{ id: `k-${Date.now()}-${Math.random()}`, kind: "kill", targetName: data.targetName || "Objetivo", killerName: data.killerName || "Cazador", prime: data.reward?.primeMeat || 0, at: Date.now() }, ...f].slice(0, MAX_FEED));
    }

    // Alertas globales personalizadas
    if (event === "bounty:contract_new" && data && mySid && data.targetId === mySid) {
      toast.error("¡Pusieron precio a tu cabeza!", {
        description: `Recompensa: 🥩 ${Number(data.reward?.primeMeat || 0).toLocaleString()} · huye o pelea.`,
        icon: <Skull className="w-4 h-4 text-[#ff6b74]" />,
        duration: 7000,
      });
    }
    if (event === "bounty:self_invite" && data) {
      toast("Tu cabeza puede tener precio", { description: "Actívalo para ganar PrimeMeat mientras sobrevivas.", icon: <Droplet className="w-4 h-4 text-[#F0B429]" /> });
    }
    if (event === "bounty:completed" && data) {
      const iKilled = mySid && data.killerSid && data.killerSid === mySid;
      const iDied = mySid && data.targetId === mySid;
      if (iKilled) {
        play("bountyComplete");
        toast.success(`¡Cobraste la recompensa por ${data.targetName}!`, {
          description: `+🥩 ${Number(data.reward?.primeMeat || 0).toLocaleString()}${data.reward?.amberium ? ` · +🟠 ${Number(data.reward.amberium).toLocaleString()}` : ""}`,
          icon: <Skull className="w-4 h-4 text-[#F0B429]" />, duration: 7000,
        });
      } else if (iDied) {
        toast.error(`${data.killerName} cobró la recompensa por tu cabeza.`, { icon: <Skull className="w-4 h-4 text-[#ff6b74]" /> });
      } else if ((data.reward?.primeMeat || 0) >= 100000) {
        // Anuncio global sólo para cacerías grandes (evita spam)
        toast(`Cacería completada: ${data.killerName} cazó a ${data.targetName}`, {
          description: `Recompensa 🥩 ${Number(data.reward?.primeMeat || 0).toLocaleString()}`,
          icon: <Skull className="w-4 h-4 text-[#F0B429]" />,
        });
      }
    }
  });

  return <BountyCtx.Provider value={{ ...value, feed }}>{children}</BountyCtx.Provider>;
}

export const useBounty = () => useContext(BountyCtx) || { board: { contracts: [], self: [] }, config: null, connected: false, lastEvent: null, feed: [] };
