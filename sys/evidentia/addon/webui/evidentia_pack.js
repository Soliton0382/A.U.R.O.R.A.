// 📦 the web handed to the investigation (this installation's own, never published; owner, 12 Nov: «quando clicco,
// essendo che si espandono e rafforzano i legami, si possa passare "il pacchetto" all'investigazione così che la
// ragnatela si espanda in ogni direzione recuperando i legami e vagliando di conseguenza diverse piste»). The public
// people drawn — the ones opened first, then the most tied — become leads of one case for the network mapper: each
// maps that person's documented ties, reads the messages, and opens a lead for every tie worth a deeper look (at most
// three steps from the start, Evidentia's MAX_DEPTH): the web grows in every direction by itself, through the leads.
// A private person (grey) is never in the package; a protected name never reaches the drawing.
import { bus } from "/static/js/bus.js";
import { call } from "/static/js/api.js";
import { el } from "/static/js/dom.js";
import { t } from "/static/js/i18n.js";
import { API } from "./evidentia_view.js";
import { folders } from "./evidentia_cases.js";

const SHOWN = 16, CHOSEN = 8;          // a case holds at most 20 open leads (Evidentia's MAX_OPEN): room left for theirs
const AGENT = "network_mapper";

// the public people of the drawing, opened ones first, then by how many messages tie them in
export function candidates(nodes, links) {
  const weight = new Map(), peers = new Map();
  for (const l of links.values()) {
    for (const [me, other] of [[l.a, l.b], [l.b, l.a]]) {
      weight.set(me, (weight.get(me) || 0) + (l.n || 1));
      if (other.public) (peers.get(me) || peers.set(me, []).get(me)).push([other.name, l.n || 1]);
    }
  }
  return [...nodes.values()].filter((n) => n.public && n.name)
    .map((n) => ({ node: n, open: !!n.open, weight: weight.get(n) || 0,
      peers: (peers.get(n) || []).sort((a, b) => b[1] - a[1]).slice(0, 5).map((p) => p[0]) }))
    .sort((a, b) => (b.open - a.open) || (b.weight - a.weight))
    .slice(0, SHOWN);
}

export function lead(c, seed) {
  return {
    agent: AGENT,
    what: `Map the documented ties of ${c.node.name}: who they wrote to and were copied with, what the messages are ` +
      "about, and which ties lead further",
    why: `From the web around ${seed}, drawn in Aurora` +
      (c.peers.length ? `: ${c.node.name} is tied there to ${c.peers.join(", ")}` : "") +
      ". Follow the ties the documents support in every direction; open a lead for each one worth a deeper look.",
  };
}

// the side card: which case, which people (the first ones ticked), then the leads opened one by one
export async function pack(net) {
  const box = net.side;
  const list = candidates(net.nodes, net.links);
  if (!list.length) { box.replaceChildren(el("p", "muted", t("evd.pack_none"))); return; }
  const seed = [...net.nodes.values()][0]?.name || list[0].node.name;
  box.replaceChildren(el("h3", "", `📦 ${t("evd.pack_title")}`), el("p", "muted", t("evd.pack_hint")));
  const pick = el("select");
  pick.append(Object.assign(el("option", "", `➕ ${t("evd.pack_new", { s: seed })}`), { value: "" }));
  try {
    for (const cs of Object.values(await folders())) {
      for (const c of cs) pick.append(Object.assign(el("option", "", c.title), { value: c.id }));
    }
  } catch { /* Evidentia off: a new case only */ }
  box.append(pick);
  const ticks = list.map((c, i) => {
    const row = el("label", "evd-lead");
    const box2 = Object.assign(el("input"), { type: "checkbox", checked: i < CHOSEN });
    row.append(box2, el("span", "", ` 👤 ${c.node.name}` + (c.open ? " · 🔓" : "") + ` · ${c.weight}`));
    return [box2, row, c];
  });
  box.append(...ticks.map((x) => x[1]));
  const go = el("button", "approve", `📦 ${t("evd.pack_go")}`);
  const out = el("div", "");
  box.append(go, out);
  go.addEventListener("click", async () => {
    const chosen = ticks.filter((x) => x[0].checked).map((x) => x[2]);
    if (!chosen.length) return;
    go.disabled = true;
    let cid = pick.value;
    try {
      if (!cid) cid = (await call(`${API}/cases`, { method: "POST", body: JSON.stringify({ title: `🕸️ ${seed}` }) })).id;
    } catch (e) { out.replaceChildren(el("p", "muted", t("evd.off", { m: e.message }))); go.disabled = false; return; }
    let opened = 0, reused = 0;
    for (const c of chosen) {
      const row = el("div", "muted", `… ${c.node.name}`);
      out.append(row);
      try {
        const r = await call(`${API}/cases/${cid}/leads`, { method: "POST", body: JSON.stringify(lead(c, seed)) });
        r.reused ? reused++ : opened++;
        row.textContent = `${r.reused ? "♻️" : "🧭"} ${c.node.name} · #${r.id}`;
      } catch (e) {                                   // the case's or the archive's cap: said, the rest not tried
        row.textContent = `⛔ ${c.node.name}: ${e.message}`;
        break;
      }
    }
    const open = el("button", "", `🗂️ ${t("evd.pack_open")}`);
    open.addEventListener("click", async () => {
      const cases = (await import("./evidentia_cases.js")).default;
      cases.current = cid;
      bus.emit("show", { id: "evd_cases" });
    });
    out.append(el("p", "", t("evd.pack_done", { n: opened, r: reused })), open);
  });
}
