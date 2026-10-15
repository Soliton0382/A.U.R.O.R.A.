// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// What is hidden, shown the same way in ☁️ Cloud accounts (what leaves for the cloud) and in 📣 Social (what the check
// before a post looks for) — owner, 2026-10-16: «far vedere i mascheramenti di default e quelli impostati per utente…
// la stessa cosa anche per la parte social»: the rules always on, read only, each with an example; a person's words,
// added and removed as chips.
import { call } from "../api.js";
import { el } from "../dom.js";
import { lang, t } from "../i18n.js";

export function rulesList(rules, title) {
  const d = el("details", "mask-rules");
  d.append(el("summary", "", `🔒 ${title} (${rules.length})`));
  const list = el("ul", "mask-rule-list");
  for (const r of rules) {
    const li = el("li");
    li.append(el("strong", "", r[lang.startsWith("it") ? "it" : "en"] || r.it), ...(r.example ? [el("code", "muted", r.example)] : []));
    list.append(li);
  }
  d.append(list);
  return d;
}

// a setting of comma-separated words as chips: ✕ takes one away, the field adds (several at once, comma separated)
export function wordsEditor(key, words, { placeholder, empty, onSaved } = {}) {
  const box = el("div", "mask-edit");
  const chips = el("div", "mask-words");
  const save = async (next) => {
    await call("/v1/aurora/settings", { method: "PUT", body: JSON.stringify({ [key]: next.join(", ") }) });
    onSaved?.();
  };
  for (const w of words) {
    const chip = el("span", "mask-word", w);
    const x = el("button", "", "✕");
    x.type = "button";
    x.title = t("acc.mask_remove");
    x.addEventListener("click", () => save(words.filter((y) => y !== w)).catch((e) => alert(e.message)));
    chip.append(x);
    chips.append(chip);
  }
  if (!words.length) chips.append(el("span", "muted", empty || t("acc.mask_none")));
  const add = el("form", "appr-actions");
  const input = el("input");
  input.placeholder = placeholder || t("acc.mask_add_ph");
  const go = el("button", "approve", `➕ ${t("acc.mask_add")}`);
  add.append(input, go);
  add.addEventListener("submit", (e) => {
    e.preventDefault();
    const fresh = input.value.split(",").map((w) => w.trim()).filter((w) => w.length >= 2 && !words.includes(w));
    if (fresh.length) save([...words, ...fresh]).catch((err) => alert(err.message));
  });
  box.append(chips, add);
  return box;
}
