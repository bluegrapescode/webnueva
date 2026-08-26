import React, { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CACHE_KEY = "cp_ref_code_pending";

/**
 * /ref/:code — captures a referral code and:
 *   • if the user is logged in: attempts to apply it immediately
 *   • if not: stashes it in localStorage and redirects to the landing so
 *     the code is applied automatically once they log in (via ApplyCodeCard).
 */
export default function RefRedirect() {
  const { code } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const clean = (code || "").toUpperCase().trim();
    if (!clean) { navigate("/"); return; }

    // Track the visit for conversion analytics (fire-and-forget)
    api.cpTrackVisit(clean).catch(() => {});

    const run = async () => {
      if (user) {
        try {
          const r = await api.cpApplyCode(clean);
          if (r.data.status === "PENDING") {
            toast.info(`✨ ¡Te refirió ${r.data.creator_name || clean}! ${r.data.pending_reason || ""}`.trim());
          } else {
            toast.success(`✓ ¡Te refirió ${r.data.creator_name || clean}!`);
          }
          navigate("/creator/dashboard");
        } catch (e) {
          const detail = e?.response?.data?.detail;
          if (detail === "REFERRAL_ALREADY_USED") {
            // 2026-08-18: one code PER CREATOR, not one code ever.
            toast.error("Ya apoyaste a este creator. Podés apoyar a otros con sus códigos.");
          } else if (detail === "CODE_NOT_FOUND") {
            toast.error("Ese Código de Creator no existe.");
          } else if (detail === "SELF_REFERRAL") {
            toast.error("No podés usar tu propio código.");
          } else {
            toast.error("No se pudo aplicar el código.");
          }
          navigate(`/creator/${clean}`);
        }
      } else {
        localStorage.setItem(CACHE_KEY, clean);
        toast.info(`✨ Código de creator ${clean} guardado. Iniciá sesión para reclamar tu bono.`);
        navigate("/");
      }
    };
    run();
  }, [code, user, navigate]);

  return (
    <div className="mx-auto max-w-md px-4 py-24 text-center text-white/60">
      Aplicando código de creator…
    </div>
  );
}
