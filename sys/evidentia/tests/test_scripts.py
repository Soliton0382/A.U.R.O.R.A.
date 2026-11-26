# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The scripts' guards from the audit of 11 Nov: the model's pin (B30), the readers' memory and output caps (B31),
the thermal guard's choice of processes (B33), the unit's quoting (B34) and the removal of the units of before (B32)."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from evidentia import inventory

CORE = Path(__file__).resolve().parents[1]
SCRIPTS = CORE / "script"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- B30: the model is loaded only if it is the pinned one

def _model_folder(tmp_path: Path) -> tuple[Path, Path]:
    """A small fake model folder and a pin file that matches it."""
    fetch = _load("fetch_model")
    models = tmp_path / "models"
    (models / "m" / "1_Pooling").mkdir(parents=True)
    (models / "m" / "config.json").write_text('{"a": 1}')
    (models / "m" / "model.safetensors").write_bytes(b"\0" * 1000)
    (models / "m" / "1_Pooling" / "config.json").write_text("{}")
    (models / "m" / "MODEL.json").write_text("{}")                      # the downloader's record: never pinned
    (models / "m" / ".cache" / "x").mkdir(parents=True)
    (models / "m" / ".cache" / "x" / "f.lock").write_text("")
    pins = tmp_path / "models.json"
    pins.write_text(json.dumps({"_comment": "test", "m": {"repo": "t/m", "revision": "abc", "files": fetch.listing(models / "m")}}))
    return models, pins


def test_the_pinned_model_is_accepted_and_every_change_is_refused(tmp_path):
    fetch = _load("fetch_model")
    models, pins = _model_folder(tmp_path)
    assert fetch.check("m", models, pins) == models / "m"
    assert set(json.loads(pins.read_text())["m"]["files"]) == {"config.json", "model.safetensors", "1_Pooling/config.json"}
    (models / "m" / "model.safetensors").write_bytes(b"\0" * 999 + b"\1")       # same size, other bytes
    with pytest.raises(fetch.ModelMismatch, match="changed: model.safetensors"):
        fetch.check("m", models, pins)
    (models / "m" / "model.safetensors").write_bytes(b"\0" * 1000)
    (models / "m" / "extra.py").write_text("print(1)")                           # a file that was not there
    with pytest.raises(fetch.ModelMismatch, match="not pinned: extra.py"):
        fetch.check("m", models, pins)
    (models / "m" / "extra.py").unlink()
    (models / "m" / "1_Pooling" / "config.json").unlink()
    with pytest.raises(fetch.ModelMismatch, match="missing: 1_Pooling/config.json"):
        fetch.check("m", models, pins)
    with pytest.raises(fetch.ModelMismatch, match="not pinned"):               # a model with no pin is never loaded
        fetch.check("other", models, pins)
    with pytest.raises(fetch.ModelMismatch, match="not pinned"):
        fetch.check("m", models, tmp_path / "absent.json")


def test_the_installed_embedding_model_matches_its_pin():
    """The real pin (sys/evidentia/config/models.json) against the real folder, when it is installed: ~1 s (1.26 GB)."""
    fetch = _load("fetch_model")
    models = CORE.parents[1] / "sys" / "models"
    if not (models / "embeddinggemma-300m" / "config.json").exists():
        pytest.skip("embeddinggemma-300m not installed here")
    pin = fetch.pins()["embeddinggemma-300m"]
    assert len(pin["revision"]) == 40 and "model.safetensors" in pin["files"]
    assert fetch.check("embeddinggemma-300m", models) == models / "embeddinggemma-300m"


def test_fetch_model_downloads_the_pinned_revision_and_refuses_a_wrong_download(tmp_path, monkeypatch):
    fetch = _load("fetch_model")
    models, pins = _model_folder(tmp_path)
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    monkeypatch.setattr(fetch, "PINS", pins)
    good = tmp_path / "good"
    shutil.copytree(models / "m", good)
    shutil.rmtree(models / "m")
    calls = []

    def fake_hf(cmd, text):                                           # «hf download»: copies the fixture into place
        calls.append(cmd)
        shutil.copytree(good, Path(cmd[cmd.index("--local-dir") + 1]), dirs_exist_ok=True)
        if "--tamper" in cmd:
            (Path(cmd[cmd.index("--local-dir") + 1]) / "config.json").write_text('{"a": 2}')
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(fetch.subprocess, "run", fake_hf)
    (good / "MODEL.json").unlink()
    assert fetch.main("t/m") == 0
    assert calls[0][calls[0].index("--revision") + 1] == "abc"                  # exactly the pinned revision
    assert json.loads((tmp_path / "sys" / "models" / "m" / "MODEL.json").read_text())["files"]["config.json"]["bytes"] == 8
    assert fetch.main("t/m") == 0                                                # already there and the pinned one
    assert len(calls) == 1
    shutil.rmtree(tmp_path / "sys" / "models" / "m")
    monkeypatch.setattr(fetch.subprocess, "run", lambda cmd, text: fake_hf(cmd + ["--tamper"], text))
    assert fetch.main("t/m") == 1                                                # a changed download: refused
    assert not (tmp_path / "sys" / "models" / "m" / "MODEL.json").exists()


