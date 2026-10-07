// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ❤️ Health: the dietitian's plans, the trainer's programmes, medical exams — sealed with the user's own key, read only
// by the local model, deleted for good when the user deletes them (owner, 2026-10-05).
import { call } from "../api.js";
import { clock, el, toBase64 } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { renderValues } from "./care_values.js";
import { renderDoctors } from "./care_doctor.js";
import { renderDiet } from "./care_diet.js";

const AREAS = ["diet", "training", "exams"];

export default {
  id: "care",
  icon: "❤️",
  title: "nav.care",
  plugin: "health",                   // in the menu only when that plugin is on

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="care.title"></h2><p class="muted" data-i18n="care.hint"></p>
      <div class="prj-tabs">${AREAS.map((a, i) => `<button type="button" class="cat-chip${i ? "" : " on"}" data-tab="${a}" data-i18n="care.${a}"></button>`).join("")}<button type="button" class="cat-chip" data-tab="doctor" data-i18n="care.doc.tab"></button></div>
      ${AREAS.map((a, i) => `<div class="care-tab" data-tab="${a}"${i ? " hidden" : ""}>
        <p class="muted" data-i18n="care.${a}_hint"></p>${a === "diet" ? '<div class="care-diet"></div>' : ""}
        <label class="dj-upload"><span data-i18n="care.upload"></span><input type="file" accept=".pdf,.txt,.md,.docx,image/*" multiple hidden></label>
        <span class="muted care-out"></span>
        <form class="import care-note"><input name="title" data-i18n-placeholder="care.note_title"><input name="text" required data-i18n-placeholder="care.note_text">
          <button type="submit" data-i18n="care.note_add"></button></form>
        ${a === "exams" ? '<div class="care-values"></div>' : ""}<div class="care-items"></div></div>`).join("")}
      <div class="care-tab" data-tab="doctor" hidden><p class="muted" data-i18n="care.doc.hint"></p><div class="care-doctors"></div></div>`;
    apply(root);
    root.querySelectorAll(".prj-tabs button").forEach((b) => b.addEventListener("click", () => {
      root.querySelectorAll(".prj-tabs button").forEach((x) => x.classList.toggle("on", x === b));
      root.querySelectorAll(".care-tab").forEach((p) => { p.hidden = p.dataset.tab !== b.dataset.tab; });
    }));
    this.tabs = {};
    this.values = root.querySelector(".care-values");
    this.doctors = root.querySelector(".care-doctors");
    this.diet = root.querySelector(".care-diet");
    root.querySelectorAll(".care-tab:not([data-tab=doctor])").forEach((tab) => {
      const area = tab.dataset.tab, out = tab.querySelector(".care-out");
      this.tabs[area] = tab.querySelector(".care-items");
      tab.querySelector("input[type=file]").addEventListener("change", async (ev) => {
        for (const f of ev.target.files) {
          out.textContent = t("care.sealing", { name: f.name });
          try { await call(`/v1/aurora/care/${area}`, { method: "POST", body: JSON.stringify({ name: f.name, data: await toBase64(f) }) }); }
          catch (e) { out.textContent = t("ev.error", { m: e.message }); return; }
        }
        out.textContent = "";
        ev.target.value = "";
        this.enter();
      });
      tab.querySelector(".care-note").addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const f = ev.target;
        try { await call(`/v1/aurora/care/${area}/note`, { method: "POST", body: JSON.stringify({ title: f.title.value, text: f.text.value }) }); f.reset(); }
        catch (e) { out.textContent = t("ev.error", { m: e.message }); }
        this.enter();
      });
    });
  },

  row(area, it) {
    const d = el("details", "report");
    d.append(el("summary", "", `${it.kind === "document" ? "📄" : "📝"} ${it.title} · ${clock(it.at)}`));
    const body = el("div");
    d.addEventListener("toggle", async () => {         // the text is unsealed only when opened
      if (!d.open || body.dataset.loaded) return;
      body.dataset.loaded = "1";
      try { body.replaceChildren(renderMarkdown((await call(`/v1/aurora/care/${area}/${it.id}`)).text)); }
      catch (e) { body.textContent = t("ev.error", { m: e.message }); }
    });
    const bar = el("div", "appr-actions");
    if (it.kind === "document") {
      const a = el("a", "", `⬇️ ${t("care.original")}`);
      a.href = `/v1/aurora/care/${area}/${it.id}/file`;
      bar.append(a);
    }
    if (area === "exams" && it.kind === "document") {     // read its values again with the local model
      const again = el("button", "", `📈 ${t("care.read_again")}`);
      again.addEventListener("click", async () => {
        await call(`/v1/aurora/health/values/read/${it.id}`, { method: "POST" });
        again.textContent = t("care.reading", { n: 1 });
        setTimeout(() => renderValues(this.values), 20000);
      });
      bar.append(again);
    }
    const del = el("button", "danger", `🗑️ ${t("care.delete")}`);
    del.addEventListener("click", async () => {
      if (!confirm(t("care.delete_q", { name: it.title }))) return;
      await call(`/v1/aurora/care/${area}/${it.id}`, { method: "DELETE" });
      this.enter();
    });
    bar.append(del);
    d.append(body, bar);
    return d;
  },

  async enter() {
    const { areas } = await call("/v1/aurora/care");
    for (const a of AREAS) {
      const list = areas[a] || [];
      this.tabs[a].replaceChildren(...(list.length ? list.map((it) => this.row(a, it)) : [el("p", "muted", t("care.none"))]));
    }
    renderValues(this.values);
    renderDoctors(this.doctors);
    renderDiet(this.diet);
  },
};
