"""Poll /readyz until it returns 200 within timeout, otherwise fail chaos test."""
import argparse
import sys
import time
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8088/readyz")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    deadline = time.time() + args.timeout
    last_err = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(args.url, timeout=2) as r:
                if r.status == 200:
                    print(f"recovered in {int(args.timeout - (deadline - time.time()))}s")
                    return 0
                last_err = f"HTTP {r.status}"
        except Exception as exc:
            last_err = str(exc)
        time.sleep(1)
    print(f"NOT recovered within {args.timeout}s — last error: {last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
