# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner signs Aurora's code of conduct (sys/core/aurora/sys_ethics.py).

Every installation has its own key pair in /etc/aurora, made here as root: the private half
(owner_ed25519, 0600 root) never exists in the user's folders, the public half (owner_ed25519.pub,
0644 root) is what the services trust. Nothing of the key is in the repository.

    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py setup [--exempt]  # installer: key pair + sign (+ exempt)
    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py sign             # after changing a protected file
    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py exempt           # exempt THIS installation from level B
    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py keygen --rotate  # new key pair (the old one is kept aside)
    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py verify-key       # is the private key the trusted one?
    .venv/bin/python sys/core/script/sys_ethics_sign.py check                 # what the services check at start
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config, sys_ethics  # noqa: E402


def give_back(path: Path) -> None:
    """Run with sudo, a file would belong to root and the services could not read it: hand it back to the
    owner of the installation."""
    if os.geteuid() == 0:
        st = sys_ethics.CODE_ROOT.stat()
        os.chown(path, st.st_uid, st.st_gid)


def load_private(path: Path):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def public_hex(key) -> str:
    from cryptography.hazmat.primitives import serialization
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def keygen(private: Path, rotate: bool) -> None:
    """A new key pair: private 0600 root, public 0644 root, folder 0755 root."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    public = private.with_name(private.name + ".pub")
    if private.exists() or public.exists():
        if not rotate:
            raise SystemExit(f"{private} exists: never overwrite a key (use --rotate for a new pair)")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for f in (private, public):
            if f.exists():
                f.rename(f.with_name(f"{f.name}.retired-{stamp}"))    # kept aside, never deleted here
    private.parent.mkdir(parents=True, exist_ok=True)
    os.chown(private.parent, 0, 0)
    os.chmod(private.parent, 0o755)
    key = Ed25519PrivateKey.generate()
    fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    fd = os.open(public, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(public_hex(key) + "\n")
    for f in (private, public):
        os.chown(f, 0, 0)
    os.chmod(public, 0o644)
    print(f"new key pair: {private} (root only), {public} (public {public_hex(key)[:16]}…)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["setup", "keygen", "sign", "exempt", "check", "verify-key"])
    ap.add_argument("--key", type=Path, default=sys_ethics.PRIVATE_KEY, help="the private key (PEM)")
    ap.add_argument("--rotate", action="store_true", help="keygen: replace an existing key pair (kept aside)")
    ap.add_argument("--exempt", action="store_true", help="setup: also exempt this installation from level B")
    args = ap.parse_args()
    root = sys_ethics.CODE_ROOT
    if args.action == "check":
        ok, reason = sys_ethics.integrity()
        print(("OK: " if ok else "FAILED: ") + reason)
        drift = sys_ethics.drift_summary(sys_ethics.code_drift())
        print("code: " + (drift or "every file as signed"))
        return 0 if ok else 1
    if os.geteuid() != 0:
        ap.error("run with sudo: the key lives in /etc/aurora and only root may use it")
    if args.action == "keygen" or (args.action == "setup" and not args.key.exists()):
        keygen(args.key, args.rotate)
        if args.action == "keygen":
            return 0
    key = load_private(args.key)
    trusted, problem = sys_ethics.owner_public_key()
    if public_hex(key) != trusted:
        ap.error(problem or "this private key does not match the trusted public key in /etc/aurora")
    if args.action == "verify-key":
        print(f"OK: {args.key} is the owner's key (public {public_hex(key)[:16]}…)")
        return 0
    if args.action in ("sign", "setup"):
        files = {f: sys_ethics._sha(root / f) for f in sys_ethics.PROTECTED}
        sig = key.sign(sys_ethics._canonical(files)).hex()
        code = {f: sys_ethics._sha(root / f) for f in sys_ethics.code_files(root)}
        code_sig = key.sign(sys_ethics._canonical(code)).hex()
        (root / sys_ethics.MANIFEST).write_text(json.dumps({"files": files, "signature": sig, "code": code,
                                                            "code_signature": code_sig}, indent=1) + "\n")
        give_back(root / sys_ethics.MANIFEST)
        print(f"signed {len(files)} protected files and {len(code)} code files -> {sys_ethics.MANIFEST}")
    if args.action == "exempt" or (args.action == "setup" and args.exempt):
        cfg = sys_config.get()
        target = cfg.path("AURORA_ETHICS_EXEMPTION")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key.sign(sys_ethics.exemption_message(cfg.root)).hex())
        give_back(target)
        print(f"level B exemption for this machine written to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
