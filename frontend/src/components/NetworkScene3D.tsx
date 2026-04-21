import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, RoundedBox, Float, Line } from '@react-three/drei';
import { useRef, useMemo } from 'react';
import * as THREE from 'three';

/* ─── palette ─── */
const C = {
  floorOffice: '#e8e5e0', floorDC: '#111827',
  wallFrame: '#b8bcc6',
  warmStrip: '#fbbf24', warmGlow: '#fef3c7',
  deskWhite: '#f5f5f0', deskLeg: '#c8c8c0',
  chairSeat: '#2d2d2d', chairBack: '#1a1a1a',
  monitorFrame: '#222222', monitorScreen: '#0f2847',
  rackBody: '#111a2e', rackPanel: '#1a2540', rackPanelAlt: '#223050', rackPort: '#0a0f1a',
  magenta: '#e1067d', magentaGlow: '#ff69b4',
  cyan: '#00cfff', cyanGlow: '#22d3ee', cyanSoft: '#67e8f9',
  purple: '#8b5cf6', purpleGlow: '#a78bfa', purpleSoft: '#c4b5fd',
  blue: '#3b82f6', blueGlow: '#60a5fa',
  green: '#10b981', greenGlow: '#34d399',
  amber: '#f59e0b', amberGlow: '#fbbf24',
  red: '#ef4444',
  teal: '#14b8a6', tealGlow: '#2dd4bf',
  coral: '#f97316', coralGlow: '#fb923c',
  gold: '#eab308', goldGlow: '#facc15',
  lime: '#84cc16', limeGlow: '#a3e635',
  rose: '#f43f5e', roseGlow: '#fb7185',
  indigo: '#6366f1', indigoGlow: '#818cf8',
  white: '#ffffff', port: '#2d3142',
};

/* ═══════════════════════════════════════════════════
   FLOORS
   ═══════════════════════════════════════════════════ */

function OfficeFloor() {
  return (
    <group>
      <RoundedBox args={[6.2, 0.12, 8]} radius={0.04} position={[-1.9, -0.06, 0]}>
        <meshStandardMaterial color={C.floorOffice} metalness={0.05} roughness={0.75} />
      </RoundedBox>
      {Array.from({ length: 7 }).map((_, i) => (
        <mesh key={`otx-${i}`} position={[-4.5 + i * 0.9, 0.002, 0]}>
          <boxGeometry args={[0.004, 0.001, 8]} />
          <meshStandardMaterial color="#d0cdc8" />
        </mesh>
      ))}
      {Array.from({ length: 9 }).map((_, i) => (
        <mesh key={`otz-${i}`} position={[-1.9, 0.002, -4 + i * 1.0]}>
          <boxGeometry args={[6.2, 0.001, 0.004]} />
          <meshStandardMaterial color="#d0cdc8" />
        </mesh>
      ))}
    </group>
  );
}

function DCFloor() {
  return (
    <group>
      <RoundedBox args={[3.8, 0.12, 8]} radius={0.04} position={[3.1, -0.06, 0]}>
        <meshStandardMaterial color={C.floorDC} metalness={0.5} roughness={0.25} />
      </RoundedBox>
      {Array.from({ length: 8 }).map((_, i) => (
        <mesh key={`dtx-${i}`} position={[1.2 + i * 0.5, 0.004, 0]}>
          <boxGeometry args={[0.008, 0.001, 8]} />
          <meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={0.25} transparent opacity={0.18} />
        </mesh>
      ))}
      {Array.from({ length: 17 }).map((_, i) => (
        <mesh key={`dtz-${i}`} position={[3.1, 0.004, -4 + i * 0.5]}>
          <boxGeometry args={[3.8, 0.001, 0.008]} />
          <meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={0.25} transparent opacity={0.18} />
        </mesh>
      ))}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[3.1, 0.003, 0]}>
        <planeGeometry args={[3.6, 7.6]} />
        <meshStandardMaterial color={C.purple} emissive={C.purple} emissiveIntensity={0.1} transparent opacity={0.04} />
      </mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   ANIMATED PERIMETER
   ═══════════════════════════════════════════════════ */

function PerimeterGlow() {
  const ref = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const p = 1.4 + 0.6 * Math.sin(clock.getElapsedTime() * 1.2);
    ref.current.children.forEach(c => {
      if (c instanceof THREE.Mesh && (c.material as THREE.MeshStandardMaterial).emissive)
        (c.material as THREE.MeshStandardMaterial).emissiveIntensity = p;
    });
  });
  const segs: { p: [number, number, number]; s: [number, number, number] }[] = [
    { p: [0, 0.01, -3.98], s: [10, 0.06, 0.08] },
    { p: [0, 0.01, 3.98], s: [10, 0.06, 0.08] },
    { p: [-4.98, 0.01, 0], s: [0.08, 0.06, 8] },
    { p: [4.98, 0.01, 0], s: [0.08, 0.06, 8] },
  ];
  return (
    <group ref={ref}>
      {segs.map((s, i) => (
        <mesh key={i} position={s.p}>
          <boxGeometry args={s.s} />
          <meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={1.8} />
        </mesh>
      ))}
      {segs.map((s, i) => (
        <mesh key={`g${i}`} position={[s.p[0], 0.005, s.p[2]]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[i < 2 ? 10 : 1, i < 2 ? 1 : 8]} />
          <meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={0.4} transparent opacity={0.05} />
        </mesh>
      ))}
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   GLASS WALL
   ═══════════════════════════════════════════════════ */

function GlassWall({ from, to, height = 1.1 }: { from: [number, number]; to: [number, number]; height?: number }) {
  const dx = to[0] - from[0], dz = to[1] - from[1];
  const len = Math.sqrt(dx * dx + dz * dz);
  const angle = Math.atan2(dx, dz);
  const cx = (from[0] + to[0]) / 2, cz = (from[1] + to[1]) / 2;
  return (
    <group>
      <mesh position={[cx, height / 2, cz]} rotation={[0, angle, 0]}>
        <boxGeometry args={[0.03, height, len]} />
        <meshStandardMaterial color="#d0dbe8" metalness={0.35} roughness={0.08} transparent opacity={0.2} />
      </mesh>
      {[height, 0.01].map((y, fi) => (
        <mesh key={fi} position={[cx, y, cz]} rotation={[0, angle, 0]}>
          <boxGeometry args={[0.055, 0.03, len]} />
          <meshStandardMaterial color={C.wallFrame} metalness={0.35} roughness={0.35} />
        </mesh>
      ))}
      {Array.from({ length: Math.max(2, Math.floor(len / 1.4)) }).map((_, pi) => {
        const t = (pi + 0.5) / Math.max(2, Math.floor(len / 1.4));
        return (
          <mesh key={pi} position={[from[0] + dx * t, height / 2, from[1] + dz * t]}>
            <boxGeometry args={[0.035, height, 0.035]} />
            <meshStandardMaterial color={C.wallFrame} metalness={0.3} roughness={0.4} />
          </mesh>
        );
      })}
      <mesh position={[cx, 0.035, cz]} rotation={[0, angle, 0]}>
        <boxGeometry args={[0.012, 0.025, len * 0.92]} />
        <meshStandardMaterial color={C.warmStrip} emissive={C.warmStrip} emissiveIntensity={1.6} />
      </mesh>
      <mesh position={[cx, 0.003, cz]} rotation={[-Math.PI / 2, 0, angle]}>
        <planeGeometry args={[len * 0.92, 0.3]} />
        <meshStandardMaterial color={C.warmStrip} emissive={C.warmStrip} emissiveIntensity={0.3} transparent opacity={0.05} />
      </mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   SERVER RACK (blue LED strips + data waterfall)
   ═══════════════════════════════════════════════════ */

function ServerRack({ position, scale = 1 }: { position: [number, number, number]; scale?: number }) {
  const ledsRef = useRef<THREE.Group>(null!);
  const sideRef = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (ledsRef.current) ledsRef.current.children.forEach((c, i) => {
      if (c instanceof THREE.Mesh) (c.material as THREE.MeshStandardMaterial).emissiveIntensity = 1.5 + Math.sin(t * 3 + i * 1.2) * 0.8;
    });
    if (sideRef.current) sideRef.current.children.forEach(c => {
      if (c instanceof THREE.Mesh) (c.material as THREE.MeshStandardMaterial).emissiveIntensity = 1.2 + Math.sin(t * 1.5) * 0.5;
    });
  });
  const ledC = [C.cyan, C.green, C.blue, C.teal, C.lime, C.amber];
  return (
    <group position={position} scale={scale}>
      <RoundedBox args={[0.5, 1.6, 0.45]} radius={0.02} position={[0, 0.8, 0]}>
        <meshStandardMaterial color={C.rackBody} metalness={0.65} roughness={0.2} />
      </RoundedBox>
      <group ref={sideRef}>
        {[-0.252, 0.252].map((x, si) => (
          <mesh key={si} position={[x, 0.8, 0.15]}>
            <boxGeometry args={[0.008, 1.5, 0.008]} />
            <meshStandardMaterial color={C.blue} emissive={C.blue} emissiveIntensity={1.5} />
          </mesh>
        ))}
        <mesh position={[0, 0.01, 0.15]}>
          <boxGeometry args={[0.5, 0.008, 0.008]} />
          <meshStandardMaterial color={C.blue} emissive={C.blue} emissiveIntensity={1.2} />
        </mesh>
      </group>
      {[0.15, 0.4, 0.65, 0.9, 1.15, 1.4].map((y, i) => (
        <group key={i}>
          <RoundedBox args={[0.42, 0.2, 0.015]} radius={0.004} position={[0, y, 0.22]}>
            <meshStandardMaterial color={i % 2 === 0 ? C.rackPanel : C.rackPanelAlt} metalness={0.5} roughness={0.3} />
          </RoundedBox>
          {Array.from({ length: 6 }).map((_, j) => (
            <mesh key={`v${j}`} position={[-0.15 + j * 0.06, y + 0.06, 0.228]}>
              <boxGeometry args={[0.03, 0.003, 0.001]} />
              <meshStandardMaterial color="#0a0f18" />
            </mesh>
          ))}
          {Array.from({ length: 4 }).map((_, j) => (
            <mesh key={j} position={[-0.1 + j * 0.07, y - 0.02, 0.23]}>
              <boxGeometry args={[0.035, 0.07, 0.003]} />
              <meshStandardMaterial color={C.rackPort} />
            </mesh>
          ))}
        </group>
      ))}
      <group ref={ledsRef}>
        {[0.15, 0.4, 0.65, 0.9, 1.15, 1.4].map((y, i) => (
          <group key={i}>
            <mesh position={[0.195, y + 0.07, 0.23]}>
              <sphereGeometry args={[0.008, 8, 8]} />
              <meshStandardMaterial color={ledC[i]} emissive={ledC[i]} emissiveIntensity={2} />
            </mesh>
            <mesh position={[0.175, y + 0.07, 0.23]}>
              <sphereGeometry args={[0.005, 6, 6]} />
              <meshStandardMaterial color={C.green} emissive={C.green} emissiveIntensity={2} />
            </mesh>
          </group>
        ))}
      </group>
      <mesh position={[0, 1.6, 0.2]}>
        <boxGeometry args={[0.42, 0.02, 0.005]} />
        <meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={2.5} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]}>
        <planeGeometry args={[0.7, 0.6]} />
        <meshStandardMaterial color={C.blue} emissive={C.blue} emissiveIntensity={0.5} transparent opacity={0.06} />
      </mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   DATA WATERFALL (particles rising from DC)
   ═══════════════════════════════════════════════════ */

function DataWaterfall({ position, color = C.cyan, count = 25 }: { position: [number, number, number]; color?: string; count?: number }) {
  const meshRef = useRef<THREE.InstancedMesh>(null!);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const data = useMemo(() => Array.from({ length: count }, () => ({
    x: (Math.random() - 0.5) * 3.2,
    z: (Math.random() - 0.5) * 6.5,
    speed: 0.3 + Math.random() * 0.6,
    offset: Math.random() * 4,
    size: 0.008 + Math.random() * 0.012,
  })), [count]);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    for (let i = 0; i < count; i++) {
      const d = data[i];
      const y = ((t * d.speed + d.offset) % 3);
      dummy.position.set(position[0] + d.x, position[1] + y, position[2] + d.z);
      dummy.scale.setScalar(d.size * 80 * (1 - y / 3));
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    }
    meshRef.current.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[0.012, 6, 6]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={2} transparent opacity={0.6} />
    </instancedMesh>
  );
}

