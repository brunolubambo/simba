import * as THREE from "three";
import { COLORS } from "./sphere.js";

const TAU = Math.PI * 2;
export const PLATFORM_R = 2.0;
const PLANE = PLATFORM_R * 2.08;
const col = (hex, k = 1) => new THREE.Color(hex).multiplyScalar(k);
const rng = seed => () => (seed = (seed * 16807) % 2147483647) / 2147483647;

function ringTexture(size, draw) {
  const c = document.createElement("canvas"); c.width = c.height = size;
  const g = c.getContext("2d");
  g.translate(size / 2, size / 2);
  g.strokeStyle = g.fillStyle = "#fff";
  draw(g, size / PLANE);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}
function band(g, r0, r1, a0, a1) {
  g.beginPath(); g.arc(0, 0, r1, a0, a1); g.arc(0, 0, r0, a1, a0, true); g.closePath(); g.fill();
}
function circle(g, r, width, alpha) {
  g.globalAlpha = alpha; g.lineWidth = width; g.beginPath(); g.arc(0, 0, r, 0, TAU); g.stroke();
}

// Camadas de fora para dentro. speed em rad/s; sentidos alternados.
const LAYERS = [
  { name: "ticks", speed: 0.022, tint: col(COLORS.cyan, 1.1), draw(g, k) {
    circle(g, 1.86 * k, 1.5, 0.35);
    for (let i = 0; i < 120; i++) {
      const a = i / 120 * TAU, major = i % 10 === 0, long = i % 2 === 0;
      g.globalAlpha = major ? 1 : long ? 0.7 : 0.38;
      g.lineWidth = major ? 3 : 2;
      const r0 = 1.885 * k, r1 = (major ? 1.99 : long ? 1.955 : 1.92) * k;
      g.beginPath(); g.moveTo(Math.cos(a) * r0, Math.sin(a) * r0); g.lineTo(Math.cos(a) * r1, Math.sin(a) * r1); g.stroke();
    }
  } },
  { name: "band", speed: -0.045, tint: col(COLORS.deep, 1.5).lerp(col(COLORS.cyan, 1.2), 0.35), draw(g, k) {
    const R = rng(24071), slot = TAU / 24;
    for (let i = 0; i < 24; i++) {
      const w = slot * (0.35 + R() * 0.55), a0 = i * slot + R() * (slot - w);
      g.globalAlpha = 0.22 + R() * 0.7;
      band(g, 1.56 * k, (1.7 + R() * 0.07) * k, a0, a0 + w);
    }
    circle(g, 1.525 * k, 1.5, 0.45);
  } },
  { name: "notches", speed: 0.035, tint: col(COLORS.hi, 1.0), draw(g, k) {
    circle(g, 1.4 * k, 2, 0.55);
    g.globalAlpha = 1;
    for (let i = 0; i < 4; i++) { const a = i * TAU / 4 + 0.4; band(g, 1.365 * k, 1.44 * k, a - 0.03, a + 0.03); }
  } },
  { name: "dashes", speed: -0.08, tint: col(COLORS.cyan, 1.0), draw(g, k) {
    const slot = TAU / 72;
    g.globalAlpha = 0.7;
    for (let i = 0; i < 72; i++) band(g, 1.17 * k, 1.235 * k, i * slot, i * slot + slot * 0.55);
  } },
  { name: "arcs", speed: 0.15, tint: col(COLORS.cyan, 1.3), draw(g, k) {
    g.lineCap = "round";
    for (const [a, l] of [[0.1, 2.05], [2.45, 1.65], [4.4, 1.75]]) {
      g.globalAlpha = 0.7; g.lineWidth = 0.05 * k;
      g.beginPath(); g.arc(0, 0, 0.97 * k, a, a + l); g.stroke();
      g.globalAlpha = 0.35; g.lineWidth = 1.5;
      g.beginPath(); g.arc(0, 0, 0.88 * k, a + 0.15, a + l - 0.15); g.stroke();
    }
  } },
  { name: "disc", speed: 0, tint: col(COLORS.hi, 1.25), draw(g, k) {
    const gr = g.createRadialGradient(0, 0, 0, 0, 0, 0.72 * k);
    gr.addColorStop(0, "rgba(255,255,255,1)");
    gr.addColorStop(0.22, "rgba(255,255,255,.6)");
    gr.addColorStop(0.6, "rgba(255,255,255,.12)");
    gr.addColorStop(1, "rgba(255,255,255,0)");
    g.globalAlpha = 1; g.fillStyle = gr; g.beginPath(); g.arc(0, 0, 0.72 * k, 0, TAU); g.fill();
    circle(g, 0.5 * k, 2, 0.75);
    circle(g, 0.63 * k, 1.5, 0.35);
  } },
];

