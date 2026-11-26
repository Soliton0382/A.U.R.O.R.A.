// 🕵️ Evidentia's pages beside its chat (this installation's own, never published; owner, 10 Nov: «menù in aurora…
// sotto menù… archivi… gestione del server mcp con health status… agenti… routine… a blocchi come le altre»):
// 🗄️ the archives, 🩺 the server, 🤖 the agents, 🔁 the routines (the leads' queue). Everything comes from Evidentia's
// own service through Aurora's local route (local/api_evidentia: fixed paths, the admin's alone); nothing of it is kept
// in Aurora. Every page is read-only but the routines', where the owner may drop a lead not yet finished.
import { call } from "/static/js/api.js";
import { el, useCss } from "/static/js/dom.js";
import { t } from "/static/js/i18n.js";
import { sourcesCard } from "./evidentia_sources.js";

const API = "/v1/aurora/evidentia";
const n = (x) => Number(x || 0).toLocaleString();
const gb = (b) => `${(Number(b || 0) / 1e9).toLocaleString(undefined, { maximumFractionDigits: 1 })} GB`;
const day = (s) => (s ? new Date(s * 1000).toLocaleString() : "—");

function card(title, cls = "") {
  const c = el("div", `evd-card ${cls}`.trim());
  c.append(el("h3", "", title));
  return c;
}

function rows(pairs) {
  const r = el("div", "evd-rows");
  for (const [k, v] of pairs) r.append(el("span", "", k), el("span", "", String(v)));
  return r;
}

function page(id, icon, title, hint, draw) {
  return {
    id, icon, title, adminOnly: true,
    mount(root) {
      root.classList.add("page");
      useCss("/static/addons/evidentia/evidentia.css");
      this.body = el("div");
      root.append(el("h2", "", `${icon} ${t(title)}`), el("p", "muted", t(hint)), this.body);
    },
    async enter() {
      this.body.replaceChildren(el("p", "muted", "…"));
      try { this.body.replaceChildren(...await draw(this)); } catch (e) {
        this.body.replaceChildren(el("p", "muted", t("evd.off", { m: e.message })));
      }
    },
  };
}

// 🗄️ the collections of the archive, each with its numbers; the vectors for the whole archive
export const archivesPage = page("evd_archives", "🗄️", "nav.evd_archives", "evd.archives_hint", async () => {
  const r = await call(`${API}/collections`);
  const grid = el("div", "evd-grid");
  for (const c of r.collections) {
    const k = card(`📁 ${c.collection}`, c.failed ? "bad" : "ok");
    k.append(el("div", "evd-num", n(c.docs)), el("div", "muted", t("evd.docs")),
      rows([[t("evd.pages"), n(c.pages)], [t("evd.passages"), n(c.passages)], [t("evd.k_text"), n(c.text)],
        [t("evd.k_scan"), n(c.scan)], [t("evd.k_mixed"), n(c.mixed)], [t("evd.k_image"), n(c.image)],
        [t("evd.failed"), n(c.failed)]]));
    grid.append(k);
  }
  const v = r.vectors;
  const vk = card(`🧭 ${t("evd.vectors")}`, v.blocks >= v.expected && v.expected ? "ok" : "bad");
  vk.append(el("div", "evd-num", `${v.blocks} / ${v.expected}`), el("div", "muted", t("evd.blocks")),
    rows([[t("evd.passages"), n(r.passages)], [t("evd.model"), v.models.join(", ") || "—"], [t("evd.size"), gb(v.bytes)]]));
  grid.append(vk);
  grid.append(sourcesCard());                          // 📥 a folder read in from here (R22, evidentia_sources.js)
  return [grid, el("p", "muted", t("evd.counted", { at: day(r.at) }))];
});

