// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Tables on a phone (owner, 2026-10-13: «le visualizzazioni in pwa che eccedono»): a data table with a header row
// becomes a pile of cards under 640 px — each row a card, each cell with its column's name before it (CSS in
// app.css, .stackable). Every page's tables, as they are drawn: no module has to do anything.
const DATA_TABLES = "table.table, table.appr-table, table.auto-table";

function label(table) {
  // the header: a <thead>, or a first row made only of <th> (most pages build it so)
  const first = table.querySelector("tr");
  const headRow = table.querySelector("thead tr") || (first && [...first.children].every((c) => c.tagName === "TH") ? first : null);
  if (!headRow) return;                                        // no header row: nothing to name the cells with
  const heads = [...headRow.children].map((th) => th.textContent.trim());
  headRow.classList.add("stack-head");
  table.classList.add("stackable");
  for (const row of table.querySelectorAll("tr")) {
    if (row === headRow) continue;
    [...row.children].forEach((cell, i) => {
      if (!cell.hasAttribute("data-label")) cell.setAttribute("data-label", heads[i] || "");
    });
  }
}

export function stackTables(root) {
  const scan = () => root.querySelectorAll(DATA_TABLES).forEach(label);
  let queued = false;
  new MutationObserver(() => {                                 // pages redraw: label again, once per frame
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; scan(); });
  }).observe(root, { childList: true, subtree: true });
  scan();
}
