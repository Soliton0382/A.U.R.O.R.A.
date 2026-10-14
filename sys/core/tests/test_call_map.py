# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The call map read from the code (owner, 15 Oct: «devi sapere esattamente cosa fa ogni script, da cosa viene
chiamato»; C323): every file named in MODULE_MAP, the routers and drivers loaded by name counted as used, the owner's
own extensions never in the public map."""
import importlib.util
from pathlib import Path

F = Path(__file__).resolve().parents[1] / "script" / "doc_callmap.py"
spec = importlib.util.spec_from_file_location("doc_callmap", F)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_every_file_is_in_the_module_map():
    assert M.unmapped() == []


def test_loaded_by_name_counts_as_used_and_local_never_shows():
    mods, by = M.lib_imports(M.code_files())
    assert "aurora.api.oauth" in by and "aurora.fw_drivers.sophos" in by
    assert not any(".local" in m or m.endswith("local") for m in mods)
    text = M.render()
    assert "local." not in text and "/local/" not in text
