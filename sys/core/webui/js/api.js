// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Access to aurora-api. The browser is a registered device: after one login with the API key the
// server sets an HttpOnly cookie, sent automatically; page scripts never hold a credential.
const OLD_KEY = "aurora.key";
try { localStorage.removeItem(OLD_KEY); } catch { /* storage unavailable */ }

export async function call(path, options = {}) {
  const res = await fetch(path, {
    ...options, credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (res.status === 401) throw Object.assign(new Error("unauthorized"), { status: 401 });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw Object.assign(new Error(JSON.stringify(body.detail || res.statusText)), { status: res.status });
  }
  return res.json();
}

// Register this browser with the API key; the key is used for this request only.
export function register(apiKey, name) {
  return call("/v1/aurora/devices", { method: "POST", headers: { Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({ name }) });
}

// Server-sent events over fetch (same authentication as every other call).
export async function stream(path, onEvent) {
  const res = await fetch(path, { credentials: "same-origin" });
  if (!res.ok) throw Object.assign(new Error(`stream ${res.status}`), { status: res.status });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      if (block.startsWith("event: end")) return;
      const data = block.split("\n").find((l) => l.startsWith("data: "));
      if (data) onEvent(JSON.parse(data.slice(6)));
    }
  }
}
