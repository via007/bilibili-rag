"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

export default function Neptune() {
  const groupRef = useRef<THREE.Group>(null);
  const neptuneRef = useRef<THREE.Mesh>(null);

  useFrame((_, delta) => {
    if (neptuneRef.current) neptuneRef.current.rotation.y += delta * 0.12;
    if (groupRef.current) groupRef.current.rotation.y += delta * 0.008;
  });

  return (
    <group ref={groupRef} position={[-4.5, -0.3, -4]}>
      {/* ── Neptune surface ── */}
      <mesh ref={neptuneRef}>
        <sphereGeometry args={[0.55, 48, 48]} />
        <shaderMaterial
          uniforms={{}}
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

            float hash(vec2 p) {
              return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
            }
            float noise(vec2 p) {
              vec2 i = floor(p);
              vec2 f = fract(p);
              f = f * f * (3.0 - 2.0 * f);
              return mix(mix(hash(i), hash(i+vec2(1,0)), f.x),
                         mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), f.x), f.y);
            }

            void main() {
              float theta = atan(vPos.z, vPos.x);
              float phi = asin(vPos.y / length(vPos));
              vec2 uv = vec2(theta / 6.28318 + 0.5, phi / 3.14159 + 0.5);

              float n1 = noise(uv * 14.0);
              float n2 = noise(uv * 28.0) * 0.4;
              float pattern = n1 + n2;

              vec3 deepBlue = vec3(0.08, 0.15, 0.55);
              vec3 midBlue = vec3(0.15, 0.3, 0.7);
              vec3 lightBlue = vec3(0.25, 0.45, 0.78);
              vec3 whiteSpot = vec3(0.7, 0.85, 0.95);

              vec3 col = mix(deepBlue, midBlue, pattern);
              col = mix(col, lightBlue, smoothstep(0.55, 0.7, pattern));

              // Occasional bright storm spots
              float storm = noise(uv * 35.0);
              col = mix(col, whiteSpot, smoothstep(0.72, 0.8, storm) * 0.3);

              float fresnel = 1.0 - abs(dot(vNormal, vec3(0,0,1)));
              col += vec3(0.2, 0.4, 0.7) * fresnel * 0.15;

              gl_FragColor = vec4(col, 1.0);
            }
          `}
        />
      </mesh>

      {/* ── Atmosphere glow ── */}
      <mesh>
        <sphereGeometry args={[0.64, 40, 40]} />
        <shaderMaterial
          transparent depthWrite={false}
          blending={THREE.AdditiveBlending}
          uniforms={{ uColor: { value: new THREE.Color("#4466cc") } }}
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
              float fresnel = 1.0 - abs(dot(vNormal, vec3(0,0,1)));
              fresnel = pow(fresnel, 4.0);
              gl_FragColor = vec4(uColor, fresnel * 0.3);
            }
          `}
        />
      </mesh>

      {/* ── Faint ring ── */}
      <mesh rotation={[Math.PI * 0.48, 0.2, 0]}>
        <ringGeometry args={[0.72, 0.78, 64]} />
        <meshBasicMaterial
          color="#6688cc"
          side={THREE.DoubleSide}
          transparent
          opacity={0.15}
          depthWrite={false}
        />
      </mesh>

      {/* ── Triton (large moon) ── */}
      <mesh position={[0.5, -0.08, -0.7]}>
        <sphereGeometry args={[0.06, 12, 12]} />
        <meshStandardMaterial color="#bbc" roughness={0.5} emissive="#111" emissiveIntensity={0.1} />
      </mesh>
    </group>
  );
}
