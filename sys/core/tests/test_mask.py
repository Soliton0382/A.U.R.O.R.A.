# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from aurora.sec_mask import Pseudonymizer, luhn


def test_sensitive_data_goes_out_masked_and_comes_back_whole(cfg):
    cfg.values.update(AURORA_OWNER_NAME="Mario Rossi", AURORA_DOMAIN="aurora.example.net",
                      AURORA_CLOUD_MASK_WORDS="Progetto Fenice, Via Roma 1")
    key = cfg.values["AURORA_API_KEY"]
    p = Pseudonymizer(cfg)
    raw = (f"Mario Rossi (mario@example.net, +39 333 123 4567) vede 172.16.5.205 e di nuovo 172.16.5.205; "
           f"IBAN IT60 X054 2811 1010 0000 0123 456, carta 4111 1111 1111 1111, chiave {key}, mac 00:11:22:33:44:55, "
           f'device_name="xg.example.net" serial=X99000AB1CDEF23, Progetto Fenice in Via Roma 1, ts 1790881354569')
    out = p.mask(raw)
    for leak in ("Mario", "mario@", "333 123", "192.168", "IT60", "4111", key, "00:11:22", "example.net", "X99000",
                 "Fenice", "Via Roma"):
        assert leak not in out, leak
    assert out.count("[IP_1]") == 2 and "[IP_2]" not in out              # the same address, the same placeholder
    assert "1790881354569" in out                                          # a timestamp is not a card (Luhn)
    assert p.unmask(out) == raw
    assert p.unmask("Il dispositivo [IP_1] e [IP_9]") == "Il dispositivo 172.16.5.205 e [IP_9]"
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


# a fake key block, written in pieces: the publication's secret scan must not see a key header in the repository
KEY_BLOCK = ("-----BEGIN OPENSSH " + "PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAA\n" + "-----END OPENSSH " + "PRIVATE KEY-----")


def test_the_new_kinds_are_masked_and_come_back_while_plain_text_stays(cfg):
    """Owner, 2026-10-05: tax code, VAT, plates, addresses, documents, dates of birth, passwords, keys, JWT, links."""
    from aurora.sec_mask import Pseudonymizer
    p = Pseudonymizer(cfg)
    secret_bits = ["RSSMRA80A01H501U", "IT01234567890", "Via Giuseppe Verdi 12", "AB 123 CD", "S3gret!xyz", "03/04/1980",
                   "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
                   "mario:segretissima", "U1A2B3C4D", "YA1234567", "b3BlbnNzaC1rZXktdjEAAAA"]
    text = ("Codice fiscale RSSMRA80A01H501U, P.IVA IT01234567890; abito in Via Giuseppe Verdi 12, targa AB 123 CD. "
            "password: S3gret!xyz, nato il 03/04/1980. Token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U, repo https://mario:segretissima@git.example.org/x.git, "
            "patente U1A2B3C4D, passaporto YA1234567.\n" + KEY_BLOCK)
    m = p.mask(text)
    assert not [b for b in secret_bits if b in m], m
    assert p.unmask(m) == text
    plain = "The year 2024 had 365 days, version 3.14.2, room 101; the Via Lattea is a galaxy; I was born in Rome."
    assert p.mask(plain) == plain


def test_the_owner_s_name_is_put_in_before_masking_so_it_never_leaves(cfg):
    """C132: %OWNER% was filled by the provider's client, after the masking: the name would have left in clear."""
    from aurora.mdl_router import MaskedLLM
    from aurora.mdl_llm import Completion
    cfg.values["AURORA_OWNER_NAME"] = "Giacomino"
    sent = {}

    class Inner:
        name, model = "fake", "m"

        def complete(self, system, user, max_tokens, think=False):
            sent["system"], sent["user"] = system, user
            return Completion("Ciao [PRIVATE_1]", "", 1, 0.1, False)
    out = MaskedLLM(Inner(), "agent", cfg).complete("You speak with %OWNER%.", "Sono Giacomino", 50)
    assert "Giacomino" not in sent["system"] and "Giacomino" not in sent["user"] and "%OWNER%" not in sent["system"]
    assert out.answer == "Ciao Giacomino"
