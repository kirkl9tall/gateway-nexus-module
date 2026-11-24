#!/usr/bin/env python3
"""
JerumedNexus Gateway  v1.0.0
LOCMEDT LOC-200 Biochemistry Analyzer → HL7 v2.5 → PIS/LIS

Usage:
    python main.py               # normale
    python main.py --debug       # modalità debug (molti più log)
    python main.py --test-parse  # testa il parser senza LOC-200 fisico
    python main.py --check       # verifica configurazione e poi esci
    LOG_LEVEL=DEBUG python main.py   # alternativa via variabile d'ambiente
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

BANNER = r"""
   _                                        _ _   _
  | | ___ _ __ _   _ _ __ ___   ___  __| | \ | |_____  ___   _ ___
  | |/ _ \ '__| | | | '_ ` _ \ / _ \/ _` |  \| / _ \ \/ / | | / __|
 _| |  __/ |  | |_| | | | | | |  __/ (_| | |\  |  __/>  <| |_| \__ \
(_)_|\___|_|   \__,_|_| |_| |_|\___|\__,_|_| \_|\___/_/\_\\__,_|___/
        JerumedNexus Gateway v1.1.4
        Laboratory analyzers -> HL7 v2.5 -> PIS/LIS
        Vitomed | curaMED | Aeskulap | Axenita | WinMed | DnaMed | Tomedo
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="JerumedNexus Gateway")
    p.add_argument("--debug",      action="store_true",
                   help="Abilita modalità debug (log dettagliati)")
    p.add_argument("--test-parse", action="store_true",
                   help="Testa il parser con un frame di esempio e poi esci")
    p.add_argument("--check",      action="store_true",
                   help="Verifica la configurazione e poi esci")
    p.add_argument("--reset-password", action="store_true",
                   help="Cancella la password admin del Web UI (richiede sudo)")
    p.add_argument("--config",     default="config/gateway.yaml",
                   help="Percorso file configurazione (default: config/gateway.yaml)")
    return p.parse_args()


def reset_password() -> int:
    """Delete the admin password hash + users file so the setup wizard re-runs."""
    files = [
        Path("config/webui_password.hash"),
        Path("config/webui_users.json"),
    ]
    removed = []
    for f in files:
        if f.exists():
            try:
                f.unlink()
                removed.append(str(f))
            except OSError as exc:
                print(f"ERROR: cannot remove {f}: {exc}", file=sys.stderr)
                return 1
    if removed:
        print("Removed:")
        for r in removed:
            print(f"  {r}")
        print()
        print("Restart the Web UI and open http://<pi>:8080 -- the setup wizard")
        print("will prompt for a new admin password.")
    else:
        print("Nothing to remove (no password files found).")
    return 0


def setup_logging(debug: bool = False, fmt: str = "text") -> None:
    from src.common.logging_setup import configure_logging
    level = "DEBUG" if debug else os.environ.get("LOG_LEVEL", "INFO").upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = "INFO"
    configure_logging(level=level, fmt=fmt)
    if debug or level == "DEBUG":
        logging.getLogger().info("DEBUG mode attivo — log dettagliati abilitati.")


def check_config(config_path: Path) -> bool:
    """Valida la configurazione e stampa un report. Returns True se OK."""
    log = logging.getLogger("loc200.check")
    ok  = True

    if not config_path.exists():
        log.error("File di configurazione non trovato: %s", config_path)
        log.error("Copia config/gateway.yaml.example → config/gateway.yaml e modifica.")
        return False

    try:
        from config.settings import load_config
        cfg = load_config(config_path)
    except Exception as exc:
        log.error("Errore nel parsing della configurazione: %s", exc, exc_info=True)
        return False

    log.info("Configurazione caricata da: %s", config_path)
    log.info("Connessione LOC-200: %s", cfg.loc200.connection_type.upper())

    if cfg.loc200.connection_type == "serial":
        port = Path(cfg.loc200.serial.port)
        if not port.exists():
            log.warning("Porta seriale non trovata: %s  (normale se LOC-200 non collegato)", port)
        else:
            log.info("Porta seriale: %s  ✓", port)

    enabled = [t for t in cfg.targets if t.enabled]
    disabled = [t for t in cfg.targets if not t.enabled]
    if not enabled:
        log.warning("Nessun target abilitato — i risultati verranno scartati!")
        ok = False
    else:
        log.info("Target abilitati (%d):", len(enabled))
        for t in enabled:
            if t.watch_folder:
                log.info("  [%s] file-drop → %s", t.name, t.watch_folder)
            elif t.host:
                log.info("  [%s] MLLP → %s:%s", t.name, t.host, t.port)
            else:
                log.warning("  [%s] nessun host né watch_folder configurato!", t.name)
                ok = False
    if disabled:
        log.info("Target disabilitati: %s", [t.name for t in disabled])

    log.info("Configurazione %s.", "OK ✓" if ok else "con AVVERTIMENTI")
    return ok


