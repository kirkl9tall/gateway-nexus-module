"""
Gli script devono restare eseguibili e con fine riga Unix.

Un pacchetto creato leggendo la copia di lavoro su Windows conteneva
script con CRLF e senza bit di esecuzione: lo shebang diventava
"#!/bin/bash\r" e Linux cercava un interprete chiamato letteralmente
"bash\r". L'installazione si fermava con "command not found", un messaggio
che non suggerisce affatto la causa vera.

Il rimedio sta alla radice: git registra il bit di esecuzione (100755) e
.gitattributes impone i fine riga LF. Questi test impediscono che si
perdano di nuovo.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


RADICE = Path(__file__).resolve().parents[1]


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=RADICE, capture_output=True,
                          text=True, check=True).stdout


def _tracciati_con_shebang() -> list[tuple[str, str]]:
    """(modo, percorso) per ogni file tracciato che inizia con '#!'."""
    fuori = []
    for riga in _git("ls-files", "-s").splitlines():
        if not riga.strip():
            continue
        modo, _resto = riga.split(" ", 1)
        percorso = riga.split("\t", 1)[1]
        f = RADICE / percorso
        if not f.is_file():
            continue
        try:
            if f.read_bytes()[:2] != b"#!":
                continue
        except OSError:
            continue
        fuori.append((modo, percorso))
    return fuori


def test_ogni_script_con_shebang_e_eseguibile():
    non_eseguibili = [p for modo, p in _tracciati_con_shebang() if modo != "100755"]
    assert non_eseguibili == [], (
        "questi script hanno uno shebang ma git non li registra eseguibili; "
        "in un pacchetto estratto su Linux non partirebbero: "
        f"{non_eseguibili}"
    )


def test_gli_script_sono_memorizzati_con_fine_riga_unix():
    """
    Si controlla il contenuto COME LO MEMORIZZA GIT, non la copia di lavoro:
    su Windows la copia di lavoro ha CRLF ed e' corretto che l'abbia.
    """
    con_crlf = []
    for _modo, percorso in _tracciati_con_shebang():
        contenuto = subprocess.run(
            ["git", "show", f"HEAD:{percorso}"], cwd=RADICE,
            capture_output=True, check=False,
        ).stdout
        if b"\r\n" in contenuto:
            con_crlf.append(percorso)
    assert con_crlf == [], (
        "questi script sono memorizzati con fine riga Windows; lo shebang "
        f"diventa '#!/bin/bash\r' e Linux non trova l'interprete: {con_crlf}"
    )


def test_gitattributes_impone_lf():
    testo = (RADICE / ".gitattributes").read_text(encoding="utf-8")
    assert "eol=lf" in testo, (
        ".gitattributes non impone piu' i fine riga LF: i pacchetti creati "
        "da una copia di lavoro Windows tornerebbero inservibili su Linux"
    )


def test_install_e_firewall_sync_sono_eseguibili():
    """I due che servono davvero durante un'installazione."""
    modi = dict((p, m) for m, p in _tracciati_con_shebang())
    for atteso in ("scripts/install.sh", "scripts/firewall-sync.sh"):
        assert modi.get(atteso) == "100755", f"{atteso} non e' eseguibile"


# ── costruzioni che non tutti i bash sanno leggere ────────────────────────

def _script_di_shell() -> list[Path]:
    return [RADICE / p for p in _git("ls-files").split("\n")
            if p.strip().endswith(".sh")]


def test_nessun_heredoc_dentro_una_sostituzione_di_comando():
    """
    porte="$(python - <<'EOF' ... EOF)" e' sintatticamente valido per alcuni
    bash e un errore per altri: il parser perde la parentesi di chiusura
    attraverso il corpo del documento e si ferma con

        syntax error near unexpected token `||'

    E' successo sul Raspberry di uno studio mentre sul computer di sviluppo
    lo stesso file passava perfino `bash -n`, quindi i test non lo vedevano:
    l'installazione si fermava a meta' e la porta dell'analizzatore restava
    chiusa. Il codice Python va in un file suo e si chiama normalmente.
    """
    colpevoli = []
    for f in _script_di_shell():
        testo = f.read_text(encoding="utf-8", errors="replace")
        for n, riga in enumerate(testo.splitlines(), start=1):
            senza_commento = riga.split("#", 1)[0]
            if "$(" in senza_commento and "<<" in senza_commento:
                colpevoli.append(f"{f.relative_to(RADICE)}:{n}")
    assert colpevoli == [], (
        "heredoc dentro una sostituzione di comando: alcuni bash non lo "
        f"leggono e lo script si ferma con un errore di sintassi: {colpevoli}"
    )


def test_ogni_script_di_shell_passa_il_controllo_di_sintassi():
    """Minimo indispensabile: non garantisce la portabilita', ma la soglia."""
    import subprocess

    rotti = []
    for f in _script_di_shell():
        res = subprocess.run(["bash", "-n", str(f)],
                             capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            rotti.append(f"{f.relative_to(RADICE)}: {res.stderr.strip()}")
    assert rotti == [], rotti
