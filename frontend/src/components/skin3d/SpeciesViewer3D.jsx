import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import * as SkeletonUtils from "three/examples/jsm/utils/SkeletonUtils.js";
import { Loader2, Egg, Move3d } from "lucide-react";
import { api, dinoAssetUrl } from "@/lib/api";
import { linearToHex, getSpeciesDefaultColors, makeTintedMaterial } from "@/components/skin3d/tintMaterial";
import { clampPattern, patternFile } from "@/lib/skinPatternCatalog";

// The 7 tint-mask colour channels, in RGBA-array form (dino.skin.colors / GET
// /api/snapshot's flat shape) -- same set FleetDinoModel's FLEET_SLOTS + "eyes" cover.
const SKIN_COLOR_KEYS = ["body", "markings", "flank", "underbelly", "detail1", "male_display", "eyes"];

// Sentinel family captured when a skin snapshot is taken between a server
// restart and the player's re-apply (colors -999999 / pattern -8). Color-only
// rule: a slot with ANY component at or below this is garbage, never a colour.
// Negative patterns alone are legitimate (glitch skins) and are NOT rejected.
const SKIN_POISON_THRESHOLD = -900000;

function loadTexture(url) {
  return new Promise((resolve, reject) => { new THREE.TextureLoader().load(url, resolve, undefined, reject); });
}

// Raw RGBA-array colours (linear, straight off the wire) -> the {c:"#hex",a} shape
// makeTintedMaterial expects, layered over the species' own default palette so any
// slot the source doesn't carry still has a sane colour instead of pure black.
function colorsFromRawSkin(species, raw) {
  if (!raw) return null;
  const out = { ...getSpeciesDefaultColors(species) };
  let any = false;
  SKIN_COLOR_KEYS.forEach((k) => {
    const arr = raw[k];
    if (!Array.isArray(arr)) return;
    if (arr.some((c) => Number(c) <= SKIN_POISON_THRESHOLD)) return; // poisoned sentinel slot
    out[k] = linearToHex(arr);
    any = true;
  });
  return any ? out : null;
}

// fallback chain per BUILD-PACKET item F: dino.skin -> GET /api/snapshot -> the
// species default palette JSON (same source SkinEditor.jsx uses via
// getSpeciesDefaultColors) -> caller falls back to the raw flat material entirely
// when even the mask texture itself can't be loaded (see the caller's try/catch).
// allowSnapshot=false is the STORED-skin mode (vault cards/preview): the live
// /api/snapshot is a different dino's current skin and must never bleed in --
// a parked dino without a stored skin renders the species default palette.
async function resolveLiveSkin(species, dinoSkin, allowSnapshot = true) {
  const fromMeState = colorsFromRawSkin(species, dinoSkin?.colors);
  if (fromMeState) return { colors: fromMeState, pattern: dinoSkin?.pattern };
  if (allowSnapshot) {
    try {
      const r = await api.skinSnapshot();
      const snap = r?.data?.active ? r.data.skin : null;
      const fromSnapshot = colorsFromRawSkin(species, snap);
      if (fromSnapshot) return { colors: fromSnapshot, pattern: snap?.pattern };
    } catch (e) { /* GET /api/snapshot unavailable — fall through to the default palette */ }
  }
  return { colors: getSpeciesDefaultColors(species), pattern: 0 };
}

// Pick the idle clip to autoplay: among clips named/containing "idle" the SHORTEST
// name wins — that is always the plain base idle ("Idle"/"IdleStill"), never a
// situational variant like "Crouch_Idle" or "KnockdownB_Idle" (anims.glb ships all
// of those and Array.find would return whichever sorts first). Falls back to the
// first clip in the file (still better than a static pose).
// Exported so FleetDinoModel (Skin Designer viewer) can reuse the exact same heuristic.
export function pickIdleClip(clips) {
  if (!clips || !clips.length) return null;
  const matches = clips.filter((c) => /idle/i.test(c.name || ""));
  if (matches.length) {
    return matches.reduce((a, b) => (((a.name || "").length <= (b.name || "").length) ? a : b));
  }
  return clips[0];
}

