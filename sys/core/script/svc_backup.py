# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-backup: the owner's data to another disk, encrypted (aurora/sys_backup.py). Run by its systemd timer
(AURORA_BACKUP_TIME), or by hand:

    python sys/core/script/svc_backup.py init                   # once: the key and its recovery code
    python sys/core/script/svc_backup.py run                    # one backup now (what the timer runs)
    python sys/core/script/svc_backup.py list                   # the snapshots kept
    python sys/core/script/svc_backup.py verify [--full]        # decrypt and check a sample (or every blob)
    python sys/core/script/svc_backup.py restore --to DIR [--snapshot S] [--only sys/vault] [--code RECOVERY]

The result goes to the API's activity feed: the owner is notified of a failure (and of a success if he asks).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sys_backup, sys_config, sys_log  # noqa: E402


def tell(cfg, event: str, payload: dict) -> None:
    """The API's activity feed (toast, push): a backup that fails must never go unnoticed."""
    try:
        httpx.post(f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}/v1/aurora/activity",
                   headers={"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"},
                   json={"source": "backup", "event": event, "payload": payload}, timeout=15)
    except httpx.HTTPError:
        pass                                           # the log has it; the health shows the age of the last backup


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["init", "run", "list", "verify", "restore"])
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--to", type=Path)
    ap.add_argument("--snapshot", default="latest")
    ap.add_argument("--only", default="", help="restore only paths starting with this (e.g. sys/vault)")
    ap.add_argument("--code", default="", help="the recovery code, when the key file is lost")
    a = ap.parse_args()
    cfg = sys_config.get()
    log = sys_log.get_logger("backup")
    try:
        if a.action == "init":
            code = sys_backup.init_key(cfg)
            print("Backup key made:", sys_backup.key_path(cfg))
            print("\nRECOVERY CODE — write it down outside this computer (password manager, paper).")
            print("Without it, if this disk is lost, no backup can be read:\n")
            print("   ", code, "\n")
            return 0
        if a.action == "run":
            out = sys_backup.run(cfg)
            tell(cfg, "backup.done", {"text": f"{out['files']} file, {out['bytes'] / 1e9:.1f} GB "
                                      f"({out['bytes_written'] / 1e9:.2f} GB nuovi) in {out['seconds']:.0f} s", **out})
            print(json.dumps(out))
            return 0
        if a.action == "list":
            st = sys_backup.status(cfg)
            print(json.dumps(st, indent=1))
            return 0
        if a.action == "verify":
            n = sys_backup.verify(cfg, sample=None if a.full else 20)
            print(f"ok: {n} blobs decrypted and checked")
            return 0
        if a.action == "restore":
            if not a.to:
                ap.error("restore needs --to DIR (an empty folder)")
            print(json.dumps(sys_backup.restore(cfg, a.to, a.snapshot, a.only, a.code)))
            return 0
    except sys_backup.BackupError as e:
        log.error("backup %s failed: %s", a.action, e)
        if a.action == "run":
            tell(cfg, "backup.failed", {"text": str(e)[:180]})
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:                             # an unexpected failure is told too, then raised
        log.exception("backup %s failed", a.action)
        if a.action == "run":
            tell(cfg, "backup.failed", {"text": f"{type(e).__name__}: {str(e)[:150]}"})
        raise
    return 2


if __name__ == "__main__":
    sys.exit(main())
