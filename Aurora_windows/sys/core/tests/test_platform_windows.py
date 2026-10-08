# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The Windows backend, checked on any machine with the outputs Windows's tools print (PowerShell's ScheduledTasks
and Get-Acl, reg.exe, ffmpeg's dshow in the old and the new format, nvidia-smi). A real Windows checks them again in
phase 5."""
import sys
import types
from pathlib import Path

import pytest

from aurora.sys_platform import for_system
from aurora.sys_platform.base import Result

DSHOW_NEW = """[dshow @ 000001c0f3a8e2c0] "Integrated Camera" (video)
[dshow @ 000001c0f3a8e2c0]   Alternative name "@device_pnp_\\\\?\\usb#vid_04f2&pid_b6dd&mi_00#6&2a7e1d0&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\\global"
[dshow @ 000001c0f3a8e2c0] "OBS Virtual Camera" (none)
[dshow @ 000001c0f3a8e2c0]   Alternative name "@device_sw_{860BB310-5D01-11D0-BD3B-00A0C911CE86}\\{A3FCE0F5-3493-419F-958A-ABA1250EC20B}"
[dshow @ 000001c0f3a8e2c0] "Microfono (Realtek(R) Audio)" (audio)
[dshow @ 000001c0f3a8e2c0]   Alternative name "@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{7A1C7B4E-4D5B-4C5A-9E3C-1F2E3D4C5B6A}"
dummy: Immediate exit requested
"""
DSHOW_OLD = """[dshow @ 0000020] DirectShow video devices (some may be both video and audio devices)
[dshow @ 0000020]  "USB2.0 HD UVC WebCam"
[dshow @ 0000020]     Alternative name "@device_pnp_\\\\?\\usb#vid_13d3&pid_56dd"
[dshow @ 0000020] DirectShow audio devices
[dshow @ 0000020]  "Microphone Array (Realtek High Definition Audio)"
[dshow @ 0000020]     Alternative name "@device_cm_{33D9A762}\\wave_{0A1B}"
dummy: Immediate exit requested
"""
TRUSTED = ("OWNER|S-1-5-32-544\nS-1-5-18|2032127|Allow|None\nS-1-5-32-544|2032127|Allow|None\n"
           "S-1-5-32-545|1179817|Allow|None\nS-1-3-0|268435456|Allow|InheritOnly\n")
USERS_WRITE = TRUSTED + "S-1-5-32-545|278|Allow|None\n"
OWNED_BY_USER = TRUSTED.replace("OWNER|S-1-5-32-544", "OWNER|S-1-5-21-1004336348-1177238915-682003330-1001")


class Fake:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, cmd, timeout=30):
        self.calls.append(list(cmd))
        line = " ".join(cmd)
        for key, res in self.answers:
            if key in line:
                return res
        return Result(127, "", f"{cmd[0]}: not found")


def win(answers, **kw):
    return for_system("win32", run=Fake(answers), env={"ProgramData": r"C:\ProgramData", "WINDIR": r"C:\Windows",
                                                        "TEMP": r"C:\Users\owner1\AppData\Local\Temp"}, **kw)


def test_services_are_scheduled_tasks_read_by_english_state_names():
    assert win([("Get-ScheduledTask", Result(0, "Running|267009\r\n"))]).service_state("aurora-api") == "active"
    assert win([("Get-ScheduledTask", Result(0, "Ready|0\r\n"))]).service_state("aurora-api") == "inactive"
    assert win([("Get-ScheduledTask", Result(0, "Ready|267014\r\n"))]).service_state("aurora-api") == "inactive"   # stopped
    assert win([("Get-ScheduledTask", Result(0, "Ready|1\r\n"))]).service_state("aurora-api") == "failed"
    assert win([("Get-ScheduledTask", Result(0, "Ready|-2147024894\r\n"))]).service_state("aurora-api") == "failed"
    # SCHED_E_ACCOUNT_INFORMATION_NOT_SET (0x8004130F as a signed int): a failure, not a stop
    assert win([("Get-ScheduledTask", Result(0, "Ready|-2147216625\r\n"))]).service_state("aurora-api") == "failed"
    assert win([("Get-ScheduledTask", Result(0, "Queued|267045\r\n"))]).service_state("aurora-api") == "activating"
    gone = Result(1, "", "Get-ScheduledTask : No MSFT_ScheduledTask objects found with property 'TaskName' equal to 'api'.")
    assert win([("Get-ScheduledTask", gone)]).service_state("aurora-api") == "missing"


def test_restart_stops_and_starts_the_task_and_only_aurora_s():
    w = win([("ScheduledTask", Result(0))])
    assert w.service_action("restart", ["aurora-models.service"]).code == 0
    script = w.run.calls[-1][-1]
    assert w.run.calls[-1][0] == "powershell.exe" and "-NoProfile" in w.run.calls[-1]
    assert script == ("Stop-ScheduledTask -TaskPath '\\Aurora\\' -TaskName 'models' -ErrorAction Stop; "
                      "Start-ScheduledTask -TaskPath '\\Aurora\\' -TaskName 'models' -ErrorAction Stop")
    for units, verb in ((["wuauserv"], "stop"), (["aurora-api'; Remove-Item C:\\ -Recurse; '"], "restart")):
        with pytest.raises(ValueError):
            w.service_action(verb, units)
    assert win([("ScheduledTask", Result(1, "", "access denied"))]).service_action("start", ["aurora-api"]).code == 1


def test_the_signing_key_is_trusted_by_sids_never_by_names():
    k = Path(r"C:\ProgramData\Aurora\keys\owner.pub")
    assert win([("Get-Acl", Result(0, TRUSTED))]).trusted_by_admin_only(k) == (True, "")
    ok, why = win([("Get-Acl", Result(0, USERS_WRITE))]).trusted_by_admin_only(k)
    assert not ok and "S-1-5-32-545" in why
    ok, why = win([("Get-Acl", Result(0, OWNED_BY_USER))]).trusted_by_admin_only(k)
    assert not ok and "must belong" in why
    assert win([("Get-Acl", Result(1, "", "denied"))]).trusted_by_admin_only(k)[0] is False
    assert str(win([]).key_dir()) == str(Path(r"C:\ProgramData") / "Aurora" / "keys")


def test_the_machine_id_os_and_nvidia():
    w = win([("MachineGuid", Result(0, "\r\nHKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography\r\n"
                                       "    MachineGuid    REG_SZ    3F2504E0-4F89-11D3-9A0C-0305E82C3301\r\n")),
             ("Win32_OperatingSystem", Result(0, "Microsoft Windows 11 Pro|10.0.22631|64 bit\r\n")),
             ("nvidia-smi", Result(0, "0, NVIDIA GeForce RTX 4090, 3, 1024, 24564, 41, [N/A]\r\n"))])
    assert w.machine_id() == "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    assert w.os_info() == {"system": "Windows", "name": "Microsoft Windows 11 Pro", "build": "10.0.22631", "machine": "64 bit"}
    g = w.gpus()
    assert (g[0].name, g[0].mem_total, g[0].temp_limit) == ("NVIDIA GeForce RTX 4090", 24564.0, None)
    assert w.accelerator() == "cuda" and win([]).accelerator() == "cpu"


def test_a_dshow_device_of_both_kinds_is_a_camera_and_a_microphone():
    out = ('[dshow @ 0001] "Elgato HD60 S" (video, audio)\n'
           '[dshow @ 0001]   Alternative name "@device_pnp_\\\\?\\usb#vid_0fd9&pid_004e"\n')
    w = win([("dshow", Result(1, "", out))])
    assert [c.name for c in w.cameras()] == ["Elgato HD60 S"] == [m.name for m in w.microphones()]
    assert w.cameras()[0].id.startswith("@device_pnp_") and w.microphones()[0].id == w.cameras()[0].id


def test_dshow_devices_old_and_new_ffmpeg_by_their_unique_name():
    w = win([("dshow", Result(1, "", DSHOW_NEW))])
    cams, mics = w.cameras(), w.microphones()
    assert [c.name for c in cams] == ["Integrated Camera"] and cams[0].id.startswith("@device_pnp_")
    assert [m.name for m in mics] == ["Microfono (Realtek(R) Audio)"] and mics[0].id.startswith("@device_cm_")
    w = win([("dshow", Result(1, "", DSHOW_OLD))])
    assert [c.name for c in w.cameras()] == ["USB2.0 HD UVC WebCam"]
    assert [m.name for m in w.microphones()] == ["Microphone Array (Realtek High Definition Audio)"]
    assert w.ffmpeg_camera("@device_pnp_x", "1280x720") == ["-f", "dshow", "-video_size", "1280x720", "-i", "video=@device_pnp_x"]
    assert w.ffmpeg_microphone("Mic") == ["-f", "dshow", "-i", "audio=Mic"]


def test_paths_text_and_programs_the_windows_way():
    w = win([])
    assert w.process_env()["PYTHONUTF8"] == "1"                     # 70 reads and writes without an encoding
    assert w.venv_python(Path("C:/A/.venv")).parts[-2:] == ("Scripts", "python.exe")
    assert w.executable(Path("bin"), "llama-server").name == "llama-server.exe"
    assert w.executable(Path("bin"), "caddy.exe").name == "caddy.exe"
    assert w.ffmpeg_path(r"C:\Windows\Fonts\arialbd.ttf") == "C\\:/Windows/Fonts/arialbd.ttf"   # ':' escaped for filters
    assert w.sandbox() is None                                      # no cage: nothing runs uncaged
    assert w.install_hint("ffmpeg") == "winget install --id Gyan.FFmpeg -e"


def test_locks_wait_on_msvcrt_and_keep_the_file_position(tmp_path, monkeypatch):
    held = {"n": 1}
    calls = []

    def locking(fd, mode, n):
        calls.append(mode)
        if mode == fake.LK_NBLCK and held["n"]:
            held["n"] -= 1
            raise OSError(36, "Resource deadlock avoided")
    fake = types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=locking)
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    w = win([])
    with open(tmp_path / "f", "w+") as fh:
        fh.write("abc")
        assert w.lock(fh, wait=False) is False                      # someone holds it
        assert w.lock(fh) is True and fh.tell() == 3                # waited, the position kept
        w.unlock(fh)
    assert calls == [2, 2, 0]


def test_replace_waits_out_a_reader_holding_the_file(tmp_path, monkeypatch):
    import os
    real, tries = os.replace, {"n": 0}

    def busy(a, b):
        tries["n"] += 1
        if tries["n"] < 3:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        real(a, b)
    monkeypatch.setattr(os, "replace", busy)
    (tmp_path / "t").write_text("new")
    win([]).replace(tmp_path / "t", tmp_path / "d")
    assert (tmp_path / "d").read_text() == "new" and tries["n"] == 3


def test_a_task_s_details_its_next_run_and_its_program():
    line = "Ready|1|2026-10-09T03:30:00|C:\\Users\\owner1\\Aurora\\.venv\\Scripts\\python.exe sys\\core\\script\\svc_backup.py\r\n"
    w = win([("Get-ScheduledTaskInfo", Result(0, line)), ("Get-ScheduledTask", Result(0, "Ready|1\r\n"))])
    assert w.service_info("aurora-backup") == {"state": "failed", "mem_mib": None, "restarts": None, "result": "exit-code", "status": 1}
    assert w.service_next_run("aurora-backup.service") == "2026-10-09T03:30:00"
    assert w.service_command("aurora-backup").endswith("svc_backup.py")
    gone = win([("Get-ScheduledTask", Result(1, "", "not found"))])
    assert gone.service_info("aurora-backup")["state"] == "missing" and gone.service_next_run("aurora-backup") is None


def test_commands_for_powershell_and_no_mount_table():
    w = win([])
    assert w.in_folder(r"C:\Users\o'neil\Aurora", "x") == "Set-Location -LiteralPath 'C:\\Users\\o''neil\\Aurora'; x"
    assert w.is_mount(Path(r"C:\Aurora")) is False
    assert win([("memory.free", Result(0, "15872\r\n"))]).gpu_free_mib(0) == 15872.0
