"""Load the plugin directory as a package and give tests a scripted Hermes ``ctx``."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent

# Running from the plugin dir puts it on sys.path, where its modules could shadow stdlib/core names.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != ROOT]
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


def _load_package():
    if "glorya_plugin" in sys.modules:
        return sys.modules["glorya_plugin"]
    spec = importlib.util.spec_from_file_location("glorya_plugin", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["glorya_plugin"] = module
    spec.loader.exec_module(module)
    return module


_load_package()


def mcp_ok(payload: dict[str, Any]) -> dict[str, Any]:
    """What ``ctx.call_mcp`` returns for a successful Glorya tool call."""
    return {"ok": True, "result": json.dumps(payload)}


def mcp_error(code: str, message: str = "Nope.", **details: Any) -> dict[str, Any]:
    return {"ok": False, "error": f"{message}\n{json.dumps({'error': code, **details})}"}


class Handle:
    def __init__(self, ctx: "FakeCtx", text: str, ok: bool = True):
        self.ok, self.error, self.message_id = ok, None if ok else "no_conversation", "m1" if ok else None
        self.texts = [text]
        self._ctx = ctx

    def edit(self, text: str) -> dict[str, Any]:
        self.texts.append(text)
        self._ctx.edits.append(text)
        return {"ok": True}


class FakeCtx:
    def __init__(self, settings: Optional[dict[str, Any]] = None):
        self.settings = settings or {}
        self.responses: dict[str, list[Any]] = {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.posts: list[str] = []
        self.edits: list[str] = []
        self.injected: list[dict[str, Any]] = []
        self.inject_result = True
        self.post_ok = True
        self.cron = None
        self.surface = "telegram"
        self.choices: list[Any] = []
        self.allowed = True

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def script(self, tool: str, *responses: Any) -> None:
        self.responses.setdefault(tool, []).extend(responses)

    def call_mcp(self, server: str, tool: str, arguments: Optional[dict] = None, timeout: float = 30) -> dict[str, Any]:
        if not self.allowed:
            raise PermissionError("not allowed")
        self.calls.append((server, tool, dict(arguments or {})))
        queue = self.responses.get(tool) or []
        if not queue:
            raise AssertionError(f"unscripted MCP call {tool}")
        response = queue.pop(0) if len(queue) > 1 else queue[0]
        return response(arguments) if callable(response) else response

    def post_message(self, text: str) -> Handle:
        self.posts.append(text)
        return Handle(self, text, ok=self.post_ok)

    def inject_message(self, content: str, role: str = "user", *, session_key: str = "", origin: Any = None) -> bool:
        self.injected.append({"content": content, "role": role, "session_key": session_key})
        return self.inject_result

    def session_surface(self) -> str:
        return self.surface

    def current_cron_execution(self) -> Any:
        return self.cron

    def ask_choice(self, question: str, choices: list) -> Any:
        return self.choices.pop(0) if self.choices else None


@pytest.fixture
def ctx() -> FakeCtx:
    return FakeCtx()


@pytest.fixture
def store(clock):
    from glorya_plugin.store import Store
    return Store(lambda: sqlite3.connect(":memory:", check_same_thread=False), clock=clock)


class Clock:
    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def plugin(ctx, store, clock, tmp_path):
    from glorya_plugin.core import GloryaPlugin
    from glorya_plugin.follower import Follower, Session

    session = lambda: Session(key="agent:main:telegram:dm:42", session_id="ses_1", platform="telegram")  # noqa: E731
    fetched: list[Any] = []

    def fetch(assets, folder, max_bytes, limit=4, **_):
        files = [{"path": str(folder / f"{a['id']}.mp4"), "asset_id": a["id"], "type": a.get("type"),
                  "label": a.get("label"), "url": a["url"]} for a in assets[:limit]]
        fetched.append(files)
        return files, assets[limit:]

    instance = GloryaPlugin(ctx, store=store, data_dir=lambda: tmp_path, clock=clock, session=session, fetch=fetch,
                            connection=lambda server: "ok")
    instance.follower = Follower(ctx, store, instance.settings, instance.glorya, lambda: tmp_path, clock=clock,
                                 sleep=lambda _s: None, session=session, notify=lambda *_: None, fetch=fetch)
    instance.fetched = fetched
    return instance


def join_followers(plugin, timeout: float = 5.0) -> None:
    for thread in list(plugin.follower._threads.values()):
        thread.join(timeout)
    import threading
    for thread in threading.enumerate():
        if thread.name.startswith("glorya-follow-"):
            thread.join(timeout)


def view(status: str = "running", **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"job_id": "job-1234567890", "kind": "video_ad", "status": status, "title": "Serum UGC",
                            "open_url": "https://platform.glorya.ai/v2/w/x", "progress": "", "assets": [],
                            "questions": [], "site": None}
    base.update(extra)
    return base


Factory = Callable[..., dict[str, Any]]
