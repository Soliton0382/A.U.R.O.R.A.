// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧭 How free Aurora is, inside the section it is about (owner, 2026-10-08: «ok averli in una pagina globale, ma
// sarebbe più pratico averli anche nelle sezioni specifiche… mi raccomando ai permessi tra amministratore e utenti»).
// autonomySlot("security") is an element that fills itself with the rows of those areas — the same levels, the same
// call as the 🧭 Autonomy page. Who may change what is the server's: an area the person may not change is not shown to
// a user, and shown locked to the admin of another's area; with nothing to show, the slot stays empty.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el, info } from "../dom.js";
import { t } from "../i18n.js";
import { apiBack } from "../restart.js";

const ICON = { 0: "🔒", 1: "🤝", 2: "🚀" };
let pending = null;                                  // one reading for the slots of a page
let read = 0;

async function state(again = false) {
  if (again || !pending || Date.now() - read > 10_000) {
    read = Date.now();
    pending = call("/v1/aurora/autonomy").catch(() => null);
  }
  return pending;
}

async function fill(slot, ids, again = false) {
  const v = await state(again);
  const areas = (v?.areas || []).filter((a) => ids.includes(a.id) && (a.mine || v.admin));
  if (!areas.length) { slot.replaceChildren(); slot.hidden = true; return; }
  slot.hidden = false;
  const box = el("details", "report auto-box");
  box.open = true;
  const head = el("summary", "", `🧭 ${t("auto.here")}`);
  box.append(head);
  for (const a of areas) {
    const row = el("div", "auto-area");
    const explain = a.levels.map((n) => `${ICON[n]} ${t(`auto.level.${n}`)}: ${t(`auto.what.${a.id}.${n}`)}`).join("\n");
    const name = el("div", "auto-name");
    name.append(el("strong", "", t(`auto.area.${a.id}`)), info(explain));
    const levels = el("div", "auto-levels");
    for (const n of a.levels) {
      const b = el("button", a.level === n ? "approve" : "", `${ICON[n]} ${t(`auto.level.${n}`)}`);
      b.title = t(`auto.what.${a.id}.${n}`);
      b.disabled = !a.mine;
      b.addEventListener("click", () => set(slot, ids, a.id, n));
      levels.append(b);
    }
    row.append(name, levels, el("p", "muted auto-now", a.level === null ? t("auto.by_hand") : t(`auto.what.${a.id}.${a.level}`)));
    if (a.external && a.level === 2 && !v.exempt) row.append(el("p", "warn", t("auto.not_exempt")));
    box.append(row);
  }
  const all = el("button", "", `🧭 ${t("auto.all")}`);
  all.addEventListener("click", () => bus.emit("show", { id: "autonomy" }));
  box.append(el("p", "muted out"), all);
  slot.replaceChildren(box);
}

async function set(slot, ids, area, level) {
  const out = slot.querySelector(".out");
  if (out) out.textContent = t("auto.saving");
  try {
    const r = await call("/v1/aurora/autonomy", { method: "PUT", body: JSON.stringify({ levels: { [area]: level } }) });
    if (r.restart?.length) {
      await call("/v1/aurora/services/restart", { method: "POST", body: JSON.stringify({ services: r.restart }) }).catch(() => null);
      if (r.restart.includes("aurora-api")) await apiBack();
    }
    await fill(slot, ids, true);
  } catch (e) { if (out) out.textContent = t("ev.error", { m: e.message }); }
}

export function autonomySlot(...ids) {
  const slot = el("div", "auto-slot");
  slot.hidden = true;
  // filled when the page is in the document; again each time it is shown (the level may change elsewhere)
  queueMicrotask(() => fill(slot, ids));
  bus.on("view", () => setTimeout(() => { if (slot.isConnected && slot.parentElement?.offsetParent !== null) fill(slot, ids); }));
  return slot;
}
