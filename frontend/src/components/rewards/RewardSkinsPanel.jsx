import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Gift, Sparkles, Package } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { RarityBadge } from "@/components/common/RarityBadge";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { HudCorners } from "@/components/common/Hud";
import { GlitchProx } from "@/components/common/GlitchProx";

// Recompensas: glitch skins won from crates. Each card applies the skin to the
// player's LIVE in-game dino through the mod (no charge — the skin is owned).
export function RewardSkinsPanel({ inGame }) {
  const { user } = useAuth();
  const { play } = useSound();
  const [data, setData] = useState(null); // null=loading, {skins, catalog_count}
  const [applying, setApplying] = useState(null);
  // Picked body layout per skin (0/1/2); absent = the skin's own design.
  // The engine draws one design as three different region layouts.
  const [layouts, setLayouts] = useState({});

  const load = () => api.rewardSkins().then((r) => setData(r.data)).catch(() => setData({ skins: [], catalog_count: 9 }));
  useEffect(() => { if (user) load(); }, [user]);

  const apply = async (skin) => {
    setApplying(skin.glitch_id);
    play("click");
    try {
      await api.applyRewardSkin(skin.glitch_id, layouts[skin.glitch_id]);
      play("success");
      toast.success("Skin glitch enviada a tu dinosaurio", {
        description: `${skin.name} se está aplicando. El cambio puede tardar unos minutos en verse dentro del juego.`,
      });
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || "No se pudo aplicar la skin glitch");
    } finally { setApplying(null); }
  };

  if (!user) return null;
  const skins = data?.skins || [];
  // `catalog_count` is the CRATE catalog, and a player can hold designs that
  // are not in it -- Battle Pass and Creator Program exclusives have always
  // been ownable and uncounted, and 2026-08-18 moved Constelacion into that
  // group ("constelacion for battlepass only"). Without this clamp a
  // collector reads "11 de 10 conseguidas", which looks like a bug in the
  // count rather than a skin the crates cannot give.
  const total = Math.max(data?.catalog_count || 9, skins.length);

  return (
    <div data-testid="reward-skins-panel">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <p className="label-overline text-xs text-gold mb-1 inline-flex items-center gap-2"><Gift size={13} /> Recompensas</p>
          <h2 className="font-display font-bold text-2xl">Skins Glitch ganadas</h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-xl">
            Las skins glitch que ganas al abrir cajas se guardan aquí para siempre. Aplícalas a tu dinosaurio en vivo cuando quieras.
          </p>
        </div>
        {data && (
          <span className="glass rounded-xl px-4 py-2 text-sm font-semibold tabular-nums" data-testid="reward-skins-progress">
            <Sparkles size={13} className="inline mr-1.5 text-gold" />{skins.length} de {total} conseguidas
          </span>
        )}
      </div>

      {data === null ? (
        <p className="text-muted-foreground py-12 text-center">Cargando recompensas…</p>
      ) : skins.length === 0 ? (
        <div className="glass rounded-2xl p-10 text-center" data-testid="reward-skins-empty">
          <Package size={28} className="mx-auto mb-3 text-gold" />
          <p className="font-display font-bold text-lg mb-1">Todavía no has ganado ninguna skin glitch</p>
          <p className="text-sm text-muted-foreground mb-5">Abre cajas para conseguir PrimeMeat, Amberium o una de las {total} skins glitch.</p>
          <Link to="/cases" onClick={() => play("click")} data-testid="reward-skins-open-cases"
            className="inline-flex items-center gap-2 bg-gold text-background font-bold px-5 py-2.5 rounded-xl hover:brightness-110 transition-all">
            <Package size={15} /> Abrir cajas
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="reward-skins-grid">
          {skins.map((s, i) => (
            <motion.div key={s.glitch_id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: i * 0.05 }}
              className="group relative overflow-hidden bg-black/40 border p-4 flex flex-col"
              style={{ borderRadius: 3, borderColor: `${s.accent_hex || "#7CA842"}44` }}
              data-testid={`reward-skin-${s.glitch_id}`}>
              <HudCorners color={`${s.accent_hex || "#7CA842"}aa`} />
              <div className="relative aspect-square overflow-hidden rounded-lg mb-3">
                {/* Name + colour proximity, never a picture (fleet order 2026-08-11). */}
                <GlitchProx proximity={s.proximity} accent={s.accent_hex} />
                <div className="absolute inset-0 bg-gradient-to-t from-background/80 via-transparent to-transparent" />
                <div className="absolute top-2 right-2"><RarityBadge rarity={s.rarity} /></div>
                {s.quantity > 1 && (
                  <span className="absolute top-2 left-2 text-[10px] font-extrabold px-2 py-0.5 rounded bg-black/60 border border-white/20 tabular-nums"
                    data-testid={`reward-skin-qty-${s.glitch_id}`}>x{s.quantity}</span>
                )}
              </div>
              <h3 className="font-display font-bold text-lg leading-tight" style={{ color: s.accent_hex || undefined }}>{s.name}</h3>
              <p className="text-xs text-muted-foreground mt-0.5 mb-3 flex-1">{s.subtitle}</p>
              <div className="flex items-center gap-1.5 mb-2.5" data-testid={`layout-picker-${s.glitch_id}`}>
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-0.5">Diseño</span>
                {[undefined, 0, 1, 2].map((p) => {
                  const active = layouts[s.glitch_id] === p || (p === undefined && layouts[s.glitch_id] == null);
                  return (
                    <button key={String(p)} type="button"
                      onClick={() => { play("click"); setLayouts((m) => ({ ...m, [s.glitch_id]: p })); }}
                      data-testid={`layout-${p === undefined ? "auto" : p}-${s.glitch_id}`}
                      className={`text-[11px] font-bold px-2 py-1 rounded-md border transition-all ${
                        active ? "bg-gold text-background border-gold" : "bg-black/30 border-white/15 text-muted-foreground hover:border-white/40"}`}>
                      {p === undefined ? "Original" : String.fromCharCode(65 + p)}
                    </button>
                  );
                })}
              </div>
              <button onClick={() => apply(s)} disabled={!inGame || applying === s.glitch_id}
                data-testid={`apply-reward-skin-${s.glitch_id}`}
                className="w-full inline-flex items-center justify-center gap-2 text-sm font-bold px-3 py-2.5 rounded-xl bg-gold text-background hover:brightness-110 transition-all disabled:opacity-50">
                <Sparkles size={14} />
                {applying === s.glitch_id ? "Aplicando…" : "Aplicar a mi dino en vivo"}
              </button>
              {!inGame && (
                <p className="text-[11px] text-muted-foreground text-center mt-2">Entra al juego con un dinosaurio para aplicarla.</p>
              )}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

export default RewardSkinsPanel;
