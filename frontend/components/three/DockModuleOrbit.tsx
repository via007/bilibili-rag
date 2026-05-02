"use client";

import { useRef, useMemo, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { DockModule } from "@/lib/dock-registry";

/* ── geometry pool ── */
type GeoKey = "box" | "octahedron" | "icosahedron" | "sphere" | "dodecahedron" | "torus";

const GEO_MAP: Record<GeoKey, THREE.BufferGeometry> = {
  box: new THREE.BoxGeometry(0.5, 0.5, 0.5, 2, 2, 2),
  octahedron: new THREE.OctahedronGeometry(0.45, 0),
  icosahedron: new THREE.IcosahedronGeometry(0.45, 0),
  sphere: new THREE.SphereGeometry(0.42, 24, 24),
  dodecahedron: new THREE.DodecahedronGeometry(0.4, 0),
  torus: new THREE.TorusGeometry(0.35, 0.14, 12, 24),
};

const GEO_KEYS: GeoKey[] = ["sphere", "icosahedron", "dodecahedron", "box", "octahedron", "torus"];

const CYAN = "#06b6d4";
const CYAN_BRIGHT = "#22d3ee";
const GOLD = "#f59e0b";
const GOLD_BRIGHT = "#fbbf24";

/* ── descriptions ── */
const DESCRIPTIONS: Record<string, string> = {
  chat: "语义检索 + LLM 生成回答",
  "chat-history": "查看历史对话记录",
  quiz: "AI 生成练习题测试知识",
  favorites: "管理 B 站收藏夹数据",
  settings: "配置 LLM API 密钥",
  billing: "查看 API 消耗统计",
};

const RING_RADIUS = 3.2;
const FLOW_PARTICLE_COUNT = 12;

interface DockModuleOrbitProps {
  dockModules: DockModule[];
  activePanelId: string | null;
  onTogglePanel: (id: string) => void;
  dimmed?: boolean;
}

export default function DockModuleOrbit({
  dockModules,
  activePanelId,
  onTogglePanel,
  dimmed = false,
}: DockModuleOrbitProps) {
  const ringRef = useRef<THREE.Group>(null);
  const flowParticlesRef = useRef<THREE.Group>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  /* ── ring curve ── */
  const lineCurve = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i < dockModules.length; i++) {
      const angle = (i / dockModules.length) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(angle) * RING_RADIUS, 0, Math.sin(angle) * RING_RADIUS));
    }
    pts.push(pts[0].clone());
    return new THREE.CatmullRomCurve3(pts, true, "catmullrom", 0.5);
  }, [dockModules]);

  const tubePoints = useMemo(() => lineCurve.getPoints(160), [lineCurve]);

  /* ── node positions ── */
  const nodePositions = useMemo(() => {
    return dockModules.map((_, i) => {
      const angle = (i / dockModules.length) * Math.PI * 2;
      return [Math.cos(angle) * RING_RADIUS, 0, Math.sin(angle) * RING_RADIUS] as [number, number, number];
    });
  }, [dockModules]);

  /* ── flow particle offsets ── */
  const flowOffsets = useMemo(
    () => Array.from({ length: FLOW_PARTICLE_COUNT }, (_, i) => i / FLOW_PARTICLE_COUNT),
    [],
  );

  /* ── animation ── */
  useFrame((_, delta) => {
    if (ringRef.current) ringRef.current.rotation.y += delta * 0.06;

    if (flowParticlesRef.current) {
      const speed = delta * 0.14;
      for (let i = 0; i < flowOffsets.length; i++) {
        flowOffsets[i] = (flowOffsets[i] + speed) % 1;
        const pt = lineCurve.getPointAt(flowOffsets[i]);
        const child = flowParticlesRef.current.children[i];
        if (child) child.position.copy(pt);
      }
    }
  });

  return (
    <group ref={ringRef}>
      {/* Ring lines */}
      <line>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[new Float32Array(tubePoints.flatMap((p) => [p.x, p.y, p.z])), 3]}
          />
        </bufferGeometry>
        <lineBasicMaterial color="#06b6d4" transparent opacity={0.18} />
      </line>
      <line>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[new Float32Array(tubePoints.flatMap((p) => [p.x, p.y + 0.002, p.z])), 3]}
          />
        </bufferGeometry>
        <lineBasicMaterial color="#22d3ee" transparent opacity={0.12} />
      </line>

      {/* Flow particles */}
      <group ref={flowParticlesRef}>
        {flowOffsets.map((_, i) => (
          <mesh key={i} position={lineCurve.getPointAt(flowOffsets[i])}>
            <sphereGeometry args={[0.04, 8, 8]} />
            <meshBasicMaterial color="#22d3ee" transparent opacity={0.7} depthWrite={false} />
          </mesh>
        ))}
      </group>

      {/* Dock module nodes */}
      {dockModules.map((mod, i) => {
        const active = activePanelId === mod.id || hoveredId === mod.id;
        const isGold = i % 2 === 1; // alternate: 0=cyan, 1=gold
        const mainColor = isGold ? GOLD : CYAN;
        const brightColor = isGold ? GOLD_BRIGHT : CYAN_BRIGHT;

        return (
          <group key={mod.id} position={nodePositions[i]}>
            <DockOrbitNode
              geometry={GEO_KEYS[i]}
              active={active}
              mainColor={mainColor}
              brightColor={brightColor}
              onClick={() => onTogglePanel(mod.id)}
              onHover={(h) => setHoveredId(h ? mod.id : null)}
            />

            {/* Label */}
            {!dimmed && (
            <Html position={[0, 0.7, 0]} center style={{ pointerEvents: "none" }} distanceFactor={8}>
              <div
                style={{
                  color: active ? brightColor : "#e2e8f0",
                  fontSize: "12px",
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                  whiteSpace: "nowrap",
                  padding: "3px 10px",
                  borderRadius: "6px",
                  background: active ? "#1a2940" : "#0f0f19",
                  border: `1px solid ${active ? mainColor + "66" : "rgba(255,255,255,0.1)"}`,
                  transition: "all 0.2s",
                  fontFamily: "system-ui, -apple-system, sans-serif",
                }}
              >
                {mod.title}
              </div>
            </Html>
            )}

            {/* Description on hover/active */}
            {!dimmed && (hoveredId === mod.id || activePanelId === mod.id) && (
              <Html position={[0, -0.65, 0]} center style={{ pointerEvents: "none" }} distanceFactor={9}>
                <div
                  style={{
                    color: activePanelId === mod.id ? "#e2e8f0" : "#cbd5e1",
                    fontSize: "11px",
                    fontWeight: 500,
                    whiteSpace: "nowrap",
                    padding: "4px 10px",
                    borderRadius: "8px",
                    background: "#141420",
                    border: `1px solid ${mainColor}55`,
                    fontFamily: "system-ui, -apple-system, sans-serif",
                  }}
                >
                  {DESCRIPTIONS[mod.id] || mod.title}
                </div>
              </Html>
            )}
          </group>
        );
      })}
    </group>
  );
}

