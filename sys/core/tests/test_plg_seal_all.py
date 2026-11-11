# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C591 follow-up: the installer fetches plugins' files as the owner; the services' account then seals each installed
tree that has no seal yet (plg_install_all --seal), so a fresh installation's plugins start."""
import importlib.util
import json
from pathlib import Path

from aurora import plg_deps, sys_config

SCRIPT = Path(__file__).resolve().parents[1] / "script" / "plg_install_all.py"


def test_only_installed_unsealed_trees_are_sealed(tmp_path, cfg, monkeypatch):
    spec = importlib.util.spec_from_file_location("pia", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "plugin.json").write_text(json.dumps({"name": name}))
    monkeypatch.setattr(m, "PLUGINS", tmp_path)
    monkeypatch.setattr(sys_config, "load", lambda *a, **k: cfg)
    states = {"a": {"wanted": True, "installed": True}, "b": {"wanted": True, "installed": False},
              "c": {"wanted": False, "installed": False}}
    monkeypatch.setattr(plg_deps, "state", lambda folder, man: states[folder.name])
    monkeypatch.setattr(plg_deps, "seal_file", lambda c, folder: folder / "no-such-seal")
    sealed = []
    monkeypatch.setattr(plg_deps, "record", lambda c, folder: sealed.append(folder.name))
    assert m.seal_all() == 0 and sealed == ["a"]
