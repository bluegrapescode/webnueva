import React, { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { useTexture } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { Egg } from "lucide-react";
import * as SkeletonUtils from "three/examples/jsm/utils/SkeletonUtils.js";
import { dinoAssetUrl } from "@/lib/api";
import { loadSpeciesGlb, pickIdleClip } from "@/components/skin3d/SpeciesViewer3D";
import { FLEET_SLOTS, DEFAULT_FLEET_COLORS, linearToHex, getSpeciesDefaultColors, makeTintedMaterial, updateAdvancedTint } from "@/components/skin3d/tintMaterial";
import { clampPattern, patternFile, mappingKey, UTILITY_MASK_FILE } from "@/lib/skinPatternCatalog";

// FLEET_SLOTS/DEFAULT_FLEET_COLORS/linearToHex/getSpeciesDefaultColors/makeTintedMaterial
// now live in tintMaterial.js (SpeciesViewer3D.jsx's live MyDino viewer reuses the exact
// same tint-mask material there too — see BUILD-PACKET item F). Re-exported here
// unchanged so every existing import site (SkinEditor.jsx) keeps working as before.
export { FLEET_SLOTS, DEFAULT_FLEET_COLORS, linearToHex, getSpeciesDefaultColors };

const colorOf = (colors, key, fallback) => new THREE.Color(colors?.[key]?.c || fallback);
const alphaOf = (colors, key) => (typeof colors?.[key]?.a === "number" ? colors[key].a : 1);

function makeEyeMaterial(colors) {
  const c = colorOf(colors, "eyes", "#e2c53a");
  const a = alphaOf(colors, "eyes");
  return new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 0.35 * a, roughness: 0.16, metalness: 0.3 });
}

const isEyeMesh = (name) => /eye|iris|cornea/i.test(name || "");

// ── Model + idle-clip loading ───────────────────────────────────────────────
// On prod, animation clips do NOT always live inside showcase.glb — they can live in a
// sibling anims.glb, or (for mesh.glb-only species) a separate idle.glb whose clips must
// be retargeted onto the mesh. SpeciesViewer3D.jsx already ships this proven fallback
// chain (showcase.glb -> anims.glb -> mesh.glb, +idle.glb clips) for the MyDino viewer;
// reused verbatim here instead of the old single-file useGLTF(showcase.glb) call, which
// silently produced a static model whenever a species kept its clips outside showcase.glb.
const _glbLoader = new GLTFLoader();
const _glbCache = new Map(); // species -> { status: pending|success|error, promise, result, error }

function useSpeciesGlb(species) {
  let entry = _glbCache.get(species);
  if (!entry) {
    entry = { status: "pending" };
    entry.promise = loadSpeciesGlb(_glbLoader, species)
      .then((g) => { entry.status = "success"; entry.result = g || { scene: new THREE.Group(), animations: [] }; })
      .catch((e) => { entry.status = "error"; entry.error = e; });
    _glbCache.set(species, entry);
  }
  if (entry.status === "pending") throw entry.promise; // Suspense boundary catches this (Skin3DBoundary handles hard failures)
  if (entry.status === "error") throw entry.error;
  return entry.result;
}

// ── Optional, NEVER-THROWING texture loads ──────────────────────────────────
// `useTexture` suspends and then THROWS on a 404, which the Skin3DBoundary turns
// into "Vista 3D no disponible" — the whole viewer replaced by a placeholder. That
// was survivable while every URL this file built was one of three files that have
// always existed. It is not survivable now:
//   • the pattern index is no longer clamped to 0..2, so it names files that
//     arrived in the 2026-08-25 asset wave;
//   • `tmc_mask.webp` is genuinely absent on any owner that has not taken that
//     wave, and MUST read as "this species has no advanced regions", not as a
//     broken viewer.
// So both go through this loader: it suspends exactly like useTexture on the
// happy path, and resolves to `null` instead of throwing on a failure. A missing
// pattern falls back to `pattern_0.webp` (the species' base sheet, which has
// existed since the site launched) and only then to null — an untinted specimen
// is a far better answer than no specimen.
const _texCache = new Map(); // url -> { status, promise, result }

function loadTextureOrNull(url) {
  let entry = _texCache.get(url);
  if (!entry) {
    entry = { status: "pending" };
    entry.promise = new Promise((resolve) => {
      new THREE.TextureLoader().load(url,
        (t) => { entry.status = "done"; entry.result = t; resolve(t); },
        undefined,
        () => { entry.status = "done"; entry.result = null; resolve(null); });
    });
    _texCache.set(url, entry);
  }
  return entry;
}

