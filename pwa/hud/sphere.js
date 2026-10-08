import * as THREE from "three";
import { SNOISE } from "./noise.js";

export const COLORS = {
  core: "#0A1F3D", deep: "#0B5CFF", cyan: "#38C8FF", hi: "#BFF3FF",
  blue: "#2F6BFF", violet: "#8A3CFF", magenta: "#FF3DD0",
};
const col = hex => new THREE.Color(hex);

const VERTEX = /* glsl */ `
uniform float uTime, uAmp, uFreq, uSpeed, uBreath;
varying vec3 vNView; varying vec3 vPosView; varying vec2 vUv; varying float vDisp;
${SNOISE}
float disp(vec3 n) {
  float s = uTime * uSpeed;
  float big = snoise(n * uFreq + vec3(0.0, s, s * 0.6));
  float mid = snoise(n * uFreq * 2.2 + vec3(s * 1.4, 7.0, -s));
  return (big * 0.72 + mid * 0.28) * uAmp;
}
void main() {
  vec3 n = normalize(position);
  vec3 nn = n;
  float d = 0.0;
  if (uAmp > 0.0005) {
    d = disp(n);
    vec3 t = normalize(cross(n, abs(n.y) < 0.99 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0)));
    vec3 b = normalize(cross(n, t));
    vec3 na = normalize(n + t * 0.02), nb = normalize(n + b * 0.02);
    vec3 p0 = n * (1.0 + d);
    nn = normalize(cross(na * (1.0 + disp(na)) - p0, nb * (1.0 + disp(nb)) - p0));
    if (dot(nn, n) < 0.0) nn = -nn;
  }
  vDisp = d;
  vUv = uv;
  vec4 mv = modelViewMatrix * vec4(n * (1.0 + d) * uBreath, 1.0);
  vPosView = mv.xyz;
  vNView = normalize(normalMatrix * nn);
  gl_Position = projectionMatrix * mv;
}`;

const FRAGMENT = /* glsl */ `
uniform vec3 cDeep, cCyan, cHi, cBlue, cViolet, cMagenta;
uniform float uSpeak, uIntensity, uLift, uBack, uDense, uAmp;
varying vec3 vNView; varying vec3 vPosView; varying vec2 vUv; varying float vDisp;
float hash1(float x) { return fract(sin(x * 91.345) * 47453.5453); }
// Linhas de ~1px em qualquer zoom (fwidth). Somem sozinhas onde as células ficam menores que poucos pixels (polos).
float grid(vec2 c) {
  vec2 w = max(fwidth(c), vec2(1e-4));
  vec2 d = abs(fract(c - 0.5) - 0.5);
  vec2 l = clamp(1.0 - d / (w * 1.15), 0.0, 1.0);
  l *= clamp((1.0 / w - 2.5) / 5.0, 0.0, 1.0);
  float vm = 0.78 + 0.44 * hash1(floor(c.x + 0.5));
  float vp = 0.78 + 0.44 * hash1(floor(c.y + 0.5) + 57.0);
  return max(l.x * vm, l.y * vp);
}
void main() {
  vec3 N = normalize(vNView);
  vec3 V = normalize(-vPosView);
  float facing = abs(dot(N, V));
  float fres = pow(1.0 - facing, 2.2);
  float g1 = grid(vUv * vec2(72.0, 48.0));
  float g2 = grid(vUv * vec2(144.0, 96.0));
  float dense = clamp(uDense * smoothstep(0.0, 0.1, abs(vDisp)), 0.0, 1.0);
  float lines = mix(g1, g2 * 0.8, dense);
  float I = lines * (0.26 + 1.3 * fres) + pow(1.0 - facing, 4.0) * 0.5 + 0.03;
  I *= uIntensity;
  if (!gl_FrontFacing) I *= uBack;

  vec3 calm = mix(cDeep, cCyan, clamp(fres * 1.25 + uLift, 0.0, 1.0));
  calm = mix(calm, cHi, clamp(pow(fres, 3.0) * 0.6 + lines * 0.12 + uLift * 0.3, 0.0, 1.0));

  vec3 L = normalize(vec3(0.6, -0.55, 0.55));
  float s = clamp(dot(N, L) * 0.6 + 0.42 + vDisp * 2.5, 0.0, 1.0);
  s = clamp(s - clamp(N.y * 0.5 + 0.5, 0.0, 1.0) * facing * 0.35, 0.0, 1.0);
  vec3 talk = s < 0.5 ? mix(cBlue, cViolet, s * 2.0) : mix(cViolet, cMagenta, (s - 0.5) * 2.0);
  talk = mix(talk, cHi, pow(fres, 3.0) * 0.22);

  gl_FragColor = vec4(mix(calm, talk, uSpeak) * I, 1.0);
}`;

