// 🗂️ Evidentia's case files as a Finder (this installation's own, never published; owner, 10 Nov: «la metterei come
// sezione dedicata nel menu evidentia… menù stile Finder così restano ordinate ed impilate»): the folders on the left,
// the case files of the chosen folder stacked newest first, the chosen case on the right — its leads and its evidence,
// each quote opening its page. New, rename, move to a folder, export, delete, open in 💬 Indagini. The picker inside
// the chat's box is the same Finder, small (finder() below).
import { bus } from "/static/js/bus.js";
import { call } from "/static/js/api.js";
import { el, useCss } from "/static/js/dom.js";
import { t } from "/static/js/i18n.js";
import { API, citeButton, translateButton } from "./evidentia_view.js";
import chat from "./evidentia.js";

const day = (s) => (s ? new Date(s * 1000).toLocaleDateString() : "—");
const NONE = "\u0000";                                  // the folder of the cases in no folder

// the folders and the cases in them: {folder: [case…]}, newest first
export async function folders() {
  const { cases } = await call(`${API}/cases`);
  const out = {};
  for (const c of cases) (out[c.grp || NONE] ||= []).push(c);
  return out;
}

export const folderName = (f) => (f === NONE ? t("evd.no_group") : f);

// the two-column picker (folders → cases): `pick(case)` when one is chosen
export function finder(groups, current, pick) {
  const left = el("div", "evd-col"), right = el("div", "evd-col");
  const names = Object.keys(groups).sort((a, b) => (a === NONE) - (b === NONE) || a.localeCompare(b));
  let on = names.find((f) => groups[f].some((c) => c.id === current)) || names[0];
  const showCases = () => {
    right.replaceChildren(...(groups[on] || []).map((c) => {
      const b = el("button", `evd-item${c.id === current ? " on" : ""}`);
      b.type = "button";
      b.append(el("span", "", `🗂️ ${c.title}`), el("small", "", `${c.steps} · ${day(c.updated)}`));
      b.addEventListener("click", () => pick(c));
      return b;
    }));
    if (!names.length) right.replaceChildren(el("p", "muted", t("evd.empty")));
  };
  const showFolders = () => {
    left.replaceChildren(...names.map((f) => {
      const b = el("button", `evd-item${f === on ? " on" : ""}`);
      b.type = "button";
      b.append(el("span", "", `📁 ${folderName(f)}`), el("small", "", String(groups[f].length)));
      b.addEventListener("click", () => { on = f; showFolders(); showCases(); });
      return b;
    }));
  };
  showFolders();
  showCases();
  return [left, right];
}

