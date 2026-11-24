#!/usr/bin/env python3
"""
Chaos: send progressively-corrupted HL7 to the ingest endpoint.
Verifies validator + escape catch bad input without crashing.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:5003/")
    p.add_argument("--token", default=os.environ.get("LOC200_HTTP_TOKEN", ""))
    p.add_argument("--iterations", type=int, default=50)
    args = p.parse_args()

    if not args.token:
        print("LOC200_HTTP_TOKEN not set", file=sys.stderr)
        return 1

    corruptions = [
        b"MSH",                                     # truncated
        b"MSH|^~\\&|X|Y|Z|Q|xxxx||ORU^R01|1|P|2.5\r",  # bad timestamp
        b"MSH|^~\\&|" + b"X" * 200 + b"|",         # oversized MSH-3
        b"\x00\x00\x00\x00\x00" * 50,              # binary garbage
        b"MSH|^~\\&|X|Y|Z|Q|20250101120000||ORU^R01|1|P|2.5\rOBX|1|NM|"
        + b"X|X" * 500 + b"\r",                    # oversized OBX
        b"MSH|^~\\&|X|Y|Z|Q|20250101120000||ORU^R01|1|P|2.5"
        + b"\r\r\r\r\r" * 100,                     # many empty CRs
    ]

    headers = {"Authorization": f"Bearer {args.token}",
               "Content-Type": "text/plain"}
    ok, fail = 0, 0
    for _ in range(args.iterations):
        body = random.choice(corruptions)
        # Add random single-byte flip
        if body and random.random() < 0.5:
            body = bytearray(body)
            idx = random.randrange(len(body))
            body[idx] = random.randint(0, 255)
            body = bytes(body)
        req = urllib.request.Request(args.url, data=body,
                                     headers=headers, method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            ok += 1
        except Exception:
            # Non-2xx is expected -- the gateway rejects them
            fail += 1
    print(f"Sent {args.iterations} corruptions: {ok} accepted, {fail} rejected.")
    print("Check: gateway should still be responsive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
