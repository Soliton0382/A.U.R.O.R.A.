// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// "Share" on Aurora's dreams and thoughts: the Social page opens with drafts (and the dream's picture);
// the owner reads and clicks Publish. Session memories are never shared: they tell the owner's conversations.
import { bus } from "./bus.js";
import { el } from "./dom.js";
import { t } from "./i18n.js";

export function shareButton(text, imageUrl) {
  const b = el("button", "share", `↗ ${t("chat.share")}`);
  b.type = "button";
  const picture = imageUrl ? decodeURIComponent(imageUrl.split("/").pop().split("?")[0]) : null;
  b.addEventListener("click", (ev) => { ev.stopPropagation(); bus.emit("share", { text, picture }); });
  return b;
}
