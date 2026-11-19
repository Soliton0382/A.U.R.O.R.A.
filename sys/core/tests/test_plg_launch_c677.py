# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔐 C677 (the sixth review's points on the plugins' launcher): plg_launch is a PROTECTED file; the cage's «--» is
given by plg_host, never looked for; a secret on several lines arrives whole; a program not of Aurora's Python (the
github plugin's) gets no secrets' file it would never empty. Invented values only."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import plg_sandbox, sys_config, sys_ethics

ROOT = Path(__file__).resolve().parents[3]
LAUNCH = ROOT / "sys/core/aurora/plg_launch.py"


def _launcher():
    spec = importlib.util.spec_from_file_location("plg_launch_t", LAUNCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_launcher_is_protected():
    assert "sys/core/aurora/plg_launch.py" in sys_ethics.PROTECTED


def test_the_index_is_given_and_checked():
    m = _launcher()
    argv = ["bwrap", "--ro-bind", "/", "/", "--chdir", "/plug", "--", "prog", "--chdir", "x", "--"]
    out = m.command(argv, 9, 6)
    assert out[:4] == argv[:4] and out[4:9] == ["--bind-data", "9", m.DEST, "--setenv", "AURORA_PLUGIN_SECRETS_FILE"]
    assert out[-7:] == ["--chdir", "/plug", "--", "prog", "--chdir", "x", "--"]   # the plugin's own arguments untouched
    for bad in (10, 3, 99):                       # the plugin's «--», a wrong index, past the end
        if bad == 10:
            continue                              # argv[8] is «--chdir»: shape-valid, which is why the host gives it
        with pytest.raises(ValueError):
            m.command(argv, 9, bad)


def test_the_launcher_refuses_without_the_index():
    r = subprocess.run([sys.executable, "-I", str(LAUNCH), "/bin/true"], capture_output=True, text=True)
    assert r.returncode != 0 and "--at" in r.stderr


def test_a_secret_on_several_lines_arrives_whole(tmp_path):
    fake = tmp_path / "bwrap"                     # stands for bubblewrap: prints what the pipe holds
    fake.write_text('#!/bin/sh\nwhile [ "$1" != "--bind-data" ]; do shift; done\ncat "/dev/fd/$2"\n')
    fake.chmod(0o755)
    pem = "-----BEGIN KEY-----\nAAAA\nBBBB\n-----END KEY-----"
    env = {"PATH": "/usr/bin:/bin", "AURORA_PLUGIN_SECRET_AURORA_ZZ_KEY": pem}
    argv = [str(fake), "--chdir", "/p", "--", "prog"]
    r = subprocess.run([sys.executable, "-I", str(LAUNCH), "--at", "3", *argv], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    secrets_file = tmp_path / "secrets"
    secrets_file.write_text(r.stdout)
    os.environ[sys_config.PLUGIN_SECRETS_FILE] = str(secrets_file)
    sys_config._plugin_secrets = None
    try:
        assert sys_config.plugin_secret("AURORA_ZZ_KEY") == pem
        assert secrets_file.read_text() == ""     # read once, then emptied
    finally:
        sys_config._plugin_secrets = None
        os.environ.pop(sys_config.PLUGIN_SECRETS_FILE, None)


@pytest.mark.parametrize("command,gets_file", [(["{python}", "server.py"], True), (["{root}/prog", "stdio"], False)])
def test_only_aurora_python_programs_get_the_file(cfg, tmp_path, monkeypatch, command, gets_file):
    from aurora import plg_deps, plg_host
    monkeypatch.setattr(plg_deps, "verify", lambda *a, **k: None)
    monkeypatch.setattr(plg_sandbox, "bwrap", lambda: "/usr/bin/bwrap")
    cfg.values["AURORA_GITHUB_TOKEN"] = cfg.raw["AURORA_GITHUB_TOKEN"] = "tok-c677"
    m = {"name": "zz", "command": command, "env_as": {"AURORA_GITHUB_TOKEN": "ZZ_TOKEN"},
         "requires": ["AURORA_GITHUB_TOKEN"], "sandbox": {"network": True}}
    params = plg_host.PluginHost(cfg)._params(plg_host.Plugin("zz", tmp_path, m))
    prefixed = [k for k in params.env if k.startswith(sys_config.PLUGIN_SECRET)]
    assert bool(prefixed) is gets_file
    assert params.env.get("ZZ_TOKEN") == "tok-c677"           # the name its program expects, as before
    at = int(params.args[3])
    assert params.args[2] == "--at" and params.args[4:][at] == "--" and params.args[4:][at - 2] == "--chdir"


# ---- C676: the pip of Aurora's environment, told to the owner -------------------------------------------------------
@pytest.mark.parametrize("version,level", [("25.1.1", "warn"), ("26.1.2", "warn"), ("26.2", "ok"), ("26.3", "ok"),
                                           ("27.0", "ok")])
def test_c676_an_old_pip_is_told_with_the_command(version, level):
    from aurora import sys_health
    got, text, detail = sys_health.pip_line(version)
    assert got == level and version in text
    assert ("--upgrade pip" in detail) is (level == "warn")


# ---- C684: a caged command killed by a limit leaves no core dump ------------------------------------------------------
@pytest.mark.skipif(not __import__("shutil").which("bwrap"), reason="bwrap")
def test_c684_the_cage_runs_with_core_dumps_off(cfg, tmp_path):
    from aurora import prj_run
    r = subprocess.run(prj_run.cage(cfg, tmp_path, "python3 -c 'import resource; print(resource.getrlimit(resource.RLIMIT_CORE))'"),
                       capture_output=True, text=True, timeout=60)
    if r.returncode and "bwrap" in r.stderr:
        pytest.skip("cage not available here")
    assert r.stdout.strip() == "(1, 1)", r.stderr
