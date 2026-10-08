# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The installer's cloud questions (a machine without a local reasoner): the models a provider offers with this key,
and one small call through Aurora's own client to prove that key and model work before anything is installed.

    AURORA_INSTALL_CLOUD_KEY=... python sys/core/script/sys_cloud_setup.py models anthropic        # one per line, suggested first
    AURORA_INSTALL_CLOUD_KEY=... python sys/core/script/sys_cloud_setup.py try anthropic <model>   # "ok", or the provider's error
    AURORA_INSTALL_CLOUD_URL=http://server:8000/v1 ... models custom    # any OpenAI-compatible service

The key is read from the environment, never from the command line (a command line is visible to every user). Model
names come from the provider's own list (GET /models), never typed from memory; the suggestion is only an order.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# not chat models: pictures, sound, embeddings, moderation, old completions
NOT_CHAT = re.compile(r"audio|realtime|transcribe|tts|image|dall|whisper|embed|moderation|search|instruct|babbage|"
                      r"davinci|computer|aqa|live|veo|imagen|guard|banana|lyria|robotics|imagine|video|omni|"
                      r"antigravity|customtools|multi-agent", re.I)
# the suggested family: a balanced model under a stable name (an alias, not a dated snapshot)
PREFER = {"anthropic": r"sonnet", "claude_code": r"^sonnet$", "openai": r"^gpt-[\d.]+$", "google": r"^gemini-pro-latest$",
          "mistral": r"^mistral-large-latest$", "xai": r"^grok-[\d.]+$", "openrouter": r"^anthropic/claude.*sonnet"}


def _cfg(provider: str, key: str):
    """A throw-away configuration (the schema's values, a temporary root) holding only this key."""
    import secrets
    from aurora import mdl_router, sys_config
    spec = mdl_router.PROVIDERS[provider]
    root = Path(tempfile.mkdtemp(prefix="aurora-cloud-setup-"))
    values = {s["key"]: s["recommended"] for s in sys_config.load_schema()["settings"]}
    values.update({s["key"]: secrets.token_urlsafe(16) for s in sys_config.load_schema()["settings"]
                   if s.get("generate") == "token"})
    values["AURORA_ROOT"] = str(root)
    if spec.get("key"):
        values[spec["key"]] = key
    if spec.get("base_key"):                             # custom: its address, by the environment too
        values[spec["base_key"]] = os.environ.get("AURORA_INSTALL_CLOUD_URL", "").strip().rstrip("/")
    env = root / ".env"
    env.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    env.chmod(0o600)                                     # it holds the key
    cfg = sys_config.load(env, check_root=False)
    # the installer asks before any .env exists: whatever reads the configuration (the log first) reads this one
    from aurora import sys_log
    sys_config._cached = cfg
    sys_log.configure(cfg)
    return cfg


def _natural(s: str) -> list:
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def suggest(provider: str, ids: list[str], keep_order: bool = False) -> list[str]:
    """The chat models, the suggested one first (newest of the preferred family), then the rest, newest first."""
    chat = [i for i in ids if not NOT_CHAT.search(i)]
    if not keep_order:                                   # anthropic lists newest first already
        chat = sorted(chat, key=_natural, reverse=True)
    pick = [i for i in chat if re.search(PREFER.get(provider, "$^"), i)]
    return ([pick[0]] if pick else []) + [i for i in chat if not pick or i != pick[0]]


def models(provider: str, key: str) -> list[str]:
    from aurora import mdl_router
    cfg = _cfg(provider, key)
    if provider == "anthropic":                         # its own order: newest first (list_models sorts by name)
        import httpx
        r = httpx.get(f"{mdl_router.PROVIDERS['anthropic']['base']}/models", params={"limit": 100}, timeout=30,
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
        r.raise_for_status()
        return suggest(provider, [m["id"] for m in r.json().get("data", [])], keep_order=True)
    return suggest(provider, mdl_router.list_models(provider, cfg))


def attempt(provider: str, key: str, model: str) -> str:
    """One small call through the client Aurora will use: "ok", or why not."""
    from aurora import mdl_router
    cfg = _cfg(provider, key)
    client = mdl_router.cloud_client(provider, model, cfg)
    if client is None:
        return "no model given"
    out = client.complete("Answer with one word.", "Say: ok", 16)
    return "ok" if out.answer.strip() else "empty answer"


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in ("models", "try"):
        print(__doc__)
        return 2
    action, provider = sys.argv[1], sys.argv[2]
    key = os.environ.get("AURORA_INSTALL_CLOUD_KEY", "")
    try:
        if action == "models":
            ids = models(provider, key)
            print("\n".join(ids))
            return 0 if ids else 1
        out = attempt(provider, key, sys.argv[3] if len(sys.argv) > 3 else "")
        print(out)
        return 0 if out == "ok" else 1
    except Exception as e:                               # noqa: BLE001 - the installer shows the reason and asks again
        msg = str(e).replace(key, "***") if key else str(e)
        print(f"{type(e).__name__}: {msg[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
