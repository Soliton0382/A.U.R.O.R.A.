// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💡 Deductions (roadmap 77, owner 2026-10-10: «come un colpo di genio… il guardare le cose da un'altra prospettiva»):
// bridges Aurora found between distant fields, both sides verified on their sources; the owner says which ones are a
// real flash — that judgement is the measure — and turns one into a PDF among the documents.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { t } from "../i18n.js";

export function deductionsBox() {
  const box = el("div", "ded-box");
  const list = el("div", "ded-list");
  const find = el("button", "", `▶ ${t("ded.find")}`);
  find.addEventListener("click", async () => {
    find.disabled = true;
    const r = await call("/v1/aurora/deductions/round", { method: "POST" }).catch((e) => ({ error: e.message }));
    find.textContent = r.run_id ? t("ded.started") : (r.error || "…");
  });
  box.append(el("h3", "setting-cat", t("ded.title")), el("p", "muted", t("ded.hint")), find, list);
  const load = async () => {
    const items = await call("/v1/aurora/deductions").catch(() => []);
    list.replaceChildren(...(items.length ? items.map(card) : [el("p", "muted", t("ded.none"))]));
  };
  const card = (d) => {
    const c = el("details", "report ded" + (d.verdict ? ` ded-${d.verdict}` : ""));
    const mark = d.verdict === "flash" ? "💡 " : d.verdict === "no" ? "✗ " : "";
    c.append(el("summary", "", `${mark}${d.text}`));
    c.append(el("p", "", `${t("ded.perspective")}: ${d.perspective}`), el("p", "muted", `${t("ded.test")}: ${d.test}`),
      el("p", "muted", `${d.da}: ${d.a_title} ↔ ${d.db}: ${d.b_title}`),
      el("p", "muted", `${t("ded.score")} ${Number(d.score).toFixed(2)} · ${clock(new Date(d.made * 1000).toISOString())}`));
    const out = el("span", "muted");
    const act = el("div", "settings-actions");
    for (const [v, label] of [["flash", t("ded.flash")], ["no", t("ded.no")], ["", t("ded.clear")]]) {
      const b = el("button", "", label);
      b.addEventListener("click", async () => {
        try { await call(`/v1/aurora/deductions/${d.id}`, { method: "PUT", body: JSON.stringify({ verdict: v }) }); load(); }
        catch (e) { out.textContent = e.message; }
      });
      act.append(b);
    }
    const pdf = el("button", "", `📄 ${t("ded.pdf")}`);
    pdf.addEventListener("click", async () => {
      pdf.disabled = true;
      try { const r = await call(`/v1/aurora/deductions/${d.id}/pdf`, { method: "POST" }); out.textContent = `✅ ${r.name}`; }
      catch (e) { out.textContent = e.message; pdf.disabled = false; }
    });
    act.append(pdf, out);
    c.append(act);
    return c;
  };
  box.load = load;
  return box;
}
