// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The shell: login, layout (side menu, top bar, views), and the modules it composes.
// It holds no feature of its own: every feature is a module listed in modules.js.
import { call, register } from "./api.js";
import { bus } from "./bus.js";
import { $, el } from "./dom.js";
import * as i18n from "./i18n.js";
import * as voice from "./voice.js";
import { adminOnly, groups, views, widgets } from "./modules.js";
import { applyTheme, current as currentTheme, themePicker } from "./theme.js";
import { welcome } from "./welcome.js";
import { SHORT, adopt, applyStyle, current as currentStyle, home as styleHome, pins, setStyle } from "./style.js";
import { stackTables } from "./stack.js";

const byId = Object.fromEntries(views.map((v) => [v.id, v]));
let current = null;
let isAdmin = true;                // multi-user: a user does not see the machine's pages (adminOnly)
// a phone's own layout (chat.css): the installed PWA, and Aurora's Android app — a WebView, never «standalone»
if (/AuroraApp\//.test(navigator.userAgent) || matchMedia("(display-mode: standalone)").matches) {
  document.documentElement.classList.add("phone-app");
}

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
  if (on) {                       // multi-user: name, password and code first; the API key stays the admin's way in
    fetch("/health").then((r) => r.json()).then((h) => {
      const users = h.login === "users";
      $("login-user").classList.toggle("hidden", !users);
      $("login-form").classList.toggle("hidden", users);
      $("login-to-user").classList.toggle("hidden", !users);
    }).catch(() => {});
  }
}
$("login-to-key").addEventListener("click", () => { $("login-user").classList.add("hidden"); $("login-form").classList.remove("hidden"); });
$("login-to-user").addEventListener("click", () => { $("login-form").classList.add("hidden"); $("login-user").classList.remove("hidden"); });

$("login-user").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const err = $("login-user-error");
  err.classList.add("hidden");
  const body = { name: $("login-name").value.trim(), password: $("login-password").value,
    code: $("login-code").value.trim(), device: deviceName() };
  try {
    const r = await call("/v1/aurora/login", { method: "POST", body: JSON.stringify(body) });
    if (r.enroll) {               // the first login: the authenticator is linked here, then the first code
      const { qrSvg } = await import("./qr.js");
      $("login-qr").replaceChildren(qrSvg(r.enroll.uri));
      $("login-secret").textContent = r.enroll.secret;
      $("login-enroll").classList.remove("hidden");
      $("login-code").required = true;
      $("login-code").focus();
      return;
    }
    $("login-password").value = ""; $("login-code").value = "";
    $("login-enroll").classList.add("hidden");
    if (await authorized()) start();
  } catch (e) {
    err.textContent = i18n.t(e.status === 429 ? "login.locked" : "login.user_error");
    err.classList.remove("hidden");
  }
});

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

function navButton(v) {
  const b = el("button");
  b.dataset.view = v.id;
  const label = el("span", "label");
  label.dataset.i18n = v.title;
  b.append(el("span", "ic", v.icon), label);
  b.addEventListener("click", () => show(v.id));
  return b;
}

// two menus, one shown by the style (style.js, ROADMAP 107): the full one (every area) and the short one (six pages,
// the pinned ones, Avanzate)
function buildNav() {
  const nav = el("div", "nav-full");
  $("nav").replaceChildren(nav, el("div", "nav-short"));
  const byView = Object.fromEntries(views.map((v) => [v.id, v]));
  const placed = new Set(["advanced"]);
  for (const g of groups) {
    const members = g.views.map((id) => byView[id]).filter(Boolean);
    members.forEach((v) => placed.add(v.id));
    if (members.length === 1 && !g.title) { nav.append(navButton(members[0])); continue; }
    const box = el("div", "nav-group");
    box.dataset.group = g.id;
    const head = el("button", "nav-head");
    const label = el("span", "label");
    label.dataset.i18n = g.title;
    head.append(el("span", "ic", g.icon), label, el("span", "chev", "▸"));
    head.addEventListener("click", () => (FLY.matches ? fly(box, !box.classList.contains("fly")) : box.classList.toggle("open")));
    box.addEventListener("mouseenter", () => FLY.matches && fly(box, true));
    box.addEventListener("mouseleave", () => FLY.matches && (box._shut = setTimeout(() => fly(box, false), 250)));
    const sub = el("div", "nav-sub");
    sub.append(...members.map(navButton));
    box.append(head, sub);
    nav.append(box);
  }
  views.filter((v) => !placed.has(v.id)).forEach((v) => nav.append(navButton(v)));   // a page not in an area yet
  shortNav();
}

