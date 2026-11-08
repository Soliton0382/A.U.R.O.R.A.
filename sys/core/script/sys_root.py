#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-root: the one way root acts for Aurora, and it trusts only the code the owner signed (owner, 9 Nov: «chiudere
il problema di root… la semplicità deve restare»).

Aurora's folder is writable by her services' account (she applies the changes the owner approves), so root never runs
it as it is: this launcher runs with the system's Python (-I, never the .venv) from root's own copy of the code,
/usr/local/lib/aurora, reads every file of the code base once, compares it with the owner's signature (Ed25519, the
key in /etc/aurora) and works only on those very bytes: an installer is run from a copy in root's own temporary
folder, the root copy is written from what was signed. What changed since the last signature is listed and the owner
answers «s» to sign it: one command, one question.

    sudo aurora-root                    what is signed, what changed, the root copy
    sudo aurora-root sign               sign what changed (the list first), then root's copy follows
    sudo aurora-root install systemd    the units, polkit, Aurora's sealed key (also: nft, tunnel; tunnel status|remove)
    sudo aurora-root exempt | private-cloud | verify-key | keygen [--rotate]
    sudo aurora-root restore --plan latest | --apply latest [--parts config]   a backup back (C538)
    first time, from Aurora's folder:   sudo /usr/bin/python3 -I sys/core/script/sys_root.py setup

Restarting Aurora from the WebUI is not root's: polkit lets the services' account do it (50-aurora.rules), unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIB = Path("/usr/local/lib/aurora")
CONF = Path("/etc/aurora/root.conf")
SHIM = Path("/usr/local/sbin/aurora-root")
HERE = Path(__file__).resolve()
STEPS = {"systemd": "sys/deploy/systemd", "nft": "sys/deploy/nft", "tunnel": "sys/deploy/cloudflared"}
# what root keeps of the code: the package and the scripts root runs (its units', this launcher's own)
LIB_SCRIPTS = ("sys_nas_mount.py", "sys_backup_retime.py", "sys_cert_perms.py", "sys_ethics_sign.py", "sys_root.py",
               "sys_root_sync.py", "sys_key_seal.py", "sys_restore.py", "sys_env_sync.py")
SHIM_TEXT = f'#!/bin/sh\n# aurora-root (sys/core/script/sys_root.py): root\'s copy, the system\'s Python\nexec /usr/bin/python3 -I {LIB}/sys/core/script/sys_root.py "$@"\n'


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    raise SystemExit(1)


def _root_owned(p: Path) -> bool:
    st = os.lstat(p)
    return st.st_uid == 0 and not st.st_mode & 0o022 and not os.path.islink(p)


def repo() -> Path:
    """Aurora's folder: written down by root at setup when run from root's copy; this file's own at setup."""
    if HERE.is_relative_to(LIB):
        for q in (CONF.parent, CONF):
            if not q.exists() or not _root_owned(q):
                die(f"{q} missing or not root's: run the setup again from Aurora's folder")
        return Path(CONF.read_text(encoding="utf-8").strip())
    return HERE.parents[3]


REPO = repo()
os.environ["INSTALL_ROOT"] = str(REPO)                 # sys_config: the installation's data, never its code
os.environ.setdefault("AURORA_ENV_FILE", str(REPO / ".env"))
os.environ["AURORA_ROOT_LAUNCHER"] = "1"              # sys_ethics_sign: called from here, not run by hand
sys.path.insert(0, str(HERE.parents[1]))               # the package beside this script: root's copy (or the setup's)
sys.path.insert(0, str(HERE.parent))

from aurora import sys_ethics  # noqa: E402


# ---- the code base, read once ----------------------------------------------------------------------------------
def _read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)     # a link in the code base is refused, never followed
    with os.fdopen(fd, "rb") as h:
        return h.read()


