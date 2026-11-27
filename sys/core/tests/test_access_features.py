# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N165: the features' registry (config/access_features.json) is true to the code — every page, plugin and API prefix it
names exists, and a prefix it closes is called by no page of another feature (a page that gathers others' pieces, as
☀️ Oggi, must take a refusal: it is listed below and its calls are caught). Old rules read under the new names."""
import json
import re
from pathlib import Path

from aurora import sys_users_groups as G

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "sys" / "core" / "webui" / "js"
EVD = ROOT / "sys" / "evidentia" / "addon" / "webui"
GATHERERS = {"today", "advanced", "alerts", "metrics", "brain", "sky", "chat"}   # widgets and the chat: pieces of others


def _pages() -> dict[str, str]:
    """page id → its source (with the modules it imports from the same folder)."""
    files = {f: f.read_text(encoding="utf-8") for f in [*WEB.rglob("*.js"), *EVD.rglob("*.js")]
             if "local" not in f.relative_to(ROOT).parts}       # an installation's own pages: not the public code's
    out = {}
    for f, s in files.items():
        for m in re.finditer(r'^\s+id: "([a-z_]+)"', s, re.M):
            src = s + "".join(files.get(f.parent / i, "") for i in re.findall(r'from "\./([a-z_]+\.js)"', s))
            out.setdefault(m.group(1), src)
        for m in re.finditer(r'page\("([a-z_]+)"', s):
            out.setdefault(m.group(1), s)
    return out


def test_every_page_plugin_and_prefix_exists():
    pages = _pages()
    plugins = {p.parent.name for p in (ROOT / "sys" / "plugins").glob("*/plugin.json")}
    routes = [m for f in [*(ROOT / "sys" / "core" / "aurora" / "api").glob("*.py"), *(ROOT / "sys" / "evidentia" / "addon").glob("*.py")]
              for m in re.findall(r'@router\.(?:get|post|put|patch|delete|api_route)\("(/v1/aurora/[^"]+)"', f.read_text(encoding="utf-8"))]
    assert len(routes) > 300
    reg = G.registry()
    assert len({f["id"] for f in reg}) == len(reg)
    for f in reg:
        assert G.FEATURE.match(f["id"]) and f["default"] in ("all", "admin"), f["id"]
        for p in f["pages"]:
            assert p in pages, f"{f['id']}: no page {p}"
        for p in f["plugins"]:
            assert p in plugins, f"{f['id']}: no plugin {p}"
        for a in f["api"]:
            assert any(r == a or r.startswith(a + "/") for r in routes), f"{f['id']}: no route under {a}"


def test_a_closed_prefix_is_no_other_page_s():
    pages = _pages()
    for view, src in pages.items():
        mine = G.of_page(view)
        for call in set(re.findall(r'["`](/v1/aurora/[a-z_\-/]+)', src)):
            f = G.of_path(call.rstrip("/"))
            if f is None or f == mine or view in GATHERERS:
                continue
            raise AssertionError(f"page {view} calls {call}, a prefix of the feature {f}")


def test_paths_whole_segments_and_old_names():
    assert G.of_path("/v1/aurora/dj") == "dj" and G.of_path("/v1/aurora/dj-song/x") == "dj"
    assert G.of_path("/v1/aurora/calendar/items/3") == "calendar" and G.of_path("/v1/aurora/calendarx") is None
    assert G.of_path("/v1/aurora/approvals") is None and G.of_path("/v1/aurora/app/download") == "phoneapp"
    assert G.canonical("plugin:calendar") == "calendar" and G.canonical("addon:evidentia") == "evidentia"
    assert G.canonical("plugin:telegram") == "plugin:telegram" and G.of_plugin("spotify") == "dj"


def test_defaults_as_before_and_an_old_rule_still_counts(cfg):
    assert G.may_use(cfg, "ann", "calendar", "boss") and G.may_use(cfg, "ann", "plugin:telegram", "boss")
    assert not G.may_use(cfg, "ann", "evidentia", "boss") and G.may_use(cfg, "boss", "evidentia", "boss")
    f = G._file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"groups": {}, "access": {"plugin:calendar": {"all": False, "users": [], "groups": []}}}))
    assert not G.may_use(cfg, "ann", "calendar", "boss") and not G.may_use(cfg, "ann", "plugin:calendar", "boss")
    assert G.denied_pages(cfg, "ann", "boss") == ["calendar", "evd_agents", "evd_archives", "evd_cases", "evd_money",
                                                  "evd_net", "evd_routines", "evd_server", "evidentia"]
    G.set_access(cfg, "calendar", True, [], [])
    assert list(json.loads(f.read_text())["access"]) == ["calendar"]       # the old name gone: one rule per feature


def test_administrative_plugins_are_the_admin_s_and_accounts_are_each_user_s(cfg):
    """Owner, 27 Nov: connectors with an account become each user's; ntfy, link checking and what touches Aurora's
    configuration or health stay the admin's. A plugin open to all keeps every one of its account settings per user."""
    for p in ("ntfy", "linkcheck", "self", "senses", "ha_query", "backup"):
        assert not G.may_use(cfg, "ann", f"plugin:{p}", "boss") and G.may_use(cfg, "boss", f"plugin:{p}", "boss")
    for p in ("telegram", "email", "github", "dropbox", "weather"):
        assert G.may_use(cfg, "ann", f"plugin:{p}", "boss")
    assert G.of_plugin("ha_states") == "plugin:ha_states"                   # out of «Casa»: the machine's own token
    schema = {s["key"]: s for s in json.loads((ROOT / "sys" / "core" / "config" / "settings_schema.json").read_text())["settings"]}
    for name in ("telegram", "email", "github", "dropbox", "nextcloud", "whatsapp", "discord", "mastodon", "homeassistant"):
        d = json.loads((ROOT / "sys" / "plugins" / name / "plugin.json").read_text())
        keys = [k for k in (d.get("settings") or []) + list(d.get("requires") or []) + [k for k in (d.get("env") or []) if isinstance(k, str)]
                if k in schema and any(w in k for w in ("TOKEN", "PASSWORD", "USER", "KEY"))]
        assert keys and all(schema[k].get("scope") == "user" for k in keys), name
