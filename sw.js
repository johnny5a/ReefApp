// Offline cache for REEF Dive Survey. Bump VERSION when you change any file.
const VERSION = "reef-survey-v17";
const CORE = ["./", "index.html", "manifest.json", "icon-180.png", "icon-192.png", "icon-512.png"];
const EXTRA = ["vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css"];
// Region data files to keep from the start come from data/regions.json (written by build.py from regions.json);
// any other region is cached the first time it's opened.

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(async c => {
    await c.addAll(CORE);
    let regions = [];
    try { regions = await (await fetch("data/regions.json", {cache: "no-store"})).json(); } catch (_) {}
    const files = [...EXTRA, ...regions.filter(r => r.precache).map(r => r.file)];
    await Promise.all(files.map(u => c.add(u).catch(() => {})));
  }).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // The app page: network first so updates arrive, cached copy on the boat.
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then(r => { const copy = r.clone(); caches.open(VERSION).then(c => c.put("index.html", copy)); return r; })
      .catch(() => caches.match("index.html")));
    return;
  }
  // Data, icons, Google Fonts and map tiles you've viewed: cache first, then network (and keep a copy).
  if (url.origin === location.origin || /fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)
      || url.hostname === "tile.openstreetmap.org") {
    e.respondWith(caches.match(req, {ignoreSearch: true}).then(hit => hit || fetch(req).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(VERSION).then(c => c.put(req, copy)); }
      return r;
    })));
  }
});
