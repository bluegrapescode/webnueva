import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Link2, RefreshCw, Unlink, Check, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { api, API, externalRedirect } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

function ProviderCard({ name, accent, configured, linked, detail, onLink, onUnlink, onSync, testid }) {
  return (
    <div className="glass rounded-2xl p-6" data-testid={testid}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-display font-bold text-lg" style={{ color: accent }}>{name}</h3>
        {linked ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-emerald"><Check size={14} /> Vinculado</span>
        ) : configured ? (
          <span className="text-xs text-muted-foreground">No vinculado</span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs text-gold"><AlertCircle size={14} /> Config. pendiente</span>
        )}
      </div>
      <p className="text-sm text-muted-foreground mb-5 min-h-[40px]">{detail}</p>
      <div className="flex gap-2">
        {!linked ? (
          <button onClick={onLink} disabled={!configured} data-testid={`${testid}-link`}
            className="inline-flex items-center gap-2 text-sm font-bold px-4 py-2.5 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ background: configured ? accent : "#2a2a30", color: configured ? "#0A0A0C" : "#888" }}>
            <Link2 size={15} /> {configured ? `Vincular ${name}` : "Config. pendiente"}
          </button>
        ) : (
          <>
            {onSync && (
              <button onClick={onSync} data-testid={`${testid}-sync`} className="inline-flex items-center gap-2 text-sm font-semibold glass px-4 py-2.5 rounded-lg hover:border-white/20 transition-colors">
                <RefreshCw size={15} /> Sincronizar
              </button>
            )}
            <button onClick={onUnlink} data-testid={`${testid}-unlink`} className="inline-flex items-center gap-2 text-sm font-semibold glass px-4 py-2.5 rounded-lg text-crimson hover:bg-crimson/10 transition-colors">
              <Unlink size={15} /> Desvincular
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export function LinkedAccounts() {
  const { user, refresh } = useAuth();
  const { play } = useSound();
  const [status, setStatus] = useState({ patreon_configured: false, discord_configured: false });
  const [params, setParams] = useSearchParams();

  useEffect(() => { api.integrationsStatus().then((r) => setStatus(r.data)).catch(() => {}); }, []);

  useEffect(() => {
    const p = params.get("patreon");
    const d = params.get("discord");
    if (p === "ok") { play("success"); toast.success("¡Patreon vinculado!"); refresh(); }
    else if (p === "error") { play("error"); toast.error("Falló la vinculación de Patreon."); }
    if (d === "ok") { play("success"); toast.success("¡Discord vinculado!"); refresh(); }
    else if (d === "error") { play("error"); toast.error("Falló la vinculación de Discord."); }
    if (p || d) { params.delete("patreon"); params.delete("discord"); params.delete("detail"); setParams(params, { replace: true }); }
    // eslint-disable-next-line
  }, []);

  if (!user) return null;
  const pat = user.patreon || {};
  const dis = user.discord || {};

  const startLink = async (provider) => {
    play("click");
    try {
      const { data } = await api.integrationsStart();
      externalRedirect(`${API}/${provider}/login?token=${data.link_token}`);
    } catch {
      play("error");
      toast.error("No se pudo iniciar la vinculación. Inténtalo de nuevo.");
    }
  };

  const patDetail = pat.linked
    ? `${pat.patron_status === "active_patron" ? "Patrón activo" : (pat.patron_status || "Vinculado")}${pat.tier_name ? " · " + pat.tier_name : ""}`
    : "Vincula tu Patreon para ganar moneda VIP y desbloquear beneficios de supporter automáticamente.";
  const disDetail = dis.linked
    ? `${dis.username || "Vinculado"}${dis.in_guild ? " · En el servidor" : " · Fuera del servidor"}${dis.vip_role ? " · Rol VIP otorgado" : ""}`
    : "Vincula tu Discord para sincronizar tu rol de supporter en el servidor de la comunidad.";

  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
      className="mb-8" data-testid="linked-accounts">
      <h2 className="font-display font-bold text-xl mb-4 inline-flex items-center gap-2"><Link2 size={18} className="text-gold" /> Cuentas Conectadas</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <ProviderCard
          name="Patreon" accent="#F1465A" testid="patreon-card"
          configured={status.patreon_configured} linked={pat.linked} detail={patDetail}
          onLink={() => startLink("patreon")}
          onSync={async () => { try { await api.patreonSync(); play("success"); toast.success("Patreon sincronizado"); refresh(); } catch { play("error"); toast.error("Falló la sincronización"); } }}
          onUnlink={async () => { await api.patreonUnlink(); play("close"); toast.success("Patreon desvinculado"); refresh(); }}
        />
        <ProviderCard
          name="Discord" accent="#5865F2" testid="discord-card"
          configured={status.discord_configured} linked={dis.linked} detail={disDetail}
          onLink={() => startLink("discord")}
          onUnlink={async () => { await api.discordUnlink(); play("close"); toast.success("Discord desvinculado"); refresh(); }}
        />
      </div>
    </motion.div>
  );
}
