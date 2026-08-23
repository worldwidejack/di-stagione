#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibratore: ricostruisce le finestre di stagionalità dai listini reali dei
mercati all'ingrosso di Milano e Genova (Osservaprezzi - Ministero delle Imprese,
dati Unioncamere/BMTI).

NON viene eseguito dal sito. Gira per conto suo una volta al mese e scrive due
file di PROPOSTA che un umano confronta col dataset in uso:

    dati/stagionalita_calcolata.json   <- la proposta, stessa forma del dataset vero
    dati/calibrazione.md               <- il referto leggibile, con i confronti

Il sito quotidiano legge SOLO dati/stagionalita.json. Se questo script si rompe,
il sito continua a funzionare come sempre.

Uso:
    python3 calibra.py                 # tutti gli anni disponibili
    python3 calibra.py --anni 2024 2025   # solo alcuni anni (per provare)
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

QUI = Path(__file__).parent
BASE = ("https://osservaprezzi.mise.gov.it/prezzi/livelli/"
        "prodotti-ortofrutticoli-all-ingrosso/mercati-italiani")
UA = "di-stagione/1.0 (progetto personale non commerciale; calendario di stagionalita)"

ANNI_DEFAULT = [2021, 2022, 2023, 2024, 2025, 2026]
SETTIMANE = [1, 3]
GRUPPI = ["FRUTTA", "ORTAGGI", "AGRUMI"]
# Un mercato per area. Milano indica spesso la regione d'origine, Genova quasi mai:
# per questo il segnale principale e' "origine italiana", non "origine regionale".
MERCATI = {"MILANO": "nord_italia", "GENOVA": "liguria"}

REGIONI = {
    "ABRUZZO", "BASILICATA", "CALABRIA", "CAMPANIA", "EMILIA ROMAGNA",
    "FRIULI VENEZIA GIULIA", "LAZIO", "LIGURIA", "LOMBARDIA", "MARCHE", "MOLISE",
    "PIEMONTE", "PUGLIA", "SARDEGNA", "SICILIA", "TOSCANA", "TRENTINO",
    "ALTO ADIGE", "UMBRIA", "VALLE D'AOSTA", "VENETO",
}
NORD = {"EMILIA ROMAGNA", "FRIULI VENEZIA GIULIA", "LIGURIA", "LOMBARDIA",
        "PIEMONTE", "TRENTINO", "ALTO ADIGE", "VALLE D'AOSTA", "VENETO"}

# Come si chiamano i prodotti nei listini -> il nostro id
SPECIE_A_ID = {
    "AGLI": "aglio", "ALBICOCCHE": "albicocche", "ARANCE": "arance",
    "ASPARAGI": "asparagi", "BASILICO": "basilico", "BIETOLE": "bietole",
    "CACHI": "cachi", "CARCIOFI": "carciofi", "CAROTE": "carote",
    "CASTAGNE": "castagne", "CAVOLFIORE": "cavolfiore", "CAVOLI BROCCOLI": "broccoli",
    "CAVOLI DI BRUXELLES": "cavolini", "CAVOLI VERZA": "verza", "CETRIOLI": "cetrioli",
    "CILIEGIE": "ciliegie", "CIPOLLE": "cipolle", "CLEMENTINE": "mandarini",
    "FAGIOLINI": "fagiolini", "FAVE": "fave", "FICHI": "fichi", "FINOCCHI": "finocchi",
    "FRAGOLE": "fragole", "FUNGHI SPONTANEI": "funghi", "KIWI": "kiwi",
    "LAMPONI": "lamponi", "LATTUGHE": "insalata", "LIMONI": "limoni",
    "MANDARINI": "mandarini", "MELE": "mele", "MELANZANE": "melanzane",
    "MELOGRANI": "melograno", "MELONI": "meloni", "MIRTILLI": "mirtilli",
    "MORE DI ROVO": "more", "NESPOLE": "nespole", "NOCI": "noci",
    "PATATE": "patate", "PEPERONI": "peperoni", "PERE": "pere", "PESCHE": "pesche",
    "NETTARINE": "pesche", "PISELLI": "piselli", "POMODORI": "pomodori",
    "PORRI": "porri", "RADICCHIO": "radicchio", "RUCOLA": "rucola",
    "SEDANI": "sedano", "SPINACI": "spinaci", "SUSINE": "susine",
    "UVA DA TAVOLA": "uva", "ZUCCHE": "zucca", "ZUCCHINE": "zucchine",
    "ANGURIE": "angurie", "COCOMERI": "angurie", "OLIVE": "olive",
}

