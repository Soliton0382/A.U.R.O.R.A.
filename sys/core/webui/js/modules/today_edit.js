// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ✏️ Oggi's tiles chosen by each person (owner, 2026-10-19: «gestire la pagina oggi come se fosse un insieme di widget
// che uno può personalizzare a suo piacimento»): each one shown or hidden and moved up or down; kept on the server
// (/v1/aurora/me/prefs "tiles": the same on every device). A tile with nothing to say stays out even when shown.
import { el } from "../dom.js";
import { t } from "../i18n.js";

// the whole order: the person's first, then any tile they have never seen (a new one comes in, shown, at the end)
export function arrange(all, prefs) {
  const known = (prefs?.order || []).filter((id) => all.includes(id));
  return [...known, ...all.filter((id) => !known.includes(id))];
}

export function shown(all, prefs) {
  const off = new Set(prefs?.off || []);
  return arrange(all, prefs).filter((id) => !off.has(id));
}

// the editor in place of the tiles: a row a tile, ✓ to show it, ↑ ↓ to move it; Save, Cancel, the first order back
export function editTiles(box, all, prefs, done) {
  let order = arrange(all, prefs);
  const off = new Set(prefs?.off || []);
  const list = el("ol", "td-edit-list");
  const draw = () => {
    list.replaceChildren(...order.map((id, i) => {
      const li = el("li", `td-edit-row${off.has(id) ? " off" : ""}`);
      const on = el("input");
      on.type = "checkbox";
      on.checked = !off.has(id);
      on.id = `td-edit-${id}`;
      on.addEventListener("change", () => { if (on.checked) off.delete(id); else off.add(id); draw(); });
      const name = el("label", "", t(`today.tile.${id}`));
      name.htmlFor = on.id;
      const move = (d) => { const j = i + d; [order[i], order[j]] = [order[j], order[i]]; draw(); };
      const up = el("button", "btn", "↑");
      up.type = "button";
      up.disabled = i === 0;
      up.setAttribute("aria-label", t("today.move_up"));
      up.addEventListener("click", () => move(-1));
      const down = el("button", "btn", "↓");
      down.type = "button";
      down.disabled = i === order.length - 1;
      down.setAttribute("aria-label", t("today.move_down"));
      down.addEventListener("click", () => move(1));
      li.append(on, name, up, down);
      return li;
    }));
  };
  draw();
  const save = el("button", "approve", t("today.edit_save"));
  save.type = "button";
  save.addEventListener("click", () => done({ order, off: order.filter((id) => off.has(id)) }));
  const cancel = el("button", "btn", t("today.edit_cancel"));
  cancel.type = "button";
  cancel.addEventListener("click", () => done(null));
  const reset = el("button", "btn", t("today.edit_reset"));
  reset.type = "button";
  reset.addEventListener("click", () => { order = [...all]; off.clear(); draw(); });
  const bar = el("div", "td-edit-bar");
  bar.append(save, cancel, reset);
  const panel = el("section", "td-tile td-edit");
  panel.append(el("h3", "", `✏️ ${t("today.edit")}`), el("p", "muted", t("today.edit_how")), list, bar);
  box.replaceChildren(panel);
}
