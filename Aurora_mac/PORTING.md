# Aurora on the Mac — the porting inventory

Every place where the Linux code speaks to the system, what replaces it on the Mac, and the phase that does it.
Counted on 2026-10-08 from the published code (the mirror, commit c6cea57) with grep and read one by one; the counts
are of files, the tests are in `sys/core/tests/test_platform_*.py`.

**Status: phases 1 and 2 done** — the interface (`aurora/sys_platform/base.py`), the Linux reference (`linux.py`, checked
against the real Linux machine) and the Mac backend (`mac.py`, checked with recorded outputs of macOS's tools).
The Linux code stays the only truth: `build.py` applies the 77 rewrites to a copy. Nothing has run on a real Mac.

## Phases

| Phase | What | Checked how |
|---|---|---|
| 1 ✅ | Interface + Linux reference + Mac backend; build.py | Linux tests against the real machine; Mac tests with recorded outputs |
| 2 ✅ | REWRITES: each Linux call site below goes through `sys_platform.current()`, one area at a time | The Linux suite unchanged on the built tree; the Mac tests |
| 2b ✅ | On a real Mac (8 Oct): the Ports workflow (macos-latest, Apple Silicon) — build, requirements from PyPI, platform tests, `probe.py` (37 checks: each read of the backend called; a socket of ours listening, a lock stopping another process, a system folder the administrators', a file replaced while read, accents through run()), the Linux suite for information | Linux reference: 37 checks, 27 ok, 0 failed, 10 info; on Mac: the workflow's first run |
| 3 | Installer (bash + Homebrew): Python, venv, llama.cpp Metal build, Caddy, ffmpeg, the launchd agents, the key | A macOS runner on GitHub Actions (macos-latest, Apple Silicon): install, start, health, tests |
| 4 | Cage for plugins and projects (sandbox-exec profile); the host firewall (pf anchor) | Until then neither runs |
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
plists), sys_ethics_sign, sys_nas_mount, sys_backup_retime, sys_relocate, sys_restore,
sys_factory_reset, sys_users_migrate, sys_doctor, the voice install scripts; the models' device («cuda» written in
mdl_tts, img_paint, img_ai, tts_qwen_worker and the settings' cuda:N) → «mps»; the pages' words «systemd» in the health card.
Phase 4: the cage (plg_sandbox, prj_run) and the host firewall (sec_hostfw).

## Checked against the sources (2026-10-08) — and what that changed

| What | Fact | Source | Effect |
|---|---|---|---|
| launchd | `launchctl print` exit 113 «Could not find service»; `bootout` 3 = ESRCH (not loaded); `bootstrap` 5 «Input/output error» = already loaded or a bad plist | Apple developer forums, Homebrew and GitLab issues (launchd is not open source: to see again on a Mac) | 5 was not handled: now «already loaded» |
| launchd's agents | a minimal PATH (no /opt/homebrew/bin: no ffmpeg); a folder protected by the Mac's privacy (Desktop, Documents, **Downloads**) makes the service fail (exit 78) | «5 launchd traps» (dev.to) | for phase 3: the plists set PATH and WorkingDirectory; **Aurora is not installed in Downloads on a Mac** |
| avfoundation listing | `[0] Name` (older ffmpeg) or `[0] Name  [uid:...] [serial:...]` | FFmpeg libavdevice/avfoundation.m, avf_log_device_entry | **my error**: the uid would have been part of the name — now cut |
| Python | text files seeked to 1<<30 move the descriptor there, size and content untouched (a+, w+, r) | measured here, Python 3.14 | the far lock's Python side holds |
| Python wheels | the 22 direct requirements have wheels for macOS arm64 and Windows amd64 on Python 3.14; of the 113 locked, the CUDA libraries and triton are Linux-only (torch asks for them with platform_system == "Linux"), http-ece is a pure-Python source package | PyPI JSON | **requirements.lock is Linux's**: phase 3 makes one per system (uv pip compile --python-platform); torch from PyPI is CPU-only on Windows (CUDA from download.pytorch.org), MPS on the Mac |
| External programs | every program started by the modules and the scripts, read from the syntax tree | tests/test_platform_residue.py | found `ss` (sec_hostaudit), `ip` (sec_fwapi), `curl -o /dev/null` (sys_health) not yet handled: rewritten (NETWORK). Programs passed as a variable (ffmpeg in aud_analysis and vid_ai, the Python workers, llama-server) checked by hand |
| Paths written as text | `str(relative path)` gives `\` on Windows | read one by one | sys_user_config (the papers recognised), sys_backup and sys_uploads (names with '/'), api/knowledge (both separators), sec_mask and agt_forge (the home folder masked) — PATHS |

Intended differences on Linux, none in behaviour the suite checks: a service that is not installed is «missing»
(before: «inactive», from `systemctl is-active`); the health card says «missing» for it.

## Inventory

| Area | Linux code (files) | Interface | Mac | Phase |
|---|---|---|---|---|
| Services: state, start, stop, restart | systemctl in agt_change, sys_soak, net_cloudflare, sys_health, mdl_image, sys_backup, api/agents, api/backup, api/knowledge, sys_doctor, sys_users_migrate, sys_restore, sys_factory_reset, sys_nas_mount, sys_backup_retime (19 files) | `service_state`, `service_action` | launchd agents of the owner (~/Library/LaunchAgents/com.aurora.*.plist, gui/<uid>): launchctl print / bootstrap / kickstart -k / bootout, no root needed. They run while the owner is logged in: a Mac kept as a server logs in by itself. Only Aurora's own services and start/stop/restart (the polkit rule's limit) | 1 ✅ / 2 |
| Graceful stop | SIGTERM handlers in svc_harvester, svc_rem, svc_sentinel, svc_llm; uvicorn | — | launchd sends SIGTERM: the same as Linux | 1 ✅ |
| Units, timers, polkit | sys_install_services.py writes units, 50-aurora.rules, install.sh | — | The installer writes the plists (KeepAlive, RunAtLoad, EnvironmentVariables, the log files) | 3 |
| Backup timer | aurora-backup.timer, sys_backup_retime (drop-in in /etc/systemd) | — | StartCalendarInterval in com.aurora.backup.plist; a new time = the plist rewritten and bootstrapped again | 3 |
| NAS mount | sys_nas_mount: fstab, cifs, /etc/aurora/nas.cred | `is_mount` | mount_smbfs into a folder of the owner, the password in the Keychain (security add-internet-password) | 3 |
| GPU | nvidia-smi in sys_metrics, kno_mood, mdl_image, api/core, sys_profile, sys_bugreport, bench_image (9 files) | `gpus`, `accelerator` | Apple GPU: name from system_profiler, memory = the machine's (unified); its use is **not measured** without root (powermetrics): said so. Intel Macs: CPU | 1 ✅ |
| CPU, memory | /proc/stat, /proc/meminfo (sys_metrics) | `cpu_percent`, `memory` | psutil (already installed with Aurora: 7.2.2) | 1 ✅ / 2 |
| Disk, mounts | /proc/self/mounts (sys_backup), shutil.disk_usage | `is_mount` | os.path.ismount; disk_usage works | 1 ✅ |
| File locks | fcntl in mdl_image, mdl_budget, sys_backup, sys_health, sec_fwapi (5 files) | `lock`, `unlock` | The same fcntl.flock (BSD) | 1 ✅ |
| Atomic replace | os.replace after a tmp file, everywhere | `replace` | The same as Linux | 1 ✅ |
| Text encoding | 38 read_text(), 24 write_text(), 8 open() without encoding= | `process_env` | UTF-8 is the Mac's default: nothing to do | 1 ✅ |
| Temporary files read by ffmpeg | NamedTemporaryFile in sns_av, kno_video (2) | — | Works as on Linux | — |
| Secrets' permissions | chmod 0600/0700 in 20+ places | — | The same chmod | 1 ✅ |
| Owner's signing key | /etc/aurora, root-owned (sys_ethics — protected file, needs the owner's signature), sys_ethics_sign | `key_dir`, `trusted_by_admin_only`, `is_admin` | /Library/Application Support/Aurora/keys, root-owned and writable by root only (the same test as Linux); sudo works the same | 1 ✅ / 2 (signed) |
| Machine id | /etc/machine-id (sys_ethics) | `machine_id` | IOPlatformUUID (ioreg) | 1 ✅ |
| OS description | /etc/os-release, platform.release (sys_bugreport) | `os_info` | sw_vers | 1 ✅ |
| Service user | pwd in sys_config, sys_install_services, sys_nas_mount | — | pwd works on the Mac: the owner | 2 |
| Camera, microphone | sns_av: /sys/class/video4linux, pactl, ffmpeg v4l2/pulse, XDG_RUNTIME_DIR | `cameras`, `microphones`, `ffmpeg_camera`, `ffmpeg_microphone` | ffmpeg avfoundation by index; «Capture screen» never offered as a camera. macOS asks the owner once per program (Privacy): a launchd agent cannot show the question — the first photo and recording are made from the Terminal by the installer | 1 ✅ / 3 |
| Fonts for the videos | DejaVuSans-Bold path (kno_story) | `bold_font`, `ffmpeg_path` | Arial Bold (Supplemental) or Helvetica.ttc | 1 ✅ / 2 |
| Word lists | /usr/share/dict (sec_privacy) | `dictionaries` | /usr/share/dict/words (English only): fewer Italian words recognised — to measure | 2 |
| venv, programs | .venv/bin/python; llama.cpp bin/llama-server (svc_llm) | `venv_python`, `executable` | The same paths | 1 ✅ |
| Tools missing | «sudo apt install ffmpeg / poppler-utils» (sys_features) | `install_hint` | brew install ffmpeg / poppler | 1 ✅ |
| Administrator commands | «sudo …» in hints | `as_admin` | sudo | 1 ✅ |
| Plugin cage | bwrap (plg_sandbox, prj_run) | `sandbox` | sandbox-exec (Seatbelt), present though deprecated by Apple: its profile is phase 4. **plg_host (protected) today runs a plugin uncaged when bwrap is missing** (only its own secrets filtered, plg_host.py:140): on the Mac that would be every plugin. Phase 2 must make plg_host refuse instead (the owner signs it) | 2 (refuse) / 4 (cage) |
| Host firewall | nft through /usr/local/sbin/aurora-nft and an AF_UNIX socket (sec_hostfw) | `host_firewall` | pf with an anchor of Aurora's, through a root helper (a launchd daemon) and an AF_UNIX socket as on Linux | 4 |
| Cloudflare tunnel | systemctl on cloudflared's unit (net_cloudflare) | `service_state`, `service_action` | cloudflared as a launchd service (brew services) | 3 |
| HTTPS | Caddy, the Caddyfile generator | — | caddy from Homebrew; the same Caddyfile | 3 |
| Python packages | requirements.txt: torch 2.14 from PyPI (CUDA on Linux) | — | torch from PyPI carries MPS on Apple Silicon; faiss-cpu has arm64 wheels — to check at install. The models service asks for "mps" where it asks for "cuda" (phase 2) | 2 / 3 |
| LLM runtime | llama.cpp built for CUDA (sys_nvidia.sh, svc_llm) | `accelerator` | llama.cpp built with Metal (the default on Apple Silicon) | 3 |
| Shell scripts | install.sh, sys_nvidia.sh, sys_tts_install.sh, sys_relocate.sh, dev_publish.sh | — | bash exists on the Mac (3.2, old): the owner's scripts are checked for bash 4 features; apt → brew | 3 |
| File names | — | — | Measured on 27,280 names: no case clashes (the Mac's disk ignores case by default); ':' is allowed by APFS but Finder shows it as '/': the 5 PDFs in usr/documents/papers with ':' keep working | measured |

## Never

- Never a silent fall back to Linux commands (`for_system` raises for a system without a backend).
- Never a plugin or a project uncaged because the cage is missing.
- Never a number not measured: the Apple GPU's use, the wheels are «to check» until a run shows them.

## The plugins on the Mac (checked 8 October 2026)

Read from each plugin's code (a test now fails on any Linux-only word or program in sys/plugins: test_platform_residue)
and from what each needs around it. **The one that decides everything: the cage.** On Linux every plugin runs in
bubblewrap; the Mac has no bwrap, and the port refuses to start a plugin without a cage while AURORA_PLUGIN_SANDBOX
was on (GUARDS). **Done 8 Oct (the owner's «A»):** sandbox-exec, a profile from cage_plan (`mac.profile`); the same contract as bubblewrap (`cage_plan`), checked by `probe.py` with a real process in the real cage on the Mac (the Ports run).

| Plugins | What they need | On the Mac |
|---|---|---|
| calendar, weather, news, cinema, notes, expenses, health, diary, documents, email, email_diag, telegram, discord, mastodon, nextcloud, whatsapp, twitch, instagram, homeassistant, netintel, web, pyenv, logs, self, cloud | Python and the network only | ✅ the same code (pure Python, httpx, the MCP library) — after the cage |
| facebook (videos: ffprobe), dj (ffmpeg), projects (git) | ffmpeg, git | ✅ code portable; the installer installs ffmpeg and git (brew install ffmpeg git) |
| senses | camera and microphone | ✅ through sys_platform (avfoundation, phase 2) |
| backup | the NAS (smb://) mounted on /mnt/aurora-nas by aurora-mount | 🔨 phase 3: mount_smbfs into ~/aurora-nas (no root), the same mount check through the mount table; its card's text shows Linux commands |
| cloudflare | cloudflared installed and run as the service aurora-tunnel (sys/deploy/cloudflared/install.sh: apt + systemd) | 🔨 phase 3: brew install cloudflared, a launchd agent com.aurora.tunnel; its card says `sudo bash …install.sh` |
| github | its own program, sys/runtime/github-mcp-server (Go) — **no script installs it, not even on Linux** (found 8 Oct) | 🔨 phase 3: the installer downloads the release asset of the system (github-mcp-server_Darwin_arm64.tar.gz) — on Linux too |
| dropbox, tiktok | authorize.py, told as `.venv/bin/python …` | 🔨 phase 3: the command written per system (.venv/bin/python, as today) |
| security (host firewall part) | nftables | ⏸️ phase 4 (pf, or the Mac's application firewall: to decide); the firewall's API part (Sophos) is portable |