function shortNav() {
  const box = document.querySelector("#nav .nav-short");
  const ids = [...SHORT, ...pins().filter((id) => !SHORT.includes(id))].filter((id) => byId[id]);
  box.replaceChildren(...ids.map((id) => navButton(byId[id])), el("div", "nav-gap"), navButton(byId.advanced));
  box.lastChild.classList.add("nav-adv");
  i18n.apply(box);
  for (const b of box.querySelectorAll("button[data-view]")) {     // hidden as in the full menu (a user's, a plugin's)
    const twin = document.querySelector(`#nav .nav-full button[data-view="${b.dataset.view}"]`);
    if (twin?.classList.contains("hidden")) b.classList.add("hidden");
    b.classList.toggle("active", b.dataset.view === current);
  }
}
bus.on("pins", shortNav);

// with a mouse an area's pages open in a panel beside the menu, at the height of its head; leaving it closes after
// 250 ms, so the pointer can cross the gap
const FLY = matchMedia("(hover: hover) and (pointer: fine)");
function fly(box, on) {
  clearTimeout(box._shut);
  if (!on) { box.classList.remove("fly"); return; }
  document.querySelectorAll("#nav .nav-group.fly").forEach((g) => g !== box && fly(g, false));
  const sub = box.querySelector(".nav-sub");
  box.classList.add("fly");
  const top = box.querySelector(".nav-head").getBoundingClientRect().top;
  box.style.setProperty("--fly-top", `${Math.max(8, Math.min(top, innerHeight - sub.offsetHeight - 8))}px`);
}

// an area with no visible page (its plugins off) is hidden too
function tidyNav() {
  document.querySelectorAll("#nav .nav-group").forEach((g) => {
    g.classList.toggle("hidden", ![...g.querySelectorAll(".nav-sub button")].some((b) => !b.classList.contains("hidden")));
  });
}

function mountAll() {
  for (const v of views) {
    const section = el("section", "view hidden");
    section.id = `view-${v.id}`;
    $("views").append(section);
    v.mount(section, ctx);
  }
  for (const w of widgets) w.mount($(`slot-${w.slot}`), ctx);
  stackTables($("views"));                          // tables become cards on a phone
  i18n.apply(document);
}

function drawer(open) {
  document.body.classList.toggle("drawer-open", open);
  if (!open) document.querySelectorAll("#nav .nav-group.fly").forEach((g) => fly(g, false));
}

// the machine's pages hidden from a user (their API refuses them anyway)
function adminNav() {
  for (const id of adminOnly) if (!isAdmin) document.querySelectorAll(`#nav button[data-view="${id}"]`).forEach((b) => b.classList.add("hidden"));
  tidyNav();
}

const SHOWN = "aurora.view";                         // the page shown, for this tab only (a fresh open starts at home)