// 🩺 the server: Evidentia's service, its plugin in Aurora (an MCP server in her cage), the archive's files, the originals, the queue
export const serverPage = page("evd_server", "🧰", "nav.evd_server", "evd.server_hint", async () => {
  const [h, mcp] = await Promise.all([call(`${API}/health`),
    call("/v1/aurora/mcp-servers").catch(() => ({ servers: [] }))]);
  const s = (mcp.servers || []).find((x) => x.name === "evidentia");      // the plugin (27 Nov: no more local_evidentia)
  const grid = el("div", "evd-grid");
  const api = card(`🟢 ${t("evd.api")}`, h.archive ? "ok" : "bad");
  api.append(rows([[t("evd.state"), h.archive ? `✅ ${t("evd.running")}` : `⚠️ ${t("evd.no_archive")}`],
    [t("evd.since"), day(h.up_since)], ["PID", h.pid]]));
  const m = card(`🧩 ${t("evd.mcp")}`, s?.available ? "ok" : "bad");
  if (!s) m.append(el("p", "muted", t("evd.mcp_missing")));
  else {
    m.append(rows([[t("evd.state"), s.unsigned ? `✍️ ${t("evd.unsigned")}` : s.available ? `✅ ${t("evd.running")}` : `⚠️ ${s.error}`],
      [t("evd.memory"), s.memory ? "🧠" : `🫥 ${t("evd.not_kept")}`], [t("evd.tools"), s.tools.length]]));
    m.append(el("div", "muted", s.tools.map((x) => `${x.effect === "read" ? "👁️" : "🛎️"} ${x.name}`).join("  ")));
  }
  const files = card(`💾 ${t("evd.files")}`);
  files.append(rows(Object.entries(h.files).map(([k, v]) => [k, gb(v)])));
  const src = card(`📂 ${t("evd.sources")}`, h.sources.reachable ? "ok" : "bad");
  src.append(el("div", "evd-code", h.sources.path),
    el("p", "", h.sources.reachable ? `✅ ${t("evd.reachable")}` : `⚠️ ${t("evd.unreachable")}`));
  const q = card(`🔁 ${t("evd.queue")}`);
  q.append(rows(["open", "working", "done", "cold", "dropped"].map((k) => [t(`evd.st_${k}`), n(h.leads[k])])));
  const ag = card(`🦾 ${t("nav.evd_agents")}`, h.agents.active > 0 ? "ok" : "bad");
  ag.append(rows([[t("evd.active"), h.agents.active], [t("evd.proposed"), h.agents.proposed]]));
  grid.append(api, m, files, src, q, ag);
  return [grid, el("p", "muted", t("evd.checked", { at: day(h.at) }))];
});

// 🤖 the agents, by pack; the proposals waiting for the owner
export const agentsPage = page("evd_agents", "🦾", "nav.evd_agents", "evd.agents_hint", async () => {
  const r = await call(`${API}/agents`);
  const out = [];
  for (const profile of ["investigative", "legal", "common"]) {
    const grid = el("div", "evd-grid");
    for (const a of r.agents.filter((x) => x.profile === profile)) {
      const k = card(a.title);
      const more = el("details");
      more.append(el("summary", "", t("evd.instructions")), el("pre", "", a.instructions));
      k.append(el("div", "evd-code", a.name), el("p", "", a.description), more);
      grid.append(k);
    }
    out.push(el("h3", "", t(`evd.pack_${profile}`)), grid);
  }
  out.push(el("h3", "", `📝 ${t("evd.proposed")}`));
  if (!r.proposed.length) out.push(el("p", "muted", t("evd.no_proposals")));
  for (const p of r.proposed) {
    const k = card(`${p.title} · ${t(`evd.pack_${p.profile}`)}`);
    k.append(el("p", "", p.description), el("div", "evd-code", `.venv/bin/python sys/core/script/evd_agents.py show ${p.name}`),
      el("div", "evd-code", `.venv/bin/python sys/core/script/evd_agents.py approve ${p.name}`));
    out.push(k);
  }
  return out;
});

