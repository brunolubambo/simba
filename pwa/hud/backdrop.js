import * as THREE from "three";
import { SNOISE } from "./noise.js";

// Fundo: gradiente radial azul-marinho centrado na esfera, com manchas escuras e desfocadas de "ambiente".
export function createBackdrop() {
  const uniforms = {
    uCenter: { value: new THREE.Vector2(0.5, 0.6) },
    uAspect: { value: 1 },
    uTime: { value: 0 },
    cEdge: { value: new THREE.Color("#020812") },
    cCenter: { value: new THREE.Color("#041A33") },
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    depthTest: false,
    depthWrite: false,
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() { vUv = uv; gl_Position = vec4(position.xy, 0.999, 1.0); }`,
    fragmentShader: /* glsl */ `
      uniform vec2 uCenter; uniform float uAspect, uTime; uniform vec3 cEdge, cCenter;
      varying vec2 vUv;
      ${SNOISE}
      void main() {
        vec2 p = vUv - uCenter; p.x *= uAspect;
        float g = smoothstep(0.95, 0.0, length(p * vec2(0.85, 1.0)));
        vec3 col = mix(cEdge, cCenter, g * g);
        vec2 q = vUv * vec2(uAspect, 1.0);
        float n = snoise(vec3(q * 1.3, uTime * 0.015)) * 0.6 + snoise(vec3(q * 2.7 + 11.0, uTime * 0.02)) * 0.4;
        col *= 0.78 + 0.32 * smoothstep(-0.6, 0.7, n);
        gl_FragColor = vec4(col, 1.0);
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  mesh.frustumCulled = false;
  mesh.renderOrder = -100;
  return { mesh, uniforms };
}

// Último passe, já em sRGB: vinheta e granulação de filme (~3%). Sem scanlines.
export const FinishShader = {
  uniforms: { tDiffuse: { value: null }, uTime: { value: 0 }, uGrain: { value: 0.03 }, uVignette: { value: 0.5 } },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse; uniform float uTime, uGrain, uVignette;
    varying vec2 vUv;
    float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    void main() {
      vec4 c = texture2D(tDiffuse, vUv);
      float vig = smoothstep(0.98, 0.3, length((vUv - 0.5) * vec2(1.15, 1.0)));
      c.rgb *= mix(1.0 - uVignette, 1.0, vig);
      c.rgb += (hash(gl_FragCoord.xy + fract(uTime * 7.31) * 97.0) - 0.5) * uGrain;
      gl_FragColor = c;
    }`,
};
