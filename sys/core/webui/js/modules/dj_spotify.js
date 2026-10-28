// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🟢 Spotify in the DJ page, for a Premium account (plugin spotify; owner, 28 Oct: «lasciamolo come plugin interno alla
// pagina che uso se lo attiva se ha premium… con la guida che spiega come fare»). Everything in this browser: the
// sign-in (OAuth with PKCE: no secret anywhere, the token kept here only), Spotify's own player (Web Playback SDK) as a
// device of the account, a link pasted and played. Shown only when the installation has a Client ID
// (AURORA_SPOTIFY_CLIENT_ID); the WebUI's security policy opens to Spotify only then (net_https).
import { el } from "../dom.js";
import { t } from "../i18n.js";

const KEY = "aurora.spotify";
const SCOPES = "streaming user-read-email user-read-private user-read-playback-state user-modify-playback-state";
const redirect = () => `${location.origin}/`;
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const kept = () => { try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch { return null; } };
const keep = (v) => { try { v ? localStorage.setItem(KEY, JSON.stringify(v)) : localStorage.removeItem(KEY); } catch { /* fine */ } };

async function token(form) {
  const r = await fetch("https://accounts.spotify.com/api/token", {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams(form) });
  const d = await r.json();
  if (!r.ok) throw new Error(d.error_description || d.error || `Spotify ${r.status}`);
  const prev = kept() || {};
  const v = { access: d.access_token, refresh: d.refresh_token || prev.refresh, exp: Date.now() + (d.expires_in - 60) * 1000 };
  keep(v);
  return v;
}

// back from Spotify's sign-in: the code exchanged here, the address cleaned, the DJ page opened
(async () => {
  const q = new URLSearchParams(location.search);
  let want = null;
  try { want = JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch { /* fine */ }
  if (!q.get("code") || !want || q.get("state") !== want.state) return;
  try {
    await token({ grant_type: "authorization_code", code: q.get("code"), redirect_uri: redirect(), client_id: want.client, code_verifier: want.verifier });
  } catch (e) { console.warn("spotify sign-in:", e.message); }
  try { sessionStorage.removeItem(KEY); } catch { /* fine */ }
  history.replaceState(null, "", "/?view=dj");
})();

async function access(client) {
  let v = kept();
  if (!v) return null;
  if (Date.now() > v.exp && v.refresh) v = await token({ grant_type: "refresh_token", refresh_token: v.refresh, client_id: client });
  return v.access;
}

async function signIn(client) {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(48)));
  const state = b64url(crypto.getRandomValues(new Uint8Array(12)));
  const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  sessionStorage.setItem(KEY, JSON.stringify({ verifier, state, client }));
  location.href = "https://accounts.spotify.com/authorize?" + new URLSearchParams({ response_type: "code", client_id: client,
    scope: SCOPES, redirect_uri: redirect(), state, code_challenge_method: "S256", code_challenge: challenge });
}

// a link of open.spotify.com (or a spotify: URI) as what the player takes
function what(link) {
  const m = String(link).trim().match(/(?:open\.spotify\.com\/(?:intl-[a-z]+\/)?|spotify:)(track|album|playlist|artist)[/:]([A-Za-z0-9]{22})/);
  if (!m) return null;
  const uri = `spotify:${m[1]}:${m[2]}`;
  return m[1] === "track" ? { uris: [uri] } : { context_uri: uri };
}

let sdk = null;
const loadSdk = () => sdk || (sdk = new Promise((ok) => {
  window.onSpotifyWebPlaybackSDKReady = () => ok(window.Spotify);
  const s = document.createElement("script");
  s.src = "https://sdk.scdn.co/spotify-player.js";
  document.head.append(s);
}));

export function spotifyPanel(state) {
  const client = state?.spotify?.client_id || "";
  if (!client) return null;                           // not set up here: nothing shown (the guide is in the plugin's card)
  const box = el("details", "report dj-spotify");
  box.append(el("summary", "", `🟢 ${t("dj.spotify.title")}`), el("p", "muted", t("dj.spotify.hint", { uri: redirect() })));
  const out = el("p", "muted");
  const now = el("div", "dj-spotify-now");
  const row = el("div", "appr-actions");
  const link = el("input", "dj-spotify-link");
  link.placeholder = t("dj.spotify.ph");
  const btn = (label, title) => { const b = el("button", "", label); b.type = "button"; b.title = title; return b; };
  const play = btn("▶", t("dj.spotify.play")), pause = btn("⏯", t("dj.spotify.pause")), next = btn("⏭", t("dj.spotify.next")),
    prev = btn("⏮", t("dj.spotify.prev")), conn = btn(`🔗 ${t("dj.spotify.connect")}`, ""), off = btn(`⏏ ${t("dj.spotify.off")}`, "");
  row.append(link, play, prev, pause, next);
  box.append(out, now, row, el("div", "appr-actions", ""), conn, off);
  let player = null, device = null;

  const show = (s) => {
    const tr = s?.track_window?.current_track;
    now.replaceChildren(...(tr ? [el("img", "dj-spotify-art"), el("strong", "", tr.name), el("span", "muted", ` — ${tr.artists.map((a) => a.name).join(", ")}`)] : []));
    if (tr?.album?.images?.[0]?.url?.startsWith("https://i.scdn.co/")) now.firstChild.src = tr.album.images[0].url;
  };
  const start = async () => {
    const tok = await access(client).catch(() => null);
    conn.hidden = Boolean(tok); off.hidden = !tok; row.hidden = !tok;
    if (!tok) { out.textContent = t("dj.spotify.signed_out"); return; }
    out.textContent = `✻ ${t("dj.spotify.starting")}`;
    const Spotify = await loadSdk();
    player = new Spotify.Player({ name: "Aurora", volume: 0.8, getOAuthToken: (cb) => access(client).then(cb) });
    player.addListener("ready", ({ device_id }) => { device = device_id; out.textContent = t("dj.spotify.ready"); });
    player.addListener("not_ready", () => { out.textContent = t("dj.spotify.not_ready"); });
    player.addListener("player_state_changed", show);
    for (const ev of ["initialization_error", "authentication_error", "account_error", "playback_error"]) {
      player.addListener(ev, ({ message }) => { out.textContent = `⚠ ${ev === "account_error" ? t("dj.spotify.premium") : message}`; });
    }
    player.connect();
  };
  play.addEventListener("click", async () => {
    const body = what(link.value);
    if (!body) { out.textContent = `⚠ ${t("dj.spotify.bad_link")}`; return; }
    if (!device) { out.textContent = `⚠ ${t("dj.spotify.not_ready")}`; return; }
    const r = await fetch(`https://api.spotify.com/v1/me/player/play?device_id=${encodeURIComponent(device)}`, {
      method: "PUT", headers: { Authorization: `Bearer ${await access(client)}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) out.textContent = `⚠ Spotify ${r.status}${r.status === 403 ? ` — ${t("dj.spotify.premium")}` : ""}`;
  });
  pause.addEventListener("click", () => player?.togglePlay());
  next.addEventListener("click", () => player?.nextTrack());
  prev.addEventListener("click", () => player?.previousTrack());
  conn.addEventListener("click", () => signIn(client));
  off.addEventListener("click", () => { player?.disconnect(); keep(null); start(); });
  box.addEventListener("toggle", () => { if (box.open && !player) start(); });
  return box;
}
