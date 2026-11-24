"""
src/adapters/sysmex_reader.py
Reads ASTM frames from Sysmex XP-300, XQ-320 and pocH-100i.
Supports TCP (network) and Serial (USB/RS-232) connections.
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket as _socket
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

try:
    import serial_asyncio
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

from src.common.backpressure import safe_put_sync
from src.common.framing import MAX_FRAME_BYTES, guard_buffer
from src.common import trace as _trace

log = logging.getLogger("loc200.sysmex")

ENQ = 0x05
ACK = 0x06
NAK = 0x15
EOT = 0x04
STX = 0x02
ETX = 0x03
ETB = 0x17   # intermediate-frame terminator (multi-frame records)
CR  = 0x0D
LF  = 0x0A


_L_REC_RE = re.compile(r"(?:^|[\r\n])L\|[^\r\n]*[\r\n]")


def _has_terminator_l(text: str) -> bool:
    """True when the buffer contains an ASTM L (message terminator) record
    terminated by CR/LF — signals a complete E1381-95 raw message."""
    return bool(_L_REC_RE.search(text))

SYSMEX_TEST_MAP: Dict[str, Dict] = {
    "WBC":    {"name": "Leukozyten",                          "unit": "10^3/uL", "loinc": "6690-2",  "ref": "4.0-10.0"},
    "NEUT#":  {"name": "Neutrophile abs.",                    "unit": "10^3/uL", "loinc": "26499-4", "ref": "2.0-7.0"},
    "LYMPH#": {"name": "Lymphozyten abs.",                    "unit": "10^3/uL", "loinc": "26474-7", "ref": "1.0-4.0"},
    "MXD#":   {"name": "Mono./Eos./Baso. abs.",               "unit": "10^3/uL", "loinc": "26484-6", "ref": "0.2-1.0"},
    "NEUT%":  {"name": "Neutrophile %",                       "unit": "%",       "loinc": "26499-4", "ref": "40-75"},
    "LYMPH%": {"name": "Lymphozyten %",                       "unit": "%",       "loinc": "26474-7", "ref": "20-45"},
    "MXD%":   {"name": "Mono./Eos./Baso. %",                  "unit": "%",       "loinc": "26484-6", "ref": "2-12"},
    "RBC":    {"name": "Erythrozyten",                        "unit": "10^6/uL", "loinc": "789-8",   "ref": "4.2-5.4"},
    "HGB":    {"name": "Haemoglobin",                         "unit": "g/dL",    "loinc": "718-7",   "ref": "12.0-16.0"},
    "HCT":    {"name": "Haematokrit",                         "unit": "%",       "loinc": "20570-8", "ref": "36.0-46.0"},
    "MCV":    {"name": "Mittleres Erythrozyten-Volumen",      "unit": "fL",      "loinc": "787-2",   "ref": "85-95"},
    "MCH":    {"name": "Mittlerer Hb-Gehalt pro Erythrozyt",  "unit": "pg",      "loinc": "785-6",   "ref": "27-33"},
    "MCHC":   {"name": "Mittlere Hb-Konzentration",           "unit": "g/dL",    "loinc": "786-4",   "ref": "32-36"},
    "RDW-SD": {"name": "Erythrozyten-Verteilungsbreite SD",   "unit": "fL",      "loinc": "21000-5", "ref": "37-54"},
    "RDW-CV": {"name": "Erythrozyten-Verteilungsbreite CV",   "unit": "%",       "loinc": "788-0",   "ref": "11-16"},
    "PLT":    {"name": "Thrombozyten",                        "unit": "10^3/uL", "loinc": "777-3",   "ref": "150-400"},
    "PDW":    {"name": "Thrombozyten-Verteilungsbreite",      "unit": "fL",      "loinc": "32623-1", "ref": "9-17"},
    "MPV":    {"name": "Mittleres Thrombozyten-Volumen",      "unit": "fL",      "loinc": "32623-1", "ref": "7-13"},
    "P-LCR":  {"name": "Grossthrombozyten-Anteil",            "unit": "%",       "loinc": "32623-1", "ref": "10-45"},
    "PCT":    {"name": "Thrombokrit",                         "unit": "%",       "loinc": "32623-1", "ref": "0.10-0.30"},
    "MXD":    {"name": "Mischzellen (Mono/Eos/Baso) %",       "unit": "%",       "loinc": "26484-6", "ref": "2-12"},
}

_RE_ID_SUFFIX = re.compile(r"[A-Za-z]+$")


def _strip_suffix(sample_id: str) -> str:
    return _RE_ID_SUFFIX.sub("", sample_id.strip())


def _normalize_code(code: str) -> str:
    c = (code or "").strip()
    if c in ("LYM", "LYM#", "LYM%"):
        c = c.replace("LYM", "LYMPH")
    if c in ("NEUTP", "NEUTPCT"):
        return "NEUT%"
    if c in ("LYMPHP", "LYMPHPCT", "LYMPP", "LYMPPCT"):
        return "LYMPH%"
    if c in ("MXDP", "MXDPCT"):
        return "MXD%"
    return c


def _normalize_value(code: str, value: str) -> tuple[str, list[str]]:
    """
    Normalize a value; return (new_value, transforms_applied).
    Every transformation is recorded so the conversion audit can show it.
    """
    v = (value or "").strip()
    transforms: list[str] = []
    try:
        f = float(v.replace(",", "."))
        if v.replace(",", ".") != f"{f}":
            transforms.append(f"decimal-normalize({v!r}→{f})")
        if code == "HCT" and f <= 1.0:
            return f"{f * 100:.1f}", transforms + [f"HCT-frac-to-percent(×100: {f}→{f*100:.1f})"]
        if code == "PCT" and f < 0.01:
            return f"{f * 100:.2f}".rstrip("0").rstrip("."), transforms + ["PCT-frac-to-percent(×100)"]
    except (ValueError, TypeError):
        pass
    return v, transforms


def _parse_astm(data: str, device_name: str) -> Optional[Dict[str, Any]]:
    clean = "".join(c if c >= " " or c in "\r\n" else " " for c in data)
    lines = [l.strip() for l in clean.replace("\r", "\n").split("\n") if l.strip()]

    sample_id_raw = ""
    patient_name  = ""
    observations: List[Dict] = []

    for line in lines:
        line = re.sub(r"^\d+", "", line).strip()
        parts = line.split("|")
        if not parts:
            continue
        rec = parts[0].strip().upper()

        if rec == "P":
            if len(parts) > 2 and parts[2].strip():
                patient_name = parts[2].strip()

        elif rec == "O":
            sid = ""
            if len(parts) > 3 and parts[3].strip():
                sid = parts[3]
            elif len(parts) > 2 and parts[2].strip():
                sid = parts[2]
            sid = sid.replace("^", "").strip()
            if sid:
                sample_id_raw = sid

        elif rec == "R":
            if len(parts) < 4:
                continue
            code_field  = parts[2] if len(parts) > 2 else ""
            value_field = parts[3].strip() if len(parts) > 3 else ""
            unit_field  = parts[4].strip() if len(parts) > 4 else ""
            ref_field   = parts[5].strip() if len(parts) > 5 else ""
            flag_field  = parts[8].strip() if len(parts) > 8 else ""

            if not value_field:
                continue

            tokens = [t.strip() for t in code_field.split("^") if t.strip()]
            test_code = None
            for tok in reversed(tokens):
                if not tok.isdigit():
                    test_code = tok
                    break
            if not test_code:
                continue

            raw_code = test_code
            test_code = _normalize_code(test_code)
            value_norm, xforms = _normalize_value(test_code, value_field)

            flag = ""
            if flag_field:
                fu = flag_field.upper()
                if "H" in fu:
                    flag = "H"
                elif "L" in fu:
                    flag = "L"

            try:
                value_num: Optional[float] = float(re.sub(r"[<>= ]", "", value_norm))
            except (ValueError, TypeError):
                value_num = None

            ref_low = ref_high = None
            if "-" in ref_field:
                rp = ref_field.split("-", 1)
                try:
                    ref_low  = float(rp[0].strip())
                    ref_high = float(rp[1].strip())
                except ValueError:
                    pass

            mapped  = SYSMEX_TEST_MAP.get(test_code, {})
            de_name = mapped.get("name", test_code)
            de_unit = mapped.get("unit", unit_field) or unit_field
            loinc   = mapped.get("loinc", "99999-9")

            if ref_low is None and ref_high is None and "ref" in mapped:
                rp = mapped["ref"].split("-", 1)
                try:
                    ref_low  = float(rp[0].strip())
                    ref_high = float(rp[1].strip())
                except ValueError:
                    pass

            code_transforms = xforms.copy()
            if raw_code != test_code:
                code_transforms.append(f"code-rename({raw_code!r}→{test_code!r})")
            if unit_field and de_unit and unit_field != de_unit:
                code_transforms.append(f"unit-map({unit_field!r}→{de_unit!r})")

            observations.append({
                "analyte":     test_code,
                "raw_analyte": raw_code,
                "name_de":     de_name,
                "loinc":       loinc,
                "value":       value_norm,
                "raw_value":   value_field.strip(),
                "value_num":   value_num,
                "flag":        flag,
                "ref_low":     ref_low,
                "ref_high":    ref_high,
                "unit":        de_unit,
                "raw_unit":    unit_field.strip(),
                "transforms":  code_transforms,
            })

    if not observations:
        log.warning("[%s] No R records parsed from ASTM.", device_name)
        return None

    return {
        "timestamp":    datetime.now(),
        "sample_id":    sample_id_raw,
        "patient_id":   sample_id_raw,
        "patient_name": patient_name,
        "age":          None,
        "gender":       "",
        "department":   "",
        "disc_name":    device_name,
        "lot_id":       "",
        "device":       device_name,
        "observations": observations,
    }


class _SerialASTMProtocol(asyncio.Protocol):
    """
    Protocol per connessione seriale ASTM con il Sysmex.
    Il Sysmex manda ENQ → gateway risponde ACK → Sysmex manda frame STX..ETX.
    """
    def __init__(self, on_frame: Callable, device_name: str) -> None:
        self._on_frame   = on_frame
        self._device     = device_name
        self._buf        = bytearray()
        self._in_frame   = False
        self._transport  = None

    def connection_made(self, transport) -> None:
        self._transport = transport
        log.info("[%s] Serial ASTM connection established.", self._device)

    def data_received(self, data: bytes) -> None:
        for byte in data:
            b = bytes([byte])
            if byte == ENQ:
                # Sysmex chiede di mandare — rispondiamo ACK
                if self._transport:
                    self._transport.write(bytes([ACK]))
                log.debug("[%s] ENQ ricevuto -> ACK inviato", self._device)
            elif byte == STX:
                self._buf.clear()
                self._in_frame = True
            elif byte == ETX and self._in_frame:
                self._in_frame = False
                frame = bytes(self._buf)
                self._buf.clear()
                if frame.strip():
                    log.debug("[%s] Frame ASTM ricevuto (%d bytes)", self._device, len(frame))
                    _trace.record(self._device, "in", frame)
                    self._on_frame(frame)
                # Manda ACK per confermare ricezione frame
                if self._transport:
                    self._transport.write(bytes([ACK]))
            elif byte == EOT:
                log.debug("[%s] EOT ricevuto -- fine trasmissione", self._device)
                if self._transport:
                    self._transport.write(bytes([EOT]))
            elif self._in_frame:
                self._buf.extend(b)
                if not guard_buffer(self._buf, tag=self._device):
                    self._buf.clear()
                    self._in_frame = False

    def connection_lost(self, exc) -> None:
        if exc:
            log.error("[%s] Serial connection lost: %s", self._device, exc)
        else:
            log.warning("[%s] Serial connection closed.", self._device)


class SysmexReader:

    def __init__(
        self,
        host: str,
        port: int,
        queue: asyncio.Queue,
        device_name: str = "SYSMEX Haematologie",
        strip_id_suffix: bool = True,
        on_connect: Optional[Callable] = None,
        # Parametri seriale opzionali
        serial_port: Optional[str] = None,
        baudrate: int = 9600,
        # Timeout ENQ/read per device (Roche c111 richiede 15s, Sysmex 5s)
        read_timeout_seconds: float = 30.0,
        # ASTM E1381 mode over TCP/IP (see XQ-Series Host Interface Spec §6.4)
        astm_mode: str = "1381-02",
        # If True, do not respond to Q records (XP-300 is send-only)
        unidirectional: bool = False,
        # Long idle timeout — Sysmex holds the TCP session for hours between samples
        idle_timeout_seconds: float = 300.0,
    ) -> None:
        self._host          = host
        self._port          = port
        self._queue         = queue
        self._device_name   = device_name
        self._strip_suffix  = strip_id_suffix
        self._on_connect    = on_connect
        self._serial_port   = serial_port
        self._baudrate      = baudrate
        self._read_timeout  = float(read_timeout_seconds)
        self._astm_mode     = str(astm_mode)
        self._unidirectional = bool(unidirectional)
        self._idle_timeout  = float(idle_timeout_seconds)
        self._server: Optional[asyncio.AbstractServer] = None
        self._transport     = None
        self._stop_event    = asyncio.Event()

    async def open(self) -> None:
        if self._serial_port:
            await self._open_serial()
        else:
            await self._open_tcp()

    async def _open_serial(self) -> None:
        if not _SERIAL_AVAILABLE:
            raise RuntimeError("pyserial-asyncio non installato.")
        log.info("[%s] Serial ASTM: %s @ %d baud", self._device_name, self._serial_port, self._baudrate)
        loop = asyncio.get_event_loop()

        def _make_protocol():
            return _SerialASTMProtocol(self._on_serial_frame, self._device_name)

        self._transport, _ = await serial_asyncio.create_serial_connection(
            loop,
            _make_protocol,
            self._serial_port,
            baudrate = self._baudrate,
            bytesize = 8,
            parity   = "N",
            stopbits = 1,
        )
        log.info("[%s] Serial port open.", self._device_name)

    async def _open_tcp(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        log.info("[%s] Listening on %s:%d", self._device_name, self._host, self._port)

    async def run(self) -> None:
        await self._stop_event.wait()

    async def close(self) -> None:
        self._stop_event.set()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self._transport:
            self._transport.close()
        log.info("[%s] Reader closed.", self._device_name)

    def _on_serial_frame(self, raw_frame: bytes) -> None:
        """Callback per frame ASTM ricevuti via seriale."""
        _trace.record(self._device_name, raw_frame, direction="in", tag="astm-serial")
        if self._on_connect:
            self._on_connect()
        text = raw_frame.decode("ascii", errors="ignore")
        log.debug("[%s] ASTM frame (%d bytes): %r", self._device_name, len(raw_frame), text[:200])
        result = _parse_astm(text, self._device_name)
        if result:
            if self._strip_suffix and result["sample_id"]:
                result["sample_id"]  = _strip_suffix(result["sample_id"])
                result["patient_id"] = result["sample_id"]
            log.info("[%s] Parsed: sample=%s patient=%s analytes=%d",
                     self._device_name, result["sample_id"],
                     result["patient_id"], len(result["observations"]))
            safe_put_sync(self._queue, result, tag=self._device_name)
        else:
            log.warning("[%s] Frame senza dati utili.", self._device_name)

    def _build_no_order_response(self) -> bytes:
        """Risposta ASTM alla Query: nessun ordine pendente."""
        records = "H|\\^&|||LOC200GW||||||||E1394-97\rP|1\rL|1|N\r"
        frame = "1" + records
        chk = sum(ord(c) for c in frame) % 256
        return (bytes([STX]) +
                frame.encode("ascii") +
                bytes([ETX]) +
                "{:02X}".format(chk).encode("ascii") +
                bytes([CR, LF]))

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        log.info("[%s] Connection from %s (astm_mode=%s, unidirectional=%s)",
                 self._device_name, addr, self._astm_mode, self._unidirectional)

        # Enable TCP keep-alive so a truly dead peer is detected by the OS,
        # instead of us proactively closing a healthy idle connection (which
        # made the analyzer's own screen flash "TCP not connected").
        sock = writer.get_extra_info("socket")
        if sock is not None and hasattr(sock, "setsockopt"):
            try:
                sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_KEEPALIVE, 1)
            except OSError:
                pass

        if self._on_connect:
            self._on_connect()

        try:
            if self._astm_mode == "1381-95":
                await self._handle_client_e1381_95(reader, writer, addr)
            else:
                await self._handle_client_e1381_02(reader, writer, addr)
        except Exception as exc:
            log.warning("[%s] Client error %s: %s", self._device_name, addr, exc)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            log.info("[%s] Connection %s closed.", self._device_name, addr)

    # ── E1381-95 mode (raw records, no ENQ/ACK/EOT) ──────────────────────────
    # The Sysmex sends the whole message (H|... Q|... L|... or H|... P|... O|... R|... L|...)
    # as plain text terminated by CR. No handshake at any layer. We read until
    # we see an L record (message terminator) OR idle_timeout expires, whichever
    # comes first, then parse the buffer and stay connected for the next message.
    async def _handle_client_e1381_95(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, addr
    ) -> None:
        buf = bytearray()
        while True:
            # Idle between messages → keep the session open (see §6.4). Apply a
            # timeout only while a partial message is buffered, to flush a stalled
            # transfer instead of hanging on it.
            try:
                if buf:
                    data = await asyncio.wait_for(reader.read(4096), timeout=30)
                else:
                    data = await reader.read(4096)
            except asyncio.TimeoutError:
                log.debug("[%s] Stalled mid-message — flushing buffer", self._device_name)
                if buf:
                    await self._dispatch_buffer(buf, addr)
                return
            if not data:
                log.debug("[%s] Peer closed session", self._device_name)
                if buf:
                    await self._dispatch_buffer(buf, addr)
                return
            buf.extend(data)
            if not guard_buffer(buf, tag=self._device_name):
                log.warning("[%s] Oversized session buffer — dropping", self._device_name)
                buf.clear()
                continue
            # Message complete when we see an L record terminated by CR
            text = buf.decode("ascii", errors="ignore")
            if _has_terminator_l(text):
                log.debug("[%s] E1381-95 message complete (%d bytes)", self._device_name, len(buf))
                await self._dispatch_buffer(buf, addr)
                buf = bytearray()   # ready for the next message on same TCP session

    # ── E1381-02 mode (full framing) ─────────────────────────────────────────
    # Establishment: peer sends ENQ → we ACK (or NAK if busy).
    # Transfer:      peer sends [STX][F#][Text][ETX|ETB][CHK1][CHK2][CR][LF] → we ACK/NAK.
    # Termination:   peer sends EOT.
    # Same TCP session may carry multiple messages back-to-back.
    async def _handle_client_e1381_02(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, addr
    ) -> None:
        message_buf = bytearray()   # accumulated payload for current message
        while True:
            # When idle between messages (no partial message buffered) keep the
            # TCP session open indefinitely — per the XQ-Series spec §6.4 the IPU
            # holds the connection and sits idle between analyses; closing it made
            # the analyzer report "TCP not connected". Only apply the spec's
            # 30 s receiver timeout while a message is actually in progress.
            try:
                if message_buf:
                    first = await asyncio.wait_for(reader.read(1), timeout=30)
                else:
                    first = await reader.read(1)
            except asyncio.TimeoutError:
                log.warning("[%s] Receiver timeout mid-message — discarding partial",
                            self._device_name)
                message_buf = bytearray()
                continue
            if not first:
                log.debug("[%s] Peer closed session", self._device_name)
                return
            b = first[0]
            if b == ENQ:
                writer.write(bytes([ACK]))
                await writer.drain()
                log.debug("[%s] ENQ → ACK", self._device_name)
                continue
            if b == EOT:
                log.debug("[%s] EOT — message complete (%d bytes)", self._device_name, len(message_buf))
                if message_buf:
                    await self._dispatch_buffer(message_buf, addr)
                    message_buf = bytearray()
                continue
            if b == STX:
                # Read one full frame: [F#] [Text] [ETX|ETB] [CHK1] [CHK2] [CR] [LF]
                frame_body, ok = await self._read_astm_frame(reader)
                if not ok:
                    writer.write(bytes([NAK]))
                    await writer.drain()
                    continue
                writer.write(bytes([ACK]))
                await writer.drain()
                # frame_body[0] is F# (0-7); skip it; append the record text
                if len(frame_body) >= 2:
                    message_buf.extend(frame_body[1:] + b"\r")
                continue
            # Any other stray byte outside a frame — ignore per spec
            log.debug("[%s] Stray byte outside frame: 0x%02x", self._device_name, b)

    async def _read_astm_frame(self, reader: asyncio.StreamReader) -> tuple[bytes, bool]:
        """
        Read from after STX up to and including CR LF. Returns (body_bytes, ok).
        body_bytes = F# + Text (WITHOUT the STX, ETX/ETB, CHK1/2, CR, LF).
        Verifies checksum. Rejects oversized frames.
        """
        body = bytearray()
        try:
            while True:
                b = await asyncio.wait_for(reader.readexactly(1), timeout=15.0)
                body.extend(b)
                if b[0] in (ETX, ETB):
                    # Read CHK1 CHK2 CR LF
                    trailer = await asyncio.wait_for(reader.readexactly(4), timeout=5.0)
                    chk_ascii = trailer[0:2].decode("ascii", errors="replace")
                    # Verify checksum: sum(bytes after STX up to and incl. ETX/ETB) mod 256
                    chk_calc = sum(body) & 0xFF
                    try:
                        chk_recv = int(chk_ascii, 16)
                    except ValueError:
                        log.warning("[%s] Frame checksum non-hex: %r", self._device_name, chk_ascii)
                        return bytes(body), False
                    if chk_calc != chk_recv:
                        log.warning("[%s] Frame checksum mismatch: calc=%02x recv=%02x",
                                    self._device_name, chk_calc, chk_recv)
                        return bytes(body), False
                    return bytes(body[:-1]), True   # drop the ETX/ETB terminator
                if len(body) > MAX_FRAME_BYTES:
                    log.warning("[%s] Frame overflow > MAX_FRAME_BYTES", self._device_name)
                    return bytes(body), False
        except (asyncio.IncompleteReadError, asyncio.TimeoutError) as exc:
            log.warning("[%s] Frame read failed: %s", self._device_name, exc)
            return bytes(body), False

    async def _dispatch_buffer(self, buf: bytearray, addr) -> None:
        text = buf.decode("ascii", errors="ignore")
        log.debug("[%s] Raw message (%d bytes): %r", self._device_name, len(buf), text[:300])
        # Preserve raw payload for the conversion audit — signed hash + hex head.
        raw_payload_bytes = bytes(buf)

        has_query   = ("\rQ|" in text) or ("\nQ|" in text) or text.strip().startswith("Q|")
        has_results = ("\rR|" in text) or ("\nR|" in text)

        # Reply to an analysis-order query — but only if this device is bidirectional.
        if has_query and not has_results:
            if self._unidirectional:
                log.info("[%s] Query record received but device is unidirectional — ignoring",
                         self._device_name)
                return
            log.info("[%s] Query received — replying with no-order response", self._device_name)
            try:
                q_reader, q_writer = await asyncio.open_connection(addr[0], addr[1])
                q_writer.write(bytes([ENQ]))
                await q_writer.drain()
                ack = await asyncio.wait_for(q_reader.read(1), timeout=3.0)
                if ack and ack[0] == ACK:
                    q_writer.write(self._build_no_order_response())
                    await q_writer.drain()
                    q_writer.write(bytes([EOT]))
                    await q_writer.drain()
                    log.debug("[%s] No-order response sent", self._device_name)
                q_writer.close()
            except Exception as exc:
                log.debug("[%s] No-order response failed: %s", self._device_name, exc)
            return

        result = _parse_astm(text, self._device_name)
        if result:
            raw_sample = result["sample_id"]
            if self._strip_suffix and result["sample_id"]:
                result["sample_id"]  = _strip_suffix(result["sample_id"])
                result["patient_id"] = result["sample_id"]

            # Build conversion audit — every silent transform is recorded here.
            from src.common.conversion_audit import (
                ConversionAudit, ValueChange, sha_of, hex_head,
            )
            from src.common.plausibility import check as plausibility_check, is_double_conversion

            audit = ConversionAudit(
                device=self._device_name,
                sample_id_raw=raw_sample,
                sample_id_sent=result["sample_id"],
                patient_id_raw=raw_sample,
                patient_id_sent=result["patient_id"],
                raw_payload_sha=sha_of(raw_payload_bytes),
                raw_payload_hex=hex_head(raw_payload_bytes),
            )
            if raw_sample != result["sample_id"]:
                audit.add_warning(
                    f"sample_id changed: {raw_sample!r} → {result['sample_id']!r} (strip_suffix)"
                )
            for obs in result["observations"]:
                vc = ValueChange(
                    raw_code=obs.get("raw_analyte", obs["analyte"]),
                    sent_code=obs["analyte"],
                    raw_value=obs.get("raw_value", obs["value"]),
                    sent_value=obs["value"],
                    raw_unit=obs.get("raw_unit", obs["unit"]),
                    sent_unit=obs["unit"],
                    transforms=obs.get("transforms", []),
                )
                audit.add_change(vc)
                # Plausibility check
                ok, reason = plausibility_check(obs["analyte"], obs.get("value_num"), obs["unit"])
                if not ok:
                    audit.add_warning(reason)
                    obs["flag"] = (obs.get("flag") or "") + "TC"   # technical control
                # Double-conversion detector
                try:
                    raw_num = float(vc.raw_value.replace(",", "."))
                except (ValueError, TypeError):
                    raw_num = None
                if is_double_conversion(obs["analyte"], raw_num, obs.get("value_num")):
                    audit.add_warning(
                        f"suspicious ×100 on {obs['analyte']}: raw {raw_num} → sent {obs['value_num']}"
                    )
            result["conversion_audit"] = audit.to_json()
            if audit.warnings:
                log.warning("[%s] Conversion audit warnings for sample=%s: %s",
                            self._device_name, result["sample_id"], "; ".join(audit.warnings))
                try:
                    from src.common.alerts import fire as _fire
                    _fire("warning", "plausibility",
                          f"{self._device_name} sample {result['sample_id']}: "
                          f"{len(audit.warnings)} warning(s)",
                          {"device": self._device_name,
                           "sample_id": result["sample_id"],
                           "warnings": audit.warnings})
                except Exception:
                    pass

            log.info("[%s] Parsed: sample=%s patient=%s analytes=%d transforms=%d warnings=%d",
                     self._device_name, result["sample_id"], result["patient_id"],
                     len(result["observations"]),
                     sum(len(o.get("transforms", [])) for o in result["observations"]),
                     len(audit.warnings))
            safe_put_sync(self._queue, result, tag=self._device_name)
        else:
            log.warning("[%s] No usable data (buffer len=%d)", self._device_name, len(buf))
