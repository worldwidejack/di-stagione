#!/usr/bin/env python3
"""
Di Stagione — generatore della pagina.

Legge dati/stagionalita.json, guarda che giorno e' oggi, e riscrive index.html.
Non ha nessuna dipendenza: gira con Python liscio.

Uso:
    python3 genera.py                 # usa la data di oggi
    python3 genera.py --data 2026-10-01   # finge che sia un altro giorno (per i test)
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ROMA = ZoneInfo("Europe/Rome")
except Exception:  # pragma: no cover - fallback se manca il database dei fusi
    ROMA = None

QUI = Path(__file__).parent
DATI = QUI / "dati" / "stagionalita.json"
TEMPLATE = QUI / "template.html"
USCITA = QUI / "index.html"

AREE = {"nord_italia": "Nord Italia", "liguria": "Liguria"}
LUOGO = {"nord_italia": "", "liguria": " in Liguria"}

MESI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def oggi() -> date:
    if ROMA is not None:
        return datetime.now(ROMA).date()
    return date.today()


def mese_dentro(inizio: int, fine: int, mese: int) -> bool:
    """True se `mese` cade nella finestra inizio..fine, gestendo il giro d'anno
    (es. 11 -> 2 significa novembre, dicembre, gennaio, febbraio)."""
    if inizio <= fine:
        return inizio <= mese <= fine
    return mese >= inizio or mese <= fine


def stato(prodotto: dict, area: str, mese: int):
    """Restituisce None se il prodotto non e' di stagione in quell'area,
    altrimenti un dizionario con i flag novita/picco."""
    for s in prodotto.get("stagione", []):
        if s.get("area") != area:
            continue
        if not mese_dentro(s["mese_inizio"], s["mese_fine"], mese):
            continue
        picco = s.get("picco")
        # distanza dal picco misurata DENTRO la finestra di stagione,
        # cosi' funziona anche per le stagioni che scavalcano l'anno (es. 10 -> 4)
        dal_inizio = lambda x: (x - s["mese_inizio"]) % 12
        delta = dal_inizio(picco) - dal_inizio(mese) if picco else 0
        return {
            "novita": mese == s["mese_inizio"],
            "picco": mese == picco,
            "delta_picco": delta,
            "mese_picco": picco,
        }
    return None


def mese_prossimo(mese: int) -> int:
    return mese % 12 + 1


def in_arrivo(prodotto: dict, area: str, mese: int) -> bool:
    """True se il prodotto NON e' di stagione adesso ma parte il mese prossimo."""
    if stato(prodotto, area, mese) is not None:
        return False
    for s in prodotto.get("stagione", []):
        if s.get("area") == area and s["mese_inizio"] == mese_prossimo(mese):
            return True
    return False


def frase(prodotto: dict, area: str, chiave: str) -> str:
    return prodotto.get(chiave, "").replace("{luogo}", LUOGO[area])


def card(prodotto: dict, st: dict) -> str:
    classi = ["card"]
    etichetta = ""
    if st["novita"]:
        classi.append("novita")
        etichetta = "novità"
    elif st["picco"]:
        classi.append("picco")
        etichetta = "al picco"
    else:
        d = st.get("delta_picco", 0)
        if d > 0:
            classi.append("prima")
            etichetta = f"picco a {MESI[st['mese_picco']]}"
        elif d < 0:
            classi.append("dopo")
            etichetta = f"picco era a {MESI[st['mese_picco']]}"
    badge = f'<span class="badge">{etichetta}</span>' if etichetta else ""
    return (
        f'<div class="{" ".join(classi)}">'
        f'<span class="emoji">{prodotto["emoji"]}</span>'
        f'<span><span class="nome">{prodotto["nome"]}</span>{badge}</span>'
        f"</div>"
    )


def card_arrivo(prodotto: dict) -> str:
    return (
        '<div class="card arrivo">'
        f'<span class="emoji">{prodotto["emoji"]}</span>'
        f'<span><span class="nome">{prodotto["nome"]}</span></span>'
        "</div>"
    )


