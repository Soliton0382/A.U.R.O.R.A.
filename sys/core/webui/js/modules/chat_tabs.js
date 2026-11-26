// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 💬 The chat's tabs (owner, 27 Nov, N165 F3: «chat, chat anonima e interprete sotto una sola voce, come schede»): one
// entry in the menu, the three pages a tab each; their ids stay (links, pins, the search open them as before). A tab
// of a feature the admin keeps from this person is not drawn.
import { bus } from "../bus.js";
import { isHidden } from "../access.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const TABS = [["chat", "💬", "nav.chat"], ["anonchat", "🕶️", "nav.anonchat"], ["interpret", "🌍", "nav.interpret"]];

export function chatTabs(current) {
  const box = el("div", "prj-tabs chat-tabs");
  const draw = () => {
    box.replaceChildren(...TABS.filter(([id]) => id === current || !isHidden(id)).map(([id, icon, title]) => {
      const b = el("button", `cat-chip${id === current ? " on" : ""}`, `${icon} ${t(title)}`);
      b.type = "button";
      b.addEventListener("click", () => { if (id !== current) bus.emit("show", { id }); });
      return b;
    }));
    box.hidden = box.children.length < 2;             // alone: no tabs at all
  };
  draw();
  bus.on("access", draw);
  return box;
}
