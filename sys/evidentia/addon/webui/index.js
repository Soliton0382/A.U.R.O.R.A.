// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🕵️ Evidentia's pages, an add-on (sys/evidentia): loaded by js/modules.js only when the add-on is installed
// (GET /v1/aurora/addons). An area of its own with its pages as blocks: archives, server, case files, the dedicated
// chat, the network, agents, routines. The archive's text never passes through Aurora's memory.
import { extend } from "/static/js/i18n.js";
import evidentia from "./evidentia.js";
import { agentsPage, archivesPage, routinesPage, serverPage } from "./evidentia_pages.js";
import evdCases from "./evidentia_cases.js";
import evdNet from "./evidentia_net.js";
import evdMoney from "./evidentia_money.js";

extend(await (await fetch("/static/addons/evidentia/strings.json")).json());
export const views = [archivesPage, serverPage, evdCases, evidentia, evdNet, evdMoney, agentsPage, routinesPage];
export const groups = [{ id: "evidentia", icon: "🕵️", title: "nav.g.evidentia",
  views: ["evd_archives", "evd_server", "evd_cases", "evidentia", "evd_net", "evd_money", "evd_agents", "evd_routines"] }];
