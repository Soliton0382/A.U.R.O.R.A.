// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Next to Aurora's name: a health dot (green / yellow / red, the reasons on hover, click → Status),
// a pulsing bell when something waits for the owner (click → Repairs), the notifications state of this
// device (click → Notifications), and the toasts of the events the owner chose for the WebUI.
import { call, stream } from "../api.js";
import { el, useCss } from "../dom.js";
import { t } from "../i18n.js";
import { pushState } from "../push.js";
import { bus } from "../bus.js";

export default {
  id: "alerts",
  slot: "alerts",

  mount(root, ctx) {
    useCss("/static/css/alerts.css");
    const dot = el("button", "health-dot unknown");
    dot.type = "button";
    const bell = el("button", "bell hidden");
    bell.type = "button";
    const shield = el("button", "bell shield hidden");
    shield.type = "button";
    const notif = el("button", "notif-toggle");
    notif.type = "button";
    (document.getElementById("slot-health") || root).append(dot);    // the state beside the name
    root.append(bell, shield, notif);                                // the rest under it
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
    bell.addEventListener("click", () => ctx.show("approvals"));

    const tick = async () => {
      try {
        const h = await call("/v1/aurora/health");
        dot.className = `health-dot ${h.level}`;
        dot.title = h.problems.length ? `${t("alerts.problems")}\n• ${h.problems.join("\n• ")}` : t("alerts.allgood");
        dot.setAttribute("aria-label", dot.title);
      } catch { dot.className = "health-dot unknown"; dot.title = t("alerts.unknown"); }
      try {
        const n = (await call("/v1/aurora/approvals?status=pending")).length;
        bell.classList.toggle("hidden", n === 0);
        bell.textContent = `🛎️ ${t("alerts.pending", { n })}`;
      } catch { /* logged out */ }
      try {
        const open = await call("/v1/aurora/incidents?status=open");
        shield.classList.toggle("hidden", open.length === 0);
        shield.classList.toggle("high", open.some((i) => i.severity === "high"));
        shield.textContent = `🛡️ ${t("alerts.incidents", { n: open.length })}`;
      } catch { shield.classList.add("hidden"); }          // logged out, or a user: incidents are the admin's
    };
    let timer = 0;
    this.start = () => { if (!timer) { tick(); timer = setInterval(tick, 10000); } };
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
  },

  enter() { this.start(); },

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
