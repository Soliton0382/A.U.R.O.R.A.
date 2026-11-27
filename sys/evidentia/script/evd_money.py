# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💰 Follow the money over the archive (evidentia/money.py): the money pages read, their accounts, parties, banks,
amounts and days correlated, the ties kept in findings; the strongest written to <EVD_DATA_DIR>/money_report.json.

    EVD_ENV_FILE=/etc/aurora/evidentia.env python sys/evidentia/script/evd_money.py [--limit N] [--top 15]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidentia import config, money, protect, store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    data = config.load().path("EVD_DATA_DIR")
    corpus, findings = store.connect(data, "corpus.db", readonly=True), store.connect(data, "findings.db", readonly=True)
    db = money.open_db(data)
    out = money.run(corpus, findings, protect.keys(findings), say=lambda m: print(m, flush=True), limit=a.limit, out=db)
    rep = money.report(db, a.top)
    (data / "money_report.json").write_text(json.dumps({**out, **rep}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
