# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Run by test_c594_webui_app.py in its own process (the API keeps state in its modules): the headers the API itself
puts on the WebUI's page and files, with no Caddy in front. argv: the root. Prints one JSON line."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "script"))

from aurora import sys_config as C  # noqa: E402

C._cached = C._view(C.load(Path(sys.argv[1]) / ".env", check_root=False))

import svc_api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(svc_api.app, base_url="https://testserver")
out = {}
for path in ("/", "/static/js/dom.js", "/sw.js"):
    r = c.get(path)
    out[path] = {"status": r.status_code, "csp": r.headers.get("content-security-policy", ""),
                 "nosniff": r.headers.get("x-content-type-options", "")}
print(json.dumps(out))
