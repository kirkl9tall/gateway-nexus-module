"""
Verifica impianto — controlla in pochi secondi che la catena sia intera.

Ogni controllo qui nasce da un guasto vero, costato ore o giorni di diagnosi,
e tutti avevano lo stesso sintomo: NIENTE. Nessun errore, nessun log, i
referti semplicemente non arrivavano al gestionale.

  * il Sysmex XQ-320 inviava su una porta che il firewall scartava
  * lo stesso Sysmex era acceso in un catalogo che il gateway non leggeva
  * un salvataggio della pagina Configurazione cancellava il destinatario
  * MSH-6 veniva sovrascritto con MSH-4 e il gestionale non assegnava piu'

Un controllo non prova che tutto funzioni. Prova che i punti dove le cose si
rompono davvero sono a posto, e lo dice in italiano con il rimedio accanto.

Ogni esito e' uno di:
    "ok"         va bene
    "attenzione" funziona ma c'e' qualcosa da sapere
    "guasto"     qui i referti si fermano
    "ignoto"     non verificabile da qui (manca un permesso, un comando)
"""
from __future__ import annotations

import os
import shutil
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

OK = "ok"
ATTENZIONE = "attenzione"
GUASTO = "guasto"
IGNOTO = "ignoto"

_ORDINE = {GUASTO: 0, ATTENZIONE: 1, IGNOTO: 2, OK: 3}


@dataclass
class Esito:
    """Un singolo controllo, nella forma che la pagina puo' mostrare subito."""
    nome: str
    stato: str
    dettaglio: str = ""
    rimedio: str = ""
    dati: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"nome": self.nome, "stato": self.stato,
                "dettaglio": self.dettaglio, "rimedio": self.rimedio,
                "dati": self.dati}


