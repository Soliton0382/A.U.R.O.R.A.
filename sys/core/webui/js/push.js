// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Web Push for this device: state, subscribe (asks the browser's permission), unsubscribe.
import { call } from "./api.js";
import { bus } from "./bus.js";

async function registration() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null;
  return navigator.serviceWorker.ready;
}

// inside Aurora's phone app the notifications come from its line, not from Web Push (the WebView has none): the app
// says whether Android lets it show them, and opens its settings
export const inApp = () => typeof window.AuroraApp?.notifications === "function";

// C594 (app 0.5.5): these two take the key the app gave this page's main frame, like its actions (phone.js); an app
// of before takes none
function app(name) {
  const a = window.AuroraApp;
  try { return a[name](window.AuroraAppKey || ""); } catch (e) {
    if (window.AuroraAppKey) throw e;
    return a[name]();
  }
}

export function appSettings() { if (inApp()) app("settings"); }

// 🖥️ C758 (owner, 27 Nov: «le notifiche nell'app desktop ancora non funzionano»): Aurora Desktop's window
// (QtWebEngine) has notifications but no Web Push — no push service behind it. There the page keeps Aurora's line
// open (GET /v1/aurora/line, what the phone app uses: the same notifications as push) and shows each event as a
// Notification, which the window hands to the desktop (notify-send); a click brings Aurora forward on its page.
// Any browser without Web Push but with notifications does the same.
const LINE_OFF = "aurora.line.off";
// C758 again (measured 27 Nov in a copy of the window: «PushManager» in window is true, there is no push service
// behind it — QtWebEngine/6.10.2 says so in its user agent): QtWebEngine always takes the line
const qtWindow = () => /\bQtWebEngine\//.test(navigator.userAgent || "");
export const lineMode = () => !inApp() && "Notification" in window && (qtWindow() || !("PushManager" in window));
const lineWanted = () => { try { return localStorage.getItem(LINE_OFF) !== "1"; } catch { return true; } };
let lineOn = false;

export async function startLine() {
  if (lineOn || !lineMode() || Notification.permission !== "granted" || !lineWanted()) return;
  lineOn = true;
  let next = "";
  try { next = (await call("/v1/aurora/line")).next || ""; } catch { lineOn = false; return; }
  while (lineOn && lineWanted()) {
    try {
      const r = await call(`/v1/aurora/line?after=${encodeURIComponent(next)}&wait=50`);
      next = r.next || next;
      for (const ev of r.events || []) {
        if (!ev.title || (ev.kind && ev.kind !== "notify")) continue;       // a call's ring, an ack: the phone's
        const n = new Notification(ev.title, { body: ev.body || "", tag: ev.tag || ev.id, icon: "/static/assets/icon-192.png" });
        n.onclick = () => { window.focus(); bus.emit("show", { id: ev.view || "chat" }); n.close(); };
      }
    } catch (e) {
      if (e.status === 401) { lineOn = false; return; }                     // signed out: the line ends
      await new Promise((res) => setTimeout(res, 10000));                    // Aurora restarting: again in a while
    }
  }
  lineOn = false;
}

export async function pushState() {
  if (inApp()) return app("notifications") ? "app" : "appoff";
  if (lineMode()) {
    if (Notification.permission === "denied") return "denied";
    return Notification.permission === "granted" && lineWanted() ? "on" : "off";
  }
  const reg = await registration();
  if (!reg) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  return (await reg.pushManager.getSubscription()) && Notification.permission === "granted" ? "on" : "off";
}

export async function pushOn() {
  if (lineMode()) {
    try { localStorage.removeItem(LINE_OFF); } catch { /* kept for this page only */ }
    if (await Notification.requestPermission() === "granted") startLine();
    return pushState();
  }
  const reg = await registration();
  if (!reg || await Notification.requestPermission() !== "granted") return pushState();
  const { public_key: k } = await call("/v1/aurora/push");
  const key = Uint8Array.from(atob(k.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - k.length % 4) % 4)), (c) => c.charCodeAt(0));
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  await call("/v1/aurora/push/subscribe", { method: "POST", body: JSON.stringify({ subscription: sub.toJSON() }) });
  await call("/v1/aurora/push/test", { method: "POST", body: "{}" });
  return pushState();
}

export async function pushOff() {
  if (lineMode()) {
    try { localStorage.setItem(LINE_OFF, "1"); } catch { /* for this page only */ }
    lineOn = false;
    return pushState();
  }
  const reg = await registration();
  const sub = reg && await reg.pushManager.getSubscription();
  if (sub) {
    await call("/v1/aurora/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) });
    await sub.unsubscribe();
  }
  return pushState();
}
