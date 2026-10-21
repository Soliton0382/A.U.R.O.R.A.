// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// How Aurora handles a project (prj_policy): 🔒 the local model only or ☁️ the cloud (masked); 🚫 never published.
// Chosen when it is made (owner, 2026-10-21: «uno crea un progetto decidendo come deve essere gestito»), changed here.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

// the two choices, as form fields (the creation form sends them with the project)
export function policyFields(models = "cloud", publish = true) {
  const m = el("select");
  m.name = "models";
  m.title = t("prj.models_hint");
  for (const k of ["cloud", "local"]) m.append(new Option(t(`prj.models_${k}`), k));
  m.value = models;
  const p = el("select");
  p.name = "publish";
  p.title = t("prj.publish_hint");
  for (const k of ["yes", "no"]) p.append(new Option(t(`prj.publish_${k}`), k));
  p.value = publish ? "yes" : "no";
  return [m, p];
}

// in the project's page: the same two, saved as they change
export async function policyBox(name) {
  const box = el("span", "prj-policy");
  let pol = { models: "cloud", publish: true };
  try { pol = await call(`/v1/aurora/projects/${name}/policy`); } catch { /* shown with the default */ }
  const [m, p] = policyFields(pol.models, pol.publish);
  const save = async () => {
    try {
      await call(`/v1/aurora/projects/${name}/policy`, { method: "PUT",
        body: JSON.stringify({ models: m.value, publish: p.value === "yes" }) });
    } catch (e) { box.title = t("ev.error", { m: e.message }); }
  };
  m.addEventListener("change", save);
  p.addEventListener("change", save);
  box.append(m, p);
  return box;
}
