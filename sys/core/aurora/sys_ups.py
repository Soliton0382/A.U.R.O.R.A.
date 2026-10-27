# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The UPS: power lost, power back, and this computer shut down cleanly before the battery is flat (owner, 2026-10-28:
«la possibilità di gestire spegnimento per batteria ups quasi scarica… ups collegato via usb o via web (il mio nas può
gestire il server ups)»).

Aurora speaks the network UPS protocol (NUT, TCP 3493), which NAS units serve for the UPS plugged into them and
which a local NUT server serves for a UPS on this computer's USB: so one client covers both. AURORA_UPS_SERVERS are
tried in order (host or host:port); with a user, Aurora logs in as a secondary so the UPS's server waits for it before
cutting the power.

The watch (aurora-rem's thread, every POLL_S): on battery → a notification; back on the mains → another; low —
the UPS's own LB, a forced shutdown (FSD) from its server, or charge/runtime under AURORA_UPS_SHUTDOWN_CHARGE /
AURORA_UPS_SHUTDOWN_RUNTIME_S while on battery — seen CONFIRM reads in a row → with AURORA_UPS_MODE shutdown, a last
notification, the firewall shut down too with AURORA_UPS_FIREWALL_OFF (sec_fwpower), and `systemctl poweroff`
(allowed by Aurora's polkit rule); with notify, only told.
"""
from __future__ import annotations

import json
import socket
import subprocess
import time

from . import sys_config, sys_log

PORT = 3493
POLL_S = 15
CONFIRM = 2                                   # low seen twice in a row (30 s): one odd read never powers off
KEEP = ("ups.status", "battery.charge", "battery.runtime", "input.voltage", "ups.load", "ups.model", "ups.mfr",
        "device.model", "device.mfr")


class NutError(RuntimeError):
    pass


class Client:
    """One connection to a NUT server: LIST VAR, and the optional login as a secondary."""

    def __init__(self, server: str, ups: str, user: str = "", password: str = "", timeout: float = 5.0):
        self.server, self.ups = server.strip(), ups
        host, sep, port = self.server.rpartition(":")
        if not sep or not port.isdigit():
            host, port = self.server, str(PORT)
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        self.f = self.sock.makefile("rw", encoding="utf-8", newline="\n")
        if user:
            for cmd in (f"USERNAME {user}", f"PASSWORD {password}", f"LOGIN {ups}"):
                self._ok(cmd)

    def _say(self, cmd: str) -> str:
        self.f.write(cmd + "\n")
        self.f.flush()
        line = self.f.readline()
        if not line:
            raise NutError("connection closed")
        return line.strip()

    def _ok(self, cmd: str) -> None:
        r = self._say(cmd)
        if not r.startswith("OK"):
            raise NutError(f"{cmd.split()[0]}: {r}")

    def vars(self) -> dict:
        first = self._say(f"LIST VAR {self.ups}")
        if not first.startswith("BEGIN"):
            raise NutError(first)                       # ERR ACCESS-DENIED, ERR UNKNOWN-UPS…
        out = {}
        while (line := self.f.readline().strip()) and not line.startswith("END"):
            _, _, name, value = line.split(" ", 3)
            out[name] = value.strip('"')
        return out

    def close(self) -> None:
        try:
            self.f.write("LOGOUT\n")
            self.f.flush()
        except OSError:
            pass
        self.sock.close()


def judge(v: dict, charge_min: float, runtime_min: float) -> dict:
    """What the UPS's variables say: on battery, low (LB, FSD, or under the limits while on battery)."""
    flags = set(str(v.get("ups.status", "")).split())
    on_battery = "OB" in flags
    charge = _num(v.get("battery.charge"))
    runtime = _num(v.get("battery.runtime"))
    why = []
    if "FSD" in flags:
        why.append("forced shutdown from the UPS's server")
    if on_battery and "LB" in flags:
        why.append("the UPS says low battery")
    if on_battery and charge is not None and charge <= charge_min:
        why.append(f"charge {charge:.0f} % ≤ {charge_min:.0f} %")
    if on_battery and runtime is not None and runtime <= runtime_min:
        why.append(f"runtime {runtime:.0f} s ≤ {runtime_min:.0f} s")
    return {"on_battery": on_battery, "online": "OL" in flags, "low": bool(why), "why": why,
            "charge": charge, "runtime": runtime, "flags": sorted(flags)}


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class Watch:
    """The state between two reads; step() returns the events of this read."""

    def __init__(self, cfg: sys_config.Config, connect=Client, poweroff=None, tell=None, firewall_off=None):
        self.cfg, self.connect = cfg, connect
        self.poweroff = poweroff or _poweroff
        self.firewall_off = firewall_off or (lambda: _firewall_off(cfg))
        self.tell = tell or (lambda event, title, body: _tell(cfg, event, title, body))
        self.client: Client | None = None
        self.was_battery = False
        self.lows = 0
        self.down_since: float | None = None
        self.told_down = self.told_low = self.shutting = False
        self.log = sys_log.get_logger("ups")

    def _read(self) -> tuple[dict, str]:
        if self.client:
            try:
                return self.client.vars(), self.client.server
            except (OSError, NutError):
                self.client.close()
                self.client = None
        errors = []
        for server in self.cfg["AURORA_UPS_SERVERS"]:
            try:
                self.client = self.connect(server, self.cfg["AURORA_UPS_NAME"], self.cfg["AURORA_UPS_USER"],
                                           self.cfg["AURORA_UPS_PASSWORD"])
                return self.client.vars(), server
            except (OSError, NutError) as e:
                errors.append(f"{server}: {e}")
                self.client = None
        raise NutError("; ".join(errors) or "no UPS server set")

    def step(self, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        events: list[str] = []
        try:
            v, server = self._read()
        except NutError as e:
            self.down_since = now if self.down_since is None else self.down_since
            if now - self.down_since >= 300 and not self.told_down:     # 5 minutes: not a blip
                self.told_down = True
                events.append("unreachable")
                self.log.warning("UPS server not reachable for 5 minutes: %s", e)
            _save(self.cfg, {"at": now, "reachable": False, "error": str(e)[:300]})
            return events
        if self.told_down:
            events.append("reachable")
        self.down_since, self.told_down = None, False
        j = judge(v, self.cfg["AURORA_UPS_SHUTDOWN_CHARGE"], self.cfg["AURORA_UPS_SHUTDOWN_RUNTIME_S"])
        state = f"{j['charge']:.0f} %" if j["charge"] is not None else "?"
        if j["runtime"] is not None:
            state += f", {j['runtime'] / 60:.0f} min"
        if j["on_battery"] and not self.was_battery:
            events.append("power_lost")
            self.tell("ups.power_lost", "⚡ Corrente mancata: Aurora va a batteria", f"UPS {state}")
        if self.was_battery and not j["on_battery"]:
            events.append("power_back")
            self.lows, self.told_low = 0, False
            self.tell("ups.power_back", "🔌 Corrente tornata", f"UPS {state}")
        self.was_battery = j["on_battery"]
        self.lows = self.lows + 1 if j["low"] else 0
        if self.lows >= CONFIRM and not self.shutting:
            events.append("low")
            why = ", ".join(j["why"])
            if self.cfg["AURORA_UPS_MODE"] == "shutdown":
                self.shutting = True
                events.append("shutdown")
                self.log.warning("UPS low (%s): powering off", why)
                self.tell("ups.shutdown", "🔋 Batteria quasi scarica: spengo il computer", f"{why}. UPS {state}")
                if self.cfg["AURORA_UPS_FIREWALL_OFF"]:     # after the last notification: without it nothing goes out
                    events.append("firewall_off")
                    try:
                        self.firewall_off()
                    except Exception as e:  # noqa: BLE001 — this computer is powered off whatever the firewall did
                        self.log.warning("UPS: the firewall not shut down: %s", e)
                self.poweroff()
            elif not self.told_low:
                self.told_low = True
                self.log.warning("UPS low (%s): mode notify, not powering off", why)
                self.tell("ups.low", "🔋 Batteria UPS quasi scarica", f"{why}. Lo spegnimento automatico è spento.")
        _save(self.cfg, {"at": now, "reachable": True, "server": server, **j,
                         "vars": {k: v[k] for k in KEEP if k in v}, "mode": self.cfg["AURORA_UPS_MODE"]})
        return events


def _save(cfg: sys_config.Config, state: dict) -> None:
    f = cfg.path("AURORA_STATUS_DIR") / "ups.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def status(cfg: sys_config.Config) -> dict:
    """The last read, for the page and the health."""
    f = cfg.path("AURORA_STATUS_DIR") / "ups.json"
    try:
        st = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    return {"mode": cfg["AURORA_UPS_MODE"], "servers": len(cfg["AURORA_UPS_SERVERS"]), **st}


def _tell(cfg: sys_config.Config, event: str, title: str, body: str) -> None:
    from . import sys_push
    msg = {"title": title, "body": body, "view": "status", "tag": "aurora-ups"}
    try:
        sys_push.send(msg, cfg)
        sys_push.remember(msg, event, ["push"], cfg)
    except Exception as e:  # noqa: BLE001 — the power-off never waits on a notification
        sys_log.get_logger("ups").warning("UPS notification not sent: %s", e)


def _firewall_off(cfg: sys_config.Config) -> None:
    from . import sec_fwpower
    sec_fwpower.act(cfg, "shutdown")


def _poweroff() -> None:
    # systemd stops every service in order (Aurora's units first among them) before the power goes
    subprocess.run(["systemctl", "poweroff"], capture_output=True, timeout=60)
