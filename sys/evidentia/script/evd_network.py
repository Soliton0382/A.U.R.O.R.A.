#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""R20: the network of who wrote to whom, read from the e-mail headers of every page (evidentia/network.py), and the
kind of every document (e-mail, court, testimony, news, financial, other). CPU only; made anew at every run.

    .venv/bin/python sys/evidentia/script/evd_network.py                      # build it (minutes, not hours: I9)
    .venv/bin/python sys/evidentia/script/evd_network.py protect "First Last" "why"   # never shown, never walked
    .venv/bin/python sys/evidentia/script/evd_network.py people     # only the people again (names, who may be named)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidentia import config, network, store  # noqa: E402


def main(argv: list[str]) -> int:
    data = config.load().path("EVD_DATA_DIR")
    findings = sqlite3.connect(data / "findings.db")
    findings.execute("PRAGMA journal_mode=WAL")
    if argv[:1] == ["protect"] and len(argv) >= 2:
        print("protected:", network.protect(findings, argv[1], " ".join(argv[2:])))
        return 0
    corpus = store.connect(data, "corpus.db", readonly=True)
    if argv[:1] == ["people"]:                    # only the people again, from the ties already built
        print("public:", network.people_table(corpus, findings))
        return 0
    print(network.build(corpus, findings, say=lambda s: print(s, flush=True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
