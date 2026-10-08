// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📅 The calendar's alerts in the chat (cal_store, roadmap 68): one bubble each, told by the notification too —
// «fatto» closes it, «tra 10 minuti» / «tra un'ora» tells it again then. The words are the code's (cal_text).
import { call } from "./api.js";
import { el } from "./dom.js";
import { t } from "./i18n.js";

function answer(m, key, snooze, said) {
  const b = el("button", snooze ? "" : "primary", said);
  b.type = "button";
  b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      await call("/v1/aurora/calendar/answer", { method: "POST", body: JSON.stringify({ key, snooze }) });
      m.querySelector(".appr-actions").replaceChildren(el("span", "muted", snooze ? `⏰ ${t("cal.snoozed", { n: snooze })}` : `✅ ${t("cal.done")}`));
    } catch (e) { b.disabled = false; m.append(el("div", "warn", e.message)); }
  });
  return b;
}

export async function calendarBubbles(messages) {
  let pend;
  try { pend = await call("/v1/aurora/calendar/pending"); } catch { return; }
  for (const a of pend.alerts || []) {
    if ([...messages.querySelectorAll("[data-cal]")].some((x) => x.dataset.cal === a.key)) continue;
    const m = el("div", "msg aurora cal-bubble");
    m.dataset.cal = a.key;
    m.append(el("div", "dream-title", a.item.kind === "reminder" ? t("cal.bubble_reminder") : t("cal.bubble_event")), el("p", "", a.text));
    if (a.item.notes) m.append(el("p", "muted", a.item.notes));
    const bar = el("div", "appr-actions");
    bar.append(answer(m, a.key, 0, `✅ ${t("cal.done")}`), answer(m, a.key, 10, `⏰ ${t("cal.snooze", { n: 10 })}`),
      answer(m, a.key, 60, `⏰ ${t("cal.snooze_h")}`));
    m.append(bar);
    messages.append(m);
  }
}
