// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Plugins: a grid of icons (green = active, red = off); a click opens the plugin's card with its guide,
// official links, its own settings, its tools (read-only ones can be tried) and its icon.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el, toBase64, useCss } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { autonomySlot } from "./autonomy_box.js";
import { settingsForm } from "./settings_form.js";

const KEEP = new Set(["self", "security"]);    // plg_trash.KEEP: her repairs, the security suite's tools

// a plugin Aurora forged works at once; it becomes official when the admin signs the code from a shell with root's
// rights (owner, 2026-10-08) — the signing key is root's: never from the web
async function signBox(names) {
  const box = el("div", "report plug-sign");
  let cmd = "";
  try { cmd = (await call("/v1/aurora/plugins/signature")).command; } catch { /* not the admin */ }
  box.append(el("p", "warn", `✍️ ${t("plug.unsigned", { names: names.join(", ") })}`));
  if (!cmd) return box;
  const row = el("div", "appr-actions");
  const copy = el("button", "", `📋 ${t("plug.copy")}`);
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(cmd); copy.textContent = `✅ ${t("plug.copied")}`; } catch { /* no clipboard: select it */ }
  });
  row.append(el("code", "", cmd), copy);
  box.append(row, el("p", "muted", t("plug.sign_hint")));
  return box;
}

// The weather's place by the town's name (the owner's colleague, 9 Oct: coordinates — «ma che ne so»): Open-Meteo's
// geocoding fills latitude, longitude, the place's name and the region (MeteoAlarm's warnings); typing them stays possible.
function placeSearch(form) {
  const row = el("div", "plug-field");
  const q = el("input");
  q.placeholder = t("place.hint");
  const go = el("button", "", `🔎 ${t("place.search")}`);
  const list = el("div");
  row.append(el("strong", "", `📍 ${t("place.title")}`), q, go, list);
  const set = (key, v) => { const i = form.querySelector(`[data-key="${key}"]`); if (i) i.value = v; };
  const find = async () => {
    list.replaceChildren(el("span", "muted", "…"));
    try {
      const r = await call(`/v1/aurora/places?q=${encodeURIComponent(q.value.trim())}`);
      list.replaceChildren(...(r.places.length ? r.places.map((pl) => {
        const b = el("button", "", pl.label);
        b.addEventListener("click", () => {
          set("AURORA_WEATHER_LAT", pl.lat); set("AURORA_WEATHER_LON", pl.lon);
          set("AURORA_WEATHER_PLACE", pl.name); if (pl.region) set("AURORA_WEATHER_REGION", pl.region);
          list.replaceChildren(el("span", "muted", t("place.chosen", { p: pl.label })));
        });
        return b;
      }) : [el("span", "muted", t("place.none"))]));
    } catch (e) { list.replaceChildren(el("span", "error", e.message)); }
  };
  go.addEventListener("click", find);
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); find(); } });
  form.querySelector("h4").after(row);
}

