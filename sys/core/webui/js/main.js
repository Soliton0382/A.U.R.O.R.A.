// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The shell: login, layout (side menu, top bar, views), and the modules it composes.
// It holds no feature of its own: every feature is a module listed in modules.js.
import { call, register } from "./api.js";
import { bus } from "./bus.js";
import { $, el } from "./dom.js";
import * as i18n from "./i18n.js";
import { views, widgets } from "./modules.js";

const byId = Object.fromEntries(views.map((v) => [v.id, v]));
let current = null;

// ---- login: this browser becomes a registered device ------------------------------------
function deviceName() {
  const ua = navigator.userAgent;
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Windows/.test(ua) ? "Windows"
    : /Mac OS/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "?";
  const br = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? "Safari" : "browser";
  return `${os} · ${br}${matchMedia("(display-mode: standalone)").matches ? " · app" : ""}`;
}

async function authorized() {
  try { await call("/v1/models"); return true; } catch (e) { if (e.status === 401) return false; throw e; }
}

function showLogin(on) {
  $("login").classList.toggle("hidden", !on);
  $("app").classList.toggle("hidden", on);
}

$("login-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  let ok = false;
  try { await register($("login-key").value.trim(), deviceName()); $("login-key").value = ""; ok = await authorized(); }
  catch { ok = false; }
  $("login-error").classList.toggle("hidden", ok);
  if (ok) start();
});

// ---- layout ------------------------------------------------------------------------------
const ctx = {
  show,
  relogin: () => showLogin(true),
  replay: async (run) => { await show("chat"); byId.chat.replay(run); },
};

function buildNav() {
  const nav = $("nav");
  for (const v of views) {
    const b = el("button");
    b.dataset.view = v.id;
    const label = el("span", "label");
    label.dataset.i18n = v.title;
    b.append(el("span", "ic", v.icon), label);
    b.addEventListener("click", () => show(v.id));
    nav.append(b);
  }
}

function mountAll() {
  for (const v of views) {
    const section = el("section", "view hidden");
    section.id = `view-${v.id}`;
    $("views").append(section);
    v.mount(section, ctx);
  }
  for (const w of widgets) w.mount($(`slot-${w.slot}`), ctx);
  i18n.apply(document);
}

function drawer(open) { document.body.classList.toggle("drawer-open", open); }

async function show(id) {
  current = id;
  drawer(false);
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === id));
  document.querySelectorAll(".view").forEach((s) => s.classList.toggle("hidden", s.id !== `view-${id}`));
  bus.emit("view", { id });
  try { await byId[id].enter?.(); } catch (e) { if (e.status === 401) showLogin(true); else console.error(e); }
}

$("menu").addEventListener("click", () => drawer(!document.body.classList.contains("drawer-open")));
$("scrim").addEventListener("click", () => drawer(false));
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") drawer(false); });
$("lang").addEventListener("change", async (ev) => {
  await i18n.load(ev.target.value);
  bus.emit("lang", { code: ev.target.value });
  if (current) show(current);
});

let started = false;
function start() {
  showLogin(false);
  if (!started) { for (const w of widgets) w.enter?.(); started = true; }
  const asked = new URLSearchParams(location.search).get("view");
  show(current || (asked && byId[asked] ? asked : "chat"));
}

// ---- boot --------------------------------------------------------------------------------
const lang = i18n.saved();
$("lang").value = lang;
await i18n.load(lang);
buildNav();
mountAll();
if (await authorized()) start(); else showLogin(true);
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* no offline shell */ });
  navigator.serviceWorker.addEventListener("message", (ev) => {      // a notification was clicked
    if (ev.data?.type === "show" && byId[ev.data.view]) show(ev.data.view);
  });
}