/* ═══════════════════════════════════════════════════
   OFFICE DESK + CHAIR
   ═══════════════════════════════════════════════════ */

function OfficeDesk({ position, rotation = [0, 0, 0] as [number, number, number] }: { position: [number, number, number]; rotation?: [number, number, number] }) {
  return (
    <group position={position} rotation={rotation}>
      <RoundedBox args={[0.6, 0.025, 0.35]} radius={0.006} position={[0, 0.4, 0]}>
        <meshStandardMaterial color={C.deskWhite} metalness={0.05} roughness={0.6} />
      </RoundedBox>
      <mesh position={[-0.28, 0.2, 0]}><boxGeometry args={[0.02, 0.4, 0.34]} /><meshStandardMaterial color={C.deskLeg} metalness={0.2} roughness={0.4} /></mesh>
      <mesh position={[0.28, 0.2, 0]}><boxGeometry args={[0.02, 0.4, 0.34]} /><meshStandardMaterial color={C.deskLeg} metalness={0.2} roughness={0.4} /></mesh>
      <RoundedBox args={[0.3, 0.21, 0.012]} radius={0.004} position={[0, 0.56, -0.1]}>
        <meshStandardMaterial color={C.monitorFrame} metalness={0.4} roughness={0.3} />
      </RoundedBox>
      <mesh position={[0, 0.565, -0.093]}><planeGeometry args={[0.26, 0.17]} /><meshStandardMaterial color={C.monitorScreen} emissive={C.blue} emissiveIntensity={0.4} /></mesh>
      <mesh position={[0, 0.44, -0.1]}><boxGeometry args={[0.04, 0.06, 0.018]} /><meshStandardMaterial color={C.monitorFrame} /></mesh>
      <mesh position={[0, 0.413, -0.1]}><boxGeometry args={[0.08, 0.005, 0.06]} /><meshStandardMaterial color={C.monitorFrame} /></mesh>
      <mesh position={[0, 0.415, 0.04]}><boxGeometry args={[0.16, 0.006, 0.055]} /><meshStandardMaterial color="#3a3a3a" /></mesh>
      <mesh position={[0.14, 0.415, 0.04]}><boxGeometry args={[0.03, 0.008, 0.045]} /><meshStandardMaterial color="#333" /></mesh>
      <RoundedBox args={[0.2, 0.03, 0.2]} radius={0.015} position={[0, 0.3, 0.3]}><meshStandardMaterial color={C.chairSeat} /></RoundedBox>
      <RoundedBox args={[0.2, 0.3, 0.025]} radius={0.01} position={[0, 0.47, 0.4]}><meshStandardMaterial color={C.chairBack} /></RoundedBox>
      <mesh position={[0, 0.15, 0.3]}><cylinderGeometry args={[0.015, 0.015, 0.3, 8]} /><meshStandardMaterial color="#555" metalness={0.5} roughness={0.3} /></mesh>
      {[0, 1, 2, 3, 4].map(i => {
        const a = (i / 5) * Math.PI * 2;
        return <mesh key={i} position={[Math.sin(a) * 0.08, 0.01, 0.3 + Math.cos(a) * 0.08]}><sphereGeometry args={[0.012, 6, 6]} /><meshStandardMaterial color="#444" metalness={0.5} roughness={0.3} /></mesh>;
      })}
    </group>
  );
}

function RoundTable({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      <mesh position={[0, 0.38, 0]}><cylinderGeometry args={[0.25, 0.25, 0.025, 20]} /><meshStandardMaterial color={C.deskWhite} metalness={0.08} roughness={0.55} /></mesh>
      <mesh position={[0, 0.19, 0]}><cylinderGeometry args={[0.025, 0.025, 0.38, 8]} /><meshStandardMaterial color={C.deskLeg} metalness={0.2} roughness={0.4} /></mesh>
      <mesh position={[0, 0.005, 0]}><cylinderGeometry args={[0.12, 0.12, 0.01, 12]} /><meshStandardMaterial color={C.deskLeg} metalness={0.2} roughness={0.4} /></mesh>
      {[0, Math.PI * 0.5, Math.PI, Math.PI * 1.5].map((angle, i) => (
        <mesh key={i} position={[Math.sin(angle) * 0.38, 0.22, Math.cos(angle) * 0.38]}><boxGeometry args={[0.12, 0.015, 0.12]} /><meshStandardMaterial color="#5a4a3a" /></mesh>
      ))}
    </group>
  );
}