RIGA = re.compile(r"<tr>(.*?)</tr>", re.S | re.I)
CELLA = re.compile(r'data-label="([^"]*)"[^>]*>([^<]*)<')


def scarica(anno, mese, settimana, mercato, gruppo, tentativi=3):
    url = (f"{BASE}?ANNO={anno}&MESE={mese}&SETTIMANA={settimana}"
           f"&f%5BMERCATO%5D={urllib.request.quote(mercato)}"
           f"&f%5BGRUPPO%5D={urllib.request.quote(gruppo)}")
    for n in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if n == tentativi - 1:
                print(f"  ! salto {mercato}/{gruppo} {anno}-{mese}s{settimana}: {e}",
                      file=sys.stderr)
                return ""
            time.sleep(2 * (n + 1))
    return ""


def righe(html):
    for blocco in RIGA.findall(html):
        celle = {k.strip(): v.strip() for k, v in CELLA.findall(blocco)}
        if celle.get("Specie"):
            yield celle


def italiana(origine):
    o = (origine or "").upper().strip()
    return o == "ITALIA" or o in REGIONI


def raccogli(anni):
    """Restituisce due strutture:
       visto[(area, mese, anno)]            -> True se quel listino aveva righe
       trovato[(id, area, mese, anno)]      -> insieme di (varieta, origine) italiane
    """
    visto = set()
    trovato = defaultdict(set)
    ignorate = defaultdict(int)
    totale = len(anni) * 12 * len(SETTIMANE) * len(MERCATI) * len(GRUPPI)
    fatte = 0

    for anno in anni:
        for mese in range(1, 13):
            for settimana in SETTIMANE:
                for mercato, area in MERCATI.items():
                    for gruppo in GRUPPI:
                        html = scarica(anno, mese, settimana, mercato, gruppo)
                        fatte += 1
                        if fatte % 50 == 0:
                            print(f"  {fatte}/{totale} pagine…", flush=True)
                        for c in righe(html):
                            visto.add((area, mese, anno))
                            specie = c["Specie"].upper()
                            pid = SPECIE_A_ID.get(specie)
                            if pid is None:
                                ignorate[specie] += 1
                                continue
                            if italiana(c.get("Origine")):
                                trovato[(pid, area, mese, anno)].add(
                                    (c.get("Varietà", ""), c.get("Origine", ""))
                                )
                        time.sleep(0.35)   # gentile col server del Ministero
    return visto, trovato, ignorate


def finestra(mesi_validi):
    """Dal set di mesi 'in stagione' ricava (inizio, fine) prendendo la sequenza
    contigua piu' lunga sul cerchio dell'anno. Restituisce None se vuoto."""
    if not mesi_validi:
        return None
    if len(mesi_validi) == 12:
        return (1, 12)
    migliore = (0, None)
    for partenza in mesi_validi:
        if (partenza - 2) % 12 + 1 in mesi_validi:
            continue              # non e' l'inizio di una sequenza
        lung, m = 0, partenza
        while m in mesi_validi and lung < 12:
            lung += 1
            m = m % 12 + 1
        if lung > migliore[0]:
            migliore = (lung, (partenza, (partenza + lung - 2) % 12 + 1))
    return migliore[1]


