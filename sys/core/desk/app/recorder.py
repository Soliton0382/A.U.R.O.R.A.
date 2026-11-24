# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1: the demonstration recorder (design bozza 8 §3, §10 R4/R5).

No libatspi in this process: one D-Bus connection to the AT-SPI bus (Gio), events registered for the chosen
application only (Registry.RegisterEvent with its bus name) and match rules with sender= (measured, M334: another
program's text never arrives). Kept: events of the chosen window (the frame chosen at «Mostrami») and of dialogs of the
same application that appear during the recording. Password fields: nothing of theirs is kept (not the value, not the
length); the event is counted as suppressed and dropped before any storage.
Text is rebuilt by offsets (M335: concatenating insertions in order is wrong)."""
import threading
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

EVENTS = ["object:text-changed", "object:property-change:accessible-name", "object:state-changed",
          "object:children-changed", "window:", "focus:"]
IFACES = ("Object", "Window", "Focus")
# AtspiRole number -> name as libatspi (atspi_role_get_name) names it, generated once from the installed libatspi
# (25 Nov): Qt's GetRoleName answers other spellings («button menu» for «push button menu», «push button» for
# «button»), and the procedures are matched by the bench through libatspi. GetRole + this table = the same names.
ROLE_NAMES = {
    0: 'invalid', 1: 'accelerator label', 2: 'alert', 3: 'animation', 4: 'arrow', 5: 'calendar', 6: 'canvas',
    7: 'check box', 8: 'check menu item', 9: 'color chooser', 10: 'column header', 11: 'combo box',
    12: 'date editor', 13: 'desktop icon', 14: 'desktop frame', 15: 'dial', 16: 'dialog', 17: 'directory pane',
    18: 'drawing area', 19: 'file chooser', 20: 'filler', 21: 'focus traversable', 22: 'font chooser', 23: 'frame',
    24: 'glass pane', 25: 'html container', 26: 'icon', 27: 'image', 28: 'internal frame', 29: 'label',
    30: 'layered pane', 31: 'list', 32: 'list item', 33: 'menu', 34: 'menu bar', 35: 'menu item',
    36: 'option pane', 37: 'page tab', 38: 'page tab list', 39: 'panel', 40: 'password text', 41: 'popup menu',
    42: 'progress bar', 43: 'button', 44: 'radio button', 45: 'radio menu item', 46: 'root pane', 47: 'row header',
    48: 'scroll bar', 49: 'scroll pane', 50: 'separator', 51: 'slider', 52: 'spin button', 53: 'split pane',
    54: 'status bar', 55: 'table', 56: 'table cell', 57: 'table column header', 58: 'table row header',
    59: 'tearoff menu item', 60: 'terminal', 61: 'text', 62: 'toggle button', 63: 'tool bar', 64: 'tool tip',
    65: 'tree', 66: 'tree table', 67: 'unknown', 68: 'viewport', 69: 'window', 70: 'extended', 71: 'header',
    72: 'footer', 73: 'paragraph', 74: 'ruler', 75: 'application', 76: 'autocomplete', 77: 'editbar',
    78: 'embedded', 79: 'entry', 80: 'chart', 81: 'caption', 82: 'document frame', 83: 'heading', 84: 'page',
    85: 'section', 86: 'redundant object', 87: 'form', 88: 'link', 89: 'input method window', 90: 'table row',
    91: 'tree item', 92: 'document spreadsheet', 93: 'document presentation', 94: 'document text',
    95: 'document web', 96: 'document email', 97: 'comment', 98: 'list box', 99: 'grouping', 100: 'image map',
    101: 'notification', 102: 'info bar', 103: 'level bar', 104: 'title bar', 105: 'block quote', 106: 'audio',
    107: 'video', 108: 'definition', 109: 'article', 110: 'landmark', 111: 'log', 112: 'marquee', 113: 'math',
    114: 'rating', 115: 'timer', 116: 'static', 117: 'math fraction', 118: 'math root', 119: 'subscript',
    120: 'superscript', 121: 'description list', 122: 'description term', 123: 'description value',
    124: 'footnote', 125: 'content deletion', 126: 'content insertion', 127: 'mark', 128: 'suggestion',
    129: 'push button menu', 130: 'switch', 131: 'last defined'
}

ACC = "org.a11y.atspi.Accessible"
TOP_ROLES = {"frame", "dialog", "alert", "file chooser", "window", "popup menu", "menu"}
# a top-level of the same application born during the recording counts (its dialogs, its popup menus: a Qt popup
# opened by a key is a top-level of its own, seen in Dolphin); its other frames never do
PASSWORD_ROLES = {"password text"}
STATE_EDITABLE, STATE_READ_ONLY = 7, 43      # AtspiStateType (read from libatspi: 7, 43)
MAX_EVENTS = 20000                     # bozza 8 §3: ~20 MiB at ~1 KiB per event (calculation)
MAX_SECONDS = 30 * 60


def a11y_address() -> str:
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    r = bus.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress", None,
                      GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 3000, None)
    return r.unpack()[0]


def connect(addr: str) -> Gio.DBusConnection:
    flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
    return Gio.DBusConnection.new_for_address_sync(addr, flags, None, None)


class App:
    """Read-only questions to one application over its bus name (never to the others)."""

    def __init__(self, conn: Gio.DBusConnection, bus_name: str):
        self.c, self.bus = conn, bus_name
        self.cache = {}

    def _call(self, path, iface, method, params=None, reply=None):
        return self.c.call_sync(self.bus, path, iface, method, params,
                                GLib.VariantType(reply) if reply else None, Gio.DBusCallFlags.NONE, 2000,
                                None).unpack()

    def _prop(self, path, name):
        return self._call(path, "org.freedesktop.DBus.Properties", "Get", GLib.Variant("(ss)", (ACC, name)),
                          "(v)")[0]

    def info(self, path: str) -> dict:
        if path in self.cache:
            return self.cache[path]
        d = {"path": path}
        try:
            num = self._call(path, ACC, "GetRole", None, "(u)")[0]
            d["role"] = ROLE_NAMES.get(num) or self._call(path, ACC, "GetRoleName", None, "(s)")[0]
            d["name"] = self._prop(path, "Name")
            try:
                d["id"] = self._prop(path, "AccessibleId")
            except GLib.Error:
                d["id"] = ""
            try:
                bits = self._call(path, ACC, "GetState", None, "(au)")[0]
                word = (bits[0] if bits else 0) | ((bits[1] if len(bits) > 1 else 0) << 32)
                d["editable"] = bool(word & (1 << STATE_EDITABLE))
                d["read_only"] = bool(word & (1 << STATE_READ_ONLY))
            except GLib.Error:
                d["editable"] = d["read_only"] = None
            parent = self._prop(path, "Parent")
            d["parent"] = parent[1] if parent and parent[0] == self.bus else ""
        except GLib.Error as e:
            d.update(role="?", name="", id="", parent="", error=e.message)
        self.cache[path] = d
        return d

    def refresh_name(self, path: str, name: str) -> None:
        if path in self.cache:
            self.cache[path]["name"] = name

    def top(self, path: str) -> dict:
        """The top-level window (frame, dialog…) above path, by Parent links (at most 60 steps)."""
        cur = self.info(path)
        for _ in range(60):
            if cur.get("role") in TOP_ROLES:
                return cur
            p = cur.get("parent")
            if not p or p == "/org/a11y/atspi/accessible/root":
                return cur
            cur = self.info(p)
        return cur

    def children(self, path: str) -> list:
        try:
            # an application's children live on its own connection: the bus name it reports may be its
            # well-known or unique one, so the path is what counts
            return [p for _b, p in self._call(path, ACC, "GetChildren", None, "(a(so))")[0]]
        except GLib.Error as e:
            self.last_error = e.message
            return []

    def text(self, path: str) -> str:
        try:
            n = self._call(path, "org.freedesktop.DBus.Properties", "Get",
                           GLib.Variant("(ss)", ("org.a11y.atspi.Text", "CharacterCount")), "(v)")[0]
            return self._call(path, "org.a11y.atspi.Text", "GetText", GLib.Variant("(ii)", (0, n)), "(s)")[0]
        except GLib.Error:
            return ""


class Recorder:
    """Record one window of one application. start() returns at once; stop() returns the kept events."""

    def __init__(self, addr: str, app_bus: str, frame_path: str):
        self.addr, self.app_bus, self.frame = addr, app_bus, frame_path
        self.events = []
        self.counters = {"received": 0, "kept": 0, "other_window": 0, "password_suppressed": 0, "foreign_sender": 0}
        self.texts = {}                  # path -> text rebuilt by offsets
        self.started = None
        self._q = []
        self._lock = threading.Lock()

    def start(self) -> None:
        self.conn = connect(self.addr)
        self.app = App(self.conn, self.app_bus)
        self.tops_at_start = set(self.app.children("/org/a11y/atspi/accessible/root"))
        for ev in EVENTS:
            self.conn.call_sync("org.a11y.atspi.Registry", "/org/a11y/atspi/registry", "org.a11y.atspi.Registry",
                                "RegisterEvent", GLib.Variant("(sass)", (ev, [], self.app_bus)), None,
                                Gio.DBusCallFlags.NONE, 3000, None)
        for iface in IFACES:
            self.conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch",
                                GLib.Variant("(s)", (f"type='signal',interface='org.a11y.atspi.Event.{iface}',"
                                                     f"sender='{self.app_bus}'",)), None,
                                Gio.DBusCallFlags.NONE, 3000, None)
        self.conn.add_filter(self._filter)
        self.started = time.monotonic()

    def _filter(self, _c, msg, incoming):
        if incoming and msg.get_message_type() == Gio.DBusMessageType.SIGNAL and \
                (msg.get_interface() or "").startswith("org.a11y.atspi.Event."):
            with self._lock:
                self._q.append((time.monotonic(), msg.get_sender(), msg.get_interface().rsplit(".", 1)[-1],
                                msg.get_member(), msg.get_path(), msg.get_body()))
        return msg

    def pump(self, seconds: float) -> None:
        """Process queued signals for up to `seconds` (queries to the app happen here, not in the filter thread)."""
        end = time.monotonic() + seconds
        ctx = GLib.MainContext.default()
        while time.monotonic() < end:
            while ctx.pending():
                ctx.iteration(False)
            with self._lock:
                batch, self._q = self._q, []
            for item in batch:
                self._handle(*item)
            if not batch:
                time.sleep(0.02)

    def _handle(self, t, sender, iface, member, path, body) -> None:
        self.counters["received"] += 1
        if sender != self.app_bus:                       # the bus filtered already; counted if it ever fails
            self.counters["foreign_sender"] += 1
            return
        if len(self.events) >= MAX_EVENTS or time.monotonic() - self.started > MAX_SECONDS:
            return
        u = body.unpack() if body is not None else ()
        detail = u[0] if u else ""
        info = self.app.info(path)
        if info.get("role") in PASSWORD_ROLES:
            self.counters["password_suppressed"] += 1    # nothing of it: not the value, not the length
            return
        top = self.app.top(path)
        tp = top.get("path")
        if tp != self.frame and not (top.get("role") in TOP_ROLES - {"frame"} and tp not in self.tops_at_start):
            self.counters["other_window"] += 1
            k = f"{top.get('role')}{'(new)' if tp not in self.tops_at_start else ''}"
            self.counters.setdefault("other_tops", {})[k] = self.counters.get("other_tops", {}).get(k, 0) + 1
            return
        ev = {"t": round(t - self.started, 3), "kind": f"{iface}:{member}", "detail": detail, "path": path,
              "role": info.get("role"), "name": info.get("name"), "id": info.get("id"), "top": tp,
              "top_role": top.get("role"), "editable": info.get("editable"), "read_only": info.get("read_only")}
        if member == "TextChanged":
            off, n, val = int(u[1]), int(u[2]), u[3]
            s = self.texts.get(path, "")
            if str(detail).startswith("insert"):
                s = s[:off] + str(val) + s[off:]
            elif str(detail).startswith("delete"):
                s = s[:off] + s[off + n:]
            self.texts[path] = s
            ev.update(off=off, n=n, text_after=s)
        elif member == "PropertyChange" and detail == "accessible-name":
            ev["value"] = str(u[3])
            self.app.refresh_name(path, ev["value"])
        elif member == "StateChanged":
            ev["value"] = int(u[1])
        self.events.append(ev)
        self.counters["kept"] += 1

    def stop(self) -> dict:
        self.pump(0.3)
        try:
            for ev in EVENTS:
                self.conn.call_sync("org.a11y.atspi.Registry", "/org/a11y/atspi/registry",
                                    "org.a11y.atspi.Registry", "DeregisterEvent", GLib.Variant("(s)", (ev,)), None,
                                    Gio.DBusCallFlags.NONE, 2000, None)
        except GLib.Error:
            pass
        self.conn.close_sync(None)
        return {"events": self.events, "texts": dict(self.texts), "counters": dict(self.counters)}


def main() -> int:
    """A recorder process of its own (no libatspi in it, R4): records until --stop exists, then writes --out."""
    import argparse
    import json
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", required=True)
    ap.add_argument("--app-bus", required=True)
    ap.add_argument("--frame", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stop", required=True)
    a = ap.parse_args()
    r = Recorder(a.addr, a.app_bus, a.frame)
    r.start()
    with open(a.out + ".ready", "w") as f:
        f.write("ready")
    while not os.path.exists(a.stop):
        r.pump(0.1)
    res = r.stop()
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(res, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
