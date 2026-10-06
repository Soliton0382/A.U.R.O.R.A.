// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Plugins: a grid of icons (green = active, red = off); a click opens the plugin's card with its guide,
// official links, its own settings, its tools (read-only ones can be tried) and its icon.
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el, toBase64, useCss } from "../dom.js";
import { apply, lang, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";
import { restartPrompt } from "../restart.js";

export default {
  id: "plugins",
  icon: "🧩",
  title: "nav.plugins",

  mount(root) {
    useCss("/static/css/agents.css");
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="plug.title"></h2><p class="muted" data-i18n="plug.hint"></p><div class="plug-grid"></div>`;
    apply(root);
    this.grid = root.querySelector(".plug-grid");
  },

  async enter() {
    const code = lang.slice(0, 2);
    const plugins = await call("/v1/aurora/plugins");
    this.me = await call("/v1/aurora/me").catch(() => ({ admin: true }));
    this.grid.replaceChildren(...plugins.map((p) => {
      const b = el("button", `plug-tile ${p.available ? "on" : "off"}`);
      b.type = "button";
      const img = el("img");
      img.src = p.icon;
      img.alt = "";
      b.append(img, el("span", "name", p.name), el("span", "state", p.available ? t("plug.on") : t("plug.off")));
      b.title = p.description?.[code] || p.description?.en || "";
      b.addEventListener("click", () => this.open(p, code));
      return b;
    }));
  },

  async open(p, code) {
    const dlg = el("dialog", "modal plug-modal");
    const close = el("button", "icon close", "✕");
    close.addEventListener("click", () => { dlg.close(); dlg.remove(); this.enter(); });
    const head = el("div", "plug-head");
    const img = el("img");
    img.src = p.icon;
    head.append(img, el("h3", "", `${p.name} · v${p.version || "?"}`), close);
    dlg.append(head, el("p", "", p.description?.[code] || p.description?.en || ""));
    const state = !p.enabled ? t("plug.state.disabled") : p.missing.length ? t("plug.state.missing", { keys: p.missing.join(", ") })
      : p.error ? t("plug.state.error", { e: p.error }) : t("plug.state.ok", { n: p.tools.length });
    const sw = el("button", "", p.enabled ? t("plug.disable") : t("plug.enable"));
    sw.addEventListener("click", async () => {
      await call(`/v1/aurora/plugins/${p.name}/${p.enabled ? "disable" : "enable"}`, { method: "POST" });
      dlg.close(); dlg.remove(); this.enter();
      bus.emit("plugins", {});                       // the menu follows: a plugin's page appears or goes
    });
    const stRow = el("div", "appr-actions");
    stRow.append(el("span", `pill ${p.available ? "ok" : "bad"}`, p.available ? t("plug.on") : t("plug.off")), el("span", "", state));
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
    }
    dlg.append(stRow);
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

    // the plugin's own settings (the same .env values as in Settings)
    if (p.settings?.length) {
      const all = (await call("/v1/aurora/settings")).settings;
      const specs = all.filter((s) => p.settings.includes(s.key));
      const form = el("div", "plug-settings");
      form.append(el("h4", "", `⚙️ ${t("plug.settings")}`));
      // devices connected to the machine: the camera and the microphone are chosen from a list
      const found = p.name === "senses" ? await call("/v1/aurora/senses/devices").catch(() => null) : null;
      const choices = found ? { AURORA_SENSES_CAMERA: found.cameras, AURORA_SENSES_MIC: found.microphones } : {};
      for (const s of specs) {
        const row = el("label", "plug-field");
        const list = choices[s.key];
        // yes/no as a checkbox, a choice as a menu, a number as a number (owner, 2026-10-04)
        const on = (v) => ["1", "true", "yes", "on"].includes(String(v).toLowerCase());
        if (s.type === "bool") {
          const box = el("input");
          box.type = "checkbox";
          box.checked = on(s.value);
          box.dataset.key = s.key;
          box.dataset.bool = "1";
          box.dataset.orig = on(s.value) ? "1" : "0";
          const r = el("label", "plug-field plug-check");
          r.append(box, el("span", "", s[code] || s.en));
          form.append(r);
          continue;
        }
        const input = el(list || s.type === "enum" ? "select" : "input");
        if (!list && s.type === "enum") for (const c of s.choices) input.append(el("option", "", c));
        if (s.type === "int") { input.type = "number"; if (s.min !== undefined) input.min = s.min; if (s.max !== undefined) input.max = s.max; }
        if (list) {
          for (const d of [{ id: "auto", name: t("plug.device.auto") }, ...list]) {
            const o = el("option", "", d.id === "auto" ? d.name : `${d.name} — ${d.id}`);
            o.value = d.id;
            input.append(o);
          }
          if (s.value && ![...input.options].some((o) => o.value === s.value)) input.append(el("option", "", s.value));
        }
        input.value = s.secret ? "" : s.value;
        input.placeholder = s.secret ? (s.value ? t("plug.secret.set") : t("plug.secret.empty")) : (s.recommended || "");
        if (s.secret) input.type = "password";
        input.dataset.key = s.key;
        input.dataset.secret = s.secret ? "1" : "";
        input.dataset.orig = s.secret ? "" : s.value;
        row.append(el("code", "", s.key), input, el("span", "muted", s[code] || s.en));
        form.append(row);
      }
      const save = el("button", "approve", `💾 ${t("settings.save")}`);
      const out = el("span", "muted");
      save.addEventListener("click", async () => {
        const changes = {};
        form.querySelectorAll("[data-key]").forEach((i) => {
          if (i.dataset.bool) { const v = i.checked ? "1" : "0"; if (v !== i.dataset.orig) changes[i.dataset.key] = v; return; }
          if (i.dataset.secret ? i.value !== "" : i.value !== i.dataset.orig) changes[i.dataset.key] = i.value;
        });
        if (!Object.keys(changes).length) { out.textContent = t("settings.none"); return; }
        try {
          const r = await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify(changes) });
          out.textContent = t("settings.saved", { keys: r.changed.join(", "), services: r.restart.join(", ") || "—" });
          if (await restartPrompt(r.restart)) { dlg.close(); dlg.remove(); this.enter(); }
        } catch (e) { out.textContent = t("ev.error", { m: e.message }); }
      });
      const actions = el("div", "appr-actions");
      actions.append(save, out);
      form.append(actions);
      dlg.append(form);
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
};
