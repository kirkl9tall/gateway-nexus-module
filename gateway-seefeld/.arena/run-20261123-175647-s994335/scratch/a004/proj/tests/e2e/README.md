# End-to-end browser tests

Uses Playwright (Chromium) to drive the real Web UI and verify each page loads.

## Local run

```bash
pip install playwright pytest-playwright
playwright install chromium

# Start the webui in one terminal
python -m flask --app webui.app run --host=127.0.0.1 --port=8080

# In another terminal
BASE_URL=http://127.0.0.1:8080 E2E_ADMIN_PASSWORD=changeme pytest tests/e2e/ -v
```

## In CI

Add a job in `.github/workflows/ci.yml`:

```yaml
- name: Install Playwright
  run: |
    pip install playwright pytest-playwright
    playwright install chromium --with-deps

- name: Start webui in background
  run: python -m flask --app webui.app run --host=127.0.0.1 --port=8080 &

- name: Run E2E
  env:
    BASE_URL: http://127.0.0.1:8080
    E2E_ADMIN_PASSWORD: ${{ secrets.E2E_ADMIN_PASSWORD }}
  run: pytest tests/e2e/
```
