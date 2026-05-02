"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

export default function Mars() {
  const groupRef = useRef<THREE.Group>(null);
  const marsRef = useRef<THREE.Mesh>(null);

  useFrame((_, delta) => {
    if (marsRef.current) marsRef.current.rotation.y += delta * 0.2;
    if (groupRef.current) groupRef.current.rotation.y += delta * 0.02;
  });

  return (
    <group ref={groupRef} position={[4, -0.3, 3.5]}>
      {/* ── Mars surface ── */}
      <mesh ref={marsRef}>
        <sphereGeometry args={[0.38, 48, 48]} />
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

              float n1 = noise(uv * 10.0);
              float n2 = noise(uv * 20.0) * 0.5;
              float n3 = noise(uv * 40.0) * 0.25;
              float pattern = n1 + n2 + n3;

              vec3 darkRed = vec3(0.45, 0.12, 0.04);
              vec3 midRed = vec3(0.65, 0.2, 0.06);
              vec3 lightRed = vec3(0.8, 0.3, 0.1);
              vec3 pole = vec3(0.9, 0.85, 0.8);

              vec3 col = mix(darkRed, midRed, pattern);
              col = mix(col, lightRed, smoothstep(0.6, 0.8, pattern));

              // Polar caps
              float absLat = abs(uv.y - 0.5) * 2.0;
              col = mix(col, pole, smoothstep(0.8, 0.95, absLat) * 0.6);

              float fresnel = 1.0 - abs(dot(vNormal, vec3(0,0,1)));
              col += vec3(0.5, 0.2, 0.1) * fresnel * 0.1;

              gl_FragColor = vec4(col, 1.0);
            }
          `}
        />
      </mesh>

      {/* ── Thin atmosphere ── */}
      <mesh>
        <sphereGeometry args={[0.46, 32, 32]} />
        <shaderMaterial
          transparent depthWrite={false}
          blending={THREE.AdditiveBlending}
          uniforms={{ uColor: { value: new THREE.Color("#ff9966") } }}
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
              fresnel = pow(fresnel, 4.5);
              gl_FragColor = vec4(uColor, fresnel * 0.25);
            }
          `}
        />
      </mesh>

      {/* ── Tiny moons Phobos & Deimos ── */}
      <mesh position={[0.55, 0.1, 0.15]}>
        <sphereGeometry args={[0.04, 8, 8]} />
        <meshStandardMaterial color="#888" roughness={0.8} />
      </mesh>
      <mesh position={[-0.5, -0.05, -0.3]}>
        <sphereGeometry args={[0.025, 6, 6]} />
        <meshStandardMaterial color="#999" roughness={0.8} />
      </mesh>
    </group>
  );
}
