/*
 * Service Worker — offline-capable PWA + push notifications.
 * Simple cache-first strategy for /static/*, network-first for everything else.
 */
const CACHE = 'jerumednexus-v1';
const OFFLINE_ASSETS = [
  '/static/logo.png',
  '/static/command_palette.js',
  '/static/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(OFFLINE_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE).map(k => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  // Never intercept anything but GET. POST/PUT/DELETE (all save/config/API
  // calls) must go straight to the network untouched — routing them through
  // the SW is a cross-browser source of failed saves ("non salva").
  if (e.request.method !== 'GET') {
    return;
  }
  const url = new URL(e.request.url);
  // Only handle same-origin GETs; leave fonts/CDN/etc. to the browser.
  if (url.origin !== self.location.origin) {
    return;
  }
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
    return;
  }
  // Never cache API responses — always fresh, no offline fallback.
  if (url.pathname.startsWith('/api/')) {
    return;
  }
  // Network-first for pages so operators always see fresh data
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});

// Push notifications — operator alerts
self.addEventListener('push', (e) => {
  const data = e.data ? e.data.json() : {title: 'JerumedNexus', body: 'Notifica'};
  e.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    icon: '/static/logo.png',
    tag:  data.tag || 'default',
    data: {url: data.url || '/'},
    requireInteraction: data.severity === 'critical',
  }));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data.url));
});
