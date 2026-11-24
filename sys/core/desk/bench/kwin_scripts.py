# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""KWin scripts on the bench's virtual KWin (F1): the reader aurora-desk would use, and the bench's director.

The reader is what is measured: PID, internal id, transient relation, stacking order, «keep above», geometry and
cursor position (read only), sent back over the bench bus with callDBus. The director only arranges the scenario
(geometry, keep above, raise order); it is a separate script and never reports what the reader reports.
Each run: Scripting.loadScript(file, unique name) -> Script<id>.run() -> the script calls back -> unloadScript.
Latency = from the loadScript call to the callback arriving.
"""
import json
import os
import time
from pathlib import Path

from gi.repository import Gio, GLib

SERVICE, OBJ, IFACE = "org.n152.Bench", "/Report", "org.n152.Bench"
XML = f"""<node><interface name="{IFACE}"><method name="Report"><arg type="s" name="json" direction="in"/>
</method></interface></node>"""

READER_JS = """
var out = {windows: [], cursor: {x: workspace.cursorPos.x, y: workspace.cursorPos.y}};
var order = workspace.stackingOrder;
for (var i = 0; i < order.length; i++) {
    var w = order[i];
    var g = w.frameGeometry, c = w.clientGeometry;
    out.windows.push({
        id: w.internalId.toString(), pid: w.pid, caption: w.caption,
        transient: w.transient, transientFor: w.transientFor ? w.transientFor.internalId.toString() : null,
        keepAbove: w.keepAbove, normal: w.normalWindow, dialog: w.dialog,
        frame: [g.x, g.y, g.width, g.height], client: c ? [c.x, c.y, c.width, c.height] : null
    });
}
callDBus("%(service)s", "%(obj)s", "%(iface)s", "Report", JSON.stringify(out));
"""

DIRECTOR_JS = """
var plan = %(plan)s;
var byCap = {};
var all = workspace.windowList();
for (var i = 0; i < all.length; i++) { byCap[all[i].caption] = all[i]; }
var missing = [];
for (var k = 0; k < plan.length; k++) {
    var p = plan[k], w = byCap[p.title];
    if (!w) { missing.push(p.title); continue; }
    w.keepAbove = p.above;
    w.frameGeometry = {x: p.x, y: p.y, width: p.w, height: p.h};
}
for (var k = 0; k < plan.length; k++) {
    var w = byCap[plan[k].title];
    if (w) { workspace.raiseWindow(w); }
}
callDBus("%(service)s", "%(obj)s", "%(iface)s", "Report", JSON.stringify({director: true, missing: missing}));
"""


class KWinScripts:
    def __init__(self, workdir: Path):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.inbox = []
        node = Gio.DBusNodeInfo.new_for_xml(XML)
        self.reg = self.bus.register_object(OBJ, node.interfaces[0], self._on_call, None, None)
        self.owner = Gio.bus_own_name_on_connection(self.bus, SERVICE, Gio.BusNameOwnerFlags.NONE, None, None)
        self.n = 0
        self._pump(0.3)

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        self.inbox.append((time.monotonic(), params.unpack()[0]))
        invocation.return_value(None)

    def _pump(self, seconds: float) -> None:
        ctx = GLib.MainContext.default()
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds:
            ctx.iteration(False)
            time.sleep(0.0005)

    def _call(self, path, iface, method, params=None, reply=None):
        return self.bus.call_sync("org.kde.KWin", path, iface, method, params,
                                  GLib.VariantType(reply) if reply else None, Gio.DBusCallFlags.NONE, 5000, None)

    def run(self, js: str, timeout: float = 5.0):
        """Load, run and unload one script; return (payload dict or None, latency seconds)."""
        self.n += 1
        name = f"n152_{os.getpid()}_{self.n}"
        f = self.workdir / f"{name}.js"
        f.write_text(js)
        self.inbox.clear()
        t0 = time.monotonic()
        sid = self._call("/Scripting", "org.kde.kwin.Scripting", "loadScript",
                         GLib.Variant("(ss)", (str(f), name)), "(i)").unpack()[0]
        self._call(f"/Scripting/Script{sid}", "org.kde.kwin.Script", "run")
        ctx = GLib.MainContext.default()
        while not self.inbox and time.monotonic() - t0 < timeout:
            ctx.iteration(False)
        got = self.inbox[0] if self.inbox else None
        try:
            self._call("/Scripting", "org.kde.kwin.Scripting", "unloadScript", GLib.Variant("(s)", (name,)), "(b)")
        except GLib.Error:
            pass
        if got is None:
            return None, None
        return json.loads(got[1]), got[0] - t0

    def read(self):
        return self.run(READER_JS % {"service": SERVICE, "obj": OBJ, "iface": IFACE})

    def direct(self, plan: list):
        return self.run(DIRECTOR_JS % {"plan": json.dumps(plan), "service": SERVICE, "obj": OBJ, "iface": IFACE})
