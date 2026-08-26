import React, { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useGLTF } from "@react-three/drei";

// Evrima-style skin config: colour regions (each with alpha) + gender/variation/pattern.
export const DEFAULT_SKIN_CFG = {
  gender: "male",
  variation: 0,
  pattern: 0,
  bellyLevel: 0.42,
  metalness: 0.05,
  roughness: 0.82,
  colors: {
    maleDisplay: { c: "#c9c9c9", a: 1 },
    markings:    { c: "#2a2118", a: 1 },
    body:        { c: "#8a6b45", a: 1 },
    flank:       { c: "#a67c4e", a: 1 },
    underbelly:  { c: "#d9c9a8", a: 1 },
    detail:      { c: "#5c3f26", a: 1 },
    eyes:        { c: "#e2c53a", a: 1 },
  },
};

const _col = (o, k, d) => o?.colors?.[k]?.c || d;
const _a = (o, k) => (o?.colors?.[k]?.a ?? 1);

// Regions come from the OBJECT-SPACE surface normal (anatomically correct):
//  underbelly = faces down (-Y), male display / dorsal = faces up (+Y), flank = faces sideways.
const COMMON_GLSL = `
  uniform vec3 uBody, uFlank, uUnderbelly, uMaleDisplay, uMarkings, uDetail;
  uniform float aFlank, aUnderbelly, aMaleDisplay, aMarkings, aDetail;
  uniform float uVariation, uBellyLevel, uMale;
  uniform int uPattern;
  varying vec3 vLocalPos;
  varying vec3 vObjNormal;
  float h3(vec3 p){ return fract(sin(dot(p, vec3(12.9898,78.233,37.719)))*43758.5453); }
  float noise3(vec3 p){
    vec3 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
    return mix(mix(mix(h3(i),h3(i+vec3(1,0,0)),f.x),mix(h3(i+vec3(0,1,0)),h3(i+vec3(1,1,0)),f.x),f.y),
               mix(mix(h3(i+vec3(0,0,1)),h3(i+vec3(1,0,1)),f.x),mix(h3(i+vec3(0,1,1)),h3(i+vec3(1,1,1)),f.x),f.y),f.z);
  }
  float patFn(int ty, vec3 p, float s, float seed){
    vec3 q = p*s + seed*7.13;
    if(ty==1){ float n=noise3(q); return smoothstep(0.60,0.72,n); }
    if(ty==2){ float b=sin((p.y*s)+noise3(q)*2.0); return smoothstep(0.15,0.45,b); }
    if(ty==3){ float n=noise3(q); return smoothstep(0.09,0.02,abs(n-0.5)); }
    return 0.0;
  }`;

const COLOR_GLSL = `#include <color_fragment>
  float lum = 0.85;
  #ifdef USE_MAP
    lum = dot(texture2D(map, vMapUv).rgb, vec3(0.299,0.587,0.114));
  #endif
  vec3 n = normalize(vObjNormal);
  float ny = n.y;
  float belly = smoothstep(0.10, -0.40, ny);            // downward-facing = underbelly
  float dorsal = smoothstep(0.45, 0.85, ny);            // upward-facing = dorsal/male display
  float flank = smoothstep(0.30, 0.95, 1.0 - abs(ny));  // sideways-facing = flank
  vec3 region = uBody;
  region = mix(region, uFlank, flank * aFlank * 0.6);
  region = mix(region, uUnderbelly, belly * aUnderbelly);
  region = mix(region, uMaleDisplay, dorsal * aMaleDisplay * uMale);
  float scl = 3.5 + uVariation * 1.6;
  float pat = patFn(uPattern, vLocalPos, scl, uVariation);
  region = mix(region, uMarkings, pat * aMarkings);
  float dpat = patFn(uPattern, vLocalPos, scl*2.2, uVariation+3.0);
  region = mix(region, uDetail, dpat * aDetail * 0.6);
  float shade = 0.45 + lum * 1.0;
  diffuseColor.rgb = region * shade;`;

function setUniforms(shaders, cfg) {
  shaders.forEach((sh) => {
    if (!sh?.uniforms?.uBody) return;
    const u = sh.uniforms;
    u.uBody.value.set(_col(cfg, "body", "#8a6b45"));
    u.uFlank.value.set(_col(cfg, "flank", "#a67c4e"));
    u.uUnderbelly.value.set(_col(cfg, "underbelly", "#d9c9a8"));
    u.uMaleDisplay.value.set(_col(cfg, "maleDisplay", "#c9c9c9"));
    u.uMarkings.value.set(_col(cfg, "markings", "#2a2118"));
    u.uDetail.value.set(_col(cfg, "detail", "#5c3f26"));
    u.aFlank.value = _a(cfg, "flank");
    u.aUnderbelly.value = _a(cfg, "underbelly");
    u.aMaleDisplay.value = _a(cfg, "maleDisplay");
    u.aMarkings.value = _a(cfg, "markings");
    u.aDetail.value = _a(cfg, "detail");
    u.uPattern.value = cfg.pattern | 0;
    u.uVariation.value = cfg.variation ?? 0;
    u.uBellyLevel.value = cfg.bellyLevel ?? 0.42;
    u.uMale.value = cfg.gender === "female" ? 0 : 1;
  });
}

