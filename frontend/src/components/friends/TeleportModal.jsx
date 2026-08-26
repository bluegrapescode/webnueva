import React, { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { X, Zap, Activity, Navigation, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

const FULL = 99;

function StatCard({ label, ok, dino, name }) {
  return (
    <div className={`glass rounded-xl p-3 border ${ok ? "border-emerald/40" : "border-crimson/40"}`}>
      <p className="text-[10px] label-overline text-muted-foreground truncate">{label}</p>
      <p className="text-sm font-semibold truncate mb-1.5">{name || "—"}</p>
      <div className="space-y-1 text-[11px]">
        <div className="flex items-center gap-1.5"><Activity size={11} className="text-crimson" /> HP {dino ? Math.round(dino.health) : "—"}%</div>
        <div className="flex items-center gap-1.5"><Zap size={11} className="text-sky-400" /> STA {dino ? Math.round(dino.stamina) : "—"}%</div>
      </div>
    </div>
  );
}

export function TeleportModal({ friend, onClose, play }) {
  const [n, setN] = useState(20);
  const [status, setStatus] = useState("channeling");
  const [reason, setReason] = useState("");
  const [myDino, setMyDino] = useState(undefined);
  const [fr, setFr] = useState(friend);
  const tick = useRef(null);

  const stop = () => { clearInterval(tick.current); };
  const cancel = (why) => { stop(); setStatus("cancelled"); setReason(why); play?.("error"); };

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const me = (await api.activeDino()).data.active;
        if (!active) return;
        setMyDino(me);
        const list = (await api.friends()).data.friends || [];
        const f = list.find((x) => x.id === friend.id);
        if (f) setFr(f);
        if (!me) return cancel("You no longer have a live dino.");
        if (!f || !f.online || !f.dino) return cancel("Your friend went offline.");
        if (me.live.health < FULL || me.live.stamina < FULL) return cancel("Your dino dropped below 100% health/stamina.");
        if (f.dino.health < FULL || f.dino.stamina < FULL) return cancel("Your friend's dino dropped below 100% health/stamina.");
      } catch { /* keep channeling */ }
    };
    poll();
    tick.current = setInterval(() => {
      poll();
      setN((c) => {
        if (c <= 1) { clearInterval(tick.current); commit(); return 0; }
        return c - 1;
      });
    }, 1000);
    return () => { active = false; clearInterval(tick.current); };
    // eslint-disable-next-line
  }, []);

  const commit = async () => {
    try {
      const { data } = await api.friendsTeleport(friend.id);
      setStatus("done"); play?.("success");
      toast.success(`Teleported to ${data.friend}!`, { description: data.message });
    } catch (e) {
      setStatus("cancelled"); setReason(e?.response?.data?.detail || "Teleport failed."); play?.("error");
    }
  };

  const myOk = myDino && myDino.live && myDino.live.health >= FULL && myDino.live.stamina >= FULL;
  const frOk = fr && fr.dino && fr.dino.health >= FULL && fr.dino.stamina >= FULL;

  return (
    <motion.div className="fixed inset-0 z-[100002] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="teleport-modal">
      <div className="absolute inset-0 bg-black/85 backdrop-blur-md" onClick={onClose} />
      <motion.div initial={{ scale: 0.92, y: 20 }} animate={{ scale: 1, y: 0 }} className="relative glass-strong rounded-2xl w-full max-w-md p-7 text-center">
        <button onClick={onClose} className="absolute top-4 right-4 p-2 rounded-lg hover:bg-white/10"><X size={18} /></button>
        <p className="label-overline text-[10px] text-gold mb-1">Teletransporte de campo</p>
        <h3 className="font-display font-bold text-2xl mb-1">Teletransportar a {friend.persona_name}</h3>
        <p className="text-xs text-muted-foreground mb-6">Ambos dinos deben mantener 100% de salud y vigor durante todo el canalizado.</p>

        {status === "channeling" && (
          <>
            <div className="relative w-32 h-32 mx-auto mb-5">
              <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                <circle cx="50" cy="50" r="44" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="6" />
                <motion.circle cx="50" cy="50" r="44" fill="none" stroke="#7CA842" strokeWidth="6" strokeLinecap="round"
                  strokeDasharray={2 * Math.PI * 44} initial={{ strokeDashoffset: 0 }} animate={{ strokeDashoffset: (2 * Math.PI * 44) * (1 - n / 20) }} transition={{ duration: 1, ease: "linear" }} />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center"><span className="font-display font-extrabold text-4xl tabular-nums" data-testid="teleport-countdown">{n}</span></div>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-6 text-left">
              <StatCard label="Tú" ok={myOk} dino={myDino?.live} name={myDino?.name} />
              <StatCard label={friend.persona_name} ok={frOk} dino={fr?.dino} name={fr?.dino?.name} />
            </div>
            <button onClick={onClose} data-testid="teleport-cancel" className="w-full glass font-semibold py-3 rounded-xl hover:border-crimson/40 text-crimson transition-all">Cancelar teletransporte</button>
          </>
        )}
        {status === "done" && (
          <div data-testid="teleport-done" className="py-6">
            <div className="w-16 h-16 rounded-full bg-emerald/15 flex items-center justify-center mx-auto mb-4"><Navigation size={28} className="text-emerald" /></div>
            <p className="font-display font-bold text-xl">Teletransporte completo</p>
            <p className="text-xs text-muted-foreground mt-1">Simulado — el teletransporte real en el juego se activa cuando se conecte el RCON.</p>
            <button onClick={onClose} className="mt-5 w-full bg-gold text-background font-bold py-3 rounded-xl hover:brightness-110">Cerrar</button>
          </div>
        )}
        {status === "cancelled" && (
          <div data-testid="teleport-cancelled" className="py-6">
            <div className="w-16 h-16 rounded-full bg-crimson/15 flex items-center justify-center mx-auto mb-4"><AlertTriangle size={28} className="text-crimson" /></div>
            <p className="font-display font-bold text-xl">Teletransporte cancelado</p>
            <p className="text-xs text-muted-foreground mt-1">{reason}</p>
            <button onClick={onClose} className="mt-5 w-full glass font-semibold py-3 rounded-xl">Cerrar</button>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
