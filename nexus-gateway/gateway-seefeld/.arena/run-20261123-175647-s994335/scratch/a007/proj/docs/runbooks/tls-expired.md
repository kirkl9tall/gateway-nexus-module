# Runbook: certificato TLS scaduto

## Symptom
- Browser mostra "certificato scaduto" o "not secure"
- Caddy log: `certificate expired`

## Impact
Medio — il cliente non può accedere alla Web UI in HTTPS.
Il gateway continua a funzionare in HTTP interno (127.0.0.1:8080).

## Diagnose

```bash
# Con Let's Encrypt (Caddy auto-renew)
sudo journalctl -u caddy | grep -i "renew\|expir\|certif" | tail -20

# Verifica cert corrente
echo | openssl s_client -connect <fqdn>:443 2>/dev/null | openssl x509 -noout -dates
```

## Mitigate

Force renew:
```bash
sudo systemctl restart caddy
sleep 30
# Se ancora scaduto:
sudo caddy reload --config /etc/caddy/Caddyfile
```

## Fix

Se Let's Encrypt rate-limit:
```bash
sudo systemctl stop caddy
sudo rm -rf /var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org-directory
sudo systemctl start caddy
```

Verifica che porte 80/443 siano aperte per il challenge:
```bash
sudo ufw status | grep -E "80|443"
```
