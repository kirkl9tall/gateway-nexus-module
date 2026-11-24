"""
Il canale SFTP deve avere le stesse garanzie degli altri.

SFTP e' il canale di Tomedo, cioe' l'unico davvero usato in produzione, ed era
anche l'unico che NON applicava le riscritture di config/rewrites/<target>.yaml
e NON passava dal validatore HL7. Una regola scritta per Tomedo non aveva
effetto e un messaggio malformato partiva comunque. Inoltre l'estensione del
file era fissata a .hl7, ignorando quella configurata sul target.
"""
from __future__ import annotations

import asyncio


from src.transport.sftp_dispatcher import SFTPDispatcher


class _Msg:
    """Messaggio minimo: quel tanto che il dispatcher usa davvero."""
    _codec = "iso-8859-1"

    def __init__(self, testo: str) -> None:
        self._testo = testo

    def to_string(self) -> str:
        return self._testo

    def to_file(self) -> bytes:
        return self._testo.replace(chr(13), chr(13) + chr(10)).encode(self._codec)


def _dispatcher(**kw) -> SFTPDispatcher:
    base = dict(host="h", username="u", password="p", remote_path="/import")
    base.update(kw)
    return SFTPDispatcher(**base)


def _cattura_upload(d: SFTPDispatcher, monkeypatch) -> dict:
    """Sostituisce la salita SFTP e registra cosa sarebbe stato caricato."""
    visto: dict = {}

    async def _finto(nome, contenuto):
        visto["nome"] = nome
        visto["contenuto"] = contenuto

    monkeypatch.setattr(d, "_upload", _finto)
    return visto


def test_usa_il_testo_verificato_quando_fornito(monkeypatch):
    d = _dispatcher()
    visto = _cattura_upload(d, monkeypatch)
    grezzo = "MSH|^~" + chr(13) + "PID|||111"
    riscritto = "MSH|^~" + chr(13) + "PID|||999"
    asyncio.run(d.dispatch(_Msg(grezzo), {"patient_id": "111"},
                           testo_verificato=riscritto))
    assert b"999" in visto["contenuto"], visto["contenuto"]
    assert b"111" not in visto["contenuto"]


def test_senza_testo_verificato_si_comporta_come_prima(monkeypatch):
    d = _dispatcher()
    visto = _cattura_upload(d, monkeypatch)
    grezzo = "MSH|^~" + chr(13) + "PID|||111"
    asyncio.run(d.dispatch(_Msg(grezzo), {"patient_id": "111"}))
    assert visto["contenuto"] == _Msg(grezzo).to_file()


def test_i_segmenti_finiscono_in_crlf():
    """Tomedo rifiuta i file con fine-riga sbagliati."""
    d = _dispatcher()
    visto = {}

    async def _finto(nome, contenuto):
        visto["contenuto"] = contenuto

    d._upload = _finto
    testo = "MSH|a" + chr(13) + "PID|b" + chr(13) + "OBX|c"
    asyncio.run(d.dispatch(_Msg(testo), {"patient_id": "1"}, testo_verificato=testo))
    assert visto["contenuto"].count(bytes([13, 10])) == 2
    assert bytes([13, 13]) not in visto["contenuto"]


def test_non_raddoppia_i_crlf_gia_presenti():
    d = _dispatcher()
    visto = {}

    async def _finto(nome, contenuto):
        visto["contenuto"] = contenuto

    d._upload = _finto
    gia_crlf = "MSH|a" + chr(13) + chr(10) + "PID|b"
    asyncio.run(d.dispatch(_Msg(gia_crlf), {"patient_id": "1"},
                           testo_verificato=gia_crlf))
    assert visto["contenuto"] == b"MSH|a" + bytes([13, 10]) + b"PID|b"


def test_rispetta_l_estensione_configurata(monkeypatch):
    """Un gestionale che importa solo *.ldt non vedeva mai i file."""
    d = _dispatcher(file_extension=".ldt")
    visto = _cattura_upload(d, monkeypatch)
    asyncio.run(d.dispatch(_Msg("MSH|a"), {"patient_id": "42"}))
    assert visto["nome"].endswith(".ldt"), visto["nome"]


def test_estensione_predefinita_invariata(monkeypatch):
    d = _dispatcher()
    visto = _cattura_upload(d, monkeypatch)
    asyncio.run(d.dispatch(_Msg("MSH|a"), {"patient_id": "42"}))
    assert visto["nome"].endswith(".hl7"), visto["nome"]


# ── il dispatcher principale passa davvero per il punto unico ──────────────

def test_il_conteggio_delle_riscritture_non_e_sempre_zero():
    """
    Il log diceva "Applied 0 rewrite rule(s)" anche quando le regole si
    applicavano, perche' contava la stringa backslash-r invece del CR.
    """
    from src.transport.dispatcher import Dispatcher
    import inspect as _inspect
    sorgente = _inspect.getsource(Dispatcher._testo_verificato)
    assert "chr(13)" in sorgente
    assert 'count("' + chr(92) + 'r")' not in sorgente


def test_tutti_e_tre_i_canali_usano_lo_stesso_punto():
    from src.transport.dispatcher import Dispatcher
    import inspect as _inspect
    for metodo in (Dispatcher._preview_bytes, Dispatcher._send_file,
                   Dispatcher._send_sftp):
        assert "_testo_verificato" in _inspect.getsource(metodo), metodo.__name__