function CoffeeMachine({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      <RoundedBox args={[0.7, 0.04, 0.35]} radius={0.008} position={[0, 0.5, 0]}><meshStandardMaterial color="#5c3d2e" metalness={0.1} roughness={0.7} /></RoundedBox>
      <mesh position={[0, 0.65, -0.16]}><boxGeometry args={[0.68, 0.3, 0.02]} /><meshStandardMaterial color="#4a3020" /></mesh>
      {[[-0.3, 0.25, -0.14], [0.3, 0.25, -0.14], [-0.3, 0.25, 0.14], [0.3, 0.25, 0.14]].map((p, i) => (
        <mesh key={i} position={p as [number, number, number]}><boxGeometry args={[0.025, 0.5, 0.025]} /><meshStandardMaterial color="#4a3020" /></mesh>
      ))}
      <RoundedBox args={[0.14, 0.22, 0.14]} radius={0.015} position={[0.2, 0.63, 0.02]}><meshStandardMaterial color="#2a2a2a" metalness={0.4} roughness={0.3} /></RoundedBox>
      <mesh position={[-0.12, 0.54, 0.05]}><cylinderGeometry args={[0.05, 0.04, 0.08, 10]} /><meshStandardMaterial color="#1a1a1a" metalness={0.3} roughness={0.4} /></mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   NETWORK EQUIPMENT
   ═══════════════════════════════════════════════════ */

function Router({ position, rotation = [0, 0, 0] as [number, number, number] }: { position: [number, number, number]; rotation?: [number, number, number] }) {
  return (
    <group position={position} rotation={rotation}>
      <RoundedBox args={[0.5, 0.05, 0.3]} radius={0.01} position={[0, 0.025, 0]}><meshStandardMaterial color={C.white} metalness={0.15} roughness={0.3} /></RoundedBox>
      <mesh position={[0, 0.025, 0.153]}><boxGeometry args={[0.42, 0.012, 0.003]} /><meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={1} /></mesh>
      {[-0.15, 0, 0.15].map((x, i) => (
        <group key={i} position={[x, 0.05, -0.08]} rotation={[-(Math.PI / 7) + i * 0.08, 0, 0]}>
          <mesh><cylinderGeometry args={[0.008, 0.012, 0.3, 8]} /><meshStandardMaterial color={C.white} metalness={0.1} roughness={0.4} /></mesh>
          <mesh position={[0, 0.16, 0]}><sphereGeometry args={[0.015, 8, 8]} /><meshStandardMaterial color={C.white} /></mesh>
        </group>
      ))}
      <mesh position={[0.2, 0.04, 0.153]}><sphereGeometry args={[0.008, 8, 8]} /><meshStandardMaterial color={C.green} emissive={C.green} emissiveIntensity={3} /></mesh>
    </group>
  );
}

function AccessPoint({ position }: { position: [number, number, number] }) {
  const waveRefs = useRef<THREE.Mesh[]>([]);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    waveRefs.current.forEach((m, i) => {
      if (!m) return;
      const phase = (t * 1.2 + i * 0.8) % 3;
      m.scale.set(1 + phase * 0.6, 1, 1 + phase * 0.6);
      (m.material as THREE.MeshStandardMaterial).opacity = Math.max(0, 0.3 - phase * 0.1);
    });
  });
  return (
    <group position={position}>
      <mesh><cylinderGeometry args={[0.15, 0.17, 0.035, 20]} /><meshStandardMaterial color={C.white} metalness={0.15} roughness={0.3} /></mesh>
      <mesh position={[0, -0.02, 0]}><cylinderGeometry args={[0.035, 0.035, 0.005, 10]} /><meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={1.5} transparent opacity={0.8} /></mesh>
      {[0, 1, 2].map(i => (
        <mesh key={i} ref={el => { if (el) waveRefs.current[i] = el; }} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.03, 0]}>
          <torusGeometry args={[0.12, 0.003, 8, 24]} />
          <meshStandardMaterial color={C.cyanGlow} emissive={C.cyanGlow} emissiveIntensity={1} transparent opacity={0.25} />
        </mesh>
      ))}
    </group>
  );
}

function Firewall({ position, rotation = [0, 0, 0] as [number, number, number] }: { position: [number, number, number]; rotation?: [number, number, number] }) {
  return (
    <group position={position} rotation={rotation}>
      <RoundedBox args={[0.7, 0.08, 0.35]} radius={0.012} position={[0, 0.04, 0]}><meshStandardMaterial color={C.white} metalness={0.15} roughness={0.35} /></RoundedBox>
      <mesh position={[-0.26, 0.05, 0.18]}><circleGeometry args={[0.02, 6]} /><meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={2} /></mesh>
      {Array.from({ length: 6 }).map((_, i) => (<mesh key={i} position={[-0.1 + i * 0.065, 0.035, 0.18]}><boxGeometry args={[0.035, 0.022, 0.004]} /><meshStandardMaterial color={C.port} /></mesh>))}
      <mesh position={[0, 0.07, 0.18]}><boxGeometry args={[0.62, 0.008, 0.003]} /><meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={0.8} /></mesh>
      <mesh position={[0.28, 0.06, 0.18]}><sphereGeometry args={[0.006, 8, 8]} /><meshStandardMaterial color={C.green} emissive={C.green} emissiveIntensity={3} /></mesh>
    </group>
  );
}

