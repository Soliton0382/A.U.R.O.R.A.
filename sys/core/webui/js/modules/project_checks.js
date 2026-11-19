// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔒🧑‍⚖️ Predictions and reviews of a project (ROADMAP N142): the frozen predictions as Aurora keeps them (open /
// closed, passed / failed / void, integrity) and the severe referee's reviews with their verdict line; a review can be
// started by hand. Read from GET /prereg and /reviews (api/projects_conduct.py); nothing here writes the ledger.
// 📐 N143: the last formal checks (GET /proof, Lean in a read-only cage) and a .lean file checked by hand (POST /proof).
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

const MODE = { off: "checks.mode_off", warn: "checks.mode_warn", strict: "checks.mode_strict" };
const cell = (v) => String(v ?? "").replace(/\|/g, "/").replace(/\n/g, " ");

function ledger(d) {
  const out = [el("h4", "", t("checks.prereg")), el("p", "muted", t(MODE[d.mode] || "checks.mode_warn"))];
  if (!d.intact) out.push(el("p", "error", t("checks.tampered")));
  if (!d.entries.length) return [...out, el("p", "muted", t("checks.no_prereg"))];
  const rows = d.entries.map((e) => {
    const c = e.counted || {};
    const passed = c.not_counted ? `0 (${t("checks.not_counted", { n: c.not_counted })})` : (c.passed ?? "");
    const integ = e.integrity === "intact" ? `✅ ${t("checks.intact")}` : e.integrity ? `⚠️ ${t("checks.changed")}: ${(e.changed || []).join(", ")}` : "—";
    return `| ${cell(e.id)} | ${cell(e.title)} | ${e.status === "open" ? t("checks.open") : t("checks.closed")} | ${cell(passed)} | ${cell(c.failed)} | ${cell(c.void)} | ${cell(integ)} |`;
  });
  const head = `| id | ${t("checks.title")} | ${t("checks.status")} | ${t("checks.passed")} | ${t("checks.failed")} | ${t("checks.void")} | ${t("checks.integrity")} |\n|---|---|---|---|---|---|---|`;
  out.push(renderMarkdown(`${head}\n${rows.join("\n")}`));
  return out;
}

function reviewsBox(name, d) {
  const out = [el("h4", "", t("checks.reviews"))];
  if (!d.enabled) out.push(el("p", "muted", t("checks.referee_off")));
  const go = el("button", "approve", t("checks.start"));
  go.title = t("checks.start_hint");
  go.disabled = !d.enabled;
  const said = el("p", "muted", "");
  go.addEventListener("click", async () => {
    go.disabled = true;
    try {
      await call(`/v1/aurora/projects/${name}/referee`, { method: "POST", body: "{}" });
      said.textContent = t("checks.started");
    } catch (e) { said.textContent = t("ev.error", { m: e.message }); go.disabled = false; }
  });
  out.push(el("div", "", ""), go, said);
  if (!d.items.length) return [...out, el("p", "muted", t("checks.no_reviews"))];
  d.items.forEach((r, i) => {
    const box = el("details", "report");
    box.open = i === 0;
    const cost = typeof r.cost_usd === "number" ? `${r.cost_usd.toFixed(2)} USD` : t("checks.no_cost");
    const when = r.created ? clock(Date.parse(r.created) / 1000) : "";
    const verdict = r.verdict || t(r.status === "done" ? "checks.no_verdict" : "checks.stopped", { why: r.why || r.status || "" });
    box.append(el("summary", "", `${(r.file || "").replace("reviews/", "")} · ${when} · ${verdict} · ${cost} · ${r.seconds ?? "?"} s`),
      renderMarkdown((r.text || "").replace(/^<!-- aurora-review .*? -->\n?/, "")));
    out.push(box);
  });
  return out;
}

const PROOF = { proved: "✅", not_proved: "❌", refused: "⛔", error: "⚠️" };

function proofLine(r) {
  const box = el("details", "report");
  const when = r.created ? clock(Date.parse(r.created) / 1000) : "";
  box.append(el("summary", "", `${PROOF[r.status] || "?"} ${r.path || ""} · ${t(`checks.proof_${r.status}`)} · ${when} · ${r.seconds ?? "?"} s`));
  const ax = Object.entries(r.axioms || {}).map(([n, a]) => `- \`${n}\`: ${a.length ? a.join(", ") : t("checks.proof_no_axioms")}`);
  const err = (r.errors || []).map((e) => `    ${e.replace(/\n/g, "\n    ")}`);
  box.append(renderMarkdown([ax.join("\n"), err.length ? err.join("\n") : ""].filter(Boolean).join("\n\n") || t("checks.proof_nothing")));
  return box;
}

function proofBox(name, d) {
  const out = [el("h4", "", t("checks.proofs")), el("p", "muted", t(d.enabled ? "checks.proof_hint" : "checks.proof_off"))];
  const path = el("input", "");
  path.placeholder = "proofs/teorema.lean";
  const go = el("button", "approve", t("checks.proof_start"));
  go.disabled = !d.enabled;
  const list = el("div", "", "");
  go.addEventListener("click", async () => {
    if (!path.value.trim()) return;
    go.disabled = true;
    try {
      const r = await call(`/v1/aurora/projects/${name}/proof`, { method: "POST", body: JSON.stringify({ path: path.value.trim() }) });
      list.prepend(proofLine(r));
    } catch (e) { list.prepend(el("p", "error", t("ev.error", { m: e.message }))); }
    go.disabled = false;
  });
  if (!d.items.length) list.append(el("p", "muted", t("checks.no_proofs")));
  d.items.forEach((r) => list.append(proofLine(r)));
  return [...out, path, go, list];
}

export async function checksView(name) {
  const [pre, rev, prf] = await Promise.all([call(`/v1/aurora/projects/${name}/prereg`), call(`/v1/aurora/projects/${name}/reviews`),
    call(`/v1/aurora/projects/${name}/proof`)]);
  return [el("p", "muted", t("checks.hint")), ...ledger(pre), ...reviewsBox(name, rev), ...proofBox(name, prf)];
}
