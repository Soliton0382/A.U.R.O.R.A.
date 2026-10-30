// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📅 An appointment or a reminder, new or changed (calendar.js): what, when, how long, where, when to tell, how often.
// The times are wall-clock times of Aurora's zone (cal_store): what is typed here is what is kept. 👥 Who else takes
// part (cal_share): users of this installation (in their calendar at once) and addresses (an invitation, sent on
// the person's word: a notice before it goes); another's appointment shows who made it, only its alerts change.
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
export function itemForm(item, day, done, hour = 9) {        // hour: where the day or week grid was tapped
  const f = el("form", "cal-form");
  const kind = select("kind", ["event", "reminder"], (k) => t(`cal.kind.${k}`), item?.kind || "event");
  const title = input("title", "text", item?.title || "");
  title.required = true;
  title.maxLength = 200;
  title.placeholder = t("cal.title_ph");
  const [d0, h0] = (item?.start || `${day}T${pad(hour)}:00`).split("T");
  const [d1, h1] = (item?.end || `${day}T${pad(Math.min(hour + 1, 23))}:${hour >= 23 ? "59" : "00"}`).split("T");
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
  // 👥 the people: a chip per user of this installation, and addresses
  const shared = item?.shared_from || null;
  const had = item?.people || [];
  const picked = new Set(had.filter((x) => x.user).map((x) => x.user));
  const users = el("div", "chips cal-people");
  const emails = input("emails", "text", had.filter((x) => x.email).map((x) => x.email).join(", "));
  emails.placeholder = t("cal.emails_ph");
  emails.autocomplete = "off";
  call("/v1/aurora/calendar/people").then((r) => {
    const said = Object.fromEntries(had.filter((x) => x.user).map((x) => [x.user, x.rsvp || "pending"]));
    const mark = { pending: "⏳", yes: "✔", no: "✘" };
    for (const name of new Set([...r.users, ...picked])) {
      const b = el("button", `chip ${picked.has(name) ? "on" : ""}`, `👤 ${name}${said[name] ? ` ${mark[said[name]]}` : ""}`);
      if (said[name]) b.title = t(`cal.rsvp.${said[name]}`);
      b.type = "button";
      b.disabled = !!shared;
      b.addEventListener("click", () => { picked.has(name) ? picked.delete(name) : picked.add(name); b.classList.toggle("on", picked.has(name)); });
      users.append(b);
    }
    if (!users.children.length) users.append(el("span", "muted", t("cal.people_none")));
    if (!r.mail) mailHint.hidden = false;           // the invitations need the ✉️ plugin: where to set it up
  }).catch(() => users.append(el("span", "muted", t("cal.people_none"))));
  const mailHint = el("small", "muted cal-mail-hint", t("cal.mail_setup"));
  mailHint.hidden = true;
  const addresses = () => emails.value.split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean);
  // the notice before an invitation leaves Aurora (owner, 30 Oct: «basta un disclaimer… procedere ugualmente?»)
  const okToMail = (list) => !list.length || confirm(t("cal.email_ask", { list: list.join(", ") }));
  const told = (r) => {
    const bad = r?.mail?.failed || [];
    if (bad.length) alert(t("cal.mail_failed", { list: bad.map((x) => `${x.to} (${x.why})`).join("; ") }));
  };

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
  if (shared) {
    f.append(el("p", "muted", t("cal.shared_by", { n: shared.user })));
    // my answer to whoever added me (owner, 30 Oct): accept or decline, they are told
    const mine = item.mine;                          // the server's: my own answer (api calendar)
    const ask = el("div", "appr-actions cal-rsvp");
    for (const yes of [true, false]) {
      const b = el("button", yes ? "primary" : "", yes ? `✔ ${t("cal.accept")}` : `✘ ${t("cal.decline")}`);
      b.type = "button";
      b.addEventListener("click", async () => {
        try { await call(`/v1/aurora/calendar/items/${item.id}/rsvp`, { method: "POST", body: JSON.stringify({ yes }) }); done(true); }
        catch (e) { out.textContent = e.message; }
      });
      ask.append(b);
    }
    if (mine) ask.append(el("span", "muted", t(`cal.rsvp.${mine}`)));
    f.append(ask);
  }
  const people = el("div", "cal-row");
  const mailField = field(t("cal.emails"), emails);
  mailField.append(mailHint);
  people.append(field(t("cal.people"), users), mailField);
  f.append(field(t("cal.kind"), kind), field(t("cal.what"), title), when, field(t("cal.where"), where),
    field(t("cal.notes"), notes), people, tell, again, out);
  if (shared) for (const x of [kind, title, date, start, end, allDay, where, notes, emails, repeat, until]) x.disabled = true;

  const bar = el("div", "appr-actions");
  const save = el("button", "primary", `💾 ${t("cal.save")}`);
  save.type = "submit";
  const cancel = el("button", "", t("cal.cancel"));
  cancel.type = "button";
  cancel.addEventListener("click", () => done(false));
  bar.append(save, cancel);
  if (item) {
    const del = el("button", "danger", `🗑️ ${shared ? t("cal.leave") : item.repeat ? t("cal.delete_all") : t("cal.delete")}`);
    del.type = "button";
    del.addEventListener("click", async () => {
      if (!confirm(t(shared ? "cal.leave_ask" : "cal.delete_ask", { title: item.title }))) return;
      const mails = shared ? [] : had.filter((x) => x.email).map((x) => x.email);
      if (!okToMail(mails)) return;
      try { told(await call(`/v1/aurora/calendar/items/${item.id}${mails.length ? "?confirm_email=true" : ""}`, { method: "DELETE" })); done(true); }
      catch (e) { out.textContent = e.message; }
    });
    bar.append(del);
    if (item.repeat && item.at && !shared) {
      const one = el("button", "", `✂️ ${t("cal.delete_one")}`);
      one.type = "button";
      one.addEventListener("click", async () => {
        const mails = had.filter((x) => x.email).map((x) => x.email);
        if (!okToMail(mails)) return;
        try { told(await call(`/v1/aurora/calendar/items/${item.id}?occurrence=${encodeURIComponent(item.at)}${mails.length ? "&confirm_email=true" : ""}`, { method: "DELETE" })); done(true); }
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
      people: [...[...picked].map((user) => ({ user })), ...addresses().map((email) => ({ email }))],
    };
    // the addresses told: the ones there now, and the ones taken off (their cancellation)
    const mails = [...new Set([...addresses(), ...had.filter((x) => x.email).map((x) => x.email)])];
    if (!shared && !okToMail(mails)) return;
    if (mails.length) body.confirm_email = true;
    save.disabled = true;
    try {
      told(await call(item ? `/v1/aurora/calendar/items/${item.id}` : "/v1/aurora/calendar/items",
        { method: item ? "PUT" : "POST", body: JSON.stringify(shared ? { alerts } : body) }));
      done(true);
    } catch (e) { out.textContent = e.message; save.disabled = false; }
  });
  sync();
  setTimeout(() => title.focus(), 0);
  return f;
}
