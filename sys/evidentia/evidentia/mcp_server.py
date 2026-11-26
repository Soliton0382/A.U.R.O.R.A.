# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia as an MCP server for the agents (the sniper, the lead hunter, the verifier): read-only tools on the
archive, every answer with its source. Run on stdio by the client that orchestrates (Aurora's MCP servers, 10 Nov).

It holds no data and opens no database: each tool is one request to Evidentia's API on its unix socket
(the unit evidentia-api). Whoever runs it — Aurora's account — reaches only that socket, never the archive's files.

The agents (owner, 10 Nov: defined in the server, run by the client): every active card is an MCP prompt — the
client's model gets the shared rules, the agent's instructions and the goal. A client may propose a new agent; it
stays a proposal until the owner approves it."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import quote

import httpx
from mcp.server.mcpserver import MCPServer

SOCK = os.environ.get("EVD_SOCKET") or "/var/lib/evidentia-api/evidentia.sock"   # the installed service (aurora-root install evidentia)
server = MCPServer("evidentia", version="0.2")
logging.getLogger("httpx").setLevel(logging.WARNING)        # one line a call on the client's error log: no


def _get(path: str, **params) -> str:
    return _ask("GET", path, params=params)


def _ask(method: str, path: str, **kw) -> str:
    try:
        # R15: the user whose chat calls this tool (Aurora gives each plugin its user: AURORA_PLUGIN_USER)
        who = {"X-Evidentia-User": os.environ.get("AURORA_PLUGIN_USER", "")}
        with httpx.Client(transport=httpx.HTTPTransport(uds=SOCK), base_url="http://evidentia", timeout=60, headers=who) as c:
            r = c.request(method, path, **kw)
    except httpx.HTTPError as e:
        return json.dumps({"error": f"Evidentia does not answer: {type(e).__name__}"})
    if not r.headers.get("content-type", "").startswith("application/json"):
        return json.dumps({"error": f"HTTP {r.status_code}"})
    return json.dumps(r.json(), ensure_ascii=False)


@server.tool()
def find_passages(words: str, limit: int = 20) -> str:
    """Passages that contain these words (a phrase in quotes stays a phrase), best first, each with its source."""
    return _get("/search", q=words, n=max(1, min(int(limit), 50)))


@server.tool()
def read_page(doc: str, page: int) -> str:
    """One page's whole text, e.g. doc="ABC:ABC0001234", page=2, with its source."""
    return _get(f"/doc/{quote(doc, safe='')}/page/{int(page)}")


@server.tool()
def document_info(doc: str) -> str:
    """A document's collection, number, pages and kind (text, scan, mixed, image)."""
    return _get(f"/doc/{quote(doc, safe='')}")


@server.tool()
def same_identifier(kind: str, value: str) -> str:
    """Every page where this very identifier appears (kind: iban, bic, aba, account, coords, amount, tail); `valid`
    says whether it passed its check — only a valid one may carry a strong link."""
    return _get(f"/identifier/{quote(kind, safe='')}", value=value)


@server.tool()
def list_agents() -> str:
    """The agents this server defines (investigative, legal, common), each with its title and what it does; run one
    through its prompt (the same name)."""
    out = json.loads(_get("/agents"))
    if "agents" in out:
        out["agents"] = [{k: a[k] for k in ("name", "profile", "title", "description")} for a in out["agents"]]
    return json.dumps(out, ensure_ascii=False)


@server.tool()
def propose_agent(name: str, profile: str, title: str, description: str, instructions: str) -> str:
    """Propose a new agent when none of the existing ones fits a recurring kind of work: name (lowercase, _), profile
    (investigative, legal or common), a title, one line of what it does, and its instructions (how it works, what it
    reports). It stays a proposal, not usable, until the owner approves it."""
    return _ask("POST", "/agents/proposed", json={"name": name, "profile": profile, "title": title,
                                                    "description": description, "instructions": instructions})


@server.tool()
def open_lead(case: str, what: str, agent: str, why: str = "", docs: list[str] | None = None,
              parent: int | None = None) -> str:
    """Open a lead in a case for one agent to chase later (what to chase, which agent — see list_agents — why it
    matters, the documents to start from, the lead it was born from). The same work already done is never redone:
    its evidence comes back at once (reused)."""
    return _ask("POST", f"/cases/{quote(case, safe='')}/leads",
                json={"what": what, "agent": agent, "why": why, "docs": docs or [], "parent": parent})


@server.tool()
def case_leads(case: str, status: str = "") -> str:
    """The leads of a case (status: open, working, done, cold, dropped; empty: all), with their evidence."""
    return _get("/leads", case=case, status=status)


@server.tool()
def next_lead(worker: str, agent: str = "") -> str:
    """Take the next open lead (optionally only one agent's) to work on: it comes with the agent's prompt and a token;
    report it with report_lead and that token before the lease ends (30 minutes) or it goes back to the queue."""
    return _ask("POST", "/leads/claim", json={"worker": worker, "agent": agent})


@server.tool()
def report_lead(lead: int, token: str, status: str, summary: str, evidence: list[dict] | None = None) -> str:
    """Close a lead you took, with the token next_lead gave: status «done» (evidence: [{doc, page, quote, note}], each
    quote at least four words copied exactly from its page — what the page does not say is refused) or «cold» (the
    summary says what was looked for and not found)."""
    return _ask("POST", f"/leads/{int(lead)}/report",
                json={"token": token, "status": status, "summary": summary, "evidence": evidence or []})


@server.tool()
def contacts(name: str, limit: int = 30) -> str:
    """The lateral moves from one person: who they wrote to, who wrote to them, who was in copy — each tie with its
    kind (wrote_to, copied; «_by» when the other wrote), how many messages, the first and last day and where it is seen.
    From e-mail headers only; a private person appears as a label, never by name."""
    return _get("/network/contacts", name=name, n=max(1, min(int(limit), 100)))


@server.tool()
def people(part: str, limit: int = 20) -> str:
    """Who in the network fits a part of a name — a first name, a surname, a title as the e-mails write it
    («president», «prince», «dr»): the public people, most documented first. Use it before contacts or chain when
    you have only part of a name; contacts and chain also answer «several people fit» with the candidates."""
    return _get("/network/people", q=part, n=max(1, min(int(limit), 50)))


@server.tool()
def correspondence(a: str, b: str) -> str:
    """The messages between two people, both ways, in order of day: document, page, day, subject."""
    return _get("/network/between", a=a, b=b)


@server.tool()
def chain(a: str, b: str, depth: int = 3) -> str:
    """The shortest chain of documented ties (who wrote to whom) from one person to another, through public people
    only, at most `depth` ties (1–4), each with one message that shows it. No chain is an answer too."""
    return _get("/network/path", a=a, b=b, depth=max(1, min(int(depth), 4)))


def _register_prompts() -> int:
    """Every active agent as a prompt; with the API not answering, none (the tools still say why)."""
    from evidentia import agents as A
    try:
        cards = json.loads(_get("/agents")).get("agents", [])
    except ValueError:
        return 0
    for card in cards:
        def run(goal: str = "", card=card) -> str:
            return A.prompt(card, goal)
        server.prompt(name=card["name"], title=card["title"], description=card["description"])(run)
    return len(cards)


if __name__ == "__main__":
    _register_prompts()
    server.run("stdio")
