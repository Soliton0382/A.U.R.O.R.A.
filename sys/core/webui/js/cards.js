// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Command cards (roadmap 74): what only the owner can do from a shell — an update through the installer, a
// signature — with the exact command for this system, a copy button, and «Check» once it is done. No terminal in
// the WebUI: a shell reachable from the browser is the first thing an attacker looks for.
import { call } from "./api.js";
import { el } from "./dom.js";
import { t } from "./i18n.js";

async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { /* http or refused: the old way */ }
  const area = el("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.cssText = "position:fixed;opacity:0;top:0;left:0";
  document.body.append(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  area.remove();
  return ok;
}

export async function commandCards(box, onDone) {
  box.replaceChildren();
  let r;
  try { r = await call("/v1/aurora/commands"); } catch { return; }      // not the admin, or an older Aurora
  for (const c of r.cards || []) {
    const card = el("div", "cmd-card");
    card.append(el("strong", "", c.title), el("p", "", c.text));
    if (c.admin) card.append(el("div", "muted", t("cmd.admin")));
    const code = el("pre", "cmd-line", c.command);
    const bar = el("div", "settings-actions");
    const cp = el("button", "", `📋 ${t("cmd.copy")}`);
    cp.addEventListener("click", async () => { cp.textContent = (await copy(c.command)) ? `✅ ${t("cmd.copied")}` : t("cmd.select"); });
    const check = el("button", "approve", `🔎 ${t("cmd.verify")}`);
    const out = el("div", "muted");
    check.addEventListener("click", async () => {
      check.disabled = true;
      out.textContent = t("cmd.checking");
      try {
        const v = await call(`/v1/aurora/commands/${c.id}/verify`, { method: "POST", body: "{}" });
        out.textContent = v.done ? `✅ ${t("cmd.done")}` : `⏳ ${t("cmd.notyet")}${v.error ? ` — ${v.error}` : ""}`;
        if (v.done && onDone) onDone();
      } catch (e) { out.textContent = e.message; }
      check.disabled = false;
    });
    bar.append(cp, check);
    card.append(code, bar, out);
    box.append(card);
  }
}
