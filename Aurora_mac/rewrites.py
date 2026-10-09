# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The places of the Linux code that speak to the system, sent through sys_platform (phase 2). The same for both ports:
sys_platform.current() picks the backend. Each rewrite: (file, anchor found exactly once, replacement, why).

The proof that a rewrite keeps Linux as it is: the whole Linux suite on the built tree, where current() is the Linux
reference (build.py --suite). Areas are added one at a time, each with that proof."""

P = "from aurora import sys_platform"

SERVICES = [
    # agt_change (a protected file: each installation signs its own code at setup)
    ("sys/core/aurora/agt_change.py",
     '''        threading.Timer(3, lambda: subprocess.run(["systemctl", "restart", "--no-block", *services],
                                                  capture_output=True, timeout=30)).start()''',
     f'''        {P}
        threading.Timer(3, lambda: sys_platform.current().service_action("restart", services, wait=False)).start()''',
     "agt_change: the changed services restarted"),

    ("sys/core/aurora/sys_soak.py",
     '''    try:
        out = subprocess.run(["systemctl", "show", name, "-p", "MemoryCurrent", "-p", "NRestarts", "-p", "ActiveState"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    v = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    mem = v.get("MemoryCurrent", "")
    return {"mem_mib": round(int(mem) / 2**20, 1) if mem.isdigit() else None,
            "restarts": int(v["NRestarts"]) if v.get("NRestarts", "").isdigit() else None, "state": v.get("ActiveState")}''',
     f'''    {P}
    v = sys_platform.current().service_info(name)
    return {{"mem_mib": v["mem_mib"], "restarts": v["restarts"], "state": v["state"]}}''',
     "sys_soak: a service's memory, restarts and state"),

    ("sys/core/aurora/net_cloudflare.py",
     '''    r = subprocess.run(["systemctl", "show", "-p", "LoadState,ActiveState", "--value", UNIT],
                       capture_output=True, text=True, timeout=10)
    load, _, active = r.stdout.strip().partition("\\n")
    return "missing" if load.strip() != "loaded" else active.strip() or "inactive"''',
     f'''    {P}
    return sys_platform.current().service_state(UNIT)''',
     "net_cloudflare: the tunnel's state"),
    ("sys/core/aurora/net_cloudflare.py",
     '''    systemctl = systemctl or (lambda verb: subprocess.run(["systemctl", verb, UNIT], capture_output=True, text=True,
                                                          timeout=30))''',
     f'''    {P}
    systemctl = systemctl or (lambda verb: sys_platform.current().service_action(verb, [UNIT], timeout=30))''',
     "net_cloudflare.apply: the tunnel started or restarted"),
    ("sys/core/aurora/net_cloudflare.py",
     '''    systemctl = systemctl or (lambda verb: subprocess.run(["systemctl", verb, UNIT], capture_output=True, text=True, timeout=30))''',
     f'''    {P}
    systemctl = systemctl or (lambda verb: sys_platform.current().service_action(verb, [UNIT], timeout=30))''',
     "net_cloudflare.stop: the tunnel stopped"),

    ("sys/core/aurora/sys_health.py",
     '''        return subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5).stdout.strip()''',
     f'''        {P}
        return sys_platform.current().service_state(name)''',
     "sys_health: each service's state"),

    ("sys/core/aurora/mdl_image.py",
     '''    subprocess.run(["systemctl", verb, unit], check=True, timeout=120)       # polkit rule 50-aurora.rules''',
     f'''    {P}
    r = sys_platform.current().service_action(verb, [unit])         # polkit rule 50-aurora.rules on Linux
    if r.code != 0:
        raise subprocess.CalledProcessError(r.code, [verb, unit], r.out, r.err)''',
     "mdl_image: the reasoner stopped and started around a GPU job"),
    ("sys/core/aurora/mdl_image.py",
     '''    return subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=30).returncode == 0''',
     f'''    {P}
    return sys_platform.current().service_state(unit) == "active"''',
     "mdl_image: is the reasoner on"),

    ("sys/core/aurora/sys_backup.py",
     '''    import subprocess
    try:
        out = subprocess.run(["systemctl", "show", unit, "-p", "Result", "-p", "ExecMainStatus", "-p", "LoadState"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    v = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    if v.get("LoadState") != "loaded" or v.get("Result", "success") == "success":
        return None
    code = int(v.get("ExecMainStatus") or 0)
    return UNIT_STATUS.get(code, f"esito {v.get('Result')}, codice {code}")''',
     f'''    {P}
    v = sys_platform.current().service_info(unit)
    if v["state"] == "missing" or (v["result"] or "success") == "success":
        return None
    code = v["status"] or 0
    return UNIT_STATUS.get(code, f"esito {{v['result']}}, codice {{code}}")''',
     "sys_backup: why the last backup failed"),

    ("sys/core/aurora/api/agents.py",
     '''        r = await asyncio.to_thread(subprocess.run, ["systemctl", "restart", "--no-block", *others],
                                    capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise HTTPException(status_code=500, detail=r.stderr.strip()[:300] or "systemctl failed")
    if "aurora-api" in wanted:
        threading.Timer(1.5, lambda: subprocess.run(["systemctl", "restart", "--no-block", "aurora-api"],
                                                    capture_output=True, timeout=30)).start()''',
     f'''        {P}
        r = await asyncio.to_thread(sys_platform.current().service_action, "restart", others, False, 30)
        if r.returncode != 0:
            raise HTTPException(status_code=500, detail=r.stderr.strip()[:300] or "restart failed")
    if "aurora-api" in wanted:
        {P}
        threading.Timer(1.5, lambda: sys_platform.current().service_action("restart", ["aurora-api"], False, 30)).start()''',
     "api/agents: services restarted from the WebUI"),
    ("sys/core/aurora/api/agents.py",
     '''                    threading.Timer(3.0, lambda: subprocess.run(["systemctl", "restart", "--no-block", *UNITS],
                                                                capture_output=True)).start()''',
     f'''                    {P}
                    threading.Timer(3.0, lambda: sys_platform.current().service_action("restart", UNITS, False)).start()''',
     "api/agents: every service restarted after an update"),

    ("sys/core/aurora/api/backup.py",
     '''    unit = subprocess.run(["systemctl", "show", "-p", "LoadState,ActiveState", "--value", "aurora-backup.service"],
                          capture_output=True, text=True).stdout.split()
    timer = subprocess.run(["systemctl", "show", "-p", "NextElapseUSecRealtime", "--value", "aurora-backup.timer"],
                           capture_output=True, text=True).stdout.strip()''',
     f'''    {P}
    state = sys_platform.current().service_state("aurora-backup.service")
    timer = sys_platform.current().service_next_run("aurora-backup.service") or ""''',
     "api/backup: is the backup installed, running, when next"),
    ("sys/core/aurora/api/backup.py",
     '''    return {**st, "installed": bool(unit) and unit[0] == "loaded", "running": len(unit) > 1 and unit[1] == "activating",''',
     '''    return {**st, "installed": state != "missing", "running": state in ("activating", "active"),   # oneshot: active only while it runs''',
     "api/backup: installed and running from the state"),
    ("sys/core/aurora/api/backup.py",
     '''    r = subprocess.run(["systemctl", "start", "--no-block", "aurora-retime.service"], capture_output=True, text=True)''',
     f'''    {P}
    r = sys_platform.current().service_action("start", ["aurora-retime.service"], wait=False)''',
     "api/backup: the backup's new time"),
    ("sys/core/aurora/api/backup.py",
     '''    r = subprocess.run(["systemctl", "start", "--no-block", "aurora-mount.service"], capture_output=True, text=True)''',
     f'''    {P}
    r = sys_platform.current().service_action("start", ["aurora-mount.service"], wait=False)''',
     "api/backup: the NAS mounted after a settings change"),
    ("sys/core/aurora/api/backup.py",
     '''    r = subprocess.run(["systemctl", "start", "aurora-mount.service"], capture_output=True, text=True, timeout=200)''',
     f'''    {P}
    r = sys_platform.current().service_action("start", ["aurora-mount.service"], timeout=200)''',
     "api/backup: the NAS mounted now"),
    ("sys/core/aurora/api/backup.py",
     '''    r = subprocess.run(["systemctl", "start", "--no-block", "aurora-backup.service"], capture_output=True, text=True)''',
     f'''    {P}
    r = sys_platform.current().service_action("start", ["aurora-backup.service"], wait=False)''',
     "api/backup: a backup now"),

    ("sys/core/aurora/api/knowledge.py",
     '''    try:
        out = subprocess.run(["systemctl", "show", unit, "-p", "ExecStart"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return f"{cfg.root}/" in out''',
     f'''    {P}
    cmd = sys_platform.current().service_command(unit)
    return any(f"{{cfg.root}}{{sep}}" in cmd for sep in ("/", "\\\\"))      # Windows writes C:\\...\\Aurora\\''',
     "api/knowledge: a service runs this folder's code (C140)"),
    ("sys/core/aurora/api/knowledge.py",
     '''                threading.Timer(2.0, lambda: subprocess.run(["systemctl", "restart", "--no-block",
                                                             *[u for u in mine if u != "aurora-api"]], capture_output=True)).start()''',
     f'''                {P}
                threading.Timer(2.0, lambda: sys_platform.current().service_action(
                    "restart", [u for u in mine if u != "aurora-api"], False)).start()''',
     "api/knowledge: this copy's services restarted after an update"),
    ("sys/core/aurora/api/knowledge.py",
     '''                threading.Timer(4.0, lambda: subprocess.run(["systemctl", "restart", "--no-block", "aurora-api"],
                                                            capture_output=True)).start()''',
     f'''                {P}
                threading.Timer(4.0, lambda: sys_platform.current().service_action("restart", ["aurora-api"], False)).start()''',
     "api/knowledge: aurora-api restarted last after an update"),
    ("sys/core/aurora/net_https.py",
     '''    r = subprocess.run(["systemctl", verb, "aurora-https"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise HttpsError(f"systemctl {verb} aurora-https: {(r.stderr or r.stdout).strip()[-300:]}")''',
     f'''    {P}
    r = sys_platform.current().service_action("restart", ["aurora-https"], timeout=60)     # reload is Linux's verb
    if r.code != 0:
        raise HttpsError(f"aurora-https restart: {{(r.err or r.out).strip()[-300:]}}")''',
     "net_https: Caddy takes the new Caddyfile"),
    ("sys/core/aurora/mdl_modes.py",
     '''    r = run(["systemctl", verb, "aurora-llm"], capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stderr or r.stdout).strip()''',
     f'''    {P}
    r = sys_platform.current().service_action(verb, ["aurora-llm"], timeout=120)
    return r.code, (r.err or r.out).strip()''',
     "mdl_modes: the local reasoner started or stopped"),
]

LOCKS = [
    # fcntl exists on Linux and the Mac, not on Windows: imported at the top it stops the module from loading
    ("sys/core/aurora/mdl_image.py", "import fcntl\n", "", "mdl_image: no fcntl at import"),
    ("sys/core/aurora/mdl_image.py",
     """    with open(f, "a+", encoding="utf-8") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fh, fcntl.LOCK_UN)
        return False""",
     f"""    {P}
    with open(f, "a+", encoding="utf-8") as fh:
        if not sys_platform.current().lock(fh, wait=False):
            return True
        sys_platform.current().unlock(fh)
        return False""",
     "mdl_image.gpu_busy: is a GPU job holding the lock"),
    ("sys/core/aurora/mdl_image.py",
     """            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= end:""",
     f"""            {P}
            if sys_platform.current().lock(fh, wait=False):
                break
            else:
                if time.time() >= end:""",
     "mdl_image.gpu_lock: one GPU job at a time"),
    ("sys/core/aurora/mdl_image.py",
     """        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)""",
     """        finally:
            sys_platform.current().unlock(fh)""",
     "mdl_image.gpu_lock: released"),
    ("sys/core/aurora/mdl_budget.py", "import fcntl\n", "", "mdl_budget: no fcntl at import"),
    ("sys/core/aurora/mdl_budget.py",
     """        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            data = json.loads(fh.read() or "{}")
        except ValueError:
            data = {}
        change(data)
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(data))
    return data""",
     f"""        {P}
        sys_platform.current().lock(fh)
        fh.seek(0)
        try:
            data = json.loads(fh.read() or "{{}}")
        except ValueError:
            data = {{}}
        change(data)
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(data))
        fh.flush()
        # released by hand: Windows frees a lock left to the closing «when resources allow» (LockFile, Remarks)
        sys_platform.current().unlock(fh)
    return data""",
     "mdl_budget: the day's spending, one writer at a time"),
    ("sys/core/aurora/sys_backup.py", "import fcntl\n", "", "sys_backup: no fcntl at import"),
    ("sys/core/aurora/sys_backup.py",
     """    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:""",
     f"""    {P}
    try:
        if not sys_platform.current().lock(lock, wait=False):
            raise BlockingIOError
    except BlockingIOError:""",
     "sys_backup: one backup at a time"),
    ("sys/core/aurora/sys_health.py",
     """    import fcntl
    f = cfg.path("AURORA_STATUS_DIR") / "gpu.lock\"""",
     f"""    {P}
    f = cfg.path("AURORA_STATUS_DIR") / "gpu.lock\"""",
     "sys_health.gpu_job: no fcntl"),
    ("sys/core/aurora/sys_health.py",
     """        try:
            fcntl.flock(fh, fcntl.LOCK_SH | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
            return ""
        except BlockingIOError:
            return fh.read().strip() or "a GPU job\"""",
     """        if sys_platform.current().lock(fh, exclusive=False, wait=False):
            sys_platform.current().unlock(fh)
            return ""
        return fh.read().strip() or "a GPU job\"""",
     "sys_health.gpu_job: who holds the GPU"),
    ("sys/core/aurora/sec_fwapi.py",
     """    import fcntl
    f = cfg.path("AURORA_STATUS_DIR") / "security" / "fwapi.lock\"""",
     f"""    {P}
    f = cfg.path("AURORA_STATUS_DIR") / "security" / "fwapi.lock\"""",
     "sec_fwapi: no fcntl"),
    ("sys/core/aurora/sec_fwapi.py",
     """        fcntl.flock(h, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(h, fcntl.LOCK_UN)""",
     """        sys_platform.current().lock(h)
        try:
            yield
        finally:
            sys_platform.current().unlock(h)""",
     "sec_fwapi: one firewall call at a time (C192)"),
]

