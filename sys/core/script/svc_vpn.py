#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-vpn: the tunnel of Aurora's own internet (net_vpn). The only unit with CAP_NET_ADMIN (its device, its rules,
its table): it reads what the owner wants (prefs.json), runs openvpn with the profile due, sets the routes and the
resolver when the tunnel is up, the kill switch while it is not, and writes what is (state.json).

    svc_vpn.py           the loop (the unit)
    svc_vpn.py hook ...  openvpn's up/down: the tunnel's DNS servers to the loop (run.json)

A profile that does not come up in CONNECT_S, or falls: the next (net_vpn.order); all of them: «failed», tried again
every RETRY_S — the API asks the owner whether to use the unprotected line meanwhile."""
from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import net_vpn as V, net_vpn_dns as D, sys_config, sys_log  # noqa: E402

RUN = Path(os.environ.get("RUNTIME_DIRECTORY") or "/run/aurora-vpn")
CONNECT_S = 40                                     # «Initialization Sequence Completed» within this, or the next profile
RETRY_S = 60                                       # every profile failed: a new round after this
TICK_S = 2
OPENVPN = "/usr/sbin/openvpn"
log = sys_log.get_logger("vpn")


def sh(cmd: list[str], quiet: bool = False) -> bool:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if r.returncode and not quiet:
        log.warning("vpn: %s: %s", " ".join(cmd[:4]), (r.stderr or r.stdout).strip()[:200])
    return r.returncode == 0


def hook(argv: list[str]) -> int:
    """openvpn's up/down: the DNS servers pushed (foreign_option_N «dhcp-option DNS x»), for the loop."""
    dns = [v.split()[-1] for k, v in sorted(os.environ.items()) if k.startswith("foreign_option_") and "DNS" in v.split()]
    (RUN / "run.json").write_text(json.dumps({"script": os.environ.get("script_type", ""), "dns": dns,
                                              "ip": os.environ.get("ifconfig_local", "")}), encoding="utf-8")
    return 0


