// 🔑 Keys and recovery, under ⚙️ System (sys_key_recovery, N64): where Aurora's key is and whether the TPM holds it,
// the escrow, and the recovery code — made and shown once, checked without showing it.
import { call } from "../api.js";
import { el, useCss } from "../dom.js";
import { t } from "../i18n.js";

export default {
  id: "keys",
  adminOnly: true,                                   // her key opens every user's data: the admin's page alone
  icon: "🔑",
  title: "nav.keys",

  mount(root) {
    root.classList.add("page");
    useCss("/static/css/keys.css");
    this.root = root;
  },

  async enter() {
    let k;
    try { k = await call("/v1/aurora/keys"); } catch (e) { this.root.replaceChildren(el("p", "muted", t("ev.error", { m: e.message }))); return; }
    this.root.replaceChildren(el("h2", "", t("keys.title")), el("p", "muted", t("keys.hint")), this.state(k), this.recovery(k));
  },

  row(label, ok, text) {
    const r = el("div", "keys-row");
    const info = el("div", "keys-info");
    info.append(el("span", "keys-name", label), el("span", "keys-state", `${ok ? "✅" : "⚠️"} ${text}`));
    r.append(info);
    return r;
  },

  state(k) {
    const box = el("div", "keys-card");
    const tpm = k.bound === "host+tpm2";
    box.append(el("h4", "", t("keys.state")),
      this.row(t("keys.where"), k.where === "credential" || k.where === "sealed", t(`keys.where.${k.where}`)),
      this.row(t("keys.tpm"), tpm, tpm ? t("keys.tpm.bound") : (k.tpm ? t("keys.tpm.ready") : t("keys.tpm.none"))),
      this.row(t("keys.escrow"), k.escrow, k.escrow ? t("keys.escrow.yes") : t("keys.escrow.no")));
    return box;
  },

  recovery(k) {
    const box = el("div", "keys-card");
    const when = k.recovery.created ? new Date(k.recovery.created * 1000).toLocaleDateString() : "";
    box.append(el("h4", "", t("keys.rec")), el("p", "muted", t("keys.rec.hint")),
      this.row(t("keys.rec.state"), k.recovery.exists, k.recovery.exists ? t("keys.rec.yes", { d: when }) : t("keys.rec.no")));
    const shown = el("div", "keys-code");
    const make = el("button", "approve", t(k.recovery.exists ? "keys.rec.again" : "keys.rec.make"));
    const msg = el("span", "muted");
    make.addEventListener("click", async () => {
      if (k.recovery.exists && !confirm(t("keys.rec.again_q"))) return;
      make.disabled = true;
      msg.textContent = t("keys.rec.making");
      try {
        const r = await call("/v1/aurora/keys/recovery", { method: "POST", body: "{}" });
        const code = el("code", "", r.code);
        code.style.cssText = "font-size:1.4em;letter-spacing:.08em;user-select:all;word-break:break-all";
        shown.replaceChildren(el("p", "", t("keys.rec.write")), code, el("p", "keys-warn", t("keys.rec.once")));
        msg.textContent = "";
        k.recovery = r.recovery;
      } catch (e) { msg.textContent = t("ev.error", { m: e.message }); }
      make.disabled = false;
    });
    const input = el("input");
    input.placeholder = "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX";
    input.autocomplete = "off";
    const check = el("button", "", t("keys.rec.check"));
    const verdict = el("span", "muted");
    check.addEventListener("click", async () => {
      check.disabled = true;
      verdict.textContent = "…";
      try {
        const r = await call("/v1/aurora/keys/recovery/check", { method: "POST", body: JSON.stringify({ code: input.value }) });
        verdict.textContent = r.opens ? t("keys.rec.opens") : t("keys.rec.wrong");
      } catch (e) { verdict.textContent = t("ev.error", { m: e.message }); }
      input.value = "";                              // never left on the page
      check.disabled = false;
    });
    const btns = el("div", "keys-btns");
    btns.append(make, msg);
    const test = el("div", "keys-btns");
    test.append(input, check, verdict);
    box.append(btns, shown, el("h4", "", t("keys.rec.test")), test, el("p", "muted", t("keys.rec.restore")));
    return box;
  },
};
