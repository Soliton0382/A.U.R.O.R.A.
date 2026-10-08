# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Mac backend, checked on any machine with the outputs macOS's tools print (launchctl, system_profiler, sw_vers,
ioreg, ffmpeg's avfoundation). The formats were written from the tools' documented output; a real Mac checks them
again in phase 5 (tests/README: «Non misurato»)."""
import json
from pathlib import Path

import pytest

from aurora.sys_platform import for_system
from aurora.sys_platform.base import Result

RUNNING = """gui/501/com.aurora.api = {
\tactive count = 1
\tpath = /Users/owner1/Library/LaunchAgents/com.aurora.api.plist
\tstate = running

\tprogram = /Users/owner1/Aurora/.venv/bin/python
\truns = 1
\tpid = 4242
\tlast exit code = (never exited)
}
"""
CRASHED = RUNNING.replace("state = running", "state = not running").replace("(never exited)", "1")
STOPPED_CLEAN = RUNNING.replace("state = running", "state = not running").replace("(never exited)", "0")
AVFOUNDATION = """[AVFoundation indev @ 0x7f8b1c004a00] AVFoundation video devices:
[AVFoundation indev @ 0x7f8b1c004a00] [0] FaceTime HD Camera
[AVFoundation indev @ 0x7f8b1c004a00] [1] Capture screen 0
[AVFoundation indev @ 0x7f8b1c004a00] AVFoundation audio devices:
[AVFoundation indev @ 0x7f8b1c004a00] [0] MacBook Pro Microphone
[AVFoundation indev @ 0x7f8b1c004a00] [1] Microsoft Teams Audio
: Input/output error
"""


class Fake:
    """A runner that answers by the command's words and keeps what it was asked."""
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, cmd, timeout=30):
        self.calls.append(list(cmd))
        line = " ".join(cmd)
        for key, res in self.answers:
            if key in line:
                return res
        return Result(127, "", f"{cmd[0]}: not found")


def mac(answers, tmp_path, **kw):
    return for_system("darwin", run=Fake(answers), uid=501, home=tmp_path, **kw)


def test_services_are_launchd_agents_of_the_owner(tmp_path):
    m = mac([("print gui/501/com.aurora.api", Result(0, RUNNING))], tmp_path)
    assert m.label("aurora-api.service") == "com.aurora.api"
    assert m.service_state("aurora-api") == "active"
    assert mac([("print", Result(0, CRASHED))], tmp_path).service_state("aurora-api") == "failed"
    assert mac([("print", Result(0, STOPPED_CLEAN))], tmp_path).service_state("aurora-api") == "inactive"
    gone = Result(113, "", 'Could not find service "com.aurora.api" in domain for user gui: 501')
    assert mac([("print", gone)], tmp_path).service_state("aurora-api") == "missing"
    plist = tmp_path / "Library" / "LaunchAgents" / "com.aurora.api.plist"
    plist.parent.mkdir(parents=True)
    plist.write_text("<plist/>")
    assert mac([("print", gone)], tmp_path).service_state("aurora-api") == "inactive"   # installed, stopped


def test_restart_is_a_kickstart_and_a_stopped_agent_is_loaded_first(tmp_path):
    plist = tmp_path / "Library" / "LaunchAgents" / "com.aurora.llm.plist"
    plist.parent.mkdir(parents=True)
    plist.write_text("<plist/>")
    run = Fake([("print", Result(0, RUNNING)), ("kickstart", Result(0))])
    m = for_system("darwin", run=run, uid=501, home=tmp_path)
    assert m.service_action("restart", ["aurora-llm"]).code == 0
    assert run.calls[-1] == ["launchctl", "kickstart", "-k", "gui/501/com.aurora.llm"]
    run = Fake([("print", Result(113)), ("bootstrap", Result(0))])
    m = for_system("darwin", run=run, uid=501, home=tmp_path)
    assert m.service_action("start", ["aurora-llm"]).code == 0
    assert ["launchctl", "bootstrap", "gui/501", str(plist)] in run.calls and not any("kickstart" in c for c in run.calls)
    run = Fake([("print", Result(113)), ("bootstrap", Result(5, "", "Bootstrap failed: 5: Input/output error")),
                ("kickstart", Result(0))])
    assert for_system("darwin", run=run, uid=501, home=tmp_path).service_action("restart", ["aurora-llm"]).code == 0
    run = Fake([("bootout", Result(3, "", "Boot-out failed: 3: No such process"))])
    assert for_system("darwin", run=run, uid=501, home=tmp_path).service_action("stop", ["aurora-llm"]).code == 0