def snapshot() -> dict[str, bytes]:
    """Every file the owner signs, its bytes read once: what root signs, checks and runs is this, nothing read later."""
    out, links = {}, []
    for rel in sys_ethics.code_files(REPO):
        p = REPO / rel
        if p.is_symlink() or any((REPO / q).is_symlink() for q in Path(rel).parents if str(q) != "."):
            links.append(rel)
            continue
        out[rel] = _read(p)
    if links:
        die("symbolic links in the code base, refused: " + ", ".join(links[:10]))
    return out


def protected(snap: dict[str, bytes]) -> tuple[str, ...]:
    """The protected files as the code being signed lists them (its sys_ethics.py, read as data), not as root's copy —
    the previous signature — does: a list that grew was signed with the old one, and the services refused to start
    until a second signature (C542, again 9 Nov)."""
    import ast
    try:
        tree = ast.parse(snap["sys/core/aurora/sys_ethics.py"])
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "PROTECTED" for t in node.targets):
                value = ast.literal_eval(node.value)
                if isinstance(value, tuple) and all(isinstance(x, str) for x in value):
                    return value
    except (KeyError, SyntaxError, ValueError):
        pass
    return tuple(sys_ethics.PROTECTED)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _manifest() -> dict:
    try:
        return json.loads(_read(REPO / sys_ethics.MANIFEST))
    except (OSError, ValueError):
        return {}


def drift(snap: dict[str, bytes]) -> dict:
    """{"changed", "added", "removed", "protected": [files], "unsigned": reason or ""} against the owner's signature."""
    public, problem = sys_ethics.owner_public_key()
    m = _manifest()
    if not public:
        return {"unsigned": problem, "changed": [], "added": sorted(snap), "removed": [], "protected": []}
    code = m.get("code") or {}
    ok = bool(code) and sys_ethics._verify(sys_ethics._canonical(code), m.get("code_signature", ""), public) \
        and sys_ethics._verify(sys_ethics._canonical(m.get("files", {})), m.get("signature", ""), public)
    if not ok:
        return {"unsigned": "no valid signature of the owner", "changed": [], "added": sorted(snap), "removed": [],
                "protected": [f for f in sys_ethics.PROTECTED if f in snap]}
    changed = sorted(f for f in snap if f in code and code[f] != _sha(snap[f]))
    added = sorted(f for f in snap if f not in code)
    removed = sorted(f for f in code if f not in snap)
    files = m.get("files") or {}                       # the rules' own list: a protected file added to it, or one changed
    rules = protected(snap)
    newly = sorted(f for f in rules if f not in files or (f in snap and files[f] != _sha(snap[f])))
    prot = sorted(set(f for f in rules if f in changed or f in added or f in removed) | set(newly))
    unsigned = "" if not newly else "the rules' list does not cover every protected file: to sign again"
    return {"unsigned": unsigned, "changed": changed, "added": added, "removed": removed, "protected": prot}


def show(d: dict) -> int:
    rows = [("✏️", f) for f in d["changed"]] + [("➕", f) for f in d["added"]] + [("➖", f) for f in d["removed"]]
    if d["unsigned"]:
        print(f"⚠️ {d['unsigned']}")
    for mark, f in rows[:40]:
        print(f"  {mark} {'🔒 ' if f in d['protected'] else ''}{f}")
    if len(rows) > 40:
        print(f"  … e altri {len(rows) - 40}")
    if d["protected"]:
        print("  🔒 = regole di Aurora (codice etico): senza firma i servizi non partono")
    return len(rows)


def forged_list() -> None:
    """Aurora's own plugins, outside the signature: each with what its contract lets it do (9 Nov: «se aurora si crea
    un plugin "per evadere"…»; «senza che debba ogni volta firmare»): the cage holds them, not the signature."""
    from aurora import agt_forge
    for name in sorted(sys_ethics.forged_plugins(REPO)):
        try:
            m = json.loads(_read(REPO / "sys" / "plugins" / name / "plugin.json"))
        except (OSError, ValueError):
            continue
        print(f"  🔨 {name} (di Aurora, sotto contratto): " + " · ".join(agt_forge.powers(m, "it")[:3]))


