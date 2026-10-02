# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Before a publish: nothing Aurora knows to be the owner's may be in the published folder.

    python sys/core/script/dev_privacy_scan.py /path/to/mirror      # exit 1 and file:line for every hit

The terms come from the installation itself, not from a list kept by hand: what the cloud masker hides (the value of
every secret setting, the owner's name, domain, place, coordinates, sensitive words, home folder) and the devices the
firewall reports in its logs (device names and serial numbers). A hit is shown by file, line and kind — never the
value. The owner's hand-made deny list (dev_publish.sh) stays as a second net.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config  # noqa: E402
from aurora.sec_mask import Pseudonymizer  # noqa: E402

DEVICE = re.compile(r'\b(device_name|device_serial_id|serial|hostname)="([^"]{4,})"')
TEXT = {".py", ".md", ".json", ".js", ".css", ".html", ".sh", ".txt", ".toml", ".yml", ".yaml", ".service", ".example",
        ".lock", ".cfg", ".ini", ".svg", ".webmanifest", ""}


def terms(cfg: sys_config.Config) -> dict[str, str]:
    """{term: kind}"""
    p = Pseudonymizer(cfg)
    out = {t: "secret setting" for t in p.secrets}
    out.update({t: "owner's own words" for t in p.private})
    for f in cfg.path("AURORA_LOG_DIR").glob("firewall/*.log"):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                for kind, value in DEVICE.findall(line):
                    out.setdefault(value, f"firewall {kind}")
                if i > 200_000:                          # the devices repeat: the head of the log is enough
                    break
    return {t: k for t, k in out.items() if len(t) >= 4}


def main() -> int:
    dst = Path(sys.argv[1]).resolve()
    found = terms(sys_config.get())
    hits = 0
    for f in sorted(dst.rglob("*")):
        if ".git" in f.parts or not f.is_file() or f.suffix not in TEXT:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        low = text.lower()
        for term, kind in found.items():
            if term.lower() in low:
                for n, line in enumerate(text.splitlines(), 1):
                    if term.lower() in line.lower():
                        print(f"  {f.relative_to(dst)}:{n}: {kind}")
                        hits += 1
    print(f"{len(found)} private terms checked: " + (f"{hits} hits" if hits else "none found"))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
