// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Recent runs (answers, acquisitions, autonomic tasks), each can be replayed in the chat.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";

export default {
  id: "runs",
  icon: "🗂️",
  title: "nav.runs",

  mount(root, ctx) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="runs.title"></h2><div class="list"></div>
      <h3 class="setting-cat" data-i18n="runs.notes"></h3><div class="notes log"></div>`;
    apply(root);
    this.list = root.querySelector(".list");
    this.notes = root.querySelector(".notes");
    this.ctx = ctx;
  },

  async enter() {
    const runs = await call("/v1/aurora/runs");
    const table = el("table", "table");
    const head = el("tr");
    for (const k of ["runs.when", "runs.question", "runs.origin", "runs.events", ""]) head.append(el("th", "", k && t(k)));
    table.append(head);
    for (const r of runs) {
      const tr = el("tr");
      const replay = el("button", "", t("runs.replay"));
      replay.addEventListener("click", () => this.ctx.replay(r));
      tr.append(el("td", "", clock(r.started)), el("td", "", r.question), el("td", "", r.origin),
        el("td", "", String(r.events)), el("td"));
      tr.lastChild.append(replay);
      table.append(tr);
    }
    this.list.replaceChildren(table);
    // what the services reported (harvester, owner decisions...), newest first
    const notes = (await call("/v1/aurora/activity?limit=200")).filter((a) => !a.event.startsWith("run.")).reverse();
    this.notes.replaceChildren(...(notes.length ? notes.slice(0, 80).map((a) => {
      const p = a.payload || {};
      const what = p.title || p.reason || (p.papers !== undefined ? `${p.papers} ${t("runs.papers")}` : "") || "";
      return el("div", "ev", `${clock(a.ts)} · ${a.source} · ${a.event}${what ? " · " + what : ""}`);
    }) : [el("p", "muted", t("runs.nonotes"))]));
  },
};
