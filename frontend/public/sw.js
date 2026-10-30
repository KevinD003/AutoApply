// NoEfforts service worker (D89). It keeps exactly one thing for offline use: a static page that
// says you are offline. It never stores a page, an API response or anything about you, so a
// shared or lost device holds none of your jobs, answers or applications. Every request goes to
// the network as before; only a page you open while offline gets the offline page instead.
const CACHE = "noefforts-offline-v1";
const OFFLINE = "/offline.html";
const PRECACHE = [OFFLINE, "/icons/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  // Older caches (an earlier version of this worker) are removed, never read.
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return; // the browser handles everything else itself
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE)));
});
