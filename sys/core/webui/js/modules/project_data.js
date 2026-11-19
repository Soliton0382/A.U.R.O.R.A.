// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📥 The owner's data brought into a project (C697, positive provenance; owner, 20 Nov: «vai aggiungi»): a .csv or
// .npz chosen here is recorded as the owner's from the bytes received, before the file is written
// (POST /v1/aurora/projects/{name}/data) — the only tables on which the discovery engine (N147) may say DISCOVERED.
// Files written from the project's terminal or by Aurora's agents never count as the owner's.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const MAX = 64 * 1024 * 1024;                     // prj_provenance.MAX_BYTES (the server says it again if smaller)

function base64(buf) {                            // chunked: String.fromCharCode on a whole large buffer overflows
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

export function dataView(name) {
  const box = el("div", "prj-data");
  const form = el("form", "prj-term-line");
  const file = el("input");
  file.type = "file";
  file.accept = ".csv,.npz";
  const path = el("input");
  path.placeholder = t("prj.data_path_ph");
  const go = el("button", "", t("prj.data_send"));
  go.type = "submit";
  form.append(file, path, go);
  const state = el("p", "muted");
  box.append(el("p", "muted", t("prj.data_note")), form, state);

  file.addEventListener("change", () => {
    const f = file.files[0];
    if (f && !path.value) path.value = `data/${f.name}`;
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = file.files[0];
    if (!f) { file.focus(); return; }
    if (!/\.(csv|npz)$/i.test(f.name)) { state.textContent = t("prj.data_kind"); return; }
    if (f.size > MAX) { state.textContent = t("prj.data_big"); return; }
    go.disabled = true;
    state.textContent = t("prj.data_working");
    try {
      const out = await call(`/v1/aurora/projects/${encodeURIComponent(name)}/data`, { method: "POST",
        body: JSON.stringify({ path: path.value || `data/${f.name}`, data: base64(await f.arrayBuffer()) }) });
      state.textContent = t("prj.data_done", { path: out.path, kb: Math.max(1, Math.round(out.bytes / 1024)),
        sha: String(out.sha256 || "").slice(0, 12) }) + (out.warning ? ` ⚠️ ${out.warning}` : "");
      file.value = "";
      path.value = "";
    } catch (err) {
      state.textContent = err.message;
    } finally {
      go.disabled = false;
    }
  });
  return box;
}
