# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F9's two Qt test programs.

    python3 -I -B f9_apps.py desk  --events FILE   aurora-desk's critical window as a test: code field, a QR-like area
                                                    (qrencode is not installed: a drawn invented pattern, no real
                                                    QR), buttons «Sì» / «No». Every press and every text change is
                                                    written to FILE by the window itself: the oracle of «an action
                                                    happened», independent of AT-SPI.
    python3 -I -B f9_apps.py tree  --ready FILE    a known tree: 50 widgets with accessible names nodo-00…nodo-49
                                                    (20 labels, 15 push buttons, 15 check boxes); FILE gets the spec.
Way A (F9): aurora-desk's window is started with AT_SPI_BUS_ADDRESS pointing at a path that does not exist, so
Qt's AT-SPI bridge cannot connect; the reader is a separate libatspi client and needs no Qt bridge.
"""
import argparse
import json
import os
import sys
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QApplication, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QWidget)

N_LABEL, N_BUTTON, N_CHECK = 20, 15, 15


def tree_spec() -> list:
    out = []
    for i in range(N_LABEL + N_BUTTON + N_CHECK):
        kind = "label" if i < N_LABEL else ("button" if i < N_LABEL + N_BUTTON else "check")
        out.append({"name": f"nodo-{i:02d}", "kind": kind})
    return out


class FakeQR(QWidget):
    """An invented black and white pattern in place of the QR (no encoder installed)."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(168, 168)
        self.setAccessibleName("qr-area")

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        for y in range(21):
            for x in range(21):
                if (x * 7 + y * 13 + x * y) % 3 == 0:
                    p.fillRect(4 + x * 8, 4 + y * 8, 8, 8, QColor(0, 0, 0))
        p.end()


def desk(events: str) -> int:
    app = QApplication(sys.argv[:1])
    w = QWidget()
    w.setWindowTitle("aurora-desk-prova")
    log = open(events, "a", buffering=1)

    def ev(kind, value=""):
        log.write(json.dumps({"t": time.time(), "pid": os.getpid(), "kind": kind, "value": value}) + "\n")

    code = QLineEdit()
    code.setAccessibleName("codice")
    code.setPlaceholderText("codice a 6 cifre")
    code.textChanged.connect(lambda s: ev("text", s))
    yes, no = QPushButton("Sì"), QPushButton("No")
    yes.clicked.connect(lambda: ev("press", "si"))
    no.clicked.connect(lambda: ev("press", "no"))
    lay = QVBoxLayout(w)
    lay.addWidget(QLabel("Collega Aurora Desktop: inquadra il codice"))
    lay.addWidget(FakeQR())
    lay.addWidget(code)
    row = QHBoxLayout()
    row.addWidget(yes)
    row.addWidget(no)
    lay.addLayout(row)
    w.show()
    QTimer.singleShot(200, lambda: ev("ready", str(os.environ.get("AT_SPI_BUS_ADDRESS", ""))))
    return app.exec()


def tree(ready: str) -> int:
    app = QApplication(sys.argv[:1])
    w = QWidget()
    w.setWindowTitle("albero-di-prova")
    grid = QGridLayout(w)
    for i, s in enumerate(tree_spec()):
        if s["kind"] == "label":
            x = QLabel(f"etichetta {i}")
        elif s["kind"] == "button":
            x = QPushButton(f"bottone {i}")
        else:
            x = QCheckBox(f"casella {i}")
        x.setAccessibleName(s["name"])
        grid.addWidget(x, i // 5, i % 5)
    w.show()

    def done():
        with open(ready + ".tmp", "w") as f:
            json.dump({"pid": os.getpid(), "spec": tree_spec()}, f)
        os.replace(ready + ".tmp", ready)

    QTimer.singleShot(300, done)
    return app.exec()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("desk", "tree"))
    ap.add_argument("--events", default="")
    ap.add_argument("--ready", default="")
    a = ap.parse_args()
    sys.exit(desk(a.events) if a.mode == "desk" else tree(a.ready))
