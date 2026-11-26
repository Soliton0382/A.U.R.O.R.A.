# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N169: aurora-desk-client.tar.gz — Aurora's window for a computer where Aurora is not (its installer, its pinned
requirements, the window's modules as this Aurora has them; never the learning part). Served by GET /v1/aurora/app/desk."""
from __future__ import annotations

import io
import tarfile
from pathlib import Path

CORE = Path(__file__).resolve().parents[2]
FILES = ("desk/__init__.py", "desk/app/__init__.py", "desk/app/web.py", "desk/app/store.py", "desk/app/icon.py",
         "desk/app/address.py", "desk/app/connect_form.py")


def build(core: Path = CORE) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel, arc in [("desk/client/install.sh", "install.sh"), ("desk/client/requirements.txt", "requirements.txt"),
                         *[(f, f) for f in FILES]]:
            info = tar.gettarinfo(str(core / rel), arcname=f"aurora-desk-client/{arc}")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if arc.endswith(".sh") else 0o644
            with open(core / rel, "rb") as f:
                tar.addfile(info, f)
    return buf.getvalue()
