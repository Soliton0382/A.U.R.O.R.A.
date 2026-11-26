// 🕵️ Evidentia (this installation's own, never published): a chat whose every conversation is a case file
// (owner, 9 Nov: «lo gestirei proprio come una chat con la selezione dei fascicoli… cliccando sul tasto dentro al box
// della chat»). The 🗂️ button inside the box opens a Finder of the case files (folders → cases, 10 Nov);
// the bar above has export, summary and the investigative document. The cases live in the archive of Evidentia
// (the add-on's own service), never in Aurora's memory; Aurora's route only carries the requests
// (local/api_evidentia). Until the agents come (F8) a question is a search: its answer, with its sources, is the
// message of Evidentia, and the step lands in the case's diary.
import { bus } from "/static/js/bus.js";
import { call } from "/static/js/api.js";
import { el, useCss } from "/static/js/dom.js";
import { lang, t } from "/static/js/i18n.js";
import { renderMarkdown } from "/static/js/md.js";
import { composer } from "/static/js/modules/composer.js";
import { auroraBubble, follow } from "/static/js/modules/trace.js";
import { finder, folders } from "./evidentia_cases.js";
import net from "./evidentia_net.js";
import { API, citeButton, translateButton } from "./evidentia_view.js";
const day = (s) => (s ? new Date(s * 1000).toLocaleDateString() : "—");

