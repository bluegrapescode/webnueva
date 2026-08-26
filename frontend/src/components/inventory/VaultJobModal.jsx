import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, CheckCircle2, XCircle, Clock3 } from "lucide-react";
import { api } from "@/lib/api";

const STATUS_META = {
  pending: { label: "Procesando…", icon: Loader2, color: "#7CA842", spin: true },
  queued: { label: "En cola…", icon: Clock3, color: "#38bdf8", spin: false },
  running: { label: "Procesando…", icon: Loader2, color: "#7CA842", spin: true },
  ok: { label: "Completado", icon: CheckCircle2, color: "#34D399", spin: false },
  failed: { label: "Fallido", icon: XCircle, color: "#E24A4A", spin: false },
  // The job record itself expired/was lost (server restart, TTL) before reaching a
  // terminal state, AND GET /api/me/vault couldn't confirm what actually happened.
  unknown: { label: "Resultado incierto", icon: XCircle, color: "#f59e0b", spin: false },
};

const TITLES = {
  park: "Aparcando tu dinosaurio",
  redeem: "Canjeando dinosaurio",
  slay: "Sacrificando dinosaurio",
};

/**
 * Polls GET /api/me/vault/job/{job_id} to a terminal state (ok|failed) and shows
 * Spanish status copy throughout.
 *
 * - Every request carries a monotonic sequence number; a response is only ever
 *   applied if it is still the LATEST request issued (out-of-order/late
 *   responses are ignored outright).
 * - Once a terminal state (ok/failed, or the 404-recovery outcomes below) has
 *   been rendered, polling stops for good — no further requests are issued.
 * - On a 404 (the in-memory job record expired/was lost — e.g. a backend
 *   restart) while still pending, GET /api/me/vault is fetched ONCE to try to
 *   confirm what actually happened: for "redeem" (dinoId known) the parked
 *   dino's absence means it redeemed; for "park" a slots_used increase over
 *   the pre-job baseline means it landed. Anything else renders a neutral
 *   Spanish error with a close button — never a silent, endless spinner.
 */