def test_parser() -> None:
    """Esegue il parser su un frame di esempio e stampa il risultato."""
    from src.adapters.loc200_reader import Loc200Reader
    import json

    sample_frame = (
        "Sample ID: | TEST001\nPatient ID: | PAZ123\nName: Bianchi Marco\n"
        "Age: 52\nGender: Male\nDisc Name: General Chemistry Kit 18\nLot ID: LOT-2024\n"
        "AST|38|DOWN|15-40|U/L\n"
        "ALT|22||7-35|U/L\n"
        "CHOL|6.20|UP|3.1-5.7|mmol/L\n"
        "HDL-C|1.05||1.16-1.42|mmol/L\n"
        "LDL-C|4.50|UP|<3.4|mmol/L\n"
        "GLU|5.8||3.9-6.1|mmol/L\n"
        "CRE|88||62-106|umol/L\n"
        "UA|380||208-428|umol/L\n"
        "K+|4.2||3.5-5.1|mmol/L\n"
        "Na+|141||136-145|mmol/L\n"
    ).encode()

    print("\n  Test parser LOC-200:")
    print("  " + "─" * 50)
    result = Loc200Reader._parse_frame(sample_frame)
    if not result:
        print("  ERRORE: parser non ha restituito risultati!")
        return
    print(f"  Sample ID  : {result['sample_id']}")
    print(f"  Patient ID : {result['patient_id']}")
    print(f"  Paziente   : {result['patient_name']}  età={result['age']}  sesso={result['gender']}")
    print(f"  Disco      : {result['disc_name']}  lotto={result['lot_id']}")
    print(f"  Analiti    : {len(result['observations'])}")
    print()
    for o in result["observations"]:
        flag = f"  [{o['flag']}] ← FUORI NORMA" if o["flag"] else ""
        ref  = f"  rif. {o['ref_low']}-{o['ref_high']}" if o["ref_low"] is not None else ""
        print(f"  {o['analyte']:<10} = {str(o['value']):<10} {o['unit']:<12}{ref}{flag}")
    print()


async def main() -> None:
    args = parse_args()
    setup_logging(debug=args.debug, fmt=os.environ.get("LOG_FORMAT", "text"))
    log = logging.getLogger("loc200.main")

    print(BANNER)

    # ── --reset-password ──────────────────────────────────────────────────────
    if args.reset_password:
        sys.exit(reset_password())

    # ── --test-parse ──────────────────────────────────────────────────────────
    if args.test_parse:
        test_parser()
        return

    # ── Carica configurazione ─────────────────────────────────────────────────
    config_path = Path(args.config)
    if not config_path.exists():
        log.error("File di configurazione non trovato: %s", config_path)
        log.error("Copia config/gateway.yaml.example → config/gateway.yaml e modifica.")
        sys.exit(1)

    # ── --check ───────────────────────────────────────────────────────────────
    if args.check:
        ok = check_config(config_path)
        sys.exit(0 if ok else 1)

    # ── Avvio normale ─────────────────────────────────────────────────────────
    from config.settings import load_config
    from src.gateway import Gateway

    try:
        config = load_config(config_path)
    except Exception as exc:
        log.critical("Impossibile caricare la configurazione: %s", exc, exc_info=True)
        sys.exit(1)

    # Override log level da --debug
    if args.debug:
        config.log_level = "DEBUG"

    gateway = Gateway(config)

    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        # Non-blocking: flag the gateway to wind down so run_forever() returns;
        # the real cleanup (drain + DLQ + save) runs in the finally: await stop().
        gateway.request_stop()

    # loop.add_signal_handler is POSIX-only. On Windows fall back to signal.signal().
    signals = [signal.SIGINT]
    if hasattr(signal, "SIGTERM"):
        signals.append(signal.SIGTERM)
    for sig in signals:
        try:
            loop.add_signal_handler(sig, _request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_: _request_stop())

    # SIGHUP -> hot reload of config (POSIX only)
    if hasattr(signal, "SIGHUP"):
        def _request_reload() -> None:
            log.info("SIGHUP received -- reloading config.")
            asyncio.create_task(gateway.reload_config())
        try:
            loop.add_signal_handler(signal.SIGHUP, _request_reload)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await gateway.start()
        await gateway.run_forever()
    except Exception as exc:
        log.critical("Errore fatale nel gateway: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        await gateway.stop()
        log.info("Gateway arrestato.")


if __name__ == "__main__":
    asyncio.run(main())
