# SPDX-License-Identifier: Apache-2.0
"""Plugin "cloud": the configured cloud AI providers, with this month's usage and cost from Aurora's records."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("cloud", version="1.0")

# Canonical provider names and the aliases that may appear in settings keys or usage records.
ALIASES = {
    "openai": "openai", "anthropic": "anthropic", "claude": "anthropic",
    "gemini": "gemini", "google": "gemini", "mistral": "mistral", "groq": "groq",
    "openrouter": "openrouter", "deepseek": "deepseek", "together": "together",
    "xai": "xai", "grok": "xai", "cohere": "cohere", "perplexity": "perplexity",
    "azure": "azure", "bedrock": "bedrock", "fireworks": "fireworks",
}
LOCAL = {"local", "llama", "llama.cpp", "llamacpp", "aurora", "ollama", "none", ""}
COST_KEYS = ("cost", "cost_eur", "cost_usd", "eur", "usd", "price", "spend")
TOKEN_KEYS = ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens", "tokens", "total_tokens")
PROV_KEYS = ("provider", "vendor", "backend", "service")


def _canon(name: str) -> str:
    """Map a provider name to its canonical form."""
    n = str(name).strip().lower()
    for alias, canon in ALIASES.items():
        if n == alias or n.startswith(alias):
            return canon
    return n


def _pairs(text: str) -> dict:
    """Parse 'a=1;b=2' (also comma separated) into a dict keyed by canonical provider."""
    out = {}
    for part in re.split(r"[;,\n]", text or ""):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip():
                out[_canon(k)] = v.strip()
    return out


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _when(v) -> float:
    """Epoch seconds from an epoch number or an ISO timestamp; 0 if unknown."""
    if isinstance(v, (int, float)):
        return float(v) / (1000 if v > 1e12 else 1)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _is_usage(d: dict) -> bool:
    return any(k in d for k in COST_KEYS + TOKEN_KEYS + ("requests", "calls"))


def _add(acc: dict, prov: str, d: dict) -> None:
    """Add one usage record to the accumulator."""
    p = _canon(prov)
    if p in LOCAL:
        return
    a = acc.setdefault(p, {"costo": 0.0, "token": 0, "richieste": 0, "ts": 0.0})
    a["costo"] += sum(_num(d.get(k)) for k in COST_KEYS)
    a["token"] += int(sum(_num(d.get(k)) for k in TOKEN_KEYS if k != "total_tokens")
                      or _num(d.get("total_tokens")))
    a["richieste"] += int(_num(d.get("requests") or d.get("calls") or 1))
    for k in ("at", "ts", "time", "timestamp", "updated"):
        if k in d:
            a["ts"] = max(a["ts"], _when(d[k]))


def _walk(node, acc: dict, hint: str = "") -> None:
    """Find usage records in any JSON shape: records with a provider field, or dicts keyed by provider."""
    if isinstance(node, list):
        for x in node:
            _walk(x, acc, hint)
    elif isinstance(node, dict):
        prov = next((node[k] for k in PROV_KEYS if isinstance(node.get(k), str)), "")
        if (prov or hint) and _is_usage(node):
            _add(acc, prov or hint, node)
            return
        for k, v in node.items():
            child_hint = k if _canon(k) in ALIASES.values() else hint
            _walk(v, acc, child_hint)


def _keyed_providers(values: dict) -> set:
    """Providers that have a non-empty key or token in the settings (the value is never read out)."""
    found = set()
    for k, v in values.items():
        ku = k.upper()
        if not v or not re.search(r"(API_?KEY|TOKEN|SECRET)$", ku):
            continue
        for alias, canon in ALIASES.items():
            if alias.upper() in ku:
                found.add(canon)
    return found


@server.tool()
def cloud_providers() -> str:
    """Cloud AI providers configured by the owner as JSON text: name, plan, this month's usage and cost, budget, last update."""
    try:
        values = sys_config.get().values
        budgets = _pairs(values.get("AURORA_CLOUD_BUDGETS", ""))
        plans = _pairs(values.get("AURORA_CLOUD_PLANS", ""))
        month = datetime.now().strftime("%Y%m")
        acc: dict = {}
        files_read = 0
        udir = Path(cfg.path("AURORA_STATUS_DIR")) / "usage"
        if udir.is_dir():
            for f in sorted(udir.glob(month + "*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                except (OSError, ValueError):
                    continue
                files_read += 1
                before = {p: a["ts"] for p, a in acc.items()}
                _walk(data, acc)
                mt = f.stat().st_mtime
                for p, a in acc.items():  # file time as fallback for the last update
                    if a["ts"] == 0 or p not in before:
                        a["ts"] = max(a["ts"], mt) if a["ts"] == 0 else a["ts"]
        names = set(acc) | _keyed_providers(values) | set(budgets) | set(plans)
        names -= LOCAL
        if not names:
            return "Nessun fornitore di AI cloud configurato (nessuna chiave nelle impostazioni, nessun uso registrato questo mese)."
        out = []
        for p in sorted(names):
            a = acc.get(p, {"costo": 0.0, "token": 0, "richieste": 0, "ts": 0.0})
            b = _num(budgets.get(p)) if p in budgets else None
            row = {
                "nome": p,
                "piano": plans.get(p, "non indicato"),
                "uso_periodo": {"richieste": a["richieste"] if p in acc else 0, "token": a["token"]},
                "costo_periodo": round(a["costo"], 4),
                "limite_budget": b,
                "budget_usato_pct": round(100 * a["costo"] / b, 1) if b else None,
                "ultimo_aggiornamento": (datetime.fromtimestamp(a["ts"], timezone.utc).astimezone()
                                         .isoformat(timespec="seconds") if a["ts"] else None),
            }
            out.append(row)
        return json.dumps({
            "periodo": datetime.now().strftime("%Y-%m"),
            "file_uso_letti": files_read,
            "fornitori": out,
            "nota": "Costi stimati dai registri d'uso di Aurora; il saldo ufficiale è sul sito del fornitore.",
        }, ensure_ascii=False, indent=1)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")
