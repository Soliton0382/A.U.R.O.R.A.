// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔭 Astro (ROADMAP 79 step 0; owner, 2026-10-16: «una parte nel menù chiamata astro, con il menù di configurazione del
// plugin che indica lo script da usare, il comando da utilizzare e dove si trova il file txt che Aurora deve
// digerire»): 1. the script for the telescope's PC and its command; 2. the inventory and the manuals uploaded to the
// person's astro folder; 3. the equipment as Aurora reads it — scales, guiding, darks, what to check.
import { call } from "../api.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { liveTab } from "./astro_live.js";
import { nightsTab } from "./astro_nights.js";
import { adviceTab } from "./astro_advice.js";
import { pluginSlot } from "./plugin_slot.js";
import { settingsForm } from "./settings_form.js";

const n = (x, d = 2) => (x == null ? "—" : Number(x).toLocaleString(undefined, { maximumFractionDigits: d }));

function card(title, rows) {
  const c = el("section", "astro-card");
  c.append(el("h4", "", title));
  const dl = el("dl");
  for (const [k, v] of rows) if (v !== undefined && v !== null && v !== "") { dl.append(el("dt", "", k), el("dd", "", String(v))); }
  c.append(dl);
  return c;
}

export default {
  id: "astro",
  icon: "🔭",
  title: "nav.astro",
  plugin: "astro",                    // in the menu only when that plugin is on

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="nav.astro"></h2><p class="muted" data-i18n="astro.hint"></p>
      <div class="prj-tabs astro-tabs"><button type="button" class="cat-chip on" data-tab="gear" data-i18n="astro.tab.gear"></button><button type="button" class="cat-chip" data-tab="live" data-i18n="astro.tab.live"></button><button type="button" class="cat-chip" data-tab="nights" data-i18n="astro.tab.nights"></button><button type="button" class="cat-chip" data-tab="advice" data-i18n="astro.tab.advice"></button></div>
      <div class="astro-tab" data-tab="gear">
        <h3 class="setting-cat" data-i18n="astro.step1"></h3><div class="astro-script"></div>
        <h3 class="setting-cat" data-i18n="astro.step2"></h3><div class="astro-files"></div>
        <h3 class="setting-cat" data-i18n="astro.step3"></h3><div class="astro-profile"></div></div>
      <div class="astro-tab" data-tab="live" hidden><div class="astro-live"></div></div>
      <div class="astro-tab" data-tab="nights" hidden><div class="astro-nights"></div></div>
      <div class="astro-tab" data-tab="advice" hidden><div class="astro-advice"></div></div>`;
    root.querySelector("h2").after(pluginSlot("astro"));
    apply(root);
    this.root = root;
    // the tabs (owner, 2026-10-16: «una nuova tab per la pianificazione e il monitoraggio in tempo reale»)
    root.querySelectorAll(".astro-tabs button").forEach((b) => b.addEventListener("click", () => this.tab(b.dataset.tab)));
  },

  tab(id) {
    this.root.querySelectorAll(".astro-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === id));
    this.root.querySelectorAll(".astro-tab").forEach((d) => { d.hidden = d.dataset.tab !== id; });
    if (id === "live") {
      this.live ||= liveTab(this.root.querySelector(".astro-live"), this.scale);
      this.live.start();
    } else this.live?.stop();
    if (id === "nights") nightsTab(this.root.querySelector(".astro-nights"));
    if (id === "advice") adviceTab(this.root.querySelector(".astro-advice"));
  },

  async enter() {
    let d;
    try { d = await call("/v1/aurora/astro"); } catch (e) { this.root.querySelector(".astro-profile").textContent = e.message; return; }
    this.drawScript(d);
    this.drawFiles(d);
    this.drawProfile(d);
    this.scale = d.profile?.rig?.scale_arcsec_px || null;    // the imaging scale: what the guiding is judged against
  },

  drawScript(d) {
    const box = this.root.querySelector(".astro-script");
    const get = el("button", "primary", `⬇️ ${t("astro.download", { f: d.script })}`);
    get.addEventListener("click", async () => {         // read through call(), then saved as a file
      try {
        const s = await call("/v1/aurora/astro/script?as_json=true");
        const a = el("a");
        a.href = URL.createObjectURL(new Blob([s.text], { type: "text/plain" }));
        a.download = d.script;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      } catch (e) { alert(e.message); }
    });
    const getRow = el("div", "appr-actions");
    getRow.append(get);
    const cmd = el("code", "astro-cmd", d.command);
    const copy = el("button", "", `📋 ${t("astro.copy")}`);
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(d.command); copy.textContent = `✅ ${t("astro.copied")}`; } catch { /* the text is there to copy */ }
    });
    const row = el("div", "appr-actions");
    row.append(cmd, copy);
    box.replaceChildren(el("p", "", t("astro.script_how")), getRow, el("p", "muted", t("astro.script_run")), row,
      el("p", "muted", t("astro.script_after")));
  },

  drawFiles(d) {
    const box = this.root.querySelector(".astro-files");
    const pick = el("input");
    pick.type = "file";
    pick.multiple = true;
    pick.accept = ".txt,.md,.pdf,.csv,.json,.xml,.log";
    const out = el("span", "muted");
    pick.addEventListener("change", async () => {
      for (const f of pick.files) {
        out.textContent = `${f.name}…`;
        try {
          await call("/v1/aurora/astro/files", { method: "POST", headers: { "X-File-Name": f.name, "Content-Type": "application/octet-stream" }, body: f });
        } catch (e) { out.textContent = `${f.name}: ${e.message}`; return; }
      }
      out.textContent = "";
      this.enter();
    });
    const label = el("button", "approve", `📎 ${t("astro.upload")}`);
    label.addEventListener("click", () => pick.click());
    pick.hidden = true;
    const list = el("div", "astro-file-list");
    for (const f of d.files) {
      const r = el("div", "acc-row");
      const del = el("button", "", "🗑️");
      del.title = t("astro.remove");
      del.addEventListener("click", async () => {
        if (!confirm(t("astro.remove_q", { f: f.name }))) return;
        try { await call(`/v1/aurora/astro/files/${encodeURIComponent(f.name)}`, { method: "DELETE" }); this.enter(); } catch (e) { alert(e.message); }
      });
      r.append(el("span", "", `${f.inventory ? "🧾" : "📄"} ${f.name}`), el("span", "muted", `${Math.max(1, Math.round(f.bytes / 1024))} KB`), del);
      list.append(r);
    }
    if (!d.files.length) list.append(el("p", "muted", t("astro.no_files")));
    const bar = el("div", "appr-actions");
    bar.append(label, pick, out);
    box.replaceChildren(el("p", "muted", t("astro.folder", { f: d.folder })), bar, list);
    settingsForm(["AURORA_ASTRO_DARKS_DIR", "AURORA_ASTRO_DARKS_TEMP"], { title: `🌑 ${t("astro.darks_dir")}`, onSaved: () => this.enter() })
      .then((form) => box.append(form)).catch(() => {});
  },

  drawProfile(d) {
    const box = this.root.querySelector(".astro-profile");
    const p = d.profile;
    if (!p) { box.replaceChildren(el("p", "muted", t("astro.no_profile"))); return; }
    const r = p.rig, g = r.guiding || {};
    const cards = el("div", "astro-cards");
    cards.append(
      card(`🔭 ${t("astro.optics")}`, [[t("astro.telescope"), r.telescope], [t("astro.focal"), r.focal_mm && `${n(r.focal_mm, 0)} mm  f/${n(r.focal_ratio, 1)}`],
        [t("astro.mount"), r.mount], [t("astro.driver"), r.mount_driver], [t("astro.focuser"), r.focuser],
        [t("astro.filters"), [r.filter_wheel, (r.filters || []).join(", ")].filter(Boolean).join(" · ")]]),
      card(`📷 ${t("astro.camera")}`, [[t("astro.model"), r.camera], [t("astro.pixel"), r.pixel_um && `${n(r.pixel_um)} µm`],
        [t("astro.scale"), r.scale_arcsec_px && `${n(r.scale_arcsec_px)}″/px`], ["Gain / offset", r.gain != null ? `${r.gain} / ${r.offset}` : ""],
        [t("astro.cooling"), r.cooling_c != null ? `${n(r.cooling_c, 1)} °C` : ""], [t("astro.images"), [r.images, r.file_type].filter(Boolean).join(" · ")]]),
      card(`🎯 ${t("astro.guiding")}`, [[t("astro.profile"), g.profile], [t("astro.camera"), g.camera],
        [t("astro.focal"), g.focal_mm && `${n(g.focal_mm, 0)} mm`], [t("astro.scale"), g.scale_arcsec_px && `${n(g.scale_arcsec_px)}″/px (${n(g.ratio, 1)}× ${t("astro.vs_imaging")})`],
        [t("astro.exposure"), g.exposure_ms && `${n(g.exposure_ms / 1000, 1)} s`], ["RA / DEC", g.ra_algorithm ? `${g.ra_algorithm} / ${g.dec_algorithm}` : ""],
        [t("astro.aggression"), g.aggression != null ? `${n(g.aggression * 100, 0)} %` : ""]]),
      card(`🧭 ${t("astro.solving")}`, [[t("astro.solver"), r.solver], [t("astro.catalogs"), (p.astap.databases || []).join(" ")],
        [t("astro.site"), r.site ? `${r.site.lat}°, ${r.site.lon}°, ${n(r.site.elevation_m, 0)} m (${t("astro.rounded")})` : ""],
        [t("astro.flip"), r.meridian_flip?.MinutesAfterMeridian != null ? t("astro.flip_v", { a: r.meridian_flip.MinutesAfterMeridian, b: r.meridian_flip.MaxMinutesAfterMeridian }) : ""]]),
    );
    const L = p.links || {};
    if ((L.servers || []).length) {                       // script 3: the programs' own servers, as the PC tried them
      cards.append(card(`🔌 ${t("astro.links")}`, [
        ...L.servers.map((s) => [s.name, s.ok ? `✅ ${s.text || t("astro.answers")}` : `❌ ${t("astro.no_answer")}`]),
        [t("astro.listening"), (L.listening || []).map((x) => `${x.program} ${x.proto}/${x.port}${x.network ? "" : ` (${t("astro.local_only")})`}`).join(", ")],
        [t("astro.network"), [(L.addresses || []).join(", "), (L.profiles || []).join(", ")].filter(Boolean).join(" · ")]]));
    }
    const lib = p.library;
    const darks = el("section", "astro-card wide");
    darks.append(el("h4", "", `🌑 ${t("astro.darks")}`));
    if (lib) {
      darks.append(el("p", "", t("astro.darks_match", { g: lib.gain, o: lib.offset, e: lib.match.map((x) => `${n(x, 0)} s`).join(", ") || "—" })));
      const list = el("ul", "mask-rule-list");
      for (const x of lib.darks) list.append(el("li", x.old ? "muted" : "", `${x.file} — ${n(x.exposure_s, 0)} s, gain ${x.gain ?? "?"}, offset ${x.offset ?? "?"}, ${x.temp_c != null ? `${n(x.temp_c, 1)} °C, ` : ""}${x.frames ?? "?"} ${t("astro.frames")}, ${x.date || "?"}${x.old ? ` (${t("astro.old")})` : ""}`));
      darks.append(list);
    } else if (p.darks.length) {
      darks.append(...p.darks.map((x) => el("p", "", `${x.folder}: ${x.files}`)));
    } else darks.append(el("p", "muted", t("astro.darks_none")));
    cards.append(darks);
    const soft = el("details", "astro-soft");
    soft.append(el("summary", "", `🧩 ${t("astro.software")} (${p.software.length})`),
      ...p.software.map((s) => el("div", "", `${s.name} ${s.version || ""}`)));
    const checks = el("div");
    if (p.checks.length) {
      checks.append(el("h4", "", `⚠️ ${t("astro.checks")}`), ...p.checks.map((c) => {
        const r = el("p", "warn");
        r.append(el("strong", "", c.what), ` — ${c.why}`);
        return r;
      }));
    }
    box.replaceChildren(el("p", "muted", t("astro.read_from", { f: p.file, w: p.written, s: p.system })), cards, checks, soft);
  },
};
