"""
src/gateway.py
Central orchestrator: all readers → shared queue → builder → dispatcher.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from config.settings import GatewayConfig
from src.devices.registry import DeviceRegistry
from src.hl7.builder import HL7Builder
from src.transport.dispatcher import Dispatcher
from src.debug import log_parse_result, log_hl7, perf
from src.common.dead_letter import write_dead_letter
from src.common import backpressure as _bp
from src.common import alerting as _alerts
from src.common import history as _history_db
from src.common import telemetry as _otel
from src.common import privacy as _privacy
from src.common import retention as _retention
from src.common import wal as _wal

log = logging.getLogger("loc200.gateway")


def _wal_replay_to_dlq(uuid: str, target: str, control_id: str, payload: bytes) -> str:
    """
    Called for every WAL orphan found at boot.

    Semantics: we never blindly re-send at startup — the LIS may already
    have accepted the message (that's why we crashed *after* the send but
    before the ACK bookkeeping). Instead we hand the payload to the DLQ
    with a "wal_recovered_at_boot" reason so an operator can inspect and
    replay from the WebUI DLQ page. Then WAL clears the entry.
    """
    try:
        body = payload.decode("utf-8", errors="replace")
    except Exception:
        body = ""
    sample_id = ""
    for seg in body.split("\r"):
        if seg.startswith("PID"):
            parts = seg.split("|")
            if len(parts) > 3:
                sample_id = parts[3].split("^", 1)[0]
            break
    write_dead_letter(
        hl7_body=body,
        control_id=control_id,
        sample_id=sample_id,
        device="?",
        targets=[target],
        errors={"__wal_recovery__": "gateway restarted while message was in-flight"},
        reason="wal_recovered_at_boot",
    )
    log.warning(
        "WAL orphan quarantined to DLQ: target=%s control_id=%s uuid=%s",
        target, control_id, uuid[:8],
    )
    return "skip"  # tells recover_at_boot() to just delete the entry

_SEEN_FILE = Path("logs/seen_samples.json")


_SEEN_TTL_SECONDS   = 86400
_SEEN_SAVE_INTERVAL = 60     # write to disk at most once per minute
_SEEN_SAVE_EVERY_N  = 50     # or every N new samples


def _load_seen() -> Dict[str, str]:
    """Carica i sample già processati dal disco, filtrando entry > TTL o corrotte."""
    if not _SEEN_FILE.exists():
        return {}
    try:
        data = json.loads(_SEEN_FILE.read_text())
    except Exception as exc:
        log.warning("seen_samples.json illeggibile: %s — riparto vuoto.", exc)
        return {}
    now = datetime.now()
    clean: Dict[str, str] = {}
    for k, v in data.items():
        try:
            if (now - datetime.fromisoformat(v)).total_seconds() < _SEEN_TTL_SECONDS:
                clean[k] = v
        except (ValueError, TypeError):
            continue  # skip corrupt entry
    return clean


def _save_seen(seen: Dict[str, str]) -> None:
    """Salva i sample processati su disco (write atomica)."""
    try:
        _SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _SEEN_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(seen, indent=2))
        import os as _os
        _os.replace(tmp, _SEEN_FILE)
    except Exception as e:
        log.debug("Impossibile salvare seen_samples.json: %s", e)


def _prune_seen(seen: Dict[str, str]) -> Dict[str, str]:
    now = datetime.now()
    out: Dict[str, str] = {}
    for k, v in seen.items():
        try:
            if (now - datetime.fromisoformat(v)).total_seconds() < _SEEN_TTL_SECONDS:
                out[k] = v
        except (ValueError, TypeError):
            continue
    return out


class Gateway:
    def __init__(self, config: GatewayConfig) -> None:
        self._config     = config
        self._queue:     asyncio.Queue = asyncio.Queue(maxsize=config.queue_maxsize)
        self._builder    = HL7Builder(config.hl7)
        self._dispatcher = Dispatcher(config)
        self._running    = False
        self._stopping   = False
        self._stopped    = False
        self._discovery_task: Optional[asyncio.Task] = None
        self._run_tasks: List[asyncio.Task] = []
        self._start_time = 0.0
        self._stats      = {"results_today": 0, "results_total": 0,
                            "errors_today": 0, "last_result": None}
        self._history:   List[Dict] = []
        self._last_seen: Dict[str, str] = {}
        # Analizzatori configurati che non hanno ancora inviato niente da
        # quando il gateway e' partito. Senza questo insieme un apparecchio
        # che non ha MAI parlato non compariva in _last_seen, quindi la
        # sorveglianza del silenzio non lo guardava nemmeno: il Sysmex
        # XQ-320 e' rimasto muto per giorni senza un solo allarme.
        self._mai_sentiti: set[str] = set()
        self._connected: Dict[str, str] = {}
        self._seen:      Dict[str, str] = _load_seen()  # caricato dal disco
        self._seen_dirty_count: int = 0
        self._seen_last_save:   float = time.time()
        # Watchdog: last auto-restart attempt per reader, and backoff seconds
        self._reader_restart_last: Dict[str, float] = {}
        self._reader_restart_backoff: Dict[str, float] = {}
        self._status_last_write: float = 0.0
        self._status_min_interval: float = 2.0  # write status.json at most every 2s
        self._registry:  DeviceRegistry = DeviceRegistry(
            config, self._queue, on_connect=self._on_connect
        )
        self._readers:   List[Any] = []

        log.info("Filtro duplicati: %d sample caricati dal disco.", len(self._seen))

    def _on_connect(self, device_name: str) -> None:
        self._connected[device_name] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self._write_status()

    async def start(self) -> None:
        log.info("Starting JerumedNexus Gateway ...")
        self._setup_file_logging()
        _privacy.install_log_filter()    # hash patient_id/sample_id in all logs
        _alerts.configure_from(self._config)
        _otel.configure()   # no-op if OTEL_EXPORTER_OTLP_ENDPOINT not set
        _retention.start_background()    # daily purge of expired data
        # Exactly-once promise: sweep the WAL for messages that were
        # in-flight when the previous process died and quarantine them.
        # Runs synchronously — small (SQLite) and never touches the
        # network, so it can't hang boot.
        try:
            report = _wal.recover_at_boot(_wal_replay_to_dlq)
            if report.get("total"):
                log.warning("WAL boot recovery: %s", report)
        except Exception as exc:
            log.error("WAL recover_at_boot failed: %s", exc, exc_info=True)
        # Plug-and-play: keep scanning USB every 10s so any device the operator
        # plugs in appears immediately in the Web UI, even before it's been
        # assigned to a slot in gateway.yaml. Uses DiscoveryService so the
        # snapshot lands in logs/discovered.json (which the WebUI reads).
        try:
            from src.discovery.service import DiscoveryService
            _disc = DiscoveryService()
            async def _discovery_loop() -> None:
                while not self._stopping:
                    try:
                        await _disc.scan_once()
                    except asyncio.CancelledError:
                        break
                    except Exception as exc:
                        log.debug("Discovery scan failed: %s", exc)
                    # sleep in short steps so shutdown is prompt
                    for _ in range(20):
                        if self._stopping:
                            break
                        await asyncio.sleep(0.5)
            self._discovery_task = asyncio.create_task(_discovery_loop(), name="usb-discovery")
            log.info("USB auto-discovery: background scanner started (every 10s).")
        except Exception as exc:
            log.warning("USB auto-discovery could not start: %s", exc)
        await self._open_all_readers()
        # Optional: bidirectional order receiver (LIS -> gateway -> analyzer)
        self._order_recv = None
        if getattr(self._config, "order_receiver_enabled", False):
            from src.adapters.order_receiver import OrderReceiver, get_store
            self._order_recv = OrderReceiver(
                self._config.order_receiver_host,
                self._config.order_receiver_port,
                get_store(),
            )
            await self._order_recv.start()
        self._running    = True
        self._start_time = time.time()
        # Proof of life right away: the Web UI shows "on" without waiting
        # for the first 5-minute health check.
        self._write_status(force=True)
        active = [r.__class__.__name__ for r in self._readers]
        log.info("Gateway started. Active readers: %s", active)
        # DEMO_MODE: push a fake result every 30s so the UI has data
        from src.common.sandbox import start_demo_loop
        start_demo_loop(self._queue)

    async def run_forever(self) -> None:
        tasks = []
        for reader in self._readers:
            tasks.append(asyncio.create_task(reader.run(), name=reader.__class__.__name__))
        tasks.append(asyncio.create_task(self._worker(), name="worker"))
        tasks.append(asyncio.create_task(self._health_check(), name="health"))
        self._run_tasks = tasks
        # Watcher: returns as soon as a stop is requested, so we don't wait for
        # a reader task to raise. Without it, a stop left run_forever blocked
        # (health task sleeps in long chunks) → systemd SIGKILL on timeout.
        async def _stop_watcher() -> None:
            # Attesa attiva voluta: `_stopping` viene alzato anche da un
            # gestore di segnale sincrono, che non puo' toccare un
            # asyncio.Event. 250 ms e' irrilevante accanto a un arresto.
            while not self._stopping:  # noqa: ASYNC110
                await asyncio.sleep(0.25)
        watcher = asyncio.create_task(_stop_watcher(), name="stop-watcher")
        done, pending = await asyncio.wait(
            tasks + [watcher], return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if not t.cancelled() and t.exception():
                log.critical("Task %s raised: %s", t.get_name(), t.exception(), exc_info=True)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    def request_stop(self) -> None:
        """Signal-handler-safe: ask the gateway to wind down. Non-blocking.
        Sets the stop flag and cancels the background loops so run_forever()
        returns promptly; the real cleanup happens in stop()."""
        self._stopping = True
        self._running = False
        if self._discovery_task and not self._discovery_task.done():
            self._discovery_task.cancel()
        for t in self._run_tasks:
            if not t.done():
                t.cancel()

    async def stop(self) -> None:
        if self._stopped:
            return          # cleanup runs exactly once
        self._stopped  = True
        self._stopping = True
        self._running  = False
        if self._discovery_task and not self._discovery_task.done():
            self._discovery_task.cancel()
        log.info("Shutting down ...")
        # Close readers first so no new frames arrive
        await self._registry.close_all()
        # Drain the queue (best-effort; do not exceed drain_timeout)
        drain_deadline = time.time() + 15.0
        drained = 0
        while not self._queue.empty() and time.time() < drain_deadline:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                await asyncio.wait_for(self._process(item), timeout=5.0)
                drained += 1
            except Exception as exc:
                log.warning("Drain: processing failed for one item: %s", exc)
            finally:
                self._queue.task_done()
        remaining = self._queue.qsize()
        if remaining:
            log.warning("Drain: %d item(s) still in queue at shutdown -- writing to DLQ.",
                        remaining)
            while not self._queue.empty():
                try:
                    item = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                write_dead_letter(
                    hl7_body="",
                    control_id="",
                    sample_id=item.get("sample_id",""),
                    device=item.get("device",""),
                    reason="undrained at shutdown",
                    errors={"reason": "gateway shutdown before dispatch"},
                )
                self._queue.task_done()
        log.info("Drain complete: %d dispatched, %d to DLQ.", drained, remaining)
        try:
            _save_seen(_prune_seen(self._seen))
        except Exception as exc:
            log.warning("Final save_seen failed: %s", exc)
        # Last status write with running=False, so the Web UI shows "off"
        # right away instead of trusting a still-fresh status.json.
        self._write_status(force=True)
        log.info(perf.summary())
        log.info("Gateway stopped cleanly.")

    async def reload_config(self) -> None:
        """
        SIGHUP handler: reload gateway.yaml.

        Only hot-reloadable fields are applied (targets, retry, breaker,
        alerting). Structural changes (queue size, log_file, device list) still
        require a full restart -- we log a WARNING when they differ.
        """
        from config.settings import load_config
        cfg_path = Path("config/gateway.yaml")
        # Un solo stat su disco locale, a ricarica richiesta: non vale il
        # costo di un executor.
        if not cfg_path.exists():  # noqa: ASYNC240
            log.warning("reload_config: %s missing", cfg_path)
            return
        try:
            new_cfg = load_config(cfg_path)
        except Exception as exc:
            log.error("reload_config: parse failed: %s -- keeping old config", exc)
            return

        # Warn on structural changes that need a restart
        for attr in ("queue_maxsize", "log_file", "log_level"):
            if getattr(self._config, attr, None) != getattr(new_cfg, attr, None):
                log.warning("reload_config: '%s' changed but requires a restart to apply.", attr)

        self._dispatcher.reload_from(new_cfg)
        # Re-init outbound alerting so webhook/SMTP changes take effect.
        _alerts.configure_from(new_cfg)
        # Update the retained config for /api/status readers.
        self._config = new_cfg
        log.info("reload_config: applied (dispatcher + alerting).")

    async def _open_all_readers(self) -> None:
        self._readers = await self._registry.open_all()
        # Il silenzio di un apparecchio che non ha mai parlato si misura
        # dall'avvio. La chiave e' la stessa che i lettori mettono in
        # result["device"], cioe' il nome della definizione.
        self._mai_sentiti = {d.name for d in self._registry.definitions}
        self._mai_sentiti.add("LOC-200")

    async def _worker(self) -> None:
        log.debug("Worker task started.")
        while self._running:
            try:
                result: Dict[str, Any] = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # ── Filtro duplicati (persistente su disco) ───────────────────────
            # La chiave include un hash dei VALORI: due frame con lo stesso
            # sample_id ma valori diversi (repeat legittimo del medico) NON
            # vengono più scartati. Solo i veri duplicati tecnici (retry del
            # device con payload identico) sono droppati.
            device = result.get("device", result.get("disc_name", "?"))
            sample = result.get("sample_id", "")
            obs_sig_src = "|".join(
                f"{o.get('analyte', '')}={o.get('value', '')}"
                for o in (result.get("observations") or [])
            )
            obs_sig = hashlib.sha256(obs_sig_src.encode("utf-8")).hexdigest()[:16]
            key = f"{device}:{sample}:{obs_sig}"
            now = datetime.now()

            last_str = self._seen.get(key)
            if last_str:
                try:
                    last_dt = datetime.fromisoformat(last_str)
                    if (now - last_dt).total_seconds() < 86400:
                        log.warning(
                            "Duplicato tecnico ignorato: device=%s sample=%s "
                            "(payload identico già processato alle %s)",
                            device, sample, last_dt.strftime("%H:%M:%S")
                        )
                        self._queue.task_done()
                        continue
                except Exception:
                    pass

            # Repeat check: same sample_id, different values → allow but note it
            legacy_key = f"{device}:{sample}"
            legacy_seen = self._seen.get(legacy_key)
            if legacy_seen and legacy_key != key:
                log.info(
                    "Repeat sample accepted: device=%s sample=%s "
                    "(valori diversi dal precedente delle %s)",
                    device, sample, legacy_seen[-8:] if len(legacy_seen) >= 8 else legacy_seen
                )
            self._seen[legacy_key] = now.isoformat()   # keep for repeat detection
            self._seen[key] = now.isoformat()
            self._seen_dirty_count += 1

            # AI anomaly monitor: track inter-arrival per device
            try:
                from src.ai.anomaly import record_device_receive
                record_device_receive(device)
            except Exception:
                pass

            # Periodica: pulizia + save (non a ogni messaggio — risparmia SD/flash)
            elapsed = time.time() - self._seen_last_save
            if (self._seen_dirty_count >= _SEEN_SAVE_EVERY_N
                    or elapsed >= _SEEN_SAVE_INTERVAL):
                try:
                    self._seen = _prune_seen(self._seen)
                    _save_seen(self._seen)
                except Exception as exc:
                    log.warning("Persistenza seen fallita: %s", exc)
                self._seen_dirty_count = 0
                self._seen_last_save = time.time()
            # ─────────────────────────────────────────────────────────────────

            await self._process(result)
            self._queue.task_done()

    async def _process(self, result: Dict[str, Any]) -> None:
        log_parse_result(result)
        try:
            msg = self._builder.build_oru_r01(result)
        except Exception as exc:
            log.error("HL7 build failed sample=%s device=%s: %s",
                      result.get("sample_id","?"), result.get("device","?"), exc, exc_info=True)
            self._stats["errors_today"] += 1
            self._write_status()
            return

        log_hl7(msg.to_string(), direction="-> PIS")
        device = result.get("device", result.get("disc_name","?"))
        log.info("Processing device=%s sample=%s patient=%s analytes=%d queue=%d",
                 device, result.get("sample_id","?"), result.get("patient_id","?"),
                 len(result.get("observations",[])), self._queue.qsize())

        now = datetime.now()
        self._last_seen[device] = now.strftime("%Y-%m-%dT%H:%M:%S")
        self._mai_sentiti.discard(device)

        try:
            summary = await self._dispatcher.dispatch(msg, result)
        except Exception as exc:
            log.error("Dispatch failed sample=%s: %s",
                      result.get("sample_id","?"), exc, exc_info=True)
            self._stats["errors_today"] += 1
            write_dead_letter(
                hl7_body=msg.to_string(),
                control_id=msg.control_id,
                sample_id=result.get("sample_id",""),
                device=device,
                targets=[],
                errors={"__dispatch__": str(exc)},
                reason="dispatch raised",
            )
            self._history.append({
                "date":       now.strftime("%d.%m.%Y"),
                "time":       now.strftime("%H:%M:%S"),
                "device":     device,
                "patient_id": result.get("patient_id", "?"),
                "analytes":   len(result.get("observations", [])),
                "status":     "ERRORE",
                # Istante confrontabile: date e time sono stringhe, e la pagina
                # Topologia non poteva distinguere un flusso di adesso da uno
                # di ore fa -- li mostrava tutti come in transito.
                "ts":         now.timestamp(),
            })
            summary = None

        if summary is not None:
            if summary.succeeded:
                self._stats["results_today"] += 1
                self._stats["results_total"] += 1
                self._stats["last_result"]    = now.strftime("%d.%m.%Y %H:%M:%S")
            if summary.failed:
                self._stats["errors_today"] += 1
            if summary.all_failed and summary.total > 0:
                # Every target failed -- persist to DLQ for manual replay.
                write_dead_letter(
                    hl7_body=msg.to_string(),
                    control_id=msg.control_id,
                    sample_id=result.get("sample_id",""),
                    device=device,
                    targets=summary.failed,
                    errors=summary.errors,
                    reason="all targets failed",
                )
                _alerts.send(
                    level="critical",
                    title=f"Message dropped to DLQ (sample={result.get('sample_id','?')})",
                    message=("All configured PIS targets rejected the message. "
                             "The HL7 is in logs/dead_letter/ for manual replay."),
                    dedup_key=f"dlq:{device}",
                    details={"device": device, "targets": summary.failed,
                             "errors": summary.errors, "sample_id": result.get("sample_id","")},
                )
            status_label = ("OK" if summary.succeeded and not summary.failed
                            else ("PARZIALE" if summary.succeeded else "ERRORE"))
            self._history.append({
                "date":       now.strftime("%d.%m.%Y"),
                "time":       now.strftime("%H:%M:%S"),
                "device":     device,
                "patient_id": result.get("patient_id", "?"),
                "analytes":   len(result.get("observations", [])),
                "status":     status_label,
                "ts":         now.timestamp(),
                "succeeded":  list(summary.succeeded),
                "failed":     list(summary.failed),
            })
            # Persist to SQLite for cross-time search from the UI
            _history_db.record({
                "ts":         now.isoformat(),
                "device":     device,
                "sample_id":  result.get("sample_id", ""),
                "patient_id": result.get("patient_id", ""),
                "control_id": msg.control_id,
                "analytes":   len(result.get("observations", [])),
                "status":     status_label,
                "succeeded":  list(summary.succeeded),
                "failed":     list(summary.failed),
                "errors":     dict(summary.errors),
                "conversion_audit": result.get("conversion_audit") or None,
                # Kept so the Frame Inspector can re-dispatch this sample:
                # `result` lets the message be rebuilt with the current
                # config, `hl7` is the exact payload that went out.
                "hl7":        msg.to_string(),
                "result":     result,
            })

        if len(self._history) > 500:
            self._history = self._history[-500:]

        self._write_status()

    async def _health_check(self) -> None:
        """Every 5 minutes: write logs/health.json and check reader silence."""
        health_path = Path("logs/health.json")
        check_interval = 300  # 5 minuti
        warn_after = getattr(self._config, "reader_silence_warning_seconds", 900)
        alert_after = getattr(self._config, "reader_silence_alert_seconds", 3600)

        while self._running:
            await asyncio.sleep(check_interval)
            try:
                now = datetime.now()
                uptime = int(time.time() - self._start_time)
                healthy = self._running and uptime > 0

                # Watchdog: warn/alert if a reader has been silent too long
                # Gli apparecchi che non hanno mai parlato si contano
                # dall'avvio: altrimenti un analizzatore configurato male resta
                # invisibile per sempre, che e' come si e' perso il Sysmex.
                silent: list[dict] = []
                da_controllare = dict(self._last_seen or {})
                avvio = datetime.fromtimestamp(self._start_time)
                for mai in self._mai_sentiti:
                    da_controllare.setdefault(
                        mai, avvio.strftime("%Y-%m-%dT%H:%M:%S"))
                for name, ts_str in da_controllare.items():
                    try:
                        dt = datetime.fromisoformat(ts_str)
                        silence = int((now - dt).total_seconds())
                    except (ValueError, TypeError):
                        continue
                    mai_sentito = name in self._mai_sentiti
                    if silence >= alert_after:
                        silent.append({"device": name, "silence_sec": silence,
                                       "level": "alert",
                                       "mai_sentito": mai_sentito})
                        log.error("WATCHDOG: reader %s silent for %ds (>= %ds alert).",
                                  name, silence, alert_after)
                        if mai_sentito:
                            titolo = f"{name}: nessun dato dall'avvio del gateway"
                            messaggio = (
                                "L'analizzatore e' configurato ma non ha mai "
                                "inviato niente da quando il gateway e' partito. "
                                "Di solito e' la porta chiusa nel firewall, un "
                                "cavo staccato, o l'apparecchio che punta a un "
                                "indirizzo sbagliato. Apri Verifica impianto "
                                "nella WebUI per il dettaglio."
                            )
                        else:
                            titolo = f"{name}: silenzioso da oltre {alert_after}s"
                            messaggio = (
                                "Nessun referto ricevuto. Controlla collegamento, "
                                "cavo, percorso di rete o alimentazione."
                            )
                        _alerts.send(
                            level="critical",
                            title=titolo,
                            message=messaggio,
                            dedup_key=f"watchdog:{name}",
                            details={"device": name, "silence_sec": silence,
                                     "mai_sentito": mai_sentito},
                        )
                        await self._try_restart_reader(name)
                    elif silence >= warn_after:
                        silent.append({"device": name, "silence_sec": silence,
                                       "level": "warning",
                                       "mai_sentito": mai_sentito})
                        log.warning("WATCHDOG: reader %s silent for %ds.",
                                    name, silence)

                payload = {
                    "healthy":        healthy,
                    "uptime_seconds": uptime,
                    "results_total":  self._stats["results_total"],
                    "errors_today":   self._stats["errors_today"],
                    "last_result":    self._stats["last_result"],
                    "queue_size":     self._queue.qsize(),
                    "queue_full_events": _bp.queue_full_events,
                    "silent_readers": silent,
                    "checked_at":     now.isoformat(),
                }
                health_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = health_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(payload, indent=2))
                import os as _os
                _os.replace(tmp, health_path)

                # status.json veniva scritto SOLO all'arrivo di un referto o
                # alla connessione di un apparecchio, mai a intervalli
                # regolari. In uno studio senza esami invecchiava
                # all'infinito, e chi guardava la sua eta' per capire se il
                # gateway fosse vivo concludeva che si fosse bloccato.
                # Riscriverlo qui lo rende un vero segno di vita.
                self._write_status()

                if healthy:
                    log.debug("Health OK -- uptime=%ds results=%d queue=%d silent=%d",
                              uptime, self._stats["results_total"],
                              self._queue.qsize(), len(silent))
                else:
                    log.warning("Health FAILED -- gateway non attivo!")
            except Exception as exc:
                log.debug("Health check error: %s", exc)

    async def _try_restart_reader(self, name: str) -> None:
        """
        Best-effort reopen of a reader that has been silent past alert_after.
        Exponential backoff (60s, 120s, 240s, ..., capped at 30 min) to avoid
        thrashing when a device is genuinely offline.
        """
        now = time.time()
        backoff = self._reader_restart_backoff.get(name, 60.0)
        last = self._reader_restart_last.get(name, 0.0)
        if now - last < backoff:
            return
        self._reader_restart_last[name] = now
        self._reader_restart_backoff[name] = min(backoff * 2, 1800.0)

        # Match the reader by class name (Sysmex uses device_name; others just class)
        target_reader = None
        for r in self._readers:
            r_name = getattr(r, "_device_name", r.__class__.__name__)
            if r_name == name or r.__class__.__name__ == name:
                target_reader = r
                break
        if not target_reader:
            log.warning("WATCHDOG: no reader instance matches %r -- cannot restart", name)
            return

        log.warning("WATCHDOG: attempting reader %s restart (next attempt in %.0fs)",
                    name, self._reader_restart_backoff[name])
        try:
            await target_reader.close()
        except Exception as exc:
            log.warning("WATCHDOG: close() raised: %s", exc)
        try:
            await target_reader.open()
            # Reset backoff on successful reopen
            self._reader_restart_backoff[name] = 60.0
            log.info("WATCHDOG: reader %s reopened successfully", name)
        except Exception as exc:
            log.error("WATCHDOG: reopen failed for %s: %s (will retry with backoff)",
                      name, exc)

    def _write_status(self, force: bool = False) -> None:
        # Throttle: at most once every `_status_min_interval` seconds unless forced.
        now_mono = time.time()
        if not force and (now_mono - self._status_last_write) < self._status_min_interval:
            return
        self._status_last_write = now_mono
        try:
            status_path = Path("logs/status.json")
            status_path.parent.mkdir(parents=True, exist_ok=True)
            cfg = self._config
            readers = self._registry.reader_status()
            payload = {
                **self._stats,
                "running": self._running,
                "connection_status": cfg.loc200.connection_type,
                "uptime_seconds": int(time.time() - self._start_time),
                "latency_p95_ms": perf.p95_ms(),
                "queue_size": self._queue.qsize(),
                "queue_maxsize": self._queue.maxsize,
                "queue_full_events": _bp.queue_full_events,
                "active_readers": readers,
                "targets": [{"name": t.name, "type": t.type, "enabled": t.enabled}
                            for t in cfg.targets if t.enabled],
                "breakers": self._dispatcher.targets_snapshot(),
                "history":   list(reversed(self._history)),
                "last_seen": self._last_seen,
                "connected": self._connected,
                "updated_at": datetime.now().isoformat(),
            }
            status_path.write_text(json.dumps(payload, indent=2))
        except Exception as exc:
            log.debug("Could not write status.json: %s", exc)

    def _setup_file_logging(self) -> None:
        # 1) JSON stdout logging via src.common.structured_log (Loki/ELK-ready).
        #    Turn on with LOG_FORMAT=json in the environment.
        try:
            from src.common.structured_log import configure_root
            configure_root(level=self._config.log_level.upper())
        except Exception as exc:
            log.debug("structured_log configure_root failed: %s", exc)

        # 2) Rotating file logging (legacy, always human text).
        if not self._config.log_file:
            return
        import logging.handlers
        log_path = Path(self._config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S"
        ))
        root = logging.getLogger()
        root.addHandler(fh)
        root.setLevel(getattr(logging, self._config.log_level.upper(), logging.INFO))
        log.info("File logging -> %s  (level=%s)", log_path, self._config.log_level)

        # 3) Apply forward-only DB migrations before any component queries the DB.
        try:
            from src.common.migrations import apply as _apply_migrations
            from pathlib import Path as _P
            v = _apply_migrations(_P("logs/history.db"))
            log.info("Schema migrations applied: version=%d", v)
        except Exception as exc:
            log.warning("Schema migrations skipped: %s", exc)
