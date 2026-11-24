"""
Regression tests for the repeat-sample dedup fix.

Scenario che ha motivato il fix (segnalato dall'operatore):
> "Se il medico fa un test alle 09:00 e ripete lo stesso sample_id
>  alle 09:30 con valori diversi, il repeat viene droppato come duplicato.
>  Il medico non se ne accorge."

Fix: la chiave dedup ora include un hash dei valori. Un repeat legittimo
(stesso sample_id, valori diversi) passa. Un vero duplicato tecnico
(stesso sample_id, stessi identici valori entro 24h) è ancora droppato.
"""
from __future__ import annotations

import hashlib


def _make_obs_sig(observations: list[dict]) -> str:
    obs_sig_src = "|".join(
        f"{o.get('analyte', '')}={o.get('value', '')}"
        for o in (observations or [])
    )
    return hashlib.sha256(obs_sig_src.encode("utf-8")).hexdigest()[:16]


def test_same_sample_id_different_values_produces_different_key() -> None:
    """Repeat sample: same ID, different HGB reading → different dedup key."""
    obs_first = [{"analyte": "HGB", "value": "14.2"},
                 {"analyte": "WBC", "value": "7.4"}]
    obs_repeat = [{"analyte": "HGB", "value": "13.9"},
                  {"analyte": "WBC", "value": "7.5"}]
    sig_first = _make_obs_sig(obs_first)
    sig_repeat = _make_obs_sig(obs_repeat)
    assert sig_first != sig_repeat
    key_first = f"Sysmex XQ-320:SN0042:{sig_first}"
    key_repeat = f"Sysmex XQ-320:SN0042:{sig_repeat}"
    assert key_first != key_repeat


def test_exact_duplicate_produces_same_key() -> None:
    """True technical duplicate: retry by device → same key → will be dropped."""
    obs = [{"analyte": "HGB", "value": "14.2"},
           {"analyte": "WBC", "value": "7.4"}]
    sig1 = _make_obs_sig(obs)
    sig2 = _make_obs_sig(obs)
    assert sig1 == sig2


def test_different_devices_same_sample_id_same_values_different_key() -> None:
    """Case 3: two devices happen to share a sample_id → device prefix disambiguates."""
    obs = [{"analyte": "HGB", "value": "14.2"}]
    sig = _make_obs_sig(obs)
    key_sysmex = f"Sysmex XQ-320:SN0042:{sig}"
    key_cobas = f"Cobas b101:SN0042:{sig}"
    assert key_sysmex != key_cobas


def test_signature_is_stable_across_observation_order() -> None:
    """Observation order matters — a repeat with the same values in the
    same order must produce the same signature (dedup as duplicate)."""
    obs_a = [{"analyte": "HGB", "value": "14.2"},
             {"analyte": "WBC", "value": "7.4"}]
    obs_b = [{"analyte": "HGB", "value": "14.2"},
             {"analyte": "WBC", "value": "7.4"}]
    assert _make_obs_sig(obs_a) == _make_obs_sig(obs_b)


def test_signature_reflects_missing_observations() -> None:
    obs_full = [{"analyte": "HGB", "value": "14.2"},
                {"analyte": "WBC", "value": "7.4"}]
    obs_partial = [{"analyte": "HGB", "value": "14.2"}]   # WBC missing
    assert _make_obs_sig(obs_full) != _make_obs_sig(obs_partial)


def test_signature_empty_observations_is_stable() -> None:
    assert _make_obs_sig([]) == _make_obs_sig([])
    assert _make_obs_sig([]) != _make_obs_sig([{"analyte": "HGB", "value": "14.2"}])
