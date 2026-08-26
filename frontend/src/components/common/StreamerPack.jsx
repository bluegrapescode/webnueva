import React, { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Video, Check, X, Send, Loader2, Clock, ShieldCheck, AlertCircle, Radio, Link2 } from "lucide-react";
import { toast } from "sonner";
import { MEDIA } from "@/lib/media";
import { api, API, externalRedirect } from "@/lib/api";
import { useSound } from "@/context/SoundContext";

const DISCORD_BLURPLE = "#5865F2";

// ── Streamer Pack ────────────────────────────────────────────────────────────
// A FREE, application-only perk tier for content creators. It is NOT a real
// Patreon product — this section is display-only marketing of what a streamer
// gets, plus the application flow. The actual benefits are granted server-side
// by the Discord "Streamer" role (assigned on approval, revoked when removed):
//   • +20,000 Amberium every two weeks
//   • Skin creator unlocked
//   • Dino (locked-species) unlock
//   • PrimeMeat multiplier UNCHANGED (no coin boost — that stays a paid perk)
// Accent = Twitch-recognisable purple so it reads distinctly from the paid tiers.
const ACCENT = "#9146FF";
const GOLD = "#EAB308";

const PLATFORMS = ["Twitch", "YouTube", "Kick", "TikTok", "Otra"];

const PERKS = [
  "+20,000 Amberium cada dos semanas",
  "Potenciador de 2.0x PrimeMeat",
  "Acceso al creador de Skins guardadas y personalizadas",
  "Desbloqueo de dinos (especies bloqueadas)",
  "Rol de Streamer en Discord",
  "Canal exclusivo para streamers",
];

function fmtDate(iso) {
  if (!iso) return null;
  try { return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return null; }
}

// Hoisted to module scope on purpose: a component defined INSIDE ApplyModal gets a new
// function identity on every keystroke-driven re-render, so React remounts the <input>
// and it loses focus after each character. Module scope keeps a stable identity.
const INPUT_CLS = "w-full bg-white/[0.03] border border-white/10 rounded-lg px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:border-[var(--acc)] focus:outline-none transition-colors";
const Field = ({ label, children }) => (
  <label className="block">
    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
    <div className="mt-1.5">{children}</div>
  </label>
);

