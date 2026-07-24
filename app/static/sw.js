// Service worker: habilita la instalación como app (PWA).
// Estrategia "network-first" para estáticos: siempre intenta traer la versión
// más nueva desde la red y solo usa la caché si estás sin conexión. Así los
// cambios de diseño (CSS) se ven apenas se despliegan, sin quedar pegado a una
// versión vieja.
const CACHE = "ga-static-v2";
const ASSETS = ["/static/style.css", "/static/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {}));
});

self.addEventListener("activate", (e) => {
  // Borra cachés de versiones anteriores.
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      fetch(e.request)
        .then((resp) => {
          // Guarda una copia fresca en caché para uso offline.
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
          return resp;
        })
        .catch(() => caches.match(e.request))
    );
  }
});
