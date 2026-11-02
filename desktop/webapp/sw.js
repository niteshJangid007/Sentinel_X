/* SentinelX service worker: keeps the app shell available and makes the
   dashboard installable on a phone home screen. Data always comes from the
   running server; nothing sensitive is cached. */

const CACHE = "sentinelx-shell-v1";
const SHELL = ["/pwa/icon-192.png", "/pwa/icon-512.png", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) {
    return;
  }
  event.respondWith(
    fetch(request).catch(() =>
      caches.match(request).then((cached) => cached || Response.error())
    )
  );
});
