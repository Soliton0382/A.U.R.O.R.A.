// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧠 Synapses (owner, 2026-10-05): the links between Aurora's knowledge of different domains — how many, the concepts
// they make (synapses of synapses, named by the local model), each link with its two passages, weight, uses, level;
// the owner strengthens a link, pins it (it never fades), wakes one that faded below 0.5, or deletes it.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { autonomySlot } from "./autonomy_box.js";
import { deductionsBox } from "./deductions_box.js";

export default {
  id: "synapses",
  icon: "🧠",
  title: "nav.synapses",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="syn.title"></h2><p class="muted" data-i18n="syn.hint"></p>
      <div class="syn-stats"></div>
      <h3 class="setting-cat" data-i18n="syn.concepts"></h3><p class="muted" data-i18n="syn.concepts_hint"></p><div class="syn-concepts"></div>
      <h3 class="setting-cat" data-i18n="syn.links"></h3>
      <div class="syn-filter">
        <select class="syn-state"><option value="1" data-i18n="syn.awake"></option><option value="0" data-i18n="syn.asleep"></option></select>
        <select class="syn-level"><option value="0" data-i18n="syn.all_levels"></option><option value="1" data-i18n="syn.level1"></option><option value="2" data-i18n="syn.level2"></option></select>
        <input class="syn-domain" data-i18n-placeholder="syn.domain">
        <button class="syn-go" data-i18n="syn.show"></button>
      </div>
      <div class="syn-list"></div><div class="syn-more"></div>`;
    root.querySelector("h2").after(autonomySlot("shadow", "train"));   // how free Aurora is, here (owner, 2026-10-08)
    this.ded = deductionsBox();                                        // 💡 the deductions first (roadmap 77)
    root.querySelector(".syn-stats").after(this.ded);
    apply(root);
    this.q = (s) => root.querySelector(s);
    this.q(".syn-go").addEventListener("click", () => this.links(0));
    this.offset = 0;
  },

  async stats() {
    const s = await call("/v1/aurora/synapses");
    const lv = Object.entries(s.levels || {}).map(([k, n]) => `${t("syn.level")} ${k}: ${n}`).join(" · ");
    const run = el("button", "", `▶ ${t("syn.l2_now")}`);
    run.addEventListener("click", async () => {
      const r = await call("/v1/aurora/synapses/level2", { method: "POST" }).catch((e) => ({ error: e.message }));
      run.textContent = r.started ? t("syn.l2_started") : (r.error || t("syn.l2_busy"));
    });
    this.q(".syn-stats").replaceChildren(
      el("p", "", t("syn.stats", { n: s.links, u: s.used, d: s.today, a: s.asleep, p: s.pinned, c: s.concepts })),
      el("p", "muted", lv + (s.growing ? ` · ${t("status.syn_growing")}` : "")),
      el("p", "muted", s.pairs.map((x) => `${x.a} ↔ ${x.b} ${x.n}`).join(" · ")), run);
  },

  async concepts() {
    const list = await call("/v1/aurora/synapses/concepts").catch(() => []);
    this.q(".syn-concepts").replaceChildren(...(list.length ? list.map((c) => {
      const d = el("details", "report");
      d.append(el("summary", "", `💡 ${c.name || t("syn.unnamed")} · ${c.domains.join(", ")} · ${t("syn.n_passages", { n: c.members.length })}`),
        ...c.passages.map((p) => el("p", "", `[${p.domain}] ${p.title}`)));
      return d;
    }) : [el("p", "muted", t("syn.no_concepts"))]));
  },

  card(l) {
    const c = el("details", "report syn-link");
    c.append(el("summary", "", `${l.pinned ? "📌 " : ""}${l.level === 2 ? "⬆️ " : ""}[${l.da}] ${l.pa.title || "—"}  ↔  [${l.db}] ${l.pb.title || "—"} · ${Number(l.w).toFixed(2)}`));
    c.append(el("p", "muted", `${t(`syn.kind.${l.kind}`)} · ${t("syn.level")} ${l.level} · ${t("syn.uses", { n: l.uses })} · ${clock(l.made)}`),
      el("p", "", `[${l.da}] ${l.pa.text}`), el("p", "", `[${l.db}] ${l.pb.text}`));
    const w = el("input");
    w.type = "number"; w.min = "0"; w.max = "1"; w.step = "0.05"; w.value = Number(l.w).toFixed(2);
    const save = el("button", "", t("syn.save_w"));
    const pin = el("button", "", l.pinned ? t("syn.unpin") : `📌 ${t("syn.pin")}`);
    const wake = el("button", "approve", `↩️ ${t("syn.wake")}`);
    const del = el("button", "danger", "🗑️");
    const out = el("span", "muted");
    const edit = async (body) => {
      try { await call("/v1/aurora/synapses/link", { method: "PUT", body: JSON.stringify({ a: l.a, b: l.b, ...body }) }); out.textContent = "✅"; this.links(this.offset); this.stats(); }
      catch (e) { out.textContent = t("ev.error", { m: e.message }); }
    };
    save.addEventListener("click", () => edit({ w: Number(w.value) }));
    pin.addEventListener("click", () => edit({ pinned: !l.pinned }));
    wake.addEventListener("click", () => edit({ active: true }));
    del.addEventListener("click", () => { if (confirm(t("syn.delete_q"))) edit({ delete: true }); });
    const row = el("div", "appr-actions");
    row.append(w, save, pin, ...(l.active ? [] : [wake]), del, out);
    c.append(row);
    return c;
  },

  async links(offset) {
    this.offset = offset;
    const qs = new URLSearchParams({ active: this.q(".syn-state").value === "1", level: this.q(".syn-level").value,
      domain: this.q(".syn-domain").value.trim(), limit: 60, offset });
    const { links } = await call(`/v1/aurora/synapses/list?${qs}`);
    this.q(".syn-list").replaceChildren(...(links.length ? links.map((l) => this.card(l)) : [el("p", "muted", t("syn.none"))]));
    const more = el("button", "", t("syn.more"));
    more.addEventListener("click", () => this.links(offset + 60));
    this.q(".syn-more").replaceChildren(...(links.length === 60 ? [more] : []));
  },

  async enter() {
    await Promise.all([this.stats(), this.ded.load(), this.concepts(), this.links(0)]);
  },
};
