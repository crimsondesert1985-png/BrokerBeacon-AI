"""Production entry point for BrokerBeacon and optional sprint modules."""
import sqlite3

from app import DB, app
from sprint36_discovery import install as install_sprint36_discovery


def brokerbeacon_db_connector():
    """Return a connection matching BrokerBeacon's normal SQLite behavior."""
    connection = sqlite3.connect(DB, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys=on")
    connection.execute("pragma busy_timeout=30000")
    return connection


install_sprint36_discovery(app, brokerbeacon_db_connector)

__all__ = ["app"]
