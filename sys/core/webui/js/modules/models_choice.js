// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧠 Models → Come ragiona (owner, 2026-10-14: «la pagina modelli… incasinata… si capisce poco»; ROADMAP 109): one
// choice of four, each with what stays here, what leaves masked and what it was measured at (M214, D2). «Il meglio
// dei due» is the granular assignment: the short calls local, the long reading and writing in the cloud; the forge's
// roles are left as they are. «Su misura» opens the rows, grouped.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { restartPrompt } from "../restart.js";
import { explain } from "./models_mode.js";
import { bestRoles, choiceOf } from "./models_presets.js";

const CHOICES = ["local", "best", "cloud", "custom"];

const list = (key) => t(key).split("|").filter(Boolean);

export async function renderChoice(box, m, onChange, openCustom) {
  let s;
  try { s = await call("/v1/aurora/models/modes"); } catch (e) { box.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
  const now = choiceOf(m.roles, s.mode);
  // the cloud the roles already use (claude_code · sonnet here), else the default of the modes: a default without its
  // key would send the four steps to a provider that cannot answer
  const used = m.roles.find((r) => r.provider !== "local" && !r.id.startsWith("forge_"));
  const cloud = used ? { provider: used.provider, model: used.model || "" } : { provider: s.provider, model: s.model || "" };
  let picked = now;
  const cards = el("div", "mch-cards");
  const detail = el("div", "mch-detail");
  const bar = el("div", "mch-apply");

  const stat = (label, value, note) => {
    const d = el("span", "mch-stat");
    d.append(el("small", "", label), el("strong", "", value), el("small", "", note));
    return d;
  };
  const panel = (title, items) => {
    const d = el("div", "mch-panel");
    const ul = el("ul");
    ul.append(...items.map((x) => el("li", "", x)));
    d.append(el("h4", "", title), ul);
    return d;
  };

  function draw() {
    cards.replaceChildren(...CHOICES.map((id) => {
      const b = el("button", `mch-card${id === picked ? " on" : ""}`);
      b.type = "button";
      b.setAttribute("aria-pressed", String(id === picked));
      const head = el("span", "mch-head");
      head.append(el("strong", "", t(`mch.${id}`)));
      if (id === "best") head.append(el("span", "mch-tag", t("mch.advised")));
      if (id === now) head.append(el("span", "mch-now", `● ${t("mm.now")}`));
      const stats = el("span", "mch-stats");
      stats.append(stat(t("mch.right"), t(`mch.${id}.right`), t(`mch.${id}.right_note`)), stat(t("mch.secs"), t(`mch.${id}.secs`), t("mch.median")));
      b.append(head, el("span", "mch-line", t(`mch.${id}.line`)), stats, el("span", "mch-price", t(`mch.${id}.price`)));
      b.addEventListener("click", () => { picked = id; draw(); });
      return b;
    }));
    const guards = el("div", "mch-panel");
    guards.append(el("h4", "", t("mch.guards")), el("p", m.mask ? "" : "error", t(m.mask ? "md.mask_on" : "md.mask_off")),
      el("p", m.exempt ? "" : "error", t(m.exempt ? "md.exempt_on" : "md.exempt_off")), el("p", "muted", t("md.pictures")));
    detail.replaceChildren(panel(t("mch.stays"), list(`mch.${picked}.stays`)), panel(t("mch.leaves"), list(`mch.${picked}.leaves`)), guards);
    const go = el("button", "approve", t(picked === "custom" ? "mch.open_custom" : picked === now ? "mch.in_use" : "mch.use"));
    go.disabled = picked === now && picked !== "custom";
    go.addEventListener("click", () => use(picked));
    const out = el("span", "muted");
    bar.replaceChildren(el("span", "", t(`mch.${picked}.apply`)), go, out);
  }

  async function use(id) {
    if (id === "custom") { openCustom(); return; }
    try {
      if (id === "best") {
        await call("/v1/aurora/models/roles", { method: "PUT", body: JSON.stringify(bestRoles(m.roles, cloud.provider, cloud.model)) });
      } else {
        const r = await call("/v1/aurora/models/mode", { method: "POST",
          body: JSON.stringify({ mode: id === "cloud" ? "cloud_private" : "local", provider: cloud.provider, model: cloud.model }) });
        if (r.restart && r.restart.length) await restartPrompt(r.restart);
      }
      onChange();
    } catch (e) { explain(e); }
  }

  draw();
  box.replaceChildren(cards, detail, bar, el("p", "muted mch-note", t("mch.note")));
}
