#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The answer key of the law-office bench, written BEFORE Evidentia reads the corpus; frozen by SHA-256 (chiave.sha256).
gold: [stem, page] pairs where the fact is written; «scan» = a PDF without text (Evidentia does not OCR PDFs today),
«png» = an image Evidentia reads by OCR (English model). All cases invented.
Usage: /usr/bin/python3 -I chiave.py  → ../chiave/chiave.json and ../chiave/chiave.sha256"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LOOKUP = [  # (a) one fact, with document and page
    ("a1", "A", "Qual è la penale per il ritardo nella consegna prevista dal contratto 2025/114 e qual è il suo tetto massimo?",
     [["0,5%"], ["10%"]], [["A01_contratto_fornitura_2025-114", 2]]),
    ("a2", "A", "Qual è il prezzo complessivo della fornitura nel contratto tra Ferri Meccanica e Lumen Impianti?",
     [["184.500"]], [["A01_contratto_fornitura_2025-114", 1]]),
    ("a3", "A", "Quale foro è competente per le controversie del contratto di fornitura con Lumen Impianti?",
     [["Brescia"]], [["A01_contratto_fornitura_2025-114", 3]]),
    ("a4", "A", "In che data sono state effettivamente consegnate le linee LX-900 a Ferri Meccanica?",
     [["2 luglio 2025", "02/07/2025", "2 luglio"]], [["A08_DDT_3318_consegna", 1], ["A09_verbale_installazione", 1]]),
    ("a5", "A", "Quanto ha speso Ferri Meccanica per far verniciare all'esterno mentre le linee erano ferme?",
     [["11.240"]], [["A13_email_interna_ferri_produzione", 1], ["A14_fatture_terzista_gardesane", 1],
                     ["A16_pec_rifiuto_proposta", 1]]),
    ("a6", "A", "Quale somma è stata ingiunta a Ferri Meccanica con il decreto ingiuntivo n. 1543/2025?",
     [["157.563"]], [["A17_decreto_ingiuntivo_1543-2025", 1]]),
    ("a7", "B", "Con quale livello del CCNL è stato assunto Giorgio Rinaldi secondo il contratto di assunzione?",
     [["livello 3"]], [["B01_contratto_assunzione_Rinaldi", 1]]),
    ("a8", "B", "Qual è la retribuzione lorda mensile di Giorgio Rinaldi?",
     [["2.140"]], [["B01_contratto_assunzione_Rinaldi", 1], ["B11_busta_paga_marzo", 1], ["B36_cedolino_febbraio_Rinaldi", 1]]),
    ("a9", "B", "A che ora risulta entrato Rinaldi il 19 marzo 2025 secondo il cartellino presenze?",
     [["08:02", "8:02", "8.02"]], [["B04_cartellino_presenze_marzo", 2]]),
    ("a10", "B", "In che data Rinaldi ha ricevuto la lettera di licenziamento?",
     [["22 aprile 2025", "22/04/2025", "22 aprile"]], [["B10_ricevuta_raccomandata_licenziamento", 1],
                                                       ["B13_impugnazione_stragiudiziale", 1]]),
    ("a11", "B", "In che data è stata emessa la comunicazione di servizio sul cambio turno del magazzino B e da quando si applica?",
     [["17 marzo"], ["24 marzo"]], [["B03_comunicazione_cambio_turno", 1]]),
    ("a12", "B", "Per quanto tempo è rimasta chiusa la tangenziale sud il 12 marzo 2025?",
     [["07:35", "7:35", "7.35"], ["08:40", "8:40", "8.40"]], [["B12_verbale_polizia_locale_12_marzo", 1]]),
    ("a13", "C", "Qual è l'importo del preventivo approvato per rifare l'impermeabilizzazione del lastrico solare?",
     [["38.600"]], [["C05_preventivo_Impermeabilizzazioni_Adige", 1], ["C07_verbale_assemblea_12_maggio", 1],
                    ["C34_contratto_appalto_lavori", 1]]),
    ("a14", "C", "Quanti millesimi risultano presenti all'assemblea straordinaria del 12 maggio 2025 secondo il verbale?",
     [["612"]], [["C07_verbale_assemblea_12_maggio", 1]]),
    ("a15", "C", "Come ripartisce l'art. 15 del regolamento le spese di manutenzione straordinaria del lastrico solare?",
     [["due terzi", "2/3"]], [["C01_regolamento_condominio", 1]]),
    ("a16", "C", "A quanto stima i danni all'interno 4 la perizia dell'Ing. Moretti?",
     [["4.800"]], [["C04_perizia_Moretti", 2]]),
    ("a17", "C", "In che data è stato comunicato il verbale dell'assemblea alla Sig.ra Bassi?",
     [["20 maggio 2025", "20/05/2025", "20 maggio"]], [["C09_invio_verbale_assenti", 1]]),
    ("a18", "C", "Qual è la causa delle infiltrazioni nell'interno 4 secondo la perizia tecnica?",
     [["guaina"]], [["C04_perizia_Moretti", 2]]),
]

