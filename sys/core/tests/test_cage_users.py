# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Multi-user: a plugin in the cage of one user cannot read another user's data, the users store, or its own user's
whole .env; the admin's plugins still see the owner's own folders of usr/ (his papers). A real bubblewrap cage."""
import json
import shutil
import subprocess

import pytest

from aurora import plg_sandbox, sys_user_config as U, sys_users_layout as L
from aurora.sys_users import Users


def _cage_works() -> bool:
    """bubblewrap installed and able to make a namespace here: not inside another cage (the self plugin's tests, C144)."""
    return bool(shutil.which("bwrap")) and subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                          capture_output=True).returncode == 0


@pytest.mark.skipif(not _cage_works(), reason="bubblewrap missing, or inside a cage (no nested namespaces)")
def test_each_user_s_plugins_see_only_their_own_things(cfg, tmp_path):
    st = cfg.path("AURORA_STATUS_DIR")
    st.mkdir(parents=True, exist_ok=True)
    (st / L.STATE).write_text(json.dumps({"layout": 1, "admin": "boss"}))
    users = Users(cfg)
    users.add("boss", "admin", "a long password")
    users.add("guest", "user", "another long password")
    usr = cfg.root / "usr"
    for who in ("boss", "guest"):
        (usr / who / "notes").mkdir(parents=True)
        (usr / who / "notes" / "secret.md").write_text(f"{who}'s secret")
        (usr / who / ".env").write_text(f"AURORA_TMDB_TOKEN={who}-token\n")
        mem = L.home(cfg, L.BY_NAME["memory"], who)
        mem.mkdir(parents=True)
        (mem / "turns.db").write_text(f"{who}'s turns")
    (usr / "documents" / "papers").mkdir(parents=True)
    (usr / "documents" / "papers" / "patent.pdf").write_text("the owner's patent")
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    env = tmp_path / "filtered.env"
    env.write_text("X=1\n")
    probe = ("import pathlib, json; r=pathlib.Path(%r); out={}\n"
             "for p in ['usr/boss/notes/secret.md','usr/guest/notes/secret.md','usr/documents/papers/patent.pdf',"
             "'usr/boss/.env','usr/guest/.env','sys/status/users.db']:\n"
             "    f=r/p\n    out[p]=f.read_text(errors='replace')[:40] if f.is_file() else None\n"
             "for who in ('boss','guest'):\n"
             "    d=r/'sys/vault/memory/users'/who\n    out['mem/'+who]=sorted(x.name for x in d.iterdir()) if d.is_dir() else None\n"
             "print(json.dumps(out))") % str(cfg.root)
    seen = {}
    for who in ("boss", "guest"):
        cmd = plg_sandbox.wrap(["python3", "-c", probe], plugin, {}, env, U.for_user(cfg, who))
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[-1500:]
        seen[who] = json.loads(r.stdout)
    b, g = seen["boss"], seen["guest"]
    assert b["usr/boss/notes/secret.md"] == "boss's secret" and g["usr/guest/notes/secret.md"] == "guest's secret"
    assert b["usr/guest/notes/secret.md"] is None and g["usr/boss/notes/secret.md"] is None     # never the other's
    assert b["mem/guest"] == [] and g["mem/boss"] == [] and b["mem/boss"] == ["turns.db"]
    assert b["usr/documents/papers/patent.pdf"] == "the owner's patent"                         # the admin's plugins
    assert g["usr/documents/papers/patent.pdf"] is None                                          # not a user's
    for s in (b, g):
        assert not s["sys/status/users.db"] and not s["usr/boss/.env"] and not s["usr/guest/.env"]
