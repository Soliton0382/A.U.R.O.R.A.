// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The showcase: which modules make up the WebUI, in menu order.
// Views get a page and a menu entry; widgets live in a slot (background, topbar).
// Adding a piece to the interface = one import and one line here.
import approvals from "./modules/approvals.js";
import reports from "./modules/reports.js";
import alerts from "./modules/alerts.js";
import chat from "./modules/chat.js";
import diary from "./modules/diary.js";
import dj from "./modules/dj.js";
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
import sky from "./modules/sky.js";
import social from "./modules/social.js";
import status from "./modules/status.js";
import updates from "./modules/updates.js";
import users from "./modules/users.js";

export const views = [chat, approvals, reports, security, diary, social, dj, care, projects, routines, models, plugins, importDocs, uploads, harvester, runs, status, notifications, updates, users, settings, guide, bugreport];
export const widgets = [sky, alerts, metrics];

// the side menu in areas (owner, 2026-10-05): an area of one page is a plain entry; the others open on a tap
// (phone) or on hover (PC); the area of the page shown stays open
export const groups = [
  { id: "chat", views: ["chat"] },
  { id: "activity", icon: "🛎️", title: "nav.g.activity", views: ["approvals", "notifications", "reports", "runs"] },
  { id: "life", icon: "✨", title: "nav.g.life", views: ["diary", "social", "dj", "care"] },
  { id: "work", icon: "🛠️", title: "nav.g.work", views: ["projects", "routines", "uploads"] },
  { id: "knowledge", icon: "📚", title: "nav.g.knowledge", views: ["import", "harvester"] },
  { id: "security", views: ["security"] },
  { id: "system", icon: "⚙️", title: "nav.g.system", views: ["status", "models", "plugins", "users", "settings", "updates"] },
  { id: "help", icon: "❓", title: "nav.g.help", views: ["guide", "bugreport"] },
];
