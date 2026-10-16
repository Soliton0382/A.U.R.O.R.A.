// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro → 📈 → 🤖 the guiding tuned during the night (ROADMAP N28): the mode (off / propose / apply), the limits of
// each parameter Aurora may move, what PHD2 has now, the proposal or the change on trial, the latest actions
// (api/astro → ast_autoguide). The person decides the mode and the limits; Aurora never steps out of them.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const PARAMS = [["exposure_ms", "ms", 100], ["ra_min_move", "px", 0.01], ["dec_min_move", "px", 0.01]];
const ICON = { propose: "💡", apply: "🔧", keep: "✅", revert: "↩️" };

function action(a) {
  const when = new Date(a.t * 1000).toLocaleTimeString();
  const what = a.action === "revert" ? t("at.a.revert", a) : a.action === "keep" ? t("at.a.keep", a)
    : t(`at.a.${a.action}`, { ...a, p: t(`at.p.${a.param}`), why: t(`at.why.${a.why}`, a) });
  return el("div", "muted", `${when} ${ICON[a.action] || "•"} ${what}`);
}

export function tunerBox(box) {
  box.innerHTML = `<h4>🤖 <span data-i18n="at.title"></span></h4><p class="muted" data-i18n="at.hint"></p>
    <div class="at-modes prj-tabs"></div><div class="at-limits aa-grid"></div><div class="at-state"></div>
    <details><summary data-i18n="at.history"></summary><div class="at-history al-events"></div></details>`;
  box.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
  let d = null;
  const save = async (mode) => {
    const limits = {};
    for (const [k] of PARAMS) {
      limits[k] = [box.querySelector(`[name="${k}-lo"]`).value, box.querySelector(`[name="${k}-hi"]`).value];
    }
    try { draw(await call("/v1/aurora/astro/autoguide", { method: "PUT", body: JSON.stringify({ mode, limits }) })); }
    catch (e) { box.querySelector(".at-state").textContent = e.message; }
  };
  const draw = (x) => {
    d = x;
    const modes = box.querySelector(".at-modes");
    modes.replaceChildren(...["off", "propose", "apply"].map((m) => {
      const b = el("button", `cat-chip${d.mode === m ? " on" : ""}`, t(`at.mode.${m}`));
      b.type = "button";
      b.addEventListener("click", () => {
        if (m === "apply" && !confirm(t("at.confirm"))) return;
        save(m);
      });
      return b;
    }));
    const lim = box.querySelector(".at-limits");
    if (!lim.childElementCount) {
      for (const [k, unit, step] of PARAMS) {
        const lab = el("label", "aa-fact");
        lab.append(el("span", "", `${t(`at.p.${k}`)} (${unit})`));
        const row = el("div", "at-pair");
        for (const [i, side] of [[0, "lo"], [1, "hi"]]) {
          const inp = el("input");
          Object.assign(inp, { type: "number", step, name: `${k}-${side}`, value: d.limits[k][i] });
          inp.setAttribute("aria-label", `${t(`at.p.${k}`)} ${t(`at.${side}`)}`);
          inp.addEventListener("change", () => save(d.mode));
          row.append(inp);
        }
        lab.append(row);
        lim.append(lab);
      }
    }
    const s = d.state || {};
    const st = box.querySelector(".at-state");
    const lines = [];
    if (d.mode === "off") lines.push(t("at.off"));
    else if (s.error) lines.push(`⚠️ ${s.error}`);
    if (s.now && Object.keys(s.now).length) lines.push(t("at.now", { e: s.now.exposure_ms, r: s.now.ra_min_move, d: s.now.dec_min_move }));
    if (s.trial) lines.push(`🔧 ${t("at.trial", { ...s.trial, p: t(`at.p.${s.trial.param}`) })}`);
    else if (s.proposal) lines.push(`💡 ${t("at.a.propose", { ...s.proposal, p: t(`at.p.${s.proposal.param}`), why: t(`at.why.${s.proposal.why}`, s.proposal) })}`);
    else if (d.mode !== "off") lines.push(t("at.nothing"));
    st.replaceChildren(...lines.map((x) => el("p", "", x)));
    const h = d.history || [];
    box.querySelector(".at-history").replaceChildren(...(h.length ? h.slice().reverse().map(action) : [el("div", "muted", "—")]));
  };
  const refresh = async () => {
    try { draw(await call("/v1/aurora/astro/autoguide")); } catch (e) { box.querySelector(".at-state").textContent = e.message; }
  };
  refresh();
  return { refresh };
}
