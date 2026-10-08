# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A plugin inside a Windows AppContainer (the owner, 2026-10-08: the cages first, «A») — the same contract as Linux's
bubblewrap, made of what Windows has:

    python -m aurora.sys_platform.win_cage SPEC.json -- COMMAND...

SPEC is windows.Windows.cage's cage_plan plus the container's name. An AppContainer process reads and writes only
what its SID is granted (and what Windows gives every app container: the system's own folders), so:
  read    Aurora's folder, the plugin's, the Python      granted read (inherited by what is created later)
  hide    the secrets inside them                         denied to the SID (a deny wins over the inherited grant)
  allow   its own filtered .env                           granted on the file itself (an explicit grant wins over the
                                                          inherited deny); made again at each start, as the file is
  write   its folders and temp                            granted modify
  network internetClient + privateNetworkClientServer     capabilities; none when the manifest says no network
The grants on folders are kept (a marker remembers them: a grant on Aurora's folder walks thousands of files once);
the denials and the .env's grant are made at every start, cheap, because a file written again (os.replace, the
settings saved) loses the explicit entries. The plugin runs in a Job object that kills it when this launcher goes
(the launcher dies with Aurora's pipe), with this launcher's stdin/stdout/stderr (the MCP pipe) and exit code.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

INTERNET_CLIENT = "S-1-15-3-1"
PRIVATE_NETWORK = "S-1-15-3-3"                        # the LAN: Home Assistant, the firewall's API
SE_GROUP_ENABLED = 0x4
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
EXTENDED_STARTUPINFO_PRESENT, CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT = 0x00080000, 0x4, 0x400
STARTF_USESTDHANDLES = 0x100
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 0x2000, 9
HANDLE_FLAG_INHERIT = 0x1
ALREADY_EXISTS = -2147024713                          # HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS) as a signed long
INFINITE = 0xFFFFFFFF


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [("AppContainerSid", ctypes.c_void_p), ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
                ("CapabilityCount", wintypes.DWORD), ("Reserved", wintypes.DWORD)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE), ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD)]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                               "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _dlls():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    env = ctypes.WinDLL("userenv")
    ole = ctypes.WinDLL("ole32")
    for f, res, args in (
            (env.CreateAppContainerProfile, ctypes.c_long, [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                                            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]),
            (env.DeriveAppContainerSidFromAppContainerName, ctypes.c_long, [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]),
            (env.GetAppContainerFolderPath, ctypes.c_long, [wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPWSTR)]),
            (adv.ConvertSidToStringSidW, wintypes.BOOL, [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]),
            (adv.ConvertStringSidToSidW, wintypes.BOOL, [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]),
            (k32.InitializeProcThreadAttributeList, wintypes.BOOL, [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                                                    ctypes.POINTER(ctypes.c_size_t)]),
            (k32.UpdateProcThreadAttribute, wintypes.BOOL, [ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t,
                                                            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]),
            (k32.DeleteProcThreadAttributeList, None, [ctypes.c_void_p]),
            (k32.CreateProcessW, wintypes.BOOL, [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                                 wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
                                                 ctypes.c_void_p, ctypes.POINTER(PROCESS_INFORMATION)]),
            (k32.CreateJobObjectW, wintypes.HANDLE, [ctypes.c_void_p, wintypes.LPCWSTR]),
            (k32.SetInformationJobObject, wintypes.BOOL, [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]),
            (k32.AssignProcessToJobObject, wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE]),
            (k32.ResumeThread, wintypes.DWORD, [wintypes.HANDLE]),
            (k32.WaitForSingleObject, wintypes.DWORD, [wintypes.HANDLE, wintypes.DWORD]),
            (k32.GetExitCodeProcess, wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]),
            (k32.GetStdHandle, wintypes.HANDLE, [wintypes.DWORD]),
            (k32.SetHandleInformation, wintypes.BOOL, [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]),
            (k32.CloseHandle, wintypes.BOOL, [wintypes.HANDLE]),
            (ole.CoTaskMemFree, None, [ctypes.c_void_p])):
        f.restype, f.argtypes = res, args
    return k32, adv, env, ole


def _fail(msg: str) -> None:
    raise OSError(f"win_cage: {msg} (error {ctypes.get_last_error()})")


def container(name: str):
    """(SID pointer, its string, the container's own folder) — the profile made once, found again afterwards."""
    k32, adv, env, ole = _dlls()
    sid = ctypes.c_void_p()
    hr = env.CreateAppContainerProfile(name, name, "Aurora plugin", None, 0, ctypes.byref(sid))
    if hr == ALREADY_EXISTS:
        hr = env.DeriveAppContainerSidFromAppContainerName(name, ctypes.byref(sid))
    if hr != 0:
        raise OSError(f"win_cage: AppContainer {name}: HRESULT {hr & 0xFFFFFFFF:#010x}")
    text = wintypes.LPWSTR()
    if not adv.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        _fail("ConvertSidToStringSid")
    s = text.value
    folder = wintypes.LPWSTR()
    if env.GetAppContainerFolderPath(s, ctypes.byref(folder)) != 0:
        raise OSError("win_cage: GetAppContainerFolderPath")
    path = folder.value
    ole.CoTaskMemFree(folder)
    return sid, s, path


