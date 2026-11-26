# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""«Cosa ho imparato» (C747; the owner, 26 Nov: «non vedo niente di quello che ha imparato… così non si può trustare
niente»): every procedure Aurora Desktop knows, readable before anyone says it was learned.

- the general library (signed with the code) and the person's drafts (not approved), each with its steps in plain
  words, its values, the day it was saved and every bench trial with its outcome;
- «Esporta» saves a copy where the person chooses; «Togli» moves a draft into «tolte» (it can be put back), never a
  general procedure, never a deletion;
- the files stay on this computer (~/.local/state/aurora-desk): nothing is sent anywhere."""
from __future__ import annotations

import html
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QSplitter, QTextBrowser, QVBoxLayout)

from desk.app import explain, store

KIND_IT = {"generale": "libreria generale (firmata col codice)", "bozza": "tua bozza (non approvata)"}


def summary(e: dict) -> str:
    t = e["trials"]
    if e["kind"] == "generale":
        return "provata dai test di Aurora"
    if not t:
        return "mai provata sul banco"
    ok = sum(1 for x in t if x["ok"])
    return f"prove sul banco: {ok} riuscite su {len(t)}"


def detail_html(e: dict) -> str:
    rows = "".join(f"<li>{html.escape(explain.describe(s))}</li>" for s in e["steps"])
    params = ", ".join(f"{html.escape(k)} ({html.escape(v.get('kind', ''))})" for k, v in e["params"].items()) or "nessuno"
    trials = "".join(f"<li>{x['date']}: {'riuscita' if x['ok'] else 'non riuscita'} ({x['steps_ok']}/{x['steps']} passi)</li>"
                     for x in e["trials"]) or "<li>nessuna</li>"
    return (f"<h3>{html.escape(e['title'])}</h3>"
            f"<p><b>Programma:</b> {html.escape(e['program'])} ({html.escape(e['os'])})<br>"
            f"<b>Da dove:</b> {KIND_IT[e['kind']]}<br><b>Salvata il:</b> {e['saved']}<br>"
            f"<b>Valori da dare:</b> {params}<br><b>Identificativo:</b> {html.escape(e['id'])}</p>"
            f"<p><b>Passi</b></p><ol>{rows}</ol><p><b>Prove sul banco</b></p><ul>{trials}</ul>")


class Learned(QDialog):
    def __init__(self, parent, general_root: Path):
        super().__init__(parent)
        self.setWindowTitle("Cosa ho imparato")
        self.resize(860, 520)
        self.general_root = general_root
        lay = QVBoxLayout(self)
        split = QSplitter()
        self.list = QListWidget()
        self.text = QTextBrowser()
        split.addWidget(self.list)
        split.addWidget(self.text)
        split.setSizes([320, 540])
        lay.addWidget(split)
        row = QHBoxLayout()
        self.export_btn, self.remove_btn, close = QPushButton("Esporta…"), QPushButton("Togli"), QPushButton("Chiudi")
        for b in (self.export_btn, self.remove_btn, close):
            row.addWidget(b)
        lay.addLayout(row)
        self.export_btn.clicked.connect(self.export)
        self.remove_btn.clicked.connect(self.remove)
        close.clicked.connect(self.accept)
        self.list.currentItemChanged.connect(self.show_one)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        self.entries = store.learned(self.general_root)
        for e in self.entries:
            it = QListWidgetItem(f"{e['program']} — {e['title']}\n   {KIND_IT[e['kind']]}; {summary(e)}")
            self.list.addItem(it)
        if self.entries:
            self.list.setCurrentRow(0)
        else:
            self.text.setHtml("<p>Non ho ancora imparato niente. Premi «Mostrami» e fammi vedere come si fa.</p>")
            self.export_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)

    def current(self) -> dict | None:
        r = self.list.currentRow()
        return self.entries[r] if 0 <= r < len(self.entries) else None

    def show_one(self, *_):
        e = self.current()
        if e:
            self.text.setHtml(detail_html(e))
            self.remove_btn.setEnabled(e["kind"] == "bozza")
            self.export_btn.setEnabled(True)

    def export(self) -> None:
        e = self.current()
        if not e:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Esporta la procedura", str(Path.home() / e["path"].name),
                                              "Procedura (*.json)")
        if dest:
            shutil.copyfile(e["path"], dest)

    def remove(self) -> None:
        e = self.current()
        if not e or e["kind"] != "bozza":
            return
        if QMessageBox.question(self, "Togli", f"Tolgo «{e['title']}»? Finisce nella cartella «tolte», "
                                "da dove la puoi rimettere.") == QMessageBox.StandardButton.Yes:
            store.remove_draft(e["path"])
            self.reload()
