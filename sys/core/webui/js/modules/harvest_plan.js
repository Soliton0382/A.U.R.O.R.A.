// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📐 What is left to harvest and the room it takes (kno_harvest_plan, once a day): arXiv's newest id against the
// vault's, and per domain taken · available · left · the measured weight of a document · the projected room
// (owner, 2026-10-13: «quanto ancora manca per avere il vault completo e una proiezione dell'eventuale spazio»).
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { lang, t } from "../i18n.js";

const n = (x) => (x == null ? "—" : Number(x).toLocaleString(lang.startsWith("it") ? "it-IT" : "en-US"));
const size = (b) => (b == null ? "—" : b >= 1e12 ? `${(b / 1e12).toFixed(1)} TB` : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB`
  : b >= 1e6 ? `${(b / 1e6).toFixed(0)} MB` : `${Math.round(b / 1e3)} kB`);

export function planBlock(plan, names, refresh) {
  const box = el("section", "harvest-plan");
  const head = el("div", "appr-actions");
  const again = el("button", "", t("hplan.again"));
  again.addEventListener("click", async () => {
    again.disabled = true;
    try { await call("/v1/aurora/harvester/plan", { method: "POST" }); again.textContent = t("hplan.asked"); } catch { again.disabled = false; }
    setTimeout(refresh, 1500);
  });
  head.append(el("span", "muted", plan ? t("hplan.at", { at: clock(new Date(plan.at * 1000).toISOString()) }) : t("hplan.never")), again);
  box.append(head);
  if (!plan) return box;
  const a = plan.arxiv_newest, v = plan.arxiv_newest_taken;
  const even = a && v && (v >= a);
  box.append(el("p", "", `📚 ${t("hplan.arxiv", { a: a || "—", v: v || "—" })} ${a && v ? (even ? `✅ ${t("hplan.even")}` : `⏳ ${t("hplan.behind")}`) : ""}`));
  const table = el("table", "table");
  const tr = el("tr");
  for (const k of ["domain", "taken", "available", "left", "weight", "room"]) tr.append(el("th", "", t(`hplan.${k}`)));
  table.append(tr);
  let room = 0, unknown = 0;
  for (const d of plan.domains) {
    const r = el("tr");
    const left = d.done ? 0 : d.left;
    if (d.projected_bytes != null && !d.done) room += d.projected_bytes; else if (!d.done) unknown += 1;
    const avail = d.available == null ? t("hplan.not_measured") : `${n(d.available)}${d.unknown.length ? ` + ${t("hplan.unknown", { list: d.unknown.join(", ") })}` : ""}`;
    for (const v2 of [names[d.domain] || d.domain, n(d.taken), avail, d.done ? `✅ ${t("harvest.complete")}` : n(left),
      d.per_doc ? size(d.per_doc) : "—", d.done ? "0" : size(d.projected_bytes)]) {
      const c = el("td", "", v2);
      r.append(c);
    }
    table.append(r);
  }
  const wrap = el("div", "table-wrap");
  wrap.append(table);
  box.append(wrap, el("p", "", `💾 ${t("hplan.total", { room: size(room) })}${unknown ? ` · ${t("hplan.total_unknown", { n: unknown })}` : ""}`),
    el("p", "muted", t("hplan.note")));
  return box;
}
