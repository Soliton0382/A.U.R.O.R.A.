# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧩 The owner's MCP servers (owner, 10 Nov: «una sezione dedita all'integrazione dei server mcp così che aurora possa
usarli nella chat»; «http e https… non limitiamoci»): the manifest built from the form and checked, the cage reading
only the places named, a real server outside Aurora answering from inside the cage, the answers that stay out of her
memory."""
import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

from aurora import plg_contract, plg_host, plg_mcp, plg_sandbox

FORM = {"name": "archive", "description": "Searches the archive of public documents, with sources.",
        "read_tools": ["find"], "memory": False}


def test_a_local_or_remote_server_becomes_a_manifest_that_keeps_the_contract(cfg, tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("elsewhere")      # outside Aurora's folder (C591: never a place inside it)
    local = plg_mcp.manifest(cfg, {**FORM, "command": [sys.executable, "-I", "server.py"], "read": [str(tmp_path)]})
    assert local["kind"] == "mcp" and local["effects"] == {"find": "read", "*": "external"} and local["memory"] is False
    assert local["sandbox"] == {"read": [str(tmp_path)], "network": False}
    for url in ("https://mcp.example.org/mcp", "http://10.0.0.5:8000/mcp"):          # both, as the owner asked
        lan = {"lan": True} if "10.0.0.5" in url else {}                             # in the house: said (C571)
        remote = plg_mcp.manifest(cfg, {**FORM, "url": url, **lan})
        assert remote["url"] == url and "command" not in remote and remote.get("lan", False) is bool(lan)
        assert remote["from_network"] == ["*"]                     # its answers through the honeypot (audit, 10 Nov)
        assert plg_contract.check(remote, "local_archive") == []
    assert plg_contract.check(local, "local_archive") == [] and local["name"] == "local_archive"   # C546: never published


@pytest.mark.parametrize("bad, why", [
    ({"name": "Bad Name"}, "name"),
    ({"description": "short"}, "description"),
    ({"url": "ftp://x.org/m"}, "address"),
    ({"url": "https://x.org/m", "command": ["/bin/true"]}, "not both"),
    ({"command": ["server.py"]}, "absolute"),
    ({"command": ["/bin/true"], "network": True}, "network"),
    ({"command": ["/bin/true"], "network": "proxy"}, "hosts"),
    ({"command": ["/bin/true"], "effect": "delete"}, "effect"),
    ({"command": ["/bin/true"], "read": ["/proc"]}, "system"),            # the host's /proc: every process (audit)
    ({"command": ["/bin/true"], "read": ["/run"]}, "system"),
])
def test_a_wrong_form_is_told_why(cfg, bad, why):
    body = {**FORM, **bad}
    if "url" not in body and "command" not in body:
        body["command"] = ["/bin/true"]
    with pytest.raises(ValueError, match=why):
        plg_mcp.manifest(cfg, body)


def test_the_cage_reads_only_the_places_named_never_the_home_or_a_hidden_one(cfg, tmp_path, tmp_path_factory):
    home = Path(os.environ.get("HOME") or Path.home()).resolve()
    for place, why in ((home, "home"), (home.parent, "home"), (Path("/"), "root"), (home / ".ssh", "hidden"),
                       (cfg.path("AURORA_STATUS_DIR"), "state"), (Path("/opt/aurora-test-missing"), "exist")):
        with pytest.raises(ValueError, match=why):
            plg_sandbox.read_paths({"kind": "mcp", "sandbox": {"read": [str(place)]}}, cfg)
    with pytest.raises(ValueError, match="outside Aurora|own state"):                         # C591: her own folder
        plg_sandbox.read_paths({"kind": "mcp", "sandbox": {"read": [str(tmp_path)]}}, cfg)
    out = tmp_path_factory.mktemp("elsewhere")
    assert plg_sandbox.read_paths({"kind": "mcp", "sandbox": {"read": [str(out)]}}, cfg) == [out.resolve()]
    assert plg_sandbox.read_paths({"forged": {"at": 1}, "sandbox": {"read": [str(out)]}}, cfg) == []   # never forged
    assert "sandbox.read: only an MCP server" in " ".join(
        plg_contract.check({"name": "x1", "version": "1", "kind": "tool", "description": {"it": "x", "en": "x"},
                            "command": ["a"], "requires": [], "effects": {}, "sandbox": {"read": ["/opt"]}}))


def test_saved_whole_never_over_another_plugin_and_removed_only_if_it_is_one(cfg, tmp_path):
    cfg.values["AURORA_PLUGINS_DIR"] = str(tmp_path / "plugins")
    other = tmp_path / "plugins" / "local_archive"
    other.mkdir(parents=True)
    (other / "plugin.json").write_text(json.dumps({"name": "local_archive", "kind": "tool"}))
    m = plg_mcp.manifest(cfg, {**FORM, "url": "https://mcp.example.org/mcp"})
    with pytest.raises(ValueError, match="another plugin"):
        plg_mcp.save(cfg, m)
    assert plg_mcp.remove(cfg, "local_archive") is False and other.exists()
    (other / "plugin.json").unlink()
    other.rmdir()
    plg_mcp.save(cfg, m)
    assert json.loads((other / "plugin.json").read_text())["url"] == "https://mcp.example.org/mcp"
    assert plg_mcp.remove(cfg, "local_archive") is True and not other.exists()


SERVER = textwrap.dedent('''
    from pathlib import Path
    from mcp.server.mcpserver import MCPServer
    server = MCPServer("demo")

    @server.tool()
    def find(words: str) -> str:
        """Echo, from a server living outside Aurora."""
        return "found: " + words

    @server.tool()
    def peek(path: str) -> str:
        """Whether a file can be read from inside the cage."""
        try:
            return "READ " + Path(path).read_text()[:20]
        except OSError as e:
            return "BLOCKED " + type(e).__name__

    server.run("stdio")
''')


@pytest.mark.skipif(not plg_sandbox.available(), reason="bubblewrap missing")
def test_a_real_server_outside_aurora_answers_from_its_cage_and_sees_nothing_else(cfg, tmp_path, tmp_path_factory):
    srv = tmp_path_factory.mktemp("outside") / "elsewhere"
    srv.mkdir()
    (srv / "server.py").write_text(SERVER)
    secret = Path(os.environ.get("HOME") or Path.home()) / ".bashrc"
    m = plg_mcp.manifest(cfg, {**FORM, "command": [sys.executable, "-I", str(srv / "server.py")], "read": [str(srv)]})
    m["command"][0] = os.path.normpath(sys.executable)            # Aurora's own Python (bound into the cage); pytest may
    #                                                                 be started through «sys/core/../../.venv», not a path there
    folder = tmp_path / "plugins" / "local_archive"
    folder.mkdir(parents=True)
    cfg.values["AURORA_PLUGIN_SANDBOX"] = True
    host = plg_host.PluginHost(cfg)
    p = plg_host.Plugin("local_archive", folder, m)
    tools = {t["name"] for t in host._tools(p, 1.0)}
    assert tools == {"find", "peek"} and p.effect("find") == "read" and p.effect("peek") == "external"
    assert host.call.__name__                                       # the same call path as every plugin
    out = host._run(host._session(p, lambda s: s.call_tool("find", {"words": "manifest"})))
    assert out.content[0].text == "found: manifest"
    if secret.exists():
        seen = host._run(host._session(p, lambda s: s.call_tool("peek", {"path": str(secret)})))
        assert seen.content[0].text.startswith("BLOCKED")          # the home stays hidden in the cage


def test_an_answer_that_used_a_server_kept_out_of_memory_is_not_remembered(cfg, tmp_path):
    class Host:
        def plugins(self, with_tools=True):
            mk = lambda n, mem: plg_host.Plugin(n, tmp_path, {"name": n, "kind": "mcp", "memory": mem})   # noqa: E731
            return [mk("archive", False), mk("weather", True), plg_host.Plugin("news", tmp_path, {"name": "news"})]
    assert plg_mcp.unremembered(Host()) == {"archive"}


def test_a_run_that_used_an_unremembered_server_keeps_nothing_of_it(cfg):
    """Audit, 10 Nov: the chat honoured «memory: false», a routine's memory, a reflection, a project's report did not."""
    from types import SimpleNamespace
    from aurora import agt_loop, sys_routines

    class Host:
        def plugins(self, with_tools=True):
            return [plg_host.Plugin("local_archive", Path("/"), {"name": "local_archive", "kind": "mcp", "memory": False})]
    agent = SimpleNamespace(ledger=[(f"local_archive{agt_loop.SEP}find", {}), ("weather", {})], host=Host())
    assert agt_loop.Agent.kept_out(agent) == {"local_archive"}
    agent.ledger = [(f"weather{agt_loop.SEP}now", {})]
    assert agt_loop.Agent.kept_out(agent) == set()
    import inspect
    assert "remember" in inspect.signature(sys_routines.record).parameters


def test_a_plugins_folder_moved_out_of_the_signed_one_loads_nothing(cfg, tmp_path):
    """Audit, 10 Nov: AURORA_PLUGINS_DIR set to a folder the agent wrote → its plugins loaded unsigned."""
    from aurora import sys_ethics
    (cfg.root / sys_ethics.MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    (cfg.root / sys_ethics.MANIFEST).write_text("{}")
    elsewhere = tmp_path / "elsewhere_plugins" / "evil"
    elsewhere.mkdir(parents=True)
    (elsewhere / "plugin.json").write_text(json.dumps({"name": "evil", "kind": "tool", "command": ["x"]}))
    cfg.values["AURORA_PLUGINS_DIR"] = str(elsewhere.parent)
    [p] = plg_host.PluginHost(cfg).plugins(with_tools=False)
    assert "not in sys/plugins" in p.error
