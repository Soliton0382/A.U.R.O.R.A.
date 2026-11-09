# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What a plugin process can see: its own secrets only, and a filesystem it cannot use against Aurora.

env_file()  a .env for one plugin: every ordinary setting, but only the secrets its manifest declares
            ("env", "env_as", "requires"); every other secret reads "redacted". Without it a plugin, which
            loads the configuration like any module of Aurora, would read every key and token of the owner.
wrap()      the plugin's command inside bubblewrap (AURORA_PLUGIN_SANDBOX): the system read-only, the home
            hidden (a private tmpfs), Aurora's folder read-only with its .env replaced by the filtered one,
            the push keys, the registered devices and the other plugins' env files hidden, private /tmp,
            own PID/IPC/UTS namespaces; with "sandbox": {"network": false} no network at all (forged plugins);
            with "network": "local" none either, but the local model reached through a socket (plg_modelnet);
            writable only the folders the manifest names in "sandbox": {"write":
            [settings]} (e.g. AURORA_PROJECTS_DIR). Network and devices stay (connectors talk to services,
            the senses use the camera). Dies with Aurora.
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path

from . import sys_config

REDACTED = "redacted"
# a plugin Aurora wrote herself (manifest "forged", agt_forge) — owner, 9 Nov: «se aurora si crea un plugin "per
# evadere" e io firmo lei diventa indipendente»: whatever its manifest says, at every start it writes only here, reads
# only its own secrets, and reaches the network only through plg_netproxy
FORGED_WRITE = {"AURORA_PROJECTS_DIR"}


def read_paths(manifest: dict, cfg: sys_config.Config) -> list[Path]:
    """The few places outside Aurora a plugin may read (its «sandbox.read»: an MCP server of the owner's that lives
    elsewhere — its program, its code, its socket; owner, 10 Nov). Never for a forged plugin; never the root, the home or
    a folder above it, a hidden place (.ssh, .gnupg…) or Aurora's own state. ValueError says which and why."""
    if forged(manifest):
        return []
    home = Path(os.environ.get("HOME") or Path.home()).resolve()
    status = cfg.path("AURORA_STATUS_DIR").resolve()
    out = []
    for raw in manifest.get("sandbox", {}).get("read", []):
        p = Path(str(raw))
        if not p.is_absolute():
            raise ValueError(f"{raw}: an absolute path is needed")
        p = p.resolve()
        if p == Path("/") or p == home or home.is_relative_to(p):
            raise ValueError(f"{raw}: the root, the home or a folder above it is never readable")
        if any(part.startswith(".") and part not in (".venv",) for part in p.parts):
            raise ValueError(f"{raw}: a hidden place is never readable")
        if p.is_relative_to(status):
            raise ValueError(f"{raw}: Aurora's own state is never readable")
        if any(p.is_relative_to(n) or n.is_relative_to(p) for n in NEVER_READ):
            raise ValueError(f"{raw}: the system's own places (/proc, /run, /dev, /sys, the credentials) are never readable")
        if not p.exists():
            raise ValueError(f"{raw}: does not exist")
        out.append(p)
    return out


def _homes() -> list[Path]:
    """The folders people's homes live in: /home and /root (a home elsewhere is the service's HOME, hidden apart)."""
    return [p for p in (Path("/home"), Path("/root")) if p.is_dir()]


NEVER_READ = (Path("/proc"), Path("/sys"), Path("/dev"), Path("/run"), Path("/etc/credstore"),
              Path("/etc/credstore.encrypted"), Path("/boot"))   # the kernel's and the machine's secrets (audit, 10 Nov)


def forged(manifest: dict) -> bool:
    return bool(manifest.get("forged"))


def _declared(manifest: dict) -> set[str]:
    keys = set(manifest.get("env", [])) | set(manifest.get("env_as", {})) | set(manifest.get("requires", []))
    if forged(manifest):                               # its own settings only (AURORA_<NAME>_…), never another's secret
        name = str(manifest.get("name", ""))           # nor a key Aurora's core or another plugin has (audit 9 Nov)
        prefix, theirs = f"AURORA_{name.upper()}_", sys_config.others_keys(name)
        keys = {k for k in keys if k.startswith(prefix) and k not in theirs}
    return keys


_scrubbed: set[str] = set()


