#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Measure a random sample of the PDFs: pages, text per page (born-digital vs scanned), images, time. Prints numbers
only, never any text of the documents."""
import json
import os
import random
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from evidentia import config  # noqa: E402

D = str(config.load().path("EVD_SOURCES_DIR"))      # the .env's, never a folder of this machine in the repo (B23)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
names = os.listdir(D)
random.seed(9)
pick = random.sample([n for n in names if n.lower().endswith(".pdf")], N)


def one(name):
    p = os.path.join(D, name)
    out = {"bytes": os.path.getsize(p)}
    try:
        info = subprocess.run(["pdfinfo", p], capture_output=True, text=True, timeout=30).stdout
        out["pages"] = next((int(l.split()[-1]) for l in info.splitlines() if l.startswith("Pages:")), 0)
        t0 = time.time()
        txt = subprocess.run(["pdftotext", "-layout", p, "-"], capture_output=True, timeout=120).stdout
        out["text_s"] = time.time() - t0
        out["chars"] = len(txt.decode("utf-8", "replace").strip())
        imgs = subprocess.run(["pdfimages", "-list", p], capture_output=True, text=True, timeout=60).stdout
        out["images"] = max(0, len(imgs.splitlines()) - 2)
    except Exception as e:  # noqa: BLE001
        out["error"] = type(e).__name__
    return out


t0 = time.time()
with ThreadPoolExecutor(max_workers=6) as ex:
    rows = list(ex.map(one, pick))
wall = time.time() - t0
ok = [r for r in rows if "error" not in r and r.get("pages")]
pages = [r["pages"] for r in ok]
cpp = [r["chars"] / r["pages"] for r in ok]
scanned = [r for r in ok if r["chars"] / r["pages"] < 100]
res = {
    "total_pdfs": len(names), "sample": N, "ok": len(ok), "errors": len(rows) - len(ok),
    "pages_mean": round(statistics.mean(pages), 2), "pages_median": statistics.median(pages), "pages_max": max(pages),
    "pages_total_sample": sum(pages),
    "bytes_mean": int(statistics.mean(r["bytes"] for r in ok)),
    "text_chars_per_page_median": round(statistics.median(cpp), 1),
    "scanned_share": round(len(scanned) / len(ok), 3),
    "with_images_share": round(sum(1 for r in ok if r["images"] > 0) / len(ok), 3),
    "images_total_sample": sum(r["images"] for r in ok),
    "text_seconds_per_pdf": round(statistics.mean(r["text_s"] for r in ok), 3),
    "wall_s": round(wall, 1), "workers": 6,
}
print(json.dumps(res, indent=1))
