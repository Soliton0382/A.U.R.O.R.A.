# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""CI, 12 Nov (after C592): `./install.sh --yes` stopped at «Firmo questi file? — nessuno a cui chiederlo»: the owner's
--yes did not reach the account's own root step. It goes through every step now; without it the owner is asked."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "script"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"t_{name}", SCRIPT / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_owners_yes_reaches_the_accounts_root_steps(monkeypatch):
    R = _load("sys_root")
    ran = []
    monkeypatch.setattr(R, "_signed_run", lambda cmd, yes: ran.append((cmd, yes)) or 0)
    monkeypatch.setattr(R, "SHIM", Path("/nonexistent-shim"))
    monkeypatch.setattr(R.os, "geteuid", lambda: 0)
    R.main(["account", "--yes"])
    R.main(["account"])
    assert ran[0][0][-1] == "--yes" and ran[0][1] is True
    assert "--yes" not in ran[1][0] and ran[1][1] is False
    S = _load("sys_service_account")
    calls = []
    monkeypatch.setattr(S, "step", lambda text, fn=None, *a: calls.append(a))
    monkeypatch.setattr(S.sys, "argv", ["x", "--yes"])
    S.services("someone")
    assert any(a and a[-1] == "--yes" and "systemd" in a for a in calls)
    install = (Path(__file__).resolve().parents[3] / "install.sh").read_text()
    assert 'aurora-root account $([ "$YES" = 1 ] && echo --yes)' in install