async function show(id) {
  if (!isAdmin && adminOnly.has(id)) id = "chat";
  current = id;
  try { sessionStorage.setItem(SHOWN, id); } catch { /* private mode: home after a reload */ }
  drawer(false);
  document.querySelectorAll("#nav button[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === id));
  document.querySelectorAll("#nav .nav-group").forEach((g) => {        // the shown page's area stays open
    if (g.querySelector(`button[data-view="${id}"]`)) g.classList.add("open");
  });
  document.querySelectorAll(".view").forEach((s) => s.classList.toggle("hidden", s.id !== `view-${id}`));
  bus.emit("view", { id });
  try { await byId[id].enter?.(); } catch (e) { if (e.status === 401) showLogin(true); else console.error(e); }
}

$("menu").addEventListener("click", () => drawer(!document.body.classList.contains("drawer-open")));
// log out: this device is forgotten (its key revoked); the next visit asks for the login again
$("logout").addEventListener("click", async () => {
  if (!confirm(i18n.t("nav.logout_q"))) return;
  try { await call("/v1/aurora/logout", { method: "POST" }); } catch { /* already out: the login anyway */ }
  drawer(false);
  showLogin(true);
});
$("scrim").addEventListener("click", () => drawer(false));
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") drawer(false); });
$("lang").addEventListener("change", async (ev) => {
  await i18n.load(ev.target.value);
  bus.emit("lang", { code: ev.target.value });
  if (current) show(current);
});

// a page that belongs to a plugin shows in the menu only while the plugin is on (and connected: "social" means
// any social platform); a page may also say whether it has something to show (visible(): the house's kinds of device);
// a failure leaves the menu whole
async function pluginNav() {
  let list;
  try { list = await call("/v1/aurora/plugins"); } catch { return; }
  const on = (p) => p.enabled && p.available;
  let firewalls = null;                                 // the security suite: once a firewall is connected
  if (isAdmin && views.some((v) => v.needs === "firewall")) {
    try { firewalls = (await call("/v1/aurora/security/firewalls")).receivers.length > 0; } catch { firewalls = false; }
  }
  for (const v of views) {
    if (!v.plugin && !v.needs) continue;
    let shown = v.needs === "firewall" ? !!firewalls
      : v.plugin === "social" ? list.some((p) => p.social && on(p)) : list.some((p) => p.name === v.plugin && on(p));
    if (shown && v.visible) shown = await v.visible().catch(() => false);   // a page with nothing to show stays out
    document.querySelectorAll(`#nav button[data-view="${v.id}"]`).forEach((b) => b.classList.toggle("hidden", !shown || (!isAdmin && adminOnly.has(v.id))));
  }
  tidyNav();
}
bus.on("plugins", pluginNav);
// a plugin switched on elsewhere (another device, its settings, a restart) shows its page without reopening the app
// (owner, 2026-10-12: «ho dovuto chiudere e riaprire la pwa per vedere la scheda»): when the app comes back to the
// front, and every 2 minutes while it is open
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") pluginNav(); });
setInterval(() => { if (document.visibilityState === "visible") pluginNav(); }, 120_000);
bus.on("show", ({ id }) => { if (byId[id]) show(id); });              // a page asked from inside another one

// who the assistant is for this user (name in the top bar, the voice's gender): their own settings
async function persona() {
  try {
    const m = await call("/v1/aurora/me");
    document.querySelector(".topbar .brand").textContent = m.assistant || "Aurora";
    document.title = m.assistant || "Aurora";
    voice.setGender(m.gender);
    isAdmin = m.admin !== false;
    adopt(m.prefs, m.name);                            // this person's style and pins, from any device
    applyStyle(currentStyle(isAdmin));                 // until chosen: Completo for the admin, Essenziale for a user
    shortNav();
    whoIs(m);
    adminNav();
    if (!isAdmin && adminOnly.has(current)) show("chat");
    firstSetup(m);
    return m;
  } catch { return null; /* the defaults stay */ }
}

// who is logged in, at the menu's foot beside the language and the logout (owner, 2026-10-07): their name for Aurora,
// the login and the role; a single-user install has no login, only the name
function whoIs(m) {
  const box = $("who");
  const login = m.mode === "multi" ? m.name : null;
  const person = m.person && m.person !== "Owner" ? m.person : null;
  if (!login && !person) { box.classList.add("hidden"); return; }
  const role = i18n.t(m.admin ? "nav.role_admin" : "nav.role_user");
  box.replaceChildren(
    Object.assign(document.createElement("span"), { className: "who-icon", textContent: m.admin ? "🛡️" : "👤" }),
    Object.assign(document.createElement("strong"), { textContent: person || login }),
    Object.assign(document.createElement("span"), { className: "muted",
      textContent: [login && login !== person ? login : null, login ? role : null].filter(Boolean).join(" · ") }));
  box.title = i18n.t("nav.who", { n: person || login });
  box.classList.remove("hidden");
}

// multi-user, the admin's first login (owner, 2026-10-05): in with the installer's API key, then a password and Google
// Authenticator before anything else — the Users page, with a note, until both are done
function firstSetup(m) {
  const todo = m.mode === "multi" && m.admin && m.name && (!m.has_password || (m.mfa && !m.totp_on));
  document.body.classList.toggle("first-setup", Boolean(todo));
  if (!todo) { document.getElementById("first-setup")?.remove(); return; }
  show("users");
  const note = document.getElementById("first-setup") || Object.assign(document.createElement("p"), { id: "first-setup", className: "warn first-setup-note" });
  note.textContent = i18n.t("users.first_setup");
  document.getElementById("view-users")?.prepend(note);
}
bus.on("me-changed", persona);

// back from a provider's sign-in (api/oauth): its code and state handed to the API, the address cleaned, the plugins
// page shown with the outcome
async function oauthBack() {
  const q = new URLSearchParams(location.search);
  const state = q.get("state") || "";
  if (!/^[a-z]+\.[\w-]+$/.test(state) || !(q.get("code") || q.get("error"))) return false;
  history.replaceState(null, "", location.pathname);
  let text;
  try {
    if (q.get("error")) throw new Error(q.get("error_description") || q.get("error"));
    const r = await call("/v1/aurora/oauth/finish", { method: "POST", body: JSON.stringify({ code: q.get("code"), state }) });
    text = i18n.t("oauth.done", { name: r.provider, days: r.days });
  } catch (e) { text = i18n.t("oauth.failed", { m: e.message }); }
  await show("plugins");
  alert(text);
  return true;
}

let started = false;
async function start() {
  showLogin(false);
  const m = await persona();
  pluginNav();
  if (!started) { for (const w of widgets) w.enter?.(); started = true; }
  const asked = new URLSearchParams(location.search).get("view");
  if (await oauthBack()) return;
  // after a reload — a new version of the WebUI (controllerchange), the phone freeing the page in the background — the
  // page that was open, not the home (owner, 17 Oct: «dopo qualche secondo… mi porta nella chat»)
  let kept = null;
  try { kept = sessionStorage.getItem(SHOWN); } catch { /* none */ }
  show(current || (asked && byId[asked] ? asked : kept && byId[kept] ? kept : styleHome(isAdmin)));
  if (m && !m.welcomed) welcome(m, show);              // the first run's five screens, once per person (107)
}

// ---- boot --------------------------------------------------------------------------------
applyTheme(currentTheme());                          // the colours first: no flash of another theme
applyStyle(currentStyle(true));
$("theme").addEventListener("click", () => themePicker({ style: currentStyle(isAdmin), onStyle: setStyle,
  onWelcome: async () => { const m = await call("/v1/aurora/me"); welcome(m, show); } }));
const lang = i18n.saved();
$("lang").value = lang;
await i18n.load(lang);
buildNav();
mountAll();
// Aurora may still be starting (a new installation loads its models; Caddy answers 502 meanwhile): say it and try
// again, never a page with only its background (the owner's colleague, 9 Oct: «resta ferma la foto… solo le stelle»)
async function boot() {
  let note = null;
  for (let attempt = 1; ; attempt++) {
    try {
      const ok = await authorized();
      note?.remove();
      if (ok) start(); else showLogin(true);
      return;
    } catch (e) {
      if (!note) { note = el("div", "boot-wait"); document.body.append(note); }
      note.textContent = i18n.t("boot.waiting", { n: attempt, m: e.status ? `HTTP ${e.status}` : e.message });
      await new Promise((r) => setTimeout(r, Math.min(2000 * attempt, 10000)));
    }
  }
}
await boot();
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* no offline shell */ });
  // a new version of the WebUI took over this page: load it once, so the page runs the new modules (C109)
  if (navigator.serviceWorker.controller) {
    let reloaded = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => { if (!reloaded) { reloaded = true; location.reload(); } });
  }
  navigator.serviceWorker.addEventListener("message", (ev) => {      // a notification was clicked
    if (ev.data?.type === "show" && byId[ev.data.view]) show(ev.data.view);
  });
}
