// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧠 My models (ROADMAP 106; owner, 14 Oct: «ogni utente si configura le parti dei modelli che preferisce con il proprio
// account cloud… se l'admin lo permette»): each step the admin's choice, or the user's own — the local model or a
// provider their account reaches (api/accounts /v1/aurora/me/models, mdl_user_roles). The admin uses the Models page.
import { call } from "../api.js";
import { el } from "../dom.js";
import { lang, t } from "../i18n.js";

const said = (a) => (a.provider === "local" ? t("acc.models_local") : `${a.provider}${a.model ? ` · ${a.model}` : ""}`);

export async function myModels(again) {
  const box = el("section", "report acc-section");
  box.append(el("h3", "", `🧠 ${t("acc.models")}`));
  let d;
  try { d = await call("/v1/aurora/me/models"); } catch (e) { box.append(el("p", "error", e.message)); return box; }
  if (d.admin) { box.append(el("p", "muted", t("acc.models_admin"))); return box; }
  if (!d.allowed) { box.append(el("p", "muted", t("acc.models_shared"))); return box; }
  box.append(el("p", "muted", t("acc.models_hint")));
  const code = lang.slice(0, 2);
  const rows = [];
  for (const r of d.roles) {
    const row = el("div", "acc-row acc-model");
    const pick = el("select");
    const house = el("option", "", `🏠 ${t("acc.models_house")}: ${said(r.house)}`);
    house.value = "";
    pick.append(house, ...d.providers.map((p) => { const o = el("option", "", p.label); o.value = p.id; return o; }));
    pick.value = r.mine ? r.provider : "";
    const model = el("input");
    Object.assign(model, { placeholder: t("acc.models_model"), value: r.mine ? r.model : "" });
    const list = el("datalist");
    list.id = `acc-models-${r.id}`;
    model.setAttribute("list", list.id);
    const show = async () => {                           // a provider's own list, read with the user's key
      model.hidden = !pick.value || pick.value === "local";
      if (model.hidden) return;
      try {
        const m = await call(`/v1/aurora/me/models/${pick.value}/list`);
        list.replaceChildren(...m.models.map((x) => { const o = el("option"); o.value = x; return o; }));
      } catch { list.replaceChildren(); }
    };
    pick.addEventListener("change", () => { model.value = ""; show(); });
    show();
    const label = el("span");
    label.append(el("strong", "", r[code] || r.en), el("small", "muted", ` — ${t("acc.models_sees")}: ${r.sees}`));
    row.append(label, pick, model, list);
    rows.push({ r, pick, model });
    box.append(row);
  }
  const out = el("span", "muted");
  const save = el("button", "", t("settings.save"));
  save.addEventListener("click", async () => {
    const roles = Object.fromEntries(rows.map(({ r, pick, model }) =>
      [r.id, pick.value ? { provider: pick.value, model: pick.value === "local" ? "" : model.value.trim() } : null]));
    try { await call("/v1/aurora/me/models", { method: "PUT", body: JSON.stringify({ roles }) }); out.textContent = t("acc.models_saved"); again(); }
    catch (e) { out.textContent = t("ev.error", { m: e.message }); }
  });
  const reset = el("button", "", `↩ ${t("acc.models_reset")}`);
  reset.addEventListener("click", async () => {
    if (!confirm(t("acc.models_reset_confirm"))) return;
    try { await call("/v1/aurora/me/models", { method: "PUT", body: JSON.stringify({ reset: true }) }); again(); }
    catch (e) { out.textContent = t("ev.error", { m: e.message }); }
  });
  const bar = el("div", "settings-actions");
  bar.append(save, " ", reset, " ", out);
  box.append(bar);
  return box;
}