// Preferred-clip variant: among clips whose name contains `prefer` (e.g.
// "walk" -> WalkF / WalkF_Lean_N / Injured_Body_WalkF), the SHORTEST name wins
// — that is always the plain base gait, not an injured/lean variant.
// Otherwise the idle heuristic applies.
function pickPreferredClip(clips, prefer) {
  if (!clips || !clips.length) return null;
  if (prefer) {
    const re = new RegExp(prefer, "i");
    const matches = clips.filter((c) => re.test(c.name || ""));
    if (matches.length) {
      return matches.reduce((a, b) => (((a.name || "").length <= (b.name || "").length) ? a : b));
    }
  }
  return pickIdleClip(clips);
}

function loadGlb(loader, url) {
  return new Promise((resolve, reject) => loader.load(url, resolve, undefined, reject));
}

// Fallback chain: mesh_idle.glb -> showcase.glb -> anims.glb -> mesh.glb (+idle.glb for
// the animation if the mesh file itself ships without one). mesh_idle.glb goes FIRST:
// it is the slim (~1-5 MB) export whose only clip is the true base idle, while every
// species' showcase.glb carries a single ACTION clip (Pounced/Thrash/Attack_F/...) —
// the old showcase-first order made all 21 species play their attack animation in the
// Skin Designer and MyDino previews. A candidate only wins early if it actually ships
// an idle-named clip; the first candidate with ANY clip is remembered as a fallback so
// species without an idle export still animate. If nothing in the chain has a clip, the
// first successfully-loaded static scene is returned so a model still renders (just static).
// Exported so FleetDinoModel (Skin Designer viewer) can reuse this exact proven chain
// instead of inventing a second convention for the same dino-assets layout.
const hasIdleClip = (anims) => (anims || []).some((c) => /idle/i.test(c.name || ""));
export async function loadSpeciesGlb(loader, species) {
  let staticOnly = null;
  let animFallback = null;
  for (const file of ["mesh_idle.glb", "showcase.glb", "anims.glb"]) {
    try {
      const g = await loadGlb(loader, dinoAssetUrl(species, file));
      if (g?.scene) {
        if (g.animations?.length) {
          if (hasIdleClip(g.animations)) return g;
          if (!animFallback) animFallback = g;
        } else if (!staticOnly) {
          staticOnly = g;
        }
      }
    } catch (e) { /* try the next candidate */ }
  }
  try {
    const meshG = await loadGlb(loader, dinoAssetUrl(species, "mesh.glb"));
    if (meshG?.scene) {
      let animations = meshG.animations || [];
      if (!animations.length) {
        try {
          const idleG = await loadGlb(loader, dinoAssetUrl(species, "idle.glb"));
          if (idleG?.animations?.length) animations = idleG.animations;
        } catch (e) { /* no separate idle clip available either */ }
      }
      if (animations.length && (hasIdleClip(animations) || !animFallback)) return { scene: meshG.scene, animations };
      if (!staticOnly) staticOnly = { scene: meshG.scene, animations: [] };
    }
  } catch (e) { /* mesh.glb missing too */ }
  return animFallback || staticOnly;
}

// Session-scoped GLB cache so many simultaneous viewers (the vault cards) fetch
// and parse each species at most once. Every instance renders a
// SkeletonUtils.clone() of the cached scene -- plain Object3D.clone(true) keeps
// the SOURCE skeleton bound, so clones would stay frozen at bind pose;
// SkeletonUtils rebinds the bones per clone so each instance animates
// independently. The cached geometry is SHARED across instances and must never
// be disposed by any single viewer (renderer.dispose() releases each canvas's
// own GPU copies on unmount).
const _speciesGlbCache = new Map(); // species -> Promise<{scene, animations} | null>
export function loadSpeciesGlbCached(loader, species) {
  let entry = _speciesGlbCache.get(species);
  if (!entry) {
    entry = loadSpeciesGlb(loader, species).catch((e) => {
      _speciesGlbCache.delete(species); // transient failure: allow a retry later
      throw e;
    });
    _speciesGlbCache.set(species, entry);
  }
  return entry;
}

