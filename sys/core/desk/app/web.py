# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora as a desktop app (N156; the owner, 26 Nov: «come se fosse l'app android… una app standalone basata sulla
webui così non si è costretti ad aprire chrome»): the WebUI in a window of its own, beside Aurora Desktop.

- only Aurora's own address is loaded: every request to another host is blocked inside the page (the user units of
  systemd cannot filter addresses: measured 26 Nov, «IP firewall, but not running as root»); a link to the outside is
  handed to the system browser, never opened here;
- the login is kept in a profile of its own under ~/.local/state/aurora-desk/web (0700), not in Chrome's;
- camera, microphone, screen and notifications are asked to the person each time, and only for Aurora's address;
- downloads are saved where the person chooses;
- one window at a time: a second start brings the first one forward (a local socket, as the tray does)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from desk.app import store  # noqa: E402

URL = os.environ.get("DESK_WEB_URL", "http://127.0.0.1:9700/")
SOCKET = "web.sock"
LOCAL_SCHEMES = {"data", "blob", "qrc", "about"}


def same_origin(url: QUrl, base: QUrl) -> bool:
    """True for Aurora's own address (scheme, host and port as the base), or a scheme that never leaves the machine."""
    if url.scheme() in LOCAL_SCHEMES:
        return True
    ws = {"http": "ws", "https": "wss"}.get(base.scheme())
    return (url.scheme() in (base.scheme(), ws) and url.host() == base.host()
            and url.port(80 if base.scheme() == "http" else 443) == base.port(80 if base.scheme() == "http" else 443))


class OnlyAurora(QWebEngineUrlRequestInterceptor):
    """Blocks every request that is not to Aurora (scripts, images, fonts, calls): nothing leaves from the page."""
    def __init__(self, base: QUrl):
        super().__init__()
        self.base, self.blocked = base, 0

    def interceptRequest(self, info) -> None:
        if not same_origin(info.requestUrl(), self.base):
            info.block(True)
            self.blocked += 1


class Page(QWebEnginePage):
    def __init__(self, profile, base: QUrl, parent):
        super().__init__(profile, parent)
        self.base = base
        self.permissionRequested.connect(self._permission_new)   # Qt ≥ 6.8: the old featurePermissionRequested is not sent

    def acceptNavigationRequest(self, url: QUrl, kind, main_frame: bool) -> bool:
        if same_origin(url, self.base):
            return True
        if kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked and url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)                 # the outside goes to the system browser
        return False

    def createWindow(self, _kind):                        # target=_blank: same rule, through a throwaway page
        tmp = Page(self.profile(), self.base, self.parent())
        tmp.urlChanged.connect(lambda u: (self.acceptNavigationRequest(u, QWebEnginePage.NavigationType.NavigationTypeLinkClicked, True)
                                          and self.setUrl(u), tmp.deleteLater()))
        return tmp

    def _permission_new(self, perm) -> None:
        """Camera, microphone, screen, notifications: asked to the person, only for Aurora's address. Notifications
        are kept once allowed (the profile remembers it); the others are asked each time."""
        from PyQt6.QtWebEngineCore import QWebEnginePermission as P
        T = P.PermissionType
        names = {T.MediaAudioCapture: "il microfono", T.MediaVideoCapture: "la fotocamera",
                 T.MediaAudioVideoCapture: "microfono e fotocamera", T.Notifications: "le notifiche",
                 T.DesktopVideoCapture: "lo schermo", T.DesktopAudioVideoCapture: "lo schermo con l'audio"}
        what = names.get(perm.permissionType())
        if not what or not same_origin(perm.origin(), self.base):
            perm.deny()
            return
        once = "" if perm.permissionType() == T.Notifications else ", solo per questa volta"
        if QMessageBox.question(self.parent(), "Aurora", f"Aurora chiede di usare {what}. Permetti{once}?") \
                == QMessageBox.StandardButton.Yes:
            perm.grant()
        else:
            perm.deny()

    def _permission(self, origin: QUrl, feature) -> None:
        grant = QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
        if same_origin(origin, self.base):
            names = {QWebEnginePage.Feature.MediaAudioCapture: "il microfono",
                     QWebEnginePage.Feature.MediaVideoCapture: "la fotocamera",
                     QWebEnginePage.Feature.MediaAudioVideoCapture: "microfono e fotocamera",
                     QWebEnginePage.Feature.Notifications: "le notifiche",
                     QWebEnginePage.Feature.DesktopVideoCapture: "lo schermo",
                     QWebEnginePage.Feature.DesktopAudioVideoCapture: "lo schermo con l'audio"}
            what = names.get(feature)
            if what and QMessageBox.question(self.parent(), "Aurora",
                                             f"Aurora chiede di usare {what}. Permetti, solo per questa volta?") \
                    == QMessageBox.StandardButton.Yes:
                grant = QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
        self.setFeaturePermission(origin, feature, grant)


