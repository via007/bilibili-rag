"use client";

import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

export default function Jupiter() {
  const groupRef = useRef<THREE.Group>(null);
  const jupiterRef = useRef<THREE.Mesh>(null);

  const moons = useMemo(() => [
    { radius: 1.7, speed: 0.6, angle: 0, size: 0.08 },
    { radius: 2.0, speed: 0.4, angle: 1.5, size: 0.06 },
    { radius: 2.3, speed: 0.3, angle: 3.0, size: 0.07 },
    { radius: 2.6, speed: 0.25, angle: 5.0, size: 0.05 },
  ], []);

  useFrame((_, delta) => {
    if (jupiterRef.current) jupiterRef.current.rotation.y += delta * 0.35;
    if (groupRef.current) groupRef.current.rotation.y += delta * 0.015;
    moons.forEach((m) => { m.angle += delta * m.speed; });
  });

  return (
    <group ref={groupRef} position={[-3, -0.4, 4]}>
      {/* ── Jupiter surface with bands ── */}
      <mesh ref={jupiterRef}>
        <sphereGeometry args={[1.0, 64, 64]} />
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
              float phi = asin(vPos.y / length(vPos));
              float latitude = phi / 3.14159 + 0.5;
              float theta = atan(vPos.z, vPos.x);
              float longitude = theta / 6.28318 + 0.5;

              // Horizontal bands
              float bands = sin(latitude * 25.0) * 0.5
                          + sin(latitude * 17.0 + 1.5) * 0.3
                          + sin(latitude * 11.0 + 0.8) * 0.2;
              bands = bands * 0.5 + 0.5;

              // Turbulence in bands
              float turb = noise(vec2(longitude * 12.0, latitude * 28.0)) * 0.3;
              bands += turb;

              vec3 lightBand = vec3(0.85, 0.65, 0.35);
              vec3 midBand = vec3(0.7, 0.45, 0.2);
              vec3 darkBand = vec3(0.5, 0.3, 0.12);
              vec3 redSpot = vec3(0.75, 0.35, 0.15);

              vec3 col = mix(darkBand, lightBand, bands);
              col = mix(col, midBand, smoothstep(0.3, 0.5, bands));

              // Great Red Spot
              float spotDist = length(vec2(longitude * 2.0 - 1.0, (latitude - 0.42) * 3.0));
              float spot = 1.0 - smoothstep(0.08, 0.15, spotDist);
              col = mix(col, redSpot, spot * 0.7);

              float fresnel = 1.0 - abs(dot(vNormal, vec3(0,0,1)));
              col += vec3(0.4, 0.3, 0.15) * fresnel * 0.1;

              gl_FragColor = vec4(col, 1.0);
            }
          `}
        />
      </mesh>

      {/* ── Atmosphere glow ── */}
      <mesh>
        <sphereGeometry args={[1.15, 48, 48]} />
        <shaderMaterial
          transparent depthWrite={false}
          blending={THREE.AdditiveBlending}
          uniforms={{ uColor: { value: new THREE.Color("#cc8844") } }}
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
              fresnel = pow(fresnel, 3.5);
              gl_FragColor = vec4(uColor, fresnel * 0.3);
            }
          `}
        />
      </mesh>

      {/* ── Galilean moons ── */}
      {moons.map((m, i) => (
        <mesh
          key={i}
          position={[
            Math.cos(m.angle) * m.radius,
            (i - 1.5) * 0.15,
            Math.sin(m.angle) * m.radius,
          ]}
        >
          <sphereGeometry args={[m.size, 12, 12]} />
          <meshStandardMaterial
            color={["#ddd", "#bbb", "#e8d8c0", "#ccb"][i]}
            roughness={0.6}
            emissive="#111"
            emissiveIntensity={0.1}
          />
        </mesh>
      ))}
    </group>
  );
}
