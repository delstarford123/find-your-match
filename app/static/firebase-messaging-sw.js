// firebase-messaging-sw.js
// Find Your Match -- findyourmatch.co.ke
// FCM Background Message Handler (Firebase v9 compat SDK)

importScripts('https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.23.0/firebase-messaging-compat.js');

const firebaseConfig = {
    apiKey: "AIzaSyDUgNemh6L12y45b1kFZxAgsspwygvgkGc",
    authDomain: "mmust-dating-site.firebaseapp.com",
    databaseURL: "https://mmust-dating-site-default-rtdb.firebaseio.com",
    projectId: "mmust-dating-site",
    storageBucket: "mmust-dating-site.firebasestorage.app",
    messagingSenderId: "572096461211",
    appId: "1:572096461211:web:e38b542343ac8e4eca893e",
    measurementId: "G-YDFCFRS3HW"
};

try {
    firebase.initializeApp(firebaseConfig);
    const messaging = firebase.messaging();

    // Background message handler -- fires when app is closed/backgrounded
    messaging.onBackgroundMessage(function(payload) {
        console.log('[FYM SW] Background FCM message received:', payload);

        const notification = payload.notification || {};
        const data         = payload.data         || {};

        const title    = notification.title || data.title || 'Find Your Match';
        const body     = notification.body  || data.body  || 'You have a new message!';
        const icon     = notification.icon  || '/static/img/icon-192.png';
        const badge    = '/static/img/badge-icon.png';
        const clickUrl = data.url || notification.click_action || '/matches';

        const options = {
            body:     body,
            icon:     icon,
            badge:    badge,
            vibrate:  [300, 100, 300],
            data:     { url: clickUrl },
            actions: [
                { action: 'open',  title: 'Open Chat' },
                { action: 'close', title: 'Dismiss'   }
            ],
            tag:      'fym-message-' + (data.sender_id || 'general'),
            renotify: true
        };

        return self.registration.showNotification(title, options);
    });

    // Notification click -- open the exact chat or matches page
    self.addEventListener('notificationclick', function(event) {
        event.notification.close();

        if (event.action === 'close') return;

        const targetUrl = (event.notification.data && event.notification.data.url)
            ? event.notification.data.url
            : '/matches';

        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(windowClients) {
                for (let client of windowClients) {
                    if (client.url.includes(targetUrl) && 'focus' in client) {
                        return client.focus();
                    }
                }
                if (clients.openWindow) {
                    return clients.openWindow('https://findyourmatch.co.ke' + targetUrl);
                }
            })
        );
    });

} catch(e) {
    console.warn('[FYM SW] Firebase messaging init error:', e);
}
