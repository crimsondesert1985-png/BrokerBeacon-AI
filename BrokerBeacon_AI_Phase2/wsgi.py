"""Production WSGI entrypoint for BrokerBeacon.

Keeps app.py stable while registering Sprint 37 platform-owner extensions.
"""
from app import app, DB
from national_data_center import install_national_data_center
from national_warehouse_api import install_national_warehouse

install_national_warehouse(app, DB)
install_national_data_center(app)

__all__ = ["app"]
