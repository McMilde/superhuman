// Service worker for Superhuman 2.0 – viser push-varsler fra coachen.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = { tittel: "Superhuman", tekst: "", url: "/" };
  try {
    data = { ...data, ...event.data.json() };
  } catch (e) {
    if (event.data) data.tekst = event.data.text();
  }
  event.waitUntil(
    self.registration.showNotification(data.tittel, {
      body: data.tekst,
      icon: "/static/icon-192.png",
      badge: "/static/icon-192.png",
      data: { url: data.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((liste) => {
      for (const klient of liste) {
        if ("focus" in klient) {
          klient.navigate(url).catch(() => {});
          return klient.focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
