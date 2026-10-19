# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""U3/U5: user B never sees user A's things, through every route that lists or serves them (api_crossing.py, its
own process); and every route but the public few asks who is calling."""
import json
import subprocess

import os
# Windows starts no socket without SYSTEMROOT (WinError 10106 on a real Windows, 9 Oct); nothing elsewhere
WINDOWS = {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_guest_never_sees_boss_s_things(cfg):
    r = subprocess.run([sys.executable, str(HERE / "api_crossing.py"), str(cfg.root)], capture_output=True, text=True,
                       timeout=180, env={**WINDOWS, "PATH": "/usr/bin:/bin", "AURORA_ENV_FILE": str(cfg.env_file)})
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    boss, guest = out["boss"], out["guest"]
    assert boss["me"] == "boss" and guest["me"] == "guest"
    for k in ("activity", "settings_tmdb", "routines", "approvals", "history", "documents", "runs", "calendar",
              "calendar_export"):
        assert boss[k] is True, f"boss does not see their own {k}"
        assert guest[k] is False, f"guest sees boss's {k}"
    assert boss["uploads"] == 1 and guest["uploads"] == 0
    assert boss["upload_file"] == 200 and guest["upload_file"] == 404
    assert boss["document_file"] == 200 and guest["document_file"] == 404
    assert boss["run_events"] == 200 and guest["run_events"] == 404
    assert boss["calendar_item"] == 200 and guest["calendar_item"] == 404
    assert boss["devices"] == ["boss phone", "guest phone"] and guest["devices"] == ["guest phone"]
    assert boss["users_page"] == 200 and guest["users_page"] == 403
    assert boss["machine_setting"] == 200 and guest["machine_setting"] == 403
    assert guest["revoke_boss_device"] == 404
    assert boss["accounts_list"] is True and guest["accounts_list"] is False           # 106: a user's key is theirs
    assert guest["account_remove"] == 403 and guest["account_shared"] == 403
    assert guest["account_policy"] == 403 and guest["service_add"] == 403
    assert boss["welcomed"] is True and guest["welcomed"] is False                     # 107: once per person
    assert boss["prefs"] == {"style": "essenziale", "theme": "foresta", "pins": ["dreams", "models"]} and guest["prefs"] == {}
    assert guest["prefs_bad"] == 422 and guest["theme_bad"] == 422
    assert guest["tiles"] == {"order": ["sky", "agenda", "page:ideas"], "off": ["news"]} and guest["tiles_bad"] == 422
    assert boss["health"] == ["warn", 1, 1] and guest["health"] == ["warn", 0, 0]          # the machine's details: the admin's
    assert guest["cloud_set"] == 403 and boss["cloud_set"] == {"guest": 200000} and boss["cloud_self"] == 422
    assert boss["cloud_list"] == {"boss": 0, "guest": 200000}
    assert boss["usage"][0] and set(boss["usage"][1]) >= {"", "boss", "guest"} and boss["usage_pick"] == 1
    assert guest["usage"] == [False, ["guest"], 1] and guest["usage_pick"] == 1          # their own, not boss's
    assert guest["oauth_start"] == 409 and guest["oauth_finish"] == 403 and boss["oauth_no_keys"] == 409   # his own keys; not boss's sign-in
    assert boss["oauth_scope"] == "user.info.basic,video.publish"                       # no scope the plugin does not use
    assert boss["oauth_forged"] == 409 and boss["oauth_again"] == 409                   # a state Aurora gave, once
    assert boss["oauth_finish"]["days"] == 365 and boss["oauth_saved"] is True
    assert guest["oauth_saved"] is False and guest["oauth_machine"] is False           # boss's token stays boss's


def test_the_same_holds_when_aurora_lives_behind_a_symlink(tmp_path):
    """Found on a real Mac (8 Oct: /var is a symlink there): a root behind a symlink put boss's folders elsewhere — he
    lost his own history, and his documents went to usr/documents/users/boss. Same check, the root a symlink."""
    import os
    from conftest import write_env
    (tmp_path / "real").mkdir()
    root = tmp_path / "link"
    os.symlink(tmp_path / "real", root)
    env = write_env(root, AURORA_ROOT=str(root))
    r = subprocess.run([sys.executable, str(HERE / "api_crossing.py"), str(root)], capture_output=True, text=True,
                       timeout=180, env={**WINDOWS, "PATH": "/usr/bin:/bin", "AURORA_ENV_FILE": str(env)})
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    for k in ("activity", "routines", "approvals", "history", "documents", "runs", "calendar"):
        assert out["boss"][k] is True and out["guest"][k] is False, k


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
                       env={**WINDOWS, "PATH": "/usr/bin:/bin", "AURORA_ENV_FILE": str(cfg.env_file)})
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.split("\n")[:-1] == ["GET /", "GET /health", "GET /manifest.webmanifest", "GET /sw.js",
                                         "GET /v1/preview/{token}/{path:path}", "POST /v1/aurora/devices",
                                         "POST /v1/aurora/login", "POST /v1/aurora/push-ack"]   # the push's id is its proof
