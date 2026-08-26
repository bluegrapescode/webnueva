import React from "react";
import { Loader2, PaintBucket, Lock, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import {
  V2_SLOTS, V1_SLOTS, V2_NEW_SLOTS, V2_SLOT_LABELS, V2_VARIATIONS, themeLabel,
  readContractState, listPatterns, listThemes, listSupportedSlots, listSwatches,
  buildApplyV2Body, pickVariation, serverRefusalMessage,
} from "@/lib/skinContractV2";
import { previewChannelMappingFor, paintableAdvancedSlots } from "@/lib/skinPatternCatalog";

// Skin contract v2 surface. It is ADDITIVE: nothing here renders unless the game
// side has published the contract, and the probe below answers "off" for every
// failure mode there is (route not mounted, network dead, junk body, enabled:false),
// so the v1 seven-slot editor above stays exactly what the live site shows today.

// ===== probe =====

// Never rejects. The caller stores whatever this returns; only { enabled: true }
// renders the v2 panel, so a thrown/refused/absent probe IS the v1 fallback.
export async function probeSkinContractV2() {
  try {
    const r = await api.skinContractState();
    if (r?.status !== 200) return null;
    const verdict = readContractState(r?.data);
    return verdict.enabled ? verdict : null;
  } catch (e) {
    // 404 (route not mounted — today's live state), 5xx, timeout, offline: all v1.
    return null;
  }
}

// ===== manifest (761 KB, immutable, once per session) =====

let manifestCache = null;   // resolved table, kept for the whole session
let manifestInFlight = null; // de-dupes concurrent mounts

async function loadManifest() {
  if (manifestCache) return manifestCache;
  if (!manifestInFlight) {
    manifestInFlight = api.skinContract()
      .then((r) => {
        const d = r?.data;
        // A table with no species map is as useless as a failed fetch — treat it as one.
        manifestCache = d && typeof d === "object" && d.species && typeof d.species === "object" ? d : null;
        return manifestCache;
      })
      .catch(() => null)
      .finally(() => { manifestInFlight = null; });
  }
  return manifestInFlight;
}

// ===== local boundary =====

// The studio must survive this panel throwing. The page-level ErrorBoundary would
// replace the WHOLE studio with an error card; this one drops just the v2 block.
class V2Boundary extends React.Component {
  constructor(props) { super(props); this.state = { dead: false }; }
  static getDerivedStateFromError() { return { dead: true }; }
  componentDidCatch(error) {
    console.warn("[skin-v2] panel no disponible:", error?.message || error);
    // The panel's own effect cleanup does not run on a throw, so the 3D preview
    // would keep painting teeth/mouth/claws with no controls left to change them.
    try { this.props.onDead?.(null); } catch (e) { /* never throw from a boundary */ }
  }
  render() { return this.state.dead ? null : this.props.children; }
}

// ===== pieces =====

function V2ColorRow({ slot, hex, swatches, onColor }) {
  return (
    <div className="glass rounded-lg px-2.5 py-2 flex items-center gap-2.5" data-testid={`skin-v2-region-${slot}`}>
      <label className="relative shrink-0">
        <span className="block w-8 h-8 rounded border border-white/20 cursor-pointer" style={{ background: hex }} />
        <input type="color" value={hex} onChange={(e) => onColor(e.target.value)} data-testid={`skin-v2-color-${slot}`}
          className="absolute inset-0 opacity-0 cursor-pointer" />
      </label>
      <div className="flex-1 min-w-0">
        <span className="block text-[10px] font-extrabold uppercase tracking-wide truncate">{V2_SLOT_LABELS[slot] || slot}</span>
        {swatches.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1" data-testid={`skin-v2-swatches-${slot}`}>
            {swatches.map((c) => (
              <button key={c} onClick={() => onColor(c)} title={c} style={{ background: c }}
                className="w-3.5 h-3.5 rounded-sm border border-white/20 hover:border-white/60 transition-colors" />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Chip({ active, onClick, children, testid }) {
  return (
    <button onClick={onClick} data-testid={testid}
      className={`px-2.5 py-1.5 rounded-md text-[11px] font-mono font-bold border transition-colors ${active
        ? "border-emerald text-emerald bg-emerald/10"
        : "border-white/10 text-muted-foreground hover:border-white/25"}`}>{children}</button>
  );
}

// ===== panel =====

function SkinContractV2PanelInner({ contract, speciesKey, colors, pattern, allowed, play, onAdvancedPreview }) {
  const [manifest, setManifest] = React.useState(undefined); // undefined=cargando, null=no disponible
  const [theme, setTheme] = React.useState(null);
  const [variation, setVariation] = React.useState(V2_VARIATIONS[0]);
  const [extra, setExtra] = React.useState({ teeth: "#ffffff", mouth: "#ffffff", claws: "#ffffff" });
  const [applying, setApplying] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    loadManifest().then((m) => { if (alive) setManifest(m || null); }).catch(() => { if (alive) setManifest(null); });
    return () => { alive = false; };
  }, []);

  const capSlots = contract?.slots || [];
  const capThemes = contract?.themes || [];

  const patterns = React.useMemo(
    () => (manifest ? listPatterns(manifest, speciesKey) : []),
    [manifest, speciesKey]);
  // The v1 pattern picker stays the single source of truth so the 3D preview keeps
  // matching; when the table doesn't publish that index we fall back and say so.
  const pat = patterns.includes(pattern) ? pattern : (patterns.length ? patterns[0] : null);
  const themes = React.useMemo(
    () => (manifest && pat != null ? listThemes(manifest, speciesKey, pat, capThemes) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [manifest, speciesKey, pat, contract]);

  React.useEffect(() => {
    setTheme((t) => (themes.includes(t) ? t : (themes.length ? themes[0] : null)));
  }, [themes]);

  const supported = React.useMemo(
    () => (manifest && pat != null && theme != null ? listSupportedSlots(manifest, speciesKey, pat, theme, capSlots) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [manifest, speciesKey, pat, theme, contract]);

  const setExtraColor = (slot, c) => setExtra((p) => ({ ...p, [slot]: c }));

  const applyV2 = async () => {
    if (applying || pat == null || theme == null) return;
    setApplying(true);
    try {
      // Every one of the ten slots ships: the seven the v1 editor holds (verbatim,
      // same 0-1 sRGB numbers /api/apply gets) plus the three v2 adds. A slot this
      // theme does not support is not editable here and rides at its v1 value.
      const hexColors = {};
      V1_SLOTS.forEach((s) => { hexColors[s] = colors?.[s]?.c || "#ffffff"; });
      V2_NEW_SLOTS.forEach((s) => { hexColors[s] = extra[s] || "#ffffff"; });
      const r = await api.applySkinV2(buildApplyV2Body({ pattern: pat, variation, theme, hexColors }));
      play?.("success");
      toast.success("Skin v2 enviada a tu Dino en Vivo.", {
        description: r?.data?.cmd_id ? `Orden ${r.data.cmd_id}` : undefined,
      });
    } catch (e) {
      play?.("error");
      if (e?.response?.status === 429) {
        toast.error("Espera un momento — demasiadas aplicaciones seguidas.");
      } else {
        toast.error(serverRefusalMessage(e?.response?.data) || "No se pudo aplicar la skin v2.");
      }
    } finally {
      setApplying(false);
    }
  };

  const editable = V2_SLOTS.filter((s) => supported.includes(s));
  const editableNew = V2_NEW_SLOTS.filter((s) => supported.includes(s));

  // ── The 3D preview lane for teeth / mouth / claws ──────────────────────────
  // The seven base slots repaint the specimen as you turn the dial; these three
  // never did on any owner, and every advanced row printed "In-game preview
  // unavailable" instead. They are carried by a SECOND mask sampler
  // (<Species>/tmc_mask.webp) with three independent one-hot channels, so they
  // do not compete with the seven for the RGB cube's eight corners.
  //
  // ★ A slot is painted only when it clears BOTH gates: this exact
  // species/pattern/theme row supports it, AND the species' mask has a MEASURED
  // channel for it. Of 858 slot instances the whole game declares claws 18,
  // mouth 13 and teeth 1 — so on almost every row this resolves to nothing at
  // all, and nothing is exactly what must be drawn. An invented control here
  // would be the standing lie the fleet already paid for once.
  const advancedMapping = React.useMemo(
    () => (manifest ? previewChannelMappingFor(manifest, speciesKey) : null),
    [manifest, speciesKey]);
  const paintable = React.useMemo(
    () => paintableAdvancedSlots(advancedMapping, editableNew),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [advancedMapping, editableNew.join(",")]);

  // Hand up only the slots that passed both gates; a mapping trimmed to those is
  // what keeps an unsupported region inert in the shader too.
  React.useEffect(() => {
    if (typeof onAdvancedPreview !== "function") return;
    if (!paintable.length) { onAdvancedPreview(null); return; }
    const mapping = {};
    const painted = {};
    paintable.forEach((s) => { mapping[s] = advancedMapping[s]; painted[s] = { c: extra[s] || "#ffffff", a: 1 }; });
    // ★ THE SPECIES RIDES WITH THE MAP. A channel map is a fact about ONE animal's
    // mask, and the viewer remounts on a species change one commit BEFORE this
    // effect can clear it — so for that window the new species was handed the old
    // species' map and painted its own mask with it. Measured: switching from a
    // magenta-clawed Omniraptor to Allosaurus (which has no measured channel at
    // all, and whose panel correctly showed no claws row) left 1,130 magenta
    // pixels on the Allosaurus. Naming the species makes the mismatch
    // unrepresentable instead of racing the scheduler.
    onAdvancedPreview({ species: speciesKey, mapping, colors: painted });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onAdvancedPreview, speciesKey, paintable.join(","), advancedMapping, extra]);

  // ★ CLEARING BELONGS TO UNMOUNT ALONE. Putting it in the effect above would
  // make every colour drag report null-then-value, and the null is what tells
  // the viewer "no advanced lane" — one frame of it re-clones the whole scene.
  // The contract flipping off, or the studio leaving, unmounts this panel, and
  // a stale advanced lane must not keep painting a region nobody can edit.
  React.useEffect(() => () => {
    if (typeof onAdvancedPreview === "function") onAdvancedPreview(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="mt-6 glass rounded-2xl border border-emerald/20 p-4" data-testid="skin-v2-panel">
      <div className="flex items-center justify-between gap-3 mb-3">
        <p className="label-overline text-[10px] text-emerald inline-flex items-center gap-1.5">
          <Sparkles size={12} /> Skins v2
        </p>
        {contract?.build && <span className="text-[9px] font-mono text-muted-foreground">build {contract.build}</span>}
      </div>

      {manifest === undefined && (
        <p className="text-xs text-muted-foreground inline-flex items-center gap-2" data-testid="skin-v2-loading">
          <Loader2 size={13} className="animate-spin" /> Cargando temas…
        </p>
      )}

      {manifest === null && (
        <p className="text-xs text-muted-foreground" data-testid="skin-v2-manifest-error">
          La tabla de temas no está disponible. Sigue usando el editor de arriba.
        </p>
      )}

      {manifest && pat == null && (
        <p className="text-xs text-muted-foreground" data-testid="skin-v2-no-patterns">
          Esta especie aún no tiene patrones v2.
        </p>
      )}

      {manifest && pat != null && (
        <div className="space-y-3">
          {pat !== pattern && (
            <p className="text-[11px] text-amber-400/80" data-testid="skin-v2-pattern-fallback">
              El patrón {pattern} no está en la tabla — usando el {pat}.
            </p>
          )}

          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1.5">Tema</p>
            {themes.length === 0 ? (
              <p className="text-xs text-muted-foreground" data-testid="skin-v2-no-themes">
                Este patrón no tiene temas disponibles.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5" data-testid="skin-v2-themes">
                {themes.map((t) => (
                  <Chip key={t} active={t === theme} onClick={() => { setTheme(t); play?.("click"); }} testid={`skin-v2-theme-${t}`}>
                    {themeLabel(t)}
                  </Chip>
                ))}
              </div>
            )}
          </div>

          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1.5">
              Variación <span className="normal-case font-normal">(claves del motor: 2 · 8 · 16)</span>
            </p>
            <div className="flex flex-wrap gap-1.5" data-testid="skin-v2-variations">
              {V2_VARIATIONS.map((v) => (
                <Chip key={v} active={v === pickVariation(variation)} onClick={() => { setVariation(v); play?.("click"); }} testid={`skin-v2-variation-${v}`}>
                  {v}
                </Chip>
              ))}
            </div>
          </div>

          {theme != null && (
            <div>
              <p className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1.5">
                Colores nuevos
              </p>
              {editableNew.length === 0 ? (
                <p className="text-xs text-muted-foreground" data-testid="skin-v2-no-new-slots">
                  Este tema no añade colores nuevos.
                </p>
              ) : (
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-1.5" data-testid="skin-v2-new-slots">
                  {editableNew.map((s) => (
                    <V2ColorRow key={s} slot={s} hex={extra[s]} onColor={(c) => setExtraColor(s, c)}
                      swatches={listSwatches(manifest, speciesKey, pat, theme, s)} />
                  ))}
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-1.5" data-testid="skin-v2-slot-count">
                {editable.length} de {V2_SLOTS.length} colores en este tema. El resto va con el valor del editor.
              </p>
              {editableNew.length > 0 && (
                <p className="text-[11px] text-muted-foreground mt-1" data-testid="skin-v2-preview-note">
                  {paintable.length > 0
                    ? `Se ven en el modelo 3D: ${paintable.map((s) => V2_SLOT_LABELS[s] || s).join(" · ")}.`
                    : "Estos colores se aplican en el juego, pero esta especie aún no tiene mapa de vista previa — el modelo 3D no los pinta."}
                </p>
              )}
            </div>
          )}

          <button onClick={applyV2} disabled={applying || !allowed || theme == null || !speciesKey} data-testid="skin-v2-apply"
            className={`w-full inline-flex items-center justify-center gap-2 font-extrabold uppercase tracking-wide text-sm py-3 rounded-lg transition-all disabled:opacity-50 ${allowed
              ? "bg-[#e8722a] text-white hover:brightness-110 shadow-lg shadow-[#e8722a]/20"
              : "bg-white/5 text-muted-foreground border border-gold/30"}`}>
            {applying ? <Loader2 size={15} className="animate-spin" /> : allowed ? <PaintBucket size={15} /> : <Lock size={15} />}
            {applying ? "Aplicando…" : allowed ? "Aplicar skin v2" : "Aplicar requiere Patreon"}
          </button>
        </div>
      )}
    </div>
  );
}

export function SkinContractV2Panel(props) {
  // The boundary drops the panel on a throw — and the 3D preview must go with
  // it, or the specimen keeps wearing an advanced tint whose controls are gone.
  return (
    <V2Boundary onDead={props.onAdvancedPreview}>
      <SkinContractV2PanelInner {...props} />
    </V2Boundary>
  );
}

export default SkinContractV2Panel;
