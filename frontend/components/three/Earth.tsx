"use client";

import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

export default function Earth() {
  const groupRef = useRef<THREE.Group>(null);
  const earthRef = useRef<THREE.Mesh>(null);
  const cloudsRef = useRef<THREE.Mesh>(null);

  const moonOrbit = useMemo(() => ({ radius: 1.5, speed: 0.5, angle: 0 }), []);

  useFrame((_, delta) => {
    if (earthRef.current) earthRef.current.rotation.y += delta * 0.25;
    if (cloudsRef.current) cloudsRef.current.rotation.y += delta * 0.18;
    moonOrbit.angle += delta * moonOrbit.speed;
  });

  return (
    <group ref={groupRef} position={[7.5, -0.5, -1.5]}>
      {/* ── Earth surface ── */}
      <mesh ref={earthRef}>
        <sphereGeometry args={[0.62, 64, 64]} />
        <shaderMaterial
          uniforms={{
            uTime: { value: 0 },
          }}
          vertexShader={/* glsl */ `
            varying vec3 vPos;
            varying vec3 vNormal;
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

            float hash(vec2 p) {
              return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
            }

            float noise(vec2 p) {
              vec2 i = floor(p);
              vec2 f = fract(p);
              f = f * f * (3.0 - 2.0 * f);
              return mix(
                mix(hash(i), hash(i + vec2(1,0)), f.x),
                mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), f.x), f.y);
            }

            void main() {
              // Convert 3D position to spherical coords for continent-like patterns
              float theta = atan(vPos.z, vPos.x);
              float phi = asin(vPos.y / length(vPos));

              vec2 uv = vec2(theta / 6.28318 + 0.5, phi / 3.14159 + 0.5);

              // Multi-octave noise for continents
              float n1 = noise(uv * 8.0);
              float n2 = noise(uv * 16.0) * 0.5;
              float n3 = noise(uv * 32.0) * 0.25;
              float land = n1 + n2 + n3;

              // Oceans (deep blue) vs land (green-brown)
              vec3 oceanDeep = vec3(0.02, 0.15, 0.45);
              vec3 oceanShallow = vec3(0.05, 0.35, 0.65);
              vec3 landLow = vec3(0.15, 0.45, 0.12);
              vec3 landMid = vec3(0.25, 0.40, 0.08);
              vec3 landHigh = vec3(0.35, 0.32, 0.06);
              vec3 ice = vec3(0.85, 0.88, 0.92);

              // Threshold for ocean vs land
              float shore = smoothstep(0.45, 0.52, land);
              float mountain = smoothstep(0.65, 0.75, land);

              vec3 col = mix(oceanShallow, oceanDeep, n1 * 0.5 + 0.3);
              col = mix(col, mix(landLow, landMid, mountain), shore);
              col = mix(col, landHigh, mountain * 0.6);

              // Polar ice caps
              float absLat = abs(uv.y - 0.5) * 2.0;
              float iceFactor = smoothstep(0.75, 0.92, absLat);
              col = mix(col, ice, iceFactor * 0.7);

              // Atmosphere fresnel
              float fresnel = 1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0)));
              col += vec3(0.25, 0.55, 0.85) * fresnel * 0.15;

              gl_FragColor = vec4(col, 1.0);
            }
          `}
        />
      </mesh>

      {/* ── Cloud layer ── */}
      <mesh ref={cloudsRef}>
        <sphereGeometry args={[0.645, 48, 48]} />
        <shaderMaterial
          transparent
          depthWrite={false}
          uniforms={{
            uTime: { value: 0 },
          }}
          vertexShader={/* glsl */ `
            varying vec3 vPos;
            varying vec3 vNormal;
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

            float hash(vec2 p) {
              return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
            }

            float noise(vec2 p) {
              vec2 i = floor(p);
              vec2 f = fract(p);
              f = f * f * (3.0 - 2.0 * f);
              return mix(
                mix(hash(i), hash(i + vec2(1,0)), f.x),
                mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), f.x), f.y);
            }

            void main() {
              float theta = atan(vPos.z, vPos.x);
              float phi = asin(vPos.y / length(vPos));
              vec2 uv = vec2(theta / 6.28318 + 0.5, phi / 3.14159 + 0.5);

              float n = noise(uv * 12.0 + uTime * 0.02) * 0.6 + noise(uv * 24.0 - uTime * 0.015) * 0.4;
              float alpha = smoothstep(0.35, 0.7, n) * 0.35;

              // No clouds near poles
              float absLat = abs(uv.y - 0.5) * 2.0;
              alpha *= 1.0 - smoothstep(0.7, 0.95, absLat);

              gl_FragColor = vec4(1.0, 1.0, 1.0, alpha);
            }
          `}
        />
      </mesh>

      {/* ── Atmosphere glow ── */}
      <mesh>
        <sphereGeometry args={[0.78, 48, 48]} />
        <shaderMaterial
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          uniforms={{
            uColor: { value: new THREE.Color("#4dc9f6") },
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
              float alpha = fresnel * 0.45;
              gl_FragColor = vec4(uColor, alpha);
            }
          `}
        />
      </mesh>

      {/* ── Outer atmosphere ── */}
      <mesh>
        <sphereGeometry args={[0.92, 48, 48]} />
        <shaderMaterial
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          uniforms={{
            uColor: { value: new THREE.Color("#06b6d4") },
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
              fresnel = pow(fresnel, 5.5);
              float alpha = fresnel * 0.2;
              gl_FragColor = vec4(uColor, alpha);
            }
          `}
        />
      </mesh>

      {/* ── Moon ── */}
      <mesh
        position={[
          Math.cos(moonOrbit.angle) * moonOrbit.radius,
          0,
          Math.sin(moonOrbit.angle) * moonOrbit.radius,
        ]}
      >
        <sphereGeometry args={[0.1, 20, 20]} />
        <meshStandardMaterial
          color="#c8c8d0"
          roughness={0.7}
          metalness={0.05}
          emissive="#111111"
          emissiveIntensity={0.15}
        />
      </mesh>

      {/* ── Subtle ring ── */}
      <mesh rotation={[Math.PI * 0.4, 0, 0]}>
        <ringGeometry args={[0.98, 1.01, 80]} />
        <meshBasicMaterial
          color="#4dc9f6"
          transparent
          opacity={0.12}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}
