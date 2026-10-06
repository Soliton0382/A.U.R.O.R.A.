// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Report a bug: the owner describes it, chooses the conversations involved and how many hours of logs; Aurora packs
// what is needed with private data masked, shows what is inside and what was masked, then the zip and a GitHub issue.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderIdeas } from "./ideas.js";

export default {
  id: "bugreport",
  icon: "🐞",
  title: "nav.bugreport",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `
      <div class="prj-tabs"><button type="button" class="cat-chip on" data-tab="bug" data-i18n="bug.tab"></button><button type="button" class="cat-chip" data-tab="idea" data-i18n="idea.tab"></button></div>
      <div class="bug-tab" data-tab="idea" hidden><h2 data-i18n="idea.title"></h2><p class="muted" data-i18n="idea.hint"></p><div class="ideas"></div></div>
      <div class="bug-tab" data-tab="bug">
      <h2 data-i18n="bug.title"></h2><p class="muted" data-i18n="bug.hint"></p>
      <label data-i18n="bug.what"></label><textarea class="bug-what" rows="4"></textarea>
      <label data-i18n="bug.steps"></label><textarea class="bug-steps" rows="3"></textarea>
      <label data-i18n="bug.expected"></label><textarea class="bug-expected" rows="2"></textarea>
      <label data-i18n="bug.runs"></label><div class="bug-runs"></div>
      <div class="ev"><label data-i18n="bug.hours"></label>
        <select class="bug-hours"><option value="2">2 h</option><option value="6" selected>6 h</option><option value="24">24 h</option><option value="72">72 h</option></select>
        <button class="bug-make" data-i18n="bug.make"></button></div>
      <div class="bug-out"></div>
      <h3 class="setting-cat" data-i18n="bug.past"></h3><div class="bug-past"></div></div>`;
    apply(root);
    root.querySelectorAll(".prj-tabs button").forEach((b) => b.addEventListener("click", () => {
      root.querySelectorAll(".prj-tabs button").forEach((x) => x.classList.toggle("on", x === b));
      root.querySelectorAll(".bug-tab").forEach((p) => { p.hidden = p.dataset.tab !== b.dataset.tab; });
      if (b.dataset.tab === "idea") renderIdeas(root.querySelector(".ideas"));
    }));
    this.q = (s) => root.querySelector(s);
    this.q(".bug-make").addEventListener("click", () => this.make());
  },

  async enter() {
    const runs = await call("/v1/aurora/runs").catch(() => []);
    this.q(".bug-runs").replaceChildren(...runs.slice(0, 12).map((r) => {
      const row = el("label", "ev bug-run");
      const cb = el("input");
      cb.type = "checkbox";
      cb.value = r.id;
      row.append(cb, el("span", "muted", clock(r.started)), el("span", "", r.question.slice(0, 90)));
      return row;
    }));
    this.past();
  },

  async past() {
    const list = await call("/v1/aurora/bugreports").catch(() => []);
    this.q(".bug-past").replaceChildren(...(list.length ? list.slice(0, 10).map((r) => {
      const a = el("a", "chip", `🐞 ${r.name} · ${Math.round(r.bytes / 1024)} KB`);
      a.href = r.url;
      a.setAttribute("download", r.name);
      return a;
    }) : [el("p", "muted", t("bug.none"))]));
  },

  async make() {
    const out = this.q(".bug-out");
    const btn = this.q(".bug-make");
    btn.disabled = true;
    out.replaceChildren(el("p", "muted", t("bug.working")));
    try {
      const r = await call("/v1/aurora/bugreport", { method: "POST", body: JSON.stringify({
        description: this.q(".bug-what").value, steps: this.q(".bug-steps").value, expected: this.q(".bug-expected").value,
        hours: Number(this.q(".bug-hours").value),
        run_ids: [...this.q(".bug-runs").querySelectorAll("input:checked")].map((c) => c.value) }) });
      const masked = Object.entries(r.masked).map(([k, n]) => `${k} ${n}`).join(", ") || t("md.nothing");
      const dl = el("a", "chip", `⬇️ ${r.name} · ${Math.round(r.bytes / 1024)} KB`);
      dl.href = r.url;
      dl.setAttribute("download", r.name);
      out.replaceChildren(el("p", "", t("bug.done", { n: r.files.length })), el("p", "muted", r.files.join(" · ")),
        el("p", "", t("bug.masked", { what: masked })), el("p", "muted", t("bug.check")), dl);
      if (r.issue_url) {
        const gh = el("a", "chip", t("bug.issue"));
        gh.href = r.issue_url;
        gh.target = "_blank";
        gh.rel = "noopener";
        out.append(gh);
      }
      this.past();
    } catch (e) {
      out.replaceChildren(el("p", "error", t("ev.error", { m: e.message })));
    } finally {
      btn.disabled = false;
    }
  },
};
