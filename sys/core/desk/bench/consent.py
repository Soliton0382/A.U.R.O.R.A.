# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The bench's consent clicker (§13.1, U2 a): the only input of phase 0, virtual and on the bench bus only.

    python3 -I -B consent.py --log events.jsonl [--deny]

Watches the AT-SPI tree of xdg-desktop-portal-kde on the bench bus. For every ScreenCast dialog it writes one event
(time, title, the dialog's words, the «Allow restoring» box as AT-SPI reports it) and accepts with a doAction
«Press» on the virtual screen's card: with multiple = false the KDE dialog accepts on that card (its QML:
onClicked -> selectAndAccept); the footer «Share» button is not in the AT-SPI tree (measured). The box is never
touched. aurora-desk never does this (§9.2); no module of aurora-desk imports this file (a test checks it).
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from desk.bench import a11y  # noqa: E402
from gi.repository import Atspi  # noqa: E402

PORTAL_APP = "xdg-desktop-portal-kde"
CARD = "Virtual-0"
RESTORE = "Allow restoring on future sessions"


def scan_dialog(app) -> dict:
    """The open dialog of the portal app, read: frame title, words, restore box, the card to press."""
    for j in range(app.get_child_count()):
        try:
            win = app.get_child_at_index(j)
        except Exception:                               # noqa: BLE001
            continue
        if win is None:
            continue
        title = win.get_name() or ""
        if not title.startswith("Share screen"):
            continue
        out = {"title": title, "card": None, "restore": None}
        for _, n in a11y.walk(win):
            try:
                role, name = n.get_role_name(), n.get_name()
            except Exception:                           # noqa: BLE001
                continue
            if role == "button" and name == CARD and out["card"] is None:
                out["card"] = n
            if role == "check box" and name == RESTORE:
                st = n.get_state_set()
                out["restore"] = {"showing": st.contains(Atspi.StateType.SHOWING),
                                  "checked": st.contains(Atspi.StateType.CHECKED)}
        out["text"] = a11y.text_of(win)
        return out
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--settle", type=float, default=0.15)
    a = ap.parse_args()
    a11y.init()
    seen = 0
    with open(a.log, "a", buffering=1) as log:
        log.write(json.dumps({"event": "ready", "t": time.time(), "pid": os.getpid()}) + "\n")
        while True:
            app = next((x for x in a11y.apps() if (x.get_name() or "") == PORTAL_APP), None)
            d = scan_dialog(app) if app is not None and app.get_child_count() else {}
            if d and d.get("card") is not None:
                t_seen = time.time()
                time.sleep(a.settle)                    # let the dialog finish building its tree
                d = scan_dialog(app) or d
                action = a11y.do_action(d["card"], ("Press",)) if d.get("card") is not None else ""
                seen += 1
                log.write(json.dumps({"event": "dialog", "n": seen, "t": t_seen, "t_action": time.time(),
                                      "title": d["title"], "text": d.get("text", ""), "restore": d.get("restore"),
                                      "action": action}) + "\n")
                t0 = time.monotonic()                   # wait for this dialog to go before looking again
                while time.monotonic() - t0 < 10 and scan_dialog(app):
                    time.sleep(0.05)
            else:
                time.sleep(0.05)


if __name__ == "__main__":
    sys.exit(main())
