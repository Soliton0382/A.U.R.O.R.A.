// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ⚙️ A few settings in a box (the same .env values as in Settings): a yes/no as a checkbox, a choice as a menu, a
// number as a number, a secret never shown. One code for a plugin's window and for a page that keeps its own settings
// (owner, 2026-10-16: «se hanno una pagina tanto vale avere le configurazioni lì dentro»).
import { call } from "../api.js";
import { el } from "../dom.js";
import { lang, t } from "../i18n.js";
import { restartPrompt } from "../restart.js";
import { openWizard } from "./wizard.js";

// keys: the settings; title: the box's heading; choices: {key: [{id, name}]} for a key chosen from a list;
// after(form): more inside the box (the weather's town); onSaved(r, restarted): after a save; guide: {title, intro,
// links} — the plugin's own guide, the first step of its 🧙 guided window
export async function settingsForm(keys, { title = "", choices = {}, after = null, onSaved = null, guide = null } = {}) {
  const code = lang.slice(0, 2);
  const all = (await call("/v1/aurora/settings")).settings;
  const specs = all.filter((s) => keys.includes(s.key));
  const form = el("div", "plug-settings");
  const head = el("div", "plug-settings-head");
  head.append(el("h4", "", title || `⚙️ ${t("plug.settings")}`));
  if (specs.length) {                                    // the same settings, one a step, with their explanation
    const wz = el("button", "wz-open", `🧙 ${t("wz.open")}`);
    wz.type = "button";
    wz.addEventListener("click", () => openWizard(specs, { guide: guide || { title }, choices,
      onSaved: async (r, restarted) => {
        form.replaceWith(await settingsForm(keys, { title, choices, after, onSaved, guide }));
        if (onSaved) onSaved(r, restarted);
      } }));
    head.append(wz);
  }
  form.append(head);
  for (const s of specs) {
    const row = el("label", "plug-field");
    const list = choices[s.key];
    // yes/no as a checkbox, a choice as a menu, a number as a number (owner, 2026-10-04)
    const on = (v) => ["1", "true", "yes", "on"].includes(String(v).toLowerCase());
    if (s.type === "bool") {
      const box = el("input");
      box.type = "checkbox";
      box.checked = on(s.value);
      box.dataset.key = s.key;
      box.dataset.bool = "1";
      box.dataset.orig = on(s.value) ? "1" : "0";
      const r = el("label", "plug-field plug-check");
      r.append(box, el("span", "", s[code] || s.en));
      form.append(r);
      continue;
    }
    const input = el(list || s.type === "enum" ? "select" : "input");
    if (!list && s.type === "enum") for (const c of s.choices) input.append(el("option", "", c));
    if (s.type === "int") { input.type = "number"; if (s.min !== undefined) input.min = s.min; if (s.max !== undefined) input.max = s.max; }
    if (list) {
      for (const d of [{ id: "auto", name: t("plug.device.auto") }, ...list]) {
        const o = el("option", "", d.id === "auto" ? d.name : `${d.name} — ${d.id}`);
        o.value = d.id;
        input.append(o);
      }
      if (s.value && ![...input.options].some((o) => o.value === s.value)) input.append(el("option", "", s.value));
    }
    input.value = s.secret ? "" : s.value;
    input.placeholder = s.secret ? (s.value ? t("plug.secret.set") : t("plug.secret.empty")) : (s.recommended || "");
    if (s.secret) input.type = "password";
    input.dataset.key = s.key;
    input.dataset.secret = s.secret ? "1" : "";
    input.dataset.orig = s.secret ? "" : s.value;
    row.append(el("code", "", s.key), input, el("span", "muted", s[code] || s.en));
    form.append(row);
  }
  if (after) after(form);
  const save = el("button", "approve", `💾 ${t("settings.save")}`);
  const out = el("span", "muted");
  save.addEventListener("click", async () => {
    const changes = {};
    form.querySelectorAll("[data-key]").forEach((i) => {
      if (i.dataset.bool) { const v = i.checked ? "1" : "0"; if (v !== i.dataset.orig) changes[i.dataset.key] = v; return; }
      if (i.dataset.secret ? i.value !== "" : i.value !== i.dataset.orig) changes[i.dataset.key] = i.value;
    });
    if (!Object.keys(changes).length) { out.textContent = t("settings.none"); return; }
    try {
      const r = await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify(changes) });
      out.textContent = t("settings.saved", { keys: r.changed.join(", "), services: r.restart.join(", ") || "—" });
      const restarted = await restartPrompt(r.restart);
      if (onSaved) onSaved(r, restarted);
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
  });
  const actions = el("div", "appr-actions");
  actions.append(save, out);
  form.append(actions);
  return form;
}