class Tunnel:
    def __init__(self, cfg):
        self.cfg, self.uid = cfg, pwd.getpwnam(sys_config.service_user(cfg)).pw_uid
        self.proc, self.pid, self.started, self.failed = None, None, 0.0, set()
        self.rules_on, self.nft_id, self.round_at, self.up = False, None, 0.0, False
        self.dns: list[str] = []                           # the tunnel's DNS servers (pushed), the resolver's upstream
        self.ups, self.resets, self.last_reset, self.up_at = 0, 0, 0.0, 0.0   # the page's statistics, since the unit started

    # ---- the routes --------------------------------------------------------------------------------------------------
    def guard(self, on: bool) -> None:
        """The rules in place (the service user's traffic by the table) or gone (the normal line, as before)."""
        if on and not self.rules_on:
            for c in V.rules(self.uid, False):
                sh(c, quiet=True)                          # a rule left by a crash: never twice
            for c in V.rules(self.uid, True) + V.table(self.up):
                sh(c)
            self.rules_on = True
        elif not on and self.rules_on:
            for c in V.rules(self.uid, False):
                sh(c, quiet=True)
            self.rules_on = False
        if on:
            self.exclude(V.bypass(V.prefs(self.cfg)))
        elif self.nft_id is not None:
            sh(["nft", "delete", "table", "inet", "aurora_vpn"], quiet=True)
            self.nft_id = None

    def exclude(self, units: list[str]) -> None:
        """The services not ticked outside: nftables matches a cgroup by its id, and a restarted unit is a new id —
        so the rules are loaded again whenever the running ones' ids change (a unit not running: not in them)."""
        cg = Path("/sys/fs/cgroup/system.slice")
        live = tuple((u, (cg / u).stat().st_ino) for u in units if (cg / u).exists())
        if live == self.nft_id:
            return
        sh(["nft", "delete", "table", "inet", "aurora_vpn"], quiet=True)
        f = RUN / "exclude.nft"
        f.write_text(V.nft_exclusions([u for u, _ in live]), encoding="utf-8")
        sh(["nft", "-f", str(f)])
        self.nft_id = live

    def keep_home(self, found: list[tuple[str, int]]) -> None:
        """A kept domain answered with public addresses: those too on the normal line (net_vpn_dns)."""
        for c in V.nft_split(found):
            sh(c, quiet=True)

    def route(self, up: bool) -> None:
        self.up = up
        for c in V.table(up):
            sh(c)

    # ---- openvpn -----------------------------------------------------------------------------------------------------
    def start(self, pid: str) -> None:
        RUN.mkdir(mode=0o700, exist_ok=True)
        auth = RUN / "auth"
        auth.write_text(V.account(self.cfg), encoding="utf-8")
        auth.chmod(0o600)
        (RUN / "run.json").unlink(missing_ok=True)
        hook_cmd = f'"{sys.executable} {Path(__file__).resolve()} hook"'
        conf = RUN / "client.conf"
        conf.write_text(V.runtime_config(V.profile(self.cfg, pid), RUN, hook_cmd), encoding="utf-8")
        conf.chmod(0o600)
        self.log = open(RUN / "openvpn.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen([OPENVPN, "--config", str(conf), "--cd", str(RUN)], stdout=self.log,
                                     stderr=subprocess.STDOUT, cwd=RUN)
        self.pid, self.started = pid, time.time()
        log.info("vpn: connecting with %s", pid)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc, self.pid = None, None
        for f in ("auth", "client.conf"):
            (RUN / f).unlink(missing_ok=True)

    def ready(self) -> bool:
        try:
            return "Initialization Sequence Completed" in (RUN / "openvpn.log").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False

    def last_error(self) -> str:
        try:
            lines = (RUN / "openvpn.log").read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        bad = [x for x in lines if any(w in x for w in ("AUTH_FAILED", "error", "Error", "ERROR", "failed", "TLS Error"))]
        return (bad or lines or [""])[-1][-200:]

    # ---- one tick ----------------------------------------------------------------------------------------------------
    def tick(self) -> None:
        p = V.prefs(self.cfg)
        p["use"] = V._read(V.folder(self.cfg) / "prefs.json", {}).get("use")
        if not p["on"] or not p["profiles"] or not p["account"]:
            self.stop()
            self.guard(False)
            V.set_dns(self.cfg, None)
            if self.up:
                self.up = False
            V.write_state(self.cfg, phase="off", why="" if p["on"] else "off",
                          missing=[k for k, ok in (("profiles", p["profiles"]), ("account", p["account"])) if not ok])
            return
        if p.get("use") and p["use"] != self.pid:          # the owner chose a profile: that one now
            self.stop()
            self.failed.discard(p["use"])
        alive = self.proc is not None and self.proc.poll() is None
        if alive and self.ready() and self.up and p["reset_h"] and time.time() - self.up_at > p["reset_h"] * 3600:
            # the connection made again on its timer (owner, 30 Oct): the same profile, the kill switch meanwhile
            log.info("vpn: %s made again after %d h", self.pid, p["reset_h"])
            pid = self.pid
            self.route(False)
            self.stop()
            self.resets, self.last_reset = self.resets + 1, time.time()
            self.start(pid)
            V.write_state(self.cfg, phase="connecting", profile=pid, reset=True, **self.stats(p))
            return
        if alive and self.ready():
            if not self.up:
                run = V._read(RUN / "run.json", {})
                self.route(True)
                self.dns = run.get("dns") or []
                V.set_dns(self.cfg, [D.ADDRESS[0]])          # the services ask the resolver here (net_vpn_dns)
                self.failed.clear()
                self._remember(self.pid)
                self.ups, self.up_at = self.ups + 1, time.time()
                log.info("vpn: up with %s", self.pid)
            run = V._read(RUN / "run.json", {})
            V.write_state(self.cfg, phase="up", profile=self.pid, since=self.up_at, dns=run.get("dns") or [],
                          ip=run.get("ip", ""), **self.stats(p))
            self.guard(True)
            return
        if self.up:                                        # it fell: the kill switch at once, then the next profile
            log.warning("vpn: %s fell: %s", self.pid, self.last_error())
            self.route(False)
            V.set_dns(self.cfg, None)
            self.failed.add(self.pid)
            self.stop()
        if alive and time.time() - self.started < CONNECT_S:
            self.guard(self.blocked(p))
            V.write_state(self.cfg, phase="connecting", profile=self.pid, tried=sorted(self.failed))
            return
        if alive or (self.proc is not None):               # not up in time, or ended: failed
            log.warning("vpn: %s did not come up: %s", self.pid, self.last_error())
            self.failed.add(self.pid)
            err = self.last_error()
            self.stop()
        else:
            err = ""
        nxt = V.order(p, self.failed)
        if not p["failover"]:                              # no change of profile by itself: the first one only
            nxt = nxt[:1] if not self.failed else []
        if nxt:
            self.guard(self.blocked(p))
            self.start(nxt[0])
            V.write_state(self.cfg, phase="connecting" if not self.failed else "retrying", profile=nxt[0],
                          tried=sorted(self.failed), error=err)
            return
        # every profile failed: «failed» (the API asks the owner), tried again after RETRY_S
        if not self.round_at:
            self.round_at = time.time()
        self.guard(self.blocked(p))
        V.write_state(self.cfg, phase="failed" if self.blocked(p) else "unprotected", tried=sorted(self.failed),
                      error=err or self.last_error())
        if time.time() - self.round_at > RETRY_S:
            self.failed.clear()
            self.round_at = 0.0

    def stats(self, p: dict) -> dict:
        """The page's statistics: the traffic of this connection, the connections made and the resets since the unit
        started, the last reset and the next one."""
        try:
            moved = V.traffic((RUN / "status").read_text(encoding="utf-8", errors="replace"))
        except OSError:
            moved = {}
        nxt = self.up_at + p["reset_h"] * 3600 if p["reset_h"] and self.up_at else None
        return {**moved, "connections": self.ups, "resets": self.resets, "last_reset": self.last_reset or None,
                "next_reset": nxt}

    @staticmethod
    def blocked(p: dict) -> bool:
        """The tunnel down: Aurora kept off the normal line (the kill switch), unless the owner chose otherwise."""
        return p["killswitch"] and not p["unprotected"]

    def _remember(self, pid: str) -> None:
        """The last used is the default (owner, 30 Oct); the one asked now is asked no more."""
        f = V.folder(self.cfg) / "prefs.json"
        raw = V._read(f, {})
        raw["last"], raw["default"] = pid, pid
        raw.pop("use", None)
        if raw.get("unprotected"):
            raw["unprotected"] = False                     # the tunnel is back: the normal line no more
        V._write(f, raw)


def main() -> int:
    if sys.argv[1:2] == ["hook"]:
        return hook(sys.argv[2:])
    cfg = sys_config.get()
    t = Tunnel(cfg)
    V.set_dns(cfg, None)
    try:                                               # the resolver of the services while the tunnel is up
        D.Forwarder(lambda: V.prefs(cfg)["split"], lambda: V.upstream(V.prefs(cfg), t.dns), t.keep_home, log).start()
    except OSError as e:
        log.warning("vpn: the resolver could not start (%s): the tunnel's names go to the machine's resolver", e)
    log.info("vpn: watching %s", V.folder(cfg))
    try:
        while True:
            try:
                t.tick()
            except Exception as e:  # noqa: BLE001 — the loop never dies: the rules stay as they are
                log.warning("vpn: %s: %s", type(e).__name__, str(e)[:200])
            time.sleep(TICK_S)
    finally:
        t.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