/* ── individual orbit node ── */

function DockOrbitNode({
  geometry,
  active,
  mainColor,
  brightColor,
  onClick,
  onHover,
}: {
  geometry: GeoKey;
  active: boolean;
  mainColor: string;
  brightColor: string;
  onClick: () => void;
  onHover: (hovered: boolean) => void;
}) {
  const geoRef = useRef<THREE.Group>(null);
  const pulseRef = useRef<THREE.Mesh>(null);
  const geo = GEO_MAP[geometry];

  useFrame((_, delta) => {
    if (geoRef.current) {
      geoRef.current.rotation.x += delta * 0.2;
      geoRef.current.rotation.y += delta * 0.3;
    }
    if (pulseRef.current && active) {
      const s = 1 + Math.sin(Date.now() * 0.004) * 0.15;
      pulseRef.current.scale.setScalar(s);
      (pulseRef.current.material as THREE.MeshBasicMaterial).opacity =
        0.2 + Math.sin(Date.now() * 0.004) * 0.15;
    }
  });

  return (
    <group>
      <group
        ref={geoRef}
        onClick={(e) => {
          e.stopPropagation();
          onClick();
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover(true);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          onHover(false);
          document.body.style.cursor = "";
        }}
      >
        <mesh geometry={geo}>
          <meshStandardMaterial
            color={active ? mainColor : "#555555"}
            roughness={0.3}
            metalness={0.15}
            emissive={active ? mainColor : "#333333"}
            emissiveIntensity={active ? 0.8 : 0.1}
          />
        </mesh>
        <mesh geometry={geo}>
          <meshBasicMaterial
            color={active ? brightColor : "#555555"}
            wireframe
            transparent
            opacity={active ? 0.35 : 0.1}
          />
        </mesh>
      </group>

      {active && (
        <mesh ref={pulseRef}>
          <ringGeometry args={[0.62, 0.67, 48]} />
          <meshBasicMaterial
            color={mainColor}
            transparent
            opacity={0.25}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      )}
    </group>
  );
}
