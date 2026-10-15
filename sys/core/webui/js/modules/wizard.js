// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧙 A guided window for a few settings (owner, 2026-10-16: «un tasto wizard in ogni sezione che richiede una
// configurazione… si compone dinamicamente in base a quello che c'è già scritto nella configurazione dei plugin… semplice
// e chiaro»): made from what is already written — the plugin's own guide and links first, then one setting a step with
// its explanation and the right field (yes/no, a choice, a number, a secret never shown), then what will change, saved
// together. Nothing of its own to keep up: a new setting or a new guide shows here by itself.
import { call } from "../api.js";
import { el, external } from "../dom.js";
import { lang, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { restartPrompt } from "../restart.js";

const on = (v) => ["1", "true", "yes", "on"].includes(String(v).toLowerCase());

function field(s, choices) {
  if (s.type === "bool") {
    const box = el("input");
    box.type = "checkbox";
    box.checked = on(s.value);
    const r = el("label", "wz-check");
    r.append(box, el("span", "", t("wz.yes")));
    return { node: r, value: () => (box.checked ? "1" : "0"), orig: on(s.value) ? "1" : "0" };
  }
  const list = choices[s.key];
  const input = el(list || s.type === "enum" ? "select" : "input");
  if (!list && s.type === "enum") for (const c of s.choices) input.append(el("option", "", c));
  if (list) for (const d of list) { const o = el("option", "", `${d.name} — ${d.id}`); o.value = d.id; input.append(o); }
  if (s.type === "int") input.type = "number";
  if (s.secret) { input.type = "password"; input.placeholder = s.value ? t("plug.secret.set") : t("plug.secret.empty"); }
  else { input.value = s.value ?? ""; input.placeholder = s.recommended || ""; }
  return { node: input, value: () => input.value, orig: s.secret ? "" : String(s.value ?? ""), secret: !!s.secret };
}

// specs: the settings as /v1/aurora/settings gives them; guide: {title, intro (markdown), links}
export function openWizard(specs, { guide = {}, choices = {}, onSaved = null } = {}) {
  const code = lang.slice(0, 2);
  const steps = [];
  if (guide.intro || guide.links?.length) steps.push({ kind: "intro" });
  const fields = specs.map((s) => ({ s, f: field(s, choices) }));
  for (const x of fields) steps.push({ kind: "field", x });
  steps.push({ kind: "end" });
  const dlg = el("dialog", "modal wizard");
  let i = 0;
  const changes = () => Object.fromEntries(fields.filter(({ f }) => (f.secret ? f.value() !== "" : f.value() !== f.orig))
    .map(({ s, f }) => [s.key, f.value()]));
  const out = el("p", "error");
  const draw = () => {
    const st = steps[i];
    const body = [];
    if (st.kind === "intro") {
      body.push(el("h3", "", `🧙 ${guide.title || t("wz.title")}`), renderMarkdown(guide.intro || ""));
      if (guide.links?.length) {
        const ul = el("ul");
        for (const l of guide.links) { const li = el("li"); li.append(external(el("a", "", l.label || l.url), l.url)); ul.append(li); }
        body.push(ul);
      }
    } else if (st.kind === "field") {
      const { s, f } = st.x;
      body.push(el("h3", "", s[code] ? s[code].split(/[.:(]/)[0].slice(0, 80) : s.key), el("p", "", s[code] || s.en),
        f.node, el("p", "muted", s.secret ? t("wz.secret") : s.recommended ? t("wz.recommended", { v: s.recommended }) : ""),
        el("small", "muted", s.key));
    } else {
      const c = changes();
      body.push(el("h3", "", `✅ ${t("wz.end")}`));
      if (!Object.keys(c).length) body.push(el("p", "muted", t("wz.nothing")));
      else {
        const ul = el("ul");
        for (const [k, v] of Object.entries(c)) {
          const s = specs.find((x) => x.key === k);
          ul.append(el("li", "", `${(s[code] || k).split(/[.:(]/)[0].slice(0, 60)}: ${s.secret ? "••••••" : v || t("wz.empty")}`));
        }
        body.push(ul);
      }
    }
    const back = el("button", "", `← ${t("wl.back")}`);
    back.disabled = i === 0;
    back.addEventListener("click", () => { i -= 1; out.textContent = ""; draw(); });
    const next = el("button", "approve", st.kind === "end" ? `💾 ${t("settings.save")}` : `${t("wl.next")} →`);
    next.addEventListener("click", async () => {
      if (st.kind !== "end") { i += 1; draw(); return; }
      const c = changes();
      if (!Object.keys(c).length) { dlg.close(); dlg.remove(); return; }
      next.disabled = true;
      try {
        const r = await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify(c) });
        dlg.close();
        dlg.remove();
        const restarted = await restartPrompt(r.restart);
        if (onSaved) onSaved(r, restarted);
      } catch (e) { out.textContent = t("ev.error", { m: e.message }); next.disabled = false; }
    });
    const close = el("button", "icon close", "✕");
    close.addEventListener("click", () => { dlg.close(); dlg.remove(); });
    const bar = el("div", "wl-bar");
    bar.append(back, next);
    const dots = el("div", "wl-dots");
    steps.forEach((_, n) => dots.append(el("span", n <= i ? "on" : "")));
    dlg.replaceChildren(close, dots, el("small", "muted", t("wl.count", { n: i + 1, m: steps.length })), ...body, out, bar);
  };
  document.body.append(dlg);
  draw();
  dlg.showModal();
}
