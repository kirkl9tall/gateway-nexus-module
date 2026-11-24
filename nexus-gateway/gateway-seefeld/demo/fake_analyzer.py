"""A fake lab analyzer: sends an HL7 result over the network (MLLP) to the
gateway every few seconds, like a real Seamaty / Horiba would.

    python demo/fake_analyzer.py --port 6000 --name SMT120 --every 20
"""
import argparse, random, socket, time
from datetime import datetime

TESTS = {
    "SMT120": [("GLU", "Glukose", "mmol/L", 3.9, 6.1), ("CHOL", "Cholesterin", "mmol/L", 3.0, 5.2),
               ("CRE", "Kreatinin", "umol/L", 45, 90), ("ALT", "ALT", "U/L", 7, 40)],
    "HORIBA": [("WBC", "Leukozyten", "10^3/uL", 4.0, 10.0), ("HGB", "Haemoglobin", "g/dL", 12, 16),
               ("PLT", "Thrombozyten", "10^3/uL", 150, 400), ("CRP", "CRP", "mg/L", 0.5, 5.0)],
}


def message(name, n):
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    pid = f"P{random.randint(10000, 99999)}"
    seg = [f"MSH|^~\\&|{name}|LAB|LIS|PRAXIS|{now}||ORU^R01|{name}{n:05d}|P|2.5",
           f"PID||{pid}||{pid}||Test^Patient{n}||||F",
           f"OBR|1||S{n:05d}{random.randint(10, 99)}|panel|||{now}"]
    for i, (code, label, unit, lo, hi) in enumerate(TESTS.get(name, TESTS["SMT120"]), 1):
        v = round(random.uniform(lo * 0.9, hi * 1.1), 1)
        seg.append(f"OBX|{i}|NM|{code}^{label}^L|1|{v}|{unit}|{lo}-{hi}|N|||F")
    return ("\r".join(seg) + "\r").encode(), pid


def send(port, payload):
    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(b"\x0b" + payload + b"\x1c\r")
        ack = s.recv(4096)
    return b"MSA|AA" in ack


ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, required=True)
ap.add_argument("--name", default="SMT120")
ap.add_argument("--every", type=float, default=20)
ap.add_argument("--count", type=int, default=0, help="0 = forever")
a = ap.parse_args()
n = 0
while a.count == 0 or n < a.count:
    n += 1
    payload, pid = message(a.name, n)
    try:
        ok = send(a.port, payload)
        print(f"[{a.name}] result #{n} for patient {pid} -> gateway {'accepted' if ok else 'NOT accepted'}", flush=True)
    except OSError as e:
        print(f"[{a.name}] gateway not reachable on port {a.port}: {e}", flush=True)
    time.sleep(a.every)
