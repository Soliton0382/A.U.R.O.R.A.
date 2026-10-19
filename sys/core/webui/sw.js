// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Aurora service worker: the app shell works offline-first-paint; the API is never cached.
const SHELL = "aurora-shell-v212";
const FILES = ["/", "/static/app.css", "/static/css/chat.css", "/static/css/metrics.css", "/static/css/usage.css", "/static/css/agents.css", "/static/css/alerts.css",
  "/static/js/main.js", "/static/js/stack.js", "/static/js/modules.js", "/static/js/api.js", "/static/js/i18n.js", "/static/js/dom.js", "/static/js/dates.js", "/static/js/md.js", "/static/js/restart.js",
  "/static/js/bus.js", "/static/js/modules/chat.js", "/static/js/modules/trace.js", "/static/js/modules/import.js",
  "/static/js/modules/runs.js", "/static/js/modules/usage.js", "/static/js/modules/settings.js", "/static/js/modules/status.js",
  "/static/js/modules/metrics.js", "/static/js/modules/brain.js", "/static/js/modules/brain_gray.js", "/static/css/brain.css", "/static/js/modules/approvals.js", "/static/js/modules/alerts.js", "/static/js/modules/diary.js", "/static/js/modules/dreams.js", "/static/js/modules/accounts.js", "/static/js/modules/accounts_services.js", "/static/js/modules/today.js", "/static/js/modules/advanced.js", "/static/js/style.js", "/static/js/welcome.js", "/static/js/modules/social.js", "/static/js/modules/security.js", "/static/js/modules/autonomy.js", "/static/js/modules/care_values.js", "/static/js/modules/care_doctor.js", "/static/js/modules/care_diet.js", "/static/js/modules/chat_media.js", "/static/js/modules/chat_think.js", "/static/js/modules/chat_menu.js", "/static/js/modules/chat_actions.js", "/static/js/diet.js", "/static/css/diet.css", "/static/js/modules/calendar.js", "/static/js/modules/calendar_form.js", "/static/js/modules/calendar_grid.js", "/static/js/calendar_alerts.js", "/static/css/calendar.css", "/static/js/modules/security_defence.js", "/static/js/modules/security_watch.js", "/static/js/modules/security_map.js", "/static/js/modules/fw_pick.js", "/static/js/modules/mask_view.js", "/static/js/modules/astro.js", "/static/js/modules/astro_live.js", "/static/js/modules/astro_nights.js", "/static/js/modules/astro_advice.js", "/static/js/modules/astro_imaging.js", "/static/js/modules/astro_sky.js", "/static/js/modules/astro_tuner.js", "/static/js/modules/astro_mount.js", "/static/js/modules/astro_mount3d.js", "/static/js/modules/astro_collim.js", "/static/js/modules/wizard.js", "/static/js/modules/security_defence_page.js", "/static/js/modules/security_watch_page.js", "/static/js/modules/security_out_page.js", "/static/js/modules/security_trace.js", "/static/js/modules/security_firewalls.js", "/static/js/modules/plugin_slot.js", "/static/js/modules/settings_form.js", "/static/js/modules/expenses.js", "/static/js/modules/security_edge.js", "/static/js/modules/dj_deck.js", "/static/css/dj_deck.css", "/static/js/modules/home.js", "/static/js/modules/home_scenes.js", "/static/css/home.css", "/static/css/trace.css", "/static/vendor/world/countries-110m.json", "/static/js/modules/ciso.js", "/static/js/modules/firewall.js", "/static/js/modules/aurorafw.js", "/static/js/modules/autonomy_box.js", "/static/js/modules/ideas.js", "/static/js/modules/ideas_page.js", "/static/js/modules/memory.js", "/static/js/modules/synapses.js", "/static/js/modules/deductions_box.js", "/static/js/modules/project_term.js", "/static/js/modules/project_plan.js", "/static/js/modules/project_docs.js", "/static/js/modules/plugins.js", "/static/js/modules/models.js", "/static/js/modules/models_mode.js", "/static/js/modules/models_custom.js", "/static/js/modules/models_choice.js", "/static/js/modules/models_presets.js", "/static/css/models_mode.css", "/static/js/modules/guide.js", "/static/js/modules/bugreport.js", "/static/js/modules/harvester.js", "/static/js/modules/harvest_plan.js", "/static/js/modules/notifications.js", "/static/js/modules/updates.js", "/static/js/modules/https.js", "/static/js/push.js", "/static/js/viewer.js", "/static/js/share.js", "/static/js/artifact.js", "/static/js/voice.js", "/static/js/vad.js", "/static/js/mood.js", "/static/js/backup.js", "/static/js/cards.js", "/static/js/qr.js", "/static/vendor/qrcode/qrcode.mjs", "/static/js/modules/users.js", "/static/js/modules/sky.js", "/static/js/theme.js", "/static/css/themes.css", "/static/js/modules/routines.js", "/static/js/modules/routines_templates.js", "/static/i18n/it_IT.json", "/static/i18n/en_US.json",
  "/static/assets/aurora_face_bg.webp", "/static/assets/aurora_face_bg_s.webp", "/static/assets/icon-192.png",
  "/manifest.webmanifest"];

self.addEventListener("install", (ev) => {
  // "reload": the offline copy is taken from the server, never from the browser's own cache (C109)
  ev.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES.map((u) => new Request(u, { cache: "reload" }))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Network first, so a new version is used at once; the cache only covers being offline. "no-cache" asks the server
// every time (an unchanged file is a 304): copies the browser kept by its own heuristics, from before the server
// said no-cache, served an old md.js and social.js after an update (C107, C109).
self.addEventListener("fetch", (ev) => {
  const url = new URL(ev.request.url);
  if (ev.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/v1/")) return;
  ev.respondWith(fetch(ev.request, { cache: "no-cache" }).then((res) => {
    if (res.ok) { const copy = res.clone(); caches.open(SHELL).then((c) => c.put(ev.request, copy)); }
    return res;
  }).catch(() => caches.match(ev.request)));
});

// Web Push: Aurora writes, the device shows it even with the WebUI closed.
self.addEventListener("push", (ev) => {
  let d = {};
  try { d = ev.data ? ev.data.json() : {}; } catch { d = { title: "Aurora", body: ev.data ? ev.data.text() : "" }; }
  // the device says it got it (M101): the push's random id is the proof, no key needed; a failure changes nothing
  const ack = d.id ? self.registration.pushManager.getSubscription()
    .then((sub) => fetch("/v1/aurora/push-ack", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: d.id, endpoint: sub ? sub.endpoint : "" }) })).catch(() => {}) : Promise.resolve();
  ev.waitUntil(Promise.all([ack, self.registration.showNotification(d.title || "Aurora", {
    body: d.body || "", tag: d.tag, icon: "/static/assets/icon-192.png", badge: "/static/assets/icon-192.png",
    data: { view: d.view || "chat" },
  })]));
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