// Full animation library (anims.glb): its OWN mesh + skeleton + every native
// clip (WalkF, RunF, ...) authored for that exact rig. This is the only
// reliable source for non-idle gaits — the per-clip sidecar files (walk.glb
// etc.) use heterogeneous per-species rig conventions (DinoRef identity vs
// -90°X, different pelvis axes), so cross-file retargeting onto the showcase
// scene stretches limbs or re-orients the whole body. Bigger download
// (~10-47 MB), so it only loads when a caller asks for a non-idle clip;
// species without anims.glb (Kentrosaurus) fall back to the showcase chain.
const _animsGlbCache = new Map(); // species -> Promise<{scene, animations} | null>
function loadSpeciesAnimsGlbCached(loader, species) {
  let entry = _animsGlbCache.get(species);
  if (!entry) {
    entry = loadGlb(loader, dinoAssetUrl(species, "anims.glb"))
      .then((g) => (g?.scene && g.animations?.length ? g : null))
      .catch(() => null)
      .then((g) => g || loadSpeciesGlbCached(loader, species));
    _animsGlbCache.set(species, entry);
  }
  return entry;
}

// Slim walk-only export (walk_native.glb, 0.6-2.3 MB): the SAME anims.glb mesh
// + rig subset to its single native walk clip server-side — no retargeting, so
// none of the sidecar-clip rig traps apply. Light enough for the always-on
// vault CARDS, which full anims.glb (10-47 MB) never was. Species without the
// export (or without anims.glb at all, e.g. Kentrosaurus) fall through the
// full-anims chain and ultimately back to the idle showcase chain.
const _walkGlbCache = new Map(); // species -> Promise<{scene, animations} | null>
// A gait export whose UVs were stripped (bare gltf-transform prune() in
// make_walk_glb.mjs builds before 2026-07-16) makes every fragment sample the
// tint mask at UV(0,0) — the mask's background corner — so the whole dino
// renders one flat default color instead of its skin. Treat a UV-less file as
// unusable here; the walk lane always has the full-anims chain to fall to.
function hasMeshUvs(g) {
  let meshes = 0;
  let withUv = 0;
  g?.scene?.traverse?.((o) => {
    if (o.isMesh && o.geometry) {
      meshes++;
      if (o.geometry.attributes?.uv) withUv++;
    }
  });
  return meshes > 0 && withUv === meshes;
}
function loadSpeciesWalkGlbCached(loader, species) {
  let entry = _walkGlbCache.get(species);
  if (!entry) {
    // ?v=uv1: /dino-assets/* is served immutable max-age=1y on unversioned
    // URLs, and every pre-2026-07-16 walk_native.glb (UV-less, see above) is
    // cached under the bare URL — the query busts straight past those copies.
    entry = loadGlb(loader, dinoAssetUrl(species, "walk_native.glb?v=uv1"))
      .then((g) => (g?.scene && g.animations?.length && hasMeshUvs(g) ? g : null))
      .catch(() => null)
      .then((g) => g || loadSpeciesAnimsGlbCached(loader, species));
    _walkGlbCache.set(species, entry);
  }
  return entry;
}

