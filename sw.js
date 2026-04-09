const CACHE_NAME = 'ican-heralds-v1';
const urlsToCache = [
  './ican_news.html',
  './manifest.json',
  './images/main_article.png',
  './css/style.css',
  './js/main.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});