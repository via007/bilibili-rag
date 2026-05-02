"use client";

import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

const METEOR_COUNT = 8;
const MAX_LIFETIME = 3.5; // seconds
const SPAWN_INTERVAL = 4; // seconds between new meteors

interface MeteorData {
  position: THREE.Vector3;
  direction: THREE.Vector3;
  speed: number;
  length: number;
  age: number;
  lifetime: number;
  color: THREE.Color;
}

export default function MeteorShower() {
  const groupRef = useRef<THREE.Group>(null);
  const spawnTimer = useRef(0);

  const meteors = useRef<MeteorData[]>([]);

  // Pre-create line geometries for reuse
  const lineGeo = useMemo(() => new THREE.BufferGeometry(), []);

  const spawnMeteor = (): MeteorData => {
    // Spawn from random edge of a large bounding box
    const side = Math.floor(Math.random() * 4); // 0=top, 1=right, 2=bottom, 3=left
    let x: number, y: number, z: number;

    switch (side) {
      case 0: // top
        x = (Math.random() - 0.5) * 16;
        y = 5 + Math.random() * 3;
        z = (Math.random() - 0.5) * 8;
        break;
      case 1: // right
        x = 8 + Math.random() * 2;
        y = (Math.random() - 0.5) * 8;
        z = (Math.random() - 0.5) * 8;
        break;
      case 2: // bottom
        x = (Math.random() - 0.5) * 16;
        y = -5 - Math.random() * 3;
        z = (Math.random() - 0.5) * 8;
        break;
      default: // left
        x = -8 - Math.random() * 2;
        y = (Math.random() - 0.5) * 8;
        z = (Math.random() - 0.5) * 8;
    }

    // Direction: mostly diagonal, slight variation
    const dx = (Math.random() - 0.3) * 1.4;
    const dy = -0.4 - Math.random() * 1.0;
    const dz = (Math.random() - 0.5) * 0.6;
    const dir = new THREE.Vector3(dx, dy, dz).normalize();

    // Cyan or white meteor
    const isCyan = Math.random() < 0.5;
    const color = new THREE.Color(
      isCyan ? 0.4 + Math.random() * 0.3 : 0.8 + Math.random() * 0.2,
      isCyan ? 0.7 + Math.random() * 0.3 : 0.8 + Math.random() * 0.2,
      isCyan ? 0.8 + Math.random() * 0.2 : 0.7 + Math.random() * 0.3,
    );

    return {
      position: new THREE.Vector3(x, y, z),
      direction: dir,
      speed: 4 + Math.random() * 6,
      length: 0.6 + Math.random() * 1.2,
      age: 0,
      lifetime: 1.5 + Math.random() * MAX_LIFETIME,
      color,
    };
  };

  useFrame((_, delta) => {
    if (!groupRef.current) return;

    // Spawn new meteors periodically, cap at METEOR_COUNT
    spawnTimer.current += delta;
    if (
      spawnTimer.current > SPAWN_INTERVAL &&
      meteors.current.length < METEOR_COUNT
    ) {
      spawnTimer.current = 0;
      meteors.current.push(spawnMeteor());
    }

    // Ensure we always have some meteors
    if (meteors.current.length === 0) {
      meteors.current.push(spawnMeteor());
    }

    // Update meteor positions
    const dt = delta;
    for (let i = meteors.current.length - 1; i >= 0; i--) {
      const m = meteors.current[i];
      m.age += dt;
      if (m.age > m.lifetime) {
        meteors.current.splice(i, 1);
        continue;
      }
      // Move head position
      m.position.x += m.direction.x * m.speed * dt;
      m.position.y += m.direction.y * m.speed * dt;
      m.position.z += m.direction.z * m.speed * dt;
    }

    // Update line visuals — each meteor = one child line
    const children = groupRef.current.children;
    // Remove excess children
    while (children.length > meteors.current.length) {
      const last = children[children.length - 1];
      if (last) {
        (last as THREE.Line).geometry.dispose();
        ((last as THREE.Line).material as THREE.Material).dispose();
        groupRef.current.remove(last);
      } else {
        break;
      }
    }

    for (let i = 0; i < meteors.current.length; i++) {
      const m = meteors.current[i];
      const lifeRatio = m.age / m.lifetime;

      // Fade in quickly, fade out slowly
      let alpha: number;
      if (lifeRatio < 0.1) {
        alpha = lifeRatio / 0.1;
      } else if (lifeRatio > 0.7) {
        alpha = 1 - (lifeRatio - 0.7) / 0.3;
      } else {
        alpha = 1;
      }

      // Tail position (behind the head)
      const tail = m.position.clone().addScaledVector(m.direction, -m.length);

      // Create or update line geometry
      let line: THREE.Line;
      if (i < children.length) {
        line = children[i] as THREE.Line;
      } else {
        line = new THREE.Line(
          lineGeo.clone(),
          new THREE.LineBasicMaterial({
            color: m.color,
            transparent: true,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          }),
        );
        groupRef.current.add(line);
      }

      const geom = line.geometry;
      const positions = new Float32Array([
        tail.x, tail.y, tail.z,
        m.position.x, m.position.y, m.position.z,
      ]);
      geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geom.setDrawRange(0, 2);

      (line.material as THREE.LineBasicMaterial).opacity = alpha * 0.8;
    }
  });

  return <group ref={groupRef} />;
}
