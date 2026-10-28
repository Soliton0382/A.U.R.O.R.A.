# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What root keeps for Aurora, refreshed by root only (the installer, the owner's signature): run with sudo.

1. The code the root units run (aurora-mount, aurora-retime) as a copy root owns, /usr/local/lib/aurora (owner, 28 Oct,
   after the security review: those units ran the service user's own files as root — whoever could write them was
   root at the next start). The copy is run by the system's Python with -I; from the installation it reads data only
   (the .env, the schema), never code (INSTALL_ROOT).
2. /etc/aurora/nft-never: the addresses the root firewall helper never blocks, whatever it is asked (the owner's
   protected addresses, the gateways, this machine's own) — the list was only in the service's Python (C420).

Usage: sudo .venv/bin/python sys/core/script/sys_root_sync.py [--check]
"""
from __future__ import annotations

import ipaddress
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIB = Path("/usr/local/lib/aurora")
NEVER = Path("/etc/aurora/nft-never")
SCRIPTS = ("sys_nas_mount.py", "sys_backup_retime.py", "sys_cert_perms.py")


def _own(path: Path, mode: int) -> None:
    os.chown(path, 0, 0)
    os.chmod(path, mode)


def sync_code() -> int:
    """sys/core/aurora (its .py files) and the root units' scripts copied under LIB, root:root, read only to others."""
    tmp = LIB.with_name("aurora.new")
    if tmp.exists():
        shutil.rmtree(tmp)
    src = ROOT / "sys" / "core"
    n = 0
    for rel in [p.relative_to(src) for p in (src / "aurora").rglob("*.py")] + [Path("script") / s for s in SCRIPTS]:
        dst = tmp / "sys" / "core" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / rel, dst)
        n += 1
    for p in [tmp, *tmp.rglob("*")]:
        _own(p, 0o755 if p.is_dir() else 0o644)
    if LIB.exists():
        shutil.rmtree(LIB)
    tmp.rename(LIB)
    return n


def never_list() -> list[str]:
    """The addresses never blocked: this machine's, the default gateways, the owner's protected ones and the firewall."""
    out: set[str] = set()
    r = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True)
    out |= {line.split()[3].split("/")[0] for line in r.stdout.splitlines() if len(line.split()) > 3}
    r = subprocess.run(["ip", "-4", "route", "show", "default"], capture_output=True, text=True)
    out |= {w[w.index("via") + 1] for w in (line.split() for line in r.stdout.splitlines()) if "via" in w}
    sys.path.insert(0, str(ROOT / "sys" / "core"))
    try:
        from aurora import sec_defence, sys_config
        cfg = sys_config.load()
        out |= {str(n) for n in sec_defence.protected(cfg)}
        from urllib.parse import urlparse
        host = urlparse(str(cfg["AURORA_FIREWALL_API_URL"] or "")).hostname
        if host:
            out.add(host)
    except Exception as e:                               # noqa: BLE001 — no .env yet: the machine's own and the gateways
        print(f"  (protected addresses not read: {type(e).__name__})")
    good = []
    for a in sorted(out):
        try:
            net = ipaddress.ip_network(a, strict=False)
        except ValueError:
            continue
        if net.version == 4 and not net.is_loopback:
            good.append(str(net))
    return good


def write_never(nets: list[str]) -> None:
    NEVER.parent.mkdir(parents=True, exist_ok=True)
    NEVER.write_text("# addresses the firewall helper never blocks (sys_root_sync.py)\n" + "\n".join(nets) + "\n")
    _own(NEVER, 0o644)


def main() -> int:
    if os.geteuid() != 0:
        print("run with sudo")
        return 1
    if "--check" in sys.argv:
        print(f"{LIB}: {'present' if LIB.is_dir() else 'missing'}; {NEVER}: {'present' if NEVER.is_file() else 'missing'}")
        return 0
    n = sync_code()
    nets = never_list()
    write_never(nets)
    print(f"  root units' code: {n} files in {LIB} (root:root); never blocked: {len(nets)} addresses in {NEVER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
