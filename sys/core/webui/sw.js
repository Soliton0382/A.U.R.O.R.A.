// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Aurora service worker: the app shell works offline-first-paint; the API is never cached.
const SHELL = "aurora-shell-v21";
const FILES = ["/", "/static/app.css", "/static/css/chat.css", "/static/css/metrics.css", "/static/css/agents.css", "/static/css/alerts.css",
  "/static/js/main.js", "/static/js/modules.js", "/static/js/api.js", "/static/js/i18n.js", "/static/js/dom.js", "/static/js/md.js", "/static/js/restart.js",
  "/static/js/bus.js", "/static/js/modules/chat.js", "/static/js/modules/trace.js", "/static/js/modules/import.js",
  "/static/js/modules/runs.js", "/static/js/modules/settings.js", "/static/js/modules/status.js",
  "/static/js/modules/metrics.js", "/static/js/modules/approvals.js", "/static/js/modules/alerts.js", "/static/js/modules/diary.js", "/static/js/modules/social.js", "/static/js/modules/security.js", "/static/js/modules/plugins.js", "/static/js/modules/harvester.js", "/static/js/modules/notifications.js", "/static/js/modules/updates.js", "/static/js/push.js", "/static/js/modules/sky.js", "/static/i18n/it_IT.json", "/static/i18n/en_US.json",
  "/static/assets/aurora_face_bg.webp", "/static/assets/aurora_face_bg_s.webp", "/static/assets/icon-192.png",
  "/manifest.webmanifest"];

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Network first, so a new version is used at once; the cache only covers being offline.
self.addEventListener("fetch", (ev) => {
  const url = new URL(ev.request.url);
  if (ev.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/v1/")) return;
  ev.respondWith(fetch(ev.request).then((res) => {
    if (res.ok) { const copy = res.clone(); caches.open(SHELL).then((c) => c.put(ev.request, copy)); }
    return res;
  }).catch(() => caches.match(ev.request)));
});

// Web Push: Aurora writes, the device shows it even with the WebUI closed.
self.addEventListener("push", (ev) => {
  let d = {};
  try { d = ev.data ? ev.data.json() : {}; } catch { d = { title: "Aurora", body: ev.data ? ev.data.text() : "" }; }
  ev.waitUntil(self.registration.showNotification(d.title || "Aurora", {
    body: d.body || "", tag: d.tag, icon: "/static/assets/icon-192.png", badge: "/static/assets/icon-192.png",
    data: { view: d.view || "chat" },
  }));
});

self.addEventListener("notificationclick", (ev) => {
  ev.notification.close();
  const view = ev.notification.data?.view || "chat";
  ev.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    const open = list.find((c) => new URL(c.url).origin === location.origin);
    if (open) { open.postMessage({ type: "show", view }); return open.focus(); }
    return self.clients.openWindow(`/?view=${encodeURIComponent(view)}`);
  }));
});
