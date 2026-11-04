"""Follow Glorya jobs in the background and report in the chat that started them.

One daemon thread per job long-polls ``get_job`` through Hermes' MCP client. The thread runs in a
copy of the starting call's context, so ``ctx.post_message`` keeps posting into that chat after the
turn ends. Finished files are downloaded and handed to the agent with ``ctx.inject_message`` so the
chat receives them as native attachments; without that grant the chat gets links.
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import media, render
from .client import FATAL_CODES, Glorya, GloryaError
from .settings import Settings
from .store import TERMINAL, Store

logger = logging.getLogger(__name__)

POLL_WAIT_SECONDS = 30
MIN_CALL_SPACING = 2.0
MIN_EDIT_SPACING = 2.0
MAX_FAILURES = 8
MAX_FOLLOWERS = 8


@dataclass
class Session:
    """Where a job's updates go: the gateway routing key, the stored session id and the surface."""
    key: str = ""
    session_id: str = ""
    platform: str = ""


def current_session() -> Session:
    try:
        from gateway.session_context import get_session_env
    except Exception:
        return Session()
    return Session(key=get_session_env("HERMES_SESSION_KEY", ""), session_id=get_session_env("HERMES_SESSION_ID", ""),
                   platform=get_session_env("HERMES_SESSION_PLATFORM", ""))


def broadcast(event: str, payload: dict[str, Any]) -> None:
    """Tell connected Desktop windows a job changed (no-op without a Desktop)."""
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event
        broadcast_plugin_event("glorya", event, payload)
    except Exception:
        logger.debug("glorya: desktop event %s not sent", event, exc_info=True)


