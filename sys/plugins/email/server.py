# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "email": the owner's mailbox. Only encrypted connections: IMAP over TLS (993), SMTP with TLS
(465) or STARTTLS (587); a server that does not offer them is refused."""
from __future__ import annotations

import email
import email.policy
import imaplib
import os
import smtplib
import ssl
from email.message import EmailMessage

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

IMAP = os.environ.get("AURORA_EMAIL_IMAP_HOST", "")
SMTP = os.environ.get("AURORA_EMAIL_SMTP_HOST", "")
USER = os.environ.get("AURORA_EMAIL_USER", "")
PASSWORD = os.environ.get("AURORA_EMAIL_PASSWORD", "")
CTX = ssl.create_default_context()
server = MCPServer("email", version="1.0")


def _imap():
    if not (IMAP and USER and PASSWORD):
        raise ToolError("mailbox not configured")
    host, _, port = IMAP.partition(":")
    m = imaplib.IMAP4_SSL(host, int(port or 993), ssl_context=CTX)
    m.login(USER, PASSWORD)
    return m


def _text(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    return part.get_content() if part else ""


@server.tool()
def list_unread(limit: int = 20) -> str:
    """Unread messages in the inbox: id, date, sender, subject (they stay unread)."""
    m = _imap()
    try:
        m.select("INBOX", readonly=True)
        _, ids = m.search(None, "UNSEEN")
        rows = []
        for i in ids[0].split()[-max(1, min(limit, 100)):]:
            _, data = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            h = email.message_from_bytes(data[0][1], policy=email.policy.default)
            rows.append(f"{i.decode()} | {h['date']} | {h['from']} | {h['subject']}")
        return "\n".join(reversed(rows)) or "no unread messages"
    finally:
        m.logout()


@server.tool()
def read_message(message_id: str) -> str:
    """One message (headers and text), without marking it as read."""
    m = _imap()
    try:
        m.select("INBOX", readonly=True)
        _, data = m.fetch(message_id.encode(), "(BODY.PEEK[])")
        msg = email.message_from_bytes(data[0][1], policy=email.policy.default)
        return f"From: {msg['from']}\nTo: {msg['to']}\nDate: {msg['date']}\nSubject: {msg['subject']}\n\n{_text(msg)[:20000]}"
    finally:
        m.logout()


@server.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email from the owner's address (an external action: the owner confirms it)."""
    if not (SMTP and USER and PASSWORD):
        raise ToolError("sending not configured (AURORA_EMAIL_SMTP_HOST)")
    host, _, port = SMTP.partition(":")
    port = int(port or 465)
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = USER, to, subject
    msg.set_content(body)
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=CTX, timeout=30) as s:
            s.login(USER, PASSWORD)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=CTX)                  # raises if the server does not offer TLS: never in clear
            s.login(USER, PASSWORD)
            s.send_message(msg)
    return f"sent to {to}"


if __name__ == "__main__":
    server.run("stdio")
