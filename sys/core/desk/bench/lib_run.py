# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 bench (Linux): run general-library procedures on the virtual compositor through AT-SPI actions and check
every step's expected state. Bench only: aurora-desk acts by input through libei; this proves the anchors and the
flow. The program runs in the procedure's locale (LANG/LANGUAGE), with a bench home and invented data.

    python3 -I -B lib_run.py --scratch DIR --job job.json      job = [{"proc": file, "params": {...}, "tag": "x"}, ...]
Results in DIR/run-*/lib/<tag>.json."""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from desk.bench import a11y, bench as benchmod, guard  # noqa: E402

LOCALES = {"it": "it_IT.UTF-8", "en": "C.UTF-8"}
KEYS = {}              # input by real keys (portal + libei, ei_input.py) when a job asks for it: {"kb": Keyboard}
SETTLE = 0.25          # s after each action: the program handles it asynchronously (KCalc read 12+3 without it)


def sub(s: str, params: dict) -> str:
    for k, v in params.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def ident(node) -> str:
    try:
        return node.get_accessible_id() or ""
    except Exception:                                   # noqa: BLE001
        return ""


def _safe(f, d=""):
    try:
        return f()
    except Exception:                                   # noqa: BLE001
        return d


def matches(node, t: dict, loc: str, params: dict) -> bool:
    if _safe(node.get_role_name) != t["role"]:
        return False
    if t.get("id") and ident(node) != t["id"]:
        return False
    if t.get("id_end") and not ident(node).endswith(t["id_end"]):
        return False
    nm = _safe(node.get_name)
    if t.get("name") and t["name"].get(loc) is not None and nm != sub(t["name"][loc], params):
        return False
    if t.get("name_re") and t["name_re"].get(loc) and not re.search(sub(t["name_re"][loc], params), nm or ""):
        return False
    if t.get("in_dialog") and not _in_dialog(node):
        return False
    return True


def _in_dialog(node) -> bool:
    n = node
    for _ in range(40):
        n = _safe(n.get_parent, None)
        if n is None:
            return False
        if _safe(n.get_role_name) == "dialog":
            return True
    return False


def showing(node) -> bool:
    try:
        from gi.repository import Atspi
        st = node.get_state_set()
        return st.contains(Atspi.StateType.SHOWING)
    except Exception:                                   # noqa: BLE001
        return False


class Task:
    """The task's windows: the program's process tree and the KDE portal's dialogs (design §8.2)."""

    def __init__(self, before: set, portal_pid: int):
        # Bench simplification (declared): some programs re-launch themselves in another process (Kate), so the
        # task is every accessible application that appeared after the launch, plus the portal. On the bench nothing
        # else starts; aurora-desk uses the process tree from its pidfd (design §8.1).
        self.before, self.portal = before, portal_pid

    def roots(self) -> list:
        return [a for a in a11y.apps() if a11y.app_pid(a) not in self.before or a11y.app_pid(a) == self.portal]

    def find(self, t: dict, loc: str, params: dict):
        for app in self.roots():
            for _, n in a11y.walk(app, limit=20000):
                if matches(n, t, loc, params) and (showing(n) or t.get("offscreen_ok")):
                    return n
        return None

    def find_all(self, t: dict, loc: str, params: dict) -> list:
        out = []
        for app in self.roots():
            for _, n in a11y.walk(app, limit=20000):
                if matches(n, t, loc, params) and showing(n):
                    out.append(n)
        return out

    def wait(self, t: dict, loc: str, params: dict, sec: float):
        end = time.monotonic() + sec
        while True:
            n = self.find(t, loc, params)
            if n is not None or time.monotonic() > end:
                return n
            time.sleep(0.2)

    def dump(self, limit: int = 3000) -> list:
        out = []
        for app in self.roots():
            for d, n in a11y.walk(app, limit=20000):
                nm, i = _safe(n.get_name), ident(n)
                if nm or i:
                    out.append(f"{d}|{_safe(n.get_role_name)}|{nm}|{i}|show={int(showing(n))}")
                if len(out) >= limit:
                    return out
        return out


def _press(node, do: str) -> str:
    got = a11y.do_action(node, ("ShowMenu",) if do == "open_menu" else ("Press", "press", "click", "Toggle", "toggle",
                                                                         "activate", "Activate"))
    if not got:
        ai = node.get_action_iface()
        names = [ai.get_action_name(i) for i in range(ai.get_n_actions())] if ai is not None else []
        raise RuntimeError(f"no press action (has {names})")
    return got


