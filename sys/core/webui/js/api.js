// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// Access to aurora-api. The browser is a registered device: after one login with the API key the
// server sets an HttpOnly cookie, sent automatically; page scripts never hold a credential.
const OLD_KEY = "aurora.key";
try { localStorage.removeItem(OLD_KEY); } catch { /* storage unavailable */ }

// A lost connection is not an error of Aurora (owner, 2026-10-08: «uscendo e rientrando dalla PWA… network error»,
// C199): the request is sent again once the page is visible and online, with the same key (X-Aurora-Request), so the
// server answers it once — a post, a firewall change, a video are never made twice, and their answer is not lost.
const TRIES = 6;
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

export function back() {                               // the page visible and the network up again
  return new Promise((ok) => {
    const ready = () => !document.hidden && navigator.onLine !== false;
    if (ready()) { ok(); return; }
    const check = () => { if (ready()) { document.removeEventListener("visibilitychange", check); removeEventListener("online", check); ok(); } };
    document.addEventListener("visibilitychange", check);
    addEventListener("online", check);
  });
}

function lost(e) { return e instanceof TypeError || /network|fetch|load failed/i.test(String(e?.message)); }

export async function call(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const key = method === "GET" ? null
    : (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`);
  // the server keeps answers up to 8 MB (aurora/sys_replay.py): a bigger upload is never sent twice by itself
  const again = !key || typeof options.body !== "string" || options.body.length <= 8 * 2 ** 20;
  for (let attempt = 1; ; attempt++) {
    let res, out;
    try {
      res = await fetch(path, {
        ...options, credentials: "same-origin",
        headers: { "Content-Type": "application/json", ...(key ? { "X-Aurora-Request": key } : {}), ...(options.headers || {}) },
      });
      if (res.status === 401) throw Object.assign(new Error("unauthorized"), { status: 401 });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw Object.assign(new Error(JSON.stringify(body.detail || res.statusText)), { status: res.status });
      }
      out = await res.json();
    } catch (e) {
      if (e.status || e.name === "AbortError" || !lost(e) || !again || attempt >= TRIES) {
        throw lost(e) && !e.status ? Object.assign(new Error("connection lost (the work may still be running: try again in a moment)"), { lost: true }) : e;
      }
      await back();
      await sleep(Math.min(1000 * 2 ** (attempt - 1), 8000));
      continue;
    }
    return out;
  }
}

// Register this browser with the API key; the key is used for this request only.
export function register(apiKey, name) {
  return call("/v1/aurora/devices", { method: "POST", headers: { Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({ name }) });
}

// Server-sent events over fetch (same authentication as every other call). True when the server said the end;
// false when the connection closed before it (the caller follows again: followRun).
export async function stream(path, onEvent) {
  const res = await fetch(path, { credentials: "same-origin" });
  if (!res.ok) throw Object.assign(new Error(`stream ${res.status}`), { status: res.status });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return false;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      if (block.startsWith("event: end")) return true;
      const data = block.split("\n").find((l) => l.startsWith("data: "));
      if (data) onEvent(JSON.parse(data.slice(6)));
    }
  }
}

// A run's events followed to its end across lost connections (C199): from the last event seen, again and again while
// the page is away; the work goes on on the server meanwhile. onRetry says it to the user.
export async function followRun(runId, onEvent, onRetry) {
  let last = 0;
  for (let attempt = 0; ;) {
    try {
      const ended = await stream(`/v1/aurora/runs/${runId}/events${last ? `?after=${last}` : ""}`, (e) => { last = e.seq || last; onEvent(e); });
      if (ended) return;
      attempt = 0;                                      // it closed cleanly: follow again at once
    } catch (e) {
      if (e.status === 404 || e.status === 401 || ++attempt > 60) throw e;
      onRetry?.();
      await back();
      await sleep(Math.min(2000 * attempt, 10000));
    }
  }
}
