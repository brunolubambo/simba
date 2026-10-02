import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const canvas = document.getElementById("core");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const TAU = Math.PI * 2;

const vert = `
uniform float uTime;
uniform float uAmp;
uniform float uFreq;
varying vec3 vN;
varying vec3 vObj;
varying float vDisp;
varying vec2 vUv;

vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);
  const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);
  vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy);
  vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;
  vec3 x2=x0-i2+C.yyy;
  vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;
  vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z);
  vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;
  vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);
  vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;
  vec4 s1=floor(b1)*2.0+1.0;
  vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);
  vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z);
  vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
  m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
float disp(vec3 n){
  float a=snoise(n*uFreq+uTime*0.40);
  float b=snoise(n*uFreq*2.05-uTime*0.22);
  return (a*0.66+b*0.34)*uAmp;
}
void main(){
  vUv=uv;
  vec3 n=normalize(position);
  float d=disp(n);
  float e=0.045;
  float dx=disp(normalize(n+vec3(e,0.0,0.0)))-disp(normalize(n-vec3(e,0.0,0.0)));
  float dy=disp(normalize(n+vec3(0.0,e,0.0)))-disp(normalize(n-vec3(0.0,e,0.0)));
  float dz=disp(normalize(n+vec3(0.0,0.0,e)))-disp(normalize(n-vec3(0.0,0.0,e)));
  vec3 bent=normalize(n-vec3(dx,dy,dz));
  vec3 pos=n*(1.0+d);
  vDisp=d;
  vObj=pos;
  vN=normalize(normalMatrix*bent);
  gl_Position=projectionMatrix*modelViewMatrix*vec4(pos,1.0);
}`;

const frag = `
uniform float uTalk;
uniform float uAmp;
varying vec3 vN;
varying vec3 vObj;
varying float vDisp;
varying vec2 vUv;
void main(){
  vec3 view=normalize(cameraPosition-vObj);
  float fres=pow(1.0-clamp(abs(dot(normalize(vN),view)),0.0,1.0),2.15);
  vec2 gv=vUv*vec2(72.0,48.0)*(1.0+uAmp*1.6);
  vec2 fw=fwidth(gv);
  vec2 g=abs(fract(gv-0.5)-0.5);
  float line=max(smoothstep(fw.x*1.15,0.0,g.x),smoothstep(fw.y*1.15,0.0,g.y));
  float grain=0.86+0.14*sin(vUv.x*140.0+vUv.y*90.0);
  float face=gl_FrontFacing?1.0:0.33;
  vec3 blue=mix(vec3(0.05,0.28,0.72),vec3(0.45,0.9,1.0),fres);
  vec3 mag=mix(vec3(0.18,0.42,1.0),vec3(0.62,0.28,1.0),clamp(vObj.y*0.45+0.4,0.0,1.0));
  mag=mix(mag,vec3(1.0,0.28,0.78),clamp(-vN.x*0.65+vDisp*4.0,0.0,1.0));
  vec3 col=mix(blue,mag,uTalk);
  float alpha=(line*0.9*grain+fres*0.28)*face;
  gl_FragColor=vec4(col*(0.25+line*1.15+fres*0.35),clamp(alpha,0.0,0.92));
}`;

const beamVert = `
varying vec2 vUv;
void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`;
const beamFrag = `
uniform float uTime;
uniform float uGlow;
varying vec2 vUv;
void main(){
  float up=pow(1.0-vUv.y,1.4);
  float stripe=0.65+0.35*sin(vUv.x*48.0-uTime*1.4);
  float a=up*stripe*uGlow*0.45;
  gl_FragColor=vec4(vec3(0.35,0.75,1.0)*a*2.2,a);
}`;

const haloFrag = `
varying vec2 vUv;
uniform float uOn;
void main(){
  float ang=vUv.x*6.28318;
  float arc=smoothstep(0.15,0.45,ang)*smoothstep(5.6,4.8,ang);
  vec3 col=mix(vec3(0.22,0.78,1.0),vec3(1.0,0.24,0.82),vUv.x);
  gl_FragColor=vec4(col,arc*uOn);
}`;

function ringTex(draw) {
  const c = document.createElement("canvas");
  c.width = c.height = 1024;
  const g = c.getContext("2d");
  g.translate(512, 512);
  draw(g);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}