function poolTexture() {
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const g = c.getContext("2d");
  const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  gr.addColorStop(0, "rgba(255,255,255,1)");
  gr.addColorStop(0.4, "rgba(255,255,255,.45)");
  gr.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function createBeam(height) {
  const uniforms = { uTime: { value: 0 }, uOpacity: { value: 0.5 }, uColor: { value: col(COLORS.cyan) } };
  const mat = new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    vertexShader: /* glsl */ `
      varying vec2 vUv; varying vec3 vN; varying vec3 vV;
      void main() {
        vUv = uv;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform float uTime, uOpacity; uniform vec3 uColor;
      varying vec2 vUv; varying vec3 vN; varying vec3 vV;
      void main() {
        float up = pow(1.0 - vUv.y, 1.35) * smoothstep(1.0, 0.82, vUv.y);
        float edge = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 1.4);
        float a = vUv.x * 6.2831853;
        float streak = 0.5 + 0.5 * sin(a * 31.0 + sin(a * 5.0) * 2.0);
        float rise = 0.55 + 0.45 * sin(vUv.y * 16.0 - uTime * 1.1 + sin(a * 9.0) * 3.0);
        float I = up * (0.2 + 0.8 * edge) * mix(0.55, 1.0, streak * rise) * uOpacity;
        gl_FragColor = vec4(uColor * I, 1.0);
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.4, height, 96, 1, true), mat);
  mesh.position.y = height / 2;
  return { mesh, uniforms };
}

function createParticles(count, height) {
  const seeds = new Float32Array(count * 4), extra = new Float32Array(count * 4);
  for (let i = 0; i < count; i++) {
    seeds.set([Math.random(), Math.random(), Math.random(), Math.random()], i * 4);
    extra.set([Math.random(), Math.random() < 0.35 ? 1 : 0, Math.random(), 0], i * 4);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(count * 3), 3));
  geo.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 4));
  geo.setAttribute("aExtra", new THREE.BufferAttribute(extra, 4));
  const uniforms = {
    uFlow: { value: 0 }, uSpiral: { value: 0.5 }, uActive: { value: 0.35 }, uSpread: { value: 1 }, uSpeak: { value: 0 },
    uBright: { value: 1 }, uHeight: { value: height }, uDpr: { value: 1 },
    cA: { value: col(COLORS.hi, 1.4) }, cB: { value: col(COLORS.magenta, 1.6) },
  };
  const mat = new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: /* glsl */ `
      attribute vec4 aSeed; attribute vec4 aExtra;
      uniform float uFlow, uSpiral, uActive, uSpread, uSpeak, uHeight, uDpr;
      varying float vAlpha; varying float vPink;
      void main() {
        float ph = fract(aSeed.x + uFlow * (0.07 + aSeed.y * 0.11));
        float r = mix(0.28, 0.55, ph) * (0.2 + 0.8 * aExtra.x) * mix(1.0, uSpread, ph);
        float ang = aSeed.z * 6.2831853 + ph * uSpiral * 3.14159265 + uFlow * 0.12;
        vec3 p = vec3(cos(ang) * r, ph * uHeight, sin(ang) * r);
        vAlpha = smoothstep(0.0, 0.06, ph) * pow(1.0 - ph, 0.9) * step(aExtra.z, uActive);
        vPink = aExtra.y * uSpeak;
        gl_PointSize = (1.0 + aSeed.w * 2.0) * uDpr;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
      }`,
    fragmentShader: /* glsl */ `
      uniform float uBright; uniform vec3 cA, cB;
      varying float vAlpha; varying float vPink;
      void main() {
        float d = length(gl_PointCoord - 0.5);
        float a = smoothstep(0.5, 0.0, d) * vAlpha * uBright;
        if (a < 0.003) discard;
        gl_FragColor = vec4(mix(cA, cB, vPink) * a, 1.0);
      }`,
  });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  return { points, uniforms };
}

export function createPlatform({ light = false, beamHeight = 1.05 } = {}) {
  const group = new THREE.Group();          // escala no celular; os anéis ficam aqui
  const tilt = new THREE.Group();
  tilt.rotation.x = -THREE.MathUtils.degToRad(85);
  group.add(tilt);

  const size = light ? 1024 : 2048;
  const geo = new THREE.PlaneGeometry(PLANE, PLANE);
  const layers = LAYERS.map((L, i) => {
    const mat = new THREE.MeshBasicMaterial({ map: ringTexture(size, L.draw), color: L.tint.clone(),
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.z = i * 0.002;
    mesh.rotation.z = Math.random() * TAU;
    tilt.add(mesh);
    return { ...L, mesh, mat, base: L.tint.clone() };
  });

  const poolMat = new THREE.MeshBasicMaterial({ map: poolTexture(), color: col(COLORS.deep, 0.5),
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.55 });
  const pool = new THREE.Mesh(new THREE.PlaneGeometry(PLATFORM_R * 4.4, PLATFORM_R * 4.4), poolMat);
  pool.position.z = -0.01;
  tilt.add(pool);

  const column = new THREE.Group();         // feixe e partículas não inclinam nem encolhem com os anéis
  const beam = createBeam(beamHeight);
  const parts = createParticles(light ? 90 : 190, beamHeight);
  column.add(beam.mesh, parts.points);

  const ringByName = Object.fromEntries(layers.map(l => [l.name, l]));
  return {
    group, column, layers,
    setDpr(d) { parts.uniforms.uDpr.value = d; },
    update({ dt, t, ring, expand, flow, spiral, active, spread, speak, glow, pulse = 0 }) {
      for (const l of layers) {
        l.mesh.rotation.z += l.speed * ring * dt;
        l.mat.color.copy(l.base).multiplyScalar(glow * (1 + pulse * (l.name === "disc" ? 0.6 : 0.35)));
      }
      ringByName.ticks.mesh.scale.setScalar(1 + expand);
      beam.uniforms.uTime.value = t;
      beam.uniforms.uOpacity.value = 0.5 * glow;
      parts.uniforms.uFlow.value = flow;
      parts.uniforms.uSpiral.value = spiral;
      parts.uniforms.uActive.value = active;
      parts.uniforms.uSpread.value = spread;
      parts.uniforms.uSpeak.value = speak;
    },
  };
}