function NetSwitch({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      <RoundedBox args={[0.65, 0.06, 0.3]} radius={0.012} position={[0, 0.03, 0]}><meshStandardMaterial color={C.white} metalness={0.15} roughness={0.35} /></RoundedBox>
      {Array.from({ length: 8 }).map((_, i) => (
        <group key={i}>
          <mesh position={[-0.22 + i * 0.065, 0.03, 0.153]}><boxGeometry args={[0.035, 0.02, 0.004]} /><meshStandardMaterial color={C.port} /></mesh>
          <mesh position={[-0.22 + i * 0.065, 0.048, 0.153]}><sphereGeometry args={[0.005, 6, 6]} /><meshStandardMaterial color={i % 3 === 0 ? C.amber : C.green} emissive={i % 3 === 0 ? C.amber : C.green} emissiveIntensity={2.5} /></mesh>
        </group>
      ))}
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   CELL TOWER
   ═══════════════════════════════════════════════════ */

function CellTower({ position }: { position: [number, number, number] }) {
  const beaconRef = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => {
    if (beaconRef.current) (beaconRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity = 2 + Math.sin(clock.getElapsedTime() * 4) * 1.5;
  });
  return (
    <group position={position}>
      <mesh position={[0, 0.6, 0]}><cylinderGeometry args={[0.02, 0.035, 1.2, 8]} /><meshStandardMaterial color="#888" metalness={0.6} roughness={0.3} /></mesh>
      {[0, Math.PI * 2 / 3, Math.PI * 4 / 3].map((angle, i) => (
        <group key={i} position={[Math.sin(angle) * 0.08, 1.0, Math.cos(angle) * 0.08]} rotation={[0, angle, 0]}>
          <mesh><boxGeometry args={[0.04, 0.22, 0.015]} /><meshStandardMaterial color="#555" metalness={0.5} roughness={0.3} /></mesh>
          <mesh position={[0, 0, 0.008]}><boxGeometry args={[0.03, 0.16, 0.002]} /><meshStandardMaterial color={C.red} emissive={C.red} emissiveIntensity={0.5} /></mesh>
        </group>
      ))}
      <mesh ref={beaconRef} position={[0, 1.2, 0]}><sphereGeometry args={[0.025, 8, 8]} /><meshStandardMaterial color={C.red} emissive={C.red} emissiveIntensity={3} /></mesh>
      {[0.4, 0.65, 0.9].map((y, i) => (
        <group key={i}><mesh position={[0, y, 0]} rotation={[0, i * 0.5, 0]}><boxGeometry args={[0.22, 0.008, 0.008]} /><meshStandardMaterial color="#888" metalness={0.5} roughness={0.3} /></mesh></group>
      ))}
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   WALL SCREENS
   ═══════════════════════════════════════════════════ */

function WallScreen({ position, rotation = [0, 0, 0] as [number, number, number], color = C.blue }: { position: [number, number, number]; rotation?: [number, number, number]; color?: string }) {
  const ref = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => { if (ref.current) (ref.current.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.3 + 0.15 * Math.sin(clock.getElapsedTime() * 2); });
  return (
    <group position={position} rotation={rotation}>
      <RoundedBox args={[0.5, 0.32, 0.02]} radius={0.008}><meshStandardMaterial color="#1a1a1a" metalness={0.4} roughness={0.3} /></RoundedBox>
      <mesh ref={ref} position={[0, 0, 0.011]}><planeGeometry args={[0.46, 0.28]} /><meshStandardMaterial color="#0a1628" emissive={color} emissiveIntensity={0.35} /></mesh>
      {Array.from({ length: 5 }).map((_, i) => (
        <mesh key={i} position={[-0.14 + i * 0.07, 0.02, 0.012]}><planeGeometry args={[0.04, 0.04 + Math.sin(i * 2.5) * 0.03]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.7} transparent opacity={0.4} /></mesh>
      ))}
      <mesh position={[0, 0.11, 0.012]}><planeGeometry args={[0.4, 0.01]} /><meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={0.8} transparent opacity={0.5} /></mesh>
      <mesh position={[0.2, 0.12, 0.012]}><circleGeometry args={[0.008, 8]} /><meshStandardMaterial color={C.green} emissive={C.green} emissiveIntensity={2} /></mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   HOLOGRAPHIC PANEL (floating HUD)
   ═══════════════════════════════════════════════════ */

function HoloPanel({ position, rotation = [0, 0, 0] as [number, number, number], color = C.cyan }: { position: [number, number, number]; rotation?: [number, number, number]; color?: string }) {
  const ref = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => { if (ref.current) ref.current.position.y = position[1] + Math.sin(clock.getElapsedTime() * 1.2) * 0.03; });
  return (
    <group ref={ref} position={position} rotation={rotation}>
      <mesh><planeGeometry args={[0.45, 0.28]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.15} transparent opacity={0.08} side={THREE.DoubleSide} /></mesh>
      {[{ p: [0, 0.138, 0], s: [0.45, 0.003, 0.001] }, { p: [0, -0.138, 0], s: [0.45, 0.003, 0.001] }, { p: [-0.223, 0, 0], s: [0.003, 0.28, 0.001] }, { p: [0.223, 0, 0], s: [0.003, 0.28, 0.001] }].map((b, i) => (
        <mesh key={i} position={b.p as [number, number, number]}><boxGeometry args={b.s as [number, number, number]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.5} transparent opacity={0.6} /></mesh>
      ))}
      {Array.from({ length: 7 }).map((_, i) => (
        <mesh key={i} position={[-0.14 + i * 0.045, -0.03, 0.001]}><planeGeometry args={[0.022, 0.03 + i * 0.012]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9} transparent opacity={0.35} side={THREE.DoubleSide} /></mesh>
      ))}
      {Array.from({ length: 3 }).map((_, i) => (
        <mesh key={`t${i}`} position={[-0.05, 0.08 - i * 0.025, 0.001]}><planeGeometry args={[0.22 - i * 0.05, 0.006]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.6} transparent opacity={0.3} side={THREE.DoubleSide} /></mesh>
      ))}
      {/* Circular indicator */}
      <mesh position={[0.14, 0.08, 0.001]}><torusGeometry args={[0.025, 0.002, 8, 16]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={1} transparent opacity={0.5} side={THREE.DoubleSide} /></mesh>
      <mesh position={[0.14, 0.08, 0.001]}><circleGeometry args={[0.015, 12]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} transparent opacity={0.15} side={THREE.DoubleSide} /></mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   FLOATING SHIELD ICON
   ═══════════════════════════════════════════════════ */

function ShieldIcon({ position }: { position: [number, number, number] }) {
  const ref = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.position.y = position[1] + Math.sin(clock.getElapsedTime() * 1.5) * 0.06;
      ref.current.rotation.y = clock.getElapsedTime() * 0.3;
    }
  });
  return (
    <group ref={ref} position={position}>
      <mesh><sphereGeometry args={[0.22, 16, 16]} /><meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={0.25} transparent opacity={0.06} /></mesh>
      <mesh position={[0, 0, -0.008]}><circleGeometry args={[0.12, 20]} /><meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={0.3} transparent opacity={0.1} side={THREE.DoubleSide} /></mesh>
      <RoundedBox args={[0.13, 0.15, 0.012]} radius={0.025}><meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={1.2} transparent opacity={0.55} /></RoundedBox>
      <mesh position={[0, -0.015, 0.007]}><boxGeometry args={[0.045, 0.04, 0.002]} /><meshStandardMaterial color={C.white} emissive={C.white} emissiveIntensity={1} transparent opacity={0.85} /></mesh>
      <mesh position={[0, 0.025, 0.007]}><torusGeometry args={[0.017, 0.005, 8, 12, Math.PI]} /><meshStandardMaterial color={C.white} emissive={C.white} emissiveIntensity={1} transparent opacity={0.85} /></mesh>
      <mesh position={[0, -0.5, 0]}><boxGeometry args={[0.003, 0.8, 0.003]} /><meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={0.5} transparent opacity={0.15} /></mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   SHIELD DOME + PULSE WAVES
   ═══════════════════════════════════════════════════ */

function ShieldDome({ position, radius = 3.0 }: { position: [number, number, number]; radius?: number }) {
  const meshRef = useRef<THREE.Mesh>(null!);
  const ringRef = useRef<THREE.Mesh>(null!);
  const pulseRefs = useRef<THREE.Mesh[]>([]);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (meshRef.current) (meshRef.current.material as THREE.MeshStandardMaterial).opacity = 0.04 + 0.02 * Math.sin(t * 0.8);
    if (ringRef.current) (ringRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.6 + 0.3 * Math.sin(t * 1.5);
    pulseRefs.current.forEach((m, i) => {
      if (!m) return;
      const phase = (t * 0.4 + i * 1.5) % 4;
      const s = 1 + phase * 0.15;
      m.scale.set(s, s, s);
      (m.material as THREE.MeshStandardMaterial).opacity = Math.max(0, 0.08 - phase * 0.02);
    });
  });
  return (
    <group position={position}>
      <mesh ref={meshRef}>
        <sphereGeometry args={[radius, 40, 24, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color={C.purpleSoft} emissive={C.purple} emissiveIntensity={0.3} transparent opacity={0.04} side={THREE.DoubleSide} wireframe />
      </mesh>
      <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
        <torusGeometry args={[radius, 0.018, 8, 64]} />
        <meshStandardMaterial color={C.purpleGlow} emissive={C.purple} emissiveIntensity={0.8} transparent opacity={0.5} />
      </mesh>
      {/* Pulse waves expanding from dome */}
      {[0, 1, 2].map(i => (
        <mesh key={i} ref={el => { if (el) pulseRefs.current[i] = el; }}>
          <sphereGeometry args={[radius, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color={C.purpleSoft} emissive={C.purple} emissiveIntensity={0.2} transparent opacity={0.06} side={THREE.DoubleSide} wireframe />
        </mesh>
      ))}
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   AI BRAIN (neural net + orbiting rings)
   ═══════════════════════════════════════════════════ */

function AIBrain({ position }: { position: [number, number, number] }) {
  const groupRef = useRef<THREE.Group>(null!);
  const nodesRef = useRef<THREE.Group>(null!);
  const ringsRef = useRef<THREE.Group>(null!);
  const nodes = useMemo(() => {
    const pts: [number, number, number][] = [];
    [3, 5, 7, 5, 3].forEach((count, li) => { for (let i = 0; i < count; i++) pts.push([(li - 2) * 0.28, (i - (count - 1) / 2) * 0.15, 0]); });
    return pts;
  }, []);
  const nodeColors = useMemo(() => nodes.map((_, i) => [C.cyan, C.magenta, C.purple, C.teal, C.gold, C.coral, C.lime, C.rose][i % 8]), [nodes]);
  const connections = useMemo(() => {
    const conns: [number, number][] = [];
    const layers = [3, 5, 7, 5, 3]; let offset = 0;
    for (let li = 0; li < layers.length - 1; li++) {
      const next = offset + layers[li];
      for (let i = 0; i < layers[li]; i++) for (let j = 0; j < layers[li + 1]; j++) if (Math.random() > 0.45) conns.push([offset + i, next + j]);
      offset = next;
    }
    return conns;
  }, []);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (groupRef.current) groupRef.current.rotation.y = t * 0.25;
    if (nodesRef.current) nodesRef.current.children.forEach((c, i) => { if (c instanceof THREE.Mesh) c.scale.setScalar(1 + 0.4 * Math.sin(t * 2.5 + i * 0.4)); });
    if (ringsRef.current) ringsRef.current.children.forEach((c, i) => { c.rotation.z = t * (0.25 + i * 0.12); c.rotation.x = Math.sin(t * 0.4 + i) * 0.3; });
  });
  return (
    <Float speed={2} rotationIntensity={0.1} floatIntensity={0.35}>
      <group position={position}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.5, 0]}><circleGeometry args={[0.7, 32]} /><meshStandardMaterial color={C.cyanSoft} emissive={C.cyan} emissiveIntensity={0.3} transparent opacity={0.06} /></mesh>
        <group ref={ringsRef}>
          <mesh rotation={[Math.PI / 3, 0, 0]}><torusGeometry args={[0.5, 0.006, 8, 48]} /><meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={1.5} transparent opacity={0.5} /></mesh>
          <mesh rotation={[-Math.PI / 4, Math.PI / 4, 0]}><torusGeometry args={[0.55, 0.005, 8, 48]} /><meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={1.2} transparent opacity={0.4} /></mesh>
          <mesh rotation={[0, Math.PI / 3, Math.PI / 6]}><torusGeometry args={[0.6, 0.004, 8, 48]} /><meshStandardMaterial color={C.gold} emissive={C.gold} emissiveIntensity={1} transparent opacity={0.3} /></mesh>
          <mesh rotation={[Math.PI / 6, -Math.PI / 5, Math.PI / 3]}><torusGeometry args={[0.65, 0.003, 8, 48]} /><meshStandardMaterial color={C.teal} emissive={C.teal} emissiveIntensity={0.8} transparent opacity={0.25} /></mesh>
        </group>
        <group ref={groupRef}>
          {connections.map(([a, b], i) => (
            <Line key={i} points={[nodes[a], nodes[b]]} color={C.cyanSoft} transparent opacity={0.18} lineWidth={1} />
          ))}
          <group ref={nodesRef}>{nodes.map((pos, i) => (
            <mesh key={i} position={pos}><sphereGeometry args={[0.026, 12, 12]} /><meshStandardMaterial color={nodeColors[i]} emissive={nodeColors[i]} emissiveIntensity={2.2} transparent opacity={0.9} /></mesh>
          ))}</group>
        </group>
      </group>
    </Float>
  );
}

/* ═══════════════════════════════════════════════════
   ORBITING DEVICE MODELS (like the reference image)
   ═══════════════════════════════════════════════════ */

/* Mini Router — magenta + white */
function MiniRouter() {
  return (
    <group scale={1.4}>
      <RoundedBox args={[0.35, 0.06, 0.22]} radius={0.012}>
        <meshStandardMaterial color={C.white} metalness={0.1} roughness={0.3} />
      </RoundedBox>
      {[-0.1, 0, 0.1].map((x, i) => (
        <group key={i} position={[x, 0.03, -0.06]} rotation={[-0.3 + i * 0.1, 0, 0]}>
          <mesh><cylinderGeometry args={[0.006, 0.01, 0.18, 6]} /><meshStandardMaterial color={C.white} metalness={0.1} roughness={0.3} /></mesh>
          <mesh position={[0, 0.1, 0]}><sphereGeometry args={[0.012, 6, 6]} /><meshStandardMaterial color={C.white} /></mesh>
        </group>
      ))}
      <mesh position={[0, 0.025, 0.112]}><boxGeometry args={[0.3, 0.008, 0.003]} /><meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={1.2} /></mesh>
      <mesh position={[0.14, 0.035, 0.1]}><sphereGeometry args={[0.008, 6, 6]} /><meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={3} /></mesh>
    </group>
  );
}

/* Mini Switch — magenta + white */
function MiniSwitch() {
  return (
    <group scale={1.4}>
      <RoundedBox args={[0.4, 0.05, 0.2]} radius={0.01}>
        <meshStandardMaterial color={C.white} metalness={0.1} roughness={0.3} />
      </RoundedBox>
      {Array.from({ length: 6 }).map((_, i) => (
        <mesh key={i} position={[-0.12 + i * 0.05, 0, 0.102]}>
          <boxGeometry args={[0.025, 0.018, 0.004]} />
          <meshStandardMaterial color="#e0e0e0" />
        </mesh>
      ))}
      <mesh position={[0, 0.028, 0.102]}><boxGeometry args={[0.32, 0.006, 0.003]} /><meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={1.2} /></mesh>
      <mesh position={[-0.15, 0.028, 0.102]}><sphereGeometry args={[0.006, 6, 6]} /><meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={3} /></mesh>
    </group>
  );
}

/* Mini Satellite Dish — magenta + white */
function MiniSatellite() {
  return (
    <group scale={1.4}>
      <mesh rotation={[0.4, 0, 0]}>
        <sphereGeometry args={[0.1, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2.5]} />
        <meshStandardMaterial color={C.white} metalness={0.15} roughness={0.25} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={[0, 0.04, -0.03]} rotation={[0.4, 0, 0]}>
        <cylinderGeometry args={[0.008, 0.008, 0.12, 6]} />
        <meshStandardMaterial color={C.white} metalness={0.15} roughness={0.3} />
      </mesh>
      <mesh position={[0, 0.1, -0.06]}>
        <sphereGeometry args={[0.015, 6, 6]} />
        <meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={2.5} />
      </mesh>
      <mesh position={[0, -0.06, 0]}>
        <cylinderGeometry args={[0.015, 0.015, 0.08, 6]} />
        <meshStandardMaterial color={C.white} metalness={0.15} roughness={0.3} />
      </mesh>
      <mesh position={[0, -0.1, 0]}>
        <cylinderGeometry args={[0.04, 0.04, 0.01, 8]} />
        <meshStandardMaterial color={C.white} metalness={0.15} roughness={0.3} />
      </mesh>
    </group>
  );
}

/* Mini Server — magenta + white */
function MiniServer() {
  return (
    <group scale={1.4}>
      <RoundedBox args={[0.22, 0.3, 0.18]} radius={0.01}>
        <meshStandardMaterial color={C.white} metalness={0.1} roughness={0.3} />
      </RoundedBox>
      {[0.06, 0, -0.06].map((y, i) => (
        <RoundedBox key={i} args={[0.18, 0.06, 0.01]} radius={0.003} position={[0, y, 0.09]}>
          <meshStandardMaterial color="#f0f0f0" metalness={0.1} roughness={0.3} />
        </RoundedBox>
      ))}
      {[0.06, 0, -0.06].map((y, i) => (
        <mesh key={`l${i}`} position={[0.08, y, 0.095]}>
          <sphereGeometry args={[0.006, 6, 6]} />
          <meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={2.5} />
        </mesh>
      ))}
    </group>
  );
}

/* Mini Access Point — magenta + white */
function MiniAP() {
  return (
    <group scale={1.4}>
      <mesh><cylinderGeometry args={[0.1, 0.12, 0.03, 16]} /><meshStandardMaterial color={C.white} metalness={0.1} roughness={0.3} /></mesh>
      <mesh position={[0, -0.018, 0]}><cylinderGeometry args={[0.025, 0.025, 0.005, 8]} /><meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={1.5} transparent opacity={0.8} /></mesh>
    </group>
  );
}

/* The orbit controller — positions device models around the office */
const ORBIT_DEVICES = [
  { type: 'router', angle: 0 },
  { type: 'switch', angle: Math.PI * 0.25 },
  { type: 'satellite', angle: Math.PI * 0.5 },
  { type: 'server', angle: Math.PI * 0.75 },
  { type: 'router', angle: Math.PI },
  { type: 'ap', angle: Math.PI * 1.15 },
  { type: 'satellite', angle: Math.PI * 1.35 },
  { type: 'switch', angle: Math.PI * 1.55 },
  { type: 'server', angle: Math.PI * 1.75 },
  { type: 'ap', angle: Math.PI * 1.9 },
];

function OrbitingDevices({ center, radius = 6.2, height = 1.2 }: { center: [number, number, number]; radius?: number; height?: number }) {
  const ref = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.getElapsedTime();
    ref.current.children.forEach((device, i) => {
      const baseAngle = ORBIT_DEVICES[i].angle;
      const angle = baseAngle + t * 0.1;
      const r = radius + Math.sin(t * 0.25 + i * 1.5) * 0.5;
      const y = height + Math.sin(t * 0.4 + i * 0.8) * 0.35;
      device.position.set(
        center[0] + Math.cos(angle) * r,
        y,
        center[2] + Math.sin(angle) * r
      );
      device.rotation.y = -angle + Math.PI;
    });
  });
  return (
    <group ref={ref}>
      {ORBIT_DEVICES.map((d, i) => (
        <group key={i}>
          {d.type === 'router' && <MiniRouter />}
          {d.type === 'switch' && <MiniSwitch />}
          {d.type === 'satellite' && <MiniSatellite />}
          {d.type === 'server' && <MiniServer />}
          {d.type === 'ap' && <MiniAP />}
        </group>
      ))}
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   AI SCANNING BEAM (rotating cone over entire office)
   ═══════════════════════════════════════════════════ */

function AIScanBeam({ position }: { position: [number, number, number] }) {
  const ref = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.rotation.y = clock.getElapsedTime() * 0.6;
    }
  });
  return (
    <group ref={ref} position={position}>
      {/* Scan cone */}
      <mesh position={[2, -1.2, 0]} rotation={[0, 0, 0.15]}>
        <coneGeometry args={[1.2, 2.5, 4, 1, true]} />
        <meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={0.2} transparent opacity={0.03} side={THREE.DoubleSide} />
      </mesh>
      {/* Scan line on ground */}
      <mesh position={[2, -2.4, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[2.5, 0.04]} />
        <meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={1.5} transparent opacity={0.2} />
      </mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   HOLOGRAPHIC GLOBE
   ═══════════════════════════════════════════════════ */

function HoloGlobe({ position }: { position: [number, number, number] }) {
  const globeRef = useRef<THREE.Group>(null!);
  const ringRefs = useRef<THREE.Mesh[]>([]);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (globeRef.current) globeRef.current.rotation.y = t * 0.3;
    ringRefs.current.forEach((r, i) => {
      if (r) r.rotation.x = Math.PI / 3 + Math.sin(t * 0.5 + i * 1.2) * 0.2;
    });
  });
  return (
    <Float speed={1.5} rotationIntensity={0.05} floatIntensity={0.2}>
      <group position={position}>
        <group ref={globeRef}>
          {/* Wireframe sphere */}
          <mesh>
            <sphereGeometry args={[0.3, 16, 12]} />
            <meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={0.4} transparent opacity={0.08} wireframe />
          </mesh>
          {/* Latitude lines */}
          {[-0.15, 0, 0.15].map((y, i) => (
            <mesh key={i} position={[0, y, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[Math.sqrt(0.09 - y * y), 0.002, 8, 24]} />
              <meshStandardMaterial color={C.cyanGlow} emissive={C.cyanGlow} emissiveIntensity={1} transparent opacity={0.4} />
            </mesh>
          ))}
          {/* Continents (simplified dots) */}
          {Array.from({ length: 12 }).map((_, i) => {
            const phi = Math.acos(2 * (i / 12) - 1);
            const theta = i * 2.4;
            return (
              <mesh key={i} position={[Math.sin(phi) * Math.cos(theta) * 0.3, Math.cos(phi) * 0.3, Math.sin(phi) * Math.sin(theta) * 0.3]}>
                <sphereGeometry args={[0.015, 6, 6]} />
                <meshStandardMaterial color={C.tealGlow} emissive={C.teal} emissiveIntensity={2} transparent opacity={0.7} />
              </mesh>
            );
          })}
        </group>
        {/* Orbiting rings */}
        {[0, 1, 2].map(i => (
          <mesh key={i} ref={el => { if (el) ringRefs.current[i] = el; }} rotation={[Math.PI / 3, i * Math.PI / 3, 0]}>
            <torusGeometry args={[0.38 + i * 0.06, 0.002, 8, 32]} />
            <meshStandardMaterial color={[C.cyan, C.gold, C.magenta][i]} emissive={[C.cyan, C.gold, C.magenta][i]} emissiveIntensity={1.2} transparent opacity={0.4} />
          </mesh>
        ))}
        {/* Base glow */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.35, 0]}>
          <circleGeometry args={[0.35, 24]} />
          <meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={0.3} transparent opacity={0.06} />
        </mesh>
      </group>
    </Float>
  );
}

/* ═══════════════════════════════════════════════════
   ENERGY ARCS between racks
   ═══════════════════════════════════════════════════ */

function EnergyArc({ from, to, color = C.cyan }: { from: [number, number, number]; to: [number, number, number]; color?: string }) {
  const ref = useRef<THREE.Group>(null!);
  const points = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    const f = new THREE.Vector3(...from), t = new THREE.Vector3(...to);
    const mid = f.clone().lerp(t, 0.5);
    mid.y += 0.4;
    for (let i = 0; i <= 20; i++) {
      const p = i / 20;
      const a = f.clone().lerp(mid, p);
      const b = mid.clone().lerp(t, p);
      pts.push(a.clone().lerp(b, p));
    }
    return pts;
  }, [from, to]);
  const dotRef = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => {
    if (!dotRef.current) return;
    const t = (clock.getElapsedTime() * 0.8) % 1;
    const idx = Math.floor(t * (points.length - 1));
    const frac = t * (points.length - 1) - idx;
    if (idx < points.length - 1) {
      dotRef.current.position.lerpVectors(points[idx], points[idx + 1], frac);
    }
  });
  const linePoints = useMemo(() => points.map(p => [p.x, p.y, p.z] as [number, number, number]), [points]);
  return (
    <group ref={ref}>
      <Line points={linePoints} color={color} transparent opacity={0.15} lineWidth={1} />
      <mesh ref={dotRef}><sphereGeometry args={[0.018, 8, 8]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={3} /></mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   AURORA EFFECT (shimmering curtain above DC)
   ═══════════════════════════════════════════════════ */

function Aurora({ position }: { position: [number, number, number] }) {
  const ref = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => {
    if (ref.current) {
      const t = clock.getElapsedTime();
      ref.current.rotation.y = Math.sin(t * 0.15) * 0.3;
      (ref.current.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.15 + 0.08 * Math.sin(t * 0.8);
      (ref.current.material as THREE.MeshStandardMaterial).opacity = 0.03 + 0.015 * Math.sin(t * 0.6);
    }
  });
  return (
    <group position={position}>
      <mesh ref={ref}>
        <planeGeometry args={[6, 2.5, 20, 10]} />
        <meshStandardMaterial color={C.purpleSoft} emissive={C.purple} emissiveIntensity={0.15} transparent opacity={0.03} side={THREE.DoubleSide} />
      </mesh>
      {/* Secondary shimmer layer */}
      <mesh position={[0.5, 0.2, 0.3]} rotation={[0, 0.3, 0]}>
        <planeGeometry args={[5, 2, 15, 8]} />
        <meshStandardMaterial color={C.cyanSoft} emissive={C.cyan} emissiveIntensity={0.08} transparent opacity={0.02} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   FIREWALL ENERGY BARRIER
   ═══════════════════════════════════════════════════ */

function FirewallBarrier() {
  const ref = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => {
    if (ref.current) {
      const t = clock.getElapsedTime();
      (ref.current.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.2 + 0.1 * Math.sin(t * 2);
      (ref.current.material as THREE.MeshStandardMaterial).opacity = 0.04 + 0.02 * Math.sin(t * 1.5);
    }
  });
  return (
    <mesh ref={ref} position={[1.2, 0.55, 0]}>
      <planeGeometry args={[0.02, 1.1, 1, 20]} />
      <meshStandardMaterial color={C.magenta} emissive={C.magenta} emissiveIntensity={0.25} transparent opacity={0.04} side={THREE.DoubleSide} />
    </mesh>
  );
}

/* ═══════════════════════════════════════════════════
   NETWORK TOPOLOGY WEB (floating above office)
   ═══════════════════════════════════════════════════ */

function NetworkTopology({ position }: { position: [number, number, number] }) {
  const ref = useRef<THREE.Group>(null!);
  const nodePositions = useMemo(() => {
    const pts: [number, number, number][] = [];
    for (let i = 0; i < 15; i++) {
      pts.push([(Math.random() - 0.5) * 4, (Math.random() - 0.5) * 0.5, (Math.random() - 0.5) * 3]);
    }
    return pts;
  }, []);
  const edges = useMemo(() => {
    const e: [number, number][] = [];
    for (let i = 0; i < nodePositions.length; i++) {
      for (let j = i + 1; j < nodePositions.length; j++) {
        const d = new THREE.Vector3(...nodePositions[i]).distanceTo(new THREE.Vector3(...nodePositions[j]));
        if (d < 2.0 && Math.random() > 0.4) e.push([i, j]);
      }
    }
    return e;
  }, [nodePositions]);
  const colors = [C.cyan, C.teal, C.blue, C.purple, C.magenta, C.green, C.gold, C.coral, C.indigo, C.lime, C.rose, C.amber, C.cyanGlow, C.tealGlow, C.purpleGlow];
  useFrame(({ clock }) => {
    if (ref.current) ref.current.rotation.y = Math.sin(clock.getElapsedTime() * 0.1) * 0.1;
  });
  return (
    <group ref={ref} position={position}>
      {edges.map(([a, b], i) => (
        <Line key={i} points={[nodePositions[a], nodePositions[b]]} color={C.cyanSoft} transparent opacity={0.1} lineWidth={1} />
      ))}
      {nodePositions.map((pos, i) => (
        <mesh key={i} position={pos}>
          <sphereGeometry args={[0.025, 8, 8]} />
          <meshStandardMaterial color={colors[i]} emissive={colors[i]} emissiveIntensity={1.5} transparent opacity={0.7} />
        </mesh>
      ))}
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   DATA BEAM
   ═══════════════════════════════════════════════════ */

function DataBeam({ from, to, color = C.cyan, speed = 1, dots = 3 }: { from: [number, number, number]; to: [number, number, number]; color?: string; speed?: number; dots?: number }) {
  const dotsRef = useRef<THREE.Group>(null!);
  const fromV = useMemo(() => new THREE.Vector3(...from), [from]);
  const toV = useMemo(() => new THREE.Vector3(...to), [to]);
  useFrame(({ clock }) => {
    if (!dotsRef.current) return;
    const t = clock.getElapsedTime();
    dotsRef.current.children.forEach((c, i) => {
      if (c instanceof THREE.Mesh) {
        const phase = ((t * speed * 0.3) + i * (1 / dots)) % 1;
        c.position.lerpVectors(fromV, toV, phase);
        c.scale.setScalar(0.6 + 0.4 * Math.sin(t * 4 + i * 2));
        (c.material as THREE.MeshStandardMaterial).emissiveIntensity = 1.5 + Math.sin(t * 5 + i) * 0.8;
      }
    });
  });
  return (
    <group>
      <Line points={[from, to]} color={color} transparent opacity={0.22} lineWidth={1} />
      <group ref={dotsRef}>{Array.from({ length: dots }).map((_, i) => (
        <mesh key={i}><sphereGeometry args={[0.022, 8, 8]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={2} /></mesh>
      ))}</group>
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   PARTICLES
   ═══════════════════════════════════════════════════ */

function Particles({ count = 80, bounds = [10, 3.5, 7] as [number, number, number] }) {
  const meshRef = useRef<THREE.InstancedMesh>(null!);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const data = useMemo(() => Array.from({ length: count }, () => ({
    speed: { x: (Math.random() - 0.5) * 0.25, y: 0.06 + Math.random() * 0.18, z: (Math.random() - 0.5) * 0.25 },
    offset: { x: (Math.random() - 0.5) * bounds[0], y: Math.random() * bounds[1], z: (Math.random() - 0.5) * bounds[2] },
  })), [count, bounds]);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    for (let i = 0; i < count; i++) {
      const d = data[i];
      dummy.position.set(d.offset.x + Math.sin(t * d.speed.x + i) * 0.6, (d.offset.y + t * d.speed.y * 0.1) % bounds[1], d.offset.z + Math.cos(t * d.speed.z + i) * 0.6);
      dummy.scale.setScalar(0.4 + 0.6 * Math.sin(t * 1.8 + i * 0.7));
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    }
    meshRef.current.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[0.012, 6, 6]} />
      <meshStandardMaterial color={C.cyanGlow} emissive={C.cyanGlow} emissiveIntensity={2} transparent opacity={0.45} />
    </instancedMesh>
  );
}

/* ─── Scan Line ─── */
function ScanLine() {
  const ref = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.position.z = -4 + ((clock.getElapsedTime() * 0.35) % 1) * 8;
      (ref.current.material as THREE.MeshStandardMaterial).opacity = 0.1 + 0.05 * Math.sin(clock.getElapsedTime() * 3);
    }
  });
  return (
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.008, 0]}>
      <planeGeometry args={[10, 0.06]} />
      <meshStandardMaterial color={C.cyan} emissive={C.cyan} emissiveIntensity={1} transparent opacity={0.1} />
    </mesh>
  );
}

/* ═══════════════════════════════════════════════════
   MAIN SCENE
   ═══════════════════════════════════════════════════ */

function Scene() {
  const groupRef = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    // Continuous slow rotation — the office revolves!
    if (groupRef.current) groupRef.current.rotation.y = clock.getElapsedTime() * 0.06;
  });

  return (
    <group ref={groupRef} position={[0, -0.8, 0]}>
      <OfficeFloor />
      <DCFloor />
      <PerimeterGlow />
      <ScanLine />

      {/* ── Walls ── */}
      <GlassWall from={[-5, -4]} to={[-5, 4]} />
      <GlassWall from={[-5, -4]} to={[0, -4]} />
      <GlassWall from={[-5, 4]} to={[5, 4]} />
      <GlassWall from={[5, -4]} to={[5, 4]} />
      <GlassWall from={[0, -4]} to={[5, -4]} />
      <GlassWall from={[-5, 0]} to={[-2, 0]} />
      <GlassWall from={[-2, -4]} to={[-2, 0]} />
      <GlassWall from={[-5, -2]} to={[-2, -2]} />
      <GlassWall from={[-5, 2]} to={[-2.5, 2]} />
      <GlassWall from={[-2.5, 0]} to={[-2.5, 2]} />
      <GlassWall from={[1.2, -4]} to={[1.2, 4]} height={1.2} />

      {/* ── Firewall energy barrier ── */}
      <FirewallBarrier />

      {/* ── Desks ── */}
      {[
        { pos: [-0.5, 0, -2.5] as [number, number, number], rot: [0, 0, 0] as [number, number, number] },
        { pos: [0.5, 0, -2.5] as [number, number, number], rot: [0, Math.PI, 0] as [number, number, number] },
        { pos: [-0.5, 0, -1.3] as [number, number, number], rot: [0, 0, 0] as [number, number, number] },
        { pos: [0.5, 0, -1.3] as [number, number, number], rot: [0, Math.PI, 0] as [number, number, number] },
        { pos: [-0.5, 0, 1.0] as [number, number, number], rot: [0, 0, 0] as [number, number, number] },
        { pos: [0.5, 0, 1.0] as [number, number, number], rot: [0, Math.PI, 0] as [number, number, number] },
        { pos: [-0.5, 0, 2.2] as [number, number, number], rot: [0, 0, 0] as [number, number, number] },
        { pos: [0.5, 0, 2.2] as [number, number, number], rot: [0, Math.PI, 0] as [number, number, number] },
      ].map((d, i) => <OfficeDesk key={`desk-${i}`} position={d.pos} rotation={d.rot} />)}
      <OfficeDesk position={[-3.5, 0, -3]} rotation={[0, Math.PI / 2, 0]} />
      <OfficeDesk position={[-3.5, 0, -1]} rotation={[0, -Math.PI / 2, 0]} />
      <OfficeDesk position={[-4, 0, 1]} rotation={[0, Math.PI / 4, 0]} />
      <OfficeDesk position={[-3, 0, 1]} rotation={[0, -Math.PI / 4, 0]} />

      {/* ── Break room ── */}
      <RoundTable position={[-3.8, 0, 3]} />
      <RoundTable position={[-3, 0, 3.2]} />
      <CoffeeMachine position={[-4.3, 0, 2.5]} />

      {/* ── Wall screens ── */}
      <WallScreen position={[-4.96, 0.65, -1]} rotation={[0, Math.PI / 2, 0]} color={C.blue} />
      <WallScreen position={[-4.96, 0.65, 3.2]} rotation={[0, Math.PI / 2, 0]} color={C.teal} />
      <WallScreen position={[0.5, 0.65, -3.96]} rotation={[0, 0, 0]} color={C.indigo} />
      <WallScreen position={[4.96, 0.7, -2.5]} rotation={[0, -Math.PI / 2, 0]} color={C.cyan} />
      <WallScreen position={[4.96, 0.7, 1.5]} rotation={[0, -Math.PI / 2, 0]} color={C.purple} />

      {/* ── Server Racks ── */}
      {[
        [2.0, 0, -2.8], [2.8, 0, -2.8], [3.6, 0, -2.8], [4.4, 0, -2.8],
        [2.0, 0, -1.3], [2.8, 0, -1.3], [3.6, 0, -1.3], [4.4, 0, -1.3],
        [2.0, 0, 0.2], [2.8, 0, 0.2], [3.6, 0, 0.2], [4.4, 0, 0.2],
        [2.0, 0, 1.7], [2.8, 0, 1.7], [3.6, 0, 1.7], [4.4, 0, 1.7],
      ].map((p, i) => <ServerRack key={`rack-${i}`} position={p as [number, number, number]} scale={0.85} />)}

      {/* ── Network Equipment ── */}
      <Router position={[-4.5, 0.82, -3.5]} />
      <Router position={[-4.5, 0.82, -0.5]} rotation={[0, Math.PI / 4, 0]} />
      <Router position={[-4.5, 0.82, 3.5]} />
      <Router position={[0.5, 0.82, -3.8]} rotation={[0, -0.2, 0]} />
      <Firewall position={[1.2, 0, -3.2]} />
      <Firewall position={[1.2, 0, 0.0]} />
      <Firewall position={[1.2, 0, 3.0]} />
      <NetSwitch position={[2.5, 0, -3.5]} />
      <NetSwitch position={[4, 0, -3.5]} />
      <NetSwitch position={[2.5, 0, 3.0]} />
      <NetSwitch position={[4, 0, 3.0]} />

      {/* ── Access Points ── */}
      <AccessPoint position={[-3.5, 1.15, -1]} />
      <AccessPoint position={[-3.5, 1.15, 3]} />
      <AccessPoint position={[0, 1.15, -0.5]} />
      <AccessPoint position={[0, 1.15, 2.5]} />
      <AccessPoint position={[3, 1.15, -0.2]} />
      <AccessPoint position={[3, 1.15, 2.5]} />

      {/* ── Cell Towers ── */}
      <CellTower position={[3.5, 1.6, -1]} />
      <CellTower position={[2.0, 1.6, 2.5]} />

      {/* ── Shield Dome with pulse waves ── */}
      <ShieldDome position={[3.2, 0, -0.3]} radius={3.2} />

      {/* ── Shield Icons ── */}
      <ShieldIcon position={[-3.5, 1.8, -3.2]} />
      <ShieldIcon position={[1.2, 1.6, 0]} />

      {/* ── AI Brain ── */}
      <AIBrain position={[3.2, 2.6, -0.3]} />

      {/* ── Holographic Globe ── */}
      <HoloGlobe position={[-3.5, 2.0, 1]} />

      {/* ── AI Scanning Beam ── */}
      <AIScanBeam position={[3.2, 3.0, -0.3]} />

      {/* ── Orbiting Hex Shields ── */}

      {/* ── Orbit trail rings (elliptical paths) ── */}
      {[5.8, 6.2, 6.6].map((r, i) => (
        <mesh key={`orbit-${i}`} rotation={[-Math.PI / 2, 0, 0]} position={[0, 1.0 + i * 0.3, 0]}>
          <torusGeometry args={[r, 0.006, 8, 80]} />
          <meshStandardMaterial color="#c0c0c0" transparent opacity={0.12 - i * 0.03} />
        </mesh>
      ))}

      {/* ── Orbiting Devices (routers, switches, satellites, servers, APs) ── */}
      <OrbitingDevices center={[0, 0, 0]} radius={6.2} height={1.2} />

      {/* ── Network Topology Web ── */}
      <NetworkTopology position={[-1, 2.0, 0]} />

      {/* ── Holographic Panels ── */}
      <HoloPanel position={[1.8, 1.9, -3.5]} rotation={[0, 0.3, 0]} color={C.cyan} />
      <HoloPanel position={[4.5, 1.9, -0.5]} rotation={[0, -0.8, 0]} color={C.purple} />
      <HoloPanel position={[-1.5, 1.6, -3.5]} rotation={[0, 0.2, 0]} color={C.teal} />
      <HoloPanel position={[-4.8, 1.6, 0.5]} rotation={[0, 0.8, 0]} color={C.gold} />

      {/* ── Aurora Effect ── */}
      <Aurora position={[3.2, 3.5, -0.3]} />

      {/* ── Data Waterfall ── */}
      <DataWaterfall position={[3.1, 0, 0]} color={C.cyan} count={30} />
      <DataWaterfall position={[3.1, 0, 0]} color={C.purple} count={15} />

      {/* ── Particles ── */}
      <Particles count={80} bounds={[10, 3.5, 7]} />

      {/* ── Data Beams ── */}
      <DataBeam from={[-3.5, 0.5, -1]} to={[0, 0.5, -2]} color={C.cyanSoft} speed={0.7} dots={2} />
      <DataBeam from={[-3.5, 0.5, 3]} to={[0, 0.5, 1.5]} color={C.tealGlow} speed={0.6} dots={2} />
      <DataBeam from={[0, 0.5, -2]} to={[1.2, 0.4, -3.2]} color={C.cyanGlow} speed={0.9} dots={3} />
      <DataBeam from={[0, 0.5, 1.5]} to={[1.2, 0.4, 0]} color={C.cyanGlow} speed={1.0} dots={3} />
      <DataBeam from={[1.2, 0.4, -3.2]} to={[3, 0.8, -2.8]} color={C.cyan} speed={1.2} dots={3} />
      <DataBeam from={[1.2, 0.4, 0]} to={[3, 0.8, 0.2]} color={C.cyan} speed={0.9} dots={3} />
      <DataBeam from={[1.2, 0.4, 3.0]} to={[3, 0.8, 1.7]} color={C.cyan} speed={1.0} dots={3} />
      <DataBeam from={[3.2, 2.2, -0.3]} to={[3, 0.8, -2.8]} color={C.purple} speed={1.4} dots={2} />
      <DataBeam from={[3.2, 2.2, -0.3]} to={[3, 0.8, 1.7]} color={C.purpleGlow} speed={1.2} dots={2} />
      <DataBeam from={[3.2, 2.2, -0.3]} to={[3, 0.8, 0.2]} color={C.indigo} speed={1.0} dots={2} />
      <DataBeam from={[3, 0.8, -2.8]} to={[4.4, 0.8, -2.8]} color={C.cyan} speed={1.5} dots={2} />
      <DataBeam from={[2.0, 0.8, 0.2]} to={[4.4, 0.8, 0.2]} color={C.teal} speed={1.3} dots={2} />
      <DataBeam from={[2.0, 0.8, -2.8]} to={[2.0, 0.8, 1.7]} color={C.blue} speed={0.5} dots={4} />
      <DataBeam from={[4.4, 0.8, -2.8]} to={[4.4, 0.8, 1.7]} color={C.blue} speed={0.6} dots={4} />
      <DataBeam from={[-4.5, 0.85, -3.5]} to={[0, 0.5, -2]} color={C.magentaGlow} speed={0.4} dots={2} />
      <DataBeam from={[-4.5, 0.85, 3.5]} to={[0, 0.5, 1.5]} color={C.coralGlow} speed={0.5} dots={2} />
      <DataBeam from={[-3.5, 2.0, 1]} to={[0, 1.15, -0.5]} color={C.gold} speed={0.6} dots={2} />
      <DataBeam from={[3.2, 2.6, -0.3]} to={[-3.5, 2.0, 1]} color={C.goldGlow} speed={0.3} dots={3} />

      {/* ── Energy Arcs ── */}
      <EnergyArc from={[2.0, 1.36, -2.8]} to={[2.8, 1.36, -2.8]} color={C.cyan} />
      <EnergyArc from={[2.8, 1.36, -2.8]} to={[3.6, 1.36, -2.8]} color={C.teal} />
      <EnergyArc from={[3.6, 1.36, -2.8]} to={[4.4, 1.36, -2.8]} color={C.blue} />
      <EnergyArc from={[2.0, 1.36, 0.2]} to={[2.8, 1.36, 0.2]} color={C.purple} />
      <EnergyArc from={[2.8, 1.36, 0.2]} to={[3.6, 1.36, 0.2]} color={C.indigo} />
      <EnergyArc from={[3.6, 1.36, 0.2]} to={[4.4, 1.36, 0.2]} color={C.cyan} />
      <EnergyArc from={[2.0, 1.36, 1.7]} to={[4.4, 1.36, 1.7]} color={C.magenta} />
      <EnergyArc from={[2.0, 1.36, -1.3]} to={[4.4, 1.36, -1.3]} color={C.gold} />
    </group>
  );
}

/* ═══════════════════════════════════════════════════
   CANVAS
   ═══════════════════════════════════════════════════ */

export default function NetworkScene3D() {
  return (
    <div style={{ width: '100%', height: '100%', minHeight: 340 }}>
      <Canvas
        camera={{ position: [9, 7.5, 9], fov: 34 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true }}
        style={{ background: '#ffffff' }}
      >
        <ambientLight intensity={1.0} color="#ffffff" />
        <directionalLight position={[8, 14, 6]} intensity={1.8} color="#ffffff" />
        <directionalLight position={[-6, 10, -4]} intensity={0.7} color="#fff8f0" />
        <directionalLight position={[0, 12, 0]} intensity={0.4} color="#ffffff" />
        <pointLight position={[-3.5, 2, -1]} intensity={0.6} color={C.warmGlow} distance={8} />
        <pointLight position={[-3.5, 2, 3]} intensity={0.6} color={C.warmGlow} distance={8} />
        <pointLight position={[0, 2, 0]} intensity={0.5} color={C.warmGlow} distance={10} />
        <pointLight position={[3, 2.5, -1]} intensity={0.8} color={C.cyan} distance={8} />
        <pointLight position={[3, 2.5, 1.5]} intensity={0.7} color={C.cyan} distance={8} />
        <pointLight position={[3.2, 4, 0]} intensity={0.5} color={C.purple} distance={12} />
        <pointLight position={[0, 0.5, -4]} intensity={0.35} color={C.magenta} distance={6} />
        <pointLight position={[0, 0.5, 4]} intensity={0.35} color={C.magenta} distance={6} />
        <pointLight position={[-5, 0.5, 0]} intensity={0.2} color={C.magenta} distance={5} />
        <pointLight position={[5, 0.5, 0]} intensity={0.2} color={C.magenta} distance={5} />
        <pointLight position={[-3.5, 2.5, 1]} intensity={0.3} color={C.teal} distance={6} />

        <Scene />

        <OrbitControls
          enableZoom={false}
          enablePan={false}
          minPolarAngle={Math.PI / 5}
          maxPolarAngle={Math.PI / 3}
          autoRotate={false}
        />
      </Canvas>
    </div>
  );
}
