"use client";

// The 3D Organization Sphere — concentric shells (company core → departments → AI agents →
// people) you orbit with drag and zoom with scroll/pinch. Node positions come from the pure,
// tested layout in lib/orgSphereLayout; this file is the WebGL presentation only.
//
// Premium look is achieved WITHOUT a postprocessing/bloom pass (its SMAA path can spawn a worker
// the dashboard CSP blocks, and fullscreen bloom is too heavy at 2,000 nodes on a phone). Instead:
//   - additive, brightened "emissive-look" node materials so dense clusters glow for free,
//   - a GLSL fresnel atmosphere shell + an additive starfield + exponential fog for depth,
//   - all motion (intro reveal, idle pulse, selection ring) mutated imperatively in useFrame —
//     never via per-frame React state (the #1 rule for 2,000 instances on mobile).
//
// Performance posture: one InstancedMesh for all people (one draw call), per-instance color
// recomputed only on selection/search change, bounded labels, dpr capped, reduced-motion gated.

import { useEffect, useMemo, useRef, useState } from "react";

import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
// Import ONLY non-troika drei exports. drei's <Text>/<Billboard text> spawn a troika SDF web worker
// via a blob: URL, which this dashboard's CSP (worker-src falls back to 'self') BLOCKS. For text use
// the canvas-texture LabelSprite below, never drei <Text>.
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";

import type { OrgOverview } from "@/lib/types";
import { computeFocus, type OrgFocus } from "@/lib/orgFocus";
import { buildOrgSphereLayout, R_PEOPLE, type Vec3 } from "@/lib/orgSphereLayout";

type Props = {
  data: OrgOverview;
  selectedPersonId: string | null;
  selectedAgentKey: string | null;
  selectedDeptKey: string | null;
  query: string;
  motionOK: boolean;
  onSelectPerson: (id: string) => void;
  onSelectAgent: (key: string) => void;
  onSelectDept: (key: string) => void;
  onClearSelection: () => void;
};

const PERSON_R = 0.13;
const LEAD_R = 0.21;
const PEOPLE_BRIGHT = 1.5; // emissive-look: color pushed > 1 with toneMapped off + additive blending
const OUT_OF_FOCUS = 0.1; // how dark a non-spotlighted node/edge/label goes
const LABEL_DIM = 0.16;
const PEOPLE_EDGE_LIMIT = 450; // above this, dept→person edges become a hairball — suppress them
const SEARCH_LABEL_CAP = 40;
const INTRO_DUR = 1.15; // seconds
const FOG_COLOR = "#080a12";
const FOG_FINAL = 0.015; // constant — gentle depth cue; far nodes melt into the backdrop
const STAR_COUNT = 700;

// ---- canvas-texture label sprites (no troika/worker; CSP-safe) ----

