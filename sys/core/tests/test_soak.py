# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C389: the API's memory, given back."""
import pytest


def test_the_api_gives_back_the_memory_glibc_holds_every_half_hour(monkeypatch):
    """C389: malloc_trim every TRIM_S from aurora-rem's tick, its MiB in the log; never more often."""
    import sys as _sys
    from aurora.sys_config import ConfigError
    try:
        from aurora.api import core
    except ConfigError:                                   # the API loads the configuration: none here (publish's run)
        pytest.skip("no configuration to load the API with")
    monkeypatch.setattr(core, "_trimmed", [0.0])
    first = core.trim_memory(now=10_000.0)
    assert first is None if not _sys.platform.startswith("linux") else isinstance(first, int)
    assert core.trim_memory(now=10_000.0 + core.TRIM_S - 1) is None          # not again within half an hour
    assert core._trimmed[0] == 10_000.0