// ── Application form modal ───────────────────────────────────────────────────
function ApplyModal({ onClose, onSubmitted, onLinkDiscord, inviteUrl }) {
  const { play } = useSound();
  const [platform, setPlatform] = useState("Twitch");
  const [channelUrl, setChannelUrl] = useState("");
  const [followers, setFollowers] = useState("");
  const [avgViewers, setAvgViewers] = useState("");
  const [about, setAbout] = useState("");
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(null); // null | "link" | "join"

  const urlOk = /^https?:\/\/.+\..+/i.test(channelUrl.trim());
  const canSubmit = !busy && !!platform && urlOk && about.trim().length >= 10;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    play?.("click");
    try {
      await api.streamerApply({
        platform,
        channel_url: channelUrl.trim().slice(0, 300),
        followers: followers.trim().slice(0, 40),
        avg_viewers: avgViewers.trim().slice(0, 40),
        about: about.trim().slice(0, 1000),
      });
      play?.("success");
      toast.success("¡Solicitud enviada!", { description: "Un administrador revisará tu solicitud pronto." });
      onSubmitted?.();
      onClose?.();
    } catch (e) {
      play?.("error");
      const code = e?.response?.data?.detail;
      // Show the fix INSIDE the modal instead of a dead-end toast.
      if (code === "discord_link_required" || code === "discord_required") { setBlocked("link"); return; }
      if (code === "guild_join_required") { setBlocked("join"); return; }
      const msg =
        code === "already_streamer" ? "Ya eres un streamer aprobado."
        : code === "already_pending" ? "Ya tienes una solicitud en revisión."
        : code === "streamer_disabled" ? "Las solicitudes de streamer no están disponibles ahora."
        : code === "discord_unreachable" ? "No se pudo verificar tu Discord. Inténtalo de nuevo en un momento."
        : "No se pudo enviar la solicitud. Inténtalo de nuevo.";
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.div className="fixed inset-0 z-[100002] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="streamer-apply-modal" style={{ ["--acc"]: ACCENT }}>
      <div className="absolute inset-0 bg-black/85 backdrop-blur-md" onClick={busy ? undefined : onClose} />
      <motion.div initial={{ scale: 0.94, y: 20 }} animate={{ scale: 1, y: 0 }} className="relative glass-strong rounded-2xl w-full max-w-lg p-7 max-h-[90vh] overflow-y-auto">
        <button onClick={onClose} disabled={busy} className="absolute top-4 right-4 p-2 rounded-lg hover:bg-white/10 disabled:opacity-40" data-testid="streamer-apply-close"><X size={18} /></button>
        <div className="flex items-center gap-3 mb-1">
          <div className="w-11 h-11 flex items-center justify-center shrink-0" style={{ borderRadius: 8, background: `${ACCENT}22`, color: ACCENT }}><Video size={22} /></div>
          <div>
            <p className="label-overline text-[10px]" style={{ color: ACCENT }}>Streamer Pack</p>
            <h3 className="font-display font-bold text-2xl leading-none">Aplicar al Streamer Pack</h3>
          </div>
        </div>
        <p className="text-xs text-muted-foreground mb-6 mt-2">Cuéntanos sobre tu canal. Un administrador revisará tu solicitud en Discord y, si es aprobada, recibirás el rol de Streamer automáticamente.</p>

        {blocked && (
          <div className="mb-5 p-3.5 flex flex-col sm:flex-row sm:items-center gap-3" data-testid="streamer-modal-block"
            style={{ borderRadius: 8, border: `1px solid ${DISCORD_BLURPLE}66`, background: `${DISCORD_BLURPLE}14` }}>
            <p className="text-sm text-foreground/90 flex-1">
              {blocked === "link"
                ? "Primero vincula tu cuenta de Discord para poder aplicar."
                : "Únete al servidor de Discord de la comunidad para poder aplicar."}
            </p>
            {blocked === "link" ? (
              <button type="button" onClick={onLinkDiscord} data-testid="streamer-modal-link"
                className="inline-flex items-center justify-center gap-2 text-sm font-bold px-4 py-2.5 shrink-0 transition-all hover:brightness-110"
                style={{ borderRadius: 6, background: DISCORD_BLURPLE, color: "#fff" }}>
                <Link2 size={15} /> Vincular Discord
              </button>
            ) : inviteUrl ? (
              <a href={inviteUrl} target="_blank" rel="noreferrer" data-testid="streamer-modal-join"
                className="inline-flex items-center justify-center gap-2 text-sm font-bold px-4 py-2.5 shrink-0 transition-all hover:brightness-110"
                style={{ borderRadius: 6, background: DISCORD_BLURPLE, color: "#fff" }}>
                <Link2 size={15} /> Unirse al servidor
              </a>
            ) : null}
          </div>
        )}

        <div className="space-y-4">
          <Field label="Plataforma">
            <div className="flex flex-wrap gap-2" data-testid="streamer-platform">
              {PLATFORMS.map((p) => (
                <button key={p} type="button" onClick={() => setPlatform(p)}
                  className="px-3 py-2 rounded-lg text-sm font-semibold border transition-all"
                  style={platform === p ? { borderColor: ACCENT, color: ACCENT, background: `${ACCENT}18` } : { borderColor: "rgba(255,255,255,0.1)", color: "var(--muted-foreground, #9ca3af)" }}>
                  {p}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Enlace de tu canal">
            <input value={channelUrl} onChange={(e) => setChannelUrl(e.target.value)} placeholder="https://twitch.tv/tu_canal" className={INPUT_CLS} data-testid="streamer-channel-url" maxLength={300} />
            {channelUrl.trim() && !urlOk && (
              <p className="text-[10px] text-amber-400/80 mt-1" data-testid="streamer-url-hint">Ingresa un enlace completo, p. ej. https://twitch.tv/tu_canal</p>
            )}
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Seguidores / subs">
              <input value={followers} onChange={(e) => setFollowers(e.target.value)} placeholder="p. ej. 1.200" className={INPUT_CLS} data-testid="streamer-followers" maxLength={40} />
            </Field>
            <Field label="Espectadores prom.">
              <input value={avgViewers} onChange={(e) => setAvgViewers(e.target.value)} placeholder="p. ej. 40" className={INPUT_CLS} data-testid="streamer-viewers" maxLength={40} />
            </Field>
          </div>
          <Field label="¿Por qué quieres el Streamer Pack?">
            <textarea value={about} onChange={(e) => setAbout(e.target.value)} rows={4} placeholder="Cuéntanos sobre tu contenido, con qué frecuencia transmites y qué planeas hacer en el servidor…"
              className={`${INPUT_CLS} resize-none`} data-testid="streamer-about" maxLength={1000} />
            <div className="flex items-center justify-between mt-1">
              {about.trim().length < 10
                ? <span className="text-[10px] text-amber-400/80" data-testid="streamer-about-hint">Escribe al menos 10 caracteres</span>
                : <span className="text-[10px] text-emerald-400/70">Listo</span>}
              <span className="text-[10px] text-muted-foreground/60">{about.trim().length}/1000</span>
            </div>
          </Field>
        </div>

        <div className="flex gap-3 mt-6">
          <button onClick={onClose} disabled={busy} className="flex-1 glass font-semibold py-3 rounded-xl hover:border-white/20 transition-all disabled:opacity-40">Cancelar</button>
          <button onClick={submit} disabled={!canSubmit} data-testid="streamer-apply-submit"
            className="flex-1 inline-flex items-center justify-center gap-2 font-bold py-3 rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: ACCENT, color: "#fff" }}>
            {busy ? <><Loader2 size={16} className="animate-spin" /> Enviando…</> : <><Send size={16} /> Enviar solicitud</>}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Status strip (below the perks card) ──────────────────────────────────────
function StatusStrip({ status, onApply, onLinkDiscord }) {
  if (!status) return null;

  // Already an approved streamer (role held now).
  if (status.is_streamer) {
    return (
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 p-4 mt-4" style={{ borderRadius: 6, border: `1px solid ${ACCENT}55`, background: `${ACCENT}10` }} data-testid="streamer-status-active">
        <span className="inline-flex items-center gap-2 text-sm font-extrabold uppercase tracking-wide" style={{ color: ACCENT }}>
          <ShieldCheck size={16} /> Eres un Streamer aprobado
        </span>
        <span className="text-xs text-muted-foreground sm:ml-auto">Tus beneficios están activos mientras conserves el rol de Streamer en Discord.</span>
      </div>
    );
  }

  const app = status.application;
  if (app?.status === "pending") {
    return (
      <div className="flex items-center gap-3 p-4 mt-4" style={{ borderRadius: 6, border: `1px solid ${GOLD}44`, background: `${GOLD}0a` }} data-testid="streamer-status-pending">
        <Clock size={18} style={{ color: GOLD }} className="shrink-0" />
        <div className="text-sm">
          <span className="font-semibold" style={{ color: GOLD }}>Solicitud en revisión</span>
          <span className="text-muted-foreground"> · enviada {fmtDate(app.created_at) || "recientemente"}. Te avisaremos en Discord.</span>
        </div>
      </div>
    );
  }

  // Eligibility problems (not linked / not in guild) → actionable button right here.
  if (!status.discord_linked || !status.in_guild) {
    const invite = status.discord_invite;
    return (
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 p-4 mt-4" style={{ borderRadius: 6, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.02)" }} data-testid="streamer-status-blocked">
        <div className="flex items-start gap-2 text-sm text-muted-foreground">
          <AlertCircle size={18} className="shrink-0 mt-0.5" />
          <p>
            {!status.discord_linked
              ? "Para aplicar, primero vincula tu cuenta de Discord."
              : "Ya casi — únete al servidor de Discord de la comunidad para poder aplicar."}
          </p>
        </div>
        <div className="sm:ml-auto shrink-0">
          {!status.discord_linked ? (
            <button onClick={onLinkDiscord} data-testid="streamer-link-discord"
              className="inline-flex items-center justify-center gap-2 text-sm font-extrabold uppercase tracking-wide px-4 py-2.5 transition-all hover:brightness-110"
              style={{ borderRadius: 6, background: DISCORD_BLURPLE, color: "#fff" }}>
              <Link2 size={15} /> Vincular Discord
            </button>
          ) : invite ? (
            <a href={invite} target="_blank" rel="noreferrer" data-testid="streamer-join-server"
              className="inline-flex items-center justify-center gap-2 text-sm font-extrabold uppercase tracking-wide px-4 py-2.5 transition-all hover:brightness-110"
              style={{ borderRadius: 6, background: DISCORD_BLURPLE, color: "#fff" }}>
              <Link2 size={15} /> Unirse al servidor
            </a>
          ) : null}
        </div>
      </div>
    );
  }

  const rejected = app?.status === "rejected";
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3 mt-4" data-testid="streamer-status-open">
      {rejected && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <X size={15} className="text-crimson shrink-0" />
          <span>Tu solicitud anterior no fue aprobada{app.reason ? `: ${app.reason}` : "."}{status.can_apply ? " Puedes volver a aplicar." : ""}</span>
        </div>
      )}
      {status.can_apply ? (
        <button onClick={onApply} data-testid="streamer-apply-btn"
          className="sm:ml-auto inline-flex items-center justify-center gap-2 text-sm font-extrabold uppercase tracking-widest px-5 py-3 transition-all hover:brightness-110"
          style={{ borderRadius: 6, background: ACCENT, color: "#fff" }}>
          <Video size={15} /> {rejected ? "Volver a aplicar" : "Aplicar al Streamer Pack"}
        </button>
      ) : !rejected ? (
        <span className="text-sm text-muted-foreground" data-testid="streamer-status-unavailable">Las solicitudes no están disponibles ahora.</span>
      ) : null}
    </div>
  );
}

export default function StreamerPack() {
  const [status, setStatus] = useState(null);
  const [showModal, setShowModal] = useState(false);

  const load = useCallback(() => {
    api.streamerStatus().then((r) => setStatus(r.data)).catch(() => setStatus(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  // Start Discord OAuth right from this section (no hunting for "Cuentas Conectadas").
  // Leave a breadcrumb so that after the redirect back we can re-open the apply form.
  const startDiscordLink = async () => {
    try {
      localStorage.setItem("streamer_intent", "1");
      const { data } = await api.integrationsStart();
      externalRedirect(`${API}/discord/login?token=${data.link_token}`);
    } catch {
      toast.error("No se pudo iniciar la vinculación de Discord. Inténtalo de nuevo.");
    }
  };

  // Returning from a Discord link started here: the intent is served once linked; if the
  // user is now eligible, open the apply form immediately ("when they do that, it comes up").
  useEffect(() => {
    if (!status) return;
    const intent = (() => { try { return localStorage.getItem("streamer_intent"); } catch { return null; } })();
    if (intent && status.discord_linked) {
      try { localStorage.removeItem("streamer_intent"); } catch { /* ignore */ }
      if (status.can_apply) setShowModal(true);
    }
  }, [status]);

  return (
    <section className="pt-2" data-testid="streamer-pack">
      {/* section divider + heading */}
      <div className="flex items-center gap-3 mt-2 mb-3">
        <span className="text-[10px] font-bold px-2 py-0.5 rounded inline-flex items-center gap-1" style={{ background: `${ACCENT}18`, color: ACCENT, border: `1px solid ${ACCENT}40` }}>
          <Radio size={10} /> STREAMER PACK
        </span>
        <p className="text-sm text-muted-foreground">Gratis para creadores de contenido — aplica y transmite en el servidor.</p>
      </div>

      {/* perks card (mirrors the paid tier-card design) */}
      <div className="relative overflow-hidden" data-testid="streamer-pack-card"
        style={{ borderRadius: 6, border: `1px solid ${ACCENT}66`, background: "#0b0b0e", boxShadow: `0 0 40px ${ACCENT}1c` }}>
        <div className="absolute inset-0 pointer-events-none" style={{ background: `radial-gradient(120% 90% at 100% 0%, ${ACCENT}20, transparent 60%)` }} />

        <div className="relative flex items-center gap-3 px-5 pt-5 pb-4">
          <div className="w-12 h-12 flex items-center justify-center shrink-0" style={{ borderRadius: 6, background: `${ACCENT}22`, color: ACCENT }}>
            <Video size={26} />
          </div>
          <div className="flex-1">
            <h3 className="font-display font-extrabold text-2xl leading-none" style={{ color: ACCENT }}>Streamer Pack</h3>
            <p className="text-xs text-muted-foreground mt-1">Para creadores de contenido</p>
          </div>
          <span className="text-[11px] font-extrabold uppercase tracking-widest px-3 py-1.5 shrink-0" style={{ borderRadius: 4, color: "#22C55E", border: "1px solid #22C55E66", background: "#22C55E12" }}>Gratis</span>
        </div>

        {/* stat boxes — amberium + multiplier-unchanged */}
        <div className="relative grid grid-cols-2 gap-2 px-5">
          <div className="p-3" style={{ borderRadius: 4, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.02)" }}>
            <div className="flex items-center gap-1.5">
              <img src={MEDIA.coinVip} alt="" className="w-4 h-4 object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
              <span className="font-mono font-extrabold text-lg" style={{ color: GOLD }}>20,000</span>
            </div>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">Amberium quincenal</p>
          </div>
          <div className="p-3" style={{ borderRadius: 4, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.02)" }}>
            <span className="font-mono font-extrabold text-lg text-emerald">2.0x</span>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">Boost de monedas</p>
          </div>
        </div>

        {/* perks */}
        <div className="relative px-5 py-4 space-y-2">
          {PERKS.map((p, i) => (
            <div key={i} className="flex items-start gap-2 text-[13px]">
              <Check size={15} className="shrink-0 mt-0.5" style={{ color: ACCENT }} />
              <span className="text-foreground/85">{p}</span>
            </div>
          ))}
        </div>

        {/* status / apply */}
        <div className="relative px-5 pb-5">
          <StatusStrip status={status} onApply={() => setShowModal(true)} onLinkDiscord={startDiscordLink} />
        </div>
      </div>

      <AnimatePresence>
        {showModal && <ApplyModal onClose={() => setShowModal(false)} onSubmitted={load} onLinkDiscord={startDiscordLink} inviteUrl={status?.discord_invite} />}
      </AnimatePresence>
    </section>
  );
}
