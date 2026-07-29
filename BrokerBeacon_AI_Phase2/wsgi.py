"""Gunicorn entry point for BrokerBeacon.

The existing app remains unchanged; feature modules are registered here before the
server begins accepting requests.
"""
from app import DB, app
from broker_dna import register_broker_dna

register_broker_dna(app, DB)

__all__ = ["app"]
