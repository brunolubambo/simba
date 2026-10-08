const CACHE = "simba-v2";
const SHELL = ["./", "index.html", "manifest.json", "icon.svg",
  "hud/hud.js", "hud/sphere.js", "hud/platform.js", "hud/backdrop.js", "hud/noise.js",
  "vendor/three/three.module.min.js",
  "vendor/three/addons/postprocessing/EffectComposer.js", "vendor/three/addons/postprocessing/RenderPass.js",
  "vendor/three/addons/postprocessing/UnrealBloomPass.js", "vendor/three/addons/postprocessing/OutputPass.js",
  "vendor/three/addons/postprocessing/ShaderPass.js", "vendor/three/addons/postprocessing/MaskPass.js",
  "vendor/three/addons/postprocessing/Pass.js",
  "vendor/three/addons/shaders/CopyShader.js", "vendor/three/addons/shaders/LuminosityHighPassShader.js",
  "vendor/three/addons/shaders/OutputShader.js"];
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/push")) return;
  // Sempre pergunta ao servidor (sem a cópia do cache HTTP); o cache do SW só serve offline.
  e.respondWith(fetch(e.request, { cache: "no-cache" }).catch(() => caches.match(e.request, { ignoreSearch: true })));
});
self.addEventListener("push", e => {
  const d = e.data ? e.data.json() : { title: "SIMBA", body: "" };
  e.waitUntil(self.registration.showNotification(d.title, { body: d.body, icon: "icon.svg", badge: "icon.svg" }));
});
self.addEventListener("notificationclick", e => { e.notification.close(); e.waitUntil(clients.openWindow("./")); });
