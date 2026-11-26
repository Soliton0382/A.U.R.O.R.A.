# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora Desktop in the system tray (the owner, 25 Nov: «sarebbe utile avere aurora desk nella system tray, in
questo modo si accede a lei più facilmente che dal menù»).

- an icon beside the clock with a menu: Aurora (the WebUI window, N156), Apri, Mostrami, Cosa ho imparato,
  Esci; a click opens Aurora (the WebUI window; owner, 27 Nov), «Apri» this app's own window;
- closing the window hides it in the tray; «Esci» really quits (accessibility put back first);
- a second start (the menu entry, the login autostart) does not open a second app: it asks the running one to show
  itself through a local socket in the runtime folder (AF_UNIX, the only sockets the launcher allows);
- idle in the tray the app does nothing: accessibility stays off until «Mostrami»."""
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from desk.app import store

SOCKET = "show.sock"
WEB_LAUNCHER = "/usr/local/bin/aurora-desk"


def ask_running_to_show() -> bool:
    """True when an Aurora Desktop already runs and was asked to show its window."""
    s = QLocalSocket()
    s.connectToServer(str(store.runtime_dir() / SOCKET))
    if not s.waitForConnected(1500):
        return False
    s.write(b"show\n")
    s.waitForBytesWritten(1500)
    s.disconnectFromServer()
    return True


class Tray:
    def __init__(self, app: QApplication, main, icon):
        self.app, self.main = app, main
        self.quitting = False
        self.server = QLocalServer()
        path = str(store.runtime_dir() / SOCKET)
        QLocalServer.removeServer(path)                  # a socket left by a crash (the lock says we are alone)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.listen(path)
        self.server.newConnection.connect(self._show_request)
        self.icon = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.icon = QSystemTrayIcon(icon)
            self.icon.setToolTip("Aurora Desktop — impara (versione 1)")
            menu = QMenu()
            for text, slot in (("Aurora", self._web), ("Apri", self.show), ("Mostrami", self._demonstrate),
                               ("Cosa ho imparato", self._learned), ("Cambia indirizzo di Aurora", self._web_setup),
                               ("Esci", self.quit)):
                a = QAction(text, menu)
                a.triggered.connect(slot)
                menu.addAction(a)
            self.icon.setContextMenu(menu)
            self.menu = menu
            self.icon.activated.connect(self._activated)
            self.icon.show()
            app.setQuitOnLastWindowClosed(False)

    @property
    def available(self) -> bool:
        return self.icon is not None

    def _show_request(self) -> None:
        c = self.server.nextPendingConnection()
        if c is not None:
            c.readyRead.connect(lambda: (c.readAll(), self.show()))

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._web()                                  # the owner, 27 Nov: a click opens Aurora (the WebUI window);
                                                         # Aurora Desktop's own window from the menu («Apri»)

    def show(self) -> None:
        self.main.showNormal()
        self.main.raise_()
        self.main.activateWindow()

    def _web(self) -> None:
        """The WebUI window (N156): its own unit, with the network this app has not (the launcher's --web)."""
        import subprocess
        subprocess.Popen([WEB_LAUNCHER, "--web"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    def _web_setup(self) -> None:
        """The Android app's address form again (address.py, connect_form.py): another Aurora, a new port."""
        import subprocess
        subprocess.Popen([WEB_LAUNCHER, "--web-setup"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    def _learned(self) -> None:
        self.show()
        self.main.show_learned()

    def _demonstrate(self) -> None:
        self.show()
        if self.main.show_btn.isEnabled():
            self.main.start()

    def recording(self, on: bool, what: str = "") -> None:
        if self.icon is not None:
            self.icon.setToolTip(f"● Aurora Desktop registra: {what}" if on else "Aurora Desktop — impara (versione 1)")

    def quit(self) -> None:
        self.quitting = True
        self.main.close()
        self.server.close()
        if self.icon is not None:
            self.icon.hide()
        self.app.quit()
