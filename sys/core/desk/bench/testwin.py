# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A bench test program (F1): 1-3 frameless windows, each painted one unique colour, with an invented title.

    python3 -I -B testwin.py --spec '{"windows": [{"title": "n152-7-0", "rgb": [200, 30, 40]},
                                                 {"title": "n152-7-1", "rgb": [...], "parent": 0}]}' --ready FILE

It reports by itself, as the oracle: its own PID (os.getpid), each title, colour and declared transient parent.
"""
import argparse
import json
import os
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QApplication, QWidget


class Swatch(QWidget):
    def __init__(self, title: str, rgb):
        super().__init__(None, Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        self.color = QColor(*rgb)
        self.resize(200, 150)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), self.color)
        p.end()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--ready", required=True)
    a = ap.parse_args()
    spec = json.loads(a.spec)
    app = QApplication(sys.argv[:1])
    wins = []
    for w in spec["windows"]:
        s = Swatch(w["title"], w["rgb"])
        wins.append(s)
    for s in wins:
        s.winId()                                   # native window now, so the parent can be set before show
    for w, s in zip(spec["windows"], wins):
        if w.get("parent") is not None:            # transient: xdg_toplevel.set_parent
            s.windowHandle().setTransientParent(wins[w["parent"]].windowHandle())
    for s in wins:
        s.show()

    def ready():
        tmp = a.ready + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"pid": os.getpid(), "windows": spec["windows"]}, f)
        os.replace(tmp, a.ready)

    QTimer.singleShot(300, ready)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
