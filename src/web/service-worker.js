/* TaskHub 1.0.0 PWA shell. API/private content is never cached. */
'use strict';
const CACHE_NAME = 'taskhub-v1-0-0-static';
const STATIC_ASSETS = [
  '/assets/v7_ui.css', '/assets/v7_ui.js',
  '/assets/v8_ui.css', '/assets/v8_ui.js',
  '/assets/game_ui.css', '/assets/game_ui.js',
  '/assets/i18n.js', '/assets/i18n.json',
  '/assets/taskhub-icon-192.png', '/assets/taskhub-icon-512.png',
  '/assets/Vazirmatn-Regular.ttf', '/assets/Vazirmatn-Bold.ttf',
  '/manifest.webmanifest'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => Promise.all(STATIC_ASSETS.map(url =>
        fetch(url, {cache: 'reload'}).then(response => {
          if (response && response.ok) return cache.put(url, response.clone());
          return null;
        }).catch(() => null)
      )))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)));
    await self.clients.claim();
    const clients = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
    clients.forEach(client => client.postMessage({type: 'TASKHUB_SW_READY', version: '1.0.0'}));
  })());
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname === '/') return;
  if (!STATIC_ASSETS.includes(url.pathname)) return;

  event.respondWith((async () => {
    try {
      const response = await fetch(request, {cache: 'no-store'});
      if (response && response.ok) {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(url.pathname, response.clone());
      }
      return response;
    } catch (_) {
      return (await caches.match(url.pathname)) || Response.error();
    }
  })());
});