METRICS = [
    ("sys/core/aurora/sys_metrics.py",
     """def _cpu_times() -> tuple[int, int]:
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return idle, sum(v)


def _ram() -> dict:
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) // 1024                     # MiB
    return {"used_mib": info["MemTotal"] - info["MemAvailable"], "total_mib": info["MemTotal"],
            "swap_used_mib": info["SwapTotal"] - info["SwapFree"]}


def _gpus() -> list[dict]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        i, name, util, used, total, temp = [x.strip() for x in line.split(",")]
        gpus.append({"index": int(i), "name": name, "util_pct": int(util), "used_mib": int(used),
                     "total_mib": int(total), "temp_c": int(temp)})
    return gpus""",
     f"""{P}


def _cpu_times() -> tuple[float, float]:
    return sys_platform.current().cpu_times()


def _ram() -> dict:
    return sys_platform.current().memory()


def _int(v):
    return None if v is None else int(v)                          # not measured on this system: said, never 0


def _gpus() -> list[dict]:
    return [{{"index": g.index, "name": g.name, "util_pct": _int(g.util), "used_mib": _int(g.mem_used),
             "total_mib": _int(g.mem_total), "temp_c": _int(g.temp)}} for g in sys_platform.current().gpus()]""",
     "sys_metrics: CPU, memory, GPUs"),

    ("sys/core/aurora/kno_mood.py",
     """    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,utilization.gpu,temperature.gpu,temperature.gpu.tlimit",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    res = []
    for line in out.strip().splitlines():
        try:
            i, util, temp, margin = (x.strip() for x in line.split(","))
            res.append({"index": int(i), "util": int(util), "temp_c": int(temp),
                        "margin_c": int(margin) if margin.lstrip("-").isdigit() else None})
        except ValueError:
            continue
    return res""",
     f"""    {P}
    # a GPU whose load or temperature this system does not tell (the Mac's) gives the mood nothing: left out
    return [{{"index": g.index, "util": int(g.util), "temp_c": int(g.temp),
             "margin_c": None if g.temp_limit is None else int(g.temp_limit)}}
            for g in sys_platform.current().gpus() if g.util is not None and g.temp is not None]""",
     "kno_mood: the GPUs' load and heat"),

    ("sys/core/aurora/api/core.py",
     """    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout
        facts["gpu_memory_mib"] = {f"gpu{i.strip()}": f"{u.strip()}/{t.strip()}" for i, u, t in
                                   (l.split(",") for l in out.strip().splitlines())}
    except (OSError, subprocess.SubprocessError, ValueError):
        facts["gpu_memory_mib"] = "not measured\"""",
     f"""    {P}
    gpus = sys_platform.current().gpus()
    facts["gpu_memory_mib"] = ({{f"gpu{{g.index}}": f"{{g.mem_used:.0f}}/{{g.mem_total:.0f}}" if g.mem_used is not None
                                 and g.mem_total is not None else "not measured" for g in gpus}} or "not measured")""",
     "api/core: the GPUs' memory in Aurora's facts"),

    ("sys/core/aurora/sys_bugreport.py",
     """    try:
        env["os"] = next(l.split("=", 1)[1].strip().strip('"') for l in open("/etc/os-release")
                         if l.startswith("PRETTY_NAME="))
    except (OSError, StopIteration):
        env["os"] = "?\"""",
     f"""    {P}
    env["os"] = sys_platform.current().os_info().get("name") or "?\"""",
     "sys_bugreport: the system's name"),
]

