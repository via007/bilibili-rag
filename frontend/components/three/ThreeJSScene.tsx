"use client";

import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import ParticleField from "./ParticleField";
import DockModuleOrbit from "./DockModuleOrbit";
import Sun from "./Sun";
import Earth from "./Earth";
import Mars from "./Mars";
import Jupiter from "./Jupiter";
import Saturn from "./Saturn";
import Neptune from "./Neptune";
import MeteorShower from "./MeteorShower";
import TechGalaxy from "./TechGalaxy";
import type { DockModule } from "@/lib/dock-registry";

interface ThreeJSSceneProps {
  dimmed?: boolean;
  dockModules: DockModule[];
  activePanelId: string | null;
  onTogglePanel: (id: string) => void;
}

export default function ThreeJSScene({
  dimmed = false,
  dockModules,
  activePanelId,
  onTogglePanel,
}: ThreeJSSceneProps) {
  return (
    <div className="three-scene-container" style={{ flex: 1, width: "100%", height: "100%" }}>
      <Canvas
        style={{
          pointerEvents: dimmed ? "none" : "auto",
        }}
        camera={{ position: [0, 0, 12], fov: 50 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: false }}
      >
        <color attach="background" args={["#0d0d0d"]} />
        <ambientLight intensity={0.3} color="#ffd599" />
        {/* Warm sunlight from the sun direction */}
        <directionalLight position={[-7.5, 0.8, -2]} intensity={1.2} color="#ffcc66" />
        <directionalLight position={[0, -2, 5]} intensity={0.15} color="#ffaa33" />
        {/* Subtle fill to prevent harsh shadows */}
        <pointLight position={[5, 5, 5]} intensity={0.25} color="#ffd599" />
        {/* Bottom rim light for depth */}
        <pointLight position={[0, -8, 2]} intensity={0.2} color="#886633" />
        <ParticleField />
        <DockModuleOrbit
          dockModules={dockModules}
          activePanelId={activePanelId}
          onTogglePanel={onTogglePanel}
          dimmed={dimmed}
        />
        <TechGalaxy dimmed={dimmed} />
        <Sun />
        <Earth />
        <Mars />
        <Jupiter />
        <Saturn />
        <Neptune />
        <MeteorShower />
        <OrbitControls
          enableDamping
          dampingFactor={0.08}
          minDistance={5}
          maxDistance={20}
          maxPolarAngle={Math.PI * 0.7}
          enabled={!dimmed}
        />
      </Canvas>
      {dimmed && <div className="scene-overlay" />}
    </div>
  );
}