def _carica(percorso: Path) -> Dict[str, Any]:
    try:
        return yaml.safe_load(percorso.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


# ── 1. Il gateway e' vivo e aggiorna il suo stato ─────────────────────────

def _secondi_dall_avvio() -> float | None:
    """Da quanto e' accesa la macchina. None se non si puo' sapere."""
    try:
        with open("/proc/uptime", encoding="ascii") as f:
            return float(f.read().split()[0])
    except Exception:
        return None


def controlla_servizio(stato_file: Path = Path("logs/status.json"),
                       eta_massima_s: float = 660.0,
                       avvio_recente_s: float = 180.0) -> Esito:
    """
    Il gateway riscrive status.json ogni cinque minuti, quindi un file molto
    vecchio di solito significa processo fermo o bloccato -- e intanto la
    pagina Panoramica continua a mostrare gli ultimi numeri come se fossero
    attuali.

    La soglia e' di undici minuti: due cicli mancati. Prima era di due
    minuti, costruita sull'idea sbagliata che il file venisse riscritto a
    ogni giro -- invece veniva scritto SOLO all'arrivo di un referto. In uno
    studio senza esami invecchiava all'infinito e questo controllo
    annunciava un blocco che non c'era.

    "Di solito", pero', non sempre: se la macchina e' stata spenta per venti
    ore, il file e' vecchio di venti ore e non c'e' niente di rotto. Prima
    questo controllo annunciava "il processo e' fermo o bloccato" anche in
    quel caso, mandando a cercare un guasto che non esisteva. Ora confronta
    con l'ora di accensione: cio' che conta non e' quanto e' vecchio il file,
    ma se il gateway ha scritto qualcosa DA QUANDO la macchina e' accesa.
    """
    if not stato_file.exists():
        return Esito("Servizio gateway", GUASTO,
                     "Il gateway non ha mai scritto il suo stato.",
                     "Avvialo: sudo systemctl start jerumednexus-gateway")

    eta = time.time() - stato_file.stat().st_mtime
    dall_avvio = _secondi_dall_avvio()

    # Il file e' piu' vecchio dell'accensione: e' un residuo di prima dello
    # spegnimento, il gateway non ha ancora scritto nulla in questa sessione.
    if dall_avvio is not None and eta > dall_avvio:
        if dall_avvio < avvio_recente_s:
            return Esito("Servizio gateway", ATTENZIONE,
                         f"La macchina e' accesa da {int(dall_avvio)} secondi "
                         "e il gateway non ha ancora scritto il suo stato. "
                         "Riprova fra un minuto.",
                         "Se persiste: sudo systemctl status jerumednexus-gateway",
                         {"eta_s": round(eta), "uptime_s": round(dall_avvio)})
        return Esito("Servizio gateway", GUASTO,
                     f"La macchina e' accesa da {int(dall_avvio // 60)} minuti "
                     "ma il gateway non ha mai scritto il suo stato: non e' "
                     "partito.",
                     "sudo systemctl status jerumednexus-gateway  "
                     "(poi: sudo journalctl -u jerumednexus-gateway -n 40)",
                     {"eta_s": round(eta), "uptime_s": round(dall_avvio)})

    if eta > eta_massima_s:
        return Esito("Servizio gateway", GUASTO,
                     f"Il gateway era attivo ma lo stato non si aggiorna da "
                     f"{int(eta // 60)} minuti: il processo si e' bloccato.",
                     "sudo systemctl restart jerumednexus-gateway",
                     {"eta_s": round(eta)})

    return Esito("Servizio gateway", OK,
                 f"Attivo, stato aggiornato {int(eta)} secondi fa.",
                 dati={"eta_s": round(eta)})


# ── 2. L'intestazione HL7 che il gestionale usa per assegnare ─────────────

def controlla_intestazione_hl7(cfg: Dict[str, Any]) -> List[Esito]:
    """
    MSH-4 e MSH-6 sono due cose diverse: da chi arriva il referto e a chi e'
    indirizzato. Una versione della pagina Configurazione copiava il primo
    nel secondo. Il gestionale riceveva i file, li leggeva, e non li
    assegnava piu' a nessun paziente. Due giorni di diagnosi.
    """
    hl7 = cfg.get("hl7") or {}
    esiti: List[Esito] = []

    mittente = str(hl7.get("sending_facility") or "").strip()
    destinatario = str(hl7.get("receiving_facility") or "").strip()
    applicazione = str(hl7.get("sending_application") or "").strip()

    if not applicazione:
        esiti.append(Esito("MSH-3 · Nome del sistema mittente", GUASTO,
                           "Non impostato.",
                           "Configurazione -> Identita HL7. Deve coincidere "
                           "con il nome dichiarato nel gestionale."))
    else:
        esiti.append(Esito("MSH-3 · Nome del sistema mittente", OK,
                           applicazione, dati={"valore": applicazione}))

    if mittente and mittente == destinatario:
        esiti.append(Esito("MSH-4 e MSH-6 · Mittente e destinatario", GUASTO,
                           f"Sono identici ({mittente}). MSH-4 e' da chi arriva "
                           "il referto, MSH-6 a chi e' indirizzato: se "
                           "coincidono il gestionale riceve i file ma non li "
                           "assegna ai pazienti.",
                           "Configurazione -> Identita HL7: rimetti il "
                           "destinatario corretto, di solito il nome del "
                           "medico.",
                           {"valore": mittente}))
    elif not mittente:
        esiti.append(Esito("MSH-4 · Studio mittente", ATTENZIONE,
                           "Non impostato.",
                           "Configurazione -> Identita HL7."))
    else:
        esiti.append(Esito("MSH-4 · Studio mittente", OK, mittente,
                           dati={"valore": mittente}))

    if not destinatario:
        esiti.append(Esito("MSH-6 · Destinatario del referto", GUASTO,
                           "Non impostato: il gestionale non sa a chi "
                           "assegnare i referti e li lascia in attesa.",
                           "Configurazione -> Identita HL7: inserisci il "
                           "destinatario, di solito il nome del medico."))
    elif mittente != destinatario:
        esiti.append(Esito("MSH-6 · Destinatario del referto", OK,
                           destinatario, dati={"valore": destinatario}))
    return esiti


# ── 3. Gli analizzatori configurati sono davvero raggiungibili ────────────

def _porta_in_ascolto(porta: int, host: str = "127.0.0.1",
                      timeout: float = 0.5) -> bool:
    """Qualcuno ascolta su questa porta in locale?"""
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            return True
    except OSError:
        return False


def controlla_analizzatori(cfg: Dict[str, Any]) -> List[Esito]:
    """
    Due guasti insieme: un analizzatore acceso solo nel catalogo, che il
    gateway ignorava, e una porta TCP che il firewall scartava in silenzio.
    """
    from config.settings import GatewayConfig
    from src.devices.registry import resolve_devices

    esiti: List[Esito] = []
    try:
        attivi = resolve_devices(GatewayConfig.model_validate(cfg))
    except Exception as exc:
        return [Esito("Analizzatori", GUASTO,
                      f"La configurazione non e' valida: {exc}",
                      "Correggila in Configurazione, poi riprova.")]

    if not attivi:
        return [Esito("Analizzatori", ATTENZIONE,
                      "Nessun analizzatore attivo.",
                      "Analizzatori -> accendi quelli collegati.")]

    for d in attivi:
        porta = getattr(d, "listen_port", None)
        seriale = getattr(d, "serial_port", None)
        nome = getattr(d, "display_name", None) or d.id

        if seriale:
            if Path(seriale).exists():
                esiti.append(Esito(f"Analizzatore · {nome}", OK,
                                   f"Collegato su {seriale}.",
                                   dati={"porta": seriale}))
            else:
                esiti.append(Esito(f"Analizzatore · {nome}", GUASTO,
                                   f"{seriale} non esiste: cavo staccato, "
                                   "apparecchio spento, o percorso sbagliato.",
                                   "Controlla il cavo USB, poi Analizzatori -> "
                                   "Rileva dispositivi.",
                                   {"porta": seriale}))
        elif porta:
            if _porta_in_ascolto(int(porta)):
                esiti.append(Esito(f"Analizzatore · {nome}", OK,
                                   f"In ascolto sulla porta {porta}.",
                                   dati={"porta": int(porta)}))
            else:
                esiti.append(Esito(f"Analizzatore · {nome}", GUASTO,
                                   f"Nessuno ascolta sulla porta {porta}. "
                                   "L'apparecchio puo' inviare quanto vuole: "
                                   "i dati non arrivano e nei log non compare "
                                   "niente.",
                                   "Riavvia il gateway; se persiste apri la "
                                   "porta nel firewall con sudo "
                                   "/opt/jerumednexus/scripts/firewall-sync.sh",
                                   {"porta": int(porta)}))
        else:
            esiti.append(Esito(f"Analizzatore · {nome}", ATTENZIONE,
                               "Ne' porta seriale ne' porta di ascolto "
                               "configurata.",
                               "Analizzatori -> modifica e indica come e' "
                               "collegato."))
    return esiti


# ── 4. I gestionali destinatari rispondono ────────────────────────────────

def controlla_destinatari(cfg: Dict[str, Any],
                          timeout: float = 3.0) -> List[Esito]:
    """
    Un salvataggio della pagina Configurazione poteva cancellare un
    destinatario, e il gateway smetteva di consegnare senza un errore.
    """
    destinatari = [t for t in (cfg.get("targets") or [])
                   if isinstance(t, dict) and t.get("enabled", True)]
    if not destinatari:
        return [Esito("Gestionali destinatari", GUASTO,
                      "Nessun destinatario attivo: i referti vengono letti "
                      "dagli analizzatori e non vanno da nessuna parte.",
                      "Configurazione -> Gestionali destinatari.")]

    esiti: List[Esito] = []
    for t in destinatari:
        nome = t.get("name", "?")
        tipo = str(t.get("type") or "")

        if t.get("watch_folder"):
            cartella = Path(str(t["watch_folder"]))
            etichetta = f"Gestionale · {nome} (cartella)"
            if not cartella.is_dir():
                esiti.append(Esito(etichetta, GUASTO,
                                   f"{cartella} non e' raggiungibile.",
                                   "Verifica che la condivisione di rete sia "
                                   "montata e che il percorso sia corretto."))
            elif not os.access(cartella, os.W_OK):
                esiti.append(Esito(etichetta, GUASTO,
                                   f"{cartella} esiste ma non e' scrivibile.",
                                   "Concedi la scrittura all'utente del "
                                   "gateway su quella cartella."))
            else:
                esiti.append(Esito(etichetta, OK, f"{cartella} scrivibile."))
            continue

        if tipo == "tomedo" or t.get("sftp_host"):
            host = t.get("sftp_host")
            porta = t.get("sftp_port") or 22
            etichetta = f"Gestionale · {nome} (SFTP)"
        else:
            host = t.get("host")
            porta = t.get("port")
            etichetta = f"Gestionale · {nome} (MLLP)"

        if not host or not porta:
            esiti.append(Esito(etichetta, GUASTO,
                               "Indirizzo o porta mancanti.",
                               "Configurazione -> Gestionali destinatari: "
                               "ricompila i campi e salva."))
            continue
        try:
            with socket.create_connection((str(host), int(porta)),
                                          timeout=timeout):
                esiti.append(Esito(etichetta, OK,
                                   f"{host}:{porta} risponde.",
                                   dati={"host": str(host),
                                         "porta": int(porta)}))
        except OSError as exc:
            esiti.append(Esito(etichetta, GUASTO,
                               f"{host}:{porta} non risponde ({exc}). "
                               "I referti si accumuleranno in coda.",
                               "Verifica che il server del gestionale sia "
                               "acceso e raggiungibile dalla rete dello "
                               "studio.",
                               {"host": str(host), "porta": int(porta)}))
    return esiti


# ── 5. C'e' spazio per scrivere ───────────────────────────────────────────

def controlla_spazio(percorso: Path = Path("."),
                     minimo_mb: int = 200) -> Esito:
    """Senza spazio il gateway non scrive piu' log, coda, ne' referti."""
    try:
        libero_mb = shutil.disk_usage(percorso).free // (1024 * 1024)
    except Exception as exc:
        return Esito("Spazio su disco", IGNOTO, str(exc))
    if libero_mb < minimo_mb:
        return Esito("Spazio su disco", GUASTO,
                     f"Solo {libero_mb} MB liberi: il gateway sta per non "
                     "poter piu' scrivere.",
                     "Libera spazio, oppure riduci la conservazione dei log.",
                     {"libero_mb": libero_mb})
    if libero_mb < minimo_mb * 5:
        return Esito("Spazio su disco", ATTENZIONE,
                     f"{libero_mb} MB liberi.",
                     "Tieni d'occhio la crescita dei log.",
                     {"libero_mb": libero_mb})
    return Esito("Spazio su disco", OK, f"{libero_mb} MB liberi.",
                 dati={"libero_mb": libero_mb})


# ── Esecuzione completa ───────────────────────────────────────────────────

def esegui(config_file: Path = Path("config/gateway.yaml"),
           stato_file: Path = Path("logs/status.json")) -> Dict[str, Any]:
    """
    Esegue tutti i controlli. Non solleva mai: un controllo che esplode
    diventa un esito "ignoto", perche' una verifica che si interrompe a meta'
    e' peggio di una che dice "questo non lo so".
    """
    cfg = _carica(config_file)
    esiti: List[Esito] = []

    passi = (
        ("Servizio gateway", lambda: [controlla_servizio(stato_file)]),
        ("Identita HL7",     lambda: controlla_intestazione_hl7(cfg)),
        ("Analizzatori",     lambda: controlla_analizzatori(cfg)),
        ("Destinatari",      lambda: controlla_destinatari(cfg)),
        ("Spazio su disco",  lambda: [controlla_spazio()]),
    )
    for nome, chiamata in passi:
        try:
            esiti.extend(chiamata())
        except Exception as exc:
            esiti.append(Esito(nome, IGNOTO,
                               f"Controllo non riuscito: {exc}",
                               "Segnalalo all'assistenza con i log."))

    peggiore = min((e.stato for e in esiti),
                   key=lambda s: _ORDINE.get(s, 9), default=OK)
    conteggio = {s: sum(1 for e in esiti if e.stato == s)
                 for s in (OK, ATTENZIONE, GUASTO, IGNOTO)}
    return {
        "stato_generale": peggiore,
        "conteggio": conteggio,
        "esiti": [e.to_dict() for e in esiti],
        "eseguito_alle": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
