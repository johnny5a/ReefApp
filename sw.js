// Offline cache for REEF Dive Survey. Bump VERSION when you change any file.
const VERSION = "reef-survey-v22";
// Map tiles and fonts live in their own cache so an app or data update does not wipe the offline map.
const KEEP = "reef-keep-v1", KEEP_MAX = 1500;
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
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION && k !== KEEP).map(k => caches.delete(k)))).then(() => self.clients.claim()));
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
  // Map tiles you've viewed and Google Fonts: cache first, kept across updates (oldest dropped past KEEP_MAX).
  if (url.hostname === "tile.openstreetmap.org" || /fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok) {
        const copy = r.clone();
        e.waitUntil(caches.open(KEEP).then(async c => {
          await c.put(req, copy);
          if (Math.random() < 0.05) { const keys = await c.keys(); if (keys.length > KEEP_MAX) await Promise.all(keys.slice(0, keys.length - KEEP_MAX + 200).map(k => c.delete(k))); }
        }));
      }
      return r;
    })));
    return;
  }
  // The app's own files and data: cache first, then network (and keep a copy).
  if (url.origin === location.origin) {
    e.respondWith(caches.match(req, {ignoreSearch: true}).then(hit => hit || fetch(req).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(VERSION).then(c => c.put(req, copy)); }
      return r;
    })));
  }
});
