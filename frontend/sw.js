// sw.js - basic service worker for notifications and push handling
self.addEventListener('install', event => {
  self.skipWaiting();
  console.log('Service Worker installed');
});

self.addEventListener('activate', event => {
  self.clients.claim();
  console.log('Service Worker activated');
});

// handle push events (server must send push messages)
// push payloads are not guaranteed; use default if not present
self.addEventListener('push', event => {
  let title = 'Medicine Reminder';
  let body = 'Time to take your medicine';
  try {
    const data = event.data ? event.data.json() : null;
    if(data) {
      title = data.title || title;
      body = data.body || body;
    }
  } catch(e) {
    // if not JSON
    const text = event.data ? event.data.text() : null;
    if(text) body = text;
  }

  const options = {
    body,
    icon: '/favicon.ico',
    badge: '/favicon.ico',
    vibrate: [100, 50, 100],
    data: { time: Date.now() }
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  // Focus or open the app
  event.waitUntil(
    clients.matchAll({ type: "window" }).then(clientList => {
      for (const client of clientList) {
        if (client.url && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow('/');
    })
  );
});
