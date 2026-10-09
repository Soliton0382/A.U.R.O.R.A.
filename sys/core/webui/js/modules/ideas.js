// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💡 Ideas to improve Aurora (owner, 2026-10-06): ticks for the areas, the kind, a priority, a title and notes — a
// request written in a form the developer can take into consideration; each one moves new → considered → planned →
// done (or no, with why). Kept in the user's own state (sys_ideas), never in the repository.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { t } from "../i18n.js";

function choice(name, values, prefix, selected) {
  const s = el("select");
  s.name = name;
  for (const v of values) { const o = el("option", "", t(`${prefix}.${v}`)); o.value = v; o.selected = v === selected; s.append(o); }
  return s;
}

export async function renderIdeas(root) {
  let data;
  try { data = await call("/v1/aurora/ideas"); } catch (e) { root.replaceChildren(el("p", "muted", t("ev.error", { m: e.message }))); return; }
  const form = el("div", "idea-form");
  const ticks = el("div", "rt-plugins");
  for (const a of data.areas) {
    const l = el("label", "rt-day"); const cb = el("input"); cb.type = "checkbox"; cb.value = a;
    l.append(cb, el("span", "", t(`idea.area.${a}`))); ticks.append(l);
  }
  const kind = choice("kind", data.kinds, "idea.kind", "improve"), prio = choice("priority", data.priorities, "idea.prio", "normal");
  const title = el("input"); title.placeholder = t("idea.title_ph");
  const text = el("textarea"); text.rows = 5; text.placeholder = t("idea.text_ph");
  const out = el("span", "muted");
  const save = el("button", "primary", `💡 ${t("idea.save")}`);
  save.addEventListener("click", async () => {
    try {
      await call("/v1/aurora/ideas", { method: "POST", body: JSON.stringify({ areas: [...ticks.querySelectorAll("input:checked")].map((i) => i.value),
        kind: kind.value, priority: prio.value, title: title.value, text: text.value }) });
      renderIdeas(root);
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
  });
  const row = el("div", "ev");
  row.append(kind, prio);
  const bar = el("div", "appr-actions");
  bar.append(save, out);
  form.append(el("p", "muted", t("idea.areas")), ticks, row, title, text, bar);
  const list = data.ideas.map((it) => {
    const d = el("details", "report");
    d.append(el("summary", "", `${{ new: "🆕", considered: "🤔", planned: "🗓️", done: "✅", no: "🚫" }[it.state]} ${it.title} · ${t(`idea.kind.${it.kind}`)} · ${clock(it.at)}`));
    d.append(el("p", "muted", it.areas.map((a) => t(`idea.area.${a}`)).join(", ")), el("p", "", it.text));
    if (it.note) d.append(el("p", "muted", `📝 ${it.note}`));
    const state = choice("state", data.states, "idea.state", it.state);
    state.addEventListener("change", async () => {
      await call(`/v1/aurora/ideas/${it.id}`, { method: "PUT", body: JSON.stringify({ state: state.value }) });
      renderIdeas(root);
    });
    const copy = el("button", "", `📋 ${t("idea.copy")}`);
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(it.markdown); copy.textContent = `✅ ${t("idea.copied")}`; } catch { copy.textContent = "—"; }
    });
    // to the developers as a GitHub issue, masked; GitHub shows it before it is sent (a GitHub account is needed)
    const gh = el("button", "", `🐙 ${t("idea.github")}`);
    gh.addEventListener("click", async () => {
      try {
        const r = await call(`/v1/aurora/ideas/${it.id}/issue`, { method: "POST" });
        if (!r.issue_url) { gh.textContent = `⚠️ ${t("bug.leaks", { k: (r.leaks || []).join(", ") })}`; return; }
        window.open(r.issue_url, "_blank", "noopener");
      } catch (e) { gh.textContent = `⚠️ ${e.message.slice(0, 80)}`; }
    });
    const b = el("div", "appr-actions");
    b.append(state, copy, gh);
    d.append(b);
    return d;
  });
  root.replaceChildren(form, el("h3", "setting-cat", t("idea.list", { n: data.ideas.length })), ...list);
}
