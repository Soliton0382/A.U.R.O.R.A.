# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Owner, 27 Nov: Aurora Desktop on Aurora's own computer asks nothing; elsewhere the Android app's form, with the
same rules (desk/app/address.py mirrors sys/app's Address.java)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desk.app import address as A  # noqa: E402


@pytest.mark.parametrize("typed,want", [("aurora.example", "https://aurora.example"), ("Aurora.Example:8443", "https://aurora.example:8443"),
                                        ("https://aurora.example:443/x", "https://aurora.example"), ("http://aurora.example", None),
                                        ("https://user@aurora.example", None), ("", None), ("https://", None)])
def test_an_address_as_the_android_app_reads_it(typed, want):
    assert A.normalize(typed) == want


def test_the_form_s_two_fields():
    assert A.of("aurora.example", "8443") == "https://aurora.example:8443"
    assert A.of("aurora.example", "") == "https://aurora.example" and A.of("aurora.example", "443") == "https://aurora.example"
    assert A.of("aurora.example", "99999") is None and A.of("aurora.example", "80a") is None and A.of("", "8443") is None


def test_here_nothing_asked_else_the_saved_one_else_the_form(tmp_path, monkeypatch):
    monkeypatch.setattr(A.store, "STATE", tmp_path)
    assert A.choose(up=lambda u: True, state=tmp_path) == (A.LOCAL, "local")
    assert A.choose(up=lambda u: False, state=tmp_path) == (None, "ask")
    A.save("https://aurora.example:8443", tmp_path)
    assert oct((tmp_path / A.FILE).stat().st_mode & 0o777) == "0o600"
    assert A.choose(up=lambda u: False, state=tmp_path) == ("https://aurora.example:8443", "saved")
    assert A.choose(setup=True, up=lambda u: True, state=tmp_path) == (None, "ask")   # the menu: the form always


def test_the_android_rules_are_the_same():
    java = (ROOT.parent / "app" / "android" / "java" / "org" / "aurora" / "app" / "Address.java").read_text(encoding="utf-8")
    assert '"https".equals' in java and '"443".equals(p)' in java                    # HTTPS only, 443 left out


def test_the_launcher_and_the_tray_open_the_form_again():
    root = (ROOT / "script" / "sys_root_desk.py").read_text(encoding="utf-8")
    assert "--web-setup" in root and 'DESK_WEB_SETUP="$setup"' in root
    tray = (ROOT / "desk" / "app" / "tray.py").read_text(encoding="utf-8")
    assert '("Cambia indirizzo di Aurora", self._web_setup)' in tray and '"--web-setup"' in tray
