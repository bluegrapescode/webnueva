import React, { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Toaster } from "sonner";

import { AuthProvider } from "@/context/AuthContext";
import { SoundProvider } from "@/context/SoundContext";
import { CartProvider } from "@/context/CartContext";
import { VoiceProvider } from "@/context/VoiceContext";
import { LiveSimProvider } from "@/context/LiveSimContext";
import { Layout } from "@/components/layout/Layout";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { LiveTicker } from "@/components/live/LiveTicker";

import Landing from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import Store from "@/pages/Store";
import Economy from "@/pages/Economy";
import Profile from "@/pages/Profile";
import AuthCallback from "@/pages/AuthCallback";
import RedeemCode from "@/pages/RedeemCode";
import Quests from "@/pages/Quests";
import Leaderboard from "@/pages/Leaderboard";
import Admin from "@/pages/Admin";
import MyDino from "@/pages/MyDino";
import Marketplace from "@/pages/Marketplace";
import SkinEditor from "@/pages/SkinEditor";
import Casino from "@/pages/Casino";
import ProximityVoice from "@/pages/ProximityVoice";
import BattlePass from "@/pages/BattlePass";
import CreatorDashboard from "@/pages/CreatorDashboard";
import CreatorPublic from "@/pages/CreatorPublic";
import RefRedirect from "@/pages/RefRedirect";
import CreatorNotifier from "@/components/creator/CreatorNotifier";
import CelebrationOverlay from "@/components/creator/CelebrationOverlay";

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo({ top: 0, behavior: "instant" }); }, [pathname]);
  return null;
}

function PageWrap({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}

// A redirect that carries the query string across with it. Plain <Navigate to="/x">
// DROPS the search, which would silently break every ?tab= deep link that lands on
// a renamed route (e.g. the /cases -> crates tab link).
function RedirectKeepingQuery({ to }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
        <Route path="/" element={<PageWrap><Landing /></PageWrap>} />
        <Route path="/dashboard" element={<PageWrap><Dashboard /></PageWrap>} />
        <Route path="/store" element={<PageWrap><Store /></PageWrap>} />
        {/* /cases retired 2026-07-16 — Cajas lives inside Mini Juegos (crates tab);
            keep old bookmarks/deep links working with a redirect. */}
        <Route path="/cases" element={<Navigate to="/mini-juegos?tab=crates" replace />} />
        <Route path="/my-dino" element={<PageWrap><MyDino /></PageWrap>} />
        <Route path="/skin-editor" element={<PageWrap><SkinEditor /></PageWrap>} />
        {/* Renamed 2026-08-13 (owner ask): the word "Casino" was tripping the
            streaming platforms' gambling filters, and the URL shows on stream
            too — so /mini-juegos is the real route now and /casino is a
            query-preserving redirect, keeping every old bookmark, Discord link
            and ?tab= deep link working. */}
        <Route path="/mini-juegos" element={<PageWrap><Casino /></PageWrap>} />
        <Route path="/casino" element={<RedirectKeepingQuery to="/mini-juegos" />} />
        <Route path="/proximity-voice" element={<PageWrap><ProximityVoice /></PageWrap>} />
        <Route path="/marketplace" element={<PageWrap><Marketplace /></PageWrap>} />
        {/* Intercambios — player-to-player trades. NOT a page of its own since
            2026-08-11: trading happens on the Mercado, on the same grid as the
            dinosaurs that are for sale, so this path opens that page with the
            trade filter already on. Every old link, bookmark and Discord message
            still lands where the feature actually is. */}
        <Route path="/intercambios" element={<PageWrap><Marketplace initialTab="trade" /></PageWrap>} />
        {/* The English path is the one an owner or a support message will type by
            habit; it must not 404 into the blank route. */}
        <Route path="/trades" element={<Navigate to="/intercambios" replace />} />
        <Route path="/economy" element={<PageWrap><Economy /></PageWrap>} />
        <Route path="/battle-pass" element={<PageWrap><BattlePass /></PageWrap>} />
        <Route path="/profile" element={<PageWrap><Profile /></PageWrap>} />
        {/* /inventory retired 2026-07-11 — everything lives in Dino en Vivo (my-dino);
            keep old bookmarks/deep links working with a redirect. */}
        <Route path="/inventory" element={<Navigate to="/my-dino?tab=equipo" replace />} />
        <Route path="/redeem" element={<PageWrap><RedeemCode /></PageWrap>} />
        <Route path="/quests" element={<PageWrap><Quests /></PageWrap>} />
        <Route path="/leaderboard" element={<PageWrap><Leaderboard /></PageWrap>} />
        {/* Creator Program — dashboard (own code + stats), a creator's public
            referral page, and the /ref/:code capture link creators share. */}
        <Route path="/creator/dashboard" element={<PageWrap><CreatorDashboard /></PageWrap>} />
        <Route path="/creator/:code" element={<PageWrap><CreatorPublic /></PageWrap>} />
        <Route path="/ref/:code" element={<PageWrap><RefRedirect /></PageWrap>} />
        <Route path="/admin" element={<PageWrap><Admin /></PageWrap>} />
        <Route path="/auth/callback" element={<AuthCallback />} />
      </Routes>
    </AnimatePresence>
    </ErrorBoundary>
  );
}

function App() {
  return (
    <SoundProvider>
      <AuthProvider>
        {/* Voice lives at app level so the session survives navigating the site. */}
        <VoiceProvider>
        <CartProvider>
          <LiveSimProvider>
          <BrowserRouter>
            <ScrollToTop />
            <Layout>
              <AnimatedRoutes />
            </Layout>
            {/* Creator Program global overlays — live alongside the Toaster so
                a referral/rank/skin event surfaces no matter which page is open. */}
            <CreatorNotifier />
            <CelebrationOverlay />
            <LiveTicker />
            <Toaster
              position="bottom-right"
              theme="dark"
              className="pointer-events-none"
              toastOptions={{
                style: {
                  background: "rgba(12,12,15,0.9)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  backdropFilter: "blur(16px)",
                  color: "#F3F4F6",
                },
              }}
            />
          </BrowserRouter>
          </LiveSimProvider>
        </CartProvider>
        </VoiceProvider>
      </AuthProvider>
    </SoundProvider>
  );
}

export default App;
