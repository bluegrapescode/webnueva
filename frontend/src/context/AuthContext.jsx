import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { api, registerMutationListener } from "@/lib/api";
import { isBanRefusal, refusalText } from "@/lib/webBans";

const AuthContext = createContext(null);
// The website-ban sentence survives the sign-out that follows it: sessionStorage,
// so a banned player who reloads still reads WHY instead of a bare sign-in page.
const BAN_NOTICE_KEY = "lin_ban_notice";

function readBanNotice() {
  try { return sessionStorage.getItem(BAN_NOTICE_KEY) || ""; } catch (e) { return ""; }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  // Plain-words sentence from the server when THIS browser's account is banned
  // from the website (401 + X-Web-Ban on /auth/me, or ?error=banned after a
  // refused Steam sign-in). Shown as a banner until dismissed.
  const [banNotice, setBanNoticeState] = useState(readBanNotice);
  const setBanNotice = useCallback((text) => {
    const value = String(text || "");
    setBanNoticeState(value);
    try {
      if (value) sessionStorage.setItem(BAN_NOTICE_KEY, value);
      else sessionStorage.removeItem(BAN_NOTICE_KEY);
    } catch (e) { /* storage blocked -> banner still shows this page-load */ }
  }, []);
  // Last /auth/me payload, serialized. Background refreshes (post-spend interceptor,
  // 20s passive-tick ride-along) only setUser when the payload actually changed, so
  // [user]-keyed effects across the app don't refire on every no-op re-sync.
  const lastMeRef = useRef(null);
  // Frontend build this tab was loaded with (first web_build seen). When a later
  // /auth/me reports a DIFFERENT build, a newer frontend was deployed while this
  // tab sat open — reload ONCE (sessionStorage latch per target build) so nobody
  // keeps using a stale page without knowing.
  const buildAtLoadRef = useRef(null);
  // While a crate/roulette reel animates, hold the debounced /auth/me re-sync so the
  // balance does NOT drift mid-spin; the authoritative post-open balance is applied at
  // the reveal (applyBalance) so PrimeMeat ticks exactly when the reel lands. Nestable
  // counter + a hard safety timer so the hold can never latch.
  const refreshHoldRef = useRef(0);
  const holdSafetyRef = useRef(null);

  const maybeSelfHeal = (wb) => {
    if (!wb) return;
    if (!buildAtLoadRef.current) { buildAtLoadRef.current = wb; return; }
    if (buildAtLoadRef.current === wb) return;
    const latch = `lin_reload_${wb}`;
    try {
      if (sessionStorage.getItem(latch)) return;
      sessionStorage.setItem(latch, "1");
    } catch (e) { /* storage blocked -> still reload, worst case once per change */ }
    window.location.reload();
  };

  const refresh = useCallback(async () => {
    const token = localStorage.getItem("primal_token");
    if (!token) { lastMeRef.current = null; setUser(null); setLoading(false); return; }
    try {
      const { data } = await api.me();
      maybeSelfHeal(data?.web_build);
      const snapshot = JSON.stringify(data);
      if (snapshot !== lastMeRef.current) {
        lastMeRef.current = snapshot;
        setUser(data);
      }
    } catch (e) {
      // Only a real auth rejection signs the user out. Transient network/5xx errors
      // must not — background refreshes would otherwise randomly log users out.
      const status = e?.response?.status;
      if (status === 401 || status === 403) {
        // A website ban is a 401 too, but one that must be SAID: keep the
        // server's sentence so the page can tell the player why they are out.
        if (isBanRefusal(e)) setBanNotice(refusalText(e, ""));
        localStorage.removeItem("primal_token");
        lastMeRef.current = null;
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, [setBanNotice]);

  useEffect(() => { refresh(); }, [refresh]);

  // Every successful mutating API call (spend, purchase, award, refund) schedules a
  // debounced balance re-sync — no page reload needed to see the new balance.
  useEffect(() => {
    let timer = null;
    registerMutationListener(() => {
      // A reel is animating: the authoritative balance is applied at the reveal, so
      // skip the mid-spin re-poll that would otherwise move the number invisibly.
      if (refreshHoldRef.current > 0) return;
      clearTimeout(timer);
      timer = setTimeout(() => { refresh(); }, 350);
    });
    return () => { clearTimeout(timer); registerMutationListener(null); };
  }, [refresh]);

  const loginWithToken = useCallback(async (token) => {
    localStorage.setItem("primal_token", token);
    lastMeRef.current = null;
    setBanNotice("");   // a token was minted, so this account is not banned
    await refresh();
  }, [refresh, setBanNotice]);

  const demoLogin = useCallback(async () => {
    const { data } = await api.demoLogin();
    await loginWithToken(data.token);
  }, [loginWithToken]);

  const logout = useCallback(() => {
    localStorage.removeItem("primal_token");
    lastMeRef.current = null;
    setUser(null);
  }, []);

  // Apply an authoritative balance ({coins, vip_coins}) straight from a mutating
  // response (crate open, passive tick) so the HUD + countdown bar tick INSTANTLY,
  // with no /auth/me round-trip. Null-safe, and a no-op when nothing changed.
  const applyBalance = useCallback((bal) => {
    if (!bal) return;
    setUser((prev) => {
      if (!prev) return prev;
      const coins = typeof bal.coins === "number" ? bal.coins : prev.coins;
      const vip_coins = typeof bal.vip_coins === "number" ? bal.vip_coins : prev.vip_coins;
      if (coins === prev.coins && vip_coins === prev.vip_coins) return prev;
      return { ...prev, coins, vip_coins };
    });
  }, []);

  const holdAutoRefresh = useCallback(() => {
    refreshHoldRef.current += 1;
    clearTimeout(holdSafetyRef.current);
    // Safety net: a missed release (unmount, navigation) can never latch the hold —
    // force-clear well past the ~6s reel so balances always resume updating.
    holdSafetyRef.current = setTimeout(() => { refreshHoldRef.current = 0; }, 12000);
  }, []);

  const releaseAutoRefresh = useCallback(() => {
    refreshHoldRef.current = Math.max(0, refreshHoldRef.current - 1);
    if (refreshHoldRef.current === 0) {
      clearTimeout(holdSafetyRef.current);
      refresh(); // reconcile anything that changed out-of-band during the hold
    }
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ user, setUser, loading, refresh, applyBalance, holdAutoRefresh, releaseAutoRefresh, loginWithToken, demoLogin, logout, banNotice, setBanNotice }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
