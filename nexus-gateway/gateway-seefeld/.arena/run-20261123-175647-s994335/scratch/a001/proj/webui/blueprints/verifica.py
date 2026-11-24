"""
Verifica impianto — un pulsante che risponde a "sta funzionando davvero?".

La domanda ricorrente in ogni studio e' sempre la stessa: il gateway e'
acceso, la pagina mostra numeri verdi, ma i referti non compaiono nel
gestionale. Nessuno dei guasti che abbiamo davvero incontrato produceva un
errore visibile -- porta chiusa dal firewall, analizzatore acceso in un
catalogo ignorato, destinatario cancellato da un salvataggio, MSH-6
sovrascritto. Qui si controllano quei punti, uno per uno, in pochi secondi.

Endpoint:
    GET  /verifica            pagina con i risultati
    POST /api/verifica        esegue i controlli, restituisce JSON
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, session

from src.common.verifica_impianto import esegui
from src.security.audit import AuditEvent, audit
from webui.blueprints._helpers import client_ip, csrf_check, require_role

verifica_bp = Blueprint("verifica", __name__)


@verifica_bp.route("/verifica")
@require_role("viewer")
def pagina_verifica():
    # La pagina esce vuota e chiede i risultati via fetch: i controlli aprono
    # connessioni di rete con un timeout, e far aspettare il caricamento
    # darebbe l'impressione che la WebUI sia bloccata.
    return render_template("verifica.html")


@verifica_bp.route("/api/verifica", methods=["POST"])
@require_role("viewer")
def api_verifica():
    """
    Esegue i controlli. E' un POST perche' apre connessioni verso i
    gestionali: non e' un'azione senza effetti, e non va ripetuta da un
    precaricamento del browser. Aperta anche al ruolo viewer: il medico e'
    il primo a chiedersi "funziona?", e il controllo non modifica niente.
    """
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    risultato = esegui(config_file=Path("config/gateway.yaml"),
                       stato_file=Path("logs/status.json"))
    audit(AuditEvent.SERVICE_ACTION,
          actor=session.get("username", "?"), ip=client_ip(),
          detail={"azione": "verifica_impianto",
                  "esito": risultato["stato_generale"],
                  "conteggio": risultato["conteggio"]})
    # Doctor view: the same results as five plain questions, rendered
    # translated by the server. The technical list stays in `esiti`.
    from flask import render_template as _render
    from webui.check_view import doctor_view
    from webui.i18n import t
    semplice = doctor_view(risultato, t)
    html = _render("_check_result.html", ck=semplice, eseguito_alle=risultato.get("eseguito_alle", ""))
    return jsonify({"ok": True, **risultato, "semplice": semplice, "html": html})
