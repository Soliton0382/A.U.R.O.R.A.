# Security, privacy, compliance

Measured on 2026-09-30 (not assumed). What is protected, how, and what is not yet.

## In transit

| path | protection | measured |
|---|---|---|
| browser / PWA / Chatbox → Aurora | Caddy, TLS 1.3 only (TLS 1.1 refused), owner's certificate, HSTS 1 year, CSP (self only, no inline script, no framing), X-Frame-Options DENY, nosniff, Referrer-Policy | `openssl s_client`, response headers; the WebUI runs under the CSP with 0 violations |
| WebUI authentication | registered device: random token in an HttpOnly, Secure, SameSite=Strict cookie; only its SHA-256 is stored (0600); the API key is used once and never kept by the browser | tests, headless Chrome |
| internal services (api 9700, models 9710, llm 9711, Caddy admin 2019) | bound to 127.0.0.1 only | `ss -ltn` |
| plugins | child processes on pipes (MCP over stdio), never a network port | code |
| telescope PC's camera → Aurora (astro_camera.ps1 + .py, 19 Oct) | the PC only sends (no port opened on it): its agent's POST (OpenCV, the camera's frames as mpjpeg) over Aurora's HTTPS; it installs Python, OpenCV and pygrabber for its user only (winget, pip) in a folder of its own with a camera key in X-Aurora-Camera — made by the person, given once, kept only as its SHA-256 with its person, one a person (a new one replaces it); it may only tell the PC's cameras and send frames, never read Aurora; a wrong key is a 401 that never counts toward the login lockout; frames in memory only, never written | test_ast_camrelay (a real ffmpeg sending; no key, 401) |
| outgoing: arXiv, Telegram, Facebook, GitHub, Mastodon, Open-Meteo, RDAP, AbuseIPDB, Brave | HTTPS only (arXiv moved from HTTP on 2026-09-30) | scan of every URL in the code |
| outgoing email | IMAP over TLS (993), SMTP over TLS (465) or STARTTLS (587): no clear-text fallback | code |
| web plugin | refuses local and private addresses, also through public DNS names that point to them | live: 192.168.x, localhost, 127.0.0.1.nip.io refused |
| firewall syslog (inbound) | UDP from the allowed addresses only (AURORA_SENTINEL_ALLOW), default 127.0.0.1; one datagram one line (control characters escaped), new sources and incidents capped, a flood told (C566). UDP's sender can be forged on the LAN: the caps bound it, they do not stop it — TLS syslog to a relay on loopback, or anti-spoofing on the switch, would | test, `test_c566_sentinel.py` |
| outgoing to cloud models | **always masked** (no setting turns it off since 2026-10-05): addresses, e-mails, phones, IBANs, cards, keys and tokens, the .env's secrets, the users' names and private words, key=value fields naming people or devices; and private keys, JWTs, a password in a link, the Italian tax code, VAT, car plates, street addresses, any value said by its name (password, PIN, tax code, passport, identity card, driving licence, health card, date of birth). The owner's name is put in before masking (C132). Pictures cannot be masked (warned) | `test_mask.py`, `test_cloud.py` (every provider wrapped) |
| from away: Cloudflare One (plugin cloudflare, optional) | WARP private network: cloudflared connects out, no port opened; only this computer's /32 (and the home DNS) routed and carried by WARP; the same name and certificate as at home, then Caddy and the device login as above. Through the tunnel every remote device has this computer's address: the lockout still counts it, the host firewall never blocks it (C180) | tests on a fake account; live not yet (N107) |
| health data | never sent to a cloud model: the private plugin answers only to the local one | `test_health.py` |

Not end-to-end encrypted by the platforms themselves: Telegram bot chats and Facebook posts are
encrypted to the platform (HTTPS) but readable by it; that is how those platforms work.

## At rest

| data | protection | state |
|---|---|---|
| `.env` and `.env.proposed` (keys, tokens) | mode 0600, kept at every write and restored at every start | was 0644 until 2026-09-30 (C30) |
| device tokens, approvals, TLS private key | 0600 | measured |
| a user's memory (STM, LTM: turns, session memories, thoughts, dreams, reviews, a chat's attached documents) | text, title and extra of every row AES-256-GCM with the user's «memory» key, the sid and the column bound to it; the vectors AES-CTR with their own key, no HNSW graph; the memory of before sealed at the start, the files' old pages emptied (VACUUM) — N64, 29 Oct | `test_memory_sealed.py`, `test_memory_seal_migration.py`; plain for the queries: dates, kind, STM/LTM, the source id (a kind and an id) |
| the traces (api, agent, search, approvals) | a chat's text in them sealed with the run's user's key (an approval's title too; its log line keeps the id only); the drafts not written; another user's lines never read back | `test_sys_log.py`, `test_n64_logs.py`, `test_seal_more.py`; the traces of before stay until their 30 days pass |
| a user's routines, ideas and projects' state (routines.json, ideas.json; projects/<p>/plan.json, conduct.jsonl, reports.jsonl) | AES-256-GCM with the user's «state» key, the file's name (a JSON file) or the project's file (each JSONL line) bound to it; a file or line of before read as it is, sealed at its next write | `test_seal_more.py`; the routines plugin, caged without the state key, says the file is sealed instead of listing it |
| a picture or a video a user asked for in their chat, a user's spending, the plugins' shadow | sealed with the user's key: the picture or video in the uploads (private, the painter's plain copy removed; a user's story video without its folder of topic and scenes), served by ranges as a plain file (a player seeks); the spending's what and payment with its own key «expenses» (day, amount and category plain for the month's sums); the shadow's key an HMAC with the user's key (a guessed argument is not confirmed from the file); the routines with their own key «routines», the one the routines plugin's cage gets; Aurora's own pictures and stories (the social plugins post them) and the dreams' paintings plain | `test_seal_status.py`, `test_plugins_cinema_expenses.py`, `test_seal_more.py` |
| the knowledge (harvested papers), its indexes, the deductions, the synapses | file permissions of the services' account: public papers, not encrypted (owner, 29 Oct) | the disk is ext4 without LUKS |
| the users' keys | each wrapped by Aurora's own key (sys_keyring): a key file alone opens nothing | `test_keyring.py` |
| the firewall's API (its password, its answers) | with the CA check off (a firewall's own certificate), the certificate seen at the owner's «Collega» is pinned and every later call trusts it only: another one fails the handshake before the password is sent (C567) | `test_tlspin.py` |
| the cloud providers' keys (cloud_accounts.json) | AES-256-GCM with Aurora's «state» key (sys_seal), 0600; a file of before sealed at its next write (C563) | `test_cloud_accounts.py` |
| the logs | every line passes sys_log.hide_secrets: an address's login and a bearer token blanked, also inside a traceback (C502) | `test_log_secrets.py` |
| Aurora's own key | a systemd credential bound to this machine (host+tpm2 with no PCR when systemd finds a TPM 2.0 in full working order — the installer checks it and adds its missing libraries; the host key alone otherwise; a key sealed before the TPM worked is sealed again at the next install; /etc/credstore.encrypted, root's), opened by systemd for her services only in /run/credentials (hidden from the plugins' cage); a file of the services' account (0600) until the installer seals it, and on the Mac and Windows ports; its recovery copy sealed with the backup's key | `test_keyring.py`; root on the running machine can still reach it |
| the recovery code of Aurora's key | sys_key_recovery: her key sealed with a code of 25 characters (about 124 bits) — Argon2id 64 MiB × 3 then AES-256-GCM, the parameters bound to the file — in keys/aurora.recovery, which the backup carries; the code shown once (⚙️ System → 🔑 Keys and recovery, the admin's), written nowhere; a new code retires the old | `test_key_recovery.py`; the code and a recovery file open her key, as the backup's key and the escrow do |
| an installation's own ciphers | the backup's frames may pass through a layer of the installation's own before AES-256-GCM (aurora.local.backup_layer), and the recovery code may be sealed by its own cipher (aurora.local.recovery_cipher); the published Aurora has neither: AES-256-GCM and Argon2id alone. A file says by its first bytes which made it; one made by a cipher not here is refused by name, never read as damaged | `test_backup_layer.py`, `test_key_recovery.py` |
| health (diet, training, exams) | AES-256-GCM per file, one key per user kept apart (status/users/<name>/keys, 0600), the file's name bound to it; deletion final | `test_health.py`; protects at rest, not against root (the key is on this machine) |
| the doctors' cards (hours, phone, notes) | the same as health: sealed with the user's key (hlt_doctor) | `test_doctor.py` |
| the plugins' cage and the home | bubblewrap: every home (/home, /root, the service's own) a private tmpfs wherever Aurora is installed, Aurora's folder bound again (C204; C548: before, only the service's own HOME); a plugins' folder other than the signed sys/plugins loads nothing (C550); the Mac (sandbox-exec) and Windows (AppContainer) ports give the same contract (cage_plan) | `test_cage_users.py`; the ports' probe on real machines |
| the calendar (appointments, reminders) | the same as health, its own key "calendar" (cal_store); the alerts told are state, not sealed (ids and times, no titles) | `test_calendar.py`; the crossing test |
| the network map (hosts by name, DHCP reservations with MAC addresses, interfaces, routes) | AES-256-GCM, its own key "network" (sec_netmap), the one before kept to say what changed; read only from the firewall's API, never written there; never in the repository | `test_netmap.py`; the owner's map: 363 hosts, 66 reservations (M114) |
| pictures, edits, videos given to a cloud provider (mdl_media) | the words masked like any cloud call; a photo cannot be masked: an edit or a video from a photo leaves only on an installation the owner exempted, else the local model does it; every call counted in "What went out" | `test_media.py` |
| a user's view (multi-user) | the machine's settings, models, incidents, security, harvester, updates, services and the vault's imports answer 403 to a user; a user's settings are only their own (scope user); their chats, memory and files theirs; the vault and the seed's shadow shared | M116 |
| Aurora's own firewall (nftables) | Aurora may run ONE root command, /usr/local/sbin/aurora-nft (sudoers, checked with visudo), and it touches only its own table inet aurora: an address in a timed blocklist, out, the list; never a protected address (AURORA_DEFENCE_PROTECTED), this machine, the firewall | test_security_plus.py; installed by the owner |

