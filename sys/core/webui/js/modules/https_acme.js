// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔏 The automatic certificate in the HTTPS page (owner, 1 Nov: «integrarlo nella pagina https come sezione aggiuntiva
// che oltre al rinnovo dice tutto sul certificato… la scadenza, quando è previsto il rinnovo automatico»; «metto il
// dominio, faccio partire, dà il token da aggiungere, lo aggiungo e poi fa la verifica del dominio… un po' più
// interattiva nella pagina se no si perdono pezzi»). The facts of the certificate in use, then a guided way in steps —
// 1 the names, 2 who writes the DNS record (Aurora through Cloudflare, or by hand), 3 the records with their state as
// the Internet sees them, 4 the authority's verification — and the copy for the other devices. The admin's only.
import { call } from "../api.js";
import { el } from "../dom.js";
import { lang, t } from "../i18n.js";
import { settingsForm } from "./settings_form.js";

const MORE = ["AURORA_ACME_EMAIL"];
const when = (x) => (x ? new Date(typeof x === "number" ? x * 1000 : x).toLocaleString(lang.replace("_", "-"),
  { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const day = (x) => (x ? new Date(x).toLocaleDateString(lang.replace("_", "-"), { day: "numeric", month: "long", year: "numeric" }) : "—");
const save = (values) => call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify(values) });
let timer = null;

function copyButton(text) {
  const b = el("button", "acme-copy", "📋");
  b.type = "button";
  b.title = t("acme.copy_value");
  b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); b.textContent = "✅"; } catch { b.textContent = "⚠️"; }
    setTimeout(() => { b.textContent = "📋"; }, 1500);
  });
  return b;
}

function facts(s) {
  const c = s.certificate && !s.certificate.error ? s.certificate : null;
  const rows = [
    [t("acme.names"), c ? c.names.join(", ") : "—"],
    [t("acme.issuer"), c ? c.issuer : "—"],
    [t("acme.valid"), c ? `${day(c.not_before)} → ${day(c.not_after)} (${t("acme.days", { n: c.days_left })})` : "—"],
    [t("acme.renew_at"), !s.enabled ? t("acme.renew_off") : s.due ? t("acme.renew_due", { w: s.due })
      : `${day(s.renew_from)}${s.manual ? ` · ${t("acme.renew_by_hand")}` : ""}`],
    [t("acme.last"), s.last.tried ? `${when(s.last.tried)} — ${s.last.trying ? `⏳ ${t("acme.in_progress")}` : s.last.error ? `❌ ${s.last.error}` : "✅"}` : "—"],
    [t("acme.copy"), !s.copy.dir ? t("acme.copy_none") : s.copy.error ? `❌ ${s.copy.error}`
      : `${s.copy.dir} · ${s.copy.at ? when(s.copy.at) : t("acme.copy_never")}${s.copy.p12_password ? "" : ` · ⚠️ ${t("acme.p12_nopass")}`}`],
  ];
  const table = el("div", "acme-facts");
  for (const [k, v] of rows) table.append(el("span", "muted", k), el("span", "", v));
  const auto = el("label", "acme-auto");
  const box = el("input");
  box.type = "checkbox";
  box.checked = s.enabled;
  auto.append(box, ` 🔁 ${t("acme.auto")}`);
  return [table, auto, box];
}

