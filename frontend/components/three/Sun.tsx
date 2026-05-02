"use client";

import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

const FLARE_COUNT = 12;
const ORBIT_PARTICLE_COUNT = 30;

export default function Sun() {
  const groupRef = useRef<THREE.Group>(null);
  const coreRef = useRef<THREE.Mesh>(null);
  const glowOuterRef = useRef<THREE.Mesh>(null);
  const glowMidRef = useRef<THREE.Mesh>(null);
  const coronaRef = useRef<THREE.Mesh>(null);

  /* ── flare data ── */
  const flares = useMemo(() =>
    Array.from({ length: FLARE_COUNT }, () => ({
      theta: Math.random() * Math.PI * 2,
      phi: (Math.random() - 0.5) * Math.PI * 0.5,
      length: 0.3 + Math.random() * 0.6,
      speed: 0.4 + Math.random() * 0.8,
      phase: Math.random() * Math.PI * 2,
    })),
  []);

  const orbitParticles = useMemo(() =>
    Array.from({ length: ORBIT_PARTICLE_COUNT }, (_, i) => ({
      angle: (i / ORBIT_PARTICLE_COUNT) * Math.PI * 2,
      radius: 1.6 + Math.random() * 0.5,
      speed: 0.2 + Math.random() * 0.5,
      y: (Math.random() - 0.5) * 0.6,
      size: 0.02 + Math.random() * 0.04,
    })),
  []);

  useFrame((_, delta) => {
    const t = Date.now() * 0.001;
    if (groupRef.current) groupRef.current.rotation.y += delta * 0.06;

    // Core pulsation
    if (coreRef.current) {
      const s = 1 + Math.sin(t * 1.8) * 0.015 + Math.sin(t * 3.2) * 0.01;
      coreRef.current.scale.setScalar(s);
    }

    // Glow shells pulsate in opposite phases
    if (glowMidRef.current) {
      glowMidRef.current.scale.setScalar(1 + Math.sin(t * 2.2 + 1) * 0.03);
    }
    if (glowOuterRef.current) {
      glowOuterRef.current.scale.setScalar(1 + Math.sin(t * 1.6 + 2.5) * 0.05);
    }
    if (coronaRef.current) {
      coronaRef.current.scale.setScalar(1 + Math.sin(t * 1.2) * 0.06);
    }
  });

  return (
    <group ref={groupRef} position={[-7.5, 0.8, -2]}>
      {/* ── Solar surface ── */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.85, 64, 64]} />
        <shaderMaterial
          uniforms={{
            uTime: { value: 0 },
            uColor1: { value: new THREE.Color("#ffcc00") },
            uColor2: { value: new THREE.Color("#ff6600") },
            uColor3: { value: new THREE.Color("#ff4400") },
          }}
          vertexShader={/* glsl */ `
            varying vec3 vPos;
            varying vec3 vNormal;
            varying vec2 vUv;
            void main() {
              vPos = position;
              vNormal = normalize(normalMatrix * normal);
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
          `}
          fragmentShader={/* glsl */ `
            varying vec3 vPos;
            varying vec3 vNormal;
            uniform float uTime;
            uniform vec3 uColor1;
            uniform vec3 uColor2;
            uniform vec3 uColor3;

            // Simple 3D noise
            float hash(vec3 p) {
              float h = dot(p, vec3(127.1, 311.7, 74.7));
              return fract(sin(h) * 43758.5453);
            }

            float noise(vec3 p) {
              vec3 i = floor(p);
              vec3 f = fract(p);
              f = f * f * (3.0 - 2.0 * f);
              return mix(
                mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x),
                    mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
                mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
                    mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
            }

            void main() {
              float n1 = noise(vPos * 4.0 + uTime * 0.15);
              float n2 = noise(vPos * 2.5 - uTime * 0.1);
              float pattern = n1 * 0.6 + n2 * 0.4;

              // Darker spots
              float spot = smoothstep(0.35, 0.7, pattern);

              vec3 col = mix(uColor3, uColor2, pattern);
              col = mix(col, uColor1, spot * 0.5);

              // Brighter limb
              float fresnel = 1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0)));
              col = mix(col, uColor1, fresnel * 0.2);

              gl_FragColor = vec4(col, 1.0);
            }
          `}
        />
      </mesh>

      {/* ── Inner hot glow ── */}
      <mesh ref={glowMidRef}>
        <sphereGeometry args={[1.02, 48, 48]} />
        <shaderMaterial
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          uniforms={{
            uColor: { value: new THREE.Color("#ff8c00") },
          }}
          vertexShader={/* glsl */ `
            varying vec3 vNormal;
            void main() {
              vNormal = normalize(normalMatrix * normal);
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
          `}
          fragmentShader={/* glsl */ `
            varying vec3 vNormal;
            uniform vec3 uColor;
            void main() {
              float fresnel = 1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0)));
              fresnel = pow(fresnel, 2.0);
              float alpha = fresnel * 0.5;
              gl_FragColor = vec4(uColor, alpha);
            }
          `}
        />
      </mesh>

      {/* ── Outer glow shell ── */}
      <mesh ref={glowOuterRef}>
        <sphereGeometry args={[1.35, 48, 48]} />
        <shaderMaterial
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          uniforms={{
            uColor: { value: new THREE.Color("#ff6600") },
          }}
          vertexShader={/* glsl */ `
            varying vec3 vNormal;
            void main() {
              vNormal = normalize(normalMatrix * normal);
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
          `}
          fragmentShader={/* glsl */ `
            varying vec3 vNormal;
            uniform vec3 uColor;
            void main() {
              float fresnel = 1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0)));
              fresnel = pow(fresnel, 3.0);
              float alpha = fresnel * 0.35;
              gl_FragColor = vec4(uColor, alpha);
            }
          `}
        />
      </mesh>

      {/* ── Corona / wide aura ── */}
      <mesh ref={coronaRef}>
        <sphereGeometry args={[1.8, 48, 48]} />
        <shaderMaterial
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          uniforms={{
            uColor: { value: new THREE.Color("#ffaa33") },
          }}
          vertexShader={/* glsl */ `
            varying vec3 vNormal;
            void main() {
              vNormal = normalize(normalMatrix * normal);
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
          `}
          fragmentShader={/* glsl */ `
            varying vec3 vNormal;
            uniform vec3 uColor;
            void main() {
              float fresnel = 1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0)));
              fresnel = pow(fresnel, 5.0);
              float alpha = fresnel * 0.18;
              gl_FragColor = vec4(uColor, alpha);
            }
          `}
        />
      </mesh>

      {/* ── Solar flares ── */}
      {flares.map((f, i) => {
        const t = Date.now() * 0.001;
        const active = Math.sin(t * f.speed + f.phase) > 0.2;
        if (!active) return null;
        const strength = (Math.sin(t * f.speed + f.phase) - 0.2) / 0.8;
        const dir = new THREE.Vector3(
          Math.cos(f.theta) * Math.cos(f.phi),
          Math.sin(f.phi),
          Math.sin(f.theta) * Math.cos(f.phi),
        ).normalize();
        const start = dir.clone().multiplyScalar(1.0);
        const end = dir.clone().multiplyScalar(1.0 + f.length * strength);
        const mid = start.clone().add(end).multiplyScalar(0.5);

        return (
          <mesh key={i} position={mid}>
            <capsuleGeometry args={[0.015 * strength, f.length * strength, 4, 8]} />
            <meshBasicMaterial
              color="#ffcc44"
              transparent
              opacity={0.7 * strength}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
        );
      })}

      {/* ── Orbiting particles ── */}
      {orbitParticles.map((p, i) => (
        <mesh
          key={`orbit-${i}`}
          position={[
            Math.cos(p.angle) * p.radius,
            p.y,
            Math.sin(p.angle) * p.radius,
          ]}
        >
          <sphereGeometry args={[p.size, 6, 6]} />
          <meshBasicMaterial
            color="#ffbb55"
            transparent
            opacity={0.7}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      ))}

      {/* ── Equatorial ring ── */}
      <mesh rotation={[Math.PI * 0.5, 0, 0]}>
        <ringGeometry args={[1.5, 1.53, 80]} />
        <meshBasicMaterial
          color="#ffaa33"
          transparent
          opacity={0.2}
          side={THREE.DoubleSide}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  );
}
