# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The end of an installation: where to open Aurora, the key that registers a browser or an app, how a phone gets in.

    python sys/core/script/sys_ready.py             # install.sh, step 13
    python sys/core/script/sys_ready.py --pending   # the services are not started yet (sudo left to do by hand)

Printed every time, also when the installer stops before the services: the address and the key are what the person
installing needs, and the key is in the .env only (generated anew for every new installation).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import net_https, sys_config  # noqa: E402


def lines(cfg: sys_config.Config, it: bool, pending: bool) -> list[str]:
    t = (lambda a, b: a) if it else (lambda a, b: b)
    st = net_https.status(cfg)
    out = []
    if pending:
        out.append(t("  Dopo i comandi qui sopra:", "  After the commands above:"))
    out.append(f"  WebUI:   {st['urls'][0]}")
    for u in st["urls"][1:]:
        out.append(f"           {u}")
    out.append(f"  {t('Chiave API', 'API key')}: {cfg['AURORA_API_KEY']}   "
               + t("(una volta, per registrare ogni browser o app)", "(once, to register each browser or app)"))
    others = [n for n in st["names"] if n != "localhost"]
    if others and st["mode"] == "internal":
        http = int(cfg["AURORA_HTTP_PORT"])
        ca = f"http://{net_https._host(others[0])}{'' if http == 80 else f':{http}'}{net_https.CA_PATH}"
        out += ["", t("  Dal telefono (stessa rete Wi-Fi):", "  From the phone (same Wi-Fi network):"),
                t(f"    1. apri {ca} e installa il certificato come «certificato CA» (impostazioni di sicurezza del telefono)",
                  f"    1. open {ca} and install the certificate as a «CA certificate» (the phone's security settings)"),
                t(f"    2. apri {st['urls'][0]} e incolla la chiave API; poi «Aggiungi a schermata Home» per averla come app",
                  f"    2. open {st['urls'][0]} and paste the API key; then «Add to Home screen» to have it as an app"),
                t("    Consiglio: nel router dai a questo computer un indirizzo fisso, o l'indirizzo cambierà.",
                  "    Advice: give this computer a fixed address in the router, or the address will change.")]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pending", action="store_true", help="the services are not started yet")
    args = ap.parse_args()
    it = os.environ.get("LANG", "").startswith("it")
    print("\n".join(lines(sys_config.get(), it, args.pending)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
