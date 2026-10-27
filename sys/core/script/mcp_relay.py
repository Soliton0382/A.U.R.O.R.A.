# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The one MCP server a project's conductor sees on the Claude CLI (prj_act, ROADMAP N39 step 3): a relay with no
logic of its own. It speaks MCP over stdin/stdout (JSON-RPC, a message per line) and hands every tools/list and
tools/call to Aurora's API with the run's token (CONDUCTOR_RELAY_URL, CONDUCTOR_RELAY_TOKEN); the API checks each
path, runs commands in the project's cage, masks what goes back. Standard library only: started with python -I.
"""
import json
import os
import sys
import urllib.error
import urllib.request

URL, TOKEN = os.environ.get("CONDUCTOR_RELAY_URL", ""), os.environ.get("CONDUCTOR_RELAY_TOKEN", "")


def api(path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(URL + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"X-Aurora-Conductor": TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"text": f"ERROR: Aurora refused ({e.code}): {e.read().decode(errors='replace')[:300]}", "error": True}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"text": f"ERROR: Aurora not reachable: {e}", "error": True}


def answer(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:                                       # a notification (initialized, cancelled): no answer
        return None
    if method == "initialize":
        result = {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-06-18"),
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "aurora", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": api("/tools").get("tools", [])}
    elif method == "tools/call":
        p = msg.get("params") or {}
        r = api("/call", {"name": p.get("name"), "arguments": p.get("arguments") or {}})
        result = {"content": [{"type": "text", "text": str(r.get("text", ""))}], "isError": bool(r.get("error"))}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> None:
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        out = answer(msg)
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