def act(node, step: dict, params: dict, rec: dict) -> None:
    do = step["do"]
    if do in ("press", "open_menu"):
        try:
            got = _press(node, do)
        except Exception as e:                          # noqa: BLE001
            # an action that opens a modal dialog answers only when the dialog closes: sent, then the expect decides
            if "Did not receive a reply" not in str(e):
                raise
            got = "Press (no reply: modal)"
        rec["via"] = got
    elif do == "type" and KEYS.get("kb"):
        from gi.repository import Atspi
        Atspi.Component.grab_focus(node)
        time.sleep(0.2)
        KEYS["kb"].type(sub(step["text"], params))
        rec["via"] = "keys"
    elif do == "key":
        if not KEYS.get("kb"):
            raise RuntimeError("a key step needs real keys (job input: keys)")
        if node is not None:
            from gi.repository import Atspi
            Atspi.Component.grab_focus(node)
            time.sleep(0.2)
        KEYS["kb"].tap(*step["keys"].split("+"))
        rec["via"] = "keys"
    elif do == "type":
        e = node.get_editable_text_iface()
        if e is None:
            raise RuntimeError("not editable")
        txt = sub(step["text"], params)
        if not e.set_text_contents(txt):
            raise RuntimeError("set_text_contents refused")
        rec["via"] = "set_text_contents"
    elif do == "read":
        from gi.repository import Atspi
        if node.get_text_iface() is not None:
            rec["read"] = Atspi.Text.get_text(node, 0, Atspi.Text.get_character_count(node))
        else:
            rec["read"] = _safe(node.get_name)
    elif do == "wait":
        pass
    else:
        raise RuntimeError(f"unknown step {do}")


def _stop_pid(pid: int, grace: float = 3.0) -> None:
    import signal
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    end = time.monotonic() + grace
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_one(b, proc: dict, params: dict, loc: str, work: Path) -> dict:
    res = {"id": proc["id"], "locale": loc, "steps": [], "ok": False}
    lang = LOCALES[loc]
    la = proc["program"]["launch"]
    argv = [la["exe"]] + [sub(x, params) for x in la.get("args", [])]
    env = b.wenv(LANG=lang, LC_ALL=lang, LANGUAGE=loc, QT_LINUX_ACCESSIBILITY_ALWAYS_ON="1")
    portal = b.started["portal-kde"].pid
    before = {a11y.app_pid(a) for a in a11y.apps()}
    p = b.procs.start(f"lib-{proc['id'].split('/')[-1]}", argv, env, stdout=b.out("lib"), stderr=-2, cwd=str(work))
    task = Task(before, portal)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 30 and not any(a.get_child_count() for a in task.roots() if a11y.app_pid(a) != portal):
        time.sleep(0.2)
    time.sleep(1.0)
    if KEYS.get("pending"):                              # the portal wants a window open before its dialog
        from desk.bench import ei_input
        from desk.bench.p4_measure import approve
        pt = ei_input.Portal()
        kb = ei_input.Keyboard(pt.connect(approve, timeout=20))
        if not kb.ready(10):
            raise RuntimeError("keyboard not ready")
        KEYS.update(pt=pt, kb=kb)
        KEYS.pop("pending")
        before |= {a11y.app_pid(a) for a in a11y.apps() if (a.get_name() or "") != proc["program"]["name"]}
    try:
        for st in proc["steps"]:
            rec = {"n": st["n"], "do": st["do"], "class": st["class"]}
            t1 = time.monotonic()
            try:
                tmo = st.get("timeout_s", 10)
                node = None
                if st["do"] == "press_each":
                    # a keypad: one button per character of the parameter, each found by its own anchor
                    seq = sub(st["text"], params)
                    for ch in seq:
                        if ch not in st["keys_map"]:
                            raise RuntimeError(f"no button for {ch!r}")
                        k = task.wait(dict(st["target"], id_end=st["keys_map"][ch]), loc, params, tmo)
                        if k is None:
                            raise RuntimeError(f"button for {ch!r} not found")
                        _press(k, "press")
                        time.sleep(SETTLE)
                    rec["via"] = f"press_each x{len(seq)}"
                    st = dict(st, target=None, do="wait")
                if st["do"] == "read_list":
                    time.sleep(1.0)
                    rec["read"] = [_safe(n.get_name) for n in task.find_all(st["target"], loc, params)]
                    st = dict(st, target=None, do="wait")
                if st.get("target"):
                    node = task.wait(st["target"], loc, params, tmo)
                    if node is None:
                        raise RuntimeError("target not found")
                act(node, st, params, rec)
                if st["do"] in ("press", "open_menu", "type", "key"):
                    time.sleep(SETTLE)
                ex = st.get("expect") or {}
                if ex.get("present") and task.wait(ex["present"], loc, params, tmo) is None:
                    raise RuntimeError("expected element missing")
                if ex.get("gone"):
                    end = time.monotonic() + tmo
                    while task.find(ex["gone"], loc, params) is not None and time.monotonic() < end:
                        time.sleep(0.2)
                    if task.find(ex["gone"], loc, params) is not None:
                        raise RuntimeError("expected element still there")
                rec["ok"] = True
            except Exception as e:                      # noqa: BLE001
                rec.update(ok=False, error=str(e), dump=task.dump())
                rec["ms"] = round((time.monotonic() - t1) * 1000)
                res["steps"].append(rec)
                raise
            rec["ms"] = round((time.monotonic() - t1) * 1000)
            res["steps"].append(rec)
        res["ok"] = True
    except Exception as e:                              # noqa: BLE001
        res["error"] = str(e)
    finally:
        b.procs.stop_one(p)
        # the program's real process (Kate re-launches itself; the launcher is not it): stop it by the PID AT-SPI
        # reports, or the next run's file opens inside it, outside the task (first measured run: Kate 1/10)
        name = proc["program"]["name"]
        left = {a11y.app_pid(a) for a in task.roots() if _safe(a.get_name) == name and a11y.app_pid(a) not in before}
        for pid in left:
            _stop_pid(pid)
        res["stopped"] = sorted(left)
    return res


