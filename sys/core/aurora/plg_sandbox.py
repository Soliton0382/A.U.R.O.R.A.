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
            writable only the folders the manifest names in "sandbox": {"write":
            [settings]} (e.g. AURORA_PROJECTS_DIR). Network and devices stay (connectors talk to services,
            the senses use the camera). Dies with Aurora.
"""
from __future__ import annotations

import os
import shutil
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


def wrap(cmd: list[str], folder: Path, manifest: dict, filtered_env: Path, cfg: sys_config.Config) -> list[str]:
    root = cfg.root
    status = cfg.path("AURORA_STATUS_DIR")
    home = Path(os.environ.get("HOME") or Path.home())
    args = ["bwrap", "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
            "--unshare-cgroup-try", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp"]
    if home != Path("/") and root.is_relative_to(home):
        args += ["--tmpfs", str(home), "--ro-bind", str(root), str(root)]
    args += ["--ro-bind", str(filtered_env), str(cfg.env_file)]
    for hidden in (status / "push", status / "plugins" / "env"):
        if hidden.is_dir():
            args += ["--tmpfs", str(hidden)]
    if (status / "devices.json").exists():
        args += ["--ro-bind", "/dev/null", str(status / "devices.json")]
    for key in manifest.get("sandbox", {}).get("write", []):
        p = cfg.path(key)
        p.mkdir(parents=True, exist_ok=True)
        args += ["--bind", str(p), str(p)]
    if manifest.get("sandbox", {}).get("network") is False:
        args += ["--unshare-net"]                               # no network at all (forged plugins): nothing leaves
    args += ["--ro-bind", str(folder), str(folder)]           # the plugin's own code, wherever it lives
    args += ["--setenv", "AURORA_IN_SANDBOX", "1"]              # programs inside may rely on this cage (doc_pdf)
    return args + ["--chdir", str(folder), "--"] + cmd
