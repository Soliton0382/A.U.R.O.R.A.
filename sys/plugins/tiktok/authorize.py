# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Authorize Aurora on TikTok, once (OAuth 2.0). Run it from Aurora's folder:

    .venv/bin/python sys/plugins/tiktok/authorize.py

It prints the address to open (logged in to the TikTok account), you accept, TikTok sends the browser to the Redirect
URI of your app with ?code=… in the address bar: paste that whole address here. The refresh token (365 days) is saved
through Aurora's settings (never printed).
"""
from __future__ import annotations

import json
import secrets
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
import httpx  # noqa: E402

from aurora import sys_config  # noqa: E402

cfg = sys_config.get()
key, secret, redirect = (str(cfg.values.get(k) or "").strip() for k in
                         ("AURORA_TIKTOK_CLIENT_KEY", "AURORA_TIKTOK_CLIENT_SECRET", "AURORA_TIKTOK_REDIRECT_URI"))
if not (key and secret and redirect):
    sys.exit("first put client key, client secret and redirect URI in the tiktok plugin's card")
state = secrets.token_urlsafe(16)
print("\n1) Open this address, logged in to the TikTok account Aurora will use, and accept:\n")
print("https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": key, "scope": "user.info.basic,video.publish,video.upload", "response_type": "code",
    "redirect_uri": redirect, "state": state}))
back = input("\n2) Paste here the whole address the browser shows after accepting:\n> ").strip()
q = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
if q.get("state", [""])[0] != state:
    sys.exit("the address is not the answer to this request (state differs): run again")
code = q.get("code", [""])[0]
r = httpx.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
    "client_key": key, "client_secret": secret, "code": code, "grant_type": "authorization_code", "redirect_uri": redirect}).json()
if "refresh_token" not in r:
    sys.exit(f"TikTok refused: {r.get('error_description') or r.get('error')}")
api_key = cfg["AURORA_API_KEY"]
res = httpx.put(f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}/v1/aurora/settings", timeout=30,
                headers={"Authorization": f"Bearer {api_key}"}, json={"AURORA_TIKTOK_REFRESH_TOKEN": r["refresh_token"]})
res.raise_for_status()
print(f"\nDone: Aurora is authorized on TikTok (scopes: {r.get('scope')}; valid {r.get('refresh_expires_in', 0) // 86400} days).")
print("Restart aurora-api from the Settings page, then press ▶ Try on tiktok_account.")
