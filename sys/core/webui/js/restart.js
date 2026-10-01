// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// After a settings change: ask whether to restart the services that read it, then do it and wait.
import { call } from "./api.js";
import { el } from "./dom.js";
import { t } from "./i18n.js";

export function restartPrompt(services) {
  const known = (services || []).filter((s) => s.startsWith("aurora-"));
  if (!known.length) return Promise.resolve(false);
  return new Promise((done) => {
    const dlg = el("dialog", "modal");
    dlg.append(el("h3", "", `🔄 ${t("restart.title")}`), el("p", "", t("restart.text", { s: known.join(", ") })));
    const status = el("p", "muted");
    const yes = el("button", "approve big", `✔ ${t("restart.now")}`), no = el("button", "", t("restart.later"));
    const row = el("div", "appr-actions");
    row.append(yes, no);
    dlg.append(status, row);
    document.body.append(dlg);
    dlg.showModal();
    no.addEventListener("click", () => { dlg.close(); dlg.remove(); done(false); });
    yes.addEventListener("click", async () => {
      yes.disabled = no.disabled = true;
      status.textContent = t("restart.doing");
      try {
        await call("/v1/aurora/services/restart", { method: "POST", body: JSON.stringify({ services: known }) });
        if (known.includes("aurora-api")) {
          await new Promise((ok) => setTimeout(ok, 3000));
          for (let i = 0; i < 40; i++) {                 // the API comes back in a few seconds
            try { if ((await fetch("/health")).ok) break; } catch { /* restarting */ }
            await new Promise((ok) => setTimeout(ok, 1000));
          }
        }
        status.textContent = t("restart.done");
        setTimeout(() => { dlg.close(); dlg.remove(); done(true); }, 900);
      } catch (e) { status.textContent = t("ev.error", { m: e.message }); no.disabled = false; }
    });
  });
}
