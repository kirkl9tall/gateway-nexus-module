"""Playwright fixtures + shared helpers."""
from __future__ import annotations

import os
import pytest

# Skip the whole e2e module if Playwright / pytest-playwright not installed.
pytest.importorskip("playwright.sync_api")
pytest.importorskip("pytest_playwright")

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
ADMIN_USER = "admin"
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "DemoPassword123!")


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture
def logged_in_page(page, base_url):
    """Return a page authenticated as admin. Skips test if server unreachable."""
    page.set_default_timeout(5000)
    try:
        page.goto(base_url + "/login")
    except Exception:
        pytest.skip(f"Server not reachable at {base_url}")
    if page.locator("input[name='password']").count() == 0:
        pytest.skip("Login form not found -- setup may be required")
    page.fill("input[name='username']", ADMIN_USER)
    page.fill("input[name='password']", ADMIN_PASSWORD)
    page.click("button[type='submit']")
    page.wait_for_url(f"{base_url}/", timeout=5000)
    return page