DEVICES = [
    ("sys/core/aurora/sns_av.py",
     """    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")""",
     f"""    {P}
    env.setdefault("XDG_RUNTIME_DIR", str(sys_platform.current().runtime_dir()))""",
     "sns_av: the session's runtime folder (no os.getuid on Windows)"),
    ("sys/core/aurora/sns_av.py",
     """    out = []
    for d in sorted(Path("/sys/class/video4linux").glob("video*"), key=lambda p: int(p.name[5:])):
        try:
            if (d / "index").read_text().strip() != "0":
                continue
            out.append({"id": f"/dev/{d.name}", "name": (d / "name").read_text().strip().split(":")[0]})
        except OSError:
            continue
    return out""",
     f"""    {P}
    return [{{"id": d.id, "name": d.name}} for d in sys_platform.current().cameras()]""",
     "sns_av.cameras: v4l2, avfoundation or dshow"),
    ("sys/core/aurora/sns_av.py",
     """    r = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True, env=_env(), timeout=10)
    mics, cur = [], {}
    for line in r.stdout.splitlines():
        s = line.strip()
        if s.startswith("Name:") or s.startswith("Nome:"):
            cur = {"id": s.split(":", 1)[1].strip()}
        elif (s.startswith("Description:") or s.startswith("Descrizione:")) and cur:
            cur["name"] = s.split(":", 1)[1].strip()
            if not cur["id"].endswith(".monitor"):
                mics.append(cur)
            cur = {}
    return mics""",
     f"""    {P}
    p = sys_platform.current()
    if p.name == "linux":                                     # pactl needs the session's audio server address
        p = type(p)(run=lambda cmd, timeout=30: _run_env(cmd, timeout))
    return [{{"id": d.id, "name": d.name}} for d in p.microphones()]


def _run_env(cmd, timeout):
    from aurora.sys_platform.base import Result
    try:
        r = subprocess.run(list(cmd), capture_output=True, text=True, env=_env(), timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return Result(1, "", str(e))
    return Result(r.returncode, r.stdout, r.stderr)""",
     "sns_av.microphones: PulseAudio, avfoundation or dshow"),
    ("sys/core/aurora/sns_av.py",
     """    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-video_size", f"{w}x{h}",
                        "-i", cam, "-frames:v", "1",""",
     f"""    {P}
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *sys_platform.current().ffmpeg_camera(cam, f"{{w}}x{{h}}"),
                        "-frames:v", "1",""",
     "sns_av.photo: the camera's input for ffmpeg"),
    ("sys/core/aurora/sns_av.py",
     """    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "pulse", "-i", mic, "-t", str(seconds),""",
     f"""    {P}
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *sys_platform.current().ffmpeg_microphone(mic), "-t", str(seconds),""",
     "sns_av.record: the microphone's input for ffmpeg"),
    # an open NamedTemporaryFile cannot be opened by another program on Windows: closed first, deleted at the end
    ("sys/core/aurora/sns_av.py",
     """    with tempfile.NamedTemporaryFile(prefix="aurora-voice-", suffix=".bin") as f:
        f.write(data)
        f.flush()""",
     """    with tempfile.NamedTemporaryFile(prefix="aurora-voice-", suffix=".bin", delete_on_close=False) as f:
        f.write(data)
        f.close()                                     # Windows: ffmpeg may open it only once it is closed""",
     "sns_av.decode: the browser's recording handed to ffmpeg"),
    ("sys/core/aurora/kno_video.py",
     """    with tempfile.NamedTemporaryFile(prefix="aurora-video-", suffix=Path(name).suffix or ".mp4") as f:
        f.write(data)
        f.flush()""",
     """    with tempfile.NamedTemporaryFile(prefix="aurora-video-", suffix=Path(name).suffix or ".mp4", delete_on_close=False) as f:
        f.write(data)
        f.close()                                     # Windows: ffmpeg may open it only once it is closed""",
     "kno_video: the attached video handed to ffmpeg"),
]

