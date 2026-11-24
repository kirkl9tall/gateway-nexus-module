"""Simulated practice software (stands in for Tomedo): accepts HL7 over MLLP
on 127.0.0.1:12575 and answers AA. Run: python demo/mock_tomedo.py"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.mock_lis import MockLIS


async def main():
    lis = MockLIS(port=12575)
    await lis.start()
    print("Simulated Tomedo listening on 127.0.0.1:12575", flush=True)
    seen = 0
    while True:
        await asyncio.sleep(1)
        while seen < len(lis.received):
            msg = lis.received[seen]; seen += 1
            pid = next((l.split("|")[3] for l in msg.split("\r") if l.startswith("PID")), "?")
            print(f"Tomedo received result #{seen} (patient {pid})", flush=True)

asyncio.run(main())
