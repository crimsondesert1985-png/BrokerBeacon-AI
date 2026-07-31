"""Production WSGI entrypoint for BrokerBeacon.

Keeps app.py stable while registering Sprint 37 platform-owner extensions.
"""
from app import app, DB
from ai_ops_api import install_ai_ops
from discovery_ops_api import install_discovery_ops
from national_data_center import install_national_data_center
from national_warehouse_api import install_national_warehouse
from state_connector_api import install_state_connectors

install_national_warehouse(app, DB)
install_state_connectors(app, DB)
install_discovery_ops(app, DB)
install_ai_ops(app, DB)
install_national_data_center(app)

__all__ = ["app"]
