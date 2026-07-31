"""Small, dependency-free production security alert helpers."""
from datetime import datetime, timezone
import json
import logging
import os
from urllib.request import Request, urlopen


LOGGER = logging.getLogger("brokerbeacon.security")


def emit_security_alert(event, severity="warning", detail=None):
    """Log a structured event and optionally deliver it to an operator webhook."""
    payload = {
        "service": "BrokerBeacon",
        "event": event,
        "severity": severity,
        "detail": detail or {},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    LOGGER.warning("security_event %s", json.dumps(payload, sort_keys=True))
    webhook = os.getenv("SECURITY_ALERT_WEBHOOK_URL", "").strip()
    if webhook:
        request = Request(
            webhook,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "BrokerBeacon-Security/1.0"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                response.read(1)
        except Exception:
            LOGGER.exception("Unable to deliver BrokerBeacon security alert")
    return payload
