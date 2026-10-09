// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧩 A local reasoner of one's own (roadmap 73, aurora/mdl_custom.py): a Hugging Face repository → its GGUF files →
// one checked before downloading (its header read from the first megabytes: family, experts, context, fits or not) →
// downloaded with its SHA-256 → tried with one question → used; the model before always one click away.
import { call, followRun } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const FIT = { whole: "✅", experts_in_ram: "🟡", no: "⛔" };

export async function renderCustom(box) {
  box.replaceChildren();
  let st;
  try { st = await call("/v1/aurora/models/custom"); } catch { return; }
  const p = st.current.profile;
  box.append(el("p", "", t("mc.current", { m: st.current.model, f: p.family, tpl: p.template, v: st.current.mmproj ? "👁️" : "—" })));
  const bar = el("div", "settings-actions");
  if (st.previous) {
    const back = el("button", "", `↩️ ${t("mc.revert", { m: st.previous.AURORA_LLM_MODEL.split("/").pop() })}`);
    back.addEventListener("click", () => act(back, "/v1/aurora/models/custom/revert", {}, box));
    bar.append(back);
  }
  for (const m of st.installed) {
    if (m === st.current.model) continue;
    const use = el("button", "", `▶️ ${t("mc.use", { m: m.split("/").pop() })}`);
    use.addEventListener("click", () => act(use, "/v1/aurora/models/custom/switch", { model: m, mmproj: "" }, box));
    bar.append(use);
  }
  if (bar.children.length) box.append(bar);

  const form = el("div", "ev");
  const repo = el("input");
  repo.placeholder = "unsloth/Mistral-Small-3.2-24B-Instruct-2506-GGUF";
  const look = el("button", "", `🔎 ${t("mc.inspect")}`);
  form.append(repo, look);
  const out = el("div");
  box.append(el("p", "muted", t("mc.hint")), form, out);
  look.addEventListener("click", async () => {
    out.replaceChildren(el("p", "muted", t("mc.looking")));
    let info;
    try { info = await call(`/v1/aurora/models/custom/inspect?repo=${encodeURIComponent(repo.value.trim())}`); }
    catch (e) { out.replaceChildren(el("p", "error", e.message)); return; }
    out.replaceChildren(el("p", "muted", t("mc.repo", { r: info.repo, rev: info.revision.slice(0, 10), l: info.licence || "?" })));
    const proj = el("select");
    proj.append(new Option(t("mc.noproj"), ""));
    for (const pj of info.projectors) proj.append(new Option(`👁️ ${pj.file} (${pj.size_gb} GB)`, pj.file));
    if (info.projectors.length) proj.selectedIndex = 1;
    out.append(el("label", "plug-field", t("mc.projector")), proj);
    for (const f of info.files) {
      const row = el("div", "ev");
      const name = el("strong", "", `${f.file} · ${f.size_gb} GB${f.parts.length > 1 ? ` (${f.parts.length} parti)` : ""}`);
      const check = el("button", "", t("mc.check"));
      const res = el("div", "muted");
      row.append(name, check, res);
      out.append(row);
      check.addEventListener("click", async () => {
        check.disabled = true;
        res.textContent = t("mc.reading");
        let c;
        try {
          c = await call(`/v1/aurora/models/custom/check?repo=${encodeURIComponent(info.repo)}&revision=${info.revision}`
            + `&file=${encodeURIComponent(f.file)}&size_gb=${f.size_gb}`);
        } catch (e) { res.textContent = e.message; check.disabled = false; return; }
        const pr = c.profile;
        res.textContent = `${FIT[c.fit.verdict]} ${c.fit.why} · ${c.architecture}, ${c.moe}, ctx ${c.context} · `
          + t("mc.profile", { f: pr.family, tpl: pr.template, tools: pr.tools });
        if (c.fit.verdict === "no") return;
        const get = el("button", "approve", `⬇️ ${t("mc.download")}`);
        const log = el("div", "muted");
        row.append(get, log);
        get.addEventListener("click", async () => {
          get.disabled = true;
          const files = [...f.parts, ...(proj.value ? [proj.value] : [])];
          try {
            const { run_id: id } = await call("/v1/aurora/models/custom/download", { method: "POST",
              body: JSON.stringify({ repo: info.repo, revision: info.revision, files }) });
            await followRun(id, (e) => {
              if (e.event === "custom.download") log.textContent = `⬇️ ${e.payload.file} (${e.payload.size_gb} GB)…`;
              if (e.event === "custom.verified") log.textContent = `✅ SHA-256 ${e.payload.file}`;
              if (e.event === "answer.final") {
                const r = JSON.parse(e.payload.text);
                log.textContent = r.ok ? t("mc.downloaded") : `⛔ ${r.error}`;
                if (r.ok) {
                  const use = el("button", "approve", `▶️ ${t("mc.try")}`);
                  use.addEventListener("click", () => act(use, "/v1/aurora/models/custom/switch",
                    { model: r.paths[0], mmproj: proj.value ? r.paths[r.paths.length - 1] : "" }, box));
                  row.append(use);
                }
              }
            });
          } catch (e2) { log.textContent = e2.message; get.disabled = false; }
        });
      });
    }
  });
}

async function act(btn, path, body, box) {
  btn.disabled = true;
  const note = el("p", "muted", t("mc.switching"));
  btn.after(note);
  try {
    const r = await call(path, { method: "POST", body: JSON.stringify(body) });
    note.textContent = t("mc.switched", { m: r.model.split("/").pop(), a: r.answer, s: r.seconds }) + (r.note ? ` ⚠️ ${r.note}` : "");
    setTimeout(() => renderCustom(box), 4000);
  } catch (e) { note.textContent = `⛔ ${e.message}`; btn.disabled = false; }
}
