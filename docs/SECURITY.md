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

Not end-to-end encrypted by the platforms themselves: Telegram bot chats and Facebook posts are
encrypted to the platform (HTTPS) but readable by it; that is how those platforms work.

## At rest

| data | protection | state |
|---|---|---|
| `.env` and `.env.proposed` (keys, tokens) | mode 0600, kept at every write and restored at every start | was 0644 until 2026-09-30 (C30) |
| device tokens, approvals, TLS private key | 0600 | measured |
| knowledge and memory stores, logs, traces | file permissions of the service user | **not encrypted**: the disk is ext4 without LUKS |

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

## Hardening still to do (2026-10-01)

| risk | today | to do |
|---|---|---|
| plugins and services run as the owner's user | a plugin could read the configuration file itself | a dedicated system user for Aurora; plugins in a sandbox (systemd DynamicUser, bubblewrap or containers) with only their own secrets |
| systemd units with no confinement | full user privileges | ProtectSystem=strict, ProtectHome, PrivateTmp, NoNewPrivileges, CapabilityBoundingSet=, RestrictAddressFamilies, MemoryMax per service |
| storage not encrypted | ext4 without LUKS | full-disk encryption (owner) or SQLCipher for the vault (cost not measured) |
| supply chain | requirements pinned by version | pinned by hash (`pip install --require-hashes`), llama.cpp by commit (done), models by revision + SHA-256 (done), Dependabot/OSV scan on the repository |
| releases | git commits only | signed tags and releases (the owner's key), the updater accepting only signed commits |
| WebUI sessions | device cookie, HttpOnly, SameSite=Strict | rate limit and lockout on the API key login, session expiry shown and revocable (revocation exists) |
| DNS rebinding in the web plugin | not closed | pin the resolved address for the connection |
| secrets in memory and logs | logs never print secrets (checked by grep) | an automated test that scans the logs for every secret of .env |
| tampering with the code of conduct | signed manifest of 6 files, key in /etc/aurora | sign the whole code base (not only the 6 files) and check it at start; keep the private key offline (not on the machine) |
| prompt injection from web pages, papers, plugin results | answers are verified against passages; actions need approval | mark untrusted text in prompts, never let it set tool arguments without the owner (partly done by the approval gate) |
