# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The security review of 28 Oct (C420–C429), the pieces that are not routes: the cages hide /run (docker answered from
inside), a project's .git and .venv are read only in it, the plugins' cage hides the machine's keys and gives a
minimal /dev, the agent's sandbox tests run caged, the host's git runs no fsmonitor and no hook, a preview token keeps
its folder, an address typed by a user never reaches this machine, the plugins' logs lose their tokens, a new password
logs the other sessions out."""
import shutil
import subprocess
import sys

import pytest

from aurora import net_public, plg_sandbox, prj_browse, prj_run, sys_tests
from aurora.plg_host import _redact
from aurora.sys_devices import Devices

LINUX = pytest.mark.skipif(sys.platform != "linux" or not shutil.which("bwrap"), reason="bubblewrap")


def _pairs(args, flag):
    return [args[i + 1] for i, a in enumerate(args) if a == flag]


def test_the_project_cage_hides_run_and_keeps_git_read_only(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".venv").mkdir()
    args = prj_run.cage(None, tmp_path, "true")
    assert "/run" in _pairs(args, "--tmpfs")
    assert str(tmp_path / ".git") in _pairs(args, "--ro-bind") and str(tmp_path / ".venv") in _pairs(args, "--ro-bind")
    assert args.index("--bind") < args.index(str(tmp_path / ".git"))                 # read only over the writable bind


@LINUX
def test_inside_the_cage_no_host_socket_and_git_not_writable(tmp_path):
    (tmp_path / ".git").mkdir()
    r = subprocess.run(prj_run.cage(None, tmp_path, "ls /run | wc -l; echo x > .git/config 2>/dev/null && echo WROTE; "
                                    "echo y > ok.txt && echo OK"), capture_output=True, text=True, timeout=30)
    if r.returncode or not r.stdout.strip():             # a machine whose kernel refuses the cage (CI runners): nothing to see
        pytest.skip(f"the cage does not start here: {r.stderr.strip()[:80]}")
    out = r.stdout.split()
    assert out[0] == "0" and "WROTE" not in out and "OK" in out


def test_the_plugin_cage_hides_run_keys_and_devices(cfg, tmp_path):
    status = cfg.path("AURORA_STATUS_DIR")
    for d in ("keys", "cloudflare", "cloud_accounts", "claude_code"):
        (status / d).mkdir(parents=True, exist_ok=True)
    (status / "camera_keys.json").write_text("{}")
    env = tmp_path / "env"
    env.write_text("")
    args = plg_sandbox.wrap(["python3"], tmp_path, {"sandbox": {}}, env, cfg)
    hidden = _pairs(args, "--tmpfs")
    assert "/run" in hidden and all(str(status / d) in hidden for d in ("keys", "cloudflare", "cloud_accounts", "claude_code"))
    assert ["/dev/null", str(status / "camera_keys.json")] == args[args.index(str(status / "camera_keys.json")) - 1:
                                                                 args.index(str(status / "camera_keys.json")) + 1]
    assert "--dev-bind" not in args and "--dev" in args                               # a minimal /dev by default
    assert "--dev-bind" in plg_sandbox.wrap(["python3"], tmp_path, {"sandbox": {"devices": True}}, env, cfg)


def test_the_agent_s_sandbox_tests_run_caged(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(sys_tests.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or subprocess.CompletedProcess(cmd, 0, "1 passed", ""))
    sys_tests.run_suite(tmp_path, caged=True)
    assert ran[0][0] == "bwrap" and "/run" in _pairs(ran[0], "--tmpfs") and "pytest" in ran[0][-1]
    sys_tests.run_suite(tmp_path)                                                    # the live code: as before
    assert ran[1][0] == sys.executable


def test_the_host_s_git_runs_no_fsmonitor_and_no_hook(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "core.fsmonitor", f"touch {tmp_path / 'RAN'}; false"], check=True)
    prj_browse._git(tmp_path, "status", "--porcelain")
    assert not (tmp_path / "RAN").exists()


def test_a_preview_keeps_its_folder(cfg, monkeypatch, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d, word in ((a, "mine"), (b, "theirs")):
        d.mkdir()
        (d / "index.html").write_text(word)
    monkeypatch.setattr(prj_browse, "project", lambda cfg, name: a)
    tok = prj_browse.preview_token(cfg, "x")
    monkeypatch.setattr(prj_browse, "project", lambda cfg, name: b)                  # another user's view of «x»
    assert prj_browse.preview_file(cfg, tok, "")[0] == b"mine"


def test_an_address_typed_never_reaches_this_machine():
    for url in ("http://127.0.0.1:9711/slots", "http://localhost:9700/", "http://[::1]/", "http://169.254.169.254/",
                "http://0.0.0.0/", "file:///etc/passwd"):
        with pytest.raises(net_public.Refused):
            net_public.check(url, lan=True)
    with pytest.raises(net_public.Refused):
        net_public.check("http://192.168.1.10/", lan=False)
    assert net_public.check("http://192.168.1.10/", lan=True) == "192.168.1.10"


def test_the_plugins_logs_lose_their_tokens():
    assert _redact("GET /me?access_token=EAAJabc123&x=1") == "GET /me?access_token=<redacted>&x=1"
    assert _redact("Authorization: Bearer sk-abc") == "Authorization: Bearer <redacted>"
    assert _redact("nothing secret here") == "nothing secret here"


def test_a_new_password_logs_the_other_sessions_out(cfg):
    d = Devices(cfg)
    _, keep = d.register("phone", "ua", user="anna")
    d.register("laptop", "ua", user="anna")
    d.register("other", "ua", user="bruno")
    assert d.revoke_user("anna", keep=keep["id"]) == 1
    assert sorted(x["name"] for x in d.list()) == ["other", "phone"]


def test_no_stray_folder_under_usr_with_the_machine_s_configuration(cfg, tmp_path, monkeypatch):
    """Owner, 28 Oct: nine empty folders straight under usr/ (music, notes…), made when the plugins' tools were listed
    with the machine's configuration: a plugin's writable folder is made only when it is a user's."""
    from aurora import sys_users_layout as L
    monkeypatch.setattr(L, "migrated", lambda cfg: {"layout": 1, "admin": "boss"})
    music = cfg.path("AURORA_MUSIC_DIR")                    # usr/music with no user: nobody's folder
    assert music.parent == L.usr(cfg) and not music.exists()
    env = tmp_path / "env"
    env.write_text("")
    args = plg_sandbox.wrap(["python3"], tmp_path, {"sandbox": {"write": ["AURORA_MUSIC_DIR"]}}, env, cfg)
    assert not music.exists() and str(music) not in args