FILES = [
    ("sys/core/aurora/kno_story.py",
     """FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf\"""",
     f"""{P}
# a bold sans of this system, written for an ffmpeg filter (Windows's "C:" escaped)
FONT = sys_platform.current().ffmpeg_path(sys_platform.current().bold_font() or "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")""",
     "kno_story: the font of the videos' label"),
    ("sys/core/aurora/kno_story.py",
     """    vf = (f"subtitles={folder / 'subs.srt'}:force_style=""",
     """    vf = (f"subtitles={sys_platform.current().ffmpeg_path(folder / 'subs.srt')}:force_style=""",
     "kno_story: the subtitles' file written for the filter (C:\\ on Windows)"),
    ("sys/core/aurora/sec_privacy.py",
     """DICTS = ("/usr/share/dict/words", "/usr/share/dict/italian", "/usr/share/dict/american-english",
         "/usr/share/dict/british-english")""",
     f"""{P}
DICTS = tuple(str(p) for p in sys_platform.current().dictionaries())      # none on Windows: fewer words recognised""",
     "sec_privacy: the system's word lists"),
    ("sys/core/aurora/sys_config.py",
     """    import pwd
    return str(cfg.values.get("AURORA_SERVICE_USER") or "").strip() or pwd.getpwuid(cfg.root.stat().st_uid).pw_name""",
     """    try:
        import pwd
    except ImportError:                                   # Windows: the owner who installed runs the tasks
        import getpass
        return str(cfg.values.get("AURORA_SERVICE_USER") or "").strip() or getpass.getuser()
    return str(cfg.values.get("AURORA_SERVICE_USER") or "").strip() or pwd.getpwuid(cfg.root.stat().st_uid).pw_name""",
     "sys_config.service_user: no pwd on Windows"),
    ("sys/core/aurora/sys_features.py",
     """            fix.append(f"sudo apt install {'ffmpeg' if p.startswith('ff') else 'poppler-utils' if p.startswith('pdf') else p}")""",
     f"""            {P}
            fix.append(sys_platform.current().install_hint(p))""",
     "sys_features: how to install a missing tool here"),
    ("sys/core/script/svc_llm.py",
     """    cmd = [str(bin_dir / "llama-server"),""",
     """    from aurora import sys_platform
    cmd = [str(sys_platform.current().executable(bin_dir, "llama-server")),          # .exe on Windows""",
     "svc_llm: the reasoner's program"),
    ("sys/core/aurora/net_https.py", "import os\nimport pwd\nimport subprocess\n", "import os\nimport subprocess\nimport sys\n",
     "net_https: no pwd on Windows"),
    ("sys/core/aurora/net_https.py",
     '''    """Where Caddy (run as the service user, no XDG_DATA_HOME) keeps its local authority."""
    home = Path(pwd.getpwnam(sys_config.service_user(cfg)).pw_dir)
    return home / ".local" / "share" / "caddy" / "pki" / "authorities" / "local"''',
     '''    """Where Caddy keeps its local authority: its data folder on this system (the installing user runs it)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Caddy"
    else:                                                # the Mac
        base = Path.home() / "Library" / "Application Support" / "Caddy"
    return base / "pki" / "authorities" / "local"''',
     "net_https: Caddy's data folder on the Mac and Windows"),
]

