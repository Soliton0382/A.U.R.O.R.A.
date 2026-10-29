# SPDX-License-Identifier: Apache-2.0
"""Plugin "ntfy": sends push notifications to the owner's phone via ntfy and reads the latest ones."""
from __future__ import annotations

import json
from datetime import datetime

import httpx
from aurora import sys_config
from mcp.server.mcpserver import MCPServer

server = MCPServer("ntfy", version="1.0")

DEFAULT_URL = "https://ntfy.sh"
MAX_BYTES = 4000          # ntfy truncates message bodies above 4096 bytes
DISCLOSURE = "— Messaggio generato da Aurora (IA)"


def _settings() -> tuple[str, str, str, str]:
    """Read the settings at call time; return (url, topic, token, missing_key)."""
    values = sys_config.get().values
    url = (values.get("AURORA_NTFY_URL", "") or DEFAULT_URL).strip().rstrip("/")
    topic = (values.get("AURORA_NTFY_TOPIC", "") or "").strip()
    token = (values.get("AURORA_NTFY_TOKEN", "") or "").strip()
    missing = "" if topic else "AURORA_NTFY_TOPIC"
    return url, topic, token, missing


def _headers(token: str) -> dict:
    """Authorization header only when a token is configured."""
    return {"Authorization": f"Bearer {token}"} if token else {}


def _trim(text: str) -> str:
    """Keep the body under ntfy's size limit without breaking UTF-8 characters."""
    raw = text.encode("utf-8")
    if len(raw) <= MAX_BYTES:
        return text
    return raw[:MAX_BYTES].decode("utf-8", errors="ignore").rstrip() + "…"


@server.tool()
def ntfy_send(message: str, title: str = "", priority: int = 3, tags: str = "") -> str:
    """Send a push notification to the owner's phone (title optional, priority 1-5, tags comma-separated); waits for approval."""
    try:
        url, topic, token, missing = _settings()
        if missing:
            return f"Non configurato: manca {missing} (Plugin → ntfy)"
        body = (message or "").strip()
        if not body:
            return "Niente da inviare: il messaggio è vuoto."
        body = _trim(body + "\n\n" + DISCLOSURE)
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        if "robot" not in tag_list:
            tag_list.append("robot")     # visible AI marker in the app
        payload = {
            "topic": topic,
            "message": body,
            "title": (title or "Aurora").strip()[:200],
            "priority": max(1, min(5, int(priority))),
            "tags": tag_list,
        }
        # JSON publishing keeps titles and text in UTF-8 (headers would be ASCII only)
        r = httpx.post(url, json=payload, headers=_headers(token), timeout=20)
        if r.status_code in (401, 403):
            return "Invio rifiutato dal server ntfy: controlla AURORA_NTFY_TOKEN (Plugin → ntfy)."
        if r.status_code == 429:
            return "Invio rifiutato: troppi messaggi, il server ntfy chiede di attendere."
        if r.status_code >= 400:
            return f"Invio non riuscito: il server ntfy ha risposto {r.status_code} {r.text[:200]}"
        msg_id = ""
        try:
            msg_id = r.json().get("id", "")
        except Exception:
            pass
        return f"Notifica inviata sul canale ntfy ({len(body)} caratteri){' id ' + msg_id if msg_id else ''}."
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def ntfy_recent(hours: float = 24, limit: int = 10) -> str:
    """List the latest notifications on the configured ntfy topic over the last hours (time, title, text)."""
    try:
        url, topic, token, missing = _settings()
        if missing:
            return f"Non configurato: manca {missing} (Plugin → ntfy)"
        seconds = max(60, int(float(hours) * 3600))
        r = httpx.get(f"{url}/{topic}/json",
                      params={"poll": "1", "since": f"{seconds}s"},
                      headers=_headers(token), timeout=20)
        if r.status_code in (401, 403):
            return "Lettura rifiutata dal server ntfy: controlla AURORA_NTFY_TOKEN (Plugin → ntfy)."
        if r.status_code >= 400:
            return f"Lettura non riuscita: il server ntfy ha risposto {r.status_code}."
        items = []
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") != "message":
                continue
            items.append(ev)
        if not items:
            return f"Nessuna notifica sul canale nelle ultime {hours:g} ore (server {url})."
        items.sort(key=lambda e: e.get("time", 0), reverse=True)
        out = [f"Notifiche nelle ultime {hours:g} ore: {len(items)} (le più recenti {min(len(items), limit)})"]
        for ev in items[:max(1, int(limit))]:
            when = datetime.fromtimestamp(int(ev.get("time", 0))).astimezone().strftime("%d/%m %H:%M")
            title = ev.get("title") or "(senza titolo)"
            text = (ev.get("message") or "").replace("\n", " ")
            if len(text) > 160:
                text = text[:160] + "…"
            out.append(f"- {when} · {title}: {text}")
        return "\n".join(out)
    except Exception as e:
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")
