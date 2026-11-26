# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N165 F3–F5 (owner, 27 Nov): the menu tidied — 💻 Sistema and 🗝️ Amministrazione, the chat's tabs, 💾 Backup e
ripristino, one icon per entry, each plugin with a page set up there (and in that page's feature)."""
import json
import re
from pathlib import Path

from aurora import sys_users_groups as G

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "sys" / "core" / "webui" / "js"
MODULES = (WEB / "modules.js").read_text(encoding="utf-8")


def _icons() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    files = [*WEB.rglob("*.js"), *(ROOT / "sys" / "evidentia" / "addon" / "webui").rglob("*.js")]
    for f in files:
        if "local" in f.relative_to(ROOT).parts:
            continue
        s = f.read_text(encoding="utf-8")
        for m in re.finditer(r'^\s+id: "([a-z_]+)",\s*\n\s+icon: "([^"]+)"', s, re.M):
            out.setdefault(m.group(2), []).append(m.group(1))
        for m in re.finditer(r'page\("([a-z_]+)", "([^"]+)"', s):
            out.setdefault(m.group(2), []).append(m.group(1))
    for m in re.finditer(r'\{ id: "([a-z]+)", icon: "([^"]+)"', MODULES):
        out.setdefault(m.group(2), []).append("area:" + m.group(1))
    return out


def test_one_icon_per_entry():
    twice = {i: v for i, v in _icons().items() if len(set(v)) > 1}
    assert not twice, twice


def test_the_areas_and_the_chat_s_tabs():
    system = re.search(r'id: "system".*?views: \[([^\]]*)\]', MODULES).group(1)
    admin = re.search(r'id: "admin".*?views: \[([^\]]*)\]', MODULES).group(1)
    assert "users" not in system and "plugins" not in system and "models" in system
    assert all(f'"{v}"' in admin for v in ("users", "accounts", "usage", "autonomy", "settings", "backup", "plugins", "phoneapp"))
    assert 'id: "anonchat", views' not in MODULES and 'id: "interpret", views' not in MODULES
    assert "for (const v of [anonchat, interpret]) v.menu = false;" in MODULES
    assert re.search(r'adminOnly = new Set\(\["backup",', MODULES)
    for page in ("chat.js", "chat_anon.js", "interpret.js"):
        assert "chatTabs(" in (WEB / "modules" / page).read_text(encoding="utf-8")
    css = (ROOT / "sys" / "core" / "webui" / "css" / "chat.css").read_text(encoding="utf-8")
    assert ".view.chat.has-tabs:not(.hidden)" in css and "min-height: 0" in css     # the input never cut off


def test_each_plugin_with_a_page_is_in_that_page_s_feature():
    for f in sorted((ROOT / "sys" / "plugins").glob("*/plugin.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        page = d.get("page")
        feat = G.of_page(page) if page else None
        if feat:
            assert G.of_plugin(d["name"]) == feat, f"{d['name']} is set up in {page} ({feat}) but belongs to {G.of_plugin(d['name'])}"
    for n in ("backup", "backup_files", "backup_verify"):         # those of this installation (one is not published)
        f = ROOT / "sys" / "plugins" / n / "plugin.json"
        if f.is_file():
            assert json.loads(f.read_text())["page"] == "backup"


def test_the_plugins_page_splits_connectors_and_tools():
    s = (WEB / "modules" / "plugins.js").read_text(encoding="utf-8")
    assert '["connector", "🔗", "plug.k.connector"]' in s and 'p.kind === "connector"' in s
    assert 'const plugins = all.filter((p) => !p.page);' in s                   # a plugin with a page: set up there
    for lang in ("it_IT", "en_US"):
        d = json.loads((ROOT / "sys" / "core" / "webui" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        assert all(k in d for k in ("plug.k.connector", "plug.k.tool", "plug.go_page", "nav.backup", "nav.g.admin"))