TESTS = [
    ("sys/core/tests/conftest.py",
     """    values["AURORA_ROOT"] = str(root)
""",
     """    values["AURORA_ROOT"] = str(root)
    import os
    for s in schema["settings"]:   # a port tested on another system (Windows's tree on Linux): its factory paths are
        if s["type"] == "path_abs" and s["key"] != "AURORA_ROOT" and not os.path.isabs(values[s["key"]]):
            values[s["key"]] = str(root / "bin" / values[s["key"]].replace("\\\\", "/").rsplit("/", 1)[-1])   # tests only
""",
     "conftest: the test installation's program paths valid on the machine that runs the tests"),
    ("sys/core/tests/test_nas.py",
     """from aurora import sys_backup as B
""",
     """from aurora import sys_backup as B

pytest.importorskip("pwd", reason="sys_nas_mount is Linux's /etc/fstab; Windows reaches the NAS as \\\\\\\\host\\\\share (phase 3)")
""",
     "test_nas: Linux's NAS mount said skipped where there is no such mount (Windows, a real run)"),
    ("sys/core/tests/conftest.py",
     """    import stat
    return stat.S_IMODE(Path(path).stat().st_mode) == 0o600
""",
     """    from aurora import sys_platform
    return sys_platform.current().is_private(Path(path))
""",
     "conftest.private: who may read a file, asked of this system (its ACL on Windows)"),
    ("sys/core/tests/test_backup.py",
     """    \"\"\"A18: the NAS asleep at 03:30 → the unit failed before Aurora's code ran (226/NAMESPACE): no log, no push.\"\"\"
""",
     """    \"\"\"A18: the NAS asleep at 03:30 → the unit failed before Aurora's code ran (226/NAMESPACE): no log, no push.\"\"\"
    import sys
    if sys.platform != "linux":   # it feeds systemctl's own text; launchd's and the tasks' have their test_platform_*
        pytest.skip("systemctl show's text: this system's service_info is checked in test_platform_*")
""",
     "test_backup: systemd's text said skipped elsewhere (each system's service_info has its own test)"),
]

