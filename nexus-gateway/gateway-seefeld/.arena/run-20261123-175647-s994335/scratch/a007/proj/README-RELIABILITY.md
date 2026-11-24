# Reliability & Raspberry Pi Optimization Plan

Core review of the gateway (`src/`), done on 2026-11-23.
Goal: **no lab result is ever lost without someone knowing**, and the gateway runs light on a Raspberry Pi with an SD card.

---

## 1. Current status

| Check | Result |
|---|---|
| Web UI starts | OK: `.venv/bin/python -m flask --app webui.app run --host=127.0.0.1 --port=8088 --debug` |
| Test suite | 342 passed, 12 failed. All 12 failures come from the environment, not the code (see §5) |
| Core data path | **9 reliability bugs found**. 5 of them can lose a result without any error |

### How data flows today

```
Analyzer ──frame──▶ Reader ──ACK "AA"──▶ Analyzer        (analyzer now forgets the result)
                      │
                      └─ safe_put_sync ─▶ asyncio.Queue (RAM only, 500 slots)
                                              │
                                              ▼
                                   Worker (1 message at a time)
                                   dedup ▶ build HL7 ▶ dispatch to all targets
                                              │
                                   DLQ only if *every* target failed
```

The weak point: the analyzer receives the ACK **before** the result is stored anywhere durable.
From then on the result exists only in RAM.

---

## 2. Problems found

Severity: 🔴 data can be lost without any error · 🟠 wrong behaviour / degraded delivery · 🟡 performance / SD wear

### 🔴 P1: the analyzer gets an ACK before the result is safely stored

