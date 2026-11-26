#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F1: read every PDF of EVD_SOURCES_DIR into the archive (resumable). CPU only, no GPU.

    .venv/bin/python sys/evidentia/script/evd_inventory.py            all of it
    .venv/bin/python sys/evidentia/script/evd_inventory.py --limit 5000   a first slice
    .venv/bin/python sys/evidentia/script/evd_inventory.py --source <folder> --images --workers 12   a collection of images
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidentia import config, inventory  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--source", default=None, help="another collection's folder (default EVD_SOURCES_DIR)")
    ap.add_argument("--images", action="store_true", help="the folder holds images (jpg, png, tif): read by OCR")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--no-verify", action="store_true", help="a moved document trusted by its name and size alone "
                    "(by default its SHA-256 is compared: its bytes are read once)")
    a = ap.parse_args()
    cfg = config.load()
    src = Path(a.source) if a.source else cfg.path("EVD_SOURCES_DIR")
    exts = inventory.IMAGES if a.images else inventory.PDF
    print(json.dumps(inventory.run(src, cfg.path("EVD_DATA_DIR"), a.workers or cfg["EVD_WORKERS"], a.limit, exts=exts,
                                   verify=not a.no_verify)))
