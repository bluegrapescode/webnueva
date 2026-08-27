import React, { useEffect, Suspense } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, ContactShadows, Bounds, Center, Html, Environment, Lightformer } from "@react-three/drei";
import { Loader2, Move3d } from "lucide-react";
import { FleetDinoModel, Skin3DBoundary } from "@/components/skin3d/FleetDinoModel";

// Grabs a JPEG snapshot of the live canvas (used by the designer for preset thumbnails).
export function Capturer({ captureRef }) {
  const { gl, scene, camera } = useThree();
  useEffect(() => {
    if (!captureRef) return;
    captureRef.current = () => {
      gl.render(scene, camera);
      const src = gl.domElement;
      const W = 480, H = Math.round((W * src.height) / src.width) || 400;
      const off = document.createElement("canvas");
      off.width = W; off.height = H;
      off.getContext("2d").drawImage(src, 0, 0, W, H);
      return off.toDataURL("image/jpeg", 0.72);
    };
  }, [gl, scene, camera, captureRef]);
  return null;
}

// Shared 3D specimen preview for BOTH skin systems (Skin Designer + Glitch Lab).
// Feeds FleetDinoModel the same {slot:{c,a}} colour shape and a pattern index so
// every colour edit repaints the model live and identically in both tools.
export function SkinPreview3D({
  species, colors, pattern = 0,
  advancedColors = null, advancedMapping = null,
  captureRef = null, height = 560,
  testid = "skin-preview-3d", emptyLabel = "Elige una especie para previsualizar.",
}) {
  return (
    <div className="relative rounded-2xl overflow-hidden" style={{ height, background: "radial-gradient(120% 90% at 50% 35%, #0e120f, #050605 78%)" }} data-testid={testid}>
      {!species ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">{emptyLabel}</div>
      ) : (
        // The boundary must wrap the WHOLE Canvas: its fallback is DOM, which R3F
        // cannot reconcile inside <Canvas>, so a failed glb degrades instead of
        // crashing the page root.
        <Skin3DBoundary resetKey={species}>
          <Canvas shadows dpr={[1, 2]} gl={{ preserveDrawingBuffer: true, antialias: true }} camera={{ position: [4.5, 1.1, 5], fov: 38 }}>
            {captureRef && <Capturer captureRef={captureRef} />}
            <ambientLight intensity={0.5} />
            <hemisphereLight args={["#cfe8d0", "#0c1409", 0.5]} />
            <directionalLight position={[5, 9, 6]} intensity={1.4} castShadow shadow-mapSize={[1024, 1024]} />
            <directionalLight position={[-6, 4, -4]} intensity={0.5} color="#9fe6b0" />
            <Suspense fallback={<Html center><div className="flex items-center gap-2 text-emerald text-sm"><Loader2 className="animate-spin" size={16} /> Cargando modelo…</div></Html>}>
              <Bounds fit clip observe margin={1.05}>
                <Center key={species}>
                  <FleetDinoModel species={species} colors={colors} pattern={pattern}
                    advancedColors={advancedColors} advancedMapping={advancedMapping} />
                </Center>
              </Bounds>
              <Environment resolution={256} frames={1}>
                <Lightformer intensity={2.2} position={[0, 4, -6]} scale={[12, 7, 1]} color="#ffffff" />
                <Lightformer intensity={1.1} position={[-5, 1, 2]} scale={[3, 7, 1]} color="#aad9b6" />
                <Lightformer intensity={1.1} position={[5, 1, 2]} scale={[3, 7, 1]} color="#e9e0c4" />
              </Environment>
            </Suspense>
            <ContactShadows position={[0, -1.5, 0]} opacity={0.5} scale={14} blur={2.6} far={4} />
            <OrbitControls makeDefault enablePan enableDamping minDistance={2} maxDistance={14} />
          </Canvas>
        </Skin3DBoundary>
      )}
      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 text-[10px] font-bold px-3 py-1.5 rounded-full glass border border-white/10 text-muted-foreground pointer-events-none">
        <Move3d size={12} /> ARRASTRA PARA ROTAR
      </div>
    </div>
  );
}

export default SkinPreview3D;
