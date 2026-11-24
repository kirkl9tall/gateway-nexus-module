# Runbook: password admin dimenticata / setup ripetuto

## Symptom
- Impossibile fare login su Web UI
- "Password errata" ripetuta

## Impact
Basso finché il gateway funziona, ma non puoi modificare la config.

## Fix (via CLI locale)

```bash
sudo -u jerumednexus jerumednexus reset-password
```

Poi apri la Web UI: parte il wizard di setup e crei una nuova password.

## Fix (via SSH senza CLI)

```bash
sudo rm /opt/jerumednexus/config/webui_password.hash
sudo rm /opt/jerumednexus/config/webui_users.json
sudo systemctl restart jerumednexus-webui
```

## Prevenire

- Salva la password in un password manager clinica-wide
- Crea più utenti admin ridondanti (Web UI → Utenti)
- Documenta la procedura per lo staff IT del cliente
