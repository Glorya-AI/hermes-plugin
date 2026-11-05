from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _fake_fastapi() -> types.ModuleType:
    module = types.ModuleType("fastapi")

    class APIRouter:
        def get(self, _path):
            return lambda fn: fn

    module.APIRouter = APIRouter
    module.HTTPException = type("HTTPException", (Exception,), {})
    module.Query = lambda default=None, **_: default
    return module


def test_the_host_can_load_the_dashboard_backend_standalone(monkeypatch):
    # The host execs plugin_api.py by path, without the plugin package.
    monkeypatch.setitem(sys.modules, "fastapi", _fake_fastapi())
    monkeypatch.delitem(sys.modules, "hermes_glorya_store", raising=False)
    path = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
    spec = importlib.util.spec_from_file_location("glorya_dashboard_api", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._store_module.Store and module._store_module.Job