// Detect a specific skin region from a material/mesh name (for models already split by region).
function detectRegion(name) {
  const n = (name || "").toLowerCase();
  if (/eye/.test(n)) return "eyes";
  if (/underbelly|belly|ventral/.test(n)) return "underbelly";
  if (/maledisplay|display|crest|frill|dorsal/.test(n)) return "maleDisplay";
  if (/marking|pattern|stripe|spot/.test(n)) return "markings";
  if (/detail|accent/.test(n)) return "detail";
  if (/flank/.test(n)) return "flank";
  return null; // body / unknown -> geometry-normal shader
}

function makeUniforms(c) {
  const C = (k, d) => ({ value: new THREE.Color(_col(c, k, d)) });
  return {
    uBody: C("body", "#8a6b45"), uFlank: C("flank", "#a67c4e"), uUnderbelly: C("underbelly", "#d9c9a8"),
    uMaleDisplay: C("maleDisplay", "#c9c9c9"), uMarkings: C("markings", "#2a2118"), uDetail: C("detail", "#5c3f26"),
    aFlank: { value: _a(c, "flank") }, aUnderbelly: { value: _a(c, "underbelly") }, aMaleDisplay: { value: _a(c, "maleDisplay") },
    aMarkings: { value: _a(c, "markings") }, aDetail: { value: _a(c, "detail") },
    uPattern: { value: c.pattern | 0 }, uVariation: { value: c.variation ?? 0 },
    uBellyLevel: { value: c.bellyLevel ?? 0.42 }, uMale: { value: c.gender === "female" ? 0 : 1 },
  };
}

export function DinoModel3D({ url, config }) {
  const { scene } = useGLTF(url);
  const shadersRef = useRef([]); const bodyMatsRef = useRef([]); const eyeMatsRef = useRef([]);
  const regionMatsRef = useRef([]);   // meshes whose material name maps to a specific region
  const cfgRef = useRef(config); cfgRef.current = config;

  const group = useMemo(() => {
    const root = scene.clone(true);
    shadersRef.current = []; bodyMatsRef.current = []; eyeMatsRef.current = []; regionMatsRef.current = [];

    root.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true; o.receiveShadow = true;
      const src = o.material;
      const c = cfgRef.current || DEFAULT_SKIN_CFG;
      const region = detectRegion(src?.name) || detectRegion(o.name);

      // Eyes: isolated coloured + emissive material.
      if (region === "eyes") {
        o.material = new THREE.MeshStandardMaterial({
          map: src?.map || null,
          color: new THREE.Color(_col(c, "eyes", "#e2c53a")),
          emissive: new THREE.Color(_col(c, "eyes", "#e2c53a")),
          emissiveIntensity: 0.35 * _a(c, "eyes"), metalness: 0.1, roughness: 0.35,
        });
        eyeMatsRef.current.push(o.material);
        return;
      }

      // Model already split into named regions -> paint that region EXACTLY (1:1, like the game).
      if (region) {
        const mat = new THREE.MeshStandardMaterial({
          map: src?.map || null, normalMap: src?.normalMap || null,
          color: new THREE.Color(_col(c, region, "#8a6b45")),
          metalness: c.metalness ?? 0.05, roughness: c.roughness ?? 0.82,
        });
        o.material = mat; regionMatsRef.current.push({ mat, region });
        return;
      }

      // Single body mesh (no region split) -> geometry-normal approximation shader.
      const mat = new THREE.MeshStandardMaterial({
        map: src?.map || null, normalMap: src?.normalMap || null,
        color: 0xffffff, metalness: c.metalness ?? 0.05, roughness: c.roughness ?? 0.82,
      });
      mat.onBeforeCompile = (shader) => {
        Object.assign(shader.uniforms, makeUniforms(cfgRef.current || DEFAULT_SKIN_CFG));
        shader.vertexShader = shader.vertexShader
          .replace("#include <common>", "#include <common>\nvarying vec3 vLocalPos;\nvarying vec3 vObjNormal;")
          .replace("#include <begin_vertex>", "#include <begin_vertex>\n vLocalPos = position;\n vObjNormal = normalize(normal);");
        shader.fragmentShader = shader.fragmentShader
          .replace("#include <common>", "#include <common>\n" + COMMON_GLSL)
          .replace("#include <map_fragment>", "")   // use albedo only for luminance detail
          .replace("#include <color_fragment>", COLOR_GLSL);
        shadersRef.current.push(shader);
      };
      o.material = mat; bodyMatsRef.current.push(mat);
    });
    return root;
  }, [scene]);

  useEffect(() => {
    setUniforms(shadersRef.current, config);
    bodyMatsRef.current.forEach((m) => { m.metalness = config.metalness ?? 0.05; m.roughness = config.roughness ?? 0.82; });
    regionMatsRef.current.forEach(({ mat, region }) => {
      mat.color.set(_col(config, region, "#8a6b45"));
      mat.metalness = config.metalness ?? 0.05; mat.roughness = config.roughness ?? 0.82;
    });
    eyeMatsRef.current.forEach((m) => {
      const c = _col(config, "eyes", "#e2c53a");
      m.color.set(c); m.emissive.set(c); m.emissiveIntensity = 0.35 * _a(config, "eyes");
    });
  }, [config]);

  return <primitive object={group} />;
}