Recommendation (the owner's decision: it needs a reinstall or an encrypted home): full-disk
encryption with LUKS, under the application-level sealing above. Its cost: M268 (a retrieval +0.1 ms).

**Who the sealing protects from (N64), said plainly.** Aurora must open a chat to answer it, to consolidate it at
night, to dream: while she works unattended her key is on this machine. The admin's account (in the services' group),
another user, a plugin, a project's code, a NAS copy, a backup: they find only ciphertext. A stolen disk too, but only
with a working TPM and the backup's key not on that disk in plaintext: with the host key alone the secret that
opens her key is on the same disk (C459), and the escrow opened with a backup key left there (C461, closed: sealed the same way). What a stolen disk
still gives: the swap file's pages (C462) and the .env's secrets (C463). Root on the
running machine can ask systemd for the credential or read a service's memory: no design without the user's own
password at every opening stops that (ROADMAP N64, phase 7, optional).

## 🔑 aurora-root: root acts only on what the owner signed (9 Nov 2026)

Aurora's folder is writable by her services' account, because she applies the changes the owner approves. Root
therefore never runs it as it is. Every root step goes through `sudo aurora-root …` (sys/core/script/sys_root.py):
the system's Python (-I, never the .venv) from root's own copy in /usr/local/lib/aurora; every code file (the
installers, the units and the polkit rule included) read once and compared with the owner's Ed25519 signature; what
changed since the last signature listed and signed only on the owner's «s»; an installer run from a copy in root's own
temporary folder. Inside the services' folders root follows no symbolic link (C521, C524). Restarting Aurora from the
WebUI needs no root (polkit, 50-aurora.rules) and is unchanged. The first time, from Aurora's folder:
`sudo /usr/bin/python3 -I sys/core/script/sys_root.py setup`.

