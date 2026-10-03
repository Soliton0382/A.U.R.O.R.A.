// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// An artifact (an interactive page Aurora made) live inside the answer: a sandboxed frame on /v1/preview/ (opaque
// origin, no network: doc_artifact), opened with a short-lived token; full screen and download on demand.
import { call } from "./api.js";
import { el } from "./dom.js";
import { t } from "./i18n.js";

async function frame(url) {
  const { url: page } = await call("/v1/aurora/artifacts/open", { method: "POST", body: JSON.stringify({ url }) });
  const f = el("iframe", "artifact-frame");
  f.setAttribute("sandbox", "allow-scripts");
  f.setAttribute("referrerpolicy", "no-referrer");
  f.loading = "lazy";
  f.src = page;
  return f;
}

export function artifactCard(file) {
  const card = el("div", "artifact");
  const bar = el("div", "artifact-bar");
  const full = el("button", "", `⛶ ${t("artifact.full")}`);
  const reload = el("button", "", "↻");
  const save = el("a", "chip", `⬇ ${file.name}`);
  save.href = file.url;
  save.setAttribute("download", file.name);
  full.type = reload.type = "button";
  reload.title = t("artifact.reload");
  bar.append(el("span", "artifact-title", `🧩 ${file.name.replace(/-\d{8}-\d{6}\.html$/, "")}`), full, reload, save);
  const body = el("div", "artifact-body", t("viewer.loading"));
  const load = () => frame(file.url).then((f) => body.replaceChildren(f))
    .catch((e) => body.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))));
  reload.addEventListener("click", load);
  full.addEventListener("click", () => card.classList.toggle("full"));
  card.append(bar, body);
  load();
  return card;
}
