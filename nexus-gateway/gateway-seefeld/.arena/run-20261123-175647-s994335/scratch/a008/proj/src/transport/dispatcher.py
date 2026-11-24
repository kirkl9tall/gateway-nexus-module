"""
src/transport/dispatcher.py
Routes HL7 messages to one or more PIS/LIS targets.

Delivery modes:
  MLLP/TCP  → Vitomed, curaMED, Aeskulap, Axenita, DnaMed, generic
  File-drop → WinMed (watch-folder *.hl7), Tomedo (import-folder)

Debug:
  Set log_level: "DEBUG" in gateway.yaml to see:
  - Full MLLP ACK response from every PIS
  - Delivery timing (ms) per target
  - Retry details with exception trace
  - File-drop path + byte size
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from config.settings import GatewayConfig, PISTarget
from src.hl7.builder import HL7Message
from src.hl7.rewrites import apply_rewrites
from src.hl7.validator import validate_hl7_message
from src.debug import log_mllp_ack, perf
from src.security.audit import audit_message_failed, audit_message_sent
from src.security.secrets import resolve_target_secrets
from src.transport.circuit_breaker import BreakerRegistry
from src.common import trace as _trace
from src.common import telemetry as _otel

log = logging.getLogger("loc200.dispatcher")


class DispatchResult:
    """Summary of a dispatch call -- used by the gateway to decide DLQ."""

    __slots__ = ("total", "succeeded", "failed", "skipped_open", "errors")

    def __init__(self) -> None:
        self.total: int = 0
        self.succeeded: list[str] = []
        self.failed: list[str] = []
        self.skipped_open: list[str] = []
        self.errors: dict[str, str] = {}

    @property
    def all_failed(self) -> bool:
        return self.total > 0 and not self.succeeded

    def to_dict(self) -> dict:
        return {
            "total":         self.total,
            "succeeded":     list(self.succeeded),
            "failed":        list(self.failed),
            "skipped_open":  list(self.skipped_open),
            "errors":        dict(self.errors),
        }


class Dispatcher:

    def __init__(self, config: GatewayConfig) -> None:
        self._targets: list[PISTarget] = []
        for t in config.targets:
            if not t.enabled:
                continue
            resolved = self._resolve_secrets(t)
            self._targets.append(resolved)
        self._retry_max  = config.retry_max_attempts
        self._retry_delay = config.retry_delay_seconds
        self._breakers = BreakerRegistry(
            threshold=getattr(config, "breaker_threshold", 5),
            recovery_timeout=getattr(config, "breaker_recovery_seconds", 60.0),
        )
        # Held for FHIR builder (LOINC + facility)
        self._hl7_cfg = getattr(config, "hl7", None)
        log.info(
            "Dispatcher initialised: %d target(s) enabled: %s",
            len(self._targets),
            [t.name for t in self._targets] or ["(none)"],
        )

    def targets_snapshot(self) -> list[dict]:
        """Read-only view for the Web UI (name, type, breaker state)."""
        breaker_state = self._breakers.snapshot()
        return [
            {
                "name":    t.name,
                "type":    t.type,
                "breaker": breaker_state.get(t.name, {"state": "closed"}),
            }
            for t in self._targets
        ]

    def reload_from(self, config: GatewayConfig) -> None:
        """Hot-reload: swap the enabled target list."""
        new_targets = []
        for t in config.targets:
            if not t.enabled:
                continue
            new_targets.append(self._resolve_secrets(t))
        self._targets = new_targets
        self._retry_max  = config.retry_max_attempts
        self._retry_delay = config.retry_delay_seconds
        log.info("Dispatcher reloaded: %d target(s) enabled: %s",
                 len(self._targets), [t.name for t in self._targets] or ["(none)"])

    @staticmethod
    def _resolve_secrets(target: PISTarget) -> PISTarget:
        """Load SFTP credentials from secrets.env / env vars when available."""
        fields = {
            "sftp_pass": target.sftp_pass or "",
            "sftp_user": target.sftp_user or "",
            "sftp_host": target.sftp_host or "",
        }
        if not any(fields.values()):
            return target
        resolved = resolve_target_secrets(target.name, fields)
        updates = {}
        if resolved.get("sftp_pass"):
            updates["sftp_pass"] = resolved["sftp_pass"]
        if resolved.get("sftp_user"):
            updates["sftp_user"] = resolved["sftp_user"]
        if resolved.get("sftp_host"):
            updates["sftp_host"] = resolved["sftp_host"]
        return target.model_copy(update=updates) if updates else target

    async def dispatch(self, msg: HL7Message, result: Dict[str, Any]) -> DispatchResult:
        """
        Fan-out to all enabled targets concurrently.

        Returns a DispatchResult so the caller (Gateway) can decide whether
        to write the message to the dead-letter queue.
        """
        summary = DispatchResult()
        if not self._targets:
            log.warning("No enabled targets -- message discarded (sample=%s).",
                        result.get("sample_id", "?"))
            return summary

        summary.total = len(self._targets)
        log.debug("Dispatching to %d target(s): %s",
                  len(self._targets), [t.name for t in self._targets])

        # Filter out targets whose circuit breaker is OPEN
        eligible: list[PISTarget] = []
        for target in self._targets:
            breaker = self._breakers.get(target.name)
            if not breaker.allow():
                summary.skipped_open.append(target.name)
                log.warning(
                    "[%s] Circuit breaker OPEN -- skipping delivery (retry in %.0fs).",
                    target.name,
                    max(0, breaker.recovery_timeout - (time.time() - breaker.opened_at)),
                )
                continue
            eligible.append(target)

        tasks = [
            asyncio.create_task(
                self._deliver_with_retry(target, msg, result),
                name=f"deliver-{target.name}",
            )
            for target in eligible
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        device = result.get("device", result.get("disc_name", "?"))
        sample = result.get("sample_id", "?")
        analytes = len(result.get("observations", []))

        for target, res in zip(eligible, results, strict=True):
            if isinstance(res, Exception):
                self._breakers.record_failure(target.name)
                _otel.count_dispatched(target.name, success=False)
                summary.failed.append(target.name)
                summary.errors[target.name] = str(res)
                log.error(
                    "Delivery to [%s] ultimately FAILED after %d attempts: %s",
                    target.name, self._retry_max, res,
                    exc_info=log.isEnabledFor(logging.DEBUG),
                )
                audit_message_failed(device, sample, target.name, str(res))
            else:
                self._breakers.record_success(target.name)
                _otel.count_dispatched(target.name, success=True)
                summary.succeeded.append(target.name)
                audit_message_sent(device, sample, target.name, analytes)

        # Also count skipped_open as failures for the summary
        for name in summary.skipped_open:
            summary.failed.append(name)
            summary.errors[name] = "circuit breaker open"

        return summary

    # ── Retry wrapper ─────────────────────────────────────────────────────────

    async def _deliver_with_retry(
        self, target: PISTarget, msg: HL7Message, result: Dict[str, Any]
    ) -> None:
        """
        Exponential backoff: delay doubles on each attempt, capped at 60s.
        Small jitter (+/- 25%) prevents thundering-herd when many targets
        recover at once.
        """
        import random
        last_exc: Exception | None = None
        base_delay = max(0.1, self._retry_delay)
        for attempt in range(1, self._retry_max + 1):
            t0 = time.perf_counter()
            try:
                await self._deliver_once(target, msg, result)
                elapsed = (time.perf_counter() - t0) * 1000
                perf.record(target.name, elapsed, success=True)
                if attempt > 1:
                    log.info(
                        "[%s] Delivery succeeded on attempt %d/%d  (%.0f ms)",
                        target.name, attempt, self._retry_max, elapsed,
                    )
                else:
                    log.info("[%s] Delivered OK  (%.0f ms)", target.name, elapsed)
                return

            except Exception as exc:
                elapsed = (time.perf_counter() - t0) * 1000
                perf.record(target.name, elapsed, success=False)
                last_exc = exc
                log.warning(
                    "[%s] Attempt %d/%d FAILED (%.0f ms): %s",
                    target.name, attempt, self._retry_max, elapsed, exc,
                    exc_info=log.isEnabledFor(logging.DEBUG),
                )
                if attempt < self._retry_max:
                    delay = min(60.0, base_delay * (2 ** (attempt - 1)))
                    delay *= (1.0 + random.uniform(-0.25, 0.25))
                    log.debug("[%s] Retrying in %.1f s (exponential backoff) ...",
                              target.name, delay)
                    await asyncio.sleep(delay)

        raise RuntimeError(
            f"All {self._retry_max} delivery attempts to [{target.name}] failed. "
            f"Last error: {last_exc}"
        )

    # ── Routing ───────────────────────────────────────────────────────────────

    async def _deliver_once(
        self, target: PISTarget, msg: HL7Message, result: Dict[str, Any]
    ) -> None:
        t = target.type
        if t in ("vitomed", "curamed", "aeskulap", "axenita",
                 "dnamed", "generic_hl7_mllp"):
            await self._send_mllp(target, msg)
        elif t == "winmed":
            await self._send_file(target, msg)
        elif t == "tomedo":
            if getattr(target, "sftp_host", None):
                await self._send_sftp(target, msg, result)
            elif target.watch_folder:
                await self._send_file(target, msg)
            else:
                await self._send_mllp(target, msg)
        elif t == "fhir_r4":
            await self._send_fhir(target, result)
        else:
            raise ValueError(f"Unknown target type: {t!r}")

    async def _send_fhir(self, target: PISTarget, result: Dict[str, Any]) -> None:
        if not target.fhir_endpoint:
            raise ValueError(f"[{target.name}] 'fhir_endpoint' required for fhir_r4")
        from src.hl7.fhir_builder import FHIRBundleBuilder
        from src.transport.fhir_dispatcher import FHIRDispatcher
        # We need the HL7Config for LOINC map + facility -- reuse from dispatcher's held reference
        from config.settings import HL7Config
        # Use a defaulted HL7Config if not attached (this is safe: FHIR only uses loinc + facility)
        hcfg = getattr(self, "_hl7_cfg", None) or HL7Config()
        bundle = FHIRBundleBuilder(hcfg).build(result)
        client = FHIRDispatcher(
            endpoint=target.fhir_endpoint,
            token=target.fhir_token,
            verify_tls=target.fhir_verify_tls,
            timeout=target.mllp_timeout,
        )
        await client.dispatch(bundle)

    # ── MLLP ─────────────────────────────────────────────────────────────────

    def _testo_verificato(self, target: PISTarget, msg: HL7Message) -> str:
        """
        Applica le riscritture del target e valida il messaggio.

        Unico punto per tutti i canali di consegna. Prima MLLP e file-drop lo
        facevano ciascuno per conto suo e SFTP -- cioe' Tomedo, l'unico usato
        in produzione -- non lo faceva affatto: le regole in
        config/rewrites/tomedo.yaml non venivano mai applicate e un messaggio
        malformato partiva senza alcun controllo.
        """
        raw = msg.to_string()
        riscritto = apply_rewrites(raw, target.name)
        if riscritto != raw:
            # Quanti segmenti sono cambiati. Il conteggio precedente cercava
            # la stringa "\r" (backslash + r) invece del ritorno a capo, e
            # quindi annunciava sempre "Applied 0 rewrite rule(s)".
            cambiati = sum(1 for prima, dopo
                           in zip(raw.split(chr(13)), riscritto.split(chr(13)), strict=False)
                           if prima != dopo)
            log.info("[%s] Riscritture applicate: %d segmento/i modificato/i",
                     target.name, cambiati)
        report = validate_hl7_message(riscritto)
        for w in report.warnings:
            log.debug("[%s] validator WARN %s: %s",
                      target.name, w.segment, w.message)
        if not report.is_valid:
            msgs = "; ".join(f"{e.segment}: {e.message}" for e in report.errors)
            raise ValueError(f"HL7 validation failed: {msgs}")
        return riscritto

    def _preview_bytes(self, target: PISTarget, msg: HL7Message) -> bytes:
        """
        Produce the MLLP payload for `target`, applying per-target rewrites
        and running the compliance validator. Warnings are logged; errors
        raise so retry / DLQ kicks in immediately (no burnt round-trip).
        """
        rewritten = self._testo_verificato(target, msg)
        # Wrap in MLLP framing manually so rewrites are honoured
        return b"\x0B" + rewritten.encode(msg._codec, errors="replace") + b"\x1C\x0D"

    async def _send_mllp(self, target: PISTarget, msg: HL7Message) -> None:
        """
        Open a fresh TCP connection per message.

        NOTE: MLLP has no keep-alive semantics in HL7 v2 and most PIS/LIS
        close the connection after each transaction. Pooling would be a
        micro-optimization that risks half-closed sockets. If a customer
        installation has >100 msg/min sustained, revisit with keep-alive
        negotiation at the socket level.
        """
        if not target.host or not target.port:
            raise ValueError(
                f"[{target.name}] 'host' and 'port' are required for MLLP."
            )

        payload = self._preview_bytes(target, msg)
        log.debug("[%s] MLLP connect → %s:%d  payload=%d bytes",
                  target.name, target.host, target.port, len(payload))

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(target.host, target.port),
            timeout=target.mllp_timeout,
        )
        log.debug("[%s] TCP connected.", target.name)
        try:
            writer.write(payload)
            await writer.drain()
            _trace.record(f"target:{target.name}", "out", payload)
            log.debug("[%s] Payload sent, waiting for ACK …", target.name)

            ack_raw = await asyncio.wait_for(
                reader.read(4096), timeout=target.mllp_timeout
            )
            _trace.record(f"target:{target.name}", "in", ack_raw)
            log_mllp_ack(ack_raw, target.name)   # full ACK only in DEBUG
            self._check_ack(
                ack_raw.decode("utf-8", errors="replace"),
                target.name,
                expected_control_id=msg.control_id,
            )

        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    def _check_ack(ack: str, target_name: str, expected_control_id: str | None = None) -> None:
        """
        Parse MSA segment: AA=accept, AE=app-error, AR=app-reject.

        HL7 segments are separated by CR (\\r); some peers emit CRLF or LF.
        MSA-2 must match the MSH-10 (message control ID) of the sent message —
        otherwise the ACK belongs to a different transaction.
        """
        if "MSA" not in ack:
            log.debug("[%s] No MSA in ACK — assuming accepted.", target_name)
            return
        # Normalise segment terminators — HL7 spec uses \r; be liberal on input.
        raw = ack.replace("\r\n", "\r").replace("\n", "\r")
        for line in raw.split("\r"):
            if not line.startswith("MSA"):
                continue
            fields = line.split("|")
            code   = fields[1].strip() if len(fields) > 1 else "??"
            msg_id = fields[2].strip() if len(fields) > 2 else ""
            if expected_control_id and msg_id and msg_id != expected_control_id:
                log.warning(
                    "[%s] ACK control-id mismatch — sent=%s got=%s (code=%s)",
                    target_name, expected_control_id, msg_id, code,
                )
                raise RuntimeError(
                    f"[{target_name}] ACK control-id mismatch "
                    f"(sent={expected_control_id!r}, got={msg_id!r})"
                )
            if code == "AA":
                log.debug("[%s] ACK AA — accepted (msg=%s).", target_name, msg_id or "?")
            elif code == "CA":  # HL7 v2.5 — Commit Accept
                log.debug("[%s] ACK CA — commit accepted.", target_name)
            elif code == "AE":
                raise RuntimeError(
                    f"[{target_name}] ACK AE — Application Error for msg {msg_id or '?'}"
                )
            elif code == "AR":
                raise RuntimeError(
                    f"[{target_name}] ACK AR — Application Reject for msg {msg_id or '?'}"
                )
            elif code in ("CE", "CR"):
                raise RuntimeError(
                    f"[{target_name}] ACK {code} — commit failure for msg {msg_id or '?'}"
                )
            else:
                log.warning("[%s] Unknown ACK code %r for msg %s.",
                            target_name, code, msg_id or "?")
            return
        log.debug("[%s] MSA present but not parsed.", target_name)

    # ── File-drop ─────────────────────────────────────────────────────────────

    async def _send_file(self, target: PISTarget, msg: HL7Message) -> None:
        folder = Path(target.watch_folder)
        loop = asyncio.get_event_loop()
        # La cartella e' spesso una condivisione di rete (//SERVER/Laboreingang).
        # Crearla in modo bloccante congelava l'intero ciclo di eventi quando il
        # server era lento o irraggiungibile: tutti gli analizzatori restavano
        # appesi per colpa di un solo destinatario.
        await loop.run_in_executor(
            None, lambda: folder.mkdir(parents=True, exist_ok=True))

        ts       = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"JMNX_{ts}{target.file_extension}"
        dest     = folder / filename
        raw = self._testo_verificato(target, msg)
        content = raw.replace("\r", "\r\n").encode(target.file_encoding, errors="replace")

        log.debug("[%s] File-drop → %s  (%d bytes, encoding=%s)",
                  target.name, dest, len(content), target.file_encoding)

        tmp  = dest.with_suffix(".tmp")
        await loop.run_in_executor(None, lambda: _atomic_write(tmp, dest, content))
        log.info("[%s] File written → %s", target.name, dest.name)


    async def _send_sftp(self, target, msg, result: Dict[str, Any]) -> None:
        from src.transport.sftp_dispatcher import SFTPDispatcher
        d = SFTPDispatcher(
            host=target.sftp_host,
            port=getattr(target, "sftp_port", 22),
            username=getattr(target, "sftp_user", ""),
            password=getattr(target, "sftp_pass", ""),
            remote_path=getattr(target, "sftp_remote_path", "/tmp"),
            file_encoding=target.file_encoding,
            file_extension=getattr(target, "file_extension", ".hl7"),
        )
        # Le riscritture e la validazione valgono anche qui. Il testo gia'
        # verificato viene passato al dispatcher, che altrimenti userebbe il
        # messaggio grezzo; la codifica resta quella dichiarata in MSH-18.
        await d.dispatch(msg, result,
                         testo_verificato=self._testo_verificato(target, msg))

def _atomic_write(tmp: Path, dest: Path, content: bytes) -> None:
    tmp.write_bytes(content)
    os.replace(tmp, dest)