def test_only_aurora_s_own_services_and_verbs(tmp_path):
    m = mac([], tmp_path)
    for units, verb in ((["sshd"], "stop"), (["aurora-api; rm"], "restart"), (["aurora-api"], "disable")):
        with pytest.raises(ValueError):
            m.service_action(verb, units)


def test_the_machine_apple_gpu_os_and_id(tmp_path):
    prof = json.dumps({"SPDisplaysDataType": [{"sppci_model": "Apple M2 Pro", "sppci_cores": "19"}]})
    m = mac([("system_profiler", Result(0, prof)), ("hw.memsize", Result(0, "34359738368\n")),
             ("sw_vers", Result(0, "ProductName:\t\tmacOS\nProductVersion:\t\t15.1\nBuildVersion:\t\t24B83\n")),
             ("ioreg", Result(0, '  |   "IOPlatformUUID" = "1A2B3C4D-0000-1111-2222-333344445555"\n'))],
            tmp_path, machine="arm64")
    g = m.gpus()
    assert [(x.name, x.mem_total, x.util) for x in g] == [("Apple M2 Pro", 32768.0, None)]   # use: not measured
    assert m.accelerator() == "metal"
    assert m.os_info() == {"system": "Darwin", "name": "macOS 15.1", "build": "24B83", "machine": "arm64"}
    assert m.machine_id() == "1A2B3C4D-0000-1111-2222-333344445555"
    assert mac([], tmp_path, machine="x86_64").accelerator() == "cpu"
    assert mac([("system_profiler", Result(1, "", "boom"))], tmp_path, machine="arm64").gpus() == []


def test_the_newer_ffmpeg_listing_with_uid_and_serial(tmp_path):
    out = ("[AVFoundation indev @ 0x1] AVFoundation video devices:\n"
           "[AVFoundation indev @ 0x1] [0] FaceTime HD Camera  [uid:0x1420000005ac8600] [serial:CC2X1234]\n"
           "[AVFoundation indev @ 0x1] [1] Capture screen 0\n"
           "[AVFoundation indev @ 0x1] AVFoundation audio devices:\n"
           "[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone  [uid:BuiltInMicrophoneDevice]\n")
    m = mac([("avfoundation", Result(1, "", out))], tmp_path)
    assert [(d.id, d.name) for d in m.cameras()] == [("0", "FaceTime HD Camera")]
    assert [d.name for d in m.microphones()] == ["MacBook Pro Microphone"]


def test_cameras_never_offer_the_screen_and_ffmpeg_gets_the_index(tmp_path):
    m = mac([("avfoundation", Result(1, "", AVFOUNDATION))], tmp_path)
    assert [(d.id, d.name) for d in m.cameras()] == [("0", "FaceTime HD Camera")]
    assert [(d.id, d.name) for d in m.microphones()] == [("0", "MacBook Pro Microphone"), ("1", "Microsoft Teams Audio")]
    assert m.ffmpeg_camera("0", "1280x720")[-2:] == ["-i", "0:none"]
    assert m.ffmpeg_microphone("1") == ["-f", "avfoundation", "-i", ":1"]


def test_files_keys_fonts_and_hints(tmp_path):
    m = mac([], tmp_path)
    assert str(m.key_dir()) == "/Library/Application Support/Aurora/keys"
    assert m.install_hint("pdftoppm") == "brew install poppler" and m.as_admin("x") == "sudo x"
    assert m.install_hint("ffmpeg") == "brew install ffmpeg-full"                 # drawtext, subtitles, rubberband
    assert m.ffmpeg_path(m.fonts()[0]) == "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    assert m.process_env() == {}
    ok, why = m.trusted_by_admin_only(tmp_path / "k.pub")                  # the owner's folder: not root's
    assert not ok and why


