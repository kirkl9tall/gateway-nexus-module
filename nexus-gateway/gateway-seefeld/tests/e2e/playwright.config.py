"""
Playwright config for end-to-end browser tests.

Run:
    pip install playwright pytest-playwright
    playwright install chromium
    BASE_URL=http://127.0.0.1:8080 pytest tests/e2e/
"""
import os

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "DemoPassword123!")