// step 3: the records, each ✅ when the Internet sees it; the verification when all are there
function records(p, refresh, say) {
  const wrap = el("div", "acme-step");
  wrap.append(el("h4", "", `3️⃣ ${t(p.manual ? "acme.s3_hand" : "acme.s3_auto")}`),
    el("p", "muted", t(p.manual ? "acme.s3_hand_hint" : "acme.s3_auto_hint")));
  const table = el("div", "acme-records");
  table.append(el("b", "", t("acme.type")), el("b", "", t("acme.rec_name")), el("b", "", t("acme.rec_value")), el("b", "", t("acme.rec_state")));
  const marks = [];
  for (const r of p.records) {
    const n = el("span", "acme-code"), v = el("span", "acme-code"), mark = el("span", "", "⏳");
    n.append(el("code", "", r.name), copyButton(r.name));
    v.append(el("code", "", r.value), copyButton(r.value));
    table.append(el("span", "", "TXT"), n, v, mark);
    marks.push(mark);
  }
  if (!p.records.length) table.append(el("span", "", "—"), el("span", "muted", t("acme.none_needed")), el("span", ""), el("span", "", "✅"));
  const state = el("p", "muted", t("acme.looking"));
  const go = el("button", "approve", `✅ ${t("acme.verify")}`);
  const stop = el("button", "", `✖ ${t("acme.cancel")}`);
  const row = el("div", "appr-actions");
  row.append(go, stop);
  wrap.append(table, state, row, el("p", "muted", t("acme.verify_hint")));
  let ready = !p.records.length;
  const look = async () => {
    if (!wrap.isConnected) { clearInterval(timer); return; }
    try {
      const c = await call("/v1/aurora/https/acme/check");
      c.records.forEach((r, i) => { if (marks[i]) marks[i].textContent = r.seen ? "✅" : "⏳"; });
      ready = c.all_seen;
      state.textContent = ready ? t("acme.all_seen") : t("acme.not_yet", { n: c.records.filter((r) => !r.seen).length });
    } catch (e) { state.textContent = e.message; }
  };
  clearInterval(timer);
  if (p.records.length) { look(); timer = setInterval(look, 10000); } else state.textContent = t("acme.all_seen");
  go.addEventListener("click", async () => {
    if (!ready && !confirm(t("acme.verify_anyway"))) return;
    go.disabled = stop.disabled = true;
    clearInterval(timer);
    state.textContent = `🔏 ${t("acme.verifying")}`;
    try {
      const r = await call("/v1/aurora/https/acme/verify", { method: "POST" });
      say(`${t("acme.done", { d: day(r.certificate?.not_after) })}${r.copied?.copied ? ` ${t("acme.copied")}` : ""}${r.copied?.error ? ` ⚠️ ${r.copied.error}` : ""}`);
    } catch (e) { say(t("ev.error", { m: e.message })); }
    await refresh();
  });
  stop.addEventListener("click", async () => {
    clearInterval(timer);
    await call("/v1/aurora/https/acme/order", { method: "DELETE" }).catch(() => null);
    await refresh();
  });
  return wrap;
}

// steps 1 and 2: the names, who writes the record; then the order begins
function begin(s, refresh, say) {
  const wrap = el("div", "acme-step");
  const names = el("input");
  names.value = s.names.join(", ");
  names.placeholder = "example.org, *.example.org";
  const test = el("label", "");
  const tbox = el("input");
  tbox.type = "checkbox";
  tbox.checked = s.staging;
  test.append(tbox, ` 🧪 ${t("acme.test")}`);
  wrap.append(el("h4", "", `1️⃣ ${t("acme.s1")}`), el("p", "muted", t("acme.s1_hint")), names, test);
  wrap.append(el("h4", "", `2️⃣ ${t("acme.s2")}`));
  const ways = el("div", "acme-ways");
  let way = s.manual ? "manual" : "cloudflare";
  const token = el("input");
  token.type = "password";
  token.autocomplete = "off";
  token.placeholder = s.token_set ? t("acme.token_kept") : t("acme.token_ph");
  const tokenRow = el("label", "acme-token");
  tokenRow.append(t("acme.token_label"), token);
  const card = (id, title, hint) => {
    const b = el("button", `acme-way${way === id ? " on" : ""}`);
    b.type = "button";
    b.append(el("b", "", title), el("span", "muted", hint));
    b.addEventListener("click", () => {
      way = id;
      ways.querySelectorAll(".acme-way").forEach((x) => x.classList.toggle("on", x === b));
      tokenRow.hidden = way !== "cloudflare";
    });
    return b;
  };
  ways.append(card("cloudflare", `🤖 ${t("acme.way_auto")}`, t("acme.way_auto_hint")), card("manual", `✋ ${t("acme.way_hand")}`, t("acme.way_hand_hint")));
  tokenRow.hidden = way !== "cloudflare";
  const go = el("button", "approve", `▶️ ${t("acme.start")}`);
  const out = el("p", "muted");
  wrap.append(ways, tokenRow, el("p", "muted", t("acme.token_help")), go, out);
  go.addEventListener("click", async () => {
    if (way === "cloudflare" && !s.token_set && !token.value.trim()) { out.textContent = t("acme.token_needed"); return; }
    go.disabled = true;
    out.textContent = `⏳ ${t(way === "manual" ? "acme.starting_hand" : "acme.starting_auto")}`;
    try {
      await save({ AURORA_ACME_DOMAINS: names.value, AURORA_ACME_STAGING: tbox.checked ? "1" : "0", AURORA_ACME_DNS: way,
        ...(token.value.trim() ? { AURORA_ACME_DNS_TOKEN: token.value.trim() } : {}) });
      await call("/v1/aurora/https/acme/start", { method: "POST" });
      say("");
    } catch (e) { out.textContent = t("ev.error", { m: e.message }); go.disabled = false; return; }
    await refresh();
  });
  return wrap;
}

