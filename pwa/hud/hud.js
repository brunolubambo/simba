import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { createSphere } from "./sphere.js";
import { createPlatform, PLATFORM_R } from "./platform.js";
import { createBackdrop, FinishShader } from "./backdrop.js";

const canvas = document.getElementById("core");
const stage = document.getElementById("stage");
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

const FOV = 35, PITCH = THREE.MathUtils.degToRad(17), SPHERE_Y = 2.05, BEAM_H = 1.1;

let renderer = null;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "high-performance" });
} catch (e) {
  console.warn("[hud] WebGL indisponível; fica só o fundo em CSS.", e);
}
if (renderer) start(renderer);

function start(renderer) {
  const light = false;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);

  const backdrop = createBackdrop();
  const sphere = createSphere({ light });
  const platform = createPlatform({ light, beamHeight: BEAM_H });
  sphere.group.position.y = SPHERE_Y;
  scene.add(backdrop.mesh, platform.group, platform.column, sphere.group);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.9, 0.6, 0.1);
  const bloomSize = bloom.setSize.bind(bloom);
  bloom.setSize = (w, h) => bloomSize(Math.max(1, w >> 1), Math.max(1, h >> 1));   // bloom em meia resolução
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  const finish = new ShaderPass(FinishShader);
  composer.addPass(finish);

  // Parâmetros visuais atuais (P) perseguem os do estado (target) com amortecimento: nada salta.
  const IDLE = { rot: 0.05, ring: 1, expand: 0, speak: 0, halo: 0, bloom: 0.9, lift: 0, glow: 1,
                 active: 0.35, flow: 1, spiral: 0.5, spread: 1, amp: 0, intensity: 1 };
  const P = { ...IDLE }, target = { ...IDLE };

  const sphereCenter = new THREE.Vector3(0, SPHERE_Y, 0);
  const tmp = new THREE.Vector3();
  const toPx = (v, h) => (1 - (tmp.copy(v).project(camera).y * 0.5 + 0.5)) * h;

  function layout() {
    const w = innerWidth, h = innerHeight;
    if (!w || !h) return;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.setSize(w, h, false);
    composer.setPixelRatio(dpr);
    composer.setSize(w, h);
    platform.setDpr(dpr);
    camera.aspect = w / h;

    const box = stage.getBoundingClientRect();
    const tanH = Math.tan(THREE.MathUtils.degToRad(FOV / 2));
    const floorY = box.bottom - Math.max(30, h * 0.045);    // centro da plataforma, logo acima do rótulo
    let D = h > w ? 0.62 * w : 0.36 * h;                    // diâmetro da esfera em px
    let ringScale = 1;
    for (let pass = 0; pass < 3; pass++) {
      const dist = h / (D * tanH);
      camera.position.set(0, SPHERE_Y + Math.sin(PITCH) * dist, Math.cos(PITCH) * dist);
      camera.lookAt(sphereCenter);
      camera.clearViewOffset();
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld();
      const gap = toPx(tmp.set(0, 0, 0), h) - h / 2;        // distância vertical esfera -> plataforma
      const sphereY = floorY - gap;
      // a plataforma não pode passar da largura da tela
      const left = tmp.set(-PLATFORM_R, 0, 0).project(camera).x, right = -left;
      const ringPx = (right - left) * 0.5 * w;
      ringScale = Math.min(1, (w * 0.96) / ringPx);
      // e a esfera não pode subir além do topo do palco
      const top = sphereY - D / 2;
      if (top >= box.top + 8 || pass === 2) {
        camera.setViewOffset(w, h, 0, h / 2 - sphereY, w, h);
        camera.updateProjectionMatrix();
        backdrop.uniforms.uCenter.value.set(0.5, 1 - sphereY / h);
        break;
      }
      D *= Math.max(0.5, (floorY - box.top - 8) / (floorY - top));
    }
    platform.group.scale.setScalar(ringScale);
    backdrop.uniforms.uAspect.value = w / h;
  }
  layout();
  addEventListener("resize", layout);
  if ("ResizeObserver" in window) new ResizeObserver(layout).observe(stage);

  let last = performance.now(), yaw = 0, flow = 0, raf = 0;
  const t0 = last;
  function frame(now) {
    raf = requestAnimationFrame(frame);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const t = (now - t0) / 1000, motion = reduceMotion ? 0 : 1;
    const k = 1 - Math.exp(-dt / 0.16);
    for (const key in target) P[key] += (target[key] - P[key]) * k;
    yaw += dt * P.rot * motion;
    flow += dt * P.flow * motion;
    const breath = 1 + 0.015 * Math.sin(t * Math.PI / 2) * motion;
    sphere.update({ t: t * motion, yaw, breath, speak: P.speak, amp: P.amp * motion, lift: P.lift,
                    intensity: P.intensity, halo: P.halo }, camera);
    platform.update({ dt: dt * motion, t: t * motion, ring: P.ring, expand: P.expand, flow, spiral: P.spiral,
                      active: motion ? P.active : 0, spread: P.spread, speak: P.speak, glow: P.glow });
    bloom.strength = P.bloom;
    backdrop.uniforms.uTime.value = t * motion;
    finish.uniforms.uTime.value = t;
    composer.render(dt);
  }
  raf = requestAnimationFrame(frame);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { cancelAnimationFrame(raf); raf = 0; }
    else if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); }
  });

  window.simbaHUD = { P, target, IDLE };
}
