#!/usr/bin/env python3
"""
Elenca le porte TCP su cui il gateway si mette in ascolto.

Stampa una riga per porta: "<porta> <nome apparecchio>".
Usato da firewall-sync.sh per sapere cosa aprire nel firewall.

Sta in un file suo, e non dentro lo script di shell, perche' un heredoc
Python annidato in una sostituzione di comando -- porte="$(python - <<'EOF'
... EOF)" -- e' una costruzione che alcuni bash non riescono a leggere: il
parser perde la parentesi di chiusura attraverso il corpo del documento e
si ferma con "syntax error near unexpected token". Succedeva sul Raspberry
di uno studio mentre sul computer di sviluppo funzionava, quindi i test non
lo vedevano.

La lista dei device viene chiesta al gateway stesso, con la stessa funzione
che usa lui per decidere cosa aprire: resolve_devices() unisce gateway.yaml
e config/devices/*.yaml. Leggere solo gateway.yaml significava non vedere
gli analizzatori aggiunti dalla pagina Analizzatori, che scrive nel
catalogo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("uso: _porte_in_ascolto.py <percorso gateway.yaml>",
              file=sys.stderr)
        return 2

    config = Path(argv[1]).resolve()
    if not config.is_file():
        print(f"configurazione non trovata: {config}", file=sys.stderr)
        return 1

    # config/devices/ viene cercato relativo alla cartella di lavoro: ci si
    # sposta nella radice dell'installazione, cioe' la nonna del file di
    # configurazione (<radice>/config/gateway.yaml).
    radice = config.parent.parent
    os.chdir(radice)
    if str(radice) not in sys.path:
        sys.path.insert(0, str(radice))

    try:
        from config.settings import load_config
        from src.devices.registry import resolve_devices
    except Exception as exc:
        print(f"codice del gateway non importabile da {radice}: {exc}",
              file=sys.stderr)
        return 1

    try:
        cfg = load_config(config)
    except Exception as exc:
        print(f"configurazione non valida: {exc}", file=sys.stderr)
        return 1

    viste: dict[int, str] = {}   # porta -> nome (una regola per porta)

    for d in resolve_devices(cfg):
        porta = getattr(d, "listen_port", None)
        if not porta:
            continue              # seriale: non c'e' niente da aprire
        try:
            p = int(porta)
        except (TypeError, ValueError):
            continue
        if 1 <= p <= 65535:
            viste.setdefault(p, d.name)

    # Anche la porta di ingresso del LOC-200, quando ascolta in HTTP.
    loc = getattr(cfg, "loc200", None)
    if loc is not None and str(getattr(loc, "connection_type", "")) == "http":
        porta_http = getattr(loc, "http_port", None)
        if porta_http:
            try:
                viste.setdefault(int(porta_http), "LOC-200 (HTTP)")
            except (TypeError, ValueError):
                pass

    for p in sorted(viste):
        print(p, viste[p])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