- **Where:** [src/adapters/mllp_reader.py:220-226](src/adapters/mllp_reader.py#L220-L226)
- **What happens:**
  - The reader parses the frame and calls `safe_put_sync()`. That call **drops the item** if the queue is full ([src/common/backpressure.py:59-79](src/common/backpressure.py#L59-L79)).
  - Then it sends `MSA|AA` no matter what happened, even when parsing returned `None`.
- **Same drop-on-full call in:** `loc200_reader.py:373`, `sysmex_reader.py:393/676`, `cobas_reader.py:401`, `uc1000_reader.py:126`, `reflotron_reader.py:238`, `devices/registry.py:255`.
- **Impact:** a full queue, a parse failure, a crash or a **power cut on the Pi** loses every result still in RAM. The analyzer thinks they were delivered and never resends them.

### 🔴 P2: the WAL (write-ahead log) is never written

- **Where:** [src/common/wal.py](src/common/wal.py)
- **What happens:** `wal.enter()` and `wal.ack()` have no callers anywhere in `src/`. Only `recover_at_boot()` runs, so it always finds nothing to recover.
- **Impact:** the "exactly-once / crash-safe" promise is not implemented.

### 🔴 P3: a missing or partial ACK from the PIS counts as success

- **Where:** [src/transport/dispatcher.py:366-395](src/transport/dispatcher.py#L366-L395)
- **What happens:**
  - The sender does a single `reader.read(4096)`.
  - If the reply has no `MSA`, it logs "assuming accepted" and returns.
  - That covers an **empty reply** (the PIS closed the connection) and an ACK **split across two network packets**.
- **Impact:** the message is marked delivered when the PIS may never have stored it.

### 🔴 P4: with several targets, a failure for one target is lost

- **Where:** [src/gateway.py:485](src/gateway.py#L485)
- **What happens:**
  - A message goes to the DLQ only when `summary.all_failed` is true.
  - If target A succeeds and target B fails, or B is skipped because its circuit breaker is open, nothing is stored for B.
- **Impact:** that PIS silently never gets the result.

### 🔴 P5: results still queued at shutdown go to the DLQ without their content

- **Where:** [src/gateway.py:289-302](src/gateway.py#L289-L302)
- **What happens:** items left in the queue at shutdown are written with `hl7_body=""`. The parsed result is not saved.
- **Impact:** the DLQ shows an entry, but there is nothing in it to resend.

### 🟠 P6: one unreachable target blocks every analyzer

- **Where:** [src/gateway.py:352-426](src/gateway.py#L352-L426) and [src/transport/dispatcher.py:206-251](src/transport/dispatcher.py#L206-L251)
- **What happens:**
  - One worker handles one message at a time, and retries happen inside it.
  - Each message can take 5 attempts with backoff 5+10+20+40 s plus a 15 s timeout per attempt, so about **2.5 min**.
  - The breaker opens only after 5 failed *messages*, so about **12 min** of blocking before it does.
- **Impact:** the queue fills up and P1 starts dropping new results.

### 🟠 P7: validation errors are retried and count against the target

- **Where:** [src/transport/dispatcher.py:321-323](src/transport/dispatcher.py#L321-L323)
- **What happens:**
  - A message that fails `validate_hl7_message` raises `ValueError`.
  - The retry loop tries it 5 times, and each failure counts toward that target's circuit breaker.
- **Impact:** one malformed message can open the breaker and block valid messages to that target.

### 🟠 P8: after a delivery failure, the analyzer's resend is dropped for 24 h

- **Where:** [src/gateway.py:401-402](src/gateway.py#L401-L402)
- **What happens:** the sample is marked "seen" *before* HL7 build and dispatch. If those fail and the analyzer resends, the resend is dropped as a "technical duplicate" for 24 h.
- **Impact:** a manual resend from the analyzer doesn't fix the failure.

### 🟠 P9: false "LOC-200 has sent no data" alarm

- **Where:** [src/gateway.py:350](src/gateway.py#L350)
- **What happens:** `"LOC-200"` is always added to the silence watchdog, even on sites without a LOC-200.
- **Impact:** after 1 h those sites get a critical alert that isn't true.

### 🟡 P10: status.json writes wear the SD card

- **Where:** [src/gateway.py:686-717](src/gateway.py#L686-L717)
- **What happens:**
  - `status.json` is rewritten up to every 2 s with up to 500 history entries (`indent=2`).
  - The write is not atomic, so the Web UI can read a half-written file.
  - There is no trailing write, so the last status change can be skipped by the throttle.

### 🟡 P11: blocking disk writes inside the event loop

- **What happens:** the SQLite `history.record()` (full HL7 + full result JSON on every message), `write_dead_letter()` and `_save_seen()` all run synchronously inside the asyncio loop.
- **Impact:** on a slow SD card these pause **every** reader and sender.

### 🟡 P12: byte-by-byte MLLP parsing

- **Where:** [src/adapters/mllp_reader.py:210-211](src/adapters/mllp_reader.py#L210-L211)
- **What happens:** every byte becomes a new `bytes` object in Python.
- **Fix direction:** `bytearray.find(VT/FS)` is about 10-50× faster, which matters on a Pi 3B+.

### 🟡 P13: no fsync before rename

- **Where:** `_atomic_write` in [dispatcher.py:478](src/transport/dispatcher.py#L478), `_save_seen` in [gateway.py:95](src/gateway.py#L95)
- **What happens:** the file is renamed without an `fsync` first.
- **Impact:** after a power cut, ext4 on an SD card can leave a 0-byte file.

---

## 3. Fix plan

### Phase 1: Never lose a result (P1, P2, P5, P8)

**Principle:** *store durably first, ACK second, delete only after every target confirmed.*

```
Analyzer ─frame─▶ Reader ─parse─▶ INBOX (SQLite, synchronous=FULL) ─▶ ACK "AA"
                                    │  (if the write fails ▶ ACK "AE", analyzer resends)
                                    ▼
                         Worker reads from INBOX, not RAM
                                    ▼
                  OUTBOX: one row per (message, target) ─▶ deleted on confirmed ACK
```

1. Add a durable inbox, by extending `wal.py` or adding `src/common/inbox.py`.
   - Readers call `inbox.put(result)` **before** building the ACK.
   - On failure, MLLP readers answer `AE` and ASTM readers answer `NAK`, so the analyzer retries.
2. Change the asyncio queue to carry only inbox IDs. On boot, unfinished inbox rows are put back in the queue.
   - This replaces "quarantine everything to DLQ at boot".
   - Duplicates are prevented by P8's dedup plus the MSH-10 control ID.
3. Mark "seen" (dedup) only **after** the message is built and handed to the outbox (P8).
4. Shutdown no longer needs to drain anything: every result is already on disk (P5).
5. Remove the drop path from `safe_put_sync` for readers. Backpressure becomes "inbox write failed → NAK".

### Phase 2: Correct delivery semantics (P3, P4, P6, P7)

1. **ACK reading:** read until `\x1c\x0d` (or EOF) with a total timeout. An empty reply or a reply without `MSA` counts as **failure**. Add a per-target option `accept_no_msa: false` (default) for odd PIS that really send no MSA.
2. **One delivery row per target:** each target has its own retry state in the outbox. A partial failure keeps retrying (or goes to the DLQ) for **that target only**.
3. **Retries outside the worker:** one small sender task per target pulls from its own outbox. A dead target no longer blocks the others, and the worker only builds messages.
4. **Errors that can't succeed on retry** (`ValueError` from validation, AR responses) go straight to the DLQ with no retries, and don't count toward the circuit breaker.

### Phase 3: Correctness fixes (P9)

- Add `"LOC-200"` to the watchdog only if `config.loc200` is actually enabled and its reader opened.

### Phase 4: Raspberry Pi / SD card (P10–P13)

| Fix | Effect |
|---|---|
| `status.json`: write at most every 10 s, atomically (tmp + `os.replace`), compact JSON, last 100 history entries; the full history is already in SQLite | ~90% fewer SD writes |
| Move `history.record`, `write_dead_letter` and `_save_seen` to `asyncio.to_thread` (or a single writer thread with a queue) | No event-loop stalls |
| MLLP framing with `bytearray.find` | Lower CPU on Pi 3B+ |
| `fsync(file)` + `fsync(dir)` in `_atomic_write` / `_save_seen` | Files survive a power cut |
| Recommend `logs/` on tmpfs for trace/debug files, and keep `history.db` + inbox on the SD card | Longer SD card life |

### Phase 5: Tests for every fix

Each fix comes with a test that fails before the fix:

| Test | Proves |
|---|---|
| Queue full → reader answers `AE`/`NAK`, result not lost | P1 |
| Kill the process after ACK, restart → result is delivered | P1, P2 |
| PIS closes without replying → counted as failure, retried | P3 |
| PIS sends the ACK in 2 TCP packets → parsed correctly | P3 |
| 2 targets, B down → B gets the message once it recovers, A gets it once | P4, P6 |
| Validation error → DLQ immediately, breaker unchanged | P7 |
| Build fails, analyzer resends → second attempt processed | P8 |
| No LOC-200 configured → no "LOC-200 silent" alarm | P9 |

---

## 4. Order of work

| # | Phase | Risk if not fixed | Effort |
|---|---|---|---|
| 1 | Phase 2.1: ACK reading (P3) | High | Small, isolated in `_send_mllp` / `_check_ack` |
| 2 | Phase 2.4: no retry on validation errors (P7) | Medium | Small |
| 3 | Phase 3: LOC-200 false alarm (P9) | Low | Tiny |
| 4 | Phase 1: durable inbox + ACK after storage (P1, P2, P5, P8) | **Highest** | Large, touches every reader |
| 5 | Phase 2.2–2.3: per-target outbox (P4, P6) | High | Medium |
| 6 | Phase 4: Pi optimizations (P10–P13) | SD wear / latency | Medium |

Items 1-3 are quick and can ship right away. Items 4-5 are the real reliability work and should ship together.

---

## 5. Notes on the 12 failing tests (environment, not code)

| Tests | Cause | Fix |
|---|---|---|
| `test_pacchetto_eseguibile.py` (5) | The folder is not a git repo, so `git ls-files` fails | Run inside the git checkout |
| `test_dlq_rispedisci.py` (2) | No `config/gateway.yaml` in this copy | Copy from `config/gateway.yaml.example` |
| `test_firewall_sync.py` (5) | `firewall-sync.sh` only finds the venv under `/opt/jerumednexus` | Also try `$QUI/../.venv/bin/python` in the script. With the venv on `PATH`, all 10 pass |
