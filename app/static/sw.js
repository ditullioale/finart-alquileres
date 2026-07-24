// Service worker mínimo: habilita la instalación como app (PWA).
// No cachea páginas de datos para evitar mostrar información desactualizada.
const CACHE = "ga-static-v1";
const ASSETS = ["/static/style.css", "/static/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {}));
});

self.addEventListener("activate", (e) => {
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Solo servimos desde caché los archivos estáticos; el resto va a la red.
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(e.request).then((r) => r || fetch(e.request))
    );
  }
});
