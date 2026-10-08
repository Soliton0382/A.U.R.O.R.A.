# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The reference backend against the real Linux machine, where there is one: what it says must be what Aurora's own
code sees today (systemctl, nvidia-smi, /etc/machine-id). The same file in both port folders."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import sys_platform
from aurora.sys_platform.base import parse_nvidia

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="the reference is checked on Linux")


@linux_only
def test_the_reference_sees_the_services_as_systemd_does():
    p = sys_platform.current()
    assert p.name == "linux"
    for unit in ("aurora-api", "aurora-llm"):
        truth = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True).stdout.strip()
        if truth in ("active", "inactive", "failed"):
            assert p.service_state(unit) == truth
    assert p.service_state("aurora-no-such-unit") == "missing"


@linux_only
def test_the_reference_reads_the_gpus_and_the_machine_id():
    p = sys_platform.current()
    if shutil.which("nvidia-smi"):
        n = len(subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout.strip().splitlines())
        assert len(p.gpus()) == n and p.accelerator() == "cuda"
    if Path("/etc/machine-id").is_file():
        assert p.machine_id() == Path("/etc/machine-id").read_text().strip()


def test_nvidia_lines_with_values_not_measured():
    g = parse_nvidia("0, NVIDIA RTX A4000, 12, 9600, 16376, 54, 90\n1, Tesla P4, [N/A], 2400, 7680, [Not Supported], [N/A]\n")
    assert (g[0].util, g[0].temp_limit) == (12.0, 90.0) and (g[1].util, g[1].temp, g[1].temp_limit) == (None, None, None)


def test_an_unknown_system_is_an_error_never_a_linux_fall_back():
    with pytest.raises(RuntimeError):
        sys_platform.for_system("freebsd13")

