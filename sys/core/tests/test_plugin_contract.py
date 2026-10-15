# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The plugin contract (owner, 16 Oct: «hanno tutti un contratto di funzionamento… se no creiamo casini»): every plugin
of sys/plugins follows it, and a manifest that breaks it is told why."""
import json
from pathlib import Path

from aurora import plg_contract as C

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
GOOD = {"name": "demo", "version": "1.0", "kind": "tool", "description": {"it": "x", "en": "x"},
        "command": ["{python}", "server.py"], "requires": [], "effects": {"*": "read"}}


def test_every_plugin_follows_the_contract():
    broken = {f.parent.name: C.check(json.loads(f.read_text(encoding="utf-8")), f.parent.name)
              for f in sorted(PLUGINS.glob("*/plugin.json"))}
    assert {k: v for k, v in broken.items() if v} == {}
    assert len(broken) >= 30


def test_a_manifest_that_breaks_it_is_told_why():
    assert C.check(GOOD, "demo") == []
    bad = {**GOOD, "kind": "agent", "effects": {"x": "delete"}, "sandbox": {"network": "yes", "disk": 1}, "colour": "red",
           "settings_spec": [{"key": "AURORA_OTHER_X"}]}
    errs = " | ".join(C.check(bad, "other"))
    for part in ("kind 'agent'", "x=delete", "sandbox: disk", "sandbox.network", "colour", "AURORA_DEMO_", "folder"):
        assert part in errs, part
    assert any("description" in e for e in C.check({**GOOD, "description": {"it": "x"}}))


def test_a_plugin_s_page_is_a_page_of_the_menu():
    """A plugin with a page of its own is configured there (owner, 16 Oct): the page must exist."""
    import re
    js = Path(__file__).resolve().parents[1] / "webui" / "js"
    ids = {m for f in js.rglob("*.js") for m in re.findall(r'^\s*id: "([a-z_]+)"', f.read_text(encoding="utf-8"), re.M)}
    pages = {f.parent.name: json.loads(f.read_text(encoding="utf-8")).get("page") for f in PLUGINS.glob("*/plugin.json")}
    assert {k: v for k, v in pages.items() if v and v not in ids} == {}
    assert pages.get("security") == "firewalls" and pages.get("health") == "care"
