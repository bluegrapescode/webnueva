import React, { useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PageLoader } from "@/components/common/PageLoader";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

export default function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { loginWithToken, setBanNotice } = useAuth();
  const { play } = useSound();
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : window.location.hash;
    const hashParams = new URLSearchParams(hash);
    const token = hashParams.get("token");
    const error = params.get("error");
    if (!token && error === "banned") {
      // The server refused the sign-in because this account is banned from the
      // website: no token was minted. Say WHY, in the server's own words, and
      // keep saying it (banner) after the toast is gone.
      const msg = params.get("msg") || "Esta cuenta está baneada de esta página web.";
      setBanNotice(msg);
      play("error");
      toast.error("No puedes entrar", { description: msg, duration: 15000 });
      navigate("/", { replace: true });
      return;
    }
    if (token) {
      loginWithToken(token).then(() => {
        window.history.replaceState(null, "", window.location.pathname);
        play("success");
        toast.success("¡Sesión iniciada con Steam!", { description: "Bienvenido a la isla." });
        navigate("/dashboard", { replace: true });
      }).catch(() => {
        window.history.replaceState(null, "", window.location.pathname);
        play("error");
        toast.error("Falló el inicio de sesión con Steam.", { description: "No se pudo validar la sesión. Inténtalo de nuevo." });
        navigate("/", { replace: true });
      });
    } else {
      play("error");
      toast.error("Falló el inicio de sesión con Steam.", { description: error || "Inténtalo de nuevo." });
      navigate("/", { replace: true });
    }
  }, [params, loginWithToken, setBanNotice, navigate, play]);

  return <PageLoader label="Completando inicio de sesion con Steam" />;
}
