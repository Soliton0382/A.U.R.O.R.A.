# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Import documents into the knowledge vault through aurora-api.

The API process is the only writer of the vault and the index, so documents go
through it (POST /v1/aurora/import) and are serialized with the running answers.
Folders are walked recursively; unsupported files are listed and skipped.

    python sys/core/script/kno_import.py --domain physics paper.pdf notes/
    python sys/core/script/kno_import.py --domains          # list the knowledge domains
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sys_config  # noqa: E402
from aurora.kno_ingest import FORMATS  # noqa: E402


def files(paths: list[str]) -> tuple[list[Path], list[Path]]:
    found, skipped = [], []
    for p in map(Path, paths):
        for f in (sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]):
            (found if f.suffix.lower() in FORMATS else skipped).append(f)
    return found, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--domain", help="knowledge domain of the taxonomy")
    ap.add_argument("--title", default="", help="title for a single document (default: its own)")
    ap.add_argument("--domains", action="store_true", help="list the knowledge domains and exit")
    args = ap.parse_args()
    cfg = sys_config.get()
    base = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
    client = httpx.Client(headers={"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}, timeout=cfg["AURORA_LLM_TIMEOUT_S"])
    if args.domains:
        for d in client.get(f"{base}/v1/aurora/domains").raise_for_status().json():
            print(f"{d['id']:28} {d['it']} / {d['en']}")
        return 0
    if not args.domain or not args.paths:
        ap.error("--domain and at least one path are required")
    found, skipped = files(args.paths)
    for f in skipped:
        print(f"skip  {f} (unsupported format)")
    failed = 0
    for f in found:
        body = {"name": f.name, "domain": args.domain, "data": base64.b64encode(f.read_bytes()).decode("ascii"),
                "title": args.title if len(found) == 1 else ""}
        r = client.post(f"{base}/v1/aurora/import", json=body)
        if r.status_code != 200:
            failed += 1
            print(f"FAIL  {f}: {r.status_code} {r.json().get('detail', r.text)}")
            continue
        x = r.json()
        print(f"ok    {f}: {x['chunks']} chunks, {x['written']} new, {x['duplicates']} already known, "
              f"{len(x['rejected'])} rejected, {x['indexed']} indexed")
        for sid, problems in x["rejected"].items():
            print(f"      rejected {sid}: {'; '.join(problems)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
