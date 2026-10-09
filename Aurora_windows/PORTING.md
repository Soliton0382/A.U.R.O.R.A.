# Aurora on Windows — the porting inventory

Every place where the Linux code speaks to the system, what replaces it on Windows, and the phase that does it.
Counted on 2026-10-08 from the published code (the mirror, commit c6cea57) with grep and read one by one; the counts
are of files, the tests are in `sys/core/tests/test_platform_*.py`.

**Status: phases 1 and 2 done** — the interface (`aurora/sys_platform/base.py`), the Linux reference (`linux.py`, checked
against the real Linux machine) and the Windows backend (`windows.py`, checked with recorded outputs of Windows's
tools). The Linux code stays the only truth: `build.py` applies the 77 rewrites to a copy. Nothing has run on a real Windows.

## Phases

| Phase | What | Checked how |
|---|---|---|
| 1 ✅ | Interface + Linux reference + Windows backend; build.py | Linux tests against the real machine; Windows tests with recorded outputs |
| 2 ✅ | REWRITES: each Linux call site below goes through `sys_platform.current()`, one area at a time | The Linux suite unchanged on the built tree; the Windows tests |
| 2b ✅ | On a real Windows (8 Oct): the Ports workflow (windows-latest, x64) — build, requirements from PyPI, platform tests, `probe.py` (37 checks: each read of the backend called; a socket of ours listening, a lock stopping another process, a system folder the administrators', a file replaced while read, accents through run()), the Linux suite for information | Linux reference: 37 checks, 27 ok, 0 failed, 10 info; on Windows: the workflow's first run |
| 3 🔨 | Installer (PowerShell): Python, venv, Caddy, ffmpeg, the tasks, the ACLs, the key — **cloud reasoner done** (9 Oct, `install.ps1` + `sys_install_tasks.py`, on a real Windows 11 VM: fresh install and update); llama.cpp CUDA build left | The owner's Windows 11 VM (2 vCPU, 15.6 GB): unattended install, six tasks, HTTPS trusted by the system, a masked question through a stand-in provider |
| 4 | Cage for plugins and projects; the host firewall | Research first (AppContainer / Job objects); until then neither runs |
| 5 | The owner's real machine (if one appears) or the runner only | — |

## Phase 2 — done (2026-10-08)

77 rewrites in 33 files (`rewrites.py`, the same for both ports), in eleven areas, each proved by **the whole Linux
suite on the built tree** (where `current()` is the Linux reference) and, where a value can be read here, by the
original and the rewritten module side by side on this machine:

| Area | Rewrites | Checked side by side on the Linux machine |
|---|---|---|
| Services | 19 (agt_change, sys_soak, net_cloudflare, sys_health, mdl_image, sys_backup, api/agents, api/backup, api/knowledge) | — (they start and stop services) |
| Locks | 11 (mdl_image, mdl_budget, sys_backup, sys_health, sec_fwapi; no `import fcntl` left) | — |
| Measures | 4 (sys_metrics, kno_mood, api/core, sys_bugreport) | the same totals and GPUs; CPU and use differ only by the moment |
| Devices and temporary files | 7 (sns_av, kno_video) | the same webcam and microphone |
| Files | 5 (kno_story font, sec_privacy, sys_config, sys_features, svc_llm) | — |
| Guards | 5 (plg_host: no cage → no plugin outside Linux; sys_ethics: key folder, trust, machine id) | the real key: the same answer, the same refusal for a key not root's |
| Commands shown and the rest | 8 (sign, restore, factory reset, model download; NAS mount table; GPU free memory) | the same strings, character by character |
| Network (after the check of every program) | 4 (sec_hostaudit ports, sec_fwapi own addresses, sys_health curl output) | the same 39 sockets and 5 addresses; psutil's view = ss and ip |
| Words shown | 8 (health card's «systemd», tunnel, host firewall, «which program listens») | the same texts on Linux |
| Paths as text | 5 (papers in a user's settings, backup names, uploads, two home-folder masks) | the same bytes on Linux (as_posix) |
| Requirements | 1 (psutil named) | — |

`tests/test_platform_residue.py` fails as soon as a Linux-only call appears in the modules Aurora runs without being
listed here (it finds 19 kinds of them in the Linux code before the rewrites).

Left for phase 3 (the installer and the admin's scripts): install.sh, sys_nvidia.sh, sys_install_services (units →
task XML), sys_ethics_sign, sys_nas_mount, sys_backup_retime, sys_relocate, sys_restore,
sys_factory_reset, sys_users_migrate, sys_doctor, the voice install scripts; the models' device («cuda» written in
mdl_tts, img_paint, img_ai, tts_qwen_worker and the settings' cuda:N); the pages' words «systemd» in the health card.
Phase 4: the cage (plg_sandbox, prj_run) and the host firewall (sec_hostfw).

## Checked against the sources (2026-10-08) — and what that changed

| What | Fact | Source | Effect |
|---|---|---|---|
| Task Scheduler results | SCHED_S_TASK_READY 0x41300, _RUNNING 0x41301, _HAS_NOT_RUN 0x41303, _TERMINATED 0x41306, _QUEUED 0x41325; **0x8004130F is SCHED_E_ACCOUNT_INFORMATION_NOT_SET, an error** | Microsoft Learn, «Task Scheduler error and success constants» | **my error**: 0x8004130F was among the «not failed» — a broken task would have looked stopped |
| Task states | Unknown, Disabled, Queued, Ready, Running | MS-TSCH 2.3.13 TASK_STATE | Queued now said «activating» (started, not running yet), as systemd says it |
| winget | Gyan.FFmpeg (aliases ffmpeg, ffprobe) and oschwartz10612.Poppler exist; a portable file without an alias gets its own file name as the command (pdftoppm, pdfinfo) | microsoft/winget-pkgs manifests; winget-cli PortableFlow.cpp lines 236-238 | verified |
| LockFile | bytes past the end of the file can be locked; locks are mandatory; a lock left to the closing is freed «when resources allow» | Microsoft Learn, LockFile, Remarks | mdl_budget now unlocks by hand |
| dshow listing | `"Name" (video)`, `"Name" (video, audio)`, `"Name" (none)`, then `  Alternative name "..."` | FFmpeg libavdevice/dshow.c | **my error**: a device of both kinds was dropped — now a camera and a microphone |
| psutil on Windows | the listening sockets and their processes without the administrator | psutil on this Linux gives the same 30 ports as ss and the same 5 addresses as ip (measured) | — |
| Python | text files seeked to 1<<30 move the descriptor there, size and content untouched (a+, w+, r) | measured here, Python 3.14 | the far lock's Python side holds |
| Python wheels | the 22 direct requirements have wheels for macOS arm64 and Windows amd64 on Python 3.14; of the 113 locked, the CUDA libraries and triton are Linux-only (torch asks for them with platform_system == "Linux"), http-ece is a pure-Python source package | PyPI JSON | **requirements.lock is Linux's**: phase 3 makes one per system (uv pip compile --python-platform); torch from PyPI is CPU-only on Windows (CUDA from download.pytorch.org), MPS on the Mac |
| External programs | every program started by the modules and the scripts, read from the syntax tree | tests/test_platform_residue.py | found `ss` (sec_hostaudit), `ip` (sec_fwapi), `curl -o /dev/null` (sys_health) not yet handled: rewritten (NETWORK). Programs passed as a variable (ffmpeg in aud_analysis and vid_ai, the Python workers, llama-server) checked by hand |
| Paths written as text | `str(relative path)` gives `\` on Windows | read one by one | sys_user_config (the papers recognised), sys_backup and sys_uploads (names with '/'), api/knowledge (both separators), sec_mask and agt_forge (the home folder masked) — PATHS |

Intended differences on Linux, none in behaviour the suite checks: a service that is not installed is «missing»
(before: «inactive», from `systemctl is-active`); the health card says «missing» for it.

## Inventory

| Area | Linux code (files) | Interface | Windows | Phase |
|---|---|---|---|---|
| Services: state, start, stop, restart | systemctl in agt_change, sys_soak, net_cloudflare, sys_health, mdl_image, sys_backup, api/agents, api/backup, api/knowledge, sys_doctor, sys_users_migrate, sys_restore, sys_factory_reset, sys_nas_mount, sys_backup_retime (19 files) | `service_state`, `service_action` | Scheduled tasks in `\Aurora\` (at logon, restart on failure, as the owner); PowerShell ScheduledTasks: states are English enum names on every Windows (schtasks.exe translates them). Only Aurora's own services and start/stop/restart (the polkit rule's limit) | 1 ✅ / 2 |
| Graceful stop | SIGTERM handlers in svc_harvester, svc_rem, svc_sentinel, svc_llm; uvicorn | — | Windows has no SIGTERM: a stopped task ends the process. The stores already write tmp + replace (safe). svc_llm forwards SIGTERM to llama-server: on Windows the task stops the child with it (a Job object in the launcher, phase 3) | 3 |
| Units, timers, polkit | sys_install_services.py writes units, 50-aurora.rules, install.sh | — | The installer writes the task XML (triggers, RestartOnFailure, the environment) | 3 |
| Backup timer | aurora-backup.timer, sys_backup_retime (drop-in in /etc/systemd) | — | A daily trigger on the task `\Aurora\backup`; a new time = Set-ScheduledTask | 3 |
| NAS mount | sys_nas_mount: fstab, cifs, /etc/aurora/nas.cred | `is_mount` | No mount: Windows writes to `\\nas\share` directly; the credential in Windows's Credential Manager (cmdkey) | 3 |
| GPU | nvidia-smi in sys_metrics, kno_mood, mdl_image, api/core, sys_profile, sys_bugreport, bench_image (9 files) | `gpus`, `accelerator` | The same nvidia-smi and CSV (System32) | 1 ✅ |
| CPU, memory | /proc/stat, /proc/meminfo (sys_metrics) | `cpu_percent`, `memory` | psutil (already installed with Aurora: 7.2.2) | 1 ✅ / 2 |
| Disk, mounts | /proc/self/mounts (sys_backup), shutil.disk_usage | `is_mount` | os.path.ismount; disk_usage works | 1 ✅ |
| File locks | fcntl in mdl_image, mdl_budget, sys_backup, sys_health, sec_fwapi (5 files) | `lock`, `unlock` | msvcrt.locking on byte 0, our own wait (msvcrt gives up after 10 s); no shared lock: shared = exclusive | 1 ✅ |
| Atomic replace | os.replace after a tmp file, everywhere (stores, settings, uploads) | `replace` | A reader holding the file open makes os.replace fail (sharing violation): retried for up to 1 s | 1 ✅ / 2 |
| Text encoding | 38 read_text(), 24 write_text(), 8 open() without encoding= | `process_env` | Every process starts with PYTHONUTF8=1 (otherwise cp1252: every accent) | 1 ✅ / 3 |
| Temporary files read by ffmpeg | NamedTemporaryFile in sns_av, kno_video (2) | — | An open NamedTemporaryFile cannot be opened by another process: delete=False + unlink after | 2 |
| Secrets' permissions | chmod 0600/0700 in 20+ places (.env, uploads, keys, backups) | — | chmod does nothing: the installer gives the Aurora folder to the owner and SYSTEM only (icacls /inheritance:r) | 3 |
| Owner's signing key | /etc/aurora, root-owned (sys_ethics — protected file, needs the owner's signature), sys_ethics_sign | `key_dir`, `trusted_by_admin_only`, `is_admin` | %ProgramData%\Aurora\keys, trusted when owner and every writer are SYSTEM / Administrators / TrustedInstaller — read as SIDs (names are translated). The installer removes inherited rights (ProgramData lets Users create files) | 1 ✅ / 2 (signed) |
| Machine id | /etc/machine-id (sys_ethics) | `machine_id` | MachineGuid (reg.exe) | 1 ✅ |
| OS description | /etc/os-release, platform.release (sys_bugreport) | `os_info` | Win32_OperatingSystem | 1 ✅ |
| Service user | pwd in sys_config, sys_install_services, sys_nas_mount | — | The owner who installed (getpass.getuser) | 2 |
| Camera, microphone | sns_av: /sys/class/video4linux, pactl, ffmpeg v4l2/pulse, XDG_RUNTIME_DIR | `cameras`, `microphones`, `ffmpeg_camera`, `ffmpeg_microphone` | ffmpeg dshow (old and new list formats); a device by its unique alternative name | 1 ✅ / 2 |
| Fonts for the videos | DejaVuSans-Bold path (kno_story) | `bold_font`, `ffmpeg_path` | arialbd.ttf / segoeuib.ttf; ':' escaped in ffmpeg filters (C\:/Windows/...) | 1 ✅ / 2 |
| Word lists | /usr/share/dict (sec_privacy) | `dictionaries` | None on Windows: the privacy check works without (fewer common words recognised) — to measure | 2 |
| venv, programs | .venv/bin/python in hints and scripts; llama.cpp bin/llama-server (svc_llm) | `venv_python`, `executable` | .venv\Scripts\python.exe, llama-server.exe | 1 ✅ / 2 |
| Tools missing | «sudo apt install ffmpeg / poppler-utils» (sys_features) | `install_hint` | winget install Gyan.FFmpeg; poppler: oschwartz10612.Poppler — **the winget ids are to be checked on Windows** | 1 ✅ / 3 |
| Administrator commands | «sudo …» in hints (sign, nft, cloudflared, restore) | `as_admin` | PowerShell as administrator | 1 ✅ / 2 |
| Plugin cage | bwrap (plg_sandbox, prj_run) | `sandbox` | None yet. **plg_host (protected) today runs a plugin uncaged when bwrap is missing** (only its own secrets filtered, plg_host.py:140): on Windows that would be every plugin. Phase 2 must make plg_host refuse instead (the owner signs it) | 2 (refuse) / 4 (cage) |
| Host firewall | nft through /usr/local/sbin/aurora-nft and an AF_UNIX socket (sec_hostfw) | `host_firewall` | Windows Firewall rules through a helper as SYSTEM; no AF_UNIX in Windows's Python: a named pipe or localhost | 4 |
| Cloudflare tunnel | systemctl on cloudflared's unit (net_cloudflare) | `service_state`, `service_action` | cloudflared installs itself as a Windows service: `sc.exe` (not a task) | 3 |
| HTTPS | Caddy (cross-platform), the Caddyfile generator | — | caddy.exe; the same Caddyfile (CSP included) | 3 |
| Python packages | requirements.txt: torch 2.14 from PyPI (CUDA on Linux) | — | **torch from PyPI is CPU only on Windows**: the CUDA build comes from download.pytorch.org (the installer chooses); faiss-cpu, the others have Windows wheels — to check at install | 3 |
| LLM runtime | llama.cpp built for CUDA (sys_nvidia.sh, svc_llm) | `accelerator` | The official llama.cpp Windows CUDA release (llama-server.exe + cudart) | 3 |
| Shell scripts | install.sh, sys_nvidia.sh, sys_tts_install.sh, sys_relocate.sh, dev_publish.sh | — | PowerShell equivalents for the owner's ones (install, tts); dev_publish stays on Linux | 3 |
| File names | — | — | Measured on 27,280 names: none too long (longest 239 of 260 as C:\Users\utente\Aurora\…), no case clashes; **5 PDFs in usr/documents/papers have ':' in the name** (the owner's documents: never touched; a migration to Windows must rename them with the owner) | measured |

## Never

- Never a silent fall back to Linux commands (`for_system` raises for a system without a backend).
- Never a plugin or a project uncaged because the cage is missing.
- Never a number not measured: the Apple/Windows GPU use, the winget ids, the wheels are «to check» until a run shows them.

## The plugins on Windows (checked 8 October 2026)

Read from each plugin's code (a test now fails on any Linux-only word or program in sys/plugins: test_platform_residue)
and from what each needs around it. **The one that decides everything: the cage.** On Linux every plugin runs in
bubblewrap; Windows has no bwrap, and the port refuses to start a plugin without a cage while AURORA_PLUGIN_SANDBOX
was on (GUARDS). **Done 8 Oct (the owner's «A»):** an AppContainer per plugin (`win_cage.py`: ACLs from cage_plan, a Job object, the capabilities); the same contract as bubblewrap (`cage_plan`), checked by `probe.py` with a real process in the real cage on Windows (the Ports run).

| Plugins | What they need | On Windows |
|---|---|---|
| calendar, weather, news, cinema, notes, expenses, health, diary, documents, email, email_diag, telegram, discord, mastodon, nextcloud, whatsapp, twitch, instagram, homeassistant, netintel, web, pyenv, logs, self, cloud | Python and the network only | ✅ the same code (pure Python, httpx, the MCP library) — after the cage |
| facebook (videos: ffprobe), dj (ffmpeg), projects (git) | ffmpeg, git | ✅ code portable; the installer installs ffmpeg and git (winget: Gyan.FFmpeg, Git.Git) |
| senses | camera and microphone | ✅ through sys_platform (dshow, phase 2) |
| backup | the NAS (smb://) mounted on /mnt/aurora-nas by aurora-mount | 🔨 phase 3: no mount: the backup writes to \\host\share\folder directly (is_mount is False by design, measured on a real Windows), target() must take that path instead of /mnt/aurora-nas; its card's text shows Linux commands |
| cloudflare | cloudflared installed and run as the service aurora-tunnel (sys/deploy/cloudflared/install.sh: apt + systemd) | 🔨 phase 3: winget install Cloudflare.cloudflared, a scheduled task \Aurora\tunnel; its card says `sudo bash …install.sh` |
| github | its own program, sys/runtime/github-mcp-server (Go) — **no script installs it, not even on Linux** (found 8 Oct) | 🔨 phase 3: the installer downloads the release asset of the system (github-mcp-server_Windows_x86_64.zip) — on Linux too |
| dropbox, tiktok | authorize.py, told as `.venv/bin/python …` | 🔨 phase 3: the command written per system (.venv\Scripts\python.exe) |
| security (host firewall part) | nftables | ⏸️ phase 4 (Windows Defender Firewall (New-NetFirewallRule): to decide); the firewall's API part (Sophos) is portable |

## Phase 3's list, from the Linux suite on a real machine (8 Oct, M149)

The whole Linux suite runs on the built tree in the Ports workflow; what fails there is the work, read from the
machine and not guessed. The run's public notices name each failed test and its reason.

## Phase 3 — the cloud installer on a real Windows 11 (2026-10-09)

`Aurora_windows\install.ps1` (run as administrator from the download): winget (Python 3.14, VC++ runtime, FFmpeg,
Poppler, Caddy), build.py into %TEMP% and the code copied over C:\Aurora (robocopy without /PURGE: .env and the data
never touched), venv from requirements.txt, the cloud model listed and tried, the profile, .env, the folder's ACL
(owner, SYSTEM, Administrators), the models, the key in %ProgramData%\Aurora\keys and the signature, six scheduled
tasks (`sys_install_tasks.py`), Caddy's root in LocalMachine\Root, the firewall rule for the home network.

What a real Windows taught, each fixed:

| Found | Fix |
|---|---|
| winget absent for a user never signed in on the desktop; then «Data required by the source is missing» | Add-AppxPackage -RegisterByFamilyName; the catalogue source2.msix added |
| torch: WinError 1114 loading c10.dll | Microsoft.VCRedist.2015+.x64 installed first |
| 49 tests failing, 12 of them cp1252 reading Aurora's UTF-8 texts | every service and script run with `python -X utf8` (37 left: listed for the next step) |
| `claude` (npm's claude.cmd) not found: WinError 2 | C218: mdl_cloud resolves it with shutil.which |
| sys_profile: os.sysconf missing | rewrite: psutil |
| sys_ethics_sign: geteuid, chown, /etc/aurora | rewrites: is_admin, guard_key_folder / guard_key_files (ACLs by SID) |
| the encoder refused to start: «permissions not readable» — PowerShell past 30 s with six services starting on 2 cores | the ACL read waits 90 s and tries twice |
| Task Scheduler restarts a task only when it fails to start, never when its program ends | a trigger every minute (IgnoreNew): a fallen service is back within 60 s; stop = Stop + Disable, start = Enable + Start |
| an update left the old code running (a running task ignores a start) | the installer restarts the tasks |
| `caddy trust`: «Richiesta non supportata» (the user's store wants a confirmation window) | the root read from Caddy's admin API and imported into LocalMachine\Root |
| `a,b` unquoted is an array in PowerShell | quoted |
| Refresh-Path dropped this window's own path | appended, not replaced |
| curl (schannel) refuses Caddy's root: no revocation list | not Aurora's: browsers accept it; `curl --ssl-no-revoke` |
| a question waited 10+ minutes behind a harvested document | C219 (all systems): the owner's requests first in aurora-models |

Not yet: the local reasoner (llama.cpp CUDA), Piper's voice, the GitHub plugin's program, a Windows lock file with
hashes (requirements.txt today), plugins (the AppContainer cage is written, not tried here), the 37 tests.
