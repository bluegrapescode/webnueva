import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { RarityBadge } from "@/components/common/RarityBadge";
import { GlitchProx } from "@/components/common/GlitchProx";
import { GOLD } from "@/components/battlepass/RewardCard";

// The claimed Battle Pass skins, ON the pass page (owner ask 2026-08-07: "is
// there skins too? i supposedly got some but cant see them" — they lived only
// on the equipment page). Read-only strip: applying stays on Dino en Vivo,
// where the live-dino context the apply needs already exists.
export function BpSkinsStrip() {
  const [skins, setSkins] = useState(null);

  useEffect(() => {
    let dead = false;
    api.rewardSkins()
      .then((r) => {
        if (dead) return;
        const all = r.data?.skins || [];
        setSkins(all.filter((s) => String(s.source || "").startsWith("Pase de Batalla")));
      })
      .catch(() => { if (!dead) setSkins([]); });
    return () => { dead = true; };
  }, []);

  if (!skins || skins.length === 0) return null;

  return (
    <div className="glass rounded-2xl p-5 sm:p-6" data-testid="bp-skins-strip">
      <div className="mb-1 flex items-center gap-2">
        <Sparkles size={16} style={{ color: GOLD }} />
        <p className="label-overline text-[10px]" style={{ color: GOLD }}>Tus skins del pase</p>
      </div>
      <p className="mb-4 text-sm text-muted-foreground">
        Ya son tuyas. Se aplican desde{" "}
        <Link to="/my-dino?tab=equipo" className="font-semibold underline decoration-dotted underline-offset-2 hover:text-foreground" style={{ color: GOLD }}>
          Dino en Vivo · Equipo
        </Link>{" "}
        con tu dinosaurio dentro del juego.
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7">
        {skins.map((s) => (
          <div key={s.glitch_id} className="group relative overflow-hidden rounded-xl border border-white/10 bg-black/40" data-testid={`bp-skin-${s.glitch_id}`}>
            <div className="aspect-square overflow-hidden">
              {/* Name + colour proximity, never a picture (fleet order 2026-08-11). */}
              <GlitchProx proximity={s.proximity} accent={s.accent_hex} />
              <div className="absolute inset-0 bg-gradient-to-t from-background/90 to-transparent" />
            </div>
            <div className="absolute top-1.5 right-1.5"><RarityBadge rarity={s.rarity} className="text-[8px] px-1.5 py-0" /></div>
            <div className="absolute bottom-0 inset-x-0 p-2">
              <p className="text-[11px] font-bold leading-tight line-clamp-2">{s.name}</p>
              <p className="text-[9px] text-gold font-semibold">{s.uses ?? 0} usos</p>
            </div>
          </div>
        ))}
      </div>
      <Link to="/my-dino?tab=equipo"
        className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-gold px-4 py-2 text-xs font-bold text-background transition-all hover:brightness-110"
        data-testid="bp-skins-apply-link">
        <ExternalLink size={13} /> Aplicar una skin
      </Link>
    </div>
  );
}
