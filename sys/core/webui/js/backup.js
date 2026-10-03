// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The backup's row (Status page and the backup plugin's card): last copy, next one, 💾 Run now, 🔌 Mount the NAS.
// While a backup runs the row follows it until it ends. The admin's only (the API answers 403 to others).
import { call } from "./api.js";
import { clock, el } from "./dom.js";
import { t } from "./i18n.js";

export async function backupRow() {
  const b = await call("/v1/aurora/backup").catch(() => null);
  if (!b) return null;
  const row = el("div", "ev backup-row");
  const fill = (b) => {
    row.replaceChildren();
    if (!b.configured) {
      row.append(el("span", "ic", "⚠️"), el("span", "error", t("status.backup.off", { why: b.problem })));
      if (String(b.problem).includes("NAS")) {           // a NAS folder not mounted: mount it from here
        const m = el("button", "", t("status.backup.mount"));
        m.addEventListener("click", async () => {
          m.disabled = true;
          try { await call("/v1/aurora/backup/mount", { method: "POST" }); fill(await call("/v1/aurora/backup")); }
          catch (e) { m.textContent = t("ev.error", { m: e.message }); }
        });
        row.append(m);
      }
      return;
    }
    const l = b.last;
    row.append(el("span", "ic", b.running ? "⏳" : l ? "✅" : "⏳"),
      el("span", "", b.running ? t("status.backup.running") : l ? t("status.backup.last", { at: clock(l.at), files: l.files,
        gb: (l.bytes / 1e9).toFixed(1), n: b.snapshots.length }) : t("status.backup.never")),
      el("span", "muted", b.installed ? t("status.backup.next", { at: b.next || b.time }) : t("status.backup.unit")));
    const go = el("button", "", t("status.backup.run"));
    go.disabled = b.running;
    go.addEventListener("click", async () => {
      go.disabled = true;
      try { await call("/v1/aurora/backup/run", { method: "POST" }); go.textContent = t("status.backup.started"); follow(); }
      catch (e) { go.textContent = t("ev.error", { m: e.message }); go.disabled = false; }
    });
    row.append(go);
  };
  const follow = async () => {                           // every 5 s while it runs, then the result
    for (let i = 0; i < 720; i++) {
      await new Promise((ok) => setTimeout(ok, 5000));
      if (!row.isConnected) return;
      const now = await call("/v1/aurora/backup").catch(() => null);
      if (!now) return;
      fill(now);
      if (!now.running && i > 0) return;
    }
  };
  fill(b);
  if (b.running) follow();
  return row;
}
