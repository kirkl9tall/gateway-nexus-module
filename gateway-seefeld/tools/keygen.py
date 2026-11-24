#!/usr/bin/env python3
"""
tools/keygen.py  —  Generatore e gestore chiavi licenza LOC-200 Connect
════════════════════════════════════════════════════════════════════════
Usare sul PC del RIVENDITORE — mai sul Raspberry Pi del cliente.

Funzioni:
  1. Genera nuova chiave (prima installazione)
  2. Rinnova chiave scaduta (dopo 365 giorni)
  3. Verifica una chiave esistente
  4. Stampa registro clienti

Variabile d'ambiente obbligatoria:
  LOC200_LICENSE_SECRET=<segreto-rivenditore>
  (deve essere identica a quella impostata sui Raspberry Pi dei clienti)
"""
import hashlib
import hmac
import json
import os
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

SECRET   = os.environ.get("LOC200_LICENSE_SECRET", "loc200-license-secret-2024")
LOG_FILE = Path(__file__).parent / "license_log.json"   # registro locale clienti


# ── Algoritmo chiave ──────────────────────────────────────────────────────────
def gen_key(device_serial: str, validity_days: int = 365) -> str:
    """
    Genera una chiave legata al seriale + periodo di validità.
    Formato: LOC200-XXXX-XXXX-YYYY-CCCCCCCC
      XXXX-XXXX = parti casuali
      YYYY      = anno di scadenza codificato (es. 2025 → 25VV)
      CCCCCCCC  = HMAC-SHA256(segreto, seriale:prefisso)[:8]
    """
    rand1 = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    rand2 = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    expiry_year = (datetime.now() + timedelta(days=validity_days)).strftime("%y")  # 2-digit year
    year_encoded = f"{expiry_year}VV"   # es. "25VV" per 2025

    prefix  = f"LOC200-{rand1}-{rand2}-{year_encoded}"
    payload = f"{device_serial.strip()}:{prefix}"
    chk     = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:8].upper()
    return f"{prefix}-{chk}"


def verify_key(device_serial: str, key: str) -> tuple[bool, str]:
    """
    Verifica una chiave. Restituisce (valida: bool, messaggio: str).
    Controlla sia la firma crittografica che la scadenza.
    """
    import re
    if not re.match(r"^LOC200-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{8}$", key):
        return False, "Formato chiave non valido"

    parts      = key.split("-")
    prefix     = "-".join(parts[:4])
    provided   = parts[4]
    payload    = f"{device_serial.strip()}:{prefix}"
    expected   = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:8].upper()

    if provided != expected:
        return False, "Firma crittografica non valida (seriale non corrispondente o chiave alterata)"

    # Controlla scadenza (campo YYYY = es. "25VV" → anno 2025)
    year_field = parts[3]  # es "25VV"
    if year_field.endswith("VV") and year_field[:2].isdigit():
        expiry_year = int("20" + year_field[:2])
        if expiry_year < datetime.now().year:
            return False, f"Chiave scaduta (anno di scadenza: {expiry_year})"

    return True, "Chiave valida"


# ── Registro clienti ──────────────────────────────────────────────────────────
def load_log() -> list:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except Exception:
            pass
    return []

def save_log(entries: list) -> None:
    LOG_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False))

def log_entry(serial: str, customer: str, key: str, validity_days: int, action: str) -> None:
    entries = load_log()
    entries.append({
        "date":          datetime.now().strftime("%Y-%m-%d %H:%M"),
        "action":        action,
        "customer":      customer,
        "serial":        serial,
        "key":           key,
        "validity_days": validity_days,
        "expires":       (datetime.now() + timedelta(days=validity_days)).strftime("%Y-%m-%d"),
    })
    save_log(entries)


# ── Menu principale ───────────────────────────────────────────────────────────
def print_header():
    print("\n" + "═" * 54)
    print("  LOC-200 Connect — Gestione Chiavi Licenza")
    print("═" * 54)

def menu_genera(action_label: str = "NUOVA LICENZA") -> None:
    print(f"\n  [{action_label}]")
    serial   = input("  Numero seriale RPi del cliente : ").strip()
    customer = input("  Nome cliente / studio          : ").strip()
    if not serial:
        print("  Errore: seriale obbligatorio."); return

    print("\n  Durata licenza:")
    print("    1. 365 giorni  (1 anno)  — standard")
    print("    2. 730 giorni  (2 anni)  — promozione")
    print("    3. 180 giorni  (6 mesi)  — prova")
    scelta = input("  Scelta [1]: ").strip() or "1"
    days_map = {"1": 365, "2": 730, "3": 180}
    validity = days_map.get(scelta, 365)
    expiry   = (datetime.now() + timedelta(days=validity)).strftime("%d/%m/%Y")

    key = gen_key(serial, validity)
    log_entry(serial, customer, key, validity, action_label)

    print("\n  ┌─────────────────────────────────────────────────┐")
    print(f"  │  Cliente  : {customer[:44]:<44}")
    print(f"  │  Seriale  : {serial[:44]:<44}")
    print(f"  │  Validità : {validity} giorni  (scade il {expiry})")
    print("  │")
    print(f"  │  CHIAVE   : {key}")
    print("  └─────────────────────────────────────────────────┘")
    print("\n  Comunicare la chiave al cliente.")
    print("  Il cliente: WebUI → Licenza → Attiva Licenza\n")


def menu_rinnovo() -> None:
    print("\n  [RINNOVO LICENZA SCADUTA]")
    print("  Il cliente apre WebUI → Licenza e comunica il numero seriale.")
    menu_genera("RINNOVO")


def menu_verifica() -> None:
    print("\n  [VERIFICA CHIAVE]")
    serial = input("  Numero seriale RPi : ").strip()
    key    = input("  Chiave da verificare: ").strip().upper()
    ok, msg = verify_key(serial, key)
    status = "VALIDA ✓" if ok else "NON VALIDA ✗"
    print(f"\n  Risultato: {status}")
    print(f"  Dettaglio: {msg}\n")


def menu_registro() -> None:
    entries = load_log()
    if not entries:
        print("\n  Nessun cliente nel registro.\n")
        return
    print(f"\n  {'Data':<17} {'Azione':<12} {'Cliente':<28} {'Scadenza':<12}")
    print("  " + "─" * 72)
    for e in entries[-20:]:  # ultimi 20
        print(f"  {e['date']:<17} {e['action']:<12} {e['customer'][:27]:<28} {e['expires']:<12}")
    print(f"\n  Totale registrazioni: {len(entries)}")
    print(f"  File log: {LOG_FILE}\n")


def main():
    print_header()

    if SECRET == "loc200-license-secret-2024":
        print("\n  ⚠️  ATTENZIONE: stai usando il segreto di default!")
        print("  Impostare: export LOC200_LICENSE_SECRET=<tuo-segreto-privato>")
        print("  prima di emettere chiavi per i clienti reali.\n")

    print("\n  1. Genera nuova chiave (prima installazione)")
    print("  2. Rinnova chiave scaduta")
    print("  3. Verifica una chiave esistente")
    print("  4. Registro clienti")
    print("  0. Esci")

    scelta = input("\n  Scelta: ").strip()
    if   scelta == "1": menu_genera()
    elif scelta == "2": menu_rinnovo()
    elif scelta == "3": menu_verifica()
    elif scelta == "4": menu_registro()
    elif scelta == "0": print()
    else: print("  Scelta non valida.\n")


if __name__ == "__main__":
    main()
