importScripts('https://www.gstatic.com/firebasejs/8.10.0/firebase-app.js');
importScripts('https://www.gstatic.com/firebasejs/8.10.0/firebase-messaging.js');

firebase.initializeApp({
    apiKey: "AIzaSyDUgNemh6L12y45b1kFZxAgsspwygvgkGc",
    projectId: "mmust-dating-site",
    messagingSenderId: "572096461211",
    appId: "1:572096461211:web:e38b542343ac8e4eca893e"
});

const messaging = firebase.messaging();
messaging.onBackgroundMessage(function(payload) {
    console.log('[FCM] Background message received: ', payload);
    const notificationTitle = payload.notification ? payload.notification.title : (payload.data ? payload.data.title : 'Find Your Match');
    const notificationOptions = {
        body: payload.notification ? payload.notification.body : (payload.data ? payload.data.body : 'You have a new notification!'),
        icon: '/static/img/icon-192.png',
        data: payload.data,
        tag: 'fym-notification'
    };
    self.registration.showNotification(notificationTitle, notificationOptions);
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.click_action)
        ? event.notification.data.click_action
        : '/matches';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(windowClients) {
            for (let client of windowClients) {
                if (client.url.includes(targetUrl) && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow('https://findyourmatch.vercel.app' + targetUrl);
            }
        })
    );
});
