// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Web Push for this device: state, subscribe (asks the browser's permission), unsubscribe.
import { call } from "./api.js";

async function registration() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null;
  return navigator.serviceWorker.ready;
}

// inside Aurora's phone app the notifications come from its line, not from Web Push (the WebView has none): the app
// says whether Android lets it show them, and opens its settings
export const inApp = () => typeof window.AuroraApp?.notifications === "function";

export function appSettings() { window.AuroraApp?.settings(); }

export async function pushState() {
  if (inApp()) return window.AuroraApp.notifications() ? "app" : "appoff";
  const reg = await registration();
  if (!reg) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  return (await reg.pushManager.getSubscription()) && Notification.permission === "granted" ? "on" : "off";
}

export async function pushOn() {
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
  const reg = await registration();
  const sub = reg && await reg.pushManager.getSubscription();
  if (sub) {
    await call("/v1/aurora/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) });
    await sub.unsubscribe();
  }
  return pushState();
}