def icacls(path: str, *args: str) -> None:
    r = subprocess.run(["icacls", path, *args, "/C", "/Q"], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise OSError(f"win_cage: icacls {path} {' '.join(args)}: {(r.stdout + r.stderr).strip()[-300:]}")


def grant(spec: dict, sid: str) -> None:
    marker = Path(spec["marker"])
    done = set(json.loads(marker.read_text(encoding="utf-8"))) if marker.is_file() else set()
    want = [(p, "(OI)(CI)(RX)") for p in spec["read"]] + [(p, "(OI)(CI)(M)") for p in spec["write"]]
    for path, right in want:
        if f"{path}|{right}" in done or not Path(path).exists():
            continue
        icacls(path, "/grant", f"*{sid}:{right}")
        done.add(f"{path}|{right}")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(sorted(done)), encoding="utf-8")
    for h in spec["hide"]:                            # every start: a file written again lost its entry
        if Path(h).exists():
            icacls(h, "/deny", f"*{sid}:(OI)(CI)(F)" if Path(h).is_dir() else f"*{sid}:(F)")
    for a in spec["allow"]:
        icacls(a, "/grant", f"*{sid}:(R)")


def run(spec: dict, cmd: list[str]) -> int:
    k32, adv, env, ole = _dlls()
    sid, sid_text, home = container(spec["name"])
    grant(spec, sid_text)
    caps, keep = [], []
    for s in ([INTERNET_CLIENT, PRIVATE_NETWORK] if spec["network"] else []):
        p = ctypes.c_void_p()
        if not adv.ConvertStringSidToSidW(s, ctypes.byref(p)):
            _fail(f"capability {s}")
        caps.append(SID_AND_ATTRIBUTES(p, SE_GROUP_ENABLED))
        keep.append(p)
    arr = (SID_AND_ATTRIBUTES * max(1, len(caps)))(*caps)
    sc = SECURITY_CAPABILITIES(sid, arr if caps else None, len(caps), 0)
    size = ctypes.c_size_t()
    k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    attrs = ctypes.create_string_buffer(size.value)
    if not k32.InitializeProcThreadAttributeList(attrs, 1, 0, ctypes.byref(size)):
        _fail("InitializeProcThreadAttributeList")
    if not k32.UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, ctypes.byref(sc),
                                         ctypes.sizeof(sc), None, None):
        _fail("UpdateProcThreadAttribute")
    si = STARTUPINFOEXW()
    si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
    si.StartupInfo.dwFlags = STARTF_USESTDHANDLES
    for field, n in (("hStdInput", -10), ("hStdOutput", -11), ("hStdError", -12)):
        h = k32.GetStdHandle(wintypes.DWORD(n & 0xFFFFFFFF))
        if h:
            k32.SetHandleInformation(h, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
        setattr(si.StartupInfo, field, h)
    si.lpAttributeList = ctypes.cast(attrs, ctypes.c_void_p)
    environ = {**os.environ, "TEMP": home, "TMP": home, "AURORA_IN_SANDBOX": "1"}
    block = ctypes.create_unicode_buffer("".join(f"{k}={v}\0" for k, v in environ.items()) + "\0")
    line = ctypes.create_unicode_buffer(subprocess.list2cmdline(cmd))
    pi = PROCESS_INFORMATION()
    if not k32.CreateProcessW(None, line, None, None, True,
                              EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT,
                              block, os.getcwd(), ctypes.byref(si), ctypes.byref(pi)):
        _fail(f"CreateProcess {cmd[0]}")
    k32.DeleteProcThreadAttributeList(attrs)
    job = k32.CreateJobObjectW(None, None)
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not k32.SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
                                                  ctypes.sizeof(info)) or not k32.AssignProcessToJobObject(job, pi.hProcess):
        _fail("Job object")                          # never a plugin that could outlive Aurora
    k32.ResumeThread(pi.hThread)
    k32.WaitForSingleObject(pi.hProcess, INFINITE)
    code = wintypes.DWORD()
    k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
    for h in (pi.hThread, pi.hProcess):
        k32.CloseHandle(h)
    return code.value


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "--":
        print("usage: python -m aurora.sys_platform.win_cage SPEC.json -- COMMAND...", file=sys.stderr)
        return 2
    try:
        return run(json.loads(Path(argv[0]).read_text(encoding="utf-8")), argv[2:])
    except OSError as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
