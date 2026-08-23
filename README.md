# Di Stagione

Una pagina web che dice cosa è di stagione **oggi**, in Nord Italia e in Liguria.
Si riscrive da sola ogni mattina. Non c'è un server: c'è un robot di GitHub che
ogni giorno rilegge il calendario, riscrive la pagina e la ripubblica.

## Come funziona, in tre righe

1. `dati/stagionalita.json` è il calendario: per ogni prodotto, in che mesi è di
   stagione nelle due aree e in che mese è al picco.
2. `genera.py` guarda che giorno è, legge il calendario e riscrive `index.html`
   usando la grafica di `template.html`.
3. `.github/workflows/aggiorna.yml` fa girare `genera.py` ogni mattina alle 6:00
   UTC (le 8:00 italiane d'estate) e ricommitta `index.html`. Vercel vede il
   commit nuovo e ripubblica il sito da solo.

## I file

| File | Cos'è |
|---|---|
| `dati/stagionalita.json` | Il calendario. **È qui che si aggiungono i prodotti.** |
| `template.html` | La grafica. Si può modificare senza toccare il Python. |
| `genera.py` | Il motore. Mette i dati dentro la grafica. |
| `index.html` | **Generato in automatico. Non modificarlo a mano**, viene sovrascritto. |
| `.github/workflows/aggiorna.yml` | La sveglia giornaliera. |

## Se qualcosa si rompe

**Il sito è fermo a qualche giorno fa.**
La pagina se ne accorge da sola e mostra un avviso in alto. Vai su GitHub →
scheda **Actions** e guarda se l'ultimo run è rosso. Se lo è, aprilo e leggi
l'errore.

**Voglio rilanciarlo subito senza aspettare domattina.**
GitHub → **Actions** → *Aggiorna la pagina* → bottone **Run workflow**.

**Voglio aggiungere un prodotto.**
Apri `dati/stagionalita.json`, copia un blocco esistente, cambia i valori.
I mesi sono numeri da 1 a 12. Le aree possibili sono solo `nord_italia` e
`liguria`. Salva e committa: la pagina si aggiorna al run successivo (o lancialo
a mano, vedi sopra).

**Voglio provare come sarà la pagina in un altro mese.**
Da terminale, nella cartella del progetto:

```bash
python3 genera.py --data 2026-12-01
```

Riscrive `index.html` come se fosse quel giorno. Ricordati di rilanciare
`python3 genera.py` senza `--data` prima di committare.

## Cosa NON c'è (e non è una dimenticanza)

Niente database, niente notifiche push, niente login, niente dati nutrizionali.
Sono cose della Fase 2. Il campo `nutriente_eroe` nel JSON è compilato ma non
viene usato: serve solo a non dover rifare il dataset più avanti.
