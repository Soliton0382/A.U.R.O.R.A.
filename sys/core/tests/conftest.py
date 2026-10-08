# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Every test runs in its own temporary root with a .env built from the settings schema."""
from pathlib import Path

import pytest

from aurora import sys_config, sys_log


def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write_env(root: Path, **overrides: str) -> Path:
    schema = sys_config.load_schema()
    values = {s["key"]: s["recommended"] for s in schema["settings"]}
    values["AURORA_ROOT"] = str(root)
    # the test installation's services on ports nothing listens on: never this machine's own Aurora (C208 — the
    # suite reached the live aurora-models on 9710, so a test passed here and failed on a fresh machine, and its
    # embeddings ran on the owner's GPU)
    for key in ("AURORA_API_PORT", "AURORA_MODELS_PORT", "AURORA_LLM_PORT"):
        values[key] = str(_free_port())
    for s in schema["settings"]:
        if s.get("secret"):
            values[s["key"]] = "test-secret-" + s["key"].lower()
    values.update(overrides)
    env = root / ".env"
    env.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return env


def private(path) -> bool:
    """Only its owner may read it: mode 600 here. The Mac and Windows ports ask their system (sys_platform.is_private:
    an ACL on Windows, where a file's mode says nothing of who may read it — a real Windows, 8 Oct 2026)."""
    import stat
    return stat.S_IMODE(Path(path).stat().st_mode) == 0o600


@pytest.fixture
def cfg(tmp_path: Path) -> sys_config.Config:
    config = sys_config.load(write_env(tmp_path), check_root=False)
    sys_log.configure(config)
    return config
