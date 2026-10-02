# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository. You will get an answer, and the fix will be credited.

Useful in a report: what an attacker can do, the steps, the version (`pyproject.toml`) or commit, and whether it
needs access to the machine, to the local network, or only to the WebUI's address.

## What is protected, and how

The measured state — transport, authentication, plugins in a cage, secrets, the signed code of conduct, masking of
what goes to cloud models, backups — is in [docs/SECURITY.md](docs/SECURITY.md).

## Supported versions

Only the latest commit of `main` receives fixes.
