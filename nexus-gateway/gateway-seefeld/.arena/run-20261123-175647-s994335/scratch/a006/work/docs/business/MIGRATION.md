# Migration guide — from competing middleware to JerumedNexus

Supported inbound migrations (the vendor helps you extract config):

## From Data Innovations Instrument Manager (IM)

1. Export IM's instrument definitions:
   ```
   File → Export → All instruments → XML
   ```
2. Run our converter:
   ```bash
   jerumednexus import --from=data-innovations \
       --input im_export.xml \
       --output config/devices/
   ```
3. Review the generated YAML files and enable each `enabled: true`.
4. Point the analyzers at the Pi (same serial cable) — no analyzer-side
   change needed.
5. Cut over the LIS receiver: change its expected sender host to the Pi.

## From HL7 Soup / Iguana Interface Engine

1. Export channel definitions as JSON.
2. Our importer maps each Iguana channel to a
   `config/devices/*.yaml` + a target section in `gateway.yaml`.
3. Custom Lua translation scripts are **not** ported automatically —
   we replicate them with our HL7 builder options (see the migration
   worksheet the vendor provides).

## From Roche IT Solution / cobas infinity

1. Roche exports are `.rif` files. Contact `support@jerumednexus.example`
   for the converter (partner-only, NDA required).
2. Or: enable dual-writing during the transition — Roche keeps sending
   to its middleware AND to the Pi. Compare 100 samples, then switch
   the LIS receiver.

## Cut-over checklist

- [ ] Backup old middleware config **and** database.
- [ ] Deploy Pi in **shadow mode**: same devices, output to a demo LIS.
- [ ] Compare 100 dispatches for byte-equivalent HL7 output.
- [ ] Schedule cut-over during a low-volume window (lunch, Saturday morning).
- [ ] Keep the old system running in shadow for 30 days.
- [ ] Cancel old vendor licence at the end of the 30-day window.

Typical migration project: **4–6 weeks elapsed**, **20–40 hours of
engineering** including 1 on-site day.
