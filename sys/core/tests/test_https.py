# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔒 HTTPS (net_https): the Caddyfile from the settings with the other names of this machine, the root certificate for
the phones, the owner's own certificate checked before use and put back when anything fails, the way back to Caddy's
authority; the end of an installation saying where to open Aurora, with the key, every time."""
import datetime as dt
import importlib.util
import subprocess

import pytest

from aurora import net_https, sys_config

from conftest import private, write_env

# Caddy takes a new Caddyfile by a reload here; the ports (Mac, Windows) restart their service (rewrites.py)
RELOAD = "restart" if importlib.util.find_spec("aurora.sys_platform") else "reload"


def pem_pair(names, days=30, start_days=-1):
    """A self-signed certificate naming `names` (DNS or IP), and its key, as PEM."""
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    sans = []
    for n in names:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(n)))
        except ValueError:
            sans.append(x509.DNSName(n))
    now = dt.datetime.now(dt.UTC)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now + dt.timedelta(days=start_days))
            .not_valid_after(now + dt.timedelta(days=days)).add_extension(x509.SubjectAlternativeName(sans), False)
            .sign(key, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


@pytest.fixture
def https(tmp_path, monkeypatch):
    """An installation answering at aurora.example.com, with caddy and systemctl answered by the test."""
    cfg = sys_config.load(write_env(tmp_path, AURORA_DOMAIN="aurora.example.com"), check_root=False)
    calls = []
    try:                    # the ports keep secrets by the folder's ACL, which the installer sets (Windows: no 0600);
        from aurora import sys_platform               # before subprocess.run is answered by the test below
        sys_platform.current().make_private(tmp_path)
    except ImportError:
        pass

    def run(cmd, **k):
        calls.append(cmd)
        bad = getattr(run, "fail", None)
        return subprocess.CompletedProcess(cmd, 1 if bad and bad in cmd else 0, "", "refused" if bad in cmd else "")
    monkeypatch.setattr(net_https.subprocess, "run", run)
    monkeypatch.setattr(net_https, "ca_dir", lambda c: tmp_path / "ca")
    try:                                              # the ports: Caddy's service through the platform, answered here too
        from aurora import sys_platform               # (a Windows run of this test restarted the real task, 9 Oct)
        from aurora.sys_platform.base import Result
        plat = sys_platform.current()

        def action(verb, units, wait=True, timeout=120):
            r = run(["systemctl", verb, *[u.removesuffix(".service") for u in units]])
            return Result(r.returncode, "", r.stderr)
        monkeypatch.setattr(plat, "service_action", action)
    except ImportError:                               # the Linux tree: systemctl itself, answered by run()
        pass
    return cfg, calls, run


def test_one_site_for_every_name_and_the_root_for_the_phones(https):
    cfg, _, _ = https
    text = net_https.render(cfg, AURORA_DOMAIN="192.168.1.20", AURORA_DOMAIN_ALIASES="casa.local, localhost,casa.local")
    assert "192.168.1.20:443, casa.local:443, localhost:443 {" in text
    assert "http://192.168.1.20:80, http://casa.local:80, http://localhost:80 {" in text
    assert f"handle {net_https.CA_PATH}" in text and "rewrite * /root.crt" in text and "tls internal" in text
    own = net_https.render(cfg, AURORA_TLS_MODE="files")
    assert net_https.CA_PATH not in own and "tls internal" not in own            # an own certificate: no local root
    assert "[fd00::5]:443" in net_https.render(cfg, AURORA_DOMAIN_ALIASES="fd00::5")


def test_a_certificate_is_refused_with_its_reason(https):
    cfg, _, _ = https
    cert, key = pem_pair(["aurora.example.com"])
    other_cert, other_key = pem_pair(["aurora.example.com"])
    for c, k, why in [(b"nonsense", key, "PEM"), (cert, b"nonsense", "private key"), (cert, other_key, "not this"),
                      (*pem_pair(["altro.example.com"]), "not aurora.example.com"),
                      (*pem_pair(["aurora.example.com"], days=-1, start_days=-10), "expired"),
                      (*pem_pair(["aurora.example.com"], start_days=2), "valid only from")]:
        with pytest.raises(net_https.HttpsError, match=why):
            net_https.check_pair(c, k, "aurora.example.com")
    assert net_https.check_pair(*pem_pair(["*.example.com"]), "aurora.example.com")["days_left"] >= 29


def test_the_owners_certificate_goes_in_and_the_names_set_before_stay(https, monkeypatch):
    cfg, calls, _ = https
    net_https.set_aliases(cfg, ["192.168.1.20", "Casa.local"])
    cert, key = pem_pair(["aurora.example.com", "casa.local"])
    out = net_https.install_cert(cfg, cert, key)       # cfg is the one loaded before: the .env is read again
    assert out["mode"] == "files" and out["not_covered"] == ["192.168.1.20"]
    now = net_https.fresh(cfg)
    assert now["AURORA_TLS_MODE"] == "files" and now["AURORA_DOMAIN_ALIASES"] == "192.168.1.20,casa.local"
    assert now.path("AURORA_TLS_CERT").read_bytes() == cert
    text = net_https.caddyfile(cfg).read_text()
    assert "casa.local:443" in text and f"tls {net_https._q(now.path('AURORA_TLS_CERT'))}" in text
    assert ["systemctl", RELOAD, "aurora-https"] in calls
    assert net_https.use_internal(cfg)["mode"] == "internal" and "tls internal" in net_https.caddyfile(cfg).read_text()
    monkeypatch.undo()                                # the ports ask their system who may read it (not answered here)
    assert private(now.path("AURORA_TLS_KEY"))


def test_a_reload_that_fails_puts_everything_back(https):
    cfg, _, run = https
    old_cert, old_key = pem_pair(["aurora.example.com"])
    net_https.install_cert(cfg, old_cert, old_key)
    before = net_https.caddyfile(cfg).read_text()
    run.fail = RELOAD
    with pytest.raises(net_https.HttpsError, match="refused"):
        net_https.install_cert(cfg, *pem_pair(["aurora.example.com"]))
    now = net_https.fresh(cfg)
    assert now.path("AURORA_TLS_CERT").read_bytes() == old_cert and now.path("AURORA_TLS_KEY").read_bytes() == old_key
    assert net_https.caddyfile(cfg).read_text() == before and now["AURORA_TLS_MODE"] == "files"
    with pytest.raises(net_https.HttpsError, match="not a name"):
        net_https.set_aliases(cfg, ["bad name;rm"])


def test_an_invalid_caddyfile_is_not_left_in_place(https):
    cfg, _, run = https
    good = net_https.write(cfg).read_text()
    run.fail = "validate"
    with pytest.raises(net_https.HttpsError, match="caddy validate"):
        net_https.write(cfg, AURORA_DOMAIN_ALIASES="casa.local")
    assert net_https.caddyfile(cfg).read_text() == good


def test_the_end_of_an_installation_says_where_and_how_also_for_the_phone(https):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
    import sys_ready
    cfg, _, _ = https
    sys_config.write_env(cfg.env_file, {"AURORA_DOMAIN": "192.168.1.20", "AURORA_DOMAIN_ALIASES": "casa.local,localhost"})
    cfg = net_https.fresh(cfg)
    text = "\n".join(sys_ready.lines(cfg, True, pending=True))
    assert "https://192.168.1.20/" in text and cfg["AURORA_API_KEY"] in text and "Dopo i comandi" in text
    assert "http://192.168.1.20/aurora-ca.crt" in text and "telefono" in text
    sys_config.write_env(cfg.env_file, {"AURORA_DOMAIN": "localhost", "AURORA_DOMAIN_ALIASES": ""})
    alone = "\n".join(sys_ready.lines(net_https.fresh(cfg), False, pending=False))
    assert "https://localhost/" in alone and "phone" not in alone


def test_other_ports_are_checked_then_used_and_a_failure_puts_everything_back(https, monkeypatch):
    """Owner, 9 Oct: «voglio far usare ad aurora un'altra porta perchè sulla 443 ho altri servizi»."""
    import socket
    cfg, calls, run = https
    restarts = []
    monkeypatch.setattr(net_https, "restart_api_later", lambda: restarts.append(1))
    with pytest.raises(net_https.HttpsError, match="different"):
        net_https.set_ports(cfg, 8443, 8443)
    with pytest.raises(net_https.HttpsError, match="Aurora's own"):
        net_https.set_ports(cfg, int(cfg["AURORA_API_PORT"]), 8080)
    with socket.socket() as busy:                                     # another program already there
        busy.bind(("0.0.0.0", 0))
        busy.listen()
        with pytest.raises(net_https.HttpsError, match="already used"):
            net_https.set_ports(cfg, busy.getsockname()[1], 8080)
    monkeypatch.setattr(net_https, "_in_use", lambda port: False)   # the next ports may be taken on the suite's machine
    out = net_https.set_ports(cfg, 8443, 8080)
    assert out["changed"] and out["urls"] == ["https://aurora.example.com:8443/"] and restarts == [1]
    assert (net_https.fresh(cfg)["AURORA_HTTPS_PORT"], net_https.fresh(cfg)["AURORA_HTTP_PORT"]) == (8443, 8080)
    assert "aurora.example.com:8443 {" in net_https.caddyfile(cfg).read_text(encoding="utf-8")
    assert ["systemctl", "restart", "aurora-https"] in calls        # new listeners: a restart, not a reload
    # below 1024 only when Caddy's unit has the right to it (written so by the installer when it saw a low port)
    unit = cfg.root / "sys" / "deploy" / "systemd" / "aurora-https.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text("[Service]\nExecStart=caddy run\n", encoding="utf-8")
    with pytest.raises(net_https.HttpsError, match="install.sh"):
        net_https.set_ports(cfg, 443, 80)
    unit.write_text("[Service]\nAmbientCapabilities=CAP_NET_BIND_SERVICE\n", encoding="utf-8")
    assert net_https.set_ports(cfg, 8444, 80)["changed"]               # allowed now
    assert net_https.set_ports(cfg, 8443, 8080)["changed"]
    # Caddy refuses the new ports: settings and Caddyfile as they were
    run.fail = "restart"
    n = len(calls)
    with pytest.raises(net_https.HttpsError):
        net_https.set_ports(cfg, 9443, 9080)
    assert calls[n:].count(["systemctl", "restart", "aurora-https"]) == 2      # started again on the old file
    assert net_https.fresh(cfg)["AURORA_HTTPS_PORT"] == 8443 and restarts == [1, 1, 1]   # no restart for the refused one
    assert "aurora.example.com:8443 {" in net_https.caddyfile(cfg).read_text(encoding="utf-8")


