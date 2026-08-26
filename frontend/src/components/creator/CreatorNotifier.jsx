import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { creatorWsUrl } from "@/lib/api";

/**
 * Global WebSocket listener for the Creator Program.
 *
 * Mounts at App level. When the current user is authenticated:
 *   1. Opens WS to /api/creator/ws?token=<jwt>
 *   2. Emits toasts + SFX for:
 *      - creator_notification (NEW_REFERRAL, REWARD_RECEIVED, SKIN_UNLOCKED, MILESTONE)
 *      - creator_dashboard delta (new referrals, rank up) — used as a redundant
 *        push in case the dashboard page is not mounted.
 *
 * Suppressed while the user is on /creator/dashboard (that page has its own
 * WS listener that already handles the deltas — we don't want double toasts).
 */
// The backend fires type MILESTONE for two very different things: a real
// growth-stage milestone AND the anti-abuse burst-pause notice ("Cuenta en
// revisión" — see server.py's burst check). A green toast.success on a pause
// warning would tell a held creator the opposite of what just happened, so
// this sniffs the Spanish copy the backend always uses for the pause case.
const PAUSE_NOTICE_RE = /revisi[oó]n|pausad/i;

export default function CreatorNotifier() {
  const { user }   = useAuth();
  const { play }   = useSound();
  const location   = useLocation();
  const wsRef      = useRef(null);
  const pingRef    = useRef(null);
  const prevTotalRef = useRef(null);
  const prevRankRef  = useRef(null);
  const activeRef  = useRef(false);

  // Suppress this notifier when the dedicated page is mounted
  activeRef.current = !location.pathname.startsWith("/creator/dashboard");

  useEffect(() => {
    if (!user) return undefined;
    let closed = false;
    let reconnectT = null;

    const handleDashboardDelta = (data) => {
      const total = data?.creator?.total_referrals;
      const rank  = data?.creator?.rank;
      // First message: no toast, just seed the refs
      if (prevTotalRef.current == null) { prevTotalRef.current = total; prevRankRef.current = rank; return; }
      if (activeRef.current) {
        if (total > prevTotalRef.current) {
          play("newReferral");
          toast.success(`🎉 ¡Nuevo referido! (+${total - prevTotalRef.current})`, { duration: 3000 });
        }
        if (rank && rank < prevRankRef.current) {
          play("rankUp");
          toast.success(`🏆 ¡Subiste de rank! #${prevRankRef.current} → #${rank}`, { duration: 3500 });
        }
      }
      prevTotalRef.current = total;
      prevRankRef.current  = rank;
    };

    const handleNotification = (n) => {
      if (!activeRef.current) return;
      if (n?.type === "SKIN_UNLOCKED") {
        play("skinUnlocked");
        toast.success(`👑 ${n.title}`, { duration: 6000, description: n.message });
      } else if (n?.type === "REWARD_RECEIVED") {
        play("rewardReceived");
        toast.success(`🥩 ${n.title}`, { duration: 4000, description: n.message });
      } else if (n?.type === "NEW_REFERRAL") {
        play("newReferral");
        toast(`✨ ${n.title}`, { duration: 3000, description: n.message });
      } else if (n?.type === "MILESTONE") {
        const isPause = PAUSE_NOTICE_RE.test(n.title || "") || PAUSE_NOTICE_RE.test(n.message || "");
        if (isPause) {
          play("error");
          toast.warning(`⚠️ ${n.title}`, { duration: 6000, description: n.message });
        } else {
          play("milestone");
          toast.success(`🔥 ${n.title}`, { duration: 5000, description: n.message });
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
            if (msg.type === "creator_dashboard") handleDashboardDelta(msg.data);
            else if (msg.type === "creator_notification") handleNotification(msg.notification);
          } catch (_) {}
        };
        ws.onclose = () => { if (!closed) reconnectT = setTimeout(connect, 5000); };
        ws.onerror = () => {};
      } catch (_) { reconnectT = setTimeout(connect, 5000); }
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
      prevTotalRef.current = null;
      prevRankRef.current  = null;
    };
  }, [user?.id, play]); // eslint-disable-line react-hooks/exhaustive-deps

  return null;
}
