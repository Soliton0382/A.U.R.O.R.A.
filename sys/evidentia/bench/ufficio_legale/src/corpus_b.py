# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Matter B (invented): Giorgio Rinaldi against Alfa Logistica S.r.l., a dismissal. Every name and event fictitious."""

def _timbrature(days):
    rows = "\n".join(f"{d} marzo 2025 — entrata {e} — uscita {u}" for d, e, u in days)
    return f"""ALFA LOGISTICA S.R.L. — CARTELLINO PRESENZE MARZO 2025
Dipendente: Giorgio Rinaldi, matricola 4471, reparto magazzino B, turno ordinario 08:00–17:00
{rows}"""


DOCS = [
    ("B01_contratto_assunzione_Rinaldi", "pdf", ["""CONTRATTO DI LAVORO SUBORDINATO A TEMPO INDETERMINATO
Tra ALFA LOGISTICA S.R.L., con sede in Via Fermi 9, Verona, e il Sig. GIORGIO RINALDI, nato a Mantova il 2 agosto 1984.
Data di assunzione: 1 febbraio 2019. Mansione: magazziniere addetto alla movimentazione merci. Inquadramento: livello 3 del CCNL Logistica, Trasporto Merci e Spedizione. Retribuzione lorda mensile: € 2.140,00 per 14 mensilità. Orario: 40 ore settimanali su turni comunicati per iscritto con almeno 7 giorni di preavviso.""", """Periodo di prova: 30 giorni lavorativi. Il lavoratore dichiara di aver ricevuto copia del codice disciplinare aziendale, affisso in bacheca ai sensi dell'art. 7 della legge 300/1970.
Verona, 28 gennaio 2019. Firmato: per Alfa Logistica, Dott. Marco Zanetti (Direttore del personale); il lavoratore, Giorgio Rinaldi"""]),
    ("B02_codice_disciplinare", "pdf", ["""ALFA LOGISTICA S.R.L. — CODICE DISCIPLINARE (estratto)
Punto 4. Ritardi: il ritardo non giustificato superiore a 15 minuti comporta, alla prima mancanza, il rimprovero scritto; in caso di recidiva nell'arco di 12 mesi, la multa fino a 4 ore di retribuzione; nei casi più gravi, la sospensione fino a 3 giorni.
Punto 9. Licenziamento per giusta causa: falsificazione di documenti aziendali, furto, rissa, insubordinazione grave."""]),
    ("B03_comunicazione_cambio_turno", "pdf", ["""ALFA LOGISTICA — COMUNICAZIONE DI SERVIZIO N. 14/2025
Data: 17 marzo 2025. Destinatari: personale magazzino B.
Dal 24 marzo 2025 il turno del magazzino B è anticipato alle ore 07:00–16:00.
Firmato: il caporeparto, Sig. Stefano Lodi"""]),
    ("B04_cartellino_presenze_marzo", "pdf", [_timbrature([
        (3, "07:58", "17:02"), (4, "08:01", "17:00"), (5, "07:59", "17:05"), (6, "08:00", "17:01"), (7, "07:57", "17:00"),
        (10, "08:03", "17:00"), (11, "07:59", "17:02"), (12, "08:24", "17:10"), (13, "08:00", "17:00"), (14, "07:58", "17:01")]),
        _timbrature([(17, "08:00", "17:00"), (18, "07:59", "17:03"), (19, "08:02", "17:00"), (20, "08:01", "17:02"),
                     (21, "07:58", "17:00"), (24, "07:41", "16:05"), (25, "07:02", "16:00"), (26, "07:38", "16:01"),
                     (27, "06:59", "16:00"), (28, "07:01", "16:02")])]),
    ("B05_lettera_contestazione_disciplinare", "pdf", ["""ALFA LOGISTICA S.R.L.
Raccomandata a mano — Verona, 7 aprile 2025
Al Sig. Giorgio Rinaldi, matricola 4471
Oggetto: contestazione disciplinare ai sensi dell'art. 7 della legge 300/1970
Le contestiamo i seguenti addebiti: ritardi non giustificati nelle giornate del 12 marzo 2025 (24 minuti), del 19 marzo 2025 (32 minuti) e del 26 marzo 2025 (38 minuti). Le contestiamo inoltre di aver alterato la timbratura del 19 marzo 2025, facendo risultare un ingresso alle ore 08:02.
Ella potrà presentare le sue giustificazioni, anche verbalmente, entro 5 giorni dal ricevimento della presente.
Dott. Marco Zanetti, Direttore del personale"""]),
    ("B06_giustificazioni_Rinaldi", "pdf", ["""Al Direttore del personale di Alfa Logistica S.r.l.
Verona, 11 aprile 2025
Oggetto: giustificazioni alla contestazione del 7 aprile 2025
Il sottoscritto Giorgio Rinaldi dichiara: il 12 marzo sono arrivato in ritardo per un incidente sulla tangenziale, documentato dalla Polizia Locale. Il 19 marzo sono entrato regolarmente alle 08:02, come risulta dal cartellino, e non ho mai alterato alcuna timbratura. Il 26 marzo il turno era già stato anticipato alle 07:00, ma la comunicazione mi è stata data solo a voce dal caporeparto il giorno 10 marzo, e per iscritto non l'ho mai ricevuta prima del 24 marzo.
Giorgio Rinaldi"""]),
    ("B07_dichiarazione_collega_Neri", "pdf", ["""DICHIARAZIONE SCRITTA
La sottoscritta Paola Neri, dipendente di Alfa Logistica S.r.l. nel magazzino B dal 2017, dichiara che la comunicazione di servizio sul cambio del turno è stata affissa in bacheca solo il 25 marzo 2025 e che prima di quella data il caporeparto ne aveva parlato soltanto a voce, durante la pausa, ad alcuni colleghi.
Verona, 2 maggio 2025. Paola Neri"""]),
    ("B08_email_HR_falsificazione", "pdf", ["""Da: m.zanetti@alfalogistica.example
A: direzione@alfalogistica.example
Data: 14 aprile 2025
Oggetto: Rinaldi — proposta di licenziamento
Ritengo che Rinaldi abbia falsificato il cartellino del 19 marzo: il caporeparto Lodi afferma di non averlo visto in magazzino prima delle 08:30. Non abbiamo i filmati perché la telecamera dell'ingresso era guasta. Propongo il licenziamento per giusta causa (punto 9 del codice disciplinare). Marco Zanetti"""]),
    ("B09_lettera_licenziamento", "scan", ["""ALFA LOGISTICA S.R.L.
Verona, 18 aprile 2025
Al Sig. Giorgio Rinaldi, matricola 4471, inquadrato al livello 4 del CCNL Logistica
Oggetto: licenziamento per giusta causa
Esaminate le sue giustificazioni, ritenute non accoglibili, le comunichiamo il licenziamento per giusta causa con effetto immediato, per la gravità dei fatti contestati con lettera del 7 aprile 2025, in particolare l'alterazione della timbratura del 19 marzo 2025.
Dott. Marco Zanetti, Direttore del personale"""]),
    ("B10_ricevuta_raccomandata_licenziamento", "pdf", ["""POSTE — AVVISO DI RICEVIMENTO
Raccomandata n. 61847720931-4 spedita il 18 aprile 2025 da Alfa Logistica S.r.l.
Destinatario: Giorgio Rinaldi, Via Cavour 7, Verona.
Consegnata al destinatario in data 22 aprile 2025. Firma: G. Rinaldi"""]),
    ("B11_busta_paga_marzo", "pdf", ["""CEDOLINO PAGA — MARZO 2025
Dipendente: Giorgio Rinaldi, matricola 4471. Livello: 3 CCNL Logistica. Anzianità: 01/02/2019.
Retribuzione lorda mensile: € 2.140,00. Trattenute: multa ritardo 12/03 — € 0,00 (nessuna sanzione applicata).
Netto in busta: € 1.612,40."""]),
    ("B12_verbale_polizia_locale_12_marzo", "png", ["""POLIZIA LOCALE DI VERONA — ATTESTAZIONE
Si attesta che il giorno 12 marzo 2025 dalle ore 07:35 alle ore 08:40 la tangenziale sud, carreggiata ovest, è rimasta chiusa al traffico per un incidente stradale tra due mezzi pesanti all'altezza dello svincolo 4.
Verona, 9 aprile 2025. Il Comandante"""]),
    ("B13_impugnazione_stragiudiziale", "pdf", ["""Avv. Chiara Fontana — Foro di Verona
PEC ad: alfalogistica@pec.example
Verona, 9 giugno 2025
Oggetto: impugnazione del licenziamento del Sig. Giorgio Rinaldi ex art. 6 legge 604/1966
In nome e per conto del Sig. Rinaldi impugno il licenziamento intimato con lettera del 18 aprile 2025, ricevuta il 22 aprile 2025, in quanto illegittimo per insussistenza del fatto contestato e sproporzione della sanzione. Riservo ogni azione.
Avv. Chiara Fontana"""]),
    ("B14_nota_avv_Fontana_termini", "pdf", ["""NOTA INTERNA — pratica Rinaldi
Verona, 10 giugno 2025
Impugnazione stragiudiziale inviata a mezzo PEC il 9 giugno 2025 e consegnata lo stesso giorno (ricevuta di consegna in fascicolo). Prossimo adempimento: deposito del ricorso al Tribunale di Verona in funzione di giudice del lavoro nel termine di legge decorrente dall'impugnazione.
Elementi: cartellino del 19 marzo (08:02), comunicazione di servizio 14/2025 datata 17 marzo, dichiarazione Neri, attestazione Polizia Locale per il 12 marzo.
Avv. Chiara Fontana"""]),
    ("B15_email_Lodi_versione", "eml", ["""Da: s.lodi@alfalogistica.example
A: m.zanetti@alfalogistica.example
Data: 13 aprile 2025
Oggetto: Rinaldi 19 marzo
Marco, confermo che il 19 marzo non ho visto Rinaldi al suo posto prima delle 08:30, ma ero in riunione al piano di sopra fino alle 08:20. Stefano"""]),
]
