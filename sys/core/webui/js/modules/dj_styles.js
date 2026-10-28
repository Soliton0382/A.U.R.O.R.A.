// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎓 The DJ's styles, a tab of 🎧 (owner, 29 Oct: «un tasto play di fianco agli stili per sentire come sono… senza fare
// refresh»): its own and the ones learnt from a radio or a track (aud_learn), each with ▶ to hear 16 bars of the DJ's
// drums and bass in it, the learnt ones with 🗑️; filled again when a style is learnt or forgotten («dj-styles»).
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

export function stylesPanel(play) {
  const box = el("div", "dj-styles");
  const out = el("p", "muted");
  const mine = el("ol", "dj-radio-list");
  const own = el("ol", "dj-radio-list");
  box.append(el("p", "muted", t("dj.styles.hint")), el("h4", "", `🎓 ${t("dj.learn.mine")}`), mine,
    el("h4", "", `🎛️ ${t("dj.styles.own")}`), own, out);

  const row = (x) => {
    const li = el("li");
    const hear = el("button", "", "▶");
    hear.type = "button";
    hear.title = t("dj.learn.hear");
    hear.addEventListener("click", () => play(`/v1/aurora/dj/styles/${encodeURIComponent(x.id)}/preview`, `🎧 ${x.label}`, false));
    li.append(hear);
    if (x.learned) {
      const del = el("button", "", "🗑️");
      del.type = "button";
      del.title = t("dj.learn.forget");
      del.addEventListener("click", async () => {
        if (!confirm(t("dj.learn.forget_q", { name: x.label }))) return;
        try { await call(`/v1/aurora/dj/styles/${encodeURIComponent(x.id)}`, { method: "DELETE" }); window.dispatchEvent(new Event("dj-styles")); }
        catch (e) { out.textContent = t("ev.error", { m: e.message }); }
      });
      li.append(" ", del);
    }
    li.append(el("strong", "", ` ${x.label}`),
      el("span", "muted", `${x.bpm ? ` — ${x.bpm} BPM` : ""}${x.station ? ` · ${x.station}` : ""}`));
    return li;
  };
  const fill = async () => {
    let styles;
    try { styles = (await call("/v1/aurora/dj")).styles; } catch (e) { out.textContent = t("ev.error", { m: e.message }); return; }
    const learnt = styles.filter((x) => x.learned);
    mine.replaceChildren(...(learnt.length ? learnt.map(row) : [el("li", "muted", t("dj.styles.none"))]));
    own.replaceChildren(...styles.filter((x) => !x.learned).map(row));
  };
  fill();
  window.addEventListener("dj-styles", fill);
  return box;
}
