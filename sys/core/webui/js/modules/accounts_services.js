// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ➕ Services of one's own, OpenAI-compatible (owner, 2026-10-15: «ollama oppure altri modelli api come kimi… dargli un
// nome e il tasto più per aggiungere diversi custom; i custom si possono rimuovere, i default no»): a suggestion fills
// name and address, «Prova» asks the service its models before it is saved, the admin adds and removes them.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

export function renderServices(d, onChange) {
  const box = el("section", "report acc-section");
  box.append(el("h3", "", t("svc.title")), el("p", "muted", t("svc.hint")));
  const mine = d.providers.filter((p) => p.custom);
  if (!mine.length) box.append(el("p", "muted", t("svc.empty")));
  for (const p of mine) {
    const row = el("div", "acc-row");
    row.append(el("span", "", `${p.label} · ${p.base}`), el("span", p.ready ? "ok" : "muted", p.ready ? `✅ ${t("acc.ready")}` : t("acc.not_set")));
    if (d.admin) {
      const del = el("button", "danger", `🗑️ ${t("acc.remove")}`);
      del.addEventListener("click", async () => {
        if (!confirm(t("svc.remove_q", { name: p.label }))) return;
        try { await call(`/v1/aurora/accounts/services/${p.id}`, { method: "DELETE" }); onChange(); } catch (e) { alert(e.message); }
      });
      row.append(del);
    }
    box.append(row);
  }
  if (!d.admin) { box.append(el("p", "muted", t("svc.admin"))); return box; }

  const open = el("button", "", `➕ ${t("svc.add")}`);
  const form = el("div", "acc-form svc-form");
  form.hidden = true;
  open.addEventListener("click", () => { form.hidden = !form.hidden; });
  const preset = el("select");
  preset.append(new Option(t("svc.preset"), ""));
  for (const [i, p] of d.presets.entries()) preset.append(new Option(p.name, String(i)));
  const name = el("input");
  name.placeholder = t("svc.name");
  const base = el("input");
  base.placeholder = "https://… /v1";
  base.inputMode = "url";
  const key = el("input");
  key.type = "password";
  key.autocomplete = "off";
  key.placeholder = t("svc.key");
  const out = el("small", "muted svc-out", t("svc.try_first"));
  preset.addEventListener("change", () => {
    const p = d.presets[Number(preset.value)];
    if (!p) return;
    name.value = p.name;
    base.value = p.base;
    key.placeholder = t(p.key ? "svc.key_needed" : "svc.key");
  });
  const tryIt = el("button", "", `🔌 ${t("svc.try")}`);
  tryIt.addEventListener("click", async () => {
    out.className = "muted svc-out";
    out.textContent = t("acc.checking");
    try {
      const r = await call("/v1/aurora/accounts/services/try", { method: "POST", body: JSON.stringify({ base: base.value, key: key.value }) });
      out.className = "ok svc-out";
      out.textContent = t("svc.works", { n: r.count }) + (r.models.length ? `: ${r.models.slice(0, 6).join(", ")}${r.count > 6 ? "…" : ""}` : "");
    } catch (e) { out.className = "error svc-out"; out.textContent = e.message; }
  });
  const add = el("button", "approve", t("acc.add_go"));
  add.addEventListener("click", async () => {
    try {
      await call("/v1/aurora/accounts/services", { method: "POST", body: JSON.stringify({ name: name.value, base: base.value, key: key.value }) });
      onChange();
    } catch (e) { out.className = "error svc-out"; out.textContent = e.message; }
  });
  form.append(preset, name, base, key, tryIt, add, out);
  box.append(open, form);
  return box;
}
