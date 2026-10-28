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
from pathlib import Path

from . import sys_config

REDACTED = "redacted"


def _declared(manifest: dict) -> set[str]:
    return set(manifest.get("env", [])) | set(manifest.get("env_as", {})) | set(manifest.get("requires", []))


def env_file(name: str, manifest: dict, cfg: sys_config.Config) -> Path:
    specs = {s["key"]: s for s in sys_config.load_schema()["settings"]}
    # the effective values of the plugin's user (the machine's, their own settings, their folders: U3), else the file
    raw = dict(cfg.raw) or sys_config.parse_env(cfg.env_file.read_text(encoding="utf-8"), str(cfg.env_file))
    mine = _declared(manifest)
    lines = []
    for k, v in raw.items():
        if specs.get(k, {}).get("secret") and k not in mine:
            v = REDACTED if v else ""
        lines.append(f"{k}={v}")
    d = cfg.path("AURORA_STATUS_DIR") / "plugins" / "env"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
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
    if home != Path("/"):
        args += ["--tmpfs", str(home)]
    if (home != Path("/") and root.is_relative_to(home)) or root.is_relative_to("/tmp"):
        args += ["--ro-bind", str(root), str(root)]
    for python in sorted({Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve()}):
        if home != Path("/") and python.is_relative_to(home) and not python.is_relative_to(root):
            args += ["--ro-bind", str(python), str(python)]
    args += ["--ro-bind", str(filtered_env), str(cfg.env_file)]
    # /run hidden (C420: docker, libvirt, the system D-Bus and the firewall helper's sockets were reachable from a
    # plugin), the resolver's folder put back for the plugins with a network (/etc/resolv.conf points there)
    args += ["--tmpfs", "/run"]
    if Path("/run/systemd/resolve").is_dir():
        args += ["--ro-bind", "/run/systemd/resolve", "/run/systemd/resolve"]
    # the machine's keys and tokens, never a plugin's (C420): the SSH key for the computers, the tunnel's token, the
    # cloud accounts and the Claude logins, the cameras' keys, the HTTPS key, the phone app's signing keys
    for hidden in (status / "keys", status / "cloudflare", status / "cloud_accounts", status / "claude_code",
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
    for key in manifest.get("sandbox", {}).get("write", []):
        p = cfg.path(key)
        # a user's folder only: with the machine's configuration (no user: the tools listed at start) the path is
        # usr/<x> itself, not anyone's — never made (owner, 28 Oct: «dentro usr ci sono cartelle che non dovrebbero
        # esserci»: nine empty ones, made at a start)
        if usr is not None and p.parent == usr and not p.exists():
            continue
        p.mkdir(parents=True, exist_ok=True)
        args += ["--bind", str(p), str(p)]
    net = manifest.get("sandbox", {}).get("network")
    if net is False or net == "local":
        args += ["--unshare-net"]                               # no network at all (forged plugins): nothing leaves
    if net == "local":                                          # the local model only, through a socket (plg_modelnet)
        from . import plg_modelnet
        sock, port = plg_modelnet.bridge(cfg)
        cmd = plg_modelnet.wrap(cmd, sock, port)
    args += ["--ro-bind", str(folder), str(folder)]           # the plugin's own code, wherever it lives
    args += ["--setenv", "AURORA_IN_SANDBOX", "1"]              # programs inside may rely on this cage (doc_pdf)
    return args + ["--chdir", str(folder), "--"] + cmd
