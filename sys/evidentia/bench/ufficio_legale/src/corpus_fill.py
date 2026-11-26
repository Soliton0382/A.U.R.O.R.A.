# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Distractors (invented): documents of the same three matters' files that look alike but carry other numbers — other
contracts with a penalty, other dismissals, other assemblies — so that a search must find the right page."""

FILL_A = [
    ("A30_contratto_manutenzione_2024-031", "pdf", ["""CONTRATTO DI MANUTENZIONE N. 2024/031
Tra Ferri Meccanica S.r.l. e Tecnoservice Garda S.r.l. Oggetto: manutenzione programmata dei compressori. Canone annuo € 9.600,00 + IVA. Art. 6 — Penale: in caso di intervento oltre 48 ore dalla chiamata è dovuta una penale di € 150,00 per ogni giorno di ritardo. Foro competente: Mantova. Rezzato, 8 gennaio 2024."""]),
    ("A31_ordine_acquisto_vernici_2025", "pdf", ["""ORDINE DI ACQUISTO N. OA-2025-219 — Ferri Meccanica
Fornitore: Colorificio Benacense S.p.A. Articolo: vernice a polvere poliestere RAL 9010, 1.200 kg. Prezzo € 7,40/kg. Consegna richiesta: 30 maggio 2025. Data ordine: 12 maggio 2025."""]),
    ("A32_DDT_1190_vernici", "pdf", ["""DOCUMENTO DI TRASPORTO N. 1190 — Colorificio Benacense
Destinatario: Ferri Meccanica S.r.l., Rezzato. Merce: vernice a polvere RAL 9010, 48 sacchi da 25 kg. Data di consegna: 28 maggio 2025."""]),
    ("A33_fattura_Tecnoservice_2025-15", "pdf", ["""FATTURA N. 15/2025 — Tecnoservice Garda S.r.l.
Cliente: Ferri Meccanica S.r.l. Canone manutenzione I semestre 2025: imponibile € 4.800,00, IVA € 1.056,00, totale € 5.856,00. Scadenza pagamento: 31 marzo 2025."""]),
    ("A34_email_offerta_concorrente", "pdf", ["""Da: commerciale@verniciaturaitalia.example
A: a.ferri@ferrimeccanica.example
Data: 20 febbraio 2025
Oggetto: offerta linee di verniciatura
Vi proponiamo tre linee modello VI-700 a € 171.000,00 + IVA, consegna in 90 giorni, penale per ritardo dell'1% settimanale fino al 5%."""]),
    ("A35_verbale_cda_ferri_marzo", "pdf", ["""VERBALE DEL CONSIGLIO DI AMMINISTRAZIONE — FERRI MECCANICA S.R.L.
Seduta del 10 marzo 2025. Il consiglio autorizza il presidente Alberto Ferri a sottoscrivere con Lumen Impianti S.p.A. il contratto per tre linee di verniciatura, per un importo non superiore a € 190.000,00 + IVA, preferito all'offerta di Verniciatura Italia per l'affidabilità del fornitore."""]),
    ("A36_decreto_ingiuntivo_altro_2024", "pdf", ["""TRIBUNALE DI MANTOVA — DECRETO INGIUNTIVO N. 822/2024
Su ricorso di Ferri Meccanica S.r.l. si ingiunge a Officine Po S.n.c. di pagare € 23.400,00 entro 40 giorni dalla notifica. Mantova, 4 novembre 2024. Notificato il 15 novembre 2024; non opposto."""]),
    ("A37_listino_ricambi_Lumen", "pdf", ["""LUMEN IMPIANTI — LISTINO RICAMBI 2025
Cabina di verniciatura LX-900 completa: € 21.300,00. Quadro elettrico LX-900: € 8.900,00. Pistola automatica: € 1.150,00. Prezzi IVA esclusa, validi dal 1 gennaio 2025."""]),
]

