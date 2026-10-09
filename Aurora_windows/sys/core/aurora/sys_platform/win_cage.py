# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A plugin inside a Windows AppContainer (the owner, 2026-10-08: the cages first, «A») — the same contract as Linux's
bubblewrap, made of what Windows has:

    python -m aurora.sys_platform.win_cage SPEC.json -- COMMAND...

SPEC is windows.Windows.cage's cage_plan plus the container's name. An AppContainer process reads and writes only
what its SID is granted (and what Windows gives every app container: the system's own folders), so:
  read    Aurora's folder, the plugin's, the Python      granted read, branch by branch around the secrets
  hide    the secrets inside them                         never granted (no denial: v0.2.0's run showed a granted
                                                          folder's deny did not stop the AppContainer)
  allow   its own filtered .env                           granted on the file itself, at each start (written again)
  write   its folders and temp                            granted modify
  network internetClient + privateNetworkClientServer     capabilities; none when the manifest says no network
  window  the window station and the desktop of the session   read only: without them user32.dll does not start, and
                                                          every DLL that needs it fails «DLL initialization routine
                                                          failed» — _ssl, _hashlib, _ctypes, cryptography: the MCP
                                                          library, so every plugin (C231, the test VM, 9 Oct)
The grants are kept in a marker (a grant on a big folder walks its files once); one whose right changed is removed
first; the .env's grant is made at every start, as the file is written again (os.replace). The plugin runs in a Job object that kills it when this launcher goes
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
SE_WINDOW_OBJECT, DACL_SECURITY_INFORMATION, GRANT_ACCESS = 7, 0x4, 1
READ_CONTROL = 0x00020000
WINSTA_READ = READ_CONTROL | 0x0002 | 0x0020 | 0x0100   # READATTRIBUTES, ACCESSGLOBALATOMS, ENUMERATE
DESKTOP_READ = READ_CONTROL | 0x0001 | 0x0040           # READOBJECTS, ENUMERATE


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [("AppContainerSid", ctypes.c_void_p), ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
                ("CapabilityCount", wintypes.DWORD), ("Reserved", wintypes.DWORD)]


class TRUSTEE_W(ctypes.Structure):
    _fields_ = [("pMultipleTrustee", ctypes.c_void_p), ("MultipleTrusteeOperation", ctypes.c_int),
                ("TrusteeForm", ctypes.c_int), ("TrusteeType", ctypes.c_int), ("ptstrName", ctypes.c_void_p)]


class EXPLICIT_ACCESS_W(ctypes.Structure):
    _fields_ = [("grfAccessPermissions", wintypes.DWORD), ("grfAccessMode", ctypes.c_int),
                ("grfInheritance", wintypes.DWORD), ("Trustee", TRUSTEE_W)]


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


def window_access(sid) -> None:
    """The container may read the session's window station and desktop: user32.dll needs them to start (C231). The
    plugins' services run in session 0 (S4U tasks), whose desktop shows no one's windows; read only, never input."""
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32.GetProcessWindowStation.restype = u32.GetThreadDesktop.restype = ctypes.c_void_p
    u32.GetThreadDesktop.argtypes = [wintypes.DWORD]
    adv.GetSecurityInfo.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    adv.SetEntriesInAclW.argtypes = [wintypes.ULONG, ctypes.POINTER(EXPLICIT_ACCESS_W), ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_void_p)]
    adv.SetSecurityInfo.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p, ctypes.c_void_p]
    for handle, rights in ((u32.GetProcessWindowStation(), WINSTA_READ),
                           (u32.GetThreadDesktop(k32.GetCurrentThreadId()), DESKTOP_READ)):
        dacl, sd, new = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        if adv.GetSecurityInfo(handle, SE_WINDOW_OBJECT, DACL_SECURITY_INFORMATION, None, None, ctypes.byref(dacl),
                               None, ctypes.byref(sd)) != 0:
            _fail("GetSecurityInfo (window station / desktop)")
        ea = EXPLICIT_ACCESS_W(rights, GRANT_ACCESS, 0, TRUSTEE_W(None, 0, 0, 0, sid))   # TRUSTEE_IS_SID
        if adv.SetEntriesInAclW(1, ctypes.byref(ea), dacl, ctypes.byref(new)) != 0:
            _fail("SetEntriesInAcl (window station / desktop)")
        if adv.SetSecurityInfo(handle, SE_WINDOW_OBJECT, DACL_SECURITY_INFORMATION, None, None, new, None) != 0:
            _fail("SetSecurityInfo (window station / desktop)")
        k32.LocalFree(ctypes.c_void_p(new.value))
        k32.LocalFree(ctypes.c_void_p(sd.value))


def icacls(path: str, *args: str) -> None:
    r = subprocess.run(["icacls", path, *args, "/C", "/Q"], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise OSError(f"win_cage: icacls {path} {' '.join(args)}: {(r.stdout + r.stderr).strip()[-300:]}")


TREE, ONLY, WRITE, FILE = "(OI)(CI)(RX)", "(RX)", "(OI)(CI)(M)", "(R)"


def _under(p: Path, top: Path) -> bool:
    return p == top or top in p.parents


def plan_grants(read: list[str], hide: list[str], write: list[str]) -> dict[str, str]:
    """{path: right}: only grants, never a denial (v0.2.0's Windows run: with the whole folder granted and the secrets
    denied, the AppContainer still read .env and the push key). A branch with no secret in it is granted whole; a
    folder holding a secret somewhere below is granted for itself only (listed, crossed) and its children are looked
    at one by one; a secret gets nothing — an AppContainer reads only what it is given, so nothing reaches it."""
    hidden = [Path(h) for h in hide]
    out: dict[str, str] = {}

    def walk(p: Path) -> None:
        if any(_under(p, h) for h in hidden) or not p.exists():
            return
        if p.is_dir() and any(h != p and p in h.parents for h in hidden):
            out[str(p)] = ONLY
            for child in sorted(p.iterdir()):
                walk(child)
        else:
            out[str(p)] = TREE if p.is_dir() else FILE
    for r in read:
        walk(Path(r))
    for w in write:
        if Path(w).exists() and not any(_under(Path(w), h) for h in hidden):
            out[str(w)] = WRITE
    return out


def grant(spec: dict, sid: str) -> None:
    """The plan's grants, kept in a marker: a path whose right changed (a folder that now holds another user's data)
    has its old entry removed first — the removal of an inherited grant reaches what is below it."""
    marker = Path(spec["marker"])
    before = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
    if not isinstance(before, dict):                  # the first marker (a list): start again
        before = {}
    want = plan_grants(spec["read"], spec["hide"], spec["write"])
    for path, right in before.items():
        if want.get(path) != right and Path(path).exists():
            icacls(path, "/remove:g", f"*{sid}")
    for path, right in want.items():
        if before.get(path) != right:
            icacls(path, "/grant", f"*{sid}:{right}")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(want, indent=0), encoding="utf-8")
    for a in spec["allow"]:                           # every start: the file is written again (os.replace)
        icacls(a, "/grant", f"*{sid}:{FILE}")


def run(spec: dict, cmd: list[str]) -> int:
    k32, adv, env, ole = _dlls()
    sid, sid_text, home = container(spec["name"])
    grant(spec, sid_text)
    window_access(sid)
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
