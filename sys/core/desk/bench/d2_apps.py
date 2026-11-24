# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1, D2/D3 test programs for the bench (invented fields, no real data):
  qt   — a Qt window: «Nome» (plain), «Password» (echo mode Password), «Codice OTP» (plain, a secret by its name)
  gtk  — a GTK 3 window: «Nome» (plain), «Password» (visibility off)
  qt2  — one Qt process with two windows, «Finestra A» and «Finestra B», one field each
  other — a Qt window of another process, «Altro programma», one field
    python3 -I -B d2_apps.py MODE --ready FILE"""
import argparse
import sys


def qt(mode: str, ready: str) -> int:
    from PyQt6.QtWidgets import QApplication, QFormLayout, QLabel, QLineEdit, QWidget
    app = QApplication(sys.argv)

    def window(title: str, fields: list) -> QWidget:
        w = QWidget()
        w.setWindowTitle(title)
        form = QFormLayout(w)
        for label, obj, secret in fields:
            e = QLineEdit()
            e.setObjectName(obj)
            if secret:
                e.setEchoMode(QLineEdit.EchoMode.Password)
            lab = QLabel(label)
            lab.setBuddy(e)
            e.setAccessibleName(label.rstrip(":"))
            form.addRow(lab, e)
        w.resize(420, 160)
        w.show()
        return w

    keep = []
    if mode == "qt":
        keep.append(window("Prova D2 Qt", [("Nome:", "nome", False), ("Password:", "pwd", True),
                                           ("Codice OTP:", "otp", False)]))
    elif mode == "qt2":
        keep.append(window("Finestra A", [("Testo A:", "a", False)]))
        keep.append(window("Finestra B", [("Testo B:", "b", False)]))
    else:
        keep.append(window("Altro programma", [("Testo:", "altro", False)]))
    open(ready, "w").write("ready")
    return app.exec()


def gtk(ready: str) -> int:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    w = Gtk.Window(title="Prova D2 GTK")
    grid = Gtk.Grid(column_spacing=8, row_spacing=8)
    for i, (label, secret) in enumerate((("Nome", False), ("Password", True))):
        lab = Gtk.Label(label=label)
        e = Gtk.Entry()
        e.set_visibility(not secret)
        lab.set_mnemonic_widget(e)
        e.get_accessible().set_name(label)
        grid.attach(lab, 0, i, 1, 1)
        grid.attach(e, 1, i, 1, 1)
    w.add(grid)
    w.connect("destroy", Gtk.main_quit)
    w.show_all()
    open(ready, "w").write("ready")
    Gtk.main()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["qt", "gtk", "qt2", "other"])
    ap.add_argument("--ready", required=True)
    a = ap.parse_args()
    return gtk(a.ready) if a.mode == "gtk" else qt(a.mode, a.ready)


if __name__ == "__main__":
    sys.exit(main())