# the protected files (sys_ethics.PROTECTED): changed in the port's code, signed by each installation at its setup
GUARDS = [
    ("sys/core/aurora/plg_host.py",
     """        if self.cfg["AURORA_PLUGIN_SANDBOX"] and plg_sandbox.available():
            cmd = plg_sandbox.wrap(cmd, p.folder, p.manifest, filtered, self.cfg)   # inside, .env is the filtered one
        else:""",
     """        from aurora import sys_platform
        caged = (sys_platform.current().cage(cmd, p.folder, p.manifest, filtered, self.cfg)
                 if self.cfg["AURORA_PLUGIN_SANDBOX"] else None)
        if caged:              # Linux: bubblewrap (inside, .env is the filtered one); the Mac, Windows: their own cage
            cmd, inside = caged
            env.update(inside)
        elif self.cfg["AURORA_PLUGIN_SANDBOX"] and sys_platform.current().name != "linux":
            # no cage here (sandbox-exec missing, an AppContainer refused): a plugin never runs uncaged because of that
            raise RuntimeError(f"{p.name}: no cage for plugins on this system, so it does not run")
        else:""",
     "plg_host: each system's cage (bubblewrap, sandbox-exec, an AppContainer); no cage, no plugin"),
    ("sys/core/aurora/sys_ethics.py",
     """KEY_DIR = Path("/etc/aurora")                       # one key pair per installation, made by the installer as root""",
     """from . import sys_platform
KEY_DIR = sys_platform.current().key_dir()           # one key pair per installation, made by the installer as the admin""",
     "sys_ethics: where the owner's key lives"),
    ("sys/core/aurora/sys_ethics.py",
     """        for x in (p.parent, p):
            st = x.stat()                                  # follows links: a link to a user's file fails here
            if st.st_uid != 0 or st.st_mode & 0o022:
                return "", f"{x} must belong to root and be writable by root only\"""",
     """        p.parent.stat(), p.stat()                          # follows links: missing = no key
        ok, why = sys_platform.current().trusted_by_admin_only(p)
        if not ok:
            return "", why""",
     "sys_ethics: the key trusted only when the admin alone can change it"),
    ("sys/core/aurora/sys_ethics.py",
     """        return "", f"no owner key at {p} (run: sudo .venv/bin/python sys/core/script/sys_ethics_sign.py setup)\"""",
     """        how = sys_platform.current().as_admin(f"{sys_platform.current().venv_python(Path('.venv'))} sys/core/script/sys_ethics_sign.py setup")
        return "", f"no owner key at {p} (run: {how})\"""",
     "sys_ethics: the command that makes the key, this system's way"),
    ("sys/core/aurora/sys_ethics.py",
     """    try:
        return Path("/etc/machine-id").read_text().strip()
    except OSError:
        return "unknown-machine\"""",
     """    return sys_platform.current().machine_id() or "unknown-machine\"""",
     "sys_ethics: this machine's id (an exemption is bound to it)"),
]

_VENV = "sys_platform.current().venv_python(__import__('pathlib').Path('.venv'))"
HINTS = [
    ("sys/core/aurora/api/agents.py",
     """SIGN = "cd {root} && sudo .venv/bin/python sys/core/script/sys_ethics_sign.py sign\"""",
     f"""{P}
SIGN = sys_platform.current().in_folder("{{root}}", sys_platform.current().as_admin(
    f"{{{_VENV}}} sys/core/script/sys_ethics_sign.py sign"))""",
     "api/agents: the signing command shown to the admin"),
    ("sys/core/aurora/api/backup.py",
     """    return [{**r, "command": f"cd {cfg.root} && .venv/bin/python sys/core/script/sys_restore.py --apply {r['snapshot']}"}""",
     f"""    {P}
    return [{{**r, "command": sys_platform.current().in_folder(cfg.root, f"{{{_VENV}}} sys/core/script/sys_restore.py --apply {{r['snapshot']}}")}}""",
     "api/backup: the restore command"),
    ("sys/core/aurora/api/system.py",
     """    return {**out, "command_mind": f"cd {cfg.root} && .venv/bin/python sys/core/script/sys_factory_reset.py --apply"}""",
     f"""    {P}
    return {{**out, "command_mind": sys_platform.current().in_folder(cfg.root, f"{{{_VENV}}} sys/core/script/sys_factory_reset.py --apply")}}""",
     "api/system: the factory reset command"),
    ("sys/core/aurora/sys_features.py",
     """FETCH = ".venv/bin/python sys/core/script/sys_models_fetch.py --models {m} --yes\"""",
     f"""{P}
FETCH = f"{{{_VENV}}} sys/core/script/sys_models_fetch.py --models {{{{m}}}} --yes\"""",
     "sys_features: the command that downloads a missing model"),
    ("sys/core/aurora/mdl_modes.py",
     """EXEMPT_COMMAND = "sudo .venv/bin/python sys/core/script/sys_ethics_sign.py exempt\"""",
     f"""{P}
EXEMPT_COMMAND = sys_platform.current().as_admin(f"{{{_VENV}}} sys/core/script/sys_ethics_sign.py exempt")""",
     "mdl_modes: the exemption's command, this system's way"),
    ("sys/core/aurora/sys_cloud_consent.py",
     """COMMAND = "sudo .venv/bin/python sys/core/script/sys_ethics_sign.py private-cloud\"""",
     f"""{P}
COMMAND = sys_platform.current().as_admin(f"{{{_VENV}}} sys/core/script/sys_ethics_sign.py private-cloud")""",
     "sys_cloud_consent: the consent's command, this system's way"),
]

MORE = [
    ("sys/core/aurora/sys_backup.py",
     """    try:
        return any(line.split()[1] == str(mount) for line in Path("/proc/self/mounts").read_text().splitlines())
    except (OSError, IndexError):
        return False""",
     f"""    {P}
    return sys_platform.current().is_mount(mount)""",
     "sys_backup.mounted: the mount table, the folder never touched"),
    ("sys/core/aurora/mdl_image.py",
     """    out = subprocess.run(["nvidia-smi", "-i", str(gpu), "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=True, timeout=30).stdout
    return float(out.strip()) / 1024""",
     f"""    {P}
    free = sys_platform.current().gpu_free_mib(gpu)
    if free is None:
        raise RuntimeError(f"GPU {{gpu}}: its free memory cannot be read on this system")
    return free / 1024""",
     "mdl_image.free_gb: room on the GPU for a picture"),
]

