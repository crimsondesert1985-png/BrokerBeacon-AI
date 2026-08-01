"""Compatibility loader for Sprint 37 extensions under gunicorn app:app.

Python imports sitecustomize during interpreter startup. We hook the first import
of the main app module, then register the Sprint 37 APIs without changing the
existing Render start command.
"""
import builtins
import sys

_original_import = builtins.__import__
_installed = False


def _install_extensions():
    global _installed
    if _installed:
        return
    app_module = sys.modules.get("app")
    if app_module is None or not hasattr(app_module, "app") or not hasattr(app_module, "DB"):
        return
    from ai_ops_api import install_ai_ops
    from discovery_ops_api import install_discovery_ops
    from national_data_center import install_national_data_center
    from national_warehouse_api import install_national_warehouse
    from state_connector_api import install_state_connectors

    flask_app = app_module.app
    db_path = app_module.DB
    install_national_warehouse(flask_app, db_path)
    install_state_connectors(flask_app, db_path)
    install_discovery_ops(flask_app, db_path)
    install_ai_ops(flask_app, db_path)
    install_national_data_center(flask_app)
    _installed = True
    print("BrokerBeacon Sprint 37 extensions loaded under app:app", flush=True)


def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if name == "app":
        try:
            _install_extensions()
        except Exception as exc:
            print(f"Sprint 37 extension loader failed: {exc}", flush=True)
            raise
    return module


builtins.__import__ = _patched_import
