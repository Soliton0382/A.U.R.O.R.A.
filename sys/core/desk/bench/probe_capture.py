# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A capture client of the bench, standing in for aurora-desk (F2, F13, F14; frames for F1's oracle).

    python3 -I -B probe_capture.py --out result.json [--dumpable 0|1] [--register APP_ID] [--frames N]
                                   [--save-frame raw.bin] [--hold SECONDS]

Opens a ScreenCast session on the bench portal with persist_mode = 0, connects the PipeWire stream through
GStreamer (pipewiresrc) and counts frames. Writes one JSON result; never keeps a restore token.
With --dumpable 0 the very first thing it does is prctl(PR_SET_DUMPABLE, 0) through ctypes (os.prctl does not exist).
"""
import ctypes
import sys

PR_SET_DUMPABLE, PR_GET_DUMPABLE = 4, 3


def _early_dumpable() -> None:
    if "--dumpable" in sys.argv and sys.argv[sys.argv.index("--dumpable") + 1] == "0":
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
            sys.exit(f"prctl failed errno={ctypes.get_errno()}")


_early_dumpable()                                      # first instruction, before any other import

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import secrets  # noqa: E402
import time  # noqa: E402

import gi  # noqa: E402

gi.require_version("Gst", "1.0")
from gi.repository import Gio, GLib, Gst  # noqa: E402

BUS, PATH = "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
SC = "org.freedesktop.portal.ScreenCast"


class Portal:
    def __init__(self, timeout: float):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")
        self.timeout = timeout
        self.loop = GLib.MainLoop()

    def call(self, iface, method, params, reply="(o)", fds=None):
        r = self.bus.call_with_unix_fd_list_sync(BUS, PATH, iface, method, params, GLib.VariantType(reply),
                                                 Gio.DBusCallFlags.NONE, int(self.timeout * 1000), fds, None)
        return r

    def request(self, iface, method, args: list, options: dict):
        """Call a portal method that answers with a Request; return (response code, results dict, seconds)."""
        token = "n152_" + secrets.token_hex(6)
        options = dict(options)
        options["handle_token"] = GLib.Variant("s", token)
        path = f"{PATH}/request/{self.sender}/{token}"
        got = {}

        def on_response(_c, _s, _p, _i, _sig, params):
            code, results = params.unpack()
            got["code"], got["results"] = code, results
            self.loop.quit()

        sub = self.bus.signal_subscribe(BUS, "org.freedesktop.portal.Request", "Response", path, None,
                                        Gio.DBusSignalFlags.NO_MATCH_RULE, on_response)
        t0 = time.monotonic()
        sig = "(" + "".join(a[0] for a in args) + "a{sv})"
        params = GLib.Variant(sig, tuple(a[1] for a in args) + (options,))
        self.call(iface, method, params)
        tid = GLib.timeout_add(int(self.timeout * 1000), self.loop.quit)
        self.loop.run()
        GLib.source_remove(tid) if "code" in got else None
        self.bus.signal_unsubscribe(sub)
        if "code" not in got:
            return None, {}, time.monotonic() - t0
        return got["code"], got["results"], time.monotonic() - t0


def serve_frames(fd: int, node: int, save: str, ready: str) -> None:
    """Keep the stream; on SIGUSR1 write the latest frame to save (atomically), until SIGTERM."""
    import signal
    Gst.init(None)
    pipe = Gst.parse_launch(f"pipewiresrc fd={fd} path={node} always-copy=true ! videoconvert ! "
                            "video/x-raw,format=RGBx ! fakesink name=sink signal-handoffs=true sync=false")
    st = {"last": None, "n": 0, "dims": None}
    loop = GLib.MainLoop()

    def handoff(_sink, buf, pad):
        ok, info = buf.map(Gst.MapFlags.READ)
        if ok:
            st["last"] = bytes(info.data)
            buf.unmap(info)
            st["n"] += 1
            if st["dims"] is None:
                c = pad.get_current_caps().get_structure(0)
                st["dims"] = (c.get_value("width"), c.get_value("height"))

    def dump():
        if st["last"] is not None:
            with open(save + ".tmp", "wb") as f:
                f.write(st["last"])
            os.replace(save + ".tmp", save)
            with open(save + ".json.tmp", "w") as f:
                json.dump({"frames": st["n"], "dims": st["dims"], "t": time.time()}, f)
            os.replace(save + ".json.tmp", save + ".json")
        return True

    pipe.get_by_name("sink").connect("handoff", handoff)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, dump)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (loop.quit(), False)[1])
    pipe.set_state(Gst.State.PLAYING)
    with open(ready, "w") as f:
        f.write(str(os.getpid()))
    loop.run()
    pipe.set_state(Gst.State.NULL)


def count_frames(fd: int, node: int, want: int, timeout: float, save: str = "") -> dict:
    Gst.init(None)
    pipe = Gst.parse_launch(f"pipewiresrc fd={fd} path={node} always-copy=true ! videoconvert ! "
                            "video/x-raw,format=RGBx ! fakesink name=sink signal-handoffs=true sync=false")
    sink = pipe.get_by_name("sink")
    st = {"frames": 0, "first_s": None, "caps": None, "saved": False}
    t0 = time.monotonic()
    loop = GLib.MainLoop()

    def handoff(_sink, buf, pad):
        st["frames"] += 1
        if st["first_s"] is None:
            st["first_s"] = time.monotonic() - t0
        if save and not st["saved"]:                    # KWin sends frames on damage: a still screen gives one
            caps = pad.get_current_caps().get_structure(0)
            st["caps"] = {"w": caps.get_value("width"), "h": caps.get_value("height")}
            ok, info = buf.map(Gst.MapFlags.READ)
            if ok:
                with open(save, "wb") as f:
                    f.write(bytes(info.data))
                buf.unmap(info)
                st["saved"] = True
        if st["frames"] >= want and (not save or st["saved"]):
            GLib.idle_add(loop.quit)

    sink.connect("handoff", handoff)
    bus = pipe.get_bus()
    bus.add_signal_watch()

    def on_msg(_b, msg):
        if msg.type == Gst.MessageType.ERROR:
            st["error"] = str(msg.parse_error()[0].message)
            loop.quit()

    bus.connect("message", on_msg)
    pipe.set_state(Gst.State.PLAYING)
    tid = GLib.timeout_add(int(timeout * 1000), loop.quit)
    loop.run()
    GLib.source_remove(tid) if st["frames"] >= want else None
    pipe.set_state(Gst.State.NULL)
    return st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dumpable", default="1")
    ap.add_argument("--register", default="")
    ap.add_argument("--frames", type=int, default=1)
    ap.add_argument("--save-frame", default="")
    ap.add_argument("--hold", type=float, default=0.0)
    ap.add_argument("--timeout", type=float, default=25.0)
    ap.add_argument("--serve", default="", help="ready file: keep the stream, SIGUSR1 writes --save-frame")
    a = ap.parse_args()
    libc = ctypes.CDLL(None, use_errno=True)
    res = {"pid": os.getpid(), "dumpable": libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0), "t_start": time.time()}
    try:
        p = Portal(a.timeout)
        if a.register:
            try:
                p.bus.call_sync(BUS, PATH, "org.freedesktop.host.portal.Registry", "Register",
                                GLib.Variant("(sa{sv})", (a.register, {})), None, Gio.DBusCallFlags.NONE,
                                5000, None)
                res["register"] = "ok"
            except GLib.Error as e:
                res["register"] = f"error: {e.message}"
        code, r, dt = p.request(SC, "CreateSession", [],
                                {"session_handle_token": GLib.Variant("s", "n152s" + secrets.token_hex(4))})
        res["create"] = {"code": code, "s": dt}
        if code != 0:
            raise RuntimeError(f"CreateSession code={code}")
        session = r["session_handle"]
        code, r, dt = p.request(SC, "SelectSources", [("o", session)],
                                {"types": GLib.Variant("u", 1), "multiple": GLib.Variant("b", False),
                                 "persist_mode": GLib.Variant("u", 0)})
        res["select"] = {"code": code, "s": dt}
        if code != 0:
            raise RuntimeError(f"SelectSources code={code}")
        res["t_start_call"] = time.time()
        code, r, dt = p.request(SC, "Start", [("o", session), ("s", "")], {})
        res["start"] = {"code": code, "s": dt, "t_answer": time.time(),
                        "restore_token": bool(r.get("restore_token")) if r else False,
                        "streams": len(r.get("streams", [])) if r else 0}
        if code != 0:
            raise RuntimeError(f"Start code={code}")
        node = r["streams"][0][0]
        out = p.bus.call_with_unix_fd_list_sync(BUS, PATH, SC, "OpenPipeWireRemote",
                                                GLib.Variant("(oa{sv})", (session, {})), GLib.VariantType("(h)"),
                                                Gio.DBusCallFlags.NONE, 5000, None, None)
        fd = out[1].get(out[0].unpack()[0])
        res["node"] = node
        if a.serve:
            with open(a.out, "w") as f:
                json.dump(res, f)
            serve_frames(fd, node, a.save_frame, a.serve)
            return 0
        res["capture"] = count_frames(fd, node, a.frames, a.timeout, a.save_frame)
        if a.hold:
            time.sleep(a.hold)
        try:
            p.bus.call_sync(BUS, session, "org.freedesktop.portal.Session", "Close", None, None,
                            Gio.DBusCallFlags.NONE, 3000, None)
        except GLib.Error:
            pass
    except Exception as e:                              # noqa: BLE001 — one JSON result, whatever failed
        res["error"] = f"{type(e).__name__}: {e}"
    with open(a.out, "w") as f:
        json.dump(res, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
