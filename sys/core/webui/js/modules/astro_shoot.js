// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 📸 Astro → 📈 the shooting and the night's progress (owner, 2026-10-20: «nella parte guida dal vivo metterei una
// sezione dedicata allo scatto e al progresso totale così almeno si ha tutto sotto controllo in una unica videata»):
// the exposure going on with its countdown, the sequence's hours done of planned, each series, the camera's cooling and
// the last picture's HFR and stars. N.I.N.A.'s state as the mount's box already reads it (ast_nina): no call of its own.
import { el } from "../dom.js";
import { t } from "../i18n.js";

const f = (x, d = 1) => (x == null ? "—" : Number(x).toFixed(d));

// seconds as hours and minutes: «2 h 30 min», «45 min», «3 min 20 s»
export function hours(s) {
  if (s == null) return "—";
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  if (h) return `${h} h${m ? ` ${m} min` : ""}`;
  if (m) return `${m} min${s % 60 && m < 10 ? ` ${s % 60} s` : ""}`;
  return `${s} s`;
}

function bar(done, total, live = false) {
  const b = el("div", `sh-bar${live ? " live" : ""}`);
  const p = total > 0 ? Math.min(100, (100 * done) / total) : 0;
  const fill = el("span");
  fill.style.width = `${p.toFixed(1)}%`;
  b.append(fill);
  return b;
}

export function shootBox(box) {
  box.innerHTML = "";
  const now = el("div", "sh-now"), total = el("div", "sh-total"), list = el("div", "sh-series"), lines = el("ul", "am-lines");
  box.append(now, total, list, lines);
  let last = null, timer = 0;

  // the exposure's own clock, between two reads (every 4 s): the countdown goes on by itself
  const clock = () => {
    if (!last) return;
    const c = last.camera || {}, run = (last.sequence?.series || []).find((x) => x.running);
    const exp = run?.exposure_s;
    if (c.exposing && last.ends != null) {
      const left = Math.max(0, last.ends - (Date.now() - last.at) / 1000);
      const head = el("div", "sh-line", `📸 ${t("sh.exposing", { left: hours(left), exp: exp ? hours(exp) : "?" })}`);
      now.replaceChildren(head, bar(exp ? exp - left : 0, exp || 1, true));
    } else {
      now.replaceChildren(el("div", "sh-line muted", `📷 ${t(c.connected === false ? "sh.no_camera" : "sh.idle", { s: c.state || "—" })}`));
    }
  };

  function update(d) {
    clearInterval(timer);
    if (!d || !d.reachable) {
      last = null;
      now.replaceChildren(el("div", "sh-line muted", t("sh.off")));
      total.replaceChildren();
      list.replaceChildren();
      lines.replaceChildren();
      return;
    }
    last = { ...d, ends: d.camera?.ends_in_s, at: Date.now() };
    const sq = d.sequence || {}, series = sq.series || [];
    if (series.length) {
      const pct = sq.planned_s ? Math.round((100 * sq.done_s) / sq.planned_s) : 0;
      total.replaceChildren(el("div", "sh-line", `🗂️ ${t("sh.total", { done: hours(sq.done_s), all: hours(sq.planned_s), p: pct, left: hours(sq.left_s) })}`),
        bar(sq.done_s, sq.planned_s));
      list.replaceChildren(...series.map((x) => {
        const row = el("div", `sh-row${x.running ? " on" : ""}`);
        row.append(el("span", "", `${x.running ? "▶️" : x.done >= x.total && x.total ? "✅" : "⏸️"} ${x.target ? `${x.target} · ` : ""}${x.name}`),
          el("span", "muted", `${x.done}/${x.total} × ${hours(x.exposure_s)} · gain ${x.gain ?? "—"} / offset ${x.offset ?? "—"}`),
          el("strong", "", `${hours(x.done * x.exposure_s)} / ${hours(x.total * x.exposure_s)}`), bar(x.done, x.total));
        return row;
      }));
    } else {
      total.replaceChildren(el("div", "sh-line muted", t("sh.no_sequence")));
      list.replaceChildren();
    }
    const c = d.camera || {}, im = d.image;
    lines.replaceChildren(
      el("li", "", `❄️ ${f(c.temp_c)} °C → ${f(c.target_c)} °C${c.cooler ? ` · ${t("sh.cooler", { p: f(c.power, 0) })}` : ` · ${t("am.cooler_off")}`} · gain ${c.gain ?? "—"} / offset ${c.offset ?? "—"}`),
      el("li", im ? "" : "muted", im ? `🖼️ ${t("sh.image", { n: im.n, type: im.type || "—", exp: hours(im.exposure_s), filter: im.filter || "—", hfr: f(im.hfr, 2), stars: im.stars ?? "—" })}`
        : `🖼️ ${t("sh.no_image")}`));
    clock();
    if (c.exposing) timer = setInterval(() => { if (box.isConnected) clock(); else clearInterval(timer); }, 1000);
  }
  update(null);
  return { update };
}
