# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""AT-SPI on the bench bus only (libatspi through gi; pyatspi is not installed): walk trees, find the portal's
consent dialog, accept it with doAction. Used by the bench harness, never by aurora-desk (§9.2, §13.1)."""
import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402

_ready = False


def init() -> None:
    global _ready
    if not _ready:
        Atspi.init()
        _ready = True


def apps() -> list:
    init()
    d = Atspi.get_desktop(0)
    out = []
    for i in range(d.get_child_count()):
        try:
            a = d.get_child_at_index(i)
        except Exception:                               # noqa: BLE001 — an app that just left
            continue
        if a is not None:
            out.append(a)
    return out


def app_pid(a) -> int:
    try:
        return a.get_process_id()
    except Exception:                                   # noqa: BLE001
        return -1


def walk(acc, depth: int = 0, limit: int = 4000):
    """Yield (depth, node) over a subtree, children by index."""
    stack, seen = [(depth, acc)], 0
    while stack and seen < limit:
        dep, node = stack.pop()
        seen += 1
        yield dep, node
        try:
            n = node.get_child_count()
        except Exception:                               # noqa: BLE001
            continue
        kids = []
        for i in range(n):
            try:
                c = node.get_child_at_index(i)
            except Exception:                           # noqa: BLE001
                c = None
            if c is not None:
                kids.append((dep + 1, c))
        stack.extend(reversed(kids))


def info(node) -> dict:
    def safe(f, default=""):
        try:
            return f()
        except Exception:                               # noqa: BLE001
            return default
    return {"role": safe(node.get_role_name), "name": safe(node.get_name),
            "n_actions": safe(lambda: node.get_action_iface().get_n_actions() if node.get_action_iface() else 0, 0)}


def dump(acc) -> list:
    return [(d, info(n)) for d, n in walk(acc)]


def text_of(acc) -> str:
    """Every name and text under acc, joined (the dialog's words, read without any capture)."""
    parts = []
    for _, n in walk(acc):
        try:
            nm = n.get_name()
            if nm:
                parts.append(nm)
            t = n.get_text_iface()
            if t is not None:
                s = t.get_text(0, t.get_character_count())
                if s:
                    parts.append(s)
        except Exception:                               # noqa: BLE001
            continue
    return " | ".join(parts)


def do_action(node, names=("Press", "press", "click", "Toggle", "toggle", "activate")) -> str:
    """Invoke the first action of node whose name is in names; return its name or ''."""
    a = node.get_action_iface()
    if a is None:
        return ""
    for i in range(a.get_n_actions()):
        nm = a.get_action_name(i)
        if nm in names:
            a.do_action(i)
            return nm
    return ""
