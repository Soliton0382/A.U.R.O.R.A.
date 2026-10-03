# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Artifacts: interactive pages Aurora makes on request (a chart, a calculator, a simulation, a small app), shown
live in the chat.

An artifact is one self-contained HTML file kept with its turn (sys_uploads: the Files page, the conversation).
It never runs as Aurora's own page: only under /v1/preview/, with a token valid 10 minutes that the logged-in
WebUI asks for, in a sandbox (opaque origin: no cookie, no access to Aurora's API) and with no network at all
(connect-src 'none'; no external script, style, font or image: everything inline). The download of the file
stays a download (sys_uploads never serves HTML inline).
"""
from __future__ import annotations

import html as htmllib
import re
import secrets
import time
from pathlib import Path

from . import sys_config, sys_uploads

MAX_BYTES = 300_000
TTL_S = 600
PREFIX = "art-"                       # tokens of artifacts in the /v1/preview/ space (projects use theirs)
CSP = ("sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'; form-action 'none'; "
       "base-uri 'none'; frame-ancestors 'self'")
UPLOAD_URL = re.compile(r"/v1/aurora/uploads/([0-9a-f]{16})")
_tokens: dict[str, tuple[Path, float]] = {}


def create(cfg: sys_config.Config, run_id: str, title: str, page: str) -> dict:
    """Keep a page Aurora wrote; returns the file as the chat shows it ({name, url, mime})."""
    page = str(page or "").strip()
    if "<" not in page:
        raise ValueError("an artifact is an HTML page (inline CSS and JavaScript, no external files)")
    if len(page.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"the page is larger than {MAX_BYTES // 1000} KB")
    title = (str(title or "").strip() or "artefatto")[:80]
    if not re.search(r"<html|<body|<!doctype", page, re.I):          # a fragment: given a page around it
        page = (f"<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-"
                f"width,initial-scale=1\"><title>{htmllib.escape(title)}</title></head><body>{page}</body></html>")
    slug = re.sub(r"[^\w-]+", "-", title.lower()).strip("-")[:40] or "artefatto"
    name = f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}.html"
    item = sys_uploads.public(sys_uploads.save(cfg, run_id, name, "text/html", page.encode("utf-8"), role="assistant"))
    return {"name": name, "url": item["url"], "mime": "text/html"}


def open_token(cfg: sys_config.Config, url: str) -> str:
    """A short-lived token to run one of Aurora's artifacts in the sandbox; only pages Aurora made."""
    m = UPLOAD_URL.fullmatch(str(url or ""))
    found = sys_uploads.get(cfg, m.group(1)) if m else None
    if not found or found[1].get("mime") != "text/html" or found[1].get("role") != "assistant":
        raise FileNotFoundError("not an artifact of Aurora's")
    now = time.time()
    for t in [t for t, (_, exp) in _tokens.items() if exp < now]:
        _tokens.pop(t, None)
    tok = PREFIX + secrets.token_urlsafe(24)
    _tokens[tok] = (found[0], now + TTL_S)
    return tok


def page(token: str) -> bytes:
    path, exp = _tokens.get(token, (None, 0.0))
    if path is None or exp < time.time():
        raise PermissionError("artifact expired")
    return path.read_bytes()