def test_settings_refuse_an_api_port_as_the_https_port(https):
    """C227 (owner, 9 Oct): «dalla pagina web ho messo come porta caddy la 9700 … non raggiungo aurora». Settings now
    go through the 🔒 page's checks."""
    cfg, _, _ = https
    with pytest.raises(net_https.HttpsError, match="Aurora's own"):
        net_https.check_ports(cfg, int(cfg["AURORA_API_PORT"]), 80)
    with pytest.raises(net_https.HttpsError, match="different"):
        net_https.check_ports(cfg, 443, 443)


def test_caddy_follows_the_env_even_when_the_number_did_not_change(https, monkeypatch):
    """C228 (owner, 9 Oct): the .env said 8443 (written by hand) and Caddy still listened on 32443; asking 8443 again
    answered «no change» and left Caddy there. Now Caddy is written and restarted whenever its file is not the .env's."""
    cfg, calls, _ = https
    monkeypatch.setattr(net_https, "restart_api_later", lambda: None)
    monkeypatch.setattr(net_https, "_in_use", lambda port: False)
    from aurora import sys_config
    sys_config.write_env(cfg.env_file, {"AURORA_HTTPS_PORT": "8443"})             # by hand: Caddy never told
    net_https.caddyfile(cfg).parent.mkdir(parents=True, exist_ok=True)
    net_https.caddyfile(cfg).write_text("old file on 32443", encoding="utf-8")
    out = net_https.set_ports(cfg, 8443, 80)
    assert out["changed"] and "aurora.example.com:8443 {" in net_https.caddyfile(cfg).read_text(encoding="utf-8")
    assert ["systemctl", "restart", "aurora-https"] in calls
    n = len(calls)
    assert net_https.set_ports(cfg, 8443, 80)["changed"] is False and len(calls) == n          # aligned: nothing to do


