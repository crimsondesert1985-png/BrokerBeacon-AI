"""Load BrokerBeacon Sprint 37 extensions after the main application imports."""
import builtins
import sys

_original_import = builtins.__import__
_applied = False


def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    global _applied
    module = _original_import(name, globals, locals, fromlist, level)
    if not _applied and name == "app" and "app" in sys.modules:
        try:
            from sprint37_patch import apply
            apply(sys.modules["app"])
            _applied = True
        except Exception as exc:
            print(f"Sprint 37 extension failed to load: {exc}", flush=True)
    return module


builtins.__import__ = _patched_import