class Window(QMainWindow):
    def __init__(self, url: str = URL):
        super().__init__()
        self.setWindowTitle("Aurora")
        self.resize(1200, 820)
        base = QUrl(url)
        data = store.private_dir(store.STATE / "web")
        self.profile = QWebEngineProfile("aurora-desk", self)
        self.profile.setPersistentStoragePath(str(data / "storage"))
        self.profile.setCachePath(str(data / "cache"))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.guard = OnlyAurora(base)
        self.profile.setUrlRequestInterceptor(self.guard)
        self.profile.downloadRequested.connect(self._download)
        self.profile.setNotificationPresenter(self._notify)     # the page's notifications on the desktop
        self.view = QWebEngineView(self)
        self.view.setPage(Page(self.profile, base, self))
        self.view.page().titleChanged.connect(lambda t: self.setWindowTitle(t or "Aurora"))
        self.setCentralWidget(self.view)
        self.view.setUrl(base)

    def _notify(self, n) -> None:
        """A notification of the page shown by the desktop (notify-send: the session's notification server); a click
        on it brings this window forward."""
        import subprocess
        self._last = n                                          # kept alive while shown
        try:
            subprocess.Popen(["/usr/bin/notify-send", "--app-name=Aurora", "--icon=aurora-desk", "--",
                              n.title()[:200] or "Aurora", n.message()[:1000]],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            n.show()
        except OSError:
            pass

    def _download(self, item) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Salva", str(Path.home() / item.downloadFileName()))
        if not path:
            item.cancel()
            return
        item.setDownloadDirectory(str(Path(path).parent))
        item.setDownloadFileName(Path(path).name)
        item.accept()


def ask_running_to_show() -> bool:
    s = QLocalSocket()
    s.connectToServer(str(store.runtime_dir() / SOCKET))
    if not s.waitForConnected(1500):
        return False
    s.write(b"show\n")
    s.waitForBytesWritten(1500)
    return True


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Aurora")
    app.setDesktopFileName("aurora-desk")
    setup = os.environ.get("DESK_WEB_SETUP") == "1"     # the menu's «Cambia indirizzo di Aurora» (--web-setup)
    if not setup and ask_running_to_show():
        return 0
    from desk.app import address                        # Aurora here: asked nothing; else the Android app's form
    url, why = address.choose(setup)
    if url is None:
        from desk.app import connect_form
        url = connect_form.ask(address.saved())
        if url is None:
            return 0
    from PyQt6.QtGui import QPixmap
    from desk.app import icon
    pm = QPixmap()
    pm.loadFromData(icon.SVG.encode(), "SVG")
    app.setWindowIcon(QIcon(pm))
    w = Window(url if url.endswith("/") else url + "/")
    server = QLocalServer()
    path = str(store.runtime_dir() / SOCKET)
    QLocalServer.removeServer(path)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    server.listen(path)

    def show():
        c = server.nextPendingConnection()
        if c is not None:
            c.readyRead.connect(lambda: (c.readAll(), w.showNormal(), w.raise_(), w.activateWindow()))
    server.newConnection.connect(show)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
