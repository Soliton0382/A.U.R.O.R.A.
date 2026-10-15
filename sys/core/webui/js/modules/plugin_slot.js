// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// ⚙️ The plugins of a page, configured in the page itself (owner, 2026-10-16: «i plugin hanno senso se non hanno una
// pagina, ma se hanno una pagina tanto vale avere le configurazioni lì dentro»): one chip per plugin whose manifest
// says this page («page»), its state, and the same window as the Plugins page's. The admin's; out when there is none.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { openPlugin } from "./plugins.js";

async function fill(slot, page) {
  let list;
  try { list = (await call("/v1/aurora/plugins")).filter((p) => p.page === page); } catch { slot.hidden = true; return; }
  const me = await call("/v1/aurora/me").catch(() => ({ admin: false }));
  if (!list.length || !me.admin) { slot.hidden = true; return; }
  const chips = list.map((p) => {
    const b = el("button", `plug-chip ${p.available ? "on" : "off"}`);
    b.type = "button";
    const state = p.available ? "✅" : p.missing?.length ? "⚠️" : "⏸️";
    b.append(el("span", "", `${state} ${p.name}`));
    b.title = p.available ? t("plug.on") : p.missing?.length ? t("plug.state.missing", { keys: p.missing.join(", ") }) : t("plug.off");
    b.addEventListener("click", () => openPlugin(p.name));
    return b;
  });
  slot.replaceChildren(el("span", "muted", `⚙️ ${t("plug.page_settings")}`), ...chips);
  slot.hidden = false;
}

export function pluginSlot(page) {
  const slot = el("div", "plug-slot");
  slot.hidden = true;
  queueMicrotask(() => fill(slot, page));
  bus.on("plugins", () => { if (slot.isConnected) fill(slot, page); });
  return slot;
}