CHRONO = {  # (b) the key events: date that must appear, and where it is written
    "A": [("14 marzo 2025", "A01_contratto_fornitura_2025-114"), ("17 marzo 2025", "A03_bonifico_acconto_30"),
          ("13 maggio 2025", "A06_pec_diffida_ad_adempiere"), ("10 giugno 2025", "A06_pec_diffida_ad_adempiere"),
          ("16 giugno 2025", "A07_pec_risposta_lumen_forza_maggiore"), ("2 luglio 2025", "A09_verbale_installazione"),
          ("14 luglio 2025", "A09_verbale_installazione"), ("24 luglio 2025", "A10_verbale_collaudo_negativo"),
          ("5 settembre 2025", "A15_verbale_riunione_5_settembre"), ("11 settembre 2025", "A16_pec_rifiuto_proposta"),
          ("26 settembre 2025", "A17_decreto_ingiuntivo_1543-2025"), ("3 ottobre 2025", "A18_relata_notifica_decreto")],
    "B": [("1 febbraio 2019", "B01_contratto_assunzione_Rinaldi"), ("17 marzo 2025", "B03_comunicazione_cambio_turno"),
          ("7 aprile 2025", "B05_lettera_contestazione_disciplinare"), ("11 aprile 2025", "B06_giustificazioni_Rinaldi"),
          ("18 aprile 2025", "B10_ricevuta_raccomandata_licenziamento"), ("22 aprile 2025", "B10_ricevuta_raccomandata_licenziamento"),
          ("9 giugno 2025", "B13_impugnazione_stragiudiziale")],
    "C": [("3 febbraio 2025", "C03_segnalazione_Bassi_infiltrazioni"), ("21 marzo 2025", "C04_perizia_Moretti"),
          ("2 aprile 2025", "C04_perizia_Moretti"), ("10 aprile 2025", "C05_preventivo_Impermeabilizzazioni_Adige"),
          ("28 aprile 2025", "C06_convocazione_assemblea"), ("12 maggio 2025", "C07_verbale_assemblea_12_maggio"),
          ("20 maggio 2025", "C09_invio_verbale_assenti"), ("5 giugno 2025", "C10_lettera_avv_Bassi_contestazione"),
          ("13 giugno 2025", "C13_mediazione_istanza")],
}

CONTRA = {  # (c) contradictions: each side's words; found if the answer names both sides
    "A": [("c1", "data di consegna", [["20 giugno"], ["2 luglio"]]),
          ("c2", "durata dello sciopero", [["9 maggio"], ["2 maggio"]]),
          ("c3", "importo del saldo", [["148.500"], ["157.563", "184.500"]])],
    "B": [("c4", "livello di inquadramento", [["livello 4"], ["livello 3"]]),
          ("c5", "ingresso del 19 marzo", [["32 minuti", "32 min"], ["08:02", "8:02"]]),
          ("c6", "comunicazione del cambio turno", [["17 marzo"], ["25 marzo", "a voce"]])],
    "C": [("c7", "millesimi presenti", [["612"], ["587"]]),
          ("c8", "causa dei danni", [["impianto idraulico", "impianti"], ["guaina", "perizia"]]),
          ("c9", "ripartizione della spesa", [["art. 15", "articolo 15", "due terzi"], ["millesimi"]]),
          ("c10", "importo dei danni", [["6.200"], ["4.800"]])],
}

DEADLINES = [  # (d) termini: the date the agent must give; norm = what it rests on (not in the corpus)
    ("d1", "A", "opposizione al decreto ingiuntivo n. 1543/2025", ["12 novembre 2025", "12/11/2025"],
     "40 giorni dalla notifica del 3 ottobre 2025 (art. 641 c.p.c.; il termine è scritto nel decreto, che è una scansione)"),
    ("d2", "A", "consegna delle linee secondo il contratto", ["13 maggio 2025", "13/05/2025"], "art. 4: 60 giorni dal 14 marzo 2025"),
    ("d3", "A", "intervento del fornitore dopo il collaudo negativo", ["13 agosto 2025", "13/08/2025"],
     "20 giorni dal 24 luglio 2025 (verbale di collaudo)"),
    ("d4", "B", "impugnazione stragiudiziale del licenziamento", ["21 giugno 2025", "21/06/2025"],
     "60 giorni dalla ricezione del 22 aprile 2025 (art. 6 l. 604/1966)"),
    ("d5", "B", "deposito del ricorso al giudice del lavoro", ["6 dicembre 2025", "06/12/2025"],
     "180 giorni dall'impugnazione del 9 giugno 2025 (art. 6 c. 2 l. 604/1966)"),
    ("d6", "C", "impugnazione della delibera del 12 maggio 2025 da parte della condomina assente", ["19 giugno 2025", "19/06/2025"],
     "30 giorni dalla comunicazione del 20 maggio 2025 (art. 1137 c.c.)"),
]