const view = {
  id: "plugins",
  icon: "🧩",
  title: "nav.plugins",

  mount(root, ctx) {
    this.ctx = ctx;
    useCss("/static/css/agents.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="plug.title"></h2><p class="muted" data-i18n="plug.hint"></p><div class="plug-grid"></div>`;
    root.querySelector("h2").after(autonomySlot("forge"));   // how free Aurora is, here (owner, 2026-10-08)
    apply(root);
    this.grid = root.querySelector(".plug-grid");
    this.root = root;
  },

  async enter() {
    const code = lang.slice(0, 2);
    const all = await call("/v1/aurora/plugins");
    this.me = await call("/v1/aurora/me").catch(() => ({ admin: true }));
    // a plugin with a page of its own is configured there (owner, 2026-10-16): the grid keeps the general ones
    const plugins = all.filter((p) => !p.page);
    const paged = all.filter((p) => p.page);
    this.root.querySelector(".plug-paged")?.remove();
    if (paged.length) {                              // one button each, to the page where it is set (owner, 2026-10-16)
      const box = el("div", "plug-paged");
      box.append(el("p", "muted", t("plug.paged_hint")));
      const row = el("div", "chips");
      for (const p of paged) {
        const label = document.querySelector(`#nav button[data-view="${p.page}"]`)?.textContent.trim() || p.page;
        const b = el("button", `plug-chip ${p.available ? "on" : "off"}`, `${p.available ? "✅" : p.missing?.length ? "⚠️" : "⏸️"} ${p.name} → ${label}`);
        b.type = "button";
        b.addEventListener("click", () => this.ctx?.show(p.page));
        row.append(b);
      }
      box.append(row);
      this.grid.after(box);
    }
    this.grid.replaceChildren(...plugins.map((p) => {
      const b = el("button", `plug-tile ${p.available ? "on" : "off"}`);
      b.type = "button";
      const img = el("img");
      img.src = p.icon;
      img.alt = "";
      b.append(img, el("span", "name", `${p.forged ? "🔨 " : ""}${p.name}`),
        el("span", "state", `${p.available ? t("plug.on") : (p.enabled && !p.missing.length ? t("plug.stuck") : t("plug.off"))}${p.unsigned ? " · ✍️" : ""}`));
      b.title = p.description?.[code] || p.description?.en || "";
      b.addEventListener("click", () => this.open(p, code));
      return b;
    }));
    this.root?.querySelector(".plug-trash")?.remove();
    this.root?.querySelector(".plug-sign")?.remove();
    if (!this.me.admin) return;                      // the trash is the admin's, like deleting
    const unsigned = plugins.filter((p) => p.unsigned).map((p) => p.name);
    if (unsigned.length) this.grid.before(await signBox(unsigned));
    const items = await call("/v1/aurora/plugins-trash").catch(() => []);
    if (!items.length) return;
    const box = el("details", "plug-trash");
    box.append(el("summary", "", `🗑️ ${t("plug.trash", { n: items.length })}`));
    for (const it of items) {
      const row = el("div", "appr-actions");
      const back = el("button", "", `↩️ ${t("plug.restore")}`);
      back.addEventListener("click", async () => {
        try { await call(`/v1/aurora/plugins-trash/${it.id}/restore`, { method: "POST" }); this.enter(); bus.emit("plugins", {}); }
        catch (e) { alert(e.message); }
      });
      const gone = el("button", "danger", `✖️ ${t("plug.purge")}`);
      gone.addEventListener("click", async () => {
        if (!confirm(t("plug.purge_q", { name: it.name }))) return;
        try { await call(`/v1/aurora/plugins-trash/${it.id}/purge`, { method: "POST" }); this.enter(); }
        catch (e) { alert(e.message); }
      });
      row.append(el("span", "", `${it.name} · ${new Date(it.at * 1000).toLocaleString()}`), back, gone);
      box.append(row);
    }
    this.grid.after(box);
  },

  async open(p, code) {
    const dlg = el("dialog", "modal plug-modal");
    const close = el("button", "icon close", "✕");
    close.addEventListener("click", () => { dlg.close(); dlg.remove(); this.reshow(); });
    const head = el("div", "plug-head");
    const img = el("img");
    img.src = p.icon;
    head.append(img, el("h3", "", `${p.name} · v${p.version || "?"}`), close);
    dlg.append(head, el("p", "", p.description?.[code] || p.description?.en || ""));
    // switched on but not running: said as such, with the reason from its stderr (the owner's colleague, 9 Oct: «me li
    // da tutti spenti ma quando clicco su uno c'è solo il pulsante spegni»)
    const stuck = p.enabled && !p.available && !p.missing.length;
    const state = !p.enabled ? t("plug.state.disabled") : p.missing.length ? t("plug.state.missing", { keys: p.missing.join(", ") })
      : stuck ? t("plug.state.stuck", { e: p.why || p.error || "?" }) : p.error ? t("plug.state.error", { e: p.error }) : t("plug.state.ok", { n: p.tools.length });
    const sw = el("button", "", p.enabled ? t("plug.disable") : t("plug.enable"));
    sw.addEventListener("click", async () => {
      await call(`/v1/aurora/plugins/${p.name}/${p.enabled ? "disable" : "enable"}`, { method: "POST" });
      dlg.close(); dlg.remove(); this.reshow();
      bus.emit("plugins", {});                       // the menu follows: a plugin's page appears or goes
    });
    const stRow = el("div", "appr-actions");
    stRow.append(el("span", `pill ${p.available ? "ok" : "bad"}`, p.available ? t("plug.on") : stuck ? t("plug.stuck") : t("plug.off")), el("span", "", state));
    if (stuck && this.me.admin) {
      const again = el("button", "approve", `🔄 ${t("plug.retry")}`);
      again.addEventListener("click", async () => {
        again.disabled = true;
        await call(`/v1/aurora/plugins/${p.name}/retry`, { method: "POST" });
        dlg.close(); dlg.remove(); this.reshow();
      });
      stRow.append(again);
    }
    if (this.me.admin) {                            // switching on/off and sharing are the admin's (multi-user)
      const share = el("label", "plug-share");
      const box = el("input");
      box.type = "checkbox";
      box.checked = !!p.users;
      box.addEventListener("change", async () => {
        try { await call(`/v1/aurora/plugins/${p.name}/${box.checked ? "share" : "unshare"}`, { method: "POST" }); p.users = box.checked; }
        catch (e) { box.checked = !box.checked; alert(e.message); }
      });
      share.append(box, el("span", "", t("plug.users")));
      stRow.append(sw, share);
      if (!KEEP.has(p.name)) {                      // deleted into the trash: restored from the foot of this page
        const del = el("button", "danger", `🗑️ ${t("plug.delete")}`);
        del.addEventListener("click", async () => {
          if (!confirm(t("plug.delete_q", { name: p.name }))) return;
          try { await call(`/v1/aurora/plugins/${p.name}/delete`, { method: "POST" }); }
          catch (e) { alert(e.message); return; }
          dlg.close(); dlg.remove(); this.reshow();
          bus.emit("plugins", {});
        });
        stRow.append(del);
      }
    }
    dlg.append(stRow);
    if (this.me.admin && p.install) {               // 📦 what it brings (plg_deps, ROADMAP 101): in its own folder, never Aurora's
      const st = p.install;
      const what = [...st.needs.python.map((r) => r.split(" ")[0]), ...st.needs.programs.map((x) => x.name)].join(", ");
      const row = el("div", "appr-actions");
      const kb = (n) => (n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`);
      row.append(el("span", `pill ${st.installed ? "ok" : "bad"}`, st.installed ? `📦 ${kb(st.bytes)}` : "📦"),
        el("span", "", t(st.installed ? "plug.deps_in" : "plug.deps_out", { what })));
      const go = el("button", st.installed ? "" : "approve", st.installed ? t("plug.deps_remove") : t("plug.deps_install"));
      go.addEventListener("click", async () => {
        go.disabled = true;
        go.textContent = "…";
        try { await call(`/v1/aurora/plugins/${p.name}/${st.installed ? "uninstall" : "install"}`, { method: "POST" }); }
        catch (e) { alert(e.message); }
        dlg.close(); dlg.remove(); this.reshow();
      });
      row.append(go);
      dlg.append(row);
    }
    if (this.me.admin && p.forged) dlg.append(el("p", "muted", t("plug.forged", { need: p.forged_need || "" })));
    if (this.me.admin && p.unsigned) dlg.append(await signBox([p.name]));
    if (p.name === "backup") {                      // the backup itself: last copy, next one, 💾 Run now
      const { backupRow, restoreBox } = await import("../backup.js");
      const row = await backupRow();
      if (row) dlg.append(row, restoreBox());
    }

    // guide and official links
    const setup = p.setup || {};
    if (setup[code] || setup.en) {
      const g = el("details", "report");
      g.open = !p.available;
      g.append(el("summary", "", `📘 ${t("plug.guide")}`), renderMarkdown(setup[code] || setup.en));
      if (setup.links?.length) {
        const ul = el("ul");
        for (const l of setup.links) {
          const a = el("a", "", l.label);
          a.href = l.url; a.target = "_blank"; a.rel = "noopener noreferrer";
          const li = el("li"); li.append(a); ul.append(li);
        }
        g.append(el("div", "muted", t("plug.links")), ul);
      }
      dlg.append(g);
    }

    // 🔗 an account connected from here (api/oauth): the provider's sign-in, back to this WebUI, the token kept
    if (p.oauth) {                                   // each person's own account (the settings are scope user)
      const box = el("div", "report oauth-box");
      const go = el("button", "approve", `🔗 ${t(p.available ? "oauth.again" : "oauth.connect", { name: p.social_label || p.name })}`);
      go.addEventListener("click", async () => {
        go.disabled = true;
        try { location.href = (await call(`/v1/aurora/oauth/${p.oauth}/start`, { method: "POST" })).url; }
        catch (e) { go.disabled = false; box.append(el("p", "error", e.message)); }
      });
      box.append(el("p", p.available ? "ok" : "muted", t(p.available ? "oauth.connected" : "oauth.hint")), go);
      dlg.append(box);
    }

    // the plugin's own settings (settings_form.js: the same box a page uses for its own)
    if (p.settings?.length) {
      // devices connected to the machine: the camera and the microphone are chosen from a list
      const found = p.name === "senses" ? await call("/v1/aurora/senses/devices").catch(() => null) : null;
      const choices = found ? { AURORA_SENSES_CAMERA: found.cameras, AURORA_SENSES_MIC: found.microphones } : {};
      dlg.append(await settingsForm(p.settings, { choices,
        after: p.settings.includes("AURORA_WEATHER_LAT") ? placeSearch : null,     // the town by its name, not coordinates
        onSaved: (r, restarted) => {
          bus.emit("plugins", {});                        // its account filled: its page may appear now
          if (restarted) { dlg.close(); dlg.remove(); this.reshow(); bus.emit("plugins", {}); }
        } }));
    }

    // tools: effect, and a "Try" for read-only tools without required arguments
    if (p.tools.length) {
      const d = el("details", "report");
      d.append(el("summary", "", `🔧 ${t("plug.tools", { n: p.tools.length })}`));
      for (const tl of p.tools) {
        const r = el("div", "tool-row");
        r.append(el("span", `pill effect-${tl.effect}`, t(`appr.effect.${tl.effect}`)), el("code", "", tl.name),
          el("span", "muted", tl.description.split("\n")[0].slice(0, 140)));
        if (tl.effect === "read" && !(tl.required || []).length && p.available) {
          const tryB = el("button", "", `▶ ${t("plug.try")}`);
          const res = el("pre", "try-out hidden");
          tryB.addEventListener("click", async () => {
            tryB.disabled = true;
            res.classList.remove("hidden");
            res.textContent = "…";
            try {
              const o = await call(`/v1/aurora/plugins/${p.name}/try/${tl.name}`, { method: "POST" });
              res.textContent = `${o.ok ? "✔" : "✘"} ${o.seconds} s\n${o.text}`;
            } catch (e) { res.textContent = `✘ ${e.message}`; }
            tryB.disabled = false;
          });
          r.append(tryB, res);
        }
        d.append(r);
      }
      dlg.append(d);
    }

    // icon: upload an image or give a web link
    const ic = el("details", "report");
    ic.append(el("summary", "", `🖼️ ${t("plug.icon")}`));
    const file = el("input"); file.type = "file"; file.accept = "image/*";
    const url = el("input"); url.placeholder = "https://…/icon.png";
    const setIcon = el("button", "", t("plug.icon.set"));
    const icOut = el("span", "muted");
    setIcon.addEventListener("click", async () => {
      try {
        const body = file.files[0] ? { data: await toBase64(file.files[0]) } : { url: url.value.trim() };
        await call(`/v1/aurora/plugins/${p.name}/icon`, { method: "POST", body: JSON.stringify(body) });
        img.src = `${p.icon.split("?")[0]}?v=${Date.now()}`;
        icOut.textContent = t("plug.icon.done");
      } catch (e) { icOut.textContent = t("ev.error", { m: e.message }); }
    });
    ic.append(file, url, setIcon, icOut);
    dlg.append(ic);

    document.body.append(dlg);
    dlg.showModal();
  },
  // the grid again only where it is shown: the same window opens from a plugin's own page (plugin_slot.js)
  reshow() { if (this.root?.isConnected) this.enter(); else bus.emit("plugins", {}); },
};
export default view;

// a plugin's window from any page (owner, 2026-10-16: «se hanno una pagina tanto vale avere le configurazioni lì
// dentro»): the same window as the Plugins page's, one code for both
export async function openPlugin(name) {
  view.me = view.me || await call("/v1/aurora/me").catch(() => ({ admin: true }));
  const p = (await call("/v1/aurora/plugins")).find((x) => x.name === name);
  if (p) view.open(p, lang.slice(0, 2));
}
