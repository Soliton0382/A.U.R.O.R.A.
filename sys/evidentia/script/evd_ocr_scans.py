# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C751: OCR of the scanned pages inside PDFs that have no text (evidentia/ocr_scans). Goes on from where it stopped.

    EVD_ENV_FILE=/etc/aurora/evidentia.env python sys/evidentia/script/evd_ocr_scans.py [--workers 12] [--limit N]
Then the vectors of the new passages: evd_embed.py (as after an inventory)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidentia import config, ocr_scans  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    cfg = config.load()
    print(json.dumps(ocr_scans.run(cfg.path("EVD_DATA_DIR"), a.workers or cfg["EVD_WORKERS"], a.limit, say=lambda m: print(m, flush=True))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