def inner(a) -> int:
    b = benchmod.Bench(os.environ["N152_BENCH"])
    jobs = json.loads(Path(a.job).read_text())
    outd = b.base / "lib"
    outd.mkdir(exist_ok=True)
    work = Path(b.desc["home"]) / "lavoro"
    work.mkdir(exist_ok=True)
    try:
        b.up()
        from gi.repository import Atspi
        a11y.init()                                     # after up(): before it, libatspi would start its own bus
        Atspi.set_timeout(2000, 15000)                   # a modal dialog must not hold a step for 25 s
        for j in jobs:
            # T16c: the bytes already shown (inline, with their sha256), never re-read from a path when given
            if "proc_json" in j:
                import hashlib
                raw = j["proc_json"].encode()
                if j.get("sha256") and hashlib.sha256(raw).hexdigest() != j["sha256"]:
                    raise RuntimeError("procedure bytes differ from the ones shown")
                proc = json.loads(raw)
            else:
                proc = json.loads(Path(j["proc"]).read_text())
            if j.get("input") == "keys" and not KEYS:
                KEYS["pending"] = True
            params = {k: sub(str(v), {"lavoro": str(work)}) for k, v in j.get("params", {}).items()}
            r = run_one(b, proc, params, j.get("locale", "it"), work)
            r["files"] = sorted(str(x.relative_to(work)) for x in work.rglob("*"))
            for chk in j.get("check_reads", []):
                got = next((s.get("read") for s in r["steps"] if s["n"] == chk["step"]), None)
                r.setdefault("checks", []).append({"step": chk["step"], "want": chk["equals"], "got": got,
                                                   "ok": got == chk["equals"]})
            for chk in j.get("check_files", []):
                f = work / chk["path"]
                r.setdefault("checks", []).append({"path": chk["path"], "exists": f.exists(),
                                                   "content_ok": (f.read_text(errors="replace").rstrip("\n") == chk["text"])
                                                   if f.is_file() and "text" in chk else None})
            (outd / f"{j['tag']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    finally:
        if KEYS.get("kb"):
            KEYS["kb"].close()
            KEYS["pt"].close()
        b.down()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default=str(benchmod.default_scratch()))
    ap.add_argument("--job")
    ap.add_argument("--inside", action="store_true")
    a = ap.parse_args()
    if a.inside:
        return inner(a)
    desc = benchmod.prepare(Path(a.scratch))
    argv = ["/usr/bin/python3", "-I", "-B", str(Path(__file__).resolve()), "--inside", "--job",
            str(Path(a.job).resolve())]
    rc = benchmod.reexec_inside(desc, argv)
    print(f"results: {desc['base']}/lib")
    return rc


if __name__ == "__main__":
    sys.exit(main())
