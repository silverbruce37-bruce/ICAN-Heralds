const CACHE_NAME = 'ican-heralds-2026-04-28';
const STATIC_ASSETS = [
    './css/style.css',
    './css/food-hunter.css',
    './js/main.js',
    './js/academy.js',
    './js/academy-data.js',
    './manifest.json'
];

self.addEventListener('install', event => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', event => {
    if (event.request.destination === 'document') {
        // Network-first for HTML — always get fresh daily edition
        event.respondWith(
            fetch(event.request)
                .then(resp => {
                    const clone = resp.clone();
                    caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
                    return resp;
                })
                .catch(() => caches.match(event.request))
        );
    } else {
        // Cache-first for static assets (CSS, JS, images)
        event.respondWith(
            caches.match(event.request).then(r => r || fetch(event.request))
        );
    }
});
