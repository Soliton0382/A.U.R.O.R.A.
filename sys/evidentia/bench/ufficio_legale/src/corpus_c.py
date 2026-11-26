# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Matter C (invented): Condominio Via dei Tigli 18, Verona — water leaks from the roof terrace. All fictitious.
A trap for matter isolation: a resident named Luca Ferri (no relation to matter A's Ferri Meccanica)."""

AMM = "Studio Amministrazioni Bellini — amministratore del Condominio Via dei Tigli 18, Verona"

MILLESIMI = [("int. 1", "Rossi Mario", 88, "presente"), ("int. 2", "Luca Ferri", 92, "presente"),
             ("int. 3", "Gialli Anna", 75, "presente"), ("int. 4", "Elena Bassi", 81, "assente"),
             ("int. 5", "Conti Paolo", 110, "presente"), ("int. 6", "Sartori Giulia", 96, "presente per delega"),
             ("int. 7", "Moro Franco", 70, "assente"), ("int. 8", "Valli Teresa", 126, "presente"),
             ("int. 9", "Dal Bosco Ugo", 105, "assente"), ("int. 10", "Pesce Irene", 157, "assente")]
_present = sum(m for _, _, m, s in MILLESIMI if s.startswith("presente"))    # 587

DOCS = [
    ("C01_regolamento_condominio", "pdf", ["""REGOLAMENTO DEL CONDOMINIO VIA DEI TIGLI 18 — VERONA (estratto)
Art. 15 — Lastrico solare. Il lastrico solare è di proprietà comune. Le spese di manutenzione straordinaria sono ripartite per due terzi tra tutti i condomini in proporzione ai millesimi di proprietà e per un terzo a carico dei titolari dell'uso esclusivo, ove esistente.
Art. 21 — Assemblea. L'assemblea è convocata dall'amministratore con avviso inviato almeno 5 giorni prima della data fissata per l'adunanza, a mezzo raccomandata o PEC."""]),
    ("C02_tabella_millesimi", "pdf", ["TABELLA MILLESIMALE DI PROPRIETÀ\n" + "\n".join(f"{i} — {n}: {m} millesimi" for i, n, m, _ in MILLESIMI) + "\nTotale: 1000 millesimi"]),
    ("C03_segnalazione_Bassi_infiltrazioni", "pdf", ["""Alla cortese attenzione dell'amministratore
Verona, 3 febbraio 2025
Sono Elena Bassi, proprietaria dell'interno 4 all'ultimo piano. Da metà gennaio dal soffitto della camera da letto e del bagno filtra acqua a ogni pioggia. Ho dovuto spostare i mobili e ho già fatto fare un preventivo per il ripristino: € 6.200,00. Chiedo un sopralluogo urgente e il risarcimento dei danni.
Elena Bassi"""]),
    ("C04_perizia_Moretti", "pdf", ["""PERIZIA TECNICA — Ing. Davide Moretti, Ordine degli Ingegneri di Verona n. 3307
Committente: Condominio Via dei Tigli 18. Data del sopralluogo: 21 marzo 2025. Data della relazione: 2 aprile 2025.
Oggetto: infiltrazioni nell'appartamento interno 4.
Accertamenti: la guaina bituminosa del lastrico solare presenta fessurazioni diffuse e distacchi lungo il perimetro; lo scarico pluviale nord-est risulta ostruito. Umidità rilevata nel solaio dell'interno 4: 18% (valore normale inferiore al 5%).""", """Conclusioni: la causa delle infiltrazioni è da attribuire al deterioramento della guaina impermeabilizzante del lastrico solare comune, aggravato dall'ostruzione dello scarico pluviale. Si esclude un'origine dagli impianti dell'interno 4.
Intervento consigliato: rifacimento completo dell'impermeabilizzazione (circa 260 mq) e pulizia degli scarichi. Stima dei danni all'interno 4: € 4.800,00.
Ing. Davide Moretti"""]),
    ("C05_preventivo_Impermeabilizzazioni_Adige", "pdf", ["""IMPERMEABILIZZAZIONI ADIGE S.R.L. — PREVENTIVO N. 55/2025
Data: 10 aprile 2025. Cliente: Condominio Via dei Tigli 18, Verona.
Rimozione guaina esistente, fornitura e posa di doppia guaina ardesiata su 260 mq, rifacimento scossaline, pulizia scarichi: € 38.600,00 + IVA 10%.
Validità dell'offerta: 60 giorni. Durata dei lavori: 25 giorni lavorativi."""]),
    ("C06_convocazione_assemblea", "pdf", [f"""{AMM}
Verona, 28 aprile 2025
AVVISO DI CONVOCAZIONE DELL'ASSEMBLEA STRAORDINARIA
L'assemblea è convocata in prima convocazione il 9 maggio 2025 alle ore 7:00 e in seconda convocazione il giorno 12 maggio 2025 alle ore 18:30, presso la sala comune, per deliberare sul seguente ordine del giorno: 1) approvazione dei lavori di rifacimento dell'impermeabilizzazione del lastrico solare e del relativo preventivo; 2) ripartizione della spesa; 3) richiesta di risarcimento della condomina dell'interno 4.
L'amministratore, Rag. Paolo Bellini"""]),
    ("C07_verbale_assemblea_12_maggio", "pdf", [f"""VERBALE DI ASSEMBLEA STRAORDINARIA — CONDOMINIO VIA DEI TIGLI 18
Il giorno 12 maggio 2025 alle ore 18:30, in seconda convocazione, presso la sala comune, si è riunita l'assemblea. Presiede il Sig. Paolo Conti, segretario il Rag. Paolo Bellini.
Sono presenti, in proprio o per delega, condomini rappresentanti 612 millesimi su 1000.
Punto 1: l'assemblea approva i lavori di rifacimento dell'impermeabilizzazione secondo il preventivo n. 55/2025 di Impermeabilizzazioni Adige S.r.l. per € 38.600,00 + IVA. Voti favorevoli: 6 condomini; contrari: nessuno.""", """Punto 2: la spesa è ripartita interamente in base ai millesimi di proprietà, senza applicazione dell'art. 15 del regolamento.
Punto 3: l'assemblea respinge la richiesta di risarcimento della Sig.ra Bassi, ritenendo che i danni derivino dall'impianto idraulico dell'interno 4.
Il Sig. Luca Ferri (int. 2) dichiara a verbale che a suo avviso la Sig.ra Bassi «ha lasciato aperto il lucernario per settimane».
La seduta è tolta alle ore 20:10. Il Presidente Paolo Conti — Il Segretario Paolo Bellini"""]),
    ("C08_foglio_presenze_assemblea", "scan", ["FOGLIO PRESENZE — ASSEMBLEA DEL 12 MAGGIO 2025\n" + "\n".join(
        f"{i} — {n} — {m} millesimi — {s}" for i, n, m, s in MILLESIMI) + f"\nTotale millesimi presenti o rappresentati: {_present}"]),
    ("C09_invio_verbale_assenti", "pdf", [f"""{AMM}
Verona, 20 maggio 2025
Ai condomini assenti all'assemblea del 12 maggio 2025 (interni 4, 7, 9, 10)
Trasmetto a mezzo PEC e raccomandata copia del verbale dell'assemblea straordinaria del 12 maggio 2025.
Per la Sig.ra Elena Bassi (int. 4): PEC consegnata il 20 maggio 2025.
L'amministratore, Rag. Paolo Bellini"""]),
    ("C10_lettera_avv_Bassi_contestazione", "pdf", ["""Avv. Roberto Gatti — Foro di Verona
PEC all'amministratore — Verona, 5 giugno 2025
Oggetto: Condominio Via dei Tigli 18 — delibera del 12 maggio 2025
Per conto della Sig.ra Elena Bassi contesto la delibera: (i) il punto 2 viola l'art. 15 del regolamento; (ii) il punto 3 è smentito dalla perizia dell'Ing. Moretti, che esclude un'origine dagli impianti dell'interno 4. Chiedo il risarcimento dei danni quantificati in € 6.200,00 secondo il preventivo della mia assistita. Mi riservo l'impugnazione della delibera nei termini di legge.
Avv. Roberto Gatti"""]),
    ("C11_email_amministratore_risposta", "pdf", ["""Da: bellini@amministrazioni.example
A: gatti@pec-avvocati.example
Data: 9 giugno 2025
Oggetto: Via dei Tigli 18
Egregio Avvocato, l'assemblea si è espressa. Le faccio presente che il condomino Ferri sostiene che la Sig.ra Bassi abbia lasciato aperto il lucernario: è una sua dichiarazione, di cui non ho riscontri. Rag. Paolo Bellini"""]),
    ("C12_preventivo_Bassi_ripristino", "png", ["""EDILCASA DI MARCHI LUCA — PREVENTIVO
Verona, 28 gennaio 2025. Cliente: Elena Bassi, Via dei Tigli 18 int. 4.
Rifacimento intonaci camera e bagno, trattamento antimuffa, tinteggiatura, sostituzione parquet danneggiato (12 mq): totale € 6.200,00 IVA inclusa."""]),
    ("C13_mediazione_istanza", "docx", ["""ISTANZA DI MEDIAZIONE — Organismo di mediazione forense di Verona
Parte istante: Elena Bassi. Parte convocata: Condominio Via dei Tigli 18. Oggetto: impugnazione della delibera del 12 maggio 2025 e risarcimento danni. Depositata il 13 giugno 2025."""]),
]
