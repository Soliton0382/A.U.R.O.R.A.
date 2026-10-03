# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""U3/U5: user B never sees user A's things, through every route that lists or serves them (api_crossing.py, its
own process); and every route but the public few asks who is calling."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_guest_never_sees_boss_s_things(cfg):
    r = subprocess.run([sys.executable, str(HERE / "api_crossing.py"), str(cfg.root)], capture_output=True, text=True,
                       timeout=180, env={"PATH": "/usr/bin:/bin", "AURORA_ENV_FILE": str(cfg.env_file)})
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    boss, guest = out["boss"], out["guest"]
    assert boss["me"] == "boss" and guest["me"] == "guest"
    for k in ("activity", "settings_tmdb", "routines", "approvals", "history", "documents", "runs"):
        assert boss[k] is True, f"boss does not see their own {k}"
        assert guest[k] is False, f"guest sees boss's {k}"
    assert boss["uploads"] == 1 and guest["uploads"] == 0
    assert boss["upload_file"] == 200 and guest["upload_file"] == 404
    assert boss["document_file"] == 200 and guest["document_file"] == 404
    assert boss["run_events"] == 200 and guest["run_events"] == 404
    assert boss["devices"] == ["boss phone", "guest phone"] and guest["devices"] == ["guest phone"]
    assert boss["users_page"] == 200 and guest["users_page"] == 403
    assert boss["machine_setting"] == 200 and guest["machine_setting"] == 403
    assert guest["revoke_boss_device"] == 404


def test_only_the_public_routes_go_without_authentication(cfg):
    code = f"""
import sys; sys.path.insert(0, "."); sys.path.insert(0, "script")
from aurora import sys_config as C
C._cached = C.load(__import__("pathlib").Path({str(cfg.env_file)!r}), check_root=False)   # a test installation
import svc_api
from fastapi.routing import APIRoute
def walk(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        else:
            sub = getattr(getattr(r, "original_router", None), "routes", None)
            yield from walk(sub or [])
def deps(d):
    for x in d.dependencies:
        yield getattr(x.call, "__name__", "")
        yield from deps(x)
print("\\n".join(sorted(f"{{min(r.methods)}} {{r.path}}" for r in walk(svc_api.app.routes) if not set(deps(r.dependant)) & {{"auth", "admin_only"}})))
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=HERE.parent,
                       env={"PATH": "/usr/bin:/bin", "AURORA_ENV_FILE": str(cfg.env_file)})
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.split("\n")[:-1] == ["GET /", "GET /health", "GET /manifest.webmanifest", "GET /sw.js",
                                         "GET /v1/preview/{token}/{path:path}", "POST /v1/aurora/devices",
                                         "POST /v1/aurora/login"]
