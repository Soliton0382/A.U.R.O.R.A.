# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N169 (owner, 27 Nov): Aurora's window for a computer without Aurora — one package from the WebUI (📱 App →
🖥️), its installer for the user (nothing as root), the window's modules only (never the learning part)."""
import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_package_holds_the_window_its_form_and_its_installer():
    sys.path.insert(0, str(ROOT))
    from desk.client import package
    names = tarfile.open(fileobj=io.BytesIO(package.build())).getnames()
    assert "aurora-desk-client/install.sh" in names and "aurora-desk-client/requirements.txt" in names
    assert "aurora-desk-client/desk/app/web.py" in names and "aurora-desk-client/desk/app/connect_form.py" in names
    assert not any("recorder" in n or "learned" in n or "tray" in n for n in names)        # the window only
    api = (ROOT / "aurora" / "api" / "phone_app.py").read_text(encoding="utf-8")
    assert '@router.get("/v1/aurora/app/desk", dependencies=[Depends(auth)])' in api and "package.build()" in api


def test_the_installer_is_the_user_s_and_pins_what_was_tried():
    sh = (ROOT / "desk" / "client" / "install.sh").read_text(encoding="utf-8")
    assert subprocess.run(["sh", "-n", str(ROOT / "desk" / "client" / "install.sh")]).returncode == 0
    assert "sudo" not in sh and "$HOME/.local" in sh and "--remove" in sh
    req = (ROOT / "desk" / "client" / "requirements.txt").read_text(encoding="utf-8")
    assert "PyQt6==6.10.2" in req and "PyQt6-WebEngine==6.10.0" in req