export default {
  id: "evidentia",
  adminOnly: true,
  icon: "💬",
  title: "nav.evd_chat",                              // 💬 Indagini, the third page of 🕵️ Evidentia

  mount(root) {
    root.classList.add("page");
    useCss("/static/css/chat.css");
    useCss("/static/css/composer.css");
    useCss("/static/css/trace.css");
    root.innerHTML = `<div class="inv-bar settings-actions"></div><p class="muted inv-status"></p>
      <div class="messages inv-messages" style="min-height:50vh;max-height:65vh"></div>
      <form class="ask inv-box" style="margin-top:.6rem"></form>`;
    this.root = root;
    this.bar = root.querySelector(".inv-bar");
    this.statusLine = root.querySelector(".inv-status");
    this.messages = root.querySelector(".inv-messages");
    this.box = root.querySelector(".inv-box");
    this.drawBox();
  },

  async enter() {
    try {
      const st = await call(`${API}/status`);
      this.statusLine.textContent = st.corpus ? t("evd.no_archive") : t("evd.archive", { n: st.text || 0, p: st.passages || 0 });
    } catch (e) { this.statusLine.textContent = t("evd.off", { m: e.message }); return; }
    if (this.open) await this.drawCase(this.open);
    else { this.drawBar(null); this.messages.replaceChildren(this.say(t("evd.pick"))); }
  },

  // the box of the chat: 🗂️ (the case files), the question, send
  // the box of every chat of Aurora (composer.js, owner 26 Oct: «mettendo i tasti dentro il field»): the question over
  // the whole width, inside it the 🗂️ of the case files (owner, 10 Nov: «il bottone nel blob della chat») and Send
  drawBox() {
    const pick = el("button", "icon", "🗂️");
    pick.type = "button";
    pick.title = t("evd.cases");
    pick.addEventListener("click", () => this.toggleExplorer());
    this.input = el("textarea");
    Object.assign(this.input, { rows: 2, placeholder: t("evd.ask_ph") });
    this.send = el("button", "send", t("chat.send"));
    this.send.type = "submit";
    this.box.replaceChildren(this.input, pick, this.send);
    composer({ form: this.box, input: this.input });
    this.box.addEventListener("submit", (ev) => { ev.preventDefault(); this.ask(); });
  },

  // the bar above the chat: the case's title and its buttons
  drawBar(c) {
    const items = [el("strong", "", c ? `🗂️ ${c.title}` : t("evd.no_case"))];
    if (c) {                                   // owner, 10 Nov: «esportazione… PDF ben formattato e che il riassunto funzioni»
      const btn = (label, fn) => {
        const b = el("button", "", label);
        b.addEventListener("click", async () => {
          b.disabled = true;
          try { await fn(b); } catch (e) { this.messages.append(this.say(t("ev.error", { m: e.message }))); }
          b.disabled = false;
        });
        return b;
      };
      items.push(
        btn(`📄 ${t("evd.pdf")}`, () => this.pdf(c, "case")),
        btn(`🧾 ${t("evd.summary")}`, (b) => this.summary(c, b)),
        btn(`📑 ${t("evd.dossier")}`, () => this.dossier(c)),
        btn(`⬇️ ${t("evd.markdown")}`, () => this.export(c)));
    }
    this.bar.replaceChildren(...items);
  },

  // the picker inside the box (owner, 10 Nov: «la selezione la metterei dentro il blog dove si scrive la chat… come
  // menù stile Finder»): folders → cases, stacked; the full Finder is 🗂️ Fascicoli
  async toggleExplorer(force) {
    // owner, 12 Nov: «se cliccavo sugli archivi poi non si chiudevano più» — a second click while the folders were
    // loading drew a second picker and the first stayed, orphaned: now every picker is removed, a stale load dropped
    const show = force ?? !(this.pop || this.loading);
    const turn = (this.turn = (this.turn || 0) + 1);
    this.box.querySelectorAll(".evd-pop").forEach((p) => p.remove());
    this.pop = null;
    this.loading = false;
    if (!show) return;
    const pop = el("div", "evd-pop");
    let groups;
    this.loading = true;
    try { groups = await folders(); } catch (e) { pop.append(el("p", "muted", t("evd.off", { m: e.message }))); }
    if (turn !== this.turn) return;            // closed or opened again meanwhile: this one is not drawn
    this.loading = false;
    if (groups) {
      const [left, right] = finder(groups, this.open, async (c) => { this.open = c.id; await this.toggleExplorer(false); await this.enter(); });
      const foot = el("div", "evd-bar");
      const add = el("button", "link", `➕ ${t("evd.new")}`);
      add.type = "button";
      add.addEventListener("click", async () => {
        const title = prompt(t("evd.new_title"));
        if (!title) return;
        const c = await call(`${API}/cases`, { method: "POST", body: JSON.stringify({ title }) });
        this.open = c.id;
        await this.toggleExplorer(false);
        await this.enter();
      });
      const all = el("button", "link", `🗂️ ${t("nav.evd_cases")}`);
      all.type = "button";
      all.addEventListener("click", () => { this.toggleExplorer(false); bus.emit("show", { id: "evd_cases" }); });
      foot.append(add, all);
      left.append(foot);
      pop.append(left, right);
    }
    this.pop = pop;
    this.box.append(pop);
    const away = (ev) => {                     // a click outside it or Esc closes it, as a menu does
      if (this.pop !== pop) return document.removeEventListener("pointerdown", away, true);
      if (ev.type === "keydown" ? ev.key === "Escape" : !pop.contains(ev.target) && !ev.target.closest?.("button.icon")) {
        document.removeEventListener("pointerdown", away, true);
        document.removeEventListener("keydown", away, true);
        this.toggleExplorer(false);
      }
    };
    document.addEventListener("pointerdown", away, true);
    document.addEventListener("keydown", away, true);
  },

  // a case as a conversation: its diary, question by question, answers with their sources
  async drawCase(cid) {
    let c;
    try { c = await call(`${API}/cases/${cid}`); } catch { this.open = null; return this.enter(); }
    this.drawBar(c);
    this.hits ||= {};
    const msgs = [];
    for (const s of c.diary) {
      if (s.kind === "search") {
        msgs.push(this.mine(s.content.q));
        msgs.push(this.hits[s.id] ? this.answer(this.hits[s.id], s.content.q) : this.say(t("evd.found", { n: s.content.hits, d: s.docs.length }), s.docs));
      } else if (s.kind === "question") msgs.push(this.mine(s.content.text || ""));
      else if (s.kind === "answer") msgs.push(this.told(s.content.text || ""));
      else if (s.kind === "note") msgs.push(String(s.content.text || "").startsWith("🧾") ? this.told(s.content.text, "summary") : this.say(s.content.text || "", s.docs));
      else if (s.kind === "lead") msgs.push(this.say(t("evd.lead", { n: s.content.lead, agent: s.content.agent, what: s.content.what })));
      else if (s.kind === "evidence") msgs.push(this.evidence(s.content));
    }
    this.messages.replaceChildren(...(msgs.length ? msgs : [this.say(t("evd.diary_empty"))]));
    if (this.watching?.cid === cid) this.messages.append(this.watching.root);        // still at work: its bubble stays
    else {
      const mine = Object.entries(this.runs()).find(([, r]) => r.cid === cid);
      const lastQ = [...c.diary].reverse().find((x) => x.kind === "question")?.content?.text;
      if (!mine && lastQ) {                            // started elsewhere (another tab, before a reload): by its question
        call("/v1/aurora/runs").then((got) => {
          const r = (Array.isArray(got) ? got : got.runs || []).find((x) => !x.done && x.origin === "evidentia" && x.question === lastQ);
          if (r && !this.watching) this.live(cid, r.id, lastQ);
        }).catch(() => {});
      }
      if (mine) {
        call("/v1/aurora/runs").then((got) => {
          const r = (Array.isArray(got) ? got : got.runs || []).find((x) => x.id === mine[0]);
          if (r && !r.done && !this.watching) this.live(cid, mine[0], mine[1].q);
          else if (!r || r.done) { const left = this.runs(); delete left[mine[0]]; this.runs(left); }
        }).catch(() => {});
      }
    }
    this.messages.scrollTop = this.messages.scrollHeight;
  },

  // a question (owner, 10 Nov: «la ricerca deve essere completa… la chat deve essere come Aurora, deve mostrare quello
  // che sta facendo»): the whole search at once — how many passages in all, the words used, more on request — then
  // Evidentia's investigator (one of Aurora's agents with Evidentia's tools only), followed live as Aurora's chat is
  async ask() {
    const q = this.input.value.trim();
    if (!q) return;
    if (!this.open) { await this.toggleExplorer(true); return; }
    this.send.disabled = true;
    this.input.value = "";
    this.messages.append(this.mine(q));
    const cid = this.open;
    try {
      const r = await call(`${API}/cases/${cid}/search`, { method: "POST", body: JSON.stringify({ q }) });
      const c = await call(`${API}/cases/${cid}`);
      this.hits[c.diary[c.diary.length - 1].id] = r;            // kept across Aurora's redraw after an action (main.js)
      this.messages.append(this.answer(r, q));
      this.messages.scrollTop = this.messages.scrollHeight;
      const run = await call("/v1/aurora/evidentia-ask", { method: "POST", body: JSON.stringify({ case: cid, question: q, lang }) });
      await this.live(cid, run.id, q);
    } catch (e) { this.messages.append(this.say(t("ev.error", { m: e.message }))); }
    this.send.disabled = false;
  },

  // the investigator at work, Aurora style (owner, 10 Nov: «nella chat non si vede cosa sta facendo… sembra fermo»):
  // the bubble of Aurora's chat (trace.js) with every step; kept with its case across a redraw or a visit elsewhere,
  // taken up again after a reload (the run's events from the first); while another run holds Aurora, it says so
  async live(cid, runId, q) {
    const known = this.runs();
    known[runId] = { cid, q };
    this.runs(known);
    const holder = el("div");
    const b = auroraBubble(holder);
    this.watching = { cid, runId, root: b.root };
    if (this.open === cid) this.messages.append(b.root);
    let started = false;
    const queued = async () => {
      if (started) return;
      try {
        const got = await call("/v1/aurora/runs");
        const runs = Array.isArray(got) ? got : got.runs || [];
        const other = runs.find((r) => !r.done && r.id !== runId);
        if (other && !started) b.head.querySelector(".iter-text").textContent = `⏳ ${t("evd.queued", { q: String(other.question || "").slice(0, 60) })}`;
      } catch { /* the bubble's own words stay */ }
    };
    const timer = setInterval(queued, 2500);
    queued();
    try {
      await follow(runId, b, this.messages, () => { started = true; });
    } finally {
      clearInterval(timer);
      const left = this.runs();
      delete left[runId];
      this.runs(left);
      if (this.watching?.runId === runId) this.watching = null;
      if (this.open === cid && !this.messages.contains(b.root)) await this.drawCase(cid);
    }
  },

  // the runs this page started and their cases (this tab's memory, so a reload takes them up again)
  runs(set) {
    try {
      if (set) { sessionStorage.setItem("evd.runs", JSON.stringify(set)); return set; }
      return JSON.parse(sessionStorage.getItem("evd.runs") || "{}");
    } catch { return {}; }
  },

  told(text, what = "dossier") {
    const m = el("div", "msg aurora");
    const body = el("div", "body");
    try { body.append(renderMarkdown(text)); } catch { body.textContent = text; }
    const pdf = el("button", "link evd-cite", `📄 ${t("evd.pdf")}`);
    pdf.addEventListener("click", () => this.open && this.pdf({ id: this.open }, what, text));
    m.append(body, translateButton(text, m), pdf);
    return m;
  },

  // 📄 a PDF laid out by Aurora's own printer: the whole case, a summary or a document (never kept among her files)
  async pdf(c, what, text = "") {
    const app = typeof window.AuroraApp === "object" && window.AuroraApp !== null;
    const r = await fetch("/v1/aurora/evidentia-pdf", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case: c.id, what, text, lang, ticket: app }),
    });
    if (app && r.ok) {                                  // C726: the app's WebView drops blob: downloads; a one-time
      const a = el("a");                                // address of Aurora's own reaches its download manager
      a.href = new URL((await r.json()).url, location.href).href;
      a.click();
      return;
    }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
    const name = (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "fascicolo.pdf";
    const a = el("a");
    a.href = URL.createObjectURL(await r.blob());
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
  },

  // 🧾 the case in a page, in the reader's language; it stays in the diary as a note
  async summary(c, b) {
    const was = b.textContent;
    b.textContent = `⏳ ${t("evd.summarizing")}`;
    try {
      const r = await call("/v1/aurora/evidentia-summary", { method: "POST", body: JSON.stringify({ case: c.id, lang }) });
      this.messages.append(this.told(r.text, "summary"));
      this.messages.scrollTop = this.messages.scrollHeight;
    } finally { b.textContent = was; }
  },

  // 📑 the investigative document, written by Evidentia's reporter, followed live like a question
  async dossier(c) {
    this.messages.append(this.mine(`📑 ${t("evd.dossier")}`));
    const run = await call("/v1/aurora/evidentia-dossier", { method: "POST", body: JSON.stringify({ case: c.id, lang }) });
    await this.live(c.id, run.id, "dossier");
  },

  mine(text) { return el("div", "msg user", text); },

  say(text, docs) {
    const m = el("div", "msg aurora");
    m.append(el("p", "", text));
    if (docs?.length) m.append(el("div", "muted", docs.slice(0, 12).join(" · ") + (docs.length > 12 ? " …" : "")));
    return m;
  },

  // the search's answer: {hits, total, used, mode} (an older step: a bare list of hits); every hit opens its page
  answer(r, q = "") {
    const res = Array.isArray(r) ? { hits: r, total: r.length } : r;
    const m = el("div", "msg aurora");
    if (!res.hits.length) { m.append(el("p", "", t("evd.no_hits")), this.next(q)); return m; }
    const many = res.total >= (res.cap || Infinity) ? t("evd.more_than", { n: Number(res.cap).toLocaleString() })
      : Number(res.total || res.hits.length).toLocaleString();
    m.append(el("p", "", t("evd.hits_all", { t: many, n: res.hits.length })));
    if (res.used && res.used !== q) m.append(el("div", "muted", t("evd.used", { w: res.used })));
    const list = el("div");
    const rows = (hits) => hits.map((h) => {
      const row = el("div", "ev");
      row.append(citeButton(h, res.used || q), el("div", "", h.snippet.replaceAll("«", "").replaceAll("»", "")));
      if (h.copies?.length) row.append(el("div", "muted", t("evd.copies", { n: h.copies.length, c: h.copies.slice(0, 3).join(", ") })));
      return row;
    });
    list.append(...rows(res.hits));
    m.append(list);
    let shown = res.hits.length;
    if ((res.total || 0) > shown && this.open) {
      const more = el("button", "", `⬇️ ${t("evd.more20")}`);
      const cid = this.open;
      more.addEventListener("click", async () => {
        more.disabled = true;
        try {
          const n = await call(`${API}/cases/${cid}/search`, { method: "POST", body: JSON.stringify({ q, offset: shown }) });
          list.append(...rows(n.hits));
          shown += n.hits.length;
          if (!n.hits.length || shown >= (res.total || 0)) more.remove();
        } catch (e) { more.textContent = `⚠️ ${e.message}`; }
        more.disabled = false;
      });
      m.append(more);
    }
    m.append(this.next(q));
    return m;
  },

  // what to do next with a question (owner, 10 Nov: «la chat può essere più interattiva»): a lead for an agent; a
  // person's web when the question is a name
  next(q) {
    const box = el("div", "evd-suggest");
    if (!q || !this.open) return box;
    const lead = (agent, label) => {
      const b = el("button", "", label);
      b.addEventListener("click", async () => {
        b.disabled = true;
        try {
          await call(`${API}/cases/${this.open}/leads`, { method: "POST", body: JSON.stringify({ what: q, agent, why: t("evd.from_chat") }) });
          await this.drawCase(this.open);
        } catch (e) { b.textContent = `⚠️ ${e.message}`; }
      });
      box.append(b);
    };
    lead("sniper", `🎯 ${t("evd.ask_sniper")}`);
    lead("lead_hunter", `🧭 ${t("evd.ask_hunter")}`);
    if (/^\s*"?[A-ZÀ-Ý][\w'’.-]+(\s+[A-ZÀ-Ý][\w'’.-]+){1,3}"?\s*$/.test(q)) {
      const web = el("button", "", `🕸️ ${t("evd.web_of", { n: q.replaceAll('"', "") })}`);
      web.addEventListener("click", () => { bus.emit("show", { id: "evd_net" }); net.start(q.replaceAll('"', "")); });
      box.append(web);
      lead("network_mapper", `🗺️ ${t("evd.ask_mapper")}`);
    }
    return box;
  },

  // 🧾 a lead's evidence (10 Nov: «messaggi nella chat investigativa tipo evidences»): every quote checked by Evidentia
  // on its page, each opening it
  evidence(e) {
    const m = el("div", "msg aurora");
    const head = e.status === "cold" ? "evd.cold" : "evd.evidence";
    m.append(el("p", "", t(head, { n: e.lead, agent: e.agent, what: e.what }) + (e.reused ? ` · ${t("evd.reused")}` : "")));
    if (e.summary) m.append(el("p", "", e.summary));
    for (const x of e.evidence || []) {
      const row = el("div", "ev");
      row.append(citeButton(x, x.quote), el("div", "", `«${x.quote}»`));
      if (x.note) row.append(el("div", "muted", x.note));
      m.append(row);
    }
    const all = [e.summary, ...(e.evidence || []).map((x) => `«${x.quote}» — ${x.cite}${x.note ? ` (${x.note})` : ""}`)].filter(Boolean).join("\n");
    if (all) m.append(translateButton(all, m));
    return m;
  },

  async export(c) {
    const r = await fetch(`${API}/cases/${c.id}/export.md`, { credentials: "same-origin" });
    const a = el("a");
    a.href = URL.createObjectURL(new Blob([await r.text()], { type: "text/markdown" }));
    a.download = `${c.title.replace(/[^\w\- ]+/g, "").trim() || "fascicolo"}.md`;
    a.click();
  },
};
