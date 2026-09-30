const CACHE = "simba-v1";
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(["./", "index.html", "manifest.json", "icon.svg"]))));
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET" || new URL(e.request.url).pathname.startsWith("/push")) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
self.addEventListener("push", e => {
  const d = e.data ? e.data.json() : { title: "SIMBA", body: "" };
  e.waitUntil(self.registration.showNotification(d.title, { body: d.body, icon: "icon.svg", badge: "icon.svg" }));
});
self.addEventListener("notificationclick", e => { e.notification.close(); e.waitUntil(clients.openWindow("./")); });