class Follower:
    def __init__(self, ctx: Any, store: Store, settings: Callable[[], Settings], glorya: Callable[[], Glorya],
                 data_dir: Callable[[], Path], *, clock: Callable[[], float] = time.time,
                 sleep: Optional[Callable[[float], None]] = None,
                 session: Callable[[], Session] = current_session,
                 notify: Callable[[str, dict[str, Any]], None] = broadcast,
                 fetch: Callable[..., Any] = media.fetch_assets):
        self._ctx = ctx
        self._store = store
        self._settings = settings
        self._glorya = glorya
        self._data_dir = data_dir
        self._clock = clock
        self._stop = threading.Event()
        self._sleep = sleep or (lambda seconds: self._stop.wait(seconds))
        self._session = session
        self._notify = notify
        self._fetch = fetch
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}

    # -- starting -----------------------------------------------------------------------------

    def in_cron(self) -> bool:
        try:
            return self._ctx.current_cron_execution() is not None
        except Exception:
            return False

    def following(self, job_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(job_id)
            return bool(thread and thread.is_alive())

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for thread in self._threads.values() if thread.is_alive())

    def start(self, job_id: str, *, kind: str = "", title: str = "", open_url: str = "",
              source: str = "agent") -> bool:
        """Follow ``job_id`` from the calling chat. True when this plugin now reports the job there,
        so the model need not poll; False when it can't (cron, no live chat, disabled, at capacity)."""
        settings = self._settings()
        if not settings.follow or not job_id or self.in_cron():
            return False
        if self.following(job_id):
            return True
        session = self._session()
        if not session.key:
            return False
        if self.active_count() >= MAX_FOLLOWERS:
            logger.info("glorya: %d jobs already followed; not following %s", MAX_FOLLOWERS, job_id)
            return False
        handle = self._ctx.post_message(render.started(kind, title, open_url))
        if not getattr(handle, "ok", False):
            logger.info("glorya: no live chat for %s (%s)", job_id, getattr(handle, "error", "?"))
            return False
        self._store.track(job_id, kind=kind, title=title, open_url=open_url, source=source,
                          session_key=session.key, platform=session.platform)
        self._store.set_session_id(job_id, session.session_id)
        started_at = self._clock()
        run = contextvars.copy_context().run
        thread = threading.Thread(target=run, args=(self._run, job_id, handle, started_at), daemon=True,
                                  name=f"glorya-follow-{job_id[:8]}")
        with self._lock:
            self._threads = {key: t for key, t in self._threads.items() if t.is_alive()}
            self._threads[job_id] = thread
        thread.start()
        self._notify("job.updated", {"job_id": job_id, "status": "running"})
        return True

    def stop(self) -> None:
        self._stop.set()

    # -- the loop -------------------------------------------------------------------------------

    def _run(self, job_id: str, handle: Any, started_at: float) -> None:
        try:
            self._follow(job_id, handle, started_at)
        except Exception:
            logger.exception("glorya: follower for %s crashed", job_id)
            self._post(f"Glorya: I lost track of job {job_id[:8]}. Send /glorya follow {job_id[:8]} to pick it up again.")
        finally:
            with self._lock:
                if self._threads.get(job_id) is threading.current_thread():
                    self._threads.pop(job_id, None)

    def _follow(self, job_id: str, handle: Any, started_at: float) -> None:
        settings = self._settings()
        client = self._glorya()
        deadline = started_at + settings.follow_minutes * 60
        failures, last_text, last_edit, last_call = 0, "", 0.0, 0.0
        while not self._stop.is_set():
            if self._clock() > deadline:
                job = self._store.get(job_id)
                self._edit(handle, f"{render.headline(job.kind if job else '', job.title if job else '')}\n"
                                   f"Still running after {settings.follow_minutes} min. "
                                   f"Send /glorya status {job_id[:8]} to check, or open it in Glorya.")
                return
            spacing = MIN_CALL_SPACING - (self._clock() - last_call)
            if spacing > 0:
                self._sleep(spacing)
            last_call = self._clock()
            try:
                view = client.get_job(job_id, wait_seconds=POLL_WAIT_SECONDS)
            except GloryaError as error:
                if error.code in FATAL_CODES:
                    self._edit(handle, render.failure(error))
                    return
                failures += 1
                if failures >= MAX_FAILURES:
                    self._post(f"Glorya: I can't reach job {job_id[:8]} right now ({error.message}). "
                               f"Send /glorya follow {job_id[:8]} to try again.")
                    return
                retry = error.data.get("retry_after_seconds")
                self._sleep(float(retry) if isinstance(retry, (int, float)) else min(60.0, 5.0 * 2 ** min(failures, 4)))
                continue
            failures = 0
            view = {**view, "job_id": view.get("job_id") or job_id}
            job = self._store.save_view(job_id, view)
            if job is None:
                return
            state = str(view.get("status") or "running")
            text = render.status(view, started_at, self._clock())
            if text != last_text:
                wait = MIN_EDIT_SPACING - (self._clock() - last_edit)
                if wait > 0 and state not in TERMINAL:
                    self._sleep(wait)
                self._edit(handle, text)
                last_text, last_edit = text, self._clock()
                self._notify("job.updated", {"job_id": job_id, "status": state})
            if state == "needs_input":
                self._ask(job.job_id, view, job.asked)
            if state in TERMINAL:
                self._finish(job_id, view)
                return

    # -- reporting ------------------------------------------------------------------------------

    def _post(self, text: str) -> None:
        try:
            self._ctx.post_message(text)
        except Exception:
            logger.debug("glorya: post failed", exc_info=True)

    @staticmethod
    def _edit(handle: Any, text: str) -> None:
        try:
            handle.edit(text)
        except Exception:
            logger.debug("glorya: edit failed", exc_info=True)

    def _ask(self, job_id: str, view: dict[str, Any], asked: list[str]) -> None:
        fresh = [q for q in view.get("questions") or []
                 if isinstance(q, dict) and q.get("request_id") and q["request_id"] not in asked]
        for q in fresh:
            self._post(render.question(view, q, job_id[:8]))
        if fresh:
            self._store.add_marks(job_id, "asked", [q["request_id"] for q in fresh])

    def _finish(self, job_id: str, view: dict[str, Any]) -> None:
        state = str(view.get("status"))
        if state == "failed":
            self._post(f"❌ {render.headline(str(view.get('kind') or ''), str(view.get('title') or ''))} failed: "
                       f"{render.clip(view.get('error') or view.get('progress'), 300) or 'no details'}\n"
                       f"Try /glorya refine {job_id[:8]} <what to change>, or start a new one.")
            return
        if state == "cancelled":
            self._post(f"⏹ {render.headline(str(view.get('kind') or ''), '')} stopped. Finished files stay in Glorya.")
            return
        job = self._store.get(job_id)
        delivered = set(job.delivered if job else [])
        new_assets = [a for a in render.assets_of(view) if str(a.get("id") or a.get("url")) not in delivered]
        if new_assets and self.deliver_files(job_id, view, new_assets):
            return
        self._post(render.result_links(view))
        if new_assets:
            self._store.add_marks(job_id, "delivered", [str(a.get("id") or a.get("url")) for a in new_assets])

    def deliver_files(self, job_id: str, view: dict[str, Any], assets: list[dict[str, Any]]) -> bool:
        """Download ``assets`` and have the agent attach them in this chat. False to fall back to links."""
        settings = self._settings()
        if settings.deliver != "attach":
            return False
        session = self._session()
        folder = self._data_dir() / "media" / job_id
        files, links = self._fetch(assets, folder, settings.attach_max_mb * 1024 * 1024)
        if not files:
            return False
        job = self._store.get(job_id)
        self._store.set_files(job_id, [*(job.files if job else []), *files])
        try:
            accepted = bool(session.key) and self._ctx.inject_message(
                render.delivery_turn(view, files), role="user", session_key=session.key)
        except Exception:
            logger.debug("glorya: inject failed", exc_info=True)
            accepted = False
        if not accepted:
            return False
        if links:
            self._post("More from Glorya (too big to attach):\n"
                       + "\n".join(f"{a.get('label') or a.get('type') or 'File'}: {a.get('url')}" for a in links))
        self._store.add_marks(job_id, "delivered", [str(a.get("id") or a.get("url")) for a in assets])
        self._notify("job.updated", {"job_id": job_id, "status": "completed"})
        return True
