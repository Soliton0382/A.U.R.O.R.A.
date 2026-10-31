// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔏 The automatic certificate in the HTTPS page (owner, 1 Nov: «integrarlo nella pagina https come sezione aggiuntiva
// che oltre al rinnovo dice tutto sul certificato… la scadenza, quando è previsto il rinnovo automatico»): the
// certificate in use and its dates, the renewal's day, the last try with its steps, the copy for the other devices
// (the NAS's folder, keyStore.p12), the settings, a renewal now. The admin's only, as the whole page.
import { call } from "../api.js";
import { el } from "../dom.js";
import { lang, t } from "../i18n.js";
import { settingsForm } from "./settings_form.js";

const KEYS = ["AURORA_ACME_ENABLED", "AURORA_ACME_DOMAINS", "AURORA_ACME_EMAIL", "AURORA_ACME_DNS", "AURORA_ACME_DNS_TOKEN",
  "AURORA_ACME_STAGING", "AURORA_CERTS_COPY_DIR", "AURORA_CERTS_P12_PASSWORD", "AURORA_CERTS_P12_LEGACY"];
const when = (x) => (x ? new Date(typeof x === "number" ? x * 1000 : x).toLocaleString(lang.replace("_", "-"),
  { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const day = (x) => (x ? new Date(x).toLocaleDateString(lang.replace("_", "-"), { day: "numeric", month: "long", year: "numeric" }) : "—");

export async function acmeBox(box, say, refresh) {
  let s;
  try { s = await call("/v1/aurora/https/acme"); } catch (e) { box.replaceChildren(el("p", "error", e.message)); return; }
  const c = s.certificate && !s.certificate.error ? s.certificate : null;
  const rows = [
    [t("acme.state"), s.enabled ? (s.staging ? t("acme.on_test") : t("acme.on")) : t("acme.off")],
    [t("acme.names"), s.names.join(", ") || "—"],
    [t("acme.issuer"), c ? c.issuer : "—"],
    [t("acme.valid"), c ? `${day(c.not_before)} → ${day(c.not_after)} (${t("acme.days", { n: c.days_left })})` : "—"],
    [t("acme.renew_at"), !s.enabled ? t("acme.renew_off") : s.due ? t("acme.renew_due", { w: s.due }) : day(s.renew_from)],
    [t("acme.last"), s.last.tried ? `${when(s.last.tried)} — ${s.last.trying ? "⏳" : s.last.error ? `❌ ${s.last.error}` : "✅"}` : "—"],
    [t("acme.copy"), !s.copy.dir ? t("acme.copy_none") : s.copy.error ? `❌ ${s.copy.error}`
      : `${s.copy.dir} · ${s.copy.at ? when(s.copy.at) : t("acme.copy_never")}${s.copy.p12_password ? "" : ` · ⚠️ ${t("acme.p12_nopass")}`}`],
  ];
  const table = el("div", "acme-facts");
  for (const [k, v] of rows) table.append(el("span", "muted", k), el("span", "", v));
  const parts = [el("h3", "", t("acme.title")), el("p", "muted", t("acme.hint")), table];
  if (s.last.steps && s.last.steps.length) {
    const d = el("details", "");
    d.append(el("summary", "", t("acme.steps")), el("pre", "acme-steps", s.last.steps.join("\n")));
    parts.push(d);
  }
  const row = el("div", "appr-actions");
  const renew = el("button", "approve", s.staging ? t("acme.renew_test") : t("acme.renew_now"));
  renew.disabled = !s.enabled || !s.token_set;
  renew.addEventListener("click", async () => {
    if (!confirm(t(s.staging ? "acme.renew_test_q" : "acme.renew_q", { n: s.names.join(", ") }))) return;
    renew.disabled = true;
    say(t("acme.working"));
    try {
      const r = await call("/v1/aurora/https/acme/renew?force=true", { method: "POST" });
      say(t("acme.done", { d: day(r.certificate?.not_after) }));
    } catch (e) { say(t("ev.error", { m: e.message })); }
    await refresh();
  });
  const copy = el("button", "", t("acme.copy_now"));
  copy.disabled = !s.copy.dir;
  copy.addEventListener("click", async () => {
    try { const r = await call("/v1/aurora/https/acme/copy", { method: "POST" }); say(r.error ? t("ev.error", { m: r.error }) : t(r.copied ? "acme.copied" : "acme.copy_same")); }
    catch (e) { say(t("ev.error", { m: e.message })); }
    await refresh();
  });
  row.append(renew, copy);
  parts.push(row);
  if (!s.token_set) parts.push(el("p", "muted", t("acme.token_hint")));
  parts.push(await settingsForm(KEYS, { title: `⚙️ ${t("acme.settings")}`, choices: { AURORA_ACME_DNS: [{ id: "cloudflare", name: "Cloudflare" }] },
    onSaved: () => refresh() }));
  box.replaceChildren(...parts);
}
