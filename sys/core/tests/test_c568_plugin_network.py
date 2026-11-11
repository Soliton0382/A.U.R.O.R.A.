# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C568 (area audit, 10 Nov): a plugin whose manifest says nothing about the network has none — it used to share the
host's, Aurora's API on 127.0.0.1 included. The plugins that need it say so, and the real cage keeps the others out."""
import json
import re
import shutil
import socket
import subprocess
import threading
from pathlib import Path

import pytest

from aurora import plg_sandbox

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
NETWORK_LIBRARY = re.compile(r"^\s*(?:import|from)\s+(httpx|requests|aiohttp|imaplib|smtplib|websockets)\b", re.M)


def _cage_works() -> bool:
    return bool(shutil.which("bwrap")) and subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                          capture_output=True).returncode == 0


def _wrapped(cfg, tmp_path, manifest, cmd=("python3",)):
    env = tmp_path / "filtered.env"
    env.write_text("X=1\n")
    plugin = tmp_path / "plugin"
    plugin.mkdir(exist_ok=True)
    return plg_sandbox.wrap(list(cmd), plugin, manifest, env, cfg)


@pytest.mark.parametrize("manifest", [{}, {"sandbox": {}}, {"sandbox": {"write": []}},
                                      {"sandbox": {"network": False}}, {"sandbox": {"network": "yes"}},
                                      {"sandbox": {"network": 1}}])
def test_nothing_said_is_no_network(cfg, tmp_path, manifest):
    assert "--unshare-net" in _wrapped(cfg, tmp_path, manifest)


def test_the_host_s_network_only_when_asked(cfg, tmp_path):
    args = _wrapped(cfg, tmp_path, {"sandbox": {"network": True}})
    assert "--unshare-net" not in args and "HTTPS_PROXY" not in args
    forged = _wrapped(cfg, tmp_path, {"name": "sly", "forged": {"request": "r"}})
    assert "--unshare-net" in forged and "HTTPS_PROXY" not in forged      # a forged one that asks nothing: none either


def test_a_plugin_that_brings_a_network_library_says_what_it_needs():
    """Whoever writes a plugin decides: with the default at «none», a connector that forgot would only fail at its
    first call. The house's own plugins (local_*, ha_*) are theirs to declare."""
    silent = []
    for f in sorted(PLUGINS.glob("*/plugin.json")):
        if f.parent.name.startswith(("local_", "ha_")):
            continue
        m = json.loads(f.read_text(encoding="utf-8"))
        code = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in f.parent.glob("*.py"))
        if NETWORK_LIBRARY.search(code) and "network" not in (m.get("sandbox") or {}):
            silent.append(f.parent.name)
    assert silent == []


def test_the_connectors_of_this_repository_still_reach_their_services():
    need = ("calendar", "discord", "email", "github", "homeassistant", "linkcheck", "news", "projects", "security",
            "senses", "sky", "telegram", "weather", "web")
    for name in need:
        m = json.loads((PLUGINS / name / "plugin.json").read_text(encoding="utf-8"))
        assert m["sandbox"]["network"] is True, name


@pytest.mark.skipif(not _cage_works(), reason="bubblewrap missing, or inside a cage (no nested namespaces)")
def test_in_the_real_cage_a_silent_plugin_reaches_no_port_of_this_machine(cfg, tmp_path):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)

    def run():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            c.sendall(b"api")
            c.close()
    threading.Thread(target=run, daemon=True).start()
    probe = ("import socket\n"
             "try:\n    print(socket.create_connection(('127.0.0.1', %d), timeout=3).recv(10).decode())\n"
             "except OSError:\n    print('refused')") % srv.getsockname()[1]
    seen = {}
    for label, manifest in (("silent", {}), ("asked", {"sandbox": {"network": True}})):
        r = subprocess.run(_wrapped(cfg, tmp_path, manifest, ("python3", "-c", probe)), capture_output=True, text=True,
                           timeout=60)
        assert r.returncode == 0, r.stderr[-1500:]
        seen[label] = r.stdout.strip().splitlines()[-1]
    srv.close()
    assert seen == {"silent": "refused", "asked": "api"}
