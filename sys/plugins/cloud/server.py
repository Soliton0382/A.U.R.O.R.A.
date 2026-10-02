# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "cloud": the cloud AI providers Aurora may use (keys in its settings), read only.
Which model does each step is chosen in the 🧠 Models page (mdl_router); here: which providers are ready, and each
provider's own list of models."""
from __future__ import annotations

from aurora import mdl_router, sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("cloud", version="1.0")


@server.tool()
def cloud_providers() -> str:
    """The cloud providers and whether each has its key (no key is ever shown)."""
    rows = []
    for k, v in mdl_router.PROVIDERS.items():
        ready = v["kind"] in ("local", "claude_code") or bool(cfg.values.get(v.get("key", "")))
        rows.append(f"{'✅' if ready else '⚪'} {v['label']} ({k})" + ("" if ready else f": manca {v['key']}"))
    return "\n".join(rows)


@server.tool()
def cloud_models(provider: str) -> str:
    """The models a provider offers now (its own list), e.g. provider="google" or "xai"."""
    try:
        names = mdl_router.list_models(provider, cfg)
    except Exception as e:                       # noqa: BLE001 - a wrong key is an answer, not a crash
        return f"ERRORE: {type(e).__name__}: {str(e)[:300]}"
    return f"{len(names)} modelli di {provider}:\n" + "\n".join(names[:200])


if __name__ == "__main__":
    server.run("stdio")