def test_locks_are_flock(tmp_path):
    m = mac([], tmp_path)
    f = tmp_path / "lock"
    with open(f, "w") as a, open(f, "w") as b:
        assert m.lock(a) and not m.lock(b, wait=False)
        m.unlock(a)
        assert m.lock(b, wait=False)


def test_a_service_s_details_its_timer_and_its_program_from_launchd_and_the_plist(tmp_path):
    import plistlib
    plist = tmp_path / "Library" / "LaunchAgents" / "com.aurora.backup.plist"
    plist.parent.mkdir(parents=True)
    plist.write_bytes(plistlib.dumps({"Label": "com.aurora.backup", "StartCalendarInterval": {"Hour": 3, "Minute": 30},
                                      "ProgramArguments": ["/Users/owner1/Aurora/.venv/bin/python", "sys/core/script/svc_backup.py"]}))
    crashed = CRASHED.replace("runs = 1", "runs = 4")
    m = mac([("print", Result(0, crashed))], tmp_path)
    assert m.service_info("aurora-backup") == {"state": "failed", "mem_mib": None, "restarts": 3, "result": "exit-code", "status": 1}
    assert m.service_next_run("aurora-backup.service") == "every day at 03:30"
    assert m.service_command("aurora-backup") == "/Users/owner1/Aurora/.venv/bin/python sys/core/script/svc_backup.py"
    assert mac([], tmp_path).service_command("aurora-api") == ""        # no plist: nothing known


def test_the_nas_is_found_in_the_mount_table_without_touching_its_folder(tmp_path):
    table = ("/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)\n"
             "//owner1@nas.local/backups on /Users/owner1/aurora-nas (smbfs, nodev, nosuid, mounted by owner1)\n")
    m = mac([("mount", Result(0, table))], tmp_path)
    assert m.is_mount("/Users/owner1/aurora-nas") and not m.is_mount("/Users/owner1/aurora")
    assert m.in_folder("/Users/owner1/Aurora", "x") == "cd /Users/owner1/Aurora && x"


def test_a_plugin_s_cage_is_a_sandbox_profile_where_the_last_rule_decides(cfg, tmp_path, monkeypatch):
    """The profile of sandbox-exec, from the same cage_plan as Windows's: home hidden, Aurora's folder reopened for
    reading, the secrets hidden again, the plugin's own .env reopened, writes only in its folders, no network."""
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/sandbox-exec")
    mac = for_system("darwin", run=lambda cmd, timeout=30: Result(0, "arm64"))
    folder = tmp_path / "plugins" / "forged"
    folder.mkdir(parents=True)
    filtered = cfg.path("AURORA_STATUS_DIR") / "plugins" / "env" / "forged.env"
    filtered.parent.mkdir(parents=True)
    filtered.write_text("X=1")
    cmd, env = mac.cage(["python", "server.py"], folder, {"sandbox": {"network": False}}, filtered, cfg)
    assert cmd[:2] == ["/usr/bin/sandbox-exec", "-p"] and cmd[3:] == ["python", "server.py"]
    prof = cmd[2].splitlines()
    real = lambda p: str(Path(p).resolve())                                           # noqa: E731
    starts = ["(version 1)", "(allow default)", f'(deny file-read* file-write* (subpath "{Path.home().resolve()}"))',
              "(allow file-read* (subpath", "(deny file-read* file-write* (", "(allow file-read* (literal",
              "(deny file-write*)", "(allow file-write*", "(deny network*)"]
    assert len(prof) == len(starts) and all(r.startswith(x) for r, x in zip(prof, starts)), prof   # the last rule decides
    order = [0, 3, 0, 5]
    assert f'(literal "{real(cfg.env_file)}")' in cmd[2] and f'(subpath "{real(filtered.parent)}")' in cmd[2]
    assert f'(literal "{real(filtered)}")' in prof[order[3]] and f'(subpath "{real(cfg.root)}")' in prof[order[1]]
    assert env["AURORA_ENV_FILE"] == real(filtered) and env["AURORA_IN_SANDBOX"] == "1"
    open_net = mac.cage(["x"], folder, {}, filtered, cfg)[0][2]
    assert "(deny network*)" not in open_net
