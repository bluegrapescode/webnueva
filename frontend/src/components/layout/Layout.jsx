import React from "react";
import { useLocation } from "react-router-dom";
import { Navbar } from "./Navbar";
import { Footer } from "./Footer";
import { MouseGlow } from "@/components/effects/MouseGlow";
import { CartDrawer } from "@/components/common/CartDrawer";
import { FriendsDock } from "@/components/friends/FriendsDock";
import { ChatDock } from "@/components/chat/ChatDock";
import { BanNotice } from "@/components/common/BanNotice";

export function Layout({ children }) {
  const { pathname } = useLocation();
  const hideFooter = pathname.startsWith("/clanes");
  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <MouseGlow />
      <Navbar />
      <main className="relative z-10 pt-[68px]"><BanNotice />{children}</main>
      {!hideFooter && <Footer />}
      <CartDrawer />
      <FriendsDock />
      <ChatDock />
    </div>
  );
}