def calcola(visto, trovato, soglia=0.5):
    aree = sorted({a for (_, a, _, _) in trovato} | {a for (a, _, _) in visto})
    prodotti = sorted({p for (p, _, _, _) in trovato})
    esito = {}
    for pid in prodotti:
        for area in aree:
            quota, abbondanza = {}, {}
            for mese in range(1, 13):
                anni_visti = {y for (a, m, y) in visto if a == area and m == mese}
                if not anni_visti:
                    continue
                anni_ok = {y for y in anni_visti if trovato.get((pid, area, mese, y))}
                quota[mese] = len(anni_ok) / len(anni_visti)
                abbondanza[mese] = (
                    sum(len(trovato.get((pid, area, mese, y), ())) for y in anni_visti)
                    / len(anni_visti)
                )
            mesi_ok = {m for m, q in quota.items() if q >= soglia}
            f = finestra(mesi_ok)
            if not f:
                continue
            inizio, fine = f
            dentro = []
            m = inizio
            while True:
                dentro.append(m)
                if m == fine:
                    break
                m = m % 12 + 1
            picco = max(dentro, key=lambda x: abbondanza.get(x, 0))
            esito[(pid, area)] = {
                "mese_inizio": inizio, "mese_fine": fine, "picco": picco,
                "quota": quota, "abbondanza": abbondanza,
            }
    return esito


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anni", nargs="*", type=int, default=ANNI_DEFAULT)
    ap.add_argument("--soglia", type=float, default=0.5,
                    help="quota minima di anni in cui il prodotto dev'essere quotato")
    args = ap.parse_args()

    print(f"Scarico i listini per gli anni {args.anni}…", flush=True)
    visto, trovato, ignorate = raccogli(args.anni)
    print(f"Listini con dati: {len(visto)} | prodotti riconosciuti: "
          f"{len({p for (p, _, _, _) in trovato})}", flush=True)

    esito = calcola(visto, trovato, args.soglia)

    # dataset in uso, per il confronto
    attuale = json.loads((QUI / "dati" / "stagionalita.json").read_text("utf-8"))
    per_id = {p["id"]: p for p in attuale["prodotti"]}

    # 1) la proposta, nella stessa forma del dataset vero
    proposta = {"_nota": "PROPOSTA calcolata da calibra.py sui listini di Milano e "
                         "Genova. Non e' il file usato dal sito.",
                "prodotti": []}
    for pid in sorted({p for (p, _) in esito}):
        base = per_id.get(pid, {"id": pid, "nome": pid.title(), "emoji": "•",
                                "categoria": "?", "frase_inizio": "", "frase_picco": "",
                                "nutriente_eroe": ""})
        stagione = []
        for area in ("nord_italia", "liguria"):
            r = esito.get((pid, area))
            if r:
                stagione.append({"area": area, "mese_inizio": r["mese_inizio"],
                                 "mese_fine": r["mese_fine"], "picco": r["picco"]})
        proposta["prodotti"].append({**{k: v for k, v in base.items()
                                        if k != "stagione"}, "stagione": stagione})
    (QUI / "dati" / "stagionalita_calcolata.json").write_text(
        json.dumps(proposta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 2) il referto leggibile
    barra = lambda q: "".join("█" if q.get(m, 0) >= .8 else
                              "▓" if q.get(m, 0) >= .5 else
                              "░" if q.get(m, 0) > 0 else "·" for m in range(1, 13))
    out = ["# Referto di calibrazione", "",
           f"Anni analizzati: {args.anni} — soglia: {args.soglia:.0%} degli anni.", "",
           "La barra è l'anno, gennaio→dicembre. `█` quotato quasi sempre, ",
           "`▓` spesso, `░` raramente, `·` mai (con origine italiana).", ""]
    for area, titolo in (("nord_italia", "Nord Italia (mercato di Milano)"),
                         ("liguria", "Liguria (mercato di Genova)")):
        out += [f"## {titolo}", "",
                "| Prodotto | Andamento reale | Calcolato | In uso adesso | |",
                "|---|---|---|---|---|"]
        for pid in sorted({p for (p, a) in esito if a == area}):
            r = esito[(pid, area)]
            calc = f"{r['mese_inizio']}–{r['mese_fine']} (picco {r['picco']})"
            vecchio = "—"
            for s in per_id.get(pid, {}).get("stagione", []):
                if s["area"] == area:
                    vecchio = f"{s['mese_inizio']}–{s['mese_fine']} (picco {s['picco']})"
            segno = "" if vecchio == "—" else ("✓" if calc == vecchio else "⚠")
            nome = per_id.get(pid, {}).get("nome", pid)
            out.append(f"| {nome} | `{barra(r['quota'])}` | {calc} | {vecchio} | {segno} |")
        out.append("")
    if ignorate:
        out += ["## Specie nei listini che non sappiamo tradurre", "",
                "Se qualcuna vi interessa, si aggiunge a `SPECIE_A_ID` in `calibra.py`.", "",
                ", ".join(f"{k} ({v})" for k, v in
                          sorted(ignorate.items(), key=lambda x: -x[1])[:40]), ""]
    (QUI / "dati" / "calibrazione.md").write_text("\n".join(out), encoding="utf-8")

    print("Scritti dati/stagionalita_calcolata.json e dati/calibrazione.md")


if __name__ == "__main__":
    main()
