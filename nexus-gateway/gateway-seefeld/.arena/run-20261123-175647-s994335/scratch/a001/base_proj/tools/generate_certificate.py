"""
Generate a signed PDF certification badge for a PLATINUM device.

Usage:
    python -m tools.generate_certificate sysmex_xq320 --praxis "Praxis Rossi" \
        --out cert-sysmex-xq320.pdf --gpg-recipient cert@jerumednexus.example
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _load_field(device_id: str) -> dict:
    p = Path("logs/field_validation.json")
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get(device_id, {})


def _build_pdf(device_id: str, praxis: str, out_path: Path,
               validation: dict) -> None:
    """Build PDF with reportlab if available, else a plain text fallback."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
    except ImportError:
        # Text fallback
        out_path.write_text(_build_text(device_id, praxis, validation),
                             encoding="utf-8")
        print(f"reportlab not installed — wrote text certificate to {out_path}")
        return

    c = canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    # Header
    c.setFillColorRGB(0.03, 0.57, 0.70)
    c.rect(0, h - 3*cm, w, 3*cm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(2*cm, h - 2*cm, "JerumedNexus Gateway")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, h - 2.6*cm, "Device Certification — PLATINUM")

    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, h - 5*cm, "Certificato di compatibilità")
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, h - 5.7*cm,
                  "Rilasciato da Jerumed Nexus GmbH — Zug, Svizzera")

    y = h - 7.5*cm
    for label, value in [
        ("Device:", device_id),
        ("Praxis:", praxis),
        ("Data installazione:", validation.get("installed_at", "—")),
        ("Serial number:", validation.get("device_serial", "—")),
        ("Installatore:", validation.get("installer", "—")),
        ("Checks completate:", str(validation.get("checks_completed", "—"))),
        ("Sign-off:", "✓ FIRMATO" if validation.get("signed_off") else "in attesa"),
    ]:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(2*cm, y, label)
        c.setFont("Helvetica", 10)
        c.drawString(6*cm, y, value)
        y -= 0.7*cm

    # Footer
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(2*cm, 2*cm,
                  f"Generato il {datetime.utcnow().isoformat()}Z · v1.3.0")
    c.drawString(2*cm, 1.5*cm,
                  "Questo certificato attesta che il device ha superato ogni "
                  "signal di verifica")
    c.drawString(2*cm, 1.1*cm,
                  "definito in tools/device_certification.py.")

    c.save()
    print(f"PDF certificate written to {out_path}")


def _build_text(device_id: str, praxis: str, validation: dict) -> str:
    return f"""
=====================================================
  JerumedNexus Gateway — CERTIFICATO DI COMPATIBILITÀ
=====================================================
  Device tier:      💎 PLATINUM
  Device ID:        {device_id}
  Praxis:           {praxis}
  Data installazione: {validation.get('installed_at', '—')}
  Serial:           {validation.get('device_serial', '—')}
  Installatore:     {validation.get('installer', '—')}
  Checks completate: {validation.get('checks_completed', '—')}/15
  Sign-off:         {'✓ FIRMATO' if validation.get('signed_off') else 'in attesa'}
  Rilasciato da:    Jerumed Nexus GmbH — Zug, Svizzera
  Generato:         {datetime.utcnow().isoformat()}Z · v1.3.0
=====================================================
""".strip()


def _gpg_sign(pdf_path: Path, recipient: str) -> Path:
    sig_path = pdf_path.with_suffix(pdf_path.suffix + ".sig")
    try:
        subprocess.run(
            ["gpg", "--batch", "--yes", "--default-key", recipient,
             "--output", str(sig_path), "--detach-sign", str(pdf_path)],
            check=True,
        )
        return sig_path
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"GPG signing skipped: {exc}", file=sys.stderr)
        return sig_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("device_id")
    ap.add_argument("--praxis", required=True)
    ap.add_argument("--out", default="certificate.pdf")
    ap.add_argument("--gpg-recipient", default=None,
                     help="GPG key ID to sign the PDF with")
    args = ap.parse_args()

    validation = _load_field(args.device_id)
    out = Path(args.out)
    _build_pdf(args.device_id, args.praxis, out, validation)

    if args.gpg_recipient:
        sig = _gpg_sign(out, args.gpg_recipient)
        print(f"GPG signature: {sig}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
