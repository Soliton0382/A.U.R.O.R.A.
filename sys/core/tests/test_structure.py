# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The installation holds together: settings, texts, pages, models and features name each other consistently.
Each test is a class of configuration bug that would show only when a feature is used."""
import json
import re
from pathlib import Path

from aurora import sys_config
from aurora import sys_features as F

CORE = Path(__file__).resolve().parents[1]
ROOT = CORE.parents[1]
WEB = CORE / "webui"
PROCESS_ENV = {"AURORA_ENV_FILE", "AURORA_IN_SANDBOX", "AURORA_PUBLISH_DENY", "AURORA_PLUGIN"}   # variables of a process, not settings
# (AURORA_INSTALL_* too: the installer's unattended answers, read once by install.sh)


def code_files():
    yield from (CORE / "aurora").rglob("*.py")
    yield from (CORE / "script").glob("*.py")
    yield from (CORE / "script").glob("*.sh")
    yield from (ROOT / "sys" / "plugins").glob("*/*.py")
    yield from (ROOT / "sys" / "plugins").glob("*/plugin.json")
    yield from WEB.rglob("*.js")
    yield from (ROOT / "sys" / "deploy").rglob("*.*")
    yield ROOT / "install.sh"


def named_keys():
    keys = {}
    for f in code_files():
        if f.is_file():
            for k in re.findall(r"\b(AURORA_[A-Z0-9_]+)\b", f.read_text(encoding="utf-8", errors="replace")):
                keys.setdefault(k, f.name)
    return keys


def test_every_setting_the_code_reads_is_in_the_schema_and_every_setting_is_read():
    schema = {s["key"] for s in sys_config.load_schema()["settings"]}
    named = named_keys()
    assert sorted(k for k in named if k not in schema and k not in PROCESS_ENV
                  and not k.endswith("_") and not k.startswith("AURORA_INSTALL_")) == [],"the code reads a setting the schema does not describe"
    assert sorted(schema - set(named) - {"AURORA_ROOT"}) == [], "a setting nothing reads: changing it would do nothing"


def test_both_languages_have_every_text_the_interface_uses():
    it = json.loads((WEB / "i18n/it_IT.json").read_text(encoding="utf-8"))
    en = json.loads((WEB / "i18n/en_US.json").read_text(encoding="utf-8"))
    assert set(it) == set(en)
    used = set()
    for f in list(WEB.rglob("*.js")) + list(WEB.glob("*.html")):
        s = f.read_text(encoding="utf-8")
        used |= set(re.findall(r'\bt\(\s*"([a-z][\w.]+)"', s)) | set(re.findall(r'data-i18n(?:-[a-z]+)?="([\w.]+)"', s))
        used |= set(re.findall(r'title: "(nav\.\w+)"', s))
    assert sorted(used - set(it)) == []


def test_every_page_of_the_menu_has_its_line_in_the_guide():
    it = json.loads((WEB / "i18n/it_IT.json").read_text(encoding="utf-8"))
    views = re.search(r"export const views = \[([^\]]+)\]", (WEB / "js/modules.js").read_text(encoding="utf-8")).group(1)
    ids = []
    for name in (v.strip() for v in views.split(",")):
        src = re.search(rf'import {name} from "\./modules/(\w+)\.js"', (WEB / "js/modules.js").read_text(encoding="utf-8"))
        ids.append(re.search(r'id: "(\w+)"', (WEB / f"js/modules/{src.group(1)}.js").read_text(encoding="utf-8")).group(1))
    assert sorted(i for i in ids if i != "guide" and f"gd.p.{i}" not in it) == []


def test_the_offline_shell_lists_only_files_that_exist():
    # cache.addAll is all or nothing: one missing file and the phone app has no offline shell at all
    files = re.findall(r'"(/static/[^"]+|/manifest\.webmanifest)"', (WEB / "sw.js").read_text(encoding="utf-8"))
    missing = [f for f in files if not (WEB / f.removeprefix("/static/")).is_file()
               and not (WEB / f.lstrip("/")).is_file()]
    assert len(files) > 20 and missing == []


def test_every_api_module_has_a_router_and_only_public_functions_are_routes():
    import ast
    api = CORE / "aurora" / "api"
    modules = ast.literal_eval(re.search(r"MODULES = (\[.*\])", (api / "__init__.py").read_text()).group(1))
    # core and its parts (core_*: shared code, no routes) are not routers
    assert sorted(modules) == sorted(f.stem for f in api.glob("*.py") if f.stem != "__init__" and not f.stem.startswith("core"))
    routes = 0
    for name in modules:
        tree = ast.parse((api / f"{name}.py").read_text(encoding="utf-8"))
        assert any(isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "router" for t in n.targets) for n in tree.body)
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                    "router." in ast.unparse(d) for d in n.decorator_list):
                assert not n.name.startswith("_"), f"{name}.{n.name}: a helper took a route's decorator"
                routes += sum("router." in ast.unparse(d) for d in n.decorator_list)
    assert routes >= 89                     # 89 on 2 October 2026 (+ the WebUI's 3 and /static in svc_api): none lost


def test_every_setting_category_is_declared_with_both_labels():
    schema = sys_config.load_schema()
    used = {s["category"] for s in schema["settings"]}
    assert sorted(used - set(schema["categories"])) == []          # .env.example and the Settings page need them
    assert all({"it", "en"} <= set(v) for v in schema["categories"].values())


def test_the_api_publishes_no_map_of_itself():
    src = (CORE / "script" / "svc_api.py").read_text(encoding="utf-8")
    app = re.search(r"^app = FastAPI\((.*)\)", src, re.M).group(1)
    assert all(f"{k}=None" in app for k in ("docs_url", "redoc_url", "openapi_url"))   # C79


def test_models_features_and_installer_groups_agree():
    man = F.manifest()
    for name, (_, _, models, paths, switch, _) in F.FEATURES.items():
        assert set(models) <= set(man), f"{name} needs a model the manifest does not have"
    schema = {s["key"] for s in sys_config.load_schema()["settings"]}
    assert {p for f in F.FEATURES.values() for p in f[3]} | {f[4] for f in F.FEATURES.values() if f[4]} <= schema
    grouped = {m for g in F.GROUPS.values() for m in g["models"]}
    optional = {m for m, spec in man.items() if not spec["required"]}
    assert grouped == optional, "an optional model the installer would never offer, or a group naming a required one"
    assert {f for g in F.GROUPS.values() for f in g["features"]} <= set(F.FEATURES)
    for m, spec in man.items():
        assert set(spec.get("settings", {})) <= schema


def test_aurora_s_own_files_open_inside_the_page_never_in_a_new_window():
    # the installed app opens a new window in the system browser, which has no device cookie: "invalid key" (C39, C100)
    for name in ("chat.js", "trace.js", "uploads.js", "routines.js"):
        src = (WEB / "js" / "modules" / name).read_text(encoding="utf-8")
        assert '"_blank"' not in src and "window.open" not in src, name
    assert "viewLink" in (WEB / "js" / "modules" / "trace.js").read_text(encoding="utf-8")
