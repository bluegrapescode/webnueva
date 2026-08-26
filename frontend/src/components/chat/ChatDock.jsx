import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, X, Send, Shield, Trophy, Gem, Trash2, Smile, Flame, Egg, Sparkles, PawPrint, Lock, Clock, Globe, Landmark, Mountain, Sun, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { DecoName, DecoAvatar, buildBgStyle } from "@/components/cosmetics/deco";

const REGIONS = [
  { k: "global", label: "GLOBAL", Icon: Globe },
  { k: "eu", label: "EU", Icon: Landmark },
  { k: "na", label: "NA", Icon: Mountain },
  { k: "au", label: "AU", Icon: Sun },
];
const fmtTime = (iso) => { try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };
const canMod = (u) => u?.role === "admin" || ["owner", "admin", "mod", "helper"].includes(u?.staff_rank);
const sameMinute = (a, b) => { try { return Math.abs(new Date(a) - new Date(b)) < 5 * 60 * 1000; } catch { return false; } };

function RankBadge({ meta }) {
  if (!meta) return null;
  return <span className="text-[9px] font-bold px-1.5 py-[1px] rounded uppercase tracking-wider leading-none" style={{ color: meta.color, background: `${meta.color}1f`, border: `1px solid ${meta.color}44` }}>{meta.label}</span>;
}

function LevelBadge({ level }) {
  if (!level) return null;
  return <span className="absolute -top-1.5 -left-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-[#171310] border border-gold/50 text-gold text-[10px] font-bold flex items-center justify-center tabular-nums leading-none" style={{ boxShadow: "0 0 6px rgba(124, 168, 66,0.35)" }}>{level}</span>;
}