def test_a_path_with_spaces_is_one_caddyfile_token(cfg, monkeypatch):
    """The Install run on a real Mac (9 Oct): Caddy's authority lives in «~/Library/Application Support/Caddy»; unquoted,
    «root * …/Application Support/…» was two arguments and the Caddyfile invalid."""
    from pathlib import Path
    from aurora import net_https
    monkeypatch.setattr(net_https, "ca_dir", lambda c: Path("/Users/r/Library/Application Support/Caddy/pki"))
    text = net_https.render(cfg, AURORA_TLS_MODE="internal")
    assert 'root * "/Users/r/Library/Application Support/Caddy/pki"' in text
    assert 'output file "' in text and net_https._q("C:\\Aurora\\x") == '"C:/Aurora/x"'


def test_an_untrusted_certificate_is_said_not_http_000(monkeypatch):
    """The owner's colleague, 9 Oct: «aurora-https: HTTPS non risponde (HTTP 000)» — curl refused Caddy's certificate
    (caddy trust never ran): the health says what is wrong and the command."""
    import subprocess
    from types import SimpleNamespace
    from aurora import sys_health
    for code, said in ((60, "sudo caddy trust"), (7, "nessuno ascolta")):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=code, stdout="000"))
        ok, how = sys_health._https("casa.local", 443)
        assert not ok and said in how


def test_a_firewall_that_stopped_speaking_is_said(cfg):
    """The owner, 10 Oct: the UDP port removed from ufw, no syslog for 8 hours and Aurora said nothing."""
    import os
    import time
    from aurora import sys_health
    cfg.values.update(AURORA_SENTINEL_ALLOW=["10.0.0.1"], AURORA_SENTINEL_BIND="10.0.0.2:5514")
    assert sys_health.syslog_silence(cfg) is None                       # never spoke here: nothing to say
    f = cfg.path("AURORA_LOG_DIR") / "firewall" / "firewall.log"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x\n")
    assert sys_health.syslog_silence(cfg) is None                       # fresh
    os.utime(f, (time.time() - 8 * 3600, time.time() - 8 * 3600))
    text, fix = sys_health.syslog_silence(cfg)
    assert "480 min" in text and "sudo ufw allow from 10.0.0.1 to any port 5514 proto udp" in fix