// 🤖 the lead worker (local/evd_worker): Aurora working the open leads by herself, one at a time, when nobody uses her
async function workerCard(view) {
  const k = card(`🤖 ${t("evd.worker")}`);
  let w;
  try { w = await call("/v1/aurora/evidentia-worker"); } catch (e) { k.append(el("p", "muted", t("evd.off", { m: e.message }))); return k; }
  const sw = el("button", w.on ? "" : "approve", w.on ? `⏸️ ${t("evd.worker_off")}` : `▶️ ${t("evd.worker_on")}`);
  sw.addEventListener("click", async () => {
    await call("/v1/aurora/evidentia-worker", { method: "POST", body: JSON.stringify({ on: !w.on }) });
    view.enter();
  });
  k.append(el("p", "", w.on ? `🟢 ${t("evd.worker_is_on")}` : `⚪ ${t("evd.worker_is_off")}`),
    el("p", "muted", t("evd.worker_hint", { e: w.every_minutes, s: w.steps, m: w.minutes })), sw);
  for (const r of (w.last || []).slice(0, 6)) {
    k.append(el("div", "muted", `#${r.lead} · ${t(`evd.st_${r.result}`)} · ${day(r.at)}${r.steps ? ` · ${r.steps} ${t("evd.steps")}` : ""}`));
  }
  return k;
}

// 🔁 the routines: the leads' queue of the whole archive (each done once), their evidence, a drop for one not finished
export const routinesPage = page("evd_routines", "🔁", "nav.evd_routines", "evd.routines_hint", async (view) => {
  view.status ??= "";
  const pick = el("select");
  for (const k of ["", "open", "working", "done", "cold", "dropped"]) pick.append(new Option(k ? t(`evd.st_${k}`) : t("evd.all"), k));
  pick.value = view.status;
  pick.addEventListener("change", () => { view.status = pick.value; view.enter(); });
  const { leads } = await call(`${API}/leads${view.status ? `?status=${view.status}` : ""}`);
  const box = card(`🧭 ${t("evd.leads")} (${leads.length})`);
  if (!leads.length) box.append(el("p", "muted", t("evd.no_leads")));
  for (const l of leads) {
    const row = el("div", "evd-lead");
    row.append(el("strong", "", `#${l.id} · ${t(`evd.st_${l.status}`)} · ${l.agent}`), el("div", "", l.what),
      el("div", "muted", `${t("evd.depth")} ${l.depth} · ${day(l.created)}${l.finished ? ` → ${day(l.finished)}` : ""}`));
    if (l.summary) row.append(el("p", "", l.summary));
    for (const e of (l.evidence || []).slice(0, 5)) row.append(el("div", "evd-quote", `«${e.quote}» — ${e.cite}`));
    if ((l.evidence || []).length > 5) row.append(el("div", "muted", t("evd.more", { n: l.evidence.length - 5 })));
    if (l.status === "open" || l.status === "working") {
      const drop = el("button", "link", `🗑️ ${t("evd.drop")}`);
      drop.addEventListener("click", async () => {
        const why = prompt(t("evd.drop_why"));
        if (why === null) return;
        await call(`${API}/leads/${l.id}`, { method: "DELETE", body: JSON.stringify({ why }) });
        view.enter();
      });
      row.append(drop);
    }
    if (l.status === "cold" || l.status === "dropped") {                 // ↩️ the owner's only (B20): agents never reach it
      if (l.worker) row.append(el("div", "muted", t("evd.closed_by", { who: l.worker })));
      const again = el("button", "link", `↩️ ${t("evd.reopen")}`);
      again.addEventListener("click", async () => {
        const why = prompt(t("evd.reopen_why"));
        if (why === null) return;
        await call(`${API}/leads/${l.id}/reopen`, { method: "POST", body: JSON.stringify({ why }) });
        view.enter();
      });
      row.append(again);
    }
    box.append(row);
  }
  const bar = el("div", "evd-bar");
  bar.append(el("span", "", t("evd.filter")), pick);
  return [await workerCard(view), bar, box];
});
