#!/usr/bin/env python3
"""
jerumednexus -- CLI for JerumedNexus Gateway.

Usage:
    jerumednexus status
    jerumednexus target list
    jerumednexus target test <name>
    jerumednexus dlq list [--limit N]
    jerumednexus dlq replay <control_id> [--targets a,b]
    jerumednexus device add            # interactive wizard
    jerumednexus device list
    jerumednexus discover              # USB + optional TCP scan
    jerumednexus users list
    jerumednexus users create <name> --role <viewer|operator|admin>
    jerumednexus trace [<device>] [--limit N]
    jerumednexus validate <hl7-file>
    jerumednexus sla <YYYY-MM> [--out DIR]
    jerumednexus reset-password
    jerumednexus reload

No stdlib-only design; no `click` dep. Uses argparse only.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_status(_args) -> int:
    p = Path("logs/status.json")
    if not p.exists():
        print("logs/status.json not found (gateway not started?)"); return 1
    d = json.loads(p.read_text())
    print(f"Running:  {d.get('running')}")
    print(f"Uptime:   {d.get('uptime_seconds')} s")
    print(f"Queue:    {d.get('queue_size')}/{d.get('queue_maxsize')}"
          f"  (full events: {d.get('queue_full_events', 0)})")
    print(f"Today:    {d.get('results_today')} OK, {d.get('errors_today')} errors")
    print(f"Total:    {d.get('results_total')}")
    print(f"Targets:  {[t['name'] for t in d.get('targets', [])]}")
    return 0


def _load_config():
    import yaml
    cfg_path = Path("config/gateway.yaml")
    if not cfg_path.exists():
        print("config/gateway.yaml not found", file=sys.stderr); sys.exit(1)
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


def cmd_target_list(_args) -> int:
    cfg = _load_config()
    for t in cfg.get("targets", []):
        flag = "on " if t.get("enabled") else "off"
        loc = t.get("host") or t.get("watch_folder") or t.get("sftp_host") or "?"
        print(f"[{flag}] {t.get('name'):<15} {t.get('type'):<20} -> {loc}")
    return 0


def cmd_target_test(args) -> int:
    from datetime import datetime
    from config.settings import GatewayConfig, HL7Config
    from src.hl7.builder import HL7Builder
    from src.transport.dispatcher import Dispatcher

    cfg = _load_config()
    target = next((t for t in cfg.get("targets", []) if t.get("name") == args.name), None)
    if not target:
        print(f"target {args.name!r} not found"); return 2
    single_cfg = GatewayConfig.model_validate({**cfg, "targets": [target]})

    fake = {
        "timestamp": datetime.now(), "sample_id": f"CLI_{datetime.now():%H%M%S}",
        "patient_id": "TEST0000", "patient_name": "TEST Patient",
        "gender": "M", "disc_name": "TEST", "lot_id": "TEST",
        "observations": [{"analyte": "AST", "value": "10", "value_num": 10.0,
                          "flag": "", "ref_low": 15, "ref_high": 40, "unit": "U/L"}],
    }
    builder = HL7Builder(HL7Config(**cfg.get("hl7", {})))
    msg = builder.build_oru_r01(fake)

    async def _go():
        d = Dispatcher(single_cfg)
        return await d.dispatch(msg, fake)

    summary = asyncio.run(_go())
    print(f"succeeded: {summary.succeeded}")
    print(f"failed:    {summary.failed}")
    if summary.errors:
        for name, err in summary.errors.items():
            print(f"  [{name}] {err}")
    return 0 if summary.succeeded else 1


def cmd_dlq_list(args) -> int:
    from src.common.dead_letter import list_dead_letters
    for e in list_dead_letters(limit=args.limit):
        print(f"{e['ts']:<26} {e['control_id']:<20} device={e.get('device','?'):<15} "
              f"targets={','.join(e.get('targets', []))} reason={e.get('reason','')}")
    return 0


def cmd_dlq_replay(args) -> int:
    from src.common.dead_letter import read_dead_letter
    from config.settings import GatewayConfig
    from src.hl7.builder import HL7Message
    from src.transport.dispatcher import Dispatcher

    body = read_dead_letter(args.control_id)
    if body is None:
        print("not found"); return 2

    cfg = _load_config()
    if args.targets:
        wanted = set(args.targets.split(","))
        cfg = {**cfg, "targets": [t for t in cfg.get("targets", []) if t.get("name") in wanted]}
    gcfg = GatewayConfig.model_validate(cfg)
    segments = [s for s in body.split("\r") if s.strip()]
    msg = HL7Message(segments, msh_control_id=args.control_id, charset=gcfg.hl7.charset)
    summary = asyncio.run(Dispatcher(gcfg).dispatch(msg, {
        "sample_id": f"REPLAY_{args.control_id}", "patient_id": "REPLAY",
        "device": "DLQ_REPLAY", "observations": [],
    }))
    print(f"succeeded: {summary.succeeded}")
    print(f"failed:    {summary.failed}")
    return 0 if summary.succeeded else 1


def cmd_device_list(_args) -> int:
    import yaml
    catalog = Path("config/devices")
    for f in sorted(catalog.glob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text()) or {}
            flag = "on " if d.get("enabled") else "off"
            print(f"[{flag}] {d.get('id', f.stem):<24} type={d.get('type', '?'):<18} "
                  f"vendor={d.get('vendor', '')}")
        except Exception as exc:
            print(f"[?] {f.name}: {exc}")
    return 0


def cmd_device_add(_args) -> int:
    """Interactive wizard: create a config/devices/<id>.yaml"""
    print("=== Wizard aggiunta device ===")
    print()
    dev_id = input("ID device (kebab-case, es. sysmex-xn550): ").strip()
    if not dev_id:
        print("ID richiesto"); return 2
    print()
    print("Tipo (protocollo):")
    print("  1) mllp_hl7        -- HL7 v2 MLLP standard (default)")
    print("  2) sysmex_astm     -- ASTM E1381 (Sysmex XP-300, pocH-100i)")
    print("  3) uc1000_serial   -- Menarini UC-1000 (RS-232 CSV)")
    print("  4) cobas_poct      -- Roche Cobas b101 (POCT1-A2 XML)")
    dtype = {"1": "mllp_hl7", "2": "sysmex_astm",
             "3": "uc1000_serial", "4": "cobas_poct"}.get(
        input("scelta [1]: ").strip() or "1", "mllp_hl7")
    print()
    display = input("Nome display: ").strip() or dev_id
    vendor  = input("Vendor: ").strip()
    model   = input("Modello: ").strip()
    print()
    out = {
        "id":           dev_id,
        "type":         dtype,
        "enabled":      False,       # user must review before enabling
        "display_name": display,
        "vendor":       vendor,
        "model":        model,
    }
    if dtype in ("mllp_hl7", "sysmex_astm"):
        out["listen_host"] = "0.0.0.0"
        out["listen_port"] = int(input("Porta TCP di ascolto (es. 5100): ").strip() or "5100")
    elif dtype == "uc1000_serial":
        out["serial_port"] = input("Porta seriale [/dev/ttyUSB1]: ").strip() or "/dev/ttyUSB1"
        out["baudrate"]    = int(input("Baudrate [9600]: ").strip() or "9600")
    elif dtype == "cobas_poct":
        out["serial_port"] = input("Porta USB CDC [/dev/ttyACM0]: ").strip() or "/dev/ttyACM0"

    import yaml
    path = Path("config/devices") / f"{dev_id}.yaml"
    if path.exists():
        if input(f"{path} esiste. Sovrascrivere? [y/N]: ").strip().lower() != "y":
            print("aborted"); return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(out, sort_keys=False), encoding="utf-8")
    print()
    print(f"Salvato: {path}")
    print()
    print("Il device è creato DISABILITATO. Per attivarlo:")
    print(f"  1. Verifica  {path}  (cambia enabled: true)")
    print("  2. Ricarica  jerumednexus reload   (oppure  systemctl restart jerumednexus-gateway)")
    return 0


def cmd_discover(args) -> int:
    from src.discovery.service import DiscoveryService
    svc = DiscoveryService()
    tcp_range = args.tcp.split(",") if args.tcp else None
    tcp_ports = [int(p) for p in args.ports.split(",")] if args.ports else None
    snap = asyncio.run(svc.scan_once(tcp_range=tcp_range, tcp_ports=tcp_ports))
    for d in snap:
        print(f"[{d['confidence']:3d}%] {d['source']:<4} {d['location']:<28} "
              f"proto={d.get('protocol') or '-':<12} {d.get('display_name') or ''}")
    return 0


def cmd_users_list(_args) -> int:
    from src.security import roles
    for u in roles.list_users():
        print(f"{u['role']:<10} {u['name']}")
    return 0


def cmd_users_create(args) -> int:
    from src.security import roles
    pw = getpass.getpass("Password: ")
    pw2 = getpass.getpass("Conferma: ")
    if pw != pw2:
        print("passwords do not match"); return 2
    try:
        roles.create_user(args.name, pw, args.role)
        print(f"user {args.name!r} created (role={args.role})")
        return 0
    except ValueError as exc:
        print(f"error: {exc}"); return 1


def cmd_trace(args) -> int:
    from src.common import trace as _trace
    entries = _trace.snapshot(device=args.device, limit=args.limit)
    if not entries:
        devs = _trace.devices()
        print(f"(nessun frame in trace; device conosciuti: {devs})")
        return 0
    for e in entries:
        d = e.get("device", args.device or "?")
        arrow = "->" if e["direction"] == "in" else "<-"
        text = e["text"][:120].replace("\r", "\\r").replace("\n", "\\n")
        print(f"{e['ts']:.3f} {d:<20} {arrow} {e['size']:>5}b  {text}")
    return 0


def cmd_validate(args) -> int:
    from src.hl7.validator import validate_hl7_message
    text = Path(args.file).read_text(encoding="utf-8")
    # Normalise to CR
    text = text.replace("\r\n", "\r").replace("\n", "\r")
    rep = validate_hl7_message(text)
    print(f"valid={rep.is_valid}  errors={len(rep.errors)}  warnings={len(rep.warnings)}")
    for f in rep.findings:
        marker = "!!" if f.level == "ERROR" else "??" if f.level == "WARN" else "  "
        print(f"{marker} [{f.level}] {f.segment}: {f.message}"
              + (f"  ({f.field!r})" if f.field else ""))
    return 0 if rep.is_valid else 1


def cmd_sla(args) -> int:
    from src.common.sla_report import save_report
    y, m = args.period.split("-")
    out_dir = Path(args.out or "logs/sla")
    cfg = _load_config()
    facility = (cfg.get("hl7") or {}).get("sending_facility", "PRAXIS")
    dest = save_report(int(y), int(m), out_dir, facility=facility)
    print(f"SLA report: {dest}")
    return 0


def cmd_reset_password(_args) -> int:
    files = [Path("config/webui_password.hash"), Path("config/webui_users.json")]
    for f in files:
        if f.exists():
            f.unlink()
            print(f"removed {f}")
    print("open the Web UI to run the setup wizard.")
    return 0


def cmd_patient_export(args) -> int:
    from src.common.patient_rights import export
    data = export(args.patient_id)
    import json as _json
    text = _json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Export written to {args.out}")
    else:
        print(text)
    return 0


def cmd_patient_purge(args) -> int:
    from src.common.patient_rights import purge, export
    # Show first so the operator can confirm
    e = export(args.patient_id)
    n = (len(e.get("dispatches") or [])
         + len(e.get("dead_letter") or [])
         + len(e.get("orders") or [])
         + len(e.get("seen_samples") or []))
    if n == 0:
        print(f"No trace found for patient_id={args.patient_id!r}")
        return 0
    print(f"Will DELETE {n} records for patient_id={args.patient_id!r}")
    print("  history:      %d" % len(e.get("dispatches") or []))
    print("  dead_letter:  %d" % len(e.get("dead_letter") or []))
    print("  orders:       %d" % len(e.get("orders") or []))
    print("  seen_samples: %d" % len(e.get("seen_samples") or []))
    if not args.yes:
        try:
            confirm = input("Type YES to proceed: ").strip()
        except EOFError:
            confirm = ""
        if confirm != "YES":
            print("Aborted.")
            return 1
    report = purge(args.patient_id)
    print(f"Purged: {report}")
    return 0


def cmd_reload(_args) -> int:
    import subprocess
    r = subprocess.run(
        ["sudo", "systemctl", "kill", "--signal=SIGHUP", "jerumednexus-gateway"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr); return 1
    print("SIGHUP sent -- gateway reloading config.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jerumednexus", description="JerumedNexus Gateway CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show current gateway status").set_defaults(fn=cmd_status)

    t = sub.add_parser("target", help="PIS/LIS target ops"); ts = t.add_subparsers(required=True)
    ts.add_parser("list").set_defaults(fn=cmd_target_list)
    tt = ts.add_parser("test", help="send a synthetic HL7 to a target")
    tt.add_argument("name"); tt.set_defaults(fn=cmd_target_test)

    d = sub.add_parser("dlq", help="dead-letter queue"); ds = d.add_subparsers(required=True)
    dl = ds.add_parser("list"); dl.add_argument("--limit", type=int, default=50); dl.set_defaults(fn=cmd_dlq_list)
    dr = ds.add_parser("replay")
    dr.add_argument("control_id"); dr.add_argument("--targets", default="")
    dr.set_defaults(fn=cmd_dlq_replay)

    dev = sub.add_parser("device", help="lab device catalog"); dvs = dev.add_subparsers(required=True)
    dvs.add_parser("list").set_defaults(fn=cmd_device_list)
    dvs.add_parser("add", help="interactive wizard").set_defaults(fn=cmd_device_add)

    disc = sub.add_parser("discover", help="plug-and-play scan")
    disc.add_argument("--tcp", default="", help="CIDR(s) or IP(s), comma-separated")
    disc.add_argument("--ports", default="", help="TCP ports, comma-separated")
    disc.set_defaults(fn=cmd_discover)

    u = sub.add_parser("users", help="user account management"); us = u.add_subparsers(required=True)
    us.add_parser("list").set_defaults(fn=cmd_users_list)
    uc = us.add_parser("create"); uc.add_argument("name")
    uc.add_argument("--role", choices=("viewer", "operator", "admin"), default="viewer")
    uc.set_defaults(fn=cmd_users_create)

    tr = sub.add_parser("trace", help="live protocol frames")
    tr.add_argument("device", nargs="?", default=None)
    tr.add_argument("--limit", type=int, default=50); tr.set_defaults(fn=cmd_trace)

    v = sub.add_parser("validate", help="check an HL7 file for compliance")
    v.add_argument("file"); v.set_defaults(fn=cmd_validate)

    s = sub.add_parser("sla", help="generate monthly SLA report (HTML)")
    s.add_argument("period", help="YYYY-MM")
    s.add_argument("--out", default=None); s.set_defaults(fn=cmd_sla)

    # Patient rights (nDSG / GDPR)
    pat = sub.add_parser("patient", help="patient data rights (nDSG / GDPR)")
    pat_sub = pat.add_subparsers(required=True)
    pe = pat_sub.add_parser("export", help="dump every trace of a patient to JSON")
    pe.add_argument("patient_id"); pe.add_argument("--out", default=None)
    pe.set_defaults(fn=cmd_patient_export)
    pp = pat_sub.add_parser("purge", help="delete every trace of a patient")
    pp.add_argument("patient_id")
    pp.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    pp.set_defaults(fn=cmd_patient_purge)

    sub.add_parser("reset-password",
                   help="delete admin creds so setup wizard re-runs").set_defaults(fn=cmd_reset_password)
    sub.add_parser("reload", help="send SIGHUP for config hot-reload").set_defaults(fn=cmd_reload)

    # Triage a support bundle (AI ops)
    tri = sub.add_parser("triage", help="analyze a support bundle and suggest cause + runbook")
    tri.add_argument("bundle_path", help="path to support bundle directory")
    tri.add_argument("--llm", action="store_true",
                     help="use LLM backend if ANTHROPIC_API_KEY is set")
    tri.set_defaults(fn=cmd_triage)

    return p


def cmd_triage(args) -> int:
    from pathlib import Path
    from src.ai.support_triage import triage_bundle, triage_llm

    bundle_path = Path(args.bundle_path)
    if args.llm:
        logs = (bundle_path / "gateway.log").read_text(encoding="utf-8",
                                                        errors="replace")
        result = triage_llm(logs)
    else:
        result = triage_bundle(bundle_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    p = build_parser()
    args = p.parse_args()
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
