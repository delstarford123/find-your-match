// =========================================================================
// FIND YOUR MATCH (FYM) PWA SERVICE WORKER
// Robust Offline Support + W3C Web Push + Firebase Cloud Messaging (FCM)
// =========================================================================

const CACHE_NAME = 'find-your-match-v1.3';
const ASSETS_TO_CACHE = [
    '/',
    '/static/css/style.css',
    '/static/js/main.js',
    '/static/img/icon-192.png',
    '/static/img/badge-icon.png',
    '/static/img/placeholder.png',
    'https://assets.mixkit.co/active_storage/sfx/1435/1435-preview.mp3'
];

// 1. INSTALL: Pre-cache essential assets
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('✨ FYM PWA: Pre-caching assets for offline resilience');
            return cache.addAll(ASSETS_TO_CACHE).catch(err => {
                console.warn('⚠️ Pre-caching non-fatal warning:', err);
            });
        })
    );
    self.skipWaiting();
});

// 2. ACTIVATE: Clean up outdated caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(
                keys.map(key => {
                    if (key !== CACHE_NAME) {
                        console.log('🗑️ FYM PWA: Purging outdated cache:', key);
                        return caches.delete(key);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// 3. FETCH: Smart Network-First Strategy
self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;

    // Do not intercept external CDNs or Firebase Realtime DB streaming
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin && !url.href.includes('mixkit.co')) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then(networkResponse => {
                if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
                    const responseClone = networkResponse.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, responseClone);
                    });
                }
                return networkResponse;
            })
            .catch(() => {
                return caches.match(event.request).then(cachedResponse => {
                    if (cachedResponse) return cachedResponse;
                    if (event.request.mode === 'navigate') {
                        return caches.match('/');
                    }
                });
            })
    );
});

// 4. W3C WEB PUSH (Fired when app is closed / phone locked / in background)
self.addEventListener('push', event => {
    console.log('[FYM SW] Background push notification received');
    let data = {
        title: "Find Your Match 🔥",
        body: "You have a new alert on Find Your Match!",
        url: "/matches"
    };

    if (event.data) {
        try {
            data = Object.assign(data, event.data.json());
        } catch (e) {
            try {
                const text = event.data.text();
                if (text) data.body = text;
            } catch (err) {}
        }
    }

    const clickUrl = data.url || data.click_action || '/matches';
    const tag = data.tag || ('fym-alert-' + (data.type || 'msg') + '-' + (data.match_id || data.sender_id || Date.now()));

    const options = {
        body: data.body,
        icon: data.icon || '/static/img/icon-192.png',
        badge: data.badge || '/static/img/badge-icon.png',
        vibrate: [300, 100, 300, 100, 300],
        data: {
            url: clickUrl,
            timestamp: Date.now()
        },
        actions: [
            { action: 'open', title: 'Open Now 💬' },
            { action: 'close', title: 'Dismiss' }
        ],
        tag: tag,
        renotify: true,
        requireInteraction: true
    };

    event.waitUntil(
        self.registration.showNotification(data.title || "Find Your Match 🔥", options)
    );
});

// 5. FCM BACKGROUND HANDLER (Dual-Stack Support)
try {
    importScripts('https://www.gstatic.com/firebasejs/8.10.0/firebase-app.js');
    importScripts('https://www.gstatic.com/firebasejs/8.10.0/firebase-messaging.js');

    if (typeof firebase !== 'undefined' && !firebase.apps.length) {
        firebase.initializeApp({
            apiKey: "AIzaSyDUgNemh6L12y45b1kFZxAgsspwygvgkGc",
            projectId: "mmust-dating-site",
            messagingSenderId: "572096461211",
            appId: "1:572096461211:web:e38b542343ac8e4eca893e"
        });
    }

    if (typeof firebase !== 'undefined' && firebase.messaging.isSupported()) {
        const fcmMessaging = firebase.messaging();
        fcmMessaging.onBackgroundMessage(function(payload) {
            console.log('[FYM SW] FCM onBackgroundMessage:', payload);
            const notif = payload.notification || {};
            const d = payload.data || {};
            const title = notif.title || d.title || 'Find Your Match 🔥';
            const body = notif.body || d.body || 'You have a new update!';
            const clickUrl = d.url || notif.click_action || '/matches';
            const tag = d.tag || ('fym-fcm-' + (d.sender_id || Date.now()));

            const options = {
                body: body,
                icon: notif.icon || '/static/img/icon-192.png',
                badge: '/static/img/badge-icon.png',
                vibrate: [300, 100, 300, 100, 300],
                data: { url: clickUrl },
                actions: [
                    { action: 'open', title: 'Open 💬' },
                    { action: 'close', title: 'Dismiss' }
                ],
                tag: tag,
                renotify: true,
                requireInteraction: true
            };
            return self.registration.showNotification(title, options);
        });
    }
} catch (e) {
    console.log('[FYM SW] FCM worker script note:', e);
}

// 6. NOTIFICATION CLICK: Focus open tab or open window straight to destination
self.addEventListener('notificationclick', event => {
    event.notification.close();

    if (event.action === 'close') {
        return;
    }

    const rawTarget = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/matches';
    const targetUrl = new URL(rawTarget, self.location.origin).href;

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
            // If already on this exact page, just focus
            for (let client of windowClients) {
                if (client.url === targetUrl && 'focus' in client) {
                    return client.focus();
                }
            }
            // If an app window is open anywhere on our origin, navigate and focus
            for (let client of windowClients) {
                if (client.url.startsWith(self.location.origin) && 'focus' in client && 'navigate' in client) {
                    return client.navigate(targetUrl).then(focusedClient => focusedClient.focus());
                }
            }
            // If app is closed, open a brand new window directly to the target URL
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});