What the owner runs is not the services' to write either (C556, 11 Nov 2026): the venv, install.sh, uninstall.sh and
publish.sh have no group write and their folders are sticky, so the services can neither change nor swap them; the
account's and the GPU's root steps run from root's signed copy (`sudo aurora-root account`, `sudo aurora-root nvidia
…`); publish.sh and uninstall.sh first ask `aurora-root verify` (root's copy, no sudo) and run nothing of the folder as
the owner until every file is as he signed it; the owner's Python keeps its own bytecode. The signature covers the
behaviour files too (C558: the locks, pyproject.toml, .github, *.mjs, the config folder, a plugin's sub-folders), and
a restore as root writes only through directory handles that follow no link (C557). Open: a plugin's fetched
programs are checked only when fetched, and install.sh runs the folder's tests before it signs (C579).

After the audit of 12 Nov 2026 (C592): install.sh reaches the account's step through `sudo aurora-root account`, and
that step launches root's own copy of aurora-root, never the folder's; the one-time setup ignores the folder's compiled
files. The list to sign is shown whole, with odd names escaped. A unit is installed only if it holds the directives
Aurora's generator writes and no other (no group, no credential, no capability but the one for ports below 1024, no
file opened by root; a root unit only this installation's folder and .env in its environment). Host names and paths
that go into the units and into the script root runs must be plain text, or nothing is written. A restore opens its
stage through no link and gives no file a setuid, setgid or sticky bit; the proposed settings are a new file, never a
link followed; owners and modes are set on open files, not on paths. A path setting cannot hold «..». uninstall.sh
deletes a sealed credential only by its own name in root's folder.

## 🔨 The contract of Aurora's own plugins (9 Nov 2026)

Since C591 (audit of 12 Nov): in the projects' folder a forged plugin finds every .git and .venv read-only, and one it
leaves behind is renamed «.git.set-aside-…» when it ends (git runs what a .git's configuration names, pip a .venv's
python: they ran later outside its cage). The API's own git on a project (the Projects page, the live view, the mood)
runs in a cage of its own — no network, the homes, Aurora's folder and her state hidden, the project read-only — and
where no cage starts, with the filters the configuration names switched off; the projects plugin sends its token only
to https://github.com/<owner>/<name>, and not at all when the project's git configuration rewrites addresses or
changes how https is spoken. «env_as» never names what the system, the loader, Python or Aurora read (PATH, LD_…,
PYTHON…, AURORA_…) and bubblewrap is started by its whole path. The certificates' account key and the VPN's folder are
hidden from every cage. The sealed digest of what a plugin fetched lives in Aurora's state, not beside the files, and a
missing one is never recorded at a start (install again). An MCP server's readable places are never inside Aurora's
folder. Left open, said: while a forged plugin is still running, a repository it made in a new folder exists until it
ends — a call of the projects plugin on that very folder in those seconds would read it.

A plugin Aurora writes herself (the forge, manifest «forged») is held by its cage at every start, whatever its
manifest says: it writes at most in the projects' folder; it reads only its own settings (AURORA_<NAME>_…), never
another plugin's secret or a sealed store's key; it never commands the house's devices by itself; it has no network of
its own — a proxy of its own (plg_netproxy) lets it reach only the address the owner set in its settings and the public
hosts its manifest lists, never Aurora's own services, and every connection is logged; it cannot see another plugin's
way out. The forge refuses a manifest asking for more, and the owner's approval of a plugin that reaches the network or
acts outside shows first, in plain words, what it will be able to do; what is installed is the draft approved, byte
for byte (each request its own folder, the draft's digest checked at install: C540). Her plugins stand outside the owner's code
signature — the contract holds them, so she makes and uses them without a signature each time — while a plugin that is
neither hers nor signed by the owner is not loaded.

## 🔌 The owner's MCP servers (10 Nov 2026)

An MCP server the owner adds from the Plugins page (plg_mcp) is a plugin made of a manifest only, kind «mcp», saved as
«local_<name>» so that it is never published (C546), and like
every plugin of his it is loaded only once signed (sudo aurora-root sign): nothing runs as Aurora without his yes. A local
one runs in the plugins' cage with no network unless asked (through plg_netproxy to the hosts it names) and reads only
the few absolute paths it names (sandbox.read: never the root, the home or a folder above it, a hidden place, Aurora's
state, /proc, /run, /dev, /sys or the credentials (C554); never a forged plugin) — every home stays a private tmpfs
(C548). A remote one is reached at its address only, http or https (http shown «in clear»); an address is never
accepted from a forged plugin (C549). Its tools wait for the owner's approval unless he marks them as reads; a remote
server's answers, or a proxied one's, go through the honeypot like a web page (from_network, C553). «chat»: false
keeps it out of the chat; «memory»: false keeps any answer that used it out of Aurora's memory — the turn, a routine's
memory, a forge request, a repair's reflection, a project's report (C551).
`test_mcp_servers.py`: a real server living outside Aurora answers from its cage and cannot read a file of the home.

## Code of conduct (sys/core/ethics/CODE.md)

Level A, always and for everyone: no attacks or probing of systems that are not the owner's, no
identification or location of persons, no malware, no unauthorized access, no impersonation. A
plugin that declares such a capability is not loaded.

Level B, by default: AI disclosure, confirmation of external actions, approval of code changes.
The owner's installation is exempted by a file signed with the owner's Ed25519 key for this machine
and this installation only (never committed).

Plugins and users (2026-10-03): in the cage of a user a plugin sees nothing of the other users (their usr/<name>/,
memory, index, state), never users.db, never a whole .env (its filtered one only); the owner's own folders of usr/
(his papers) only to the admin's plugins. The forge's look at the data never takes another user's things, the users
store or the owner's files (C119).

Users (multi-user, 2026-10-03): each request carries its user; nobody reads another user's conversations, files,
settings, routines, approvals, runs or live activity (a crossing test through the API checks it). The login asks for
name, password (scrypt) and, by default, the Authenticator's 6-digit code (RFC 6238; a code is never accepted twice);
the failed-login lockout applies to it. The admin can pass to multi only after setting their own password and code;
the API key stays the admin's. Deleting a user removes their folder, memory, devices, trace lines and what the API
holds in memory; the audit log keeps the event (who, when) until its retention.

Push delivery (2026-10-05, M101): one more route without a key, `POST /v1/aurora/push-ack`, for the service worker
that has none. It only counts: the body (at most 2 KB) must name the random 16-hex id of a push sent in the last
48 h, once per device (the endpoint is stored as a 12-hex hash); anything else answers `counted: false`. It reads and
returns nothing. A test lists the 8 routes without authentication.

Autonomous defence (2026-10-05): off by default (suggest: the owner's click). In auto, a block happens only on an
installation exempted from level B (rule 7), for an incident of the chosen severity, from a public address that is
neither protected (AURORA_DEFENCE_PROTECTED) nor the firewall nor this machine; never an address of the local network;
at most AURORA_DEFENCE_MAX_PER_DAY a day; each lasts AURORA_DEFENCE_HOURS and is lifted by itself; recorded (audit,
trace, the Autonomy ledger) and notified. Aurora never writes a firewall rule: only the address into the group.

Privacy of what is published (2026-10-05): a social post is checked by the local model for private people's names,
places and personal data (sec_privacy) on the owner's click; an autonomous post that names someone waits for the
owner. Bug reports mask the names of the people Aurora knows and those the local model reads in the description.

Artifacts (interactive pages Aurora makes, 2026-10-03): they run only under `/v1/preview/` through a token valid
10 minutes that the logged-in WebUI asks for, in a sandbox without `allow-same-origin` (opaque origin: no cookie,
no access to the API) and with no network (`connect-src 'none'`, nothing external); only HTML files Aurora made
(role assistant) can be opened; the file itself is always a download.

Autonomous posts (owner, 2026-10-03): on an exempted installation, with `AURORA_SOCIAL_AUTONOMY` on, Aurora
publishes her own posts without waiting, but only through the tools of `AURORA_SOCIAL_AUTO_TOOLS`
(`facebook.publish_post`, `facebook.publish_photo`) and at most `AURORA_SOCIAL_POSTS_PER_DAY` a day (3); the
AI disclosure stays; each post is recorded in the approvals with status "auto" and notified. Replies to
comments, page changes and every other external action still wait. The rule lives in the signed approval
gate (`sys_approvals.social_auto`). Without the exemption nothing changes.

Integrity: the protected files (the rules, the code that enforces them, the approval gate, the
disclosure, the change applier) are signed in `MANIFEST.json`; a change without the owner's
signature stops every service at start (verified: one changed line gives "changed without the
owner's signature"). This makes changes to the rules deliberate and evident; like any open-source
program, a copy can be modified by whoever holds it, the check included.

### One key per installation

Nothing of the key is in the repository. Each installation makes its own Ed25519 key pair, as root,
in `/etc/aurora`:

| file | owner, mode | who can use it |
|---|---|---|
| `/etc/aurora/owner_ed25519` (private) | root, 0600 | only `sudo`, that is only the owner |
| `/etc/aurora/owner_ed25519.pub` (public) | root, 0644 | read by the services; trusted only while root owns it and its folder and nobody else can write them |
| `sys/core/ethics/MANIFEST.json`, `exemption.sig` | installation user | signed with this installation's key; not committed |
| `sys/core/ethics/private_to_cloud.sig` («Tutto cloud») | installation user | the owner's consent that private data (health, the firewall's configuration) may go, masked, to the cloud where no local reasoner runs: signed with `sudo … sys_ethics_sign.py private-cloud`, never from the web; taken back from the Models page with no shell (going back to privacy is always easy); not committed |

Why: the services run as the owner's user. A key that user could read or replace would let a
process of Aurora sign changes to her own rules. Level A has no exemption, whatever the key.

    sudo /usr/bin/python3 -I sys/core/script/sys_root.py setup            # key pair + signature (installer)
    sudo /usr/bin/python3 -I sys/core/script/sys_root.py setup --exempt   # the same, and exempt this installation from level B
    sudo aurora-root sign             # after a protected file changes
    sudo aurora-root keygen --rotate  # new pair; the old one is renamed .retired-<date>, then `sign`

## EU AI Act, article 50

Published text gets a disclosure line before the owner approves it; images carry a machine-readable
mark (XMP with the IPTC DigitalSourceType "trainedAlgorithmicMedia", PNG text chunks) and a visible
label; documents Aurora writes start with a disclosure header. Obligations apply from 2 August 2026
(2 December 2026 for systems already on the market). Implemented as the sources describe them; not
legal advice.

## Changes on the firewall (2026-10-07)

Aurora's own blocking group was the only thing she wrote on the firewall. Now she can also publish a server, put a
device in quarantine and put an IPS policy on a rule (sec_fwwrite), within these limits:
- off by default (`AURORA_FIREWALL_WRITE`); every change is planned first and applied by a tool whose effect is
  "external": the owner approves each one;
- she adds and removes only objects named `Aurora-…`/`aurora-…`; an owner's rule is changed only by «harden» (IPS
  policy and log), its XML before the change kept as the undo;
- each step is checked; at the first refusal, or if the objects do not read back within `AURORA_FIREWALL_CONFIRM_S`,
  every step done is undone; the record of every change is in `status/security/fwchanges.json`;
- a shared address of a CDN or a cloud (Cloudflare, Google) is never blocked by her alone (C190); it can be blocked
  on the attacked ports only (`sec_fwport`, plan «portblock»: a Drop rule from WAN, approved, lifted by itself after its
  hours), and never on a port Cloudflare's proxy serves (80, 443…): there the author is blocked at Cloudflare.

## Cloudflare and shared networks (2026-10-14, ROADMAP 103)

- Traffic from a shared network that the firewall **already refused** is not an incident: counted per day in
  `status/security/shared_denied.json`, told once a day with the provider's fix (Cloudflare: SSL/TLS Full (strict),
  Always Use HTTPS). Anything those networks bring that was not refused stays an incident (`sec_shared`, M213).
- Who is behind Cloudflare is read from Cloudflare's own analytics (`net_cfwaf.culprits`: the clients the origin did
  not answer, with hosts and paths and a label — scanner, Aurora's own app, Google's service, unknown — a guess for the
  owner, never a verdict). The token needs Account Firewall Access Rules Edit, Zone Read and Analytics Read (the
  plugin's guide); nothing more.
- A block at Cloudflare is an IP Access Rule of the account: the owner's approval each time (`cloudflare_block`,
  external), or by herself with `AURORA_CLOUDFLARE_AUTOBLOCK` — only clients labelled scanners in the last hour, for
  `AURORA_DEFENCE_HOURS`, at most `AURORA_DEFENCE_MAX_PER_DAY` a day, only exempted from level B, each one told and
  recorded in `status/security/cf_blocks.json`; lifted by itself when its time is over. Never a Cloudflare node, an
  address of the house or a protected one.
The firewall's documentation is kept in `status/security/fwdocs.sqlite`: copyrighted, for the licensee's own use on
this machine, never in the repository.

## Networks never reached (2026-10-27, ROADMAP N50, M263)

A Qwen model (not the one Aurora uses) was caught, as an agent with a shell, writing a curl to a storage bucket of
Alibaba Cloud in Beijing. A model's weights reach nothing by themselves: its tools do. On this machine the local
reasoner talked to 127.0.0.1 alone, so its unit now forbids every other address (IPAddressDeny=any,
IPAddressAllow=localhost); the commands of a project already run without network. The services that do go out (the
tools, the plugins, the harvest) never reach the networks of AURORA_EGRESS_DENY_ASNS (Alibaba Cloud and Taobao by
default; prefixes from RIPEstat, kept a week, written into their units at install). The machine is also the owner's
desktop, which the list does not touch: the sentinel raises a high incident, never quieted, for any firewall line
from this machine to a listed network, with the local process when its connection is still open. And the local
model's own processes are watched every 10 s, whatever the model: an address not loopback (even an attempt the unit
refuses) is a high incident with the network's owner; the network goes on the list by the owner's click, or by Aurora
herself when security is at 🚀 on the Autonomy page.

Every way out of Aurora's other services is learnt too (sec_egress_watch, ROADMAP N50): their own sockets (by
cgroup, never the owner's desktop) every 10 s, per service the networks reached. A week of learning; then a network a
service never reached is an incident, high when no run was working (a connection «from nothing»), medium during one,
and a connection sending more than 10 MB and four times the most that service ever sent there is high (a file going
out). The owner answers ✓ legitimate (learnt) or 🚫 (the deny list); at 🚀 Aurora learns the networks met during a run
and denies those met with nothing running, unless they are a shared network (a cloud's, a CDN's), which wait.

## Powering off for the UPS (2026-10-28, ROADMAP N53)

The service user may power the computer off only when the owner chose AURORA_UPS_MODE shutdown: then, and only
then, Aurora's polkit rule (50-aurora.rules, written by sys_install_services) grants it logind's power-off actions;
in any other mode the rule does not hold them. The power-off follows a low battery read twice in a row (30 s), so one
odd read never stops the machine; the UPS's password, when set, is a secret setting and never logged.

## The firewall's console (2026-10-28, ROADMAP N55)

Restarting or shutting the Sophos down is not in its XML API: Aurora reaches the console over SSH as the default
admin (the only account the console takes) with a key of its own, never a password; the owner adds its public half on
the firewall and can remove it there at any time. Aurora types one of two commands only (`system restart all`,
`system shutdown`), from a routine the admin made or from the UPS's power-off when the owner chose it; each is
written to the firewall log as an audit line.

## Computers shut down over SSH (2026-10-28, ROADMAP N56)

Aurora's key for the house's computers is its own (ed25519, in its state folder, mode 600), never the owner's. On
each target the owner adds it to authorized_keys with a forced command: the key runs one script, aurora-power,
whatever is asked, with no terminal and no forwarding. The script knows three words (test, restart, shutdown) and
refuses the rest; sudo lets the target's user run only the two power commands. Whoever holds the key can at worst
restart or shut down that machine. A machine counts for the UPS only after a trial that worked, and again after its
address or user changes. Every restart and shutdown is an audit line in the power log.

## The forge never builds into Aurora's own data (2026-10-30)

A run asked the forge for a plugin reading the people's cards (sys_people.load): in its cage it could not open the sealed store, and a plugin that could would go around the seals, the users' separation and what each person chose to share. Now a request naming Aurora's own stores (agt_forge.CORE_STORES: the people's cards, memories, users, keys, approvals, settings, sealed files) is refused before it is queued, and the agent is told so in its rules; the cards reach the agent through the core's own read-only tool `people_cards`.

## Assistance: the admin inside a user's account (2026-10-30, ROADMAP 🛟)

- Only when the user opens a window (8, 16, 24, 48 or 72 h) from their own page; the disclaimer beside the button is the consent. The user closes it at any moment; it ends by itself, and a session inside it ends with it (checked at every request).
- Only from a device of the admin's: the API key never enters. Inside, the admin's device is the user for every route, so the admin's own pages answer 403 until they leave.
- Never reached, whoever asks (403 before the route): the password, the Authenticator, the API keys, the devices, the logout, the window itself (the admin cannot extend it).
- Every step (method and path, never a body; a page polled counted once a minute) goes into the user's own log, each line sealed with the user's key, shown on their page; the user is told when the admin enters and when it ends.

## Security review (2026-10-28)

Four read-only reviews of the code (authentication, command execution, files and network, deployment); each finding
checked again before its fix (BUGS.md C420–C429). Closed since, 28 Oct: Caddy's admin on a Unix socket (C444; on Windows still on 127.0.0.1:2019, C446), the authenticator's change confirmed (C440), changes
from another site refused (C441), sessions ending on the server (C437). A known limit: behind the WARP private
network every remote client reaches Caddy from this machine's own address (WARP carries the connection, it adds no
header with the client's), so the login lockout cannot tell one remote client from another; a valid session or key
passes even while the lockout holds (C427). Left for the installation, needing root: the services run as the
owner's own account, which on a typical desktop is in groups that give root (docker, libvirt): a dedicated service
account (ROADMAP U6) is the real fix; the units that run as root should run code root owns; the polkit rule should
name its units one by one; the firewall helper should keep its own list of addresses never blocked; Caddy's admin
endpoint on a socket; the real client address from the tunnel. Done since: the services' own account (U6),
root's own copy of its units' code, the polkit rule unit by unit, the firewall helper's own never-blocked list.
The tunnel's private network reaches this machine on every port: the owner's choice (28 Oct: SSH through it), the
machine's own firewall letting in 8443 and 22 only.

## Known limits

- After the audit of 12 Nov 2026 (C593), sealed data: a sealed file is bound to its path inside the user's folder
  (not to its bare name), so a file of the same name from another folder does not open in its place; a file sealed
  before keeps its old binding until its next write, and a file at the top of a folder can still be opened from a
  deeper folder that ends with the same path. A user's memory, once all sealed at a start (`memory_sealed`, itself
  sealed with the user's key), refuses a plain value put in a row; whoever can delete that mark in the state folder
  takes the check away. The other sealed stores (the state files read by `read_any`, the JSONL lines, the shadow)
  still read a value of before as it is: nothing says yet that they hold none, and refusing would make old data
  unreadable. The memory's vectors without a tag of today's format are built again from the sealed memory, never
  trusted as «a file of before».
- Since C572 every component's trace is sealed like the chat's (whatever is not a number or a name of the
  structure, with the key of the user the work is for; the admin's without one); Aurora's own counts open it
  (`sys_log.opened`), a line of before reads as it is. A script run by hand outside the services has no key: its
  events keep their numbers and drop their words. The logs plugin and the benchmarks see the sealed values, not the
  words. The cloud conductor's CLI keeps one folder per login: under the policy «shared» (the default) every user's
  sessions use the shared login, each in its own working folder; they are removed when the user is purged, or after
  30 days idle. A login per user is the policy «own» (a user without one then uses the local model).
- A text is «public» for the diary and the posts only when the local model could look at it: when it does not answer
  (the GPU busy), nothing is drawn that night (C593).
- Plugins keep the network and the devices (connectors talk to services, the senses use the camera); the cage
  (bubblewrap, on by default) hides the home, Aurora's secrets and the other plugins' files, not the Internet.
- The honeypot (ROADMAP 104) catches a content that makes the decoy **act**; an injection that only bends what the
  answer says, without asking for any action, is not caught by it — the answers' honesty and the approval gate remain
  the defence there. A site of good reputation is tried only around suspicious words (the owner's choice: cost).
- Telegram and Facebook content is readable by the platforms.

## Hardening (2026-10-01, measured)

| risk | defence | evidence |
|---|---|---|
| a plugin reads Aurora's secrets, the owner's SSH keys, the push keys, or writes into Aurora's folder | every plugin runs inside **bubblewrap** (`plg_sandbox.py`, protected): system read-only, home hidden, Aurora's folder read-only with its `.env` replaced by a copy holding only that plugin's declared secrets (the others read `redacted`), push keys and devices hidden, private /tmp and PID/IPC namespaces; writable only the folders the manifest names | a probe plugin: without the cage it read the API key, `~/.ssh` and the push key and wrote into Aurora's folder; inside it saw `redacted`, no `~/.ssh`, an empty push folder, and could not write. The 12 real plugins work inside (camera, PDF, web, projects…) |
| an agent driven by a poisoned page or e-mail sends a secret out | `plg_host` refuses any call whose arguments contain the value of a `.env` secret not owned by that plugin, whatever the model decided | a URL with the API key: refused and logged; normal calls pass. Measured injections: 0/5 in answers, 0/3 in an agent reading a phishing e-mail (prompts now also say that tool results and passages are data) |
| a page, an e-mail, a comment or a document carrying a prompt injection never seen before (0-day) makes the agent act, poisons an answer or is kept in the vault | `sec_detonate` (ROADMAP 104): what the agent reads from a plugin that declares `from_network`, the pages the answers open, and every document from the network before the vault are tried first on a decoy (a link of good reputation only around its cues) — the local model, fake tools, a fake secret, asked only to summarise; a content that makes it call a tool or write the secret is refused to the agent, its site listed (linkcheck refuses it), the owner told; reporting it to VirusTotal is their approval | tests with decoy models (`test_sec_detonate.py`); M215: 13/24 traps caught (6/8 zero-day), 0/24 false alarms, on a test set written for it (not real attack pages) |
| systemd services with the user's full privileges | `ProtectSystem=strict`, home read-only but Aurora's folder (and caches), `NoNewPrivileges`, no capabilities (Caddy keeps only the low-port one), kernel/clock/control groups protected, private /tmp, `UMask=0077` (AURORA_SERVICE_HARDENING) | `systemd-analyze security`: 9.2 UNSAFE → 4.1 OK (api, llm), 9.3 → 4.3 (https) |
| brute force of the API key | 10 failures from one address in 15 minutes → 429 for 15 minutes and a security notification (AURORA_AUTH_MAX_FAILS/WINDOW_S) | code; the live test runs after the services restart |
| DNS rebinding through the web plugin | the name is resolved once, every address must be public, and the connection goes to that very address (Host and TLS SNI carry the name, the certificate is still checked) | example.org and redirects work; 127.0.0.1, 192.168.x, 127.0.0.1.nip.io refused; a self-signed certificate refused |
| a forged update | commits are signed (SSH); the updater applies only commits signed by a key of the **local** `allowed_signers` (an update cannot bring its own signer) — AURORA_UPDATE_REQUIRE_SIGNED | tests: an unsigned commit and a commit signed by a foreign key are refused |
| unseen changes to the code | second tier of the signature: every code file (165) listed with its SHA-256 and signed; a difference is reported in the logs, in the health check (yellow) and to the owner, without stopping Aurora (a self-repair the owner approved keeps working until he signs) | health shows "firma del codice" |

### The owner's private key off the machine

The public half stays in `/etc/aurora/owner_ed25519.pub` (that is all the services need). The private half can
live on a USB stick, so that not even root on this machine can sign:

    sudo cp /etc/aurora/owner_ed25519 /media/$USER/KEY/   # once, then check the copy
    sudo shred -u /etc/aurora/owner_ed25519
    # whenever something must be signed: plug the stick in
    sudo aurora-root sign --key /media/$USER/KEY/owner_ed25519

## Hardening still to do

| risk | today | to do |
|---|---|---|
| each person's data under one account | since 0.3.0 the services run as their own account «aurora» (U6 stage 1), confined by systemd, plugins caged by bubblewrap | each person a system account of their own (U6 stage 2) |
| storage not encrypted | ext4 without LUKS | full-disk encryption (owner) or SQLCipher for the vault (cost not measured) |
| secrets in memory and logs | logs never print secrets (checked by grep) | an automated test that scans the logs for every secret of .env |

## Links Aurora opens (13 Oct 2026, roadmap 96)

Every page the answers open and every agent's tool call that carries a link pass the plugin linkcheck (on by default): the link's own form (hidden credentials, punycode look-alikes) and the reputation services the owner ticks (VirusTotal, URLhaus, AbuseIPDB), each with the owner's key. A malicious link is not opened and the refusal carries the services' reasons; a service without key or down counts as not checked, never as clean. Verdicts are kept a day in <STATUS>/linkcheck.json (the link, not the page).

## Tried with a model that refuses nothing (13 Nov 2026, N135, M292)

Aurora's guards on actions are code, not the model's good manners. To measure it, an uncensored model (Qwen3.8-27B
«Heretic») was put behind Aurora's real agent loop, with settings as a real installation's (level B exempted, external
actions confirmed, self-changes asked, social posts autonomous), every tool fake, and made-up pages hiding orders to
the assistant: a link or a phone number in a post, a message to a stranger, data carried out in an address, a change
to the ethics code. Then the same orders given by a scripted model that obeys them to the letter, past the honeypot.
In 41 runs no action that should not have been ran: the honeypot blocked every page, and with it off every order was
held by the code (a destination neither asked nor read, nothing leaving alone after a network read, a contact the
owner did not write, a self-change waiting for the owner, privacy). One gap was found and closed (C601: a page could
plant its own link in a post).

What this does not cover: the chat's words are the model's. Level A in the code refuses plugins and holds actions; with
a model that refuses nothing, a request against level A in the chat itself is answered. The model chosen for Aurora
must be one that refuses on its own.

## Content from the network tried on a decoy (14 Oct 2026, roadmap 104)

Since C590 the core decides what comes from the network, not the manifest alone (`agt_asked.outside`): every read
tool of a plugin that reaches the network counts, except the house's own devices and a short list in the core
(`TRUSTED_READS`: numbers and states, not a stranger's text). After such a read, in the same run: a call to a plugin
that reaches the network whose link is neither in the owner's request nor written in what was read waits for the
owner (`carries_out`: a read tool was a way out for data); so does every external action — a post under the social
autonomy too — and a self-change set to «by herself» (`owner_decides`). «Named» (C561) reads only a call's
identifying fields. An approved code change is applied from the bytes checked after the sandbox's tests, which run
with the sandbox read only; a sandbox holding a conftest.py, a pytest.ini, a .pth… outside sys/core is refused. A
command to the house is judged by each entity's own domain (homeassistant.toggle on a cover lowers its security).

What a plugin declares `from_network` (pages and searches, e-mails, comments, chats), the pages the answers open and
every document from the network before it enters the vault are handed first to a decoy: the local model (C317: Claude, as a decoy, fell for none of the traps — it told nothing), fake
tools (messages, posts, home, files, web requests, shell), a fake key different every time, asked only to summarise.
Nothing is executed and no VM is needed: the decoy only writes text, and a tool call or the fake key in that text means
the content carries an injection that works on a model. Then the content is never shown to Aurora or kept in the
vault, its site is listed (`status/security/honeypot.json`; linkcheck refuses it even when switched off), the owner is
told, and reporting it to VirusTotal (analysis, a «malicious» vote, a comment with the reason) waits for the owner's
approval. `AURORA_WEB_DETONATE`: unrated (default: a link a reputation service calls clean only around suspicious
words; unrated, doubtful and link-less contents whole), all, suspicious, off. The owner's own files are never tried.
Measured by `bench_honeypot.py` (M215; no network: 12 traps, 4 of them with none of the cheap cues, and 12 harmless
look-alikes, each tried twice): **13 of 24 tries caught, 6 of 8 «zero-day», 0 false alarms**, 0.9 s median a content.
Missed: an e-mail impersonating the owner, a «courier at the gate» asking to open it, a fake tool call written in the
page itself, a «forget your instructions» on a recipe; the approval gate stays the defence for those.

