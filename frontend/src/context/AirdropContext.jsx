import React, { createContext, useContext, useCallback, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { Package, Plane, Trophy } from "lucide-react";
import { api } from "@/lib/api";
import { useAirdropSocket } from "@/hooks/useAirdropSocket";
import { useSound } from "@/context/SoundContext";
import { useAuth } from "@/context/AuthContext";

// Contexto GLOBAL del Airdrop: un único WebSocket compartido para toda la web.
// Reproduce los sonidos globales del evento y dispara avisos (toast) en cualquier
// página cuando un suministro cae / aterriza / es reclamado. La escena jugable
// (AirdropArena, dentro de Mini Juegos) consume este mismo estado.
const AirdropCtx = createContext(null);

const RARITY_ES = { common: "COMÚN", rare: "RARO", epic: "ÉPICO", legendary: "LEGENDARIO" };

export function AirdropProvider({ children }) {
  const { play } = useSound();
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const locRef = useRef(location);
  locRef.current = location;

  const inMiniGames = () => (locRef.current?.pathname || "").startsWith("/mini-juegos");
  const goToAirdrop = () => navigate("/mini-juegos?tab=airdrop");

  const sock = useAirdropSocket((event, data) => {
    if (event === "airdrop:incoming") {
      play("airdropIncoming");
      if (!inMiniGames()) {
        toast("⚠️ Airdrop entrante", {
          description: `Un suministro ${RARITY_ES[data?.rarity] || ""} descenderá pronto sobre La Isla Nublar.`,
          icon: <Plane className="w-4 h-4 text-[#F0B429]" />,
          action: { label: "Ver", onClick: goToAirdrop },
          duration: 7000,
        });
      }
    } else if (event === "airdrop:falling") {
      play("airdropFalling");
    } else if (event === "airdrop:available") {
      play("airdropLanded");
      setTimeout(() => play("airdropAvailable"), 550);
      if (!inMiniGames()) {
        toast.success("📦 ¡Suministro disponible!", {
          description: "El primero en reclamarlo se lo lleva todo. ¡Corre!",
          icon: <Package className="w-4 h-4 text-[#F0B429]" />,
          action: { label: "Reclamar", onClick: goToAirdrop },
          duration: 10000,
        });
      }
    } else if (event === "airdrop:claimed") {
      play("airdropClaimed");
      if (!inMiniGames() && data?.winner?.name) {
        toast(`🏆 ${data.winner.name} aseguró el suministro`, {
          description: "El próximo Airdrop llegará pronto.",
          icon: <Trophy className="w-4 h-4 text-[#F0B429]" />,
          duration: 6000,
        });
      }
    } else if (event === "airdrop:rewards") {
      // El ganador recibió sus recompensas: refresca saldos.
      refresh && refresh();
    }
  });

  const claim = useCallback(async () => {
    const r = await api.airdropClaim();
    refresh && refresh();
    return r.data; // { success, winner, rewards, rarity }
  }, [refresh]);

  return (
    <AirdropCtx.Provider value={{ ...sock, claim, goToAirdrop }}>
      {children}
    </AirdropCtx.Provider>
  );
}

export const useAirdrop = () => useContext(AirdropCtx) || { state: null, connected: false, serverNow: () => Date.now(), claim: async () => ({}), goToAirdrop: () => {} };