export default {
  id: "evd_cases",
  adminOnly: true,
  icon: "🗂️",
  title: "nav.evd_cases",

  mount(root) {
    root.classList.add("page");
    useCss("/static/addons/evidentia/evidentia.css");
    this.bar = el("div", "evd-bar");
    this.box = el("div", "evd-finder");
    root.append(el("h2", "", `🗂️ ${t("nav.evd_cases")}`), el("p", "muted", t("evd.cases_hint")), this.bar, this.box);
  },

  async enter() {
    let groups;
    try { groups = await folders(); } catch (e) { this.box.replaceChildren(el("p", "muted", t("evd.off", { m: e.message }))); return; }
    const add = el("button", "approve", `➕ ${t("evd.new")}`);
    add.addEventListener("click", async () => {
      const title = prompt(t("evd.new_title"));
      if (!title) return;
      const c = await call(`${API}/cases`, { method: "POST", body: JSON.stringify({ title }) });
      this.current = c.id;
      this.enter();
    });
    this.bar.replaceChildren(add);
    const detail = el("div", "evd-col");
    const [left, right] = finder(groups, this.current, (c) => { this.current = c.id; this.enter(); });
    this.box.replaceChildren(left, right, detail);
    if (this.current) await this.drawCase(detail, this.current);
    else detail.append(el("p", "muted", t("evd.pick_case")));
  },

  async drawCase(box, cid) {
    let c, leads = [];
    try {
      c = await call(`${API}/cases/${cid}`);
      ({ leads } = await call(`${API}/leads?case=${cid}`));
    } catch { this.current = null; box.append(el("p", "muted", t("evd.pick_case"))); return; }
    const acts = el("div", "evd-bar");
    const act = (label, fn) => { const b = el("button", "", label); b.addEventListener("click", fn); acts.append(b); };
    act(`💬 ${t("evd.open_chat")}`, () => { chat.open = cid; bus.emit("show", { id: "evidentia" }); });
    // 👥 shared between users (owner, 27 Nov): the maker names its members; a member works in it, nothing more
    let members = null;
    try { members = (await call(`${API}/cases/${cid}/members`)).members; } catch { /* shared with me: not mine to change */ }
    if (members === null) {
      box.append(el("h3", "", `🗂️ ${c.title}`), el("p", "muted", t("evd.shared_with_me")), acts);
      return this.drawLeads(box, leads);
    }
    act(`👥 ${t("evd.share")}${members.length ? ` · ${members.length}` : ""}`, async () => {
      const { people } = await call("/v1/aurora/evidentia-people").catch(() => ({ people: [] }));
      const pick = el("div", "prj-tabs");
      for (const n of people) {
        const b = el("button", `cat-chip${members.includes(n) ? " on" : ""}`, `👤 ${n}`);
        b.type = "button"; b.dataset.value = n;
        b.addEventListener("click", () => b.classList.toggle("on"));
        pick.append(b);
      }
      const save = el("button", "approve", t("evd.share_save"));
      save.addEventListener("click", async () => {
        const chosen = [...pick.querySelectorAll(".cat-chip.on")].map((b) => b.dataset.value);
        await call(`${API}/cases/${cid}/members`, { method: "PUT", body: JSON.stringify({ members: chosen }) });
        this.enter();
      });
      const panel = el("div", "evd-share");
      panel.append(el("p", "muted", people.length ? t("evd.share_hint") : t("evd.share_none")), pick, save);
      acts.after(panel);
    });
    act(`✏️ ${t("evd.rename")}`, async () => {
      const title = prompt(t("evd.new_title"), c.title);
      if (title) { await call(`${API}/cases/${cid}`, { method: "PATCH", body: JSON.stringify({ title }) }); this.enter(); }
    });
    act(`📁 ${t("evd.move")}`, async () => {
      const group = prompt(t("evd.move_q"), c.grp || "");
      if (group !== null) { await call(`${API}/cases/${cid}`, { method: "PATCH", body: JSON.stringify({ group }) }); this.enter(); }
    });
    act(`📄 ${t("evd.export")}`, () => chat.export(c));
    act(`🗑️ ${t("evd.delete")}`, async () => {
      if (!confirm(t("evd.delete_confirm", { title: c.title }))) return;
      await call(`${API}/cases/${cid}`, { method: "DELETE" });
      this.current = null;
      this.enter();
    });
    box.append(el("h3", "", `🗂️ ${c.title}`),
      el("p", "muted", t("evd.case_line", { s: c.steps, l: leads.length, d: day(c.updated) })), acts);
    this.drawLeads(box, leads);
  },

  drawLeads(box, leads) {
    if (!leads.length) box.append(el("p", "muted", t("evd.no_leads")));
    for (const l of leads) {
      const row = el("div", "evd-lead");
      row.append(el("strong", "", `🧭 #${l.id} · ${t(`evd.st_${l.status}`)} · ${l.agent}`), el("div", "", l.what));
      if (l.summary) row.append(el("p", "", l.summary), translateButton(l.summary, row));
      for (const e of l.evidence || []) {
        const q = el("div", "evd-quote");
        q.append(el("span", "", `«${e.quote}» `), citeButton(e, e.quote));
        if (e.note) q.append(el("div", "muted", e.note));
        row.append(q);
      }
      box.append(row);
    }
  },
};
