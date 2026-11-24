# Cluster mode (active/standby)

For hospitals or high-availability requirements.
Not needed for single-clinic deployments.

## Architettura

```
                  ┌─────────────┐
                  │  NFS / SMB  │  /mnt/jerumednexus/
                  │   share     │  (config, logs, history.db)
                  └──────┬──────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
   ┌────▼────┐                       ┌────▼────┐
   │  Pi #1  │   heartbeat            │  Pi #2  │
   │ LEADER  │◄──────via lock─────────►│ STANDBY │
   └────┬────┘                       └─────────┘
        │
     dispatch
        │
   ┌────▼──────────────┐
   │  PIS / LIS        │
   └───────────────────┘
```

## Setup

1. Setup NFS/SMB share accessible da entrambi i Pi. Monta su:
   `/mnt/jerumednexus/config/` e `/mnt/jerumednexus/logs/`

2. Su entrambi i Pi:
   ```bash
   sudo systemctl stop jerumednexus-gateway
   sudo mv /opt/jerumednexus/config /opt/jerumednexus/config.local-backup
   sudo ln -s /mnt/jerumednexus/config /opt/jerumednexus/config
   sudo ln -s /mnt/jerumednexus/logs   /opt/jerumednexus/logs
   ```

3. Setta `CLUSTER_MODE=1` in `config/secrets.env` su entrambi i Pi.

4. Fai partire il gateway. Il primo che parte diventa LEADER; il secondo
   partirà in STANDBY (visibile nel log come `not-leader, standby`).

## Failover

- Se il LEADER muore o perde la rete verso l'NFS, l'STANDBY se ne accorge
  entro 15 secondi e diventa LEADER automaticamente.
- Nessun intervento manuale.
- Durante il failover: fino a 15s di potenziali messaggi ritardati (i
  reader restano attivi solo sul leader).

## Test

```bash
# Sul LEADER
sudo systemctl stop jerumednexus-gateway

# Sul STANDBY, entro 15s dovresti vedere:
# INFO stealing stale lock from <old-leader>
# INFO promoted to LEADER
```

## Limiti conosciuti

- Storage NFS deve essere robusto (single point of failure) — considera
  storage replicato (Ceph, GlusterFS) per veri deployment ospedalieri.
- Split-brain possibile se la partizione di rete separa i due Pi ma
  entrambi vedono l'NFS. Mitigazione: usa un lock manager esterno
  (Consul, etcd) invece del file lock per deployment >2 nodi.
