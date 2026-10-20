# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C372: a plugin's call made from inside a running event loop (an async endpoint, before the background listing was
over) runs in a thread of its own instead of failing «asyncio.run() cannot be called from a running event loop»."""
import asyncio

import pytest

from aurora.plg_host import PluginHost


def host():
    h = PluginHost.__new__(PluginHost)
    h.cfg = {"AURORA_PLUGIN_TIMEOUT_S": 5}
    return h


async def answer(x):
    await asyncio.sleep(0)
    return x


async def broken():
    raise ValueError("the plugin's own error")


def test_outside_and_inside_a_running_loop():
    h = host()
    assert h._run(answer(7)) == 7                                  # a plain thread: as before

    async def endpoint():                                          # an async endpoint asks for a plugin
        return h._run(answer(8))
    assert asyncio.run(endpoint()) == 8

    async def failing():
        return h._run(broken())
    with pytest.raises(ValueError, match="own error"):              # its error given back, not swallowed
        asyncio.run(failing())
