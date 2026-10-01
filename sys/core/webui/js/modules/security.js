// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Firewall incidents: severity, public registry data about the source network, Aurora's report
// with the defensive actions she recommends; the owner closes them.
import { call } from "../api.js";
import { clock, el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { renderMarkdown } from "../md.js";

const SEV = { high: "bad", medium: "warn", low: "ok" };

export default {
  id: "security",
  icon: "🛡️",
  title: "nav.security",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="sec.title"></h2><p class="muted" data-i18n="sec.hint"></p>
      <h3 class="setting-cat" data-i18n="sec.open"></h3><div class="open"></div>
      <h3 class="setting-cat" data-i18n="sec.closed"></h3><div class="closed"></div>`;
    apply(root);
    this.open = root.querySelector(".open");
    this.closed = root.querySelector(".closed");
  },

  card(i) {
    const c = el("details", "report");
    c.open = i.status === "open";
    const head = el("summary");
    head.append(el("span", `pill ${SEV[i.severity] || "warn"}`, t(`sec.sev.${i.severity}`)),
      el("span", "", ` ${t(`sec.kind.${i.kind}`)} · ${i.source}${i.internal ? " (" + t("sec.internal") + ")" : ""} · `
        + `${i.count} ${t("sec.events")} · ${clock(i.received)}`));
    c.append(head);
    if (i.intel) for (const [k, v] of Object.entries(i.intel)) c.append(el("div", "muted", `${k}: ${v}`));
    c.append(i.report ? renderMarkdown(i.report) : el("p", "muted", t("sec.pending")));
    if (i.samples?.length) {
      const d = el("details");
      d.append(el("summary", "", t("sec.samples")), el("pre", "", i.samples.join("\n")));
      c.append(d);
    }
    if (i.status === "open") {
      const b = el("button", "", `✔ ${t("sec.close")}`);
      b.addEventListener("click", async () => { await call(`/v1/aurora/incidents/${i.id}/close`, { method: "POST" }); this.enter(); });
      c.append(b);
    }
    return c;
  },

  async enter() {
    const all = await call("/v1/aurora/incidents");
    const open = all.filter((i) => i.status === "open"), closed = all.filter((i) => i.status !== "open").slice(0, 30);
    this.open.replaceChildren(...(open.length ? open.map((i) => this.card(i)) : [el("p", "muted", t("sec.none"))]));
    this.closed.replaceChildren(...closed.map((i) => this.card(i)));
  },
};
