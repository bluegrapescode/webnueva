import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { X, Check, Loader2, Bone, Crown, Lock } from "lucide-react";
import { RarityBadge } from "@/components/common/RarityBadge";
import { useSound } from "@/context/SoundContext";
import { GOLD, BAND_LABEL } from "@/components/battlepass/RewardCard";

function grantNote(track, viewerTier, cell) {
  // The ROW decides what lands: premium-row picks are PRIME, regular-row picks
  // are not. Each pick carries its OWN mutation count on the cell.
  const n = Number(cell?.mutations);
  const muts = Number.isFinite(n) && n > 0
    ? `con ${n} ${n === 1 ? "mutación" : "mutaciones"}`
    : "con mutaciones incluidas";
  if (track === "premium") return `Llega a tu Bóveda al 75% de crecimiento, PRIME y ${muts}.`;
  return `Llega a tu Bóveda al 75% de crecimiento, sin Prime y ${muts}.`;
}

/**
 * A dino cell is a PICK, not a fixed grant: the player chooses one species out
 * of the band the cell unlocked. Nothing is claimed until a species is picked,
 * so this modal always opens before the claim call.
 */
export function DinoPicker({ open, onClose, cell, track, band, viewerTier, busy, onConfirm, apexSpecies }) {
  const { play } = useSound();
  const [choice, setChoice] = useState(null);

  useEffect(() => { if (open) setChoice(null); }, [open, cell?.level]);

  const options = band || [];
  const apexList = Array.isArray(apexSpecies) ? apexSpecies : [];
  const apexSlugSet = new Set(apexList.map((sp) => sp && sp.slug).filter(Boolean));
  const allBand = cell?.band === "all";
  // A regular bracket pick shows the apexes LOCKED so the player learns the
  // rule where they would look for the species, not in a footnote elsewhere.
  const lockedApexes = !allBand && track === "regular"
    ? apexList.filter((sp) => sp && sp.slug && !options.some((o) => o.slug === sp.slug))
    : [];

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/80 p-3 backdrop-blur-md sm:p-4"
          onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}
          data-testid="bp-dino-picker"
        >
          <motion.div
            initial={{ scale: 0.92, y: 20, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.92, y: 20, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            className="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border p-5 sm:p-6"
            style={{ borderColor: `${GOLD}44`, background: "#0b0b0e" }}
          >
            <button
              type="button"
              onClick={() => { play("close"); onClose(); }}
              disabled={busy}
              aria-label="Cerrar"
              data-testid="bp-picker-close"
              className="absolute right-3 top-3 rounded-full bg-white/5 p-2 text-foreground/70 transition-all hover:bg-white/10 hover:text-foreground disabled:opacity-40"
            >
              <X size={18} />
            </button>

            <div className="mb-1 flex items-center gap-2">
              <Bone size={16} style={{ color: GOLD }} />
              <p className="label-overline text-[10px]" style={{ color: GOLD }}>
                Nivel {cell?.level} · {allBand ? "Cualquier especie · Ápex incluidos" : `Banda ${BAND_LABEL[cell?.band] || cell?.band || ""}`}
              </p>
            </div>
            <h3 className="font-display text-2xl font-extrabold tracking-tight">Elige tu dinosaurio</h3>
            <p className="mt-1.5 text-sm text-muted-foreground">{grantNote(track, viewerTier, cell)}</p>

            {options.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground" data-testid="bp-picker-empty">
                No hay especies disponibles en esta banda ahora mismo. Vuelve a cargar la página o avisa al staff.
              </p>
            ) : (
              <div className="mt-5 grid grid-cols-3 gap-2.5 sm:grid-cols-4 md:grid-cols-5">
                {options.map((sp) => {
                  const active = choice === sp.slug;
                  const isApex = apexSlugSet.has(sp.slug);
                  return (
                    <button
                      key={sp.slug}
                      type="button"
                      onClick={() => { play("click"); setChoice(sp.slug); }}
                      disabled={busy}
                      data-testid={`bp-picker-${sp.slug}`}
                      aria-pressed={active}
                      className="relative flex flex-col items-center gap-1.5 rounded-xl border p-2.5 transition-all disabled:opacity-50"
                      style={{
                        borderColor: active ? GOLD : isApex ? `${GOLD}59` : "rgba(255,255,255,0.1)",
                        background: active ? `${GOLD}14` : isApex ? `${GOLD}08` : "rgba(255,255,255,0.02)",
                        boxShadow: active ? `0 0 22px ${GOLD}33` : "none",
                      }}
                    >
                      {isApex && (
                        <span
                          className="absolute left-1.5 top-1.5 inline-flex items-center gap-0.5 rounded-sm px-1 py-[1px] text-[7px] font-extrabold text-black"
                          style={{ background: GOLD }}
                        >
                          <Crown size={7} /> ÁPEX
                        </span>
                      )}
                      {active && (
                        <span className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full" style={{ background: GOLD }}>
                          <Check size={12} className="text-black" />
                        </span>
                      )}
                      <img
                        src={`/dinos/${sp.slug}.png`}
                        alt=""
                        loading="lazy"
                        className="h-14 w-14 object-contain sm:h-16 sm:w-16"
                        onError={(e) => { e.currentTarget.style.visibility = "hidden"; }}
                      />
                      <span className="w-full truncate text-center text-[11px] font-semibold">{sp.name || sp.slug}</span>
                      {sp.rarity && <RarityBadge rarity={sp.rarity} />}
                    </button>
                  );
                })}
              </div>
            )}

            {lockedApexes.length > 0 && (
              <div className="mt-6" data-testid="bp-picker-apex-locked">
                <div className="mb-2 flex items-center gap-2">
                  <Crown size={13} style={{ color: GOLD }} />
                  <p className="label-overline text-[9px]" style={{ color: GOLD }}>Solo fila Premium</p>
                </div>
                <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4 md:grid-cols-5">
                  {lockedApexes.map((sp) => (
                    <div
                      key={sp.slug}
                      aria-disabled="true"
                      data-testid={`bp-picker-apexlocked-${sp.slug}`}
                      className="relative flex flex-col items-center gap-1.5 rounded-xl border border-white/8 bg-white/[0.015] p-2.5 opacity-50"
                    >
                      <span className="absolute right-1.5 top-1.5">
                        <Lock size={11} className="text-white/55" />
                      </span>
                      <img
                        src={`/dinos/${sp.slug}.png`}
                        alt=""
                        loading="lazy"
                        className="h-14 w-14 object-contain grayscale sm:h-16 sm:w-16"
                        onError={(e) => { e.currentTarget.style.visibility = "hidden"; }}
                      />
                      <span className="w-full truncate text-center text-[11px] font-semibold text-white/70">{sp.name || sp.slug}</span>
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  Los ápex se eligen solo con los picks de la fila{" "}
                  <span className="font-bold" style={{ color: GOLD }}>Premium</span> del Pase.
                </p>
              </div>
            )}

            <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => { play("close"); onClose(); }}
                disabled={busy}
                data-testid="bp-picker-cancel"
                className="rounded-lg border border-white/10 px-4 py-2.5 text-sm font-bold text-muted-foreground transition-all hover:text-foreground disabled:opacity-40"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => onConfirm(choice)}
                disabled={!choice || busy}
                data-testid="bp-picker-confirm"
                className="inline-flex items-center justify-center gap-2 rounded-lg px-5 py-2.5 text-sm font-extrabold text-black transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
                style={{ background: GOLD }}
              >
                {busy && <Loader2 size={15} className="animate-spin" />}
                Reclamar este dino
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}

export default DinoPicker;