export function VaultJobModal({ jobId, verb = "park", dinoId = null, baselineSlotsUsed = null, onClose, onDone }) {
  const [state, setState] = useState({ status: "queued", detail: null });
  const [timedOut, setTimedOut] = useState(false);
  const timer = useRef(null);
  const timeoutRef = useRef(null);
  const seqRef = useRef(0);          // monotonic per-request sequence
  const terminalRef = useRef(false); // true once a terminal state has rendered -- stop polling for good
  // The poll lifecycle below is keyed on jobId ALONE; every other prop is read through
  // this ref. verb/dinoId/baselineSlotsUsed never change for a given job, and callback
  // props change IDENTITY on every parent render — if any of them restarted the effect,
  // the "queued" reset would wipe the terminal latch, re-poll, re-fire onDone, and
  // onDone's own vault refetch would re-render the parent into an endless
  // queued/Completado flicker (every ~125ms, on park and redeem alike).
  const propsRef = useRef(null);
  propsRef.current = { verb, dinoId, baselineSlotsUsed, onDone };

  useEffect(() => {
    if (!jobId) return undefined;
    setState({ status: "queued", detail: null });
    setTimedOut(false);
    seqRef.current = 0;
    terminalRef.current = false;

    const stop = () => {
      terminalRef.current = true;
      clearInterval(timer.current);
      clearTimeout(timeoutRef.current);
    };

    const settle = (status, detail, data) => {
      if (terminalRef.current) return; // a terminal state already rendered -- never overwrite it
      setState({ status, detail: detail || null });
      if (status === "ok" || status === "failed" || status === "unknown") {
        stop();
        if (status === "ok") propsRef.current.onDone?.(data || {});
      }
    };

    // GET /api/me/vault/job/{id} 404s once the in-memory job record is gone
    // (server restart, TTL prune). Try once to confirm the real outcome from
    // the vault itself rather than spinning forever or lying about success.
    const recoverFrom404 = (mySeq) => {
      api.meVault().then((r) => {
        if (mySeq !== seqRef.current || terminalRef.current) return; // superseded by a newer request
        const data = r.data || {};
        const dinos = data.dinos || [];
        const { verb: jobVerb, dinoId: jobDinoId, baselineSlotsUsed: baseline } = propsRef.current;
        let confirmedOk = false;
        if (jobVerb === "redeem" && jobDinoId != null) {
          confirmedOk = !dinos.some((d) => d.id === jobDinoId); // redeemed -> the row left the vault
        } else if (jobVerb === "park") {
          confirmedOk = typeof baseline === "number" && typeof data.slots_used === "number"
            && data.slots_used > baseline; // parked -> a new row landed
        }
        if (confirmedOk) {
          settle("ok", "Confirmado a través de tu bóveda.", data);
        } else {
          settle("unknown", "No pudimos confirmar el resultado. Revisa tu bóveda — si el cambio no aparece, inténtalo de nuevo.");
        }
      }).catch(() => {
        if (mySeq !== seqRef.current || terminalRef.current) return;
        settle("unknown", "No pudimos confirmar el resultado. Revisa tu bóveda — si el cambio no aparece, inténtalo de nuevo.");
      });
    };

    const poll = () => {
      if (terminalRef.current) return;
      const mySeq = ++seqRef.current;
      api.meVaultJob(jobId).then((r) => {
        if (mySeq !== seqRef.current || terminalRef.current) return; // a newer request has since been issued
        // GET /api/me/vault/job/{id} returns {state: "pending|ok|failed", message, kind,
        // dino_id, slots_used} — the job's lifecycle field is `state`, not `status`.
        const data = r.data || {};
        settle(data.state || "pending", data.message, data);
      }).catch((e) => {
        if (mySeq !== seqRef.current || terminalRef.current) return;
        if (e?.response?.status === 404) {
          recoverFrom404(mySeq);
        }
        // any other transient network hiccup -- keep polling on the existing interval
      });
    };
    poll();
    timer.current = setInterval(poll, 1500);
    // Escape hatch: the backend's park ack timeout is ~90s. If the job never reaches a
    // terminal state (dropped connection, crashed job, etc.) the user must never be
    // trapped under this full-screen overlay — force the close button after 95s.
    timeoutRef.current = setTimeout(() => setTimedOut(true), 95000);
    return () => { stop(); };
  }, [jobId]); // jobId is the job's whole identity — all other props flow through propsRef

  const meta = STATUS_META[state.status] || STATUS_META.running;
  const Icon = meta.icon;
  const done = state.status === "ok" || state.status === "failed" || state.status === "unknown" || timedOut;

  return createPortal(
    <AnimatePresence>
      {jobId && (
        <motion.div className="fixed inset-0 z-[130] flex items-center justify-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} data-testid="vault-job-overlay">
          <div className="absolute inset-0 bg-black/75 backdrop-blur-md" />
          <motion.div
            className="relative w-full max-w-sm bg-[#0c0c0e] border p-7 text-center"
            style={{ borderColor: `${meta.color}55`, borderRadius: 4, boxShadow: `0 0 40px ${meta.color}22` }}
            initial={{ scale: 0.94, y: 10, opacity: 0 }} animate={{ scale: 1, y: 0, opacity: 1 }} exit={{ scale: 0.94, y: 10, opacity: 0 }}
            data-testid="vault-job-modal"
          >
            <div className="mx-auto mb-4 flex items-center justify-center" style={{ width: 60, height: 60, borderRadius: 999, background: `${meta.color}18`, border: `1px solid ${meta.color}55`, color: meta.color }}>
              <Icon size={26} className={meta.spin ? "animate-spin" : ""} />
            </div>
            <h3 className="font-display font-extrabold text-xl mb-1.5">{TITLES[verb] || "Procesando acción"}</h3>
            <p className="text-sm font-semibold mb-1" style={{ color: meta.color }} data-testid="vault-job-status">{meta.label}</p>
            {state.detail && <p className="text-xs text-muted-foreground mb-2 leading-relaxed">{state.detail}</p>}
            {timedOut && state.status !== "ok" && state.status !== "failed" && (
              <p className="text-xs text-muted-foreground mb-2 leading-relaxed">Esto está tardando más de lo esperado. Puedes cerrar esta ventana; seguiremos intentando en segundo plano.</p>
            )}
            {done && (
              <button onClick={onClose} data-testid="vault-job-close"
                className="mt-4 w-full py-2.5 font-extrabold uppercase tracking-wide text-sm glass border border-white/10 hover:bg-white/5 transition-all" style={{ borderRadius: 4 }}>
                Cerrar
              </button>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}

export default VaultJobModal;
