// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ✏️ Oggi's tiles chosen by each person (owner, 2026-10-19: «gestire la pagina oggi come se fosse un insieme di widget
// che uno può personalizzare a suo piacimento»): each one shown or hidden and moved up or down; kept on the server
// (/v1/aurora/me/prefs "tiles": the same on every device). A tile with nothing to say stays out even when shown. Any
// page the person may open added too ("page:<id>", today_pages.js), here or with ☀️ beside its 📌 in Avanzate.
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { BUILTIN, pages } from "./today_pages.js";

const PAGE = "page:";

// the whole order: the person's first, then any tile they have never seen (a new one comes in, shown, at the end)
export function arrange(all, prefs) {
  const known = [...new Set(prefs?.order || [])].filter((id) => all.includes(id) || id.startsWith(PAGE));
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
      const page = id.startsWith(PAGE) && pages().find((p) => `${PAGE}${p.id}` === id);
      if (id.startsWith(PAGE) && !page) return null;                 // a page this person may no longer open
      const name = el("label", "", page ? `${page.icon} ${page.label}` : t(`today.tile.${id}`));
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
      if (page) {
        const drop = el("button", "btn", "✕");
        drop.type = "button";
        drop.setAttribute("aria-label", t("today.remove"));
        drop.addEventListener("click", () => { order = order.filter((x) => x !== id); draw(); });
        li.append(drop);
      }
      return li;
    }).filter(Boolean));
    // ➕ any other page this person may open (one with a tile of its own turns that tile on)
    const free = pages().filter((p) => (BUILTIN[p.id] ? off.has(BUILTIN[p.id]) : !order.includes(`${PAGE}${p.id}`)));
    add.replaceChildren(el("option", "", `➕ ${t("today.add_page")}`), ...free.map((p) => { const o = el("option", "", `${p.icon} ${p.label}`); o.value = p.id; return o; }));
    add.firstChild.value = "";
    add.hidden = !free.length;
  };
  const add = el("select", "td-edit-add");
  add.setAttribute("aria-label", t("today.add_page"));
  add.addEventListener("change", () => {
    const id = add.value;
    if (!id) return;
    if (BUILTIN[id]) off.delete(BUILTIN[id]);
    else order.push(`${PAGE}${id}`);
    draw();
  });
  draw();
  const save = el("button", "approve", t("today.edit_save"));
  save.type = "button";
  save.addEventListener("click", () => done({ order, off: order.filter((id) => off.has(id)) }));
  const cancel = el("button", "btn", t("today.edit_cancel"));
  cancel.type = "button";
  cancel.addEventListener("click", () => done(null));
  const reset = el("button", "btn", t("today.edit_reset"));
  reset.type = "button";
  reset.addEventListener("click", () => { order = [...all]; off.clear(); draw(); });   // the added pages go too
  const bar = el("div", "td-edit-bar");
  bar.append(save, cancel, reset);
  const panel = el("section", "td-tile td-edit");
  panel.append(el("h3", "", `✏️ ${t("today.edit")}`), el("p", "muted", t("today.edit_how")), list, add, bar);
  box.replaceChildren(panel);
}

// a page in Oggi or not (Avanzate's ☀️): its own tile shown, or the page's tile present and shown
export function inToday(all, prefs, id) {
  const off = new Set(prefs?.off || []);
  return BUILTIN[id] ? !off.has(BUILTIN[id]) : (prefs?.order || []).includes(`${PAGE}${id}`) && !off.has(`${PAGE}${id}`);
}

export function toggleToday(all, prefs, id) {
  const order = arrange(all, prefs);
  const off = new Set(prefs?.off || []);
  const key = BUILTIN[id] || `${PAGE}${id}`;
  if (inToday(all, prefs, id)) {
    if (BUILTIN[id]) off.add(key);
    else return { order: order.filter((x) => x !== key), off: [...off].filter((x) => x !== key) };
  } else {
    off.delete(key);
    if (!order.includes(key)) order.push(key);
  }
  return { order, off: order.filter((x) => off.has(x)) };
}
