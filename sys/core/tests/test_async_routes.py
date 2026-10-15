# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C334: an async route that lists the plugins in the event loop (plugin_host().get() lists every plugin's tools)
makes asyncio.run fail for each of them; the failure is kept 10 minutes and every plugin shows as broken. Listing
the plugins goes in a thread (in_thread, asyncio.to_thread)."""
import ast
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "aurora"
LISTS = {"get", "plugins", "keep_watching", "_ha", "_ready", "_on", "platforms", "investigate"}


def in_loop(fn: ast.AsyncFunctionDef):
    def scan(node, nested=False):
        for ch in ast.iter_child_nodes(node):
            inner = nested or isinstance(ch, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef))
            if isinstance(ch, ast.Call) and not nested:
                f = ch.func
                host = isinstance(f, ast.Attribute) and isinstance(f.value, ast.Call) and \
                    getattr(f.value.func, "id", "") == "plugin_host"
                with_tools = not any(k.arg == "with_tools" for k in ch.keywords)
                if host and f.attr in ("get", "plugins") and with_tools:
                    yield ch.lineno, f"plugin_host().{f.attr}()"
                elif getattr(f, "id", None) in LISTS - {"get", "plugins"}:
                    yield ch.lineno, f.id
            yield from scan(ch, inner)
    yield from scan(fn)


def test_no_async_route_lists_the_plugins_in_the_event_loop():
    found = []
    for f in sorted(API.glob("api/*.py")) + sorted(API.glob("local/api_*.py")):
        for fn in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(fn, ast.AsyncFunctionDef):
                found += [f"{f.name}:{n} {fn.name} → {what}" for n, what in in_loop(fn)]
    assert found == []
