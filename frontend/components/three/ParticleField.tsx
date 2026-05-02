"use client";

import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

const PARTICLE_COUNT = 800;

export default function ParticleField() {
  const pointsRef = useRef<THREE.Points>(null);

  const { positions, colors } = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3);
    const col = new Float32Array(PARTICLE_COUNT * 3);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      // Random positions in a flattened sphere
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 4 + Math.random() * 6;
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.4; // flatten Y
      pos[i * 3 + 2] = r * Math.cos(phi) - 2;

      // ~15% cyan-tinted particles, rest grayscale
      const isCyan = Math.random() < 0.15;
      if (isCyan) {
        col[i * 3] = 0.02;
        col[i * 3 + 1] = 0.45;
        col[i * 3 + 2] = 0.55;
      } else {
        const brightness = 0.35 + Math.random() * 0.65;
        col[i * 3] = brightness;
        col[i * 3 + 1] = brightness;
        col[i * 3 + 2] = brightness;
      }
    }

    return { positions: pos, colors: col };
  }, []);

  useFrame((state, delta) => {
    if (!pointsRef.current) return;
    const posAttr = pointsRef.current.geometry.attributes.position;
    const arr = posAttr.array as Float32Array;

    const mx = state.pointer.x * 0.3;
    const my = state.pointer.y * 0.3;

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3;
      const x = arr[i3];
      const z = arr[i3 + 2];
      const angle = delta * 0.08;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      arr[i3] = x * cos - z * sin + mx * delta * 0.15;
      arr[i3 + 2] = z * cos + x * sin + my * delta * 0.15;
    }

    posAttr.needsUpdate = true;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
        <bufferAttribute
          attach="attributes-color"
          args={[colors, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.025}
        vertexColors
        transparent
        opacity={0.7}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}
