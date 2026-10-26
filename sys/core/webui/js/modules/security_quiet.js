// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Security → 🚨 Incidents: the owner's verdicts put to use (sec_quiet; owner, 2026-10-27: «do i feedback su quello che
// ricevo» and nothing changed). A kind of alert judged false again and again is proposed for quiet, with its counts;
// the owner says yes or no. A quiet kind is still kept and listed, as low, with no notification; one click wakes it.
import { call } from "../api.js";
import { el } from "../dom.js";
import * as i18n from "../i18n.js";

export const quiet = {
  async loadQuiet() {
    const box = this.root.querySelector(".sec-quiet");
    let q;
    try { q = await call(`/v1/aurora/incidents/quiet?lang=${i18n.lang.startsWith("it") ? "it" : "en"}`); } catch { box.replaceChildren(); return; }
    const set = async (pattern, state) => {
      try { await call("/v1/aurora/incidents/quiet", { method: "POST", body: JSON.stringify({ pattern, state }) }); }
      catch (e) { alert(e.message); }
      this.loadQuiet();
    };
    const rows = [];
    for (const p of q.proposals) {
      const r = el("div", "report sec-quiet-row");
      const yes = el("button", "approve", `🔇 ${i18n.t("sec.quiet.yes")}`);
      const no = el("button", "", i18n.t("sec.quiet.no"));
      yes.addEventListener("click", () => set(p.pattern, "quiet"));
      no.addEventListener("click", () => set(p.pattern, "declined"));
      r.append(el("p", "", i18n.t("sec.quiet.ask", { what: p.label, fa: p.false_alarm, right: p.right, n: p.judged })), yes, no);
      rows.push(r);
    }
    if (q.quiet.length) {
      const d = el("details", "report");
      d.append(el("summary", "", i18n.t("sec.quiet.list", { n: q.quiet.length })));
      for (const p of q.quiet) {
        const r = el("div", "appr-actions");
        const wake = el("button", "", `🔔 ${i18n.t("sec.quiet.wake")}`);
        wake.addEventListener("click", () => set(p.pattern, "awake"));
        r.append(el("span", "", `🔇 ${p.label} · ${i18n.t("sec.quiet.counts", { fa: p.fa, right: p.right })}`), wake);
        d.append(r);
      }
      rows.push(d);
    }
    const rule = { fa: q.rule.false_alarm, share: Math.round(q.rule.right_share * 100), days: q.rule.days };
    if (rows.length) rows.unshift(el("p", "muted", i18n.t(q.alone ? "sec.quiet.hint_alone" : "sec.quiet.hint", rule)));
    box.replaceChildren(...rows);
  },
};
