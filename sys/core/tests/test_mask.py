# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from aurora.sec_mask import Pseudonymizer, luhn


def test_sensitive_data_goes_out_masked_and_comes_back_whole(cfg):
    cfg.values.update(AURORA_OWNER_NAME="Mario Rossi", AURORA_DOMAIN="aurora.example.net",
                      AURORA_CLOUD_MASK_WORDS="Progetto Fenice, Via Roma 1")
    key = cfg.values["AURORA_API_KEY"]
    p = Pseudonymizer(cfg)
    raw = (f"Mario Rossi (mario@example.net, +39 333 123 4567) vede 192.168.0.205 e di nuovo 192.168.0.205; "
           f"IBAN IT60 X054 2811 1010 0000 0123 456, carta 4111 1111 1111 1111, chiave {key}, mac 00:11:22:33:44:55, "
           f'device_name="xg.example.net" serial=X99000AB1CDEF23, Progetto Fenice in Via Roma 1, ts 1790881354569')
    out = p.mask(raw)
    for leak in ("Mario", "mario@", "333 123", "192.168", "IT60", "4111", key, "00:11:22", "example.net", "X99000",
                 "Fenice", "Via Roma"):
        assert leak not in out, leak
    assert out.count("[IP_1]") == 2 and "[IP_2]" not in out              # the same address, the same placeholder
    assert "1790881354569" in out                                          # a timestamp is not a card (Luhn)
    assert p.unmask(out) == raw
    assert p.unmask("Il dispositivo [IP_1] e [IP_9]") == "Il dispositivo 192.168.0.205 e [IP_9]"
    assert p.counts["IP"] == 1 and p.counts["SECRET"] == 1


def test_a_placeholder_split_across_stream_pieces_is_put_back(cfg):
    p = Pseudonymizer(cfg)
    p.mask("server 10.0.0.7")
    pieces = [("thought", "x"), ("answer", "Il server [I"), ("answer", "P_1] risponde"), ("answer", ".")]
    assert "".join(t for k, t in p.unmask_stream(pieces) if k == "answer") == "Il server 10.0.0.7 risponde."


def test_luhn():
    assert luhn("4111 1111 1111 1111") and not luhn("1790881354569") and not luhn("1234")


def test_dates_numbers_and_code_stay_readable(cfg):
    p = Pseudonymizer(cfg)
    text = "il 01.10.2026 alle 17:23 (2026-10-01T17:23:13+02:00) 17.853 documenti, versione 2.14.0, porta 6667, 1790881354569"
    assert p.mask(text) == text


def test_a_phone_at_the_end_of_a_sentence_is_masked(cfg):
    p = Pseudonymizer(cfg)
    out = p.mask("Chiamami al +39 333 123 4567. Oppure allo 02 1234 5678.")
    assert "333" not in out and "1234" not in out and out.count("[PHONE_") == 2
    assert p.mask("Il 01.10.2026. Versione 2.14.0.") == "Il 01.10.2026. Versione 2.14.0."


def test_a_model_that_drops_the_brackets_still_gets_the_real_values_back_only_for_its_own(cfg):
    p = Pseudonymizer(cfg)
    p.mask("server 10.20.30.40, mail mario@example.org")
    assert p.unmask("IP_1 | EMAIL_1 | IP_7 | VIP_1x") == "10.20.30.40 | mario@example.org | IP_7 | VIP_1x"
