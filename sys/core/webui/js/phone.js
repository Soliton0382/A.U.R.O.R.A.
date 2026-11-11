// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📱 An action Aurora was asked for on the phone (agt_phone, N68): the Android app does it (AuroraApp.act →
// PhoneActions: the phone's own browser, clock, calendar, maps, dialler); in a browser without the app, a link where
// one exists. Each action once, even when the run's stream is read again.
import { el } from "./dom.js";
import { t } from "./i18n.js";

const done = new Set();

// C565 (app 0.5.4): the app's actions take the key it gave this page's main frame; an app of before takes none
export function appCall(name, arg) {
  const app = window.AuroraApp;
  try { return app[name](window.AuroraAppKey || "", arg); } catch (e) {
    if (window.AuroraAppKey) throw e;                  // the new app: refused, never asked again without the key
    return app[name](arg);
  }
}

function link(p) {
  const q = encodeURIComponent;
  switch (p.action) {
    case "open_url": return p.url;
    case "web_search": return `https://www.google.com/search?q=${q(p.query)}`;
    case "navigate": return `https://www.google.com/maps/search/?api=1&query=${q(p.destination)}`;
    case "call": return p.number ? `tel:${p.number}` : "";
    case "message": return p.number ? `sms:${p.number}?body=${q(p.text || "")}` : "";
    default: return "";
  }
}

export function phoneAction(p, into) {
  if (!p?.id || done.has(p.id)) return;
  done.add(p.id);
  const line = el("div", "phone-act");
  if (window.AuroraApp?.act) {
    let r;
    try { r = appCall("act", JSON.stringify(p)); } catch { r = "bad"; }
    line.textContent = `📱 ${t(`phone.${r}`) || r}`;
  } else {
    const url = link(p);
    if (url) {
      const a = el("a", "", `📱 ${t("phone.open")}`);
      Object.assign(a, { href: url, target: "_blank", rel: "noopener" });
      line.append(a);
    } else {
      line.textContent = `📱 ${t("phone.app_only")}`;
    }
  }
  into.append(line);
}
