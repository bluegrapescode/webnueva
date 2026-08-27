import React, { useEffect, useRef, useState, useMemo } from "react";
import { motion } from "framer-motion";
import { Lock, Loader2, Save, Palette, BarChart3, PaintBucket, Zap, Timer, Users, RotateCw, Crown, Unlock, Flame, Check, X, HelpCircle, RefreshCw, Link2, Copy, ClipboardPaste, Trash2, Camera, Dices, Sparkles } from "lucide-react";
import { HudCorners, HudGrid, SegBar } from "@/components/common/Hud";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { toast } from "sonner";
import { api, API, externalRedirect } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";
import { SignInPrompt } from "@/components/common/SignInPrompt";
import { FLEET_SLOTS, DEFAULT_FLEET_COLORS, getSpeciesDefaultColors } from "@/components/skin3d/FleetDinoModel";
import { SkinPreview3D } from "@/components/skin3d/SkinPreview3D";
import { snapshotToEditorSkin, bareClass, extractRawSnapshot, rawIsLossy } from "@/lib/copyLiveSkin";
import { SkinContractV2Panel, probeSkinContractV2 } from "@/components/skin3d/SkinContractV2Panel";
import { clampPattern, maxPatternIndex } from "@/lib/skinPatternCatalog";
import {
  GLITCH_SLOTS, GLITCH_SLOT_LABELS, GLITCH_FAMILIES, GLITCH_VARIATION_KEYS,
  emptyGlitchFields, rawToFields, fieldsToRaw, encodeGlitchCode, decodeGlitchCode,
  rawNeedsGlitchLab, randomGlitchSlot, randomGlitchFields,
} from "@/lib/glitchLab";

// Spanish, fully spelled-out labels for the fleet colour slots (matches POST /api/apply's
// colors:{body,markings,flank,underbelly,detail1,eyes,male_display} shape).
const SLOT_LABELS = {
  body: "Cuerpo",
  markings: "Marcas",
  flank: "Costado",
  underbelly: "Vientre",
  detail1: "Detalle",
  male_display: "Exhibición Macho",
  eyes: "Ojos",
};
const SLOT_ORDER = [...FLEET_SLOTS, "eyes"];
const APPLY_COOLDOWN = 10; // seconds, mirrors the in-game skin apply cooldown
const POP_CD = 300; // Patreon population ability cooldown (5 min)
const fmtTime = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

// The payload carries DISPLAY (sRGB) 0-1 values — the backend's SkinPayloadIn.to_command
// does the single sRGB->linear decode (donor CI parity: its frontend sends parseInt(hex)/255
// with no gamma decode). Pre-linearizing here would double-decode and darken in-game colors.
const clamp01 = (c) => Math.max(0, Math.min(1, c));
function srgb01FromHex(hex) {
  const n = parseInt((hex || "#ffffff").slice(1), 16);
  return { r: clamp01(((n >> 16) & 255) / 255), g: clamp01(((n >> 8) & 255) / 255), b: clamp01((n & 255) / 255) };
}
function srgb01ToHex([r, g, b, a]) {
  const toByte = (c) => Math.round(clamp01(c) * 255).toString(16).padStart(2, "0");
  return { c: `#${toByte(r)}${toByte(g)}${toByte(b)}`, a: typeof a === "number" ? a : 1 };
}
function buildApplyColors(colors) {
  const out = {};
  SLOT_ORDER.forEach((k) => {
    const srgb = srgb01FromHex(colors[k]?.c);
    out[k] = { ...srgb, a: typeof colors[k]?.a === "number" ? colors[k].a : 1 };
  });
  return out;
}
function speciesKey(s) { return s?.slug || s?.id || s?.name; }

