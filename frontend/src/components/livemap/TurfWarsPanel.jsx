import React from "react";
import { Link } from "react-router-dom";
import { Swords, Flame, Crown, Megaphone, Trophy } from "lucide-react";

// Panel de Turf Wars bajo el mapa: ranking de dominio + control de rally del clan.
export function TurfWarsPanel({ turf }) {
  const { zones = [], leaderboard = [], my_clan_id, my_rally, busy, rally, config = {} } = turf || {};
  const owned = zones.filter((z) => z.owner?.id === my_clan_id);
  const contested = zones.filter((z) => z.contest);

  return (
    <div className="mt-6 rounded-2xl border border-emerald-500/15 bg-[#0a0f14] p-5" data-testid="turf-panel">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="w-9 h-9 rounded-lg border border-red-500/40 bg-red-500/10 flex items-center justify-center"><Swords size={17} className="text-red-400" /></div>
        <div className="leading-tight">
          <p className="text-[9px] tracking-[0.2em] text-red-500/70 font-bold uppercase">Guerra de Territorios</p>
          <h3 className="font-display font-extrabold text-lg">Turf Wars</h3>
        </div>
        <span className="ml-auto text-[10px] text-muted-foreground">Captura: sostén una zona con más miembros durante {config.capture_seconds || 30}s</span>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* Leaderboard de dominio */}
        <div>
          <p className="text-[10px] tracking-[0.18em] text-muted-foreground font-bold uppercase mb-2.5 flex items-center gap-1.5"><Trophy size={12} /> Dominio de territorios</p>
          <div className="space-y-1.5" data-testid="turf-leaderboard">
            {leaderboard.length === 0 && <p className="text-sm text-muted-foreground">Aún nadie controla territorios. ¡Sé el primero!</p>}
            {leaderboard.map((c, i) => (
              <div key={c.id} className={`flex items-center gap-2.5 rounded-lg px-3 py-2 border ${c.id === my_clan_id ? "border-emerald-400/40 bg-emerald-500/[0.07]" : "border-white/[0.06] bg-white/[0.02]"}`}>
                <span className="text-xs font-black text-muted-foreground w-4 text-center">{i === 0 ? <Crown size={13} className="text-amber-400 inline" /> : i + 1}</span>
                <span className="font-display font-black uppercase rounded px-1.5 py-0.5 text-[11px]" style={{ color: "#0a0b0f", background: c.color || "#64748b" }}>[{c.tag}]</span>
                <span className="flex-1 min-w-0 text-sm font-semibold truncate">{c.name}</span>
                <span className="text-xs font-bold text-emerald-300 tabular-nums" title="Zonas controladas">{c.zones} <span className="text-[9px] text-muted-foreground">zonas</span></span>
                <span className="text-xs font-bold text-amber-300 tabular-nums inline-flex items-center gap-1" title="Notoriedad"><Flame size={11} />{c.notoriety}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Control del clan / rally */}
        <div>
          <p className="text-[10px] tracking-[0.18em] text-muted-foreground font-bold uppercase mb-2.5 flex items-center gap-1.5"><Megaphone size={12} /> Tu frente</p>
          {!my_clan_id ? (
            <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 text-sm text-muted-foreground">
              Únete o funda un clan para luchar por los territorios.
              <Link to="/clanes" data-testid="turf-goto-clans" className="mt-3 inline-flex items-center gap-1.5 bg-emerald-500 text-background font-bold px-3 py-2 rounded-lg text-xs">Ir a Clanes</Link>
            </div>
          ) : (
            <>
              {my_rally && (
                <div className="mb-3 rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-200" data-testid="turf-rally-active">
                  📣 Rally activo en <b>{zones.find((z) => z.id === my_rally.zone_id)?.name || my_rally.zone_id}</b> · {my_rally.seconds_left}s restantes
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mb-2">Tocá una zona del mapa (o un botón de abajo) para ordenar un <b>Rally</b>: refuerza la presencia de tu clan allí y ayuda a capturarla.</p>
              <div className="grid grid-cols-2 gap-1.5 max-h-[220px] overflow-y-auto pr-1" data-testid="turf-zone-controls">
                {zones.map((z) => {
                  const mine = z.owner?.id === my_clan_id;
                  return (
                    <button key={z.id} onClick={() => rally?.(z.id)} disabled={busy || (my_rally && my_rally.zone_id === z.id)}
                      data-testid={`turf-zone-rally-btn-${z.id}`}
                      className={`flex items-center gap-2 rounded-lg px-2.5 py-2 border text-left transition-colors disabled:opacity-50 ${mine ? "border-emerald-400/40 bg-emerald-500/[0.07]" : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.06]"}`}>
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: z.owner?.color || "#64748b" }} />
                      <span className="flex-1 min-w-0">
                        <span className="block text-xs font-semibold truncate">{z.name}</span>
                        <span className="block text-[10px] text-muted-foreground truncate">{z.owner ? `[${z.owner.tag}]${mine ? " · Tuya" : ""}` : "Neutral"}{z.contest ? ` · disputa ${z.contest.progress}%` : ""}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="mt-2 text-[10px] text-muted-foreground">{owned.length} tuyas · {contested.length} en disputa</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
