# High availability & read replica

The gateway is **single-Pi first** — that fits 95% of clinics. For the
5% that need more, we support two topologies.

## Topology A — Active + hot spare (2 Pis)

Two Pis on the same LAN, both provisioned identically. **Leader election
via file lock** on a shared NFS mount, or via `etcd` if the site
already runs one.

```
   ┌── Analyzer ──┐
   │              │
   ▼              ▼
Pi-primary  Pi-standby     (leader-elected; only leader is active)
   │              │
   └──────┬───────┘
          ▼
        LIS
```

- **Failover time**: 5–10 s (leader lease renewal).
- **Data**: `history.db` is on the shared NFS. Standby has read access
  for reporting.
- **Config**: identical (Ansible provisioning), pinned to the same
  version.

Guide: [docs/CLUSTER.md](CLUSTER.md).

## Topology B — Read replica for BI

For clinics that want a real-time feed into a data warehouse (analytics,
patient population reports), enable the **event log replicator**:

```yaml
# gateway.yaml
replication:
  enabled: true
  destination: "postgresql://readonly@dw.clinic.example/lab"
  events: ["dispatch", "dlq_enter", "dlq_retry", "audit"]
  batch_size: 100
  batch_interval_seconds: 30
```

- Only **hashed patient IDs** are shipped (safety default).
- No HL7 body, no analyte values by default; enable
  `include_analytes: true` explicitly if your DW has BAA/DPA coverage.
- The replicator is **at-least-once** — the DW must dedupe on
  `event_uuid`.
- Failure to reach the DW does **not** block the primary dispatch path.
  Events buffer to `logs/replication_queue.db` (bounded 100 MB
  ring-buffer).

## Sizing

| Deployment | Pis | Analyzers | Notes |
|------------|-----|-----------|-------|
| Small praxis | 1 | 1–3 | Baseline. |
| Group praxis | 1 | 4–8 | Baseline; consider Pi 5. |
| Small clinic | 2 (HA) | 4–10 | Topology A. |
| Multi-site chain | N Pis + 1 fleet console | 10s–100s | See [FLEET-MGMT.md](FLEET-MGMT.md). |
| Central lab | 2 HA Pis + read replica | 5–20 | Topology A + B. |
| Large hospital | Helm on K8s | 20+ | [deploy/helm/](../deploy/helm/) chart. |
