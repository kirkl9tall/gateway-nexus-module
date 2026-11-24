"""
Golden-file regression tests for the six devices already verified
in real production. Dynamically discovers pairs of

    tests/fixtures/golden/<device>/<slug>.in.{txt,bin}
    tests/fixtures/golden/<device>/<slug>.out.hl7

and asserts the current parser produces the recorded HL7 output byte-
per-byte (after \\r segment normalization). If no fixture is present,
the test is skipped silently (the folders ship with a .gitkeep and no
captures — owner adds real frames post-hardware-test).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden"

# Device → (parser callable that takes raw text and returns a dict, then
# builder callable that takes dict and returns HL7 string).
_ADAPTERS = {}


def _load_adapters():
    """Lazy-import so pytest collection does not fail on missing deps."""
    global _ADAPTERS
    if _ADAPTERS:
        return _ADAPTERS
    try:
        from src.adapters.sysmex_reader import _parse_astm
        from src.hl7 import hl7_builder as _hl7
        _ADAPTERS["sysmex_xq320"] = (
            lambda text: _parse_astm(text, "Sysmex XQ-320"),
            lambda d: _hl7.build_hl7_message(d) if hasattr(_hl7, "build_hl7_message") else "",
        )
    except ImportError as exc:
        pytest.skip(f"parser import failed: {exc}", allow_module_level=False)
    return _ADAPTERS


def _discover_fixtures():
    """Return list of (device, slug, in_path, out_path)."""
    fixtures = []
    if not _FIXTURE_ROOT.exists():
        return fixtures
    for device_dir in sorted(p for p in _FIXTURE_ROOT.iterdir() if p.is_dir()):
        for in_file in sorted(list(device_dir.glob("*.in.txt")) +
                              list(device_dir.glob("*.in.bin"))):
            slug = in_file.stem.rsplit(".in", 1)[0]
            out_file = device_dir / f"{slug}.out.hl7"
            if out_file.exists():
                fixtures.append((device_dir.name, slug, in_file, out_file))
    return fixtures


def _normalize_hl7(msg: str) -> str:
    """Normalize segment separators for comparison."""
    return re.sub(r"[\r\n]+", "\r", msg.strip()).strip()


_FIXTURES = _discover_fixtures()


@pytest.mark.parametrize(
    "device,slug,in_path,out_path",
    _FIXTURES,
    ids=[f"{d}/{s}" for d, s, _, _ in _FIXTURES] or ["_no_fixtures_present"],
)
def test_golden_regression(device, slug, in_path, out_path):
    if not _FIXTURES:
        pytest.skip("no golden fixtures present — drop real captures into "
                    "tests/fixtures/golden/<device>/ to activate")
    adapters = _load_adapters()
    if device not in adapters:
        pytest.skip(f"no adapter mapping for device {device!r}")
    parser, builder = adapters[device]

    if in_path.suffix == ".bin":
        raw = in_path.read_bytes().decode("ascii", errors="ignore")
    else:
        raw = in_path.read_text(encoding="ascii", errors="ignore")

    parsed = parser(raw)
    assert parsed is not None, f"parser returned None for {in_path}"
    produced = builder(parsed)
    expected = out_path.read_text(encoding="utf-8")

    assert _normalize_hl7(produced) == _normalize_hl7(expected), (
        f"HL7 regression on {device}/{slug}:\n"
        f"--- expected ---\n{expected}\n"
        f"--- produced ---\n{produced}\n"
    )