// ===== Shareable skin code =====
// Format contract (versioned): "LIN1-" + base64url(JSON {v:1, d:<dino_class>, p:<pattern 0-2>,
// c:{<slot>:"RRGGBBAA"}}). Decodes entirely client-side, so codes work across accounts and
// match the preset payload shape ({pattern, body:{r,g,b,a}, ...}) both ways.
const SKIN_CODE_PREFIX = "LIN1-";
function encodeSkinCode(dinoClass, payload) {
  const c = {};
  SLOT_ORDER.forEach((k) => {
    const slot = payload?.[k];
    const { c: hex, a } = srgb01ToHex([slot?.r ?? 1, slot?.g ?? 1, slot?.b ?? 1, slot?.a]);
    c[k] = hex.slice(1) + Math.round(clamp01(a) * 255).toString(16).padStart(2, "0");
  });
  const json = JSON.stringify({ v: 1, d: String(dinoClass || ""), p: typeof payload?.pattern === "number" ? payload.pattern : 0, c });
  return SKIN_CODE_PREFIX + btoa(json).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
// Returns {dinoClass, pattern, colors} or null on ANY malformed input — never throws.
function decodeSkinCode(raw) {
  try {
    const trimmed = String(raw || "").trim();
    if (!trimmed.startsWith(SKIN_CODE_PREFIX)) return null;
    let b64 = trimmed.slice(SKIN_CODE_PREFIX.length).replace(/-/g, "+").replace(/_/g, "/");
    if (!b64 || /[^A-Za-z0-9+/]/.test(b64)) return null;
    while (b64.length % 4) b64 += "=";
    const obj = JSON.parse(atob(b64));
    if (!obj || obj.v !== 1 || typeof obj.d !== "string" || !obj.c || typeof obj.c !== "object") return null;
    const colors = { ...DEFAULT_FLEET_COLORS };
    SLOT_ORDER.forEach((k) => {
      const h = obj.c[k];
      if (typeof h === "string" && /^[0-9a-fA-F]{8}$/.test(h)) {
        colors[k] = { c: `#${h.slice(0, 6).toLowerCase()}`, a: Math.round(clamp01(parseInt(h.slice(6, 8), 16) / 255) * 100) / 100 };
      }
    });
    // ★ THE CODE ALWAYS CARRIED THE REAL PATTERN — the DECODER threw it away.
    // encodeSkinCode has never clamped, so LIN1- codes holding pattern 3..5 have
    // been circulating since the day the feature shipped, and every import of one
    // silently became pattern 2. Resolved against the code's OWN species now; a
    // species this site does not know still stops at 2.
    const pattern = Number.isInteger(obj.p) ? clampPattern(obj.p, null, bareClass(obj.d)) : 0;
    return { dinoClass: obj.d, pattern, colors };
  } catch (e) { return null; }
}
async function copyTextToClipboard(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch (e) {
    // http/permission fallback — hidden textarea + execCommand
    try {
      const ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.focus(); ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e2) { return false; }
  }
}

export default function SkinEditor() {
  const { user } = useAuth();
  const { play } = useSound();
  const [tab, setTab] = useState("designer");
  const [speciesList, setSpeciesList] = useState(undefined); // undefined=loading, []=empty/error
  const [selected, setSelected] = useState(null);
  const [fleetColors, setFleetColors] = useState(DEFAULT_FLEET_COLORS);
  const [pattern, setPattern] = useState(0);
  const [meState, setMeState] = useState(undefined);
  const [applying, setApplying] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [saving, setSaving] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [presets, setPresets] = useState([]);
  const [importCode, setImportCode] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(null); // preset pending delete confirmation
  const [deletingId, setDeletingId] = useState(null);       // id mid-delete (spinner + modal lock)
  const [copying, setCopying] = useState(false);            // copy-current-skin in flight
  // {presetId, name} while an EXACT copy is armed: Aplicar replays the
  // server-witnessed snapshot bytes verbatim instead of the editor state (the
  // pickers cannot hold glitch-space values — they clamp into display gamut).
  // ANY edit disarms it: from that moment the player is designing, not copying.
  const [exactCopy, setExactCopy] = useState(null);
  // Patreon access is decided by the SERVER (live Discord tier-role read), never by
  // fields cached on the login payload: undefined=checking, object=verdict.
  const [access, setAccess] = useState(undefined);
  const [gateOpen, setGateOpen] = useState(false);
  // Glitch Lab entitlement (owners + Streamer + Adult/Elder/Apex): SERVER verdict.
  const [glitchAccess, setGlitchAccess] = useState(undefined);
  const [glitchFields, setGlitchFields] = useState(() => emptyGlitchFields());
  const [glitchName, setGlitchName] = useState("");
  // Skin contract v2: null = the v1 seven-slot editor, and it STAYS null unless the
  // game side publishes an enabled contract (the probe answers null for a 404, a
  // dead network, a junk body or enabled:false). Never a flash of a half-built v2.
  const [v2Contract, setV2Contract] = useState(null);
  // What the 3D specimen should paint for teeth / mouth / claws, reported UP by
  // the v2 panel: {mapping, colors}. null whenever there is no v2 panel, no mask
  // channel measured for this species, or no row that supports those slots — and
  // null is what makes FleetDinoModel compile the shader it has always compiled.
  const [v2Advanced, setV2Advanced] = useState(null);
  const captureRef = useRef(null);

  const allowed = !!access?.allowed;
  const selKey = speciesKey(selected);
  // How far the pattern control may travel for THIS species. The art table is
  // the authority (no manifest fetch on the v1 page); the v2 panel narrows it
  // through the same helper when it has the table in hand.
  const patternMax = maxPatternIndex(null, selKey);

  // A design at Pattern 5 on an Omniraptor cannot survive a switch to a species
  // with three. Pull it into range on every species change, so the picker, the
  // 3D specimen and the payload can never disagree.
  useEffect(() => {
    setPattern((p) => clampPattern(p, null, selKey));
  }, [selKey]);

  // ★ A MASK CHANNEL MAP BELONGS TO ONE SPECIES, AND THE VIEWER REMOUNTS BEFORE
  // THE PANEL'S EFFECT CAN CLEAR IT. For that one commit the new animal was
  // handed the old animal's map and painted its own mask with it — an Allosaurus
  // wearing an Omniraptor's magenta claws, on a species whose panel correctly
  // offered no claws row at all (measured 2026-08-25, 1,130 magenta pixels).
  // This is not a race to be won with more waiting: the map simply is not valid
  // for another animal, so it is dropped by NAME.
  const v2AdvancedForSpecies = (v2Advanced && v2Advanced.species === selKey) ? v2Advanced : null;
  const loadPresets = () => api.presetsList().then((r) => setPresets(Array.isArray(r.data) ? r.data : (r.data?.presets || []))).catch(() => {});

  useEffect(() => {
    if (!user) return;
    api.patreonAccess().then((r) => setAccess(r.data)).catch(() => setAccess(null));
    api.glitchAccess().then((r) => setGlitchAccess(r.data)).catch(() => setGlitchAccess(null));
    api.species().then((r) => {
      const list = Array.isArray(r.data) ? r.data : (r.data?.species || []);
      setSpeciesList(list);
      const first = list[0] || null;
      setSelected(first);
      if (first) setFleetColors(getSpeciesDefaultColors(first));
    }).catch(() => setSpeciesList([]));
    api.meState().then((r) => setMeState(r.data)).catch(() => setMeState(null));
    probeSkinContractV2().then((c) => setV2Contract(c)).catch(() => setV2Contract(null));
    loadPresets();
    // Depend on the user's IDENTITY, not the user object: AuthContext.refresh() (fired by
    // e.g. BalanceHUD's passive-earn tick) replaces the object with a fresh reference every
    // time, and re-running this initializer on that reset the species selection AND wiped
    // the player's in-progress colours back to the species defaults mid-edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  if (!user) return <div className="max-w-6xl mx-auto px-6 py-14"><SignInPrompt title="Patreon Access" sub="Inicia sesión para acceder a la población de dinos y el diseñador de skins." /></div>;

  const setColor = (key, c) => { setExactCopy(null); setFleetColors((p) => ({ ...p, [key]: { ...p[key], c } })); };
  const setAlpha = (key, a) => { setExactCopy(null); setFleetColors((p) => ({ ...p, [key]: { ...p[key], a } })); };
  const inGame = !!meState?.in_game;

  const applyToLive = async () => {
    if (!selKey) return;
    if (!allowed) { play("error"); setGateOpen(true); return; }
    if (!inGame) {
      // meState loads once per login (the initializer no longer re-runs on auth refreshes),
      // so re-check live before rejecting — the player may have deployed a dino after opening the page.
      const fresh = await api.meState().then((r) => r.data).catch(() => null);
      if (fresh) setMeState(fresh);
      if (!fresh?.in_game) { toast.error("Despliega un dino primero — se aplica a tu Dino en Vivo."); play("error"); return; }
    }
    if (cooldown > 0) return;
    setApplying(true);
    try {
      // SkinPayloadIn (backend) is flat: {pattern, body, markings, flank, underbelly, detail1,
      // eyes, male_display, ...}. buildApplyColors already returns exactly those channel keys,
      // so spread it at the top level — species is never sent, the server derives it from the
      // caller's own active dino.
      if (exactCopy) {
        // Armed exact copy: the server replays the witnessed bytes verbatim —
        // the editor approximation on screen is display-only.
        await api.applyPresetExact(exactCopy.presetId);
      } else {
        await api.applySkinLive({ pattern, ...buildApplyColors(fleetColors) });
      }
      setCooldown(APPLY_COOLDOWN);
      // Confirm the change actually landed before declaring success — brief poll, never blocks the UI for long.
      let confirmed = false;
      for (let i = 0; i < 5; i++) {
        await new Promise((res) => setTimeout(res, 700));
        try { const snap = await api.skinSnapshot(); if (snap?.data) { confirmed = true; break; } } catch (e) { /* keep trying until the loop ends */ }
      }
      play("success");
      toast.success("¡Skin aplicada a tu Dino en Vivo!", { description: confirmed ? "Confirmada por el servidor." : "Enviada — confirmando con el servidor…" });
      api.meState().then((r) => setMeState(r.data)).catch(() => {});
    } catch (e) {
      play("error");
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.code === "patreon_required") {
        // Server re-verified live and denied: refresh the verdict and show the full explanation.
        if (detail.access) setAccess(detail.access);
        setGateOpen(true);
      } else if (detail && typeof detail === "object" && detail.code === "tier_insufficient") {
        // Allowed patron/role holder whose tier does not include the skin creator (Juvie).
        if (detail.access) setAccess(detail.access);
        toast.error(detail.message || "Tu nivel de Patreon no incluye el creador de skins.");
      } else if (exactCopy && [400, 404, 422].includes(e?.response?.status)) {
        // The armed exact copy is gone or no longer valid server-side — disarm
        // honestly instead of silently applying the clamped approximation.
        setExactCopy(null);
        toast.error(typeof detail === "string" && detail.trim() ? detail : "La copia exacta ya no está disponible — vuelve a pulsar «Copiar mi skin actual».");
      } else {
        toast.error(typeof detail === "string" && detail.trim() ? detail : "Falló al aplicar");
      }
    }
    finally { setApplying(false); }
  };

  const savePreset = async () => {
    if (!selKey) return;
    setSaving(true);
    try {
      // Backend SkinPresetIn expects exactly {name, dino_class, payload: SkinPayloadIn} —
      // no top-level species/colors/preview (the backend model has no preview field at all).
      const payload = { pattern, ...buildApplyColors(fleetColors) };
      await api.presetsSave({ name: presetName.trim() || `${selected?.name || selKey} skin`, dino_class: selKey, payload });
      play("success"); toast.success("Preset guardado"); setPresetName(""); loadPresets();
    } catch (e) { play("error"); toast.error(e?.response?.data?.detail || "No se pudo guardar"); }
    finally { setSaving(false); }
  };

  // Copy the skin the player's LIVE dinosaur is wearing right now into the
  // editor, and keep it as a saved preset (owner feature 2026-08-07: "copy
  // current skins … it gets saved as a skin for them"). Reading the snapshot
  // and saving a preset are both free — only APPLYING a skin is Patreon-gated,
  // so this button deliberately sits outside the gate.
  const copyCurrentSkin = async () => {
    if (copying) return;
    setCopying(true);
    try {
      const r = await api.skinSnapshot();
      const data = r?.data;
      if (!data?.active) {
        play("error");
        toast.error("Despliega un dino primero — la skin actual se lee de tu Dino en Vivo.");
        return;
      }
      const bare = bareClass(data.class);
      const sp = (speciesList || []).find((s) => String(speciesKey(s) || "").toLowerCase() === bare.toLowerCase()) || null;
      const converted = snapshotToEditorSkin(data.skin, getSpeciesDefaultColors(sp || bare), speciesKey(sp) || bare);
      if (!converted.ok) {
        play("error");
        toast.error(converted.reason === "none"
          ? "Tu dino aún no tiene una lectura de skin en el servidor. Espera unos segundos y vuelve a intentarlo."
          : "La lectura de skin no es utilizable ahora mismo (servidor recién reiniciado). Vuelve a intentarlo en un momento.");
        return;
      }
      if (sp) setSelected(sp);
      setFleetColors(converted.colors);
      setPattern(converted.pattern);
      // The save is the point of the feature — but the editor load above is
      // already done, so a failed save reports the honest partial outcome.
      const dinoClass = sp ? speciesKey(sp) : bare;
      const label = `Skin actual — ${String(sp?.name || bare || "dino").slice(0, 40)}`.slice(0, 64);
      // Verbatim sidecar: when the live skin can't survive the editor's gamut
      // (glitch payloads), the preset keeps the raw bytes and Aplicar arms an
      // exact replay — otherwise a copied glitch skin re-applies re-authored
      // (owner report 2026-08-08: "when i copy the current skin is different").
      // allowGlitch: Glitch-Lab-entitled accounts (Owner + Streamer + Adult/Elder/Apex)
      // may copy a worn PAST-SENTINEL glitch look exactly; the backend
      // re-verifies the entitlement itself on save (stamps glitch_grant).
      const raw = extractRawSnapshot(data.skin, { allowGlitch: !!glitchAccess?.allowed });
      try {
        const saveBody = { name: label, dino_class: dinoClass, payload: { pattern: converted.pattern, ...buildApplyColors(converted.colors) } };
        if (raw) saveBody.raw = raw;
        const saved = await api.presetsSave(saveBody);
        loadPresets();
        play("success");
        const exact = Boolean(raw && rawIsLossy(raw) && saved?.data?.id != null);
        setExactCopy(exact ? { presetId: saved.data.id, name: label } : null);
        toast.success("Skin actual copiada al editor", {
          description: exact
            ? `Guardada como "${label}" con copia exacta — Aplicar la enviará tal cual la lleva tu dino.`
            : `Guardada en tus presets como "${label}".`,
        });
      } catch (e2) {
        play("error");
        setExactCopy(null);
        const d2 = e2?.response?.data?.detail;
        toast.error(typeof d2 === "string" && d2.trim() ? d2 : "Skin cargada en el editor, pero no se pudo guardar el preset. Usa el botón de guardar en Presets.");
      }
    } catch (e) {
      play("error");
      const detail = e?.response?.data?.detail;
      toast.error(typeof detail === "string" && detail.trim() ? detail : "No se pudo leer tu skin actual. Inténtalo de nuevo.");
    } finally {
      setCopying(false);
    }
  };

  // Copy the CURRENT design (species + pattern + all slot colours) as a shareable code.
  const exportCurrentCode = async () => {
    if (!selKey) { play("error"); toast.error("Elige una especie primero — el código de skin incluye la especie."); return; }
    const code = encodeSkinCode(selKey, { pattern, ...buildApplyColors(fleetColors) });
    const ok = await copyTextToClipboard(code);
    if (ok) { play("success"); toast.success("Código de skin copiado", { description: "Pégalo aquí mismo en Importar, o compártelo con quien quieras." }); }
    else { play("error"); toast.error("No se pudo copiar al portapapeles. Inténtalo de nuevo."); }
  };

  // Copy a SAVED preset as a shareable code. A preset holding an exact-copy
  // sidecar exports a LIN2 code (the raw floats VERBATIM — what makes copying
  // someone else's skin actually apply); otherwise the classic LIN1 code.
  // Grant keys never ride a code (encodeGlitchCode strips them).
  const copyPresetCode = async (p) => {
    let code = p?.raw ? encodeGlitchCode(p.dino_class || selKey || "", p.raw) : null;
    if (!code) code = encodeSkinCode(p.dino_class || selKey || "", p.payload || {});
    const ok = await copyTextToClipboard(code);
    if (ok) {
      play("success");
      toast.success(`Código de "${p.name || "preset"}" copiado`, {
        description: p?.raw ? "Código exacto (LIN2): quien lo importe recibe la skin byte a byte." : undefined,
      });
    } else { play("error"); toast.error("No se pudo copiar al portapapeles. Inténtalo de nuevo."); }
  };

  const importFromCode = () => {
    // LIN2 exact codes first: raw engine floats, byte-for-byte.
    const exact = decodeGlitchCode(importCode);
    if (exact) {
      const sp = (speciesList || []).find((s) => speciesKey(s) === exact.dinoClass);
      if (rawIsLossy(exact.raw)) {
        // Out-of-editor payload: reproduced exactly only through the Glitch Lab.
        if (!glitchAccess?.allowed) {
          if (rawNeedsGlitchLab(exact.raw)) {
            // Sentinel-band glitch: no honest approximation exists — refuse.
            play("error");
            toast.error("Este código es una skin glitch", {
              description: "Importarla requiere una cuenta Owner, el rol Streamer o Patreon Adult, Elder o Apex.",
            });
            return;
          }
          // Mild out-of-gamut payload: load the clamped approximation, honestly.
          const approx = snapshotToEditorSkin(exact.raw, getSpeciesDefaultColors(sp || bareClass(exact.dinoClass)), speciesKey(sp) || bareClass(exact.dinoClass));
          if (approx.ok) {
            if (sp) setSelected(sp);
            setExactCopy(null);
            setFleetColors(approx.colors);
            setPattern(approx.pattern);
            setImportCode("");
            play("success");
            toast.message("Importado como aproximación", {
              description: "Este diseño usa valores fuera del editor — la copia exacta requiere el Glitch Lab (Owner, Streamer o Adult/Elder/Apex).",
            });
            return;
          }
          play("error");
          toast.error("Código de skin no válido", { description: "El código LIN2 no se pudo cargar." });
          return;
        }
        if (sp) setSelected(sp);
        setGlitchFields(rawToFields(exact.raw));
        setImportCode("");
        setTab("glitch");
        play("success");
        toast.success("Skin glitch importada al Glitch Lab", {
          description: "Números cargados tal cual — pulsa Aplicar para llevarla a tu Dino en Vivo.",
        });
        return;
      }
      // In-gamut exact code: the editor can hold it — load it like a snapshot.
      const converted = snapshotToEditorSkin(exact.raw, getSpeciesDefaultColors(sp || bareClass(exact.dinoClass)), speciesKey(sp) || bareClass(exact.dinoClass));
      if (converted.ok) {
        if (sp) setSelected(sp);
        setExactCopy(null);
        setFleetColors(converted.colors);
        setPattern(converted.pattern);
        setImportCode("");
        play("success");
        toast.success("Diseño exacto importado", {
          description: sp
            ? `Especie ${sp.name || exact.dinoClass} y colores cargados en el editor.`
            : "Colores cargados. La especie del código no está disponible — se mantiene tu especie actual.",
        });
        return;
      }
      play("error");
      toast.error("Código de skin no válido", { description: "El código LIN2 no se pudo cargar." });
      return;
    }
    const decoded = decodeSkinCode(importCode);
    if (!decoded) { play("error"); toast.error("Código de skin no válido", { description: "Revisa que el código esté completo y empiece por LIN1- o LIN2-." }); return; }
    const sp = (speciesList || []).find((s) => speciesKey(s) === decoded.dinoClass);
    if (sp) setSelected(sp);
    setExactCopy(null);
    setFleetColors(decoded.colors);
    setPattern(decoded.pattern);
    setImportCode("");
    play("success");
    toast.success("Diseño importado", {
      description: sp
        ? `Especie ${sp.name || decoded.dinoClass} y colores cargados en el editor.`
        : `Colores cargados. La especie del código (${decoded.dinoClass || "desconocida"}) no está disponible — se mantiene tu especie actual.`,
    });
  };

  // Delete a SAVED preset (server DELETE /presets/{id}). Always confirmed via the modal
  // first — a saved design is only recoverable afterwards if the player still has its
  // LIN1- code, so never one-click destroy. Fully exception-contained; the removal is
  // optimistic (id-scoped filter, no full reload) and a 404 (already gone on another
  // tab) reconciles the row away silently instead of erroring.
  const deletePreset = async (p) => {
    const id = p?.id;
    if (id == null) { setConfirmDelete(null); return; }
    setDeletingId(id);
    try {
      await api.presetsDelete(id);
      setPresets((prev) => prev.filter((x) => x.id !== id));
      if (exactCopy?.presetId === id) setExactCopy(null);
      play("success");
      toast.success(`Preset "${p.name || "preset"}" eliminado`);
    } catch (e) {
      if (e?.response?.status === 404) {
        setPresets((prev) => prev.filter((x) => x.id !== id));
        toast.message("Ese preset ya no existía.");
      } else {
        play("error");
        toast.error(e?.response?.data?.detail || "No se pudo eliminar el preset");
      }
    } finally {
      setDeletingId(null);
      setConfirmDelete(null);
    }
  };

  const loadPreset = (p) => {
    const sp = (speciesList || []).find((s) => speciesKey(s) === p.dino_class);
    if (sp) setSelected(sp);
    const payload = p.payload || {};
    const colors = { ...DEFAULT_FLEET_COLORS };
    SLOT_ORDER.forEach((k) => { if (payload[k]) colors[k] = srgb01ToHex([payload[k].r, payload[k].g, payload[k].b, payload[k].a]); });
    setFleetColors(colors);
    setPattern(typeof payload.pattern === "number" ? payload.pattern : 0);
    setPresetName(p.name || "");
    // A preset carrying a lossy exact-copy sidecar re-arms verbatim apply; the
    // editor shows the clamped approximation, the server holds the real bytes.
    setExactCopy(p?.raw && rawIsLossy(p.raw) && p.id != null ? { presetId: p.id, name: p.name || "" } : null);
    play("click");
  };

  return (
    <div className="max-w-[1280px] mx-auto px-6 py-6">
      <PatreonGateModal open={gateOpen} access={access} onClose={() => setGateOpen(false)} onAccess={(a) => { setAccess(a); if (a?.allowed) setGateOpen(false); }} play={play} />
      <ConfirmModal
        open={!!confirmDelete}
        onClose={() => { if (deletingId == null) setConfirmDelete(null); }}
        onConfirm={() => confirmDelete && deletePreset(confirmDelete)}
        loading={deletingId != null}
        tone="danger"
        icon={<Trash2 size={30} />}
        title="¿Eliminar preset?"
        message={confirmDelete ? <>Se eliminará <span className="text-foreground font-semibold">{confirmDelete.name || "este preset"}</span> de forma permanente. Podrás volver a crearlo solo si guardaste su código de skin.</> : null}
        confirmLabel="Eliminar"
        abortLabel="Cancelar"
      />
      <div className="mb-3 flex items-center gap-2 flex-wrap" data-testid="patreon-access-banner">
        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-gold/15 text-gold border border-gold/30">PATREON ACCESS</span>
        {access === undefined ? (
          <span className="text-xs text-muted-foreground inline-flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Comprobando tu acceso…</span>
        ) : allowed ? (
          <span className="text-xs text-muted-foreground">
            Acceso activo{access?.tier ? <> · nivel <span className="text-gold font-semibold">{access.tier}</span></> : null}{access?.via === "admin" ? " · administrador" : null}
          </span>
        ) : (
          <>
            <span className="text-xs text-muted-foreground">Modo vista previa — diseña libremente; aplicar skins requiere Patreon</span>
            <button onClick={() => { setGateOpen(true); play("click"); }} data-testid="patreon-gate-why"
              className="text-xs font-bold text-gold hover:underline inline-flex items-center gap-1"><HelpCircle size={12} /> ¿Cómo lo desbloqueo?</button>
          </>
        )}
      </div>
      {/* Tabs */}
      <div className="flex items-center gap-6 border-b border-white/10 mb-5">
        <TabBtn active={tab === "population"} onClick={() => { setTab("population"); play("click"); }} icon={<BarChart3 size={15} />} label="POPULATION" testid="skintab-population" />
        <TabBtn active={tab === "designer"} onClick={() => { setTab("designer"); play("click"); }} icon={<Palette size={15} />} label="SKIN DESIGNER" testid="skintab-designer" />
        <TabBtn active={tab === "glitch"} onClick={() => { setTab("glitch"); play("click"); }} icon={<Zap size={15} />} label="GLITCH LAB" testid="skintab-glitch" />
      </div>

      {tab === "population" ? (
        access === undefined ? (
          <div className="py-20 text-center text-muted-foreground flex items-center justify-center gap-2"><Loader2 className="animate-spin" size={16} /> Comprobando tu acceso…</div>
        ) : allowed ? (
          <PopulationPanel play={play} />
        ) : (
          <PatreonGateBody access={access} onAccess={(a) => setAccess(a)} play={play} />
        )
      ) : tab === "glitch" ? (
        <GlitchLabPanel
          verdict={glitchAccess}
          onVerdict={(v) => setGlitchAccess(v)}
          fields={glitchFields}
          setFields={setGlitchFields}
          name={glitchName}
          setName={setGlitchName}
          speciesList={speciesList}
          selected={selected}
          setSelected={setSelected}
          cooldown={cooldown}
          setCooldown={setCooldown}
          meState={meState}
          setMeState={setMeState}
          loadPresets={loadPresets}
          importCode={importCode}
          setImportCode={setImportCode}
          importFromCode={importFromCode}
          play={play}
        />
      ) : (
        <div data-testid="skin-designer">
          {/* Species grid */}
          <div className="mb-5">
            <p className="label-overline text-[10px] text-emerald mb-2">Especie</p>
            {speciesList === undefined ? (
              <p className="text-sm text-muted-foreground inline-flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Cargando especies…</p>
            ) : speciesList.length === 0 ? (
              <p className="text-sm text-muted-foreground" data-testid="species-empty">No hay especies disponibles todavía.</p>
            ) : (
              <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-2" data-testid="species-grid">
                {speciesList.map((s) => {
                  const key = speciesKey(s);
                  const isSel = key === selKey;
                  return (
                    <button key={key} onClick={() => { setSelected(s); setExactCopy(null); setFleetColors(getSpeciesDefaultColors(s)); play("click"); }} data-testid={`species-card-${key}`}
                      className={`flex flex-col items-center gap-1 rounded-lg border p-2 transition-all ${isSel ? "border-emerald bg-emerald/10 text-emerald" : "border-white/10 bg-white/[0.02] text-muted-foreground hover:border-emerald/40 hover:text-foreground"}`}>
                      <div className="w-full aspect-square rounded bg-black/30 overflow-hidden flex items-center justify-center">
                        {s.image ? <img src={s.image} alt="" className="w-full h-full object-contain p-1" /> : <Palette size={16} />}
                      </div>
                      <span className="text-[10px] font-bold truncate w-full text-center">{s.name || key}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="grid lg:grid-cols-[270px_1fr_280px] gap-5 items-start">
            {/* LEFT: pattern + colours */}
            <div className="space-y-3">
              <NumBox label="Patrón" value={pattern} min={0} max={patternMax} onChange={(v) => { setExactCopy(null); setPattern(v); }} testid="skin-pattern" />

              <p className="label-overline text-[10px] text-emerald pt-1">Colores</p>
              <div className="space-y-1.5" data-testid="skin-colours">
                {SLOT_ORDER.map((key) => (
                  <RegionCard key={key} rkey={key} label={SLOT_LABELS[key]} value={fleetColors[key] || DEFAULT_FLEET_COLORS[key]}
                    onColor={(c) => setColor(key, c)} onAlpha={(a) => setAlpha(key, a)} />
                ))}
              </div>
            </div>

            {/* CENTER: 3D Viewer */}
            <SkinPreview3D species={selKey} colors={fleetColors} pattern={pattern}
              advancedColors={v2AdvancedForSpecies?.colors || null} advancedMapping={v2AdvancedForSpecies?.mapping || null}
              captureRef={captureRef} testid="skinlab-3d-viewer" />

            {/* RIGHT: apply + presets */}
            <div className="space-y-6">
              <div>
                <p className="label-overline text-[10px] text-emerald mb-1.5">Aplicar</p>
                <p className="text-xs text-muted-foreground mb-2.5">Aplica el diseño a tu dinosaurio <span className="text-foreground font-semibold">en vivo</span>. {APPLY_COOLDOWN} segundos de espera entre aplicaciones.</p>
                <button onClick={applyToLive} disabled={applying || !selKey || meState === undefined || access === undefined || cooldown > 0} data-testid="apply-to-live-dino"
                  className={`w-full inline-flex items-center justify-center gap-2 font-extrabold uppercase tracking-wide text-sm py-3 rounded-lg transition-all disabled:opacity-50 ${allowed || access === undefined
                    ? "bg-[#e8722a] text-white hover:brightness-110 shadow-lg shadow-[#e8722a]/20"
                    : "bg-white/5 text-muted-foreground border border-gold/30 hover:border-gold/60 hover:text-gold"}`}>
                  {applying ? <Loader2 size={15} className="animate-spin" /> : allowed || access === undefined ? <PaintBucket size={15} /> : <Lock size={15} />}
                  {cooldown > 0 ? `Espera ${cooldown}s` : applying ? "Aplicando…" : allowed || access === undefined ? "Aplicar a mi dinosaurio en vivo" : "Aplicar requiere Patreon"}
                </button>
                {!allowed && access !== undefined && (
                  <p className="text-[11px] text-muted-foreground mt-2">Pulsa el botón para ver exactamente qué te falta y cómo desbloquearlo.</p>
                )}
                {allowed && !inGame && meState !== undefined && <p className="text-[11px] text-amber-400/80 mt-2">No hay Dino en Vivo desplegado.</p>}
                {exactCopy && (
                  <p className="text-[11px] text-emerald mt-2" data-testid="exact-copy-armed">
                    Copia exacta armada — Aplicar enviará la skin tal cual la lleva tu dino (el editor solo muestra una aproximación). Editar cualquier color o patrón la desarma.
                  </p>
                )}
              </div>

              <div>
                <p className="label-overline text-[10px] text-emerald mb-1.5">Skin actual</p>
                <p className="text-xs text-muted-foreground mb-2.5">Copia la skin que tu dinosaurio lleva puesta <span className="text-foreground font-semibold">ahora mismo</span> al editor, y se guarda en tus presets.</p>
                <button onClick={copyCurrentSkin} disabled={copying} data-testid="copy-live-skin"
                  className="w-full inline-flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-wide py-2.5 rounded-lg glass border border-emerald/30 text-emerald hover:bg-emerald/10 transition-all disabled:opacity-50">
                  {copying ? <Loader2 size={13} className="animate-spin" /> : <Camera size={13} />} Copiar mi skin actual
                </button>
              </div>

              <div>
                <p className="label-overline text-[10px] text-emerald mb-1.5">Código de skin</p>
                <p className="text-xs text-muted-foreground mb-2.5">Comparte tu diseño como un código de texto, o pega el código de otra persona para cargarlo en el editor.</p>
                <button onClick={exportCurrentCode} disabled={!selKey} data-testid="skin-code-export"
                  className="w-full inline-flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-wide py-2.5 rounded-lg glass border border-emerald/30 text-emerald hover:bg-emerald/10 transition-all disabled:opacity-50 mb-2">
                  <Copy size={13} /> Copiar código del diseño
                </button>
                <div className="flex gap-2">
                  <input value={importCode} onChange={(e) => setImportCode(e.target.value)} placeholder="Pega un código LIN1- o LIN2-…" data-testid="skin-code-input" spellCheck={false}
                    onKeyDown={(e) => { if (e.key === "Enter" && importCode.trim()) importFromCode(); }}
                    className="flex-1 min-w-0 glass rounded-lg px-2.5 py-2 text-xs font-mono bg-transparent focus:outline-none focus:ring-2 focus:ring-emerald/40" />
                  <button onClick={importFromCode} disabled={!importCode.trim()} data-testid="skin-code-import" title="Importar diseño"
                    className="px-2.5 rounded-lg bg-emerald text-background hover:brightness-110 transition-all disabled:opacity-50">
                    <ClipboardPaste size={15} />
                  </button>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <p className="label-overline text-[10px] text-emerald">Presets</p>
                  <span className="text-[11px] text-muted-foreground">{presets.length}/100</span>
                </div>
                <div className="flex gap-2 mb-2.5">
                  <input value={presetName} onChange={(e) => setPresetName(e.target.value)} maxLength={40} placeholder="Nombre del preset…" data-testid="skin-preset-name"
                    className="flex-1 glass rounded-lg px-2.5 py-2 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-emerald/40" />
                  <button onClick={savePreset} disabled={saving || !selKey} data-testid="skin-preset-save"
                    className="px-2.5 rounded-lg bg-emerald text-background hover:brightness-110 transition-all disabled:opacity-50">
                    {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                  </button>
                </div>
                <div className="space-y-1 max-h-[360px] overflow-y-auto pr-1" data-testid="skin-presets">
                  {presets.length === 0 && <p className="text-xs text-muted-foreground">Aún no tienes presets.</p>}
                  {presets.map((p, i) => (
                    <div key={p.id ?? i} className="group flex items-center gap-2.5 rounded-lg p-1.5 hover:bg-white/5 transition-all cursor-pointer" data-testid={`skin-preset-${p.id ?? i}`} onClick={() => loadPreset(p)}>
                      <div className="w-8 h-8 rounded bg-black/40 overflow-hidden shrink-0 flex items-center justify-center">
                        {p.preview ? <img src={p.preview} alt="" className="w-full h-full object-cover" /> : <Palette size={13} className="text-muted-foreground" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[13px] font-bold truncate">
                          {p.name}
                          {p.raw && rawIsLossy(p.raw) && (
                            <span className="ml-1.5 align-middle inline-block text-[8px] font-extrabold uppercase tracking-wide px-1 py-px rounded bg-emerald/15 text-emerald border border-emerald/30" title="Guarda la skin byte a byte — al aplicarla se envía tal cual" data-testid={`skin-preset-exact-${p.id ?? i}`}>Exacta</span>
                          )}
                        </p>
                        <p className="text-[9px] text-muted-foreground">Actualizado {new Date(p.updated_at || p.created_at || Date.now()).toLocaleDateString()}</p>
                      </div>
                      <button onClick={(e) => { e.stopPropagation(); copyPresetCode(p); }} title="Copiar código de skin" data-testid={`skin-preset-copy-${p.id ?? i}`}
                        className="shrink-0 p-1.5 rounded-md text-muted-foreground opacity-40 group-hover:opacity-100 hover:text-emerald hover:bg-emerald/10 transition-all">
                        <Copy size={13} />
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); if (p.id != null) { setConfirmDelete(p); play("click"); } }} disabled={deletingId === p.id} title="Eliminar preset" data-testid={`skin-preset-delete-${p.id ?? i}`}
                        className="shrink-0 p-1.5 rounded-md text-muted-foreground opacity-40 group-hover:opacity-100 hover:text-crimson hover:bg-crimson/10 transition-all disabled:opacity-30">
                        {deletingId === p.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Skin contract v2 — renders ONLY when the game side published an enabled
              contract. Off (today's live state) this whole branch is nothing at all. */}
          {v2Contract?.enabled && (
            <SkinContractV2Panel contract={v2Contract} speciesKey={selKey} colors={fleetColors}
              pattern={pattern} allowed={allowed || access === undefined} play={play}
              onAdvancedPreview={setV2Advanced} />
          )}
        </div>
      )}
    </div>
  );
}

// How long an unlock window / its wait actually lasts, in the right words.
// Always rounding to minutes turned the 30 s window the owner asked for
// (2026-08-21) into "~1 min" and promised the player twice what the server
// gives; under a minute it has to say seconds. Falls back to `fallback` when
// the backend value is missing or junk.
function fmtUnlockSpan(seconds, fallback) {
  const raw = Number(seconds);
  const total = Math.max(0, Math.round(Number.isFinite(raw) && raw > 0 ? raw : fallback));
  return total < 60 ? `${total} s` : `${Math.max(1, Math.round(total / 60))} min`;
}

function PopulationPanel({ play }) {
  const [server, setServer] = useState("LIVE");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null);
  const [cds, setCds] = useState({});   // per-slug UNLOCK cooldown (folded w/ the global unlock cd)
  const [rcds, setRcds] = useState({}); // per-slug RESPAWN cooldown (unfolded + global swap cd)
  const [confirm, setConfirm] = useState(null); // { sp, mode: "respawn"|"unlock" }

  const load = (srv) => api.population(srv).then((r) => {
    setData(r.data);
    // TWO cooldown maps (2026-07-16): `cooldown_remaining` is FOLDED with the
    // 1h GLOBAL unlock cooldown and only ever gates Desbloquear; Respawn runs
    // on the unfolded per-slug value + the page-level swap cooldown.
    const swapGlobal = r.data.swap_cooldown_remaining || 0;
    const map = {}; const rmap = {};
    (r.data.species || []).forEach((s) => {
      if (s.cooldown_remaining > 0) map[s.slug] = s.cooldown_remaining;
      const rcd = Math.max(s.respawn_cooldown_remaining != null ? s.respawn_cooldown_remaining : (s.cooldown_remaining || 0), swapGlobal);
      if (rcd > 0) rmap[s.slug] = rcd;
    });
    setCds(map);
    setRcds(rmap);
  }).catch(() => {});

  useEffect(() => {
    load(server);
    const t = setInterval(() => load(server), 20000);
    return () => clearInterval(t);
  }, [server]);

  // local 1s countdown across both cooldown maps
  useEffect(() => {
    const tick = (prev) => {
      const next = {}; let changed = false;
      for (const k in prev) { const v = Math.max(0, prev[k] - 1); if (v > 0) next[k] = v; if (v !== prev[k]) changed = true; }
      return changed ? next : prev;
    };
    const t = setInterval(() => { setCds(tick); setRcds(tick); }, 1000);
    return () => clearInterval(t);
  }, []);

  const doAction = async (sp, mode) => {
    const cd = (mode === "respawn" ? rcds[sp.slug] : cds[sp.slug]) || 0;
    if (cd > 0) { play("error"); toast.error(`${sp.name} en cooldown · ${fmtTime(cd)}`); setConfirm(null); return; }
    setBusy(sp.slug);
    try {
      const r = mode === "respawn" ? await api.populationRespawn(server, sp.slug) : await api.populationUnlock(server, sp.slug);
      play("success");
      const cdVal = r.data.cooldown_remaining;
      if (mode === "respawn") {
        const growth = r.data.growth_pct ? ` · ${r.data.growth_pct}% de crecimiento` : "";
        toast.success(`Respawn como ${sp.name}`, { description: `Tu dino cambió en el juego${growth}` });
        if (cdVal > 0) setRcds((p) => ({ ...p, [sp.slug]: cdVal }));
      } else {
        toast.success(`${sp.name} desbloqueado`, { description: `Bypass global del límite en ${server} · aparece en la selección del juego en unos segundos` });
        if (cdVal > 0) setCds((p) => ({ ...p, [sp.slug]: cdVal }));
      }
      setConfirm(null);
      load(server);
    } catch (e) {
      play("error");
      toast.error(e?.response?.data?.detail || "No se pudo completar");
      setConfirm(null);
      if (e?.response?.status === 429) load(server);
    } finally { setBusy(null); }
  };

  if (!data) return (
    <div className="py-20 text-center text-muted-foreground flex items-center justify-center gap-2" data-testid="population-loading">
      <Loader2 className="animate-spin" size={16} /> Cargando población…
    </div>
  );

  const activeSp = data.in_game && data.active_slug ? (data.species.find((x) => x.slug === data.active_slug) || {}) : null;

  return (
    <div data-testid="population-panel" className="space-y-5">
      <ConfirmModal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        onConfirm={() => confirm && doAction(confirm.sp, confirm.mode)}
        loading={!!busy}
        tone={confirm?.mode === "respawn" ? "danger" : "gold"}
        title={confirm ? (confirm.mode === "respawn" ? `¿Respawn como ${confirm.sp.name}?` : `¿Desbloquear ${confirm.sp.name}?`) : ""}
        message={confirm ? (confirm.mode === "respawn"
          ? <>Tu dinosaurio actual se transformará al instante en un <span className="text-foreground font-semibold">{confirm.sp.name}</span> recién nacido al <span className="text-gold font-semibold">{data.swap_growth_pct || 25}% de crecimiento</span>, en el mismo lugar donde estás, <span className="text-crimson font-semibold">aunque la especie esté al límite</span>. Tu dinosaurio actual se perderá.</>
          : <>Desbloquearás <span className="text-foreground font-semibold">{confirm.sp.name}</span> <span className="text-gold font-semibold">globalmente</span> en <span className="text-gold font-semibold">{server}</span>. Se ignora el límite y queda jugable para todos en ese servidor (~{fmtUnlockSpan(data.unlock_total, 300)}). Después esperarás {fmtUnlockSpan(data.unlock_cooldown_total, 3600)} para volver a desbloquear (cualquier especie).</>) : null}
        warning={confirm?.mode === "respawn" ? "ESTO NO SE PUEDE DESHACER" : null}
        confirmLabel={confirm?.mode === "respawn" ? "Confirmar respawn" : "Desbloquear global"}
        abortLabel="Abortar"
      />

      {/* ===== Perk banner ===== */}
      <div className="relative overflow-hidden rounded-2xl border border-gold/25 bg-gradient-to-r from-gold/[0.07] via-transparent to-transparent p-4 sm:p-5" data-testid="pop-ability-bar">
        <HudGrid color="rgba(124, 168, 66,0.06)" cell={30} />
        <HudCorners color="rgba(124, 168, 66,0.6)" size={18} />
        <div className="relative flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0 bg-gold/20 text-gold"><Zap size={22} /></div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-gold/15 text-gold border border-gold/30 inline-flex items-center gap-1"><Crown size={10} /> PATREON</span>
              <p className="text-sm font-extrabold tracking-wide truncate">Bypass de Límites de Dinos</p>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              <span className="text-crimson font-semibold">Rojo</span> = a máxima capacidad · <span className="text-gold font-semibold">Dorado</span> = ya desbloqueado en este servidor. Desbloquear es <span className="text-foreground font-semibold">global por servidor</span> · <span className="text-crimson font-semibold">Respawn</span> = cámbiate tú al instante a una especie llena (en juego).
            </p>
          </div>
          {activeSp && (
            <div className="shrink-0 hidden sm:flex items-center gap-2 rounded-lg border border-[#A3C96B]/30 bg-[#A3C96B]/[0.06] px-3 py-2" data-testid="pop-ingame">
              <span className="relative flex h-2 w-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#A3C96B] opacity-70" /><span className="relative inline-flex rounded-full h-2 w-2 bg-[#A3C96B]" /></span>
              <span className="text-[11px]"><span className="text-[#A3C96B] font-bold uppercase">En juego</span> · {activeSp.name || data.active_slug}</span>
            </div>
          )}
        </div>
      </div>

      {/* ===== Server selector ===== */}
      <div className="flex flex-wrap items-center gap-2">
        {data.servers.map((s) => (
          <button key={s.id} onClick={() => { setServer(s.id); play("click"); }} data-testid={`pop-server-${s.id}`}
            className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all inline-flex items-center gap-2 ${server === s.id ? "bg-gold text-background shadow-lg shadow-gold/20" : "glass border border-white/10 hover:border-gold/40 text-muted-foreground hover:text-foreground"}`}>
            {s.label}
            <span className={`inline-flex items-center gap-1 font-mono ${server === s.id ? "text-background/80" : "text-muted-foreground"}`}><Users size={11} /> {s.players}</span>
          </button>
        ))}
        <span className="ml-auto text-xs text-muted-foreground inline-flex items-center gap-1.5">
          <Users size={13} /> {data.total_players} en línea · {data.servers.length} servidores
        </span>
      </div>

      {/* ===== Species grid ===== */}
      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2.5" data-testid="population-grid">
        {data.species.map((sp) => {
          const unlockCd = cds[sp.slug] || 0;
          const respawnCd = rcds[sp.slug] || 0;
          const isActive = sp.is_active;
          const unlocked = sp.unlocked;                 // gold state
          const atCap = sp.at_cap && !unlocked;         // red state
          // FULL-species perk pair (owner ruling 2026-07-16): a species at max
          // capacity offers BOTH choices — Desbloquear (global, ~5 min) and
          // Respawn (swap yourself into it, in-game only). Free species get
          // neither (spawn from the in-game menu like normal).
          const overCapacity = sp.cap != null && sp.online >= sp.cap;
          const canRespawn = data.in_game && !isActive && overCapacity && !sp.locked;
          // accent color drives border / brackets / name / count / bar (web theme: gold / crimson / soft-gold / neutral)
          const accent = isActive ? "#A3C96B" : unlocked ? "#7CA842" : atCap ? "#E24A4A" : "#7C8590";
          const accentRgb = isActive ? "232,199,102" : unlocked ? "124, 168, 66" : atCap ? "226,74,74" : "124,133,144";
          // buttons: 0..2 actions per card, stacked when both apply. Each
          // action carries ITS OWN cooldown timer — the unlock timer (folded
          // with the 1h global unlock cd) must never hide the Respawn perk.
          const buttons = [];
          if (isActive) buttons.push({ key: "active", label: <><RotateCw size={12} /> En juego</>, cls: "bg-[#A3C96B]/15 text-[#A3C96B] border border-[#A3C96B]/40" });
          else {
            if (atCap) {
              if (unlockCd > 0) buttons.push({ key: "cd", label: <><Timer size={12} /> {fmtTime(unlockCd)}</>, cls: "glass border border-white/10 text-muted-foreground" });
              else buttons.push({ key: "unlock", mode: "unlock", actionable: true, label: <><Unlock size={12} /> Desbloquear</>, cls: "border text-gold hover:bg-gold/10", style: { borderColor: "#7CA842" } });
            }
            if (canRespawn && data.swap_enabled !== false) {
              if (respawnCd > 0) buttons.push({ key: "rcd", label: <><Timer size={12} /> {fmtTime(respawnCd)}</>, cls: "glass border border-white/10 text-muted-foreground" });
              else buttons.push({ key: "respawn", mode: "respawn", actionable: true, label: <><RotateCw size={12} /> Respawn</>, cls: "bg-crimson text-white hover:brightness-110 shadow-md shadow-crimson/20" });
            }
            if (buttons.length === 0) buttons.push({ key: "playable", label: <>Jugable</>, cls: "glass border border-white/10 text-muted-foreground" });
          }
          return (
            <div key={sp.slug} data-testid={`pop-card-${sp.slug}`}
              className="relative group overflow-hidden bg-[#0b0d0c] transition-all"
              style={{ borderRadius: 4, border: `1px solid rgba(${accentRgb},0.35)` }}>
              <HudCorners color={`rgba(${accentRgb},0.85)`} size={14} thickness={2} />
              <div className="aspect-square relative flex items-center justify-center overflow-hidden">
                <HudGrid color={`rgba(${accentRgb},0.07)`} cell={20} />
                <span className="absolute inset-0 flex items-center justify-center text-[20px] font-display font-extrabold uppercase tracking-tighter whitespace-nowrap select-none pointer-events-none" style={{ color: `rgba(${accentRgb},0.07)` }}>{sp.name}</span>
                {/* store dino image (same source as the Store) */}
                <img src={sp.image} alt={sp.name} className="relative w-full h-full object-contain p-2 drop-shadow-lg" />
                {/* state badge top-right */}
                <span className="absolute top-2 right-2 text-[8px] font-extrabold px-1.5 py-1 inline-flex items-center gap-1" style={{ borderRadius: 3, color: accent, border: `1px solid ${accent}`, background: `rgba(${accentRgb},0.10)` }} data-testid={`pop-state-${sp.slug}`}>
                  {isActive ? <><RotateCw size={9} /> TU DINO</> : unlocked ? <><Unlock size={9} /> DESBLOQUEADO</> : atCap ? <><Lock size={9} /> LLENO</> : <><Unlock size={9} /> LIBRE</>}
                </span>
              </div>
              <div className="p-2">
                <div className="flex items-center justify-between gap-1">
                  <p className="text-[11px] font-extrabold uppercase tracking-wide truncate" style={{ color: unlocked ? "#7CA842" : atCap ? "#E24A4A" : undefined }}>{sp.name}</p>
                  {sp.apex && <span className="shrink-0 text-[7px] font-extrabold px-1 py-0.5 inline-flex items-center gap-0.5 text-gold border border-gold/40" style={{ borderRadius: 3 }}><Flame size={7} /> APEX+</span>}
                </div>
                <div className="flex items-end justify-between mt-1.5">
                  <span className="text-[8px] text-muted-foreground uppercase tracking-wider mb-0.5">Online</span>
                  <span className="font-mono font-extrabold text-base leading-none" style={{ color: unlocked ? "#7CA842" : atCap ? "#E24A4A" : "#e6e6e6" }} data-testid={`pop-count-${sp.slug}`}>
                    {sp.online}<span className="text-muted-foreground text-[10px] font-bold"> / {sp.cap}</span>
                  </span>
                </div>
                <div className="mt-1"><SegBar value={Math.min(sp.online, sp.cap)} max={sp.cap} color={accent} height={5} /></div>
                {buttons.map((b, bi) => (
                  <button
                    key={b.key}
                    onClick={() => { if (!b.actionable) return; play("click"); setConfirm({ sp, mode: b.mode }); }}
                    disabled={busy === sp.slug || !b.actionable}
                    data-testid={b.key === "respawn" ? `pop-respawn-${sp.slug}` : `pop-select-${sp.slug}`}
                    style={b.style}
                    className={`${bi === 0 ? "mt-2" : "mt-1"} w-full text-[9px] font-extrabold uppercase tracking-wider py-2 transition-all disabled:cursor-not-allowed inline-flex items-center justify-center gap-1 ${b.cls}`}>
                    {busy === sp.slug ? <Loader2 size={11} className="animate-spin" /> : b.label}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ===== Patreon gate: the full "why can't I apply" explanation =====
// Server verdict (live Discord role read) rendered as a requirements checklist with
// the user's exact status per requirement plus the action that fixes it.

function GateRow({ ok, title, detail, action, testid }) {
  // ok: true = met, false = not met, null = could not be verified right now
  const Icon = ok === true ? Check : ok === false ? X : HelpCircle;
  const tone = ok === true ? "text-emerald border-emerald-500/30 bg-emerald-500/10"
    : ok === false ? "text-crimson border-crimson/30 bg-crimson/10"
    : "text-muted-foreground border-white/15 bg-white/5";
  return (
    <div className="flex items-start gap-3 py-3 border-b border-white/5 last:border-0" data-testid={testid}>
      <span className={`mt-0.5 w-6 h-6 shrink-0 rounded-full border flex items-center justify-center ${tone}`}><Icon size={13} /></span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-bold leading-tight">{title}</p>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{detail}</p>
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  );
}

function PatreonGateBody({ access, onAccess, play, compactClose }) {
  const [checking, setChecking] = useState(false);
  const [linking, setLinking] = useState(null);
  const d = access?.discord || {};
  const p = access?.patreon || {};
  const tiers = (access?.tier_roles && access.tier_roles.length) ? access.tier_roles : ["Apex", "Elder", "Adult", "Sub Adult", "Juvie"];
  const tierList = tiers.join(", ");

  const recheck = async () => {
    setChecking(true);
    try {
      const r = await api.patreonAccess(true);
      onAccess?.(r.data);
      if (r.data?.allowed) { play?.("success"); toast.success("Acceso Patreon verificado", { description: r.data.tier ? `Nivel ${r.data.tier} detectado. Ya puedes aplicar skins.` : "Ya puedes aplicar skins." }); }
      else { play?.("click"); toast.message("Todavía sin acceso Patreon", { description: "Revisa los requisitos de abajo. La comprobación es en vivo." }); }
    } catch { play?.("error"); toast.error("No se pudo comprobar tu acceso. Inténtalo de nuevo."); }
    finally { setChecking(false); }
  };

  const startLink = async (provider) => {
    play?.("click");
    setLinking(provider);
    try {
      const { data } = await api.integrationsStart();
      externalRedirect(`${API}/${provider}/login?token=${data.link_token}`);
    } catch {
      play?.("error");
      toast.error("No se pudo iniciar la vinculación. Inténtalo de nuevo.");
      setLinking(null);
    }
  };

  const linkBtn = (provider, label) => (
    <button onClick={() => startLink(provider)} disabled={linking === provider}
      data-testid={`gate-link-${provider}`}
      className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg bg-gold text-background hover:brightness-110 transition-all disabled:opacity-60">
      {linking === provider ? <Loader2 size={12} className="animate-spin" /> : <Link2 size={12} />} {label}
    </button>
  );

  const unknownNote = "No se pudo verificar en este momento (Discord no respondió). Espera unos segundos y pulsa \"Volver a comprobar\".";

  return (
    <div data-testid="patreon-gate">
      <div className="flex items-start gap-3 mb-4">
        <div className="w-11 h-11 rounded-xl bg-gold/15 border border-gold/30 flex items-center justify-center shrink-0"><Lock size={20} className="text-gold" /></div>
        <div>
          <h2 className="font-display font-extrabold text-xl leading-tight">Aplicar skins es un beneficio Patreon</h2>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
            Puedes usar el diseñador libremente, pero aplicar el diseño a tu dinosaurio en vivo está reservado
            a los suscriptores de Patreon de La Isla Nublar. Tu suscripción se verifica con el rol de nivel
            que recibes en nuestro servidor de Discord ({tierList}).
          </p>
        </div>
      </div>

      <div className="glass rounded-xl px-4 py-1 mb-4">
        <GateRow
          testid="gate-discord-linked"
          ok={d.linked === true}
          title="1 · Cuenta de Discord vinculada al sitio"
          detail={d.linked
            ? <>Vinculada{access?.discord?.username ? ` como ${access.discord.username}` : ""}. El sitio puede leer tus roles del servidor.</>
            : "Sin tu Discord vinculado el sitio no puede saber qué roles tienes. Vincúlalo aquí mismo — tarda unos segundos."}
          action={!d.linked && linkBtn("discord", "Vincular Discord")}
        />
        <GateRow
          testid="gate-discord-guild"
          ok={!d.linked ? false : d.in_guild === true ? true : d.in_guild === false ? false : null}
          title="2 · Miembro del servidor de Discord de La Isla Nublar"
          detail={!d.linked
            ? "Se comprueba después de vincular tu Discord."
            : d.in_guild === true ? "Estás en el servidor."
            : d.in_guild === false ? "Tu cuenta de Discord no está en el servidor de La Isla Nublar. Únete al servidor y vuelve a comprobar."
            : unknownNote}
        />
        <GateRow
          testid="gate-tier-role"
          ok={d.tier_role ? true : (!d.linked || d.in_guild === false) ? false : d.in_guild === true ? false : null}
          title="3 · Rol de nivel Patreon en Discord"
          detail={d.tier_role
            ? <>Tienes el rol <span className="text-gold font-semibold">{d.tier_role}</span>. Este rol te da acceso completo.</>
            : d.in_guild === true
              ? <>No tienes ninguno de los roles de nivel Patreon ({tierList}). El rol se asigna en Discord al suscribirte en Patreon con tu cuenta de Discord conectada. Si ya eres suscriptor y no ves tu rol, pide al staff en Discord que te lo asigne — en cuanto lo tengas, el acceso es inmediato.</>
              : <>Necesitas uno de los roles de nivel Patreon: {tierList}. Se comprueba en cuanto tu Discord esté vinculado y seas miembro del servidor.</>}
        />
        <GateRow
          testid="gate-patreon-alt"
          ok={p.active === true}
          title="Alternativa · Patreon vinculado directamente al sitio"
          detail={p.active
            ? <>Suscripción de Patreon activa{p.tier_name ? ` (${p.tier_name})` : ""}.</>
            : p.linked
              ? "Tu Patreon está vinculado pero no consta una suscripción activa. Si acabas de suscribirte, sincroniza desde tu Perfil o vuelve a comprobar."
              : "Si prefieres no vincular Discord, puedes vincular tu cuenta de Patreon con la suscripción activa y el sitio la verificará directamente."}
          action={!p.active && linkBtn("patreon", p.linked ? "Volver a vincular Patreon" : "Vincular Patreon")}
        />
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={recheck} disabled={checking} data-testid="gate-recheck"
          className="inline-flex items-center gap-2 text-sm font-bold px-4 py-2.5 rounded-lg bg-emerald text-background hover:brightness-110 transition-all disabled:opacity-60">
          {checking ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Volver a comprobar
        </button>
        <p className="text-[11px] text-muted-foreground">La comprobación es en vivo: si acabas de recibir tu rol en Discord, se detecta al instante.</p>
        {compactClose}
      </div>
    </div>
  );
}

function PatreonGateModal({ open, access, onClose, onAccess, play }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" data-testid="patreon-gate-modal">
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={onClose} />
      <motion.div initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        className="relative glass-strong rounded-2xl border border-white/10 p-6 w-full max-w-xl max-h-[85vh] overflow-y-auto">
        <button onClick={onClose} data-testid="patreon-gate-close"
          className="absolute top-3 right-3 p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"><X size={16} /></button>
        <PatreonGateBody access={access} onAccess={onAccess} play={play} />
      </motion.div>
    </div>
  );
}

function TabBtn({ active, onClick, icon, label, testid }) {
  return (
    <button onClick={onClick} data-testid={testid}
      className={`inline-flex items-center gap-2 pb-3 -mb-px text-sm font-bold tracking-wide border-b-2 transition-all ${active ? "text-gold border-gold" : "text-muted-foreground border-transparent hover:text-foreground"}`}>
      {icon} {label}
    </button>
  );
}

function NumBox({ label, value, min, max, onChange, testid }) {
  return (
    <label className="block">
      <span className="label-overline text-[9px] text-muted-foreground">{label}</span>
      <input type="number" min={min} max={max} value={value} data-testid={testid}
        onChange={(e) => onChange(Math.max(min, Math.min(max, parseInt(e.target.value || "0", 10))))}
        className="mt-1 w-full glass rounded-lg px-2 py-2 text-xs bg-transparent focus:outline-none focus:ring-2 focus:ring-emerald/40" />
    </label>
  );
}

function RegionCard({ rkey, label, value, onColor, onAlpha }) {
  return (
    <div className="glass rounded-lg px-2.5 py-2 flex items-center gap-2.5" data-testid={`skin-region-${rkey}`}>
      <label className="relative shrink-0">
        <span className="block w-8 h-8 rounded border border-white/20 cursor-pointer" style={{ background: value.c }} />
        <input type="color" value={value.c} onChange={(e) => onColor(e.target.value)} data-testid={`skin-color-${rkey}`}
          className="absolute inset-0 opacity-0 cursor-pointer" />
      </label>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-[10px] font-extrabold uppercase tracking-wide truncate">{label}</span>
          <span className="text-[9px] font-mono text-emerald ml-1">{Number(value.a).toFixed(2)}</span>
        </div>
        <input type="range" min={0} max={1} step={0.01} value={value.a} onChange={(e) => onAlpha(parseFloat(e.target.value))}
          data-testid={`skin-alpha-${rkey}`} className="w-full h-1 accent-emerald cursor-pointer" />
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="glass rounded-xl p-4">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-display font-extrabold mt-1">{value}</p>
    </div>
  );
}

// ============================================================================
// GLITCH LAB (2026-08-23 owner order): advanced custom glitch skin creator —
// raw engine numbers, era-family randomizer, exact save/apply/share. Access =
// website owners + Streamer role + Patreon Adult/Elder/Apex, decided by the SERVER on every
// call; this panel only renders the verdict it is given. A glitch skin is
// NEVER fake-rendered (fleet rule): the identity card shows name + colour
// proximity, the real look exists only in game.
// ============================================================================

const GLITCH_ACCENT = "#E14BEF";
const GLITCH_ACCENT2 = "#38C7F0";
const GLITCH_REASON_TEXT = {
  shape: "El diseño está incompleto.",
  pattern: "El patrón debe ser un número entero.",
  poison_pattern: "El patrón -8 está reservado por el motor — elige otro.",
  pattern_range: "El patrón debe estar entre -32 y 32.",
  variation: "La variación no es un número válido (máx ±1e12).",
};

function glitchReasonText(reason) {
  if (GLITCH_REASON_TEXT[reason]) return GLITCH_REASON_TEXT[reason];
  if (String(reason || "").startsWith("slot_")) {
    const k = String(reason).slice(5);
    return `Revisa los números de «${GLITCH_SLOT_LABELS[k] || k}» — deben ser números finitos (máx ±1e12).`;
  }
  return "El diseño glitch no es válido.";
}

function GlitchChannelInput({ value, onChange, testid }) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      data-testid={testid}
      spellCheck={false}
      inputMode="text"
      className="w-full min-w-0 bg-black/40 border border-white/10 rounded-md px-1.5 py-1.5 text-[11px] font-mono text-foreground outline-none transition-colors focus:border-[#E14BEF]/60"
      placeholder="0"
    />
  );
}

function GlitchLabPanel({ verdict, onVerdict, fields, setFields, name, setName, speciesList, selected, setSelected, cooldown, setCooldown, meState, setMeState, loadPresets, importCode, setImportCode, importFromCode, play }) {
  const [family, setFamily] = useState("mixto");
  const [applying, setApplying] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rechecking, setRechecking] = useState(false);
  const selKey = selected ? (selected.slug || selected.id || selected.name) : "";

  // ---- Live preview + colour selector plumbing -------------------------------
  // Glitch numbers are raw engine floats (can be huge/negative). For the 3D
  // specimen we clamp each channel into the display gamut so the design is
  // visible; the real in-game look still comes from the raw bytes on apply.
  const clampUnit = (v) => Math.max(0, Math.min(1, Number.isFinite(v) ? v : 0));
  const chanToHex = (v) => Math.round(clampUnit(v) * 255).toString(16).padStart(2, "0");
  const slotHex = (k) => {
    const [r, g, b] = fields.slots[k].map((s) => Number(String(s).trim()));
    return `#${chanToHex(r)}${chanToHex(g)}${chanToHex(b)}`;
  };
  // The colour picker writes sRGB 0-1 values into R/G/B (alpha untouched) so a
  // player can design visually and still fine-tune the raw numbers by hand.
  const setSlotColorFromHex = (k, hex) => {
    const n = parseInt(String(hex).slice(1), 16);
    const to01 = (v) => Math.round((v / 255) * 1000) / 1000;
    const r = to01((n >> 16) & 255), g = to01((n >> 8) & 255), b = to01(n & 255);
    setFields((p) => ({ ...p, slots: { ...p.slots, [k]: [String(r), String(g), String(b), p.slots[k][3]] } }));
    play("click");
  };
  const previewColors = useMemo(() => {
    const out = {};
    GLITCH_SLOTS.forEach((k) => {
      const [r, g, b, a] = fields.slots[k].map((s) => Number(String(s).trim()));
      // Only honour an explicit 0..1 alpha; glitch rails stay opaque so the
      // colour is actually visible in the preview.
      const aa = (Number.isFinite(a) && a >= 0 && a <= 1) ? a : 1;
      out[k] = { c: `#${chanToHex(r)}${chanToHex(g)}${chanToHex(b)}`, a: aa };
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields]);
  const previewPattern = clampPattern(parseInt(fields.pattern, 10) || 0, null, selKey);


  const recheck = async () => {
    setRechecking(true);
    try { const r = await api.glitchAccess(); onVerdict(r.data); if (r.data?.allowed) play("success"); }
    catch (e) { onVerdict(null); }
    finally { setRechecking(false); }
  };

  const setChan = (k, i, v) => setFields((p) => {
    const slots = { ...p.slots, [k]: p.slots[k].map((c, idx) => (idx === i ? v : c)) };
    return { ...p, slots };
  });

  const randomizeSlot = (k) => {
    setFields((p) => ({ ...p, slots: { ...p.slots, [k]: randomGlitchSlot(family).map((c) => String(c)) } }));
    play("click");
  };
  const randomizeAll = () => { setFields(randomGlitchFields(family)); play("success"); };
  const clearAll = () => { setFields(emptyGlitchFields()); play("click"); };

  const parsed = fieldsToRaw(fields);

  const applyGlitch = async () => {
    if (!parsed.ok) { play("error"); toast.error(glitchReasonText(parsed.reason)); return; }
    if (!meState?.in_game) {
      const fresh = await api.meState().then((r) => r.data).catch(() => null);
      if (fresh) setMeState(fresh);
      if (!fresh?.in_game) { toast.error("Despliega un dino primero — se aplica a tu Dino en Vivo."); play("error"); return; }
    }
    if (cooldown > 0) return;
    setApplying(true);
    try {
      await api.glitchApply(parsed.raw);
      setCooldown(APPLY_COOLDOWN);
      play("success");
      toast.success("¡Skin glitch aplicada a tu Dino en Vivo!", { description: "El aspecto real se ve dentro del juego." });
    } catch (e) {
      play("error");
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.code === "glitch_tier_insufficient") {
        if (detail.glitch) onVerdict(detail.glitch);
        toast.error(detail.message || "Tu rol o nivel no incluye el Glitch Lab.");
      } else {
        toast.error(typeof detail === "string" && detail.trim() ? detail : "Falló al aplicar la skin glitch.");
      }
    } finally { setApplying(false); }
  };

  const saveGlitch = async () => {
    if (!parsed.ok) { play("error"); toast.error(glitchReasonText(parsed.reason)); return; }
    if (!selKey) { play("error"); toast.error("Elige una especie — el preset y el código la incluyen."); return; }
    setSaving(true);
    try {
      // Display payload = the clamped approximation (what the designer/preset
      // list can show); the RAW sidecar carries the real bytes.
      const clamp01 = (v) => Math.max(0, Math.min(1, Number(v) || 0));
      const payload = { pattern: clampPattern(fields.pattern, null, selKey) };
      GLITCH_SLOTS.forEach((k) => {
        const [r, g, b, a] = parsed.raw[k];
        payload[k] = { r: clamp01(r), g: clamp01(g), b: clamp01(b), a: clamp01(a) };
      });
      const label = (name.trim() || "Glitch sin nombre").slice(0, 64);
      await api.presetsSave({ name: label, dino_class: selKey, payload, raw: parsed.raw });
      loadPresets();
      play("success");
      toast.success(`Glitch "${label}" guardado en tus presets`, { description: "Desde Presets se aplica byte a byte, y su código se comparte con Copiar código." });
    } catch (e) {
      play("error");
      const detail = e?.response?.data?.detail;
      toast.error(typeof detail === "string" && detail.trim() ? detail : "No se pudo guardar el glitch.");
    } finally { setSaving(false); }
  };

  const copyGlitchCode = async () => {
    if (!parsed.ok) { play("error"); toast.error(glitchReasonText(parsed.reason)); return; }
    const code = encodeGlitchCode(selKey || "", parsed.raw);
    if (!code) { play("error"); toast.error("El diseño no es válido para un código."); return; }
    const ok = await copyTextToClipboard(code);
    if (ok) { play("success"); toast.success("Código glitch copiado (LIN2)", { description: "Quien lo importe con acceso al Glitch Lab recibe la skin byte a byte." }); }
    else { play("error"); toast.error("No se pudo copiar al portapapeles. Inténtalo de nuevo."); }
  };

  if (verdict === undefined) {
    return <div className="py-20 text-center text-muted-foreground flex items-center justify-center gap-2" data-testid="glitch-loading"><Loader2 className="animate-spin" size={16} /> Comprobando tu acceso al Glitch Lab…</div>;
  }

  if (!verdict?.allowed) {
    return (
      <div className="max-w-xl mx-auto" data-testid="glitch-locked">
        <div className="glass rounded-2xl p-8 text-center relative overflow-hidden">
          <div aria-hidden className="absolute inset-x-0 top-0 h-1" style={{ background: `linear-gradient(90deg, ${GLITCH_ACCENT}, ${GLITCH_ACCENT2})` }} />
          <Lock size={30} className="mx-auto mb-3" style={{ color: GLITCH_ACCENT }} />
          <h3 className="font-display text-xl font-extrabold tracking-wide">GLITCH LAB</h3>
          <p className="text-sm text-muted-foreground mt-2">
            Crea skins glitch con números crudos del motor: valores imposibles para el editor normal,
            aleatorizador por familias probadas y códigos exactos para compartir.
          </p>
          <div className="flex items-center justify-center gap-2 mt-4 flex-wrap">
            {["Owner", "Streamer", "Adult", "Elder", "Apex"].map((t) => (
              <span key={t} className="text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded-full border" style={{ color: GLITCH_ACCENT2, borderColor: `${GLITCH_ACCENT2}55`, background: `${GLITCH_ACCENT2}11` }}>{t}</span>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-4">
            Incluido para cuentas Owner, el rol de Discord <span className="text-foreground font-semibold">Streamer</span> y los niveles de Patreon <span className="text-foreground font-semibold">Adult, Elder y Apex</span>.
            {verdict?.tier ? <> Tu nivel actual: <span className="text-foreground font-semibold">{verdict.tier}</span>.</> : null}
          </p>
          <button onClick={recheck} disabled={rechecking} data-testid="glitch-recheck"
            className="mt-5 inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-bold uppercase tracking-wide border border-white/15 hover:border-white/30 transition-colors">
            {rechecking ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Volver a comprobar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-[minmax(0,1fr)_400px] gap-5" data-testid="glitch-lab">
      {/* ------------------------------------------------ the numbers ------ */}
      <div className="glass rounded-2xl p-5 relative overflow-hidden">
        <div aria-hidden className="absolute inset-x-0 top-0 h-1" style={{ background: `linear-gradient(90deg, ${GLITCH_ACCENT}, ${GLITCH_ACCENT2})` }} />
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <p className="label-overline text-[10px]" style={{ color: GLITCH_ACCENT }}>Números del glitch</p>
            <p className="text-xs text-muted-foreground mt-0.5">Valores crudos del motor por zona (RGBA). Acepta notación científica: <span className="font-mono">-1e11</span>, <span className="font-mono">-999</span>, <span className="font-mono">0.5</span>…</p>
          </div>
          <span className="text-[10px] font-extrabold uppercase tracking-wider px-2 py-1 rounded border" style={{ color: GLITCH_ACCENT, borderColor: `${GLITCH_ACCENT}55`, background: `${GLITCH_ACCENT}11` }} data-testid="glitch-via">{verdict.via === "owner" ? "Acceso Owner" : `Acceso ${verdict.tier || "Patreon"}`}</span>
        </div>

        <div className="mt-4 space-y-1.5">
          <div className="grid grid-cols-[84px_28px_repeat(4,minmax(0,1fr))_30px] gap-1.5 px-0.5">
            <span />
            <span />
            {["R", "G", "B", "A"].map((h) => <span key={h} className="text-[10px] font-extrabold text-muted-foreground text-center uppercase">{h}</span>)}
            <span />
          </div>
          {GLITCH_SLOTS.map((k) => (
            <div key={k} className="grid grid-cols-[84px_28px_repeat(4,minmax(0,1fr))_30px] gap-1.5 items-center" data-testid={`glitch-row-${k}`}>
              <span className="text-[11px] font-semibold text-muted-foreground truncate">{GLITCH_SLOT_LABELS[k] || k}</span>
              <label className="relative block h-7 w-7 shrink-0" title="Elegir color">
                <span className="block h-full w-full rounded-md border border-white/20 cursor-pointer" style={{ background: slotHex(k) }} />
                <input type="color" value={slotHex(k)} onChange={(e) => setSlotColorFromHex(k, e.target.value)} data-testid={`glitch-colorpicker-${k}`}
                  className="absolute inset-0 opacity-0 cursor-pointer" />
              </label>
              {fields.slots[k].map((v, i) => (
                <GlitchChannelInput key={i} value={v} onChange={(nv) => setChan(k, i, nv)} testid={`glitch-slot-${k}-${i}`} />
              ))}
              <button onClick={() => randomizeSlot(k)} title="Aleatorio en esta zona" data-testid={`glitch-random-${k}`}
                className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-white/10 hover:border-[#E14BEF]/60 transition-colors">
                <Dices size={13} />
              </button>
            </div>
          ))}
        </div>

        <div className="mt-4 grid sm:grid-cols-2 gap-3">
          <div className="glass rounded-lg px-3 py-2.5">
            <p className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1.5">Patrón <span className="normal-case font-normal">(entero, -32 a 32 · -8 reservado)</span></p>
            <GlitchChannelInput value={fields.pattern} onChange={(v) => setFields((p) => ({ ...p, pattern: v }))} testid="glitch-pattern" />
          </div>
          <div className="glass rounded-lg px-3 py-2.5">
            <p className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1.5">Variación <span className="normal-case font-normal">(claves del motor: 2 · 8 · 16)</span></p>
            <div className="flex items-center gap-1.5">
              {GLITCH_VARIATION_KEYS.map((vk) => (
                <button key={vk} onClick={() => { setFields((p) => ({ ...p, variation: String(vk) })); play("click"); }} data-testid={`glitch-variation-${vk}`}
                  className={`px-2.5 py-1.5 rounded-md text-[11px] font-mono font-bold border transition-colors ${String(fields.variation) === String(vk) ? "border-[#38C7F0] text-[#38C7F0] bg-[#38C7F0]/10" : "border-white/10 text-muted-foreground hover:border-white/25"}`}>{vk}</button>
              ))}
              <GlitchChannelInput value={fields.variation} onChange={(v) => setFields((p) => ({ ...p, variation: v }))} testid="glitch-variation" />
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground">Familia:</span>
          {GLITCH_FAMILIES.map((f) => (
            <button key={f.id} onClick={() => { setFamily(f.id); play("click"); }} data-testid={`glitch-family-${f.id}`}
              className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide border transition-colors ${family === f.id ? "border-[#E14BEF] text-[#E14BEF] bg-[#E14BEF]/10" : "border-white/10 text-muted-foreground hover:border-white/25"}`}>
              {f.label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <button onClick={randomizeAll} data-testid="glitch-random-all"
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide border transition-colors"
              style={{ color: GLITCH_ACCENT, borderColor: `${GLITCH_ACCENT}66`, background: `${GLITCH_ACCENT}11` }}>
              <Sparkles size={13} /> Aleatorio total
            </button>
            <button onClick={clearAll} data-testid="glitch-clear"
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide border border-white/10 text-muted-foreground hover:border-white/25 transition-colors">
              <X size={13} /> Limpiar
            </button>
          </div>
        </div>
        {!parsed.ok && (
          <p className="mt-3 text-[11px] text-red-400" data-testid="glitch-invalid">{glitchReasonText(parsed.reason)}</p>
        )}
      </div>

      {/* --------------------------------------------- preview + identity + actions -- */}
      <div className="space-y-4">
        <div data-testid="glitch-preview-wrap">
          <SkinPreview3D species={selKey} colors={previewColors} pattern={previewPattern} height={340}
            testid="glitch-3d-viewer" emptyLabel="Elige una especie para previsualizar el glitch." />
          <p className="text-[10px] text-muted-foreground mt-1.5 px-0.5">
            Vista previa aproximada — los colores se recortan al rango visible. El aspecto exacto (raíles, campos profundos) solo se ve dentro del juego.
          </p>
        </div>
        <div className="glass rounded-2xl p-4">
          <p className="label-overline text-[10px] mb-2" style={{ color: GLITCH_ACCENT2 }}>Identidad</p>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder="Nombre del glitch…" data-testid="glitch-name" spellCheck={false}
            className="w-full bg-black/40 border border-white/10 rounded-md px-2.5 py-2 text-sm outline-none transition-colors focus:border-[#38C7F0]/60" />
          <div className="mt-3 rounded-xl p-4 relative overflow-hidden" style={{ background: "#050505", border: "1px solid rgba(255,255,255,0.08)" }} data-testid="glitch-card">
            <span className="absolute top-2 right-2 text-[8px] font-extrabold uppercase tracking-widest px-1.5 py-0.5 rounded border" style={{ color: GLITCH_ACCENT, borderColor: `${GLITCH_ACCENT}66` }}>Glitch</span>
            <p className="font-display text-lg font-extrabold tracking-wide truncate" style={{ backgroundImage: `linear-gradient(90deg, ${GLITCH_ACCENT}, ${GLITCH_ACCENT2})`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
              {name.trim() || "Glitch sin nombre"}
            </p>
          </div>
          <div className="mt-3">
            <p className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1">Especie (para el preset y el código)</p>
            <select value={selKey} onChange={(e) => { const sp = (speciesList || []).find((s) => (s.slug || s.id || s.name) === e.target.value); if (sp) setSelected(sp); play("click"); }} data-testid="glitch-species"
              className="w-full bg-black/40 border border-white/10 rounded-md px-2.5 py-2 text-sm outline-none transition-colors focus:border-white/25">
              {(speciesList || []).map((s) => { const k = s.slug || s.id || s.name; return <option key={k} value={k}>{s.name || k}</option>; })}
            </select>
          </div>
        </div>

        <div className="glass rounded-2xl p-4 space-y-2.5">
          <button onClick={applyGlitch} disabled={applying || cooldown > 0 || !parsed.ok} data-testid="glitch-apply"
            className="w-full inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-xs font-extrabold uppercase tracking-wide transition-all disabled:opacity-50"
            style={{ background: `linear-gradient(90deg, ${GLITCH_ACCENT}cc, ${GLITCH_ACCENT2}cc)`, color: "#0a0a0a" }}>
            {applying ? <Loader2 size={14} className="animate-spin" /> : cooldown > 0 ? <Timer size={14} /> : <Zap size={14} />}
            {cooldown > 0 ? `Espera ${cooldown}s` : "Aplicar al Dino en Vivo"}
          </button>
          <div className="grid grid-cols-2 gap-2.5">
            <button onClick={saveGlitch} disabled={saving || !parsed.ok} data-testid="glitch-save"
              className="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[11px] font-bold uppercase tracking-wide border border-white/15 hover:border-white/30 transition-colors disabled:opacity-50">
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Guardar preset
            </button>
            <button onClick={copyGlitchCode} disabled={!parsed.ok} data-testid="glitch-code-copy"
              className="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[11px] font-bold uppercase tracking-wide border border-white/15 hover:border-white/30 transition-colors disabled:opacity-50">
              <Copy size={13} /> Copiar código
            </button>
          </div>
          <div className="pt-1">
            <p className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1.5">Importar código (LIN1 o LIN2)</p>
            <div className="flex items-center gap-2">
              <input value={importCode} onChange={(e) => setImportCode(e.target.value)} placeholder="Pega un código LIN2-…" data-testid="glitch-import-input" spellCheck={false}
                onKeyDown={(e) => { if (e.key === "Enter" && importCode.trim()) importFromCode(); }}
                className="flex-1 min-w-0 bg-black/40 border border-white/10 rounded-md px-2.5 py-2 text-xs font-mono outline-none transition-colors focus:border-white/25" />
              <button onClick={importFromCode} disabled={!importCode.trim()} data-testid="glitch-import-btn" title="Importar"
                className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-white/15 hover:border-white/30 transition-colors disabled:opacity-40">
                <ClipboardPaste size={14} />
              </button>
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground pt-1">
            Los presets glitch aparecen en Skin Designer → Presets con la insignia <span className="text-emerald font-semibold">Exacta</span>: se aplican byte a byte y sobreviven al relog.
          </p>
        </div>
      </div>
    </div>
  );
}
