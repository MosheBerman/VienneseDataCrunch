/* Service Worker: cache-first for our data + app shell, so repeat visits
   are instant and the map works offline. Basemap tiles: stale-while-revalidate. */
const CACHE = 'lehmann1938-v1';
const SHELL = ['.', 'index.html', 'style.css', 'app.js', 'worker.js'];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((ks) =>
      Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  // Cache-first for everything we fetch (app shell, data, basemap tiles);
  // populate the cache on miss. Repeat visits are instant, map works offline.
  e.respondWith(
    caches.match(e.request).then((hit) => {
      if (hit) return hit;
      return fetch(e.request).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      });
    })
  );
});
