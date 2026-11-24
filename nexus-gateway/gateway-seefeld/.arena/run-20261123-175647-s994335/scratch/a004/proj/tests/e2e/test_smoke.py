"""
End-to-end browser smoke test.

Log in as admin, visit every top-level page, assert no 5xx and expected content.

This is intentionally shallow (no forms filled) -- it's the safety net that
catches "did I break the login page again?" between deploys.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")


PAGES_UNDER_TEST = [
    ("/",                     "Dashboard"),
    ("/config",               "Configurazione"),
    ("/analyzers",            "Analizzatori"),
    ("/trace",                "Trace protocollo"),
    ("/dlq",                  "Dead-Letter"),
    ("/users",                "Gestione utenti"),
    ("/results",              "Risultati"),
    ("/logs",                 "Log"),
    ("/license",              "Licenza"),
    ("/settings",             "Impostazioni"),
    ("/support",              "supporto"),
    ("/devices/new",          "Aggiungi nuovo device"),
    ("/devices/edit/uc1000",  "Modifica device"),
    ("/devices/archive",      "Archivio device"),
]


@pytest.mark.parametrize("path,expected_text", PAGES_UNDER_TEST)
def test_page_loads(logged_in_page, base_url, path, expected_text):
    logged_in_page.goto(base_url + path)
    body = logged_in_page.content()
    assert expected_text.lower() in body.lower(), \
        f"Expected {expected_text!r} on {path}"


def test_health_json_public(page, base_url):
    page.goto(base_url + "/api/status/public")
    body = page.content()
    assert "operational" in body or "outage" in body


def test_metrics_endpoint_shape(logged_in_page, base_url):
    logged_in_page.goto(base_url + "/metrics")
    body = logged_in_page.content()
    assert "jerumednexus_up" in body
    assert "# HELP" in body


def test_login_rate_limit(page, base_url):
    """Six wrong logins should get rate-limited."""
    page.goto(base_url + "/login")
    for _ in range(6):
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "wrong-password")
        page.click("button[type='submit']")
    body = page.content()
    assert "riprova" in body.lower() or "troppi" in body.lower()