function disc(g, r, w, color, a0 = 0, a1 = TAU) {
  g.beginPath();
  g.arc(0, 0, r, a0, a1);
  g.strokeStyle = color;
  g.lineWidth = w;
  g.stroke();
}

const texTicks = ringTex(g => {
  for (let i = 0; i < 120; i++) {
    const a = (i / 120) * TAU, long = i % 5 === 0;
    g.save();
    g.rotate(a);
    g.fillStyle = long ? "rgba(191,243,255,.95)" : "rgba(56,200,255,.55)";
    g.fillRect(-1.2, 430, long ? 2.6 : 1.4, long ? 46 : 22);
    g.restore();
  }
});
const texSeg = ringTex(g => {
  for (let i = 0; i < 24; i++) {
    const a = (i / 24) * TAU, span = 0.11 + (i % 3) * 0.03;
    g.globalAlpha = 0.45 + (i % 4) * 0.14;
    g.strokeStyle = "#7ee7ff";
    g.lineWidth = 18;
    g.beginPath();
    g.arc(0, 0, 360, a, a + span);
    g.stroke();
  }
});
const texThin = ringTex(g => {
  disc(g, 300, 2, "rgba(56,200,255,.8)");
  for (let i = 0; i < 4; i++) {
    g.fillStyle = "#bff3ff";
    const a = (i / 4) * TAU;
    g.beginPath();
    g.arc(Math.cos(a) * 300, Math.sin(a) * 300, 7, 0, TAU);
    g.fill();
  }
});
const texDash = ringTex(g => {
  g.strokeStyle = "rgba(56,200,255,.7)";
  g.lineWidth = 3;
  for (let i = 0; i < 72; i++) {
    const a = (i / 72) * TAU;
    g.beginPath();
    g.arc(0, 0, 250, a, a + 0.045);
    g.stroke();
  }
});
const texArc = ringTex(g => {
  g.lineWidth = 6;
  const spans = [[0.2, 1.6], [2.2, 1.2], [4.0, 1.9], [5.3, 0.7]];
  spans.forEach(([a, len], i) => {
    g.strokeStyle = i % 2 ? "rgba(191,243,255,.9)" : "rgba(11,92,255,.85)";
    g.beginPath();
    g.arc(0, 0, 200 - i * 16, a, a + len);
    g.stroke();
  });
});
const texPool = ringTex(g => {
  const grd = g.createRadialGradient(0, 0, 20, 0, 0, 480);
  grd.addColorStop(0, "rgba(11,92,255,.55)");
  grd.addColorStop(0.45, "rgba(8,40,90,.22)");
  grd.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grd;
  g.beginPath();
  g.arc(0, 0, 480, 0, TAU);
  g.fill();
});
const texCore = ringTex(g => {
  const grd = g.createRadialGradient(0, 0, 8, 0, 0, 200);
  grd.addColorStop(0, "rgba(191,243,255,.95)");
  grd.addColorStop(0.35, "rgba(11,92,255,.35)");
  grd.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grd;
  g.fillRect(-512, -512, 1024, 1024);
});

function plane(tex, size, opacity) {
  const m = new THREE.MeshBasicMaterial({
    map: tex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    opacity, toneMapped: false
  });
  const mesh = new THREE.Mesh(new THREE.CircleGeometry(size, 64), m);
  mesh.rotation.x = -1.48;
  return mesh;
}

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
renderer.setClearColor(0x000000, 0);
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 40);
camera.position.set(0, 1.85, 7.2);
camera.lookAt(0, 0.15, 0);

const rig = new THREE.Group();
scene.add(rig);

let light = reduce || (navigator.hardwareConcurrency || 8) <= 4;
const sphereMat = new THREE.ShaderMaterial({
  vertexShader: vert, fragmentShader: frag, transparent: true, depthWrite: false,
  blending: THREE.AdditiveBlending, side: THREE.DoubleSide, toneMapped: false,
  uniforms: { uTime: { value: 0 }, uAmp: { value: 0 }, uFreq: { value: 1.5 }, uTalk: { value: 0 } }
});
const sphere = new THREE.Mesh(new THREE.SphereGeometry(1, light ? 64 : 128, light ? 48 : 96), sphereMat);
sphere.position.y = 0.72;
rig.add(sphere);

