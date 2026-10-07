// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The harvester, steered by the owner: on/off, a round now, which domains to harvest (off, a round, until
// exhausted) with their sources and progress, a batch of arXiv papers; progress follows live.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { restartPrompt } from "../restart.js";
import { autonomySlot } from "./autonomy_box.js";

const when = (s) => (s ? clock(new Date(s * 1000).toISOString()) : "—");

export default {
  id: "harvester",
  icon: "🌾",
  title: "nav.harvester",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `
      <h2 data-i18n="harvest.title"></h2>
      <p class="muted" data-i18n="harvest.hint"></p>
      <div class="harvest-state"></div>
      <div class="harvest-actions"><button class="toggle"></button> <button class="now" data-i18n="harvest.now"></button>
        <span class="result muted"></span></div>
      <h3 class="setting-cat" data-i18n="harvest.langs"></h3>
      <p class="muted" data-i18n="harvest.langs_hint"></p><div class="harvest-langs"></div>
      <h3 class="setting-cat" data-i18n="harvest.domains"></h3>
      <p class="muted" data-i18n="harvest.domains_hint"></p>
      <div class="harvest-domains"></div>
      <h3 class="setting-cat" data-i18n="harvest.batch"></h3>
      <p class="muted" data-i18n="harvest.batch_hint"></p>
      <textarea class="batch-items" rows="6"></textarea>
      <div><button class="send" data-i18n="harvest.send"></button></div>
      <div class="batch-progress"></div>`;
    root.querySelector("h2").after(autonomySlot("knowledge", "study"));   // how free Aurora is, here (owner, 2026-10-08)
    apply(root);
    this.stateBox = root.querySelector(".harvest-state");
    this.domainsBox = root.querySelector(".harvest-domains");
    this.langsBox = root.querySelector(".harvest-langs");
    this.progress = root.querySelector(".batch-progress");
    this.out = root.querySelector(".result");
    this.toggle = root.querySelector(".toggle");
    const items = root.querySelector(".batch-items");
    items.placeholder = "2104.09864\nhttps://arxiv.org/abs/1706.03762\narXiv:2310.06825";
    root.querySelector(".now").addEventListener("click", async () => {
      await call("/v1/aurora/harvester/now", { method: "POST", body: "{}" });
      this.out.textContent = t("harvest.queued");
      this.refresh();
    });
    this.toggle.addEventListener("click", async () => {
      const on = !this.enabled;
      const r = await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify({ AURORA_HARVEST_ENABLED: on ? "1" : "0" }) });
      await restartPrompt(r.restart);
      this.refresh();
    });
    root.querySelector(".send").addEventListener("click", async () => {
      try {
        const r = await call("/v1/aurora/harvester/batch", { method: "POST", body: JSON.stringify({ items: items.value }) });
        this.out.textContent = t("harvest.batch_queued", { n: r.ids.length })
          + (r.unsupported.length ? ` · ${t("harvest.unsupported", { list: r.unsupported.join(", ") })}` : "");
        items.value = "";
      } catch (e) { this.out.textContent = t("harvest.none"); }
      this.refresh();
    });
  },

  async refresh() {
    const s = await call("/v1/aurora/harvester");
    this.enabled = s.enabled_setting;
    this.toggle.textContent = t(s.enabled_setting ? "harvest.turn_off" : "harvest.turn_on");
    const box = this.stateBox;
    box.replaceChildren();
    const row = (label, value) => { const r = el("div", "ev"); r.append(el("strong", "", label), el("span", "", value)); box.append(r); };
    row(t("harvest.state"), `${t(`harvest.st.${s.state}`)}${s.pending ? ` · ${t("harvest.pending", { n: s.pending })}` : ""}`);
    row(t("harvest.auto"), t(s.enabled_setting ? "harvest.auto_on" : "harvest.auto_off", { h: s.interval_h, n: s.per_category }));
    row(t("harvest.last"), when(s.last_round));
    if (s.next_round && s.enabled_setting) row(t("harvest.next"), when(s.next_round));
    row(t("harvest.seen"), String(s.papers_seen));
    this.renderDomains(s.domains || []);
    const b = s.batch;
    this.progress.replaceChildren();
    if (b) {
      const done = b.items.filter((i) => i.state === "done").length;
      this.progress.append(el("div", "muted", t("harvest.batch_line", { done, total: b.total, at: when(b.started) })
        + (b.finished ? ` · ${t("harvest.finished", { at: when(b.finished) })}` : "")));
      for (const i of b.items) {
        const r = el("div", "ev");
        r.append(el("span", `pill ${i.state === "done" ? "ok" : /failed|not found/.test(i.state) ? "bad" : "warn"}`, i.state),
          el("code", "", i.id), el("span", "", i.title || ""), el("span", "muted", i.domain ? `→ ${i.domain}` : ""));
        if (i.state === "done") r.append(el("span", "muted", t("harvest.chunks", { n: i.written })));
        this.progress.append(r);
      }
    }
  },

  renderDomains(domains) {
    const box = this.domainsBox;
    if (box.contains(document.activeElement)) return;      // never redraw under the owner's hand
    box.replaceChildren();
    for (const d of domains) {
      const r = el("div", "ev");
      const sel = el("select", "");
      sel.style.width = "auto";
      for (const m of ["off", "round", "exhaust"]) {
        const o = el("option", "", t(`harvest.mode.${m}`));
        o.value = m;
        o.selected = d.mode === m;
        sel.append(o);
      }
      sel.disabled = !d.sources.length;
      sel.addEventListener("change", async () => {
        const out = await call("/v1/aurora/harvester/domains", { method: "PUT", body: JSON.stringify({ [d.id]: sel.value }) });
        sel.blur();
        this.out.textContent = this.enabled || sel.value === "off" ? t("harvest.saved") : t("harvest.saved_off");
        this.renderDomains(out.domains);
      });
      const state = !d.sources.length ? el("span", "muted", t("harvest.no_source"))
        : d.done ? el("span", "pill ok", t("harvest.complete"))
        : el("span", "muted", t("harvest.taken", { n: d.taken }));
      r.append(el("strong", "", lang.startsWith("it") ? d.it : d.en), sel,
        el("span", "muted", [...new Set(d.sources)].join(" · ")), state);
      box.append(r);
    }
  },

  // Wikipedia in other languages (owner, 2026-10-05): English always; the installation's language by default; a tick more
  async langs() {
    let st;
    try { st = await call("/v1/aurora/settings"); } catch { return; }
    const cur = (st.settings.find((x) => x.key === "AURORA_HARVEST_LANGS")?.value || "").split(",").map((x) => x.trim()).filter(Boolean);
    const lang = (st.settings.find((x) => x.key === "AURORA_LANG_DEFAULT")?.value || "it_IT").slice(0, 2);
    const chosen = new Set(cur.length ? cur : [lang]);
    this.langsBox.replaceChildren(...["en", "it", "fr", "de", "es", "pt"].map((l) => {
      const lbl = el("label", "cat-chip");
      const box = el("input");
      box.type = "checkbox";
      box.checked = l === "en" || chosen.has(l);
      box.disabled = l === "en";                       // the models' language: always
      box.addEventListener("change", async () => {
        const list = [...this.langsBox.querySelectorAll("input")].filter((b) => b.checked && !b.disabled).map((b) => b.value);
        await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify({ AURORA_HARVEST_LANGS: list.join(",") }) });
        await call("/v1/aurora/services/restart", { method: "POST", body: JSON.stringify({ services: ["aurora-harvester"] }) }).catch(() => null);
        this.refresh();
      });
      box.value = l;
      lbl.append(box, el("span", "", ` ${t(`harvest.lang.${l}`)}`));
      return lbl;
    }));
  },

  async enter() {
    this.langs();
    await this.refresh();
    clearInterval(this.timer);
    this.timer = setInterval(() => { if (!document.hidden && document.querySelector("#view-harvester:not(.hidden)")) this.refresh().catch(() => {}); }, 5000);
  },
};
