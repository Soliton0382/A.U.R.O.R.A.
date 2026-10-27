// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The showcase: which modules make up the WebUI, in menu order.
// Views get a page and a menu entry; widgets live in a slot (background, topbar).
// Adding a piece to the interface = one import and one line here.
import approvals from "./modules/approvals.js";
import autonomy from "./modules/autonomy.js";
import reports from "./modules/reports.js";
import alerts from "./modules/alerts.js";
import chat from "./modules/chat.js";
import diary from "./modules/diary.js";
import dreams from "./modules/dreams.js";
import accounts from "./modules/accounts.js";
import today from "./modules/today.js";
import advanced from "./modules/advanced.js";
import dj from "./modules/dj.js";
import memory from "./modules/memory.js";
import care from "./modules/care.js";
import calendar from "./modules/calendar.js";
import harvester from "./modules/harvester.js";
import notifications from "./modules/notifications.js";
import importDocs from "./modules/import.js";
import uploads from "./modules/uploads.js";
import metrics from "./modules/metrics.js";
import anonchat from "./modules/chat_anon.js";
import interpret from "./modules/interpret.js";
import phoneApp from "./modules/phone_app.js";
import plugins from "./modules/plugins.js";
import models from "./modules/models.js";
import guide from "./modules/guide.js";
import bugreport from "./modules/bugreport.js";
import projects from "./modules/projects.js";
import routines from "./modules/routines.js";
import runs from "./modules/runs.js";
import settings from "./modules/settings.js";
import security from "./modules/security.js";
import secDefence from "./modules/security_defence_page.js";
import secWatch from "./modules/security_watch_page.js";
import secOut from "./modules/security_out_page.js";
import secEgress from "./modules/security_egress_page.js";
import secTrace from "./modules/security_trace.js";
import secFirewalls from "./modules/security_firewalls.js";
import expenses from "./modules/expenses.js";
import consoles from "./modules/consoles.js";
import ups from "./modules/ups.js";
import astro from "./modules/astro.js";
import secEdge from "./modules/security_edge.js";
import ciso from "./modules/ciso.js";
import firewall from "./modules/firewall.js";
import aurorafw from "./modules/aurorafw.js";
import sky from "./modules/sky.js";
import brain from "./modules/brain.js";
import synapses from "./modules/synapses.js";
import social from "./modules/social.js";
import status from "./modules/status.js";
import updates from "./modules/updates.js";
import users from "./modules/users.js";
import usage from "./modules/usage.js";
import ideas from "./modules/ideas_page.js";
import https from "./modules/https.js";
import home from "./modules/home.js";
import { kinds as homeKinds } from "./modules/home.js";

// this installation's own pages (js/local, never published): added when present
let local = { views: [] };
try { local = await import("./local/index.js"); } catch { /* none on this installation */ }

export const views = [today, advanced, chat, anonchat, interpret, approvals, reports, secFirewalls, secEdge, security, ciso, firewall, aurorafw, secDefence, secWatch, secOut, secEgress, secTrace, autonomy, diary, dreams, memory, social, dj, care, expenses, astro, home, consoles, calendar, projects, routines, models, accounts, plugins, importDocs, uploads, harvester, synapses, runs, status, notifications, updates, users, usage, settings, https, ups, guide, bugreport, ideas, phoneApp];
views.push(...homeKinds, ...local.views);
export const widgets = [sky, alerts, metrics, brain];

// the side menu in areas (owner, 2026-10-05): an area of one page is a plain entry; the others open on a tap
// (phone) or on hover (PC); the area of the page shown stays open
export const groups = [
  { id: "today", views: ["today"] },
  { id: "chat", views: ["chat"] },
  { id: "anonchat", views: ["anonchat"] },              // 🕶️ the anonymous chat, beside the chat (owner, 20 Oct)
  { id: "interpret", views: ["interpret"] },            // 🌍 the interpreter, a page of its own (owner, 24 Oct)
  { id: "activity", icon: "🛎️", title: "nav.g.activity", views: ["approvals", "notifications", "reports", "runs"] },
  { id: "life", icon: "✨", title: "nav.g.life", views: ["calendar", "diary", "dreams", "memory", "social", "dj", "care", "expenses", "astro"] },
  // 🏠 the house (owner, 2026-10-12: «sotto casa avremmo tab casa e poi…»): Home Assistant's pages
  // 🖥️ the devices' own management pages, beside the house (owner, 28 Oct)
  { id: "home", icon: "🏠", title: "nav.g.home", views: ["home", "consoles", ...homeKinds.map((v) => v.id),
  ...local.views.filter((v) => v.group === "home").map((v) => v.id)] },
  { id: "work", icon: "🛠️", title: "nav.g.work", views: ["projects", "routines", "uploads"] },
  { id: "knowledge", icon: "📚", title: "nav.g.knowledge", views: ["import", "harvester", "synapses"] },
  // the security area (owner, 2026-10-08: «sotto menù specifici CISO, etc… separate e pulite»); defence, checks and
  // what was shared are tabs of 🚨 Incidenti e difesa, one entry (owner, 27 Oct: «sono già tutti accorpati… basta una
  // voce sola del menù»): their own ids still open the page on their tab
  { id: "security", icon: "🛡️", title: "nav.g.security", views: ["firewalls", "edge", "security", "ciso", "firewall", "aurorafw", "secegress", "sectrace"] },
  // ⚙️ the system, with how free Aurora is and the phone app (owner, 27 Oct: «app per il telefono lo metterei sotto la
  // voce sistema… anche autonomia»)
  { id: "system", icon: "⚙️", title: "nav.g.system", views: ["status", "autonomy", "models", "accounts", "plugins", "users", "usage", "settings", "https", "updates", "ups", "phoneapp"] },
  { id: "help", icon: "❓", title: "nav.g.help", views: ["guide", "bugreport", "ideas"] },
];
// the machine's pages (owner, 2026-10-06, multi-user): a user sees neither them in the menu nor their data (the API
// answers 403); their own preferences are in 👥 Users → My account, their plugins' settings in the plugins' cards
export const adminOnly = new Set(["firewalls", "edge", "security", "ciso", "firewall", "aurorafw", "secdefence", "secwatch", "secout", "secegress", "sectrace", "models", "harvester", "synapses", "status", "updates", "settings", "import", "https"]);
// a page may say it is the admin's alone (adminOnly: true), e.g. an installation's own pages about the house
for (const v of views) if (v.adminOnly) adminOnly.add(v.id);
