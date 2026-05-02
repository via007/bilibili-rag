"use client";

import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";

const ARM_COUNT = 3;
const PARTICLES_PER_ARM = 400;
const TOTAL = ARM_COUNT * PARTICLES_PER_ARM;
const GALAXY_RADIUS = 5.5;
const CORE_RADIUS = 0.8;

const TECH_STACK = [
  { name: "Next.js", angle: 0.3, radius: 4.2 },
  { name: "FastAPI", angle: 2.4, radius: 3.8 },
  { name: "Python", angle: 4.5, radius: 4.5 },
  { name: "ChromaDB", angle: 1.2, radius: 3.5 },
  { name: "Three.js", angle: 3.2, radius: 4.0 },
  { name: "SQLite", angle: 5.0, radius: 3.2 },
  { name: "LangChain", angle: 0.8, radius: 4.8 },
  { name: "Whisper ASR", angle: 5.8, radius: 4.3 },
];

export default function TechGalaxy({ dimmed = false }: { dimmed?: boolean }) {
  const groupRef = useRef<THREE.Group>(null);
  const pointsRef = useRef<THREE.Points>(null);

  /* ── spiral particle positions & colors ── */
  const { positions, colors } = useMemo(() => {
    const pos = new Float32Array(TOTAL * 3);
    const col = new Float32Array(TOTAL * 3);

    const armOffsets = Array.from({ length: ARM_COUNT }, (_, i) => (i / ARM_COUNT) * Math.PI * 2);

    for (let arm = 0; arm < ARM_COUNT; arm++) {
      const baseAngle = armOffsets[arm];
      for (let j = 0; j < PARTICLES_PER_ARM; j++) {
        const idx = (arm * PARTICLES_PER_ARM + j) * 3;
        // logarithmic spiral: r grows with j, with some randomness
        const t = j / PARTICLES_PER_ARM;
        const r = CORE_RADIUS + t * (GALAXY_RADIUS - CORE_RADIUS);
        const spiralAngle = baseAngle + t * 4.5; // tight spiral
        const spreadAngle = (Math.random() - 0.5) * (0.4 + t * 0.5); // wider spread at edges
        const angle = spiralAngle + spreadAngle;

        // slight vertical scatter
        const y = (Math.random() - 0.5) * 0.3 * (1 - t * 0.7);

        pos[idx] = Math.cos(angle) * r;
        pos[idx + 1] = y;
        pos[idx + 2] = Math.sin(angle) * r;

        // Color: core = white/gold, outer = warm gold, dimmer
        const brightness = 0.5 + (1 - t) * 0.5;
        col[idx] = brightness;
        col[idx + 1] = brightness * (0.6 + (1 - t) * 0.25);
        col[idx + 2] = brightness * (0.3 + (1 - t) * 0.15);
      }
    }

    return { positions: pos, colors: col };
  }, []);

  /* ── rotation ── */
  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.04;
    }
  });

  return (
    <group ref={groupRef}>
      {/* Galaxy particles */}
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
          <bufferAttribute attach="attributes-color" args={[colors, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={0.03}
          vertexColors
          transparent
          opacity={0.75}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>

      {/* Tech labels */}
      {!dimmed && TECH_STACK.map((tech, i) => {
        const x = Math.cos(tech.angle) * tech.radius;
        const z = Math.sin(tech.angle) * tech.radius;
        return (
          <Html
            key={i}
            position={[x, (Math.random() - 0.5) * 0.4, z]}
            center
            distanceFactor={10}
            style={{ pointerEvents: "none" }}
          >
            <div
              style={{
                color: "#fbbf24",
                fontSize: "10px",
                fontWeight: 600,
                letterSpacing: "0.04em",
                whiteSpace: "nowrap",
                padding: "2px 8px",
                borderRadius: "6px",
                background: "#1a1a08",
                border: "1px solid rgba(245, 158, 11, 0.3)",
                fontFamily: "system-ui, -apple-system, sans-serif",
              }}
            >
              {tech.name}
            </div>
          </Html>
        );
      })}
    </group>
  );
}