def ask(question: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        print(f"{question} — nessuno a cui chiederlo (aggiungi --yes)")
        return False
    return input(f"{question} [s/N] ").strip().lower() in ("s", "si", "sì", "y", "yes")


# ---- writing as root, never through a link ---------------------------------------------------------------------
def _write(path: Path, data: bytes, mode: int, owner: tuple[int, int] | None = None) -> None:
    for q in (path.parent, *path.parent.parents):
        if q.is_symlink():
            die(f"{q} is a symbolic link: refused")
    tmp = path.with_name(f".{path.name}.aurora-root")
    if os.path.lexists(tmp):
        os.unlink(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as h:
        h.write(data)
    os.chmod(tmp, mode)
    if owner and os.geteuid() == 0:
        os.chown(tmp, *owner, follow_symlinks=False)
    os.replace(tmp, path)                               # a rename: a link at `path` is replaced, never followed


def sign(snap: dict[str, bytes], yes: bool = False) -> bool:
    d = drift(snap)
    if not show(d):
        print("✅ tutto il codice è già firmato")
        return True
    if not ask("Firmo questi file?", yes):
        print("niente firmato")
        return False
    import sys_ethics_sign as S
    key = S.load_private(sys_ethics.PRIVATE_KEY)
    trusted, problem = sys_ethics.owner_public_key()
    if S.public_hex(key) != trusted:
        die(problem or "the private key does not match the trusted public key in /etc/aurora")
    rules = protected(snap)
    missing = [f for f in rules if f not in snap]
    if missing:
        die("protected files missing: " + ", ".join(missing))
    files = {f: _sha(snap[f]) for f in rules}
    code = {f: _sha(b) for f, b in snap.items()}
    text = json.dumps({"files": files, "signature": key.sign(sys_ethics._canonical(files)).hex(), "code": code,
                       "code_signature": key.sign(sys_ethics._canonical(code)).hex()}, indent=1) + "\n"
    st = os.stat(REPO)
    _write(REPO / sys_ethics.MANIFEST, text.encode(), 0o644, (st.st_uid, st.st_gid))
    print(f"✅ firmati {len(files)} file protetti e {len(code)} file di codice")
    return True


def sync_lib(snap: dict[str, bytes]) -> int:
    """Root's copy, written from the bytes just checked against the signature; the launcher's command beside it."""
    code = (_manifest().get("code") or {})
    pick = {rel: b for rel, b in snap.items()
            if (rel.startswith("sys/core/aurora/") and rel.endswith(".py"))
            or rel in {f"sys/core/script/{s}" for s in LIB_SCRIPTS}}
    wrong = [rel for rel, b in pick.items() if code.get(rel) != _sha(b)]
    if wrong:
        die("not as signed, root's copy left as it was: " + ", ".join(wrong[:10]))
    new = LIB.with_name("aurora.new")
    if new.exists():
        shutil.rmtree(new)
    for rel, b in pick.items():
        dst = new / rel
        dst.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        dst.write_bytes(b)
        os.chmod(dst, 0o644)
    for p in [new, *new.rglob("*")]:
        if os.geteuid() == 0:
            os.chown(p, 0, 0, follow_symlinks=False)
        if p.is_dir():
            os.chmod(p, 0o755)
    if LIB.exists():
        shutil.rmtree(LIB)
    new.rename(LIB)
    CONF.parent.mkdir(mode=0o755, exist_ok=True)
    _write(CONF, f"{REPO}\n".encode(), 0o644, (0, 0))
    _write(SHIM, SHIM_TEXT.encode(), 0o755, (0, 0))
    try:                                                # the addresses root's firewall helper never blocks (C420)
        import sys_root_sync
        sys_root_sync.write_never(sys_root_sync.never_list())
    except Exception as e:  # noqa: BLE001 — the copy is made; the list said apart
        print(f"  (elenco degli indirizzi mai bloccati non scritto: {e})")
    return len(pick)


def install(step: str, extra: list[str], yes: bool) -> int:
    if step not in STEPS:
        die(f"install: one of {', '.join(STEPS)}")
    snap = snapshot()
    d = drift(snap)
    if d["changed"] or d["added"] or d["removed"] or d["unsigned"]:
        print("Prima di installare, il codice cambiato dall'ultima firma:")
        if not sign(snap, yes):
            return 1
    print(f"  copia di root: {sync_lib(snap)} file")
    folder = STEPS[step] + "/"
    work = Path(tempfile.mkdtemp(prefix="aurora-root-"))
    try:
        for rel, b in snap.items():
            if rel.startswith(folder):
                dst = work / rel[len(folder):]
                dst.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                dst.write_bytes(b)
                os.chmod(dst, 0o755 if b.startswith(b"#!") else 0o644)
        if not (work / "install.sh").exists():
            die(f"{folder}install.sh not in the signed code")
        env = {**os.environ, "INSTALL_ROOT": str(REPO), "AURORA_DEPLOY": str(work), "AURORA_LIB": str(LIB)}
        return subprocess.run(["bash", str(work / "install.sh"), *extra], env=env, cwd="/").returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


def status() -> int:
    snap = snapshot()
    d = drift(snap)
    ok, reason = sys_ethics.integrity(REPO)
    print(f"Aurora: {REPO}")
    print(f"regole (codice etico): {'✅' if ok else '✗'} {reason}")
    n = show(d)
    print("codice: " + ("✅ tutto come firmato" if not n else f"{n} file da firmare (sudo aurora-root sign)"))
    print("plugin scritti da Aurora (fuori dalla firma, li tiene il loro contratto):")
    forged_list()
    print(f"copia di root: {'✅ ' + str(LIB) if LIB.is_dir() else '✗ assente'}; comando: "
          f"{'✅ ' + str(SHIM) if SHIM.exists() else '✗ assente'}")
    return 0


def main(argv: list[str]) -> int:
    yes = "--yes" in argv
    args = [a for a in argv if a != "--yes"]
    action = args[0] if args else "status"
    if action in ("status", "check"):
        return status()
    if os.geteuid() != 0:
        die("con sudo: la chiave del proprietario è di root (sudo aurora-root …)")
    if action == "setup":
        import sys_ethics_sign as S
        if not sys_ethics.PRIVATE_KEY.exists():
            S.keygen(sys_ethics.PRIVATE_KEY, False)
        snap = snapshot()
        if not sign(snap, yes):
            return 1
        print(f"  copia di root: {sync_lib(snap)} file; da ora: sudo aurora-root …")
        if "--exempt" in args:                         # the installer's choice: this machine exempt from level B
            sys.argv = ["sys_ethics_sign.py", "exempt"]
            return S.main()
        return 0
    if action == "sign":
        snap = snapshot()
        if not sign(snap, yes):
            return 1
        print(f"  copia di root: {sync_lib(snap)} file")
        return 0
    if action == "install":
        if len(args) < 2:
            die("install: systemd, nft or tunnel")
        return install(args[1], args[2:], yes)
    if action == "restore":                             # C538: root's copy of the restore, the system's Python, data only
        script = LIB / "sys" / "core" / "script" / "sys_restore.py"
        if not script.is_file():
            die("root's copy has no restore yet: sudo aurora-root sign first")
        return subprocess.run(["/usr/bin/python3", "-I", str(script), *args[1:]], cwd=str(REPO),
                              env={**os.environ, "INSTALL_ROOT": str(REPO)}).returncode
    if action in ("exempt", "private-cloud", "verify-key", "keygen"):
        import sys_ethics_sign as S
        sys.argv = ["sys_ethics_sign.py", *args]
        return S.main()
    die(f"unknown: {action} (status, sign, install, restore, exempt, private-cloud, verify-key, keygen, setup)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
