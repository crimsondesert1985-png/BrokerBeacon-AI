"""Trigger one secure Ember cycle against the live BrokerBeacon service."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

url = os.getenv("BROKERBEACON_URL", "https://brokerbeacon-ai.onrender.com").rstrip("/") + "/api/internal/ember-cycle"
token = os.getenv("EMBER_AUTOMATION_TOKEN", "").strip()
if not token:
    raise SystemExit("EMBER_AUTOMATION_TOKEN is required")

request = urllib.request.Request(
    url,
    data=b"{}",
    method="POST",
    headers={
        "Content-Type": "application/json",
        "X-Ember-Token": token,
        "User-Agent": "BrokerBeacon-Ember-Scheduler/1.0",
    },
)
try:
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
        print(json.dumps(payload, indent=2, sort_keys=True))
except Exception as exc:
    print(f"Scheduled Ember cycle failed: {exc}", file=sys.stderr)
    raise
