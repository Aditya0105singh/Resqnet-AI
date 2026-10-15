/* resqnet offline cache.
 * Keeps map tiles and web fonts the browser has already loaded, so a demo rehearsed once keeps
 * working without a connection. It never prefetches: bulk downloading is against the tile
 * servers' usage policies (OpenStreetMap in particular). Cache-first; tiles change rarely. */
const CACHE = "resqnet-offline-v1";
const HOSTS = ["tile.openstreetmap.org", "tile.opentopomap.org", "server.arcgisonline.com", "fonts.googleapis.com", "fonts.gstatic.com"];
const MAX_ENTRIES = 8000;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

const cacheable = (url) => HOSTS.some((h) => url.hostname === h || url.hostname.endsWith("." + h));

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (!cacheable(url)) return;
  event.respondWith(
    (async () => {
      // the cache is an optimisation only: any CacheStorage failure falls through to the network
      let cache = null;
      try {
        cache = await caches.open(CACHE);
        const hit = await cache.match(req, { ignoreVary: true });
        if (hit) return hit;
      } catch {
        cache = null;
      }
      try {
        const res = await fetch(req);
        if (cache && res.ok) {
          cache.put(req, res.clone()).catch(() => {});
          event.waitUntil(trim(cache).catch(() => {}));
        }
        return res;
      } catch {
        return new Response("", { status: 504, statusText: "offline and not cached" });
      }
    })(),
  );
});

let trimming = false;
async function trim(cache) {
  if (trimming) return;
  trimming = true;
  try {
    const keys = await cache.keys();
    for (let i = 0; i < keys.length - MAX_ENTRIES; i++) await cache.delete(keys[i]);
  } finally {
    trimming = false;
  }
}