// 📁 Where the certificate is copied (owner, 3 Nov: «mettimi la parte di autenticazione nella parte dove si imposta il
// percorso di copia… a spunta tipo percorso di rete così espande il percorso riportando l'autenticazione»): a folder of
// this machine, or ticked a NAS folder as smb://… with its NAS user and password (empty: the backup's)
async function copyFolder(s, refresh, say) {
  const all = (await call("/v1/aurora/settings")).settings;
  const val = (k) => String((all.find((x) => x.key === k) || {}).value || "");
  const wrap = el("div", "acme-copy-dir plug-settings");
  wrap.append(el("h4", "", `📁 ${t("acme.copy_dir")}`));
  const net = el("input");
  net.type = "checkbox";
  net.checked = val("AURORA_CERTS_COPY_DIR").startsWith("smb://");
  const tick = el("label", "plug-field plug-check");
  tick.append(net, el("span", "", `🌐 ${t("acme.copy_net")}`));
  const dir = el("input");
  dir.value = val("AURORA_CERTS_COPY_DIR");
  const where = el("label", "plug-field");
  where.append(el("span", "", t("acme.copy_where")), dir);
  const user = el("input");
  user.value = val("AURORA_CERTS_NAS_USER");
  user.placeholder = t("acme.copy_user_hint");
  user.autocomplete = "off";
  const pass = el("input");
  pass.type = "password";
  pass.autocomplete = "new-password";
  pass.placeholder = t("acme.copy_pass_hint");
  const auth = el("div", "acme-copy-auth");
  for (const [label, input] of [[t("acme.copy_user"), user], [t("acme.copy_pass"), pass]]) {
    const r = el("label", "plug-field");
    r.append(el("span", "", label), input);
    auth.append(r);
  }
  const show = () => {
    auth.hidden = !net.checked;
    dir.placeholder = net.checked ? "smb://192.168.1.10/share/folder" : "/path/to/folder";
  };
  net.addEventListener("change", show);
  show();
  // 🎯 a certificate of the copy's own, and 🔑 the p12 with its password (owner, 3 Nov)
  const names = el("input");
  names.value = (s.copy.names || []).join(", ");
  names.placeholder = t("acme.copy_names_hint");
  const namesRow = el("label", "plug-field");
  namesRow.append(el("span", "", `🎯 ${t("acme.copy_names")}`), names);
  const own = s.copy.own;
  const ownLine = el("p", "muted", s.copy.own_error ? `❌ ${s.copy.own_error}`
    : own ? t("acme.copy_own", { n: own.names.join(", "), d: day(own.not_after) }) : t(s.copy.names?.length ? "acme.copy_own_none" : "acme.copy_own_same"));
  const p12 = el("input");
  p12.type = "checkbox";
  p12.checked = s.copy.p12 !== false;
  const p12Row = el("label", "plug-field plug-check");
  p12Row.append(p12, el("span", "", `🔑 ${t("acme.copy_p12")}`));
  const p12Pass = el("input");
  p12Pass.type = "password";
  p12Pass.autocomplete = "new-password";
  p12Pass.placeholder = t(s.copy.p12_password ? "acme.copy_p12_set" : "acme.copy_p12_none");
  const legacy = el("input");
  legacy.type = "checkbox";
  legacy.checked = !!s.copy.legacy;
  const p12Auth = el("div", "acme-copy-auth");
  const pr = el("label", "plug-field");
  pr.append(el("span", "", t("acme.copy_p12_pass")), p12Pass);
  const lr = el("label", "plug-field plug-check");
  lr.append(legacy, el("span", "", t("acme.copy_p12_legacy")));
  p12Auth.append(pr, lr);
  const showP12 = () => { p12Auth.hidden = !p12.checked; };
  p12.addEventListener("change", showP12);
  showP12();
  // 🗓️ when the copy may run (a NAS asleep at night): empty = right after the renewal; Aurora says how many hours of
  // the window fall between the renewal and the certificate's end
  const win = el("input");
  win.value = s.copy.window || "";
  win.placeholder = t("acme.copy_window_hint");
  const winRow = el("label", "plug-field");
  winRow.append(el("span", "", `🗓️ ${t("acme.copy_window")}`), win);
  const advice = el("p", "muted", !s.copy.window ? t("acme.copy_window_none")
    : s.copy.chances === null || s.copy.chances === undefined ? t("acme.copy_window_bad")
      : t(s.copy.chances < 8 ? "acme.copy_window_few" : "acme.copy_window_ok", { n: s.copy.chances }));
  const go = el("button", "", `💾 ${t("acme.copy_save")}`);
  go.type = "button";
  go.addEventListener("click", async () => {
    const d = dir.value.trim();
    if (net.checked && d && !d.startsWith("smb://")) { say(t("acme.copy_need_smb")); return; }
    if (!net.checked && d.startsWith("smb://")) { say(t("acme.copy_need_local")); return; }
    try {
      await save({ AURORA_CERTS_COPY_DIR: d, AURORA_CERTS_COPY_WINDOW: win.value.trim(), AURORA_CERTS_COPY_NAMES: names.value.trim(),
        AURORA_CERTS_P12: p12.checked ? "1" : "0", AURORA_CERTS_P12_LEGACY: legacy.checked ? "1" : "0",
        ...(p12Pass.value ? { AURORA_CERTS_P12_PASSWORD: p12Pass.value } : {}), ...(net.checked ? { AURORA_CERTS_NAS_USER: user.value.trim() } : {}),
        ...(net.checked && pass.value ? { AURORA_CERTS_NAS_PASSWORD: pass.value } : {}) });
      say(t("acme.copy_saved"));
    } catch (e) { say(t("ev.error", { m: e.message })); return; }
    await refresh();
  });
  wrap.append(tick, where, auth, namesRow, ownLine, p12Row, p12Auth, winRow, advice, go);
  return wrap;
}

