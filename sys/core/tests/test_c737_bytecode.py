# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C737: a .pyc left next to a signed source is never what the services run."""
import os
import py_compile
import subprocess
import sys
from pathlib import Path

ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": "/nonexistent/aurora-pycache"}


def _plant(tmp_path: Path) -> Path:
    """mod.py says «signed»; its __pycache__ holds a .pyc of «planted» whose header matches the source (same mtime
    and size), as code running as the service could leave it."""
    src = tmp_path / "mod.py"
    src.write_text("WHO = 'planted'\n", encoding="utf-8")
    # next to the source, whatever prefix the test itself runs under (publish.sh sets one: the pyc went there)
    pyc = tmp_path / "__pycache__" / f"mod.{sys.implementation.cache_tag}.pyc"
    py_compile.compile(str(src), cfile=str(pyc), doraise=True)   # the planted text's bytecode
    st = src.stat()
    src.write_text("WHO = 'signed!'\n", encoding="utf-8")         # same size as the planted line
    os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns))
    return src


def _who(tmp_path: Path, env: dict) -> str:
    run = subprocess.run([sys.executable, "-c", "import mod; print(mod.WHO)"], cwd=tmp_path, capture_output=True,
                         text=True, env={**{k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}, **env})
    return run.stdout.strip()


def test_c737_a_planted_pyc_runs_without_the_units_environment(tmp_path):
    _plant(tmp_path)
    assert _who(tmp_path, {}) == "planted"                        # the hole: Python trusts a header that matches


def test_c737_with_the_units_environment_the_signed_source_runs(tmp_path):
    _plant(tmp_path)
    assert _who(tmp_path, ENV) == "signed!"


def test_c737_every_unit_of_the_services_account_carries_it():
    text = (Path(__file__).resolve().parents[1] / "script" / "sys_install_services.py").read_text(encoding="utf-8")
    assert text.count("\nUser=$user\nEnvironment=PYTHONDONTWRITEBYTECODE=1\n"
                      "Environment=PYTHONPYCACHEPREFIX=/nonexistent/aurora-pycache\n") == text.count("\nUser=$user\n") == 4