NETWORK = [
    ("sys/core/aurora/sec_hostaudit.py",
     """    if raw is None:
        try:
            raw = subprocess.run(["ss", "-tulnpH"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            raw = \"\"""",
     f"""    {P}
    if raw is None and sys_platform.current().name != "linux":     # netstat on the Mac, psutil on Windows
        return [{{**x, "local": _local(x["address"])}} for x in sys_platform.current().listening()]
    if raw is None:
        try:
            raw = subprocess.run(["ss", "-tulnpH"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            raw = \"\"""",
     "sec_hostaudit: the ports open on this machine"),
    ("sys/core/aurora/sec_fwapi.py",
     """    try:
        r = subprocess.run(["ip", "-j", "addr", "show"], capture_output=True, text=True, timeout=5)
        for iface in json.loads(r.stdout or "[]"):
            out.update(a["local"] for a in iface.get("addr_info", []) if a.get("local"))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass""",
     f"""    {P}
    try:
        out.update(sys_platform.current().own_addresses())
    except (OSError, ValueError, ImportError):
        pass""",
     "sec_fwapi: this machine's own addresses, never blocked (C180)"),
    ("sys/core/aurora/sys_health.py", "import shutil\nimport subprocess\n", "import os\nimport shutil\nimport subprocess\n",
     "sys_health: os for os.devnull"),
    ("sys/core/aurora/sys_health.py",
     """        out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5",""",
     """        out = subprocess.run(["curl", "-s", "-o", os.devnull, "-w", "%{http_code}", "--max-time", "5",   # NUL on Windows""",
     "sys_health: the HTTPS check's empty output"),
]

_SOON = "non ancora disponibile su questo sistema"
WORDS = [
    # the health card names the service manager of this system (Linux: systemd, as before)
    ("sys/core/aurora/sys_health.py", """            add(unit, "warn", f"risponde ma systemd dice {state!r}", how)""",
     f"""            {P}
            add(unit, "warn", f"risponde ma {{sys_platform.current().manager}} dice {{state!r}}", how)""",
     "sys_health: «systemd» named as this system's manager (1)"),
    ("sys/core/aurora/sys_health.py", """            add(unit, "down", f"non risponde ({how}), systemd: {state}", url)""",
     f"""            {P}
            add(unit, "down", f"non risponde ({{how}}), {{sys_platform.current().manager}}: {{state}}", url)""",
     "sys_health: «systemd» named as this system's manager (2)"),
    ("sys/core/aurora/sys_health.py", """        "HTTPS attivo" if state == "active" and ok else f"HTTPS non risponde ({how}), systemd: {state}", how)""",
     """        "HTTPS attivo" if state == "active" and ok else f"HTTPS non risponde ({how}), {__import__('aurora.sys_platform', fromlist=['current']).current().manager}: {state}", how)""",
     "sys_health: «systemd» named as this system's manager (3)"),
    ("sys/core/aurora/sys_health.py", """            add(unit, "down", f"fermo (systemd: {state})")""",
     f"""            {P}
            add(unit, "down", f"fermo ({{sys_platform.current().manager}}: {{state}})")""",
     "sys_health: «systemd» named as this system's manager (4)"),
    ("sys/core/aurora/net_cloudflare.py", """INSTALL = "sudo bash sys/deploy/cloudflared/install.sh (una volta sola)\"""",
     f"""{P}
INSTALL = ("sudo bash sys/deploy/cloudflared/install.sh (una volta sola)" if sys_platform.current().name == "linux"
           else "il tunnel di Aurora è {_SOON} (PORTING.md, fase 3)")""",
     "net_cloudflare: the tunnel's install command, Linux only for now"),
    ("sys/core/aurora/sec_report.py",
     """NAMES = {"firewall_api": "l'API del firewall", "hostfw": "il firewall di Aurora (sudo bash sys/deploy/nft/install.sh)",""",
     f"""{P}
NAMES = {{"firewall_api": "l'API del firewall", "hostfw": "il firewall di Aurora (sudo bash sys/deploy/nft/install.sh)"
         if sys_platform.current().name == "linux" else "il firewall di Aurora ({_SOON})",""",
     "sec_report: the host firewall's line"),
    ("sys/core/aurora/sec_hostaudit.py",
     """                        "fix": "capire quale programma è (sudo ss -tulnp) e chiuderlo o legarlo a 127.0.0.1", "port": s["port"]})""",
     """                        "fix": f"capire quale programma è ({__import__('aurora.sys_platform', fromlist=['current']).current().listen_hint}) e chiuderlo o legarlo a 127.0.0.1", "port": s["port"]})""",
     "sec_hostaudit: how to see which program listens, this system's way"),
    ("sys/core/aurora/sec_hostfw.py",
     """    if not HELPER.is_file() or not shutil.which("sudo"):
        return 1, "aurora-nft not installed: sudo bash sys/deploy/nft/install.sh\"""",
     f"""    {P}
    if sys_platform.current().name != "linux":
        return 1, "Aurora's own firewall is {_SOON} (PORTING.md, phase 4)"
    if not HELPER.is_file() or not shutil.which("sudo"):
        return 1, "aurora-nft not installed: sudo bash sys/deploy/nft/install.sh\"""",
     "sec_hostfw: said plainly where the host firewall does not exist yet"),
]

# paths written as text: always with "/" (as_posix), the same bytes on Linux, readable on every system
PATHS = [
    ("sys/core/aurora/sys_user_config.py",
     """            if (p == usr or usr in p.parents) and not str(p.relative_to(usr)).startswith(tuple(L.UNTOUCHED)):""",
     """            if (p == usr or usr in p.parents) and not p.relative_to(usr).as_posix().startswith(tuple(L.UNTOUCHED)):""",
     "sys_user_config: the owner's papers recognised on Windows too (documents\\papers ≠ documents/papers)"),
    ("sys/core/aurora/sys_backup.py",
     """                rel = str(full.relative_to(root)) if root in full.parents else "external" + str(full)""",
     """                rel = full.relative_to(root).as_posix() if root in full.parents else "external" + full.as_posix()""",
     "sys_backup: the snapshot's names with '/', restorable on any system"),
    ("sys/core/aurora/sys_uploads.py",
     """    items.append({**record, "path": str(path.relative_to(_dir(cfg)))})""",
     """    items.append({**record, "path": path.relative_to(_dir(cfg)).as_posix()})""",
     "sys_uploads: a file's place with '/'"),
    ("sys/core/aurora/sec_mask.py",
     """        if len(user) >= 3:
            own.append(f"/home/{user}")""",
     """        if len(user) >= 3:
            own.append(f"/home/{user}")
            own += [f"/Users/{user}", f"\\\\Users\\\\{user}"]           # the Mac's and Windows's home folders""",
     "sec_mask: the user's home masked on the Mac and Windows too"),
    ("sys/core/aurora/agt_forge.py",
     """        return text.replace(f"/home/{self.user}/", "/home/user/") if self.user else text""",
     """        if not self.user:
            return text
        for home, neutral in ((f"/home/{self.user}/", "/home/user/"), (f"/Users/{self.user}/", "/Users/user/"),
                              (f"\\\\Users\\\\{self.user}\\\\", "\\\\Users\\\\user\\\\")):
            text = text.replace(home, neutral)
        return text""",
     "agt_forge: the user's home made neutral on the Mac and Windows too"),
]

