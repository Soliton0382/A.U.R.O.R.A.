// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📅 An appointment or a reminder, new or changed (calendar.js): what, when, how long, where, when to tell, how often.
// The times are wall-clock times of Aurora's zone (cal_store): what is typed here is what is kept.
import { call } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const ALERTS = [-1, 0, 5, 10, 15, 30, 60, 120, 1440, 2880];
const REPEATS = ["", "daily", "weekly", "monthly", "yearly"];

const pad = (n) => String(n).padStart(2, "0");
export const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function alertLabel(m) {
  if (m < 0) return t("cal.alert.none");
  if (m === 0) return t("cal.alert.now");
  if (m % 1440 === 0) return t("cal.alert.days", { n: m / 1440 });
  if (m % 60 === 0) return t("cal.alert.hours", { n: m / 60 });
  return t("cal.alert.min", { n: m });
}

function select(name, values, label, current) {
  const s = el("select");
  s.name = name;
  for (const v of values) {
    const o = el("option", "", label(v));
    o.value = String(v);
    s.append(o);
  }
  s.value = String(current);
  return s;
}

function field(label, input) {
  const l = el("label", "cal-field");
  l.append(el("span", "", label), input);
  return l;
}

function input(name, type, value = "") {
  const i = el("input");
  i.name = name;
  i.type = type;
  i.value = value;
  return i;
}

// item: a stored item to change (with `at`: the occurrence opened), or null for a new one on `day` (YYYY-MM-DD)
export function itemForm(item, day, done) {
  const f = el("form", "cal-form");
  const kind = select("kind", ["event", "reminder"], (k) => t(`cal.kind.${k}`), item?.kind || "event");
  const title = input("title", "text", item?.title || "");
  title.required = true;
  title.maxLength = 200;
  title.placeholder = t("cal.title_ph");
  const [d0, h0] = (item?.start || `${day}T09:00`).split("T");
  const [d1, h1] = (item?.end || `${day}T10:00`).split("T");
  const date = input("date", "date", d0);
  date.required = true;
  const start = input("start", "time", h0);
  const end = input("end", "time", h1);
  const allDay = input("all_day", "checkbox");
  allDay.checked = !!item?.all_day;
  const where = input("location", "text", item?.location || "");
  where.placeholder = t("cal.where_ph");
  const notes = el("textarea");
  notes.name = "notes";
  notes.rows = 2;
  notes.value = item?.notes || "";
  const a = item?.alerts || [];
  const alert1 = select("alert1", ALERTS, alertLabel, a.length ? a[0] : (item ? -1 : 30));
  const alert2 = select("alert2", ALERTS, alertLabel, a.length > 1 ? a[1] : -1);
  const repeat = select("repeat", REPEATS, (r) => t(`cal.repeat.${r || "none"}`), item?.repeat?.freq || "");
  const until = input("until", "date", item?.repeat?.until || "");
  const out = el("div", "warn");

  const rowEnd = field(t("cal.end"), end);
  const rowAll = el("label", "cal-check");
  rowAll.append(allDay, el("span", "", t("cal.all_day")));
  const rowUntil = field(t("cal.until"), until);
  const sync = () => {
    const reminder = kind.value === "reminder";
    rowEnd.hidden = reminder || allDay.checked;
    rowAll.hidden = reminder;
    start.disabled = allDay.checked && !reminder;
    rowUntil.hidden = !repeat.value;
  };
  [kind, allDay, repeat].forEach((x) => x.addEventListener("change", sync));

  const when = el("div", "cal-row");
  when.append(field(t("cal.day"), date), field(t("cal.start"), start), rowEnd, rowAll);
  const tell = el("div", "cal-row");
  tell.append(field(t("cal.alert"), alert1), field(t("cal.alert2"), alert2));
  const again = el("div", "cal-row");
  again.append(field(t("cal.repeat"), repeat), rowUntil);
  if (item?.repeat) f.append(el("p", "muted", t("cal.series_hint")));
  f.append(field(t("cal.kind"), kind), field(t("cal.what"), title), when, field(t("cal.where"), where),
    field(t("cal.notes"), notes), tell, again, out);

  const bar = el("div", "appr-actions");
  const save = el("button", "primary", `💾 ${t("cal.save")}`);
  save.type = "submit";
  const cancel = el("button", "", t("cal.cancel"));
  cancel.type = "button";
  cancel.addEventListener("click", () => done(false));
  bar.append(save, cancel);
  if (item) {
    const del = el("button", "danger", `🗑️ ${item.repeat ? t("cal.delete_all") : t("cal.delete")}`);
    del.type = "button";
    del.addEventListener("click", async () => {
      if (!confirm(t("cal.delete_ask", { title: item.title }))) return;
      try { await call(`/v1/aurora/calendar/items/${item.id}`, { method: "DELETE" }); done(true); } catch (e) { out.textContent = e.message; }
    });
    bar.append(del);
    if (item.repeat && item.at) {
      const one = el("button", "", `✂️ ${t("cal.delete_one")}`);
      one.type = "button";
      one.addEventListener("click", async () => {
        try { await call(`/v1/aurora/calendar/items/${item.id}?occurrence=${encodeURIComponent(item.at)}`, { method: "DELETE" }); done(true); }
        catch (e) { out.textContent = e.message; }
      });
      bar.append(one);
    }
  }
  f.append(bar);

  f.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const reminder = kind.value === "reminder";
    const whole = allDay.checked && !reminder;
    const alerts = [alert1.value, alert2.value].map(Number).filter((m) => m >= 0);
    let endAt = whole ? null : `${date.value}T${end.value || start.value}`;
    // an end before the start on the same day: it ends the day after (a night shift, a party)
    if (endAt && !reminder && end.value && end.value <= start.value) {
      const next = new Date(`${date.value}T00:00`);
      next.setDate(next.getDate() + 1);
      endAt = `${ymd(next)}T${end.value}`;
    }
    const body = {
      kind: kind.value, title: title.value, start: `${date.value}T${whole ? "00:00" : start.value || "09:00"}`,
      all_day: whole, location: where.value, notes: notes.value, alerts,
      repeat: repeat.value ? { freq: repeat.value, ...(until.value ? { until: until.value } : {}) } : null,
      ...(reminder || whole ? {} : { end: endAt }),
    };
    save.disabled = true;
    try {
      await call(item ? `/v1/aurora/calendar/items/${item.id}` : "/v1/aurora/calendar/items",
        { method: item ? "PUT" : "POST", body: JSON.stringify(body) });
      done(true);
    } catch (e) { out.textContent = e.message; save.disabled = false; }
  });
  sync();
  setTimeout(() => title.focus(), 0);
  return f;
}
