// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🏗️ A project's plan, carried by Aurora herself (ROADMAP 97, prj_plan): the owner writes the goal, Aurora proposes
// the steps (each with the command that proves it), the owner changes them and starts the plan. In idle time she does
// the next step; the step's command decides whether it is done. Blocked after 3 failures; 🤝 waits for «go on».
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { t } from "../i18n.js";

const MARK = { open: "⬜", done: "✅", blocked: "⛔" };

// the steps as lines «title | command»: what the owner reads and writes
const toLines = (steps) => steps.map((s) => `${s.title} | ${s.test}`).join("\n");
const fromLines = (text) => text.split("\n").map((l) => l.split("|")).filter((p) => p.length >= 2)
  .map((p) => ({ title: p[0].trim(), test: p.slice(1).join("|").trim() })).filter((s) => s.title && s.test);

export function planView(name) {
  const box = el("div", "prj-plan");
  const fail = (e) => box.replaceChildren(el("p", "error", t("ev.error", { m: e.message })));

  const empty = () => {
    const goal = el("textarea");
    goal.rows = 4;
    goal.placeholder = t("plan.goal_ph");
    const go = el("button", "approve", t("plan.draft"));
    go.addEventListener("click", async () => {
      if (!goal.value.trim()) return;
      go.disabled = true;
      go.textContent = t("plan.drafting");
      try { show(await call(`/v1/aurora/projects/${name}/plan`, { method: "POST", body: JSON.stringify({ goal: goal.value }) })); }
      catch (e) { fail(e); }
    });
    box.replaceChildren(el("h4", "", t("plan.title")), el("p", "muted", t("plan.none")), goal, go);
  };

  const change = async (body) => {
    try { show(await call(`/v1/aurora/projects/${name}/plan`, { method: "PUT", body: JSON.stringify(body) })); }
    catch (e) { fail(e); }
  };

  const show = (plan) => {
    const head = el("div", "ev");
    const state = plan.active ? (plan.waiting ? t("plan.waiting") : t("plan.running")) : t("plan.paused");
    head.append(el("strong", "", state));
    const toggle = el("button", plan.active ? "" : "approve", plan.active ? t("plan.pause") : t("plan.start"));
    toggle.addEventListener("click", () => change({ active: !plan.active }));
    head.append(toggle);
    if (plan.waiting) {
      const on = el("button", "approve", t("plan.go_on"));
      on.addEventListener("click", () => change({ go_on: true }));
      head.append(on);
    }
    const steps = plan.steps.map((s, i) => {
      const row = el("details", "report");
      row.append(el("summary", "", `${MARK[s.status] || "•"} ${i + 1}. ${s.title}${s.tries ? ` · ${t("plan.tries", { n: s.tries })}` : ""}`),
        el("code", "", s.test));
      for (const r of (s.runs || []).slice().reverse()) {
        row.append(el("p", "muted", `${clock(r.at)} · exit ${r.exit}${r.seconds != null ? ` · ${r.seconds} s` : ""}`),
          el("pre", "prj-code", (r.report ? `${r.report}\n\n` : "") + (r.tail || "")));
      }
      if (s.status === "blocked") {
        const again = el("button", "approve", t("plan.retry"));
        again.addEventListener("click", () => change({ retry: i }));
        row.append(again);
      }
      return row;
    });
    const edit = el("details");
    const lines = el("textarea", "", toLines(plan.steps));
    lines.rows = Math.min(12, plan.steps.length + 2);
    const save = el("button", "", t("plan.save"));
    save.addEventListener("click", () => {
      const s = fromLines(lines.value);
      if (s.length) change({ steps: s.map((x) => ({ ...x, ...(plan.steps.find((o) => o.title === x.title && o.test === x.test) || {}) })) });
    });
    edit.append(el("summary", "", t("plan.edit")), el("p", "muted", t("plan.edit_hint")), lines, save);
    box.replaceChildren(el("h4", "", t("plan.title")), el("p", "", plan.goal),
      el("p", "muted", t(`auto.what.projects.${plan.level}`)), head, ...steps, edit);
  };

  call(`/v1/aurora/projects/${name}/plan`).then(show).catch((e) => (/no plan/.test(e.message) ? empty() : fail(e)));
  return box;
}
