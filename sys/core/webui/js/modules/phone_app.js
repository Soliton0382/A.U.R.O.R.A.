// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📱 Aurora's phone app (owner, 25 Oct: «il pacchetto apk scaricabile dalla WebUI… un menù apposito che spiega come
// impostarla, magari con qualche screen»): the APK built on this machine (/v1/aurora/app), how to install and set it
// up step by step with the app's own screens, and this Aurora's address and port to type, read from the page itself.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { apply, t } from "../i18n.js";

const STEPS = [                                      // [text key, screenshot or null]
  ["phoneapp.s1", null],
  ["phoneapp.s2", "1_welcome"],
  ["phoneapp.s3", "2_address"],
  ["phoneapp.s4", null],
  ["phoneapp.s5", "3_line"],
  ["phoneapp.s6", null],
];

const BRANDS = ["samsung", "xiaomi", "huawei", "oppo", "other"];

const ago = (s) => (s < 90 ? t("phoneapp.line.now") : s < 5400 ? t("phoneapp.line.min", { n: Math.round(s / 60) })
  : t("phoneapp.line.hours", { n: Math.round(s / 3600) }));

const older = (a, b) => {                            // version a before b
  const x = a.split(".").map(Number), y = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) < (y[i] || 0);
  return false;
};

export default {
  id: "phoneapp",
  icon: "📱",
  title: "nav.phoneapp",

  mount(root) {
    root.classList.add("page");
    useCss("/static/css/phone_app.css");
    root.innerHTML = `<h2 data-i18n="phoneapp.title"></h2><p class="muted" data-i18n="phoneapp.hint"></p>
      <div class="pa-get"></div><div class="pa-lines"></div><ol class="pa-steps"></ol>
      <details class="pa-bg"><summary data-i18n="phoneapp.bg.title"></summary><p data-i18n="phoneapp.bg.intro"></p>
        <ul><li data-i18n="phoneapp.bg.check"></li><li data-i18n="phoneapp.bg.battery"></li><li data-i18n="phoneapp.bg.recent"></li></ul>
        <table class="pa-brands"><tbody></tbody></table></details>
      <p class="muted" data-i18n="phoneapp.tips"></p>`;
    apply(root);
    this.get = root.querySelector(".pa-get");
    this.lines = root.querySelector(".pa-lines");
    const brands = root.querySelector(".pa-brands tbody");          // where each maker hides «run in the background»
    for (const b of BRANDS) {
      const tr = el("tr");
      tr.append(el("th", "", t(`phoneapp.bg.${b}.name`)), el("td", "", t(`phoneapp.bg.${b}`)));
      brands.append(tr);
    }
    const ol = root.querySelector(".pa-steps");
    const port = location.port || "443";
    for (const [key, shot] of STEPS) {
      const li = el("li", "pa-step");
      li.append(el("p", "", t(key, { host: location.hostname, port })));
      if (shot) {
        const img = el("img", "pa-shot");
        img.src = `/static/assets/app/${shot}.webp`;
        img.alt = t(key, { host: location.hostname, port });
        img.loading = "lazy";
        li.append(img);
      }
      ol.append(li);
    }
  },

  async enter() {
    const box = this.get;
    box.replaceChildren(el("p", "muted", "…"));
    let a;
    try { a = await call("/v1/aurora/app"); } catch (e) { box.replaceChildren(el("p", "error", e.message)); return; }
    box.replaceChildren();
    // 📶 is the line of each phone open? (the notifications only arrive while it is)
    // between two requests of the line there is a second or two: a minute without one is a line stopped
    const live = (l) => l.open || l.ago < 90;
    this.lines.replaceChildren(...(a.lines?.length ? a.lines.map((l) => el("p", live(l) ? "pa-line on" : "pa-line",
      t(live(l) ? "phoneapp.line.open" : "phoneapp.line.last", { name: l.name, when: ago(l.ago) })))
      : [el("p", "muted", t("phoneapp.line.none"))]));
    if (a.lines?.some(live)) {                         // 📞 a test call to this user's phones (N45)
      const ring = el("button", "", t("phoneapp.call"));
      ring.addEventListener("click", async () => {
        ring.disabled = true;
        try {
          await call("/v1/aurora/call", { method: "POST", body: JSON.stringify({ reason: t("phoneapp.call_reason") }) });
          ring.textContent = t("phoneapp.call_sent");
        } catch (e) { ring.textContent = e.message; }
        setTimeout(() => { ring.disabled = false; ring.textContent = t("phoneapp.call"); }, 30000);
      });
      this.lines.append(ring);
    }
    const mine = (navigator.userAgent.match(/AuroraApp\/([\d.]+)/) || [])[1];
    if (mine) box.append(el("p", "pa-mine", t(a.available && older(mine, a.version) ? "phoneapp.update" : "phoneapp.using",
                                            { v: mine, n: a.version || "" })));
    if (!a.available) { box.append(el("p", "muted", t("phoneapp.none"))); return; }
    const link = el("a", "pa-download approve", t("phoneapp.download", { v: a.version }));
    link.href = "/v1/aurora/app/download";
    link.setAttribute("download", a.name);
    box.append(link, el("p", "muted pa-sum", t("phoneapp.sum", { mb: (a.size / 1048576).toFixed(2), sha: a.sha256.slice(0, 16) })));
  },
};
