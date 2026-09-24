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
import AuthCallback from "@/pages/AuthCallback";

// Route-level code splitting — heavy pages (3D skin editor, marketplace, admin,
// mini-games, cemetery) load on demand so the initial bundle stays small.
const Dashboard = React.lazy(() => import("@/pages/Dashboard"));
const Store = React.lazy(() => import("@/pages/Store"));
const Economy = React.lazy(() => import("@/pages/Economy"));
const Profile = React.lazy(() => import("@/pages/Profile"));
const RedeemCode = React.lazy(() => import("@/pages/RedeemCode"));
const Quests = React.lazy(() => import("@/pages/Quests"));
const Leaderboard = React.lazy(() => import("@/pages/Leaderboard"));
const Admin = React.lazy(() => import("@/pages/Admin"));
const MyDino = React.lazy(() => import("@/pages/MyDino"));
const Marketplace = React.lazy(() => import("@/pages/Marketplace"));
const SkinEditor = React.lazy(() => import("@/pages/SkinEditor"));
const Casino = React.lazy(() => import("@/pages/Casino"));
const ProximityVoice = React.lazy(() => import("@/pages/ProximityVoice"));
const BattlePass = React.lazy(() => import("@/pages/BattlePass"));
const CreatorDashboard = React.lazy(() => import("@/pages/CreatorDashboard"));
const CreatorPublic = React.lazy(() => import("@/pages/CreatorPublic"));
const RefRedirect = React.lazy(() => import("@/pages/RefRedirect"));
const Cementerio = React.lazy(() => import("@/pages/Cementerio"));
const TiendaSkins = React.lazy(() => import("@/pages/TiendaSkins"));
const PaymentSuccess = React.lazy(() => import("@/pages/PaymentSuccess"));
const Bounty = React.lazy(() => import("@/pages/Bounty"));
const SkinCrafting = React.lazy(() => import("@/pages/SkinCrafting"));
const Clans = React.lazy(() => import("@/pages/Clans"));
const BountyOverlay = React.lazy(() => import("@/pages/BountyOverlay"));
import CreatorNotifier from "@/components/creator/CreatorNotifier";
import CelebrationOverlay from "@/components/creator/CelebrationOverlay";
import { BountyWidget } from "@/components/bounty/BountyWidget";
import { BountySelfInvite } from "@/components/bounty/BountySelfInvite";
import { BountyProvider } from "@/context/BountyContext";

function PageFallback() {
  return (
    <div className="flex items-center justify-center py-40" data-testid="page-loading">
      <div className="w-9 h-9 rounded-full border-2 border-gold/25 border-t-gold animate-spin" />
    </div>
  );
}

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
        <React.Suspense fallback={<PageFallback />}>
        <Routes location={location} key={location.pathname}>
        <Route path="/" element={<PageWrap><Landing /></PageWrap>} />
        <Route path="/dashboard" element={<PageWrap><Dashboard /></PageWrap>} />
        <Route path="/store" element={<PageWrap><Store /></PageWrap>} />
        {/* /cases retired 2026-07-16 — Cajas lives inside Mini Juegos (crates tab);
            keep old bookmarks/deep links working with a redirect. */}
        <Route path="/cases" element={<Navigate to="/mini-juegos?tab=crates" replace />} />
        <Route path="/my-dino" element={<PageWrap><MyDino /></PageWrap>} />
        <Route path="/cementerio" element={<PageWrap><Cementerio /></PageWrap>} />
        <Route path="/tienda-skins" element={<PageWrap><TiendaSkins /></PageWrap>} />
        <Route path="/crafteo" element={<PageWrap><SkinCrafting /></PageWrap>} />
        <Route path="/clanes" element={<PageWrap><Clans /></PageWrap>} />
        <Route path="/bounty" element={<PageWrap><Bounty /></PageWrap>} />
        <Route path="/bounty/overlay" element={<BountyOverlay />} />
        <Route path="/payment/success" element={<PageWrap><PaymentSuccess /></PageWrap>} />
        <Route path="/payment/cancel" element={<Navigate to="/tienda-skins?canceled=1" replace />} />
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
      </React.Suspense>
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
            <BountyProvider>
            <ScrollToTop />
            <Layout>
              <AnimatedRoutes />
            </Layout>
            {/* Creator Program global overlays — live alongside the Toaster so
                a referral/rank/skin event surfaces no matter which page is open. */}
            <CreatorNotifier />
            <CelebrationOverlay />
            <BountyWidget />
            <BountySelfInvite />
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
            </BountyProvider>
          </BrowserRouter>
          </LiveSimProvider>
        </CartProvider>
        </VoiceProvider>
      </AuthProvider>
    </SoundProvider>
  );
}

export default App;
