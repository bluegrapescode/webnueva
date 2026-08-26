import React from "react";
import { Link } from "react-router-dom";
import { MEDIA } from "@/lib/media";
import { Github, Twitter, MessageCircle } from "lucide-react";

export function Footer() {
  return (
    <footer className="relative border-t border-white/5 mt-24" data-testid="footer">
      <div className="max-w-7xl mx-auto px-6 py-14 grid grid-cols-2 md:grid-cols-4 gap-8">
        <div className="col-span-2 md:col-span-1">
          <img src={MEDIA.logo} alt="Isla Nublar LATAM" className="h-12 w-auto mb-4" />
          <p className="text-sm text-muted-foreground max-w-xs">
            Plataforma comunitaria no oficial para The Isle: Evrima. Sobrevive. Caza. Domina.
          </p>
        </div>
        <div>
          <p className="label-overline text-xs text-gold mb-4">Plataforma</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link to="/dashboard" className="hover:text-foreground transition-colors">Panel</Link></li>
            <li><Link to="/store" className="hover:text-foreground transition-colors">Tienda</Link></li>
            <li><Link to="/battle-pass" className="hover:text-foreground transition-colors">Pase de Batalla</Link></li>
          </ul>
        </div>
        <div>
          <p className="label-overline text-xs text-gold mb-4">Servidor</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li>Evrima 0.16</li>
            <li>Mapa Gateway</li>
            <li>120 plazas</li>
            <li>Región LATAM</li>
          </ul>
        </div>
        <div>
          <p className="label-overline text-xs text-gold mb-4">Comunidad</p>
          <div className="flex gap-3">
            {[
              { Icon: MessageCircle, href: "https://discord.gg/Xg9byPCaVu", label: "Discord" },
              { Icon: Twitter, href: "#", label: "Twitter" },
              { Icon: Github, href: "#", label: "GitHub" },
            ].map(({ Icon, href, label }, i) => (
              <a key={i} href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noreferrer" title={label}
                data-testid={`footer-social-${label.toLowerCase()}`}
                className="p-2.5 rounded-lg glass hover:border-gold/40 hover:text-gold transition-colors text-muted-foreground">
                <Icon size={16} />
              </a>
            ))}
          </div>
        </div>
      </div>
      <div className="border-t border-white/5 py-6 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} Isla Nublar LATAM. No afiliado con Afterthought LLC ni The Isle. Hecho para la comunidad.
      </div>
    </footer>
  );
}
