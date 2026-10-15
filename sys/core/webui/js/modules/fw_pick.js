// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Which firewall a page reads (the audit, the network map), when more than one is connected (ROADMAP N8): a select
// with each one's name and kind; nothing with one alone.
import { el } from "../dom.js";

export function fwPick(list, current, onPick) {
  if (!list || list.length < 2) return null;
  const s = el("select", "fw-pick");
  for (const f of list) {
    const o = el("option", "", `${f.name} · ${f.kind}`);
    o.value = f.id;
    o.selected = f.id === current;
    s.append(o);
  }
  s.addEventListener("change", () => onPick(s.value));
  return s;
}
