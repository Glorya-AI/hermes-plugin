"""Glorya backend for Hermes Desktop: the jobs this profile follows, read from the plugin's store.

Mounted at ``/api/plugins/glorya/`` once ``glorya`` is in ``plugins.enabled``. Read-only: actions go
through the chat (``/glorya …``), so they run with the user's Glorya sign-in and Hermes' approvals.
The host scopes each request to its profile; the store is opened per request, never at import.

Routes:
    GET /jobs?limit=   newest jobs first, plus how many are running or waiting for an answer
    GET /job?id=       one job (the ``::glorya-job`` card)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _load_store_module():
    """``store.py`` beside this folder: the host imports this file standalone, without the package."""
    name = "hermes_glorya_store"
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / "store.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_store_module = _load_store_module()


def _store():
    from plugins.plugin_storage import plugin_db
    return _store_module.Store(lambda: plugin_db("glorya"))


@router.get("/jobs")
def jobs(limit: int = Query(30, ge=1, le=100)) -> dict:
    store = _store()
    try:
        rows = store.recent(limit=limit)
    finally:
        store.close()
    return {
        "jobs": [job.to_public() for job in rows],
        "running": sum(1 for job in rows if job.status == "running"),
        "waiting": sum(1 for job in rows if job.status == "needs_input"),
    }


@router.get("/job")
def job(id: str = Query(..., min_length=1, max_length=200)) -> dict:  # noqa: A002 - query name
    store = _store()
    try:
        found = store.get(id)
    finally:
        store.close()
    if found is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return {"job": found.to_public()}
