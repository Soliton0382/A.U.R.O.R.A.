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
import dj from "./modules/dj.js";
import memory from "./modules/memory.js";
import care from "./modules/care.js";
import harvester from "./modules/harvester.js";
import notifications from "./modules/notifications.js";
import importDocs from "./modules/import.js";
import uploads from "./modules/uploads.js";
import metrics from "./modules/metrics.js";
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
import ciso from "./modules/ciso.js";
import firewall from "./modules/firewall.js";
import sky from "./modules/sky.js";
import synapses from "./modules/synapses.js";
import social from "./modules/social.js";
import status from "./modules/status.js";
import updates from "./modules/updates.js";
import users from "./modules/users.js";
import ideas from "./modules/ideas_page.js";

export const views = [chat, approvals, reports, security, ciso, firewall, secDefence, secWatch, secOut, autonomy, diary, memory, social, dj, care, projects, routines, models, plugins, importDocs, uploads, harvester, synapses, runs, status, notifications, updates, users, settings, guide, bugreport, ideas];
export const widgets = [sky, alerts, metrics];

// the side menu in areas (owner, 2026-10-05): an area of one page is a plain entry; the others open on a tap
// (phone) or on hover (PC); the area of the page shown stays open
export const groups = [
  { id: "chat", views: ["chat"] },
  { id: "activity", icon: "🛎️", title: "nav.g.activity", views: ["approvals", "notifications", "reports", "runs"] },
  { id: "life", icon: "✨", title: "nav.g.life", views: ["diary", "memory", "social", "dj", "care"] },
  { id: "work", icon: "🛠️", title: "nav.g.work", views: ["projects", "routines", "uploads"] },
  { id: "knowledge", icon: "📚", title: "nav.g.knowledge", views: ["import", "harvester", "synapses"] },
  // the security area (owner, 2026-10-08: «sotto menù specifici CISO, etc… separate e pulite»)
  { id: "security", icon: "🛡️", title: "nav.g.security", views: ["security", "ciso", "firewall", "secdefence", "secwatch", "secout"] },
  { id: "autonomy", views: ["autonomy"] },
  { id: "system", icon: "⚙️", title: "nav.g.system", views: ["status", "models", "plugins", "users", "settings", "updates"] },
  { id: "help", icon: "❓", title: "nav.g.help", views: ["guide", "bugreport", "ideas"] },
];
// the machine's pages (owner, 2026-10-06, multi-user): a user sees neither them in the menu nor their data (the API
// answers 403); their own preferences are in 👥 Users → My account, their plugins' settings in the plugins' cards
export const adminOnly = new Set(["security", "ciso", "firewall", "secdefence", "secwatch", "secout", "models", "harvester", "synapses", "status", "updates", "settings", "import"]);