FILL_B = [
    ("B30_contestazione_altro_dipendente", "pdf", ["""ALFA LOGISTICA S.R.L. — Verona, 3 febbraio 2025
Al Sig. Ivan Russo, matricola 3920
Oggetto: contestazione disciplinare — ritardo del 28 gennaio 2025 (20 minuti). Potrà presentare giustificazioni entro 5 giorni.
Dott. Marco Zanetti"""]),
    ("B31_rimprovero_scritto_Russo", "pdf", ["""ALFA LOGISTICA S.R.L. — Verona, 12 febbraio 2025
Al Sig. Ivan Russo: a seguito della contestazione del 3 febbraio 2025 le viene irrogato il rimprovero scritto ai sensi del punto 4 del codice disciplinare.
Dott. Marco Zanetti"""]),
    ("B32_comunicazione_servizio_13-2025", "pdf", ["""ALFA LOGISTICA — COMUNICAZIONE DI SERVIZIO N. 13/2025
Data: 3 marzo 2025. Destinatari: personale magazzino A. Dal 10 marzo 2025 il turno del magazzino A è posticipato alle ore 09:00–18:00. Il caporeparto, Sig.ra Monica Fabbri"""]),
    ("B33_cartellino_Neri_marzo", "pdf", ["""ALFA LOGISTICA S.R.L. — CARTELLINO PRESENZE MARZO 2025
Dipendente: Paola Neri, matricola 3011, reparto magazzino B.
19 marzo 2025 — entrata 07:56 — uscita 17:00
26 marzo 2025 — entrata 06:58 — uscita 16:00"""]),
    ("B34_accordo_aziendale_turni_2023", "pdf", ["""ACCORDO AZIENDALE SUI TURNI — ALFA LOGISTICA S.R.L. e RSU — 15 settembre 2023
Le variazioni dell'orario di turno sono comunicate per iscritto e affisse in bacheca con almeno 7 giorni di calendario di anticipo. In caso di urgenza il preavviso può essere ridotto a 48 ore con il consenso della RSU."""]),
    ("B35_licenziamento_altro_2023", "pdf", ["""ALFA LOGISTICA S.R.L. — Verona, 6 ottobre 2023
Al Sig. Dario Gallo, matricola 2210: licenziamento per giustificato motivo oggettivo per soppressione della posizione di carrellista notturno. Preavviso di 30 giorni come da CCNL. Dott. Marco Zanetti"""]),
    ("B36_cedolino_febbraio_Rinaldi", "pdf", ["""CEDOLINO PAGA — FEBBRAIO 2025
Dipendente: Giorgio Rinaldi, matricola 4471. Livello: 3. Retribuzione lorda mensile: € 2.140,00. Straordinari: 6 ore, € 95,40. Netto: € 1.688,10."""]),
]

FILL_C = [
    ("C30_bilancio_consuntivo_2024", "pdf", ["""CONDOMINIO VIA DEI TIGLI 18 — RENDICONTO CONSUNTIVO 2024
Spese ordinarie totali: € 21.480,00. Pulizia scale € 4.200,00; energia parti comuni € 2.950,00; manutenzione ascensore € 3.100,00; compenso amministratore € 3.600,00. Fondo lavori straordinari al 31/12/2024: € 7.800,00."""]),
    ("C31_verbale_assemblea_ordinaria_2025", "pdf", ["""VERBALE DI ASSEMBLEA ORDINARIA — 24 febbraio 2025
Presenti condomini per 702 millesimi. Approvato il consuntivo 2024 e il preventivo 2025 (€ 22.000,00). L'amministratore riferisce la segnalazione di infiltrazioni dell'interno 4 e propone un sopralluogo tecnico. Approvato all'unanimità dei presenti."""]),
    ("C32_lettera_Ferri_parcheggio", "pdf", ["""All'amministratore — Verona, 2 marzo 2025
Sono Luca Ferri, interno 2. Segnalo per l'ennesima volta che il posto auto n. 7 viene occupato da veicoli non autorizzati. Chiedo l'installazione di una sbarra. Luca Ferri"""]),
    ("C33_preventivo_concorrente_lastrico", "pdf", ["""COPERTURE VERONESI S.N.C. — PREVENTIVO N. 18/2025
Data: 14 aprile 2025. Impermeabilizzazione lastrico solare 260 mq con membrana sintetica: € 42.900,00 + IVA. Durata lavori 30 giorni."""]),
    ("C34_contratto_appalto_lavori", "pdf", ["""CONTRATTO DI APPALTO — Condominio Via dei Tigli 18 e Impermeabilizzazioni Adige S.r.l.
Verona, 26 maggio 2025. Corrispettivo € 38.600,00 + IVA 10%. Inizio lavori 9 giugno 2025, ultimazione entro 25 giorni lavorativi. Penale per ritardo: € 100,00 per ogni giorno. Garanzia decennale ex art. 1669 c.c."""]),
]
DOCS = FILL_A + FILL_B + FILL_C
