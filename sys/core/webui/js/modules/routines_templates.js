// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧰 Ready-made sets of agents and routines (owner, 2026-10-08: «template di agenti e routine basati sulla mia
// configurazione e su configurazioni per diversi utilizzi come social, cyber security…»): each set says what it would
// add, what is already there and what misses a plugin; «Applica» adds only what is missing. «📸» keeps the user's own
// routines as a set the other users can apply (the admin's machine routines are never offered to them).
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const STATE = { new: "➕", present: "✅", missing: "🚫" };

export async function templatesSection(onChange) {
  const box = el("div", "rt-templates");
  const save = el("button", "", `📸 ${t("rt.tpl_save")}`);
  save.addEventListener("click", async () => {
    const title = prompt(t("rt.tpl_save_q"));
    if (!title) return;
    try { await call("/v1/aurora/routines/templates", { method: "POST", body: JSON.stringify({ title }) }); fill(); }
    catch (e) { alert(e.message); }
  });
  const list = el("div", "rt-tpl-list");
  box.append(el("p", "muted", t("rt.tpl_sets_hint")), list, save);

  async function fill() {
    let packs;
    try { packs = await call("/v1/aurora/routines/templates"); } catch (e) { list.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
    list.replaceChildren(...packs.map((p) => {
      const d = el("details", "report");
      const fresh = p.items.filter((i) => i.state === "new").length;
      d.append(el("summary", "", `${p.icon} ${p.title} · ${t("rt.tpl_count", { n: fresh, all: p.items.length })}`));
      if (p.description) d.append(el("p", "muted", p.description));
      if (p.saved_by) d.append(el("p", "muted", `📸 ${t("rt.tpl_saved_by", { who: p.saved_by })}`));
      const ul = el("ul");
      for (const i of p.items) {
        ul.append(el("li", i.state === "missing" ? "muted" : "",
          `${STATE[i.state]} ${i.title}${i.state === "missing" ? ` — ${t("rt.tpl_missing", { p: i.missing.join(", ") })}` : ""}`));
      }
      d.append(ul);
      const row = el("div", "appr-actions");
      const go = el("button", "approve", `✔ ${t("rt.tpl_apply", { n: fresh })}`);
      go.disabled = !fresh;
      const out = el("span", "muted");
      go.addEventListener("click", async () => {
        go.disabled = true;
        try {
          const r = await call(`/v1/aurora/routines/templates/${p.id}/apply`, { method: "POST" });
          out.textContent = t("rt.tpl_done", { n: r.created.length });
          await onChange();
          fill();
        } catch (e) { out.textContent = t("ev.error", { m: e.message }); go.disabled = false; }
      });
      row.append(go);
      if (p.mine) {
        const del = el("button", "danger", `🗑️ ${t("rt.remove")}`);
        del.addEventListener("click", async () => {
          if (!confirm(t("rt.tpl_delete_q", { name: p.title }))) return;
          try { await call(`/v1/aurora/routines/templates/${p.id}`, { method: "DELETE" }); fill(); } catch (e) { alert(e.message); }
        });
        row.append(del);
      }
      row.append(out);
      d.append(row);
      return d;
    }));
  }
  await fill();
  return box;
}
