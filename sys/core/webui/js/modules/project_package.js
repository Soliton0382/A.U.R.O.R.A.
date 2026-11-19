// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📦 The package to publish (N148; owner, 20 Nov: «un pulsante che esegue tutto fino al bundle in automatico… e una
// volta preparato il pacchetto… il pulsante di download»): the user's message → commit + aurora.bundle in the project's
// cage (prj_package: no network) → a download button. The push is the user's, from their own computer, after review.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const kb = (n) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`);

export function packageView(name) {
  const box = el("div", "prj-package");
  const info = el("p", "muted", t("prj.pkg_note"));
  const state = el("p", "muted");
  const form = el("form", "prj-term-line");
  const msg = el("input");
  msg.placeholder = t("prj.pkg_msg_ph");
  msg.maxLength = 500;
  const author = el("input");
  author.placeholder = t("prj.pkg_author_ph");
  const email = el("input");
  email.placeholder = t("prj.pkg_email_ph");
  email.type = "email";
  const go = el("button", "", t("prj.pkg_prepare"));
  go.type = "submit";
  form.append(msg, author, email, go);
  const ready = el("div", "prj-package-ready");
  const commits = el("ul", "prj-package-log");
  const steps = el("details", "prj-package-steps");
  steps.append(el("summary", "", t("prj.pkg_steps_title")), el("pre", "", t("prj.pkg_steps", { name })));
  box.append(info, state, form, ready, commits, steps);

  const show = (s) => {
    state.textContent = !s.repo ? t("prj.pkg_norepo")
      : t("prj.pkg_state", { dirty: s.dirty, who: s.name ? `${s.name} <${s.email}>` : t("prj.pkg_noauthor") });
    if (s.name && !author.value) author.value = s.name;
    if (s.email && !email.value) email.value = s.email;
    commits.replaceChildren(...s.commits.map((c) => el("li", "", c)));
    ready.replaceChildren();
    if (s.bundle) {
      const a = el("a", "btn", t("prj.pkg_download", { size: kb(s.bundle.size) }));
      a.href = `/v1/aurora/projects/${encodeURIComponent(name)}/package/download`;
      a.setAttribute("download", `${name}.bundle`);
      ready.append(a, el("span", "muted", " " + t("prj.pkg_made", { when: new Date(s.bundle.mtime * 1000).toLocaleString() })));
    }
  };
  const load = () => call(`/v1/aurora/projects/${encodeURIComponent(name)}/package`).then(show)
    .catch((e) => { state.textContent = e.message; });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!msg.value.trim()) { msg.focus(); return; }
    go.disabled = true;
    state.textContent = t("prj.pkg_working");
    try {
      const s = await call(`/v1/aurora/projects/${encodeURIComponent(name)}/package`, { method: "POST",
        body: JSON.stringify({ message: msg.value, author: author.value, email: email.value }) });
      show(s);
      state.textContent = (s.committed ? t("prj.pkg_done") : t("prj.pkg_nochange")) + " " + state.textContent;
      msg.value = "";
    } catch (err) {
      state.textContent = err.message;
    } finally {
      go.disabled = false;
    }
  });
  load();
  return box;
}
