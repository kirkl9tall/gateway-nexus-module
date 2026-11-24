"""
Bidirectional order receiver.

Listens on an MLLP TCP port for ORM^O01 / OML^O21 messages from the PIS
and stores them in a queue for the corresponding analyzer to fetch when
it queries for pending orders.

Design:
  * One MLLP server per configured `order_listen_port`.
  * Parsed orders go into an in-memory + on-disk queue keyed by
    (target_analyzer, sample_id).
  * The analyzer's reader/adapter pulls pending orders when the device
    sends a QUERY (ASTM Q record, HL7 QBP^Q11, etc.).

For now we implement the LISTEN + STORE part; the actual "push to device"
side depends on each analyzer's protocol -- adapters register a callback.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("loc200.orders")

VT = b"\x0B"
FS = b"\x1C"
CR = b"\x0D"

_ORDERS_DIR = Path("logs/orders")


class Order:
    __slots__ = ("sample_id", "patient_id", "analyzer", "tests",
                 "priority", "received_at", "raw_hl7")

    def __init__(self, sample_id: str, patient_id: str, analyzer: str,
                 tests: List[str], priority: str = "R",
                 raw_hl7: str = "") -> None:
        self.sample_id  = sample_id
        self.patient_id = patient_id
        self.analyzer   = analyzer
        self.tests      = tests
        self.priority   = priority  # R=routine, S=stat, A=asap
        self.received_at = datetime.now()
        self.raw_hl7    = raw_hl7

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_id":   self.sample_id,
            "patient_id":  self.patient_id,
            "analyzer":    self.analyzer,
            "tests":       self.tests,
            "priority":    self.priority,
            "received_at": self.received_at.isoformat(),
        }


class OrderStore:
    """
    Thread-safe in-memory + disk-persistent order queue.
    Analyzers query for pending orders by sample_id or by wildcard.
    """

    def __init__(self, path: Path = _ORDERS_DIR) -> None:
        self._path = path
        self._path.mkdir(parents=True, exist_ok=True)
        self._orders: Dict[str, Order] = {}   # key = sample_id
        self._lock = asyncio.Lock()
        self._load()

    def _load(self) -> None:
        for f in sorted(self._path.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                o = Order(
                    sample_id=d["sample_id"], patient_id=d["patient_id"],
                    analyzer=d["analyzer"], tests=d.get("tests", []),
                    priority=d.get("priority", "R"),
                )
                self._orders[o.sample_id] = o
            except Exception as exc:
                log.warning("bad order file %s: %s", f.name, exc)

    async def add(self, order: Order) -> None:
        async with self._lock:
            self._orders[order.sample_id] = order
            self._persist(order)
        log.info("Order received: sample=%s analyzer=%s tests=%s prio=%s",
                 order.sample_id, order.analyzer, order.tests, order.priority)

    def _persist(self, order: Order) -> None:
        f = self._path / f"{_slug(order.sample_id)}.json"
        f.write_text(json.dumps(order.to_dict(), indent=2), encoding="utf-8")

    async def get_for_analyzer(self, analyzer: str,
                                sample_id: Optional[str] = None) -> List[Order]:
        async with self._lock:
            out = []
            for o in self._orders.values():
                if o.analyzer and o.analyzer != analyzer:
                    continue
                if sample_id and o.sample_id != sample_id:
                    continue
                out.append(o)
            return out

    async def complete(self, sample_id: str) -> None:
        """Remove an order once the analyzer has processed it."""
        async with self._lock:
            self._orders.pop(sample_id, None)
            f = self._path / f"{_slug(sample_id)}.json"
            if f.exists():
                f.unlink()

    def snapshot(self) -> List[Dict[str, Any]]:
        return [o.to_dict() for o in self._orders.values()]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:80] or "unknown"


# ── HL7 v2 ORM^O01 / OML^O21 parser ──────────────────────────────────────────

def parse_order_hl7(text: str) -> Optional[Order]:
    """Parse an incoming order message. Returns None if not a recognisable order."""
    segments = [s.strip() for s in text.replace("\r\n", "\r").split("\r") if s.strip()]
    if not segments or not segments[0].startswith("MSH|"):
        return None

    # Extract message type from MSH-9
    msh = segments[0].split("|")
    if len(msh) < 9:
        return None
    msg_type = msh[8].split("^")[0]
    if msg_type not in ("ORM", "OML"):
        return None

    patient_id = ""
    sample_id  = ""
    tests: List[str] = []
    analyzer   = ""
    priority   = "R"

    for seg in segments:
        parts = seg.split("|")
        name = parts[0]
        if name == "PID":
            if len(parts) > 3 and parts[3]:
                patient_id = parts[3].split("^")[0].strip()
            elif len(parts) > 2 and parts[2]:
                patient_id = parts[2].split("^")[0].strip()
        elif name == "ORC":
            # ORC-2 (placer order number) or ORC-3 (filler order number) = sample ID
            if len(parts) > 2 and parts[2]:
                sample_id = parts[2].split("^")[0].strip()
            elif len(parts) > 3 and parts[3]:
                sample_id = parts[3].split("^")[0].strip()
            # ORC-7 = timing/quantity, ORC-10 = entered by (skip)
        elif name == "OBR":
            if len(parts) > 2 and parts[2] and not sample_id:
                sample_id = parts[2].split("^")[0].strip()
            # OBR-4 = universal service ID = the test/panel requested
            if len(parts) > 4 and parts[4]:
                code = parts[4].split("^")[0].strip()
                if code:
                    tests.append(code)
            # OBR-5 = priority
            if len(parts) > 5 and parts[5]:
                priority = parts[5].strip().upper()[:1] or "R"
            # OBR-24 = diagnostic serv sect ID = which analyzer group (LAB, HEM, CHEM...)
            if len(parts) > 24 and parts[24] and not analyzer:
                analyzer = parts[24].split("^")[0].strip()
        elif name == "TQ1":
            # HL7 v2.5+ timing/priority segment
            if len(parts) > 9 and parts[9] and priority == "R":
                priority = parts[9].strip().upper()[:1] or "R"

    if not sample_id and not tests:
        return None
    return Order(
        sample_id  = sample_id or patient_id or "UNKNOWN",
        patient_id = patient_id,
        analyzer   = analyzer,
        tests      = tests,
        priority   = priority,
        raw_hl7    = text,
    )


# ── MLLP listener ─────────────────────────────────────────────────────────────

class OrderReceiver:
    """MLLP TCP listener that accepts orders and stores them in an OrderStore."""

    def __init__(
        self,
        host: str,
        port: int,
        store: OrderStore,
        on_order: Optional[Callable[[Order], None]] = None,
    ) -> None:
        self._host   = host
        self._port   = port
        self._store  = store
        self._on_order = on_order
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port,
        )
        log.info("Order receiver listening on %s:%d (MLLP)",
                 self._host, self._port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader,
                              writer: asyncio.StreamWriter) -> None:
        addr = writer.get_extra_info("peername")
        buf  = bytearray()
        in_msg = False
        try:
            while True:
                data = await asyncio.wait_for(reader.read(4096), timeout=30.0)
                if not data:
                    break
                for byte in data:
                    b = bytes([byte])
                    if b == VT:
                        buf.clear()
                        in_msg = True
                    elif b == FS and in_msg:
                        in_msg = False
                        text = buf.decode("utf-8", errors="replace")
                        buf.clear()
                        order = parse_order_hl7(text)
                        if order:
                            await self._store.add(order)
                            if self._on_order:
                                try:
                                    self._on_order(order)
                                except Exception as exc:
                                    log.warning("on_order callback failed: %s", exc)
                            writer.write(_build_ack(text, "AA"))
                        else:
                            writer.write(_build_ack(text, "AR"))
                        await writer.drain()
                    elif in_msg:
                        buf.extend(b)
        except asyncio.TimeoutError:
            pass
        except Exception as exc:
            log.warning("order client %s: %s", addr, exc)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


def _build_ack(orig: str, code: str = "AA") -> bytes:
    """Build a minimal ACK^O01 for the incoming order."""
    from datetime import datetime as _dt
    ctrl_new = "ACK" + _dt.now().strftime("%H%M%S%f")[:16]
    ts       = _dt.now().strftime("%Y%m%d%H%M%S")
    msh = next((l for l in orig.split("\r") if l.startswith("MSH")), "")
    fields = msh.split("|")
    sending_app = fields[2] if len(fields) > 2 else "PIS"
    orig_ctrl   = fields[9] if len(fields) > 9 else ctrl_new
    body = (
        f"MSH|^~\\&|JMNX_GW|PRAXIS|{sending_app}|PIS|{ts}||ACK^O01|"
        f"{ctrl_new}|P|2.5\r"
        f"MSA|{code}|{orig_ctrl}|Order received\r"
    )
    return VT + body.encode("utf-8") + FS + CR


# ── Singleton ───────────────────────────────────────────────────────────────

_global_store: Optional[OrderStore] = None


def get_store() -> OrderStore:
    global _global_store
    if _global_store is None:
        _global_store = OrderStore()
    return _global_store