let measureCtx: CanvasRenderingContext2D | null = null;
function measureText(text: string, font: string): number {
  if (!measureCtx) measureCtx = document.createElement("canvas").getContext("2d");
  if (!measureCtx) return text.length * 14;
  measureCtx.font = font;
  return measureCtx.measureText(text).width;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function makeLabelTexture(text: string, color: string): { texture: THREE.CanvasTexture; aspect: number } {
  const dpr = typeof window !== "undefined" ? Math.min(window.devicePixelRatio || 1, 2) : 1;
  const font = `600 26px ui-sans-serif, system-ui, -apple-system, sans-serif`;
  const padX = 12;
  const textW = Math.ceil(measureText(text, font));
  const w = textW + padX * 2;
  const h = 40;
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(w * dpr);
  canvas.height = Math.ceil(h * dpr);
  const ctx = canvas.getContext("2d")!;
  ctx.scale(dpr, dpr);
  ctx.font = font;
  ctx.fillStyle = "rgba(8,10,18,0.74)";
  roundRect(ctx, 0, 0, w, h, 9);
  ctx.fill();
  ctx.strokeStyle = `${color}66`;
  ctx.lineWidth = 1;
  roundRect(ctx, 0.5, 0.5, w - 1, h - 1, 9);
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.textBaseline = "middle";
  ctx.fillText(text, padX, h / 2 + 1);
  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  texture.colorSpace = THREE.SRGBColorSpace;
  return { texture, aspect: w / h };
}

function LabelSprite({
  position,
  text,
  color,
  size = 0.62,
  yOffset = 0.34,
  dim = 1,
}: {
  position: Vec3;
  text: string;
  color: string;
  size?: number;
  yOffset?: number;
  dim?: number;
}) {
  const { texture, aspect } = useMemo(() => makeLabelTexture(text, color), [text, color]);
  useEffect(() => () => texture.dispose(), [texture]);
  return (
    // raycast disabled so labels never intercept clicks meant for the nodes behind them.
    <sprite position={[position[0], position[1] + yOffset, position[2]]} scale={[size * aspect, size, 1]} raycast={() => null}>
      <spriteMaterial map={texture} transparent opacity={dim} depthTest={false} depthWrite={false} toneMapped={false} />
    </sprite>
  );
}

// ---- atmosphere: a back-side fresnel shell so the globe reads with a soft rim glow ----

// Fresnel via the VIEW-SPACE normal — its z component points at the camera, so the rim (where z→0)
// glows. This needs only built-ins three injects into every ShaderMaterial vertex stage
// (normalMatrix / modelViewMatrix); crucially it avoids `cameraPosition`, which three does NOT
// declare in the fragment stage (using it there is a GLSL compile error).
const FRESNEL_VERT = /* glsl */ `
  varying vec3 vNormalView;
  void main() {
    vNormalView = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }`;
const FRESNEL_FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform float uIntensity;
  varying vec3 vNormalView;
  void main() {
    float fres = pow(1.0 - abs(vNormalView.z), 3.0);
    gl_FragColor = vec4(uColor * uIntensity * fres, fres);
  }`;

function Atmosphere() {
  const uniforms = useMemo(
    () => ({ uColor: { value: new THREE.Color("#3f74ff") }, uIntensity: { value: 1.15 } }),
    [],
  );
  return (
    <mesh raycast={() => null} scale={R_PEOPLE + 1.6}>
      <icosahedronGeometry args={[1, 5]} />
      <shaderMaterial
        side={THREE.BackSide}
        transparent
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        uniforms={uniforms}
        vertexShader={FRESNEL_VERT}
        fragmentShader={FRESNEL_FRAG}
      />
    </mesh>
  );
}

// ---- starfield: faint additive points for parallax depth ----

function Starfield() {
  const positions = useMemo(() => {
    const arr = new Float32Array(STAR_COUNT * 3);
    // Deterministic-enough scatter on a far shell; Math.random is fine here (visual only, app code).
    for (let i = 0; i < STAR_COUNT; i++) {
      const r = 16 + Math.random() * 26;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      arr[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      arr[i * 3 + 1] = r * Math.cos(phi);
      arr[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
    }
    return arr;
  }, []);
  return (
    <points raycast={() => null} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={positions} count={STAR_COUNT} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial
        color="#9fb4e8"
        size={0.07}
        sizeAttenuation
        transparent
        opacity={0.6}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </points>
  );
}

// A merged line set. frustumCulled off so a changing bufferAttribute can't compute a stale bounding
// sphere and vanish; it's one cheap draw call.
function Edges({ data, opacity }: { data: { position: Float32Array; color: Float32Array }; opacity: number }) {
  if (data.position.length === 0) return null;
  return (
    <lineSegments frustumCulled={false} raycast={() => null}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={data.position} count={data.position.length / 3} itemSize={3} />
        <bufferAttribute attach="attributes-color" array={data.color} count={data.color.length / 3} itemSize={3} />
      </bufferGeometry>
      <lineBasicMaterial vertexColors transparent opacity={opacity} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
    </lineSegments>
  );
}

// ---- guards + per-frame driver ----

function ContextGuard({ onLost }: { onLost: () => void }) {
  const gl = useThree((s) => s.gl);
  useEffect(() => {
    const canvas = gl.domElement;
    const handler = (e: Event) => {
      e.preventDefault();
      onLost();
    };
    canvas.addEventListener("webglcontextlost", handler as EventListener, false);
    return () => canvas.removeEventListener("webglcontextlost", handler as EventListener);
  }, [gl, onLost]);
  return null;
}

// Drives all motion imperatively (no React state per frame): a cosmetic intro scale-in, a gentle
// company-core breathe, and the pulsing selection ring positioned at the active node. Visibility
// never depends on this loop (fog is constant), so a stalled frame can't hide the scene.
function SceneFx({
  motionOK,
  groupRef,
  coreRef,
  ringRef,
  ringPosRef,
}: {
  motionOK: boolean;
  groupRef: React.RefObject<THREE.Group>;
  coreRef: React.RefObject<THREE.Group>;
  ringRef: React.RefObject<THREE.Mesh>;
  ringPosRef: React.MutableRefObject<Vec3 | null>;
}) {
  const intro = useRef(motionOK ? 0 : 1);
  useFrame((state, delta) => {
    if (intro.current < 1) {
      intro.current = Math.min(1, intro.current + delta / INTRO_DUR);
      const e = 1 - Math.pow(1 - intro.current, 3); // expo-out
      if (groupRef.current) groupRef.current.scale.setScalar(0.94 + 0.06 * e);
    }
    const t = state.clock.elapsedTime;
    if (motionOK && coreRef.current) coreRef.current.scale.setScalar(1 + Math.sin(t * 1.4) * 0.045);
    const ring = ringRef.current;
    if (ring) {
      const p = ringPosRef.current;
      if (p) {
        ring.visible = true;
        ring.position.set(p[0], p[1], p[2]);
        ring.scale.setScalar(0.42 + (motionOK ? (Math.sin(t * 4) + 1) * 0.05 : 0.05));
        (ring.material as THREE.Material).opacity = motionOK ? 0.5 + Math.sin(t * 4) * 0.2 : 0.7;
      } else {
        ring.visible = false;
      }
    }
  });
  return null;
}

// ---- the scene graph (inside <Canvas>) ----

function Scene({
  data,
  selectedPersonId,
  selectedAgentKey,
  selectedDeptKey,
  query,
  motionOK,
  onSelectPerson,
  onSelectAgent,
  onSelectDept,
  rotate,
}: Omit<Props, "onClearSelection"> & { rotate: boolean }) {
  const layout = useMemo(
    () =>
      buildOrgSphereLayout({
        company: data.company,
        departments: data.departments,
        people: data.people,
        agents: data.agents,
      }),
    [data],
  );

  const meshRef = useRef<THREE.InstancedMesh>(null);
  const groupRef = useRef<THREE.Group>(null);
  const coreRef = useRef<THREE.Group>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const ringPosRef = useRef<Vec3 | null>(null);
  const downPos = useRef<{ x: number; y: number } | null>(null);
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const personIndexById = useMemo(() => {
    const m = new Map<string, number>();
    layout.people.forEach((p, i) => m.set(p.id, i));
    return m;
  }, [layout]);

  const deptPosByKey = useMemo(() => {
    const m = new Map<string, Vec3>();
    for (const d of layout.departments) m.set(d.key, d.position);
    return m;
  }, [layout]);

  // Connected highlight set — shared with the 2D wheel via lib/orgFocus so the views never drift.
  const focus: OrgFocus = useMemo(
    () => computeFocus(data, { personId: selectedPersonId, agentKey: selectedAgentKey, deptKey: selectedDeptKey }),
    [data, selectedPersonId, selectedAgentKey, selectedDeptKey],
  );
  const focusSig = selectedPersonId ?? selectedAgentKey ?? selectedDeptKey ?? "none";

  const q = query.trim().toLowerCase();
  const personActive = useMemo(() => {
    return (id: string, name: string, title: string): boolean => {
      if (focus) return focus.people.has(id);
      if (q) return name.toLowerCase().includes(q) || title.toLowerCase().includes(q);
      return true;
    };
  }, [focus, q]);

  const deptActive = (key: string) => !focus || focus.depts.has(key);
  const agentActive = (key: string) => !focus || focus.agents.has(key);

  // Instance transforms — set once per layout.
  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const dummy = new THREE.Object3D();
    layout.people.forEach((p, i) => {
      dummy.position.set(p.position[0], p.position[1], p.position[2]);
      dummy.scale.setScalar(p.lead ? LEAD_R : PERSON_R);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
    mesh.count = layout.people.length;
    // Origin-centered bounds (every person sits on R_PEOPLE per the layout invariant) so frustum
    // culling + the raycast broad-phase reject work without a per-instance bbox recompute.
    mesh.geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), R_PEOPLE + LEAD_R + 0.5);
  }, [layout]);

  // Instance colors — recomputed only when layout/selection/search changes (never per frame).
  // Brightened (> 1) for the additive emissive glow; dimmed hard when out of the spotlight.
  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const base = new THREE.Color();
    layout.people.forEach((p, i) => {
      base.set(p.color).multiplyScalar(personActive(p.id, p.name, p.title) ? PEOPLE_BRIGHT : OUT_OF_FOCUS);
      mesh.setColorAt(i, base);
    });
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [layout, personActive]);

  // ---- edges (focus-dimmed: spotlight bakes into the per-edge color) ----
  const companyEdges = useMemo(() => {
    const pos: number[] = [];
    const col: number[] = [];
    const c = new THREE.Color();
    for (const d of layout.departments) {
      c.set(d.color).multiplyScalar(deptActive(d.key) ? 1 : OUT_OF_FOCUS);
      pos.push(0, 0, 0, d.position[0], d.position[1], d.position[2]);
      col.push(c.r, c.g, c.b, c.r, c.g, c.b);
    }
    return { position: new Float32Array(pos), color: new Float32Array(col) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, focusSig]);

  const showPeopleEdges = layout.people.length <= PEOPLE_EDGE_LIMIT;
  const peopleEdges = useMemo(() => {
    if (!showPeopleEdges) return { position: new Float32Array(0), color: new Float32Array(0) };
    const pos: number[] = [];
    const col: number[] = [];
    const c = new THREE.Color();
    for (const p of layout.people) {
      const hub = deptPosByKey.get(p.departmentKey);
      if (!hub) continue;
      const on = !focus || focus.people.has(p.id);
      c.set(p.color).multiplyScalar(on ? 1 : OUT_OF_FOCUS);
      pos.push(hub[0], hub[1], hub[2], p.position[0], p.position[1], p.position[2]);
      col.push(c.r, c.g, c.b, c.r, c.g, c.b);
    }
    return { position: new Float32Array(pos), color: new Float32Array(col) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, deptPosByKey, showPeopleEdges, focusSig]);

  const agentEdges = useMemo(() => {
    const pos: number[] = [];
    const col: number[] = [];
    const c = new THREE.Color();
    for (const a of layout.agents) {
      c.set(a.color).multiplyScalar(agentActive(a.key) ? 1 : OUT_OF_FOCUS);
      for (const key of a.servesKeys) {
        const hub = deptPosByKey.get(key);
        if (!hub) continue;
        pos.push(a.position[0], a.position[1], a.position[2], hub[0], hub[1], hub[2]);
        col.push(c.r, c.g, c.b, c.r, c.g, c.b);
      }
    }
    return { position: new Float32Array(pos), color: new Float32Array(col) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, deptPosByKey, focusSig]);

  const hoveredPerson = hoveredIdx != null ? layout.people[hoveredIdx] : null;
  const selectedPerson =
    selectedPersonId != null ? layout.people[personIndexById.get(selectedPersonId) ?? -1] ?? null : null;

  // Position the pulsing selection ring at whatever is selected (person / dept / agent).
  const selectedPos: Vec3 | null = useMemo(() => {
    if (selectedPerson) return selectedPerson.position;
    if (selectedDeptKey) return layout.departments.find((d) => d.key === selectedDeptKey)?.position ?? null;
    if (selectedAgentKey) return layout.agents.find((a) => a.key === selectedAgentKey)?.position ?? null;
    return null;
  }, [selectedPerson, selectedDeptKey, selectedAgentKey, layout]);
  useEffect(() => {
    ringPosRef.current = selectedPos;
  }, [selectedPos]);

  const onDown = (e: ThreeEvent<PointerEvent>) => {
    downPos.current = { x: e.nativeEvent.clientX, y: e.nativeEvent.clientY };
  };
  const onMove = (e: ThreeEvent<PointerEvent>) => {
    if (e.instanceId == null) return;
    if (e.nativeEvent.pointerType === "touch") return; // touch has no hover — skip the per-move raycast
    e.stopPropagation();
    if (e.instanceId !== hoveredIdx) setHoveredIdx(e.instanceId);
  };
  const onOut = () => setHoveredIdx(null);
  const onClick = (e: ThreeEvent<MouseEvent>) => {
    if (e.instanceId == null) return;
    e.stopPropagation();
    const d = downPos.current;
    if (d) {
      const dx = e.nativeEvent.clientX - d.x;
      const dy = e.nativeEvent.clientY - d.y;
      if (dx * dx + dy * dy > 36) return; // moved > 6px → it was a drag, not a click
    }
    const p = layout.people[e.instanceId];
    if (p) onSelectPerson(p.id);
  };

  return (
    <>
      <fogExp2 attach="fog" args={[FOG_COLOR, FOG_FINAL]} />
      <OrbitControls
        makeDefault
        enablePan={false}
        enableDamping={motionOK}
        dampingFactor={0.08}
        rotateSpeed={0.6}
        zoomSpeed={0.85}
        minDistance={10.5}
        maxDistance={48}
        minPolarAngle={0.18}
        maxPolarAngle={Math.PI - 0.18}
        autoRotate={rotate}
        autoRotateSpeed={0.4}
      />
      <SceneFx motionOK={motionOK} groupRef={groupRef} coreRef={coreRef} ringRef={ringRef} ringPosRef={ringPosRef} />

      <Starfield />

      <group ref={groupRef}>
        <Atmosphere />

        {/* company → dept spokes (always) · dept → person (gated at scale) · agent → dept */}
        <Edges key={`ce-${focusSig}-${companyEdges.position.length}`} data={companyEdges} opacity={0.55} />
        <Edges key={`pe-${focusSig}-${peopleEdges.position.length}`} data={peopleEdges} opacity={0.22} />
        <Edges key={`ae-${focusSig}-${agentEdges.position.length}`} data={agentEdges} opacity={0.6} />

        {/* company core (glowing, breathing) */}
        <group ref={coreRef}>
          <mesh raycast={() => null}>
            <icosahedronGeometry args={[0.82, 3]} />
            <meshBasicMaterial color="#9cc0ff" transparent opacity={0.95} toneMapped={false} />
          </mesh>
          <mesh raycast={() => null} scale={2.1}>
            <icosahedronGeometry args={[0.82, 2]} />
            <meshBasicMaterial color="#3f74ff" transparent opacity={0.22} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
          </mesh>
        </group>

        {/* department hubs + glow halos */}
        {layout.departments.map((d) => {
          const on = deptActive(d.key);
          return (
            <group key={`hub-${d.key}`} position={[d.position[0], d.position[1], d.position[2]]}>
              <mesh
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectDept(d.key);
                }}
              >
                <icosahedronGeometry args={[0.4, 2]} />
                <meshBasicMaterial color={d.color} transparent opacity={(on ? 1 : OUT_OF_FOCUS) * 0.98} toneMapped={false} />
              </mesh>
              <mesh raycast={() => null} scale={2.3}>
                <icosahedronGeometry args={[0.4, 1]} />
                <meshBasicMaterial color={d.color} transparent opacity={(on ? 0.28 : 0.03)} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
              </mesh>
            </group>
          );
        })}

        {/* AI agent nodes */}
        {layout.agents.map((a) => {
          const on = agentActive(a.key);
          return (
            <mesh
              key={`agent-${a.key}`}
              position={[a.position[0], a.position[1], a.position[2]]}
              onClick={(e) => {
                e.stopPropagation();
                onSelectAgent(a.key);
              }}
            >
              <octahedronGeometry args={[0.3, 0]} />
              <meshBasicMaterial color={a.color} wireframe transparent opacity={(on ? 1 : OUT_OF_FOCUS) * 0.95} toneMapped={false} />
            </mesh>
          );
        })}

        {/* people — one instanced draw call, additive emissive glow */}
        <instancedMesh
          ref={meshRef}
          // geometry + material come from the children; only the instance count is needed here.
          // (cast bridges a known @react-three/fiber typing gap for the args tuple)
          args={[undefined, undefined, Math.max(layout.people.length, 1)] as unknown as [THREE.BufferGeometry, THREE.Material, number]}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerOut={onOut}
          onClick={onClick}
        >
          <icosahedronGeometry args={[1, 1]} />
          <meshBasicMaterial transparent opacity={0.95} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </instancedMesh>

        {/* hover highlight + the pulsing selection ring (positioned/animated in SceneFx) */}
        {hoveredPerson && (
          <mesh raycast={() => null} position={[hoveredPerson.position[0], hoveredPerson.position[1], hoveredPerson.position[2]]}>
            <icosahedronGeometry args={[0.3, 1]} />
            <meshBasicMaterial color={hoveredPerson.color} wireframe transparent opacity={0.9} toneMapped={false} />
          </mesh>
        )}
        <mesh ref={ringRef} raycast={() => null} visible={false}>
          <icosahedronGeometry args={[1, 1]} />
          <meshBasicMaterial color="#ffffff" wireframe transparent opacity={0.7} depthWrite={false} toneMapped={false} />
        </mesh>

        {/* labels — bounded set: company, departments, agents, leads, + hovered/selected/search */}
        <LabelSprite position={[0, 0, 0]} text={data.company.name} color="#dce6ff" size={0.82} yOffset={1.1} />
        {layout.departments.map((d) => (
          <LabelSprite key={`dl-${d.key}`} text={`${d.name} · ${d.headCount}`} color={d.color} position={d.position} size={0.66} yOffset={0.62} dim={deptActive(d.key) ? 1 : LABEL_DIM} />
        ))}
        {layout.agents.map((a) => (
          <LabelSprite key={`al-${a.key}`} text={a.label} color={a.color} position={a.position} size={0.5} yOffset={0.42} dim={agentActive(a.key) ? 1 : LABEL_DIM} />
        ))}
        {layout.people
          .filter((p) => p.lead)
          .map((p) => (
            <LabelSprite key={`ll-${p.id}`} text={p.name} color={p.color} position={p.position} size={0.5} yOffset={0.34} dim={!focus || focus.people.has(p.id) ? 1 : LABEL_DIM} />
          ))}
        {hoveredPerson && !hoveredPerson.lead && (
          <LabelSprite text={hoveredPerson.name} color={hoveredPerson.color} position={hoveredPerson.position} size={0.54} yOffset={0.34} />
        )}
        {selectedPerson && !selectedPerson.lead && (
          <LabelSprite text={selectedPerson.name} color="#ffffff" position={selectedPerson.position} size={0.54} yOffset={0.34} />
        )}
        {q &&
          layout.people
            .filter((p) => !p.lead && (p.name.toLowerCase().includes(q) || p.title.toLowerCase().includes(q)))
            .slice(0, SEARCH_LABEL_CAP)
            .map((p) => <LabelSprite key={`ql-${p.id}`} text={p.name} color={p.color} position={p.position} size={0.5} yOffset={0.34} />)}
      </group>
    </>
  );
}

export default function OrgSphere(props: Props) {
  const [contextLost, setContextLost] = useState(false);
  const [rotate, setRotate] = useState(false); // explicit still / auto-rotate toggle (default still)

  // r3f v8 sometimes measures its container as 0 on mount (react-use-measure / ResizeObserver timing)
  // and then NEVER starts its render loop, leaving a blank canvas. A one-time resize nudge on the next
  // frame forces a re-measure so the loop starts. Harmless if the size was already correct.
  useEffect(() => {
    const id = requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <div className="relative h-full w-full" style={{ touchAction: "none" }}>
      <Canvas
        frameloop={props.motionOK || rotate ? "always" : "demand"}
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
        camera={{ position: [0, 5.5, 24], fov: 50, near: 0.1, far: 200 }}
        onPointerMissed={() => props.onClearSelection()}
        // Opaque dark clear (alpha 1) so additive-blended node glow sums against a backdrop instead
        // of compositing to nothing over a transparent canvas.
        onCreated={({ gl }) => gl.setClearColor(FOG_COLOR, 1)}
        style={{ touchAction: "none" }}
      >
        <ContextGuard onLost={() => setContextLost(true)} />
        <Scene {...props} rotate={rotate} />
      </Canvas>

      <button
        onClick={() => setRotate((r) => !r)}
        title={rotate ? "Stop auto-rotation" : "Start auto-rotation"}
        className="absolute bottom-3 left-3 z-10 inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-ink-900/80 px-2.5 py-1.5 text-xs font-medium text-zinc-300 backdrop-blur transition hover:text-white"
      >
        <span aria-hidden>{rotate ? "⏸" : "⟳"}</span>
        {rotate ? "Rotating" : "Rotate"}
      </button>

      {contextLost && (
        <div className="absolute inset-0 grid place-items-center bg-ink-900/60 text-sm text-zinc-300">
          3D view lost the graphics context. Switch to Classic 2D, or reload to restore it.
        </div>
      )}
    </div>
  );
}