export function ChatDock() {
  const { user } = useAuth();
  const { play } = useSound();
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState("global");
  const [view, setView] = useState("chat"); // 'chat' | 'feed'
  const [msgs, setMsgs] = useState([]);
  const [online, setOnline] = useState(0);
  const [counts, setCounts] = useState({});
  const [text, setText] = useState("");
  const [unseen, setUnseen] = useState(0);
  const [sending, setSending] = useState(false);
  const [emoteOpen, setEmoteOpen] = useState(false);
  const [emotes, setEmotes] = useState([]);
  const [emotePacks, setEmotePacks] = useState([]);
  const [activePack, setActivePack] = useState("react");
  const [cooldownSec, setCooldownSec] = useState(0);
  const [cooldownLeft, setCooldownLeft] = useState(0);
  const [atBottom, setAtBottom] = useState(true);
  const PACK_ICON = { react: Smile, meme: Flame, dino: Egg, vibe: Sparkles, animals: PawPrint };
  const loadEmotes = () => { if (emotes.length === 0) api.chatEmotes().then((r) => { setEmotes(r.data.emotes); setEmotePacks(r.data.packs); }).catch(() => {}); };
  const lastTs = useRef(null);
  const scroller = useRef(null);
  const atBottomRef = useRef(true); useEffect(() => { atBottomRef.current = atBottom; }, [atBottom]);
  const openRef = useRef(open); useEffect(() => { openRef.current = open; }, [open]);

  const pollCh = view === "feed" ? "feed" : channel;
  const pollChRef = useRef(pollCh); useEffect(() => { pollChRef.current = pollCh; }, [pollCh]);

  const scrollToBottom = (behavior = "smooth") => {
    const el = scroller.current;
    if (el) { el.scrollTo({ top: el.scrollHeight, behavior }); setAtBottom(true); }
  };

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    setAtBottom(near);
  };

  const poll = async () => {
    try {
      const { data } = await api.chatPoll(pollChRef.current, lastTs.current || undefined);
      setOnline(data.online);
      if (data.channels) setCounts(data.channels);
      if (typeof data.cooldown === "number") setCooldownSec(data.cooldown);
      if (data.messages.length) {
        lastTs.current = data.messages[data.messages.length - 1].created_at;
        setMsgs((m) => {
          const ids = new Set(m.map((x) => x.id));
          const fresh = data.messages.filter((x) => !ids.has(x.id));
          if (fresh.length && !openRef.current) setUnseen((u) => Math.min(99, u + fresh.length));
          return [...m, ...fresh].slice(-120);
        });
      }
    } catch {}
  };

  useEffect(() => {
    if (!user) return;
    setMsgs([]); lastTs.current = null; setAtBottom(true);
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [user, pollCh]);

  useEffect(() => {
    if (open) setUnseen(0);
    if (open && atBottomRef.current) setTimeout(() => scrollToBottom("auto"), 60);
    // eslint-disable-next-line
  }, [open, msgs.length]);

  useEffect(() => {
    if (cooldownLeft <= 0) return;
    const t = setTimeout(() => setCooldownLeft((c) => Math.max(0, c - 1)), 1000);
    return () => clearTimeout(t);
  }, [cooldownLeft]);

  if (!user) return null;

  const send = async (e) => {
    e?.preventDefault();
    const t = text.trim();
    if (!t || sending || view === "feed" || cooldownLeft > 0) return;
    setSending(true);
    try {
      const { data } = await api.chatSend(t, channel);
      setText("");
      setMsgs((m) => (m.some((x) => x.id === data.id) ? m : [...m, data].slice(-120)));
      lastTs.current = data.created_at; play("click");
      setTimeout(() => scrollToBottom(), 40);
      if (cooldownSec > 0) setCooldownLeft(cooldownSec);
    } catch (e2) { play("error"); toast.error(e2?.response?.data?.detail || "No se pudo enviar"); }
    finally { setSending(false); }
  };

  const del = async (id) => {
    try {
      await api.chatDelete(id);
      setMsgs((m) => m.map((x) => (x.id === id ? { ...x, deleted: true, deleted_by: user.persona_name || "Staff", text: "" } : x)));
      play("close");
    } catch { play("error"); toast.error("No se pudo eliminar"); }
  };

  const activeLabel = REGIONS.find((r) => r.k === channel)?.label || "GLOBAL";
  const title = view === "feed" ? "FEED" : `${activeLabel} CHAT`;

  return (
    <>
      {/* Floating button */}
      <button onClick={() => { setOpen((o) => !o); play(open ? "close" : "open"); }} data-testid="chat-dock-toggle"
        className="fixed bottom-6 left-6 z-[90] w-14 h-14 rounded-2xl bg-gradient-to-br from-gold to-[#a67c00] text-background shadow-2xl gold-glow flex items-center justify-center hover:brightness-110 active:scale-95 transition-all" aria-label="Live chat">
        <MessageCircle size={22} />
        {online > 0 && <span className="absolute -top-1.5 -left-1.5 min-w-[22px] h-[22px] px-1 rounded-full bg-emerald text-background text-[11px] font-bold flex items-center justify-center border-2 border-background" data-testid="chat-dock-online">{online}</span>}
        {unseen > 0 && <span className="absolute -bottom-1.5 -right-1.5 min-w-[20px] h-[20px] px-1 rounded-full bg-crimson text-white text-[10px] font-bold flex items-center justify-center border-2 border-background animate-pulse" data-testid="chat-dock-unseen">{unseen}</span>}
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div className="fixed inset-0 z-[89] bg-black/40 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOpen(false)} />
            <motion.aside initial={{ x: -400, opacity: 0.6 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -400, opacity: 0 }}
              transition={{ type: "spring", stiffness: 260, damping: 30 }}
              className="fixed top-0 left-0 bottom-0 z-[90] w-[92vw] max-w-[380px] flex flex-col glass-strong border-r border-white/10"
              data-testid="chat-dock-panel">

              {/* Header */}
              <div className="shrink-0 px-5 pt-4 pb-3 border-b border-white/10">
                <div className="flex items-center justify-between">
                  <h3 className="font-display font-extrabold text-xl tracking-[0.14em] text-foreground uppercase" data-testid="chat-title">{title}</h3>
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald/40 bg-emerald/10 px-2.5 py-1 text-[11px] font-bold text-emerald" data-testid="chat-online">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald animate-pulse" /> {online} En línea
                    </span>
                    <button onClick={() => setOpen(false)} data-testid="chat-dock-close" className="p-1.5 rounded-lg hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors"><X size={17} /></button>
                  </div>
                </div>

                {/* Region tabs */}
                <div className="mt-3 grid grid-cols-4 gap-1.5" data-testid="chat-channels">
                  {REGIONS.map((r) => {
                    const act = view === "chat" && channel === r.k;
                    return (
                      <button key={r.k} onClick={() => { setChannel(r.k); setView("chat"); play("click"); }} data-testid={`chat-channel-${r.k}`}
                        className={`flex items-center justify-center gap-1.5 rounded-lg px-1.5 py-2 text-[11px] font-bold uppercase tracking-wide transition-all border ${act ? "bg-gold/12 border-gold/50 text-gold" : "bg-white/[0.02] border-white/[0.06] text-muted-foreground hover:text-foreground hover:border-white/15"}`}>
                        <r.Icon size={13} className="shrink-0" />
                        <span>{r.label}</span>
                        <span className={`text-[10px] tabular-nums ${act ? "text-gold/70" : "text-muted-foreground/50"}`}>{counts[r.k] ?? 0}</span>
                      </button>
                    );
                  })}
                </div>

                {/* CHAT / FEED segment */}
                <div className="mt-2 grid grid-cols-2 gap-1.5 p-1 rounded-lg bg-black/40 border border-white/[0.05]">
                  <button onClick={() => { setView("chat"); play("click"); }} data-testid="chat-view-chat"
                    className={`rounded-md py-2 text-[12px] font-bold uppercase tracking-[0.14em] transition-all ${view === "chat" ? "bg-white/[0.07] text-foreground shadow-inner" : "text-muted-foreground hover:text-foreground"}`}>Chat</button>
                  <button onClick={() => { setView("feed"); play("click"); }} data-testid="chat-view-feed"
                    className={`rounded-md py-2 text-[12px] font-bold uppercase tracking-[0.14em] transition-all ${view === "feed" ? "bg-white/[0.07] text-foreground shadow-inner" : "text-muted-foreground hover:text-foreground"}`}>Feed</button>
                </div>
              </div>

              {/* Messages */}
              <div ref={scroller} onScroll={onScroll} className="relative flex-1 overflow-y-auto py-3 px-3" data-testid="chat-messages">
                {msgs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-center gap-2 px-6">
                    <div className="w-12 h-12 rounded-2xl bg-gold/[0.06] border border-gold/15 flex items-center justify-center">
                      {view === "feed" ? <Trophy size={20} className="text-gold" /> : <MessageCircle size={20} className="text-gold/70" />}
                    </div>
                    <p className="text-muted-foreground text-sm">{view === "feed" ? "Las grandes victorias aparecerán aquí." : `Bienvenido a ${activeLabel}.`}</p>
                    {view !== "feed" && <p className="text-muted-foreground/60 text-xs">Sé el primero en saludar 👋</p>}
                  </div>
                ) : (
                  msgs.map((m, i) => {
                    const prev = msgs[i - 1];
                    if (m.type === "triple_green_alert") {
                      const a = m.alert || {};
                      return (
                        <motion.div key={m.id} initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
                          className="relative my-2.5 rounded-lg overflow-hidden" data-testid={`chat-alert-${m.id}`}
                          style={{ background: "linear-gradient(160deg, rgba(10,32,22,0.95), rgba(5,16,11,0.98))", border: "1px solid rgba(16,185,129,0.55)", boxShadow: "0 0 20px rgba(16,185,129,0.22), inset 0 0 40px rgba(16,185,129,0.05)" }}>
                          <div className="absolute inset-0 pointer-events-none opacity-[0.06]" style={{ backgroundImage: "repeating-linear-gradient(0deg, #10B981 0px, #10B981 1px, transparent 1px, transparent 3px)" }} />
                          <div className="absolute -top-6 -left-6 w-20 h-20 pointer-events-none rounded-full" style={{ background: "radial-gradient(circle, rgba(16,185,129,0.5), transparent 70%)", filter: "blur(6px)" }} />
                          <div className="relative p-3.5">
                            <div className="flex items-center gap-2 mb-3">
                              <Trophy size={16} className="text-emerald-400" style={{ filter: "drop-shadow(0 0 5px rgba(16,185,129,0.8))" }} />
                              <span className="font-display font-extrabold text-emerald-400 tracking-[0.22em] text-[15px]" style={{ textShadow: "0 0 8px rgba(16,185,129,0.6)" }}>ALERTA TRIPLE VERDE</span>
                            </div>
                            <div className="flex items-center gap-2 mb-3">
                              <span className="w-9 h-11 rounded-lg bg-emerald-400 text-background font-display font-extrabold flex items-center justify-center text-lg" style={{ boxShadow: "0 0 14px rgba(16,185,129,0.7)" }}>0</span>
                              <span className="w-9 h-11 rounded-lg bg-emerald-400 text-background font-display font-extrabold flex items-center justify-center text-lg" style={{ boxShadow: "0 0 14px rgba(16,185,129,0.7)" }}>0</span>
                              <span className="w-9 h-11 rounded-lg bg-emerald-400/8 border border-emerald-400/30 text-emerald-400/50 font-display font-extrabold flex items-center justify-center text-lg">?</span>
                              <span className="text-emerald-400 font-display font-bold text-base ml-1.5 tracking-wide">2/3 Verdes</span>
                            </div>
                            <p className="text-[13px] text-foreground/90 leading-relaxed mb-3">¡La ronda jackpot está <b className="text-emerald-400">EN VIVO</b>! <b className="text-gold">{Number(a.jackpot || 0).toLocaleString()} CC</b> en el bonus pool — ¿caerá el tercer verde?</p>
                            <div className="flex items-center gap-1.5 text-emerald-400 text-[11px] font-display font-bold tracking-[0.18em]"><Clock size={13} /> {a.seconds || 15} SEGUNDOS PARA APOSTAR</div>
                          </div>
                        </motion.div>
                      );
                    }
                    if (m.role === "system" || view === "feed") {
                      return (
                        <motion.div key={m.id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}
                          className={`my-1.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs border ${m.win?.kind === "crate" ? "bg-sky-500/[0.08] border-sky-400/20" : "bg-gold/[0.08] border-gold/20"}`} data-testid={`chat-msg-${m.id}`}>
                          <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${m.win?.kind === "crate" ? "bg-sky-400/15" : "bg-gold/15"}`}>
                            {m.win?.kind === "crate" ? <Gem size={13} className="text-sky-400" /> : <Trophy size={13} className="text-gold" />}
                          </div>
                          <span className={`font-bold ${m.win?.kind === "crate" ? "text-sky-300" : "text-gold"}`}>{m.name}</span>
                          <span className="text-foreground/90 truncate">{m.text}</span>
                        </motion.div>
                      );
                    }
                    const grouped = prev && prev.user_id === m.user_id && prev.role !== "system" && prev.type !== "triple_green_alert" && sameMinute(prev.created_at, m.created_at);
                    const cos = m.cosmetics;
                    const hasNameCos = cos && (cos.color || cos.effect || cos.font);
                    const bg = buildBgStyle(cos);
                    return (
                      <div key={m.id} className={`group relative flex gap-3 px-1 rounded transition-colors ${bg.className} ${!bg.style.background ? "hover:bg-white/[0.03]" : ""} ${grouped ? "py-0.5" : "pt-2.5 pb-1"}`} style={bg.style} data-testid={`chat-msg-${m.id}`}>
                        {grouped ? (
                          <span className="w-10 shrink-0 text-[9px] text-muted-foreground/0 group-hover:text-muted-foreground/60 text-right pr-1 pt-0.5 tabular-nums">{fmtTime(m.created_at)}</span>
                        ) : (
                          <div className="relative shrink-0">
                            <DecoAvatar src={m.avatar} cosmetics={cos} size={40} ringColor={m.staff_meta ? m.staff_meta.color : "rgba(255,255,255,0.08)"} />
                            <LevelBadge level={m.level} />
                          </div>
                        )}
                        <div className="min-w-0 flex-1">
                          {!grouped && (
                            <p className="text-[13px] font-bold flex items-center gap-1.5 flex-wrap leading-tight">
                              {hasNameCos
                                ? <DecoName cosmetics={cos}>{m.name}</DecoName>
                                : <span style={m.staff_meta ? { color: m.staff_meta.color } : {}} className={!m.staff_meta ? (m.user_id === user.id ? "text-gold" : "text-foreground") : ""}>{m.name}</span>}
                              <RankBadge meta={m.staff_meta} />
                              {!m.staff_meta && m.role === "admin" && <Shield size={10} className="text-crimson" />}
                              <span className="text-muted-foreground/40 font-normal text-[10px]">{fmtTime(m.created_at)}</span>
                            </p>
                          )}
                          {m.deleted
                            ? <p className="text-sm italic text-muted-foreground/60 leading-snug flex items-center gap-1.5" data-testid={`chat-deleted-${m.id}`}><Trash2 size={11} /> Eliminado por el staff{m.deleted_by ? ` · ${m.deleted_by}` : ""}</p>
                            : <p className="text-[15px] break-words leading-snug text-foreground/85">{m.text}</p>}
                        </div>
                        {canMod(user) && !m.deleted && (
                          <button onClick={() => del(m.id)} data-testid={`chat-del-${m.id}`} className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-crimson hover:bg-crimson/10 transition-opacity self-start shrink-0"><Trash2 size={12} /></button>
                        )}
                      </div>
                    );
                  })
                )}
              </div>

              {/* Scroll-pause pill */}
              <AnimatePresence>
                {!atBottom && msgs.length > 0 && (
                  <motion.button initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
                    onClick={() => scrollToBottom()} data-testid="chat-scroll-bottom"
                    className="absolute left-1/2 -translate-x-1/2 bottom-[136px] z-10 inline-flex items-center gap-2 rounded-full border border-gold/40 bg-[#171310] px-4 py-1.5 text-[11px] font-bold text-gold shadow-lg hover:bg-gold/10 transition-colors">
                    <ChevronDown size={13} /> Pausado (bajaste el scroll)
                  </motion.button>
                )}
              </AnimatePresence>

              {/* Composer */}
              {view !== "feed" ? (
                <div className="relative shrink-0 border-t border-white/10 p-3 bg-black/30">
                  {emoteOpen && (
                    <div className="absolute bottom-full left-3 right-3 mb-2 border border-white/10 bg-[#0b0b0e] shadow-2xl rounded-xl z-20 overflow-hidden" data-testid="chat-emote-picker">
                      <div className="flex items-center gap-0.5 px-2 pt-1.5 border-b border-white/10 overflow-x-auto">
                        {emotePacks.map((p) => {
                          const Ic = PACK_ICON[p.key] || Smile;
                          const act = activePack === p.key;
                          return (
                            <button key={p.key} type="button" data-testid={`emote-pack-${p.key}`}
                              onClick={() => { setActivePack(p.key); play("click"); }}
                              className={`relative flex items-center gap-1 px-2.5 py-2 text-[11px] font-bold whitespace-nowrap transition-colors ${act ? "text-gold" : "text-muted-foreground hover:text-foreground"}`}>
                              <Ic size={13} /> {p.label}
                              {act && <span className="absolute bottom-0 inset-x-1 h-0.5 bg-gold rounded-full" />}
                            </button>
                          );
                        })}
                      </div>
                      <div className="max-h-52 overflow-y-auto p-2 grid grid-cols-7 gap-1" data-testid="emote-grid">
                        {emotes.filter((e) => e.pack === activePack).map((e) => (
                          <button key={e.id} type="button" disabled={!e.owned} title={e.owned ? e.name : `${e.name} · Bloqueado`} data-testid={`chat-emote-${e.id}`}
                            onClick={() => { if (!e.owned) return; setText((t) => (t + e.emote).slice(0, 300)); play("click"); }}
                            className={`relative w-9 h-9 flex items-center justify-center text-xl rounded transition-all ${e.owned ? "hover:bg-white/10 cursor-pointer" : "cursor-not-allowed"}`}>
                            <span style={!e.owned ? { filter: "grayscale(1)", opacity: 0.4 } : {}}>{e.emote}</span>
                            {!e.owned && <Lock size={9} className="absolute bottom-0.5 right-0.5 text-muted-foreground" />}
                          </button>
                        ))}
                        {emotes.length === 0 && <p className="col-span-7 text-center text-xs text-muted-foreground py-6">Cargando…</p>}
                      </div>
                    </div>
                  )}
                  <form onSubmit={send}>
                    <div className="relative flex items-center rounded-xl bg-white/[0.04] border border-white/[0.08] focus-within:border-gold/40 focus-within:ring-2 focus-within:ring-gold/20 transition-all">
                      <input value={text} maxLength={300} disabled={cooldownLeft > 0} onChange={(e) => setText(e.target.value)} onFocus={() => setEmoteOpen(false)}
                        placeholder={cooldownLeft > 0 ? `Modo lento · espera ${cooldownLeft}s…` : `¿Qué tienes en mente, ${user.persona_name || "superviviente"}?`} data-testid="chat-input"
                        className="flex-1 bg-transparent px-4 py-3 text-sm focus:outline-none placeholder:text-muted-foreground/50 disabled:opacity-60" />
                      <button type="button" onClick={() => { const n = !emoteOpen; setEmoteOpen(n); play("click"); if (n) loadEmotes(); }} data-testid="chat-emote-toggle" title="Emotes"
                        className={`mr-1.5 w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-all ${emoteOpen ? "bg-gold/20 text-gold" : "text-muted-foreground hover:text-foreground"}`}>
                        <Smile size={18} />
                      </button>
                    </div>
                    <div className="mt-2.5 flex items-center justify-between">
                      <span className="text-[11px] text-muted-foreground/60">Reglas del chat</span>
                      <button type="submit" disabled={sending || !text.trim() || cooldownLeft > 0} data-testid="chat-send"
                        className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-gold to-[#a67c00] text-background font-extrabold uppercase tracking-[0.14em] text-[13px] px-6 py-2.5 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-40 disabled:cursor-not-allowed">
                        {cooldownLeft > 0 ? <span className="tabular-nums" data-testid="chat-cooldown-left">{cooldownLeft}s</span> : <>Enviar <Send size={15} /></>}
                      </button>
                    </div>
                  </form>
                </div>
              ) : (
                <div className="shrink-0 p-4 border-t border-white/10 bg-black/30 text-center text-[11px] text-muted-foreground inline-flex items-center justify-center gap-1.5"><Trophy size={12} className="text-gold" /> Feed de victorias en vivo · solo lectura</div>
              )}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
