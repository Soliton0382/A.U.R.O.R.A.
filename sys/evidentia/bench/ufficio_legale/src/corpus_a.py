# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Matter A (invented): Ferri Meccanica S.r.l. against Lumen Impianti S.p.A., a supply contract. Every name, number
and event is fictitious. Each entry: (file stem, form, pages); form = pdf | scan | png | eml | docx."""

STUDIO = "Studio Legale Castelli & Rota — Via Mazzini 41, 25121 Brescia"

CONTRATTO = [
    """CONTRATTO DI FORNITURA N. 2025/114
Tra FERRI MECCANICA S.R.L., con sede in Via dell'Industria 12, Rezzato (BS), P.IVA 03918220987, in persona del legale rappresentante Sig. Alberto Ferri (di seguito «Committente»)
e LUMEN IMPIANTI S.P.A., con sede in Corso Europa 220, Milano, P.IVA 07724410158, in persona dell'amministratore delegato Dott.ssa Silvia Marchetti (di seguito «Fornitore»)
si conviene e si stipula quanto segue.
Art. 1 — Oggetto. Il Fornitore si obbliga a fornire al Committente n. 3 linee di verniciatura automatica modello LX-900, complete di quadro elettrico e software di gestione, conformi alla scheda tecnica allegata (Allegato A).
Art. 2 — Prezzo. Il prezzo complessivo della fornitura è fissato in € 184.500,00 (centottantaquattromilacinquecento/00) oltre IVA di legge, comprensivo di trasporto e installazione.
Art. 3 — Pagamento. Il pagamento avverrà per il 30% alla firma del presente contratto e per il restante 70% entro 30 giorni dal collaudo positivo, mediante bonifico bancario.""",
    """Art. 4 — Termine di consegna. Il Fornitore si obbliga a consegnare e installare le linee entro 60 (sessanta) giorni dalla data di sottoscrizione del presente contratto. Il termine è essenziale nell'interesse del Committente.
Art. 5 — Collaudo. Il collaudo sarà eseguito in contraddittorio entro 15 giorni dall'installazione; dell'esito sarà redatto verbale sottoscritto da entrambe le parti.
Art. 6 — Garanzia. Il Fornitore garantisce le linee per 24 mesi dal collaudo positivo contro vizi di progettazione, materiale e lavorazione.
Art. 7 — Penale. In caso di ritardo nella consegna rispetto al termine di cui all'art. 4, il Fornitore sarà tenuto a corrispondere al Committente una penale pari allo 0,5% del prezzo per ogni giorno di ritardo, fino a un massimo del 10% del prezzo complessivo, salvo il risarcimento del maggior danno.
Art. 8 — Forza maggiore. Nessuna delle parti sarà responsabile per ritardi dovuti a eventi di forza maggiore, purché comunicati per iscritto all'altra parte entro 5 giorni dal loro verificarsi.""",
    """Art. 9 — Recesso. Ciascuna parte potrà recedere dal contratto con preavviso scritto di almeno 90 giorni, da comunicarsi a mezzo PEC.
Art. 10 — Riservatezza. Le parti si impegnano a mantenere riservate le informazioni tecniche e commerciali scambiate.
Art. 11 — Legge applicabile. Il presente contratto è regolato dalla legge italiana.
Art. 12 — Foro competente. Per ogni controversia relativa al presente contratto sarà competente in via esclusiva il Foro di Brescia.
Letto, approvato e sottoscritto in Rezzato, il 14 marzo 2025.
Per Ferri Meccanica S.r.l.: Alberto Ferri        Per Lumen Impianti S.p.A.: Silvia Marchetti
Ai sensi degli artt. 1341 e 1342 c.c. le parti approvano specificamente gli artt. 4, 7, 8 e 12.""",
]