def _scrub(d: Path) -> None:
    """Once per process: the env files written before C463 held a plugin's secrets in clear; each call writes its own
    again, so one older than an hour is nobody's now and goes (a plugin starting this minute keeps its file)."""
    if str(d) in _scrubbed:
        return
    _scrubbed.add(str(d))
    old = time.time() - 3600
    for f in d.glob("*.env"):
        try:
            if f.stat().st_mtime < old:
                f.unlink()
        except OSError:
            pass


def env_file(name: str, manifest: dict, cfg: sys_config.Config) -> Path:
    specs = {s["key"]: s for s in sys_config.load_schema()["settings"]}
    # the effective values of the plugin's user (the machine's, their own settings, their folders: U3), else the file
    raw = dict(cfg.raw) or sys_config.parse_env(cfg.env_file.read_text(encoding="utf-8"), str(cfg.env_file))
    mine = _declared(manifest)
    lines = []
    for k, v in raw.items():
        if specs.get(k, {}).get("secret") and k not in mine:
            v = REDACTED if v else ""
        elif specs.get(k, {}).get("secret") and v:     # its own: named here, the value in its environment (C463)
            v = sys_config.ENV_REF + k
        lines.append(f"{k}={v}")
    d = cfg.path("AURORA_STATUS_DIR") / "plugins" / "env"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    _scrub(d)
    f = d / (f"{name}.{cfg.user}.env" if cfg.user else f"{name}.env")      # one per user: never each other's
    # a temporary file of this call only: two calls of the same plugin at once (the tool lists at start) collided
    # on one shared name and one failed (C115)
    tmp = f.with_name(f"{f.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, f)
    return f


def available() -> bool:
    return shutil.which("bwrap") is not None


def _others_hidden(cfg: sys_config.Config) -> list[str]:
    """Multi-user: a plugin working for a user sees nothing of the others (their usr/<name>/, memory, index, state),
    nor the users store, nor its own user's whole .env (it gets its filtered one); the owner's top-level folders of
    usr/ (his papers) only for the admin's plugins."""
    from . import sys_users_layout as L
    base = cfg.base or cfg
    m = L.migrated(base)
    if not m:
        return []
    me, admin, out = cfg.user or m["admin"], m["admin"], []
    usr = L.usr(base)
    for d in (x for x in usr.iterdir() if x.is_dir()) if usr.is_dir() else []:
        if d.name != me and not (me == admin and d.name not in L._registered(base) | {admin}):
            out += ["--tmpfs", str(d)]
    for area in L.SYS_AREAS:
        users = L.root(base, area) / L.USERS
        for d in (x for x in users.iterdir() if x.is_dir()) if users.is_dir() else []:
            if d.name != me:
                out += ["--tmpfs", str(d)]
    for secret in (base.path("AURORA_STATUS_DIR") / "users.db", usr / me / ".env"):
        if secret.exists():
            out += ["--ro-bind", "/dev/null", str(secret)]
    own = L.place(base, "state", me) / "keys"            # its own user's keys too (N64): they open the user's memory
    if own.is_dir():
        out += ["--tmpfs", str(own)]
    return out


def _devices(manifest: dict) -> bool:
    """The host's devices only for a plugin that says it needs them (a camera, the GPU, sound): the others get a
    minimal /dev, no shared /dev/shm (C420)."""
    return bool(manifest.get("sandbox", {}).get("devices"))


def wrap(cmd: list[str], folder: Path, manifest: dict, filtered_env: Path, cfg: sys_config.Config) -> list[str]:
    root = cfg.root
    status = cfg.path("AURORA_STATUS_DIR")
    home = Path(os.environ.get("HOME") or Path.home())
    args = ["bwrap", "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
            "--unshare-cgroup-try", "--ro-bind", "/", "/", "--dev-bind" if _devices(manifest) else "--dev", "/dev",
            *(["/dev"] if _devices(manifest) else []), "--proc", "/proc",
            "--tmpfs", "/tmp"]
    # the home hidden wherever Aurora is (C204, 8 Oct 2026: with Aurora outside the home — /opt, /srv — a plugin read
    # the whole home, ~/.ssh included; the ports' probe found it); Aurora's folder visible again when it is inside
    # the home or under /tmp (the tests), and the Python the venv runs on when it lives in the home (pyenv, uv)
    # /home and /root hidden too, not only the service's own HOME (audit, 10 Nov: the service's HOME is inside Aurora,
    # and a cage read the owner's own home through its open folders — documents, VPN profiles); Aurora's folder and
    # the Python it runs on bound again when they live there, the service's HOME hidden again after
    homes = [h for h in _homes() if h != Path("/")]
    if home != Path("/"):
        homes.append(home)
    for h in homes:
        args += ["--tmpfs", str(h)]
    if any(root.is_relative_to(h) for h in homes) or root.is_relative_to("/tmp"):
        args += ["--ro-bind", str(root), str(root)]
    for python in sorted({Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve()}):
        if any(python.is_relative_to(h) for h in homes) and not python.is_relative_to(root):
            args += ["--ro-bind", str(python), str(python)]
    if home != Path("/") and home.is_relative_to(root):
        args += ["--tmpfs", str(home)]
    args += ["--ro-bind", str(filtered_env), str(cfg.env_file)]
    # /run hidden (C420: docker, libvirt, the system D-Bus and the firewall helper's sockets were reachable from a
    # plugin), the resolver's folder put back for the plugins with a network (/etc/resolv.conf points there)
    args += ["--tmpfs", "/run"]
    if Path("/run/systemd/resolve").is_dir():
        args += ["--ro-bind", "/run/systemd/resolve", "/run/systemd/resolve"]
    # the machine's keys and tokens, never a plugin's (C420): the SSH key for the computers, the tunnel's token, the
    # cloud accounts and the Claude logins, the cameras' keys, the HTTPS key, the phone app's signing keys
    for hidden in (status / "keys", status / "cloudflare", status / "cloud_accounts", status / "claude_code", status / "caddy",
                   root / "sys" / "https" / "cert", root / "sys" / "app" / "keys"):
        if hidden.is_dir():
            args += ["--tmpfs", str(hidden)]
    for f in (status / "camera_keys.json", status / "cloud_accounts.json"):
        if f.is_file():
            args += ["--ro-bind", "/dev/null", str(f)]
    for hidden in (status / "push", status / "plugins" / "env"):
        if hidden.is_dir():
            args += ["--tmpfs", str(hidden)]
    if (status / "devices.json").exists():
        args += ["--ro-bind", "/dev/null", str(status / "devices.json")]
    args += _others_hidden(cfg)
    from . import sys_users_layout as L
    usr = L.usr(cfg) if L.migrated(cfg) else None
    writes = manifest.get("sandbox", {}).get("write", [])
    if forged(manifest):                               # never Aurora's code, settings, approvals or other plugins
        writes = [k for k in writes if k in FORGED_WRITE]
    for key in writes:
        p = cfg.path(key)
        # a user's folder only: with the machine's configuration (no user: the tools listed at start) the path is
        # usr/<x> itself, not anyone's — never made (owner, 28 Oct: «dentro usr ci sono cartelle che non dovrebbero
        # esserci»: nine empty ones, made at a start)
        if usr is not None and p.parent == usr and not p.exists():
            continue
        p.mkdir(parents=True, exist_ok=True)
        args += ["--bind", str(p), str(p)]
    net = manifest.get("sandbox", {}).get("network")
    if forged(manifest) and net not in (False, "local"):
        net = "proxy"                                           # a forged plugin: the owner's places only (plg_netproxy)
    bridges = status / "plugins" / "bridge"
    bridges.mkdir(parents=True, exist_ok=True)                  # hidden even for the first cage (audit 9 Nov)
    if bridges.is_dir():                                        # the other plugins' ways out hidden; its own bound below
        args += ["--tmpfs", str(bridges)]
    if net is False or net in ("local", "proxy"):
        args += ["--unshare-net"]                               # no network of its own: nothing leaves by itself
    from . import plg_modelnet
    if net == "local":                                          # the local model only, through a socket (plg_modelnet)
        sock, port = plg_modelnet.bridge(cfg)
        args += ["--ro-bind", str(sock), str(sock)]
        cmd = plg_modelnet.wrap(cmd, sock, port)
    if net == "proxy":
        from . import plg_netproxy
        sock, port = plg_netproxy.bridge(str(manifest.get("name", folder.name)), manifest, cfg)
        args += ["--ro-bind", str(sock), str(sock), *plg_netproxy.environment(port)]
        cmd = plg_modelnet.wrap(cmd, sock, port)
    for extra in read_paths(manifest, cfg):                    # an MCP server living elsewhere: what it reads (10 Nov)
        args += ["--ro-bind", str(extra), str(extra)]
    args += ["--ro-bind", str(folder), str(folder)]           # the plugin's own code, wherever it lives
    args += ["--setenv", "AURORA_IN_SANDBOX", "1"]              # programs inside may rely on this cage (doc_pdf)
    return args + ["--chdir", str(folder), "--"] + cmd
