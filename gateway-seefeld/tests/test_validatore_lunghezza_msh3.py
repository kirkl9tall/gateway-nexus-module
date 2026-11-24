"""
Il validatore non deve rifiutare un nome che il gestionale accetta.

In HL7 2.2 e 2.3 i campi MSH-3 e MSH-5 sono ST con lunghezza 180. Il tipo HD,
e con esso il limite di 20 sul primo componente, arriva con la 2.3.1. Il
validatore applicava 20 a tutte le versioni.

Non e' un dettaglio teorico. Lo studio ha registrato in Tomedo il mittente
"SYSMEX XQ320 Haematologie" -- 25 caratteri. Il costruttore lo scriveva per
intero, come deve in 2.3, e questo validatore lo rifiutava:

    HL7 validation failed: MSH-3: exceeds max length (20 chars): 25 chars

Cinque tentativi di consegna falliti, referto finito in coda, e un messaggio
d'errore che citava una regola inesistente per quella versione. Il nome non si
poteva nemmeno accorciare, perche' doveva restare identico a quello
dichiarato nel gestionale.
"""
from __future__ import annotations


from src.hl7.validator import validate_hl7_message

CR = chr(13)
NOME_LUNGO = "SYSMEX XQ320 Haematologie"          # 25 caratteri


def _messaggio(versione: str, mittente: str = NOME_LUNGO) -> str:
    return CR.join([
        f"MSH|^~\\&|{mittente}|Altstetten|LIS|Dr. A Abuawad|20261007130155||"
        f"ORU^R01^ORU_R01|ABC123|P|{versione}|||NE|AL||8859/1",
        "PID||6895|6895||^|||||||||||||",
        "OBR|1|||6895^6895^L||20261007130155|20261007130155|||||||||||||||F",
        "OBX|1|ST|1988-5^CRP^LN|1|20.4|mg/L^mg/L^ISO+|||||F",
    ])


def _errori(rep, segmento: str) -> list:
    return [e for e in rep.errors if e.segment == segmento]


def test_il_nome_registrato_nel_gestionale_passa_in_2_3():
    """Il caso reale che bloccava le consegne."""
    rep = validate_hl7_message(_messaggio("2.3"))
    assert _errori(rep, "MSH-3") == [], [e.message for e in rep.errors]
    assert rep.is_valid, [e.message for e in rep.errors]


def test_vale_anche_per_la_2_2():
    rep = validate_hl7_message(_messaggio("2.2"))
    assert _errori(rep, "MSH-3") == []


def test_in_2_5_il_limite_stretto_resta():
    """Dalla 2.3.1 il tipo e' HD: il limite di 20 ha senso e va mantenuto."""
    rep = validate_hl7_message(_messaggio("2.5"))
    assert _errori(rep, "MSH-3") != [], "in 2.5 un MSH-3 di 25 caratteri va segnalato"


def test_in_2_3_1_il_limite_stretto_resta():
    rep = validate_hl7_message(_messaggio("2.3.1"))
    assert _errori(rep, "MSH-3") != []


def test_un_nome_corto_passa_in_tutte_le_versioni():
    for versione in ("2.2", "2.3", "2.3.1", "2.5"):
        rep = validate_hl7_message(_messaggio(versione, "LOC200"))
        assert _errori(rep, "MSH-3") == [], versione


def test_oltre_180_e_un_errore_anche_in_2_3():
    """Il limite si alza, non sparisce."""
    rep = validate_hl7_message(_messaggio("2.3", "X" * 200))
    assert _errori(rep, "MSH-3") != []


def test_il_messaggio_d_errore_cita_il_limite_giusto():
    """
    Diceva "max length (20 chars)" anche dove il limite era un altro: chi
    leggeva il log cercava una regola che per quella versione non esiste.
    """
    rep = validate_hl7_message(_messaggio("2.3", "X" * 200))
    assert any("180" in e.message for e in _errori(rep, "MSH-3")), \
        [e.message for e in rep.errors]


def test_anche_msh5_segue_la_versione():
    """MSH-5 ha lo stesso tipo e la stessa storia di MSH-3."""
    msg = _messaggio("2.3").replace("|LIS|", f"|{NOME_LUNGO}|")
    rep = validate_hl7_message(msg)
    assert _errori(rep, "MSH-5") == []


def test_costruttore_e_validatore_concordano():
    """
    Il difetto nasceva dal fatto che i due avevano regole diverse sulla
    stessa cosa. Se tornano a divergere, questo test cade.
    """
    from datetime import datetime

    from config.settings import HL7Config
    from src.hl7.builder import HL7Builder

    cfg = HL7Config(version="2.3", charset="8859/1", include_timezone=False,
                    sending_application="JMNX_GW", sending_facility="Altstetten",
                    receiving_application="LIS", receiving_facility="Dr. A Abuawad")
    msg = HL7Builder(cfg).build_oru_r01({
        "timestamp": datetime(2026, 10, 7, 13, 1, 55),
        "sample_id": "9094", "patient_id": "9094",
        "patient_name": "", "gender": "", "department": "",
        "disc_name": NOME_LUNGO, "lot_id": "", "device": NOME_LUNGO,
        "observations": [{"analyte": "CRP", "value": "20.4", "unit": "mg/L"}],
    })
    testo = msg.to_string()
    assert NOME_LUNGO in testo, "il costruttore ha troncato il nome"
    rep = validate_hl7_message(testo)
    assert rep.is_valid, (
        "il costruttore produce un messaggio che il validatore rifiuta: "
        f"{[e.message for e in rep.errors]}"
    )
