# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The lines of code of a tree, for the README's badge (owner, 28 Oct: «le righe di codice in bella mostra sulla prima
pagina rendono l'idea della complessità del progetto»): the files git keeps, non-empty lines of the code's own
languages; the plugins' bundled third-party libraries and programs (.deps, .bin), the Mac and Windows ports' copies,
the documents and the data left out. Usage: doc_loc.py <root> [--badge] — the count, or the badge's text (103k).
"""
import subprocess
import sys
from pathlib import Path

CODE = {".py", ".js", ".css", ".sh", ".html", ".java", ".ps1", ".yml"}
SKIP = ("/.deps/", "/.bin/")


def count(root: Path) -> int:
    files = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
    total = 0
    for rel in files:
        if not rel or Path(rel).suffix not in CODE or any(s in f"/{rel}" for s in SKIP) \
                or rel.startswith(("Aurora_mac/", "Aurora_windows/", "docs/")):
            continue
        try:
            with open(root / rel, encoding="utf-8", errors="ignore") as f:
                total += sum(1 for line in f if line.strip())
        except OSError:
            continue
    return total


def badge(n: int) -> str:
    return f"{n / 1000:.0f}k" if n >= 10000 else str(n)


if __name__ == "__main__":
    n = count(Path(sys.argv[1]))
    print(badge(n) if "--badge" in sys.argv else n)
