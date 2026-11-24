"""
SFTP dispatcher for Tomedo (or any host that ingests .hl7 via SFTP).

Security:
  * Host key verification is enabled by default -- known_hosts loaded from
    config/known_hosts or ~/.ssh/known_hosts. Set SFTP_INSECURE_HOSTKEY=1
    in secrets.env only when explicitly authorised by the operator
    (e.g. lab environment, first-time provisioning).
  * Password lives on the object only for the duration of dispatch; consider
    key-based auth for production (client_keys parameter).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("loc200.sftp")

_KNOWN_HOSTS_CANDIDATES = [
    Path("config/known_hosts"),
    Path.home() / ".ssh" / "known_hosts",
]


def _resolve_known_hosts() -> Optional[str]:
    """Return the first existing known_hosts path, or None to fall back."""
    for p in _KNOWN_HOSTS_CANDIDATES:
        if p.exists():
            return str(p)
    return None


class SFTPDispatcher:
    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        password: str = "",
        remote_path: str = "/import",
        file_encoding: str = "utf-8",
        file_extension: str = ".hl7",
        retry_max: int = 3,
        retry_delay: float = 5.0,
        connect_timeout: float = 15.0,
        client_key_path: Optional[str] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._remote_path = remote_path
        self._encoding = file_encoding
        # L'estensione era fissata a .hl7 e ignorava quella configurata sul
        # target: un gestionale che importa solo *.ldt non vedeva mai i file.
        self._extension = file_extension or ".hl7"
        self._retry_max = retry_max
        self._retry_delay = retry_delay
        self._connect_timeout = connect_timeout
        self._client_key_path = client_key_path
        log.info("SFTP dispatcher -> %s@%s:%d%s", username, host, port, remote_path)

    async def dispatch(self, msg, result: Dict[str, Any],
                       testo_verificato: Optional[str] = None) -> None:
        """
        `testo_verificato` e' il messaggio gia' passato per le riscritture del
        target e per il validatore. Quando manca -- chiamate diverse da quella
        del dispatcher -- si usa il messaggio grezzo, che e' il comportamento
        di prima.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        patient_id = str(result.get("patient_id", "") or "")
        if not patient_id or patient_id == "0":
            try:
                hl7_text = msg.to_string()
                for line in hl7_text.split("\r"):
                    if line.startswith("PID"):
                        fields = line.split("|")
                        if len(fields) > 3 and fields[3]:
                            patient_id = fields[3].split("^")[0].strip()
                            break
            except Exception:
                pass
        if not patient_id or patient_id == "0":
            patient_id = "UNKNOWN"
        # Sanitise patient_id (no path traversal)
        patient_id = "".join(c for c in patient_id if c.isalnum() or c in "-_")[:64] or "UNKNOWN"
        filename = f"{patient_id}_LOC200_{ts}{self._extension}"
        # Encode the file to match the charset declared in MSH-18 (e.g. 8859/1 →
        # iso-8859-1). A fixed file_encoding (utf-8) while MSH said 8859/1 made
        # mojibake for µ/umlauts and Tomedo rejected the file.
        if testo_verificato is None:
            content = msg.to_file()
        else:
            # Stessa codifica e stessi fine-riga di msg.to_file(), ma sul testo
            # riscritto e validato.
            content = testo_verificato.replace(chr(13) + chr(10), chr(13))                                       .replace(chr(13), chr(13) + chr(10))                                       .encode(msg._codec, errors="replace")

        last_exc: Optional[Exception] = None
        for attempt in range(1, self._retry_max + 1):
            try:
                await asyncio.wait_for(
                    self._upload(filename, content),
                    timeout=self._connect_timeout + 10,
                )
                log.info("SFTP OK -> %s/%s (%d bytes)",
                         self._remote_path, filename, len(content))
                return
            except Exception as exc:
                last_exc = exc
                log.warning("SFTP tentativo %d/%d fallito: %s",
                            attempt, self._retry_max, exc)
                if attempt < self._retry_max:
                    await asyncio.sleep(self._retry_delay)
        raise RuntimeError(
            f"SFTP fallito dopo {self._retry_max} tentativi: {last_exc}"
        )

    async def _upload(self, filename: str, content: bytes) -> None:
        import asyncssh

        # Host key verification: known_hosts unless explicitly opted out
        insecure = os.environ.get("SFTP_INSECURE_HOSTKEY", "").lower() in ("1", "true", "yes")
        if insecure:
            log.warning(
                "SFTP_INSECURE_HOSTKEY=1 -- skipping host key verification for %s. "
                "Do NOT use in production.", self._host,
            )
            known_hosts_arg: Any = None
        else:
            path = _resolve_known_hosts()
            if path is None:
                raise RuntimeError(
                    f"SFTP host key verification requested but no known_hosts file "
                    f"found (tried {[str(p) for p in _KNOWN_HOSTS_CANDIDATES]}). "
                    f"Populate one, or set SFTP_INSECURE_HOSTKEY=1 in secrets.env."
                )
            known_hosts_arg = path

        conn_kwargs: Dict[str, Any] = {
            "host":         self._host,
            "port":         self._port,
            "username":     self._username,
            "known_hosts":  known_hosts_arg,
            "connect_timeout": self._connect_timeout,
        }
        if self._client_key_path:
            conn_kwargs["client_keys"] = [self._client_key_path]
        elif self._password:
            conn_kwargs["password"] = self._password
        else:
            raise RuntimeError("SFTP: neither password nor client_key_path configured")

        async with asyncssh.connect(**conn_kwargs) as conn:
            async with conn.start_sftp_client() as sftp:
                try:
                    await sftp.mkdir(self._remote_path)
                except Exception:
                    pass
                remote_file = f"{self._remote_path}/{filename}"
                tmp_file = f"{self._remote_path}/.{filename}.tmp"
                async with sftp.open(tmp_file, "wb") as f:
                    await f.write(content)
                await sftp.rename(tmp_file, remote_file)
