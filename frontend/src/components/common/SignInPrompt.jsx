import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { LogIn } from "lucide-react";
import { MEDIA } from "@/lib/media";
import { api, startSteamLogin } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

export function SignInPrompt({ title = "Inicio de sesión requerido", sub = "Accede a esta área iniciando sesión." }) {
  const { demoLogin } = useAuth();
  const { play } = useSound();
  const [demoEnabled, setDemoEnabled] = useState(false);

  useEffect(() => {
    api.root()
      .then((r) => setDemoEnabled(Boolean(r.data?.demo)))
      .catch(() => setDemoEnabled(false));
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
      className="relative glass-strong rounded-3xl p-12 text-center overflow-hidden grain max-w-xl mx-auto my-16"
      data-testid="signin-prompt"
    >
      <img src={MEDIA.logo} alt="Isla Nublar LATAM" className="w-28 h-28 mx-auto mb-5 object-contain animate-float" />
      <h2 className="font-display font-extrabold text-3xl tracking-tight mb-2">{title}</h2>
      <p className="text-muted-foreground mb-8">{sub}</p>
      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <button onClick={() => { play("click"); startSteamLogin(); }} data-testid="prompt-steam-login"
          className="inline-flex items-center justify-center gap-2 bg-gold text-background font-bold px-6 py-3 rounded-xl hover:brightness-110 hover:gold-glow transition-all">
          <LogIn size={18} /> Iniciar sesión con Steam
        </button>
        {demoEnabled && (
          <button onClick={() => { play("click"); demoLogin(); }} data-testid="prompt-demo-login"
            className="inline-flex items-center justify-center gap-2 glass font-semibold px-6 py-3 rounded-xl hover:border-gold/40 transition-all">
            Probar cuenta demo
          </button>
        )}
      </div>
    </motion.div>
  );
}
