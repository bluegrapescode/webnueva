import React from "react";
import { BattlePassSection } from "@/components/battlepass/BattlePassSection";

// The Battle Pass as a FIRST-CLASS page (owner order 2026-08-07: it was hidden
// inside the profile tabs — "that way everyone the joins the web sees BP and
// click on it"). The section carries its own signed-out prompt, the Stripe
// return poll (?bp_session=…) and every modal; this page only gives it a home.
export default function BattlePass() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 pb-16 pt-6 sm:px-6" data-testid="battlepass-page">
      <BattlePassSection />
    </div>
  );
}
