# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Android app's welcome and address form, on the desktop (owner, 27 Nov): Aurora's address (an IP or a name) and
its port, HTTPS only; then the WebUI asks the login once, as on the phone. address.py says when it is shown."""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

from desk.app import address

WELCOME = ("Aurora sul tuo computer. Ti servono l'indirizzo della tua Aurora e, solo la prima volta, la chiave o il "
           "tuo utente per entrare: poi l'app entra da sola.")
HELP = "L'indirizzo che apri nel browser per Aurora, per esempio aurora.example e la porta 8443 (vuota: 443)."


class ConnectForm(QDialog):
    def __init__(self, current: str | None = None, why: str = ""):
        super().__init__()
        self.setWindowTitle("Collega Aurora")
        self.address: str | None = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>Aurora</b><br>{WELCOME}"))
        self.host, self.port = QLineEdit(), QLineEdit()
        self.host.setPlaceholderText("aurora.example")
        self.port.setPlaceholderText("443")
        if current:
            from urllib.parse import urlsplit
            u = urlsplit(current)
            self.host.setText(u.hostname or "")
            self.port.setText(str(u.port) if u.port else "")
        lay.addWidget(QLabel("Indirizzo (IP o nome)"))
        lay.addWidget(self.host)
        lay.addWidget(QLabel("Porta"))
        lay.addWidget(self.port)
        self.note = QLabel(why or HELP)
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Collega")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annulla")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _save(self) -> None:
        a = address.of(self.host.text(), self.port.text())
        if a is None:
            self.note.setText("Non è un indirizzo HTTPS valido: un nome o un IP, e una porta tra 1 e 65535.")
            return
        address.save(a)
        self.address = a
        self.accept()


def ask(current: str | None = None, why: str = "") -> str | None:
    f = ConnectForm(current, why)
    return f.address if f.exec() == QDialog.DialogCode.Accepted else None