export async function acmeBox(box, say, refresh) {
  let s;
  try { s = await call("/v1/aurora/https/acme"); } catch (e) { box.replaceChildren(el("p", "error", e.message)); return; }
  const [table, auto, autoBox] = facts(s);
  autoBox.addEventListener("change", async () => { await save({ AURORA_ACME_ENABLED: autoBox.checked ? "1" : "0" }); await refresh(); });
  const guide = el("div", "acme-guide");
  guide.append(el("h4", "acme-guide-title", `🧭 ${t(s.certificate && !s.certificate.error ? "acme.guide_renew" : "acme.guide_get")}`));
  if (s.pending) {
    guide.append(el("p", "muted", t("acme.pending", { n: s.pending.names.join(", "), w: when(s.pending.started) })
      + (s.pending.staging ? ` 🧪 ${t("acme.test_short")}` : "")), records(s.pending, refresh, say));
  } else {
    guide.append(begin(s, refresh, say));
  }
  const parts = [el("h3", "", t("acme.title")), el("p", "muted", t("acme.hint")), table, auto, guide];
  if (s.last.steps && s.last.steps.length) {
    const d = el("details", "");
    d.append(el("summary", "", t("acme.steps")), el("pre", "acme-steps", s.last.steps.join("\n")));
    parts.push(d);
  }
  const more = el("details", "acme-more");
  more.append(el("summary", "", `📁 ${t("acme.more")}`));
  const copy = el("button", "", t("acme.copy_now"));
  copy.disabled = !s.copy.dir;
  copy.addEventListener("click", async () => {
    try { const r = await call("/v1/aurora/https/acme/copy", { method: "POST" }); say(r.error ? t("ev.error", { m: r.error }) : t(r.copied ? "acme.copied" : "acme.copy_same")); }
    catch (e) { say(t("ev.error", { m: e.message })); }
    await refresh();
  });
  more.append(await copyFolder(s, refresh, say), copy,
    await settingsForm(MORE, { title: `⚙️ ${t("acme.settings")}`, onSaved: () => refresh() }));
  parts.push(more);
  box.replaceChildren(...parts);
}