/**
 * Live species preview for the MyDino Stats tab, and (in stored-skin mode) the
 * vault cards/preview. Loads the fleet dino-asset chain through the shared GLB
 * cache, applies FleetDinoModel's tint-mask material using the caller's skin
 * colours (skin prop -> GET /api/snapshot when liveSnapshotFallback -> species
 * default palette), autoplays the idle clip, and shows a graceful placeholder
 * offline/without a dino. Falls back to the flat diffuse-only material (no
 * tint) when a species has no pattern mask asset yet.
 *
 * interactive=false renders a fixed-camera showcase (no OrbitControls, no
 * drag hint) for small cards; onStatus reports every status change so a card
 * can swap to a flat image when 3D is unavailable.
 *
 * animate=false holds the model on a single mid-clip frame — a still pose,
 * never a T-pose (the bind pose is never a presentable stance). With
 * animate=false and no turntable, the render loop also stops drawing until
 * something actually changes (a drag, a resize), so a grid of still cards
 * costs no continuous GPU work.
 *
 * view="side" frames the body in PROFILE (camera perpendicular to the
 * tail->pelvis line) instead of the default head-on "front".
 */
export function SpeciesViewer3D({ species, active, skin, className = "", interactive = true, liveSnapshotFallback = true, preferClip = "idle", turntable = false, animate = true, view = "front", onStatus }) {
  const mountRef = useRef(null);
  const glRef = useRef({});
  const [status, setStatus] = useState("idle"); // idle | loading | ready | error
  const onStatusRef = useRef(onStatus);
  onStatusRef.current = onStatus;
  // Stable primitive key so a poll tick that merely re-fetches an UNCHANGED skin
  // (new object reference, same values) does not tear down and rebuild the whole
  // WebGL scene — only a genuinely different skin (or species/active) does.
  const skinKey = skin ? JSON.stringify(skin) : "";

  useEffect(() => {
    const applyStatus = (s) => { setStatus(s); onStatusRef.current?.(s); };
    const mount = mountRef.current;
    if (!active || !species || !mount) { applyStatus("idle"); return undefined; }

    let disposed = false;
    applyStatus("loading");

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: interactive ? "high-performance" : "low-power" });
    } catch (e) {
      applyStatus("error");
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 1000);
    camera.position.set(0, 1.6, 5);

    scene.add(new THREE.AmbientLight(0xffffff, 0.45));
    scene.add(new THREE.HemisphereLight(0xcfe8d0, 0x0c1409, 0.6));
    const sun = new THREE.DirectionalLight(0xfff4d4, 1.4);
    sun.position.set(5, 9, 6);
    scene.add(sun);
    const rim = new THREE.DirectionalLight(0x9fe6b0, 0.5);
    rim.position.set(-6, 4, -4);
    scene.add(rim);

    // On-demand rendering: a still (animate=false, no turntable) viewer only
    // draws when something actually changed — model ready, texture arrived,
    // resize, or an OrbitControls move. The rAF loop still ticks (it is what
    // drives controls damping) but issues no draw call, so a vault grid of
    // still cards costs idle GPU work instead of N continuous render loops.
    // Declared ABOVE the controls block: the "change" listener below captures
    // requestRender at attach time, and a `const` further down would be in its
    // temporal dead zone there — a hard crash on mount, not a subtle bug.
    let needsRender = true;
    const requestRender = () => { needsRender = true; };

    let controls = null;
    if (interactive) {
      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.enablePan = false;
      controls.minDistance = 2;
      controls.maxDistance = 12;
      controls.target.set(0, 1, 0);
      controls.addEventListener("change", requestRender);
    } else {
      camera.lookAt(0, 1, 0);
    }

    const clock = new THREE.Clock();
    let mixer = null;
    let root = null;
    let raf = 0;
    let fitCamera = null; // set once the model is loaded; re-run on every resize
    // Root-motion pin: gait clips animate the rig's top locomotion node
    // (DinoRef-family) with real yaw + travel, so a playing walk slowly turns
    // and wanders off the framed pose — on cards that reads as the model
    // "spinning" out of the camera line. Pinning that node to its framed-pose
    // transform every frame keeps the body planted (limbs still animate) while
    // preserving the up-correction baked into the same node's track.
    let rootPin = null;
    // Turntable pivot: the grounded model is x/z-centered at the origin, so
    // spinning this group rotates it about its own center column.
    const pivot = new THREE.Group();
    scene.add(pivot);

    function resize() {
      // clientWidth/Height, NOT getBoundingClientRect(): the vault preview
      // opens inside a framer-motion layout morph that animates via transform
      // scale, and getBoundingClientRect() includes transforms — sizing the
      // canvas to that transient tiny rect (with no later ResizeObserver event,
      // since the LAYOUT size never changes) left the model small in a corner.
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      if (w < 1 || h < 1) return;
      // updateStyle=true so the canvas CSS size always matches the mount box —
      // without it the canvas displays at its device-pixel attribute size and
      // the view renders cropped/offset inside overflow-hidden parents.
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      if (fitCamera) fitCamera();
      requestRender();
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    function loop() {
      raf = requestAnimationFrame(loop);
      const dt = clock.getDelta();
      if (mixer && animate) {
        mixer.update(dt);
        if (rootPin) {
          rootPin.node.position.copy(rootPin.position);
          rootPin.node.quaternion.copy(rootPin.quaternion);
          rootPin.node.scale.copy(rootPin.scale);
        }
        needsRender = true;
      }
      if (turntable) { pivot.rotation.y += dt * 0.35; needsRender = true; }
      if (controls) controls.update(); // may fire "change" -> requestRender
      if (!needsRender) return;
      needsRender = false;
      renderer.render(scene, camera);
    }
    loop();

    const loader = new GLTFLoader();
    (async () => {
      try {
        const wantsGait = !!preferClip && preferClip !== "idle";
        const g = await (wantsGait
          ? (/walk/i.test(preferClip)
              ? loadSpeciesWalkGlbCached(loader, species)
              : loadSpeciesAnimsGlbCached(loader, species))
          : loadSpeciesGlbCached(loader, species));
        if (disposed) return;
        if (!g?.scene) { applyStatus("error"); return; }

        // Clone from the shared cache (SkeletonUtils rebinds skinned meshes to
        // the clone's own bones — see loadSpeciesGlbCached above).
        root = SkeletonUtils.clone(g.scene);

        const animations = g.animations || [];
        // requestRender in the callback: on a still viewer the loop has already
        // stopped drawing by the time this texture lands, so without it the
        // model would sit on screen untextured.
        const diffuse = new THREE.TextureLoader().load(dinoAssetUrl(species, "diffuse.webp"), (t) => {
          t.colorSpace = THREE.SRGBColorSpace;
          t.flipY = false;
          requestRender();
        });

        let maskTex = null;
        try {
          const resolved = await resolveLiveSkin(species, skin, liveSnapshotFallback);
          if (disposed) return;
          // ★ THIS VIEWER SHOWS A SKIN THE PLAYER ALREADY OWNS, so the old
          // Math.min(2, …) was not a cosmetic clamp — a player wearing Pattern 4
          // in game was shown Pattern 2's sheet here and told nothing. Resolved
          // against the art this site actually ships (skinPatternCatalog), which
          // never names a file that is not on the box. No manifest is fetched:
          // the art table alone is the authority on what can be rendered, and the
          // catch below still covers a genuinely missing file.
          const patternIdx = clampPattern(resolved.pattern, null, species);
          maskTex = await loadTexture(dinoAssetUrl(species, patternFile(patternIdx)));
          if (disposed) { maskTex.dispose(); return; }
          maskTex.colorSpace = THREE.NoColorSpace;
          maskTex.flipY = false;
          root.traverse((o) => {
            if (!o.isMesh) return;
            o.material = makeTintedMaterial(diffuse, maskTex, resolved.colors);
            o.castShadow = false;
            o.receiveShadow = false;
            o.frustumCulled = false;
          });
        } catch (e) {
          // No pattern-mask asset for this species yet (or a transient load error) —
          // fall back to the original flat diffuse-only material, same as before.
          maskTex = null;
          root.traverse((o) => {
            if (!o.isMesh) return;
            o.material = new THREE.MeshStandardMaterial({ map: diffuse, roughness: 0.78, metalness: 0.06 });
            o.castShadow = false;
            o.receiveShadow = false;
            o.frustumCulled = false;
          });
        }
        glRef.current.maskTex = maskTex;

        // Frame + center on the ground plane so every species (hatchling to apex) fills the stage similarly.
        root.updateMatrixWorld(true);
        const box = new THREE.Box3().setFromObject(root);
        const size = box.getSize(new THREE.Vector3());
        const scale = 3.4 / Math.max(0.0001, Math.max(size.x, size.z));
        root.scale.setScalar(scale);
        root.updateMatrixWorld(true);
        const b2 = new THREE.Box3().setFromObject(root);
        root.position.x -= (b2.min.x + b2.max.x) / 2;
        root.position.z -= (b2.min.z + b2.max.z) / 2;
        root.position.y -= b2.min.y;
        pivot.add(root);

        // Fit the camera to the model for THIS canvas's aspect ratio. The old
        // fixed camera (0,1.6,5 -> 0,1,0) framed the wide live panel fine but
        // left tall/narrow mounts (the vault preview column, small cards) with
        // a tiny model in a corner: it only ever normalized footprint, never
        // the view distance against the vertical/horizontal FOV. Hero framing:
        // fit the bounding sphere against the tighter FOV axis, then pull in
        // ~15% -- the sphere overestimates elongated bodies' real screen
        // footprint, so a strict fit reads small. Registered as fitCamera so
        // every resize (including the preview's layout-morph settling) refits.
        root.updateMatrixWorld(true);
        const fitBox = new THREE.Box3().setFromObject(root);
        const center = fitBox.getCenter(new THREE.Vector3());
        const sphere = fitBox.getBoundingSphere(new THREE.Sphere());
        // Landmark bones for view orientation: clips are free to yaw the rig
        // (DinoRef carries each clip's authored facing), so a fixed camera
        // azimuth can end up head-on. The posed TAIL-END -> PELVIS axis gives
        // a long, stable horizontal body line on every species (pelvis->head
        // is useless on bipeds — the head rides almost directly above the
        // hips, leaving a tiny noisy projection). view="front" shoots DEAD
        // AHEAD down that axis; view="side" shoots along its ground-plane
        // PERPENDICULAR, so the body reads as a full-length profile
        // (owner 2026-07-27: "looking to the side and not to the front").
        // Interactive surfaces still offer drag-to-rotate for other angles.
        let pelvisBone = null;
        let tailEndBone = null; // traverse order is hierarchical: last /tail/ match is deepest
        root.traverse((o) => {
          if (!o.isBone) return;
          if (!pelvisBone && /pelvis/i.test(o.name || "")) pelvisBone = o;
          if (/tail/i.test(o.name || "")) tailEndBone = o;
        });
        const fitBounds = fitBox.clone(); // posed box; recenterPosed refreshes it
        fitCamera = () => {
          const vFov = THREE.MathUtils.degToRad(camera.fov);
          const hFov = 2 * Math.atan(Math.tan(vFov / 2) * Math.max(0.1, camera.aspect));
          const sideView = view === "side";
          // Fallback azimuth when the rig carries no pelvis/tail landmark: a
          // 3/4 view for "front", a near-broadside one for "side".
          const dir = sideView
            ? new THREE.Vector3(0.98, 0.18, 0.10)
            : new THREE.Vector3(0.42, 0.18, 0.89);
          if (pelvisBone && tailEndBone) {
            // forward = tail tip -> pelvis, projected to the ground plane
            const body = pelvisBone.getWorldPosition(new THREE.Vector3())
              .sub(tailEndBone.getWorldPosition(new THREE.Vector3()));
            body.y = 0;
            if (body.lengthSq() > 1e-4) {
              body.normalize();
              // side = rotate the body axis 90 deg about the ground normal
              if (sideView) dir.set(-body.z, 0, body.x); else dir.copy(body);
              dir.y = 0.2;
              dir.normalize();
            }
          }
          // Distance: fit the POSED box's corners against both FOV axes for
          // THIS view direction. The old bounding-sphere fit blew up on
          // head-on framings — the body length counts as camera-axis depth,
          // not screen size, so a sphere fit left the card mostly empty.
          // Interactive frames near edge-to-edge (drag/zoom available); cards
          // keep ~10% margin.
          const margin = interactive ? 0.95 : 0.9;
          const tanV = Math.tan(vFov / 2) * margin;
          const tanH = Math.tan(hFov / 2) * margin;
          const rightAxis = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), dir);
          if (rightAxis.lengthSq() < 1e-6) rightAxis.set(1, 0, 0); else rightAxis.normalize();
          let dist = Math.max(0.0001, sphere.radius) * 0.35; // floor: never inside the model
          const rel = new THREE.Vector3();
          for (let ci = 0; ci < 8; ci++) {
            rel.set(
              (ci & 1) ? fitBounds.max.x : fitBounds.min.x,
              (ci & 2) ? fitBounds.max.y : fitBounds.min.y,
              (ci & 4) ? fitBounds.max.z : fitBounds.min.z,
            ).sub(center);
            const depth = rel.dot(dir); // toward the camera
            dist = Math.max(dist, depth + Math.abs(rel.y) / tanV, depth + Math.abs(rel.dot(rightAxis)) / tanH);
          }
          camera.position.copy(center).addScaledVector(dir, dist);
          camera.lookAt(center);
          camera.near = Math.max(0.01, dist / 100);
          camera.far = Math.max(1000, dist * 50);
          camera.updateProjectionMatrix();
          if (controls) {
            controls.target.copy(center);
            controls.minDistance = dist * 0.4;
            controls.maxDistance = dist * 3;
          }
          requestRender();
        };
        fitCamera();

        // Clips re-orient the rig around DinoRef, which sits away from the
        // bind-pose center — once a pose is applied, the bind-pose grounding
        // above no longer holds (the model ends up off the turntable axis and
        // half out of frame). Box3.setFromObject can't see this (skinned
        // meshes report bind-pose geometry bounds), so recenter from the TRUE
        // skinned bounds of the applied pose, then reframe.
        const recenterPosed = () => {
          root.updateMatrixWorld(true);
          const posed = new THREE.Box3();
          let any = false;
          root.traverse((o) => {
            if (o.isSkinnedMesh && o.skeleton && o.computeBoundingBox) {
              o.skeleton.update();
              o.computeBoundingBox();
              if (o.boundingBox) {
                posed.union(o.boundingBox.clone().applyMatrix4(o.matrixWorld));
                any = true;
              }
            }
          });
          if (!any || posed.isEmpty()) return;
          const dx = (posed.min.x + posed.max.x) / 2;
          const dz = (posed.min.z + posed.max.z) / 2;
          const dy = posed.min.y;
          root.position.x -= dx;
          root.position.z -= dz;
          root.position.y -= dy;
          root.updateMatrixWorld(true);
          const shifted = posed.clone().translate(new THREE.Vector3(-dx, -dy, -dz));
          center.copy(shifted.getCenter(new THREE.Vector3()));
          shifted.getBoundingSphere(sphere);
          fitBounds.copy(shifted);
          fitCamera();
        };

        if (animations.length) {
          mixer = new THREE.AnimationMixer(root);
          const clip = pickPreferredClip(animations, preferClip);
          if (clip) {
            const action = mixer.clipAction(clip);
            action.setLoop(THREE.LoopRepeat, Infinity);
            // Desync sibling cards showing the same species — an in-phase grid
            // of identical idles reads as one looping GIF, not living animals.
            // A STILL viewer instead samples the SAME mid-clip frame every
            // time: deterministic, never the bind/T-pose (which is what simply
            // not playing a clip would leave on screen), and never frame 0 —
            // several idle exports open on a wide transitional stance
            // (Pteranodon's has both wings thrown out) that the animal settles
            // out of within the first beat, which is not the pose to freeze.
            action.time = animate ? Math.random() * (clip.duration || 0) : (clip.duration || 0) * 0.5;
            action.play();
            // Apply the first pose NOW, then recenter + reframe on it.
            mixer.update(0);
            // Capture the root-motion pin from THIS framed pose: the clip's
            // topmost animated node is the locomotion root (its track carries
            // yaw/travel plus the rig's up-correction, so we freeze it at the
            // framed value rather than deleting the track).
            const animatedNames = new Set(clip.tracks.map((t) => t.name.split(".")[0]));
            let pinNode = null;
            let pinDepth = Infinity;
            root.traverse((o) => {
              if (!animatedNames.has(o.name)) return;
              let d = 0;
              for (let p = o; p && p !== root; p = p.parent) d++;
              if (d < pinDepth) { pinDepth = d; pinNode = o; }
            });
            if (pinNode) {
              rootPin = {
                node: pinNode,
                position: pinNode.position.clone(),
                quaternion: pinNode.quaternion.clone(),
                scale: pinNode.scale.clone(),
              };
            }
            if (!animate) action.paused = true; // hold this frame; loop stops drawing
            recenterPosed();
          }
        }
        requestRender();
        applyStatus("ready");
      } catch (e) {
        if (!disposed) applyStatus("error");
      }
    })();

    glRef.current = { renderer, ro };

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls?.dispose?.();
      if (root) {
        root.traverse((o) => {
          if (!o.isMesh) return;
          // GEOMETRY is shared with the module GLB cache (every clone reuses the
          // source BufferGeometry) — never dispose it here; renderer.dispose()
          // below releases this canvas's GPU copies. Materials/textures ARE
          // per-instance: dispose the diffuse map, the separate tint-mask texture
          // (not covered by `.map`, it lives in the shader's uTintMask uniform),
          // then the material itself (same pattern as FleetDinoModel.jsx).
          const mats = Array.isArray(o.material) ? o.material : [o.material];
          mats.forEach((m) => {
            m?.map?.dispose?.();
            m?.userData?.tintUniforms?.uTintMask?.value?.dispose?.();
            m?.dispose?.();
          });
        });
      }
      glRef.current.maskTex?.dispose?.();
      renderer.dispose();
      if (renderer.domElement.parentElement === mount) mount.removeChild(renderer.domElement);
    };
    // skinKey (a derived primitive) is the intentional dependency, not `skin` itself —
    // see the comment on skinKey above (avoids tearing down the WebGL scene on every
    // poll tick that merely re-fetches an unchanged skin as a new object reference).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [species, active, skinKey, interactive, liveSnapshotFallback, preferClip, turntable, animate, view]);

  const showOverlay = status !== "ready";
  const message = !active
    ? "No hay dinosaurio activo para mostrar."
    : status === "error"
    ? "Vista 3D no disponible para esta especie."
    : "Cargando modelo 3D…";

  return (
    <div className={`relative w-full h-full overflow-hidden ${className}`} data-testid="species-viewer-3d" data-status={status}>
      <div ref={mountRef} className="absolute inset-0" />
      {showOverlay && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 text-center px-6 pointer-events-none">
          {status === "loading" ? (
            <Loader2 size={26} className="animate-spin text-emerald-400" />
          ) : (
            <Egg size={30} className="text-muted-foreground/50" />
          )}
          <p className="text-xs text-muted-foreground max-w-[220px] leading-relaxed">{message}</p>
        </div>
      )}
      {!showOverlay && interactive && (
        <div className="absolute bottom-2.5 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 text-[10px] font-bold px-2.5 py-1 rounded-full glass border border-white/10 text-muted-foreground pointer-events-none">
          <Move3d size={11} /> ARRASTRA PARA ROTAR
        </div>
      )}
    </div>
  );
}

export default SpeciesViewer3D;