/** Suspense-friendly. Returns the texture, or null when the file is not there. */
function useOptionalTexture(url) {
  if (!url) return null;
  const entry = loadTextureOrNull(url);
  if (entry.status === "pending") throw entry.promise;
  return entry.result;
}

export function FleetDinoModel({ species, colors, pattern = 0, manifest = null, advancedColors = null, advancedMapping = null }) {
  const { scene, animations } = useSpeciesGlb(species);
  const diffuseTex = useTexture(dinoAssetUrl(species, "diffuse.webp"));
  // The index is resolved against the ART this site ships for THIS species, so a
  // wide species (Omniraptor 0..5) wears its real sheet instead of collapsing
  // onto pattern 2, and a species with only three keeps exactly what it had.
  const patternIdx = clampPattern(pattern, manifest, species);
  const patternUrl = dinoAssetUrl(species, patternFile(patternIdx));
  const patternTex = useOptionalTexture(patternUrl);
  const fallbackTex = useOptionalTexture(patternTex ? "" : dinoAssetUrl(species, patternFile(0)));
  const maskTex = patternTex || fallbackTex;
  // Absent on a species with no advanced regions, and absent on any box that has
  // not taken the mask wave. Both are the same silent "no advanced lane".
  const utilTex = useOptionalTexture(advancedMapping ? dinoAssetUrl(species, UTILITY_MASK_FILE) : "");

  useEffect(() => { if (diffuseTex) { diffuseTex.colorSpace = THREE.SRGBColorSpace; diffuseTex.flipY = false; diffuseTex.needsUpdate = true; } }, [diffuseTex]);
  useEffect(() => { if (maskTex) { maskTex.colorSpace = THREE.NoColorSpace; maskTex.flipY = false; maskTex.needsUpdate = true; } }, [maskTex]);
  useEffect(() => { if (utilTex) { utilTex.colorSpace = THREE.NoColorSpace; utilTex.flipY = false; utilTex.needsUpdate = true; } }, [utilTex]);

  const tintMatsRef = useRef([]);
  const eyeMatsRef = useRef([]);
  const mixerRef = useRef(null);
  const colorsRef = useRef(colors);
  colorsRef.current = colors;
  const advancedRef = useRef(advancedColors);
  advancedRef.current = advancedColors;

  // ★ KEYED ON THE MAPPING'S CONTENT, NOT ITS IDENTITY. The panel rebuilds its
  // {teeth:'r',…} object on every colour drag, and `advanced` feeds `group`'s
  // memo — so keying on the object would clone the whole scene and recompile a
  // shader per mesh on every tick of a colour picker. That is exactly the GL
  // program leak the disposal comment below was written for.
  const mapKey = mappingKey(advancedMapping);
  const mappingRef = useRef(advancedMapping);
  mappingRef.current = advancedMapping;

  // Only build the advanced lane when there is BOTH a mask on the box AND a
  // measured channel map for this species. Either one missing renders exactly
  // the shader that shipped — no teeth/mouth/claws region is invented.
  const advanced = useMemo(
    () => (utilTex && mapKey
      ? { texture: utilTex, mapping: mappingRef.current, colors: advancedRef.current }
      : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [utilTex, mapKey]);

  const group = useMemo(() => {
    // SkeletonUtils.clone, NOT scene.clone(true): a plain Object3D clone keeps the
    // SOURCE scene's skeleton bound to the skinned meshes, so the mixer below would
    // animate the clone's (unbound) bones and the mesh would hold bind pose forever.
    const root = SkeletonUtils.clone(scene);
    tintMatsRef.current = [];
    eyeMatsRef.current = [];
    root.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true;
      o.receiveShadow = true;
      const src = o.material;
      if (isEyeMesh(src?.name) || isEyeMesh(o.name)) {
        const mat = makeEyeMaterial(colorsRef.current);
        o.material = mat;
        eyeMatsRef.current.push(mat);
        return;
      }
      const mat = makeTintedMaterial(diffuseTex, maskTex, colorsRef.current, advanced);
      o.material = mat;
      tintMatsRef.current.push(mat);
    });
    return root;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene, diffuseTex, maskTex, advanced]);

  // Every recompute of `group` above clones the whole scene and compiles a brand-new
  // MeshStandardMaterial (+ onBeforeCompile shader) per mesh, without ever disposing the
  // PREVIOUS batch — that leaked GL programs/materials on every species or color-pattern
  // change and is what produced the visual glitching. `scene` (the GLTF source) and
  // `diffuseTex`/`maskTex` (from useTexture's cache) are shared across every viewer
  // instance and must NOT be disposed here; only the materials created above (and the
  // detached scene clone itself) are owned exclusively by this instance/render.
  useEffect(() => {
    const staleGroup = group;
    const staleTintMats = tintMatsRef.current;
    const staleEyeMats = eyeMatsRef.current;
    return () => {
      staleTintMats.forEach((m) => m?.dispose?.());
      staleEyeMats.forEach((m) => m?.dispose?.());
      staleGroup.traverse((o) => { if (o.isMesh) o.material = null; });
    };
  }, [group]);

  // Autoplay the idle clip — same pickIdleClip heuristic as the MyDino (SpeciesViewer3D) viewer,
  // now fed by whichever file in the showcase/anims/mesh+idle chain actually carried the clip.
  useEffect(() => {
    if (!animations?.length) { mixerRef.current = null; return undefined; }
    const mixer = new THREE.AnimationMixer(group);
    const clip = pickIdleClip(animations);
    if (clip) mixer.clipAction(clip).play();
    mixerRef.current = mixer;
    return () => { mixer.stopAllAction(); mixerRef.current = null; };
  }, [group, animations]);

  useFrame((_, delta) => { mixerRef.current?.update(delta); });

  // Reactive colour updates (no reload needed on every picker tweak).
  useEffect(() => {
    tintMatsRef.current.forEach((m) => {
      const u = m.userData.tintUniforms;
      if (!u) return;
      u.cBody.value.set(colorOf(colors, "body", "#8a6b45"));
      u.cMarkings.value.set(colorOf(colors, "markings", "#2a2118"));
      u.cFlank.value.set(colorOf(colors, "flank", "#a67c4e"));
      u.cUnderbelly.value.set(colorOf(colors, "underbelly", "#d9c9a8"));
      u.cDetail1.value.set(colorOf(colors, "detail1", "#5c3f26"));
      u.cMaleDisplay.value.set(colorOf(colors, "male_display", "#c9c9c9"));
      u.aBody.value = alphaOf(colors, "body");
      u.aMarkings.value = alphaOf(colors, "markings");
      u.aFlank.value = alphaOf(colors, "flank");
      u.aUnderbelly.value = alphaOf(colors, "underbelly");
      u.aDetail1.value = alphaOf(colors, "detail1");
      u.aMaleDisplay.value = alphaOf(colors, "male_display");
    });
    eyeMatsRef.current.forEach((m) => {
      const c = colorOf(colors, "eyes", "#e2c53a");
      m.color.set(c);
      m.emissive.set(c);
      m.emissiveIntensity = 0.35 * alphaOf(colors, "eyes");
    });
  }, [colors]);

  // Same lane for teeth/mouth/claws: a uniform write, no clone and no recompile,
  // so dragging one of the three pickers costs exactly what dragging any of the
  // seven already costs. A material with no advanced lane is a no-op.
  useEffect(() => {
    tintMatsRef.current.forEach((m) => updateAdvancedTint(m, advancedColors));
  }, [advancedColors]);

  return <primitive object={group} />;
}

// Small panel-scoped error boundary — a broken/missing species asset should never take
// down the whole Skin Designer tab, only show a graceful placeholder in its place.
export class Skin3DBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, resetKey: props.resetKey }; }
  static getDerivedStateFromError() { return { hasError: true }; }
  static getDerivedStateFromProps(props, state) {
    if (props.resetKey !== state.resetKey) return { hasError: false, resetKey: props.resetKey };
    return null;
  }
  componentDidCatch(error) { console.warn("[skin-designer] vista 3D no disponible:", error?.message || error); }
  render() {
    if (this.state.hasError) {
      return (
        <div className="w-full h-full flex flex-col items-center justify-center gap-2.5 text-center px-6">
          <Egg size={28} className="text-muted-foreground/50" />
          <p className="text-xs text-muted-foreground max-w-[220px] leading-relaxed">Vista 3D no disponible para esta especie todavía.</p>
        </div>
      );
    }
    return this.props.children;
  }
}

export default FleetDinoModel;
