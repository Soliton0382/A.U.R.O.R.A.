# Security, privacy, compliance

Measured on 2026-09-30 (not assumed). What is protected, how, and what is not yet.

## In transit

| path | protection | measured |
|---|---|---|
| browser / PWA / Chatbox → Aurora | Caddy, TLS 1.3 only (TLS 1.1 refused), owner's certificate, HSTS 1 year, CSP (self only, no inline script, no framing), X-Frame-Options DENY, nosniff, Referrer-Policy | `openssl s_client`, response headers; the WebUI runs under the CSP with 0 violations |
| WebUI authentication | registered device: random token in an HttpOnly, Secure, SameSite=Strict cookie; only its SHA-256 is stored (0600); the API key is used once and never kept by the browser | tests, headless Chrome |
| internal services (api 9700, models 9710, llm 9711, Caddy admin 2019) | bound to 127.0.0.1 only | `ss -ltn` |
| plugins | child processes on pipes (MCP over stdio), never a network port | code |
| outgoing: arXiv, Telegram, Facebook, GitHub, Mastodon, Open-Meteo, RDAP, AbuseIPDB, Brave | HTTPS only (arXiv moved from HTTP on 2026-09-30) | scan of every URL in the code |
| outgoing email | IMAP over TLS (993), SMTP over TLS (465) or STARTTLS (587): no clear-text fallback | code |
| web plugin | refuses local and private addresses, also through public DNS names that point to them | live: 192.168.x, localhost, 127.0.0.1.nip.io refused |
| firewall syslog (inbound) | UDP from the allowed addresses only (AURORA_SENTINEL_ALLOW), default 127.0.0.1 | test |
| outgoing to cloud models | **always masked** (no setting turns it off since 2026-10-05): addresses, e-mails, phones, IBANs, cards, keys and tokens, the .env's secrets, the users' names and private words, key=value fields naming people or devices; and private keys, JWTs, a password in a link, the Italian tax code, VAT, car plates, street addresses, any value said by its name (password, PIN, tax code, passport, identity card, driving licence, health card, date of birth). The owner's name is put in before masking (C132). Pictures cannot be masked (warned) | `test_mask.py`, `test_cloud.py` (every provider wrapped) |
| health data | never sent to a cloud model: the private plugin answers only to the local one | `test_health.py` |

Not end-to-end encrypted by the platforms themselves: Telegram bot chats and Facebook posts are
encrypted to the platform (HTTPS) but readable by it; that is how those platforms work.

## At rest

| data | protection | state |
|---|---|---|
| `.env` and `.env.proposed` (keys, tokens) | mode 0600, kept at every write and restored at every start | was 0644 until 2026-09-30 (C30) |
| device tokens, approvals, TLS private key | 0600 | measured |
| knowledge and memory stores, logs, traces | file permissions of the service user | **not encrypted**: the disk is ext4 without LUKS |
| health (diet, training, exams) | AES-256-GCM per file, one key per user kept apart (status/users/<name>/keys, 0600), the file's name bound to it; deletion final | `test_health.py`; protects at rest, not against root (the key is on this machine) |

Recommendation (the owner's decision: it needs a reinstall or an encrypted home): full-disk
encryption with LUKS. Application-level encryption of the stores (SQLCipher) is possible; its cost
on search speed is not measured.

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

Why: the services run as the owner's user. A key that user could read or replace would let a
process of Aurora sign changes to her own rules. Level A has no exemption, whatever the key.

    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py setup            # key pair + signature (installer)
    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py setup --exempt   # the same, and exempt this installation from level B
    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py sign             # after a protected file changes
    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py keygen --rotate  # new pair; the old one is renamed .retired-<date>, then `sign`

## EU AI Act, article 50

Published text gets a disclosure line before the owner approves it; images carry a machine-readable
mark (XMP with the IPTC DigitalSourceType "trainedAlgorithmicMedia", PNG text chunks) and a visible
label; documents Aurora writes start with a disclosure header. Obligations apply from 2 August 2026
(2 December 2026 for systems already on the market). Implemented as the sources describe them; not
legal advice.

## Known limits

- DNS rebinding between the address check and the connection (web plugin) is not closed.
- Plugins run as the same user as Aurora: "only the declared secrets" is what the host passes, not
  an isolation (a plugin could read the configuration file itself).
- Telegram and Facebook content is readable by the platforms.

## Hardening (2026-10-01, measured)

| risk | defence | evidence |
|---|---|---|
| a plugin reads Aurora's secrets, the owner's SSH keys, the push keys, or writes into Aurora's folder | every plugin runs inside **bubblewrap** (`plg_sandbox.py`, protected): system read-only, home hidden, Aurora's folder read-only with its `.env` replaced by a copy holding only that plugin's declared secrets (the others read `redacted`), push keys and devices hidden, private /tmp and PID/IPC namespaces; writable only the folders the manifest names | a probe plugin: without the cage it read the API key, `~/.ssh` and the push key and wrote into Aurora's folder; inside it saw `redacted`, no `~/.ssh`, an empty push folder, and could not write. The 12 real plugins work inside (camera, PDF, web, projects…) |
| an agent driven by a poisoned page or e-mail sends a secret out | `plg_host` refuses any call whose arguments contain the value of a `.env` secret not owned by that plugin, whatever the model decided | a URL with the API key: refused and logged; normal calls pass. Measured injections: 0/5 in answers, 0/3 in an agent reading a phishing e-mail (prompts now also say that tool results and passages are data) |
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
    sudo .venv/bin/python sys/core/script/sys_ethics_sign.py sign --key /media/$USER/KEY/owner_ed25519

## Hardening still to do

| risk | today | to do |
|---|---|---|
| services run as the owner's user | confined by systemd, plugins caged by bubblewrap | a dedicated system user for new installations (the owner's own installation keeps its user) |
| storage not encrypted | ext4 without LUKS | full-disk encryption (owner) or SQLCipher for the vault (cost not measured) |
| secrets in memory and logs | logs never print secrets (checked by grep) | an automated test that scans the logs for every secret of .env |
