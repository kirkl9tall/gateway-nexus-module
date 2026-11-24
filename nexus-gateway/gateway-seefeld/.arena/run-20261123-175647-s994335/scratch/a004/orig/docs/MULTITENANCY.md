# Multi-tenancy

Single-tenant è il default. Multi-tenant è **opt-in** e backward compatible.

## Quando servirebbe

- **Reseller / rivenditore**: gestisci N cliniche da un unico gateway
- **Ospedale universitario**: reparti isolati (chimica, ematologia, POCT)
- **Franchise di praxis**: 10 studi con lo stesso brand

## Come si attiva

1. Crea `config/tenants/<id>.yaml`:
   ```yaml
   id: praxis-zurich
   name: Praxis Dr. Meier Zurich
   contact: dr.meier@example.ch
   quota:
     max_devices: 20
     max_messages_day: 5000
   sending_facility: PRAXIS_MEIER
   ```

2. Setta `MULTITENANT=1` in `config/secrets.env` (o crea qualche file
   `config/tenants/*.yaml` — la presenza attiva il modo).

3. Restart: `sudo systemctl restart jerumednexus-gateway jerumednexus-webui`.

## Come funziona

- URL: `https://gateway/t/<tenant_id>/...` (invece di `https://gateway/...`)
- API: header `X-Tenant-Id: <tenant_id>`
- Utenti: campo `tenant_id` in `webui_users.json` (assente = admin globale)
- Log / DLQ / history: file separati per tenant
- Metrics Prometheus: label `tenant`

## Limiti dell'implementazione attuale (v1.2)

Ship in **modalità scaffolding**:
- Configurazione tenant + routing header ✅
- Isolamento log / DLQ ✅
- Isolamento config devices/targets ⚠️ ancora manuale
- Isolamento UI (URL prefix, dashboard filtrata) ⚠️ da completare in v1.3

Per il primo cliente reale multi-tenant, va completato il testing in staging.
