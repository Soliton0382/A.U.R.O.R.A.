# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F14's sibling attacker: same uid, not an ancestor of the target. Three tries on a target PID:
PTRACE_ATTACH, open + read /proc/<pid>/mem at a mapped address, process_vm_readv of the same address.

    python3 -I -B attack.py TARGET_PID            -> one JSON line: {"ptrace": {...}, "mem": {...}, "vm_readv": {...}}
    python3 -I -B attack.py --self-test           -> the same three on a child of its own (an ancestor may: control)
"""
import ctypes
import json
import os
import sys
import time

PTRACE_ATTACH, PTRACE_DETACH = 16, 17
libc = ctypes.CDLL(None, use_errno=True)


class IOVec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("len", ctypes.c_size_t)]


libc.ptrace.restype = ctypes.c_long
libc.ptrace.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
libc.process_vm_readv.restype = ctypes.c_ssize_t
libc.process_vm_readv.argtypes = [ctypes.c_int, ctypes.POINTER(IOVec), ctypes.c_ulong, ctypes.POINTER(IOVec),
                                  ctypes.c_ulong, ctypes.c_ulong]


def an_address(pid: int) -> int:
    """A readable mapped address of the target (maps is readable for a dumpable process of our uid)."""
    try:
        for ln in open(f"/proc/{pid}/maps"):
            rng, perms = ln.split()[:2]
            if perms.startswith("r"):
                return int(rng.split("-")[0], 16)
    except OSError:
        pass
    return 0


def try_all(pid: int) -> dict:
    out = {}
    r = libc.ptrace(PTRACE_ATTACH, pid, None, None)
    e = ctypes.get_errno()
    out["ptrace"] = {"ok": r == 0, "errno": 0 if r == 0 else e}
    if r == 0:
        os.waitpid(pid, 0) if pid in _children else time.sleep(0.05)
        libc.ptrace(PTRACE_DETACH, pid, None, None)
    addr = an_address(pid)
    out["address_found"] = addr != 0
    try:
        fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
        try:
            data = os.pread(fd, 16, addr)
            out["mem"] = {"ok": len(data) > 0, "errno": 0}
        except OSError as ex:
            out["mem"] = {"ok": False, "errno": ex.errno, "stage": "read"}
        finally:
            os.close(fd)
    except OSError as ex:
        out["mem"] = {"ok": False, "errno": ex.errno, "stage": "open"}
    buf = ctypes.create_string_buffer(16)
    local = IOVec(ctypes.cast(buf, ctypes.c_void_p), 16)
    remote = IOVec(ctypes.c_void_p(addr), 16)
    n = libc.process_vm_readv(pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0)
    out["vm_readv"] = {"ok": n > 0, "errno": 0 if n > 0 else ctypes.get_errno()}
    return out


_children = set()

if __name__ == "__main__":
    if sys.argv[1] == "--self-test":
        c = os.fork()
        if c == 0:
            time.sleep(5)
            os._exit(0)
        _children.add(c)
        time.sleep(0.2)
        res = try_all(c)
        os.kill(c, 9)
        os.waitpid(c, 0)
    else:
        res = try_all(int(sys.argv[1]))
    print(json.dumps(res))
