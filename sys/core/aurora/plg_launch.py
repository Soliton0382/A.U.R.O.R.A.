# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Start a plugin's cage with its secrets in a file inside the cage, never in an environment (C672).

plg_host gives this launcher, outside the cage, the plugin's own secrets as AURORA_PLUGIN_SECRET_<KEY> variables and
the cage's command line (plg_sandbox.wrap). The launcher takes them out of the environment, writes them into a pipe and
replaces itself with bubblewrap: bubblewrap copies the pipe into a file inside the cage (--bind-data, nothing on the
disk) and the plugin reads it once (sys_config.plugin_secret), then empties it. Before C672 the values stayed in
bubblewrap's own environment — /proc/1/environ inside the cage — where any program the plugin ran (a git filter named
by a project's configuration) could read them.

Run with `python -I`: the standard library only, nothing of Aurora imported.
"""
import json
import os
import sys

PREFIX = "AURORA_PLUGIN_SECRET_"
DEST = "/run/aurora-plugin-secrets"
MAX = 60_000                                    # a pipe holds 64 KiB before a writer blocks


def command(argv: list[str], secrets_fd: int, at: int) -> list[str]:
    """The cage's command line with the secrets' file added before «--chdir <folder> --». `at` is the index of that
    «--», given by plg_host, which built the line (C677: looking for the last «--chdir» found one in the plugin's own
    arguments, after «--», where bubblewrap never reads it)."""
    if not (2 <= at < len(argv) and argv[at] == "--" and argv[at - 2] == "--chdir"):
        raise ValueError("not a cage's command line")
    i = at - 2
    return argv[:i] + ["--bind-data", str(secrets_fd), DEST, "--setenv", "AURORA_PLUGIN_SECRETS_FILE", DEST] + argv[i:]


def main() -> None:
    argv = sys.argv[1:]
    if argv[:1] != ["--at"] or len(argv) < 3 or not argv[1].isdigit():
        sys.exit("plg_launch: --at <index of the cage's «--»> first")
    at, argv = int(argv[1]), argv[2:]
    secrets = {k[len(PREFIX):]: v for k, v in os.environ.items() if k.startswith(PREFIX)}
    env = {k: v for k, v in os.environ.items() if not k.startswith(PREFIX)}
    if secrets:
        # C677: each value as a JSON string — a key on several lines (a PEM) arrives whole, not with spaces for newlines
        data = "".join(f"{k}={json.dumps(v)}\n" for k, v in secrets.items()).encode()
        if len(data) > MAX:
            sys.exit("plg_launch: the plugin's secrets are too long for the pipe")
        r, w = os.pipe()
        os.write(w, data)
        os.close(w)
        os.set_inheritable(r, True)
        argv = command(argv, r, at)
    os.execve(argv[0], argv, env)


if __name__ == "__main__":
    main()
