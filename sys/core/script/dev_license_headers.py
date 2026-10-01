# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Apache-2.0 headers on every source file of the repository (SPDX form).

    python sys/core/script/dev_license_headers.py            # report the files without a header
    python sys/core/script/dev_license_headers.py --apply    # add the header where it is missing

The protected files of the code of conduct are skipped unless --include-protected is given:
changing them stops every service until the owner signs again (sys_ethics_sign.py sign).
A shebang and a Python encoding line stay first; files that already carry an SPDX line are left alone.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_ethics  # noqa: E402

ROOT = sys_ethics.CODE_ROOT
HOLDER = "A.U.R.O.R.A. Project"
YEAR = "2026"
STYLE = {".py": ("# ", ""), ".sh": ("# ", ""), ".js": ("// ", ""), ".css": ("/* ", " */")}
SKIP_DIRS = {".venv", ".git", "node_modules", "runtime", "models", "vault", "logs", "status", "sandbox", "tmp", "usr", "deploy", "https"}


def files() -> list[Path]:
    """Files git would publish (respects .gitignore); without git, a walk that skips data folders."""
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split("\n")
        found = [ROOT / p for p in out if p]
    except (OSError, subprocess.CalledProcessError):
        found = [p for p in ROOT.rglob("*") if p.is_file() and not SKIP_DIRS & set(p.relative_to(ROOT).parts)]
    return sorted(p for p in found if p.suffix in STYLE and p.is_file())


def header(suffix: str) -> list[str]:
    a, b = STYLE[suffix]
    return [f"{a}SPDX-License-Identifier: Apache-2.0{b}", f"{a}Copyright {YEAR} {HOLDER}{b}"]


def add(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").split("\n")
    keep = 0
    if lines and lines[0].startswith("#!"):
        keep = 1
    if len(lines) > keep and "coding" in lines[keep] and lines[keep].startswith("#"):
        keep += 1
    path.write_text("\n".join(lines[:keep] + header(path.suffix) + lines[keep:]), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-protected", action="store_true")
    args = ap.parse_args()
    protected = {ROOT / p for p in sys_ethics.PROTECTED}
    missing = [p for p in files() if "SPDX-License-Identifier" not in p.read_text(encoding="utf-8")[:600]]
    skipped = [p for p in missing if p in protected and not args.include_protected]
    todo = [p for p in missing if p not in skipped]
    for p in todo:
        print(("added: " if args.apply else "missing: ") + str(p.relative_to(ROOT)))
        if args.apply:
            add(p)
    for p in skipped:
        print(f"protected, skipped: {p.relative_to(ROOT)} (use --include-protected, then sign)")
    print(f"{len(todo)} {'updated' if args.apply else 'without header'}, {len(skipped)} protected skipped")
    return 0 if args.apply or not missing else 1


if __name__ == "__main__":
    sys.exit(main())
