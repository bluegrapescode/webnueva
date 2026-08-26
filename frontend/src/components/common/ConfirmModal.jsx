import React, { useEffect } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Lock, Loader2 } from "lucide-react";

const TONES = {
  danger: { accent: "#E24A4A", ring: "rgba(226,74,74,0.55)", soft: "rgba(226,74,74,0.10)" },
  gold: { accent: "#7CA842", ring: "rgba(124, 168, 66,0.55)", soft: "rgba(124, 168, 66,0.10)" },
  emerald: { accent: "#34D399", ring: "rgba(52,211,153,0.55)", soft: "rgba(52,211,153,0.10)" },
  orange: { accent: "#F97316", ring: "rgba(249,115,22,0.55)", soft: "rgba(249,115,22,0.10)" },
};

/**
 * Reusable tactical confirmation modal (Isla Nublar LATAM style).
 * Props:
 *  - open, onClose(), onConfirm()
 *  - title, message (string | node)
 *  - warning: optional "cannot be undone" banner text (omit to hide)
 *  - confirmLabel, abortLabel, tone ("danger" | "gold" | "emerald" | "orange"), loading, icon
 */
export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title = "¿Confirmar acción?",
  message,
  warning,
  confirmLabel = "Confirmar",
  abortLabel = "Cancelar",
  tone = "danger",
  loading = false,
  icon,
}) {
  const t = TONES[tone] || TONES.danger;

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape" && !loading) onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, loading, onClose]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[120] flex items-center justify-center p-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          data-testid="confirm-modal-overlay"
          onMouseDown={(e) => { if (e.target === e.currentTarget && !loading) onClose?.(); }}
        >
          <div className="absolute inset-0 bg-black/70 backdrop-blur-md" />
          <motion.div
            className="relative w-full max-w-md bg-[#0c0c0e] border p-7 text-center"
            style={{ borderColor: t.ring, borderRadius: 4, boxShadow: `0 0 40px ${t.soft}` }}
            initial={{ scale: 0.92, y: 12, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.92, y: 12, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            data-testid="confirm-modal"
          >
            {/* Icon */}
            <div
              className="mx-auto mb-5 flex items-center justify-center"
              style={{ width: 68, height: 68, borderRadius: 4, background: t.soft, border: `1px solid ${t.ring}`, color: t.accent }}
            >
              {icon || <AlertTriangle size={30} />}
            </div>

            <h3 className="font-display font-extrabold text-2xl tracking-tight mb-3" data-testid="confirm-modal-title">{title}</h3>
            {message && <div className="text-sm text-muted-foreground leading-relaxed mb-6 px-2">{message}</div>}

            {warning && (
              <div
                className="w-full flex items-center justify-center gap-2 py-3 mb-5 font-extrabold uppercase tracking-wide text-xs"
                style={{ background: t.soft, border: `1px solid ${t.ring}`, color: t.accent, borderRadius: 4 }}
                data-testid="confirm-modal-warning"
              >
                <Lock size={14} /> {warning}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={onClose}
                disabled={loading}
                data-testid="confirm-modal-abort"
                className="py-3 font-extrabold uppercase tracking-wide text-sm glass border border-white/10 text-foreground hover:bg-white/5 transition-all disabled:opacity-50"
                style={{ borderRadius: 4 }}
              >
                {abortLabel}
              </button>
              <button
                onClick={onConfirm}
                disabled={loading}
                data-testid="confirm-modal-confirm"
                className="py-3 font-extrabold uppercase tracking-wide text-sm transition-all disabled:opacity-50 inline-flex items-center justify-center gap-2 hover:brightness-110"
                style={{ background: t.soft, border: `1px solid ${t.accent}`, color: t.accent, borderRadius: 4 }}
              >
                {loading ? <Loader2 size={15} className="animate-spin" /> : null}
                {confirmLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}

export default ConfirmModal;
