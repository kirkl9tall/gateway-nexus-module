"""
Performance benchmarks: catch regressions in hot paths.

Run manually:
    pytest tests/test_benchmarks.py --benchmark-only

In CI these are skipped by default (they're advisory, not gating).
"""
from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("pytest_benchmark")

from config.settings import HL7Config
from src.hl7.builder import HL7Builder, _esc


@pytest.fixture
def sample_result():
    return {
        "timestamp":    datetime(2025, 1, 1, 12, 0, 0),
        "sample_id":    "S001",
        "patient_id":   "P123",
        "patient_name": "Mueller Hans",
        "gender":       "M",
        "disc_name":    "K1",
        "lot_id":       "L1",
        "observations": [
            {"analyte": f"ANL{i}", "value": str(i), "value_num": float(i),
             "flag": "", "ref_low": None, "ref_high": None, "unit": "U/L"}
            for i in range(20)
        ],
    }


def test_bench_esc_short(benchmark):
    benchmark(_esc, "Mueller|Hans^Dr")


def test_bench_esc_long(benchmark):
    text = "Patient with a long name and special chars: | ^ ~ & \\r\\n " * 10
    benchmark(_esc, text)


def test_bench_build_message(benchmark, sample_result):
    builder = HL7Builder(HL7Config(sending_facility="BENCH"))
    benchmark(builder.build_oru_r01, sample_result)


def test_bench_mllp_encode(benchmark, sample_result):
    builder = HL7Builder(HL7Config(sending_facility="BENCH"))
    msg = builder.build_oru_r01(sample_result)
    benchmark(msg.to_mllp)