function glowTexture() {
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const g = c.getContext("2d");
  const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  gr.addColorStop(0, "rgba(255,255,255,1)");
  gr.addColorStop(0.45, "rgba(255,255,255,.35)");
  gr.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// Arco fino de ~270° em volta da esfera, ciano -> magenta, com pontas afinando.
function createHalo() {
  const uniforms = { uOpacity: { value: 0 }, cA: { value: col(COLORS.cyan) }, cB: { value: col(COLORS.magenta) } };
  const mat = new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    vertexShader: /* glsl */ `
      varying vec2 vP;
      void main() { vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: /* glsl */ `
      uniform float uOpacity; uniform vec3 cA, cB;
      varying vec2 vP;
      void main() {
        float a = (atan(vP.y, vP.x) + 3.14159265) / 6.2831853;
        float span = 0.75;
        if (a > span) discard;
        float k = a / span;
        float taper = smoothstep(0.0, 0.14, k) * smoothstep(1.0, 0.8, k);
        float r = length(vP);
        float prof = 1.0 - smoothstep(0.0, 0.018 + 0.012 * taper, abs(r - 1.35));
        gl_FragColor = vec4(mix(cA, cB, k) * prof * taper * uOpacity * 1.6, 1.0);
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.RingGeometry(1.3, 1.4, 256, 1), mat);
  const pivot = new THREE.Group(); pivot.add(mesh);
  return { pivot, mesh, uniforms };
}

export function createSphere({ light = false } = {}) {
  const uniforms = {
    uTime: { value: 0 }, uAmp: { value: 0 }, uFreq: { value: 1.6 }, uSpeed: { value: 0.4 }, uBreath: { value: 1 },
    uSpeak: { value: 0 }, uIntensity: { value: 1 }, uLift: { value: 0 }, uBack: { value: 0.32 }, uDense: { value: 1 },
    cDeep: { value: col(COLORS.deep) }, cCyan: { value: col(COLORS.cyan) }, cHi: { value: col(COLORS.hi) },
    cBlue: { value: col(COLORS.blue) }, cViolet: { value: col(COLORS.violet) }, cMagenta: { value: col(COLORS.magenta) },
  };
  const material = new THREE.ShaderMaterial({
    uniforms, vertexShader: VERTEX, fragmentShader: FRAGMENT,
    transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
  });
  const mesh = new THREE.Mesh(light ? new THREE.SphereGeometry(1, 64, 48) : new THREE.SphereGeometry(1, 128, 96), material);

  const glowMat = new THREE.SpriteMaterial({ map: glowTexture(), color: col(COLORS.core).multiplyScalar(2.2),
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.55 });
  const glow = new THREE.Sprite(glowMat); glow.scale.setScalar(1.7);

  const halo = createHalo();
  const group = new THREE.Group();
  group.add(glow, mesh, halo.pivot);

  const calmGlow = col(COLORS.core).multiplyScalar(2.2), talkGlow = col(COLORS.violet).multiplyScalar(0.35);
  return {
    group, uniforms,
    update({ t, yaw, breath, speak, amp, lift, intensity, halo: haloOn }, camera) {
      uniforms.uTime.value = t;
      uniforms.uBreath.value = breath;
      uniforms.uSpeak.value = speak;
      uniforms.uAmp.value = amp;
      uniforms.uLift.value = lift;
      uniforms.uIntensity.value = intensity;
      mesh.rotation.y = yaw;
      glowMat.color.copy(calmGlow).lerp(talkGlow, speak);
      glow.scale.setScalar(1.7 * breath * (1 + amp * 0.6));
      halo.uniforms.uOpacity.value = haloOn;
      halo.pivot.visible = haloOn > 0.003;
      if (halo.pivot.visible) {
        halo.pivot.quaternion.copy(camera.quaternion);
        halo.mesh.rotation.set(THREE.MathUtils.degToRad(20), 0, -0.6 + t * 0.12);
        halo.mesh.scale.setScalar(1 + amp * 0.35);
      }
    },
  };
}