const core = new THREE.Sprite(new THREE.SpriteMaterial({
  map: texCore, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.22, toneMapped: false
}));
core.position.y = 0.72;
core.scale.set(1.15, 1.15, 1);
rig.add(core);

const deck = new THREE.Group();
deck.position.y = -0.95;
rig.add(deck);
const layers = [
  { mesh: plane(texTicks, 1.55, 0.9), speed: 0.12 },
  { mesh: plane(texSeg, 1.32, 0.85), speed: -0.18 },
  { mesh: plane(texThin, 1.12, 0.8), speed: 0.07 },
  { mesh: plane(texDash, 0.98, 0.75), speed: -0.28 },
  { mesh: plane(texArc, 0.86, 0.9), speed: 0.22 }
];
layers.forEach((l, i) => { l.mesh.position.y = i * 0.012; deck.add(l.mesh); });
const pool = plane(texPool, 2.4, 0.7);
pool.position.y = -0.02;
deck.add(pool);
const well = plane(texCore, 0.42, 0.9);
well.position.y = 0.03;
deck.add(well);

const beamMat = new THREE.ShaderMaterial({
  vertexShader: beamVert, fragmentShader: beamFrag, transparent: true, depthWrite: false,
  blending: THREE.AdditiveBlending, side: THREE.DoubleSide, toneMapped: false,
  uniforms: { uTime: { value: 0 }, uGlow: { value: 0.55 } }
});
const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.34, 1.45, 24, 1, true), beamMat);
beam.position.y = -0.12;
rig.add(beam);

const haloMat = new THREE.ShaderMaterial({
  vertexShader: beamVert, fragmentShader: haloFrag, transparent: true, depthWrite: false,
  blending: THREE.AdditiveBlending, side: THREE.DoubleSide, toneMapped: false,
  uniforms: { uOn: { value: 0 } }
});
const halo = new THREE.Mesh(new THREE.TorusGeometry(1.35, 0.012, 12, 160), haloMat);
halo.position.y = 0.72;
halo.rotation.x = 1.15;
rig.add(halo);

const PCOUNT = light ? 70 : 180;
const seeds = Array.from({ length: PCOUNT }, () => ({
  a: Math.random() * TAU, r: 0.04 + Math.random() * 0.28,
  y: Math.random(), v: 0.12 + Math.random() * 0.4, s: 1 + Math.random() * 2.2
}));
const pPos = new Float32Array(PCOUNT * 3);
const pGeo = new THREE.BufferGeometry();
pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
const points = new THREE.Points(pGeo, new THREE.PointsMaterial({
  color: 0xbff3ff, size: 0.035, transparent: true, depthWrite: false,
  blending: THREE.AdditiveBlending, opacity: 0.85, toneMapped: false, sizeAttenuation: true
}));
rig.add(points);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.42, 0.45, 0.28);
composer.addPass(bloom);
composer.addPass(new OutputPass());

const modeTarget = { idle: 0, listening: 1, thinking: 2, speaking: 3 };
let mode = "idle";
let talk = 0, spin = 0, breathe = 0, amp = 0, bloomS = 0.9, part = 0.35, speed = 1, haloOn = 0;
let paused = false, acc = 0, lowFor = 0, last = performance.now();

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  const pr = light ? Math.min(devicePixelRatio || 1, 1.25) : Math.min(devicePixelRatio || 1, 2);
  renderer.setPixelRatio(pr);
  renderer.setSize(w, h, false);
  const bw = Math.max(2, w * pr * 0.5), bh = Math.max(2, h * pr * 0.5);
  composer.setSize(w, h);
  bloom.setSize(bw, bh);
  const visH = 2 * Math.tan(THREE.MathUtils.degToRad(35) / 2) * camera.position.z;
  rig.scale.setScalar(visH * 0.5 / 2);
}
addEventListener("resize", resize);
if ("ResizeObserver" in window) new ResizeObserver(resize).observe(canvas);
resize();

function levels(t) {
  if (typeof window.simbaLevels === "function") return window.simbaLevels(t);
  return { rms: 0, bass: 0, mid: 0, high: 0 };
}

