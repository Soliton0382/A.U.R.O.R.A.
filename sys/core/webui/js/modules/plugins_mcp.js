// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🔌 The owner's MCP servers (owner, 10 Nov: «una sezione dedita all'integrazione dei server mcp così che aurora possa
// usarli nella chat»): the list with each server's state and tools, a form to add one — a program on this machine
// (in the plugins' cage, reading only the places named) or an address, http or https — and the removal. A server added
// is loaded once signed (sudo aurora-root sign), like every plugin of the owner's. The admin only (plugins.js).
import { call } from "../api.js";
import { bus } from "../bus.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";

const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);

function serverRow(s, done) {
  const row = el("div", "ev");
  const state = s.unsigned ? `✍️ ${t("mcp.unsigned")}` : s.available ? `✅ ${t("plug.on")}` : `⚠️ ${s.error || t("plug.off")}`;
  const flags = [s.remote ? (s.clear ? `🌐 ${t("mcp.clear")}` : "🌐 https") : `💻 ${t("mcp.local")}`,
    s.chat ? `💬 ${t("mcp.in_chat")}` : `🚫 ${t("mcp.not_chat")}`, s.memory ? `🧠 ${t("mcp.kept")}` : `🫥 ${t("mcp.not_kept")}`];
  row.append(el("strong", "", s.name), el("span", "muted", ` · ${state} · ${flags.join(" · ")}`),
    el("div", "muted", s.description), el("div", "muted", s.where));
  if (s.tools.length) {
    row.append(el("div", "", s.tools.map((x) => `${x.effect === "read" ? "👁️" : "🛎️"} ${x.name}`).join("  ")));
  }
  const del = el("button", "link", `🗑️ ${t("mcp.remove")}`);
  del.addEventListener("click", async () => {
    if (!confirm(t("mcp.remove_q", { name: s.name }))) return;
    try { await call(`/v1/aurora/mcp-servers/${encodeURIComponent(s.name)}`, { method: "DELETE" }); bus.emit("plugins", {}); done(); }
    catch (e) { alert(e.message); }
  });
  row.append(del);
  return row;
}

function form(done) {
  const f = el("form", "settings-form");
  const field = (key, input) => { const l = el("label", "", t(key)); l.append(input); return l; };
  const name = Object.assign(el("input"), { placeholder: "archive", pattern: "[a-z][a-z0-9_]{1,29}", required: true });
  const desc = Object.assign(el("textarea"), { rows: 2, placeholder: t("mcp.desc_ph"), required: true });
  const kind = el("select");
  kind.append(new Option(`💻 ${t("mcp.local")}`, "local"), new Option(`🌐 ${t("mcp.remote")}`, "remote"));
  const command = Object.assign(el("textarea"), { rows: 3, placeholder: "/opt/server/.venv/bin/python\n-I\n/opt/server/server.py" });
  const read = Object.assign(el("textarea"), { rows: 2, placeholder: "/opt/server" });
  const url = Object.assign(el("input"), { type: "url", placeholder: "https://mcp.example.org/mcp" });
  const reads = Object.assign(el("input"), { placeholder: "search, read_page" });
  const chat = Object.assign(el("input"), { type: "checkbox", checked: true });
  const memory = Object.assign(el("input"), { type: "checkbox", checked: true });
  const localBox = el("div", "", "");
  localBox.append(field("mcp.command", command), field("mcp.read", read));
  const remoteBox = el("div", "", "");
  remoteBox.append(field("mcp.url", url));
  const sync = () => { localBox.hidden = kind.value !== "local"; remoteBox.hidden = kind.value !== "remote"; };
  kind.addEventListener("change", sync);
  sync();
  const out = el("p", "muted");
  const go = el("button", "approve", `➕ ${t("mcp.add")}`);
  f.append(field("mcp.name", name), field("mcp.desc", desc), field("mcp.kind", kind), localBox, remoteBox,
    field("mcp.read_tools", reads), field("mcp.chat", chat), field("mcp.memory", memory), go, out);
  f.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = { name: name.value.trim(), description: desc.value.trim(), chat: chat.checked, memory: memory.checked,
      read_tools: reads.value.split(",").map((x) => x.trim()).filter(Boolean) };
    if (kind.value === "local") Object.assign(body, { command: lines(command.value), read: lines(read.value) });
    else body.url = url.value.trim();
    go.disabled = true;
    try {
      await call("/v1/aurora/mcp-servers", { method: "POST", body: JSON.stringify(body) });
      out.textContent = `✍️ ${t("mcp.saved")}`;
      bus.emit("plugins", {});
      done();
    } catch (e) { out.textContent = `⚠️ ${e.message}`; }
    go.disabled = false;
  });
  return f;
}

export async function mcpBox(done) {
  const box = el("details", "report plug-mcp");
  let servers = [];
  try { ({ servers } = await call("/v1/aurora/mcp-servers")); } catch { /* the list is the admin's: shown empty */ }
  box.append(el("summary", "", `🔌 ${t("mcp.title")} (${servers.length})`), el("p", "muted", t("mcp.hint")));
  for (const s of servers) box.append(serverRow(s, done));
  box.append(form(done));
  return box;
}
