const CACHE_NAME = 'find-your-match-v1.2'; // Bumped version to force update
const ASSETS_TO_CACHE = [
    '/',
    '/static/css/style.css',
    '/static/js/main.js',
    '/static/img/icon-192.png',
    '/static/img/placeholder.png',
    'https://assets.mixkit.co/active_storage/sfx/1435/1435-preview.mp3' // Cache the match sound!
];

// ==========================================
// 1. INSTALL: Pre-cache essential assets
// ==========================================
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('✨ PWA: Pre-caching assets for offline use');
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
    self.skipWaiting(); // Force the waiting service worker to become active
});

// ==========================================
// 2. ACTIVATE: Clean up old versions
// ==========================================
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(
                keys.map(key => {
                    if (key !== CACHE_NAME) {
                        console.log('🗑️ PWA: Removing old cache', key);
                        return caches.delete(key);
                    }
                })
            );
        })
    );
    self.clients.claim(); // Immediately take control of all open tabs
});

// ==========================================
// 3. FETCH: Smart Network-First Strategy
// ==========================================
self.addEventListener('fetch', event => {
    // We only want to intercept GET requests (API POSTs like swipes must go to server)
    if (event.request.method !== 'GET') return;

    event.respondWith(
        fetch(event.request)
            .then(networkResponse => {
                // If the network works, clone the response and save it to cache
                return caches.open(CACHE_NAME).then(cache => {
                    cache.put(event.request, networkResponse.clone());
                    return networkResponse;
                });
            })
            .catch(() => {
                // If network fails (Offline), look in the cache
                return caches.match(event.request).then(cachedResponse => {
                    if (cachedResponse) return cachedResponse;
                    
                    // If even the cache is empty, return to home
                    if (event.request.mode === 'navigate') {
                        return caches.match('/');
                    }
                });
            })
    );
});

// ==========================================
// 4. PUSH: Background Notification Handler
// ==========================================
self.addEventListener('push', event => {
    let data = { title: "New Message!", body: "Someone sent you a chat.", url: "/dashboard" };
    
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            console.log("Push event received text instead of JSON, or parsing failed.");
        }
    }

    const options = {
        body: data.body,
        icon: '/static/img/icon-192.png',
        badge: '/static/img/badge-icon.png', // Transparent white icon for Android status bar
        vibrate: [300, 100, 300],
        data: { url: data.url }, // THIS holds the deep link to the specific chat!
        actions: [
            { action: 'reply', title: 'Reply Now 💬' },
            { action: 'close', title: 'Dismiss' }
        ],
        tag: 'match-chat-notification', // Groups messages so the phone doesn't spam 10 separate alerts
        renotify: true // Alerts the user even if they already have an unread notification from this tag
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// ==========================================
// 5. NOTIFICATION CLICK: Intelligent Routing
// ==========================================
self.addEventListener('notificationclick', event => {
    event.notification.close(); // Close the popup

    // If they clicked the "Dismiss" action button, do nothing else
    if (event.action === 'close') {
        return;
    }

    // Grab the exact chat URL we passed in the push payload
    const targetUrl = event.notification.data.url || '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
            // 1. Check if they already have the app open in a tab
            for (let client of windowClients) {
                // If the specific chat is already open, just focus the screen on it
                if (client.url === targetUrl && 'focus' in client) {
                    return client.focus();
                }
            }
            // 2. If the app is closed or they are on a different page, open a new window directly to the chat
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});