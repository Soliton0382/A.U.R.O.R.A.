// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔒 HTTPS and devices (owner, 2026-10-08: the certificate chosen from the WebUI; Aurora opened from the phone): the
// addresses Aurora answers to, with a QR code for the phone; the certificate in use; the owner's own certificate
// (checked by the server before use, everything put back if Caddy refuses it); back to Caddy's local authority; the
// ports (owner, 2026-10-09: «sulla 443 ho altri servizi»): checked, then Aurora moves and the page says where.
import { call } from "../api.js";
import { el } from "../dom.js";
import { apply, t } from "../i18n.js";
import { qrSvg } from "../qr.js";

const readText = (file) => (file ? file.text() : Promise.resolve(""));

export default {
  id: "https",
  icon: "🔒",
  title: "nav.https",

  mount(root) {
    root.classList.add("page");
    root.innerHTML = `<h2 data-i18n="https.title"></h2><p class="muted" data-i18n="https.hint"></p>
      <section class="https-names"></section><section class="https-ports"></section><section class="https-cert"></section>
      <section class="https-own"></section>
      <p class="muted https-msg" role="status"></p>`;
    apply(root);
    this.root = root;
    this.msg = root.querySelector(".https-msg");
  },

  say(text) { this.msg.textContent = text; },

  async enter() {
    let s;
    try { s = await call("/v1/aurora/https"); } catch (e) { this.say(t("ev.error", { m: e.message })); return; }
    this.names(s);
    this.ports(s);
    this.cert(s);
    this.own(s);
  },

  names(s) {
    const box = this.root.querySelector(".https-names");
    const list = el("ul");
    for (const u of s.urls) {
      const li = el("li");
      const a = el("a", "", u);
      a.href = u;
      li.append(a);
      list.append(li);
    }
    const phone = s.urls.find((u) => !u.includes("//localhost"));
    const input = el("input");
    input.id = "https-aliases";
    input.value = s.names.slice(1).join(", ");
    input.placeholder = "192.168.1.20, casa.local";
    const save = el("button", "approve", t("https.save_names"));
    save.addEventListener("click", () => this.saveNames(input.value));
    const row = el("div", "appr-actions");
    row.append(input, save);
    for (const sug of s.suggest || []) {
      const add = el("button", "", `➕ ${sug}`);
      add.addEventListener("click", () => this.saveNames(`${input.value},${sug}`));
      row.append(add);
    }
    box.replaceChildren(el("h3", "", t("https.names")), list, el("p", "muted", t("https.names_hint")), row);
    if (phone) box.append(el("p", "", t("https.phone_qr")), qrSvg(phone, 180));
  },

  ports(s) {
    const box = this.root.querySelector(".https-ports");
    if (s.docker) {                                   // Docker maps the ports: chosen in docker/.env
      box.replaceChildren(el("h3", "", t("https.ports")),
        el("p", "", `HTTPS ${s.https_port} · HTTP ${s.http_port}`), el("p", "muted", t("https.ports_docker")));
      return;
    }
    const field = (id, value, label) => {
      const input = el("input");
      input.id = id;
      input.type = "number";
      input.min = "1"; input.max = "65535";
      input.value = value;
      const l = el("label", "", label);
      l.htmlFor = id;
      return [l, input];
    };
    const [lh, https] = field("https-port", s.https_port, t("https.port_https"));
    const [lp, http] = field("http-port", s.http_port, t("https.port_http"));
    const go = el("button", "approve", t("https.ports_save"));
    go.addEventListener("click", async () => {
      const body = { https: Number(https.value), http: Number(http.value) };
      if (body.https === s.https_port && body.http === s.http_port) return;
      if (!confirm(t("https.ports_q", { p: body.https }))) return;
      this.say(t("https.applying"));
      try {
        const r = await call("/v1/aurora/https/ports", { method: "PUT", body: JSON.stringify(body) });
        // this page's address stops answering: the new one, to open (the key is asked again there)
        const list = el("ul");
        for (const u of r.urls) { const li = el("li"); const a = el("a", "", u); a.href = u; li.append(a); list.append(li); }
        box.replaceChildren(el("h3", "", t("https.ports")), el("p", "", t("https.ports_moved")), list,
          el("p", "muted", t("https.ports_after")));
        this.say("");
      } catch (e) { this.say(t("ev.error", { m: e.message })); }
    });
    const row = el("div", "appr-actions");
    row.append(lh, https, lp, http, go);
    box.replaceChildren(el("h3", "", t("https.ports")), el("p", "muted", t("https.ports_hint")), row);
  },

  cert(s) {
    const box = this.root.querySelector(".https-cert");
    box.replaceChildren(el("h3", "", t("https.cert")));
    const c = s.mode === "files" ? s.certificate : s.ca;
    if (s.error) box.append(el("p", "error", s.error));
    if (!c) { box.append(el("p", "muted", t("https.ca_none"))); return; }
    const warn = c.days_left < 20;
    box.append(el("p", "", s.mode === "files" ? t("https.own_in_use", { issuer: c.issuer }) : t("https.caddy_in_use")),
      el("p", warn ? "error" : "muted", t("https.until", { d: c.not_after.slice(0, 10), n: c.days_left })),
      el("p", "muted", `${t("https.covers")}: ${c.names.join(", ")}`));
    if (s.mode === "internal" && c.urls && c.urls.length) {
      const steps = el("ol");
      steps.append(el("li", "", t("https.phone_1", { u: c.urls[0] })), el("li", "", t("https.phone_2")),
        el("li", "", t("https.phone_3")));
      box.append(el("h3", "", t("https.phone")), steps, qrSvg(c.urls[0], 160));
    }
    if (s.mode === "files") {
      const back = el("button", "danger", t("https.back"));
      back.addEventListener("click", async () => {
        if (!confirm(t("https.back_q"))) return;
        await this.change(() => call("/v1/aurora/https/cert", { method: "DELETE" }));
      });
      box.append(back);
    }
  },

  own(s) {
    const box = this.root.querySelector(".https-own");
    const cert = el("input"), key = el("input");
    cert.type = key.type = "file";
    cert.id = "https-cert-file"; key.id = "https-key-file";
    cert.accept = key.accept = ".pem,.crt,.key,.cer";
    const lc = el("label", "", t("https.cert_file")), lk = el("label", "", t("https.key_file"));
    lc.htmlFor = cert.id; lk.htmlFor = key.id;
    const use = el("button", "approve", t("https.use_own"));
    use.addEventListener("click", async () => {
      const [c, k] = await Promise.all([readText(cert.files[0]), readText(key.files[0])]);
      if (!c || !k) { this.say(t("https.both")); return; }
      await this.change(() => call("/v1/aurora/https/cert", { method: "PUT", body: JSON.stringify({ cert: c, key: k }) }));
    });
    box.replaceChildren(el("h3", "", t("https.own")), el("p", "muted", t("https.own_hint", { d: s.names[0] })),
      lc, cert, lk, key, use);
  },

  async saveNames(text) {
    const aliases = text.split(",").map((x) => x.trim()).filter(Boolean);
    await this.change(() => call("/v1/aurora/https/names", { method: "PUT", body: JSON.stringify({ aliases }) }));
  },

  async change(doit) {
    this.say(t("https.applying"));
    try {
      const r = await doit();
      const missing = (r && r.not_covered) || [];
      this.say(missing.length ? t("https.done_partial", { n: missing.join(", ") }) : t("https.done"));
      await this.enter();
    } catch (e) {
      this.say(t("ev.error", { m: e.message }));
    }
  },
};
