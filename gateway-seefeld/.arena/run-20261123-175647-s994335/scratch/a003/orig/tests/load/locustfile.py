"""
Load test: simulate N analyzers pushing HL7 to the LOC-200 HTTP ingestion.

Run:
    pip install locust
    LOC200_HTTP_TOKEN=xxxxxxxx locust -f tests/load/locustfile.py \
        --host http://127.0.0.1:5003 --users 50 --spawn-rate 5

Then open http://localhost:8089 for the web UI.
"""
from __future__ import annotations

import os
import random
import time

from locust import HttpUser, between, task


TOKEN = os.environ.get("LOC200_HTTP_TOKEN", "test-token")


HL7_TEMPLATE = (
    "MSH|^~\\&|LOC200|SIM|LIS|PRAXIS|{ts}||ORU^R01^ORU_R01|CTL{ctl}|P|2.5\r"
    "PID||PAT{pat}|PAT{pat}||Mueller^Hans||||M\r"
    "OBR|1|||S{sid}^S{sid}^L||{ts}|{ts}|||||||||||||F\r"
    "OBX|1|NM|1920-8^AST^LN|1|{ast}|U/L|15^40|||||F\r"
    "OBX|2|NM|2345-7^GLU^LN|1|{glu}|mmol/L|3.9^6.1|||||F\r"
    "OBX|3|NM|2093-3^CHOL^LN|1|{chol}|mmol/L|0^5.17|||||F\r"
)


def _now_ts() -> str:
    return time.strftime("%Y%m%d%H%M%S")


class AnalyzerUser(HttpUser):
    """Each virtual user simulates one analyzer POSTing results."""

    wait_time = between(1, 4)

    @task(10)
    def push_result(self):
        body = HL7_TEMPLATE.format(
            ts=_now_ts(),
            ctl=random.randint(100000, 999999),
            pat=random.randint(1, 500),
            sid=random.randint(10000, 99999),
            ast=round(random.uniform(10, 60), 1),
            glu=round(random.uniform(3.5, 8.0), 2),
            chol=round(random.uniform(2.5, 8.0), 2),
        )
        self.client.post("/", data=body,
                         headers={"Content-Type": "text/plain",
                                  "Authorization": f"Bearer {TOKEN}"},
                         name="/ HL7 POST")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")
