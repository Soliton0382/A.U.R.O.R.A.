// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Next to Aurora's name: a health dot (green / yellow / red, the reasons on hover, click → Status),
// a pulsing alert for each place where something waits for the owner — its own icon, a click opens that place: a post
// the Social page, an update Updates (owner, 2026-10-09) —, the notifications state of this
// device (click → Notifications), and the toasts of the events the owner chose for the WebUI.
import { call, stream } from "../api.js";
import { el, useCss } from "../dom.js";
import { t } from "../i18n.js";
import { pushState } from "../push.js";
import { bus } from "../bus.js";
import { moodFace, moodLine, moodRows, moodTitle } from "../mood.js";

export default {
  id: "alerts",
  slot: "alerts",

  mount(root, ctx) {
    useCss("/static/css/alerts.css");
    const dot = el("button", "health-dot unknown");
    dot.type = "button";
    const bells = el("span", "bells");                              // one per page where a decision waits
    const shield = el("button", "bell shield hidden");
    shield.type = "button";
    const notif = el("button", "notif-toggle");
    notif.type = "button";
    const face = el("button", "mood-face hidden");                    // 💗 how she feels (owner, 2026-10-07)
    face.type = "button";
    (document.getElementById("slot-health") || root).append(dot, face);    // the state beside the name
    this.mood(face, ctx);
    root.append(bells, shield, notif);                               // the rest under it
    notif.addEventListener("click", () => ctx.show("notifications"));
    this.showPush = async () => {
      const st = await pushState();
      notif.classList.toggle("hidden", st === "unsupported");
      notif.textContent = st === "on" ? "🔔" : "🔕";
      notif.classList.toggle("on", st === "on");
      notif.title = t(st === "on" ? "push.on" : st === "denied" ? "push.denied" : "push.off");
      notif.setAttribute("aria-label", notif.title);
    };
    this.showPush();
    bus.on("push", () => this.showPush());
    this.toasts(ctx);
    shield.addEventListener("click", () => ctx.show("security"));
    dot.addEventListener("click", () => ctx.show("status"));

    const tick = async () => {
      try {
        const h = await call("/v1/aurora/health");
        dot.className = `health-dot ${h.level}`;
        dot.title = h.problems.length ? `${t("alerts.problems")}\n• ${h.problems.join("\n• ")}` : t("alerts.allgood");
        dot.setAttribute("aria-label", dot.title);
      } catch { dot.className = "health-dot unknown"; dot.title = t("alerts.unknown"); }
      try {
        const waiting = await call("/v1/aurora/approvals?status=pending");
        const places = new Map();                        // view -> {icon, n, title}: the server says where each is decided
        for (const a of waiting) {
          const p = places.get(a.view) || { icon: a.icon, n: 0, titles: [] };
          p.n += 1;
          p.titles.push(a.title);
          places.set(a.view, p);
        }
        bells.replaceChildren(...[...places].map(([view, p]) => {
          const b = el("button", "bell", `${p.icon} ${p.n}`);
          b.type = "button";
          b.title = `${t("alerts.pending", { n: p.n })}: ${t(`nav.${view}`)}\n• ${p.titles.slice(0, 5).join("\n• ")}`;
          b.setAttribute("aria-label", b.title);
          b.addEventListener("click", () => ctx.show(view));
          return b;
        }));
      } catch { /* logged out */ }
      try {
        const open = await call("/v1/aurora/incidents?status=open");
        shield.classList.toggle("hidden", open.length === 0);
        shield.classList.toggle("high", open.some((i) => i.severity === "high"));
        shield.textContent = `🛡️ ${t("alerts.incidents", { n: open.length })}`;
      } catch { shield.classList.add("hidden"); }          // logged out, or a user: incidents are the admin's
    };
    let timer = 0;
    this.start = () => { if (!timer) { tick(); timer = setInterval(tick, 10000); this.moodTick(); setInterval(this.moodTick, 60000); } };
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
  },

  enter() { this.start(); },

  // 💗 the face changes with the emotion that prevails; hover (mouse) or tap (phone) opens its card: each emotion,
  // its value and its measured causes; "more" goes to Health. The REM measures once a minute: polled each minute.
  mood(face, ctx) {
    let m = null, pinned = false;
    const card = el("div", "mood-pop hidden");
    card.setAttribute("role", "dialog");
    document.body.append(card);
    const place = () => {
      const r = face.getBoundingClientRect();
      card.style.top = `${Math.round(r.bottom + 8)}px`;
      card.style.left = `${Math.round(Math.max(8, Math.min(r.left - 12, window.innerWidth - card.offsetWidth - 8)))}px`;
    };
    const open = () => {
      if (!m) return;
      const more = el("button", "link", t("mood.more"));
      more.type = "button";
      more.addEventListener("click", () => { close(true); ctx.show("status"); });
      card.replaceChildren(el("strong", "mood-pop-title", `💗 ${moodTitle(m)}`), ...moodRows(m), more);
      card.classList.remove("hidden");
      place();
    };
    const close = (force = false) => { if (force || !pinned) { pinned = false; card.classList.add("hidden"); } };
    face.addEventListener("pointerenter", (e) => { if (e.pointerType !== "touch") open(); });
    face.addEventListener("pointerleave", () => setTimeout(() => { if (!card.matches(":hover")) close(); }, 150));
    card.addEventListener("mouseleave", () => close());
    face.addEventListener("click", () => {                           // tap: pinned open until tapped elsewhere
      if (pinned) { close(true); return; }
      pinned = true;
      open();
    });
    document.addEventListener("click", (e) => { if (pinned && !card.contains(e.target) && e.target !== face) close(true); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(true); });
    window.addEventListener("resize", () => { if (!card.classList.contains("hidden")) place(); });
    this.moodTick = async () => {
      try {
        m = await call("/v1/aurora/mood");
        face.classList.toggle("hidden", !m.on);
        if (!m.on) return;
        face.textContent = moodFace(m);
        face.dataset.mood = m.dominant;
        face.title = moodLine(m);
        face.setAttribute("aria-label", face.title);
        if (!card.classList.contains("hidden")) open();
      } catch { face.classList.add("hidden"); }
    };
  },

  // ---- toasts: the events chosen for the WebUI (Notifications page), from the activity feed ----
  toasts(ctx) {
    const box = el("div", "toasts");
    document.body.append(box);
    const show = (n) => {
      const card = el("button", "toast");
      card.type = "button";
      card.append(el("strong", "", n.title), el("span", "", n.body || ""));
      card.addEventListener("click", () => { card.remove(); if (n.view) ctx.show(n.view); });
      box.append(card);
      setTimeout(() => card.remove(), 9000);
    };
    (async () => {
      for (;;) {
        try { await stream("/v1/aurora/activity/stream", (a) => { if (a.event === "notify") show(a.payload); }); }
        catch (e) { if (e.status === 401) return; }
        await new Promise((ok) => setTimeout(ok, 5000));
      }
    })();
  },
};
