"""
Fallback PDF dispatcher — for LIS that don't accept HL7/FHIR, we generate
a printable PDF and drop it in a shared folder (or email attachment).

Uses reportlab if available; otherwise falls back to plain-text file.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("loc200.pdf_dispatcher")


def render_report(payload: dict[str, Any], out_path: Path) -> Path:
    """Render one sample as a PDF and return the file path."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
    except ImportError:
        return _render_text(payload, out_path.with_suffix(".txt"))

    c = canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    c.setFillColorRGB(0.03, 0.57, 0.70)
    c.rect(0, h - 2.5*cm, w, 2.5*cm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, h - 1.7*cm, "Referto di laboratorio")
    c.setFont("Helvetica", 10)
    c.drawString(2*cm, h - 2.2*cm,
                  f"JerumedNexus Gateway · {datetime.utcnow().isoformat()}Z")

    c.setFillColorRGB(0, 0, 0)
    y = h - 4*cm
    c.setFont("Helvetica-Bold", 11)
    for label, key in [("Patient ID:", "patient_id"),
                        ("Sample ID:", "sample_id"),
                        ("Device:", "device")]:
        c.drawString(2*cm, y, label)
        c.setFont("Helvetica", 11)
        c.drawString(5*cm, y, str(payload.get(key, "—")))
        c.setFont("Helvetica-Bold", 11)
        y -= 0.7*cm

    y -= 1*cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(2*cm, y, "Analita")
    c.drawString(8*cm, y, "Valore")
    c.drawString(11*cm, y, "Unità")
    c.drawString(14*cm, y, "Range")
    c.drawString(17*cm, y, "Flag")
    y -= 0.4*cm
    c.line(2*cm, y, w - 2*cm, y)
    y -= 0.5*cm

    c.setFont("Helvetica", 10)
    for obs in payload.get("observations", []):
        c.drawString(2*cm,  y, str(obs.get("analyte", ""))[:30])
        c.drawString(8*cm,  y, str(obs.get("value", "")))
        c.drawString(11*cm, y, str(obs.get("unit", "")))
        rng = ""
        if obs.get("ref_low") is not None or obs.get("ref_high") is not None:
            rng = f"{obs.get('ref_low', '')}-{obs.get('ref_high', '')}"
        c.drawString(14*cm, y, rng)
        c.drawString(17*cm, y, str(obs.get("flag", "")))
        y -= 0.5*cm

    c.save()
    return out_path


def _render_text(payload: dict[str, Any], out_path: Path) -> Path:
    lines = [
        "=" * 60,
        "  Referto di laboratorio (JerumedNexus Gateway fallback)",
        "=" * 60,
        f"Patient:   {payload.get('patient_id', '—')}",
        f"Sample:    {payload.get('sample_id', '—')}",
        f"Device:    {payload.get('device', '—')}",
        f"Timestamp: {datetime.utcnow().isoformat()}Z",
        "-" * 60,
    ]
    lines.append(f"{'Analita':<20} {'Valore':<10} {'Unità':<12} {'Flag':<6}")
    lines.append("-" * 60)
    for obs in payload.get("observations", []):
        lines.append(
            f"{str(obs.get('analyte', ''))[:20]:<20} "
            f"{str(obs.get('value', '')):<10} "
            f"{str(obs.get('unit', '')):<12} "
            f"{str(obs.get('flag', '')):<6}"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def dispatch(payload: dict[str, Any], drop_dir: str) -> Path:
    """Full dispatch: render + save in drop_dir with structured filename."""
    d = Path(drop_dir)
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    sample = str(payload.get("sample_id", "sample")).replace("/", "_")
    fname = d / f"{ts}_{sample}.pdf"
    result = render_report(payload, fname)
    log.info("PDF fallback dispatch: %s", result)
    return result
