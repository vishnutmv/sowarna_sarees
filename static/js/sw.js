self.addEventListener('install', event => {
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(clients.claim());
});

self.addEventListener('push', function(event) {
    let data = {};
    try {
        data = event.data.json();
    } catch (e) {
        data = { title: "New Update", body: event.data.text(), url: "/" };
    }

    const options = {
        body: data.body,
        icon: '/static/img/logo.png',
        badge: '/static/img/badge.png',
        data: {
            url: data.url
        },
        tag: 'new-product-notification',
        renotify: true
    };

    // Broadcast to all open tabs immediately
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
        clients.forEach(client => {
            client.postMessage({
                type: 'NEW_PRODUCT',
                title: data.title,
                body: data.body,
                url: data.url
            });
        });
    });

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url || '/')
    );
});
