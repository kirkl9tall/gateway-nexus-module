"""
Doctor view of "Verifica impianto".

src/common/verifica_impianto.py runs the real checks and describes them for a
technician (MSH-6, ports, sudo commands). This module regroups the same
results into five plain questions a practice asks, each with one sentence and
one thing to do:

    gateway   Is the gateway on?
    machines  Can the machines reach it?
    software  Does the practice software answer?
    identity  Do results land on the right patient?
    storage   Is there room to keep results?

The technical lines stay available, unchanged, in the technician section.
"""
from __future__ import annotations

from typing import Any, Dict, List

LEVEL = {"ok": "good", "attenzione": "warning", "guasto": "critical", "ignoto": "neutral"}
_RANK = {"critical": 0, "warning": 1, "neutral": 2, "good": 3}

GROUPS = [
    ("gateway",  "Il gateway è acceso?"),
    ("machines", "Gli apparecchi arrivano al gateway?"),
    ("software", "Il software dello studio risponde?"),
    ("identity", "I risultati arrivano al paziente giusto?"),
    ("storage",  "C'è spazio per conservare i risultati?"),
]


def _group_of(nome: str) -> str:
    if nome.startswith("Servizio"):
        return "gateway"
    if nome.startswith("Analizzator"):
        return "machines"
    if nome.startswith(("Gestional", "Destinatari")):
        return "software"
    if nome.startswith(("MSH", "Identita")):
        return "identity"
    if nome.startswith("Spazio"):
        return "storage"
    return "gateway"


def _label(nome: str) -> str:
    """'Analizzatore · Sysmex XQ-320' → 'Sysmex XQ-320';
    'Gestionale · Tomedo (SFTP)' → 'Tomedo'."""
    if " · " not in nome:
        return ""
    label = nome.split(" · ", 1)[1]
    if label.endswith(")") and " (" in label:
        label = label.rsplit(" (", 1)[0]
    return label


def _sentence(group: str, level: str, e: Dict[str, Any], t) -> str:
    name = _label(e.get("nome", ""))
    usb = isinstance((e.get("dati") or {}).get("porta"), str)
    if level == "neutral":
        return t("Non è stato possibile controllarlo.")
    if group == "gateway":
        return {"good": t("Il gateway è acceso e funziona."),
                "warning": t("Il gateway si sta avviando. Riprova fra un minuto.")
                }.get(level, t("Il gateway non funziona."))
    if group == "machines":
        if not name:
            return t("Nessun apparecchio è attivo.")
        if level == "good":
            return t("{name}: collegato.", name=name) if usb else t("{name}: pronto a ricevere.", name=name)
        if level == "warning":
            return t("{name}: manca il tipo di collegamento.", name=name)
        return t("{name}: cavo USB non rilevato.", name=name) if usb \
            else t("{name}: il gateway non lo riceve.", name=name)
    if group == "software":
        if not name:
            return t("Nessun software dello studio è collegato.")
        return t("{name}: risponde.", name=name) if level == "good" \
            else t("{name}: non risponde.", name=name)
    if group == "identity":
        return t("I risultati sono indirizzati correttamente.") if level == "good" \
            else t("Il software dello studio potrebbe non assegnare i risultati ai pazienti.")
    if group == "storage":
        return {"good": t("C'è spazio sufficiente."),
                "warning": t("Lo spazio si sta esaurendo.")
                }.get(level, t("Spazio quasi esaurito: il gateway smetterà di salvare i risultati."))
    return e.get("nome", "")


def _todo(group: str, items: List[Dict[str, Any]], t) -> str:
    bad = [i for i in items if i["level"] in ("critical", "warning")]
    if not bad:
        return ""
    if group == "gateway":
        return t("Spegni e riaccendi il gateway (la scatola grigia). Se non basta, chiama l'assistenza.")
    if group == "machines":
        if any(i["usb"] for i in bad):
            return t("Controlla che il cavo USB sia inserito e che l'apparecchio sia acceso.")
        return t("Riavvia il gateway. Se l'apparecchio non arriva ancora, chiama l'assistenza.")
    if group == "software":
        if not any(i["name"] for i in bad):
            return t("Chiama l'assistenza per collegare il software dello studio.")
        return t("Controlla che il computer con il software dello studio sia acceso e in rete. Intanto i risultati restano nel gateway.")
    if group == "identity":
        return t("Chiama l'assistenza: serve una correzione nella configurazione.")
    return t("Chiama l'assistenza.")


def doctor_view(result: Dict[str, Any], t) -> Dict[str, Any]:
    """Regroup verifica_impianto.esegui() output for the doctor."""
    buckets: Dict[str, List[Dict[str, Any]]] = {g: [] for g, _ in GROUPS}
    for e in result.get("esiti") or []:
        group = _group_of(str(e.get("nome", "")))
        level = LEVEL.get(e.get("stato"), "neutral")
        buckets[group].append({
            "level": level,
            "name": _label(str(e.get("nome", ""))),
            "usb": isinstance((e.get("dati") or {}).get("porta"), str),
            "text": _sentence(group, level, e, t),
        })
    groups = []
    for key, question in GROUPS:
        items = buckets[key]
        if not items:
            continue
        worst = min((i["level"] for i in items), key=lambda lv: _RANK[lv])
        groups.append({"key": key, "question": t(question), "level": worst,
                       "items": items, "todo": _todo(key, items, t)})
    groups.sort(key=lambda g: _RANK[g["level"]])
    overall = min((g["level"] for g in groups), key=lambda lv: _RANK[lv], default="neutral")
    return {"level": overall, "groups": groups,
            "problems": sum(1 for g in groups if g["level"] in ("critical", "warning"))}
