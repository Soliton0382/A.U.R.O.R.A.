# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Every test runs in its own temporary root with a .env built from the settings schema."""
from pathlib import Path

import pytest

from aurora import sys_config, sys_log


def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write_env(root: Path, **overrides: str) -> Path:
    schema = sys_config.load_schema()
    values = {s["key"]: s["recommended"] for s in schema["settings"]}
    values["AURORA_ROOT"] = str(root)
    # the test installation's services on ports nothing listens on: never this machine's own Aurora (C208 — the
    # suite reached the live aurora-models on 9710, so a test passed here and failed on a fresh machine, and its
    # embeddings ran on the owner's GPU)
    for key in ("AURORA_API_PORT", "AURORA_MODELS_PORT", "AURORA_LLM_PORT"):
        values[key] = str(_free_port())
    for s in schema["settings"]:
        if s.get("secret"):
            values[s["key"]] = "test-secret-" + s["key"].lower()
    # the test's own backup key, never the one in the home of whoever runs the suite (C461: the tests read the
    # owner's real key, and stopped when it was sealed)
    values["AURORA_BACKUP_KEY_FILE"] = str(root / "home" / ".config" / "aurora" / "backup.key")
    values.update(overrides)
    env = root / ".env"
    env.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return env


def _never_the_installation() -> None:
    """12 Nov: a project turn's test imported api.core, whose configuration is the process's own (sys_config.get()):
    with this installation's .env next to the code, the test searched the owner's real knowledge and memory (36
    indexes) and called the live models service — C208's class again. The process's configuration is now a test
    installation of its own for the whole session, unless the run named one (AURORA_ENV_FILE: the no-.env check)."""
    import os
    import tempfile
    if os.environ.get("AURORA_ENV_FILE"):
        return
    root = Path(tempfile.mkdtemp(prefix="aurora-tests-"))
    os.environ["AURORA_ENV_FILE"] = str(write_env(root))


_never_the_installation()


def private(path) -> bool:
    """Only its owner may read it: mode 600 here. The Mac and Windows ports ask their system (sys_platform.is_private:
    an ACL on Windows, where a file's mode says nothing of who may read it — a real Windows, 8 Oct 2026)."""
    import stat
    return stat.S_IMODE(Path(path).stat().st_mode) == 0o600


@pytest.fixture
def cfg(tmp_path: Path) -> sys_config.Config:
    config = sys_config.load(write_env(tmp_path), check_root=False)
    sys_log.configure(config)
    return config


@pytest.fixture(autouse=True)
def nothing_leaves_the_tests(monkeypatch, request):
    """No test reaches the owner's devices nor their notifications' history, and no test's trace listener outlives it (owner, 9 Oct: «continuo a
    ricevere errori fake (gate) provider giù» — a test imported the API in-process, its trace listener stayed, and
    the later tests' simulated provider failures went out as real push notifications to 6 devices)."""
    from aurora import sys_push
    sent = []
    if request.module.__name__.rsplit(".", 1)[-1] != "test_push":     # the sending itself, on the tests' own devices
        monkeypatch.setattr(sys_push, "send", lambda msg, cfg: sent.append(msg) or {"sent": 0, "failed": 0})
    # nor the owner's Notifications page (C336, 16 Oct: «fake (gate): provider down», a decoy's tool call and a cloud
    # ceiling of a test were in the owner's history: the API imported in-process kept them with its own configuration)
    monkeypatch.setattr(sys_push, "remember", lambda msg, event, channels, cfg: sent.append({"event": event, **msg}))
    # nor RIPEstat: the deny list's networks are the test's own (sec_egress)
    if request.module.__name__.rsplit(".", 1)[-1] != "test_egress":
        from aurora import sec_egress
        monkeypatch.setattr(sec_egress, "refresh", lambda cfg, fetch=None, force=False: sec_egress.load(cfg))
    listeners = list(sys_log._listeners)
    yield sent
    sys_log._listeners[:] = listeners


@pytest.fixture(autouse=True)
def _no_tls_pin_over_the_network(request, monkeypatch):
    """C567: a driver test's firewall is a stand-in; learning its certificate would reach the network. A test of the
    pinning itself asks for the real one (the fixture «real_tls»)."""
    if "real_tls" in request.fixturenames:
        yield
        return
    from aurora import sec_tlspin
    monkeypatch.setattr(sec_tlspin, "verify", lambda cfg, url, ca: True)
    monkeypatch.setattr(sec_tlspin, "learn", lambda cfg, url, timeout=10.0: None)
    yield


@pytest.fixture()
def real_tls():
    """The real sec_tlspin (see _no_tls_pin_over_the_network)."""
    return True


def in_a_user_namespace() -> bool:
    """Inside a cage (bubblewrap's --unshare-user: the sandbox stage of a change, the live cage after one) only the
    runner's own id is mapped: /proc/self/uid_map is one line of one id, never the host's «0 0 4294967295»."""
    try:
        return Path("/proc/self/uid_map").read_text().split() != ["0", "0", "4294967295"]
    except OSError:
        return False                                   # no /proc (the Mac and Windows ports): not a Linux cage


# C585: what a test needs that a cage takes away on purpose — said per test, so a skip is never silent
CAGED = {
    "test_evd_chat.py::test_the_chat_agent_has_evidentias_tools_only_and_saves_into_the_case":
        "needs this installation's .env, hidden in the cage",
    "test_evd_chat.py::test_the_page_reaches_the_reopen_of_a_lead_and_never_its_report":
        "needs this installation's .env, hidden in the cage",
    "tests/local/test_evd_worker.py": "needs this installation's .env, hidden in the cage",
    "test_mcp_servers.py::test_a_real_server_outside_aurora_answers_from_its_cage_and_sees_nothing_else":
        "starts its own cage: a cage inside the cage is refused",
    "test_service_account.py::test_the_services_never_get_to_write_what_the_owner_runs":
        "hands files to the services' group, which a user namespace does not map",
    "test_sshkey.py::test_a_sealed_key_logs_in_through_its_own_agent":
        "ssh refuses its system config, owned by an id the cage does not map",
}


def pytest_collection_modifyitems(config, items):
    if not in_a_user_namespace():
        return
    for item in items:
        for key, why in CAGED.items():
            if item.nodeid.endswith(key) or key in item.nodeid:
                item.add_marker(pytest.mark.skip(reason=f"in a cage: {why} (C585)"))


@pytest.fixture(autouse=True, scope="module")
def _this_installation_for_local_tests(request):
    """tests/local: this installation's own tests (never published) read its configuration on purpose — Evidentia's
    chat and worker against the live archive's settings. Every other test runs on a test installation of its own
    (_never_the_installation); what a local test imported bound to this one (api.core's BASE, its pipelines) is
    forgotten after its module, so a later test imports it again on its own test installation."""
    import os
    import sys
    was = os.environ.get("AURORA_ENV_FILE", "")
    local = f"{os.sep}tests{os.sep}local{os.sep}" in str(getattr(request, "path", "") or request.fspath)
    if not local or not os.path.basename(os.path.dirname(was)).startswith("aurora-tests-"):
        yield
        return
    del os.environ["AURORA_ENV_FILE"]
    cached, before = sys_config._cached, set(sys.modules)
    sys_config._cached = None
    try:
        yield
    finally:
        os.environ["AURORA_ENV_FILE"] = was
        sys_config._cached = cached
        for name in set(sys.modules) - before:
            if name.startswith("aurora.api"):
                sys.modules.pop(name, None)