# ---------------------------------------------------------------- B31: the readers' memory and output are capped

PY = sys.executable


def test_a_reader_flooding_stdout_is_cut_at_the_cap_and_killed():
    with pytest.raises(ValueError, match="more than"):
        inventory.run_capped([PY, "-c", "import sys\nwhile True: sys.stdout.buffer.write(b'x' * 65536)"],
                             timeout=30, mem=1 << 30, cap=1 << 20)
    assert not subprocess.run(["pgrep", "-f", "sys.stdout.buffer.write"], capture_output=True).stdout


def test_a_reader_beyond_its_memory_cap_fails_alone():
    r = inventory.run_capped([PY, "-c", "bytearray(900 << 20); print('allocated')"], timeout=60, mem=512 << 20)
    assert r.returncode != 0 and b"MemoryError" in r.stderr and b"allocated" not in r.stdout
    r = inventory.run_capped([PY, "-c", "bytearray(100 << 20); print('allocated')"], timeout=60, mem=1 << 30)
    assert r.returncode == 0 and r.stdout == b"allocated\n"


def test_a_reader_that_hangs_is_killed_at_the_timeout():
    with pytest.raises(subprocess.TimeoutExpired):
        inventory.run_capped([PY, "-c", "import time; time.sleep(30)"], timeout=0.5, mem=1 << 30)
    assert not subprocess.run(["pgrep", "-f", "time.sleep\\(30\\)"], capture_output=True).stdout


def test_a_noisy_stderr_never_blocks_the_reader():
    r = inventory.run_capped([PY, "-c", "import sys\nsys.stderr.write('e' * 300000)\nsys.stdout.write('ok')"],
                             timeout=30, mem=1 << 30)
    assert r.returncode == 0 and r.stdout == b"ok" and len(r.stderr) <= inventory.ERR_CAP


def test_a_pdf_beyond_the_output_cap_becomes_the_documents_error(pdfs, monkeypatch):
    monkeypatch.setattr(inventory, "OUT_CAP", 16)
    out = inventory.read_doc(str(pdfs / "ABCD00000001.pdf"))
    assert "pages" not in out and out["error"].startswith("ValueError: pdftotext wrote more than")
    monkeypatch.setattr(inventory, "OUT_CAP", 64 << 20)
    assert len(inventory.read_doc(str(pdfs / "ABCD00000001.pdf"))["pages"]) == 2


def test_the_caps_are_above_the_corpus_ceilings():
    """Measured 11 Nov on the archive's extremes: pdftotext 17.8 MB of text, 90 MB virtual; tesseract 476 MB virtual."""
    assert inventory.OUT_CAP >= 3 * 17_809_326
    assert inventory.PDF_MEM >= 4 * 90 * 2**20 and inventory.OCR_MEM >= 4 * 476 * 2**20


# ---------------------------------------------------------------- B33: the guard pauses the job, not an editor

def test_the_thermal_guard_matches_the_script_python_runs_not_a_substring():
    th = _load("evd_thermal")
    gpu = th.JOBS["gpu"]
    assert th.runs(b"/x/.venv/bin/python\0/x/sys/evidentia/script/evd_embed.py\0", gpu)
    assert th.runs(b"python3.14\0-I\0-u\0/x/sys/evidentia/script/evd_embed.py\0--check\0", gpu)
    assert th.runs(b"python3\0-W\0ignore\0/x/evd_embed.py\0", gpu)
    assert not th.runs(b"vim\0/x/sys/evidentia/script/evd_embed.py\0", gpu)                 # an editor on the file
    assert not th.runs(b"/usr/bin/code\0--file\0/x/evd_embed.py\0", gpu)
    assert not th.runs(b"python3\0-m\0pytest\0tests/test_evd_embed.py\0", gpu)         # a module, not the script
    assert not th.runs(b"python3\0-c\0open('evd_embed.py')\0", gpu)
    assert not th.runs(b"python3\0/x/evd_inventory.py\0--note\0evd_embed.py\0", gpu)    # the script is argv[1]
    assert th.runs(b"python3\0/x/evd_inventory.py\0--note\0evd_embed.py\0", th.JOBS["cpu"])
    assert not th.runs(b"bash\0-c\0python evd_embed.py\0", gpu)
    assert not th.runs(b"", gpu) and not th.runs(b"python3\0", gpu)


