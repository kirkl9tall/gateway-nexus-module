#!/usr/bin/env bash
#
# Apre nel firewall le porte TCP su cui il gateway ascolta gli analizzatori.
#
# Serve perche' ufw e' in "default deny incoming": un analizzatore configurato
# nella WebUI con una porta nuova (es. il Sysmex XQ-320 su 5006) invia i dati,
# il kernel li scarta, e nei log del gateway non compare NULLA -- nessun
# errore, nessuna connessione. Sintomo identico a un cavo staccato.
#
# Va eseguito dall'installer e di nuovo, a mano, ogni volta che si aggiunge un
# analizzatore in rete dalla WebUI (che gira senza privilegi e non puo' farlo):
#
#     sudo /opt/jerumednexus/scripts/firewall-sync.sh
#
# Idempotente: ufw ignora una regola gia' presente.
set -euo pipefail

CONFIG="${1:-/opt/jerumednexus/config/gateway.yaml}"
RADICE="${INSTALL_DIR:-/opt/jerumednexus}"
QUI="$(cd "$(dirname "$0")" && pwd)"
ELENCO="$QUI/_porte_in_ascolto.py"

if ! command -v ufw >/dev/null 2>&1; then
    echo "ufw non installato -- niente da fare." >&2
    exit 0
fi
if [ ! -f "$CONFIG" ]; then
    echo "Configurazione non trovata: $CONFIG" >&2
    exit 0
fi

# Non basta che l'interprete esista: deve avere le librerie del gateway.
# Su alcuni sistemi "python3" c'e' ma e' uno stub, oppure e' il python di
# sistema senza pydantic -- sceglierlo faceva fallire l'estrazione in
# silenzio, e lo script rispondeva "Nessuna porta configurata" su un impianto
# che ne aveva.
PY_BIN=""
for _c in "$RADICE/.venv/bin/python" /opt/jerumednexus/.venv/bin/python python3 python; do
    if command -v "$_c" >/dev/null 2>&1 && "$_c" -c "import yaml, pydantic" >/dev/null 2>&1; then
        PY_BIN="$_c"
        break
    fi
done

# L'elenco delle porte lo produce _porte_in_ascolto.py, che chiede la lista
# dei device al gateway stesso. Sta in un file separato apposta: un heredoc
# Python dentro una sostituzione di comando e' una costruzione che alcuni
# bash non riescono a leggere, e si fermava con "syntax error near
# unexpected token" sul Raspberry mentre altrove funzionava.
porte=""
if [ -n "$PY_BIN" ] && [ -f "$ELENCO" ]; then
    porte="$("$PY_BIN" "$ELENCO" "$CONFIG" 2>/dev/null)" || porte=""
elif [ -z "$PY_BIN" ]; then
    echo "Attenzione: interprete Python del gateway non trovato." >&2
fi

if [ -z "$porte" ]; then
    # Ripiego: si legge la forma indentata di gateway.yaml e dei profili nel
    # catalogo. Incompleto, ma meglio di niente -- e copre anche il caso
    # "nessun analizzatore in ascolto".
    porte="$(cat "$CONFIG" "$RADICE"/config/devices/*.yaml 2>/dev/null \
             | grep -oE '^[[:space:]]*listen_port:[[:space:]]*[0-9]+' \
             | grep -oE '[0-9]+$' | sort -un | sed 's/$/ analizzatore/')" || porte=""
fi

if [ -z "$porte" ]; then
    echo "Nessuna porta di ascolto configurata."
    exit 0
fi

while read -r porta nome; do
    [ -n "$porta" ] || continue
    if ufw allow "$porta/tcp" comment "JerumedNexus $nome" >/dev/null 2>&1; then
        echo "Aperta $porta/tcp ($nome)"
    else
        echo "Impossibile aprire $porta/tcp ($nome)" >&2
    fi
done <<< "$porte"