DOCS = [
    ("A01_contratto_fornitura_2025-114", "pdf", CONTRATTO),
    ("A02_allegato_A_scheda_tecnica", "pdf", ["""ALLEGATO A — SCHEDA TECNICA LINEA LX-900
Lunghezza linea: 18,4 m. Cabina di verniciatura a polveri con recupero. Forno di polimerizzazione a gas, potenza 240 kW. Trasportatore aereo a catena, velocità regolabile 0,5–4 m/min. Quadro elettrico IP54 con PLC e pannello operatore da 15 pollici. Software di gestione ricette con registro di produzione.
Consumi dichiarati: energia elettrica 62 kW, gas metano 21 Nm3/h a pieno regime.""", """Prove di accettazione previste al collaudo: spessore del film 60–80 micron su provino standard, aderenza secondo norma ISO 2409 classe 0–1, produttività minima 140 pezzi/ora per linea."""]),
    ("A03_bonifico_acconto_30", "pdf", ["""CONTABILE DI BONIFICO
Ordinante: Ferri Meccanica S.r.l. — Beneficiario: Lumen Impianti S.p.A.
Data esecuzione: 17 marzo 2025. Importo: € 67.527,00. Causale: acconto 30% contratto n. 2025/114 (prezzo € 184.500,00 + IVA 22% = € 225.090,00; 30% = € 67.527,00).
CRO 0884512276301."""]),
    ("A04_email_lumen_conferma_ordine", "pdf", ["""Da: ordini@lumenimpianti.example
A: acquisti@ferrimeccanica.example
Data: 18 marzo 2025 09:14
Oggetto: Conferma ordine contratto 2025/114
Gentili Signori, confermiamo l'ordine in oggetto. Prevediamo la consegna delle tre linee LX-900 entro la metà di maggio 2025, in linea con il termine contrattuale. Cordiali saluti, Ufficio Ordini Lumen Impianti."""]),
    ("A05_email_lumen_ritardo_componenti", "pdf", ["""Da: f.galli@lumenimpianti.example (Fabio Galli, responsabile di commessa)
A: a.ferri@ferrimeccanica.example
Data: 6 maggio 2025 17:40
Oggetto: Commessa 2025/114 — slittamento
Gentile Sig. Ferri, la informo che a causa di un ritardo del nostro subfornitore dei quadri elettrici la consegna slitterà di alcune settimane. Stiamo facendo il possibile per recuperare. Le daremo una data certa a breve. Fabio Galli."""]),
    ("A06_pec_diffida_ad_adempiere", "pdf", [f"""{STUDIO}
PEC a: lumenimpianti@pec.example
Brescia, 10 giugno 2025
Oggetto: Contratto di fornitura n. 2025/114 del 14 marzo 2025 — diffida ad adempiere ex art. 1454 c.c.
Scrivo in nome e per conto di Ferri Meccanica S.r.l. Il termine essenziale di consegna previsto dall'art. 4 del contratto è scaduto il 13 maggio 2025 senza che le linee siano state consegnate. Vi diffido ad adempiere entro e non oltre 15 giorni dal ricevimento della presente, avvertendo che, decorso inutilmente tale termine, il contratto si intenderà risolto di diritto, fatta salva l'applicazione della penale di cui all'art. 7 e il risarcimento del maggior danno.
Avv. Marta Castelli"""]),
    ("A07_pec_risposta_lumen_forza_maggiore", "pdf", ["""LUMEN IMPIANTI S.P.A. — Ufficio Legale
PEC a: castelli@pec-avvocati.example
Milano, 16 giugno 2025
Oggetto: Vs. diffida del 10 giugno 2025 — contratto n. 2025/114
Respingiamo la diffida. Il ritardo è dovuto a un evento di forza maggiore, lo sciopero nazionale dell'autotrasporto dal 28 aprile al 9 maggio 2025, che ha bloccato i componenti presso il nostro subfornitore. Precisiamo inoltre che le linee sono state consegnate presso lo stabilimento di Rezzato in data 20 giugno 2025, come risulterà dalla documentazione di trasporto. Nessuna penale è pertanto dovuta.
Avv. Giulio Ferretti, Direzione Affari Legali"""]),
    ("A08_DDT_3318_consegna", "scan", ["""DOCUMENTO DI TRASPORTO N. 3318
Mittente: Lumen Impianti S.p.A., Corso Europa 220, Milano
Destinatario: Ferri Meccanica S.r.l., Via dell'Industria 12, Rezzato (BS)
Causale: vendita — contratto 2025/114
Descrizione merce: n. 3 linee di verniciatura LX-900 in colli, n. 3 quadri elettrici
Data e ora inizio trasporto: 1 luglio 2025 ore 15:30
Data di consegna: 2 luglio 2025
Vettore: Trasporti Bergamini S.n.c.
Firma del destinatario per ricevuta: R. Bonetti (magazzino Ferri)"""]),
    ("A09_verbale_installazione", "pdf", ["""VERBALE DI FINE INSTALLAZIONE
In data 14 luglio 2025 presso lo stabilimento di Ferri Meccanica S.r.l. in Rezzato si dà atto che le tre linee LX-900 risultano installate e collegate. Presenti: per il Committente Ing. Carla Pedretti; per il Fornitore Sig. Fabio Galli.
Il Committente annota che la consegna è avvenuta il 2 luglio 2025 e formula riserva in merito al ritardo.
Firmato: Carla Pedretti, Fabio Galli"""]),
    ("A10_verbale_collaudo_negativo", "pdf", ["""VERBALE DI COLLAUDO N. 1
Data: 24 luglio 2025. Luogo: Rezzato (BS), stabilimento Ferri Meccanica.
Prove eseguite secondo l'Allegato A. Linea 1: produttività 146 pezzi/ora, spessore film 62–78 micron — conforme. Linea 2: produttività 131 pezzi/ora — NON conforme (minimo 140). Linea 3: aderenza classe 2 secondo ISO 2409 — NON conforme (richiesta classe 0–1).
Esito complessivo: collaudo NEGATIVO per le linee 2 e 3. Il Fornitore si impegna a intervenire entro 20 giorni.""", """Osservazioni del Fornitore: il Sig. Galli dichiara che la non conformità della linea 3 dipende dalla qualità della vernice fornita dal Committente e non da un vizio dell'impianto.
Osservazioni del Committente: l'Ing. Pedretti contesta tale dichiarazione e rileva che la vernice è quella indicata nella scheda tecnica approvata dal Fornitore.
Firmato: Carla Pedretti, Fabio Galli"""]),
    ("A11_fattura_77-2025", "pdf", ["""FATTURA N. 77/2025 — Lumen Impianti S.p.A.
Data: 3 luglio 2025. Cliente: Ferri Meccanica S.r.l.
Descrizione: fornitura e installazione n. 3 linee LX-900 — contratto 2025/114.
Imponibile: € 184.500,00. IVA 22%: € 40.590,00. Totale documento: € 225.090,00.
Già versato (acconto 30%): € 67.527,00. Saldo da pagare: € 157.563,00 entro 30 giorni dal collaudo positivo."""]),
    ("A12_nota_debito_lumen", "pdf", ["""NOTA DI DEBITO N. 12/2025 — Lumen Impianti S.p.A.
Data: 30 settembre 2025. Cliente: Ferri Meccanica S.r.l.
Riferimento: contratto 2025/114 — saldo fornitura.
Imponibile residuo dichiarato: € 148.500,00. Interessi di mora dal 24 agosto 2025.
Si invita al pagamento immediato."""]),
    ("A13_email_interna_ferri_produzione", "pdf", ["""Da: c.pedretti@ferrimeccanica.example
A: a.ferri@ferrimeccanica.example
Data: 29 luglio 2025
Oggetto: fermo produzione
Alberto, con le linee 2 e 3 ferme stiamo esternalizzando la verniciatura presso la Verniciature Gardesane: costo sostenuto finora € 11.240,00 (fatture allegate). Ti segnalo anche che il cliente Bresciani Arredi ha annullato un ordine da € 32.000 per i ritardi. Carla"""]),
    ("A14_fatture_terzista_gardesane", "pdf", ["""VERNICIATURE GARDESANE S.R.L. — riepilogo fatture a Ferri Meccanica
Fattura 401 del 21/07/2025: € 3.980,00. Fattura 417 del 25/07/2025: € 4.120,00. Fattura 425 del 28/07/2025: € 3.140,00.
Totale imponibile: € 11.240,00."""]),
    ("A15_verbale_riunione_5_settembre", "pdf", ["""VERBALE DI RIUNIONE
5 settembre 2025, sede Lumen Impianti, Milano. Presenti: Avv. Marta Castelli e Ing. Carla Pedretti (per Ferri Meccanica); Avv. Giulio Ferretti e Sig. Fabio Galli (per Lumen Impianti).
Lumen propone di sostituire la cabina della linea 3 entro il 15 ottobre 2025 e di riconoscere uno sconto di € 5.000,00 a tacitazione di ogni pretesa. Ferri Meccanica si riserva di rispondere entro il 12 settembre 2025.
Il Sig. Galli afferma che lo sciopero dell'autotrasporto è stato comunicato a Ferri «per telefono» ai primi di maggio; l'Avv. Castelli dichiara che nessuna comunicazione scritta è mai pervenuta."""]),
    ("A16_pec_rifiuto_proposta", "pdf", [f"""{STUDIO}
PEC a: lumenimpianti@pec.example
Brescia, 11 settembre 2025
Oggetto: proposta del 5 settembre 2025
La proposta non è accettabile. Ferri Meccanica chiede il pagamento della penale contrattuale massima, pari a € 18.450,00 (10% del prezzo), e il rimborso dei costi di verniciatura esterna sostenuti, pari a € 11.240,00, oltre al ripristino delle linee 2 e 3. In difetto si procederà in via giudiziale.
Avv. Marta Castelli"""]),
    ("A17_decreto_ingiuntivo_1543-2025", "scan", ["""TRIBUNALE DI BRESCIA — SEZIONE CIVILE
DECRETO INGIUNTIVO N. 1543/2025 (R.G. 6612/2025)
Il Giudice, letto il ricorso depositato da Lumen Impianti S.p.A. il 18 settembre 2025, ingiunge a Ferri Meccanica S.r.l. di pagare alla ricorrente la somma di € 157.563,00, oltre interessi e spese della procedura liquidate in € 2.100,00, entro 40 giorni dalla notifica, avvertendo che nello stesso termine può essere proposta opposizione.
Brescia, 26 settembre 2025. Il Giudice: Dott.ssa Laura Venturi"""]),
    ("A18_relata_notifica_decreto", "pdf", ["""RELATA DI NOTIFICA
Io sottoscritto Ufficiale Giudiziario, su richiesta di Lumen Impianti S.p.A., ho notificato il decreto ingiuntivo n. 1543/2025 del Tribunale di Brescia a Ferri Meccanica S.r.l., mediante consegna a mani del legale rappresentante Sig. Alberto Ferri, in Rezzato, il giorno 3 ottobre 2025.
L'Ufficiale Giudiziario"""]),
    ("A19_nota_studio_promemoria", "pdf", [f"""{STUDIO}
NOTA INTERNA — pratica Ferri/Lumen
Brescia, 6 ottobre 2025
Ricevuto il decreto ingiuntivo n. 1543/2025, notificato il 3 ottobre 2025. Valutare opposizione con domanda riconvenzionale per penale (art. 7) e danni. Raccogliere: DDT 3318, verbale di collaudo n. 1, fatture Gardesane. Chiedere al cliente la prova dell'ordine annullato da Bresciani Arredi.
Avv. Marta Castelli"""]),
    ("A20_email_bresciani_annullamento", "png", ["""Da: acquisti@brescianiarredi.example
A: commerciale@ferrimeccanica.example
Data: 22 luglio 2025
Oggetto: annullamento ordine 2025-088
Con riferimento al nostro ordine n. 2025-088 del 3 giugno 2025 per la verniciatura di 4.000 pannelli (valore € 32.000,00), vi comunichiamo l'annullamento per il mancato rispetto dei tempi di consegna annunciati. Distinti saluti, Ufficio Acquisti Bresciani Arredi."""]),
    ("A21_comunicato_sciopero_autotrasporto", "pdf", ["""COMUNICATO — Coordinamento nazionale autotrasportatori (documento pubblico, ritaglio stampa)
Fermo nazionale dell'autotrasporto proclamato dal 28 aprile al 2 maggio 2025. Il fermo si è concluso regolarmente il 2 maggio 2025 alle ore 24:00.""" ]),
    ("A22_email_galli_data_consegna", "eml", ["""Da: f.galli@lumenimpianti.example
A: a.ferri@ferrimeccanica.example
Data: 24 giugno 2025
Oggetto: data di consegna
Gentile Sig. Ferri, le confermo che il camion partirà da Milano il 1 luglio pomeriggio, consegna prevista il 2 luglio in mattinata. Fabio Galli"""]),
    ("A23_parere_preliminare_bozza", "docx", ["""BOZZA DI PARERE — riservato, coperto da segreto professionale
La penale massima è di € 18.450,00. Il comunicato dello sciopero indica una durata fino al 2 maggio, non al 9 maggio come sostenuto da Lumen. Nessuna comunicazione scritta di forza maggiore entro 5 giorni (art. 8)."""]),
]
