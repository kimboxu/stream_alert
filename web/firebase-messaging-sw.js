importScripts('https://www.gstatic.com/firebasejs/9.10.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.10.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyA7Y2JnRXZ-nO4h1KDBvL2IsfS9mkYtTMM",
  authDomain: "streamalert-a07d2.firebaseapp.com",
  projectId: "streamalert-a07d2",
  storageBucket: "streamalert-a07d2.firebasestorage.app",
  messagingSenderId: "280701318686",
  appId: "1:280701318686:web:58495355e029a1257ca00f",
  measurementId: "G-RW0D9Z0781"
});

const messaging = firebase.messaging();

// 백그라운드 메시지 핸들링
messaging.onBackgroundMessage((payload) => {
  console.log('Background message received:', payload);
  
  const notificationTitle = payload.notification.title;
  const notificationOptions = {
    body: payload.notification.body,
    icon: '/favicon.png'
  };

  return self.registration.showNotification(notificationTitle, notificationOptions);
});
// 알림 클릭 처리
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  const urlToOpen = new URL('/notifications', self.location.origin).href;
  
  const promiseChain = clients.matchAll({
    type: 'window',
    includeUncontrolled: true
  })
  .then((windowClients) => {
    // 이미 열린 창이 있는지 확인
    for (let i = 0; i < windowClients.length; i++) {
      const client = windowClients[i];
      if (client.url === urlToOpen && 'focus' in client) {
        return client.focus();
      }
    }
    
    // 열린 창이 없으면 새 창 열기
    if (clients.openWindow) {
      return clients.openWindow(urlToOpen);
    }
  });
  
  event.waitUntil(promiseChain);
});