# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""☁️ Cloudflare as a page of the security area, and the masked words in ☁️ Accounts (owner, 16 Oct)."""
import json
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]


def test_the_cloudflare_page_is_the_admin_s_and_reads_aurora_s_own_records():
    src = (CORE / "aurora" / "api" / "edge.py").read_text(encoding="utf-8")
    for route in ('"/v1/aurora/security/edge"', '"/v1/aurora/security/edge/culprits"', '"/v1/aurora/security/edge/block"',
                  '"/v1/aurora/security/edge/unblock"'):
        assert f"{route}, dependencies=[Depends(admin_only)]" in src, route
    assert "net_cfwaf.block," in src and "net_cfwaf.unblock," in src            # Aurora's own records, one module
    manifest = json.loads((CORE.parent / "plugins" / "cloudflare" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["page"] == "edge"
    page = (CORE / "webui" / "js" / "modules" / "security_edge.js").read_text(encoding="utf-8")
    assert 'autonomySlot("edge")' in page and 'pluginSlot("edge")' in page


def test_what_is_masked_is_shown_built_in_rules_apart_from_each_person_s_words(cfg):
    """Owner, 16 Oct: «far vedere i mascheramenti di default e quelli impostati per utente», and the same for posts."""
    from aurora import sec_mask, sec_privacy
    described = {k for k, *_ in sec_mask.RULES}
    assert {k for k, _ in sec_mask.PATTERNS + sec_mask.BLOCKS} - {"IP6"} <= described      # IPv6 told with IP
    assert {"ID", "FIELD", "SECRET"} <= described
    cfg.values["AURORA_CLOUD_MASK_MINE"] = "Progetto Orsa"
    assert "Progetto Orsa" in sec_mask.Pseudonymizer(cfg).private                       # a person's own words count
    cfg.values["AURORA_SOCIAL_PRIVATE_WORDS"] = "Lilla, Monte Basso"
    found = {f["value"]: f for f in sec_privacy.findings("Oggi con lilla al monte basso.", cfg)}
    assert found["lilla"]["kind"] == "PRIVATE" and "monte basso" in found
    src = (CORE / "aurora" / "api" / "accounts.py").read_text(encoding="utf-8")
    assert '"installation": house if admin else []' in src                                 # a user sees how many
    js = (CORE / "webui" / "js" / "modules" / "accounts.js").read_text(encoding="utf-8")
    assert 'wordsEditor("AURORA_CLOUD_MASK_MINE"' in js and 'rulesList(m.rules' in js
    social = (CORE / "webui" / "js" / "modules" / "social.js").read_text(encoding="utf-8")
    assert 'wordsEditor("AURORA_SOCIAL_PRIVATE_WORDS"' in social
