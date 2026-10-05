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

export const views = [chat, approvals, reports, security, diary, social, projects, routines, models, plugins, importDocs, uploads, harvester, runs, status, notifications, updates, users, settings, guide, bugreport];
export const widgets = [sky, alerts, metrics];
