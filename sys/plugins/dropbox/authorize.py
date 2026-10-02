# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Authorize Aurora on Dropbox, once. From Aurora's folder:

    .venv/bin/python sys/plugins/dropbox/authorize.py

Open the address it prints, allow, copy the code Dropbox shows and paste it here. The refresh token (it does not
expire) is saved through Aurora's settings, never printed.
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
import httpx  # noqa: E402

from aurora import sys_config  # noqa: E402

cfg = sys_config.get()
key, secret = (str(cfg.values.get(k) or "").strip() for k in ("AURORA_DROPBOX_APP_KEY", "AURORA_DROPBOX_APP_SECRET"))
if not (key and secret):
    sys.exit("first put the app key and the app secret in the dropbox plugin's card")
print("\n1) Open this address, logged in to Dropbox, and allow Aurora:\n")
print("https://www.dropbox.com/oauth2/authorize?" + urllib.parse.urlencode(
    {"client_id": key, "response_type": "code", "token_access_type": "offline"}))
code = input("\n2) Paste the code Dropbox shows:\n> ").strip()
r = httpx.post("https://api.dropboxapi.com/oauth2/token", timeout=30, data={
    "code": code, "grant_type": "authorization_code", "client_id": key, "client_secret": secret}).json()
if "refresh_token" not in r:
    sys.exit(f"Dropbox refused: {r.get('error_description') or r.get('error')}")
res = httpx.put(f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}/v1/aurora/settings", timeout=30,
                headers={"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"},
                json={"AURORA_DROPBOX_REFRESH_TOKEN": r["refresh_token"]})
res.raise_for_status()
print("\nDone: Aurora is authorized on Dropbox. Restart aurora-api from the Settings page, then ▶ Try dropbox_list.")
