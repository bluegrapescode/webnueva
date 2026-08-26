import React, { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { creatorWsUrl } from "@/lib/api";

/**
 * Full-screen celebratory overlay triggered when:
 *  - the current creator crosses the Elder milestone (skin unlock) or
 *  - hits the APEX PREDATOR stage.
 *
 * Listens to WS messages on /api/creator/ws for `creator_notification`
 * with type SKIN_UNLOCKED or MILESTONE (apex).
 *
 * Mount once at App level (like CreatorNotifier).
 */

const COLORS = ["#D4AF37", "#EC4899", "#A78BFA", "#22C55E", "#F59E0B", "#06B6D4"];
const PARTICLES = 90;

function ConfettiPiece({ i }) {
  const startX  = (Math.random() - 0.5) * 800;
  const endX    = startX + (Math.random() - 0.5) * 400;
  const endY    = 900 + Math.random() * 200;
  const rotate  = Math.random() * 720 - 360;
  const color   = COLORS[i % COLORS.length];
  const size    = 6 + Math.random() * 8;
  const delay   = Math.random() * 0.4;
  const shape   = i % 3 === 0 ? "50%" : i % 3 === 1 ? "3px" : "0";
  return (
    <motion.div
      className="absolute top-0 left-1/2"
      initial={{ x: startX, y: -50, rotate: 0, opacity: 1 }}
      animate={{ x: endX, y: endY, rotate, opacity: 0 }}
      transition={{ duration: 3.5 + Math.random() * 1.5, delay, ease: [0.25, 1, 0.5, 1] }}
      style={{
        width: size, height: size,
        background: color, borderRadius: shape,
        boxShadow: `0 0 8px ${color}88`,
      }}
    />
  );
}

export default function CelebrationOverlay() {
  const { user } = useAuth();
  const { play } = useSound();
  const [active, setActive] = useState(null); // { title, subtitle, medal, color }
  const wsRef  = useRef(null);
  const pingRef = useRef(null);

  useEffect(() => {
    if (!user) return undefined;
    let closed = false;
    let reconnectT = null;

    const trigger = (type, notif) => {
      if (type === "SKIN_UNLOCKED") {
        play("skinUnlocked");
        setActive({
          medal: "🦴",
          title: "¡ELDER OF THE PACK!",
          subtitle: notif?.title || "Skin exclusiva desbloqueada",
          message: notif?.message || "Alcanzaste 100 referidos validados",
          color: "#A78BFA",
        });
      } else if (type === "MILESTONE") {
        const t = String(notif?.title || "");
        if (t.includes("APEX") || t.includes("APEX PREDATOR")) {
          play("skinUnlocked");
          setActive({
            medal: "👑",
            title: "¡APEX PREDATOR!",
            subtitle: notif?.title || "Cima del programa",
            message: notif?.message || "250 referidos validados",
            color: "#D4AF37",
          });
        }
      }
    };

    const connect = () => {
      try {
        const ws = new WebSocket(creatorWsUrl());
        wsRef.current = ws;
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "creator_notification") trigger(msg.notification?.type, msg.notification);
          } catch (_) {}
        };
        ws.onclose = () => { if (!closed) reconnectT = setTimeout(connect, 6000); };
        ws.onerror = () => {};
      } catch (_) { reconnectT = setTimeout(connect, 6000); }
    };
    connect();
    pingRef.current = setInterval(() => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 25000);

    return () => {
      closed = true;
      if (reconnectT) clearTimeout(reconnectT);
      if (pingRef.current) clearInterval(pingRef.current);
      const ws = wsRef.current;
      if (ws) { try { ws.close(); } catch (_) {} }
    };
  }, [user?.id, play]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-close after 8s
  useEffect(() => {
    if (!active) return undefined;
    const t = setTimeout(() => setActive(null), 8000);
    return () => clearTimeout(t);
  }, [active]);

  return (
    <AnimatePresence>
      {active && (
        <motion.div
          key="celebration-overlay"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="fixed inset-0 z-[9999] flex items-center justify-center"
          style={{ background: "radial-gradient(circle at center, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.95) 60%)" }}
          data-testid="celebration-overlay"
          onClick={() => setActive(null)}
        >
          {/* Confetti burst */}
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            {Array.from({ length: PARTICLES }).map((_, i) => <ConfettiPiece key={i} i={i} />)}
          </div>

          {/* Center card */}
          <motion.div
            initial={{ scale: 0.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
            transition={{ type: "spring", stiffness: 220, damping: 18 }}
            className="relative max-w-md mx-4 rounded-3xl p-8 sm:p-10 text-center overflow-hidden"
            style={{
              background: "linear-gradient(180deg, rgba(27,22,48,0.95), rgba(22,18,37,0.98))",
              border: `2px solid ${active.color}`,
              boxShadow: `0 0 60px ${active.color}80, inset 0 0 40px ${active.color}22`,
            }}
          >
            <button onClick={() => setActive(null)}
              className="absolute top-3 right-3 h-8 w-8 rounded-full border border-white/10 bg-black/40 flex items-center justify-center text-white/50 hover:text-white transition">
              <X size={14} />
            </button>

            <motion.div
              animate={{ rotate: 360, scale: [1, 1.15, 1] }}
              transition={{ rotate: { duration: 20, repeat: Infinity, ease: "linear" },
                            scale:  { duration: 1.4, repeat: Infinity } }}
              className="mx-auto text-8xl mb-2 relative"
              style={{ filter: `drop-shadow(0 0 30px ${active.color}cc)` }}
            >
              {active.medal}
            </motion.div>

            <motion.div
              initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.15 }}
              className="mt-3 text-xs font-black tracking-[0.4em]" style={{ color: active.color }}>
              MILESTONE DESBLOQUEADO
            </motion.div>
            <motion.h2
              initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.2 }}
              className="mt-2 text-3xl sm:text-4xl font-black tracking-tight text-white">
              {active.title}
            </motion.h2>
            {active.subtitle && (
              <motion.p
                initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.28 }}
                className="mt-2 text-sm text-white/70">
                {active.subtitle}
              </motion.p>
            )}
            {active.message && (
              <motion.p
                initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.36 }}
                className="mt-1 text-xs text-white/40 tabular-nums">
                {active.message}
              </motion.p>
            )}

            <motion.div
              initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.5, type: "spring" }}
              className="mt-6 inline-flex items-center gap-2 rounded-full px-4 py-2 text-[11px] font-black tracking-widest"
              style={{ background: active.color, color: "#0B0714" }}>
              <Sparkles size={12} /> ACHIEVEMENT UNLOCKED
            </motion.div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
