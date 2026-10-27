# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import socket
import threading

from aurora import sys_ups


def fake_nut(vars_: dict, logins: list) -> str:
    """A NUT server on a free local port, answering LIST VAR for «ups» and recording the login."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        f = conn.makefile("rw", encoding="utf-8", newline="\n")
        for line in f:
            cmd = line.strip()
            if cmd.startswith(("USERNAME", "PASSWORD", "LOGIN")):
                logins.append(cmd.split()[0])
                f.write("OK\n")
            elif cmd == "LIST VAR ups":
                f.write("BEGIN LIST VAR ups\n" + "".join(f'VAR ups {k} "{v}"\n' for k, v in vars_.items())
                        + "END LIST VAR ups\n")
            elif cmd.startswith("LIST VAR"):
                f.write("ERR UNKNOWN-UPS\n")
            elif cmd == "LOGOUT":
                f.write("OK Goodbye\n")
                f.flush()
                break
            f.flush()
        conn.close()
        srv.close()
    threading.Thread(target=serve, daemon=True).start()
    return f"127.0.0.1:{srv.getsockname()[1]}"


def test_the_client_reads_the_variables_and_logs_in_as_a_secondary():
    logins = []
    c = sys_ups.Client(fake_nut({"ups.status": "OB DISCHRG", "battery.charge": "54"}, logins), "ups", "mon", "pw")
    v = c.vars()
    c.close()
    assert v == {"ups.status": "OB DISCHRG", "battery.charge": "54"} and logins == ["USERNAME", "PASSWORD", "LOGIN"]


def test_low_only_on_battery_or_when_the_server_forces_it():
    assert not sys_ups.judge({"ups.status": "OL CHRG LB", "battery.charge": "10"}, 30, 300)["low"]   # charging
    assert sys_ups.judge({"ups.status": "OB LB"}, 30, 300)["low"]
    assert sys_ups.judge({"ups.status": "OB", "battery.charge": "30"}, 30, 300)["low"]
    assert sys_ups.judge({"ups.status": "OB", "battery.charge": "80", "battery.runtime": "240"}, 30, 300)["low"]
    assert not sys_ups.judge({"ups.status": "OB", "battery.charge": "80", "battery.runtime": "900"}, 30, 300)["low"]
    assert sys_ups.judge({"ups.status": "OL FSD"}, 30, 300)["low"]


class FakeClient:
    reads: list = []

    def __init__(self, server, *_a):
        self.server = server

    def vars(self):
        v = FakeClient.reads.pop(0)
        if v is None:
            raise OSError("refused")
        return v

    def close(self):
        pass


def watch(cfg, mode):
    cfg.values.update({"AURORA_UPS_MODE": mode, "AURORA_UPS_SERVERS": ["a", "b"]})
    told, off = [], []
    w = sys_ups.Watch(cfg, connect=FakeClient, poweroff=lambda: off.append(1), tell=lambda e, *_: told.append(e))
    return w, told, off


def test_power_lost_low_twice_then_poweroff(cfg):
    w, told, off = watch(cfg, "shutdown")
    FakeClient.reads = [{"ups.status": "OL"}, {"ups.status": "OB", "battery.charge": "60"},
                        {"ups.status": "OB", "battery.charge": "25"}, {"ups.status": "OB", "battery.charge": "24"},
                        {"ups.status": "OB", "battery.charge": "23"}]
    events = [w.step(now=t) for t in range(5)]
    assert events[1] == ["power_lost"] and events[2] == [] and events[3] == ["low", "shutdown"] and events[4] == []
    assert off == [1] and told == ["ups.power_lost", "ups.shutdown"]
    assert sys_ups.status(cfg)["on_battery"] is True


def test_notify_mode_never_powers_off_and_power_back_resets(cfg):
    w, told, off = watch(cfg, "notify")
    FakeClient.reads = [{"ups.status": "OB LB"}, {"ups.status": "OB LB"}, {"ups.status": "OB LB"}, {"ups.status": "OL"}]
    for t in range(4):
        w.step(now=t)
    assert off == [] and told == ["ups.power_lost", "ups.low", "ups.power_back"]


def test_a_server_down_is_told_after_five_minutes_and_the_next_one_is_tried(cfg):
    w, told, off = watch(cfg, "shutdown")
    FakeClient.reads = [None, None, None, None, {"ups.status": "OL"}]
    assert w.step(now=0) == [] and w.step(now=301) == ["unreachable"]      # each read: a, then b
    assert w.step(now=320) == ["reachable"] and off == []
    assert not sys_ups.status(cfg).get("error")


def test_the_power_off_rule_only_in_shutdown_mode():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("sis", Path(__file__).resolve().parents[1] / "script" /
                                                  "sys_install_services.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rule = mod.POLKIT.substitute(user="u", power=mod.POWER.substitute(user="u"))
    assert "login1.power-off" in rule and "login1" not in mod.POLKIT.substitute(user="u", power="")


def test_the_firewall_goes_down_first_only_when_chosen(cfg):
    for chosen, expect in ((True, ["fw", "off"]), (False, ["off"])):
        cfg.values.update({"AURORA_UPS_MODE": "shutdown", "AURORA_UPS_SERVERS": ["a"], "AURORA_UPS_FIREWALL_OFF": chosen})
        order = []
        w = sys_ups.Watch(cfg, connect=FakeClient, poweroff=lambda: order.append("off"), tell=lambda *a: None,
                          firewall_off=lambda: order.append("fw"))
        FakeClient.reads = [{"ups.status": "OB LB"}, {"ups.status": "OB LB"}]
        w.step(now=0)
        w.step(now=1)
        assert order == expect


def test_a_firewall_that_cannot_be_shut_down_never_stops_the_power_off(cfg):
    cfg.values.update({"AURORA_UPS_MODE": "shutdown", "AURORA_UPS_SERVERS": ["a"], "AURORA_UPS_FIREWALL_OFF": True})
    off = []

    def fail():
        raise RuntimeError("no console")
    w = sys_ups.Watch(cfg, connect=FakeClient, poweroff=lambda: off.append(1), tell=lambda *a: None, firewall_off=fail)
    FakeClient.reads = [{"ups.status": "OB LB"}, {"ups.status": "OB LB"}]
    w.step(now=0)
    assert "firewall_off" in w.step(now=1) and off == [1]
