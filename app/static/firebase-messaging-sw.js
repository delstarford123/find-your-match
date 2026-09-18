importScripts('https://www.gstatic.com/firebasejs/8.10.0/firebase-app.js');
importScripts('https://www.gstatic.com/firebasejs/8.10.0/firebase-messaging.js');

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

    messaging.onBackgroundMessage(function(payload) {
        console.log('[firebase-messaging-sw.js] Received background message ', payload);
        const notificationTitle = payload.notification.title || "New Match!";
        const notificationOptions = {
            body: payload.notification.body,
            icon: '/static/img/icon-192.png'
        };
        self.registration.showNotification(notificationTitle, notificationOptions);
    });
} catch(e) {
    console.log("Firebase not configured in SW");
}