function frame(now) {
  if (paused) return;
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  acc += dt;
  if (light && acc < 1 / 30) return;
  const step = acc; acc = 0;
  const lv = levels(now / 1000);
  const wantTalk = mode === "speaking" ? 1 : 0;
  const k = 1 - Math.exp(-step * 5);
  talk += (wantTalk - talk) * k;
  const audio = reduce ? 0 : (mode === "speaking" ? lv.rms : mode === "listening" ? 0.18 : 0);
  const ampTarget = reduce ? 0 : (mode === "speaking" ? 0.18 * (0.25 + audio) : 0);
  amp += (ampTarget - amp) * k;
  const bloomTarget = mode === "speaking" ? 0.7 : mode === "idle" ? 0.38 : 0.5;
  bloomS += (bloomTarget - bloomS) * k;
  bloom.strength = light ? bloomS * 0.65 : bloomS;
  bloom.enabled = !light;
  const partTarget = mode === "speaking" ? 1 : mode === "thinking" ? 0.75 : mode === "listening" ? 0.5 : 0.32;
  part += (partTarget - part) * k;
  const speedTarget = mode === "thinking" ? 2.4 : mode === "listening" ? 1.45 : mode === "speaking" ? 1 + lv.mid : 1;
  speed += (speedTarget - speed) * k;
  haloOn += (((mode === "speaking" ? 1 : mode === "thinking" ? 0.25 : 0)) - haloOn) * k;
  breathe += step * (reduce ? 0.4 : 1);
  spin += step * (mode === "thinking" ? 0.22 : 0.05) * (reduce ? 0.25 : 1);
  sphere.rotation.y = spin;
  const breath = 1 + Math.sin(breathe * 1.5) * (reduce ? 0.004 : 0.015);
  sphere.scale.setScalar(breath);
  sphereMat.uniforms.uTime.value = now / 1000;
  sphereMat.uniforms.uAmp.value = amp;
  sphereMat.uniforms.uTalk.value = talk;
  sphereMat.uniforms.uFreq.value = 1.35 + audio * 0.4;
  beamMat.uniforms.uTime.value = now / 1000;
  beamMat.uniforms.uGlow.value = 0.35 + part * 0.5 + lv.bass * talk;
  haloMat.uniforms.uOn.value = haloOn;
  halo.rotation.z += step * 0.15;
  core.material.opacity = 0.28 + talk * 0.35 + Math.sin(breathe * 2) * 0.05;
  layers.forEach(l => { l.mesh.rotation.z += step * l.speed * speed * (0.65 + lv.mid * talk); });
  const spread = 0.15 + part * 0.2 + talk * lv.high * 0.15;
  for (let i = 0; i < PCOUNT; i++) {
    const s = seeds[i];
    s.y += step * s.v * (0.45 + part * 1.3);
    if (s.y > 1) s.y -= 1;
    const ang = s.a + s.y * (mode === "thinking" ? 2.2 : 0.6);
    const rr = s.r * (0.4 + s.y) * (1 + spread);
    const y = -0.9 + s.y * 1.55;
    pPos[i * 3] = Math.cos(ang) * rr;
    pPos[i * 3 + 1] = y;
    pPos[i * 3 + 2] = Math.sin(ang) * rr;
  }
  pGeo.attributes.position.needsUpdate = true;
  points.material.opacity = 0.25 + part * 0.7;
  points.material.color.set(talk > 0.4 ? 0xff6ad4 : 0xbff3ff);
  const link = document.getElementById("hudLink");
  if (link) link.classList.toggle("off", !(window.simbaOnline && window.simbaOnline()));
  composer.render();
  const fps = step > 0 ? 1 / step : 60;
  if (!light && fps < 40) lowFor += step; else lowFor = 0;
  if (lowFor > 3) {
    light = true;
    sphere.geometry.dispose();
    sphere.geometry = new THREE.SphereGeometry(1, 64, 48);
    bloom.enabled = false;
    resize();
  }
}
requestAnimationFrame(frame);
document.addEventListener("visibilitychange", () => {
  paused = document.hidden;
  if (!paused) { last = performance.now(); requestAnimationFrame(frame); }
});

window.simbaHud = {
  setMode(next) { mode = modeTarget[next] != null ? next : "idle"; }
};
