"""Generate a chaos post-mortem from gateway state after chaos-weekly."""
import subprocess
from datetime import datetime
from pathlib import Path


def _read(p, default=""):
    try:
        return Path(p).read_text(encoding="utf-8")[:2000]
    except Exception:
        return default


def main() -> None:
    print(f"# Chaos-weekly report — {datetime.utcnow().isoformat()}Z\n")
    print("## Recovery")
    for f in ("logs/health.json", "logs/breakers.json", "logs/status.json"):
        print(f"\n### `{f}`\n```json\n{_read(f)}\n```")
    print("\n## Last 40 log lines")
    print("```\n" + _read("logs/gateway.log") + "\n```")
    try:
        journal = subprocess.check_output(
            ["journalctl", "-u", "jerumednexus-gateway", "-n", "40"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
        print("\n## journalctl\n```\n" + journal + "\n```")
    except Exception:
        pass


if __name__ == "__main__":
    main()