def griglia(prodotti: list) -> str:
    if not prodotti:
        return ""
    return '<div class="griglia">' + "".join(card(p, s) for p, s in prodotti) + "</div>"


def sezione_area(dati: dict, area: str, mese: int) -> str:
    novita, picco, resto = [], [], []
    for p in dati["prodotti"]:
        st = stato(p, area, mese)
        if st is None:
            continue
        if st["novita"]:
            novita.append((p, st))
        elif st["picco"]:
            picco.append((p, st))
        else:
            resto.append((p, st))

    for gruppo in (novita, picco, resto):
        gruppo.sort(key=lambda x: (x[0]["categoria"], x[0]["nome"]))

    arrivo = sorted(
        [p for p in dati["prodotti"] if in_arrivo(p, area, mese)],
        key=lambda p: (p["categoria"], p["nome"]),
    )
    coda = ""
    if arrivo:
        celle = "".join(card_arrivo(p) for p in arrivo)
        coda = (
            f'<p class="gruppo-titolo">Sta per arrivare &middot; {MESI[mese_prossimo(mese)]}</p>'
            f'<div class="griglia arrivi">{celle}</div>'
        )

    if not (novita or picco or resto):
        return '<p class="vuoto">Questo mese qui non entra niente di nuovo. Succede.</p>' + coda

    pezzi = []
    if novita:
        pezzi.append(f'<p class="gruppo-titolo">Nuovi di {MESI[mese]}</p>{griglia(novita)}')
    if picco:
        pezzi.append(f'<p class="gruppo-titolo">Al picco</p>{griglia(picco)}')
    if resto:
        pezzi.append(f'<p class="gruppo-titolo">Anche di stagione</p>{griglia(resto)}')
    pezzi.append(coda)
    return "".join(pezzi)


def blocco_novita(dati: dict, mese: int) -> str:
    """Le frasi scritte a mano, per i prodotti che partono questo mese."""
    righe = []
    for p in dati["prodotti"]:
        for area in AREE:
            st = stato(p, area, mese)
            if st and st["novita"]:
                righe.append(f'<p class="frase">{frase(p, area, "frase_inizio")}</p>')
                break  # una riga per prodotto, il Nord ha la precedenza
    # al massimo tre frasi in cima: il resto si vede comunque nelle schede
    return "".join(righe[:3])


def genera(giorno: date) -> str:
    dati = json.loads(DATI.read_text(encoding="utf-8"))
    mese = giorno.month
    html = TEMPLATE.read_text(encoding="utf-8")
    sostituzioni = {
        "{{DATA_LUNGA}}": f"{GIORNI[giorno.weekday()]} {giorno.day} {MESI[mese]} {giorno.year}",
        "{{NOVITA}}": blocco_novita(dati, mese),
        "{{NORD}}": sezione_area(dati, "nord_italia", mese),
        "{{LIGURIA}}": sezione_area(dati, "liguria", mese),
        "{{GENERATO_ISO}}": giorno.isoformat(),
        "{{GENERATO_LEGGIBILE}}": f"{giorno.day} {MESI[mese]} {giorno.year}",
    }
    for chiave, valore in sostituzioni.items():
        html = html.replace(chiave, valore)

    rimasti = [c for c in sostituzioni if c in html]
    if rimasti:
        sys.exit(f"ERRORE: segnaposto non sostituiti nel template: {rimasti}")
    return html


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="finge una data, formato AAAA-MM-GG")
    parser.add_argument("--stdout", action="store_true", help="stampa invece di scrivere il file")
    args = parser.parse_args()

    giorno = date.fromisoformat(args.data) if args.data else oggi()
    html = genera(giorno)

    if args.stdout:
        print(html)
    else:
        USCITA.write_text(html, encoding="utf-8")
        print(f"index.html rigenerato per il {giorno.isoformat()}")


if __name__ == "__main__":
    main()
