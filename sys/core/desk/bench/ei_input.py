# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 bench: real keyboard input on the virtual KWin through the RemoteDesktop portal (liboeffis) and libei, by
ctypes (no Python binding is installed; libei/liboeffis 1.5.0 are). The input path aurora-desk will use in version 2;
here only on the bench bus (the caller is inside the bench's dbus-run-session; guard.check_env ran before).
Text is typed with a US keymap table (the virtual KWin's default): ASCII only, declared."""
import ctypes
import select
import time

_oe = ctypes.CDLL("liboeffis.so.1")
_ei = ctypes.CDLL("libei.so.1")
for name, res, args in (
        ("oeffis_new", ctypes.c_void_p, [ctypes.c_void_p]),
        ("oeffis_get_fd", ctypes.c_int, [ctypes.c_void_p]),
        ("oeffis_create_session", None, [ctypes.c_void_p, ctypes.c_uint32]),
        ("oeffis_dispatch", None, [ctypes.c_void_p]),
        ("oeffis_get_event", ctypes.c_int, [ctypes.c_void_p]),
        ("oeffis_get_eis_fd", ctypes.c_int, [ctypes.c_void_p]),
        ("oeffis_get_error_message", ctypes.c_char_p, [ctypes.c_void_p]),
        ("oeffis_unref", ctypes.c_void_p, [ctypes.c_void_p])):
    f = getattr(_oe, name)
    f.restype, f.argtypes = res, args
for name, res, args in (
        ("ei_new_sender", ctypes.c_void_p, [ctypes.c_void_p]),
        ("ei_configure_name", None, [ctypes.c_void_p, ctypes.c_char_p]),
        ("ei_setup_backend_fd", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
        ("ei_get_fd", ctypes.c_int, [ctypes.c_void_p]),
        ("ei_dispatch", None, [ctypes.c_void_p]),
        ("ei_get_event", ctypes.c_void_p, [ctypes.c_void_p]),
        ("ei_event_get_type", ctypes.c_int, [ctypes.c_void_p]),
        ("ei_event_type_to_string", ctypes.c_char_p, [ctypes.c_int]),
        ("ei_event_get_seat", ctypes.c_void_p, [ctypes.c_void_p]),
        ("ei_event_get_device", ctypes.c_void_p, [ctypes.c_void_p]),
        ("ei_event_unref", ctypes.c_void_p, [ctypes.c_void_p]),
        ("ei_seat_has_capability", ctypes.c_bool, [ctypes.c_void_p, ctypes.c_int]),
        ("ei_device_has_capability", ctypes.c_bool, [ctypes.c_void_p, ctypes.c_int]),
        ("ei_device_get_name", ctypes.c_char_p, [ctypes.c_void_p]),
        ("ei_device_start_emulating", None, [ctypes.c_void_p, ctypes.c_uint32]),
        ("ei_device_stop_emulating", None, [ctypes.c_void_p]),
        ("ei_device_keyboard_key", None, [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_bool]),
        ("ei_device_frame", None, [ctypes.c_void_p, ctypes.c_uint64]),
        ("ei_now", ctypes.c_uint64, [ctypes.c_void_p]),
        ("ei_disconnect", None, [ctypes.c_void_p]),
        ("ei_unref", ctypes.c_void_p, [ctypes.c_void_p])):
    f = getattr(_ei, name)
    f.restype, f.argtypes = res, args
_ei.ei_seat_bind_capabilities.restype = None        # variadic, 0-terminated

OEFFIS_KEYBOARD, OEFFIS_POINTER = 1 << 0, 1 << 1
OE_NONE, OE_CONNECTED, OE_CLOSED, OE_DISCONNECTED = 0, 1, 2, 3
CAPS = {"POINTER": 1 << 0, "POINTER_ABSOLUTE": 1 << 1, "KEYBOARD": 1 << 2, "TOUCH": 1 << 3, "SCROLL": 1 << 4,
        "BUTTON": 1 << 5}

# evdev key codes (linux/input-event-codes.h), US layout
_KEYS = {"Esc": 1, "Tab": 15, "Enter": 28, "Ctrl": 29, "Shift": 42, "Alt": 56, "Space": 57, "Backspace": 14,
         "Up": 103, "Left": 105, "Right": 106, "Down": 108, "F10": 68}
_ROWS = [("1234567890-=", 2), ("qwertyuiop[]", 16), ("asdfghjkl;'", 30), ("zxcvbnm,./", 44)]
_SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
            "_": "-", "+": "=", "{": "[", "}": "]", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
            "|": "\\"}
_CHAR = {}
for row, first in _ROWS:
    for i, ch in enumerate(row):
        _CHAR[ch] = (first + i, False)
_CHAR.update({" ": (57, False), "\n": (28, False), "`": (41, False), "\\": (43, False)})
for s, base in _SHIFTED.items():
    _CHAR[s] = (_CHAR[base][0], True)
for ch in "abcdefghijklmnopqrstuvwxyz":
    _CHAR[ch.upper()] = (_CHAR[ch][0], True)


def keycode(name: str) -> int:
    if name in _KEYS:
        return _KEYS[name]
    if len(name) == 1 and name.lower() in _CHAR:
        return _CHAR[name.lower()][0]
    raise KeyError(name)


class Portal:
    """A RemoteDesktop session over D-Bus (Gio), registered with an app id first: liboeffis opens its own D-Bus
    connection, which cannot be registered, and the portal answered «Permission denied» (bench, 25 Nov).
    on_wait() runs every 100 ms while a request is pending (the consent dialog)."""

    BUS, PATH = "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
    RD = "org.freedesktop.portal.RemoteDesktop"

    def __init__(self, app_id: str = "org.aurora.desk", timeout: float = 30.0):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")
        self.timeout = timeout
        self.events = []
        try:
            self.bus.call_sync(self.BUS, self.PATH, "org.freedesktop.host.portal.Registry", "Register",
                               GLib.Variant("(sa{sv})", (app_id, {})), None, Gio.DBusCallFlags.NONE, 5000, None)
            self.events.append("register ok")
        except GLib.Error as e:
            self.events.append(f"register error: {e.message}")
        self.session = None

    def _request(self, method: str, args: list, options: dict, on_wait=None):
        import secrets
        Gio, GLib = self.Gio, self.GLib
        token = "n152_" + secrets.token_hex(6)
        options = dict(options)
        options["handle_token"] = GLib.Variant("s", token)
        path = f"{self.PATH}/request/{self.sender}/{token}"
        got, loop = {}, GLib.MainLoop()

        def on_response(_c, _s, _p, _i, _sig, params):
            got["code"], got["results"] = params.unpack()
            loop.quit()

        sub = self.bus.signal_subscribe(self.BUS, "org.freedesktop.portal.Request", "Response", path, None,
                                        Gio.DBusSignalFlags.NO_MATCH_RULE, on_response)
        sig = "(" + "".join(a[0] for a in args) + "a{sv})"
        self.bus.call_sync(self.BUS, self.PATH, self.RD, method,
                           GLib.Variant(sig, tuple(a[1] for a in args) + (options,)), GLib.VariantType("(o)"),
                           Gio.DBusCallFlags.NONE, int(self.timeout * 1000), None)
        t_end = time.monotonic() + self.timeout

        def tick():
            if on_wait is not None:
                on_wait()
            if time.monotonic() > t_end:
                loop.quit()
                return False
            return "code" not in got

        GLib.timeout_add(100, tick)
        loop.run()
        self.bus.signal_unsubscribe(sub)
        if "code" not in got:
            raise TimeoutError(f"{method}: no answer")
        self.events.append(f"{method} {got['code']}")
        if got["code"] != 0:
            raise RuntimeError(f"{method}: response {got['code']}")
        return got["results"]

    def connect(self, on_wait=None, timeout: float = 30.0) -> int:
        import secrets
        GLib = self.GLib
        self.timeout = timeout
        r = self._request("CreateSession", [], {"session_handle_token": GLib.Variant("s", "n152s" + secrets.token_hex(4))})
        self.session = r["session_handle"]
        self._request("SelectDevices", [("o", self.session)],
                      {"types": GLib.Variant("u", OEFFIS_KEYBOARD | OEFFIS_POINTER), "persist_mode": GLib.Variant("u", 0)})
        r = self._request("Start", [("o", self.session), ("s", "")], {}, on_wait)
        self.events.append(f"devices {r.get('devices')}")
        out = self.bus.call_with_unix_fd_list_sync(self.BUS, self.PATH, self.RD, "ConnectToEIS",
                                                   GLib.Variant("(oa{sv})", (self.session, {})),
                                                   GLib.VariantType("(h)"), self.Gio.DBusCallFlags.NONE, 5000,
                                                   None, None)
        return out[1].get(out[0].unpack()[0])

    def close(self) -> None:
        if self.session:
            try:
                self.bus.call_sync(self.BUS, self.session, "org.freedesktop.portal.Session", "Close", None, None,
                                   self.Gio.DBusCallFlags.NONE, 3000, None)
            except self.GLib.Error:
                pass
            self.session = None


class Keyboard:
    """An ei sender bound to the seat's keyboard; typing = key press/release + frame."""

    def __init__(self, eis_fd: int, name: str = "aurora-desk-banco"):
        self.ei = _ei.ei_new_sender(None)
        _ei.ei_configure_name(self.ei, name.encode())
        rc = _ei.ei_setup_backend_fd(self.ei, eis_fd)
        if rc != 0:
            raise RuntimeError(f"ei_setup_backend_fd {rc}")
        self.kbd = None
        self.seq = 0
        self.log = []

    def _pump(self, until, timeout: float):
        fd = _ei.ei_get_fd(self.ei)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                _ei.ei_dispatch(self.ei)
            e = _ei.ei_get_event(self.ei)
            while e:
                t = _ei.ei_event_type_to_string(_ei.ei_event_get_type(e)).decode()
                self.log.append(t)
                if t.endswith("SEAT_ADDED"):
                    seat = _ei.ei_event_get_seat(e)
                    caps = [k for k, v in CAPS.items() if _ei.ei_seat_has_capability(seat, v)]
                    self.log.append(f"seat caps {caps}")
                    _ei.ei_seat_bind_capabilities(seat, ctypes.c_int(CAPS["KEYBOARD"]), ctypes.c_int(0))
                elif t.endswith("DEVICE_ADDED"):
                    dev = _ei.ei_event_get_device(e)
                    if _ei.ei_device_has_capability(dev, CAPS["KEYBOARD"]):
                        self.kbd = dev
                        self.log.append(f"keyboard {_ei.ei_device_get_name(dev)}")
                elif t.endswith("DEVICE_RESUMED") and self.kbd is not None:
                    self.seq += 1
                    _ei.ei_device_start_emulating(self.kbd, self.seq)
                    self.resumed = True
                elif t.endswith("DISCONNECT"):
                    _ei.ei_event_unref(e)
                    raise RuntimeError("ei disconnected")
                _ei.ei_event_unref(e)
                e = _ei.ei_get_event(self.ei)
            if until():
                return True
        return False

    def ready(self, timeout: float = 10.0) -> bool:
        self.resumed = False
        return self._pump(lambda: self.kbd is not None and self.resumed, timeout)

    def key(self, code: int, press: bool) -> None:
        _ei.ei_device_keyboard_key(self.kbd, code, press)
        _ei.ei_device_frame(self.kbd, _ei.ei_now(self.ei))
        _ei.ei_dispatch(self.ei)

    def tap(self, *names: str, gap: float = 0.02) -> None:
        """A chord: names pressed in order, released in reverse (e.g. tap("Ctrl", "s"))."""
        codes = [keycode(n) for n in names]
        for c in codes:
            self.key(c, True)
            time.sleep(gap)
        for c in reversed(codes):
            self.key(c, False)
            time.sleep(gap)
        self._pump(lambda: False, 0.01)

    def type(self, text: str, gap: float = 0.02) -> None:
        for ch in text:
            if ch not in _CHAR:
                raise KeyError(f"not typeable with the US table: {ch!r}")
            code, shift = _CHAR[ch]
            if shift:
                self.key(_KEYS["Shift"], True)
            self.key(code, True)
            time.sleep(gap)
            self.key(code, False)
            if shift:
                self.key(_KEYS["Shift"], False)
            time.sleep(gap)
        self._pump(lambda: False, 0.01)

    def close(self) -> None:
        if self.kbd is not None:
            _ei.ei_device_stop_emulating(self.kbd)
        _ei.ei_disconnect(self.ei)
        _ei.ei_unref(self.ei)
        self.ei = None