# ---------------------------------------------------------------- B34: a space or a % in the project's path

def test_the_unit_quotes_the_root_and_doubles_the_percent(tmp_path):
    root = _load("evd_root")
    text = root.unit_text(Path("/srv/my proj/100%"))
    lines = dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#"))
    assert lines["WorkingDirectory"] == "/srv/my proj/100%%"
    assert lines["ExecStart"] == '"/srv/my proj/100%%/.venv/bin/python" "/srv/my proj/100%%/sys/evidentia/script/svc_api.py"'
    assert lines["BindReadOnlyPaths"] == '"/srv/my proj/100%%"'
    assert lines["BindPaths"] == ('"/srv/my proj/100%%/sys/data" "/srv/my proj/100%%/sys/status" '
                                  '"/srv/my proj/100%%/sys/logs"')
    assert "%" not in text.replace("%%", "")                                  # no lone % left for the specifiers
    assert root.unit_path('/a"b\\c$d', True) == '"/a\\"b\\\\c$$d"' and root.unit_path("/a$d") == '"/a$d"'
    plain = root.unit_text(Path("/opt/evidentia"))                             # the usual path: the same words, quoted
    assert 'ExecStart="/opt/evidentia/.venv/bin/python" "/opt/evidentia/sys/evidentia/script/svc_api.py"' in plain
    assert root.UNIT_TEXT == root.unit_text(root.ROOT)


def test_systemd_reads_the_quoted_unit_back(tmp_path):
    """systemd-analyze verify on the rendered unit: the path with a space and a % is one argument, not a syntax error."""
    if not shutil.which("systemd-analyze"):
        pytest.skip("no systemd-analyze")
    root = _load("evd_root")
    proj = tmp_path / "my proj 100%"                       # a real project tree there: verify checks the command exists
    (proj / ".venv" / "bin").mkdir(parents=True)
    (proj / ".venv" / "bin" / "python").symlink_to(sys.executable)
    (proj / "sys" / "evidentia" / "script").mkdir(parents=True)
    (proj / "sys" / "evidentia" / "script" / "svc_api.py").write_text("")
    unit = tmp_path / "evidentia-api.service"
    unit.write_text(root.unit_text(proj), encoding="utf-8")
    r = subprocess.run(["systemd-analyze", "verify", "--man=no", "--generators=no", str(unit)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and not r.stderr.strip(), r.stderr   # the old text: «Command /…/my is not executable»,
    # «BindPaths= path is not absolute, ignoring: proj 100%/sys/data» (seen 11 Nov on the unquoted form)


# ---------------------------------------------------------------- B32: V8's MCP unit removed by the migration step

def test_the_old_units_are_removed_once_dry_run_only_prints(tmp_path, monkeypatch, capsys):
    root = _load("evd_root")
    units = tmp_path / "system"
    units.mkdir()
    for name in ("investigatore-api.service", "investigatore-mcp.service", "evidentia-api.service"):
        (units / name).write_text("[Unit]\n")
    monkeypatch.setattr(root, "ROOT", tmp_path)
    (tmp_path / "sys" / "status").mkdir(parents=True)
    (tmp_path / "sys" / "status" / "investigatore.sock").write_text("")
    calls = []
    monkeypatch.setattr(root.subprocess, "run", lambda cmd, check=True: calls.append(list(cmd)))
    monkeypatch.setattr(root, "DRY", True)
    assert root.remove_old_units(units) == ["investigatore-api.service", "investigatore-mcp.service"]
    assert calls == [] and (units / "investigatore-mcp.service").exists()           # dry: nothing done
    printed = capsys.readouterr().out
    assert "systemctl disable --now investigatore-mcp.service" in printed and "daemon-reload" in printed
    monkeypatch.setattr(root, "DRY", False)
    assert root.remove_old_units(units) == ["investigatore-api.service", "investigatore-mcp.service"]
    assert ["systemctl", "disable", "--now", "investigatore-mcp.service"] in calls
    assert ["systemctl", "disable", "--now", "investigatore-api.service"] in calls
    assert ["systemctl", "daemon-reload"] in calls
    assert sorted(p.name for p in units.iterdir()) == ["evidentia-api.service"]      # the new unit untouched
    assert not (tmp_path / "sys" / "status" / "investigatore.sock").exists()
    assert capsys.readouterr().out.count("0. the unit of before investigatore-mcp.service") == 1
    calls.clear()
    assert root.remove_old_units(units) == [] and calls == []                        # idempotent: a second run is silent
    assert capsys.readouterr().out == ""