SUMMARY = {  # (e) the points a summary for the client must contain
    "A": [["184.500"], ["2 luglio"], ["collaudo", "negativo"], ["18.450", "penale"], ["1543", "decreto ingiuntivo"]],
    "B": [["18 aprile", "licenziamento"], ["08:02", "cartellino"], ["livello"], ["22 aprile"], ["9 giugno", "impugnazione"]],
    "C": [["38.600"], ["guaina", "perizia"], ["612", "587", "millesimi"], ["6.200", "4.800"], ["20 maggio"]],
}

CLASSIFY = [  # (f) fatto / testimonianza / accusa
    ("f1", "B", "Rinaldi ha alterato la timbratura del 19 marzo 2025.", ["accusa"]),
    ("f2", "B", "Il caporeparto non ha visto Rinaldi in magazzino prima delle 08:30 del 19 marzo.", ["testimonianza"]),
    ("f3", "B", "Il cartellino registra l'ingresso di Rinaldi alle 08:02 del 19 marzo 2025.", ["fatto"]),
    ("f4", "B", "Il cambio turno era stato comunicato solo a voce prima del 24 marzo.", ["testimonianza"]),
    ("f5", "B", "Il 12 marzo 2025 la tangenziale sud è rimasta chiusa dalle 07:35 alle 08:40.", ["fatto"]),
    ("f6", "C", "La Sig.ra Bassi ha lasciato aperto il lucernario per settimane.", ["accusa", "testimonianza"]),
    ("f7", "A", "Lumen ha comunicato lo sciopero a Ferri per telefono ai primi di maggio.", ["testimonianza"]),
    ("f8", "A", "Le linee LX-900 sono state consegnate il 2 luglio 2025.", ["fatto"]),
]

ISOLATION = [  # (g) a question asked inside one matter; any hit from another matter is a leak
    ("g1", "A", "Ferri"), ("g2", "A", "penale ritardo"), ("g3", "A", "decreto ingiuntivo notifica"),
    ("g4", "B", "contestazione disciplinare ritardo"), ("g5", "B", "turno"), ("g6", "C", "Ferri lucernario"),
    ("g7", "C", "preventivo"), ("g8", "C", "assemblea millesimi"),
]

ITALIAN = [  # (i) the same thing asked with another inflection: the English stemmer of the index
    ("i1", "penale", "penali", "A01_contratto_fornitura_2025-114"), ("i2", "licenziamento", "licenziato", "B09_lettera_licenziamento"),
    ("i3", "infiltrazioni", "infiltrazione", "C04_perizia_Moretti"), ("i4", "consegnate", "consegna", "A08_DDT_3318_consegna"),
    ("i5", "assemblea", "assemblee", "C07_verbale_assemblea_12_maggio"), ("i6", "ritardi", "ritardo", "B05_lettera_contestazione_disciplinare"),
    ("i7", "giustificazioni", "giustificazione", "B06_giustificazioni_Rinaldi"), ("i8", "condomini", "condominio", "C07_verbale_assemblea_12_maggio"),
]


def main() -> None:
    key = {"written": "2026-11-19", "rule": "invented cases only; frozen before Evidentia reads the corpus",
           "lookup": LOOKUP, "chrono": CHRONO, "contra": CONTRA, "deadlines": DEADLINES, "summary": SUMMARY,
           "classify": CLASSIFY, "isolation": ISOLATION, "italian": ITALIAN,
           "manifest_sha256": hashlib.sha256((ROOT / "manifest.json").read_bytes()).hexdigest()}
    out = ROOT / "chiave"
    out.mkdir(exist_ok=True)
    data = json.dumps(key, indent=1, ensure_ascii=False).encode()
    (out / "chiave.json").write_bytes(data)
    h = hashlib.sha256(data).hexdigest()
    (out / "chiave.sha256").write_text(f"{h}  chiave.json\n")
    print(h)


if __name__ == "__main__":
    main()
