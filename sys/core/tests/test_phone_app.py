# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📱 The phone app's page: the newest APK offered, logged in only, the steps and their screens in the WebUI."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "aurora" / "api" / "phone_app.py").read_text()
PAGE = (ROOT / "webui" / "js" / "modules" / "phone_app.js").read_text()


def test_the_newest_version_is_offered(cfg):
    from aurora import sys_phone_app
    assert sys_phone_app.newest(cfg) is None and sys_phone_app.info(cfg) == {"available": False}
    d = cfg.path("AURORA_STATUS_DIR") / "app"
    d.mkdir(parents=True)
    for v in ("0.2.1", "0.10.0", "0.9.9"):
        (d / f"aurora-app-{v}.apk").write_bytes(b"PK" + v.encode())
    (d / "aurora-app-9.0.0.apk.part").write_bytes(b"x")              # not a finished build
    info = sys_phone_app.info(cfg)
    assert info["version"] == "0.10.0" and info["size"] == 8 and len(info["sha256"]) == 64


def test_both_routes_need_a_login():
    routes = re.findall(r'@router\.get\("([^"]+)", dependencies=\[Depends\((\w+)\)\]\)', SRC)
    assert routes == [("/v1/aurora/app", "auth"), ("/v1/aurora/app/download", "auth")]
    assert "'phone_app'" in (ROOT / "aurora" / "api" / "__init__.py").read_text()


def test_the_page_is_in_the_menu_with_its_texts_and_screens():
    assert 'import phoneApp from "./modules/phone_app.js"' in (ROOT / "webui" / "js" / "modules.js").read_text()
    assert "/static/js/modules/phone_app.js" in (ROOT / "webui" / "sw.js").read_text()
    keys = set(re.findall(r'"(phoneapp\.[\w.]+)"', PAGE))
    for loc in ("it_IT", "en_US"):
        table = json.loads((ROOT / "webui" / "i18n" / f"{loc}.json").read_text())
        assert keys and keys <= set(table) and "nav.phoneapp" in table
        assert "{host}" in table["phoneapp.s3"] and "{port}" in table["phoneapp.s3"]   # this Aurora's, read live
    for b in re.findall(r'"(\w+)"', PAGE.split("const BRANDS = [")[1].split("]")[0]):  # the makers' rows
        assert f"phoneapp.bg.{b}" in table and f"phoneapp.bg.{b}.name" in table
    for shot in re.findall(r'"phoneapp\.s\d", "(\w+)"', PAGE):
        assert (ROOT / "webui" / "assets" / "app" / f"{shot}.webp").is_file()
