# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C725: in the Android app the viewer's ⬇️ did nothing — the WebView hands a blob: address to the download listener,
which only takes the server's own https addresses. In the app the upload's real address is clicked with ?download=1
and the server answers it as an attachment, so the app's download manager saves it (with the page's cookie)."""
from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]


def test_the_server_sends_an_attachment_when_asked():
    src = (CORE / "aurora/api/uploads.py").read_text()
    assert 'getattr(request, "query_params", {}).get("download") != "1"' in src
    assert src.count("'inline' if show else 'attachment'") == 1          # sealed files
    assert src.count('"inline" if show else "attachment"') == 1          # plain files
    assert "'inline' if inline else" not in src and '"inline" if inline else' not in src


def test_the_viewer_uses_the_real_address_only_inside_the_app_and_only_for_uploads():
    js = (CORE / "webui/js/viewer.js").read_text()
    assert "window.AuroraApp" in js and "download=1" in js
    pat = re.search(r'const direct = inApp && /(.+)/\.test\(url\);', js).group(1).replace("\\/", "/")
    assert re.search(pat, "/v1/aurora/uploads/0123456789abcdef")
    assert re.search(pat, "https://x.test/v1/aurora/uploads/0123456789abcdef?a=1")
    assert not re.search(pat, "/v1/aurora/preview/page?url=x")          # other files keep the blob way
    assert "URL.createObjectURL(blob)" in js                              # the browser and the PWA: unchanged


def test_an_image_asked_with_download_comes_as_an_attachment(cfg, monkeypatch):
    import importlib
    import sys
    from aurora import sys_config, sys_uploads
    monkeypatch.setattr(sys_config, "_cached", cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):
        importlib.import_module(f"aurora.api.{name}")
    from aurora.api import uploads

    class Asked:
        def __init__(self, q): self.headers, self.query_params = {}, q
    item = sys_uploads.save(cfg, "run-1", "ritratto.png", "image/png", b"\x89PNG invented", role="assistant")
    shown = uploads.upload_get(item["id"], Asked({}))
    saved = uploads.upload_get(item["id"], Asked({"download": "1"}))
    assert shown.headers["content-disposition"].startswith("inline")
    assert saved.headers["content-disposition"].startswith("attachment")
    assert saved.media_type == "image/png"                                  # still a picture, only saved