REQUIREMENTS = [
    ("requirements.txt", "accelerate==1.15.0\n",
     "accelerate==1.15.0\npsutil==7.2.2            # sys_platform: CPU, memory, sockets, addresses on every system (the version in requirements.lock)\n",
     "requirements: psutil named, not only pulled in by accelerate"),
    ("requirements.txt", "accelerate==1.15.0\n",
     "accelerate==1.15.0\ntzdata==2026.5 ; sys_platform == \"win32\"   # the time zones (the PSF's own): Windows has no IANA database (a real Windows, 8 Oct)\n",
     "requirements: tzdata on Windows, where Python finds no time zone without it"),
]

# phase 3: the scripts the installers run (sys_ethics_sign makes and uses the key, sys_doctor reads the services)
INSTALLER = [
    ("sys/core/script/sys_ethics_sign.py",
     """    if os.geteuid() == 0:
        st = sys_ethics.CODE_ROOT.stat()""",
     """    if hasattr(os, "geteuid") and os.geteuid() == 0:   # Windows: the folder's ACL already lets the owner read
        st = sys_ethics.CODE_ROOT.stat()""",
     "sys_ethics_sign.give_back: files handed back to the owner where there is a root"),
    ("sys/core/script/sys_ethics_sign.py",
     """    os.chown(private.parent, 0, 0)
    os.chmod(private.parent, 0o755)""",
     f"""    {P}
    sys_platform.current().guard_key_folder(private.parent)""",
     "sys_ethics_sign.keygen: the key's folder the administrator's"),
    ("sys/core/script/sys_ethics_sign.py",
     """    for f in (private, public):
        os.chown(f, 0, 0)
    os.chmod(public, 0o644)""",
     """    sys_platform.current().guard_key_files(private, public)""",
     "sys_ethics_sign.keygen: the private half the administrator's only, the public half readable"),
    ("sys/core/script/sys_ethics_sign.py",
     """    if os.geteuid() != 0:
        ap.error("run with sudo: the key lives in /etc/aurora and only root may use it")""",
     f"""    {P}
    if not sys_platform.current().is_admin():
        ap.error(f"run as the administrator: the key lives in {{sys_ethics.KEY_DIR}} and only the administrator may use it")""",
     "sys_ethics_sign: the administrator, this system's way"),
    ("sys/core/script/sys_doctor.py",
     """ROOT = Path(__file__).resolve().parents[3]""",
     """ROOT = Path(__file__).resolve().parents[3]
from aurora import sys_platform  # noqa: E402
PLAT = sys_platform.current()""",
     "sys_doctor: this system's commands"),
    ("sys/core/script/sys_doctor.py",
     """         f"sudo .venv/bin/python sys/core/script/sys_ethics_sign.py {'setup' if first else 'sign'}\"""",
     """         PLAT.as_admin(f"{PLAT.venv_python(Path('.venv'))} sys/core/script/sys_ethics_sign.py {'setup' if first else 'sign'}")""",
     "sys_doctor: the signing command, this system's way"),
    ("sys/core/script/sys_doctor.py",
     """        st = subprocess.run(["systemctl", "is-active", u], capture_output=True, text=True).stdout.strip() or "?"
        cmd = subprocess.run(["systemctl", "show", "-p", "ExecStart", u], capture_output=True, text=True).stdout
        if st == "active" and str(ROOT) + "/" not in cmd:""",
     """        st = PLAT.service_state(u)
        cmd = PLAT.service_command(u)
        if st == "active" and str(ROOT) not in cmd:""",
     "sys_doctor: each service's state and command (systemd units, scheduled tasks)"),
    ("sys/core/script/sys_doctor.py",
     """        line("✅" if st == "active" else "⚪" if st in ("inactive", "unknown") else "⛔", f"{u}: {st}")""",
     """        line("✅" if st == "active" else "⚪" if st in ("inactive", "unknown", "missing") else "⛔", f"{u}: {st}")""",
     "sys_doctor: a service not installed is not a failure"),
    ("sys/core/script/sys_profile.py",
     """    return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)""",
     """    import psutil                                         # Windows has no sysconf (a real Windows, 9 Oct)
    return round(psutil.virtual_memory().total / 2**30, 1)""",
     "sys_profile: the RAM, this system's way"),
    ("sys/core/aurora/net_https.py",
     """    threading.Timer(seconds, lambda: subprocess.run(["systemctl", "restart", "--no-block", "aurora-api"],
                                                    capture_output=True, timeout=30)).start()""",
     f"""    {P}
    threading.Timer(seconds, lambda: sys_platform.current().service_action("restart", ["aurora-api"], wait=False)).start()""",
     "net_https.restart_api_later: the API restarted after a change of ports"),
]

REWRITES = SERVICES + LOCKS + METRICS + DEVICES + FILES + GUARDS + HINTS + MORE + NETWORK + WORDS + PATHS + REQUIREMENTS + INSTALLER + TESTS
